// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { forgotPasswordMock } = vi.hoisted(() => ({ forgotPasswordMock: vi.fn() }));

vi.mock('@/features/auth/api', () => ({ forgotPassword: forgotPasswordMock }));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ApiError, GENERIC_ERROR_MESSAGE } from '@/lib/api/problem';

import { ForgotPasswordForm, forgotErrorMessage } from './ForgotPasswordForm';

beforeEach(() => {
  forgotPasswordMock.mockReset();
});

afterEach(cleanup);

describe('ForgotPasswordForm', () => {
  it('validates the e-mail before calling the API', async () => {
    render(<ForgotPasswordForm />);

    await userEvent.click(screen.getByRole('button', { name: 'Enviar instruções' }));
    expect(forgotPasswordMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe seu e-mail.')).toBeTruthy();

    await userEvent.type(screen.getByLabelText('E-mail'), 'sem-arroba');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar instruções' }));
    expect(forgotPasswordMock).not.toHaveBeenCalled();
    expect(screen.getByText('Informe um e-mail válido.')).toBeTruthy();
  });

  it('shows the same confirmation for any address', async () => {
    forgotPasswordMock.mockResolvedValue(undefined);
    render(<ForgotPasswordForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), ' owner@example.com ');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar instruções' }));

    await waitFor(() => {
      expect(forgotPasswordMock).toHaveBeenCalledWith('owner@example.com');
    });
    expect(
      screen.getByText(
        'Se existir uma conta com este e-mail, enviaremos as instruções de recuperação. Verifique sua caixa de entrada e o spam.',
      ),
    ).toBeTruthy();
  });

  it('shows the wait time on 429', async () => {
    forgotPasswordMock.mockRejectedValue(
      new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 45 }),
    );
    render(<ForgotPasswordForm />);

    await userEvent.type(screen.getByLabelText('E-mail'), 'owner@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar instruções' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Muitas tentativas. Tente novamente em 45 segundos.',
    );
  });
});

describe('forgotErrorMessage', () => {
  it('falls back to the generic message', () => {
    expect(forgotErrorMessage(new TypeError('fetch failed'))).toBe(GENERIC_ERROR_MESSAGE);
  });
});
