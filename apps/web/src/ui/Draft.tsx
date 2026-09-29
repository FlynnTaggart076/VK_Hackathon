import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Catalog, DraftView, ReceiptView } from '../api/types';
import { ErrorMessage } from './errors';
import { ActionList } from './ActionList';
import { datasetKindLabel, formatMoney } from './labels';

export function Draft({ catalog }: { catalog: Catalog | null }) {
  const [params, setParams] = useSearchParams();
  const receiptId = params.get('receipt');
  const draftId = params.get('id');
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [draft, setDraft] = useState<DraftView | null>(null);
  const [text, setText] = useState('');
  const [topic, setTopic] = useState(params.get('topic') ?? '');
  const [lineId, setLineId] = useState('');
  const [question, setQuestion] = useState('');
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
    event.preventDefault(); if ((receipt && receipt.status !== 'confirmed') || !topic) return;
    setBusy(true); setError(null); setNotice('');
    try {
      const value = await api.createDraft({ topic_id: topic, organization_id: null,
        receipt_refs: receipt ? [{ id: receipt.id, revision: receipt.revision }] : [], line_id: receipt ? lineId || null : null,
        user_question: question.trim() }, crypto.randomUUID());
      setDraft(value); setText(value.text); setParams(receipt ? { id: value.id, receipt: receipt.id } : { id: value.id });
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
    {!receiptId && !draftId && <p>Черновик можно подготовить без квитанции или по подтверждённой квитанции из <Link to="/history">истории</Link>.</p>}
    {receipt && <div className="notice-box"><h3>Факты для сверки</h3>
      {receipt.dataset_kind === 'synthetic' && <p className="badge">{datasetKindLabel(receipt.dataset_kind)}</p>}
      <p>{receipt.bill_data.period ?? 'Период не указан'} · {receipt.bill_data.issuer_name ?? 'Организация не определена'} · версия {receipt.revision}</p>
      <p>Итого по документу: {receipt.bill_data.document_total_due === null ? 'нет данных' : formatMoney(receipt.bill_data.document_total_due)}</p>
      {receipt.bill_data.services.map((line) => <p key={line.line_id}>{line.raw_name}: {line.charge_amount === null ? 'нет суммы' : formatMoney(line.charge_amount)}</p>)}
      {receipt.status !== 'confirmed' && <p className="review-warning">Создать черновик можно после подтверждения квитанции.</p>}
    </div>}
    {!draft && !draftId && (!receiptId || receipt?.status === 'confirmed') && <form onSubmit={(event) => void create(event)}>
      {!catalog?.topics.length && <p className="notice">Каталог тем пока не загружен. Обновите страницу позднее.</p>}
      <label htmlFor="draft-topic">Тема</label><select id="draft-topic" value={topic} onChange={(event) => setTopic(event.target.value)} required><option value="">Выберите тему</option>{catalog?.topics.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
      {receipt && <><label htmlFor="draft-line">Строка квитанции</label><select id="draft-line" value={lineId} onChange={(event) => setLineId(event.target.value)}><option value="">Без строки</option>{receipt.bill_data.services.map((line) => <option key={line.line_id} value={line.line_id}>{line.raw_name}</option>)}</select></>}
      <label htmlFor="draft-question">Ваш вопрос</label><textarea id="draft-question" rows={3} maxLength={2000} value={question} placeholder="Например: прошу пояснить начисление за горячую воду" onChange={(event) => setQuestion(event.target.value)} />
      <button disabled={busy || !topic || (!receipt && !question.trim())}>Подготовить черновик</button>
    </form>}
    {draft && <article className="answer"><h3>Проверьте текст</h3>
      <p>Получатель: {draft.recipient?.label ?? 'не определён; выберите канал самостоятельно'}</p>
      <ActionList actions={draft.actions} />
      {draft.stale && <p className="review-warning">Черновик устарел: исходный документ или сведения изменились.</p>}
      <label htmlFor="draft-text">Текст черновика</label><textarea id="draft-text" rows={12} maxLength={5000} value={text} onChange={(event) => { setText(event.target.value); setStaleApproved(false); }} />
      <div className="actions"><button type="button" disabled={busy || !text.trim()} onClick={() => void save()}>Сохранить изменения</button><button type="button" disabled={busy} onClick={() => void copy()}>Копировать текст</button></div>
      {draft.stale && <label className="check"><input type="checkbox" checked={staleApproved} onChange={(event) => setStaleApproved(event.target.checked)} />Я проверил устаревшие факты перед копированием</label>}
      {notice && <p role="status">{notice}</p>}
    </article>}
  </section>;
}
