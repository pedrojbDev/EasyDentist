'use client';

import {
  Building2,
  CalendarDays,
  ChevronDown,
  KeyRound,
  LayoutDashboard,
  Menu,
  Settings,
  UserRound,
  Users,
  X,
} from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

import { Brand } from '@/components/ui/brand';
import type { Clinic } from '@/features/clinics/api';
import { cn } from '@/lib/utils';

const workItems = [
  { suffix: '/agenda', label: 'Agenda', icon: CalendarDays },
  { suffix: '/patients', label: 'Pacientes', icon: UserRound },
  { suffix: '', label: 'Visão geral', icon: LayoutDashboard },
] as const;

const managementItems = [
  { suffix: '/settings', label: 'Ajustes', icon: Settings },
  { suffix: '/members', label: 'Equipe', icon: Users },
] as const;

export function AppSidebar({ clinics }: { clinics: Clinic[] }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const clinicId = pathname.match(/^\/clinics\/([^/]+)/)?.[1];
  const clinic =
    clinics.find((item) => item.id === clinicId) ??
    (!clinicId && pathname !== '/clinics' && clinics.length === 1 && clinics[0].status === 'ACTIVE'
      ? clinics[0]
      : undefined);
  const clinicPath = clinic ? `/clinics/${clinic.id}` : undefined;

  function itemLink(href: string, label: string, Icon: typeof CalendarDays, active: boolean) {
    return (
      <Link
        key={href}
        href={href as Route}
        aria-current={active ? 'page' : undefined}
        onClick={() => setOpen(false)}
        className={cn(
          'flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-white/30',
          active
            ? 'bg-white/12 text-white'
            : 'text-sidebar-foreground/75 hover:bg-white/8 hover:text-white',
        )}
      >
        <Icon aria-hidden="true" className="size-4 shrink-0" />
        <span>{label}</span>
      </Link>
    );
  }

  return (
    <aside className="sticky top-0 z-30 border-b border-white/10 bg-sidebar text-sidebar-foreground lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r">
      <div className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 lg:block lg:px-4 lg:py-6">
        <Link
          href={(clinicPath ? `${clinicPath}/agenda` : '/clinics') as Route}
          aria-label="EasyDentist — ir para a área de trabalho"
          className="rounded-xl focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-white/35 lg:mb-8 lg:inline-block"
          onClick={() => setOpen(false)}
        >
          <span className="lg:hidden">
            <Brand compact inverse />
          </span>
          <span className="hidden lg:inline-flex">
            <Brand inverse />
          </span>
        </Link>
        <button
          type="button"
          aria-label={open ? 'Fechar menu' : 'Abrir menu'}
          aria-controls="app-navigation"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="grid size-11 place-items-center rounded-lg text-white hover:bg-white/8 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-white/30 lg:hidden"
        >
          {open ? (
            <X aria-hidden="true" className="size-5" />
          ) : (
            <Menu aria-hidden="true" className="size-5" />
          )}
        </button>

        <div
          id="app-navigation"
          className={cn('basis-full pb-4 lg:pb-0', open ? 'block' : 'hidden', 'lg:block')}
        >
          {clinic ? (
            <>
              <div className="mb-5 rounded-xl border border-white/10 bg-white/6 px-3 py-3">
                <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-sidebar-foreground/55">
                  Área de trabalho
                </p>
                <p
                  className="mt-1 truncate text-sm font-semibold text-white"
                  title={clinic.legal_name}
                >
                  {clinic.legal_name}
                </p>
              </div>
              <nav aria-label="Navegação principal" className="flex flex-col gap-1">
                {workItems.map((item) => {
                  const href = `${clinicPath}${item.suffix}`;
                  const active = item.suffix
                    ? pathname === href || pathname.startsWith(`${href}/`)
                    : pathname === href;
                  return itemLink(href, item.label, item.icon, active);
                })}
              </nav>
              <p className="mb-2 mt-7 px-3 text-[0.6875rem] font-semibold uppercase tracking-[0.16em] text-sidebar-foreground/50">
                Administração
              </p>
              <nav aria-label="Administração da clínica" className="flex flex-col gap-1">
                {managementItems.map((item) => {
                  const href = `${clinicPath}${item.suffix}`;
                  return itemLink(
                    href,
                    item.label,
                    item.icon,
                    pathname === href || pathname.startsWith(`${href}/`),
                  );
                })}
              </nav>
            </>
          ) : (
            <nav aria-label="Navegação principal">
              {itemLink('/clinics', 'Escolher clínica', Building2, pathname === '/clinics')}
            </nav>
          )}
          <div className="mt-7 border-t border-white/10 pt-4">
            {clinics.length > 1 &&
              clinic &&
              itemLink('/clinics', 'Trocar clínica', ChevronDown, pathname === '/clinics')}
            {itemLink('/sessions', 'Sessões da conta', KeyRound, pathname === '/sessions')}
          </div>
        </div>
      </div>
    </aside>
  );
}
