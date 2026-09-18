import { cn } from '@/lib/utils';

export function Brand({
  compact = false,
  inverse = false,
}: {
  compact?: boolean;
  inverse?: boolean;
}) {
  return (
    <span className={cn('inline-flex items-center gap-3', inverse && 'text-sidebar-foreground')}>
      <span
        aria-hidden="true"
        className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-sm font-bold tracking-tight text-primary-foreground shadow-sm"
      >
        ED
      </span>
      {!compact && <span className="text-base font-semibold tracking-tight">EasyDentist</span>}
      <span className="sr-only">EasyDentist</span>
    </span>
  );
}
