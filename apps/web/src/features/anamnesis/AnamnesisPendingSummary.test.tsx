// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { AnamnesisPendingSummary } from './components/AnamnesisPendingSummary';
import type { PendingQuestion } from './answers';
import { SECTIONS } from './catalog';

const firstQuestion = SECTIONS[0]!.questions[0]!;
const allergyQuestion = SECTIONS.find((section) => section.id === 'allergies')!.questions[0]!;

const pending: PendingQuestion[] = [
  {
    sectionId: SECTIONS[0]!.id,
    sectionTitle: SECTIONS[0]!.title,
    question: firstQuestion,
    reason: 'unanswered',
  },
  {
    sectionId: 'allergies',
    sectionTitle: 'Alergias',
    question: allergyQuestion,
    reason: 'details',
  },
];

afterEach(cleanup);

describe('AnamnesisPendingSummary', () => {
  it('lists pending sections with anchors and counts', () => {
    render(<AnamnesisPendingSummary pending={pending} answered={3} total={10} />);

    expect(screen.getByText('3/10 respondidas')).toBeTruthy();
    expect(screen.getByText('Faltam 2 itens para concluir.')).toBeTruthy();
    expect(screen.getByRole('link', { name: SECTIONS[0]!.title }).getAttribute('href')).toBe(
      `#anamnesis-section-${SECTIONS[0]!.id}`,
    );
    expect(screen.getByText(/1 complemento\(s\)/)).toBeTruthy();
  });

  it('celebrates a complete anamnesis', () => {
    render(<AnamnesisPendingSummary pending={[]} answered={10} total={10} />);

    expect(screen.getByText(/Todas as perguntas estão respondidas/)).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
  });
});
