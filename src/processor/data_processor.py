import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, date
import pytz
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader


def get_intraday_progress() -> float:
    """
    计算当前时间在交易日中的进度比例 (0.0 - 1.0)。
    A股交易时间: 09:30-11:30 (120分钟) + 13:00-15:00 (120分钟) = 240分钟
    
    Returns:
        float: 交易进度。0.0 = 尚未开盘, 1.0 = 已收盘。
               如果在午休或非交易时间，返回当时的累计进度。
    """
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    
    # 将时间转换为当天的分钟数 (从00:00开始)
    current_minutes = now.hour * 60 + now.minute
    
    # A股时间节点 (分钟)
    OPEN_AM = 9 * 60 + 30    # 09:30 = 570
    CLOSE_AM = 11 * 60 + 30  # 11:30 = 690
    OPEN_PM = 13 * 60        # 13:00 = 780
    CLOSE_PM = 15 * 60       # 15:00 = 900
    TOTAL_TRADING_MINUTES = 240.0
    
    if current_minutes < OPEN_AM:
        # 尚未开盘
        return 0.0
    elif current_minutes <= CLOSE_AM:
        # 上午交易时段
        elapsed = current_minutes - OPEN_AM
        return elapsed / TOTAL_TRADING_MINUTES
    elif current_minutes < OPEN_PM:
        # 午休时间 (11:30-13:00)，算上午的120分钟
        return 120.0 / TOTAL_TRADING_MINUTES  # = 0.5
    elif current_minutes <= CLOSE_PM:
        # 下午交易时段
        elapsed_am = 120.0  # 上午满额
        elapsed_pm = current_minutes - OPEN_PM
        return (elapsed_am + elapsed_pm) / TOTAL_TRADING_MINUTES
    else:
        # 已收盘
        return 1.0


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
            # 🔧 修复: 确保历史数据不包含今日，避免MA20重复计算
            # 问题: 腾讯K线API可能返回当日未完成的K线，导致今日价格被计算两次
            # 解决: 按日期过滤，只保留今日之前的数据
            tz = pytz.timezone('Asia/Shanghai')
            today = datetime.now(tz).date()

            # 确保有日期列用于过滤
            if 'date' in history_df.columns:
                date_col = 'date'
            elif '日期' in history_df.columns:
                date_col = '日期'
            else:
                date_col = None

            if date_col:
                # 转换日期列并过滤
                try:
                    history_df_filtered = history_df.copy()
                    history_df_filtered[date_col] = pd.to_datetime(history_df_filtered[date_col])
                    history_df_filtered = history_df_filtered[
                        history_df_filtered[date_col].dt.date < today
                    ]
                except Exception as e:
                    logger.warning(f"Date filtering failed for {code}: {e}, using original data")
                    history_df_filtered = history_df
            else:
                # 无日期列时，假设最后一条可能是今日，保守地去掉
                logger.warning(f"No date column found for {code}, assuming last row may be today")
                history_df_filtered = history_df.iloc[:-1] if len(history_df) > self.ma_window else history_df

            past_closes = history_df_filtered[close_col].tail(self.ma_window - 1).tolist()
            
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

            # 4. Pass through volume data and calculate volume ratio (日内归一化)
            volume = stock_d.get('volume', 0.0)
            turnover_rate = stock_d.get('turnover_rate', 0.0)
            avg_volume_5d = stock_d.get('avg_volume_5d', 0.0)
            
            # 🔧 修复: 日内量比归一化
            # 问题: 午盘时 volume 只有半天数据，直接除以5日均量会低估50%
            # 解决: 将当前成交量换算为"预估全天成交量"
            intraday_progress = get_intraday_progress()
            if intraday_progress > 0 and avg_volume_5d > 0:
                projected_daily_volume = volume / intraday_progress
                volume_ratio = projected_daily_volume / avg_volume_5d
            else:
                volume_ratio = 0.0

            return {
                "code": code,
                "name": name,
                "current_price": round(current_price, 2),
                "pct_change": stock_d.get('pct_change', 0.0),
                "ma20": round(realtime_ma20, 2),
                "bias_pct": round(bias_pct, 4), # e.g. 0.0512 = 5.12%
                "volume": round(volume / 10000, 2),  # 转换为万手
                "turnover_rate": round(turnover_rate, 2),
                "volume_ratio": round(volume_ratio, 2),  # 量比
                "news": stock_d.get('news', [])
            }

        except Exception as e:
            logger.error(f"Error calculating indicators for {code}: {e}")
            return stock_d

    def generate_signals(self, processed_stocks: List[Dict]) -> List[Dict]:
        """
        Applies rules to generate status tags (SAFE/DANGER/WATCH).
        Uses Bias-based tiered logic and volume confirmation.
        NOTE: North funds logic has been REMOVED as it's no longer real-time.
        """
        results = []

        # 🔧 修复: 从配置读取阈值，而非硬编码
        bias_thresholds = self.risk_params.get('bias_thresholds', {})
        BIAS_WATCH_THRESHOLD = bias_thresholds.get('watch', -0.01)      # -1%
        BIAS_WARNING_THRESHOLD = bias_thresholds.get('warning', -0.03)  # -3%
        BIAS_DANGER_THRESHOLD = bias_thresholds.get('danger', -0.05)    # -5%
        BIAS_OVERBOUGHT_THRESHOLD = bias_thresholds.get('overbought', 0.05)  # +5%

        # 量比阈值（放量判定）
        VOLUME_RATIO_HIGH = 1.5  # 量比 > 1.5 = 放量

        for stock in processed_stocks:
            price = stock['current_price']
            ma20 = stock['ma20']
            bias = stock.get('bias_pct', 0)
            volume_ratio = stock.get('volume_ratio', 1.0)
            pct_change = stock.get('pct_change', 0.0)

            if ma20 == 0:
                stock['signal'] = "N/A"
                results.append(stock)
                continue

            # 🔧 新增: 涨跌停检测
            # A股涨跌停规则: 主板±10%, 创业板/科创板±20%
            # 通过代码前缀判断板块: 300xxx/301xxx=创业板, 688xxx=科创板
            code = stock.get('code', '')
            if code.startswith('300') or code.startswith('301') or code.startswith('688'):
                limit_threshold = 19.5  # 创业板/科创板 ±20%，留0.5%容差
            else:
                limit_threshold = 9.5   # 主板 ±10%，留0.5%容差

            # 涨跌停状态标记
            if pct_change >= limit_threshold:
                stock['signal'] = "LIMIT_UP"
                stock['limit_status'] = "涨停"
                results.append(stock)
                continue
            elif pct_change <= -limit_threshold:
                stock['signal'] = "LIMIT_DOWN"
                stock['limit_status'] = "跌停"
                results.append(stock)
                continue

            # Signal Logic v2.0 with Bias Tiers
            if price > ma20:
                # Above MA20
                if bias > BIAS_OVERBOUGHT_THRESHOLD:
                    signal = "OVERBOUGHT"
                else:
                    signal = "SAFE"
            else:
                # Below MA20 - use tiered approach
                if bias < BIAS_DANGER_THRESHOLD:  # < -5%
                    signal = "DANGER"
                elif bias < BIAS_WARNING_THRESHOLD:  # -5% ~ -3%
                    # Volume confirmation: 放量破位更危险
                    if volume_ratio > VOLUME_RATIO_HIGH:
                        signal = "DANGER"
                    else:
                        signal = "WARNING"
                elif bias < BIAS_WATCH_THRESHOLD:  # -3% ~ -1%
                    signal = "WATCH"
                else:  # -1% ~ 0%
                    signal = "OBSERVED"

            stock['signal'] = signal
            results.append(stock)

        return results
