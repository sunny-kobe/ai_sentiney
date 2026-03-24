from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from src.processor.swing_tracker import build_price_matrix, calculate_max_drawdown


ACTION_ORDER = ["增配", "持有", "减配", "回避", "观察"]
ACTION_DOWNGRADE_ORDER = ["增配", "持有", "观察", "减配", "回避"]
RISK_CLUSTERS = {"small_cap", "ai", "semiconductor"}
BROAD_BETA_CODES = ("159338", "510300", "510980")
BENCHMARK_CANDIDATES = {
    "broad_beta": ["159338", "510300", "510980"],
    "small_cap": ["510500", "563300", "159338", "510300"],
    "ai": ["159819", "588760", "159338", "510300"],
    "semiconductor": ["512480", "560780", "159338", "510300"],
    "precious_metals": ["159934", "159937", "159338", "510300"],
    "sector_etf": ["159338", "510300", "510980"],
    "single_name": ["159338", "510300", "510980"],
}

SIGNAL_SCORES = {
    "OPPORTUNITY": 3,
    "ACCUMULATE": 2,
    "SAFE": 0,
    "HOLD": 0,
    "WATCH": -1,
    "OBSERVED": -1,
    "OVERBOUGHT": -2,
    "WARNING": -2,
    "DANGER": -3,
    "LOCKED_DANGER": -3,
    "LIMIT_DOWN": -3,
}

ACTION_PLANS = {
    "增配": "只做分批加，不追高，优先把仓位放到最强的一档。",
    "持有": "先把现有仓位拿住，等下一次确认转强再决定要不要加。",
    "减配": "先收缩一部分仓位，把组合波动降下来。",
    "回避": "先收缩到低风险状态，没有重新站稳前不急着回去。",
    "观察": "先看，不急着动，等方向更清楚再决定。",
}

SIGNAL_PHRASES = {
    "OPPORTUNITY": "已经重新转强",
    "ACCUMULATE": "回踩后有企稳迹象",
    "SAFE": "主趋势还在",
    "HOLD": "主趋势还在",
    "WATCH": "还没确认重新走强",
    "OBSERVED": "方向暂时不清楚",
    "OVERBOUGHT": "短线有点过热",
    "WARNING": "已经开始转弱",
    "DANGER": "趋势明显破位",
    "LOCKED_DANGER": "趋势明显破位",
    "LIMIT_DOWN": "风险集中释放",
}

REGIME_CONCLUSIONS = {
    "进攻": "当前偏进攻，可以把仓位集中到最强方向，但继续分批，不追高。",
    "均衡": "当前偏均衡，核心仓先稳住，只对最强方向做小幅调整。",
    "防守": "当前偏防守，先守住已有成果，弱势方向以收缩仓位为主。",
    "撤退": "当前进入撤退阶段，先把高波动方向降下来，等市场重新企稳再回来。",
}
POSITION_TEMPLATES = {
    "进攻": {"total_exposure": (90, 100), "core": (50, 60), "satellite": (30, 40), "cash": (0, 10)},
    "均衡": {"total_exposure": (65, 80), "core": (40, 50), "satellite": (15, 25), "cash": (20, 35)},
    "防守": {"total_exposure": (35, 55), "core": (20, 35), "satellite": (0, 10), "cash": (45, 65)},
    "撤退": {"total_exposure": (0, 20), "core": (0, 15), "satellite": (0, 0), "cash": (80, 100)},
}
ACTION_WEIGHT_PRIORITY = {"增配": 5, "持有": 4, "观察": 2, "减配": 1, "回避": 0}
SMALL_POSITION_RANGES = {"观察": (0, 5), "减配": (0, 3), "回避": (0, 0)}


def _format_pct_value(value: float) -> str:
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def _parse_pct_range(weight: str) -> Sequence[int]:
    text = str(weight or "0%").replace("%", "")
    if "-" in text:
        min_part, max_part = text.split("-", 1)
        return int(min_part), int(max_part)
    value = int(text or 0)
    return value, value


def _format_money(value: float) -> str:
    return f"{float(value):.2f}"


def infer_cluster(stock: Mapping[str, Any]) -> str:
    name = str(stock.get("name", ""))
    code = str(stock.get("code", ""))

    if "中证2000" in name or "中证500" in name or code in {"510500", "563300"}:
        return "small_cap"
    if "人工智能" in name or code in {"159819", "588760"}:
        return "ai"
    if "半导体" in name or code in {"512480", "560780"}:
        return "semiconductor"
    if any(keyword in name for keyword in ("黄金", "白银", "紫金", "资源")):
        return "precious_metals"
    if any(keyword in name for keyword in ("沪深300", "A500", "上证")) or code in {"510300", "159338", "510980"}:
        return "broad_beta"
    if "ETF" in name:
        return "sector_etf"
    return "single_name"


def _downgrade_action(action_label: str, steps: int = 1) -> str:
    try:
        index = ACTION_DOWNGRADE_ORDER.index(action_label)
    except ValueError:
        return action_label
    return ACTION_DOWNGRADE_ORDER[min(index + max(steps, 0), len(ACTION_DOWNGRADE_ORDER) - 1)]


def _format_pct_range(min_weight: int, max_weight: int) -> str:
    min_weight = max(int(round(min_weight)), 0)
    max_weight = max(int(round(max_weight)), 0)
    if max_weight <= 0:
        return "0%"
    if min_weight == max_weight:
        return f"{max_weight}%"
    return f"{min_weight}%-{max_weight}%"


def _assign_position_bucket(decision: Mapping[str, Any]) -> str:
    action_label = str(decision.get("action_label", "观察"))
    cluster = str(decision.get("cluster", "single_name"))

    if action_label == "回避":
        return "空仓"
    if action_label in {"观察", "减配"}:
        return "卫星仓"
    if cluster in RISK_CLUSTERS or cluster == "single_name":
        return "卫星仓"
    if cluster in {"broad_beta", "precious_metals"}:
        return "核心仓"
    if cluster == "sector_etf" and not _is_weak_relative(
        decision.get("relative_return_20"),
        decision.get("relative_return_40"),
    ):
        return "核心仓"
    return "卫星仓"


def _weight_score(decision: Mapping[str, Any]) -> int:
    base = ACTION_WEIGHT_PRIORITY.get(str(decision.get("action_label", "观察")), 1)
    raw_score = int(decision.get("score", 0) or 0)
    return max(base + max(raw_score, 0), 1)


def _allocate_bucket_ranges(
    decisions: Sequence[Mapping[str, Any]],
    target_range: Sequence[int],
) -> Dict[str, Dict[str, int]]:
    allocations: Dict[str, Dict[str, int]] = {}
    if not decisions:
        return allocations

    fixed_items = [item for item in decisions if str(item.get("action_label")) in SMALL_POSITION_RANGES]
    strong_items = [item for item in decisions if str(item.get("action_label")) not in SMALL_POSITION_RANGES]

    fixed_min = 0
    fixed_max = 0
    for item in fixed_items:
        min_weight, max_weight = SMALL_POSITION_RANGES[str(item.get("action_label"))]
        allocations[str(item.get("code"))] = {"min": min_weight, "max": max_weight}
        fixed_min += min_weight
        fixed_max += max_weight

    remaining_min = max(int(target_range[0]) - fixed_min, 0)
    remaining_max = max(int(target_range[1]) - fixed_max, 0)

    if not strong_items:
        return allocations

    total_score = sum(_weight_score(item) for item in strong_items)
    for item in strong_items:
        code = str(item.get("code"))
        score = _weight_score(item)
        min_weight = int(round(remaining_min * score / total_score))
        max_weight = int(round(remaining_max * score / total_score))
        allocations[code] = {"min": min_weight, "max": max_weight}

    return allocations


def _summarize_bucket_ranges(items: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    total_min = 0
    total_max = 0
    for item in items:
        weight = str(item.get("target_weight", "0%"))
        if weight == "0%":
            continue
        if "-" in weight:
            min_part, max_part = weight.replace("%", "").split("-", 1)
            total_min += int(min_part)
            total_max += int(max_part)
        else:
            value = int(weight.replace("%", ""))
            total_min += value
            total_max += value
    return {"min": total_min, "max": total_max}


def build_position_plan(decisions: Sequence[Mapping[str, Any]], regime: str) -> Dict[str, Any]:
    template = POSITION_TEMPLATES.get(regime, POSITION_TEMPLATES["均衡"])
    enriched = [dict(item) for item in decisions]

    core_candidates: List[Dict[str, Any]] = []
    satellite_candidates: List[Dict[str, Any]] = []

    for item in enriched:
        bucket = _assign_position_bucket(item)
        item["position_bucket"] = bucket
        if bucket == "核心仓":
            core_candidates.append(item)
        elif bucket == "卫星仓":
            satellite_candidates.append(item)
        else:
            item["target_weight"] = "0%"

    core_allocations = _allocate_bucket_ranges(core_candidates, template["core"])
    satellite_allocations = _allocate_bucket_ranges(satellite_candidates, template["satellite"])

    for item in enriched:
        code = str(item.get("code"))
        bucket = item.get("position_bucket")
        if bucket == "核心仓":
            allocation = core_allocations.get(code, {"min": 0, "max": 0})
            item["target_weight"] = _format_pct_range(allocation["min"], allocation["max"])
        elif bucket == "卫星仓":
            allocation = satellite_allocations.get(code, {"min": 0, "max": 0})
            item["target_weight"] = _format_pct_range(allocation["min"], allocation["max"])
        else:
            item["target_weight"] = "0%"

    buckets = {"核心仓": [], "卫星仓": [], "现金": []}
    for item in enriched:
        bucket = item.get("position_bucket")
        if bucket not in {"核心仓", "卫星仓"}:
            continue
        buckets[bucket].append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "target_weight": item.get("target_weight", "0%"),
            }
        )

    core_summary = _summarize_bucket_ranges(buckets["核心仓"])
    satellite_summary = _summarize_bucket_ranges(buckets["卫星仓"])
    total_summary = {
        "min": core_summary["min"] + satellite_summary["min"],
        "max": core_summary["max"] + satellite_summary["max"],
    }
    cash_summary = {
        "min": max(0, 100 - total_summary["max"]),
        "max": max(0, 100 - total_summary["min"]),
    }

    return {
        "actions": enriched,
        "position_plan": {
            "total_exposure": _format_pct_range(total_summary["min"], total_summary["max"]),
            "core_target": _format_pct_range(core_summary["min"], core_summary["max"]),
            "satellite_target": _format_pct_range(satellite_summary["min"], satellite_summary["max"]),
            "cash_target": _format_pct_range(cash_summary["min"], cash_summary["max"]),
            "regime_total_exposure": _format_pct_range(*template["total_exposure"]),
            "regime_core_target": _format_pct_range(*template["core"]),
            "regime_satellite_target": _format_pct_range(*template["satellite"]),
            "regime_cash_target": _format_pct_range(*template["cash"]),
            "weekly_rebalance": "每周五收盘后生成计划，下一交易日分批执行。",
            "daily_rule": "日级只减不加，先减卫星仓，再减观察位。",
            "buckets": buckets,
        },
    }


def build_current_position_snapshot(
    decisions: Sequence[Mapping[str, Any]],
    portfolio_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    state = dict(portfolio_state or {})
    cash_balance = float(state.get("cash_balance", 0) or 0)
    lot_size = int(state.get("lot_size", 100) or 100)

    current_value_total = 0.0
    enriched_actions: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        shares = int(updated.get("shares", 0) or 0)
        current_price = float(updated.get("current_price", 0) or 0)
        current_value = round(shares * current_price, 2)
        updated["current_shares"] = shares
        updated["current_value"] = _format_money(current_value)
        current_value_total += current_value
        enriched_actions.append(updated)

    account_total_assets = round(current_value_total + cash_balance, 2)
    if account_total_assets <= 0:
        account_total_assets = round(current_value_total, 2)

    for updated in enriched_actions:
        shares = int(updated.get("current_shares", 0) or 0)
        current_price = float(updated.get("current_price", 0) or 0)
        current_value = float(updated.get("current_value", 0) or 0)
        current_weight_pct = (current_value / account_total_assets * 100) if account_total_assets > 0 else 0.0
        updated["current_weight"] = _format_pct_value(current_weight_pct)

        target_min_pct, target_max_pct = _parse_pct_range(updated.get("target_weight", "0%"))
        target_min_value = account_total_assets * target_min_pct / 100
        target_max_value = account_total_assets * target_max_pct / 100

        if current_price <= 0 or shares <= 0:
            if target_max_pct > 0:
                updated["rebalance_action"] = "暂无持仓，等重新转强后再分批建仓"
            else:
                updated["rebalance_action"] = "暂无持仓"
            continue

        if target_max_value <= 0:
            updated["rebalance_action"] = f"卖出{shares}份"
            continue

        keep_max_shares = math.floor(target_max_value / current_price / lot_size) * lot_size
        keep_min_shares = math.ceil(target_min_value / current_price / lot_size) * lot_size if target_min_value > 0 else 0
        keep_max_shares = max(min(keep_max_shares, shares), 0)
        keep_min_shares = max(keep_min_shares, 0)

        if shares > keep_max_shares:
            sell_shares = shares - keep_max_shares
            if keep_max_shares > 0:
                updated["rebalance_action"] = f"卖出{sell_shares}份，保留约{keep_max_shares}份"
            else:
                updated["rebalance_action"] = f"卖出{sell_shares}份"
        elif shares < keep_min_shares:
            buy_shares = keep_min_shares - shares
            updated["rebalance_action"] = f"如转强可加{buy_shares}份，补到约{keep_min_shares}份"
        else:
            updated["rebalance_action"] = "先按当前仓位拿住"

    current_exposure_pct = (current_value_total / account_total_assets * 100) if account_total_assets > 0 else 0.0
    current_cash_pct = (cash_balance / account_total_assets * 100) if account_total_assets > 0 else 0.0

    return {
        "actions": enriched_actions,
        "position_snapshot": {
            "current_total_exposure": _format_pct_value(current_exposure_pct),
            "current_cash_pct": _format_pct_value(current_cash_pct),
            "account_total_assets": _format_money(account_total_assets),
            "cash_balance": _format_money(cash_balance),
            "lot_size": lot_size,
        },
    }


def resolve_benchmark_code(stock: Mapping[str, Any], available_codes: Set[str]) -> Optional[str]:
    code = str(stock.get("code", "") or "")
    cluster = infer_cluster(stock)
    candidate_codes = BENCHMARK_CANDIDATES.get(cluster, BENCHMARK_CANDIDATES["single_name"])

    for candidate in candidate_codes:
        if candidate == code:
            continue
        if candidate in available_codes:
            return candidate

    for candidate in BROAD_BETA_CODES:
        if candidate == code:
            continue
        if candidate in available_codes:
            return candidate

    return None


def _build_price_timeline(matrix: Mapping[str, Any], code: str) -> List[float]:
    timeline: List[float] = []
    for record_date in matrix.get("dates", []):
        price = (matrix.get("prices", {}) or {}).get(code, {}).get(record_date)
        if isinstance(price, (int, float)) and price > 0:
            timeline.append(float(price))
    return timeline


def _window_return(prices: Sequence[float], window: int) -> Optional[float]:
    if len(prices) <= window:
        return None
    entry = float(prices[-(window + 1)])
    exit_price = float(prices[-1])
    if entry <= 0:
        return None
    return round((exit_price / entry) - 1, 4)


def _window_drawdown(prices: Sequence[float], window: int) -> Optional[float]:
    if len(prices) < 2:
        return None
    window_prices = list(prices[-(window + 1):]) if len(prices) > window else list(prices)
    if len(window_prices) < 2:
        return None
    return calculate_max_drawdown(window_prices)


def _is_strong_relative(relative_20: Optional[float], relative_40: Optional[float]) -> bool:
    return (relative_20 is not None and relative_20 >= 0.05) or (relative_40 is not None and relative_40 >= 0.08)


def _is_weak_relative(relative_20: Optional[float], relative_40: Optional[float]) -> bool:
    return (relative_20 is not None and relative_20 <= -0.05) or (relative_40 is not None and relative_40 <= -0.08)


def build_benchmark_context(
    stocks: Sequence[Mapping[str, Any]],
    historical_records: Sequence[Mapping[str, Any]],
    analysis_date: Optional[str] = None,
) -> Dict[str, Any]:
    records = list(historical_records)
    if stocks:
        snapshot_date = analysis_date or (historical_records[-1].get("date") if historical_records else "9999-12-31")
        records.append(
            {
                "date": snapshot_date,
                "raw_data": {"stocks": [dict(stock) for stock in stocks]},
                "ai_result": {"actions": []},
            }
        )

    matrix = build_price_matrix(records)
    available_codes = set((matrix.get("prices") or {}).keys())
    benchmark_snapshot: Dict[str, Dict[str, Any]] = {}

    for stock in stocks:
        code = str(stock.get("code", "") or "")
        if not code:
            continue

        benchmark_code = resolve_benchmark_code(stock, available_codes)
        asset_prices = _build_price_timeline(matrix, code)
        benchmark_prices = _build_price_timeline(matrix, benchmark_code) if benchmark_code else []

        asset_return_20 = _window_return(asset_prices, 20)
        asset_return_40 = _window_return(asset_prices, 40)
        benchmark_return_20 = _window_return(benchmark_prices, 20) if benchmark_prices else None
        benchmark_return_40 = _window_return(benchmark_prices, 40) if benchmark_prices else None
        relative_return_20 = (
            round(asset_return_20 - benchmark_return_20, 4)
            if asset_return_20 is not None and benchmark_return_20 is not None
            else None
        )
        relative_return_40 = (
            round(asset_return_40 - benchmark_return_40, 4)
            if asset_return_40 is not None and benchmark_return_40 is not None
            else None
        )

        benchmark_snapshot[code] = {
            "benchmark_code": benchmark_code,
            "asset_return_20": asset_return_20,
            "asset_return_40": asset_return_40,
            "benchmark_return_20": benchmark_return_20,
            "benchmark_return_40": benchmark_return_40,
            "relative_return_20": relative_return_20,
            "relative_return_40": relative_return_40,
            "drawdown_20": _window_drawdown(asset_prices, 20),
            "drawdown_40": _window_drawdown(asset_prices, 40),
        }

    return {
        "price_matrix": matrix,
        "available_codes": available_codes,
        "benchmark_snapshot": benchmark_snapshot,
    }


def _parse_breadth_score(market_breadth: str) -> int:
    numbers = [int(item) for item in re.findall(r"\d+", market_breadth or "")]
    if len(numbers) < 2:
        return 0

    up_count, down_count = numbers[0], numbers[1]
    spread = up_count - down_count
    if spread >= 1200:
        return 1
    if spread <= -1200:
        return -1
    return 0


def _history_momentum_score(historical_records: Sequence[Mapping[str, Any]]) -> int:
    price_paths: Dict[str, List[float]] = {}
    for record in historical_records:
        stocks = (record.get("raw_data") or {}).get("stocks", []) or []
        for stock in stocks:
            code = stock.get("code")
            price = stock.get("current_price")
            if code and isinstance(price, (int, float)) and price > 0:
                price_paths.setdefault(code, []).append(float(price))

    if not price_paths:
        return 0

    returns = []
    for prices in price_paths.values():
        if len(prices) < 2:
            continue
        returns.append((prices[-1] / prices[0]) - 1)

    if not returns:
        return 0

    average_return = sum(returns) / len(returns)
    if average_return >= 0.03:
        return 1
    if average_return <= -0.03:
        return -1
    return 0


def _news_score(news_items: Iterable[str]) -> int:
    positive_keywords = ("回暖", "修复", "企稳", "改善", "增持", "突破")
    negative_keywords = ("暴跌", "关税", "避险", "升级", "下修", "减持")
    score = 0

    for item in news_items:
        text = str(item)
        if any(keyword in text for keyword in negative_keywords):
            score -= 1
        elif any(keyword in text for keyword in positive_keywords):
            score += 1

    if score > 0:
        return 1
    if score < 0:
        return -1
    return 0


def _detect_stressed_clusters(stocks: Sequence[Mapping[str, Any]]) -> Set[str]:
    stressed = set()
    for stock in stocks:
        cluster = infer_cluster(stock)
        if cluster not in RISK_CLUSTERS:
            continue

        signal = str(stock.get("signal", "SAFE")).upper()
        bias_pct = float(stock.get("bias_pct", 0) or 0)
        pct_change = float(stock.get("pct_change", 0) or 0)
        if signal in {"DANGER", "WARNING", "LOCKED_DANGER"} or bias_pct <= -0.03 or pct_change <= -2:
            stressed.add(cluster)
    return stressed


def classify_market_regime(ai_input: Mapping[str, Any], historical_records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    indices = ai_input.get("indices", {}) or {}
    change_values = [
        float(data.get("change_pct", 0) or 0)
        for data in indices.values()
        if isinstance(data, Mapping)
    ]
    average_change = sum(change_values) / len(change_values) if change_values else 0.0

    score = 0
    reasons: List[str] = []

    if average_change >= 1.0:
        score += 2
        reasons.append("指数同步走强")
    elif average_change >= 0.3:
        score += 1
        reasons.append("指数偏强")
    elif average_change <= -2.0:
        score -= 3
        reasons.append("指数快速走弱")
    elif average_change <= -0.8:
        score -= 1
        reasons.append("指数偏弱")

    breadth_score = _parse_breadth_score(str(ai_input.get("market_breadth", "")))
    if breadth_score > 0:
        reasons.append("市场宽度在改善")
    elif breadth_score < 0:
        reasons.append("下跌家数明显更多")
    score += breadth_score

    history_score = _history_momentum_score(historical_records)
    if history_score > 0:
        reasons.append("近几天趋势向上")
    elif history_score < 0:
        reasons.append("近几天趋势向下")
    score += history_score

    news_score = _news_score((ai_input.get("macro_news", {}) or {}).get("telegraph", []) or [])
    if news_score > 0:
        reasons.append("消息面偏暖")
    elif news_score < 0:
        reasons.append("消息面偏空")
    score += news_score

    stressed_clusters = _detect_stressed_clusters(ai_input.get("stocks", []) or [])
    if len(stressed_clusters) >= 2:
        score -= 1
        reasons.append("高弹性板块联动走弱")

    if score >= 3:
        regime = "进攻"
    elif score >= 0:
        regime = "均衡"
    elif score >= -3:
        regime = "防守"
    else:
        regime = "撤退"

    return {
        "regime": regime,
        "score": score,
        "reasons": reasons,
        "stressed_clusters": stressed_clusters,
    }


def _label_from_score(score: int) -> str:
    if score >= 5:
        return "增配"
    if score >= 2:
        return "持有"
    if score >= 0:
        return "观察"
    if score <= -5:
        return "回避"
    if score <= -2:
        return "减配"
    return "观察"


def score_holding(stock: Mapping[str, Any], benchmark_context: Mapping[str, Any]) -> Dict[str, Any]:
    signal = str(stock.get("signal", "SAFE")).upper()
    code = str(stock.get("code", "") or "")
    cluster = infer_cluster(stock)
    regime = str(benchmark_context.get("regime", "均衡"))
    stressed_clusters = set(benchmark_context.get("stressed_clusters", set()) or set())
    benchmark_snapshot = (benchmark_context.get("benchmark_snapshot") or {}).get(code, {})

    score = SIGNAL_SCORES.get(signal, 0)

    current_price = float(stock.get("current_price", 0) or 0)
    ma20 = float(stock.get("ma20", 0) or 0)
    pct_change = float(stock.get("pct_change", 0) or 0)
    bias_pct = float(stock.get("bias_pct", 0) or 0)
    if bias_pct >= 0.02:
        score += 1
    elif bias_pct <= -0.02:
        score -= 1

    macd_trend = str((stock.get("macd") or {}).get("trend", "UNKNOWN")).upper()
    if macd_trend in {"BULLISH", "GOLDEN_CROSS"}:
        score += 1
    elif macd_trend in {"BEARISH", "DEATH_CROSS"}:
        score -= 1

    obv_trend = str((stock.get("obv") or {}).get("trend", "UNKNOWN")).upper()
    if obv_trend == "INFLOW":
        score += 1
    elif obv_trend == "OUTFLOW":
        score -= 1

    if ma20 > 0 and current_price < ma20 and pct_change < 0:
        score -= 1

    relative_return_20 = benchmark_snapshot.get("relative_return_20")
    relative_return_40 = benchmark_snapshot.get("relative_return_40")
    drawdown_20 = benchmark_snapshot.get("drawdown_20")
    if _is_strong_relative(relative_return_20, relative_return_40):
        score += 2
    elif _is_weak_relative(relative_return_20, relative_return_40):
        score -= 2

    if isinstance(drawdown_20, (int, float)):
        if drawdown_20 <= -0.12:
            score -= 2
        elif drawdown_20 <= -0.08:
            score -= 1

    if regime == "进攻" and cluster in RISK_CLUSTERS and signal in {"OPPORTUNITY", "ACCUMULATE"}:
        score += 1
    elif regime == "防守" and cluster in RISK_CLUSTERS:
        score -= 1
    elif regime == "撤退":
        score -= 1
        if cluster in RISK_CLUSTERS:
            score -= 1

    if cluster in stressed_clusters:
        score -= 1

    action_label = _label_from_score(score)

    if ma20 > 0 and current_price >= ma20:
        position_phrase = f"还站在20日线 {ma20:.2f} 上方"
        risk_line = f"收盘跌回20日线 {ma20:.2f} 下方，就先缩仓。"
    else:
        position_phrase = f"已经落到20日线 {ma20:.2f} 下方"
        risk_line = f"不能重新站上20日线 {ma20:.2f} 之前，先别加仓。"

    flow_phrase = "承接还在配合" if obv_trend == "INFLOW" else "承接偏弱"
    reason_parts = [
        position_phrase,
        SIGNAL_PHRASES.get(signal, "方向还不明朗"),
        flow_phrase,
    ]
    if _is_strong_relative(relative_return_20, relative_return_40):
        reason_parts.append("强于对照基准")
    elif _is_weak_relative(relative_return_20, relative_return_40):
        reason_parts.append("弱于对照基准")
    if isinstance(drawdown_20, (int, float)) and drawdown_20 <= -0.08:
        reason_parts.append("近一段回撤偏深")
    reason = "，".join(reason_parts) + "。"

    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "cluster": cluster,
        "signal": signal,
        "score": score,
        "confidence": stock.get("confidence", ""),
        "action_label": action_label,
        "conclusion": action_label,
        "operation": action_label,
        "reason": reason,
        "plan": ACTION_PLANS[action_label],
        "risk_line": risk_line,
        "technical_evidence": stock.get("tech_summary", ""),
        "current_price": current_price,
        "ma20": ma20,
        "shares": int(stock.get("shares", 0) or 0),
        "benchmark_code": benchmark_snapshot.get("benchmark_code"),
        "relative_return_20": relative_return_20,
        "relative_return_40": relative_return_40,
        "drawdown_20": drawdown_20,
    }


def apply_cluster_risk_overlay(
    decisions: Sequence[Mapping[str, Any]],
    stressed_clusters: Set[str],
) -> List[Dict[str, Any]]:
    if len(stressed_clusters & RISK_CLUSTERS) < 2:
        return [dict(item) for item in decisions]

    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        if updated.get("cluster") in stressed_clusters and updated.get("cluster") in RISK_CLUSTERS:
            updated["action_label"] = _downgrade_action(str(updated.get("action_label", "观察")))
            updated["conclusion"] = updated["action_label"]
            updated["operation"] = updated["action_label"]
            updated["plan"] = ACTION_PLANS[updated["action_label"]]
            updated["reason"] = f"{updated['reason']} 板块联动走弱，先把动作降一级。"
        adjusted.append(updated)
    return adjusted


def apply_emergency_retreat_overlay(
    decisions: Sequence[Mapping[str, Any]],
    ai_input: Mapping[str, Any],
    regime_info: Mapping[str, Any],
    benchmark_context: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    stocks_by_code = {
        str(stock.get("code", "") or ""): stock
        for stock in ai_input.get("stocks", []) or []
        if stock.get("code")
    }
    negative_news = _news_score((ai_input.get("macro_news", {}) or {}).get("telegraph", []) or []) < 0
    stressed_clusters = set(regime_info.get("stressed_clusters", set()) or set())
    market_retreat = str(regime_info.get("regime", "均衡")) == "撤退"
    benchmark_snapshot = benchmark_context.get("benchmark_snapshot", {}) or {}

    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        code = str(updated.get("code", "") or "")
        stock = stocks_by_code.get(code, {})
        snapshot = benchmark_snapshot.get(code, {})

        pct_change = float(stock.get("pct_change", 0) or 0)
        bias_pct = float(stock.get("bias_pct", 0) or 0)
        current_price = float(updated.get("current_price", 0) or 0)
        ma20 = float(updated.get("ma20", 0) or 0)
        cluster = updated.get("cluster")
        weak_relative = _is_weak_relative(snapshot.get("relative_return_20"), snapshot.get("relative_return_40"))
        structure_break = ma20 > 0 and current_price < ma20 and (pct_change <= -2 or bias_pct <= -0.03)
        severe_drop = pct_change <= -3.5 or bias_pct <= -0.06 or float(snapshot.get("drawdown_20") or 0) <= -0.12
        cluster_break = cluster in stressed_clusters and cluster in RISK_CLUSTERS

        downgrade_steps = 0
        extra_reasons: List[str] = []

        if market_retreat and cluster_break:
            downgrade_steps = max(downgrade_steps, 1)
            extra_reasons.append("市场进入撤退阶段，高波动方向先按防守处理。")
        if structure_break and weak_relative:
            downgrade_steps = max(downgrade_steps, 1)
            extra_reasons.append("走势破位并且弱于对照基准。")
        if severe_drop and cluster_break:
            downgrade_steps = max(downgrade_steps, 2)
            extra_reasons.append("同类高波动方向一起失守，先把仓位降到低风险。")
        if negative_news and structure_break and weak_relative:
            downgrade_steps = max(downgrade_steps, 2 if market_retreat or cluster_break else 1)
            extra_reasons.append("利空确认后，先按撤退处理。")

        if downgrade_steps > 0:
            updated["action_label"] = _downgrade_action(str(updated.get("action_label", "观察")), steps=downgrade_steps)
            updated["conclusion"] = updated["action_label"]
            updated["operation"] = updated["action_label"]
            updated["plan"] = ACTION_PLANS[updated["action_label"]]
            updated["reason"] = f"{updated['reason']} {' '.join(extra_reasons)}".strip()
            if ma20 > 0 and structure_break:
                updated["risk_line"] = f"反抽不能站回20日线 {ma20:.2f}，且继续弱于对照基准时，就先退出。"
        adjusted.append(updated)

    return adjusted


def build_swing_report(
    ai_input: Mapping[str, Any],
    historical_records: Sequence[Mapping[str, Any]],
    analysis_date: str,
) -> Dict[str, Any]:
    regime_info = classify_market_regime(ai_input, historical_records)
    benchmark_context = build_benchmark_context(ai_input.get("stocks", []) or [], historical_records, analysis_date=analysis_date)
    context = {
        "regime": regime_info["regime"],
        "stressed_clusters": regime_info["stressed_clusters"],
        "benchmark_snapshot": benchmark_context.get("benchmark_snapshot", {}),
    }

    decisions = [score_holding(stock, context) for stock in ai_input.get("stocks", []) or []]
    decisions = apply_cluster_risk_overlay(decisions, regime_info["stressed_clusters"])
    decisions = apply_emergency_retreat_overlay(decisions, ai_input, regime_info, benchmark_context)
    position_output = build_position_plan(decisions, regime_info["regime"])
    snapshot_output = build_current_position_snapshot(
        position_output["actions"],
        ai_input.get("portfolio_state"),
    )
    decisions = snapshot_output["actions"]
    position_plan = dict(position_output["position_plan"])
    position_plan.update(snapshot_output["position_snapshot"])

    ordered_actions = sorted(
        decisions,
        key=lambda item: (ACTION_ORDER.index(item["action_label"]), str(item.get("name", ""))),
    )
    portfolio_actions = {label: [] for label in ACTION_ORDER}
    for decision in ordered_actions:
        portfolio_actions[decision["action_label"]].append(decision)

    technical_evidence = [
        {
            "code": stock.get("code"),
            "name": stock.get("name"),
            "signal": stock.get("signal"),
            "confidence": stock.get("confidence", ""),
            "tech_summary": stock.get("tech_summary", ""),
        }
        for stock in ai_input.get("stocks", []) or []
    ]

    return {
        "mode": "swing",
        "analysis_date": analysis_date,
        "market_regime": regime_info["regime"],
        "market_conclusion": REGIME_CONCLUSIONS[regime_info["regime"]],
        "market_drivers": regime_info["reasons"],
        "position_plan": position_plan,
        "portfolio_actions": portfolio_actions,
        "actions": ordered_actions,
        "technical_evidence": technical_evidence,
    }
