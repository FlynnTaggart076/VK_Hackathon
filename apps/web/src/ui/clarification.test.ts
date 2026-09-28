import { describe, expect, it } from 'vitest';
import type { Catalog } from '../api/types';
import { recognizedValue, selectedValue, serviceContext, suggestionsFor } from './clarification';

const catalog: Catalog = {
  topics: [{ id: 'supplier_contacts', label: 'Контакты поставщика' }],
  territories: [{ id: 'moscow', label: 'Москва' }], organizations: [],
  service_codes: [], units: [], document_kinds: [], demo_receipts: [],
};

describe('assistant clarification mapping', () => {
  it('accepts labels and IDs from backend or catalog without discarding free text', () => {
    const options = suggestionsFor('territory_id', catalog, [{ value: 'mo', label: 'Московская область' }]);
    expect(selectedValue('Москва', options)).toBe('moscow');
    expect(selectedValue('mo', options)).toBe('mo');
    expect(selectedValue('Новый город', options)).toBe('Новый город');
    expect(recognizedValue('Новый город', options)).toBeNull();
    expect(recognizedValue('МОСКВА', options)).toBe('moscow');
    expect(suggestionsFor('service_code', catalog, [])).toEqual([]);
  });

  it('maps a typed service to the strict contract and retains unknown service text', () => {
    expect(serviceContext('горячая вода')).toEqual({ code: 'hot_water', freeText: null });
    expect(serviceContext('Лифт')).toEqual({ code: 'other', freeText: 'Лифт' });
    expect(serviceContext('')).toEqual({ code: null, freeText: null });
  });
});
