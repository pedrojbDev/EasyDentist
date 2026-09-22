'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ConfirmButton } from '@/components/ui/confirm-button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
import { roleLabel } from '@/features/clinics/labels';
import type { Member, Role } from '@/features/members/api';
import { ApiError } from '@/lib/api/problem';

import { WorkingHoursEditor } from './WorkingHoursEditor';
import {
  createProfessional,
  createRoom,
  setProfessionalArchived,
  setRoomArchived,
  updateProfessional,
  updateRoom,
  type AgendaProfessional,
  type AgendaRoom,
} from '../api';

function actionError(error: unknown, resource: string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'Você não tem permissão para alterar este cadastro.';
    if (error.status === 404) return 'Cadastro não encontrado. Atualize a página.';
    if (error.status === 409)
      return 'Há conflito de agenda ou vínculo duplicado. Resolva-o antes de continuar.';
    if (error.status === 422) return 'Revise os campos informados.';
  }
  return `Não foi possível salvar ${resource}. Tente novamente.`;
}

function resourceStatus(status: string): string {
  return status === 'ACTIVE' ? 'Ativo' : 'Arquivado';
}

export function AgendaResourceManager({
  clinicId,
  role,
  currentUserId,
  initialProfessionals,
  initialRooms,
  members,
}: {
  clinicId: string;
  role: Role;
  currentUserId: string;
  initialProfessionals: AgendaProfessional[];
  initialRooms: AgendaRoom[];
  members: Member[];
}) {
  const [professionals, setProfessionals] = useState(initialProfessionals);
  const [rooms, setRooms] = useState(initialRooms);
  const [editingProfessional, setEditingProfessional] = useState<AgendaProfessional | null>(null);
  const [editingRoom, setEditingRoom] = useState<AgendaRoom | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const canManage = role === 'OWNER' || role === 'ADMIN';
  const assignableMembers = members.filter(
    (member) => member.status === 'ACTIVE' && ['DENTIST', 'OWNER'].includes(member.role),
  );

  async function saveProfessional(formData: FormData) {
    setError(null);
    setMessage(null);
    setPending(true);
    const croNumber = String(formData.get('cro_number') ?? '').trim();
    const croState = String(formData.get('cro_state') ?? '')
      .trim()
      .toUpperCase();
    if (croNumber.length > 0 !== croState.length > 0) {
      setError('Informe CRO e UF juntos, ou deixe ambos vazios.');
      setPending(false);
      return;
    }
    const membershipValue = String(formData.get('membership_id') ?? '');
    const payload = {
      name: String(formData.get('name') ?? '').trim(),
      membership_id: membershipValue || null,
      cro_number: croNumber || null,
      cro_state: croState || null,
    };
    try {
      const saved = editingProfessional
        ? await updateProfessional(clinicId, editingProfessional.id, payload)
        : await createProfessional(clinicId, payload);
      setProfessionals((current) => {
        const without = current.filter((item) => item.id !== saved.id);
        return [...without, saved].sort((left, right) =>
          left.name.localeCompare(right.name, 'pt-BR'),
        );
      });
      setEditingProfessional(null);
      setMessage(editingProfessional ? 'Profissional atualizado.' : 'Profissional cadastrado.');
    } catch (cause) {
      setError(actionError(cause, 'o profissional'));
    } finally {
      setPending(false);
    }
  }

  async function saveRoom(formData: FormData) {
    setError(null);
    setMessage(null);
    setPending(true);
    const payload = { name: String(formData.get('room_name') ?? '').trim() };
    try {
      const saved = editingRoom
        ? await updateRoom(clinicId, editingRoom.id, payload)
        : await createRoom(clinicId, payload);
      setRooms((current) => {
        const without = current.filter((item) => item.id !== saved.id);
        return [...without, saved].sort((left, right) =>
          left.name.localeCompare(right.name, 'pt-BR'),
        );
      });
      setEditingRoom(null);
      setMessage(editingRoom ? 'Sala atualizada.' : 'Sala cadastrada.');
    } catch (cause) {
      setError(actionError(cause, 'a sala'));
    } finally {
      setPending(false);
    }
  }

  async function toggleProfessional(professional: AgendaProfessional) {
    setError(null);
    setMessage(null);
    setPending(true);
    try {
      const saved = await setProfessionalArchived(
        clinicId,
        professional.id,
        professional.status === 'ACTIVE',
      );
      setProfessionals((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setMessage(
        saved.status === 'ACTIVE' ? 'Profissional restaurado.' : 'Profissional arquivado.',
      );
    } catch (cause) {
      setError(actionError(cause, 'o profissional'));
    } finally {
      setPending(false);
    }
  }

  async function toggleRoom(room: AgendaRoom) {
    setError(null);
    setMessage(null);
    setPending(true);
    try {
      const saved = await setRoomArchived(clinicId, room.id, room.status === 'ACTIVE');
      setRooms((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setMessage(saved.status === 'ACTIVE' ? 'Sala restaurada.' : 'Sala arquivada.');
    } catch (cause) {
      setError(actionError(cause, 'a sala'));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid items-start gap-5 xl:grid-cols-2">
      <section className="app-panel min-w-0">
        <h2 className="font-semibold text-foreground">Profissionais da agenda</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Cadastro da clínica, separado do perfil profissional usado na anamnese.
        </p>
        {!canManage && (
          <p className="mt-3 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
            Acesso somente para consulta.
          </p>
        )}
        {canManage && (
          <form
            action={saveProfessional}
            className="mt-5 grid gap-3 border-b border-border pb-5 sm:grid-cols-2"
          >
            <label className="grid gap-1.5 text-sm font-medium sm:col-span-2">
              Nome
              <input
                key={editingProfessional?.id ?? 'new-professional-name'}
                name="name"
                className="app-field"
                required
                maxLength={200}
                defaultValue={editingProfessional?.name ?? ''}
                placeholder="Nome do profissional"
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              CRO (opcional)
              <input
                key={editingProfessional?.id ?? 'new-professional-cro'}
                name="cro_number"
                className="app-field"
                maxLength={50}
                defaultValue={editingProfessional?.cro_number ?? ''}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              UF do CRO (opcional)
              <input
                key={editingProfessional?.id ?? 'new-professional-uf'}
                name="cro_state"
                className="app-field uppercase"
                maxLength={2}
                defaultValue={editingProfessional?.cro_state ?? ''}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium sm:col-span-2">
              Conta da equipe (opcional)
              <select
                key={editingProfessional?.id ?? 'new-professional-member'}
                name="membership_id"
                className="app-field"
                defaultValue={editingProfessional?.membership_id ?? ''}
              >
                <option value="">Sem conta vinculada</option>
                {assignableMembers.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.email ?? member.user_id} · {roleLabel(member.role)}
                  </option>
                ))}
              </select>
              <span className="text-xs font-normal text-muted-foreground">
                Vínculo limitado a integrante ativo com papel Dentista ou Proprietário.
              </span>
            </label>
            <div className="flex flex-wrap gap-2 sm:col-span-2">
              <Button type="submit" disabled={pending}>
                {pending
                  ? 'Salvando…'
                  : editingProfessional
                    ? 'Salvar profissional'
                    : 'Adicionar profissional'}
              </Button>
              {editingProfessional && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingProfessional(null)}
                >
                  Cancelar edição
                </Button>
              )}
            </div>
          </form>
        )}
        {professionals.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">Nenhum profissional cadastrado.</p>
        ) : (
          <ul className="mt-4 divide-y divide-border">
            {professionals.map((professional) => (
              <li
                key={professional.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{professional.name}</span>
                    <StatusBadge tone={professional.status === 'ACTIVE' ? 'success' : 'neutral'}>
                      {resourceStatus(professional.status)}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {professional.cro_number
                      ? `CRO ${professional.cro_number}/${professional.cro_state}`
                      : 'Sem CRO informado'}
                    {' · '}
                    {professional.membership_id ? 'Conta vinculada' : 'Sem conta vinculada'}
                  </p>
                  {professional.status === 'ACTIVE' && (
                    <WorkingHoursEditor
                      clinicId={clinicId}
                      professionalId={professional.id}
                      enabled={
                        canManage ||
                        (role === 'DENTIST' &&
                          members.some(
                            (member) =>
                              member.id === professional.membership_id &&
                              member.user_id === currentUserId &&
                              member.status === 'ACTIVE',
                          ))
                      }
                    />
                  )}
                </div>
                {canManage && (
                  <div className="flex flex-wrap gap-2">
                    {professional.status === 'ACTIVE' && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingProfessional(professional)}
                      >
                        Editar
                      </Button>
                    )}
                    <ConfirmButton
                      message={
                        professional.status === 'ACTIVE'
                          ? `Arquivar ${professional.name}? Resolva consultas pendentes antes de continuar.`
                          : `Restaurar ${professional.name}?`
                      }
                      onConfirm={() => void toggleProfessional(professional)}
                      ariaLabel={`${professional.status === 'ACTIVE' ? 'Arquivar' : 'Restaurar'} ${professional.name}`}
                      size="sm"
                    >
                      {professional.status === 'ACTIVE' ? 'Arquivar' : 'Restaurar'}
                    </ConfirmButton>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="app-panel min-w-0">
        <h2 className="font-semibold text-foreground">Salas e cadeiras</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Recursos físicos da clínica; a sala pode ser opcional em cada consulta.
        </p>
        {canManage && (
          <form
            action={saveRoom}
            className="mt-5 flex flex-wrap items-end gap-3 border-b border-border pb-5"
          >
            <label className="grid min-w-48 flex-1 gap-1.5 text-sm font-medium">
              Nome da sala
              <input
                key={editingRoom?.id ?? 'new-room-name'}
                name="room_name"
                className="app-field"
                required
                maxLength={200}
                defaultValue={editingRoom?.name ?? ''}
                placeholder="Ex.: Consultório 1"
              />
            </label>
            <Button type="submit" disabled={pending}>
              {pending ? 'Salvando…' : editingRoom ? 'Salvar sala' : 'Adicionar sala'}
            </Button>
            {editingRoom && (
              <Button type="button" variant="outline" onClick={() => setEditingRoom(null)}>
                Cancelar
              </Button>
            )}
          </form>
        )}
        {rooms.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">Nenhuma sala cadastrada.</p>
        ) : (
          <ul className="mt-4 divide-y divide-border">
            {rooms.map((room) => (
              <li key={room.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-foreground">{room.name}</span>
                  <StatusBadge tone={room.status === 'ACTIVE' ? 'success' : 'neutral'}>
                    {resourceStatus(room.status)}
                  </StatusBadge>
                </div>
                {canManage && (
                  <div className="flex flex-wrap gap-2">
                    {room.status === 'ACTIVE' && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingRoom(room)}
                      >
                        Editar
                      </Button>
                    )}
                    <ConfirmButton
                      message={
                        room.status === 'ACTIVE'
                          ? `Arquivar ${room.name}? Resolva consultas pendentes antes de continuar.`
                          : `Restaurar ${room.name}?`
                      }
                      onConfirm={() => void toggleRoom(room)}
                      ariaLabel={`${room.status === 'ACTIVE' ? 'Arquivar' : 'Restaurar'} ${room.name}`}
                      size="sm"
                    >
                      {room.status === 'ACTIVE' ? 'Arquivar' : 'Restaurar'}
                    </ConfirmButton>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {(error !== null || message !== null) && (
        <div className="xl:col-span-2">
          {error !== null && <Feedback tone="error">{error}</Feedback>}
          {message !== null && <Feedback tone="success">{message}</Feedback>}
        </div>
      )}
    </div>
  );
}
