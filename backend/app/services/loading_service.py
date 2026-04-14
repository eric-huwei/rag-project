from __future__ import annotations

from io import BytesIO
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

def load_docs_root_dir() -> Path:
    # Directory at the same level as app/services: app/01-load-dcos
    return Path(__file__).resolve().parent.parent / "01-load-dcos"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id(prefix: str = "load") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{ts}_{uuid.uuid4().hex[:8]}"


def _safe_filename(filename: str | None, default_name: str) -> str:
    candidate = Path(filename or default_name).name
    if not candidate:
        return default_name
    # Windows-illegal chars: <>:"/\|?* and control chars.
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", candidate).strip().rstrip(". ")
    return cleaned or default_name


def _parse_chunking_options(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text == "[object Object]":
        # Common FormData mistake from frontend: object appended directly.
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Keep endpoint tolerant; ignore invalid options instead of hard-failing.
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class LoadingService:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or load_docs_root_dir()
        self._page_map: list[dict[str, Any]] = []

    async def load(
        self,
        file: UploadFile,
        *,
        loading_method: str | None,
        strategy: str | None = None,
        chunking_strategy: str | None = None,
        chunking_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = _new_run_id("load")
        filename = _safe_filename(file.filename, "upload.bin")
        self.root_dir.mkdir(parents=True, exist_ok=True)

        await file.seek(0)
        content = await file.read()

        page_map, resolved_loading_method = self.load_pdf(
            content,
            filename=filename,
            loading_method=loading_method,
            strategy=strategy,
        )
        self._page_map = page_map
        chunks = self.build_chunks(
            page_map,
            chunking_strategy=chunking_strategy,
            chunking_options=chunking_options,
        )
        metadata = {
            "filename": filename,
            "total_chunks": len(chunks),
            "total_pages": self.get_total_pages(),
            "loading_method": resolved_loading_method,
            "loading_strategy": strategy,
            "chunking_strategy": chunking_strategy or "by_page",
            "timestamp": _utc_now_iso(),
        }
        filepath = self.save_document(
            run_id=run_id,
            filename=filename,
            chunks=chunks,
            metadata=metadata,
            loading_method=resolved_loading_method,
            strategy=strategy,
            chunking_strategy=chunking_strategy,
        )
        document_data = json.loads(filepath.read_text(encoding="utf-8"))

        payload = {
            "filename": filename,
            "content_type": file.content_type,
            "json_path": filepath.as_posix(),
            "size_bytes": filepath.stat().st_size,
            "total_chunks": document_data.get("metadata", {}).get("total_chunks"),
            "total_pages": document_data.get("metadata", {}).get("total_pages"),
            "loading_method": resolved_loading_method,
            "loading_strategy": strategy,
            "chunking_strategy": chunking_strategy or "by_page",
            "created_at": _utc_now_iso(),
        }
        return {
            "run_id": run_id,
            "loaded_content": document_data,
            "filepath": filepath.as_posix(),
            "result": payload,
        }

    def load_pdf(
        self,
        content: bytes,
        *,
        filename: str,
        loading_method: str | None,
        strategy: str | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        method = (loading_method or "auto").strip().lower()
        ext = Path(filename).suffix.lower()
        is_pdf = ext == ".pdf"
        aliases = {
            "pdf": "pymupdf",
            "default": "auto",
            "fitz": "pymupdf",
            "plain": "text",
        }
        method = aliases.get(method, method)

        if method in {"", "auto"}:
            method = "pymupdf" if is_pdf else "text"
        elif is_pdf and method == "text":
            # For PDF, plain text decode usually creates binary gibberish.
            method = "pymupdf"

        if method == "pymupdf":
            try:
                page_map = self._extract_with_pymupdf_bytes(content)
            except Exception:
                try:
                    page_map = self._extract_with_pypdf_bytes(content)
                    method = "pypdf"
                except Exception:
                    page_map = self._extract_as_text_from_bytes(content, binary_hint=is_pdf)
                    method = "text"
        elif method == "pypdf":
            try:
                page_map = self._extract_with_pypdf_bytes(content)
            except Exception:
                try:
                    page_map = self._extract_with_pymupdf_bytes(content)
                    method = "pymupdf"
                except Exception:
                    page_map = self._extract_as_text_from_bytes(content, binary_hint=is_pdf)
                    method = "text"
        elif method == "text":
            page_map = self._extract_as_text_from_bytes(content, binary_hint=is_pdf)
        else:
            # Unknown method from old/new frontend values: fallback gracefully.
            if is_pdf:
                try:
                    page_map = self._extract_with_pymupdf_bytes(content)
                    method = "pymupdf"
                except Exception:
                    try:
                        page_map = self._extract_with_pypdf_bytes(content)
                        method = "pypdf"
                    except Exception:
                        page_map = self._extract_as_text_from_bytes(content, binary_hint=True)
                        method = "text"
            else:
                page_map = self._extract_as_text_from_bytes(content)
                method = "text"

        if (strategy or "").strip().lower() == "clean":
            for p in page_map:
                p["text"] = _normalize_whitespace(p.get("text", ""))
        return page_map, method

    def _extract_with_pypdf_bytes(self, content: bytes) -> list[dict[str, Any]]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("pypdf is not installed") from exc

        reader = PdfReader(BytesIO(content))
        pages: list[dict[str, Any]] = []
        for idx, page in enumerate(reader.pages, start=1):
            pages.append({"page": idx, "text": page.extract_text() or ""})
        return pages

    def _extract_with_pymupdf_bytes(self, content: bytes) -> list[dict[str, Any]]:
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError("pymupdf is not installed") from exc

        pages: list[dict[str, Any]] = []
        doc = fitz.open(stream=content, filetype="pdf")
        try:
            for idx, page in enumerate(doc, start=1):
                pages.append({"page": idx, "text": page.get_text("text") or ""})
        finally:
            doc.close()
        return pages

    def _extract_as_text_from_bytes(
        self,
        content: bytes,
        *,
        binary_hint: bool = False,
    ) -> list[dict[str, Any]]:
        if binary_hint:
            # Avoid returning noisy binary gibberish for binary formats like PDF.
            return [{"page": 1, "text": ""}]
        return [{"page": 1, "text": content.decode("utf-8", errors="ignore")}]

    def get_total_pages(self) -> int:
        return len(self._page_map)

    def get_page_map(self) -> list[dict[str, Any]]:
        return list(self._page_map)

    def build_chunks(
        self,
        page_map: list[dict[str, Any]],
        *,
        chunking_strategy: str | None = None,
        chunking_options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        strategy = (chunking_strategy or "by_page").strip().lower()
        opts = chunking_options or {}
        chunks: list[dict[str, Any]] = []

        if strategy == "fixed_size":
            chunk_size = int(opts.get("chunk_size", 400))
            overlap = int(opts.get("overlap", 50))
            chunk_id = 1
            for page in page_map:
                page_number = int(page.get("page", 1))
                page_text = str(page.get("text", "") or "")
                for piece in self._split_fixed_size(page_text, chunk_size, overlap):
                    chunks.append(
                        {
                            "content": piece,
                            "metadata": {
                                "chunk_id": chunk_id,
                                "page_number": page_number,
                                "page_range": str(page_number),
                                "word_count": len(piece.split()),
                            },
                        }
                    )
                    chunk_id += 1
            return chunks

        if strategy == "sentence":
            max_chars = int(opts.get("max_chars", 1200))
            chunk_id = 1
            for page in page_map:
                page_number = int(page.get("page", 1))
                page_text = str(page.get("text", "") or "")
                for piece in self._split_sentence(page_text, max_chars):
                    chunks.append(
                        {
                            "content": piece,
                            "metadata": {
                                "chunk_id": chunk_id,
                                "page_number": page_number,
                                "page_range": str(page_number),
                                "word_count": len(piece.split()),
                            },
                        }
                    )
                    chunk_id += 1
            return chunks

        # Default strategy: one chunk per page.
        for idx, page in enumerate(page_map, 1):
            text = str(page.get("text", "") or "")
            page_number = int(page.get("page", idx))
            chunk_metadata = {
                "chunk_id": idx,
                "page_number": page_number,
                "page_range": str(page_number),
                "word_count": len(text.split()),
            }
            if isinstance(page.get("metadata"), dict):
                chunk_metadata.update(page["metadata"])
            chunks.append({"content": text, "metadata": chunk_metadata})
        return chunks

    def _split_fixed_size(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        words = text.split()
        if not words:
            return []
        safe_chunk_size = max(1, chunk_size)
        safe_overlap = max(0, min(overlap, safe_chunk_size - 1))
        step = max(1, safe_chunk_size - safe_overlap)
        out: list[str] = []
        for start in range(0, len(words), step):
            piece_words = words[start : start + safe_chunk_size]
            if not piece_words:
                continue
            out.append(" ".join(piece_words))
            if start + safe_chunk_size >= len(words):
                break
        return out

    def _split_sentence(self, text: str, max_chars: int) -> list[str]:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            return []
        out: list[str] = []
        current: list[str] = []
        current_len = 0
        safe_max = max(100, max_chars)
        for sent in sentences:
            sent_len = len(sent)
            if current and current_len + 1 + sent_len > safe_max:
                out.append(" ".join(current))
                current = [sent]
                current_len = sent_len
            else:
                current.append(sent)
                current_len += sent_len if current_len == 0 else sent_len + 1
        if current:
            out.append(" ".join(current))
        return out

    def save_document(
        self,
        *,
        run_id: str,
        filename: str,
        chunks: list[dict[str, Any]],
        metadata: dict[str, Any],
        loading_method: str,
        strategy: str | None = None,
        chunking_strategy: str | None = None,
    ) -> Path:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        out = {
            "run_id": run_id,
            "filename": filename,
            "metadata": {
                **metadata,
                "total_chunks": len(chunks),
                "loading_method": loading_method,
                "loading_strategy": strategy,
                "chunking_strategy": chunking_strategy or "by_page",
            },
            "chunks": chunks,
        }
        json_name = f"{Path(filename).stem or 'document'}.json"
        out_path = self.root_dir / _safe_filename(json_name, "document.json")
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path


loading_service = LoadingService()


async def load_document(
    file: UploadFile,
    *,
    loading_method: str | None = None,
    strategy: str | None = None,
    chunking_strategy: str | None = None,
    chunking_options: str | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible function wrapper used by router modules.
    """
    parsed_chunking_options = _parse_chunking_options(chunking_options)
    return await loading_service.load(
        file,
        loading_method=loading_method,
        strategy=strategy,
        chunking_strategy=chunking_strategy,
        chunking_options=parsed_chunking_options,
    )

