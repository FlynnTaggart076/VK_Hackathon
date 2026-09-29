// «Вид услуги» is a list where every service can be picked once; changing it brings unit and area with it.
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

if (!process.env.CHROME_PATH) throw new Error('Set CHROME_PATH');
const base = process.env.E5_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const fail = (message) => { throw new Error(message); };
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('link', { name: 'Платёжка' }).click();
  const fixture = await readFile(new URL('../public/synthetic-receipt.png', import.meta.url));
  await page.getByLabel('Файл платёжки').setInputFiles({ name: 'demo-bill-2026-08.png', mimeType: 'image/png', buffer: fixture });
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await page.waitForURL(/\/review\?id=/, { timeout: 20000 });
  await page.getByRole('heading', { name: 'Данные для проверки' }).waitFor();

  const kinds = () => page.getByLabel('Вид услуги');
  const options = async (index) => kinds().nth(index).evaluate((select) =>
    [...select.options].map((option) => ({ text: option.textContent, value: option.value, disabled: option.disabled })));
  const state = (list, value) => list.find((option) => option.value === value);

  // The mock receipt has one line with «Холодная вода»; a new line starts as «Прочее».
  await page.getByRole('button', { name: 'Добавить строку' }).click();
  const second = await options(1);
  if (!state(second, 'cold_water').disabled || !state(second, 'cold_water').text.includes('уже выбрано в строке 1'))
    fail(`Холодная вода must be taken in the new line: ${JSON.stringify(state(second, 'cold_water'))}`);
  if (state(second, 'other').disabled) fail('«Прочее» must always stay available');
  if (state(second, 'electricity').disabled) fail('A free service must be available');

  // Picking a service in the new line takes it away from the first one.
  await kinds().nth(1).selectOption('electricity');
  if (!state(await options(0), 'electricity').disabled) fail('Электроэнергия must be unavailable in line 1 once line 2 uses it');
  if (state(await options(1), 'cold_water').disabled === false) fail('Холодная вода must stay unavailable in line 2');
  if (await page.locator('.service-row').nth(1).getByLabel('Единица').inputValue() !== 'kwh') fail('The unit must follow the service');

  // Removing the line frees the service again.
  await page.locator('.service-row').nth(1).getByRole('button', { name: 'Удалить строку' }).click();
  if (state(await options(0), 'electricity').disabled) fail('A removed line must free its service');

  // Changing the first line keeps the printed name and the charge, and resets what no longer fits.
  await page.getByLabel('Объём').first().fill('5');
  await page.getByLabel('Тариф', { exact: true }).first().fill('40.00');
  await kinds().nth(0).selectOption('electricity');
  const line = page.locator('.service-row').first();
  if (await line.getByLabel('Единица').inputValue() !== 'kwh') fail('Unit must switch to kWh');
  if (await line.getByLabel('Название в квитанции').inputValue() !== 'Холодная вода') fail('The printed name must stay');
  if (await line.getByLabel('Сумма, ₽').inputValue() !== '200.00') fail('The charge must stay');
  if (await line.getByLabel('Объём').inputValue() !== '' || await line.getByLabel('Тариф', { exact: true }).inputValue() !== '')
    fail('Volume and tariff of another unit must be cleared');
  await line.getByText('Объём и тариф сброшены').waitFor();

  // Going back to the original service restores the loaded values.
  await kinds().nth(0).selectOption('cold_water');
  if (await line.getByLabel('Единица').inputValue() !== 'm3') fail('Unit must come back with the original service');
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) fail(`Horizontal overflow: ${JSON.stringify(layout)}`);
  process.stdout.write(JSON.stringify({ flow: 'service-kind-unique-list-and-dependent-fields', layout }) + '\n');
} finally { await browser.close(); }
