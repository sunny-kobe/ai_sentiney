import asyncio
import json

from src.service.analysis_service import AnalysisService


def test_replay_dry_run_skips_ai_call(tmp_path, monkeypatch):
    service = AnalysisService()

    replay_file = tmp_path / "latest_context.json"
    replay_file.write_text(
        json.dumps(
            {
                "context_date": "2026-03-19",
                "market_breadth": "涨: 10 / 跌: 5 (平: 1)",
                "north_funds": 0,
                "indices": {},
                "macro_news": {},
                "stocks": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service.data_path = replay_file

    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode="midday": result)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(
        "src.service.analysis_service.GeminiClient",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called in replay dry-run")),
    )

    result = asyncio.run(service.run_analysis(mode="midday", replay=True, dry_run=True))

    assert result["market_sentiment"] == "DryRun"
    assert result["actions"] == []
