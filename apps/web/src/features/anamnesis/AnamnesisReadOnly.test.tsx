// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { AnamnesisReadOnly } from './components/AnamnesisReadOnly';
import { makeAnamnesis, makeFinal } from './test-fixtures';

afterEach(cleanup);

describe('AnamnesisReadOnly', () => {
  it('renders the finalized metadata and answered questions', () => {
    render(
      <AnamnesisReadOnly
        anamnesis={makeFinal(2, {
          payload: {
            allergies: {
              known_allergy: { value: 'YES', details: 'Penicilina' },
              emergency_care: { value: 'NO' },
            },
            chief_complaint: { description: { text: 'Dor no dente' } },
          },
        })}
      />,
    );

    expect(screen.getByText('Concluída')).toBeTruthy();
    expect(screen.getByText('Versão 2')).toBeTruthy();
    expect(screen.getByText(/Dra. Ana Souza/)).toBeTruthy();
    expect(screen.getByText('Alergias')).toBeTruthy();
    expect(screen.getByText('Sim — Penicilina')).toBeTruthy();
    expect(screen.getByText('Não')).toBeTruthy();
    expect(screen.getByText('Dor no dente')).toBeTruthy();
    expect(screen.queryByText('História familiar')).toBeNull();
  });

  it('shows an empty state for a draft without answers', () => {
    render(<AnamnesisReadOnly anamnesis={makeAnamnesis()} />);

    expect(screen.getByText('Nenhuma resposta registrada ainda.')).toBeTruthy();
    expect(screen.getByText('Rascunho')).toBeTruthy();
    expect(screen.getByText('Ainda não concluída')).toBeTruthy();
  });
});
