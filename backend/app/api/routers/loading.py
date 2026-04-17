from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.loading_service import get_chunking_config, load_document, load_docs_root_dir

router = APIRouter()


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_documents() -> list[tuple[Path, dict[str, Any]]]:
    root = load_docs_root_dir()
    if not root.exists():
        return []

    docs: list[tuple[Path, dict[str, Any]]] = []
    for p in root.glob("*.json"):
        if not p.is_file():
            continue
        obj = _read_json_file(p)
        if not isinstance(obj, dict):
            continue
        docs.append((p, obj))

    docs.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    return docs


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    loading_method: str = Form("auto"),
    strategy: str | None = Form(None),
    chunking_strategy: str | None = Form(None),
    chunking_options: str | None = Form(None),
) -> dict:
    """
    Upload a document, parse/chunk it, and persist processed JSON.
    """
    try:
        return await load_document(
            file,
            loading_method=loading_method,
            strategy=strategy,
            chunking_strategy=chunking_strategy,
            chunking_options=chunking_options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/chunking-config")
def chunking_config() -> dict[str, Any]:
    return get_chunking_config()


@router.get("/uploads")
def list_uploads() -> dict[str, Any]:
    """
    List uploaded JSON documents from app/01-load-dcos.
    """
    items: list[dict[str, Any]] = []
    for path, obj in _iter_documents():
        md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        items.append(
            {
                "run_id": obj.get("run_id") or path.stem,
                "created_at": md.get("timestamp"),
                "filename": obj.get("filename") or path.name,
                "content_type": None,
                "document_type": md.get("document_type"),
                "json_path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "total_chunks": md.get("total_chunks"),
                "total_pages": md.get("total_pages"),
                "loading_method": md.get("loading_method"),
                "loading_strategy": md.get("loading_strategy"),
                "chunking_strategy": md.get("chunking_strategy"),
            }
        )

    return {"items": items}


@router.get("/uploads/{run_id}")
def get_upload(run_id: str) -> dict[str, Any]:
    for path, obj in _iter_documents():
        if (obj.get("run_id") or path.stem) != run_id:
            continue

        return {
            "run_id": run_id,
            "load": obj,
            "files": [
                {
                    "name": path.name,
                    "path": path.as_posix(),
                    "size_bytes": path.stat().st_size,
                }
            ],
        }

    raise HTTPException(status_code=404, detail="run_id not found")


@router.delete("/uploads/{run_id}")
def delete_upload(run_id: str) -> dict[str, Any]:
    for path, obj in _iter_documents():
        if (obj.get("run_id") or path.stem) != run_id:
            continue

        try:
            path.unlink(missing_ok=True)
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail="file is in use, please retry") from exc
        return {"ok": True, "run_id": run_id}

    raise HTTPException(status_code=404, detail="run_id not found")
