import asyncio

from src.service.analysis_service import AnalysisService


def test_run_analysis_blocks_when_input_quality_is_blocked(monkeypatch):
    service = AnalysisService()

    async def fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "N/A",
            "indices": {},
            "macro_news": {"telegraph": []},
            "stocks": [],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called")))

    result = asyncio.run(service.run_analysis(mode="midday"))

    assert result["quality_status"] == "blocked"
    assert "missing_stocks" in result["quality_issues"]


def test_run_analysis_degrades_to_structured_report_without_ai(monkeypatch):
    service = AnalysisService()

    async def fake_collect(_portfolio):
        return {
            "context_date": "2026-03-21",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": []},
            "stocks": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "SAFE",
                    "confidence": "高",
                    "tech_summary": "[日线_MACD_多头_无背驰_0]",
                    "current_price": 1500.0,
                    "pct_change": 1.0,
                    "news": [],
                }
            ],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called")))

    result = asyncio.run(service.run_analysis(mode="midday"))

    assert result["quality_status"] == "degraded"
    assert result["structured_report"]["stocks"][0]["signal"] == "SAFE"
    assert result["actions"][0]["operation"] == "持有观察"


def test_run_analysis_normal_mode_passes_structured_report_to_gemini(monkeypatch):
    service = AnalysisService()
    captured = {}

    async def fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "SAFE",
                    "confidence": "高",
                    "tech_summary": "[日线_MACD_多头_无背驰_0]",
                    "current_price": 1500.0,
                    "pct_change": 1.0,
                    "news": ["公司回购进展"],
                }
            ],
        }

    class DummyGemini:
        def analyze(self, ai_input):
            captured["structured_report"] = ai_input.get("structured_report")
            return {
                "market_sentiment": "分歧",
                "volume_analysis": "平量",
                "macro_summary": "市场分歧震荡",
                "actions": [
                    {"code": "600519", "name": "贵州茅台", "operation": "错误操作", "reason": "量价配合"}
                ],
            }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: DummyGemini())

    result = asyncio.run(service.run_analysis(mode="midday"))

    assert result["quality_status"] == "normal"
    assert captured["structured_report"]["stocks"][0]["signal"] == "SAFE"
    assert result["structured_report"]["stocks"][0]["operation"] == "持有观察"
