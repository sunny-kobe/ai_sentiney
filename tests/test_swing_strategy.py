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
    shares=0,
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
        "shares": shares,
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
            _make_stock(
                "512660",
                "军工ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.05,
                pct_change=1.9,
                current_price=0.92,
                ma20=0.88,
                tech_summary="重新站上20日线，量能放大",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            ),
        ],
        "held_codes": {"512480", "510300", "563300"},
        "watchlist_codes": {"512660"},
        "watchlist": [{"code": "512660", "name": "军工ETF", "strategy": "trend", "priority": "high"}],
        "strategy_preferences": {"risk_profile": "aggressive", "candidate_limit": 2},
    }

    report = build_swing_report(
        ai_input,
        _make_history("510300", [100, 101, 103, 104]),
        analysis_date="2026-03-23",
    )

    assert report["market_regime"] == "进攻"
    assert report["market_conclusion"]
    assert set(report["portfolio_actions"]) == {"增配", "持有", "减配", "回避"}
    assert all(item["code"] != "512660" for item in report["actions"])
    assert report["watchlist_candidates"][0]["code"] == "512660"
    assert report["watchlist_actions"]["进入试仓区"][0]["code"] == "512660"

    lead = next(item for item in report["actions"] if item["code"] == "512480")
    assert lead["conclusion"] == "持有"
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


def test_build_swing_report_uses_validation_feedback_to_block_weak_offensive_setup():
    ai_input = {
        "market_breadth": "2600家上涨，2100家下跌",
        "indices": {"上证指数": {"change_pct": 0.3}, "创业板指": {"change_pct": 0.5}},
        "macro_news": {"telegraph": ["情绪平稳，暂无系统性风险"]},
        "stocks": [
            _make_stock(
                "159611",
                "电力ETF",
                signal="ACCUMULATE",
                confidence="中",
                bias_pct=0.01,
                pct_change=0.6,
                current_price=1.01,
                ma20=1.0,
                tech_summary="回踩后重新站稳20日线",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            )
        ],
        "held_codes": {"159611"},
        "strategy_preferences": {"risk_profile": "aggressive"},
        "performance_context": {"offensive": {"pullback_resume": {"allowed": False, "reason": "样本不足"}}},
        "validation_report": {"summary_text": "样本不足，当前进攻 setup 不做加仓放大。"},
    }

    report = build_swing_report(
        ai_input,
        _make_history("159611", [1.0, 1.01, 1.02, 1.03]),
        analysis_date="2026-03-24",
    )

    action = report["actions"][0]
    assert action["action_label"] == "持有"
    assert report["validation_summary"] == "样本不足，当前进攻 setup 不做加仓放大。"


def test_build_swing_report_downgrades_offensive_action_when_cluster_evidence_is_weak():
    ai_input = {
        "market_breadth": "3200家上涨，1700家下跌",
        "indices": {"上证指数": {"change_pct": 0.8}, "创业板指": {"change_pct": 1.1}},
        "macro_news": {"telegraph": ["风险偏好修复，成长方向回暖"]},
        "stocks": [
            _make_stock(
                "159819",
                "人工智能ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.05,
                pct_change=2.1,
                current_price=1.08,
                ma20=1.0,
                tech_summary="重新站上20日线，量价配合",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            )
        ],
        "held_codes": {"159819"},
        "strategy_preferences": {"risk_profile": "aggressive"},
        "performance_context": {"offensive": {"pullback_resume": {"allowed": True, "reason": "全局验证仍允许进攻"}}},
        "validation_report": {
            "summary_text": "整体有效，但人工智能方向最近胜率不稳。",
            "decision_evidence": {
                "primary_window": 20,
                "offensive_allowed": True,
                "offensive_reason": "全局验证仍允许进攻",
                "action": {
                    "增配": {
                        "sample_count": 9,
                        "avg_absolute_return": 0.016,
                        "avg_relative_return": -0.011,
                        "avg_max_drawdown": -0.052,
                    }
                },
                "cluster": {
                    "ai": {
                        "sample_count": 7,
                        "avg_absolute_return": -0.018,
                        "avg_relative_return": -0.032,
                        "avg_max_drawdown": -0.094,
                    }
                },
                "regime": {
                    "进攻": {
                        "sample_count": 12,
                        "avg_absolute_return": 0.013,
                        "avg_relative_return": 0.008,
                        "avg_max_drawdown": -0.041,
                    }
                },
            },
        },
    }

    report = build_swing_report(
        ai_input,
        _make_multi_history(
            {
                "159819": [1.00 + (idx * 0.012) for idx in range(41)],
                "159338": [1.00 + (idx * 0.004) for idx in range(41)],
            }
        ),
        analysis_date="2026-03-24",
    )

    action = report["actions"][0]
    assert action["action_label"] == "持有"
    assert "人工智能方向的20日验证偏弱" in action["validation_note"]
    assert "历史验证偏弱" in action["reason"]


def test_build_swing_report_attaches_validation_evidence_summary_to_actions():
    ai_input = {
        "market_breadth": "2600家上涨，2400家下跌",
        "indices": {"上证指数": {"change_pct": 0.1}, "创业板指": {"change_pct": 0.0}},
        "macro_news": {"telegraph": ["消息偏中性"]},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="中",
                bias_pct=0.02,
                pct_change=0.4,
                current_price=1.16,
                ma20=1.14,
                tech_summary="维持强势",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            )
        ],
        "held_codes": {"510300"},
        "validation_report": {
            "summary_text": "大盘类方向验证仍稳定。",
            "decision_evidence": {
                "primary_window": 20,
                "offensive_allowed": True,
                "offensive_reason": "当前允许进攻",
                "action": {
                    "持有": {
                        "sample_count": 11,
                        "avg_absolute_return": 0.021,
                        "avg_relative_return": 0.009,
                        "avg_max_drawdown": -0.028,
                    }
                },
                "cluster": {
                    "broad_beta": {
                        "sample_count": 10,
                        "avg_absolute_return": 0.019,
                        "avg_relative_return": 0.007,
                        "avg_max_drawdown": -0.026,
                    }
                },
                "regime": {
                    "均衡": {
                        "sample_count": 8,
                        "avg_absolute_return": 0.013,
                        "avg_relative_return": 0.004,
                        "avg_max_drawdown": -0.021,
                    }
                },
            },
        },
    }

    report = build_swing_report(
        ai_input,
        _make_multi_history(
            {
                "510300": [1.00 + (idx * 0.004) for idx in range(41)],
                "159338": [1.00 + (idx * 0.0035) for idx in range(41)],
            }
        ),
        analysis_date="2026-03-24",
    )

    action = report["actions"][0]
    assert action["validation_note"] == "20日验证里，大盘核心方向样本10笔，平均跑赢基准0.7%，回撤约2.6%。"
    assert action["validation_evidence"]["cluster"]["sample_count"] == 10


def test_build_swing_report_caps_target_weight_when_validation_cluster_is_weak():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.5) for idx in range(41)],
            "159819": [100 + (idx * 0.9) for idx in range(41)],
            "159338": [100 + (idx * 0.3) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "3500家上涨，1400家下跌",
        "indices": {"上证指数": {"change_pct": 1.0}, "创业板指": {"change_pct": 1.5}},
        "macro_news": {"telegraph": ["风险偏好回升，成长方向活跃"]},
        "strategy_preferences": {"risk_profile": "aggressive"},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="高",
                bias_pct=0.03,
                pct_change=1.0,
                current_price=125.0,
                ma20=119.0,
                tech_summary="站上20日线",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            ),
            _make_stock(
                "159819",
                "人工智能ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.06,
                pct_change=2.6,
                current_price=136.0,
                ma20=128.0,
                tech_summary="强势突破",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            ),
        ],
        "validation_report": {
            "summary_text": "AI 方向验证走弱。",
            "decision_evidence": {
                "primary_window": 20,
                "cluster": {
                    "ai": {
                        "sample_count": 7,
                        "avg_absolute_return": -0.018,
                        "avg_relative_return": -0.032,
                        "avg_max_drawdown": -0.094,
                    }
                },
                "regime": {
                    "进攻": {
                        "sample_count": 12,
                        "avg_absolute_return": 0.015,
                        "avg_relative_return": 0.009,
                        "avg_max_drawdown": -0.041,
                    }
                },
                "action": {
                    "增配": {
                        "sample_count": 10,
                        "avg_absolute_return": 0.018,
                        "avg_relative_return": 0.006,
                        "avg_max_drawdown": -0.047,
                    }
                },
            },
        },
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-24")

    broad = next(item for item in report["actions"] if item["code"] == "510300")
    ai = next(item for item in report["actions"] if item["code"] == "159819")

    assert broad["target_weight"] == "45%-55%"
    assert ai["target_weight"] == "0%-10%"
    assert report["position_plan"]["satellite_target"] == "0%-10%"


def test_build_swing_report_uses_stricter_cap_for_severely_weak_validation_cluster():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.5) for idx in range(41)],
            "159819": [100 + (idx * 0.9) for idx in range(41)],
            "159338": [100 + (idx * 0.3) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "3500家上涨，1400家下跌",
        "indices": {"上证指数": {"change_pct": 1.0}, "创业板指": {"change_pct": 1.5}},
        "macro_news": {"telegraph": ["风险偏好回升，成长方向活跃"]},
        "strategy_preferences": {"risk_profile": "aggressive"},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="高",
                bias_pct=0.03,
                pct_change=1.0,
                current_price=125.0,
                ma20=119.0,
                tech_summary="站上20日线",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            ),
            _make_stock(
                "159819",
                "人工智能ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.06,
                pct_change=2.6,
                current_price=136.0,
                ma20=128.0,
                tech_summary="强势突破",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            ),
        ],
        "validation_report": {
            "summary_text": "AI 方向验证明显走坏。",
            "decision_evidence": {
                "primary_window": 20,
                "offensive_allowed": True,
                "cluster": {
                    "ai": {
                        "sample_count": 9,
                        "avg_absolute_return": -0.031,
                        "avg_relative_return": -0.051,
                        "avg_max_drawdown": -0.123,
                    }
                },
                "regime": {
                    "进攻": {
                        "sample_count": 12,
                        "avg_absolute_return": 0.015,
                        "avg_relative_return": 0.009,
                        "avg_max_drawdown": -0.041,
                    }
                },
                "action": {
                    "增配": {
                        "sample_count": 10,
                        "avg_absolute_return": 0.018,
                        "avg_relative_return": 0.006,
                        "avg_max_drawdown": -0.047,
                    }
                },
            },
        },
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-24")

    ai = next(item for item in report["actions"] if item["code"] == "159819")
    assert ai["target_weight"] == "0%-5%"
    assert report["position_plan"]["satellite_target"] == "0%-5%"


def test_build_swing_report_caps_add_action_when_global_offensive_gate_is_closed():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.5) for idx in range(41)],
            "512660": [100 + (idx * 0.9) for idx in range(41)],
            "159338": [100 + (idx * 0.3) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "3500家上涨，1400家下跌",
        "indices": {"上证指数": {"change_pct": 1.0}, "创业板指": {"change_pct": 1.5}},
        "macro_news": {"telegraph": ["风险偏好回升，成长方向活跃"]},
        "strategy_preferences": {"risk_profile": "aggressive"},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="高",
                bias_pct=0.03,
                pct_change=1.0,
                current_price=125.0,
                ma20=119.0,
                tech_summary="站上20日线",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            ),
            _make_stock(
                "512660",
                "军工ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.06,
                pct_change=2.6,
                current_price=136.0,
                ma20=128.0,
                tech_summary="强势突破",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            ),
        ],
        "validation_report": {
            "summary_text": "近期不支持主动进攻。",
            "decision_evidence": {
                "primary_window": 20,
                "offensive_allowed": False,
                "offensive_reason": "真实建议近期进攻统计失效",
                "cluster": {},
                "regime": {
                    "进攻": {
                        "sample_count": 12,
                        "avg_absolute_return": 0.015,
                        "avg_relative_return": 0.009,
                        "avg_max_drawdown": -0.041,
                    }
                },
                "action": {
                    "增配": {
                        "sample_count": 10,
                        "avg_absolute_return": 0.018,
                        "avg_relative_return": 0.006,
                        "avg_max_drawdown": -0.047,
                    }
                },
            },
        },
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-24")

    candidate = next(item for item in report["actions"] if item["code"] == "512660")
    assert candidate["target_weight"] == "0%-5%"


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


def test_build_swing_report_adds_core_satellite_cash_position_plan():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.6) for idx in range(41)],
            "512480": [100 + (idx * 0.9) for idx in range(41)],
            "563300": [100 - (idx * 0.5) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "3600家上涨，1200家下跌",
        "indices": {"上证指数": {"change_pct": 1.1}, "创业板指": {"change_pct": 1.6}},
        "macro_news": {"telegraph": ["风险偏好回升，成交改善"]},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="高",
                bias_pct=0.03,
                pct_change=1.0,
                current_price=124.0,
                ma20=118.0,
                tech_summary="站上20日线",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            ),
            _make_stock(
                "512480",
                "半导体ETF",
                signal="OPPORTUNITY",
                confidence="高",
                bias_pct=0.05,
                pct_change=2.8,
                current_price=136.0,
                ma20=128.0,
                tech_summary="强势突破",
                macd_trend="GOLDEN_CROSS",
                obv_trend="INFLOW",
            ),
            _make_stock(
                "563300",
                "中证2000ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.05,
                pct_change=-3.8,
                current_price=80.0,
                ma20=90.0,
                tech_summary="跌破20日线",
                macd_trend="DEATH_CROSS",
                obv_trend="OUTFLOW",
            ),
        ],
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-23")

    assert "position_plan" in report
    plan = report["position_plan"]
    assert plan["total_exposure"] == "80%-100%"
    assert plan["core_target"] == "50%-60%"
    assert plan["satellite_target"] == "30%-40%"
    assert "每周五收盘后" in plan["weekly_rebalance"]
    assert "下一交易日按优先级分批执行" in plan["daily_rule"]

    core_items = plan["buckets"]["核心仓"]
    satellite_items = plan["buckets"]["卫星仓"]
    assert core_items[0]["name"] == "沪深300ETF"
    assert core_items[0]["target_weight"] == "50%-60%"
    assert satellite_items[0]["name"] == "半导体ETF"
    assert satellite_items[0]["target_weight"] == "30%-40%"

    broad = next(item for item in report["actions"] if item["code"] == "510300")
    semi = next(item for item in report["actions"] if item["code"] == "512480")
    small = next(item for item in report["actions"] if item["code"] == "563300")
    assert broad["position_bucket"] == "核心仓"
    assert broad["target_weight"] == "50%-60%"
    assert semi["position_bucket"] == "卫星仓"
    assert semi["target_weight"] == "30%-40%"
    assert small["target_weight"] == "0%"


def test_build_swing_report_caps_watch_and_reduce_positions_to_small_weights():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.4) for idx in range(41)],
            "WATCH": [100 + (idx * 0.35) for idx in range(41)],
            "REDUCE": [100 + (idx * 0.2) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "2600家上涨，2300家下跌",
        "indices": {"上证指数": {"change_pct": 0.1}, "创业板指": {"change_pct": 0.0}},
        "macro_news": {"telegraph": ["消息偏中性"]},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="中",
                bias_pct=0.02,
                pct_change=0.4,
                current_price=116.0,
                ma20=114.0,
                tech_summary="维持强势",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
            ),
            _make_stock(
                "WATCH",
                "观察标的",
                signal="WATCH",
                confidence="中",
                bias_pct=0.0,
                pct_change=0.1,
                current_price=114.0,
                ma20=113.0,
                tech_summary="待确认",
                macd_trend="UNKNOWN",
                obv_trend="UNKNOWN",
            ),
            _make_stock(
                "REDUCE",
                "减配标的",
                signal="WARNING",
                confidence="中",
                bias_pct=-0.01,
                pct_change=-0.6,
                current_price=108.0,
                ma20=110.0,
                tech_summary="转弱",
                macd_trend="UNKNOWN",
                obv_trend="UNKNOWN",
            ),
        ],
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-23")
    watch = next(item for item in report["actions"] if item["code"] == "WATCH")
    reduce = next(item for item in report["actions"] if item["code"] == "REDUCE")

    assert watch["action_label"] == "持有"
    assert watch["target_weight"] == "0%-5%"
    assert reduce["action_label"] == "减配"
    assert reduce["target_weight"] == "0%"
    assert "每周五收盘后" in report["position_plan"]["weekly_rebalance"]
    assert "下一交易日按优先级分批执行" in report["position_plan"]["daily_rule"]


def test_build_swing_report_adds_current_position_snapshot_and_rebalance_moves():
    history = _make_multi_history(
        {
            "510300": [100 + (idx * 0.4) for idx in range(41)],
            "563300": [100 - (idx * 0.3) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "2500家上涨，2400家下跌",
        "indices": {"上证指数": {"change_pct": 0.1}, "创业板指": {"change_pct": 0.0}},
        "macro_news": {"telegraph": ["消息偏中性"]},
        "portfolio_state": {"cash_balance": 6000, "lot_size": 100},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="SAFE",
                confidence="高",
                bias_pct=0.02,
                pct_change=0.4,
                current_price=10.0,
                ma20=9.5,
                tech_summary="维持强势",
                macd_trend="BULLISH",
                obv_trend="INFLOW",
                shares=1000,
            ),
            _make_stock(
                "563300",
                "中证2000ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.05,
                pct_change=-3.0,
                current_price=5.0,
                ma20=5.6,
                tech_summary="跌破20日线",
                macd_trend="DEATH_CROSS",
                obv_trend="OUTFLOW",
                shares=1200,
            ),
        ],
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-24")

    plan = report["position_plan"]
    assert plan["current_total_exposure"] == "72.7%"
    assert plan["current_cash_pct"] == "27.3%"
    assert plan["account_total_assets"] == "22000.00"
    assert plan["cash_balance"] == "6000.00"

    broad = next(item for item in report["actions"] if item["code"] == "510300")
    small = next(item for item in report["actions"] if item["code"] == "563300")
    assert broad["current_shares"] == 1000
    assert broad["current_weight"] == "45.5%"
    assert broad["rebalance_action"] == "先按当前仓位拿住"
    assert small["current_shares"] == 1200
    assert small["current_weight"] == "27.3%"
    assert small["rebalance_action"] == "卖出1200份"


def test_build_swing_report_aggressive_profile_keeps_core_and_relative_leader_exposure():
    history = _make_multi_history(
        {
            "510300": [4.00 + (idx * 0.015) for idx in range(41)],
            "159338": [1.00 + (idx * 0.0045) for idx in range(41)],
            "159819": [1.12 + (idx * 0.011) for idx in range(41)],
            "588760": [0.70 + (idx * 0.0025) for idx in range(41)],
            "512480": [1.34 + (idx * 0.0055) for idx in range(41)],
            "563300": [1.24 + (idx * 0.006) for idx in range(41)],
        }
    )
    ai_input = {
        "market_breadth": "2400家上涨，2500家下跌",
        "indices": {"上证指数": {"change_pct": 0.2}, "创业板指": {"change_pct": -0.4}},
        "macro_news": {"telegraph": ["消息偏中性"]},
        "strategy_preferences": {"risk_profile": "aggressive"},
        "portfolio_state": {"cash_balance": 33091.73, "lot_size": 100},
        "stocks": [
            _make_stock(
                "510300",
                "沪深300ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.04,
                pct_change=0.6,
                current_price=4.40,
                ma20=4.60,
                tech_summary="跌回20日线下方，但日内有承接",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
                shares=600,
            ),
            _make_stock(
                "159338",
                "中证A500ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.03,
                pct_change=0.5,
                current_price=1.12,
                ma20=1.20,
                tech_summary="围绕20日线震荡",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
                shares=9700,
            ),
            _make_stock(
                "159819",
                "人工智能ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.05,
                pct_change=0.3,
                current_price=1.45,
                ma20=1.54,
                tech_summary="主线回撤后缩量企稳",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
                shares=6500,
            ),
            _make_stock(
                "588760",
                "科创人工智能ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.08,
                pct_change=-1.8,
                current_price=0.67,
                ma20=0.80,
                tech_summary="弱反抽后继续承压",
                macd_trend="DEATH_CROSS",
                obv_trend="OUTFLOW",
                shares=10500,
            ),
            _make_stock(
                "512480",
                "半导体ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.07,
                pct_change=0.6,
                current_price=1.43,
                ma20=1.57,
                tech_summary="破位后反弹力度一般",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
                shares=4200,
            ),
            _make_stock(
                "563300",
                "中证2000ETF",
                signal="DANGER",
                confidence="高",
                bias_pct=-0.06,
                pct_change=1.0,
                current_price=1.38,
                ma20=1.50,
                tech_summary="下探后有回拉",
                macd_trend="BEARISH",
                obv_trend="OUTFLOW",
                shares=5200,
            ),
        ],
    }

    report = build_swing_report(ai_input, history, analysis_date="2026-03-24")

    assert report["market_regime"] == "防守"
    assert report["position_plan"]["cash_target"] != "100%"
    assert report["position_plan"]["total_exposure"] != "0%"
    assert report["position_plan"]["regime_total_exposure"] == "45%-65%"

    broad = next(item for item in report["actions"] if item["code"] == "510300")
    ai_leader = next(item for item in report["actions"] if item["code"] == "159819")
    ai_laggard = next(item for item in report["actions"] if item["code"] == "588760")

    assert broad["action_label"] == "持有"
    assert broad["target_weight"] != "0%"
    assert ai_leader["action_label"] == "持有"
    assert ai_leader["target_weight"] != "0%"
    assert "强于对照基准" in ai_leader["reason"]
    assert ai_laggard["action_label"] == "回避"
    assert ai_laggard["target_weight"] == "0%"
    assert "加" in broad["rebalance_action"] or "加" in ai_leader["rebalance_action"] or "先按当前仓位拿住" in broad["rebalance_action"] or "先按当前仓位拿住" in ai_leader["rebalance_action"]


def test_build_swing_report_keeps_drawdown_metadata_for_lab_parameters():
    ai_input = {
        "market_breadth": "2600家上涨，2200家下跌",
        "indices": {"上证指数": {"change_pct": 0.2}, "创业板指": {"change_pct": -0.1}},
        "macro_news": {"telegraph": ["消息偏中性"]},
        "stocks": [
            _make_stock("510300", "沪深300ETF", signal="SAFE", confidence="高", shares=1000, current_price=1.18, ma20=1.20),
            _make_stock("159338", "中证A500ETF", signal="SAFE", confidence="中", shares=0, current_price=0.98, ma20=1.00),
        ],
    }
    history = _make_multi_history(
        {
            "510300": [1.20, 1.19, 1.18, 1.17, 1.16, 1.15, 1.14, 1.13, 1.12, 1.11, 1.10, 1.09, 1.08, 1.09, 1.10, 1.12, 1.11, 1.10, 1.09, 1.08, 1.07, 1.08, 1.09, 1.10, 1.08, 1.06, 1.04, 1.03, 1.02, 1.01, 1.00, 1.02, 1.03, 1.04, 1.05, 1.06, 1.08, 1.10, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18],
            "159338": [1.00, 1.00, 1.01, 1.01, 1.02, 1.02, 1.03, 1.03, 1.04, 1.04, 1.05, 1.05, 1.06, 1.06, 1.07, 1.07, 1.08, 1.08, 1.09, 1.09, 1.10, 1.10, 1.09, 1.09, 1.08, 1.08, 1.07, 1.07, 1.06, 1.06, 1.05, 1.05, 1.04, 1.04, 1.03, 1.03, 1.02, 1.02, 1.01, 1.01, 1.00, 1.00, 0.99, 0.99, 0.98],
        }
    )

    report = build_swing_report(ai_input, history, analysis_date="2026-03-24")
    action = next(item for item in report["actions"] if item["code"] == "510300")

    assert action["relative_return_40"] is not None
    assert action["drawdown_20"] is not None
