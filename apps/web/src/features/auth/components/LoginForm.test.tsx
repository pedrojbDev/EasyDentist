// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { replaceMock, refreshMock } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  refreshMock: vi.fn(),
}));
const { loginMock } = vi.hoisted(() => ({ loginMock: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
}));
vi.mock('@/features/auth/api', () => ({ login: loginMock }));

import { ApiError, GENERIC_ERROR_MESSAGE } from '@/lib/api/problem';

import { LoginForm, loginErrorMessage } from './LoginForm';

beforeEach(() => {
  loginMock.mockReset();
  replaceMock.mockReset();
  refreshMock.mockReset();
});

afterEach(cleanup);

describe('LoginForm', () => {
  it('renders labeled fields', () => {
    render(<LoginForm />);

    expect(screen.getByLabelText('E-mail')).toBeTruthy();
    expect(screen.getByLabelText('Senha')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeTruthy();
  });

  it('blocks submission when the fields are empty and focuses the first error', async () => {
    render(<LoginForm />);

    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    expect(loginMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe seu e-mail.')).toBeTruthy();
    expect(screen.getByText('Informe sua senha.')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText('E-mail'));
  });

  it('blocks submission for an invalid e-mail without calling the API', async () => {
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), 'sem-arroba');
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-secreta-123');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    expect(loginMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe um e-mail válido.')).toBeTruthy();
  });

  it('signs in with trimmed e-mail and redirects to the clinic selector', async () => {
    loginMock.mockResolvedValue({
      user: { id: '1', email: 'owner@example.com', email_verified_at: null, status: 'ACTIVE' },
    });
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), ' owner@example.com ');
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-secreta-123');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('owner@example.com', 'senha-secreta-123');
    });
    expect(replaceMock).toHaveBeenCalledWith('/clinics');
    expect(refreshMock).toHaveBeenCalled();
  });

  it('shows a generic invalid-credentials message on 401', async () => {
    loginMock.mockRejectedValue(new ApiError({ status: 401, title: 'Não autenticado' }));
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), 'owner@example.com');
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-errada-123');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    expect((await screen.findByRole('alert')).textContent).toContain('E-mail ou senha inválidos.');
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('shows the wait time on 429', async () => {
    loginMock.mockRejectedValue(
      new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 30 }),
    );
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), 'owner@example.com');
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-secreta-123');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Muitas tentativas. Tente novamente em 30 segundos.',
    );
  });

  it('disables the button while the request is in flight', async () => {
    let resolveLogin: (value: unknown) => void = () => {};
    loginMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLogin = resolve;
        }),
    );
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), 'owner@example.com');
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-secreta-123');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    const button = await screen.findByRole('button', { name: 'Entrando...' });
    expect((button as HTMLButtonElement).disabled).toBe(true);

    resolveLogin({
      user: { id: '1', email: 'owner@example.com', email_verified_at: null, status: 'ACTIVE' },
    });
    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/clinics');
    });
  });
});

describe('loginErrorMessage', () => {
  it('falls back to the generic message for unknown failures', () => {
    expect(loginErrorMessage(new TypeError('fetch failed'))).toBe(GENERIC_ERROR_MESSAGE);
    expect(loginErrorMessage(new ApiError({ status: 500, title: 'Erro interno' }))).toBe(
      GENERIC_ERROR_MESSAGE,
    );
  });

  it('handles a missing retry-after value', () => {
    expect(loginErrorMessage(new ApiError({ status: 429, title: 'Muitas tentativas' }))).toBe(
      'Muitas tentativas. Tente novamente em instantes.',
    );
  });
});
