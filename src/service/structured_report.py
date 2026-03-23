from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


SIGNAL_OPERATION_MAP = {
    "DANGER": "减仓30%-50%",
    "LOCKED_DANGER": "减仓30%-50%",
    "WARNING": "减仓10%-20%",
    "OVERBOUGHT": "减仓10%-20%",
    "WATCH": "持有观察",
    "OBSERVED": "持有观察",
    "SAFE": "持有观察",
    "HOLD": "持有观察",
    "OPPORTUNITY": "加仓20%-30%",
    "ACCUMULATE": "加仓10%-20%",
    "LIMIT_UP": "锁仓观察",
    "LIMIT_DOWN": "暂不操作",
    "N/A": "观望",
}


def map_signal_to_operation(signal: str, mode: str = "midday") -> str:
    return SIGNAL_OPERATION_MAP.get((signal or "N/A").upper(), "观望")


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def build_structured_report(ai_input: Dict[str, Any], mode: str, quality_status: str) -> Dict[str, Any]:
    data_timestamp = ai_input.get("context_date") or datetime.now().strftime("%Y-%m-%d")
    market_source_labels = ["rule_engine"]
    if ai_input.get("indices"):
        market_source_labels.append("indices")
    if ai_input.get("macro_news", {}).get("telegraph"):
        market_source_labels.append("macro_news")

    stocks = []
    top_level_sources = list(market_source_labels)
    for stock in ai_input.get("stocks", []):
        stock_sources = ["rule_engine"]
        news_evidence = stock.get("news", [])[:3]
        if news_evidence:
            stock_sources.append("stock_news")
            top_level_sources.append("stock_news")

        stocks.append({
            "code": stock.get("code"),
            "name": stock.get("name"),
            "signal": stock.get("signal", "N/A"),
            "confidence": stock.get("confidence", ""),
            "operation": map_signal_to_operation(stock.get("signal", "N/A"), mode=mode),
            "current_price": stock.get("current_price", 0.0),
            "pct_change": stock.get("pct_change", 0.0),
            "tech_evidence": stock.get("tech_summary", ""),
            "news_evidence": news_evidence,
            "source_labels": _dedupe(stock_sources),
            "data_timestamp": data_timestamp,
        })

    indices = ai_input.get("indices", {})
    indices_info = " / ".join(
        f"{name} {'+' if data.get('change_pct', 0) > 0 else ''}{data.get('change_pct', 0)}%"
        for name, data in indices.items()
    )

    return {
        "mode": mode,
        "quality_status": quality_status,
        "data_timestamp": data_timestamp,
        "source_labels": _dedupe(top_level_sources),
        "market": {
            "market_breadth": ai_input.get("market_breadth", "N/A"),
            "indices_info": indices_info,
            "macro_news_evidence": ai_input.get("macro_news", {}).get("telegraph", [])[:3],
            "data_timestamp": data_timestamp,
            "source_labels": _dedupe(market_source_labels),
        },
        "stocks": stocks,
    }
