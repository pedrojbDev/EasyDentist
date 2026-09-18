import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AuthShell } from '@/components/layout/auth-shell';
import { LoginForm } from '@/features/auth/components/LoginForm';
import { getCurrentUser } from '@/features/auth/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function LoginPage() {
  try {
    await getCurrentUser();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return (
        <AuthShell
          eyebrow="Acesso seguro"
          title="Entre na sua conta"
          description="Use o e-mail cadastrado para continuar."
          footer={
            <Link href="/forgot-password" className="app-link">
              Esqueci minha senha
            </Link>
          }
        >
          <LoginForm />
        </AuthShell>
      );
    }
    throw error;
  }

  redirect('/clinics');
}
