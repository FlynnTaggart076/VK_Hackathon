// Interface mirror of packages/housing_engine/src/housing_engine/service_catalog.py.
// The JSON is kept identical to the Python catalogue by tests on both sides.
import type { BillData } from '../api/types';
import raw from './serviceCatalog.json';
import { serviceLabels, unitLabels, type Scope, type ServiceCode, type Unit } from './labels';

export type Service = BillData['services'][number];
export interface ServiceSpec {
  code: ServiceCode; label: string; units: Unit[]; default_unit: Unit | null;
  scopes: Scope[]; default_scope: Scope; segments: { key: string; label: string }[];
}

export const serviceCatalog = raw.services as unknown as ServiceSpec[];
export const serviceSpec = (code: ServiceCode): ServiceSpec => serviceCatalog.find((item) => item.code === code)!;

export interface CodeChoice { code: ServiceCode; label: string; takenBy: number | null }

/**
 * Codes offered in the «Вид услуги» list of one line. A code already used by another
 * line is unavailable (takenBy = its 1-based row number); «Прочее» is always available.
 */
export function availableServiceCodes(lines: Service[], currentLineId: string): CodeChoice[] {
  return serviceCatalog.map((spec) => {
    const index = spec.code === 'other' ? -1
      : lines.findIndex((line) => line.line_id !== currentLineId && line.service_code === spec.code);
    return { code: spec.code, label: spec.label, takenBy: index === -1 ? null : index + 1 };
  });
}

/** Units the line's «Единица» list should offer: the catalogue units plus the value already on the line. */
export function unitChoices(code: ServiceCode, current: Unit | null): Unit[] {
  const units = serviceSpec(code).units;
  return current && !units.includes(current) ? [...units, current] : units;
}

export interface ServiceChange { line: Service; notes: string[] }

/**
 * Switches the line to another service and brings the dependent fields with it.
 * The printed name and the charge are the document's own text and never change.
 * `original` is the line as loaded from the server: going back to its service restores it.
 */
export function changeServiceCode(line: Service, code: ServiceCode, original?: Service): ServiceChange {
  if (line.service_code === code) return { line, notes: [] };
  const spec = serviceSpec(code);
  if (original && original.service_code === code) {
    return { line: { ...line, service_code: code, scope: original.scope, unit: original.unit, unit_label: original.unit_label,
      quantity: original.quantity, tariff: original.tariff, segment_key: original.segment_key }, notes: [] };
  }
  const notes: string[] = [];
  let unit = line.unit;
  let volumeReset = false;
  if (unit === null || !spec.units.includes(unit)) {
    const next = spec.default_unit;
    if (unit !== null && unit !== 'other') {
      notes.push(`Единица «${unitLabels[unit]}» не подходит для услуги «${spec.label}».`);
      volumeReset = true;
    } else if (unit === 'other' && next !== null) {
      notes.push(`Единица заменена на «${unitLabels[next]}» — проверьте по квитанции.`);
    }
    unit = next;
  }
  const scope = spec.scopes.includes(line.scope) && !(code !== 'other' && line.scope === 'unspecified') ? line.scope : spec.default_scope;
  const segment = spec.segments.some((item) => item.key === line.segment_key) ? line.segment_key : null;
  const quantity = volumeReset ? null : line.quantity;
  const tariff = volumeReset ? null : line.tariff;
  if (volumeReset && (line.quantity !== null || line.tariff !== null)) notes.push('Объём и тариф сброшены — введите их по квитанции.');
  return { line: { ...line, service_code: code, unit, unit_label: unit === 'other' ? line.unit_label : null,
    scope, segment_key: segment, quantity, tariff,
    raw_name: line.raw_name.trim() || (code === 'other' ? '' : serviceLabels[code]) }, notes };
}

/** A line added by hand starts as «Прочее»: the user picks the service in the list. */
export function newServiceLine(): Service {
  return { line_id: crypto.randomUUID(), raw_name: '', service_code: 'other', scope: 'unspecified', unit: null,
    unit_label: null, quantity: null, tariff: null, charge_amount: null, supplier_key: null, segment_key: null,
    calculation_kind: 'document_amount' };
}
