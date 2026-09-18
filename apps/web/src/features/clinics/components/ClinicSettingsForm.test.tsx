// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { updateSettingsMock } = vi.hoisted(() => ({ updateSettingsMock: vi.fn() }));

vi.mock('@/features/clinics/api', () => ({ updateSettings: updateSettingsMock }));

import { ApiError } from '@/lib/api/problem';

import { ClinicSettingsForm, settingsErrorMessage } from './ClinicSettingsForm';

const settings = {
  clinic_id: 'c1',
  display_name: 'Clínica A',
  timezone: 'America/Bahia',
  locale: 'pt-BR',
  currency: 'BRL',
};

beforeEach(() => {
  updateSettingsMock.mockReset();
});

afterEach(cleanup);

describe('ClinicSettingsForm', () => {
  it('is read-only for operational roles', () => {
    render(<ClinicSettingsForm clinicId="c1" role="DENTIST" initialSettings={settings} />);

    expect(screen.getByText('America/Bahia')).toBeTruthy();
    expect(screen.getByText('BRL')).toBeTruthy();
    expect(screen.queryByLabelText('Nome comercial')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Salvar configurações' })).toBeNull();
  });

  it('lets OWNER and ADMIN edit with pre-filled values', () => {
    render(<ClinicSettingsForm clinicId="c1" role="ADMIN" initialSettings={settings} />);

    expect((screen.getByLabelText('Nome comercial') as HTMLInputElement).value).toBe('Clínica A');
    expect((screen.getByLabelText('Fuso horário') as HTMLInputElement).value).toBe('America/Bahia');
    expect((screen.getByLabelText('Idioma') as HTMLInputElement).value).toBe('pt-BR');
    expect((screen.getByLabelText('Moeda') as HTMLInputElement).value).toBe('BRL');
  });

  it('validates timezone and currency before calling the API', async () => {
    render(<ClinicSettingsForm clinicId="c1" role="OWNER" initialSettings={settings} />);

    const timezone = screen.getByLabelText('Fuso horário');
    await userEvent.clear(timezone);
    await userEvent.type(timezone, 'Marte/Olimpo');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar configurações' }));

    expect(updateSettingsMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe um fuso horário IANA válido.')).toBeTruthy();

    await userEvent.clear(timezone);
    await userEvent.type(timezone, 'America/Sao_Paulo');
    const currency = screen.getByLabelText('Moeda');
    await userEvent.clear(currency);
    await userEvent.type(currency, 'BRL$');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar configurações' }));

    expect(updateSettingsMock).not.toHaveBeenCalled();
    expect(screen.getByText('Use três letras maiúsculas (ex.: BRL).')).toBeTruthy();
  });

  it('saves the settings and confirms the success', async () => {
    updateSettingsMock.mockResolvedValue({
      ...settings,
      display_name: 'Clínica Nova',
      timezone: 'America/Sao_Paulo',
    });
    render(<ClinicSettingsForm clinicId="c1" role="OWNER" initialSettings={settings} />);

    const displayName = screen.getByLabelText('Nome comercial');
    await userEvent.clear(displayName);
    await userEvent.type(displayName, 'Clínica Nova');
    const timezone = screen.getByLabelText('Fuso horário');
    await userEvent.clear(timezone);
    await userEvent.type(timezone, 'America/Sao_Paulo');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar configurações' }));

    await waitFor(() => {
      expect(updateSettingsMock).toHaveBeenCalledWith('c1', {
        display_name: 'Clínica Nova',
        timezone: 'America/Sao_Paulo',
        locale: 'pt-BR',
        currency: 'BRL',
      });
    });
    expect((await screen.findByRole('status')).textContent).toContain('Configurações atualizadas.');
  });

  it('shows the permission message on 403', async () => {
    updateSettingsMock.mockRejectedValue(new ApiError({ status: 403, title: 'Acesso negado' }));
    render(<ClinicSettingsForm clinicId="c1" role="OWNER" initialSettings={settings} />);

    await userEvent.click(screen.getByRole('button', { name: 'Salvar configurações' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Você não tem permissão para editar as configurações.',
    );
  });
});

describe('settingsErrorMessage', () => {
  it('maps invalid data, rate limits and unknown failures', () => {
    expect(settingsErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' }))).toBe(
      'Não foi possível salvar as configurações. Verifique os campos e tente novamente.',
    );
    expect(
      settingsErrorMessage(
        new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 9 }),
      ),
    ).toBe('Muitas tentativas. Tente novamente em 9 segundos.');
    expect(settingsErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível salvar as configurações. Tente novamente.',
    );
  });
});
