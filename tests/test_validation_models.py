from src.validation.models import ValidationRequest, ValidationResult


def test_validation_request_normalizes_date_range_and_codes():
    request = ValidationRequest(
        mode="swing",
        date_from="2026-03-01",
        date_to="2026-03-25",
        codes=["510300", " 512660 ", "", None],
    )

    assert request.mode == "swing"
    assert request.date_from == "2026-03-01"
    assert request.date_to == "2026-03-25"
    assert request.codes == ["510300", "512660"]


def test_validation_request_rejects_inverted_date_range():
    try:
        ValidationRequest(
            mode="swing",
            date_from="2026-03-25",
            date_to="2026-03-01",
        )
    except ValueError as exc:
        assert "date range" in str(exc)
    else:
        raise AssertionError("expected ValidationRequest to reject inverted date ranges")


def test_validation_result_compact_snapshot_keeps_high_signal_fields_only():
    result = ValidationResult(
        mode="swing",
        as_of_date="2026-03-25",
        investor_summary="历史验证支持继续进攻，但只做分批加仓。",
        compact={"verdict": "supportive", "offensive_allowed": True},
        details={"backtest": {"trade_count": 4}},
    )

    payload = result.to_dict()

    assert payload["mode"] == "swing"
    assert payload["as_of_date"] == "2026-03-25"
    assert payload["compact"]["verdict"] == "supportive"
    assert payload["details"]["backtest"]["trade_count"] == 4
