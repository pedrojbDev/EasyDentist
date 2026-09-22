import { NextResponse, type NextRequest } from 'next/server';

import { CSP_HEADER_NAME, buildSecurityHeaders, generateNonce } from '@/lib/security-headers';
import { logServerEvent } from '@/lib/server-logging';

export function middleware(request: NextRequest): NextResponse {
  const nonce = generateNonce();
  const requestId = crypto.randomUUID();
  const headers = buildSecurityHeaders(nonce, {
    production: process.env.APP_ENV === 'production',
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  requestHeaders.set('x-request-id', requestId);
  requestHeaders.set(CSP_HEADER_NAME, headers[CSP_HEADER_NAME]);

  logServerEvent('INFO', {
    event: 'http.request',
    requestId,
    method: request.method,
    route: request.nextUrl.pathname,
  });

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set('x-request-id', requestId);
  for (const [name, value] of Object.entries(headers)) {
    response.headers.set(name, value);
  }
  return response;
}

export const config = {
  // The API rewrite must stay out of this middleware so the response keeps the
  // API-owned headers instead of receiving the document CSP.
  matcher: ['/((?!api/v1|_next/static|_next/image|favicon.ico).*)'],
};
