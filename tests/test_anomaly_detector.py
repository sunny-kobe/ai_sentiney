"""
Tests for AnomalyDetector (src/alerts/anomaly_detector.py)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest

from src.alerts.anomaly_detector import Anomaly, AnomalyDetector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    """Provide a minimal config dict so ConfigLoader is not needed."""
    return {
        "alert": {
            "thresholds": {
                "price_change_pct": 3.0,
                "volume_ratio": 1.5,
                "turnover_rate": 8.0,
            }
        },
        "portfolio": [
            {"code": "510500", "name": "中证500ETF"},
        ],
        "watchlist": [
            {"code": "159915", "name": "创业板ETF"},
        ],
    }


@pytest.fixture
def detector(mock_config):
    """Build an AnomalyDetector with mocked ConfigLoader and DataCollector."""
    with patch("src.alerts.anomaly_detector.ConfigLoader") as MockCL, \
         patch("src.alerts.anomaly_detector.DataCollector"):
        MockCL.return_value.config = mock_config
        det = AnomalyDetector()
        return det


# ---------------------------------------------------------------------------
# _detect_anomalies – sharp move
# ---------------------------------------------------------------------------

class TestDetectSharpMove:
    def test_upward_sharp_move_detected(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.50,
            "pct_change": 4.5,   # > 3% threshold
            "volume": 100000,
            "turnover_rate": 2.0,
        }
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        sharp = [a for a in anomalies if a.anomaly_type == "sharp_move"]
        assert len(sharp) == 1
        assert sharp[0].code == "510500"
        assert sharp[0].pct_change == 4.5
        assert "急涨" in sharp[0].detail

    def test_downward_sharp_move_detected(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 6.00,
            "pct_change": -5.0,
            "volume": 80000,
            "turnover_rate": 1.0,
        }
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        sharp = [a for a in anomalies if a.anomaly_type == "sharp_move"]
        assert len(sharp) == 1
        assert sharp[0].severity == "critical"  # abs >= 5.0
        assert "急跌" in sharp[0].detail

    def test_no_sharp_move_when_below_threshold(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 1.0,   # below 3% threshold
            "volume": 50000,
            "turnover_rate": 2.0,
        }
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        assert [a for a in anomalies if a.anomaly_type == "sharp_move"] == []

    def test_severity_levels(self, detector):
        """critical >= 5, alert >= 4, warning >= 3"""
        target = {"code": "510500", "name": "中证500ETF"}

        for pct, expected in [(5.0, "critical"), (4.0, "alert"), (3.5, "warning")]:
            quote = {"name": "X", "current_price": 7.0, "pct_change": pct, "volume": 0, "turnover_rate": 0}
            anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
            sharp = [a for a in anomalies if a.anomaly_type == "sharp_move"]
            assert sharp[0].severity == expected, f"pct={pct} should be {expected}"


# ---------------------------------------------------------------------------
# _detect_anomalies – volume spike
# ---------------------------------------------------------------------------

class TestDetectVolumeSpike:
    def test_volume_spike_detected(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 1.0,
            "volume": 300000,
            "turnover_rate": 2.0,
        }
        avg_volume = 100000  # ratio = 3.0x
        anomalies = detector._detect_anomalies(target, quote, avg_volume=avg_volume)
        vol = [a for a in anomalies if a.anomaly_type == "volume_spike"]
        assert len(vol) == 1
        assert vol[0].severity == "critical"  # ratio >= 3.0

    def test_no_volume_spike_below_threshold(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 1.0,
            "volume": 100000,
            "turnover_rate": 2.0,
        }
        avg_volume = 100000  # ratio = 1.0x, below 1.5
        anomalies = detector._detect_anomalies(target, quote, avg_volume=avg_volume)
        assert [a for a in anomalies if a.anomaly_type == "volume_spike"] == []

    def test_no_volume_spike_when_avg_is_none(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {"name": "X", "current_price": 7.0, "pct_change": 0, "volume": 999999, "turnover_rate": 0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        assert [a for a in anomalies if a.anomaly_type == "volume_spike"] == []

    def test_volume_spike_severity_levels(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        for ratio, expected in [(3.0, "critical"), (2.0, "alert"), (1.6, "warning")]:
            avg_vol = 100000
            quote = {"name": "X", "current_price": 7.0, "pct_change": 0, "volume": avg_vol * ratio, "turnover_rate": 0}
            anomalies = detector._detect_anomalies(target, quote, avg_volume=avg_vol)
            vol = [a for a in anomalies if a.anomaly_type == "volume_spike"]
            assert vol[0].severity == expected, f"ratio={ratio} should be {expected}"


# ---------------------------------------------------------------------------
# _detect_anomalies – high turnover
# ---------------------------------------------------------------------------

class TestDetectHighTurnover:
    def test_high_turnover_detected(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 1.0,
            "volume": 50000,
            "turnover_rate": 10.0,  # >= 8% threshold
        }
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        to = [a for a in anomalies if a.anomaly_type == "high_turnover"]
        assert len(to) == 1
        assert to[0].severity == "warning"

    def test_high_turnover_alert_level(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 1.0,
            "volume": 50000,
            "turnover_rate": 16.0,  # >= 15 → alert
        }
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        to = [a for a in anomalies if a.anomaly_type == "high_turnover"]
        assert to[0].severity == "alert"

    def test_no_high_turnover_below_threshold(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 1.0,
            "volume": 50000,
            "turnover_rate": 5.0,  # below 8%
        }
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        assert [a for a in anomalies if a.anomaly_type == "high_turnover"] == []


# ---------------------------------------------------------------------------
# _detect_anomalies – limit move (涨跌停)
# ---------------------------------------------------------------------------

class TestDetectLimitMove:
    def test_main_board_limit_up(self, detector):
        """主板 60xxxx 涨停 +10%"""
        target = {"code": "600519", "name": "贵州茅台"}
        quote = {"name": "贵州茅台", "current_price": 1800.0, "pct_change": 10.0,
                 "volume": 50000, "turnover_rate": 1.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        lm = [a for a in anomalies if a.anomaly_type == "limit_move"]
        assert len(lm) == 1
        assert lm[0].severity == "critical"
        assert "涨停" in lm[0].detail
        assert "主板" in lm[0].detail

    def test_main_board_limit_down(self, detector):
        """主板 00xxxx 跌停 -10%"""
        target = {"code": "000001", "name": "平安银行"}
        quote = {"name": "平安银行", "current_price": 10.0, "pct_change": -10.0,
                 "volume": 50000, "turnover_rate": 1.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        lm = [a for a in anomalies if a.anomaly_type == "limit_move"]
        assert len(lm) == 1
        assert lm[0].severity == "alert"
        assert "跌停" in lm[0].detail
        assert "主板" in lm[0].detail

    def test_chinext_limit_up(self, detector):
        """创业板 30xxxx 涨停 +20%"""
        target = {"code": "300750", "name": "宁德时代"}
        quote = {"name": "宁德时代", "current_price": 250.0, "pct_change": 20.0,
                 "volume": 80000, "turnover_rate": 2.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        lm = [a for a in anomalies if a.anomaly_type == "limit_move"]
        assert len(lm) == 1
        assert lm[0].severity == "critical"
        assert "创业板" in lm[0].detail

    def test_star_market_limit_up(self, detector):
        """科创板 68xxxx 涨停 +20%"""
        target = {"code": "688981", "name": "中芯国际"}
        quote = {"name": "中芯国际", "current_price": 80.0, "pct_change": 20.0,
                 "volume": 60000, "turnover_rate": 3.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        lm = [a for a in anomalies if a.anomaly_type == "limit_move"]
        assert len(lm) == 1
        assert "科创板" in lm[0].detail

    def test_st_stock_limit_up(self, detector):
        """ST 股票涨停 +5%"""
        target = {"code": "600000", "name": "ST 浦发"}
        quote = {"name": "ST 浦发", "current_price": 3.5, "pct_change": 5.0,
                 "volume": 20000, "turnover_rate": 0.5}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        lm = [a for a in anomalies if a.anomaly_type == "limit_move"]
        assert len(lm) == 1
        assert "ST" in lm[0].detail

    def test_within_tolerance(self, detector):
        """距涨停 0.05%（< 0.1% 容差）应视为涨停"""
        target = {"code": "600519", "name": "贵州茅台"}
        quote = {"name": "贵州茅台", "current_price": 1800.0, "pct_change": 9.95,
                 "volume": 50000, "turnover_rate": 1.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        lm = [a for a in anomalies if a.anomaly_type == "limit_move"]
        assert len(lm) == 1

    def test_outside_tolerance(self, detector):
        """距涨停 0.2%（> 0.1% 容差）不应视为涨停"""
        target = {"code": "600519", "name": "贵州茅台"}
        quote = {"name": "贵州茅台", "current_price": 1800.0, "pct_change": 9.8,
                 "volume": 50000, "turnover_rate": 1.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        assert [a for a in anomalies if a.anomaly_type == "limit_move"] == []

    def test_etf_no_limit(self, detector):
        """ETF 没有涨跌停"""
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {"name": "中证500ETF", "current_price": 7.0, "pct_change": 10.0,
                 "volume": 50000, "turnover_rate": 1.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        assert [a for a in anomalies if a.anomaly_type == "limit_move"] == []

    def test_limit_up_also_triggers_sharp_move(self, detector):
        """涨停同时也会触发 sharp_move"""
        target = {"code": "600519", "name": "贵州茅台"}
        quote = {"name": "贵州茅台", "current_price": 1800.0, "pct_change": 10.0,
                 "volume": 50000, "turnover_rate": 1.0}
        anomalies = detector._detect_anomalies(target, quote, avg_volume=None)
        types = {a.anomaly_type for a in anomalies}
        assert "limit_move" in types
        assert "sharp_move" in types


# ---------------------------------------------------------------------------
# _detect_anomalies – combined scenarios
# ---------------------------------------------------------------------------

class TestDetectCombined:
    def test_multiple_anomalies_from_single_quote(self, detector):
        """A single quote can trigger all three anomaly types."""
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 5.5,      # sharp_move (critical)
            "volume": 400000,
            "turnover_rate": 12.0,   # high_turnover (warning)
        }
        avg_volume = 100000  # ratio 4.0x → volume_spike (critical)
        anomalies = detector._detect_anomalies(target, quote, avg_volume=avg_volume)
        types = {a.anomaly_type for a in anomalies}
        assert types == {"sharp_move", "volume_spike", "high_turnover"}

    def test_no_anomalies_when_all_normal(self, detector):
        target = {"code": "510500", "name": "中证500ETF"}
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 0.5,
            "volume": 80000,
            "turnover_rate": 3.0,
        }
        avg_volume = 100000  # ratio 0.8
        anomalies = detector._detect_anomalies(target, quote, avg_volume=avg_volume)
        assert anomalies == []


# ---------------------------------------------------------------------------
# scan() – integration with mocked data fetching
# ---------------------------------------------------------------------------

class TestScan:
    @pytest.mark.asyncio
    async def test_scan_returns_anomalies(self, detector):
        """When quotes trigger anomalies, scan() returns a sorted list."""
        quote = {
            "name": "中证500ETF",
            "current_price": 7.50,
            "pct_change": 4.2,
            "volume": 200000,
            "turnover_rate": 2.0,
        }
        detector._fetch_current_quote = AsyncMock(return_value=quote)
        detector._fetch_historical_avg_volume = AsyncMock(return_value=None)

        result = await detector.scan()
        assert len(result) > 0
        assert all(isinstance(a, Anomaly) for a in result)

    @pytest.mark.asyncio
    async def test_scan_returns_empty_when_no_anomalies(self, detector):
        """When all data is normal, scan() returns an empty list."""
        quote = {
            "name": "中证500ETF",
            "current_price": 7.00,
            "pct_change": 0.3,
            "volume": 50000,
            "turnover_rate": 1.0,
        }
        detector._fetch_current_quote = AsyncMock(return_value=quote)
        detector._fetch_historical_avg_volume = AsyncMock(return_value=100000)

        result = await detector.scan()
        assert result == []

    @pytest.mark.asyncio
    async def test_scan_sorted_by_severity(self, detector):
        """Results should be sorted: critical < alert < warning."""
        def fake_quote(code):
            if code == "510500":
                return {"name": "A", "current_price": 7, "pct_change": 5.5, "volume": 100, "turnover_rate": 1}
            return {"name": "B", "current_price": 3, "pct_change": 3.5, "volume": 100, "turnover_rate": 1}

        detector._fetch_current_quote = AsyncMock(side_effect=fake_quote)
        detector._fetch_historical_avg_volume = AsyncMock(return_value=None)

        result = await detector.scan()
        if len(result) >= 2:
            severity_order = {"critical": 0, "alert": 1, "warning": 2}
            orders = [severity_order[a.severity] for a in result]
            assert orders == sorted(orders)

    @pytest.mark.asyncio
    async def test_scan_returns_empty_when_fetch_fails(self, detector):
        """When quote fetching returns None, no crash and empty list."""
        detector._fetch_current_quote = AsyncMock(return_value=None)
        detector._fetch_historical_avg_volume = AsyncMock(return_value=None)

        result = await detector.scan()
        assert result == []

    @pytest.mark.asyncio
    async def test_scan_returns_empty_when_no_targets(self, detector):
        """When portfolio + watchlist are empty, returns empty."""
        detector.config["portfolio"] = []
        detector.config["watchlist"] = []
        detector._fetch_current_quote = AsyncMock(return_value=None)

        result = await detector.scan()
        assert result == []


# ---------------------------------------------------------------------------
# _get_watch_targets
# ---------------------------------------------------------------------------

class TestGetWatchTargets:
    def test_combines_portfolio_and_watchlist(self, detector):
        targets = detector._get_watch_targets()
        codes = [t["code"] for t in targets]
        assert "510500" in codes
        assert "159915" in codes
        assert any(t.get("source") == "portfolio" for t in targets)
        assert any(t.get("source") == "watchlist" for t in targets)
