import { SessionsTable } from '@/features/sessions/components/SessionsTable';
import { listSessionsOnServer } from '@/features/sessions/server';

export const dynamic = 'force-dynamic';

export default async function SessionsPage() {
  const sessions = await listSessionsOnServer();

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Sessões</h1>
        <p className="text-sm text-muted-foreground">
          Dispositivos com acesso à sua conta. Encerre o que não reconhecer.
        </p>
      </div>
      <SessionsTable sessions={sessions} />
    </section>
  );
}
