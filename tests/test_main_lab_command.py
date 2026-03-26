import json
from pathlib import Path

import src.main as main_module


def test_entry_point_lab_command_outputs_json(monkeypatch, capsys):
    class FakeResult:
        def to_dict(self):
            return {
                "mode": "swing",
                "preset": "aggressive_midterm",
                "winner": "candidate",
                "summary_text": "candidate 更优",
            }

    class FakeService:
        def build_lab_result(self, **kwargs):
            assert kwargs["preset"] == "aggressive_midterm"
            assert kwargs["overrides"] == ["confidence_min=高"]
            return FakeResult()

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: FakeService())
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["sentinel", "lab", "--mode", "swing", "--preset", "aggressive_midterm", "--override", "confidence_min=高", "--output", "json"],
    )

    main_module.entry_point()

    out = json.loads(capsys.readouterr().out)
    assert out["winner"] == "candidate"


def test_readme_mentions_lab_command():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "python -m src.main lab --preset aggressive_midterm" in text
