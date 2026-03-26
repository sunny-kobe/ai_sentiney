from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _normalize_codes(codes: Optional[List[Optional[str]]]) -> List[str]:
    normalized: List[str] = []
    for code in codes or []:
        text = str(code or "").strip()
        if text:
            normalized.append(text)
    return normalized


@dataclass(slots=True)
class ValidationRequest:
    mode: str
    days: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    codes: List[str] = field(default_factory=list)
    benchmark_code: Optional[str] = None
    preset: Optional[str] = None

    def __post_init__(self) -> None:
        self.mode = str(self.mode or "").strip()
        self.date_from = str(self.date_from).strip() if self.date_from else None
        self.date_to = str(self.date_to).strip() if self.date_to else None
        self.codes = _normalize_codes(self.codes)
        self.benchmark_code = str(self.benchmark_code).strip() if self.benchmark_code else None
        self.preset = str(self.preset).strip() if self.preset else None

        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("invalid date range: date_from cannot be later than date_to")
        if self.days is not None:
            self.days = int(self.days)
            if self.days <= 0:
                raise ValueError("days must be positive")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "days": self.days,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "codes": list(self.codes),
            "benchmark_code": self.benchmark_code,
            "preset": self.preset,
        }


@dataclass(slots=True)
class ValidationResult:
    mode: str
    investor_summary: str
    compact: Dict[str, Any]
    as_of_date: Optional[str] = None
    text: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "mode": self.mode,
            "summary_text": self.investor_summary,
            "compact": dict(self.compact),
        }
        if self.as_of_date:
            payload["as_of_date"] = self.as_of_date
        if self.text:
            payload["text"] = self.text
        if self.diagnostics:
            payload["diagnostics"] = dict(self.diagnostics)
        if self.details:
            payload["details"] = self.details
        return payload
