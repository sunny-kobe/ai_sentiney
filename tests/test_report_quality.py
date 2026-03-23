from src.service.report_quality import evaluate_input_quality, evaluate_output_quality


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
