'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Plus, RefreshCw, Settings2 } from 'lucide-react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
import type { Member, Role } from '@/features/members/api';
import { ApiError } from '@/lib/api/problem';

import {
  listAllAppointments,
  listScheduleBlocks,
  type AgendaProfessional,
  type AgendaRoom,
  type Appointment,
  type AppointmentStatus,
  type ScheduleBlock,
} from '../api';
import {
  addLocalDays,
  clinicDateRange,
  clinicLocalDate,
  clinicLocalInstant,
  clinicToday,
  formatClinicDate,
  formatClinicTime,
  startOfClinicWeek,
} from '../date-utils';
import { AppointmentDialog } from './AppointmentDialog';
import { ScheduleBlockDialog } from './ScheduleBlockDialog';

const statusLabels: Record<AppointmentStatus, string> = {
  SCHEDULED: 'Agendada',
  CONFIRMED: 'Confirmada',
  CHECKED_IN: 'Chegou',
  IN_PROGRESS: 'Em atendimento',
  COMPLETED: 'Concluída',
  CANCELLED: 'Cancelada',
  NO_SHOW: 'Faltou',
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 403)
    return 'Seu papel não permite consultar esta agenda.';
  if (error instanceof ApiError && error.status === 404)
    return 'A clínica ou um recurso da agenda não foi encontrado.';
  if (error instanceof ApiError && error.status === 409)
    return 'A agenda foi atualizada. Atualize para ver os horários disponíveis.';
  return 'Não foi possível carregar a agenda. Tente atualizar.';
}

function dateTitle(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat('pt-BR', {
    timeZone,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(clinicLocalInstant(value, timeZone));
}

function statusTone(status: AppointmentStatus): 'neutral' | 'info' | 'success' | 'warning' {
  if (status === 'COMPLETED') return 'success';
  if (status === 'CANCELLED' || status === 'NO_SHOW') return 'neutral';
  if (status === 'IN_PROGRESS') return 'warning';
  return 'info';
}

export function AgendaCalendar({
  clinicId,
  clinicPath,
  timezone,
  role,
  currentUserId,
  professionals,
  rooms,
  members,
}: {
  clinicId: string;
  clinicPath: string;
  timezone: string;
  role: Role;
  currentUserId: string;
  professionals: AgendaProfessional[];
  rooms: AgendaRoom[];
  members: Member[];
}) {
  const [selectedDate, setSelectedDate] = useState(() => clinicToday(timezone));
  const [view, setView] = useState<'day' | 'week'>('day');
  const [professionalFilter, setProfessionalFilter] = useState('');
  const [roomFilter, setRoomFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<AppointmentStatus | ''>('');
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [appointmentDialog, setAppointmentDialog] = useState<{
    appointment: Appointment | null;
    localStart?: string;
  } | null>(null);
  const [blockDialog, setBlockDialog] = useState<{
    block: ScheduleBlock | null;
    localStart?: string;
  } | null>(null);

  const ownMembership = members.find(
    (member) => member.user_id === currentUserId && member.status === 'ACTIVE',
  );
  const ownProfessional = professionals.find(
    (professional) => professional.membership_id === ownMembership?.id,
  );
  const editableProfessionals =
    role === 'DENTIST' ? (ownProfessional ? [ownProfessional] : []) : professionals;
  const canManage = role !== 'ASSISTANT';
  const selectedRange = useMemo(
    () => clinicDateRange(selectedDate, view, timezone),
    [selectedDate, timezone, view],
  );
  const visibleAppointments = useMemo(
    () =>
      appointments.filter(
        (appointment) =>
          (!professionalFilter || appointment.professional_id === professionalFilter) &&
          (!roomFilter || appointment.room_id === roomFilter) &&
          (!statusFilter || appointment.status === statusFilter),
      ),
    [appointments, professionalFilter, roomFilter, statusFilter],
  );
  const visibleBlocks = useMemo(
    () =>
      blocks.filter(
        (block) =>
          (!professionalFilter || block.professional_id === professionalFilter) &&
          (!roomFilter || block.room_id === roomFilter),
      ),
    [blocks, professionalFilter, roomFilter],
  );

  const refreshAgenda = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const appointmentItems = await listAllAppointments(clinicId, {
        starts_at: selectedRange.starts_at,
        ends_at: selectedRange.ends_at,
        ...(professionalFilter ? { professional_id: professionalFilter } : {}),
        ...(roomFilter ? { room_id: roomFilter } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
      });
      const blockItems: ScheduleBlock[] = [];
      let offset = 0;
      let total = 0;
      do {
        const page = await listScheduleBlocks(clinicId, {
          starts_at: selectedRange.starts_at,
          ends_at: selectedRange.ends_at,
          ...(professionalFilter ? { professional_id: professionalFilter } : {}),
          ...(roomFilter ? { room_id: roomFilter } : {}),
          limit: 100,
          offset,
        });
        blockItems.push(...page.items);
        total = page.total;
        offset += page.items.length;
      } while (offset < total);
      setAppointments(appointmentItems);
      setBlocks(blockItems);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [clinicId, professionalFilter, roomFilter, selectedRange, statusFilter]);

  useEffect(() => {
    void refreshAgenda();
  }, [refreshAgenda, reload]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void refreshAgenda();
    };
    const refreshOnFocus = () => void refreshAgenda();
    window.addEventListener('focus', refreshOnFocus);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refreshAgenda();
    }, 60_000);
    return () => {
      window.removeEventListener('focus', refreshOnFocus);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      window.clearInterval(timer);
    };
  }, [refreshAgenda]);

  const appointmentsForDay = (day: string) =>
    visibleAppointments.filter(
      (appointment) => clinicLocalDate(appointment.starts_at, timezone) === day,
    );
  const blocksForDay = (day: string) =>
    visibleBlocks.filter((block) => {
      const dayStarts = clinicLocalInstant(day, timezone).getTime();
      const dayEnds = clinicLocalInstant(addLocalDays(day, 1), timezone).getTime();
      return Date.parse(block.starts_at) < dayEnds && Date.parse(block.ends_at) > dayStarts;
    });

  function moveDate(offset: number) {
    setSelectedDate((current) => addLocalDays(current, view === 'week' ? offset * 7 : offset));
  }

  function openAppointmentAt(day: string, hour = '09:00') {
    setAppointmentDialog({ appointment: null, localStart: `${day}T${hour}` });
  }

  function dayEvents(day: string) {
    const dayStartsAt = clinicLocalInstant(day, timezone).getTime();
    const dayEndsAt = clinicLocalInstant(addLocalDays(day, 1), timezone).getTime();
    return [
      ...appointmentsForDay(day).map((appointment) => ({
        kind: 'appointment' as const,
        startsAt: appointment.starts_at,
        endsAt: appointment.ends_at,
        appointment,
      })),
      ...blocksForDay(day).map((block) => ({
        kind: 'block' as const,
        startsAt: new Date(Math.max(Date.parse(block.starts_at), dayStartsAt)).toISOString(),
        endsAt: new Date(Math.min(Date.parse(block.ends_at), dayEndsAt)).toISOString(),
        block,
      })),
    ].sort((left, right) => left.startsAt.localeCompare(right.startsAt));
  }

  function renderDayItems(day: string) {
    const events = dayEvents(day);
    if (events.length === 0) {
      return (
        <p className="py-4 text-sm text-muted-foreground">
          Nenhum atendimento ou bloqueio neste dia.
        </p>
      );
    }
    return (
      <ul className="grid gap-2">
        {events.map((event) =>
          event.kind === 'appointment' ? (
            <li key={event.appointment.id}>
              <button
                type="button"
                className="flex w-full flex-col gap-1 rounded-lg border border-border bg-surface px-3 py-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/30 sm:flex-row sm:items-center sm:justify-between"
                onClick={() => setAppointmentDialog({ appointment: event.appointment })}
              >
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-foreground">
                    {event.appointment.patient_name}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {event.appointment.professional_name}
                    {event.appointment.room_name ? ` · ${event.appointment.room_name}` : ''}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="text-sm tabular-nums text-muted-foreground">
                    {formatClinicTime(event.appointment.starts_at, timezone)}–
                    {formatClinicTime(event.appointment.ends_at, timezone)}
                  </span>
                  <StatusBadge tone={statusTone(event.appointment.status)}>
                    {statusLabels[event.appointment.status]}
                  </StatusBadge>
                </span>
              </button>
            </li>
          ) : (
            <li key={event.block.id}>
              <button
                type="button"
                className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed border-warning/50 bg-warning/5 px-3 py-3 text-left hover:bg-warning/10"
                onClick={() =>
                  canManage &&
                  (role !== 'DENTIST' || event.block.professional_id === ownProfessional?.id) &&
                  setBlockDialog({ block: event.block })
                }
              >
                <span className="font-medium text-foreground">
                  {event.block.label || 'Horário bloqueado'}
                </span>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {formatClinicTime(event.startsAt, timezone)}–
                  {formatClinicTime(event.endsAt, timezone)}
                </span>
              </button>
            </li>
          ),
        )}
      </ul>
    );
  }

  function isBusy(day: string, localTime: string): boolean {
    try {
      const start = clinicLocalInstant(`${day}T${localTime}`, timezone);
      const end = new Date(start.getTime() + 30 * 60_000);
      return dayEvents(day).some((event) => {
        if (
          event.kind === 'appointment' &&
          ['CANCELLED', 'NO_SHOW'].includes(event.appointment.status)
        ) {
          return false;
        }
        return (
          Date.parse(event.startsAt) < end.getTime() && Date.parse(event.endsAt) > start.getTime()
        );
      });
    } catch {
      return true;
    }
  }

  const weekdays = selectedRange.days;
  const weekStart = startOfClinicWeek(selectedDate);
  const slots = Array.from({ length: 22 }, (_, index) => {
    const minutes = 8 * 60 + index * 30;
    return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  });

  return (
    <div className="grid gap-5">
      <section className="app-panel grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSelectedDate(clinicToday(timezone))}
            >
              Hoje
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Período anterior"
              onClick={() => moveDate(-1)}
            >
              <ChevronLeft aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Próximo período"
              onClick={() => moveDate(1)}
            >
              <ChevronRight aria-hidden="true" />
            </Button>
            <label className="sr-only" htmlFor="agenda-date">
              Data selecionada
            </label>
            <input
              id="agenda-date"
              className="app-field w-40"
              type="date"
              value={selectedDate}
              onChange={(event) => setSelectedDate(event.target.value)}
            />
            <span className="hidden text-sm font-medium capitalize text-muted-foreground sm:inline">
              {view === 'week'
                ? `Semana de ${formatClinicDate(weekStart, timezone)}`
                : dateTitle(selectedDate, timezone)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant={view === 'day' ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={view === 'day'}
              onClick={() => setView('day')}
            >
              Dia
            </Button>
            <Button
              type="button"
              variant={view === 'week' ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={view === 'week'}
              onClick={() => setView('week')}
            >
              Semana
            </Button>
          </div>
        </div>
        <div className="grid gap-3 border-t border-border pt-4 sm:grid-cols-3">
          <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
            Profissional
            <select
              className="app-field min-h-9 text-sm text-foreground"
              value={professionalFilter}
              onChange={(event) => setProfessionalFilter(event.target.value)}
            >
              <option value="">Todos</option>
              {professionals.map((professional) => (
                <option key={professional.id} value={professional.id}>
                  {professional.name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
            Sala
            <select
              className="app-field min-h-9 text-sm text-foreground"
              value={roomFilter}
              onChange={(event) => setRoomFilter(event.target.value)}
            >
              <option value="">Todas</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
            Estado da consulta
            <select
              className="app-field min-h-9 text-sm text-foreground"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as AppointmentStatus | '')}
            >
              <option value="">Todos</option>
              {(Object.keys(statusLabels) as AppointmentStatus[]).map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          {canManage && (
            <>
              <Button
                type="button"
                onClick={() => openAppointmentAt(selectedDate)}
                disabled={editableProfessionals.length === 0}
              >
                <Plus aria-hidden="true" /> Novo agendamento
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setBlockDialog({ block: null, localStart: `${selectedDate}T09:00` })}
              >
                Bloquear horário
              </Button>
            </>
          )}
          <Button
            type="button"
            variant="ghost"
            disabled={refreshing}
            onClick={() => setReload((value) => value + 1)}
          >
            <RefreshCw aria-hidden="true" className={refreshing ? 'animate-spin' : ''} /> Atualizar
          </Button>
          <Link
            className="ml-auto inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold text-muted-foreground hover:bg-accent hover:text-foreground"
            href={`${clinicPath}/agenda/resources`}
          >
            <Settings2 aria-hidden="true" className="size-4" /> Profissionais e salas
          </Link>
        </div>
      </section>

      {error && <Feedback tone="error">{error}</Feedback>}
      {loading ? (
        <section
          className="app-panel py-10 text-center text-sm text-muted-foreground"
          role="status"
        >
          Carregando agenda…
        </section>
      ) : professionals.length === 0 ? (
        <section className="app-panel grid justify-items-start gap-3">
          <CalendarDays aria-hidden="true" className="size-7 text-muted-foreground" />
          <h2 className="font-semibold text-foreground">Configure um profissional para começar</h2>
          <p className="text-sm text-muted-foreground">
            A agenda só aceita consultas depois do cadastro e da configuração dos horários semanais.
          </p>
          <Button asChild>
            <Link href={`${clinicPath}/agenda/resources`}>
              Cadastrar profissionais e expediente
            </Link>
          </Button>
        </section>
      ) : (
        <>
          <section className="app-panel md:hidden">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold capitalize text-foreground">
                {dateTitle(selectedDate, timezone)}
              </h2>
              {canManage && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={editableProfessionals.length === 0}
                  onClick={() => openAppointmentAt(selectedDate)}
                >
                  <Plus aria-hidden="true" /> Novo
                </Button>
              )}
            </div>
            {renderDayItems(selectedDate)}
            {canManage && (
              <div className="mt-4 grid grid-cols-3 gap-2 border-t border-border pt-4 sm:grid-cols-4">
                {slots
                  .filter((_, index) => index % 2 === 0)
                  .map((slot) => (
                    <Button
                      key={slot}
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={isBusy(selectedDate, slot)}
                      onClick={() => openAppointmentAt(selectedDate, slot)}
                    >
                      {slot}
                    </Button>
                  ))}
              </div>
            )}
          </section>

          {view === 'day' ? (
            <section className="app-panel hidden md:block">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="font-semibold capitalize text-foreground">
                  {dateTitle(selectedDate, timezone)}
                </h2>
                {canManage && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setBlockDialog({ block: null, localStart: `${selectedDate}T09:00` })
                    }
                  >
                    Adicionar bloqueio
                  </Button>
                )}
              </div>
              {renderDayItems(selectedDate)}
              {canManage && (
                <div className="mt-4 grid grid-cols-[repeat(11,minmax(0,1fr))] gap-1 border-t border-border pt-4">
                  {slots
                    .filter((_, index) => index % 2 === 0)
                    .map((slot) => (
                      <Button
                        key={slot}
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={isBusy(selectedDate, slot)}
                        onClick={() => openAppointmentAt(selectedDate, slot)}
                      >
                        {slot}
                      </Button>
                    ))}
                </div>
              )}
            </section>
          ) : (
            <section className="hidden gap-2 md:grid md:grid-cols-7">
              {weekdays.map((day) => (
                <article key={day} className="app-panel min-w-0 px-3 py-3">
                  <button
                    type="button"
                    className="mb-3 w-full text-left"
                    onClick={() => {
                      setSelectedDate(day);
                      setView('day');
                    }}
                  >
                    <span className="block text-xs font-semibold uppercase text-muted-foreground">
                      {formatClinicDate(day, timezone).split(',')[0]}
                    </span>
                    <span className="mt-1 block text-sm font-semibold text-foreground">
                      {dateTitle(day, timezone).split(' de ').slice(0, 2).join(' de ')}
                    </span>
                  </button>
                  <div className="grid gap-2">
                    {dayEvents(day).map((event) =>
                      event.kind === 'appointment' ? (
                        <button
                          key={event.appointment.id}
                          type="button"
                          className="grid gap-1 rounded-md border border-border p-2 text-left hover:border-primary/40"
                          onClick={() => setAppointmentDialog({ appointment: event.appointment })}
                        >
                          <span className="text-xs tabular-nums text-muted-foreground">
                            {formatClinicTime(event.startsAt, timezone)}
                          </span>
                          <span className="line-clamp-2 text-xs font-semibold text-foreground">
                            {event.appointment.patient_name}
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            {event.appointment.professional_name}
                          </span>
                        </button>
                      ) : (
                        <button
                          key={event.block.id}
                          type="button"
                          className="rounded-md border border-dashed border-warning/50 bg-warning/5 p-2 text-left text-xs"
                          onClick={() =>
                            canManage &&
                            (role !== 'DENTIST' ||
                              event.block.professional_id === ownProfessional?.id) &&
                            setBlockDialog({ block: event.block })
                          }
                        >
                          <span className="block tabular-nums text-muted-foreground">
                            {formatClinicTime(event.startsAt, timezone)}–
                            {formatClinicTime(event.endsAt, timezone)}
                          </span>
                          <span className="mt-1 block font-medium text-foreground">
                            {event.block.label || 'Bloqueado'}
                          </span>
                        </button>
                      ),
                    )}
                  </div>
                  {canManage && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="mt-3 w-full"
                      onClick={() => openAppointmentAt(day)}
                    >
                      <Plus aria-hidden="true" /> 09:00
                    </Button>
                  )}
                </article>
              ))}
            </section>
          )}
        </>
      )}

      {appointmentDialog && (
        <AppointmentDialog
          clinicId={clinicId}
          timezone={timezone}
          clinicPath={clinicPath}
          professionals={editableProfessionals}
          rooms={rooms}
          appointment={appointmentDialog.appointment}
          initialLocalStart={appointmentDialog.localStart}
          canManage={
            canManage &&
            (role !== 'DENTIST' ||
              appointmentDialog.appointment?.professional_id === ownProfessional?.id ||
              appointmentDialog.appointment === null)
          }
          onClose={() => setAppointmentDialog(null)}
          onSaved={() => setReload((value) => value + 1)}
        />
      )}
      {blockDialog && (
        <ScheduleBlockDialog
          clinicId={clinicId}
          timezone={timezone}
          professionals={editableProfessionals}
          rooms={rooms}
          block={blockDialog.block}
          allowRoomOnly={role !== 'DENTIST'}
          initialLocalStart={blockDialog.localStart}
          onClose={() => setBlockDialog(null)}
          onSaved={() => setReload((value) => value + 1)}
        />
      )}
    </div>
  );
}
