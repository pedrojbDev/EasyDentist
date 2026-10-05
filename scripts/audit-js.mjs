import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const severities = ['info', 'low', 'moderate', 'high', 'critical'];

export function evaluateAudit(report) {
  if (
    !report ||
    report.error ||
    !report.advisories ||
    Array.isArray(report.advisories) ||
    typeof report.advisories !== 'object' ||
    !report.metadata?.vulnerabilities
  ) {
    throw new Error('Invalid or incomplete pnpm audit report');
  }
  const counts = Object.fromEntries(severities.map((severity) => [severity, 0]));
  const blocked = [];
  const mitigated = [];
  for (const advisory of Object.values(report.advisories)) {
    if (
      !advisory ||
      !severities.includes(advisory.severity) ||
      typeof advisory.module_name !== 'string' ||
      typeof advisory.github_advisory_id !== 'string'
    ) {
      throw new Error('Unrecognized pnpm advisory');
    }
    counts[advisory.severity] += 1;
    const locallyPatched =
      advisory.module_name === 'braces' &&
      advisory.github_advisory_id === 'GHSA-vfj7-8cjw-p6xm' &&
      Array.isArray(advisory.findings) &&
      advisory.findings.length > 0 &&
      advisory.findings.every(
        (finding) =>
          finding.version === '3.0.3' &&
          finding.dev === true &&
          Array.isArray(finding.paths) &&
          finding.paths.length > 0 &&
          finding.paths.every(
            (path) =>
              typeof path === 'string' &&
              path.includes('>eslint-config-next>') &&
              path.endsWith('>braces'),
          ),
      );
    if (locallyPatched) mitigated.push(advisory);
    else if (['high', 'critical'].includes(advisory.severity)) blocked.push(advisory);
  }
  for (const severity of severities) {
    if (report.metadata.vulnerabilities[severity] !== counts[severity]) {
      throw new Error('Incomplete pnpm advisory counts');
    }
  }
  return { blocked, mitigated };
}

function main() {
  const result = spawnSync('pnpm', ['audit', '--json'], {
    encoding: 'utf8',
    maxBuffer: 4 * 1024 * 1024,
  });
  if (result.error || result.signal || ![0, 1].includes(result.status)) {
    throw new Error('pnpm audit did not complete');
  }
  const report = JSON.parse(result.stdout);
  const { blocked, mitigated } = evaluateAudit(report);
  if (result.status !== 0 && Object.keys(report.advisories).length === 0) {
    throw new Error('pnpm audit failed without a valid advisory report');
  }
  for (const advisory of mitigated) {
    console.log(
      `Locally mitigated: ${advisory.github_advisory_id} (${advisory.module_name}@3.0.3, ESLint development dependency)`,
    );
  }
  for (const advisory of blocked) {
    console.error(
      `Blocked: ${advisory.severity} ${advisory.github_advisory_id} (${advisory.module_name})`,
    );
  }
  console.log(
    `Full registry audit: ${blocked.length} unmitigated high/critical advisories; ${mitigated.length} locally mitigated.`,
  );
  process.exitCode = blocked.length ? 1 : 0;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    main();
  } catch (cause) {
    console.error(cause.message);
    process.exitCode = 1;
  }
}
