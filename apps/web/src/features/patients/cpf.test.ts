import { describe, expect, it } from 'vitest';

import { formatCpf, isValidCpf, normalizeCpf } from './cpf';

const VALID_CPF = '52998224725';

describe('normalizeCpf', () => {
  it('keeps only digits', () => {
    expect(normalizeCpf('529.982.247-25')).toBe(VALID_CPF);
    expect(normalizeCpf(' 529 982 247 25 ')).toBe(VALID_CPF);
    expect(normalizeCpf('abc')).toBe('');
  });
});

describe('isValidCpf', () => {
  it('accepts valid numbers and rejects broken ones', () => {
    expect(isValidCpf(VALID_CPF)).toBe(true);
    expect(isValidCpf('52998224724')).toBe(false);
    expect(isValidCpf('11111111111')).toBe(false);
    expect(isValidCpf('123')).toBe(false);
  });
});

describe('formatCpf', () => {
  it('formats eleven digits and leaves other shapes untouched', () => {
    expect(formatCpf(VALID_CPF)).toBe('529.982.247-25');
    expect(formatCpf('123')).toBe('123');
  });
});
