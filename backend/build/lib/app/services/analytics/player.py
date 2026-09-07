"""Player-level aggregates.

Per-match features answer "how did that game go". These answer "what kind of
player is this" — which needs aggregation across games, and in two cases needs
statistics that only exist at the player level at all:

* **Consistency.** Variance across games is itself a skill signal. A player whose
  cohort-normalised output swings wildly is a different problem from one who is
  reliably mediocre, and a season average hides the difference entirely.
* **Lead conversion.** Whether a lead at 15 becomes a win is a property of a set
  of games, not of one.
"""

from __future__ import annotations

import statistics
from typing import Any

import numpy as np
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.constants import QUEUE_NAMES, TIER_GROUP_ORDER
from app.core.errors import NotFoundError
from app.db.models import (
    LeagueEntry,
    Match,
    MatchParticipant,
    ParticipantFeatures,
    Summoner,
)
from app.services.analytics.cohorts import CohortService, game_context
from app.services.analytics.features import FEATURE_LABELS, LOWER_IS_BETTER

#: Metrics shown on the profile header — chosen to span economy, combat,
#: efficiency, vision and macro rather than five variations of the same thing.
HEADLINE_METRICS: tuple[str, ...] = (
    "cs_per_min",
    "gold_diff_10",
    "kill_participation",
    "rce_raw",
    "vision_score_per_min",
    "objective_participation",
    "deaths_per_10min",
    "damage_per_gold",
)

#: The composite used for consistency. Each is z-scored against the player's own
#: cohort, sign-corrected so higher always means better, then averaged.
COMPOSITE_METRICS: tuple[str, ...] = (
    "cs_per_min",
    "damage_per_min",
    "kill_participation",
    "vision_score_per_min",
    "damage_per_gold",
    "deaths_per_10min",
    "objective_participation",
)


def get_summoner(session: Session, puuid: str) -> Summoner:
    row = session.get(Summoner, puuid)
    if row is None:
        raise NotFoundError(f"player {puuid} has not been ingested")
    return row


def player_ranks(session: Session, puuid: str) -> list[dict[str, Any]]:
    from app.core.constants import tier_group

    return [
        {
            "queue_type": e.queue_type,
            "tier": e.tier,
            "division": e.division,
            "league_points": e.league_points,
            "wins": e.wins,
            "losses": e.losses,
            "rank_score": e.rank_score,
            "tier_group": tier_group(e.tier),
            "hot_streak": e.hot_streak,
        }
        for e in session.scalars(select(LeagueEntry).where(LeagueEntry.puuid == puuid))
    ]


def player_features(session: Session, puuid: str) -> list[ParticipantFeatures]:
    return list(
        session.scalars(
            select(ParticipantFeatures)
            .join(Match, Match.match_id == ParticipantFeatures.match_id)
            .where(ParticipantFeatures.puuid == puuid)
            .order_by(Match.game_start.desc())
        )
    )


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return float(statistics.fmean(clean)) if clean else None


def player_context(features: list[ParticipantFeatures]) -> dict[str, Any]:
    """A representative cohort context for a player.

    The role and champion are taken as a *pair*, not independently: a player who
    mostly bot-lanes but whose single most-played champion is a jungler would
    otherwise get the incoherent context "BOTTOM + that jungler", which describes
    no real cohort. Per-game comparisons use each game's own context
    (`cohorts.game_context`); this is for display and for the rare caller that
    needs one context to stand for the player.
    """
    if not features:
        return {}

    def mode(attr: str) -> Any:
        values = [getattr(f, attr) for f in features if getattr(f, attr) is not None]
        return statistics.mode(values) if values else None

    pairs = [
        (f.team_position, f.champion_id)
        for f in features
        if f.team_position and f.champion_id is not None
    ]
    role, champion = statistics.mode(pairs) if pairs else (mode("team_position"), None)
    return {
        "team_position": role,
        "champion_id": champion,
        "tier_group": mode("tier_group"),
        "patch": mode("patch"),
        "duration_bucket": mode("duration_bucket"),
    }


def headline_metrics(session: Session, features: list[ParticipantFeatures]) -> list[dict[str, Any]]:
    service = CohortService(session)
    out: list[dict[str, Any]] = []
    for metric in HEADLINE_METRICS:
        summary = service.summarize_player(features, metric)
        out.append(
            {
                "metric": metric,
                "label": FEATURE_LABELS.get(metric, metric),
                "value": summary.value if summary else None,
                "percentile": summary.percentile if summary else None,
                "cohort_median": summary.cohort_median if summary else None,
                "cohort_n": summary.cohort_n if summary else None,
                "higher_is_better": metric not in LOWER_IS_BETTER,
            }
        )
    return out


def consistency_stats(
    session: Session, features: list[ParticipantFeatures]
) -> dict[str, Any] | None:
    """Variance of a cohort-normalised composite across the player's games."""
    if len(features) < 3:
        return None
    service = CohortService(session)

    per_game: list[float] = []
    for f in features:
        zs: list[float] = []
        # Each game is z-scored against the cohort for *that game's* champion,
        # role, patch and length — not the player's modal one.
        context = game_context(f)
        for metric in COMPOSITE_METRICS:
            value = getattr(f, metric, None)
            if value is None:
                continue
            comparison = service.compare(metric, float(value), context)
            if comparison is None or comparison.z_score is None:
                continue
            z = comparison.z_score
            # Flip metrics where lower is better so the composite is always
            # "higher = played better".
            zs.append(-z if metric in LOWER_IS_BETTER else z)
        if zs:
            per_game.append(float(statistics.fmean(zs)))

    if len(per_game) < 3:
        return None
    mean = float(statistics.fmean(per_game))
    std = float(statistics.pstdev(per_game))
    within = sum(1 for z in per_game if abs(z - mean) <= std) / len(per_game)
    return {
        "games": len(per_game),
        "performance_mean": mean,
        "performance_std": std,
        "best_game_z": max(per_game),
        "worst_game_z": min(per_game),
        "consistency_rate": within,
    }


def lead_conversion_stats(
    session: Session, features: list[ParticipantFeatures]
) -> dict[str, Any] | None:
    """Lead-to-win conversion, and its mirror image, comeback rate."""
    if not features:
        return None
    with_lead = [f for f in features if f.had_lead_at_15]
    behind = [
        f for f in features if f.team_gold_diff_15 is not None and f.team_gold_diff_15 <= -1000
    ]
    converted = sum(1 for f in with_lead if f.win)
    comebacks = sum(1 for f in behind if f.win)

    cohort_rate = None
    context = player_context(features)
    tier_group = context.get("tier_group")
    if tier_group:
        total, wins = session.execute(
            select(
                func.count(ParticipantFeatures.id),
                func.sum(func.cast(ParticipantFeatures.win, __import__("sqlalchemy").Integer)),
            ).where(
                ParticipantFeatures.had_lead_at_15.is_(True),
                ParticipantFeatures.tier_group == tier_group,
            )
        ).one()
        if total:
            cohort_rate = float((wins or 0) / total)

    return {
        "games_with_lead": len(with_lead),
        "leads_converted": converted,
        "lead_conversion_rate": (converted / len(with_lead)) if with_lead else None,
        "games_behind": len(behind),
        "comebacks": comebacks,
        "comeback_rate": (comebacks / len(behind)) if behind else None,
        "cohort_lead_conversion_rate": cohort_rate,
    }


def role_splits(session: Session, puuid: str) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            MatchParticipant.team_position,
            func.count(MatchParticipant.id),
            func.sum(func.cast(MatchParticipant.win, __import__("sqlalchemy").Integer)),
        )
        .where(MatchParticipant.puuid == puuid)
        .group_by(MatchParticipant.team_position)
        .order_by(func.count(MatchParticipant.id).desc())
    ).all()
    out = []
    for role, games, wins in rows:
        champs = list(
            session.scalars(
                select(MatchParticipant.champion_name)
                .where(
                    MatchParticipant.puuid == puuid,
                    MatchParticipant.team_position == role,
                )
                .group_by(MatchParticipant.champion_name)
                .order_by(func.count(MatchParticipant.id).desc())
                .limit(4)
            )
        )
        out.append(
            {
                "role": role,
                "games": int(games),
                "wins": int(wins or 0),
                "win_rate": float((wins or 0) / games) if games else 0.0,
                "champions": [c for c in champs if c],
            }
        )
    return out


def _at_least_one(column):  # type: ignore[no-untyped-def]
    """`max(column, 1)` as portable SQL.

    Postgres spells this `greatest()` and SQLite spells it `max()`, but SQLite's
    `max` collides with the aggregate. A CASE expression is understood by both
    and keeps the test-suite runnable without a database container.
    """
    return case((column < 1, 1), else_=column)


def champion_splits(session: Session, puuid: str, limit: int = 8) -> list[dict[str, Any]]:
    from sqlalchemy import Integer

    rows = session.execute(
        select(
            MatchParticipant.champion_id,
            MatchParticipant.champion_name,
            func.count(MatchParticipant.id).label("games"),
            func.sum(func.cast(MatchParticipant.win, Integer)),
            func.avg(
                (MatchParticipant.kills + MatchParticipant.assists)
                / _at_least_one(MatchParticipant.deaths)
            ),
            func.avg(
                (MatchParticipant.total_minions_killed + MatchParticipant.neutral_minions_killed)
                * 60.0
                / _at_least_one(Match.game_duration_seconds)
            ),
        )
        .join(Match, Match.match_id == MatchParticipant.match_id)
        .where(MatchParticipant.puuid == puuid)
        .group_by(MatchParticipant.champion_id, MatchParticipant.champion_name)
        .order_by(func.count(MatchParticipant.id).desc())
        .limit(limit)
    ).all()
    return [
        {
            "champion_id": int(cid),
            "champion_name": name,
            "games": int(games),
            "wins": int(wins or 0),
            "win_rate": float((wins or 0) / games) if games else 0.0,
            "kda": float(kda or 0.0),
            "cs_per_min": float(cspm or 0.0),
        }
        for cid, name, games, wins, kda, cspm in rows
    ]


def build_profile(session: Session, puuid: str) -> dict[str, Any]:
    summoner = get_summoner(session, puuid)
    features = player_features(session, puuid)
    ranks = player_ranks(session, puuid)
    context = player_context(features)
    wins = sum(1 for f in features if f.win)

    return {
        "player": {
            "puuid": summoner.puuid,
            "game_name": summoner.game_name,
            "tag_line": summoner.tag_line,
            "platform": summoner.platform,
            "profile_icon_id": summoner.profile_icon_id,
            "summoner_level": summoner.summoner_level,
            "last_ingested_at": summoner.last_ingested_at,
            "ranks": ranks,
        },
        "games_analyzed": len(features),
        "win_rate": (wins / len(features)) if features else None,
        "primary_role": context.get("team_position"),
        "tier_group": context.get("tier_group") or "UNRANKED",
        "headline_metrics": headline_metrics(session, features) if features else [],
        "role_splits": role_splits(session, puuid),
        "champion_splits": champion_splits(session, puuid),
        "consistency": consistency_stats(session, features),
        "lead_conversion": lead_conversion_stats(session, features),
    }


def build_match_list(
    session: Session, puuid: str, *, limit: int = 20, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    total = (
        session.scalar(
            select(func.count(MatchParticipant.id)).where(MatchParticipant.puuid == puuid)
        )
        or 0
    )
    rows = session.execute(
        select(MatchParticipant, Match, ParticipantFeatures)
        .join(Match, Match.match_id == MatchParticipant.match_id)
        .outerjoin(
            ParticipantFeatures,
            (ParticipantFeatures.match_id == MatchParticipant.match_id)
            & (ParticipantFeatures.puuid == MatchParticipant.puuid),
        )
        .where(MatchParticipant.puuid == puuid)
        .order_by(Match.game_start.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for participant, match, feature in rows:
        items.append(
            {
                "match_id": match.match_id,
                "queue_id": match.queue_id,
                "queue_name": QUEUE_NAMES.get(match.queue_id, "Unknown"),
                "patch": match.patch,
                "game_start": match.game_start.isoformat() if match.game_start else None,
                "duration_seconds": match.game_duration_seconds,
                "win": participant.win,
                "champion_id": participant.champion_id,
                "champion_name": participant.champion_name,
                "team_position": participant.team_position,
                "kills": participant.kills,
                "deaths": participant.deaths,
                "assists": participant.assists,
                "cs": participant.cs,
                "cs_per_min": feature.cs_per_min if feature else None,
                "gold_earned": participant.gold_earned,
                "vision_score": participant.vision_score,
                "kill_participation": feature.kill_participation if feature else None,
                "gold_diff_10": feature.gold_diff_10 if feature else None,
                "gold_diff_15": feature.gold_diff_15 if feature else None,
                "rce_raw": feature.rce_raw if feature else None,
                "has_timeline": match.timeline_ingested,
            }
        )
    return items, int(total)


def build_advanced_stats(
    session: Session, puuid: str, *, metrics: list[str] | None = None
) -> dict[str, Any]:
    from app.services.analytics.features import BEHAVIOUR_FEATURES

    features = player_features(session, puuid)
    if not features:
        raise NotFoundError(f"no analysed games for player {puuid}")
    selected = metrics or list(BEHAVIOUR_FEATURES)
    context = player_context(features)
    service = CohortService(session)

    summaries = service.summarize_player_many(features, selected)

    rce_raw = _mean([f.rce_raw for f in features])
    rce_z = _mean([f.rce_z for f in features])
    rce_summary = service.summarize_player(features, "rce_raw")
    interpretation = None
    if rce_raw is not None:
        if rce_raw >= 1.15:
            interpretation = (
                "Converts more of the team's gold into damage than the share of "
                "gold taken would imply."
            )
        elif rce_raw <= 0.85:
            interpretation = (
                "Takes a larger share of team gold than the share of damage "
                "produced — the resources are not coming back out as output."
            )
        else:
            interpretation = "Output share is roughly proportional to resource share."

    return {
        "puuid": puuid,
        "games_analyzed": len(features),
        "tier_group": context.get("tier_group") or "UNRANKED",
        "context": context,
        "metrics": [
            {
                "metric": s.metric,
                "label": FEATURE_LABELS.get(s.metric, s.metric),
                "value": s.value,
                "percentile": s.percentile,
                "z_score": s.z_score,
                "cohort_mean": s.cohort_median,
                "cohort_median": s.cohort_median,
                "cohort_p25": s.cohort_p25,
                "cohort_p75": s.cohort_p75,
                "cohort_n": s.cohort_n,
                "cohort_dimensions": s.cohort_dimensions,
                "is_fallback_cohort": s.is_fallback,
                "games_compared": s.games_compared,
            }
            for s in summaries
        ],
        "resource_conversion": {
            "rce_raw_mean": rce_raw,
            "rce_z_mean": rce_z,
            "damage_share_mean": _mean([f.damage_share for f in features]),
            "gold_share_mean": _mean([f.gold_share for f in features]),
            "percentile": rce_summary.percentile if rce_summary else None,
            "cohort_n": rce_summary.cohort_n if rce_summary else None,
            "interpretation": interpretation,
        },
    }


def cohort_comparison_table(
    session: Session,
    puuid: str,
    *,
    target_tier_group: str | None = None,
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Side-by-side of the player against their own band and a target band."""
    from app.services.analytics.features import BEHAVIOUR_FEATURES

    features = player_features(session, puuid)
    if not features:
        raise NotFoundError(f"no analysed games for player {puuid}")
    selected = metrics or list(BEHAVIOUR_FEATURES)
    context = player_context(features)
    own_band = context.get("tier_group") or "UNRANKED"
    if target_tier_group is None:
        idx = TIER_GROUP_ORDER.index(own_band) if own_band in TIER_GROUP_ORDER else 0
        target_tier_group = TIER_GROUP_ORDER[min(idx + 1, len(TIER_GROUP_ORDER) - 1)]

    service = CohortService(session)
    target_context = {**context, "tier_group": target_tier_group}

    rows: list[dict[str, Any]] = []
    for metric in selected:
        own = service.summarize_player(features, metric)
        value = own.value if own else None
        target = service.resolve(metric, target_context)
        if own is None and target is None:
            continue
        gap = None
        if value is not None and target is not None:
            raw = target.mean - value
            gap = -raw if metric in LOWER_IS_BETTER else raw
        rows.append(
            {
                "metric": metric,
                "label": FEATURE_LABELS.get(metric, metric),
                "player_value": value,
                "player_percentile": own.percentile if own else None,
                "own_cohort_median": own.cohort_median if own else None,
                "own_cohort_n": own.cohort_n if own else None,
                "target_cohort_mean": target.mean if target else None,
                "target_cohort_median": target.p50 if target else None,
                "target_cohort_n": target.n if target else None,
                # Positive => the target band does this better than the player.
                "gap_to_target": gap,
                "gap_z": (
                    (gap / target.std) if gap is not None and target and target.std else None
                ),
                "higher_is_better": metric not in LOWER_IS_BETTER,
            }
        )

    rows.sort(key=lambda r: r["gap_z"] or 0.0, reverse=True)
    return {
        "puuid": puuid,
        "games_analyzed": len(features),
        "player_tier_group": own_band,
        "target_tier_group": target_tier_group,
        "context": context,
        "rows": rows,
    }


def performance_trend(session: Session, puuid: str, *, window: int = 5) -> list[dict[str, Any]]:
    """Rolling mean of a few key metrics over the player's recent games."""
    features = list(reversed(player_features(session, puuid)))
    if not features:
        return []
    tracked = ("cs_per_min", "kill_participation", "vision_score_per_min", "rce_raw")
    out: list[dict[str, Any]] = []
    for idx, f in enumerate(features):
        lo = max(0, idx - window + 1)
        chunk = features[lo : idx + 1]
        point: dict[str, Any] = {
            "index": idx + 1,
            "match_id": f.match_id,
            "win": f.win,
        }
        for metric in tracked:
            values = [
                float(getattr(c, metric)) for c in chunk if getattr(c, metric, None) is not None
            ]
            point[metric] = float(np.mean(values)) if values else None
        out.append(point)
    return out
