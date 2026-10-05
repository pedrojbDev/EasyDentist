// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

const { getWorkingHours } = vi.hoisted(() => ({ getWorkingHours: vi.fn() }));
vi.mock('../api', () => ({ getWorkingHours, replaceWorkingHours: vi.fn() }));

import { WorkingHoursEditor } from './WorkingHoursEditor';

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('waits for saved working hours before accepting edits', async () => {
  let finishLoad!: (value: { intervals: [] }) => void;
  getWorkingHours.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishLoad = resolve;
      }),
  );
  render(<WorkingHoursEditor clinicId="clinic" professionalId="professional" enabled />);
  await userEvent.click(screen.getByRole('button', { name: 'Configurar expediente semanal' }));
  const add = screen.getByRole('button', { name: 'Adicionar intervalo' }) as HTMLButtonElement;
  expect(add.disabled).toBe(true);
  await act(async () => finishLoad({ intervals: [] }));
  expect(add.disabled).toBe(false);
  await userEvent.click(add);
  expect(screen.getByLabelText('Dia')).toBeTruthy();
});

it('does not allow replacing saved hours after a failed load', async () => {
  getWorkingHours.mockRejectedValueOnce(new Error('network unavailable'));
  render(<WorkingHoursEditor clinicId="clinic" professionalId="professional" enabled />);
  await userEvent.click(screen.getByRole('button', { name: 'Configurar expediente semanal' }));
  await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
  expect(
    (screen.getByRole('button', { name: 'Adicionar intervalo' }) as HTMLButtonElement).disabled,
  ).toBe(true);
  expect(
    (screen.getByRole('button', { name: 'Salvar expediente' }) as HTMLButtonElement).disabled,
  ).toBe(true);
  getWorkingHours.mockResolvedValueOnce({
    intervals: [{ weekday: 1, starts_at: '08:00', ends_at: '17:00' }],
  });
  await userEvent.click(screen.getByRole('button', { name: 'Tentar carregar expediente' }));
  await waitFor(() => expect((screen.getByLabelText('Dia') as HTMLSelectElement).value).toBe('1'));
});

it('loads the new professional before enabling edits when the resource changes', async () => {
  getWorkingHours.mockResolvedValueOnce({
    intervals: [{ weekday: 0, starts_at: '08:00', ends_at: '17:00' }],
  });
  const { rerender } = render(
    <WorkingHoursEditor clinicId="clinic" professionalId="first" enabled />,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Configurar expediente semanal' }));
  await waitFor(() => expect(screen.getByLabelText('Dia')).toBeTruthy());
  let finishLoad!: (value: { intervals: [] }) => void;
  getWorkingHours.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishLoad = resolve;
      }),
  );
  rerender(<WorkingHoursEditor clinicId="clinic" professionalId="second" enabled />);
  expect(
    (screen.getByRole('button', { name: 'Salvar expediente' }) as HTMLButtonElement).disabled,
  ).toBe(true);
  expect(screen.queryByLabelText('Dia')).toBeNull();
  await act(async () => finishLoad({ intervals: [] }));
  expect(
    (screen.getByRole('button', { name: 'Salvar expediente' }) as HTMLButtonElement).disabled,
  ).toBe(false);
  expect(getWorkingHours).toHaveBeenLastCalledWith('clinic', 'second');
});

it.each(['pending', 'failed'])(
  'reloads the original resource after another load is %s',
  async (outcome) => {
    getWorkingHours.mockResolvedValueOnce({
      intervals: [{ weekday: 0, starts_at: '08:00', ends_at: '17:00' }],
    });
    const { rerender } = render(
      <WorkingHoursEditor clinicId="clinic" professionalId="first" enabled />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Configurar expediente semanal' }));
    await waitFor(() => expect(screen.getByLabelText('Dia')).toBeTruthy());
    if (outcome === 'failed') {
      getWorkingHours.mockRejectedValueOnce(new Error('network unavailable'));
    } else {
      getWorkingHours.mockImplementationOnce(() => new Promise(() => {}));
    }
    rerender(<WorkingHoursEditor clinicId="clinic" professionalId="second" enabled />);
    if (outcome === 'failed') await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    let finishLoad!: (value: { intervals: [] }) => void;
    getWorkingHours.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishLoad = resolve;
        }),
    );
    rerender(<WorkingHoursEditor clinicId="clinic" professionalId="first" enabled />);
    expect(getWorkingHours).toHaveBeenCalledTimes(3);
    expect(
      (screen.getByRole('button', { name: 'Salvar expediente' }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await act(async () => finishLoad({ intervals: [] }));
    expect(
      (screen.getByRole('button', { name: 'Salvar expediente' }) as HTMLButtonElement).disabled,
    ).toBe(false);
  },
);
