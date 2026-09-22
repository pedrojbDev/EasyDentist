// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { AnamnesisHistory } from './components/AnamnesisHistory';
import { makeAnamnesis, makeFinal } from './test-fixtures';

afterEach(cleanup);

describe('AnamnesisHistory', () => {
  it('shows an empty state without final versions', () => {
    render(<AnamnesisHistory clinicId="c1" patientId="p1" versions={[makeAnamnesis()]} />);

    expect(screen.getByText('Nenhuma versão concluída registrada.')).toBeTruthy();
  });

  it('lists final versions newest first and marks the current one', () => {
    render(
      <AnamnesisHistory
        clinicId="c1"
        patientId="p1"
        versions={[makeFinal(1), makeFinal(3), makeFinal(2)]}
      />,
    );

    const items = screen.getAllByRole('listitem');
    expect(items[0]?.textContent).toContain('Versão 3');
    expect(items[0]?.textContent).toContain('Vigente');
    expect(items[2]?.textContent).toContain('Versão 1');
    expect(screen.getAllByRole('link', { name: 'Ver versão' })[0]?.getAttribute('href')).toBe(
      '/clinics/c1/patients/p1/anamnesis/final-3',
    );
    expect(screen.getAllByText(/Dra. Ana Souza/).length).toBe(3);
  });
});
