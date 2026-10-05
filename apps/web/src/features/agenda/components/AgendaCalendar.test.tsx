// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { listAppointments, listBlocks, dialog } = vi.hoisted(() => ({
  listAppointments: vi.fn(),
  listBlocks: vi.fn(),
  dialog: vi.fn(),
}));
vi.mock('../api', () => ({
  listAllAppointments: listAppointments,
  listScheduleBlocks: listBlocks,
}));
vi.mock('./AppointmentDialog', () => ({ AppointmentDialog: dialog }));
vi.mock('./ScheduleBlockDialog', () => ({ ScheduleBlockDialog: () => null }));

import { AgendaCalendar } from './AgendaCalendar';
import type { Appointment } from '../api';
import { clinicToday } from '../date-utils';

const professionals = [
  {
    id: 'professional',
    clinic_id: 'clinic',
    name: 'Dentista',
    cro_number: null,
    cro_state: null,
    membership_id: null,
    archived_at: null,
    status: 'ACTIVE' as const,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('agenda refresh ordering', () => {
  it('keeps the newest day when an older request finishes later', async () => {
    let finishOld!: (items: unknown[]) => void;
    listAppointments.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve;
        }),
    );
    listBlocks.mockResolvedValue({ items: [], total: 0 });
    render(
      <AgendaCalendar
        clinicId="clinic"
        clinicPath="/clinics/clinic"
        timezone="America/Bahia"
        role="ASSISTANT"
        currentUserId="user"
        professionals={professionals}
        rooms={[]}
        members={[]}
      />,
    );
    await waitFor(() => expect(listAppointments).toHaveBeenCalledTimes(1));
    listAppointments.mockResolvedValueOnce([
      {
        id: 'new',
        patient_name: 'Paciente do novo dia',
        professional_name: 'Dentista',
        starts_at: '2026-12-09T12:00:00Z',
        ends_at: '2026-12-09T12:30:00Z',
        status: 'SCHEDULED',
      },
    ]);
    fireEvent.change(screen.getByLabelText('Data selecionada'), {
      target: { value: '2026-12-09' },
    });
    await waitFor(() =>
      expect(screen.getAllByText('Paciente do novo dia').length).toBeGreaterThan(0),
    );
    await act(async () => finishOld([]));
    expect(screen.getAllByText('Paciente do novo dia').length).toBeGreaterThan(0);
  });

  it('keeps the current date when the date input is cleared', async () => {
    listAppointments.mockResolvedValue([]);
    listBlocks.mockResolvedValue({ items: [], total: 0 });
    render(
      <AgendaCalendar
        clinicId="clinic"
        clinicPath="/clinics/clinic"
        timezone="America/Bahia"
        role="ASSISTANT"
        currentUserId="user"
        professionals={[]}
        rooms={[]}
        members={[]}
      />,
    );
    await waitFor(() => expect(listAppointments).toHaveBeenCalledTimes(1));
    const input = screen.getByLabelText('Data selecionada') as HTMLInputElement;
    const originalDate = input.value;
    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe(originalDate);
  });

  it('keeps the mutation result when refresh fails and an older response arrives', async () => {
    const today = clinicToday('America/Bahia');
    const appointment: Appointment = {
      id: 'appointment',
      clinic_id: 'clinic',
      patient_id: 'patient',
      professional_id: 'professional',
      room_id: null,
      patient_name: 'Paciente',
      professional_name: 'Dentista',
      room_name: null,
      starts_at: `${today}T12:00:00Z`,
      ends_at: `${today}T12:30:00Z`,
      status: 'SCHEDULED',
      administrative_note: null,
      cancellation_reason: null,
      version: 1,
      created_at: `${today}T12:00:00Z`,
      updated_at: `${today}T12:00:00Z`,
    };
    listAppointments.mockResolvedValueOnce([appointment]);
    listBlocks.mockResolvedValue({ items: [], total: 0 });
    dialog.mockImplementation(
      (props: {
        appointment: Appointment | null;
        onSaved: (result: Appointment) => Promise<void>;
        onClose: () => void;
      }) =>
        props.appointment ? (
          <button
            onClick={async () => {
              await props.onSaved({ ...props.appointment!, status: 'CONFIRMED', version: 2 });
              props.onClose();
            }}
          >
            Confirmar versão {props.appointment.version}
          </button>
        ) : null,
    );
    render(
      <AgendaCalendar
        clinicId="clinic"
        clinicPath="/clinics/clinic"
        timezone="America/Bahia"
        role="OWNER"
        currentUserId="user"
        professionals={professionals}
        rooms={[]}
        members={[]}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: /Paciente/ })[0]).toBeTruthy(),
    );
    let finishOld!: (items: Appointment[]) => void;
    listAppointments.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve;
        }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }));
    await waitFor(() => expect(listAppointments).toHaveBeenCalledTimes(2));
    listAppointments.mockRejectedValueOnce(new Error('refresh unavailable'));
    fireEvent.click(screen.getAllByRole('button', { name: /Paciente/ })[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar versão 1' }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Confirmar versão 1' })).toBeNull(),
    );
    await act(async () => finishOld([appointment]));
    fireEvent.click(screen.getAllByRole('button', { name: /Paciente/ })[0]);
    expect(screen.getByRole('button', { name: 'Confirmar versão 2' })).toBeTruthy();
  });
});
