import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Catalog, DraftView, ReceiptView } from '../api/types';
import { ErrorMessage } from './errors';

export function Draft({ catalog }: { catalog: Catalog | null }) {
  const [params, setParams] = useSearchParams();
  const receiptId = params.get('receipt');
  const draftId = params.get('id');
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [draft, setDraft] = useState<DraftView | null>(null);
  const [text, setText] = useState('');
  const [topic, setTopic] = useState('');
  const [lineId, setLineId] = useState('');
  const [question, setQuestion] = useState('Почему выросла сумма за воду?');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [staleApproved, setStaleApproved] = useState(false);
  useEffect(() => {
    let active = true; setError(null); setDraft(null); setReceipt(null); setNotice('');
    if (draftId) api.draft(draftId).then((value) => { if (active) { setDraft(value); setText(value.text); } }).catch((cause) => { if (active) setError(cause); });
    if (receiptId) api.receipt(receiptId).then((value) => { if (active) { setReceipt(value); setLineId(value.bill_data.services[0]?.line_id ?? ''); } }).catch((cause) => { if (active) setError(cause); });
    return () => { active = false; };
  }, [draftId, receiptId]);
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!receipt || receipt.status !== 'confirmed' || !topic) return;
    setBusy(true); setError(null); setNotice('');
    try {
      const value = await api.createDraft({ topic_id: topic, organization_id: null,
        receipt_refs: [{ id: receipt.id, revision: receipt.revision }], line_id: lineId || null,
        user_question: question.trim() }, crypto.randomUUID());
      setDraft(value); setText(value.text); setParams({ id: value.id, receipt: receipt.id });
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!draft) return;
    setBusy(true); setError(null); setNotice('');
    try { const value = await api.editDraft(draft.id, { expected_revision: draft.revision, text }); setDraft(value); setText(value.text); setNotice('Изменения сохранены.'); }
    catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  async function copy() {
    if (!draft) return;
    setError(null); setNotice('');
    let current: DraftView;
    try { current = await api.draft(draft.id); setDraft(current); }
    catch (cause) { setError(cause); return; }
    if (current.stale && !staleApproved) { setNotice('Исходная квитанция или знания изменились. Проверьте факты и подтвердите копирование устаревшего черновика.'); return; }
    if (text !== current.text) { setNotice('Сначала сохраните изменения, затем копируйте актуальный текст.'); return; }
    try { await navigator.clipboard.writeText(current.text); setNotice('Текст скопирован. Обращение не отправлено.'); setStaleApproved(false); }
    catch { setNotice('Буфер обмена недоступен. Выделите текст и скопируйте вручную.'); }
  }
  return <section className="panel">
    <h2>Черновик обращения</h2><p className="notice">Текст можно сохранить и скопировать. Отправка обращения из приложения не выполняется.</p>
    <ErrorMessage error={error} />
    {!receiptId && !draftId && <p>Выберите подтверждённую квитанцию в <Link to="/history">истории</Link> или после сравнения.</p>}
    {receipt && <div className="notice-box"><h3>Факты для сверки</h3>
      {receipt.dataset_kind === 'synthetic' && <p className="badge">Синтетический пример</p>}
      <p>{receipt.bill_data.period ?? 'Период не указан'} · {receipt.bill_data.issuer_name ?? 'Организация не определена'} · ревизия {receipt.revision}</p>
      <p>Итого по документу: {receipt.bill_data.document_total_due ?? 'нет данных'} ₽</p>
      {receipt.bill_data.services.map((line) => <p key={line.line_id}>{line.raw_name}: {line.charge_amount ?? 'нет суммы'} ₽</p>)}
      {receipt.status !== 'confirmed' && <p className="review-warning">Создать черновик можно после подтверждения квитанции.</p>}
    </div>}
    {receipt && !draft && receipt.status === 'confirmed' && <form onSubmit={(event) => void create(event)}>
      <label htmlFor="draft-topic">Тема</label><select id="draft-topic" value={topic} onChange={(event) => setTopic(event.target.value)} required><option value="">Выберите тему</option>{catalog?.topics.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
      <label htmlFor="draft-line">Строка квитанции</label><select id="draft-line" value={lineId} onChange={(event) => setLineId(event.target.value)}><option value="">Без строки</option>{receipt.bill_data.services.map((line) => <option key={line.line_id} value={line.line_id}>{line.raw_name}</option>)}</select>
      <label htmlFor="draft-question">Ваш вопрос</label><textarea id="draft-question" rows={3} maxLength={2000} value={question} onChange={(event) => setQuestion(event.target.value)} />
      <button disabled={busy || !topic || !question.trim()}>Подготовить черновик</button>
    </form>}
    {draft && <article className="answer"><h3>Проверьте текст</h3>
      <p>Получатель: {draft.recipient?.label ?? 'не определён; выберите канал самостоятельно'}</p>
      {draft.actions.map((action) => <p key={action.id}>{action.label}</p>)}
      {draft.stale && <p className="review-warning">Черновик устарел: исходный документ или сведения изменились.</p>}
      <label htmlFor="draft-text">Текст черновика</label><textarea id="draft-text" rows={12} maxLength={5000} value={text} onChange={(event) => { setText(event.target.value); setStaleApproved(false); }} />
      <div className="actions"><button type="button" disabled={busy || !text.trim()} onClick={() => void save()}>Сохранить изменения</button><button type="button" disabled={busy} onClick={() => void copy()}>Копировать текст</button></div>
      {draft.stale && <label className="check"><input type="checkbox" checked={staleApproved} onChange={(event) => setStaleApproved(event.target.checked)} />Я проверил устаревшие факты перед копированием</label>}
      {notice && <p role="status">{notice}</p>}
    </article>}
  </section>;
}
