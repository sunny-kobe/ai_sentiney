import asyncio
from datetime import datetime

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


def test_run_analysis_midday_uses_rule_engine_without_gemini(monkeypatch):
    service = AnalysisService()
    captured = {}
    today = datetime.now().strftime("%Y-%m-%d")

    async def fake_collect(_portfolio):
        return {
            "context_date": today,
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

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "src.service.analysis_service.build_strategy_snapshot",
        lambda ai_input, historical_records, mode, performance_context=None: captured.update(
            {"mode": mode, "structured_report": ai_input.get("structured_report")}
        )
        or {
            "mode": mode,
            "market_regime": "均衡",
            "holdings": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "final_action": "持有",
                    "setup_type": "trend_follow",
                    "execution_window": "尾盘再确认",
                    "target_weight_range": "0%",
                    "rebalance_instruction": "尾盘再确认，不盘中追高",
                    "evidence_text": "价格仍在强势区",
                    "invalid_condition": "跌回MA20下方则转弱",
                    "current_price": 1500.0,
                    "ma20": 1480.0,
                    "pct_change": 1.0,
                    "tech_summary": "[日线_MACD_多头_无背驰_0]",
                }
            ],
            "market_drivers": ["市场分歧"],
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_intraday_rule_report",
        lambda ai_input, strategy_snapshot, mode, scorecard=None: {
            "market_sentiment": "分歧平衡",
            "volume_analysis": "分歧整理",
            "macro_summary": "先看风险与强弱分化，主动加仓留到尾盘再确认。",
            "actions": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "持有",
                    "operation": "尾盘再确认，不盘中追高",
                    "reason": "价格仍在强势区。失效条件：跌回MA20下方则转弱",
                }
            ],
            "strategy_snapshot": strategy_snapshot,
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.GeminiClient",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    result = asyncio.run(service.run_analysis(mode="midday"))

    assert result["quality_status"] == "normal"
    assert captured["mode"] == "midday"
    assert captured["structured_report"]["stocks"][0]["signal"] == "SAFE"
    assert result["actions"][0]["operation"] == "尾盘再确认，不盘中追高"
    assert result["strategy_snapshot"]["market_regime"] == "均衡"


def test_run_analysis_preclose_uses_rule_engine_without_gemini(monkeypatch):
    service = AnalysisService()
    captured = {"mode": None, "structured_report": None}
    today = datetime.now().strftime("%Y-%m-%d")

    async def fake_collect(_portfolio):
        return {
            "context_date": today,
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["尾盘银行股护盘"]},
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

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr(service.db, "get_last_close_analysis", lambda: None)
    monkeypatch.setattr(
        "src.service.analysis_service.build_strategy_snapshot",
        lambda ai_input, historical_records, mode, performance_context=None: captured.update(
            {"mode": mode, "structured_report": ai_input.get("structured_report")}
        )
        or {
            "mode": mode,
            "market_regime": "均衡",
            "holdings": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "final_action": "持有",
                    "setup_type": "trend_follow",
                    "execution_window": "今日不动",
                    "target_weight_range": "0%",
                    "rebalance_instruction": "今日不动",
                    "evidence_text": "量价稳定",
                    "invalid_condition": "跌回MA20下方则转弱",
                    "current_price": 1500.0,
                    "ma20": 1480.0,
                    "pct_change": 1.0,
                    "tech_summary": "[日线_MACD_多头_无背驰_0]",
                }
            ],
            "market_drivers": ["尾盘确认"],
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_intraday_rule_report",
        lambda ai_input, strategy_snapshot, mode, scorecard=None: {
            "market_sentiment": "分歧平衡",
            "volume_analysis": "温和修复",
            "macro_summary": "整体建议：其余仓位以不动为主。",
            "actions": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "持有",
                    "operation": "今日不动",
                    "reason": "量价稳定。失效条件：跌回MA20下方则转弱",
                }
            ],
            "strategy_snapshot": strategy_snapshot,
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.GeminiClient",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    result = asyncio.run(service.run_analysis(mode="preclose"))

    assert captured["mode"] == "preclose"
    assert captured["structured_report"]["mode"] == "preclose"
    assert result["quality_status"] == "normal"
    assert result["actions"][0]["operation"] == "今日不动"


def test_run_analysis_close_uses_rule_engine_without_gemini(monkeypatch):
    service = AnalysisService()
    captured = {}
    today = datetime.now().strftime("%Y-%m-%d")

    async def fake_collect(_portfolio):
        return {
            "context_date": today,
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["收盘后等待次日确认"]},
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

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_compute_signal_scorecard", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "src.service.analysis_service.build_strategy_snapshot",
        lambda ai_input, historical_records, mode, performance_context=None: captured.update({"mode": mode})
        or {
            "mode": mode,
            "market_regime": "均衡",
            "holdings": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "final_action": "持有",
                    "setup_type": "trend_follow",
                    "execution_window": "明日观察",
                    "target_weight_range": "0%",
                    "rebalance_instruction": "继续持有，等待下一次确认",
                    "evidence_text": "收盘结构未破坏",
                    "invalid_condition": "明日跌回MA20下方则转弱",
                    "current_price": 1500.0,
                    "ma20": 1480.0,
                    "pct_change": 1.0,
                    "tech_summary": "[日线_MACD_多头_无背驰_0]",
                }
            ],
            "market_drivers": ["收盘确认"],
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_close_rule_report",
        lambda ai_input, strategy_snapshot, scorecard=None: {
            "market_summary": "当前属于均衡环境，收盘后以条件计划为主。",
            "market_temperature": "分歧平衡",
            "actions": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "today_review": "收盘结构未破坏",
                    "tomorrow_plan": "优先持有观察，不急着加减; 明日跌回MA20下方则转弱",
                    "support_level": 1450.0,
                    "resistance_level": 1545.0,
                }
            ],
            "strategy_snapshot": strategy_snapshot,
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.GeminiClient",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    result = asyncio.run(service.run_analysis(mode="close"))

    assert captured["mode"] == "close"
    assert result["quality_status"] == "normal"
    assert result["actions"][0]["tomorrow_plan"].startswith("优先持有观察")
