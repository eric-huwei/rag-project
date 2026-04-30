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

        self.assertEqual(result["reply"], "\u62b1\u6b49\u60a8\u63d0\u4f9b\u7684\u5730\u5740\u5339\u914d\u4e0d\u4e0a\u3002")

        final_output_code = _load_final_output_code()
        self.assertIn('content: isFailed ? failedReply : reply', final_output_code)
        self.assertIn('IsEnd: isFailed ? "-1"', final_output_code)
        self.assertNotIn('startsWith("请问您说的是")', final_output_code)

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

        self.assertEqual(output["reply"], "抱歉您提供的地址匹配不上。")

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


if __name__ == "__main__":
    unittest.main()
