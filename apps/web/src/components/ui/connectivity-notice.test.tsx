// @vitest-environment jsdom

import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { ConnectivityNotice } from './connectivity-notice';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('shows the offline notice and clears it after reconnection', () => {
  let online = false;
  vi.spyOn(window.navigator, 'onLine', 'get').mockImplementation(() => online);

  render(<ConnectivityNotice />);
  expect(screen.getByRole('status').textContent).toContain('Sem conexão');

  online = true;
  act(() => window.dispatchEvent(new Event('online')));

  expect(screen.queryByRole('status')).toBeNull();
});
