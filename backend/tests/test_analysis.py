"""Metric derivation and the availability contract."""

from __future__ import annotations

import pytest

from app.services.analysis import insights
from app.services.analysis.metrics import analyze
from app.services.parser import get_parser
from app.services.parser.types import Availability


@pytest.fixture(scope="module")
def with_queue(request):
    from tests.conftest import REC_WITH_QUEUE
    return analyze(get_parser().parse(REC_WITH_QUEUE.read_bytes()))


@pytest.fixture(scope="module")
def without_queue(request):
    from tests.conftest import REC_WITHOUT_QUEUE
    return analyze(get_parser().parse(REC_WITHOUT_QUEUE.read_bytes()))


class TestAvailabilityContract:
    """The core invariant: never report a number we did not measure."""

    def test_unavailable_metrics_have_no_value(self, with_queue, without_queue):
        for analysis in (with_queue, without_queue):
            for player in analysis.players:
                for metric in player.metrics.values():
                    if metric.availability is Availability.UNAVAILABLE:
                        assert metric.value is None, (
                            f"{metric.key} is unavailable but carries {metric.value!r}"
                        )

    def test_combat_metrics_always_unavailable(self, with_queue):
        """Replays record commands, not outcomes. There are no kill counts."""
        for player in with_queue.players:
            for key in ("resources_killed", "resources_lost", "engagement_efficiency"):
                assert player.metrics[key].availability is Availability.UNAVAILABLE
                assert player.metrics[key].value is None

    def test_production_unavailable_when_queue_undecodable(self, without_queue):
        for player in without_queue.players:
            for key in ("villagers_queued", "max_production_gap"):
                assert player.metrics[key].availability is Availability.UNAVAILABLE

    def test_production_observed_when_queue_decodable(self, with_queue):
        for player in with_queue.players:
            assert with_queue.players[0].metrics["villagers_queued"].availability is (
                Availability.OBSERVED
            )
            assert player.metrics["villagers_queued"].value > 0

    def test_every_metric_declares_availability(self, with_queue):
        for player in with_queue.players:
            for metric in player.metrics.values():
                assert isinstance(metric.availability, Availability)
                assert metric.label


class TestAgeTimings:
    def test_reached_ages_are_observed(self, with_queue):
        for player in with_queue.players:
            assert player.metrics["feudal_time"].availability is Availability.OBSERVED
            assert player.metrics["feudal_time"].value > 0

    def test_unreached_age_is_unavailable(self, with_queue):
        # Neither player reached Imperial in this game.
        for player in with_queue.players:
            assert player.metrics["imperial_time"].availability is Availability.UNAVAILABLE

    def test_deltas_are_symmetric(self, with_queue):
        """In a 1v1, one player's lead is exactly the other's deficit."""
        a, b = with_queue.players
        for age in ("feudal", "castle"):
            assert a.metrics[f"{age}_delta"].value == -b.metrics[f"{age}_delta"].value

    def test_faster_player_has_negative_delta(self, with_queue):
        a, b = with_queue.players
        faster = a if a.age_timings_ms["feudal"] < b.age_timings_ms["feudal"] else b
        assert faster.metrics["feudal_delta"].value < 0


class TestResourceCurve:
    def test_curve_is_populated_and_ordered(self, with_queue):
        for player in with_queue.players:
            stamps = [p["timestamp_ms"] for p in player.resource_curve]
            assert stamps and stamps == sorted(stamps)

    def test_float_metrics_marked_inferred(self, with_queue):
        """Sync-packet fields are reverse-engineered, so never claim `observed`."""
        for player in with_queue.players:
            for key in ("float_mean", "float_peak", "time_floating"):
                assert player.metrics[key].availability is Availability.INFERRED

    def test_peak_is_at_least_mean(self, with_queue):
        for player in with_queue.players:
            assert player.metrics["float_peak"].value >= player.metrics["float_mean"].value

    def test_float_by_age_only_covers_ages_reached(self, with_queue):
        for player in with_queue.players:
            assert set(player.float_by_age) <= {"dark", "feudal", "castle", "imperial"}
            assert "imperial" not in player.float_by_age


class TestOpening:
    def test_opening_is_classified_or_explicitly_unknown(self, with_queue, without_queue):
        allowed = {"archers", "scouts", "militia line", "tower rush", "fast castle", "unclassified"}
        for analysis in (with_queue, without_queue):
            for player in analysis.players:
                assert player.opening in allowed


class TestInsights:
    def test_insights_are_generated(self, with_queue):
        for player in with_queue.players:
            lines = insights.for_player(with_queue, player)
            assert lines
            assert all(line.strip() for line in lines)

    def test_insights_cite_numbers(self, with_queue):
        """No generic advice: every line should reference a measured value."""
        for player in with_queue.players:
            for line in insights.for_player(with_queue, player):
                assert any(ch.isdigit() for ch in line), f"no number in: {line}"

    def test_unavailable_production_is_stated_not_hidden(self, without_queue):
        joined = " ".join(
            line
            for p in without_queue.players
            for line in insights.for_player(without_queue, p)
        )
        assert "unavailable" in joined.lower()


def test_analysis_is_deterministic():
    from tests.conftest import REC_WITH_QUEUE

    raw = REC_WITH_QUEUE.read_bytes()
    parser = get_parser()
    a, b = analyze(parser.parse(raw)), analyze(parser.parse(raw))
    for pa, pb in zip(a.players, b.players, strict=True):
        assert {k: v.value for k, v in pa.metrics.items()} == {
            k: v.value for k, v in pb.metrics.items()
        }
        assert pa.float_by_age == pb.float_by_age
