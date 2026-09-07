"""Objective setup analysis.

The question this answers is not "did you get the drake" but "what were you doing
in the ninety seconds before it". For every neutral objective in a game — taken by
either team — we reconstruct, per player: how far from the pit they were at T-90,
T-60 and T-30, when they first arrived, what vision they contributed, and whether
they died going into it.

Positions between Riot's one-minute frames are linearly interpolated, so arrival
timing is an estimate with roughly frame-interval resolution. Everything derived
from it is surfaced as an estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import BARON_PIT, DRAGON_PIT, Role
from app.db.models import ObjectiveSetup, ParticipantFeatures
from app.services.analytics.context import MatchContext

#: Objectives worth analysing. Voidgrubs/horde are grouped with Herald because
#: they occupy the same pit and the same early-game decision.
TRACKED_MONSTERS: frozenset[str] = frozenset({"DRAGON", "BARON_NASHOR", "RIFTHERALD", "HORDE"})

#: Distance under which a player counts as "at" the objective.
ARRIVAL_RADIUS = 2500.0
#: How far back we look for setup behaviour.
SETUP_WINDOW_SECONDS = 90
#: Deaths this close before the objective are counted as "died into it".
DEATH_WINDOW_SECONDS = 45

#: Weights of the four components of `setup_score`. They sum to 1.0 and are a
#: judgement call, not a fitted quantity — documented as such in the API so the
#: number is read as a summary, not a measurement.
SCORE_WEIGHTS = {"arrival": 0.40, "vision": 0.25, "survival": 0.20, "proximity": 0.15}


def pit_for(monster_type: str) -> tuple[float, float]:
    return DRAGON_PIT if monster_type == "DRAGON" else BARON_PIT


@dataclass(slots=True)
class SetupRow:
    puuid: str
    participant_id: int
    role: str
    objective_type: str
    objective_sub_type: str | None
    objective_ms: int
    team_secured: bool
    player_credited: bool
    distance_30s: float | None
    distance_60s: float | None
    distance_90s: float | None
    arrival_lead_seconds: float | None
    wards_placed_window: int
    wards_cleared_window: int
    deaths_window: int
    setup_score: float | None


def _distance(a: tuple[float, float] | None, b: tuple[float, float]) -> float | None:
    if a is None:
        return None
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _arrival_lead(
    ctx: MatchContext, pid: int, objective_ms: int, pit: tuple[float, float]
) -> float | None:
    """How many seconds before the objective the player got into position.

    Walks backwards in 10-second steps and returns the length of the *unbroken*
    stretch spent inside `ARRIVAL_RADIUS`. `None` means they were not there when
    it happened.
    """
    step_ms = 10_000
    lead = 0.0
    for offset in range(0, (SETUP_WINDOW_SECONDS + 30) * 1000 + 1, step_ms):
        ts = objective_ms - offset
        if ts < 0:
            break
        d = _distance(ctx.position_at(pid, ts), pit)
        if d is None or d > ARRIVAL_RADIUS:
            break
        lead = offset / 1000.0
    if lead == 0.0:
        d0 = _distance(ctx.position_at(pid, objective_ms), pit)
        return 0.0 if d0 is not None and d0 <= ARRIVAL_RADIUS else None
    return lead


def _score(
    arrival_lead: float | None,
    wards: int,
    deaths: int,
    distance_30: float | None,
) -> float | None:
    if arrival_lead is None and distance_30 is None:
        return None
    arrival = min((arrival_lead or 0.0) / 60.0, 1.0)
    vision = min(wards / 2.0, 1.0)
    survival = 1.0 if deaths == 0 else 0.0
    proximity = 1.0 - min((distance_30 if distance_30 is not None else 15000.0) / 6000.0, 1.0)
    return (
        SCORE_WEIGHTS["arrival"] * arrival
        + SCORE_WEIGHTS["vision"] * vision
        + SCORE_WEIGHTS["survival"] * survival
        + SCORE_WEIGHTS["proximity"] * proximity
    )


def build_setups(ctx: MatchContext) -> list[SetupRow]:
    rows: list[SetupRow] = []
    elites = [
        e
        for e in ctx.events_by_type.get("ELITE_MONSTER_KILL", [])
        if (e.monster_type or "") in TRACKED_MONSTERS
    ]
    if not elites or not ctx.has_timeline:
        return rows

    wards_placed = ctx.events_by_type.get("WARD_PLACED", [])
    wards_killed = ctx.events_by_type.get("WARD_KILL", [])

    for event in elites:
        monster = event.monster_type or "UNKNOWN"
        pit = pit_for(monster)
        raw = event.raw if isinstance(event.raw, dict) else {}
        killer_team = raw.get("killerTeamId") or event.team_id
        if not killer_team and event.killer_id:
            killer = ctx.by_pid.get(event.killer_id)
            killer_team = killer.team_id if killer else None

        window_start = event.timestamp_ms - SETUP_WINDOW_SECONDS * 1000
        death_start = event.timestamp_ms - DEATH_WINDOW_SECONDS * 1000

        for p in ctx.participants:
            pid = p.participant_id
            d30 = _distance(ctx.position_at(pid, event.timestamp_ms - 30_000), pit)
            d60 = _distance(ctx.position_at(pid, event.timestamp_ms - 60_000), pit)
            d90 = _distance(ctx.position_at(pid, event.timestamp_ms - 90_000), pit)
            placed = sum(
                1
                for w in wards_placed
                if w.creator_id == pid and window_start <= w.timestamp_ms <= event.timestamp_ms
            )
            cleared = sum(
                1
                for w in wards_killed
                if w.killer_id == pid and window_start <= w.timestamp_ms <= event.timestamp_ms
            )
            deaths = sum(
                1 for d in ctx.deaths_of(pid) if death_start <= d.timestamp_ms <= event.timestamp_ms
            )
            lead = _arrival_lead(ctx, pid, event.timestamp_ms, pit)
            rows.append(
                SetupRow(
                    puuid=p.puuid,
                    participant_id=pid,
                    role=p.team_position,
                    objective_type=monster,
                    objective_sub_type=event.monster_sub_type,
                    objective_ms=event.timestamp_ms,
                    team_secured=killer_team == p.team_id,
                    player_credited=ctx.took_part(event, pid),
                    distance_30s=d30,
                    distance_60s=d60,
                    distance_90s=d90,
                    arrival_lead_seconds=lead,
                    wards_placed_window=placed,
                    wards_cleared_window=cleared,
                    deaths_window=deaths,
                    setup_score=_score(lead, placed + cleared, deaths, d30),
                )
            )
    return rows


def analyze_objectives(session: Session, match_id: str) -> int:
    """Compute and store objective setups, then fold the summary into features."""
    ctx = MatchContext.load(session, match_id)
    if ctx is None:
        return 0
    rows = build_setups(ctx)

    session.execute(delete(ObjectiveSetup).where(ObjectiveSetup.match_id == match_id))
    for r in rows:
        session.add(
            ObjectiveSetup(
                match_id=match_id,
                puuid=r.puuid,
                participant_id=r.participant_id,
                role=r.role,
                objective_type=r.objective_type,
                objective_sub_type=r.objective_sub_type,
                objective_ms=r.objective_ms,
                team_secured=r.team_secured,
                player_credited=r.player_credited,
                distance_30s=r.distance_30s,
                distance_60s=r.distance_60s,
                distance_90s=r.distance_90s,
                arrival_lead_seconds=r.arrival_lead_seconds,
                wards_placed_window=r.wards_placed_window,
                wards_cleared_window=r.wards_cleared_window,
                deaths_window=r.deaths_window,
                setup_score=r.setup_score,
            )
        )

    by_puuid: dict[str, list[float]] = {}
    for r in rows:
        if r.setup_score is not None:
            by_puuid.setdefault(r.puuid, []).append(r.setup_score)

    if by_puuid:
        features = {
            f.puuid: f
            for f in session.scalars(
                select(ParticipantFeatures).where(ParticipantFeatures.match_id == match_id)
            )
        }
        for puuid, scores in by_puuid.items():
            target = features.get(puuid)
            if target is not None:
                target.objective_setup_score = sum(scores) / len(scores)

    session.flush()
    return len(rows)


def role_of(row: ObjectiveSetup) -> Role:
    try:
        return Role(row.role)
    except ValueError:
        return Role.UNKNOWN
