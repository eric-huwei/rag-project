from __future__ import annotations

import json
from pathlib import Path
import unittest


def _load_code_main(predicate):
    workflow_path = next(Path(__file__).resolve().parents[1].glob("*.json"))
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

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
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

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

        self.assertIn("User: 三号楼1201保利香槟", result["user_message"])
        self.assertEqual(result["effective_match_input"], "三号楼1201保利香槟")

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
        self.assertEqual(result["next_last_unmatched_address"], "")

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
        self.assertEqual(result["next_similar_no_match_count"], 1)

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

        self.assertIn("User: 1201三号楼东区", result["user_message"])
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
        self.assertEqual(first_turn["next_similar_no_match_count"], 1)

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
            "我记录的地址信息是：中山路八号楼，请您再提供下门牌号信息",
        )
        self.assertEqual(second_turn["next_last_unmatched_address"], "中山路八号楼")
        self.assertEqual(second_turn["next_similar_no_match_count"], 2)

        third_turn = postprocess_main(
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
            clean_user_input="5555",
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertTrue(third_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(third_turn["llm_result"]["reply"], "")
        self.assertEqual(third_turn["next_last_unmatched_address"], "")
        self.assertEqual(third_turn["next_similar_no_match_count"], 0)

        output = build_output_main(
            data={
                "match_failed": True,
                "is_completed": False,
                "state": "matching",
                "matched_index": -1,
                "matched_account": "",
            },
            llm_result=third_turn["llm_result"],
            user_spoken_address="5555",
            clean_user_input="5555",
            last_unmatched_address=third_turn["next_last_unmatched_address"],
        )

        self.assertEqual(output["reply"], "抱歉您提供的地址不正确。")

    def test_irrelevant_followup_after_road_and_building_keeps_previous_reply(self) -> None:
        build_llm_message_main = _load_build_llm_message_main()
        postprocess_main = _load_address_postprocess_main()
        build_output_main = _load_build_output_main()

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
            "我记录的地址信息是：中山路:，请您再提供下楼号、单元号及门牌号信息。",
        )

        second_built = build_llm_message_main(
            {
                "userInput": "3号楼",
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

        self.assertEqual(
            second_turn["llm_result"]["reply"],
            "我记录的地址信息是：中山路:3号楼，请您再提供下单元号及门牌号信息。",
        )

        third_built = build_llm_message_main(
            {
                "userInput": "数据量时间段",
                "state": "matching",
                "matchedIndex": -1,
                "last_unmatched_address": second_turn["next_last_unmatched_address"],
                "similar_no_match_count": second_turn["next_similar_no_match_count"],
                "kdRecords": addresses,
            }
        )

        self.assertEqual(third_built["effective_match_input"], "数据量时间段")

        third_turn = postprocess_main(
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
            clean_user_input=third_built["effective_match_input"],
            last_unmatched_address=second_turn["next_last_unmatched_address"],
            similar_no_match_count=second_turn["next_similar_no_match_count"],
            address_list=addresses,
        )

        self.assertEqual(
            third_turn["llm_result"]["reply"],
            second_turn["llm_result"]["reply"],
        )
        self.assertEqual(
            third_turn["next_last_unmatched_address"],
            second_turn["next_last_unmatched_address"],
        )

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

        self.assertEqual(output["reply"], second_turn["llm_result"]["reply"])

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

    def test_llm_recorded_followup_is_preserved_when_no_candidate_matches(self) -> None:
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
        self.assertEqual(result["llm_result"]["reply"], recorded_reply)
        self.assertEqual(result["next_last_unmatched_address"], user_address)

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


if __name__ == "__main__":
    unittest.main()
