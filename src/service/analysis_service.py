import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.collector.data_fetcher import DataCollector
from src.processor.data_processor import DataProcessor
from src.analyst.gemini_client import GeminiClient
from src.reporter.feishu_client import FeishuClient
from src.storage.database import SentinelDB

class AnalysisService:
    def __init__(self):
        self.config = ConfigLoader().config
        self.db = SentinelDB()
        self.data_path = Path("data/latest_context.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

    async def collect_and_process_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """Collects raw data and processes it into AI-ready context."""
        # 1. Collect Data (Async)
        collector = DataCollector()
        raw_data = await collector.collect_all(portfolio)
        
        market_breadth = raw_data['market_breadth']
        north_funds = raw_data['north_funds']
        stock_data_list = raw_data['stocks']
        indices = raw_data.get('indices', {})
        macro_news = raw_data.get('macro_news', {})
        
        logger.info(f"Data Collected. Market Breadth: {market_breadth}, North Funds: {north_funds}")

        # 2. Process Data (Indicators)
        processor = DataProcessor()
        processed_stocks = []
        for stock_raw in stock_data_list:
            stock_indicators = processor.calculate_indicators(stock_raw)
            processed_stocks.append(stock_indicators)
            
        # Pre-calculate signals
        processed_stocks = processor.generate_signals(processed_stocks, north_funds)

        return {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "macro_news": macro_news,
            "stocks": processed_stocks
        }

    def post_process_result(self, analysis_result: Dict, ai_input: Dict) -> Dict:
        """Injects real-time data back into analysis result for display."""
        indices = ai_input.get('indices', {})
        processed_stocks = ai_input.get('stocks', [])
        
        # 1. Format Indices Info
        indices_str = []
        for name, data in indices.items():
            pct = data.get('change_pct', 0.0)
            sign = "+" if pct > 0 else ""
            indices_str.append(f"{name} {sign}{pct}%")
        analysis_result['indices_info'] = " / ".join(indices_str)
        
        # 2. MATCH Stock Pct Change to Actions
        for action in analysis_result.get('actions', []):
            code = action.get('code')
            name = action.get('name')
            
            # Robust matching: try code first, then name
            stock_obj = None
            if code:
                for s in processed_stocks:
                    if s['code'] == code:
                        stock_obj = s
                        break
            
            if not stock_obj and name:
                for s in processed_stocks:
                    if s['name'] == name:
                        stock_obj = s
                        break
            
            if stock_obj:
                pct = stock_obj.get('pct_change', 0.0)
                current_price = stock_obj.get('current_price', 0.0)
                action['current_price'] = current_price
                
                sign = "+" if pct > 0 else ""
                color = "🔴" if pct > 0 else "🟢" 
                action['pct_change_str'] = f"`{color} {sign}{pct}%`"
            else:
                action['pct_change_str'] = ""
                
        return analysis_result

    async def run_analysis(self, mode: str, dry_run: bool = False, replay: bool = False) -> Dict:
        """
        Runs the full analysis pipeline.
        Returns the analysis result dict.
        """
        logger.info(f"=== Starting Analysis ({mode.upper()}) ===")
        
        portfolio = self.config.get('portfolio', [])
        ai_input = None

        # --- Step 1: Data Preparation ---
        if replay:
            if self.data_path.exists():
                logger.info("Replay Mode: Loading data from local JSON file...")
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    ai_input = json.load(f)
            else:
                latest_record = self.db.get_latest_record(mode=mode)
                if latest_record:
                    logger.info("Replay Mode: Loading data from SQLite DB...")
                    ai_input = latest_record
                else:
                     logger.error("No historical data found for replay.")
                     return {"error": "No replay data"}
        else:
            if not portfolio:
                logger.warning("Portfolio is empty.")
                return {"error": "Portfolio is empty"}
            
            try:
                ai_input = await self.collect_and_process_data(portfolio)
                # Save context
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(ai_input, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Data collection failed: {e}")
                return {"error": str(e)}

        # --- Step 2: AI Analysis ---
        analyst = GeminiClient()
        analysis_result = {}
        
        try:
            if dry_run and not replay:
                logger.info("Dry Run Mode: Mocking AI response.")
                analysis_result = {
                    "market_sentiment": "DryRun", 
                    "summary": "This is a dry run.", 
                    "actions": []
                }
            else:
                if mode == 'midday':
                    last_close = self.db.get_last_close_analysis()
                    ai_input['yesterday_context'] = last_close
                    analysis_result = analyst.analyze(ai_input)
                elif mode == 'close':
                    system_prompt = self.config['prompts'].get('close_review')
                    if system_prompt:
                        analysis_result = analyst.analyze_with_prompt(ai_input, system_prompt)
                    else:
                        analysis_result = analyst.analyze(ai_input)
            
            # Unified Post-Processing
            analysis_result = self.post_process_result(analysis_result, ai_input)
            
            logger.info(f"{mode.capitalize()} Analysis Completed.")
            
        except Exception as e:
            logger.error(f"AI Analysis Failed: {e}")
            return {"error": f"AI Analysis Failed: {e}"}

        # --- Step 3: Reporting ---
        reporter = FeishuClient()
        if dry_run:
            logger.info("Dry Run Mode: Skipping Feishu Push.")
            # For WebUI return, we still want the result
        else:
            if mode == 'midday':
                reporter.send_card(analysis_result)
            else:
                reporter.send_close_card(analysis_result)

        # --- Step 4: Persistence ---
        if not dry_run or (dry_run and replay):
            if not dry_run: 
                self.db.save_record(mode=mode, ai_input=ai_input, ai_analysis=analysis_result)

        logger.info(f"=== Analysis ({mode.upper()}) Finished ===")
        return analysis_result
