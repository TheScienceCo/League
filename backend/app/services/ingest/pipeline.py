"""The ingestion pipeline.

    Riot identifier -> match ids -> match + timeline -> normalized rows -> features

Concurrency model: the Riot calls are async and run a few at a time under a
semaphore (the rate limiter is the real throttle); the database work is
synchronous and happens in short transactions between awaits, so no transaction
is ever held open across a network call.

Idempotency: re-running a job for the same player is cheap. Matches already
stored are skipped unless `force_refresh` is set, and every writer is an upsert.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import SR_QUEUES, region_for_platform
from app.core.errors import NotFoundError, RiftLabError
from app.core.logging import get_logger
from app.db.models import IngestJob, JobStatus, Match, Summoner
from app.db.session import session_scope as _default_scope
from app.services.analytics.features import compute_and_store_features
from app.services.analytics.objectives import analyze_objectives
from app.services.analytics.roams import analyze_roams
from app.services.ingest.persistence import (
    backfill_participant_ranks,
    persist_match,
    persist_timeline,
    upsert_league_entries,
    upsert_summoner,
)
from app.services.riot.protocol import RiotProvider

log = get_logger(__name__)


@dataclass(slots=True)
class IngestOptions:
    count: int = 30
    queue: int | None = 420
    include_timeline: bool = True
    #: Look up ranked standing for *every* participant, not just the requested
    #: player. This makes rank cohorts dense, but costs ~10 extra Riot calls per
    #: match — sensible for seeding and offline dataset builds, not for
    #: interactive requests against a personal key.
    resolve_participant_ranks: bool = False
    force_refresh: bool = False
    concurrency: int = 4


@dataclass(slots=True)
class IngestResult:
    puuid: str
    discovered: int = 0
    ingested: int = 0
    skipped: int = 0
    timelines: int = 0
    features: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> JobStatus:
        if self.errors and not self.ingested:
            return JobStatus.FAILED
        if self.errors:
            return JobStatus.PARTIAL
        return JobStatus.SUCCEEDED


#: A callable returning a transactional context manager over a Session.
SessionScope = Callable[[], AbstractContextManager[Session]]


class IngestionService:
    """Drives ingestion for one provider.

    The session scope is injectable. By default each unit of work opens its own
    short transaction (`session_scope`), which is what the worker wants: no
    transaction is held across a network call. The API passes a scope bound to
    the current request instead, so that identity resolution is visible to the
    rest of the request rather than landing in a session the caller cannot see.
    """

    def __init__(
        self, provider: RiotProvider, *, session_scope: SessionScope | None = None
    ) -> None:
        self.provider = provider
        self._scope: SessionScope = session_scope or _default_scope

    # --- identity ---------------------------------------------------------

    async def resolve_riot_id(self, riot_id: str, platform: str) -> str:
        """`Name#TAG` -> PUUID, persisting the account and its standing."""
        if "#" not in riot_id:
            raise NotFoundError(
                "a Riot ID must be formatted as Name#TAG",
                detail={"received": riot_id},
            )
        game_name, tag_line = riot_id.rsplit("#", 1)
        account = await self.provider.get_account_by_riot_id(
            game_name.strip(), tag_line.strip(), platform=platform
        )
        await self._store_identity(account.puuid, platform, account=account)
        return account.puuid

    async def _store_identity(self, puuid: str, platform: str, *, account=None) -> None:  # type: ignore[no-untyped-def]
        if account is None:
            account = await self.provider.get_account_by_puuid(puuid, platform=platform)
        try:
            summoner = await self.provider.get_summoner_by_puuid(puuid, platform=platform)
        except RiftLabError:
            summoner = None
        try:
            entries = await self.provider.get_league_entries(puuid, platform=platform)
        except RiftLabError as exc:
            log.warning("ingest.league_entries_failed", puuid=puuid, error=str(exc))
            entries = []
        with self._scope() as session:
            upsert_summoner(session, account, summoner, platform)
            upsert_league_entries(session, puuid, entries)

    async def refresh_player(self, puuid: str, platform: str) -> None:
        await self._store_identity(puuid, platform)

    # --- matches ----------------------------------------------------------

    async def ingest_player(
        self,
        puuid: str,
        platform: str,
        options: IngestOptions | None = None,
        *,
        job_id: str | None = None,
    ) -> IngestResult:
        opts = options or IngestOptions()
        result = IngestResult(puuid=puuid)
        region_for_platform(platform)  # validates the platform early

        self._job_update(job_id, status=JobStatus.RUNNING, started_at=datetime.now(UTC))
        try:
            await self._store_identity(puuid, platform)
            match_ids = await self._discover_matches(puuid, platform, opts)
            result.discovered = len(match_ids)
            self._job_update(job_id, matches_discovered=len(match_ids))

            pending = match_ids if opts.force_refresh else self._filter_known(match_ids)
            result.skipped = len(match_ids) - len(pending)

            semaphore = asyncio.Semaphore(max(1, opts.concurrency))
            tasks = [
                self._ingest_one(mid, platform, opts, semaphore, result, job_id) for mid in pending
            ]
            await asyncio.gather(*tasks)
        except RiftLabError as exc:
            result.errors.append(str(exc))
            log.error("ingest.failed", puuid=puuid, error=str(exc))
            self._job_update(
                job_id,
                status=JobStatus.FAILED,
                error=str(exc),
                finished_at=datetime.now(UTC),
            )
            return result

        with self._scope() as session:
            row = session.get(Summoner, puuid)
            if row is not None:
                row.last_ingested_at = datetime.now(UTC)

        self._job_update(
            job_id,
            status=result.status,
            matches_ingested=result.ingested,
            matches_skipped=result.skipped,
            timelines_ingested=result.timelines,
            features_computed=result.features,
            error="; ".join(result.errors[:5]) or None,
            finished_at=datetime.now(UTC),
        )
        log.info(
            "ingest.completed",
            puuid=puuid,
            discovered=result.discovered,
            ingested=result.ingested,
            skipped=result.skipped,
            errors=len(result.errors),
        )
        return result

    async def _discover_matches(self, puuid: str, platform: str, opts: IngestOptions) -> list[str]:
        """Page through match ids until we have `count` of them."""
        wanted = min(opts.count, settings.ingest_max_match_count)
        collected: list[str] = []
        start = 0
        while len(collected) < wanted:
            page = await self.provider.get_match_ids(
                puuid,
                platform=platform,
                start=start,
                count=min(100, wanted - len(collected)),
                queue=opts.queue,
            )
            if not page:
                break
            collected.extend(page)
            start += len(page)
        return collected[:wanted]

    def _filter_known(self, match_ids: list[str]) -> list[str]:
        if not match_ids:
            return []
        with self._scope() as session:
            known = set(
                session.scalars(select(Match.match_id).where(Match.match_id.in_(match_ids)))
            )
        return [m for m in match_ids if m not in known]

    async def _ingest_one(
        self,
        match_id: str,
        platform: str,
        opts: IngestOptions,
        semaphore: asyncio.Semaphore,
        result: IngestResult,
        job_id: str | None,
    ) -> None:
        async with semaphore:
            try:
                match_dto = await self.provider.get_match(match_id, platform=platform)
            except RiftLabError as exc:
                result.errors.append(f"{match_id}: {exc}")
                return

            queue_id = match_dto.info.queue_id
            if queue_id not in SR_QUEUES:
                # ARAM and friends have no lanes, no jungle and a different map;
                # none of the analytics below would mean anything there.
                result.skipped += 1
                log.debug("ingest.skipped_queue", match_id=match_id, queue_id=queue_id)
                return

            timeline_dto = None
            if opts.include_timeline:
                try:
                    timeline_dto = await self.provider.get_timeline(match_id, platform=platform)
                except RiftLabError as exc:
                    log.warning("ingest.timeline_failed", match_id=match_id, error=str(exc))

            if opts.resolve_participant_ranks:
                await self._resolve_ranks(match_dto, platform)

            try:
                with self._scope() as session:
                    persist_match(
                        session,
                        match_dto,
                        platform=platform,
                        data_source="mock" if settings.use_mock_riot else "riot",
                    )
                    if timeline_dto is not None:
                        persist_timeline(session, timeline_dto, match_id=match_id)
                        result.timelines += 1
                    backfill_participant_ranks(session, match_id)

                with self._scope() as session:
                    written = compute_and_store_features(session, match_id)
                    analyze_objectives(session, match_id)
                    analyze_roams(session, match_id)
                    result.features += written
            except Exception as exc:
                result.errors.append(f"{match_id}: {exc}")
                log.exception("ingest.persist_failed", match_id=match_id)
                return

            result.ingested += 1
            self._job_update(job_id, matches_ingested=result.ingested)

    async def _resolve_ranks(self, match_dto, platform: str) -> None:  # type: ignore[no-untyped-def]
        """Fetch standings for participants we have never seen before."""
        puuids = [p.puuid for p in match_dto.info.participants]
        with self._scope() as session:
            known = set(session.scalars(select(Summoner.puuid).where(Summoner.puuid.in_(puuids))))
        for puuid in puuids:
            if puuid in known:
                continue
            try:
                await self._store_identity(puuid, platform)
            except RiftLabError as exc:
                log.debug("ingest.rank_lookup_failed", puuid=puuid, error=str(exc))

    # --- job bookkeeping --------------------------------------------------

    def _job_update(self, job_id: str | None, **fields: object) -> None:
        if job_id is None:
            return
        with self._scope() as session:
            job = session.get(IngestJob, job_id)
            if job is None:
                return
            for key, value in fields.items():
                if value is not None or key == "error":
                    setattr(job, key, value)


def create_job(session: Session, puuid: str, platform: str, requested: int) -> IngestJob:
    job = IngestJob(
        puuid=puuid,
        platform=platform,
        status=JobStatus.PENDING,
        requested_matches=requested,
    )
    session.add(job)
    session.flush()
    return job
