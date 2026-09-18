// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { changeRoleMock, removeMemberMock } = vi.hoisted(() => ({
  changeRoleMock: vi.fn(),
  removeMemberMock: vi.fn(),
}));

vi.mock('@/features/members/api', () => ({
  changeRole: changeRoleMock,
  removeMember: removeMemberMock,
}));

import { ApiError } from '@/lib/api/problem';

import { MembersTable, memberErrorMessage } from './MembersTable';

const members = [
  {
    id: 'm1',
    user_id: 'u1',
    role: 'OWNER' as const,
    status: 'ACTIVE',
    created_at: '2026-09-17T12:00:00Z',
    email: 'owner@example.com',
  },
  {
    id: 'm2',
    user_id: 'u2',
    role: 'DENTIST' as const,
    status: 'ACTIVE',
    created_at: '2026-09-17T12:00:00Z',
    email: 'dentista@example.com',
  },
];

const restrictedMembers = [
  {
    id: 'm1',
    user_id: 'u1',
    role: 'OWNER' as const,
    status: 'ACTIVE',
    created_at: '2026-09-17T12:00:00Z',
  },
  {
    id: 'm2',
    user_id: 'u2',
    role: 'DENTIST' as const,
    status: 'PENDING',
    created_at: '2026-09-17T12:00:00Z',
  },
];

beforeEach(() => {
  changeRoleMock.mockReset();
  removeMemberMock.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('MembersTable', () => {
  it('renders members with pt-BR roles, statuses and e-mails', () => {
    render(<MembersTable clinicId="c1" actorRole="OWNER" members={members} />);

    expect(screen.getByText('owner@example.com')).toBeTruthy();
    expect(screen.getAllByText('Proprietário').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Ativo')).toHaveLength(2);
  });

  it('hides the e-mail column when the API omits contacts', () => {
    render(<MembersTable clinicId="c1" actorRole="DENTIST" members={restrictedMembers} />);

    expect(screen.queryByText('E-mail')).toBeNull();
    expect(screen.getByText('Pendente')).toBeTruthy();
  });

  it('shows an empty state without memberships', () => {
    render(<MembersTable clinicId="c1" actorRole="OWNER" members={[]} />);

    expect(screen.getByText('Nenhum vínculo encontrado.')).toBeTruthy();
  });

  it('lets OWNER change any role', async () => {
    changeRoleMock.mockResolvedValue({
      ...members[1],
      role: 'ASSISTANT',
    });
    render(<MembersTable clinicId="c1" actorRole="OWNER" members={members} />);

    const ownerSelect = screen.getByLabelText('Novo papel de owner@example.com');
    expect(within(ownerSelect).getAllByRole('option')).toHaveLength(5);

    const dentistSelect = screen.getByLabelText('Novo papel de dentista@example.com');
    await userEvent.selectOptions(dentistSelect, 'ASSISTANT');
    await userEvent.click(
      screen.getByRole('button', { name: 'Alterar papel de dentista@example.com' }),
    );

    await waitFor(() => {
      expect(changeRoleMock).toHaveBeenCalledWith('c1', 'm2', 'ASSISTANT');
    });
    expect((await screen.findByRole('status')).textContent).toContain('Papel atualizado.');
    expect(screen.getAllByText('Assistente').length).toBeGreaterThan(0);
  });

  it('prevents ADMIN from managing owners or admins', () => {
    render(<MembersTable clinicId="c1" actorRole="ADMIN" members={members} />);

    expect(screen.queryByLabelText('Novo papel de owner@example.com')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Remover owner@example.com' })).toBeNull();

    const dentistSelect = screen.getByLabelText('Novo papel de dentista@example.com');
    const options = within(dentistSelect)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value);
    expect(options).toEqual(['DENTIST', 'ASSISTANT', 'RECEPTIONIST']);
  });

  it('hides actions from operational roles', () => {
    render(<MembersTable clinicId="c1" actorRole="ASSISTANT" members={members} />);

    expect(screen.queryByRole('button', { name: /Alterar papel/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Remover/ })).toBeNull();
  });

  it('removes a member after confirmation', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    removeMemberMock.mockResolvedValue(undefined);
    render(<MembersTable clinicId="c1" actorRole="OWNER" members={members} />);

    await userEvent.click(screen.getByRole('button', { name: 'Remover dentista@example.com' }));

    await waitFor(() => {
      expect(removeMemberMock).toHaveBeenCalledWith('c1', 'm2');
    });
    expect(screen.queryByText('dentista@example.com')).toBeNull();
  });

  it('shows the last-owner conflict on 409', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    removeMemberMock.mockRejectedValue(new ApiError({ status: 409, title: 'Conflito' }));
    render(<MembersTable clinicId="c1" actorRole="OWNER" members={members} />);

    await userEvent.click(screen.getByRole('button', { name: 'Remover owner@example.com' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'O último proprietário ativo não pode ser removido ou rebaixado.',
    );
  });

  it('shows the permission message on 403', async () => {
    changeRoleMock.mockRejectedValue(new ApiError({ status: 403, title: 'Acesso negado' }));
    render(<MembersTable clinicId="c1" actorRole="OWNER" members={members} />);

    await userEvent.selectOptions(
      screen.getByLabelText('Novo papel de dentista@example.com'),
      'ASSISTANT',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Alterar papel de dentista@example.com' }),
    );

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Você não tem permissão para gerenciar esta equipe.',
    );
  });
});

describe('memberErrorMessage', () => {
  it('maps conflicts, missing links, rate limits and unknown failures', () => {
    expect(memberErrorMessage(new ApiError({ status: 409, title: 'Conflito' }))).toBe(
      'O último proprietário ativo não pode ser removido ou rebaixado.',
    );
    expect(memberErrorMessage(new ApiError({ status: 404, title: 'Recurso não encontrado' }))).toBe(
      'Vínculo não encontrado. Atualize a página.',
    );
    expect(
      memberErrorMessage(new ApiError({ status: 429, title: 'Muitas tentativas', retryAfter: 3 })),
    ).toBe('Muitas tentativas. Tente novamente em 3 segundos.');
    expect(memberErrorMessage(new TypeError('fetch failed'))).toBe(
      'Não foi possível concluir a ação. Tente novamente.',
    );
  });
});
