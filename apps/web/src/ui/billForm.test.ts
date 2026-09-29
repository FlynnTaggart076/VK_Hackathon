import { describe, expect, it } from 'vitest';
import { normalizeNumber } from './billForm';

describe('numbers typed or pasted by people', () => {
  it('accepts a comma, spaces between digit groups and the typographic minus', () => {
    expect(normalizeNumber('1 234,5', 'money')).toBe('1234.50');
    expect(normalizeNumber('1 234,50', 'money')).toBe('1234.50');
    expect(normalizeNumber('1 234', 'money')).toBe('1234.00');
    expect(normalizeNumber('−50,00', 'money')).toBe('-50.00');
    expect(normalizeNumber(' 40,5 ', 'decimal')).toBe('40.5');
  });
  it('turns a negative zero into zero so the server does not report a false mismatch', () => {
    expect(normalizeNumber('-0', 'money')).toBe('0.00');
    expect(normalizeNumber('-0,00', 'money')).toBe('0.00');
    expect(normalizeNumber('-0', 'decimal')).toBe('0');
  });
  it('leaves clearly invalid input as typed and treats blanks as unknown', () => {
    expect(normalizeNumber('12,345,67', 'money')).toBe('12.345.67');
    expect(normalizeNumber('   ', 'money')).toBeNull();
    expect(normalizeNumber(null, 'decimal')).toBeNull();
  });
});
