"""Проверка черновика на выдумку и на соблюдение регламента.

Главная функция модуля — `check`. Она отвечает на два вопроса заказчика:
«откуда цифры?» и «не выдумал ли он?».
"""

from __future__ import annotations

import re
from pathlib import Path

from . import derive, numbers as num, rules
from .base_index import ARTICLE_RE, EMAIL_RE, URL_RE, BaseIndex, load
from .model import ERROR, WARNING, Claim, Finding, Verdict

PHONE_RE = re.compile(r"(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b")
LATIN_TOKEN_RE = re.compile(r"\b[A-Za-z]{2,}(?:-\d+)?\b")
# Артикулы и коды моделей: цифры внутри них — часть имени, а не число.
CODE_RE = re.compile(r"\b[A-Za-z]{2,}-[A-Za-z0-9]+\b")


def _mask_codes(text: str) -> str:
    """Затереть коды моделей, сохранив длину: TS-192E не должен дать число 192."""
    return CODE_RE.sub(lambda m: " " * len(m.group(0)), text)

# Сильные сигналы «клиент спросил про то, чего в базе нет».
TOPIC_LEXICON = (
    "юан", "доллар", "евро", "рассрочк", "отсрочк", "лизинг", "аккредитив",
    "библиотек", "ленточн", "стример", "коммутатор", "лицензи", "гаранти",
    "монтаж", "аренд", "трейд-ин", "утилизац",
)

# Типы чисел, выдумка которых — ошибка, а не придирка.
HARD_KINDS = {"money", "duration", "percent"}


def unknown_topics(request: str, index: BaseIndex) -> list[str]:
    """О чём клиент спросил, а в базе про это ничего нет."""
    found: list[str] = []

    for token in LATIN_TOKEN_RE.findall(request):
        if len(token) < 3 or index.mentions(token):
            continue
        if token.upper() not in {t.upper() for t in found}:
            found.append(token)

    lowered = request.lower()
    for topic in TOPIC_LEXICON:
        if topic in lowered and not index.mentions(topic):
            found.append(topic)
    return found


def _quantities(draft: str, request: str | None) -> list[int]:
    def collect(kinds: set[str]) -> list[int]:
        values: list[int] = []
        for text in (request or "", draft):
            for found in num.extract(_mask_codes(text)):
                if found.kind in kinds and found.value.is_integer():
                    candidate = int(found.value)
                    if 1 <= candidate <= 10_000 and candidate not in values:
                        values.append(candidate)
        return values[:60]

    # Явные количества («12 шт») точнее всего. Числа без единицы берём только
    # тогда, когда явных нет — иначе расчёт «сойдётся» со случайным числом.
    explicit = collect({"qty"})
    return explicit or collect({"qty", "other"})


def _ground_numbers(
    draft: str,
    index: BaseIndex,
    request: str | None,
    quantities: list[int],
) -> tuple[list[Claim], list[Finding]]:
    request_numbers = (
        {n.value for n in num.extract(_mask_codes(request))} if request else set()
    )
    found = [n for n in num.extract(_mask_codes(draft)) if n.kind != "reference"]

    claims: list[Claim] = []
    for item in found:
        claims.append(
            Claim(
                text=item.raw,
                kind=item.kind,
                line=item.line,
                grounded=False,
                context=item.context,
            )
        )

    # Проход 1: буквально из базы, из запроса или из расчёта по прайсу.
    for claim, item in zip(claims, found):
        literal = index.has_number(item.value)
        if literal:
            claim.grounded, claim.source = True, f"база: {literal}"
            continue
        if item.value in request_numbers:
            claim.grounded, claim.source = True, "запрос клиента"
            continue
        computed = derive.from_price_math(item.value, index, quantities)
        if computed:
            claim.grounded, claim.source = True, computed

    # Проходы 2-3: итоговые суммы складываются из уже обоснованных чисел.
    for _ in range(2):
        anchors = [
            item.value
            for claim, item in zip(claims, found)
            if claim.grounded and item.kind == "money"
        ]
        for claim, item in zip(claims, found):
            if claim.grounded or item.kind != "money":
                continue
            summed = derive.from_sum(item.value, anchors)
            if summed:
                claim.grounded, claim.source = True, summed

    findings: list[Finding] = []
    for claim, item in zip(claims, found):
        if claim.grounded:
            # Число сходится, но получено по неположенной скидке.
            if claim.source and "скидка не положена" in claim.source:
                findings.append(
                    Finding(
                        kind="discount_not_earned",
                        severity=ERROR,
                        message=(
                            f"Скидка применена к позиции, где её нет: {item.raw} "
                            f"(порог — {index.discount_min_qty} шт одной позиции)"
                        ),
                        evidence=item.context,
                        line=item.line,
                        rule="прайс: условия скидки",
                    )
                )
            continue
        hard = item.kind in HARD_KINDS or (item.kind == "qty" and request is not None)
        findings.append(
            Finding(
                kind="ungrounded_number",
                severity=ERROR if hard else WARNING,
                message=f"Число {item.raw} не выводится из базы",
                evidence=item.context,
                line=item.line,
                rule="регламент п.5",
            )
        )
    return claims, findings


def _ground_entities(
    draft: str, index: BaseIndex, request: str | None = None
) -> tuple[list[Claim], list[Finding]]:
    claims: list[Claim] = []
    findings: list[Finding] = []
    asked = (request or "").lower()

    def add(text: str, kind: str, known: bool, message: str) -> None:
        # Код, который назвал сам клиент, черновик цитирует, а не выдумывает:
        # честный отказ «LTO-9 у нас нет» обязан упомянуть LTO-9.
        quoted = bool(asked) and text.lower() in asked
        source = "база" if known else ("запрос клиента" if quoted else None)
        claims.append(Claim(text=text, kind=kind, line=0,
                            grounded=known or quoted, source=source))
        if not (known or quoted):
            findings.append(
                Finding(kind=f"unknown_{kind}", severity=ERROR, message=message,
                        evidence=text, rule="регламент п.5")
            )

    for email in set(EMAIL_RE.findall(draft)):
        add(email, "email", email in index.emails, f"Адрес {email} отсутствует в базе")

    for article in set(ARTICLE_RE.findall(draft)):
        known = article.upper() in {a.upper() for a in index.articles}
        add(article, "article", known, f"Артикул {article} отсутствует в прайсе")

    for url in set(match.lower() for match in URL_RE.findall(draft)):
        if "@" in url:
            continue
        add(url, "url", url in index.urls, f"Ссылка {url} отсутствует в базе")

    for phone in set(PHONE_RE.findall(draft)):
        add(phone, "phone", False, f"Телефон {phone} выдуман — в базе телефонов нет")

    return claims, findings


def check(
    draft: str,
    base_dir: str | Path,
    request: str | None = None,
    index: BaseIndex | None = None,
) -> Verdict:
    """Проверить черновик против базы компании.

    draft    — текст черновика ответа
    base_dir — папка базы (прайс, регламент, прошлые ответы)
    request  — исходный запрос клиента, если есть: без него нельзя проверить
               обращение по имени и количества
    """
    index = index or load(base_dir)
    topics = unknown_topics(request, index) if request else []
    quantities = _quantities(draft, request)

    number_claims, number_findings = _ground_numbers(draft, index, request, quantities)
    entity_claims, entity_findings = _ground_entities(draft, index, request)
    rule_findings = rules.check_all(draft, index, request, topics)

    verdict = Verdict(
        claims=[*number_claims, *entity_claims],
        findings=[*number_findings, *entity_findings, *rule_findings],
    )
    verdict.ok = not verdict.errors
    return verdict
