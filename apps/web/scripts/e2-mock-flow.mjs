import { chromium } from 'playwright-core';
import { readFile } from 'node:fs/promises';

const browserPath = process.env.CHROME_PATH;
if (!browserPath) throw new Error('Set CHROME_PATH to the local Chrome or Chromium executable');
const base = process.env.E2_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh/';
const browser = await chromium.launch({ executablePath: browserPath, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor();
  await page.getByRole('link', { name: 'Платёжка' }).click();
  const fixture = await readFile(new URL('../public/synthetic-receipt.png', import.meta.url));
  await page.getByLabel('Файл платёжки').setInputFiles({ name: 'demo-bill-2026-08.png', mimeType: 'image/png', buffer: fixture });
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await page.waitForURL(/\/processing\?job=/);
  await page.waitForURL(/\/review\?id=/, { timeout: 20000 });
  await page.waitForURL(/\/review\?id=/);
  await page.getByRole('img', { name: 'Страница 1 исходной платёжки' }).waitFor();
  await page.getByRole('textbox', { name: 'Тариф', exact: true }).fill('41,00');

  // Simulate a second tab changing the server revision before this form is saved.
  await page.evaluate(async () => {
    const { api } = await import('/team/zhkh/src/api/client.ts');
    const receipt = await api.receipt('10000000-0000-4000-8000-000000000001');
    await api.editReceipt(receipt.id, { expected_revision: receipt.revision, bill_data: { ...receipt.bill_data, account_number: 'server-edit' } });
  });
  await page.getByRole('button', { name: 'Сохранить исправления' }).click();
  await page.getByText('Ваши правки сохранены в форме').waitFor();
  if (await page.getByRole('textbox', { name: 'Тариф', exact: true }).inputValue() !== '41.00') throw new Error('Draft lost after revision conflict');
  await page.getByRole('button', { name: 'Применить мои правки к актуальной ревизии' }).click();
  await page.getByRole('button', { name: 'Сохранить исправления' }).click();
  await page.getByText('ревизия 3').waitFor();
  const saved = await page.evaluate(async () => {
    const { api } = await import('/team/zhkh/src/api/client.ts');
    return api.receipt('10000000-0000-4000-8000-000000000001');
  });
  if (saved.bill_data.services[0].tariff !== '41.00' || saved.bill_data.settlement.formula_kind !== 'signed_balance_v1')
    throw new Error('Saved values differ from review form or server formula');
  if (await page.getByRole('combobox', { name: 'Формула остатка' }).count()) throw new Error('Server formula is editable');
  if (await page.getByRole('combobox', { name: 'Основание суммы' }).count()) throw new Error('Server calculation kind is editable');
  if (await page.getByRole('textbox', { name: 'Код макета' }).count()) throw new Error('Server template is editable');
  await page.getByLabel(/Принимаю предупреждение/).check();
  await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
  await page.waitForURL(/\/explanation\?id=/);
  await page.getByText('К оплате по документу').waitFor();
  await page.getByRole('link', { name: 'Вернуться к документу' }).waitFor();
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  if (process.env.E2_SCREENSHOT) await page.screenshot({ path: process.env.E2_SCREENSHOT, fullPage: true });
  await page.evaluate(async () => { const { setSessionToken } = await import('/team/zhkh/src/api/client.ts'); setSessionToken('expired-session'); });
  await page.getByRole('link', { name: 'Вернуться к документу' }).click();
  await page.getByRole('button', { name: 'Войти в учебный mock' }).waitFor();
  const reviewUrl = new URL(page.url());
  if (reviewUrl.pathname !== '/team/zhkh/review' || !reviewUrl.searchParams.get('id')) throw new Error('Review route lost after 401');
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('heading', { name: 'Данные для проверки' }).waitFor();
  process.stdout.write(JSON.stringify({ flow: 'upload-poll-review-conflict-edit-confirm-explain-401', layout, route: reviewUrl.pathname }) + '\n');
} finally { await browser.close(); }
