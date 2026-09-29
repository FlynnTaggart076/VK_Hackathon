import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiRequestError } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import type { BillData, ReceiptView } from '../api/types';
import { billErrors, normalizeBill } from './billForm';
import { ErrorMessage } from './errors';
import { datasetKindLabel, extractionOutcomeLabel, formatMoney, formatPeriod, receiptStatusLabel, type ServiceCode } from './labels';
import { availableServiceCodes, changeServiceCode, newServiceLine } from './serviceCatalog';
import { AdjustmentCard } from './review/AdjustmentCard';
import { Evidence, lineNeedsAttention } from './review/Evidence';
import { Field } from './review/Field';
import { IssuesPanel } from './review/IssuesPanel';
import { LineCard } from './review/LineCard';
import { SourcePreview } from './review/SourcePreview';
import { TotalsSection } from './review/TotalsSection';

type Service = BillData['services'][number];
type Adjustment = BillData['adjustments'][number];

const statusChip: Record<ReceiptView['status'], string> = {
  queued: 'chip--info', processing: 'chip--info', needs_review: 'chip--warn', confirmed: 'chip--ok', failed: 'chip--warn',
};

export function ReceiptReview() {
  const [params] = useSearchParams();
  const id = params.get('id');
  const navigate = useNavigate();
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [draft, setDraft] = useState<BillData | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [conflict, setConflict] = useState<ReceiptView | null>(null);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const confirmKey = useRef(crypto.randomUUID());
  const [reload, setReload] = useState(0);
  const [expandedLines, setExpandedLines] = useState<string[]>([]);
  const [lineNotes, setLineNotes] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setLoading(true); setError(null); setReceipt(null); setDraft(null); setConflict(null); setLineNotes({});
    api.receipt(id, controller.signal).then((value) => {
      setReceipt(value); setDraft(value.bill_data);
      const focus = value.bill_data.services.findIndex((_, index) => lineNeedsAttention(index, value.field_evidence, value.issues));
      const first = value.bill_data.services[Math.max(focus, 0)];
      setExpandedLines(first ? [first.line_id] : []);
    }).catch((cause) => { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload]);

  function update<K extends keyof BillData>(key: K, value: BillData[K]) {
    setDraft((current) => current ? { ...current, [key]: value } : null);
  }
  function updateLine(index: number, patch: Partial<Service>) {
    setDraft((current) => current ? { ...current, services: current.services.map((line, pos) => pos === index ? { ...line, ...patch } : line) } : null);
    if (draft && ('quantity' in patch || 'tariff' in patch || 'unit' in patch)) {
      const lineId = draft.services[index]?.line_id;
      if (lineId) setLineNotes((current) => ({ ...current, [lineId]: [] }));
    }
  }
  function changeService(index: number, code: ServiceCode) {
    if (!draft) return;
    const line = draft.services[index];
    const taken = availableServiceCodes(draft.services, line.line_id).find((choice) => choice.code === code)?.takenBy;
    if (taken && code !== line.service_code) return; // Each service can be used once; «Прочее» is never taken.
    const original = receipt?.bill_data.services.find((item) => item.line_id === line.line_id);
    const result = changeServiceCode(line, code, original);
    setDraft({ ...draft, services: draft.services.map((item, pos) => pos === index ? result.line : item) });
    setLineNotes((current) => ({ ...current, [line.line_id]: result.notes }));
  }
  function removeLine(index: number) {
    if (!draft) return;
    const removed = draft.services[index];
    update('services', draft.services.filter((_, pos) => pos !== index));
    setExpandedLines((current) => current.filter((lineId) => lineId !== removed.line_id));
  }
  function addLine() {
    if (!draft) return;
    const line = newServiceLine();
    update('services', [...draft.services, line]);
    setExpandedLines((current) => [...current, line.line_id]);
  }
  function updateAdjustment(index: number, patch: Partial<Adjustment>) {
    setDraft((current) => current ? { ...current, adjustments: current.adjustments.map((item, pos) => pos === index ? { ...item, ...patch } : item) } : null);
  }
  function updateSettlement<K extends keyof BillData['settlement']>(key: K, value: BillData['settlement'][K]) {
    setDraft((current) => current ? { ...current, settlement: { ...current.settlement, [key]: value } } : null);
  }
  async function loadConflict(cause: unknown) {
    if (cause instanceof ApiRequestError && cause.status === 409 && cause.code === 'REVISION_CONFLICT' && id) {
      try { setConflict(await api.receipt(id)); } catch (reloadCause) { setError(reloadCause); return; }
    }
    setError(cause);
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!id || !receipt || !draft || conflict) return;
    const normalized = normalizeBill(draft);
    setDraft(normalized);
    if (billErrors(normalized).length) return;
    setBusy(true); setError(null);
    try {
      const result = await api.editReceipt(id, { expected_revision: receipt.revision, bill_data: normalized });
      setReceipt(result); setDraft(result.bill_data); setAcknowledged([]); setLineNotes({}); confirmKey.current = crypto.randomUUID();
    } catch (cause) { await loadConflict(cause); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!id || !receipt || !draft || conflict) return;
    const warnings = receipt.issues.filter((issue) => issue.severity === 'warning').map((issue) => issue.code);
    if (billErrors(normalizeBill(draft)).length || JSON.stringify(draft) !== JSON.stringify(receipt.bill_data) ||
      receipt.issues.some((issue) => issue.severity === 'error') || warnings.some((code) => !acknowledged.includes(code))) return;
    setBusy(true); setError(null);
    try {
      const result = await api.confirmReceipt(id, { expected_revision: receipt.revision, acknowledged_warning_codes: [...new Set(warnings)] }, confirmKey.current);
      setReceipt(result); navigate(`/explanation?id=${encodeURIComponent(result.id)}`);
    } catch (cause) { await loadConflict(cause); }
    finally { setBusy(false); }
  }

  if (!id) return <section className="panel"><h2>Проверка платёжки</h2><p>Документ не выбран. <Link to="/upload">Загрузить платёжку</Link></p></section>;
  const normalized = draft ? normalizeBill(draft) : null;
  const validation = normalized ? billErrors(normalized) : [];
  const dirty = !!draft && !!receipt && JSON.stringify(draft) !== JSON.stringify(receipt.bill_data);
  const warnings = receipt?.issues.filter((issue) => issue.severity === 'warning') ?? [];
  const hasServerErrors = !!receipt?.issues.some((issue) => issue.severity === 'error');
  const unacknowledged = warnings.some((issue) => !acknowledged.includes(issue.code));
  const canConfirm = receipt?.status === 'needs_review' && !busy && !conflict && !dirty && !validation.length && !hasServerErrors && !unacknowledged;
  const editable = receipt?.status === 'needs_review' || receipt?.status === 'confirmed';
  const barHint = dirty
    ? (validation.length ? 'Исправьте ошибки в форме.' : 'Сохраните исправления, затем подтвердите данные.')
    : hasServerErrors ? 'Сервер сообщил об ошибках данных.'
      : unacknowledged ? 'Отметьте предупреждения выше.' : '';
  return <section className="panel"><h2>Проверка платёжки</h2>
    {loading && <p role="status">Загружаем документ с сервера…</p>}
    <ErrorMessage error={error} />
    {!receipt && !loading && <button type="button" onClick={() => setReload((value) => value + 1)}>Повторить загрузку</button>}
    {receipt && draft && <>
      <div className="hero">
        <div className="label">Итого к оплате</div>
        <div className="amount">{formatMoney(receipt.bill_data.document_total_due)}</div>
        <div>{formatPeriod(receipt.bill_data.period)} · {receipt.bill_data.issuer_name ?? 'Организация не определена'}</div>
      </div>
      <div className="chips">
        <span className={`chip ${statusChip[receipt.status]}`}>{receiptStatusLabel(receipt.status)}</span>
        <span className="chip">{datasetKindLabel(receipt.dataset_kind)}</span>
        <span className="chip">Версия {receipt.revision}</span>
      </div>
      {receipt.status === 'needs_review' && <p className="notice">{extractionOutcomeLabel(receipt.extraction_outcome)}. Сверьте каждое число с оригиналом.</p>}
      {receipt.status === 'queued' || receipt.status === 'processing' ? <p role="status">Обработка ещё не завершена. <Link to={receipt.job ? `/processing?job=${encodeURIComponent(receipt.job.id)}` : '/upload'}>Вернуться к обработке</Link></p> : null}
      {receipt.status === 'failed' && <p role="alert">Обработка не удалась. Дождитесь доступного повторного запуска или введите данные вручную после перехода документа в состояние проверки.</p>}
      <SourcePreview receipt={receipt} />
      {conflict && <div className="error" role="alert"><p>На сервере уже версия {conflict.revision}. Ваши правки сохранены в форме и не отправлены повторно.</p>
        <div className="actions">
          <button type="button" onClick={() => { setReceipt(conflict); setConflict(null); setError(null); setAcknowledged([]); confirmKey.current = crypto.randomUUID(); }}>Применить мои правки к актуальной версии</button>
          <button type="button" className="secondary" onClick={() => { setReceipt(conflict); setDraft(conflict.bill_data); setConflict(null); setError(null); setAcknowledged([]); }}>Использовать серверную версию</button>
        </div></div>}
      <form id="review-form" onSubmit={(event) => void save(event)}><h3>Данные для проверки</h3>
        <p className="notice">Поля без значения остаются неизвестными. Сохранение не подтверждает законность начислений.</p>
        <Field label="Период (ГГГГ-ММ)" value={draft.period} maxLength={7} onChange={(value) => update('period', value)}
          hint={<><p className="field-hint">{formatPeriod(draft.period)}</p><Evidence path="/period" evidence={receipt.field_evidence} issues={receipt.issues} /></>} />
        <Field label="Организация" value={draft.issuer_name} maxLength={200} onChange={(value) => update('issuer_name', value)} hint={<Evidence path="/issuer_name" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <Field label="Номер лицевого счёта" value={draft.account_number} maxLength={64} onChange={(value) => update('account_number', value)} hint={<Evidence path="/account_number" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <Field label="Адрес" value={draft.address_text} maxLength={500} onChange={(value) => update('address_text', value)} hint={<Evidence path="/address_text" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <details><summary>Дополнительные реквизиты</summary>
          <Field label="Код поставщика (если известен)" value={draft.provider_id} maxLength={200} onChange={(value) => update('provider_id', value)} hint={<Evidence path="/provider_id" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        </details>
        <h3>Строки начислений</h3>
        {draft.services.length === 0 && <p>Строки не найдены. Добавьте их по оригиналу.</p>}
        {draft.services.map((line, index) => <LineCard key={line.line_id} line={line} index={index} lines={draft.services}
          evidence={receipt.field_evidence} issues={receipt.issues} notes={lineNotes[line.line_id] ?? []} open={expandedLines.includes(line.line_id)}
          onToggle={(open) => setExpandedLines((current) => open ? [...new Set([...current, line.line_id])] : current.filter((lineId) => lineId !== line.line_id))}
          onChange={(patch) => updateLine(index, patch)} onServiceChange={(code) => changeService(index, code)} onRemove={() => removeLine(index)} />)}
        <button type="button" className="add-card" onClick={addLine}>Добавить строку</button>
        <h3>Перерасчёты</h3>
        {draft.adjustments.length === 0 && <p className="notice">Перерасчётов в документе нет.</p>}
        {draft.adjustments.map((item, index) => <AdjustmentCard key={item.adjustment_id} item={item} index={index} lines={draft.services}
          evidence={receipt.field_evidence} issues={receipt.issues} onChange={(patch) => updateAdjustment(index, patch)}
          onRemove={() => update('adjustments', draft.adjustments.filter((_, pos) => pos !== index))} />)}
        <button type="button" className="add-card" onClick={() => update('adjustments', [...draft.adjustments, { adjustment_id: crypto.randomUUID(), label: '', amount: null, service_line_id: null, related_period: null }])}>Добавить перерасчёт</button>
        <TotalsSection draft={draft} evidence={receipt.field_evidence} issues={receipt.issues} onChange={update} onSettlementChange={updateSettlement} />
        {validation.length > 0 && <div className="error" role="alert"><strong>Для сохранения исправьте:</strong><ul>{validation.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      </form>
      <IssuesPanel issues={receipt.issues} acknowledged={acknowledged} canAcknowledge={receipt.status === 'needs_review'}
        onAcknowledge={(code, checked) => setAcknowledged((current) => checked ? [...new Set([...current, code])] : current.filter((item) => item !== code))} />
      {receipt.status === 'needs_review' && <p className="notice">Вы подтверждаете проверенные вами данные платёжки, а не законность начислений.</p>}
      {receipt.status === 'confirmed' && !dirty && <div className="actions"><Link to={`/explanation?id=${encodeURIComponent(receipt.id)}`}>Открыть объяснение</Link><Link to={`/assistant?receipt=${encodeURIComponent(receipt.id)}`}>Вопрос по платёжке</Link><Link to={`/city-comparison?receipt=${encodeURIComponent(receipt.id)}`}>{PREVIEW_MODE && receipt.dataset_kind === 'synthetic' ? 'Сравнить с учебной выборкой' : 'Сравнить с городом'}</Link></div>}
      {editable && (dirty || receipt.status === 'needs_review') && <div className="sticky-bar">
        {dirty
          ? <button type="submit" form="review-form" disabled={busy || !!conflict || !!validation.length}>{busy ? 'Сохраняем…' : 'Сохранить исправления'}</button>
          : <button type="button" disabled={!canConfirm} onClick={() => void confirm()}>{busy ? 'Подтверждаем…' : 'Подтвердить проверенные данные'}</button>}
        {barHint && <p>{barHint}</p>}
      </div>}
    </>}
  </section>;
}
