from src.lab.mutations import apply_candidate_mutations


def test_apply_candidate_mutations_degrades_holds_in_defense():
    actions = [
        {"code": "512480", "action_label": "持有", "market_regime": "防守", "cluster": "semiconductor", "confidence": "高"},
        {"code": "510300", "action_label": "持有", "market_regime": "进攻", "cluster": "broad_beta", "confidence": "高"},
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={"hold_in_defense": "degrade"},
        parameter_overrides={},
        portfolio_overrides={},
    )

    assert mutated[0]["action_label"] == "减配"
    assert mutated[1]["action_label"] == "持有"


def test_apply_candidate_mutations_filters_low_confidence_and_blocked_clusters():
    actions = [
        {"code": "512480", "action_label": "增配", "market_regime": "进攻", "cluster": "semiconductor", "confidence": "中"},
        {"code": "510300", "action_label": "增配", "market_regime": "进攻", "cluster": "broad_beta", "confidence": "高"},
        {"code": "159819", "action_label": "增配", "market_regime": "进攻", "cluster": "ai", "confidence": "高"},
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={"confidence_min": "高", "cluster_blocklist": "ai"},
        parameter_overrides={},
        portfolio_overrides={},
    )

    kept_codes = [item["code"] for item in mutated]
    assert kept_codes == ["510300"]


def test_apply_candidate_mutations_enforces_core_only_and_balanced_risk_profile():
    actions = [
        {"code": "510300", "action_label": "持有", "market_regime": "进攻", "cluster": "broad_beta", "confidence": "高", "target_weight": "40%-50%", "shares": 600},
        {"code": "512480", "action_label": "持有", "market_regime": "进攻", "cluster": "semiconductor", "confidence": "高", "target_weight": "30%-40%", "shares": 500},
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={},
        parameter_overrides={},
        portfolio_overrides={"core_only": "broad_beta", "risk_profile": "balanced"},
    )

    broad = next(item for item in mutated if item["code"] == "510300")
    semi = next(item for item in mutated if item["code"] == "512480")

    assert broad["target_weight"] == "32%-40%"
    assert semi["target_weight"] == "0%"


def test_apply_candidate_mutations_limits_watchlist_candidates():
    actions = [
        {"code": "510300", "action_label": "持有", "market_regime": "进攻", "cluster": "broad_beta", "confidence": "高", "target_weight": "35%-45%", "shares": 600},
        {"code": "512480", "action_label": "增配", "market_regime": "进攻", "cluster": "semiconductor", "confidence": "高", "target_weight": "12%-18%", "shares": 0},
        {"code": "159819", "action_label": "增配", "market_regime": "进攻", "cluster": "ai", "confidence": "中", "target_weight": "5%-8%", "shares": 0},
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={},
        parameter_overrides={},
        portfolio_overrides={"watchlist_limit": "1"},
    )

    semi = next(item for item in mutated if item["code"] == "512480")
    ai = next(item for item in mutated if item["code"] == "159819")

    assert semi["target_weight"] == "12%-18%"
    assert ai["target_weight"] == "0%"


def test_apply_candidate_mutations_uses_lookback_window_to_degrade_weak_trend():
    actions = [
        {
            "code": "159819",
            "action_label": "持有",
            "market_regime": "均衡",
            "cluster": "ai",
            "confidence": "高",
            "target_weight": "18%-24%",
            "shares": 300,
            "relative_return_20": 0.03,
            "relative_return_40": -0.09,
        }
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={},
        parameter_overrides={"lookback_window": "40"},
        portfolio_overrides={},
    )

    assert mutated[0]["action_label"] == "减配"
    assert mutated[0]["target_weight"] == "5%"


def test_apply_candidate_mutations_uses_drawdown_limit_to_block_new_exposure():
    actions = [
        {
            "code": "512480",
            "action_label": "增配",
            "market_regime": "进攻",
            "cluster": "semiconductor",
            "confidence": "高",
            "target_weight": "20%",
            "shares": 0,
            "drawdown_20": -0.18,
        }
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={},
        parameter_overrides={"drawdown_limit": "0.10"},
        portfolio_overrides={},
    )

    assert mutated[0]["action_label"] == "回避"
    assert mutated[0]["target_weight"] == "0%"
