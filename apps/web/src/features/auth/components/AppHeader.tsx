'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ConfirmButton } from '@/components/ui/confirm-button';
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
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-3">
      <div className="flex items-center gap-4">
        <span className="font-semibold">EasyDentist</span>
        <Link href="/clinics" className="text-sm underline-offset-4 hover:underline">
          Clínicas
        </Link>
        <Link href="/sessions" className="text-sm underline-offset-4 hover:underline">
          Sessões
        </Link>
        <span className="text-sm text-muted-foreground">{user.email}</span>
      </div>
      <div className="flex items-center gap-3">
        {error !== null && (
          <span role="alert" className="text-sm text-destructive">
            {error}
          </span>
        )}
        <button
          type="button"
          disabled={pending}
          onClick={() => void run(logout)}
          className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-60"
        >
          Sair
        </button>
        <ConfirmButton
          message="Encerrar a sessão em todos os dispositivos?"
          onConfirm={() => void run(logoutAll)}
          className="rounded-md border border-border px-3 py-1.5 text-sm"
        >
          Sair de todos os dispositivos
        </ConfirmButton>
      </div>
    </header>
  );
}
