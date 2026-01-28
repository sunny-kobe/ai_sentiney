import pandas as pd
from typing import Dict, Any, List
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader

class DataProcessor:
    def __init__(self):
        self.config = ConfigLoader().get_system_config()
        self.risk_params = ConfigLoader().config.get('risk_management', {})
        self.ma_window = self.risk_params.get('ma_window', 20)

    def calculate_indicators(self, stock_d: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates dynamic indicators for a single stock.
        Stitches history + current price to get Realtime MA20.
        """
        code = stock_d.get('code')
        name = stock_d.get('name')
        current_price = stock_d.get('current_price', 0.0)
        history_df = stock_d.get('history') # DataFrame

        if current_price == 0 or history_df is None or history_df.empty:
            logger.warning(f"Insufficient data for {code} to calculate indicators.")
            return {
                "code": code,
                "name": name,
                "current_price": current_price, 
                "ma20": 0.0,
                "bias_pct": 0.0,
                "status": "UNKNOWN",
                "news": stock_d.get('news', [])
            }

        try:
            # 1. Prepare Data for Stitching
            # Hist Data usually has '收盘' or 'Close'
            # AkShare daily columns:日期, 开盘, 收盘, 最高, 最低, 成交量...
            # We need the last N-1 days close prices.
            
            # Ensure we are using the right column
            if '收盘' in history_df.columns:
                close_col = '收盘'
            elif 'Close' in history_df.columns:
                close_col = 'Close'
            elif 'close' in history_df.columns:
                close_col = 'close'
            else:
                layout_msg = str(history_df.columns.tolist())
                logger.error(f"Missing close column in history: {layout_msg}")
                raise KeyError("Missing close column")
            
            # Get last (Window - 1) closing prices
            # Note: history_df could include TODAY if run after close. 
            # But usually detailed history API updates at night.
            # We assume history_df DOES NOT contain today's realtime close yet.
            
            past_closes = history_df[close_col].tail(self.ma_window - 1).tolist()
            
            # Stitch
            combined_closes = past_closes + [current_price]
            
            # 2. Calculate Realtime MA20
            if len(combined_closes) < self.ma_window:
                # Not enough data (e.g. IPO < 20 days)
                realtime_ma20 = sum(combined_closes) / len(combined_closes)
            else:
                realtime_ma20 = sum(combined_closes[-self.ma_window:]) / self.ma_window

            # 3. Calculate Bias (乖离率)
            # Bias = (Price - MA20) / MA20
            bias_pct = (current_price - realtime_ma20) / realtime_ma20

            return {
                "code": code,
                "name": name,
                "current_price": round(current_price, 2),
                "pct_change": stock_d.get('pct_change', 0.0),
                "ma20": round(realtime_ma20, 2),
                "bias_pct": round(bias_pct, 4), # e.g. 0.0512 = 5.12%
                "news": stock_d.get('news', [])
            }

        except Exception as e:
            logger.error(f"Error calculating indicators for {code}: {e}")
            return stock_d

    def generate_signals(self, processed_stocks: List[Dict], north_funds: float) -> List[Dict]:
        """
        Applies rules to generate simple status tags (SAFE/DANGER/WATCH).
        This is a pre-filter before AI analysis.
        """
        results = []
        stop_loss_threshold = 0.995 # 0.5% buffer
        north_threshold = self.risk_params.get('north_money_threshold_billion', 30)

        for stock in processed_stocks:
            price = stock['current_price']
            ma20 = stock['ma20']
            
            if ma20 == 0:
                stock['signal'] = "N/A"
                results.append(stock)
                continue

            # Signal Logic
            if price > ma20:
                signal = "SAFE"
            else:
                # Below MA20
                if price < (ma20 * stop_loss_threshold):
                    # Effective Breakdown
                    if north_funds > north_threshold:
                        signal = "WATCH" # Broken but Big Money is buying
                    else:
                        signal = "DANGER"
                else:
                    # Hovering around MA20
                    signal = "Observed"

            stock['signal'] = signal
            results.append(stock)
            
        return results
