import { LockKeyhole } from 'lucide-react';

export function AnamnesisRestricted() {
  return (
    <section
      className="app-panel flex flex-col items-start gap-3"
      aria-labelledby="anamnesis-restricted"
    >
      <span
        aria-hidden="true"
        className="grid size-10 place-items-center rounded-lg bg-muted text-muted-foreground"
      >
        <LockKeyhole className="size-5" />
      </span>
      <h2 id="anamnesis-restricted" className="font-semibold text-foreground">
        Acesso restrito
      </h2>
      <p className="text-sm text-muted-foreground">
        A anamnese é conteúdo clínico e não está disponível para o seu papel nesta clínica.
      </p>
    </section>
  );
}
