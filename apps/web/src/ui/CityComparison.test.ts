import { describe, expect, it } from 'vitest';
import type { CityComparisonView, SyntheticCityComparisonView } from '../api/types';
import { comparablePreviewMonths, previousMonth, publishableCityResult, publishablePreviewResult } from './CityComparison';

const complete: CityComparisonView = {
  status: 'available', city: 'Москва', period: '2026-09', service_code: 'heating',
  unit: 'm2', metric: 'tariff', sample_size: 5, average: '10.00', median: '9.00',
  provenance: 'confirmed_opted_in_real_receipts',
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

const preview: SyntheticCityComparisonView = {
  status: 'available', city: 'moskva', city_label: 'Москва', period: '2026-09',
  service_code: 'cold_water', scope: 'individual', segment_key: null, unit: 'm3',
  metric: 'charge_amount', sample_size: 5, receipt_value: '270.00', average: '342.00',
  median: '315.00', difference_from_average: '-72.00', difference_percent: '-21.05',
  comparison: 'below', explanation: 'Это синтетическая учебная выборка.',
  provenance: 'synthetic_preview_cohort',
};

describe('separate synthetic preview gate', () => {
  it('publishes only complete synthetic results with at least five artificial entries', () => {
    expect(publishablePreviewResult(preview)).toBe(true);
    expect(publishableCityResult(preview as unknown as CityComparisonView)).toBe(false);
    expect(publishablePreviewResult({ ...preview, sample_size: 4 })).toBe(false);
    expect(publishablePreviewResult({ ...preview, status: 'ineligible', sample_size: null })).toBe(false);
    expect(publishablePreviewResult({ ...preview, receipt_value: null })).toBe(false);
    expect(publishablePreviewResult({ ...preview, provenance: 'confirmed_opted_in_real_receipts' } as unknown as SyntheticCityComparisonView)).toBe(false);
  });
  it('shows the preceding month only with identical city, service, scope, segment, unit and metric', () => {
    const older = { ...preview, period: '2026-08', receipt_value: '200.00', average: '256.00' };
    expect(comparablePreviewMonths(preview, older)).toBe(true);
    expect(comparablePreviewMonths(preview, { ...older, city: 'lyubertsy' })).toBe(false);
    expect(comparablePreviewMonths(preview, { ...older, scope: 'building' })).toBe(false);
    expect(comparablePreviewMonths(preview, { ...older, segment_key: 'night' })).toBe(false);
    expect(comparablePreviewMonths(preview, { ...older, unit: 'person' })).toBe(false);
    expect(comparablePreviewMonths(preview, { ...older, metric: 'tariff' })).toBe(false);
    expect(comparablePreviewMonths(preview, { ...older, period: '2026-07' })).toBe(false);
  });
});
