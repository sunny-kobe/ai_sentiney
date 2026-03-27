import efinance as ef
import pandas as pd
from typing import Optional
from src.collector.source_interface import DataSource
from src.utils.logger import logger

class EfinanceSource(DataSource):
    def get_source_name(self) -> str:
        return "Efinance"

    def fetch_market_breadth(self) -> str:
        # Efinance lacks a reliable lightweight breadth endpoint.
        # Return a placeholder so fallback logic can continue to better sources.
        return "N/A (Efinance)"

    def fetch_prices(self, code: str, period: str = 'daily', count: int = 20) -> Optional[pd.DataFrame]:
        try:
            # Efinance code format usually needs just the number, but let's handle normalization if needed
            # Assuming code is "600519"
            df = ef.stock.get_quote_history(code)
            
            if df is None or df.empty:
                return None
            
            # Rename columns to standard format
            # Efinance columns: 股票名称, 股票代码, 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
                '涨跌幅': 'pct_chg'
            })
            
            # Sort by date descending to get latest 'count' records, then reverse back
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date', ascending=True)
            
            return df.tail(count)
            
        except Exception as e:
            logger.error(f"Efinance price fetch failed for {code}: {e}")
            return None

    def fetch_news(self, code: str, count: int = 5) -> str:
        # Efinance doesn't have a specific individual stock news API that is stable
        # We might skip this or return empty to let AkShare fallback handle it
        return ""

    def fetch_spot_data(self) -> Optional[pd.DataFrame]:
        try:
            # Efinance realtime quotes
            df = ef.stock.get_realtime_quotes()
            if df is None or df.empty:
                return None
            
            # Efinance columns: 股票代码, 股票名称, 涨跌幅, 最新价, 成交量, 换手率 ...
            df = df.rename(columns={
                '股票代码': 'code',
                '股票名称': 'name',
                '最新价': 'current_price',
                '涨跌幅': 'pct_change',
                '成交量': 'volume',
                '换手率': 'turnover_rate'
            })
            
            # Ensure columns exist
            required = ['code', 'name', 'current_price', 'pct_change']
            optional = ['volume', 'turnover_rate']
            if not all(col in df.columns for col in required):
                return None
            
            # Include optional columns if present
            cols_to_return = required + [c for c in optional if c in df.columns]
            return df[cols_to_return]
        except Exception as e:
            logger.error(f"Efinance spot fetch failed: {e}")
            return None
