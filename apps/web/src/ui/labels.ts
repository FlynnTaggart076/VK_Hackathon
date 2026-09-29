// Russian labels for every machine value that can reach the screen.
// Records are typed by the generated API unions, so a new enum value in the
// contract fails `tsc` here until it gets a Russian label.
import type { BillData, FieldEvidence, Issue, Job, ReceiptView } from '../api/types';

type Service = BillData['services'][number];
export type ServiceCode = Service['service_code'];
export type Scope = Service['scope'];
export type Unit = NonNullable<Service['unit']>;

const FALLBACK = 'Не определено';

function pick<K extends string>(table: Record<K, string>, key: string | null | undefined, name: string): string {
  if (key !== null && key !== undefined && Object.prototype.hasOwnProperty.call(table, key)) return table[key as K];
  if (key !== null && key !== undefined && typeof console !== 'undefined') console.warn(`Нет русской подписи для ${name}: ${key}`);
  return FALLBACK;
}

export const serviceLabels: Record<ServiceCode, string> = {
  cold_water: 'Холодная вода', hot_water: 'Горячая вода', drainage: 'Водоотведение', electricity: 'Электроэнергия',
  heating: 'Отопление', maintenance: 'Содержание жилья', capital_repair: 'Капитальный ремонт',
  waste: 'Обращение с ТКО', other: 'Прочее',
};
export const scopeLabels: Record<Scope, string> = {
  individual: 'Индивидуальное потребление', common_property: 'Общедомовые нужды', unspecified: 'Не указана',
};
export const unitLabels: Record<Unit, string> = {
  m3: 'м³', kwh: 'кВт·ч', gcal: 'Гкал', m2: 'м²', month: 'мес.', person: 'чел.', other: 'другая',
};
export const receiptStatusLabels: Record<ReceiptView['status'], string> = {
  queued: 'В очереди', processing: 'Обрабатывается', needs_review: 'Нужна проверка',
  confirmed: 'Подтверждена', failed: 'Ошибка обработки',
};
export const extractionOutcomeLabels: Record<NonNullable<ReceiptView['extraction_outcome']>, string> = {
  recognized: 'Распознано, проверьте цифры', partial: 'Распознано частично', manual_required: 'Нужен ручной ввод',
};
export const severityLabels: Record<Issue['severity'], string> = { info: 'Справка', warning: 'Проверьте', error: 'Ошибка' };
export const evidenceSourceLabels: Record<FieldEvidence['source'], string> = {
  pdf_text: 'текст документа', ocr: 'распознано с изображения', manual: 'введено вручную', template_default: 'по шаблону',
};
export const datasetKindLabels: Record<ReceiptView['dataset_kind'] | 'public_reference', string> = {
  synthetic: 'Синтетический пример', user_provided: 'Ваш файл', public_reference: 'Публичный источник',
};
export const jobStateLabels: Record<Job['state'], string> = {
  queued: 'В очереди', running: 'Обработка выполняется', succeeded: 'Обработка завершена', failed: 'Ошибка обработки',
};
export const jobStageLabels: Record<string, string> = {
  extracting: 'Распознаём документ', dev_stub: 'Учебная обработка без распознавания',
};
export const reconciliationLabels: Record<'matched' | 'mismatch' | 'incomplete' | 'unsupported', string> = {
  matched: 'Совпадает', mismatch: 'Есть различие', incomplete: 'Неполные данные', unsupported: 'Формула не поддерживается',
};
export const lineMatchLabels: Record<'matched' | 'added' | 'removed' | 'ambiguous' | 'incompatible', string> = {
  matched: 'Сопоставлена', added: 'Новая строка', removed: 'Строки нет в новом документе',
  ambiguous: 'Сопоставление неоднозначно', incompatible: 'Несовместимая строка',
};
export const metricLabels: Record<'charge_amount' | 'tariff', string> = {
  charge_amount: 'начисление по услуге', tariff: 'тариф',
};
export const reconciliationFieldLabels: Record<string, string> = {
  document_current_charges: 'Сверка: начисления за период',
  document_closing_balance: 'Сверка: остаток по документу',
  document_total_due: 'Сверка: сумма к оплате',
};

export const serviceLabel = (code: string | null | undefined) => pick(serviceLabels, code, 'вида услуги');
export const scopeLabel = (value: string | null | undefined) => pick(scopeLabels, value, 'области');
export const unitLabel = (value: string | null | undefined) => (value ? pick(unitLabels, value, 'единицы') : '');
export const receiptStatusLabel = (value: string | null | undefined) => pick(receiptStatusLabels, value, 'статуса');
export const extractionOutcomeLabel = (value: string | null | undefined) => (value ? pick(extractionOutcomeLabels, value, 'результата распознавания') : 'Результат пока не готов');
export const severityLabel = (value: string | null | undefined) => pick(severityLabels, value, 'серьёзности');
export const evidenceSourceLabel = (value: string | null | undefined) => pick(evidenceSourceLabels, value, 'источника значения');
export const datasetKindLabel = (value: string | null | undefined) => pick(datasetKindLabels, value, 'происхождения данных');
export const jobStateLabel = (value: string | null | undefined) => pick(jobStateLabels, value, 'состояния задания');
export const jobStageLabel = (value: string | null | undefined) => (value ? (jobStageLabels[value] ?? 'Обработка документа') : '');
export const reconciliationLabel = (value: string | null | undefined) => pick(reconciliationLabels, value, 'статуса сверки');
export const lineMatchLabel = (value: string | null | undefined) => pick(lineMatchLabels, value, 'статуса сопоставления');
export const metricLabel = (value: string | null | undefined) => pick(metricLabels, value, 'показателя');
export const reconciliationFieldLabel = (value: string | null | undefined) =>
  value && Object.prototype.hasOwnProperty.call(reconciliationFieldLabels, value) ? reconciliationFieldLabels[value] : 'Итог документа';

/** Unit text as shown next to a number: the catalogue unit, or the printed label for «другая». */
export function unitText(unit: string | null | undefined, printed: string | null | undefined): string {
  if (unit === 'other' || !unit) return printed ?? '';
  return unitLabel(unit);
}

const months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];

/** «2026-08» → «август 2026». Anything else stays neutral. */
export function formatPeriod(period: string | null | undefined): string {
  const match = period ? /^(\d{4})-(0[1-9]|1[0-2])$/.exec(period) : null;
  return match ? `${months[Number(match[2]) - 1]} ${match[1]}` : 'Период не указан';
}

/**
 * Money is shown exactly as the server sends it («200.00 ₽»): the engine writes its own
 * explanations the same way, and the browser never computes or rounds money.
 */
export function formatMoney(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? 'Неизвестно' : `${value} ₽`;
}

function trimDecimal(value: string, minFraction: number): string {
  const match = /^(-?\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value;
  const fraction = (match[2] ?? '').replace(/0+$/, '').padEnd(minFraction, '0');
  return fraction ? `${match[1]}.${fraction}` : match[1];
}

/** Quantity for display: «5.000000» → «5», «5.250000» → «5.25». */
export function formatDecimal(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '' : trimDecimal(value, 0);
}

/** Tariff for display: «40.000000» → «40.00 ₽», «40.125000» → «40.125 ₽». */
export function formatTariff(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? 'Неизвестно' : `${trimDecimal(value, 2)} ₽`;
}

/** Russian plural: plural(1, ['замечание','замечания','замечаний']). */
export function plural(count: number, forms: [string, string, string]): string {
  const n = Math.abs(count) % 100;
  const last = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}
