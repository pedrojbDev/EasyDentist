// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { verifyEmailMock } = vi.hoisted(() => ({ verifyEmailMock: vi.fn() }));

vi.mock('@/features/auth/api', () => ({ verifyEmail: verifyEmailMock }));
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ApiError } from '@/lib/api/problem';

import { VerifyEmailPanel, verifyErrorMessage } from './VerifyEmailPanel';

beforeEach(() => {
  verifyEmailMock.mockReset();
  window.history.replaceState(null, '', '/verify-email');
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '', '/');
});

describe('VerifyEmailPanel', () => {
  it('explains the invalid link when there is no token', () => {
    render(<VerifyEmailPanel />);

    expect(
      screen.getByText('Link inválido ou expirado. Solicite uma nova verificação.'),
    ).toBeTruthy();
    expect(verifyEmailMock).not.toHaveBeenCalled();
  });

  it('confirms the e-mail automatically with the fragment token', async () => {
    window.history.replaceState(null, '', '/verify-email#token=token-1');
    verifyEmailMock.mockResolvedValue(undefined);

    render(<VerifyEmailPanel />);

    expect(await screen.findByText('E-mail confirmado com sucesso.')).toBeTruthy();
    expect(verifyEmailMock).toHaveBeenCalledWith('token-1');
    expect(window.location.hash).toBe('');
  });

  it('keeps the token in memory and allows retrying after a failure', async () => {
    window.history.replaceState(null, '', '/verify-email#token=token-2');
    verifyEmailMock
      .mockRejectedValueOnce(new ApiError({ status: 400, title: 'Requisição inválida' }))
      .mockResolvedValueOnce(undefined);

    render(<VerifyEmailPanel />);

    expect(
      await screen.findByText(
        'Não foi possível confirmar o e-mail. O link pode ter expirado ou já ter sido usado.',
      ),
    ).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));

    expect(await screen.findByText('E-mail confirmado com sucesso.')).toBeTruthy();
    expect(verifyEmailMock).toHaveBeenLastCalledWith('token-2');
  });
});

describe('verifyErrorMessage', () => {
  it('falls back to the generic confirmation failure message', () => {
    expect(verifyErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível confirmar o e-mail. O link pode ter expirado ou já ter sido usado.',
    );
  });
});
