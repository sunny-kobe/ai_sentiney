from src.service.analysis_service import AnalysisService


def test_midday_scorecard_uses_previous_trading_day_analysis(monkeypatch):
    service = AnalysisService()

    monkeypatch.setattr(
        service.db,
        "get_previous_analysis",
        lambda mode, before_date: {
            "ai_result": {
                "actions": [
                    {
                        "code": "600519",
                        "name": "贵州茅台",
                        "signal": "SAFE",
                        "confidence": "高",
                    }
                ]
            }
        },
        raising=False,
    )
    monkeypatch.setattr(service.db, "get_records_range", lambda mode, days: [], raising=False)

    scorecard = service._compute_signal_scorecard(
        [{"code": "600519", "name": "贵州茅台", "pct_change": 1.2}],
        mode="midday",
        analysis_date="2026-03-19",
    )

    assert scorecard["comparison_mode"] == "overnight_followup"
    assert scorecard["comparison_label"] == "昨日午盘信号 -> 今日午盘验证"
    assert scorecard["yesterday_evaluation"][0]["yesterday_signal"] == "SAFE"


def test_close_scorecard_uses_same_day_midday_analysis(monkeypatch):
    service = AnalysisService()

    monkeypatch.setattr(
        service.db,
        "get_latest_analysis_for_date",
        lambda mode, target_date: {
            "ai_result": {
                "actions": [
                    {
                        "code": "601899",
                        "name": "紫金矿业",
                        "signal": "WARNING",
                        "confidence": "中",
                    }
                ]
            }
        },
        raising=False,
    )
    monkeypatch.setattr(service.db, "get_records_range", lambda mode, days: [], raising=False)

    scorecard = service._compute_signal_scorecard(
        [{"code": "601899", "name": "紫金矿业", "pct_change": -0.8}],
        mode="close",
        analysis_date="2026-03-19",
    )

    assert scorecard["comparison_mode"] == "intraday_followup"
    assert scorecard["comparison_label"] == "今日午盘信号 -> 今日收盘验证"
    assert scorecard["yesterday_evaluation"][0]["yesterday_signal"] == "WARNING"
