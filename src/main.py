import asyncio
import sys
import argparse
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.collector.data_fetcher import DataCollector
from src.processor.data_processor import DataProcessor
from src.analyst.gemini_client import GeminiClient
from src.reporter.feishu_client import FeishuClient

import json
from pathlib import Path

async def main_midday_check(dry_run: bool = False, replay: bool = False):
    logger.info("=== Starting Sentinel Midday Check ===")
    
    # 0. Load Config & dependencies
    config = ConfigLoader().config
    portfolio = config.get('portfolio', [])
    data_path = Path("data/latest_context.json")
    
    # Replay Mode: Skip Fetching
    if replay:
        if not data_path.exists():
             logger.error("No historical data found for replay. Run normal mode first.")
             return
        logger.info("Replay Mode: Loading data from local file...")
        with open(data_path, 'r', encoding='utf-8') as f:
            ai_input = json.load(f)
        # Skip steps 1 & 2
    else:            
        if not portfolio:
            logger.warning("Portfolio is empty. Exiting.")
            return
    
        # 1. Collect Data (Async)
        collector = DataCollector()
        raw_data = await collector.collect_all(portfolio)
        
        market_breadth = raw_data['market_breadth']
        north_funds = raw_data['north_funds']
        stock_data_list = raw_data['stocks']
        indices = raw_data.get('indices', {})
        
        logger.info(f"Data Collected. Market Breadth: {market_breadth}, North Funds: {north_funds}")
    
        # 2. Process Data (Indicators)
        processor = DataProcessor()
        processed_stocks = []
        for stock_raw in stock_data_list:
            # Calculate MA20, Bias
            stock_indicators = processor.calculate_indicators(stock_raw)
            processed_stocks.append(stock_indicators)
            
        # Pre-calculate signals (Rule-based)
        processed_stocks = processor.generate_signals(processed_stocks, north_funds)
    
        # Prepare data for AI
        ai_input = {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "stocks": processed_stocks
        }
        
        # SAVE Context for Replay
        try:
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(ai_input, f, ensure_ascii=False, indent=2)
            logger.info(f"Context saved to {data_path}")
        except Exception as e:
            logger.warning(f"Failed to save context context: {e}")

    # 3. AI Analysis
    analyst = GeminiClient()
    try:
        if dry_run and not replay:
            logger.info("Dry Run Mode: Skipping actual Gemini API call (Mocking response).")
            analysis_result = {
                "market_sentiment": "DryRun Mode", 
                "summary": "This is a dry run.", 
                "actions": []
            }
        else:
            # Replay Mode OR Normal Mode
            analysis_result = analyst.analyze(ai_input)
            
        # --- POST-PROCESSING: Inject Real-time Data (Indices & Pct Change) ---
        # 1. Format Indices Info
        indices_str = []
        for name, data in indices.items():
            pct = data.get('change_pct', 0.0)
            sign = "+" if pct > 0 else ""
            indices_str.append(f"{name} {sign}{pct}%")
        analysis_result['indices_info'] = " / ".join(indices_str)
        
        # 2. MATCH Stock Pct Change to Actions
        # Create map: code -> pct_change
        stock_map = {s['code']: s.get('pct_change', 0.0) for s in processed_stocks}
        
        for action in analysis_result.get('actions', []):
            code = action.get('code')
            if code in stock_map:
                pct = stock_map[code]
                sign = "+" if pct > 0 else ""
                color = "🔴" if pct > 0 else "🟢" # China: Red is up
                action['pct_change_str'] = f"`{color} {sign}{pct}%`"
            else:
                 action['pct_change_str'] = ""

        logger.info("AI Analysis Completed.")
        logger.debug(f"Analysis Result: {analysis_result}")
        
    except Exception as e:
        logger.error(f"AI Analysis Failed: {e}")
        return

    # 4. Report
    reporter = FeishuClient()
    if dry_run:
        logger.info("Dry Run Mode: Skipping Feishu Push.")
        print("\n--- Feishu Card Content ---")
        # For replay + dry_run, maybe we want to see the card printed?
        print(reporter._construct_card(analysis_result))
    else:
        reporter.send_card(analysis_result)

    logger.info("=== Sentinel Check Finished ===")

def entry_point():
    parser = argparse.ArgumentParser(description="Project Sentinel V2")
    parser.add_argument('--mode', type=str, default='midday', choices=['midday', 'close'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without calling expensive APIs or sending notifications')
    parser.add_argument('--replay', action='store_true', help='Replay analysis using last saved data')
    
    args = parser.parse_args()
    
    if args.mode == 'midday':
        asyncio.run(main_midday_check(dry_run=args.dry_run, replay=args.replay))
    else:
        logger.info(f"Mode {args.mode} not implemented yet.")

if __name__ == "__main__":
    entry_point()
