"""Persistent, user-isolated dialogue history."""
import os
import sqlite3
import time


class HistoryStore:
    def __init__(self, path):
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.path = path
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS messages (
                user_id INTEGER NOT NULL, username TEXT, first_name TEXT,
                role TEXT NOT NULL, text TEXT NOT NULL, ts INTEGER NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_ts ON messages(user_id, ts)")

    def _connect(self):
        return sqlite3.connect(self.path)

    def add(self, user_id, username, first_name, role, text):
        with self._connect() as conn:
            conn.execute("INSERT INTO messages(user_id, username, first_name, role, text, ts) VALUES (?, ?, ?, ?, ?, ?)", (int(user_id), username or "", first_name or "", role, text, int(time.time())))

    def recent(self, user_id, limit=20):
        with self._connect() as conn:
            rows = conn.execute("SELECT username, first_name, role, text, ts FROM messages WHERE user_id = ? ORDER BY ts DESC, rowid DESC LIMIT ?", (int(user_id), int(limit))).fetchall()
        rows.reverse()
        return [{"username": r[0], "first_name": r[1], "role": r[2], "text": r[3], "ts": r[4]} for r in rows]
