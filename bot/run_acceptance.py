"""Прогоняет guard_gate на приёмочных примерах (без вызова LLM)."""
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.gate import guard_gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = [
    ("examples/01-тикет-доступ/input/тикет.txt", "src/guard/fixtures/good-01.md"),
    ("examples/02-запрос-кп/input/запрос.txt", "src/guard/fixtures/good-02.md"),
    ("examples/03-вне-базы/input/запрос.txt", "src/guard/fixtures/good-03.md"),
]


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def main():
    passed = 0
    for request_path, draft_path in CASES:
        request = read(request_path)
        draft = read(draft_path)
        _, blocked, errors = guard_gate(draft, request)
        ok = not blocked
        passed += 1 if ok else 0
        status = "OK" if ok else "BLOCKED"
        print("%s -> %s (%s)" % (draft_path, status, ", ".join(e.kind for e in errors) or "-"))
    print("прошло %d из %d" % (passed, len(CASES)))


if __name__ == "__main__":
    main()
