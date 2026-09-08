"""Replay file ingestion and processing pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.db.models import Match, MatchPlayer, ReplayFile, ReplayProcessingStatus
from app.services.aoe.parser import ParsedReplay, ReplayParser
from app.services.coaching.report import CoachingReportGenerator
from app.services.analytics.metrics import MetricsCalculator
from app.services.replay.state_reconstruction import StateReconstructor

log = get_logger(__name__)


class ReplayIngestionService:
    """
    Orchestrates the complete replay ingestion and analysis pipeline.

    Pipeline stages:
    1. File validation and storage
    2. Replay parsing (extract events and metadata)
    3. Event stream normalization
    4. Game state reconstruction
    5. Metrics calculation
    6. Coaching report generation
    7. Database storage
    """

    def __init__(
        self,
        storage_path: str = "/data/replays",
        parser_type: str = "mock",
        snapshot_interval_ms: int = 10000,
    ):
        """
        Initialize replay ingestion service.

        Args:
            storage_path: Path to store uploaded replay files
            parser_type: Type of replay parser to use ("mock", "aoc_mgz", etc.)
            snapshot_interval_ms: Interval for game state snapshots
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.parser = ReplayParser(parser_type=parser_type)
        self.reconstructor = StateReconstructor(snapshot_interval_ms=snapshot_interval_ms)
        self.metrics_calculator = MetricsCalculator()
        self.report_generator = CoachingReportGenerator()

        log.info(
            "Replay ingestion service initialized",
            storage_path=str(self.storage_path),
            parser_type=parser_type,
        )

    async def process_replay(
        self, file_contents: bytes, filename: str, uploader_id: int | None = None
    ) -> dict[str, Any]:
        """
        Process a replay file through the complete pipeline.

        Args:
            file_contents: Raw replay file bytes
            filename: Original filename
            uploader_id: User ID of uploader (optional)

        Returns:
            Dict with processing results including match_id, metrics, etc.
        """
        log.info("Starting replay processing", filename=filename, size_bytes=len(file_contents))

        # Stage 1: Store and validate file
        file_hash = hashlib.sha256(file_contents).hexdigest()
        stored_path = self.storage_path / file_hash / filename

        try:
            stored_path.parent.mkdir(parents=True, exist_ok=True)
            stored_path.write_bytes(file_contents)
            log.info("Replay file stored", path=str(stored_path), hash=file_hash)
        except Exception as e:
            log.error("Failed to store replay file", error=str(e))
            return {
                "success": False,
                "error": f"Failed to store file: {str(e)}",
            }

        # Stage 2: Parse replay
        try:
            parsed = await self.parser.parse(str(stored_path))
            if not parsed.success:
                log.error("Replay parsing failed", error=parsed.error)
                return {
                    "success": False,
                    "error": f"Parsing failed: {parsed.error}",
                }

            log.info(
                "Replay parsed successfully",
                map=parsed.metadata.map_name,
                duration=parsed.metadata.duration_seconds,
                players=len(parsed.players),
            )
        except Exception as e:
            log.error("Replay parsing exception", error=str(e))
            return {
                "success": False,
                "error": f"Parsing exception: {str(e)}",
            }

        # Stage 3: Extract match metadata and create players/match records
        try:
            match_data = self._prepare_match_data(parsed)
            log.info(
                "Match data prepared",
                map_type=match_data["map_type"],
                player_count=match_data["player_count"],
            )
        except Exception as e:
            log.error("Failed to prepare match data", error=str(e))
            return {
                "success": False,
                "error": f"Failed to prepare match data: {str(e)}",
            }

        # Stage 4: Reconstruct game state
        try:
            # Filter events by player and reconstruct
            state_snapshots = self.reconstructor.reconstruct(
                events=parsed.events,
                players=parsed.players,
            )
            log.info(
                "Game state reconstructed",
                total_snapshots=sum(len(s) for s in state_snapshots.values()),
            )
        except Exception as e:
            log.error("State reconstruction failed", error=str(e))
            return {
                "success": False,
                "error": f"State reconstruction failed: {str(e)}",
            }

        # Stage 5: Calculate metrics for each player
        try:
            all_metrics = {}
            for player_id, states in state_snapshots.items():
                player_events = [e for e in parsed.events if e.get("player_id") == player_id]

                metrics = self.metrics_calculator.calculate_all_metrics(
                    player_id=player_id,
                    match_id=0,  # Will be assigned from DB
                    states=states,
                    events=player_events,
                    all_player_events=parsed.events,
                )
                all_metrics[player_id] = metrics

            log.info("Metrics calculated", players_analyzed=len(all_metrics))
        except Exception as e:
            log.error("Metrics calculation failed", error=str(e))
            return {
                "success": False,
                "error": f"Metrics calculation failed: {str(e)}",
            }

        # Stage 6: Generate coaching reports
        try:
            coaching_reports = {}
            for player_id, metrics in all_metrics.items():
                report = self.report_generator.generate_report(
                    match_id=0,  # Will be assigned from DB
                    player_id=player_id,
                    metrics=metrics,
                    events=parsed.events,
                    opponent_metrics={
                        oid: om
                        for oid, om in all_metrics.items()
                        if oid != player_id
                    },
                )
                coaching_reports[player_id] = report

            log.info("Coaching reports generated", count=len(coaching_reports))
        except Exception as e:
            log.error("Coaching report generation failed", error=str(e))
            return {
                "success": False,
                "error": f"Coaching report generation failed: {str(e)}",
            }

        # Return complete analysis results
        return {
            "success": True,
            "file_hash": file_hash,
            "filename": filename,
            "match_metadata": match_data,
            "players": parsed.players,
            "events_count": len(parsed.events),
            "state_snapshots": {
                str(pid): len(states)
                for pid, states in state_snapshots.items()
            },
            "metrics": {
                str(pid): m.to_dict()
                for pid, m in all_metrics.items()
            },
            "coaching_reports": {
                str(pid): r.model_dump()
                for pid, r in coaching_reports.items()
            },
        }

    def _prepare_match_data(self, parsed: ParsedReplay) -> dict[str, Any]:
        """
        Prepare match data from parsed replay for database storage.

        Args:
            parsed: ParsedReplay object

        Returns:
            Dict with normalized match data
        """
        metadata = parsed.metadata

        # Determine map type
        map_type = metadata.map_type or "arabia"

        # Prepare match data
        match_data = {
            "map_type": map_type,
            "map_name": metadata.map_name,
            "duration_seconds": metadata.duration_seconds,
            "player_count": metadata.player_count,
            "patch_version": metadata.patch_version or "latest",
            "game_version": metadata.game_version,
        }

        # Validate player count
        if metadata.player_count < 2 or metadata.player_count > 8:
            raise ValueError(
                f"Invalid player count: {metadata.player_count} (must be 2-8)"
            )

        if len(parsed.players) != metadata.player_count:
            log.warning(
                "Player count mismatch",
                reported=metadata.player_count,
                actual=len(parsed.players),
            )

        return match_data


# Singleton instance
_ingest_service: ReplayIngestionService | None = None


def get_replay_ingest_service(
    storage_path: str = "/data/replays",
    parser_type: str = "mock",
    snapshot_interval_ms: int = 10000,
) -> ReplayIngestionService:
    """Get or create the global replay ingestion service."""
    global _ingest_service
    if _ingest_service is None:
        _ingest_service = ReplayIngestionService(
            storage_path=storage_path,
            parser_type=parser_type,
            snapshot_interval_ms=snapshot_interval_ms,
        )
    return _ingest_service
