import { preview } from 'vite';
import { chromium } from 'playwright-core';

const { CHROME_PATH, EXPECT_PREVIEW } = process.env;
if (!CHROME_PATH || !['true', 'false'].includes(EXPECT_PREVIEW))
  throw new Error('Set CHROME_PATH and EXPECT_PREVIEW=true|false after building the matching bundle');
const appBase = EXPECT_PREVIEW === 'true' ? '/team/zhkh-preview/' : '/team/zhkh/';
const server = await preview({ preview: { host: '127.0.0.1', port: 4173, strictPort: true } });
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  const seen = [];
  let guestCount = 0;
  let expireFirstGuest = false;
  const profile = { role: 'other', territory_id: null, onboarding_completed: false,
    privacy_notice_version: null, privacy_acknowledged_at: null };
  await page.route('https://st.max.ru/js/max-web-app.js', (route) => route.fulfill({
    contentType: 'application/javascript', body: '',
  }));
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    seen.push(`${route.request().method()} ${url.pathname}`);
    if (!url.pathname.startsWith(`${appBase}api/v1/`)) throw new Error(`Wrong API prefix: ${url.pathname}`);
    if (url.pathname.endsWith('/meta')) return route.fulfill({ json: {
      api_version: '1.0', engine_version: 'synthetic', knowledge_version: 'synthetic',
      mode: EXPECT_PREVIEW === 'true' ? 'preview' : 'production',
      features: { voice: false, external_submission: false, receipt_ocr: true, comparison: true, engine_stub: false, demo_auth: false },
      limits: { upload_max_bytes: 10485760, pdf_max_pages: 3, receipt_retention_days: 30, source_retention_days: 7 },
      privacy_notice: { version: '1.0', text: 'Учебный стенд' },
    } });
    if (url.pathname.endsWith('/auth/preview')) {
      guestCount++;
      return route.fulfill({ json: {
        access_token: `guest-token-${guestCount}`, token_type: 'bearer', expires_in: 3600,
        user: { id: `guest-${guestCount}` }, profile,
      } });
    }
    if (url.pathname.endsWith('/me')) {
      if (expireFirstGuest && route.request().headers().authorization === 'Bearer guest-token-1')
        return route.fulfill({ status: 401, json: { error: { code: 'SESSION_EXPIRED', message: 'Session expired',
          retryable: false, fields: [], details: {} }, request_id: '00000000-0000-4000-8000-000000000001' } });
      return route.fulfill({ json: { user: { id: `guest-${guestCount}` }, profile } });
    }
    if (url.pathname.endsWith('/catalog')) return route.fulfill({ json: {
      territories: [], organizations: [], topics: [], service_codes: [], units: [], document_kinds: [], demo_receipts: [],
    } });
    if (url.pathname.endsWith('/receipts')) return route.fulfill({ json: { items: [], next_cursor: null } });
    throw new Error(`Unexpected API call: ${url.pathname}`);
  });
  const deepLink = new URL(`${appBase}history`, 'http://127.0.0.1:4173').href;
  await page.goto(deepLink, { waitUntil: 'domcontentloaded' });
  if (EXPECT_PREVIEW === 'true') {
    await page.getByRole('heading', { name: 'История документов' }).waitFor();
    await page.getByText('Документов пока нет.').waitFor();
    await page.getByRole('note').getByText('Публичный учебный стенд').waitFor();
    if (seen.filter((value) => value.endsWith('/auth/preview')).length !== 1)
      throw new Error(`Expected one preview auth exchange: ${seen.join(', ')}`);
    if (await page.evaluate(() => sessionStorage.getItem('zhkh-preview-session')) !== 'guest-token-1')
      throw new Error('Preview session was not stored per tab');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByText('Документов пока нет.').waitFor();
    if (seen.filter((value) => value.endsWith('/auth/preview')).length !== 1)
      throw new Error('Reload created a new guest despite valid tab session');
    await page.getByRole('link', { name: 'Платёжка' }).click();
    await page.locator('.review-warning').waitFor();
    if (await page.getByLabel('Файл платёжки').count()) throw new Error('Public preview exposed raw upload');
    expireFirstGuest = true;
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByText('Создан новый виртуальный гость', { exact: false }).waitFor();
    if (guestCount !== 2 || await page.evaluate(() => sessionStorage.getItem('zhkh-preview-session')) !== 'guest-token-2')
      throw new Error('Expired preview token did not recover with a new guest');
  } else {
    await page.getByText('Откройте приложение внутри MAX', { exact: false }).waitFor();
    if (seen.some((value) => value.endsWith('/auth/preview'))) throw new Error('Production called preview auth');
    if (await page.getByRole('note').count()) throw new Error('Preview banner leaked into production');
  }
  process.stdout.write(JSON.stringify({ build: EXPECT_PREVIEW === 'true' ? 'preview' : 'production',
    deepLink, apiCalls: seen }) + '\n');
} finally {
  await browser.close();
  await new Promise((resolve, reject) => server.httpServer.close((error) => error ? reject(error) : resolve()));
}
