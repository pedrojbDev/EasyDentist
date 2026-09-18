import { VerifyEmailPanel } from '@/features/auth/components/VerifyEmailPanel';

export default function VerifyEmailPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Confirmação de e-mail</h1>
        <p className="text-sm text-muted-foreground">
          Estamos confirmando o seu endereço de e-mail.
        </p>
      </div>
      <VerifyEmailPanel />
    </main>
  );
}
