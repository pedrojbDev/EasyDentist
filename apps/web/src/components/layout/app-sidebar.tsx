'use client';

import { Building2, KeyRound } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { Brand } from '@/components/ui/brand';
import { cn } from '@/lib/utils';

const items = [
  { href: '/clinics', label: 'Clínicas', icon: Building2 },
  { href: '/sessions', label: 'Sessões', icon: KeyRound },
] as const;

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 z-30 border-b border-white/10 bg-sidebar text-sidebar-foreground lg:h-screen lg:border-b-0 lg:border-r">
      <div className="flex min-h-16 items-center gap-3 px-4 lg:h-full lg:flex-col lg:items-stretch lg:px-4 lg:py-6">
        <Link
          href="/clinics"
          aria-label="EasyDentist — ir para clínicas"
          className="mr-auto rounded-xl focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-white/35 lg:mb-7 lg:mr-0"
        >
          <span className="lg:hidden">
            <Brand compact inverse />
          </span>
          <span className="hidden lg:inline-flex">
            <Brand inverse />
          </span>
        </Link>

        <p className="hidden px-3 text-[0.6875rem] font-semibold uppercase tracking-[0.16em] text-sidebar-foreground/50 lg:block">
          Organização
        </p>
        <nav
          aria-label="Navegação principal"
          className="flex items-center gap-1 lg:mt-2 lg:flex-col lg:items-stretch"
        >
          {items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-white/30',
                  active
                    ? 'bg-white/12 text-white'
                    : 'text-sidebar-foreground/75 hover:bg-white/8 hover:text-white',
                )}
              >
                <Icon aria-hidden="true" className="size-4" />
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
