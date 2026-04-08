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
INTRADAY_CORE_BLOCKS = ("stock_quotes", "stock_history")


def _normalize_now(now: Optional[str]) -> str:
    if now:
        return now
    return datetime.now().strftime("%Y-%m-%d")


def _is_non_fresh_block(block: Dict[str, Any]) -> bool:
    status = str((block or {}).get("status", "") or "").strip().lower()
    return status in {"missing", "degraded", "blocked"}


def _has_hard_collection_degradation(collection_status: Dict[str, Any], mode: str) -> bool:
    if str((collection_status or {}).get("overall_status", "") or "").strip().lower() != "degraded":
        return False

    if mode not in ("midday", "preclose", "close"):
        return True

    blocks = collection_status.get("blocks") or {}
    for block_name in INTRADAY_CORE_BLOCKS:
        if _is_non_fresh_block(dict(blocks.get(block_name) or {})):
            return True
    return False


def _format_block_labels(block_names: List[str]) -> str:
    labels = [BLOCK_LABELS.get(name, name) for name in block_names]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return "、".join(labels)


def _non_fresh_blocks(collection_status: Dict[str, Any], block_names: tuple[str, ...]) -> List[str]:
    blocks = collection_status.get("blocks") or {}
    return [
        name
        for name in block_names
        if _is_non_fresh_block(dict(blocks.get(name) or {}))
    ]


def build_quality_detail(
    ai_input: Dict[str, Any],
    issues: List[str],
    *,
    mode: str,
    now: Optional[str] = None,
) -> str:
    if not issues:
        return ""

    current_day = _normalize_now(now)
    context_date = str(ai_input.get("context_date") or "").strip()
    collection_status = ai_input.get("collection_status") or {}
    details: List[str] = []

    for issue in issues:
        if issue == "missing_stocks":
            details.append("缺少标的行情，当前无法生成有效报告。")
            continue

        if issue == "stale_context":
            if context_date and current_day:
                details.append(f"上下文日期仍是 {context_date}，不是今天 {current_day}。")
            else:
                details.append("上下文日期不是今天。")
            continue

        if issue == "missing_evidence":
            details.append("宏观快讯和个股新闻都不足。")
            continue

        if issue == "degraded_collection":
            candidate_blocks = INTRADAY_CORE_BLOCKS if mode in ("midday", "preclose", "close") else tuple(
                (collection_status.get("blocks") or {}).keys()
            )
            missing_blocks = _non_fresh_blocks(collection_status, candidate_blocks)
            if missing_blocks:
                details.append(f"核心行情不完整：{_format_block_labels(missing_blocks)}。")
            else:
                details.append("核心行情数据不完整。")
            continue

        if issue == "incomplete_action_coverage":
            details.append("生成结果没有覆盖全部标的，已回退到结构化结果。")
            continue

        details.append(str(issue))

    return "；".join(detail.rstrip("。") for detail in details if detail).strip("；") + "。"


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

    if status != "blocked" and _has_hard_collection_degradation(collection_status, mode):
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
