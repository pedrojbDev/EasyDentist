import type { PatientDocument } from './api';

export function makeDocument(overrides: Partial<PatientDocument> = {}): PatientDocument {
  return {
    id: 'd1',
    clinic_id: 'c1',
    patient_id: 'p1',
    category: 'CLINICAL',
    title: 'Laudo clínico',
    original_filename: 'laudo.pdf',
    detected_mime: 'application/pdf',
    size_bytes: 2048,
    sha256: 'a'.repeat(64),
    uploaded_by_user_id: 'u1',
    status: 'ACTIVE',
    archived_at: null,
    created_at: '2026-09-20T12:00:00Z',
    updated_at: '2026-09-20T12:00:00Z',
    ...overrides,
  };
}
