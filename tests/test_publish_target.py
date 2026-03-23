import asyncio
from unittest.mock import Mock

from src.service.analysis_service import AnalysisService


class _DummyGemini:
    def analyze(self, ai_input):
        return {"actions": []}

    def analyze_with_prompt(self, ai_input, system_prompt):
        return {"actions": []}

    def analyze_morning(self, morning_data, system_prompt):
        return {"actions": []}


def test_publish_target_telegram_routes_to_telegram(monkeypatch):
    service = AnalysisService()

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='midday': result)
    monkeypatch.setattr(service.db, "get_last_close_analysis", lambda: None)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)

    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram, raising=False)

    asyncio.run(service.run_analysis(mode="midday", publish=True, publish_target="telegram"))

    telegram.send_midday_report.assert_called_once()
    feishu.send_card.assert_not_called()


def test_publish_target_default_routes_to_feishu(monkeypatch):
    service = AnalysisService()

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='midday': result)
    monkeypatch.setattr(service.db, "get_last_close_analysis", lambda: None)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)

    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="midday", publish=True))

    feishu.send_card.assert_called_once()
    telegram.send_midday_report.assert_not_called()


def test_publish_target_telegram_routes_close_to_telegram(monkeypatch):
    service = AnalysisService()

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='midday': result)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="close", publish=True, publish_target="telegram"))

    telegram.send_close_report.assert_called_once()
    feishu.send_close_card.assert_not_called()


def test_publish_target_telegram_routes_morning_to_telegram(monkeypatch):
    service = AnalysisService()

    async def _fake_collect_morning(_portfolio):
        return {
            "context_date": "2026-03-23",
            "global_indices": [],
            "commodities": [],
            "us_treasury": {},
            "macro_news": {},
            "stocks": [],
        }

    monkeypatch.setattr(service, "collect_and_process_morning_data", _fake_collect_morning)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='morning': result)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr("src.service.analysis_service.GeminiClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="morning", publish=True, publish_target="telegram"))

    telegram.send_morning_report.assert_called_once()
    feishu.send_morning_card.assert_not_called()
