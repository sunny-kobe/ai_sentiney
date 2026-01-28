import akshare as ak
import pandas as pd
from typing import Optional
from src.collector.source_interface import DataSource
from src.utils.logger import logger

class AkshareSource(DataSource):
    def get_source_name(self) -> str:
        return "AkShare"

    def fetch_market_breadth(self) -> str:
        try:
            # AkShare's market breadth API or similar
            # For simplicity, we might just return a timestamp or basic index info if specific breadth API is heavy
            df = ak.stock_zh_a_spot_em()
            up = len(df[df['涨跌幅'] > 0])
            down = len(df[df['涨跌幅'] < 0])
            flat = len(df[df['涨跌幅'] == 0])
            return f"Up: {up}, Down: {down}, Flat: {flat}"
        except Exception as e:
            logger.error(f"AkShare market breadth fetch failed: {e}")
            return "N/A"

    def fetch_prices(self, code: str, period: str = 'daily', count: int = 20) -> Optional[pd.DataFrame]:
        """
        Fetch history from AkShare (Switching to Tencent backend for resilience).
        
        Tencent API (stock_zh_a_hist_tx) returns: [date, open, close, high, low, amount]
        """
        try:
            # Config check for symbol format? 
            # stock_zh_a_hist_tx needs 'sz000001' or 'sh600519'.
            # Our code is usually '000001'. Need helper to add prefix.
            symbol = self._get_tencent_symbol(code)
            
            # end_date = today
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=count*2)).strftime("%Y%m%d")

            df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start_date, end_date=end_date, adjust="qfq")
            
            if df is None or df.empty:
                return None

            # Standardize columns
            # Tencent result cols: date, open, close, high, low, amount
            df = df.rename(columns={
                'date': 'Date',
                'open': 'Open', 
                'close': 'Close',
                'high': 'High',
                'low': 'Low',
                'amount': 'Volume'
            })
            
            # Ensure Date is datetime
            df['Date'] = pd.to_datetime(df['Date'])
            
            return df
            
        except Exception as e:
            # logger.warning(f"AkShare history fetch failed for {code}: {e}")
            raise e

    def _get_tencent_symbol(self, code: str) -> str:
        """Helper to convert 600xxx -> sh600xxx"""
        if code.startswith('6'): return f"sh{code}"
        if code.startswith('0') or code.startswith('3'): return f"sz{code}"
        if code.startswith('4') or code.startswith('8'): return f"bj{code}"
        raise ValueError(f"Unsupported stock code format for Tencent API: {code}")

    def fetch_news(self, code: str, count: int = 5) -> str:
        try:
            # stock_news_em usually works for individual stock news
            df = ak.stock_news_em(symbol=code)
            if df is None or df.empty:
                return ""
            
            # Take top 'count' titles
            titles = df['新闻标题'].head(count).tolist()
            return "; ".join(titles)
        except Exception as e:
            logger.warning(f"AkShare news fetch failed: {e}")
            return ""

    def fetch_spot_data(self) -> Optional[pd.DataFrame]:
        try:
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
                
            # AkShare columns: 代码, 名称, 最新价, 涨跌幅 ...
            df = df.rename(columns={
                '代码': 'code',
                '名称': 'name',
                '最新价': 'current_price',
                '涨跌幅': 'pct_change'
            })
            
            required = ['code', 'name', 'current_price', 'pct_change']
            if not all(col in df.columns for col in required):
                return None
            
            return df[required]
        except Exception as e:
            logger.error(f"AkShare spot fetch failed: {e}")
            return None
