'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ConfirmButton } from '@/components/ui/confirm-button';
import { logoutAll } from '@/features/auth/api';
import { ApiError } from '@/lib/api/problem';

import { revokeSession, type Session } from '../api';

const dateFormatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

export function sessionErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para encerrar esta sessão.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível encerrar a sessão. Tente novamente.';
}

export function SessionsTable({ sessions }: { sessions: Session[] }) {
  const router = useRouter();
  const [rows, setRows] = useState(sessions);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function goToLogin() {
    router.replace('/login');
    router.refresh();
  }

  async function handleRevoke(session: Session) {
    setMessage(null);
    setError(null);
    try {
      await revokeSession(session.id);
      if (session.current) {
        goToLogin();
        return;
      }
      setRows((current) => current.filter((row) => row.id !== session.id));
      setMessage('Sessão encerrada.');
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        setRows((current) => current.filter((row) => row.id !== session.id));
        setMessage('Esta sessão já havia sido encerrada.');
        return;
      }
      setError(sessionErrorMessage(cause));
    }
  }

  async function handleLogoutAll() {
    setMessage(null);
    setError(null);
    try {
      await logoutAll();
      goToLogin();
    } catch (cause) {
      setError(sessionErrorMessage(cause));
    }
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">Nenhuma sessão ativa.</p>
        <ConfirmButton
          message="Encerrar a sessão em todos os dispositivos?"
          onConfirm={() => void handleLogoutAll()}
          className="w-fit rounded-md border border-border px-3 py-1.5 text-sm"
        >
          Sair de todos os dispositivos
        </ConfirmButton>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error !== null && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {message !== null && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th scope="col" className="py-2 pr-3">
                Criada em
              </th>
              <th scope="col" className="py-2 pr-3">
                Último acesso
              </th>
              <th scope="col" className="py-2 pr-3">
                Expira em
              </th>
              <th scope="col" className="py-2 pr-3">
                Situação
              </th>
              <th scope="col" className="py-2">
                Ação
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((session) => {
              const createdLabel = dateFormatter.format(new Date(session.created_at));
              return (
                <tr key={session.id} className="border-b border-border align-middle">
                  <td className="py-2 pr-3">{createdLabel}</td>
                  <td className="py-2 pr-3">
                    {dateFormatter.format(new Date(session.last_seen_at))}
                  </td>
                  <td className="py-2 pr-3">
                    {dateFormatter.format(new Date(session.expires_at))}
                  </td>
                  <td className="py-2 pr-3">
                    {session.current ? (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs">Esta sessão</span>
                    ) : (
                      'Outro dispositivo'
                    )}
                  </td>
                  <td className="py-2">
                    <ConfirmButton
                      message={
                        session.current
                          ? 'Encerrar esta sessão e voltar ao login?'
                          : `Encerrar a sessão criada em ${createdLabel}?`
                      }
                      onConfirm={() => void handleRevoke(session)}
                      ariaLabel={
                        session.current
                          ? 'Encerrar esta sessão'
                          : `Revogar sessão criada em ${createdLabel}`
                      }
                      className="rounded-md border border-border px-2 py-1"
                    >
                      Revogar
                    </ConfirmButton>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmButton
        message="Encerrar a sessão em todos os dispositivos?"
        onConfirm={() => void handleLogoutAll()}
        className="w-fit rounded-md border border-border px-3 py-1.5 text-sm"
      >
        Sair de todos os dispositivos
      </ConfirmButton>
    </div>
  );
}
