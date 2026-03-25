from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional


def _normalize_code_filter(codes: Optional[Iterable[str]]) -> set[str]:
    return {
        str(code).strip()
        for code in (codes or [])
        if str(code or "").strip()
    }


def _trim_record_to_codes(record: Dict[str, Any], code_filter: set[str]) -> Optional[Dict[str, Any]]:
    cloned = deepcopy(record)
    raw_data = cloned.get("raw_data") or {}
    stocks = [
        stock
        for stock in (raw_data.get("stocks") or [])
        if str(stock.get("code", "") or "") in code_filter
    ]
    if not stocks:
        return None

    raw_data["stocks"] = stocks
    cloned["raw_data"] = raw_data

    ai_result = cloned.get("ai_result") or {}
    actions = [
        action
        for action in (ai_result.get("actions") or [])
        if str(action.get("code", "") or "") in code_filter
    ]
    if actions:
        ai_result["actions"] = actions
        cloned["ai_result"] = ai_result
    return cloned


def slice_records(
    records: List[Dict[str, Any]],
    *,
    days: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    ordered = sorted(records, key=lambda item: str(item.get("date", "")))

    if date_from:
        ordered = [record for record in ordered if str(record.get("date", "")) >= str(date_from)]
    if date_to:
        ordered = [record for record in ordered if str(record.get("date", "")) <= str(date_to)]
    if days is not None and not date_from and not date_to:
        ordered = ordered[-int(days) :]

    code_filter = _normalize_code_filter(codes)
    if not code_filter:
        return ordered

    trimmed: List[Dict[str, Any]] = []
    for record in ordered:
        filtered = _trim_record_to_codes(record, code_filter)
        if filtered is not None:
            trimmed.append(filtered)
    return trimmed
