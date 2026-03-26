from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _normalize_group_by(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


@dataclass(slots=True)
class DiagnosisRequest:
    group_by: Optional[str] = None
    primary_window: Optional[int] = None

    def __post_init__(self) -> None:
        self.group_by = _normalize_group_by(self.group_by)
        if self.primary_window is not None:
            self.primary_window = int(self.primary_window)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_by": self.group_by,
            "primary_window": self.primary_window,
        }


@dataclass(slots=True)
class DiagnosticGroup:
    key: str
    sample_count: int
    avg_absolute_return: float
    avg_relative_return: float
    avg_max_drawdown: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "sample_count": int(self.sample_count),
            "avg_absolute_return": float(self.avg_absolute_return),
            "avg_relative_return": float(self.avg_relative_return),
            "avg_max_drawdown": float(self.avg_max_drawdown),
        }


@dataclass(slots=True)
class DiagnosisSummary:
    group_by: Optional[str]
    primary_window: Optional[int]
    summary_text: str
    groups: List[DiagnosticGroup] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_by": self.group_by,
            "primary_window": self.primary_window,
            "summary_text": self.summary_text,
            "groups": [group.to_dict() for group in self.groups],
        }
