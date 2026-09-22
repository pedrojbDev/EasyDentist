import type { DocumentCategory, DocumentStatus } from './api';

const CATEGORY_LABELS: Record<DocumentCategory, string> = {
  ADMINISTRATIVE: 'Administrativo',
  CLINICAL: 'Clínico',
};

const STATUS_LABELS: Record<DocumentStatus, string> = {
  ACTIVE: 'Ativo',
  ARCHIVED: 'Arquivado',
};

export function categoryLabel(category: DocumentCategory): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function statusLabel(status: DocumentStatus): string {
  return STATUS_LABELS[status] ?? status;
}

const SIZE_UNITS = ['KB', 'MB', 'GB'];

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return bytes === 1 ? '1 byte' : `${bytes} bytes`;
  }
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < SIZE_UNITS.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const rounded = Math.round(value * 10) / 10;
  return `${rounded.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${SIZE_UNITS[unitIndex]}`;
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
