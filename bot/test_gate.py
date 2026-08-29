"""Оффлайн-тесты для bot.gate — без Telegram и без LLM."""
import os
import sys
import unittest

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.gate import FALLBACK_REPLY, guard_gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        return handle.read()


class GuardGateTests(unittest.TestCase):
    def test_poisoned_draft_is_blocked(self):
        request = read("examples/02-запрос-кп/input/запрос.txt")
        draft = "Привезём завтра, гарантирую, цена 999 999 ₽"
        text, blocked, errors = guard_gate(draft, request)
        self.assertTrue(blocked)
        self.assertEqual(text, FALLBACK_REPLY)
        codes = [e.kind for e in errors]
        self.assertIn("promised_tomorrow", codes)

    def test_good_fixture_passes(self):
        request = read("examples/02-запрос-кп/input/запрос.txt")
        draft = read("src/guard/fixtures/good-02.md")
        text, blocked, errors = guard_gate(draft, request)
        self.assertFalse(blocked)
        self.assertEqual(text, draft)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
