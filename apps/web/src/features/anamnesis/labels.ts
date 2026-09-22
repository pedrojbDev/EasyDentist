import type { components } from '@/lib/api/generated/schema';

import type { AnswerState } from './answers';
import type { CatalogQuestion } from './catalog';

export type AnamnesisStatus = components['schemas']['AnamnesisStatus'];

const STATUS_LABELS: Record<AnamnesisStatus, string> = {
  DRAFT: 'Rascunho',
  FINAL: 'Concluída',
};

export const ANSWER_VALUE_LABELS: Record<string, string> = {
  YES: 'Sim',
  NO: 'Não',
  UNKNOWN: 'Não sabe',
};

export function anamnesisStatusLabel(status: AnamnesisStatus): string {
  return STATUS_LABELS[status] ?? status;
}

export function answerLabel(question: CatalogQuestion, answer: AnswerState): string {
  if (question.answer_type === 'TEXT') {
    return answer.text.trim() !== '' ? answer.text : '—';
  }
  const option = question.options.find((candidate) => candidate.id === answer.value);
  const base = option?.label ?? ANSWER_VALUE_LABELS[answer.value ?? ''] ?? answer.value ?? '—';
  const details = answer.details.trim();
  return details !== '' ? `${base} — ${details}` : base;
}

const dateFormatter = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' });
const dateTimeFormatter = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
});

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date);
}

export function authorLabel(
  name: string | null,
  croNumber: string | null,
  croState: string | null,
): string | null {
  if (name === null) {
    return null;
  }
  const cro =
    croNumber === null ? null : `CRO ${croNumber}${croState === null ? '' : `/${croState}`}`;
  return cro === null ? name : `${name} · ${cro}`;
}
