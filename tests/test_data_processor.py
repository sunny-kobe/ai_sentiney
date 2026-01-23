
import pytest
import pandas as pd
from src.processor.data_processor import DataProcessor

@pytest.fixture
def processor():
    return DataProcessor()

@pytest.fixture
def sample_history():
    # Create 30 days of history
    data = {'收盘': [100.0] * 30}
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

def test_generate_signal_danger(processor):
    """Test DANGER signal generation (Price < MA20 * threshold & North Flow < 0)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Danger Stock",
        "current_price": 90.0,
        "ma20": 100.0,
        "bias_pct": -0.1
    }]
    
    # North flow outflow
    results = processor.generate_signals(processed_stocks, north_funds=-10.0)
    assert results[0]['signal'] == "DANGER"

def test_generate_signal_watch_fake_drop(processor):
    """Test WATCH signal (Price < Threshold BUT North Flow > 30)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Fake Drop",
        "current_price": 90.0,
        "ma20": 100.0,
        "bias_pct": -0.1
    }]
    
    # Big inflow
    results = processor.generate_signals(processed_stocks, north_funds=50.0)
    assert results[0]['signal'] == "WATCH"

def test_generate_signal_safe(processor):
    """Test SAFE signal (Price > MA20)."""
    processed_stocks = [{
        "code": "000001",
        "name": "Safe Stock",
        "current_price": 110.0,
        "ma20": 100.0,
        "bias_pct": 0.1
    }]
    
    results = processor.generate_signals(processed_stocks, north_funds=0.0)
    assert results[0]['signal'] == "SAFE"
