import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { AppHeader } from '@/features/auth/components/AppHeader';
import { getCurrentUser } from '@/features/auth/server';
import { ApiError } from '@/lib/api/problem';

export const dynamic = 'force-dynamic';

export default async function AuthenticatedLayout({ children }: { children: ReactNode }) {
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      redirect('/login');
    }
    throw error;
  }

  return (
    <div className="min-h-screen">
      <AppHeader user={user} />
      <main className="mx-auto max-w-4xl p-6">{children}</main>
    </div>
  );
}
