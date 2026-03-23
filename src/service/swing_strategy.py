from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set


ACTION_ORDER = ["增配", "持有", "减配", "回避", "观察"]
RISK_CLUSTERS = {"small_cap", "ai", "semiconductor"}

SIGNAL_SCORES = {
    "OPPORTUNITY": 3,
    "ACCUMULATE": 2,
    "SAFE": 0,
    "HOLD": 0,
    "WATCH": -1,
    "OBSERVED": -1,
    "OVERBOUGHT": -2,
    "WARNING": -2,
    "DANGER": -3,
    "LOCKED_DANGER": -3,
    "LIMIT_DOWN": -3,
}

ACTION_PLANS = {
    "增配": "只做分批加，不追高，优先把仓位放到最强的一档。",
    "持有": "先把现有仓位拿住，等下一次确认转强再决定要不要加。",
    "减配": "先收缩一部分仓位，把组合波动降下来。",
    "回避": "先收缩到低风险状态，没有重新站稳前不急着回去。",
    "观察": "先看，不急着动，等方向更清楚再决定。",
}

SIGNAL_PHRASES = {
    "OPPORTUNITY": "已经重新转强",
    "ACCUMULATE": "回踩后有企稳迹象",
    "SAFE": "主趋势还在",
    "HOLD": "主趋势还在",
    "WATCH": "还没确认重新走强",
    "OBSERVED": "方向暂时不清楚",
    "OVERBOUGHT": "短线有点过热",
    "WARNING": "已经开始转弱",
    "DANGER": "趋势明显破位",
    "LOCKED_DANGER": "趋势明显破位",
    "LIMIT_DOWN": "风险集中释放",
}

REGIME_CONCLUSIONS = {
    "进攻": "当前偏进攻，可以把仓位集中到最强方向，但继续分批，不追高。",
    "均衡": "当前偏均衡，核心仓先稳住，只对最强方向做小幅调整。",
    "防守": "当前偏防守，先守住已有成果，弱势方向以收缩仓位为主。",
    "撤退": "当前进入撤退阶段，先把高波动方向降下来，等市场重新企稳再回来。",
}


def infer_cluster(stock: Mapping[str, Any]) -> str:
    name = str(stock.get("name", ""))
    code = str(stock.get("code", ""))

    if "中证2000" in name or "中证500" in name or code in {"510500", "563300"}:
        return "small_cap"
    if "人工智能" in name or code in {"159819", "588760"}:
        return "ai"
    if "半导体" in name or code in {"512480", "560780"}:
        return "semiconductor"
    if any(keyword in name for keyword in ("黄金", "白银", "紫金", "资源")):
        return "precious_metals"
    if any(keyword in name for keyword in ("沪深300", "A500", "上证")) or code in {"510300", "159338", "510980"}:
        return "broad_beta"
    if "ETF" in name:
        return "sector_etf"
    return "single_name"


def _parse_breadth_score(market_breadth: str) -> int:
    numbers = [int(item) for item in re.findall(r"\d+", market_breadth or "")]
    if len(numbers) < 2:
        return 0

    up_count, down_count = numbers[0], numbers[1]
    spread = up_count - down_count
    if spread >= 1200:
        return 1
    if spread <= -1200:
        return -1
    return 0


def _history_momentum_score(historical_records: Sequence[Mapping[str, Any]]) -> int:
    price_paths: Dict[str, List[float]] = {}
    for record in historical_records:
        stocks = (record.get("raw_data") or {}).get("stocks", []) or []
        for stock in stocks:
            code = stock.get("code")
            price = stock.get("current_price")
            if code and isinstance(price, (int, float)) and price > 0:
                price_paths.setdefault(code, []).append(float(price))

    if not price_paths:
        return 0

    returns = []
    for prices in price_paths.values():
        if len(prices) < 2:
            continue
        returns.append((prices[-1] / prices[0]) - 1)

    if not returns:
        return 0

    average_return = sum(returns) / len(returns)
    if average_return >= 0.03:
        return 1
    if average_return <= -0.03:
        return -1
    return 0


def _news_score(news_items: Iterable[str]) -> int:
    positive_keywords = ("回暖", "修复", "企稳", "改善", "增持", "突破")
    negative_keywords = ("暴跌", "关税", "避险", "升级", "下修", "减持")
    score = 0

    for item in news_items:
        text = str(item)
        if any(keyword in text for keyword in negative_keywords):
            score -= 1
        elif any(keyword in text for keyword in positive_keywords):
            score += 1

    if score > 0:
        return 1
    if score < 0:
        return -1
    return 0


def _detect_stressed_clusters(stocks: Sequence[Mapping[str, Any]]) -> Set[str]:
    stressed = set()
    for stock in stocks:
        cluster = infer_cluster(stock)
        if cluster not in RISK_CLUSTERS:
            continue

        signal = str(stock.get("signal", "SAFE")).upper()
        bias_pct = float(stock.get("bias_pct", 0) or 0)
        pct_change = float(stock.get("pct_change", 0) or 0)
        if signal in {"DANGER", "WARNING", "LOCKED_DANGER"} or bias_pct <= -0.03 or pct_change <= -2:
            stressed.add(cluster)
    return stressed


def classify_market_regime(ai_input: Mapping[str, Any], historical_records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    indices = ai_input.get("indices", {}) or {}
    change_values = [
        float(data.get("change_pct", 0) or 0)
        for data in indices.values()
        if isinstance(data, Mapping)
    ]
    average_change = sum(change_values) / len(change_values) if change_values else 0.0

    score = 0
    reasons: List[str] = []

    if average_change >= 1.0:
        score += 2
        reasons.append("指数同步走强")
    elif average_change >= 0.3:
        score += 1
        reasons.append("指数偏强")
    elif average_change <= -2.0:
        score -= 3
        reasons.append("指数快速走弱")
    elif average_change <= -0.8:
        score -= 1
        reasons.append("指数偏弱")

    breadth_score = _parse_breadth_score(str(ai_input.get("market_breadth", "")))
    if breadth_score > 0:
        reasons.append("市场宽度在改善")
    elif breadth_score < 0:
        reasons.append("下跌家数明显更多")
    score += breadth_score

    history_score = _history_momentum_score(historical_records)
    if history_score > 0:
        reasons.append("近几天趋势向上")
    elif history_score < 0:
        reasons.append("近几天趋势向下")
    score += history_score

    news_score = _news_score((ai_input.get("macro_news", {}) or {}).get("telegraph", []) or [])
    if news_score > 0:
        reasons.append("消息面偏暖")
    elif news_score < 0:
        reasons.append("消息面偏空")
    score += news_score

    stressed_clusters = _detect_stressed_clusters(ai_input.get("stocks", []) or [])
    if len(stressed_clusters) >= 2:
        score -= 1
        reasons.append("高弹性板块联动走弱")

    if score >= 3:
        regime = "进攻"
    elif score >= 0:
        regime = "均衡"
    elif score >= -3:
        regime = "防守"
    else:
        regime = "撤退"

    return {
        "regime": regime,
        "score": score,
        "reasons": reasons,
        "stressed_clusters": stressed_clusters,
    }


def _label_from_score(score: int) -> str:
    if score >= 5:
        return "增配"
    if score >= 2:
        return "持有"
    if score >= 0:
        return "观察"
    if score <= -5:
        return "回避"
    if score <= -2:
        return "减配"
    return "观察"


def score_holding(stock: Mapping[str, Any], benchmark_context: Mapping[str, Any]) -> Dict[str, Any]:
    signal = str(stock.get("signal", "SAFE")).upper()
    cluster = infer_cluster(stock)
    regime = str(benchmark_context.get("regime", "均衡"))
    stressed_clusters = set(benchmark_context.get("stressed_clusters", set()) or set())

    score = SIGNAL_SCORES.get(signal, 0)

    bias_pct = float(stock.get("bias_pct", 0) or 0)
    if bias_pct >= 0.02:
        score += 1
    elif bias_pct <= -0.02:
        score -= 1

    macd_trend = str((stock.get("macd") or {}).get("trend", "UNKNOWN")).upper()
    if macd_trend in {"BULLISH", "GOLDEN_CROSS"}:
        score += 1
    elif macd_trend in {"BEARISH", "DEATH_CROSS"}:
        score -= 1

    obv_trend = str((stock.get("obv") or {}).get("trend", "UNKNOWN")).upper()
    if obv_trend == "INFLOW":
        score += 1
    elif obv_trend == "OUTFLOW":
        score -= 1

    if regime == "进攻" and cluster in RISK_CLUSTERS and signal in {"OPPORTUNITY", "ACCUMULATE"}:
        score += 1
    elif regime == "防守" and cluster in RISK_CLUSTERS:
        score -= 1
    elif regime == "撤退":
        score -= 1
        if cluster in RISK_CLUSTERS:
            score -= 1

    if cluster in stressed_clusters:
        score -= 1

    action_label = _label_from_score(score)
    current_price = float(stock.get("current_price", 0) or 0)
    ma20 = float(stock.get("ma20", 0) or 0)

    if ma20 > 0 and current_price >= ma20:
        position_phrase = f"还站在20日线 {ma20:.2f} 上方"
        risk_line = f"收盘跌回20日线 {ma20:.2f} 下方，就先缩仓。"
    else:
        position_phrase = f"已经落到20日线 {ma20:.2f} 下方"
        risk_line = f"不能重新站上20日线 {ma20:.2f} 之前，先别加仓。"

    flow_phrase = "承接还在配合" if obv_trend == "INFLOW" else "承接偏弱"
    reason = f"{position_phrase}，{SIGNAL_PHRASES.get(signal, '方向还不明朗')}，{flow_phrase}。"

    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "cluster": cluster,
        "signal": signal,
        "confidence": stock.get("confidence", ""),
        "action_label": action_label,
        "conclusion": action_label,
        "operation": action_label,
        "reason": reason,
        "plan": ACTION_PLANS[action_label],
        "risk_line": risk_line,
        "technical_evidence": stock.get("tech_summary", ""),
        "current_price": current_price,
        "ma20": ma20,
    }


def apply_cluster_risk_overlay(
    decisions: Sequence[Mapping[str, Any]],
    stressed_clusters: Set[str],
) -> List[Dict[str, Any]]:
    if len(stressed_clusters & RISK_CLUSTERS) < 2:
        return [dict(item) for item in decisions]

    downgrade_map = {
        "增配": "持有",
        "持有": "观察",
        "观察": "减配",
        "减配": "回避",
        "回避": "回避",
    }

    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        if updated.get("cluster") in stressed_clusters and updated.get("cluster") in RISK_CLUSTERS:
            updated["action_label"] = downgrade_map.get(updated["action_label"], updated["action_label"])
            updated["conclusion"] = updated["action_label"]
            updated["operation"] = updated["action_label"]
            updated["plan"] = ACTION_PLANS[updated["action_label"]]
            updated["reason"] = f"{updated['reason']} 板块联动走弱，先把动作降一级。"
        adjusted.append(updated)
    return adjusted


def build_swing_report(
    ai_input: Mapping[str, Any],
    historical_records: Sequence[Mapping[str, Any]],
    analysis_date: str,
) -> Dict[str, Any]:
    regime_info = classify_market_regime(ai_input, historical_records)
    context = {
        "regime": regime_info["regime"],
        "stressed_clusters": regime_info["stressed_clusters"],
    }

    decisions = [score_holding(stock, context) for stock in ai_input.get("stocks", []) or []]
    decisions = apply_cluster_risk_overlay(decisions, regime_info["stressed_clusters"])

    ordered_actions = sorted(
        decisions,
        key=lambda item: (ACTION_ORDER.index(item["action_label"]), str(item.get("name", ""))),
    )
    portfolio_actions = {label: [] for label in ACTION_ORDER}
    for decision in ordered_actions:
        portfolio_actions[decision["action_label"]].append(decision)

    technical_evidence = [
        {
            "code": stock.get("code"),
            "name": stock.get("name"),
            "signal": stock.get("signal"),
            "confidence": stock.get("confidence", ""),
            "tech_summary": stock.get("tech_summary", ""),
        }
        for stock in ai_input.get("stocks", []) or []
    ]

    return {
        "mode": "swing",
        "analysis_date": analysis_date,
        "market_regime": regime_info["regime"],
        "market_conclusion": REGIME_CONCLUSIONS[regime_info["regime"]],
        "market_drivers": regime_info["reasons"],
        "portfolio_actions": portfolio_actions,
        "actions": ordered_actions,
        "technical_evidence": technical_evidence,
    }
