import asyncio
from unittest.mock import Mock

from src.service.analysis_service import AnalysisService


class _DummyGemini:
    def analyze(self, ai_input):
        return {"actions": []}

    def analyze_preclose(self, ai_input):
        return {"actions": []}

    def analyze_with_prompt(self, ai_input, system_prompt):
        return {"actions": []}

    def analyze_morning(self, morning_data, system_prompt):
        return {"actions": []}


def test_publish_target_telegram_routes_to_telegram(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='midday': result)
    monkeypatch.setattr(service.db, "get_last_close_analysis", lambda: None)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)

    monkeypatch.setattr("src.service.analysis_service.HybridAIClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram, raising=False)

    asyncio.run(service.run_analysis(mode="midday", publish=True, publish_target="telegram"))

    telegram.send_midday_report.assert_called_once()
    feishu.send_card.assert_not_called()


def test_publish_target_default_routes_to_feishu(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='midday': result)
    monkeypatch.setattr(service.db, "get_last_close_analysis", lambda: None)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)

    monkeypatch.setattr("src.service.analysis_service.HybridAIClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="midday", publish=True))

    feishu.send_card.assert_called_once()
    telegram.send_midday_report.assert_not_called()


def test_publish_target_telegram_routes_close_to_telegram(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='midday': result)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.service.analysis_service.HybridAIClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="close", publish=True, publish_target="telegram"))

    telegram.send_close_report.assert_called_once()
    feishu.send_close_card.assert_not_called()


def test_publish_target_telegram_routes_morning_to_telegram(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def _fake_collect_morning(_portfolio):
        return {
            "context_date": "2026-03-23",
            "global_indices": [],
            "commodities": [],
            "us_treasury": {},
            "macro_news": {},
            "stocks": [],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_morning_data", _fake_collect_morning)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='morning': result)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr("src.service.analysis_service.HybridAIClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="morning", publish=True, publish_target="telegram"))

    telegram.send_morning_report.assert_called_once()
    feishu.send_morning_card.assert_not_called()


def test_publish_target_telegram_routes_preclose_to_telegram(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def _fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "north_funds": 0,
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", _fake_collect)
    monkeypatch.setattr(service, "post_process_result", lambda result, _ai_input, mode='preclose': result)
    monkeypatch.setattr(service.db, "get_last_close_analysis", lambda: None)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.service.analysis_service.HybridAIClient", lambda: _DummyGemini())

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="preclose", publish=True, publish_target="telegram"))

    telegram.send_preclose_report.assert_called_once()
    feishu.send_preclose_card.assert_not_called()


def test_publish_target_telegram_routes_swing_with_lab_hint(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def fake_collect(_portfolio):
        return {
            "context_date": "2026-03-23",
            "market_breadth": "3200家上涨，1700家下跌",
            "indices": {"上证指数": {"change_pct": 0.8}, "创业板指": {"change_pct": 1.1}},
            "macro_news": {"telegraph": ["成交温和回暖，风险偏好修复"]},
            "stocks": [
                {
                    "code": "512480",
                    "name": "半导体ETF",
                    "signal": "OPPORTUNITY",
                    "confidence": "高",
                    "bias_pct": 0.06,
                    "pct_change": 2.2,
                    "current_price": 1.08,
                    "ma20": 1.0,
                    "tech_summary": "MACD金叉，站上20日线",
                    "macd": {"trend": "GOLDEN_CROSS"},
                    "obv": {"trend": "INFLOW"},
                }
            ],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: [])
    monkeypatch.setattr(
        service,
        "_compute_swing_validation_report",
        lambda historical_records: {
            "scorecard": None,
            "backtest": {"summary_text": "样本不足，暂无正式回测"},
            "performance_context": {"offensive": {"pullback_resume": {"allowed": False, "reason": "样本不足"}}},
            "summary_text": "样本不足，暂无正式回测",
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: {
            "mode": "swing",
            "market_regime": "均衡",
            "market_conclusion": "当前偏均衡。",
            "position_plan": {"total_exposure": "75%-90%"},
            "portfolio_actions": {"增配": [], "持有": [], "减配": [], "回避": [], "观察": []},
            "actions": [],
            "technical_evidence": [],
        },
    )
    monkeypatch.setattr(
        service,
        "_build_swing_lab_hint",
        lambda: {
            "preset": "aggressive_leader_focus",
            "winner": "candidate",
            "summary_text": "candidate 更优",
            "score_delta": 3.2,
            "trade_count_delta": -60,
            "candidate_trade_count": 18,
            "total_return_delta": 0.08,
            "max_drawdown_delta": 0.04,
        },
    )
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    feishu = Mock()
    telegram = Mock()
    monkeypatch.setattr("src.service.analysis_service.FeishuClient", lambda: feishu)
    monkeypatch.setattr("src.service.analysis_service.TelegramClient", lambda: telegram)

    asyncio.run(service.run_analysis(mode="swing", publish=True, publish_target="telegram"))

    telegram.send_swing_report.assert_called_once()
    payload = telegram.send_swing_report.call_args[0][0]
    assert payload["lab_hint"]["preset"] == "aggressive_leader_focus"
    feishu.send_swing_card.assert_not_called()
