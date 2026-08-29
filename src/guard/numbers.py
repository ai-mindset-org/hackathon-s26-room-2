"""Извлечение и нормализация чисел из русского текста.

Русские тексты пишут тысячи через пробел («33 900»), причём пробел бывает
обычным, неразрывным или узким. Всё это — одно число.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Пробелы, которыми в русском тексте разделяют разряды.
THIN_SPACES = "    "

_GROUPED = r"\d{1,3}(?:[" + THIN_SPACES + r"]\d{3})+(?:[.,]\d+)?"
_PLAIN = r"\d+(?:[.,]\d+)?"
NUMBER_RE = re.compile(_GROUPED + "|" + _PLAIN)

# Сколько символов вокруг числа смотрим, чтобы понять его тип.
CONTEXT = 28

MONEY_HINTS = ("₽", "руб", "цена", "цен", "стоим", "сумм", "итого", "скидк", "прайс")
QTY_HINTS = ("шт",)
DURATION_HINTS = ("дн", "день", "дня", "час", "недел", "месяц", "срок")
PERCENT_HINTS = ("%", "процент")
REFERENCE_HINTS = ("п.", "пункт", "№", "#", "тикет", "артикул")


@dataclass(frozen=True)
class Number:
    """Число, найденное в тексте, вместе с его типом и местом."""

    value: float
    raw: str
    kind: str  # money | qty | duration | percent | reference | other
    line: int
    context: str

    @property
    def is_money(self) -> bool:
        return self.kind == "money"


def normalize(raw: str) -> float:
    """«33 900» → 33900.0, «1,5» → 1.5."""
    cleaned = raw
    for space in THIN_SPACES:
        cleaned = cleaned.replace(space, "")
    return float(cleaned.replace(",", "."))


def _classify(text: str, start: int, end: int, raw: str) -> str:
    """Тип числа определяем по тексту вокруг него."""
    before = text[max(0, start - CONTEXT) : start].lower()
    after = text[end : end + CONTEXT].lower()

    # Ссылка на пункт регламента или номер тикета — не факт о мире.
    tail = before.rstrip()
    if tail.endswith(("п.", "№", "#", "пункт")):
        return "reference"

    # Маркер нумерованного списка («1.», «2)») — тоже не факт.
    line_head = before.rsplit("\n", 1)[-1]
    if not line_head.strip(" \t-*") and after[:2] in (". ", ") ", ".\t", ")\t"):
        return "reference"
    if any(h in before[-12:] for h in REFERENCE_HINTS):
        return "reference"

    if after.lstrip().startswith("%") or any(h in after[:8] for h in PERCENT_HINTS):
        return "percent"
    if any(h in after[:10] for h in QTY_HINTS):
        return "qty"
    if any(h in after[:14] for h in DURATION_HINTS):
        return "duration"
    if "₽" in after[:10] or any(h in after[:14] for h in MONEY_HINTS):
        return "money"
    if any(h in before[-20:] for h in MONEY_HINTS):
        return "money"

    # Разряды через пробел — почти всегда деньги в этом домене.
    if any(space in raw for space in THIN_SPACES):
        return "money"
    return "other"


def extract(text: str) -> list[Number]:
    """Все числа текста с типом и номером строки."""
    line_starts = [0]
    for match in re.finditer(r"\n", text):
        line_starts.append(match.end())

    def line_of(pos: int) -> int:
        low, high = 0, len(line_starts) - 1
        while low < high:
            mid = (low + high + 1) // 2
            if line_starts[mid] <= pos:
                low = mid
            else:
                high = mid - 1
        return low + 1

    found: list[Number] = []
    for match in NUMBER_RE.finditer(text):
        raw = match.group(0)
        start, end = match.span()
        snippet = text[max(0, start - CONTEXT) : end + CONTEXT].replace("\n", " ")
        found.append(
            Number(
                value=normalize(raw),
                raw=raw,
                kind=_classify(text, start, end, raw),
                line=line_of(start),
                context=snippet.strip(),
            )
        )
    return found
