'use client';

import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';

import {
  cancelScheduleBlock,
  createScheduleBlock,
  updateScheduleBlock,
  type AgendaProfessional,
  type AgendaRoom,
  type ScheduleBlock,
} from '../api';
import { addLocalMinutes, clinicLocalDateTimeInput } from '../date-utils';

function readableError(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return 'Seu papel não permite alterar este bloqueio.';
  }
  if (error instanceof ApiError && error.status === 409) {
    return 'O bloqueio conflita com uma consulta ou outro bloqueio.';
  }
  return 'Não foi possível salvar o bloqueio.';
}

export function ScheduleBlockDialog({
  clinicId,
  timezone,
  professionals,
  rooms,
  block,
  allowRoomOnly = true,
  initialLocalStart,
  onClose,
  onSaved,
}: {
  clinicId: string;
  timezone: string;
  professionals: AgendaProfessional[];
  rooms: AgendaRoom[];
  block: ScheduleBlock | null;
  allowRoomOnly?: boolean;
  initialLocalStart?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [localStart, setLocalStart] = useState(
    block ? clinicLocalDateTimeInput(block.starts_at, timezone) : (initialLocalStart ?? ''),
  );
  const [localEnd, setLocalEnd] = useState(
    block
      ? clinicLocalDateTimeInput(block.ends_at, timezone)
      : initialLocalStart
        ? addLocalMinutes(initialLocalStart, 60)
        : '',
  );
  const [professionalId, setProfessionalId] = useState(
    block?.professional_id ?? professionals[0]?.id ?? '',
  );
  const [roomId, setRoomId] = useState(block?.room_id ?? '');
  const [label, setLabel] = useState(block?.label ?? '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      if (block) {
        await updateScheduleBlock(clinicId, block.id, {
          local_start: localStart,
          local_end: localEnd,
          professional_id: professionalId || null,
          room_id: roomId || null,
          label: label.trim() || null,
        });
      } else {
        await createScheduleBlock(clinicId, {
          local_start: localStart,
          local_end: localEnd,
          professional_id: professionalId || null,
          room_id: roomId || null,
          label: label.trim() || null,
        });
      }
      onSaved();
      onClose();
    } catch (cause) {
      setError(readableError(cause));
      setPending(false);
    }
  }

  async function cancel() {
    if (!block) return;
    setPending(true);
    setError(null);
    try {
      await cancelScheduleBlock(clinicId, block.id);
      onSaved();
      onClose();
    } catch (cause) {
      setError(readableError(cause));
      setPending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/45 p-3 sm:p-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="block-dialog-title"
        className="app-panel my-auto w-full max-w-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="block-dialog-title" className="text-lg font-semibold text-foreground">
            {block ? 'Editar bloqueio' : 'Bloquear horário'}
          </h2>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </div>
        <form className="mt-5 grid gap-4" onSubmit={(event) => void save(event)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium">
              Início local da clínica
              <input
                className="app-field"
                type="datetime-local"
                required
                value={localStart}
                onChange={(event) => setLocalStart(event.target.value)}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Fim local da clínica
              <input
                className="app-field"
                type="datetime-local"
                required
                value={localEnd}
                onChange={(event) => setLocalEnd(event.target.value)}
              />
            </label>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium">
              Profissional
              <select
                className="app-field"
                value={professionalId}
                onChange={(event) => setProfessionalId(event.target.value)}
              >
                {allowRoomOnly && <option value="">Nenhum</option>}
                {professionals.map((professional) => (
                  <option key={professional.id} value={professional.id}>
                    {professional.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Sala
              <select
                className="app-field"
                value={roomId}
                onChange={(event) => setRoomId(event.target.value)}
              >
                <option value="">Nenhuma</option>
                {rooms.map((room) => (
                  <option key={room.id} value={room.id}>
                    {room.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="grid gap-1.5 text-sm font-medium">
            Descrição (opcional)
            <input
              className="app-field"
              maxLength={200}
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Ex.: manutenção da cadeira"
            />
          </label>
          {error && <Feedback tone="error">{error}</Feedback>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={pending || (!professionalId && !roomId)}>
              {pending ? 'Salvando…' : block ? 'Salvar bloqueio' : 'Criar bloqueio'}
            </Button>
            {block && (
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => void cancel()}
              >
                Cancelar bloqueio
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={onClose}>
              Fechar
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
