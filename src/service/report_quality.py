from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

BLOCK_LABELS = {
    "stock_quotes": "实时行情",
    "stock_history": "历史走势",
    "market_breadth": "市场广度",
    "macro_news": "宏观消息",
    "indices": "指数快照",
    "north_funds": "北向资金",
    "stock_news": "个股新闻",
    "bulk_spot": "批量行情",
}
SWING_CORE_BLOCKS = ("stock_quotes", "stock_history")
SWING_SUPPORTING_BLOCKS = ("market_breadth", "macro_news", "indices", "north_funds", "stock_news")


def _normalize_now(now: Optional[str]) -> str:
    if now:
        return now
    return datetime.now().strftime("%Y-%m-%d")


def _is_non_fresh_block(block: Dict[str, Any]) -> bool:
    status = str((block or {}).get("status", "") or "").strip().lower()
    return status in {"missing", "degraded", "blocked"}


def _format_block_labels(block_names: List[str]) -> str:
    labels = [BLOCK_LABELS.get(name, name) for name in block_names]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return "、".join(labels)


def build_swing_quality_guard(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    collection_status = ai_input.get("collection_status") or {}
    blocks = collection_status.get("blocks") or {}
    core_issues = [
        name
        for name in SWING_CORE_BLOCKS
        if _is_non_fresh_block(dict(blocks.get(name) or {}))
    ]
    supporting_issues = []
    for name in SWING_SUPPORTING_BLOCKS:
        block = dict(blocks.get(name) or {})
        if name == "stock_news" and "etf-heavy" in str(block.get("detail", "") or "").lower():
            continue
        if _is_non_fresh_block(block):
            supporting_issues.append(name)

    if core_issues:
        summary = (
            f"核心行情不完整（{_format_block_labels(core_issues)}）。"
            "今天结论只供参考，不做主动加仓，不开新仓。"
        )
        return {
            "trust_level": "low",
            "execution_readiness": "仅供参考",
            "summary": summary,
            "allow_offensive": False,
            "allow_new_entries": False,
            "core_issues": core_issues,
            "supporting_issues": supporting_issues,
        }

    if supporting_issues:
        summary = (
            f"核心行情完整，但{_format_block_labels(supporting_issues)}暂时缺失。"
            "已有仓位可按计划处理，新开仓先等补齐信息。"
        )
        return {
            "trust_level": "medium",
            "execution_readiness": "谨慎执行",
            "summary": summary,
            "allow_offensive": True,
            "allow_new_entries": False,
            "core_issues": core_issues,
            "supporting_issues": supporting_issues,
        }

    return {
        "trust_level": "high",
        "execution_readiness": "可执行",
        "summary": "核心行情完整，结论可直接执行。",
        "allow_offensive": True,
        "allow_new_entries": True,
        "core_issues": [],
        "supporting_issues": [],
    }


def evaluate_input_quality(ai_input: Dict[str, Any], mode: str, now: Optional[str] = None) -> Dict[str, Any]:
    issues: List[str] = []
    status = "normal"
    current_day = _normalize_now(now)
    context_date = ai_input.get("context_date")
    collection_status = ai_input.get("collection_status") or {}

    if mode in ("midday", "preclose", "close"):
        stocks = ai_input.get("stocks", [])
        if not stocks:
            issues.append("missing_stocks")
            status = "blocked"

    if context_date and context_date != current_day and status != "blocked":
        issues.append("stale_context")
        status = "degraded"

    if mode in ("midday", "preclose", "close") and status != "blocked":
        macro_news = ai_input.get("macro_news", {}).get("telegraph", [])
        stock_news = [n for stock in ai_input.get("stocks", []) for n in stock.get("news", [])]
        if not macro_news and not stock_news:
            issues.append("missing_evidence")
            status = "degraded"

    if status != "blocked" and collection_status.get("overall_status") == "degraded":
        issues.append("degraded_collection")
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
