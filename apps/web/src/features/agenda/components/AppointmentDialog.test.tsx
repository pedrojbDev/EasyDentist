// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

const { setAppointmentStatus, listAppointmentHistory, listPatients } = vi.hoisted(() => ({
  setAppointmentStatus: vi.fn(),
  listAppointmentHistory: vi.fn(),
  listPatients: vi.fn(),
}));
vi.mock('../api', () => ({ setAppointmentStatus, listAppointmentHistory }));
vi.mock('@/features/patients/api', () => ({ listPatients }));

import type { Appointment } from '../api';
import { AppointmentDialog } from './AppointmentDialog';

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('waits for the refreshed appointment version before closing', async () => {
  listAppointmentHistory.mockResolvedValue({ items: [] });
  listPatients.mockResolvedValue({ items: [] });
  let finishRefresh!: () => void;
  const onSaved = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finishRefresh = resolve;
      }),
  );
  const onClose = vi.fn();
  const appointment: Appointment = {
    id: 'appointment',
    clinic_id: 'clinic',
    patient_id: 'patient',
    professional_id: 'professional',
    room_id: null,
    patient_name: 'Paciente',
    professional_name: 'Dentista',
    room_name: null,
    starts_at: '2026-10-05T12:00:00Z',
    ends_at: '2026-10-05T12:30:00Z',
    status: 'SCHEDULED',
    administrative_note: null,
    cancellation_reason: null,
    version: 1,
    created_at: '2026-10-01T12:00:00Z',
    updated_at: '2026-10-01T12:00:00Z',
  };
  const savedAppointment = { ...appointment, status: 'CONFIRMED', version: 2 };
  setAppointmentStatus.mockResolvedValue(savedAppointment);
  render(
    <AppointmentDialog
      clinicId="clinic"
      clinicPath="/clinics/clinic"
      timezone="America/Bahia"
      professionals={[]}
      rooms={[]}
      appointment={appointment}
      canManage
      onSaved={onSaved}
      onClose={onClose}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar consulta' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(onSaved).toHaveBeenCalledWith(savedAppointment);
  expect(onClose).not.toHaveBeenCalled();
  expect(
    (screen.getByRole('button', { name: 'Confirmar consulta' }) as HTMLButtonElement).disabled,
  ).toBe(true);
  await act(async () => finishRefresh());
  expect(onClose).toHaveBeenCalledOnce();
});
