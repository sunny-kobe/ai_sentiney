from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def gate_offensive_setup(stats: Mapping[str, Any]) -> Dict[str, Any]:
    count = int(stats.get("count", 0) or 0)
    avg_relative_return = stats.get("avg_relative_return")
    avg_max_drawdown = float(stats.get("avg_max_drawdown", 0) or 0)

    if count < 5:
        return {"allowed": False, "reason": "样本不足"}
    if avg_relative_return is None or float(avg_relative_return) <= 0:
        return {"allowed": False, "reason": "近期超额收益不达标"}
    if avg_max_drawdown <= -0.08:
        return {"allowed": False, "reason": "近期回撤过大"}
    return {"allowed": True, "reason": "近期进攻统计仍有效"}


def build_default_performance_context() -> Dict[str, Any]:
    conservative = gate_offensive_setup({"count": 0, "avg_relative_return": None, "avg_max_drawdown": 0})
    return {
        "offensive": {
            "trend_follow": {"allowed": True, "reason": "强趋势延续默认允许持有"},
            "pullback_resume": conservative,
        }
    }


def resolve_offensive_permission(
    setup_type: str,
    performance_context: Optional[Mapping[str, Any]],
    regime_offensive_allowed: bool,
) -> Dict[str, Any]:
    if not regime_offensive_allowed:
        return {"allowed": False, "reason": "当前市场阶段不支持主动进攻"}

    context = performance_context or build_default_performance_context()
    setup_gate = ((context.get("offensive") or {}).get(setup_type) or {})
    if not setup_gate:
        return {"allowed": False, "reason": "该 setup 没有进攻授权"}
    return {"allowed": bool(setup_gate.get("allowed")), "reason": str(setup_gate.get("reason", ""))}
