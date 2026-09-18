import { cookies } from 'next/headers';

import { apiErrorFrom, readJsonBody } from './problem';

function internalBaseUrl(): string {
  return process.env.API_INTERNAL_BASE_URL ?? 'http://localhost:8000';
}

export async function serverFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join('; ');
  const response = await fetch(`${internalBaseUrl()}${path}`, {
    headers: cookieHeader.length > 0 ? { Cookie: cookieHeader } : {},
    cache: 'no-store',
  });
  const body = await readJsonBody(response);
  if (!response.ok) {
    throw apiErrorFrom(response, body);
  }
  return body as T;
}
