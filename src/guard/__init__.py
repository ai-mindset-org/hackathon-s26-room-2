"""guard — проверка черновика ответа на выдумку и на регламент.

Модуль комнаты 2, участник QE2K.

    from src.guard import check
    verdict = check(draft_text, "examples/base", request=request_text)
    verdict.ok          # можно ли показывать человеку
    verdict.findings    # что не так
    verdict.claims      # каждый факт с источником
"""

from .base_index import BaseIndex, load
from .guard import check, unknown_topics
from .model import ERROR, WARNING, Claim, Finding, Verdict

__all__ = [
    "BaseIndex",
    "Claim",
    "ERROR",
    "Finding",
    "Verdict",
    "WARNING",
    "check",
    "load",
    "unknown_topics",
]
