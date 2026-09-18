import { AuthShell } from '@/components/layout/auth-shell';
import { ForgotPasswordForm } from '@/features/auth/components/ForgotPasswordForm';

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      eyebrow="Recuperação de acesso"
      title="Recupere sua senha"
      description="Informe seu e-mail para receber as instruções de recuperação."
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}
