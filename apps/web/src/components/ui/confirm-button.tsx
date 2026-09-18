'use client';

import type { ReactNode } from 'react';

import { Button } from '@/components/ui/button';

export function ConfirmButton({
  message,
  onConfirm,
  children,
  className,
  ariaLabel,
  variant = 'outline',
  size = 'default',
}: {
  message: string;
  onConfirm: () => void;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
  variant?: React.ComponentProps<typeof Button>['variant'];
  size?: React.ComponentProps<typeof Button>['size'];
}) {
  return (
    <Button
      type="button"
      aria-label={ariaLabel}
      variant={variant}
      size={size}
      onClick={() => {
        if (window.confirm(message)) {
          onConfirm();
        }
      }}
      className={className}
    >
      {children}
    </Button>
  );
}
