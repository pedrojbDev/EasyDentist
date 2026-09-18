'use client';

import { useEffect, type RefObject } from 'react';

export function useFocusFirstInvalid(
  errors: Record<string, string | undefined>,
  formRef: RefObject<HTMLFormElement | null>,
) {
  useEffect(() => {
    const hasErrors = Object.values(errors).some((value) => value !== undefined);
    if (!hasErrors) {
      return;
    }
    const firstInvalid = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    firstInvalid?.focus();
  }, [errors, formRef]);
}
