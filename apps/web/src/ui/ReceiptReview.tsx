import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiRequestError } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import type { BillData, FieldEvidence, Issue, ReceiptView } from '../api/types';
import { billErrors, normalizeBill } from './billForm';
import { ErrorMessage } from './errors';

type Service = BillData['services'][number];
type Adjustment = BillData['adjustments'][number];
const serviceCodes: Service['service_code'][] = ['cold_water', 'hot_water', 'drainage', 'electricity', 'heating', 'maintenance', 'capital_repair', 'waste', 'other'];
const scopes: Service['scope'][] = ['individual', 'common_property', 'unspecified'];
const units: NonNullable<Service['unit']>[] = ['m3', 'kwh', 'gcal', 'm2', 'month', 'person', 'other'];
const display = (value: string | null) => value ?? '';

function Field({ label, value, onChange, hint, inputMode, placeholder }: {
  label: string; value: string | null; onChange: (value: string | null) => void;
  hint?: React.ReactNode; inputMode?: 'decimal' | 'text'; placeholder?: string;
}) {
  const id = useRef(crypto.randomUUID());
  return <div className="field"><label htmlFor={id.current}>{label}</label>
    <input id={id.current} value={display(value)} inputMode={inputMode} placeholder={placeholder}
      onChange={(event) => onChange(event.target.value || null)} />{hint}</div>;
}

function Evidence({ path, evidence, issues }: { path: string; evidence: FieldEvidence[]; issues: Issue[] }) {
  const related = evidence.filter((item) => item.path === path);
  const warnings = issues.filter((item) => item.path === path);
  if (!related.length && !warnings.length) return null;
  return <div className="field-note">{related.map((item, index) => <p key={index} className={item.needs_review ? 'review-warning' : undefined}>
    {item.source === 'manual' ? 'Введено вручную' : item.needs_review ? 'Проверьте' : 'Распознано'} · {item.source}
    {item.page_number && ` · стр. ${item.page_number}`}{item.source_text && ` · «${item.source_text}»`}{item.reason && ` · ${item.reason}`}
  </p>)}{warnings.map((item, index) => <p key={index} className="review-warning">{item.message}</p>)}</div>;
}

function SourcePreview({ receipt }: { receipt: ReceiptView }) {
  const [page, setPage] = useState(1);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [reloadPage, setReloadPage] = useState(0);
  useEffect(() => {
    setUrl(null); setError(null);
    if (!receipt.document.available) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    api.page(receipt.id, page, controller.signal).then((blob) => {
      if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); }
    }).catch((cause) => { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [receipt.id, receipt.document.available, page, reloadPage]);
  async function download() {
    setBusy(true); setError(null);
    try {
      const blob = await api.source(receipt.id);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl; anchor.download = `receipt-${receipt.id}.${receipt.document.mime_type === 'application/pdf' ? 'pdf' : receipt.document.mime_type === 'image/jpeg' ? 'jpg' : 'png'}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  return <section className="notice-box" aria-label="Исходный документ"><h3>Исходник</h3>
    {!receipt.document.available ? <p>Срок хранения исходника истёк или файл недоступен. Сохранённые цифры можно проверить, но страницу показать нельзя.</p> : <>
      {url ? <><img className="receipt-page" src={url} alt={`Страница ${page} исходной платёжки`} /><p><a href={url} target="_blank" rel="noopener noreferrer">Открыть страницу крупно</a></p></> : !error && <p role="status">Загружаем защищённый просмотр страницы…</p>}
      <ErrorMessage error={error} />
      {error && <button type="button" onClick={() => setReloadPage((value) => value + 1)}>Повторить просмотр страницы</button>}
      {receipt.document.page_count && receipt.document.page_count > 1 && <div className="actions">
        <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Предыдущая</button>
        <span>Страница {page} из {receipt.document.page_count}</span>
        <button type="button" disabled={page >= receipt.document.page_count} onClick={() => setPage(page + 1)}>Следующая</button>
      </div>}
      <button type="button" disabled={busy} onClick={() => void download()}>{busy ? 'Скачиваем…' : 'Скачать исходник'}</button>
    </>}
  </section>;
}

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

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setLoading(true); setError(null); setReceipt(null); setDraft(null); setConflict(null);
    api.receipt(id, controller.signal).then((value) => { setReceipt(value); setDraft(value.bill_data); setExpandedLines(value.bill_data.services[0] ? [value.bill_data.services[0].line_id] : []); })
      .catch((cause) => { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload]);

  function update<K extends keyof BillData>(key: K, value: BillData[K]) {
    setDraft((current) => current ? { ...current, [key]: value } : null);
  }
  function updateLine(index: number, patch: Partial<Service>) {
    setDraft((current) => current ? { ...current, services: current.services.map((line, pos) => pos === index ? { ...line, ...patch } : line) } : null);
  }
  function updateAdjustment(index: number, patch: Partial<Adjustment>) {
    setDraft((current) => current ? { ...current, adjustments: current.adjustments.map((item, pos) => pos === index ? { ...item, ...patch } : item) } : null);
  }
  function updateSettlement<K extends keyof BillData['settlement']>(key: K, value: BillData['settlement'][K]) {
    setDraft((current) => current ? { ...current, settlement: { ...current.settlement, [key]: value } } : null);
  }
  async function loadConflict(cause: unknown) {
    if (cause instanceof ApiRequestError && cause.status === 409 && id) {
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
      setReceipt(result); setDraft(result.bill_data); setAcknowledged([]); confirmKey.current = crypto.randomUUID();
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
  const canConfirm = receipt?.status === 'needs_review' && !busy && !conflict && !dirty && !validation.length &&
    !receipt.issues.some((issue) => issue.severity === 'error') && warnings.every((issue) => acknowledged.includes(issue.code));
  return <section className="panel"><h2>Проверка платёжки</h2>
    {loading && <p role="status">Загружаем документ с сервера…</p>}
    <ErrorMessage error={error} />
    {!receipt && !loading && <button type="button" onClick={() => setReload((value) => value + 1)}>Повторить загрузку</button>}
    {receipt && draft && <>
      <p className="badge">{receipt.dataset_kind === 'synthetic' ? 'Синтетический пример' : 'Загруженный пользователем файл'} · ревизия {receipt.revision}</p>
      <p>Состояние: {receipt.status}. Извлечение: {receipt.extraction_outcome === 'recognized' ? 'распознано, проверьте цифры' : receipt.extraction_outcome === 'partial' ? 'частично распознано' : receipt.extraction_outcome === 'manual_required' ? 'нужен ручной ввод' : 'результат пока не готов'}.</p>
      {receipt.status === 'queued' || receipt.status === 'processing' ? <p role="status">Обработка ещё не завершена. <Link to={receipt.job ? `/processing?job=${encodeURIComponent(receipt.job.id)}` : '/upload'}>Вернуться к обработке</Link></p> : null}
      {receipt.status === 'failed' && <p role="alert">Обработка не удалась. Дождитесь доступного повторного запуска или введите данные вручную после перехода документа в состояние проверки.</p>}
      <SourcePreview receipt={receipt} />
      {receipt.issues.length > 0 && <section className="notice-box"><h3>Предупреждения и ошибки</h3><ul>{receipt.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.severity}: {issue.message}{issue.path && ` (${issue.path})`}</li>)}</ul></section>}
      {conflict && <div className="error" role="alert"><p>На сервере уже ревизия {conflict.revision}. Ваши правки сохранены в форме и не отправлены повторно.</p>
        <button type="button" onClick={() => { setReceipt(conflict); setConflict(null); setError(null); setAcknowledged([]); confirmKey.current = crypto.randomUUID(); }}>Применить мои правки к актуальной ревизии</button>
        <button type="button" onClick={() => { setReceipt(conflict); setDraft(conflict.bill_data); setConflict(null); setError(null); setAcknowledged([]); }}>Использовать серверную версию</button></div>}
      <form onSubmit={(event) => void save(event)}><h3>Данные для проверки</h3>
        <p>Поля без значения остаются неизвестными. Организация может быть неизвестна; сервер предупредит об этом. Сверьте каждое число с исходником. Сохранение не подтверждает юридическую правильность начисления.</p>
        <Field label="Период (ГГГГ-ММ)" value={draft.period} onChange={(value) => update('period', value)} hint={<Evidence path="/period" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <Field label="Организация" value={draft.issuer_name} onChange={(value) => update('issuer_name', value)} hint={<Evidence path="/issuer_name" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <Field label="Номер лицевого счёта" value={draft.account_number} onChange={(value) => update('account_number', value)} hint={<Evidence path="/account_number" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <Field label="Адрес" value={draft.address_text} onChange={(value) => update('address_text', value)} hint={<Evidence path="/address_text" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <details><summary>Дополнительные реквизиты</summary>
          <Field label="Код поставщика (если известен)" value={draft.provider_id} onChange={(value) => update('provider_id', value)} hint={<Evidence path="/provider_id" evidence={receipt.field_evidence} issues={receipt.issues} />} />
          <p>Макет: {draft.template_id ?? 'не определён'}; версия: {draft.template_version ?? 'не определена'}. Эти значения определяет сервер.</p>
        </details>
        <h3>Строки начислений</h3>
        {draft.services.length === 0 && <p>Строки не найдены. Добавьте их по исходнику.</p>}
        {draft.services.map((line, index) => <details key={line.line_id} className="service-row" open={expandedLines.includes(line.line_id)}
          onToggle={(event) => { const open = event.currentTarget.open; setExpandedLines((current) => open ? [...new Set([...current, line.line_id])] : current.filter((id) => id !== line.line_id)); }}>
          <summary>Строка {index + 1} · {line.raw_name || 'без названия'} · {line.charge_amount === null ? 'сумма неизвестна' : `${line.charge_amount} ₽`}</summary>
          <fieldset><legend>Проверка строки {index + 1}</legend>
          <Field label="Название услуги" value={line.raw_name} onChange={(value) => updateLine(index, { raw_name: value ?? '' })} hint={<Evidence path={`/services/${index}/raw_name`} evidence={receipt.field_evidence} issues={receipt.issues} />} />
          <label htmlFor={`code-${line.line_id}`}>Код услуги</label><select id={`code-${line.line_id}`} value={line.service_code} onChange={(event) => updateLine(index, { service_code: event.target.value as Service['service_code'] })}>{serviceCodes.map((code) => <option key={code} value={code}>{code}</option>)}</select>
          <label htmlFor={`scope-${line.line_id}`}>Область</label><select id={`scope-${line.line_id}`} value={line.scope} onChange={(event) => updateLine(index, { scope: event.target.value as Service['scope'] })}>{scopes.map((scope) => <option key={scope} value={scope}>{scope}</option>)}</select>
          <label htmlFor={`unit-${line.line_id}`}>Единица</label><select id={`unit-${line.line_id}`} value={line.unit ?? ''} onChange={(event) => updateLine(index, { unit: (event.target.value || null) as Service['unit'] })}><option value="">Неизвестна</option>{units.map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select>
          <Field label="Подпись единицы из документа" value={line.unit_label} onChange={(value) => updateLine(index, { unit_label: value })} />
          <Field label="Объём" value={line.quantity} inputMode="decimal" onChange={(value) => updateLine(index, { quantity: value })} hint={<Evidence path={`/services/${index}/quantity`} evidence={receipt.field_evidence} issues={receipt.issues} />} />
          <Field label="Тариф" value={line.tariff} inputMode="decimal" onChange={(value) => updateLine(index, { tariff: value })} hint={<Evidence path={`/services/${index}/tariff`} evidence={receipt.field_evidence} issues={receipt.issues} />} />
          <Field label="Начислено за период, ₽" value={line.charge_amount} inputMode="decimal" onChange={(value) => updateLine(index, { charge_amount: value })} hint={<Evidence path={`/services/${index}/charge_amount`} evidence={receipt.field_evidence} issues={receipt.issues} />} />
          <p>Основание суммы: {line.calculation_kind === 'simple_product' ? 'объём × тариф' : 'сумма из документа'}. Его определяет сервер; новая строка сохраняется как сумма из документа.</p>
          <details><summary>Служебные признаки строки</summary>
            <Field label="Ключ поставщика" value={line.supplier_key} onChange={(value) => updateLine(index, { supplier_key: value })} />
            <Field label="Ключ сегмента" value={line.segment_key} onChange={(value) => updateLine(index, { segment_key: value })} />
          </details>
          <button type="button" onClick={() => update('services', draft.services.filter((_, pos) => pos !== index))}>Удалить строку</button>
          </fieldset>
        </details>)}
        <button type="button" onClick={() => { const line: Service = { line_id: crypto.randomUUID(), raw_name: '', service_code: 'other', scope: 'unspecified', unit: null, unit_label: null, quantity: null, tariff: null, charge_amount: null, supplier_key: null, segment_key: null, calculation_kind: 'document_amount' }; update('services', [...draft.services, line]); setExpandedLines((current) => [...current, line.line_id]); }}>Добавить строку</button>
        <h3>Перерасчёты</h3>
        {draft.adjustments.map((item, index) => <fieldset key={item.adjustment_id}><legend>Перерасчёт {index + 1}</legend>
          <Field label="Название" value={item.label} onChange={(value) => updateAdjustment(index, { label: value ?? '' })} />
          <Field label="Сумма, ₽ (может быть отрицательной)" value={item.amount} inputMode="decimal" onChange={(value) => updateAdjustment(index, { amount: value })} hint={<Evidence path={`/adjustments/${index}/amount`} evidence={receipt.field_evidence} issues={receipt.issues} />} />
          <label htmlFor={`adjustment-line-${item.adjustment_id}`}>Связь со строкой</label><select id={`adjustment-line-${item.adjustment_id}`} value={item.service_line_id ?? ''} onChange={(event) => updateAdjustment(index, { service_line_id: event.target.value || null })}><option value="">Не связана с отдельной строкой</option>{draft.services.map((line, lineIndex) => <option key={line.line_id} value={line.line_id}>{lineIndex + 1}. {line.raw_name || 'Без названия'}</option>)}</select>
          <Field label="Период перерасчёта (ГГГГ-ММ)" value={item.related_period} onChange={(value) => updateAdjustment(index, { related_period: value })} />
          <button type="button" onClick={() => update('adjustments', draft.adjustments.filter((_, pos) => pos !== index))}>Удалить перерасчёт</button>
        </fieldset>)}
        <button type="button" onClick={() => update('adjustments', [...draft.adjustments, { adjustment_id: crypto.randomUUID(), label: '', amount: null, service_line_id: null, related_period: null }])}>Добавить перерасчёт</button>
        <h3>Итоги документа</h3>
        <Field label="Начислено за текущий период, ₽" value={draft.document_current_charges} inputMode="decimal" onChange={(value) => update('document_current_charges', value)} hint={<Evidence path="/document_current_charges" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <Field label="К оплате по документу, ₽" value={draft.document_total_due} inputMode="decimal" onChange={(value) => update('document_total_due', value)} hint={<Evidence path="/document_total_due" evidence={receipt.field_evidence} issues={receipt.issues} />} />
        <p>Формула остатка: <strong>{draft.settlement.formula_kind === 'signed_balance_v1' ? 'Остаток с учётом оплат' : 'Не определена'}</strong>. Её определяет сервер по макету документа; изменить выбор в форме нельзя.</p>
        <Field label="Остаток на начало, ₽" value={draft.settlement.opening_balance} inputMode="decimal" onChange={(value) => updateSettlement('opening_balance', value)} />
        <Field label="Учтённые оплаты, ₽" value={draft.settlement.payments_credited} inputMode="decimal" onChange={(value) => updateSettlement('payments_credited', value)} />
        <Field label="Пени, ₽" value={draft.settlement.penalties} inputMode="decimal" onChange={(value) => updateSettlement('penalties', value)} />
        <Field label="Другие изменения счёта, ₽" value={draft.settlement.other_account_changes} inputMode="decimal" onChange={(value) => updateSettlement('other_account_changes', value)} />
        <Field label="Остаток по документу, ₽" value={draft.settlement.document_closing_balance} inputMode="decimal" onChange={(value) => updateSettlement('document_closing_balance', value)} />
        {validation.length > 0 && <div className="error" role="alert"><strong>Для сохранения исправьте:</strong><ul>{validation.map((item) => <li key={item}>{item}</li>)}</ul></div>}
        {receipt.status === 'needs_review' || receipt.status === 'confirmed' ? <button type="submit" disabled={busy || !!conflict || !!validation.length || !dirty}>{busy ? 'Сохраняем…' : 'Сохранить исправления'}</button> : null}
      </form>
      {receipt.status === 'needs_review' && <section className="notice-box"><h3>Подтверждение данных</h3>
        <p>Вы подтверждаете проверенные вами данные платёжки, а не законность начислений.</p>
        {warnings.map((issue, index) => <label className="check" key={`${issue.code}-${index}`}><input type="checkbox" checked={acknowledged.includes(issue.code)} onChange={(event) => setAcknowledged((current) => event.target.checked ? [...new Set([...current, issue.code])] : current.filter((code) => code !== issue.code))} />Принимаю предупреждение {issue.code}: {issue.message}</label>)}
        {dirty && <p>Сначала сохраните исправления.</p>}
        {receipt.issues.some((issue) => issue.severity === 'error') && <p role="alert">Сервер сообщил об ошибках данных. Подтверждение недоступно.</p>}
        <button type="button" disabled={!canConfirm} onClick={() => void confirm()}>Подтвердить проверенные данные</button>
      </section>}
      {receipt.status === 'confirmed' && <div className="actions"><Link to={`/explanation?id=${encodeURIComponent(receipt.id)}`}>Открыть объяснение</Link><Link to={`/assistant?receipt=${encodeURIComponent(receipt.id)}`}>Вопрос по платёжке</Link><Link to={`/city-comparison?receipt=${encodeURIComponent(receipt.id)}`}>{PREVIEW_MODE && receipt.dataset_kind === 'synthetic' ? 'Сравнить с учебной выборкой' : 'Сравнить с городом'}</Link></div>}
    </>}
  </section>;
}
