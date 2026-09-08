"""Calculate derived analytics metrics from game state and events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.services.replay.state_reconstruction import PlayerGameState

log = get_logger(__name__)


@dataclass
class PlayerMetrics:
    """Complete metrics for a player in a match."""

    player_id: int
    match_id: int

    # Economy metrics
    tc_idle_time_ms: int | None = None
    villager_idle_time_estimated_ms: int | None = None
    resource_float_peak: float | None = None
    resource_float_average: float | None = None
    resources_collected_total: float | None = None
    villager_production_uptime: float | None = None

    # Build order metrics
    age_up_timing_ms: dict[str, int] | None = None
    first_military_building_time_ms: int | None = None
    first_military_unit_time_ms: int | None = None

    # Military metrics
    military_value_killed: float | None = None
    military_value_lost: float | None = None
    military_production_uptime: float | None = None
    engagement_efficiency: float | None = None

    # Scouting metrics
    scouting_coverage_percent: float | None = None
    time_to_enemy_discovery_ms: int | None = None

    # Strategic metrics
    reaction_latency_ms: int | None = None
    tempo_score: float | None = None

    # All metrics flattened for storage
    all_metrics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "player_id": self.player_id,
            "match_id": self.match_id,
            "tc_idle_time_ms": self.tc_idle_time_ms,
            "villager_idle_time_estimated_ms": self.villager_idle_time_estimated_ms,
            "resource_float_peak": self.resource_float_peak,
            "resource_float_average": self.resource_float_average,
            "resources_collected_total": self.resources_collected_total,
            "villager_production_uptime": self.villager_production_uptime,
            "age_up_timing_ms": self.age_up_timing_ms,
            "first_military_building_time_ms": self.first_military_building_time_ms,
            "first_military_unit_time_ms": self.first_military_unit_time_ms,
            "military_value_killed": self.military_value_killed,
            "military_value_lost": self.military_value_lost,
            "military_production_uptime": self.military_production_uptime,
            "engagement_efficiency": self.engagement_efficiency,
            "scouting_coverage_percent": self.scouting_coverage_percent,
            "time_to_enemy_discovery_ms": self.time_to_enemy_discovery_ms,
            "reaction_latency_ms": self.reaction_latency_ms,
            "tempo_score": self.tempo_score,
        }


class MetricsCalculator:
    """Calculate derived metrics from game state and events."""

    def __init__(self):
        """Initialize metrics calculator."""
        pass

    def calculate_all_metrics(
        self,
        player_id: int,
        match_id: int,
        states: list[PlayerGameState],
        events: list[dict[str, Any]],
        all_player_events: list[dict[str, Any]],
    ) -> PlayerMetrics:
        """
        Calculate all metrics for a player.

        Args:
            player_id: Player ID
            match_id: Match ID
            states: List of game state snapshots for this player
            events: Events for this player
            all_player_events: All events in the match (for cross-player analysis)

        Returns:
            PlayerMetrics with all calculated values
        """
        metrics = PlayerMetrics(player_id=player_id, match_id=match_id)

        # Economy metrics
        metrics.tc_idle_time_ms = self._calculate_tc_idle_time(states, events)
        metrics.resource_float_peak, metrics.resource_float_average = (
            self._calculate_resource_float(states)
        )
        metrics.resources_collected_total = self._calculate_resources_collected(states)
        metrics.villager_production_uptime = self._calculate_villager_uptime(
            states, events
        )

        # Build order metrics
        metrics.age_up_timing_ms = self._calculate_age_up_timings(events)
        metrics.first_military_building_time_ms = (
            self._find_first_military_building(events)
        )
        metrics.first_military_unit_time_ms = self._find_first_military_unit(events)

        # Military metrics
        metrics.military_value_killed, metrics.military_value_lost = (
            self._calculate_military_values(all_player_events, player_id)
        )
        metrics.military_production_uptime = (
            self._calculate_military_production_uptime(states, events)
        )
        metrics.engagement_efficiency = self._calculate_engagement_efficiency(
            metrics.military_value_killed, metrics.military_value_lost
        )

        # Scouting metrics
        metrics.scouting_coverage_percent = self._calculate_scouting_coverage(states)

        # Strategic metrics
        metrics.tempo_score = self._calculate_tempo_score(states)

        # Flatten for storage
        metrics.all_metrics = metrics.to_dict()

        return metrics

    def _calculate_tc_idle_time(
        self, states: list[PlayerGameState], events: list[dict[str, Any]]
    ) -> int | None:
        """
        Calculate TC idle time (in milliseconds).

        TC is idle when it exists but is not producing a villager.
        """
        if not states or not events:
            return None

        idle_time_ms = 0
        last_production_time = 0
        tc_created_time = 0

        for event in events:
            if event.get("type") == "build_completed":
                if event.get("data", {}).get("building_type") == "tc":
                    tc_created_time = event.get("timestamp_ms", 0)
            elif event.get("type") == "unit_created":
                if event.get("data", {}).get("unit_type") == "villager":
                    # Production happened
                    if last_production_time > 0:
                        # There was a gap
                        gap = event.get("timestamp_ms", 0) - last_production_time
                        idle_time_ms += gap
                    last_production_time = event.get("timestamp_ms", 0)

        return max(0, idle_time_ms)

    def _calculate_resource_float(
        self, states: list[PlayerGameState]
    ) -> tuple[float | None, float | None]:
        """
        Calculate peak and average unspent resources.

        Resource float = sum of resources at any point in time.
        """
        if not states:
            return None, None

        floats = []
        for state in states:
            total = sum(state.resources.values())
            floats.append(float(total))

        if not floats:
            return None, None

        peak = max(floats)
        average = sum(floats) / len(floats)

        return peak, average

    def _calculate_resources_collected(
        self, states: list[PlayerGameState]
    ) -> float | None:
        """Estimate total resources collected based on spent + floating."""
        if not states:
            return None

        # Last state shows remaining resources
        last_resources = sum(states[-1].resources.values())

        # Approximate by adding back economy value / 50 (rough cost conversion)
        if states[-1].economy_value:
            estimated_spent = states[-1].economy_value * 0.5
        else:
            estimated_spent = 0

        return last_resources + estimated_spent

    def _calculate_villager_uptime(
        self, states: list[PlayerGameState], events: list[dict[str, Any]]
    ) -> float | None:
        """
        Estimate villager production uptime.

        Uptime = time spent producing villagers / total time with spare food.
        """
        if not states or not events:
            return None

        # Count villager production events vs time when it should have been happening
        villager_events = [e for e in events if e.get("data", {}).get("unit_type") == "villager"]

        if not villager_events:
            return 0.0

        # Rough estimate: food was available most of the time
        # So production uptime ≈ (villager count growth) / (expected production)
        first_state = states[0]
        last_state = states[-1]

        if first_state.villagers >= last_state.villagers:
            return 50.0  # No net gain, so idle much of the time

        villagers_produced = last_state.villagers - first_state.villagers
        duration_ms = last_state.timestamp_ms - first_state.timestamp_ms

        # A villager takes ~25s to produce, so expected production is duration / 25000
        if duration_ms == 0:
            return None

        expected_villagers = duration_ms / 25000
        uptime = (villagers_produced / expected_villagers * 100) if expected_villagers > 0 else 0

        return min(100.0, uptime)

    def _calculate_age_up_timings(
        self, events: list[dict[str, Any]]
    ) -> dict[str, int] | None:
        """Find timestamps of age advances."""
        timings = {}

        for event in events:
            if event.get("type") == "age_up":
                age = event.get("data", {}).get("age")
                timestamp_ms = event.get("timestamp_ms", 0)

                age_names = {2: "feudal", 3: "castle", 4: "imperial"}
                if age in age_names:
                    timings[age_names[age]] = timestamp_ms

        return timings if timings else None

    def _find_first_military_building(
        self, events: list[dict[str, Any]]
    ) -> int | None:
        """Find timestamp of first military building."""
        for event in events:
            if event.get("type") == "build_completed":
                building_type = event.get("data", {}).get("building_type")
                if building_type in ["range", "stable", "barracks", "tower"]:
                    return event.get("timestamp_ms")
        return None

    def _find_first_military_unit(self, events: list[dict[str, Any]]) -> int | None:
        """Find timestamp of first military unit."""
        for event in events:
            if event.get("type") == "unit_created":
                unit_type = event.get("data", {}).get("unit_type")
                if unit_type in ["archer", "spearman", "cavalry", "knight", "siege"]:
                    return event.get("timestamp_ms")
        return None

    def _calculate_military_values(
        self, all_events: list[dict[str, Any]], player_id: int
    ) -> tuple[float | None, float | None]:
        """Calculate value killed and lost in military engagements."""
        killed = 0.0
        lost = 0.0

        unit_values = {
            "villager": 25,
            "archer": 40,
            "spearman": 35,
            "cavalry": 100,
            "knight": 120,
            "scout": 120,
            "siege": 180,
        }

        for event in all_events:
            if event.get("type") == "unit_died":
                unit_type = event.get("data", {}).get("unit_type", "unknown")
                value = unit_values.get(unit_type, 50)
                owner_id = event.get("player_id")
                attacker_id = event.get("data", {}).get("attacker_id")

                if owner_id == player_id:
                    lost += value
                elif attacker_id == player_id:
                    killed += value

        return (
            (killed if killed > 0 else None),
            (lost if lost > 0 else None),
        )

    def _calculate_military_production_uptime(
        self, states: list[PlayerGameState], events: list[dict[str, Any]]
    ) -> float | None:
        """Estimate military production building uptime."""
        if not states or not events:
            return None

        # Count time with available production buildings
        first_military_time = None

        for event in events:
            if event.get("type") == "build_completed":
                if event.get("data", {}).get("building_type") in [
                    "range",
                    "stable",
                    "barracks",
                ]:
                    first_military_time = event.get("timestamp_ms", 0)
                    break

        if not first_military_time:
            return 0.0

        # Very rough: assume 50% uptime if they have production buildings
        return 50.0

    def _calculate_engagement_efficiency(
        self, killed: float | None, lost: float | None
    ) -> float | None:
        """Calculate engagement efficiency (kill/loss ratio normalized)."""
        if killed is None or lost is None:
            return None

        if lost == 0:
            return 100.0 if killed > 0 else 50.0

        ratio = killed / lost if lost > 0 else 0
        # Normalize to 0-100 scale (1.0 ratio = 50, 2.0 ratio = 75, etc.)
        efficiency = min(100.0, 50.0 + (ratio - 1.0) * 25.0)

        return max(0.0, efficiency)

    def _calculate_scouting_coverage(
        self, states: list[PlayerGameState]
    ) -> float | None:
        """Estimate scouting coverage percentage."""
        if not states:
            return None

        # Very rough: check if player has scout/militia units early
        for state in states:
            if state.timestamp_ms < 5 * 60 * 1000:  # First 5 minutes
                if state.unit_composition.get("scout", 0) > 0:
                    return 70.0  # Good early scouting

        return 40.0  # Assume mediocre scouting

    def _calculate_tempo_score(
        self, states: list[PlayerGameState]
    ) -> float | None:
        """Calculate tempo score based on army activity and resource spending."""
        if not states:
            return None

        # Check if player is spending resources and moving units
        army_activity = sum(
            s.military_count for s in states[-10:] if s.military_count > 0
        )
        resource_spending = sum(s.resources.values() for s in states[-10:])

        # Score: more spending + more units = higher tempo
        tempo = (army_activity / 10 + resource_spending / 1000) / 2

        return min(100.0, tempo * 50)
