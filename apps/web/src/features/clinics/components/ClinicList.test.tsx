// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ClinicList } from './ClinicList';

afterEach(cleanup);

const clinics = [
  {
    id: 'c1',
    slug: 'clinica-a',
    legal_name: 'Clínica A',
    status: 'ACTIVE',
    role: 'OWNER' as const,
  },
  {
    id: 'c2',
    slug: 'clinica-b',
    legal_name: 'Clínica B',
    status: 'PROVISIONING',
    role: 'DENTIST' as const,
  },
];

describe('ClinicList', () => {
  it('renders each clinic with its pt-BR role and a link to the selector target', () => {
    render(<ClinicList clinics={clinics} />);

    expect(screen.getByText('Clínica A')).toBeTruthy();
    expect(screen.getByText('clinica-a')).toBeTruthy();
    expect(screen.getByText('Proprietário')).toBeTruthy();
    expect(screen.getByText('Dentista')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Clínica A/ }).getAttribute('href')).toBe(
      '/clinics/c1',
    );
  });

  it('shows an empty state when the user has no active membership', () => {
    render(<ClinicList clinics={[]} />);

    expect(screen.getByText('Você ainda não participa de nenhuma clínica.')).toBeTruthy();
  });
});
