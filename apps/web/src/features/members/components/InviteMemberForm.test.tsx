// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { inviteMemberMock } = vi.hoisted(() => ({ inviteMemberMock: vi.fn() }));

vi.mock('@/features/members/api', () => ({ inviteMember: inviteMemberMock }));

import { ApiError } from '@/lib/api/problem';

import { InviteMemberForm, inviteErrorMessage } from './InviteMemberForm';

const expiryFormatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' });

beforeEach(() => {
  inviteMemberMock.mockReset();
});

afterEach(cleanup);

describe('InviteMemberForm', () => {
  it('is hidden for operational roles', () => {
    render(<InviteMemberForm clinicId="c1" actorRole="ASSISTANT" />);

    expect(screen.queryByLabelText('E-mail do convidado')).toBeNull();
  });

  it('offers every role to OWNER', () => {
    render(<InviteMemberForm clinicId="c1" actorRole="OWNER" />);

    const select = screen.getByLabelText('Papel do convidado');
    expect(within(select).getAllByRole('option')).toHaveLength(5);
  });

  it('hides OWNER and ADMIN from ADMIN options', () => {
    render(<InviteMemberForm clinicId="c1" actorRole="ADMIN" />);

    const select = screen.getByLabelText('Papel do convidado');
    const options = within(select)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value);
    expect(options).toEqual(['DENTIST', 'ASSISTANT', 'RECEPTIONIST']);
  });

  it('validates the e-mail before calling the API', async () => {
    render(<InviteMemberForm clinicId="c1" actorRole="OWNER" />);

    await userEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));
    expect(inviteMemberMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe o e-mail do convidado.')).toBeTruthy();

    await userEvent.type(screen.getByLabelText('E-mail do convidado'), 'sem-arroba');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));
    expect(inviteMemberMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe um e-mail válido.')).toBeTruthy();
  });

  it('invites a member and shows the expiry date', async () => {
    inviteMemberMock.mockResolvedValue({
      membership_id: 'm9',
      invitation_expires_at: '2026-09-20T12:00:00Z',
    });
    render(<InviteMemberForm clinicId="c1" actorRole="ADMIN" />);

    await userEvent.type(screen.getByLabelText('E-mail do convidado'), ' novo@example.com ');
    await userEvent.selectOptions(screen.getByLabelText('Papel do convidado'), 'RECEPTIONIST');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));

    await waitFor(() => {
      expect(inviteMemberMock).toHaveBeenCalledWith('c1', 'novo@example.com', 'RECEPTIONIST');
    });
    const status = await screen.findByRole('status');
    expect(status.textContent).toContain('Convite enviado para novo@example.com.');
    expect(status.textContent).toContain(expiryFormatter.format(new Date('2026-09-20T12:00:00Z')));
  });

  it('explains an existing membership on 409', async () => {
    inviteMemberMock.mockRejectedValue(new ApiError({ status: 409, title: 'Conflito' }));
    render(<InviteMemberForm clinicId="c1" actorRole="OWNER" />);

    await userEvent.type(screen.getByLabelText('E-mail do convidado'), 'ja@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Este e-mail já participa da clínica.',
    );
  });

  it('shows the wait time on 429', async () => {
    inviteMemberMock.mockRejectedValue(
      new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 60 }),
    );
    render(<InviteMemberForm clinicId="c1" actorRole="OWNER" />);

    await userEvent.type(screen.getByLabelText('E-mail do convidado'), 'novo@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Muitas tentativas. Tente novamente em 60 segundos.',
    );
  });
});

describe('inviteErrorMessage', () => {
  it('maps permission, invalid data and unknown failures', () => {
    expect(inviteErrorMessage(new ApiError({ status: 403, title: 'Acesso negado' }))).toBe(
      'Você não tem permissão para convidar para esta clínica.',
    );
    expect(inviteErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' }))).toBe(
      'Não foi possível enviar o convite. Verifique os dados e tente novamente.',
    );
    expect(inviteErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível enviar o convite. Tente novamente.',
    );
  });
});
