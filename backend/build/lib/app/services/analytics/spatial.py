"""Spatial analytics: where players stand, and what it costs them.

Two complementary things live here.

1. **An empirical risk surface.** Every timeline frame is an *exposure*: a player
   at a position, at a time, in a game state. We label it with whether that player
   died within the next N seconds, then aggregate over a grid. The result answers
   "how dangerous is this square of the map, for this role, in this phase" purely
   by counting.

2. **A learned risk model.** The grid cannot condition on much without its cells
   emptying out, so we also fit a classifier over the same exposures with richer
   features — proximity to objectives, the team's gold state, recent nearby
   deaths, time in the game. Its output is used for the risk-adjusted positioning
   stats (`expected_deaths`, `deaths_above_expected`).

A deliberate constraint on the feature set
------------------------------------------
The model is only allowed to see information a player could legitimately have had
at that moment: their own position, their own team's state, the game clock, the
objective state, and events that are announced to everyone (kills, objectives).
It is never given live enemy positions, even though the historical timeline
contains them. That is partly principle — the product is post-game coaching, not
a live advantage — and partly a useful property: a model that never needed hidden
information cannot leak it. See `docs/COMPLIANCE.md`.

Everything here estimates association, not causation. A region being followed by
deaths does not establish that entering it caused them; the players who enter it
differ from those who do not in ways no observational model can fully control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    BARON_PIT,
    BLUE_BASE,
    DRAGON_PIT,
    RED_BASE,
    Phase,
    Role,
    Zone,
    phase_for_seconds,
)
from app.db.models import (
    MapRiskCell,
    Match,
    MatchParticipant,
    ParticipantFeatures,
    TimelineEvent,
    TimelineFrame,
)
from app.services.analytics.geometry import (
    cell_center,
    classify_zone,
    grid_cell,
    is_enemy_half,
)

#: Laplace smoothing so a cell with 3 exposures and 1 death does not read as 33%.
SMOOTHING_ALPHA = 2.0

#: Radius within which another player's death counts as "nearby" for the
#: recent-deaths feature. Deaths are announced to everyone, so this is public.
NEARBY_DEATH_RADIUS = 4000.0
NEARBY_DEATH_WINDOW_MS = 60_000


@dataclass(slots=True)
class RiskModelMetrics:
    roc_auc: float
    brier: float
    base_rate: float
    n_samples: int
    n_positive: int


# --- exposure construction ----------------------------------------------------


def build_exposure_frame(
    session: Session,
    *,
    horizon_seconds: int | None = None,
    match_ids: list[str] | None = None,
    limit_matches: int | None = None,
) -> pd.DataFrame:
    """One row per (participant, frame): position, game state, and the label.

    The label is `died_within_horizon` — whether this participant appears as the
    victim of a CHAMPION_KILL in the `horizon_seconds` following the frame.
    """
    horizon = horizon_seconds or settings.risk_horizon_seconds
    horizon_ms = horizon * 1000

    match_stmt = select(Match.match_id, Match.patch, Match.game_duration_seconds).where(
        Match.timeline_ingested.is_(True)
    )
    if match_ids:
        match_stmt = match_stmt.where(Match.match_id.in_(match_ids))
    if limit_matches:
        match_stmt = match_stmt.order_by(Match.game_start.desc()).limit(limit_matches)
    matches = pd.DataFrame(
        session.execute(match_stmt).all(), columns=["match_id", "patch", "duration_s"]
    )
    if matches.empty:
        return pd.DataFrame()

    ids = matches["match_id"].tolist()

    frames = pd.DataFrame(
        session.execute(
            select(
                TimelineFrame.match_id,
                TimelineFrame.participant_id,
                TimelineFrame.timestamp_ms,
                TimelineFrame.minute,
                TimelineFrame.position_x,
                TimelineFrame.position_y,
                TimelineFrame.total_gold,
                TimelineFrame.level,
            ).where(TimelineFrame.match_id.in_(ids))
        ).all(),
        columns=[
            "match_id",
            "participant_id",
            "timestamp_ms",
            "minute",
            "x",
            "y",
            "total_gold",
            "level",
        ],
    )
    if frames.empty:
        return pd.DataFrame()
    frames = frames.dropna(subset=["x", "y"])

    participants = pd.DataFrame(
        session.execute(
            select(
                MatchParticipant.match_id,
                MatchParticipant.participant_id,
                MatchParticipant.puuid,
                MatchParticipant.team_id,
                MatchParticipant.team_position,
                MatchParticipant.champion_id,
                MatchParticipant.tier_group,
            ).where(MatchParticipant.match_id.in_(ids))
        ).all(),
        columns=[
            "match_id",
            "participant_id",
            "puuid",
            "team_id",
            "role",
            "champion_id",
            "tier_group",
        ],
    )

    events = pd.DataFrame(
        session.execute(
            select(
                TimelineEvent.match_id,
                TimelineEvent.timestamp_ms,
                TimelineEvent.type,
                TimelineEvent.victim_id,
                TimelineEvent.position_x,
                TimelineEvent.position_y,
                TimelineEvent.monster_type,
            ).where(
                TimelineEvent.match_id.in_(ids),
                TimelineEvent.type.in_(["CHAMPION_KILL", "ELITE_MONSTER_KILL"]),
            )
        ).all(),
        columns=["match_id", "timestamp_ms", "type", "victim_id", "ex", "ey", "monster_type"],
    )

    df = frames.merge(participants, on=["match_id", "participant_id"], how="inner")
    df = df.merge(matches[["match_id", "patch", "duration_s"]], on="match_id", how="left")

    # --- label: died within the horizon -----------------------------------
    deaths = events[events["type"] == "CHAMPION_KILL"][
        ["match_id", "timestamp_ms", "victim_id", "ex", "ey"]
    ].rename(columns={"timestamp_ms": "death_ms", "victim_id": "participant_id"})
    deaths = deaths.dropna(subset=["participant_id"])
    deaths["participant_id"] = deaths["participant_id"].astype(int)

    df = df.sort_values(["match_id", "participant_id", "timestamp_ms"])
    df["died_within_horizon"] = 0
    if not deaths.empty:
        merged = df.merge(deaths, on=["match_id", "participant_id"], how="left")
        merged["hit"] = (
            (merged["death_ms"] >= merged["timestamp_ms"])
            & (merged["death_ms"] < merged["timestamp_ms"] + horizon_ms)
        ).astype(int)
        label = (
            merged.groupby(["match_id", "participant_id", "timestamp_ms"])["hit"]
            .max()
            .reset_index()
            .rename(columns={"hit": "label"})
        )
        df = df.merge(label, on=["match_id", "participant_id", "timestamp_ms"], how="left")
        df["died_within_horizon"] = df["label"].fillna(0).astype(int)
        df = df.drop(columns=["label"])

    # --- derived state features -------------------------------------------
    df["game_seconds"] = df["timestamp_ms"] / 1000.0
    df["phase"] = df["game_seconds"].map(lambda s: phase_for_seconds(s).value)
    df["zone"] = [classify_zone(x, y) for x, y in zip(df["x"], df["y"], strict=True)]
    df["zone"] = df["zone"].map(lambda z: z.value if isinstance(z, Zone) else str(z))
    df["enemy_half"] = [
        int(is_enemy_half(x, y, t)) for x, y, t in zip(df["x"], df["y"], df["team_id"], strict=True)
    ]
    df["dist_dragon"] = np.hypot(df["x"] - DRAGON_PIT[0], df["y"] - DRAGON_PIT[1])
    df["dist_baron"] = np.hypot(df["x"] - BARON_PIT[0], df["y"] - BARON_PIT[1])
    own_base_x = np.where(df["team_id"] == 100, BLUE_BASE[0], RED_BASE[0])
    own_base_y = np.where(df["team_id"] == 100, BLUE_BASE[1], RED_BASE[1])
    df["dist_own_base"] = np.hypot(df["x"] - own_base_x, df["y"] - own_base_y)

    # Team gold difference at each frame — the player's own team state, which is
    # visible in-game via the scoreboard.
    team_gold = (
        df.groupby(["match_id", "timestamp_ms", "team_id"])["total_gold"].sum().reset_index()
    )
    pivot = team_gold.pivot_table(
        index=["match_id", "timestamp_ms"], columns="team_id", values="total_gold"
    ).reset_index()
    if 100 in pivot.columns and 200 in pivot.columns:
        pivot["gold_diff_100"] = pivot[100] - pivot[200]
        df = df.merge(
            pivot[["match_id", "timestamp_ms", "gold_diff_100"]],
            on=["match_id", "timestamp_ms"],
            how="left",
        )
        df["team_gold_diff"] = np.where(
            df["team_id"] == 100, df["gold_diff_100"], -df["gold_diff_100"]
        )
        df = df.drop(columns=["gold_diff_100"])
    else:
        df["team_gold_diff"] = 0.0
    df["team_gold_diff"] = df["team_gold_diff"].fillna(0.0)

    df["nearby_recent_deaths"] = _nearby_recent_deaths(df, events)
    df["objective_pressure"] = _objective_pressure(df, events)
    df["cell_x"], df["cell_y"] = zip(
        *[
            grid_cell(x, y, settings.risk_model_grid_size)
            for x, y in zip(df["x"], df["y"], strict=True)
        ],
        strict=True,
    )
    return df


def _nearby_recent_deaths(df: pd.DataFrame, events: pd.DataFrame) -> np.ndarray:
    """Deaths near this position in the preceding minute.

    Kills are announced to every player, so this is information the player had.
    """
    out = np.zeros(len(df), dtype=float)
    kills = events[(events["type"] == "CHAMPION_KILL") & events["ex"].notna()]
    if kills.empty:
        return out
    by_match: dict[str, np.ndarray] = {
        mid: sub[["timestamp_ms", "ex", "ey"]].to_numpy(dtype=float)
        for mid, sub in kills.groupby("match_id")
    }
    positions = df[["timestamp_ms", "x", "y"]].to_numpy(dtype=float)
    match_ids = df["match_id"].to_numpy()
    for i in range(len(df)):
        arr = by_match.get(match_ids[i])
        if arr is None:
            continue
        ts, x, y = positions[i]
        window = arr[(arr[:, 0] <= ts) & (arr[:, 0] > ts - NEARBY_DEATH_WINDOW_MS)]
        if window.size == 0:
            continue
        d = np.hypot(window[:, 1] - x, window[:, 2] - y)
        out[i] = float(np.sum(d <= NEARBY_DEATH_RADIUS))
    return out


def _objective_pressure(df: pd.DataFrame, events: pd.DataFrame) -> np.ndarray:
    """Whether a major neutral objective is plausibly live.

    Derived only from what has already happened (elapsed time and previously
    taken objectives), never from the future. Baron is treated as up once the
    game clock passes 20 minutes and no Baron has fallen in the last six.
    """
    out = np.zeros(len(df), dtype=float)
    barons = events[
        (events["type"] == "ELITE_MONSTER_KILL") & (events["monster_type"] == "BARON_NASHOR")
    ]
    baron_by_match: dict[str, np.ndarray] = {
        mid: sub["timestamp_ms"].to_numpy(dtype=float) for mid, sub in barons.groupby("match_id")
    }
    ts = df["timestamp_ms"].to_numpy(dtype=float)
    match_ids = df["match_id"].to_numpy()
    for i in range(len(df)):
        t = ts[i]
        if t < 20 * 60_000:
            out[i] = 1.0 if t >= 5 * 60_000 else 0.0  # dragon cadence only
            continue
        taken = baron_by_match.get(match_ids[i])
        recent = taken is not None and taken[(taken <= t) & (taken > t - 6 * 60_000)].size > 0
        out[i] = 1.0 if recent else 2.0
    return out


# --- empirical grid -----------------------------------------------------------


def refresh_risk_grid(
    session: Session,
    *,
    horizon_seconds: int | None = None,
    grid_size: int | None = None,
    limit_matches: int | None = None,
) -> int:
    """Recompute `map_risk_cells` from the current corpus. Returns rows written."""
    horizon = horizon_seconds or settings.risk_horizon_seconds
    size = grid_size or settings.risk_model_grid_size
    df = build_exposure_frame(session, horizon_seconds=horizon, limit_matches=limit_matches)
    if df.empty:
        return 0

    baseline = (
        df.groupby(["phase", "role", "tier_group"])["died_within_horizon"]
        .mean()
        .rename("baseline_risk")
        .reset_index()
    )
    grouped = (
        df.groupby(["cell_x", "cell_y", "phase", "role", "tier_group"])
        .agg(exposures=("died_within_horizon", "size"), deaths=("died_within_horizon", "sum"))
        .reset_index()
        .merge(baseline, on=["phase", "role", "tier_group"], how="left")
    )
    # Shrink towards the (phase, role, tier) marginal so sparse cells do not
    # produce confident nonsense.
    grouped["risk"] = (grouped["deaths"] + SMOOTHING_ALPHA * grouped["baseline_risk"]) / (
        grouped["exposures"] + SMOOTHING_ALPHA
    )
    grouped["lift"] = np.where(
        grouped["baseline_risk"] > 0, grouped["risk"] / grouped["baseline_risk"], 1.0
    )

    session.execute(delete(MapRiskCell))
    written = 0
    for row in grouped.itertuples(index=False):
        cx, cy = int(row.cell_x), int(row.cell_y)
        zx, zy = cell_center(cx, cy, size)
        session.add(
            MapRiskCell(
                grid_size=size,
                cell_x=cx,
                cell_y=cy,
                phase=str(row.phase),
                role=str(row.role),
                tier_group=str(row.tier_group),
                horizon_seconds=horizon,
                exposures=int(row.exposures),
                deaths=int(row.deaths),
                risk=float(row.risk),
                baseline_risk=float(row.baseline_risk),
                lift=float(row.lift),
                zone=classify_zone(zx, zy).value,
            )
        )
        written += 1
    session.flush()
    return written


# --- learned model ------------------------------------------------------------

NUMERIC_FEATURES: tuple[str, ...] = (
    "x",
    "y",
    "game_seconds",
    "team_gold_diff",
    "dist_dragon",
    "dist_baron",
    "dist_own_base",
    "enemy_half",
    "nearby_recent_deaths",
    "objective_pressure",
    "level",
)
CATEGORICAL_FEATURES: tuple[str, ...] = ("role", "zone", "phase")


class DeathRiskModel:
    """P(death within the horizon | position, clock, own-team state).

    Backed by scikit-learn's histogram gradient boosting. The estimator is built
    by a factory so that swapping in XGBoost later is a one-line change (see
    `services/ml/registry.py`).
    """

    def __init__(self, horizon_seconds: int | None = None) -> None:
        self.horizon_seconds = horizon_seconds or settings.risk_horizon_seconds
        self.pipeline: Any | None = None
        self.metrics: RiskModelMetrics | None = None
        self.feature_names: list[str] = list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES)

    def _build_pipeline(self) -> Any:
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder

        pre = ColumnTransformer(
            transformers=[
                ("num", "passthrough", list(NUMERIC_FEATURES)),
                (
                    "cat",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                    list(CATEGORICAL_FEATURES),
                ),
            ]
        )
        return Pipeline(
            [
                ("pre", pre),
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        max_iter=180,
                        learning_rate=0.08,
                        max_depth=6,
                        min_samples_leaf=40,
                        l2_regularization=1.0,
                        random_state=42,
                    ),
                ),
            ]
        )

    def fit(self, df: pd.DataFrame, *, test_size: float = 0.25) -> RiskModelMetrics:
        from sklearn.metrics import brier_score_loss, roc_auc_score
        from sklearn.model_selection import GroupShuffleSplit

        data = df.dropna(subset=list(NUMERIC_FEATURES)).copy()
        if data.empty or data["died_within_horizon"].nunique() < 2:
            raise ValueError("not enough labelled exposures to fit a risk model")

        X = data[self.feature_names]
        y = data["died_within_horizon"].astype(int).to_numpy()
        # Split by match so frames from one game never straddle train and test —
        # they are far too correlated for a random split to be honest.
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=42)
        train_idx, test_idx = next(splitter.split(X, y, groups=data["match_id"]))

        self.pipeline = self._build_pipeline()
        self.pipeline.fit(X.iloc[train_idx], y[train_idx])
        proba = self.pipeline.predict_proba(X.iloc[test_idx])[:, 1]
        y_test = y[test_idx]
        self.metrics = RiskModelMetrics(
            roc_auc=float(roc_auc_score(y_test, proba)) if len(set(y_test)) > 1 else float("nan"),
            brier=float(brier_score_loss(y_test, proba)),
            base_rate=float(y.mean()),
            n_samples=len(y),
            n_positive=int(y.sum()),
        )
        return self.metrics

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if self.pipeline is None:
            raise RuntimeError("risk model is not fitted")
        data = df.copy()
        for col in NUMERIC_FEATURES:
            if col not in data:
                data[col] = 0.0
        data[list(NUMERIC_FEATURES)] = data[list(NUMERIC_FEATURES)].fillna(0.0)
        return self.pipeline.predict_proba(data[self.feature_names])[:, 1]


def score_match_positions(session: Session, match_id: str, model: DeathRiskModel) -> int:
    """Fill the risk-adjusted positioning features for one match.

    `deaths_above_expected` is the honest version of "he dies too much": actual
    deaths minus the deaths the model expected given where and when the player
    stood. Positive means they died more than their positioning implied.
    """
    df = build_exposure_frame(session, horizon_seconds=model.horizon_seconds, match_ids=[match_id])
    if df.empty:
        return 0
    df["risk"] = model.predict(df)
    high = df["risk"].quantile(0.90) if len(df) > 20 else df["risk"].max()

    agg = (
        df.groupby("puuid")
        .agg(
            mean_risk=("risk", "mean"),
            expected=("risk", "sum"),
            actual=("died_within_horizon", "sum"),
            high_share=("risk", lambda s: float((s >= high).mean())),
        )
        .reset_index()
    )

    features = {
        f.puuid: f
        for f in session.scalars(
            select(ParticipantFeatures).where(ParticipantFeatures.match_id == match_id)
        )
    }
    updated = 0
    for row in agg.itertuples(index=False):
        target = features.get(row.puuid)
        if target is None:
            continue
        target.mean_position_risk = float(row.mean_risk)
        target.expected_deaths = float(row.expected)
        target.deaths_above_expected = float(row.actual) - float(row.expected)
        target.high_risk_exposure_share = float(row.high_share)
        updated += 1
    session.flush()
    return updated


# --- read models for the API --------------------------------------------------


def heatmap_cells(
    session: Session,
    *,
    role: str | None = None,
    phase: str | None = None,
    tier_group: str | None = None,
    min_exposures: int = 10,
) -> list[dict[str, object]]:
    stmt = select(MapRiskCell).where(MapRiskCell.exposures >= min_exposures)
    if role:
        stmt = stmt.where(MapRiskCell.role == role)
    if phase:
        stmt = stmt.where(MapRiskCell.phase == phase)
    if tier_group:
        stmt = stmt.where(MapRiskCell.tier_group == tier_group)
    return [
        {
            "cell_x": c.cell_x,
            "cell_y": c.cell_y,
            "grid_size": c.grid_size,
            "phase": c.phase,
            "role": c.role,
            "tier_group": c.tier_group,
            "exposures": c.exposures,
            "deaths": c.deaths,
            "risk": c.risk,
            "baseline_risk": c.baseline_risk,
            "lift": c.lift,
            "zone": c.zone,
        }
        for c in session.scalars(stmt)
    ]


@dataclass(slots=True)
class ZoneRisk:
    zone: str
    phase: str
    exposures: int
    deaths: int
    risk: float
    baseline_risk: float
    lift: float


def zone_risk_table(
    session: Session,
    *,
    role: str | None = None,
    tier_group: str | None = None,
    min_exposures: int = 30,
) -> list[ZoneRisk]:
    """Risk by named region and phase — the source of the region insights."""
    stmt = select(MapRiskCell)
    if role:
        stmt = stmt.where(MapRiskCell.role == role)
    if tier_group:
        stmt = stmt.where(MapRiskCell.tier_group == tier_group)
    rows = list(session.scalars(stmt))
    if not rows:
        return []
    frame = pd.DataFrame(
        [
            {
                "zone": r.zone or "UNKNOWN",
                "phase": r.phase,
                "exposures": r.exposures,
                "deaths": r.deaths,
                "baseline_risk": r.baseline_risk,
            }
            for r in rows
        ]
    )
    grouped = (
        frame.groupby(["zone", "phase"])
        .agg(
            exposures=("exposures", "sum"),
            deaths=("deaths", "sum"),
            baseline_risk=("baseline_risk", "mean"),
        )
        .reset_index()
    )
    grouped = grouped[grouped["exposures"] >= min_exposures]
    grouped["risk"] = grouped["deaths"] / grouped["exposures"].clip(lower=1)
    grouped["lift"] = np.where(
        grouped["baseline_risk"] > 0, grouped["risk"] / grouped["baseline_risk"], 1.0
    )
    return [
        ZoneRisk(
            zone=str(r.zone),
            phase=str(r.phase),
            exposures=int(r.exposures),
            deaths=int(r.deaths),
            risk=float(r.risk),
            baseline_risk=float(r.baseline_risk),
            lift=float(r.lift),
        )
        for r in grouped.sort_values("lift", ascending=False).itertuples(index=False)
    ]


def player_exposure_heatmap(
    session: Session,
    puuid: str,
    *,
    grid_size: int | None = None,
    limit_matches: int = 40,
) -> dict[str, object]:
    """Where one player actually spends their time, and where they die."""
    size = grid_size or settings.risk_model_grid_size
    match_ids = list(
        session.scalars(
            select(MatchParticipant.match_id)
            .join(Match, Match.match_id == MatchParticipant.match_id)
            .where(MatchParticipant.puuid == puuid, Match.timeline_ingested.is_(True))
            .order_by(Match.game_start.desc())
            .limit(limit_matches)
        )
    )
    if not match_ids:
        return {"grid_size": size, "cells": [], "deaths": [], "matches": 0}

    df = build_exposure_frame(session, match_ids=match_ids)
    if df.empty:
        return {"grid_size": size, "cells": [], "deaths": [], "matches": 0}
    mine = df[df["puuid"] == puuid]
    if mine.empty:
        return {"grid_size": size, "cells": [], "deaths": [], "matches": len(match_ids)}

    cells = (
        mine.groupby(["cell_x", "cell_y"])
        .agg(exposures=("died_within_horizon", "size"), deaths=("died_within_horizon", "sum"))
        .reset_index()
    )
    cells["death_rate"] = cells["deaths"] / cells["exposures"].clip(lower=1)

    deaths = pd.DataFrame(
        session.execute(
            select(
                TimelineEvent.match_id,
                TimelineEvent.timestamp_ms,
                TimelineEvent.position_x,
                TimelineEvent.position_y,
            )
            .join(
                MatchParticipant,
                (MatchParticipant.match_id == TimelineEvent.match_id)
                & (MatchParticipant.participant_id == TimelineEvent.victim_id),
            )
            .where(
                TimelineEvent.match_id.in_(match_ids),
                TimelineEvent.type == "CHAMPION_KILL",
                MatchParticipant.puuid == puuid,
            )
        ).all(),
        columns=["match_id", "timestamp_ms", "x", "y"],
    ).dropna(subset=["x", "y"])

    return {
        "grid_size": size,
        "matches": len(match_ids),
        "cells": cells.to_dict("records"),
        "deaths": [
            {
                "match_id": r.match_id,
                "minute": int(r.timestamp_ms // 60000),
                "x": float(r.x),
                "y": float(r.y),
                "zone": classify_zone(float(r.x), float(r.y)).value,
            }
            for r in deaths.itertuples(index=False)
        ],
    }


def default_role(role: str | None) -> str:
    try:
        return Role(role or "").value
    except ValueError:
        return Role.MIDDLE.value


def default_phase(phase: str | None) -> str:
    try:
        return Phase(phase or "").value
    except ValueError:
        return Phase.EARLY.value
