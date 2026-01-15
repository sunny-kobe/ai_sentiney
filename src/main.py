import asyncio
import sys
import argparse
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.collector.data_fetcher import DataCollector
from src.processor.data_processor import DataProcessor
from src.analyst.gemini_client import GeminiClient
from src.reporter.feishu_client import FeishuClient

async def main_midday_check(dry_run: bool = False):
    logger.info("=== Starting Sentinel Midday Check ===")
    
    # 0. Load Config & dependencies
    config = ConfigLoader().config
    portfolio = config.get('portfolio', [])
    
    if not portfolio:
        logger.warning("Portfolio is empty. Exiting.")
        return

    # 1. Collect Data (Async)
    collector = DataCollector()
    raw_data = await collector.collect_all(portfolio)
    
    market_breadth = raw_data['market_breadth']
    north_funds = raw_data['north_funds']
    stock_data_list = raw_data['stocks']
    
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

    # 3. AI Analysis
    # Prepare data for AI
    ai_input = {
        "market_breadth": market_breadth,
        "north_funds": north_funds,
        "stocks": processed_stocks
    }
    
    analyst = GeminiClient()
    try:
        if dry_run:
            logger.info("Dry Run Mode: Skipping actual Gemini API call (Mocking response).")
            analysis_result = {
                "market_sentiment": "DryRun Mode", 
                "summary": "This is a dry run.", 
                "actions": []
            }
        else:
            analysis_result = analyst.analyze(ai_input)
            
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
        print(reporter._construct_card(analysis_result))
    else:
        reporter.send_card(analysis_result)

    logger.info("=== Sentinel Check Finished ===")

def entry_point():
    parser = argparse.ArgumentParser(description="Project Sentinel V2")
    parser.add_argument('--mode', type=str, default='midday', choices=['midday', 'close'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without calling expensive APIs or sending notifications')
    
    args = parser.parse_args()
    
    if args.mode == 'midday':
        asyncio.run(main_midday_check(dry_run=args.dry_run))
    else:
        logger.info(f"Mode {args.mode} not implemented yet.")

if __name__ == "__main__":
    entry_point()
