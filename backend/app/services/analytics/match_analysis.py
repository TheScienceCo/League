"""Assembles the full analysis of a single match from one player's perspective.

Everything the match page shows comes from here: the economy timeline against the
lane opponent, the significant events with their map context, each death with the
risk the model assigned to where the player was standing, objective setups, roams,
the derived metrics with their cohort placement, and the generated observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import QUEUE_NAMES, Role
from app.core.errors import NotFoundError
from app.db.models import ObjectiveSetup, ParticipantFeatures, RoamEvent
from app.services.analytics.coaching import generate_observations
from app.services.analytics.cohorts import CohortService
from app.services.analytics.context import MatchContext
from app.services.analytics.features import BEHAVIOUR_FEATURES, FEATURE_LABELS
from app.services.analytics.geometry import classify_zone

#: Event types worth putting on the match timeline.
SIGNIFICANT_EVENTS = ("CHAMPION_KILL", "ELITE_MONSTER_KILL", "BUILDING_KILL")


def _zone_of(x: float | None, y: float | None) -> str | None:
    """Named region for a position, or `None` when it is not fully known."""
    if x is None or y is None:
        return None
    return classify_zone(x, y).value


@dataclass(slots=True)
class TimelinePoint:
    minute: int
    gold: int
    xp: int
    cs: int
    level: int
    gold_diff: int | None
    xp_diff: int | None
    cs_diff: int | None
    team_gold_diff: float | None


def _participant_payload(p, ctx: MatchContext) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "participant_id": p.participant_id,
        "puuid": p.puuid,
        "riot_id": (f"{p.riot_id_game_name}#{p.riot_id_tagline}" if p.riot_id_game_name else None),
        "team_id": p.team_id,
        "win": p.win,
        "champion_id": p.champion_id,
        "champion_name": p.champion_name,
        "team_position": p.team_position,
        "champ_level": p.champ_level,
        "kills": p.kills,
        "deaths": p.deaths,
        "assists": p.assists,
        "cs": p.cs,
        "gold_earned": p.gold_earned,
        "damage_to_champions": p.total_damage_to_champions,
        "damage_taken": p.total_damage_taken,
        "vision_score": p.vision_score,
        "wards_placed": p.wards_placed,
        "wards_killed": p.wards_killed,
        "kill_participation": (
            (p.kills + p.assists) / ctx.team_kills[p.team_id]
            if ctx.team_kills.get(p.team_id)
            else None
        ),
    }


def build_timeline_series(ctx: MatchContext, pid: int) -> list[dict[str, Any]]:
    """Per-minute economy for the player, differenced against their lane opponent."""
    opp_pid = ctx.lane_opponents.get(pid)
    me = ctx.by_pid[pid]
    points: list[dict[str, Any]] = []
    for frame in ctx.frames.get(pid, []):
        opp = ctx.frame_at_minute(opp_pid, frame.minute) if opp_pid is not None else None
        cs = frame.minions_killed + frame.jungle_minions_killed
        opp_cs = (opp.minions_killed + opp.jungle_minions_killed) if opp else None
        points.append(
            {
                "minute": frame.minute,
                "gold": frame.total_gold,
                "xp": frame.xp,
                "cs": cs,
                "level": frame.level,
                "gold_diff": (frame.total_gold - opp.total_gold) if opp else None,
                "xp_diff": (frame.xp - opp.xp) if opp else None,
                "cs_diff": (cs - opp_cs) if opp_cs is not None else None,
                "team_gold_diff": ctx.team_gold_diff_at(me.team_id, frame.minute),
                "position": (
                    {"x": frame.position_x, "y": frame.position_y}
                    if frame.position_x is not None
                    else None
                ),
            }
        )
    return points


def build_events(ctx: MatchContext, pid: int) -> list[dict[str, Any]]:
    me = ctx.by_pid[pid]
    out: list[dict[str, Any]] = []
    for event in ctx.events:
        if event.type not in SIGNIFICANT_EVENTS:
            continue
        involved = event.killer_id == pid or event.victim_id == pid or pid in ctx.assists_of(event)
        actor = ctx.by_pid.get(event.killer_id) if event.killer_id else None
        victim = ctx.by_pid.get(event.victim_id) if event.victim_id else None
        out.append(
            {
                "type": event.type,
                "timestamp_ms": event.timestamp_ms,
                "minute": event.minute,
                "involved_player": involved,
                "killer": actor.champion_name if actor else None,
                "killer_team_id": actor.team_id if actor else event.team_id,
                "victim": victim.champion_name if victim else None,
                "assists": len(ctx.assists_of(event)),
                "monster_type": event.monster_type,
                "monster_sub_type": event.monster_sub_type,
                "building_type": event.building_type,
                "lane_type": event.lane_type,
                "position": (
                    {"x": event.position_x, "y": event.position_y}
                    if event.position_x is not None
                    else None
                ),
                "zone": _zone_of(event.position_x, event.position_y),
                "player_team": me.team_id,
            }
        )
    return out


def build_deaths(
    ctx: MatchContext, pid: int, risk_lookup: dict[int, float]
) -> list[dict[str, Any]]:
    """Each death with the map context it happened in.

    `risk_at_position` is the modelled probability of dying within the horizon,
    evaluated at the *previous* timeline frame — i.e. what the model thought of
    where the player was standing just before it happened. It is a model output,
    not a measurement.
    """
    deaths: list[dict[str, Any]] = []
    for event in ctx.deaths_of(pid):
        frame = ctx.frame_before(pid, event.timestamp_ms)
        killer = ctx.by_pid.get(event.killer_id) if event.killer_id else None
        zone = _zone_of(event.position_x, event.position_y)
        deaths.append(
            {
                "timestamp_ms": event.timestamp_ms,
                "minute": event.minute,
                "position": (
                    {"x": event.position_x, "y": event.position_y}
                    if event.position_x is not None
                    else None
                ),
                "zone": zone,
                "killer": killer.champion_name if killer else None,
                "assist_count": len(ctx.assists_of(event)),
                "solo_death": len(ctx.assists_of(event)) == 0,
                "risk_at_position": risk_lookup.get(frame.timestamp_ms) if frame else None,
                "team_gold_diff": ctx.team_gold_diff_at(ctx.by_pid[pid].team_id, event.minute),
            }
        )
    return deaths


def analyze_match(
    session: Session,
    match_id: str,
    puuid: str,
    *,
    include_risk: bool = True,
) -> dict[str, Any]:
    ctx = MatchContext.load(session, match_id)
    if ctx is None:
        raise NotFoundError(f"match {match_id} has not been ingested")
    me = ctx.by_puuid.get(puuid)
    if me is None:
        raise NotFoundError(f"player {puuid} did not play in match {match_id}")
    pid = me.participant_id

    features = session.scalar(
        select(ParticipantFeatures).where(
            ParticipantFeatures.match_id == match_id, ParticipantFeatures.puuid == puuid
        )
    )

    risk_lookup: dict[int, float] = {}
    if include_risk and ctx.has_timeline:
        risk_lookup = _risk_by_timestamp(session, match_id, puuid)

    feature_values: dict[str, float | None] = {}
    if features is not None:
        for name in BEHAVIOUR_FEATURES:
            value = getattr(features, name, None)
            feature_values[name] = float(value) if value is not None else None

    cohort_service = CohortService(session)
    context = {
        "team_position": me.team_position,
        "champion_id": me.champion_id,
        "tier_group": me.tier_group,
        "patch": ctx.match.patch,
        "duration_bucket": ctx.duration_bucket,
    }
    comparisons = cohort_service.compare_many(feature_values, context)
    observations = generate_observations(cohort_service, feature_values, context)

    setups = list(
        session.scalars(
            select(ObjectiveSetup)
            .where(ObjectiveSetup.match_id == match_id, ObjectiveSetup.puuid == puuid)
            .order_by(ObjectiveSetup.objective_ms)
        )
    )
    roams = list(
        session.scalars(
            select(RoamEvent)
            .where(RoamEvent.match_id == match_id, RoamEvent.puuid == puuid)
            .order_by(RoamEvent.start_ms)
        )
    )

    return {
        "match": {
            "match_id": ctx.match.match_id,
            "platform": ctx.match.platform,
            "queue_id": ctx.match.queue_id,
            "queue_name": QUEUE_NAMES.get(ctx.match.queue_id, "Unknown"),
            "patch": ctx.match.patch,
            "game_start": ctx.match.game_start.isoformat() if ctx.match.game_start else None,
            "duration_seconds": ctx.match.game_duration_seconds,
            "winning_team_id": ctx.match.winning_team_id,
            "has_timeline": ctx.has_timeline,
        },
        "player": _participant_payload(me, ctx),
        "lane_opponent": (
            _participant_payload(ctx.by_pid[ctx.lane_opponents[pid]], ctx)
            if pid in ctx.lane_opponents
            else None
        ),
        "teams": [
            {
                "team_id": team.team_id,
                "win": team.win,
                "champion_kills": team.champion_kills,
                "dragon_kills": team.dragon_kills,
                "baron_kills": team.baron_kills,
                "herald_kills": team.herald_kills,
                "tower_kills": team.tower_kills,
                "inhibitor_kills": team.inhibitor_kills,
                "first_blood": team.first_blood,
                "first_tower": team.first_tower,
            }
            for team in ctx.teams.values()
        ],
        "participants": [_participant_payload(p, ctx) for p in ctx.participants],
        "timeline": build_timeline_series(ctx, pid),
        "events": build_events(ctx, pid),
        "deaths": build_deaths(ctx, pid, risk_lookup),
        "objective_setups": [
            {
                "objective_type": s.objective_type,
                "objective_sub_type": s.objective_sub_type,
                "minute": s.objective_ms // 60000,
                "timestamp_ms": s.objective_ms,
                "team_secured": s.team_secured,
                "player_credited": s.player_credited,
                "distance_30s": s.distance_30s,
                "distance_60s": s.distance_60s,
                "distance_90s": s.distance_90s,
                "arrival_lead_seconds": s.arrival_lead_seconds,
                "wards_placed_window": s.wards_placed_window,
                "wards_cleared_window": s.wards_cleared_window,
                "deaths_window": s.deaths_window,
                "setup_score": s.setup_score,
            }
            for s in setups
        ],
        "roams": [
            {
                "start_minute": r.start_ms // 60000,
                "end_minute": r.end_ms // 60000,
                "target_zone": r.target_zone,
                "kills": r.kills,
                "assists": r.assists,
                "deaths": r.deaths,
                "objectives": r.objectives,
                "gold_gained": r.gold_gained,
                "xp_gained": r.xp_gained,
                "cs_sacrificed": r.cs_sacrificed,
                "value": r.value,
                "expected_value": r.expected_value,
                "efficiency": (
                    r.value - r.expected_value if r.expected_value is not None else None
                ),
                "success": r.success,
            }
            for r in roams
        ],
        "advanced_metrics": [
            {
                "metric": name,
                "label": FEATURE_LABELS.get(name, name),
                "value": feature_values.get(name),
            }
            for name in BEHAVIOUR_FEATURES
            if feature_values.get(name) is not None
        ],
        "cohort_comparisons": [
            {
                "metric": c.metric,
                "label": FEATURE_LABELS.get(c.metric, c.metric),
                "value": c.value,
                "percentile": c.percentile,
                "z_score": c.z_score,
                "cohort_mean": c.mean,
                "cohort_median": c.p50,
                "cohort_p25": c.p25,
                "cohort_p75": c.p75,
                "cohort_n": c.cohort_n,
                "cohort_dimensions": c.cohort_dimensions,
                "is_fallback_cohort": c.is_fallback,
            }
            for c in comparisons
        ],
        "observations": [o.to_dict() for o in observations],
    }


def _risk_by_timestamp(session: Session, match_id: str, puuid: str) -> dict[int, float]:
    """Score this match's frames with the saved risk model, if one exists."""
    from app.services.analytics.refresh import load_risk_model
    from app.services.analytics.spatial import build_exposure_frame

    model = load_risk_model(session)
    if model is None:
        return {}
    frame = build_exposure_frame(
        session, horizon_seconds=model.horizon_seconds, match_ids=[match_id]
    )
    if frame.empty:
        return {}
    mine = frame[frame["puuid"] == puuid]
    if mine.empty:
        return {}
    risks = model.predict(mine)
    return {int(ts): float(r) for ts, r in zip(mine["timestamp_ms"], risks, strict=True)}


def role_or_default(value: str | None) -> str:
    try:
        return Role(value or "").value
    except ValueError:
        return Role.UNKNOWN.value
