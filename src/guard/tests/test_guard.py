"""Тесты модуля guard. Только stdlib: python -m unittest src.guard.tests.test_guard"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.guard import check, load
from src.guard.derive import explain

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "examples" / "base"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EXAMPLES = ROOT / "examples"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def request_of(example: str) -> str:
    folder = EXAMPLES / example / "input"
    return "\n\n".join(read(p) for p in sorted(folder.iterdir()) if p.is_file())


def kinds(verdict) -> set[str]:
    return {finding.kind for finding in verdict.findings}


def error_kinds(verdict) -> set[str]:
    return {finding.kind for finding in verdict.errors}


class TestBaseIndex(unittest.TestCase):
    def setUp(self) -> None:
        self.index = load(BASE)

    def test_price_table_parsed(self) -> None:
        self.assertEqual(len(self.index.price_rows), 5)
        row = self.index.price_of("TS-192E")
        self.assertIsNotNone(row)
        self.assertEqual(row.price, 33900)
        self.assertEqual(row.lead_time_days, 3)

    def test_in_stock_is_zero_days(self) -> None:
        self.assertEqual(self.index.price_of("TS-TRAY").lead_time_days, 0)

    def test_commercial_rules(self) -> None:
        self.assertEqual(self.index.discount_min_qty, 10)
        self.assertEqual(self.index.discount_percent, 7)
        self.assertEqual(self.index.free_delivery_from, 50000)

    def test_email_and_articles_known(self) -> None:
        self.assertIn("no-reply@technosklad.example", self.index.emails)
        self.assertIn("TS-16H", self.index.articles)


class TestDerivation(unittest.TestCase):
    """Правильный расчёт содержит числа, которых в прайсе нет."""

    def setUp(self) -> None:
        self.index = load(BASE)

    def test_line_total(self) -> None:
        self.assertIn("TS-192E", explain(406800, self.index, [12]))

    def test_discounted_line(self) -> None:
        self.assertIn("7%", explain(378324, self.index, [12]))

    def test_grand_total_is_a_sum(self) -> None:
        got = explain(485266, self.index, [12, 2, 14], peers=[378324, 79600, 27342])
        self.assertIsNotNone(got)
        self.assertTrue(got.startswith("сумма"))

    def test_invented_number_has_no_source(self) -> None:
        self.assertIsNone(explain(245000, self.index, [1, 12, 2, 14]))


class TestAcceptanceDrafts(unittest.TestCase):
    """Чистый черновик проходит, отравленный — нет."""

    def check_fixture(self, name: str, example: str):
        return check(read(FIXTURES / name), BASE, request=request_of(example))

    # --- 01 тикет: доступ ---------------------------------------------

    def test_good_01_passes(self) -> None:
        verdict = self.check_fixture("good-01.md", "01-тикет-доступ")
        self.assertTrue(verdict.ok, f"неожиданные ошибки: {error_kinds(verdict)}")

    def test_bad_01_caught(self) -> None:
        verdict = self.check_fixture("bad-01.md", "01-тикет-доступ")
        self.assertFalse(verdict.ok)
        for expected in ("tone_ty", "unknown_email", "unknown_phone",
                         "promised_tomorrow", "no_signature"):
            self.assertIn(expected, error_kinds(verdict))

    def test_bad_01_invented_link_lifetime(self) -> None:
        """«6 часов» вместо 2 — выдуманный срок."""
        verdict = self.check_fixture("bad-01.md", "01-тикет-доступ")
        self.assertTrue(
            any(f.kind == "ungrounded_number" and "6" in f.message for f in verdict.errors)
        )

    # --- 02 КП: арифметика --------------------------------------------

    def test_good_02_passes(self) -> None:
        verdict = self.check_fixture("good-02.md", "02-запрос-кп")
        self.assertTrue(verdict.ok, f"неожиданные ошибки: {error_kinds(verdict)}")

    def test_good_02_every_price_has_a_source(self) -> None:
        verdict = self.check_fixture("good-02.md", "02-запрос-кп")
        self.assertEqual(verdict.ungrounded, [])
        sources = {c.text: c.source for c in verdict.claims if c.source}
        self.assertIn("485 266", sources)
        self.assertTrue(sources["485 266"].startswith("сумма"))

    def test_bad_02_discount_where_it_is_not_earned(self) -> None:
        """Ключевая проверка приёмки: скидка не положена HDD (2 шт < 10)."""
        verdict = self.check_fixture("bad-02.md", "02-запрос-кп")
        self.assertFalse(verdict.ok)
        self.assertIn("discount_not_earned", error_kinds(verdict))

    # --- 03 вне базы: тест на выдумку ---------------------------------

    def test_good_03_passes(self) -> None:
        verdict = self.check_fixture("good-03.md", "03-вне-базы")
        self.assertTrue(verdict.ok, f"неожиданные ошибки: {error_kinds(verdict)}")

    def test_bad_03_invention_caught(self) -> None:
        verdict = self.check_fixture("bad-03.md", "03-вне-базы")
        self.assertFalse(verdict.ok)
        self.assertIn("ungrounded_number", error_kinds(verdict))
        self.assertIn("unknown_article", error_kinds(verdict))
        self.assertIn("promised_tomorrow", error_kinds(verdict))

    def test_out_of_base_topics_detected(self) -> None:
        from src.guard import unknown_topics

        topics = unknown_topics(request_of("03-вне-базы"), load(BASE))
        self.assertTrue(any("LTO" in t for t in topics))
        self.assertTrue(any("юан" in t for t in topics))

    def test_in_base_request_has_no_false_topics(self) -> None:
        """КП по прайсу не должно считаться «вопросом вне базы»."""
        from src.guard import unknown_topics

        self.assertEqual(unknown_topics(request_of("02-запрос-кп"), load(BASE)), [])


class TestContract(unittest.TestCase):
    def test_verdict_serialises(self) -> None:
        verdict = check(read(FIXTURES / "good-02.md"), BASE, request=request_of("02-запрос-кп"))
        payload = verdict.to_dict()
        self.assertIn("stats", payload)
        self.assertIn("claims", payload)
        self.assertEqual(payload["stats"]["ungrounded"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
