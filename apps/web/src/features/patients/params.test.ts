import { describe, expect, it } from 'vitest';

import { parsePatientListParams, patientListHref } from './params';

describe('parsePatientListParams', () => {
  it('uses safe defaults for an empty query', () => {
    expect(parsePatientListParams({})).toEqual({
      search: null,
      status: 'ACTIVE',
      limit: 20,
      offset: 0,
      page: 1,
    });
  });

  it('trims the search, keeps archived status and derives the offset', () => {
    expect(parsePatientListParams({ search: '  ana  ', status: 'ARCHIVED', page: '3' })).toEqual({
      search: 'ana',
      status: 'ARCHIVED',
      limit: 20,
      offset: 40,
      page: 3,
    });
  });

  it('caps the search length and repairs invalid pages', () => {
    const parsed = parsePatientListParams({ search: 'x'.repeat(400), page: '-2' });
    expect(parsed.search).toHaveLength(120);
    expect(parsed.page).toBe(1);
    expect(parsed.offset).toBe(0);
    expect(parsePatientListParams({ page: 'abc' }).page).toBe(1);
  });

  it('accepts array values from the router', () => {
    expect(parsePatientListParams({ search: ['ana', 'bruno'] }).search).toBe('ana');
    expect(parsePatientListParams({ status: ['ARCHIVED'] }).status).toBe('ARCHIVED');
  });
});

describe('patientListHref', () => {
  it('omits defaults and preserves the filters', () => {
    expect(patientListHref('c1', {})).toBe('/clinics/c1/patients');
    expect(patientListHref('c1', { page: 1 })).toBe('/clinics/c1/patients');
    expect(patientListHref('c1', { search: 'ana', status: 'ARCHIVED', page: 2 })).toBe(
      '/clinics/c1/patients?search=ana&status=ARCHIVED&page=2',
    );
  });
});
