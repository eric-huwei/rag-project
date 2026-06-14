from __future__ import annotations

import json
from pathlib import Path
import unittest


def _load_code_main(predicate):
    workflow_path = next(Path(__file__).resolve().parents[1].glob("*.json"))
    workflow = json.loads(workflow_path.read_text(encoding="utf-8-sig"))

    code_blocks: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("key") == "code" and isinstance(node.get("value"), str):
                code_blocks.append(node["value"])
            for value in node.values():
                walk(value)
            return

        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(workflow)

    for code in code_blocks:
        if not predicate(code):
            continue

        namespace: dict[str, object] = {}
        exec(code, namespace)
        return namespace["main"]

    raise AssertionError("workflow code block not found")


def _load_address_postprocess_main():
    return _load_code_main(
        lambda code: (
            "from difflib import SequenceMatcher" in code
            and "last_unmatched_address" in code
        )
    )


def _load_build_output_main():
    return _load_code_main(
        lambda code: (
            "CONFIRM_REPLY_TEMPLATE" in code
            and "matched_account" in code
            and "user_spoken_address" in code
        )
    )


def _load_final_output_code():
    workflow_path = next(Path(__file__).resolve().parents[1].glob("*.json"))
    workflow = json.loads(workflow_path.read_text(encoding="utf-8-sig"))

    code_blocks: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("key") == "code" and isinstance(node.get("value"), str):
                code_blocks.append(node["value"])
            for value in node.values():
                walk(value)
            return

        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(workflow)

    for code in code_blocks:
        if "function main({ data })" in code and "IsEnd" in code:
            return code

    raise AssertionError("final output code block not found")


def _load_build_llm_message_main():
    return _load_code_main(
        lambda code: (
            "import re" in code
            and "import json" in code
            and "candidates_info=" in code
            and "get_base_community" in code
        )
    )


def _load_build_llm_message_file_main():
    source_path = Path(__file__).resolve().parents[1] / "构建llm消息.py"
    namespace: dict[str, object] = {}
    exec(source_path.read_text(encoding="utf-8-sig"), namespace)
    return namespace["main"]


def _load_workflow_state_main():
    return _load_code_main(
        lambda code: (
            "# 后处理状态" in code
            and "cleanHistory" in code
            and "match_failed" in code
        )
    )


class AddressExtractionWorkflowTests(unittest.TestCase):
    def test_town_level_address_echoes_on_first_followup(self) -> None:
        main = _load_address_postprocess_main()
        town = "\u6c64\u6c60\u9547"
        layer_reply = (
            "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684"
            "\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        )
        expected_reply = (
            "\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a"
            "\u6c64\u6c60\u9547\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684"
            "\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        )

        result = main(
            llm_result={
                "match_count": 0,
                "matched_index": -1,
                "is_completed": False,
                "is_extract_failed": False,
                "reply": layer_reply,
            },
            meaningless_result={},
            state="matching",
            matched_index=-1,
            clean_user_input=town,
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[],
        )

        self.assertEqual(result["llm_result"]["reply"], expected_reply)
        self.assertEqual(result["next_last_unmatched_address"], town)
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_empty_optional_state_fields_match_omitted_fields(self) -> None:
        main = _load_address_postprocess_main()
        town = "\u6c64\u6c60\u9547"
        layer_reply = (
            "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684"
            "\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        )
        addresses = [
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf\u6c64\u6c60"
            "\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109",
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf\u6c64\u6c60"
            "\u9547\u767e\u82b1\u5c0f\u533a9\u680b1110",
        ]
        base_payload = {
            "matched_index": 0,
            "meaningless_result": {"is_meaningless": False, "reply": ""},
            "llm_result": {
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": layer_reply,
                "is_extract_failed": False,
            },
            "clean_user_input": town,
            "address_list": addresses,
        }

        omitted_result = main(**base_payload)
        explicit_empty_result = main(
            **{
                **base_payload,
                "state": "",
                "last_unmatched_address": "",
                "similar_no_match_count": None,
            }
        )

        self.assertEqual(omitted_result, explicit_empty_result)
        self.assertEqual(
            omitted_result["llm_result"]["reply"],
            (
                "\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a"
                "\u6c64\u6c60\u9547\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b"
                "\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
            ),
        )

    def test_confirm_reply_uses_user_spoken_address_not_full_match(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": (
                    "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
                    "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109"
                ),
            },
            llm_result={"match_count": 1, "reply": ""},
            user_spoken_address="\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109",
        )

        self.assertEqual(
            result["reply"],
            "\u8bf7\u95ee\u60a8\u8bf4\u7684\u662f"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109\u5417\uff1f",
        )
        self.assertEqual(
            result["matched_account"],
            (
                "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
                "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109"
            ),
        )

    def test_confirm_reply_merges_previous_place_with_current_building_room(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": "中山路3号楼2101",
            },
            llm_result={"match_count": 1, "reply": ""},
            user_spoken_address="3号楼2101",
            clean_user_input="3号楼2101",
            last_unmatched_address="中山路:",
        )

        self.assertEqual(result["reply"], "请问您说的是中山路:3号楼2101吗？")
        self.assertEqual(result["matched_account"], "中山路3号楼2101")

    def test_confirm_reply_merges_current_named_place_with_previous_building_room(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": "福州市岳峰镇保利香槟国际东区三号楼1201",
            },
            llm_result={"match_count": 1, "reply": ""},
            user_spoken_address="保利香槟",
            clean_user_input="保利香槟",
            last_unmatched_address="三号楼1201",
        )

        self.assertEqual(result["reply"], "请问您说的是三号楼1201保利香槟吗？")
        self.assertEqual(result["matched_account"], "福州市岳峰镇保利香槟国际东区三号楼1201")

    def test_match_failed_output_uses_short_terminal_reply(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": True,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result={"reply": ""},
        )

        self.assertEqual(result["reply"], "\u62b1\u6b49\u60a8\u63d0\u4f9b\u7684\u5730\u5740\u4e0d\u6b63\u786e\u3002")

        final_output_code = _load_final_output_code()
        self.assertIn('content: isFailed ? failedReply : reply', final_output_code)
        self.assertIn('IsEnd: isFailed ? "-1"', final_output_code)
        self.assertNotIn('startsWith("请问您说的是")', final_output_code)

    def test_confirming_irrelevant_input_repeats_previous_confirm_address(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": "福州市岳峰镇保利香槟国际东区三号楼1201",
            },
            llm_result={"match_count": 1, "reply": ""},
            user_spoken_address="数据量时间段",
            clean_user_input="数据量时间段",
            last_unmatched_address="",
        )

        self.assertEqual(result["reply"], "请问您说的是保利香槟国际东区三号楼1201吗？")

    def test_confirming_overlapping_partial_fragment_reuses_previous_confirm_phrase(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": "福州市岳峰镇保利香槟国际东区三号楼1201",
            },
            llm_result={"match_count": 1, "reply": ""},
            user_spoken_address="3号楼",
            clean_user_input="3号楼",
            last_unmatched_address="",
        )

        self.assertEqual(result["reply"], "请问您说的是1201保利香槟国际吗？")

    def test_confirming_overlapping_building_appends_to_previous_confirm_phrase(self) -> None:
        main = _load_build_output_main()

        result = main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": "福州市岳峰镇保利香槟国际东区三号楼1201",
            },
            llm_result={"match_count": 1, "reply": ""},
            user_spoken_address="3号楼",
            clean_user_input="3号楼",
            last_unmatched_address="__NO_MERGE__:1201保利香槟国际",
        )

        self.assertEqual(result["reply"], "请问您说的是1201保利香槟国际3号楼吗？")

    def test_completed_user_says_wrong_restarts_with_layer_reply(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再重新说一下报修宽带所在小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="completed",
            matched_index=0,
            clean_user_input="错了",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state="completed")
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address="错了",
            clean_user_input="错了",
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(third_state["state"], "matching")
        self.assertEqual(third_output["reply"], "好的，请您再说一下具体的小区或村镇名称。")

    def test_build_llm_message_keeps_full_clean_address_and_base_address(self) -> None:
        main = _load_build_llm_message_main()

        result = main(
            {
                "userInput": "汤池镇百花小区9栋1109",
                "state": "confirming",
                "matchedIndex": 0,
                "kdRecords": [
                    "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                ],
            }
        )

        self.assertIn(
            '"clean_address": "安徽省合肥市庐江县汤池镇百花小区9栋1109"',
            result["user_message"],
        )
        self.assertIn(
            '"base_address": "安徽省合肥市庐江县汤池镇百花小区"',
            result["user_message"],
        )

    def test_build_llm_message_merges_named_place_with_previous_building_room(self) -> None:
        main = _load_build_llm_message_main()

        result = main(
            {
                "userInput": "保利香槟",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "三号楼1201",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "福州市岳峰镇保利香槟国际东区三号楼1201",
                    "福州市岳峰镇保利香槟国际东区三号楼1200",
                ],
            }
        )

        self.assertIn("User: 保利香槟", result["user_message"])
        self.assertIn("last_unmatched_address=三号楼1201", result["user_message"])
        self.assertIn("本轮 User 只表示 clean_user_input", result["user_message"])
        self.assertEqual(result["llm_user_input"], "保利香槟")
        self.assertEqual(result["effective_match_input"], "三号楼1201保利香槟")

    def test_build_llm_message_keeps_east_area_after_room_number(self) -> None:
        main = _load_build_llm_message_main()

        result = main(
            {
                "userInput": "保利香槟",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "三号楼1201东区",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "福州市岳峰镇保利香槟国际东区三号楼1201",
                    "福州市岳峰镇保利香槟国际东区三号楼1200",
                ],
            }
        )

        self.assertIn("User: 保利香槟", result["user_message"])
        self.assertIn("last_unmatched_address=三号楼1201东区", result["user_message"])
        self.assertEqual(result["llm_user_input"], "保利香槟")
        self.assertEqual(result["effective_match_input"], "三号楼1201东区保利香槟")
        self.assertNotIn("1201栋区", result["user_message"])

    def test_build_llm_message_does_not_merge_terms_from_different_candidates(self) -> None:
        main = _load_build_llm_message_main()

        result = main(
            {
                "userInput": "保利香槟",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "中山路",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "中山路3号楼2101",
                    "福州市岳峰镇保利香槟国际东区三号楼1201",
                ],
            }
        )

        self.assertEqual(result["effective_match_input"], "保利香槟")
        self.assertNotIn("User: 中山路保利香槟", result["user_message"])

    def test_build_llm_message_does_not_force_ambiguous_phonetic_correction(self) -> None:
        main = _load_build_llm_message_main()

        result = main(
            {
                "userInput": "普美镇",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "1201",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "福建漳州云霄县莆美镇福湾小区8号楼1201",
                    "福建漳州云霄县普美镇福湾小区8号楼1201",
                ],
            }
        )

        self.assertEqual(result["effective_match_input"], "普美镇")
        self.assertNotIn("1201莆美镇", result["user_message"])

    def test_intro_noise_and_candidate_suffix_are_stripped_from_recorded_followup(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        built = build_llm_message_main(
            {
                "userInput": "我住在福州市岳峰镇保利香槟国际",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "",
                "similar_no_match_count": 0,
                "kdRecords": addresses,
            }
        )

        self.assertEqual(built["clean_user_input"], "福州市岳峰镇保利香槟国际")
        self.assertEqual(built["effective_match_input"], "福州市岳峰镇保利香槟国际")
        self.assertNotIn("我住在", built["user_message"])
        self.assertIn("\nUser: 福州市岳峰镇保利香槟国际", built["user_message"])
        self.assertNotIn("\nUser: 福州市岳峰镇保利香槟国际东区", built["user_message"])

        located_by_candidate = build_llm_message_main(
            {
                "userInput": "麻烦帮我查一下福州市岳峰镇保利香槟国际",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "",
                "similar_no_match_count": 0,
                "kdRecords": addresses,
            }
        )

        self.assertEqual(located_by_candidate["clean_user_input"], "福州市岳峰镇保利香槟国际")
        self.assertNotIn("麻烦", located_by_candidate["user_message"])

        omitted_middle_candidate_text = build_llm_message_main(
            {
                "userInput": "麻烦查一下保利香槟3号楼1200",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "",
                "similar_no_match_count": 0,
                "kdRecords": addresses,
            }
        )

        self.assertEqual(omitted_middle_candidate_text["clean_user_input"], "保利香槟3号楼1200")
        self.assertIn("\nUser: 保利香槟3号楼1200", omitted_middle_candidate_text["user_message"])
        self.assertNotIn("user-spoken scope: 保利香槟国际东区", omitted_middle_candidate_text["user_message"])
        self.assertNotIn("\nUser: 保利香槟国际东区", omitted_middle_candidate_text["user_message"])
        self.assertNotIn("麻烦", omitted_middle_candidate_text["user_message"])

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "我记录的地址信息是：福州市岳峰镇保利香槟国际东区，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=built["effective_match_input"],
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：福州市岳峰镇保利香槟国际，请您再说一下具体的楼栋号、单元号及门牌号。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "福州市岳峰镇保利香槟国际")

    def test_case_five_named_place_followup_matches_after_premerge(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        built = build_llm_message_main(
            {
                "userInput": "保利香槟",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "三号楼1201",
                "similar_no_match_count": 1,
                "kdRecords": addresses,
            }
        )

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=built["effective_match_input"],
            last_unmatched_address="三号楼1201",
            similar_no_match_count=1,
            address_list=addresses,
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)

        output = build_output_main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 0,
                "matched_account": "福州市岳峰镇保利香槟国际东区三号楼1201",
            },
            llm_result=result["llm_result"],
            user_spoken_address=built["effective_match_input"],
            clean_user_input=built["clean_user_input"],
            last_unmatched_address="",
        )

        self.assertEqual(output["reply"], "请问您说的是三号楼1201保利香槟吗？")
        self.assertEqual(output["matched_account"], "福州市岳峰镇保利香槟国际东区三号楼1201")

    def test_case_six_room_followup_after_building_keeps_recorded_address(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        built = build_llm_message_main(
            {
                "userInput": "1201",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "三号楼",
                "similar_no_match_count": 1,
                "kdRecords": addresses,
            }
        )

        self.assertEqual(built["effective_match_input"], "三号楼1201")

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=built["effective_match_input"],
            last_unmatched_address="三号楼",
            similar_no_match_count=1,
            address_list=addresses,
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "三号楼1201")

        output = build_output_main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=result["llm_result"],
            user_spoken_address=built["effective_match_input"],
            clean_user_input=built["clean_user_input"],
            last_unmatched_address=result["next_last_unmatched_address"],
        )

        self.assertEqual(
            output["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )

    def test_case_six_room_followup_after_building_demotes_llm_unique_match(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        built = build_llm_message_main(
            {
                "userInput": "1201",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "三号楼",
                "similar_no_match_count": 1,
                "kdRecords": addresses,
            }
        )

        result = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=built["effective_match_input"],
            last_unmatched_address="三号楼",
            similar_no_match_count=1,
            address_list=addresses,
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )

        output = build_output_main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=result["llm_result"],
            user_spoken_address=built["effective_match_input"],
            clean_user_input=built["clean_user_input"],
            last_unmatched_address=result["next_last_unmatched_address"],
        )

        self.assertEqual(
            output["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )

    def test_precise_candidate_suffix_match_overrides_llm_no_match(self) -> None:
        main = _load_address_postprocess_main()
        user_address = "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109"
        addresses = [
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109",
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1110",
        ]

        result = main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u8bf7\u60a8\u63d0\u4f9b\u6b63\u786e\u5b8c\u6574\u7684\u5730\u5740\u4fe1\u606f",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=0,
            clean_user_input=user_address,
            address_list=addresses,
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            f"__NO_MERGE__:{user_address}",
        )

    def test_precise_room_conflict_overrides_llm_wrong_unique_match(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        result = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="州市鼓楼区保利香槟国际8号楼2101",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福建省福州市鼓楼区中山路保利香槟国际八号楼2103",
                "福建省福州市鼓楼区中山路保利香槟国际八号楼2101",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 1)
        self.assertEqual(result["llm_result"]["match_count"], 1)

        output = build_output_main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "confirming",
                "matched_index": 1,
                "matched_account": "福建省福州市鼓楼区中山路保利香槟国际八号楼2101",
            },
            llm_result=result["llm_result"],
            user_spoken_address="福州市鼓楼区保利香槟国际8号楼2101",
            clean_user_input="州市鼓楼区保利香槟国际8号楼2101",
        )

        self.assertEqual(output["matched_account"], "福建省福州市鼓楼区中山路保利香槟国际八号楼2101")
        self.assertEqual(output["reply"], "请问您说的是福州市鼓楼区保利香槟国际8号楼2101吗？")

    def test_broad_town_suffix_does_not_override_llm_no_match(self) -> None:
        main = _load_address_postprocess_main()
        town = "\u6c64\u6c60\u9547"
        addresses = [
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109",
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1110",
        ]

        result = main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684"
                "\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=0,
            clean_user_input=town,
            address_list=addresses,
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertIn(town, result["llm_result"]["reply"])

    def test_town_level_followup_is_merged_but_not_matched_until_village_level(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福建漳州云霄县莆美镇大埔村352",
            "福建漳州云霄县常山农场树洞村123",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="云霄县",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：云霄县，请您再说一下具体的小区或村镇名称。",
        )

        second_built = build_llm_message_main(
            {
                "userInput": "普美镇",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(second_turn["llm_result"]["matched_index"], -1)
        self.assertEqual(second_turn["llm_result"]["match_count"], 0)
        self.assertEqual(
            second_turn["llm_result"]["reply"],
            "我记录的地址信息是：云霄县莆美镇，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(second_turn["next_last_unmatched_address"], "云霄县莆美镇")

        third_built = build_llm_message_main(
            {
                "userInput": "大埔村",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(third_built["effective_match_input"], "云霄县莆美镇大埔村")

        third_turn = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state="matching")
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address=third_built["effective_match_input"],
            clean_user_input=third_built["clean_user_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(third_state["state"], "confirming")
        self.assertEqual(third_output["reply"], "请问您说的是云霄县莆美镇大埔村吗？")
        self.assertTrue(third_turn["next_last_unmatched_address"].startswith("__NO_MERGE__:"))

        fourth_built = build_llm_message_main(
            {
                "userInput": "叫阿里克斯酱豆腐教室",
                "state": third_state["state"],
                "matchedIndex": third_state["matched_index"],
                "last_unmatched_address": third_turn["next_last_unmatched_address"],
                "similar_no_match_count": third_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        fourth_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": True, "reply": "请直接回答是或者不是。"},
            state=third_state["state"],
            matched_index=third_state["matched_index"],
            clean_user_input=fourth_built["effective_match_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
            similar_no_match_count=third_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        fourth_state = state_main(fourth_turn["llm_result"], address=addresses, state=third_state["state"])
        fourth_output = build_output_main(
            data=fourth_state,
            llm_result=fourth_turn["llm_result"],
            user_spoken_address=fourth_built["effective_match_input"],
            clean_user_input=fourth_built["clean_user_input"],
            last_unmatched_address=fourth_turn["next_last_unmatched_address"],
        )

        self.assertEqual(fourth_output["reply"], third_output["reply"])
        self.assertNotIn("352", fourth_output["reply"])

        fifth_built = build_llm_message_main(
            {
                "userInput": "352",
                "state": fourth_state["state"],
                "matchedIndex": fourth_state["matched_index"],
                "last_unmatched_address": fourth_turn["next_last_unmatched_address"],
                "similar_no_match_count": fourth_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        fifth_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=fourth_state["state"],
            matched_index=fourth_state["matched_index"],
            clean_user_input=fifth_built["effective_match_input"],
            last_unmatched_address=fourth_turn["next_last_unmatched_address"],
            similar_no_match_count=fourth_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        fifth_state = state_main(fifth_turn["llm_result"], address=addresses, state=fourth_state["state"])
        fifth_output = build_output_main(
            data=fifth_state,
            llm_result=fifth_turn["llm_result"],
            user_spoken_address=fifth_built["effective_match_input"],
            clean_user_input=fifth_built["clean_user_input"],
            last_unmatched_address=fifth_turn["next_last_unmatched_address"],
        )

        self.assertEqual(fifth_state["state"], "confirming")
        self.assertEqual(fifth_output["reply"], "请问您说的是云霄县莆美镇大埔村352吗？")
        self.assertNotIn("352大埔村", fifth_output["reply"])

    def test_city_district_road_house_does_not_confirm_unspoken_place_detail(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = ["福建三明龙溪城区东三路4号香江悦府1幢1层401"]
        turns = [
            ("三明", "我记录的地址信息是：三明，请您再说一下具体的小区或村镇名称。"),
            ("龙溪城区", "我记录的地址信息是：三明龙溪城区，请您再说一下具体的小区或村镇名称。"),
            ("东三路", "我记录的地址信息是：三明龙溪城区东三路，请您再说一下具体的小区或村镇名称。"),
            ("4号", "我记录的地址信息是：三明龙溪城区东三路4号，请您再说一下具体的小区或村镇名称。"),
        ]

        state = "matching"
        matched_index = -1
        last_unmatched = ""
        similar_count = 0

        for user_input, expected_reply in turns:
            built = build_llm_message_main(
                {
                    "userInput": user_input,
                    "state": state,
                    "matchedIndex": matched_index,
                    "last_unmatched_address": last_unmatched,
                    "similar_no_match_count": similar_count,
                    "kdRecords": addresses,
                }
            )
            llm_result = {
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            }
            if user_input == "4号":
                llm_result = {
                    "matched_index": 0,
                    "match_count": 1,
                    "is_completed": False,
                    "reply": "",
                    "is_extract_failed": False,
                }

            post = postprocess_main(
                llm_result=llm_result,
                meaningless_result={"is_meaningless": False, "reply": ""},
                state=state,
                matched_index=matched_index,
                clean_user_input=built["effective_match_input"],
                last_unmatched_address=last_unmatched,
                similar_no_match_count=similar_count,
                address_list=addresses,
            )
            data = state_main(post["llm_result"], address=addresses, state=state)
            output = build_output_main(
                data=data,
                llm_result=post["llm_result"],
                user_spoken_address=built["effective_match_input"],
                clean_user_input=built["clean_user_input"],
                last_unmatched_address=post["next_last_unmatched_address"],
            )

            self.assertEqual(output["reply"], expected_reply)
            state = data["state"]
            matched_index = data["matched_index"]
            last_unmatched = post["next_last_unmatched_address"]
            similar_count = post["next_similar_no_match_count"]

    def test_beijing_prefix_from_candidate_is_not_spoken_in_recorded_or_confirm_reply(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "北京市朝阳区建国路88号现代城5号楼1单元101室",
            "北京市朝阳区建国路88号现代城5号楼1单元105室",
        ]
        turns = [
            (
                "朝阳区",
                {
                    "matched_index": -1,
                    "match_count": 0,
                    "is_completed": False,
                    "reply": "好的，请您再说一下具体的小区或村镇名称。",
                    "is_extract_failed": False,
                },
                "我记录的地址信息是：朝阳区，请您再说一下具体的小区或村镇名称。",
            ),
            (
                "建国路88号",
                {
                    "matched_index": -1,
                    "match_count": 0,
                    "is_completed": False,
                    "reply": "我记录的地址信息是：北京市朝阳区建国路88号，请您再说一下具体的小区或村镇名称。",
                    "is_extract_failed": False,
                },
                "我记录的地址信息是：朝阳区建国路88号，请您再说一下具体的小区或村镇名称。",
            ),
            (
                "现代城",
                {
                    "matched_index": -1,
                    "match_count": 0,
                    "is_completed": False,
                    "reply": "我记录的地址信息是：北京市朝阳区建国路88号现代城，请您再说一下具体的楼栋号、单元号及门牌号。",
                    "is_extract_failed": False,
                },
                "我记录的地址信息是：朝阳区建国路88号现代城，请您再说一下具体的楼栋号、单元号及门牌号。",
            ),
            (
                "5号楼",
                {
                    "matched_index": -1,
                    "match_count": 0,
                    "is_completed": False,
                    "reply": "我记录的地址信息是：北京市朝阳区建国路88号现代城5号楼，请您再说一下具体的单元号及门牌号。",
                    "is_extract_failed": False,
                },
                "我记录的地址信息是：朝阳区建国路88号现代城5号楼，请您再说一下具体的单元号及门牌号。",
            ),
            (
                "1单元101室",
                {
                    "matched_index": 0,
                    "match_count": 1,
                    "is_completed": False,
                    "reply": "",
                    "is_extract_failed": False,
                },
                "请问您说的是朝阳区建国路88号现代城5号楼1单元101室吗？",
            ),
        ]

        state = "matching"
        matched_index = -1
        last_unmatched = ""
        similar_count = 0

        for user_input, llm_result, expected_reply in turns:
            built = build_llm_message_main(
                {
                    "userInput": user_input,
                    "state": state,
                    "matchedIndex": matched_index,
                    "last_unmatched_address": last_unmatched,
                    "similar_no_match_count": similar_count,
                    "kdRecords": addresses,
                }
            )
            post = postprocess_main(
                llm_result=llm_result,
                meaningless_result={"is_meaningless": False, "reply": ""},
                state=state,
                matched_index=matched_index,
                clean_user_input=built["effective_match_input"],
                last_unmatched_address=last_unmatched,
                similar_no_match_count=similar_count,
                address_list=addresses,
            )
            data = state_main(post["llm_result"], address=addresses, state=state)
            output = build_output_main(
                data=data,
                llm_result=post["llm_result"],
                user_spoken_address=built["effective_match_input"],
                clean_user_input=built["clean_user_input"],
                last_unmatched_address=post["next_last_unmatched_address"],
            )

            self.assertEqual(output["reply"], expected_reply)
            self.assertNotIn("北京市", output["reply"])
            state = data["state"]
            matched_index = data["matched_index"]
            last_unmatched = post["next_last_unmatched_address"]
            similar_count = post["next_similar_no_match_count"]

    def test_confirming_denial_with_trailing_word_does_not_count_as_mismatch(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="保利香槟国际3号楼1200",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        first_state = state_main(first_turn["llm_result"], address=addresses, state="matching")
        first_output = build_output_main(
            data=first_state,
            llm_result=first_turn["llm_result"],
            user_spoken_address="保利香槟国际3号楼1200",
            clean_user_input="保利香槟国际3号楼1200",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
        )

        self.assertEqual(first_output["reply"], "请问您说的是保利香槟国际3号楼1200吗？")

        second_built = build_llm_message_main(
            {
                "userInput": "不是后",
                "state": first_state["state"],
                "matchedIndex": first_state["matched_index"],
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(second_built["effective_match_input"], "不是后")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=first_state["state"],
            matched_index=first_state["matched_index"],
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state=first_state["state"])
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_output["reply"], "请您提供详细的地址信息")
        self.assertEqual(second_turn["next_similar_no_match_count"], 0)

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=second_state["state"],
            matched_index=second_state["matched_index"],
            clean_user_input="三号楼1201",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state=second_state["state"])
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address="三号楼1201",
            clean_user_input="三号楼1201",
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(third_state["state"], "matching")
        self.assertEqual(
            third_output["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )

    def test_confirming_plain_denial_restarts_matching_without_counting_mismatch(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_built = build_llm_message_main(
            {
                "userInput": "保利香槟国际3号楼1200",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "",
                "similar_no_match_count": 0,
                "kdRecords": addresses,
            }
        )

        first_turn = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=first_built["effective_match_input"],
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        first_state = state_main(first_turn["llm_result"], address=addresses, state="matching")
        first_output = build_output_main(
            data=first_state,
            llm_result=first_turn["llm_result"],
            user_spoken_address=first_built["effective_match_input"],
            clean_user_input=first_built["clean_user_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
        )

        self.assertEqual(first_state["state"], "confirming")
        self.assertEqual(first_output["reply"], "请问您说的是保利香槟国际3号楼1200吗？")

        second_built = build_llm_message_main(
            {
                "userInput": "不是",
                "state": first_state["state"],
                "matchedIndex": first_state["matched_index"],
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(second_built["effective_match_input"], "不是")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再重新说一下报修宽带所在小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=first_state["state"],
            matched_index=first_state["matched_index"],
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=0,
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state=first_state["state"])
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_state["state"], "matching")
        self.assertEqual(second_output["reply"], "请您提供详细的地址信息")
        self.assertEqual(second_turn["next_similar_no_match_count"], 0)

        third_built = build_llm_message_main(
            {
                "userInput": "三号楼1201",
                "state": second_state["state"],
                "matchedIndex": second_state["matched_index"],
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=second_state["state"],
            matched_index=second_state["matched_index"],
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state=second_state["state"])
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address=third_built["effective_match_input"],
            clean_user_input=third_built["clean_user_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(third_state["state"], "matching")
        self.assertEqual(
            third_output["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )

    def test_place_less_building_room_llm_unique_match_is_demoted_to_followup(self) -> None:
        main = _load_address_postprocess_main()

        result = main(
            llm_result={
                "matched_index": 1,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="8号楼2102",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：8号楼2102，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "8号楼2102")
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_equivalent_building_markers_still_reject_unspoken_place(self) -> None:
        main = _load_address_postprocess_main()
        address_list = [
            "\u79fb\u673a\u8d3950\u5143\u5c71\u897f\u592a\u539f\u5e02\u5c16\u8349\u576a\u533a\u5367\u864e\u5c71\u8def\u67cf\u7fe0\u82d11\u53f7\u697c5\u5355\u5143202\u5ba4",
            "\u5c71\u897f\u592a\u539f\u5e02\u5c16\u8349\u576a\u533a\u5367\u864e\u5c71\u8def\u67cf\u7fe0\u82d14\u53f7\u697c2\u5355\u5143102\u5ba4",
            "\u79fb\u673a\u8d3950\u5143\u5c71\u897f\u592a\u539f\u5e02\u5c16\u8349\u576a\u533a\u6c5f\u9633\u5546\u4e1a\u8857\u6c5f\u9633\u5316\u5de5\u5382100\u53f7\u697c1\u5355\u5143302\u5ba4",
        ]

        for clean_user_input in (
            "\u4e00\u767e\u697c\u4e00\u5355\u5143\u4e09\u96f6\u4e8c",
            "100\u680b1\u5355\u5143302\u5ba4",
            "100\u53f71\u5355\u5143302\u5ba4",
        ):
            with self.subTest(clean_user_input=clean_user_input):
                result = main(
                    llm_result={
                        "matched_index": 2,
                        "match_count": 1,
                        "is_completed": False,
                        "reply": "",
                        "is_extract_failed": False,
                    },
                    meaningless_result={"is_meaningless": False, "reply": ""},
                    state="matching",
                    matched_index=-1,
                    clean_user_input=clean_user_input,
                    last_unmatched_address="",
                    similar_no_match_count=0,
                    address_list=address_list,
                )

                self.assertEqual(result["llm_result"]["matched_index"], -1)
                self.assertEqual(result["llm_result"]["match_count"], 0)
                self.assertEqual(
                    result["llm_result"]["reply"],
                    f"我记录的地址信息是：{clean_user_input}，请您再说一下具体的小区或村镇名称。",
                )
                self.assertEqual(result["next_last_unmatched_address"], clean_user_input)
                self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_llm_unique_match_still_rejects_different_building_number(self) -> None:
        main = _load_address_postprocess_main()

        result = main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="101\u697c1\u5355\u5143302\u5ba4",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "\u5c71\u897f\u592a\u539f\u5e02\u5c16\u8349\u576a\u533a\u6c5f\u9633\u5316\u5de5\u5382100\u53f7\u697c1\u5355\u5143302\u5ba4",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)

    def test_building_without_room_requests_only_room_number(self) -> None:
        main = _load_address_postprocess_main()

        result = main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="中山路八号楼",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：中山路八号楼，请您再提供下门牌号信息",
        )
        self.assertEqual(result["next_last_unmatched_address"], "中山路八号楼")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_room_number_fragment_with_candidate_overlap_records_and_requests_place(self) -> None:
        main = _load_address_postprocess_main()

        result = main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="2103",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：2103，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "2103")
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_building_fragment_after_room_number_keeps_combined_recorded_address(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "广东省深圳市中山路八号楼2103",
            "广东省深圳市中山路八号楼2102",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="2103",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="八号楼",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            "我记录的地址信息是：2103八号楼，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(second_turn["next_last_unmatched_address"], "2103八号楼")
        self.assertEqual(second_turn["next_similar_no_match_count"], 1)

        output = build_output_main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=second_turn["llm_result"],
            user_spoken_address="八号楼",
            clean_user_input="八号楼",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(
            output["reply"],
            "我记录的地址信息是：2103八号楼，请您再说一下具体的小区或村镇名称。",
        )

    def test_build_llm_message_merges_weak_area_fragment_with_previous_overlap_address(self) -> None:
        main = _load_build_llm_message_main()

        result = main(
            {
                "userInput": "东区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "1201三号楼",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "福州市岳峰镇保利香槟国际东区三号楼1201",
                    "福州市岳峰镇保利香槟国际东区三号楼1200",
                ],
            }
        )

        self.assertIn("User: 东区", result["user_message"])
        self.assertIn("last_unmatched_address=1201三号楼", result["user_message"])
        self.assertEqual(result["llm_user_input"], "东区")
        self.assertEqual(result["possible_merged_input"], "1201三号楼东区")
        self.assertEqual(result["effective_match_input"], "1201三号楼东区")

    def test_overlap_fragments_keep_concatenating_across_three_turns(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="1201",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：1201，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(first_turn["next_last_unmatched_address"], "1201")

        second_built = build_llm_message_main(
            {
                "userInput": "三号楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(second_built["effective_match_input"], "1201三号楼")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            "我记录的地址信息是：1201三号楼，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(second_turn["next_last_unmatched_address"], "1201三号楼")

        third_built = build_llm_message_main(
            {
                "userInput": "东区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(third_built["effective_match_input"], "1201三号楼东区")

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            third_turn["llm_result"]["reply"],
            "我记录的地址信息是：1201三号楼东区，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(third_turn["next_last_unmatched_address"], "1201三号楼东区")

        output = build_output_main(
            data={
                "match_failed": False,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=third_turn["llm_result"],
            user_spoken_address=third_built["effective_match_input"],
            clean_user_input=third_built["clean_user_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(
            output["reply"],
            "我记录的地址信息是：1201三号楼东区，请您再说一下具体的小区或村镇名称。",
        )

    def test_non_overlapping_weak_area_does_not_merge_but_later_overlap_fragments_do(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="1200",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：1200，请您再说一下具体的小区或村镇名称。",
        )

        second_built = build_llm_message_main(
            {
                "userInput": "三号楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )
        self.assertEqual(second_built["effective_match_input"], "1200三号楼")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            "我记录的地址信息是：1200三号楼，请您再说一下具体的小区或村镇名称。",
        )

        third_built = build_llm_message_main(
            {
                "userInput": "南区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )
        self.assertEqual(third_built["effective_match_input"], "南区")

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            third_turn["llm_result"]["reply"],
            "我记录的地址信息是：1200三号楼，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(third_turn["next_last_unmatched_address"], "1200三号楼")

        fourth_built = build_llm_message_main(
            {
                "userInput": "东区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": third_turn["next_last_unmatched_address"],
                "similar_no_match_count": third_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )
        self.assertEqual(fourth_built["effective_match_input"], "1200三号楼东区")

        fourth_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=fourth_built["effective_match_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
            similar_no_match_count=third_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            fourth_turn["llm_result"]["reply"],
            "我记录的地址信息是：1200三号楼东区，请您再说一下具体的小区或村镇名称。",
        )

        fifth_built = build_llm_message_main(
            {
                "userInput": "保利香槟国际",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": fourth_turn["next_last_unmatched_address"],
                "similar_no_match_count": fourth_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )
        self.assertEqual(fifth_built["effective_match_input"], "1200三号楼东区保利香槟国际")

        fifth_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=fifth_built["effective_match_input"],
            last_unmatched_address=fourth_turn["next_last_unmatched_address"],
            similar_no_match_count=fourth_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(fifth_turn["llm_result"]["matched_index"], 1)
        self.assertEqual(fifth_turn["llm_result"]["match_count"], 1)

        fifth_state = state_main(fifth_turn["llm_result"], address=addresses, state="matching")
        fifth_output = build_output_main(
            data=fifth_state,
            llm_result=fifth_turn["llm_result"],
            user_spoken_address=fifth_built["effective_match_input"],
            clean_user_input=fifth_built["clean_user_input"],
            last_unmatched_address=fifth_turn["next_last_unmatched_address"],
        )

        self.assertEqual(
            fifth_output["reply"],
            "请问您说的是1200三号楼东区保利香槟国际吗？",
        )

        sixth_built = build_llm_message_main(
            {
                "userInput": "责令咖啡教室砥砺奋进",
                "state": fifth_state["state"],
                "matchedIndex": fifth_state["matched_index"],
                "last_unmatched_address": fifth_turn["next_last_unmatched_address"],
                "similar_no_match_count": fifth_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        sixth_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=fifth_state["state"],
            matched_index=fifth_state["matched_index"],
            clean_user_input=sixth_built["effective_match_input"],
            last_unmatched_address=fifth_turn["next_last_unmatched_address"],
            similar_no_match_count=fifth_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        sixth_state = state_main(sixth_turn["llm_result"], address=addresses, state=fifth_state["state"])
        sixth_output = build_output_main(
            data=sixth_state,
            llm_result=sixth_turn["llm_result"],
            user_spoken_address=sixth_built["effective_match_input"],
            clean_user_input=sixth_built["clean_user_input"],
            last_unmatched_address=sixth_turn["next_last_unmatched_address"],
        )

        self.assertEqual(sixth_output["reply"], fifth_output["reply"])

    def test_confirming_overlap_followup_keeps_previous_confirm_reply(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="1201",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        second_built = build_llm_message_main(
            {
                "userInput": "保利香槟国际",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state="matching")
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_output["reply"], "请问您说的是1201保利香槟国际吗？")

        third_built = build_llm_message_main(
            {
                "userInput": "3号楼",
                "state": second_state["state"],
                "matchedIndex": second_state["matched_index"],
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state=second_state["state"],
            matched_index=second_state["matched_index"],
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state=second_state["state"])
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address=third_built["effective_match_input"],
            clean_user_input=third_built["clean_user_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(third_state["state"], "confirming")
        self.assertEqual(third_state["matched_index"], 0)
        self.assertEqual(third_output["reply"], "请问您说的是1201保利香槟国际3号楼吗？")

    def test_confirming_irrelevant_followup_keeps_previous_spoken_confirm_reply(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="三号楼1201",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        second_built = build_llm_message_main(
            {
                "userInput": "保利香槟",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(second_built["effective_match_input"], "三号楼1201保利香槟")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state="matching")
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_output["reply"], "请问您说的是三号楼1201保利香槟吗？")
        self.assertTrue(second_turn["next_last_unmatched_address"].startswith("__NO_MERGE__:"))

        third_built = build_llm_message_main(
            {
                "userInput": "哈哈哈哈",
                "state": second_state["state"],
                "matchedIndex": second_state["matched_index"],
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": True, "reply": "请直接回答是或者不是。"},
            state=second_state["state"],
            matched_index=second_state["matched_index"],
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state=second_state["state"])
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address=third_built["effective_match_input"],
            clean_user_input=third_built["clean_user_input"],
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(third_output["reply"], second_output["reply"])

    def test_unrelated_followups_keep_previous_recorded_reply_then_fail(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "广东省深圳市中山路八号楼2103",
            "广东省深圳市中山路八号楼2102",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="中山路八号楼",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：中山路八号楼，请您再提供下门牌号信息",
        )
        self.assertEqual(first_turn["next_last_unmatched_address"], "中山路八号楼")
        self.assertEqual(first_turn["next_similar_no_match_count"], 0)

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="3333",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            first_turn["llm_result"]["reply"],
        )
        self.assertEqual(second_turn["next_last_unmatched_address"], first_turn["next_last_unmatched_address"])
        self.assertEqual(second_turn["next_similar_no_match_count"], 1)


    def test_build_llm_message_does_not_premerge_unrelated_room_followup(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "广东省深圳市中山路八号楼2103",
            "广东省深圳市中山路八号楼2102",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="中山路八号楼",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        second_built = build_llm_message_main(
            {
                "userInput": "3333",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(second_built["effective_match_input"], "3333")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            first_turn["llm_result"]["reply"],
        )
        self.assertEqual(
            second_turn["next_last_unmatched_address"],
            first_turn["next_last_unmatched_address"],
        )
        self.assertEqual(second_turn["next_similar_no_match_count"], 1)

    def test_road_only_then_building_room_confirms_combined_address(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()
        state_main = _load_workflow_state_main()

        addresses = [
            "中山路3号楼2101",
            "中山路3号楼2102",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="中山路:",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：中山路:，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(first_turn["next_last_unmatched_address"], "中山路:")

        second_built = build_llm_message_main(
            {
                "userInput": "3号楼2101",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(second_built["effective_match_input"], "中山路3号楼2101")
        self.assertEqual(second_turn["llm_result"]["matched_index"], 0)
        self.assertEqual(second_turn["llm_result"]["match_count"], 1)

        second_state = state_main(second_turn["llm_result"], address=addresses, state="matching")
        output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(output["reply"], "请问您说的是中山路3号楼2101吗？")

    def test_road_only_then_homophone_building_fragment_still_merges(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()

        addresses = [
            "中山路3号楼2101",
            "中山路3号楼2102",
        ]

        built = build_llm_message_main(
            {
                "userInput": "3好楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "中山路:",
                "similar_no_match_count": 1,
                "kdRecords": addresses,
            }
        )

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=built["effective_match_input"],
            last_unmatched_address="中山路:",
            similar_no_match_count=1,
            address_list=addresses,
        )

        self.assertEqual(built["effective_match_input"], "中山路3号楼")
        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：中山路3号楼，请您再提供下门牌号信息",
        )

    def test_non_matching_room_fragment_after_building_keeps_previous_followup(self) -> None:
        postprocess_main = _load_address_postprocess_main()

        addresses = [
            "中山路3号楼2101",
            "中山路3号楼2102",
        ]

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="1203",
            last_unmatched_address="中山路3号楼",
            similar_no_match_count=1,
            address_list=addresses,
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：中山路3号楼，请您再提供下门牌号信息",
        )
        self.assertEqual(result["next_last_unmatched_address"], "中山路3号楼")
        self.assertEqual(result["next_similar_no_match_count"], 2)

    def test_full_precise_unmatched_address_requests_correct_complete_info(self) -> None:
        main = _load_address_postprocess_main()
        user_address = "\u5317\u4eac\u5e02\u5927\u540c\u533a\u767e\u82b1\u5c0f\u533a9\u680b1109"
        addresses = [
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109",
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1119",
        ]

        result = main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684"
                "\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=user_address,
            address_list=addresses,
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(
            result["llm_result"]["reply"],
            "\u8bf7\u60a8\u63d0\u4f9b\u6b63\u786e\u5b8c\u6574\u7684\u5730\u5740\u4fe1\u606f",
        )
        self.assertEqual(result["next_last_unmatched_address"], user_address)

    def test_model_reply_is_ignored_when_fragment_conflicts_with_candidates(self) -> None:
        main = _load_address_postprocess_main()
        user_address = "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109"
        recorded_reply = (
            "\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109\uff0c"
            "\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684"
            "\u5355\u5143\u53f7\u53ca\u95e8\u724c\u53f7\u3002"
        )

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": recorded_reply,
                "is_extract_failed": False,
                "matched_address_fragment": user_address,
            },
            clean_user_input=user_address,
            last_unmatched_address="\u6c64\u6c60\u9547",
            similar_no_match_count=1,
            address_list=[
                "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
                "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1019",
                "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
                "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1020",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(result["llm_result"]["reply"], "\u8bf7\u60a8\u63d0\u4f9b\u6b63\u786e\u5b8c\u6574\u7684\u5730\u5740\u4fe1\u606f")
        self.assertEqual(result["next_last_unmatched_address"], user_address)

    def test_repeating_recorded_no_match_address_triggers_extract_failed(self) -> None:
        main = _load_address_postprocess_main()
        user_address = "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109"

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u8bf7\u60a8\u63d0\u4f9b\u8be6\u7ec6\u7684\u5730\u5740\u4fe1\u606f",
                "is_extract_failed": False,
            },
            clean_user_input=user_address,
            last_unmatched_address=user_address,
            similar_no_match_count=1,
            address_list=[
                "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
                "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1019",
                "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
                "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1020",
            ],
        )

        self.assertTrue(result["llm_result"]["is_extract_failed"])
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(result["next_last_unmatched_address"], "")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_same_recorded_no_match_address_increments_before_failure(self) -> None:
        main = _load_address_postprocess_main()
        user_address = "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1109"
        addresses = [
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1019",
            "\u5b89\u5fbd\u7701\u5408\u80a5\u5e02\u5e90\u6c5f\u53bf"
            "\u6c64\u6c60\u9547\u767e\u82b1\u5c0f\u533a9\u680b1020",
        ]

        first_turn = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u8bf7\u60a8\u63d0\u4f9b\u8be6\u7ec6\u7684\u5730\u5740\u4fe1\u606f",
                "is_extract_failed": False,
            },
            clean_user_input=user_address,
            last_unmatched_address=user_address,
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertFalse(first_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(first_turn["next_last_unmatched_address"], user_address)
        self.assertEqual(first_turn["next_similar_no_match_count"], 1)

        second_turn = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u8bf7\u60a8\u63d0\u4f9b\u8be6\u7ec6\u7684\u5730\u5740\u4fe1\u606f",
                "is_extract_failed": False,
            },
            clean_user_input=user_address,
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertTrue(second_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(second_turn["next_last_unmatched_address"], "")
        self.assertEqual(second_turn["next_similar_no_match_count"], 0)

    def test_repeated_meaningless_matching_input_counts_and_fails(self) -> None:
        main = _load_address_postprocess_main()
        addresses = [
            "\u798f\u5dde\u5e02\u5cb3\u5cf0\u9547\u4fdd\u5229\u9999\u69df\u56fd\u9645\u4e1c\u533a\u4e09\u53f7\u697c1201",
            "\u798f\u5dde\u5e02\u5cb3\u5cf0\u9547\u4fdd\u5229\u9999\u69df\u56fd\u9645\u4e1c\u533a\u4e09\u53f7\u697c1200",
        ]

        first_turn = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": True, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u8bf7\u60a8\u63d0\u4f9b\u8be6\u7ec6\u7684\u5730\u5740\u4fe1\u606f",
                "is_extract_failed": False,
            },
            clean_user_input="\u963f\u65af\u8482\u82ac",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertFalse(first_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(first_turn["next_similar_no_match_count"], 1)

        second_turn = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": True, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "\u8bf7\u60a8\u63d0\u4f9b\u8be6\u7ec6\u7684\u5730\u5740\u4fe1\u606f",
                "is_extract_failed": False,
            },
            clean_user_input="\u963f\u65af\u8482\u82ac",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertTrue(second_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(second_turn["llm_result"]["reply"], "")
        self.assertEqual(second_turn["next_last_unmatched_address"], "")
        self.assertEqual(second_turn["next_similar_no_match_count"], 0)

    def test_model_reply_is_ignored_after_tentative_match_demotion(self) -> None:
        main = _load_address_postprocess_main()
        user_address = "\u798f\u5efa\u7701\u798f\u5dde\u5e02\u664b\u5b89\u533a\u5cb3\u5cf0\u95478\u53f7\u697c"
        recorded_reply = (
            "\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a"
            "\u798f\u5efa\u7701\u798f\u5dde\u5e02\u664b\u5b89\u533a\u5cb3\u5cf0\u95478\u53f7\u697c\uff0c"
            "\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5355\u5143\u53f7\u53ca\u95e8\u724c\u53f7\u3002"
        )

        input_llm_result = {
            "matched_index": -1,
            "match_count": 0,
            "is_completed": False,
            "reply": recorded_reply,
            "is_extract_failed": False,
            "matched_address_fragment": user_address,
        }
        input_llm_result_snapshot = dict(input_llm_result)

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result=input_llm_result,
            clean_user_input=user_address,
            last_unmatched_address="\u798f\u5efa\u7701\u798f\u5dde\u5e02\u664b\u5b89\u533a\u5cb3\u5cf0\u9547",
            similar_no_match_count=1,
            address_list=[
                "\u798f\u5efa\u7701\u798f\u5dde\u5e02\u664b\u5b89\u533a\u5cb3\u5cf0\u9547"
                "\u4fdd\u5229\u9999\u69df\u56fd\u9645\u516b\u53f7\u697c2103",
                "\u798f\u5efa\u7701\u798f\u5dde\u5e02\u9f13\u697c\u533a\u4e2d\u5c71\u8def"
                "\u4fdd\u5229\u9999\u69df\u56fd\u9645\u516b\u53f7\u697c2101",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertFalse(result["llm_result"]["is_extract_failed"])
        self.assertEqual(
            result["llm_result"]["reply"],
            "\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a"
            f"{user_address}\uff0c"
            "\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002",
        )
        self.assertEqual(result["next_last_unmatched_address"], user_address)
        self.assertEqual(input_llm_result, input_llm_result_snapshot)

    def test_followup_fragment_uses_merged_user_scope_for_record_and_count(self) -> None:
        main = _load_address_postprocess_main()
        prev_address = "\u671d\u9633\u533a\u5efa\u56fd\u8def88\u53f7\u73b0\u4ee3\u57ce"
        current_fragment = "5\u53f7\u697c"
        merged_address = f"{prev_address}{current_fragment}"
        recorded_reply = (
            "\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a"
            f"{merged_address}\uff0c"
            "\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5355\u5143\u53f7\u53ca\u95e8\u724c\u53f7\u3002"
        )

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": recorded_reply,
                "is_extract_failed": False,
            },
            clean_user_input=current_fragment,
            last_unmatched_address=prev_address,
            similar_no_match_count=0,
            address_list=[
                "\u5317\u4eac\u5e02\u671d\u9633\u533a\u5efa\u56fd\u8def88\u53f7\u73b0\u4ee3\u57ce5\u53f7\u697c1\u5355\u5143101\u5ba4",
                "\u5317\u4eac\u5e02\u671d\u9633\u533a\u5efa\u56fd\u8def88\u53f7\u73b0\u4ee3\u57ce5\u53f7\u697c1\u5355\u5143105\u5ba4",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(result["llm_result"]["reply"], recorded_reply)
        self.assertEqual(result["next_last_unmatched_address"], merged_address)
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_broad_region_without_overlap_clears_unmatched_context(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        build_llm_message_main = _load_build_llm_message_main()

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="北京市",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(first_turn["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertTrue(first_turn["next_last_unmatched_address"].startswith("__NO_MERGE__:"))
        self.assertEqual(first_turn["next_similar_no_match_count"], 1)

        second_turn = build_llm_message_main(
            {
                "userInput": "八号楼",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": [
                    "广东省深圳市中山路八号楼2103",
                    "广东省深圳市中山路八号楼2102",
                ],
            }
        )

        self.assertIn("User: 八号楼", second_turn["user_message"])
        self.assertNotIn("User: 北京市八号楼", second_turn["user_message"])

    def test_repeated_broad_region_without_overlap_triggers_extract_failed(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="广东省",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(first_turn["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertTrue(first_turn["next_last_unmatched_address"].startswith("__NO_MERGE__:"))
        self.assertEqual(first_turn["next_similar_no_match_count"], 1)

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="广东省",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertTrue(second_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(second_turn["llm_result"]["reply"], "")

        output = build_output_main(
            data={
                "match_failed": True,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=second_turn["llm_result"],
            user_spoken_address="广东省",
            clean_user_input="广东省",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(output["reply"], "抱歉您提供的地址不正确。")

    def test_candidate_overlap_resets_similar_no_match_count_between_wrong_inputs(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        addresses = [
            "\u798f\u5dde\u5e02\u5cb3\u5cf0\u9547\u4fdd\u5229\u9999\u69df\u56fd\u9645\u4e1c\u533a\u4e09\u53f7\u697c1201",
            "\u798f\u5dde\u5e02\u5cb3\u5cf0\u9547\u4fdd\u5229\u9999\u69df\u56fd\u9645\u4e1c\u533a\u4e09\u53f7\u697c1200",
        ]
        llm_result = {
            "matched_index": -1,
            "match_count": 0,
            "is_completed": False,
            "reply": "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002",
            "is_extract_failed": False,
        }

        first_turn = postprocess_main(
            llm_result=llm_result,
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="\u4fdd\u5229\u9999\u69df",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )
        self.assertEqual(first_turn["next_last_unmatched_address"], "\u4fdd\u5229\u9999\u69df")
        self.assertEqual(first_turn["next_similar_no_match_count"], 0)

        second_turn = postprocess_main(
            llm_result=llm_result,
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="\u5927\u5858\u6751",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )
        self.assertFalse(second_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(second_turn["next_last_unmatched_address"], "\u4fdd\u5229\u9999\u69df")
        self.assertEqual(second_turn["next_similar_no_match_count"], 1)

        third_turn = postprocess_main(
            llm_result=llm_result,
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="\u4e09\u53f7\u697c",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )
        self.assertFalse(third_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(third_turn["next_last_unmatched_address"], "\u4fdd\u5229\u9999\u69df\u4e09\u53f7\u697c")
        self.assertEqual(third_turn["next_similar_no_match_count"], 0)

    def test_two_different_broad_regions_without_overlap_trigger_extract_failed(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="广东省",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(first_turn["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertTrue(first_turn["next_last_unmatched_address"].startswith("__NO_MERGE__:"))
        self.assertEqual(first_turn["next_similar_no_match_count"], 1)

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="北京市",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertTrue(second_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(second_turn["llm_result"]["reply"], "")
        self.assertEqual(second_turn["next_last_unmatched_address"], "")
        self.assertEqual(second_turn["next_similar_no_match_count"], 0)

        output = build_output_main(
            data={
                "match_failed": True,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=second_turn["llm_result"],
            user_spoken_address="北京市",
            clean_user_input="北京市",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(output["reply"], "抱歉您提供的地址不正确。")

    def test_broad_region_without_overlap_upgrades_detail_reply_to_correct_complete(self) -> None:
        postprocess_main = _load_address_postprocess_main()

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="广东省",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertTrue(result["next_last_unmatched_address"].startswith("__NO_MERGE__:"))
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_confirming_two_irrelevant_turns_repeat_then_fail(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福州市岳峰镇保利香槟国际东区三号楼1201",
            "福州市岳峰镇保利香槟国际东区三号楼1200",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="保利香槟国际东区三号楼1201",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        first_state = state_main(first_turn["llm_result"], address=addresses, state="matching")
        first_output = build_output_main(
            data=first_state,
            llm_result=first_turn["llm_result"],
            user_spoken_address="保利香槟国际东区三号楼1201",
            clean_user_input="保利香槟国际东区三号楼1201",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
        )

        self.assertEqual(first_output["reply"], "请问您说的是保利香槟国际东区三号楼1201吗？")

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": True, "reply": "请直接回答是或者不是。"},
            state=first_state["state"],
            matched_index=first_state["matched_index"],
            clean_user_input="数据量时间段",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state=first_state["state"])
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address="数据量时间段",
            clean_user_input="数据量时间段",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_output["reply"], "请问您说的是保利香槟国际东区三号楼1201吗？")
        self.assertEqual(second_turn["next_similar_no_match_count"], 1)

        third_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": True, "reply": "请直接回答是或者不是。"},
            state=second_state["state"],
            matched_index=second_state["matched_index"],
            clean_user_input="打发发呆",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        third_state = state_main(third_turn["llm_result"], address=addresses, state=second_state["state"])
        third_output = build_output_main(
            data=third_state,
            llm_result=third_turn["llm_result"],
            user_spoken_address="打发发呆",
            clean_user_input="打发发呆",
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertTrue(third_turn["llm_result"]["is_extract_failed"])
        self.assertTrue(third_state["match_failed"])
        self.assertEqual(third_output["reply"], "抱歉您提供的地址不正确。")

    def test_fuzzy_county_then_village_correction_confirms_with_user_scope_only(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福建漳州云霄县莆美镇大埔村352",
            "福建漳州云霄县常山农场树洞村123",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="云效县",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：云霄县，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(first_turn["next_last_unmatched_address"], "云霄县")

        second_built = build_llm_message_main(
            {
                "userInput": "长山农场树东村",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state="matching")
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_state["state"], "confirming")
        self.assertEqual(second_state["matched_index"], 1)
        self.assertEqual(second_output["reply"], "请问您说的是云霄县常山农场树洞村吗？")

    def test_homophone_county_with_pypinyin_correction_records_expected_scope(self) -> None:
        postprocess_main = _load_address_postprocess_main()

        addresses = [
            "福建漳州云霄县莆美镇大埔村352",
            "福建漳州云霄县常山农场树洞村123",
        ]

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
                "matched_address_fragment": "云霄县",
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="云晓现",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：云霄县，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "云霄县")

    def test_fuzzy_named_place_correction_keeps_only_user_mentioned_scope(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福建漳州云霄县莆美镇世安新城方景小区352",
            "福建漳州云霄县南阳路福宁小区123",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="四安新城",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        self.assertEqual(
            first_turn["llm_result"]["reply"],
            "我记录的地址信息是：世安新城，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(first_turn["next_last_unmatched_address"], "世安新城")

        second_built = build_llm_message_main(
            {
                "userInput": "欢景小区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": first_turn["next_last_unmatched_address"],
                "similar_no_match_count": first_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input=second_built["effective_match_input"],
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        second_state = state_main(second_turn["llm_result"], address=addresses, state="matching")
        second_output = build_output_main(
            data=second_state,
            llm_result=second_turn["llm_result"],
            user_spoken_address=second_built["effective_match_input"],
            clean_user_input=second_built["clean_user_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
        )

        self.assertEqual(second_state["state"], "confirming")
        self.assertEqual(second_state["matched_index"], 0)
        self.assertEqual(second_output["reply"], "请问您说的是世安新城方景小区吗？")

    def test_pinyin_overlap_fragment_merges_with_previous_unmatched_address(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()

        result = build_llm_message_main(
            {
                "userInput": "芳景小区",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "世安新城",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "福建漳州云霄县莆美镇世安新城方景小区352",
                    "福建漳州云霄县南阳路福宁小区123",
                ],
            }
        )

        self.assertEqual(result["effective_match_input"], "世安新城方景小区")
        self.assertEqual(result["llm_user_input"], "芳景小区")
        self.assertEqual(result["possible_merged_input"], "世安新城方景小区")
        self.assertIn("User: 芳景小区", result["user_message"])

    def test_build_llm_message_rejects_different_syllable_named_place_correction(self) -> None:
        payload = {
            "userInput": "保留香槟",
            "state": "matching",
            "matchedIndex": -1,
            "last_unmatched_address": "三号楼1201",
            "last_unmatched_fragment": "三号楼1201",
            "similar_no_match_count": 1,
            "kdRecords": [
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        }

        for label, build_llm_message_main in (
            ("workflow-json", _load_build_llm_message_main()),
            ("source-file", _load_build_llm_message_file_main()),
        ):
            with self.subTest(label=label):
                result = build_llm_message_main(payload)
                user_message = result["user_message"]

                self.assertEqual(result["clean_user_input"], "保留香槟")
                self.assertEqual(result["llm_user_input"], "保留香槟")
                self.assertEqual(result["effective_match_input"], "保留香槟")
                self.assertEqual(result["possible_merged_input"], "")
                self.assertIn("User: 保留香槟", user_message)
                self.assertIn("保留香槟", user_message)
                self.assertIn("保利香槟", user_message)
                self.assertIn("留(liu)≠利(li)", user_message)
                self.assertIn("不同音节", user_message)
                self.assertNotIn("根据拼音(多音字)发现用户片段与候选片段相近: 保留香槟~保利香槟", user_message)

    def test_build_llm_message_lets_model_judge_current_input_against_previous_fragment(self) -> None:
        payload = {
            "userInput": "保利香槟",
            "state": "matching",
            "matchedIndex": -1,
            "last_unmatched_address": "福州市鼓楼区",
            "last_unmatched_fragment": "福州市鼓楼区",
            "similar_no_match_count": 1,
            "kdRecords": [
                "福建省福州市鼓楼区中山路保利香槟国际八号楼2103",
                "福建省福州市鼓楼区中山路保利香槟国际八号楼2101",
            ],
        }

        for label, build_llm_message_main in (
            ("workflow-json", _load_build_llm_message_main()),
            ("source-file", _load_build_llm_message_file_main()),
        ):
            with self.subTest(label=label):
                result = build_llm_message_main(payload)
                user_message = result["user_message"]

                self.assertEqual(result["clean_user_input"], "保利香槟")
                self.assertEqual(result["llm_user_input"], "保利香槟")
                self.assertEqual(result["effective_match_input"], "福州市鼓楼区保利香槟")
                self.assertEqual(result["possible_merged_input"], "福州市鼓楼区保利香槟")
                self.assertIn("clean_user_input=保利香槟", user_message)
                self.assertIn("last_matched_address_fragment=福州市鼓楼区", user_message)
                self.assertIn(
                    "candidate_combined_user_scope_if_supplement=福州市鼓楼区保利香槟",
                    user_message,
                )
                self.assertIn("User: 保利香槟", user_message)
                self.assertNotIn("User: 福州市鼓楼区保利香槟", user_message)
                self.assertIn("请先判断 clean_user_input", user_message)
                self.assertIn("不能只输出 clean_user_input 本轮片段", user_message)
                self.assertNotIn("候选支持的地址片段是“福州市鼓楼区”", user_message)

    def test_numeric_suffix_prefix_overlap_merges_without_duplication(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()

        result = build_llm_message_main(
            {
                "userInput": "1201",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "A120",
                "similar_no_match_count": 1,
                "kdRecords": ["A1201", "A1200"],
            }
        )

        self.assertEqual(result["effective_match_input"], "A1201")
        self.assertEqual(result["llm_user_input"], "1201")
        self.assertEqual(result["possible_merged_input"], "A1201")
        self.assertIn("User: 1201", result["user_message"])
        self.assertNotIn("A1201201", result["user_message"])

    def test_address_context_suffix_prefix_overlap_merges_without_duplication(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()

        result = build_llm_message_main(
            {
                "userInput": "1201",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "福州市岳峰镇保利香槟国际东区三号楼120",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "福州市岳峰镇保利香槟国际东区三号楼1201",
                    "福州市岳峰镇保利香槟国际东区三号楼1200",
                ],
            }
        )

        self.assertEqual(result["effective_match_input"], "福州市岳峰镇保利香槟国际东区三号楼1201")
        self.assertEqual(result["llm_user_input"], "1201")
        self.assertEqual(result["possible_merged_input"], "福州市岳峰镇保利香槟国际东区三号楼1201")
        self.assertIn("User: 1201", result["user_message"])
        self.assertNotIn("1201201", result["user_message"])

    def test_candidate_noise_cleaning_trims_only_non_address_wrappers(self) -> None:
        cases = (
            (
                "真爱桃园华府",
                ["公园路桃园华府30号楼"],
                "桃园华府",
            ),
            (
                "宽地阔的公园路",
                ["公园路桃园华府30号楼"],
                "公园路",
            ),
            (
                "乱七八糟公园路",
                ["公园路桃园华府30号楼"],
                "公园路",
            ),
            (
                "100栋302",
                ["移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室"],
                "100栋302",
            ),
            (
                "桃园华府北门",
                ["公园路桃园华府30号楼"],
                "桃园华府北门",
            ),
            (
                "桃园华府的公园路",
                ["公园路桃园华府30号楼"],
                "桃园华府的公园路",
            ),
            (
                "北门的公园路",
                ["公园路桃园华府30号楼"],
                "北门的公园路",
            ),
        )

        for label, build_llm_message_main in (
            ("workflow-json", _load_build_llm_message_main()),
            ("source-file", _load_build_llm_message_file_main()),
        ):
            for user_input, records, expected in cases:
                with self.subTest(label=label, user_input=user_input):
                    result = build_llm_message_main(
                        {
                            "userInput": user_input,
                            "state": "matching",
                            "matchedIndex": -1,
                            "last_unmatched_address": "",
                            "similar_no_match_count": 0,
                            "kdRecords": records,
                        }
                    )

                    self.assertEqual(result["clean_user_input"], expected)
                    self.assertEqual(result["effective_match_input"], expected)
                    self.assertIn(f"User: {expected}", result["user_message"])
                    self.assertNotIn("用户正在纠正上一条地址", result["user_message"])

    def test_chinese_numeric_detail_preserved_on_first_candidate_overlap_cleaning(self) -> None:
        payload = {
            "userInput": "一百楼一单元三零二",
            "state": "matching",
            "matchedIndex": -1,
            "last_unmatched_address": "",
            "similar_no_match_count": 0,
            "kdRecords": [
                "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        }

        for label, build_llm_message_main in (
            ("workflow-json", _load_build_llm_message_main()),
            ("source-file", _load_build_llm_message_file_main()),
        ):
            with self.subTest(label=label):
                result = build_llm_message_main(payload)

                self.assertEqual(result["clean_user_input"], "一百楼一单元三零二")
                self.assertEqual(result["effective_match_input"], "一百楼一单元三零二")
                self.assertIn("User: 一百楼一单元三零二", result["user_message"])
                self.assertIn("clean_user_input: 一百楼一单元三零二", result["user_message"])
                self.assertNotIn("User: 楼一单元三零二", result["user_message"])
                self.assertNotIn("clean_user_input: 楼一单元三零二", result["user_message"])

    def test_chinese_numeric_detail_preserved_when_candidate_backed_supplement_merges(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()

        result = build_llm_message_main(
            {
                "userInput": "江阳化工厂",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": "一百楼一单元三零二",
                "similar_no_match_count": 1,
                "kdRecords": [
                    "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                    "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                    "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
                ],
            }
        )

        expected = "一百楼一单元三零二江阳化工厂"
        self.assertEqual(result["effective_match_input"], expected)
        self.assertEqual(result["llm_user_input"], "江阳化工厂")
        self.assertEqual(result["possible_merged_input"], expected)
        self.assertIn("User: 江阳化工厂", result["user_message"])
        self.assertIn("last_unmatched_address=一百楼一单元三零二", result["user_message"])
        self.assertIn("clean_user_input: 江阳化工厂", result["user_message"])
        self.assertNotIn("一百楼1单元302", result["user_message"])
        self.assertNotIn("一百楼1单元302", result["history_user_message"])

    def test_previous_candidate_fragment_is_passed_to_llm_context(self) -> None:
        payload = {
            "userInput": "江洋小区",
            "state": "matching",
            "matchedIndex": -1,
            "last_unmatched_address": "一百楼一单元三零二",
            "last_unmatched_fragment": "100号楼1单元302室",
            "similar_no_match_count": 1,
            "kdRecords": [
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        }

        for label, build_llm_message_main in (
            ("workflow-json", _load_build_llm_message_main()),
            ("source-file", _load_build_llm_message_file_main()),
        ):
            with self.subTest(label=label):
                result = build_llm_message_main(payload)
                user_message = result["user_message"]

                self.assertIn("last_unmatched_address=100号楼1单元302室", user_message)
                self.assertIn("last_matched_address_fragment=100号楼1单元302室", user_message)
                self.assertNotIn("last_unmatched_address=一百楼一单元三零二", user_message)

    def test_unsupported_residential_anchor_after_denial_does_not_reuse_previous_fragment(self) -> None:
        postprocess_main = _load_address_postprocess_main()

        result = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "一百楼一单元三零二江阳化工厂",
                "reason": "one",
                "reply": "",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="江阳小区",
            last_unmatched_address="一百楼一单元三零二江阳化工厂",
            last_unmatched_fragment="一百楼一单元三零二江阳化工厂",
            similar_no_match_count=1,
            address_list=[
                "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        )

        output = result["llm_result"]
        self.assertEqual(output["matched_index"], -1)
        self.assertEqual(output["match_count"], 0)
        self.assertFalse(output["is_completed"])
        self.assertEqual(output["matched_address_fragment"], "")
        self.assertEqual(output["reason"], "")
        self.assertEqual(result["next_last_unmatched_fragment"], "")

    def test_unsupported_residential_anchor_hint_after_previous_context_does_not_request_previous_fallback(self) -> None:
        payload = {
            "userInput": "江阳小区",
            "state": "matching",
            "matchedIndex": -1,
            "last_unmatched_address": "一百楼一单元三零二江阳化工厂",
            "last_unmatched_fragment": "一百楼一单元三零二江阳化工厂",
            "similar_no_match_count": 1,
            "kdRecords": [
                "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        }

        for label, build_llm_message_main in (
            ("workflow-json", _load_build_llm_message_main()),
            ("source-file", _load_build_llm_message_file_main()),
        ):
            with self.subTest(label=label):
                result = build_llm_message_main(payload)
                user_message = result["user_message"]

                self.assertIn("本轮地点主体校验", user_message)
                self.assertIn("candidate_supports_current_anchor=false", user_message)
                self.assertIn("matched_address_fragment 应按提示词中无候选支持或上一轮结果的规则处理", user_message)
                self.assertNotIn("allowed_matched_address_fragments", user_message)
                self.assertNotIn("候选支持片段白名单", user_message)
                self.assertNotIn('禁止输出 matched_address_fragment="江阳小区"', user_message)

    def test_room_then_homophone_town_records_candidate_corrected_text(self) -> None:
        postprocess_main = _load_address_postprocess_main()

        addresses = [
            "福建漳州云霄县莆美镇福湾小区8号楼1202",
            "福建漳州云霄县常山农场树洞村123",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="1202",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        second_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
                "matched_address_fragment": "1202莆美镇",
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="1202普美镇",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            "我记录的地址信息是：1202莆美镇，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(second_turn["next_last_unmatched_address"], "1202莆美镇")

    def test_fuzzy_named_place_with_building_confirms_without_unmentioned_words(self) -> None:
        postprocess_main = _load_address_postprocess_main()
        state_main = _load_workflow_state_main()
        build_output_main = _load_build_output_main()

        addresses = [
            "福建漳州云霄县莆美镇沧海名著3号楼352",
            "福建漳州云霄县南阳路福宁小区123",
        ]

        first_turn = postprocess_main(
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
            meaningless_result={"is_meaningless": False, "reply": ""},
            state="matching",
            matched_index=-1,
            clean_user_input="参海民筑3号楼",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=addresses,
        )

        first_state = state_main(first_turn["llm_result"], address=addresses, state="matching")
        first_output = build_output_main(
            data=first_state,
            llm_result=first_turn["llm_result"],
            user_spoken_address="参海民筑3号楼",
            clean_user_input="参海民筑3号楼",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
        )

        self.assertEqual(first_state["state"], "confirming")
        self.assertEqual(first_state["matched_index"], 0)
        self.assertEqual(first_output["reply"], "请问您说的是沧海名著3号楼吗？")


if __name__ == "__main__":
    unittest.main()
