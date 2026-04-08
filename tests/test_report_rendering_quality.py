import io
from contextlib import redirect_stdout

from src.main import _print_text_summary
from src.reporter.feishu_client import FeishuClient
from src.reporter.telegram_client import TelegramClient


def test_cli_summary_displays_quality_status_and_sources():
    result = {
        "quality_status": "degraded",
        "quality_detail": "上下文日期仍是 2026-04-01，不是今天 2026-04-03。",
        "data_timestamp": "2026-03-23",
        "source_labels": ["rule_engine", "stock_news"],
        "market_sentiment": "结构化快报",
        "volume_analysis": "N/A",
        "indices_info": "上证指数 +0.5%",
        "macro_summary": "证据不足，降级输出",
        "actions": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "operation": "持有观察"}],
    }

    output = io.StringIO()
    with redirect_stdout(output):
        _print_text_summary(result, "midday")

    rendered = output.getvalue()
    assert "数据提示: 数据降级" in rendered
    assert "时间 2026-03-23" in rendered
    assert "来源 rule_engine, stock_news" in rendered
    assert "原因 上下文日期仍是 2026-04-01，不是今天 2026-04-03。" in rendered


def test_telegram_midday_text_includes_quality_metadata():
    client = TelegramClient()
    text = client._build_midday_text(
        {
            "quality_status": "degraded",
            "data_timestamp": "2026-03-23",
            "source_labels": ["rule_engine", "stock_news"],
            "market_sentiment": "结构化快报",
            "macro_summary": "证据不足，降级输出",
            "actions": [],
        }
    )

    assert "质量: degraded" in text
    assert "时间: 2026-03-23" in text
    assert "来源: rule_engine, stock_news" in text


def test_cli_summary_preclose_uses_execution_label():
    result = {
        "quality_status": "normal",
        "data_timestamp": "2026-03-23 14:48",
        "source_labels": ["rule_engine", "indices"],
        "market_sentiment": "分歧",
        "volume_analysis": "缩量",
        "indices_info": "上证指数 +0.2%",
        "macro_summary": "收盘前以执行为主",
        "actions": [{"code": "600519", "name": "贵州茅台", "signal": "SAFE", "operation": "持有观察"}],
    }

    output = io.StringIO()
    with redirect_stdout(output):
        _print_text_summary(result, "preclose")

    rendered = output.getvalue()
    assert "=== 收盘前执行 ===" in rendered
    assert "收盘前" in rendered


def test_telegram_preclose_text_includes_execution_metadata():
    client = TelegramClient()
    text = client._build_preclose_text(
        {
            "quality_status": "normal",
            "data_timestamp": "2026-03-23 14:48",
            "source_labels": ["rule_engine", "indices"],
            "market_sentiment": "分歧",
            "macro_summary": "收盘前以执行为主",
            "actions": [],
        }
    )

    assert "收盘前执行" in text
    assert "时间: 2026-03-23 14:48" in text
    assert "来源: rule_engine, indices" in text


def test_feishu_card_displays_degraded_banner_and_metadata():
    client = FeishuClient()
    card = client._construct_card(
        {
            "quality_status": "degraded",
            "quality_detail": "核心行情不完整：实时行情。",
            "data_timestamp": "2026-03-23",
            "source_labels": ["rule_engine", "stock_news"],
            "market_sentiment": "结构化快报",
            "macro_summary": "证据不足，降级输出",
            "actions": [],
        }
    )

    contents = [
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    ]
    joined = "\n".join(contents)
    assert "结构化快报" in joined
    assert "数据提示" in joined
    assert "rule_engine, stock_news" in joined
    assert "核心行情不完整：实时行情。" in joined


def test_feishu_card_hides_quality_metadata_when_report_is_normal():
    client = FeishuClient()
    card = client._construct_card(
        {
            "quality_status": "normal",
            "data_timestamp": "2026-03-23",
            "source_labels": ["rule_engine", "stock_news"],
            "market_sentiment": "结构化快报",
            "macro_summary": "证据充分，正常输出",
            "actions": [],
        }
    )

    contents = [
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    ]
    joined = "\n".join(contents)
    assert "结构化快报" in joined
    assert "质量:" not in joined
    assert "时间:" not in joined
    assert "来源:" not in joined


def test_cli_summary_formats_structured_tech_tags_for_humans():
    result = {
        "quality_status": "normal",
        "data_timestamp": "2026-03-23",
        "source_labels": ["rule_engine"],
        "market_sentiment": "分歧",
        "volume_analysis": "缩量",
        "indices_info": "上证指数 +0.2%",
        "macro_summary": "先看执行节奏",
        "actions": [
            {
                "code": "600519",
                "name": "贵州茅台",
                "signal": "SAFE",
                "operation": "持有观察",
                "tech_summary": "[日线_MACD_空头-超弱_无背驰_0] [日线_OBV_资金流出_0] [日线_RSI_中性_42.0_0]",
            }
        ],
    }

    output = io.StringIO()
    with redirect_stdout(output):
        _print_text_summary(result, "midday")

    rendered = output.getvalue()
    assert "[日线_MACD_" not in rendered
    assert "MACD空头-超弱，无背驰" in rendered
    assert "OBV资金流出" in rendered
    assert "RSI 42.0，中性" in rendered


def test_feishu_card_formats_structured_tech_tags_for_humans():
    client = FeishuClient()
    card = client._construct_card(
        {
            "quality_status": "normal",
            "data_timestamp": "2026-03-23",
            "source_labels": ["rule_engine"],
            "market_sentiment": "分歧",
            "indices_info": "上证指数 +0.2%",
            "macro_summary": "先看执行节奏",
            "actions": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "SAFE",
                    "operation": "持有观察",
                    "reason": "暂时没有破位",
                    "tech_summary": "[日线_MACD_空头-超弱_无背驰_0] [日线_OBV_资金流出_0] [日线_RSI_中性_42.0_0]",
                }
            ],
        }
    )

    contents = [
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    ]
    joined = "\n".join(contents)
    assert "[日线_MACD_" not in joined
    assert "MACD空头-超弱，无背驰" in joined
    assert "OBV资金流出" in joined
    assert "RSI 42.0，中性" in joined


def test_feishu_preclose_card_avoids_duplicate_tech_summary_when_reason_repeats_it():
    client = FeishuClient()
    card = client._construct_preclose_card(
        {
            "quality_status": "degraded",
            "quality_detail": "核心行情不完整：实时行情。",
            "data_timestamp": "2026-03-23",
            "source_labels": ["rule_engine"],
            "market_sentiment": "信息不全，先看技术结构",
            "indices_info": "上证指数 +0.2%",
            "macro_summary": "当前主要依据技术面和已采集快讯整理，先给保守执行摘要。",
            "actions": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "SAFE",
                    "operation": "持有观察",
                    "reason": "[日线_MACD_空头-超弱_无背驰_0]",
                    "tech_summary": "[日线_MACD_空头-超弱_无背驰_0]",
                }
            ],
        }
    )

    contents = [
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    ]
    joined = "\n".join(contents)
    assert "[日线_MACD_" not in joined
    assert joined.count("MACD空头-超弱，无背驰") == 1
