from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Set


SIGNAL_PRIORITY = {
    "OPPORTUNITY": 4,
    "ACCUMULATE": 3,
    "SAFE": 2,
    "HOLD": 2,
    "WATCH": 1,
    "OBSERVED": 1,
    "WARNING": 0,
    "DANGER": -1,
    "LOCKED_DANGER": -1,
    "LIMIT_DOWN": -2,
}
CONFIDENCE_PRIORITY = {"高": 2, "中": 1, "低": 0}
WATCHLIST_BUCKETS = ("转正式仓", "进入试仓区", "继续观察")


def _watchlist_rank(item: Mapping[str, Any]) -> int:
    signal = str(item.get("signal", "")).upper()
    confidence = str(item.get("confidence", "") or "")
    final_action = str(item.get("final_action", "观察"))
    action_bonus = 2 if final_action == "增配" else 1 if final_action == "持有" else 0
    return SIGNAL_PRIORITY.get(signal, 0) + CONFIDENCE_PRIORITY.get(confidence, 0) + action_bonus


def _candidate_action(item: Mapping[str, Any], market_regime: str) -> str:
    signal = str(item.get("signal", "")).upper()
    confidence = str(item.get("confidence", "") or "")
    final_action = str(item.get("final_action", "观察"))

    if market_regime == "撤退":
        return "继续观察"
    if final_action == "增配" and signal == "OPPORTUNITY" and confidence == "高" and market_regime == "进攻":
        return "进入试仓区"
    if final_action in {"增配", "持有"} and signal in {"OPPORTUNITY", "ACCUMULATE", "SAFE", "HOLD"} and market_regime in {"进攻", "均衡"}:
        return "进入试仓区"
    return "继续观察"


def build_watchlist_candidates(
    holdings: Sequence[Mapping[str, Any]],
    *,
    held_codes: Set[str],
    watchlist_codes: Set[str],
    strategy_preferences: Mapping[str, Any],
    market_regime: str,
) -> Dict[str, Any]:
    candidate_limit = int(strategy_preferences.get("candidate_limit", 3) or 3)
    daily_limit = int(strategy_preferences.get("max_watchlist_adds_per_day", candidate_limit) or candidate_limit)
    active_limit = max(min(candidate_limit, daily_limit), 0)

    candidates = []
    for item in holdings:
        code = str(item.get("code", "") or "")
        if not code or code in held_codes or code not in watchlist_codes:
            continue

        action_label = _candidate_action(item, market_regime)
        candidates.append(
            {
                "code": code,
                "name": item.get("name", code),
                "signal": item.get("signal", ""),
                "confidence": item.get("confidence", ""),
                "action_label": action_label,
                "reason": item.get("evidence_text", "") or item.get("tech_summary", ""),
                "plan": item.get("rebalance_instruction", "继续观察"),
                "risk_line": item.get("invalid_condition", ""),
                "rank_score": _watchlist_rank(item),
            }
        )

    candidates.sort(key=lambda item: (-item["rank_score"], item["code"]))

    promoted = 0
    for item in candidates:
        if item["action_label"] != "进入试仓区":
            continue
        if promoted >= active_limit:
            item["action_label"] = "继续观察"
            item["plan"] = "先留在观察池，等更好的位置或更强的确认后再考虑试仓。"
            continue
        promoted += 1

    action_buckets = {label: [] for label in WATCHLIST_BUCKETS}
    for item in candidates:
        action_buckets.setdefault(item["action_label"], []).append(item)

    active_candidates = [
        item for item in candidates if item["action_label"] in {"转正式仓", "进入试仓区"}
    ]

    return {
        "all_candidates": candidates,
        "active_candidates": active_candidates,
        "action_buckets": action_buckets,
    }
