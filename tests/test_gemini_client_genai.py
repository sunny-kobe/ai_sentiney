from types import SimpleNamespace

import pytest

from src.analyst.gemini_client import (
    CloseAnalysis,
    GeminiClient,
    MiddayAnalysis,
    MorningAnalysis,
)


class _FakeModels:
    def __init__(self, handler):
        self._handler = handler

    def generate_content(self, **kwargs):
        return self._handler(**kwargs)


class _FakeClient:
    def __init__(self, handler, captured, api_key=None):
        captured["api_key"] = api_key
        self.models = _FakeModels(handler)


def _get_config_value(config, key):
    if isinstance(config, dict):
        return config.get(key)
    return getattr(config, key)


def test_gemini_client_uses_google_genai_client_for_midday(monkeypatch):
    captured = {}

    def fake_handler(**kwargs):
        captured["request"] = kwargs
        parsed = MiddayAnalysis(
            market_sentiment="分歧",
            volume_analysis="缩量震荡",
            macro_summary="结构化输出",
            actions=[],
        )
        return SimpleNamespace(parsed=parsed, text='{"market_sentiment":"分歧","actions":[]}')

    monkeypatch.setattr(
        "src.analyst.gemini_client.ConfigLoader",
        lambda: SimpleNamespace(
            config={
                "api_keys": {"gemini_api_key": "test-key"},
                "ai": {"model_name": "gemini-3.1-pro-preview"},
                "prompts": {"midday_focus": "请分析"},
            }
        ),
    )
    monkeypatch.setattr("src.analyst.gemini_client.genai.configure", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.GenerativeModel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old SDK path must not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.Client",
        lambda api_key=None: _FakeClient(fake_handler, captured, api_key=api_key),
        raising=False,
    )

    client = GeminiClient()
    result = client.analyze(
        {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "structured_report": {
                "mode": "midday",
                "data_timestamp": "2026-03-23",
                "source_labels": ["rule_engine", "stock_news"],
                "market": {"market_breadth": "涨: 10 / 跌: 5", "indices_info": "上证指数 +0.5%"},
                "stocks": [
                    {
                        "code": "600519",
                        "name": "贵州茅台",
                        "signal": "SAFE",
                        "confidence": "高",
                        "operation": "持有观察",
                        "tech_evidence": "[日线_MACD_多头_无背驰_0]",
                        "news_evidence": ["公司回购进展"],
                        "source_labels": ["rule_engine", "stock_news"],
                        "data_timestamp": "2026-03-23",
                    }
                ],
            },
            "stocks": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "signal": "SAFE",
                    "confidence": "高",
                    "tech_summary": "[日线_MACD_多头_无背驰_0]",
                    "news": ["公司回购进展"],
                }
            ],
        }
    )

    assert captured["api_key"] == "test-key"
    assert captured["request"]["model"] == "gemini-3.1-pro-preview"
    assert _get_config_value(captured["request"]["config"], "response_mime_type") == "application/json"
    assert _get_config_value(captured["request"]["config"], "response_schema") is MiddayAnalysis
    assert result["market_sentiment"] == "分歧"


def test_gemini_client_falls_back_to_json_text_when_parsed_is_missing(monkeypatch):
    monkeypatch.setattr(
        "src.analyst.gemini_client.ConfigLoader",
        lambda: SimpleNamespace(
            config={
                "api_keys": {"gemini_api_key": "test-key"},
                "ai": {"model_name": "gemini-3.1-pro-preview"},
                "prompts": {"midday_focus": "请分析"},
            }
        ),
    )
    monkeypatch.setattr("src.analyst.gemini_client.genai.configure", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.GenerativeModel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old SDK path must not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.Client",
        lambda api_key=None: _FakeClient(
            lambda **_kwargs: SimpleNamespace(
                parsed=None,
                text='{"market_sentiment":"修复","volume_analysis":"放量突破","macro_summary":"回暖","actions":[]}',
            ),
            {},
            api_key=api_key,
        ),
        raising=False,
    )

    client = GeminiClient()
    result = client.analyze(
        {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [],
        }
    )

    assert result["market_sentiment"] == "修复"
    assert result["actions"] == []


def test_gemini_client_uses_close_and_morning_schemas(monkeypatch):
    captured = {"schemas": []}

    def fake_handler(**kwargs):
        config = kwargs["config"]
        captured["schemas"].append(_get_config_value(config, "response_schema"))
        text = '{"market_summary":"复盘","market_temperature":"存量博弈","actions":[]}'
        if _get_config_value(config, "response_schema") is MorningAnalysis:
            text = '{"global_overnight_summary":"隔夜平稳","commodity_summary":"商品偏强","us_treasury_impact":"中性","a_share_outlook":"平开","risk_events":[],"actions":[]}'
        return SimpleNamespace(parsed=None, text=text)

    monkeypatch.setattr(
        "src.analyst.gemini_client.ConfigLoader",
        lambda: SimpleNamespace(
            config={
                "api_keys": {"gemini_api_key": "test-key"},
                "ai": {"model_name": "gemini-3.1-pro-preview"},
                "prompts": {"midday_focus": "请分析"},
            }
        ),
    )
    monkeypatch.setattr("src.analyst.gemini_client.genai.configure", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.GenerativeModel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old SDK path must not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.Client",
        lambda api_key=None: _FakeClient(fake_handler, {}, api_key=api_key),
        raising=False,
    )

    client = GeminiClient()
    close_result = client.analyze_with_prompt(
        {
            "context_date": "2026-03-23",
            "market_breadth": "涨: 10 / 跌: 5",
            "indices": {"上证指数": {"change_pct": 0.5}},
            "macro_news": {"telegraph": ["流动性平稳"]},
            "stocks": [],
        },
        "close prompt",
    )
    morning_result = client.analyze_morning({"context_date": "2026-03-23", "stocks": []}, "morning prompt")

    assert captured["schemas"] == [CloseAnalysis, MorningAnalysis]
    assert close_result["market_summary"] == "复盘"
    assert morning_result["a_share_outlook"] == "平开"


def test_gemini_client_qa_stays_text_only(monkeypatch):
    captured = {}

    def fake_handler(**kwargs):
        captured["request"] = kwargs
        return SimpleNamespace(text="保持谨慎，优先观察MA20得失。")

    monkeypatch.setattr(
        "src.analyst.gemini_client.ConfigLoader",
        lambda: SimpleNamespace(
            config={
                "api_keys": {"gemini_api_key": "test-key"},
                "ai": {"model_name": "gemini-3.1-pro-preview"},
                "prompts": {"midday_focus": "请分析"},
            }
        ),
    )
    monkeypatch.setattr("src.analyst.gemini_client.genai.configure", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.GenerativeModel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("old SDK path must not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        "src.analyst.gemini_client.genai.Client",
        lambda api_key=None: _FakeClient(fake_handler, {}, api_key=api_key),
        raising=False,
    )

    client = GeminiClient()
    answer = client.ask_question(
        {"market_breadth": "涨: 10 / 跌: 5", "stocks": []},
        {"market_sentiment": "分歧"},
        "现在该减仓吗？",
        "qa prompt",
    )

    assert answer == "保持谨慎，优先观察MA20得失。"
    assert "config" not in captured["request"] or _get_config_value(captured["request"].get("config", {}), "response_schema") is None
