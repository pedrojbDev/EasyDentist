export type ServerLogLevel = 'INFO' | 'WARN' | 'ERROR';

export type ServerLogContext = {
  event: string;
  request_id?: string;
  method?: string;
  route?: string;
  status_code?: number;
  duration_ms?: number;
  error_type?: string;
};

const UUID_PATTERN = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

export function normalizeRoute(pathname: string): string {
  return pathname.replace(UUID_PATTERN, '{id}');
}

export function logServerEvent(level: ServerLogLevel, context: ServerLogContext): void {
  const line = JSON.stringify({
    timestamp: new Date().toISOString(),
    service: 'web',
    environment: process.env.APP_ENV ?? 'development',
    level,
    ...context,
  });
  if (level === 'ERROR') {
    console.error(line);
    return;
  }
  console.log(line);
}
