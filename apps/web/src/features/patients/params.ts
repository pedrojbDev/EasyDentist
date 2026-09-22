export const PATIENT_PAGE_SIZE = 20;
export const PATIENT_SEARCH_MAX_LENGTH = 120;

export type PatientListStatus = 'ACTIVE' | 'ARCHIVED';

export type PatientListQuery = {
  search: string | null;
  status: PatientListStatus;
  limit: number;
  offset: number;
  page: number;
};

type RawSearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

export function parsePatientListParams(raw: RawSearchParams): PatientListQuery {
  const searchValue = firstValue(raw.search)?.trim().slice(0, PATIENT_SEARCH_MAX_LENGTH);
  const status: PatientListStatus = firstValue(raw.status) === 'ARCHIVED' ? 'ARCHIVED' : 'ACTIVE';
  const parsedPage = Number.parseInt(firstValue(raw.page) ?? '1', 10);
  const page = Number.isFinite(parsedPage) && parsedPage >= 1 ? parsedPage : 1;
  return {
    search: searchValue ? searchValue : null,
    status,
    limit: PATIENT_PAGE_SIZE,
    offset: (page - 1) * PATIENT_PAGE_SIZE,
    page,
  };
}

export function patientListHref(
  clinicId: string,
  query: { search?: string | null; status?: PatientListStatus; page?: number },
): string {
  const params = new URLSearchParams();
  if (query.search) {
    params.set('search', query.search);
  }
  if (query.status === 'ARCHIVED') {
    params.set('status', 'ARCHIVED');
  }
  if (query.page !== undefined && query.page > 1) {
    params.set('page', String(query.page));
  }
  const queryString = params.toString();
  const base = `/clinics/${clinicId}/patients`;
  return queryString ? `${base}?${queryString}` : base;
}
