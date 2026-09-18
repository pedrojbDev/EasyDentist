import { AuthShell } from '@/components/layout/auth-shell';
import { AcceptInvitationForm } from '@/features/auth/components/AcceptInvitationForm';

export default function AcceptInvitationPage() {
  return (
    <AuthShell
      eyebrow="Convite para a equipe"
      title="Ative seu acesso"
      description="Confirme o convite para entrar na clínica."
    >
      <AcceptInvitationForm />
    </AuthShell>
  );
}
