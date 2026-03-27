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
VALIDATION_MIN_SAMPLE = 5
WEAK_VALIDATION_RELATIVE = -0.02
WEAK_VALIDATION_DRAWDOWN = -0.08
CLUSTER_LABELS = {
    "ai": "人工智能方向",
    "broad_beta": "大盘核心方向",
    "small_cap": "中小盘方向",
    "semiconductor": "半导体方向",
    "precious_metals": "贵金属方向",
    "sector_etf": "行业轮动方向",
    "single_name": "个股方向",
}


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


def _is_weak_validation_stats(stats: Mapping[str, Any]) -> bool:
    sample_count = int(stats.get("sample_count", 0) or 0)
    avg_relative = stats.get("avg_relative_return")
    avg_drawdown = float(stats.get("avg_max_drawdown", 0.0) or 0.0)
    return sample_count >= VALIDATION_MIN_SAMPLE and (
        (avg_relative is not None and float(avg_relative) <= WEAK_VALIDATION_RELATIVE)
        or avg_drawdown <= WEAK_VALIDATION_DRAWDOWN
    )


def _validation_note_for_item(item: Mapping[str, Any], decision_evidence: Mapping[str, Any]) -> str:
    if decision_evidence and decision_evidence.get("offensive_allowed") is False:
        reason = str(decision_evidence.get("offensive_reason", "验证暂不支持主动进攻") or "验证暂不支持主动进攻")
        return f"当前全局进攻权限关闭：{reason}。"

    primary_window = decision_evidence.get("primary_window")
    cluster = str(item.get("cluster", "") or "")
    cluster_stats = ((decision_evidence.get("cluster") or {}).get(cluster)) or {}
    if not primary_window or not cluster_stats:
        return ""

    cluster_label = CLUSTER_LABELS.get(cluster, cluster or "该方向")
    avg_relative = cluster_stats.get("avg_relative_return")
    relative_text = (
        f"平均跑赢基准{float(avg_relative) * 100:.1f}%"
        if isinstance(avg_relative, (int, float)) and float(avg_relative) >= 0
        else f"平均落后基准{abs(float(avg_relative or 0.0)) * 100:.1f}%"
    )
    drawdown = abs(float(cluster_stats.get("avg_max_drawdown", 0.0) or 0.0)) * 100
    if _is_weak_validation_stats(cluster_stats):
        return (
            f"{cluster_label}的{int(primary_window)}日验证偏弱，样本"
            f"{int(cluster_stats.get('sample_count', 0) or 0)}笔，{relative_text}，回撤约{drawdown:.1f}%。"
        )
    return ""


def build_watchlist_candidates(
    holdings: Sequence[Mapping[str, Any]],
    *,
    held_codes: Set[str],
    watchlist_codes: Set[str],
    strategy_preferences: Mapping[str, Any],
    market_regime: str,
    decision_evidence: Mapping[str, Any] | None = None,
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
        validation_note = _validation_note_for_item(item, decision_evidence or {})
        if validation_note and action_label == "进入试仓区":
            action_label = "继续观察"
            if (decision_evidence or {}).get("offensive_allowed") is False:
                plan = "进攻权限恢复前先不试仓，继续观察，等验证重新转强后再考虑。"
            else:
                plan = "验证暂时不支持直接试仓，先继续观察，等该方向样本修复后再考虑。"
        else:
            plan = item.get("rebalance_instruction", "继续观察")
        candidates.append(
            {
                "code": code,
                "name": item.get("name", code),
                "signal": item.get("signal", ""),
                "confidence": item.get("confidence", ""),
                "action_label": action_label,
                "reason": item.get("evidence_text", "") or item.get("tech_summary", ""),
                "plan": plan,
                "risk_line": item.get("invalid_condition", ""),
                "validation_note": validation_note,
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
