"""Demo corpus generation.

Produces a dataset that spans every rank band, which the cohort engine and the
rank-separation model both need in order to do anything interesting. Accounts are
chosen by scanning candidate names and keeping the ones whose (deterministic)
simulated skill lands in each band, so the spread is by construction rather than
by luck.

This only runs against the simulated provider. Against a live key the equivalent
step is ingesting real accounts you have permission to analyse — see the README.
"""

from __future__ import annotations

from typing import Any

from app.core.constants import TIER_GROUP_ORDER, tier_group
from app.core.logging import get_logger
from app.services.ingest.pipeline import IngestionService, IngestOptions
from app.services.riot.mock import DEMO_ACCOUNTS, MockRiotProvider, mock_puuid_for
from app.services.riot.simulation import rank_for_skill, skill_for_puuid

log = get_logger(__name__)

#: How many candidate names to scan when filling the rank bands.
CANDIDATE_POOL = 4000


def pick_accounts(per_band: int, *, tag: str = "NA1") -> dict[str, list[str]]:
    """Riot IDs bucketed by rank band, `per_band` in each where possible."""
    buckets: dict[str, list[str]] = {band: [] for band in TIER_GROUP_ORDER}
    for band, riot_id in _demo_account_bands():
        if band in buckets:
            buckets[band].append(riot_id)

    for i in range(CANDIDATE_POOL):
        if all(len(v) >= per_band for v in buckets.values()):
            break
        name = f"RiftLab{i:04d}"
        puuid = mock_puuid_for(name, tag)
        tier, _, _ = rank_for_skill(skill_for_puuid(puuid))
        band = tier_group(tier)
        if band in buckets and len(buckets[band]) < per_band:
            buckets[band].append(f"{name}#{tag}")
    return buckets


def _demo_account_bands() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    provider = MockRiotProvider()
    for riot_id in DEMO_ACCOUNTS:
        name, tag = riot_id.split("#")
        puuid = mock_puuid_for(name, tag)
        tier, _, _ = rank_for_skill(provider.skill_of(puuid))
        out.append((tier_group(tier), riot_id))
    return out


async def seed_corpus(
    *, accounts: int = 40, matches: int = 12, platform: str = "na1"
) -> dict[str, Any]:
    """Ingest a spread of simulated accounts and return a summary."""
    per_band = max(1, accounts // len(TIER_GROUP_ORDER))
    buckets = pick_accounts(per_band)

    provider = MockRiotProvider()
    service = IngestionService(provider)
    summary: dict[str, Any] = {
        "accounts_by_band": {k: len(v) for k, v in buckets.items()},
        "matches_per_account": matches,
        "ingested": 0,
        "errors": 0,
        "players": [],
    }

    for band, riot_ids in buckets.items():
        for riot_id in riot_ids:
            puuid = await service.resolve_riot_id(riot_id, platform)
            result = await service.ingest_player(
                puuid,
                platform,
                IngestOptions(
                    count=matches,
                    queue=420,
                    # Resolving every participant's rank is what makes rank
                    # cohorts dense enough to model; cheap against the simulator.
                    resolve_participant_ranks=True,
                ),
            )
            summary["ingested"] += result.ingested
            summary["errors"] += len(result.errors)
            summary["players"].append(
                {"riot_id": riot_id, "band": band, "puuid": puuid, "ingested": result.ingested}
            )
            log.info("seed.account", riot_id=riot_id, band=band, ingested=result.ingested)

    await provider.aclose()
    return summary
