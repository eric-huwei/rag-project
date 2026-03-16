from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.storage import new_run_id, save_step_result
from app.core.config import settings


async def load_document(file: UploadFile) -> dict:
    run_id = new_run_id("load")

    uploads_dir = Path(settings.storage_dir) / "uploads" / run_id
    uploads_dir.mkdir(parents=True, exist_ok=True)

    raw_path = uploads_dir / file.filename
    with raw_path.open("wb") as f:
        await file.seek(0)
        shutil.copyfileobj(file.file, f)

    payload = {
        "filename": file.filename,
        "content_type": file.content_type,
        "raw_path": str(raw_path.as_posix()),
        "size_bytes": raw_path.stat().st_size,
    }
    save_step_result(run_id, "load", payload, inputs={})
    return {"run_id": run_id, "result": payload}

