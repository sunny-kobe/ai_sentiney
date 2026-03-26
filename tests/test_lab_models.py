from src.lab.models import LabRequest, LabResult


def test_lab_request_normalizes_override_text():
    request = LabRequest(
        mode="swing",
        preset="aggressive_midterm",
        overrides=["confidence_min=高", "cluster_blocklist=small_cap,ai"],
    )

    assert request.override_map["confidence_min"] == "高"
    assert request.override_map["cluster_blocklist"] == "small_cap,ai"


def test_lab_result_serializes_baseline_candidate_and_diff():
    result = LabResult(
        mode="swing",
        preset="aggressive_midterm",
        baseline={"summary_text": "baseline"},
        candidate={"summary_text": "candidate"},
        diff={"total_return_delta": 0.024},
        winner="candidate",
        summary_text="candidate 更优",
    )

    payload = result.to_dict()

    assert payload["winner"] == "candidate"
    assert payload["diff"]["total_return_delta"] == 0.024


def test_lab_result_serializes_compact_view_by_default():
    result = LabResult(
        mode="swing",
        preset="aggressive_leader_focus",
        baseline={"backtest": {"summary_text": "baseline backtest"}, "compact": {"verdict": "baseline"}},
        candidate={
            "backtest": {"summary_text": "candidate backtest"},
            "compact": {"verdict": "candidate", "backtest_trade_count": 27},
            "applied_overrides": {"portfolio_overrides": {"watchlist_limit": "1"}},
        },
        diff={
            "total_return_delta": 0.024,
            "max_drawdown_delta": 0.011,
            "trade_count_delta": -18,
            "baseline_score": 1.5,
            "candidate_score": 3.2,
        },
        winner="candidate",
        summary_text="candidate 更优",
    )

    payload = result.to_dict()

    assert payload["summary"]["winner"] == "candidate"
    assert payload["summary"]["candidate_trade_count"] == 27
    assert "baseline" not in payload
    assert "candidate" not in payload


def test_lab_result_serializes_full_view_when_requested():
    result = LabResult(
        mode="swing",
        preset="aggressive_midterm",
        baseline={"summary_text": "baseline"},
        candidate={"summary_text": "candidate"},
        diff={"total_return_delta": 0.024},
        winner="candidate",
        summary_text="candidate 更优",
    )

    payload = result.to_dict(detail="full")

    assert payload["baseline"]["summary_text"] == "baseline"
    assert payload["candidate"]["summary_text"] == "candidate"
