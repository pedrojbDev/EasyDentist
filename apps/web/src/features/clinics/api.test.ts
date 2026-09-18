import { afterEach, describe, expect, it, vi } from 'vitest';

import { getSettings, listClinics, updateClinic, updateSettings } from './api';

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe('clinics api', () => {
  it('lists the memberships of the current user', async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json([
        {
          id: 'c1',
          slug: 'clinica-a',
          legal_name: 'Clínica A',
          status: 'ACTIVE',
          role: 'OWNER',
        },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const clinics = await listClinics();

    expect(clinics).toHaveLength(1);
    expect(clinics[0].role).toBe('OWNER');
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/clinics', expect.objectContaining({}));
  });

  it('updates the legal name with csrf protection', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-1' })).mockResolvedValueOnce(
      Response.json({
        id: 'c1',
        slug: 'clinica-a',
        legal_name: 'Clínica A Ltda',
        status: 'ACTIVE',
        role: 'OWNER',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const clinic = await updateClinic('c1', 'Clínica A Ltda');

    expect(clinic.legal_name).toBe('Clínica A Ltda');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/clinics/c1');
    expect(init.method).toBe('PATCH');
    expect(init.body).toBe(JSON.stringify({ legal_name: 'Clínica A Ltda' }));
    expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-1' });
  });

  it('reads the clinic settings', async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json({
        clinic_id: 'c1',
        display_name: 'Clínica A',
        timezone: 'America/Bahia',
        locale: 'pt-BR',
        currency: 'BRL',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const settings = await getSettings('c1');

    expect(settings.timezone).toBe('America/Bahia');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/clinics/c1/settings',
      expect.objectContaining({}),
    );
  });

  it('updates the settings with csrf protection', async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ csrf_token: 'csrf-1' })).mockResolvedValueOnce(
      Response.json({
        clinic_id: 'c1',
        display_name: 'Clínica Nova',
        timezone: 'America/Sao_Paulo',
        locale: 'pt-BR',
        currency: 'BRL',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const settings = await updateSettings('c1', {
      display_name: 'Clínica Nova',
      timezone: 'America/Sao_Paulo',
    });

    expect(settings.display_name).toBe('Clínica Nova');
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/v1/clinics/c1/settings');
    expect(init.method).toBe('PATCH');
    expect(init.body).toBe(
      JSON.stringify({ display_name: 'Clínica Nova', timezone: 'America/Sao_Paulo' }),
    );
  });
});
