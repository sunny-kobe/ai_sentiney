import json
from pathlib import Path

import src.main as main_module


def test_entry_point_validate_command_outputs_compact_validation_json(monkeypatch, capsys):
    class FakeResult:
        def to_dict(self):
            return {
                "mode": "swing",
                "summary_text": "历史验证支持继续进攻。",
                "compact": {"verdict": "supportive", "offensive_allowed": True},
                "as_of_date": "2026-03-25",
            }

    class FakeService:
        def build_validation_result(self, **kwargs):
            assert kwargs["mode"] == "swing"
            assert kwargs["date_from"] == "2026-03-01"
            assert kwargs["date_to"] == "2026-03-20"
            return FakeResult()

        def build_validation_snapshot(self, mode: str):
            raise AssertionError("legacy validation snapshot should not be used for validate command")

        async def run_analysis(self, **kwargs):
            raise AssertionError("run_analysis should not be called for validate command")

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: FakeService())
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        [
            "sentinel",
            "validate",
            "--mode",
            "swing",
            "--from",
            "2026-03-01",
            "--to",
            "2026-03-20",
            "--output",
            "json",
        ],
    )

    main_module.entry_point()

    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["mode"] == "swing"
    assert parsed["compact"]["verdict"] == "supportive"


def test_entry_point_experiment_command_prints_text(monkeypatch, capsys):
    class FakeResult:
        investor_summary = "实验结果支持继续进攻。"
        text = "实验结果支持继续进攻。\n回测: 回测收益9.4%，最大回撤-5.2%，交易4笔"

        def to_dict(self):
            return {
                "mode": "swing",
                "summary_text": self.investor_summary,
                "text": self.text,
                "compact": {"verdict": "supportive"},
            }

    class FakeService:
        def build_validation_result(self, **kwargs):
            assert kwargs["preset"] == "aggressive_midterm"
            return FakeResult()

        async def run_analysis(self, **kwargs):
            raise AssertionError("run_analysis should not be called for experiment command")

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: FakeService())
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        [
            "sentinel",
            "experiment",
            "--preset",
            "aggressive_midterm",
            "--mode",
            "swing",
        ],
    )

    main_module.entry_point()

    out = capsys.readouterr().out
    assert "实验结果支持继续进攻" in out
    assert "回测" in out


def test_readme_mentions_validate_and_experiment_commands():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "python -m src.main validate --mode swing" in text
    assert "python -m src.main experiment --preset aggressive_midterm" in text
