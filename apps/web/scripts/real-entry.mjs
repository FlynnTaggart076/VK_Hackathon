function pathOf(url) {
  try { return new URL(url).pathname; } catch { return '(invalid URL)'; }
}

function safeText(value) {
  return String(value)
    .replace(/https?:\/\/[^\s)]+/gi, (url) => pathOf(url))
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/\b(?:sk-|ds-)[A-Za-z0-9_-]+\b/gi, '[redacted]')
    .replace(/\b[A-Za-z0-9_-]{32,}\b/g, '[redacted]')
    .slice(0, 240);
}

export function watchDevEntry(page) {
  const record = { meta: [], failedRequests: [], consoleErrors: [], pageErrors: [], metaMode: null, demoAuth: null,
    reset() { this.meta = []; this.failedRequests = []; this.consoleErrors = []; this.pageErrors = []; this.metaMode = null; this.demoAuth = null; } };
  page.on('response', (response) => {
    if (!pathOf(response.url()).endsWith('/api/v1/meta')) return;
    record.meta.push(response.status());
    if (record.meta.length > 6) record.meta.shift();
    if (response.ok()) void response.json().then((value) => {
      record.metaMode = typeof value?.mode === 'string' ? value.mode : null;
      record.demoAuth = typeof value?.features?.demo_auth === 'boolean' ? value.features.demo_auth : null;
    }).catch(() => {});
  });
  page.on('requestfailed', (request) => {
    if (record.failedRequests.length < 6) record.failedRequests.push({ path: pathOf(request.url()), error: safeText(request.failure()?.errorText ?? 'unknown') });
  });
  page.on('console', (message) => {
    if (message.type() === 'error' && record.consoleErrors.length < 6)
      record.consoleErrors.push({ message: safeText(message.text()), path: pathOf(message.location().url) });
  });
  page.on('pageerror', (error) => {
    if (record.pageErrors.length < 6) record.pageErrors.push(safeText(error.message));
  });
  return record;
}

async function failure(page, record, stage, reason) {
  const text = await page.locator('body').innerText().catch(() => '(body unavailable)');
  const diagnosis = {
    stage, reason, path: pathOf(page.url()), metaStatus: record.meta,
    metaMode: record.metaMode, demoAuth: record.demoAuth,
    failedRequests: record.failedRequests, consoleErrors: record.consoleErrors,
    pageErrors: record.pageErrors, visibleText: safeText(text),
  };
  throw new Error(`Dev entry failed: ${JSON.stringify(diagnosis)}`);
}

export async function waitForDevEntry(page, record, stage) {
  const login = page.getByRole('button', { name: 'Войти в dev' });
  const retry = page.getByRole('button', { name: 'Повторить загрузку данных' });
  try {
    await Promise.any([login.waitFor({ state: 'visible', timeout: 15000 }), retry.waitFor({ state: 'visible', timeout: 15000 })]);
  } catch { await failure(page, record, stage, 'neither dev login nor API retry appeared within 15 s'); }
  if (await login.isVisible()) return;
  if (!(await retry.isVisible())) await failure(page, record, stage, 'dev login absent and API retry not visible');

  const lastMeta = record.meta.at(-1);
  const failedMeta = record.failedRequests.some((item) => item.path.endsWith('/api/v1/meta'));
  const transient = lastMeta === 429 || (lastMeta >= 500 && lastMeta <= 599) || (lastMeta === undefined && failedMeta);
  if (!transient) await failure(page, record, stage, 'API retry is visible but /meta was not a transient network or 5xx/429 failure');

  process.stdout.write(JSON.stringify({ stage, action: 'retry-visible-transient-meta-once', metaStatus: record.meta,
    failedMeta }) + '\n');
  await retry.click();
  try { await login.waitFor({ state: 'visible', timeout: 15000 }); }
  catch { await failure(page, record, stage, 'dev login absent after one /meta retry'); }
}
