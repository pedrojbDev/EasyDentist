'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { verifyEmail } from '../api';
import { useFragmentToken } from '../use-fragment-token';

const INVALID_LINK_MESSAGE = 'Link inválido ou expirado. Solicite uma nova verificação.';
const GENERIC_FAILURE =
  'Não foi possível confirmar o e-mail. O link pode ter expirado ou já ter sido usado.';

export function verifyErrorMessage(_error: unknown): string {
  return GENERIC_FAILURE;
}

export function VerifyEmailPanel() {
  const token = useFragmentToken();
  const [status, setStatus] = useState<'pending' | 'done' | 'error'>('pending');
  const startedRef = useRef(false);

  useEffect(() => {
    if (token === null || startedRef.current) {
      return;
    }
    startedRef.current = true;
    void verifyEmail(token).then(
      () => setStatus('done'),
      () => setStatus('error'),
    );
  }, [token]);

  async function retry() {
    if (token === null) {
      return;
    }
    setStatus('pending');
    try {
      await verifyEmail(token);
      setStatus('done');
    } catch {
      setStatus('error');
    }
  }

  if (token === null) {
    return (
      <div className="flex flex-col gap-3">
        <p role="alert" className="text-sm text-destructive">
          {INVALID_LINK_MESSAGE}
        </p>
        <Link href="/login" className="text-sm underline">
          Ir para o login
        </Link>
      </div>
    );
  }

  if (status === 'pending') {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Confirmando seu e-mail...
      </p>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex flex-col gap-3">
        <p role="alert" className="text-sm text-destructive">
          {verifyErrorMessage(null)}
        </p>
        <button
          type="button"
          onClick={() => void retry()}
          className="w-fit rounded-md border border-border px-4 py-2 text-sm"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p role="status" className="text-sm">
        E-mail confirmado com sucesso.
      </p>
      <Link href="/clinics" className="text-sm underline">
        Ir para as clínicas
      </Link>
    </div>
  );
}
