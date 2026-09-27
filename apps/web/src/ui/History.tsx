import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { ReceiptSummary } from '../api/types';
import { ErrorMessage } from './errors';

export function History() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ReceiptSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  async function load(page: string | null) {
    setBusy(true); setError(null);
    try {
      const result = await api.receipts(page, 10);
      setItems(result.items); setCursor(page); setNextCursor(result.next_cursor);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(null); }, []);
  async function remove(id: string) {
    setBusy(true); setError(null);
    try { await api.deleteReceipt(id); setConfirmId(null); await load(cursor); }
    catch (cause) { setError(cause); setBusy(false); }
  }
  async function downloadSource(item: ReceiptSummary) {
    setError(null);
    try {
      const blob = await api.source(item.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `receipt-${item.period ?? 'source'}`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) { setError(cause); }
  }
  async function resume(item: ReceiptSummary) {
    setError(null);
    try {
      const receipt = await api.receipt(item.id);
      if (!receipt.job?.id) throw new Error('Задание для документа не найдено.');
      navigate(`/processing?job=${encodeURIComponent(receipt.job.id)}`);
    } catch (cause) { setError(cause); }
  }
  return <section className="panel">
    <h2>История документов</h2>
    <p>В истории доступны ваши документы. Сравнить можно только две подтверждённые квитанции.</p>
    <div className="actions"><Link to="/comparison">Сравнить квитанции</Link><Link to="/upload">Загрузить документ</Link></div>
    <ErrorMessage error={error} />
    {error !== null && <button type="button" disabled={busy} onClick={() => void load(cursor)}>Повторить загрузку истории</button>}
    {busy && <p role="status">Загружаем историю…</p>}
    {!busy && !error && items.length === 0 && <p>Документов пока нет.</p>}
    <ul className="history-list">{items.map((item) => <li key={item.id} className="notice-box">
      <strong>{item.period ?? 'Период не указан'} · {item.issuer_name ?? 'Организация не определена'}</strong>
      <p>{item.status === 'confirmed' ? 'Подтверждена' : item.status === 'needs_review' ? 'Требует проверки' : item.status === 'queued' || item.status === 'processing' ? 'Обрабатывается' : 'Ошибка обработки'} · ревизия {item.revision}</p>
      {item.dataset_kind === 'synthetic' && <p className="badge">Синтетический пример</p>}
      {item.document_total_due !== null && <p>Итого по документу: {item.document_total_due} ₽</p>}
      <p>{item.source_available ? 'Исходный файл доступен' : 'Исходный файл недоступен; извлечённые данные сохранены'}</p>
      <div className="actions"><Link to={`/review?id=${encodeURIComponent(item.id)}`}>Открыть</Link>{item.status === 'queued' || item.status === 'processing' ? <button type="button" onClick={() => void resume(item)}>Продолжить обработку</button> : null}{item.source_available && <button type="button" onClick={() => void downloadSource(item)}>Исходный файл</button>}<button type="button" onClick={() => setConfirmId(item.id)}>Удалить</button></div>
      {confirmId === item.id && <div className="notice-box" role="group" aria-label="Подтверждение удаления"><p>Удалить этот документ и связанные данные?</p><div className="actions"><button type="button" disabled={busy} onClick={() => void remove(item.id)}>Да, удалить</button><button type="button" onClick={() => setConfirmId(null)}>Отмена</button></div></div>}
    </li>)}</ul>
    {nextCursor && <button type="button" disabled={busy} onClick={() => void load(nextCursor)}>Следующая страница</button>}
    {cursor && <button type="button" disabled={busy} onClick={() => void load(null)}>К началу</button>}
  </section>;
}
