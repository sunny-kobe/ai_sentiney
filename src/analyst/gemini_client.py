from google import genai
from google.genai import types
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel, Field, field_validator
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.utils.json_parser import extract_json_from_text, parse_ai_response
from src.utils.context_builder import build_intraday_context, build_morning_context


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
    # T+1 相关字段（由 post_process 注入，非 AI 输出）
    tradeable: Optional[bool] = Field(default=None)
    signal_note: Optional[str] = Field(default=None)

    @field_validator('action')
    @classmethod
    def normalize_action(cls, v: str) -> str:
        valid = {'DANGER', 'WARNING', 'WATCH', 'OBSERVED', 'SAFE', 'OVERBOUGHT',
                 'HOLD', 'BUY', 'LIMIT_UP', 'LIMIT_DOWN', 'LOCKED_DANGER',
                 'OPPORTUNITY', 'ACCUMULATE', 'N/A'}
        v_upper = v.upper()
        if v_upper in valid:
            return v_upper
        # 尝试模糊匹配
        if '危' in v or '卖' in v or 'SELL' in v_upper or '减仓' in v:
            return 'DANGER'
        if '机会' in v or '抄底' in v:
            return 'OPPORTUNITY'
        if '买' in v or '加仓' in v or '建仓' in v:
            return 'OPPORTUNITY'
        if '观' in v or '看' in v:
            return 'WATCH'
        return 'HOLD'


class MiddayAnalysis(BaseModel):
    """午盘分析结果"""
    market_sentiment: str = Field(default="未知")
    volume_analysis: str = Field(default="")
    macro_summary: str = Field(default="暂无大盘点评")
    bull_case: str = Field(default="")
    bear_case: str = Field(default="")
    actions: List[MiddayAction] = Field(default_factory=list)


class CloseAction(BaseModel):
    """收盘个股复盘"""
    code: str
    name: str
    signal: str = Field(default="N/A")
    today_review: str = Field(default="")
    tomorrow_plan: str = Field(default="")
    support_level: float = Field(default=0.0)
    resistance_level: float = Field(default=0.0)


class CloseAnalysis(BaseModel):
    """收盘复盘结果"""
    market_summary: str = Field(default="暂无总结")
    market_temperature: str = Field(default="未知")
    bull_case: str = Field(default="")
    bear_case: str = Field(default="")
    actions: List[CloseAction] = Field(default_factory=list)


class MorningAction(BaseModel):
    """早报个股操作建议"""
    code: str
    name: str
    overnight_driver: str = Field(default="")
    opening_expectation: str = Field(default="FLAT")
    strategy: str = Field(default="观望")
    ma20_status: str = Field(default="NEAR")
    key_level: float = Field(default=0.0)

    @field_validator('opening_expectation')
    @classmethod
    def normalize_expectation(cls, v: str) -> str:
        v_upper = v.upper()
        valid = {'HIGH_OPEN', 'LOW_OPEN', 'FLAT'}
        if v_upper in valid:
            return v_upper
        if '高' in v or 'HIGH' in v_upper:
            return 'HIGH_OPEN'
        if '低' in v or 'LOW' in v_upper:
            return 'LOW_OPEN'
        return 'FLAT'


class MorningAnalysis(BaseModel):
    """早报分析结果"""
    global_overnight_summary: str = Field(default="暂无隔夜综述")
    commodity_summary: str = Field(default="")
    us_treasury_impact: str = Field(default="")
    a_share_outlook: str = Field(default="平开")
    risk_events: List[str] = Field(default_factory=list)
    actions: List[MorningAction] = Field(default_factory=list)

class GeminiClient:
    def __init__(self):
        self.config = ConfigLoader().config
        self.api_key = self.config['api_keys']['gemini_api_key']
        if not self.api_key:
            logger.warning("Gemini API Key is missing!")

        self.model_name = self.config.get('ai', {}).get('model_name', 'gemini-3.1-pro-preview')
        logger.info(f"Initializing Gemini Client with model: {self.model_name}")
        self.client = genai.Client(api_key=self.api_key)

    def _build_context(self, market_breadth: str, north_funds: float, indices: Dict, macro_news: Dict, portfolio: List[Dict], yesterday_context: Dict = None, scorecard: Dict = None, context_date: str = None) -> str:
        """Constructs the prompt context (slim version for token efficiency).
        委托公共 context_builder 模块。
        """
        from src.utils.context_builder import _build_context
        return _build_context(
            market_breadth=market_breadth, north_funds=north_funds,
            indices=indices, macro_news=macro_news, portfolio=portfolio,
            yesterday_context=yesterday_context, scorecard=scorecard,
            context_date=context_date,
        )

    def _build_structured_config(self, system_prompt: str, response_schema: type[BaseModel]) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
        )

    def _build_text_config(self, system_prompt: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(system_instruction=system_prompt)

    def _extract_structured_payload(self, response: Any) -> Dict[str, Any]:
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, BaseModel):
                return parsed.model_dump()
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()
            if isinstance(parsed, dict):
                return parsed
        text = getattr(response, "text", "") or ""
        result = extract_json_from_text(text)
        if result is not None:
            return result
        logger.error(f"Failed to parse Gemini response as JSON. Raw text preview: {text[:500]}...")
        return {
            "market_sentiment": "解析错误",
            "summary": "AI输出格式无效，请检查prompt配置",
            "actions": [],
            "_raw_text": text[:1000],
        }

    def _generate_structured_content(
        self,
        *,
        system_prompt: str,
        context_label: str,
        context_json: str,
        response_schema: type[BaseModel],
    ) -> Dict[str, Any]:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=f"{context_label}\n{context_json}",
            config=self._build_structured_config(system_prompt, response_schema),
        )
        return self._extract_structured_payload(response)

    def _generate_text_content(self, *, system_prompt: str, content: str) -> str:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=content,
            config=self._build_text_config(system_prompt),
        )
        return (getattr(response, "text", "") or "").strip()

    def _build_intraday_context_json(self, market_data: Dict[str, Any]) -> str:
        return build_intraday_context(market_data)

    def _analyze_intraday(self, market_data: Dict[str, Any], system_prompt: str, log_label: str) -> Dict[str, Any]:
        context_json = self._build_intraday_context_json(market_data)

        logger.info(log_label)
        try:
            parsed = self._generate_structured_content(
                system_prompt=system_prompt,
                context_label="[REAL-TIME DATA CONTEXT]",
                context_json=context_json,
                response_schema=MiddayAnalysis,
            )
            return self._validate_midday_response(parsed)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends data to Gemini and retrieves structured analysis.
        🔧 增强: 使用Pydantic进行输出校验
        """
        system_prompt = self.config['prompts']['midday_focus']
        return self._analyze_intraday(market_data, system_prompt, "Sending request to Gemini...")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def analyze_preclose(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """收盘前模式：复用盘中结构化 schema，但使用独立执行 prompt。"""
        system_prompt = self.config['prompts']['preclose_focus']
        return self._analyze_intraday(market_data, system_prompt, "Sending preclose execution request to Gemini...")

    def analyze_with_prompt(self, market_data: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        """
        Analyze with a custom system prompt (for close mode, etc.).
        🔧 增强: 使用Pydantic进行输出校验
        """
        context_json = build_intraday_context(market_data)

        logger.info("Sending request to Gemini (custom prompt)...")
        try:
            parsed = self._generate_structured_content(
                system_prompt=system_prompt,
                context_label="[REAL-TIME DATA CONTEXT]",
                context_json=context_json,
                response_schema=CloseAnalysis,
            )
            return self._validate_close_response(parsed)

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """🔧 增强版JSON解析器（委托公共 json_parser 模块）。"""
        result = extract_json_from_text(text)
        if result is not None:
            return result
        logger.error(f"Failed to parse Gemini response as JSON. Raw text preview: {text[:500]}...")
        return {
            "market_sentiment": "解析错误",
            "summary": "AI输出格式无效，请检查prompt配置",
            "actions": [],
            "_raw_text": text[:1000],
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

    def _build_morning_context(self, morning_data: Dict[str, Any]) -> str:
        """Constructs the prompt context for morning mode (委托公共 context_builder)。"""
        return build_morning_context(morning_data)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def analyze_morning(self, morning_data: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        """
        早报模式：发送外盘+持仓数据到Gemini进行盘前分析。
        """
        context_json = self._build_morning_context(morning_data)

        logger.info("Sending morning brief request to Gemini...")
        try:
            parsed = self._generate_structured_content(
                system_prompt=system_prompt,
                context_label="[OVERNIGHT DATA CONTEXT]",
                context_json=context_json,
                response_schema=MorningAnalysis,
            )
            return self._validate_morning_response(parsed)
        except Exception as e:
            logger.error(f"Gemini API call failed (morning): {e}")
            raise

    def _validate_morning_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """使用Pydantic校验早报分析输出"""
        try:
            validated = MorningAnalysis.model_validate(data)
            result = validated.model_dump()
            logger.info(f"Morning schema validation passed: {len(result.get('actions', []))} actions")
            return result
        except Exception as e:
            logger.warning(f"Morning schema validation failed, using raw data: {e}")
            if 'actions' not in data or not isinstance(data['actions'], list):
                data['actions'] = []
            return data

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def ask_question(self, context_data: Dict[str, Any], ai_result: Dict[str, Any], question: str, system_prompt: str) -> str:
        """
        Free-text Q&A: answer user questions based on cached market data and AI analysis.
        Returns plain text (not JSON).
        """
        if context_data:
            slim_context = self._slim_qa_context(context_data)
            context_summary = json.dumps(slim_context, ensure_ascii=False, indent=1)
        else:
            context_summary = "无市场数据"
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
{question}
"""
        logger.info(f"Sending Q&A request to Gemini: {question[:50]}...")
        try:
            return self._generate_text_content(system_prompt=system_prompt, content=full_prompt)
        except Exception as e:
            logger.error(f"Gemini Q&A call failed: {e}")
            raise

    def _slim_qa_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Slim down Q&A context: only keep key fields."""
        slim = {"market_breadth": data.get("market_breadth")}
        if "indices" in data:
            slim["indices"] = data["indices"]
        stocks = data.get("stocks", [])
        if stocks:
            slim["stocks"] = [{
                "code": s.get("code"), "name": s.get("name"),
                "price": s.get("current_price"), "change": s.get("pct_change"),
                "signal": s.get("signal"), "tech": s.get("tech_summary", ""),
            } for s in stocks]
        return slim
