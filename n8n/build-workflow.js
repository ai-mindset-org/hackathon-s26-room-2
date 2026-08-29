/**
 * Собирает n8n-воркфлоу, вшивая свежий guard.js в Code-ноду.
 * Запуск:  node n8n/build-workflow.js
 * Результат: n8n/workflow.json — можно импортировать в n8n как есть.
 *
 * Правишь guard.js -> прогоняешь selftest.js -> пересобираешь этим скриптом.
 * Логика живёт в одном месте, а не в скопированном тексте внутри JSON.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const ROOT = path.resolve(HERE, '..');
const OPENAI_CREDENTIAL = { id: 'eiCWbTLWQ6dhq03J', name: 'DK ' };

const read = (p) => fs.readFileSync(p, 'utf8');

// guard.js без строчки module.exports — в Code-ноде её нет.
const guardSource = read(path.join(HERE, 'guard.js'))
  .replace(/if \(typeof module[\s\S]*$/m, '')
  .trimEnd();

const baseFiles = {};
for (const name of fs.readdirSync(path.join(ROOT, 'examples', 'base'))) {
  if (/\.(md|txt)$/i.test(name)) {
    baseFiles[name] = read(path.join(ROOT, 'examples', 'base', name));
  }
}
const dealStub = JSON.parse(read(path.join(HERE, 'fixtures', 'deal-02.json')));
const sampleRequest = read(
  path.join(ROOT, 'examples', '02-запрос-кп', 'input', 'запрос.txt')
).trim();

// ------------------------------------------------------------------ ноды

const node = (name, type, typeVersion, position, parameters, extra) =>
  Object.assign({ parameters, name, type, typeVersion, position }, extra || {});

const codeNode = (name, position, jsCode) =>
  node(name, 'n8n-nodes-base.code', 2, position, { jsCode });

const sticky = (position, width, height, content, color) =>
  node('Note ' + position.join('_'), 'n8n-nodes-base.stickyNote', 1, position, {
    content, height, width, color,
  });

const BASE_CODE = `// ЗАГЛУШКА БАЗЫ ЗНАНИЙ.
// В проде тут Supabase/Postgres retrieval — вернуть те же поля, и ничего ниже
// по цепочке менять не придётся.
const src = $input.first().json;
const request = src.request || (src.body && src.body.request) || '';

const base = ${JSON.stringify(baseFiles, null, 2)};

return [{ json: { request, base } }];`;

const DEAL_CODE = `// ЗАГЛУШКА СДЕЛКИ BITRIX24 — тот самый «пустой слот» под CRM.
// Форма данных ровно та, что вернут crm.deal.get + crm.deal.productrows.get +
// crm.contact.get. Подключение Bitrix меняет ИСТОЧНИК, а не форму:
// достаточно включить соседнюю HTTP-ноду и отдать её ответ в этом же виде.
//
// Чтобы проверить поведение без CRM — верните deal: null,
// и все проверки группы «сделка» просто промолчат.
const prev = $input.first().json;

const deal = ${JSON.stringify(dealStub, null, 2)};

return [{ json: { request: prev.request, base: prev.base, deal } }];`;

const GUARD_CODE = `${guardSource}

// ------------------------------------------------------------- вход/выход n8n
const ctx = $('Сделка Bitrix24 (заглушка)').first().json;
const incoming = $input.first().json;
const draft = incoming.output || incoming.text || incoming.draft || '';

const verdict = checkDraft({
  draft,
  request: ctx.request,
  base: ctx.base,
  deal: ctx.deal,
});

return [{ json: Object.assign({ draft }, verdict) }];`;

const AGENT_PROMPT = `=Ты готовишь ЧЕРНОВИК ответа клиенту компании «ТехноСклад».
Черновик читает человек, правит и отправляет сам.

ЗАПРОС КЛИЕНТА:
{{ $json.request }}

БАЗА КОМПАНИИ — единственный разрешённый источник фактов:

=== прайс.md ===
{{ $json.base['прайс.md'] }}

=== регламент-ответов.md ===
{{ $json.base['регламент-ответов.md'] }}

=== прошлый-ответ-доступ.md ===
{{ $json.base['прошлый-ответ-доступ.md'] }}

Верни только текст письма, без пояснений и без markdown-заголовков.`;

const AGENT_SYSTEM = `=Ты — ассистент поддержки компании «ТехноСклад».

Жёсткие правила:
1. Каждый факт, число, цену, срок и артикул бери ТОЛЬКО из базы выше. Ничего не выдумывай.
2. Цену называй всегда вместе с артикулом.
3. Скидка 7% — только для позиции от 10 шт одной позиции. Меньше 10 шт — скидки нет.
4. Не обещай «завтра» и не давай безусловных обещаний («гарантирую», «100%»). Сроки — только из прайса.
5. Если ответа в базе нет — честно скажи об этом и передай вопрос менеджеру. Не придумывай.
6. Обращайся по имени, на «вы», живым языком, без канцелярита.
7. Подпись в конце: «Команда ТехноСклад».

Ответ на проблему строй так: сначала шаги решения, потом причина, в конце — что делать,
если не помогло.

Помни: после тебя черновик проходит автоматическую проверку, которая сверяет каждое
число и артикул с базой. Выдуманный факт будет отклонён, и ответ не уйдёт клиенту.`;

const nodes = [
  node('Запустить вручную', 'n8n-nodes-base.manualTrigger', 1, [-220, 0], {}),

  node('Пример запроса', 'n8n-nodes-base.set', 3.4, [0, 0], {
    assignments: {
      assignments: [
        { id: 'req', name: 'request', value: sampleRequest, type: 'string' },
      ],
    },
    options: {},
  }),

  node('Webhook', 'n8n-nodes-base.webhook', 2, [-220, 200], {
    httpMethod: 'POST',
    path: 'answer-guard',
    options: {},
  }, { webhookId: 'a7f1c2e4-9b3d-4c5a-8e6f-1d2b3c4a5e6f' }),

  codeNode('База знаний (заглушка)', [240, 100], BASE_CODE),
  codeNode('Сделка Bitrix24 (заглушка)', [460, 100], DEAL_CODE),

  node('Bitrix24 crm.deal.get — подключить позже', 'n8n-nodes-base.httpRequest', 4.2,
    [460, 320], {
      url: 'https://ВАШ-ПОРТАЛ.bitrix24.ru/rest/1/ВЕБХУК/crm.deal.get.json',
      sendQuery: true,
      queryParameters: {
        parameters: [{ name: 'id', value: '={{ $json.deal_id }}' }],
      },
      options: {},
    }, { disabled: true }),

  node('Черновик ответа', '@n8n/n8n-nodes-langchain.agent', 1.8, [700, 100], {
    promptType: 'define',
    text: AGENT_PROMPT,
    options: { systemMessage: AGENT_SYSTEM },
  }),

  node('OpenAI Chat Model', '@n8n/n8n-nodes-langchain.lmChatOpenAi', 1.2, [700, 320], {
    model: 'gpt-4o-mini',
    options: {},
  }, { credentials: { openAiApi: OPENAI_CREDENTIAL } }),

  codeNode('ГАРД — проверка черновика', [960, 100], GUARD_CODE),

  node('Гард пропустил?', 'n8n-nodes-base.if', 2, [1200, 100], {
    conditions: {
      options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
      conditions: [
        {
          id: 'passed',
          leftValue: '={{ $json.passed }}',
          rightValue: '',
          operator: { type: 'boolean', operation: 'true', singleValue: true },
        },
      ],
      combinator: 'and',
    },
    options: {},
  }),

  node('OK — можно отправлять клиенту', 'n8n-nodes-base.set', 3.4, [1440, 0], {
    assignments: {
      assignments: [
        { id: 's', name: 'статус', value: 'проверено, можно отправлять', type: 'string' },
        { id: 'd', name: 'текст', value: '={{ $json.draft }}', type: 'string' },
        { id: 'g', name: 'фактов_с_источником', value: '={{ $json.stats.grounded }}', type: 'number' },
      ],
    },
    options: {},
  }),

  node('СТОП — на ревью менеджеру', 'n8n-nodes-base.set', 3.4, [1440, 220], {
    assignments: {
      assignments: [
        { id: 's', name: 'статус', value: 'НЕ отправлять — есть нарушения', type: 'string' },
        { id: 'd', name: 'текст', value: '={{ $json.draft }}', type: 'string' },
        {
          id: 'v',
          name: 'нарушения',
          value: '={{ $json.violations.filter(v => v.severity === "error").map(v => v.message).join("\\n") }}',
          type: 'string',
        },
      ],
    },
    options: {},
  }),

  sticky([-260, -180], 420, 150,
    '## Вход\\nРучной запуск — для демо.\\nWebhook POST /answer-guard — для интеграции:\\n`{ "request": "текст клиента" }`', 4),

  sticky([420, 440], 420, 200,
    '## Шов под Bitrix24\\nСейчас сделка приходит из заглушки.\\n\\nЧтобы подключить CRM: включить HTTP-ноду ниже,\\nотдать её ответ в том же виде\\n(products / total / currency / stage / contact_name)\\nи всё остальное продолжит работать без правок.\\n\\n`deal: null` — проверки по сделке молчат.', 3),

  sticky([940, -220], 440, 280,
    '## Гард — единственное место, где решается,\\n## увидит ли клиент этот текст\\n\\nСтоит ЖЁСТКО в цепочке, а не как tool агента:\\nмодель не может его обойти или «решить не звать».\\n\\nПроверяет:\\n· каждое число — из базы, из запроса клиента\\n  или выводится арифметикой по прайсу\\n· артикулы, email, ссылки, телефоны\\n· регламент: «вы», подпись, цена с артикулом,\\n  запрет «завтра» и безусловных обещаний\\n· сверку со сделкой из CRM\\n\\nИсходник: n8n/guard.js · тесты: node n8n/selftest.js', 6),

  sticky([1420, -180], 380, 150,
    '## Развилка\\nIF, а не Filter: у Filter один выход,\\nи забракованные черновики он молча выбрасывает.\\nЗдесь обе ветки живые — брак уходит человеку.', 5),
];

const connections = {
  'Запустить вручную': { main: [[{ node: 'Пример запроса', type: 'main', index: 0 }]] },
  'Пример запроса': { main: [[{ node: 'База знаний (заглушка)', type: 'main', index: 0 }]] },
  Webhook: { main: [[{ node: 'База знаний (заглушка)', type: 'main', index: 0 }]] },
  'База знаний (заглушка)': {
    main: [[{ node: 'Сделка Bitrix24 (заглушка)', type: 'main', index: 0 }]],
  },
  'Сделка Bitrix24 (заглушка)': {
    main: [[{ node: 'Черновик ответа', type: 'main', index: 0 }]],
  },
  'OpenAI Chat Model': {
    ai_languageModel: [[{ node: 'Черновик ответа', type: 'ai_languageModel', index: 0 }]],
  },
  'Черновик ответа': {
    main: [[{ node: 'ГАРД — проверка черновика', type: 'main', index: 0 }]],
  },
  'ГАРД — проверка черновика': {
    main: [[{ node: 'Гард пропустил?', type: 'main', index: 0 }]],
  },
  'Гард пропустил?': {
    main: [
      [{ node: 'OK — можно отправлять клиенту', type: 'main', index: 0 }],
      [{ node: 'СТОП — на ревью менеджеру', type: 'main', index: 0 }],
    ],
  },
};

const workflow = {
  name: '[TEST] [HACK] Ответ клиенту по базе + гард',
  nodes,
  connections,
  settings: { executionOrder: 'v1' },
};

const out = path.join(HERE, 'workflow.json');
fs.writeFileSync(out, JSON.stringify(workflow, null, 2), 'utf8');
console.log(
  `Собрано: ${out}\n  нод: ${nodes.length}\n  guard.js вшит: ${guardSource.length} символов`
);
