"""Long-polling entrypoint: python3 bot/main.py."""
import logging
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.brain import decide
from bot.index import BM25Index
from bot.store import HistoryStore
from bot.telegram_api import TelegramAPI

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KB = "/Users/agent/knowledge/BUILDIN_SELECTED_EXPORT_FINAL"

def load_env(path):
    if not os.path.exists(path): return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def log_escalation(text):
    directory = os.path.join(BOT_DIR, "data")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "escalations.log"), "a", encoding="utf-8") as handle:
        handle.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))

def notify_operator(api, support_id, user, question, history, reason):
    ops_token = os.environ.get("OPS_BOT_TOKEN", "")
    ops_api = TelegramAPI(ops_token) if ops_token else api
    transcript = "\n".join("%s: %s" % (entry["role"], entry["text"]) for entry in history[-20:])
    report = "ЭСКАЛАЦИЯ\nКлиент: %s (@%s, id=%s)\nВопрос: %s\nПричина: %s\nПоследний контекст:\n%s" % (user.get("first_name") or "без имени", user.get("username") or "—", user["id"], question, reason, transcript or "—")
    if not support_id:
        log_escalation(report + "\nНе задан SUPPORT_CHAT_ID")
        return
    try: api.send_message(support_id, report[:4000])
    except Exception as exc:
        logging.exception("Failed to send escalation")
        log_escalation(report + "\nОшибка отправки: %s" % exc)

MAX_TEXT_LEN = 2000
RATE_LIMIT_N, RATE_WINDOW_S = 5, 60
_rate = {}

def rate_limited(user_id):
    now = time.time()
    hits = [t for t in _rate.get(user_id, []) if now - t < RATE_WINDOW_S]
    if len(hits) >= RATE_LIMIT_N:
        _rate[user_id] = hits; return True
    hits.append(now); _rate[user_id] = hits; return False

def handle_message(api, store, index, message, support_id):
    chat, sender = message.get("chat", {}), message.get("from", {})
    if chat.get("type") != "private" or not sender: return
    user = {"id": sender["id"], "username": sender.get("username", ""), "first_name": sender.get("first_name", "")}
    text = message.get("text")
    if not text:
        api.send_message(chat["id"], "Пожалуйста, опишите вопрос текстом — так я смогу помочь."); return
    if len(text) > MAX_TEXT_LEN:
        api.send_message(chat["id"], "Сообщение слишком длинное — сократите, пожалуйста, до %d символов." % MAX_TEXT_LEN); return
    if rate_limited(user["id"]):
        api.send_message(chat["id"], "Слишком много сообщений подряд — подождите минуту, пожалуйста."); return
    if text.startswith("/start"):
        reply = "Здравствуйте%s! Я поддержка биржи. Опишите ваш вопрос текстом." % ((", " + user["first_name"]) if user["first_name"] else "")
        store.add(user["id"], user["username"], user["first_name"], "assistant", reply); api.send_message(chat["id"], reply); return
    store.add(user["id"], user["username"], user["first_name"], "user", text)
    try: api.send_typing(chat["id"])
    except Exception: pass
    history = store.recent(user["id"], 20)
    import threading
    stop_typing = threading.Event()
    def keep_typing():
        while not stop_typing.wait(4.5):
            try: api.send_typing(chat["id"])
            except Exception: pass
    t = threading.Thread(target=keep_typing, daemon=True); t.start()
    try:
        decision = decide(index, user, text, history)
    finally:
        stop_typing.set()
    store.add(user["id"], user["username"], user["first_name"], "assistant", decision["reply"])
    api.send_message(chat["id"], decision["reply"])
    if decision["action"] == "escalate": notify_operator(api, support_id, user, text, history, decision["reason"])

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env(os.path.join(BOT_DIR, ".env"))
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token: raise SystemExit("TELEGRAM_TOKEN is required in bot/.env")
    index = BM25Index.from_path(os.environ.get("KB_PATH", DEFAULT_KB))
    logging.info("index built: %d files, %d chunks", index.file_count, len(index.chunks))
    store, api = HistoryStore(os.path.join(BOT_DIR, "data", "history.db")), TelegramAPI(token)
    me = api.get_me(); logging.info("getMe OK: @%s; ready", me.get("username", me.get("id")))
    offset = None
    while True:
        try:
            for update in api.get_updates(offset):
                offset = update["update_id"] + 1
                if "message" in update: handle_message(api, store, index, update["message"], os.environ.get("SUPPORT_CHAT_ID", ""))
        except KeyboardInterrupt: raise
        except Exception:
            logging.exception("Polling error; retrying"); time.sleep(3)
if __name__ == "__main__": main()
