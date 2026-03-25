import json
import logging
import sys

import src.main as main_module
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
    snapshot = {"mode": "swing", "summary_text": "真实建议跟踪近90天已兑现20日建议8笔。", "live": {"summary_text": "live"}}

    class FakeService:
        def build_validation_snapshot(self, mode: str):
            assert mode == "swing"
            return snapshot

        async def run_analysis(self, **kwargs):
            raise AssertionError("run_analysis should not be called for --validation-report")

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: FakeService())
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["sentinel", "--mode", "swing", "--validation-report", "--output", "json"],
    )

    main_module.entry_point()

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == snapshot


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
