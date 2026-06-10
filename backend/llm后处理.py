import re
from difflib import SequenceMatcher

def main(
    llm_result: dict,
    meaningless_result: dict = None,
    state: str = "matching",
    matched_index: int = -1,
    clean_user_input: str = "",
    last_unmatched_address: str = "",
    last_unmatched_fragment: str = "",
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
        text = _normalize_address_marker_tokens(text)
        text = re.sub(r"\[拼音:.*?\]", "", text)
        text = text.replace("#", "号")
        text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
        return text.lower().strip()


    _CANONICAL_ADDRESS_MARKERS = ("号楼", "单元", "号院", "栋", "幢", "座", "楼", "室", "号", "弄", "里")

    def _normalize_address_marker_tokens(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        result = []
        markers = sorted(_CANONICAL_ADDRESS_MARKERS, key=len, reverse=True)
        prefix_pattern = r"(?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)$"
        i = 0
        while i < len(text):
            prefix = "".join(result)
            if prefix and re.search(prefix_pattern, prefix):
                replaced = False
                for marker in markers:
                    fragment = text[i:i + len(marker)]
                    if (
                        fragment == marker
                        and not (
                            marker in ("栋", "幢", "座", "楼")
                            and fragment != marker
                            and text[i + len(marker):i + len(marker) + 1] in {"区", "侧", "门"}
                        )
                    ):
                        result.append(marker)
                        i += len(marker)
                        replaced = True
                        break
                if replaced:
                    continue
            result.append(text[i])
            i += 1

        normalized = "".join(result)
        normalized = re.sub(r"((?<!\d)\d{3,6})栋(?=区)", r"\1东", normalized)
        return normalized
    def _contains_any(text: str, words) -> bool:
        return any(word in text for word in words)

    def _normalize_cn_digits(text: str) -> str:
        text = _to_str(text)
        if not text or re.fullmatch(r"\d+", text):
            return text

        digit_map = {
            "\u96f6": 0, "\u3007": 0, "\u4e00": 1, "\u4e8c": 2, "\u4e24": 2, "\u4e09": 3, "\u56db": 4,
            "\u4e94": 5, "\u516d": 6, "\u4e03": 7, "\u516b": 8, "\u4e5d": 9,
            "Áã": 0, "Ò»": 1, "¶þ": 2, "Á½": 2, "Èý": 3, "ËÄ": 4,
            "Îå": 5, "Áù": 6, "Æß": 7, "°Ë": 8, "¾Å": 9
        }
        unit_map = {"\u5341": 10, "\u767e": 100, "\u5343": 1000, "Ê®": 10, "°Ù": 100, "Ç§": 1000}

        if all(ch in digit_map for ch in text) and len(text) >= 2:
            return "".join(str(digit_map[ch]) for ch in text)

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

    def _extract_longest_place_token(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        stripped = _strip_broad_region_prefix(text)
        matches = []
        for pattern in (
            "[\u4e00-\u9fa5A-Za-z0-9]{2,30}(?:\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751)",
            "[\u4e00-\u9fa5A-Za-z0-9]{1,30}(?:\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857(?!\u9053))",
        ):
            matches.extend(re.findall(pattern, stripped))
        if matches:
            return max(matches, key=len)

        fragment = _strip_leading_admin_tokens(_extract_named_place_fragment(text))
        return fragment or stripped

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

    def _is_level5_place_only(text: str) -> bool:
        return (
            _address_detail_level(text) == 5
            and not (_has_building_or_room(text) or _extract_house_name(text))
        )

    def _is_similar(a: str, b: str) -> bool:
        na, nb = _normalize_text(a), _normalize_text(b)
        if not na or not nb:
            return False
        if na == nb or na in nb or nb in na:
            return True
        return False

    def _token_overlap(a_list, b_list):
        if not a_list or not b_list:
            return False
        for a in a_list:
            for b in b_list:
                na, nb = _normalize_text(a), _normalize_text(b)
                if na == nb or na in nb or nb in na:
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

    def _has_full_building_unit_room_detail(text: str) -> bool:
        text = _normalize_address_marker_tokens(_to_str(text))
        if not text or not _extract_building_name(text):
            return False

        has_unit = bool(re.search(r"(?:\d+|[一二三四五六七八九十百零两]+)单元", text))
        if not has_unit:
            return False

        text_without_building = re.sub(
            r"(?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼|号(?=(?:\d+单元|\d{3,6}(?:室)?)))",
            "",
            text,
            count=1
        )
        text_without_unit = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+)单元", "", text_without_building, count=1)
        return bool(
            _extract_room_name(text)
            or re.search(r"(?:\d{3,6}|[一二三四五六七八九十百零两]{3,6})室?", text_without_unit)
        )

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
            if extractor is _extract_building_name:
                user_value = _normalize_building_for_compare(user_value)
                candidate_value = _normalize_building_for_compare(candidate_value)
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
        text = _normalize_address_marker_tokens(text)
        if not text:
            return ""
        m = re.search(r"((?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼|号(?=(?:\d+单元|\d{3,6}(?:室)?))))", text)
        if not m:
            return ""
        raw = m.group(1)
        m2 = re.match(r"((?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*))(栋|幢|座|号楼|楼|号)", raw)
        if not m2:
            return raw
        return f"{_normalize_cn_digits(m2.group(1))}{m2.group(2)}"

    def _normalize_building_for_compare(value: str) -> str:
        value = _to_str(value)
        if not value:
            return ""

        m = re.fullmatch(r"((?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*))(栋|幢|座|号楼|楼|号)", value)
        if not m:
            return value
        return f"{_normalize_cn_digits(m.group(1))}楼"

    def _extract_unit_name(text: str) -> str:
        text = _to_str(text)
        text = _normalize_address_marker_tokens(text)
        if not text:
            return ""
        m = re.search(r"((?:\d+|[一二三四五六七八九十百零两]+)单元)", text)
        if not m:
            return ""
        m2 = re.match(r"((?:\d+|[一二三四五六七八九十百零两]+))单元", m.group(1))
        if not m2:
            return m.group(1)
        return f"{_normalize_cn_digits(m2.group(1))}单元"

    def _extract_room_name(text: str) -> str:
        text = _to_str(text)
        text = _normalize_address_marker_tokens(text)
        if not text:
            return ""

        m = re.search(r"((?:\d+|[一二三四五六七八九十百零两]{3,6})室)", text)
        if m:
            raw = m.group(1)
            m2 = re.match(r"((?:\d+|[一二三四五六七八九十百零两]{3,6}))室", raw)
            if not m2:
                return raw
            return _normalize_cn_digits(m2.group(1))

        tmp = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼)", "", text)
        tmp = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+)单元", "", tmp)
        nums = re.findall(r"(?<!\d)(\d{3,6})(?!\d)|([一二三四五六七八九十百零两]{3,6})", tmp)
        values = [num or cn_num for num, cn_num in nums if num or cn_num]
        return _normalize_cn_digits(values[-1]) if values else ""

    def _detail_values_covered(prev_text: str, curr_text: str) -> bool:
        prev_building = _normalize_building_for_compare(_extract_building_name(prev_text))
        curr_building = _normalize_building_for_compare(_extract_building_name(curr_text))
        if prev_building and prev_building != curr_building:
            return False

        for extractor in (_extract_unit_name, _extract_room_name, _extract_house_name):
            prev_value = extractor(prev_text)
            if not prev_value:
                continue
            curr_value = extractor(curr_text)
            if curr_value != prev_value:
                return False

        return bool(prev_building or _extract_unit_name(prev_text) or _extract_room_name(prev_text) or _extract_house_name(prev_text))

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

    def _merge_user_spoken_scope(prev_text: str, curr_text: str) -> str:
        prev_text = _to_str(prev_text)
        curr_text = _to_str(curr_text)
        if not prev_text:
            return curr_text
        if not curr_text:
            return prev_text

        prev_norm = _normalize_text(prev_text)
        curr_norm = _normalize_text(curr_text)
        if not prev_norm or not curr_norm:
            return f"{prev_text}{curr_text}"
        if curr_norm == prev_norm or curr_norm in prev_norm:
            return prev_text
        if prev_norm in curr_norm:
            return curr_text
        if _detail_values_covered(prev_text, curr_text):
            return curr_text

        max_overlap = min(len(prev_text), len(curr_text))
        for size in range(max_overlap, 0, -1):
            if _normalize_text(prev_text[-size:]) == _normalize_text(curr_text[:size]):
                return f"{prev_text}{curr_text[size:]}"
        return f"{prev_text}{curr_text}"

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
        text = _normalize_address_marker_tokens(text)
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

        recorded = current_input or prev_unmatched or fallback_text
        if not recorded or not fallback_text:
            return recorded

        recorded_fragment = _extract_named_place_fragment(recorded)
        fallback_fragment = _extract_named_place_fragment(fallback_text)
        token_sources = [
            _extract_conflict_tokens(recorded),
            _extract_conflict_tokens(recorded_fragment),
        ]
        fallback_sources = [
            _extract_conflict_tokens(fallback_text),
            _extract_conflict_tokens(fallback_fragment),
        ]

        for level in ("town", "road", "community"):
            recorded_values = []
            fallback_values = []
            for source_tokens in token_sources:
                value = source_tokens[level][0] if source_tokens[level] else ""
                value = _to_str(value)
                if value and value not in recorded_values:
                    recorded_values.append(value)
            for source_tokens in fallback_sources:
                value = source_tokens[level][0] if source_tokens[level] else ""
                value = _to_str(value)
                if value and value not in fallback_values:
                    fallback_values.append(value)

        return recorded

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
            weak_stripped_raw_named_place_fragment = _strip_leading_weak_area_fragment(raw_named_place_fragment)
            weak_stripped_named_place_fragment = _strip_leading_weak_area_fragment(stripped_named_place_fragment)
            for value in (
                raw_named_place_fragment,
                stripped_named_place_fragment,
                weak_stripped_raw_named_place_fragment,
                weak_stripped_named_place_fragment,
            ):
                value = _to_str(value)
                value_norm = _normalize_text(value)
                if (
                    value
                    and len(value_norm) >= 4
                    and not _is_weak_area_fragment(value)
                    and value not in named_place_fragments
                ):
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
                if not any(
                    named_place_norm in candidate_norm
                    for named_place_norm in named_place_norms
                ):
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

    def _extract_overlap_terms(text: str) -> list[str]:
        text = _to_str(text)
        if not text:
            return []

        tokens = _extract_conflict_tokens(text)
        terms = []

        def _add_term(value: str) -> None:
            value = _to_str(value)
            norm = _normalize_text(value)
            if norm and norm not in terms:
                terms.append(norm)

        for level in ("province", "city", "district", "town", "road", "community"):
            for token in tokens.get(level, []):
                _add_term(token)

        for value in (
            _extract_community_name(text),
            _extract_road_name(text),
            _extract_building_name(text),
            _extract_unit_name(text),
            _extract_room_name(text),
            _extract_house_name(text),
        ):
            _add_term(value)

        raw_named_place = _extract_named_place_fragment(text)
        stripped_named_place = _strip_leading_admin_tokens(raw_named_place)
        weak_stripped_raw_named_place = _strip_leading_weak_area_fragment(raw_named_place)
        weak_stripped_named_place = _strip_leading_weak_area_fragment(stripped_named_place)
        for value in (
            raw_named_place,
            stripped_named_place,
            weak_stripped_raw_named_place,
            weak_stripped_named_place,
        ):
            norm = _normalize_text(value)
            if len(norm) >= 4 and norm not in terms:
                terms.append(norm)

        full_norm = _normalize_text(text)
        if full_norm and full_norm not in terms:
            terms.append(full_norm)

        return terms

    def _has_address_overlap(a: str, b: str) -> bool:
        a = _to_str(a)
        b = _to_str(b)
        if not a or not b:
            return False

        na = _normalize_text(a)
        nb = _normalize_text(b)
        if na and nb and (na == nb or na in nb or nb in na):
            return True
        a_terms = _extract_overlap_terms(a)
        b_terms = _extract_overlap_terms(b)
        for a_term in a_terms:
            for b_term in b_terms:
                if a_term == b_term or a_term in b_term or b_term in a_term:
                    return True

        return False

    def _has_any_candidate_overlap(user_text: str, addresses: list) -> bool:
        user_text = _to_str(user_text)
        if not user_text:
            return False

        for address in addresses or []:
            if _has_address_overlap(user_text, address):
                return True

        return False

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
            if recorded_norm and expected_norm and recorded_norm == expected_norm:
                return recorded_address
            if recorded_norm and expected_norm and recorded_norm.startswith(expected_norm) and recorded_norm != expected_norm:
                return expected_input
            if recorded_norm and expected_norm and recorded_norm.endswith(expected_norm) and recorded_norm != expected_norm:
                return expected_input

        return recorded_address

    def _fragment_supported_by_candidate(fragment: str, candidate: str) -> bool:
        fragment = _to_str(fragment)
        candidate = _to_str(candidate)
        if not fragment or not candidate:
            return False

        fragment_norm = _normalize_text(fragment)
        candidate_norm = _normalize_text(candidate)
        return bool(fragment_norm and candidate_norm and fragment_norm in candidate_norm)

    def _has_literal_candidate_overlap_with_addresses(text: str, addresses: list) -> bool:
        raw_text = _to_str(text)
        if len(raw_text) >= 2 and any(raw_text in _to_str(address) for address in addresses):
            return True
        text_norm = _normalize_text(text)
        if len(text_norm) < 2:
            return False
        return any(text_norm in _normalize_text(address) for address in addresses)

    def _has_candidate_overlap_with_addresses(text: str, addresses: list) -> bool:
        return bool(
            text
            and (
                _has_any_candidate_overlap(text, addresses)
                or _has_literal_candidate_overlap_with_addresses(text, addresses)
            )
        )

    def _should_use_model_fragment_fallback(raw_input: str, model_fragment: str, addresses: list) -> bool:
        return bool(
            current_state == "matching"
            and raw_input
            and model_fragment
            and isinstance(addresses, list)
            and addresses
            and not _has_candidate_overlap_with_addresses(raw_input, addresses)
            and _has_candidate_overlap_with_addresses(model_fragment, addresses)
        )

    def _strip_admin_prefix_for_tail(text: str) -> str:
        text = _normalize_address_marker_tokens(_to_str(text))
        if not text:
            return ""

        tail = text
        for pattern, skip_fn in (
            (r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省)", None),
            (r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?市", None),
            (r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗)", lambda token: bool(re.search(r"(?:街道|镇|乡)", token))),
            (r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:街道|镇|乡)", None),
        ):
            match = re.match(pattern, tail)
            if not match:
                continue
            token = match.group(0)
            if skip_fn and skip_fn(token):
                continue
            rest = tail[match.end():].strip()
            if rest:
                tail = rest

        return tail

    def _normalize_tail_compare_text(text: str) -> str:
        text = _normalize_address_marker_tokens(_to_str(text))
        if not text:
            return ""

        cn_number = r"[一二三四五六七八九十百零两]{1,6}"
        text = re.sub(
            fr"({cn_number})(号楼|楼|栋|幢|座|单元|室|号院|号|弄|里)",
            lambda match: f"{_normalize_cn_digits(match.group(1))}{match.group(2)}",
            text
        )
        text = re.sub(
            fr"(?<![A-Za-z0-9一二三四五六七八九十百零两])({cn_number})(?![A-Za-z0-9一二三四五六七八九十百零两])",
            lambda match: _normalize_cn_digits(match.group(1)),
            text
        )
        return _normalize_text(text)

    def _candidate_tail_support_score(user_text: str, candidate: str) -> float:
        user_norm = _normalize_tail_compare_text(user_text)
        tail_norm = _normalize_tail_compare_text(_strip_admin_prefix_for_tail(candidate))
        if not user_norm or not tail_norm:
            return 0.0
        if user_norm == tail_norm:
            return 1.0
        if tail_norm in user_norm:
            return len(tail_norm) / max(len(user_norm), 1)
        if user_norm in tail_norm:
            return len(user_norm) / max(len(tail_norm), 1)

        matcher = SequenceMatcher(None, user_norm, tail_norm)
        longest = max((match.size for match in matcher.get_matching_blocks()), default=0)
        user_coverage = longest / max(len(user_norm), 1)
        tail_coverage = longest / max(len(tail_norm), 1)
        similarity = matcher.ratio()
        return max(min(user_coverage, tail_coverage), similarity)

    def _has_detail_signal_for_tail_support(text: str) -> bool:
        return bool(_has_building_or_room(text) or _extract_house_name(text))

    def _candidate_tail_supported_by_user_scope(user_text: str, candidate: str) -> bool:
        user_text = _normalize_address_marker_tokens(_to_str(user_text))
        candidate = _normalize_address_marker_tokens(_to_str(candidate))
        if not user_text or not candidate:
            return False
        if _has_strong_conflict(user_text, candidate) or _has_precise_detail_conflict(user_text, candidate):
            return False

        score = _candidate_tail_support_score(user_text, candidate)
        if score >= 0.85:
            return True
        return score >= 0.70 and _has_detail_signal_for_tail_support(user_text)

    def _is_weak_area_fragment(text: str) -> bool:
        text = _to_str(text)
        if not text:
            return False
        return bool(re.fullmatch(r"(东|西|南|北|中)(区|侧|门)?|[A-Za-z]区|[一二三四五六七八九十0-9]+区", text))

    def _strip_leading_weak_area_fragment(text: str) -> str:
        text = _to_str(text)
        if not text:
            return ""

        patterns = (
            r"^(东|西|南|北|中)(区|侧|门)?",
            r"^[A-Za-z]区",
            r"^[一二三四五六七八九十0-9]+区",
        )

        stripped = text
        for pattern in patterns:
            match = re.match(pattern, stripped)
            if match:
                stripped = stripped[match.end():].strip()
                break

        return stripped

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
        text = _normalize_address_marker_tokens(text)

        fragment = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼|号(?=(?:\d+单元|\d{3,6}(?:室)?)))", "", text)
        fragment = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+)单元", "", fragment)
        fragment = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+)室", "", fragment)
        fragment = re.sub(r"(?<!\d)\d{3,6}(?!\d)|[一二三四五六七八九十百零两]{3,6}", "", fragment)
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

    def _has_matchable_place_level(text: str) -> bool:
        text = _to_str(text)
        if not text:
            return False
        if _has_place_anchor(text) or _has_named_place_anchor(text):
            return True
        return bool(re.search("(\u793e\u533a|\u6751\u7ec4|\u6751|\u8def|\u5927\u9053|\u5df7|\u80e1\u540c|\u8857(?!\u9053)|\u5f04|\u91cc|\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u697c\u5b87|\u82d1)", text))

    def _strip_specific_place_fragment(text: str) -> str:
        fragment = _normalize_address_marker_tokens(_extract_named_place_fragment(text))
        if not fragment:
            return ""

        fragment = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+)层", "", fragment).strip()
        fragment = _strip_leading_admin_tokens(fragment)

        changed = True
        while changed and fragment:
            changed = False
            updated = re.sub(r"^[\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:大道|路|巷|胡同|街(?!道))", "", fragment).strip()
            if updated != fragment:
                fragment = updated
                changed = True

        fragment = _strip_leading_weak_area_fragment(fragment)
        fragment = re.sub(
            r"(东|西|南|北|中)(区|侧|门)?$|[A-Za-z]区$|[一二三四五六七八九十0-9]+区$",
            "",
            fragment
        ).strip()
        fragment = re.sub(r"^(?:\d+|[一二三四五六七八九十百零两]+)层", "", fragment).strip()

        fragment_norm = _normalize_text(fragment)
        if len(fragment_norm) < 4 or _is_weak_area_fragment(fragment):
            return ""
        return fragment

    def _has_specific_place_fragment(text: str) -> bool:
        text = _to_str(text)
        if not text:
            return False
        return bool(_extract_community_name(text) or _strip_specific_place_fragment(text))

    def _candidate_has_unspoken_specific_place(current_text: str, addresses: list, matched_idx: int = -1) -> bool:
        current_text = _to_str(current_text)
        if not current_text or _has_specific_place_fragment(current_text):
            return False

        candidate_pool = []
        if isinstance(addresses, list) and 0 <= matched_idx < len(addresses):
            candidate_pool = [_to_str(addresses[matched_idx])]
        elif isinstance(addresses, list):
            candidate_pool = [
                _to_str(address)
                for address in addresses
                if _has_address_overlap(current_text, _to_str(address))
            ]

        return any(_has_specific_place_fragment(address) for address in candidate_pool if address)

    def _add_candidate_backed_term(terms: list, value: str, min_len: int = 2) -> None:
        value = _normalize_address_marker_tokens(_to_str(value))
        norm = _normalize_text(value)
        if len(norm) >= min_len and norm not in {item[1] for item in terms}:
            terms.append((value, norm))

    def _candidate_backed_terms(text: str) -> list:
        text = _normalize_address_marker_tokens(_to_str(text))
        terms = []
        if not text:
            return terms

        has_detail = bool(_has_building_or_room(text) or _extract_house_name(text))
        if not has_detail:
            for pattern in (
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u81ea\u6cbb\u533a|\u7279\u522b\u884c\u653f\u533a|\u7701)",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?\u5e02",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u533a|\u53bf|\u65d7)",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u8857\u9053|\u9547|\u4e61)",
            ):
                for match in re.findall(pattern, text):
                    if not _is_false_district_token(match):
                        _add_candidate_backed_term(terms, match)

        for value in (
            _extract_road_name(text),
            _extract_community_name(text),
            _extract_building_name(text),
            _extract_unit_name(text),
            _extract_room_name(text),
            _extract_house_name(text),
        ):
            _add_candidate_backed_term(terms, value)

        named = _strip_leading_admin_tokens(_extract_named_place_fragment(text))
        if named:
            if _is_weak_area_fragment(named):
                _add_candidate_backed_term(terms, named)
                return terms
            weak_match = re.match(r"(\u4e1c|\u897f|\u5357|\u5317|\u4e2d)(\u533a|\u4fa7|\u95e8)?|[A-Za-z]\u533a|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u96f60-9]+\u533a", named)
            if weak_match and weak_match.end() < len(named):
                _add_candidate_backed_term(terms, weak_match.group(0))
                named = named[weak_match.end():].strip()
            weak_tail = re.search(r"(\u4e1c|\u897f|\u5357|\u5317|\u4e2d)(\u533a|\u4fa7|\u95e8)?$|[A-Za-z]\u533a$|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u96f60-9]+\u533a$", named)
            if weak_tail and weak_tail.start() > 0:
                _add_candidate_backed_term(terms, weak_tail.group(0))
                named = named[:weak_tail.start()].strip()
            if named and not _is_weak_area_fragment(named):
                marker_min_len = 2 if re.search(r"(\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751|\u9547|\u4e61|\u8857\u9053|\u8def|\u5927\u9053|\u5df7|\u80e1\u540c|\u8857(?!\u9053))", named) else 4
                _add_candidate_backed_term(terms, named, marker_min_len)

        if not terms:
            _add_candidate_backed_term(terms, text)

        return terms

    def _combine_candidate_backed_parts(prev_text: str, curr_text: str) -> str:
        prev_text = _normalize_address_marker_tokens(_to_str(prev_text))
        curr_text = _normalize_address_marker_tokens(_to_str(curr_text))
        if not curr_text:
            return ""
        if not prev_text:
            return curr_text
        prev_norm = _normalize_text(prev_text)
        curr_norm = _normalize_text(curr_text)
        if curr_norm == prev_norm or (curr_norm and curr_norm in prev_norm):
            return prev_text
        if prev_norm and prev_norm in curr_norm:
            return curr_text
        return _merge_user_spoken_scope(prev_text, curr_text)

    def _find_candidate_backed_merge(prev_text: str, curr_text: str, addresses: list) -> str:
        prev_text = _to_str(prev_text)
        curr_text = _to_str(curr_text)
        if not prev_text or not curr_text or not isinstance(addresses, list) or not addresses:
            return ""
        if _is_weak_area_fragment(prev_text) and _has_named_place_anchor(curr_text):
            return ""

        prev_terms = _candidate_backed_terms(prev_text)
        curr_terms = _candidate_backed_terms(curr_text)
        if not prev_terms or not curr_terms:
            return ""

        required_terms = []
        by_norm = {}
        for source, terms in (("prev", prev_terms), ("curr", curr_terms)):
            for value, norm in terms:
                if norm not in by_norm:
                    item = {"value": value, "norm": norm, "sources": {source}}
                    by_norm[norm] = item
                    required_terms.append(item)
                else:
                    by_norm[norm]["sources"].add(source)

        combined = _combine_candidate_backed_parts(prev_text, curr_text)
        results = []
        for address in addresses or []:
            address = _to_str(address)
            if not address:
                continue
            address_norm = _normalize_text(address)
            if not all(item["norm"] and item["norm"] in address_norm for item in required_terms):
                continue
            if not any("prev" in item["sources"] for item in required_terms):
                continue
            if not any("curr" in item["sources"] for item in required_terms):
                continue
            results.append(combined)

        unique_results = []
        seen_norms = set()
        for result in results:
            norm = _normalize_text(result)
            if norm and norm not in seen_norms:
                seen_norms.add(norm)
                unique_results.append(result)
        return unique_results[0] if len(unique_results) == 1 else ""

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

    def _filter_by_named_place_fragment(fragment: str, addresses: list) -> list:
        fragment_norms = []
        for value in (
            _to_str(fragment),
            _strip_leading_admin_tokens(fragment),
            _strip_leading_weak_area_fragment(fragment),
            _strip_leading_weak_area_fragment(_strip_leading_admin_tokens(fragment)),
        ):
            norm = _normalize_text(value)
            if len(norm) >= 4 and norm not in fragment_norms:
                fragment_norms.append(norm)

        if not fragment_norms:
            return []
        return [
            address for address in addresses
            if any(
                fragment_norm in _normalize_text(address)
                for fragment_norm in fragment_norms
            )
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

    def _build_candidate_backed_partial_followup(current_input: str, address_list: list) -> tuple[str, str]:
        current_input = _normalize_address_marker_tokens(_to_str(current_input))
        if not current_input or not isinstance(address_list, list) or not address_list:
            return "", ""

        terms = []

        def _add_term(value: str, kind: str, min_len: int = 2) -> None:
            value = _normalize_address_marker_tokens(_to_str(value))
            norm = _normalize_text(value)
            if len(norm) >= min_len and norm not in {item[1] for item in terms}:
                terms.append((value, norm, kind))

        road = _extract_road_name(current_input)
        road_matches = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857(?!\u9053))", current_input)
        road_span = max(road_matches, key=len) if road_matches else ""
        community = _extract_community_name(current_input)
        building = _extract_building_name(current_input)
        unit = _extract_unit_name(current_input)
        room = _extract_room_name(current_input)
        house = _extract_house_name(current_input)

        _add_term(road_span, "scope")
        _add_term(road, "scope")
        _add_term(community, "scope")
        for detail in (building, unit, room, house):
            _add_term(detail, "detail")

        residual = current_input
        for value in sorted([road_span, road, community, building, unit, room, house], key=lambda item: len(_to_str(item)), reverse=True):
            value = _to_str(value)
            if value and value in residual:
                residual = residual.replace(value, "", 1)
        residual = _strip_leading_weak_area_fragment(_strip_leading_admin_tokens(residual))
        residual = re.sub(r"^[,?:?\s]+|[,?:?\s]+$", "", residual)
        if residual and not _is_weak_area_fragment(residual):
            _add_term(residual, "scope")
            named_fragment = _extract_named_place_fragment(residual)
            if named_fragment != residual:
                _add_term(named_fragment, "scope")

        has_scope = any(kind == "scope" for _value, _norm, kind in terms)
        has_detail = any(kind == "detail" for _value, _norm, kind in terms)
        if not has_scope or not has_detail:
            return "", ""

        has_matching_candidate = False
        for address in address_list:
            candidate = _to_str(address)
            if not candidate or _has_strong_conflict(current_input, candidate) or _has_precise_detail_conflict(current_input, candidate):
                continue

            candidate_norm = _normalize_text(candidate)
            if all(norm and norm in candidate_norm for _value, norm, _kind in terms):
                has_matching_candidate = True
                break

        if not has_matching_candidate:
            return "", ""

        recorded_address = _to_str(current_input)
        if not recorded_address:
            return "", ""
        reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        return reply, recorded_address

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
        has_colon_separator = ":" in current_input or "：" in current_input

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
                elif candidate_units:
                    reply = f"我记录的地址信息是：{recorded_address}，请您再提供下单元号及门牌号信息"
                elif has_colon_separator:
                    reply = f"我记录的地址信息是：{recorded_address}，请您再提供下单元号及门牌号信息。"
                else:
                    reply = f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息"
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
                if has_colon_separator:
                    reply = f"我记录的地址信息是：{recorded_address}，请您再提供下楼号、单元号及门牌号信息。"
                else:
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

    def _build_fragment_detail_followup(recorded_address: str, address_list: list) -> tuple[str, str]:
        recorded_address = _normalize_address_marker_tokens(_to_str(recorded_address))
        if not recorded_address or not isinstance(address_list, list) or len(address_list) < 2:
            return "", ""

        has_place_scope = bool(
            _extract_community_name(recorded_address)
            or _extract_road_name(recorded_address)
            or _has_place_anchor(recorded_address)
            or _has_named_place_anchor(recorded_address)
        )
        if not has_place_scope and (_has_building_or_room(recorded_address) or _extract_house_name(recorded_address)):
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
            return reply, recorded_address

        matched_candidates = []
        for candidate in address_list:
            candidate = _to_str(candidate)
            if not candidate:
                continue
            if _has_strong_conflict(recorded_address, candidate) or _has_precise_detail_conflict(recorded_address, candidate):
                continue
            if _fragment_supported_by_candidate(recorded_address, candidate):
                matched_candidates.append(candidate)

        if len(matched_candidates) < 2:
            return "", ""

        current_building = _extract_building_name(recorded_address)
        current_unit = _extract_unit_name(recorded_address)
        current_room = _extract_room_name(recorded_address)
        current_house = _extract_house_name(recorded_address)

        candidate_buildings = list(dict.fromkeys([
            value for value in (_extract_building_name(candidate) for candidate in matched_candidates) if value
        ]))
        candidate_units = list(dict.fromkeys([
            value for value in (_extract_unit_name(candidate) for candidate in matched_candidates) if value
        ]))
        candidate_rooms = list(dict.fromkeys([
            value for value in (_extract_room_name(candidate) for candidate in matched_candidates) if value
        ]))

        if current_unit and not current_room and candidate_rooms:
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u63d0\u4f9b\u4e0b\u95e8\u724c\u53f7\u4fe1\u606f"
            return reply, recorded_address

        if current_building:
            if current_unit and candidate_rooms:
                reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u63d0\u4f9b\u4e0b\u95e8\u724c\u53f7\u4fe1\u606f"
                return reply, recorded_address
            if not current_unit:
                if candidate_units:
                    reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5355\u5143\u53f7\u53ca\u95e8\u724c\u53f7\u3002"
                    return reply, recorded_address
                if candidate_rooms:
                    reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u63d0\u4f9b\u4e0b\u95e8\u724c\u53f7\u4fe1\u606f"
                    return reply, recorded_address

        has_specific_place_scope = bool(
            _extract_community_name(recorded_address)
            or _extract_road_name(recorded_address)
            or _extract_house_name(recorded_address)
            or _has_named_place_anchor(recorded_address)
        )
        has_named_or_community_scope = bool(
            _extract_community_name(recorded_address)
            or _has_named_place_anchor(recorded_address)
        )
        should_request_building_detail = (
            has_specific_place_scope
            and not current_building
            and not current_unit
            and not current_room
            and (not current_house or has_named_or_community_scope)
        )
        if should_request_building_detail:
            if candidate_buildings or candidate_units or candidate_rooms:
                reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u697c\u680b\u53f7\u3001\u5355\u5143\u53f7\u53ca\u95e8\u724c\u53f7\u3002"
                return reply, recorded_address

        return "", ""

    current_raw_input = _normalize_address_marker_tokens(_to_str(clean_user_input))
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
    prev_unmatched_fragment_raw = _normalize_address_marker_tokens(_to_str(last_unmatched_fragment))

    current_input = current_raw_input
    ignored_no_overlap_input = False
    candidate_backed_merged_input = _find_candidate_backed_merge(
        mergeable_prev_unmatched,
        current_raw_input,
        address_list
    )
    if candidate_backed_merged_input:
        current_input = candidate_backed_merged_input
    else:
        should_merge_named_place_with_previous = bool(
            mergeable_prev_unmatched
            and current_raw_input
            and not address_list
            and _has_named_place_anchor(current_raw_input)
            and _has_building_or_room(mergeable_prev_unmatched)
            and _has_any_candidate_overlap(current_raw_input, address_list)
        )
        should_merge_candidate_overlap_with_previous = bool(
            mergeable_prev_unmatched
            and current_raw_input
            and not address_list
            and _has_any_candidate_overlap(current_raw_input, address_list)
            and not (
                _is_weak_area_fragment(mergeable_prev_unmatched)
                and _has_named_place_anchor(current_raw_input)
            )
        )
        if mergeable_prev_unmatched and current_raw_input and (
            (not address_list and _is_fragment_like(current_raw_input))
            or should_merge_named_place_with_previous
            or should_merge_candidate_overlap_with_previous
        ):
            ncur = _normalize_text(current_raw_input)
            nprev = _normalize_text(mergeable_prev_unmatched)

            if ncur == nprev or ncur in nprev:
                current_input = mergeable_prev_unmatched
            elif nprev and nprev in ncur:
                current_input = current_raw_input
            else:
                current_input = _merge_user_spoken_scope(mergeable_prev_unmatched, current_raw_input)
        elif mergeable_prev_unmatched and current_raw_input and _should_merge_region_continuation(mergeable_prev_unmatched, current_raw_input):
            current_input = _merge_user_spoken_scope(mergeable_prev_unmatched, current_raw_input)

    if (
        mergeable_prev_unmatched
        and current_raw_input
        and _is_weak_area_fragment(current_raw_input)
        and _has_building_or_room(mergeable_prev_unmatched)
    ):
        weak_area_scope = _merge_user_spoken_scope(mergeable_prev_unmatched, current_raw_input)
        weak_area_supported = any(
            _fragment_supported_by_candidate(weak_area_scope, candidate)
            and not _has_precise_detail_conflict(weak_area_scope, candidate)
            for candidate in address_list
        )
        if not weak_area_supported:
            ignored_no_overlap_input = True
            current_input = mergeable_prev_unmatched

    if (
        mergeable_prev_unmatched
        and current_raw_input
        and current_input == current_raw_input
        and not _has_address_overlap(current_raw_input, mergeable_prev_unmatched)
        and not _has_any_candidate_overlap(current_raw_input, address_list)
        and not _has_building_or_room(current_raw_input)
    ):
        ignored_no_overlap_input = True
        current_input = mergeable_prev_unmatched

    effective_user_scope = current_input
    if (
        mergeable_prev_unmatched
        and current_raw_input
        and not ignored_no_overlap_input
        and (
            _is_fragment_like(current_raw_input)
            or _has_address_overlap(mergeable_prev_unmatched, current_raw_input)
            or _has_any_candidate_overlap(_merge_user_spoken_scope(mergeable_prev_unmatched, current_raw_input), address_list)
        )
    ):
        merged_scope = _merge_user_spoken_scope(mergeable_prev_unmatched, current_raw_input)
        merged_scope_norm = _normalize_text(merged_scope)
        merged_scope_literal_overlap = bool(
            len(merged_scope_norm) >= 2
            and any(merged_scope_norm in _normalize_text(address) for address in address_list)
        )
        if _has_any_candidate_overlap(merged_scope, address_list) or merged_scope_literal_overlap:
            effective_user_scope = merged_scope

    if (
        mergeable_prev_unmatched
        and current_raw_input
        and not ignored_no_overlap_input
        and _has_building_or_room(mergeable_prev_unmatched)
        and not _has_building_or_room(current_raw_input)
        and (_has_place_anchor(current_raw_input) or _has_named_place_anchor(current_raw_input))
    ):
        place_first_scope = _merge_user_spoken_scope(current_raw_input, mergeable_prev_unmatched)
        place_first_norm = _normalize_text(place_first_scope)
        place_first_literal_overlap = bool(
            len(place_first_norm) >= 2
            and any(place_first_norm in _normalize_text(address) for address in address_list)
        )
        if _has_any_candidate_overlap(place_first_scope, address_list) or place_first_literal_overlap:
            current_input = place_first_scope
            effective_user_scope = place_first_scope

    prev_repeat_count = max(_to_int(similar_no_match_count, 0), 0)
    SIMILAR_NO_MATCH_FAIL_THRESHOLD = 2

    def _next_repeat_count(min_count: int = 1) -> int:
        return max(prev_repeat_count + 1, min_count)

    def _should_fail_by_repeat(next_count: int) -> bool:
        return next_count >= SIMILAR_NO_MATCH_FAIL_THRESHOLD

    def _with_ai_context_reply(result: dict) -> dict:
        if not isinstance(result, dict):
            return result
        result_llm = result.get("llm_result")
        if isinstance(result_llm, dict):
            result_llm.setdefault("ai_context_reply", _to_str(result_llm.get("reply")))
        return result

    def _is_confirming_confirmation_or_denial(text: str) -> bool:
        norm = _normalize_text(text)
        if not norm:
            return False
        confirm_words = {
            "\u662f", "\u662f\u7684", "\u5bf9", "\u5bf9\u7684", "\u6ca1\u9519",
            "\u6b63\u786e", "\u53ef\u4ee5", "\u597d", "\u597d\u7684", "\u55ef", "\u55ef\u55ef"
        }
        if norm in confirm_words:
            return True
        denial_prefixes = (
            "\u4e0d\u662f", "\u4e0d\u5bf9", "\u9519\u4e86", "\u9519", "\u5426", "\u4e0d"
        )
        return norm.startswith(denial_prefixes)

    def _is_confirming_denial(text: str) -> bool:
        norm = _normalize_text(text)
        if not norm:
            return False
        denial_prefixes = (
            "\u4e0d\u662f", "\u4e0d\u5bf9", "\u9519\u4e86", "\u9519", "\u5426", "\u4e0d"
        )
        return norm.startswith(denial_prefixes)

    def _has_confirming_new_address_signal(text: str) -> bool:
        text = _to_str(text)
        if not text:
            return False
        address_pattern = (
            r"(\u7701|\u5e02|\u533a|\u53bf|\u65d7|\u9547|\u4e61|\u8857\u9053|"
            r"\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751|"
            r"\u8def|\u5927\u9053|\u5df7|\u80e1\u540c|\u8857(?!\u9053))"
        )
        if re.search(address_pattern, text):
            return True
        return bool(_has_building_or_room(text) or _extract_house_name(text))

    def _build_confirming_repeat_result(next_count: int) -> dict:
        return _with_ai_context_reply({
            "llm_result": {
                "match_count": 1,
                "matched_index": current_matched_index,
                "is_completed": False,
                "is_extract_failed": False,
                "matched_address_fragment": "",
                "reply": ""
            },
            "next_last_unmatched_address": prev_unmatched_raw,
            "next_last_unmatched_fragment": "",
            "next_similar_no_match_count": next_count
        })

    def _build_extract_failed_result() -> dict:
        return _with_ai_context_reply({
            "llm_result": {
                "match_count": 0,
                "matched_index": -1,
                "is_completed": False,
                "is_extract_failed": True,
                "matched_address_fragment": "",
                "reply": ""
            },
            "next_last_unmatched_address": "",
            "next_last_unmatched_fragment": "",
            "next_similar_no_match_count": 0
        })

    if current_state == "confirming" and current_matched_index >= 0 and current_input:
        confirming_candidate = _to_str(address_list[current_matched_index]) if 0 <= current_matched_index < len(address_list) else ""
        if (
            not _is_confirming_confirmation_or_denial(current_input)
            and not _has_address_overlap(current_input, confirming_candidate)
            and not _has_confirming_new_address_signal(current_input)
        ):
            next_repeat_count = _next_repeat_count()
            if _should_fail_by_repeat(next_repeat_count):
                return _build_extract_failed_result()
            return _build_confirming_repeat_result(next_repeat_count)

    model_matched_address_fragment = _normalize_address_marker_tokens(
        _to_str(llm_result.get("matched_address_fragment"))
    )
    use_model_fragment_fallback = _should_use_model_fragment_fallback(
        current_raw_input,
        model_matched_address_fragment,
        address_list
    )
    if use_model_fragment_fallback:
        current_input = model_matched_address_fragment
        effective_user_scope = model_matched_address_fragment
        ignored_no_overlap_input = False

    meaningless_flag = _to_bool(
        meaningless_result.get(
            "is_meaningless",
            meaningless_result.get("meaningless", meaningless_result.get("is_irrelevant", False))
        )
    )
    meaningless_reply = _to_str(meaningless_result.get("reply"))

    if use_model_fragment_fallback:
        meaningless_flag = False
        meaningless_reply = ""

    if meaningless_flag and current_input and _looks_like_address(current_input):
        meaningless_flag = False
        meaningless_reply = ""

    if meaningless_flag:
        next_repeat_count = _next_repeat_count()
        if current_state == "confirming" and current_matched_index >= 0:
            if _should_fail_by_repeat(next_repeat_count):
                llm_result = {
                    "match_count": 0,
                    "matched_index": -1,
                    "is_completed": False,
                    "is_extract_failed": True,
                    "matched_address_fragment": "",
                    "reply": ""
                }
                return _with_ai_context_reply({
                    "llm_result": llm_result,
                    "next_last_unmatched_address": "",
                    "next_last_unmatched_fragment": "",
                    "next_similar_no_match_count": 0
                })

            llm_result = {
                "match_count": 1,
                "matched_index": current_matched_index,
                "is_completed": False,
                "is_extract_failed": False,
                "matched_address_fragment": "",
                "reply": ""
            }
            return _with_ai_context_reply({
                "llm_result": llm_result,
                "next_last_unmatched_address": prev_unmatched_raw,
                "next_last_unmatched_fragment": "",
                "next_similar_no_match_count": next_repeat_count
            })
        else:
            meaningless_extract_failed = _should_fail_by_repeat(next_repeat_count)
            llm_result = {
                "match_count": 0,
                "matched_index": -1,
                "is_completed": False,
                "is_extract_failed": meaningless_extract_failed,
                "matched_address_fragment": "",
                "reply": "" if meaningless_extract_failed else (meaningless_reply or "请您提供详细的地址信息")
            }
        return _with_ai_context_reply({
            "llm_result": llm_result,
            "next_last_unmatched_address": "" if llm_result["is_extract_failed"] else prev_unmatched_raw,
            "next_last_unmatched_fragment": "",
            "next_similar_no_match_count": 0 if llm_result["is_extract_failed"] else next_repeat_count
        })

    model_match_count = max(_to_int(llm_result.get("match_count"), 0), 0)
    model_matched_index = _to_int(llm_result.get("matched_index"), -1)
    model_is_completed = _to_bool(llm_result.get("is_completed", False))
    model_fragment_for_output = _sanitize_recorded_address(
        model_matched_address_fragment,
        effective_user_scope or current_input,
        mergeable_prev_unmatched
    )
    model_fragment_display_address = (
        model_fragment_for_output
        or effective_user_scope
        or current_input
    ) if model_matched_address_fragment else ""
    model_reuses_previous_fragment = bool(
        current_state == "matching"
        and model_match_count == 0
        and model_matched_index < 0
        and model_matched_address_fragment
        and prev_unmatched_fragment_raw
        and _normalize_text(model_matched_address_fragment) == _normalize_text(prev_unmatched_fragment_raw)
    )
    if model_reuses_previous_fragment:
        ignored_no_overlap_input = True
        current_input = prev_unmatched or model_fragment_for_output or prev_unmatched_fragment_raw
        effective_user_scope = current_input

    # Phase 1: calculate internal decisions only. The incoming llm_result is
    # not updated until the final assembly block at the end of the function.
    match_count = model_match_count
    llm_matched_index = model_matched_index
    is_completed = model_is_completed
    is_extract_failed = False
    reply = ""

    model_unique_fragment_demoted = False
    model_unique_fragment_supported = False
    user_place_context_for_unique_match = bool(
        _has_matchable_place_level(current_input)
        or _has_matchable_place_level(mergeable_prev_unmatched)
        or _has_matchable_place_level(effective_user_scope)
    )

    if llm_matched_index >= 0 and 0 <= llm_matched_index < len(address_list):
        selected_address = _to_str(address_list[llm_matched_index])
        candidate_tail_supported = bool(
            model_matched_address_fragment
            and _candidate_tail_supported_by_user_scope(model_matched_address_fragment, selected_address)
            and (
                _candidate_tail_supported_by_user_scope(current_input, selected_address)
                or _candidate_tail_supported_by_user_scope(effective_user_scope, selected_address)
            )
        )
        model_unique_fragment_supported = bool(
            current_state == "matching"
            and match_count == 1
            and not model_is_completed
            and model_matched_address_fragment
            and (user_place_context_for_unique_match or candidate_tail_supported)
            and _fragment_supported_by_candidate(model_matched_address_fragment, selected_address)
        )
        unsupported_model_fragment = (
            current_state == "matching"
            and match_count == 1
            and not model_is_completed
            and bool(model_matched_address_fragment)
            and not model_unique_fragment_supported
        )
        if (
            (
                not model_unique_fragment_supported
                and (
                    _has_strong_conflict(current_input, selected_address)
                    or _has_precise_detail_conflict(current_input, selected_address)
                )
            )
            or unsupported_model_fragment
        ):
            model_unique_fragment_demoted = unsupported_model_fragment
            llm_matched_index = -1
            match_count = 0
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
        current_state == "confirming"
        and current_matched_index >= 0
        and 0 <= current_matched_index < len(address_list)
        and current_input
    ):
        confirming_candidate = _to_str(address_list[current_matched_index])
        if (
            _has_address_overlap(current_input, confirming_candidate)
            and not _has_strong_conflict(current_input, confirming_candidate)
            and not _has_precise_detail_conflict(current_input, confirming_candidate)
        ):
            llm_matched_index = current_matched_index
            match_count = 1
            is_completed = False
            is_extract_failed = False
            reply = ""

    if (
        current_state == "matching"
        and llm_matched_index >= 0
        and match_count == 1
        and mergeable_prev_unmatched
        and current_input
        and 0 <= llm_matched_index < len(address_list)
    ):
        selected_address = _to_str(address_list[llm_matched_index])
        merged_unique_input = _merge_user_spoken_scope(mergeable_prev_unmatched, current_input)
        if (
            _has_address_overlap(mergeable_prev_unmatched, selected_address)
            and not _has_strong_conflict(merged_unique_input, selected_address)
            and not _has_precise_detail_conflict(merged_unique_input, selected_address)
        ):
            current_input = merged_unique_input

    if (
        current_state == "matching"
        and llm_matched_index >= 0
        and match_count == 1
        and not model_unique_fragment_supported
        and (
            _should_reject_place_less_unique_match(current_input)
            or (
                not _has_full_building_unit_room_detail(current_input)
                and not _has_matchable_place_level(current_input)
            )
        )
    ):
        llm_matched_index = -1
        match_count = 0
        is_completed = False
        reply = ""

    pending_unique_matched_index = -1
    pending_unique_input = ""
    precise_matched_index = -1
    if current_state == "matching" and not is_completed and not is_extract_failed:
        precise_matched_index = _find_precise_unique_match(current_input, address_list)
        if precise_matched_index >= 0 and (
            llm_matched_index < 0
            or match_count == 0
            or llm_matched_index != precise_matched_index
        ):
            pending_unique_matched_index = precise_matched_index
            pending_unique_input = current_input

    def _build_confirm_context_address(prev_text: str, curr_text: str) -> str:
        prev_text = _strip_non_merge_history(prev_text)
        curr_text = _to_str(curr_text)
        if not prev_text or not curr_text:
            return ""

        prev_norm = _normalize_text(prev_text)
        curr_norm = _normalize_text(curr_text)
        if not prev_norm or not curr_norm:
            return ""

        if curr_norm == prev_norm or curr_norm in prev_norm:
            return _mark_non_merge_history(prev_text)

        if prev_norm in curr_norm:
            return _mark_non_merge_history(curr_text)

        if _is_layer_missing(prev_text) and (_has_matchable_place_level(curr_text) or _has_named_place_anchor(curr_text) or _has_building_or_room(curr_text)):
            return _mark_non_merge_history(f"{prev_text}{curr_text}")

        if (_has_place_anchor(curr_text) or _has_named_place_anchor(curr_text)) and _has_building_or_room(prev_text):
            if not (_has_place_anchor(prev_text) or _has_named_place_anchor(prev_text)):
                return _mark_non_merge_history(f"{prev_text}{curr_text}")
            return _mark_non_merge_history(prev_text)

        if (_has_place_anchor(curr_text) or _has_named_place_anchor(curr_text)) and (_has_place_anchor(prev_text) or _has_named_place_anchor(prev_text)) and not _has_building_or_room(prev_text) and not _has_building_or_room(curr_text):
            return _mark_non_merge_history(f"{prev_text}{curr_text}")

        if _has_building_or_room(curr_text) and (_has_place_anchor(prev_text) or _has_named_place_anchor(prev_text)):
            prev_building = _extract_building_name(prev_text)
            prev_unit = _extract_unit_name(prev_text)
            prev_room = _extract_room_name(prev_text)
            prev_house = _extract_house_name(prev_text)
            curr_building = _extract_building_name(curr_text)
            curr_unit = _extract_unit_name(curr_text)
            curr_room = _extract_room_name(curr_text)
            curr_house = _extract_house_name(curr_text)

            if (curr_room or curr_house) and not (prev_room or prev_house):
                return _mark_non_merge_history(f"{prev_text}{curr_text}")
            if curr_unit and not prev_unit and not (prev_room or prev_house):
                return _mark_non_merge_history(f"{prev_text}{curr_text}")
            if curr_building and not prev_building and not (prev_unit or prev_room or prev_house):
                return _mark_non_merge_history(f"{prev_text}{curr_text}")
            return _mark_non_merge_history(prev_text)

        return ""

    if pending_unique_matched_index >= 0:
        pending_input = pending_unique_input or current_input
        pending_has_place_context = bool(
            _has_matchable_place_level(pending_input)
            or _has_matchable_place_level(mergeable_prev_unmatched)
            or _has_matchable_place_level(effective_user_scope)
        )
        if (
            pending_has_place_context
            and not _candidate_has_unspoken_specific_place(pending_input, address_list, pending_unique_matched_index)
        ):
            current_input = pending_input
            llm_matched_index = pending_unique_matched_index
            match_count = 1
            reply = ""

    unspoken_specific_place_demoted = model_unique_fragment_demoted
    if (
        current_state == "matching"
        and match_count == 1
        and llm_matched_index >= 0
        and not is_completed
        and not is_extract_failed
        and not model_unique_fragment_supported
        and _candidate_has_unspoken_specific_place(current_input, address_list, llm_matched_index)
    ):
        unspoken_specific_place_demoted = True
        llm_matched_index = -1
        match_count = 0
        reply = ""

    next_last_unmatched_address = ""
    next_similar_no_match_count = 0

    confirm_context_address = ""
    if match_count == 1 and llm_matched_index >= 0 and not is_completed and current_input:
        if current_state == "matching":
            if prev_unmatched_raw:
                confirm_context_address = _build_confirm_context_address(prev_unmatched_raw, current_input)
            if not confirm_context_address:
                confirm_context_address = _mark_non_merge_history(current_input)
        elif _is_non_merge_history(prev_unmatched_raw):
            confirm_context_address = _build_confirm_context_address(prev_unmatched_raw, current_input)

    def _has_literal_candidate_overlap(text: str) -> bool:
        raw_text = _to_str(text)
        if len(raw_text) >= 2 and any(raw_text in _to_str(address) for address in address_list):
            return True
        text_norm = _normalize_text(text)
        if len(text_norm) < 2:
            return False
        return any(text_norm in _normalize_text(address) for address in address_list)

    current_has_candidate_scope_overlap = bool(
        effective_user_scope
        and len(_normalize_text(effective_user_scope)) >= 2
        and (
            _has_any_candidate_overlap(effective_user_scope, address_list)
            or _has_literal_candidate_overlap(effective_user_scope)
        )
    )
    current_missing_candidate_specific_place = _candidate_has_unspoken_specific_place(
        current_input,
        address_list,
        llm_matched_index
    )
    current_raw_has_candidate_overlap = bool(
        current_raw_input
        and len(_normalize_text(current_raw_input)) >= 2
        and (
            _has_any_candidate_overlap(current_raw_input, address_list)
            or _has_literal_candidate_overlap(current_raw_input)
        )
    )
    current_raw_no_candidate_overlap = bool(current_raw_input and not current_raw_has_candidate_overlap)
    current_room_or_building_overlaps_candidate = bool(
        current_input
        and _has_building_or_room(current_input)
        and _has_any_candidate_overlap(current_input, address_list)
    )
    current_looks_like_address = (
        _looks_like_address(current_input)
        or current_has_candidate_scope_overlap
        or current_room_or_building_overlaps_candidate
    )
    current_is_layer_missing = _is_layer_missing(current_input)
    current_has_effective_address = _has_effective_address(current_input)
    current_address_level = _address_detail_level(current_input)
    current_is_level5_place_only = _is_level5_place_only(current_input)
    should_echo_partial_address = bool(
        current_input
        and current_looks_like_address
        and (_needs_specific_place_followup(current_input) or current_missing_candidate_specific_place)
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

    candidate_backed_partial_reply = ""
    candidate_backed_partial_address = ""
    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed and not is_extract_failed:
        candidate_backed_partial_reply, candidate_backed_partial_address = _build_candidate_backed_partial_followup(
            current_input,
            address_list
        )
    detail_scope_corrected_input = ""
    detail_scope_recorded_address = ""
    use_detail_scope_recorded_address = False
    display_recorded_address = (
        model_matched_address_fragment
        if use_model_fragment_fallback
        else (prev_unmatched if model_reuses_previous_fragment else current_raw_input)
    )
    fragment_followup_reply = ""
    fragment_recorded_address = ""
    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed and not is_extract_failed:
        fragment_followup_reply, fragment_recorded_address = _build_fragment_detail_followup(
            display_recorded_address,
            address_list
        )
    previous_context_followup_reply = ""
    previous_context_recorded_address = ""
    previous_context_candidate_scope = (
        _merge_user_spoken_scope(prev_unmatched, current_raw_input)
        if prev_unmatched and current_raw_input and not model_reuses_previous_fragment
        else ""
    )
    previous_context_current_matches_candidate = bool(
        previous_context_candidate_scope
        and any(
            _fragment_supported_by_candidate(previous_context_candidate_scope, candidate)
            and not _has_precise_detail_conflict(previous_context_candidate_scope, candidate)
            for candidate in address_list
        )
    )
    if (
        current_state == "matching"
        and llm_matched_index < 0
        and match_count == 0
        and not is_completed
        and not is_extract_failed
        and not model_reuses_previous_fragment
        and prev_unmatched
        and current_raw_input
        and _has_building_or_room(prev_unmatched)
        and _has_building_or_room(current_raw_input)
        and not (_has_place_anchor(current_raw_input) or _has_named_place_anchor(current_raw_input))
        and _has_any_candidate_overlap(prev_unmatched, address_list)
        and not previous_context_current_matches_candidate
    ):
        previous_context_followup_reply, previous_context_recorded_address = _build_fragment_detail_followup(
            prev_unmatched,
            address_list
        )

    def _build_multi_match_followup(recorded_address: str, addresses: list) -> tuple[str, str]:
        recorded_address = _normalize_address_marker_tokens(_to_str(recorded_address))
        if not recorded_address or not isinstance(addresses, list) or len(addresses) < 2:
            return "", ""

        has_place_scope = bool(
            _extract_community_name(recorded_address)
            or _extract_road_name(recorded_address)
            or _has_place_anchor(recorded_address)
            or _has_named_place_anchor(recorded_address)
        )
        if not has_place_scope and (_has_building_or_room(recorded_address) or _extract_house_name(recorded_address)):
            return (
                f"我记录的地址信息是：{recorded_address}，请您再说一下具体的小区或村镇名称。",
                recorded_address,
            )

        filtered = [
            _to_str(address)
            for address in addresses
            if _to_str(address)
            and _has_address_overlap(recorded_address, _to_str(address))
            and not _has_precise_detail_conflict(recorded_address, _to_str(address))
        ]
        if len(filtered) < 2:
            filtered = [_to_str(address) for address in addresses if _to_str(address)]
        if len(filtered) < 2:
            return "", ""

        current_building = _extract_building_name(recorded_address)
        current_unit = _extract_unit_name(recorded_address)
        current_room = _extract_room_name(recorded_address)
        current_house = _extract_house_name(recorded_address)

        candidate_buildings = list(dict.fromkeys([
            value for value in (_extract_building_name(address) for address in filtered) if value
        ]))
        candidate_units = list(dict.fromkeys([
            value for value in (_extract_unit_name(address) for address in filtered) if value
        ]))
        candidate_rooms = list(dict.fromkeys([
            value for value in (_extract_room_name(address) for address in filtered) if value
        ]))
        candidate_houses = list(dict.fromkeys([
            value for value in (_extract_house_name(address) for address in filtered) if value
        ]))

        if current_room or current_house:
            return "", recorded_address

        if current_building:
            if current_unit and (len(candidate_rooms) >= 2 or len(candidate_houses) >= 2 or len(filtered) >= 2):
                return f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息", recorded_address
            if len(candidate_units) >= 2 and not current_unit:
                return f"我记录的地址信息是：{recorded_address}，请您再提供下单元号及门牌号信息", recorded_address
            if len(candidate_rooms) >= 2 or len(candidate_houses) >= 2 or len(filtered) >= 2:
                return f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息", recorded_address

        if current_unit and not current_building:
            return f"我记录的地址信息是：{recorded_address}，请您再提供下楼栋号及门牌号信息", recorded_address

        if len(candidate_buildings) >= 2:
            return f"我记录的地址信息是：{recorded_address}，请您再提供下楼栋号、单元号及门牌号信息", recorded_address
        if len(candidate_units) >= 2:
            return f"我记录的地址信息是：{recorded_address}，请您再提供下单元号及门牌号信息", recorded_address
        if len(candidate_rooms) >= 2 or len(candidate_houses) >= 2:
            return f"我记录的地址信息是：{recorded_address}，请您再提供下门牌号信息", recorded_address

        return f"我记录的地址信息是：{recorded_address}，请您再提供下详细地址信息", recorded_address

    multi_match_recorded_address = ""
    multi_match_followup_reply = ""
    if (
        current_state == "matching"
        and llm_matched_index < 0
        and match_count > 1
        and not is_completed
        and not is_extract_failed
    ):
        multi_match_recorded_address = (
            model_fragment_for_output
            or (
                _merge_user_spoken_scope(mergeable_prev_unmatched, current_raw_input)
                if mergeable_prev_unmatched and current_raw_input
                else ""
            )
            or effective_user_scope
            or current_input
            or current_raw_input
        )
        if multi_match_recorded_address:
            multi_match_followup_reply, precise_recorded_address = _build_precise_followup(
                mergeable_prev_unmatched,
                multi_match_recorded_address,
                address_list
            )
            if precise_recorded_address:
                multi_match_recorded_address = precise_recorded_address
            if not multi_match_followup_reply:
                multi_match_followup_reply, precise_recorded_address = _build_multi_match_followup(
                    multi_match_recorded_address,
                    address_list
                )
                if precise_recorded_address:
                    multi_match_recorded_address = precise_recorded_address

    should_track_unmatched = (
        current_state == "matching"
        and llm_matched_index < 0
        and match_count == 0
        and not is_completed
        and bool(current_input)
        and (
            current_looks_like_address
            or current_raw_no_candidate_overlap
            or bool(model_matched_address_fragment)
            or bool(custom_recorded_address)
            or bool(fragment_recorded_address)
            or bool(previous_context_recorded_address)
            or bool(candidate_backed_partial_address)
        )
    )
    should_reset_unmatched_for_broad_no_overlap = (
        should_track_unmatched
        and not mergeable_prev_unmatched
        and current_is_layer_missing
        and not current_has_candidate_scope_overlap
        and not _has_any_core_region_overlap(current_input, address_list)
    )
    is_unmatched_for_fragment_count = (
        current_state == "matching"
        and llm_matched_index < 0
        and match_count == 0
        and not is_completed
    )
    current_unmatched_fragment_norm = _normalize_text(model_matched_address_fragment)
    previous_unmatched_fragment_norm = _normalize_text(prev_unmatched_fragment_raw)
    repeated_non_empty_fragment = bool(
        current_unmatched_fragment_norm
        and previous_unmatched_fragment_norm
        and current_unmatched_fragment_norm == previous_unmatched_fragment_norm
    )
    if not is_unmatched_for_fragment_count:
        next_fragment_repeat_count = 0
    elif current_unmatched_fragment_norm:
        next_fragment_repeat_count = prev_repeat_count + 1 if repeated_non_empty_fragment else 0
    else:
        next_fragment_repeat_count = prev_repeat_count + 1 if not previous_unmatched_fragment_norm else 1

    has_followup_reply = bool(
        custom_followup_reply
        or fragment_followup_reply
        or previous_context_followup_reply
        or candidate_backed_partial_reply
    )
    if is_unmatched_for_fragment_count and has_followup_reply and not current_unmatched_fragment_norm:
        next_fragment_repeat_count = prev_repeat_count

    should_fail_for_consecutive_no_overlap = (
        is_unmatched_for_fragment_count
        and (
            repeated_non_empty_fragment
            or not current_unmatched_fragment_norm
        )
        and not (has_followup_reply and not current_unmatched_fragment_norm)
        and _should_fail_by_repeat(next_fragment_repeat_count)
    )

    if should_fail_for_consecutive_no_overlap:
        is_extract_failed = True
        match_count = 0
        llm_matched_index = -1
        is_completed = False
        reply = ""
        next_last_unmatched_address = ""
        next_similar_no_match_count = next_fragment_repeat_count
    elif should_track_unmatched:
        if ignored_no_overlap_input:
            next_last_unmatched_address = prev_unmatched_raw
            next_similar_no_match_count = next_fragment_repeat_count
        elif previous_context_recorded_address:
            next_last_unmatched_address = previous_context_recorded_address
            next_similar_no_match_count = next_fragment_repeat_count
        elif should_reset_unmatched_for_broad_no_overlap:
            next_last_unmatched_address = _mark_non_merge_history(current_input)
            next_similar_no_match_count = next_fragment_repeat_count
        else:
            next_last_unmatched_address = (
                custom_recorded_address
                or fragment_recorded_address
                or previous_context_recorded_address
                or candidate_backed_partial_address
                or effective_user_scope
                or current_input
                or model_fragment_display_address
            )
            next_similar_no_match_count = next_fragment_repeat_count
    else:
        if is_completed:
            next_last_unmatched_address = ""
            next_similar_no_match_count = 0
        elif llm_matched_index >= 0:
            next_last_unmatched_address = confirm_context_address
            next_similar_no_match_count = 0
        elif is_unmatched_for_fragment_count:
            next_last_unmatched_address = prev_unmatched_raw
            next_similar_no_match_count = next_fragment_repeat_count
        elif multi_match_recorded_address:
            next_last_unmatched_address = multi_match_recorded_address
            next_similar_no_match_count = 0
        else:
            next_last_unmatched_address = prev_unmatched_raw
            next_similar_no_match_count = next_fragment_repeat_count

    REPLY_LAYER = "好的，请您再说一下具体的小区或村镇名称。"
    REPLY_DETAIL = "请您提供详细的地址信息"
    REPLY_CORRECT = "请您提供正确完整的地址信息"

    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed:
        if is_extract_failed:
            reply = ""
        elif display_recorded_address and _is_layer_missing(display_recorded_address):
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{display_recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        elif current_is_level5_place_only:
            recorded_address = display_recorded_address
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        elif custom_followup_reply:
            reply = custom_followup_reply
        elif fragment_followup_reply:
            reply = fragment_followup_reply
        elif previous_context_followup_reply:
            reply = previous_context_followup_reply
        elif candidate_backed_partial_reply:
            reply = candidate_backed_partial_reply
        elif (
            current_looks_like_address
            and _has_building_or_room(current_input)
            and not (_has_place_anchor(current_input) or _has_named_place_anchor(current_input))
        ):
            reply = f"我记录的地址信息是：{display_recorded_address}，请您再说一下具体的小区或村镇名称。"
        elif should_echo_partial_address:
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{display_recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        else:
            if not current_input:
                reply = REPLY_DETAIL
            elif current_is_layer_missing:
                reply = REPLY_CORRECT if should_force_correct_complete else REPLY_LAYER
            elif current_looks_like_address:
                reply = REPLY_CORRECT
            else:
                reply = REPLY_DETAIL
    elif current_state == "matching" and llm_matched_index < 0 and match_count > 1 and not is_completed:
        reply = multi_match_followup_reply or (
            f"我记录的地址信息是：{multi_match_recorded_address}，请您再提供下详细地址信息"
            if multi_match_recorded_address
            else REPLY_DETAIL
        )

    if current_state == "confirming" and current_matched_index >= 0 and _is_confirming_denial(current_input):
        llm_matched_index = -1
        match_count = 0
        is_completed = False
        is_extract_failed = False
        reply = REPLY_DETAIL
        next_last_unmatched_address = ""
        next_similar_no_match_count = 0
    elif current_state == "completed" and _is_confirming_denial(current_input):
        llm_matched_index = -1
        match_count = 0
        is_completed = False
        is_extract_failed = False
        reply = REPLY_LAYER
        next_last_unmatched_address = ""
        next_similar_no_match_count = 0

    if current_state == "confirming" and current_matched_index >= 0:
        if (
            not _is_confirming_denial(current_input)
            and not is_completed
            and match_count <= 0
            and llm_matched_index < 0
            and not reply
            and not is_extract_failed
        ):
            llm_matched_index = current_matched_index
            match_count = 1

    final_match_count = match_count
    final_matched_index = llm_matched_index
    final_is_completed = is_completed
    final_is_extract_failed = is_extract_failed
    final_reply = reply

    # Phase 2: assemble final output after every validation/demotion rule has run.
    if final_is_completed or final_is_extract_failed:
        final_reply = ""
    elif final_match_count == 1 and final_matched_index >= 0:
        confirm_display_address = current_raw_input or current_input
        final_reply = (
            f"\u8bf7\u95ee\u60a8\u8bf4\u7684\u662f{confirm_display_address}\u5417\uff1f"
            if confirm_display_address
            else ""
        )

    recorded_reply_prefix = "我记录的地址信息是："

    def _replace_recorded_reply_address(reply_text: str, recorded_address: str) -> str:
        reply_text = _to_str(reply_text)
        recorded_address = _to_str(recorded_address)
        if not reply_text.startswith(recorded_reply_prefix) or not recorded_address:
            return reply_text
        reply_tail = reply_text[len(recorded_reply_prefix):]
        split_index = -1
        for marker in ("，请", "。请", ",请"):
            marker_index = reply_tail.find(marker)
            if marker_index > 0 and (split_index < 0 or marker_index < split_index):
                split_index = marker_index
        if split_index >= 0:
            return f"{recorded_reply_prefix}{recorded_address}{reply_tail[split_index:]}"
        return f"{recorded_reply_prefix}{recorded_address}"

    final_display_recorded_address = (
        multi_match_recorded_address
        if final_match_count > 1 and final_matched_index < 0 and multi_match_recorded_address
        else display_recorded_address
    )
    final_reply = _replace_recorded_reply_address(final_reply, final_display_recorded_address)

    final_matched_address_fragment = ""
    if not final_is_completed and not final_is_extract_failed:
        if final_match_count == 1 and final_matched_index >= 0:
            final_matched_address_fragment = model_fragment_for_output or current_input
        elif final_match_count == 0:
            final_matched_address_fragment = (
                model_fragment_for_output
                or custom_recorded_address
                or fragment_recorded_address
                or previous_context_recorded_address
                or candidate_backed_partial_address
                or (display_recorded_address if current_looks_like_address or should_track_unmatched else "")
            )
        elif final_match_count > 1:
            final_matched_address_fragment = model_fragment_for_output or effective_user_scope or current_input

    next_last_unmatched_fragment = ""
    if (
        not final_is_extract_failed
        and not final_is_completed
        and final_matched_index < 0
        and (final_match_count == 0 or final_match_count > 1)
    ):
        next_last_unmatched_fragment = model_matched_address_fragment

    final_ai_context_reply = final_reply
    if final_matched_address_fragment:
        final_ai_context_reply = _replace_recorded_reply_address(
            final_reply,
            final_matched_address_fragment
        )

    output_llm_result = dict(llm_result)
    output_llm_result["match_count"] = final_match_count
    output_llm_result["matched_index"] = final_matched_index
    output_llm_result["is_completed"] = final_is_completed
    output_llm_result["is_extract_failed"] = final_is_extract_failed
    output_llm_result["matched_address_fragment"] = final_matched_address_fragment
    output_llm_result["reply"] = final_reply
    output_llm_result["ai_context_reply"] = final_ai_context_reply

    return {
        "llm_result": output_llm_result,
        "next_last_unmatched_address": next_last_unmatched_address,
        "next_last_unmatched_fragment": next_last_unmatched_fragment,
        "next_similar_no_match_count": next_similar_no_match_count
    }
