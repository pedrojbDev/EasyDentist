// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { resetPasswordMock } = vi.hoisted(() => ({ resetPasswordMock: vi.fn() }));

vi.mock('@/features/auth/api', () => ({ resetPassword: resetPasswordMock }));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ApiError } from '@/lib/api/problem';

import { ResetPasswordForm, resetErrorMessage } from './ResetPasswordForm';

beforeEach(() => {
  resetPasswordMock.mockReset();
  window.history.replaceState(null, '', '/reset-password');
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '', '/');
});

function openWithToken(token: string) {
  window.history.replaceState(null, '', `/reset-password#token=${token}`);
}

describe('ResetPasswordForm', () => {
  it('explains the invalid link when there is no token', () => {
    render(<ResetPasswordForm />);

    expect(
      screen.getByText('Link inválido ou expirado. Solicite uma nova recuperação.'),
    ).toBeTruthy();
    expect(screen.queryByLabelText('Nova senha')).toBeNull();
  });

  it('validates length and confirmation before calling the API', async () => {
    openWithToken('token-1');
    render(<ResetPasswordForm />);

    await userEvent.type(screen.getByLabelText('Nova senha'), 'curta');
    await userEvent.type(screen.getByLabelText('Confirme a nova senha'), 'curta');
    await userEvent.click(screen.getByRole('button', { name: 'Redefinir senha' }));

    expect(resetPasswordMock).not.toHaveBeenCalled();
    expect(screen.getByText('A senha deve ter entre 12 e 128 caracteres.')).toBeTruthy();

    await userEvent.clear(screen.getByLabelText('Nova senha'));
    await userEvent.type(screen.getByLabelText('Nova senha'), 'senha-nova-123456');
    await userEvent.clear(screen.getByLabelText('Confirme a nova senha'));
    await userEvent.type(screen.getByLabelText('Confirme a nova senha'), 'senha-diferente-1');
    await userEvent.click(screen.getByRole('button', { name: 'Redefinir senha' }));

    expect(resetPasswordMock).not.toHaveBeenCalled();
    expect(screen.getByText('As senhas não coincidem.')).toBeTruthy();
  });

  it('resets the password and offers the login link', async () => {
    openWithToken('token-2');
    resetPasswordMock.mockResolvedValue(undefined);
    render(<ResetPasswordForm />);

    await userEvent.type(screen.getByLabelText('Nova senha'), 'senha-nova-123456');
    await userEvent.type(screen.getByLabelText('Confirme a nova senha'), 'senha-nova-123456');
    await userEvent.click(screen.getByRole('button', { name: 'Redefinir senha' }));

    await waitFor(() => {
      expect(resetPasswordMock).toHaveBeenCalledWith('token-2', 'senha-nova-123456');
    });
    expect(screen.getByText('Senha alterada com sucesso.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Entrar' }).getAttribute('href')).toBe('/login');
  });

  it('keeps the token in memory to allow a retry after a failure', async () => {
    openWithToken('token-3');
    resetPasswordMock
      .mockRejectedValueOnce(new ApiError({ status: 400, title: 'Requisição inválida' }))
      .mockResolvedValueOnce(undefined);
    render(<ResetPasswordForm />);

    await userEvent.type(screen.getByLabelText('Nova senha'), 'senha-nova-123456');
    await userEvent.type(screen.getByLabelText('Confirme a nova senha'), 'senha-nova-123456');
    await userEvent.click(screen.getByRole('button', { name: 'Redefinir senha' }));

    expect(
      await screen.findByText('Link inválido ou expirado. Solicite uma nova recuperação.'),
    ).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));

    await waitFor(() => {
      expect(resetPasswordMock).toHaveBeenCalledTimes(2);
    });
    expect(resetPasswordMock).toHaveBeenLastCalledWith('token-3', 'senha-nova-123456');
  });
});

describe('resetErrorMessage', () => {
  it('maps invalid tokens, rate limits and unknown failures', () => {
    expect(resetErrorMessage(new ApiError({ status: 400, title: 'Requisição inválida' }))).toBe(
      'Link inválido ou expirado. Solicite uma nova recuperação.',
    );
    expect(
      resetErrorMessage(new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 10 })),
    ).toBe('Muitas tentativas. Tente novamente em 10 segundos.');
    expect(resetErrorMessage(new ApiError({ status: 500, title: 'Erro interno' }))).toBe(
      'Não foi possível redefinir a senha. Tente novamente.',
    );
  });
});
