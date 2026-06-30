import re
import json
from functools import lru_cache

def main(args: dict) -> dict:
    try:
        import pypinyin
        has_pinyin = True
    except ImportError:
        has_pinyin = False

    user_input = (args.get("userInput") or "").strip()
    state = (args.get("state") or "matching").strip()
    matched_index = args.get("matchedIndex", -1)
    last_unmatched_address_raw = (args.get("last_unmatched_address") or "").strip()
    last_unmatched_fragment_raw = (args.get("last_unmatched_fragment") or "").strip()

    try:
        similar_no_match_count = int(args.get("similar_no_match_count") or 0)
    except (ValueError, TypeError):
        similar_no_match_count = 0

    NON_MERGE_HISTORY_PREFIX = "__NO_MERGE__:"

    def is_non_merge_history(text):
        return str(text or "").strip().startswith(NON_MERGE_HISTORY_PREFIX)

    def strip_non_merge_history(text):
        text = str(text or "").strip()
        if is_non_merge_history(text):
            return text[len(NON_MERGE_HISTORY_PREFIX):].strip()
        return text

    def strip_embedded_reason_field(text):
        text = str(text or "").strip()
        if not text:
            return ""
        text = re.sub(
            r"""(?is)\s*[,，]?\\?["']?\s*reason\s*\\?["']?\s*[:：]\s*\\?["']?(?:one|two|true|false|只命中最后一级|只命中倒数第二级|命中最后两级)?\\?["']?.*$""",
            "",
            text
        )
        text = re.sub(
            r"""(?is)\s*[,，]?\s*['"]?\s*reason\s*['"]?\s*[:：]\s*['"]?(?:one|two|true|false|只命中最后一级|只命中倒数第二级|命中最后两级)?['"]?.*$""",
            "",
            text
        )
        text = re.sub(r"""(?is)\s*\\?["']\s*[,，]\s*\\?["']?\s*reason\s*\\?["']?.*$""", "", text)
        text = re.sub(r"""(?is)\s*['"],\s*['"]?\s*reason\s*['"]?.*$""", "", text)
        return text.strip(" ,，'\"")

    def clean_prefix(text):
        if not text:
            return ""
        text = str(text).strip()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"^(?:我的地址(?:是|在)?|我(?:现在)?(?:住在|在)|我家(?:在)?|住在|住址是|地址(?:是|在)|我的|我是|在|大概在|就|那个)", "", text)
        text = re.sub(r"^(?:河北省?|石家庄市?)+", "", text)

        admin_regions = [
            "长安区", "桥西区", "新华区", "裕华区", "井陉矿区", "藁城区", "鹿泉区", "栾城区",
            "井陉县", "正定县", "行唐县", "灵寿县", "赞皇县", "平山县", "元氏县", "赵县",
            "晋州市", "新乐市", "高新区", "开发区"
        ]
        admin_regions.sort(key=len, reverse=True)

        for region in admin_regions:
            if text.startswith(region):
                text = text[len(region):]
                break

        return text.strip()

    def _has_candidate_noise_address_evidence(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        if not text:
            return False

        norm = normalize_text(text)
        if not norm:
            return False

        if re.search(r"[A-Za-z0-9]", norm):
            return True
        if _has_strong_address_structure(text):
            return True
        if is_weak_area_fragment(text):
            return True
        if re.search(
            r"(省|市|区|县|旗|镇|乡|街道|大道|路|巷|胡同|街|小区|社区|园区|校区|景区|厂区|"
            r"花园|公园|家园|公寓|大厦|广场|中心|大院|苑|府|村|庄|城|湾|庭|郡|都|"
            r"栋|幢|座|楼|单元|室|号|院|弄|里|门|口|侧|东|西|南|北|中|"
            r"厂|公司|学校|医院|商场|市场|酒店)",
            text
        ):
            return True

        return False

    def _is_discardable_candidate_noise(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        if not text:
            return True

        return not _has_candidate_noise_address_evidence(text)

    def clean_candidate_supported_noise(text, candidates):
        text = normalize_address_marker_tokens(str(text or "").strip())
        if not text or not isinstance(candidates, list) or not candidates:
            return text

        text_norm = normalize_text(text)
        if not text_norm:
            return text

        normalized_candidates = []
        for candidate in candidates:
            candidate_text = normalize_address_marker_tokens(str(candidate or "").strip())
            candidate_norm = normalize_text(candidate_text)
            if candidate_text and candidate_norm:
                normalized_candidates.append((candidate_text, candidate_norm))

        if not normalized_candidates:
            return text

        for candidate_text, candidate_norm in normalized_candidates:
            if text_norm in candidate_norm or _phonetic_substring_match(text, candidate_text):
                return text

        best = None
        text_len = len(text)
        for candidate_text, candidate_norm in normalized_candidates:
            for start in range(text_len):
                for end in range(start + 2, text_len + 1):
                    if start == 0 and end == text_len:
                        continue

                    span = text[start:end]
                    span_norm = normalize_text(span)
                    if len(span_norm) < 2:
                        continue

                    supported = span_norm in candidate_norm or _phonetic_substring_match(span, candidate_text)
                    if not supported:
                        continue

                    has_signal = (
                        _has_candidate_overlap_span_signal(span)
                        or has_building_or_room(span)
                        or bool(_extract_house_name(span))
                        or is_room_number_fragment(span)
                    )
                    if not has_signal:
                        continue

                    prefix = text[:start]
                    suffix = text[end:]
                    if not _is_discardable_candidate_noise(prefix):
                        continue
                    if not _is_discardable_candidate_noise(suffix):
                        continue

                    prefix_norm = normalize_text(prefix)
                    suffix_norm = normalize_text(suffix)
                    score = (
                        len(span_norm) * 100
                        + (30 if has_signal else 0)
                        - len(prefix_norm) * 5
                        - len(suffix_norm) * 5
                        - start
                    )
                    item = (score, len(span_norm), span)
                    if best is None or item > best:
                        best = item

        return best[2].strip() if best else text

    def extract_effective_input(text):
        return clean_prefix(text)

    @lru_cache(maxsize=4096)
    def normalize_text(text):
        text = str(text or "").strip()
        text = normalize_address_marker_tokens(text)
        text = normalize_address_number_compare_tokens(text)
        text = re.sub(r"\[拼音:.*?\]", "", text)
        text = text.replace("#", "号")
        text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
        return text.lower()


    _PINYIN_CHAR_OVERRIDES = {
        "\u4e91": ("yun",), "\u6548": ("xiao",), "\u9704": ("xiao",), "\u6653": ("xiao",), "\u6821": ("xiao",),
        "\u53bf": ("xian",), "\u8386": ("pu",), "\u666e": ("pu",), "\u7f8e": ("mei",),
        "\u957f": ("chang", "zhang"), "\u5e38": ("chang",), "\u5c71": ("shan",), "\u519c": ("nong",), "\u573a": ("chang",),
        "\u6811": ("shu",), "\u4e1c": ("dong",), "\u6d1e": ("dong",), "\u6751": ("cun",),
        "\u4e16": ("shi",), "\u56db": ("si",), "\u5b89": ("an",), "\u65b0": ("xin",), "\u57ce": ("cheng",),
        "\u65b9": ("fang",), "\u82b3": ("fang",), "\u6b22": ("huan",), "\u7559": ("liu",),
        "\u666f": ("jing",), "\u4e95": ("jing",), "\u5c0f": ("xiao",), "\u533a": ("qu",),
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

    _FUZZY_CHAR_GROUPS_FOR_PINYIN = (
        "\u9704\u6548\u6653\u6821", "\u6d1e\u4e1c", "\u4e16\u56db", "\u65b9\u6b22", "\u6ca7\u53c2\u82cd\u4ed3",
        "\u540d\u6c11\u660e", "\u8457\u7b51\u4f4f\u67f1", "\u7d2b\u5b50\u6893", "\u60a6\u6708\u8d8a\u9605", "\u8386\u666e", "\u666f\u4e95",
    )
    _FUZZY_CHAR_MAP_FOR_PINYIN = {}
    for _group in _FUZZY_CHAR_GROUPS_FOR_PINYIN:
        _chars = set(_group)
        for _char in _chars:
            _FUZZY_CHAR_MAP_FOR_PINYIN.setdefault(_char, set()).update(_chars - {_char})


    _CN_CHAR_DIGIT_KEYS = {
        "\u96f6": "0", "〇": "0", "\u4e00": "1", "\u4e8c": "2", "\u4e24": "2", "\u4e09": "3", "\u56db": "4",
        "\u4e94": "5", "\u516d": "6", "\u4e03": "7", "\u516b": "8", "\u4e5d": "9"
    }

    _CN_NUMBER_DIGITS = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
    }
    _CN_NUMBER_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    _CN_ADDRESS_NUMBER_CHARS = "一二两三四五六七八九十百千万零〇"

    @lru_cache(maxsize=1024)
    def _cn_number_to_arabic(text):
        text = str(text or "").strip()
        if not text:
            return ""

        if re.fullmatch(r"[零〇一二两三四五六七八九]+", text):
            return "".join(str(_CN_NUMBER_DIGITS[ch]) for ch in text)

        total = 0
        section = 0
        number = 0
        for ch in text:
            if ch in _CN_NUMBER_DIGITS:
                number = _CN_NUMBER_DIGITS[ch]
                continue
            unit = _CN_NUMBER_UNITS.get(ch)
            if not unit:
                return text
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0

        return str(total + section + number)

    @lru_cache(maxsize=4096)
    def normalize_address_number_compare_tokens(text):
        text = str(text or "").strip()
        if not text:
            return ""

        cn_num = f"[{_CN_ADDRESS_NUMBER_CHARS}]+"
        if re.fullmatch(cn_num, text):
            return _cn_number_to_arabic(text)

        # 只用于比较归一化，不能用这个结果替换用户原话。
        text = re.sub(
            fr"({cn_num})(?=号楼|楼|栋|幢|座|单元|室)",
            lambda m: _cn_number_to_arabic(m.group(1)),
            text
        )
        text = re.sub(
            fr"(?<=单元)({cn_num})(?=室|$|[^\u4e00-\u9fa5A-Za-z0-9])",
            lambda m: _cn_number_to_arabic(m.group(1)),
            text
        )
        text = text.replace("号楼", "楼")
        return text

    @lru_cache(maxsize=1024)
    def pinyin_variants(py):
        py = str(py or "").lower().replace("\u00fc", "v").replace("u:", "v")
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

    @lru_cache(maxsize=2048)
    def char_pinyin_keys(ch):
        ch = str(ch or "").strip()
        if not ch:
            return set()
        keys = set()
        if ch in _CN_CHAR_DIGIT_KEYS:
            keys.add(_CN_CHAR_DIGIT_KEYS[ch])
        if has_pinyin and re.fullmatch(r"[\u4e00-\u9fa5]", ch):
            try:
                for item in pypinyin.pinyin(ch, heteronym=True, style=pypinyin.NORMAL)[0]:
                    keys.update(pinyin_variants(item))
            except Exception:
                pass
        for item in _PINYIN_CHAR_OVERRIDES.get(ch, ()): 
            keys.update(pinyin_variants(item))
        if not keys and re.fullmatch(r"[A-Za-z0-9]", ch):
            keys.add(ch.lower())
        return keys

    @lru_cache(maxsize=4096)
    def chars_phonetic_equal(a, b):
        a = str(a or "").strip()
        b = str(b or "").strip()
        if not a or not b:
            return False
        if a == b:
            return True
        a_keys = char_pinyin_keys(a)
        b_keys = char_pinyin_keys(b)
        return bool(a_keys and b_keys and a_keys.intersection(b_keys))

    @lru_cache(maxsize=4096)
    def phonetic_text_overlap(a, b):
        a_norm = normalize_text(a)
        b_norm = normalize_text(b)
        if not a_norm or not b_norm:
            return False
        if len(a_norm) > len(b_norm):
            a_norm, b_norm = b_norm, a_norm
        if len(a_norm) < 2:
            return False
        for start in range(len(b_norm) - len(a_norm) + 1):
            if all(chars_phonetic_equal(a_ch, b_norm[start + idx]) for idx, a_ch in enumerate(a_norm)):
                return True
        return False

    _CANONICAL_ADDRESS_MARKERS = ("号楼", "单元", "号院", "栋", "幢", "座", "楼", "室", "号", "弄", "里")

    @lru_cache(maxsize=4096)
    def marker_phonetic_equal(fragment, marker):
        fragment = str(fragment or "").strip()
        marker = str(marker or "").strip()
        return bool(
            len(fragment) == len(marker)
            and fragment
            and all(chars_phonetic_equal(a, b) for a, b in zip(fragment, marker))
        )

    @lru_cache(maxsize=4096)
    def normalize_address_marker_tokens(text):
        text = str(text or "").strip()
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
                        marker_phonetic_equal(fragment, marker)
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
    def has_building_or_room(text):
        text = str(text or "").strip()
        text = normalize_address_marker_tokens(text)
        if not text:
            return False
        return bool(re.search(
            r"((?:\d+|[一二三四五六七八九十百零两]+)(?:栋|幢|座|号楼|楼)|\d+单元|\d+室|(?<!\d)\d{3,6}(?!\d))",
            text
        ))

    def extract_named_place_fragment(text):
        text = str(text or "").strip()
        text = normalize_address_marker_tokens(text)
        if not text:
            return ""

        fragment = re.sub(r"(?:\d+|[一二三四五六七八九十百零两]+)(?:栋|幢|座|号楼|楼)", "", text)
        fragment = re.sub(r"\d+单元", "", fragment)
        fragment = re.sub(r"\d+室", "", fragment)
        fragment = re.sub(r"(?<!\d)\d{3,6}(?!\d)", "", fragment)
        fragment = re.sub(r"(\d+号院|\d+号(?!楼|栋|幢|单元|室)|\d+弄|\d+里)", "", fragment)
        return fragment.strip()

    def strip_leading_admin_tokens(text):
        text = str(text or "").strip()
        if not text:
            return ""

        patterns = (
            r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省)",
            r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?市",
            r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗)",
            r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:街道|镇|乡)",
        )

        stripped = text
        changed = True
        while changed and stripped:
            changed = False
            for pattern in patterns:
                match = re.match(pattern, stripped)
                if match:
                    stripped = stripped[match.end():]
                    changed = True
                    break

        return stripped.strip()

    def is_weak_area_fragment(text):
        text = str(text or "").strip()
        if not text:
            return False
        return bool(re.fullmatch(r"(东|西|南|北|中)(区|侧|门)?|[A-Za-z]区|[一二三四五六七八九十0-9]+区", text))

    def has_named_place_anchor(text):
        fragment = strip_leading_admin_tokens(extract_named_place_fragment(text))
        fragment_norm = normalize_text(fragment)
        if len(fragment_norm) < 4:
            return False
        return not is_weak_area_fragment(fragment)

    def is_fragment_input(text):
        t = normalize_text(text)
        if not t:
            return False

        has_detail = bool(re.search(
            r"(小区|花园|公寓|大厦|苑|村|路|大道|巷|胡同|街|栋|幢|座|单元|室|号楼|号院|\d+号|\d+栋|\d+单元|\d+室|\d{3,6})",
            t
        ))

        t_for_region = re.sub(r"(小区|园区|校区|景区|社区|厂区|公寓|大厦|花园|苑)", "", t)

        has_broad_region = bool(re.search(
            r"(?:[\u4e00-\u9fa5]{2,12}(?:省|市|县|旗|镇|乡|街道))|(?:[\u4e00-\u9fa5]{2,12}区(?![路街巷村]))",
            t_for_region
        ))

        return has_detail and not has_broad_region

    def extract_overlap_terms(text):
        text = str(text or "").strip()
        if not text:
            return []

        terms = []

        def add_term(value):
            norm = normalize_text(value)
            if norm and norm not in terms:
                terms.append(norm)

        for pattern in (
            r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省)",
            r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?市",
            r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗)",
            r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:街道|镇|乡)",
            r"[\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:大道|路|巷|胡同|街(?!道))",
            r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:小区|花园|公寓|大厦|苑|村)",
            r"(?:\d+|[一二三四五六七八九十百零两]+)(?:栋|幢|座|号楼|楼)",
            r"\d+单元",
            r"\d+室",
            r"(?<!\d)\d{3,6}(?!\d)",
            r"\d+号院|\d+号(?!楼|栋|幢|单元|室)|\d+弄|\d+里",
        ):
            for match in re.findall(pattern, text):
                add_term(match)

        raw_named_place = extract_named_place_fragment(text)
        stripped_named_place = strip_leading_admin_tokens(raw_named_place)
        for value in (raw_named_place, stripped_named_place, text):
            add_term(value)

        return terms

    def has_address_overlap(a, b):
        a = str(a or "").strip()
        b = str(b or "").strip()
        if not a or not b:
            return False

        an = normalize_text(a)
        bn = normalize_text(b)
        if an and bn and (an == bn or an in bn or bn in an):
            return True
        if phonetic_text_overlap(a, b):
            return True

        a_terms = extract_overlap_terms(a)
        b_terms = extract_overlap_terms(b)
        for a_term in a_terms:
            for b_term in b_terms:
                if a_term == b_term or a_term in b_term or b_term in a_term:
                    return True
                if phonetic_text_overlap(a_term, b_term):
                    return True

        return False

    def has_any_candidate_overlap(text, candidates):
        text = str(text or "").strip()
        if not text:
            return False

        for candidate in candidates or []:
            if has_address_overlap(text, candidate):
                return True

        return False



    def _has_strong_address_structure(text):
        text = str(text or "").strip()
        if not text:
            return False
        text = normalize_address_marker_tokens(text)
        return bool(re.search(
            r"(\u7701|\u5e02|\u533a|\u53bf|\u65d7|\u9547|\u4e61|\u8857\u9053|\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857|\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751|\u680b|\u5e62|\u5ea7|\u5355\u5143|\u5ba4|\u53f7\u697c|\u53f7\u9662|\d+\u53f7|\d{3,6})",
            text
        ))

    def _has_place_like_signal(text):
        text = str(text or "").strip()
        if not text:
            return False
        return bool(
            has_named_place_anchor(text)
            or re.search(
                r"(\u7701|\u5e02|\u533a|\u53bf|\u65d7|\u9547|\u4e61|\u8857\u9053|\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857|\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751)",
                text
            )
        )

    def _has_candidate_overlap_span_signal(text):
        return _has_strong_address_structure(text) or _has_place_like_signal(text) or has_named_place_anchor(text)

    def is_room_number_fragment(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        if not text:
            return False
        if text.endswith("室"):
            text = text[:-1]
        number_text = normalize_address_number_compare_tokens(text)
        return bool(re.fullmatch(r"\d{3,6}", number_text))

    @lru_cache(maxsize=8192)
    def _phonetic_substring_match(fragment, candidate):
        fragment_norm = normalize_text(fragment)
        candidate_norm = normalize_text(candidate)
        if not fragment_norm or not candidate_norm or len(fragment_norm) > len(candidate_norm):
            return False
        for start in range(len(candidate_norm) - len(fragment_norm) + 1):
            candidate_slice = candidate_norm[start:start + len(fragment_norm)]
            if all(chars_phonetic_equal(a, b) for a, b in zip(fragment_norm, candidate_slice)):
                return True
        return False

    def extract_by_candidate_overlap(raw_text, candidates):
        compact_raw = re.sub(r"\s+", "", str(raw_text or "").strip())
        if not compact_raw or not isinstance(candidates, list) or not candidates:
            return ""

        raw_len = len(compact_raw)
        best_span = ""
        best_score = -1

        for candidate in candidates:
            candidate_norm = normalize_text(candidate)
            if not candidate_norm:
                continue

            matched_spans = []
            for start in range(raw_len):
                for end in range(start + 2, raw_len + 1):
                    span = compact_raw[start:end]
                    span_norm = normalize_text(span)
                    if len(span_norm) < 2:
                        continue
                    has_signal = _has_candidate_overlap_span_signal(span) or is_room_number_fragment(span)
                    if len(span_norm) < 4 and not has_signal:
                        continue
                    if span_norm in candidate_norm or _phonetic_substring_match(span, candidate):
                        matched_spans.append((start, end, len(span_norm), has_signal))

            if not matched_spans:
                continue

            # Keep only spans that add coverage, preserving user-spoken pieces
            # even when candidates contain unspoken text between them.
            matched_spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
            selected = []
            covered_until = -1
            for item in matched_spans:
                start, end, _length, _has_signal = item
                if end <= covered_until:
                    continue
                selected.append(item)
                covered_until = max(covered_until, end)

            if not selected:
                continue

            window_start = min(item[0] for item in selected)
            window_end = max(item[1] for item in selected)
            window = compact_raw[window_start:window_end]
            total_matched_len = sum(item[2] for item in selected)
            has_any_signal = any(item[3] for item in selected)
            if total_matched_len < 4 and not has_any_signal:
                continue

            score = total_matched_len * 10 + len(normalize_text(window)) + (20 if has_any_signal else 0) - window_start
            if score > best_score:
                best_score = score
                best_span = window

        return best_span.strip()

    def _candidate_supported_user_fragment(user_text, candidates):
        user_text = normalize_address_marker_tokens(str(user_text or "").strip())
        if not user_text or not isinstance(candidates, list) or not candidates:
            return ""

        raw_len = len(user_text)
        best = None
        for candidate in candidates:
            candidate = normalize_address_marker_tokens(str(candidate or "").strip())
            candidate_norm = normalize_text(candidate)
            if not candidate_norm:
                continue

            for start in range(raw_len):
                for end in range(start + 2, raw_len + 1):
                    span = user_text[start:end]
                    span_norm = normalize_text(span)
                    if len(span_norm) < 2:
                        continue
                    supported = span_norm in candidate_norm or _phonetic_substring_match(span, candidate)
                    if not supported:
                        continue

                    has_signal = _has_candidate_overlap_span_signal(span) or is_room_number_fragment(span) or has_named_place_anchor(span)
                    if len(span_norm) < 4 and not has_signal:
                        continue

                    unsupported_prefix_norm = normalize_text(user_text[:start])
                    unsupported_suffix_norm = normalize_text(user_text[end:])
                    score = (
                        len(span_norm) * 100
                        + (30 if has_signal else 0)
                        - len(unsupported_prefix_norm) * 3
                        - len(unsupported_suffix_norm) * 2
                    )
                    item = (score, len(span_norm), start, end, span)
                    if best is None or item > best:
                        best = item

        return best[4].strip() if best else ""

    def extract_by_address_structure(raw_text):
        compact_raw = re.sub(r"\s+", "", str(raw_text or "").strip())
        if not compact_raw:
            return ""
        for start in range(len(compact_raw)):
            suffix = compact_raw[start:]
            if not (_has_strong_address_structure(suffix) or _has_place_like_signal(suffix)):
                continue
            if start == 0 or not re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9]", compact_raw[start - 1]):
                return suffix.strip()
        return compact_raw if _has_strong_address_structure(compact_raw) else ""

    def expand_candidate_span_to_user_address_window(raw_text, candidate_span):
        compact_raw = re.sub(r"\s+", "", str(raw_text or "").strip())
        candidate_span = re.sub(r"\s+", "", str(candidate_span or "").strip())
        if not compact_raw or not candidate_span:
            return candidate_span

        start = compact_raw.find(candidate_span)
        if start < 0:
            return candidate_span

        suffix = compact_raw[start:]
        structured_span = extract_by_address_structure(suffix)
        if (
            structured_span
            and normalize_text(candidate_span)
            and normalize_text(candidate_span) in normalize_text(structured_span)
        ):
            return structured_span

        return candidate_span

    def extract_spoken_address_parts(raw_text, candidates):
        compact_raw = re.sub(r"\s+", "", str(raw_text or "").strip())
        if not compact_raw:
            return "", ""

        cleaned_raw = extract_effective_input(compact_raw)

        candidate_noise_cleaned_raw = clean_candidate_supported_noise(cleaned_raw, candidates)

        structured_span = extract_by_address_structure(candidate_noise_cleaned_raw)
        if structured_span:
            return structured_span, candidate_noise_cleaned_raw

        candidate_span = extract_by_candidate_overlap(candidate_noise_cleaned_raw, candidates)
        if candidate_span:
            return (
                expand_candidate_span_to_user_address_window(candidate_noise_cleaned_raw, candidate_span),
                candidate_noise_cleaned_raw,
            )

        return candidate_noise_cleaned_raw, candidate_noise_cleaned_raw

    def extract_spoken_address(raw_text, candidates):
        return extract_spoken_address_parts(raw_text, candidates)[0]



    def _strip_leading_weak_area_fragment(text):
        text = str(text or "").strip()
        if not text:
            return ""
        for pattern in (
            r"^(\u4e1c|\u897f|\u5357|\u5317|\u4e2d)(\u533a|\u4fa7|\u95e8)?",
            r"^[A-Za-z]\u533a",
            r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u96f60-9]+\u533a",
        ):
            match = re.match(pattern, text)
            if match:
                return text[match.end():].strip()
        return text

    def _extract_building_name(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        if not text:
            return ""
        match = re.search(r"((?:\d+|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u96f6\u4e24]+|[A-Za-z]\d*)(?:\u680b|\u5e62|\u5ea7|\u53f7\u697c|\u697c))", text)
        return match.group(1) if match else ""

    def _extract_unit_name(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        match = re.search(r"(\d+\u5355\u5143)", text)
        return match.group(1) if match else ""

    def _extract_room_name(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        if not text:
            return ""
        match = re.search(r"(\d+\u5ba4)", text)
        if match:
            return match.group(1)
        text = re.sub(r"(?:\d+|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u96f6\u4e24]+|[A-Za-z]\d*)(?:\u680b|\u5e62|\u5ea7|\u53f7\u697c|\u697c)", "", text)
        text = re.sub(r"\d+\u5355\u5143", "", text)
        nums = re.findall(r"(?<!\d)(\d{3,6})(?!\d)", text)
        return nums[-1] if nums else ""

    def _extract_house_name(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        match = re.search(r"(\d+\u53f7\u9662|\d+\u53f7(?!\u697c|\u680b|\u5e62|\u5355\u5143|\u5ba4)|\d+\u5f04|\d+\u91cc)", text)
        return match.group(1) if match else ""

    def _normalized_detail_value(value):
        return normalize_text(value)

    def _has_precise_detail_conflict(user_text, candidate_text):
        for extractor in (_extract_building_name, _extract_unit_name, _extract_room_name, _extract_house_name):
            user_value = extractor(user_text)
            candidate_value = extractor(candidate_text)
            if (
                user_value
                and candidate_value
                and _normalized_detail_value(user_value) != _normalized_detail_value(candidate_value)
            ):
                return True
        return False

    def _unique_candidate_detail_values(candidates, extractor):
        values = []
        seen = set()
        for candidate in candidates:
            value = extractor(candidate)
            norm = _normalized_detail_value(value)
            if norm and norm not in seen:
                seen.add(norm)
                values.append(value)
        return values

    @lru_cache(maxsize=8192)
    def _find_phonetic_span_match(fragment, candidate):
        fragment_norm = normalize_text(fragment)
        candidate_norm = normalize_text(candidate)
        if not fragment_norm or not candidate_norm or len(fragment_norm) > len(candidate_norm):
            return "", -1, -1
        for start in range(len(candidate_norm) - len(fragment_norm) + 1):
            span = candidate_norm[start:start + len(fragment_norm)]
            if all(chars_phonetic_equal(a, b) for a, b in zip(fragment_norm, span)):
                return span, start, start + len(fragment_norm)
        return "", -1, -1

    def _find_phonetic_span(fragment, candidate):
        span, _start, _end = _find_phonetic_span_match(fragment, candidate)
        return span

    def _replace_first_phonetic(text, old, new):
        text = normalize_address_marker_tokens(str(text or "").strip())
        old = normalize_address_marker_tokens(str(old or "").strip())
        new = normalize_address_marker_tokens(str(new or "").strip())
        if not text or not old or not new:
            return text
        if old in text:
            return text.replace(old, new, 1)
        if len(old) > len(text):
            return text
        for start in range(len(text) - len(old) + 1):
            segment = text[start:start + len(old)]
            if all(chars_phonetic_equal(a, b) for a, b in zip(old, segment)):
                return f"{text[:start]}{new}{text[start + len(old):]}"
        return text

    def _add_match_term(terms, value, min_len=2):
        value = normalize_address_marker_tokens(str(value or "").strip())
        norm = normalize_text(value)
        if len(norm) >= min_len and norm not in {item[1] for item in terms}:
            terms.append((value, norm))

    def _is_detail_match_term(value):
        value_norm = normalize_text(value)
        if not value_norm:
            return False
        for extractor in (_extract_building_name, _extract_unit_name, _extract_room_name, _extract_house_name):
            extracted = extractor(value)
            if extracted and normalize_text(extracted) == value_norm:
                return True
        value = normalize_address_marker_tokens(str(value or "").strip())
        cn_num = r"[一二两三四五六七八九十百千万零〇]+"
        num = fr"(?:\d+|{cn_num}|[A-Za-z]\d*)"
        stripped = value
        stripped = re.sub(fr"{num}(?:栋|幢|座|号楼|楼)", "", stripped)
        stripped = re.sub(fr"(?:\d+|{cn_num})单元", "", stripped)
        stripped = re.sub(fr"(?:\d+|{cn_num})室", "", stripped)
        stripped = re.sub(r"\d+号院|\d+号(?!楼|栋|幢|单元|室)|\d+弄|\d+里", "", stripped)
        stripped = re.sub(fr"(?<![A-Za-z0-9一二两三四五六七八九十百千万零〇])(?:\d{{3,6}}|{cn_num})(?![A-Za-z0-9一二两三四五六七八九十百千万零〇])", "", stripped)
        return value != stripped and not normalize_text(stripped)

    def _extract_candidate_backed_terms(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        terms = []
        if not text:
            return terms

        has_detail = has_building_or_room(text) or bool(_extract_house_name(text))
        if not has_detail:
            for pattern in (
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u81ea\u6cbb\u533a|\u7279\u522b\u884c\u653f\u533a|\u7701)",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?\u5e02",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u533a|\u53bf|\u65d7)",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:\u8857\u9053|\u9547|\u4e61)",
                r"[\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:\u5927\u9053|\u8def|\u5df7|\u80e1\u540c|\u8857(?!\u9053))",
                r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751)",
            ):
                for match in re.findall(pattern, text):
                    _add_match_term(terms, match)

        for value in (
            _extract_building_name(text),
            _extract_unit_name(text),
            _extract_room_name(text),
            _extract_house_name(text),
        ):
            _add_match_term(terms, value)

        named = strip_leading_admin_tokens(extract_named_place_fragment(text))
        if named:
            if is_weak_area_fragment(named):
                _add_match_term(terms, named)
                return terms
            weak_match = re.match(r"(\u4e1c|\u897f|\u5357|\u5317|\u4e2d)(\u533a|\u4fa7|\u95e8)?|[A-Za-z]\u533a|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u96f60-9]+\u533a", named)
            if weak_match and weak_match.end() < len(named):
                _add_match_term(terms, weak_match.group(0))
                named = named[weak_match.end():].strip()
            weak_tail = re.search(r"(\u4e1c|\u897f|\u5357|\u5317|\u4e2d)(\u533a|\u4fa7|\u95e8)?$|[A-Za-z]\u533a$|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u96f60-9]+\u533a$", named)
            if weak_tail and weak_tail.start() > 0:
                _add_match_term(terms, weak_tail.group(0))
                named = named[:weak_tail.start()].strip()
            if named and not is_weak_area_fragment(named):
                marker_min_len = 2 if re.search(r"(\u5c0f\u533a|\u82b1\u56ed|\u516c\u5bd3|\u5927\u53a6|\u82d1|\u6751|\u9547|\u4e61|\u8857\u9053|\u8def|\u5927\u9053|\u5df7|\u80e1\u540c|\u8857(?!\u9053))", named) else 4
                _add_match_term(terms, named, marker_min_len)

        if not terms:
            _add_match_term(terms, text)

        return terms

    _RESIDENTIAL_PLACE_SUFFIXES = ("小区", "花园", "公寓", "家园", "苑", "府", "村")

    def _extract_residential_place_terms(text):
        text = normalize_address_marker_tokens(str(text or "").strip())
        raw_named = extract_named_place_fragment(text)
        stripped_named = strip_leading_admin_tokens(raw_named)
        source_texts = [value for value in (raw_named, stripped_named) if value]
        if not source_texts:
            return []

        suffix_pattern = "|".join(re.escape(suffix) for suffix in _RESIDENTIAL_PLACE_SUFFIXES)
        terms = []
        seen = set()
        for source_text in source_texts:
            for match in re.findall(fr"[\u4e00-\u9fa5A-Za-z0-9]{{2,20}}(?:{suffix_pattern})", source_text):
                norm = normalize_text(match)
                if norm and norm not in seen:
                    seen.add(norm)
                    terms.append(match)
        return terms

    def _candidate_supports_residential_place_term(term, candidate):
        term = normalize_address_marker_tokens(str(term or "").strip())
        candidate = normalize_address_marker_tokens(str(candidate or "").strip())
        if not term or not candidate:
            return False

        term_norm = normalize_text(term)
        candidate_norm = normalize_text(candidate)
        if term_norm and candidate_norm and term_norm in candidate_norm:
            return True

        suffix = next((item for item in _RESIDENTIAL_PLACE_SUFFIXES if term.endswith(item)), "")
        if not suffix or len(term) > len(candidate):
            return False

        for start in range(len(candidate) - len(term) + 1):
            span = candidate[start:start + len(term)]
            if not span.endswith(suffix):
                continue
            if all(chars_phonetic_equal(left, right) for left, right in zip(term, span)):
                return True
        return False

    def _has_unsupported_residential_place_anchor(current_text, candidates):
        terms = _extract_residential_place_terms(current_text)
        if not terms:
            return False

        candidates = [str(candidate or "").strip() for candidate in candidates or [] if str(candidate or "").strip()]
        if not candidates:
            return True

        return not any(
            all(_candidate_supports_residential_place_term(term, candidate) for term in terms)
            for candidate in candidates
        )

    def _combine_address_parts(prev_text, curr_text):
        prev_text = normalize_address_marker_tokens(str(prev_text or "").strip())
        curr_text = normalize_address_marker_tokens(str(curr_text or "").strip())
        if not curr_text:
            return ""
        if not prev_text:
            return curr_text
        prev_norm = normalize_text(prev_text)
        curr_norm = normalize_text(curr_text)
        if curr_norm == prev_norm or (curr_norm and curr_norm in prev_norm):
            return prev_text
        if prev_norm and prev_norm in curr_norm:
            return curr_text
        overlap_len = _suffix_prefix_overlap_len(prev_norm, curr_norm)
        if overlap_len:
            return f"{prev_text}{curr_text[overlap_len:]}"
        return f"{prev_text}{curr_text}"

    def _suffix_prefix_overlap_len(prev_norm, curr_norm):
        max_overlap = min(len(prev_norm), len(curr_norm))
        for overlap_len in range(max_overlap, 1, -1):
            if prev_norm.endswith(curr_norm[:overlap_len]):
                return overlap_len
        return 0

    def _find_candidate_backed_merge(prev_text, curr_text, candidates):
        prev_text = str(prev_text or "").strip()
        curr_text = str(curr_text or "").strip()
        if not prev_text or not curr_text or not isinstance(candidates, list) or not candidates:
            return ""
        if is_weak_area_fragment(prev_text) and has_named_place_anchor(curr_text):
            return ""

        prev_terms = _extract_candidate_backed_terms(prev_text)
        curr_terms = _extract_candidate_backed_terms(curr_text)
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

        combined = _combine_address_parts(prev_text, curr_text)
        results = []
        for candidate in candidates:
            candidate = str(candidate or "").strip()
            if not candidate:
                continue
            spans = []
            for item in required_terms:
                span, start, end = _find_phonetic_span_match(item["value"], candidate)
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
            for value, span, _start, _end, _sources in sorted(spans, key=lambda item: len(normalize_text(item[0])), reverse=True):
                if not _is_detail_match_term(value):
                    corrected = _replace_first_phonetic(corrected, value, span)
            results.append(corrected)

        unique_results = []
        seen_norms = set()
        for result in results:
            norm = normalize_text(result)
            if norm and norm not in seen_norms:
                seen_norms.add(norm)
                unique_results.append(result)
        return unique_results[0] if len(unique_results) == 1 else ""

    def _candidate_supports_user_scope(user_scope, candidate):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        candidate = normalize_address_marker_tokens(str(candidate or "").strip())
        if not user_scope or not candidate:
            return False
        if _has_precise_detail_conflict(user_scope, candidate):
            return False

        user_norm = normalize_text(user_scope)
        candidate_norm = normalize_text(candidate)
        if user_norm and candidate_norm and user_norm in candidate_norm:
            return True

        terms = _extract_candidate_backed_terms(user_scope)
        if not terms:
            return has_address_overlap(user_scope, candidate)

        for value, norm in terms:
            if not norm:
                continue
            if norm in candidate_norm:
                continue
            if _find_phonetic_span(value, candidate):
                continue
            return False
        return True

    def _find_ordered_candidate_term_window(terms, candidate):
        candidate_norm = normalize_text(candidate)
        if not terms or not candidate_norm:
            return None

        spans = []
        search_start = 0
        for value, norm in terms:
            if not norm:
                continue
            found = None
            if len(norm) > len(candidate_norm):
                return None
            for start in range(search_start, len(candidate_norm) - len(norm) + 1):
                candidate_span = candidate_norm[start:start + len(norm)]
                if all(chars_phonetic_equal(a, b) for a, b in zip(norm, candidate_span)):
                    found = (value, candidate_span, start, start + len(norm))
                    break
            if not found:
                return None
            spans.append(found)
            search_start = found[3]

        if not spans:
            return None
        return spans[0][2], spans[-1][3], spans

    def _extend_detail_window_end(candidate_norm, window_end):
        while window_end < len(candidate_norm) and candidate_norm[window_end] in "号室":
            window_end += 1
        return window_end

    def _build_ordered_candidate_anchor_span_hint(user_scope, candidates):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        if not user_scope or not isinstance(candidates, list) or not candidates:
            return ""

        terms = _extract_candidate_backed_terms(user_scope)
        if len(terms) < 2:
            return ""

        matched_windows = []
        for idx, candidate in enumerate(candidates):
            candidate_text = normalize_address_marker_tokens(str(candidate or "").strip())
            candidate_norm = normalize_text(candidate_text)
            window = _find_ordered_candidate_term_window(terms, candidate_text)
            if not window:
                continue
            window_start, window_end, spans = window
            window_end = _extend_detail_window_end(candidate_norm, window_end)
            if window_start < 0 or window_end <= window_start:
                continue
            standard_fragment = candidate_norm[window_start:window_end]
            matched_windows.append((idx, standard_fragment, spans))

        if len(matched_windows) != 1:
            return ""

        matched_idx, standard_fragment, spans = matched_windows[0]
        anchor_text = "、".join(dict.fromkeys(value for value, _span, _start, _end in spans))
        return (
            f"当前 clean_user_input 的关键地址锚点“{anchor_text}”按顺序落在第 {matched_idx} 条候选中；"
            f"matched_address_fragment 可使用候选从第一个锚点到最后一个锚点之间的连续标准片段“{standard_fragment}”，"
            "允许补全锚点之间省略的同一层级或 L7 结构成分（如单元/号/室），"
            "但禁止补入该窗口外的省/市/区/街道/路名/小区/主体等候选独有内容。"
        )

    def _build_no_candidate_anchor_hint(user_scope, candidates):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        if not user_scope or not isinstance(candidates, list) or not candidates:
            return ""

        terms = _extract_candidate_backed_terms(user_scope)
        for candidate in candidates:
            candidate_text = str(candidate or "").strip()
            if _candidate_supports_user_scope(user_scope, candidate_text):
                return ""
            if terms and _find_ordered_candidate_term_window(terms, candidate_text):
                return ""

        return (
            f"当前 clean_user_input“{user_scope}”没有任何可锚定到 candidates_info 的地址成分；"
            "不能把它写入 matched_address_fragment，也不能仅凭拼音把不同音节纠正为候选地址。"
            "若没有上一轮已被候选支持的片段，matched_address_fragment 必须为 \"\"。"
        )

    def _build_ambiguous_candidate_hint(user_scope, candidates):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        if not user_scope or not isinstance(candidates, list) or len(candidates) < 2:
            return ""

        matched_candidates = [
            str(candidate)
            for candidate in candidates
            if _candidate_supports_user_scope(user_scope, candidate)
        ]
        if len(matched_candidates) < 2:
            return ""

        user_building = _extract_building_name(user_scope)
        user_unit = _extract_unit_name(user_scope)
        user_room = _extract_room_name(user_scope)
        user_house = _extract_house_name(user_scope)

        missing_parts = []
        differing_values = []
        candidate_buildings = _unique_candidate_detail_values(matched_candidates, _extract_building_name)
        candidate_units = _unique_candidate_detail_values(matched_candidates, _extract_unit_name)
        candidate_rooms = _unique_candidate_detail_values(matched_candidates, _extract_room_name)
        candidate_houses = _unique_candidate_detail_values(matched_candidates, _extract_house_name)

        if not user_building and len(candidate_buildings) > 1:
            missing_parts.append("楼栋号")
            differing_values.extend(candidate_buildings)
        if not user_unit and len(candidate_units) > 1:
            missing_parts.append("单元号")
            differing_values.extend(candidate_units)
        if not user_room and len(candidate_rooms) > 1:
            missing_parts.append("门牌号/房间号")
            differing_values.extend(candidate_rooms)
        if not user_house and len(candidate_houses) > 1:
            missing_parts.append("门牌号")
            differing_values.extend(candidate_houses)

        if not missing_parts:
            return ""

        differing_text = "、".join(str(value) for value in differing_values if value)
        missing_text = "、".join(dict.fromkeys(missing_parts))
        detail_text = f"（候选差异值：{differing_text}）" if differing_text else ""
        return (
            f"当前用户已说范围“{user_scope}”仍匹配 {len(matched_candidates)} 条候选，"
            f"候选仍存在用户未提供的{missing_text}差异{detail_text}；"
            f"禁止补入任一候选中用户未说出的楼栋、单元、门牌或房间号，禁止输出 match_count=1。"
            f"本轮必须输出 matched_index=-1, match_count=0, is_completed=false；"
            "reason 必须根据 matched_address_fragment 覆盖候选最后两级的情况填写："
            "只含倒数第二级输出 two，只含倒数第一级输出 one，两级都含输出 true，其他输出空字符串；"
            "只覆盖 L5/前置路址范围时 reason 必须为空字符串；"
            f"matched_address_fragment 只能包含用户已说范围对应的候选支持片段，不能包含未说出的差异字段。"
        )

    def _build_unique_candidate_hint(user_scope, candidates):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        if not user_scope or not isinstance(candidates, list) or len(candidates) < 2:
            return ""

        matched_candidates = [
            (idx, str(candidate))
            for idx, candidate in enumerate(candidates)
            if _candidate_supports_user_scope(user_scope, candidate)
        ]
        if len(matched_candidates) != 1:
            return ""

        matched_idx, matched_candidate = matched_candidates[0]
        return (
            f"合并后的用户已说范围“{user_scope}”只匹配第 {matched_idx} 条候选“{matched_candidate}”；"
            "这只表示候选范围唯一，仍必须按候选地址最后两个有效层级是否都被用户已说范围命中来决定 match_count。"
            f"若未命中最后两级，仍输出 matched_index=-1, match_count=0, is_completed=false；"
            "L7 内部楼栋号、单元号、门牌号、房号无论命中多少项，都只能算命中最后一级，不能替代倒数第二级；"
            "reason 必须根据 matched_address_fragment 覆盖候选最后两级的情况填写："
            "只含倒数第二级输出 two，只含倒数第一级输出 one，两级都含输出 true，其他输出空字符串；"
            "只覆盖 L5/前置路址范围时 reason 必须为空字符串；"
            f"matched_address_fragment 必须保留该合并范围对应的候选支持片段，不能丢失为仅 clean_user_input。"
        )

    def _extract_place_anchor_for_last_level_hint(text):
        fragment = strip_leading_admin_tokens(extract_named_place_fragment(text))
        fragment = normalize_address_marker_tokens(fragment)
        fragment_norm = normalize_text(fragment)
        if len(fragment_norm) < 4 or is_weak_area_fragment(fragment):
            return ""
        return fragment

    def _extract_detail_numbers(text):
        text = normalize_address_number_compare_tokens(
            normalize_address_marker_tokens(str(text or "").strip())
        )
        return re.findall(r"\d+", text)

    def _first_detail_number(text):
        numbers = _extract_detail_numbers(text)
        return numbers[0] if numbers else ""

    def _candidate_level_hint_evidence(user_scope, candidate, place_anchor):
        candidate = normalize_address_marker_tokens(str(candidate or "").strip())
        if not candidate:
            return None

        place_start = candidate.find(place_anchor)
        if place_start < 0:
            return None

        user_numbers = set(_extract_detail_numbers(user_scope))
        if not user_numbers:
            return None

        building = _extract_building_name(candidate)
        unit = _extract_unit_name(candidate)
        room = _extract_room_name(candidate)
        house = _extract_house_name(candidate)

        required_parts = []
        for part in (building, unit, house, room):
            if not part:
                continue
            number = _first_detail_number(part)
            if not number or number not in user_numbers:
                return None
            required_parts.append(part)

        if not required_parts:
            return None

        has_terminal_anchor = bool(
            (room and _first_detail_number(room) in user_numbers)
            or (house and _first_detail_number(house) in user_numbers)
        )
        if not has_terminal_anchor:
            return None

        place_end = place_start + len(place_anchor)
        positions = []
        for part in required_parts:
            part_start = candidate.find(part, place_end)
            if part_start < 0:
                continue
            positions.append((part_start, part_start + len(part)))

        standard_fragment = ""
        if positions:
            detail_start = min(start for start, _end in positions)
            detail_end = max(end for _start, end in positions)
            gap = candidate[place_end:detail_start]
            if not normalize_text(gap):
                standard_fragment = candidate[place_start:detail_end]

        return {
            "candidate": candidate,
            "standard_fragment": standard_fragment,
            "required_parts": required_parts,
        }

    def _build_current_unique_last_level_hint(user_scope, candidates):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        if not user_scope or not isinstance(candidates, list) or not candidates:
            return ""
        if not has_building_or_room(user_scope):
            return ""

        place_anchor = _extract_place_anchor_for_last_level_hint(user_scope)
        if not place_anchor:
            return ""

        matched_candidates = []
        for idx, candidate in enumerate(candidates):
            evidence = _candidate_level_hint_evidence(user_scope, candidate, place_anchor)
            if evidence:
                matched_candidates.append((idx, evidence))

        if len(matched_candidates) != 1:
            return ""

        matched_idx, evidence = matched_candidates[0]
        detail_text = "、".join(dict.fromkeys(evidence["required_parts"]))
        standard_fragment = evidence["standard_fragment"]
        standard_fragment_hint = (
            f"候选中该用户已说范围的标准片段可写为“{standard_fragment}”；"
            if standard_fragment
            else ""
        )

        return (
            f"当前 clean_user_input 已同时说出候选第 {matched_idx} 条支持的 L6 地点主体"
            f"“{place_anchor}”和 L7 关键锚点“{detail_text}”；"
            f"{standard_fragment_hint}"
            "这不是只命中 L7。若 matched_address_fragment 同时包含该 L6 主体和这些 L7 锚点，"
            f"应判定覆盖候选最后两级 L6+L7，输出 reason=\"true\"、matched_index={matched_idx}、match_count=1；"
            "不要把包含 L6 主体的片段误判为 reason=\"one\"。"
            "L7 内“单元/栋/幢/楼/座/号”等弱结构词错位或多余，"
            "只要候选楼栋/单元/房号关键数字锚点已覆盖，就不能把 reason 从 true 降为 one。"
        )

    def _char_pinyin_label(ch):
        ch = str(ch or "").strip()
        if not ch:
            return ""
        values = []
        if has_pinyin and re.fullmatch(r"[\u4e00-\u9fa5]", ch):
            try:
                values = pypinyin.pinyin(ch, heteronym=True, style=pypinyin.NORMAL)[0]
            except Exception:
                values = []
        if not values:
            values = list(_PINYIN_CHAR_OVERRIDES.get(ch, ()))
        if not values and re.fullmatch(r"[A-Za-z0-9]", ch):
            values = [ch.lower()]
        values = [str(value).lower().replace("\u00fc", "v").replace("u:", "v") for value in values if value]
        return "/".join(dict.fromkeys(values))

    def _build_phonetic_mismatch_hint(user_scope, candidates):
        user_scope = normalize_address_marker_tokens(str(user_scope or "").strip())
        if not user_scope or not isinstance(candidates, list) or not candidates:
            return ""

        user_compact = re.sub(r"\s+", "", user_scope)
        user_norm = normalize_text(user_compact)
        if len(user_norm) < 2:
            return ""

        for candidate in candidates:
            candidate_compact = re.sub(r"\s+", "", normalize_address_marker_tokens(str(candidate or "").strip()))
            if len(candidate_compact) < len(user_compact):
                continue

            for start in range(len(candidate_compact) - len(user_compact) + 1):
                candidate_span = candidate_compact[start:start + len(user_compact)]
                exact_count = 0
                mismatch_pairs = []
                for user_ch, candidate_ch in zip(user_compact, candidate_span):
                    if user_ch == candidate_ch:
                        exact_count += 1
                        continue
                    if chars_phonetic_equal(user_ch, candidate_ch):
                        continue
                    mismatch_pairs.append((user_ch, candidate_ch))

                if not mismatch_pairs or exact_count < max(1, len(user_compact) - 1):
                    continue

                mismatch_text = "、".join(
                    f"{user_ch}({_char_pinyin_label(user_ch) or '无拼音'})≠"
                    f"{candidate_ch}({_char_pinyin_label(candidate_ch) or '无拼音'})"
                    for user_ch, candidate_ch in mismatch_pairs[:3]
                )
                return (
                    f"用户片段“{user_compact}”与候选片段“{candidate_span}”存在拼音不等价字符："
                    f"{mismatch_text}；禁止将这类不同音节内容按拼音纠错，"
                    "也不能据此把用户片段纠正为该候选片段或补入候选未说出的地址层级；"
                    "但如果用户片段与其他候选精确一致，仍应按精确匹配结果判断唯一匹配。"
                )

        return ""

    def merge_with_previous_address(prev_text, curr_text):
        prev_text = str(prev_text or "").strip()
        curr_text = str(curr_text or "").strip()

        if not curr_text:
            return ""
        if not prev_text:
            return normalize_address_marker_tokens(curr_text)

        candidate_backed_merge = _find_candidate_backed_merge(prev_text, curr_text, kd_records)
        if candidate_backed_merge:
            return candidate_backed_merge

        prev_text = normalize_address_marker_tokens(prev_text)
        curr_text = normalize_address_marker_tokens(curr_text)
        prev_norm = normalize_text(prev_text)
        curr_norm = normalize_text(curr_text)

        if curr_norm == prev_norm:
            return prev_text

        curr_is_specific_street_under_subdistrict = bool(
            curr_text.endswith("街")
            and not curr_text.endswith("街道")
            and f"{curr_text}道" in prev_text
        )
        if curr_norm and curr_norm in prev_norm and not curr_is_specific_street_under_subdistrict:
            return prev_text

        if prev_norm and prev_norm in curr_norm:
            return curr_text

        if _suffix_prefix_overlap_len(prev_norm, curr_norm):
            return _combine_address_parts(prev_text, curr_text)

        if kd_records and (has_any_candidate_overlap(prev_text, kd_records) or has_any_candidate_overlap(curr_text, kd_records)):
            return curr_text

        if is_fragment_input(curr_text):
            if has_any_candidate_overlap(curr_text, kd_records):
                return _combine_address_parts(prev_text, curr_text)
            return curr_text

        if (
            has_named_place_anchor(curr_text)
            and has_building_or_room(prev_text)
            and has_any_candidate_overlap(curr_text, kd_records)
        ):
            return _combine_address_parts(prev_text, curr_text)

        return curr_text

    kd_records = args.get("addList") or args.get("kdRecords") or []
    if not isinstance(kd_records, list):
        kd_records = []

    raw_clean_input = clean_prefix(user_input)
    clean_input, candidate_noise_clean_input = extract_spoken_address_parts(user_input, kd_records)
    last_unmatched_address = strip_embedded_reason_field(strip_non_merge_history(last_unmatched_address_raw))
    last_unmatched_fragment = strip_embedded_reason_field(strip_non_merge_history(last_unmatched_fragment_raw))
    llm_last_unmatched_address = last_unmatched_fragment or last_unmatched_address
    merge_base_address = last_unmatched_address or last_unmatched_fragment
    can_merge_with_previous = bool(merge_base_address) and not is_non_merge_history(last_unmatched_address_raw)
    candidate_merge_base_address = last_unmatched_fragment or merge_base_address

    effective_merged_input = merge_with_previous_address(merge_base_address if can_merge_with_previous else "", clean_input)
    possible_merged_input = merge_with_previous_address(candidate_merge_base_address if can_merge_with_previous else "", clean_input)

    candidate_backed_effective_input = (
        _find_candidate_backed_merge(candidate_merge_base_address, clean_input, kd_records)
        if can_merge_with_previous and clean_input
        else ""
    )
    if candidate_backed_effective_input:
        possible_merged_input = candidate_backed_effective_input

    is_possible_supplement_fragment = (
        can_merge_with_previous
        and normalize_text(possible_merged_input) != normalize_text(clean_input)
    )

    is_candidate_noise_cleaning = bool(
        clean_input
        and raw_clean_input
        and normalize_text(candidate_noise_clean_input) == normalize_text(clean_input)
        and normalize_text(candidate_noise_clean_input) != normalize_text(raw_clean_input)
    )
    is_address_correction = bool(clean_input) and clean_input != raw_clean_input and not is_candidate_noise_cleaning
    prompt_state = "matching" if state == "completed" and is_address_correction else state

    context_parts = [f"[Context] state={prompt_state}"]
    try:
        matched_index_int = int(matched_index)
    except (ValueError, TypeError):
        matched_index_int = -1

    if matched_index_int >= 0 and prompt_state != "matching":
        context_parts.append(f"matched_index={matched_index_int}")

    if clean_input:
        context_parts.append(f"clean_user_input={clean_input}")

    if llm_last_unmatched_address:
        context_parts.append(f"last_unmatched_address={llm_last_unmatched_address}")
    if last_unmatched_fragment:
        context_parts.append(f"last_matched_address_fragment={last_unmatched_fragment}")
    if is_possible_supplement_fragment and possible_merged_input:
        context_parts.append(f"candidate_combined_user_scope_if_supplement={possible_merged_input}")

    if llm_last_unmatched_address:
        if has_pinyin:
            prev_pys = pypinyin.pinyin(llm_last_unmatched_address, heteronym=False, style=pypinyin.NORMAL)
            prev_py_str = " ".join([p[0] for p in prev_pys]) if prev_pys else ""
            if prev_py_str:
                context_parts.append(f"last_unmatched_pinyin={prev_py_str}")

    if similar_no_match_count > 0:
        context_parts.append(f"similar_no_match_count={similar_no_match_count}")

    def get_base_community(address):
        match = re.split(r"([A-Za-z\d\-]*\d+[#号栋单元层室]|第?\d+[#号栋单元层室])", address)
        if len(match) > 1:
            base = match[0].strip()
            base = re.sub(r"[A-Za-z\-]+$", "", base).strip()
            return base if base else address
        return address

    raw_clean_recs = []
    bases = []
    for record in kd_records:
        record_str = str(record)
        clean_rec = clean_prefix(record_str)
        raw_clean_recs.append((record_str, clean_rec))
        bases.append(get_base_community(clean_rec))

    base_counts = {}
    for b in bases:
        base_counts[b] = base_counts.get(b, 0) + 1

    clean_records_info = []
    pinyin_hints = []

    for i, (record_str, clean_rec) in enumerate(raw_clean_recs):
        b = bases[i]
        base_rec = b if base_counts[b] == 1 else clean_rec

        py_str = ""
        if has_pinyin and clean_rec:
            rec_pys = pypinyin.pinyin(clean_rec, heteronym=False, style=pypinyin.NORMAL)
            py_str = " ".join([p[0] for p in rec_pys]) if rec_pys else ""

        clean_records_info.append({
            "original": record_str,
            "clean_address": clean_rec,
            "base_address": base_rec,
            "pinyin": py_str
        })

    if clean_records_info:
        context_parts.append(f"candidates_info={json.dumps(clean_records_info, ensure_ascii=False)}")

    context_text = ", ".join(context_parts)

    display_scope = clean_input
    if display_scope:
        context_text += (
            f"\n[Display Constraint] If reply starts with the recorded-address prefix, "
            f"the recorded address must be limited to candidate-supported user-spoken scope from clean_user_input: {display_scope}, "
            "unless the model first judges clean_user_input is a supplement to "
            "last_matched_address_fragment/last_unmatched_address; in that supplement case, "
            "the recorded address may use the combined user-spoken scope made only from those fields. "
            "Use candidates_info only for matching, same-scope homophone correction, ordered address-anchor completion, and missing-level judgment. "
            "If multiple spoken anchors map in order to one candidate, the recorded fragment may use the candidate standard text between the first and last anchor, "
            "but must not add candidate-only province/city/district/town/road/community or any text outside that anchored span. "
            "If clean_user_input has no candidate-backed anchor, do not record it as matched_address_fragment. "
            "A correction may only replace an already-spoken span with similar-length same-scope text. "
            "Pinyin correction is limited to identical pronunciation, polyphone pronunciation overlap, "
            "zh/z, ch/c, sh/s initials, and front/back nasal finals; different syllables must not be corrected."
        )

    clean_candidate_records = [clean_rec for _record_str, clean_rec in raw_clean_recs]

    phonetic_mismatch_hint = _build_phonetic_mismatch_hint(
        display_scope,
        clean_candidate_records,
    )
    if phonetic_mismatch_hint:
        context_text += f"\n[System Hint] {phonetic_mismatch_hint}"

    ordered_anchor_span_hint = _build_ordered_candidate_anchor_span_hint(
        display_scope,
        clean_candidate_records,
    )
    if ordered_anchor_span_hint:
        context_text += f"\n[System Hint] {ordered_anchor_span_hint}"

    no_candidate_anchor_hint = _build_no_candidate_anchor_hint(
        display_scope,
        clean_candidate_records,
    )
    if no_candidate_anchor_hint:
        context_text += f"\n[System Hint] {no_candidate_anchor_hint}"

    previous_context_fragment = last_unmatched_fragment or last_unmatched_address
    if clean_input and previous_context_fragment:
        context_text += (
            f"\n[System Hint] 本轮 User 只表示 clean_user_input“{clean_input}”，"
            "不是与上一轮地址自动拼接后的文本。请先判断 clean_user_input 与 "
            f"last_matched_address_fragment/last_unmatched_address“{previous_context_fragment}”的关系："
            "若是补充上一轮地址，可将上一轮片段与本轮片段共同视为用户已说范围参与匹配；"
            "若是纠正、冲突、全新地址或无关内容，则不要强行合并。"
            "matched_address_fragment 只能输出模型判定后的用户已说且候选支持范围；"
            "如果判定为补充上一轮地址，matched_address_fragment 必须包含上一轮片段和本轮片段，"
            "必须输出两者在同一候选中的标准合并结果，不能只输出 clean_user_input 本轮片段。"
            "禁止补入候选中用户未说出的路名、楼栋、单元、门牌或房间号。"
        )

    if previous_context_fragment:
        has_unsupported_residential_place_anchor = _has_unsupported_residential_place_anchor(
            display_scope,
            clean_candidate_records,
        )
        if has_unsupported_residential_place_anchor:
            context_text += (
                f"\n[System Hint] 本轮地点主体校验：current_place_anchor={json.dumps(display_scope, ensure_ascii=False)}；"
                "anchor_type=住宅/村镇主体；candidate_supports_current_anchor=false。"
                "共享前缀、拼音相近或上一轮门牌细节唯一，都不能视为候选支持当前地点主体。"
                "本轮应按地点主体无候选支持处理：matched_index=-1, match_count=0, is_completed=false；"
                "matched_address_fragment 应按提示词中无候选支持或上一轮结果的规则处理。"
            )
        else:
            combined_context_scope = (
                _find_candidate_backed_merge(
                    previous_context_fragment,
                    display_scope,
                    clean_candidate_records,
                )
                or _combine_address_parts(previous_context_fragment, display_scope)
            )
            unique_supplement_hint = _build_unique_candidate_hint(
                combined_context_scope,
                clean_candidate_records,
            )
            if unique_supplement_hint:
                context_text += f"\n[System Hint] {unique_supplement_hint}"
            else:
                ambiguity_hint = _build_ambiguous_candidate_hint(
                    combined_context_scope,
                    clean_candidate_records,
                )
                if ambiguity_hint:
                    context_text += f"\n[System Hint] {ambiguity_hint}"
                else:
                    context_text += (
                        "\n[System Hint] 如果你判断本轮是在补充上一轮地址，"
                        "请先用合并后的用户已说范围重新筛选 candidates_info："
                        "若能缩到唯一候选，仍必须继续校验是否命中该候选最后两个有效层级，只有命中最后两级才输出 match_count=1；"
                        "合并后仍匹配多条候选，或未命中最后两级时，输出 matched_index=-1、match_count=0。"
                        "L7 内部楼栋号、单元号、门牌号、房号无论命中多少项，都只能算命中最后一级，不能替代倒数第二级。"
                        "reason 必须根据 matched_address_fragment 覆盖候选最后两级的情况填写："
                        "只含倒数第二级输出 two，只含倒数第一级输出 one，两级都含输出 true，其他输出空字符串；"
                        "只覆盖 L5/前置路址范围时 reason 必须为空字符串。"
                        "matched_address_fragment 应保留合并后的用户已说且候选支持范围，"
                        "不得丢失为仅 clean_user_input；例如上一轮“100号楼1单元302室”、本轮“江阳化工厂”、"
                        "候选支持“江阳化工厂100号楼1单元302室”时，matched_address_fragment 必须输出“江阳化工厂100号楼1单元302室”。"
                    )
    else:
        current_unique_level_hint = _build_current_unique_last_level_hint(
            display_scope,
            clean_candidate_records,
        )
        if current_unique_level_hint:
            context_text += f"\n[System Hint] {current_unique_level_hint}"
        else:
            ambiguity_hint = _build_ambiguous_candidate_hint(
                display_scope,
                clean_candidate_records,
            )
            if ambiguity_hint:
                context_text += f"\n[System Hint] {ambiguity_hint}"

    if is_address_correction:
        context_text += f"\n[System Hint] 用户正在纠正上一条地址，本轮有效地址片段更可能是: {clean_input}。如当前状态不是matching，请按新的匹配请求处理。"

    pinyin_source_input = clean_input
    if has_pinyin and pinyin_source_input:
        t1 = re.sub(r"[^\w\u4e00-\u9fff]+", "", pinyin_source_input)
        if t1:
            user_pys = [set(p) for p in pypinyin.pinyin(t1, heteronym=True, style=pypinyin.NORMAL)]
            n_u = len(user_pys)

            if n_u >= 2:
                for rec_info in clean_records_info:
                    record_str = rec_info["original"]
                    clean_rec = rec_info["clean_address"]

                    t2 = re.sub(r"[^\w\u4e00-\u9fff]+", "", clean_rec)
                    if not t2:
                        continue

                    record_pys = [set(p) for p in pypinyin.pinyin(t2, heteronym=True, style=pypinyin.NORMAL)]
                    n_r = len(record_pys)

                    match_hint = ""
                    if 0 < n_u <= n_r:
                        for i_r in range(n_r - n_u + 1):
                            if all(chars_phonetic_equal(t1[j], t2[i_r + j]) for j in range(n_u)):
                                matched_span = t2[i_r:i_r + n_u]
                                match_hint = f"{t1}~{matched_span}" if matched_span and matched_span != t1 else t1
                                break
                    elif 0 < n_r <= n_u:
                        for i_u in range(n_u - n_r + 1):
                            if all(chars_phonetic_equal(t2[j], t1[i_u + j]) for j in range(n_r)):
                                user_span = t1[i_u:i_u + n_r]
                                match_hint = f"{user_span}~{t2}" if user_span and user_span != t2 else t2
                                break

                    if match_hint:
                        pinyin_hints.append(match_hint)

    if pinyin_hints:
        pinyin_hints = list(dict.fromkeys(pinyin_hints))
        context_text += f"\n[System Hint] \u6839\u636e\u62fc\u97f3(\u591a\u97f3\u5b57)\u53d1\u73b0\u7528\u6237\u7247\u6bb5\u4e0e\u5019\u9009\u7247\u6bb5\u76f8\u8fd1: {', '.join(pinyin_hints)}\u3002\u53ea\u80fd\u7528\u4e8e\u66ff\u6362\u7528\u6237\u5df2\u8bf4\u51fa\u7684\u540c\u5c42\u7ea7\u7247\u6bb5\uff0c\u7981\u6b62\u8865\u9f50\u5019\u9009\u4e2d\u7528\u6237\u672a\u8bf4\u51fa\u7684\u5185\u5bb9\u3002"

    semantic_hints = []
    if re.search(r"\d+\s*#", user_input):
        semantic_hints.append("用户输入中的“数字#”表示楼栋/栋座标记，例如“10#101”应理解为“10号楼101”，不要匹配成“10号门”。")
    if re.search(r"\d+\s*号\s*门", user_input):
        semantic_hints.append("用户输入中的“数字号门”表示门或入口位置，不表示楼栋号，不能与“数字#”“数字号楼”“数字栋”互认。")
    if re.search(r"[一二两三四五六七八九十百千万零〇]+(?:楼|号楼|栋|幢|座|单元|室)|单元[一二两三四五六七八九十百千万零〇]{2,6}", user_input):
        semantic_hints.append("用户输入中的中文数字地址编号必须在用户口述范围内保留原片段，并按分段等价参与匹配：例如“一百楼一单元三零二”中“一百”可匹配候选的“100”，“一”可匹配“1”，“三零二”可匹配“302”；禁止把“一百”裁掉只剩“楼”，也不能仅凭该规则补入用户未说出的地点层级。若用户只说楼栋/单元/房号等 L7 详细地址，即使命中多个 L7 元素，也只能算“只命中最后一级”，不能输出 match_count=1；禁止把“100号楼”拆成倒数第二级、把“1单元302室”拆成最后一级；matched_address_fragment 仍必须使用候选地址中的标准原文片段，不能输出用户口述中文数字片段。")
    if semantic_hints:
        context_text += f"\n[System Hint] {' '.join(semantic_hints)}"

    effective_user_input = clean_input
    combined = f"{context_text}\nUser: {effective_user_input}" if effective_user_input else context_text

    history_base = clean_input
    history_msg = history_base
    if has_pinyin and history_msg:
        raw_pys = pypinyin.pinyin(history_msg, heteronym=False, style=pypinyin.NORMAL)
        user_py_str = " ".join([p[0] for p in raw_pys]) if raw_pys else ""
        if user_py_str:
            history_msg = f"{history_msg} [拼音: {user_py_str}]"

    return {
        "user_message": combined,
        "history_user_message": history_msg,
        "clean_user_input": clean_input,
        "llm_user_input": clean_input,
        "effective_match_input": effective_merged_input or clean_input,
        "possible_merged_input": possible_merged_input if is_possible_supplement_fragment else ""
    }
