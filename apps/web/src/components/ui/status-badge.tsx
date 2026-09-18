import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

const tones = {
  neutral: 'bg-muted text-muted-foreground',
  info: 'bg-accent text-accent-foreground',
  success: 'bg-success/12 text-foreground ring-success/20',
  warning: 'bg-warning/15 text-foreground ring-warning/25',
  danger: 'bg-destructive/10 text-destructive ring-destructive/20',
};

export function StatusBadge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: keyof typeof tones;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ring-transparent',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
