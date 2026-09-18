import { afterEach, describe, expect, it, vi } from 'vitest';

const { serverFetchMock } = vi.hoisted(() => ({ serverFetchMock: vi.fn() }));

vi.mock('@/lib/api/server-client', () => ({ serverFetch: serverFetchMock }));

import { getClinicOnServer, getClinicSettingsOnServer, listClinicsOnServer } from './server';

afterEach(() => {
  serverFetchMock.mockReset();
});

describe('clinics server api', () => {
  it('lists the clinics through the server client', async () => {
    serverFetchMock.mockResolvedValueOnce([]);

    await expect(listClinicsOnServer()).resolves.toEqual([]);
    expect(serverFetchMock).toHaveBeenCalledWith('/api/v1/clinics');
  });

  it('fetches a single clinic by id', async () => {
    const clinic = {
      id: 'c1',
      slug: 'clinica-a',
      legal_name: 'Clínica A',
      status: 'ACTIVE',
      role: 'OWNER',
    };
    serverFetchMock.mockResolvedValueOnce(clinic);

    await expect(getClinicOnServer('c1')).resolves.toEqual(clinic);
    expect(serverFetchMock).toHaveBeenCalledWith('/api/v1/clinics/c1');
  });

  it('fetches the clinic settings by id', async () => {
    const settings = {
      clinic_id: 'c1',
      display_name: 'Clínica A',
      timezone: 'America/Bahia',
      locale: 'pt-BR',
      currency: 'BRL',
    };
    serverFetchMock.mockResolvedValueOnce(settings);

    await expect(getClinicSettingsOnServer('c1')).resolves.toEqual(settings);
    expect(serverFetchMock).toHaveBeenCalledWith('/api/v1/clinics/c1/settings');
  });
});
