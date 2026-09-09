"""On-disk store for completed analyses.

Analyses are keyed by the SHA-256 of the replay file, so re-uploading the same
file is idempotent and cheap. This is deliberately a flat file store rather than
a table: an analysis is a self-contained document that is written once and read
whole, and keeping it out of Postgres means the upload path has no database
dependency to fail on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root() -> Path:
    root = Path(settings.replay_storage_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _paths(replay_id: str) -> tuple[Path, Path]:
    d = _root() / replay_id
    return d / "replay.bin", d / "analysis.json"


def save(replay_id: str, raw: bytes, analysis: dict[str, Any]) -> None:
    blob, doc = _paths(replay_id)
    doc.parent.mkdir(parents=True, exist_ok=True)
    if not blob.exists():
        blob.write_bytes(raw)
    doc.write_text(json.dumps(analysis, indent=2))
    log.info("analysis.saved", replay_id=replay_id, path=str(doc))


def load(replay_id: str) -> dict[str, Any] | None:
    _, doc = _paths(replay_id)
    if not doc.exists():
        return None
    try:
        return json.loads(doc.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("analysis.unreadable", replay_id=replay_id, error=str(exc))
        return None


def list_all(limit: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _root()
    entries = sorted(root.glob("*/analysis.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in entries[:limit]:
        doc = load(path.parent.name)
        if doc:
            out.append(doc)
    return out
