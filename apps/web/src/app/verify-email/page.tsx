import { AuthShell } from '@/components/layout/auth-shell';
import { VerifyEmailPanel } from '@/features/auth/components/VerifyEmailPanel';

export default function VerifyEmailPage() {
  return (
    <AuthShell
      eyebrow="Confirmação de identidade"
      title="Confirme seu e-mail"
      description="Estamos validando o endereço associado à sua conta."
    >
      <VerifyEmailPanel />
    </AuthShell>
  );
}
