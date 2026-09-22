import { describe, expect, it } from 'vitest';

import {
  answeredCount,
  answersFromPayload,
  emptyAnswer,
  pendingQuestions,
  payloadFromAnswers,
  withAnswer,
  type DraftAnswers,
} from './answers';
import { TOTAL_QUESTIONS } from './catalog';
import { completePayload } from './test-fixtures';

describe('answersFromPayload', () => {
  it('normalizes value, details and text answers', () => {
    const answers = answersFromPayload({
      allergies: {
        known_allergy: { value: 'YES', details: 'Penicilina' },
        emergency_care: { value: 'NO' },
      },
      chief_complaint: { description: { text: 'Dor no dente' } },
      unknown_section: { anything: { value: 'YES' } },
    });

    expect(answers.allergies?.known_allergy).toEqual({
      value: 'YES',
      details: 'Penicilina',
      text: '',
    });
    expect(answers.allergies?.emergency_care).toEqual({ value: 'NO', details: '', text: '' });
    expect(answers.chief_complaint?.description?.text).toBe('Dor no dente');
    expect(answers.unknown_section).toBeUndefined();
  });

  it('tolerates empty and invalid payloads', () => {
    expect(answersFromPayload(null)).toEqual({});
    expect(answersFromPayload('nope')).toEqual({});
    expect(answersFromPayload({ allergies: null })).toEqual({});
  });
});

describe('payloadFromAnswers', () => {
  it('sends explicit nulls for unanswered questions and trims values', () => {
    let answers: DraftAnswers = {};
    answers = withAnswer(answers, 'allergies', 'allergies.known_allergy', {
      value: 'YES',
      details: '  Penicilina  ',
    });
    answers = withAnswer(answers, 'chief_complaint', 'chief_complaint.description', {
      text: '  Dor intensa  ',
    });
    answers = withAnswer(answers, 'chief_complaint', 'chief_complaint.duration', {
      text: '   ',
    });

    const payload = payloadFromAnswers(answers);

    expect(payload.allergies).toEqual({
      known_allergy: { value: 'YES', details: 'Penicilina' },
      emergency_care: null,
    });
    expect(payload.chief_complaint).toEqual({
      description: { text: 'Dor intensa' },
      duration: null,
      evolution: null,
    });
    expect(payload.dental_inventory).toBeUndefined();
  });

  it('clears a previously stored answer with null', () => {
    const stored = answersFromPayload({ chief_complaint: { description: { text: 'Dor' } } });
    const cleared = withAnswer(stored, 'chief_complaint', 'chief_complaint.description', {
      text: '',
    });

    expect(payloadFromAnswers(cleared).chief_complaint).toEqual({
      description: null,
      duration: null,
      evolution: null,
    });
  });

  it('round-trips a complete payload', () => {
    const payload = completePayload();
    expect(payloadFromAnswers(answersFromPayload(payload))).toEqual(payload);
  });
});

describe('pendingQuestions', () => {
  it('reports every unanswered question on an empty draft', () => {
    const pending = pendingQuestions({});
    expect(pending).toHaveLength(TOTAL_QUESTIONS);
    expect(pending[0]?.reason).toBe('unanswered');
  });

  it('flags a missing mandatory complement on a positive finding', () => {
    let answers: DraftAnswers = {};
    answers = withAnswer(answers, 'allergies', 'allergies.known_allergy', { value: 'YES' });
    const pending = pendingQuestions(answers);
    const item = pending.find((candidate) => candidate.question.id === 'allergies.known_allergy');
    expect(item?.reason).toBe('details');
  });

  it('accepts a positive finding with its complement', () => {
    let answers: DraftAnswers = {};
    answers = withAnswer(answers, 'allergies', 'allergies.known_allergy', {
      value: 'YES',
      details: 'Penicilina',
    });
    const pending = pendingQuestions(answers);
    expect(pending.some((candidate) => candidate.question.id === 'allergies.known_allergy')).toBe(
      false,
    );
  });

  it('accepts a complete payload', () => {
    const answers = answersFromPayload(completePayload());
    expect(pendingQuestions(answers)).toEqual([]);
    expect(answeredCount(answers)).toBe(TOTAL_QUESTIONS);
  });
});

describe('withAnswer', () => {
  it('keeps the previous state untouched', () => {
    const before: DraftAnswers = {};
    const after = withAnswer(before, 'allergies', 'allergies.known_allergy', { value: 'NO' });
    expect(before).toEqual({});
    expect(after.allergies?.known_allergy).toEqual({ ...emptyAnswer(), value: 'NO' });
  });
});
