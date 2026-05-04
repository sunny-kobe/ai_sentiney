"""
混合 AI 客户端
优先使用 MiMo（OpenAI 兼容），失败时降级到 Gemini。
保持与 GeminiClient 相同的接口，对调用方透明。
"""

import json
from typing import Dict, Any, List, Optional
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.analyst.openai_compat_client import OpenAICompatClient
from src.utils.context_builder import build_intraday_context, build_morning_context


class HybridAIClient:
    """
    混合 AI 客户端
    - 主力：MiMo（OpenAI 兼容 API）
    - 兜底：Gemini（Google GenAI）
    - 接口与 GeminiClient 完全兼容
    """

    def __init__(self):
        self.config = ConfigLoader().config

        # MiMo 配置
        mimo_config = self.config.get('ai', {}).get('mimo', {})
        self.mimo_enabled = mimo_config.get('enabled', False)
        self.mimo_client = None
        if self.mimo_enabled:
            base_url = mimo_config.get('base_url', '')
            api_key = mimo_config.get('api_key', '')
            model = mimo_config.get('model', 'mimo-v2.5-pro')
            if base_url and api_key:
                self.mimo_client = OpenAICompatClient(base_url, api_key, model)
                logger.info(f"MiMo client ready: {model}")
            else:
                logger.warning("MiMo config incomplete, disabled")
                self.mimo_enabled = False

        # Gemini 配置（兜底）
        self.gemini_client = None
        try:
            from src.analyst.gemini_client import GeminiClient
            self.gemini_client = GeminiClient()
            logger.info("Gemini client ready (fallback)")
        except Exception as e:
            logger.warning(f"Gemini client init failed: {e}")

        if not self.mimo_enabled and not self.gemini_client:
            raise RuntimeError("No AI client available! Check MiMo and Gemini config.")

    def _call_with_fallback(self, method_name: str, mimo_func, gemini_func, label: str = ""):
        """尝试 MiMo，失败则降级到 Gemini。"""
        # 尝试 MiMo
        if self.mimo_enabled and self.mimo_client:
            try:
                logger.info(f"[{label}] Trying MiMo...")
                result = mimo_func()
                logger.info(f"[{label}] MiMo succeeded")
                return result
            except Exception as e:
                logger.warning(f"[{label}] MiMo failed: {e}, falling back to Gemini")

        # 降级到 Gemini
        if self.gemini_client:
            try:
                logger.info(f"[{label}] Using Gemini fallback...")
                result = gemini_func()
                logger.info(f"[{label}] Gemini succeeded")
                return result
            except Exception as e:
                logger.error(f"[{label}] Gemini also failed: {e}")
                raise

        raise RuntimeError(f"Both MiMo and Gemini failed for {label}")

    def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """午盘分析"""
        system_prompt = self.config['prompts']['midday_focus']
        context_json = self._build_structured_context(market_data)

        def mimo_call():
            return self.mimo_client.chat_json(system_prompt, f"[REAL-TIME DATA CONTEXT]\n{context_json}")

        def gemini_call():
            return self.gemini_client.analyze(market_data)

        return self._call_with_fallback("analyze", mimo_call, gemini_call, "午盘分析")

    def analyze_preclose(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """尾盘执行"""
        system_prompt = self.config['prompts']['preclose_focus']
        context_json = self._build_structured_context(market_data)

        def mimo_call():
            return self.mimo_client.chat_json(system_prompt, f"[REAL-TIME DATA CONTEXT]\n{context_json}")

        def gemini_call():
            return self.gemini_client.analyze_preclose(market_data)

        return self._call_with_fallback("analyze_preclose", mimo_call, gemini_call, "尾盘执行")

    def analyze_with_prompt(self, market_data: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        """自定义 prompt 分析（收盘复盘等）"""
        context_json = self._build_structured_context(market_data)

        def mimo_call():
            return self.mimo_client.chat_json(system_prompt, f"[REAL-TIME DATA CONTEXT]\n{context_json}")

        def gemini_call():
            return self.gemini_client.analyze_with_prompt(market_data, system_prompt)

        return self._call_with_fallback("analyze_with_prompt", mimo_call, gemini_call, "自定义分析")

    def analyze_morning(self, morning_data: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        """早报分析"""
        context_json = self._build_morning_context(morning_data)

        def mimo_call():
            return self.mimo_client.chat_json(system_prompt, f"[OVERNIGHT DATA CONTEXT]\n{context_json}")

        def gemini_call():
            return self.gemini_client.analyze_morning(morning_data, system_prompt)

        return self._call_with_fallback("analyze_morning", mimo_call, gemini_call, "早报分析")

    def ask_question(self, context_data: Dict[str, Any], ai_result: Dict[str, Any], question: str, system_prompt: str) -> str:
        """自由问答"""
        context_summary = json.dumps(context_data, ensure_ascii=False, indent=1) if context_data else "无市场数据"
        ai_summary = json.dumps(ai_result, ensure_ascii=False, indent=1) if ai_result else "无AI分析结果"

        from datetime import datetime
        today_str = datetime.now().strftime('%Y年%m月%d日')

        full_prompt = f"""[当前日期]
{today_str}

---
[市场数据]
{context_summary}

---
[AI分析结果]
{ai_summary}

---
[用户问题]
{question}"""

        def mimo_call():
            return self.mimo_client.chat(system_prompt, full_prompt)

        def gemini_call():
            return self.gemini_client.ask_question(context_data, ai_result, question, system_prompt)

        return self._call_with_fallback("ask_question", mimo_call, gemini_call, "问答")

    def _build_structured_context(self, market_data: Dict[str, Any]) -> str:
        """构建结构化上下文（委托公共 context_builder 模块）。"""
        return build_intraday_context(market_data)

    def _build_morning_context(self, morning_data: Dict[str, Any]) -> str:
        """构建早报上下文（委托公共 context_builder 模块）。"""
        return build_morning_context(morning_data)
