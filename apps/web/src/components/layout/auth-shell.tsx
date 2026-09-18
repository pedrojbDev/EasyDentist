import type { ReactNode } from 'react';

import { Brand } from '@/components/ui/brand';

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
  footer,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(20rem,0.9fr)_minmax(28rem,1.1fr)]">
      <aside className="relative hidden overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex lg:flex-col lg:justify-between xl:p-14">
        <div
          aria-hidden="true"
          className="absolute -right-32 -top-32 size-96 rounded-full border border-white/10 bg-white/5"
        />
        <Brand inverse />
        <div className="relative max-w-md">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-sidebar-foreground/65">
            Gestão com tranquilidade
          </p>
          <p className="text-3xl font-semibold leading-tight tracking-tight text-white xl:text-4xl">
            Sua clínica organizada, todos os dias.
          </p>
          <p className="mt-4 max-w-sm text-base leading-relaxed text-sidebar-foreground/75">
            Um ambiente seguro para cuidar da equipe e manter o trabalho da clínica em ordem.
          </p>
        </div>
        <p className="relative text-xs text-sidebar-foreground/55">
          Segurança e clareza desde a base.
        </p>
      </aside>

      <section className="flex min-h-screen items-center justify-center px-5 py-10 sm:px-8 lg:px-12">
        <div className="w-full max-w-md">
          <div className="mb-10 lg:hidden">
            <Brand />
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            {eyebrow}
          </p>
          <h1
            id="auth-title"
            className="mt-2 text-3xl font-semibold tracking-tight text-foreground"
          >
            {title}
          </h1>
          <p className="mt-2 text-base leading-relaxed text-muted-foreground">{description}</p>
          <div className="mt-7">{children}</div>
          {footer !== undefined && <div className="mt-6 text-center text-sm">{footer}</div>}
        </div>
      </section>
    </main>
  );
}
