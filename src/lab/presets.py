from __future__ import annotations

from typing import Any, Dict


LAB_PRESETS: Dict[str, Dict[str, Any]] = {
    "aggressive_midterm": {
        "name": "aggressive_midterm",
        "description": "Aggressive mid-term baseline candidate for broad swing allocation.",
        "rule_overrides": {},
        "parameter_overrides": {},
        "portfolio_overrides": {},
    },
    "defensive_exit_fix": {
        "name": "defensive_exit_fix",
        "description": "Reduce slow exits by downgrading hold actions during defensive regimes.",
        "rule_overrides": {"hold_in_defense": "degrade"},
        "parameter_overrides": {},
        "portfolio_overrides": {},
    },
    "high_conf_only": {
        "name": "high_conf_only",
        "description": "Keep only high-confidence offensive actions.",
        "rule_overrides": {"confidence_min": "高"},
        "parameter_overrides": {},
        "portfolio_overrides": {},
    },
    "broad_beta_core": {
        "name": "broad_beta_core",
        "description": "Keep broad beta as the portfolio core and reduce noisy satellite exposure.",
        "rule_overrides": {},
        "parameter_overrides": {},
        "portfolio_overrides": {"core_only": "broad_beta"},
    },
    "risk_cluster_filter": {
        "name": "risk_cluster_filter",
        "description": "Filter out selected high-volatility clusters from the candidate portfolio.",
        "rule_overrides": {"cluster_blocklist": "small_cap,ai,semiconductor"},
        "parameter_overrides": {},
        "portfolio_overrides": {},
    },
}


def resolve_lab_preset(name: str) -> Dict[str, Any]:
    key = str(name or "").strip()
    preset = LAB_PRESETS.get(key)
    if preset is None:
        raise ValueError(f"unknown preset: {key}")
    return {
        "name": preset["name"],
        "description": preset["description"],
        "rule_overrides": dict(preset.get("rule_overrides") or {}),
        "parameter_overrides": dict(preset.get("parameter_overrides") or {}),
        "portfolio_overrides": dict(preset.get("portfolio_overrides") or {}),
    }
