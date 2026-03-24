from datetime import date, timedelta

from src.service.execution_gate import apply_mode_gate
from src.service.market_regime import classify_market_regime
from src.service.performance_gate import gate_offensive_setup
from src.service.setup_classifier import classify_setup
from src.service.strategy_engine import build_strategy_snapshot


def _make_stock(
    code,
    name,
    *,
    signal="SAFE",
    confidence="中",
    bias_pct=0.01,
    pct_change=0.5,
    current_price=1.0,
    ma20=0.98,
    tech_summary="站上20日线，趋势偏强",
    macd_trend="BULLISH",
    macd_power="STRONG",
    macd_divergence="NONE",
    obv_trend="INFLOW",
    kdj_signal="NEUTRAL",
    shares=0,
):
    return {
        "code": code,
        "name": name,
        "signal": signal,
        "confidence": confidence,
        "bias_pct": bias_pct,
        "pct_change": pct_change,
        "current_price": current_price,
        "ma20": ma20,
        "tech_summary": tech_summary,
        "macd": {"trend": macd_trend, "power": macd_power, "divergence": macd_divergence},
        "obv": {"trend": obv_trend},
        "kdj": {"signal": kdj_signal},
        "shares": shares,
    }


def _make_history(price_map):
    records = []
    start = date(2026, 2, 2)
    total_days = len(next(iter(price_map.values())))
    for idx in range(total_days):
        stocks = []
        for code, prices in price_map.items():
            stocks.append({"code": code, "name": code, "current_price": prices[idx]})
        records.append(
            {
                "date": (start + timedelta(days=idx)).isoformat(),
                "raw_data": {"stocks": stocks},
                "ai_result": {"actions": []},
            }
        )
    return records


def test_classify_market_regime_uses_breadth_indices_and_cluster_stress():
    regime = classify_market_regime(
        {
            "market_breadth": "900家上涨，4100家下跌",
            "indices": {"上证指数": {"change_pct": -2.3}, "创业板指": {"change_pct": -3.2}},
            "macro_news": {"telegraph": ["外围走弱，避险情绪升温"]},
            "stocks": [
                _make_stock("159819", "人工智能ETF", signal="DANGER", bias_pct=-0.06, pct_change=-4.1, current_price=0.8, ma20=0.95),
                _make_stock("512480", "半导体ETF", signal="WARNING", bias_pct=-0.05, pct_change=-3.2, current_price=0.9, ma20=1.04),
            ],
        },
        _make_history({"510300": [100, 98, 95, 92]}),
    )

    assert regime["regime"] == "撤退"
    assert regime["action_bias"] == "risk_off"
    assert regime["offensive_allowed"] is False


def test_classify_setup_distinguishes_key_patterns():
    trend_follow = classify_setup(
        _make_stock("A", "强趋势ETF", signal="SAFE", current_price=1.12, ma20=1.02, bias_pct=0.05, pct_change=2.0),
        {"relative_return_20": 0.08, "relative_return_40": 0.12},
    )
    pullback_resume = classify_setup(
        _make_stock(
            "B",
            "回踩企稳ETF",
            signal="ACCUMULATE",
            current_price=1.01,
            ma20=1.0,
            bias_pct=0.01,
            pct_change=0.6,
            macd_divergence="BOTTOM_DIV",
        ),
        {"relative_return_20": 0.03, "relative_return_40": 0.04},
    )
    breakdown = classify_setup(
        _make_stock("C", "破位ETF", signal="DANGER", current_price=0.92, ma20=1.02, bias_pct=-0.05, pct_change=-3.6, obv_trend="OUTFLOW", macd_trend="DEATH_CROSS", macd_power="SUPER_WEAK"),
        {"relative_return_20": -0.08, "relative_return_40": -0.12},
    )
    rebound_trap = classify_setup(
        _make_stock("D", "反抽ETF", signal="WARNING", current_price=0.95, ma20=1.03, bias_pct=-0.04, pct_change=1.8, obv_trend="INFLOW", macd_trend="BEARISH", macd_power="WEAK"),
        {"relative_return_20": -0.06, "relative_return_40": -0.09},
    )
    conflict = classify_setup(
        _make_stock("E", "冲突ETF", signal="SAFE", current_price=0.99, ma20=1.0, bias_pct=-0.01, pct_change=0.1, obv_trend="INFLOW", macd_trend="DEATH_CROSS", macd_power="SUPER_WEAK"),
        {"relative_return_20": 0.0, "relative_return_40": 0.0},
    )

    assert trend_follow["setup_type"] == "trend_follow"
    assert pullback_resume["setup_type"] == "pullback_resume"
    assert breakdown["setup_type"] == "breakdown"
    assert rebound_trap["setup_type"] == "rebound_trap"
    assert conflict["setup_type"] == "conflict"


def test_gate_offensive_setup_blocks_low_sample_or_weak_stats():
    assert gate_offensive_setup({"count": 2, "avg_relative_return": 0.04, "avg_max_drawdown": -0.03})["allowed"] is False
    assert gate_offensive_setup({"count": 8, "avg_relative_return": -0.02, "avg_max_drawdown": -0.05})["allowed"] is False
    allowed = gate_offensive_setup({"count": 9, "avg_relative_return": 0.05, "avg_max_drawdown": -0.03})
    assert allowed["allowed"] is True


def test_apply_mode_gate_suppresses_midday_adds_and_requires_permission_for_preclose():
    midday = apply_mode_gate(
        mode="midday",
        candidate_action="增配",
        setup_type="pullback_resume",
        regime="均衡",
        offensive_allowed=True,
    )
    preclose_blocked = apply_mode_gate(
        mode="preclose",
        candidate_action="增配",
        setup_type="pullback_resume",
        regime="均衡",
        offensive_allowed=False,
    )
    preclose_allowed = apply_mode_gate(
        mode="preclose",
        candidate_action="增配",
        setup_type="pullback_resume",
        regime="均衡",
        offensive_allowed=True,
    )

    assert midday["final_action"] == "持有"
    assert midday["execution_window"] == "尾盘再确认"
    assert preclose_blocked["final_action"] == "持有"
    assert preclose_allowed["final_action"] == "增配"
    assert preclose_allowed["execution_window"] == "今日尾盘"


def test_build_strategy_snapshot_returns_normalized_holdings_and_conservative_actions():
    history = _make_history(
        {
            "510300": [100 + (idx * 0.4) for idx in range(21)],
            "159819": [100 + (idx * 0.8) for idx in range(21)],
        }
    )
    snapshot = build_strategy_snapshot(
        {
            "market_breadth": "2600家上涨，2200家下跌",
            "indices": {"上证指数": {"change_pct": 0.2}, "创业板指": {"change_pct": 0.4}},
            "macro_news": {"telegraph": ["情绪温和修复"]},
            "stocks": [
                _make_stock("159819", "人工智能ETF", signal="OPPORTUNITY", confidence="高", current_price=1.35, ma20=1.25, bias_pct=0.04, pct_change=2.0),
                _make_stock("512480", "半导体ETF", signal="WARNING", confidence="中", current_price=0.95, ma20=1.02, bias_pct=-0.04, pct_change=1.2, obv_trend="INFLOW", macd_trend="BEARISH", macd_power="WEAK"),
            ],
        },
        historical_records=history,
        mode="midday",
        performance_context={"offensive": {"pullback_resume": {"allowed": True}, "trend_follow": {"allowed": True}}},
    )

    assert snapshot["mode"] == "midday"
    assert snapshot["market_regime"] in {"进攻", "均衡"}
    assert len(snapshot["holdings"]) == 2

    leader = next(item for item in snapshot["holdings"] if item["code"] == "159819")
    laggard = next(item for item in snapshot["holdings"] if item["code"] == "512480")

    assert leader["final_action"] == "持有"
    assert leader["setup_type"] in {"trend_follow", "pullback_resume"}
    assert leader["execution_window"] == "尾盘再确认"
    assert leader["invalid_condition"]

    assert laggard["setup_type"] in {"rebound_trap", "conflict"}
    assert laggard["final_action"] in {"持有", "减配"}
    assert laggard["evidence"]
