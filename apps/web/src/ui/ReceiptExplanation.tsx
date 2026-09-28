import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { ReceiptExplanation as Explanation, ReceiptView } from '../api/types';
import { ErrorMessage } from './errors';

function amount(value: string | null): string { return value === null ? 'Неизвестно' : `${value} ₽`; }

export function ReceiptExplanation() {
  const [params] = useSearchParams();
  const id = params.get('id');
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setReceipt(null); setExplanation(null); setError(null); setLoading(true);
    api.receipt(id, controller.signal).then(async (value) => {
      setReceipt(value);
      if (value.status === 'confirmed') setExplanation(await api.explanation(id, value.revision, controller.signal));
    }).catch((cause) => { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload]);
  return <section className="panel"><h2>Объяснение платёжки</h2>
    {!id && <p>Документ не выбран. <Link to="/upload">Загрузить платёжку</Link></p>}
    {loading && <p role="status">Получаем подтверждённую ревизию и объяснение…</p>}
    <ErrorMessage error={error} />
    {id && error !== null && <button type="button" onClick={() => setReload((value) => value + 1)}>Повторить</button>}
    {receipt && receipt.status !== 'confirmed' && <p role="status">Документ ещё не подтверждён. <Link to={`/review?id=${encodeURIComponent(receipt.id)}`}>Проверить данные</Link></p>}
    {receipt?.status === 'confirmed' && !explanation && !loading && !error && <p>Объяснение для текущей ревизии пока отсутствует.</p>}
    {explanation && <>
      <p className="badge">{receipt?.dataset_kind === 'synthetic' ? 'Синтетический пример' : 'Загруженный пользователем файл'} · ревизия {explanation.receipt_ref.revision}</p>
      <p>{explanation.summary}</p>
      <dl className="totals"><dt>Начислено за период</dt><dd>{amount(explanation.current_charges)}</dd>
        <dt>К оплате по документу</dt><dd>{amount(explanation.document_total_due)}</dd>
        <dt>Расчётный остаток</dt><dd>{amount(explanation.calculated_closing_balance)}</dd>
        <dt>Расчётный итог к оплате</dt><dd>{amount(explanation.calculated_total_due)}</dd>
        <dt>Разница, которую не удалось объяснить</dt><dd>{amount(explanation.unexplained_difference)}</dd></dl>
      <p>Сверка: {explanation.reconciliation_status === 'matched' ? 'совпадает' : explanation.reconciliation_status === 'mismatch' ? 'есть различие' : explanation.reconciliation_status === 'incomplete' ? 'неполные данные' : 'формула не поддерживается'}.</p>
      <h3>Строки</h3>
      {!explanation.lines.length && <p>Разбор отдельных строк пока не доступен.</p>}
      {explanation.lines.map((line) => <article className="notice-box" key={line.line_id}><h4>{line.title}</h4><p>{line.explanation}</p>
        {line.formula_text && <p>Формула сервера: {line.formula_text}</p>}
        <p>Рассчитано: {amount(line.calculated_amount)}; разница: {amount(line.difference)}.</p>
        {line.issues.map((issue, index) => <p key={`${issue.code}-${index}`} className="review-warning">{issue.message}</p>)}
      </article>)}
      {explanation.balance_components.length > 0 && <><h3>Состав остатка</h3><dl className="totals">{explanation.balance_components.map((item) => <div key={item.code}><dt>{item.label}</dt><dd>{amount(item.amount)}</dd></div>)}</dl></>}
      {explanation.reconciliation_checks.length > 0 && <><h3>Проверки</h3><ul>{explanation.reconciliation_checks.map((item, index) => <li key={index}>{item.field}: документ {amount(item.document_value)}, расчёт {amount(item.calculated_value)}, разница {amount(item.difference)} · {item.status}</li>)}</ul></>}
      {explanation.issues.length > 0 && <><h3>Ограничения и предупреждения</h3><ul>{explanation.issues.map((item, index) => <li key={`${item.code}-${index}`}>{item.message}</li>)}</ul></>}
      <h3>Источники</h3>
      {!explanation.sources.length && <p>Внешние источники для этого расчёта не указаны; цифры берутся из подтверждённой платёжки.</p>}
      {explanation.sources.map((source) => <p key={source.id}>{source.title} · проверено {source.verified_at}{source.is_synthetic && ' · синтетический источник'}{source.url && <a href={source.url} target="_blank" rel="noopener noreferrer"> Открыть источник</a>}</p>)}
      <div className="actions"><Link to={`/review?id=${encodeURIComponent(explanation.receipt_ref.id)}`}>Вернуться к документу</Link><Link to={`/assistant?receipt=${encodeURIComponent(explanation.receipt_ref.id)}`}>Вопрос по платёжке</Link><Link to={`/city-comparison?receipt=${encodeURIComponent(explanation.receipt_ref.id)}`}>Сравнить с городом</Link></div>
    </>}
  </section>;
}
