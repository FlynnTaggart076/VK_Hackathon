import { chromium } from 'playwright-core';

const { BASE_URL, DEMO_ACCESS_CODE, CHROME_PATH } = process.env;
if (!BASE_URL || !DEMO_ACCESS_CODE || !CHROME_PATH) throw new Error('Set BASE_URL, DEMO_ACCESS_CODE and CHROME_PATH outside Git');
const base = new URL(BASE_URL);
if (!base.pathname.endsWith('/team/zhkh/')) throw new Error('BASE_URL must end with /team/zhkh/');
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(base.href, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в dev' }).waitFor({ timeout: 15000 });
  await page.getByLabel('Учётная запись').selectOption('reviewer_a');
  await page.getByLabel('Локальный код').fill(DEMO_ACCESS_CODE);
  await page.getByRole('button', { name: 'Войти в dev' }).click();
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor();

  async function importAndConfirm(label, period) {
    await page.getByRole('link', { name: 'Платёжка' }).click();
    await page.getByRole('button', { name: `Загрузить образец · ${label}` }).click();
    await page.waitForURL(/\/processing\?job=/);
    await page.getByRole('link', { name: 'Проверить данные платёжки' }).waitFor({ timeout: 150000 });
    await page.getByRole('link', { name: 'Проверить данные платёжки' }).click();
    await page.waitForURL(/\/review\?id=/);
    const id = new URL(page.url()).searchParams.get('id');
    if (!id) throw new Error('Receipt ID missing');
    await page.getByText('Синтетический пример').first().waitFor();
    if (await page.getByLabel('Период (ГГГГ-ММ)').inputValue() !== period) throw new Error(`Unexpected period for ${label}`);
    const warnings = page.getByLabel(/Принимаю предупреждение/);
    for (let index = 0, count = await warnings.count(); index < count; index++) await warnings.nth(index).check();
    await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
    await page.waitForURL(/\/explanation\?id=/);
    return id;
  }
  const older = await importAndConfirm('Вода, август', '2026-08');
  const newer = await importAndConfirm('Вода, сентябрь', '2026-09');
  await page.getByRole('link', { name: 'История' }).click();
  await page.getByRole('heading', { name: 'История документов' }).waitFor();
  await page.getByRole('link', { name: 'Сравнить квитанции' }).click();
  await page.getByLabel('Ранний документ').selectOption(older);
  await page.getByLabel('Поздний документ').selectOption(newer);
  await page.getByRole('button', { name: 'Сравнить', exact: true }).click();
  await page.getByRole('heading', { name: 'Сравнение готово' }).waitFor({ timeout: 15000 });
  const comparison = await page.locator('.answer').innerText();
  for (const value of ['70.00', '40.00', '30.00', 'Синтетический пример']) if (!comparison.includes(value)) throw new Error(`Missing server comparison value: ${value}`);
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в dev' }).waitFor();
  await page.getByLabel('Учётная запись').selectOption('reviewer_a');
  await page.getByLabel('Локальный код').fill(DEMO_ACCESS_CODE);
  await page.getByRole('button', { name: 'Войти в dev' }).click();
  await page.getByRole('heading', { name: 'Сравнение квитанций' }).waitFor();
  const options = await page.getByLabel('Поздний документ').locator('option').allTextContents();
  if (!options.some((label) => label.includes('2026-09'))) throw new Error('History did not survive reload');
  process.stdout.write(JSON.stringify({ mode: 'real E3 dev API', flow: 'demo-import-two-confirmed-compare-reload', comparison: '70/40/30', layout }) + '\n');
} finally { await browser.close(); }
