"""CLI модуля guard.

    python -m src.guard.cli draft.md --base examples/base
    python -m src.guard.cli draft.md --example examples/02-запрос-кп
    python -m src.guard.cli draft.md --base examples/base --json

Код возврата: 0 — черновик можно показывать человеку, 1 — есть ошибки.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .guard import check
from .model import ERROR

MARK = {"error": "ОШИБКА ", "warning": "внимание"}


def _stdout_utf8() -> None:
    """На Windows консоль по умолчанию не UTF-8, а отчёт на русском."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def _read_request(example_dir: Path) -> str | None:
    input_dir = example_dir / "input"
    if not input_dir.is_dir():
        return None
    parts = [
        path.read_text(encoding="utf-8")
        for path in sorted(input_dir.iterdir())
        if path.is_file()
    ]
    return "\n\n".join(parts) if parts else None


def report(verdict, draft_name: str) -> str:
    stats = verdict.to_dict()["stats"]
    lines = [
        f"Черновик: {draft_name}",
        f"Фактов проверено: {stats['claims']} · с источником: {stats['grounded']}"
        f" · без источника: {stats['ungrounded']}",
        "",
    ]

    if verdict.findings:
        lines.append("Замечания:")
        for finding in sorted(verdict.findings, key=lambda f: f.severity != ERROR):
            rule = f" [{finding.rule}]" if finding.rule else ""
            lines.append(f"  {MARK[finding.severity]}{rule} {finding.message}")
            if finding.evidence:
                lines.append(f"            └ {finding.evidence.strip()[:110]}")
        lines.append("")

    grounded = [c for c in verdict.claims if c.grounded and c.source]
    if grounded:
        lines.append("Источники:")
        for claim in grounded:
            lines.append(f"  {claim.text:>12}  ←  {claim.source}")
        lines.append("")

    lines.append("ИТОГ: черновик опирается на базу" if verdict.ok
                 else "ИТОГ: показывать нельзя — есть выдумка или нарушение регламента")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    parser = argparse.ArgumentParser(
        prog="guard", description="Проверка черновика ответа на выдумку и регламент"
    )
    parser.add_argument("draft", help="файл с черновиком ответа")
    parser.add_argument("--base", default="examples/base", help="папка базы компании")
    parser.add_argument("--request", help="файл с исходным запросом клиента")
    parser.add_argument("--example", help="папка примера приёмки (запрос возьмём из input/)")
    parser.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    args = parser.parse_args(argv)

    draft_path = Path(args.draft)
    if not draft_path.is_file():
        print(f"нет файла черновика: {draft_path}", file=sys.stderr)
        return 2
    draft = draft_path.read_text(encoding="utf-8")

    request = None
    if args.example:
        request = _read_request(Path(args.example))
    elif args.request:
        request = Path(args.request).read_text(encoding="utf-8")

    verdict = check(draft, args.base, request=request)

    if args.json:
        print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report(verdict, draft_path.name))
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
