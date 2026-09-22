#!/usr/bin/env sh
set -eu

# Reproducible scanner over versioned files with explicit patterns. It prints
# file:line and the rule name, never the matched value, so findings do not leak
# into CI logs. Documented local values are allowed inline; production values
# must never be committed.

failures=0

# Local development values documented in infra/.env.example, docker-compose and
# test fixtures. They are not production secrets; anything else is a finding.
ALLOWED_LOCAL_VALUES='easydentist-development-secret-not-for-production|easydentist-local-only|easydentist-app-local-only|easydentist-migrator-local-only|test-auth-secret-with-enough-bytes-123|not-for-production|local-only|:secret@|:password@|password-12345|wrong-password-12345|senha-secreta-|senha-nova-|token-value|not-a-stored-token|definitely-not-a-token|too-short|secret-token|token-1|token-4|must-not-persist|m16-cookie-password'

report() {
  rule=$1
  matches=$2
  if [ -n "$matches" ]; then
    echo "secret-scan: $rule" >&2
    printf '%s\n' "$matches" | cut -d: -f1-2 >&2
    failures=$((failures + 1))
  fi
}

scan() {
  rule=$1
  pattern=$2
  shift 2
  matches=$(
    {
      git grep -nE -e "$pattern" -- "$@" || true
    } | grep -vE "$ALLOWED_LOCAL_VALUES" || true
  )
  report "$rule" "$matches"
}

scan 'private-key' '-----BEGIN [A-Z ]*PRIVATE KEY-----'
scan 'aws-access-key' 'AKIA[0-9A-Z]{16}'
scan 'github-token' 'gh[pousr]_[A-Za-z0-9]{30,}'
scan 'slack-token' 'xox[baprs]-[A-Za-z0-9-]{10,}'
scan 'provider-api-key' 'sk-[A-Za-z0-9]{20,}'
scan 'credential-url' '://[^/@[:space:]]+:[^/@[:space:]]+@'
scan 'assigned-secret' '(password|passwd|secret|token|api[_-]?key)["'\'']?[[:space:]]*[:=][[:space:]]*["'\''][A-Za-z0-9_./+=-]{8,}["'\'']'

unexpected_env_files=$(git ls-files | grep -E '(^|/)\.env($|\.)' | grep -vE '\.env\.example$' || true)
report 'versioned-env-file' "$unexpected_env_files"

tracked_artifacts=$(
  git ls-files | grep -E '(^|/)(test-results|playwright-report)/|^artifacts/|\.dump$|\.dump\.gz$' || true
)
report 'versioned-artifact' "$tracked_artifacts"

for ignored in .env artifacts/e2e/manifest.json artifacts/e2e/test-results/trace.zip; do
  if ! git check-ignore -q "$ignored"; then
    echo "secret-scan: $ignored is not ignored by git" >&2
    failures=$((failures + 1))
  fi
done

if [ "$failures" -ne 0 ]; then
  echo "secret scan: $failures rule group(s) failed" >&2
  exit 1
fi

echo 'secret scan: clean'
