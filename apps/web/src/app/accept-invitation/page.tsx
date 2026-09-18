import { AcceptInvitationForm } from '@/features/auth/components/AcceptInvitationForm';

export default function AcceptInvitationPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Aceitar convite</h1>
        <p className="text-sm text-muted-foreground">
          Ative o seu acesso à clínica que enviou o convite.
        </p>
      </div>
      <AcceptInvitationForm />
    </main>
  );
}
