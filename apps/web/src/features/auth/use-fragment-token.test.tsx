// @vitest-environment jsdom

import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useFragmentToken } from './use-fragment-token';

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('useFragmentToken', () => {
  it('captures the token into memory before clearing the fragment', () => {
    window.history.replaceState(null, '', '/reset-password#token=abc123');

    const { result } = renderHook(() => useFragmentToken());

    expect(result.current).toBe('abc123');
    expect(window.location.hash).toBe('');
    expect(window.location.pathname).toBe('/reset-password');
  });

  it('returns null when there is no fragment', () => {
    window.history.replaceState(null, '', '/accept-invitation');

    const { result } = renderHook(() => useFragmentToken());

    expect(result.current).toBeNull();
  });

  it('keeps unrelated fragments untouched', () => {
    window.history.replaceState(null, '', '/verify-email#outra=coisa');

    const { result } = renderHook(() => useFragmentToken());

    expect(result.current).toBeNull();
    expect(window.location.hash).toBe('#outra=coisa');
  });
});
