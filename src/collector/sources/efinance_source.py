import efinance as ef
import pandas as pd
from typing import Optional
from src.collector.source_interface import DataSource
from src.utils.logger import logger

class EfinanceSource(DataSource):
    def get_source_name(self) -> str:
        return "Efinance"

    def fetch_market_breadth(self) -> str:
        # Efinance doesn't have a direct "breadth" summary API like AkShare's summary
        # But we can simulate it or return a simplified string.
        # For now, we will leave this placeholder or implement a lightweight check
        try:
            # Getting real-time quotes for major indices to show market status
            indices = {
                "上证指数": "1.000001",
                "深证成指": "0.399001",
                "创业板指": "0.399006"
            }
            summary_parts = []
            for name, code in indices.items():
                # Efinance fetch quote
                df = ef.stock.get_quote_history(code) 
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    summary_parts.append(f"{name}: {latest['收盘']}")
            
            return " | ".join(summary_parts)
        except Exception as e:
            logger.warning(f"Efinance breadth fetch failed: {e}")
            return "Market Breadth: N/A"

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
            
            # Efinance columns: 股票代码, 股票名称, 涨跌幅, 最新价, ...
            # Needs strict mapping
            df = df.rename(columns={
                '股票代码': 'code',
                '股票名称': 'name',
                '最新价': 'current_price',
                '涨跌幅': 'pct_change'
            })
            
            # Ensure columns exist
            required = ['code', 'name', 'current_price', 'pct_change']
            if not all(col in df.columns for col in required):
                return None
                
            return df[required]
        except Exception as e:
            logger.error(f"Efinance spot fetch failed: {e}")
            return None
