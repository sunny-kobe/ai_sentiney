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
