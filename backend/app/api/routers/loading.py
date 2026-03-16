from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.loading_service import load_document
from app.core.config import settings
from app.core.storage import read_json

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """
    Upload a document and persist metadata + raw bytes path.
    Output saved to: app/storage/runs/<run_id>/load.json
    """
    return await load_document(file)


@router.get("/uploads")
def list_uploads() -> dict[str, Any]:
    """
    List uploaded documents (from storage_dir/uploads).
    """
    base = Path(settings.storage_dir) / "uploads"
    if not base.exists():
        return {"items": []}

    items: list[dict[str, Any]] = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        run_id = p.name
        load_json = Path(settings.storage_dir) / "runs" / run_id / "load.json"
        if load_json.exists():
            try:
                obj = read_json(load_json)
                payload = obj.get("payload") or {}
                items.append(
                    {
                        "run_id": run_id,
                        "created_at": obj.get("created_at"),
                        "filename": payload.get("filename"),
                        "content_type": payload.get("content_type"),
                        "raw_path": payload.get("raw_path"),
                        "size_bytes": payload.get("size_bytes"),
                    }
                )
                continue
            except Exception:
                # Fall back to directory scan below
                pass

        files = [x for x in p.iterdir() if x.is_file()]
        biggest = max(files, key=lambda x: x.stat().st_size) if files else None
        items.append(
            {
                "run_id": run_id,
                "created_at": None,
                "filename": biggest.name if biggest else None,
                "content_type": None,
                "raw_path": biggest.as_posix() if biggest else None,
                "size_bytes": biggest.stat().st_size if biggest else None,
            }
        )

    items.sort(key=lambda x: (x.get("created_at") or "", x["run_id"]), reverse=True)
    return {"items": items}


@router.get("/uploads/{run_id}")
def get_upload(run_id: str) -> dict[str, Any]:
    uploads_dir = Path(settings.storage_dir) / "uploads" / run_id
    if not uploads_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")

    load_json = Path(settings.storage_dir) / "runs" / run_id / "load.json"
    data: dict[str, Any] = {"run_id": run_id}
    if load_json.exists():
        try:
            data["load"] = read_json(load_json)
        except Exception:
            data["load"] = None

    data["files"] = [
        {
            "name": f.name,
            "path": f.as_posix(),
            "size_bytes": f.stat().st_size,
        }
        for f in uploads_dir.iterdir()
        if f.is_file()
    ]
    return data


@router.delete("/uploads/{run_id}")
def delete_upload(run_id: str) -> dict[str, Any]:
    uploads_dir = Path(settings.storage_dir) / "uploads" / run_id
    runs_dir = Path(settings.storage_dir) / "runs" / run_id
    if not uploads_dir.exists() and not runs_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")

    if uploads_dir.exists():
        shutil.rmtree(uploads_dir, ignore_errors=True)
    if runs_dir.exists():
        shutil.rmtree(runs_dir, ignore_errors=True)
    return {"ok": True, "run_id": run_id}

