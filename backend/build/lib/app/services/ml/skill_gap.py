"""Skill Gap Analysis.

The question
------------
"Which measurable behaviours most separate this player from the tier above them,
after controlling for what they play and when they played it?"

Note what is *not* happening here: nobody writes down that CS/min matters more
than vision score. A model is trained to predict a player's rank band from
residualized behavioural features, and the features it leans on are the answer.
If the data says vision matters more than farming at a given rank, that is what
comes out.

Method
------
1. **Residualize.** Every behavioural feature is centred on its champion x role x
   patch x duration control group (`ml.preprocessing`), so the model cannot cheat
   by learning champion identity.
2. **Fit.** A gradient-boosted classifier predicts the rank band from the
   residuals, cross-validated with `GroupKFold` on PUUID so no player appears in
   both folds — without that, the model memorises players rather than behaviours
   and every score is inflated.
3. **Attribute.** Permutation importance on a held-out, player-disjoint split
   gives each behaviour's multivariate weight. A univariate Spearman correlation
   against rank is reported next to it, because a feature can rank highly for
   either reason and the difference matters when reading the result.
4. **Compare.** For a specific player, each behaviour's gap to the target tier is
   expressed in pooled standard deviations, signed so positive always means "the
   target tier does this better". Ranking by `importance x gap` puts a behaviour
   at the top only when it both separates ranks *and* is one the player is
   actually behind on.

What this is not
----------------
Observational and correlational. A behaviour separating ranks does not establish
that adopting it raises rank; players who do it differ from players who do not in
ways this data cannot see. Every number surfaced from here is labelled an
estimate, and the report carries its own caveats to the API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from app.core.constants import TIER_GROUP_ORDER
from app.core.errors import InsufficientDataError
from app.core.logging import get_logger
from app.services.analytics.cohorts import CohortService, load_feature_frame
from app.services.analytics.features import (
    BEHAVIOUR_FEATURES,
    FEATURE_LABELS,
    LOWER_IS_BETTER,
)
from app.services.ml.preprocessing import ResidualBaselines, apply_residuals, residualize
from app.services.ml.registry import (
    ModelArtifact,
    load_model,
    make_classifier,
    next_version,
    save_model,
)

log = get_logger(__name__)

MODEL_NAME = "skill_gap"
#: Minimum labelled rows before a fit is attempted at all.
MIN_TRAINING_ROWS = 200
#: Minimum games for one player before their personal report is trustworthy.
MIN_PLAYER_GAMES = 5
RESID_SUFFIX = "_resid"


@dataclass(slots=True)
class BehaviourGap:
    feature: str
    label: str
    #: Multivariate weight from permutation importance (0-1, normalised).
    importance: float
    #: Univariate Spearman rho between the residualized feature and rank score.
    rank_correlation: float
    player_value: float | None
    player_residual: float | None
    target_residual: float | None
    #: Gap in pooled standard deviations. Positive => the target tier is better.
    gap_z: float
    #: The same gap in the feature's natural units, on the same *controlled*
    #: basis as `gap_z` and with the same orientation. Deriving this from raw
    #: tier averages instead would contradict `gap_z` whenever a player's
    #: champion or role mix differs from their target band's.
    gap_natural: float
    #: The target band's raw, *uncontrolled* average. Useful context, but not
    #: comparable to this player's value unless they play the same mix.
    target_band_average: float | None
    #: importance x max(gap_z, 0) — what the ranking is by.
    impact: float
    higher_is_better: bool
    player_percentile: float | None = None
    cohort_n: int | None = None


@dataclass(slots=True)
class SkillGapReport:
    puuid: str
    player_tier_group: str
    target_tier_group: str
    games_analyzed: int
    behaviours: list[BehaviourGap]
    model: dict[str, Any]
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "puuid": self.puuid,
            "player_tier_group": self.player_tier_group,
            "target_tier_group": self.target_tier_group,
            "games_analyzed": self.games_analyzed,
            "behaviours": [asdict(b) for b in self.behaviours],
            "model": self.model,
            "caveats": self.caveats,
        }


# --- training -----------------------------------------------------------------


def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], ResidualBaselines]:
    features = [f for f in BEHAVIOUR_FEATURES if f in df.columns]
    resid, baselines = residualize(df, features, suffix=RESID_SUFFIX)
    resid_cols = [f + RESID_SUFFIX for f in features]
    # A missing residual means "no information", which is exactly the control
    # group's expectation — i.e. zero after centring. Imputing the mean here is
    # honest; imputing a value would invent behaviour the player never showed.
    resid[resid_cols] = resid[resid_cols].fillna(0.0)
    return resid, resid_cols, baselines


def train_skill_gap_model(
    session: Session,
    *,
    min_rows: int = MIN_TRAINING_ROWS,
    n_splits: int = 4,
) -> ModelArtifact:
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import balanced_accuracy_score, f1_score
    from sklearn.model_selection import GroupKFold, GroupShuffleSplit
    from sklearn.utils.class_weight import compute_sample_weight

    frame = load_feature_frame(session)
    frame = frame[frame["tier_group"].isin(TIER_GROUP_ORDER)].copy()
    if len(frame) < min_rows:
        raise InsufficientDataError(
            f"skill-gap training needs at least {min_rows} ranked rows, found {len(frame)}",
            detail={"rows": len(frame)},
        )
    if frame["tier_group"].nunique() < 2:
        raise InsufficientDataError(
            "skill-gap training needs players from at least two rank bands",
            detail={"bands": sorted(frame["tier_group"].unique().tolist())},
        )

    resid, resid_cols, baselines = _prepare(frame)
    tier_index = {t: i for i, t in enumerate(TIER_GROUP_ORDER)}
    y = resid["tier_group"].map(tier_index).to_numpy()
    X = resid[resid_cols]
    groups = resid["puuid"].to_numpy()

    # --- cross-validated performance, players never split across folds -----
    #
    # Two choices here matter more than the estimator does.
    #
    # Rank bands are heavily imbalanced (most players sit in the middle), so
    # plain accuracy rewards a model for always guessing the modal band. We
    # weight classes to balance and score with balanced accuracy, whose chance
    # level is a fixed 1/n_classes.
    #
    # And the target is *ordinal*: being one band out is not the same kind of
    # error as being four out, which argmax accuracy cannot express. The headline
    # number is therefore the Spearman correlation between the true band and the
    # model's probability-weighted expected band — it measures whether the model
    # orders players correctly, which is the question the product actually asks.
    n_groups = len(np.unique(groups))
    splits = max(2, min(n_splits, n_groups))
    balanced_accuracies: list[float] = []
    macro_f1s: list[float] = []
    spearmans: list[float] = []
    if n_groups >= 2:
        for train_idx, test_idx in GroupKFold(n_splits=splits).split(X, y, groups):
            if len(np.unique(y[train_idx])) < 2:
                continue
            model = make_classifier(n_classes=len(TIER_GROUP_ORDER))
            model.fit(
                X.iloc[train_idx],
                y[train_idx],
                sample_weight=compute_sample_weight("balanced", y[train_idx]),
            )
            pred = model.predict(X.iloc[test_idx])
            balanced_accuracies.append(float(balanced_accuracy_score(y[test_idx], pred)))
            macro_f1s.append(float(f1_score(y[test_idx], pred, average="macro")))
            if len(np.unique(y[test_idx])) > 1:
                rho = stats.spearmanr(
                    y[test_idx], _expected_class(model, X.iloc[test_idx])
                ).statistic
                if not np.isnan(rho):
                    spearmans.append(float(rho))

    # --- final fit + permutation importance on a held-out split ------------
    estimator = make_classifier(n_classes=len(TIER_GROUP_ORDER))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    tr_idx, te_idx = next(splitter.split(X, y, groups))
    estimator.fit(
        X.iloc[tr_idx], y[tr_idx], sample_weight=compute_sample_weight("balanced", y[tr_idx])
    )

    importances: dict[str, float] = {}
    if len(np.unique(y[te_idx])) > 1:
        perm = permutation_importance(
            estimator,
            X.iloc[te_idx],
            y[te_idx],
            n_repeats=5,
            random_state=42,
            scoring="balanced_accuracy",
        )
        raw = np.clip(perm.importances_mean, 0.0, None)
        total = float(raw.sum())
        if total > 0:
            importances = {
                col.removesuffix(RESID_SUFFIX): float(v / total)
                for col, v in zip(resid_cols, raw, strict=True)
            }
    if not importances:
        importances = {col.removesuffix(RESID_SUFFIX): 1.0 / len(resid_cols) for col in resid_cols}

    # Refit on everything for the artifact that will actually be served.
    estimator = make_classifier(n_classes=len(TIER_GROUP_ORDER))
    estimator.fit(X, y, sample_weight=compute_sample_weight("balanced", y))

    # --- univariate rank correlations --------------------------------------
    rank_corr: dict[str, float] = {}
    rank_score = pd.to_numeric(resid["rank_score"], errors="coerce").fillna(0.0)
    for col in resid_cols:
        values = resid[col]
        if values.std(ddof=0) == 0:
            rank_corr[col.removesuffix(RESID_SUFFIX)] = 0.0
            continue
        rho = stats.spearmanr(values, rank_score).statistic
        rank_corr[col.removesuffix(RESID_SUFFIX)] = 0.0 if np.isnan(rho) else float(rho)

    # --- per-tier behavioural profiles (the comparison targets) ------------
    tier_profiles: dict[str, dict[str, float]] = {}
    for tier, sub in resid.groupby("tier_group"):
        tier_profiles[str(tier)] = {
            col.removesuffix(RESID_SUFFIX): float(sub[col].mean()) for col in resid_cols
        }
    resid_sd = {
        col.removesuffix(RESID_SUFFIX): float(resid[col].std(ddof=0) or 1.0) for col in resid_cols
    }
    raw_means = {
        f: float(pd.to_numeric(frame[f], errors="coerce").mean())
        for f in BEHAVIOUR_FEATURES
        if f in frame.columns
    }
    tier_raw_means: dict[str, dict[str, float]] = {}
    for tier, sub in frame.groupby("tier_group"):
        tier_raw_means[str(tier)] = {
            f: float(pd.to_numeric(sub[f], errors="coerce").mean())
            for f in BEHAVIOUR_FEATURES
            if f in sub.columns
        }

    n_classes_present = int(resid["tier_group"].nunique())
    metrics = {
        # Headline: does the model order players by rank correctly?
        "cv_rank_spearman": float(np.mean(spearmans)) if spearmans else None,
        "cv_rank_spearman_std": float(np.std(spearmans)) if spearmans else None,
        "cv_balanced_accuracy": float(np.mean(balanced_accuracies))
        if balanced_accuracies
        else None,
        "cv_balanced_accuracy_std": float(np.std(balanced_accuracies))
        if balanced_accuracies
        else None,
        "cv_macro_f1": float(np.mean(macro_f1s)) if macro_f1s else None,
        # Chance level for balanced accuracy is 1/k regardless of imbalance.
        "chance_balanced_accuracy": 1.0 / max(n_classes_present, 1),
        "majority_class_share": float(pd.Series(y).value_counts(normalize=True).max()),
        "n_rows": len(resid),
        "n_players": int(n_groups),
        "median_games_per_player": float(resid.groupby("puuid").size().median()),
        "n_tier_bands": n_classes_present,
        "cv_folds": splits,
        "rank_correlations": rank_corr,
    }
    log.info(
        "ml.skill_gap.trained", **{k: v for k, v in metrics.items() if k != "rank_correlations"}
    )

    artifact = ModelArtifact(
        name=MODEL_NAME,
        version=next_version(),
        kind="classifier",
        estimator=estimator,
        metrics=metrics,
        params={"features": [c.removesuffix(RESID_SUFFIX) for c in resid_cols]},
        feature_importances=importances,
        feature_names=[c.removesuffix(RESID_SUFFIX) for c in resid_cols],
        n_samples=len(resid),
        payload={
            "baselines": baselines,
            "tier_profiles": tier_profiles,
            "tier_raw_means": tier_raw_means,
            "resid_sd": resid_sd,
            "raw_means": raw_means,
            "feature_cols": [c.removesuffix(RESID_SUFFIX) for c in resid_cols],
            "rank_correlations": rank_corr,
        },
    )
    save_model(session, artifact)
    return artifact


def _expected_class(model: Any, X: pd.DataFrame) -> np.ndarray:
    """Probability-weighted expected class index.

    For an ordinal target this is a far better readout than argmax: a model that
    puts most of its mass on the two bands either side of the truth is doing well,
    and argmax throws that away.
    """
    proba = model.predict_proba(X)
    classes = np.asarray(getattr(model, "classes_", np.arange(proba.shape[1])), dtype=float)
    return proba @ classes


# --- inference ----------------------------------------------------------------


def next_tier_group(tier_group: str) -> str:
    """The band a player is realistically working toward."""
    if tier_group not in TIER_GROUP_ORDER:
        return TIER_GROUP_ORDER[0]
    idx = TIER_GROUP_ORDER.index(tier_group)
    return TIER_GROUP_ORDER[min(idx + 1, len(TIER_GROUP_ORDER) - 1)]


def analyze_player(
    session: Session,
    puuid: str,
    *,
    target_tier_group: str | None = None,
    top_n: int = 5,
) -> SkillGapReport:
    loaded = load_model(session, MODEL_NAME)
    if loaded is None:
        raise InsufficientDataError(
            "the skill-gap model has not been trained yet; run `riftlab train-skill-gap`"
        )
    record, bundle = loaded
    payload = bundle["payload"]
    baselines: ResidualBaselines = payload["baselines"]
    feature_cols: list[str] = payload["feature_cols"]
    tier_profiles: dict[str, dict[str, float]] = payload["tier_profiles"]
    tier_raw_means: dict[str, dict[str, float]] = payload["tier_raw_means"]
    resid_sd: dict[str, float] = payload["resid_sd"]
    rank_corr: dict[str, float] = payload.get("rank_correlations", {})
    importances: dict[str, float] = dict(record.feature_importances or {})

    frame = load_feature_frame(session)
    mine = frame[frame["puuid"] == puuid].copy()
    if mine.empty:
        raise InsufficientDataError(
            "no analysed games for this player yet — ingest some matches first",
            detail={"puuid": puuid},
        )

    player_tier = _dominant_tier(mine)
    target = target_tier_group or next_tier_group(player_tier)
    if target not in tier_profiles:
        available = [t for t in TIER_GROUP_ORDER if t in tier_profiles]
        if not available:
            raise InsufficientDataError("the trained model has no tier profiles")
        target = available[-1]

    resid = apply_residuals(mine, feature_cols, baselines, suffix=RESID_SUFFIX)
    target_profile = tier_profiles[target]
    cohorts = CohortService(session)
    # Percentiles come from comparing each game against its own cohort, never a
    # multi-game mean against a single-game distribution (see cohorts.py).
    game_rows = list(mine.itertuples(index=False))

    gaps: list[BehaviourGap] = []
    for feature in feature_cols:
        col = feature + RESID_SUFFIX
        if col not in resid:
            continue
        player_resid_series = pd.to_numeric(resid[col], errors="coerce").dropna()
        if player_resid_series.empty:
            continue
        player_resid = float(player_resid_series.mean())
        target_resid = float(target_profile.get(feature, 0.0))
        sd = float(resid_sd.get(feature, 1.0)) or 1.0
        higher_better = feature not in LOWER_IS_BETTER

        # Residuals are mean-centred versions of the feature, so their difference
        # is already in natural units; orienting it the same way as `gap_z` keeps
        # the two numbers telling the same story.
        raw_gap = target_resid - player_resid
        gap_natural = raw_gap if higher_better else -raw_gap
        gap_z = gap_natural / sd

        player_raw = pd.to_numeric(mine[feature], errors="coerce").dropna()
        player_value = float(player_raw.mean()) if not player_raw.empty else None
        target_raw = tier_raw_means.get(target, {}).get(feature)

        importance = float(importances.get(feature, 0.0))
        standing = cohorts.summarize_player(game_rows, feature)

        gaps.append(
            BehaviourGap(
                feature=feature,
                label=FEATURE_LABELS.get(feature, feature),
                importance=importance,
                rank_correlation=float(rank_corr.get(feature, 0.0)),
                player_value=player_value,
                player_residual=player_resid,
                target_residual=target_resid,
                gap_z=float(gap_z),
                gap_natural=float(gap_natural),
                target_band_average=float(target_raw) if target_raw is not None else None,
                impact=importance * max(gap_z, 0.0),
                higher_is_better=higher_better,
                player_percentile=standing.percentile if standing else None,
                cohort_n=standing.cohort_n if standing else None,
            )
        )

    gaps.sort(key=lambda g: g.impact, reverse=True)
    games = int(mine["match_id"].nunique())

    caveats = [
        "Associational, not causal: these behaviours separate rank bands in this "
        "dataset; that does not establish that changing them raises rank.",
        "Behaviours are compared after controlling for champion, role, patch and "
        "game duration, but unobserved factors (team quality, matchup, tilt) remain.",
        f"Based on {games} analysed game(s) for this player against "
        f"{record.n_samples} labelled rows overall.",
    ]
    if games < MIN_PLAYER_GAMES:
        caveats.insert(
            0,
            f"Only {games} game(s) analysed — treat this as indicative until at "
            f"least {MIN_PLAYER_GAMES} are ingested.",
        )

    return SkillGapReport(
        puuid=puuid,
        player_tier_group=player_tier,
        target_tier_group=target,
        games_analyzed=games,
        behaviours=gaps[:top_n],
        model={
            "name": record.name,
            "version": record.version,
            "trained_at": record.trained_at.isoformat() if record.trained_at else None,
            "n_samples": record.n_samples,
            "metrics": {
                k: v for k, v in (record.metrics or {}).items() if k != "rank_correlations"
            },
        },
        caveats=caveats,
    )


def rank_separation_summary(session: Session, *, top_n: int = 15) -> dict[str, Any]:
    """Which behaviours separate ranks overall, independent of any one player."""
    loaded = load_model(session, MODEL_NAME)
    if loaded is None:
        raise InsufficientDataError("the skill-gap model has not been trained yet")
    record, bundle = loaded
    rank_corr = bundle["payload"].get("rank_correlations", {})
    importances = record.feature_importances or {}
    ranked = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return {
        "model": {
            "name": record.name,
            "version": record.version,
            "trained_at": record.trained_at.isoformat() if record.trained_at else None,
            "n_samples": record.n_samples,
            "metrics": {
                k: v for k, v in (record.metrics or {}).items() if k != "rank_correlations"
            },
        },
        "behaviours": [
            {
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature),
                "importance": float(value),
                "rank_correlation": float(rank_corr.get(feature, 0.0)),
                "higher_is_better": feature not in LOWER_IS_BETTER,
                "tier_means": {
                    tier: profile.get(feature)
                    for tier, profile in bundle["payload"]["tier_raw_means"].items()
                },
            }
            for feature, value in ranked
        ],
    }


def _dominant_tier(frame: pd.DataFrame) -> str:
    ranked = frame[frame["tier_group"].isin(TIER_GROUP_ORDER)]
    if ranked.empty:
        return "UNRANKED"
    return str(ranked["tier_group"].mode().iloc[0])
