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
            "我记录的地址信息是：北京市大同区，请您再说一下具体的小区或村镇名称。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "北京市大同区")
        self.assertEqual(result["next_similar_no_match_count"], 1)

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
        self.assertEqual(result["next_similar_no_match_count"], 1)

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
        self.assertEqual(result["next_last_unmatched_address"], "")

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
        self.assertEqual(result["next_last_unmatched_address"], "")

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
        self.assertEqual(result["next_last_unmatched_address"], "")

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
        self.assertEqual(result["next_last_unmatched_address"], "")
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
        self.assertEqual(result["next_similar_no_match_count"], 1)

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

    def test_recorded_reply_does_not_append_candidate_suffix(self) -> None:
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
            "我记录的地址信息是：福州市岳峰镇保利香槟，请您再说一下具体的单元号及门牌号。",
        )
        self.assertEqual(result["next_last_unmatched_address"], "福州市岳峰镇保利香槟")
        self.assertNotIn("国际东区三号楼", result["llm_result"]["reply"])

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
        self.assertEqual(result["next_similar_no_match_count"], 1)

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
        self.assertEqual(result["next_similar_no_match_count"], 1)

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
        self.assertEqual(result["next_last_unmatched_address"], "")
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
        self.assertEqual(result["next_last_unmatched_address"], "")
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
        self.assertEqual(result["next_last_unmatched_address"], "")
        self.assertEqual(result["next_similar_no_match_count"], 0)

    def test_road_only_gets_precise_followup_instead_of_correct_complete(self) -> None:
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
            "我记录的地址信息是：中山路，请您再提供下门牌号信息",
        )
        self.assertEqual(result["next_last_unmatched_address"], "中山路")
        self.assertEqual(result["next_similar_no_match_count"], 1)

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
        self.assertEqual(result["next_last_unmatched_address"], "")
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


if __name__ == "__main__":
    unittest.main()
