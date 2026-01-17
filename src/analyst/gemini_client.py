import google.generativeai as genai
from typing import Dict, Any, List
import json
import os
from tenacity import retry, stop_after_attempt, wait_exponential
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader

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

    def _build_context(self, market_breadth: str, north_funds: float, indices: Dict, macro_news: Dict, portfolio: List[Dict]) -> str:
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
                "Signal": stock.get('signal', 'N/A'),
                "News": stock.get('news', [])
            })
            
        context = {
            "Market_Breadth": market_breadth,
            "North_Money": f"{north_funds} Billion",
            "Indices": indices,
            "Macro_News": {
                "财联社电报": macro_news.get("telegraph", []),
                "AI科技热点": macro_news.get("ai_tech", [])
            },
            "Portfolio": portfolio_summary
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends data to Gemini and retrieves structured analysis.
        """
        market_breadth = market_data.get('market_breadth', "Unknown")
        north_funds = market_data.get('north_funds', 0.0)
        portfolio = market_data.get('stocks', [])
        indices = market_data.get('indices', {})
        macro_news = market_data.get('macro_news', {})
        
        context_json = self._build_context(market_breadth, north_funds, indices, macro_news, portfolio)
        
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
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def analyze_with_prompt(self, market_data: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
        """
        Analyze with a custom system prompt (for close mode, etc.).
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
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """
        Robustly parses JSON from the AI response, handling potential MD/text noise.
        """
        try:
            # 1. Try direct parsing
            return json.loads(text)
        except json.JSONDecodeError:
            # 2. Extract JSON block if surrounded by text
            try:
                # Find the first '{' and the last '}'
                start = text.find('{')
                end = text.rfind('}') + 1
                if start != -1 and end != 0:
                    json_str = text[start:end]
                    return json.loads(json_str)
            except Exception as e:
                logger.error(f"Failed to extract JSON from text: {e}")
        
        # 3. Fallback: Return raw text wrapped in a safe dict, or raise error
        logger.error(f"Failed to parse Gemini response as JSON. Raw text: {text}")
        return {
            "market_sentiment": "Parse Error", 
            "summary": "AI output format invalid.", 
            "actions": []
        }
