import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Erro 404</p>
      <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
        Página não encontrada
      </h1>
      <p className="text-sm text-muted-foreground">
        O endereço acessado não existe ou você não tem acesso a este recurso.
      </p>
      <Link href="/clinics" className="app-link text-sm">
        Voltar para as clínicas
      </Link>
    </main>
  );
}
