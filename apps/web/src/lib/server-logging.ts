export type ServerLogLevel = 'INFO' | 'WARN' | 'ERROR';

export type ServerLogContext = {
  event: string;
  requestId?: string;
  method?: string;
  route?: string;
  status?: number;
  durationMs?: number;
  errorType?: string;
};

export const ALLOWED_SERVER_LOG_FIELDS = [
  'event',
  'requestId',
  'method',
  'route',
  'status',
  'durationMs',
  'errorType',
] as const;

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
