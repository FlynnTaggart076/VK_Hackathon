import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const { BASE_URL, DEMO_ACCESS_CODE, CHROME_PATH } = process.env;
if (!BASE_URL || !DEMO_ACCESS_CODE || !CHROME_PATH)
  throw new Error('Set BASE_URL, DEMO_ACCESS_CODE and CHROME_PATH outside Git');
const base = new URL(BASE_URL);
if (!base.pathname.endsWith('/team/zhkh/')) throw new Error('BASE_URL must end with /team/zhkh/');
const demo = await readFile(new URL('../../../fixtures/receipts/demo-bill-2026-08.pdf', import.meta.url));
const unknown = await readFile(new URL('../../../fixtures/receipts/unknown-layout.pdf', import.meta.url));
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });

async function signIn(page) {
  await page.getByRole('button', { name: 'Войти в dev' }).waitFor({ timeout: 15000 });
  await page.getByLabel('Учётная запись').selectOption('reviewer_a');
  await page.getByLabel('Локальный код').fill(DEMO_ACCESS_CODE);
  await page.getByRole('button', { name: 'Войти в dev' }).click();
}

async function checkLayout(page, width) {
  await page.setViewportSize({ width, height: 800 });
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  if (!new URL(page.url()).pathname.startsWith('/team/zhkh/')) throw new Error('Route escaped app prefix');
}

try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  let interrupted = false;
  let simulateNetworkOutage = true;
  await page.route((url) => url.pathname === '/team/zhkh/api/v1/receipts' && url.searchParams.has('limit'), async (route) => {
    if (simulateNetworkOutage) { interrupted = true; await route.abort('failed'); }
    else await route.continue();
  });
  await page.goto(new URL('history', base).href, { waitUntil: 'domcontentloaded' });
  await signIn(page);
  await page.getByRole('button', { name: 'Повторить загрузку истории' }).waitFor({ timeout: 15000 });
  if (await page.getByText('Документов пока нет.').count()) throw new Error('Network error rendered false empty history');
  simulateNetworkOutage = false;
  await page.getByRole('button', { name: 'Повторить загрузку истории' }).click();
  await page.getByRole('button', { name: 'Повторить загрузку истории' }).waitFor({ state: 'detached' });
  if (!interrupted) throw new Error('Transport interruption was not exercised');
  await page.unrouteAll();

  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor();

  await page.getByRole('link', { name: 'Платёжка' }).click();
  await page.getByLabel('Файл платёжки').setInputFiles({
    name: 'too-large.pdf', mimeType: 'application/pdf', buffer: Buffer.concat([demo, Buffer.alloc(11 * 1024 * 1024)]),
  });
  const tooLarge = page.waitForResponse((response) => response.url().includes('/api/v1/receipts') && response.status() === 413);
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await tooLarge;
  await page.getByText('Выберите файл меньшего размера').waitFor();

  await page.getByRole('button', { name: /Загрузить образец · Вода, август/ }).click();
  await page.waitForURL(/\/processing\?job=/);
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).waitFor({ timeout: 150000 });
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).click();
  await page.waitForURL(/\/review\?id=/);
  const receiptId = new URL(page.url()).searchParams.get('id');
  if (!receiptId) throw new Error('Review route has no receipt ID');
  await page.getByText('Синтетический пример').first().waitFor();
  const issuer = page.getByRole('textbox', { name: 'Организация', exact: true });
  const originalIssuer = await issuer.inputValue();
  await issuer.fill(`${originalIssuer} (мой ввод)`);
  await page.evaluate(async (id) => {
    const { api } = await import('/team/zhkh/src/api/client.ts');
    const current = await api.receipt(id);
    await api.editReceipt(id, { expected_revision: current.revision,
      bill_data: { ...current.bill_data, issuer_name: `${current.bill_data.issuer_name} (другая вкладка)` } });
  }, receiptId);
  const conflict = page.waitForResponse((response) => response.url().includes(`/receipts/${receiptId}/draft`) && response.status() === 409);
  await page.getByRole('button', { name: 'Сохранить исправления' }).click();
  await conflict;
  await page.getByRole('button', { name: 'Применить мои правки к актуальной ревизии' }).waitFor();
  if (await issuer.inputValue() !== `${originalIssuer} (мой ввод)`) throw new Error('409 discarded unsaved local edit');
  await page.getByRole('button', { name: 'Применить мои правки к актуальной ревизии' }).click();
  await page.getByRole('button', { name: 'Сохранить исправления' }).click();
  await page.getByText('ревизия 3').first().waitFor();
  if (await issuer.inputValue() !== `${originalIssuer} (мой ввод)`) throw new Error('Conflict resolution saved different value');

  await checkLayout(page, 360);
  await checkLayout(page, 1280);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await signIn(page);
  await page.getByRole('textbox', { name: 'Организация', exact: true }).waitFor();
  if (await page.getByRole('textbox', { name: 'Организация', exact: true }).inputValue() !== `${originalIssuer} (мой ввод)`)
    throw new Error('Review state did not survive deep-link reload');
  await page.getByText('Синтетический пример').first().waitFor();
  await checkLayout(page, 1280);
  await checkLayout(page, 360);

  await page.getByRole('link', { name: 'Помощник' }).click();
  await page.getByLabel('Тема').selectOption('');
  await page.getByLabel('Ваш вопрос').fill('xyzzy неизвестное');
  await page.getByRole('button', { name: 'Спросить' }).click();
  await page.getByRole('heading', { name: 'Пока нет проверенного ответа' }).waitFor();
  if (await page.locator('article.answer').getByText('Источник:').count())
    throw new Error('Unsupported answer displayed a fabricated source');

  await page.getByRole('link', { name: 'Платёжка' }).click();
  await page.getByLabel('Файл платёжки').setInputFiles({ name: 'unknown-layout.pdf', mimeType: 'application/pdf', buffer: unknown });
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await page.waitForURL(/\/processing\?job=/);
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).waitFor({ timeout: 150000 });
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).click();
  await page.getByText('нужен ручной ввод').waitFor({ timeout: 15000 });
  await checkLayout(page, 360);

  const currentRoute = new URL(page.url()).pathname + new URL(page.url()).search;
  const expired = await page.evaluate(async () => {
    const { api, setSessionToken } = await import('/team/zhkh/src/api/client.ts');
    setSessionToken('deliberately-expired-for-e4-test');
    try { await api.me(); return null; } catch (error) { return { status: error.status, code: error.code }; }
  });
  if (expired?.status !== 401) throw new Error(`Expected real API 401, got ${JSON.stringify(expired)}`);
  await page.getByRole('heading', { name: 'Вход', exact: true }).waitFor();
  if (new URL(page.url()).pathname + new URL(page.url()).search !== currentRoute) throw new Error('401 changed deep-link route');
  process.stdout.write(JSON.stringify({ mode: 'real E4 dev API', checks: [
    'injected network abort then real retry', 'real 413', 'real 409 and preserved edit',
    'synthetic provenance', 'deep-link reload', 'unsupported without source', 'manual_required', 'real 401', '360 and 1280 px',
  ] }) + '\n');
} finally { await browser.close(); }
