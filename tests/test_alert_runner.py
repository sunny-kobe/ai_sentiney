"""
Tests for AlertRunner (src/alerts/runner.py)
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.alerts.anomaly_detector import Anomaly
from src.alerts.runner import AlertRunner, ANOMALY_TYPE_CN, SEVERITY_EMOJI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anomaly(**overrides):
    defaults = dict(
        code="510500",
        name="中证500ETF",
        anomaly_type="sharp_move",
        severity="warning",
        current_price=7.50,
        pct_change=4.2,
        volume=200000,
        turnover_rate=2.0,
        detail="急涨 +4.20%，当前价 7.5",
        timestamp="10:30:00",
    )
    defaults.update(overrides)
    return Anomaly(**defaults)


@pytest.fixture
def runner(tmp_path):
    """Build an AlertRunner with all dependencies mocked."""
    state_file = tmp_path / "alert_state.json"

    with patch("src.alerts.runner.ConfigLoader") as MockCL, \
         patch("src.alerts.runner.AnomalyDetector") as MockDetector, \
         patch("src.alerts.runner.NewsSearcher") as MockNews, \
         patch("src.alerts.runner.TelegramClient") as MockTG:
        MockCL.return_value.config = {"alert": {}}
        r = AlertRunner()
        r.state_file = state_file
        r.last_alerts = {}
        r.detector = MockDetector.return_value
        r.news_searcher = MockNews.return_value
        r.telegram = MockTG.return_value
        yield r


# ---------------------------------------------------------------------------
# Non-trading day skip
# ---------------------------------------------------------------------------

class TestNonTradingDaySkip:
    @pytest.mark.asyncio
    async def test_skips_on_weekend(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=False):
            result = await runner.run()
        assert result["anomalies"] == []
        assert result["sent"] is False
        assert result.get("skip_reason") == "非交易日"

    @pytest.mark.asyncio
    async def test_does_not_skip_on_workday(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=True):
            runner.detector.scan = AsyncMock(return_value=[])
            result = await runner.run()
        assert "skip_reason" not in result


# ---------------------------------------------------------------------------
# Anomaly filtering / dedup
# ---------------------------------------------------------------------------

class TestFilterAndDedup:
    def test_filter_new_anomalies_passes_first_time(self, runner):
        a = _make_anomaly()
        runner.last_alerts = {}
        result = runner._filter_new_anomalies([a])
        assert len(result) == 1

    def test_filter_new_anomalies_deduplicates_same_day(self, runner):
        a = _make_anomaly()
        key = runner._make_alert_key(a)
        today = datetime.now().strftime("%Y-%m-%d")
        runner.last_alerts = {key: today}

        result = runner._filter_new_anomalies([a])
        assert result == []

    def test_filter_allows_different_day(self, runner):
        a = _make_anomaly()
        key = runner._make_alert_key(a)
        runner.last_alerts = {key: "2020-01-01"}

        result = runner._filter_new_anomalies([a])
        assert len(result) == 1

    def test_filter_allows_different_type(self, runner):
        a1 = _make_anomaly(anomaly_type="sharp_move")
        a2 = _make_anomaly(anomaly_type="volume_spike")
        key1 = runner._make_alert_key(a1)
        today = datetime.now().strftime("%Y-%m-%d")
        runner.last_alerts = {key1: today}

        result = runner._filter_new_anomalies([a1, a2])
        assert len(result) == 1
        assert result[0].anomaly_type == "volume_spike"

    def test_make_alert_key_format(self, runner):
        a = _make_anomaly(code="000001", anomaly_type="sharp_move", severity="alert")
        assert runner._make_alert_key(a) == "000001:sharp_move:alert"


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

class TestBuildAlertMessage:
    def test_message_contains_header(self, runner):
        a = _make_anomaly()
        msg = runner._build_alert_message([a], {})
        assert "Sentinel 异动预警" in msg

    def test_message_contains_stock_info(self, runner):
        a = _make_anomaly(code="510500", name="中证500ETF")
        msg = runner._build_alert_message([a], {})
        assert "510500" in msg
        assert "中证500ETF" in msg

    def test_message_contains_anomaly_detail(self, runner):
        a = _make_anomaly(detail="急涨 +4.20%，当前价 7.5")
        msg = runner._build_alert_message([a], {})
        assert "急涨" in msg

    def test_message_contains_type_cn(self, runner):
        a = _make_anomaly(anomaly_type="sharp_move")
        msg = runner._build_alert_message([a], {})
        assert ANOMALY_TYPE_CN["sharp_move"] in msg

    def test_message_includes_news(self, runner):
        a = _make_anomaly(code="510500")
        news_map = {"510500": [{"title": "重大利好消息", "source": "百度"}]}
        msg = runner._build_alert_message([a], news_map)
        assert "重大利好消息" in msg

    def test_message_groups_by_code(self, runner):
        a1 = _make_anomaly(code="510500", anomaly_type="sharp_move")
        a2 = _make_anomaly(code="510500", anomaly_type="volume_spike")
        a3 = _make_anomaly(code="159915", anomaly_type="sharp_move")
        msg = runner._build_alert_message([a1, a2, a3], {})
        # Two stock sections (each separator is '─' * 20)
        assert msg.count("─" * 20) == 2

    def test_message_uses_severity_emoji(self, runner):
        for sev, emoji in SEVERITY_EMOJI.items():
            a = _make_anomaly(severity=sev)
            msg = runner._build_alert_message([a], {})
            assert emoji in msg


# ---------------------------------------------------------------------------
# run() integration
# ---------------------------------------------------------------------------

class TestRun:
    @pytest.mark.asyncio
    async def test_run_dry_run_does_not_send(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=True):
            a = _make_anomaly()
            runner.detector.scan = AsyncMock(return_value=[a])
            runner.news_searcher.batch_search = AsyncMock(return_value={})

            result = await runner.run(dry_run=True)
        assert result["sent"] is False
        runner.telegram._send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_sends_telegram(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=True):
            a = _make_anomaly()
            runner.detector.scan = AsyncMock(return_value=[a])
            runner.news_searcher.batch_search = AsyncMock(return_value={})

            result = await runner.run(dry_run=False)
        assert result["sent"] is True
        runner.telegram._send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_returns_empty_when_no_anomalies(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=True):
            runner.detector.scan = AsyncMock(return_value=[])
            result = await runner.run()
        assert result["anomalies"] == []
        assert result["sent"] is False

    @pytest.mark.asyncio
    async def test_run_deduplicates_already_sent(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=True):
            a = _make_anomaly()
            key = runner._make_alert_key(a)
            today = datetime.now().strftime("%Y-%m-%d")
            runner.last_alerts = {key: today}

            runner.detector.scan = AsyncMock(return_value=[a])
            result = await runner.run()
        assert result["sent"] is False

    @pytest.mark.asyncio
    async def test_run_saves_state(self, runner):
        with patch("src.alerts.runner.is_workday", return_value=True):
            a = _make_anomaly()
            runner.detector.scan = AsyncMock(return_value=[a])
            runner.news_searcher.batch_search = AsyncMock(return_value={})

            await runner.run(dry_run=True)
        assert runner.state_file.exists()
        saved = json.loads(runner.state_file.read_text())
        assert "last_alerts" in saved
        assert "last_scan" in saved
