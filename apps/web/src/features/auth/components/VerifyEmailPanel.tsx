'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';

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
        <Feedback tone="error">{INVALID_LINK_MESSAGE}</Feedback>
        <Link href="/login" className="app-link text-sm">
          Ir para o login
        </Link>
      </div>
    );
  }

  if (status === 'pending') {
    return <Feedback tone="info">Confirmando seu e-mail...</Feedback>;
  }

  if (status === 'error') {
    return (
      <div className="flex flex-col gap-3">
        <Feedback tone="error">{verifyErrorMessage(null)}</Feedback>
        <Button type="button" variant="outline" onClick={() => void retry()} className="w-fit">
          Tentar novamente
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Feedback tone="success">E-mail confirmado com sucesso.</Feedback>
      <Link href="/clinics" className="app-link text-sm">
        Ir para as clínicas
      </Link>
    </div>
  );
}
