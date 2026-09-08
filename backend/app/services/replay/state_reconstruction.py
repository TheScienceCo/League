"""Game state reconstruction from event stream."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class PlayerGameState:
    """Complete game state for a player at a point in time."""

    timestamp_ms: int
    player_id: int

    # Age and progression
    age: int = 1  # 1=dark, 2=feudal, 3=castle, 4=imperial

    # Resources
    resources: dict[str, int] = field(
        default_factory=lambda: {
            "food": 0,
            "wood": 0,
            "gold": 0,
            "stone": 0,
        }
    )

    # Population
    population: int = 0
    villagers: int = 0
    military_count: int = 0
    housing: int = 5  # Starting housing

    # Structures
    tc_count: int = 1  # Starting TC
    production_building_count: int = 0
    unit_count: int = 0
    building_count: int = 1  # Starting TC counts

    # Military composition (unit -> count)
    unit_composition: dict[str, int] = field(default_factory=dict)

    # Estimated values
    army_value: float = 0.0
    economy_value: float = 0.0
    score: int = 0

    # Researched technologies
    technologies: list[str] = field(default_factory=list)

    # Map position (where units are/have been)
    map_position: dict[str, int] = field(default_factory=dict)

    # Tracking of recent events
    recent_engagements: list[int] = field(default_factory=list)
    recent_losses: list[dict[str, Any]] = field(default_factory=list)

    # Confidence metric (how reliable is this reconstruction)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "timestamp_ms": self.timestamp_ms,
            "player_id": self.player_id,
            "age": self.age,
            "resources": self.resources,
            "population": self.population,
            "villagers": self.villagers,
            "military_count": self.military_count,
            "housing": self.housing,
            "tc_count": self.tc_count,
            "production_building_count": self.production_building_count,
            "unit_count": self.unit_count,
            "building_count": self.building_count,
            "unit_composition": self.unit_composition,
            "army_value": self.army_value,
            "economy_value": self.economy_value,
            "score": self.score,
            "technologies": self.technologies,
            "map_position": self.map_position,
            "recent_engagements": self.recent_engagements,
            "recent_losses": self.recent_losses,
            "confidence": self.confidence,
        }


class StateReconstructor:
    """
    Reconstructs game state from event stream.

    Maintains cumulative state and applies events to track:
    - Resource collection and spending
    - Building and unit creation/destruction
    - Population and housing
    - Technologies and age progression
    - Army composition and value
    """

    # Unit type -> gold cost (approximate for value calculation)
    UNIT_COSTS = {
        "villager": 25,
        "archer": 25,
        "spearman": 25,
        "cavalry": 60,
        "knight": 80,
        "scout": 80,
        "tower": 100,
        "siege": 120,
    }

    # Unit type -> gold value when destroyed
    UNIT_VALUES = {
        "villager": 25,
        "archer": 40,
        "spearman": 35,
        "cavalry": 100,
        "knight": 120,
        "scout": 120,
        "tower": 150,
        "siege": 180,
    }

    def __init__(self, snapshot_interval_ms: int = 10000):
        """
        Initialize state reconstructor.

        Args:
            snapshot_interval_ms: Interval at which to capture state snapshots
        """
        self.snapshot_interval_ms = snapshot_interval_ms

    def reconstruct(
        self, events: list[dict[str, Any]], players: list[dict[str, Any]]
    ) -> dict[int, list[PlayerGameState]]:
        """
        Reconstruct game states from events.

        Args:
            events: Sorted list of events from replay
            players: List of player info (id, name, civ, etc.)

        Returns:
            Dict mapping player_id -> list of GameState snapshots
        """
        # Initialize state for each player
        states_by_player: dict[int, list[PlayerGameState]] = {}
        current_state: dict[int, PlayerGameState] = {}

        for player_info in players:
            player_id = player_info["player_id"]
            current_state[player_id] = PlayerGameState(timestamp_ms=0, player_id=player_id)
            states_by_player[player_id] = []

        if not events:
            # Return initial states
            for player_id, state in current_state.items():
                states_by_player[player_id].append(state)
            return states_by_player

        # Process events
        next_snapshot_time = self.snapshot_interval_ms
        last_snapshot_time = 0

        for event in events:
            timestamp_ms = event.get("timestamp_ms", 0)
            player_id = event.get("player_id")

            # Capture snapshots at regular intervals
            while next_snapshot_time <= timestamp_ms:
                self._capture_snapshots(
                    current_state, next_snapshot_time, states_by_player
                )
                next_snapshot_time += self.snapshot_interval_ms

            # Apply event to state
            if player_id and player_id in current_state:
                self._apply_event(current_state[player_id], event)
            elif player_id is None:
                # Global event (apply to all players)
                for state in current_state.values():
                    self._apply_event(state, event)

            last_snapshot_time = timestamp_ms

        # Capture final snapshot
        if last_snapshot_time > next_snapshot_time - self.snapshot_interval_ms:
            self._capture_snapshots(current_state, last_snapshot_time, states_by_player)

        return states_by_player

    def _capture_snapshots(
        self,
        current_state: dict[int, PlayerGameState],
        timestamp_ms: int,
        states_by_player: dict[int, list[PlayerGameState]],
    ) -> None:
        """Capture and store state snapshots at a point in time."""
        for player_id, state in current_state.items():
            snapshot = PlayerGameState(
                timestamp_ms=timestamp_ms,
                player_id=player_id,
                age=state.age,
                resources=state.resources.copy(),
                population=state.population,
                villagers=state.villagers,
                military_count=state.military_count,
                housing=state.housing,
                tc_count=state.tc_count,
                production_building_count=state.production_building_count,
                unit_count=state.unit_count,
                building_count=state.building_count,
                unit_composition=state.unit_composition.copy(),
                army_value=state.army_value,
                economy_value=state.economy_value,
                score=state.score,
                technologies=state.technologies.copy(),
                map_position=state.map_position.copy(),
                recent_engagements=state.recent_engagements.copy(),
                recent_losses=state.recent_losses.copy(),
                confidence=state.confidence,
            )
            states_by_player[player_id].append(snapshot)

    def _apply_event(self, state: PlayerGameState, event: dict[str, Any]) -> None:
        """Apply a single event to a player's state."""
        event_type = event.get("type")
        data = event.get("data", {})

        if event_type == "age_up":
            state.age = data.get("age", state.age)
            log.debug("Age up", player_id=state.player_id, age=state.age)

        elif event_type == "unit_created":
            unit_type = data.get("unit_type", "unknown")

            # Update counts
            state.unit_count += 1

            if unit_type == "villager":
                state.villagers += 1
                state.population += 1
            else:
                state.military_count += 1
                state.population += 1

            # Update composition
            state.unit_composition[unit_type] = state.unit_composition.get(
                unit_type, 0
            ) + 1

            # Update army value
            unit_value = self.UNIT_VALUES.get(unit_type, 50)
            state.army_value += unit_value

        elif event_type == "unit_died":
            unit_type = data.get("unit_type", "unknown")
            attacker_id = data.get("attacker_id")

            # Update counts
            if state.unit_count > 0:
                state.unit_count -= 1
            if state.population > 0:
                state.population -= 1

            if unit_type == "villager":
                if state.villagers > 0:
                    state.villagers -= 1
            else:
                if state.military_count > 0:
                    state.military_count -= 1

            # Update composition
            if state.unit_composition.get(unit_type, 0) > 0:
                state.unit_composition[unit_type] -= 1

            # Update army value
            unit_value = self.UNIT_VALUES.get(unit_type, 50)
            if state.army_value > 0:
                state.army_value = max(0, state.army_value - unit_value)

            # Track loss
            state.recent_losses.append(
                {
                    "unit_type": unit_type,
                    "timestamp_ms": event.get("timestamp_ms"),
                    "killed_by": attacker_id,
                }
            )

        elif event_type == "build_completed":
            building_type = data.get("building_type", "unknown")

            state.building_count += 1
            state.population += 1

            if building_type == "tc":
                state.tc_count += 1
            else:
                state.production_building_count += 1

            # Rough housing value
            housing_map = {
                "house": 5,
                "mill": 0,
                "range": 0,
                "stable": 0,
                "tower": 0,
            }
            state.housing += housing_map.get(building_type, 0)

            # Update economy value
            building_value = 150 if building_type == "tc" else 100
            state.economy_value += building_value

        elif event_type == "build_destroyed":
            building_type = data.get("building_type", "unknown")

            if state.building_count > 0:
                state.building_count -= 1
            if state.population > 0:
                state.population -= 1

            if building_type == "tc" and state.tc_count > 0:
                state.tc_count -= 1
            elif state.production_building_count > 0:
                state.production_building_count -= 1

            # Deduct from economy value
            building_value = 150 if building_type == "tc" else 100
            if state.economy_value > 0:
                state.economy_value = max(0, state.economy_value - building_value)

        elif event_type == "resource_tribute":
            # Update resources (positive for receiver, handled by other player)
            amount = data.get("amount", 0)
            resource_type = data.get("resource_type", "food")
            state.resources[resource_type] = max(0, state.resources[resource_type] - amount)

        elif event_type == "technology_researched":
            tech_name = data.get("technology_name", "unknown")
            if tech_name not in state.technologies:
                state.technologies.append(tech_name)

        # Update score (simplified)
        self._update_score(state)

    def _update_score(self, state: PlayerGameState) -> None:
        """Recalculate score based on current state."""
        # Simplified scoring: resources + buildings + units
        resource_score = sum(state.resources.values()) // 50
        building_score = state.building_count * 10
        unit_score = state.unit_count * 5
        tech_score = len(state.technologies) * 5

        state.score = int(resource_score + building_score + unit_score + tech_score)
