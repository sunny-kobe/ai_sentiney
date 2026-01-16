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


from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time

# Custom exception for clean retry filtering if needed, though generic Exception is fine for now
class FetchError(Exception):
    pass



class DataCollector:
    def __init__(self):
        # GitHub Actions runners / Standard Cloud Instances (2-4 vCPUs)
        # 32 workers is aggressive but acceptable for high-latency I/O (AkShare).
        self.executor = ThreadPoolExecutor(max_workers=16)
        self.config = ConfigLoader().config

        # Wrap blocking AK calls with retry logic dynamically or just use helper
        # For simplicity, we implement retry inside the _run_blocking helper or specifically in logical blocks.

    async def _run_blocking(self, func, *args, **kwargs):
        """
        Helper to run blocking AkShare calls in a thread executor with smart retry logic.
        Uses tenacity to retry on exceptions with exponential backoff.
        """
        loop = asyncio.get_running_loop()
        
        # Define the retry policy: 
        # Stop after 3 attempts
        # Wait 2^x * 1 second between retries (1s, 2s, 4s...)
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
            return await loop.run_in_executor(self.executor, retriable_func)
        except Exception as e:
            logger.error(f"Command {func.__name__} failed definitively after retries.")
            raise e


    def _get_dynamic_start_date(self, days_lookback: int = 60) -> str:
        """
        Calculates start date string (YYYYMMDD) dynamically.
        MA20 requires at least 20 trading days. 60 calendar days is a safe buffer.
        """
        return (datetime.now() - timedelta(days=days_lookback)).strftime("%Y%m%d")

    async def get_market_breadth(self) -> str:
        """
        Fetches market breadth (Rise/Fall ratio).
        Strategy: Use 'stock_zh_a_spot_em' to get a full market snapshot.
        """
        logger.info("Fetching market breadth...")
        try:
            # This is a heavy call (~5000 rows), but provides the most accurate "Temperature".
            df = await self._run_blocking(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return "Unknown"
            
            # Using vectorization for speed
            # '涨跌幅' column usually exists independently of column naming changes in AkShare 
            # (Akshare standardizes to中文 columns mostly).
            if '涨跌幅' not in df.columns:
                logger.error("Column '涨跌幅' not found in market spot data.")
                return "Data Error"

            rise = (df['涨跌幅'] > 0).sum()
            fall = (df['涨跌幅'] < 0).sum()
            flat = (df['涨跌幅'] == 0).sum()
            
            ratio = f"涨: {rise} / 跌: {fall} (平: {flat})"
            logger.info(f"Market Breadth: {ratio}")
            return ratio
        except Exception as e:
            logger.error(f"Error fetching market breadth: {e}")
            return "Error"

    async def get_north_funds(self) -> float:
        """
        Fetches Real-time Northbound Fund Net Inflow (Unit: 100 million).
        Robustly parses 'stock_hsgt_fund_flow_summary_em'.
        """
        logger.info("Fetching Northbound funds...")
        try:
            df = await self._run_blocking(ak.stock_hsgt_fund_flow_summary_em)
            if df is None or df.empty:
                return 0.0

            # Debugging column names if API changes
            # Expected columns usually relate to板块, 净流入 etc.
            # We look for the row containing "北向" in any column.
            
            # Convert entire DF to string to search safely
            mask = df.astype(str).apply(lambda x: x.str.contains('北向')).any(axis=1)
            north_rows = df[mask]
            
            if north_rows.empty:
                return 0.0
            
            # Extract the value. Usually in a column named '净流入' or similar.
            # We look for a column that looks like a number.
            # Heuristic: Find the column with '净流入' in name.
            value_col = None
            for col in df.columns:
                if '净流入' in str(col):
                    value_col = col
                    break
            
            if not value_col:
                # Fallback: assume the 2nd column (index 1) is the value
                raw_val = north_rows.iloc[0, 1]
            else:
                raw_val = north_rows.iloc[0][value_col]

            # Clean and Parse
            # Usually format is like "12.34" or "12.34亿元"
            val_str = str(raw_val)
            # Remove Chinese characters and keep numbers, dot, minus
            val_clean = re.sub(r'[^\d\.\-]', '', val_str)
            
            try:
                north_money = float(val_clean)
            except ValueError:
                logger.warning(f"Failed to parse North Money value: {val_str}")
                return 0.0

            # Unit standardization: AkShare usually uses existing units or 'Yi'.
            # Based on standard EastMoney display, this is usually in "Yi" (Billions) or "Wan".
            # CAUTION: Check API docs. 'stock_hsgt_fund_flow_summary_em' typically returns Yi.
            # We assume it is Yuan (Billions) consistent with common dashboards.
            
            return round(north_money, 2)

        except Exception as e:
            logger.error(f"Error fetching North funds: {e}")
            return 0.0

    async def get_indices(self) -> Dict[str, Dict]:
        """
        Fetches major indices: ShangZheng, ShenZheng, ChiNext.
        """
        try:
             # Use stock_zh_index_spot_sina for fast real-time data
             df = await self._run_blocking(ak.stock_zh_index_spot_sina)
             
             # Map standard names to what we want
             target_map = {
                 "上证指数": "sh000001",
                 "深证成指": "sz399001", 
                 "创业板指": "sz399006"
             }
             
             results = {}
             # Vectorized lookup is overkill for 3 items, loop is fine.
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
        Fetches macro news using robust logic.
        """
        logger.info("Fetching macro news...")
        result = {"telegraph": [], "ai_tech": []}
        
        try:
            # 1. CCTV News (Robust source)
            today_str = datetime.now().strftime('%Y%m%d')
            df_news = await self._run_blocking(ak.news_cctv, date=today_str)
            
            # Fallback to previous day if today is empty (e.g. morning before news)
            if df_news.empty:
                 yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
                 df_news = await self._run_blocking(ak.news_cctv, date=yesterday_str)

            if not df_news.empty:
                result["telegraph"] = df_news.head(10)['title'].tolist()
            else:
                # Secondary Fallback: Global financial news
                df_global = await self._run_blocking(ak.stock_info_global_em)
                if not df_global.empty:
                    result["telegraph"] = df_global.head(10)['标题'].tolist()

        except Exception as e:
            logger.warning(f"Failed to fetch macro news: {e}")
        
        # 2. Tech News Filtering
        ai_keywords = ['人工智能', 'AI', '芯片', '半导体', '算力', '大模型', 'GPU', '英伟达', '华为', '科技', '机器']
        if result["telegraph"]:
            # List comprehension with early exit logic is efficient enough here
            result["ai_tech"] = [
                n for n in result["telegraph"] 
                if any(k in n for k in ai_keywords)
            ][:5]
        
        return result

    async def collect_all(self, portfolio: List[Dict]):
        """
        Main entry point. Orchestrates parallel data fetching.
        """
        logger.info("Starting Batch Data Collection...")
        
        # 1. Global Market Data
        # We launch these first as they are independent of portfolio
        global_tasks = [
            self.get_market_breadth(),
            self.get_north_funds(),
            self.get_indices(),
            self.get_macro_news()
        ]
        
        # 2. Pre-fetch Spot Data for ALL stocks to minimize requests
        # Instead of calling 'get_individual_stock' N times for spot, we get it once.
        try:
            df_stocks = await self._run_blocking(ak.stock_zh_a_spot_em)
        except Exception:
            logger.warning("Failed to bulk fetch stock spot data.")
            df_stocks = pd.DataFrame()

        try:
            df_etfs = await self._run_blocking(ak.fund_etf_spot_em)
        except Exception:
            logger.warning("Failed to bulk fetch ETF spot data.")
            df_etfs = pd.DataFrame()
        
        # Merge spot data simply
        df_all_spot = pd.concat([df_stocks, df_etfs], ignore_index=True) if not df_stocks.empty or not df_etfs.empty else pd.DataFrame()
        
        # 3. Portfolio Level Fetching (History & News need individual calls)
        stock_tasks = []
        for stock in portfolio:
            code = stock['code']
            stock_tasks.append(self._fetch_individual_stock_extras(code, df_all_spot))
            
        # Await all
        global_results = await asyncio.gather(*global_tasks, return_exceptions=True)
        stock_results = await asyncio.gather(*stock_tasks, return_exceptions=True)
        
        # Unpack Global Results (Handling Exceptions safely)
        market_breadth = global_results[0] if not isinstance(global_results[0], Exception) else "Error"
        north_funds = global_results[1] if not isinstance(global_results[1], Exception) else 0.0
        indices = global_results[2] if not isinstance(global_results[2], Exception) else {}
        macro_news = global_results[3] if not isinstance(global_results[3], Exception) else {"telegraph": [], "ai_tech": []}
        
        # Filter valid stock results
        valid_stocks = [res for res in stock_results if not isinstance(res, Exception) and "error" not in res]

        return {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "macro_news": macro_news,
            "stocks": valid_stocks
        }

    async def _fetch_individual_stock_extras(self, code: str, df_all_spot: pd.DataFrame) -> Dict:
        """
        Fetches History and News for a specific stock.
        Uses cached spot data `df_all_spot` to avoid N spot requests.
        """
        try:
            # 1. Extract Spot Data from Bulk DataFrame
            current_price = 0.0
            pct_change = 0.0
            name = "Unknown"
            
            if not df_all_spot.empty:
                # Vectorized search
                # Assuming '代码' column. Akshare usually return 6 digit string.
                spot_row = df_all_spot[df_all_spot['代码'] == code]
                if not spot_row.empty:
                    try:
                        current_price = float(spot_row.iloc[0]['最新价'])
                        pct_change = float(spot_row.iloc[0]['涨跌幅'])
                        name = spot_row.iloc[0]['名称']
                    except (ValueError, KeyError, IndexError):
                        pass

            # 2. Fetch History (Dynamic Date)
            is_etf = code.startswith(('15', '50', '51', '56', '57', '58'))
            start_date = self._get_dynamic_start_date(days_lookback=60)
            
            fetch_func = ak.fund_etf_hist_em if is_etf else ak.stock_zh_a_hist
            
            try:
                df_hist = await self._run_blocking(
                    fetch_func,
                    symbol=code, 
                    period="daily", 
                    start_date=start_date,
                    adjust="qfq"
                )
            except Exception as e:
                logger.warning(f"History fetch failed for {code}: {e}")
                df_hist = pd.DataFrame()

            # Keep only last 30 for calculations
            if not df_hist.empty:
                df_hist = df_hist.tail(30)
            
            # 3. Fetch Specific Stock News
            # This is low priority, silence errors
            news = []
            try:
                df_news = await self._run_blocking(ak.stock_news_em, symbol=code)
                if not df_news.empty:
                    news = df_news.head(5)['新闻标题'].tolist()
            except Exception:
                pass

            return {
                "code": code,
                "name": name,
                "current_price": current_price,
                "pct_change": pct_change,
                "history": df_hist,
                "news": news
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
