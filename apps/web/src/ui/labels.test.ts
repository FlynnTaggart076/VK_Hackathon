import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import {
  datasetKindLabels, evidenceSourceLabels, extractionOutcomeLabels, formatDecimal, formatMoney, formatPeriod, formatTariff,
  jobStateLabels, plural, receiptStatusLabels, scopeLabels, serviceLabel, serviceLabels, severityLabels, unitLabels, unitText,
} from './labels';

const schema = (name: string) => JSON.parse(readFileSync(new URL(`../../../../contracts/engine/v1/${name}.schema.json`, import.meta.url), 'utf8')) as
  { properties?: Record<string, { enum?: string[]; anyOf?: { enum?: string[] }[] }>; $defs?: Record<string, { properties: Record<string, { enum?: string[]; anyOf?: { enum?: string[] }[] }> }> };
const openapi = readFileSync(new URL('../../../../contracts/http/openapi.yaml', import.meta.url), 'utf8');
const enumOf = (field: { enum?: string[]; anyOf?: { enum?: string[] }[] } | undefined) => field?.enum ?? field?.anyOf?.find((item) => item.enum)?.enum ?? [];

describe('Russian labels cover every contract enum', () => {
  const service = schema('BillData').$defs!.ServiceLine.properties;
  it('service line enums', () => {
    expect(Object.keys(serviceLabels).sort()).toEqual([...enumOf(service.service_code)].sort());
    expect(Object.keys(scopeLabels).sort()).toEqual([...enumOf(service.scope)].sort());
    expect(Object.keys(unitLabels).sort()).toEqual([...enumOf(service.unit)].sort());
  });
  it('issue severity and evidence source', () => {
    expect(Object.keys(severityLabels).sort()).toEqual([...enumOf(schema('Issue').properties!.severity)].sort());
    expect(Object.keys(evidenceSourceLabels).sort()).toEqual([...enumOf(schema('FieldEvidence').properties!.source)].sort());
  });
  it('receipt and job states from OpenAPI', () => {
    const statuses = /enum: \[([^\]]*needs_review[^\]]*)\]/.exec(openapi)![1].split(',').map((item) => item.trim());
    expect(Object.keys(receiptStatusLabels).sort()).toEqual([...statuses].sort());
    const states = /enum: \[([^\]]*succeeded[^\]]*)\]/.exec(openapi)![1].split(',').map((item) => item.trim());
    expect(Object.keys(jobStateLabels).sort()).toEqual([...states].sort());
    expect(Object.keys(extractionOutcomeLabels).sort()).toEqual(['manual_required', 'partial', 'recognized']);
    expect(Object.keys(datasetKindLabels).sort()).toEqual(['public_reference', 'synthetic', 'user_provided']);
  });
  it('every label is Russian text without Latin words', () => {
    const all = [serviceLabels, scopeLabels, unitLabels, receiptStatusLabels, severityLabels, evidenceSourceLabels, jobStateLabels,
      extractionOutcomeLabels, datasetKindLabels].flatMap((table) => Object.values(table));
    for (const text of all) expect(text).not.toMatch(/[A-Za-z]{2,}/);
  });
});

describe('display helpers never show raw codes', () => {
  it('unknown values get neutral Russian text', () => {
    expect(serviceLabel('gas')).toBe('Не определено');
    expect(serviceLabel(null)).toBe('Не определено');
    expect(unitText('other', 'кв.м')).toBe('кв.м');
    expect(unitText('m3', null)).toBe('м³');
  });
  it('formats money, decimals and periods without arithmetic', () => {
    expect(formatMoney('200.00')).toBe('200.00 ₽');
    expect(formatMoney('-50.00')).toBe('-50.00 ₽');
    expect(formatMoney(null)).toBe('Неизвестно');
    expect(formatDecimal('5.000000')).toBe('5');
    expect(formatDecimal('5.250000')).toBe('5.25');
    expect(formatTariff('40.000000')).toBe('40.00 ₽');
    expect(formatTariff('40.125000')).toBe('40.125 ₽');
    expect(formatTariff(null)).toBe('Неизвестно');
    expect(formatPeriod('2026-08')).toBe('август 2026');
    expect(formatPeriod('bad')).toBe('Период не указан');
  });
  it('declines Russian plurals', () => {
    const forms: [string, string, string] = ['замечание', 'замечания', 'замечаний'];
    expect([1, 2, 5, 11, 21, 22, 25].map((n) => plural(n, forms))).toEqual([
      'замечание', 'замечания', 'замечаний', 'замечаний', 'замечание', 'замечания', 'замечаний']);
  });
});
