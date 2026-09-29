import { chromium } from 'playwright-core';

const { CHROME_PATH } = process.env;
const base = new URL(process.env.PREVIEW_URL ?? 'https://flynntaggart075.asuscomm.com/team/zhkh-preview/');
if (!CHROME_PATH || base.protocol !== 'https:' || base.pathname !== '/team/zhkh-preview/' ||
  base.search || base.hash || base.username || base.password)
  throw new Error('Set CHROME_PATH and an HTTPS PREVIEW_URL ending in /team/zhkh-preview/');

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const observed = { previewAuth: 0, previewQueries: 0, realQueries: 0, httpErrors: [], pageErrors: 0, consoleErrors: 0, escapedPaths: [] };
let step = 'launch';

function apiKind(pathname) {
  if (pathname.endsWith('/api/v1/auth/preview')) return 'preview-auth';
  if (pathname.includes('/api/v1/preview/receipts/') && pathname.endsWith('/city-comparison')) return 'synthetic-city';
  if (pathname.includes('/api/v1/receipts/') && pathname.endsWith('/city-comparison')) return 'real-city';
  const suffix = pathname.split('/api/v1/')[1];
  return suffix ? suffix.split('/')[0] : 'web';
}

function safeError(cause) {
  return String(cause instanceof Error ? cause.message : cause)
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/https?:\/\/[^\s)]+/gi, '[URL redacted]')
    .replace(/\b[A-Za-z0-9_-]{40,}\b/g, '[redacted]')
    .slice(0, 300);
}

function watch(page) {
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin !== base.origin) {
      if (url.hostname === 'st.max.ru') observed.escapedPaths.push('MAX Bridge');
      return;
    }
    if (!url.pathname.startsWith(base.pathname) && url.pathname !== '/favicon.ico') observed.escapedPaths.push(url.pathname);
    if (url.pathname.endsWith('/api/v1/auth/preview')) observed.previewAuth++;
    if (apiKind(url.pathname) === 'synthetic-city') observed.previewQueries++;
    if (apiKind(url.pathname) === 'real-city') observed.realQueries++;
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.origin === base.origin && response.status() >= 400 && url.pathname !== '/favicon.ico')
      observed.httpErrors.push({ status: response.status(), kind: apiKind(url.pathname) });
  });
  page.on('pageerror', () => { observed.pageErrors++; });
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource:')) observed.consoleErrors++;
  });
}

function isCityResponse(response, id) {
  const url = new URL(response.url());
  return url.origin === base.origin && url.pathname === `${base.pathname}api/v1/preview/receipts/${encodeURIComponent(id)}/city-comparison`
    && url.searchParams.get('service_code') === 'cold_water' && url.searchParams.get('metric') === 'charge_amount';
}

function verifyPayload(value, city, cityLabel, period, receiptValue, average, median, difference, percentage) {
  if (value.status !== 'available' || value.provenance !== 'synthetic_preview_cohort' || value.city !== city ||
    value.city_label !== cityLabel || value.period !== period || value.service_code !== 'cold_water' ||
    value.scope !== 'individual' || value.segment_key !== null || value.unit !== 'm3' || value.metric !== 'charge_amount' ||
    value.sample_size !== 5 || value.receipt_value !== receiptValue || value.average !== average ||
    value.median !== median || value.difference_from_average !== difference || value.difference_percent !== percentage ||
    value.comparison !== 'below' || !value.explanation?.toLowerCase().includes('учебн'))
    throw new Error(`Unexpected ${period} preview cohort shape or values`);
}

async function layout(page, width) {
  const value = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
  if (value.viewport !== width || value.document > value.viewport) throw new Error(`Horizontal overflow at ${width}px: ${JSON.stringify(value)}`);
  return value;
}

async function importAndConfirm(page, label, period) {
  await page.getByRole('link', { name: 'Платёжка' }).click();
  if (await page.getByLabel('Файл платёжки').count()) throw new Error('Public preview exposed personal-file upload');
  await page.getByRole('button', { name: `Загрузить образец · ${label}` }).click();
  await page.waitForURL(/\/team\/zhkh-preview\/processing\?job=/, { timeout: 20000 });
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).waitFor({ timeout: 150000 });
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).click();
  await page.waitForURL(/\/team\/zhkh-preview\/review\?id=/);
  await page.getByText('Синтетический пример').first().waitFor();
  if (await page.getByLabel('Период (ГГГГ-ММ)').inputValue() !== period) throw new Error(`Imported sample has an unexpected ${period} period`);
  const warnings = page.getByLabel(/Принимаю предупреждение/);
  const warningCount = await warnings.count();
  for (let index = 0; index < warningCount; index++) await warnings.nth(index).check();
  await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
  await page.getByRole('heading', { name: 'Объяснение платёжки' }).waitFor({ timeout: 20000 });
  const id = new URL(page.url()).searchParams.get('id');
  if (!id) throw new Error('Confirmed receipt ID absent');
  return { id, warningCount };
}

try {
  const context = await browser.newContext({ viewport: { width: 360, height: 850 } });
  const page = await context.newPage();
  watch(page);
  step = 'preview guest entry';
  const metaResponse = page.waitForResponse((response) => new URL(response.url()).pathname === `${base.pathname}api/v1/meta`);
  const navigation = await page.goto(new URL('history', base).href, { waitUntil: 'domcontentloaded' });
  if (navigation?.status() !== 200 || (await (await metaResponse).json()).mode !== 'preview') throw new Error('Preview web or API mode is unavailable');
  await page.getByRole('heading', { name: 'История документов' }).waitFor({ timeout: 20000 });
  await page.getByRole('note').getByText('Публичный учебный стенд').waitFor();
  const firstToken = await page.evaluate(() => sessionStorage.getItem('zhkh-preview-session'));
  if (!firstToken || observed.previewAuth !== 1)
    throw new Error('Virtual guest was not established once');
  step = 'Moscow onboarding';
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('moscow');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor({ timeout: 20000 });
  step = 'August city sample import, review, confirmation';
  const august = await importAndConfirm(page, 'Москва · август 2026', '2026-08');
  step = 'September city sample import, review, confirmation';
  const september = await importAndConfirm(page, 'Москва · сентябрь 2026', '2026-09');
  step = 'History to city comparison';
  await page.getByRole('link', { name: 'История' }).click();
  const septemberCard = page.locator('.history-list > li').filter({ hasText: '2026-09' });
  await septemberCard.getByText('Подтверждена').waitFor();
  await septemberCard.getByRole('link', { name: 'Сравнить с учебной выборкой' }).click();
  await page.getByLabel('Учебная квитанция прошлого месяца').selectOption(august.id);
  const currentResponse = page.waitForResponse((response) => isCityResponse(response, september.id));
  const olderResponse = page.waitForResponse((response) => isCityResponse(response, august.id));
  await page.getByRole('button', { name: 'Показать учебное сравнение' }).click();
  const [current, older] = await Promise.all([currentResponse, olderResponse]);
  verifyPayload(await current.json(), 'moskva', 'Москва', '2026-09', '270.00', '342.00', '315.00', '-72.00', '-21.05');
  verifyPayload(await older.json(), 'moskva', 'Москва', '2026-08', '200.00', '256.00', '240.00', '-56.00', '-21.88');
  const selected = page.locator('.notice-box').filter({ has: page.getByRole('heading', { name: 'Выбранный учебный месяц' }) });
  const previous = page.locator('.notice-box').filter({ has: page.getByRole('heading', { name: 'Предыдущий учебный месяц' }) });
  await selected.getByText('342.00 ₽').waitFor();
  await selected.getByText('270.00 ₽').waitFor();
  await previous.getByText('256.00 ₽').waitFor();
  await previous.getByText('200.00 ₽').waitFor();
  await page.getByText('Синтетическая учебная выборка — не данные жителей Москвы/МО').first().waitFor();
  if (await page.getByText('Источник: подтверждённые реальные квитанции').count() ||
    observed.realQueries !== 0 || observed.previewQueries !== 2) throw new Error('Real cohort was called or claimed in preview');
  const compact = await layout(page, 360);
  await page.setViewportSize({ width: 1280, height: 900 });
  await selected.getByText('342.00 ₽').waitFor();
  await previous.getByText('256.00 ₽').waitFor();
  const desktop = await layout(page, 1280);
  await context.close();

  step = 'independent Lyubertsy preview guest at 1280px';
  const oblastContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const oblastPage = await oblastContext.newPage();
  watch(oblastPage);
  const oblastNavigation = await oblastPage.goto(new URL('history', base).href, { waitUntil: 'domcontentloaded' });
  if (oblastNavigation?.status() !== 200) throw new Error('Independent preview guest could not open History');
  await oblastPage.getByRole('heading', { name: 'История документов' }).waitFor({ timeout: 20000 });
  const secondToken = await oblastPage.evaluate(() => sessionStorage.getItem('zhkh-preview-session'));
  if (!secondToken || secondToken === firstToken || observed.previewAuth !== 2)
    throw new Error('Independent virtual guest was not established');
  await oblastPage.getByRole('link', { name: 'Первый запуск' }).click();
  await oblastPage.getByLabel('Ваша роль').selectOption('tenant');
  await oblastPage.getByLabel('Территория').selectOption('moscow-oblast');
  await oblastPage.getByRole('checkbox').check();
  await oblastPage.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await oblastPage.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor({ timeout: 20000 });
  step = 'Lyubertsy city sample imports and confirmation';
  const oblastAugust = await importAndConfirm(oblastPage, 'Люберцы · август 2026', '2026-08');
  const oblastSeptember = await importAndConfirm(oblastPage, 'Люберцы · сентябрь 2026', '2026-09');
  await oblastPage.getByRole('link', { name: 'История' }).click();
  await oblastPage.locator('.history-list > li').filter({ hasText: '2026-09' }).getByRole('link', { name: 'Сравнить с учебной выборкой' }).click();
  await oblastPage.getByLabel('Учебная квитанция прошлого месяца').selectOption(oblastAugust.id);
  const oblastCurrentResponse = oblastPage.waitForResponse((response) => isCityResponse(response, oblastSeptember.id));
  const oblastOlderResponse = oblastPage.waitForResponse((response) => isCityResponse(response, oblastAugust.id));
  await oblastPage.getByRole('button', { name: 'Показать учебное сравнение' }).click();
  const [oblastCurrent, oblastOlder] = await Promise.all([oblastCurrentResponse, oblastOlderResponse]);
  verifyPayload(await oblastCurrent.json(), 'lyubertsy', 'Люберцы (Московская область)', '2026-09', '252.00', '319.20', '294.00', '-67.20', '-21.05');
  verifyPayload(await oblastOlder.json(), 'lyubertsy', 'Люберцы (Московская область)', '2026-08', '190.00', '243.20', '228.00', '-53.20', '-21.88');
  const oblastSelected = oblastPage.locator('.notice-box').filter({ has: oblastPage.getByRole('heading', { name: 'Выбранный учебный месяц' }) });
  const oblastPrevious = oblastPage.locator('.notice-box').filter({ has: oblastPage.getByRole('heading', { name: 'Предыдущий учебный месяц' }) });
  await oblastSelected.getByText('319.20 ₽').waitFor();
  await oblastPrevious.getByText('243.20 ₽').waitFor();
  await oblastPage.getByText('Синтетическая учебная выборка — не данные жителей Москвы/МО').first().waitFor();
  const oblastDesktop = await layout(oblastPage, 1280);
  if (observed.realQueries !== 0 || observed.previewQueries !== 4 || observed.httpErrors.length ||
    observed.pageErrors || observed.consoleErrors || observed.escapedPaths.length)
    throw new Error(`Browser or HTTP errors: ${JSON.stringify(observed)}`);
  process.stdout.write(JSON.stringify({ mode: 'real preview API', result: 'pass', checks: ['guest', 'onboarding', 'two city imports and confirmations',
    'history to synthetic current and previous month', 'independent Moscow Oblast guest', 'numeric API provenance', 'no real cohort', '360px and 1280px layout'],
    warningCounts: [august.warningCount, september.warningCount, oblastAugust.warningCount, oblastSeptember.warningCount],
    previewQueries: observed.previewQueries, realQueries: observed.realQueries, layout: [compact, desktop, oblastDesktop] }) + '\n');
  await oblastContext.close();
} catch (cause) {
  process.stderr.write(JSON.stringify({ mode: 'real preview API', result: 'fail', step,
    error: safeError(cause),
    previewQueries: observed.previewQueries, realQueries: observed.realQueries,
    httpErrors: observed.httpErrors.slice(0, 8), pageErrors: observed.pageErrors,
    consoleErrors: observed.consoleErrors, escapedPaths: observed.escapedPaths.slice(0, 4) }) + '\n');
  process.exitCode = 1;
} finally { await browser.close(); }
