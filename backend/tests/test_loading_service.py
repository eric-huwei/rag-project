from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

import fitz

from app.services.loading_service import LoadingService


class LoadingServiceExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_root = Path(__file__).resolve().parent / ".tmp" / uuid.uuid4().hex
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.service = LoadingService(root_dir=self.test_root)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _build_pdf_with_table(self) -> bytes:
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 40), "Before table")

        x0, y0, cell_w, cell_h = 50, 100, 120, 32
        rows, cols = 3, 3
        for row in range(rows + 1):
            y = y0 + row * cell_h
            page.draw_line((x0, y), (x0 + cols * cell_w, y))
        for col in range(cols + 1):
            x = x0 + col * cell_w
            page.draw_line((x, y0), (x, y0 + rows * cell_h))

        values = [
            ["Name", "Qty", "Price"],
            ["Apple", "3", "9.9"],
            ["Banana", "5", "12.5"],
        ]
        for row, row_values in enumerate(values):
            for col, value in enumerate(row_values):
                rect = fitz.Rect(
                    x0 + col * cell_w + 4,
                    y0 + row * cell_h + 4,
                    x0 + (col + 1) * cell_w - 4,
                    y0 + (row + 1) * cell_h - 4,
                )
                page.insert_textbox(rect, value, fontsize=11)

        page.insert_text((50, 240), "After table")
        content = doc.tobytes()
        doc.close()
        return content

    def _build_pdf_with_image(self) -> bytes:
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        page.insert_text((40, 40), "Before image")

        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False)
        pix.clear_with(0x66CC33)
        page.insert_image(fitz.Rect(50, 80, 170, 150), pixmap=pix)

        page.insert_text((40, 220), "After image")
        content = doc.tobytes()
        doc.close()
        return content

    def test_extract_with_pymupdf_bytes_renders_table_as_markdown(self) -> None:
        page_map = self.service._extract_with_pymupdf_bytes(self._build_pdf_with_table())

        self.assertEqual(len(page_map), 1)
        page = page_map[0]
        text = page["text"]

        self.assertIn("Before table", text)
        self.assertIn("|Name|Qty|Price|", text)
        self.assertIn("|Apple|3|9.9|", text)
        self.assertIn("|Banana|5|12.5|", text)
        self.assertIn("After table", text)
        self.assertEqual(text.count("Apple"), 1)
        self.assertEqual(page["metadata"]["table_count"], 1)
        self.assertEqual(page["metadata"]["extraction_mode"], "pymupdf_table_aware")

    def test_clean_strategy_preserves_markdown_table_rows(self) -> None:
        page_map, method = self.service.load_pdf(
            self._build_pdf_with_table(),
            filename="table.pdf",
            loading_method="pymupdf",
            strategy="clean",
        )

        self.assertEqual(method, "pymupdf")
        self.assertIn("|---|---|---|", page_map[0]["text"])
        self.assertIn("Before table", page_map[0]["text"])
        self.assertIn("After table", page_map[0]["text"])

    def test_extract_with_pymupdf_bytes_tracks_images_and_positions(self) -> None:
        page_map = self.service._extract_with_pymupdf_bytes(self._build_pdf_with_image())

        self.assertEqual(len(page_map), 1)
        page = page_map[0]
        text = page["text"]

        self.assertIn("Before image", text)
        self.assertIn("[Image 1: format=png, size=40x30", text)
        self.assertIn("After image", text)
        self.assertEqual(page["metadata"]["image_count"], 1)
        self.assertEqual(page["metadata"]["extraction_mode"], "pymupdf_image_aware")
        self.assertEqual(page["metadata"]["images"][0]["ext"], "png")
        self.assertEqual(page["metadata"]["images"][0]["width"], 40)
        self.assertEqual(page["metadata"]["images"][0]["height"], 30)
        self.assertIn("_images", page)

    def test_persist_page_assets_writes_extracted_images(self) -> None:
        page_map = self.service._extract_with_pymupdf_bytes(self._build_pdf_with_image())

        summary = self.service._persist_page_assets(
            run_id="load_test_assets",
            filename="image.pdf",
            page_map=page_map,
        )

        self.assertEqual(summary["total_images"], 1)
        self.assertTrue(summary["asset_dir"])
        self.assertNotIn("_images", page_map[0])
        image_path = Path(page_map[0]["metadata"]["images"][0]["path"])
        self.assertTrue(image_path.exists())
        self.assertEqual(image_path.suffix.lower(), ".png")


if __name__ == "__main__":
    unittest.main()
