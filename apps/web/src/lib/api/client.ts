import { apiErrorFrom, readJsonBody } from './problem';
import { redirectToLogin } from './redirect';

type JsonInit = RequestInit & { json?: unknown; skipAuthRedirect?: boolean };

function buildInit(init: JsonInit): RequestInit {
  const { json, headers, skipAuthRedirect, ...rest } = init;
  void skipAuthRedirect;
  if (json === undefined) {
    return { ...rest, headers };
  }
  return {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(json),
  };
}

export async function apiFetch<T>(path: string, init: JsonInit = {}): Promise<T> {
  const response = await fetch(path, buildInit(init));
  const body = await readJsonBody(response);
  if (!response.ok) {
    const error = apiErrorFrom(response, body);
    if (error.status === 401 && init.skipAuthRedirect !== true) {
      redirectToLogin();
    }
    throw error;
  }
  return body as T;
}

export async function apiFetchVoid(path: string, init: JsonInit = {}): Promise<void> {
  await apiFetch(path, init);
}

export async function csrfHeaders(): Promise<Record<string, string>> {
  const { csrf_token } = await apiFetch<{ csrf_token: string }>('/api/v1/auth/csrf', {
    cache: 'no-store',
  });
  return { 'X-CSRF-Token': csrf_token };
}

export async function apiMutation<T>(
  method: string,
  path: string,
  json?: unknown,
  options: { skipAuthRedirect?: boolean } = {},
): Promise<T> {
  const headers = await csrfHeaders();
  return apiFetch<T>(path, { method, json, headers, ...options });
}

export async function apiMutationVoid(
  method: string,
  path: string,
  json?: unknown,
  options: { skipAuthRedirect?: boolean } = {},
): Promise<void> {
  await apiMutation(method, path, json, options);
}
