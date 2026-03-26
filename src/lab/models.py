from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _normalize_overrides(overrides: Optional[List[Optional[str]]]) -> List[str]:
    normalized: List[str] = []
    for item in overrides or []:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _parse_override_map(overrides: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in overrides:
        if "=" not in item:
            mapping[item] = ""
            continue
        key, value = item.split("=", 1)
        mapping[key.strip()] = value.strip()
    return mapping


@dataclass(slots=True)
class LabRequest:
    mode: str
    preset: str
    days: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    codes: List[str] = field(default_factory=list)
    group_by: Optional[str] = None
    scoring_mode: str = "composite"
    overrides: List[str] = field(default_factory=list)
    override_map: Dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.mode = str(self.mode or "").strip()
        self.preset = str(self.preset or "").strip()
        self.date_from = str(self.date_from).strip() if self.date_from else None
        self.date_to = str(self.date_to).strip() if self.date_to else None
        self.codes = [str(code).strip() for code in (self.codes or []) if str(code or "").strip()]
        self.group_by = str(self.group_by).strip() if self.group_by else None
        self.scoring_mode = str(self.scoring_mode or "composite").strip() or "composite"
        self.overrides = _normalize_overrides(self.overrides)
        self.override_map = _parse_override_map(self.overrides)
        if self.days is not None:
            self.days = int(self.days)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "preset": self.preset,
            "days": self.days,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "codes": list(self.codes),
            "group_by": self.group_by,
            "scoring_mode": self.scoring_mode,
            "overrides": list(self.overrides),
            "override_map": dict(self.override_map),
        }


@dataclass(slots=True)
class LabResult:
    mode: str
    preset: str
    baseline: Dict[str, Any]
    candidate: Dict[str, Any]
    diff: Dict[str, Any]
    winner: str
    summary_text: str

    def _metric(self, report: Dict[str, Any], *path: str, default: Any = None) -> Any:
        current: Any = report
        for key in path:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
            if current is None:
                return default
        return current

    def _build_compact_payload(self) -> Dict[str, Any]:
        baseline_trade_count = int(
            self._metric(self.baseline, "compact", "backtest_trade_count", default=self._metric(self.baseline, "backtest", "trade_count", default=0)) or 0
        )
        candidate_trade_count = int(
            self._metric(self.candidate, "compact", "backtest_trade_count", default=self._metric(self.candidate, "backtest", "trade_count", default=0)) or 0
        )
        summary = {
            "mode": self.mode,
            "preset": self.preset,
            "winner": self.winner,
            "summary_text": self.summary_text,
            "baseline_score": float(self.diff.get("baseline_score", 0.0) or 0.0),
            "candidate_score": float(self.diff.get("candidate_score", 0.0) or 0.0),
            "baseline_trade_count": baseline_trade_count,
            "candidate_trade_count": candidate_trade_count,
            "total_return_delta": float(self.diff.get("total_return_delta", 0.0) or 0.0),
            "max_drawdown_delta": float(self.diff.get("max_drawdown_delta", 0.0) or 0.0),
            "trade_count_delta": int(self.diff.get("trade_count_delta", 0) or 0),
        }
        return {
            "mode": self.mode,
            "preset": self.preset,
            "winner": self.winner,
            "summary_text": self.summary_text,
            "diff": dict(self.diff),
            "summary": summary,
            "baseline_compact": dict(self.baseline.get("compact") or {}),
            "candidate_compact": dict(self.candidate.get("compact") or {}),
            "applied_overrides": dict(self.candidate.get("applied_overrides") or {}),
            "preset_detail": dict(self.candidate.get("preset") or {}),
        }

    def to_dict(self, detail: str = "compact") -> Dict[str, Any]:
        if str(detail or "compact").strip().lower() != "full":
            return self._build_compact_payload()
        return {
            "mode": self.mode,
            "preset": self.preset,
            "baseline": dict(self.baseline),
            "candidate": dict(self.candidate),
            "diff": dict(self.diff),
            "winner": self.winner,
            "summary_text": self.summary_text,
        }
