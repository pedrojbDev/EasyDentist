import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export type ClinicFixture = {
  id: string;
  slug: string;
  legal_name: string;
  display_name: string;
  sentinel: string;
};

export type UserFixture = {
  id: string;
  email: string;
  password: string;
};

export type PatientFixture = {
  id: string;
  full_name: string;
  sentinel: string;
  cpf: string | null;
};

export type ProfessionalProfileFixture = {
  professional_name: string;
  cro_number: string;
  cro_state: string;
};

export type Manifest = {
  run_id: string;
  created_at: string;
  clinics: { a: ClinicFixture; b: ClinicFixture };
  users: {
    multi: UserFixture;
    'clinic-a': UserFixture;
    'clinic-b': UserFixture;
    unverified: UserFixture;
    recovery: UserFixture;
    admin: UserFixture;
  };
  memberships: Record<string, string>;
  patients: { a: PatientFixture; b: PatientFixture };
  professional_profile: ProfessionalProfileFixture;
};

export const MANIFEST_PREFIX = 'E2E_MANIFEST ';

export function manifestPath(): string {
  return resolve(process.env.E2E_MANIFEST_PATH ?? 'artifacts/e2e/manifest.json');
}

export function sessionStateDir(): string {
  return resolve(process.env.E2E_SESSION_STATE_DIR ?? 'artifacts/e2e/sessions');
}

export function sessionStatePath(email: string): string {
  const safe = email.replace(/[^a-zA-Z0-9._-]/g, '_');
  return resolve(sessionStateDir(), `${safe}.json`);
}

export function readManifest(): Manifest {
  const path = manifestPath();
  if (!existsSync(path)) {
    throw new Error(
      `E2E manifest not found at ${path}; run the suite through pnpm e2e so the seed runs first`,
    );
  }
  return JSON.parse(readFileSync(path, 'utf8')) as Manifest;
}

export function inviteeEmail(manifest: Manifest, name: string): string {
  return `e2e-${manifest.run_id}-${name}@example.com`;
}
