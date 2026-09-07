"""Peer cohort statistics.

A raw number ("0.62 vision score per minute") means nothing on its own. It only
becomes information relative to players in comparable circumstances, which means
controlling for the things that move the metric for reasons that are not skill:

* **role** — a support's vision rate and an ADC's are different quantities
* **champion** — damage share is a champion property before it is a player one
* **rank band** — the whole point of the comparison
* **patch** — balance changes move every economy stat
* **game duration** — per-minute rates are not stationary over a game's length

Fully specifying all five gives the cleanest comparison and the emptiest cohorts.
So we materialise a *chain* of progressively broader cohorts and, at query time,
walk it from narrowest to broadest and use the first one with enough
observations. The dimensions actually used are returned alongside the answer, so
a caller always knows what the player was compared against.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import NamedTuple

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CohortStat, ParticipantFeatures
from app.services.analytics.features import BEHAVIOUR_FEATURES

#: Minimum observations before a cohort is considered usable.
MIN_COHORT_N = 20

#: Cohort specificity chain, narrowest first. Each entry is the set of dimensions
#: pinned at that level; the query walks this order and stops at the first cohort
#: that clears `MIN_COHORT_N`.
COHORT_LEVELS: tuple[tuple[str, ...], ...] = (
    ("team_position", "champion_id", "tier_group", "patch", "duration_bucket"),
    ("team_position", "champion_id", "tier_group", "duration_bucket"),
    ("team_position", "champion_id", "tier_group"),
    ("team_position", "tier_group", "patch", "duration_bucket"),
    ("team_position", "tier_group", "duration_bucket"),
    ("team_position", "tier_group"),
    ("team_position",),
    (),
)

DIMENSION_COLUMNS: tuple[str, ...] = (
    "team_position",
    "champion_id",
    "tier_group",
    "patch",
    "duration_bucket",
)


def cohort_key(dimensions: dict[str, object]) -> str:
    """Stable hash of a dimension mapping — the lookup key for `cohort_stats`."""
    payload = json.dumps(dimensions, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:32]


class ResolvedCohort(NamedTuple):
    """A cohort, plus whether the lookup had to widen to find it."""

    stat: CohortStat
    is_fallback: bool


@dataclass(slots=True)
class PlayerMetricSummary:
    """A player's standing on one metric, aggregated the right way round.

    Comparing a player's *multi-game mean* against a distribution of *single
    games* is a units error: the mean of n games has standard error sigma/sqrt(n),
    so it drifts into the tails of the single-game distribution far more often
    than it should, and a merely below-average player reads as first percentile.

    It is also the wrong comparison to make. A player's games differ in champion,
    patch and length, and the cohort for their modal champion is not the right
    yardstick for the game they played on something else.

    So each game is placed against the cohort for *its own* context, and the
    player's standing is the median of those per-game percentiles: "in a typical
    game, this player sits here". `value` remains the plain mean, because that is
    the number a reader wants to see.
    """

    metric: str
    value: float | None
    percentile: float | None
    games_compared: int
    cohort_median: float | None
    cohort_p25: float | None
    cohort_p75: float | None
    cohort_n: int
    cohort_dimensions: dict[str, object]
    z_score: float | None
    is_fallback: bool


def game_context(row: object) -> dict[str, object]:
    """Cohort context for a single game — always internally coherent."""
    return {
        "team_position": getattr(row, "team_position", None),
        "champion_id": getattr(row, "champion_id", None),
        "tier_group": getattr(row, "tier_group", None),
        "patch": getattr(row, "patch", None),
        "duration_bucket": getattr(row, "duration_bucket", None),
    }


@dataclass(slots=True)
class CohortComparison:
    """One metric, one player value, placed against a peer distribution."""

    metric: str
    value: float | None
    cohort_dimensions: dict[str, object]
    cohort_n: int
    mean: float
    std: float
    percentile: float | None
    z_score: float | None
    p25: float
    p50: float
    p75: float
    #: True when we had to fall back below the fully specified cohort.
    is_fallback: bool


def _percentile_from_quantiles(value: float, stat: CohortStat) -> float:
    """Interpolate a percentile from the stored quantiles.

    Preferred over a normal-CDF approximation because most of these metrics are
    visibly skewed (roam value, deaths, damage share), and the quantiles carry
    that shape while a mean/std pair does not.
    """
    knots = [
        (stat.p10, 10.0),
        (stat.p25, 25.0),
        (stat.p50, 50.0),
        (stat.p75, 75.0),
        (stat.p90, 90.0),
    ]
    if value <= knots[0][0]:
        # Extrapolate below p10 using the p10-p25 slope, floored at 1.
        lo_v, lo_p = knots[0]
        hi_v, hi_p = knots[1]
        if hi_v == lo_v:
            return 5.0
        slope = (hi_p - lo_p) / (hi_v - lo_v)
        return float(max(1.0, lo_p + (value - lo_v) * slope))
    if value >= knots[-1][0]:
        lo_v, lo_p = knots[-2]
        hi_v, hi_p = knots[-1]
        if hi_v == lo_v:
            return 95.0
        slope = (hi_p - lo_p) / (hi_v - lo_v)
        return float(min(99.0, hi_p + (value - hi_v) * slope))
    for (v0, p0), (v1, p1) in pairwise(knots):
        if v0 <= value <= v1:
            if v1 == v0:
                return float(p0)
            return float(p0 + (value - v0) * (p1 - p0) / (v1 - v0))
    return 50.0


# --- building -----------------------------------------------------------------


def load_feature_frame(
    session: Session,
    *,
    metrics: Sequence[str] | None = None,
    queue_ids: Sequence[int] | None = None,
) -> pd.DataFrame:
    """All derived features as a DataFrame — the input to cohorts and ML alike."""
    cols = list(metrics) if metrics else list(BEHAVIOUR_FEATURES)
    select_cols = [
        ParticipantFeatures.match_id,
        ParticipantFeatures.puuid,
        ParticipantFeatures.team_position,
        ParticipantFeatures.champion_id,
        ParticipantFeatures.tier_group,
        ParticipantFeatures.rank_score,
        ParticipantFeatures.patch,
        ParticipantFeatures.queue_id,
        ParticipantFeatures.duration_bucket,
        ParticipantFeatures.duration_seconds,
        ParticipantFeatures.win,
        *[getattr(ParticipantFeatures, c) for c in cols],
    ]
    stmt = select(*select_cols)
    if queue_ids:
        stmt = stmt.where(ParticipantFeatures.queue_id.in_(list(queue_ids)))
    rows = session.execute(stmt).all()
    frame = pd.DataFrame(rows, columns=[c.key for c in select_cols])
    for c in cols:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    return frame


def refresh_cohorts(
    session: Session,
    *,
    metrics: Sequence[str] | None = None,
    min_n: int = MIN_COHORT_N,
) -> int:
    """Recompute every cohort at every specificity level. Returns rows written."""
    metric_list = list(metrics) if metrics else list(BEHAVIOUR_FEATURES)
    frame = load_feature_frame(session, metrics=metric_list)
    if frame.empty:
        return 0

    session.execute(delete(CohortStat))
    written = 0
    now = datetime.now(UTC)

    for level_idx, level in enumerate(COHORT_LEVELS):
        specificity = len(COHORT_LEVELS) - level_idx
        groups: list[tuple[dict[str, object], pd.DataFrame]]
        if level:
            grouped = frame.groupby(list(level), dropna=False)
            groups = [
                (dict(zip(level, key if isinstance(key, tuple) else (key,), strict=True)), sub)
                for key, sub in grouped
            ]
        else:
            groups = [({}, frame)]

        for dimensions, sub in groups:
            if len(sub) < min_n:
                continue
            clean_dims = {k: _jsonable(v) for k, v in dimensions.items()}
            key = cohort_key(clean_dims)
            for metric in metric_list:
                series = sub[metric].dropna()
                if len(series) < min_n:
                    continue
                values = series.to_numpy(dtype=float)
                session.add(
                    CohortStat(
                        cohort_key=key,
                        dimensions=clean_dims,
                        specificity=specificity,
                        metric=metric,
                        n=int(values.size),
                        mean=float(np.mean(values)),
                        std=float(np.std(values, ddof=1)) if values.size > 1 else 0.0,
                        p10=float(np.percentile(values, 10)),
                        p25=float(np.percentile(values, 25)),
                        p50=float(np.percentile(values, 50)),
                        p75=float(np.percentile(values, 75)),
                        p90=float(np.percentile(values, 90)),
                        computed_at=now,
                    )
                )
                written += 1
    session.flush()
    return written


def _jsonable(value: object) -> object:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return value


# --- querying -----------------------------------------------------------------


class CohortService:
    """Reads cohort baselines with automatic fallback to broader cohorts."""

    def __init__(self, session: Session, *, min_n: int = MIN_COHORT_N) -> None:
        self.session = session
        self.min_n = min_n
        self._cache: dict[tuple[str, str], CohortStat | None] = {}

    def resolve_detail(self, metric: str, context: dict[str, object]) -> ResolvedCohort | None:
        """Narrowest cohort for `metric` that has enough observations.

        Returns the cohort together with whether the search had to widen, so a
        caller can tell the reader what they are actually being compared against
        rather than presenting a broader comparison as a precise one.
        """
        for level_idx, level in enumerate(COHORT_LEVELS):
            if not all(k in context and context[k] is not None for k in level):
                continue
            dims = {k: _jsonable(context[k]) for k in level}
            key = cohort_key(dims)
            cache_key = (key, metric)
            if cache_key not in self._cache:
                self._cache[cache_key] = self.session.scalar(
                    select(CohortStat).where(
                        CohortStat.cohort_key == key, CohortStat.metric == metric
                    )
                )
            stat = self._cache[cache_key]
            if stat is not None and stat.n >= self.min_n:
                return ResolvedCohort(stat=stat, is_fallback=level_idx > 0)
        return None

    def resolve(self, metric: str, context: dict[str, object]) -> CohortStat | None:
        """The cohort alone, for callers that do not need the fallback flag."""
        resolved = self.resolve_detail(metric, context)
        return resolved.stat if resolved else None

    def compare(
        self, metric: str, value: float | None, context: dict[str, object]
    ) -> CohortComparison | None:
        resolved = self.resolve_detail(metric, context)
        if resolved is None:
            return None
        stat = resolved.stat
        percentile = None
        z = None
        if value is not None:
            percentile = _percentile_from_quantiles(float(value), stat)
            if stat.std > 0:
                z = (float(value) - stat.mean) / stat.std
        return CohortComparison(
            metric=metric,
            value=value,
            cohort_dimensions=dict(stat.dimensions or {}),
            cohort_n=stat.n,
            mean=stat.mean,
            std=stat.std,
            percentile=percentile,
            z_score=z,
            p25=stat.p25,
            p50=stat.p50,
            p75=stat.p75,
            is_fallback=resolved.is_fallback,
        )

    def summarize_player(self, rows: Sequence[object], metric: str) -> PlayerMetricSummary | None:
        """Place a player on one metric by comparing each game to its own cohort."""
        percentiles: list[float] = []
        values: list[float] = []
        zs: list[float] = []
        medians: list[float] = []
        p25s: list[float] = []
        p75s: list[float] = []
        ns: list[int] = []
        dims: dict[str, object] = {}
        fallback = False

        for row in rows:
            value = getattr(row, metric, None)
            if value is None:
                continue
            resolved = self.resolve_detail(metric, game_context(row))
            values.append(float(value))
            if resolved is None:
                continue
            stat = resolved.stat
            percentiles.append(_percentile_from_quantiles(float(value), stat))
            if stat.std > 0:
                zs.append((float(value) - stat.mean) / stat.std)
            medians.append(stat.p50)
            p25s.append(stat.p25)
            p75s.append(stat.p75)
            ns.append(stat.n)
            fallback = fallback or resolved.is_fallback
            # Report the most frequently used cohort shape for display.
            dims = dict(stat.dimensions or {})

        if not values:
            return None
        return PlayerMetricSummary(
            metric=metric,
            value=float(np.mean(values)),
            percentile=float(np.median(percentiles)) if percentiles else None,
            games_compared=len(values),
            cohort_median=float(np.median(medians)) if medians else None,
            cohort_p25=float(np.median(p25s)) if p25s else None,
            cohort_p75=float(np.median(p75s)) if p75s else None,
            cohort_n=int(np.median(ns)) if ns else 0,
            cohort_dimensions=dims,
            z_score=float(np.mean(zs)) if zs else None,
            is_fallback=fallback,
        )

    def summarize_player_many(
        self, rows: Sequence[object], metrics: Sequence[str]
    ) -> list[PlayerMetricSummary]:
        out = []
        for metric in metrics:
            summary = self.summarize_player(rows, metric)
            if summary is not None:
                out.append(summary)
        return out

    def compare_many(
        self, values: dict[str, float | None], context: dict[str, object]
    ) -> list[CohortComparison]:
        out = []
        for metric, value in values.items():
            cmp = self.compare(metric, value, context)
            if cmp is not None:
                out.append(cmp)
        return out


def normalize_rce(session: Session, *, min_n: int = MIN_COHORT_N) -> int:
    """Fill `rce_z` — Resource Conversion Efficiency as a cohort z-score.

    Raw RCE is already normalised for game length and team strength (both sides
    of the ratio are shares), but it is *not* normalised for champion or role: a
    marksman converts gold to damage far better than an enchanter, and that is a
    property of the champion, not the player. The z-score against the narrowest
    available champion/role/rank/patch cohort removes exactly that.
    """
    service = CohortService(session, min_n=min_n)
    rows = list(session.scalars(select(ParticipantFeatures)))
    updated = 0
    for row in rows:
        if row.rce_raw is None:
            row.rce_z = None
            continue
        stat = service.resolve(
            "rce_raw",
            {
                "team_position": row.team_position,
                "champion_id": row.champion_id,
                "tier_group": row.tier_group,
                "patch": row.patch,
                "duration_bucket": row.duration_bucket,
            },
        )
        if stat is None or stat.std <= 0:
            row.rce_z = None
            continue
        row.rce_z = (row.rce_raw - stat.mean) / stat.std
        updated += 1
    session.flush()
    return updated
