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
        self.model = genai.GenerativeModel('gemini-3-pro-preview')

    def _build_context(self, market_breadth: str, north_funds: float, portfolio: List[Dict]) -> str:
        """Constructs the prompt context."""
        
        # Simplify portfolio data for AI to save tokens and focus attention
        portfolio_summary = []
        for stock in portfolio:
            portfolio_summary.append({
                "Code": stock['code'],
                "Name": stock['name'],
                "Price": stock['current_price'],
                "MA20": stock['ma20'],
                "Signal": stock.get('signal', 'N/A'),
                "News": stock.get('news', [])
            })
            
        context = {
            "Market_Breadth": market_breadth,
            "North_Money": f"{north_funds} Billion",
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
        
        context_json = self._build_context(market_breadth, north_funds, portfolio)
        
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
            # Gemini sometimes wraps JSON in markdown blocks like ```json ... ```
            text = response.text
            clean_text = text.replace('```json', '').replace('```', '').strip()
            
            return json.loads(clean_text)
            
        except json.JSONDecodeError:
            logger.error("Failed to parse Gemini response as JSON. Raw text: " + text)
            return {"error": "Invalid JSON response", "raw": text}
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise
