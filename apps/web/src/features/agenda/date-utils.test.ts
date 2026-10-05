import { describe, expect, it } from 'vitest';

import { clinicDateRange, formatClinicDate } from './date-utils';

describe('clinic calendar boundaries', () => {
  it.each([
    ['2026-09-06', 'America/Santiago', '2026-09-06T04:00:00.000Z', '2026-09-07T03:00:00.000Z'],
    ['2018-11-04', 'America/Sao_Paulo', '2018-11-04T03:00:00.000Z', '2018-11-05T02:00:00.000Z'],
    ['2026-10-05', 'America/Bahia', '2026-10-05T03:00:00.000Z', '2026-10-06T03:00:00.000Z'],
    ['2026-11-01', 'America/New_York', '2026-11-01T04:00:00.000Z', '2026-11-02T05:00:00.000Z'],
  ])('loads %s in %s without assuming midnight exists', (day, zone, start, end) => {
    const range = clinicDateRange(day, 'day', zone);
    expect(range.starts_at).toBe(start);
    expect(range.ends_at).toBe(end);
    expect(range.days).toEqual([day]);
  });

  it('formats a skipped-midnight date and its week', () => {
    expect(formatClinicDate('2026-09-06', 'America/Santiago')).toContain('06/09');
    const range = clinicDateRange('2026-09-06', 'week', 'America/Santiago');
    expect(range.days).toHaveLength(7);
    expect(range.days[6]).toBe('2026-09-06');
    expect(range.ends_at).toBe('2026-09-07T03:00:00.000Z');
  });
});
