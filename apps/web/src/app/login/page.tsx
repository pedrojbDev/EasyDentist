import { redirect } from 'next/navigation';

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
        <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
          <div>
            <h1 className="text-2xl font-semibold">Entrar</h1>
            <p className="text-sm text-muted-foreground">
              Acesse o EasyDentist com seu e-mail e senha.
            </p>
          </div>
          <LoginForm />
        </main>
      );
    }
    throw error;
  }

  redirect('/clinics');
}
