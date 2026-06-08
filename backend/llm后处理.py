import re
from difflib import SequenceMatcher

try:
    import pypinyin
except ImportError:
    pypinyin = None

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
        text = _normalize_address_marker_tokens(text)
        text = re.sub(r"\[拼音:.*?\]", "", text)
        text = text.replace("#", "号")
        text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
        return text.lower().strip()


    _PINYIN_CHAR_OVERRIDES = {
        "\u4e91": ("yun",), "\u6548": ("xiao",), "\u9704": ("xiao",), "\u6653": ("xiao",), "\u6821": ("xiao",),
        "\u53bf": ("xian",), "\u73b0": ("xian",), "\u8386": ("pu",), "\u666e": ("pu",), "\u7f8e": ("mei",),
        "\u957f": ("chang", "zhang"), "\u5e38": ("chang",), "\u5c71": ("shan",), "\u519c": ("nong",), "\u573a": ("chang",),
        "\u6811": ("shu",), "\u4e1c": ("dong",), "\u6d1e": ("dong",), "\u6751": ("cun",),
        "\u4e16": ("shi",), "\u56db": ("si",), "\u5b89": ("an",), "\u65b0": ("xin",), "\u57ce": ("cheng",),
        "\u65b9": ("fang",), "\u6b22": ("huan",), "\u666f": ("jing",), "\u4e95": ("jing",), "\u5c0f": ("xiao",), "\u533a": ("qu",),
        "\u6ca7": ("cang",), "\u82cd": ("cang",), "\u4ed3": ("cang",), "\u53c2": ("can", "shen", "cen"),
        "\u6d77": ("hai",), "\u540d": ("ming",), "\u660e": ("ming",), "\u6c11": ("min",),
        "\u8457": ("zhu",), "\u7b51": ("zhu",), "\u4f4f": ("zhu",), "\u67f1": ("zhu",),
        "\u7d2b": ("zi",), "\u5b50": ("zi",), "\u6893": ("zi",), "\u6676": ("jing",),
        "\u60a6": ("yue",), "\u6708": ("yue",), "\u8d8a": ("yue",), "\u9605": ("yue",),
        "\u4fdd": ("bao",), "\u5b9d": ("bao",), "\u5229": ("li",), "\u9999": ("xiang",), "\u69df": ("bin",),
        "\u798f": ("fu",), "\u6276": ("fu",), "\u5b81": ("ning",), "\u4e2d": ("zhong",), "\u8def": ("lu",),
        "\u53f7": ("hao",), "\u597d": ("hao",), "\u697c": ("lou",), "\u7701": ("sheng",), "\u5e02": ("shi",), "\u9547": ("zhen",),
        "\u4e61": ("xiang",), "\u8857": ("jie",), "\u9053": ("dao",), "\u5927": ("da",), "\u53a6": ("sha",),
        "\u82b1": ("hua",), "\u56ed": ("yuan",), "\u516c": ("gong",), "\u5bd3": ("yu",), "\u82d1": ("yuan",),
        "\u5e7f": ("guang",), "\u5317": ("bei",), "\u4eac": ("jing",), "\u6df1": ("shen",), "\u5733": ("zhen",),
        "\u5408": ("he",), "\u80a5": ("fei",), "\u5e90": ("lu",), "\u6c5f": ("jiang",), "\u6c64": ("tang",),
        "\u6c60": ("chi",), "\u767e": ("bai",), "\u5357": ("nan",), "\u9633": ("yang",),
    }


    _CN_CHAR_DIGIT_KEYS = {
        "\u96f6": "0", "\u4e00": "1", "\u4e8c": "2", "\u4e24": "2", "\u4e09": "3", "\u56db": "4",
        "\u4e94": "5", "\u516d": "6", "\u4e03": "7", "\u516b": "8", "\u4e5d": "9"
    }

    def _pinyin_variants(py: str) -> set:
        py = _to_str(py).lower().replace("\u00fc", "v").replace("u:", "v")
        py = re.sub(r"[^a-zv]", "", py)
        if not py:
            return set()

        variants = {py}
        if py.startswith("zh"):
            variants.add("z" + py[2:])
        elif py.startswith("ch"):
            variants.add("c" + py[2:])
        elif py.startswith("sh"):
            variants.add("s" + py[2:])

        for item in list(variants):
            if item.endswith("ang"):
                variants.add(item[:-3] + "an")
            if item.endswith("eng"):
                variants.add(item[:-3] + "en")
            if item.endswith("ing"):
                variants.add(item[:-3] + "in")
        return variants

    def _char_pinyin_keys(ch: str) -> set:
        ch = _to_str(ch)
        if not ch:
            return set()

        keys = set()
        if ch in _CN_CHAR_DIGIT_KEYS:
            keys.add(_CN_CHAR_DIGIT_KEYS[ch])
        if pypinyin is not None and re.fullmatch(r"[\u4e00-\u9fa5]", ch):
            try:
                for item in pypinyin.pinyin(ch, heteronym=True, style=pypinyin.NORMAL)[0]:
                    keys.update(_pinyin_variants(item))
            except Exception:
                pass

        for item in _PINYIN_CHAR_OVERRIDES.get(ch, ()): 
            keys.update(_pinyin_variants(item))

        if not keys and re.fullmatch(r"[A-Za-z0-9]", ch):
            keys.add(ch.lower())
        return keys

    def _chars_pinyin_equal(a: str, b: str) -> bool:
        a_keys = _char_pinyin_keys(a)
        b_keys = _char_pinyin_keys(b)
        return bool(a_keys and b_keys and a_keys.intersection(b_keys))

    def _phonetic_text_overlap(a: str, b: str) -> bool:
        a_norm = _normalize_text(a)
        b_norm = _normalize_text(b)
        if not a_norm or not b_norm:
            return False

        if len(a_norm) > len(b_norm):
            a_norm, b_norm = b_norm, a_norm
        if len(a_norm) < 2:
            return False

        for start in range(len(b_norm) - len(a_norm) + 1):
            if all(_chars_fuzzy_equal(a_ch, b_norm[start + idx]) for idx, a_ch in enumerate(a_norm)):
                return True
        return False

    _CANONICAL_ADDRESS_MARKERS = ("号楼", "单元", "号院", "栋", "幢", "座", "楼", "室", "号", "弄", "里")

    def _marker_phonetic_equal(fragment: str, marker: str) -> bool:
        fragment = _to_str(fragment)
        marker = _to_str(marker)
        return bool(
            len(fragment) == len(marker)
            and fragment
            and all(_chars_pinyin_equal(a, b) for a, b in zip(fragment, marker))
        )

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
                        _marker_phonetic_equal(fragment, marker)
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

    _FUZZY_CHAR_GROUPS = (
        "霄效晓校",
        "洞东",
        "世四",
        "方欢",
        "沧参苍仓",
        "名民明",
        "著筑住柱",
        "紫子梓",
        "悦月越阅",
        "莆普",
        "景井",
    )
    _FUZZY_CHAR_MAP = {}
    for _group in _FUZZY_CHAR_GROUPS:
        _group_chars = set(_group)
        for _char in _group_chars:
            _FUZZY_CHAR_MAP.setdefault(_char, set()).update(_group_chars - {_char})

    def _chars_fuzzy_equal(a: str, b: str) -> bool:
        a = _to_str(a)
        b = _to_str(b)
        if not a or not b:
            return False
        if a == b:
            return True
        if _chars_pinyin_equal(a, b):
            return True
        return b in _FUZZY_CHAR_MAP.get(a, set())

    def _best_candidate_slice(user_text: str, candidate_text: str) -> tuple[str, float, int]:
        user_text = _to_str(user_text)
        candidate_text = _to_str(candidate_text)
        if not user_text or not candidate_text:
            return "", 0.0, 0

        target_len = min(len(user_text), len(candidate_text))
        if target_len <= 0:
            return "", 0.0, 0

        compare_user = user_text[:target_len]
        if len(candidate_text) <= target_len:
            candidate_slices = [candidate_text]
        else:
            candidate_slices = [
                candidate_text[i:i + target_len]
                for i in range(len(candidate_text) - target_len + 1)
            ]

        best_slice = ""
        best_score = 0.0
        best_similar_count = 0
        for candidate_slice in candidate_slices:
            total = 0.0
            similar_count = 0
            for user_char, candidate_char in zip(compare_user, candidate_slice):
                if user_char == candidate_char:
                    total += 1.0
                    similar_count += 1
                elif _chars_fuzzy_equal(user_char, candidate_char):
                    total += 0.84
                    similar_count += 1
            score = total / max(len(compare_user), len(candidate_slice), 1)
            if score > best_score or (score == best_score and similar_count > best_similar_count):
                best_slice = candidate_slice
                best_score = score
                best_similar_count = similar_count
        return best_slice, best_score, best_similar_count

    def _replace_first(text: str, old: str, new: str) -> str:
        idx = text.find(old)
        if idx < 0:
            return text
        return f"{text[:idx]}{new}{text[idx + len(old):]}"

    def _replace_first_fuzzy(text: str, old: str, new: str) -> str:
        text = _to_str(text)
        old = _to_str(old)
        new = _to_str(new)
        if not text or not old:
            return text

        replaced = _replace_first(text, old, new)
        if replaced != text:
            return replaced

        target_len = len(old)
        if target_len <= 0 or len(text) < target_len:
            return text

        best_index = -1
        best_score = 0.0
        for idx in range(len(text) - target_len + 1):
            segment = text[idx:idx + target_len]
            total = 0.0
            for source_char, segment_char in zip(old, segment):
                if source_char == segment_char:
                    total += 1.0
                elif _chars_fuzzy_equal(source_char, segment_char):
                    total += 0.84
                else:
                    total = -1.0
                    break
            if total < 0:
                continue
            score = total / max(target_len, 1)
            if score > best_score:
                best_index = idx
                best_score = score
                if score >= 0.99:
                    break

        if best_index < 0 or best_score < 0.74:
            return text
        return f"{text[:best_index]}{new}{text[best_index + target_len:]}"

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

    def _build_candidate_aligned_text(user_text: str, candidate_text: str) -> tuple[str, float, int]:
        user_text = _to_str(user_text)
        candidate_text = _to_str(candidate_text)
        if not user_text or not candidate_text:
            return "", 0.0, 0

        corrected_text = user_text
        score_total = 0.0
        matched_count = 0
        place_matched = False

        def _apply_replacement(source_token: str, target_token: str, threshold: float = 0.74):
            nonlocal corrected_text, score_total, matched_count
            source_token = _to_str(source_token)
            target_token = _to_str(target_token)
            if not source_token or not target_token:
                return
            candidate_slice, score, similar_count = _best_candidate_slice(source_token, target_token)
            min_similar = 1 if min(len(source_token), len(candidate_slice)) <= 2 else 2
            if candidate_slice and score >= threshold and similar_count >= min_similar:
                merged_token = "".join(
                    candidate_char
                    if (user_char == candidate_char or _chars_fuzzy_equal(user_char, candidate_char))
                    else user_char
                    for user_char, candidate_char in zip(source_token[:len(candidate_slice)], candidate_slice)
                )
                corrected_text = _replace_first(corrected_text, source_token, merged_token)
                score_total += score
                matched_count += 1

        user_tokens = _extract_conflict_tokens(user_text)
        candidate_tokens = _extract_conflict_tokens(candidate_text)
        user_fragment_tokens = _extract_conflict_tokens(_extract_named_place_fragment(user_text))
        candidate_fragment_tokens = _extract_conflict_tokens(_extract_named_place_fragment(candidate_text))
        for level in ("province", "city", "district"):
            user_value = user_tokens[level][0] if user_tokens[level] else ""
            candidate_value = candidate_tokens[level][0] if candidate_tokens[level] else ""
            _apply_replacement(user_value, candidate_value)

        _matched_before_specific_place = matched_count
        for level in ("town", "road", "community"):
            user_value = (
                user_tokens[level][0] if user_tokens[level]
                else user_fragment_tokens[level][0] if user_fragment_tokens[level] else ""
            )
            candidate_value = (
                candidate_tokens[level][0] if candidate_tokens[level]
                else candidate_fragment_tokens[level][0] if candidate_fragment_tokens[level] else ""
            )
            _apply_replacement(user_value, candidate_value)
        place_matched = matched_count > _matched_before_specific_place

        user_place = _extract_longest_place_token(user_text)
        candidate_place = _extract_longest_place_token(candidate_text)
        place_required = bool(
            user_place
            and user_place not in {
                user_tokens[level][0]
                for level in ("province", "city", "district", "town")
                if user_tokens[level]
            }
        )
        _matched_before_place = matched_count
        _apply_replacement(user_place, candidate_place)
        place_matched = place_matched or matched_count > _matched_before_place

        for user_value, candidate_value in (
            (_extract_building_name(user_text), _extract_building_name(candidate_text)),
            (_extract_unit_name(user_text), _extract_unit_name(candidate_text)),
            (_extract_room_name(user_text), _extract_room_name(candidate_text)),
            (_extract_house_name(user_text), _extract_house_name(candidate_text)),
        ):
            user_value = _to_str(user_value)
            candidate_value = _to_str(candidate_value)
            if not user_value:
                continue
            if not candidate_value or _normalize_text(user_value) != _normalize_text(candidate_value):
                return "", 0.0, 0
            corrected_text = _replace_first(corrected_text, user_value, candidate_value)
            score_total += 1.0
            matched_count += 1

        if place_required and not place_matched:
            return "", 0.0, 0
        if matched_count <= 0:
            return "", 0.0, 0
        return corrected_text, score_total / matched_count, matched_count

    def _find_best_fuzzy_correction(current_text: str, address_list: list) -> str:
        results = []
        current_norm = _normalize_text(current_text)
        current_has_detail = bool(_has_building_or_room(current_text) or _extract_house_name(current_text))
        for address in address_list or []:
            corrected_text, score, matched_count = _build_candidate_aligned_text(current_text, address)
            if not corrected_text or score < 0.74 or matched_count <= 0:
                continue
            corrected_norm = _normalize_text(corrected_text)
            if current_has_detail and not _detail_tokens_preserved(current_text, corrected_text):
                continue
            if current_norm and corrected_norm and len(corrected_norm) + 1 < len(current_norm):
                continue
            if current_norm and corrected_norm and len(corrected_norm) > len(current_norm) + 1:
                continue
            results.append((corrected_text, score, matched_count))

        if not results:
            return ""

        corrected_values = {item[0] for item in results}
        if len(corrected_values) == 1:
            return results[0][0]

        results.sort(key=lambda item: (item[2], item[1], len(_normalize_text(item[0]))), reverse=True)
        if len(results) == 1 or results[0][2] > results[1][2] or results[0][1] >= results[1][1] + 0.12:
            return results[0][0]
        return ""

    def _detail_tokens_preserved(source_text: str, corrected_text: str) -> bool:
        source_text = _to_str(source_text)
        corrected_text = _to_str(corrected_text)
        if not source_text or not corrected_text:
            return False

        for extractor in (
            _extract_building_name,
            _extract_unit_name,
            _extract_room_name,
            _extract_house_name,
        ):
            source_value = extractor(source_text)
            if not source_value:
                continue
            if extractor(corrected_text) != source_value:
                return False
        return True

    def _find_detail_anchored_scope_correction(current_text: str, address_list: list) -> str:
        current_text = _to_str(current_text)
        if not current_text or not isinstance(address_list, list):
            return ""

        detail_values = (
            _extract_building_name(current_text),
            _extract_unit_name(current_text),
            _extract_room_name(current_text),
            _extract_house_name(current_text),
        )
        if not any(detail_values):
            return ""

        raw_named_fragment = _extract_named_place_fragment(current_text)
        current_tokens = _extract_conflict_tokens(current_text)
        fragment_tokens = _extract_conflict_tokens(raw_named_fragment)

        user_place_candidates = []
        for value in (
            current_tokens["town"][0] if current_tokens["town"] else "",
            current_tokens["road"][0] if current_tokens["road"] else "",
            current_tokens["community"][0] if current_tokens["community"] else "",
            fragment_tokens["town"][0] if fragment_tokens["town"] else "",
            fragment_tokens["road"][0] if fragment_tokens["road"] else "",
            fragment_tokens["community"][0] if fragment_tokens["community"] else "",
            raw_named_fragment,
        ):
            value = _to_str(value)
            norm = _normalize_text(value)
            if (
                value
                and len(norm) >= 2
                and not (_has_building_or_room(value) or _extract_house_name(value))
                and value not in user_place_candidates
            ):
                user_place_candidates.append(value)

        if not user_place_candidates:
            return ""

        results = []
        for address in address_list or []:
            address = _to_str(address)
            if not address:
                continue
            if _has_strong_conflict(current_text, address) or _has_precise_detail_conflict(current_text, address):
                continue

            candidate_tokens = _extract_conflict_tokens(address)
            candidate_fragment_tokens = _extract_conflict_tokens(_extract_named_place_fragment(address))
            candidate_values = []
            for source_tokens in (candidate_tokens, candidate_fragment_tokens):
                for level in ("town", "road", "community"):
                    value = source_tokens[level][0] if source_tokens[level] else ""
                    value = _to_str(value)
                    if value and value not in candidate_values:
                        candidate_values.append(value)

            corrected_text = current_text
            replaced = False
            for user_value in user_place_candidates:
                for candidate_value in candidate_values:
                    if not _phonetic_text_overlap(user_value, candidate_value):
                        continue
                    updated_text = _replace_first_fuzzy(corrected_text, user_value, candidate_value)
                    if updated_text == corrected_text:
                        detail_prefix = _extract_address_prefix(corrected_text, user_value)
                        if detail_prefix:
                            updated_text = f"{detail_prefix}{candidate_value}"
                    if updated_text != corrected_text:
                        corrected_text = updated_text
                        replaced = True
                        break
                if replaced:
                    break

            if replaced:
                results.append(corrected_text)

        if not results:
            return ""

        corrected_values = list(dict.fromkeys(results))
        return corrected_values[0] if len(corrected_values) == 1 else ""

    def _find_fuzzy_unique_match(current_text: str, address_list: list) -> tuple[int, str]:
        matches = []
        for idx, address in enumerate(address_list or []):
            corrected_text, score, matched_count = _build_candidate_aligned_text(current_text, address)
            if not corrected_text or score < 0.74 or matched_count <= 0:
                continue
            if _has_strong_conflict(corrected_text, address) or _has_precise_detail_conflict(corrected_text, address):
                continue

            has_detail = bool(_has_building_or_room(corrected_text) or _extract_house_name(corrected_text))
            has_confirmable_place = bool(re.search("(\u793e\u533a|\u6751\u7ec4|\u6751|\u8def|\u5927\u9053|\u5df7|\u80e1\u540c|\u8857(?!\u9053)|\u5f04|\u91cc|\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u697c\u5b87|\u82d1)", corrected_text))
            if has_detail:
                if not (_has_place_anchor(corrected_text) or _has_named_place_anchor(corrected_text) or _has_matchable_place_level(corrected_text)):
                    continue
            elif not has_confirmable_place:
                continue

            matches.append((idx, corrected_text, score, matched_count))

        if len(matches) == 1:
            return matches[0][0], matches[0][1]

        if matches:
            matches.sort(key=lambda item: (item[3], item[2], len(_normalize_text(item[1]))), reverse=True)
            if len(matches) == 1 or matches[0][3] > matches[1][3] or matches[0][2] >= matches[1][2] + 0.12:
                return matches[0][0], matches[0][1]
        return -1, ""

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

    def _is_exact_layer_reply(text: str) -> bool:
        text = _to_str(text)
        return text == "\u597d\u7684\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"

    def _is_similar(a: str, b: str) -> bool:
        na, nb = _normalize_text(a), _normalize_text(b)
        if not na or not nb:
            return False
        if na == nb or na in nb or nb in na:
            return True
        if _phonetic_text_overlap(a, b):
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
                if _phonetic_text_overlap(a, b):
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

            for recorded_value in recorded_values:
                for fallback_value in fallback_values:
                    if not _phonetic_text_overlap(recorded_value, fallback_value):
                        continue
                    updated_recorded = _replace_first_fuzzy(recorded, recorded_value, fallback_value)
                    if updated_recorded != recorded:
                        recorded = updated_recorded
                        break
                else:
                    continue
                break

        return recorded

    def _build_detail_scope_recorded_address(text: str, address_list: list) -> str:
        text = _to_str(text)
        if not text or not isinstance(address_list, list):
            return ""

        detail_prefix = (
            _extract_building_name(text)
            or _extract_unit_name(text)
            or _extract_room_name(text)
            or _extract_house_name(text)
        )
        raw_named_fragment = _extract_named_place_fragment(text)
        if not detail_prefix or not raw_named_fragment:
            return ""

        candidate_values = []
        for address in address_list or []:
            address = _to_str(address)
            if not address or _has_precise_detail_conflict(text, address):
                continue
            candidate_tokens = _extract_conflict_tokens(address)
            candidate_fragment_tokens = _extract_conflict_tokens(_extract_named_place_fragment(address))
            for source_tokens in (candidate_tokens, candidate_fragment_tokens):
                for level in ("town", "road", "community"):
                    value = source_tokens[level][0] if source_tokens[level] else ""
                    value = _to_str(value)
                    if value and value not in candidate_values:
                        candidate_values.append(value)

        for candidate_value in candidate_values:
            if _phonetic_text_overlap(raw_named_fragment, candidate_value):
                return f"{detail_prefix}{candidate_value}"
        return ""

    def _find_scope_phrase_correction(text: str, address_list: list) -> str:
        text = _to_str(text)
        if not text or not isinstance(address_list, list):
            return ""

        candidate_values = []
        for address in address_list or []:
            address = _to_str(address)
            if not address:
                continue
            candidate_tokens = _extract_conflict_tokens(address)
            candidate_fragment_tokens = _extract_conflict_tokens(_extract_named_place_fragment(address))
            for source_tokens in (candidate_tokens, candidate_fragment_tokens):
                for level in ("town", "road", "community"):
                    value = source_tokens[level][0] if source_tokens[level] else ""
                    value = _to_str(value)
                    if value and value not in candidate_values:
                        candidate_values.append(value)

        matches = [value for value in candidate_values if _phonetic_text_overlap(text, value)]
        matches = list(dict.fromkeys(matches))
        return matches[0] if len(matches) == 1 else ""

    def _find_admin_scope_correction(current_text: str, address_list: list) -> str:
        current_text = _to_str(current_text)
        if not current_text or not isinstance(address_list, list):
            return ""
        if _has_building_or_room(current_text) or _extract_house_name(current_text):
            return ""

        candidates = []
        patterns = (
            r"(?=([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u533a|\u53bf|\u65d7)))",
            r"(?=([\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u8857\u9053|\u9547|\u4e61)))",
            r"(?=([\u4e00-\u9fa5A-Za-z0-9]{1,20}?(?:\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857(?!\u9053))))",
            r"(?=([\u4e00-\u9fa5A-Za-z0-9]{2,20}?(?:\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751)))",
        )

        for address in address_list or []:
            address = _to_str(address)
            if not address:
                continue
            for pattern in patterns:
                for value in re.findall(pattern, address):
                    value = _to_str(value)
                    if value and _phonetic_text_overlap(current_text, value):
                        candidates.append(value)

        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            return ""

        target_len = len(_normalize_text(current_text))
        length_scores = []
        for value in candidates:
            value_len = len(_normalize_text(value))
            if value_len <= 0:
                continue
            length_scores.append((abs(value_len - target_len), value_len, value))
        if not length_scores:
            return ""
        best_distance = min(item[0] for item in length_scores)
        best_candidates = [item[2] for item in length_scores if item[0] == best_distance]
        best_candidates = list(dict.fromkeys(best_candidates))
        return best_candidates[0] if len(best_candidates) == 1 else ""

    def _find_short_phonetic_span_correction(current_text: str, address_list: list) -> str:
        current_text = _to_str(current_text)
        norm = _normalize_text(current_text)
        if not current_text or not isinstance(address_list, list):
            return ""
        if _has_building_or_room(current_text) or _extract_house_name(current_text):
            return ""
        if _has_matchable_place_level(current_text) or _has_named_place_anchor(current_text):
            return ""
        if len(norm) < 2 or len(norm) > 4:
            return ""

        suffix_chars = set("\u533a\u53bf\u65d7\u9547\u4e61\u6751\u8def\u8857")
        matches = []
        span_len = len(current_text)
        for address in address_list or []:
            address = _to_str(address)
            if len(address) < span_len:
                continue
            for start in range(len(address) - span_len + 1):
                segment = address[start:start + span_len]
                if not any(ch in suffix_chars for ch in segment):
                    continue
                if all(_chars_fuzzy_equal(a, b) for a, b in zip(current_text, segment)):
                    matches.append(segment)

        matches = list(dict.fromkeys(matches))
        return matches[0] if len(matches) == 1 else ""

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
                    or _phonetic_text_overlap(named_place_norm, candidate_norm)
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
        if _phonetic_text_overlap(a, b):
            return True

        a_terms = _extract_overlap_terms(a)
        b_terms = _extract_overlap_terms(b)
        for a_term in a_terms:
            for b_term in b_terms:
                if a_term == b_term or a_term in b_term or b_term in a_term:
                    return True
                if _phonetic_text_overlap(a_term, b_term):
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
            if recorded_norm and expected_norm and recorded_norm == expected_norm:
                return recorded_address
            if recorded_norm and expected_norm and recorded_norm.startswith(expected_norm) and recorded_norm != expected_norm:
                return expected_input
            if recorded_norm and expected_norm and recorded_norm.endswith(expected_norm) and recorded_norm != expected_norm:
                return expected_input

        return recorded_address

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


    def _candidate_phonetic_span_match(fragment: str, candidate: str) -> tuple[str, int, int]:
        fragment_norm = _normalize_text(fragment)
        candidate_norm = _normalize_text(candidate)
        if not fragment_norm or not candidate_norm or len(fragment_norm) > len(candidate_norm):
            return "", -1, -1
        for start in range(len(candidate_norm) - len(fragment_norm) + 1):
            span = candidate_norm[start:start + len(fragment_norm)]
            if all(_chars_fuzzy_equal(a, b) for a, b in zip(fragment_norm, span)):
                return span, start, start + len(fragment_norm)
        return "", -1, -1

    def _candidate_phonetic_span(fragment: str, candidate: str) -> str:
        span, _start, _end = _candidate_phonetic_span_match(fragment, candidate)
        return span

    def _replace_first_phonetic_span(text: str, old: str, new: str) -> str:
        text = _normalize_address_marker_tokens(_to_str(text))
        old = _normalize_address_marker_tokens(_to_str(old))
        new = _normalize_address_marker_tokens(_to_str(new))
        if not text or not old or not new:
            return text
        if old in text:
            return text.replace(old, new, 1)
        if len(old) > len(text):
            return text
        for start in range(len(text) - len(old) + 1):
            segment = text[start:start + len(old)]
            if all(_chars_fuzzy_equal(a, b) for a, b in zip(old, segment)):
                return f"{text[:start]}{new}{text[start + len(old):]}"
        return text

    def _add_candidate_backed_term(terms: list, value: str, min_len: int = 2) -> None:
        value = _normalize_address_marker_tokens(_to_str(value))
        norm = _normalize_text(value)
        if len(norm) >= min_len and norm not in {item[1] for item in terms}:
            terms.append((value, norm))

    def _is_candidate_detail_term(value: str) -> bool:
        value_norm = _normalize_text(value)
        if not value_norm:
            return False
        for extractor in (_extract_building_name, _extract_unit_name, _extract_room_name, _extract_house_name):
            extracted = extractor(value)
            if extracted and _normalize_text(extracted) == value_norm:
                return True
        return False

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
            spans = []
            for item in required_terms:
                span, start, end = _candidate_phonetic_span_match(item["value"], address)
                if not span:
                    spans = []
                    break
                spans.append((item["value"], span, start, end, item["sources"]))
            if not spans:
                continue
            if not any("prev" in sources for _value, _span, _start, _end, sources in spans):
                continue
            if not any("curr" in sources for _value, _span, _start, _end, sources in spans):
                continue
            window_start = min(start for _value, _span, start, _end, _sources in spans)
            window_end = max(end for _value, _span, _start, end, _sources in spans)
            if window_start < 0 or window_end <= window_start:
                continue

            corrected = combined
            for value, span, _start, _end, _sources in sorted(spans, key=lambda item: len(_normalize_text(item[0])), reverse=True):
                if not _is_candidate_detail_term(value):
                    corrected = _replace_first_phonetic_span(corrected, value, span)
            results.append(corrected)

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
                or _phonetic_text_overlap(fragment_norm, address)
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

        def _allow_same_scope_replacement(source_text: str, candidate_text: str) -> bool:
            source_norm = _normalize_text(source_text)
            candidate_norm = _normalize_text(candidate_text)
            if not source_norm or not candidate_norm:
                return False
            if source_norm == candidate_norm:
                return True
            if source_norm in candidate_norm or candidate_norm in source_norm:
                return len(source_norm) == len(candidate_norm)
            return abs(len(source_norm) - len(candidate_norm)) <= 1

        matched_candidates = []
        for address in address_list:
            candidate = _to_str(address)
            if not candidate or _has_strong_conflict(current_input, candidate) or _has_precise_detail_conflict(current_input, candidate):
                continue

            spans = []
            for value, _norm, kind in terms:
                span, _start, _end = _candidate_phonetic_span_match(value, candidate)
                if not span:
                    spans = []
                    break
                spans.append((value, span, kind))
            if spans:
                matched_candidates.append((candidate, spans))

        if not matched_candidates:
            return "", ""

        corrected = current_input
        for value, span, _kind in sorted(matched_candidates[0][1], key=lambda item: len(_normalize_text(item[0])), reverse=True):
            if span and _allow_same_scope_replacement(value, span):
                corrected = _replace_first_phonetic_span(corrected, value, span)

        recorded_address = _to_str(corrected)
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

    corrected_current_input = _find_best_fuzzy_correction(current_input, address_list)
    if not corrected_current_input:
        short_span_corrected_input = _find_short_phonetic_span_correction(current_input, address_list)
        if short_span_corrected_input:
            corrected_current_input = short_span_corrected_input
    fuzzy_corrected_current_input = bool(
        corrected_current_input
        and _normalize_text(corrected_current_input) != _normalize_text(current_input)
    )
    if corrected_current_input:
        current_input = corrected_current_input

    if (
        mergeable_prev_unmatched
        and current_raw_input
        and current_input == current_raw_input
        and not _has_address_overlap(current_raw_input, mergeable_prev_unmatched)
        and not _has_any_candidate_overlap(current_raw_input, address_list)
    ):
        ignored_no_overlap_input = True
        current_input = mergeable_prev_unmatched

    if mergeable_prev_unmatched and re.fullmatch(r"\d{3,6}", mergeable_prev_unmatched):
        detail_tail = current_raw_input[len(mergeable_prev_unmatched):] if current_raw_input.startswith(mergeable_prev_unmatched) else ""
        corrected_tail = _find_scope_phrase_correction(detail_tail, address_list)
        if corrected_tail:
            current_input = _merge_user_spoken_scope(mergeable_prev_unmatched, corrected_tail)

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

    prev_repeat_count = max(_to_int(similar_no_match_count, 0), 0)
    SIMILAR_NO_MATCH_FAIL_THRESHOLD = 2

    def _next_repeat_count(min_count: int = 1) -> int:
        return max(prev_repeat_count + 1, min_count)

    def _should_fail_by_repeat(next_count: int) -> bool:
        return next_count >= SIMILAR_NO_MATCH_FAIL_THRESHOLD

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
        return {
            "llm_result": {
                "match_count": 1,
                "matched_index": current_matched_index,
                "is_completed": False,
                "is_extract_failed": False,
                "reply": ""
            },
            "next_last_unmatched_address": prev_unmatched_raw,
            "next_similar_no_match_count": next_count
        }

    def _build_extract_failed_result() -> dict:
        return {
            "llm_result": {
                "match_count": 0,
                "matched_index": -1,
                "is_completed": False,
                "is_extract_failed": True,
                "reply": ""
            },
            "next_last_unmatched_address": "",
            "next_similar_no_match_count": 0
        }

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
        next_repeat_count = _next_repeat_count()
        if current_state == "confirming" and current_matched_index >= 0:
            if _should_fail_by_repeat(next_repeat_count):
                llm_result = {
                    "match_count": 0,
                    "matched_index": -1,
                    "is_completed": False,
                    "is_extract_failed": True,
                    "reply": ""
                }
                return {
                    "llm_result": llm_result,
                    "next_last_unmatched_address": "",
                    "next_similar_no_match_count": 0
                }

            llm_result = {
                "match_count": 1,
                "matched_index": current_matched_index,
                "is_completed": False,
                "is_extract_failed": False,
                "reply": ""
            }
            return {
                "llm_result": llm_result,
                "next_last_unmatched_address": prev_unmatched_raw,
                "next_similar_no_match_count": next_repeat_count
            }
        else:
            meaningless_extract_failed = _should_fail_by_repeat(next_repeat_count)
            llm_result = {
                "match_count": 0,
                "matched_index": -1,
                "is_completed": False,
                "is_extract_failed": meaningless_extract_failed,
                "reply": "" if meaningless_extract_failed else (meaningless_reply or "请您提供详细的地址信息")
            }
        return {
            "llm_result": llm_result,
            "next_last_unmatched_address": "" if llm_result["is_extract_failed"] else prev_unmatched_raw,
            "next_similar_no_match_count": 0 if llm_result["is_extract_failed"] else next_repeat_count
        }

    model_match_count = max(_to_int(llm_result.get("match_count"), 0), 0)
    model_matched_index = _to_int(llm_result.get("matched_index"), -1)
    model_is_completed = _to_bool(llm_result.get("is_completed", False))
    model_is_extract_failed = _to_bool(llm_result.get("is_extract_failed", llm_result.get("extract_failed", False)))
    model_reply = _to_str(llm_result.get("reply"))
    # Phase 1: calculate internal decisions only. The incoming llm_result is
    # not updated until the final assembly block at the end of the function.
    match_count = model_match_count
    llm_matched_index = model_matched_index
    is_completed = model_is_completed
    is_extract_failed = model_is_extract_failed
    reply = model_reply
    recorded_address_from_reply = _extract_recorded_address_from_reply(reply)
    sanitized_recorded_address = _sanitize_recorded_address(
        recorded_address_from_reply,
        effective_user_scope,
        mergeable_prev_unmatched
    )
    if sanitized_recorded_address != recorded_address_from_reply:
        reply = _replace_recorded_address_in_reply(
            reply,
            recorded_address_from_reply,
            sanitized_recorded_address
        )
        recorded_address_from_reply = sanitized_recorded_address
    source_reply = reply

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
        and not _has_full_building_unit_room_detail(current_input)
        and (
            _should_reject_place_less_unique_match(current_input)
            or not _has_matchable_place_level(current_input)
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

    fuzzy_corrected_unique_input = ""
    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed and not is_extract_failed:
        fuzzy_matched_index, fuzzy_corrected_unique_input = _find_fuzzy_unique_match(current_input, address_list)
        if fuzzy_matched_index >= 0:
            pending_unique_matched_index = fuzzy_matched_index
            pending_unique_input = fuzzy_corrected_unique_input

    if pending_unique_matched_index >= 0:
        pending_input = pending_unique_input or current_input
        if not _candidate_has_unspoken_specific_place(pending_input, address_list, pending_unique_matched_index):
            current_input = pending_input
            llm_matched_index = pending_unique_matched_index
            match_count = 1
            reply = ""

    unspoken_specific_place_demoted = False
    if (
        current_state == "matching"
        and match_count == 1
        and llm_matched_index >= 0
        and not is_completed
        and not is_extract_failed
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
    previous_has_candidate_overlap = bool(
        prev_unmatched
        and len(_normalize_text(prev_unmatched)) >= 2
        and (
            _has_any_candidate_overlap(prev_unmatched, address_list)
            or _has_literal_candidate_overlap(prev_unmatched)
        )
    )
    current_raw_no_candidate_overlap = bool(current_raw_input and not current_raw_has_candidate_overlap)
    previous_no_candidate_overlap = bool(
        prev_unmatched
        and (_is_non_merge_history(prev_unmatched_raw) or not previous_has_candidate_overlap)
    )
    current_room_or_building_overlaps_candidate = bool(
        current_input
        and _has_building_or_room(current_input)
        and _has_any_candidate_overlap(current_input, address_list)
    )
    fuzzy_named_place_candidate = bool(
        fuzzy_corrected_current_input
        and _has_named_place_anchor(current_input)
        and not _has_place_anchor(current_input)
        and not (_has_building_or_room(current_input) or _extract_house_name(current_input))
    )
    current_looks_like_address = (
        _looks_like_address(current_input)
        or current_has_candidate_scope_overlap
        or current_room_or_building_overlaps_candidate
        or fuzzy_named_place_candidate
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
        if recorded_address_from_reply:
            recorded_address_from_reply, reply = _prefer_recorded_followup(
                recorded_address_from_reply,
                reply,
                custom_recorded_address,
                custom_followup_reply,
                mergeable_prev_unmatched,
                current_input
            )

    candidate_backed_partial_reply = ""
    candidate_backed_partial_address = ""
    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed and not is_extract_failed:
        candidate_backed_partial_reply, candidate_backed_partial_address = _build_candidate_backed_partial_followup(
            current_input,
            address_list
        )
    detail_scope_corrected_input = _find_detail_anchored_scope_correction(current_input, address_list)
    detail_scope_recorded_address = _build_detail_scope_recorded_address(current_input, address_list)
    use_detail_scope_recorded_address = bool(
        detail_scope_recorded_address
        and mergeable_prev_unmatched
        and re.fullmatch(r"\d{3,6}", mergeable_prev_unmatched)
    )

    should_track_unmatched = (
        current_state == "matching"
        and llm_matched_index < 0
        and match_count == 0
        and not is_completed
        and bool(current_input)
        and (
            current_looks_like_address
            or current_raw_no_candidate_overlap
            or bool(recorded_address_from_reply)
            or bool(custom_recorded_address)
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
    candidate_overlap_scope = effective_user_scope or current_input
    if prev_unmatched and current_input and _has_address_overlap(prev_unmatched, current_input):
        candidate_overlap_scope = _merge_user_spoken_scope(prev_unmatched, current_input)
    current_has_candidate_overlap = (
        _has_any_candidate_overlap(candidate_overlap_scope, address_list)
        or _has_literal_candidate_overlap(candidate_overlap_scope)
    )
    def _has_count_reset_place_anchor(text: str) -> bool:
        place_fragment = _strip_leading_admin_tokens(_extract_named_place_fragment(text))
        place_norm = _normalize_text(place_fragment)
        text_norm = _normalize_text(text)
        return bool(
            len(place_norm) >= 2
            and (
                _has_place_anchor(place_fragment)
                or _has_named_place_anchor(place_fragment)
                or not _has_building_or_room(text)
            )
            or (
                len(text_norm) >= 4
                and re.search(r"[\u4e00-\u9fa5]", text_norm)
                and not _has_building_or_room(text)
            )
        )

    repeated_previous_address = bool(
        prev_unmatched
        and current_raw_input
        and _is_similar(current_raw_input, prev_unmatched)
        and not _is_extension_of_previous(current_raw_input, prev_unmatched)
    )
    should_reset_similar_count_for_candidate_overlap = bool(
        unspoken_specific_place_demoted
        or
        not repeated_previous_address
        and (
        (current_has_candidate_overlap and _has_count_reset_place_anchor(candidate_overlap_scope))
        or (
            candidate_backed_partial_address
            and _has_count_reset_place_anchor(candidate_backed_partial_address)
        )
        )
    )
    current_no_candidate_overlap = current_raw_no_candidate_overlap and previous_no_candidate_overlap
    should_fail_for_consecutive_no_overlap = (
        should_track_unmatched
        and (current_no_candidate_overlap or repeated_previous_address)
        and _should_fail_by_repeat(_next_repeat_count())
    )

    if should_track_unmatched:
        if should_fail_for_consecutive_no_overlap:
            is_extract_failed = True
            match_count = 0
            llm_matched_index = -1
            is_completed = False
            reply = ""
            next_last_unmatched_address = ""
            next_similar_no_match_count = 0
        elif ignored_no_overlap_input:
            next_last_unmatched_address = prev_unmatched_raw
            next_similar_no_match_count = _next_repeat_count()
        elif should_reset_unmatched_for_broad_no_overlap:
            next_last_unmatched_address = _mark_non_merge_history(current_input)
            next_similar_no_match_count = 1
        else:
            next_last_unmatched_address = (
                recorded_address_from_reply
                or effective_user_scope
                or custom_recorded_address
                or candidate_backed_partial_address
                or (detail_scope_recorded_address if use_detail_scope_recorded_address else "")
                or detail_scope_corrected_input
                or current_input
            )
            next_similar_no_match_count = 0 if should_reset_similar_count_for_candidate_overlap else 1
    else:
        if is_completed:
            next_last_unmatched_address = ""
            next_similar_no_match_count = 0
        elif llm_matched_index >= 0:
            next_last_unmatched_address = confirm_context_address
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
        elif current_state == "completed":
            reply = REPLY_LAYER
        elif current_state == "matching":
            reply = ""

    if current_state == "matching" and llm_matched_index < 0 and match_count == 0 and not is_completed:
        if is_extract_failed:
            reply = ""
        elif current_is_level5_place_only:
            recorded_address = recorded_address_from_reply or current_input
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        elif recorded_address_from_reply:
            pass
        elif fuzzy_named_place_candidate:
            recorded_address = (detail_scope_recorded_address if use_detail_scope_recorded_address else "") or current_input
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{recorded_address}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"

        elif custom_followup_reply:
            reply = custom_followup_reply
        elif candidate_backed_partial_reply and reply in {"", REPLY_LAYER, REPLY_DETAIL, REPLY_CORRECT}:
            reply = candidate_backed_partial_reply
        elif (
            current_looks_like_address
            and _has_building_or_room(current_input)
            and not (_has_place_anchor(current_input) or _has_named_place_anchor(current_input))
        ):
            reply = f"我记录的地址信息是：{current_input}，请您再说一下具体的小区或村镇名称。"
        elif should_echo_partial_address:
            reply = f"\u6211\u8bb0\u5f55\u7684\u5730\u5740\u4fe1\u606f\u662f\uff1a{current_input}\uff0c\u8bf7\u60a8\u518d\u8bf4\u4e00\u4e0b\u5177\u4f53\u7684\u5c0f\u533a\u6216\u6751\u9547\u540d\u79f0\u3002"
        elif reply == REPLY_LAYER or _is_exact_layer_reply(reply):
            has_supported_partial_address = bool(
                candidate_backed_partial_address
                or recorded_address_from_reply
                or custom_recorded_address
                or should_echo_partial_address
            )
            if should_force_correct_complete and not has_supported_partial_address:
                reply = REPLY_CORRECT
            elif current_address_level >= 5 and not has_supported_partial_address:
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

    final_match_count = match_count
    final_matched_index = llm_matched_index
    final_is_completed = is_completed
    final_is_extract_failed = is_extract_failed
    final_reply = reply

    # Phase 2: assemble final output after every validation/demotion rule has run.
    if (
        final_is_completed
        or final_is_extract_failed
        or (final_match_count == 1 and final_matched_index >= 0)
    ):
        final_reply = ""
    elif not final_reply and source_reply:
        final_reply = source_reply

    final_recorded_address = _extract_recorded_address_from_reply(final_reply)
    if (
        current_state == "matching"
        and final_matched_index < 0
        and final_match_count == 0
        and not final_is_completed
        and not final_is_extract_failed
        and final_recorded_address
    ):
        next_last_unmatched_address = final_recorded_address
        if next_similar_no_match_count <= 0:
            final_recorded_has_candidate_overlap = (
                should_reset_similar_count_for_candidate_overlap
                or _has_any_candidate_overlap(final_recorded_address, address_list)
                and _has_count_reset_place_anchor(final_recorded_address)
                or (
                    _has_literal_candidate_overlap(final_recorded_address)
                    and _has_count_reset_place_anchor(final_recorded_address)
                )
            )
            next_similar_no_match_count = 0 if final_recorded_has_candidate_overlap else 1

    output_llm_result = dict(llm_result)
    output_llm_result["match_count"] = final_match_count
    output_llm_result["matched_index"] = final_matched_index
    output_llm_result["is_completed"] = final_is_completed
    output_llm_result["is_extract_failed"] = final_is_extract_failed
    output_llm_result["reply"] = final_reply

    return {
        "llm_result": output_llm_result,
        "next_last_unmatched_address": next_last_unmatched_address,
        "next_similar_no_match_count": next_similar_no_match_count
    }

