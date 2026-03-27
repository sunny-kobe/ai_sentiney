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


def test_run_analysis_swing_mode_uses_deterministic_report_without_gemini(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"
    captured = {}
    history = [{"date": "2026-03-20", "raw_data": {"stocks": []}, "ai_result": {"actions": []}}]

    async def fake_collect(_portfolio):
        return _make_swing_input()

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: history)
    monkeypatch.setattr(
        service,
        "_compute_swing_validation_report",
        lambda historical_records: {
            "scorecard": {"summary_text": "20日样本6，平均收益3.0%"},
            "backtest": {"summary_text": "回测收益8.0%，最大回撤-4.0%"},
            "performance_context": {"offensive": {"pullback_resume": {"allowed": True, "reason": "样本通过"}}},
            "summary_text": "20日样本6，平均收益3.0%；回测收益8.0%，最大回撤-4.0%",
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: captured.update(
            {
                "historical_records": historical_records,
                "analysis_date": analysis_date,
                "performance_context": ai_input.get("performance_context"),
                "validation_report": ai_input.get("validation_report"),
            }
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
    monkeypatch.setattr(
        "src.service.analysis_service.GeminiClient",
        lambda: (_ for _ in ()).throw(AssertionError("Gemini should not be called in swing mode")),
    )
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    result = asyncio.run(service.run_analysis(mode="swing"))

    assert result["market_regime"] == "进攻"
    assert result["swing_scorecard"]["summary_text"] == "20日样本6，平均收益3.0%"
    assert result["validation_report"]["summary_text"] == "20日样本6，平均收益3.0%；回测收益8.0%，最大回撤-4.0%"
    assert result["position_plan"]["total_exposure"] == "90%-100%"
    assert result["quality_status"] == "normal"
    assert captured["historical_records"] == history
    assert captured["analysis_date"] == "2026-03-23"
    assert captured["performance_context"]["offensive"]["pullback_resume"]["allowed"] is True
    assert captured["validation_report"]["backtest"]["summary_text"].startswith("回测收益")


def test_build_swing_lab_hint_selects_best_preset_by_score_delta(monkeypatch):
    service = AnalysisService()
    calls = []

    payloads = {
        "aggressive_trend_guard": {
            "preset": "aggressive_trend_guard",
            "winner": "baseline",
            "summary_text": "baseline 更优",
            "summary": {"baseline_score": 2.0, "candidate_score": 1.5, "candidate_trade_count": 40},
            "diff": {"trade_count_delta": -10, "total_return_delta": -0.01, "max_drawdown_delta": -0.005},
        },
        "aggressive_leader_focus": {
            "preset": "aggressive_leader_focus",
            "winner": "candidate",
            "summary_text": "candidate 更优",
            "summary": {"baseline_score": 1.0, "candidate_score": 4.2, "candidate_trade_count": 18},
            "diff": {"trade_count_delta": -60, "total_return_delta": 0.08, "max_drawdown_delta": 0.04},
        },
        "aggressive_core_rotation": {
            "preset": "aggressive_core_rotation",
            "winner": "candidate",
            "summary_text": "candidate 更优",
            "summary": {"baseline_score": 0.8, "candidate_score": 2.6, "candidate_trade_count": 12},
            "diff": {"trade_count_delta": -70, "total_return_delta": 0.05, "max_drawdown_delta": 0.03},
        },
    }

    class _FakeResult:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, detail="compact"):
            assert detail == "compact"
            return self._payload

    monkeypatch.setattr(
        service,
        "build_lab_result",
        lambda **kwargs: calls.append(kwargs["preset"]) or _FakeResult(payloads[kwargs["preset"]]),
    )

    hint = service._build_swing_lab_hint()

    assert calls == ["aggressive_trend_guard", "aggressive_leader_focus", "aggressive_core_rotation"]
    assert hint["preset"] == "aggressive_leader_focus"
    assert hint["winner"] == "candidate"
    assert hint["score_delta"] == 3.2
    assert hint["candidate_trade_count"] == 18


def test_run_analysis_swing_mode_injects_lab_hint(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def fake_collect(_portfolio):
        return _make_swing_input()

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

    result = asyncio.run(service.run_analysis(mode="swing"))

    assert result["lab_hint"]["preset"] == "aggressive_leader_focus"
    assert result["lab_hint"]["score_delta"] == 3.2


def test_run_analysis_swing_mode_surfaces_collection_degradation(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"

    async def fake_collect(_portfolio):
        return {
            **_make_swing_input(),
            "collection_status": {
                "overall_status": "degraded",
                "blocks": {"bulk_spot": {"status": "missing", "source": None, "detail": "bulk spot unavailable"}},
                "issues": ["bulk spot unavailable; switched to single-quote fallback"],
                "source_labels": [],
            },
            "data_issues": ["bulk spot unavailable; switched to single-quote fallback"],
            "source_labels": [],
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
    monkeypatch.setattr(service, "_build_swing_lab_hint", lambda: None)
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    result = asyncio.run(service.run_analysis(mode="swing"))

    assert result["quality_status"] == "degraded"
    assert result["data_issues"] == ["bulk spot unavailable; switched to single-quote fallback"]
    assert result["collection_status"]["overall_status"] == "degraded"


def test_run_analysis_swing_mode_loads_close_history_for_scorecard(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"
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
        service,
        "_compute_swing_validation_report",
        lambda historical_records: {
            "scorecard": {"summary_text": "20日样本5，平均收益1.5%"},
            "backtest": {"summary_text": "回测收益3.2%，最大回撤-2.1%"},
            "performance_context": {"offensive": {"pullback_resume": {"allowed": True, "reason": "样本通过"}}},
            "summary_text": "20日样本5，平均收益1.5%；回测收益3.2%，最大回撤-2.1%",
        },
    )
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
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    result = asyncio.run(service.run_analysis(mode="swing"))

    assert calls == [90]
    assert result["swing_scorecard"]["summary_text"].startswith("20日样本")


def test_run_analysis_swing_mode_injects_strategy_preferences(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"
    service.config.setdefault("strategy", {}).setdefault("swing", {})["risk_profile"] = "aggressive"
    service.config.setdefault("strategy", {}).setdefault("swing", {})["candidate_limit"] = 3
    service.config["watchlist"] = [{"code": "512660", "name": "军工ETF", "strategy": "trend", "priority": "high"}]
    captured = {}

    async def fake_collect(_portfolio):
        return _make_swing_input()

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
        lambda ai_input, historical_records, analysis_date: captured.update(
            {
                "strategy_preferences": ai_input.get("strategy_preferences"),
                "historical_records": historical_records,
                "watchlist": ai_input.get("watchlist"),
                "watchlist_codes": ai_input.get("watchlist_codes"),
            }
        )
        or {
            "mode": "swing",
            "market_regime": "均衡",
            "market_conclusion": "当前偏均衡。",
            "position_plan": {"total_exposure": "75%-90%"},
            "portfolio_actions": {"增配": [], "持有": [], "减配": [], "回避": [], "观察": []},
            "actions": [],
            "technical_evidence": [],
        },
    )
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    asyncio.run(service.run_analysis(mode="swing"))

    assert captured["strategy_preferences"]["risk_profile"] == "aggressive"
    assert captured["strategy_preferences"]["candidate_limit"] == 3
    assert captured["watchlist"][0]["code"] == "512660"
    assert captured["watchlist_codes"] == {"512660"}


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
        lambda mode, universe_codes=None: {
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


def test_run_analysis_swing_dry_run_fetches_live_data_for_current_universe(monkeypatch, tmp_path):
    service = AnalysisService()
    service.data_path = tmp_path / "latest_context.json"
    service.data_path.write_text(
        json.dumps({"context_date": "2026-03-23", "stocks": [{"code": "600519", "name": "贵州茅台"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    service.config["portfolio"] = [
        {"code": "510300", "name": "沪深300ETF", "shares": 600, "strategy": "value"},
    ]
    service.config["watchlist"] = [
        {"code": "512660", "name": "军工ETF", "strategy": "trend", "priority": "high"},
    ]
    captured = {}

    async def fake_collect(universe):
        captured["collected_codes"] = [item["code"] for item in universe]
        return {
            "context_date": "2026-03-24",
            "market_breadth": "3200家上涨，1700家下跌",
            "indices": {"上证指数": {"change_pct": 0.8}},
            "macro_news": {"telegraph": ["情绪修复"]},
            "stocks": [
                {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "signal": "SAFE",
                    "confidence": "中",
                    "bias_pct": 0.02,
                    "pct_change": 0.8,
                    "current_price": 4.1,
                    "ma20": 4.0,
                    "tech_summary": "站上20日线",
                    "macd": {"trend": "BULLISH"},
                    "obv": {"trend": "INFLOW"},
                    "shares": 600,
                },
                {
                    "code": "512660",
                    "name": "军工ETF",
                    "signal": "OPPORTUNITY",
                    "confidence": "高",
                    "bias_pct": 0.05,
                    "pct_change": 1.7,
                    "current_price": 0.92,
                    "ma20": 0.88,
                    "tech_summary": "重新站上20日线",
                    "macd": {"trend": "GOLDEN_CROSS"},
                    "obv": {"trend": "INFLOW"},
                    "shares": 0,
                },
            ],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service, "collect_and_process_data", fake_collect)
    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: [])
    monkeypatch.setattr(service, "_compute_swing_validation_report", lambda historical_records: None)
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: captured.update(
            {"input_codes": [stock["code"] for stock in ai_input.get("stocks", [])]}
        )
        or {
            "mode": "swing",
            "market_regime": "均衡",
            "market_conclusion": "当前偏均衡。",
            "portfolio_actions": {"增配": [], "持有": [], "减配": [], "回避": [], "观察": []},
            "actions": [],
            "watchlist_candidates": [],
        },
    )
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    asyncio.run(service.run_analysis(mode="swing", dry_run=True))

    assert captured["collected_codes"] == ["510300", "512660"]
    assert captured["input_codes"] == ["510300", "512660"]


def test_run_analysis_swing_replay_prefers_cached_context_that_matches_current_universe(monkeypatch, tmp_path):
    service = AnalysisService()
    replay_file = tmp_path / "latest_context.json"
    replay_file.write_text(
        json.dumps(
            {
                "context_date": "2026-03-24",
                "market_breadth": "1800家上涨，3100家下跌",
                "indices": {"上证指数": {"change_pct": -0.8}},
                "macro_news": {"telegraph": ["旧缓存"]},
                "stocks": [{"code": "600519", "name": "贵州茅台"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service.data_path = replay_file
    service.config["portfolio"] = [
        {"code": "510300", "name": "沪深300ETF", "shares": 600, "strategy": "value"},
    ]
    service.config["watchlist"] = [
        {"code": "512660", "name": "军工ETF", "strategy": "trend", "priority": "high"},
    ]
    captured = {}

    def fake_latest_record(mode):
        if mode != "close":
            return None
        return {
            "context_date": "2026-03-23",
            "market_breadth": "3200家上涨，1700家下跌",
            "indices": {"上证指数": {"change_pct": 0.8}},
            "macro_news": {"telegraph": ["更匹配当前账户的缓存"]},
            "stocks": [
                {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "signal": "SAFE",
                    "confidence": "中",
                    "bias_pct": 0.02,
                    "pct_change": 0.8,
                    "current_price": 4.1,
                    "ma20": 4.0,
                    "tech_summary": "站上20日线",
                    "macd": {"trend": "BULLISH"},
                    "obv": {"trend": "INFLOW"},
                },
                {
                    "code": "512660",
                    "name": "军工ETF",
                    "signal": "OPPORTUNITY",
                    "confidence": "高",
                    "bias_pct": 0.05,
                    "pct_change": 1.7,
                    "current_price": 0.92,
                    "ma20": 0.88,
                    "tech_summary": "重新站上20日线",
                    "macd": {"trend": "GOLDEN_CROSS"},
                    "obv": {"trend": "INFLOW"},
                },
            ],
        }

    monkeypatch.setattr("src.service.analysis_service.should_run_market_report", lambda **kwargs: {"should_run": True})
    monkeypatch.setattr(service.db, "get_latest_record", fake_latest_record)
    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: [])
    monkeypatch.setattr(service, "_compute_swing_validation_report", lambda historical_records: None)
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_report",
        lambda ai_input, historical_records, analysis_date: captured.update(
            {
                "input_codes": [stock["code"] for stock in ai_input.get("stocks", [])],
                "shares_by_code": {stock["code"]: stock.get("shares", 0) for stock in ai_input.get("stocks", [])},
            }
        )
        or {
            "mode": "swing",
            "market_regime": "均衡",
            "market_conclusion": "当前偏均衡。",
            "portfolio_actions": {"增配": [], "持有": [], "减配": [], "回避": [], "观察": []},
            "actions": [],
            "watchlist_candidates": [],
        },
    )
    monkeypatch.setattr(service.db, "save_record", lambda **_kwargs: None)

    asyncio.run(service.run_analysis(mode="swing", replay=True, dry_run=True))

    assert captured["input_codes"] == ["510300", "512660"]
    assert captured["shares_by_code"]["510300"] == 600


def test_compute_swing_validation_report_summarizes_in_plain_language(monkeypatch):
    service = AnalysisService()
    monkeypatch.setattr(service, "_get_swing_report_records", lambda days=90: [])

    monkeypatch.setattr(
        service,
        "_build_synthetic_swing_records",
        lambda historical_records: [
            {"date": "2026-03-20", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
            {"date": "2026-03-21", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
            {"date": "2026-03-22", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
            {"date": "2026-03-23", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
        ],
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_scorecard",
        lambda synthetic_records, benchmark_map, windows: {
            "windows": [20],
            "stats": {
                "overall": {
                    20: {
                        "count": 12,
                        "avg_absolute_return": 0.031,
                        "avg_relative_return": 0.012,
                        "avg_max_drawdown": -0.052,
                    }
                }
            },
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.run_deterministic_backtest",
        lambda synthetic_records, initial_cash, lot_size: {
            "total_return": 0.094,
            "max_drawdown": -0.052,
            "trades": [{"side": "buy"}, {"side": "sell"}, {"side": "buy"}],
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.run_walkforward_validation",
        lambda synthetic_records, train_window, test_window, initial_cash: {
            "segment_count": 5,
            "segments": [],
            "avg_total_return": 0.012,
        },
    )

    report = service._compute_swing_validation_report(
        [{"date": "2026-03-23", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": []}}]
    )

    assert "可以继续进攻" in report["summary_text"]
    assert "20日样本12" in report["summary_text"]
    assert "回测收益9.4%" in report["summary_text"]


def test_compute_live_swing_validation_report_merges_swing_and_close_records():
    service = AnalysisService()

    swing_records = [
        {
            "date": "2026-03-20",
            "raw_data": {
                "stocks": [
                    {"code": "510300", "name": "沪深300ETF", "current_price": 4.00},
                    {"code": "159338", "name": "A500ETF", "current_price": 1.00},
                ]
            },
            "ai_result": {
                "actions": [
                    {"code": "510300", "name": "沪深300ETF", "action_label": "增配", "confidence": "高"}
                ]
            },
        }
    ]
    close_records = [
        {
            "date": "2026-03-20",
            "raw_data": {
                "stocks": [
                    {"code": "510300", "name": "沪深300ETF", "current_price": 4.00},
                    {"code": "159338", "name": "A500ETF", "current_price": 1.00},
                ]
            },
            "ai_result": {"actions": []},
        },
        {
            "date": "2026-03-21",
            "raw_data": {
                "stocks": [
                    {"code": "510300", "name": "沪深300ETF", "current_price": 4.20, "low": 4.10},
                    {"code": "159338", "name": "A500ETF", "current_price": 1.01, "low": 1.00},
                ]
            },
            "ai_result": {"actions": []},
        },
        {
            "date": "2026-03-22",
            "raw_data": {
                "stocks": [
                    {"code": "510300", "name": "沪深300ETF", "current_price": 4.36, "low": 4.18},
                    {"code": "159338", "name": "A500ETF", "current_price": 1.02, "low": 1.00},
                ]
            },
            "ai_result": {"actions": []},
        },
    ]

    report = service._compute_live_swing_validation_report(
        swing_records,
        close_records,
        benchmark_map={"510300": "159338"},
        windows=(1, 2),
    )

    assert report["scorecard"]["stats"]["overall"][1]["count"] == 1
    assert report["scorecard"]["stats"]["by_action"]["增配"][2]["count"] == 1
    assert report["scorecard"]["stats"]["overall"][2]["avg_relative_return"] > 0
    assert "真实建议跟踪" in report["summary_text"]
    assert "2日建议1笔" in report["summary_text"]


def test_build_validation_performance_context_prefers_live_add_signals():
    service = AnalysisService()

    live_scorecard = {
        "stats": {
            "by_action": {
                "增配": {
                    20: {"count": 6, "avg_relative_return": -0.01, "avg_max_drawdown": -0.03}
                }
            }
        }
    }
    synthetic_scorecard = {
        "stats": {
            "by_action": {
                "增配": {
                    20: {"count": 12, "avg_relative_return": 0.03, "avg_max_drawdown": -0.02}
                }
            }
        }
    }

    context = service._build_validation_performance_context(
        live_scorecard=live_scorecard,
        scorecard=synthetic_scorecard,
        backtest_report={"trade_count": 4, "total_return": 0.08, "max_drawdown": -0.05},
    )

    gate = context["offensive"]["pullback_resume"]
    assert gate["allowed"] is False
    assert "真实建议" in gate["reason"]


def test_compute_swing_validation_report_prefers_live_summary_when_samples_are_ready(monkeypatch):
    service = AnalysisService()

    monkeypatch.setattr(service, "_get_swing_report_records", lambda days=120: [{"date": "2026-03-20"}])
    monkeypatch.setattr(
        service,
        "_compute_live_swing_validation_report",
        lambda swing_records, close_records, benchmark_map=None, windows=(10, 20, 40): {
            "summary_text": "真实建议跟踪近90天已兑现20日建议8笔，平均跑赢基准1.6%，增配组平均收益4.2%。",
            "scorecard": {
                "windows": [20],
                "stats": {
                    "overall": {
                        20: {
                            "count": 8,
                            "avg_absolute_return": 0.042,
                            "avg_relative_return": 0.016,
                            "avg_max_drawdown": -0.035,
                        }
                    },
                    "by_action": {
                        "增配": {
                            20: {
                                "count": 6,
                                "avg_absolute_return": 0.051,
                                "avg_relative_return": 0.021,
                                "avg_max_drawdown": -0.031,
                            }
                        }
                    },
                },
            },
        },
    )
    monkeypatch.setattr(
        service,
        "_build_synthetic_swing_records",
        lambda historical_records: [
            {"date": "2026-03-20", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
            {"date": "2026-03-21", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
            {"date": "2026-03-22", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
            {"date": "2026-03-23", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": [{"code": "510300"}]}},
        ],
    )
    monkeypatch.setattr(
        "src.service.analysis_service.build_swing_scorecard",
        lambda synthetic_records, benchmark_map, windows: {
            "windows": [20],
            "stats": {
                "overall": {
                    20: {
                        "count": 12,
                        "avg_absolute_return": 0.031,
                        "avg_relative_return": 0.012,
                        "avg_max_drawdown": -0.052,
                    }
                },
                "by_action": {
                    "增配": {
                        20: {
                            "count": 12,
                            "avg_absolute_return": 0.031,
                            "avg_relative_return": 0.012,
                            "avg_max_drawdown": -0.052,
                        }
                    }
                },
            },
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.run_deterministic_backtest",
        lambda synthetic_records, initial_cash, lot_size: {
            "total_return": 0.094,
            "max_drawdown": -0.052,
            "trades": [{"side": "buy"}, {"side": "sell"}, {"side": "buy"}],
        },
    )
    monkeypatch.setattr(
        "src.service.analysis_service.run_walkforward_validation",
        lambda synthetic_records, train_window, test_window, initial_cash: {
            "segment_count": 5,
            "segments": [],
            "avg_total_return": 0.012,
        },
    )

    report = service._compute_swing_validation_report(
        [{"date": "2026-03-23", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": []}}]
    )

    assert report["live"]["summary_text"].startswith("真实建议跟踪")
    assert report["summary_text"].startswith("真实建议跟踪")
    assert report["performance_context"]["offensive"]["pullback_resume"]["allowed"] is True


def test_build_validation_snapshot_returns_compact_payload_without_heavy_evaluations(monkeypatch):
    service = AnalysisService()
    historical_records = [{"date": "2026-03-23", "raw_data": {"stocks": [{"code": "510300"}]}, "ai_result": {"actions": []}}]

    monkeypatch.setattr(service, "_get_swing_history_records", lambda days=90: historical_records)
    monkeypatch.setattr(
        service,
        "_compute_swing_validation_report",
        lambda records: {
            "live": {
                "summary_text": "真实建议跟踪近90天已兑现20日建议6笔，平均跑赢基准1.8%，增配组平均收益4.6%，平均回撤-3.1%；这套建议近期仍有效，可以继续进攻，但继续分批。",
                "scorecard": {
                    "windows": [20],
                    "stats": {
                        "overall": {
                            20: {
                                "count": 6,
                                "avg_absolute_return": 0.041,
                                "avg_relative_return": 0.018,
                                "avg_max_drawdown": -0.031,
                            }
                        }
                    },
                    "evaluations": [{"code": "510300", "window": 20}],
                },
            },
            "scorecard": {
                "windows": [20],
                "stats": {
                    "overall": {
                        20: {
                            "count": 12,
                            "avg_absolute_return": 0.033,
                            "avg_relative_return": 0.012,
                            "avg_max_drawdown": -0.052,
                        }
                    }
                },
                "evaluations": [{"code": "510300", "window": 20}],
            },
            "backtest": {
                "summary_text": "回测收益9.4%，最大回撤-5.2%，交易4笔",
                "total_return": 0.094,
                "max_drawdown": -0.052,
                "trade_count": 4,
            },
            "walkforward": {"segment_count": 5, "segments": [{"id": 1}], "avg_total_return": 0.012},
            "performance_context": {
                "offensive": {
                    "pullback_resume": {"allowed": True, "reason": "真实建议近期进攻统计仍有效，正式回测未见明显恶化"}
                }
            },
            "summary_text": "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。参考：20日样本12，平均收益3.3%，平均跑赢基准1.2%，平均回撤-5.2%；回测收益9.4%，最大回撤-5.2%，交易4笔；滚动验证5段，平均收益1.2%。",
        },
    )

    snapshot = service.build_validation_snapshot("swing")

    assert snapshot["mode"] == "swing"
    assert snapshot["compact"] == {
        "verdict": "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。",
        "live_sample_count": 6,
        "live_primary_window": 20,
        "synthetic_sample_count": 12,
        "synthetic_primary_window": 20,
        "backtest_trade_count": 4,
        "walkforward_segment_count": 5,
        "offensive_allowed": True,
        "offensive_reason": "真实建议近期进攻统计仍有效，正式回测未见明显恶化",
    }
    assert "scorecard" not in snapshot
    assert "live" not in snapshot
    assert "evaluations" not in json.dumps(snapshot, ensure_ascii=False)


def test_collect_and_process_data_closes_data_collector(monkeypatch):
    service = AnalysisService()
    lifecycle = {"closed": False}

    class FakeCollector:
        async def collect_all(self, portfolio):
            return {
                "market_breadth": "3200家上涨，1700家下跌",
                "north_funds": 0.0,
                "indices": {},
                "macro_news": {},
                "stocks": [],
            }

        def close(self):
            lifecycle["closed"] = True

    class FakeProcessor:
        def calculate_indicators(self, stock_raw):
            return stock_raw

        def generate_signals(self, processed_stocks):
            return processed_stocks

    monkeypatch.setattr("src.service.analysis_service.DataCollector", FakeCollector)
    monkeypatch.setattr("src.service.analysis_service.DataProcessor", FakeProcessor)

    asyncio.run(service.collect_and_process_data([]))

    assert lifecycle["closed"] is True
