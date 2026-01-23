
import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock
from src.collector.data_fetcher import DataCollector, ak

@pytest.fixture
def mock_akshare(mocker):
    """Mock AkShare APIs to avoid network calls."""
    mocker.patch('src.collector.data_fetcher.ak.stock_zh_a_spot_em')
    mocker.patch('src.collector.data_fetcher.ak.stock_hsgt_fund_flow_summary_em')
    mocker.patch('src.collector.data_fetcher.ak.stock_zh_index_spot_sina')
    mocker.patch('src.collector.data_fetcher.ak.stock_zh_a_hist')
    mocker.patch('src.collector.data_fetcher.ak.fund_etf_hist_em')
    mocker.patch('src.collector.data_fetcher.ak.stock_news_em')
    mocker.patch('src.collector.data_fetcher.ak.news_cctv')
    return ak

@pytest.fixture
def collector():
    return DataCollector()

@pytest.mark.asyncio
async def test_get_market_breadth_success(collector, mock_akshare):
    """Test successful market breadth fetch."""
    # Mock return data
    mock_df = pd.DataFrame({
        '代码': ['000001', '000002', '000003'],
        '涨跌幅': [1.5, -2.0, 0.0]
    })
    mock_akshare.stock_zh_a_spot_em.return_value = mock_df

    breadth = await collector.get_market_breadth()
    assert "涨: 1 / 跌: 1 (平: 1)" in breadth

@pytest.mark.asyncio
async def test_get_market_breadth_failure(collector, mock_akshare):
    """Test market breadth fetch failure handling."""
    mock_akshare.stock_zh_a_spot_em.side_effect = Exception("Network Error")
    
    # Needs to fail 3 times due to retry
    breadth = await collector.get_market_breadth()
    assert breadth == "Error"
    assert mock_akshare.stock_zh_a_spot_em.call_count == 3

@pytest.mark.asyncio
async def test_get_north_funds(collector, mock_akshare):
    """Test North funds parsing."""
    # Mock DataFrame imitating AkShare output
    mock_df = pd.DataFrame([
        ['北向资金', '12.34亿元', 'xx'],
        ['南向资金', '-5.00亿元', 'xx']
    ], columns=['板块', '净流入', '其他'])
    
    # We need to ensure the mock returns this DF when called
    mock_akshare.stock_hsgt_fund_flow_summary_em.return_value = mock_df
    
    funds = await collector.get_north_funds()
    assert funds == 12.34

@pytest.mark.asyncio
async def test_collect_all_integration(collector, mock_akshare):
    """Test the main collect_all orchestration."""
    # Setup mocks for all calls
    mock_akshare.stock_zh_a_spot_em.return_value = pd.DataFrame({'代码': ['600519'], '涨跌幅': [1.0], '名称': ['茅台']})
    mock_akshare.stock_hsgt_fund_flow_summary_em.return_value = pd.DataFrame()
    mock_akshare.stock_zh_index_spot_sina.return_value = pd.DataFrame()
    mock_akshare.news_cctv.return_value = pd.DataFrame() # No news
    mock_akshare.stock_zh_a_hist.return_value = pd.DataFrame({'收盘': [100.0]*20}) # Mock history
    
    portfolio = [{'code': '600519', 'name': '茅台'}]
    
    result = await collector.collect_all(portfolio)
    
    assert 'stocks' in result
    assert len(result['stocks']) == 1
    assert result['stocks'][0]['code'] == '600519'
    assert result['stocks'][0]['current_price'] == 0.0 # B/c we mocked spot to return specific DF but logic uses df_all_spot which comes from stock_zh_a_spot_em
    # Wait, in collect_all logic:
    # 1. it calls stock_zh_a_spot_em -> returns mock_df
    # 2. it passes mock_df to _fetch_individual_stock_extras
    # 3. _fetch checks code '600519' in mock_df
    # So it SHOULD find it.
    
    # Let's check why my assertion might be risky.
    # mock_df has '代码', '涨跌幅', '名称', '最新价' (missing '最新价' in my setup above)
    # Fix setup:
    mock_akshare.stock_zh_a_spot_em.return_value = pd.DataFrame({
        '代码': ['600519'], 
        '最新价': [1800.0],
        '涨跌幅': [1.0], 
        '名称': ['茅台']
    })
    
    result = await collector.collect_all(portfolio)
    assert result['stocks'][0]['current_price'] == 1800.0
