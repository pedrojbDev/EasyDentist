// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { replaceMock, refreshMock } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  refreshMock: vi.fn(),
}));
const { logoutMock, logoutAllMock } = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  logoutAllMock: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
}));
vi.mock('@/features/auth/api', () => ({
  logout: logoutMock,
  logoutAll: logoutAllMock,
}));

import { AppHeader } from './AppHeader';

const user = {
  id: '1',
  email: 'owner@example.com',
  email_verified_at: null,
  status: 'ACTIVE',
};

beforeEach(() => {
  replaceMock.mockReset();
  refreshMock.mockReset();
  logoutMock.mockReset();
  logoutAllMock.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('AppHeader', () => {
  it('shows the signed-in user', () => {
    render(<AppHeader user={user} />);

    expect(screen.getByText('owner@example.com')).toBeTruthy();
  });

  it('logs out only the current session and returns to the login page', async () => {
    logoutMock.mockResolvedValue(undefined);
    render(<AppHeader user={user} />);

    await userEvent.click(screen.getByRole('button', { name: 'Sair' }));

    await waitFor(() => {
      expect(logoutMock).toHaveBeenCalledTimes(1);
    });
    expect(logoutAllMock).not.toHaveBeenCalled();
    expect(replaceMock).toHaveBeenCalledWith('/login');
    expect(refreshMock).toHaveBeenCalled();
  });

  it('asks for confirmation before logging out every device', async () => {
    const confirmMock = vi.fn().mockReturnValue(false);
    vi.stubGlobal('confirm', confirmMock);
    render(<AppHeader user={user} />);

    await userEvent.click(screen.getByRole('button', { name: 'Sair de todos os dispositivos' }));

    expect(confirmMock).toHaveBeenCalled();
    expect(logoutAllMock).not.toHaveBeenCalled();
  });

  it('logs out every device after confirmation', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    logoutAllMock.mockResolvedValue(undefined);
    render(<AppHeader user={user} />);

    await userEvent.click(screen.getByRole('button', { name: 'Sair de todos os dispositivos' }));

    await waitFor(() => {
      expect(logoutAllMock).toHaveBeenCalledTimes(1);
    });
    expect(logoutMock).not.toHaveBeenCalled();
    expect(replaceMock).toHaveBeenCalledWith('/login');
  });
});
