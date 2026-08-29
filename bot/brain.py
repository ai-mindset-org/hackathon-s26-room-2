"""Knowledge-grounded response decision via the local Codex CLI."""
import json
import os
import subprocess
import tempfile

SYSTEM_RULES = '''Ты — оператор поддержки крипто-биржи. Верни ТОЛЬКО корректный JSON:
{"action":"answer"|"escalate","reply":"текст клиенту","reason":"краткая причина"}.
Отвечай только фактами, прямо подтверждёнными предоставленными чанками базы.
Не используй общие знания и не придумывай ссылки, шаги, сроки или статусы аккаунта.
Обращайся к клиенту по имени из профиля, если имя есть. Тон дружелюбный и короткий.
Если в чанках нет достаточной информации, вопрос требует доступа к аккаунту,
проверки транзакции, ручного вмешательства или есть сомнение — action "escalate".
При escalate в reply вежливо скажи, что вопрос передан оператору.'''


def decide(index, user, message, history):
    history = history[-20:]
    # The fresh question has priority; history supplies context but must not drown it out.
    query = message + "\n" + message + "\n" + "\n".join(item["text"] for item in history)
    chunks = index.search(query, 6)
    try:
        result = _parse_result(_run_codex(_prompt(user, message, history, chunks)))
        if result["action"] not in ("answer", "escalate") or not result["reply"]:
            raise ValueError("invalid JSON schema")
        return result
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        return {"action": "escalate", "reply": _escalation_reply(user), "reason": "Не удалось безопасно сформировать ответ: %s" % exc}


def _prompt(user, message, history, chunks):
    knowledge = "\n\n".join("[Источник: {source}; раздел: {title}]\n{text}".format(**chunk) for chunk in chunks) or "(релевантных чанков не найдено)"
    transcript = "\n".join("%s: %s" % (item["role"], item["text"]) for item in history) or "(нет)"
    return "%s\n\nПрофиль: имя=%s, username=%s\nИстория:\n%s\n\nЧанки базы:\n%s\n\nНовое сообщение: %s" % (SYSTEM_RULES, user.get("first_name") or "", user.get("username") or "", transcript, knowledge, message)


def _run_codex(prompt):
    fd, path = tempfile.mkstemp(prefix="vpam-brain-", suffix=".txt")
    os.close(fd)
    try:
        subprocess.run(["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-m", "gpt-5.6-terra", "-o", path, prompt], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, check=True)
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    finally:
        try: os.unlink(path)
        except OSError: pass


def _parse_result(raw):
    raw = raw.strip()
    try: data = json.loads(raw)
    except json.JSONDecodeError:
        left, right = raw.find("{"), raw.rfind("}")
        if left < 0 or right < left: raise
        data = json.loads(raw[left:right + 1])
    if not isinstance(data, dict): raise ValueError("JSON must be an object")
    return {"action": str(data.get("action", "")), "reply": str(data.get("reply", "")).strip(), "reason": str(data.get("reason", "")).strip()}


def _escalation_reply(user):
    return ("%s, ваш вопрос передан оператору. Он поможет разобраться." % (user.get("first_name") or "")).strip()
