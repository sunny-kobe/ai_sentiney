from src.service.validation_service import ValidationService


def test_build_comparison_diff_reports_return_drawdown_and_trade_deltas():
    service = ValidationService(db=None, config={})

    diff = service._build_comparison_diff(
        baseline={"backtest": {"total_return": 0.08, "max_drawdown": -0.10, "trade_count": 4}},
        candidate={"backtest": {"total_return": 0.11, "max_drawdown": -0.07, "trade_count": 10}},
    )

    assert diff["total_return_delta"] == 0.03
    assert diff["max_drawdown_delta"] == 0.03
    assert diff["trade_count_delta"] == 6
