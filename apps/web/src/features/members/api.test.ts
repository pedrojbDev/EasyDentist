import { afterEach, describe, expect, it, vi } from 'vitest';

import { changeRole, inviteMember, listMembers, removeMember } from './api';

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

function csrfThen(response: Response) {
  return fetchMock
    .mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-1' }))
    .mockResolvedValueOnce(response);
}

describe('members api', () => {
  it('lists the memberships of the clinic', async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json([
        {
          id: 'm1',
          user_id: 'u1',
          role: 'OWNER',
          status: 'ACTIVE',
          created_at: '2026-09-17T12:00:00Z',
          email: 'owner@example.com',
        },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const members = await listMembers('c1');

    expect(members[0].email).toBe('owner@example.com');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/clinics/c1/memberships',
      expect.objectContaining({}),
    );
  });

  it('changes a member role with csrf protection', async () => {
    csrfThen(
      Response.json({
        id: 'm1',
        user_id: 'u1',
        role: 'DENTIST',
        status: 'ACTIVE',
        created_at: '2026-09-17T12:00:00Z',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const member = await changeRole('c1', 'm1', 'DENTIST');

    expect(member.role).toBe('DENTIST');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/clinics/c1/memberships/m1');
    expect(init.method).toBe('PATCH');
    expect(init.body).toBe(JSON.stringify({ role: 'DENTIST' }));
    expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-1' });
  });

  it('removes a member', async () => {
    csrfThen(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await removeMember('c1', 'm1');

    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/clinics/c1/memberships/m1');
    expect(init.method).toBe('DELETE');
  });

  it('invites a member and returns the invitation metadata', async () => {
    csrfThen(
      Response.json(
        { membership_id: 'm9', invitation_expires_at: '2026-09-20T12:00:00Z' },
        { status: 202 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const invitation = await inviteMember('c1', 'novo@example.com', 'DENTIST');

    expect(invitation.membership_id).toBe('m9');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/clinics/c1/invitations');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ email: 'novo@example.com', role: 'DENTIST' }));
  });
});
