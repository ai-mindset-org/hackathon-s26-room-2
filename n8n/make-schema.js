/** Генерирует .excalidraw схему пайплайна. Кириллица -> fontFamily 2 (Helvetica). */

'use strict';

const fs = require('fs');

const OUT = process.argv[2];
const NOW = 1756468800000;
let seq = 1000;
const nid = () => 'el' + seq++;
const rnd = () => Math.floor(Math.random() * 1e9);

const elements = [];

function base(id, type, x, y, w, h, extra) {
  return Object.assign({
    id, type, x, y, width: w, height: h, angle: 0,
    strokeColor: '#1e1e1e', backgroundColor: 'transparent', fillStyle: 'solid',
    strokeWidth: 2, strokeStyle: 'solid', roughness: 1, opacity: 100,
    groupIds: [], frameId: null, roundness: null, seed: rnd(), versionNonce: rnd(),
    isDeleted: false, boundElements: null, updated: NOW, link: null, locked: false,
  }, extra || {});
}

function label(id, containerId, x, y, w, h, text, fontSize) {
  const el = base(id, 'text', x, y, w, h, {
    fontSize, fontFamily: 2, text, originalText: text,
    textAlign: 'center', verticalAlign: 'middle',
    baseline: Math.round(fontSize * 0.9), containerId, lineHeight: 1.25,
  });
  elements.push(el);
  return el;
}

function box(x, y, w, h, text, bg, opts) {
  const o = opts || {};
  const id = nid();
  const textId = nid();
  const rect = base(id, o.shape || 'rectangle', x, y, w, h, {
    backgroundColor: bg,
    roundness: o.shape === 'diamond' ? null : { type: 3 },
    strokeWidth: o.strokeWidth || 2,
    strokeStyle: o.strokeStyle || 'solid',
    strokeColor: o.strokeColor || '#1e1e1e',
    boundElements: [{ id: textId, type: 'text' }],
  });
  elements.push(rect);
  const fs_ = o.fontSize || 18;
  const lines = text.split('\n').length;
  const th = Math.round(fs_ * 1.25 * lines);
  label(textId, id, x + 10, y + (h - th) / 2, w - 20, th, text, fs_);
  return rect;
}

function note(x, y, w, text, fontSize, color) {
  const id = nid();
  const size = fontSize || 15;
  const lines = text.split('\n').length;
  elements.push(base(id, 'text', x, y, w, Math.round(size * 1.25 * lines), {
    fontSize: size, fontFamily: 2, text, originalText: text,
    textAlign: 'left', verticalAlign: 'top', baseline: Math.round(size * 0.9),
    containerId: null, lineHeight: 1.25, strokeColor: color || '#1e1e1e',
  }));
}

function arrow(from, to, opts) {
  const o = opts || {};
  const id = nid();
  const el = base(id, 'arrow', from[0], from[1], to[0] - from[0], to[1] - from[1], {
    points: [[0, 0], [to[0] - from[0], to[1] - from[1]]],
    lastCommittedPoint: null,
    startBinding: o.a ? { elementId: o.a.id, focus: 0, gap: 2 } : null,
    endBinding: o.b ? { elementId: o.b.id, focus: 0, gap: 2 } : null,
    startArrowhead: null, endArrowhead: 'arrow',
    strokeStyle: o.strokeStyle || 'solid',
    strokeColor: o.strokeColor || '#1e1e1e',
    strokeWidth: o.strokeWidth || 2,
  });
  elements.push(el);
  for (const shape of [o.a, o.b]) {
    if (!shape) continue;
    shape.boundElements = (shape.boundElements || []).concat([{ id, type: 'arrow' }]);
  }
  return el;
}

// ----------------------------------------------------------------- заголовок
note(0, -430, 1200,
  'Ответ клиенту по базе — где решается, увидит ли клиент этот текст', 30);
note(0, -385, 1400,
  'n8n: [TEST] [HACK] Ответ клиенту по базе + гард  ·  id tkCI9rpfOUNoGMzF', 16, '#666');

// ----------------------------------------------------------------- основной ряд
const Y = 0, H = 100;
const vhod   = box(0,    Y, 220, H, 'Вход\nwebhook / вручную', '#a5d8ff');
const kb     = box(300,  Y, 220, H, 'База знаний\n(заглушка)', '#ffec99');
const deal   = box(600,  Y, 230, H, 'Сделка Bitrix24\n(заглушка)', '#ffec99');
const draft  = box(910,  Y, 220, H, 'Черновик ответа\nLLM', '#d0bfff');
const guard  = box(1210, Y - 10, 250, H + 20, 'ГАРД\nпроверка кодом', '#b2f2bb',
  { strokeWidth: 4, fontSize: 20 });
const iff    = box(1540, Y - 15, 200, 130, 'прошёл?', 'transparent', { shape: 'diamond' });
const ok     = box(1830, Y - 150, 240, 100, 'OK\nотправлять клиенту', '#b2f2bb');
const stop   = box(1830, Y + 120, 240, 100, 'СТОП\nна ревью менеджеру', '#ffc9c9');

arrow([220, Y + 50], [300, Y + 50], { a: vhod, b: kb });
arrow([520, Y + 50], [600, Y + 50], { a: kb, b: deal });
arrow([830, Y + 50], [910, Y + 50], { a: deal, b: draft });
arrow([1130, Y + 50], [1210, Y + 50], { a: draft, b: guard });
arrow([1460, Y + 50], [1540, Y + 50], { a: guard, b: iff });
arrow([1690, Y + 10], [1830, Y - 100], { a: iff, b: ok });
arrow([1690, Y + 90], [1830, Y + 170], { a: iff, b: stop });

note(1700, Y - 150, 120, 'да', 18);
note(1700, Y + 175, 120, 'нет', 18);

// ----------------------------------------------------------------- шов под CRM
const bitrix = box(600, 280, 230, 100, 'Bitrix24\ncrm.deal.get', '#ffc9c9',
  { strokeStyle: 'dashed' });
arrow([715, 280], [715, 100], { a: bitrix, b: deal, strokeStyle: 'dashed', strokeColor: '#c92a2a' });
note(560, 400, 460,
  'ШОВ ПОД CRM — нода выключена.\n' +
  'Заглушка отдаёт ту же форму, что вернут\n' +
  'crm.deal.get + productrows + contact:\n' +
  'products / total / currency / stage / contact_name.\n' +
  'Подключение Bitrix меняет ИСТОЧНИК, а не логику.\n' +
  'deal: null — проверки по сделке молчат,\n' +
  'все остальные продолжают работать.', 15, '#c92a2a');

// ----------------------------------------------------------------- почему не tool
box(1150, -300, 520, 150, '', '#ffec99', { strokeStyle: 'dashed' });
note(1180, -285, 470,
  'ПОЧЕМУ ОБЫЧНОЙ НОДОЙ, А НЕ ИНСТРУМЕНТОМ АГЕНТА\n\n' +
  'toolWorkflow агент вызывает ПО СВОЕМУ РЕШЕНИЮ —\n' +
  'может и не позвать. Тогда гард наследует ровно ту\n' +
  'проблему, ради которой создан. Здесь он вшит\n' +
  'в цепочку: модель не может его обойти.', 15);

// ----------------------------------------------------------------- что проверяет
box(1150, 280, 520, 340, '', 'transparent', { strokeStyle: 'dashed' });
note(1180, 300, 470,
  'ЧТО ПРОВЕРЯЕТ ГАРД (детерминированно, без модели)\n\n' +
  'Выдумка\n' +
  '  каждое число — буквально из базы, из запроса\n' +
  '  клиента или выводится арифметикой по прайсу:\n' +
  '    406 800  <-  12 × 33 900 (TS-192E)\n' +
  '    378 324  <-  12 × 33 900 (TS-192E) − 7%\n' +
  '    485 266  <-  сумма строк\n' +
  '  артикулы, email, ссылки, телефоны\n\n' +
  'Регламент\n' +
  '  «вы», обращение по имени, подпись,\n' +
  '  цена только с артикулом, запрет «завтра»\n' +
  '  и безусловных обещаний, честное «в базе нет»\n' +
  '  + передача менеджеру\n\n' +
  'Прайс и сделка\n' +
  '  скидка 7% только от 10 шт одной позиции;\n' +
  '  товар вне позиций сделки, расхождение итога,\n' +
  '  валюта, контакт, стадия сделки', 15);

// ----------------------------------------------------------------- проверено
box(1830, 280, 240, 170, '', '#b2f2bb', { strokeStyle: 'dashed' });
note(1855, 300, 200,
  'ПРОВЕРЕНО\nна живых выполнениях n8n\n\n' +
  '158258  passed=true\n  24/24 факта с источником\n  -> OK\n\n' +
  '158259  passed=false\n  6 ошибок\n  -> СТОП', 14);

// ----------------------------------------------------------------- вход
note(-20, 150, 320,
  'webhook POST /answer-guard\n{ "request": "текст клиента" }\n\n' +
  'draft_override — прогнать через цепочку\nзаведомо плохой черновик,\nне полагаясь на ошибку модели', 14, '#1971c2');

const doc = {
  type: 'excalidraw',
  version: 2,
  source: 'https://excalidraw.com',
  elements,
  appState: { viewBackgroundColor: '#ffffff', gridSize: null },
  files: {},
};

fs.writeFileSync(OUT, JSON.stringify(doc, null, 2), 'utf8');
console.log('готово:', OUT, '| элементов:', elements.length);
