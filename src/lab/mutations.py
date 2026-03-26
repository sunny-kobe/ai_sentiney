from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


CONFIDENCE_ORDER = {
    "低": 1,
    "中": 2,
    "高": 3,
}

DOWNGRADE_MAP = {
    "增配": "持有",
    "持有": "减配",
    "减配": "回避",
    "回避": "回避",
    "观察": "观察",
}


def _confidence_rank(value: str) -> int:
    return CONFIDENCE_ORDER.get(str(value or "").strip(), 0)


def _parse_blocklist(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _degrade_action(action_label: str) -> str:
    return DOWNGRADE_MAP.get(str(action_label or "").strip(), str(action_label or "").strip())


def _parse_target_weight_range(value: Any, action_label: str) -> Optional[Tuple[int, int]]:
    raw_value = value
    if raw_value is None:
        default_map = {
            "增配": (20, 20),
            "减配": (5, 5),
            "回避": (0, 0),
        }
        return default_map.get(str(action_label or "").strip())

    text = str(raw_value).replace("%", "").strip()
    if not text:
        return None
    if "-" in text:
        start, end = text.split("-", 1)
        return int(float(start)), int(float(end))
    number = int(float(text))
    return number, number


def _format_target_weight_range(weight_range: Optional[Tuple[int, int]]) -> str:
    if not weight_range:
        return "0%"
    low, high = max(int(weight_range[0]), 0), max(int(weight_range[1]), 0)
    if high <= 0:
        return "0%"
    if low == high:
        return f"{high}%"
    return f"{low}%-{high}%"


def _scale_weight_range(weight_range: Optional[Tuple[int, int]], factor: float) -> Optional[Tuple[int, int]]:
    if weight_range is None:
        return None
    low, high = weight_range
    return max(int(round(low * factor)), 0), max(int(round(high * factor)), 0)


def _parse_lookback_window(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    window = int(value)
    if window in {10, 20, 40}:
        return window
    return None


def _parse_drawdown_limit(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    limit = float(value)
    return -abs(limit)


def _relative_return_for_window(action: Mapping[str, Any], window: Optional[int]) -> Optional[float]:
    if window is None:
        return None
    value = action.get(f"relative_return_{window}")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _current_shares(action: Mapping[str, Any]) -> int:
    return int(action.get("current_shares", action.get("shares", 0)) or 0)


def _watchlist_rank(action: Mapping[str, Any]) -> tuple:
    confidence = _confidence_rank(str(action.get("confidence", "") or ""))
    weight_range = _parse_target_weight_range(action.get("target_weight") or action.get("target_weight_range"), str(action.get("action_label", "") or ""))
    top_weight = weight_range[1] if weight_range else 0
    return top_weight, confidence, str(action.get("code", ""))


def apply_candidate_mutations(
    actions: Iterable[Mapping[str, Any]],
    *,
    rule_overrides: Mapping[str, Any],
    parameter_overrides: Mapping[str, Any],
    portfolio_overrides: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    confidence_min = str(rule_overrides.get("confidence_min", "") or "").strip()
    confidence_floor = _confidence_rank(confidence_min) if confidence_min else 0
    blocked_clusters = _parse_blocklist(rule_overrides.get("cluster_blocklist"))
    degrade_holds_in_defense = str(rule_overrides.get("hold_in_defense", "") or "").strip() == "degrade"
    lookback_window = _parse_lookback_window(parameter_overrides.get("lookback_window"))
    drawdown_limit = _parse_drawdown_limit(parameter_overrides.get("drawdown_limit"))
    core_only = str(portfolio_overrides.get("core_only", "") or "").strip()
    risk_profile = str(portfolio_overrides.get("risk_profile", "") or "").strip().lower()
    watchlist_limit = int(portfolio_overrides.get("watchlist_limit", 0) or 0)

    risk_factor = 1.0
    if risk_profile == "balanced":
        risk_factor = 0.8
    elif risk_profile == "aggressive":
        risk_factor = 1.15

    mutated: List[Dict[str, Any]] = []
    for action in actions:
        item = dict(action)
        current_shares = _current_shares(item)
        forced_weight_range: Optional[Tuple[int, int]] = None
        if blocked_clusters and str(item.get("cluster", "") or "") in blocked_clusters:
            continue
        if confidence_floor and _confidence_rank(str(item.get("confidence", "") or "")) < confidence_floor:
            continue
        if (
            degrade_holds_in_defense
            and str(item.get("market_regime", "") or "") == "防守"
            and str(item.get("action_label", "") or "") == "持有"
        ):
            item["action_label"] = _degrade_action(str(item.get("action_label", "") or ""))
            forced_weight_range = _parse_target_weight_range(None, str(item.get("action_label", "") or ""))

        relative_return = _relative_return_for_window(item, lookback_window)
        if relative_return is not None and relative_return <= -0.05:
            item["action_label"] = _degrade_action(str(item.get("action_label", "") or ""))
            forced_weight_range = _parse_target_weight_range(None, str(item.get("action_label", "") or ""))

        drawdown_20 = item.get("drawdown_20")
        if (
            drawdown_limit is not None
            and isinstance(drawdown_20, (int, float))
            and float(drawdown_20) <= drawdown_limit
        ):
            if current_shares > 0:
                item["action_label"] = "减配"
                forced_weight_range = _parse_target_weight_range(None, "减配")
            else:
                item["action_label"] = "回避"
                forced_weight_range = (0, 0)

        target_weight = item.get("target_weight") or item.get("target_weight_range")
        weight_range = forced_weight_range or _parse_target_weight_range(
            target_weight,
            str(item.get("action_label", "") or ""),
        )
        if core_only and str(item.get("cluster", "") or "") != core_only:
            weight_range = (0, 0)
        weight_range = _scale_weight_range(weight_range, risk_factor)
        item["target_weight"] = _format_target_weight_range(weight_range)
        mutated.append(item)

    if watchlist_limit > 0:
        watchlist_items = [item for item in mutated if _current_shares(item) <= 0]
        keep_codes = {
            item["code"]
            for item in sorted(watchlist_items, key=_watchlist_rank, reverse=True)[:watchlist_limit]
        }
        for item in mutated:
            if _current_shares(item) > 0:
                continue
            if item.get("code") in keep_codes:
                continue
            item["target_weight"] = "0%"

    return mutated
