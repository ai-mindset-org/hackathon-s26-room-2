"""guard_gate — прогоняет черновик ответа бота через src.guard перед отправкой клиенту."""
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.guard import check

BASE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "base")
FALLBACK_REPLY = "Уточню у менеджера и вернусь с ответом позже."


def guard_gate(answer, request):
    """Проверяет черновик ответа через guard.

    Возвращает (text_to_send, blocked, errors):
      blocked=False -> text_to_send == answer (guard пройден)
      blocked=True  -> text_to_send == FALLBACK_REPLY, errors — список нарушений (Finding)
    """
    verdict = check(answer, BASE_PATH, request=request)
    if verdict.ok:
        return answer, False, []
    errors = verdict.errors
    print("GUARD BLOCKED: %d нарушение(й)" % len(errors))
    for err in errors:
        print("  [%s] %s" % (err.kind, err.message))
    return FALLBACK_REPLY, True, errors
