from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.lab.models import LabRequest, LabResult
from src.lab.mutations import apply_candidate_mutations
from src.lab.presets import resolve_lab_preset
from src.service.validation_service import ValidationService


class StrategyLabService:
    def __init__(
        self,
        db: Any,
        config: Optional[Dict[str, Any]] = None,
        validation_service: Optional[ValidationService] = None,
    ):
        self.db = db
        self.config = config or {}
        self.validation_service = validation_service or ValidationService(db, self.config)

    def _merge_overrides(self, preset: Dict[str, Any], override_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        rule_overrides = dict(preset.get("rule_overrides") or {})
        parameter_overrides = dict(preset.get("parameter_overrides") or {})
        portfolio_overrides = dict(preset.get("portfolio_overrides") or {})
        for key, value in (override_map or {}).items():
            if key in {"hold_in_defense", "confidence_min", "cluster_blocklist"}:
                rule_overrides[key] = value
            elif key in {"lookback_window", "drawdown_limit"}:
                parameter_overrides[key] = value
            elif key in {"core_only", "watchlist_limit"}:
                portfolio_overrides[key] = value
            else:
                rule_overrides[key] = value
        return {
            "rule_overrides": rule_overrides,
            "parameter_overrides": parameter_overrides,
            "portfolio_overrides": portfolio_overrides,
        }

    def _build_candidate_synthetic_records(
        self,
        synthetic_records: List[Dict[str, Any]],
        *,
        rule_overrides: Dict[str, Any],
        parameter_overrides: Dict[str, Any],
        portfolio_overrides: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        mutated_records: List[Dict[str, Any]] = []
        for record in synthetic_records:
            updated = deepcopy(record)
            ai_result = dict(updated.get("ai_result") or {})
            ai_result["actions"] = apply_candidate_mutations(
                ai_result.get("actions") or [],
                rule_overrides=rule_overrides,
                parameter_overrides=parameter_overrides,
                portfolio_overrides=portfolio_overrides,
            )
            updated["ai_result"] = ai_result
            mutated_records.append(updated)
        return mutated_records

    def _build_variant_reports(self, request: LabRequest) -> Dict[str, Dict[str, Any]]:
        preset = resolve_lab_preset(request.preset)
        merged_overrides = self._merge_overrides(preset, request.override_map)
        historical_records = self.validation_service._get_swing_history_records(
            days=request.days or 90,
            date_from=request.date_from,
            date_to=request.date_to,
            codes=request.codes,
        )
        baseline_synthetic_records = self.validation_service._build_synthetic_swing_records(historical_records)
        candidate_synthetic_records = self._build_candidate_synthetic_records(
            baseline_synthetic_records,
            rule_overrides=merged_overrides["rule_overrides"],
            parameter_overrides=merged_overrides["parameter_overrides"],
            portfolio_overrides=merged_overrides["portfolio_overrides"],
        )
        baseline = self.validation_service._build_validation_report_from_synthetic_records(
            historical_records=historical_records,
            synthetic_records=baseline_synthetic_records,
            group_by=request.group_by,
        )
        candidate = self.validation_service._build_validation_report_from_synthetic_records(
            historical_records=historical_records,
            synthetic_records=candidate_synthetic_records,
            group_by=request.group_by,
        )
        candidate["preset"] = preset
        candidate["applied_overrides"] = merged_overrides
        return {
            "baseline": baseline,
            "candidate": candidate,
        }

    def _build_summary_text(
        self,
        *,
        winner: str,
        diff: Dict[str, Any],
    ) -> str:
        subject = "candidate" if winner == "candidate" else "baseline"
        return (
            f"{subject} 更优；"
            f"回测收益变化{float(diff.get('total_return_delta', 0.0) or 0.0) * 100:.1f}%，"
            f"最大回撤变化{float(diff.get('max_drawdown_delta', 0.0) or 0.0) * 100:.1f}%，"
            f"交易笔数变化{int(diff.get('trade_count_delta', 0) or 0)}。"
        )

    def build_lab_result(
        self,
        *,
        mode: str,
        preset: str,
        days: int = 90,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        codes: Optional[List[str]] = None,
        group_by: Optional[str] = None,
        scoring_mode: str = "composite",
        overrides: Optional[List[str]] = None,
    ) -> LabResult:
        request = LabRequest(
            mode=mode,
            preset=preset,
            days=days,
            date_from=date_from,
            date_to=date_to,
            codes=codes or [],
            group_by=group_by,
            scoring_mode=scoring_mode,
            overrides=overrides or [],
        )
        variant_reports = self._build_variant_reports(request)
        baseline = variant_reports["baseline"]
        candidate = variant_reports["candidate"]
        diff = self.validation_service._build_comparison_diff(baseline=baseline, candidate=candidate)
        diff["baseline_score"] = self.validation_service._score_validation_report(baseline, request.scoring_mode)
        diff["candidate_score"] = self.validation_service._score_validation_report(candidate, request.scoring_mode)
        diff["diagnostic_shift"] = {
            "baseline_top_drag": (((baseline.get("diagnostics") or {}).get("top_drag") or {}).get("key")),
            "candidate_top_drag": (((candidate.get("diagnostics") or {}).get("top_drag") or {}).get("key")),
        }
        winner = "candidate" if diff["candidate_score"] > diff["baseline_score"] else "baseline"
        return LabResult(
            mode=request.mode,
            preset=request.preset,
            baseline=baseline,
            candidate=candidate,
            diff=diff,
            winner=winner,
            summary_text=self._build_summary_text(winner=winner, diff=diff),
        )
