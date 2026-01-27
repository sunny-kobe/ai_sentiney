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
        try:
            # AkShare uses 'sh600519' format sometimes, but often just code for specific APIs
            # stock_zh_a_hist usually takes just the 6 digits
            df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
            
            if df is None or df.empty:
                return None
                
            # Columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
                '涨跌幅': 'pct_chg'
            })
            
            df['date'] = pd.to_datetime(df['date'])
            return df.tail(count)
            
        except Exception as e:
            logger.error(f"AkShare price fetch failed for {code}: {e}")
            return None

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
