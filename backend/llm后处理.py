import re


NON_MERGE_HISTORY_PREFIX = "__NO_MERGE__:"
SIMILAR_NO_MATCH_FAIL_THRESHOLD = 2
FAIL_REPLY = "抱歉您提供的地址不正确。"
DETAIL_REPLY = "请你提供详细的地址信息"


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
    if not isinstance(address_list, list):
        address_list = []
    current_state = _to_str(state)

    # Step 0: 预处理。保留用户输入清洗、上一轮上下文合并，以及 LLM fragment 按候选顺序重排。
    current_input = _normalize_address_marker_tokens(
        _strip_embedded_reason_field(_to_str(clean_user_input))
    )
    previous_address = _normalize_address_marker_tokens(
        _strip_embedded_reason_field(_strip_non_merge_history(last_unmatched_address))
    )
    previous_fragment = _normalize_address_marker_tokens(
        _strip_embedded_reason_field(_strip_non_merge_history(last_unmatched_fragment))
    )

    reason = _normalize_reason(llm_result.get("reason"))
    model_matched_index = _to_int(llm_result.get("matched_index"), -1)
    fallback_matched_index = _to_int(matched_index, -1)
    previous_count = max(_to_int(similar_no_match_count, 0), 0)

    if current_state == "confirming" and _is_confirming_affirmation(current_input):
        confirmed_index = fallback_matched_index if fallback_matched_index >= 0 else model_matched_index
        if confirmed_index >= 0:
            return _build_return(
                llm_result=llm_result,
                match_count=1,
                matched_index=confirmed_index,
                is_completed=True,
                is_extract_failed=False,
                matched_address_fragment="",
                reason="",
                reply="",
                ai_context_reply="",
                next_last_unmatched_address="",
                next_last_unmatched_fragment="",
                next_similar_no_match_count=0,
            )

    matched_address_fragment = _normalize_address_marker_tokens(
        _strip_embedded_reason_field(_to_str(llm_result.get("matched_address_fragment")))
    )
    matched_address_fragment = _reorder_llm_fragment_if_needed(
        matched_address_fragment,
        previous_fragment,
        model_matched_index,
        address_list,
    )

    ai_context_display_address = _build_ai_context_display_address(
        previous_fragment=previous_fragment,
        matched_address_fragment=matched_address_fragment,
        reason=reason,
        address_list=address_list,
    )
    matched_address_fragment = ai_context_display_address

    reused_previous_fragment = bool(
        matched_address_fragment
        and previous_fragment
        and matched_address_fragment == previous_fragment
    )
    if reused_previous_fragment and previous_address:
        reply_current_input = previous_address
        reply_previous_address = ""
    else:
        reply_current_input = current_input
        reply_previous_address = previous_address
    reply_display_address = _build_reply_display_address(
        current_input=reply_current_input,
        previous_address=reply_previous_address,
        previous_fragment="",
        matched_address_fragment=matched_address_fragment,
        reason=reason,
        address_list=address_list,
    )

    if reason == "one" and matched_address_fragment:
        fallback_index = _infer_unique_candidate_by_non_admin_tail(matched_address_fragment, address_list)
        if fallback_index >= 0:
            reason = "true"
            model_matched_index = fallback_index

    # Step 1: LLM result 的状态字段只由 reason 决定。
    final_match_count, final_matched_index, final_is_completed, final_is_extract_failed = (
        _build_result_status_by_reason(
            reason=reason,
            model_matched_index=model_matched_index,
            fallback_matched_index=fallback_matched_index,
        )
    )
    next_last_unmatched_fragment = "" if reason == "true" else matched_address_fragment

    # Step 2: 重复失败计数单独处理，只调用一次；触发失败时跳过 Step 3。
    next_similar_no_match_count, should_fail = _calculate_repeat_failure(
        reason=reason,
        matched_address_fragment=matched_address_fragment,
        last_unmatched_fragment=previous_fragment,
        previous_count=previous_count,
    )
    if should_fail:
        return _build_return(
            llm_result=llm_result,
            match_count=0,
            matched_index=-1,
            is_completed=False,
            is_extract_failed=True,
            matched_address_fragment="",
            reason="",
            reply=FAIL_REPLY,
            ai_context_reply=FAIL_REPLY,
            next_last_unmatched_address="",
            next_last_unmatched_fragment="",
            next_similar_no_match_count=next_similar_no_match_count,
        )

    # Step 3: reply 给用户看，ai_context_reply 给大模型看，两者的地址来源必须分开。
    no_supported_context = not reason and not matched_address_fragment and not previous_fragment
    reply = DETAIL_REPLY if no_supported_context else _build_reply_by_reason(reason, reply_display_address)
    ai_context_reply = (
        DETAIL_REPLY
        if no_supported_context
        else _build_reply_by_reason(reason, ai_context_display_address)
    )
    if no_supported_context:
        next_last_unmatched_address = ""
    else:
        next_last_unmatched_address = (
            _mark_non_merge_history(reply_display_address)
            if reason == "true"
            else reply_display_address
        )

    return _build_return(
        llm_result=llm_result,
        match_count=final_match_count,
        matched_index=final_matched_index,
        is_completed=final_is_completed,
        is_extract_failed=final_is_extract_failed,
        matched_address_fragment=matched_address_fragment,
        reason=reason,
        reply=reply,
        ai_context_reply=ai_context_reply,
        next_last_unmatched_address=next_last_unmatched_address,
        next_last_unmatched_fragment=next_last_unmatched_fragment,
        next_similar_no_match_count=next_similar_no_match_count,
    )


def _build_result_status_by_reason(reason: str, model_matched_index: int, fallback_matched_index: int):
    if reason == "true":
        final_matched_index = model_matched_index if model_matched_index >= 0 else fallback_matched_index
        return 1, final_matched_index, False, False
    return 0, -1, False, False


def _infer_unique_candidate_by_non_admin_tail(matched_address_fragment: str, address_list: list) -> int:
    fragment_variants = _non_admin_tail_norm_variants(matched_address_fragment, strip_subdistrict=False)
    if not fragment_variants or not _has_non_admin_place_anchor(matched_address_fragment):
        return -1

    matched_indexes = []
    for index, candidate in enumerate(address_list):
        candidate_variants = _non_admin_tail_norm_variants(candidate, strip_subdistrict=True)
        if any(
            _candidate_tail_matches_fragment(candidate_norm, fragment_norm)
            for fragment_norm in fragment_variants
            for candidate_norm in candidate_variants
        ):
            matched_indexes.append(index)

    return matched_indexes[0] if len(matched_indexes) == 1 else -1


def _candidate_tail_matches_fragment(candidate_norm: str, fragment_norm: str) -> bool:
    if candidate_norm == fragment_norm or candidate_norm.endswith(fragment_norm):
        return True
    return _fragment_extends_candidate_tail(fragment_norm, candidate_norm)


def _fragment_extends_candidate_tail(fragment_norm: str, candidate_norm: str) -> bool:
    if not fragment_norm or not candidate_norm:
        return False

    for end in range(len(fragment_norm) - 1, 1, -1):
        supported_prefix = fragment_norm[:end]
        extra_suffix = fragment_norm[end:]
        if not candidate_norm.endswith(supported_prefix):
            continue
        if not _looks_like_more_specific_detail_suffix(extra_suffix):
            continue
        if not _has_non_admin_place_anchor(supported_prefix):
            continue
        return True
    return False


def _looks_like_more_specific_detail_suffix(text: str) -> bool:
    text = _to_str(text)
    if not text:
        return False

    cn_num = _CN_ADDRESS_NUMBER_CHARS
    numeric = fr"(?:\d+|[{cn_num}]+)"
    numeric_or_seat = fr"(?:{numeric}|[a-z]\d*)"
    bare_room = fr"(?:\d{{3,6}}|[{cn_num}]{{3,6}})"
    detail_part = fr"(?:{numeric_or_seat}(?:栋|幢|座|楼|单元|室)|{bare_room})"
    return bool(re.fullmatch(fr"(?:{detail_part})+", text))


def _non_admin_tail_norm_variants(text: str, strip_subdistrict: bool) -> set[str]:
    tail = _strip_leading_admin_tokens_for_tail_match(text, strip_subdistrict=strip_subdistrict)
    if not tail:
        return set()

    variants = {
        tail,
        _fold_subdistrict_street_suffix(tail),
        _drop_repeated_subdistrict_street(tail),
    }
    return {norm for norm in (_normalize_text(value) for value in variants) if norm}


def _strip_leading_admin_tokens_for_tail_match(text: str, strip_subdistrict: bool) -> str:
    text = _normalize_address_marker_tokens(text)
    patterns = [
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省)",
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?市",
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗)",
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:镇|乡)",
    ]
    if strip_subdistrict:
        patterns.append(r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?街道")

    changed = True
    while changed and text:
        changed = False
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                text = text[match.end():]
                changed = True
                break
    return text.strip()


def _fold_subdistrict_street_suffix(text: str) -> str:
    text = _to_str(text)
    if not text:
        return ""
    cn_num = _CN_ADDRESS_NUMBER_CHARS
    return re.sub(
        fr"([\u4e00-\u9fa5A-Za-z0-9]{{1,20}})街道(?=(?:\d+|[{cn_num}]+)(?:号|号院|弄|里))",
        r"\1街",
        text,
    )


def _drop_repeated_subdistrict_street(text: str) -> str:
    text = _to_str(text)
    match = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9]{1,20}?)街道(.+)$", text)
    if not match:
        return text
    root, rest = match.groups()
    return rest if rest.startswith(f"{root}街") else text


def _has_non_admin_place_anchor(text: str) -> bool:
    tail = _strip_leading_admin_tokens_for_tail_match(text, strip_subdistrict=False)
    anchor = _extract_named_place_fragment(_prefix_before_first_detail_scope(tail))
    anchor = _strip_leading_admin_tokens_for_tail_match(anchor, strip_subdistrict=False)
    anchor = _fold_subdistrict_street_suffix(anchor)
    anchor_norm = _normalize_text(anchor)
    return bool(len(anchor_norm) >= 2 and not _is_weak_area_fragment(anchor))


def _prefix_before_first_detail_scope(text: str) -> str:
    text = _normalize_address_marker_tokens(text)
    if not text:
        return ""
    cn_num = _CN_ADDRESS_NUMBER_CHARS
    match = re.search(
        fr"(?:\d+|[{cn_num}]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼|单元|室|号院|号|弄|里)|(?<!\d)\d{{3,6}}(?!\d)",
        text,
    )
    return text[:match.start()].strip() if match else text.strip()


def _calculate_repeat_failure(
    reason: str,
    matched_address_fragment: str,
    last_unmatched_fragment: str,
    previous_count: int,
) -> tuple[int, bool]:
    if reason == "true":
        return 0, False

    current_norm = _normalize_text(matched_address_fragment)
    previous_norm = _normalize_text(last_unmatched_fragment)
    if current_norm and previous_norm and current_norm == previous_norm:
        next_count = previous_count + 1
    else:
        next_count = 0

    return next_count, next_count == SIMILAR_NO_MATCH_FAIL_THRESHOLD


def _build_reply_by_reason(reason: str, display_address: str) -> str:
    display_address = _to_str(display_address)
    if reason == "true":
        return f"请问您说的是{display_address}吗？" if display_address else ""
    if not display_address:
        return DETAIL_REPLY
    if reason == "two":
        return f"我记录的地址信息是：{display_address}，请您再提供下楼栋单元号详细信息"
    if reason == "one":
        return f"我记录的地址信息是：{display_address}，请您再提供下小区名称或楼宇名称"
    return f"我记录的地址信息是：{display_address}，请您再提供下小区和楼栋单元号详细信息"


def _build_return(
    llm_result: dict,
    match_count: int,
    matched_index: int,
    is_completed: bool,
    is_extract_failed: bool,
    matched_address_fragment: str,
    reason: str,
    reply: str,
    ai_context_reply: str,
    next_last_unmatched_address: str,
    next_last_unmatched_fragment: str,
    next_similar_no_match_count: int,
) -> dict:
    output_llm_result = dict(llm_result)
    output_llm_result["match_count"] = match_count
    output_llm_result["matched_index"] = matched_index
    output_llm_result["is_completed"] = is_completed
    output_llm_result["is_extract_failed"] = is_extract_failed
    output_llm_result["matched_address_fragment"] = matched_address_fragment
    output_llm_result["reason"] = reason
    output_llm_result["reply"] = reply
    output_llm_result["ai_context_reply"] = ai_context_reply

    return {
        "llm_result": output_llm_result,
        "next_last_unmatched_address": next_last_unmatched_address,
        "next_last_unmatched_fragment": next_last_unmatched_fragment,
        "next_similar_no_match_count": next_similar_no_match_count,
    }


def _build_ai_context_display_address(
    previous_fragment: str,
    matched_address_fragment: str,
    reason: str,
    address_list: list,
) -> str:
    return _build_reply_display_address(
        current_input=matched_address_fragment,
        previous_address="",
        previous_fragment=previous_fragment,
        matched_address_fragment=matched_address_fragment,
        reason=reason,
        address_list=address_list,
    )


def _build_reply_display_address(
    current_input: str,
    previous_address: str,
    previous_fragment: str,
    matched_address_fragment: str,
    reason: str,
    address_list: list,
) -> str:
    previous_scope = previous_address or previous_fragment
    current_input = _normalize_address_marker_tokens(current_input)
    previous_scope = _normalize_address_marker_tokens(previous_scope)

    if not current_input:
        return previous_scope or matched_address_fragment
    if not previous_scope:
        return current_input

    candidate_backed_merge = _find_candidate_backed_merge(previous_scope, current_input, address_list)
    if candidate_backed_merge:
        return candidate_backed_merge

    if _looks_like_place_scope(current_input) and _has_detail_scope(previous_scope):
        return _combine_user_spoken_parts(current_input, previous_scope)
    if _has_detail_scope(current_input) and _looks_like_place_scope(previous_scope):
        return _combine_user_spoken_parts(previous_scope, current_input)
    if _is_fragment_input(current_input) or _has_address_overlap(previous_scope, current_input):
        return _combine_user_spoken_parts(previous_scope, current_input)
    if _should_merge_region_continuation(previous_scope, current_input):
        return _combine_user_spoken_parts(previous_scope, current_input)

    if reason == "true" and matched_address_fragment:
        return _choose_user_spoken_or_fragment(
            user_scope=current_input,
            matched_address_fragment=matched_address_fragment,
        )
    return current_input


def _choose_user_spoken_or_fragment(user_scope: str, matched_address_fragment: str) -> str:
    user_norm = _normalize_text(user_scope)
    fragment_norm = _normalize_text(matched_address_fragment)
    if user_norm and fragment_norm and user_norm in fragment_norm and len(user_norm) < len(fragment_norm):
        return matched_address_fragment
    return user_scope or matched_address_fragment


def _reorder_llm_fragment_if_needed(fragment: str, previous_fragment: str, matched_index: int, address_list: list) -> str:
    if not fragment or not previous_fragment or not (0 <= matched_index < len(address_list)):
        return fragment
    reordered = _reorder_model_fragment_by_candidate_order(
        fragment,
        previous_fragment,
        _to_str(address_list[matched_index]),
    )
    return reordered or fragment


def _reorder_model_fragment_by_candidate_order(fragment: str, previous_fragment: str, candidate: str) -> str:
    fragment = _normalize_address_marker_tokens(fragment)
    previous_fragment = _normalize_address_marker_tokens(previous_fragment)
    candidate = _normalize_address_marker_tokens(candidate)
    if not fragment or not previous_fragment or not candidate:
        return ""
    if _fragment_supported_by_candidate(fragment, candidate):
        return ""

    previous_index_in_fragment = fragment.find(previous_fragment)
    if previous_index_in_fragment < 0:
        return ""

    added_fragment = (
        fragment[:previous_index_in_fragment]
        + fragment[previous_index_in_fragment + len(previous_fragment):]
    ).strip()
    if not added_fragment:
        return ""

    previous_index_in_candidate = candidate.find(previous_fragment)
    added_index_in_candidate = candidate.find(added_fragment)
    if previous_index_in_candidate < 0 or added_index_in_candidate < 0:
        return ""

    ordered_fragment = "".join(
        value for _, value in sorted(
            (
                (previous_index_in_candidate, previous_fragment),
                (added_index_in_candidate, added_fragment),
            ),
            key=lambda item: item[0],
        )
    )
    if ordered_fragment == fragment:
        return ""
    return ordered_fragment if _fragment_supported_by_candidate(ordered_fragment, candidate) else ""


def _find_candidate_backed_merge(previous_scope: str, current_input: str, address_list: list) -> str:
    previous_scope = _normalize_address_marker_tokens(previous_scope)
    current_input = _normalize_address_marker_tokens(current_input)
    if not previous_scope or not current_input or not isinstance(address_list, list):
        return ""

    previous_terms = _candidate_backed_terms(previous_scope)
    current_terms = _candidate_backed_terms(current_input)
    if not previous_terms or not current_terms:
        return ""

    required_norms = {norm for _value, norm in previous_terms + current_terms if norm}
    if not required_norms:
        return ""

    matches = []
    for candidate in address_list:
        candidate = _to_str(candidate)
        candidate_norm = _normalize_text(candidate)
        if candidate_norm and all(norm in candidate_norm for norm in required_norms):
            matches.append(candidate)

    if not matches:
        return ""

    ordered = _order_user_parts_by_candidate(previous_scope, current_input, matches[0])
    return ordered or _combine_user_spoken_parts(previous_scope, current_input)


def _order_user_parts_by_candidate(previous_scope: str, current_input: str, candidate: str) -> str:
    previous_scope = _normalize_address_marker_tokens(previous_scope)
    current_input = _normalize_address_marker_tokens(current_input)
    candidate = _normalize_address_marker_tokens(candidate)
    if not previous_scope or not current_input or not candidate:
        return ""

    prev_index = candidate.find(previous_scope)
    curr_index = candidate.find(current_input)
    if prev_index >= 0 and curr_index >= 0:
        first, second = (
            (previous_scope, current_input)
            if prev_index <= curr_index
            else (current_input, previous_scope)
        )
        return _combine_user_spoken_parts(first, second)

    if _looks_like_place_scope(current_input) and _has_detail_scope(previous_scope):
        return _combine_user_spoken_parts(current_input, previous_scope)
    if _has_detail_scope(current_input) and _looks_like_place_scope(previous_scope):
        return _combine_user_spoken_parts(previous_scope, current_input)
    return ""


def _combine_user_spoken_parts(previous_scope: str, current_input: str) -> str:
    previous_scope = _normalize_address_marker_tokens(previous_scope)
    current_input = _normalize_address_marker_tokens(current_input)
    if not current_input:
        return previous_scope
    if not previous_scope:
        return current_input

    if current_input == previous_scope or previous_scope in current_input:
        return current_input
    if current_input in previous_scope:
        return previous_scope

    previous_norm = _normalize_text(previous_scope)
    current_norm = _normalize_text(current_input)
    if current_norm == previous_norm or (current_norm and current_norm in previous_norm):
        return previous_scope
    if previous_norm and previous_norm in current_norm:
        return current_input

    overlap_len = _suffix_prefix_overlap_len(previous_norm, current_norm)
    if overlap_len:
        return f"{previous_scope}{current_input[overlap_len:]}"
    return f"{previous_scope}{current_input}"


def _suffix_prefix_overlap_len(previous_norm: str, current_norm: str) -> int:
    max_overlap = min(len(previous_norm), len(current_norm))
    for overlap_len in range(max_overlap, 1, -1):
        if previous_norm.endswith(current_norm[:overlap_len]):
            return overlap_len
    return 0


def _candidate_backed_terms(text: str) -> list[tuple[str, str]]:
    text = _normalize_address_marker_tokens(text)
    terms = []

    def add(value: str, min_len: int = 2) -> None:
        value = _normalize_address_marker_tokens(value)
        norm = _normalize_text(value)
        if len(norm) >= min_len and norm not in {item[1] for item in terms}:
            terms.append((value, norm))

    for value in (
        _extract_road_name(text),
        _extract_community_name(text),
        _extract_building_name(text),
        _extract_unit_name(text),
        _extract_room_name(text),
        _extract_house_name(text),
    ):
        add(value)

    named = _strip_leading_admin_tokens(_extract_named_place_fragment(text))
    if named:
        add(named, 2 if _looks_like_place_scope(named) else 4)

    if not terms:
        add(text, 2)
    return terms


def _fragment_supported_by_candidate(fragment: str, candidate: str) -> bool:
    fragment_norm = _normalize_text(fragment)
    candidate_norm = _normalize_text(candidate)
    return bool(fragment_norm and candidate_norm and fragment_norm in candidate_norm)


def _has_address_overlap(left: str, right: str) -> bool:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    return bool(
        left_norm
        and right_norm
        and (left_norm == right_norm or left_norm in right_norm or right_norm in left_norm)
    )


def _is_fragment_input(text: str) -> bool:
    text_norm = _normalize_text(text)
    if not text_norm:
        return False
    has_detail = bool(re.search(
        r"(小区|花园|公寓|大厦|苑|村|路|大道|巷|胡同|街|栋|幢|座|单元|室|号楼|号院|\d+号|\d+栋|\d+单元|\d+室|\d{3,6})",
        text_norm,
    ))
    has_broad_region = bool(re.search(r"(省|市|县|旗|镇|乡|街道)", text_norm))
    return has_detail and not has_broad_region


def _should_merge_region_continuation(previous_scope: str, current_input: str) -> bool:
    previous_rank = _admin_region_rank(previous_scope)
    current_rank = _admin_region_rank(current_input)
    if previous_rank <= 0 or current_rank <= previous_rank:
        return False
    previous_norm = _normalize_text(previous_scope)
    current_norm = _normalize_text(current_input)
    return bool(previous_norm and current_norm and previous_norm not in current_norm and current_norm not in previous_norm)


def _admin_region_rank(text: str) -> int:
    text = _to_str(text)
    if re.search(r"(街道|镇|乡)", text):
        return 4
    if re.search(r"(区|县|旗)", text):
        return 3
    if re.search(r"市", text):
        return 2
    if re.search(r"(省|自治区|特别行政区)", text):
        return 1
    return 0


def _looks_like_place_scope(text: str) -> bool:
    text = _to_str(text)
    return bool(
        text
        and (
            re.search(r"(小区|花园|公寓|大厦|楼宇|苑|村|镇|乡|街道|路|大道|巷|胡同|街(?!道)|弄|里)", text)
            or _has_named_place_anchor(text)
        )
    )


def _has_named_place_anchor(text: str) -> bool:
    fragment = _strip_leading_admin_tokens(_extract_named_place_fragment(text))
    fragment_norm = _normalize_text(fragment)
    if len(fragment_norm) < 4:
        return False
    return not _is_weak_area_fragment(fragment)


def _has_detail_scope(text: str) -> bool:
    text = _normalize_address_marker_tokens(text)
    if not text:
        return False
    return bool(
        _extract_building_name(text)
        or _extract_unit_name(text)
        or _extract_room_name(text)
        or _extract_house_name(text)
        or re.search(r"(?<!\d)\d{3,6}(?!\d)", text)
    )


def _extract_community_name(text: str) -> str:
    text = _strip_broad_region_prefix(text)
    matches = re.findall(r"(?=([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:小区|花园|公寓|大厦|苑|村)))", text)
    return min(set(matches), key=len) if matches else ""


def _extract_road_name(text: str) -> str:
    text = _strip_broad_region_prefix(text)
    community = _extract_community_name(text)
    if community and community in text:
        text = text[text.index(community) + len(community):]
    matches = re.findall(r"(?=([\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:大道|路|巷|胡同|街(?!道))))", text)
    return min(set(matches), key=len) if matches else ""


def _extract_building_name(text: str) -> str:
    text = _normalize_address_marker_tokens(text)
    match = re.search(r"((?:\d+|[一二两三四五六七八九十百千万零〇]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼))", text)
    return match.group(1) if match else ""


def _extract_unit_name(text: str) -> str:
    text = _normalize_address_marker_tokens(text)
    match = re.search(r"((?:\d+|[一二两三四五六七八九十百千万零〇]+)单元)", text)
    return match.group(1) if match else ""


def _extract_room_name(text: str) -> str:
    text = _normalize_address_marker_tokens(text)
    match = re.search(r"((?:\d+|[一二两三四五六七八九十百千万零〇]{3,6})室)", text)
    if match:
        return match.group(1)
    stripped = re.sub(r"(?:\d+|[一二两三四五六七八九十百千万零〇]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼)", "", text)
    stripped = re.sub(r"(?:\d+|[一二两三四五六七八九十百千万零〇]+)单元", "", stripped)
    nums = re.findall(r"(?<!\d)(\d{3,6})(?!\d)", stripped)
    return nums[-1] if nums else ""


def _extract_house_name(text: str) -> str:
    text = _normalize_address_marker_tokens(text)
    match = re.search(r"(\d+号院|\d+号(?!楼|栋|幢|单元|室)|\d+弄|\d+里)", text)
    return match.group(1) if match else ""


def _extract_named_place_fragment(text: str) -> str:
    text = _normalize_address_marker_tokens(text)
    fragment = re.sub(r"(?:\d+|[一二两三四五六七八九十百千万零〇]+|[A-Za-z]\d*)(?:栋|幢|座|号楼|楼)", "", text)
    fragment = re.sub(r"(?:\d+|[一二两三四五六七八九十百千万零〇]+)单元", "", fragment)
    fragment = re.sub(r"(?:\d+|[一二两三四五六七八九十百千万零〇]+)室", "", fragment)
    fragment = re.sub(r"(?<!\d)\d{3,6}(?!\d)|[一二两三四五六七八九十百千万零〇]{3,6}", "", fragment)
    fragment = re.sub(r"(\d+号院|\d+号(?!楼|栋|幢|单元|室)|\d+弄|\d+里)", "", fragment)
    return fragment.strip()


def _strip_broad_region_prefix(text: str) -> str:
    text = _to_str(text)
    pattern = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}(?:省|市|县|旗|镇|乡|街道)")
    last_end = 0
    for match in pattern.finditer(text):
        last_end = match.end()
    return text[last_end:] if last_end and last_end < len(text) else text


def _strip_leading_admin_tokens(text: str) -> str:
    text = _to_str(text)
    patterns = (
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:自治区|特别行政区|省)",
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?市",
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:区|县|旗)",
        r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}?(?:街道|镇|乡)",
    )
    changed = True
    while changed and text:
        changed = False
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                text = text[match.end():]
                changed = True
                break
    return text.strip()


def _is_weak_area_fragment(text: str) -> bool:
    text = _to_str(text)
    return bool(re.fullmatch(r"(东|西|南|北|中)(区|侧|门)?|[A-Za-z]区|[一二三四五六七八九十0-9]+区", text))


_CANONICAL_ADDRESS_MARKERS = ("号楼", "单元", "号院", "栋", "幢", "座", "楼", "室", "号", "弄", "里")


def _normalize_address_marker_tokens(text: str) -> str:
    text = _to_str(text)
    if not text:
        return ""

    result = []
    markers = sorted(_CANONICAL_ADDRESS_MARKERS, key=len, reverse=True)
    prefix_pattern = r"(?:\d+|[一二两三四五六七八九十百千万零〇]+|[A-Za-z]\d*)$"
    index = 0
    while index < len(text):
        prefix = "".join(result)
        if prefix and re.search(prefix_pattern, prefix):
            replaced = False
            for marker in markers:
                fragment = text[index:index + len(marker)]
                if fragment == marker:
                    result.append(marker)
                    index += len(marker)
                    replaced = True
                    break
            if replaced:
                continue
        result.append(text[index])
        index += 1

    normalized = "".join(result)
    normalized = re.sub(r"((?<!\d)\d{3,6})栋(?=区)", r"\1东", normalized)
    return normalized


def _normalize_text(text: str) -> str:
    text = _normalize_address_marker_tokens(_strip_non_merge_history(text))
    text = _normalize_address_number_compare_tokens(text)
    text = re.sub(r"\[拼音:.*?\]", "", text)
    text = text.replace("#", "号")
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
    return text.lower().strip()


_CN_NUMBER_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_NUMBER_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_CN_ADDRESS_NUMBER_CHARS = "一二两三四五六七八九十百千万零〇"


def _cn_number_to_arabic(text: str) -> str:
    text = _to_str(text)
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


def _normalize_address_number_compare_tokens(text: str) -> str:
    text = _to_str(text)
    if not text:
        return ""
    cn_num = f"[{_CN_ADDRESS_NUMBER_CHARS}]+"
    if re.fullmatch(cn_num, text):
        return _cn_number_to_arabic(text)
    text = re.sub(
        fr"({cn_num})(?=号楼|楼|栋|幢|座|单元|室)",
        lambda match: _cn_number_to_arabic(match.group(1)),
        text,
    )
    text = re.sub(
        fr"(?<=单元)({cn_num})(?=室|$|[^\u4e00-\u9fa5A-Za-z0-9])",
        lambda match: _cn_number_to_arabic(match.group(1)),
        text,
    )
    return text.replace("号楼", "楼")


def _normalize_reason(value) -> str:
    value = _to_str(value).lower()
    if value in {"true", "命中最后两级"}:
        return "true"
    if value in {"two", "只命中倒数第二级"}:
        return "two"
    if value in {"one", "只命中最后一级"}:
        return "one"
    return ""


def _is_confirming_affirmation(text: str) -> bool:
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", _to_str(text)).lower()
    if not text or re.search(r"(不是|不对|不正确|不准确|错了|错误|否)", text):
        return False

    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"^(嗯+|啊+|哦+|噢+|额+|呃+)", "", text)
        text = re.sub(r"(啊|呀|呢|吧|了|的)$", "", text)

    return text in {
        "是",
        "对",
        "没错",
        "正确",
        "准确",
        "就是",
        "是这个",
        "对这个",
        "是这个地址",
        "对这个地址",
        "好",
        "可以",
        "行",
        "没问题",
    }


def _strip_embedded_reason_field(text: str) -> str:
    text = _to_str(text)
    if not text:
        return ""
    text = re.sub(
        r"""(?is)\s*[,，]?\\?["']?\s*reason\s*\\?["']?\s*[:：]\s*\\?["']?(?:one|two|true|false|只命中最后一级|只命中倒数第二级|命中最后两级)?\\?["']?.*$""",
        "",
        text,
    )
    text = re.sub(
        r"""(?is)\s*[,，]?\s*['"]?\s*reason\s*['"]?\s*[:：]\s*['"]?(?:one|two|true|false|只命中最后一级|只命中倒数第二级|命中最后两级)?['"]?.*$""",
        "",
        text,
    )
    return text.strip(" ,，'\"")


def _to_int(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _to_str(value, default: str = "") -> str:
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
