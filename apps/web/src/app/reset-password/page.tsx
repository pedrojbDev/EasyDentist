import { ResetPasswordForm } from '@/features/auth/components/ResetPasswordForm';

export default function ResetPasswordPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Redefinir senha</h1>
        <p className="text-sm text-muted-foreground">Escolha uma nova senha para a sua conta.</p>
      </div>
      <ResetPasswordForm />
    </main>
  );
}
