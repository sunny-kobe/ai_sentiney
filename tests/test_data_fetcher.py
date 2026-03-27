import asyncio
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
async def test_fetch_with_fallback_skips_placeholder_market_breadth_values(collector):
    collector.sources = [MagicMock(), MagicMock(), MagicMock()]
    collector.sources[0].get_source_name.return_value = "Tencent"
    collector.sources[0].fetch_market_breadth.return_value = "N/A (Tencent)"
    collector.sources[1].get_source_name.return_value = "Efinance"
    collector.sources[1].fetch_market_breadth.return_value = "涨: 3000 / 跌: 1800 (平: 200)"
    collector.sources[2].get_source_name.return_value = "AkShare"
    collector.sources[2].fetch_market_breadth.return_value = None

    breadth = await collector._fetch_with_fallback("fetch_market_breadth")

    assert breadth == "涨: 3000 / 跌: 1800 (平: 200)"


@pytest.mark.asyncio
async def test_fetch_with_fallback_skips_non_breadth_market_summary_strings(collector):
    collector.sources = [MagicMock(), MagicMock(), MagicMock()]
    collector.sources[0].get_source_name.return_value = "Tencent"
    collector.sources[0].fetch_market_breadth.return_value = "N/A (Tencent)"
    collector.sources[1].get_source_name.return_value = "Efinance"
    collector.sources[1].fetch_market_breadth.return_value = "上证指数: 3321.98 | 深证成指: 10642.11 | 创业板指: 2148.39"
    collector.sources[2].get_source_name.return_value = "AkShare"
    collector.sources[2].fetch_market_breadth.return_value = "Up: 3000, Down: 1800, Flat: 200"

    breadth = await collector._fetch_with_fallback("fetch_market_breadth")

    assert breadth == "Up: 3000, Down: 1800, Flat: 200"


@pytest.mark.asyncio
async def test_fetch_with_fallback_skips_empty_news_values(collector):
    collector.sources = [MagicMock(), MagicMock(), MagicMock()]
    collector.sources[0].get_source_name.return_value = "Tencent"
    collector.sources[0].fetch_news.return_value = ""
    collector.sources[1].get_source_name.return_value = "Efinance"
    collector.sources[1].fetch_news.return_value = "   "
    collector.sources[2].get_source_name.return_value = "AkShare"
    collector.sources[2].fetch_news.return_value = "新闻1; 新闻2"

    news = await collector._fetch_with_fallback("fetch_news", code="159819", count=2)

    assert news == "新闻1; 新闻2"


@pytest.mark.asyncio
async def test_get_market_breadth_failure(collector, monkeypatch):
    """Test market breadth fetch failure handling after all sources fail."""
    collector.sources = [MagicMock(), MagicMock(), MagicMock()]
    for source, name in zip(collector.sources, ["Tencent", "Efinance", "AkShare"]):
        source.get_source_name.return_value = name
        source.fetch_market_breadth.side_effect = Exception("Network Error")
    monkeypatch.setattr(collector, "_fetch_market_breadth_backup", lambda: asyncio.sleep(0, result=None))

    breadth = await collector.get_market_breadth()
    assert breadth == "Unknown"


@pytest.mark.asyncio
async def test_get_market_breadth_uses_legu_backup_when_primary_sources_fail(collector, monkeypatch):
    async def fake_fetch_with_fallback(method_name, *args, **kwargs):
        assert method_name == "fetch_market_breadth"
        return None

    async def fake_run_blocking(func, *args, **kwargs):
        if func is ak.stock_market_activity_legu:
            return pd.DataFrame(
                [
                    {"item": "上涨家数", "value": "3123"},
                    {"item": "下跌家数", "value": "1566"},
                    {"item": "平盘家数", "value": "201"},
                ]
            )
        raise AssertionError(f"unexpected call: {func.__name__}")

    monkeypatch.setattr(collector, "_fetch_with_fallback", fake_fetch_with_fallback)
    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)

    breadth = await collector.get_market_breadth()

    assert breadth == "涨: 3123 / 跌: 1566 (平: 201)"

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
async def test_get_macro_news_falls_back_to_public_feeds_when_cctv_times_out(collector, monkeypatch):
    async def fake_run_blocking(func, *args, **kwargs):
        if func is ak.news_cctv:
            raise asyncio.TimeoutError()
        if func is ak.stock_info_global_cls:
            return pd.DataFrame([
                {"标题": "AI算力需求继续提升", "内容": "市场关注算力链条", "发布日期": pd.Timestamp("2026-03-27").date(), "发布时间": "09:00:00"},
                {"标题": "海外流动性预期回暖", "内容": "风险偏好改善", "发布日期": pd.Timestamp("2026-03-27").date(), "发布时间": "09:05:00"},
            ])
        raise AssertionError(f"unexpected call: {func.__name__}")

    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)

    result = await collector.get_macro_news()

    assert result["telegraph"] == ["AI算力需求继续提升", "海外流动性预期回暖"]
    assert result["ai_tech"] == ["AI算力需求继续提升"]


@pytest.mark.asyncio
async def test_fetch_macro_news_backup_merges_unique_headlines_across_sources(collector, monkeypatch):
    async def fake_run_blocking(func, *args, **kwargs):
        if func is ak.stock_info_global_cls:
            return pd.DataFrame(
                [
                    {"标题": "AI算力需求继续提升"},
                    {"标题": "海外流动性预期回暖"},
                ]
            )
        if func is ak.stock_info_global_sina:
            return pd.DataFrame(
                [
                    {"内容": "海外流动性预期回暖"},
                    {"内容": "美债收益率回落"},
                ]
            )
        if func is ak.stock_info_global_futu:
            return pd.DataFrame(
                [
                    {"标题": "科技股夜盘回暖", "内容": ""},
                ]
            )
        if func is ak.stock_info_global_ths:
            return pd.DataFrame()
        raise AssertionError(f"unexpected call: {func.__name__}")

    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)

    headlines = await collector._fetch_macro_news_backup()

    assert headlines == [
        "AI算力需求继续提升",
        "海外流动性预期回暖",
        "美债收益率回落",
        "科技股夜盘回暖",
    ]


@pytest.mark.asyncio
async def test_collect_morning_data_keeps_macro_news_fresh_when_backup_feed_succeeds(collector, monkeypatch):
    async def fake_global_indices():
        return [
            {"name": "标普500", "current": 6477.16, "change_pct": -1.74, "change_amount": -114.74},
            {"name": "纳斯达克", "current": 21408.08, "change_pct": -2.38, "change_amount": -521.54},
            {"name": "道琼斯", "current": 45960.11, "change_pct": -1.01, "change_amount": -469.18},
            {"name": "恒生指数", "current": 24961.49, "change_pct": 0.67, "change_amount": 167.3},
        ]

    async def fake_commodities():
        return [{"name": "布伦特原油", "current": 80.0, "change_pct": 0.3}]

    async def fake_treasury():
        return {"yield_10y": 4.42, "yield_2y": 3.96, "spread_10y_2y": 0.46}

    async def fake_macro_news():
        return {"telegraph": ["AI算力需求继续提升", "海外流动性预期回暖"], "ai_tech": ["AI算力需求继续提升"]}

    async def fake_stock_context(code, name):
        return {"code": code, "name": name, "last_close": 10.0, "ma20": 9.8, "bias_pct": 0.02, "ma20_status": "ABOVE"}

    monkeypatch.setattr(collector, "get_global_indices", fake_global_indices)
    monkeypatch.setattr(collector, "get_commodity_futures", fake_commodities)
    monkeypatch.setattr(collector, "get_us_treasury_yields", fake_treasury)
    monkeypatch.setattr(collector, "get_macro_news", fake_macro_news)
    monkeypatch.setattr(collector, "_fetch_morning_stock_context", fake_stock_context)

    result = await collector.collect_morning_data([{"code": "159819", "name": "人工智能ETF"}])

    assert result["collection_status"]["blocks"]["macro_news"]["status"] == "fresh"
    assert "macro news unavailable" not in result["data_issues"]

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
    monkeypatch.setattr(collector, "get_market_breadth", lambda: asyncio.sleep(0, result="涨: 1 / 跌: 1 (平: 1)"))
    monkeypatch.setattr(collector, "get_north_funds", lambda: asyncio.sleep(0, result=12.34))
    monkeypatch.setattr(collector, "get_indices", lambda: asyncio.sleep(0, result={"上证指数": {"change_pct": 0.5}}))
    monkeypatch.setattr(collector, "get_macro_news", lambda: asyncio.sleep(0, result={"telegraph": ["流动性平稳"], "ai_tech": []}))

    portfolio = [{'code': '600519', 'name': '茅台'}]

    result = await collector.collect_all(portfolio)

    assert 'stocks' in result
    assert len(result['stocks']) == 1
    assert result['stocks'][0]['code'] == '600519'
    assert result['stocks'][0]['current_price'] == 1800.0
    assert result["collection_status"]["overall_status"] == "fresh"
    assert result["data_issues"] == []


@pytest.mark.asyncio
async def test_collect_all_degrades_when_bulk_spot_fails_but_single_quote_succeeds(collector, monkeypatch):
    async def fake_fetch_with_fallback(method_name, *args, **kwargs):
        if method_name == "fetch_spot_data":
            return None
        if method_name == "fetch_single_quote":
            return {
                "code": kwargs["code"],
                "name": "茅台",
                "current_price": 1800.0,
                "pct_change": 1.0,
                "volume": 1000.0,
                "turnover_rate": 1.2,
            }
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
            return ""
        if method_name == "fetch_market_breadth":
            return "涨: 1 / 跌: 1 (平: 1)"
        return None

    async def fake_north_funds():
        return 0.0

    async def fake_indices():
        return {"上证指数": {"change_pct": 0.5}}

    async def fake_macro_news():
        return {"telegraph": ["流动性平稳"], "ai_tech": []}

    monkeypatch.setattr(collector, "_fetch_with_fallback", fake_fetch_with_fallback)
    monkeypatch.setattr(collector, "get_north_funds", fake_north_funds)
    monkeypatch.setattr(collector, "get_indices", fake_indices)
    monkeypatch.setattr(collector, "get_macro_news", fake_macro_news)

    result = await collector.collect_all([{"code": "600519", "name": "贵州茅台"}])

    assert len(result["stocks"]) == 1
    assert result["stocks"][0]["current_price"] == 1800.0
    assert result["collection_status"]["blocks"]["bulk_spot"]["status"] == "missing"
    assert result["collection_status"]["blocks"]["stock_quotes"]["status"] == "fresh"
    assert result["collection_status"]["overall_status"] == "degraded"
    assert "bulk spot unavailable; switched to single-quote fallback" not in result["data_issues"]
    assert "stock news unavailable" in result["data_issues"]


@pytest.mark.asyncio
async def test_collect_all_keeps_etf_portfolio_fresh_when_only_optional_blocks_are_missing(collector, monkeypatch):
    async def fake_fetch_with_fallback(method_name, *args, **kwargs):
        if method_name == "fetch_spot_data":
            return None
        if method_name == "fetch_single_quote":
            return {
                "code": kwargs["code"],
                "name": "人工智能ETF",
                "current_price": 1.5,
                "pct_change": 1.2,
                "volume": 1000.0,
                "turnover_rate": 1.2,
            }
        if method_name == "fetch_prices":
            return pd.DataFrame({
                "date": pd.date_range("2026-02-01", periods=30, freq="D"),
                "close": [1.0] * 30,
                "open": [1.0] * 30,
                "high": [1.01] * 30,
                "low": [0.99] * 30,
                "volume": [1000.0] * 30,
            })
        if method_name == "fetch_news":
            return ""
        return None

    monkeypatch.setattr(collector, "_fetch_with_fallback", fake_fetch_with_fallback)
    monkeypatch.setattr(collector, "get_market_breadth", lambda: asyncio.sleep(0, result="涨: 3000 / 跌: 1800 (平: 200)"))
    monkeypatch.setattr(collector, "get_north_funds", lambda: asyncio.sleep(0, result=12.34))
    monkeypatch.setattr(collector, "get_indices", lambda: asyncio.sleep(0, result={"上证指数": {"change_pct": 0.5}}))
    monkeypatch.setattr(collector, "get_macro_news", lambda: asyncio.sleep(0, result={"telegraph": ["流动性平稳"], "ai_tech": []}))

    result = await collector.collect_all([{"code": "159819", "name": "人工智能ETF"}])

    assert result["collection_status"]["blocks"]["bulk_spot"]["status"] == "missing"
    assert result["collection_status"]["blocks"]["stock_news"]["status"] == "missing"
    assert result["collection_status"]["overall_status"] == "fresh"
    assert result["data_issues"] == []


@pytest.mark.asyncio
async def test_collect_all_marks_supporting_data_failures_as_degraded(collector, monkeypatch):
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
            return ""
        return None

    async def fake_market_breadth():
        return "Unknown"

    async def fake_north_funds():
        return 0.0

    async def fake_indices():
        return {}

    async def fake_macro_news():
        return {"telegraph": [], "ai_tech": []}

    monkeypatch.setattr(collector, "_fetch_with_fallback", fake_fetch_with_fallback)
    monkeypatch.setattr(collector, "get_market_breadth", fake_market_breadth)
    monkeypatch.setattr(collector, "get_north_funds", fake_north_funds)
    monkeypatch.setattr(collector, "get_indices", fake_indices)
    monkeypatch.setattr(collector, "get_macro_news", fake_macro_news)

    result = await collector.collect_all([{"code": "600519", "name": "贵州茅台"}])

    assert len(result["stocks"]) == 1
    assert result["collection_status"]["blocks"]["market_breadth"]["status"] == "missing"
    assert result["collection_status"]["blocks"]["macro_news"]["status"] == "missing"
    assert result["collection_status"]["overall_status"] == "degraded"
    assert result["data_issues"]


@pytest.mark.asyncio
async def test_fetch_individual_stock_extras_skips_news_lookup_for_fund_like_security(collector, monkeypatch):
    calls = []

    async def fake_fetch_with_fallback(method_name, *args, **kwargs):
        calls.append(method_name)
        if method_name == "fetch_single_quote":
            return {
                "code": kwargs["code"],
                "name": "人工智能ETF",
                "current_price": 1.5,
                "pct_change": 1.2,
                "volume": 1000.0,
                "turnover_rate": 1.2,
            }
        if method_name == "fetch_prices":
            return pd.DataFrame({
                "date": pd.date_range("2026-02-01", periods=30, freq="D"),
                "close": [1.0] * 30,
                "open": [1.0] * 30,
                "high": [1.01] * 30,
                "low": [0.99] * 30,
                "volume": [1000.0] * 30,
            })
        raise AssertionError(f"unexpected method: {method_name}")

    monkeypatch.setattr(collector, "_fetch_with_fallback", fake_fetch_with_fallback)

    result = await collector._fetch_individual_stock_extras("159819", "人工智能ETF", pd.DataFrame())

    assert result["news"] == []
    assert result["news_status"] == "skipped"
    assert "fetch_news" not in calls


@pytest.mark.asyncio
async def test_get_global_indices_falls_back_to_hist_snapshots_when_spot_times_out(collector, monkeypatch):
    calls = []

    async def fake_run_blocking(func, *args, **kwargs):
        calls.append((func.__name__, args, kwargs))
        if func is ak.index_global_spot_em:
            raise asyncio.TimeoutError()
        if func is ak.index_global_hist_em:
            symbol = kwargs["symbol"]
            data = {
                "标普500": {"日期": pd.Timestamp("2026-03-26").date(), "最新价": 6477.16, "今开": 6555.86},
                "纳斯达克": {"日期": pd.Timestamp("2026-03-26").date(), "最新价": 21408.08, "今开": 21693.17},
                "道琼斯": {"日期": pd.Timestamp("2026-03-26").date(), "最新价": 45960.11, "今开": 46344.64},
                "恒生指数": {"日期": pd.Timestamp("2026-03-27").date(), "最新价": 24961.49, "今开": 24768.66},
                "美元指数": {"日期": pd.Timestamp("2026-03-27").date(), "最新价": 99.85, "今开": 99.93},
                "日经225": {"日期": pd.Timestamp("2026-03-27").date(), "最新价": 53410.61, "今开": 53239.59},
            }[symbol]
            return pd.DataFrame([data])
        raise AssertionError(f"unexpected call: {func.__name__}")

    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)

    result = await collector.get_global_indices()

    assert len(result) == 6
    assert {item["name"] for item in result} == {"标普500", "纳斯达克", "道琼斯", "恒生指数", "美元指数", "日经225"}
    assert any(name == "index_global_spot_em" for name, _, _ in calls)
    hist_calls = [kwargs["symbol"] for name, _, kwargs in calls if name == "index_global_hist_em"]
    assert hist_calls == ["标普500", "纳斯达克", "道琼斯", "恒生指数", "美元指数", "日经225"]


@pytest.mark.asyncio
async def test_get_global_indices_hist_fallback_runs_with_single_flight(collector, monkeypatch):
    active = 0
    max_active = 0

    async def fake_run_blocking(func, *args, **kwargs):
        if func is ak.index_global_spot_em:
            raise asyncio.TimeoutError()
        raise AssertionError(f"unexpected run_blocking call: {func.__name__}")

    async def fake_hist_snapshot(symbol):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return {
            "name": symbol,
            "current": 1.0,
            "change_pct": 0.1,
            "change_amount": 0.01,
        }

    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)
    monkeypatch.setattr(collector, "_fetch_global_index_hist_snapshot", fake_hist_snapshot)

    result = await collector.get_global_indices()

    assert len(result) == 6
    assert max_active == 1


@pytest.mark.asyncio
async def test_get_global_indices_fills_missing_targets_from_yahoo_backup(collector, monkeypatch):
    async def fake_run_blocking(func, *args, **kwargs):
        if func is ak.index_global_spot_em:
            return pd.DataFrame([
                {"名称": "标普500", "最新价": 6477.16, "涨跌幅": -1.74, "涨跌额": -114.74},
                {"名称": "道琼斯", "最新价": 45960.11, "涨跌幅": -1.01, "涨跌额": -469.18},
            ])
        raise AssertionError(f"unexpected run_blocking call: {func.__name__}")

    async def fake_yahoo_snapshot(name, symbol):
        data = {
            "纳斯达克": {"name": "纳斯达克", "current": 21408.08, "change_pct": -2.38, "change_amount": -521.54},
            "恒生指数": {"name": "恒生指数", "current": 24961.49, "change_pct": 0.67, "change_amount": 167.3},
            "美元指数": {"name": "美元指数", "current": 99.85, "change_pct": -0.08, "change_amount": -0.08},
            "日经225": {"name": "日经225", "current": 53410.61, "change_pct": 0.32, "change_amount": 171.02},
        }
        return data.get(name)

    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)
    monkeypatch.setattr(collector, "_fetch_yahoo_global_index_snapshot", fake_yahoo_snapshot)

    result = await collector.get_global_indices()

    assert [item["name"] for item in result] == ["标普500", "纳斯达克", "道琼斯", "恒生指数", "美元指数", "日经225"]
    assert len(result) == 6


@pytest.mark.asyncio
async def test_get_global_indices_can_fall_back_entirely_to_yahoo_backup(collector, monkeypatch):
    async def fake_run_blocking(func, *args, **kwargs):
        if func is ak.index_global_spot_em:
            raise asyncio.TimeoutError()
        raise AssertionError(f"unexpected run_blocking call: {func.__name__}")

    async def fake_yahoo_snapshot(name, symbol):
        return {
            "name": name,
            "current": 100.0,
            "change_pct": 1.0,
            "change_amount": 1.0,
        }

    monkeypatch.setattr(collector, "_run_blocking", fake_run_blocking)
    monkeypatch.setattr(collector, "_fetch_yahoo_global_index_snapshot", fake_yahoo_snapshot)

    result = await collector.get_global_indices()

    assert len(result) == 6
    assert {item["name"] for item in result} == {"标普500", "纳斯达克", "道琼斯", "恒生指数", "美元指数", "日经225"}


@pytest.mark.asyncio
async def test_collect_morning_data_marks_global_indices_fresh_when_backup_restores_coverage(collector, monkeypatch):
    async def fake_global_indices():
        return [
            {"name": "标普500", "current": 6477.16, "change_pct": -1.74, "change_amount": -114.74},
            {"name": "纳斯达克", "current": 21408.08, "change_pct": -2.38, "change_amount": -521.54},
            {"name": "道琼斯", "current": 45960.11, "change_pct": -1.01, "change_amount": -469.18},
            {"name": "恒生指数", "current": 24961.49, "change_pct": 0.67, "change_amount": 167.3},
        ]

    async def fake_commodities():
        return [{"name": "布伦特原油", "current": 80.0, "change_pct": 0.3}]

    async def fake_treasury():
        return {"yield_10y": 4.42, "yield_2y": 3.96, "spread_10y_2y": 0.46}

    async def fake_macro_news():
        return {"telegraph": ["海外市场震荡"], "ai_tech": []}

    async def fake_stock_context(code, name):
        return {"code": code, "name": name, "last_close": 10.0, "ma20": 9.8, "bias_pct": 0.02, "ma20_status": "ABOVE"}

    monkeypatch.setattr(collector, "get_global_indices", fake_global_indices)
    monkeypatch.setattr(collector, "get_commodity_futures", fake_commodities)
    monkeypatch.setattr(collector, "get_us_treasury_yields", fake_treasury)
    monkeypatch.setattr(collector, "get_macro_news", fake_macro_news)
    monkeypatch.setattr(collector, "_fetch_morning_stock_context", fake_stock_context)

    result = await collector.collect_morning_data([{"code": "159819", "name": "人工智能ETF"}])

    assert result["collection_status"]["blocks"]["global_indices"]["status"] == "fresh"
    assert "partial global indices missing" not in result["data_issues"]
    assert result["collection_status"]["overall_status"] == "fresh"


@pytest.mark.asyncio
async def test_collect_morning_data_marks_partial_global_indices_as_degraded(collector, monkeypatch):
    async def fake_global_indices():
        return [
            {"name": "纳斯达克", "current": 21408.08, "change_pct": -2.38, "change_amount": -521.54},
            {"name": "道琼斯", "current": 45960.11, "change_pct": -1.01, "change_amount": -469.18},
        ]

    async def fake_commodities():
        return [{"name": "布伦特原油", "current": 80.0, "change_pct": 0.3}]

    async def fake_treasury():
        return {"yield_10y": 4.42, "yield_2y": 3.96, "spread_10y_2y": 0.46}

    async def fake_macro_news():
        return {"telegraph": ["海外市场震荡"], "ai_tech": []}

    async def fake_stock_context(code, name):
        return {"code": code, "name": name, "last_close": 10.0, "ma20": 9.8, "bias_pct": 0.02, "ma20_status": "ABOVE"}

    monkeypatch.setattr(collector, "get_global_indices", fake_global_indices)
    monkeypatch.setattr(collector, "get_commodity_futures", fake_commodities)
    monkeypatch.setattr(collector, "get_us_treasury_yields", fake_treasury)
    monkeypatch.setattr(collector, "get_macro_news", fake_macro_news)
    monkeypatch.setattr(collector, "_fetch_morning_stock_context", fake_stock_context)

    result = await collector.collect_morning_data([{"code": "159819", "name": "人工智能ETF"}])

    assert result["collection_status"]["blocks"]["global_indices"]["status"] == "degraded"
    assert "partial global indices missing" in result["data_issues"]
    assert result["collection_status"]["overall_status"] == "degraded"


@pytest.mark.asyncio
async def test_collect_morning_data_returns_collection_status(collector, monkeypatch):
    async def fake_global_indices():
        return []

    async def fake_commodities():
        return []

    async def fake_treasury():
        return {}

    async def fake_macro_news():
        return {"telegraph": [], "ai_tech": []}

    async def fake_stock_context(code, name):
        return {"code": code, "name": name, "last_close": 10.0, "ma20": 9.8, "bias_pct": 0.02, "ma20_status": "ABOVE"}

    monkeypatch.setattr(collector, "get_global_indices", fake_global_indices)
    monkeypatch.setattr(collector, "get_commodity_futures", fake_commodities)
    monkeypatch.setattr(collector, "get_us_treasury_yields", fake_treasury)
    monkeypatch.setattr(collector, "get_macro_news", fake_macro_news)
    monkeypatch.setattr(collector, "_fetch_morning_stock_context", fake_stock_context)

    result = await collector.collect_morning_data([{"code": "600519", "name": "贵州茅台"}])

    assert result["collection_status"]["blocks"]["global_indices"]["status"] == "missing"
    assert result["collection_status"]["blocks"]["stocks"]["status"] == "fresh"
    assert result["collection_status"]["overall_status"] == "degraded"
    assert result["data_issues"]


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
