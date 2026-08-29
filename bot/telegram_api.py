"""Minimal Telegram Bot API client based only on requests."""
import requests


class TelegramAPI:
    def __init__(self, token): self.base_url = "https://api.telegram.org/bot%s" % token
    def call(self, method, payload=None, timeout=35):
        response = requests.post(self.base_url + "/" + method, json=payload or {}, timeout=timeout)
        response.raise_for_status(); data = response.json()
        if not data.get("ok"): raise RuntimeError("Telegram %s: %s" % (method, data.get("description")))
        return data["result"]
    def get_me(self): return self.call("getMe", timeout=15)
    def get_updates(self, offset): return self.call("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": ["message"]}, timeout=40)
    def send_message(self, chat_id, text): return self.call("sendMessage", {"chat_id": chat_id, "text": text}, timeout=15)
    def send_typing(self, chat_id): return self.call("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=10)
