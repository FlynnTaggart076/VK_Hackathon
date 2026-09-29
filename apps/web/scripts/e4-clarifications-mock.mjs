import { chromium } from 'playwright-core';

// Chat dialogue against the MSW mock: menu -> topic -> service -> address -> card, reset and unknown.
if (!process.env.CHROME_PATH) throw new Error('Set CHROME_PATH');
const base = process.env.E4_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });

async function say(page, text) {
  await page.getByLabel('Ваш вопрос').fill(text);
  await page.getByRole('button', { name: 'Спросить' }).click();
}

try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('link', { name: 'Помощник' }).click();
  await page.getByRole('button', { name: 'Контакты поставщика' }).click();
  await page.getByText('По какой услуге?').last().waitFor();
  await page.getByRole('button', { name: 'Холодная вода' }).click();
  await page.getByText('Напишите адрес дома').last().waitFor();
  await say(page, 'Учебный город');
  await page.getByText('Не вижу номера дома').last().waitFor();
  await say(page, 'Учебный город, Примерная улица, 1');
  await page.locator('.house-card').last().waitFor();
  if (await page.getByLabel('Ваш вопрос').inputValue() !== '') throw new Error('Input was not cleared');
  await page.getByRole('button', { name: 'Новый вопрос' }).first().click();
  await page.getByText('Чем помочь?').last().waitFor();
  await say(page, 'неизвестный вопрос');
  await page.getByText('Не удалось определить тему').last().waitFor();
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  process.stdout.write(JSON.stringify({ flow: 'chat-menu-service-address-card-reset-unknown', layout }) + '\n');
} finally { await browser.close(); }
