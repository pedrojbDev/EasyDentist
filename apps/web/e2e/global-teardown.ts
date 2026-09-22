import { execFileSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';

import { manifestPath, readManifest } from './manifest';

const COMPOSE_FILE = 'infra/docker-compose.yml';

function compose(args: string[]): string {
  return execFileSync('docker', ['compose', '-f', COMPOSE_FILE, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

export default async function globalTeardown(): Promise<void> {
  if (process.env.E2E_KEEP_FIXTURES === '1') {
    return;
  }
  const path = manifestPath();
  if (!existsSync(path)) {
    return;
  }
  const manifest = readManifest();
  compose([
    '--profile',
    'tools',
    'run',
    '--rm',
    '-T',
    'e2e-seed',
    'python',
    '-m',
    'scripts.seed_e2e',
    '--cleanup',
    '--run-id',
    manifest.run_id,
  ]);
  rmSync(path, { force: true });
}
