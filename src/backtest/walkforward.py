from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from src.backtest.engine import run_deterministic_backtest


def run_walkforward_validation(
    records: Sequence[Mapping[str, Any]],
    *,
    train_window: int,
    test_window: int,
    initial_cash: float = 100_000.0,
) -> Dict[str, Any]:
    ordered = sorted(records, key=lambda item: str(item.get("date", "")))
    segments = []
    start = 0

    while start + train_window + test_window <= len(ordered):
        segment_records = ordered[start + train_window - 1 : start + train_window + test_window]
        result = run_deterministic_backtest(segment_records, initial_cash=initial_cash)
        segments.append(
            {
                "train_end_date": ordered[start + train_window - 1].get("date"),
                "test_end_date": ordered[start + train_window + test_window - 1].get("date"),
                "total_return": result.get("total_return", 0.0),
                "max_drawdown": result.get("max_drawdown", 0.0),
                "trade_count": len(result.get("trades", []) or []),
            }
        )
        start += test_window

    avg_total_return = (
        round(sum(segment["total_return"] for segment in segments) / len(segments), 4)
        if segments
        else 0.0
    )

    return {
        "segment_count": len(segments),
        "segments": segments,
        "avg_total_return": avg_total_return,
    }
