/**
 * Проверка JS-порта guard против тех же фикстур, что и Python-версия.
 * Запуск из корня репозитория:  node n8n/selftest.js
 * Код возврата: 0 — всё зелёное, 1 — есть провалы.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { checkDraft } = require('./guard.js');

const ROOT = path.resolve(__dirname, '..');
const BASE_DIR = path.join(ROOT, 'examples', 'base');
const FIXTURES = path.join(ROOT, 'src', 'guard', 'fixtures');
const EXAMPLES = path.join(ROOT, 'examples');

const read = (p) => fs.readFileSync(p, 'utf8');

function loadBaseFiles() {
  const files = {};
  for (const name of fs.readdirSync(BASE_DIR)) {
    if (/\.(md|txt)$/i.test(name)) files[name] = read(path.join(BASE_DIR, name));
  }
  return files;
}

function requestOf(example) {
  const dir = path.join(EXAMPLES, example, 'input');
  return fs.readdirSync(dir).sort().map((f) => read(path.join(dir, f))).join('\n\n');
}

const BASE = loadBaseFiles();
const DEAL_02 = JSON.parse(read(path.join(__dirname, 'fixtures', 'deal-02.json')));

let passed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log('  ok   ' + name);
  } catch (err) {
    failures.push({ name, message: err.message });
    console.log('  FAIL ' + name + '\n         ' + err.message);
  }
}

const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
const codes = (v) => v.violations.map((x) => x.code);
const errorCodes = (v) => v.violations.filter((x) => x.severity === 'error').map((x) => x.code);

function run(fixture, example, deal) {
  return checkDraft({
    draft: read(path.join(FIXTURES, fixture)),
    request: requestOf(example),
    base: BASE,
    deal: deal || null,
  });
}

console.log('\nguard.js — проверка порта\n');

console.log('База и разбор прайса');
test('прайс разобран: 5 позиций, TS-192E = 33 900, срок 3 дня', () => {
  const { loadBase } = require('./guard.js');
  const idx = loadBase(BASE);
  assert(idx.priceRows.length === 5, 'позиций: ' + idx.priceRows.length);
  const row = idx.priceRows.find((r) => r.article === 'TS-192E');
  assert(row && row.price === 33900, 'цена TS-192E: ' + (row && row.price));
  assert(row.leadDays === 3, 'срок TS-192E: ' + row.leadDays);
});

test('условия скидки прочитаны из прайса (10 шт / 7%)', () => {
  const { loadBase } = require('./guard.js');
  const idx = loadBase(BASE);
  assert(idx.discountMinQty === 10, 'порог: ' + idx.discountMinQty);
  assert(idx.discountPercent === 7, 'процент: ' + idx.discountPercent);
  assert(idx.freeDeliveryFrom === 50000, 'бесплатная доставка от: ' + idx.freeDeliveryFrom);
});

test('TS-192E не даёт числа 192 (маскирование кодов)', () => {
  const { extractNumbers, maskCodes } = require('./guard.js');
  const nums = extractNumbers(maskCodes('Позиция TS-192E по цене 33 900 ₽'));
  assert(!nums.some((n) => n.value === 192), 'просочилось 192');
});

console.log('\n01 — тикет, доступ');
test('чистый черновик проходит', () => {
  const v = run('good-01.md', '01-тикет-доступ');
  assert(v.passed, 'ошибки: ' + JSON.stringify(errorCodes(v)));
});

test('отравленный ловится: ты, чужой email, телефон, «завтра», нет подписи', () => {
  const v = run('bad-01.md', '01-тикет-доступ');
  assert(!v.passed, 'должен был провалиться');
  for (const c of ['tone_ty', 'unknown_email', 'unknown_phone', 'promised_tomorrow', 'no_signature']) {
    assert(errorCodes(v).includes(c), 'нет кода ' + c + ' в ' + JSON.stringify(errorCodes(v)));
  }
});

test('выдуманный срок «6 часов» пойман (не обоснован пунктом регламента 6)', () => {
  const v = run('bad-01.md', '01-тикет-доступ');
  assert(
    v.violations.some((x) => x.code === 'ungrounded_number' && x.message.includes('6')),
    'не поймано: ' + JSON.stringify(v.violations.map((x) => x.message))
  );
});

console.log('\n02 — КП, арифметика');
test('чистое КП проходит', () => {
  const v = run('good-02.md', '02-запрос-кп');
  assert(v.passed, 'ошибки: ' + JSON.stringify(errorCodes(v)));
});

test('каждое число КП имеет источник', () => {
  const v = run('good-02.md', '02-запрос-кп');
  assert(v.stats.ungrounded === 0, 'без источника: ' + v.stats.ungrounded);
});

test('485 266 обосновано как сумма строк', () => {
  const v = run('good-02.md', '02-запрос-кп');
  const total = v.claims.find((c) => c.text === '485 266');
  assert(total, 'не найдено 485 266');
  assert(/^сумма/.test(total.source || ''), 'источник: ' + total.source);
});

test('378 324 обосновано расчётом со скидкой', () => {
  const v = run('good-02.md', '02-запрос-кп');
  const c = v.claims.find((x) => x.text === '378 324');
  assert(c && /7%/.test(c.source || ''), 'источник: ' + (c && c.source));
});

test('скидка на HDD (2 шт < 10) поймана', () => {
  const v = run('bad-02.md', '02-запрос-кп');
  assert(!v.passed, 'должен был провалиться');
  assert(errorCodes(v).includes('discount_not_earned'), JSON.stringify(errorCodes(v)));
});

console.log('\n03 — вне базы, тест на выдумку');
test('честный отказ проходит', () => {
  const v = run('good-03.md', '03-вне-базы');
  assert(v.passed, 'ошибки: ' + JSON.stringify(errorCodes(v)));
});

test('выдумка ловится: цена, артикул, «завтра», нет признания', () => {
  const v = run('bad-03.md', '03-вне-базы');
  assert(!v.passed, 'должен был провалиться');
  for (const c of ['ungrounded_number', 'unknown_article', 'promised_tomorrow']) {
    assert(errorCodes(v).includes(c), 'нет ' + c + ' в ' + JSON.stringify(errorCodes(v)));
  }
});

console.log('\nСверка со сделкой (заглушка Bitrix24)');
test('без сделки CRM-проверки молчат', () => {
  const v = run('good-02.md', '02-запрос-кп', null);
  assert(v.stats.crm === 'не подключена', v.stats.crm);
  assert(!codes(v).some((c) => c.startsWith('product_not_in_deal') || c === 'total_mismatch'));
});

test('со сделкой чистое КП по-прежнему проходит', () => {
  const v = run('good-02.md', '02-запрос-кп', DEAL_02);
  assert(v.passed, 'ошибки: ' + JSON.stringify(errorCodes(v)));
  assert(v.stats.crm === 'подключена (заглушка)', v.stats.crm);
});

test('товар вне позиций сделки ловится', () => {
  const v = checkDraft({
    draft: 'Иван, здравствуйте! Предлагаю HDD 8 TB (TS-8H) — 21 200 ₽.\n\nКоманда ТехноСклад',
    request: requestOf('02-запрос-кп'),
    base: BASE,
    deal: DEAL_02,
  });
  assert(errorCodes(v).includes('product_not_in_deal'), JSON.stringify(errorCodes(v)));
});

test('итог, расходящийся с суммой сделки, ловится', () => {
  const v = checkDraft({
    draft: 'Иван, здравствуйте!\n\nИтого: 500 000 ₽.\n\nКоманда ТехноСклад',
    request: requestOf('02-запрос-кп'),
    base: BASE,
    deal: DEAL_02,
  });
  assert(errorCodes(v).includes('total_mismatch'), JSON.stringify(errorCodes(v)));
});

test('валюта не из сделки ловится', () => {
  const v = checkDraft({
    draft: 'Иван, здравствуйте!\n\nИтого: 485 266 $.\n\nКоманда ТехноСклад',
    request: requestOf('02-запрос-кп'),
    base: BASE,
    deal: DEAL_02,
  });
  assert(errorCodes(v).includes('currency_mismatch'), JSON.stringify(errorCodes(v)));
});

test('обещание отгрузки на неподходящей стадии ловится', () => {
  const frozen = Object.assign({}, DEAL_02, {
    stage: 'Согласование КП',
    stage_allows_shipping: false,
  });
  const v = checkDraft({
    draft: 'Иван, здравствуйте!\n\nОтгрузим ваш заказ.\n\nКоманда ТехноСклад',
    request: requestOf('02-запрос-кп'),
    base: BASE,
    deal: frozen,
  });
  assert(errorCodes(v).includes('stage_conflict'), JSON.stringify(errorCodes(v)));
});

console.log('\nНовые проверки регламента');
test('безусловное обещание («гарантирую») ловится', () => {
  const v = checkDraft({
    draft: 'Иван, здравствуйте! Гарантирую поставку в срок.\n\nКоманда ТехноСклад',
    request: null,
    base: BASE,
    deal: null,
  });
  assert(errorCodes(v).includes('absolute_promise'), JSON.stringify(errorCodes(v)));
});

test('«100%» тоже ловится', () => {
  const v = checkDraft({
    draft: 'Иван, здравствуйте! Успеем на 100%.\n\nКоманда ТехноСклад',
    request: null,
    base: BASE,
    deal: null,
  });
  assert(errorCodes(v).includes('absolute_promise'), JSON.stringify(errorCodes(v)));
});

test('срок, расходящийся с прайсом, помечается', () => {
  const v = checkDraft({
    draft: 'Иван, здравствуйте! SSD 1.92 TB (TS-192E) привезём за 9 дней.\n\nКоманда ТехноСклад',
    request: null,
    base: BASE,
    deal: null,
  });
  assert(codes(v).includes('lead_time_mismatch'), JSON.stringify(codes(v)));
});

const total = passed + failures.length;
console.log(`\n${'─'.repeat(60)}`);
console.log(`Прошло ${passed} из ${total}`);
if (failures.length) {
  console.log('\nПровалы:');
  failures.forEach((f) => console.log('  · ' + f.name + ' — ' + f.message));
}
process.exit(failures.length ? 1 : 0);
