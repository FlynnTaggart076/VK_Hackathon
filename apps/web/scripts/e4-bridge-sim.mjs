import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const { BASE_URL, CHROME_PATH } = process.env;
if (!BASE_URL || !CHROME_PATH) throw new Error('Set BASE_URL (production preview) and CHROME_PATH');
const base = new URL(BASE_URL);
if (!base.pathname.endsWith('/team/zhkh/')) throw new Error('BASE_URL must end with /team/zhkh/');
const meta = JSON.parse(await readFile(new URL('../../../contracts/http/examples/meta-dev.json', import.meta.url), 'utf8'));
meta.features.demo_auth = false;
const raw = 'auth_date=123&user=%7B%22user_id%22%3A%221%22%7D&hash=opaque';
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  let exchanges = 0;
  await page.route('https://st.max.ru/js/max-web-app.js', (route) => route.fulfill({ status: 200,
    contentType: 'application/javascript', body: `window.WebApp={initData:${JSON.stringify(raw)},initDataUnsafe:{user:{user_id:'forged'}}};` }));
  await page.route('**/team/zhkh/api/v1/meta', (route) => route.fulfill({ json: meta }));
  await page.route('**/team/zhkh/api/v1/auth/max', async (route) => {
    exchanges++;
    const body = route.request().postDataJSON();
    if (JSON.stringify(body) !== JSON.stringify({ init_data: raw })) throw new Error('Bridge raw initData was changed');
    if (route.request().url().includes('hash=')) throw new Error('initData leaked into URL');
    await route.fulfill({ json: { access_token: 'simulated-session', token_type: 'bearer', expires_in: 3600,
      user: { id: 'simulated-user' }, profile: { onboarding_completed: false, territory_id: null } } });
  });
  await page.route('**/team/zhkh/api/v1/me', (route) => route.fulfill({ status: 401,
    json: { error: { code: 'SESSION_EXPIRED', message: 'Session expired', retryable: false, fields: [], details: {} },
      request_id: '00000000-0000-4000-8000-000000000001' } }));
  await page.route('**/team/zhkh/api/v1/catalog', (route) => route.fulfill({ json: { territories: [], topics: [], demo_receipts: [] } }));
  await page.goto(new URL('review?id=00000000-0000-4000-8000-000000000001', base).href, { waitUntil: 'domcontentloaded' });
  await page.getByText('Закройте и переоткройте мини-приложение в MAX').waitFor({ timeout: 15000 });
  if (exchanges !== 1) throw new Error(`Expected one MAX exchange before 401, got ${exchanges}`);
  if (!new URL(page.url()).pathname.endsWith('/team/zhkh/review')) throw new Error('401 changed deep-link pathname');
  if (await page.evaluate(() => Object.keys(localStorage).some((key) => /token|initData/i.test(key))))
    throw new Error('MAX session material was stored in localStorage');

  const external = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await external.route('https://st.max.ru/js/max-web-app.js', (route) => route.abort());
  await external.route('**/team/zhkh/api/v1/meta', (route) => route.fulfill({ json: meta }));
  await external.goto(base.href, { waitUntil: 'domcontentloaded' });
  await external.getByText('Стартовые данные MAX здесь недоступны.').waitFor({ timeout: 15000 });
  process.stdout.write(JSON.stringify({ mode: 'simulated Bridge and API responses', checks: [
    'raw initData exchange', '401 requires fresh mini-app launch', 'deep-link retained', 'no localStorage token', 'external browser no Bridge',
  ] }) + '\n');
} finally { await browser.close(); }
