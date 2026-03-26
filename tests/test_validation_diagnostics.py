from src.service.validation_service import ValidationService
from src.validation.diagnostics import DiagnosisRequest, DiagnosticGroup


def test_diagnosis_request_normalizes_group_by():
    request = DiagnosisRequest(group_by=" cluster ")

    assert request.group_by == "cluster"


def test_diagnostic_group_serializes_core_metrics():
    group = DiagnosticGroup(
        key="small_cap",
        sample_count=12,
        avg_absolute_return=-0.031,
        avg_relative_return=-0.012,
        avg_max_drawdown=-0.102,
    )

    payload = group.to_dict()
    assert payload["key"] == "small_cap"
    assert payload["sample_count"] == 12


class _FakeDB:
    def get_records_range(self, mode="close", days=7):
        return []


def test_validation_service_builds_diagnostic_rows_with_cluster_and_regime():
    service = ValidationService(_FakeDB(), config={})

    rows = service._build_diagnostic_rows(
        evaluations=[
            {
                "code": "512480",
                "name": "半导体ETF",
                "action_label": "持有",
                "confidence": "高",
                "windows": {
                    10: {
                        "entry_date": "2026-03-01",
                        "absolute_return": -0.01,
                        "relative_return": -0.005,
                        "max_drawdown": -0.03,
                    },
                    20: {
                        "entry_date": "2026-03-01",
                        "absolute_return": -0.04,
                        "relative_return": -0.02,
                        "max_drawdown": -0.09,
                    }
                },
            }
        ],
        metadata_by_observation={
            ("512480", "2026-03-01"): {"cluster": "semiconductor", "market_regime": "防守"}
        },
    )

    assert len(rows) == 2
    assert rows[0]["cluster"] == "semiconductor"
    assert rows[0]["market_regime"] == "防守"
    assert {row["window"] for row in rows} == {10, 20}


def test_group_diagnostics_aggregates_rows_by_cluster():
    service = ValidationService(_FakeDB(), config={})
    rows = [
        {"cluster": "small_cap", "absolute_return": -0.05, "relative_return": -0.02, "max_drawdown": -0.11},
        {"cluster": "small_cap", "absolute_return": -0.03, "relative_return": -0.01, "max_drawdown": -0.08},
        {"cluster": "broad_beta", "absolute_return": 0.01, "relative_return": 0.00, "max_drawdown": -0.03},
    ]

    report = service._aggregate_diagnostics(rows, group_by="cluster")

    assert report["groups"][0]["key"] == "small_cap"
    assert report["groups"][0]["sample_count"] == 2
    assert report["groups"][0]["avg_absolute_return"] == -0.04
    assert report["groups"][0]["avg_relative_return"] == -0.015
    assert report["groups"][0]["avg_max_drawdown"] == -0.095


def test_build_diagnosis_summary_calls_out_top_drag():
    service = ValidationService(_FakeDB(), config={})
    summary = service._build_diagnosis_summary(
        group_by="action",
        primary_window=20,
        groups=[
            {"key": "持有", "sample_count": 18, "avg_absolute_return": -0.046, "avg_relative_return": -0.019, "avg_max_drawdown": -0.112},
            {"key": "减配", "sample_count": 12, "avg_absolute_return": -0.005, "avg_relative_return": 0.001, "avg_max_drawdown": -0.032},
        ],
    )

    assert "持有" in summary
    assert "拖累" in summary
    assert "减配" in summary
    assert ("进攻" in summary) or ("防守" in summary)
