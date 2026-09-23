'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import type { Route } from 'next';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
import { listPatients } from '@/features/patients/api';
import { ApiError } from '@/lib/api/problem';

import {
  createAppointment,
  findAvailability,
  listAppointmentHistory,
  setAppointmentStatus,
  updateAppointment,
  type AgendaProfessional,
  type AgendaRoom,
  type Appointment,
  type AppointmentHistoryList,
  type AppointmentStatus,
  type AppointmentUpdateRequest,
} from '../api';
import { clinicLocalDateTimeInput, formatClinicTime } from '../date-utils';

const statusLabels: Record<AppointmentStatus, string> = {
  SCHEDULED: 'Agendada',
  CONFIRMED: 'Confirmada',
  CHECKED_IN: 'Chegou',
  IN_PROGRESS: 'Em atendimento',
  COMPLETED: 'Concluída',
  CANCELLED: 'Cancelada',
  NO_SHOW: 'Faltou',
};

function readableError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'Seu papel não permite esta alteração.';
    if (error.status === 404) return 'O cadastro ou a consulta não foi encontrado.';
    if (error.status === 409)
      return 'A agenda mudou ou existe conflito. Atualize e tente outro horário.';
    if (error.status === 422) return 'Confira os dados e horários informados.';
  }
  return 'Não foi possível salvar a consulta.';
}

function eventLabel(value: string): string {
  if (value === 'CREATED') return 'Consulta criada';
  if (value === 'RESCHEDULED') return 'Consulta editada ou remarcada';
  return 'Estado atualizado';
}

export function AppointmentDialog({
  clinicId,
  timezone,
  clinicPath,
  professionals,
  rooms,
  appointment,
  initialLocalStart,
  canManage,
  onClose,
  onSaved,
}: {
  clinicId: string;
  timezone: string;
  clinicPath: string;
  professionals: AgendaProfessional[];
  rooms: AgendaRoom[];
  appointment: Appointment | null;
  initialLocalStart?: string;
  canManage: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(appointment === null);
  const [localStart, setLocalStart] = useState(
    appointment
      ? clinicLocalDateTimeInput(appointment.starts_at, timezone)
      : (initialLocalStart ?? ''),
  );
  const [duration, setDuration] = useState(
    appointment
      ? Math.max(
          5,
          Math.round(
            (Date.parse(appointment.ends_at) - Date.parse(appointment.starts_at)) / 60_000,
          ),
        )
      : 30,
  );
  const [patientId, setPatientId] = useState(appointment?.patient_id ?? '');
  const [professionalId, setProfessionalId] = useState(
    appointment?.professional_id ?? professionals[0]?.id ?? '',
  );
  const [roomId, setRoomId] = useState(appointment?.room_id ?? '');
  const [note, setNote] = useState(appointment?.administrative_note ?? '');
  const [patientSearch, setPatientSearch] = useState(appointment?.patient_name ?? '');
  const [patientOptions, setPatientOptions] = useState<Array<{ id: string; name: string }>>([]);
  const [history, setHistory] = useState<AppointmentHistoryList | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const selectedDay = localStart.slice(0, 10);

  useEffect(() => {
    if (patientSearch.trim().length < 2) {
      setPatientOptions([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void listPatients(clinicId, { search: patientSearch, status: 'ACTIVE', limit: 20 })
        .then((result) => {
          if (active) {
            setPatientOptions(
              result.items.map((patient) => ({
                id: patient.id,
                name: patient.social_name || patient.full_name,
              })),
            );
          }
        })
        .catch(() => {
          if (active) setPatientOptions([]);
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [clinicId, patientSearch]);

  useEffect(() => {
    if (!appointment) return;
    let active = true;
    setLoadingHistory(true);
    void listAppointmentHistory(clinicId, appointment.id)
      .then((result) => {
        if (active) setHistory(result);
      })
      .catch(() => {
        if (active) setHistory(null);
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => {
      active = false;
    };
  }, [appointment, clinicId]);

  useEffect(() => {
    if (appointment || selectedDay.length !== 10 || !professionalId) {
      setSuggestions([]);
      return;
    }
    let active = true;
    setLoadingSuggestions(true);
    void findAvailability(clinicId, {
      professional_id: professionalId,
      local_date: selectedDay,
      duration_minutes: duration,
      ...(patientId ? { patient_id: patientId } : {}),
      ...(roomId ? { room_id: roomId } : {}),
    })
      .then((result) => {
        if (active) {
          setSuggestions(
            result.starts_at.map((value) => clinicLocalDateTimeInput(value, timezone)),
          );
        }
      })
      .catch(() => {
        if (active) setSuggestions([]);
      })
      .finally(() => {
        if (active) setLoadingSuggestions(false);
      });
    return () => {
      active = false;
    };
  }, [appointment, clinicId, duration, patientId, professionalId, roomId, selectedDay, timezone]);

  const currentPatientName = useMemo(() => {
    if (patientId === appointment?.patient_id) return appointment.patient_name;
    return patientOptions.find((patient) => patient.id === patientId)?.name ?? '';
  }, [appointment, patientId, patientOptions]);

  const canReschedule =
    appointment !== null && canManage && ['SCHEDULED', 'CONFIRMED'].includes(appointment.status);
  const canEditAppointment =
    appointment !== null &&
    canManage &&
    ['SCHEDULED', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS'].includes(appointment.status);
  const canCancel =
    appointment !== null &&
    canManage &&
    ['SCHEDULED', 'CONFIRMED', 'CHECKED_IN'].includes(appointment.status);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      if (appointment) {
        const payload: AppointmentUpdateRequest = {
          expected_version: appointment.version,
          administrative_note: note.trim() || null,
        };
        if (canReschedule) {
          payload.patient_id = patientId;
          payload.professional_id = professionalId;
          payload.room_id = roomId || null;
          payload.local_start = localStart;
          payload.duration_minutes = duration;
        }
        await updateAppointment(clinicId, appointment.id, payload);
      } else {
        if (!patientId) {
          setError('Escolha um paciente ativo.');
          setPending(false);
          return;
        }
        await createAppointment(clinicId, {
          patient_id: patientId,
          professional_id: professionalId,
          room_id: roomId || null,
          local_start: localStart,
          duration_minutes: duration,
          administrative_note: note.trim() || null,
        });
      }
      onSaved();
      onClose();
    } catch (cause) {
      setError(readableError(cause));
      setPending(false);
    }
  }

  async function changeStatus(status: AppointmentStatus, cancellationReason?: string) {
    if (!appointment) return;
    setPending(true);
    setError(null);
    try {
      await setAppointmentStatus(clinicId, appointment.id, {
        expected_version: appointment.version,
        status,
        ...(status === 'CANCELLED' ? { cancellation_reason: cancellationReason } : {}),
      });
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
        aria-labelledby="appointment-dialog-title"
        className="app-panel my-auto max-h-[92vh] w-full max-w-2xl overflow-y-auto"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Agenda
            </p>
            <h2
              id="appointment-dialog-title"
              className="mt-1 text-lg font-semibold text-foreground"
            >
              {appointment
                ? editing
                  ? 'Editar ou remarcar consulta'
                  : 'Consulta'
                : 'Novo agendamento'}
            </h2>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </div>

        {appointment && !editing ? (
          <div className="mt-5 grid gap-5">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                tone={
                  appointment.status === 'COMPLETED'
                    ? 'success'
                    : appointment.status === 'CANCELLED' || appointment.status === 'NO_SHOW'
                      ? 'neutral'
                      : 'info'
                }
              >
                {statusLabels[appointment.status]}
              </StatusBadge>
              <span className="text-sm text-muted-foreground">
                {formatClinicTime(appointment.starts_at, timezone)}–
                {formatClinicTime(appointment.ends_at, timezone)}
                {' · '}
                {appointment.professional_name}
                {appointment.room_name ? ` · ${appointment.room_name}` : ''}
              </span>
            </div>
            <div className="rounded-md border border-border p-4">
              <p className="font-semibold text-foreground">{appointment.patient_name}</p>
              <Link
                className="mt-1 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline"
                href={`${clinicPath}/patients/${appointment.patient_id}` as Route}
              >
                Abrir ficha do paciente
              </Link>
              {appointment.administrative_note && (
                <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                  {appointment.administrative_note}
                </p>
              )}
              {appointment.cancellation_reason && (
                <p className="mt-3 text-sm text-muted-foreground">
                  Motivo do cancelamento: {appointment.cancellation_reason}
                </p>
              )}
            </div>
            {canManage && appointment.status === 'SCHEDULED' && (
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => void changeStatus('CONFIRMED')}
              >
                Confirmar consulta
              </Button>
            )}
            {canManage && ['SCHEDULED', 'CONFIRMED'].includes(appointment.status) && (
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => void changeStatus('CHECKED_IN')}
              >
                Registrar chegada
              </Button>
            )}
            {canManage && appointment.status === 'CHECKED_IN' && (
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => void changeStatus('IN_PROGRESS')}
              >
                Iniciar atendimento
              </Button>
            )}
            {canManage && appointment.status === 'IN_PROGRESS' && (
              <Button
                type="button"
                disabled={pending}
                onClick={() => void changeStatus('COMPLETED')}
              >
                Concluir atendimento
              </Button>
            )}
            {canManage &&
              ['SCHEDULED', 'CONFIRMED'].includes(appointment.status) &&
              Date.now() >= Date.parse(appointment.starts_at) && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => void changeStatus('NO_SHOW')}
                >
                  Marcar falta
                </Button>
              )}
            {canCancel && (
              <div className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-[1fr_auto]">
                <label className="grid gap-1 text-sm font-medium">
                  Motivo do cancelamento
                  <input
                    className="app-field"
                    maxLength={500}
                    value={cancelReason}
                    onChange={(event) => setCancelReason(event.target.value)}
                  />
                </label>
                <Button
                  type="button"
                  variant="outline"
                  className="self-end"
                  disabled={pending || !cancelReason.trim()}
                  onClick={() => void changeStatus('CANCELLED', cancelReason.trim())}
                >
                  Cancelar consulta
                </Button>
              </div>
            )}
            {canEditAppointment && (
              <Button type="button" variant="outline" onClick={() => setEditing(true)}>
                {canReschedule ? 'Editar ou remarcar' : 'Editar observação'}
              </Button>
            )}
            <section aria-label="Histórico de alterações" className="border-t border-border pt-4">
              <h3 className="text-sm font-semibold text-foreground">Histórico</h3>
              {loadingHistory ? (
                <p className="mt-2 text-sm text-muted-foreground" role="status">
                  Carregando histórico…
                </p>
              ) : history?.items.length ? (
                <ol className="mt-2 grid gap-2">
                  {history.items.map((entry) => (
                    <li key={entry.id} className="text-sm text-muted-foreground">
                      {eventLabel(entry.event_type)} ·{' '}
                      {new Intl.DateTimeFormat('pt-BR', {
                        timeZone: timezone,
                        dateStyle: 'short',
                        timeStyle: 'short',
                      }).format(new Date(entry.occurred_at))}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  Histórico indisponível ou ainda vazio.
                </p>
              )}
            </section>
          </div>
        ) : (
          <form className="mt-5 grid gap-4" onSubmit={(event) => void save(event)}>
            <label className="grid gap-1.5 text-sm font-medium">
              Buscar paciente ativo
              <input
                className="app-field"
                value={patientSearch}
                onChange={(event) => setPatientSearch(event.target.value)}
                placeholder="Digite o nome do paciente"
                required={!appointment}
                disabled={Boolean(appointment && !canReschedule)}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Paciente
              <select
                className="app-field"
                required={!appointment}
                disabled={Boolean(appointment && !canReschedule)}
                value={patientId}
                onChange={(event) => setPatientId(event.target.value)}
              >
                <option value="">Selecione um paciente</option>
                {patientId && !patientOptions.some((patient) => patient.id === patientId) && (
                  <option value={patientId}>
                    {currentPatientName || appointment?.patient_name || 'Paciente associado'}
                  </option>
                )}
                {patientOptions.map((patient) => (
                  <option key={patient.id} value={patient.id}>
                    {patient.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm font-medium">
                Profissional
                <select
                  className="app-field"
                  required
                  disabled={Boolean(appointment && !canReschedule)}
                  value={professionalId}
                  onChange={(event) => setProfessionalId(event.target.value)}
                >
                  {professionals.map((professional) => (
                    <option key={professional.id} value={professional.id}>
                      {professional.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1.5 text-sm font-medium">
                Sala (opcional)
                <select
                  className="app-field"
                  disabled={Boolean(appointment && !canReschedule)}
                  value={roomId}
                  onChange={(event) => setRoomId(event.target.value)}
                >
                  <option value="">Sem sala definida</option>
                  {rooms.map((room) => (
                    <option key={room.id} value={room.id}>
                      {room.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
              <label className="grid gap-1.5 text-sm font-medium">
                Data e hora local da clínica
                <input
                  className="app-field"
                  type="datetime-local"
                  required
                  disabled={Boolean(appointment && !canReschedule)}
                  value={localStart}
                  onChange={(event) => setLocalStart(event.target.value)}
                />
              </label>
              <label className="grid gap-1.5 text-sm font-medium">
                Duração (minutos)
                <input
                  className="app-field"
                  type="number"
                  min={5}
                  max={480}
                  step={5}
                  required
                  disabled={Boolean(appointment && !canReschedule)}
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                />
              </label>
            </div>
            {!appointment && (
              <div className="grid gap-2 rounded-md border border-border p-3">
                <p className="text-sm font-medium text-foreground">Horários livres sugeridos</p>
                {loadingSuggestions ? (
                  <p className="text-xs text-muted-foreground" role="status">
                    Buscando disponibilidade…
                  </p>
                ) : suggestions.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {suggestions.slice(0, 8).map((suggestion) => (
                      <Button
                        key={suggestion}
                        type="button"
                        variant={suggestion === localStart ? 'secondary' : 'outline'}
                        size="sm"
                        onClick={() => setLocalStart(suggestion)}
                      >
                        {suggestion.slice(11, 16)}
                      </Button>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Não há horários livres para estes filtros.
                  </p>
                )}
              </div>
            )}
            <label className="grid gap-1.5 text-sm font-medium">
              Observação administrativa (opcional)
              <textarea
                className="app-field min-h-20 resize-y"
                maxLength={2000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            {error && <Feedback tone="error">{error}</Feedback>}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={pending || professionals.length === 0}>
                {pending ? 'Salvando…' : appointment ? 'Salvar alterações' : 'Agendar consulta'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => (appointment ? setEditing(false) : onClose())}
              >
                Voltar
              </Button>
            </div>
          </form>
        )}
        {error && !editing && (
          <div className="mt-4">
            <Feedback tone="error">{error}</Feedback>
          </div>
        )}
      </section>
    </div>
  );
}
