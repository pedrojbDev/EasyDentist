// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { archivePatientMock, restorePatientMock, refreshMock } = vi.hoisted(() => ({
  archivePatientMock: vi.fn(),
  restorePatientMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock('@/features/patients/api', () => ({
  archivePatient: archivePatientMock,
  restorePatient: restorePatientMock,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import type { PatientCapabilities } from '../permissions';
import { PatientTable } from './PatientTable';

const activePatient = {
  id: 'p1',
  clinic_id: 'c1',
  full_name: 'Ana Souza',
  social_name: 'Ana S.',
  birth_date: '1990-05-06',
  cpf: '52998224725',
  phone: '+5571999112222',
  phone_secondary: null,
  email: 'ana@example.com',
  postal_code: null,
  street: null,
  number: null,
  complement: null,
  district: null,
  city: null,
  state: null,
  occupation: null,
  nationality: null,
  birthplace: null,
  emergency_contact_name: null,
  emergency_contact_relationship: null,
  emergency_contact_phone: null,
  guardian_name: null,
  guardian_relationship: null,
  guardian_phone: null,
  administrative_notes: null,
  status: 'ACTIVE' as const,
  archived_at: null,
  created_at: '2026-09-01T12:00:00Z',
  updated_at: '2026-09-01T12:00:00Z',
};

const archivedPatient = {
  ...activePatient,
  id: 'p2',
  full_name: 'Zelia Arquivada',
  social_name: null,
  cpf: null,
  phone: '+5571900001111',
  status: 'ARCHIVED' as const,
  archived_at: '2026-09-10T12:00:00Z',
};

const fullCapabilities: PatientCapabilities = {
  canCreate: true,
  canUpdate: true,
  canArchive: true,
  canReadAlerts: true,
  canManageAlerts: true,
};

const readOnlyCapabilities: PatientCapabilities = {
  canCreate: false,
  canUpdate: false,
  canArchive: false,
  canReadAlerts: true,
  canManageAlerts: false,
};

beforeEach(() => {
  archivePatientMock.mockReset();
  restorePatientMock.mockReset();
  refreshMock.mockReset();
});

afterEach(cleanup);

describe('PatientTable', () => {
  it('renders patients with formatted CPF, contact and status', () => {
    render(
      <PatientTable
        clinicId="c1"
        patients={[activePatient, archivedPatient]}
        capabilities={fullCapabilities}
      />,
    );

    expect(screen.getByText('Ana Souza')).toBeTruthy();
    expect(screen.getByText('Ana S.')).toBeTruthy();
    expect(screen.getByText('529.982.247-25')).toBeTruthy();
    expect(screen.getByText('+5571999112222')).toBeTruthy();
    expect(screen.getByText('Ativo')).toBeTruthy();
    expect(screen.getByText('Arquivado')).toBeTruthy();
    expect(screen.getByText('Zelia Arquivada')).toBeTruthy();
  });

  it('links each patient to its detail page', () => {
    render(
      <PatientTable clinicId="c1" patients={[activePatient]} capabilities={fullCapabilities} />,
    );

    expect(screen.getByRole('link', { name: /Ana Souza/ }).getAttribute('href')).toBe(
      '/clinics/c1/patients/p1',
    );
  });

  it('shows an empty state without patients', () => {
    render(<PatientTable clinicId="c1" patients={[]} capabilities={fullCapabilities} />);

    expect(screen.getByText('Nenhum paciente encontrado.')).toBeTruthy();
  });

  it('hides archive actions from roles without the permission', () => {
    render(
      <PatientTable
        clinicId="c1"
        patients={[activePatient, archivedPatient]}
        capabilities={readOnlyCapabilities}
      />,
    );

    expect(screen.queryByRole('button', { name: /Arquivar/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Restaurar/ })).toBeNull();
    expect(screen.getAllByRole('link', { name: 'Ver' }).length).toBe(2);
  });

  it('archives a patient after confirmation and refreshes the page', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    archivePatientMock.mockResolvedValue({ ...activePatient, status: 'ARCHIVED' });
    render(
      <PatientTable clinicId="c1" patients={[activePatient]} capabilities={fullCapabilities} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Arquivar Ana Souza' }));

    await waitFor(() => {
      expect(archivePatientMock).toHaveBeenCalledWith('c1', 'p1');
    });
    expect(refreshMock).toHaveBeenCalled();
  });

  it('restores an archived patient through the API', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    restorePatientMock.mockResolvedValue({ ...archivedPatient, status: 'ACTIVE' });
    render(
      <PatientTable clinicId="c1" patients={[archivedPatient]} capabilities={fullCapabilities} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Restaurar Zelia Arquivada' }));

    await waitFor(() => {
      expect(restorePatientMock).toHaveBeenCalledWith('c1', 'p2');
    });
  });
});
