import google.generativeai as genai
from typing import Dict, Any, List, Optional
import json
import re
import os
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field, field_validator
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader


# ============================================================
# 🔧 Pydantic Schema：AI输出结构校验
# ============================================================

class MiddayAction(BaseModel):
    """午盘个股操作建议"""
    code: str
    name: str
    signal: str = Field(default="N/A")
    action: str = Field(default="HOLD")
    operation: str = Field(default="观望")
    reason: str = Field(default="")
    news_impact: str = Field(default="")

    @field_validator('action')
    @classmethod
    def normalize_action(cls, v: str) -> str:
        valid = {'DANGER', 'WARNING', 'WATCH', 'OBSERVED', 'SAFE', 'OVERBOUGHT',
                 'HOLD', 'LIMIT_UP', 'LIMIT_DOWN', 'N/A'}
        v_upper = v.upper()
        if v_upper in valid:
            return v_upper
        # 尝试模糊匹配
        if '危' in v or '卖' in v or 'SELL' in v_upper:
            return 'DANGER'
        if '观' in v or '看' in v:
            return 'WATCH'
        return 'HOLD'


class MiddayAnalysis(BaseModel):
    """午盘分析结果"""
    market_sentiment: str = Field(default="未知")
    volume_analysis: str = Field(default="")
    macro_summary: str = Field(default="暂无大盘点评")
    actions: List[MiddayAction] = Field(default_factory=list)


class CloseAction(BaseModel):
    """收盘个股复盘"""
    code: str
    name: str
    today_review: str = Field(default="")
    tomorrow_plan: str = Field(default="")
    support_level: float = Field(default=0.0)
    resistance_level: float = Field(default=0.0)


class CloseAnalysis(BaseModel):
    """收盘复盘结果"""
    market_summary: str = Field(default="暂无总结")
    market_temperature: str = Field(default="未知")
    actions: List[CloseAction] = Field(default_factory=list)

class GeminiClient:
    def __init__(self):
        self.config = ConfigLoader().config
        self.api_key = self.config['api_keys']['gemini_api_key']
        if not self.api_key:
            logger.warning("Gemini API Key is missing!")
        
        genai.configure(api_key=self.api_key)
        
        model_name = self.config.get('ai', {}).get('model_name', 'gemini-3-pro-preview')
        logger.info(f"Initializing Gemini Client with model: {model_name}")
        self.model = genai.GenerativeModel(model_name)

    def _build_context(self, market_breadth: str, north_funds: float, indices: Dict, macro_news: Dict, portfolio: List[Dict], yesterday_context: Dict = None) -> str:
        """Constructs the prompt context."""
        
        # Simplify portfolio data for AI to save tokens and focus attention
        portfolio_summary = []
        for stock in portfolio:
            portfolio_summary.append({
                "Code": stock['code'],
                "Name": stock['name'],
                "Price": stock['current_price'],
                "Change": f"{stock.get('pct_change', 0)}%",
                "MA20": stock['ma20'],
                "Bias": f"{round(stock.get('bias_pct', 0) * 100, 2)}%",  # 乖离率 (%)
                "Volume": f"{stock.get('volume', 0)}万手",  # 成交量
                "Volume_Ratio": stock.get('volume_ratio', 0),  # 量比
                "Turnover": f"{stock.get('turnover_rate', 0)}%",  # 换手率
                "Signal": stock.get('signal', 'N/A'),
                "News": stock.get('news', [])
            })
            
        context = {
            "Market_Breadth": market_breadth,
            "North_Money": f"{north_funds}亿元",  # 单位修正：原"Billion"有10倍夸大
            "Indices": indices,
            "Macro_News": {
                "财联社电报": macro_news.get("telegraph", []),
                "AI科技热点": macro_news.get("ai_tech", [])
            },
            "Portfolio": portfolio_summary
        }
        
        if yesterday_context:
            context["Yesterday_Plan"] = yesterday_context.get('actions', [])
            
        return json.dumps(context, ensure_ascii=False, indent=2)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends data to Gemini and retrieves structured analysis.
        🔧 增强: 使用Pydantic进行输出校验
        """
        market_breadth = market_data.get('market_breadth', "Unknown")
        north_funds = market_data.get('north_funds', 0.0)
        portfolio = market_data.get('stocks', [])
        indices = market_data.get('indices', {})
        macro_news = market_data.get('macro_news', {})
        yesterday_context = market_data.get('yesterday_context')

        context_json = self._build_context(market_breadth, north_funds, indices, macro_news, portfolio, yesterday_context)

        # Load Prompt Template
        # Using the midday focus from config
        system_prompt = self.config['prompts']['midday_focus']

        full_prompt = f"""
{system_prompt}

---
[REAL-TIME DATA CONTEXT]
{context_json}
"""
        logger.info("Sending request to Gemini...")
        try:
            response = self.model.generate_content(full_prompt)
            parsed = self._parse_response(response.text)
            return self._validate_midday_response(parsed)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def analyze_with_prompt(self, market_data: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        """
        Analyze with a custom system prompt (for close mode, etc.).
        🔧 增强: 使用Pydantic进行输出校验
        """
        market_breadth = market_data.get('market_breadth', "Unknown")
        north_funds = market_data.get('north_funds', 0.0)
        portfolio = market_data.get('stocks', [])
        indices = market_data.get('indices', {})
        macro_news = market_data.get('macro_news', {})
        
        context_json = self._build_context(market_breadth, north_funds, indices, macro_news, portfolio)
        
        full_prompt = f"""
{system_prompt}

---
[REAL-TIME DATA CONTEXT]
{context_json}
"""
        logger.info("Sending request to Gemini (custom prompt)...")
        try:
            response = self.model.generate_content(full_prompt)
            parsed = self._parse_response(response.text)
            return self._validate_close_response(parsed)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """
        🔧 增强版JSON解析器
        问题: 原解析器找第一个{和最后一个}，当AI输出包含思考日志时会失败
        解决:
        1. 先尝试直接解析
        2. 尝试提取markdown代码块中的JSON
        3. 使用栈匹配找到最外层完整JSON对象
        4. 降级返回错误结构
        """
        # 清理常见问题
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

        # 3. 栈匹配法：找到最外层完整的JSON对象
        # 从后向前扫描，找到最后一个完整的 {...} 结构
        def find_json_by_bracket_matching(s: str) -> str | None:
            """使用括号匹配找到完整的JSON对象"""
            # 找所有 { 的位置
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
                            # 找到完整的JSON对象
                            candidate = s[start:i+1]
                            try:
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                break  # 这个起点不行，尝试下一个
            return None

        result = find_json_by_bracket_matching(text)
        if result:
            return result

        # 4. 最后尝试：简单的首{尾}匹配（兼容旧逻辑）
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                json_str = text[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Simple bracket extraction failed: {e}")

        # 5. 降级返回
        logger.error(f"Failed to parse Gemini response as JSON. Raw text preview: {text[:500]}...")
        return {
            "market_sentiment": "解析错误",
            "summary": "AI输出格式无效，请检查prompt配置",
            "actions": [],
            "_raw_text": text[:1000]  # 保留原始文本用于调试
        }

    def _validate_midday_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 使用Pydantic校验午盘分析输出
        - 确保必要字段存在
        - 规范化action值
        - 填充缺失字段
        """
        try:
            validated = MiddayAnalysis.model_validate(data)
            result = validated.model_dump()
            logger.info(f"Schema validation passed: {len(result.get('actions', []))} actions")
            return result
        except Exception as e:
            logger.warning(f"Schema validation failed, using raw data: {e}")
            # 降级：至少确保actions是列表
            if 'actions' not in data or not isinstance(data['actions'], list):
                data['actions'] = []
            return data

    def _validate_close_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 使用Pydantic校验收盘复盘输出
        """
        try:
            validated = CloseAnalysis.model_validate(data)
            result = validated.model_dump()
            logger.info(f"Schema validation passed: {len(result.get('actions', []))} reviews")
            return result
        except Exception as e:
            logger.warning(f"Schema validation failed, using raw data: {e}")
            if 'actions' not in data or not isinstance(data['actions'], list):
                data['actions'] = []
            return data
