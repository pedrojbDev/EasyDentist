import type { ReactNode } from 'react';

import { AlertCircle, CheckCircle2, Info } from 'lucide-react';

import { cn } from '@/lib/utils';

const icons = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
};

export function Feedback({
  tone,
  children,
  className,
}: {
  tone: keyof typeof icons;
  children: ReactNode;
  className?: string;
}) {
  const Icon = icons[tone];

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('feedback', `feedback-${tone}`, className)}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}
