"""Smoke test without Telegram; it uses the real local Codex CLI."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.brain import decide
from bot.index import BM25Index
DEFAULT_KB = "/Users/agent/knowledge/BUILDIN_SELECTED_EXPORT_FINAL"
def run_case(index, title, user, question, history):
    result = decide(index, user, question, history)
    return {"case": title, "question": question, "decision": result}
def main():
    index = BM25Index.from_path(os.environ.get("KB_PATH", DEFAULT_KB))
    print(json.dumps({"index_files": index.file_count, "index_chunks": len(index.chunks)}, ensure_ascii=False))
    user = {"id": 10001, "username": "test_client", "first_name": "Анна"}
    history = [{"role": "user", "text": "Меня зовут Анна, я хочу сделать вывод."}, {"role": "assistant", "text": "Анна, уточните вопрос по выводу."}]
    cases = [("knowledge_answer", "Какие ориентиры по AML risk score?", []),
             ("personalized_history", "Что будет, если кошелек для вывода грязный?", history),
             ("outside_knowledge", "Когда вы добавите торговлю акциями Apple?", [])]
    # Requests are independent; parallel execution keeps this local smoke test short.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run_case, index, title, user, question, dialog) for title, question, dialog in cases]
        for future in futures:
            print(json.dumps(future.result(), ensure_ascii=False))
if __name__ == "__main__": main()
