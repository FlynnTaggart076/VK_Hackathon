import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiRequestError } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import type { Catalog, Job, MetaResponse, Profile, ReceiptQueued } from '../api/types';
import { canUpload } from './Onboarding';
import { ErrorMessage } from './errors';

export function Upload({ meta, profile, catalog, onQueued }: {
  meta: MetaResponse; profile: Profile | null; catalog: Catalog | null; onQueued: (value: ReceiptQueued) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !key || !canUpload(profile, meta)) return;
    setBusy(true); setError(null);
    const controller = new AbortController(); pending.current = controller;
    try { onQueued(await api.upload(file, key, controller.signal)); }
    catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }

  async function uploadDemo(id: string) {
    if (!canUpload(profile, meta)) return;
    setBusy(true); setError(null);
    const controller = new AbortController(); pending.current = controller;
    try {
      onQueued(await api.importDemo(id, crypto.randomUUID(), controller.signal));
    } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }

  return <section className="panel">
    <h2>Загрузка платёжки</h2>
    {PREVIEW_MODE ? <p className="review-warning">Публичный учебный стенд: не загружайте личные квитанции. Для проверки выберите синтетический образец ниже.</p> :
      <p>PDF, JPEG или PNG; до {Math.floor(meta.limits.upload_max_bytes / 1024 / 1024)} МБ и {meta.limits.pdf_max_pages} страниц PDF.</p>}
    {meta.features.engine_stub && <p className="badge">Dev stub: файл будет поставлен в очередь, OCR пока не выполняется.</p>}
    {!canUpload(profile, meta) ? <>
      <p role="status">Перед загрузкой заполните профиль и подтвердите актуальное уведомление. Общий вопрос можно задать после входа без загрузки документа.</p>
      <Link to="/onboarding">Перейти к первому запуску</Link>
    </> : !PREVIEW_MODE && <form onSubmit={(event) => void submit(event)}>
      <label htmlFor="receipt-file">Файл платёжки</label>
      <input id="receipt-file" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => {
        setFile(event.target.files?.[0] ?? null); setKey(event.target.files?.[0] ? crypto.randomUUID() : null); setError(null);
      }} />
      <button type="submit" disabled={busy || !file}>{busy ? 'Загружаем…' : 'Загрузить'}</button>
      {file && <p>Выбран файл: {file.name}</p>}
      <ErrorMessage error={error} />
      {error !== null && <p className="notice">{error instanceof ApiRequestError && error.status === 413
        ? 'Выберите файл меньшего размера в пределах указанного лимита.'
        : error instanceof ApiRequestError && error.status === 409
          ? 'Выберите файл заново, чтобы начать новую загрузку.'
          : 'После сетевого сбоя можно повторить тот же файл.'}</p>}
    </form>}
    {canUpload(profile, meta) && !!catalog?.demo_receipts.length && <div className="notice-box"><h3>Учебные образцы</h3><p>Синтетические документы выдаются после входа и обрабатываются сервером. Проверьте цифры перед подтверждением.</p><div className="actions">{catalog.demo_receipts.map((sample) => <button key={sample.fixture_id} type="button" disabled={busy} onClick={() => void uploadDemo(sample.fixture_id)}>Загрузить образец · {sample.label}</button>)}</div></div>}
  </section>;
}

export function Processing({ stub }: { stub: boolean }) {
  const [params] = useSearchParams();
  const jobId = params.get('job');
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [reload, setReload] = useState(0);
  const pending = useRef<AbortController | null>(null);

  async function refresh(id: string) {
    pending.current?.abort();
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError(null);
    try { setJob(await api.job(id, controller.signal)); }
    catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }
  useEffect(() => { if (jobId) void refresh(jobId); return () => pending.current?.abort(); }, [jobId, reload]);
  useEffect(() => {
    if (!jobId || !job || !['queued', 'running'].includes(job.state) || error) return;
    const timer = window.setTimeout(() => setReload((value) => value + 1), 2500);
    return () => window.clearTimeout(timer);
  }, [jobId, job, error]);

  return <section className="panel">
    <h2>Обработка</h2>
    {!jobId && <p>Задание пока не выбрано. <Link to="/upload">Загрузить платёжку</Link></p>}
    {jobId && <>
      <p>Номер задания: {jobId}</p>
      {busy && <p role="status">Получаем состояние…</p>}
      {job && <p role="status">Состояние: {job.state === 'queued' ? 'в очереди' : job.state === 'running' ? 'обработка выполняется' : job.state === 'failed' ? 'ошибка обработки' : stub ? 'dev обработка завершена без распознавания; требуется ручной ввод' : 'обработка завершена'}.</p>}
      {job?.stage && <p>Шаг: {job.stage}</p>}
      {job?.error && <p role="alert">{job.error.message}</p>}
      {stub && <p className="badge">Dev stub: задание завершится без OCR; для платёжки потребуется ручной ввод.</p>}
      {job?.state === 'succeeded' && job.receipt_id && <p><Link to={`/review?id=${encodeURIComponent(job.receipt_id)}`}>Проверить данные платёжки</Link></p>}
      {job?.state === 'failed' && <p>Проверьте ошибку задания. Повторная обработка доступна после исправления причины на сервере.</p>}
      <button type="button" onClick={() => void refresh(jobId)} disabled={busy}>Обновить состояние</button>
      <ErrorMessage error={error} />
    </>}
    <p><Link to="/history">К истории</Link></p>
  </section>;
}
