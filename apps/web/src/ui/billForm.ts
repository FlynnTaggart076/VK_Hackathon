import type { BillData } from '../api/types';

const money = /^-?(?:0|[1-9][0-9]{0,8})\.[0-9]{2}$/;
const decimal = /^-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$/;

/**
 * Accepts what people type or paste: spaces and non-breaking spaces between digit groups,
 * a comma as the decimal mark, the typographic minus. «-0.00» becomes «0.00» so that
 * the server does not report a false mismatch. Values that are still invalid are returned as typed.
 */
export function normalizeNumber(value: string | null, kind: 'money' | 'decimal'): string | null {
  if (value === null || !value.trim()) return null;
  let input = value.replace(/[\s  ]/g, '').replace(/−/g, '-').replace(/,/g, '.');
  if (/^-0(?:\.0*)?$/.test(input)) input = input.slice(1);
  if (kind === 'decimal') return input;
  if (/^-?(?:0|[1-9][0-9]{0,8})$/.test(input)) return `${input}.00`;
  if (/^-?(?:0|[1-9][0-9]{0,8})\.[0-9]$/.test(input)) return `${input}0`;
  return input;
}

export function normalizeBill(input: BillData): BillData {
  return {
    ...input,
    period: input.period?.trim() || null,
    issuer_name: input.issuer_name?.trim() || null,
    provider_id: input.provider_id?.trim() || null,
    account_number: input.account_number?.trim() || null,
    address_text: input.address_text?.trim() || null,
    services: input.services.map((line) => ({ ...line,
      raw_name: line.raw_name.trim(),
      unit_label: line.unit_label?.trim() || null,
      quantity: normalizeNumber(line.quantity, 'decimal'), tariff: normalizeNumber(line.tariff, 'decimal'),
      charge_amount: normalizeNumber(line.charge_amount, 'money'),
      supplier_key: line.supplier_key?.trim() || null, segment_key: line.segment_key?.trim() || null,
    })),
    adjustments: input.adjustments.map((item) => ({ ...item,
      label: item.label.trim(), amount: normalizeNumber(item.amount, 'money'),
      related_period: item.related_period?.trim() || null,
    })),
    settlement: { ...input.settlement,
      opening_balance: normalizeNumber(input.settlement.opening_balance, 'money'),
      payments_credited: normalizeNumber(input.settlement.payments_credited, 'money'),
      penalties: normalizeNumber(input.settlement.penalties, 'money'),
      other_account_changes: normalizeNumber(input.settlement.other_account_changes, 'money'),
      document_closing_balance: normalizeNumber(input.settlement.document_closing_balance, 'money'),
    },
    document_current_charges: normalizeNumber(input.document_current_charges, 'money'),
    document_total_due: normalizeNumber(input.document_total_due, 'money'),
  };
}

export function billErrors(bill: BillData): string[] {
  const result: string[] = [];
  if (!bill.period || !/^\d{4}-(?:0[1-9]|1[0-2])$/.test(bill.period)) result.push('Укажите период в формате ГГГГ-ММ.');
  if (!bill.services.length) result.push('Добавьте хотя бы одну строку начисления.');
  bill.services.forEach((line, index) => {
    if (!line.raw_name) result.push(`Строка ${index + 1}: нужно название.`);
    if (!line.charge_amount || !money.test(line.charge_amount)) result.push(`Строка ${index + 1}: укажите сумму в рублях, например 200.00.`);
    if (line.quantity !== null && !decimal.test(line.quantity)) result.push(`Строка ${index + 1}: проверьте объём.`);
    if (line.tariff !== null && !decimal.test(line.tariff)) result.push(`Строка ${index + 1}: проверьте тариф.`);
  });
  bill.adjustments.forEach((item, index) => {
    if (!item.label) result.push(`Перерасчёт ${index + 1}: нужно название.`);
    if (item.amount === null || !money.test(item.amount)) result.push(`Перерасчёт ${index + 1}: укажите сумму с двумя цифрами после точки.`);
    if (item.related_period && !/^\d{4}-(?:0[1-9]|1[0-2])$/.test(item.related_period)) result.push(`Перерасчёт ${index + 1}: проверьте период.`);
    if (item.service_line_id && !bill.services.some((line) => line.line_id === item.service_line_id)) result.push(`Перерасчёт ${index + 1}: связанная строка удалена.`);
  });
  const amounts = [bill.document_current_charges, bill.document_total_due,
    bill.settlement.opening_balance, bill.settlement.payments_credited, bill.settlement.penalties,
    bill.settlement.other_account_changes, bill.settlement.document_closing_balance];
  if (amounts.some((value) => value !== null && !money.test(value))) result.push('Проверьте денежные поля: нужны две цифры после точки.');
  if (bill.settlement.payments_credited?.startsWith('-')) result.push('Учтённые оплаты не могут быть отрицательными.');
  return result;
}
