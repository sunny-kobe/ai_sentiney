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


# ============================================================
# Advanced czsc-derived Technical Indicator calculations
# ============================================================

def calculate_kdj(highs: List[float], lows: List[float], closes: List[float], n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, Any]:
    """KDJ indicator: returns {k, d, j, signal}"""
    if len(closes) < n:
        return {"k": 50.0, "d": 50.0, "j": 50.0, "signal": "UNKNOWN"}
        
    k = 50.0
    d = 50.0
    
    k_seq, d_seq, j_seq = [], [], []
    
    for i in range(len(closes)):
        if i < n - 1:
            k_seq.append(50.0)
            d_seq.append(50.0)
            j_seq.append(50.0)
            continue
            
        hh = max(highs[i-n+1:i+1])
        ll = min(lows[i-n+1:i+1])
        
        rsv = 100.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0
        
        k = (m1 - 1) / m1 * k + 1 / m1 * rsv
        d = (m2 - 1) / m2 * d + 1 / m2 * k
        j = 3 * k - 2 * d
        
        k_seq.append(k)
        d_seq.append(d)
        j_seq.append(j)
        
    current_k, current_d, current_j = k_seq[-1], d_seq[-1], j_seq[-1]

    # Cross detection: K crossing D
    cross = "NONE"
    if len(k_seq) >= 2 and len(d_seq) >= 2:
        prev_k, prev_d = k_seq[-2], d_seq[-2]
        if prev_k <= prev_d and current_k > current_d:
            cross = "GOLDEN_CROSS"
        elif prev_k >= prev_d and current_k < current_d:
            cross = "DEATH_CROSS"

    signal = "NEUTRAL"
    if current_k < 20 and current_d < 20:
        signal = "OVERSOLD"
        if cross == "GOLDEN_CROSS":
            signal = "OVERSOLD_GOLDEN"  # Extreme value golden cross — strong buy
    elif current_k > 80 and current_d > 80:
        signal = "OVERBOUGHT"
        if cross == "DEATH_CROSS":
            signal = "OVERBOUGHT_DEATH"  # Extreme value death cross — strong sell

    return {
        "k": round(current_k, 2),
        "d": round(current_d, 2),
        "j": round(current_j, 2),
        "cross": cross,
        "signal": signal
    }

def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Dict[str, Any]:
    """Average True Range (Wilder Smoothing)"""
    if len(closes) < period + 1:
        return {"atr": 0.0, "atr_pct": 0.0, "volatility": "UNKNOWN"}
        
    tr_seq = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        pc = closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_seq.append(tr)
        
    atr = sum(tr_seq[:period]) / period
    for i in range(period, len(tr_seq)):
        atr = (atr * (period - 1) + tr_seq[i]) / period
        
    current_close = closes[-1]
    atr_pct = atr / current_close if current_close > 0 else 0
    
    if atr_pct > 0.08:
        volatility = "HIGH_VOLATILE"
    elif atr_pct < 0.03:
        volatility = "LOW_VOLATILE"
    else:
        volatility = "NORMAL"
        
    return {
        "atr": round(atr, 2),
        "atr_pct": round(atr_pct, 4),
        "volatility": volatility
    }

def calculate_obv(closes: List[float], opens: List[float], vols: List[float], ma_period: int = 10) -> Dict[str, Any]:
    """
    On-Balance Volume (能量潮) - czsc style.
    Calculates OBV and OBV_MA to determine energy momentum.
    """
    if len(closes) < ma_period + 1 or len(closes) != len(opens) or len(closes) != len(vols):
        return {"obv": 0, "obv_ma": 0, "trend": "UNKNOWN"}
    
    obv_seq = []
    current_obv = 0
    # Process history
    for i in range(len(closes)):
        # Rule: if close > open, vol is positive energy. Otherwise negative.
        if closes[i] > opens[i]:
            current_obv += vols[i]
        elif closes[i] < opens[i]:
            current_obv -= vols[i]
        obv_seq.append(current_obv)
    
    # Calculate EMA of OBV
    obv_ma = calculate_ema(obv_seq, ma_period)
    
    current = obv_seq[-1]
    ma = obv_ma[-1] if obv_ma else 0
    
    if current > ma:
        trend = "INFLOW"
    elif current < ma:
        trend = "OUTFLOW"
    else:
        trend = "NEUTRAL"
        
    return {
        "obv": round(current, 2),
        "obv_ma": round(ma, 2),
        "trend": trend
    }

def analyze_macd_advanced(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9, lookback: int = 5) -> Dict[str, Any]:
    """
    Advanced MACD analysis derived from czsc: detects Divergence (背驰) and Pillar Power.
    Computes MACD once and derives base + advanced signals from the same arrays.
    """
    if len(closes) < slow + signal:
        return {"macd": 0, "signal_line": 0, "histogram": 0, "trend": "UNKNOWN", "power": "UNKNOWN", "divergence": "NONE"}

    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema(macd_line[slow - 1:], signal)

    # Align arrays
    valid_len = len(signal_line)
    macd_valid = macd_line[-valid_len:]
    hist_seq = [m - s for m, s in zip(macd_valid, signal_line)]

    current_macd = macd_valid[-1]
    current_signal = signal_line[-1]
    histogram = hist_seq[-1]
    prev_histogram = hist_seq[-2] if len(hist_seq) > 1 else 0

    # Base trend
    if histogram > 0 and prev_histogram <= 0:
        trend = "GOLDEN_CROSS"
    elif histogram < 0 and prev_histogram >= 0:
        trend = "DEATH_CROSS"
    elif histogram > 0:
        trend = "BULLISH"
    else:
        trend = "BEARISH"

    # Power analysis (tas_macd_power)
    dif, dea = current_macd, current_signal
    if dif >= dea and dea >= 0:
        power = "SUPER_STRONG"
    elif histogram > 0:
        power = "STRONG"
    elif dif <= dea and dea <= 0:
        power = "SUPER_WEAK"
    elif histogram <= 0:
        power = "WEAK"
    else:
        power = "UNKNOWN"

    # Divergence analysis (tas_macd_bc)
    divergence = "NONE"
    if len(closes) >= slow + signal + lookback * 2 and valid_len > lookback * 4:
        recent_closes = closes[-lookback:]
        past_closes = closes[-lookback*3:-lookback]
        recent_macd = macd_valid[-lookback:]
        past_macd = macd_valid[-lookback*3:-lookback]

        if min(recent_closes) < min(past_closes) and min(recent_macd) > min(past_macd):
            divergence = "BOTTOM_DIV"
        elif max(recent_closes) > max(past_closes) and max(recent_macd) < max(past_macd):
            divergence = "TOP_DIV"

    return {
        "macd": round(current_macd, 4),
        "signal_line": round(current_signal, 4),
        "histogram": round(histogram, 4),
        "trend": trend,
        "power": power,
        "divergence": divergence,
    }


def _build_tech_summary(stock: Dict[str, Any]) -> str:
    """Build a czsc-style structural tag summary."""
    tags = []
    
    # 1. MACD
    macd = stock.get('macd', {})
    trend_map = {"GOLDEN_CROSS": "金叉", "DEATH_CROSS": "死叉", "BULLISH": "多头", "BEARISH": "空头"}
    power_map = {"SUPER_STRONG": "超强", "STRONG": "强势", "SUPER_WEAK": "超弱", "WEAK": "弱势"}
    div_map = {"BOTTOM_DIV": "底背驰", "TOP_DIV": "顶背驰"}
    
    macd_status = trend_map.get(macd.get('trend', ''), '未知')
    if macd.get('power') and macd.get('power') != "UNKNOWN":
        macd_status += f"-{power_map.get(macd.get('power'), '')}"
        
    macd_supp = div_map.get(macd.get('divergence', ''), '无背驰')
    tags.append(f"[日线_MACD_{macd_status}_{macd_supp}_0]")

    # 2. OBV
    obv = stock.get('obv', {})
    obv_map = {"INFLOW": "资金流入", "OUTFLOW": "资金流出", "NEUTRAL": "资金平衡"}
    obv_status = obv_map.get(obv.get('trend', ''), '未知')
    tags.append(f"[日线_OBV_{obv_status}_0]")

    # 3. KDJ
    kdj = stock.get('kdj', {})
    kdj_map = {
        "OVERBOUGHT": "超买", "OVERBOUGHT_DEATH": "超买死叉",
        "OVERSOLD": "超卖", "OVERSOLD_GOLDEN": "超卖金叉",
        "NEUTRAL": "中性"
    }
    kdj_status = kdj_map.get(kdj.get('signal', ''), '未知')
    tags.append(f"[日线_KDJ_{kdj_status}_0]")

    # 4. RSI
    rsi = stock.get('rsi', 50)
    rsi_status = "超买" if rsi > 70 else "超卖" if rsi < 30 else "中性"
    tags.append(f"[日线_RSI_{rsi_status}_{rsi}_0]")

    # 5. Volatility (ATR)
    atr = stock.get('atr', {})
    atr_map = {"HIGH_VOLATILE": "高波动", "LOW_VOLATILE": "低波动", "NORMAL": "正常波动"}
    atr_status = atr_map.get(atr.get('volatility', ''), '未知')
    tags.append(f"[日线_ATR_{atr_status}_0]")

    # 6. Bollinger
    bb = stock.get('bollinger', {})
    pos_map = {
        "ABOVE_UPPER": "突破上轨", "BELOW_LOWER": "跌破下轨",
        "UPPER_HALF": "上半区", "LOWER_HALF": "下半区",
    }
    bb_status = pos_map.get(bb.get('position', ''), '未知')
    tags.append(f"[日线_布林带_{bb_status}_0]")

    # 7. Volume
    vol_level = stock.get('volume_level', '未知')
    vol_ratio = stock.get('volume_ratio', 0)
    cont_shrink = "连缩" if stock.get('continuous_shrink', False) else "单缩"
    if vol_ratio < 1.0:
        vol_supp = f"量比{vol_ratio}x_{cont_shrink}"
    else:
        vol_supp = f"量比{vol_ratio}x"
    tags.append(f"[日线_量能_{vol_level}_{vol_supp}_0]")

    return " ".join(tags)


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

            # Extract additional properties for OBV calculation
            if '开盘' in history_df_filtered.columns:
                open_col = '开盘'
            elif 'Open' in history_df_filtered.columns:
                open_col = 'Open'
            elif 'open' in history_df_filtered.columns:
                open_col = 'open'
            else:
                open_col = close_col # fallback
                
            # Add High and Low extraction
            high_col = next((c for c in ['最高', 'High', 'high'] if c in history_df_filtered.columns), close_col)
            low_col = next((c for c in ['最低', 'Low', 'low'] if c in history_df_filtered.columns), close_col)
                
            if '成交量' in history_df_filtered.columns:
                vol_col = '成交量'
            elif 'Volume' in history_df_filtered.columns:
                vol_col = 'Volume'
            elif 'volume' in history_df_filtered.columns:
                vol_col = 'volume'
            else:
                vol_col = None

            all_past_opens = history_df_filtered[open_col].tolist()
            full_opens = all_past_opens + [stock_d.get('open_price', current_price)]
            
            all_past_highs = history_df_filtered[high_col].tolist()
            full_highs = all_past_highs + [stock_d.get('high', current_price)]
            
            all_past_lows = history_df_filtered[low_col].tolist()
            full_lows = all_past_lows + [stock_d.get('low', current_price)]

            # Detect shrinking volume trend
            continuous_shrink = False
            if vol_col and len(history_df_filtered) >= 3:
                all_past_vols = history_df_filtered[vol_col].tolist()
                full_vols = all_past_vols + [volume]
                
                # Check if last 3 days were shrinking
                v3, v2, v1 = all_past_vols[-3], all_past_vols[-2], all_past_vols[-1]
                if v1 < v2 < v3:
                    continuous_shrink = True
            else:
                full_vols = [0] * len(full_closes)

            # Categorize volume ratio
            volume_level = "无"
            if volume_ratio > 1.5:
                volume_level = "放量"
            elif volume_ratio > 1.0:
                volume_level = "平量"
            elif volume_ratio > 0.8:
                volume_level = "温和缩量"
            elif volume_ratio > 0:
                volume_level = "极度缩量"

            # 5. Multi-dimensional indicators (Advanced MACD / RSI / Bollinger / OBV)
            ti_cfg = self.risk_params.get('technical_indicators', {})

            macd_cfg = ti_cfg.get('macd', {})
            macd_result = analyze_macd_advanced(
                full_closes,
                fast=macd_cfg.get('fast_period', 12),
                slow=macd_cfg.get('slow_period', 26),
                signal=macd_cfg.get('signal_period', 9),
            )
            
            obv_result = calculate_obv(
                full_closes, full_opens, full_vols,
                ma_period=10
            )

            rsi_cfg = ti_cfg.get('rsi', {})
            rsi_value = calculate_rsi(full_closes, period=rsi_cfg.get('period', 14))

            bb_cfg = ti_cfg.get('bollinger', {})
            bb_result = calculate_bollinger(
                full_closes,
                window=bb_cfg.get('window', 20),
                num_std=bb_cfg.get('num_std', 2),
            )
            
            kdj_result = calculate_kdj(full_highs, full_lows, full_closes)
            atr_result = calculate_atr(full_highs, full_lows, full_closes)

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
                "volume_level": volume_level,
                "continuous_shrink": continuous_shrink,
                "macd": macd_result,
                "obv": obv_result,
                "rsi": rsi_value,
                "bollinger": bb_result,
                "kdj": kdj_result,
                "atr": atr_result,
                "strategy": stock_d.get('strategy', 'trend'),
                "cost": stock_d.get('cost', 0),
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

            # === Multi-dimensional cross-validation (Rule Engine) ===
            macd_data = stock.get('macd', {})
            obv_data = stock.get('obv', {})
            rsi = stock.get('rsi', 50)
            bb_data = stock.get('bollinger', {})
            
            macd_trend = macd_data.get('trend', 'UNKNOWN')
            macd_power = macd_data.get('power', 'UNKNOWN')
            macd_div = macd_data.get('divergence', 'NONE')
            obv_trend = obv_data.get('trend', 'UNKNOWN')
            bb_position = bb_data.get('position', 'UNKNOWN')

            # Build feature flags for the rule engine
            flags = set()
            if macd_trend in ("BULLISH", "GOLDEN_CROSS"): flags.add("MACD_BULLISH")
            if macd_trend in ("BEARISH", "DEATH_CROSS"): flags.add("MACD_BEARISH")
            if macd_trend == "GOLDEN_CROSS": flags.add("MACD_GOLDEN_CROSS")
            if macd_power in ("WEAK", "SUPER_WEAK"): flags.add("MACD_WEAK")
            if macd_div == "BOTTOM_DIV": flags.add("MACD_BOTTOM_DIV")
            if macd_div == "TOP_DIV": flags.add("MACD_TOP_DIV")
            if obv_trend == "INFLOW": flags.add("OBV_INFLOW")
            if obv_trend == "OUTFLOW": flags.add("OBV_OUTFLOW")
            if volume_ratio < 1.0: flags.add("VOLUME_SHRINK")   # Below average
            if volume_ratio > VOLUME_RATIO_HIGH: flags.add("VOLUME_HIGH")
            if rsi > RSI_OVERBOUGHT and bb_position == "ABOVE_UPPER": flags.add("RSI_BB_OVERBOUGHT")
            if rsi > RSI_OVERBOUGHT: flags.add("RSI_OVERBOUGHT")
            if rsi < RSI_OVERSOLD: flags.add("RSI_OVERSOLD")
            if rsi < 50: flags.add("RSI_WEAK")
            if bb_position == "BELOW_LOWER": flags.add("BB_BELOW_LOWER")
            if bb_position == "ABOVE_UPPER": flags.add("BB_ABOVE_UPPER")

            # KDJ flags
            kdj_data = stock.get('kdj', {})
            kdj_signal = kdj_data.get('signal', 'NEUTRAL')
            if kdj_signal in ("OVERSOLD", "OVERSOLD_GOLDEN"): flags.add("KDJ_OVERSOLD")
            if kdj_signal in ("OVERBOUGHT", "OVERBOUGHT_DEATH"): flags.add("KDJ_OVERBOUGHT")
            if kdj_signal == "OVERSOLD_GOLDEN": flags.add("KDJ_OVERSOLD_GOLDEN")
            if kdj_signal == "OVERBOUGHT_DEATH": flags.add("KDJ_OVERBOUGHT_DEATH")

            # ATR flags
            atr_data = stock.get('atr', {})
            atr_vol = atr_data.get('volatility', 'NORMAL')
            if atr_vol == "HIGH_VOLATILE": flags.add("ATR_HIGH_VOLATILE")
            if atr_vol == "LOW_VOLATILE": flags.add("ATR_LOW_VOLATILE")

            # Continuous shrink flag
            if stock.get('continuous_shrink', False): flags.add("VOLUME_CONTINUOUS_SHRINK")

            # Default confidence logic based on initial signal
            confidence = "中"
            if signal == "DANGER":
                bearish_count = sum([
                    "MACD_BEARISH" in flags,
                    "MACD_WEAK" in flags,
                    "OBV_OUTFLOW" in flags,
                    "RSI_OVERSOLD" in flags,
                    "BB_BELOW_LOWER" in flags,
                ])
                confidence = "高" if bearish_count >= 3 else "中"
            elif signal == "OVERBOUGHT":
                overbought_count = sum([
                    "RSI_OVERBOUGHT" in flags,
                    "BB_ABOVE_UPPER" in flags,
                    "MACD_BEARISH" in flags,
                    "MACD_TOP_DIV" in flags
                ])
                confidence = "高" if overbought_count >= 2 else "中"
            
            # Apply YAML Rules dynamically
            rules = self.risk_params.get('signal_rules', [])
            for rule in rules:
                triggers = rule.get('triggers', [])
                if signal not in triggers:
                    continue
                
                cond_all = rule.get('conditions_all', [])
                cond_any = rule.get('conditions_any', [])
                
                match_all = True
                if cond_all:
                    match_all = all(c in flags for c in cond_all)
                    
                match_any = True
                if cond_any:
                    match_any = any(c in flags for c in cond_any)
                
                if match_all and match_any:
                    new_signal = rule.get('result', '')
                    if new_signal:
                        signal = new_signal

                    new_confidence = rule.get('confidence', '')
                    if new_confidence:
                        confidence = new_confidence

                    logger.debug(f"Rule [{rule.get('name')}] fired for [{name}]: signal={signal}, confidence={confidence}")
                    break # First-match-wins: stop after first matching rule

            # Buy-side confidence scoring
            if signal in ("OPPORTUNITY", "ACCUMULATE"):
                bullish_count = sum([
                    "MACD_BOTTOM_DIV" in flags,
                    "MACD_GOLDEN_CROSS" in flags,
                    "OBV_INFLOW" in flags,
                    "KDJ_OVERSOLD_GOLDEN" in flags,
                    "RSI_OVERSOLD" in flags,
                    "BB_BELOW_LOWER" in flags,
                    "VOLUME_CONTINUOUS_SHRINK" in flags,
                ])
                if signal == "OPPORTUNITY" and bullish_count >= 3:
                    confidence = "高"
                elif signal == "ACCUMULATE" and bullish_count >= 2:
                    confidence = "高"

            stock['signal'] = signal
            stock['confidence'] = confidence
            stock['tech_summary'] = _build_tech_summary(stock)

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
