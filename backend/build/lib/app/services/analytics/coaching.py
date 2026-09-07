"""Automatically generated coaching observations.

Rules, not a language model. Each observation is a small, auditable statement
tied to a specific derived metric and its peer cohort, so a reader can always ask
"compared to whom?" and get an answer. Observations are scored by how far the
player sits from their cohort and only the strongest few are surfaced — a wall of
twenty mild remarks is worse than three sharp ones.

Deliberate constraints:

* Never assert causation. "Associated with", "in games where", not "because".
* Always name the comparison group and its size.
* Say when the evidence is thin rather than rounding it away.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.services.analytics.cohorts import CohortComparison, CohortService
from app.services.analytics.features import FEATURE_LABELS, LOWER_IS_BETTER

Severity = Literal["strength", "neutral", "watch", "priority"]

#: Percentile thresholds at which a metric is worth remarking on at all.
STRONG_PERCENTILE = 75.0
WEAK_PERCENTILE = 30.0
CRITICAL_PERCENTILE = 15.0

#: Metrics eligible for match-level observations, with the phrasing to use.
OBSERVABLE: dict[str, str] = {
    "cs_per_min": "farming",
    "cs_diff_10": "early lane farm",
    "gold_diff_10": "early lane economy",
    "gold_diff_15": "lane economy at 15",
    "xp_diff_10": "early experience",
    "kill_participation": "kill participation",
    "early_deaths": "early deaths",
    "deaths_per_10min": "death rate",
    "damage_per_gold": "gold-to-damage conversion",
    "rce_raw": "resource conversion",
    "vision_score_per_min": "vision",
    "control_wards_per_min": "control ward usage",
    "objective_participation": "objective participation",
    "objective_setup_score": "objective setup",
    "deaths_before_objectives": "deaths before objectives",
    "dpm_while_behind": "damage output while behind",
    "roam_value_per_roam": "roam value",
    "roam_cs_sacrificed": "CS lost while roaming",
    "high_risk_exposure_share": "time in high-risk areas",
    "deaths_above_expected": "deaths beyond positional expectation",
}


@dataclass(slots=True)
class Observation:
    metric: str
    label: str
    severity: Severity
    headline: str
    detail: str
    value: float | None
    percentile: float | None
    cohort_n: int
    #: Absolute distance from the cohort median, in percentile points. Used only
    #: for ranking which observations to show.
    salience: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ordinal(value: float) -> str:
    """1 -> 1st, 22 -> 22nd. Percentiles read badly as '1th'."""
    n = round(value)
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _format(value: float | None, metric: str) -> str:
    if value is None:
        return "n/a"
    if metric in {
        "kill_participation",
        "objective_participation",
        "dragon_participation",
        "baron_herald_participation",
        "time_ahead_share",
        "roam_success_rate",
        "high_risk_exposure_share",
        "objective_setup_score",
    }:
        return f"{value * 100:.0f}%"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _cohort_phrase(comparison: CohortComparison) -> str:
    dims = comparison.cohort_dimensions or {}
    parts: list[str] = []
    if dims.get("team_position"):
        parts.append(str(dims["team_position"]).title())
    if dims.get("champion_id"):
        parts.append(f"champion {dims['champion_id']}")
    if dims.get("tier_group"):
        parts.append(str(dims["tier_group"]).replace("_", "/").title())
    if dims.get("patch"):
        parts.append(f"patch {dims['patch']}")
    if dims.get("duration_bucket"):
        parts.append(f"{str(dims['duration_bucket']).lower()} games")
    scope = ", ".join(parts) if parts else "all players"
    return f"{scope} (n={comparison.cohort_n})"


def observation_for(comparison: CohortComparison) -> Observation | None:
    metric = comparison.metric
    if metric not in OBSERVABLE or comparison.percentile is None:
        return None

    label = FEATURE_LABELS.get(metric, metric)
    topic = OBSERVABLE[metric]
    higher_better = metric not in LOWER_IS_BETTER
    # Percentile is always "how high is the raw value"; flip it when a low value
    # is the good outcome so that `effective` always means "how good".
    effective = comparison.percentile if higher_better else 100.0 - comparison.percentile
    salience = abs(effective - 50.0)

    value_s = _format(comparison.value, metric)
    median_s = _format(comparison.p50, metric)
    cohort_s = _cohort_phrase(comparison)

    percentile_s = _ordinal(effective)
    if effective >= STRONG_PERCENTILE:
        severity: Severity = "strength"
        headline = f"Strong {topic}"
        detail = (
            f"{label} of {value_s} sits at the {percentile_s} percentile "
            f"against {cohort_s}, where the median is {median_s}."
        )
    elif effective <= CRITICAL_PERCENTILE:
        severity = "priority"
        headline = f"{topic.capitalize()} well below cohort"
        detail = (
            f"{label} of {value_s} is at the {percentile_s} percentile against "
            f"{cohort_s}, where the median is {median_s}."
        )
    elif effective <= WEAK_PERCENTILE:
        severity = "watch"
        headline = f"Below-cohort {topic}"
        detail = (
            f"{label} of {value_s} is at the {percentile_s} percentile against "
            f"{cohort_s}, where the median is {median_s}."
        )
    else:
        severity = "neutral"
        headline = f"{topic.capitalize()} in line with cohort"
        detail = f"{label} of {value_s} is close to the {cohort_s} median of {median_s}."

    return Observation(
        metric=metric,
        label=label,
        severity=severity,
        headline=headline,
        detail=detail,
        value=comparison.value,
        percentile=comparison.percentile,
        cohort_n=comparison.cohort_n,
        salience=salience,
    )


def generate_observations(
    service: CohortService,
    values: dict[str, float | None],
    context: dict[str, object],
    *,
    limit: int = 5,
) -> list[Observation]:
    """Rank observations by distance from the cohort and return the strongest."""
    observations: list[Observation] = []
    for metric in OBSERVABLE:
        if metric not in values:
            continue
        comparison = service.compare(metric, values[metric], context)
        if comparison is None:
            continue
        obs = observation_for(comparison)
        if obs is not None and obs.severity != "neutral":
            observations.append(obs)

    observations.sort(key=lambda o: o.salience, reverse=True)
    # Lead with the problems, but keep at least one strength when one exists —
    # a report that is only criticism is less useful and less accurate.
    priorities = [o for o in observations if o.severity in {"priority", "watch"}][: limit - 1]
    strengths = [o for o in observations if o.severity == "strength"][:2]
    combined = priorities + strengths
    if not combined:
        combined = observations[:limit]
    combined = combined[:limit]

    # Only one observation gets to be *the* biggest gap. Deciding it here rather
    # than in `observation_for` keeps that claim true: an individual observation
    # has no idea how it ranks against the others.
    if priorities:
        top = priorities[0]
        top.headline = f"Biggest gap this game: {OBSERVABLE[top.metric]}"
        top.detail = f"{top.detail} This is the largest single gap in this game."
    return combined
