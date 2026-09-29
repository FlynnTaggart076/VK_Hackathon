import { chromium } from 'playwright-core';

const { CHROME_PATH } = process.env;
const base = new URL(process.env.PREVIEW_URL || 'https://flynntaggart075.asuscomm.com/team/zhkh-preview/');
if (!CHROME_PATH || base.protocol !== 'https:' || base.pathname !== '/team/zhkh-preview/')
  throw new Error('Set CHROME_PATH and an HTTPS PREVIEW_URL ending in /team/zhkh-preview/');

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const results = [];
let step = 'launch';

function monitor(page) {
  const errors = [];
  const apiStatuses = [];
  const previewAuth = [];
  const ignored = [];
  page.on('pageerror', (error) => errors.push(`page: ${error.message}`));
  page.on('console', (message) => {
    // Chrome's generic resource message has no URL; HTTP failures are checked below.
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource:'))
      errors.push(`console: ${message.text()}`);
  });
  page.on('requestfailed', (request) => {
    // Navigation cancels in-flight React requests; it is not a transport failure.
    if (request.failure()?.errorText === 'net::ERR_ABORTED') ignored.push(`navigation canceled ${new URL(request.url()).pathname}`);
    else
      errors.push(`request failed: ${new URL(request.url()).pathname} ${request.failure()?.errorText}`);
  });
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin !== base.origin) {
      if (url.hostname === 'st.max.ru') errors.push('Preview loaded MAX Bridge');
      return;
    }
    if (!url.pathname.startsWith(base.pathname) && url.pathname !== '/favicon.ico')
      errors.push(`Request escaped preview prefix: ${url.pathname}`);
    if (url.pathname.endsWith('/api/v1/auth/preview')) previewAuth.push(request.method());
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.origin !== base.origin || response.status() < 400) return;
    if (url.pathname.endsWith('/favicon.ico')) { ignored.push(`HTTP ${response.status()} ${url.pathname}`); return; }
    if (url.pathname.startsWith(`${base.pathname}api/v1/`)) apiStatuses.push(`${response.status()} ${url.pathname}`);
    else errors.push(`HTTP ${response.status()} ${url.pathname}`);
  });
  return { errors, apiStatuses, previewAuth, ignored };
}

async function layout(page, width) {
  const sizes = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (sizes.scrollWidth > sizes.width) throw new Error(`Horizontal overflow at ${width}px: ${JSON.stringify(sizes)}`);
}

async function scenario(width, territory) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  const observed = monitor(page);
  try {
    step = `${width}px: deep link, guest entry`;
    const first = await page.goto(new URL('history', base).href, { waitUntil: 'domcontentloaded' });
    if (first?.status() !== 200) throw new Error(`Deep link HTTP ${first?.status()}`);
    await page.getByRole('heading', { name: 'История документов' }).waitFor({ timeout: 20000 });
    await page.getByText('Документов пока нет.').waitFor({ timeout: 20000 });
    await page.getByRole('note').getByText('Публичный учебный стенд').waitFor();
    if (await page.getByLabel('Локальный код').count() || await page.getByText('Откройте приложение внутри MAX').count())
      throw new Error('Preview showed a login prompt');
    if (observed.previewAuth.length !== 1) throw new Error(`Expected one guest exchange, got ${observed.previewAuth.length}`);
    const firstToken = await page.evaluate(() => sessionStorage.getItem('zhkh-preview-session'));
    if (!firstToken) throw new Error('Guest session absent from tab storage');
    await layout(page, width);

    step = `${width}px: guest reload`;
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByText('Документов пока нет.').waitFor({ timeout: 20000 });
    if (observed.previewAuth.length !== 1 || await page.evaluate(() => sessionStorage.getItem('zhkh-preview-session')) !== firstToken)
      throw new Error('Reload did not restore the same guest');

    step = `${width}px: onboarding ${territory}`;
    await page.getByRole('link', { name: 'Изменить роль и территорию' }).click();
    await page.getByLabel('Ваша роль').selectOption('tenant');
    await page.getByLabel('Территория').selectOption({ label: territory });
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor({ timeout: 20000 });

    step = `${width}px: synthetic sample import and review`;
    await page.getByRole('link', { name: 'Платёжка' }).click();
    if (await page.getByLabel('Файл платёжки').count()) throw new Error('Raw upload offered in public preview');
    await page.getByRole('button', { name: 'Загрузить образец · Вода, август' }).click();
    await page.waitForURL(/\/team\/zhkh-preview\/processing\?job=/, { timeout: 20000 });
    await page.waitForURL(/\/review\?id=/, { timeout: 150000 });
    await page.getByText('Синтетический пример').first().waitFor();
    if (await page.getByLabel('Период (ГГГГ-ММ)').inputValue() !== '2026-08')
      throw new Error('August sample period differs from fixture');
    const warnings = page.getByLabel(/Принимаю предупреждение/);
    for (let i = 0, n = await warnings.count(); i < n; i++) await warnings.nth(i).check();
    await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
    await page.getByRole('heading', { name: 'Объяснение платёжки' }).waitFor({ timeout: 20000 });

    step = `${width}px: history and FAQ`;
    await page.getByRole('link', { name: 'История' }).click();
    await page.getByText('2026-08').first().waitFor({ timeout: 20000 });
    await page.getByText('Подтверждена', { exact: false }).first().waitFor();
    await page.getByRole('link', { name: 'Помощник' }).click();
    await page.getByRole('button', { name: 'Контакты поставщика' }).waitFor({ timeout: 20000 });
    await page.getByLabel('Ваш вопрос').fill('Где найти лицевой счёт?');
    await page.getByRole('button', { name: 'Спросить' }).click();
    await page.getByText('ГИС ЖКХ: Как перейти к списку лицевых счетов').waitFor({ timeout: 20000 });
    await layout(page, width);

    step = `${width}px: fresh context isolation`;
    const isolatedContext = await browser.newContext({ viewport: { width, height: 900 } });
    try {
      const isolatedPage = await isolatedContext.newPage();
      const isolated = monitor(isolatedPage);
      await isolatedPage.goto(new URL('history', base).href, { waitUntil: 'domcontentloaded' });
      await isolatedPage.getByText('Документов пока нет.').waitFor({ timeout: 20000 });
      const isolatedToken = await isolatedPage.evaluate(() => sessionStorage.getItem('zhkh-preview-session'));
      if (!isolatedToken || isolatedToken === firstToken || isolated.previewAuth.length !== 1)
        throw new Error('Fresh browser context reused the first guest');
      if (isolated.errors.length || isolated.apiStatuses.length)
        throw new Error(`Fresh context network/console errors: ${JSON.stringify(isolated)}`);
    } finally { await isolatedContext.close(); }

    if (observed.errors.length || observed.apiStatuses.length)
      throw new Error(`Network/console errors: ${JSON.stringify(observed)}`);
    results.push({ viewport: width, territory, checks: ['deep link', 'guest entry and reload', 'onboarding',
      'synthetic import/review/confirm', 'history', 'FAQ', 'fresh context isolation', 'prefix/console/network'],
      browser: browser.version(), authExchanges: observed.previewAuth.length,
      ignoredBrowserResources: [...new Set(observed.ignored)] });
  } finally { await context.close(); }
}

try {
  await scenario(360, 'Москва');
  await scenario(1280, 'Московская область');
  process.stdout.write(`${JSON.stringify({ target: base.href, results })}\n`);
} catch (error) {
  process.stderr.write(`PREVIEW LIVE QA FAILED at ${step}: ${error.stack || error}\n`);
  process.exitCode = 1;
} finally { await browser.close(); }
