"""
公共上下文构建模块
从市场数据构建 AI 分析所需的结构化 JSON 上下文。
消除 GeminiClient、HybridAIClient 之间的重复上下文构建逻辑。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def build_intraday_context(market_data: Dict[str, Any]) -> str:
    """
    构建盘中/收盘分析的结构化上下文 JSON 字符串。

    与 GeminiClient._build_intraday_context_json + _build_context 等价，
    与 HybridAIClient._build_structured_context 等价。

    Args:
        market_data: 市场数据字典

    Returns:
        JSON 字符串，可直接拼入 prompt
    """
    structured_report = market_data.get("structured_report")
    if structured_report:
        return json.dumps(
            {"Structured_Report": structured_report},
            ensure_ascii=False,
            indent=1,
        )

    market_breadth = market_data.get('market_breadth', "Unknown")
    north_funds = market_data.get('north_funds', 0.0)
    portfolio = market_data.get('stocks', [])
    indices = market_data.get('indices', {})
    macro_news = market_data.get('macro_news', {})
    yesterday_context = market_data.get('yesterday_context')
    scorecard = market_data.get('signal_scorecard')
    context_date = market_data.get('context_date')

    return _build_context(
        market_breadth=market_breadth,
        north_funds=north_funds,
        indices=indices,
        macro_news=macro_news,
        portfolio=portfolio,
        yesterday_context=yesterday_context,
        scorecard=scorecard,
        context_date=context_date,
    )


def _build_context(
    market_breadth: str,
    north_funds: float,
    indices: Dict,
    macro_news: Dict,
    portfolio: List[Dict],
    yesterday_context: Optional[Dict] = None,
    scorecard: Optional[Dict] = None,
    context_date: Optional[str] = None,
) -> str:
    """构造盘中分析的 prompt 上下文（精简版，节省 token）。"""
    portfolio_summary = []
    for stock in portfolio:
        entry = {
            "Code": stock.get('code', ''),
            "Name": stock.get('name', ''),
            "Price": stock.get('current_price', 0),
            "Change": f"{stock.get('pct_change', 0)}%",
            "MA20": stock.get('ma20', 0),
            "Bias": f"{round(stock.get('bias_pct', 0) * 100, 2)}%",
            "Signal": stock.get('signal', 'N/A'),
            "Confidence": stock.get('confidence', '中'),
            "Tech": stock.get('tech_summary', ''),
        }
        news = stock.get('news', [])
        if news:
            entry["News"] = news[:3]
        portfolio_summary.append(entry)

    context = {
        "Date": context_date or datetime.now().strftime('%Y-%m-%d'),
        "Market_Breadth": market_breadth,
        "North_Money": north_funds,
        "Indices": {
            name: f"{'+' if d.get('change_pct', 0) > 0 else ''}{d.get('change_pct', 0)}%"
            for name, d in indices.items()
        },
        "Portfolio": portfolio_summary,
    }

    telegraph = macro_news.get("telegraph", [])
    ai_tech = macro_news.get("ai_tech", [])
    if telegraph or ai_tech:
        context["News"] = {}
        if telegraph:
            context["News"]["财联社"] = telegraph[:5]
        if ai_tech:
            context["News"]["AI科技"] = ai_tech[:3]

    if yesterday_context:
        context["Yesterday_Plan"] = [
            {
                "code": a.get("code"),
                "plan": a.get("tomorrow_plan", a.get("operation", "")),
            }
            for a in yesterday_context.get('actions', [])
        ]

    if scorecard:
        context["Signal_Track_Record"] = {
            "summary": scorecard.get("summary_text", ""),
            "yesterday": [
                {
                    "code": e["code"],
                    "signal": e["yesterday_signal"],
                    "change": f"{e['today_change']}%",
                    "result": e["result"],
                }
                for e in scorecard.get("yesterday_evaluation", [])
                if e["result"] != "NEUTRAL"
            ],
        }

    return json.dumps(context, ensure_ascii=False, indent=1)


def build_morning_context(morning_data: Dict[str, Any]) -> str:
    """
    构建早报分析的结构化上下文 JSON 字符串。

    与 GeminiClient._build_morning_context 等价，
    与 HybridAIClient._build_morning_context 等价。

    Args:
        morning_data: 早报市场数据

    Returns:
        JSON 字符串
    """
    portfolio_summary = []
    for stock in morning_data.get('stocks', []):
        portfolio_summary.append({
            "Code": stock.get('code'),
            "Name": stock.get('name'),
            "Last_Close": stock.get('last_close', 0),
            "MA20": stock.get('ma20', 0),
            "Bias": f"{round(stock.get('bias_pct', 0) * 100, 2)}%",
            "MA20_Status": stock.get('ma20_status', 'NEAR'),
            "Overnight_Drivers": stock.get('overnight_driver_str', ''),
            "Opening_Expectation": stock.get('opening_expectation', 'FLAT'),
        })

    context = {
        "Date": morning_data.get('context_date') or datetime.now().strftime('%Y-%m-%d'),
        "Global_Indices": morning_data.get('global_indices', []),
        "Commodities": morning_data.get('commodities', []),
        "US_Treasury": morning_data.get('us_treasury', {}),
        "Macro_News": {
            "财联社电报": morning_data.get('macro_news', {}).get("telegraph", []),
            "AI科技热点": morning_data.get('macro_news', {}).get("ai_tech", []),
        },
        "Portfolio": portfolio_summary,
    }
    return json.dumps(context, ensure_ascii=False, indent=2)
