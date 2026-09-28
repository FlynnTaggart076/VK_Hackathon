import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { CityComparisonView, ReceiptSummary, ReceiptView } from '../api/types';
import { ErrorMessage } from './errors';

export function publishableCityResult(result: CityComparisonView | null): boolean {
  return !!result && result.status === 'available' && result.sample_size !== null && result.sample_size >= 5 &&
    result.average !== null && result.median !== null && result.city !== null && result.period !== null;
}

export function previousMonth(period: string | null): string | null {
  if (!period || !/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) return null;
  const [year, month] = period.split('-').map(Number);
  return month === 1 ? `${year - 1}-12` : `${year}-${String(month - 1).padStart(2, '0')}`;
}

function CohortResult({ title, result }: { title: string; result: CityComparisonView | null }) {
  if (!result) return null;
  const publishable = publishableCityResult(result);
  return <div className="notice-box">
    <h3>{title}</h3>
    {publishable ? <>
      <p>{result.city} · {result.period} · {result.service_code} · {result.metric === 'tariff' ? 'тариф' : 'начисление по услуге'}{result.unit && ` · ${result.unit}`}</p>
      <dl className="totals"><div><dt>Среднее</dt><dd>{result.average} ₽</dd></div><div><dt>Медиана</dt><dd>{result.median} ₽</dd></div><div><dt>Квитанций в выборке</dt><dd>{result.sample_size}</dd></div></dl>
      <p className="notice">Источник: подтверждённые реальные квитанции участников, которые дали отдельное согласие.</p>
    </> : <p role="status">{result.status === 'ambiguous_city' ? 'Город определён неоднозначно. Сравнение недоступно.'
      : result.status === 'ineligible' ? 'Эта квитанция не подходит для городской статистики.'
        : 'Для этого города, месяца и показателя пока недостаточно подтверждённых квитанций с согласием. Числа скрыты.'}</p>}
  </div>;
}

export function CityComparison() {
  const [params] = useSearchParams();
  const id = params.get('receipt');
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [history, setHistory] = useState<ReceiptSummary[]>([]);
  const [serviceCode, setServiceCode] = useState('');
  const [metric, setMetric] = useState<CityComparisonView['metric']>('charge_amount');
  const [olderId, setOlderId] = useState('');
  const [currentResult, setCurrentResult] = useState<CityComparisonView | null>(null);
  const [olderResult, setOlderResult] = useState<CityComparisonView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setReceipt(null); setOlderId(''); setHistory([]); setCurrentResult(null); setOlderResult(null); setError(null); setLoading(true);
    async function load() {
      try {
        const current = await api.receipt(id!, controller.signal);
        if (controller.signal.aborted) return;
        setReceipt(current);
        setServiceCode(current.bill_data.services[0]?.service_code ?? '');
        const all: ReceiptSummary[] = [];
        let cursor: string | null = null;
        do {
          const page = await api.receipts(cursor, 50, controller.signal);
          all.push(...page.items);
          cursor = page.next_cursor;
        } while (cursor && all.length < 500);
        if (!controller.signal.aborted) setHistory(all.filter((item) => item.status === 'confirmed' && item.id !== id));
      } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, [id, reload]);

  async function compare() {
    if (!id || !serviceCode || receipt?.status !== 'confirmed' || receipt.dataset_kind === 'synthetic' ||
      receipt.bill_data.services.filter((line) => line.service_code === serviceCode).length !== 1) return;
    setBusy(true); setError(null); setCurrentResult(null); setOlderResult(null);
    try {
      const current = await api.cityComparison(id, serviceCode, metric);
      setCurrentResult(current);
      if (olderId) setOlderResult(await api.cityComparison(olderId, serviceCode, metric));
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  const comparable = publishableCityResult(currentResult) && publishableCityResult(olderResult) &&
    currentResult?.city === olderResult?.city && currentResult?.unit === olderResult?.unit &&
    olderResult?.period === previousMonth(currentResult?.period ?? null);
  const duplicateService = receipt?.bill_data.services.filter((line) => line.service_code === serviceCode).length !== 1;
  const expectedOlderPeriod = previousMonth(receipt?.bill_data.period ?? null);
  const serviceChoices = new Map<string, string[]>();
  for (const line of receipt?.bill_data.services ?? []) serviceChoices.set(line.service_code, [...(serviceChoices.get(line.service_code) ?? []), line.raw_name]);

  return <section className="panel">
    <h2>Сравнение с городом</h2>
    <p>Сравниваются средние подтверждённые начисления или тарифы по одной услуге за выбранный месяц. Это не проверка законности вашего счёта.</p>
    {!id && <p>Выберите свою подтверждённую квитанцию в <Link to="/history">истории</Link>.</p>}
    {loading && <p role="status">Загружаем квитанцию и историю…</p>}
    <ErrorMessage error={error} />
    {id && error !== null && <button type="button" disabled={loading || busy} onClick={() => setReload((value) => value + 1)}>Повторить загрузку</button>}
    {receipt && <>
      {receipt.dataset_kind === 'synthetic' && <p className="badge">Синтетический пример не входит в статистику реальных квитанций.</p>}
      <p>Ваша квитанция: {receipt.bill_data.period ?? 'период неизвестен'} · {receipt.bill_data.issuer_name ?? 'организация не определена'}.</p>
      {receipt.status !== 'confirmed' ? <p>Сначала <Link to={`/review?id=${encodeURIComponent(receipt.id)}`}>подтвердите данные квитанции</Link>.</p>
        : receipt.dataset_kind === 'synthetic' ? <p role="status">Городское сравнение доступно только для реальных подтверждённых квитанций.</p> : <form onSubmit={(event) => { event.preventDefault(); void compare(); }}>
        <label htmlFor="city-service">Услуга</label><select id="city-service" value={serviceCode} onChange={(event) => { setServiceCode(event.target.value); setCurrentResult(null); setOlderResult(null); }}>
          <option value="">Выберите услугу</option>{[...serviceChoices].map(([code, names]) => <option key={code} value={code}>{names.length === 1 ? names[0] : `${names[0]} · ${names.length} строки`}</option>)}
        </select>
        <label htmlFor="city-metric">Показатель</label><select id="city-metric" value={metric} onChange={(event) => { setMetric(event.target.value as CityComparisonView['metric']); setCurrentResult(null); setOlderResult(null); }}>
          <option value="charge_amount">Начисление за услугу, ₽</option><option value="tariff">Тариф, ₽ за единицу</option>
        </select>
        <label htmlFor="city-older">Квитанция прошлого месяца для динамики города</label><select id="city-older" value={olderId} onChange={(event) => { setOlderId(event.target.value); setOlderResult(null); }}>
          <option value="">Только выбранный месяц</option>{history.filter((item) => item.period === expectedOlderPeriod).map((item) => <option key={item.id} value={item.id}>{item.period} · {item.issuer_name ?? 'без организации'}</option>)}
        </select>
        {serviceCode && duplicateService && <p className="review-warning">В квитанции несколько строк этой услуги или строка не найдена. Сравнение с городской выборкой пока недоступно: нужны отдельные сегмент и единица.</p>}
        {!expectedOlderPeriod && <p className="review-warning">Период квитанции не определён; динамика по месяцам недоступна.</p>}
        <button type="submit" disabled={busy || !serviceCode || duplicateService}>{busy ? 'Сравниваем…' : 'Показать статистику'}</button>
      </form>}
      {serviceCode && <div className="notice-box"><h3>В вашей квитанции</h3>{receipt.bill_data.services.filter((line) => line.service_code === serviceCode).map((line) =>
        <p key={line.line_id}>{line.raw_name}: {metric === 'tariff' ? (line.tariff === null ? 'тариф не указан' : `${line.tariff} ₽${line.unit_label ? ` за ${line.unit_label}` : ''}`)
          : (line.charge_amount === null ? 'начисление не указано' : `${line.charge_amount} ₽`)}</p>)}</div>}
    </>}
    <CohortResult title="Выбранный месяц" result={currentResult} />
    <CohortResult title="Ранний месяц" result={olderResult} />
    {olderResult && !comparable && <p className="review-warning">Динамику города нельзя установить: для двух месяцев нужны сопоставимые город, услуга, единица и достаточная выборка в каждом месяце.</p>}
    {comparable && <p>Оба месяца имеют сопоставимые город, услугу и единицу. Смотрите средние и медианы за каждый месяц выше.</p>}
    <p><Link to="/history">К истории документов</Link></p>
  </section>;
}
