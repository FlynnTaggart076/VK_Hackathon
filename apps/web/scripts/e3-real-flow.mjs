import { chromium } from 'playwright-core';
import { waitForDevEntry, watchDevEntry } from './real-entry.mjs';

const { BASE_URL, DEMO_ACCESS_CODE, CHROME_PATH } = process.env;
if (!BASE_URL || !DEMO_ACCESS_CODE || !CHROME_PATH) throw new Error('Set BASE_URL, DEMO_ACCESS_CODE and CHROME_PATH outside Git');
const base = new URL(BASE_URL);
if (!base.pathname.endsWith('/team/zhkh/')) throw new Error('BASE_URL must end with /team/zhkh/');
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  const entry = watchDevEntry(page);
  await page.goto(base.href, { waitUntil: 'domcontentloaded' });
  await waitForDevEntry(page, entry, 'initial');
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
    await page.waitForURL(/\/review\?id=/, { timeout: 150000 });
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
  entry.reset();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForDevEntry(page, entry, 'reload');
  await page.getByLabel('Учётная запись').selectOption('reviewer_a');
  await page.getByLabel('Локальный код').fill(DEMO_ACCESS_CODE);
  await page.getByRole('button', { name: 'Войти в dev' }).click();
  await page.getByRole('heading', { name: 'Сравнение квитанций' }).waitFor();
  await page.getByLabel('Поздний документ').locator('option').filter({ hasText: '2026-09' }).waitFor({ state: 'attached', timeout: 15000 });
  const options = await page.getByLabel('Поздний документ').locator('option').allTextContents();
  if (!options.some((label) => label.includes('2026-09'))) throw new Error('History did not survive reload');
  await page.getByRole('link', { name: 'Помощник' }).click();
  await page.getByRole('button', { name: 'Контакты поставщика' }).waitFor();
  await page.getByLabel('Ваш вопрос').fill('Где найти лицевой счёт?');
  await page.getByRole('button', { name: 'Спросить' }).click();
  await page.getByText('ГИС ЖКХ: Как перейти к списку лицевых счетов').waitFor();
  const official = page.getByRole('link', { name: 'Открыть инструкцию ГИС ЖКХ' });
  if (!(await official.getAttribute('href'))?.startsWith('https://')) throw new Error('Official source lacks HTTPS link');
  await page.getByLabel('Ваш вопрос').fill('xyzzy неизвестное');
  await page.getByRole('button', { name: 'Спросить' }).click();
  await page.getByText('Не удалось определить тему').last().waitFor();

  await page.getByRole('link', { name: 'История' }).click();
  await page.getByRole('link', { name: 'Сравнить квитанции' }).click();
  await page.getByLabel('Ранний документ').selectOption(older);
  await page.getByLabel('Поздний документ').selectOption(newer);
  await page.getByRole('button', { name: 'Сравнить', exact: true }).click();
  await page.getByRole('link', { name: 'Подготовить черновик' }).waitFor();
  await page.getByRole('link', { name: 'Подготовить черновик' }).click();
  await page.getByLabel('Тема').selectOption('request_breakdown');
  await page.getByRole('button', { name: 'Подготовить черновик' }).click();
  await page.getByRole('heading', { name: 'Проверьте текст' }).waitFor();
  if (await page.getByRole('button', { name: /отправить/i }).count()) throw new Error('Unexpected send button');
  if (!(await page.getByLabel('Текст черновика').inputValue()).includes('270.00')) throw new Error('Draft lacks confirmed amount');
  await page.getByLabel('Текст черновика').fill('Прошу пояснить начисление по моей квитанции.');
  await page.getByRole('button', { name: 'Сохранить изменения' }).click();
  await page.getByRole('status').filter({ hasText: 'Изменения сохранены' }).waitFor();
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: async (value) => { window.__e3CopiedText = value; } } }));
  await page.getByRole('button', { name: 'Копировать текст' }).click();
  await page.getByRole('status').filter({ hasText: 'Текст скопирован' }).waitFor();
  if (await page.evaluate(() => window.__e3CopiedText) !== 'Прошу пояснить начисление по моей квитанции.') throw new Error('Copied draft differs from saved text');
  await page.evaluate(async (id) => {
    const { api } = await import('/team/zhkh/src/api/client.ts');
    const receipt = await api.receipt(id);
    await api.editReceipt(id, { expected_revision: receipt.revision,
      bill_data: { ...receipt.bill_data, issuer_name: `${receipt.bill_data.issuer_name ?? 'Организация'} (исправлено)` } });
  }, newer);
  await page.getByRole('button', { name: 'Копировать текст' }).click();
  await page.getByText('Черновик устарел').waitFor();
  await page.getByRole('status').filter({ hasText: 'подтвердите копирование устаревшего черновика' }).waitFor();
  await page.getByRole('checkbox', { name: 'Я проверил устаревшие факты перед копированием' }).check();
  await page.getByRole('button', { name: 'Копировать текст' }).click();
  await page.getByRole('status').filter({ hasText: 'Текст скопирован' }).waitFor();
  process.stdout.write(JSON.stringify({ mode: 'real E3 dev API', flow: 'demo-import-confirm-compare-FAQ-source-unknown-draft-copy-stale-reload', comparison: '70/40/30', layout }) + '\n');
} finally { await browser.close(); }
