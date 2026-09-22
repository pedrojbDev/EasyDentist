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
  };
  memberships: Record<string, string>;
};

export const MANIFEST_PREFIX = 'E2E_MANIFEST ';

export function manifestPath(): string {
  return resolve(process.env.E2E_MANIFEST_PATH ?? 'artifacts/e2e/manifest.json');
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
