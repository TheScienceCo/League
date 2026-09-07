"""Decision Value Added (DVA) — experimental.

The idea
--------
Outcome statistics punish players for things that were not decisions and reward
them for things that were luck. DVA tries to isolate the part of a window that
the situation did *not* already predict:

1. Represent the game state at time T (economy, objectives, kills, and where the
   player is standing).
2. Ask what usually happens next from states like that — found by nearest
   neighbours over historical states, never from the same match.
3. Compare the win-probability change that *actually* followed against that
   historical expectation.
4. Attribute the difference, in part, to the player.

    DVA(T, horizon) = ΔWP_realized - E[ΔWP | similar historical states]

Where this is honest and where it is not
----------------------------------------
The win-probability model and the neighbour lookup are real and cross-validated.
The **attribution step is the weak link, and deliberately conservative**: win
probability is a property of ten players, so a player is credited with only the
share of the residual that their own involvement in the window supports (kills,
assists, deaths, objectives they took part in), with a small flat share
otherwise. That is a heuristic, not an identification strategy, and it cannot
separate a good decision from a teammate's good decision that happened nearby.

The whole module is therefore surfaced as experimental, is excluded from the
Skill Gap feature set, and every value it returns is labelled an estimate. It is
included because the architecture for it is the interesting part; the numbers
should be read as directional.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InsufficientDataError
from app.core.logging import get_logger
from app.db.models import Match, MatchParticipant, TimelineEvent, TimelineFrame
from app.services.ml.registry import (
    ModelArtifact,
    load_model,
    make_classifier,
    next_version,
    save_model,
)

log = get_logger(__name__)

WP_MODEL_NAME = "win_probability"
DVA_INDEX_NAME = "dva_index"

#: Horizons (seconds) over which decisions are evaluated.
DEFAULT_HORIZONS: tuple[int, ...] = (30, 60, 120)

#: State features for the win-probability model. All are team-level and knowable
#: to the player at the time.
WP_FEATURES: tuple[str, ...] = (
    "minute",
    "gold_diff",
    "xp_diff",
    "level_diff",
    "kill_diff",
    "tower_diff",
    "dragon_diff",
    "baron_diff",
)

#: Additional dimensions used only for the neighbour lookup, which needs to know
#: where the player was, not just how the game was going.
NEIGHBOUR_FEATURES: tuple[str, ...] = (*WP_FEATURES, "player_gold_share", "pos_x", "pos_y")

N_NEIGHBOURS = 60
#: Flat share of a window's residual assigned to a player with no involvement.
BASELINE_ATTRIBUTION = 0.10
#: Additional share per involvement event, capped so one window cannot be
#: attributed more than fully to a single player.
INVOLVEMENT_ATTRIBUTION = 0.25
MAX_ATTRIBUTION = 0.60


@dataclass(slots=True)
class DVAWindow:
    minute: int
    horizon_seconds: int
    win_probability: float
    win_probability_after: float
    realized_delta: float
    expected_delta: float
    residual: float
    attribution_share: float
    dva: float
    involvement: int
    neighbours: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DVAReport:
    puuid: str
    match_id: str | None
    horizon_seconds: int
    total_dva: float
    mean_dva_per_window: float
    windows: list[DVAWindow] = field(default_factory=list)
    model: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    experimental: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "puuid": self.puuid,
            "match_id": self.match_id,
            "horizon_seconds": self.horizon_seconds,
            "total_dva": self.total_dva,
            "mean_dva_per_window": self.mean_dva_per_window,
            "windows": [w.to_dict() for w in self.windows],
            "model": self.model,
            "caveats": self.caveats,
            "experimental": self.experimental,
        }


# --- state construction -------------------------------------------------------


def build_state_frame(
    session: Session,
    *,
    match_ids: list[str] | None = None,
    limit_matches: int | None = None,
) -> pd.DataFrame:
    """One row per (match, team, minute, player): game state and eventual result."""
    match_stmt = select(Match.match_id, Match.winning_team_id).where(
        Match.timeline_ingested.is_(True), Match.winning_team_id.isnot(None)
    )
    if match_ids:
        match_stmt = match_stmt.where(Match.match_id.in_(match_ids))
    if limit_matches:
        match_stmt = match_stmt.order_by(Match.game_start.desc()).limit(limit_matches)
    matches = pd.DataFrame(
        session.execute(match_stmt).all(), columns=["match_id", "winning_team_id"]
    )
    if matches.empty:
        return pd.DataFrame()
    ids = matches["match_id"].tolist()

    frames = pd.DataFrame(
        session.execute(
            select(
                TimelineFrame.match_id,
                TimelineFrame.participant_id,
                TimelineFrame.minute,
                TimelineFrame.total_gold,
                TimelineFrame.xp,
                TimelineFrame.level,
                TimelineFrame.position_x,
                TimelineFrame.position_y,
            ).where(TimelineFrame.match_id.in_(ids))
        ).all(),
        columns=["match_id", "participant_id", "minute", "gold", "xp", "level", "pos_x", "pos_y"],
    )
    if frames.empty:
        return pd.DataFrame()

    participants = pd.DataFrame(
        session.execute(
            select(
                MatchParticipant.match_id,
                MatchParticipant.participant_id,
                MatchParticipant.puuid,
                MatchParticipant.team_id,
                MatchParticipant.team_position,
            ).where(MatchParticipant.match_id.in_(ids))
        ).all(),
        columns=["match_id", "participant_id", "puuid", "team_id", "role"],
    )
    frames = frames.merge(participants, on=["match_id", "participant_id"], how="inner")

    team_state = (
        frames.groupby(["match_id", "minute", "team_id"])
        .agg(gold=("gold", "sum"), xp=("xp", "sum"), level=("level", "sum"))
        .reset_index()
    )
    events = pd.DataFrame(
        session.execute(
            select(
                TimelineEvent.match_id,
                TimelineEvent.minute,
                TimelineEvent.type,
                TimelineEvent.killer_id,
                TimelineEvent.team_id,
                TimelineEvent.monster_type,
            ).where(
                TimelineEvent.match_id.in_(ids),
                TimelineEvent.type.in_(["CHAMPION_KILL", "BUILDING_KILL", "ELITE_MONSTER_KILL"]),
            )
        ).all(),
        columns=["match_id", "minute", "type", "killer_id", "event_team_id", "monster_type"],
    )
    counts = _cumulative_event_counts(events, participants, team_state)
    team_state = team_state.merge(counts, on=["match_id", "minute", "team_id"], how="left")
    for col in ("kills", "towers", "dragons", "barons"):
        team_state[col] = team_state[col].fillna(0.0)

    opponent = team_state.copy()
    opponent["team_id"] = np.where(opponent["team_id"] == 100, 200, 100)
    opponent = opponent.rename(
        columns={
            "gold": "o_gold",
            "xp": "o_xp",
            "level": "o_level",
            "kills": "o_kills",
            "towers": "o_towers",
            "dragons": "o_dragons",
            "barons": "o_barons",
        }
    )
    state = team_state.merge(opponent, on=["match_id", "minute", "team_id"], how="inner")
    state["gold_diff"] = state["gold"] - state["o_gold"]
    state["xp_diff"] = state["xp"] - state["o_xp"]
    state["level_diff"] = state["level"] - state["o_level"]
    state["kill_diff"] = state["kills"] - state["o_kills"]
    state["tower_diff"] = state["towers"] - state["o_towers"]
    state["dragon_diff"] = state["dragons"] - state["o_dragons"]
    state["baron_diff"] = state["barons"] - state["o_barons"]

    state = state.merge(matches, on="match_id", how="left")
    state["won"] = (state["team_id"] == state["winning_team_id"]).astype(int)

    out = frames.merge(
        state[
            [
                "match_id",
                "minute",
                "team_id",
                "gold",
                "won",
                *[c for c in WP_FEATURES if c != "minute"],
            ]
        ].rename(columns={"gold": "team_gold"}),
        on=["match_id", "minute", "team_id"],
        how="inner",
    )
    out["player_gold_share"] = out["gold"] / out["team_gold"].clip(lower=1)
    out["pos_x"] = out["pos_x"].fillna(7500.0)
    out["pos_y"] = out["pos_y"].fillna(7500.0)
    return out


def _cumulative_event_counts(
    events: pd.DataFrame, participants: pd.DataFrame, team_state: pd.DataFrame
) -> pd.DataFrame:
    """Running totals of kills/towers/objectives per team and minute."""
    if events.empty:
        return pd.DataFrame(
            columns=["match_id", "minute", "team_id", "kills", "towers", "dragons", "barons"]
        )
    killer_team = participants.rename(
        columns={"participant_id": "killer_id", "team_id": "killer_team"}
    )[["match_id", "killer_id", "killer_team"]]
    ev = events.merge(killer_team, on=["match_id", "killer_id"], how="left")
    # BUILDING_KILL carries the *owning* team, so the credit goes to the other side.
    ev["credit_team"] = np.where(
        ev["type"] == "BUILDING_KILL",
        np.where(ev["event_team_id"] == 100, 200, 100),
        ev["killer_team"],
    )
    ev = ev.dropna(subset=["credit_team"])
    ev["credit_team"] = ev["credit_team"].astype(int)
    ev["kills"] = (ev["type"] == "CHAMPION_KILL").astype(int)
    ev["towers"] = (ev["type"] == "BUILDING_KILL").astype(int)
    ev["dragons"] = (
        (ev["type"] == "ELITE_MONSTER_KILL") & (ev["monster_type"] == "DRAGON")
    ).astype(int)
    ev["barons"] = (
        (ev["type"] == "ELITE_MONSTER_KILL") & (ev["monster_type"] == "BARON_NASHOR")
    ).astype(int)

    per_minute = (
        ev.groupby(["match_id", "minute", "credit_team"])[["kills", "towers", "dragons", "barons"]]
        .sum()
        .reset_index()
        .rename(columns={"credit_team": "team_id"})
    )
    grid = team_state[["match_id", "minute", "team_id"]].drop_duplicates()
    merged = grid.merge(per_minute, on=["match_id", "minute", "team_id"], how="left").fillna(0.0)
    merged = merged.sort_values(["match_id", "team_id", "minute"])
    for col in ("kills", "towers", "dragons", "barons"):
        merged[col] = merged.groupby(["match_id", "team_id"])[col].cumsum()
    return merged


# --- models -------------------------------------------------------------------


def train_dva_models(session: Session, *, limit_matches: int | None = None) -> dict[str, Any]:
    """Fit the win-probability model and build the historical state index."""
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    states = build_state_frame(session, limit_matches=limit_matches)
    if states.empty or len(states) < 500:
        raise InsufficientDataError(
            "not enough timeline states to fit the DVA models",
            detail={"rows": len(states)},
        )

    team_states = (
        states.groupby(["match_id", "minute", "team_id"])
        .first()
        .reset_index()[["match_id", "minute", "team_id", *WP_FEATURES, "won"]]
    )
    X = team_states[list(WP_FEATURES)]
    y = team_states["won"].to_numpy()
    groups = team_states["match_id"].to_numpy()

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    tr, te = next(splitter.split(X, y, groups))
    wp_model = make_classifier(n_classes=2)
    wp_model.fit(X.iloc[tr], y[tr])
    proba = wp_model.predict_proba(X.iloc[te])[:, 1]
    metrics = {
        "roc_auc": float(roc_auc_score(y[te], proba)) if len(set(y[te])) > 1 else None,
        "brier": float(brier_score_loss(y[te], proba)),
        "n_states": len(team_states),
        "n_matches": int(team_states["match_id"].nunique()),
    }
    wp_model = make_classifier(n_classes=2)
    wp_model.fit(X, y)
    save_model(
        session,
        ModelArtifact(
            name=WP_MODEL_NAME,
            version=next_version(),
            kind="classifier",
            estimator=wp_model,
            metrics=metrics,
            feature_names=list(WP_FEATURES),
            n_samples=len(team_states),
            payload={"features": list(WP_FEATURES)},
        ),
    )

    # Neighbour index over player-level states, standardised so no dimension
    # dominates the distance purely because of its units.
    sample = states
    if len(sample) > 120_000:
        sample = states.sample(120_000, random_state=42)
    neighbour_X = sample[list(NEIGHBOUR_FEATURES)].to_numpy(dtype=float)
    scaler = StandardScaler().fit(neighbour_X)
    index = NearestNeighbors(n_neighbors=min(N_NEIGHBOURS, len(sample)), algorithm="auto")
    index.fit(scaler.transform(neighbour_X))

    reference = sample[["match_id", "minute", "team_id", *WP_FEATURES]].reset_index(drop=True)
    save_model(
        session,
        ModelArtifact(
            name=DVA_INDEX_NAME,
            version=next_version(),
            kind="neighbours",
            estimator=index,
            metrics={"n_reference_states": len(sample)},
            feature_names=list(NEIGHBOUR_FEATURES),
            n_samples=len(sample),
            payload={
                "scaler": scaler,
                "reference": reference,
                "features": list(NEIGHBOUR_FEATURES),
            },
        ),
    )
    log.info("dva.trained", **metrics)
    return {"win_probability": metrics, "reference_states": len(sample)}


class DVAEngine:
    """Evaluates DVA for a player using the saved WP model and state index."""

    def __init__(self, wp_model: Any, index: Any, scaler: Any, reference: pd.DataFrame) -> None:
        self.wp_model = wp_model
        self.index = index
        self.scaler = scaler
        self.reference = reference

    @classmethod
    def load(cls, session: Session) -> DVAEngine | None:
        wp = load_model(session, WP_MODEL_NAME)
        idx = load_model(session, DVA_INDEX_NAME)
        if wp is None or idx is None:
            return None
        _, wp_bundle = wp
        _, idx_bundle = idx
        return cls(
            wp_model=wp_bundle["estimator"],
            index=idx_bundle["estimator"],
            scaler=idx_bundle["payload"]["scaler"],
            reference=idx_bundle["payload"]["reference"],
        )

    def win_probability(self, states: pd.DataFrame) -> np.ndarray:
        return self.wp_model.predict_proba(states[list(WP_FEATURES)])[:, 1]

    def evaluate(
        self,
        session: Session,
        *,
        match_id: str,
        puuid: str,
        horizon_seconds: int = 60,
    ) -> DVAReport:
        states = build_state_frame(session, match_ids=[match_id])
        if states.empty:
            raise InsufficientDataError("no timeline states for this match")
        mine = states[states["puuid"] == puuid].sort_values("minute").reset_index(drop=True)
        if mine.empty:
            raise InsufficientDataError("player did not appear in this match's timeline")

        wp = self.win_probability(mine)
        mine = mine.assign(wp=wp)
        step = max(1, round(horizon_seconds / 60))

        # Expected forward change, from historically similar states in other games.
        expected = self._expected_deltas(mine, step, exclude_match=match_id)
        involvement = _involvement_by_minute(session, match_id, puuid)

        windows: list[DVAWindow] = []
        for i in range(len(mine) - step):
            realized = float(mine.loc[i + step, "wp"] - mine.loc[i, "wp"])
            exp_delta, n_neighbours = expected[i]
            if n_neighbours == 0:
                continue
            residual = realized - exp_delta
            minute = int(mine.loc[i, "minute"])
            involved = sum(involvement.get(m, 0) for m in range(minute, minute + step + 1))
            share = min(
                MAX_ATTRIBUTION,
                BASELINE_ATTRIBUTION + INVOLVEMENT_ATTRIBUTION * involved,
            )
            windows.append(
                DVAWindow(
                    minute=minute,
                    horizon_seconds=horizon_seconds,
                    win_probability=float(mine.loc[i, "wp"]),
                    win_probability_after=float(mine.loc[i + step, "wp"]),
                    realized_delta=realized,
                    expected_delta=float(exp_delta),
                    residual=float(residual),
                    attribution_share=float(share),
                    dva=float(residual * share),
                    involvement=int(involved),
                    neighbours=int(n_neighbours),
                )
            )

        total = sum(w.dva for w in windows)
        return DVAReport(
            puuid=puuid,
            match_id=match_id,
            horizon_seconds=horizon_seconds,
            total_dva=float(total),
            mean_dva_per_window=float(total / len(windows)) if windows else 0.0,
            windows=windows,
            model={"win_probability": WP_MODEL_NAME, "index": DVA_INDEX_NAME},
            caveats=[
                "Experimental. Win probability is a team-level quantity; the "
                "attribution of its residual to one player is a heuristic based "
                "on that player's involvement in the window, not a causal "
                "identification.",
                "Expected change is the average outcome of historically similar "
                "states drawn from other matches; similarity is over economy, "
                "objectives and position only.",
                "Values are estimates and should be read directionally.",
            ],
        )

    def _expected_deltas(
        self, mine: pd.DataFrame, step: int, *, exclude_match: str
    ) -> list[tuple[float, int]]:
        """Average forward WP change among similar historical states."""
        query = self.scaler.transform(mine[list(NEIGHBOUR_FEATURES)].to_numpy(dtype=float))
        n_neighbours = min(self.index.n_neighbors, len(self.reference))
        _, indices = self.index.kneighbors(query, n_neighbors=n_neighbours)

        ref = self.reference
        # Precompute the forward WP change for every reference state once.
        if "forward_delta" not in ref.columns:
            ref_wp = self.win_probability(ref)
            ref = ref.assign(wp=ref_wp)
            ref = ref.sort_values(["match_id", "team_id", "minute"]).reset_index(drop=True)
            ref["forward_delta"] = (
                ref.groupby(["match_id", "team_id"])["wp"].shift(-step) - ref["wp"]
            )
            self.reference = ref

        deltas = ref["forward_delta"].to_numpy()
        match_ids = ref["match_id"].to_numpy()
        out: list[tuple[float, int]] = []
        for row in indices:
            # Never let a match inform its own expectation.
            mask = (match_ids[row] != exclude_match) & ~np.isnan(deltas[row])
            values = deltas[row][mask]
            out.append((float(values.mean()) if values.size else 0.0, int(values.size)))
        return out


def _involvement_by_minute(session: Session, match_id: str, puuid: str) -> dict[int, int]:
    """Count of events per minute this player was personally part of."""
    participant = session.scalar(
        select(MatchParticipant).where(
            MatchParticipant.match_id == match_id, MatchParticipant.puuid == puuid
        )
    )
    if participant is None:
        return {}
    pid = participant.participant_id
    out: dict[int, int] = {}
    for event in session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.match_id == match_id,
            TimelineEvent.type.in_(["CHAMPION_KILL", "ELITE_MONSTER_KILL", "BUILDING_KILL"]),
        )
    ):
        assists = event.assisting_participant_ids
        assist_ids = [int(a) for a in assists] if isinstance(assists, list) else []
        if event.killer_id == pid or event.victim_id == pid or pid in assist_ids:
            out[event.minute] = out.get(event.minute, 0) + 1
    return out
