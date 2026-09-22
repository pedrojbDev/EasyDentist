// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { PatientSearchForm } from './PatientSearchForm';

afterEach(cleanup);

describe('PatientSearchForm', () => {
  it('submits a GET search while preserving the status filter', () => {
    render(
      <PatientSearchForm
        clinicId="c1"
        query={{ search: 'ana', status: 'ARCHIVED', limit: 20, offset: 0, page: 1 }}
      />,
    );

    const form = screen.getByRole('search');
    expect(form.getAttribute('action')).toBe('/clinics/c1/patients');
    expect(form.getAttribute('method')).toBe('get');
    expect((screen.getByLabelText('Buscar paciente') as HTMLInputElement).value).toBe('ana');
    expect((screen.getByDisplayValue('ARCHIVED') as HTMLInputElement).getAttribute('name')).toBe(
      'status',
    );
    expect(screen.getByRole('button', { name: 'Buscar' })).toBeTruthy();
  });

  it('offers a clear link only when a search is active', () => {
    render(
      <PatientSearchForm
        clinicId="c1"
        query={{ search: 'ana', status: 'ACTIVE', limit: 20, offset: 0, page: 1 }}
      />,
    );

    expect(screen.getByRole('link', { name: 'Limpar busca' }).getAttribute('href')).toBe(
      '/clinics/c1/patients',
    );

    cleanup();
    render(
      <PatientSearchForm
        clinicId="c1"
        query={{ search: null, status: 'ACTIVE', limit: 20, offset: 0, page: 1 }}
      />,
    );
    expect(screen.queryByRole('link', { name: 'Limpar busca' })).toBeNull();
  });
});
