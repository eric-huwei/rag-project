from __future__ import annotations

import json
from pathlib import Path
import unittest


def _load_llm_postprocess_main():
    path = next(Path(__file__).resolve().parents[1].glob("llm*.py"))
    namespace: dict[str, object] = {}
    exec(path.read_text(encoding="utf-8"), namespace)
    return namespace["main"]


class LlmPostprocessFileTests(unittest.TestCase):
    def test_merges_broad_region_followup_with_previous_city(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="大同区",
            last_unmatched_address="北京市",
            similar_no_match_count=1,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1119",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "",
        )
        self.assertEqual(result["next_last_unmatched_address"], "")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_preserves_recorded_reply_and_history_for_layer_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": (
                    "我记录的地址信息是：合肥市庐江县，"
                    "请您再说一下具体的小区或村镇名称。"
                ),
                "is_extract_failed": False,
            },
            clean_user_input="庐江县",
            last_unmatched_address="合肥市",
            similar_no_match_count=1,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1119",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：合肥市庐江县，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "合肥市庐江县")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_full_precise_unmatched_address_requests_correct_complete_info(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="北京市大同区百花小区9栋1109",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1119",
            ],
        )

        self.assertEqual(result["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertEqual(result["next_last_unmatched_address"], "北京市大同区百花小区9栋1109")

    def test_completed_state_with_new_city_restarts_matching_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="completed",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="福州市",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：福州市，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "福州市")
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_omitted_city_county_keeps_llm_unique_match(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            clean_user_input="安徽省汤池镇百花小区9栋1109",
            last_unmatched_address="安徽省汤池镇",
            similar_no_match_count=1,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1110",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:安徽省汤池镇百花小区9栋1109",
        )

    def test_omitted_city_town_overrides_llm_no_match_when_precise(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供正确完整的地址信息",
                "is_extract_failed": False,
            },
            clean_user_input="安徽省庐江县百花小区9栋1109",
            last_unmatched_address="安徽省庐江县",
            similar_no_match_count=1,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1110",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:安徽省庐江县百花小区9栋1109",
        )

    def test_town_community_room_overrides_llm_no_match_when_precise(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供正确完整的地址信息",
                "is_extract_failed": False,
            },
            clean_user_input="汤池镇百花小区9栋1109",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1110",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:汤池镇百花小区9栋1109",
        )

    def test_precise_room_conflict_overrides_llm_wrong_unique_match(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
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
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:州市鼓楼区保利香槟国际8号楼2101",
        )
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_precise_room_conflict_demotes_single_wrong_candidate(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            clean_user_input="州市鼓楼区保利香槟国际8号楼2101",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福建省福州市鼓楼区中山路保利香槟国际八号楼2103",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(result["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertEqual(result["next_last_unmatched_address"], "州市鼓楼区保利香槟国际8号楼2101")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_confirming_denial_uses_detail_request_not_forbidden_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="confirming",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再重新说一下报修宽带所在小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="不是",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "安徽省合肥市庐江县汤池镇百花小区9栋1109",
                "安徽省合肥市庐江县汤池镇百花小区9栋1110",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(result["llm_result"]["reply"], "请您提供详细的地址信息")

    def test_confirming_affirmation_completes_even_if_model_returns_reason_true(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="",
            matched_index=2,
            state="confirming",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 2,
                "match_count": 1,
                "is_completed": False,
                "matched_address_fragment": "江阳化工厂100号楼1单元302室",
                "reason": "true",
            },
            clean_user_input="是的",
            last_unmatched_address="__NO_MERGE__:江阳化工厂一百楼一单元三零二",
            similar_no_match_count=0,
            address_list=[
                "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 2)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertTrue(result["llm_result"]["is_completed"])
        self.assertFalse(result["llm_result"]["is_extract_failed"])
        self.assertEqual(result["llm_result"]["matched_address_fragment"], "")
        self.assertEqual(result["llm_result"]["reason"], "")
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(result["llm_result"]["ai_context_reply"], "")
        self.assertEqual(result["next_last_unmatched_address"], "")
        self.assertEqual(result["next_last_unmatched_fragment"], "")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_completed_denial_uses_layer_reply_not_forbidden_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="completed",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再重新说一下报修宽带所在小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="错了",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(
            result["llm_result"]["reply"],
            "好的，请您再说一下具体的小区或村镇名称。",
        )

    def test_model_reply_is_ignored_while_postprocess_builds_detail_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": (
                    "我记录的地址信息是：福州市岳峰镇保利香槟国际东区三号楼，"
                    "请您再说一下具体的单元号及门牌号。"
                ),
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟",
            last_unmatched_address="福州市岳峰镇",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：福州市岳峰镇保利香槟，请您再说一下具体的楼栋号、单元号及门牌号。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "福州市岳峰镇保利香槟")
        self.assertNotIn("国际东区三号楼", result["llm_result"]["reply"])

    def test_model_fragment_drives_followup_without_model_reply(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "福州市岳峰镇保利香槟",
            },
            clean_user_input="保利香槟",
            last_unmatched_address="福州市岳峰镇",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertNotIn("reply", {
            "matched_index": -1,
            "match_count": 0,
            "is_completed": False,
            "matched_address_fragment": "福州市岳峰镇保利香槟",
        })
        self.assertEqual(result["next_last_unmatched_address"], "福州市岳峰镇保利香槟")
        self.assertEqual(
            result["llm_result"]["matched_address_fragment"],
            "福州市岳峰镇保利香槟",
        )

    def test_recorded_reply_does_not_prepend_candidate_prefix(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": (
                    "我记录的地址信息是：北京市朝阳区建国路88号，"
                    "请您再说一下具体的小区或村镇名称。"
                ),
                "is_extract_failed": False,
            },
            clean_user_input="朝阳区建国路88号",
            last_unmatched_address="朝阳区",
            similar_no_match_count=1,
            address_list=[
                "北京市朝阳区建国路88号现代城5号楼1单元101室",
                "北京市朝阳区建国路88号现代城5号楼1单元105室",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：朝阳区建国路88号，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "朝阳区建国路88号")
        self.assertNotIn("北京市", result["llm_result"]["reply"])

    def test_named_place_fragment_gets_recorded_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟国际",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：保利香槟国际，请您再提供下楼栋号、单元号及门牌号信息",
        )
        self.assertEqual(result["next_last_unmatched_address"], "保利香槟国际")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_weak_area_recorded_reply_yields_to_stronger_named_place_fragment(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "我记录的地址信息是：东区，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟",
            last_unmatched_address="东区",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：保利香槟，请您再提供下楼栋号、单元号及门牌号信息",
        )
        self.assertEqual(result["next_last_unmatched_address"], "保利香槟")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_named_place_with_chinese_building_and_room_matches_uniquely(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "我记录的地址信息是：保利香槟三号楼1201，请您再提供下单元号及门牌号信息。",
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟三号楼1201",
            last_unmatched_address="保利香槟",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:保利香槟三号楼1201",
        )
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_named_place_fragment_merges_with_previous_building_room_and_matches(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟",
            last_unmatched_address="三号楼1201",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:保利香槟三号楼1201",
        )
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_named_place_fragment_with_east_area_after_room_matches(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="三号楼1201栋区保利香槟",
            last_unmatched_address="三号楼1201栋区",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:三号楼1201东区保利香槟",
        )
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_candidate_backed_merge_requires_same_candidate_explains_both_turns(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟",
            last_unmatched_address="中山路",
            similar_no_match_count=1,
            address_list=[
                "中山路3号楼2101",
                "福州市岳峰镇保利香槟国际东区三号楼1201",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：保利香槟，请您再提供下楼栋号、单元号及门牌号信息",
        )
        self.assertEqual(result["next_last_unmatched_address"], "保利香槟")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_premerged_named_place_input_does_not_duplicate_previous_building_room(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="保利香槟三号楼1201",
            last_unmatched_address="三号楼1201",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 0)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:保利香槟三号楼1201",
        )
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_road_only_gets_recorded_place_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="中山路",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "中山路3号楼2101",
                "中山路3号楼2102",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：中山路，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "中山路")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_building_and_room_without_place_records_and_requests_place_name(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="8号楼2102",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：8号楼2102，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "8号楼2102")
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_place_less_building_room_llm_unique_match_is_demoted_to_followup(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 1,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
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
        main = _load_llm_postprocess_main()
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
                    matched_index=-1,
                    state="matching",
                    meaningless_result={"is_meaningless": False, "reply": ""},
                    llm_result={
                        "matched_index": 2,
                        "match_count": 1,
                        "is_completed": False,
                        "reply": "",
                        "is_extract_failed": False,
                    },
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
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            clean_user_input="101\u697c1\u5355\u5143302\u5ba4",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "\u5c71\u897f\u592a\u539f\u5e02\u5c16\u8349\u576a\u533a\u6c5f\u9633\u5316\u5de5\u5382100\u53f7\u697c1\u5355\u5143302\u5ba4",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)

    def test_room_followup_after_building_keeps_recorded_address(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="三号楼1201",
            last_unmatched_address="三号楼",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "三号楼1201")
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_room_followup_after_building_demotes_llm_unique_match_without_place(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 0,
                "match_count": 1,
                "is_completed": False,
                "reply": "",
                "is_extract_failed": False,
            },
            clean_user_input="三号楼1201",
            last_unmatched_address="三号楼",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "三号楼1201")
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_multi_match_building_room_fragment_requests_place_name(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="三号楼",
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 2,
                "is_completed": False,
                "matched_address_fragment": "三号楼1201",
            },
            clean_user_input="三号楼1201",
            last_unmatched_address="三号楼",
            similar_no_match_count=0,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 2)
        self.assertEqual(result["llm_result"]["matched_address_fragment"], "三号楼1201")
        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(
            result["llm_result"]["ai_context_reply"],
            "我记录的地址信息是：三号楼1201，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "三号楼1201")
        self.assertEqual(result["next_last_unmatched_fragment"], "三号楼1201")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_ai_context_reply_uses_candidate_fragment_not_user_spoken_text(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="",
            matched_index=0,
            state="",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "100号楼1单元302室",
                "reason": "one",
            },
            clean_user_input="一百楼一单元三零二",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：一百楼一单元三零二，请您再提供下小区名称或楼宇名称",
        )
        self.assertEqual(
            result["llm_result"]["ai_context_reply"],
            "我记录的地址信息是：100号楼1单元302室，请您再提供下小区名称或楼宇名称",
        )
        self.assertEqual(result["next_last_unmatched_address"], "一百楼一单元三零二")
        self.assertEqual(result["next_last_unmatched_fragment"], "100号楼1单元302室")

    def test_reply_does_not_append_last_unmatched_address_to_clean_user_input(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="100号楼1单元302室",
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": 2,
                "match_count": 1,
                "is_completed": False,
                "matched_address_fragment": "江阳化工厂100号楼1单元302室",
                "reason": "true",
            },
            clean_user_input="一百楼一单元三零二江阳化工厂",
            last_unmatched_address="一百楼一单元三零二",
            similar_no_match_count=0,
            address_list=[
                "移机费50元山西太原市尖草坪区卧虎山路柏翠苑1号楼5单元202室",
                "山西太原市尖草坪区卧虎山路柏翠苑4号楼2单元102室",
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "请问您说的是一百楼一单元三零二江阳化工厂吗？",
        )
        self.assertEqual(
            result["llm_result"]["ai_context_reply"],
            "请问您说的是江阳化工厂100号楼1单元302室吗？",
        )
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:一百楼一单元三零二江阳化工厂",
        )

    def test_reply_uses_last_unmatched_address_when_fragment_is_reused(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="100号楼1单元302室",
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "100号楼1单元302室",
                "reason": "one",
            },
            clean_user_input="江阳小区",
            last_unmatched_address="一百楼一单元三零二",
            similar_no_match_count=0,
            address_list=[
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        )

        self.assertEqual(
            result["llm_result"]["reply"],
            "我记录的地址信息是：一百楼一单元三零二，请您再提供下小区名称或楼宇名称",
        )
        self.assertEqual(
            result["llm_result"]["ai_context_reply"],
            "我记录的地址信息是：100号楼1单元302室，请您再提供下小区名称或楼宇名称",
        )
        self.assertEqual(result["next_last_unmatched_address"], "一百楼一单元三零二")

    def test_empty_reason_without_supported_fragments_requests_detail_info(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="",
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "",
                "reason": "",
            },
            clean_user_input="随便一句",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[],
        )

        self.assertEqual(result["llm_result"]["reply"], "请你提供详细的地址信息")
        self.assertEqual(result["llm_result"]["ai_context_reply"], "请你提供详细的地址信息")
        self.assertEqual(result["llm_result"]["matched_address_fragment"], "")
        self.assertEqual(result["next_last_unmatched_address"], "")
        self.assertEqual(result["next_last_unmatched_fragment"], "")

    def test_repeated_matched_fragment_fails_even_when_followup_can_be_built(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="三号楼1201",
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": True, "reply": "请您提供详细的地址信息。"},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "三号楼1201",
            },
            clean_user_input="保留香槟",
            last_unmatched_address="三号楼1201",
            similar_no_match_count=1,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertTrue(result["llm_result"]["is_extract_failed"])
        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(result["llm_result"]["matched_address_fragment"], "")
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(result["next_last_unmatched_address"], "")
        self.assertEqual(result["next_last_unmatched_fragment"], "")
        self.assertEqual(result["next_similar_no_match_count"], 2)

    def test_reused_previous_fragment_infers_previous_reason(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            last_unmatched_fragment="100号楼1单元302室",
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "matched_address_fragment": "100号楼1单元302室",
                "reason": "",
            },
            clean_user_input="江阳小区",
            last_unmatched_address="100号楼1单元302室",
            similar_no_match_count=0,
            address_list=[
                "移机费50元山西太原市尖草坪区江阳商业街江阳化工厂100号楼1单元302室",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], -1)
        self.assertEqual(result["llm_result"]["match_count"], 0)
        self.assertEqual(result["llm_result"]["matched_address_fragment"], "100号楼1单元302室")
        self.assertEqual(result["llm_result"]["reason"], "one")
        self.assertEqual(result["next_last_unmatched_fragment"], "100号楼1单元302室")

    def test_reason_ignores_level5_road_house_before_named_building(self) -> None:
        main = _load_llm_postprocess_main()
        address_list = ["湖北省武汉市武昌区中北路1号楚天传媒大厦B座2004室"]

        cases = [
            ("中北路1号", -1, 0, "two", ""),
            ("楚天传媒大厦", -1, 0, "", "two"),
            ("楚天传媒大厦B座2004室", 0, 1, "", "true"),
        ]

        for fragment, matched_index, match_count, model_reason, expected_reason in cases:
            with self.subTest(fragment=fragment):
                result = main(
                    matched_index=-1,
                    state="matching",
                    meaningless_result={"is_meaningless": False, "reply": ""},
                    llm_result={
                        "matched_index": matched_index,
                        "match_count": match_count,
                        "is_completed": False,
                        "matched_address_fragment": fragment,
                        "reason": model_reason,
                        "reply": "",
                        "is_extract_failed": False,
                    },
                    clean_user_input=fragment,
                    similar_no_match_count=0,
                    address_list=address_list,
                )

                self.assertEqual(result["llm_result"]["matched_address_fragment"], fragment)
                self.assertEqual(result["llm_result"]["reason"], expected_reason)

    def test_place_fragment_merges_before_building_room_and_matches_uniquely(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="中山路",
            last_unmatched_address="8号楼2102",
            similar_no_match_count=1,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(result["llm_result"]["matched_index"], 1)
        self.assertEqual(result["llm_result"]["match_count"], 1)
        self.assertEqual(result["llm_result"]["reply"], "")
        self.assertEqual(
            result["next_last_unmatched_address"],
            "__NO_MERGE__:中山路8号楼2102",
        )
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_broad_region_without_candidate_overlap_requests_correct_complete(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=0,
            state="",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="北京市",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "广东省深圳市中山路八号楼2103",
                "广东省深圳市中山路八号楼2102",
            ],
        )

        self.assertEqual(result["llm_result"]["reply"], "请您提供正确完整的地址信息")
        self.assertTrue(result["next_last_unmatched_address"].startswith("__NO_MERGE__:"))
        self.assertEqual(result["next_similar_no_match_count"], 1)

    def test_broad_region_without_overlap_upgrades_detail_reply_to_correct_complete(self) -> None:
        main = _load_llm_postprocess_main()

        result = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "请您提供详细的地址信息",
                "is_extract_failed": False,
            },
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

    def test_repeated_broad_region_without_overlap_triggers_extract_failed(self) -> None:
        main = _load_llm_postprocess_main()

        first_turn = main(
            matched_index=0,
            state="",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="广东省",
            last_unmatched_address="",
            similar_no_match_count=0,
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        second_turn = main(
            matched_index=-1,
            state="matching",
            meaningless_result={"is_meaningless": False, "reply": ""},
            llm_result={
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            },
            clean_user_input="广东省",
            last_unmatched_address=first_turn["next_last_unmatched_address"],
            similar_no_match_count=first_turn["next_similar_no_match_count"],
            address_list=[
                "福州市岳峰镇保利香槟国际东区三号楼1201",
                "福州市岳峰镇保利香槟国际东区三号楼1200",
            ],
        )

        self.assertTrue(second_turn["llm_result"]["is_extract_failed"])
        self.assertEqual(second_turn["llm_result"]["reply"], "")
        self.assertEqual(second_turn["next_last_unmatched_address"], "")
        self.assertEqual(second_turn["next_similar_no_match_count"], 0)

    def test_candidate_backed_admin_road_and_house_keep_recorded_scope(self) -> None:
        main = _load_llm_postprocess_main()

        address_list = ["福建三明龙溪城区东三路4号香江悦府1幢1层401"]
        turns = [
            ("三明", "我记录的地址信息是：三明，请您再说一下具体的小区或村镇名称。", "三明"),
            ("龙溪城区", "我记录的地址信息是：三明龙溪城区，请您再说一下具体的小区或村镇名称。", "三明龙溪城区"),
            ("东三路", "我记录的地址信息是：三明龙溪城区东三路，请您再说一下具体的小区或村镇名称。", "三明龙溪城区东三路"),
            ("4号", "我记录的地址信息是：三明龙溪城区东三路4号，请您再说一下具体的小区或村镇名称。", "三明龙溪城区东三路4号"),
        ]

        last_unmatched = ""
        similar_count = 0
        for turn_index, (user_input, expected_reply, expected_last_unmatched) in enumerate(turns):
            llm_result = {
                "matched_index": -1,
                "match_count": 0,
                "is_completed": False,
                "reply": "好的，请您再说一下具体的小区或村镇名称。",
                "is_extract_failed": False,
            }
            if turn_index >= 2:
                llm_result.update({
                    "matched_index": 0,
                    "match_count": 1,
                    "reply": "",
                })

            result = main(
                matched_index=-1,
                state="matching",
                meaningless_result={"is_meaningless": False, "reply": ""},
                llm_result=llm_result,
                clean_user_input=user_input,
                last_unmatched_address=last_unmatched,
                similar_no_match_count=similar_count,
                address_list=address_list,
            )

            self.assertEqual(result["llm_result"]["matched_index"], -1)
            self.assertEqual(result["llm_result"]["match_count"], 0)
            self.assertEqual(result["llm_result"]["reply"], expected_reply)
            self.assertEqual(result["next_last_unmatched_address"], expected_last_unmatched)
            self.assertEqual(result["next_similar_no_match_count"], 0)

            last_unmatched = result["next_last_unmatched_address"]
            similar_count = result["next_similar_no_match_count"]


if __name__ == "__main__":
    unittest.main()
