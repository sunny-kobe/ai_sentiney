from datetime import date, timedelta

from src.service.swing_strategy import (
    apply_cluster_risk_overlay,
    build_swing_report,
    classify_market_regime,
    resolve_benchmark_code,
    score_holding,
)


def _make_stock(
    code,
    name,
    *,
    signal="SAFE",
    confidence="中",
    bias_pct=0.01,
    pct_change=0.5,
    current_price=1.0,
    ma20=0.98,
    tech_summary="站上20日线，趋势偏强",
    macd_trend="BULLISH",
    obv_trend="INFLOW",
    kdj_signal="NEUTRAL",
    atr_volatility="NORMAL",
):
    return {
        "code": code,
        "name": name,
        "signal": signal,
        "confidence": confidence,
        "bias_pct": bias_pct,
        "pct_change": pct_change,
        "current_price": current_price,
        "ma20": ma20,
        "tech_summary": tech_summary,
        "macd": {"trend": macd_trend},
        "obv": {"trend": obv_trend},
        "kdj": {"signal": kdj_signal},
        "atr": {"volatility": atr_volatility},
    }


def _make_history(code, prices):
    records = []
    start = date(2026, 2, 2)
    for idx, price in enumerate(prices):
        records.append(
            {
                "date": (start + timedelta(days=idx)).isoformat(),
                "raw_data": {"stocks": [{"code": code, "name": code, "current_price": price}]},
                "ai_result": {"actions": []},
            }
        )
    return records


def _make_multi_history(price_map):
    records = []
    start = date(2026, 1, 5)
    total_days = len(next(iter(price_map.values())))
    for idx in range(total_days):
        stocks = []
        for code, prices in price_map.items():
            stocks.append({"code": code, "name": code, "current_price": prices[idx]})
        records.append(
            {
                "date": (start + timedelta(days=idx)).isoformat(),
                "raw_data": {"stocks": stocks},
                "ai_result": {"actions": []},
            }
        )
    return records


def test_resolve_benchmark_code_prefers_cluster_proxy_and_avoids_self():
    available_codes = {"510300", "510500", "159338", "159819"}

    assert resolve_benchmark_code(_make_stock("300308", "人工智能龙头"), available_codes) == "159819"
    assert resolve_benchmark_code(_make_stock("563300", "中证2000ETF"), available_codes) == "510500"
    assert resolve_benchmark_code(_make_stock("512480", "半导体ETF"), available_codes) == "159338"
    assert resolve_benchmark_code(_make_stock("159934", "黄金ETF"), {"159934", "510300"}) == "510300"


def test_classify_market_regime_covers_attack_balance_defense_and_retreat():
    attack = classify_market_regime(
        {
            "market_breadth": "3800家上涨，1100家下跌",
            "indices": {"上证指数": {"change_pct": 1.2}, "创业板指": {"change_pct": 1.8}},
            "macro_news": {"telegraph": ["成交回暖，核心资产企稳"]},
            "stocks": [_make_stock("510300", "沪深300ETF", signal="SAFE", bias_pct=0.04)],
        },
        _make_history("510300", [100, 101, 103, 105]),
    )
    balanced = classify_market_regime(
        {
            "market_breadth": "2500家上涨，2400家下跌",
            "indices": {"上证指数": {"change_pct": 0.2}, "创业板指": {"change_pct": -0.1}},
            "macro_news": {"telegraph": ["消息偏中性"]},
            "stocks": [_make_stock("510300", "沪深300ETF", signal="SAFE", bias_pct=0.01)],
        },
        _make_history("510300", [100, 100.5, 100.2, 100.4]),
    )
    defense = classify_market_regime(
        {
            "market_breadth": "1700家上涨，3200家下跌",
            "indices": {"上证指数": {"change_pct": -0.8}, "创业板指": {"change_pct": -1.2}},
            "macro_news": {"telegraph": ["市场承压，观望情绪抬头"]},
            "stocks": [_make_stock("563300", "中证2000ETF", signal="WARNING", bias_pct=-0.03, pct_change=-1.5)],
        },
        _make_history("510300", [100, 98.5, 97.5, 96]),
    )
    retreat = classify_market_regime(
        {
            "market_breadth": "800家上涨，4200家下跌",
            "indices": {"上证指数": {"change_pct": -2.2}, "创业板指": {"change_pct": -3.4}},
            "macro_news": {"telegraph": ["外围暴跌，关税升级，避险情绪升温"]},
            "stocks": [
                _make_stock("563300", "中证2000ETF", signal="DANGER", bias_pct=-0.06, pct_change=-4.0),
                _make_stock("159819", "人工智能ETF", signal="WARNING", bias_pct=-0.04, pct_change=-3.2),
                _make_stock("512480", "半导体ETF", signal="WARNING", bias_pct=-0.05, pct_change=-3.8),
            ],
        },
        _make_history("510300", [100, 96, 93, 90]),
    )

    assert attack["regime"] == "进攻"
    assert balanced["regime"] == "均衡"
    assert defense["regime"] == "防守"
    assert retreat["regime"] == "撤退"


def test_score_holding_maps_to_plain_language_actions():
    bullish = score_holding(
        _make_stock(
            "512480",
            "半导体ETF",
            signal="OPPORTUNITY",
            confidence="高",
            bias_pct=0.06,
            pct_change=2.4,
            current_price=1.08,
            ma20=1.0,
            tech_summary="MACD金叉，站上20日线，量价配合",
            macd_trend="GOLDEN_CROSS",
            obv_trend="INFLOW",
        ),
        {"regime": "进攻", "stressed_clusters": set()},
    )
    bearish = score_holding(
        _make_stock(
            "563300",
            "中证2000ETF",
            signal="DANGER",
            confidence="高",
            bias_pct=-0.06,
            pct_change=-4.2,
            current_price=0.44,
            ma20=0.50,
            tech_summary="跌破20日线，量能失守",
            macd_trend="DEATH_CROSS",
            obv_trend="OUTFLOW",
        ),
        {"regime": "防守", "stressed_clusters": {"small_cap"}},
    )

    assert bullish["action_label"] == "增配"
    assert "20日线" in bullish["reason"]
    assert "分批加" in bullish["plan"]
    assert "20日线" in bullish["risk_line"]

    assert bearish["action_label"] == "回避"
    assert "先收缩" in bearish["plan"]
    assert "20日线" in bearish["risk_line"]


def test_apply_cluster_risk_overlay_downgrades_small_cap_ai_and_semis():
    decisions = [
        {"code": "512480", "name": "半导体ETF", "cluster": "semiconductor", "action_label": "增配", "reason": "趋势向上"},
        {"code": "159819", "name": "人工智能ETF", "cluster": "ai", "action_label": "持有", "reason": "仍在观察"},
        {"code": "563300", "name": "中证2000ETF", "cluster": "small_cap", "action_label": "持有", "reason": "弹性较大"},
        {"code": "510300", "name": "沪深300ETF", "cluster": "broad_beta", "action_label": "持有", "reason": "核心底仓"},
    ]

    adjusted = apply_cluster_risk_overlay(decisions, stressed_clusters={"semiconductor", "ai", "small_cap"})

    assert adjusted[0]["action_label"] == "持有"
    assert adjusted[1]["action_label"] == "观察"
    assert adjusted[2]["action_label"] == "观察"
    assert adjusted[3]["action_label"] == "持有"
    assert "板块联动走弱" in adjusted[0]["reason"]


def test_build_swing_report_returns_plain_language_portfolio_guidance():
    ai_input = {
        "market_breadth": "3200家上涨，1700家下跌",
        "indices": {"上证指数": {"change_pct": 0.8}, "创业板指": {"change_pct": 1.1}},
        "macro_news": {"telegraph": ["成交温和回暖，风险偏好有所修复"]},
        "stocks": [
            _make_stock(
                "512480",
                "半导体ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.06,
                pct_change=2.2,
                current_price=1.08,
                ma20=1.0,
                tech_summary="MACD金叉，站上20日线，量价配合",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            ),
            _make_stock("510300", "沪深300ETF", signal="SAFE", confidence="中", bias_pct=0.02, pct_change=0.8),
            _make_stock(
                "563300",
                "中证2000ETF",
                signal="WARNING",
                confidence="中",
                bias_pct=-0.03,
                pct_change=-1.6,
                current_price=0.48,
                ma20=0.50,
                tech_summary="跌回20日线附近，短线承压",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
            ),
        ],
    }

    report = build_swing_report(
        ai_input,
        _make_history("510300", [100, 101, 103, 104]),
        analysis_date="2026-03-23",
    )

    assert report["market_regime"] == "进攻"
    assert report["market_conclusion"]
    assert set(report["portfolio_actions"]) == {"增配", "持有", "减配", "回避", "观察"}
    assert report["portfolio_actions"]["增配"][0]["name"] == "半导体ETF"

    lead = next(item for item in report["actions"] if item["code"] == "512480")
    assert lead["conclusion"] == "增配"
    assert lead["reason"]
    assert lead["plan"]
    assert lead["risk_line"]
    assert "MACD" not in lead["reason"]
    assert "MACD" in report["technical_evidence"][0]["tech_summary"]


def test_build_swing_report_uses_relative_strength_to_promote_and_demote_actions():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.5) for idx in range(41)],
            "LEAD": [100 + idx for idx in range(41)],
            "LAG": [100 + (idx * 0.1) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "2500家上涨，2400家下跌",
        "indices": {"上证指数": {"change_pct": 0.1}, "创业板指": {"change_pct": 0.0}},
        "macro_news": {"telegraph": ["消息偏中性"]},
        "stocks": [
            _make_stock(
                "LEAD",
                "强势龙头",
                signal="SAFE",
                confidence="中",
                bias_pct=0.0,
                pct_change=0.6,
                current_price=140,
                ma20=132,
                tech_summary="站上20日线",
                macd_trend="UNKNOWN",
                obv_trend="UNKNOWN",
            ),
            _make_stock(
                "LAG",
                "弱势跟随",
                signal="SAFE",
                confidence="中",
                bias_pct=-0.01,
                pct_change=-0.4,
                current_price=104,
                ma20=108,
                tech_summary="围绕20日线反复",
                macd_trend="UNKNOWN",
                obv_trend="UNKNOWN",
            ),
        ],
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-23")
    lead = next(item for item in report["actions"] if item["code"] == "LEAD")
    lag = next(item for item in report["actions"] if item["code"] == "LAG")

    assert lead["action_label"] == "持有"
    assert "强于对照基准" in lead["reason"]
    assert lag["action_label"] == "减配"
    assert "弱于对照基准" in lag["reason"]


def test_build_swing_report_retreat_overlay_uses_breakdown_and_bad_news_confirmation():
    history = _make_multi_history(
        {
            "510300": [100 - (idx * 0.2) for idx in range(41)],
            "159819": [100 - (idx * 1.0) for idx in range(41)],
            "512480": [100 - (idx * 1.2) for idx in range(41)],
            "560780": [100 - (idx * 1.1) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "900家上涨，4100家下跌",
        "indices": {"上证指数": {"change_pct": -2.4}, "创业板指": {"change_pct": -3.1}},
        "macro_news": {"telegraph": ["科技板块业绩下修，外围暴跌，避险情绪升温"]},
        "stocks": [
            _make_stock(
                "159819",
                "人工智能ETF",
                signal="SAFE",
                confidence="高",
                bias_pct=-0.08,
                pct_change=-4.3,
                current_price=0.82,
                ma20=0.95,
                tech_summary="跌破20日线，缩量反弹失败",
                macd_trend="DEATH_CROSS",
                obv_trend="OUTFLOW",
            ),
            _make_stock(
                "512480",
                "半导体ETF",
                signal="WARNING",
                confidence="高",
                bias_pct=-0.07,
                pct_change=-4.8,
                current_price=0.78,
                ma20=0.94,
                tech_summary="放量跌破20日线",
                macd_trend="DEATH_CROSS",
                obv_trend="OUTFLOW",
            ),
            _make_stock(
                "560780",
                "半导体设备ETF",
                signal="WARNING",
                confidence="中",
                bias_pct=-0.06,
                pct_change=-3.7,
                current_price=0.83,
                ma20=0.93,
                tech_summary="弱反抽后继续走低",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
            ),
        ],
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-23")
    ai_etf = next(item for item in report["actions"] if item["code"] == "159819")

    assert report["market_regime"] == "撤退"
    assert ai_etf["action_label"] == "回避"
    assert "利空确认" in ai_etf["reason"]
    assert "反抽不能站回" in ai_etf["risk_line"]
