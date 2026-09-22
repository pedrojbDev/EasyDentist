'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ConfirmButton } from '@/components/ui/confirm-button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
import { roleLabel } from '@/features/clinics/labels';
import { ApiError } from '@/lib/api/problem';

import { changeRole, removeMember, type Member, type Role } from '../api';

const ALL_ROLES: Role[] = ['OWNER', 'ADMIN', 'DENTIST', 'ASSISTANT', 'RECEPTIONIST'];
const NON_MANAGER_ROLES: Role[] = ['DENTIST', 'ASSISTANT', 'RECEPTIONIST'];
const TARGETS_ONLY_OWNER_CAN_TOUCH: Role[] = ['OWNER', 'ADMIN'];

const MEMBERSHIP_STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pendente',
  ACTIVE: 'Ativo',
  SUSPENDED: 'Suspenso',
};

export function membershipStatusLabel(status: string): string {
  return MEMBERSHIP_STATUS_LABELS[status] ?? status;
}

const dateFormatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' });

function memberLabel(member: Member): string {
  return member.email ?? member.user_id;
}

export function memberErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para gerenciar esta equipe.';
    }
    if (error.status === 404) {
      return 'Vínculo não encontrado. Atualize a página.';
    }
    if (error.status === 409) {
      return 'O último proprietário ativo não pode ser removido ou rebaixado.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível concluir a ação. Tente novamente.';
}

function assignableRoles(actorRole: Role): Role[] {
  return actorRole === 'OWNER' ? ALL_ROLES : NON_MANAGER_ROLES;
}

function canTouch(actorRole: Role, targetRole: Role): boolean {
  if (actorRole === 'OWNER') {
    return true;
  }
  if (actorRole === 'ADMIN') {
    return !TARGETS_ONLY_OWNER_CAN_TOUCH.includes(targetRole);
  }
  return false;
}

export function MembersTable({
  clinicId,
  actorRole,
  members,
}: {
  clinicId: string;
  actorRole: Role;
  members: Member[];
}) {
  const [rows, setRows] = useState(members);
  const [drafts, setDrafts] = useState<Record<string, Role>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const showEmail = members.some((member) => member.email !== null && member.email !== undefined);
  const options = assignableRoles(actorRole);

  async function handleChangeRole(member: Member) {
    const nextRole = drafts[member.id] ?? member.role;
    if (nextRole === member.role) {
      return;
    }
    setMessage(null);
    setError(null);
    try {
      const updated = await changeRole(clinicId, member.id, nextRole);
      setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setMessage('Papel atualizado.');
    } catch (cause) {
      setError(memberErrorMessage(cause));
    }
  }

  async function handleRemove(member: Member) {
    setMessage(null);
    setError(null);
    try {
      await removeMember(clinicId, member.id);
      setRows((current) => current.filter((row) => row.id !== member.id));
      setMessage('Vínculo removido.');
    } catch (cause) {
      setError(memberErrorMessage(cause));
    }
  }

  return (
    <section className="app-panel min-w-0">
      <div className="mb-5">
        <h2 className="font-semibold text-foreground">Pessoas vinculadas</h2>
        <p className="mt-1 text-sm text-muted-foreground">Papéis e situação de acesso à clínica.</p>
      </div>
      {error !== null && (
        <Feedback tone="error" className="mb-3">
          {error}
        </Feedback>
      )}
      {message !== null && (
        <Feedback tone="success" className="mb-3">
          {message}
        </Feedback>
      )}

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum vínculo encontrado.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/55 text-left text-xs uppercase tracking-wide text-muted-foreground">
                {showEmail && (
                  <th scope="col" className="px-3 py-3">
                    E-mail
                  </th>
                )}
                <th scope="col" className="px-3 py-3">
                  Papel
                </th>
                <th scope="col" className="px-3 py-3">
                  Situação
                </th>
                <th scope="col" className="px-3 py-3">
                  Desde
                </th>
                <th scope="col" className="px-3 py-3">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((member) => {
                const label = memberLabel(member);
                const manageable = canTouch(actorRole, member.role);
                return (
                  <tr
                    key={member.id}
                    className="border-b border-border align-middle last:border-b-0 hover:bg-muted/30"
                  >
                    {showEmail && (
                      <td className="px-3 py-3 font-medium text-foreground">
                        {member.email ?? '—'}
                      </td>
                    )}
                    <td className="px-3 py-3">
                      <StatusBadge tone="info">{roleLabel(member.role)}</StatusBadge>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge tone={member.status === 'ACTIVE' ? 'success' : 'warning'}>
                        {membershipStatusLabel(member.status)}
                      </StatusBadge>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground">
                      {dateFormatter.format(new Date(member.created_at))}
                    </td>
                    <td className="px-3 py-3">
                      {manageable ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <select
                            aria-label={`Novo papel de ${label}`}
                            value={drafts[member.id] ?? member.role}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [member.id]: event.target.value as Role,
                              }))
                            }
                            className="app-field min-h-9 w-auto py-1 text-sm"
                          >
                            {options.map((role) => (
                              <option key={role} value={role}>
                                {roleLabel(role)}
                              </option>
                            ))}
                          </select>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void handleChangeRole(member)}
                            aria-label={`Alterar papel de ${label}`}
                          >
                            Alterar papel
                          </Button>
                          <ConfirmButton
                            message={`Remover ${label} da clínica?`}
                            onConfirm={() => void handleRemove(member)}
                            ariaLabel={`Remover ${label}`}
                            variant="destructive"
                            size="sm"
                          >
                            Remover
                          </ConfirmButton>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
