/**
 * guard.js — проверка черновика ответа клиенту: выдумка + регламент + сверка со сделкой.
 *
 * Порт Python-модуля src/guard на чистый JS, чтобы жить в n8n Code-ноде
 * без внешних зависимостей, без деплоя и без Python-песочницы.
 *
 * Контракт (вход):
 *   {
 *     request: "текст запроса клиента",
 *     draft:   "текст черновика ответа",
 *     base:    { "прайс.md": "...", "регламент-ответов.md": "...", ... },
 *     deal:    null | {
 *       id, currency, total, stage, stage_allows_shipping,
 *       contact_name, products: [{article, name, price, quantity}]
 *     }
 *   }
 *
 * Контракт (выход):
 *   { passed, stats: {...}, violations: [...], claims: [...] }
 *
 * deal === null означает «CRM не подключена» — проверки группы «сделка»
 * молча пропускаются, остальные работают. Это и есть шов для Bitrix24.
 */

'use strict';

const ERROR = 'error';
const WARNING = 'warning';

// Пробелы, которыми в русском тексте разделяют разряды: обычный, неразрывный, узкий.
const THIN = '    ';
const NUM_RE = new RegExp(
  '\\d{1,3}(?:[' + THIN + ']\\d{3})+(?:[.,]\\d+)?|\\d+(?:[.,]\\d+)?',
  'g'
);

// В JS \b и \w НЕ понимают кириллицу (\w === [A-Za-z0-9_]), поэтому и границы
// слова, и «хвост» русского слова задаём явно. Иначе «скидк\w*» молча никогда
// не сработает — самая коварная ошибка при переносе с Python.
const WORD = 'А-Яа-яЁёA-Za-z0-9_';
const RW = '[а-яёА-ЯЁ]'; // одна русская буква
const word = (body, flags) =>
  new RegExp('(?<![' + WORD + '])(?:' + body + ')(?![' + WORD + '])', flags || 'i');

const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
const ARTICLE_RE = /\b[A-Z]{2,}-[A-Z0-9]{1,8}\b/g;
const URL_RE = /https?:\/\/[^\s)\]]+|\b[\w-]+\.(?:ru|com|example|org|net)\b/g;
const CODE_RE = /\b[A-Za-z]{2,}-[A-Za-z0-9]+\b/g;
const PHONE_RE = /(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b/g;

const CONTEXT = 28;
const TOLERANCE = 0.5;
const MAX_SUM_TERMS = 6;

const MONEY_HINTS = ['₽', 'руб', 'цена', 'цен', 'стоим', 'сумм', 'итого', 'скидк', 'прайс'];
const DURATION_HINTS = ['дн', 'день', 'дня', 'час', 'недел', 'месяц', 'срок'];

// ---------------------------------------------------------------- числа

function normalize(raw) {
  let cleaned = raw;
  for (const space of THIN) cleaned = cleaned.split(space).join('');
  return parseFloat(cleaned.replace(',', '.'));
}

function maskCodes(text) {
  // TS-192E не должен подарить черновику «число» 192.
  return String(text || '').replace(CODE_RE, (m) => ' '.repeat(m.length));
}

function classify(text, start, end, raw) {
  const before = text.slice(Math.max(0, start - CONTEXT), start).toLowerCase();
  const after = text.slice(end, end + CONTEXT).toLowerCase();

  const tail = before.replace(/\s+$/, '');
  if (/(п\.|№|#|пункт)$/.test(tail)) return 'reference';

  // Маркер нумерованного списка «1.» / «2)» — разметка, а не факт о мире.
  const lineHead = before.split('\n').pop();
  if (!lineHead.replace(/[\s\t\-*]/g, '') && /^[.)][\s\t]/.test(after)) return 'reference';

  if (after.trimStart().startsWith('%') || after.slice(0, 8).includes('%')) return 'percent';
  if (after.slice(0, 10).includes('шт')) return 'qty';
  if (DURATION_HINTS.some((h) => after.slice(0, 14).includes(h))) return 'duration';
  if (after.slice(0, 10).includes('₽')) return 'money';
  if (MONEY_HINTS.some((h) => after.slice(0, 14).includes(h))) return 'money';
  if (MONEY_HINTS.some((h) => before.slice(-20).includes(h))) return 'money';
  if ([...THIN].some((s) => raw.includes(s))) return 'money';
  return 'other';
}

function extractNumbers(text) {
  const src = String(text || '');
  const found = [];
  let match;
  NUM_RE.lastIndex = 0;
  while ((match = NUM_RE.exec(src)) !== null) {
    const raw = match[0];
    const start = match.index;
    const end = start + raw.length;
    found.push({
      value: normalize(raw),
      raw,
      kind: classify(src, start, end, raw),
      line: src.slice(0, start).split('\n').length,
      context: src.slice(Math.max(0, start - CONTEXT), end + CONTEXT).replace(/\n/g, ' ').trim(),
    });
  }
  return found;
}

// ---------------------------------------------------------------- база

function splitRow(line) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
}

function parseLeadTime(raw) {
  const lowered = String(raw || '').toLowerCase();
  if (lowered.includes('налич')) return 0;
  const m = /(\d+)/.exec(raw || '');
  return m ? parseInt(m[1], 10) : null;
}

function parsePriceTable(text, source) {
  const rows = [];
  let header = null;
  for (const line of String(text).split('\n')) {
    if (!line.trim().startsWith('|')) {
      header = null;
      continue;
    }
    const cells = splitRow(line);
    if (cells.filter(Boolean).every((c) => /^:?-{2,}:?$/.test(c))) continue;
    if (header === null) {
      header = cells.map((c) => c.toLowerCase());
      continue;
    }
    const column = (...keys) => {
      for (let i = 0; i < header.length; i++) {
        if (keys.some((k) => header[i].includes(k)) && i < cells.length) return cells[i];
      }
      return '';
    };
    const article = column('артикул');
    const priceRaw = column('цена', 'стоим');
    if (!article || !priceRaw) continue;
    NUM_RE.lastIndex = 0;
    const digits = NUM_RE.exec(priceRaw);
    if (!digits) continue;
    rows.push({
      name: column('позиция', 'наименование', 'товар') || cells[0],
      article,
      price: normalize(digits[0]),
      leadDays: parseLeadTime(column('срок', 'постав')),
      source,
    });
  }
  return rows;
}

function loadBase(files) {
  const index = {
    files: files || {},
    numbers: new Map(),
    emails: new Set(),
    articles: new Set(),
    urls: new Set(),
    priceRows: [],
    discountMinQty: null,
    discountPercent: null,
    freeDeliveryFrom: null,
    allText: '',
  };

  for (const [name, text] of Object.entries(index.files)) {
    index.allText += '\n' + text;

    for (const n of extractNumbers(text)) {
      // Номера пунктов регламента — не факты: иначе «6. Подпись» обоснует «6 часов».
      if (n.kind === 'reference') continue;
      if (!index.numbers.has(n.value)) index.numbers.set(n.value, name + ':' + n.line);
    }

    (text.match(EMAIL_RE) || []).forEach((e) => index.emails.add(e));
    (text.match(ARTICLE_RE) || []).forEach((a) => index.articles.add(a));
    (text.match(URL_RE) || []).forEach((u) => index.urls.add(u.toLowerCase()));
    index.priceRows.push(...parsePriceTable(text, name));

    const disc = new RegExp(
      `скидк${RW}*\\s+от\\s+(\\d+)\\s*шт[^.]*?(\\d+(?:[.,]\\d+)?)\\s*%`, 'i'
    ).exec(text);
    if (disc) {
      index.discountMinQty = parseInt(disc[1], 10);
      index.discountPercent = normalize(disc[2]);
    }
    const deliv = /доставка[^.]*?бесплатн[а-яёА-ЯЁ]*\s+от\s+([\d    ]+)/i.exec(text);
    if (deliv) index.freeDeliveryFrom = normalize(deliv[1].trim());
  }

  index.priceRows.forEach((r) => index.articles.add(r.article));
  return index;
}

function hasNumber(index, value) {
  for (const [known, src] of index.numbers) {
    if (Math.abs(known - value) <= 0.01) return src;
  }
  return null;
}

function priceOf(index, article) {
  const up = String(article).toUpperCase();
  return index.priceRows.find((r) => r.article.toUpperCase() === up) || null;
}

// ---------------------------------------------------------------- вывод чисел

const close = (a, b) => Math.abs(a - b) <= TOLERANCE;
const money = (n) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

function fromPriceMath(value, index, quantities) {
  const disc = index.discountPercent;
  for (const row of index.priceRows) {
    for (const qty of quantities) {
      if (qty <= 0) continue;
      const lineTotal = qty * row.price;
      if (close(value, lineTotal)) {
        return { source: `расчёт: ${qty} × ${money(row.price)} (${row.article})`, earned: true };
      }
      if (disc === null) continue;
      const discounted = lineTotal * (1 - disc / 100);
      if (close(value, discounted) || close(value, Math.round(discounted))) {
        const earned = index.discountMinQty === null || qty >= index.discountMinQty;
        return {
          source: `расчёт: ${qty} × ${money(row.price)} (${row.article}) − ${disc}%`,
          earned,
          qty,
          article: row.article,
        };
      }
    }
  }
  return null;
}

function fromSum(value, parts) {
  const usable = parts.filter((p) => p > 0 && !close(p, value));
  if (usable.length < 2) return null;
  const max = Math.min(MAX_SUM_TERMS, usable.length);

  const walk = (start, chosen, sum) => {
    if (chosen.length >= 2 && close(sum, value)) return chosen.slice();
    if (chosen.length >= max) return null;
    for (let i = start; i < usable.length; i++) {
      chosen.push(usable[i]);
      const hit = walk(i + 1, chosen, sum + usable[i]);
      if (hit) return hit;
      chosen.pop();
    }
    return null;
  };

  const combo = walk(0, [], 0);
  return combo ? { source: 'сумма: ' + combo.map(money).join(' + ') } : null;
}

// ---------------------------------------------------------------- проверки

function paragraphs(text) {
  const result = [];
  let lineNo = 1;
  for (const block of String(text).split(/\n\s*\n/)) {
    result.push({ line: lineNo, text: block });
    lineNo += (block.match(/\n/g) || []).length + 2;
  }
  return result;
}

const TY_RE = word('ты|тебе|тебя|твой|твоя|твои|твоего|тобой');
const TOMORROW_RE = word('завтра|послезавтра');
const SOON_RE = /(сегодня же|в течение дня|в ближайшее время|максимально быстро)/i;
const ABSOLUTE_RE = word(
  `гарантиру${RW}*|стопроцентн${RW}*|точно успе${RW}*|обязательно успе${RW}*`
);
const HUNDRED_RE = /\b100\s?%/;
const SIGNATURE = 'команда техносклад';
const NET = `(?<![${WORD}])нет(?![${WORD}])`;
const ADMISSION_RE = new RegExp(
  `(?:(?:в\\s+)?(?:баз${RW}+|прайс${RW}+|наличи${RW}+)[^.!?]{0,60}?${NET}` +
    `|${NET}[^.!?]{0,60}?(?:в\\s+)?(?:баз${RW}+|прайс${RW}+|наличи${RW}+)` +
    `|отсутств${RW}*|не\\s+найд${RW}*|не\\s+поставля${RW}*|не\\s+значится` +
    `|не\\s+мог${RW}*\\s+(?:назвать|подтвердить|обещать))`,
  'i'
);
const HANDOFF_RE = /(менеджер|переда|свяж)/i;
const TOPIC_LEXICON = [
  'юан', 'доллар', 'евро', 'рассрочк', 'отсрочк', 'лизинг', 'аккредитив',
  'библиотек', 'ленточн', 'стример', 'коммутатор', 'лицензи', 'гаранти',
  'монтаж', 'аренд', 'утилизац',
];

function unknownTopics(request, index) {
  const found = [];
  const lowered = String(request || '').toLowerCase();
  const baseLower = index.allText.toLowerCase();

  for (const token of String(request || '').match(/\b[A-Za-z]{2,}(?:-\d+)?\b/g) || []) {
    if (token.length < 3) continue;
    if (baseLower.includes(token.toLowerCase())) continue;
    if (!found.some((f) => f.toUpperCase() === token.toUpperCase())) found.push(token);
  }
  for (const topic of TOPIC_LEXICON) {
    if (lowered.includes(topic) && !baseLower.includes(topic)) found.push(topic);
  }
  return found;
}

function candidateNames(request) {
  const stop = new Set([
    'ооо', 'ип', 'зао', 'оао', 'клиент', 'тикет', 'здравствуйте', 'добрый',
    'день', 'привет', 'как', 'можно', 'заказ', 'спасибо', 'прима',
  ]);
  const names = [];
  for (const m of String(request || '').matchAll(/([А-ЯЁ][а-яё]{2,})/g)) {
    if (!stop.has(m[1].toLowerCase())) names.push(m[1]);
  }
  return names;
}

// ---------------------------------------------------------------- главное

function checkDraft(input) {
  const draft = String(input.draft || '');
  const request = input.request ? String(input.request) : null;
  const deal = input.deal || null;
  const index = loadBase(input.base || {});

  const violations = [];
  const claims = [];
  const add = (code, severity, message, extra) =>
    violations.push(Object.assign({ code, severity, message }, extra || {}));

  // --- количества: явные «12 шт» точнее случайных чисел
  const collectQty = (kinds) => {
    const out = [];
    for (const text of [request || '', draft]) {
      for (const n of extractNumbers(maskCodes(text))) {
        if (kinds.includes(n.kind) && Number.isInteger(n.value)) {
          if (n.value >= 1 && n.value <= 10000 && !out.includes(n.value)) out.push(n.value);
        }
      }
    }
    return out;
  };
  const quantities = collectQty(['qty']).length
    ? collectQty(['qty'])
    : collectQty(['qty', 'other']);

  // --- заземление чисел
  const requestNumbers = new Set(
    request ? extractNumbers(maskCodes(request)).map((n) => n.value) : []
  );
  const found = extractNumbers(maskCodes(draft)).filter((n) => n.kind !== 'reference');
  const numberClaims = found.map((n) => ({
    text: n.raw, kind: n.kind, line: n.line, grounded: false, source: null, context: n.context,
  }));

  found.forEach((item, i) => {
    const claim = numberClaims[i];
    const literal = hasNumber(index, item.value);
    if (literal) { claim.grounded = true; claim.source = 'база: ' + literal; return; }
    if (requestNumbers.has(item.value)) {
      claim.grounded = true; claim.source = 'запрос клиента'; return;
    }
    const computed = fromPriceMath(item.value, index, quantities);
    if (computed) {
      claim.grounded = true;
      claim.source = computed.source;
      if (computed.earned === false) {
        add('discount_not_earned', ERROR,
          `Скидка применена к позиции, где её нет: ${item.raw} (порог — ${index.discountMinQty} шт)`,
          { evidence: item.context, line: item.line, rule: 'прайс: условия скидки' });
      }
    }
  });

  for (let pass = 0; pass < 2; pass++) {
    const anchors = found
      .map((item, i) => (numberClaims[i].grounded && item.kind === 'money' ? item.value : null))
      .filter((v) => v !== null);
    found.forEach((item, i) => {
      const claim = numberClaims[i];
      if (claim.grounded || item.kind !== 'money') return;
      const summed = fromSum(item.value, anchors);
      if (summed) { claim.grounded = true; claim.source = summed.source; }
    });
  }

  found.forEach((item, i) => {
    const claim = numberClaims[i];
    if (claim.grounded) return;
    const hard = ['money', 'duration', 'percent'].includes(item.kind) ||
      (item.kind === 'qty' && request !== null);
    add('ungrounded_number', hard ? ERROR : WARNING,
      `Число ${item.raw} не выводится из базы`,
      { evidence: item.context, line: item.line, rule: 'регламент п.5' });
  });
  claims.push(...numberClaims);

  // --- заземление сущностей
  const asked = (request || '').toLowerCase();
  const addEntity = (text, kind, known, message) => {
    const quoted = Boolean(asked) && asked.includes(text.toLowerCase());
    claims.push({
      text, kind, line: 0, grounded: known || quoted,
      source: known ? 'база' : quoted ? 'запрос клиента' : null,
    });
    if (!known && !quoted) {
      add('unknown_' + kind, ERROR, message, { evidence: text, rule: 'регламент п.5' });
    }
  };

  new Set(draft.match(EMAIL_RE) || []).forEach((e) =>
    addEntity(e, 'email', index.emails.has(e), `Адрес ${e} отсутствует в базе`));

  const knownArticles = new Set([...index.articles].map((a) => a.toUpperCase()));
  const dealArticles = new Set(
    (deal && deal.products ? deal.products : []).map((p) => String(p.article).toUpperCase())
  );
  new Set(draft.match(ARTICLE_RE) || []).forEach((a) => {
    const known = knownArticles.has(a.toUpperCase()) || dealArticles.has(a.toUpperCase());
    addEntity(a, 'article', known, `Артикул ${a} отсутствует в прайсе`);
  });

  new Set((draft.match(URL_RE) || []).map((u) => u.toLowerCase())).forEach((u) => {
    if (u.includes('@')) return;
    addEntity(u, 'url', index.urls.has(u), `Ссылка ${u} отсутствует в базе`);
  });

  // Телефон: свой (из базы/CRM/запроса) — можно, чужой — утечка ПДн.
  const ownPhones = new Set();
  (index.allText.match(PHONE_RE) || []).forEach((p) => ownPhones.add(p.replace(/\D/g, '')));
  if (deal && deal.contact_phone) ownPhones.add(String(deal.contact_phone).replace(/\D/g, ''));
  new Set(draft.match(PHONE_RE) || []).forEach((p) => {
    const digits = p.replace(/\D/g, '');
    const known = ownPhones.has(digits);
    addEntity(p, 'phone', known, `Телефон ${p} не из базы и не от клиента — возможна утечка ПДн`);
  });

  // --- регламент
  const ty = TY_RE.exec(draft);
  if (ty) add('tone_ty', ERROR, 'Обращение на «ты» — регламент требует «вы»',
    { evidence: ty[0], rule: 'регламент п.1' });

  if (request) {
    const names = candidateNames(request);
    if (names.length && !names.some((n) => draft.toLowerCase().includes(n.toLowerCase()))) {
      add('no_name', WARNING, `Нет обращения по имени (в запросе: ${names.slice(0, 3).join(', ')})`,
        { rule: 'регламент п.1' });
    }
  }

  const knownPrices = new Map(index.priceRows.map((r) => [r.price, r.article]));
  for (const block of paragraphs(draft)) {
    const here = new Set(block.text.match(ARTICLE_RE) || []);
    for (const n of extractNumbers(block.text)) {
      const article = knownPrices.get(n.value);
      if (article && !here.has(article)) {
        add('price_without_article', ERROR,
          `Цена ${n.raw} названа без артикула (${article})`,
          { evidence: n.context, line: block.line, rule: 'регламент п.3' });
      }
    }
  }

  const tomorrow = TOMORROW_RE.exec(draft);
  if (tomorrow) add('promised_tomorrow', ERROR,
    'Обещано «завтра» — сроки берём только из прайса',
    { evidence: tomorrow[0], rule: 'регламент п.4' });

  const soon = SOON_RE.exec(draft);
  if (soon) add('vague_deadline', WARNING, 'Расплывчатый срок вместо срока из прайса',
    { evidence: soon[0], rule: 'регламент п.4' });

  const absolute = ABSOLUTE_RE.exec(draft) || HUNDRED_RE.exec(draft);
  if (absolute) add('absolute_promise', ERROR,
    'Безусловное обещание — так обещать нельзя',
    { evidence: absolute[0], rule: 'регламент п.4' });

  // Срок из прайса против срока, обещанного рядом с артикулом.
  for (const block of paragraphs(draft)) {
    for (const article of new Set(block.text.match(ARTICLE_RE) || [])) {
      const row = priceOf(index, article);
      if (!row || row.leadDays === null) continue;
      for (const n of extractNumbers(maskCodes(block.text))) {
        if (n.kind !== 'duration') continue;
        if (n.value !== row.leadDays && n.value !== 0) {
          add('lead_time_mismatch', WARNING,
            `Срок ${n.raw} рядом с ${article} расходится с прайсом (${row.leadDays} дн.)`,
            { evidence: n.context, line: block.line, rule: 'прайс: срок поставки' });
        }
      }
    }
  }

  const topics = request ? unknownTopics(request, index) : [];
  if (topics.length) {
    if (!ADMISSION_RE.test(draft)) {
      add('no_admission', ERROR,
        `В базе нет ответа (${topics.slice(0, 3).join(', ')}), но черновик об этом не говорит`,
        { rule: 'регламент п.5' });
    }
    if (!HANDOFF_RE.test(draft)) {
      add('no_handoff', ERROR, 'Нет передачи менеджеру по вопросу вне базы',
        { rule: 'регламент п.5' });
    }
  }

  if (!draft.toLowerCase().includes(SIGNATURE)) {
    add('no_signature', ERROR, 'Нет подписи «Команда ТехноСклад»', { rule: 'регламент п.6' });
  }

  // --- сверка со сделкой (пропускается, если CRM не подключена)
  if (deal) {
    const inDeal = new Set((deal.products || []).map((p) => String(p.article).toUpperCase()));
    for (const a of new Set(draft.match(ARTICLE_RE) || [])) {
      if (inDeal.size && !inDeal.has(a.toUpperCase()) && !asked.includes(a.toLowerCase())) {
        add('product_not_in_deal', ERROR,
          `Артикул ${a} не входит в позиции сделки ${deal.id} и не запрошен клиентом`,
          { evidence: a, rule: 'CRM: позиции сделки' });
      }
    }

    if (deal.total !== undefined && deal.total !== null) {
      // Итогом считаем только число на строке со словом «итого», и только правее
      // этого слова. Окно контекста ±28 символов перетекает на соседнюю строку,
      // из-за чего последняя строка таблицы принималась за итог.
      const TOTAL_WORD = /(итого|к оплате|всего)/i;
      String(maskCodes(draft)).split('\n').forEach((lineText, i) => {
        const keyword = TOTAL_WORD.exec(lineText);
        if (!keyword) return;
        // Итог — ПЕРВОЕ денежное число правее слова «итого». Остальные числа на
        // той же строке (порог бесплатной доставки и т.п.) итогом не являются.
        let total = null;
        let m;
        NUM_RE.lastIndex = 0;
        while ((m = NUM_RE.exec(lineText)) !== null) {
          if (m.index <= keyword.index) continue;
          if (classify(lineText, m.index, m.index + m[0].length, m[0]) !== 'money') continue;
          total = { raw: m[0], value: normalize(m[0]) };
          break;
        }
        if (total && !close(total.value, deal.total)) {
          add('total_mismatch', ERROR,
            `Итог ${total.raw} расходится с суммой сделки ${money(deal.total)}`,
            { evidence: lineText.trim(), line: i + 1, rule: 'CRM: сумма сделки' });
        }
      });
    }

    if (deal.currency) {
      const symbols = { RUB: '₽', USD: '$', EUR: '€' };
      for (const [code, sign] of Object.entries(symbols)) {
        if (code !== deal.currency && draft.includes(sign)) {
          add('currency_mismatch', ERROR,
            `В черновике валюта ${sign}, а в сделке ${deal.currency}`,
            { evidence: sign, rule: 'CRM: валюта сделки' });
        }
      }
    }

    if (deal.contact_name && !draft.toLowerCase().includes(String(deal.contact_name).toLowerCase())) {
      add('contact_name_mismatch', WARNING,
        `Обращение не к контакту сделки (${deal.contact_name})`,
        { rule: 'CRM: контакт сделки' });
    }

    if (deal.stage_allows_shipping === false) {
      const ship = word(
        `отгру[зж]${RW}*|отправ${RW}*\\s+сегодня|резервиру${RW}*`
      ).exec(draft);
      if (ship) {
        add('stage_conflict', ERROR,
          `Обещание «${ship[0]}» противоречит стадии сделки (${deal.stage})`,
          { evidence: ship[0], rule: 'CRM: стадия сделки' });
      }
    }
  }

  const errors = violations.filter((v) => v.severity === ERROR);
  return {
    passed: errors.length === 0,
    stats: {
      claims: claims.length,
      grounded: claims.filter((c) => c.grounded).length,
      ungrounded: claims.filter((c) => !c.grounded).length,
      errors: errors.length,
      warnings: violations.length - errors.length,
      crm: deal ? 'подключена (заглушка)' : 'не подключена',
    },
    violations,
    claims,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { checkDraft, loadBase, extractNumbers, maskCodes };
}
