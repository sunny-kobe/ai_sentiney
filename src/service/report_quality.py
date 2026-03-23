from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def _normalize_now(now: Optional[str]) -> str:
    if now:
        return now
    return datetime.now().strftime("%Y-%m-%d")


def evaluate_input_quality(ai_input: Dict[str, Any], mode: str, now: Optional[str] = None) -> Dict[str, Any]:
    issues: List[str] = []
    status = "normal"
    current_day = _normalize_now(now)
    context_date = ai_input.get("context_date")

    if mode in ("midday", "close"):
        stocks = ai_input.get("stocks", [])
        if not stocks:
            issues.append("missing_stocks")
            status = "blocked"

    if context_date and context_date != current_day and status != "blocked":
        issues.append("stale_context")
        status = "degraded"

    if mode in ("midday", "close") and status != "blocked":
        macro_news = ai_input.get("macro_news", {}).get("telegraph", [])
        stock_news = [n for stock in ai_input.get("stocks", []) for n in stock.get("news", [])]
        if not macro_news and not stock_news:
            issues.append("missing_evidence")
            status = "degraded"

    return {
        "status": status,
        "issues": issues,
    }


def evaluate_output_quality(analysis_result: Dict[str, Any], structured_report: Dict[str, Any], mode: str) -> Dict[str, Any]:
    issues: List[str] = []
    expected_codes = {stock.get("code") for stock in structured_report.get("stocks", []) if stock.get("code")}
    actual_codes = {action.get("code") for action in analysis_result.get("actions", []) if action.get("code")}

    if expected_codes and actual_codes != expected_codes:
        issues.append("incomplete_action_coverage")

    return {
        "status": "degraded" if issues else "normal",
        "issues": issues,
    }
