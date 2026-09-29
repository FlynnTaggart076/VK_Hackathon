import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiRequestError } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import type { Catalog, Job, MetaResponse, Profile, ReceiptQueued } from '../api/types';
import { canUpload } from './Onboarding';
import { ErrorMessage } from './errors';
import { jobStageLabel, jobStateLabel } from './labels';

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
    {meta.features.engine_stub && <p className="badge">Учебный режим: файл встанет в очередь, распознавание пока не выполняется.</p>}
    {!canUpload(profile, meta) ? <>
      <p role="status">Перед загрузкой заполните профиль и подтвердите актуальное уведомление. Общий вопрос можно задать после входа без загрузки документа.</p>
      <Link to="/onboarding">Перейти к первому запуску</Link>
    </> : !PREVIEW_MODE && <form onSubmit={(event) => void submit(event)}>
      <div className="upload-drop">
        <input id="receipt-file" className="sr-only" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={(event) => {
          setFile(event.target.files?.[0] ?? null); setKey(event.target.files?.[0] ? crypto.randomUUID() : null); setError(null);
        }} />
        <label htmlFor="receipt-file" className="btn secondary file-button">Выбрать файл платёжки</label>
        <p className="notice">{file ? `Выбран файл: ${file.name}` : 'Файл не выбран'}</p>
      </div>
      <button type="submit" disabled={busy || !file}>{busy ? 'Загружаем…' : 'Загрузить'}</button>
      <ErrorMessage error={error} />
      {error !== null && <p className="notice">{error instanceof ApiRequestError && error.status === 413
        ? 'Выберите файл меньшего размера в пределах указанного лимита.'
        : error instanceof ApiRequestError && error.status === 409
          ? 'Выберите файл заново, чтобы начать новую загрузку.'
          : 'После сетевого сбоя можно повторить тот же файл.'}</p>}
    </form>}
    {canUpload(profile, meta) && !!catalog?.demo_receipts.length && <div className="notice-box"><h3>Учебные образцы</h3><p>Синтетические документы выдаются после входа и обрабатываются сервером. Проверьте цифры перед подтверждением.</p><div className="sample-list">{catalog.demo_receipts.map((sample) => <button key={sample.fixture_id} type="button" disabled={busy} onClick={() => void uploadDemo(sample.fixture_id)}>Загрузить образец · {sample.label}</button>)}</div></div>}
  </section>;
}

export function retryMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 410) return 'Исходный файл уже удалён по сроку хранения. Загрузите платёжку заново.';
    if (error.status === 409) return 'Документ уже изменился: откройте его из истории.';
    if (error.status === 429) return 'Сейчас слишком много заданий в очереди. Попробуйте через минуту.';
  }
  return 'Не удалось запустить повторную обработку. Попробуйте ещё раз.';
}

export function Processing({ stub }: { stub: boolean }) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const jobId = params.get('job');
  const [retryError, setRetryError] = useState<unknown>(null);
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
  useEffect(() => {
    // A finished job goes straight to the review screen; the link below stays as a fallback.
    if (job?.state === 'succeeded' && job.receipt_id && job.id === jobId && !stub) {
      navigate(`/review?id=${encodeURIComponent(job.receipt_id)}`, { replace: true });
    }
  }, [job, jobId, stub]);

  async function retry() {
    if (!job?.receipt_id) return;
    setBusy(true); setRetryError(null);
    try {
      const receipt = await api.receipt(job.receipt_id);
      const queued = await api.retryReceipt(receipt.id, receipt.revision, crypto.randomUUID());
      setJob(null);
      setParams({ job: queued.job_id }, { replace: true });
    } catch (cause) { setRetryError(cause); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <h2>Обработка</h2>
    {!jobId && <p>Задание пока не выбрано. <Link to="/upload">Загрузить платёжку</Link></p>}
    {jobId && <>
      <p>Номер задания: {jobId}</p>
      {busy && <p role="status">Получаем состояние…</p>}
      {job && <p role="status">Состояние: {job.state === 'succeeded' && stub ? 'учебная обработка завершена без распознавания; нужен ручной ввод' : jobStateLabel(job.state).toLowerCase()}.</p>}
      {job?.stage && <p>Шаг: {jobStageLabel(job.stage).toLowerCase()}</p>}
      {job?.error && <p role="alert">{job.error.message}</p>}
      {stub && <p className="badge">Учебный режим: обработка завершится без распознавания; данные платёжки нужно будет ввести вручную.</p>}
      {job?.state === 'succeeded' && job.receipt_id && <p><Link to={`/review?id=${encodeURIComponent(job.receipt_id)}`}>Проверить данные платёжки</Link></p>}
      {job?.state === 'failed' && <div className="notice-box">
        <p>Обработка не удалась. Можно запустить её ещё раз или открыть документ из истории и ввести данные вручную.</p>
        <button type="button" onClick={() => void retry()} disabled={busy}>Повторить обработку</button>
        {retryError !== null && <p role="alert">{retryMessage(retryError)}</p>}
      </div>}
      <button type="button" onClick={() => void refresh(jobId)} disabled={busy}>Обновить состояние</button>
      <ErrorMessage error={error} />
    </>}
    <p><Link to="/history">К истории</Link></p>
  </section>;
}
