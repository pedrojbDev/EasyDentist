export const GENERIC_ERROR_MESSAGE = 'Não foi possível concluir a operação. Tente novamente.';

const JSON_CONTENT_TYPES = ['application/json', 'application/problem+json'];

export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail?: string;
  readonly requestId?: string;
  readonly retryAfter?: number;

  constructor(init: {
    status: number;
    title: string;
    detail?: string;
    requestId?: string;
    retryAfter?: number;
  }) {
    super(init.title);
    this.name = 'ApiError';
    this.status = init.status;
    this.title = init.title;
    this.detail = init.detail;
    this.requestId = init.requestId;
    this.retryAfter = init.retryAfter;
  }
}

export async function readJsonBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!JSON_CONTENT_TYPES.some((accepted) => contentType.includes(accepted))) {
    return undefined;
  }
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

export function apiErrorFrom(response: Response, body: unknown): ApiError {
  const problem =
    typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  const retryAfterHeader = response.headers.get('retry-after');
  const parsedRetryAfter =
    retryAfterHeader === null ? Number.NaN : Number.parseInt(retryAfterHeader, 10);

  return new ApiError({
    status: response.status,
    title: nonEmptyString(problem.title) ?? GENERIC_ERROR_MESSAGE,
    detail: nonEmptyString(problem.detail),
    requestId: nonEmptyString(problem.request_id),
    retryAfter: Number.isFinite(parsedRetryAfter) ? parsedRetryAfter : undefined,
  });
}
