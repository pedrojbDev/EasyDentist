import { apiFetch, apiMutation, csrfHeaders } from '@/lib/api/client';
import { ApiError, GENERIC_ERROR_MESSAGE } from '@/lib/api/problem';
import type { components } from '@/lib/api/generated/schema';

export type PatientDocument = components['schemas']['DocumentResponse'];
export type DocumentCategory = components['schemas']['DocumentCategory'];
export type DocumentStatus = components['schemas']['DocumentStatus'];
export type DocumentList = components['schemas']['DocumentListResponse'];

export type DocumentListRequest = {
  category?: DocumentCategory;
  status?: DocumentStatus;
  limit?: number;
  offset?: number;
};

export type DocumentUploadRequest = {
  file: File;
  title: string;
  category: DocumentCategory;
};

function queryString(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') {
      query.set(key, String(value));
    }
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
}

export function documentsPath(clinicId: string, patientId: string): string {
  return `/api/v1/clinics/${clinicId}/patients/${patientId}/documents`;
}

export function documentPath(clinicId: string, patientId: string, documentId: string): string {
  return `${documentsPath(clinicId, patientId)}/${documentId}`;
}

export function downloadDocumentUrl(
  clinicId: string,
  patientId: string,
  documentId: string,
): string {
  return `${documentPath(clinicId, patientId, documentId)}/content`;
}

export async function listDocuments(
  clinicId: string,
  patientId: string,
  params: DocumentListRequest = {},
): Promise<DocumentList> {
  return apiFetch<DocumentList>(
    `${documentsPath(clinicId, patientId)}${queryString({
      category: params.category,
      status: params.status,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export async function uploadDocument(
  clinicId: string,
  patientId: string,
  request: DocumentUploadRequest,
): Promise<PatientDocument> {
  const headers = await csrfHeaders();
  const body = new FormData();
  body.append('file', request.file);
  body.append('title', request.title);
  body.append('category', request.category);
  return apiFetch<PatientDocument>(documentsPath(clinicId, patientId), {
    method: 'POST',
    body,
    headers,
  });
}

export async function archiveDocument(
  clinicId: string,
  patientId: string,
  documentId: string,
): Promise<PatientDocument> {
  return apiMutation<PatientDocument>(
    'POST',
    `${documentPath(clinicId, patientId, documentId)}/archive`,
  );
}

export async function restoreDocument(
  clinicId: string,
  patientId: string,
  documentId: string,
): Promise<PatientDocument> {
  return apiMutation<PatientDocument>(
    'POST',
    `${documentPath(clinicId, patientId, documentId)}/restore`,
  );
}

export function documentErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Seu papel não permite gerenciar documentos desta categoria.';
    }
    if (error.status === 404) {
      return 'Documento ou paciente não encontrado. Atualize a página.';
    }
    if (error.status === 413) {
      return 'O arquivo excede o limite de 10 MB.';
    }
    if (error.status === 415) {
      return 'Formato não aceito. Envie um arquivo PDF, JPEG ou PNG.';
    }
    if (error.status === 503) {
      return 'O armazenamento de documentos está indisponível. Tente novamente em instantes.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
    return error.title || GENERIC_ERROR_MESSAGE;
  }
  return GENERIC_ERROR_MESSAGE;
}
