from __future__ import annotations

from typing import Dict


def apply_mode_gate(
    *,
    mode: str,
    candidate_action: str,
    setup_type: str,
    regime: str,
    offensive_allowed: bool,
) -> Dict[str, str]:
    candidate_action = str(candidate_action or "持有")

    if candidate_action == "增配":
        if mode == "midday":
            return {"final_action": "持有", "execution_window": "尾盘再确认"}
        if mode == "preclose":
            if offensive_allowed and regime in {"进攻", "均衡"} and setup_type in {"trend_follow", "pullback_resume"}:
                return {"final_action": "增配", "execution_window": "今日尾盘"}
            return {"final_action": "持有", "execution_window": "今日不动"}
        if mode == "close":
            if offensive_allowed and regime in {"进攻", "均衡"}:
                return {"final_action": "增配", "execution_window": "明日条件触发"}
            return {"final_action": "持有", "execution_window": "明日观察"}
        return {"final_action": "增配" if offensive_allowed else "持有", "execution_window": "下一交易日"}

    if candidate_action in {"减配", "回避"}:
        if mode == "close":
            return {"final_action": candidate_action, "execution_window": "明日条件触发"}
        if mode == "swing":
            return {"final_action": candidate_action, "execution_window": "下一交易日"}
        return {"final_action": candidate_action, "execution_window": "今日尾盘"}

    if mode == "preclose":
        return {"final_action": "持有", "execution_window": "今日不动"}
    if mode == "close":
        return {"final_action": "持有", "execution_window": "明日观察"}
    if mode == "midday":
        return {"final_action": "持有", "execution_window": "尾盘再确认"}
    return {"final_action": "持有", "execution_window": "下一交易日"}
