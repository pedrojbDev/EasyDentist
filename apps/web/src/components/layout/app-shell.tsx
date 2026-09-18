import type { ReactNode } from 'react';

import { AppSidebar } from '@/components/layout/app-sidebar';
import { ConnectivityNotice } from '@/components/ui/connectivity-notice';
import { AppHeader } from '@/features/auth/components/AppHeader';
import type { User } from '@/features/auth/api';

export function AppShell({ user, children }: { user: User; children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Ir para o conteúdo
      </a>
      <AppSidebar />
      <div className="min-w-0">
        <AppHeader user={user} />
        <ConnectivityNotice />
        <main
          id="main-content"
          className="mx-auto w-full max-w-6xl px-5 py-7 sm:px-7 sm:py-9 lg:px-10"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
