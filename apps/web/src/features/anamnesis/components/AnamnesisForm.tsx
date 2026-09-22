'use client';

import { ClipboardCheck, Save } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';
import { ApiError } from '@/lib/api/problem';
import { cn } from '@/lib/utils';

import {
  answeredCount,
  answersFromPayload,
  emptyAnswer,
  pendingQuestions,
  payloadFromAnswers,
  withAnswer,
  type AnswerState,
  type DraftAnswers,
} from '../answers';
import {
  finalizeAnamnesis,
  updateAnamnesis,
  type Anamnesis,
  type ProfessionalProfile,
} from '../api';
import {
  SECTIONS,
  TOTAL_QUESTIONS,
  questionShortName,
  sectionAnchorId,
  type CatalogQuestion,
} from '../catalog';
import { AnamnesisFinalizeDialog } from './AnamnesisFinalizeDialog';
import { AnamnesisPendingSummary } from './AnamnesisPendingSummary';
import { ProfessionalProfileCard } from './ProfessionalProfileCard';

const YES_NO_UNKNOWN_OPTIONS = [
  { id: 'YES', label: 'Sim' },
  { id: 'NO', label: 'Não' },
  { id: 'UNKNOWN', label: 'Não sabe' },
];

export function anamnesisErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para alterar esta anamnese.';
    }
    if (error.status === 404) {
      return 'Anamnese não encontrada. Atualize a página.';
    }
    if (error.status === 409) {
      return 'Esta anamnese já foi concluída ou existe outro rascunho. Atualize a página.';
    }
    if (error.status === 422) {
      return 'Há respostas inválidas ou incompletas. Revise as seções e tente novamente.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível salvar a anamnese. Tente novamente.';
}

function QuestionField({
  question,
  answer,
  onChange,
}: {
  question: CatalogQuestion;
  answer: AnswerState;
  onChange: (patch: Partial<AnswerState>) => void;
}) {
  const fieldId = `anamnesis-${question.id.replace('.', '-')}`;

  if (question.answer_type === 'TEXT') {
    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={fieldId} className="app-label">
          {question.prompt}
        </label>
        <textarea
          id={fieldId}
          name={fieldId}
          rows={3}
          maxLength={4000}
          value={answer.text}
          onChange={(event) => onChange({ text: event.target.value })}
          className="app-field"
        />
      </div>
    );
  }

  const options =
    question.answer_type === 'YES_NO_UNKNOWN' ? YES_NO_UNKNOWN_OPTIONS : question.options;
  const detailsRequired = question.details_required && answer.value === 'YES';

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="app-label">{question.prompt}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const selected = answer.value === option.id;
          return (
            <label
              key={option.id}
              className={cn(
                'flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm transition-colors',
                selected
                  ? 'border-primary bg-accent/60 font-semibold text-accent-foreground'
                  : 'border-border bg-surface text-foreground hover:border-primary/30',
              )}
            >
              <input
                type="radio"
                name={fieldId}
                value={option.id}
                checked={selected}
                onChange={() => onChange({ value: option.id })}
                className="size-4 accent-primary"
              />
              {option.label}
            </label>
          );
        })}
      </div>
      {question.details_prompt !== null && (
        <div className="flex flex-col gap-1">
          <label htmlFor={`${fieldId}-details`} className="text-sm text-muted-foreground">
            {question.details_prompt}
            {detailsRequired ? ' (obrigatório)' : ''}
          </label>
          <textarea
            id={`${fieldId}-details`}
            name={`${fieldId}-details`}
            rows={2}
            maxLength={2000}
            value={answer.details}
            onChange={(event) => onChange({ details: event.target.value })}
            className="app-field"
          />
        </div>
      )}
    </fieldset>
  );
}

export function AnamnesisForm({
  clinicId,
  patientId,
  anamnesis,
  profile: initialProfile,
  patientName,
  canFinalize,
}: {
  clinicId: string;
  patientId: string;
  anamnesis: Anamnesis;
  profile: ProfessionalProfile | null;
  patientName: string;
  canFinalize: boolean;
}) {
  const router = useRouter();
  const [answers, setAnswers] = useState<DraftAnswers>(() => answersFromPayload(anamnesis.payload));
  const [profile, setProfile] = useState<ProfessionalProfile | null>(initialProfile);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pending = useMemo(() => pendingQuestions(answers), [answers]);
  const answered = useMemo(() => answeredCount(answers), [answers]);

  function update(sectionId: string, questionId: string, patch: Partial<AnswerState>) {
    setAnswers((current) => withAnswer(current, sectionId, questionId, patch));
    setDirty(true);
    setMessage(null);
  }

  async function persist(): Promise<boolean> {
    try {
      await updateAnamnesis(clinicId, patientId, anamnesis.id, payloadFromAnswers(answers));
      setDirty(false);
      return true;
    } catch (cause) {
      setError(anamnesisErrorMessage(cause));
      return false;
    }
  }

  async function handleSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    if (await persist()) {
      setMessage('Rascunho salvo.');
    }
    setSaving(false);
  }

  async function handleConfirmFinalize() {
    setFinalizing(true);
    setError(null);
    if (dirty && !(await persist())) {
      setFinalizing(false);
      setDialogOpen(false);
      return;
    }
    try {
      const finalized = await finalizeAnamnesis(clinicId, patientId, anamnesis.id);
      router.push(`/clinics/${clinicId}/patients/${patientId}/anamnesis/${finalized.id}`);
      router.refresh();
    } catch (cause) {
      setError(anamnesisErrorMessage(cause));
      setFinalizing(false);
      setDialogOpen(false);
    }
  }

  const canConfirmFinalize = canFinalize && profile !== null && pending.length === 0;

  return (
    <>
      {error !== null && <Feedback tone="error">{error}</Feedback>}
      {message !== null && <Feedback tone="success">{message}</Feedback>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,0.55fr)]">
        <form onSubmit={handleSave} noValidate className="flex min-w-0 flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone="info">Rascunho</StatusBadge>
              {dirty ? (
                <span className="text-sm text-muted-foreground">Alterações não salvas</span>
              ) : (
                <span className="text-sm text-muted-foreground">Sem alterações pendentes</span>
              )}
            </div>
            <Button type="submit" variant="outline" disabled={saving}>
              <Save aria-hidden="true" />
              {saving ? 'Salvando...' : 'Salvar rascunho'}
            </Button>
          </div>

          {SECTIONS.map((section) => (
            <section
              key={section.id}
              id={sectionAnchorId(section.id)}
              className="app-panel flex scroll-mt-24 flex-col gap-4"
            >
              <div>
                <h2 className="font-semibold text-foreground">{section.title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {section.questions.length === 1
                    ? '1 pergunta'
                    : `${section.questions.length} perguntas`}
                </p>
              </div>
              <div className="flex flex-col gap-5">
                {section.questions.map((question) => (
                  <QuestionField
                    key={question.id}
                    question={question}
                    answer={answers[section.id]?.[questionShortName(question.id)] ?? emptyAnswer()}
                    onChange={(patch) => update(section.id, question.id, patch)}
                  />
                ))}
              </div>
            </section>
          ))}
        </form>

        <aside className="flex flex-col gap-5 lg:sticky lg:top-6">
          <AnamnesisPendingSummary pending={pending} answered={answered} total={TOTAL_QUESTIONS} />
          {canFinalize && (
            <>
              <ProfessionalProfileCard profile={profile} onSaved={setProfile} />
              <section className="app-panel flex flex-col gap-3" aria-labelledby="finalize-title">
                <h2 id="finalize-title" className="font-semibold text-foreground">
                  Conclusão
                </h2>
                <p className="text-sm text-muted-foreground">
                  Ao concluir, a versão fica imutável e registra autoria, data e perfil
                  profissional.
                </p>
                {profile === null && (
                  <p className="text-sm text-muted-foreground">
                    Informe seu perfil profissional para liberar a conclusão.
                  </p>
                )}
                {profile !== null && pending.length > 0 && (
                  <p className="text-sm text-muted-foreground">
                    Resolva as pendências para liberar a conclusão.
                  </p>
                )}
                <Button
                  type="button"
                  disabled={!canConfirmFinalize || finalizing}
                  onClick={() => setDialogOpen(true)}
                  className="w-fit"
                >
                  <ClipboardCheck aria-hidden="true" />
                  Concluir anamnese
                </Button>
              </section>
            </>
          )}
        </aside>
      </div>

      {profile !== null && (
        <AnamnesisFinalizeDialog
          open={dialogOpen}
          patientName={patientName}
          profile={profile}
          onCancel={() => setDialogOpen(false)}
          onConfirm={() => void handleConfirmFinalize()}
          pending={finalizing}
        />
      )}
    </>
  );
}
