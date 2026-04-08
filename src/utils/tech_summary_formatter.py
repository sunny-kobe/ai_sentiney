from __future__ import annotations

import re
from typing import List


_TAG_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def _format_tag_content(content: str) -> str:
    parts = content.split("_")
    if len(parts) < 3 or parts[0] != "日线":
        return ""

    indicator = parts[1]
    values = parts[2:]
    if values and values[-1] == "0":
        values = values[:-1]

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
