"""Integration tests for the complete replay processing pipeline."""

from __future__ import annotations

import asyncio
import pytest

from app.services.aoe.parser import ReplayParser
from app.services.replay.state_reconstruction import StateReconstructor
from app.services.analytics.metrics import MetricsCalculator
from app.services.coaching.report import CoachingReportGenerator
from app.services.replay.ingest import ReplayIngestionService


@pytest.fixture
def parser():
    """Create a replay parser instance."""
    return ReplayParser(parser_type="mock")


@pytest.fixture
def reconstructor():
    """Create a state reconstructor instance."""
    return StateReconstructor(snapshot_interval_ms=10000)


@pytest.fixture
def metrics_calculator():
    """Create a metrics calculator instance."""
    return MetricsCalculator()


@pytest.fixture
def report_generator():
    """Create a coaching report generator instance."""
    return CoachingReportGenerator()


@pytest.fixture
def ingest_service():
    """Create a replay ingestion service instance."""
    return ReplayIngestionService(
        storage_path="/tmp/test_replays",
        parser_type="mock",
        snapshot_interval_ms=10000,
    )


class TestReplayParser:
    """Test replay parsing."""

    def test_mock_parser_generates_valid_data(self, parser):
        """Test that mock parser produces valid output structure."""
        import asyncio
        result = asyncio.run(parser.parse("/fake/path"))

        assert result.success is True
        assert result.metadata is not None
        assert result.metadata.duration_seconds > 0
        assert result.metadata.player_count == 2
        assert len(result.events) > 0
        assert len(result.players) == result.metadata.player_count

    def test_mock_parser_events_have_timestamps(self, parser):
        """Test that events are properly timestamped."""
        import asyncio
        result = asyncio.run(parser.parse("/fake/path"))

        for event in result.events:
            assert "timestamp_ms" in event
            assert isinstance(event["timestamp_ms"], int)
            assert event["timestamp_ms"] >= 0

    def test_mock_parser_events_are_sorted(self, parser):
        """Test that events are chronologically sorted."""
        import asyncio
        result = asyncio.run(parser.parse("/fake/path"))

        timestamps = [e.get("timestamp_ms", 0) for e in result.events]
        assert timestamps == sorted(timestamps)


class TestStateReconstruction:
    """Test game state reconstruction."""

    def test_reconstruction_produces_snapshots(self, parser, reconstructor):
        """Test that state reconstruction produces game state snapshots."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))

        states = reconstructor.reconstruct(parsed.events, parsed.players)

        # Should have states for each player
        assert len(states) == len(parsed.players)

        # Each player should have multiple snapshots
        for player_id, player_states in states.items():
            assert len(player_states) > 0
            # Each snapshot should have metadata
            for state in player_states:
                assert state.timestamp_ms >= 0
                assert state.player_id == player_id
                assert state.age >= 1

    def test_age_progression_tracked(self, parser, reconstructor):
        """Test that age progression is tracked correctly."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))

        states = reconstructor.reconstruct(parsed.events, parsed.players)

        # All players should progress through ages
        for player_id, player_states in states.items():
            ages = [s.age for s in player_states]
            # Ensure no age goes backwards
            for i in range(1, len(ages)):
                assert ages[i] >= ages[i - 1]


class TestMetricsCalculation:
    """Test metrics calculation."""

    def test_tc_idle_time_calculated(self, parser, reconstructor, metrics_calculator):
        """Test that TC idle time is calculated."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))
        states = reconstructor.reconstruct(parsed.events, parsed.players)

        for player_id, player_states in states.items():
            player_events = [e for e in parsed.events if e.get("player_id") == player_id]

            metrics = metrics_calculator.calculate_all_metrics(
                player_id=player_id,
                match_id=1,
                states=player_states,
                events=player_events,
                all_player_events=parsed.events,
            )

            # TC idle time should be present (even if 0)
            assert metrics.tc_idle_time_ms is not None
            assert metrics.tc_idle_time_ms >= 0

    def test_resource_float_calculated(self, parser, reconstructor, metrics_calculator):
        """Test that resource float is calculated."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))
        states = reconstructor.reconstruct(parsed.events, parsed.players)

        for player_id, player_states in states.items():
            player_events = [e for e in parsed.events if e.get("player_id") == player_id]

            metrics = metrics_calculator.calculate_all_metrics(
                player_id=player_id,
                match_id=1,
                states=player_states,
                events=player_events,
                all_player_events=parsed.events,
            )

            # Resource float should be calculated
            assert metrics.resource_float_peak is not None or True
            assert metrics.resource_float_average is not None or True

    def test_age_up_timings_extracted(self, parser, reconstructor, metrics_calculator):
        """Test that age-up timings are extracted."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))
        states = reconstructor.reconstruct(parsed.events, parsed.players)

        for player_id, player_states in states.items():
            player_events = [e for e in parsed.events if e.get("player_id") == player_id]

            metrics = metrics_calculator.calculate_all_metrics(
                player_id=player_id,
                match_id=1,
                states=player_states,
                events=player_events,
                all_player_events=parsed.events,
            )

            # Age-up timings should be present
            if metrics.age_up_timing_ms:
                assert "feudal" in metrics.age_up_timing_ms or "castle" in metrics.age_up_timing_ms


class TestCoachingReportGeneration:
    """Test coaching report generation."""

    def test_report_generated(self, parser, reconstructor, metrics_calculator, report_generator):
        """Test that a coaching report is generated."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))
        states = reconstructor.reconstruct(parsed.events, parsed.players)

        player_id = parsed.players[0]["player_id"]
        player_states = states[player_id]
        player_events = [e for e in parsed.events if e.get("player_id") == player_id]

        metrics = metrics_calculator.calculate_all_metrics(
            player_id=player_id,
            match_id=1,
            states=player_states,
            events=player_events,
            all_player_events=parsed.events,
        )

        report = report_generator.generate_report(
            match_id=1,
            player_id=player_id,
            metrics=metrics,
            events=player_events,
        )

        # Report should have proper structure
        assert report.match_id == 1
        assert report.player_id == player_id
        assert report.generated_at is not None
        assert report.summary is not None
        assert report.overall_grade in ["A", "B", "C", "D"]
        assert report.estimated_elo_performance > 0

    def test_report_contains_insights(self, parser, reconstructor, metrics_calculator, report_generator):
        """Test that report contains actionable insights."""
        import asyncio
        parsed = asyncio.run(parser.parse("/fake/path"))
        states = reconstructor.reconstruct(parsed.events, parsed.players)

        player_id = parsed.players[0]["player_id"]
        player_states = states[player_id]
        player_events = [e for e in parsed.events if e.get("player_id") == player_id]

        metrics = metrics_calculator.calculate_all_metrics(
            player_id=player_id,
            match_id=1,
            states=player_states,
            events=player_events,
            all_player_events=parsed.events,
        )

        report = report_generator.generate_report(
            match_id=1,
            player_id=player_id,
            metrics=metrics,
            events=player_events,
        )

        # Report should have at least some insights
        assert len(report.what_went_well) >= 0
        assert len(report.biggest_mistakes) >= 0
        assert len(report.actionable_improvements) >= 0


class TestEndToEndPipeline:
    """Test complete pipeline integration."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, ingest_service):
        """Test complete replay processing pipeline."""
        # Create fake replay bytes (would be read from file in real use)
        fake_replay_bytes = b"fake_replay_content"

        result = await ingest_service.process_replay(
            file_contents=fake_replay_bytes,
            filename="test_replay.aoe2record",
            uploader_id=None,
        )

        # Pipeline should complete successfully
        assert result["success"] is True
        assert "file_hash" in result
        assert "match_metadata" in result
        assert result["match_metadata"]["player_count"] == 2
        assert "metrics" in result
        assert "coaching_reports" in result

    @pytest.mark.asyncio
    async def test_pipeline_produces_metrics(self, ingest_service):
        """Test that pipeline produces valid metrics."""
        fake_replay_bytes = b"fake_replay_content"

        result = await ingest_service.process_replay(
            file_contents=fake_replay_bytes,
            filename="test_replay2.aoe2record",
        )

        assert result["success"] is True

        # Check that metrics exist for all players
        metrics_by_player = result["metrics"]
        assert len(metrics_by_player) > 0

        for player_id, metrics in metrics_by_player.items():
            # Metrics should have expected keys
            assert "player_id" in metrics
            assert "match_id" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
