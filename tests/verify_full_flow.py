import asyncio
import sys
import logging
from src.collector.data_fetcher import DataCollector
from src.service.analysis_service import AnalysisService
from src.utils.config_loader import ConfigLoader

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("VERIFIER")

async def verify_data_collection():
    logger.info(">>> 1. Verifying Data Collection (Source Fallback)...")
    collector = DataCollector()
    
    # Check if sources are loaded
    if len(collector.sources) < 2:
        logger.error(f"❌ Expected 2 sources (Efinance, Akshare), found {len(collector.sources)}")
        for s in collector.sources:
            logger.info(f"   - {s.get_source_name()}")
    else:
        logger.info(f"✅ Loaded {len(collector.sources)} sources:")
        for s in collector.sources:
            logger.info(f"   - {s.get_source_name()}")

    # Test Spot Data
    logger.info("   Testing fetch_spot_data...")
    try:
        df = await collector._fetch_with_fallback('fetch_spot_data')
        if df is not None and not df.empty:
            logger.info(f"✅ Spot Data fetched successfully. Shape: {df.shape}")
            logger.info(f"   Columns: {df.columns.tolist()}")
            if 'code' not in df.columns or 'current_price' not in df.columns:
                 logger.error("❌ Spot Data missing required columns!")
        else:
            logger.error("❌ Spot Data returned empty or None!")
    except Exception as e:
        logger.error(f"❌ fetch_spot_data crashed: {e}")

    # Test Individual Stock
    test_code = "600519"
    logger.info(f"   Testing individual stock fetch for {test_code}...")
    try:
        portfolio = [{"code": test_code, "market": "CN"}]
        result = await collector.collect_all(portfolio)
        stocks = result.get('stocks', [])
        if not stocks:
             logger.error("❌ No stock data returned in collect_all!")
        else:
            s = stocks[0]
            logger.info(f"✅ Stock Data for {s.get('code')}: Price={s.get('current_price')}")
            # Check History
            if 'history' in s and not s['history'].empty:
                 logger.info(f"✅ History Data present. Rows: {len(s['history'])}")
            else:
                 logger.warning("⚠️ History Data missing or empty!")
    except Exception as e:
        logger.error(f"❌ collect_all crashed: {e}")

async def verify_analysis_service():
    logger.info("\n>>> 2. Verifying Analysis Service (Dry Run)...")
    service = AnalysisService()
    try:
        # Force dry_run=True to avoid API costs
        result = await service.run_analysis(mode='midday', dry_run=True)
        if 'error' in result:
            logger.error(f"❌ Analysis Service returned error: {result['error']}")
        else:
            logger.info("✅ Analysis Service completed successfully.")
            logger.info(f"   Summary: {result.get('summary')}")
            actions = result.get('actions', [])
            logger.info(f"   Generated {len(actions)} actions.")
    except Exception as e:
        logger.error(f"❌ Analysis Service crashed: {e}")

if __name__ == "__main__":
    logger.info("=== STARTING COMPREHENSIVE VERIFICATION ===")
    
    # We run them sequentially to observe output clearly
    try:
        asyncio.run(verify_data_collection())
        asyncio.run(verify_analysis_service())
        logger.info("\n=== VERIFICATION FINISHED ===")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Global Crash: {e}")
