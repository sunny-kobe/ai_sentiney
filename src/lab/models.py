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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "preset": self.preset,
            "baseline": dict(self.baseline),
            "candidate": dict(self.candidate),
            "diff": dict(self.diff),
            "winner": self.winner,
            "summary_text": self.summary_text,
        }
