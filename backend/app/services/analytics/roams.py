"""Roam detection and valuation.

A roam is a laner leaving their lane to do something else. Detecting one from
Match-V5 data means working at the timeline's one-minute resolution: we mark the
minutes in which a laner is far from their lane centre-line and group the
consecutive ones into windows.

Valuing one is the interesting part. The naive version counts the kills that
happened and calls it good; that rewards a mid laner who walked away from three
waves for a single assist. Instead we value a roam as the *excess* resources it
produced over what the player would have gained had they stayed:

    value = (gold gained - gold expected in lane)
          + (xp gained - xp expected in lane) x XP_TO_GOLD
          + objectives x OBJECTIVE_GOLD_VALUE
          - deaths x DEATH_GOLD_COST

The "expected in lane" baselines come from the *same player in the same game* —
their own median per-minute gold and XP over the minutes they spent in lane —
which controls for champion, patch, and how the game was going, all at once.

Limitations, stated plainly: minute-resolution frames mean a sub-30-second
collapse mid-to-bot is invisible, and the gold conversions below are reasonable
constants rather than fitted values. This is an estimate of roam value, and the
API labels it as one.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import LANE_ROLES, Role, Zone
from app.db.models import MatchParticipant, ParticipantFeatures, RoamEvent
from app.services.analytics.context import MatchContext
from app.services.analytics.geometry import classify_zone, distance_to_lane

#: Distance from the lane centre-line beyond which a laner counts as "away".
ROAM_DISTANCE_UNITS = 2600.0
#: Roams before this minute are usually just pathing out of base.
ROAM_MIN_MINUTE = 4
#: Value conversions, in gold-equivalent units.
XP_TO_GOLD = 0.30
OBJECTIVE_GOLD_VALUE = 250.0
DEATH_GOLD_COST = 350.0
#: A roam has to clear this to count as a success, so that a break-even walk to
#: the river is not scored as a win.
SUCCESS_THRESHOLD_GOLD = 75.0

HOME_ZONES: dict[Role, set[Zone]] = {
    Role.TOP: {Zone.TOP_LANE},
    Role.MIDDLE: {Zone.MID_LANE},
    Role.BOTTOM: {Zone.BOT_LANE},
    Role.UTILITY: {Zone.BOT_LANE},
}
BASE_ZONES = {Zone.BLUE_BASE, Zone.RED_BASE}


@dataclass(slots=True)
class Roam:
    participant_id: int
    puuid: str
    role: str
    start_ms: int
    end_ms: int
    target_zone: str
    kills: int
    assists: int
    deaths: int
    objectives: int
    gold_gained: float
    xp_gained: float
    cs_sacrificed: float
    xp_sacrificed: float
    value: float
    success: bool


def _in_lane(x: float | None, y: float | None, role: Role) -> bool | None:
    """`None` when there is no position to judge (dead, missing frame)."""
    if x is None or y is None:
        return None
    zone = classify_zone(x, y)
    if zone in BASE_ZONES:
        return None  # recalling is not roaming
    if zone in HOME_ZONES.get(role, set()):
        return True
    return distance_to_lane(x, y, role) <= ROAM_DISTANCE_UNITS


def detect_roams(ctx: MatchContext) -> list[Roam]:
    roams: list[Roam] = []
    if not ctx.has_timeline:
        return roams

    for p in ctx.participants:
        try:
            role = Role(p.team_position)
        except ValueError:
            continue
        if role not in LANE_ROLES:
            continue  # the jungler has no lane to leave

        frames = ctx.frames.get(p.participant_id, [])
        if len(frames) < ROAM_MIN_MINUTE + 2:
            continue

        states: list[tuple[int, bool | None]] = [
            (f.minute, _in_lane(f.position_x, f.position_y, role)) for f in frames
        ]
        baselines = _lane_baselines(frames, states)
        if baselines is None:
            continue
        gold_rate, xp_rate, cs_rate = baselines

        window: list[int] = []
        for minute, state in states:
            if minute < ROAM_MIN_MINUTE:
                continue
            if state is False:
                window.append(minute)
                continue
            if window:
                roam = _build_roam(ctx, p, role, window, gold_rate, xp_rate, cs_rate)
                if roam is not None:
                    roams.append(roam)
                window = []
        if window:
            roam = _build_roam(ctx, p, role, window, gold_rate, xp_rate, cs_rate)
            if roam is not None:
                roams.append(roam)
    return roams


def _lane_baselines(frames, states) -> tuple[float, float, float] | None:  # type: ignore[no-untyped-def]
    """The player's own per-minute gold/XP/CS rate while actually in lane.

    Using the player as their own control removes champion, patch and game-state
    effects that a global baseline would leave in.
    """
    gold_d: list[float] = []
    xp_d: list[float] = []
    cs_d: list[float] = []
    for i in range(1, len(frames)):
        if states[i][1] is not True:
            continue
        prev, cur = frames[i - 1], frames[i]
        gold_d.append(float(cur.total_gold - prev.total_gold))
        xp_d.append(float(cur.xp - prev.xp))
        cs_d.append(
            float(
                (cur.minions_killed + cur.jungle_minions_killed)
                - (prev.minions_killed + prev.jungle_minions_killed)
            )
        )
    if len(gold_d) < 3:
        return None
    return statistics.median(gold_d), statistics.median(xp_d), statistics.median(cs_d)


def _build_roam(
    ctx: MatchContext,
    participant: MatchParticipant,
    role: Role,
    minutes: list[int],
    gold_rate: float,
    xp_rate: float,
    cs_rate: float,
) -> Roam | None:
    pid = participant.participant_id
    start_min, end_min = minutes[0], minutes[-1]
    start_ms = (start_min - 1) * 60_000
    end_ms = end_min * 60_000
    span_minutes = max(1, end_min - start_min + 1)

    start_frame = ctx.frame_at_minute(pid, start_min - 1) or ctx.frame_at_minute(pid, start_min)
    end_frame = ctx.frame_at_minute(pid, end_min)
    if start_frame is None or end_frame is None:
        return None

    gold_gained = float(end_frame.total_gold - start_frame.total_gold)
    xp_gained = float(end_frame.xp - start_frame.xp)
    cs_gained = float(
        (end_frame.minions_killed + end_frame.jungle_minions_killed)
        - (start_frame.minions_killed + start_frame.jungle_minions_killed)
    )

    kills = sum(1 for e in ctx.kills_by(pid) if start_ms <= e.timestamp_ms <= end_ms)
    deaths = sum(1 for e in ctx.deaths_of(pid) if start_ms <= e.timestamp_ms <= end_ms)
    assists = sum(
        1
        for e in ctx.events_by_type.get("CHAMPION_KILL", [])
        if start_ms <= e.timestamp_ms <= end_ms and pid in ctx.assists_of(e)
    )
    objectives = sum(
        1
        for e in ctx.events_by_type.get("ELITE_MONSTER_KILL", [])
        if start_ms <= e.timestamp_ms <= end_ms and ctx.took_part(e, pid)
    )

    expected_gold = gold_rate * span_minutes
    expected_xp = xp_rate * span_minutes
    expected_cs = cs_rate * span_minutes

    value = (
        (gold_gained - expected_gold)
        + XP_TO_GOLD * (xp_gained - expected_xp)
        + OBJECTIVE_GOLD_VALUE * objectives
        - DEATH_GOLD_COST * deaths
    )

    zones = [
        classify_zone(f.position_x, f.position_y)
        for m in minutes
        if (f := ctx.frame_at_minute(pid, m)) is not None
        and f.position_x is not None
        and f.position_y is not None
    ]
    target_zone = max(set(zones), key=zones.count).value if zones else Zone.MID_LANE.value

    return Roam(
        participant_id=pid,
        puuid=participant.puuid,
        role=role.value,
        start_ms=start_ms,
        end_ms=end_ms,
        target_zone=target_zone,
        kills=kills,
        assists=assists,
        deaths=deaths,
        objectives=objectives,
        gold_gained=gold_gained,
        xp_gained=xp_gained,
        cs_sacrificed=max(0.0, expected_cs - cs_gained),
        xp_sacrificed=max(0.0, expected_xp - xp_gained),
        value=value,
        success=value > SUCCESS_THRESHOLD_GOLD,
    )


def analyze_roams(session: Session, match_id: str) -> int:
    """Detect, value and store roams, then fold the summary into features."""
    ctx = MatchContext.load(session, match_id)
    if ctx is None:
        return 0
    roams = detect_roams(ctx)

    session.execute(delete(RoamEvent).where(RoamEvent.match_id == match_id))
    for r in roams:
        session.add(
            RoamEvent(
                match_id=match_id,
                puuid=r.puuid,
                participant_id=r.participant_id,
                role=r.role,
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                target_zone=r.target_zone,
                kills=r.kills,
                assists=r.assists,
                deaths=r.deaths,
                objectives=r.objectives,
                gold_gained=r.gold_gained,
                xp_gained=r.xp_gained,
                cs_sacrificed=r.cs_sacrificed,
                xp_sacrificed=r.xp_sacrificed,
                value=r.value,
                success=r.success,
            )
        )

    grouped: dict[str, list[Roam]] = {}
    for r in roams:
        grouped.setdefault(r.puuid, []).append(r)

    features = {
        f.puuid: f
        for f in session.scalars(
            select(ParticipantFeatures).where(ParticipantFeatures.match_id == match_id)
        )
    }
    for puuid, target in features.items():
        mine = grouped.get(puuid, [])
        target.roam_count = len(mine)
        target.roam_value_total = sum(r.value for r in mine)
        target.roam_value_per_roam = (target.roam_value_total / len(mine)) if mine else None
        target.roam_cs_sacrificed = sum(r.cs_sacrificed for r in mine)
        target.roam_success_rate = sum(1 for r in mine if r.success) / len(mine) if mine else None

    session.flush()
    return len(roams)
