import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { tmpdir } from 'node:os';

import {
  applyPolicy,
  createExceptionSet,
  discoverInstalledPackages,
  evaluateLicense,
  normalizeLicense,
} from './check-js-licenses.mjs';

function withVirtualStore(callback) {
  const workspacePath = mkdtempSync(join(tmpdir(), 'easydentist-license-test-'));
  const virtualStorePath = join(workspacePath, 'node_modules', '.pnpm');
  mkdirSync(virtualStorePath, { recursive: true });

  try {
    callback(virtualStorePath);
  } finally {
    rmSync(workspacePath, { force: true, recursive: true });
  }
}

function writePackage(virtualStorePath, storeEntry, packageName, manifest) {
  const packagePath = join(virtualStorePath, storeEntry, 'node_modules', ...packageName.split('/'));
  mkdirSync(packagePath, { recursive: true });
  writeFileSync(join(packagePath, 'package.json'), JSON.stringify(manifest));
  return packagePath;
}

test('accepts an explicitly allowlisted license', () => {
  assert.deepEqual(
    evaluateLicense({ name: 'permissive-package', version: '1.0.0', license: 'MIT' }, new Set()),
    { status: 'allowed', license: 'MIT' },
  );
});

test('blocks GPL, AGPL, and SSPL licenses', () => {
  assert.deepEqual(
    evaluateLicense(
      { name: 'copyleft-package', version: '1.0.0', license: 'GPL-3.0-only' },
      new Set(),
    ),
    { status: 'blocked', license: 'GPL-3.0-only' },
  );
  assert.deepEqual(
    evaluateLicense({ name: 'gpl-package', version: '1.0.0', license: 'GPL' }, new Set()),
    { status: 'blocked', license: 'GPL' },
  );
  assert.deepEqual(
    evaluateLicense(
      { name: 'agpl-package', version: '1.0.0', license: 'AGPL-3.0-only' },
      new Set(),
    ),
    { status: 'blocked', license: 'AGPL-3.0-only' },
  );
  assert.deepEqual(
    evaluateLicense({ name: 'sspl-package', version: '1.0.0', license: 'SSPL-1.0' }, new Set()),
    { status: 'blocked', license: 'SSPL-1.0' },
  );
});

test('requires review for an absent license and blocks compound copyleft expressions', () => {
  assert.deepEqual(
    evaluateLicense({ name: 'unknown-package', version: '1.0.0', license: '' }, new Set()),
    { status: 'review', license: '' },
  );
  assert.deepEqual(
    evaluateLicense(
      { name: 'compound-package', version: '1.0.0', license: 'MIT OR GPL-3.0-only' },
      new Set(),
    ),
    { status: 'blocked', license: 'MIT OR GPL-3.0-only' },
  );
  assert.deepEqual(
    evaluateLicense(
      { name: 'alternate-separator-package', version: '1.0.0', license: 'MIT/GPL-3.0-only' },
      new Set(),
    ),
    { status: 'blocked', license: 'MIT/GPL-3.0-only' },
  );
});

test('allows only an exact package, version, and license exception', () => {
  const exceptions = createExceptionSet([
    { package: 'reviewed-package', version: '2.1.0', license: 'Python-2.0' },
  ]);

  assert.deepEqual(
    evaluateLicense(
      { name: 'reviewed-package', version: '2.1.0', license: 'Python-2.0' },
      exceptions,
    ),
    { status: 'exception', license: 'Python-2.0' },
  );
  assert.deepEqual(
    evaluateLicense(
      { name: 'reviewed-package', version: '2.1.1', license: 'Python-2.0' },
      exceptions,
    ),
    { status: 'review', license: 'Python-2.0' },
  );
});

test('discovers physical unscoped, scoped, development, and transitive packages once', () => {
  withVirtualStore((virtualStorePath) => {
    writePackage(virtualStorePath, 'runtime@1.0.0', 'runtime', {
      name: 'runtime',
      version: '1.0.0',
      license: 'MIT',
    });
    writePackage(virtualStorePath, 'runtime@1.0.0_peer@1.0.0', 'runtime', {
      name: 'runtime',
      version: '1.0.0',
      license: 'MIT',
    });
    writePackage(virtualStorePath, '@scope+widget@2.0.0', '@scope/widget', {
      name: '@scope/widget',
      version: '2.0.0',
      license: 'BSD-3-Clause',
    });
    writePackage(virtualStorePath, 'dev-tool@3.0.0', 'dev-tool', {
      name: 'dev-tool',
      version: '3.0.0',
      license: 'ISC',
    });
    writePackage(virtualStorePath, 'transitive@4.0.0', 'transitive', {
      name: 'transitive',
      version: '4.0.0',
      license: 'Apache-2.0',
    });
    symlinkSync(
      join(virtualStorePath, 'transitive@4.0.0', 'node_modules', 'transitive'),
      join(virtualStorePath, 'runtime@1.0.0', 'node_modules', 'transitive'),
    );

    assert.deepEqual(discoverInstalledPackages(virtualStorePath), [
      { name: '@scope/widget', version: '2.0.0', license: 'BSD-3-Clause' },
      { name: 'dev-tool', version: '3.0.0', license: 'ISC' },
      { name: 'runtime', version: '1.0.0', license: 'MIT' },
      { name: 'transitive', version: '4.0.0', license: 'Apache-2.0' },
    ]);
  });
});

test('discovers bundled physical dependencies and applies the license policy to them', () => {
  withVirtualStore((virtualStorePath) => {
    const parentPath = writePackage(virtualStorePath, 'parent@1.0.0', 'parent', {
      name: 'parent',
      version: '1.0.0',
      license: 'MIT',
    });
    const bundledPath = join(parentPath, 'node_modules', 'bundled-gpl');
    mkdirSync(bundledPath, { recursive: true });
    writeFileSync(
      join(bundledPath, 'package.json'),
      JSON.stringify({ name: 'bundled-gpl', version: '1.0.0', license: 'GPL-3.0-only' }),
    );

    const failures = applyPolicy(discoverInstalledPackages(virtualStorePath), new Set());

    assert.deepEqual(failures, [
      {
        packageInfo: { name: 'bundled-gpl', version: '1.0.0', license: 'GPL-3.0-only' },
        decision: { status: 'blocked', license: 'GPL-3.0-only' },
      },
    ]);
  });
});

test('fails closed when a dependency symlink escapes the virtual store', () => {
  withVirtualStore((virtualStorePath) => {
    const packagePath = writePackage(virtualStorePath, 'parent@1.0.0', 'parent', {
      name: 'parent',
      version: '1.0.0',
      license: 'MIT',
    });
    mkdirSync(join(packagePath, 'node_modules'), { recursive: true });
    symlinkSync(tmpdir(), join(packagePath, 'node_modules', 'external'));

    assert.throws(
      () => discoverInstalledPackages(virtualStorePath),
      /Dependency symlink escapes virtual store/,
    );
  });
});

test('fails closed when a store entry lacks node_modules', () => {
  withVirtualStore((virtualStorePath) => {
    const incompleteEntryPath = join(virtualStorePath, 'incomplete@1.0.0');
    mkdirSync(incompleteEntryPath, { recursive: true });

    assert.throws(
      () => discoverInstalledPackages(virtualStorePath),
      new RegExp(`Missing node_modules directory for store entry: ${incompleteEntryPath}`),
    );
  });
});

test('fails closed when a physical manifest omits required identity or license fields', () => {
  withVirtualStore((virtualStorePath) => {
    const packagePath = writePackage(virtualStorePath, 'incomplete@1.0.0', 'incomplete', {
      name: 'incomplete',
      version: '1.0.0',
    });

    assert.throws(
      () => discoverInstalledPackages(virtualStorePath),
      new RegExp(`Invalid package manifest: ${packagePath}/package\\.json`),
    );
  });
});

test('fails closed when a physical package directory lacks package.json', () => {
  withVirtualStore((virtualStorePath) => {
    const packagePath = join(virtualStorePath, 'broken@1.0.0', 'node_modules', 'broken');
    mkdirSync(packagePath, { recursive: true });

    assert.throws(
      () => discoverInstalledPackages(virtualStorePath),
      new RegExp(`Missing package manifest: ${packagePath}/package\\.json`),
    );
  });
});

test('normalizes whitespace without collapsing compound license expressions', () => {
  assert.equal(normalizeLicense('  BSD-3-Clause  '), 'BSD-3-Clause');
  assert.equal(normalizeLicense(' MIT OR Apache-2.0 '), 'MIT OR Apache-2.0');
});
