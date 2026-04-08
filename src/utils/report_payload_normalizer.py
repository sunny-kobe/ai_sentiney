from __future__ import annotations

from typing import Any, Dict, List

from src.service.report_quality import build_quality_detail


LEGACY_DEGRADED_OVERVIEW = "结构化快报"
LEGACY_DEGRADED_SUMMARY = "证据不足，降级输出"
DEGRADED_OVERVIEW_LABEL = "信息不全，先看技术结构"
DEGRADED_INTRADAY_SUMMARY = "当前主要依据技术面和已采集快讯整理，先给保守执行摘要。"
DEGRADED_CLOSE_SUMMARY = "当前主要依据技术面和已采集快讯整理，先给盘后执行摘要。"
DEGRADED_CLOSE_REVIEW = "盘后信息不全，先看技术结构"


def _is_quality_alert(status: Any) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized not in {"", "normal", "fresh"}


def _infer_mode(data: Dict[str, Any]) -> str:
    if "market_temperature" in data or "market_summary" in data:
        return "close"
    if "macro_summary" in data:
        if "执行" in str(data.get("macro_summary", "") or ""):
            return "preclose"
        return "midday"
    return "unknown"


def _copy_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(action or {}) for action in actions]


def normalize_report_for_display(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return data

    mode = _infer_mode(data)
    normalized = dict(data)
    normalized["actions"] = _copy_actions(data.get("actions", []) or [])

    if _is_quality_alert(normalized.get("quality_status")) and not normalized.get("quality_detail"):
        issues = list(normalized.get("quality_issues", []) or [])
        if issues:
            structured_report = normalized.get("structured_report") or {}
            normalized["quality_detail"] = build_quality_detail(
                {
                    "context_date": normalized.get("data_timestamp") or structured_report.get("data_timestamp"),
                    "collection_status": (
                        structured_report.get("collection_status")
                        or normalized.get("collection_status")
                        or {}
                    ),
                },
                issues,
                mode=mode if mode in {"midday", "preclose", "close"} else "midday",
            )

    if mode == "close" and _is_quality_alert(normalized.get("quality_status")):
        if normalized.get("market_summary") == LEGACY_DEGRADED_SUMMARY:
            normalized["market_summary"] = DEGRADED_CLOSE_SUMMARY
        if normalized.get("market_temperature") == LEGACY_DEGRADED_OVERVIEW:
            normalized["market_temperature"] = DEGRADED_OVERVIEW_LABEL
        for action in normalized["actions"]:
            if action.get("today_review") == LEGACY_DEGRADED_OVERVIEW:
                action["today_review"] = DEGRADED_CLOSE_REVIEW
        return normalized

    if mode in {"midday", "preclose"} and _is_quality_alert(normalized.get("quality_status")):
        if normalized.get("market_sentiment") == LEGACY_DEGRADED_OVERVIEW:
            normalized["market_sentiment"] = DEGRADED_OVERVIEW_LABEL
        if normalized.get("macro_summary") == LEGACY_DEGRADED_SUMMARY:
            normalized["macro_summary"] = DEGRADED_INTRADAY_SUMMARY
        return normalized

    return normalized
