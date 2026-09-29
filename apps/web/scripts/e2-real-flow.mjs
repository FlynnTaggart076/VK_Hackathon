import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const { BASE_URL, DEMO_ACCESS_CODE, CHROME_PATH } = process.env;
if (!BASE_URL || !DEMO_ACCESS_CODE || !CHROME_PATH)
  throw new Error('Set BASE_URL (dev:real Vite URL), DEMO_ACCESS_CODE and CHROME_PATH outside Git');
const base = new URL(BASE_URL);
if (!base.pathname.endsWith('/team/zhkh/')) throw new Error('BASE_URL must end with /team/zhkh/');
const fixture = await readFile(new URL('../../../fixtures/receipts/demo-bill-2026-08.pdf', import.meta.url));
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(base.href, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в dev' }).waitFor({ timeout: 15000 });
  await page.getByLabel('Учётная запись').selectOption('reviewer_a');
  await page.getByLabel('Локальный код').fill(DEMO_ACCESS_CODE);
  await page.getByRole('button', { name: 'Войти в dev' }).click();
  await page.getByRole('link', { name: 'Изменить роль и территорию' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor();
  await page.getByRole('link', { name: 'Платёжка' }).click();
  await page.getByLabel('Файл платёжки').setInputFiles({ name: 'demo-bill-2026-08.pdf', mimeType: 'application/pdf', buffer: fixture });
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await page.waitForURL(/\/processing\?job=/);
  await page.waitForURL(/\/review\?id=/, { timeout: 150000 });
  await page.waitForURL(/\/review\?id=/);
  await page.getByRole('img', { name: 'Страница 1 исходной платёжки' }).waitFor({ timeout: 15000 });
  const receiptId = new URL(page.url()).searchParams.get('id');
  if (!receiptId) throw new Error('Receipt ID missing from review route');
  if (await page.getByLabel('Период (ГГГГ-ММ)').inputValue() !== '2026-08') throw new Error('OCR period differs from fixture');
  const issuer = page.getByRole('textbox', { name: 'Организация', exact: true });
  const originalIssuer = await issuer.inputValue();
  if (!originalIssuer.includes('Demo Housing Organization')) throw new Error(`Unexpected OCR issuer: ${originalIssuer}`);
  const reviewedIssuer = `${originalIssuer} (reviewed)`;
  await issuer.fill(reviewedIssuer);
  await page.getByRole('button', { name: 'Сохранить исправления' }).click();
  await page.getByText('версия 2').waitFor({ timeout: 15000 });
  if (await issuer.inputValue() !== reviewedIssuer) throw new Error('Saved issuer differs from form');
  const warnings = page.getByLabel(/Принимаю предупреждение/);
  for (let index = 0, count = await warnings.count(); index < count; index++) await warnings.nth(index).check();
  await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
  await page.waitForURL(/\/explanation\?id=/);
  await page.getByText('Расчётный итог к оплате').waitFor({ timeout: 15000 });
  await page.getByText('200.00 ₽').first().waitFor();
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  const explanationUrl = page.url();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в dev' }).waitFor();
  if (page.url() !== explanationUrl) throw new Error('Explanation route lost on reload');
  await page.getByLabel('Учётная запись').selectOption('reviewer_a');
  await page.getByLabel('Локальный код').fill(DEMO_ACCESS_CODE);
  await page.getByRole('button', { name: 'Войти в dev' }).click();
  await page.getByText('Расчётный итог к оплате').waitFor({ timeout: 15000 });
  await page.getByRole('link', { name: 'Вернуться к документу' }).click();
  await page.getByRole('textbox', { name: 'Организация', exact: true }).waitFor();
  if (await page.getByRole('textbox', { name: 'Организация', exact: true }).inputValue() !== reviewedIssuer)
    throw new Error('Saved edit was not restored from server by receipt ID');
  process.stdout.write(JSON.stringify({ mode: 'real E2 dev API', fixture: 'synthetic PDF bytes',
    receiptId, revision: 3, issuerSaved: true, explanationAfterReload: true, layout }) + '\n');
} finally { await browser.close(); }
