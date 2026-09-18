import { AuthShell } from '@/components/layout/auth-shell';
import { ResetPasswordForm } from '@/features/auth/components/ResetPasswordForm';

export default function ResetPasswordPage() {
  return (
    <AuthShell
      eyebrow="Nova senha"
      title="Redefina sua senha"
      description="Escolha uma nova senha segura para a sua conta."
    >
      <ResetPasswordForm />
    </AuthShell>
  );
}
