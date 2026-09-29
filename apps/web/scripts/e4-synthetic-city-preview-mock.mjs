import { chromium } from 'playwright-core';

const { CHROME_PATH } = process.env;
const base = new URL(process.env.PREVIEW_MOCK_URL ?? 'http://127.0.0.1:5173/team/zhkh-preview/');
if (!CHROME_PATH || base.pathname !== '/team/zhkh-preview/') throw new Error('Set CHROME_PATH and a preview URL ending in /team/zhkh-preview/');
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const now = '2026-09-29T10:00:00Z';
const apiPath = `${base.pathname}api/v1/`;
const samples = [
  { id: 'city-moscow-water-2026-08', label: 'Москва · август 2026', period: '2026-08', own: '200.00', mean: '256.00', median: '240.00', difference: '-56.00', percent: '-21.88', tariff: '40.000000' },
  { id: 'city-moscow-water-2026-09', label: 'Москва · сентябрь 2026', period: '2026-09', own: '270.00', mean: '342.00', median: '315.00', difference: '-72.00', percent: '-21.05', tariff: '45.000000' },
];
const receiptId = (period) => `10000000-0000-4000-8000-00000000${period.slice(-2)}00`;
const jobId = (period) => `20000000-0000-4000-8000-00000000${period.slice(-2)}00`;
let profile = { role: 'other', territory_id: null, onboarding_completed: false, aggregate_opt_in: false,
  privacy_notice_version: null, privacy_acknowledged_at: null };
const receipts = new Map();
const jobs = new Map();
const observed = { previewAuth: 0, imported: [], confirmed: [], previewQueries: [], realQueries: [], unexpected: [], pageErrors: [] };
let failNextPreviewQuery = true;
let cohortMode = 'available';
let step = 'launch';

function bill(sample) {
  return { schema_version: '1.0', period: sample.period, currency: 'RUB', issuer_name: 'Учебная организация Москвы',
    provider_id: null, account_number: '000123', address_text: 'Вымышленный учебный адрес', template_id: 'synthetic-city-v1', template_version: '1.0',
    services: [{ line_id: '30000000-0000-4000-8000-000000000001', raw_name: 'Холодная вода', service_code: 'cold_water',
      scope: 'individual', unit: 'm3', unit_label: 'м³', quantity: sample.period.endsWith('08') ? '5.000000' : '6.000000',
      tariff: sample.tariff, charge_amount: sample.own, supplier_key: null, segment_key: null, calculation_kind: 'simple_product' }],
    adjustments: [], settlement: { formula_kind: 'signed_balance_v1', opening_balance: '0.00', payments_credited: '0.00',
      penalties: '0.00', other_account_changes: '0.00', document_closing_balance: sample.own },
    document_current_charges: sample.own, document_total_due: sample.own };
}
function receipt(sample, status = 'needs_review') {
  return { id: receiptId(sample.period), status, revision: status === 'confirmed' ? 2 : 1, created_at: now, updated_at: now,
    dataset_kind: 'synthetic', extraction_outcome: 'recognized', bill_data: bill(sample), field_evidence: [], issues: [],
    document: { available: false, mime_type: null, page_count: null, expires_at: null },
    job: { id: jobId(sample.period), state: 'succeeded', stage: 'completed' },
    confirmed_at: status === 'confirmed' ? now : null, engine_version: 'synthetic-test' };
}
function envelope(status, code, message) {
  return { error: { code, message, retryable: status >= 500, fields: [], details: {} }, request_id: '40000000-0000-4000-8000-000000000001' };
}
async function serve(route) {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.slice(apiPath.length);
  const method = request.method();
  const body = request.postDataJSON?.() ?? {};
  const ok = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
  const fail = (status, code, message) => ok(envelope(status, code, message), status);
  if (path === 'meta') return ok({ api_version: '1.0', engine_version: 'synthetic-test', knowledge_version: 'synthetic-test', mode: 'preview',
    limits: { upload_max_bytes: 10485760, pdf_max_pages: 3, receipt_retention_days: 30, source_retention_days: 7 },
    features: { voice: false, external_submission: false, receipt_ocr: true, comparison: true, engine_stub: false, demo_auth: false },
    privacy_notice: { version: 'synthetic-test', text: 'Только учебные данные.' } });
  if (path === 'auth/preview' && method === 'POST') {
    observed.previewAuth++;
    return ok({ access_token: 'test-preview-token', token_type: 'bearer', expires_in: 3600,
      user: { id: '50000000-0000-4000-8000-000000000001' }, profile });
  }
  if (path !== 'auth/preview' && request.headers().authorization !== 'Bearer test-preview-token') return fail(401, 'AUTH_REQUIRED', 'Нужен вход.');
  if (path === 'me') return ok({ user: { id: '50000000-0000-4000-8000-000000000001' }, profile });
  if (path === 'catalog') return ok({ territories: [{ id: 'moscow', label: 'Москва' }], organizations: [],
    topics: [{ id: 'bill_change', label: 'Изменение суммы' }], service_codes: ['cold_water'], units: ['m3'], document_kinds: [],
    demo_receipts: samples.map((sample) => ({ fixture_id: sample.id, label: sample.label, description: 'Синтетический учебный образец' })) });
  if (path === 'me/profile' && method === 'PUT') {
    profile = { ...profile, role: body.role, territory_id: body.territory_id, onboarding_completed: true,
      privacy_notice_version: body.privacy_notice_version, privacy_acknowledged_at: now };
    return ok(profile);
  }
  if (path === 'receipts/demo' && method === 'POST') {
    const sample = samples.find((item) => item.id === body.fixture_id);
    if (!sample) return fail(404, 'NOT_FOUND', 'Образец не найден.');
    const value = receipt(sample);
    receipts.set(value.id, value); jobs.set(value.job.id, value.id); observed.imported.push(sample.id);
    return ok({ receipt: value, job_id: value.job.id }, 202);
  }
  if (path.startsWith('jobs/') && method === 'GET') {
    const id = jobs.get(path.slice('jobs/'.length));
    return id ? ok({ id: path.slice('jobs/'.length), kind: 'demo_import', state: 'succeeded', stage: 'completed',
      receipt_id: id, error: null, updated_at: now }) : fail(404, 'NOT_FOUND', 'Задание не найдено.');
  }
  if (path === 'receipts' && method === 'GET') return ok({ items: [...receipts.values()].map((value) => ({
    id: value.id, status: value.status, revision: value.revision, period: value.bill_data.period,
    issuer_name: value.bill_data.issuer_name, document_total_due: value.bill_data.document_total_due,
    dataset_kind: value.dataset_kind, created_at: value.created_at, source_available: false })), next_cursor: null });
  const city = path.match(/^preview\/receipts\/([^/]+)\/city-comparison$/);
  if (city && method === 'GET') {
    observed.previewQueries.push(city[1]);
    if (failNextPreviewQuery) { failNextPreviewQuery = false; return fail(503, 'TEMPORARY_FAILURE', 'Временная ошибка учебного сравнения.'); }
    const value = receipts.get(city[1]);
    if (!value || value.status !== 'confirmed') return fail(404, 'NOT_FOUND', 'Квитанция не найдена.');
    const sample = samples.find((item) => item.period === value.bill_data.period);
    if (cohortMode === 'insufficient') return ok({ status: 'insufficient_data', city: 'moskva', city_label: 'Москва', period: sample.period,
      service_code: 'cold_water', scope: 'individual', segment_key: null, unit: 'm3', metric: 'charge_amount',
      sample_size: null, receipt_value: null, average: null, median: null, difference_from_average: null,
      difference_percent: null, comparison: null, explanation: null, provenance: 'synthetic_preview_cohort' });
    return ok({ status: 'available', city: 'moskva', city_label: 'Москва', period: sample.period,
      service_code: 'cold_water', scope: 'individual', segment_key: null, unit: 'm3', metric: 'charge_amount',
      sample_size: 5, receipt_value: sample.own, average: sample.mean, median: sample.median,
      difference_from_average: sample.difference, difference_percent: sample.percent,
      comparison: 'below', explanation: 'Это синтетическая учебная выборка, не данные жителей Москвы.',
      provenance: 'synthetic_preview_cohort' });
  }
  if (/^receipts\/[^/]+\/city-comparison$/.test(path)) {
    observed.realQueries.push(path);
    return fail(500, 'WRONG_ENDPOINT', 'Синтетика не должна обращаться к реальной когорте.');
  }
  const confirmation = path.match(/^receipts\/([^/]+)\/confirm$/);
  if (confirmation && method === 'POST') {
    const value = receipts.get(confirmation[1]);
    if (!value || value.status !== 'needs_review') return fail(409, 'INVALID_STATE', 'Нельзя подтвердить.');
    const updated = { ...value, status: 'confirmed', revision: 2, confirmed_at: now };
    receipts.set(updated.id, updated); observed.confirmed.push(updated.id);
    return ok(updated);
  }
  const explanation = path.match(/^receipts\/([^/]+)\/explanation$/);
  if (explanation && method === 'GET') {
    const value = receipts.get(explanation[1]);
    if (!value || value.status !== 'confirmed') return fail(409, 'RECEIPT_NOT_CONFIRMED', 'Сначала подтвердите квитанцию.');
    return ok({ receipt_ref: { id: value.id, revision: value.revision }, engine_version: 'synthetic-test', knowledge_version: 'synthetic-test',
      summary: 'Учебная квитанция подтверждена.', current_charges: value.bill_data.document_current_charges,
      document_total_due: value.bill_data.document_total_due, calculated_closing_balance: null,
      calculated_total_due: null, unexplained_difference: null, reconciliation_checks: [], reconciliation_status: 'incomplete',
      lines: [], balance_components: [], issues: [], sources: [], actions: [] });
  }
  const oneReceipt = path.match(/^receipts\/([^/]+)$/);
  if (oneReceipt && method === 'GET') {
    const value = receipts.get(oneReceipt[1]);
    return value ? ok(value) : fail(404, 'NOT_FOUND', 'Квитанция не найдена.');
  }
  if (path === 'assistant/dialog' && method === 'POST') {
    const text = body.message ? 'Для сравнения с учебной выборкой откройте числовой экран квитанции.' : 'Чем помочь? Напишите вопрос по квитанции.';
    return ok({ status: 'answered', text, options: [], card: null, links: [], sources: [], actions: [], awaiting: null,
      topic_id: null, menu: false, dataset_kind: 'synthetic' });
  }
  if (path === 'assistant/answers' && method === 'POST') {
    return ok({ id: '60000000-0000-4000-8000-000000000001', created_at: now, stale: false, stale_reasons: [],
      status: 'answered', text: 'Для сравнения с учебной выборкой откройте числовой экран квитанции.',
      topic_id: 'bill_change', steps: [], sources: [], actions: [], clarification: null, limitations: [],
      knowledge_version: 'synthetic-test', receipt_ref: { id: body.context.receipt_id, revision: body.context.receipt_revision },
      dataset_kind: 'synthetic' });
  }
  observed.unexpected.push(`${method} ${path}`);
  return fail(404, 'NOT_FOUND', 'Тестовый маршрут не определён.');
}

async function importAndConfirm(page, label) {
  await page.getByRole('link', { name: 'Платёжка' }).click();
  await page.getByRole('button', { name: `Загрузить образец · ${label}` }).click();
  await page.waitForURL(/\/review\?id=/, { timeout: 20000 });
  await page.getByRole('button', { name: 'Подтвердить проверенные данные' }).click();
  await page.getByRole('heading', { name: 'Объяснение платёжки' }).waitFor();
  await page.getByText('Учебная квитанция подтверждена.').waitFor();
}

try {
  const page = await browser.newPage({ viewport: { width: 360, height: 850 } });
  page.on('pageerror', (error) => observed.pageErrors.push(error.message));
  await page.route('**/api/v1/**', (route) => void serve(route));
  step = 'preview entry';
  await page.goto(new URL('history', base).href, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: 'История документов' }).waitFor();
  step = 'onboarding';
  await page.getByRole('link', { name: 'Первый запуск' }).click();
  await page.getByLabel('Ваша роль').selectOption('tenant');
  await page.getByLabel('Территория').selectOption('moscow');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await page.getByRole('status').filter({ hasText: 'Профиль сохранён' }).waitFor();
  step = 'import and confirm two city samples';
  await importAndConfirm(page, samples[0].label);
  await importAndConfirm(page, samples[1].label);
  step = 'history to city question';
  await page.getByRole('link', { name: 'История' }).click();
  const september = page.locator('.history-list > li').filter({ hasText: '2026-09' });
  await september.getByRole('link', { name: 'Вопрос по платёжке' }).click();
  await page.getByLabel('Ваш вопрос').fill('Везде по Москве вырос счёт за холодную воду или только у меня?');
  await page.getByRole('button', { name: 'Спросить' }).click();
  await page.locator('.bubble.bot').nth(1).waitFor();
  await page.getByRole('link', { name: 'Проверить по учебной выборке' }).click();
  step = 'synthetic API error and retry';
  await page.getByLabel('Учебная квитанция прошлого месяца').selectOption(receiptId('2026-08'));
  await page.getByRole('button', { name: 'Показать учебное сравнение' }).click();
  await page.getByRole('alert').filter({ hasText: 'Временная ошибка' }).waitFor();
  await page.getByRole('button', { name: 'Повторить сравнение' }).click();
  step = 'numeric synthetic result';
  const current = page.locator('.notice-box').filter({ has: page.getByRole('heading', { name: 'Выбранный учебный месяц' }) });
  const older = page.locator('.notice-box').filter({ has: page.getByRole('heading', { name: 'Предыдущий учебный месяц' }) });
  await current.getByText('342.00 ₽').waitFor();
  await current.getByText('270.00 ₽').waitFor();
  await older.getByText('256.00 ₽').waitFor();
  await older.getByText('200.00 ₽').waitFor();
  await page.getByText('Синтетическая учебная выборка — не данные жителей Москвы/МО').first().waitFor();
  if (await page.getByText('Источник: подтверждённые реальные квитанции').count()) throw new Error('Preview made a real cohort claim');
  const screen = await page.locator('main').innerText();
  if (!screen.includes('Учебных записей (искусственных)') || !screen.includes('-72.00 ₽ (-21.05%)')) throw new Error('Synthetic count or difference absent');
  step = 'history direct link';
  await page.getByRole('link', { name: 'К истории документов' }).click();
  await page.locator('.history-list > li').filter({ hasText: '2026-09' }).getByRole('link', { name: 'Сравнить с учебной выборкой' }).click();
  await page.getByRole('button', { name: 'Показать учебное сравнение' }).click();
  await page.getByText('342.00 ₽').first().waitFor();
  step = 'insufficient synthetic sample suppression';
  cohortMode = 'insufficient';
  await page.getByRole('button', { name: 'Показать учебное сравнение' }).click();
  await page.getByText('Для выбранного города, месяца и услуги нет сопоставимой учебной выборки.').waitFor();
  if (await page.getByRole('heading', { name: 'Предыдущий учебный месяц' }).count() ||
    await page.getByText('342.00 ₽').count() || await page.getByText('Учебных записей (искусственных)').count())
    throw new Error('Insufficient synthetic cohort exposed numeric values or previous month');
  await page.getByRole('link', { name: 'Открыть учебные образцы' }).waitFor();
  const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (layout.scrollWidth > layout.width || observed.realQueries.length || observed.unexpected.length || observed.pageErrors.length ||
    observed.imported.length !== 2 || observed.confirmed.length !== 2 || observed.previewQueries.length < 4)
    throw new Error(`Preview flow incomplete: ${JSON.stringify({ layout, observed })}`);
  process.stdout.write(JSON.stringify({ mode: 'preview mock API', flow: 'import-confirm-history-question-error-retry-current-previous-direct-history-insufficient',
    layout, imported: observed.imported, previewQueryCount: observed.previewQueries.length, realQueryCount: observed.realQueries.length }) + '\n');
} catch (cause) {
  process.stderr.write(`SYNTHETIC PREVIEW BROWSER FAILED at ${step}: ${cause.stack || cause}\n`);
  process.exitCode = 1;
} finally { await browser.close(); }
