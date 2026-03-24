from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence


SWING_PREFERENCE_KEYS = (
    "risk_profile",
    "candidate_limit",
    "max_watchlist_adds_per_day",
    "max_single_position",
    "max_total_exposure",
    "min_cash_buffer",
    "max_satellite_positions",
)


def _normalize_asset(item: Mapping[str, Any], *, held: bool) -> Dict[str, Any]:
    normalized = dict(item)
    normalized["code"] = str(item.get("code", "") or "")
    normalized["name"] = str(item.get("name", normalized["code"]) or normalized["code"])
    normalized["strategy"] = str(item.get("strategy", "trend") or "trend")
    normalized["shares"] = int(item.get("shares", 0) or 0) if held else 0
    normalized["held"] = held
    normalized["priority"] = str(item.get("priority", "normal") or "normal")
    return normalized


def _extract_strategy_preferences(swing_config: Mapping[str, Any]) -> Dict[str, Any]:
    preferences: Dict[str, Any] = {}
    for key in SWING_PREFERENCE_KEYS:
        value = swing_config.get(key)
        if value is not None:
            preferences[key] = value
    return preferences


def build_investor_snapshot(
    *,
    portfolio: Sequence[Mapping[str, Any]],
    watchlist: Sequence[Mapping[str, Any]],
    portfolio_state: Mapping[str, Any],
    swing_config: Mapping[str, Any],
) -> Dict[str, Any]:
    holdings = [_normalize_asset(item, held=True) for item in portfolio if item.get("code")]
    held_codes = {item["code"] for item in holdings}

    candidates: List[Dict[str, Any]] = []
    for item in watchlist:
        code = str(item.get("code", "") or "")
        if not code or code in held_codes:
            continue
        candidates.append(_normalize_asset(item, held=False))

    return {
        "holdings": holdings,
        "watchlist": candidates,
        "universe": [*holdings, *candidates],
        "held_codes": held_codes,
        "watchlist_codes": {item["code"] for item in candidates},
        "portfolio_state": dict(portfolio_state or {}),
        "strategy_preferences": _extract_strategy_preferences(swing_config or {}),
    }
