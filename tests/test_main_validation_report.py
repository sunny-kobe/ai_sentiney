import json
import logging
import sys

import src.main as main_module
from src.service.analysis_service import AnalysisService
from src.utils.logger import setup_logger


def test_entry_point_validation_report_prints_swing_validation(monkeypatch, capsys):
    class FakeService:
        def build_validation_snapshot(self, mode: str):
            assert mode == "swing"
            return {"mode": "swing", "summary_text": "真实建议跟踪近90天已兑现20日建议8笔。"}

        async def run_analysis(self, **kwargs):
            raise AssertionError("run_analysis should not be called for --validation-report")

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: FakeService())
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["sentinel", "--mode", "swing", "--validation-report"],
    )

    main_module.entry_point()

    out = capsys.readouterr().out
    assert "真实建议跟踪近90天已兑现20日建议8笔" in out


def test_entry_point_validation_report_prints_json_when_requested(monkeypatch, capsys):
    service = AnalysisService()
    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: [{"date": "2026-03-23"}])
    monkeypatch.setattr(
        service,
        "_compute_swing_validation_report",
        lambda records: {
            "live": {
                "summary_text": "真实建议跟踪近90天已兑现20日建议6笔。",
                "scorecard": {
                    "windows": [20],
                    "stats": {"overall": {20: {"count": 6, "avg_absolute_return": 0.041, "avg_relative_return": 0.018, "avg_max_drawdown": -0.031}}},
                    "evaluations": [{"code": "510300"}],
                },
            },
            "scorecard": {
                "windows": [20],
                "stats": {"overall": {20: {"count": 12, "avg_absolute_return": 0.033, "avg_relative_return": 0.012, "avg_max_drawdown": -0.052}}},
                "evaluations": [{"code": "510300"}],
            },
            "backtest": {"summary_text": "回测收益9.4%，最大回撤-5.2%，交易4笔", "total_return": 0.094, "max_drawdown": -0.052, "trade_count": 4},
            "walkforward": {"segment_count": 5, "segments": [{"id": 1}], "avg_total_return": 0.012},
            "performance_context": {
                "offensive": {
                    "pullback_resume": {"allowed": False, "reason": "样本不足"}
                }
            },
            "summary_text": "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。参考：20日样本12，平均收益3.3%，平均跑赢基准1.2%，平均回撤-5.2%；回测收益9.4%，最大回撤-5.2%，交易4笔；滚动验证5段，平均收益1.2%。",
        },
    )

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: service)
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["sentinel", "--mode", "swing", "--validation-report", "--output", "json"],
    )

    main_module.entry_point()

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["mode"] == "swing"
    assert parsed["compact"]["synthetic_sample_count"] == 12
    assert parsed["compact"]["backtest_trade_count"] == 4
    assert "evaluations" not in out


def test_console_logger_uses_stderr():
    test_logger = logging.getLogger("validation-report-stderr")
    for handler in list(test_logger.handlers):
        test_logger.removeHandler(handler)

    configured = setup_logger("validation-report-stderr")
    console_handlers = [
        handler
        for handler in configured.handlers
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
    ]

    assert console_handlers
    assert all(getattr(handler, "stream", None) is sys.stderr for handler in console_handlers)
