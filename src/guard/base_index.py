"""Индекс базы компании: всё, на что черновик имеет право опираться.

Читает папку `base/` и раскладывает её на проверяемые факты — позиции прайса,
артикулы, сроки, адреса, правила скидок и пункты регламента. Всё, чего здесь
нет и что из этого не выводится арифметикой, считается выдумкой.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import numbers as num

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ARTICLE_RE = re.compile(r"\b[A-Z]{2,}-[A-Z0-9]{1,8}\b")
URL_RE = re.compile(r"https?://[^\s)\]]+|\b[\w-]+\.(?:ru|com|example|org|net)\b")

_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


@dataclass(frozen=True)
class PriceRow:
    """Строка прайса."""

    name: str
    article: str
    price: float
    lead_time_days: int | None
    lead_time_raw: str
    source: str


@dataclass
class BaseIndex:
    """Все факты базы, разложенные по видам."""

    files: dict[str, str] = field(default_factory=dict)
    price_rows: list[PriceRow] = field(default_factory=list)
    numbers: dict[float, list[str]] = field(default_factory=dict)
    emails: set[str] = field(default_factory=set)
    articles: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)
    rules: list[str] = field(default_factory=list)
    discount_min_qty: int | None = None
    discount_percent: float | None = None
    free_delivery_from: float | None = None

    # --- поиск --------------------------------------------------------

    def price_of(self, article: str) -> PriceRow | None:
        article = article.upper()
        for row in self.price_rows:
            if row.article.upper() == article:
                return row
        return None

    def has_number(self, value: float, tolerance: float = 0.01) -> str | None:
        """Где в базе встречается это число (если встречается)."""
        for known, sources in self.numbers.items():
            if abs(known - value) <= tolerance:
                return sources[0]
        return None

    def mentions(self, needle: str) -> str | None:
        """Где в базе встречается эта подстрока (без учёта регистра)."""
        needle = needle.lower()
        for name, text in self.files.items():
            if needle in text.lower():
                return name
        return None

    @property
    def prices(self) -> list[tuple[str, float]]:
        return [(row.article, row.price) for row in self.price_rows]


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_lead_time(raw: str) -> int | None:
    """«3 дня» → 3, «в наличии» → 0, иначе None."""
    lowered = raw.lower()
    if "налич" in lowered:
        return 0
    match = re.search(r"(\d+)", raw)
    return int(match.group(1)) if match else None


def _parse_price_table(text: str, source: str) -> list[PriceRow]:
    rows: list[PriceRow] = []
    header: list[str] | None = None

    for line in text.splitlines():
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = _split_row(line)
        if all(_SEPARATOR_CELL.match(cell) for cell in cells if cell):
            continue
        if header is None:
            header = [cell.lower() for cell in cells]
            continue

        def column(*keys: str) -> str:
            for index, title in enumerate(header or []):
                if any(key in title for key in keys) and index < len(cells):
                    return cells[index]
            return ""

        article = column("артикул")
        price_raw = column("цена", "стоим")
        if not article or not price_raw:
            continue
        digits = num.NUMBER_RE.search(price_raw)
        if not digits:
            continue
        lead_raw = column("срок", "постав")
        rows.append(
            PriceRow(
                name=column("позиция", "наименование", "товар") or cells[0],
                article=article,
                price=num.normalize(digits.group(0)),
                lead_time_days=_parse_lead_time(lead_raw),
                lead_time_raw=lead_raw,
                source=source,
            )
        )
    return rows


def _parse_commercial_rules(text: str, index: BaseIndex) -> None:
    discount = re.search(r"скидк\w*\s+от\s+(\d+)\s*шт[^.]*?(\d+(?:[.,]\d+)?)\s*%", text, re.I)
    if discount:
        index.discount_min_qty = int(discount.group(1))
        index.discount_percent = num.normalize(discount.group(2))

    delivery = re.search(
        r"доставка[^.]*?бесплатн\w*\s+от\s+(" + num.NUMBER_RE.pattern + r")", text, re.I
    )
    if delivery:
        index.free_delivery_from = num.normalize(delivery.group(1))


def load(base_dir: str | Path) -> BaseIndex:
    """Собрать индекс из всех файлов папки базы."""
    base_path = Path(base_dir)
    if not base_path.is_dir():
        raise FileNotFoundError(f"папка базы не найдена: {base_path}")

    index = BaseIndex()
    for path in sorted(base_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        name = path.name
        index.files[name] = text

        for found in num.extract(text):
            # Номера пунктов и маркеры списка — разметка документа, а не факт.
            # Иначе «6» из «6. Подпись» обоснует выдуманные «6 часов».
            if found.kind == "reference":
                continue
            index.numbers.setdefault(found.value, []).append(f"{name}:{found.line}")

        index.emails.update(EMAIL_RE.findall(text))
        index.articles.update(ARTICLE_RE.findall(text))
        index.urls.update(match.lower() for match in URL_RE.findall(text))
        index.price_rows.extend(_parse_price_table(text, name))
        _parse_commercial_rules(text, index)

        for line in text.splitlines():
            numbered = re.match(r"\s*(\d+)[.)]\s+(.{5,})", line)
            if numbered and "регламент" in name.lower():
                index.rules.append(numbered.group(2).strip())

    # Артикулы из таблицы надёжнее, чем regex по тексту.
    index.articles.update(row.article for row in index.price_rows)
    return index
