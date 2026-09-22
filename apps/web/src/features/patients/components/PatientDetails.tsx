import type { ReactNode } from 'react';

import type { Patient } from '../api';
import { formatCpf } from '../cpf';
import { ageLabel, formatBirthDate, formatDate, patientAge } from '../labels';

function InfoItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm text-foreground">{value ?? '—'}</dd>
    </div>
  );
}

function addressLine(patient: Patient): string | null {
  const street = [patient.street, patient.number].filter(Boolean).join(', ');
  const parts = [street, patient.complement, patient.district].filter((part): part is string =>
    Boolean(part),
  );
  const city = [patient.city, patient.state].filter(Boolean).join(' - ');
  if (city) {
    parts.push(city);
  }
  if (patient.postal_code) {
    parts.push(`CEP ${patient.postal_code}`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

export function PatientDetails({ patient }: { patient: Patient }) {
  const age = patientAge(patient.birth_date);
  const guardian =
    [patient.guardian_name, patient.guardian_relationship, patient.guardian_phone]
      .filter(Boolean)
      .join(' · ') || null;
  const emergency =
    [
      patient.emergency_contact_name,
      patient.emergency_contact_relationship,
      patient.emergency_contact_phone,
    ]
      .filter(Boolean)
      .join(' · ') || null;

  return (
    <div className="flex flex-col gap-5">
      <section className="app-panel flex flex-col gap-4">
        <h2 className="font-semibold text-foreground">Identificação</h2>
        <dl className="grid gap-4 sm:grid-cols-2">
          <InfoItem label="Nome completo" value={patient.full_name} />
          <InfoItem label="Nome social" value={patient.social_name} />
          <InfoItem
            label="Data de nascimento"
            value={`${formatBirthDate(patient.birth_date)}${age !== null ? ` (${ageLabel(age)})` : ''}`}
          />
          <InfoItem label="CPF" value={patient.cpf ? formatCpf(patient.cpf) : null} />
          <InfoItem label="Ocupação" value={patient.occupation} />
          <InfoItem label="Nacionalidade" value={patient.nationality} />
          <InfoItem label="Naturalidade" value={patient.birthplace} />
        </dl>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <h2 className="font-semibold text-foreground">Contato e endereço</h2>
        <dl className="grid gap-4 sm:grid-cols-2">
          <InfoItem label="Telefone principal" value={patient.phone} />
          <InfoItem label="Telefone secundário" value={patient.phone_secondary} />
          <InfoItem label="E-mail" value={patient.email} />
          <InfoItem label="Endereço" value={addressLine(patient)} />
          <InfoItem label="Responsável legal" value={guardian} />
          <InfoItem label="Contato de emergência" value={emergency} />
        </dl>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <h2 className="font-semibold text-foreground">Observações administrativas</h2>
        <p className="whitespace-pre-line text-sm text-foreground">
          {patient.administrative_notes ?? 'Nenhuma observação registrada.'}
        </p>
      </section>

      <section className="app-panel flex flex-col gap-2 text-sm">
        <h2 className="font-semibold text-foreground">Registro</h2>
        <p className="text-muted-foreground">
          Cadastrado em {formatDate(patient.created_at)} · Atualizado em{' '}
          {formatDate(patient.updated_at)}
        </p>
      </section>
    </div>
  );
}
