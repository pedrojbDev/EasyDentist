import type { components } from '@/lib/api/generated/schema';

import { SECTIONS, questionShortName, type CatalogQuestion } from './catalog';

export type AnamnesisPayload = components['schemas']['AnamnesisPayload'];

/** Normalized answer of a single catalog question while editing a draft. */
export type AnswerState = {
  value: string | null;
  details: string;
  text: string;
};

export type DraftAnswers = Record<string, Record<string, AnswerState>>;

export type PendingReason = 'unanswered' | 'details';

export type PendingQuestion = {
  sectionId: string;
  sectionTitle: string;
  question: CatalogQuestion;
  reason: PendingReason;
};

export function emptyAnswer(): AnswerState {
  return { value: null, details: '', text: '' };
}

export function hasAnswerContent(answer: AnswerState | undefined): boolean {
  if (!answer) {
    return false;
  }
  return answer.value !== null || answer.text.trim() !== '' || answer.details.trim() !== '';
}

/** Parse the API payload into the normalized form state, ignoring noise. */
export function answersFromPayload(payload: unknown): DraftAnswers {
  const answers: DraftAnswers = {};
  if (payload === null || typeof payload !== 'object') {
    return answers;
  }
  const record = payload as Record<string, unknown>;
  for (const section of SECTIONS) {
    const sectionPayload = record[section.id];
    if (sectionPayload === null || typeof sectionPayload !== 'object') {
      continue;
    }
    const sectionRecord = sectionPayload as Record<string, unknown>;
    const sectionAnswers: Record<string, AnswerState> = {};
    for (const question of section.questions) {
      const raw = sectionRecord[questionShortName(question.id)];
      if (raw === null || raw === undefined || typeof raw !== 'object') {
        continue;
      }
      const rawRecord = raw as Record<string, unknown>;
      const answer = emptyAnswer();
      if (typeof rawRecord.value === 'string') {
        answer.value = rawRecord.value;
      }
      if (typeof rawRecord.details === 'string') {
        answer.details = rawRecord.details;
      }
      if (typeof rawRecord.text === 'string') {
        answer.text = rawRecord.text;
      }
      sectionAnswers[questionShortName(question.id)] = answer;
    }
    if (Object.keys(sectionAnswers).length > 0) {
      answers[section.id] = sectionAnswers;
    }
  }
  return answers;
}

/**
 * Serialize the form state for a partial update.
 *
 * Every question is sent: unanswered ones go as explicit ``null`` so the API
 * removes a previously stored answer (for example, a text field the user
 * cleared). Blank values are normalized away.
 */
export function payloadFromAnswers(answers: DraftAnswers): AnamnesisPayload {
  const payload: Record<string, Record<string, Record<string, string> | null>> = {};
  for (const section of SECTIONS) {
    const sectionAnswers = answers[section.id];
    if (sectionAnswers === undefined) {
      continue;
    }
    const serialized: Record<string, Record<string, string> | null> = {};
    for (const question of section.questions) {
      const short = questionShortName(question.id);
      const answer = sectionAnswers?.[short];
      if (answer === undefined || !hasAnswerContent(answer)) {
        serialized[short] = null;
        continue;
      }
      if (question.answer_type === 'TEXT') {
        const text = answer.text.trim();
        serialized[short] = text === '' ? null : { text };
        continue;
      }
      if (answer.value === null) {
        serialized[short] = null;
        continue;
      }
      const entry: Record<string, string> = { value: answer.value };
      const details = answer.details.trim();
      if (details !== '') {
        entry.details = details;
      }
      serialized[short] = entry;
    }
    payload[section.id] = serialized;
  }
  return payload as unknown as AnamnesisPayload;
}

function answerIsComplete(question: CatalogQuestion, answer: AnswerState | undefined): boolean {
  if (!hasAnswerContent(answer) || answer === undefined) {
    return false;
  }
  if (question.answer_type === 'TEXT') {
    return answer.text.trim() !== '';
  }
  if (answer.value === null) {
    return false;
  }
  if (question.details_required && answer.value === 'YES' && answer.details.trim() === '') {
    return false;
  }
  return true;
}

/** Questions that still block finalization, in catalog order. */
export function pendingQuestions(answers: DraftAnswers): PendingQuestion[] {
  const pending: PendingQuestion[] = [];
  for (const section of SECTIONS) {
    for (const question of section.questions) {
      const answer = answers[section.id]?.[questionShortName(question.id)];
      if (!answerIsComplete(question, answer)) {
        const hasContent = hasAnswerContent(answer);
        pending.push({
          sectionId: section.id,
          sectionTitle: section.title,
          question,
          reason: hasContent ? 'details' : 'unanswered',
        });
      }
    }
  }
  return pending;
}

export function answeredCount(answers: DraftAnswers): number {
  let total = 0;
  for (const section of SECTIONS) {
    for (const question of section.questions) {
      if (hasAnswerContent(answers[section.id]?.[questionShortName(question.id)])) {
        total += 1;
      }
    }
  }
  return total;
}

export function withAnswer(
  answers: DraftAnswers,
  sectionId: string,
  questionId: string,
  patch: Partial<AnswerState>,
): DraftAnswers {
  const short = questionShortName(questionId);
  const sectionAnswers = answers[sectionId] ?? {};
  const current = sectionAnswers[short] ?? emptyAnswer();
  return {
    ...answers,
    [sectionId]: {
      ...sectionAnswers,
      [short]: { ...current, ...patch },
    },
  };
}
