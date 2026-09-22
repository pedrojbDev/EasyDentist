import { UserRound } from 'lucide-react';
import Link from 'next/link';

import { StatusBadge } from '@/components/ui/status-badge';

import type { Patient } from '../api';
import { formatCpf } from '../cpf';
import { ageLabel, formatBirthDate, patientAge, patientStatusLabel } from '../labels';
import type { PatientCapabilities } from '../permissions';
import { PatientArchiveButton } from './PatientArchiveButton';

function PatientIdentity({ patient }: { patient: Patient }) {
  return (
    <span className="flex min-w-0 flex-col gap-0.5">
      <Link
        href={`/clinics/${patient.clinic_id}/patients/${patient.id}`}
        className="app-link font-semibold"
      >
        {patient.full_name}
      </Link>
      {patient.social_name !== null && (
        <span className="text-xs text-muted-foreground">{patient.social_name}</span>
      )}
      {patient.cpf !== null && (
        <span className="font-mono text-xs text-muted-foreground">{formatCpf(patient.cpf)}</span>
      )}
    </span>
  );
}

function PatientBirth({ patient }: { patient: Patient }) {
  const age = patientAge(patient.birth_date);
  return (
    <span className="flex flex-col">
      <span className="text-foreground">{formatBirthDate(patient.birth_date)}</span>
      {age !== null && <span className="text-xs text-muted-foreground">{ageLabel(age)}</span>}
    </span>
  );
}

function PatientContact({ patient }: { patient: Patient }) {
  return (
    <span className="flex min-w-0 flex-col">
      <span className="text-foreground">{patient.phone}</span>
      {patient.email !== null && (
        <span className="truncate text-xs text-muted-foreground">{patient.email}</span>
      )}
    </span>
  );
}

export function PatientTable({
  clinicId,
  patients,
  capabilities,
}: {
  clinicId: string;
  patients: Patient[];
  capabilities: PatientCapabilities;
}) {
  if (patients.length === 0) {
    return (
      <div className="app-panel flex min-h-44 flex-col items-center justify-center text-center">
        <UserRound aria-hidden="true" className="mb-3 size-8 text-muted-foreground" />
        <p className="font-medium text-foreground">Nenhum paciente encontrado.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Ajuste a busca ou cadastre um novo paciente.
        </p>
      </div>
    );
  }

  return (
    <section className="app-panel min-w-0">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[48rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/55 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="px-3 py-3">
                Paciente
              </th>
              <th scope="col" className="px-3 py-3">
                Contato
              </th>
              <th scope="col" className="px-3 py-3">
                Nascimento
              </th>
              <th scope="col" className="px-3 py-3">
                Situação
              </th>
              <th scope="col" className="px-3 py-3">
                Ações
              </th>
            </tr>
          </thead>
          <tbody>
            {patients.map((patient) => (
              <tr
                key={patient.id}
                className="border-b border-border align-middle last:border-b-0 hover:bg-muted/30"
              >
                <td className="px-3 py-3">
                  <PatientIdentity patient={patient} />
                </td>
                <td className="px-3 py-3">
                  <PatientContact patient={patient} />
                </td>
                <td className="px-3 py-3">
                  <PatientBirth patient={patient} />
                </td>
                <td className="px-3 py-3">
                  <StatusBadge tone={patient.status === 'ACTIVE' ? 'success' : 'neutral'}>
                    {patientStatusLabel(patient.status)}
                  </StatusBadge>
                </td>
                <td className="px-3 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/clinics/${clinicId}/patients/${patient.id}`}
                      className="app-link text-sm"
                    >
                      Ver
                    </Link>
                    {capabilities.canArchive && (
                      <PatientArchiveButton
                        clinicId={clinicId}
                        patientId={patient.id}
                        patientName={patient.full_name}
                        archived={patient.status === 'ARCHIVED'}
                      />
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
