// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { acceptInvitationMock } = vi.hoisted(() => ({ acceptInvitationMock: vi.fn() }));

vi.mock('@/features/auth/api', () => ({ acceptInvitation: acceptInvitationMock }));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ApiError } from '@/lib/api/problem';

import { AcceptInvitationForm, acceptErrorMessage } from './AcceptInvitationForm';

beforeEach(() => {
  acceptInvitationMock.mockReset();
  window.history.replaceState(null, '', '/accept-invitation');
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '', '/');
});

function openWithToken(token: string) {
  window.history.replaceState(null, '', `/accept-invitation#token=${token}`);
}

describe('AcceptInvitationForm', () => {
  it('explains the invalid link when there is no token', () => {
    render(<AcceptInvitationForm />);

    expect(screen.getByText('Convite inválido, expirado ou já utilizado.')).toBeTruthy();
    expect(acceptInvitationMock).not.toHaveBeenCalled();
  });

  it('activates the invitation without a password and keeps the guidance visible', async () => {
    openWithToken('token-1');
    acceptInvitationMock.mockResolvedValue(undefined);
    render(<AcceptInvitationForm />);

    expect(screen.getByText(/Se você já tem conta no EasyDentist/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Ativar convite' }));

    await waitFor(() => {
      expect(acceptInvitationMock).toHaveBeenCalledWith('token-1');
    });
    expect(screen.getByText('Convite aceito com sucesso.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/login');
  });

  it('validates length and confirmation when a password is provided', async () => {
    openWithToken('token-2');
    render(<AcceptInvitationForm />);

    await userEvent.type(screen.getByLabelText('Senha (opcional)'), 'curta');
    await userEvent.type(screen.getByLabelText('Confirme a senha'), 'curta');
    await userEvent.click(screen.getByRole('button', { name: 'Ativar convite' }));

    expect(acceptInvitationMock).not.toHaveBeenCalled();
    expect(screen.getByText('A senha deve ter entre 12 e 128 caracteres.')).toBeTruthy();

    await userEvent.clear(screen.getByLabelText('Senha (opcional)'));
    await userEvent.type(screen.getByLabelText('Senha (opcional)'), 'senha-nova-123456');
    await userEvent.clear(screen.getByLabelText('Confirme a senha'));
    await userEvent.type(screen.getByLabelText('Confirme a senha'), 'outra-senha-123456');
    await userEvent.click(screen.getByRole('button', { name: 'Ativar convite' }));

    expect(acceptInvitationMock).not.toHaveBeenCalled();
    expect(screen.getByText('As senhas não coincidem.')).toBeTruthy();
  });

  it('sends the password when it is provided', async () => {
    openWithToken('token-3');
    acceptInvitationMock.mockResolvedValue(undefined);
    render(<AcceptInvitationForm />);

    await userEvent.type(screen.getByLabelText('Senha (opcional)'), 'senha-nova-123456');
    await userEvent.type(screen.getByLabelText('Confirme a senha'), 'senha-nova-123456');
    await userEvent.click(screen.getByRole('button', { name: 'Ativar convite' }));

    await waitFor(() => {
      expect(acceptInvitationMock).toHaveBeenCalledWith('token-3', 'senha-nova-123456');
    });
  });

  it('guides the first access generically on 422 without claiming the cause', async () => {
    openWithToken('token-4');
    acceptInvitationMock.mockRejectedValue(new ApiError({ status: 422, title: 'Dados inválidos' }));
    render(<AcceptInvitationForm />);

    await userEvent.click(screen.getByRole('button', { name: 'Ativar convite' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Não foi possível ativar o convite. Se este é o seu primeiro acesso, defina uma senha de 12 a 128 caracteres.',
    );
    expect(acceptInvitationMock).toHaveBeenCalledTimes(1);
  });
});

describe('acceptErrorMessage', () => {
  it('maps invalid invitations, first-access, rate limits and unknown failures', () => {
    expect(acceptErrorMessage(new ApiError({ status: 400, title: 'Requisição inválida' }))).toBe(
      'Convite inválido, expirado ou já utilizado.',
    );
    expect(acceptErrorMessage(new ApiError({ status: 422, title: 'Dados inválidos' }))).toBe(
      'Não foi possível ativar o convite. Se este é o seu primeiro acesso, defina uma senha de 12 a 128 caracteres.',
    );
    expect(
      acceptErrorMessage(new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 5 })),
    ).toBe('Muitas tentativas. Tente novamente em 5 segundos.');
    expect(acceptErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível ativar o convite. Tente novamente.',
    );
  });
});
