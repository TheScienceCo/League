"""Replay upload and analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.aoe2 import ReplayUploadResponse, ReplayProcessingStatus
from app.db.models import ReplayFile

log = get_logger(__name__)

router = APIRouter(prefix="/replays", tags=["replays"])


@router.post("/upload")
async def upload_replay(
    file: UploadFile = File(...),
    db: AsyncSession | None = None,
) -> ReplayUploadResponse:
    """
    Upload a replay file for analysis.

    The replay is queued for processing. Status can be checked via
    GET /api/v1/replays/{replay_id}/status

    Args:
        file: The .aoe2record replay file
        db: Database session

    Returns:
        Upload response with replay ID and status
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    if not file.filename.endswith((".aoe2record", ".mgz", ".rec")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a replay (.aoe2record, .mgz, or .rec)",
        )

    try:
        # Read file
        contents = await file.read()
        file_size_bytes = len(contents)

        if file_size_bytes > 100 * 1024 * 1024:  # 100 MB max
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Replay file too large (max 100 MB)",
            )

        # TODO: Calculate file hash and store
        # TODO: Queue for processing
        # TODO: Store in database

        log.info(
            "Replay uploaded",
            filename=file.filename,
            size_bytes=file_size_bytes,
        )

        # For MVP, return success response
        return ReplayUploadResponse(
            replay_id=1,  # TODO: Use actual DB ID
            status="uploaded",
            message="Replay queued for processing",
            estimated_processing_time_seconds=60,
        )

    except Exception as e:
        log.error("Replay upload failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process replay upload",
        )


@router.get("/{replay_id}/status")
async def get_replay_status(
    replay_id: int,
    db: AsyncSession | None = None,
) -> ReplayProcessingStatus:
    """
    Get current processing status of a replay.

    Args:
        replay_id: The replay ID
        db: Database session

    Returns:
        Current processing status
    """
    # TODO: Fetch from database
    return ReplayProcessingStatus(
        replay_id=replay_id,
        status="uploaded",
        progress_percent=0,
        message="Queued for processing",
        match_id=None,
        error=None,
    )


@router.get("/{replay_id}/download")
async def download_replay_result(
    replay_id: int,
    db: AsyncSession | None = None,
):
    """
    Download analysis results for a replay (as JSON).

    Args:
        replay_id: The replay ID
        db: Database session

    Returns:
        JSON with full analysis results
    """
    # TODO: Fetch from database and return analysis
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not yet implemented",
    )
