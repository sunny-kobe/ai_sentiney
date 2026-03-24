from src.backtest.walkforward import run_walkforward_validation


def _record(record_date, price, action_label="持有", target_weight="0%"):
    return {
        "date": record_date,
        "raw_data": {
            "stocks": [
                {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "open": price,
                    "current_price": price,
                    "close": price,
                }
            ]
        },
        "ai_result": {
            "actions": [
                {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "action_label": action_label,
                    "target_weight": target_weight,
                }
            ]
        },
    }


def test_run_walkforward_validation_aggregates_multiple_test_windows():
    records = [
        _record("2026-03-01", 10.0, "增配", "50%"),
        _record("2026-03-02", 10.2, "持有", "50%"),
        _record("2026-03-03", 10.4, "回避", "0%"),
        _record("2026-03-04", 10.5, "增配", "50%"),
        _record("2026-03-05", 10.8, "持有", "50%"),
        _record("2026-03-06", 11.0, "回避", "0%"),
    ]

    report = run_walkforward_validation(records, train_window=2, test_window=2, initial_cash=10_000)

    assert report["segment_count"] == 2
    assert len(report["segments"]) == 2
    assert "avg_total_return" in report
