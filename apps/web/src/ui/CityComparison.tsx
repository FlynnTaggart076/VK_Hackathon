import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import type { CityComparisonView, ReceiptSummary, ReceiptView, SyntheticCityComparisonView } from '../api/types';
import { ErrorMessage } from './errors';
import { formatMoney, metricLabel, serviceLabel, unitLabel, unitText } from './labels';

export function publishableCityResult(result: CityComparisonView | null): boolean {
  return !!result && result.provenance === 'confirmed_opted_in_real_receipts' && result.status === 'available' && result.sample_size !== null && result.sample_size >= 5 &&
    result.average !== null && result.median !== null && result.city !== null && result.period !== null;
}

export function publishablePreviewResult(result: SyntheticCityComparisonView | null): boolean {
  return !!result && result.provenance === 'synthetic_preview_cohort' && result.status === 'available' &&
    result.sample_size !== null && result.sample_size >= 5 && result.city !== null && result.city_label !== null &&
    result.period !== null && result.service_code !== null &&
    result.unit !== null && result.scope !== null && result.receipt_value !== null &&
    result.average !== null && result.median !== null && result.difference_from_average !== null &&
    result.difference_percent !== null && result.comparison !== null && result.explanation !== null;
}

export function comparablePreviewMonths(current: SyntheticCityComparisonView | null, older: SyntheticCityComparisonView | null): boolean {
  return publishablePreviewResult(current) && publishablePreviewResult(older) &&
    older?.period === previousMonth(current?.period ?? null) && current?.city === older?.city &&
    current?.service_code === older?.service_code && current?.scope === older?.scope &&
    current?.segment_key === older?.segment_key && current?.unit === older?.unit && current?.metric === older?.metric;
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
      <p>{result.city} · {result.period} · {serviceLabel(result.service_code)} · {metricLabel(result.metric)}{result.unit && ` · ${unitLabel(result.unit)}`}</p>
      <dl className="totals"><div><dt>Среднее</dt><dd>{formatMoney(result.average)}</dd></div><div><dt>Медиана</dt><dd>{formatMoney(result.median)}</dd></div><div><dt>Квитанций в выборке</dt><dd>{result.sample_size}</dd></div></dl>
      <p className="notice">Источник: подтверждённые реальные квитанции участников, которые дали отдельное согласие.</p>
    </> : <p role="status">{result.provenance !== 'confirmed_opted_in_real_receipts' ? 'Источник городской статистики не подтверждён. Числа скрыты.'
      : result.status === 'ambiguous_city' ? 'Город определён неоднозначно. Сравнение недоступно.'
      : result.status === 'ineligible' ? 'Эта квитанция не подходит для городской статистики.'
        : 'Для этого города, месяца и показателя пока недостаточно подтверждённых квитанций с согласием. Числа скрыты.'}</p>}
  </div>;
}

function PreviewResult({ title, result }: { title: string; result: SyntheticCityComparisonView | null }) {
  if (!result) return null;
  const publishable = publishablePreviewResult(result);
  const unit = result.metric === 'tariff' && result.unit ? `₽ за ${unitLabel(result.unit)}` : '₽';
  return <div className="notice-box">
    <h3>{title}</h3>
    <p className="badge">Синтетическая учебная выборка — не данные жителей Москвы/МО</p>
    {publishable ? <>
      <p>{result.city_label} · {result.period} · {serviceLabel(result.service_code)} · {metricLabel(result.metric)} · {unitLabel(result.unit)}</p>
      <dl className="totals"><div><dt>В вашей учебной квитанции</dt><dd>{result.receipt_value} {unit}</dd></div>
        <div><dt>Среднее в учебной выборке</dt><dd>{result.average} {unit}</dd></div>
        <div><dt>Медиана учебной выборки</dt><dd>{result.median} {unit}</dd></div>
        <div><dt>Отклонение от среднего</dt><dd>{result.difference_from_average} {unit} ({result.difference_percent}%)</dd></div>
        <div><dt>Учебных записей (искусственных)</dt><dd>{result.sample_size}</dd></div></dl>
      <p>{result.explanation}</p>
      <p className="notice">Источник: фиксированные учебные наблюдения. Значения не описывают начисления реальных жителей.</p>
    </> : <><p role="status">{result.status === 'ambiguous_city' ? 'Город не определён однозначно. Учебное сравнение недоступно.' : result.status === 'ineligible'
      ? 'Этот учебный образец или строка услуги не подходит для сравнения. Выберите городской образец с однозначной услугой.'
      : 'Для выбранного города, месяца и услуги нет сопоставимой учебной выборки. Числа скрыты.'}</p>
      <p><Link to="/upload">Открыть учебные образцы</Link></p></>}
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
  const [currentPreview, setCurrentPreview] = useState<SyntheticCityComparisonView | null>(null);
  const [olderPreview, setOlderPreview] = useState<SyntheticCityComparisonView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [errorStage, setErrorStage] = useState<'load' | 'compare'>('load');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const comparisonRequest = useRef<AbortController | null>(null);

  useEffect(() => () => comparisonRequest.current?.abort(), [id]);

  useEffect(() => {
    if (!id) { setReceipt(null); setHistory([]); setCurrentResult(null); setOlderResult(null); setCurrentPreview(null); setOlderPreview(null); return; }
    const controller = new AbortController();
    setReceipt(null); setOlderId(''); setHistory([]); setCurrentResult(null); setOlderResult(null);
    setCurrentPreview(null); setOlderPreview(null); setError(null); setErrorStage('load'); setLoading(true);
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
      } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) { setErrorStage('load'); setError(cause); } }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, [id, reload]);

  async function compare() {
    const syntheticPreview = PREVIEW_MODE && receipt?.dataset_kind === 'synthetic';
    if (!id || !serviceCode || receipt?.status !== 'confirmed' || (receipt.dataset_kind === 'synthetic' && !syntheticPreview) ||
      receipt.bill_data.services.filter((line) => line.service_code === serviceCode).length !== 1) return;
    comparisonRequest.current?.abort();
    const controller = new AbortController();
    comparisonRequest.current = controller;
    setBusy(true); setError(null); setCurrentResult(null); setOlderResult(null); setCurrentPreview(null); setOlderPreview(null);
    try {
      if (syntheticPreview) {
        const current = await api.previewCityComparison(id, serviceCode, metric, controller.signal);
        if (controller.signal.aborted) return;
        setCurrentPreview(current);
        if (olderId) {
          const older = await api.previewCityComparison(olderId, serviceCode, metric, controller.signal);
          if (!controller.signal.aborted) setOlderPreview(older);
        }
      } else {
        const current = await api.cityComparison(id, serviceCode, metric, controller.signal);
        if (controller.signal.aborted) return;
        setCurrentResult(current);
        if (olderId) {
          const older = await api.cityComparison(olderId, serviceCode, metric, controller.signal);
          if (!controller.signal.aborted) setOlderResult(older);
        }
      }
    } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) { setErrorStage('compare'); setError(cause); } }
    finally { if (comparisonRequest.current === controller) { comparisonRequest.current = null; setBusy(false); } }
  }

  const comparable = publishableCityResult(currentResult) && publishableCityResult(olderResult) &&
    currentResult?.city === olderResult?.city && currentResult?.unit === olderResult?.unit &&
    olderResult?.period === previousMonth(currentResult?.period ?? null);
  const previewComparable = comparablePreviewMonths(currentPreview, olderPreview);
  const syntheticPreview = PREVIEW_MODE && receipt?.dataset_kind === 'synthetic';
  const duplicateService = receipt?.bill_data.services.filter((line) => line.service_code === serviceCode).length !== 1;
  const expectedOlderPeriod = previousMonth(receipt?.bill_data.period ?? null);
  const serviceChoices = new Map<string, string[]>();
  for (const line of receipt?.bill_data.services ?? []) serviceChoices.set(line.service_code, [...(serviceChoices.get(line.service_code) ?? []), line.raw_name]);

  return <section className="panel">
    <h2>{PREVIEW_MODE ? 'Учебное сравнение квитанции' : 'Сравнение с городом'}</h2>
    {PREVIEW_MODE ? <p>Подтверждённая учебная квитанция сравнивается с фиксированной синтетической выборкой. Это не статистика жителей города и не проверка законности начислений.</p>
      : <p>Сравниваются средние подтверждённые начисления или тарифы по одной услуге за выбранный месяц. Это не проверка законности вашего счёта.</p>}
    {!id && <p>Выберите свою подтверждённую квитанцию в <Link to="/history">истории</Link>.</p>}
    {loading && <p role="status">Загружаем квитанцию и историю…</p>}
    <ErrorMessage error={error} />
    {id && error !== null && <button type="button" disabled={loading || busy} onClick={() => errorStage === 'compare' ? void compare() : setReload((value) => value + 1)}>
      {errorStage === 'compare' ? 'Повторить сравнение' : 'Повторить загрузку'}</button>}
    {receipt && <>
      {receipt.dataset_kind === 'synthetic' && <p className="badge">{syntheticPreview ? 'Синтетическая учебная выборка — не данные жителей Москвы/МО' : 'Синтетический пример не входит в статистику реальных квитанций.'}</p>}
      <p>Ваша квитанция: {receipt.bill_data.period ?? 'период неизвестен'} · {receipt.bill_data.issuer_name ?? 'организация не определена'}.</p>
      {receipt.status !== 'confirmed' ? <p>Сначала <Link to={`/review?id=${encodeURIComponent(receipt.id)}`}>подтвердите данные квитанции</Link>.</p>
        : receipt.dataset_kind === 'synthetic' && !PREVIEW_MODE ? <p role="status">Городское сравнение доступно только для реальных подтверждённых квитанций.</p>
          : PREVIEW_MODE && receipt.dataset_kind !== 'synthetic' ? <p role="status">Учебное сравнение доступно только для синтетических образцов. <Link to="/upload">Открыть образцы</Link>.</p>
            : <form onSubmit={(event) => { event.preventDefault(); void compare(); }}>
        <label htmlFor="city-service">Услуга</label><select id="city-service" value={serviceCode} disabled={busy} onChange={(event) => { setServiceCode(event.target.value); setCurrentResult(null); setOlderResult(null); setCurrentPreview(null); setOlderPreview(null); }}>
          <option value="">Выберите услугу</option>{[...serviceChoices].map(([code, names]) => <option key={code} value={code}>{names.length === 1 ? names[0] : `${names[0]} · ${names.length} строки`}</option>)}
        </select>
        <label htmlFor="city-metric">Показатель</label><select id="city-metric" value={metric} disabled={busy} onChange={(event) => { setMetric(event.target.value as CityComparisonView['metric']); setCurrentResult(null); setOlderResult(null); setCurrentPreview(null); setOlderPreview(null); }}>
          <option value="charge_amount">Начисление за услугу, ₽</option><option value="tariff">Тариф, ₽ за единицу</option>
        </select>
        <label htmlFor="city-older">{syntheticPreview ? 'Учебная квитанция прошлого месяца' : 'Квитанция прошлого месяца для динамики города'}</label><select id="city-older" value={olderId} disabled={busy} onChange={(event) => { setOlderId(event.target.value); setOlderResult(null); setOlderPreview(null); }}>
          <option value="">Только выбранный месяц</option>{history.filter((item) => item.period === expectedOlderPeriod && item.dataset_kind === receipt.dataset_kind).map((item) => <option key={item.id} value={item.id}>{item.period} · {item.issuer_name ?? 'без организации'}</option>)}
        </select>
        {serviceCode && duplicateService && <p className="review-warning">В квитанции несколько строк этой услуги или строка не найдена. Сравнение пока недоступно: нужны отдельные сегмент и единица.</p>}
        {!expectedOlderPeriod && <p className="review-warning">Период квитанции не определён; динамика по месяцам недоступна.</p>}
        <button type="submit" disabled={busy || !serviceCode || duplicateService}>{busy ? 'Сравниваем…' : syntheticPreview ? 'Показать учебное сравнение' : 'Показать статистику'}</button>
      </form>}
      {serviceCode && <div className="notice-box"><h3>В вашей квитанции</h3>{receipt.bill_data.services.filter((line) => line.service_code === serviceCode).map((line) =>
        <p key={line.line_id}>{line.raw_name}: {metric === 'tariff' ? (line.tariff === null ? 'тариф не указан' : `${line.tariff} ₽${unitText(line.unit, line.unit_label) ? ` за ${unitText(line.unit, line.unit_label)}` : ''}`)
          : (line.charge_amount === null ? 'начисление не указано' : formatMoney(line.charge_amount))}</p>)}</div>}
    </>}
    <CohortResult title="Выбранный месяц" result={currentResult} />
    <CohortResult title="Ранний месяц" result={olderResult} />
    {olderResult && !comparable && <p className="review-warning">Динамику города нельзя установить: для двух месяцев нужны сопоставимые город, услуга, единица и достаточная выборка в каждом месяце.</p>}
    {comparable && <p>Оба месяца имеют сопоставимые город, услугу и единицу. Смотрите средние и медианы за каждый месяц выше.</p>}
    <PreviewResult title="Выбранный учебный месяц" result={currentPreview} />
    {previewComparable && <PreviewResult title="Предыдущий учебный месяц" result={olderPreview} />}
    {olderPreview && !previewComparable && <p className="review-warning">Предыдущий учебный месяц не показан: для сравнения должны совпадать город, услуга, сегмент, единица и показатель, а месяцы идти подряд.</p>}
    {previewComparable && <p>Два учебных месяца сопоставимы по городу, услуге, сегменту и единице. Смотрите значения каждого месяца выше.</p>}
    <p><Link to="/history">К истории документов</Link></p>
  </section>;
}
