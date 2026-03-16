from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    base = Path(settings.storage_dir)
    (base / "runs").mkdir(parents=True, exist_ok=True)
    (base / "uploads").mkdir(parents=True, exist_ok=True)
    (base / "artifacts").mkdir(parents=True, exist_ok=True)


def new_run_id(prefix: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{ts}_{uuid.uuid4().hex[:8]}"


def run_dir(run_id: str) -> Path:
    return Path(settings.storage_dir) / "runs" / run_id


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_step_result(
    run_id: str,
    step: str,
    payload: dict[str, Any],
    *,
    inputs: dict[str, Any] | None = None,
) -> Path:
    rd = run_dir(run_id)
    rd.mkdir(parents=True, exist_ok=True)
    out = {
        "run_id": run_id,
        "step": step,
        "created_at": _utc_now_iso(),
        "inputs": inputs or {},
        "payload": payload,
    }
    out_path = rd / f"{step}.json"
    write_json(out_path, out)
    return out_path

