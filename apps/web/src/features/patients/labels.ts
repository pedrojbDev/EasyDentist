import type { PatientAlertKind, PatientAlertStatus, PatientStatus } from './api';

const PATIENT_STATUS_LABELS: Record<PatientStatus, string> = {
  ACTIVE: 'Ativo',
  ARCHIVED: 'Arquivado',
};

const ALERT_KIND_LABELS: Record<PatientAlertKind, string> = {
  ALLERGY: 'Alergia',
  MEDICATION: 'Medicação',
  CLINICAL_RISK: 'Risco clínico',
  OTHER: 'Outro',
};

const ALERT_STATUS_LABELS: Record<PatientAlertStatus, string> = {
  ACTIVE: 'Ativo',
  RESOLVED: 'Resolvido',
};

export function patientStatusLabel(status: PatientStatus): string {
  return PATIENT_STATUS_LABELS[status] ?? status;
}

export function alertKindLabel(kind: PatientAlertKind): string {
  return ALERT_KIND_LABELS[kind] ?? kind;
}

export function alertStatusLabel(status: PatientAlertStatus): string {
  return ALERT_STATUS_LABELS[status] ?? status;
}

const dateFormatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' });

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

export function formatBirthDate(value: string): string {
  const [year, month, day] = value.split('-');
  if (!year || !month || !day) {
    return value;
  }
  return `${day}/${month}/${year}`;
}

export function patientAge(birthDate: string, today: Date = new Date()): number | null {
  const [year, month, day] = birthDate.split('-').map(Number);
  if (!year || !month || !day) {
    return null;
  }
  let age = today.getFullYear() - year;
  const beforeBirthday =
    today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day);
  if (beforeBirthday) {
    age -= 1;
  }
  return age >= 0 ? age : null;
}

export function ageLabel(age: number): string {
  return age === 1 ? '1 ano' : `${age} anos`;
}
