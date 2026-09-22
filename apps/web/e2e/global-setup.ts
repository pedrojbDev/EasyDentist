import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

import { chromium, type FullConfig } from '@playwright/test';

import {
  MANIFEST_PREFIX,
  manifestPath,
  sessionStatePath,
  type Manifest,
  type UserFixture,
} from './manifest';

const COMPOSE_FILE = 'infra/docker-compose.yml';
const HEALTH_TIMEOUT_MS = 30_000;
const HEALTH_INTERVAL_MS = 1_000;
const WAIT_TIMEOUT_S = '180';

function compose(args: string[], env: Record<string, string> = {}): string {
  return execFileSync('docker', ['compose', '-f', COMPOSE_FILE, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...env },
  });
}

async function waitForApp(baseURL: string): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseURL}/health`);
      const payload = (await response.json()) as { status?: string };
      if (response.ok && payload.status === 'ok') {
        return;
      }
    } catch {
      // The Compose stack is still starting; retry until the deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, HEALTH_INTERVAL_MS));
  }
  throw new Error(
    `The Compose stack is not healthy at ${baseURL}; start it with ` +
      'docker compose -f infra/docker-compose.yml up -d --wait before pnpm e2e',
  );
}

function seedManifest(): Manifest {
  const output = compose(['--profile', 'tools', 'run', '--rm', '-T', 'e2e-seed']);
  const line = output.split('\n').find((entry) => entry.startsWith(MANIFEST_PREFIX));
  if (line === undefined) {
    throw new Error('The E2E seed did not return a manifest');
  }
  return JSON.parse(line.slice(MANIFEST_PREFIX.length)) as Manifest;
}

function applyStoragePrefix(runId: string): void {
  compose(['up', '-d', '--wait', '--wait-timeout', WAIT_TIMEOUT_S, '--no-deps', 'api'], {
    S3_KEY_PREFIX: `e2e/${runId}/`,
  });
}

/**
 * Logs in once per seeded user through the real form and stores the resulting
 * session state. Specs reuse it instead of logging in per test, keeping the
 * whole run well under the login rate limit (20/IP/15min). Flows that exist to
 * test login itself (auth.spec.ts) still use the form directly.
 */
async function createSessionStates(baseURL: string, manifest: Manifest): Promise<void> {
  const browser = await chromium.launch();
  try {
    for (const user of Object.values(manifest.users) as UserFixture[]) {
      const context = await browser.newContext({ baseURL });
      try {
        const page = await context.newPage();
        await page.goto('/login');
        await page.getByLabel('E-mail', { exact: true }).fill(user.email);
        await page.getByLabel('Senha', { exact: true }).fill(user.password);
        await page.getByRole('button', { name: 'Entrar' }).click();
        await page.waitForURL(/\/clinics$/);
        const path = sessionStatePath(user.email);
        mkdirSync(dirname(path), { recursive: true });
        await context.storageState({ path });
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://127.0.0.1:3000';
  await waitForApp(baseURL);
  compose(['--profile', 'tools', 'build', 'migrate', 'e2e-seed']);
  compose(['--profile', 'tools', 'run', '--rm', 'migrate']);
  const manifest = seedManifest();
  const path = manifestPath();
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  await createSessionStates(baseURL, manifest);
  // Documents uploaded by the specs must land under e2e/{run_id}/ so the
  // teardown can remove exactly what this run created. The API is recreated
  // with the run prefix and must be healthy again before any spec starts.
  applyStoragePrefix(manifest.run_id);
}
