"""ML methodology: residualization and the Skill Gap pipeline.

The interesting assertions here are not "the model scores X" but "the method
removes the confound it claims to remove" and "the model recovers structure we
planted". Those are the claims the product actually rests on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.services.ml.preprocessing import (
    apply_residuals,
    fit_residual_baselines,
    residualize,
    standardize,
)


@pytest.fixture
def confounded_frame() -> pd.DataFrame:
    """Champion 3 inflates the metric by a lot; skill moves it by a little.

    Without controls, champion identity dominates the correlation. That is
    exactly the failure mode residualization exists to prevent.
    """
    rng = np.random.default_rng(0)
    n = 900
    frame = pd.DataFrame(
        {
            "team_position": rng.choice(["MIDDLE", "BOTTOM"], n),
            "champion_id": rng.choice([1, 2, 3], n),
            "patch": "14.19",
            "duration_bucket": rng.choice(["SHORT", "MEDIUM"], n),
        }
    )
    frame["skill"] = rng.normal(0, 1, n)
    frame["damage_share"] = (
        10.0 + 5.0 * (frame["champion_id"] == 3) + 2.0 * frame["skill"] + rng.normal(0, 0.5, n)
    )
    return frame


def test_residualization_removes_the_confound(confounded_frame: pd.DataFrame) -> None:
    is_champ3 = (confounded_frame["champion_id"] == 3).astype(float)
    raw = abs(np.corrcoef(confounded_frame["damage_share"], is_champ3)[0, 1])

    out, _ = residualize(confounded_frame, ["damage_share"])
    residual = abs(np.corrcoef(out["damage_share_resid"], is_champ3)[0, 1])

    assert raw > 0.6, "the fixture should be strongly confounded to begin with"
    assert residual < 0.1, "champion effect should be removed"


def test_residualization_preserves_the_real_signal(confounded_frame: pd.DataFrame) -> None:
    raw = abs(np.corrcoef(confounded_frame["damage_share"], confounded_frame["skill"])[0, 1])
    out, _ = residualize(confounded_frame, ["damage_share"])
    residual = abs(np.corrcoef(out["damage_share_resid"], confounded_frame["skill"])[0, 1])
    assert residual > raw, "removing the confound should sharpen the skill signal"
    assert residual > 0.9


def test_baselines_are_reusable_on_new_rows(confounded_frame: pd.DataFrame) -> None:
    """Fitted controls must apply to unseen rows, or inference is inconsistent."""
    train = confounded_frame.iloc[:700]
    holdout = confounded_frame.iloc[700:].copy()
    baselines = fit_residual_baselines(train, ["damage_share"])

    applied = apply_residuals(holdout, ["damage_share"], baselines)
    is_champ3 = (holdout["champion_id"] == 3).astype(float)
    assert abs(np.corrcoef(applied["damage_share_resid"], is_champ3)[0, 1]) < 0.15


def test_shrinkage_protects_tiny_groups() -> None:
    """A group with one observation must not be trusted to define its own mean."""
    frame = pd.DataFrame(
        {
            "team_position": ["MIDDLE"] * 51,
            "champion_id": [1] * 50 + [99],  # champion 99 appears once
            "patch": ["14.19"] * 51,
            "duration_bucket": ["MEDIUM"] * 51,
            "value": [10.0] * 50 + [1000.0],
        }
    )
    out, _ = residualize(frame, ["value"])
    outlier = out.loc[out["champion_id"] == 99, "value_resid"].iloc[0]
    # With no shrinkage the residual would collapse to ~0; shrinkage keeps most
    # of the deviation visible.
    assert outlier > 500


def test_unknown_group_falls_back_to_the_global_mean() -> None:
    frame = pd.DataFrame(
        {
            "team_position": ["MIDDLE"] * 40,
            "champion_id": [1] * 40,
            "patch": ["14.19"] * 40,
            "duration_bucket": ["MEDIUM"] * 40,
            "value": np.linspace(5.0, 9.0, 40),
        }
    )
    baselines = fit_residual_baselines(frame, ["value"])
    unseen = pd.DataFrame(
        {
            "team_position": ["JUNGLE"],
            "champion_id": [4242],
            "patch": ["99.9"],
            "duration_bucket": ["LONG"],
            "value": [7.0],
        }
    )
    out = apply_residuals(unseen, ["value"], baselines)
    assert out["value_resid"].iloc[0] == pytest.approx(7.0 - frame["value"].mean(), abs=0.2)


def test_standardize_reports_reusable_scales() -> None:
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
    out, scales = standardize(frame, ["a"])
    assert out["a"].mean() == pytest.approx(0.0, abs=1e-9)
    assert out["a"].std(ddof=0) == pytest.approx(1.0)
    mean, std = scales["a"]
    assert mean == pytest.approx(2.5)
    assert std == pytest.approx(np.std([1, 2, 3, 4]))


def test_expected_class_beats_argmax_for_an_ordinal_target() -> None:
    """The headline metric must reward getting the *order* right.

    A model that is confidently one band out should score better than one that is
    wildly wrong, and argmax accuracy cannot express that difference.
    """
    from app.services.ml.skill_gap import _expected_class

    class Stub:
        classes_ = np.array([0, 1, 2, 3, 4])

        def __init__(self, proba: np.ndarray) -> None:
            self._proba = proba

        def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
            return self._proba

    truth = np.array([0, 1, 2, 3, 4])
    # Off by one, consistently.
    near = np.zeros((5, 5))
    for i, t in enumerate(truth):
        near[i, min(t + 1, 4)] = 1.0
    # Reversed.
    far = np.zeros((5, 5))
    for i, t in enumerate(truth):
        far[i, 4 - t] = 1.0

    frame = pd.DataFrame({"x": range(5)})
    near_rho = stats.spearmanr(truth, _expected_class(Stub(near), frame)).statistic
    far_rho = stats.spearmanr(truth, _expected_class(Stub(far), frame)).statistic
    assert near_rho > 0.9
    assert far_rho < -0.9
