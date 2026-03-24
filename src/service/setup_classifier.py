from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _is_strong_relative(relative_20: Optional[float], relative_40: Optional[float]) -> bool:
    return (relative_20 is not None and relative_20 >= 0.05) or (relative_40 is not None and relative_40 >= 0.08)


def _is_weak_relative(relative_20: Optional[float], relative_40: Optional[float]) -> bool:
    return (relative_20 is not None and relative_20 <= -0.05) or (relative_40 is not None and relative_40 <= -0.08)


def classify_setup(stock: Mapping[str, Any], benchmark_snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    signal = str(stock.get("signal", "SAFE")).upper()
    current_price = float(stock.get("current_price", 0) or 0)
    ma20 = float(stock.get("ma20", 0) or 0)
    pct_change = float(stock.get("pct_change", 0) or 0)
    bias_pct = float(stock.get("bias_pct", 0) or 0)

    macd = stock.get("macd", {}) or {}
    obv = stock.get("obv", {}) or {}
    relative_return_20 = benchmark_snapshot.get("relative_return_20")
    relative_return_40 = benchmark_snapshot.get("relative_return_40")

    price_above_ma20 = ma20 > 0 and current_price >= ma20
    near_ma20 = ma20 > 0 and abs(current_price - ma20) / ma20 <= 0.02
    strong_relative = _is_strong_relative(relative_return_20, relative_return_40)
    weak_relative = _is_weak_relative(relative_return_20, relative_return_40)
    obv_inflow = str(obv.get("trend", "UNKNOWN")).upper() == "INFLOW"
    obv_outflow = str(obv.get("trend", "UNKNOWN")).upper() == "OUTFLOW"
    macd_trend = str(macd.get("trend", "UNKNOWN")).upper()
    macd_power = str(macd.get("power", "UNKNOWN")).upper()
    bottom_div = str(macd.get("divergence", "NONE")).upper() == "BOTTOM_DIV"
    bearish_macd = macd_trend in {"BEARISH", "DEATH_CROSS"} or macd_power in {"WEAK", "SUPER_WEAK"}
    bullish_macd = macd_trend in {"BULLISH", "GOLDEN_CROSS"} and macd_power in {"STRONG", "SUPER_STRONG", "UNKNOWN"}

    evidence = []

    if price_above_ma20:
        evidence.append("价格站在MA20上方")
    elif ma20 > 0:
        evidence.append("价格仍在MA20下方")

    if strong_relative:
        evidence.append("相对基准更强")
    elif weak_relative:
        evidence.append("相对基准偏弱")

    if obv_inflow:
        evidence.append("资金承接仍在")
    elif obv_outflow:
        evidence.append("资金流出明显")

    if bottom_div:
        evidence.append("出现底背驰修复线索")

    if obv_inflow and bearish_macd and not weak_relative:
        evidence.append("量能与趋势证据冲突")
        return {"setup_type": "conflict", "evidence": evidence or ["证据冲突，先不主动出手"], "candidate_action": "持有"}

    if (near_ma20 or bottom_div or bias_pct <= 0.02) and (near_ma20 or price_above_ma20) and obv_inflow and (signal in {"ACCUMULATE", "OPPORTUNITY", "SAFE"} or bottom_div) and not weak_relative:
        return {"setup_type": "pullback_resume", "evidence": evidence or ["回踩后有企稳迹象"], "candidate_action": "增配"}

    if not price_above_ma20 and pct_change > 0 and (signal in {"WARNING", "DANGER", "WATCH", "OBSERVED"} or weak_relative or bearish_macd):
        return {"setup_type": "rebound_trap", "evidence": evidence or ["只是反抽，未重新转强"], "candidate_action": "减配"}

    if price_above_ma20 and (signal in {"SAFE", "OPPORTUNITY", "ACCUMULATE"} or bullish_macd) and not weak_relative:
        return {"setup_type": "trend_follow", "evidence": evidence or ["主趋势仍在"], "candidate_action": "增配" if strong_relative and signal in {"OPPORTUNITY", "ACCUMULATE"} else "持有"}

    if not price_above_ma20 and (signal in {"DANGER", "WARNING", "LOCKED_DANGER"} or weak_relative) and (obv_outflow or bearish_macd or bias_pct <= -0.03):
        return {"setup_type": "breakdown", "evidence": evidence or ["趋势破坏"], "candidate_action": "回避" if weak_relative and bias_pct <= -0.05 else "减配"}

    if signal in {"WATCH", "OBSERVED", "OVERBOUGHT"}:
        evidence.append("当前更适合继续观察")

    return {"setup_type": "conflict", "evidence": evidence or ["证据冲突，先不主动出手"], "candidate_action": "持有"}
