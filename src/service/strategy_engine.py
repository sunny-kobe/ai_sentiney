from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Set

from src.processor.swing_tracker import build_price_matrix, calculate_max_drawdown
from src.service.execution_gate import apply_mode_gate
from src.service.market_regime import classify_market_regime, infer_cluster
from src.service.performance_gate import build_default_performance_context, resolve_offensive_permission
from src.service.setup_classifier import classify_setup


BENCHMARK_CANDIDATES = {
    "broad_beta": ["159338", "510300", "510980"],
    "small_cap": ["510500", "563300", "159338", "510300"],
    "ai": ["159819", "588760", "159338", "510300"],
    "semiconductor": ["512480", "560780", "159338", "510300"],
    "precious_metals": ["159934", "159937", "159338", "510300"],
    "sector_etf": ["159338", "510300", "510980"],
    "single_name": ["159338", "510300", "510980"],
}
BROAD_BETA_CODES = ("159338", "510300", "510980")


def _window_return(prices: Sequence[float], window: int) -> Optional[float]:
    if len(prices) <= window:
        return None
    entry = float(prices[-(window + 1)])
    exit_price = float(prices[-1])
    if entry <= 0:
        return None
    return round((exit_price / entry) - 1, 4)


def _window_drawdown(prices: Sequence[float], window: int) -> Optional[float]:
    if len(prices) < 2:
        return None
    window_prices = list(prices[-(window + 1):]) if len(prices) > window else list(prices)
    if len(window_prices) < 2:
        return None
    return calculate_max_drawdown(window_prices)


def _build_price_timeline(matrix: Mapping[str, Any], code: str) -> list[float]:
    timeline = []
    for record_date in matrix.get("dates", []):
        price = (matrix.get("prices", {}) or {}).get(code, {}).get(record_date)
        if isinstance(price, (int, float)) and price > 0:
            timeline.append(float(price))
    return timeline


def resolve_benchmark_code(stock: Mapping[str, Any], available_codes: Set[str]) -> Optional[str]:
    code = str(stock.get("code", "") or "")
    cluster = infer_cluster(stock)
    candidate_codes = BENCHMARK_CANDIDATES.get(cluster, BENCHMARK_CANDIDATES["single_name"])

    for candidate in candidate_codes:
        if candidate == code:
            continue
        if candidate in available_codes:
            return candidate

    for candidate in BROAD_BETA_CODES:
        if candidate == code:
            continue
        if candidate in available_codes:
            return candidate

    return None


def build_benchmark_snapshot(
    stocks: Sequence[Mapping[str, Any]],
    historical_records: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    matrix = build_price_matrix(historical_records)
    available_codes = set((matrix.get("prices") or {}).keys())
    benchmark_snapshot: Dict[str, Dict[str, Any]] = {}

    for stock in stocks:
        code = str(stock.get("code", "") or "")
        if not code:
            continue

        benchmark_code = resolve_benchmark_code(stock, available_codes)
        asset_prices = _build_price_timeline(matrix, code)
        benchmark_prices = _build_price_timeline(matrix, benchmark_code) if benchmark_code else []

        asset_return_20 = _window_return(asset_prices, 20)
        asset_return_40 = _window_return(asset_prices, 40)
        benchmark_return_20 = _window_return(benchmark_prices, 20) if benchmark_prices else None
        benchmark_return_40 = _window_return(benchmark_prices, 40) if benchmark_prices else None
        relative_return_20 = (
            round(asset_return_20 - benchmark_return_20, 4)
            if asset_return_20 is not None and benchmark_return_20 is not None
            else None
        )
        relative_return_40 = (
            round(asset_return_40 - benchmark_return_40, 4)
            if asset_return_40 is not None and benchmark_return_40 is not None
            else None
        )

        benchmark_snapshot[code] = {
            "benchmark_code": benchmark_code,
            "relative_return_20": relative_return_20,
            "relative_return_40": relative_return_40,
            "drawdown_20": _window_drawdown(asset_prices, 20),
        }

    return benchmark_snapshot


def _target_range_for_action(final_action: str, setup_type: str, mode: str) -> str:
    if mode != "swing":
        if final_action == "增配":
            return "10%-15%" if setup_type == "pullback_resume" else "10%-20%"
        if final_action == "减配":
            return "10%-20%"
        if final_action == "回避":
            return "30%-50%"
        return "0%"

    if final_action == "增配":
        return "10%-20%"
    if final_action == "持有":
        return "5%-15%"
    if final_action == "减配":
        return "0%-5%"
    return "0%"


def _rebalance_instruction(final_action: str, execution_window: str, target_range: str) -> str:
    if final_action == "增配":
        if execution_window == "今日尾盘":
            return f"尾盘分批加仓{target_range}"
        if execution_window == "明日条件触发":
            return f"明日满足条件再分批加仓{target_range}"
        return f"下一交易日分批加仓{target_range}"
    if final_action == "减配":
        return f"{execution_window}减仓{target_range}"
    if final_action == "回避":
        return f"{execution_window}优先降到低风险状态"
    return "今日不动" if execution_window == "今日不动" else "继续持有，等待下一次确认"


def _invalid_condition(stock: Mapping[str, Any], setup_type: str) -> str:
    ma20 = float(stock.get("ma20", 0) or 0)
    current_price = float(stock.get("current_price", 0) or 0)
    if ma20 > 0:
        if setup_type in {"trend_follow", "pullback_resume"}:
            return f"放量跌回MA20({ma20:.2f})下方时，取消偏多判断"
        if setup_type in {"breakdown", "rebound_trap"}:
            return f"重新站回MA20({ma20:.2f})并连续走稳时，再撤销防守判断"
    return f"价格偏离当前结构 {current_price:.2f} 后再重新评估"


def _evidence_text(setup: Mapping[str, Any], stock: Mapping[str, Any]) -> str:
    parts = list(setup.get("evidence", []))
    return "；".join(part for part in parts if part)


def build_strategy_snapshot(
    ai_input: Mapping[str, Any],
    historical_records: Sequence[Mapping[str, Any]],
    mode: str,
    performance_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    stocks = ai_input.get("stocks", []) or []
    benchmark_snapshot = build_benchmark_snapshot(stocks, historical_records)
    regime_info = classify_market_regime(ai_input, historical_records)
    perf_context = dict(performance_context or build_default_performance_context())

    holdings = []
    for stock in stocks:
        code = str(stock.get("code", "") or "")
        setup = classify_setup(stock, benchmark_snapshot.get(code, {}))
        offensive_gate = resolve_offensive_permission(
            setup["setup_type"],
            perf_context,
            regime_info["offensive_allowed"],
        )
        mode_gate = apply_mode_gate(
            mode=mode,
            candidate_action=setup["candidate_action"],
            setup_type=setup["setup_type"],
            regime=regime_info["regime"],
            offensive_allowed=offensive_gate["allowed"],
        )
        target_range = _target_range_for_action(mode_gate["final_action"], setup["setup_type"], mode)
        holdings.append(
            {
                "code": code,
                "name": stock.get("name"),
                "cluster": infer_cluster(stock),
                "signal": stock.get("signal", "N/A"),
                "confidence": stock.get("confidence", ""),
                "setup_type": setup["setup_type"],
                "candidate_action": setup["candidate_action"],
                "final_action": mode_gate["final_action"],
                "evidence": setup.get("evidence", []),
                "evidence_text": _evidence_text(setup, stock),
                "invalid_condition": _invalid_condition(stock, setup["setup_type"]),
                "execution_window": mode_gate["execution_window"],
                "target_weight_range": target_range,
                "rebalance_instruction": _rebalance_instruction(mode_gate["final_action"], mode_gate["execution_window"], target_range),
                "gate_reason": offensive_gate["reason"],
                "current_price": float(stock.get("current_price", 0) or 0),
                "ma20": float(stock.get("ma20", 0) or 0),
                "pct_change": float(stock.get("pct_change", 0) or 0),
                "shares": int(stock.get("shares", 0) or 0),
                "tech_summary": stock.get("tech_summary", ""),
                "relative_return_20": benchmark_snapshot.get(code, {}).get("relative_return_20"),
                "relative_return_40": benchmark_snapshot.get(code, {}).get("relative_return_40"),
                "drawdown_20": benchmark_snapshot.get(code, {}).get("drawdown_20"),
            }
        )

    return {
        "mode": mode,
        "market_regime": regime_info["regime"],
        "action_bias": regime_info["action_bias"],
        "offensive_allowed": regime_info["offensive_allowed"],
        "market_drivers": regime_info["reasons"],
        "stressed_clusters": sorted(regime_info["stressed_clusters"]),
        "holdings": holdings,
        "performance_context": perf_context,
    }


def _market_sentiment_from_regime(regime: str) -> str:
    mapping = {
        "进攻": "风险偏好回升",
        "均衡": "分歧平衡",
        "防守": "防守优先",
        "撤退": "风险收缩",
    }
    return mapping.get(regime, "中性")


def _volume_label(ai_input: Mapping[str, Any], regime: str) -> str:
    indices = ai_input.get("indices", {}) or {}
    avg_change = 0.0
    if indices:
        values = [float(item.get("change_pct", 0) or 0) for item in indices.values() if isinstance(item, Mapping)]
        avg_change = sum(values) / len(values) if values else 0.0
    if regime == "撤退":
        return "放量回落" if avg_change <= -0.8 else "缩量偏弱"
    if regime == "进攻":
        return "放量修复" if avg_change >= 0.8 else "温和修复"
    if regime == "防守":
        return "承接偏弱"
    return "分歧整理"


def _support_resistance(holding: Mapping[str, Any]) -> tuple[float, float]:
    current_price = float(holding.get("current_price", 0) or 0)
    ma20 = float(holding.get("ma20", 0) or 0)
    if ma20 > 0:
        support = round(ma20 * 0.98, 2)
        resistance = round(max(current_price, ma20) * 1.03, 2)
    else:
        support = round(current_price * 0.97, 2)
        resistance = round(current_price * 1.03, 2)
    return support, resistance


def build_intraday_rule_report(
    ai_input: Mapping[str, Any],
    strategy_snapshot: Mapping[str, Any],
    *,
    mode: str,
    scorecard: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    holdings = strategy_snapshot.get("holdings", [])
    market_regime = str(strategy_snapshot.get("market_regime", "均衡"))
    actionable = [item for item in holdings if item.get("final_action") in {"减配", "回避", "增配"}]
    if not actionable:
        macro_summary = "整体建议：保持现有仓位不动，等待更清晰的确认信号。"
    else:
        action_names = "、".join(item.get("name", "") for item in actionable[:3] if item.get("name"))
        if mode == "preclose":
            macro_summary = f"整体建议：优先处理 {action_names}，其余仓位以不动为主。"
        else:
            macro_summary = f"当前先看风险与强弱分化，重点关注 {action_names}，主动加仓留到尾盘再确认。"

    actions = []
    for holding in holdings:
        reason = f"{holding.get('evidence_text', '')}。失效条件：{holding.get('invalid_condition', '')}"
        operation = holding.get("rebalance_instruction", "")
        if mode == "midday" and holding.get("final_action") == "增配":
            operation = "尾盘再确认，不盘中追高"
        actions.append(
            {
                "code": holding.get("code"),
                "name": holding.get("name"),
                "signal": holding.get("final_action"),
                "action": holding.get("final_action"),
                "operation": operation,
                "reason": reason,
                "news_impact": "无新增修正",
                "setup_type": holding.get("setup_type"),
                "execution_window": holding.get("execution_window"),
                "target_weight_range": holding.get("target_weight_range"),
            }
        )

    result = {
        "market_sentiment": _market_sentiment_from_regime(market_regime),
        "volume_analysis": _volume_label(ai_input, market_regime),
        "macro_summary": macro_summary,
        "bull_case": "",
        "bear_case": "",
        "actions": actions,
        "strategy_snapshot": strategy_snapshot,
    }
    if scorecard:
        result["signal_scorecard"] = scorecard
    return result


def build_close_rule_report(
    ai_input: Mapping[str, Any],
    strategy_snapshot: Mapping[str, Any],
    *,
    scorecard: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    holdings = strategy_snapshot.get("holdings", [])
    market_regime = str(strategy_snapshot.get("market_regime", "均衡"))
    actions = []
    for holding in holdings:
        support, resistance = _support_resistance(holding)
        final_action = holding.get("final_action")
        if final_action == "增配":
            tomorrow_plan = f"若明日回踩不破MA20，可分批加仓{holding.get('target_weight_range')}; {holding.get('invalid_condition')}"
        elif final_action == "减配":
            tomorrow_plan = f"若明日继续走弱，优先减仓{holding.get('target_weight_range')}; {holding.get('invalid_condition')}"
        elif final_action == "回避":
            tomorrow_plan = f"明日优先继续降到低风险状态; {holding.get('invalid_condition')}"
        else:
            tomorrow_plan = f"优先持有观察，不急着加减; {holding.get('invalid_condition')}"

        actions.append(
            {
                "code": holding.get("code"),
                "name": holding.get("name"),
                "signal": final_action,
                "today_review": holding.get("evidence_text", ""),
                "tomorrow_plan": tomorrow_plan,
                "support_level": support,
                "resistance_level": resistance,
                "setup_type": holding.get("setup_type"),
            }
        )

    result = {
        "market_summary": f"当前属于{market_regime}环境，收盘后以条件计划为主，不做盘中式追单判断。",
        "market_temperature": _market_sentiment_from_regime(market_regime),
        "bull_case": "",
        "bear_case": "",
        "actions": actions,
        "strategy_snapshot": strategy_snapshot,
    }
    if scorecard:
        result["signal_scorecard"] = scorecard
    return result
