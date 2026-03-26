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
