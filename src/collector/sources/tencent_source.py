import requests
import pandas as pd
from typing import Optional
from src.collector.source_interface import DataSource
from src.utils.logger import logger

class TencentSource(DataSource):
    def get_source_name(self) -> str:
        return "Tencent"

    def _get_tencent_code(self, code: str) -> str:
        """
        Convert to Tencent format (sh600519, sz000001).
        Heuristic: 6/9 -> sh, 0/3/4/8 -> sz, 4/8 for BSE? 
        A-share simple rule: 6xx=sh, others=sz (roughly).
        Better: 
        60xxxx -> sh
        68xxxx -> sh
        00xxxx -> sz
        30xxxx -> sz
        """
        if code.startswith('6'):
            return f"sh{code}"
        elif code.startswith('9'): # B share?
            return f"sh{code}"
        else:
            return f"sz{code}"

    def fetch_market_breadth(self) -> str:
        return "N/A (Tencent)"

    def fetch_spot_data(self) -> Optional[pd.DataFrame]:
        # Tencent API is stock-specific. 
        # Returning None triggers "Individual Fetch" logic in DataCollector
        return None

    def fetch_prices(self, code: str, period: str = 'daily', count: int = 20) -> Optional[pd.DataFrame]:
        """
        Fetch k-line data from Tencent.
        URL: http://web.ifzq.gtimg.cn/appstock/app/fqkline/get
        """
        t_code = self._get_tencent_code(code)
        # We request slightly more to ensure we have enough after adjustment
        req_count = count + 5 
        url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        # param format: code,type,start_date,end_date,count,adjust
        # type=day
        params = {
            "param": f"{t_code},day,,,{req_count},qfq"
        }
        
        try:
            # explicit timeout 10s
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Tencent returned status {resp.status_code}")
                return None

            data = resp.json()
            
            # Response: data -> {t_code} -> qfqday (if qfq used) OR day (if no adjustment)
            # data[t_code] might contain 'qfqday' AND 'day'. 'qfqday' is preferred.
            
            stock_node = data.get('data', {}).get(t_code, {})
            if not stock_node:
                return None
            
            # Use qfqday if available, else day
            kline_raw = stock_node.get('qfqday', stock_node.get('day', []))
            
            if not kline_raw:
                return None

            # Parse
            # Format: [date, open, close, high, low, volume, ...]
            # date: "2023-01-01"
            records = []
            for item in kline_raw:
                if len(item) < 6:
                    continue
                records.append({
                    'date': item[0],
                    'open': float(item[1]),
                    'close': float(item[2]),
                    'high': float(item[3]),
                    'low': float(item[4]),
                    'volume': float(item[5])
                })
            
            df = pd.DataFrame(records)
            if df.empty:
                return None

            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date', ascending=True)
            
            return df.tail(count)

        except Exception as e:
            logger.error(f"Tencent price fetch failed for {code}: {e}")
            return None

    def fetch_news(self, code: str, count: int = 5) -> str:
        return ""
