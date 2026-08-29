"""Вывод чисел из базы арифметикой.

Правильный расчёт КП содержит числа, которых в прайсе нет: 378 324 ₽ — это
12 × 33 900 минус скидка 7%. Такие числа обоснованы, и глупый детектор
«числа нет в базе → выдумка» на них сорвётся. Здесь мы честно проверяем,
выводится ли число из базы по правилам компании.
"""

from __future__ import annotations

from itertools import combinations

from .base_index import BaseIndex

TOLERANCE = 0.5  # округление до рубля
MAX_SUM_TERMS = 6
MAX_COMBINATIONS = 4000


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def from_price_math(value: float, index: BaseIndex, quantities: list[int]) -> str | None:
    """Число как строка расчёта: количество × цена, со скидкой или без."""
    discount = index.discount_percent
    min_qty = index.discount_min_qty

    for article, price in index.prices:
        for qty in quantities:
            if qty <= 0:
                continue
            line_total = qty * price
            if _close(value, line_total):
                return f"расчёт: {qty} × {price:,.0f} ({article})".replace(",", " ")

            if discount is None:
                continue
            discounted = line_total * (1 - discount / 100)
            if _close(value, discounted) or _close(value, round(discounted)):
                eligible = min_qty is None or qty >= min_qty
                note = "" if eligible else " — ВНИМАНИЕ: скидка не положена"
                return (
                    f"расчёт: {qty} × {price:,.0f} ({article}) − {discount:g}%{note}"
                ).replace(",", " ")

            saved = line_total * discount / 100
            if _close(value, saved) or _close(value, round(saved)):
                return f"расчёт: скидка {discount:g}% от {line_total:,.0f} ({article})".replace(
                    ",", " "
                )
    return None


def from_sum(value: float, parts: list[float]) -> str | None:
    """Число как сумма уже обоснованных чисел черновика (итого, подытог)."""
    usable = [part for part in parts if part > 0 and not _close(part, value)]
    if len(usable) < 2:
        return None

    seen = 0
    for size in range(2, min(MAX_SUM_TERMS, len(usable)) + 1):
        for combo in combinations(usable, size):
            seen += 1
            if seen > MAX_COMBINATIONS:
                return None
            if _close(sum(combo), value):
                terms = " + ".join(f"{part:,.0f}".replace(",", " ") for part in combo)
                return f"сумма: {terms}"
    return None


def explain(
    value: float,
    index: BaseIndex,
    quantities: list[int],
    peers: list[float] | None = None,
) -> str | None:
    """Откуда взялось число: из базы, из расчёта или из суммы. Иначе None."""
    literal = index.has_number(value)
    if literal:
        return f"база: {literal}"

    computed = from_price_math(value, index, quantities)
    if computed:
        return computed

    if peers:
        return from_sum(value, peers)
    return None
