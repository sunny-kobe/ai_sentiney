import asyncio
import json

from src.service.analysis_service import AnalysisService


def _make_swing_input():
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


def test_run_analysis_swing_mode_uses_deterministic_report_without_gemini(monkeypatch):
    service = AnalysisService()
    captured = {}
    history = [{"date": "2026-03-20", "raw_data": {"stocks": []}, "ai_result": {"actions": []}}]

    async def fake_collect(_portfolio):
        return _make_swing_input()

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: history)
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: captured.update(
            {"historical_records": historical_records, "analysis_date": analysis_date}
        )
        or {
            "mode": "swing",
            "market_regime": "进攻",
            "market_conclusion": "当前偏进攻，可以把仓位集中到最强方向。",
            "position_plan": {"total_exposure": "90%-100%"},
            "portfolio_actions": {"增配": [{"code": "512480", "name": "半导体ETF"}], "持有": [], "减配": [], "回避": [], "观察": []},
            "actions": [{"code": "512480", "name": "半导体ETF", "action_label": "增配", "conclusion": "增配"}],
            "technical_evidence": [],
        },
    )
    monkeypatch.setattr(service, "_compute_swing_scorecard", lambda historical_records: {"summary_text": "10日样本3，平均收益2.0%"})
    monkeypatch.setattr(
        "src.service.analysis_service.GeminiClient",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called in swing mode")),
    )
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    result = asyncio.run(service.run_analysis(mode="swing"))

    assert result["market_regime"] == "进攻"
    assert result["swing_scorecard"]["summary_text"] == "10日样本3，平均收益2.0%"
    assert result["position_plan"]["total_exposure"] == "90%-100%"
    assert result["quality_status"] == "normal"
    assert captured["historical_records"] == history
    assert captured["analysis_date"] == "2026-03-23"


def test_run_analysis_swing_mode_loads_close_history_for_scorecard(monkeypatch):
    service = AnalysisService()
    calls = []

    async def fake_collect(_portfolio):
        return _make_swing_input()

    def fake_history(days=90):
        calls.append(days)
        return [{"date": "2026-03-20", "raw_data": {"stocks": []}, "ai_result": {"actions": []}}]

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_get_swing_history_records", fake_history)
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: {
            "mode": "swing",
            "market_regime": "均衡",
            "market_conclusion": "当前偏均衡。",
            "portfolio_actions": {"增配": [], "持有": [], "减配": [], "回避": [], "观察": []},
            "actions": [],
            "technical_evidence": [],
        },
    )
    monkeypatch.setattr(service, "_compute_swing_scorecard", lambda historical_records: {"summary_text": "20日样本5，平均收益1.5%"})
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    result = asyncio.run(service.run_analysis(mode="swing"))

    assert calls == [90]
    assert result["swing_scorecard"]["summary_text"].startswith("20日样本")


def test_ask_question_accuracy_query_in_swing_mode_uses_medium_term_report(monkeypatch):
    service = AnalysisService()

    monkeypatch.setattr(service, "_run_swing_accuracy_report", lambda: "10日样本8，平均收益2.4%，平均回撤-1.8%")

    answer = asyncio.run(service.ask_question("最近准确率怎么样", mode="swing"))

    assert "10日样本" in answer
    assert "平均收益" in answer
    assert "命中率" not in answer


def test_build_swing_benchmark_map_reuses_shared_resolution(monkeypatch):
    service = AnalysisService()
    calls = []
    records = [
        {
            "date": "2026-03-20",
            "raw_data": {
                "stocks": [
                    {"code": "300308", "name": "人工智能龙头"},
                    {"code": "563300", "name": "中证2000ETF"},
                    {"code": "510300", "name": "沪深300ETF"},
                ]
            },
            "ai_result": {"actions": []},
        }
    ]

    def fake_resolve(stock, available_codes):
        calls.append((stock["code"], tuple(sorted(available_codes))))
        return {
            "300308": "159819",
            "563300": "510500",
            "510300": "159338",
        }[stock["code"]]

    monkeypatch.setattr("src.service.analysis_service.resolve_benchmark_code", fake_resolve)

    benchmark_map = service._build_swing_benchmark_map(records)

    assert benchmark_map == {"300308": "159819", "563300": "510500", "510300": "159338"}
    assert calls == [
        ("300308", ("300308", "510300", "563300")),
        ("563300", ("300308", "510300", "563300")),
        ("510300", ("300308", "510300", "563300")),
    ]


def test_ask_question_in_swing_mode_includes_position_sizing(monkeypatch):
    service = AnalysisService()

    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: [])
    monkeypatch.setattr(
        service,
        "_load_cached_context",
        lambda mode: {
            "context_date": "2026-03-23",
            "stocks": [{"code": "510300", "name": "沪深300ETF"}],
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: {
            "market_conclusion": "当前偏均衡。",
            "position_plan": {
                "total_exposure": "65%-80%",
                "core_target": "40%-50%",
                "satellite_target": "15%-20%",
                "cash_target": "20%-35%",
            },
            "portfolio_actions": {"增配": [], "持有": [{"name": "沪深300ETF"}], "减配": [], "回避": [], "观察": []},
            "actions": [{"name": "沪深300ETF", "conclusion": "持有", "plan": "先拿住。"}],
        },
    )
    monkeypatch.setattr(service, "_compute_swing_scorecard", lambda historical_records: None)

    answer = asyncio.run(service.ask_question("本周仓位怎么配", mode="swing"))

    assert "总仓位" in answer
    assert "核心仓" in answer
    assert "现金" in answer


def test_load_cached_context_for_swing_falls_back_when_latest_context_has_no_stocks(tmp_path, monkeypatch):
    service = AnalysisService()
    empty_cache = tmp_path / "latest_context.json"
    empty_cache.write_text(json.dumps({"context_date": "2026-03-23", "stocks": []}, ensure_ascii=False), encoding="utf-8")
    service.data_path = empty_cache

    monkeypatch.setattr(
        service.db,
        "get_latest_record",
        lambda mode: {"context_date": "2026-03-22", "stocks": [{"code": "510300", "name": "沪深300ETF"}]} if mode == "close" else None,
    )

    cached = service._load_cached_context("swing")

    assert cached["context_date"] == "2026-03-22"
    assert cached["stocks"][0]["code"] == "510300"
