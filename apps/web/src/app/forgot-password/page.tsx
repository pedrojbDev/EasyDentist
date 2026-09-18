import { ForgotPasswordForm } from '@/features/auth/components/ForgotPasswordForm';

export default function ForgotPasswordPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Recuperar senha</h1>
        <p className="text-sm text-muted-foreground">
          Informe seu e-mail para receber as instruções de recuperação.
        </p>
      </div>
      <ForgotPasswordForm />
    </main>
  );
}
