"""
OpenAI 兼容 API 客户端
支持 MiMo 等 OpenAI 兼容接口，用于替代或补充 GeminiClient。
"""
import json
import re
import requests
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


class OpenAICompatClient:
    """OpenAI 兼容 API 客户端（用于 MiMo 等模型）"""

    def __init__(self, base_url: str, api_key: str, model: str = "mimo-v2.5-pro"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        ai_cfg = ConfigLoader.get_ai_config()
        self.timeout = ai_cfg.get('timeout', 120)
        logger.info(f"OpenAICompatClient initialized: model={model}, base_url={base_url}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.3) -> str:
        """发送聊天请求，返回文本响应。"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenAICompatClient API call failed: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat_json(self, system_prompt: str, user_content: str, temperature: float = 0.2) -> Dict[str, Any]:
        """发送聊天请求，强制返回 JSON。"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt + "\n\n你必须返回纯 JSON，不要包含 markdown 代码块或任何其他文本。"},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return self._parse_json(text)
        except Exception as e:
            logger.error(f"OpenAICompatClient JSON call failed: {e}")
            raise

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """解析 JSON 响应，兼容多种格式（委托公共模块）。"""
        return parse_ai_response(text)
