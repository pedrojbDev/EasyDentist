'use client';

import type { ReactNode } from 'react';

export function ConfirmButton({
  message,
  onConfirm,
  children,
  className,
  ariaLabel,
}: {
  message: string;
  onConfirm: () => void;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={() => {
        if (window.confirm(message)) {
          onConfirm();
        }
      }}
      className={className}
    >
      {children}
    </button>
  );
}
