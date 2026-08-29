"""Small in-memory BM25 index for Markdown knowledge-base chunks."""
import math
import os
import re
from collections import Counter, defaultdict

WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
SKIP_FILES = {"МАНИФЕСТ.csv", "ОТЧЁТ_ОБЕЗЛИЧИВАНИЯ.md"}


def tokenize(text):
    return WORD_RE.findall(text.lower())


class Chunk:
    def __init__(self, source, title, text):
        self.source, self.title, self.text = source, title, text.strip()
        self.tokens = tokenize(self.text)


class BM25Index:
    def __init__(self, chunks):
        self.chunks, self.doc_freq, self.term_freqs = chunks, defaultdict(int), []
        total = 0
        for chunk in chunks:
            terms = Counter(chunk.tokens)
            self.term_freqs.append(terms)
            total += len(chunk.tokens)
            for term in terms:
                self.doc_freq[term] += 1
        self.avg_length = float(total) / len(chunks) if chunks else 0.0

    @classmethod
    def from_path(cls, root):
        chunks, files_count = [], 0
        for current, dirs, files in os.walk(root):
            dirs.sort()
            for name in sorted(files):
                if name in SKIP_FILES:
                    continue
                path = os.path.join(current, name)
                if name.lower().endswith(".md"):
                    files_count += 1
                    chunks.extend(_markdown_chunks(path, root))
                elif name.endswith(".caption.txt"):
                    files_count += 1
                    chunks.extend(_caption_chunks(path, root))
        index = cls(chunks)
        index.file_count = files_count
        return index

    def search(self, query, limit=6):
        terms = tokenize(query)
        if not terms or not self.chunks:
            return []
        scores, docs = [], len(self.chunks)
        for pos, frequencies in enumerate(self.term_freqs):
            length, score = len(self.chunks[pos].tokens), 0.0
            for term in terms:
                tf = frequencies.get(term, 0)
                if tf:
                    idf = math.log(1.0 + (docs - self.doc_freq[term] + .5) / (self.doc_freq[term] + .5))
                    score += idf * tf * 2.5 / (tf + 1.5 * (1.0 - .75 + .75 * length / (self.avg_length or 1.0)))
            if score:
                scores.append((score, self.chunks[pos]))
        scores.sort(key=lambda item: item[0], reverse=True)
        return [{"score": round(score, 3), "source": chunk.source, "title": chunk.title, "text": chunk.text} for score, chunk in scores[:limit]]


def _markdown_chunks(path, root):
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeError):
        return []
    output, title, buffer = [], os.path.basename(path), []
    def flush():
        if buffer and any(line.strip() for line in buffer):
            output.append(Chunk(os.path.relpath(path, root), title, "\n".join(buffer)))
    for line in lines:
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            flush(); title, buffer = line.lstrip("#").strip(), [line]
        elif len(buffer) >= 120:
            flush(); buffer = ["(продолжение: %s)" % title, line]
        else:
            buffer.append(line)
    flush()
    return output


def _caption_chunks(path, root):
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read().strip()
    except (OSError, UnicodeError):
        return []
    if not text:
        return []
    image = path[:-len(".caption.txt")]
    section = os.path.dirname(os.path.dirname(path))
    section_md = next((name for name in sorted(os.listdir(section)) if name.lower().endswith(".md")), "") if os.path.isdir(section) else ""
    source = os.path.relpath(image, root)
    if section_md:
        source += " | раздел: " + os.path.relpath(os.path.join(section, section_md), root)
    return [Chunk(source, "Описание скриншота", text)]
