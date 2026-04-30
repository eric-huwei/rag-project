import re
from difflib import SequenceMatcher

def main(
    llm_result: dict,
    meaningless_result: dict = None,
    state: str = "matching",
    matched_index: int = -1,
    clean_user_input: str = "",
    last_unmatched_address: str = "",
    similar_no_match_count: int = 0,
    address_list: list = None
) -> dict:
    if not isinstance(llm_result, dict):
        llm_result = {}
    if not isinstance(meaningless_result, dict):
        meaningless_result = {}
    if not isinstance(address_list, list):
        address_list = []

    NON_MERGE_HISTORY_PREFIX = "__NO_MERGE__:"

    def _to_int(value, default):
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def _to_bool(value, default=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "是", "对"}:
                return True
            if normalized in {"false", "0", "no", "n", "否", "不是", ""}:
                return False
        return default

    def _to_str(value, default=""):
        if value is None:
            return default
        return str(value).strip()

    def _is_non_merge_history(text: str) -> bool:
        return _to_str(text).startswith(NON_MERGE_HISTORY_PREFIX)

    def _strip_non_merge_history(text: str) -> str:
        text = _to_str(text)
        if _is_non_merge_history(text):
            return text[len(NON_MERGE_HISTORY_PREFIX):].strip()
        return text

    def _mark_non_merge_history(text: str) -> str:
        text = _strip_non_merge_history(text)
        return f"{NON_MERGE_HISTORY_PREFIX}{text}" if text else ""

    def _normalize_text(text: str) -> str:
        text = _to_str(text)
        text = re.sub(r"\[拼音:.*?\]", "", text)
        text = text.replace("#", "号")
        text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
        return text.lower().strip()

    def _contains_any(text: str, words) -> bool:
        return any(word in text for word in words)

    def _normalize_cn_digits(text: str) -> str:
        text = _to_str(text)
        if not text or re.fullmatch(r"\d+", text):
            return text

        digit_map = {
            "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
        }
        unit_map = {"十": 10, "百": 100, "千": 1000}

        total = 0
        current = 0
        has_cn = False
        for ch in text:
            if ch in digit_map:
                current = digit_map[ch]
                has_cn = True
            elif ch in unit_map:
                has_cn = True
                if current == 0:
                    current = 1
                total += current * unit_map[ch]
                current = 0
            else:
                return text

        if not has_cn:
            return text
        total += current
        return str(total)

    def _looks_like_address(text: str) -> bool:
        t = _normalize_text(text)
        if not t:
            return False

        address_markers = [
            "省", "市", "区", "县", "旗",
            "镇", "乡", "街道", "街", "路", "大道", "巷", "胡同",
            "小区", "花园", "公寓", "大厦", "苑", "村",
            "栋", "幢", "座", "单元", "室", "号楼", "号院", "弄", "里"
        ]
        if _contains_any(t, address_markers):
            return True

        if re.search(r"\d+(号|栋|幢|座|单元|室|号楼|号院)", t):
            return True

        return False

    def _has_effective_address(text: str) -> bool:
        t = _normalize_text(text)
        if not t:
            return False

        effective_markers = [
            "小区", "花园", "公寓", "大厦", "苑", "村",
            "镇", "乡", "街道", "街", "路", "大道", "巷", "胡同",
            "栋", "幢", "座", "单元", "室", "号楼", "号院", "弄", "里"
        ]
        if _contains_any(t, effective_markers):
            return True

        if re.search(r"\d+(号|栋|幢|座|单元|室|号楼|号院)", t):
            return True

        return False

    def _is_layer_missing(text: str) -> bool:
        t = _normalize_text(text)
        if not t:
            return False

        if _has_effective_address(text):
            return False

        if _contains_any(t, ["省", "市", "区", "县", "旗"]):
            return True

        return False

    def _needs_specific_place_followup(text: str) -> bool:
        t = _normalize_text(text)
        if not t:
            return False

        if re.search(
            r"(小区|花园|公寓|大厦|苑|村|路|大道|巷|胡同|街(?!道)|栋|幢|座|单元|室|号楼|号院|弄|里|\d+号|\d+栋|\d+单元|\d+室)",
            t
        ):
            return False

        return bool(re.search(r"(省|市|区|县|旗|镇|乡|街道)", t))

    def _address_detail_level(text: str) -> int:
        """返回输入中已出现的最高地址层级，层级定义见地址分级规则。"""
        t = _normalize_text(text)
        if not t:
            return 0

        level = 0
        if re.search(r"(省|自治区|直辖市|特别行政区)", t):
            level = max(level, 1)
        if re.search(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}市", t):
            level = max(level, 2)
        if re.search(r"(区|县|旗)", t):
            level = max(level, 3)
        if re.search(r"(街道|镇|乡)", t):
            level = max(level, 4)
        if re.search(r"(社区|村组|村|路|大道|巷|胡同|街(?!道)|弄|里)", t):
            level = max(level, 5)
        if re.search(r"(小区|花园|公寓|大厦|楼宇|苑)", t):
            level = max(level, 6)
        if re.search(r"(\d+(?:栋|幢|座|号楼|楼|单元|室|号院|号)|[A-Za-z]\d*(?:栋|幢|座))", t):
            level = max(level, 7)

        return level

    def _is_exact_layer_reply(text: str) -> bool:
        text = _to_str(text)
        return text == "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"

    def _is_similar(a: str, b: str) -> bool:
        na, nb = _normalize_text(a), _normalize_text(b)
        if not na or not nb:
            return False
        if na == nb or na in nb or nb in na:
            return True
        return SequenceMatcher(None, na, nb).ratio() >= 0.78

    def _token_overlap(a_list, b_list):
        if not a_list or not b_list:
            return False
        for a in a_list:
            for b in b_list:
                na, nb = _normalize_text(a), _normalize_text(b)
                if na == nb or na in nb or nb in na:
                    return True
                if SequenceMatcher(None, na, nb).ratio() >= 0.8:
                    return True
        return False

    def _is_false_district_token(token: str) -> bool:
        token = _to_str(token)
        return any(word in token for word in ("小区", "社区", "园区", "校区", "景区", "厂区"))

    def _extract_conflict_tokens(text: str) -> dict:
        text = _to_str(text)
        tokens = {
            "province": [],
            "city": [],
            "district": [],
            "town": [],
            "road": [],
            "community": []
        }
        if not text:
            return tokens

        rest = text

        province_match = re.match(
            r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省))",
            rest
        )
        if province_match:
            tokens["province"].append(province_match.group(1))
            rest = rest[province_match.end():]

        city_match = re.match(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}?市)", rest)
        if city_match:
            tokens["city"].append(city_match.group(1))
            rest = rest[city_match.end():]

        district_match = re.match(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗))", rest)
        if district_match:
            district = district_match.group(1)
            if not _is_false_district_token(district):
                tokens["district"].append(district)
                rest = rest[district_match.end():]

        town_match = re.match(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:街道|镇|乡))", rest)
        if town_match:
            tokens["town"].append(town_match.group(1))
            rest = rest[town_match.end():]

        road = _extract_road_name(text)
        if road:
            tokens["road"].append(road)

        community = _extract_community_name(text)
        if community:
            tokens["community"].append(community)

        return tokens

    def _has_any_core_region_overlap(user_text: str, address_list: list) -> bool:
        user_tokens = _extract_conflict_tokens(user_text)
        if not any(user_tokens[level] for level in ("province", "city", "district")):
            return False

        for address in address_list or []:
            cand_tokens = _extract_conflict_tokens(address)
            for level in ("province", "city", "district"):
                if user_tokens[level] and cand_tokens[level] and _token_overlap(user_tokens[level], cand_tokens[level]):
                    return True
        return False

    def _has_place_anchor(text: str) -> bool:
        return bool(_extract_community_name(text) or _extract_road_name(text))

    def _has_building_or_room(text: str) -> bool:
        return bool(_extract_building_name(text) or _extract_room_name(text) or _extract_unit_name(text))

    def _has_precise_detail_conflict(user_text: str, candidate_text: str) -> bool:
        user_text = _to_str(user_text)
        candidate_text = _to_str(candidate_text)
        if not user_text or not candidate_text:
            return False

        detail_extractors = (
            _extract_building_name,
            _extract_unit_name,
            _extract_room_name,
            _extract_house_name,
        )
        for extractor in detail_extractors:
            user_value = extractor(user_text)
            if not user_value:
                continue
            candidate_value = extractor(candidate_text)
            if candidate_value and candidate_value != user_value:
                return True

        return False

    def _has_strong_conflict(user_text: str, candidate_text: str) -> bool:
        user_text = _to_str(user_text)
        candidate_text = _to_str(candidate_text)
        if not user_text or not candidate_text:
            return False

        mismatch_count = 0

        user_tokens = _extract_conflict_tokens(user_text)
        candidate_tokens = _extract_conflict_tokens(candidate_text)
        for level in ("province", "city", "district", "town", "road", "community"):
            u_tokens = user_tokens[level]
            c_tokens = candidate_tokens[level]
            if u_tokens and c_tokens and not _token_overlap(u_tokens, c_tokens):
                mismatch_count += 1

        user_build = re.findall(r"(\d+)(?:栋|幢|座|号楼|号)", user_text)
        cand_build = re.findall(r"(\d+)(?:栋|幢|座|号楼|号)", candidate_text)
        if user_build and cand_build and not (set(user_build) & set(cand_build)):
            mismatch_count += 1

        user_room = re.findall(r"(?<!\d)(\d{3,6})(?!\d)", user_text)
        cand_room = re.findall(r"(?<!\d)(\d{3,6})(?!\d)", candidate_text)
        if user_room and cand_room and not (set(user_room) & set(cand_room)):
            mismatch_count += 1

        return mismatch_count >= 2

    def _strip_broad_region_prefix(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        pattern = re.compile(
            r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}(?:省|市|县|旗|镇|乡|街道)"
        )

        last_end = 0
        for m in pattern.finditer(text):
            last_end = m.end()

        if last_end and last_end < len(text):
            return text[last_end:]
        return text

    def _extract_community_name(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        stripped = _strip_broad_region_prefix(text)

        matches = []
        pattern = re.compile(
            r"(?=([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:小区|花园|公寓|大厦|苑|村)))"
        )

        for m in pattern.finditer(stripped):
            seg = m.group(1)
            if seg:
                matches.append(seg)

        if not matches:
            return ""

        matches = sorted(set(matches), key=len)
        return matches[0]

    def _extract_city_prefix(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        m = re.search(r"^([\u4e00-\u9fa5A-Za-z0-9]{2,20}?(?:省)?[\u4e00-\u9fa5A-Za-z0-9]{2,12}市)", text)
        return m.group(1) if m else ""

    def _extract_building_name(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""
        m = re.search(r"((?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼))", text)
        if not m:
            return ""
        raw = m.group(1)
        m2 = re.match(r"((?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*))(栋|幢|座|号楼|楼)", raw)
        if not m2:
            return raw
        return f"{_normalize_cn_digits(m2.group(1))}{m2.group(2)}"

    def _extract_unit_name(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""
        m = re.search(r"(\d+单元)", text)
        return m.group(1) if m else ""

    def _extract_room_name(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        m = re.search(r"(\d+室)", text)
        if m:
            return m.group(1)

        tmp = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼)", "", text)
        tmp = re.sub(r"\d+单元", "", tmp)
        nums = re.findall(r"(?<!\d)(\d{3,6})(?!\d)", tmp)
        return nums[-1] if nums else ""

    def _is_fragment_like(text: str) -> bool:
        t = _normalize_text(text)
        if not t:
            return False

        has_detail = bool(re.search(
            r"(小区|花园|公寓|大厦|苑|村|路|大道|巷|胡同|街|栋|幢|座|单元|室|号楼|号院|\d+号|\d+栋|\d+单元|\d+室)",
            t
        ))
        has_broad_region = bool(re.search(
            r"(省|市|县|旗|镇|乡|街道)",
            t
        ))
        return has_detail and not has_broad_region

    def _admin_region_rank(text: str) -> int:
        text = _to_str(text)
        if not text:
            return 0
        if re.search(r"(街道|镇|乡)", text):
            return 4
        if re.search(r"(区|县|旗)", text):
            return 3
        if re.search(r"市", text):
            return 2
        if re.search(r"(省|自治区|特别行政区)", text):
            return 1
        return 0

    def _should_merge_region_continuation(prev_text: str, curr_text: str) -> bool:
        prev_text = _to_str(prev_text)
        curr_text = _to_str(curr_text)
        if not prev_text or not curr_text:
            return False

        if not _needs_specific_place_followup(curr_text):
            return False

        prev_rank = _admin_region_rank(prev_text)
        curr_rank = _admin_region_rank(curr_text)
        if prev_rank <= 0 or curr_rank <= prev_rank:
            return False

        prev_norm = _normalize_text(prev_text)
        curr_norm = _normalize_text(curr_text)
        if not prev_norm or not curr_norm:
            return False

        if curr_norm == prev_norm or curr_norm in prev_norm or prev_norm in curr_norm:
            return False

        return True

    def _is_extension_of_previous(curr: str, prev: str) -> bool:
        ncur, nprev = _normalize_text(curr), _normalize_text(prev)
        return bool(nprev and ncur.startswith(nprev) and len(ncur) > len(nprev))

    def _extract_road_name(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        stripped = _strip_broad_region_prefix(text)
        community = _extract_community_name(stripped)
        if community and community in stripped:
            stripped = stripped[stripped.index(community) + len(community):]

        matches = []
        pattern = re.compile(
            r"(?=([\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857(?!\u9053))))"
        )

        for m in pattern.finditer(stripped):
            seg = m.group(1)
            if seg:
                matches.append(seg)

        if not matches:
            return ""

        matches = sorted(set(matches), key=len)
        return matches[0]

    def _extract_house_name(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        m = re.search("(\\d+\u53f7\u9662|\\d+\u53f7(?!\u697c|\u680b|\u5e62|\u5355\u5143|\u5ba4)|\\d+\u5f04|\\d+\u91cc)", text)
        return m.group(1) if m else ""

    def _extract_address_prefix(text: str, anchor: str) -> str:
        text = _to_str(text)
        anchor = _to_str(anchor)
        if not text or not anchor:
            return ""

        idx = text.find(anchor)
        if idx >= 0:
            return text[:idx]
        return ""

    def _build_recorded_address(
        current_input: str,
        prev_unmatched: str,
        fallback_text: str = ""
    ) -> str:
        current_input = _to_str(current_input)
        prev_unmatched = _to_str(prev_unmatched)
        fallback_text = _to_str(fallback_text)

        return current_input or prev_unmatched or fallback_text

    def _find_precise_unique_match(current_input: str, address_list: list) -> int:
        current_input = _to_str(current_input)
        if not current_input or not isinstance(address_list, list):
            return -1

        user_community = _extract_community_name(current_input)
        user_road = _extract_road_name(current_input)
        user_building = _extract_building_name(current_input)
        user_unit = _extract_unit_name(current_input)
        user_room = _extract_room_name(current_input)
        user_house = _extract_house_name(current_input)
        named_place_fragments = []
        if not (user_community or user_road):
            raw_named_place_fragment = _extract_named_place_fragment(current_input)
            stripped_named_place_fragment = _strip_leading_admin_tokens(raw_named_place_fragment)
            for value in (raw_named_place_fragment, stripped_named_place_fragment):
                value = _to_str(value)
                if value and value not in named_place_fragments:
                    named_place_fragments.append(value)

        if not (user_community or user_road or named_place_fragments):
            return -1
        if not any([user_building, user_unit, user_room, user_house]):
            return -1

        matched_indexes = []
        for idx, address in enumerate(address_list):
            candidate = _to_str(address)
            if not candidate or _has_strong_conflict(current_input, candidate):
                continue

            candidate_norm = _normalize_text(candidate)

            if user_community:
                candidate_community = _extract_community_name(candidate)
                user_community_norm = _normalize_text(user_community)
                if not (
                    (candidate_community and _is_similar(user_community, candidate_community))
                    or (user_community_norm and user_community_norm in candidate_norm)
                ):
                    continue

            if user_road:
                candidate_road = _extract_road_name(candidate)
                user_road_norm = _normalize_text(user_road)
                if not (
                    (candidate_road and _is_similar(user_road, candidate_road))
                    or (user_road_norm and user_road_norm in candidate_norm)
                ):
                    continue

            if named_place_fragments:
                named_place_norms = [
                    _normalize_text(fragment)
                    for fragment in named_place_fragments
                    if _normalize_text(fragment)
                ]
                if not any(named_place_norm in candidate_norm for named_place_norm in named_place_norms):
                    continue

            if user_building and _extract_building_name(candidate) != user_building:
                continue
            if user_unit and _extract_unit_name(candidate) != user_unit:
                continue
            if user_room and _extract_room_name(candidate) != user_room:
                continue
            if user_house and _extract_house_name(candidate) != user_house:
                continue

            matched_indexes.append(idx)

        return matched_indexes[0] if len(matched_indexes) == 1 else -1

    def _extract_recorded_address_from_reply(reply_text: str) -> str:
        prefix = "我记录的地址信息是："
        reply_text = _to_str(reply_text)
        if not reply_text.startswith(prefix):
            return ""

        body = reply_text[len(prefix):].strip()
        for marker in ("，请", "。请", ",请"):
            idx = body.find(marker)
            if idx > 0:
                return body[:idx].strip()
        return body

    def _sanitize_recorded_address(recorded_address: str, current_input: str, prev_unmatched: str = "") -> str:
        recorded_address = _to_str(recorded_address)
        current_input = _to_str(current_input)
        prev_unmatched = _to_str(prev_unmatched)
        if not recorded_address or not current_input:
            return recorded_address

        recorded_norm = _normalize_text(recorded_address)

        expected_inputs = [current_input]
        if prev_unmatched:
            current_norm = _normalize_text(current_input)
            prev_norm = _normalize_text(prev_unmatched)
            if current_norm and prev_norm and not current_norm.startswith(prev_norm):
                expected_inputs.insert(0, f"{prev_unmatched}{current_input}")

        for expected_input in expected_inputs:
            expected_norm = _normalize_text(expected_input)
            if recorded_norm and expected_norm and recorded_norm.startswith(expected_norm) and recorded_norm != expected_norm:
                return expected_input

        return recorded_address

    def _is_weak_area_fragment(text: str) -> bool:
        text = _to_str(text)
        if not text:
            return False
        return bool(re.fullmatch(r"(东|西|南|北|中)(区|侧|门)?|[A-Za-z]区|[一二三四五六七八九十0-9]+区", text))

    def _address_signal_score(text: str) -> int:
        text = _to_str(text)
        norm = _normalize_text(text)
        if not norm:
            return -1
        if _is_weak_area_fragment(text):
            return 0

        level_score = _address_detail_level(text) * 20
        length_score = min(len(norm), 20)
        if level_score == 0 and len(norm) >= 4:
            return length_score
        return level_score + length_score

    def _extract_named_place_fragment(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        fragment = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼)", "", text)
        fragment = re.sub(r"\d+单元", "", fragment)
        fragment = re.sub(r"\d+室", "", fragment)
        fragment = re.sub(r"(?<!\d)\d{3,6}(?!\d)", "", fragment)
        fragment = re.sub(r"(\d+号院|\d+号(?!楼|栋|幢|单元|室)|\d+弄|\d+里)", "", fragment)
        return fragment.strip()

    def _strip_leading_admin_tokens(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        patterns = (
            (r"^([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省))", None),
            (r"^([\u4e00-\u9fa5A-Za-z0-9]{2,12}?市)", None),
            (r"^([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗))", _is_false_district_token),
            (r"^([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:街道|镇|乡))", None),
        )

        stripped = text
        changed = True
        while changed and stripped:
            changed = False
            for pattern, skip_fn in patterns:
                match = re.match(pattern, stripped)
                if not match:
                    continue
                token = match.group(1)
                if skip_fn and skip_fn(token):
                    continue
                stripped = stripped[match.end():]
                changed = True
                break

        return stripped.strip()

    def _has_named_place_anchor(text: str) -> bool:
        fragment = _strip_leading_admin_tokens(_extract_named_place_fragment(text))
        fragment_norm = _normalize_text(fragment)
        if len(fragment_norm) < 4:
            return False
        return not _is_weak_area_fragment(fragment)

    def _should_reject_place_less_unique_match(candidate_input: str) -> bool:
        candidate_input = _to_str(candidate_input)
        if not candidate_input:
            return False

        has_specific_detail = bool(
            _has_building_or_room(candidate_input) or _extract_house_name(candidate_input)
        )
        if not has_specific_detail:
            return False

        if _has_place_anchor(candidate_input) or _has_named_place_anchor(candidate_input):
            return False

        return True

    def _replace_recorded_address_in_reply(reply_text: str, old_address: str, new_address: str) -> str:
        reply_text = _to_str(reply_text)
        old_address = _to_str(old_address)
        new_address = _to_str(new_address)
        if not reply_text or not old_address or not new_address or old_address == new_address:
            return reply_text
        return reply_text.replace(old_address, new_address, 1)

    def _prefer_recorded_followup(
        recorded_address: str,
        recorded_reply: str,
        custom_address: str = "",
        custom_reply: str = "",
        prev_unmatched: str = "",
        current_input: str = ""
    ) -> tuple[str, str]:
        recorded_address = _to_str(recorded_address)
        recorded_reply = _to_str(recorded_reply)
        custom_address = _to_str(custom_address)
        custom_reply = _to_str(custom_reply)
        prev_unmatched = _to_str(prev_unmatched)
        current_input = _to_str(current_input)

        best_address = recorded_address
        best_reply = recorded_reply
        best_score = _address_signal_score(recorded_address)

        candidates = []
        if custom_address and custom_reply:
            candidates.append((custom_address, custom_reply))

        if _is_weak_area_fragment(recorded_address):
            if prev_unmatched:
                candidates.append((
                    prev_unmatched,
                    _replace_recorded_address_in_reply(recorded_reply, recorded_address, prev_unmatched)
                ))
            if current_input:
                candidates.append((
                    current_input,
                    _replace_recorded_address_in_reply(recorded_reply, recorded_address, current_input)
                ))

        for candidate_address, candidate_reply in candidates:
            candidate_score = _address_signal_score(candidate_address)
            if candidate_score > best_score:
                best_address = candidate_address
                best_reply = candidate_reply
                best_score = candidate_score

        return best_address, best_reply

    def _filter_by_named_place_fragment(fragment: str, addresses: list) -> list:
        fragment_norms = []
        for value in (_to_str(fragment), _strip_leading_admin_tokens(fragment)):
            norm = _normalize_text(value)
            if len(norm) >= 4 and norm not in fragment_norms:
                fragment_norms.append(norm)

        if not fragment_norms:
            return []
        return [
            address for address in addresses
            if any(fragment_norm in _normalize_text(address) for fragment_norm in fragment_norms)
        ]

    def _should_restart_matching_from_completed(text: str, addresses: list) -> bool:
        text = _to_str(text)
        if not text:
            return False
        return bool(
            _looks_like_address(text)
            or _needs_specific_place_followup(text)
            or _filter_by_named_place_fragment(text, addresses)
        )

    def _build_precise_followup(prev_unmatched: str, current_input: str, address_list: list):
        if not isinstance(address_list, list) or len(address_list) < 2:
            return "", ""

        normalized_addresses = []
        for addr in address_list:
            addr_text = _to_str(addr)
            if addr_text:
                normalized_addresses.append(addr_text)

        if len(normalized_addresses) < 2:
            return "", ""

        user_fragment = current_input
        if _is_extension_of_previous(current_input, prev_unmatched):
            user_fragment = current_input[len(prev_unmatched):]

        user_community = _extract_community_name(user_fragment) or _extract_community_name(current_input)
        current_road = _extract_road_name(current_input)
        current_building = _extract_building_name(current_input)
        current_unit = _extract_unit_name(current_input)
        current_room = _extract_room_name(current_input)
        current_house = _extract_house_name(current_input)

        # ????/?/?/????????????????????
        if not any([user_community, current_road, current_building, current_unit, current_room, current_house]):
            if _needs_specific_place_followup(current_input):
                return "", ""

            named_place_filtered = (
                _filter_by_named_place_fragment(user_fragment, normalized_addresses)
                or _filter_by_named_place_fragment(current_input, normalized_addresses)
            )
            if named_place_filtered:
                recorded_address = _build_recorded_address(
                    current_input,
                    prev_unmatched,
                    user_fragment
                )
                reply = f"我记录的地址信息是：{recorded_address}，请您再提供下楼栋号、单元号及门牌号信息"
                return reply, recorded_address
            return "", ""

        filtered = normalized_addresses
        if user_community:
            community_filtered = []
            target_norm = _normalize_text(user_community)
            for addr in filtered:
                addr_community = _extract_community_name(addr)
                if addr_community and _is_similar(addr_community, user_community):
                    community_filtered.append(addr)
                elif target_norm and target_norm in _normalize_text(addr):
                    community_filtered.append(addr)
            if community_filtered:
                filtered = community_filtered

        candidate_communities = list(dict.fromkeys([
            c for c in (_extract_community_name(addr) for addr in filtered) if c
        ]))

        if user_community:
            if not candidate_communities:
                return "", ""
            candidate_community = candidate_communities[0]
        else:
            if current_road:
                candidate_community = current_road
            elif len(candidate_communities) != 1:
                return "", ""
            else:
                candidate_community = candidate_communities[0]

        if user_community and not _is_similar(user_community, candidate_community):
            if not (prev_unmatched and len(candidate_communities) == 1):
                return "", ""

        if current_road:
            road_filtered = []
            road_norm = _normalize_text(current_road)
            for addr in filtered:
                addr_road = _extract_road_name(addr)
                if addr_road and (_is_similar(addr_road, current_road) or road_norm in _normalize_text(addr)):
                    road_filtered.append(addr)
            if road_filtered:
                filtered = road_filtered

        if current_building:
            filtered = [addr for addr in filtered if _extract_building_name(addr) == current_building]
            if not filtered:
                return "", ""

        if current_unit:
            filtered = [addr for addr in filtered if _extract_unit_name(addr) == current_unit]
            if not filtered:
                return "", ""

        if current_room:
            return "", ""

        candidate_buildings = list(dict.fromkeys([
            b for b in (_extract_building_name(addr) for addr in filtered) if b
        ]))
        candidate_units = list(dict.fromkeys([
            u for u in (_extract_unit_name(addr) for addr in filtered) if u
        ]))
        candidate_rooms = list(dict.fromkeys([
            r for r in (_extract_room_name(addr) for addr in filtered) if r
        ]))
        candidate_roads = list(dict.fromkeys([
            r for r in (_extract_road_name(addr) for addr in filtered) if r
        ]))
        candidate_houses = list(dict.fromkeys([
            h for h in (_extract_house_name(addr) for addr in filtered) if h
        ]))

        place_is_village = candidate_community.endswith("\u6751")
        reference_address = filtered[0] if filtered else normalized_addresses[0]

        if current_building:
            recorded_address = _build_recorded_address(
                current_input,
                prev_unmatched,
                candidate_community
            )

            if current_unit and len(candidate_rooms) >= 2:
                reply = f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息"
                return reply, recorded_address

            if len(candidate_units) >= 2:
                reply = f"我记录的地址信息是：{recorded_address}，请您再提供下单元号及门牌号信息"
                return reply, recorded_address

            if len(candidate_rooms) >= 2 or len(filtered) >= 2:
                if current_unit:
                    reply = f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息"
                else:
                    reply = f"我记录的地址信息是：{recorded_address}，请您再提供下单元号及门牌号信息"
                return reply, recorded_address

            return "", ""

        if current_road:
            recorded_address = _build_recorded_address(
                current_input,
                prev_unmatched,
                candidate_community
            )

            if current_house:
                return "", ""

            if len(candidate_houses) >= 2 or len(filtered) >= 2:
                reply = f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息"
                return reply, recorded_address

        if place_is_village or (not candidate_buildings and candidate_roads):
            recorded_address = _build_recorded_address(
                current_input,
                prev_unmatched,
                candidate_community
            )
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u63d0\u4f9b\u4e0b\u8857\u9053\u540d\u79f0\u53ca\u95e8\u724c\u53f7\u4fe1\u606f"
            return reply, recorded_address

        if len(candidate_buildings) == 1:
            recorded_address = _build_recorded_address(
                current_input,
                prev_unmatched,
                candidate_community
            )
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u63d0\u4f9b\u4e0b\u697c\u680b\u53f7\u3001\u5355\u5143\u53f7\u53ca\u95e8\u724c\u53f7\u4fe1\u606f"
            return reply, recorded_address

        recorded_address = _build_recorded_address(
                current_input,
                prev_unmatched,
                candidate_community
            )
        reply = f"我记录的地址信息是：{recorded_address}，请您再提供下楼栋号、单元号及门牌号信息"
        return reply, recorded_address

    current_raw_input = _to_str(clean_user_input)
    raw_state = (state or "").strip() or "matching"
    current_state = (
        "matching"
        if raw_state == "completed" and _should_restart_matching_from_completed(current_raw_input, address_list)
        else raw_state
    )
    current_matched_index = -1 if current_state == "matching" else _to_int(matched_index, -1)

    prev_unmatched_raw = _to_str(last_unmatched_address)
    prev_unmatched = _strip_non_merge_history(prev_unmatched_raw)
    mergeable_prev_unmatched = "" if _is_non_merge_history(prev_unmatched_raw) else prev_unmatched

    current_input = current_raw_input
    should_merge_named_place_with_previous = bool(
        mergeable_prev_unmatched
        and current_raw_input
        and _has_named_place_anchor(current_raw_input)
        and _has_building_or_room(mergeable_prev_unmatched)
    )
    if mergeable_prev_unmatched and current_raw_input and (
        _is_fragment_like(current_raw_input) or should_merge_named_place_with_previous
    ):
        ncur = _normalize_text(current_raw_input)
        nprev = _normalize_text(mergeable_prev_unmatched)

        if ncur == nprev or ncur in nprev:
            current_input = mergeable_prev_unmatched
        elif nprev and nprev in ncur:
            current_input = current_raw_input
        elif (
            (_has_place_anchor(current_raw_input) or _has_named_place_anchor(current_raw_input))
            and _has_building_or_room(mergeable_prev_unmatched)
        ):
            current_input = f"{mergeable_prev_unmatched}{current_raw_input}"
        else:
            current_input = f"{mergeable_prev_unmatched}{current_raw_input}"
    elif mergeable_prev_unmatched and current_raw_input and _should_merge_region_continuation(mergeable_prev_unmatched, current_raw_input):
        current_input = f"{mergeable_prev_unmatched}{current_raw_input}"

    prev_repeat_count = max(_to_int(similar_no_match_count, 0), 0)

    meaningless_flag = _to_bool(
        meaningless_result.get(
            "is_meaningless",
            meaningless_result.get("meaningless", meaningless_result.get("is_irrelevant", False))
        )
    )
    meaningless_reply = _to_str(meaningless_result.get("reply"))

    if meaningless_flag and current_input and _looks_like_address(current_input):
        meaningless_flag = False
        meaningless_reply = ""

    if meaningless_flag:
        if current_state == "confirming" and current_matched_index >= 0:
            llm_result = {
                "match_count": 1,
                "matched_index": current_matched_index,
                "is_completed": False,
                "is_extract_failed": False,
                "reply": ""
            }
        else:
            llm_result = {
                "match_count": 0,
                "matched_index": -1,
                "is_completed": False,
                "is_extract_failed": False,
                "reply": meaningless_reply or "请您提供详细的地址信息"
            }
        return {
            "llm_result": llm_result,
            "next_last_unmatched_address": prev_unmatched_raw,
            "next_similar_no_match_count": prev_repeat_count
        }

    match_count = max(_to_int(llm_result.get("match_count"), 0), 0)
    llm_matched_index = _to_int(llm_result.get("matched_index"), -1)
    is_completed = _to_bool(llm_result.get("is_completed", False))
    is_extract_failed = _to_bool(llm_result.get("is_extract_failed", llm_result.get("extract_failed", False)))
    reply = _to_str(llm_result.get("reply"))
    recorded_address_from_reply = _extract_recorded_address_from_reply(reply)
    sanitized_recorded_address = _sanitize_recorded_address(
        recorded_address_from_reply,
        current_input,
        mergeable_prev_unmatched
    )
    if sanitized_recorded_address != recorded_address_from_reply:
        reply = _replace_recorded_address_in_reply(
            reply,
            recorded_address_from_reply,
            sanitized_recorded_address
        )
        recorded_address_from_reply = sanitized_recorded_address

    strong_conflict_demoted = False

    if llm_matched_index >= 0 and 0 <= llm_matched_index < len(address_list):
        selected_address = _to_str(address_list[llm_matched_index])
        if (
            _has_strong_conflict(current_input, selected_address)
            or _has_precise_detail_conflict(current_input, selected_address)
        ):
            llm_matched_index = -1
            match_count = 0
            is_completed = False
            reply = ""
            strong_conflict_demoted = True

    if strong_conflict_demoted and prev_unmatched and _is_similar(current_input, prev_unmatched) and not _is_extension_of_previous(current_input, prev_unmatched):
        is_extract_failed = True
        match_count = 0
        llm_matched_index = -1
        is_completed = False
        reply = ""

    if is_extract_failed:
        match_count = 0
        llm_matched_index = -1
        is_completed = False
        reply = ""

    if match_count == 1 and llm_matched_index < 0:
        if current_state == "confirming" and current_matched_index >= 0:
            llm_matched_index = current_matched_index
        else:
            match_count = 0

    if match_count >= 2 and llm_matched_index >= 0:
        llm_matched_index = -1
        is_completed = False

    if is_completed and llm_matched_index < 0:
        if current_state == "confirming" and current_matched_index >= 0:
            llm_matched_index = current_matched_index
            match_count = 1
        else:
            is_completed = False

    if llm_matched_index >= 0 and match_count <= 0:
        match_count = 1

    if (
        current_state == "matching"
        and llm_matched_index >= 0
        and match_count == 1
        and _should_reject_place_less_unique_match(current_input)
    ):
        llm_matched_index = -1
        match_count = 0
        is_completed = False
        reply = ""

    precise_matched_index = -1
    if current_state == "matching" and not is_completed and not is_extract_failed:
        precise_matched_index = _find_precise_unique_match(current_input, address_list)
        if precise_matched_index >= 0 and (
            llm_matched_index < 0
            or match_count == 0
            or llm_matched_index != precise_matched_index
        ):
            llm_matched_index = precise_matched_index
            match_count = 1
            reply = ""

    next_last_unmatched_address = ""
    next_similar_no_match_count = 0

    current_looks_like_address = _looks_like_address(current_input)
    current_is_layer_missing = _is_layer_missing(current_input)
    current_has_effective_address = _has_effective_address(current_input)
    current_address_level = _address_detail_level(current_input)
    should_echo_partial_address = bool(
        current_input
        and current_looks_like_address
        and _needs_specific_place_followup(current_input)
        and not (
            not mergeable_prev_unmatched
            and current_is_layer_missing
            and not _has_any_core_region_overlap(current_input, address_list)
        )
    )
    should_force_correct_complete = bool(
        not mergeable_prev_unmatched
        and current_is_layer_missing
        and not _has_any_core_region_overlap(current_input, address_list)
    )

    custom_followup_reply = ""
    custom_recorded_address = ""
    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed:
        custom_followup_reply, custom_recorded_address = _build_precise_followup(
            mergeable_prev_unmatched,
            current_input,
            address_list
        )
        if recorded_address_from_reply:
            recorded_address_from_reply, reply = _prefer_recorded_followup(
                recorded_address_from_reply,
                reply,
                custom_recorded_address,
                custom_followup_reply,
                mergeable_prev_unmatched,
                current_input
            )

    should_track_unmatched = (
        current_state == "matching"
        and llm_matched_index < 0
        and match_count == 0
        and not is_completed
        and bool(current_input)
        and (current_looks_like_address or bool(recorded_address_from_reply) or bool(custom_recorded_address))
    )
    should_reset_unmatched_for_broad_no_overlap = (
        should_track_unmatched
        and not mergeable_prev_unmatched
        and current_is_layer_missing
        and not _has_any_core_region_overlap(current_input, address_list)
    )

    if should_track_unmatched:
        if prev_unmatched and _is_similar(current_input, prev_unmatched) and not _is_extension_of_previous(current_input, prev_unmatched):
            is_extract_failed = True
            match_count = 0
            llm_matched_index = -1
            is_completed = False
            reply = ""
            next_last_unmatched_address = ""
            next_similar_no_match_count = 0
        elif should_reset_unmatched_for_broad_no_overlap:
            next_last_unmatched_address = _mark_non_merge_history(current_input)
            next_similar_no_match_count = 1
        else:
            next_last_unmatched_address = (
                recorded_address_from_reply
                or custom_recorded_address
                or current_input
            )
            next_similar_no_match_count = 1
    else:
        if llm_matched_index >= 0 or is_completed:
            next_last_unmatched_address = ""
            next_similar_no_match_count = 0
        else:
            next_last_unmatched_address = prev_unmatched_raw
            next_similar_no_match_count = prev_repeat_count

    REPLY_LAYER = "好的，请您再说一下具体的小区或村镇名称。"
    REPLY_DETAIL = "请您提供详细的地址信息"
    REPLY_CORRECT = "请您提供正确完整的地址信息"

    reply_alias_map = {
        "好的，请您再说一下具体的小区或村镇名称": REPLY_LAYER,
        "请您提供详细的地址信息。": REPLY_DETAIL,
        "请您提供详细地址信息": REPLY_DETAIL,
        "请您提供正确的地址信息": REPLY_CORRECT,
        "请您提供正确的地址信息。": REPLY_CORRECT,
        "请您提供正确完整的地址信息。": REPLY_CORRECT
    }
    reply = reply_alias_map.get(reply, reply)

    forbidden_matching_replies = {
        "好的，请您再重新说一下报修宽带所在小区或村镇名称。",
        "好的，请您再重新说一下报修宽带所在小区或村镇名称"
    }
    if reply in forbidden_matching_replies:
        if current_state == "confirming":
            reply = REPLY_DETAIL
        elif current_state == "matching":
            reply = ""

    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed:
        if is_extract_failed:
            reply = ""
        elif recorded_address_from_reply:
            pass
        elif custom_followup_reply:
            reply = custom_followup_reply
        elif (
            current_looks_like_address
            and _has_building_or_room(current_input)
            and not (_has_place_anchor(current_input) or _has_named_place_anchor(current_input))
        ):
            reply = f"我记录的地址信息是：{current_input}，请您再说一下具体的小区或村镇名称。"
        elif should_echo_partial_address:
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{current_input}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        elif reply == REPLY_LAYER or _is_exact_layer_reply(reply):
            if should_force_correct_complete:
                reply = REPLY_CORRECT
            elif current_address_level >= 5:
                reply = REPLY_CORRECT
        elif reply in {REPLY_DETAIL, REPLY_CORRECT}:
            if should_force_correct_complete:
                reply = REPLY_CORRECT
        else:
            if not current_input:
                reply = REPLY_DETAIL
            elif current_is_layer_missing:
                reply = REPLY_CORRECT if should_force_correct_complete else REPLY_LAYER
            elif current_looks_like_address:
                reply = REPLY_CORRECT
            else:
                reply = REPLY_DETAIL

    if current_state == "confirming" and current_matched_index >= 0:
        if not is_completed and match_count <= 0 and llm_matched_index < 0 and not reply and not is_extract_failed:
            llm_matched_index = current_matched_index
            match_count = 1

    if is_completed or is_extract_failed or (match_count == 1 and llm_matched_index >= 0):
        reply = ""

    llm_result["match_count"] = match_count
    llm_result["matched_index"] = llm_matched_index
    llm_result["is_completed"] = is_completed
    llm_result["is_extract_failed"] = is_extract_failed
    llm_result["reply"] = reply

    return {
        "llm_result": llm_result,
        "next_last_unmatched_address": next_last_unmatched_address,
        "next_similar_no_match_count": next_similar_no_match_count
    }
