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

        # Pre-calculate signals (north_funds removed in v2.0)
        processed_stocks = processor.generate_signals(processed_stocks)

        return {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "macro_news": macro_news,
            "stocks": processed_stocks
        }

    async def collect_and_process_morning_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """Collects and processes morning pre-market data."""
        collector = DataCollector()
        raw_data = await collector.collect_morning_data(portfolio)

        processor = DataProcessor()
        processed_data = processor.process_morning_data(raw_data, portfolio)

        logger.info(f"Morning data collected. Global indices: {len(processed_data.get('global_indices', []))}, "
                     f"Commodities: {len(processed_data.get('commodities', []))}, "
                     f"Stocks: {len(processed_data.get('stocks', []))}")
        return processed_data

    def post_process_result(self, analysis_result: Dict, ai_input: Dict, mode: str = 'midday') -> Dict:
        """Injects real-time data back into analysis result for display."""
        if mode == 'morning':
            return self._post_process_morning(analysis_result, ai_input)

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

                # 🔧 FIX: 传递 T+1 相关字段到 actions
                if 'tradeable' in stock_obj:
                    action['tradeable'] = stock_obj['tradeable']
                if 'signal_note' in stock_obj:
                    action['signal_note'] = stock_obj['signal_note']
                # 如果 processor 生成了 LOCKED_DANGER，覆盖 AI 的 signal
                if stock_obj.get('signal') == 'LOCKED_DANGER':
                    action['signal'] = 'LOCKED_DANGER'
            else:
                action['pct_change_str'] = ""
                
        return analysis_result

    def _post_process_morning(self, analysis_result: Dict, ai_input: Dict) -> Dict:
        """Injects raw overnight data into morning analysis result for Feishu display."""
        # Format global indices info
        global_indices = ai_input.get('global_indices', [])
        indices_parts = []
        for idx in global_indices:
            pct = idx.get('change_pct', 0)
            sign = "+" if pct > 0 else ""
            emoji = "🔴" if pct > 0 else "🟢"
            indices_parts.append(f"{emoji} {idx['name']} {sign}{pct}%")
        analysis_result['global_indices_info'] = "\n".join(indices_parts)

        # Format commodities info
        commodities = ai_input.get('commodities', [])
        commodity_parts = []
        for c in commodities:
            pct = c.get('change_pct', 0)
            sign = "+" if pct > 0 else ""
            commodity_parts.append(f"{c['name']} {sign}{pct}%")
        analysis_result['commodities_info'] = " / ".join(commodity_parts)

        # Format treasury info
        treasury = ai_input.get('us_treasury', {})
        if treasury:
            y10 = treasury.get('yield_10y', 0)
            y2 = treasury.get('yield_2y', 0)
            spread = treasury.get('spread_10y_2y', 0)
            analysis_result['treasury_info'] = f"10Y: {y10}% / 2Y: {y2}% / 利差: {spread}%"

        # Match overnight drivers to actions
        stocks = ai_input.get('stocks', [])
        for action in analysis_result.get('actions', []):
            code = action.get('code', '')
            for s in stocks:
                if s.get('code') == code:
                    if not action.get('overnight_driver'):
                        action['overnight_driver'] = s.get('overnight_driver_str', '')
                    if not action.get('ma20_status'):
                        action['ma20_status'] = s.get('ma20_status', 'NEAR')
                    break

        return analysis_result

    async def run_analysis(self, mode: str, dry_run: bool = False, replay: bool = False, publish: bool = False) -> Dict:
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
                if mode == 'morning':
                    ai_input = await self.collect_and_process_morning_data(portfolio)
                else:
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
                elif mode == 'morning':
                    system_prompt = self.config['prompts'].get('morning_brief')
                    if system_prompt:
                        analysis_result = analyst.analyze_morning(ai_input, system_prompt)
                    else:
                        logger.error("Morning brief prompt not found in config!")
                        return {"error": "Missing morning_brief prompt"}

            # Unified Post-Processing
            analysis_result = self.post_process_result(analysis_result, ai_input, mode=mode)
            
            logger.info(f"{mode.capitalize()} Analysis Completed.")
            
        except Exception as e:
            logger.error(f"AI Analysis Failed: {e}")
            return {"error": f"AI Analysis Failed: {e}"}

        # --- Step 3: Reporting ---
        reporter = FeishuClient()
        if dry_run:
            logger.info("Dry Run Mode: Skipping Feishu Push.")
        elif publish:
            if mode == 'midday':
                reporter.send_card(analysis_result)
            elif mode == 'close':
                reporter.send_close_card(analysis_result)
            elif mode == 'morning':
                reporter.send_morning_card(analysis_result)
        else:
            logger.info("Publish not requested: Skipping Feishu Push.")

        # --- Step 4: Persistence ---
        if not dry_run or (dry_run and replay):
            if not dry_run: 
                self.db.save_record(mode=mode, ai_input=ai_input, ai_analysis=analysis_result)

        logger.info(f"=== Analysis ({mode.upper()}) Finished ===")
        return analysis_result

    async def ask_question(self, question: str, date: str = None, mode: str = 'midday') -> str:
        """
        Q&A mode: answer user questions based on cached data.
        Detects trend keywords and routes to trend analysis if needed.
        """
        logger.info(f"=== Q&A Mode: '{question}' ===")

        # Detect trend question
        if self._detect_trend(question):
            return await self._run_trend_analysis(question)

        # Single-day question: load cached data
        if date:
            raw_data = self.db.get_record_by_date(date, mode)
            ai_result = self.db.get_analysis_by_date(date, mode)
        else:
            record = self.db.get_last_analysis(mode)
            if record:
                raw_data = record.get('raw_data')
                ai_result = record.get('ai_result')
            else:
                raw_data = None
                ai_result = None

        if not raw_data and not ai_result:
            return "没有找到缓存的分析数据。请先运行一次分析（python -m src.main --mode midday）再进行追问。"

        analyst = GeminiClient()
        qa_prompt = self.config['prompts'].get('qa_prompt', '')
        answer = analyst.ask_question(raw_data, ai_result, question, qa_prompt)
        return answer

    def _detect_trend(self, question: str) -> bool:
        """Detect if the question is about trends (multi-day analysis)."""
        trend_keywords = ['趋势', '走势', '一周', '一个月', '近期', '最近', '这周', '本周', '上周', '本月', '上月', '几天', '多天']
        return any(kw in question for kw in trend_keywords)

    async def _run_trend_analysis(self, question: str) -> str:
        """Run trend analysis over multiple days of historical data."""
        # Determine how many days to look back
        if '一个月' in question or '本月' in question or '上月' in question:
            days = 30
        elif '两周' in question:
            days = 14
        else:
            days = 7  # default to one week

        # Try close records first (more complete), fallback to midday
        records = self.db.get_records_range(mode='close', days=days)
        if not records:
            records = self.db.get_records_range(mode='midday', days=days)

        if not records:
            return f"没有找到最近{days}天的历史数据，无法进行趋势分析。"

        # Build trend context
        trend_context = []
        for r in reversed(records):  # chronological order
            day_summary = {
                "date": r['date'],
                "ai_result": r.get('ai_result'),
            }
            raw = r.get('raw_data')
            if raw:
                day_summary["market_breadth"] = raw.get('market_breadth')
                day_summary["indices"] = raw.get('indices')
            trend_context.append(day_summary)

        analyst = GeminiClient()
        trend_prompt = self.config['prompts'].get('trend_prompt', '')
        answer = analyst.ask_question(
            context_data={"trend_data": trend_context, "days": days},
            ai_result=None,
            question=question,
            system_prompt=trend_prompt
        )
        return answer
