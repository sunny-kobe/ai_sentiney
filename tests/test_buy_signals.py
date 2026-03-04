"""
Tests for buy-side signals: OPPORTUNITY and ACCUMULATE.
Covers signal generation (data_processor), signal evaluation (signal_tracker),
and regression tests ensuring existing DANGER signals are not incorrectly upgraded.
"""

import pytest
from src.processor.data_processor import DataProcessor
from src.processor.signal_tracker import (
    evaluate_signal,
    _compute_buy_stats,
    build_scorecard,
)


@pytest.fixture
def processor():
    return DataProcessor()


# ============================================================
# Signal Tracker: evaluate_signal for OPPORTUNITY / ACCUMULATE
# ============================================================

class TestEvaluateSignalBuySide:
    def test_opportunity_hit(self):
        """OPPORTUNITY + next day >+1% = HIT"""
        assert evaluate_signal("OPPORTUNITY", 1.5) == "HIT"

    def test_opportunity_miss(self):
        """OPPORTUNITY + next day <-1% = MISS"""
        assert evaluate_signal("OPPORTUNITY", -1.5) == "MISS"

    def test_opportunity_neutral(self):
        """OPPORTUNITY + next day between -1% and +1% = NEUTRAL"""
        assert evaluate_signal("OPPORTUNITY", 0.5) == "NEUTRAL"
        assert evaluate_signal("OPPORTUNITY", -0.5) == "NEUTRAL"

    def test_accumulate_hit(self):
        """ACCUMULATE + next day >0% = HIT"""
        assert evaluate_signal("ACCUMULATE", 0.5) == "HIT"
        assert evaluate_signal("ACCUMULATE", 2.0) == "HIT"

    def test_accumulate_miss(self):
        """ACCUMULATE + next day <-1.5% = MISS"""
        assert evaluate_signal("ACCUMULATE", -2.0) == "MISS"

    def test_accumulate_neutral(self):
        """ACCUMULATE + next day between -1.5% and 0% = NEUTRAL"""
        assert evaluate_signal("ACCUMULATE", -0.5) == "NEUTRAL"
        assert evaluate_signal("ACCUMULATE", -1.0) == "NEUTRAL"

    def test_existing_danger_unchanged(self):
        """Regression: DANGER evaluation logic unchanged."""
        assert evaluate_signal("DANGER", -1.0) == "HIT"
        assert evaluate_signal("DANGER", 2.0) == "MISS"
        assert evaluate_signal("DANGER", 0.0) == "NEUTRAL"

    def test_existing_safe_unchanged(self):
        """Regression: SAFE evaluation logic unchanged."""
        assert evaluate_signal("SAFE", 0.0) == "HIT"
        assert evaluate_signal("SAFE", -3.0) == "MISS"
        assert evaluate_signal("SAFE", -1.5) == "NEUTRAL"


# ============================================================
# Signal Tracker: _compute_buy_stats
# ============================================================

class TestComputeBuyStats:
    def test_with_buy_signals(self):
        by_signal = {
            "OPPORTUNITY": {"total": 5, "hits": 4, "rate": 0.8},
            "ACCUMULATE": {"total": 3, "hits": 2, "rate": 0.67},
            "DANGER": {"total": 10, "hits": 8, "rate": 0.8},
        }
        result = _compute_buy_stats(by_signal)
        assert result["total"] == 8
        assert result["hits"] == 6
        assert result["rate"] == 0.75

    def test_without_buy_signals(self):
        by_signal = {
            "DANGER": {"total": 10, "hits": 8},
            "SAFE": {"total": 5, "hits": 5},
        }
        result = _compute_buy_stats(by_signal)
        assert result["total"] == 0
        assert result["rate"] == 0

    def test_empty(self):
        result = _compute_buy_stats({})
        assert result["total"] == 0


# ============================================================
# Signal Tracker: build_scorecard includes buy stats
# ============================================================

class TestBuildScorecardBuyStats:
    def test_scorecard_includes_buy_stats_in_summary(self):
        yesterday_eval = []
        rolling_stats = {
            "period_days": 7,
            "total": 10,
            "hits": 7,
            "hit_rate": 0.7,
            "by_confidence": {},
            "by_signal": {
                "OPPORTUNITY": {"total": 3, "hits": 2, "rate": 0.67},
                "DANGER": {"total": 5, "hits": 4, "rate": 0.8},
                "SAFE": {"total": 2, "hits": 1, "rate": 0.5},
            },
        }
        scorecard = build_scorecard(yesterday_eval, rolling_stats)
        assert "买入信号" in scorecard["summary_text"]
        assert "buy_stats" in scorecard["rolling_stats"]


# ============================================================
# Data Processor: OPPORTUNITY signal via rule engine
# ============================================================

def _make_stock(code, bias_pct, volume_ratio, pct_change,
                macd_trend="UNKNOWN", macd_power="NORMAL", macd_div="NONE",
                obv_trend="UNKNOWN", kdj_signal="NEUTRAL", atr_vol="NORMAL",
                bb_position="MIDDLE", rsi=50, continuous_shrink=False):
    """Helper to build a stock dict with structured indicator data for generate_signals."""
    return {
        "code": code,
        "name": f"Stock_{code}",
        "current_price": round(100.0 * (1 + bias_pct), 2),
        "ma20": 100.0,
        "bias_pct": bias_pct,
        "volume_ratio": volume_ratio,
        "pct_change": pct_change,
        "macd": {"trend": macd_trend, "power": macd_power, "divergence": macd_div},
        "obv": {"trend": obv_trend},
        "kdj": {"signal": kdj_signal},
        "atr": {"volatility": atr_vol},
        "bollinger": {"position": bb_position},
        "rsi": rsi,
        "continuous_shrink": continuous_shrink,
    }


class TestOpportunitySignalGeneration:
    def test_opportunity_bottom_divergence(self, processor):
        """底背驰反转触底: DANGER + MACD_BOTTOM_DIV + VOLUME_SHRINK + OBV_INFLOW → OPPORTUNITY"""
        stock = _make_stock(
            "000001", bias_pct=-0.06, volume_ratio=0.5, pct_change=-3.0,
            macd_div="BOTTOM_DIV", obv_trend="INFLOW",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "OPPORTUNITY"

    def test_opportunity_oversold_golden_cross(self, processor):
        """超卖金叉反转: DANGER + KDJ_OVERSOLD_GOLDEN + OBV_INFLOW → OPPORTUNITY"""
        stock = _make_stock(
            "000001", bias_pct=-0.06, volume_ratio=0.5, pct_change=-3.0,
            kdj_signal="OVERSOLD_GOLDEN", obv_trend="INFLOW",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "OPPORTUNITY"

    def test_opportunity_volume_breakout(self, processor):
        """放量突破加仓: SAFE + MACD_GOLDEN_CROSS + VOLUME_HIGH + OBV_INFLOW → OPPORTUNITY"""
        stock = _make_stock(
            "000001", bias_pct=0.03, volume_ratio=2.0, pct_change=2.5,
            macd_trend="GOLDEN_CROSS", obv_trend="INFLOW",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "OPPORTUNITY"


# ============================================================
# Data Processor: ACCUMULATE signal via rule engine
# ============================================================

class TestAccumulateSignalGeneration:
    def test_accumulate_underwater_bottom_div(self, processor):
        """水下底背驰加仓: WATCH + MACD_BOTTOM_DIV + OBV_INFLOW → ACCUMULATE"""
        stock = _make_stock(
            "000001", bias_pct=-0.015, volume_ratio=0.8, pct_change=-1.0,
            macd_div="BOTTOM_DIV", obv_trend="INFLOW",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "ACCUMULATE"

    def test_accumulate_oversold_stabilize(self, processor):
        """超卖企稳加仓: WATCH + KDJ_OVERSOLD + VOLUME_CONTINUOUS_SHRINK → ACCUMULATE"""
        stock = _make_stock(
            "000001", bias_pct=-0.02, volume_ratio=0.6, pct_change=-1.5,
            kdj_signal="OVERSOLD", continuous_shrink=True,
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "ACCUMULATE"

    def test_accumulate_bull_low_vol(self, processor):
        """多头蓄势加仓: SAFE + MACD_BULLISH + OBV_INFLOW + ATR_LOW_VOLATILE → ACCUMULATE"""
        stock = _make_stock(
            "000001", bias_pct=0.02, volume_ratio=0.9, pct_change=0.5,
            macd_trend="BULLISH", obv_trend="INFLOW", atr_vol="LOW_VOLATILE",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "ACCUMULATE"


# ============================================================
# Regression: Existing DANGER signals not incorrectly upgraded
# ============================================================

class TestRegressionDangerNotUpgraded:
    def test_danger_without_obv_inflow_stays_watch(self, processor):
        """DANGER + MACD_BOTTOM_DIV + VOLUME_SHRINK but OBV_OUTFLOW → WATCH (existing rule), not OPPORTUNITY"""
        stock = _make_stock(
            "000001", bias_pct=-0.06, volume_ratio=0.5, pct_change=-3.0,
            macd_div="BOTTOM_DIV", obv_trend="OUTFLOW",
        )
        results = processor.generate_signals([stock])
        # Should hit "底背驰洗盘降级" → WATCH, NOT OPPORTUNITY (missing OBV_INFLOW)
        assert results[0]["signal"] == "WATCH"

    def test_pure_danger_stays_danger(self, processor):
        """DANGER with no mitigating flags remains DANGER."""
        stock = _make_stock(
            "000001", bias_pct=-0.10, volume_ratio=2.0, pct_change=-5.0,
            macd_trend="BEARISH", obv_trend="OUTFLOW",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "DANGER"

    def test_warning_with_weak_macd_obv_outflow_upgrades_to_danger(self, processor):
        """Regression: 弱势共振下杀 rule still works (WARNING → DANGER)."""
        stock = _make_stock(
            "000001", bias_pct=-0.04, volume_ratio=0.8, pct_change=-3.0,
            macd_power="WEAK", obv_trend="OUTFLOW",
        )
        results = processor.generate_signals([stock])
        assert results[0]["signal"] == "DANGER"
