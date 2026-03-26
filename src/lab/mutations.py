from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


CONFIDENCE_ORDER = {
    "低": 1,
    "中": 2,
    "高": 3,
}

DOWNGRADE_MAP = {
    "增配": "持有",
    "持有": "减配",
    "减配": "回避",
    "回避": "回避",
    "观察": "观察",
}


def _confidence_rank(value: str) -> int:
    return CONFIDENCE_ORDER.get(str(value or "").strip(), 0)


def _parse_blocklist(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _degrade_action(action_label: str) -> str:
    return DOWNGRADE_MAP.get(str(action_label or "").strip(), str(action_label or "").strip())


def apply_candidate_mutations(
    actions: Iterable[Mapping[str, Any]],
    *,
    rule_overrides: Mapping[str, Any],
    parameter_overrides: Mapping[str, Any],
    portfolio_overrides: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    _ = parameter_overrides
    _ = portfolio_overrides

    confidence_min = str(rule_overrides.get("confidence_min", "") or "").strip()
    confidence_floor = _confidence_rank(confidence_min) if confidence_min else 0
    blocked_clusters = _parse_blocklist(rule_overrides.get("cluster_blocklist"))
    degrade_holds_in_defense = str(rule_overrides.get("hold_in_defense", "") or "").strip() == "degrade"

    mutated: List[Dict[str, Any]] = []
    for action in actions:
        item = dict(action)
        if blocked_clusters and str(item.get("cluster", "") or "") in blocked_clusters:
            continue
        if confidence_floor and _confidence_rank(str(item.get("confidence", "") or "")) < confidence_floor:
            continue
        if (
            degrade_holds_in_defense
            and str(item.get("market_regime", "") or "") == "防守"
            and str(item.get("action_label", "") or "") == "持有"
        ):
            item["action_label"] = _degrade_action(str(item.get("action_label", "") or ""))
        mutated.append(item)
    return mutated
