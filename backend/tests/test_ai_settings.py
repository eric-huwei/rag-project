from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core import config
from app.services.ai_service import AIService


class AISettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = (Path(__file__).resolve().parent / ".tmp").resolve()
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = tempfile.TemporaryDirectory(dir=self.tmp_root)
        self.test_root = Path(self.tmp_dir.name).resolve()
        self.config_file = self.test_root / ".env"

    def tearDown(self) -> None:
        self.assertTrue(self.test_root.is_relative_to(self.tmp_root))
        self.tmp_dir.cleanup()

    def _load_settings(self) -> config.Settings:
        with patch.object(config, "CONFIG_FILE", self.config_file):
            return config.load_settings()

    def test_file_configuration_ignores_process_environment(self) -> None:
        self.config_file.write_text(
            "AI_API_KEY=file-key\n"
            "AI_BASE_URL=https://file.example/v1\n"
            "AI_MODEL=file-model\n",
            encoding="utf-8",
        )
        conflicting_env = {
            "GOOD_AI": "legacy-good-key",
            "ALIAI_API_KEY": "legacy-aliai-key",
            "AI_API_KEY": "environment-key",
            "AI_BASE_URL": "https://environment.example/v1",
            "AI_MODEL": "environment-model",
        }
        with patch.dict(os.environ, conflicting_env):
            settings = self._load_settings()

        self.assertEqual(settings.ai_api_key, "file-key")
        self.assertEqual(settings.ai_base_url, "https://file.example/v1")
        self.assertEqual(settings.ai_model, "file-model")

    def test_missing_file_does_not_fall_back_to_environment(self) -> None:
        with patch.dict(os.environ, {"AI_API_KEY": "environment-key"}):
            settings = self._load_settings()

        self.assertEqual(settings.ai_api_key, "")
        self.assertEqual(settings.ai_base_url, "")
        self.assertEqual(settings.ai_model, "")

    def test_file_values_are_not_interpolated_from_environment(self) -> None:
        self.config_file.write_text(
            "AI_API_KEY=${AI_API_KEY}\n", encoding="utf-8"
        )
        with patch.dict(os.environ, {"AI_API_KEY": "environment-key"}):
            settings = self._load_settings()

        self.assertEqual(settings.ai_api_key, "${AI_API_KEY}")

    def test_config_file_is_fixed_to_backend_directory(self) -> None:
        self.assertEqual(
            config.CONFIG_FILE,
            Path(__file__).resolve().parents[1] / ".env",
        )

    def test_incomplete_configuration_does_not_call_provider(self) -> None:
        incomplete_settings = config.Settings(ai_api_key="file-key")
        service = AIService()
        with patch("app.services.ai_service.settings", incomplete_settings):
            with patch.object(service, "_create_completion") as create_completion:
                with self.assertRaisesRegex(
                    RuntimeError, r"backend/\.env.*AI_BASE_URL, AI_MODEL"
                ):
                    service.ask(call_id="test-call", content="test-content")
                create_completion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
