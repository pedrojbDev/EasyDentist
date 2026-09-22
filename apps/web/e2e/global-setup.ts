import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

import type { FullConfig } from '@playwright/test';

import { MANIFEST_PREFIX, manifestPath, type Manifest } from './manifest';

const COMPOSE_FILE = 'infra/docker-compose.yml';
const HEALTH_TIMEOUT_MS = 30_000;
const HEALTH_INTERVAL_MS = 1_000;

function compose(args: string[]): string {
  return execFileSync('docker', ['compose', '-f', COMPOSE_FILE, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
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

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://127.0.0.1:3000';
  await waitForApp(baseURL);
  compose(['--profile', 'tools', 'build', 'migrate', 'e2e-seed']);
  compose(['--profile', 'tools', 'run', '--rm', 'migrate']);
  const manifest = seedManifest();
  const path = manifestPath();
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
}
