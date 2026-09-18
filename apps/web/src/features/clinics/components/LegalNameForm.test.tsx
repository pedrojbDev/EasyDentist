// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { updateClinicMock } = vi.hoisted(() => ({ updateClinicMock: vi.fn() }));

vi.mock('@/features/clinics/api', () => ({ updateClinic: updateClinicMock }));

import { ApiError } from '@/lib/api/problem';

import { LegalNameForm, legalNameErrorMessage } from './LegalNameForm';

beforeEach(() => {
  updateClinicMock.mockReset();
});

afterEach(cleanup);

describe('LegalNameForm', () => {
  it('is hidden for roles without permission', () => {
    render(<LegalNameForm clinicId="c1" role="ADMIN" initialLegalName="Clínica A" />);

    expect(screen.queryByLabelText('Razão social')).toBeNull();
  });

  it('validates before calling the API', async () => {
    render(<LegalNameForm clinicId="c1" role="OWNER" initialLegalName="Clínica A" />);

    await userEvent.clear(screen.getByLabelText('Razão social'));
    await userEvent.click(screen.getByRole('button', { name: 'Salvar razão social' }));
    expect(updateClinicMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe a razão social.')).toBeTruthy();

    await userEvent.type(screen.getByLabelText('Razão social'), 'x'.repeat(201));
    await userEvent.click(screen.getByRole('button', { name: 'Salvar razão social' }));
    expect(updateClinicMock).not.toHaveBeenCalled();
    expect(screen.getByText('A razão social deve ter no máximo 200 caracteres.')).toBeTruthy();
  });

  it('saves the legal name and confirms the success', async () => {
    updateClinicMock.mockResolvedValue({
      id: 'c1',
      slug: 'clinica-a',
      legal_name: 'Clínica A Ltda',
      status: 'ACTIVE',
      role: 'OWNER',
    });
    render(<LegalNameForm clinicId="c1" role="OWNER" initialLegalName="Clínica A" />);

    await userEvent.clear(screen.getByLabelText('Razão social'));
    await userEvent.type(screen.getByLabelText('Razão social'), 'Clínica A Ltda');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar razão social' }));

    await waitFor(() => {
      expect(updateClinicMock).toHaveBeenCalledWith('c1', 'Clínica A Ltda');
    });
    expect((await screen.findByRole('status')).textContent).toContain('Razão social atualizada.');
  });

  it('shows the permission message on 403', async () => {
    updateClinicMock.mockRejectedValue(new ApiError({ status: 403, title: 'Acesso negado' }));
    render(<LegalNameForm clinicId="c1" role="OWNER" initialLegalName="Clínica A" />);

    await userEvent.click(screen.getByRole('button', { name: 'Salvar razão social' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Você não tem permissão para editar a razão social.',
    );
  });
});

describe('legalNameErrorMessage', () => {
  it('maps rate limits and unknown failures', () => {
    expect(
      legalNameErrorMessage(
        new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 7 }),
      ),
    ).toBe('Muitas tentativas. Tente novamente em 7 segundos.');
    expect(legalNameErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível salvar a razão social. Tente novamente.',
    );
  });
});
