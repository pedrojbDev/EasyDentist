import { SessionsTable } from '@/features/sessions/components/SessionsTable';
import { listSessionsOnServer } from '@/features/sessions/server';

export const dynamic = 'force-dynamic';

export default async function SessionsPage() {
  const sessions = await listSessionsOnServer();

  return (
    <section className="flex flex-col gap-7">
      <PageHeader
        eyebrow="Segurança da conta"
        title="Sessões"
        description="Revise os acessos à sua conta e encerre o que não reconhecer."
      />
      <SessionsTable sessions={sessions} />
    </section>
  );
}
import { PageHeader } from '@/components/ui/page-header';
