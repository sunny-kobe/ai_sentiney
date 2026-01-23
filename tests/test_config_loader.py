
import pytest
import os
from src.utils.config_loader import ConfigLoader

def test_singleton_pattern():
    """Test that ConfigLoader follows singleton pattern."""
    loader1 = ConfigLoader()
    loader2 = ConfigLoader()
    assert loader1 is loader2
    assert loader1.config is loader2.config

def test_env_var_substitution(mocker):
    """Test that environment variables are correctly substituted."""
    # Reset singleton to force reload
    ConfigLoader._instance = None
    
    mocker.patch.dict(os.environ, {
        "GEMINI_API_KEY": "test_key_123",
        "FEISHU_WEBHOOK": "https://test.webhook"
    })
    
    loader = ConfigLoader()
    api_keys = loader.get_api_keys()
    
    assert api_keys.get('gemini_api_key') == "test_key_123"
    assert api_keys.get('feishu_webhook') == "https://test.webhook"

def test_portfolio_loading():
    """Test that portfolio configuration is loaded."""
    portfolio = ConfigLoader.get_portfolio()
    assert isinstance(portfolio, list)
    if len(portfolio) > 0:
        assert 'code' in portfolio[0]
        assert 'strategy' in portfolio[0]
