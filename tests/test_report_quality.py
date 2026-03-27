from src.service.report_quality import build_swing_quality_guard, evaluate_input_quality, evaluate_output_quality


def test_input_quality_blocked_when_midday_stocks_missing():
    result = evaluate_input_quality(
        {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "stocks": [],
        },
        mode="midday",
        now="2026-03-23",
    )

    assert result["status"] == "blocked"
    assert "missing_stocks" in result["issues"]


def test_input_quality_blocked_when_preclose_stocks_missing():
    result = evaluate_input_quality(
        {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "stocks": [],
        },
        mode="preclose",
        now="2026-03-23",
    )

    assert result["status"] == "blocked"
    assert "missing_stocks" in result["issues"]


def test_input_quality_degraded_when_context_is_stale_and_evidence_is_thin():
    result = evaluate_input_quality(
        {
            "context_date": "2026-03-21",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": []},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": []}],
        },
        mode="midday",
        now="2026-03-23",
    )

    assert result["status"] == "degraded"
    assert "stale_context" in result["issues"]
    assert "missing_evidence" in result["issues"]


def test_input_quality_normal_when_required_fields_and_evidence_exist():
    result = evaluate_input_quality(
        {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["央行表态稳定流动性"]},
            "stocks": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "news": ["公司回购进展"]}],
        },
        mode="midday",
        now="2026-03-23",
    )

    assert result["status"] == "normal"
    assert result["issues"] == []


def test_output_quality_degraded_when_ai_actions_do_not_cover_structured_stocks():
    structured_report = {
        "stocks": [
            {"code": "600519", "signal": "SAFE"},
            {"code": "601899", "signal": "WATCH"},
        ]
    }
    analysis_result = {
        "actions": [
            {"code": "600519", "name": "贵州茅台", "reason": "量价正常"}
        ]
    }

    result = evaluate_output_quality(analysis_result, structured_report, mode="midday")

    assert result["status"] == "degraded"
    assert "incomplete_action_coverage" in result["issues"]


def test_build_swing_quality_guard_is_cautious_when_only_supporting_blocks_are_missing():
    result = build_swing_quality_guard(
        {
            "collection_status": {
                "overall_status": "degraded",
                "blocks": {
                    "stock_quotes": {"status": "fresh"},
                    "stock_history": {"status": "fresh"},
                    "market_breadth": {"status": "missing"},
                    "macro_news": {"status": "missing"},
                },
            }
        }
    )

    assert result["trust_level"] == "medium"
    assert result["execution_readiness"] == "谨慎执行"
    assert result["allow_offensive"] is True
    assert result["allow_new_entries"] is False
    assert "核心行情完整" in result["summary"]
    assert "市场广度" in result["summary"]
    assert "宏观消息" in result["summary"]


def test_build_swing_quality_guard_is_reference_only_when_core_blocks_are_missing():
    result = build_swing_quality_guard(
        {
            "collection_status": {
                "overall_status": "degraded",
                "blocks": {
                    "stock_quotes": {"status": "missing"},
                    "stock_history": {"status": "degraded"},
                    "market_breadth": {"status": "fresh"},
                },
            }
        }
    )

    assert result["trust_level"] == "low"
    assert result["execution_readiness"] == "仅供参考"
    assert result["allow_offensive"] is False
    assert result["allow_new_entries"] is False
    assert "实时行情" in result["summary"]
    assert "历史走势" in result["summary"]
