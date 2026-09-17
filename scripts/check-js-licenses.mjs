import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync } from 'node:fs';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const allowedLicenses = new Set(['Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC', 'MIT']);
const blockedLicenses = new Set(['AGPL', 'GPL', 'SSPL']);
const blockedLicensePrefixes = ['AGPL-', 'GPL-', 'SSPL-'];
const blockedLicenseToken = /(^|[^a-z0-9])(AGPL|GPL|SSPL)(?=$|[^a-z0-9])/i;

export function normalizeLicense(license) {
  return typeof license === 'string' ? license.trim() : '';
}

export function exceptionKey({ name, version, license }) {
  return `${name}@${version}:${normalizeLicense(license)}`;
}

export function createExceptionSet(entries) {
  return new Set(
    entries.map(({ package: packageName, version, license }) =>
      exceptionKey({ name: packageName, version, license }),
    ),
  );
}

export function evaluateLicense(packageInfo, exceptions) {
  const license = normalizeLicense(packageInfo.license);

  if (allowedLicenses.has(license)) {
    return { status: 'allowed', license };
  }

  if (
    blockedLicenses.has(license) ||
    blockedLicensePrefixes.some((prefix) => license.startsWith(prefix)) ||
    blockedLicenseToken.test(license)
  ) {
    return { status: 'blocked', license };
  }

  if (exceptions.has(exceptionKey({ ...packageInfo, license }))) {
    return { status: 'exception', license };
  }

  return { status: 'review', license };
}

export function discoverInstalledPackages(virtualStorePath) {
  const packages = new Map();
  const resolvedVirtualStorePath = realpathSync(virtualStorePath);

  for (const storeEntry of directoryEntries(virtualStorePath)) {
    const storeEntryPath = resolve(virtualStorePath, storeEntry.name);
    if (storeEntry.isSymbolicLink()) {
      validateDependencySymlink(storeEntryPath, resolvedVirtualStorePath);
      continue;
    }

    if (!storeEntry.isDirectory()) {
      continue;
    }

    if (storeEntry.name === 'node_modules') {
      // pnpm uses this directory for hoisted/workspace links. Every third-party
      // package target is audited from its physical virtual-store entry.
      continue;
    }

    const modulesPath = resolve(storeEntryPath, 'node_modules');
    if (!existsSync(modulesPath) || !lstatSync(modulesPath).isDirectory()) {
      throw new Error(`Missing node_modules directory for store entry: ${storeEntryPath}`);
    }

    scanModulesDirectory(modulesPath, resolvedVirtualStorePath, packages);
  }

  return [...packages.values()].sort((left, right) =>
    `${left.name}@${left.version}`.localeCompare(`${right.name}@${right.version}`),
  );
}

function directoryEntries(path) {
  return readdirSync(path, { withFileTypes: true });
}

function scanModulesDirectory(modulesPath, virtualStorePath, packages) {
  for (const entry of directoryEntries(modulesPath)) {
    if (entry.name === '.bin') {
      continue;
    }

    const entryPath = resolve(modulesPath, entry.name);
    if (entry.isSymbolicLink()) {
      validateDependencySymlink(entryPath, virtualStorePath);
      continue;
    }

    if (!entry.isDirectory()) {
      continue;
    }

    if (entry.name.startsWith('@')) {
      for (const scopedEntry of directoryEntries(entryPath)) {
        if (scopedEntry.isSymbolicLink()) {
          validateDependencySymlink(resolve(entryPath, scopedEntry.name), virtualStorePath);
        } else if (scopedEntry.isDirectory()) {
          scanPackageDirectory(resolve(entryPath, scopedEntry.name), virtualStorePath, packages);
        }
      }
    } else {
      scanPackageDirectory(entryPath, virtualStorePath, packages);
    }
  }
}

function scanPackageDirectory(packagePath, virtualStorePath, packages) {
  const manifestPath = resolve(packagePath, 'package.json');
  if (!existsSync(manifestPath)) {
    throw new Error(`Missing package manifest: ${manifestPath}`);
  }

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  if (
    typeof manifest.name !== 'string' ||
    manifest.name.length === 0 ||
    typeof manifest.version !== 'string' ||
    manifest.version.length === 0 ||
    typeof manifest.license !== 'string'
  ) {
    throw new Error(`Invalid package manifest: ${manifestPath}`);
  }

  const packageInfo = {
    name: manifest.name,
    version: manifest.version,
    license: normalizeLicense(manifest.license),
  };
  const packageId = `${packageInfo.name}@${packageInfo.version}`;
  const existing = packages.get(packageId);

  if (existing && existing.license !== packageInfo.license) {
    throw new Error(`Conflicting licenses for installed package: ${packageId}`);
  }

  packages.set(packageId, packageInfo);

  const bundledModulesPath = resolve(packagePath, 'node_modules');
  if (existsSync(bundledModulesPath)) {
    if (!lstatSync(bundledModulesPath).isDirectory()) {
      throw new Error(`Invalid bundled node_modules directory: ${bundledModulesPath}`);
    }
    scanModulesDirectory(bundledModulesPath, virtualStorePath, packages);
  }
}

function validateDependencySymlink(symlinkPath, virtualStorePath) {
  const targetPath = realpathSync(symlinkPath);
  if (!isWithin(virtualStorePath, targetPath)) {
    throw new Error(`Dependency symlink escapes virtual store: ${symlinkPath}`);
  }

  const manifestPath = resolve(targetPath, 'package.json');
  if (!existsSync(manifestPath)) {
    throw new Error(`Dependency symlink target lacks package manifest: ${symlinkPath}`);
  }
}

function isWithin(rootPath, candidatePath) {
  const pathFromRoot = relative(rootPath, candidatePath);
  return (
    pathFromRoot === '' ||
    (!pathFromRoot.startsWith(`..${sep}`) && pathFromRoot !== '..' && !isAbsolute(pathFromRoot))
  );
}

export function applyPolicy(packages, exceptions) {
  return packages
    .map((packageInfo) => ({ packageInfo, decision: evaluateLicense(packageInfo, exceptions) }))
    .filter(({ decision }) => decision.status === 'blocked' || decision.status === 'review');
}

export function runLicenseCheck({ cwd, readFile = readFileSync }) {
  const exceptionPath = resolve(import.meta.dirname, 'js-license-exceptions.json');
  const exceptions = createExceptionSet(JSON.parse(readFile(exceptionPath, 'utf8')));
  const packages = discoverInstalledPackages(resolve(cwd, 'node_modules', '.pnpm'));
  const failures = applyPolicy(packages, exceptions);

  if (failures.length > 0) {
    const report = failures
      .map(
        ({ packageInfo, decision }) =>
          `${packageInfo.name}@${packageInfo.version}: ${decision.license || 'unknown license'} (${decision.status})`,
      )
      .sort()
      .join('\n');
    throw new Error(`Manual license review required:\n${report}`);
  }

  return packages.length;
}

function isCliEntryPoint() {
  return process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
}

if (isCliEntryPoint()) {
  const scanned = runLicenseCheck({ cwd: resolve(import.meta.dirname, '..') });
  console.log(`${scanned} installed JavaScript packages comply with the license allowlist.`);
}
