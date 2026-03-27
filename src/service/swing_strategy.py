from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from src.processor.swing_tracker import build_price_matrix, calculate_max_drawdown
from src.service.strategy_engine import build_strategy_snapshot
from src.service.watchlist_engine import build_watchlist_candidates


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
    "balanced": {
        "进攻": {"total_exposure": (90, 100), "core": (50, 60), "satellite": (30, 40), "cash": (0, 10)},
        "均衡": {"total_exposure": (65, 80), "core": (40, 50), "satellite": (15, 25), "cash": (20, 35)},
        "防守": {"total_exposure": (35, 55), "core": (20, 35), "satellite": (0, 10), "cash": (45, 65)},
        "撤退": {"total_exposure": (0, 20), "core": (0, 15), "satellite": (0, 0), "cash": (80, 100)},
    },
    "aggressive": {
        "进攻": {"total_exposure": (95, 100), "core": (45, 55), "satellite": (40, 50), "cash": (0, 5)},
        "均衡": {"total_exposure": (75, 90), "core": (35, 45), "satellite": (30, 45), "cash": (10, 25)},
        "防守": {"total_exposure": (45, 65), "core": (25, 35), "satellite": (15, 30), "cash": (35, 55)},
        "撤退": {"total_exposure": (0, 20), "core": (0, 10), "satellite": (0, 10), "cash": (80, 100)},
    },
}
ACTION_WEIGHT_PRIORITY = {"增配": 5, "持有": 4, "观察": 2, "减配": 1, "回避": 0}
SMALL_POSITION_RANGES = {"观察": (0, 5), "减配": (0, 3), "回避": (0, 0)}
DEFAULT_RISK_PROFILE = "balanced"
VALIDATION_MIN_SAMPLE = 5
WEAK_VALIDATION_RELATIVE = -0.02
WEAK_VALIDATION_DRAWDOWN = -0.08
CLUSTER_LABELS = {
    "ai": "人工智能方向",
    "broad_beta": "大盘核心方向",
    "small_cap": "中小盘方向",
    "semiconductor": "半导体方向",
    "precious_metals": "贵金属方向",
    "sector_etf": "行业轮动方向",
    "single_name": "个股方向",
}


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


def _normalize_risk_profile(value: Any) -> str:
    profile = str(value or DEFAULT_RISK_PROFILE).strip().lower()
    if profile in POSITION_TEMPLATES:
        return profile
    return DEFAULT_RISK_PROFILE


def _format_ratio_pct(value: Optional[float], *, fallback_label: str = "平均收益") -> str:
    if value is None:
        return ""
    numeric = float(value)
    if fallback_label == "相对":
        if numeric >= 0:
            return f"平均跑赢基准{numeric * 100:.1f}%"
        return f"平均落后基准{abs(numeric) * 100:.1f}%"
    return f"{fallback_label}{numeric * 100:.1f}%"


def _format_cluster_label(cluster: Any) -> str:
    normalized = str(cluster or "").strip()
    return CLUSTER_LABELS.get(normalized, normalized or "该方向")


def _build_validation_note(
    cluster: str,
    validation_evidence: Mapping[str, Any],
) -> str:
    primary_window = validation_evidence.get("primary_window")
    cluster_stats = validation_evidence.get("cluster") or {}
    if not primary_window or int(cluster_stats.get("sample_count", 0) or 0) <= 0:
        return ""

    relative_text = _format_ratio_pct(cluster_stats.get("avg_relative_return"), fallback_label="相对")
    if not relative_text:
        relative_text = _format_ratio_pct(cluster_stats.get("avg_absolute_return"), fallback_label="平均收益")
    drawdown = abs(float(cluster_stats.get("avg_max_drawdown", 0.0) or 0.0)) * 100
    cluster_label = _format_cluster_label(cluster)
    if _is_weak_validation_stats(cluster_stats):
        return (
            f"{cluster_label}的{int(primary_window)}日验证偏弱，样本"
            f"{int(cluster_stats.get('sample_count', 0) or 0)}笔，{relative_text}，回撤约{drawdown:.1f}%。"
        )
    return (
        f"{int(primary_window)}日验证里，{cluster_label}样本"
        f"{int(cluster_stats.get('sample_count', 0) or 0)}笔，{relative_text}，回撤约{drawdown:.1f}%。"
    )


def _is_weak_validation_stats(stats: Optional[Mapping[str, Any]]) -> bool:
    if not stats:
        return False
    sample_count = int(stats.get("sample_count", 0) or 0)
    avg_relative = stats.get("avg_relative_return")
    avg_drawdown = float(stats.get("avg_max_drawdown", 0.0) or 0.0)
    return sample_count >= VALIDATION_MIN_SAMPLE and (
        (avg_relative is not None and float(avg_relative) <= WEAK_VALIDATION_RELATIVE)
        or avg_drawdown <= WEAK_VALIDATION_DRAWDOWN
    )


def _attach_validation_evidence(
    decisions: Sequence[Mapping[str, Any]],
    *,
    decision_evidence: Optional[Mapping[str, Any]],
    market_regime: str,
) -> List[Dict[str, Any]]:
    evidence_root = dict(decision_evidence or {})
    enriched: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        cluster = str(updated.get("cluster", "") or "")
        action_label = str(updated.get("action_label", "") or "")
        evidence = {
            "primary_window": evidence_root.get("primary_window"),
            "action": dict(((evidence_root.get("action") or {}).get(action_label)) or {}),
            "cluster": dict(((evidence_root.get("cluster") or {}).get(cluster)) or {}),
            "regime": dict(((evidence_root.get("regime") or {}).get(market_regime)) or {}),
        }
        updated["validation_evidence"] = evidence
        note = _build_validation_note(cluster, evidence)
        if note:
            updated["validation_note"] = note
        enriched.append(updated)
    return enriched


def _apply_validation_evidence_overlay(
    decisions: Sequence[Mapping[str, Any]],
    *,
    decision_evidence: Optional[Mapping[str, Any]],
    market_regime: str,
) -> List[Dict[str, Any]]:
    evidence_root = dict(decision_evidence or {})
    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        action_label = str(updated.get("action_label", "观察") or "观察")
        if action_label not in {"增配", "持有"}:
            adjusted.append(updated)
            continue

        cluster = str(updated.get("cluster", "") or "")
        cluster_stats = ((evidence_root.get("cluster") or {}).get(cluster)) or {}
        regime_stats = ((evidence_root.get("regime") or {}).get(market_regime)) or {}
        action_stats = ((evidence_root.get("action") or {}).get(action_label)) or {}

        if _is_weak_validation_stats(cluster_stats) and not _is_weak_validation_stats(regime_stats):
            downgraded = _downgrade_action(action_label)
            if downgraded != action_label:
                updated["action_label"] = downgraded
                updated["conclusion"] = downgraded
                updated["operation"] = downgraded
                updated["plan"] = ACTION_PLANS[downgraded]
            reason_suffix = "历史验证偏弱，先降一档处理。"
            updated["reason"] = f"{updated.get('reason', '').strip()} {reason_suffix}".strip()
        elif _is_weak_validation_stats(action_stats) and action_label == "增配":
            downgraded = _downgrade_action(action_label)
            if downgraded != action_label:
                updated["action_label"] = downgraded
                updated["conclusion"] = downgraded
                updated["operation"] = downgraded
                updated["plan"] = ACTION_PLANS[downgraded]
                updated["reason"] = f"{updated.get('reason', '').strip()} 历史验证对主动进攻支持不足，先按持有处理。".strip()

        adjusted.append(updated)
    return adjusted


def _resolve_risk_profile(strategy_preferences: Optional[Mapping[str, Any]]) -> str:
    preferences = dict(strategy_preferences or {})
    return _normalize_risk_profile(preferences.get("risk_profile"))


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


def _fixed_position_range(decision: Mapping[str, Any]) -> Optional[Sequence[int]]:
    action_label = str(decision.get("action_label", "观察"))
    signal = str(decision.get("signal", "")).upper()
    shares = int(decision.get("shares", 0) or 0)

    if action_label == "回避":
        return 0, 0
    if action_label == "减配":
        return (0, 0) if shares <= 0 else SMALL_POSITION_RANGES["减配"]
    if action_label == "持有" and signal in {"WATCH", "OBSERVED", "OVERBOUGHT"} and shares <= 0:
        return SMALL_POSITION_RANGES["观察"]
    return None


def _allocate_bucket_ranges(
    decisions: Sequence[Mapping[str, Any]],
    target_range: Sequence[int],
) -> Dict[str, Dict[str, int]]:
    allocations: Dict[str, Dict[str, int]] = {}
    if not decisions:
        return allocations

    fixed_items = [item for item in decisions if _fixed_position_range(item) is not None]
    strong_items = [item for item in decisions if _fixed_position_range(item) is None]

    fixed_min = 0
    fixed_max = 0
    for item in fixed_items:
        min_weight, max_weight = _fixed_position_range(item) or (0, 0)
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


def _cap_target_weight(weight: str, cap_max: int) -> str:
    _, current_max = _parse_pct_range(weight)
    return _format_pct_range(0, min(current_max, cap_max))


def _validation_cap_max(
    *,
    action_label: str,
    cluster: str,
    cluster_stats: Optional[Mapping[str, Any]],
    decision_evidence: Optional[Mapping[str, Any]],
) -> Optional[int]:
    evidence_root = dict(decision_evidence or {})
    if action_label == "增配" and evidence_root.get("offensive_allowed") is False:
        return 5

    if not _is_weak_validation_stats(cluster_stats):
        return None

    avg_relative = cluster_stats.get("avg_relative_return") if cluster_stats else None
    avg_drawdown = float((cluster_stats or {}).get("avg_max_drawdown", 0.0) or 0.0)
    severe = (
        (avg_relative is not None and float(avg_relative) <= -0.04)
        or avg_drawdown <= -0.10
    )
    if severe:
        return 5
    return 10 if cluster in RISK_CLUSTERS or cluster == "single_name" else 15


def _cluster_budget_status(
    *,
    cluster: str,
    cluster_stats: Optional[Mapping[str, Any]],
    decision_evidence: Optional[Mapping[str, Any]],
) -> tuple[str, str]:
    evidence_root = dict(decision_evidence or {})
    primary_window = evidence_root.get("primary_window")
    if evidence_root.get("offensive_allowed") is False:
        reason = str(evidence_root.get("offensive_reason", "验证暂不支持主动进攻") or "验证暂不支持主动进攻")
        return "仅观察", f"当前全局进攻权限关闭：{reason}。"

    if not _is_weak_validation_stats(cluster_stats):
        window_text = f"{int(primary_window)}日验证稳定" if primary_window else "验证稳定"
        return "正常", f"{window_text}，当前不额外压缩。"

    avg_relative = cluster_stats.get("avg_relative_return") if cluster_stats else None
    avg_drawdown = float((cluster_stats or {}).get("avg_max_drawdown", 0.0) or 0.0)
    severe = (
        (avg_relative is not None and float(avg_relative) <= -0.04)
        or avg_drawdown <= -0.10
    )
    window_text = f"{int(primary_window)}日验证偏弱" if primary_window else "验证偏弱"
    if severe:
        return "严格限制", f"{window_text}且回撤过大，先压到最低风险预算。"
    return "受限", f"{window_text}，先只保留试仓级预算。"


def _build_validation_budgets(
    actions: Sequence[Mapping[str, Any]],
    *,
    decision_evidence: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for item in actions:
        cluster = str(item.get("cluster", "") or "")
        if not cluster:
            continue
        grouped.setdefault(cluster, []).append(item)

    budgets: List[Dict[str, Any]] = []
    for cluster, items in grouped.items():
        cluster_label = _format_cluster_label(cluster)
        summary = _summarize_bucket_ranges(items)
        budget_range = _format_pct_range(summary["min"], summary["max"])
        cluster_stats = ((decision_evidence or {}).get("cluster") or {}).get(cluster) or {}
        status, reason = _cluster_budget_status(
            cluster=cluster,
            cluster_stats=cluster_stats,
            decision_evidence=decision_evidence,
        )
        budgets.append(
            {
                "cluster": cluster,
                "label": cluster_label,
                "budget_range": budget_range,
                "status": status,
                "reason": reason,
            }
        )

    budgets.sort(
        key=lambda item: (
            {"严格限制": 0, "仅观察": 1, "受限": 2, "正常": 3}.get(str(item.get("status", "")), 9),
            str(item.get("label", "")),
        )
    )
    return budgets


def _apply_validation_position_caps(
    actions: Sequence[Mapping[str, Any]],
    position_plan: Mapping[str, Any],
    *,
    decision_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    updated_actions: List[Dict[str, Any]] = []
    for item in actions:
        updated = dict(item)
        cluster_stats = ((updated.get("validation_evidence") or {}).get("cluster")) or {}
        action_label = str(updated.get("action_label", "") or "")
        cluster = str(updated.get("cluster", "") or "")
        cap_max = _validation_cap_max(
            action_label=action_label,
            cluster=cluster,
            cluster_stats=cluster_stats,
            decision_evidence=decision_evidence,
        )
        if action_label in {"增配", "持有"} and cap_max is not None:
            updated["target_weight"] = _cap_target_weight(str(updated.get("target_weight", "0%")), cap_max)
        updated_actions.append(updated)

    buckets = {"核心仓": [], "卫星仓": [], "现金": []}
    for item in updated_actions:
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

    updated_plan = dict(position_plan)
    updated_plan["core_target"] = _format_pct_range(core_summary["min"], core_summary["max"])
    updated_plan["satellite_target"] = _format_pct_range(satellite_summary["min"], satellite_summary["max"])
    updated_plan["total_exposure"] = _format_pct_range(total_summary["min"], total_summary["max"])
    updated_plan["cash_target"] = _format_pct_range(cash_summary["min"], cash_summary["max"])
    updated_plan["buckets"] = buckets
    updated_plan["validation_budgets"] = _build_validation_budgets(
        updated_actions,
        decision_evidence=decision_evidence,
    )
    return {"actions": updated_actions, "position_plan": updated_plan}


def build_position_plan(
    decisions: Sequence[Mapping[str, Any]],
    regime: str,
    risk_profile: str = DEFAULT_RISK_PROFILE,
) -> Dict[str, Any]:
    profile_templates = POSITION_TEMPLATES.get(
        _normalize_risk_profile(risk_profile),
        POSITION_TEMPLATES[DEFAULT_RISK_PROFILE],
    )
    template = profile_templates.get(regime, profile_templates["均衡"])
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
            "risk_profile": _normalize_risk_profile(risk_profile),
            "total_exposure": _format_pct_range(total_summary["min"], total_summary["max"]),
            "core_target": _format_pct_range(core_summary["min"], core_summary["max"]),
            "satellite_target": _format_pct_range(satellite_summary["min"], satellite_summary["max"]),
            "cash_target": _format_pct_range(cash_summary["min"], cash_summary["max"]),
            "regime_total_exposure": _format_pct_range(*template["total_exposure"]),
            "regime_core_target": _format_pct_range(*template["core"]),
            "regime_satellite_target": _format_pct_range(*template["satellite"]),
            "regime_cash_target": _format_pct_range(*template["cash"]),
            "weekly_rebalance": "每周五收盘后生成计划，下一交易日分批执行。",
            "daily_rule": "下一交易日按优先级分批执行，先减弱势仓，再处理持有仓，最后考虑新增仓。",
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
            action_label = str(updated.get("action_label", "持有"))
            if action_label == "增配" and target_max_pct > 0:
                updated["rebalance_action"] = "暂无持仓，下一交易日满足条件后再试仓"
            elif action_label == "持有" and target_max_pct > 0:
                updated["rebalance_action"] = "暂无持仓，列入候选，等下一交易日继续转强再试仓"
            else:
                updated["rebalance_action"] = "暂无持仓，不在执行清单"
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


def _label_from_score(score: int, risk_profile: str = DEFAULT_RISK_PROFILE) -> str:
    profile = _normalize_risk_profile(risk_profile)
    if profile == "aggressive":
        if score >= 4:
            return "增配"
        if score >= -1:
            return "持有"
        if score >= -4:
            return "观察"
        if score <= -8:
            return "回避"
        return "减配"

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


def _apply_profile_score_adjustments(
    score: int,
    *,
    risk_profile: str,
    regime: str,
    signal: str,
    cluster: str,
    stressed_clusters: Set[str],
    current_price: float,
    ma20: float,
    pct_change: float,
    relative_return_20: Optional[float],
    relative_return_40: Optional[float],
    drawdown_20: Optional[float],
) -> int:
    profile = _normalize_risk_profile(risk_profile)
    if profile != "aggressive" or regime == "撤退":
        return score

    adjusted = score
    weak_relative = _is_weak_relative(relative_return_20, relative_return_40)
    strong_relative = _is_strong_relative(relative_return_20, relative_return_40)
    rebound_attempt = ma20 > 0 and current_price < ma20 and pct_change >= 0

    if signal == "DANGER":
        adjusted += 1
    if cluster == "broad_beta":
        adjusted += 2
        if not weak_relative:
            adjusted += 1
    if strong_relative:
        adjusted += 1
    if rebound_attempt:
        adjusted += 1
    if cluster in stressed_clusters and cluster in RISK_CLUSTERS and not weak_relative:
        adjusted += 1
    if isinstance(drawdown_20, (int, float)) and drawdown_20 <= -0.12 and not weak_relative:
        adjusted += 1

    return adjusted


def _cluster_strength_key(item: Mapping[str, Any]) -> tuple:
    relative_20 = item.get("relative_return_20")
    relative_40 = item.get("relative_return_40")
    return (
        int(item.get("score", 0) or 0),
        float(relative_20) if isinstance(relative_20, (int, float)) else float("-inf"),
        float(relative_40) if isinstance(relative_40, (int, float)) else float("-inf"),
    )


def _select_cluster_leaders(decisions: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    leaders: Dict[str, str] = {}
    for item in decisions:
        cluster = str(item.get("cluster", "") or "")
        code = str(item.get("code", "") or "")
        if not cluster or not code:
            continue
        current_code = leaders.get(cluster)
        if current_code is None:
            leaders[cluster] = code
            continue
        current_item = next((candidate for candidate in decisions if str(candidate.get("code", "")) == current_code), None)
        if current_item is None or _cluster_strength_key(item) > _cluster_strength_key(current_item):
            leaders[cluster] = code
    return leaders


def _should_preserve_aggressive_exposure(
    item: Mapping[str, Any],
    cluster_leaders: Mapping[str, str],
) -> bool:
    cluster = str(item.get("cluster", "") or "")
    code = str(item.get("code", "") or "")
    relative_return_20 = item.get("relative_return_20")
    relative_return_40 = item.get("relative_return_40")

    if _is_weak_relative(relative_return_20, relative_return_40):
        return False
    if cluster == "broad_beta":
        return True
    if _is_strong_relative(relative_return_20, relative_return_40):
        return True
    return cluster_leaders.get(cluster) == code


def score_holding(stock: Mapping[str, Any], benchmark_context: Mapping[str, Any]) -> Dict[str, Any]:
    signal = str(stock.get("signal", "SAFE")).upper()
    code = str(stock.get("code", "") or "")
    cluster = infer_cluster(stock)
    regime = str(benchmark_context.get("regime", "均衡"))
    risk_profile = _normalize_risk_profile(benchmark_context.get("risk_profile"))
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

    score = _apply_profile_score_adjustments(
        score,
        risk_profile=risk_profile,
        regime=regime,
        signal=signal,
        cluster=cluster,
        stressed_clusters=stressed_clusters,
        current_price=current_price,
        ma20=ma20,
        pct_change=pct_change,
        relative_return_20=relative_return_20,
        relative_return_40=relative_return_40,
        drawdown_20=drawdown_20,
    )

    action_label = _label_from_score(score, risk_profile=risk_profile)

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
    risk_profile: str = DEFAULT_RISK_PROFILE,
    regime: str = "均衡",
) -> List[Dict[str, Any]]:
    if len(stressed_clusters & RISK_CLUSTERS) < 2:
        return [dict(item) for item in decisions]

    profile = _normalize_risk_profile(risk_profile)
    cluster_leaders = _select_cluster_leaders(decisions) if profile == "aggressive" and regime != "撤退" else {}
    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        if updated.get("cluster") in stressed_clusters and updated.get("cluster") in RISK_CLUSTERS:
            if profile == "aggressive" and _should_preserve_aggressive_exposure(updated, cluster_leaders):
                adjusted.append(updated)
                continue
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
    risk_profile: str = DEFAULT_RISK_PROFILE,
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
    profile = _normalize_risk_profile(risk_profile)
    cluster_leaders = _select_cluster_leaders(decisions) if profile == "aggressive" and not market_retreat else {}

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
        protected_aggressive_leader = (
            profile == "aggressive"
            and not market_retreat
            and _should_preserve_aggressive_exposure(updated, cluster_leaders)
        )

        downgrade_steps = 0
        extra_reasons: List[str] = []

        if market_retreat and cluster_break:
            downgrade_steps = max(downgrade_steps, 1)
            extra_reasons.append("市场进入撤退阶段，高波动方向先按防守处理。")
        if structure_break and weak_relative:
            downgrade_steps = max(downgrade_steps, 1)
            extra_reasons.append("走势破位并且弱于对照基准。")
        if severe_drop and cluster_break:
            if market_retreat:
                downgrade_steps = max(downgrade_steps, 2)
                extra_reasons.append("同类高波动方向一起失守，先把仓位降到低风险。")
            elif profile == "aggressive":
                if weak_relative or not protected_aggressive_leader:
                    downgrade_steps = max(downgrade_steps, 1)
                    extra_reasons.append("高波动方向同步走弱，先收一档仓位。")
            else:
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


def _normalize_swing_reason(reason: str) -> str:
    text = str(reason or "")
    text = text.replace("相对基准更强", "强于对照基准")
    text = text.replace("相对基准偏弱", "弱于对照基准")
    return text


def _apply_aggressive_hold_overlay(
    decisions: Sequence[Mapping[str, Any]],
    *,
    regime: str,
    stock_map: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if regime == "撤退":
        return [dict(item) for item in decisions]

    cluster_leaders = _select_cluster_leaders(decisions)
    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        if str(updated.get("action_label", "持有")) != "减配":
            adjusted.append(updated)
            continue

        code = str(updated.get("code", "") or "")
        stock = stock_map.get(code, {})
        cluster = str(updated.get("cluster", "") or "")
        relative_20 = updated.get("relative_return_20")
        relative_40 = updated.get("relative_return_40")
        weak_relative = _is_weak_relative(relative_20, relative_40)
        strong_relative = _is_strong_relative(relative_20, relative_40)
        current_price = float(updated.get("current_price", 0) or 0)
        ma20 = float(updated.get("ma20", 0) or 0)
        pct_change = float(stock.get("pct_change", 0) or 0)

        preserve_core = cluster == "broad_beta" and not weak_relative and pct_change >= 0
        preserve_leader = strong_relative and cluster_leaders.get(cluster) == code and pct_change >= 0
        mild_break = ma20 > 0 and current_price < ma20 and (ma20 - current_price) / ma20 <= 0.08

        if mild_break and (preserve_core or preserve_leader):
            updated["action_label"] = "持有"
            updated["conclusion"] = "持有"
            updated["operation"] = "持有"
            updated["plan"] = "先把现有仓位拿住，只保留相对更强的一档主仓。"
            updated["reason"] = f"{updated['reason']} 激进模式下先保留相对更强的一档主仓。".strip()

        adjusted.append(updated)

    return adjusted


def _apply_weakness_overlay(
    decisions: Sequence[Mapping[str, Any]],
    *,
    stock_map: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    adjusted: List[Dict[str, Any]] = []
    for item in decisions:
        updated = dict(item)
        if str(updated.get("action_label", "持有")) != "持有":
            adjusted.append(updated)
            continue

        code = str(updated.get("code", "") or "")
        stock = stock_map.get(code, {})
        signal = str(updated.get("signal", "")).upper()
        current_price = float(updated.get("current_price", 0) or 0)
        ma20 = float(updated.get("ma20", 0) or 0)
        weak_relative = _is_weak_relative(updated.get("relative_return_20"), updated.get("relative_return_40"))

        should_reduce = False
        extra_reason = ""
        if ma20 > 0 and current_price < ma20 and weak_relative:
            should_reduce = True
            extra_reason = "已经弱于对照基准，先降一档处理。"
        elif ma20 > 0 and current_price < ma20 and signal in {"WARNING", "DANGER", "LOCKED_DANGER"}:
            should_reduce = True
            extra_reason = "价格回到MA20下方，先把仓位收一档。"

        if should_reduce:
            updated["action_label"] = "减配"
            updated["conclusion"] = "减配"
            updated["operation"] = "减配"
            updated["plan"] = ACTION_PLANS["减配"]
            updated["reason"] = f"{updated['reason']} {extra_reason}".strip()

        adjusted.append(updated)

    return adjusted


def build_swing_report(
    ai_input: Mapping[str, Any],
    historical_records: Sequence[Mapping[str, Any]],
    analysis_date: str,
) -> Dict[str, Any]:
    risk_profile = _resolve_risk_profile(ai_input.get("strategy_preferences"))
    benchmark_context = build_benchmark_context(
        ai_input.get("stocks", []) or [],
        historical_records,
        analysis_date=analysis_date,
    )
    strategy_snapshot = build_strategy_snapshot(
        ai_input,
        historical_records,
        mode="swing",
        performance_context=ai_input.get("performance_context"),
    )
    stock_map = {
        str(stock.get("code", "") or ""): stock
        for stock in ai_input.get("stocks", []) or []
        if stock.get("code")
    }
    held_codes = {str(code) for code in (ai_input.get("held_codes") or set())}
    watchlist_codes = {str(code) for code in (ai_input.get("watchlist_codes") or set())}
    decision_evidence = ((ai_input.get("validation_report") or {}).get("decision_evidence") or {})
    decisions = []
    watchlist_holdings = []
    for holding in strategy_snapshot.get("holdings", []):
        code = str(holding.get("code", "") or "")
        if watchlist_codes and code in watchlist_codes and code not in held_codes:
            watchlist_holdings.append(holding)
            continue
        decision = {
            "code": code,
            "name": holding.get("name"),
            "cluster": holding.get("cluster"),
            "signal": holding.get("signal"),
            "score": 0,
            "confidence": holding.get("confidence", ""),
            "action_label": holding.get("final_action", "持有"),
            "conclusion": holding.get("final_action", "持有"),
            "operation": holding.get("final_action", "持有"),
            "reason": _normalize_swing_reason(holding.get("evidence_text", "")),
            "plan": holding.get("rebalance_instruction", ""),
            "risk_line": holding.get("invalid_condition", ""),
            "technical_evidence": holding.get("tech_summary", ""),
            "current_price": holding.get("current_price", 0.0),
            "ma20": holding.get("ma20", 0.0),
            "shares": int(holding.get("shares", 0) or 0),
            "relative_return_20": holding.get("relative_return_20"),
            "relative_return_40": holding.get("relative_return_40"),
            "drawdown_20": holding.get("drawdown_20"),
            "setup_type": holding.get("setup_type"),
            "execution_window": holding.get("execution_window"),
        }
        decisions.append(decision)

    regime_info = {
        "regime": strategy_snapshot["market_regime"],
        "stressed_clusters": set(strategy_snapshot.get("stressed_clusters", []) or []),
    }
    decisions = _apply_weakness_overlay(decisions, stock_map=stock_map)
    decisions = apply_cluster_risk_overlay(
        decisions,
        stressed_clusters=set(strategy_snapshot.get("stressed_clusters", []) or []),
        risk_profile=risk_profile,
        regime=strategy_snapshot["market_regime"],
    )
    decisions = apply_emergency_retreat_overlay(
        decisions,
        ai_input,
        regime_info,
        benchmark_context,
        risk_profile=risk_profile,
    )
    decisions = _apply_validation_evidence_overlay(
        decisions,
        decision_evidence=decision_evidence,
        market_regime=strategy_snapshot["market_regime"],
    )
    for decision in decisions:
        if str(decision.get("action_label", "")) != "观察":
            continue
        signal = str(decision.get("signal", "")).upper()
        collapsed_action = "减配" if signal in {"WARNING", "DANGER", "LOCKED_DANGER", "LIMIT_DOWN"} else "持有"
        decision["action_label"] = collapsed_action
        decision["conclusion"] = collapsed_action
        decision["operation"] = collapsed_action
        decision["plan"] = ACTION_PLANS[collapsed_action]
    if risk_profile == "aggressive":
        decisions = _apply_aggressive_hold_overlay(
            decisions,
            regime=strategy_snapshot["market_regime"],
            stock_map=stock_map,
        )
    decisions = _attach_validation_evidence(
        decisions,
        decision_evidence=decision_evidence,
        market_regime=strategy_snapshot["market_regime"],
    )

    position_output = build_position_plan(decisions, strategy_snapshot["market_regime"], risk_profile=risk_profile)
    position_output = _apply_validation_position_caps(
        position_output["actions"],
        position_output["position_plan"],
        decision_evidence=decision_evidence,
    )
    snapshot_output = build_current_position_snapshot(
        position_output["actions"],
        ai_input.get("portfolio_state"),
    )
    decisions = snapshot_output["actions"]
    for decision in decisions:
        if int(decision.get("current_shares", 0) or 0) <= 0 and decision.get("action_label") == "持有":
            decision["plan"] = "暂无持仓，先列入候选，等下一交易日确认后再考虑建立试仓。"
    position_plan = dict(position_output["position_plan"])
    position_plan.update(snapshot_output["position_snapshot"])
    execution_order = [
        f"{item.get('name')}:{item.get('rebalance_action')}"
        for item in decisions
        if item.get("action_label") in {"回避", "减配", "增配"}
    ]
    if execution_order:
        position_plan["execution_order"] = execution_order

    ordered_actions = sorted(
        decisions,
        key=lambda item: (ACTION_ORDER.index(item["action_label"]), str(item.get("name", ""))),
    )
    portfolio_actions = {label: [] for label in ("增配", "持有", "减配", "回避")}
    for decision in ordered_actions:
        portfolio_actions.setdefault(decision["action_label"], []).append(decision)

    watchlist_output = build_watchlist_candidates(
        watchlist_holdings,
        held_codes=held_codes,
        watchlist_codes=watchlist_codes,
        strategy_preferences=ai_input.get("strategy_preferences", {}),
        market_regime=strategy_snapshot["market_regime"],
        decision_evidence=decision_evidence,
    )

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
        "market_regime": strategy_snapshot["market_regime"],
        "market_conclusion": REGIME_CONCLUSIONS[strategy_snapshot["market_regime"]],
        "market_drivers": strategy_snapshot["market_drivers"],
        "position_plan": position_plan,
        "portfolio_actions": portfolio_actions,
        "actions": ordered_actions,
        "watchlist_actions": watchlist_output["action_buckets"],
        "watchlist_candidates": watchlist_output["active_candidates"],
        "validation_summary": ((ai_input.get("validation_report") or {}).get("summary_text") or ""),
        "technical_evidence": technical_evidence,
        "strategy_snapshot": strategy_snapshot,
    }
