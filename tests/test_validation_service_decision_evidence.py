from src.service.validation_service import ValidationService


def test_build_validation_decision_evidence_surfaces_action_cluster_and_regime_groups():
    service = ValidationService(db=None, config={})
    scorecard = {
        "windows": [20],
        "stats": {
            "by_action": {
                "增配": {
                    20: {
                        "count": 6,
                        "avg_absolute_return": 0.041,
                        "avg_relative_return": -0.021,
                        "avg_max_drawdown": -0.083,
                    }
                },
                "持有": {
                    20: {
                        "count": 8,
                        "avg_absolute_return": 0.018,
                        "avg_relative_return": 0.006,
                        "avg_max_drawdown": -0.031,
                    }
                },
            }
        },
        "evaluations": [
            {
                "code": "159819",
                "name": "人工智能ETF",
                "action_label": "增配",
                "confidence": "高",
                "windows": {
                    20: {
                        "entry_date": "2026-03-20",
                        "absolute_return": -0.032,
                        "relative_return": -0.028,
                        "max_drawdown": -0.091,
                    }
                },
            },
            {
                "code": "510300",
                "name": "沪深300ETF",
                "action_label": "持有",
                "confidence": "中",
                "windows": {
                    20: {
                        "entry_date": "2026-03-20",
                        "absolute_return": 0.021,
                        "relative_return": 0.012,
                        "max_drawdown": -0.022,
                    }
                },
            },
        ],
    }
    synthetic_records = [
        {
            "date": "2026-03-20",
            "raw_data": {
                "stocks": [
                    {"code": "159819", "name": "人工智能ETF"},
                    {"code": "510300", "name": "沪深300ETF"},
                ]
            },
            "ai_result": {
                "market_regime": "进攻",
                "actions": [
                    {"code": "159819", "name": "人工智能ETF", "action_label": "增配", "cluster": "ai"},
                    {"code": "510300", "name": "沪深300ETF", "action_label": "持有", "cluster": "broad_beta"},
                ],
            },
        }
    ]
    performance_context = {"offensive": {"pullback_resume": {"allowed": False, "reason": "真实建议进攻组偏弱"}}}

    evidence = service._build_decision_evidence_snapshot(
        scorecard=scorecard,
        synthetic_records=synthetic_records,
        performance_context=performance_context,
    )

    assert evidence["primary_window"] == 20
    assert evidence["offensive_allowed"] is False
    assert evidence["offensive_reason"] == "真实建议进攻组偏弱"

    add_action = evidence["action"]["增配"]
    assert add_action["sample_count"] == 6
    assert add_action["avg_relative_return"] == -0.021
    assert add_action["avg_max_drawdown"] == -0.083

    ai_cluster = evidence["cluster"]["ai"]
    assert ai_cluster["sample_count"] == 1
    assert ai_cluster["avg_relative_return"] == -0.028

    attack_regime = evidence["regime"]["进攻"]
    assert attack_regime["sample_count"] == 2
    assert attack_regime["avg_absolute_return"] == -0.0055
