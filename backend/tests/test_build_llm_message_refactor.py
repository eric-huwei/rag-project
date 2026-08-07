from __future__ import annotations

from pathlib import Path
import unittest


def _load_build_llm_message_main():
    backend_dir = Path(__file__).resolve().parents[1]
    source_path = next(
        path
        for path in backend_dir.glob("*llm*.py")
        if not path.name.startswith("llm")
    )
    namespace: dict[str, object] = {}
    exec(source_path.read_text(encoding="utf-8-sig"), namespace)
    return namespace["main"]


class BuildLlmMessageRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = staticmethod(_load_build_llm_message_main())

    def test_spoken_chinese_house_number_is_never_rewritten(self) -> None:
        cases = (
            "闵行区镇江路丽月道三十七号",
            "三十五号",
            "二十号",
            "一百二十七号",
            "三十七室",
        )
        for spoken in cases:
            with self.subTest(spoken=spoken):
                result = self.main(
                    {
                        "userInput": spoken,
                        "state": "matching",
                        "matchedIndex": -1,
                        "kdRecords": ["闵行区镇江路丽月道37号"],
                    }
                )

                self.assertEqual(result["clean_user_input"], spoken)
                self.assertEqual(result["llm_user_input"], spoken)
                self.assertEqual(result["effective_match_input"], spoken)
                self.assertIn(f"User: {spoken}", result["user_message"])
                self.assertIn(spoken, result["history_user_message"])
                self.assertNotIn("三室", str(result))

    def test_chinese_house_number_compares_with_arabic_candidate_without_rewrite(self) -> None:
        result = self.main(
            {
                "userInput": "三十七号",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "丽月道",
                "kdRecords": ["闵行区镇江路丽月道37号"],
            }
        )

        self.assertEqual(result["clean_user_input"], "三十七号")
        self.assertEqual(result["llm_user_input"], "三十七号")
        self.assertEqual(result["effective_match_input"], "丽月道三十七号")
        self.assertEqual(result["possible_merged_input"], "丽月道三十七号")

    def test_homophone_marker_without_candidate_stays_spoken(self) -> None:
        result = self.main(
            {
                "userInput": "3好楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "中山路:",
                "kdRecords": [],
            }
        )

        self.assertEqual(result["clean_user_input"], "3好楼")
        self.assertEqual(result["llm_user_input"], "3好楼")
        self.assertEqual(result["effective_match_input"], "3好楼")
        self.assertEqual(result["possible_merged_input"], "")

    def test_candidate_backed_homophone_marker_can_standardize_merge(self) -> None:
        result = self.main(
            {
                "userInput": "3好楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "中山路:",
                "kdRecords": ["中山路3号楼2101", "中山路3号楼2102"],
            }
        )

        self.assertEqual(result["clean_user_input"], "3好楼")
        self.assertEqual(result["llm_user_input"], "3好楼")
        self.assertEqual(result["effective_match_input"], "中山路3号楼")
        self.assertEqual(result["possible_merged_input"], "中山路3号楼")
        self.assertIn("User: 3好楼", result["user_message"])

    def test_candidate_number_conflict_does_not_force_marker_correction(self) -> None:
        result = self.main(
            {
                "userInput": "3好楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "中山路:",
                "kdRecords": ["中山路8号楼2101"],
            }
        )

        self.assertEqual(result["clean_user_input"], "3好楼")
        self.assertEqual(result["effective_match_input"], "3好楼")
        self.assertEqual(result["possible_merged_input"], "")

    def test_candidate_backed_named_place_correction_does_not_change_user_field(self) -> None:
        result = self.main(
            {
                "userInput": "芳景小区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "世安新城",
                "kdRecords": [
                    "福建漳州云霄县莆美镇世安新城方景小区352",
                    "福建漳州云霄县南阳路福宁小区123",
                ],
            }
        )

        self.assertEqual(result["clean_user_input"], "芳景小区")
        self.assertEqual(result["llm_user_input"], "芳景小区")
        self.assertEqual(result["effective_match_input"], "世安新城方景小区")


if __name__ == "__main__":
    unittest.main()
