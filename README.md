# Комната 2 · Ответ клиенту по базе

<!-- aim-public-links:start -->
[Лабы AI Mindset](https://aimindset.org/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-2#learning) · [База знаний](https://base.aimindset.org/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-2)
<!-- aim-public-links:end -->

Хакатон AI Mindset S26 «Чужая боль» · 29.08.2026 · 10:00–14:00 CET

## Задача

Ответы клиентам съедают день: тикеты, холодные лиды, коммерческие предложения,
счета, отчётные документы под требования заказчика. Каждый ответ пишется
заново, хотя опирается на одну и ту же базу знаний компании.

**Строим:** инструмент, который берёт входящий запрос (письмо, тикет, бриф)
и базу компании (прайс, шаблоны, прошлые ответы, регламенты) и отдаёт черновик
ответа с источниками: почему предложено именно это и откуда цифры. Человек
правит и отправляет — последнее слово всегда за ним.

Боли заказчиков: сопровождение клиентов и холодные лиды; ежедневные ответы
в тикет-системе; составление предложений; счета с правками; ТЗ для госзакупок
и отчётная документация по контракту.

## Как работаем с кодом

- **Fork → ветка → PR.** Агент делает это сам: `gh repo fork ai-mindset-org/hackathon-s26-room-2 --clone`,
  ветка `КОД-УЧАСТНИКА/что-делаю`, `gh pr create --fill`. Мержит лидер комнаты.
- **Один участник — один модуль или папка.** Кто что берёт — решаем в комнате,
  фиксируем issues. Так PR не дерутся между собой.
- Конфликт: `git remote add upstream https://github.com/ai-mindset-org/hackathon-s26-room-2` →
  `git pull --rebase upstream main`.
- Интервью с заказчиками кладём в `docs/interview-КОД.md`.
- **Секретов в репозитории не бывает.** Репо публичный. `.env` в `.gitignore`,
  ключи живут только на вашей машине.
- После каждого мержа гоняем `examples/` — они и есть приёмка.

## Приёмка

В `examples/` лежат входы с ожидаемым результатом (собраны из болей заказчиков). Итог демо: «прошло N из M» + вердикт заказчиков
«решило / не решило». Частичный результат — тоже результат.

## Кто в комнате

Комната, зум и чекин — [hackathon-live.aimindset.org](https://hackathon-live.aimindset.org/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-2) (блок «мой код»)
Голосование и итоги — [hackathon-live.aimindset.org/vote](https://hackathon-live.aimindset.org/vote/?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-2)
Инструкция агенту — [hackathon-live.aimindset.org/skill/HACKATHON.md](https://hackathon-live.aimindset.org/skill/HACKATHON.md?utm_source=website&utm_medium=article&utm_campaign=start&utm_content=github-hackathon-s26-room-2)
