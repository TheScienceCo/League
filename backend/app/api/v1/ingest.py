"""Ingestion control plane: start a job, poll it, refresh derived analytics."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import DbSession, RiotDep, request_session_scope
from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.db.models import IngestJob
from app.db.session import session_scope
from app.schemas.ingest import IngestRequest, JobResponse, RefreshResponse
from app.services.analytics.refresh import refresh_all
from app.services.ingest.pipeline import IngestionService, IngestOptions, create_job

router = APIRouter()


def _job_payload(job: IngestJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        puuid=job.puuid,
        platform=job.platform,
        status=job.status,
        requested_matches=job.requested_matches,
        matches_discovered=job.matches_discovered,
        matches_ingested=job.matches_ingested,
        matches_skipped=job.matches_skipped,
        timelines_ingested=job.timelines_ingested,
        features_computed=job.features_computed,
        progress=job.progress,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post(
    "/ingest",
    response_model=JobResponse,
    status_code=202,
    summary="Start ingesting a player's recent matches",
)
async def start_ingest(
    payload: IngestRequest,
    session: DbSession,
    provider: RiotDep,
    background: BackgroundTasks,
) -> JobResponse:
    """Kick off ingestion and return immediately with a job to poll.

    Ingestion is long-running and rate-limited upstream, so it never blocks a
    request. The job row is the source of truth for progress.
    """
    if not payload.riot_id and not payload.puuid:
        raise ValidationError("provide either `riot_id` or `puuid`")

    # Resolve identity inside the request so the job row can reference a PUUID
    # the caller can immediately look up...
    resolver = IngestionService(provider, session_scope=request_session_scope(session))
    puuid = payload.puuid or await resolver.resolve_riot_id(payload.riot_id or "", payload.platform)
    # ...but run the ingestion itself on its own short transactions, because the
    # request session is closed the moment the response is returned.
    service = IngestionService(provider)

    job = create_job(session, puuid, payload.platform, payload.count)
    session.commit()
    job_id = job.id

    options = IngestOptions(
        count=payload.count,
        queue=payload.queue,
        include_timeline=payload.include_timeline,
        resolve_participant_ranks=payload.resolve_participant_ranks,
        force_refresh=payload.force_refresh,
        concurrency=settings.ingest_concurrency,
    )
    background.add_task(_run_ingest, service, puuid, payload.platform, options, job_id)
    return _job_payload(job)


async def _run_ingest(
    service: IngestionService,
    puuid: str,
    platform: str,
    options: IngestOptions,
    job_id: str,
) -> None:
    try:
        await service.ingest_player(puuid, platform, options, job_id=job_id)
    finally:
        await service.provider.aclose()


@router.get("/ingest/{job_id}", response_model=JobResponse, summary="Poll an ingestion job")
def get_job(job_id: str, session: DbSession) -> JobResponse:
    job = session.get(IngestJob, job_id)
    if job is None:
        raise NotFoundError(f"no ingestion job {job_id}")
    return _job_payload(job)


@router.get("/ingest", response_model=list[JobResponse], summary="Recent ingestion jobs")
def list_jobs(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[JobResponse]:
    from sqlalchemy import select

    jobs = session.scalars(select(IngestJob).order_by(IngestJob.created_at.desc()).limit(limit))
    return [_job_payload(j) for j in jobs]


@router.post(
    "/admin/refresh-analytics",
    response_model=RefreshResponse,
    summary="Rebuild cohorts, the risk surface and the rank-separation model",
)
async def refresh_analytics(
    limit_matches: Annotated[int, Query(ge=0)] = 0,
    train: Annotated[bool, Query()] = True,
) -> RefreshResponse:
    """Corpus-wide rebuild.

    Runs in a worker thread: it is CPU-bound (pandas + scikit-learn) and would
    otherwise block the event loop for the whole request.
    """

    def _run() -> dict:
        with session_scope() as session:
            return refresh_all(
                session,
                limit_matches=limit_matches or None,
                train_skill_gap=train,
            ).to_dict()

    return RefreshResponse.model_validate(await asyncio.to_thread(_run))


@router.post("/admin/train-dva", summary="Train the experimental DVA models")
async def train_dva(limit_matches: Annotated[int, Query(ge=0)] = 0) -> dict:
    from app.services.analytics.dva import train_dva_models

    def _run() -> dict:
        with session_scope() as session:
            return train_dva_models(session, limit_matches=limit_matches or None)

    return await asyncio.to_thread(_run)
