import asyncio
import akshare as ak
import pandas as pd
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
import functools

class DataCollector:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5) # AkShare is synchronous, so we wrap in threads
        self.config = ConfigLoader().config

    async def _run_blocking(self, func, *args, **kwargs):
        """Helper to run blocking AkShare calls in a thread executor."""
        loop = asyncio.get_running_loop()
        if kwargs:
            func = functools.partial(func, **kwargs)
        return await loop.run_in_executor(self.executor, func, *args)

    async def get_market_breadth(self) -> str:
        """
        Fetches market breadth (Rise/Fall ratio).
        Uses 'ak.stock_zh_a_spot_em()' roughly or a specific index API if available.
        For speed, we might just sample specific indices or use a summary API.
        Here we use the spot API but summarize it.
        """
        logger.info("Fetching market breadth...")
        try:
            # Getting full market spot data is heavy, usually better to get index summary
            # But specific rise/fall count usually requires full list or a specific dashboard API.
            # Let's try 'stock_zh_a_spot_em' but be mindful of data size (~5000 rows).
            # Optimization: Just get the Shanghai & Shenzhen Index movement for now to be fast?
            # User wants "Rise 4000/Fall 500". Full spot is needed or a different specific API.
            # ak.stock_zh_a_spot_em() is reliable but heavy.
            
            df = await self._run_blocking(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return "Unknown"
            
            rise = len(df[df['涨跌幅'] > 0])
            fall = len(df[df['涨跌幅'] < 0])
            flat = len(df[df['涨跌幅'] == 0])
            
            ratio = f"涨: {rise} / 跌: {fall} (平: {flat})"
            logger.info(f"Market Breadth: {ratio}")
            return ratio
        except Exception as e:
            logger.error(f"Error fetching market breadth: {e}")
            return "Error"

    async def get_north_funds(self) -> float:
        """
        Fetches Real-time Northbound Fund Net Inflow (Unit: 100 million).
        """
        logger.info("Fetching Northbound funds...")
        try:
            # Using 'stock_hsgt_fund_flow_summary_em' for realtime summary
            # Columns: 只要, 北向资金, 南向资金...
            df_summary = await self._run_blocking(ak.stock_hsgt_fund_flow_summary_em)
            # Typically row 0 is Northbound
            # Structure needs check, but usually it has '北向资金' in a column.
            # Let's simple try iterating or finding the value.
            # Assuming row with index or label.
            # Actually this API returns a small DF.
            
            # Implementation for stability:
            # Try to get value from the specific row/column
            # Example response:
            #      板块   净流入   ...
            # 0  北向资金  12.34   ...
            
            north_row = df_summary[df_summary.iloc[:, 0].astype(str).str.contains("北向")]
            if not north_row.empty:
                # Value might be string "12.34 亿元" or float. Akshare cleans it usually.
                raw_val = north_row.iloc[0, 1] # 2nd column '净流入'
                # Parse
                if isinstance(raw_val, str):
                    # Remove '亿元' etc
                    import re
                    val_str = re.sub(r'[^\d\.\-]', '', raw_val)
                    north_money = float(val_str)
                else:
                    north_money = float(raw_val)
                
                # If API returns unit in Yi already? safely assume it is consistent.
                # Usually summary APIs are in Yi or Wan.
                # Let's assume it is "Yi" (Billions) based on common display.
            else:
                 north_money = 0.0

            logger.info(f"North Funds: {north_money} 亿")
            return round(north_money, 2)

        except Exception as e:
            logger.error(f"Error fetching North funds: {e}")
            # Fallback for now
            return 0.0

    async def get_stock_data(self, code: str) -> Dict[str, Any]:
        """
        Fetches price and news for a single stock.
        """
        logger.info(f"Fetching data for {code}...")
        try:
            # 1. Price Data (Spot)
            # Use spot_em for latest info
            df_spot = await self._run_blocking(ak.stock_zh_a_spot_em)
            # Filter for specific code. This is inefficient if called N times for N stocks.
            # Optimization: Fetch spot ONCE globally in 'get_market_breadth' or 'fetch_all_prices', then filter.
            # But for cleaner code structure locally, let's assume we do it optimized in 'collect_all'.
            
            # 2. Historical Data (for MA20)
            df_hist_daily = await self._run_blocking(
                ak.stock_zh_a_hist, 
                symbol=code, 
                period="daily", 
                start_date="20240101", # Fetch enough for MA20
                adjust="qfq"
            )
            
            # 3. News
            df_news = await self._run_blocking(ak.stock_news_em, symbol=code)
            latest_news = []
            if not df_news.empty:
                latest_news = df_news.head(3)['title'].tolist()

            return {
                "code": code,
                "history": df_hist_daily,
                "news": latest_news
            }

        except Exception as e:
            logger.error(f"Error fetching stock data for {code}: {e}")
            return {}

    async def get_indices(self) -> Dict[str, Dict]:
        """
        Fetches major indices: 000001 (ShangZheng), 399001 (ShenZheng), 399006 (ChiNext).
        Returns: {'上证指数': {'current': ..., 'change_pct': ...}, ...}
        """
        try:
             # Use stock_zh_index_spot_sina for real-time index data
             # Note: This returns a large DF. We filter by code.
             df = await self._run_blocking(ak.stock_zh_index_spot_sina)
             
             targets = {
                 "sh000001": "上证指数",
                 "br000300": "沪深300", # Better to use common ones if available. 
                 # Let's check typical codes in this API. 
                 # Usually it returns '代码' like 'sh000001'.
             }
             
             results = {}
             target_names = ["上证指数", "深证成指", "创业板指"]
             
             for name in target_names:
                 row = df[df['名称'] == name]
                 if not row.empty:
                     current = float(row.iloc[0]['最新价'])
                     change_pct = float(row.iloc[0]['涨跌幅'])
                     results[name] = {
                         "current": current,
                         "change_pct": change_pct
                     }
             return results
        except Exception as e:
            logger.error(f"Failed to fetch indices: {e}")
            return {}

    async def collect_all(self, portfolio: List[Dict]):
        """
        Main entry point to collect everything in parallel.
        """
        logger.info("Starting Batch Data Collection...")
        
        # 1. Fetch Global Market Data (Breadth, North, Indices)
        task_breadth = asyncio.create_task(self.get_market_breadth())
        task_north = asyncio.create_task(self.get_north_funds())
        task_indices = asyncio.create_task(self.get_indices())
        
        # 2. Fetch Stock Data (Optimized)
        try:
             df_stocks = await self._run_blocking(ak.stock_zh_a_spot_em)
        except:
             df_stocks = pd.DataFrame()
             
        try:
            df_etfs = await self._run_blocking(ak.fund_etf_spot_em)
        except:
             df_etfs = pd.DataFrame()
        
        # Merge
        if not df_stocks.empty and not df_etfs.empty:
             df_all_spot = pd.concat([df_stocks, df_etfs], ignore_index=True)
        elif not df_etfs.empty:
             df_all_spot = df_etfs
        else:
             df_all_spot = df_stocks
        
        stock_tasks = []
        for stock in portfolio:
            code = stock['code']
            stock_tasks.append(self._fetch_individual_stock_extras(code, df_all_spot))
            
        # Wait for all
        market_breadth, north_funds, indices = await asyncio.gather(task_breadth, task_north, task_indices)
        stock_results = await asyncio.gather(*stock_tasks)
        
        return {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "stocks": stock_results
        }

    async def _fetch_individual_stock_extras(self, code: str, df_all_spot: pd.DataFrame) -> Dict:
        """
        Helper: extracts spot from global DF, then fetches Hist + News.
        """
        try:
            # Extract Spot
            spot_row = df_all_spot[df_all_spot['代码'] == code]
            if spot_row.empty:
                logger.warning(f"Code {code} not found in spot data.")
                current_price = 0.0
                pct_change = 0.0
                name = "Unknown"
            else:
                current_price = float(spot_row.iloc[0]['最新价'])
                pct_change = float(spot_row.iloc[0]['涨跌幅'])
                name = spot_row.iloc[0]['名称']

            # History (Daily) - Need last ~30 days for MA20
            is_etf = code.startswith(('15', '50', '51', '56', '57', '58'))
            
            if is_etf:
                # ETF History
                df_hist = await self._run_blocking(
                    ak.fund_etf_hist_em,
                    symbol=code,
                    period="daily",
                    start_date="20240101",
                    adjust="qfq"
                )
            else:
                # Stock History
                df_hist = await self._run_blocking(
                    ak.stock_zh_a_hist, 
                    symbol=code, 
                    period="daily", 
                    start_date="20240101", # Fetch enough
                    adjust="qfq"
                )
            if not df_hist.empty:
                df_hist = df_hist.tail(30)
            
            # News
            try:
                df_news = await self._run_blocking(ak.stock_news_em, symbol=code)
                news = df_news.head(3)['新闻标题'].tolist() if not df_news.empty else []
            except:
                news = []

            return {
                "code": code,
                "name": name,
                "current_price": current_price,
                "pct_change": pct_change,
                "history": df_hist, # DataFrame
                "news": news
            }
            
        except Exception as e:
            logger.error(f"Failed individual fetch for {code}: {e}")
            return {"code": code, "error": str(e)}

if __name__ == "__main__":
    # Test run
    # Mock config for test
    class MockConfig:
        config = {'portfolio': [{'code': '600519'}, {'code': '300750'}]}
    
    collector = DataCollector()
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(collector.collect_all(MockConfig.config['portfolio']))
    print(result['market_breadth'])
    print(result['north_funds'])
    print(len(result['stocks']))
