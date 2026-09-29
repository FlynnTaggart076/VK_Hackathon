import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import type { BillData } from '../api/types';
import { serviceLabels } from './labels';
import { availableServiceCodes, changeServiceCode, newServiceLine, serviceCatalog, unitChoices } from './serviceCatalog';

type Service = BillData['services'][number];
const water: Service = {
  line_id: '20000000-0000-4000-8000-000000000001', raw_name: 'Холодное В/С', service_code: 'cold_water', scope: 'individual',
  unit: 'm3', unit_label: null, quantity: '5.000000', tariff: '40.000000', charge_amount: '200.00',
  supplier_key: 'demo-provider', segment_key: null, calculation_kind: 'simple_product',
};
const line = (patch: Partial<Service>): Service => ({ ...water, line_id: crypto.randomUUID(), ...patch });

describe('service catalogue', () => {
  it('covers every service code of the contract with the same Russian label', () => {
    const schema = JSON.parse(readFileSync(new URL('../../../../contracts/engine/v1/BillData.schema.json', import.meta.url), 'utf8'));
    const codes: string[] = schema.$defs.ServiceLine.properties.service_code.enum;
    expect(serviceCatalog.map((item) => item.code).sort()).toEqual([...codes].sort());
    for (const item of serviceCatalog) expect(item.label).toBe(serviceLabels[item.code]);
  });
  it('gives every service a default area that it allows', () => {
    for (const item of serviceCatalog) {
      expect(item.scopes).toContain(item.default_scope);
      if (item.default_unit) expect(item.units).toContain(item.default_unit);
    }
  });
});

describe('«Вид услуги» is a list where each service can be used once', () => {
  const lines = [line({ service_code: 'electricity', unit: 'kwh' }), line({ service_code: 'cold_water' }), line({ service_code: 'other' })];
  it('marks a service used by another line as taken and names the row', () => {
    const choices = availableServiceCodes(lines, lines[1].line_id);
    expect(choices.find((item) => item.code === 'electricity')).toMatchObject({ takenBy: 1 });
    expect(choices.find((item) => item.code === 'cold_water')).toMatchObject({ takenBy: null });
    expect(choices.find((item) => item.code === 'hot_water')).toMatchObject({ takenBy: null });
  });
  it('keeps «Прочее» available even when other lines use it', () => {
    const choices = availableServiceCodes(lines, lines[0].line_id);
    expect(choices.find((item) => item.code === 'other')!.takenBy).toBeNull();
  });
  it('frees the code when the line is removed', () => {
    const rest = lines.filter((item) => item.service_code !== 'electricity');
    expect(availableServiceCodes(rest, rest[0].line_id).find((item) => item.code === 'electricity')!.takenBy).toBeNull();
  });
  it('leaves only «Прочее» when all real services are taken', () => {
    const all = serviceCatalog.filter((item) => item.code !== 'other').map((item) => line({ service_code: item.code, unit: item.default_unit }));
    const fresh = newServiceLine();
    const free = availableServiceCodes([...all, fresh], fresh.line_id).filter((item) => item.takenBy === null).map((item) => item.code);
    expect(free).toEqual(['other']);
  });
});

describe('changing the service brings the dependent fields with it', () => {
  it('reproduces the reported bug scenario: water line switched to electricity', () => {
    const result = changeServiceCode(water, 'electricity');
    expect(result.line).toMatchObject({ service_code: 'electricity', unit: 'kwh', scope: 'individual', quantity: null, tariff: null,
      charge_amount: '200.00', raw_name: 'Холодное В/С' });
    expect(result.notes.join(' ')).toContain('не подходит');
  });
  it('keeps volume and tariff when the unit still fits', () => {
    const result = changeServiceCode(water, 'drainage');
    expect(result.line).toMatchObject({ service_code: 'drainage', unit: 'm3', quantity: '5.000000', tariff: '40.000000' });
    expect(result.notes).toEqual([]);
  });
  it('fills the default unit and area for an unrecognised line', () => {
    const unknown = line({ service_code: 'other', scope: 'unspecified', unit: null, quantity: null, tariff: null });
    expect(changeServiceCode(unknown, 'heating').line).toMatchObject({ unit: 'gcal', scope: 'individual' });
  });
  it('keeps the common-property area and a known segment, drops an unknown segment', () => {
    expect(changeServiceCode(line({ service_code: 'cold_water', scope: 'common_property' }), 'drainage').line.scope).toBe('common_property');
    expect(changeServiceCode(line({ service_code: 'other', unit: 'kwh', segment_key: 'night' }), 'electricity').line.segment_key).toBe('night');
    expect(changeServiceCode(line({ segment_key: 'night' }), 'drainage').line.segment_key).toBeNull();
  });
  it('drops the unit caption unless the unit is «другая»', () => {
    const printed = line({ service_code: 'other', unit: 'other', unit_label: 'кв.м' });
    expect(changeServiceCode(printed, 'maintenance').line).toMatchObject({ unit: 'm2', unit_label: null });
  });
  it('never touches the printed name or the charge, and names a blank line after the service', () => {
    expect(changeServiceCode(line({ raw_name: '  ' }), 'waste').line.raw_name).toBe('Обращение с ТКО');
    expect(changeServiceCode(water, 'heating').line).toMatchObject({ raw_name: 'Холодное В/С', charge_amount: '200.00' });
  });
  it('restores the loaded values when the user goes back to the original service', () => {
    const changed = changeServiceCode(water, 'electricity').line;
    expect(changeServiceCode(changed, 'cold_water', water).line).toMatchObject({ unit: 'm3', quantity: '5.000000', tariff: '40.000000', scope: 'individual' });
  });
  it('offers the catalogue units plus a value already on the line', () => {
    expect(unitChoices('electricity', 'm3')).toEqual(['kwh', 'm3']);
    expect(unitChoices('electricity', 'kwh')).toEqual(['kwh']);
  });
});
