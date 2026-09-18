// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { replaceMock, refreshMock } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  refreshMock: vi.fn(),
}));
const { revokeSessionMock } = vi.hoisted(() => ({ revokeSessionMock: vi.fn() }));
const { logoutAllMock } = vi.hoisted(() => ({ logoutAllMock: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
}));
vi.mock('@/features/sessions/api', () => ({ revokeSession: revokeSessionMock }));
vi.mock('@/features/auth/api', () => ({ logoutAll: logoutAllMock }));

import { ApiError } from '@/lib/api/problem';

import { SessionsTable, sessionErrorMessage } from './SessionsTable';

const formatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

const sessions = [
  {
    id: 's1',
    created_at: '2026-09-17T12:00:00Z',
    last_seen_at: '2026-09-17T12:30:00Z',
    expires_at: '2026-10-17T12:00:00Z',
    current: true,
  },
  {
    id: 's2',
    created_at: '2026-09-16T09:00:00Z',
    last_seen_at: '2026-09-16T09:10:00Z',
    expires_at: '2026-10-16T09:00:00Z',
    current: false,
  },
];

const otherLabel = `Revogar sessão criada em ${formatter.format(new Date(sessions[1].created_at))}`;

beforeEach(() => {
  revokeSessionMock.mockReset();
  logoutAllMock.mockReset();
  replaceMock.mockReset();
  refreshMock.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SessionsTable', () => {
  it('renders formatted dates and marks the current session', () => {
    render(<SessionsTable sessions={sessions} />);

    expect(screen.getByText('Esta sessão')).toBeTruthy();
    expect(
      screen.getAllByText(formatter.format(new Date(sessions[0].created_at))).length,
    ).toBeGreaterThan(0);
  });

  it('shows an empty state without sessions', () => {
    render(<SessionsTable sessions={[]} />);

    expect(screen.getByText('Nenhuma sessão ativa.')).toBeTruthy();
  });

  it('revokes another device after confirmation', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    revokeSessionMock.mockResolvedValue(undefined);
    render(<SessionsTable sessions={sessions} />);

    await userEvent.click(screen.getByRole('button', { name: otherLabel }));

    await waitFor(() => {
      expect(revokeSessionMock).toHaveBeenCalledWith('s2');
    });
    expect(screen.queryByRole('button', { name: otherLabel })).toBeNull();
    expect((await screen.findByRole('status')).textContent).toContain('Sessão encerrada.');
  });

  it('revokes the current session and returns to the login page', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    revokeSessionMock.mockResolvedValue(undefined);
    render(<SessionsTable sessions={sessions} />);

    await userEvent.click(screen.getByRole('button', { name: 'Encerrar esta sessão' }));

    await waitFor(() => {
      expect(revokeSessionMock).toHaveBeenCalledWith('s1');
    });
    expect(replaceMock).toHaveBeenCalledWith('/login');
    expect(refreshMock).toHaveBeenCalled();
  });

  it('handles a session revoked elsewhere with 404', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    revokeSessionMock.mockRejectedValue(
      new ApiError({ status: 404, title: 'Recurso não encontrado' }),
    );
    render(<SessionsTable sessions={sessions} />);

    await userEvent.click(screen.getByRole('button', { name: otherLabel }));

    expect((await screen.findByRole('status')).textContent).toContain(
      'Esta sessão já havia sido encerrada.',
    );
    expect(screen.queryByRole('button', { name: otherLabel })).toBeNull();
  });

  it('logs out every device after confirmation', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    logoutAllMock.mockResolvedValue(undefined);
    render(<SessionsTable sessions={sessions} />);

    await userEvent.click(screen.getByRole('button', { name: 'Sair de todos os dispositivos' }));

    await waitFor(() => {
      expect(logoutAllMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock).toHaveBeenCalledWith('/login');
  });
});

describe('sessionErrorMessage', () => {
  it('maps permission, rate limit and unknown failures', () => {
    expect(sessionErrorMessage(new ApiError({ status: 403, title: 'Acesso negado' }))).toBe(
      'Você não tem permissão para encerrar esta sessão.',
    );
    expect(
      sessionErrorMessage(new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 2 })),
    ).toBe('Muitas tentativas. Tente novamente em 2 segundos.');
    expect(sessionErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível encerrar a sessão. Tente novamente.',
    );
  });
});
