"""Rebuild every derived analytics layer that depends on the whole corpus.

Per-match features are computed at ingest time, but anything that needs a
*population* — cohort baselines, the map risk surface, the rank-separation model,
expected roam value — has to be rebuilt after new matches land. This module is
that step, and it is deliberately one function so the CLI, the API and the tests
cannot drift apart on the ordering.

Ordering matters: cohorts before RCE normalisation (which reads them), the risk
grid and risk model before per-match risk scoring (which uses them), and all of
that before the skill-gap model (whose feature set includes the risk columns).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InsufficientDataError
from app.core.logging import get_logger
from app.db.models import Match, RoamEvent
from app.services.analytics.cohorts import normalize_rce, refresh_cohorts
from app.services.analytics.spatial import (
    DeathRiskModel,
    build_exposure_frame,
    refresh_risk_grid,
    score_match_positions,
)
from app.services.ml.registry import ModelArtifact, next_version, save_model
from app.services.ml.skill_gap import train_skill_gap_model

log = get_logger(__name__)

RISK_MODEL_NAME = "death_risk"


@dataclass
class RefreshReport:
    cohort_rows: int = 0
    rce_normalized: int = 0
    risk_cells: int = 0
    risk_model: dict[str, Any] | None = None
    matches_scored: int = 0
    roams_valued: int = 0
    skill_gap: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_rows": self.cohort_rows,
            "rce_normalized": self.rce_normalized,
            "risk_cells": self.risk_cells,
            "risk_model": self.risk_model,
            "matches_scored": self.matches_scored,
            "roams_valued": self.roams_valued,
            "skill_gap": self.skill_gap,
            "warnings": self.warnings,
        }


def refresh_all(
    session: Session,
    *,
    limit_matches: int | None = None,
    train_skill_gap: bool = True,
) -> RefreshReport:
    report = RefreshReport()

    report.cohort_rows = refresh_cohorts(session)
    log.info("refresh.cohorts", rows=report.cohort_rows)

    report.rce_normalized = normalize_rce(session)
    log.info("refresh.rce", rows=report.rce_normalized)

    report.risk_cells = refresh_risk_grid(session, limit_matches=limit_matches)
    log.info("refresh.risk_grid", cells=report.risk_cells)

    risk_model = _fit_risk_model(session, limit_matches, report)
    if risk_model is not None:
        match_ids = list(
            session.scalars(select(Match.match_id).where(Match.timeline_ingested.is_(True)))
        )
        for match_id in match_ids:
            report.matches_scored += (
                1 if score_match_positions(session, match_id, risk_model) else 0
            )
        log.info("refresh.risk_scoring", matches=report.matches_scored)

        # Second cohort pass. The first ran before the risk columns existed, so
        # `mean_position_risk` and friends had no baselines and every comparison
        # against them came back empty. Rebuilding now that they are populated is
        # simpler than reordering, because RCE normalisation genuinely needs
        # cohorts to exist before the risk model runs.
        report.cohort_rows = refresh_cohorts(session)
        log.info("refresh.cohorts_second_pass", rows=report.cohort_rows)

    report.roams_valued = value_roams(session)

    if train_skill_gap:
        try:
            artifact = train_skill_gap_model(session)
            report.skill_gap = {
                "version": artifact.version,
                "n_samples": artifact.n_samples,
                "metrics": artifact.metrics,
            }
        except InsufficientDataError as exc:
            report.warnings.append(f"skill-gap model not trained: {exc.message}")
            log.warning("refresh.skill_gap_skipped", reason=exc.message)

    return report


def _fit_risk_model(
    session: Session, limit_matches: int | None, report: RefreshReport
) -> DeathRiskModel | None:
    exposures = build_exposure_frame(session, limit_matches=limit_matches)
    if exposures.empty:
        report.warnings.append("no timeline exposures available; risk model not trained")
        return None
    model = DeathRiskModel()
    try:
        metrics = model.fit(exposures)
    except ValueError as exc:
        report.warnings.append(f"risk model not trained: {exc}")
        log.warning("refresh.risk_model_skipped", reason=str(exc))
        return None

    report.risk_model = {
        "roc_auc": metrics.roc_auc,
        "brier": metrics.brier,
        "base_rate": metrics.base_rate,
        "n_samples": metrics.n_samples,
        "n_positive": metrics.n_positive,
        "horizon_seconds": model.horizon_seconds,
    }
    save_model(
        session,
        ModelArtifact(
            name=RISK_MODEL_NAME,
            version=next_version(),
            kind="classifier",
            estimator=model.pipeline,
            metrics=report.risk_model,
            params={"horizon_seconds": model.horizon_seconds},
            feature_names=model.feature_names,
            n_samples=metrics.n_samples,
            payload={
                "horizon_seconds": model.horizon_seconds,
                "feature_names": model.feature_names,
            },
        ),
    )
    log.info("refresh.risk_model", **report.risk_model)
    return model


def load_risk_model(session: Session) -> DeathRiskModel | None:
    """Rehydrate the saved death-risk model, if one exists."""
    from app.services.ml.registry import load_model

    loaded = load_model(session, RISK_MODEL_NAME)
    if loaded is None:
        return None
    _record, bundle = loaded
    model = DeathRiskModel(horizon_seconds=bundle["payload"].get("horizon_seconds"))
    model.pipeline = bundle["estimator"]
    model.feature_names = bundle["payload"].get("feature_names", model.feature_names)
    return model


def value_roams(session: Session) -> int:
    """Set each roam's `expected_value` from its peer group.

    A roam's peer group is (role, destination zone): walking mid-to-dragon is a
    different proposition from walking mid-to-top, and comparing a roam to the
    average of *its own kind* is what turns raw value into efficiency.
    """
    rows = list(session.scalars(select(RoamEvent)))
    if not rows:
        return 0
    frame = pd.DataFrame(
        [{"id": r.id, "role": r.role, "zone": r.target_zone, "value": r.value} for r in rows]
    )
    group_means = frame.groupby(["role", "zone"])["value"].agg(["mean", "size"])
    role_means = frame.groupby("role")["value"].mean()
    overall = float(frame["value"].mean())

    by_id = {r.id: r for r in rows}
    updated = 0
    for record in frame.itertuples(index=False):
        key = (record.role, record.zone)
        if key in group_means.index and int(group_means.loc[key, "size"]) >= 10:
            expected = float(group_means.loc[key, "mean"])
        elif record.role in role_means.index:
            expected = float(role_means.loc[record.role])
        else:
            expected = overall
        by_id[record.id].expected_value = expected
        updated += 1
    session.flush()
    return updated
