import io
from contextlib import redirect_stdout

from src.main import _print_text_summary
from src.reporter.feishu_client import FeishuClient
from src.reporter.telegram_client import TelegramClient


def test_cli_summary_displays_quality_status_and_sources():
    result = {
        "quality_status": "degraded",
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
    assert "质量: degraded" in rendered
    assert "时间: 2026-03-23" in rendered
    assert "来源: rule_engine, stock_news" in rendered


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


def test_feishu_card_displays_degraded_banner_and_metadata():
    client = FeishuClient()
    card = client._construct_card(
        {
            "quality_status": "degraded",
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
    assert "质量: degraded" in joined
    assert "来源: rule_engine, stock_news" in joined
