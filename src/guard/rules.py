"""Проверки по регламенту ответов клиентам.

Каждая функция отвечает за один пункт регламента из `base/регламент-ответов.md`
и возвращает найденные нарушения. Пункты, которые нельзя проверить машиной
без гадания, помечаются как warning, а не error.
"""

from __future__ import annotations

import re

from .base_index import BaseIndex
from .model import ERROR, WARNING, Finding

TY_RE = re.compile(r"\b(ты|тебе|тебя|твой|твоя|твои|твоего|тобой)\b", re.I)
TOMORROW_RE = re.compile(r"\b(завтра|послезавтра)\b", re.I)
SOON_RE = re.compile(r"(сегодня же|в течение дня|в ближайшее время|максимально быстро)", re.I)
SIGNATURE = "команда техносклад"

SUPPORT_HINTS = ("поддержк", "менеджер", "свяж", "переда", "позвон")
# Честное «этого у нас нет» пишут десятком способов, поэтому не список фраз,
# а образец: отрицание рядом с упоминанием базы/прайса — либо прямой отказ.
ADMISSION_RE = re.compile(
    r"(?:(?:в\s+)?(?:баз\w+|прайс\w+|наличи\w+)[^.!?]{0,60}?\bнет\b"
    r"|\bнет\b[^.!?]{0,60}?(?:в\s+)?(?:баз\w+|прайс\w+|наличи\w+)"
    r"|отсутств\w*|не\s+найд\w*|не\s+поставля\w*|не\s+значится"
    r"|не\s+мог\w*\s+(?:назвать|подтвердить|обещать))",
    re.I,
)
CLERICAL = (
    "вышеуказанн",
    "нижеследующ",
    "настоящим уведомля",
    "осуществляется",
    "в связи с чем",
    "данный факт",
    "по факту наличия",
)

NAME_STOP = {
    "ооо", "ип", "зао", "оао", "клиент", "тикет", "здравствуйте", "добрый",
    "день", "привет", "как", "можно", "заказ", "спасибо", "прима",
}


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """Абзацы с номером первой строки."""
    result: list[tuple[int, str]] = []
    line_no = 1
    for block in re.split(r"\n\s*\n", text):
        result.append((line_no, block))
        line_no += block.count("\n") + 2
    return result


def candidate_names(request: str) -> list[str]:
    """Имена клиента из входящего запроса — грубо, но для проверки хватает."""
    names: list[str] = []
    for match in re.finditer(r"\b([А-ЯЁ][а-яё]{2,})\b", request):
        word = match.group(1)
        if word.lower() in NAME_STOP:
            continue
        names.append(word)
    return names


def rule_1_address(draft: str, request: str | None) -> list[Finding]:
    findings: list[Finding] = []
    ty = TY_RE.search(draft)
    if ty:
        findings.append(
            Finding(
                kind="tone_ty",
                severity=ERROR,
                message="Обращение на «ты» — регламент требует «вы»",
                evidence=ty.group(0),
                rule="регламент п.1",
            )
        )

    if request:
        names = candidate_names(request)
        if names and not any(name.lower() in draft.lower() for name in names):
            findings.append(
                Finding(
                    kind="no_name",
                    severity=WARNING,
                    message=f"Нет обращения по имени (в запросе: {', '.join(names[:3])})",
                    rule="регламент п.1",
                )
            )

    for word in CLERICAL:
        if word in draft.lower():
            findings.append(
                Finding(
                    kind="clerical",
                    severity=WARNING,
                    message="Канцелярит — регламент просит живой язык",
                    evidence=word,
                    rule="регламент п.1",
                )
            )
    return findings


def rule_2_order(draft: str) -> list[Finding]:
    """Контакт поддержки — в конце, а не вместо шагов решения."""
    lowered = draft.lower()
    positions = [lowered.find(hint) for hint in SUPPORT_HINTS if lowered.find(hint) >= 0]
    if not positions:
        return []
    if min(positions) < len(lowered) * 0.34:
        return [
            Finding(
                kind="order",
                severity=WARNING,
                message="Передача в поддержку стоит раньше шагов решения",
                rule="регламент п.2",
            )
        ]
    return []


def rule_3_article_with_price(draft: str, index: BaseIndex) -> list[Finding]:
    """Цену из прайса называем только вместе с артикулом."""
    from . import numbers as num

    known_prices = {row.price: row.article for row in index.price_rows}
    findings: list[Finding] = []
    for line_no, block in _paragraphs(draft):
        articles_here = set(re.findall(r"\b[A-Z]{2,}-[A-Z0-9]{1,8}\b", block))
        for found in num.extract(block):
            article = known_prices.get(found.value)
            if article and article not in articles_here:
                findings.append(
                    Finding(
                        kind="price_without_article",
                        severity=ERROR,
                        message=f"Цена {found.raw} названа без артикула ({article})",
                        evidence=found.context,
                        line=line_no,
                        rule="регламент п.3",
                    )
                )
    return findings


def rule_4_deadlines(draft: str) -> list[Finding]:
    findings: list[Finding] = []
    tomorrow = TOMORROW_RE.search(draft)
    if tomorrow:
        findings.append(
            Finding(
                kind="promised_tomorrow",
                severity=ERROR,
                message="Обещано «завтра» — сроки берём только из прайса",
                evidence=tomorrow.group(0),
                rule="регламент п.4",
            )
        )
    soon = SOON_RE.search(draft)
    if soon:
        findings.append(
            Finding(
                kind="vague_deadline",
                severity=WARNING,
                message="Расплывчатый срок вместо срока из прайса",
                evidence=soon.group(0),
                rule="регламент п.4",
            )
        )
    return findings


def rule_5_honesty(draft: str, unknown_topics: list[str]) -> list[Finding]:
    """Нет ответа в базе — говорим честно и передаём менеджеру."""
    if not unknown_topics:
        return []
    lowered = draft.lower()
    findings: list[Finding] = []
    if not ADMISSION_RE.search(draft):
        findings.append(
            Finding(
                kind="no_admission",
                severity=ERROR,
                message="В базе нет ответа ({}), но черновик об этом не говорит".format(
                    ", ".join(unknown_topics[:3])
                ),
                rule="регламент п.5",
            )
        )
    if not any(hint in lowered for hint in ("менеджер", "переда", "свяж")):
        findings.append(
            Finding(
                kind="no_handoff",
                severity=ERROR,
                message="Нет передачи менеджеру по вопросу вне базы",
                rule="регламент п.5",
            )
        )
    return findings


def rule_6_signature(draft: str) -> list[Finding]:
    if SIGNATURE in draft.lower():
        return []
    return [
        Finding(
            kind="no_signature",
            severity=ERROR,
            message="Нет подписи «Команда ТехноСклад»",
            rule="регламент п.6",
        )
    ]


def check_all(
    draft: str,
    index: BaseIndex,
    request: str | None,
    unknown_topics: list[str],
) -> list[Finding]:
    return [
        *rule_1_address(draft, request),
        *rule_2_order(draft),
        *rule_3_article_with_price(draft, index),
        *rule_4_deadlines(draft),
        *rule_5_honesty(draft, unknown_topics),
        *rule_6_signature(draft),
    ]
