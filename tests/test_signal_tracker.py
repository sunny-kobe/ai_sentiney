from src.processor.signal_tracker import evaluate_yesterday


def test_evaluate_yesterday_skips_stocks_without_fresh_quote():
    yesterday_actions = [
        {
            "code": "159819",
            "name": "人工智能ETF",
            "signal": "SAFE",
            "confidence": "高",
        }
    ]
    today_stocks = [
        {
            "code": "159819",
            "name": "人工智能ETF",
            "pct_change": 0.0,
            "quote_status": "missing",
        }
    ]

    result = evaluate_yesterday(yesterday_actions, today_stocks)

    assert result == []
