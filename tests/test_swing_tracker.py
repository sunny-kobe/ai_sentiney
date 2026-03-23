from datetime import date, timedelta

import pytest

from src.processor.swing_tracker import (
    build_price_matrix,
    build_swing_scorecard,
    calculate_max_drawdown,
    calculate_swing_stats,
    evaluate_forward_windows,
)


def _make_record(day_offset, prices, actions=None):
    record_date = (date(2026, 1, 5) + timedelta(days=day_offset)).isoformat()
    stocks = [
        {
            "code": code,
            "name": code,
            "current_price": price,
        }
        for code, price in prices.items()
    ]
    return {
        "date": record_date,
        "raw_data": {"stocks": stocks},
        "ai_result": {"actions": actions or []},
    }


def _build_records():
    actions = [
        {"code": "AAA", "name": "Alpha", "action_label": "增配", "confidence": "高"},
        {"code": "BBB", "name": "Beta", "action_label": "回避", "confidence": "中"},
        {"code": "SPARSE", "name": "Sparse", "action_label": "增配", "confidence": "低"},
    ]

    records = []
    for offset in range(41):
        prices = {
            "AAA": 100 + offset,
            "BBB": 100 - (offset * 0.5),
            "BENCH": 100 + (offset * 0.5),
        }
        if offset == 2:
            prices["AAA"] = 105
        elif offset == 4:
            prices["AAA"] = 95
        elif offset == 5:
            prices["AAA"] = 98
        if offset <= 4:
            prices["SPARSE"] = 50 + offset
        records.append(_make_record(offset, prices, actions=actions if offset == 0 else None))
    return records


def test_evaluate_forward_windows_matches_symbol_prices_and_benchmark_returns():
    records = _build_records()
    actions = records[0]["ai_result"]["actions"]

    evaluations = evaluate_forward_windows(
        actions,
        records,
        benchmark_map={"AAA": "BENCH", "BBB": "BENCH", "SPARSE": "BENCH"},
        windows=(10, 20, 40),
    )

    codes = {item["code"] for item in evaluations}
    assert codes == {"AAA", "BBB"}

    alpha = next(item for item in evaluations if item["code"] == "AAA")
    assert alpha["action_label"] == "增配"
    assert alpha["windows"][10]["absolute_return"] == pytest.approx(0.10)
    assert alpha["windows"][10]["benchmark_return"] == pytest.approx(0.05)
    assert alpha["windows"][10]["relative_return"] == pytest.approx(0.05)
    assert alpha["windows"][10]["max_drawdown"] == pytest.approx(-0.0952)
    assert "outcome" not in alpha["windows"][10]
    assert alpha["windows"][20]["absolute_return"] == pytest.approx(0.20)
    assert alpha["windows"][40]["absolute_return"] == pytest.approx(0.40)

    beta = next(item for item in evaluations if item["code"] == "BBB")
    assert beta["action_label"] == "回避"
    assert beta["windows"][10]["absolute_return"] == pytest.approx(-0.05)
    assert beta["windows"][10]["relative_return"] == pytest.approx(-0.10)


def test_calculate_max_drawdown_tracks_peak_to_trough_loss():
    drawdown = calculate_max_drawdown([100, 110, 108, 120, 90, 130])
    assert drawdown == pytest.approx(-0.25)


def test_calculate_swing_stats_groups_by_action_and_confidence():
    stats = calculate_swing_stats(
        _build_records(),
        benchmark_map={"AAA": "BENCH", "BBB": "BENCH", "SPARSE": "BENCH"},
        windows=(10, 20, 40),
    )

    assert stats["overall"][10]["count"] == 2
    assert stats["overall"][10]["avg_absolute_return"] == pytest.approx(0.025)
    assert stats["overall"][10]["avg_relative_return"] == pytest.approx(-0.025)
    assert "success_rate" not in stats["overall"][10]

    assert stats["by_action"]["增配"][10]["count"] == 1
    assert stats["by_action"]["增配"][10]["avg_relative_return"] == pytest.approx(0.05)
    assert stats["by_action"]["增配"][10]["avg_max_drawdown"] == pytest.approx(-0.0952)

    assert stats["by_action"]["回避"][20]["count"] == 1
    assert stats["by_action"]["回避"][20]["avg_relative_return"] == pytest.approx(-0.20)

    assert stats["by_confidence"]["高"][40]["count"] == 1
    assert stats["by_confidence"]["中"][40]["count"] == 1
    assert "低" not in stats["by_confidence"]


def test_build_swing_scorecard_summarizes_medium_term_windows():
    scorecard = build_swing_scorecard(
        _build_records(),
        benchmark_map={"AAA": "BENCH", "BBB": "BENCH", "SPARSE": "BENCH"},
        windows=(10, 20, 40),
    )

    assert "10日" in scorecard["summary_text"]
    assert "平均超额" in scorecard["summary_text"]
    assert "增配" in scorecard["summary_text"]
    assert "成功率" not in scorecard["summary_text"]
    assert scorecard["stats"]["by_action"]["回避"][40]["avg_relative_return"] == pytest.approx(-0.40)


def test_sparse_benchmark_still_computes_relative_return_from_entry_and_exit():
    records = []
    start = date(2026, 1, 5)
    actions = [{"code": "AAA", "name": "Alpha", "action_label": "增配", "confidence": "高"}]
    for offset in range(11):
        prices = {"AAA": 100 + offset}
        if offset in (0, 10):
            prices["BENCH"] = 100 + (offset * 0.5)
        records.append(
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "raw_data": {"stocks": [{"code": code, "name": code, "current_price": price} for code, price in prices.items()]},
                "ai_result": {"actions": actions if offset == 0 else []},
            }
        )

    evaluations = evaluate_forward_windows(actions, records, benchmark_map={"AAA": "BENCH"}, windows=(10,))
    assert evaluations[0]["windows"][10]["benchmark_return"] == pytest.approx(0.05)
    assert evaluations[0]["windows"][10]["relative_return"] == pytest.approx(0.05)

    stats = calculate_swing_stats(records, benchmark_map={"AAA": "BENCH"}, windows=(10,))
    assert stats["overall"][10]["relative_count"] == 1


def test_drawdown_starts_from_entry_price_not_entry_day_low():
    actions = [{"code": "AAA", "name": "Alpha", "action_label": "增配", "confidence": "高"}]
    records = [
        {
            "date": "2026-01-05",
            "raw_data": {"stocks": [{"code": "AAA", "name": "AAA", "current_price": 100, "low": 90}]},
            "ai_result": {"actions": actions},
        },
        {
            "date": "2026-01-06",
            "raw_data": {"stocks": [{"code": "AAA", "name": "AAA", "current_price": 95}]},
            "ai_result": {"actions": []},
        },
        {
            "date": "2026-01-07",
            "raw_data": {"stocks": [{"code": "AAA", "name": "AAA", "current_price": 120}]},
            "ai_result": {"actions": []},
        },
    ]

    evaluations = evaluate_forward_windows(actions, records, windows=(2,))
    assert evaluations[0]["windows"][2]["max_drawdown"] == pytest.approx(-0.05)


def test_build_price_matrix_deduplicates_same_day_snapshots():
    records = [
        _make_record(0, {"AAA": 100}),
        {
            "date": _make_record(0, {"AAA": 101})["date"],
            "raw_data": {"stocks": [{"code": "AAA", "name": "AAA", "current_price": 101}]},
            "ai_result": {"actions": []},
        },
        _make_record(1, {"AAA": 110}),
    ]

    matrix = build_price_matrix(records)
    assert matrix["dates"] == [records[0]["date"], records[2]["date"]]
    assert matrix["prices"]["AAA"][records[0]["date"]] == pytest.approx(101)


def test_calculate_swing_stats_skips_none_payloads():
    stats = calculate_swing_stats(
        [
            {"date": "2026-01-05", "raw_data": None, "ai_result": None},
            _make_record(1, {"AAA": 101}),
        ],
        windows=(10,),
    )

    assert stats["overall"][10]["count"] == 0
