from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set


RISK_CLUSTERS = {"small_cap", "ai", "semiconductor"}


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
    positive_keywords = ("回暖", "修复", "企稳", "改善", "增持", "突破", "护盘")
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


def _holdings_strength_score(stocks: Sequence[Mapping[str, Any]]) -> int:
    strong = 0
    weak = 0
    for stock in stocks:
        signal = str(stock.get("signal", "SAFE")).upper()
        current_price = float(stock.get("current_price", 0) or 0)
        ma20 = float(stock.get("ma20", 0) or 0)
        pct_change = float(stock.get("pct_change", 0) or 0)

        if signal in {"OPPORTUNITY", "ACCUMULATE"} or (ma20 > 0 and current_price >= ma20 and pct_change >= 0):
            strong += 1
        if signal in {"DANGER", "WARNING", "LOCKED_DANGER"} or (ma20 > 0 and current_price < ma20 and pct_change < 0):
            weak += 1

    if strong >= weak + 2:
        return 1
    if weak >= strong + 2:
        return -1
    return 0


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
        reasons.append("市场宽度改善")
    elif breadth_score < 0:
        reasons.append("下跌家数明显更多")
    score += breadth_score

    holdings_strength = _holdings_strength_score(ai_input.get("stocks", []) or [])
    if holdings_strength > 0:
        reasons.append("持仓整体强于弱势数量")
    elif holdings_strength < 0:
        reasons.append("持仓弱势数量占优")
    score += holdings_strength

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
        action_bias = "risk_on"
        offensive_allowed = True
    elif score >= 0:
        regime = "均衡"
        action_bias = "neutral"
        offensive_allowed = True
    elif score >= -3:
        regime = "防守"
        action_bias = "cautious"
        offensive_allowed = False
    else:
        regime = "撤退"
        action_bias = "risk_off"
        offensive_allowed = False

    return {
        "regime": regime,
        "score": score,
        "reasons": reasons,
        "stressed_clusters": stressed_clusters,
        "action_bias": action_bias,
        "offensive_allowed": offensive_allowed,
    }
