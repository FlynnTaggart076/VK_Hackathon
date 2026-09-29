// Walks every screen in the mock stand and fails if a user-visible text contains a Latin word.
// Collapsed sections are opened first, and select options are read too: they are visible choices.
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

if (!process.env.CHROME_PATH) throw new Error('Set CHROME_PATH');
const base = process.env.E5_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh/';
const allowed = new Set(['MAX', 'PDF', 'JPEG', 'PNG', 'HouseScore', 'Dominfo']);
const found = [];
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  const scan = async (screen) => {
    await page.evaluate(() => document.querySelectorAll('details').forEach((item) => { item.open = true; }));
    const texts = await page.evaluate(() => [document.body.innerText,
      ...[...document.querySelectorAll('option')].map((item) => item.textContent ?? ''),
      ...[...document.querySelectorAll('[placeholder]')].map((item) => item.getAttribute('placeholder') ?? ''),
      ...[...document.querySelectorAll('[aria-label]')].map((item) => item.getAttribute('aria-label') ?? ''),
      ...[...document.querySelectorAll('img[alt]')].map((item) => item.getAttribute('alt') ?? '')]);
    for (const text of texts) for (const word of text.match(/[A-Za-z][A-Za-z0-9_-]{2,}/g) ?? [])
      if (!allowed.has(word)) found.push(`${screen}: «${word}»`);
  };
  const go = async (path) => {
    await page.evaluate((target) => { window.history.pushState({}, '', target); window.dispatchEvent(new PopStateEvent('popstate')); }, `/team/zhkh${path}`);
    await page.waitForTimeout(500);
  };

  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('link', { name: 'Первый запуск' }).waitFor();
  await scan('главная (до первого запуска)');
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await scan('первый запуск');
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor();
  await page.getByRole('link', { name: 'Платёжка' }).click();
  await scan('загрузка платёжки');
  const fixture = await readFile(new URL('../public/synthetic-receipt.png', import.meta.url));
  await page.getByLabel('Файл платёжки').setInputFiles({ name: 'demo-bill-2026-08.png', mimeType: 'image/png', buffer: fixture });
  await page.getByRole('button', { name: 'Загрузить', exact: true }).click();
  await page.waitForURL(/\/processing\?job=/);
  await scan('обработка');
  await page.waitForURL(/\/review\?id=/, { timeout: 20000 });
  await page.getByRole('img', { name: 'Страница 1 исходной платёжки' }).waitFor();
  const id = new URL(page.url()).searchParams.get('id');
  await page.getByRole('button', { name: 'Добавить строку' }).click();
  await page.getByRole('button', { name: 'Добавить перерасчёт' }).click();
  await scan('проверка платёжки');
  for (const label of ['Электроэнергия', 'Отопление']) {
    await page.getByLabel('Вид услуги').last().selectOption({ label });
    await scan(`проверка платёжки, вид «${label}»`);
  }
  await page.getByRole('link', { name: 'Главная' }).click();
  await page.getByRole('heading', { name: 'Главная' }).waitFor();
  await go(`/review?id=${id}`);
  await page.getByRole('heading', { name: 'Проверка платёжки' }).waitFor();
  await page.getByRole('heading', { name: 'Данные для проверки' }).waitFor();
  await page.getByLabel(/Принимаю предупреждение/).check();
  await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
  await page.getByRole('heading', { name: 'Объяснение платёжки' }).waitFor();
  await scan('объяснение');
  await go('/history');
  await page.getByRole('heading', { name: 'История документов' }).waitFor();
  await scan('история');
  await go('/comparison');
  await scan('сравнение квитанций');
  await go(`/city-comparison?receipt=${id}`);
  await scan('сравнение с городом');
  await go(`/draft?receipt=${id}`);
  await scan('черновик');
  await go('/assistant');
  await page.getByText('Чем помочь?').first().waitFor();
  await scan('помощник');
  await go('/');
  await scan('главная');
  if (found.length) throw new Error(`Latin words on screen:\n${[...new Set(found)].join('\n')}`);
  process.stdout.write(JSON.stringify({ flow: 'every-screen-has-no-latin-words', screens: 13 }) + '\n');
} catch (error) {
  if (process.env.E5_DEBUG_SHOT) await (await browser.contexts()[0].pages())[0].screenshot({ path: process.env.E5_DEBUG_SHOT, fullPage: true });
  throw error;
} finally { await browser.close(); }
