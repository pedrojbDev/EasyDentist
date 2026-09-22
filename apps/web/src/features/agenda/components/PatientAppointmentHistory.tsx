import Link from 'next/link';

import { StatusBadge } from '@/components/ui/status-badge';

import type { AppointmentStatus } from '../api';

const labels: Record<AppointmentStatus, string> = {
  SCHEDULED: 'Agendada',
  CONFIRMED: 'Confirmada',
  CHECKED_IN: 'Chegou',
  IN_PROGRESS: 'Em atendimento',
  COMPLETED: 'Concluída',
  CANCELLED: 'Cancelada',
  NO_SHOW: 'Faltou',
};

export function PatientAppointmentHistory({
  clinicId,
  timezone,
  appointments,
}: {
  clinicId: string;
  timezone: string;
  appointments: Array<{
    id: string;
    starts_at: string;
    professional_name: string;
    room_name: string | null;
    status: AppointmentStatus;
  }>;
}) {
  return (
    <section className="app-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-foreground">Histórico de consultas</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Registros da agenda, sem incluir anotações clínicas.
          </p>
        </div>
        <Link
          className="text-sm font-semibold text-primary underline-offset-4 hover:underline"
          href={`/clinics/${clinicId}/agenda`}
        >
          Abrir agenda
        </Link>
      </div>
      {appointments.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Este paciente ainda não tem consultas registradas.
        </p>
      ) : (
        <ol className="mt-4 divide-y divide-border">
          {appointments.map((appointment) => (
            <li
              key={appointment.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3"
            >
              <div>
                <p className="text-sm font-medium text-foreground">
                  {new Intl.DateTimeFormat('pt-BR', {
                    timeZone: timezone,
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  }).format(new Date(appointment.starts_at))}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {appointment.professional_name}
                  {appointment.room_name ? ` · ${appointment.room_name}` : ''}
                </p>
              </div>
              <StatusBadge
                tone={
                  appointment.status === 'COMPLETED'
                    ? 'success'
                    : appointment.status === 'CANCELLED' || appointment.status === 'NO_SHOW'
                      ? 'neutral'
                      : 'info'
                }
              >
                {labels[appointment.status]}
              </StatusBadge>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
