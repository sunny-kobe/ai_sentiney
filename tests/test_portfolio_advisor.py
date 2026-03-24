from src.service.portfolio_advisor import build_investor_snapshot


def test_build_investor_snapshot_merges_holdings_and_watchlist_without_duplicates():
    snapshot = build_investor_snapshot(
        portfolio=[
            {"code": "510300", "name": "沪深300ETF", "strategy": "value", "shares": 600},
            {"code": "512480", "name": "半导体ETF", "strategy": "trend", "shares": 4200},
        ],
        watchlist=[
            {"code": "512480", "name": "半导体ETF", "strategy": "trend", "priority": "high"},
            {"code": "512660", "name": "军工ETF", "strategy": "trend", "priority": "high"},
        ],
        portfolio_state={"cash_balance": 33091.73, "lot_size": 100},
        swing_config={"risk_profile": "aggressive", "candidate_limit": 3, "min_cash_buffer": 0.05},
    )

    assert snapshot["held_codes"] == {"510300", "512480"}
    assert snapshot["watchlist_codes"] == {"512660"}
    assert [item["code"] for item in snapshot["universe"]] == ["510300", "512480", "512660"]
    assert snapshot["portfolio_state"]["cash_balance"] == 33091.73
    assert snapshot["strategy_preferences"]["candidate_limit"] == 3

    holding = next(item for item in snapshot["universe"] if item["code"] == "512480")
    candidate = next(item for item in snapshot["universe"] if item["code"] == "512660")

    assert holding["held"] is True
    assert candidate["held"] is False
    assert candidate["shares"] == 0

