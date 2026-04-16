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


def _parse_strategy_flags(raw: str | None) -> set[str]:
    if not raw:
        return set()
    flags: set[str] = set()
    for token in re.split(r"[\s,|+/]+", raw):
        normalized = token.strip().lower().replace("-", "_")
        if normalized:
            flags.add(normalized)
    return flags


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
        asset_summary = self._persist_page_assets(run_id=run_id, filename=filename, page_map=page_map)
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
            "total_images": asset_summary["total_images"],
            "asset_dir": asset_summary["asset_dir"],
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
            "total_images": document_data.get("metadata", {}).get("total_images"),
            "asset_dir": document_data.get("metadata", {}).get("asset_dir"),
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
        strategy_flags = _parse_strategy_flags(strategy)
        clean_output = "clean" in strategy_flags
        table_aware = not bool({"legacy", "plain_text", "text_only"} & strategy_flags)
        image_aware = not bool({"no_images", "skip_images", "text_only"} & strategy_flags)
        ext = Path(filename).suffix.lower()
        is_pdf = ext == ".pdf"
        aliases = {
            "pdf": "pymupdf",
            "default": "auto",
            "fitz": "pymupdf",
            "plain": "text",
            "unstructured": "pymupdf",
        }
        method = aliases.get(method, method)

        if method in {"", "auto"}:
            method = "pymupdf" if is_pdf else "text"
        elif is_pdf and method == "text":
            # For PDF, plain text decode usually creates binary gibberish.
            method = "pymupdf"

        if method == "pymupdf":
            try:
                page_map = self._extract_with_pymupdf_bytes(
                    content,
                    table_aware=table_aware,
                    image_aware=image_aware,
                )
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
                    page_map = self._extract_with_pymupdf_bytes(
                        content,
                        table_aware=table_aware,
                        image_aware=image_aware,
                    )
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
                    page_map = self._extract_with_pymupdf_bytes(
                        content,
                        table_aware=table_aware,
                        image_aware=image_aware,
                    )
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

        if clean_output:
            for p in page_map:
                p["text"] = self._clean_extracted_text(str(p.get("text", "") or ""))
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

    def _extract_with_pymupdf_bytes(
        self,
        content: bytes,
        *,
        table_aware: bool = True,
        image_aware: bool = True,
    ) -> list[dict[str, Any]]:
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError("pymupdf is not installed") from exc

        pages: list[dict[str, Any]] = []
        doc = fitz.open(stream=content, filetype="pdf")
        try:
            for idx, page in enumerate(doc, start=1):
                pages.append(
                    self._extract_pymupdf_page(
                        page,
                        page_number=idx,
                        table_aware=table_aware,
                        image_aware=image_aware,
                    )
                )
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

    def _extract_pymupdf_page(
        self,
        page: Any,
        *,
        page_number: int,
        table_aware: bool,
        image_aware: bool,
    ) -> dict[str, Any]:
        plain_text = str(page.get_text("text", sort=True) or page.get_text("text") or "")
        metadata: dict[str, Any] = {
            "table_count": 0,
            "image_count": 0,
            "extraction_mode": "pymupdf_sorted_text",
        }

        if not table_aware and not image_aware:
            return {"page": page_number, "text": plain_text, "metadata": metadata}

        tables = self._detect_tables(page) if table_aware else []
        images = self._extract_image_segments(page) if image_aware else []
        if not tables and not images:
            return {"page": page_number, "text": plain_text, "metadata": metadata}

        text_blocks = self._extract_text_blocks(page)
        merged_text = self._merge_page_segments(text_blocks, tables=tables, images=images)
        metadata.update(
            {
                "table_count": len(tables),
                "image_count": len(images),
                "images": [self._image_public_metadata(image) for image in images],
                "text_block_count": len(text_blocks),
                "extraction_mode": self._resolve_extraction_mode(tables=tables, images=images),
            }
        )
        page_data = {
            "page": page_number,
            "text": merged_text or plain_text,
            "metadata": metadata,
        }
        if images:
            page_data["_images"] = images
        return page_data

    def _detect_tables(self, page: Any) -> list[dict[str, Any]]:
        if not hasattr(page, "find_tables"):
            return []

        tables = self._collect_tables(page)
        if tables:
            return tables

        return self._collect_tables(
            page,
            vertical_strategy="text",
            horizontal_strategy="text",
            min_words_vertical=2,
            min_words_horizontal=1,
        )

    def _collect_tables(self, page: Any, **find_kwargs: Any) -> list[dict[str, Any]]:
        try:
            finder = page.find_tables(**find_kwargs)
        except Exception:
            return []

        out: list[dict[str, Any]] = []
        for table_index, table in enumerate(getattr(finder, "tables", []) or [], start=1):
            segment = self._table_to_segment(table, table_index=table_index)
            if segment is not None:
                out.append(segment)
        return out

    def _table_to_segment(self, table: Any, *, table_index: int) -> dict[str, Any] | None:
        row_count = int(getattr(table, "row_count", 0) or 0)
        col_count = int(getattr(table, "col_count", 0) or 0)
        if row_count < 2 or col_count < 2:
            return None

        try:
            cells = table.extract()
        except Exception:
            cells = []

        if cells and not self._looks_like_table(cells):
            return None

        try:
            markdown = str(table.to_markdown(fill_empty=True) or "").strip()
        except Exception:
            markdown = self._table_cells_to_markdown(cells)

        if not markdown:
            return None

        return {
            "bbox": tuple(float(v) for v in table.bbox),
            "text": markdown,
            "row_count": row_count,
            "col_count": col_count,
            "table_number": table_index,
        }

    def _looks_like_table(self, rows: list[list[Any]]) -> bool:
        filled_rows = 0
        non_empty_cells = 0
        for row in rows:
            if not isinstance(row, list):
                continue
            filled = sum(1 for cell in row if _normalize_whitespace(str(cell or "")))
            non_empty_cells += filled
            if filled >= 2:
                filled_rows += 1
        return filled_rows >= 2 and non_empty_cells >= 4

    def _table_cells_to_markdown(self, rows: list[list[Any]]) -> str:
        normalized_rows: list[list[str]] = []
        max_cols = 0
        for row in rows:
            normalized_row = [_normalize_whitespace(str(cell or "")) for cell in row]
            if any(normalized_row):
                normalized_rows.append(normalized_row)
                max_cols = max(max_cols, len(normalized_row))

        if not normalized_rows or max_cols == 0:
            return ""

        padded_rows = [row + [""] * (max_cols - len(row)) for row in normalized_rows]
        header = [cell or f"Col{idx + 1}" for idx, cell in enumerate(padded_rows[0])]
        lines = [
            "|" + "|".join(header) + "|",
            "|" + "|".join("---" for _ in range(max_cols)) + "|",
        ]
        for row in padded_rows[1:]:
            lines.append("|" + "|".join(row) + "|")
        return "\n".join(lines).strip()

    def _extract_image_segments(self, page: Any) -> list[dict[str, Any]]:
        page_dict = page.get_text("dict", sort=True) or {}
        blocks = page_dict.get("blocks") if isinstance(page_dict, dict) else []
        if not isinstance(blocks, list):
            return []

        images: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for block in blocks:
            if not isinstance(block, dict) or int(block.get("type", -1)) != 1:
                continue

            bbox_raw = block.get("bbox")
            if not isinstance(bbox_raw, (list, tuple)) or len(bbox_raw) != 4:
                continue

            bbox = tuple(float(v) for v in bbox_raw)
            width = int(block.get("width", 0) or 0)
            height = int(block.get("height", 0) or 0)
            ext = str(block.get("ext") or "png").lower()
            image_bytes = block.get("image")
            image_size = len(image_bytes) if isinstance(image_bytes, (bytes, bytearray)) else int(block.get("size", 0) or 0)

            dedupe_key = (
                round(bbox[0], 1),
                round(bbox[1], 1),
                round(bbox[2], 1),
                round(bbox[3], 1),
                width,
                height,
                ext,
                image_size,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            image_number = len(images) + 1
            image = {
                "bbox": bbox,
                "text": self._format_image_placeholder(
                    image_number=image_number,
                    ext=ext,
                    width=width,
                    height=height,
                    bbox=bbox,
                ),
                "kind": "image",
                "image_number": image_number,
                "ext": ext,
                "width": width,
                "height": height,
                "xres": int(block.get("xres", 0) or 0),
                "yres": int(block.get("yres", 0) or 0),
                "colorspace": int(block.get("colorspace", 0) or 0),
                "bpc": int(block.get("bpc", 0) or 0),
                "size_bytes": image_size,
            }
            if isinstance(image_bytes, (bytes, bytearray)):
                image["bytes"] = bytes(image_bytes)
            images.append(image)

        return images

    def _format_image_placeholder(
        self,
        *,
        image_number: int,
        ext: str,
        width: int,
        height: int,
        bbox: tuple[float, float, float, float],
    ) -> str:
        return (
            f"[Image {image_number}: format={ext}, size={width}x{height}, "
            f"bbox=({bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f})]"
        )

    def _image_public_metadata(self, image: dict[str, Any]) -> dict[str, Any]:
        return {
            "image_number": image.get("image_number"),
            "ext": image.get("ext"),
            "width": image.get("width"),
            "height": image.get("height"),
            "bbox": list(image.get("bbox") or ()),
            "xres": image.get("xres"),
            "yres": image.get("yres"),
            "colorspace": image.get("colorspace"),
            "bpc": image.get("bpc"),
            "size_bytes": image.get("size_bytes"),
        }

    def _resolve_extraction_mode(
        self,
        *,
        tables: list[dict[str, Any]],
        images: list[dict[str, Any]],
    ) -> str:
        if tables and images:
            return "pymupdf_table_image_aware"
        if tables:
            return "pymupdf_table_aware"
        if images:
            return "pymupdf_image_aware"
        return "pymupdf_sorted_text"

    def _extract_text_blocks(self, page: Any) -> list[dict[str, Any]]:
        blocks = page.get_text("blocks", sort=True) or []
        out: list[dict[str, Any]] = []
        for block in blocks:
            if len(block) < 7:
                continue
            x0, y0, x1, y1, text, _block_no, block_type = block[:7]
            if int(block_type) != 0:
                continue
            cleaned = _normalize_whitespace(str(text or ""))
            if not cleaned:
                continue
            out.append(
                {
                    "bbox": (float(x0), float(y0), float(x1), float(y1)),
                    "text": cleaned,
                    "kind": "text",
                }
            )
        return out

    def _merge_page_segments(
        self,
        text_blocks: list[dict[str, Any]],
        *,
        tables: list[dict[str, Any]],
        images: list[dict[str, Any]],
    ) -> str:
        segments: list[dict[str, Any]] = []

        for block in text_blocks:
            if self._segment_overlaps_table(block.get("bbox"), tables):
                continue
            segments.append(block)

        for table in tables:
            segments.append(
                {
                    "bbox": table["bbox"],
                    "text": table["text"],
                    "kind": "table",
                }
            )

        for image in images:
            segments.append(
                {
                    "bbox": image["bbox"],
                    "text": image["text"],
                    "kind": "image",
                }
            )

        segments.sort(
            key=lambda item: (
                item["bbox"][1],
                item["bbox"][0],
                self._segment_kind_priority(str(item.get("kind") or "")),
            )
        )

        pieces = [str(item.get("text", "") or "").strip() for item in segments]
        return "\n\n".join(piece for piece in pieces if piece).strip()

    def _segment_kind_priority(self, kind: str) -> int:
        priorities = {
            "text": 0,
            "table": 1,
            "image": 2,
        }
        return priorities.get(kind, 9)

    def _segment_overlaps_table(
        self,
        bbox: Any,
        tables: list[dict[str, Any]],
    ) -> bool:
        if not isinstance(bbox, tuple) or len(bbox) != 4:
            return False

        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        for table in tables:
            table_bbox = table.get("bbox")
            if not isinstance(table_bbox, tuple) or len(table_bbox) != 4:
                continue
            if self._bbox_contains_point(table_bbox, center_x, center_y):
                return True
            if self._bbox_overlap_ratio(bbox, table_bbox) >= 0.3:
                return True
        return False

    def _bbox_contains_point(
        self,
        bbox: tuple[float, float, float, float],
        x: float,
        y: float,
    ) -> bool:
        return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]

    def _bbox_overlap_ratio(
        self,
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> float:
        inter_left = max(left[0], right[0])
        inter_top = max(left[1], right[1])
        inter_right = min(left[2], right[2])
        inter_bottom = min(left[3], right[3])
        if inter_right <= inter_left or inter_bottom <= inter_top:
            return 0.0

        inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
        left_area = max(1.0, (left[2] - left[0]) * (left[3] - left[1]))
        right_area = max(1.0, (right[2] - right[0]) * (right[3] - right[1]))
        return inter_area / min(left_area, right_area)

    def _clean_extracted_text(self, text: str) -> str:
        if not re.search(r"(?m)^\|.*\|$", text):
            return _normalize_whitespace(text)

        lines: list[str] = []
        last_blank = False
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                if lines and not last_blank:
                    lines.append("")
                last_blank = True
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                lines.append(re.sub(r"[ \t]+", " ", stripped))
            else:
                lines.append(_normalize_whitespace(stripped))
            last_blank = False

        return "\n".join(lines).strip()

    def _persist_page_assets(
        self,
        *,
        run_id: str,
        filename: str,
        page_map: list[dict[str, Any]],
    ) -> dict[str, Any]:
        total_images = 0
        asset_dir: Path | None = None
        stem = Path(filename).stem or "document"

        for page in page_map:
            metadata = page.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                page["metadata"] = metadata

            private_images = page.pop("_images", [])
            if not isinstance(private_images, list) or not private_images:
                metadata["image_count"] = int(metadata.get("image_count", 0) or 0)
                continue

            public_images: list[dict[str, Any]] = []
            for image in private_images:
                if not isinstance(image, dict):
                    continue
                public_image = self._image_public_metadata(image)
                image_bytes = image.get("bytes")
                image_ext = str(image.get("ext") or "png").lower()
                image_number = int(image.get("image_number", len(public_images) + 1) or len(public_images) + 1)
                if isinstance(image_bytes, bytes):
                    if asset_dir is None:
                        asset_dir = self.root_dir / "assets" / run_id
                        asset_dir.mkdir(parents=True, exist_ok=True)
                    image_name = _safe_filename(
                        f"{stem}_p{page.get('page', 1)}_img{image_number}.{image_ext}",
                        f"image_{image_number}.{image_ext}",
                    )
                    image_path = asset_dir / image_name
                    image_path.write_bytes(image_bytes)
                    public_image["path"] = image_path.as_posix()
                public_images.append(public_image)

            metadata["images"] = public_images
            metadata["image_count"] = len(public_images)
            total_images += len(public_images)

        return {
            "total_images": total_images,
            "asset_dir": asset_dir.as_posix() if asset_dir is not None else None,
        }

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

