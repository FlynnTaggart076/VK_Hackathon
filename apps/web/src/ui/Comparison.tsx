import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { ComparisonView, ReceiptSummary } from '../api/types';
import { ErrorMessage } from './errors';
import { ActionList } from './ActionList';
import { datasetKindLabel, formatMoney, lineMatchLabel } from './labels';

export function Comparison() {
  const [items, setItems] = useState<ReceiptSummary[]>([]);
  const [left, setLeft] = useState('');
  const [right, setRight] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [result, setResult] = useState<ComparisonView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const all: ReceiptSummary[] = [];
        let cursor: string | null = null;
        do {
          const page = await api.receipts(cursor, 50);
          all.push(...page.items);
          cursor = page.next_cursor;
        } while (cursor && all.length < 500);
        if (active) setItems(all.filter((item) => item.status === 'confirmed'));
      } catch (cause) { if (active) setError(cause); }
    }
    void load(); return () => { active = false; };
  }, []);
  async function compare(ack = acknowledged) {
    setBusy(true); setError(null); setResult(null);
    const older = items.find((item) => item.id === left);
    const newer = items.find((item) => item.id === right);
    if (!older || !newer || older.id === newer.id) { setError(new Error('Выберите две разные подтверждённые квитанции.')); setBusy(false); return; }
    try { setResult(await api.compare({ left: { id: older.id, revision: older.revision }, right: { id: newer.id, revision: newer.revision }, identity_acknowledged: ack })); }
    catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  const label = (item: ReceiptSummary) => `${item.period ?? 'без периода'} · ${item.issuer_name ?? 'без организации'} · версия ${item.revision}`;
  return <section className="panel">
    <h2>Сравнение квитанций</h2>
    <p>Денежные разницы и причины возвращает сервер. Проверьте документы перед выводом.</p>
    {items.length < 2 && <p className="notice">Для сравнения нужны две подтверждённые квитанции. <Link to="/history">Открыть историю</Link>.</p>}
    <form onSubmit={(event) => { event.preventDefault(); void compare(); }}>
      <label htmlFor="compare-left">Ранний документ</label><select id="compare-left" value={left} onChange={(event) => { setLeft(event.target.value); setResult(null); setAcknowledged(false); }}><option value="">Выберите</option>{items.map((item) => <option key={item.id} value={item.id}>{label(item)}</option>)}</select>
      <label htmlFor="compare-right">Поздний документ</label><select id="compare-right" value={right} onChange={(event) => { setRight(event.target.value); setResult(null); setAcknowledged(false); }}><option value="">Выберите</option>{items.map((item) => <option key={item.id} value={item.id}>{label(item)}</option>)}</select>
      <button disabled={busy || items.length < 2}>Сравнить</button>
    </form>
    <ErrorMessage error={error} />
    {result && <article aria-live="polite" className="answer">
      {result.dataset_kind === 'synthetic' && <p className="badge">{datasetKindLabel(result.dataset_kind)}</p>}
      <h3>{result.status === 'complete' ? 'Сравнение готово' : result.status === 'partial' ? 'Частичное сравнение' : 'Подтвердите совпадение документов'}</h3>
      <p>{result.older.period ?? 'Период не указан'} → {result.newer.period ?? 'Период не указан'}</p>
      {result.status === 'needs_identity_confirmation' ? <div className="notice-box"><p>Лицевой счёт или адрес не совпадает либо отсутствует. Итоговые разницы скрыты до вашего подтверждения.</p><label className="check"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />Я сверил исходные документы и подтверждаю, что их можно сравнить</label><button type="button" disabled={!acknowledged || busy} onClick={() => void compare(true)}>Продолжить сравнение</button></div> : <>
        <dl className="totals"><div><dt>Разница начислений</dt><dd>{result.delta_current_charges === null ? 'не определена' : formatMoney(result.delta_current_charges)}</dd></div><div><dt>Разница перерасчётов</dt><dd>{result.delta_adjustments === null ? 'не определена' : formatMoney(result.delta_adjustments)}</dd></div><div><dt>Разница к оплате</dt><dd>{result.delta_total_due === null ? 'не определена' : formatMoney(result.delta_total_due)}</dd></div></dl>
        {result.lines.map((line, index) => <div className="notice-box" key={`${line.older_line_id}-${line.newer_line_id}-${index}`}><h4>{line.label}</h4><p>{lineMatchLabel(line.match_status)}</p><p>{line.explanation}</p><dl className="totals"><div><dt>Разница строки</dt><dd>{line.delta === null ? 'не определена' : formatMoney(line.delta)}</dd></div><div><dt>Влияние объёма</dt><dd>{line.quantity_effect === null ? 'не определено' : formatMoney(line.quantity_effect)}</dd></div><div><dt>Влияние тарифа</dt><dd>{line.tariff_effect === null ? 'не определено' : formatMoney(line.tariff_effect)}</dd></div></dl></div>)}
      </>}
      {result.issues.map((issue, index) => <p className="review-warning" key={`${issue.code}-${index}`}>{issue.message}</p>)}
      <ActionList actions={result.actions} />
      <div className="actions"><Link to={`/draft?receipt=${encodeURIComponent(result.newer.id)}`}>Подготовить черновик</Link><Link to={`/assistant?receipt=${encodeURIComponent(result.newer.id)}`}>Задать вопрос по документу</Link></div>
    </article>}
  </section>;
}
