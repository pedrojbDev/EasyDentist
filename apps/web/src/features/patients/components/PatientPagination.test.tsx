// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { PatientPagination } from './PatientPagination';

afterEach(cleanup);

const base = { search: null, status: 'ACTIVE' as const, limit: 20, offset: 0, page: 1 };

describe('PatientPagination', () => {
  it('summarizes the visible range and links to the next page', () => {
    render(<PatientPagination clinicId="c1" query={{ ...base, offset: 20, page: 2 }} total={42} />);

    expect(screen.getByText('Mostrando 21–40 de 42 pacientes')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Página anterior' }).getAttribute('href')).toBe(
      '/clinics/c1/patients',
    );
    expect(screen.getByRole('link', { name: 'Próxima página' }).getAttribute('href')).toBe(
      '/clinics/c1/patients?page=3',
    );
  });

  it('omits the previous link on the first page and the next link on the last page', () => {
    render(<PatientPagination clinicId="c1" query={base} total={20} />);

    expect(screen.queryByRole('link', { name: 'Página anterior' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Próxima página' })).toBeNull();
    expect(screen.getByText('Mostrando 1–20 de 20 pacientes')).toBeTruthy();
  });
});
