import { chromium } from 'playwright-core';
import { waitForDevEntry, watchDevEntry } from './real-entry.mjs';

if (!process.env.CHROME_PATH) throw new Error('Set CHROME_PATH');
const base = process.env.E4_REAL_URL ?? 'http://127.0.0.1:5173/team/zhkh/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const meta = {
  api_version: 'test', knowledge_version: 'test', mode: 'dev',
  features: { demo_auth: true },
};
const error = (status) => ({ error: { code: status === 503 ? 'SERVICE_UNAVAILABLE' : 'INVALID_REQUEST',
  message: status === 503 ? 'Временно недоступно' : 'Постоянная ошибка', retryable: status === 503,
  fields: [], details: {} }, request_id: '00000000-0000-4000-8000-000000000000' });

try {
  const transient = await browser.newPage({ viewport: { width: 360, height: 800 } });
  let attempts = 0;
  let recovered = false;
  await transient.route('**/api/v1/meta', async (route) => {
    attempts++;
    const status = recovered ? 200 : 503;
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(status === 200 ? meta : error(status)) });
  });
  const transientRecord = watchDevEntry(transient);
  await transient.goto(base, { waitUntil: 'domcontentloaded' });
  await transient.getByRole('button', { name: 'Повторить загрузку данных' }).waitFor();
  const initialAttempts = attempts;
  recovered = true;
  await waitForDevEntry(transient, transientRecord, 'transient-test');
  if (attempts !== initialAttempts + 1 || !await transient.getByRole('button', { name: 'Войти в dev' }).isVisible())
    throw new Error(`Expected exactly one visible-meta retry, got ${JSON.stringify({ initialAttempts, attempts })}`);
  await transient.close();

  const persistent = await browser.newPage({ viewport: { width: 360, height: 800 } });
  let permanentAttempts = 0;
  await persistent.route('**/api/v1/meta', async (route) => {
    permanentAttempts++;
    await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify(error(400)) });
  });
  const persistentRecord = watchDevEntry(persistent);
  await persistent.goto(base, { waitUntil: 'domcontentloaded' });
  await persistent.getByRole('button', { name: 'Повторить загрузку данных' }).waitFor();
  const initialPermanentAttempts = permanentAttempts;
  let diagnosed = false;
  let diagnosis = '';
  try { await waitForDevEntry(persistent, persistentRecord, 'persistent-test'); }
  catch (cause) { diagnosis = String(cause); diagnosed = diagnosis.includes('metaStatus') && diagnosis.includes('400') && diagnosis.includes('persistent-test'); }
  if (!diagnosed || permanentAttempts !== initialPermanentAttempts) throw new Error(`Permanent /meta failure was retried or lacked diagnostics: ${JSON.stringify({ initialPermanentAttempts, permanentAttempts, diagnosis, record: persistentRecord })}`);
  await persistent.close();
  process.stdout.write(JSON.stringify({ initialTransientAttempts: initialAttempts, transientMetaAttempts: attempts,
    initialPermanentAttempts, permanentMetaAttempts: permanentAttempts, diagnosed }) + '\n');
} finally { await browser.close(); }
