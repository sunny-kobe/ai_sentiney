from datetime import date

import pandas as pd

from src.utils.trading_calendar import is_trading_day, should_run_market_report


def test_is_trading_day_uses_exchange_calendar(monkeypatch):
    trade_dates = pd.DataFrame({"trade_date": pd.to_datetime(["2026-03-19", "2026-03-20"])})

    monkeypatch.setattr(
        "src.utils.trading_calendar.ak.tool_trade_date_hist_sina",
        lambda: trade_dates,
    )

    result = is_trading_day(date(2026, 3, 19))

    assert result["is_trading_day"] is True
    assert result["source"] == "exchange_calendar"
    assert result["fallback"] is False


def test_should_run_market_report_skips_non_trading_day(monkeypatch):
    monkeypatch.setattr(
        "src.utils.trading_calendar.is_trading_day",
        lambda target_date=None: {
            "date": "2026-03-21",
            "is_trading_day": False,
            "source": "exchange_calendar",
            "fallback": False,
        },
    )

    decision = should_run_market_report(mode="midday", publish=True, target_date=date(2026, 3, 21))

    assert decision["should_run"] is False
    assert decision["skip_reason"] == "non_trading_day"
    assert decision["calendar"]["is_trading_day"] is False


def test_is_trading_day_falls_back_to_weekday_when_calendar_fails(monkeypatch):
    monkeypatch.setattr(
        "src.utils.trading_calendar.ak.tool_trade_date_hist_sina",
        lambda: (_ for _ in ()).throw(RuntimeError("calendar down")),
    )

    result = is_trading_day(date(2026, 3, 19))

    assert result["is_trading_day"] is True
    assert result["source"] == "weekday_fallback"
    assert result["fallback"] is True
