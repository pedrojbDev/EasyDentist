import { ClipboardList } from 'lucide-react';

import { StatusBadge } from '@/components/ui/status-badge';

import { answersFromPayload } from '../answers';
import type { Anamnesis } from '../api';
import { SECTIONS, questionShortName } from '../catalog';
import { anamnesisStatusLabel, answerLabel, authorLabel, formatDateTime } from '../labels';

export function AnamnesisReadOnly({ anamnesis }: { anamnesis: Anamnesis }) {
  const answers = answersFromPayload(anamnesis.payload);
  const sections = SECTIONS.map((section) => ({
    section,
    questions: section.questions.filter(
      (question) => answers[section.id]?.[questionShortName(question.id)] !== undefined,
    ),
  })).filter((entry) => entry.questions.length > 0);
  const author = authorLabel(
    anamnesis.author_professional_name,
    anamnesis.author_cro_number,
    anamnesis.author_cro_state,
  );

  return (
    <div className="flex flex-col gap-5">
      <section className="app-panel flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={anamnesis.status === 'FINAL' ? 'success' : 'info'}>
            {anamnesisStatusLabel(anamnesis.status)}
          </StatusBadge>
          {anamnesis.version_number !== null && (
            <StatusBadge tone="neutral">Versão {anamnesis.version_number}</StatusBadge>
          )}
        </div>
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-medium text-muted-foreground">Autoria</dt>
            <dd className="mt-1 text-foreground">{author ?? 'Não registrada'}</dd>
          </div>
          <div>
            <dt className="font-medium text-muted-foreground">Concluída em</dt>
            <dd className="mt-1 text-foreground">
              {anamnesis.finalized_at !== null
                ? formatDateTime(anamnesis.finalized_at)
                : 'Ainda não concluída'}
            </dd>
          </div>
        </dl>
      </section>

      {sections.length === 0 ? (
        <section className="app-panel flex flex-col items-start gap-3">
          <span
            aria-hidden="true"
            className="grid size-10 place-items-center rounded-lg bg-muted text-muted-foreground"
          >
            <ClipboardList className="size-5" />
          </span>
          <p className="text-sm text-muted-foreground">Nenhuma resposta registrada ainda.</p>
        </section>
      ) : (
        sections.map(({ section, questions }) => (
          <section key={section.id} className="app-panel flex flex-col gap-4">
            <h2 className="font-semibold text-foreground">{section.title}</h2>
            <dl className="flex flex-col gap-4">
              {questions.map((question) => {
                const answer = answers[section.id]?.[questionShortName(question.id)];
                if (answer === undefined) {
                  return null;
                }
                return (
                  <div key={question.id}>
                    <dt className="text-sm font-medium text-muted-foreground">{question.prompt}</dt>
                    <dd className="mt-1 whitespace-pre-line text-sm text-foreground">
                      {answerLabel(question, answer)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </section>
        ))
      )}
    </div>
  );
}
