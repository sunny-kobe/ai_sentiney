from src.validation.history import slice_records


def _record(record_date: str, codes: list[str]):
    return {
        "date": record_date,
        "raw_data": {
            "stocks": [
                {
                    "code": code,
                    "name": code,
                    "close": 1.0,
                }
                for code in codes
            ]
        },
        "ai_result": {"actions": [{"code": code, "action_label": "持有"} for code in codes]},
    }


def test_slice_records_filters_date_range_and_codes():
    sample_records = [
        _record("2026-03-01", ["510300", "512660"]),
        _record("2026-03-02", ["510300", "512660"]),
        _record("2026-03-03", ["510300", "512660"]),
        _record("2026-03-04", ["510300", "512660"]),
    ]

    result = slice_records(
        sample_records,
        date_from="2026-03-02",
        date_to="2026-03-03",
        codes=["510300"],
    )

    assert [record["date"] for record in result] == ["2026-03-02", "2026-03-03"]
    assert all(
        [stock["code"] for stock in record["raw_data"]["stocks"]] == ["510300"]
        for record in result
    )
    assert all(
        [action["code"] for action in record["ai_result"]["actions"]] == ["510300"]
        for record in result
    )


def test_slice_records_uses_recent_days_when_date_range_missing():
    sample_records = [
        _record("2026-03-01", ["510300"]),
        _record("2026-03-02", ["510300"]),
        _record("2026-03-03", ["510300"]),
        _record("2026-03-04", ["510300"]),
    ]

    result = slice_records(sample_records, days=2)

    assert [record["date"] for record in result] == ["2026-03-03", "2026-03-04"]
