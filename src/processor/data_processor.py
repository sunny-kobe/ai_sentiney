import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, date
import pytz
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader


# ============================================================
# Pure Functions: Technical Indicator Calculations
# ============================================================

def calculate_ema(closes: List[float], period: int) -> List[float]:
    """Exponential Moving Average."""
    if not closes:
        return []
    ema = [closes[0]]
    multiplier = 2 / (period + 1)
    for price in closes[1:]:
        ema.append(price * multiplier + ema[-1] * (1 - multiplier))
    return ema


def calculate_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Any]:
    """MACD indicator: returns {macd, signal_line, histogram, trend}."""
    if len(closes) < slow + signal:
        return {"macd": 0, "signal_line": 0, "histogram": 0, "trend": "UNKNOWN"}
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema(macd_line[slow - 1:], signal)
    current_macd = macd_line[-1]
    current_signal = signal_line[-1] if signal_line else 0
    histogram = current_macd - current_signal
    prev_histogram = (macd_line[-2] - (signal_line[-2] if len(signal_line) > 1 else 0)) if len(macd_line) > 1 else 0

    if histogram > 0 and prev_histogram <= 0:
        trend = "GOLDEN_CROSS"
    elif histogram < 0 and prev_histogram >= 0:
        trend = "DEATH_CROSS"
    elif histogram > 0:
        trend = "BULLISH"
    else:
        trend = "BEARISH"
    return {
        "macd": round(current_macd, 4),
        "signal_line": round(current_signal, 4),
        "histogram": round(histogram, 4),
        "trend": trend,
    }


def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """RSI (0-100). Returns 50.0 if insufficient data."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_bollinger(closes: List[float], window: int = 20, num_std: int = 2) -> Dict[str, Any]:
    """Bollinger Bands: returns {upper, middle, lower, bandwidth, position}."""
    if len(closes) < window:
        return {"upper": 0, "middle": 0, "lower": 0, "bandwidth": 0, "position": "UNKNOWN"}
    recent = closes[-window:]
    middle = sum(recent) / window
    variance = sum((x - middle) ** 2 for x in recent) / window
    std = variance ** 0.5
    upper = middle + num_std * std
    lower = middle - num_std * std
    bandwidth = (upper - lower) / middle if middle > 0 else 0
    current = closes[-1]
    if current >= upper:
        position = "ABOVE_UPPER"
    elif current <= lower:
        position = "BELOW_LOWER"
    elif current > middle:
        position = "UPPER_HALF"
    else:
        position = "LOWER_HALF"
    return {
        "upper": round(upper, 2),
        "middle": round(middle, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bandwidth, 4),
        "position": position,
    }


def _build_tech_summary(macd: Dict, rsi: float, bb: Dict, bias: float, vol_ratio: float) -> str:
    """Build a concise technical indicator summary string."""
    parts = []
    trend_map = {
        "GOLDEN_CROSS": "MACD金叉", "DEATH_CROSS": "MACD死叉",
        "BULLISH": "MACD多头", "BEARISH": "MACD空头",
    }
    parts.append(trend_map.get(macd.get('trend', ''), 'MACD未知'))
    if rsi > 70:
        parts.append(f"RSI超买({rsi})")
    elif rsi < 30:
        parts.append(f"RSI超卖({rsi})")
    else:
        parts.append(f"RSI={rsi}")
    pos_map = {
        "ABOVE_UPPER": "突破布林上轨", "BELOW_LOWER": "跌破布林下轨",
        "UPPER_HALF": "布林上半区", "LOWER_HALF": "布林下半区",
    }
    bb_text = pos_map.get(bb.get('position', ''), '')
    if bb_text:
        parts.append(bb_text)
    if vol_ratio > 1.5:
        parts.append(f"放量({vol_ratio}x)")
    elif vol_ratio > 0:
        parts.append(f"量比{vol_ratio}x")
    return " | ".join(p for p in parts if p)


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
    
    # 9:15-9:25 Call Auction usually has volume, but technically not continuous trading.
    # To be safe, we treat anything < 9:30 as 0 progress.
    if current_minutes < OPEN_AM:
        # 尚未开盘 (包括集合竞价)
        return 0.0
    elif current_minutes <= CLOSE_AM:
        # 上午交易时段
        elapsed = current_minutes - OPEN_AM
        return max(0.001, elapsed / TOTAL_TRADING_MINUTES) # Avoid strict 0 if just opened
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
                # 无日期列时，无论行数多少，都保守地去掉最后一行，防止是今日数据
                logger.warning(f"No date column found for {code}, unconditionally removing last row to match previous behavior safely")
                history_df_filtered = history_df.iloc[:-1] if not history_df.empty else history_df
                
                if len(history_df_filtered) < self.ma_window - 1:
                     logger.warning(f"Insufficient history after filtering for {code}: {len(history_df_filtered)}")

            past_closes = history_df_filtered[close_col].tail(self.ma_window - 1).tolist()

            # Stitch
            combined_closes = past_closes + [current_price]

            # Full history closes for multi-dimensional indicators (MACD needs 35+ data points)
            all_past_closes = history_df_filtered[close_col].tolist()
            full_closes = all_past_closes + [current_price]
            
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
            MIN_PROGRESS_THRESHOLD = 0.1 # 至少交易24分钟才有意义，否则放大倍数过大
            
            if intraday_progress >= MIN_PROGRESS_THRESHOLD and avg_volume_5d > 0:
                projected_daily_volume = volume / intraday_progress
                # 限制最大倍数，防止开盘极端数据干扰
                volume_ratio = min(projected_daily_volume / avg_volume_5d, 10.0)
            elif intraday_progress > 0 and intraday_progress < MIN_PROGRESS_THRESHOLD:
                # 进度太小，不计算量比 (或者返回默认1.0)
                volume_ratio = 0.0 # 标记为无效/数据不足
            else:
                volume_ratio = 0.0

            # 5. Multi-dimensional indicators (MACD / RSI / Bollinger)
            ti_cfg = self.risk_params.get('technical_indicators', {})

            macd_cfg = ti_cfg.get('macd', {})
            macd_result = calculate_macd(
                full_closes,
                fast=macd_cfg.get('fast_period', 12),
                slow=macd_cfg.get('slow_period', 26),
                signal=macd_cfg.get('signal_period', 9),
            )

            rsi_cfg = ti_cfg.get('rsi', {})
            rsi_value = calculate_rsi(full_closes, period=rsi_cfg.get('period', 14))

            bb_cfg = ti_cfg.get('bollinger', {})
            bb_result = calculate_bollinger(
                full_closes,
                window=bb_cfg.get('window', 20),
                num_std=bb_cfg.get('num_std', 2),
            )

            return {
                "code": code,
                "name": name,
                "current_price": round(current_price, 2),
                "pct_change": stock_d.get('pct_change', 0.0),
                "ma20": round(realtime_ma20, 2),
                "bias_pct": round(bias_pct, 4),
                "volume": round(volume / 10000, 2),
                "turnover_rate": round(turnover_rate, 2),
                "volume_ratio": round(volume_ratio, 2),
                "macd": macd_result,
                "rsi": rsi_value,
                "bollinger": bb_result,
                "news": stock_d.get('news', [])
            }

        except Exception as e:
            logger.error(f"Error calculating indicators for {code}: {e}")
            return stock_d

    def generate_signals(self, processed_stocks: List[Dict], holdings: Dict[str, date] = None) -> List[Dict]:
        """
        Applies rules to generate status tags (SAFE/DANGER/WATCH).
        Uses Bias-based tiered logic and volume confirmation.
        Includes T+1 validation if 'holdings' context allows.
        NOTE: North funds logic has been REMOVED as it's no longer real-time.
        """
        results = []
        tz = pytz.timezone('Asia/Shanghai')
        today = datetime.now(tz).date()

        # 🔧 修复: 从配置读取阈值，而非硬编码
        bias_thresholds = self.risk_params.get('bias_thresholds', {})
        BIAS_WATCH_THRESHOLD = bias_thresholds.get('watch', -0.01)      # -1%
        BIAS_WARNING_THRESHOLD = bias_thresholds.get('warning', -0.03)  # -3%
        BIAS_DANGER_THRESHOLD = bias_thresholds.get('danger', -0.05)    # -5%
        BIAS_OVERBOUGHT_THRESHOLD = bias_thresholds.get('overbought', 0.05)  # +5%

        # 量比阈值（放量判定）- 从配置读取
        VOLUME_RATIO_HIGH = self.risk_params.get('volume_ratio_high', 1.5)

        # RSI 阈值
        ti_cfg = self.risk_params.get('technical_indicators', {})
        rsi_cfg = ti_cfg.get('rsi', {})
        RSI_OVERSOLD = rsi_cfg.get('oversold', 30)
        RSI_OVERBOUGHT = rsi_cfg.get('overbought', 70)

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

            # 🔧 新增: 涨跌停检测 & 优化 ST 判断
            # A股涨跌停规则: 主板±10%, 创业板/科创板±20%, ST±5%
            # 通过代码前缀判断板块: 300xxx/301xxx=创业板, 688xxx=科创板
            code = stock.get('code', '')
            name = stock.get('name', '')
            
            if 'ST' in name or 'st' in name:
                limit_threshold = 4.5 # ST股 ±5% (留0.5%容差)
            elif code.startswith('300') or code.startswith('301') or code.startswith('688'):
                limit_threshold = 19.5  # 创业板/科创板 ±20%
            else:
                limit_threshold = 9.5   # 主板 ±10%

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

            # === Multi-dimensional cross-validation ===
            macd_data = stock.get('macd', {})
            rsi = stock.get('rsi', 50)
            bb_data = stock.get('bollinger', {})
            macd_trend = macd_data.get('trend', 'UNKNOWN')
            bb_position = bb_data.get('position', 'UNKNOWN')

            confidence = "中"

            if signal == "DANGER":
                bearish_count = sum([
                    macd_trend in ("BEARISH", "DEATH_CROSS"),
                    rsi < RSI_OVERSOLD,
                    bb_position == "BELOW_LOWER",
                ])
                confidence = "高" if bearish_count >= 2 else "中"

            elif signal == "WARNING":
                if macd_trend in ("BULLISH", "GOLDEN_CROSS"):
                    signal = "WATCH"
                    confidence = "中"
                elif macd_trend in ("BEARISH", "DEATH_CROSS") and rsi < RSI_OVERSOLD:
                    signal = "DANGER"
                    confidence = "高"

            elif signal == "SAFE":
                if rsi > RSI_OVERBOUGHT and bb_position == "ABOVE_UPPER":
                    signal = "OVERBOUGHT"
                    confidence = "高"
                elif macd_trend in ("BULLISH", "GOLDEN_CROSS"):
                    confidence = "高"
                elif macd_trend in ("BEARISH", "DEATH_CROSS"):
                    confidence = "低"

            elif signal == "OVERBOUGHT":
                overbought_count = sum([
                    rsi > RSI_OVERBOUGHT,
                    bb_position == "ABOVE_UPPER",
                    macd_trend in ("BEARISH", "DEATH_CROSS"),
                ])
                confidence = "高" if overbought_count >= 2 else "中"

            elif signal in ("WATCH", "OBSERVED"):
                if macd_trend == "GOLDEN_CROSS" and rsi < 50:
                    confidence = "低"
                elif macd_trend in ("BEARISH", "DEATH_CROSS"):
                    confidence = "高"

            stock['signal'] = signal
            stock['confidence'] = confidence
            stock['tech_summary'] = _build_tech_summary(macd_data, rsi, bb_data, bias, volume_ratio)

            # T+1 Check
            if holdings and code in holdings:
                buy_date = holdings[code]
                if buy_date == today:
                     stock['tradeable'] = False
                     stock['signal_note'] = f"T+1限制：今日({buy_date})买入无法卖出"
                     if signal == "DANGER":
                         # Force downgrade signal intensity or mark explicitly
                         stock['signal'] = "LOCKED_DANGER" 
                else:
                     stock['tradeable'] = True

            results.append(stock)

        return results

    # ============================================================
    # Morning Mode: 盘前外盘映射处理
    # ============================================================

    # 持仓-外盘关联映射
    PORTFOLIO_GLOBAL_MAP = {
        "159934": ["黄金"],           # 黄金ETF
        "601899": ["黄金", "铜"],      # 紫金矿业
        "000603": ["白银", "黄金"],    # 盛达资源
        "512480": ["纳斯达克"],        # 半导体ETF
        "560780": ["纳斯达克"],        # 半导体设备ETF
        "588760": ["纳斯达克"],        # 科创人工智能ETF
        "159819": ["纳斯达克"],        # 人工智能ETF
        "510500": ["标普500", "纳斯达克"],  # 中证500ETF
        "510300": ["标普500", "纳斯达克"],  # 沪深300ETF
        "159338": ["标普500", "纳斯达克"],  # 中证A500ETF
        "510980": ["标普500", "纳斯达克"],  # 上证指数ETF
        "563300": ["标普500", "纳斯达克"],  # 中证2000ETF
        "600089": ["WTI原油"],         # 特变电工
    }

    def process_morning_data(self, morning_data: Dict[str, Any], portfolio_config: List[Dict]) -> Dict[str, Any]:
        """
        处理早报数据：将外盘变动映射到持仓。
        """
        global_indices = morning_data.get('global_indices', [])
        commodities = morning_data.get('commodities', [])
        stocks = morning_data.get('stocks', [])

        # Build lookup: name -> change_pct
        global_lookup = {}
        for idx in global_indices:
            global_lookup[idx['name']] = idx.get('change_pct', 0)
        for c in commodities:
            global_lookup[c['name']] = c.get('change_pct', 0)

        # Enrich each stock with overnight drivers
        enriched_stocks = []
        for stock in stocks:
            code = stock.get('code', '')
            drivers = self.PORTFOLIO_GLOBAL_MAP.get(code, [])
            overnight_impacts = []
            for driver in drivers:
                # Fuzzy match against global_lookup keys
                for key, pct in global_lookup.items():
                    if driver in key:
                        sign = "+" if pct > 0 else ""
                        overnight_impacts.append(f"{key}{sign}{pct}%")
                        break

            stock['overnight_drivers'] = overnight_impacts
            stock['overnight_driver_str'] = ", ".join(overnight_impacts) if overnight_impacts else "无直接关联外盘"

            # Determine opening expectation based on drivers
            stock['opening_expectation'] = self._morning_signal(stock, global_lookup)
            enriched_stocks.append(stock)

        morning_data['stocks'] = enriched_stocks
        return morning_data

    def _morning_signal(self, stock: Dict, global_lookup: Dict) -> str:
        """
        基于昨收MA20和外盘变动生成盘前信号。
        Returns: HIGH_OPEN / LOW_OPEN / FLAT
        """
        code = stock.get('code', '')
        drivers = self.PORTFOLIO_GLOBAL_MAP.get(code, [])

        # Collect relevant driver changes
        driver_changes = []
        for driver in drivers:
            for key, pct in global_lookup.items():
                if driver in key:
                    driver_changes.append(pct)
                    break

        if not driver_changes:
            return "FLAT"

        avg_change = sum(driver_changes) / len(driver_changes)

        if avg_change > 0.5:
            return "HIGH_OPEN"
        elif avg_change < -0.5:
            return "LOW_OPEN"
        else:
            return "FLAT"
