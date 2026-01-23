
import asyncio
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List

from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.collector.data_fetcher import DataCollector
from src.processor.data_processor import DataProcessor
from src.analyst.gemini_client import GeminiClient
from src.reporter.feishu_client import FeishuClient
from src.storage.database import SentinelDB

async def collect_and_process_data(portfolio: List[Dict]) -> Dict[str, Any]:
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

def post_process_result(analysis_result: Dict, ai_input: Dict) -> Dict:
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
    stock_map_by_code = {s['code']: s.get('pct_change', 0.0) for s in processed_stocks}
    stock_map_by_name = {s['name']: s.get('pct_change', 0.0) for s in processed_stocks}
    
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

async def run_sentinel_check(mode: str, dry_run: bool = False, replay: bool = False):
    """
    Unified workflow for both midday and close checks.
    """
    logger.info(f"=== Starting Sentinel Check ({mode.upper()}) ===")
    
    config = ConfigLoader().config
    portfolio = config.get('portfolio', [])
    data_path = Path("data/latest_context.json")
    data_path.parent.mkdir(parents=True, exist_ok=True)
    
    ai_input = None

    # --- Step 1: Data Preparation ---
    if replay:
        # Try DB first, then legacy JSON
        db = SentinelDB()
        latest_record = db.get_latest_record(mode=mode)
        
        if latest_record:
            logger.info("Replay Mode: Loading data from SQLite DB...")
            ai_input = latest_record
        elif data_path.exists():
            logger.info("Replay Mode: Loading data from local JSON file (Legacy)...")
            with open(data_path, 'r', encoding='utf-8') as f:
                ai_input = json.load(f)
        else:
             logger.error("No historical data found for replay.")
             return
    else:
        if not portfolio:
            logger.warning("Portfolio is empty. Exiting.")
            return
        
        # Live Collection
        try:
            ai_input = await collect_and_process_data(portfolio)
            
            # Save context for debugging/replay
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(ai_input, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Data collection failed: {e}")
            return

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
                analysis_result = analyst.analyze(ai_input)
            elif mode == 'close':
                system_prompt = config['prompts'].get('close_review')
                if not system_prompt:
                    logger.warning("No close_review prompt found, using default.")
                    analysis_result = analyst.analyze(ai_input)
                else:
                    analysis_result = analyst.analyze_with_prompt(ai_input, system_prompt)
        
        # Unified Post-Processing
        analysis_result = post_process_result(analysis_result, ai_input)
        
        logger.info(f"{mode.capitalize()} Analysis Completed.")
        
    except Exception as e:
        logger.error(f"AI Analysis Failed: {e}")
        # Even if AI fails, we might want to exit or send error notification
        # For now, following original logic: exit
        sys.exit(1)

    # --- Step 3: Reporting ---
    reporter = FeishuClient()
    if dry_run:
        logger.info("Dry Run Mode: Skipping Feishu Push.")
        if mode == 'midday':
            print(reporter._construct_card(analysis_result))
        else:
            print(reporter._construct_close_card(analysis_result))
    else:
        if mode == 'midday':
            reporter.send_card(analysis_result)
        else:
            reporter.send_close_card(analysis_result)

    # --- Step 4: Persistence ---
    if not dry_run or (dry_run and replay):
        if not dry_run: # Only save if not dry run (unless we change policy)
            SentinelDB().save_record(mode=mode, ai_input=ai_input, ai_analysis=analysis_result)

    logger.info(f"=== Sentinel Check ({mode.upper()}) Finished ===")

def entry_point():
    parser = argparse.ArgumentParser(description="Project Sentinel V2")
    parser.add_argument('--mode', type=str, default='midday', choices=['midday', 'close'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without calling expensive APIs or sending notifications')
    parser.add_argument('--replay', action='store_true', help='Replay analysis using last saved data')
    
    args = parser.parse_args()
    
    asyncio.run(run_sentinel_check(mode=args.mode, dry_run=args.dry_run, replay=args.replay))

if __name__ == "__main__":
    entry_point()
