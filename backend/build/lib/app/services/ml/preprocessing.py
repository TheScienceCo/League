"""Controlling for the things that are not skill.

The whole premise of Skill Gap Analysis is that we do *not* hard-code what makes
a player good — we let a model find which behaviours separate ranks. That only
works if the behaviours are measured on a level field, because otherwise the
model will happily "discover" that Master players have more damage share, when in
fact Master players in this sample picked more marksmen.

`residualize` removes exactly that. For each feature we subtract the mean of the
control group the observation belongs to — champion x role x patch x duration —
so what remains is the part of the observation that its circumstances do not
explain. Group means are shrunk toward broader means in proportion to how little
data a group has (an empirical-Bayes style adjustment), so a champion with four
games does not get a free pass.

This is a saturated-linear-controls approach. It is transparent, it is cheap, and
it does not assume the controls act linearly. It cannot capture interactions the
grouping does not express, which is a real limitation and one we state rather
than hide.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: Control hierarchy, narrowest first. A group's mean is blended with its parent's.
DEFAULT_CONTROL_LEVELS: tuple[tuple[str, ...], ...] = (
    ("team_position", "champion_id", "patch", "duration_bucket"),
    ("team_position", "champion_id", "duration_bucket"),
    ("team_position", "champion_id"),
    ("team_position", "duration_bucket"),
    ("team_position",),
)

#: Shrinkage strength: a group with this many observations is weighted equally
#: against its parent mean. Larger = more conservative.
SHRINKAGE_K = 25.0


@dataclass(slots=True)
class ResidualBaselines:
    """The fitted control means, so new observations can be residualized too."""

    levels: tuple[tuple[str, ...], ...]
    global_means: dict[str, float] = field(default_factory=dict)
    #: level index -> feature -> {group key tuple (as str) -> shrunk mean}
    group_means: dict[int, dict[str, dict[str, float]]] = field(default_factory=dict)

    @staticmethod
    def encode_key(values: Sequence[object]) -> str:
        return "|".join("" if v is None else str(v) for v in values)


def fit_residual_baselines(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    *,
    levels: tuple[tuple[str, ...], ...] = DEFAULT_CONTROL_LEVELS,
    shrinkage_k: float = SHRINKAGE_K,
) -> ResidualBaselines:
    baselines = ResidualBaselines(levels=levels)
    for col in feature_cols:
        series = pd.to_numeric(df[col], errors="coerce")
        baselines.global_means[col] = float(series.mean()) if series.notna().any() else 0.0

    # Walk from the broadest level inward, so each level shrinks toward the one
    # above it rather than toward the global mean directly.
    parent_lookup: dict[str, dict[str, float]] = {
        col: {} for col in feature_cols
    }  # keyed by the *current* level's key
    for level_idx in range(len(levels) - 1, -1, -1):
        level = levels[level_idx]
        baselines.group_means[level_idx] = {}
        for col in feature_cols:
            series = pd.to_numeric(df[col], errors="coerce")
            sub = df.loc[series.notna(), list(level)].copy()
            sub["_v"] = series[series.notna()]
            if sub.empty:
                baselines.group_means[level_idx][col] = {}
                continue
            grouped = sub.groupby(list(level), dropna=False)["_v"].agg(["mean", "count"])
            out: dict[str, float] = {}
            for key, row in grouped.iterrows():
                key_tuple = key if isinstance(key, tuple) else (key,)
                encoded = ResidualBaselines.encode_key(key_tuple)
                parent = _parent_mean(baselines, level_idx, levels, key_tuple, col, parent_lookup)
                n = float(row["count"])
                weight = n / (n + shrinkage_k)
                out[encoded] = float(weight * row["mean"] + (1.0 - weight) * parent)
            baselines.group_means[level_idx][col] = out
    return baselines


def _parent_mean(
    baselines: ResidualBaselines,
    level_idx: int,
    levels: tuple[tuple[str, ...], ...],
    key_tuple: tuple[object, ...],
    col: str,
    _cache: dict[str, dict[str, float]],
) -> float:
    """Mean of the next-broader control group containing this one."""
    if level_idx + 1 >= len(levels):
        return baselines.global_means.get(col, 0.0)
    child_level = levels[level_idx]
    parent_level = levels[level_idx + 1]
    mapping = dict(zip(child_level, key_tuple, strict=True))
    if not all(dim in mapping for dim in parent_level):
        return baselines.global_means.get(col, 0.0)
    parent_key = ResidualBaselines.encode_key([mapping[d] for d in parent_level])
    return (
        baselines.group_means.get(level_idx + 1, {})
        .get(col, {})
        .get(parent_key, baselines.global_means.get(col, 0.0))
    )


def apply_residuals(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    baselines: ResidualBaselines,
    *,
    suffix: str = "_resid",
) -> pd.DataFrame:
    """Subtract the narrowest available control mean from each observation."""
    out = df.copy()
    for col in feature_cols:
        values = pd.to_numeric(out[col], errors="coerce").to_numpy(dtype=float)
        expected = np.full(len(out), baselines.global_means.get(col, 0.0), dtype=float)
        for level_idx, level in enumerate(baselines.levels):
            if not all(dim in out.columns for dim in level):
                continue
            table = baselines.group_means.get(level_idx, {}).get(col, {})
            if not table:
                continue
            keys = [
                ResidualBaselines.encode_key(vals)
                for vals in zip(*[out[dim] for dim in level], strict=True)
            ]
            hits = np.array([table.get(k, np.nan) for k in keys], dtype=float)
            # Narrower levels are applied first and win where they exist.
            mask = ~np.isnan(hits)
            if level_idx == 0:
                expected = np.where(mask, hits, expected)
                filled = mask
            else:
                expected = np.where(~filled & mask, hits, expected)
                filled = filled | mask
        out[col + suffix] = values - expected
    return out


def residualize(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    *,
    levels: tuple[tuple[str, ...], ...] = DEFAULT_CONTROL_LEVELS,
    shrinkage_k: float = SHRINKAGE_K,
    suffix: str = "_resid",
) -> tuple[pd.DataFrame, ResidualBaselines]:
    baselines = fit_residual_baselines(df, feature_cols, levels=levels, shrinkage_k=shrinkage_k)
    return apply_residuals(df, feature_cols, baselines, suffix=suffix), baselines


def standardize(
    df: pd.DataFrame, cols: Sequence[str]
) -> tuple[pd.DataFrame, dict[str, tuple[float, float]]]:
    """Z-score columns, returning the (mean, std) used so it can be reapplied."""
    out = df.copy()
    scales: dict[str, tuple[float, float]] = {}
    for col in cols:
        series = pd.to_numeric(out[col], errors="coerce")
        mean = float(series.mean()) if series.notna().any() else 0.0
        std = float(series.std(ddof=0)) or 1.0
        scales[col] = (mean, std)
        out[col] = (series - mean) / std
    return out, scales
