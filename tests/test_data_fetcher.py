import pytest
import pandas as pd
from unittest.mock import MagicMock
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
def collector(tmp_path):
    instance = DataCollector()
    instance.state_file = str(tmp_path / "circuit_breaker_state.json")
    for cb in instance._circuit_breakers.values():
        cb.failure_count = 0
        cb.is_open = False
        cb.last_failure_time = 0.0
    try:
        yield instance
    finally:
        instance.close()

@pytest.mark.asyncio
async def test_get_market_breadth_success(collector):
    """Test successful market breadth fetch through source fallback."""
    collector.sources = [MagicMock(), MagicMock(), MagicMock()]
    collector.sources[0].get_source_name.return_value = "Tencent"
    collector.sources[0].fetch_market_breadth.return_value = None
    collector.sources[1].get_source_name.return_value = "Efinance"
    collector.sources[1].fetch_market_breadth.return_value = "涨: 1 / 跌: 1 (平: 1)"
    collector.sources[2].get_source_name.return_value = "AkShare"
    collector.sources[2].fetch_market_breadth.return_value = None

    breadth = await collector.get_market_breadth()
    assert breadth == "涨: 1 / 跌: 1 (平: 1)"

@pytest.mark.asyncio
async def test_get_market_breadth_failure(collector):
    """Test market breadth fetch failure handling after all sources fail."""
    collector.sources = [MagicMock(), MagicMock(), MagicMock()]
    for source, name in zip(collector.sources, ["Tencent", "Efinance", "AkShare"]):
        source.get_source_name.return_value = name
        source.fetch_market_breadth.side_effect = Exception("Network Error")

    breadth = await collector.get_market_breadth()
    assert breadth == "Unknown"

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
async def test_collect_all_integration(collector, mock_akshare, monkeypatch):
    """Test the main collect_all orchestration."""
    mock_akshare.stock_hsgt_fund_flow_summary_em.return_value = pd.DataFrame()
    mock_akshare.stock_zh_index_spot_sina.return_value = pd.DataFrame()
    mock_akshare.news_cctv.return_value = pd.DataFrame()  # No news

    async def fake_fetch_with_fallback(method_name, *args, **kwargs):
        if method_name == "fetch_spot_data":
            return pd.DataFrame({
                "code": ["600519"],
                "name": ["茅台"],
                "current_price": [1800.0],
                "pct_change": [1.0],
            })
        if method_name == "fetch_prices":
            return pd.DataFrame({
                "date": pd.date_range("2026-02-01", periods=30, freq="D"),
                "close": [100.0] * 30,
                "open": [100.0] * 30,
                "high": [101.0] * 30,
                "low": [99.0] * 30,
                "volume": [1000.0] * 30,
            })
        if method_name == "fetch_news":
            return "新闻1; 新闻2"
        if method_name == "fetch_single_quote":
            return None
        return None

    monkeypatch.setattr(collector, "_fetch_with_fallback", fake_fetch_with_fallback)

    portfolio = [{'code': '600519', 'name': '茅台'}]

    result = await collector.collect_all(portfolio)

    assert 'stocks' in result
    assert len(result['stocks']) == 1
    assert result['stocks'][0]['code'] == '600519'
    assert result['stocks'][0]['current_price'] == 1800.0


def test_data_collector_uses_daemon_executor_threads(collector):
    future = collector.executor.submit(lambda: 1)
    assert future.result(timeout=1) == 1
    assert collector.executor._threads
    assert all(thread.daemon for thread in collector.executor._threads)


def test_daemon_executor_exposes_stable_runtime_bootstrap_mode(collector):
    mode = collector.executor._resolve_worker_bootstrap_mode()
    assert mode in {"legacy_initializer_args", "worker_context_args"}
    assert collector.executor._resolve_worker_bootstrap_mode() == mode


def test_daemon_executor_builds_worker_args_for_current_runtime(collector):
    executor = collector.executor
    executor_ref, worker_args = executor._build_worker_args()

    assert executor_ref() is executor

    mode = executor._resolve_worker_bootstrap_mode()
    if mode == "legacy_initializer_args":
        assert worker_args == (
            executor._work_queue,
            executor._initializer,
            executor._initargs,
        )
    else:
        assert len(worker_args) == 2
        assert worker_args[1] is executor._work_queue


@pytest.mark.asyncio
async def test_run_blocking_executes_callable_through_custom_executor(collector):
    result = await collector._run_blocking(lambda: "ok", timeout=1)
    assert result == "ok"
