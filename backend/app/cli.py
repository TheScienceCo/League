"""`riftlab` — operational CLI for ingestion, analytics refresh and training."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import session_scope
from app.services.analytics.refresh import refresh_all
from app.services.ingest.pipeline import IngestionService, IngestOptions
from app.services.ml.skill_gap import analyze_player, train_skill_gap_model
from app.services.riot import get_riot_provider

app = typer.Typer(help="Rift Lab operations", no_args_is_help=True)
log = get_logger(__name__)


@app.callback()
def _root() -> None:
    configure_logging()


@app.command()
def ingest(
    riot_id: Annotated[str, typer.Argument(help="Riot ID, e.g. 'RiftLabDemo#NA1'")],
    platform: Annotated[str | None, typer.Option(help="Platform host")] = None,
    count: Annotated[int, typer.Option(help="Matches to ingest")] = 30,
    queue: Annotated[int, typer.Option(help="Queue id filter (0 for any)")] = 420,
    ranks: Annotated[
        bool, typer.Option("--ranks/--no-ranks", help="Resolve every participant's rank")
    ] = False,
) -> None:
    """Ingest a player's recent matches, timelines and derived features."""
    plat = platform or settings.riot_platform

    async def run() -> None:
        service = IngestionService(get_riot_provider())
        puuid = await service.resolve_riot_id(riot_id, plat)
        result = await service.ingest_player(
            puuid,
            plat,
            IngestOptions(
                count=count,
                queue=queue or None,
                resolve_participant_ranks=ranks,
            ),
        )
        typer.echo(
            f"{riot_id}: discovered={result.discovered} ingested={result.ingested} "
            f"skipped={result.skipped} timelines={result.timelines} errors={len(result.errors)}"
        )
        await service.provider.aclose()

    asyncio.run(run())


@app.command()
def seed(
    accounts: Annotated[int, typer.Option(help="Synthetic accounts to ingest")] = 40,
    matches: Annotated[int, typer.Option(help="Matches per account")] = 12,
    platform: Annotated[str | None, typer.Option()] = None,
    refresh: Annotated[bool, typer.Option("--refresh/--no-refresh")] = True,
) -> None:
    """Build a demo corpus spanning every rank band.

    Only meaningful against the simulated provider — it refuses to run against a
    live key, because "seed 40 accounts" would be several thousand Riot calls.
    """
    if not settings.use_mock_riot:
        raise typer.BadParameter(
            "seeding is only supported against the simulated provider; "
            "set RIOT_USE_MOCK=true or use `riftlab ingest` for real accounts"
        )
    from app.services.ingest.seed import seed_corpus

    plat = platform or settings.riot_platform
    summary = asyncio.run(seed_corpus(accounts=accounts, matches=matches, platform=plat))
    typer.echo(json.dumps(summary, indent=2))
    if refresh:
        refresh_analytics()


@app.command("refresh-analytics")
def refresh_analytics(
    limit_matches: Annotated[int, typer.Option(help="Cap matches used for the risk model")] = 0,
    train: Annotated[bool, typer.Option("--train/--no-train")] = True,
) -> None:
    """Rebuild cohorts, the map risk surface, and the rank-separation model."""
    with session_scope() as session:
        report = refresh_all(
            session,
            limit_matches=limit_matches or None,
            train_skill_gap=train,
        )
    typer.echo(json.dumps(report.to_dict(), indent=2, default=str))


@app.command("train-skill-gap")
def train_skill_gap() -> None:
    """Train (or retrain) the Skill Gap model on the current corpus."""
    with session_scope() as session:
        artifact = train_skill_gap_model(session)
    typer.echo(
        json.dumps(
            {
                "version": artifact.version,
                "n_samples": artifact.n_samples,
                "metrics": {k: v for k, v in artifact.metrics.items() if k != "rank_correlations"},
                "top_features": sorted(
                    artifact.feature_importances.items(), key=lambda kv: kv[1], reverse=True
                )[:10],
            },
            indent=2,
            default=str,
        )
    )


@app.command("skill-gap")
def skill_gap(
    riot_id: Annotated[str, typer.Argument(help="Riot ID to analyse")],
    platform: Annotated[str | None, typer.Option()] = None,
    target: Annotated[str | None, typer.Option(help="Target tier band")] = None,
) -> None:
    """Print the Skill Gap report for one player."""
    plat = platform or settings.riot_platform

    async def resolve() -> str:
        service = IngestionService(get_riot_provider())
        puuid = await service.resolve_riot_id(riot_id, plat)
        await service.provider.aclose()
        return puuid

    puuid = asyncio.run(resolve())
    with session_scope() as session:
        report = analyze_player(session, puuid, target_tier_group=target)
    typer.echo(json.dumps(report.to_dict(), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    app()
