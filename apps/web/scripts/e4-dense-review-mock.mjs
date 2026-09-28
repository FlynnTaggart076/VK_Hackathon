import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

if (!process.env.CHROME_PATH) throw new Error('Set CHROME_PATH');
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(process.env.E4_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('link', { name: 'Платёжка' }).click();
  const fixture = await readFile(new URL('../public/synthetic-receipt.png', import.meta.url));
  await page.getByLabel('Файл платёжки').setInputFiles({ name: 'synthetic.png', mimeType: 'image/png', buffer: fixture });
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await page.getByRole('link', { name: 'Проверить данные платёжки' }).click();
  await page.getByRole('heading', { name: 'Данные для проверки' }).waitFor();
  await page.evaluate(async () => {
    const { api } = await import('/team/zhkh/src/api/client.ts');
    const receipt = await api.receipt('10000000-0000-4000-8000-000000000001');
    const first = receipt.bill_data.services[0];
    const extra = Array.from({ length: 18 }, (_, index) => ({ ...first, line_id: crypto.randomUUID(),
      raw_name: `Синтетическая строка ${index + 2}`, service_code: 'other', quantity: null,
      tariff: null, charge_amount: '10.00', supplier_key: null, segment_key: null }));
    await api.editReceipt(receipt.id, { expected_revision: receipt.revision,
      bill_data: { ...receipt.bill_data, services: [first, ...extra] } });
  });
  await page.getByRole('link', { name: 'История' }).click();
  await page.locator('a[href*="review?id=10000000-0000-4000-8000-000000000001"]').click();
  await page.getByRole('heading', { name: 'Данные для проверки' }).waitFor();
  if (await page.locator('.service-row').count() !== 19) throw new Error('Not all 19 service rows rendered');
  if (await page.locator('.service-row[open]').count() !== 1) throw new Error('Dense review did not collapse extra rows');
  await page.locator('.service-row').nth(1).locator(':scope > summary').click();
  if (await page.locator('.service-row[open]').count() !== 2) throw new Error('Second service row cannot be opened');
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  process.stdout.write(JSON.stringify({ flow: 'synthetic-19-row-review-open-second-row', layout }) + '\n');
} finally { await browser.close(); }
