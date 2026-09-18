'use client';

import { WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';

export function ConnectivityNotice() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const syncConnection = () => setOnline(navigator.onLine);

    syncConnection();
    window.addEventListener('online', syncConnection);
    window.addEventListener('offline', syncConnection);

    return () => {
      window.removeEventListener('online', syncConnection);
      window.removeEventListener('offline', syncConnection);
    };
  }, []);

  if (online) return null;

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 border-b border-warning/25 bg-warning/10 px-4 py-2 text-sm font-medium text-warning-foreground"
    >
      <WifiOff aria-hidden="true" className="size-4" />
      Sem conexão. Reconecte-se para continuar.
    </div>
  );
}
