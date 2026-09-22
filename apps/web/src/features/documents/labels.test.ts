import { describe, expect, it } from 'vitest';

import { categoryLabel, formatFileSize, statusLabel } from './labels';

describe('document labels', () => {
  it('translates categories and statuses to pt-BR', () => {
    expect(categoryLabel('ADMINISTRATIVE')).toBe('Administrativo');
    expect(categoryLabel('CLINICAL')).toBe('Clínico');
    expect(statusLabel('ACTIVE')).toBe('Ativo');
    expect(statusLabel('ARCHIVED')).toBe('Arquivado');
  });
});

describe('formatFileSize', () => {
  it('formats bytes, kilobytes and megabytes with pt-BR decimals', () => {
    expect(formatFileSize(1)).toBe('1 byte');
    expect(formatFileSize(940)).toBe('940 bytes');
    expect(formatFileSize(1536)).toBe('1,5 KB');
    expect(formatFileSize(1048576)).toBe('1 MB');
    expect(formatFileSize(1234567)).toBe('1,2 MB');
    expect(formatFileSize(10 * 1024 * 1024)).toBe('10 MB');
  });
});
