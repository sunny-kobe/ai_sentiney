"""
公共 JSON 解析模块
从 AI 响应文本中提取 JSON，支持多种格式：
- 纯 JSON
- Markdown 代码块包裹的 JSON
- 含干扰文本的 JSON（括号匹配提取）
"""

import json
import re
from typing import Any, Dict, Optional

from pydantic import BaseModel

from src.utils.logger import logger


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    从文本中提取 JSON 对象。

    按优先级尝试以下策略：
    1. 直接解析整个文本
    2. 提取 ```json ... ``` 代码块
    3. 括号匹配法：扫描所有 '{'，用栈匹配找到完整 JSON 对象
    4. 简单的首 '{' 尾 '}' 截取（兼容旧逻辑）

    Args:
        text: 可能包含 JSON 的文本

    Returns:
        解析成功返回 dict，失败返回 None
    """
    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 提取 ```json ... ``` 代码块
    json_block_pattern = r'```(?:json)?\s*(\{[\s\S]*?\})\s*```'
    matches = re.findall(json_block_pattern, text)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    # 3. 括号匹配法：找到最外层完整 JSON 对象
    result = _find_json_by_bracket_matching(text)
    if result is not None:
        return result

    # 4. 简单的首{尾}匹配（兼容旧逻辑）
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    return None


def _find_json_by_bracket_matching(s: str) -> Optional[Dict[str, Any]]:
    """使用括号匹配找到完整的 JSON 对象。"""
    brace_positions = [i for i, c in enumerate(s) if c == '{']

    for start in brace_positions:
        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(s)):
            c = s[i]

            if escape_next:
                escape_next = False
                continue

            if c == '\\' and in_string:
                escape_next = True
                continue

            if c == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    candidate = s[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # 这个起点不行，尝试下一个
    return None


def parse_ai_response(
    text: str,
    schema: Optional[type[BaseModel]] = None,
    fallback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    解析 AI 响应文本，提取 JSON 并可选地进行 Pydantic 校验。

    Args:
        text: AI 返回的文本
        schema: 可选的 Pydantic 模型，用于校验和规范化
        fallback: 解析失败时的降级返回值

    Returns:
        解析后的 dict；失败时返回 fallback 或默认错误结构
    """
    parsed = extract_json_from_text(text)

    if parsed is None:
        raw_preview = text[:500] if text else "(empty)"
        logger.error(f"Failed to parse AI response as JSON. Preview: {raw_preview}...")
        if fallback is not None:
            return fallback
        return {
            "error": "JSON parse failed",
            "_raw_text": text[:1000],
        }

    # Pydantic 校验
    if schema is not None:
        try:
            validated = schema.model_validate(parsed)
            result = validated.model_dump()
            actions_count = len(result.get('actions', []))
            logger.info(f"Schema validation passed: {actions_count} actions")
            return result
        except Exception as e:
            logger.warning(f"Schema validation failed, using raw data: {e}")
            # 降级：至少确保 actions 是列表
            if 'actions' in parsed and not isinstance(parsed.get('actions'), list):
                parsed['actions'] = []

    return parsed
