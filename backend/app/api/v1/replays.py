"""Replay upload and analysis."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import DbSession
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.aoe2 import MatchAnalysisOut, ReplayListItem
from app.services.analysis import insights, persistence, store
from app.services.analysis.metrics import analyze
from app.services.parser import ReplayParseError, get_parser

log = get_logger(__name__)

router = APIRouter()

ACCEPTED_SUFFIXES = (".aoe2record", ".mgz", ".mgx", ".aoe2mpgame")


@router.post(
    "",
    response_model=MatchAnalysisOut,
    summary="Upload a replay and get its analysis",
    status_code=status.HTTP_201_CREATED,
)
async def upload_replay(session: DbSession, file: UploadFile = File(...)) -> MatchAnalysisOut:
    """Parse and analyse a replay, returning the full result.

    Analysis is synchronous because it is fast — a 45-minute game parses in a
    couple of seconds — and a synchronous result means the caller never has to
    poll. Re-uploading a file you have already analysed returns the stored
    result rather than reparsing.
    """
    filename = file.filename or "replay.aoe2record"
    if not filename.lower().endswith(ACCEPTED_SUFFIXES):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected one of {', '.join(ACCEPTED_SUFFIXES)}; got {filename!r}.",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File is empty.")
    if len(raw) > settings.max_replay_size_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Replay exceeds the {settings.max_replay_size_mb} MB limit.",
        )

    replay_id = store.file_digest(raw)
    if (cached := store.load(replay_id)) is not None:
        log.info("replay.cache_hit", replay_id=replay_id)
        return MatchAnalysisOut.model_validate(cached)

    try:
        parsed = get_parser().parse(raw)
    except ReplayParseError as exc:
        # A file we cannot parse is the user's most likely failure mode, so say
        # what went wrong rather than returning a generic 500.
        log.warning("replay.parse_failed", filename=filename, error=str(exc))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Could not parse {filename!r}. It may be corrupt, or from a game "
                f"version this parser does not support. ({exc})"
            ),
        ) from exc

    analysis = analyze(parsed)
    payload = _serialise(replay_id, filename, analysis)
    store.save(replay_id, raw, payload)
    persistence.index_analysis(session, payload)
    log.info(
        "replay.analysed",
        replay_id=replay_id,
        map=analysis.map_name,
        players=len(analysis.players),
        warnings=len(analysis.warnings),
    )
    return MatchAnalysisOut.model_validate(payload)


@router.get("", response_model=list[ReplayListItem], summary="Recently analysed replays")
async def list_replays(limit: int = 20) -> list[ReplayListItem]:
    return [
        ReplayListItem(
            replay_id=doc["replay_id"],
            filename=doc["filename"],
            map_name=doc.get("map_name"),
            duration_ms=doc["duration_ms"],
            players=[p["name"] for p in doc.get("players", [])],
        )
        for doc in store.list_all(limit=limit)
    ]


@router.get("/{replay_id}", response_model=MatchAnalysisOut, summary="Fetch a stored analysis")
async def get_replay(replay_id: str) -> MatchAnalysisOut:
    doc = store.load(replay_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No analysis for that id.")
    return MatchAnalysisOut.model_validate(doc)


def _serialise(replay_id: str, filename: str, analysis) -> dict:
    return {
        "replay_id": replay_id,
        "filename": filename,
        "map_name": analysis.map_name,
        "duration_ms": analysis.duration_ms,
        "version": analysis.version,
        "warnings": analysis.warnings,
        "players": [
            {
                "player_number": p.player_number,
                "name": p.name,
                "civilization": p.civilization,
                "winner": p.winner,
                "opening": p.opening,
                "age_timings_ms": p.age_timings_ms,
                "float_by_age": p.float_by_age,
                "metrics": {k: asdict(v) for k, v in p.metrics.items()},
                "build_order": p.build_order,
                "resource_curve": p.resource_curve,
                "insights": insights.for_player(analysis, p),
            }
            for p in analysis.players
        ],
    }
