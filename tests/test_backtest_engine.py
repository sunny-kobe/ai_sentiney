import pytest

from src.backtest.adapter import build_orders_from_actions
from src.backtest.engine import run_deterministic_backtest


def _record(record_date, stocks, actions):
    return {
        "date": record_date,
        "raw_data": {"stocks": stocks},
        "ai_result": {"actions": actions},
    }


def test_run_deterministic_backtest_executes_signals_on_next_open_with_lot_rounding_and_costs():
    records = [
        _record(
            "2026-03-20",
            [{"code": "510300", "name": "沪深300ETF", "open": 10.0, "current_price": 10.0, "close": 10.0}],
            [{"code": "510300", "name": "沪深300ETF", "action_label": "增配", "target_weight": "53%"}],
        ),
        _record(
            "2026-03-21",
            [{"code": "510300", "name": "沪深300ETF", "open": 10.5, "current_price": 10.8, "close": 10.8}],
            [{"code": "510300", "name": "沪深300ETF", "action_label": "回避", "target_weight": "0%"}],
        ),
        _record(
            "2026-03-22",
            [{"code": "510300", "name": "沪深300ETF", "open": 11.0, "current_price": 10.9, "close": 10.9}],
            [],
        ),
    ]

    result = run_deterministic_backtest(
        records,
        initial_cash=10_000,
        fee_rate=0.001,
        sell_tax_rate=0.001,
        slippage_rate=0.0,
        lot_size=100,
    )

    assert result["trades"][0]["trade_date"] == "2026-03-21"
    assert result["trades"][0]["fill_price"] == pytest.approx(10.5)
    assert result["trades"][0]["shares"] == 500
    assert result["trades"][1]["trade_date"] == "2026-03-22"
    assert result["trades"][1]["shares"] == 500
    assert result["positions"].get("510300", 0) == 0
    assert result["cash"] > 10_000
    assert result["total_fees"] > 0


def test_build_orders_from_actions_supports_action_defaults_without_target_weight():
    orders = build_orders_from_actions(
        [{"code": "512480", "name": "半导体ETF", "action_label": "增配"}],
        trade_date="2026-03-25",
    )

    assert orders[0]["code"] == "512480"
    assert orders[0]["target_weight"] == pytest.approx(0.2)

