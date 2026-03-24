from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence


def _max_drawdown(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    peak = float(values[0])
    max_drawdown = 0.0
    for value in values[1:]:
        value = float(value)
        if value > peak:
            peak = value
        if peak <= 0:
            continue
        drawdown = (value / peak) - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    return round(max_drawdown, 4)


def summarize_backtest(result: Mapping[str, Any]) -> Dict[str, Any]:
    equity_curve = result.get("equity_curve", []) or []
    values = [float(item.get("total_value", 0) or 0) for item in equity_curve]
    initial_value = values[0] if values else float(result.get("initial_cash", 0) or 0)
    final_value = values[-1] if values else initial_value
    total_return = round((final_value / initial_value) - 1, 4) if initial_value else 0.0
    return {
        "initial_value": round(initial_value, 2),
        "final_value": round(final_value, 2),
        "total_return": total_return,
        "max_drawdown": _max_drawdown(values),
        "trade_count": len(result.get("trades", []) or []),
        "total_fees": round(float(result.get("total_fees", 0) or 0), 2),
    }
