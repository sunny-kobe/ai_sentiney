import asyncio
import functools
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger
from src.collector.sources.efinance_source import EfinanceSource
from src.collector.sources.akshare_source import AkshareSource
from src.collector.sources.tencent_source import TencentSource

from tenacity import retry, stop_after_attempt, wait_exponential

class DataCollector:
    def __init__(self):
        # GitHub Actions runners / Standard Cloud Instances (2-4 vCPUs)
        self.executor = ThreadPoolExecutor(max_workers=16)
        self.config = ConfigLoader().config
        
        # Priority: Tencent -> Efinance -> AkShare
        self.sources = [TencentSource(), EfinanceSource(), AkshareSource()]
        
        # Circuit Breaker: Track sources that have failed completely
        self._disabled_sources = set()

    async def _run_blocking(self, func, *args, **kwargs):
        """
        Helper to run blocking calls in a thread executor with smart retry logic and timeout.
        """
        loop = asyncio.get_running_loop()
        timeout = kwargs.pop('timeout', 5) # Default 5s timeout (Fail Fast)
        
        @retry(
            stop=stop_after_attempt(3), 
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True
        )
        def retriable_func():
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"API Call {func.__name__} failed: {e}. Retrying...")
                raise e

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self.executor, retriable_func),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Command {func.__name__} timed out after {timeout}s.")
            raise
        except Exception as e:
            # logger.error(f"Command {func.__name__} failed definitively after retries.")
            raise e

    async def _fetch_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        """
        Try to fetch data from sources in priority order.
        """
        last_exception = None
        for source in self.sources:
            source_name = source.get_source_name()
            
            # Circuit Breaker Check
            if source_name in self._disabled_sources:
                # logger.debug(f"Skipping disabled source: {source_name}")
                continue

            try:
                func = getattr(source, method_name)
                # Run sync source method in thread pool
                result = await self._run_blocking(func, *args, **kwargs)
                
                # Check for validity
                if result is not None:
                    if isinstance(result, pd.DataFrame) and result.empty:
                        continue # Try next source if Empty DataFrame
                    return result
            except Exception as e:
                logger.warning(f"Source {source_name} failed for {method_name}: {e}")
                
                # Circuit Breaker Logic: Mark source as disabled if it fails
                # We assume network/timeout errors are persistent for the session
                self._disabled_sources.add(source_name)
                logger.error(f"Circuit Breaker: Disabling source {source_name} due to failure.")
                
                last_exception = e
                continue
        
        logger.error(f"All sources failed for {method_name}.")
        return None

    def _get_dynamic_start_date(self, days_lookback: int = 60) -> str:
        return (datetime.now() - timedelta(days=days_lookback)).strftime("%Y%m%d")

    async def get_market_breadth(self) -> str:
        """
        Fetches market breadth (Rise/Fall ratio).
        """
        logger.info("Fetching market breadth...")
        # Try abstraction first, or fallback to current manual logic if needed?
        # Current logic is specific with 'stock_zh_a_spot_em'.
        # Let's rely on AkShareSource's fetch_market_breadth for simplicity?
        # But wait, AkshareSource's impl was a placeholder that returns string.
        # The original logic calculated it from spot data.
        # Let's stick to using fetch_market_breadth from interfaces.
        res = await self._fetch_with_fallback('fetch_market_breadth')
        return res if res else "Unknown"

    async def get_north_funds(self) -> float:
        """
        Fetches Real-time Northbound Fund Net Inflow (Unit: 100 million).
        Kept specific to AkShare for now as it's specialized.
        """
        logger.info("Fetching Northbound funds...")
        try:
            df = await self._run_blocking(ak.stock_hsgt_fund_flow_summary_em)
            if df is None or df.empty:
                return 0.0

            mask = df.astype(str).apply(lambda x: x.str.contains('北向')).any(axis=1)
            north_rows = df[mask]
            
            if north_rows.empty:
                return 0.0
            
            # Heuristic to find value column
            value_col = next((col for col in df.columns if '净流入' in str(col)), None)
            
            if not value_col:
                raw_val = north_rows.iloc[0, 1]
            else:
                raw_val = north_rows.iloc[0][value_col]

            val_str = str(raw_val)
            val_clean = re.sub(r'[^\d\.\-]', '', val_str)
            
            try:
                return round(float(val_clean), 2)
            except ValueError:
                return 0.0

        except Exception as e:
            logger.error(f"Error fetching North funds: {e}")
            return 0.0

    async def get_indices(self) -> Dict[str, Dict]:
        """
        Fetches major indices.
        """
        try:
             df = await self._run_blocking(ak.stock_zh_index_spot_sina)
             target_map = {
                 "上证指数": "sh000001",
                 "深证成指": "sz399001", 
                 "创业板指": "sz399006"
             }
             results = {}
             for name in target_map.keys():
                 row = df[df['名称'] == name]
                 if not row.empty:
                     try:
                         results[name] = {
                             "current": float(row.iloc[0]['最新价']),
                             "change_pct": float(row.iloc[0]['涨跌幅'])
                         }
                     except (ValueError, KeyError):
                         continue
             return results
        except Exception as e:
            logger.error(f"Failed to fetch indices: {e}")
            return {}

    async def get_macro_news(self) -> Dict[str, List[str]]:
        """
        Fetches macro news.
        """
        logger.info("Fetching macro news...")
        result: Dict[str, List[str]] = {"telegraph": [], "ai_tech": []}
        
        try:
            today_str = datetime.now().strftime('%Y%m%d')
            df_news = await self._run_blocking(ak.news_cctv, date=today_str)
            
            if df_news is None or df_news.empty:
                 yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
                 df_news = await self._run_blocking(ak.news_cctv, date=yesterday_str)

            if df_news is not None and not df_news.empty:
                result["telegraph"] = df_news.head(10)['title'].tolist()
            else:
                df_global = await self._run_blocking(ak.stock_info_global_em)
                if df_global is not None and not df_global.empty:
                    result["telegraph"] = df_global.head(10)['标题'].tolist()

        except Exception as e:
            logger.warning(f"Failed to fetch macro news: {e}")
        
        ai_keywords = ['人工智能', 'AI', '芯片', '半导体', '算力', '大模型', 'GPU', '英伟达', '华为', '科技', '机器']
        if result["telegraph"]:
            result["ai_tech"] = [
                n for n in result["telegraph"] 
                if any(k in n for k in ai_keywords)
            ][:5]
        
        return result

    async def collect_all(self, portfolio: List[Dict]):
        """
        Main entry point. Orchestrates parallel data fetching.
        """
        logger.info("Starting Batch Data Collection (Dual Source)...")
        
        global_tasks = [
            self.get_market_breadth(),
            self.get_north_funds(),
            self.get_indices(),
            self.get_macro_news()
        ]
        
        # 2. Fetch Spot Data via Fallback
        # This will try Efinance first, then AkShare
        df_all_spot = await self._fetch_with_fallback('fetch_spot_data')
        if df_all_spot is None:
            df_all_spot = pd.DataFrame()
            logger.warning("All sources failed to fetch bulk spot data. Will rely on individual fetch.")
        
        stock_tasks = []
        for stock in portfolio:
            code = stock['code']
            stock_tasks.append(self._fetch_individual_stock_extras(code, stock.get('name', 'Unknown'), df_all_spot))
            
        try:
            global_results = await asyncio.gather(*global_tasks, return_exceptions=True)
            stock_results = await asyncio.gather(*stock_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Critical error during gather: {e}")
            # Try to salvage whatever we have
            global_results = [None] * 4
            stock_results = []

        market_breadth = global_results[0] if global_results and not isinstance(global_results[0], Exception) else "Error"
        north_funds = global_results[1] if global_results and not isinstance(global_results[1], Exception) else 0.0
        indices = global_results[2] if global_results and not isinstance(global_results[2], Exception) else {}
        macro_news = global_results[3] if global_results and not isinstance(global_results[3], Exception) else {"telegraph": [], "ai_tech": []}
        
        valid_stocks = []
        if stock_results:
            valid_stocks = [res for res in stock_results if not isinstance(res, Exception) and isinstance(res, dict) and "error" not in res]

        return {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "macro_news": macro_news,
            "stocks": valid_stocks
        }

    async def _fetch_individual_stock_extras(self, code: str, stock_name: str, df_all_spot: pd.DataFrame) -> Dict:
        """
        Fetches History and News for a specific stock using fallback.
        """
        try:
            # 1. Spot Data logic
            current_price = 0.0
            pct_change = 0.0
            name = stock_name

            if not df_all_spot.empty:
                spot_row = df_all_spot[df_all_spot['code'] == code]
                if not spot_row.empty:
                    try:
                        current_price = float(spot_row.iloc[0]['current_price'])
                        pct_change = float(spot_row.iloc[0]['pct_change'])
                        # name = spot_row.iloc[0]['name'] # Trust config name? Source name might be different
                    except (ValueError, KeyError, IndexError):
                        pass

            # 2. Try Individual Real-Time Quote (Fallback for Spot)
            # This is critical if bulk spot fetch failed (e.g. Efinance timeout)
            if current_price == 0.0:
                quote = await self._fetch_with_fallback('fetch_single_quote', code=code)
                if quote:
                    try:
                        current_price = float(quote['current_price'])
                        pct_change = float(quote['pct_change'])
                        # name = quote['name'] 
                    except Exception as e:
                        logger.warning(f"Failed to parse quote for {code}: {e}")

            # 3. Fetch Prices (History) via Fallback
            df_hist = await self._fetch_with_fallback('fetch_prices', code=code, count=30)
            if df_hist is None:
                df_hist = pd.DataFrame()
                logger.warning(f"History fetch failed for {code}")

            if not df_hist.empty:
                # Fallback for current_price if spot failed
                if current_price == 0.0:
                    try:
                        current_price = float(df_hist.iloc[-1]['close'])
                        if len(df_hist) >= 2:
                            prev_close = float(df_hist.iloc[-2]['close'])
                            if prev_close > 0:
                                pct_change = ((current_price - prev_close) / prev_close) * 100
                    except Exception:
                        pass
                
                df_hist = df_hist.tail(30)
            
            # 3. Fetch News via Fallback
            news_str = await self._fetch_with_fallback('fetch_news', code=code, count=5)
            # news_str returns string separated by ;
            news_list = news_str.split("; ") if news_str else []

            return {
                "code": code,
                "name": name,
                "current_price": current_price,
                "pct_change": pct_change,
                "history": df_hist,
                "news": news_list
            }
            
        except Exception as e:
            logger.error(f"Failed individual fetch for {code}: {e}")
            return {"code": code, "error": str(e)}

if __name__ == "__main__":
    # Smoke Test
    class MockConfig:
        config = {'portfolio': [{'code': '600519', 'name': '茅台'}]}
    
    start_t = datetime.now()
    collector = DataCollector()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(collector.collect_all(MockConfig.config['portfolio']))
    
    print(f"Time taken: {datetime.now() - start_t}")
    print(f"Market Breadth: {result['market_breadth']}")
    print(f"North Funds: {result['north_funds']}")
    if result['stocks']:
        print(f"Sample Stock Price: {result['stocks'][0]['current_price']}")
        print(f"Sample Hist Shape: {result['stocks'][0]['history'].shape}")
