"""Model construction and persistence.

Two jobs:

* **Factory.** `make_classifier` returns whichever gradient-boosted implementation
  is available, preferring XGBoost when it is installed (the `boost` extra) and
  falling back to scikit-learn otherwise. Call sites never import either directly,
  which is what keeps "add XGBoost later" a dependency change rather than a
  refactor.
* **Registry.** Fitted artifacts are written to disk with joblib and described in
  the `ml_models` table, so the API can report a model's metrics, training size
  and feature importances without loading the estimator.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import MLModelRecord

log = get_logger(__name__)

Backend = Literal["sklearn", "xgboost"]


class GradientModel(Protocol):
    """The surface every estimator in this project is used through.

    `sample_weight` is part of the contract because class balancing is applied
    at fit time rather than by a backend-specific `class_weight` parameter —
    scikit-learn and XGBoost disagree on the latter but both accept the former.
    """

    def fit(self, X: Any, y: Any, sample_weight: Any = ...) -> Any: ...
    def predict(self, X: Any) -> Any: ...
    def predict_proba(self, X: Any) -> Any: ...


def available_backend() -> Backend:
    if importlib.util.find_spec("xgboost") is not None:
        return "xgboost"
    return "sklearn"


def make_classifier(
    *,
    n_classes: int = 2,
    random_state: int = 42,
    backend: Backend | None = None,
    **overrides: Any,
) -> GradientModel:
    """A gradient-boosted classifier, from whichever backend is installed."""
    chosen = backend or available_backend()
    if chosen == "xgboost":  # pragma: no cover - optional dependency
        import xgboost as xgb

        params: dict[str, Any] = {
            "n_estimators": 300,
            "max_depth": 5,
            "learning_rate": 0.06,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "reg_lambda": 1.0,
            "random_state": random_state,
            "tree_method": "hist",
            "objective": "multi:softprob" if n_classes > 2 else "binary:logistic",
        }
        params.update(overrides)
        return xgb.XGBClassifier(**params)

    from sklearn.ensemble import HistGradientBoostingClassifier

    params = {
        "max_iter": 250,
        "learning_rate": 0.07,
        "max_depth": 5,
        "min_samples_leaf": 25,
        "l2_regularization": 1.0,
        "random_state": random_state,
    }
    params.update(overrides)
    return HistGradientBoostingClassifier(**params)


def make_regressor(*, random_state: int = 42, **overrides: Any) -> Any:
    chosen = available_backend()
    if chosen == "xgboost":  # pragma: no cover - optional dependency
        import xgboost as xgb

        params: dict[str, Any] = {
            "n_estimators": 300,
            "max_depth": 5,
            "learning_rate": 0.06,
            "random_state": random_state,
            "tree_method": "hist",
        }
        params.update(overrides)
        return xgb.XGBRegressor(**params)

    from sklearn.ensemble import HistGradientBoostingRegressor

    params = {
        "max_iter": 250,
        "learning_rate": 0.07,
        "max_depth": 5,
        "min_samples_leaf": 25,
        "random_state": random_state,
    }
    params.update(overrides)
    return HistGradientBoostingRegressor(**params)


@dataclass(slots=True)
class ModelArtifact:
    name: str
    version: str
    kind: str
    estimator: Any
    metrics: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    feature_importances: dict[str, float] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)
    n_samples: int = 0
    #: Anything the consumer needs alongside the estimator (baselines, encoders).
    payload: dict[str, Any] = field(default_factory=dict)


def model_dir() -> Path:
    path = Path(settings.model_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_model(session: Session, artifact: ModelArtifact) -> MLModelRecord:
    """Persist an artifact and mark it the active version of its name."""
    directory = model_dir()
    filename = f"{artifact.name}-{artifact.version}.joblib"
    path = directory / filename
    joblib.dump({"estimator": artifact.estimator, "payload": artifact.payload}, path, compress=3)

    for previous in session.scalars(
        select(MLModelRecord).where(
            MLModelRecord.name == artifact.name, MLModelRecord.is_active.is_(True)
        )
    ):
        previous.is_active = False

    record = session.scalar(
        select(MLModelRecord).where(
            MLModelRecord.name == artifact.name, MLModelRecord.version == artifact.version
        )
    )
    if record is None:
        record = MLModelRecord(name=artifact.name, version=artifact.version)
        session.add(record)
    record.kind = artifact.kind
    record.artifact_path = str(path)
    record.params = artifact.params
    record.metrics = artifact.metrics
    record.feature_importances = artifact.feature_importances
    record.feature_names = artifact.feature_names
    record.n_samples = artifact.n_samples
    record.trained_at = datetime.now(UTC)
    record.is_active = True
    session.flush()
    log.info(
        "ml.model_saved",
        name=artifact.name,
        version=artifact.version,
        n_samples=artifact.n_samples,
        path=str(path),
    )
    return record


def active_record(session: Session, name: str) -> MLModelRecord | None:
    return session.scalar(
        select(MLModelRecord)
        .where(MLModelRecord.name == name, MLModelRecord.is_active.is_(True))
        .order_by(MLModelRecord.trained_at.desc())
    )


def load_model(session: Session, name: str) -> tuple[MLModelRecord, dict[str, Any]] | None:
    """Load the active artifact for `name`, or `None` if it is missing."""
    record = active_record(session, name)
    if record is None or not record.artifact_path:
        return None
    path = Path(record.artifact_path)
    if not path.exists():
        log.warning("ml.artifact_missing", name=name, path=str(path))
        return None
    return record, joblib.load(path)


def next_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")
