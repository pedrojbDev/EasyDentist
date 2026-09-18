'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ConfirmButton } from '@/components/ui/confirm-button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
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
      <div className="app-panel flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">Nenhuma sessão ativa.</p>
        <ConfirmButton
          message="Encerrar a sessão em todos os dispositivos?"
          onConfirm={() => void handleLogoutAll()}
          variant="destructive"
          className="w-fit"
        >
          Sair de todos os dispositivos
        </ConfirmButton>
      </div>
    );
  }

  return (
    <section className="app-panel flex flex-col gap-4">
      <div>
        <h2 className="font-semibold text-foreground">Dispositivos conectados</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          As datas refletem o horário configurado no seu dispositivo.
        </p>
      </div>
      {error !== null && <Feedback tone="error">{error}</Feedback>}
      {message !== null && <Feedback tone="success">{message}</Feedback>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[42rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/55 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="px-3 py-3">
                Criada em
              </th>
              <th scope="col" className="px-3 py-3">
                Último acesso
              </th>
              <th scope="col" className="px-3 py-3">
                Expira em
              </th>
              <th scope="col" className="px-3 py-3">
                Situação
              </th>
              <th scope="col" className="px-3 py-3">
                Ação
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((session) => {
              const createdLabel = dateFormatter.format(new Date(session.created_at));
              return (
                <tr
                  key={session.id}
                  className="border-b border-border align-middle last:border-b-0 hover:bg-muted/30"
                >
                  <td className="px-3 py-3 font-medium text-foreground">{createdLabel}</td>
                  <td className="px-3 py-3 text-muted-foreground">
                    {dateFormatter.format(new Date(session.last_seen_at))}
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">
                    {dateFormatter.format(new Date(session.expires_at))}
                  </td>
                  <td className="px-3 py-3">
                    {session.current ? (
                      <StatusBadge tone="success">Esta sessão</StatusBadge>
                    ) : (
                      <StatusBadge>Outro dispositivo</StatusBadge>
                    )}
                  </td>
                  <td className="px-3 py-3">
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
                      variant={session.current ? 'destructive' : 'outline'}
                      size="sm"
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
        variant="destructive"
        className="w-fit"
      >
        Sair de todos os dispositivos
      </ConfirmButton>
    </section>
  );
}
