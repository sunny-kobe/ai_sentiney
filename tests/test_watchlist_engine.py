from src.service.watchlist_engine import build_watchlist_candidates


def test_build_watchlist_candidates_limits_active_ideas_and_keeps_weak_names_observed():
    candidates = build_watchlist_candidates(
        [
            {
                "code": "512660",
                "name": "军工ETF",
                "signal": "OPPORTUNITY",
                "confidence": "高",
                "final_action": "增配",
                "setup_type": "trend_follow",
                "evidence_text": "站上20日线并放量突破",
                "invalid_condition": "跌回20日线下方",
                "rebalance_instruction": "下一交易日分批加仓10%-20%",
            },
            {
                "code": "159611",
                "name": "电力ETF",
                "signal": "ACCUMULATE",
                "confidence": "中",
                "final_action": "增配",
                "setup_type": "pullback_resume",
                "evidence_text": "回踩后承接稳定",
                "invalid_condition": "放量跌破平台",
                "rebalance_instruction": "下一交易日分批加仓10%-20%",
            },
            {
                "code": "512200",
                "name": "地产ETF",
                "signal": "DANGER",
                "confidence": "高",
                "final_action": "回避",
                "setup_type": "breakdown",
                "evidence_text": "跌破20日线且相对收益转弱",
                "invalid_condition": "重新站回20日线",
                "rebalance_instruction": "保持观察",
            },
        ],
        held_codes={"510300"},
        watchlist_codes={"512660", "159611", "512200"},
        strategy_preferences={"candidate_limit": 1, "max_watchlist_adds_per_day": 1},
        market_regime="进攻",
    )

    assert [item["code"] for item in candidates["active_candidates"]] == ["512660"]
    assert candidates["action_buckets"]["进入试仓区"][0]["code"] == "512660"
    assert candidates["action_buckets"]["继续观察"][0]["code"] == "159611"
    assert candidates["all_candidates"][-1]["code"] == "512200"
    assert candidates["all_candidates"][-1]["action_label"] == "继续观察"


def test_build_watchlist_candidates_blocks_trial_when_validation_evidence_is_weak():
    candidates = build_watchlist_candidates(
        [
            {
                "code": "159819",
                "name": "人工智能ETF",
                "signal": "OPPORTUNITY",
                "confidence": "高",
                "final_action": "增配",
                "cluster": "ai",
                "setup_type": "trend_follow",
                "evidence_text": "重新站上20日线并放量",
                "invalid_condition": "跌回20日线下方",
                "rebalance_instruction": "下一交易日分批加仓10%-20%",
            },
            {
                "code": "512660",
                "name": "军工ETF",
                "signal": "OPPORTUNITY",
                "confidence": "高",
                "final_action": "增配",
                "cluster": "sector_etf",
                "setup_type": "trend_follow",
                "evidence_text": "站上20日线并放量突破",
                "invalid_condition": "跌回20日线下方",
                "rebalance_instruction": "下一交易日分批加仓10%-20%",
            },
        ],
        held_codes=set(),
        watchlist_codes={"159819", "512660"},
        strategy_preferences={"candidate_limit": 2, "max_watchlist_adds_per_day": 2},
        market_regime="进攻",
        decision_evidence={
            "primary_window": 20,
            "cluster": {
                "ai": {
                    "sample_count": 7,
                    "avg_absolute_return": -0.018,
                    "avg_relative_return": -0.032,
                    "avg_max_drawdown": -0.094,
                }
            },
        },
    )

    ai_candidate = next(item for item in candidates["all_candidates"] if item["code"] == "159819")
    defense_candidate = next(item for item in candidates["all_candidates"] if item["code"] == "512660")

    assert ai_candidate["action_label"] == "继续观察"
    assert "20日验证偏弱" in ai_candidate["validation_note"]
    assert "验证暂时不支持直接试仓" in ai_candidate["plan"]
    assert defense_candidate["action_label"] == "进入试仓区"


def test_build_watchlist_candidates_blocks_trial_when_global_offensive_gate_is_closed():
    candidates = build_watchlist_candidates(
        [
            {
                "code": "512660",
                "name": "军工ETF",
                "signal": "OPPORTUNITY",
                "confidence": "高",
                "final_action": "增配",
                "cluster": "sector_etf",
                "setup_type": "trend_follow",
                "evidence_text": "站上20日线并放量突破",
                "invalid_condition": "跌回20日线下方",
                "rebalance_instruction": "下一交易日分批加仓10%-20%",
            },
        ],
        held_codes=set(),
        watchlist_codes={"512660"},
        strategy_preferences={"candidate_limit": 2, "max_watchlist_adds_per_day": 2},
        market_regime="进攻",
        decision_evidence={
            "primary_window": 20,
            "offensive_allowed": False,
            "offensive_reason": "真实建议近期进攻统计失效",
            "cluster": {},
        },
    )

    candidate = candidates["all_candidates"][0]
    assert candidate["action_label"] == "继续观察"
    assert candidate["validation_note"] == "当前全局进攻权限关闭：真实建议近期进攻统计失效。"
    assert "进攻权限恢复" in candidate["plan"]
