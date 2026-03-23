import io
from contextlib import redirect_stdout

from src.main import _print_text_summary
from src.reporter.feishu_client import FeishuClient
from src.reporter.telegram_client import TelegramClient


def _make_swing_result():
    return {
        "market_regime": "防守",
        "market_conclusion": "当前偏防守，先守住已有成果，弱势方向以收缩仓位为主。",
        "portfolio_actions": {
            "增配": [],
            "持有": [{"code": "510300", "name": "沪深300ETF"}],
            "减配": [{"code": "563300", "name": "中证2000ETF"}],
            "回避": [],
            "观察": [{"code": "512480", "name": "半导体ETF"}],
        },
        "actions": [
            {
                "code": "510300",
                "name": "沪深300ETF",
                "conclusion": "持有",
                "action_label": "持有",
                "reason": "还站在20日线 4.01 上方，主趋势还在，承接还在配合。",
                "plan": "先把现有仓位拿住，等下一次确认转强再决定要不要加。",
                "risk_line": "收盘跌回20日线 4.01 下方，就先缩仓。",
                "technical_evidence": "MACD多头，站上20日线",
            },
            {
                "code": "563300",
                "name": "中证2000ETF",
                "conclusion": "减配",
                "action_label": "减配",
                "reason": "已经落到20日线 0.50 下方，已经开始转弱，承接偏弱。",
                "plan": "先收缩一部分仓位，把组合波动降下来。",
                "risk_line": "不能重新站上20日线 0.50 之前，先别加仓。",
                "technical_evidence": "MACD死叉，跌破20日线",
            },
        ],
        "technical_evidence": [
            {"code": "510300", "name": "沪深300ETF", "tech_summary": "MACD多头，站上20日线"},
            {"code": "563300", "name": "中证2000ETF", "tech_summary": "MACD死叉，跌破20日线"},
        ],
        "swing_scorecard": {"summary_text": "10日样本8，平均收益2.4%，平均回撤-1.8%"},
        "data_timestamp": "2026-03-23",
        "source_labels": ["rule_engine", "history"],
    }


def test_cli_swing_summary_uses_plain_language_sections():
    output = io.StringIO()
    with redirect_stdout(output):
        _print_text_summary(_make_swing_result(), "swing")

    rendered = output.getvalue()
    assert "市场结论" in rendered
    assert "组合动作" in rendered
    assert "持仓清单" in rendered
    assert "技术证据" in rendered
    assert "[510300] 沪深300ETF | 结论:持有" in rendered
    assert "MACD" not in rendered.split("持仓清单:")[1].split("技术证据:")[0]


def test_telegram_swing_text_shows_action_buckets_and_risk_lines():
    client = TelegramClient()
    text = client._build_swing_text(_make_swing_result())

    assert "市场结论" in text
    assert "组合动作" in text
    assert "减配: 中证2000ETF" in text
    assert "风险线" in text


def test_feishu_swing_card_shows_plain_language_sections():
    client = FeishuClient()
    card = client._construct_swing_card(_make_swing_result())

    contents = [
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    ]
    joined = "\n".join(contents)
    assert "市场结论" in joined
    assert "组合动作" in joined
    assert "持仓清单" in joined
    assert "风险线" in joined
