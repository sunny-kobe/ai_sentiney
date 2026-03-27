from src.service.structured_report import build_structured_report


def test_build_structured_report_midday_contains_deterministic_operation_and_evidence():
    ai_input = {
        "context_date": "2026-03-23",
        "market_breadth": "涨: 3000 / 跌: 1800 (平: 200)",
        "indices": {"上证指数": {"change_pct": 0.8}},
        "macro_news": {"telegraph": ["算力链继续活跃", "北交所成交额放大"]},
        "stocks": [
            {
                "code": "600519",
                "name": "贵州茅台",
                "signal": "DANGER",
                "confidence": "高",
                "tech_summary": "[日线_MACD_空头_无背驰_0]",
                "current_price": 1500.0,
                "pct_change": -2.5,
                "news": ["渠道反馈偏弱", "机构下调预期"],
            }
        ],
    }

    report = build_structured_report(ai_input, mode="midday", quality_status="degraded")

    assert report["quality_status"] == "degraded"
    assert report["market"]["data_timestamp"] == "2026-03-23"
    assert report["stocks"][0]["operation"] == "减仓30%-50%"
    assert report["stocks"][0]["tech_evidence"] == "[日线_MACD_空头_无背驰_0]"
    assert report["stocks"][0]["news_evidence"] == ["渠道反馈偏弱", "机构下调预期"]
    assert "rule_engine" in report["stocks"][0]["source_labels"]
    assert "stock_news" in report["stocks"][0]["source_labels"]


def test_build_structured_report_close_uses_close_operation_mapping():
    ai_input = {
        "context_date": "2026-03-23",
        "market_breadth": "涨: 2600 / 跌: 2200",
        "indices": {"上证指数": {"change_pct": -0.3}},
        "macro_news": {"telegraph": ["银行股护盘"]},
        "stocks": [
            {
                "code": "601899",
                "name": "紫金矿业",
                "signal": "ACCUMULATE",
                "confidence": "中",
                "tech_summary": "[日线_OBV_资金流入_0]",
                "current_price": 18.5,
                "pct_change": 1.2,
                "news": [],
            }
        ],
    }

    report = build_structured_report(ai_input, mode="close", quality_status="normal")

    assert report["stocks"][0]["operation"] == "加仓10%-20%"
    assert report["stocks"][0]["data_timestamp"] == "2026-03-23"
    assert report["mode"] == "close"


def test_build_structured_report_preclose_uses_intraday_operation_mapping():
    ai_input = {
        "context_date": "2026-03-23",
        "market_breadth": "涨: 2600 / 跌: 2200",
        "indices": {"上证指数": {"change_pct": -0.3}},
        "macro_news": {"telegraph": ["尾盘银行股护盘"]},
        "stocks": [
            {
                "code": "601899",
                "name": "紫金矿业",
                "signal": "WARNING",
                "confidence": "中",
                "tech_summary": "[日线_OBV_资金流出_0]",
                "current_price": 18.5,
                "pct_change": -1.2,
                "news": [],
            }
        ],
    }

    report = build_structured_report(ai_input, mode="preclose", quality_status="normal")

    assert report["stocks"][0]["operation"] == "减仓10%-20%"
    assert report["stocks"][0]["data_timestamp"] == "2026-03-23"
    assert report["mode"] == "preclose"


def test_build_structured_report_includes_collection_metadata():
    ai_input = {
        "context_date": "2026-03-23",
        "market_breadth": "Unknown",
        "indices": {"上证指数": {"change_pct": -0.3}},
        "macro_news": {"telegraph": []},
        "data_issues": ["market breadth unavailable", "macro news unavailable"],
        "collection_status": {
            "overall_status": "degraded",
            "blocks": {
                "market_breadth": {"status": "missing", "source": None, "detail": "market breadth unavailable"},
                "macro_news": {"status": "missing", "source": None, "detail": "macro news unavailable"},
            },
            "issues": ["market breadth unavailable", "macro news unavailable"],
            "source_labels": ["indices"],
        },
        "source_labels": ["indices"],
        "stocks": [
            {
                "code": "601899",
                "name": "紫金矿业",
                "signal": "WARNING",
                "confidence": "中",
                "tech_summary": "[日线_OBV_资金流出_0]",
                "current_price": 18.5,
                "pct_change": -1.2,
                "news": [],
            }
        ],
    }

    report = build_structured_report(ai_input, mode="preclose", quality_status="degraded")

    assert report["data_issues"] == ["market breadth unavailable", "macro news unavailable"]
    assert report["collection_status"]["overall_status"] == "degraded"
    assert "indices" in report["source_labels"]
