import { execFileSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';

import { manifestPath, readManifest, sessionStateDir } from './manifest';

const COMPOSE_FILE = 'infra/docker-compose.yml';
const WAIT_TIMEOUT_S = '180';

function compose(args: string[], env: Record<string, string> = {}): string {
  return execFileSync('docker', ['compose', '-f', COMPOSE_FILE, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...env },
  });
}

function restoreEmptyStoragePrefix(): void {
  compose(['up', '-d', '--wait', '--wait-timeout', WAIT_TIMEOUT_S, '--no-deps', 'api'], {
    S3_KEY_PREFIX: '',
  });
}

export default async function globalTeardown(): Promise<void> {
  const path = manifestPath();
  const keepFixtures = process.env.E2E_KEEP_FIXTURES === '1';
  try {
    if (!keepFixtures && existsSync(path)) {
      const manifest = readManifest();
      // Removes every object under e2e/{run_id}/ (verified empty) and then the
      // run rows, including immutable final anamneses. It must run even when
      // the specs failed, so the try/finally below only handles the prefix.
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
  } finally {
    // Session state files hold live cookies: never leave them on disk, and
    // whether cleanup succeeded or not the API must not keep writing under a
    // finished run prefix.
    rmSync(sessionStateDir(), { recursive: true, force: true });
    restoreEmptyStoragePrefix();
  }
}
