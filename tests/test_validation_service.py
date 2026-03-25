from src.service.validation_service import ValidationService


class _FakeDB:
    def get_records_range(self, mode="close", days=7):
        if mode == "close":
            return [{"date": "2026-03-25", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {}}]
        if mode == "swing":
            return [{"date": "2026-03-25", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {}}]
        return []


def test_validation_service_builds_result_with_backtest_and_walkforward(monkeypatch):
    service = ValidationService(_FakeDB(), config={"portfolio_state": {"lot_size": 100}})

    monkeypatch.setattr(
        service,
        "_compute_swing_validation_report",
        lambda historical_records, request=None: {
            "live": {"summary_text": "真实建议近期有效。", "scorecard": {"windows": [20], "stats": {"overall": {20: {"count": 6}}}}},
            "scorecard": {"windows": [20], "stats": {"overall": {20: {"count": 12}}}},
            "backtest": {"summary_text": "回测收益9.4%，最大回撤-5.2%，交易4笔", "trade_count": 4, "total_return": 0.094, "max_drawdown": -0.052},
            "walkforward": {"segment_count": 5, "segments": [{"id": 1}], "avg_total_return": 0.012},
            "performance_context": {"offensive": {"pullback_resume": {"allowed": True, "reason": "历史样本支持"}}},
            "summary_text": "最近这套中期动作整体有效，可以继续进攻。",
        },
    )

    result = service.build_validation_result(mode="swing", days=30)

    assert result.mode == "swing"
    assert result.compact["synthetic_sample_count"] == 12
    assert result.compact["backtest_trade_count"] == 4
    assert result.details["walkforward"]["segment_count"] == 5


def test_validation_service_build_snapshot_returns_text_payload(monkeypatch):
    service = ValidationService(_FakeDB(), config={"portfolio_state": {"lot_size": 100}})

    monkeypatch.setattr(
        service,
        "build_validation_result",
        lambda **kwargs: type(
            "FakeResult",
            (),
            {
                "to_dict": lambda self: {
                    "mode": "swing",
                    "summary_text": "历史验证支持继续进攻。",
                    "text": "历史验证支持继续进攻。\n回测: 回测收益9.4%，最大回撤-5.2%，交易4笔",
                    "compact": {"verdict": "supportive"},
                    "as_of_date": "2026-03-25",
                }
            },
        )(),
    )

    snapshot = service.build_validation_snapshot(mode="swing", days=30)

    assert snapshot["mode"] == "swing"
    assert snapshot["compact"]["verdict"] == "supportive"
    assert "回测" in snapshot["text"]


def test_validation_service_preset_defaults_to_investor_universe(monkeypatch):
    service = ValidationService(
        _FakeDB(),
        config={
            "portfolio": [{"code": "510300"}],
            "watchlist": [{"code": "512660"}],
            "portfolio_state": {"lot_size": 100},
        },
    )

    monkeypatch.setattr(
        service,
        "_compute_swing_validation_report",
        lambda historical_records, request=None: {
            "live": None,
            "scorecard": {"windows": [20], "stats": {"overall": {20: {"count": 1}}}},
            "backtest": {"summary_text": "正式回测样本不足，暂不放大解释", "trade_count": 0, "total_return": 0.0, "max_drawdown": 0.0},
            "walkforward": {"segment_count": 0, "segments": [], "avg_total_return": 0.0},
            "performance_context": {"offensive": {"pullback_resume": {"allowed": False, "reason": "样本不足"}}},
            "summary_text": "历史样本还不够，当前先把这套信号当辅助参考，不单独放大仓位。",
            "request_codes": request.codes,
        },
    )

    result = service.build_validation_result(mode="swing", days=30, preset="portfolio_focus")

    assert result.details["request"]["codes"] == ["510300", "512660"]


def test_synthetic_swing_records_keep_target_weight_for_hold_actions(monkeypatch):
    service = ValidationService(_FakeDB(), config={"portfolio_state": {"lot_size": 100}})

    monkeypatch.setattr(
        "src.service.validation_service.build_swing_report",
        lambda report_input, context_window, analysis_date: {
            "actions": [
                {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "action_label": "持有",
                    "confidence": "高",
                    "target_weight": "35%-45%",
                }
            ]
        },
    )

    records = [
        {"date": "2026-03-24", "raw_data": {"stocks": [{"code": "510300", "name": "沪深300ETF", "close": 10.0}]}, "ai_result": {}}
    ]

    synthetic = service._build_synthetic_swing_records(records)

    assert synthetic[0]["ai_result"]["actions"][0]["target_weight"] == "35%-45%"
