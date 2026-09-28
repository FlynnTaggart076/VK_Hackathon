import { describe, expect, it } from 'vitest';
import type { CityComparisonView } from '../api/types';
import { previousMonth, publishableCityResult } from './CityComparison';

const complete: CityComparisonView = {
  status: 'available', city: 'Москва', period: '2026-09', service_code: 'heating',
  unit: 'm2', metric: 'tariff', sample_size: 5, average: '10.00', median: '9.00',
  provenance: 'confirmed_opted_in_user_receipts',
};

describe('city aggregate privacy gate', () => {
  it('hides numeric results for small or incomplete cohorts even if server marks them available', () => {
    expect(publishableCityResult(complete)).toBe(true);
    expect(publishableCityResult({ ...complete, sample_size: 4 })).toBe(false);
    expect(publishableCityResult({ ...complete, average: null })).toBe(false);
    expect(publishableCityResult({ ...complete, city: null })).toBe(false);
    expect(publishableCityResult({ ...complete, status: 'insufficient_data' })).toBe(false);
  });
  it('allows a trend only for the immediate earlier month', () => {
    expect(previousMonth('2026-09')).toBe('2026-08');
    expect(previousMonth('2026-01')).toBe('2025-12');
    expect(previousMonth('2026-13')).toBeNull();
  });
});
