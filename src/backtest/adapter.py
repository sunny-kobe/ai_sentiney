from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


DEFAULT_ACTION_TARGETS = {
    "增配": 0.20,
    "减配": 0.05,
    "回避": 0.0,
}


def _parse_target_weight(action: Mapping[str, Any]) -> Optional[float]:
    raw_value = action.get("target_weight") or action.get("target_weight_range")
    if raw_value is None:
        return None

    text = str(raw_value).replace("%", "").strip()
    if not text:
        return None
    if "-" in text:
        start, end = text.split("-", 1)
        return (float(start) + float(end)) / 200
    return float(text) / 100


def build_orders_from_actions(actions: Sequence[Mapping[str, Any]], *, trade_date: str) -> List[Dict[str, Any]]:
    orders: List[Dict[str, Any]] = []
    for action in actions:
        code = str(action.get("code", "") or "")
        if not code:
            continue

        action_label = str(action.get("action_label") or action.get("conclusion") or "")
        target_weight = _parse_target_weight(action)
        if target_weight is None:
            target_weight = DEFAULT_ACTION_TARGETS.get(action_label)
        if target_weight is None:
            continue

        orders.append(
            {
                "trade_date": trade_date,
                "code": code,
                "name": action.get("name", code),
                "action_label": action_label,
                "target_weight": float(target_weight),
            }
        )
    return orders
