'use client';

import { LogOut, ShieldOff } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ConfirmButton } from '@/components/ui/confirm-button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';

import { logout, logoutAll, type User } from '../api';

export function AppHeader({ user }: { user: User }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
      router.replace('/login');
      router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.title : 'Não foi possível sair. Tente novamente.');
    } finally {
      setPending(false);
    }
  }

  return (
    <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-border bg-surface/90 px-5 py-3 backdrop-blur sm:px-7 lg:px-10">
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">Conta conectada</p>
        <p className="truncate text-sm font-semibold text-foreground">{user.email}</p>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {error !== null && (
          <Feedback tone="error" className="basis-full sm:basis-auto">
            {error}
          </Feedback>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={pending}
          onClick={() => void run(logout)}
        >
          <LogOut aria-hidden="true" />
          Sair
        </Button>
        <ConfirmButton
          message="Encerrar a sessão em todos os dispositivos?"
          onConfirm={() => void run(logoutAll)}
          ariaLabel="Sair de todos os dispositivos"
          variant="outline"
          size="sm"
        >
          <ShieldOff aria-hidden="true" />
          <span className="hidden sm:inline">Sair de todos os dispositivos</span>
          <span className="sm:hidden">Sair de todos</span>
        </ConfirmButton>
      </div>
    </header>
  );
}
