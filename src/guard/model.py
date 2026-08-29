"""Контракт модуля guard: что он принимает и что отдаёт.

Другие модули комнаты зависят только от этих трёх структур.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

ERROR = "error"
WARNING = "warning"


@dataclass
class Claim:
    """Проверяемое утверждение черновика и его источник."""

    text: str
    kind: str  # money | qty | duration | percent | article | email | url
    line: int
    grounded: bool
    source: str | None = None
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    """Нарушение: выдумка или отступление от регламента."""

    kind: str
    severity: str
    message: str
    evidence: str = ""
    line: int = 0
    rule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    """Итог проверки одного черновика."""

    ok: bool = True
    claims: list[Claim] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def grounded(self) -> list[Claim]:
        return [c for c in self.claims if c.grounded]

    @property
    def ungrounded(self) -> list[Claim]:
        return [c for c in self.claims if not c.grounded]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stats": {
                "claims": len(self.claims),
                "grounded": len(self.grounded),
                "ungrounded": len(self.ungrounded),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "findings": [f.to_dict() for f in self.findings],
            "claims": [c.to_dict() for c in self.claims],
        }
