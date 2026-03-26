from src.service.strategy_lab_service import StrategyLabService


def test_strategy_lab_service_merges_risk_profile_into_portfolio_overrides():
    service = StrategyLabService(db=None, config={})

    merged = service._merge_overrides(
        {
            "rule_overrides": {},
            "parameter_overrides": {},
            "portfolio_overrides": {},
        },
        {"risk_profile": "balanced", "watchlist_limit": "2"},
    )

    assert merged["portfolio_overrides"] == {"risk_profile": "balanced", "watchlist_limit": "2"}
    assert merged["rule_overrides"] == {}


def test_strategy_lab_service_returns_baseline_candidate_and_winner(monkeypatch):
    service = StrategyLabService(db=None, config={})

    monkeypatch.setattr(service, "_build_variant_reports", lambda request: {
        "baseline": {"summary_text": "baseline", "backtest": {"total_return": 0.08, "max_drawdown": -0.10, "trade_count": 4}},
        "candidate": {"summary_text": "candidate", "backtest": {"total_return": 0.11, "max_drawdown": -0.07, "trade_count": 10}},
    })

    result = service.build_lab_result(mode="swing", preset="aggressive_midterm")

    assert result.winner == "candidate"
    assert "candidate" in result.summary_text


def test_strategy_lab_service_reports_diagnostic_improvement(monkeypatch):
    service = StrategyLabService(db=None, config={})

    monkeypatch.setattr(service, "_build_variant_reports", lambda request: {
        "baseline": {"summary_text": "baseline", "backtest": {"total_return": 0.08, "max_drawdown": -0.10, "trade_count": 4}, "diagnostics": {"top_drag": {"key": "持有"}}},
        "candidate": {"summary_text": "candidate", "backtest": {"total_return": 0.11, "max_drawdown": -0.07, "trade_count": 10}, "diagnostics": {"top_drag": {"key": "减配"}}},
    })

    result = service.build_lab_result(mode="swing", preset="defensive_exit_fix")

    assert result.diff["diagnostic_shift"]["baseline_top_drag"] == "持有"
    assert result.diff["diagnostic_shift"]["candidate_top_drag"] == "减配"
