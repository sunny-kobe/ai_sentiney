from __future__ import annotations

import re
from typing import Dict, List, Tuple


_TAG_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def _parse_tag_content(content: str) -> Tuple[str, List[str]]:
    parts = content.split("_")
    if len(parts) < 3 or parts[0] != "日线":
        return "", []

    indicator = parts[1]
    values = parts[2:]
    if values and values[-1] == "0":
        values = values[:-1]
    return indicator, values


def _collect_tag_map(text: str) -> Dict[str, List[str]]:
    tag_map: Dict[str, List[str]] = {}
    for match in _TAG_PATTERN.finditer(text):
        indicator, values = _parse_tag_content(match.group(1))
        if indicator:
            tag_map[indicator] = values
    return tag_map


def _format_tag_content(content: str) -> str:
    indicator, values = _parse_tag_content(content)
    if not indicator:
        return ""

    if indicator == "MACD" and len(values) >= 2:
        return f"MACD{values[0]}，{values[1]}"
    if indicator == "OBV" and values:
        return f"OBV{values[0]}"
    if indicator == "KDJ" and values:
        return f"KDJ{values[0]}"
    if indicator == "RSI" and len(values) >= 2:
        return f"RSI {values[1]}，{values[0]}"
    if indicator == "ATR" and values:
        return f"ATR{values[0]}"
    if indicator == "布林带" and values:
        return f"布林带{values[0]}"
    if indicator == "量能" and len(values) >= 2:
        return f"量能{values[0]}，{values[1]}"

    return ""


def format_tech_summary_for_display(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or "[日线_" not in text:
        return text

    formatted: List[str] = []
    for match in _TAG_PATTERN.finditer(text):
        item = _format_tag_content(match.group(1))
        if item:
            formatted.append(item)

    return "；".join(formatted) if formatted else text


def format_tech_summary_for_brief(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or "[日线_" not in text:
        return text

    tag_map = _collect_tag_map(text)
    if not tag_map:
        return text

    clauses: List[str] = []

    macd_values = tag_map.get("MACD", [])
    trend_clause = ""
    risk_clause = ""
    if macd_values:
        macd_state = macd_values[0]
        if "多头" in macd_state or "金叉" in macd_state:
            trend_clause = "趋势仍偏强"
        elif "空头" in macd_state or "死叉" in macd_state:
            trend_clause = "趋势偏弱"

        if len(macd_values) >= 2:
            macd_signal = macd_values[1]
            if "顶背驰" in macd_signal:
                risk_clause = "短线有钝化压力"
            elif "底背驰" in macd_signal:
                risk_clause = "有止跌修复迹象"

    if not trend_clause:
        band_values = tag_map.get("布林带", [])
        if band_values:
            if band_values[0] in {"上半区", "上轨外"}:
                trend_clause = "位置仍在偏强区"
            elif band_values[0] in {"下半区", "下轨外"}:
                trend_clause = "位置仍在偏弱区"

    if trend_clause and risk_clause:
        clauses.append(f"{trend_clause}，但{risk_clause}")
    elif trend_clause:
        clauses.append(trend_clause)
    elif risk_clause:
        clauses.append(risk_clause)

    obv_values = tag_map.get("OBV", [])
    if obv_values:
        if "流入" in obv_values[0]:
            clauses.append("承接还在")
        elif "流出" in obv_values[0]:
            clauses.append("资金有流出")

    volume_values = tag_map.get("量能", [])
    if volume_values:
        volume_level = volume_values[0]
        if volume_level == "放量":
            clauses.append("量能有放大")
        elif volume_level == "平量":
            clauses.append("量能基本正常")
        elif volume_level in {"温和缩量", "极度缩量"}:
            clauses.append("量能偏缩")

    deduped: List[str] = []
    for clause in clauses:
        if clause and clause not in deduped:
            deduped.append(clause)

    return "；".join(deduped[:3]) if deduped else format_tech_summary_for_display(text)
