'use client';

import { useEffect, useState } from 'react';

export function useFragmentToken(): string | null {
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const fragment = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
    if (fragment.length === 0) {
      return;
    }
    const value = new URLSearchParams(fragment).get('token');
    if (value === null || value.length === 0) {
      return;
    }
    setToken(value);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  }, []);

  return token;
}
