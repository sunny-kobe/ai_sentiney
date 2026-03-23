from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


def _normalize_records(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    merged_by_date: Dict[str, Dict[str, Any]] = {}
    ordered_dates: List[str] = []

    for record in sorted(records, key=lambda item: item.get("date", "")):
        record_date = record.get("date")
        if not record_date:
            continue

        raw_data = record.get("raw_data") if isinstance(record.get("raw_data"), Mapping) else None
        ai_result = record.get("ai_result") if isinstance(record.get("ai_result"), Mapping) else None

        if record_date not in merged_by_date:
            merged_by_date[record_date] = {
                "date": record_date,
                "raw_data": raw_data,
                "ai_result": ai_result,
            }
            ordered_dates.append(record_date)
            continue

        if raw_data is not None:
            merged_by_date[record_date]["raw_data"] = raw_data
        if ai_result is not None:
            merged_by_date[record_date]["ai_result"] = ai_result

    normalized: List[Dict[str, Any]] = []
    for record_date in ordered_dates:
        normalized_record = merged_by_date[record_date]
        stocks = (normalized_record.get("raw_data") or {}).get("stocks", []) or []
        if not isinstance(stocks, list) or not stocks:
            continue
        normalized.append(normalized_record)

    return normalized


def _extract_price(stock: Mapping[str, Any]) -> Optional[float]:
    for key in ("current_price", "close", "price", "last_close"):
        value = stock.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _extract_path_price(stock: Mapping[str, Any]) -> Optional[float]:
    low = stock.get("low")
    if isinstance(low, (int, float)) and low > 0:
        return float(low)
    return _extract_price(stock)


def _resolve_action_label(action: Mapping[str, Any], action_label_key: str = "action_label") -> str:
    for key in (action_label_key, "action_label", "action", "operation", "signal"):
        value = action.get(key)
        if value:
            return str(value)
    return "观察"


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def build_price_matrix(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    sorted_records = _normalize_records(records)
    dates: List[str] = []
    prices: Dict[str, Dict[str, float]] = {}
    path_prices: Dict[str, Dict[str, float]] = {}

    for record in sorted_records:
        record_date = record.get("date")
        if not record_date:
            continue
        dates.append(record_date)
        stocks = (record.get("raw_data") or {}).get("stocks", []) or []
        for stock in stocks:
            if not isinstance(stock, Mapping):
                continue
            code = stock.get("code")
            if not code:
                continue
            price = _extract_price(stock)
            if price is not None:
                prices.setdefault(code, {})[record_date] = price
            path_price = _extract_path_price(stock)
            if path_price is not None:
                path_prices.setdefault(code, {})[record_date] = path_price

    return {
        "dates": dates,
        "prices": prices,
        "path_prices": path_prices,
    }


def calculate_forward_return(entry_price: float, exit_price: float) -> float:
    if entry_price <= 0:
        return 0.0
    return round((exit_price / entry_price) - 1, 4)


def calculate_relative_return(asset_return: float, benchmark_return: float) -> float:
    return round(asset_return - benchmark_return, 4)


def calculate_max_drawdown(prices: Sequence[float]) -> float:
    if not prices:
        return 0.0

    peak = float(prices[0])
    max_drawdown = 0.0
    for price in prices[1:]:
        price = float(price)
        if price > peak:
            peak = price
        if peak <= 0:
            continue
        drawdown = (price / peak) - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    return round(max_drawdown, 4)


def evaluate_forward_windows(
    actions: Sequence[Mapping[str, Any]],
    future_records: Sequence[Mapping[str, Any]],
    benchmark_map: Optional[Mapping[str, str]] = None,
    windows: Sequence[int] = (10, 20, 40),
    action_label_key: str = "action_label",
) -> List[Dict[str, Any]]:
    if not actions or not future_records:
        return []

    benchmark_map = benchmark_map or {}
    matrix = build_price_matrix(future_records)
    dates = matrix["dates"]
    if not dates:
        return []

    entry_date = dates[0]
    results: List[Dict[str, Any]] = []

    for action in actions:
        code = action.get("code")
        if not code:
            continue

        entry_price = matrix["prices"].get(code, {}).get(entry_date)
        if entry_price is None:
            continue

        action_label = _resolve_action_label(action, action_label_key=action_label_key)
        benchmark_code = benchmark_map.get(code)
        window_metrics: Dict[int, Dict[str, Any]] = {}

        for window in windows:
            if len(dates) <= window:
                continue

            window_dates = dates[: window + 1]
            later_path = [matrix["path_prices"].get(code, {}).get(day) for day in window_dates[1:]]
            if any(price is None for price in later_path):
                continue

            exit_date = window_dates[-1]
            exit_price = matrix["prices"].get(code, {}).get(exit_date)
            if exit_price is None:
                continue

            absolute_return = calculate_forward_return(entry_price, exit_price)
            benchmark_return = None
            relative_return = None

            if benchmark_code:
                benchmark_entry = matrix["prices"].get(benchmark_code, {}).get(entry_date)
                benchmark_exit = matrix["prices"].get(benchmark_code, {}).get(exit_date)
                if benchmark_entry is not None and benchmark_exit is not None:
                    benchmark_return = calculate_forward_return(benchmark_entry, benchmark_exit)
                    relative_return = calculate_relative_return(absolute_return, benchmark_return)

            asset_path = [entry_price, *later_path]
            window_metrics[int(window)] = {
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "absolute_return": absolute_return,
                "benchmark_return": benchmark_return,
                "relative_return": relative_return,
                "max_drawdown": calculate_max_drawdown(asset_path),
            }

        if window_metrics:
            results.append(
                {
                    "code": code,
                    "name": action.get("name", code),
                    "action_label": action_label,
                    "confidence": action.get("confidence", "") or "未知",
                    "benchmark_code": benchmark_code,
                    "windows": window_metrics,
                }
            )

    return results


def _empty_window_stats() -> Dict[str, Any]:
    return {
        "count": 0,
        "relative_count": 0,
        "avg_absolute_return": 0.0,
        "avg_relative_return": None,
        "avg_max_drawdown": 0.0,
    }


def _aggregate_window_metrics(evaluations: Sequence[Mapping[str, Any]], windows: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    aggregated: Dict[int, Dict[str, Any]] = {}
    for window in windows:
        window_entries = [item["windows"][window] for item in evaluations if window in item.get("windows", {})]
        if not window_entries:
            aggregated[int(window)] = _empty_window_stats()
            continue

        count = len(window_entries)
        relative_values = [entry["relative_return"] for entry in window_entries if entry.get("relative_return") is not None]
        aggregated[int(window)] = {
            "count": count,
            "relative_count": len(relative_values),
            "avg_absolute_return": round(sum(entry["absolute_return"] for entry in window_entries) / count, 4),
            "avg_relative_return": round(sum(relative_values) / len(relative_values), 4) if relative_values else None,
            "avg_max_drawdown": round(sum(entry["max_drawdown"] for entry in window_entries) / count, 4),
        }
    return aggregated


def calculate_swing_stats(
    records: Sequence[Mapping[str, Any]],
    benchmark_map: Optional[Mapping[str, str]] = None,
    windows: Sequence[int] = (10, 20, 40),
    action_label_key: str = "action_label",
) -> Dict[str, Any]:
    sorted_records = _normalize_records(records)
    evaluations: List[Dict[str, Any]] = []

    for index, record in enumerate(sorted_records):
        actions = (record.get("ai_result") or {}).get("actions", []) or []
        if not actions:
            continue
        evaluations.extend(
            evaluate_forward_windows(
                actions,
                sorted_records[index:],
                benchmark_map=benchmark_map,
                windows=windows,
                action_label_key=action_label_key,
            )
        )

    by_action: Dict[str, List[Dict[str, Any]]] = {}
    by_confidence: Dict[str, List[Dict[str, Any]]] = {}
    for evaluation in evaluations:
        by_action.setdefault(evaluation["action_label"], []).append(evaluation)
        by_confidence.setdefault(evaluation["confidence"], []).append(evaluation)

    return {
        "windows": [int(window) for window in windows],
        "evaluations": evaluations,
        "overall": _aggregate_window_metrics(evaluations, windows),
        "by_action": {
            label: _aggregate_window_metrics(items, windows)
            for label, items in by_action.items()
        },
        "by_confidence": {
            label: _aggregate_window_metrics(items, windows)
            for label, items in by_confidence.items()
        },
    }


def build_swing_scorecard(
    records: Sequence[Mapping[str, Any]],
    benchmark_map: Optional[Mapping[str, str]] = None,
    windows: Sequence[int] = (10, 20, 40),
    action_label_key: str = "action_label",
) -> Dict[str, Any]:
    stats = calculate_swing_stats(
        records,
        benchmark_map=benchmark_map,
        windows=windows,
        action_label_key=action_label_key,
    )

    summary_parts: List[str] = []
    for window in windows:
        window_stats = stats["overall"].get(int(window), {})
        if window_stats.get("count", 0) <= 0:
            continue
        part = f"{int(window)}日样本{window_stats['count']}，平均收益{_format_pct(window_stats['avg_absolute_return'])}"
        if window_stats.get("avg_relative_return") is not None:
            part += f"，平均超额{_format_pct(window_stats['avg_relative_return'])}"
            if window_stats.get("relative_count", 0) != window_stats["count"]:
                part += f"（超额样本{window_stats['relative_count']}/{window_stats['count']}）"
        part += f"，平均回撤{_format_pct(window_stats['avg_max_drawdown'])}"
        summary_parts.append(part)

    action_parts = []
    for label, label_stats in stats["by_action"].items():
        primary_window = next(
            (
                int(window)
                for window in windows
                if label_stats.get(int(window), {}).get("count", 0) > 0
            ),
            None,
        )
        if primary_window is None:
            continue
        action_relative = label_stats[primary_window]["avg_relative_return"]
        if action_relative is not None:
            action_parts.append(f"{label}{primary_window}日超额{_format_pct(action_relative)}")
        else:
            action_parts.append(f"{label}{primary_window}日样本{label_stats[primary_window]['count']}")

    if action_parts:
        summary_parts.append("动作分组 " + " / ".join(action_parts))

    return {
        "windows": [int(window) for window in windows],
        "evaluations": stats["evaluations"],
        "stats": {
            "overall": stats["overall"],
            "by_action": stats["by_action"],
            "by_confidence": stats["by_confidence"],
        },
        "summary_text": " | ".join(summary_parts) if summary_parts else "历史数据不足，暂无中期统计",
    }
