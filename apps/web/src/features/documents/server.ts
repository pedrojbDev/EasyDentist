import { serverFetch } from '@/lib/api/server-client';

import type { DocumentList } from './api';

export async function listDocumentsOnServer(
  clinicId: string,
  patientId: string,
): Promise<DocumentList> {
  return serverFetch<DocumentList>(
    `/api/v1/clinics/${clinicId}/patients/${patientId}/documents?limit=100`,
  );
}
