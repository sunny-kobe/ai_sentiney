
import pytest
import pandas as pd
from datetime import date
from src.processor.data_processor import DataProcessor

@pytest.fixture
def processor():
    return DataProcessor()

@pytest.fixture
def sample_history():
    # Create 30 days of history with date column
    dates = pd.date_range(end=date.today(), periods=31, freq='D')[:-1]  # Exclude today
    data = {'收盘': [100.0] * 30, '日期': dates}
    return pd.DataFrame(data)

def test_calculate_indicators_normal(processor, sample_history):
    """Test indicator calculation with sufficient history."""
    stock_input = {
        "code": "000001",
        "name": "Test Stock",
        "current_price": 100.0,
        "history": sample_history
    }

    result = processor.calculate_indicators(stock_input)
    assert result['ma20'] == 100.0
    assert result['bias_pct'] == 0.0

def test_calculate_indicators_insufficient_data(processor):
    """Test handling of insufficient history."""
    stock_input = {
        "code": "000001",
        "name": "New Stock",
        "current_price": 100.0,
        "history": pd.DataFrame()
    }

    result = processor.calculate_indicators(stock_input)
    assert result['ma20'] == 0.0
    assert result['status'] == 'UNKNOWN'

def test_generate_signal_danger_deep_break(processor):
    """Test DANGER signal generation (Bias < -5% = deep MA20 break)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Danger Stock",
        "current_price": 90.0,
        "ma20": 100.0,
        "bias_pct": -0.10,  # -10%, deep below MA20
        "volume_ratio": 2.0,  # 放量
        "pct_change": -5.0
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "DANGER"

def test_generate_signal_danger_volume_confirm(processor):
    """Test DANGER signal when bias -3%~-5% with high volume (放量破位)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Volume Break Stock",
        "current_price": 96.0,
        "ma20": 100.0,
        "bias_pct": -0.04,  # -4%, in -5% ~ -3% range
        "volume_ratio": 2.0,  # 放量 > 1.5
        "pct_change": -3.0
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "DANGER"  # 放量破位 = DANGER

def test_generate_signal_warning_low_volume(processor):
    """Test WARNING signal when bias -3%~-5% with low volume (缩量回调)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Low Volume Drop",
        "current_price": 96.0,
        "ma20": 100.0,
        "bias_pct": -0.04,  # -4%, in -5% ~ -3% range
        "volume_ratio": 0.8,  # 缩量 < 1.5
        "pct_change": -3.0
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "WARNING"  # 缩量破位 = WARNING (可能洗盘)

def test_generate_signal_watch(processor):
    """Test WATCH signal when bias -1%~-3% (轻微破位)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Watch Stock",
        "current_price": 98.0,
        "ma20": 100.0,
        "bias_pct": -0.02,  # -2%, in -3% ~ -1% range
        "volume_ratio": 1.0,
        "pct_change": -1.5
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "WATCH"

def test_generate_signal_observed(processor):
    """Test OBSERVED signal when bias 0~-1% (刚触及MA20)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Observed Stock",
        "current_price": 99.5,
        "ma20": 100.0,
        "bias_pct": -0.005,  # -0.5%, in -1% ~ 0% range
        "volume_ratio": 1.0,
        "pct_change": -0.5
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "OBSERVED"

def test_generate_signal_safe(processor):
    """Test SAFE signal (Price > MA20, bias not overbought)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Safe Stock",
        "current_price": 102.0,
        "ma20": 100.0,
        "bias_pct": 0.02,  # +2%, above MA20 but not overbought
        "volume_ratio": 1.0,
        "pct_change": 1.0
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "SAFE"

def test_generate_signal_overbought(processor):
    """Test OVERBOUGHT signal (Bias > +5%)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Overbought Stock",
        "current_price": 108.0,
        "ma20": 100.0,
        "bias_pct": 0.08,  # +8%, above +5% threshold
        "volume_ratio": 1.5,
        "pct_change": 5.0
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "OVERBOUGHT"

def test_generate_signal_limit_up(processor):
    """Test LIMIT_UP signal detection for main board stock."""
    processed_stocks = [{
        "code": "600519",
        "name": "贵州茅台",
        "current_price": 1800.0,
        "ma20": 1650.0,
        "bias_pct": 0.09,
        "volume_ratio": 3.0,
        "pct_change": 10.0  # 涨停
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "LIMIT_UP"

def test_generate_signal_limit_down_chinext(processor):
    """Test LIMIT_DOWN signal detection for ChiNext stock (±20%)."""
    processed_stocks = [{
        "code": "300750",
        "name": "宁德时代",
        "current_price": 160.0,
        "ma20": 200.0,
        "bias_pct": -0.20,
        "volume_ratio": 0.5,
        "pct_change": -20.0  # 创业板跌停
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "LIMIT_DOWN"

def test_generate_signal_st_stock_limit(processor):
    """Test ST stock limit detection (±5%)."""
    processed_stocks = [{
        "code": "000001",
        "name": "ST测试",  # Name contains ST
        "current_price": 3.0,
        "ma20": 3.2,
        "bias_pct": -0.06,
        "volume_ratio": 1.0,
        "pct_change": -5.0  # ST股跌停
    }]

    results = processor.generate_signals(processed_stocks)
    assert results[0]['signal'] == "LIMIT_DOWN"

def test_t1_locked_danger(processor):
    """Test T+1 LOCKED_DANGER signal when stock bought today is in danger."""
    today = date.today()
    holdings = {"000001": today}  # Bought today

    processed_stocks = [{
        "code": "000001",
        "name": "T+1 Locked",
        "current_price": 90.0,
        "ma20": 100.0,
        "bias_pct": -0.10,
        "volume_ratio": 2.0,
        "pct_change": -8.0
    }]

    results = processor.generate_signals(processed_stocks, holdings=holdings)
    assert results[0]['signal'] == "LOCKED_DANGER"
    assert results[0]['tradeable'] == False
    assert 'T+1' in results[0].get('signal_note', '')

def test_t1_tradeable(processor):
    """Test T+1 tradeable flag for stock bought before today."""
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    holdings = {"000001": yesterday}  # Bought yesterday

    processed_stocks = [{
        "code": "000001",
        "name": "Tradeable",
        "current_price": 90.0,
        "ma20": 100.0,
        "bias_pct": -0.10,
        "volume_ratio": 2.0,
        "pct_change": -8.0
    }]

    results = processor.generate_signals(processed_stocks, holdings=holdings)
    assert results[0]['signal'] == "DANGER"  # Normal DANGER, not LOCKED
    assert results[0].get('tradeable') == True
