import assert from 'node:assert/strict';
import test from 'node:test';

import { evaluateAudit } from './audit-js.mjs';

const mitigated = {
  module_name: 'braces',
  github_advisory_id: 'GHSA-vfj7-8cjw-p6xm',
  severity: 'high',
  findings: [
    {
      version: '3.0.3',
      dev: true,
      paths: ['apps__web>eslint-config-next>fast-glob>micromatch>braces'],
    },
  ],
};
function report(advisories) {
  const vulnerabilities = { info: 0, low: 0, moderate: 0, high: 0, critical: 0 };
  for (const advisory of advisories) vulnerabilities[advisory.severity] += 1;
  return {
    advisories: Object.fromEntries(advisories.map((item, index) => [index, item])),
    metadata: { vulnerabilities },
  };
}

test('tolerates only the exact patched ESLint dependency advisory', () => {
  assert.deepEqual(evaluateAudit(report([mitigated])), { blocked: [], mitigated: [mitigated] });
});
test('blocks the same advisory for another version, production dependency or path', () => {
  for (const finding of [
    { ...mitigated.findings[0], version: '3.0.2' },
    { ...mitigated.findings[0], dev: false },
    { ...mitigated.findings[0], paths: ['apps__web>another-package>braces'] },
  ]) {
    assert.equal(evaluateAudit(report([{ ...mitigated, findings: [finding] }])).blocked.length, 1);
  }
});
test('blocks every other high or critical advisory even alongside the mitigation', () => {
  const high = { ...mitigated, github_advisory_id: 'GHSA-other-high', module_name: 'other' };
  const critical = { ...high, severity: 'critical', github_advisory_id: 'GHSA-other-critical' };
  assert.deepEqual(evaluateAudit(report([mitigated, high, critical])).blocked, [high, critical]);
});
test('allows lower severity reports through the high severity gate', () => {
  assert.equal(evaluateAudit(report([{ ...mitigated, severity: 'moderate' }])).blocked.length, 0);
});
test('fails closed for errors, missing fields and unrecognized severity', () => {
  for (const value of [
    { error: { code: 'registry failure' } },
    {},
    { advisories: {} },
    report([{ ...mitigated, severity: 'unexpected' }]),
  ]) {
    assert.throws(() => evaluateAudit(value));
  }
});
test('fails closed when vulnerability counts do not match the advisory report', () => {
  const value = report([mitigated]);
  value.metadata.vulnerabilities.high = 2;
  assert.throws(() => evaluateAudit(value));
});
