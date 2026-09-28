import { chromium } from 'playwright-core';

if (!process.env.CHROME_PATH) throw new Error('Set CHROME_PATH');
const base = process.env.E4_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });

async function ask(page, question, topic = '') {
  await page.getByLabel('Тема', { exact: true }).selectOption(topic);
  await page.getByLabel('Ваш вопрос').fill(question);
  await page.getByRole('button', { name: 'Спросить' }).click();
}

try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Войти в учебный mock' }).click();
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('demo-territory');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await page.getByRole('link', { name: 'Помощник' }).click();

  await ask(page, 'Контакт поставщика: цепочка', 'supplier_contacts');
  await page.getByRole('heading', { name: 'Нужно уточнение' }).waitFor();
  await page.getByLabel('По какой услуге возник вопрос?').fill('горячая вода');
  await page.getByRole('button', { name: 'Продолжить с уточнениями' }).click();
  await page.getByLabel('Какая организация указана?').waitFor();
  if (await page.getByLabel('Тема', { exact: true }).inputValue() !== 'supplier_contacts') throw new Error('Selected topic was lost');
  if (await page.getByLabel('Ваш вопрос').inputValue() !== 'Контакт поставщика: цепочка') throw new Error('Original question was lost');
  await page.getByLabel('Какая организация указана?').fill('МосОблЕИРЦ');
  await page.getByRole('button', { name: 'Продолжить с уточнениями' }).click();
  await page.getByRole('heading', { name: 'Ответ', exact: true }).waitFor();
  if (await page.getByLabel('По какой услуге возник вопрос?').inputValue() !== 'горячая вода') throw new Error('Prior clarification was lost');
  await page.getByLabel('По какой услуге возник вопрос?').fill('отопление');
  await page.getByLabel('По какой услуге возник вопрос?').press('Enter');
  await page.getByRole('heading', { name: 'Ответ', exact: true }).waitFor();

  await page.getByRole('button', { name: 'Сбросить уточнения' }).click();
  await ask(page, 'Почему вырос счёт за коммуналку?');
  await page.getByRole('heading', { name: 'Ответ', exact: true }).waitFor();
  if (await page.getByLabel('Тема', { exact: true }).inputValue()) throw new Error('Topic-by-question changed selection');
  await ask(page, 'неизвестный космос');
  await page.getByRole('heading', { name: 'Пока нет проверенного ответа' }).waitFor();

  await page.evaluate(() => {
    window.__assistantBodies = [];
    const original = window.fetch.bind(window);
    window.fetch = (input, options) => {
      if (String(input).includes('/assistant/answers') && typeof options?.body === 'string')
        window.__assistantBodies.push(JSON.parse(options.body));
      return original(input, options);
    };
  });
  const lastBody = () => page.evaluate(() => window.__assistantBodies.at(-1));
  await ask(page, 'проверь поля');
  for (const [field, value] of [
    ['topic_id', 'Изменение суммы'], ['territory_id', 'Москва'], ['role', 'Собственник'],
    ['organization_id', 'УК Пример'], ['service_code', 'Лифт'], ['document_kind', 'Редкая справка'],
  ]) {
    const input = page.getByLabel(`Уточните поле ${field}`);
    await input.waitFor();
    if (field === 'topic_id' || field === 'organization_id') {
      const free = field === 'topic_id' ? 'Лифты' : 'УК Ромашка';
      await input.fill(free);
      await page.getByRole('button', { name: 'Продолжить с уточнениями' }).click();
      await input.waitFor();
      const body = await lastBody();
      if (body.context[field] !== null || !body.question.includes(free) || await input.inputValue() !== free)
        throw new Error(`Free-text ${field} was sent as an invalid ID or lost`);
    }
    if (field === 'territory_id' || field === 'role') {
      await input.fill(field === 'territory_id' ? 'Марс' : 'Космонавт');
      const before = await page.evaluate(() => window.__assistantBodies.length);
      await page.getByRole('button', { name: 'Продолжить с уточнениями' }).click();
      await page.locator('.error').last().waitFor();
      if (await page.evaluate(() => window.__assistantBodies.length) !== before) throw new Error(`Invalid ${field} reached API`);
    }
    await input.fill(value);
    if (field === 'territory_id' || field === 'role') await page.getByRole('checkbox', { name: /Я прочитал\(а\) уведомление/ }).check();
    await page.getByRole('button', { name: 'Продолжить с уточнениями' }).click();
    if (field === 'service_code') {
      const body = await lastBody();
      if (body.context.service_code !== 'other' || !body.question.includes('Лифт')) throw new Error('Free-text service did not map to other');
    }
    if (field === 'document_kind') {
      const body = await lastBody();
      if (body.context.document_kind !== 'Редкая справка') throw new Error('Free-text document kind was lost');
    }
  }
  await page.getByRole('heading', { name: 'Ответ', exact: true }).waitFor();
  await page.getByRole('link', { name: 'История' }).click();
  await page.getByRole('checkbox', { name: /Разрешаю использовать мои подтверждённые квитанции/ }).check();
  await page.getByRole('button', { name: 'Сохранить выбор' }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some((button) => button.textContent === 'Сохранить выбор' && button.disabled));
  await page.getByRole('link', { name: 'Сравнить с городом' }).first().click();
  await page.getByText('Городское сравнение доступно только для реальных подтверждённых квитанций.').waitFor();
  if (await page.getByRole('button', { name: 'Показать статистику' }).count()) throw new Error('Synthetic receipt can request a real cohort');
  if (await page.getByText('Среднее', { exact: true }).count()) throw new Error('Numeric cohort shown for synthetic receipt');
  await page.getByRole('link', { name: 'К истории документов' }).click();
  await page.getByRole('link', { name: 'Вопрос по платёжке' }).first().click();
  await page.getByText('Документ:', { exact: false }).waitFor();
  await ask(page, 'Нужна справка', 'housing_document');
  await page.getByRole('heading', { name: 'Нужно уточнение' }).waitFor();
  await page.getByRole('button', { name: 'Сведения о регистрации' }).click();
  await page.getByRole('heading', { name: 'Ответ', exact: true }).waitFor();
  if (!(new URL(page.url())).searchParams.get('receipt')) throw new Error('Selected receipt was lost');
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width) throw new Error(`Horizontal overflow: ${JSON.stringify(layout)}`);
  process.stdout.write(JSON.stringify({ flow: 'supplier-empty-options-typed-chained-amend-keyboard-intent-unknown-all-fields-consent-city-ineligible-receipt', layout }) + '\n');
} finally { await browser.close(); }
