#!/usr/bin/env bash
# Hermetic contract tests for GitHub API retry/defer behavior and Antigravity wiring.
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
module="$repo_root/scripts/github-api-resilience.cjs"

node - "$module" <<'NODE'
const assert = require('node:assert/strict');
const modulePath = process.argv[2];
(async () => {
const {
  GitHubRetryDeferredError,
  classifyGitHubError,
  computeWaitSeconds,
  dispatchWorkflow,
  formatRetryProgress,
  readPrimaryRateLimit,
  requestGitHubApi,
  retryGitHub,
} = require(modulePath);

const error = (message, status, headers = {}) => Object.assign(new Error(message), {
  status,
  response: {status, headers},
});

const primary = classifyGitHubError(error('API rate limit exceeded', 403, {
  'x-ratelimit-remaining': '0',
  'x-ratelimit-reset': '1120',
}));
assert.equal(primary.kind, 'primary');
assert.equal(primary.retryable, true);
assert.equal(primary.resetAtSeconds, 1120);
assert.equal(computeWaitSeconds(primary, {
  attempt: 1,
  nowSeconds: 1000,
  jitterSeconds: 0,
  random: () => 0,
}), 125);

const retryAfter = classifyGitHubError(error('secondary rate limit', 403, {
  'retry-after': '90',
  'x-ratelimit-remaining': '4999',
}));
assert.equal(retryAfter.kind, 'secondary');
assert.equal(retryAfter.retryAfterSeconds, 90);
assert.equal(computeWaitSeconds(retryAfter, {
  attempt: 1,
  nowSeconds: 1000,
  jitterSeconds: 0,
  random: () => 0,
}), 90);

const contentLimit = classifyGitHubError(error(
  'temporarily blocked from content creation; was submitted too quickly',
  403,
));
assert.equal(contentLimit.kind, 'secondary');
assert.equal(computeWaitSeconds(contentLimit, {
  attempt: 3,
  nowSeconds: 1000,
  jitterSeconds: 0,
  random: () => 0,
}), 240);
assert.equal(computeWaitSeconds(contentLimit, {
  attempt: 8,
  nowSeconds: 1000,
  jitterSeconds: 0,
  maxBackoffSeconds: 600,
  random: () => 0,
}), 600);

assert.deepEqual(classifyGitHubError(error('Service unavailable', 503)).kind, 'transient');
assert.equal(classifyGitHubError(error('Bad credentials', 401)).retryable, false);
assert.equal(classifyGitHubError(error('Validation failed', 422)).retryable, false);

let rateCalls = 0;
const rate = await readPrimaryRateLimit({
  request: async (route) => {
    rateCalls += 1;
    assert.equal(route, 'GET /rate_limit');
    return {data: {resources: {core: {limit: 5000, remaining: 0, reset: 1120}}}};
  },
});
assert.deepEqual(rate, {limit: 5000, remaining: 0, resetAtSeconds: 1120, resource: 'core'});
assert.equal(rateCalls, 1);

const sleeps = [];
const progress = [];
let calls = 0;
let primaryLookups = 0;
const result = await retryGitHub(async () => {
  calls += 1;
  if (calls < 3) throw error('secondary rate limit', 403);
  return 'ok';
}, {
  operationName: 'publish exact-head receipt',
  maxAttempts: 4,
  totalWaitBudgetSeconds: 600,
  jitterSeconds: 0,
  nowSeconds: () => 1000 + sleeps.reduce((sum, value) => sum + value, 0),
  random: () => 0,
  sleepSeconds: async (seconds) => sleeps.push(seconds),
  readPrimaryRateLimit: async () => {
    primaryLookups += 1;
    return rate;
  },
  onProgress: (event) => progress.push(event),
});
assert.equal(result, 'ok');
assert.deepEqual(sleeps, [60, 120]);
assert.equal(primaryLookups, 0, 'secondary cooldown must not poll /rate_limit');
assert.equal(progress.length, 2);
assert.match(formatRetryProgress(progress[0]), /^\[WAIT\]/);
assert.match(formatRetryProgress(progress[0]), /publish exact-head receipt/);
assert.match(formatRetryProgress(progress[0]), /attempt 1\/4/);
assert.match(formatRetryProgress(progress[0]), /next attempt 1970-01-01T00:17:40.000Z/);

let primaryAttempts = 0;
const primarySleeps = [];
await retryGitHub(async () => {
  primaryAttempts += 1;
  if (primaryAttempts === 1) {
    throw error('API rate limit exceeded', 403, {'x-ratelimit-remaining': '0'});
  }
  return 'primary recovered';
}, {
  operationName: 'read fleet state',
  maxAttempts: 2,
  totalWaitBudgetSeconds: 200,
  jitterSeconds: 0,
  nowSeconds: () => 1000,
  random: () => 0,
  sleepSeconds: async (seconds) => primarySleeps.push(seconds),
  readPrimaryRateLimit: async () => ({
    limit: 5000,
    remaining: 0,
    resetAtSeconds: 1120,
    resource: 'core',
  }),
  onProgress: () => {},
});
assert.deepEqual(primarySleeps, [125]);

let deferred;
try {
  await retryGitHub(async () => {
    throw error('secondary rate limit', 403, {'retry-after': '120'});
  }, {
    operationName: 'create exact-head comment',
    maxAttempts: 3,
    totalWaitBudgetSeconds: 60,
    jitterSeconds: 0,
    nowSeconds: () => 1000,
    random: () => 0,
    sleepSeconds: async () => assert.fail('must not sleep past the wait budget'),
    onProgress: () => {},
  });
} catch (caught) {
  deferred = caught;
}
assert.ok(deferred instanceof GitHubRetryDeferredError);
assert.equal(deferred.code, 84);
assert.equal(deferred.kind, 'secondary');
assert.equal(deferred.waitSeconds, 120);

let fatalCalls = 0;
await assert.rejects(
  retryGitHub(async () => {
    fatalCalls += 1;
    throw error('Validation failed', 422);
  }, {
    operationName: 'invalid mutation',
    sleepSeconds: async () => assert.fail('fatal errors must not sleep'),
    onProgress: () => {},
  }),
  /Validation failed/,
);
assert.equal(fatalCalls, 1);

const response = (status, body, headers = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: {
    get: (name) => Object.entries(headers).find(
      ([key]) => key.toLowerCase() === name.toLowerCase(),
    )?.[1] ?? null,
  },
  text: async () => JSON.stringify(body),
});
const requestSleeps = [];
const requestUrls = [];
const requestResult = await requestGitHubApi('repos/f5-sales-demo/example', {
  token: 'synthetic-token',
  jitterSeconds: 0,
  sleepSeconds: async (seconds) => requestSleeps.push(seconds),
  onProgress: () => {},
  fetch: async (url, options) => {
    requestUrls.push(url);
    assert.equal(options.headers.authorization, 'Bearer synthetic-token');
    if (requestUrls.length === 1) {
      return response(403, {message: 'secondary rate limit'}, {'Retry-After': '7'});
    }
    return response(200, {repository: 'f5-sales-demo/example'});
  },
});
assert.deepEqual(requestSleeps, [7]);
assert.deepEqual(requestResult, {repository: 'f5-sales-demo/example'});
assert.equal(requestUrls.some((url) => url.endsWith('/rate_limit')), false);

const primaryUrls = [];
const primaryRequestSleeps = [];
let repositoryCalls = 0;
await requestGitHubApi('repos/f5-sales-demo/example', {
  token: 'synthetic-token',
  jitterSeconds: 0,
  nowSeconds: () => 1000,
  sleepSeconds: async (seconds) => primaryRequestSleeps.push(seconds),
  onProgress: () => {},
  fetch: async (url) => {
    primaryUrls.push(url);
    if (url.endsWith('/rate_limit')) {
      return response(200, {resources: {core: {limit: 5000, remaining: 0, reset: 1120}}});
    }
    repositoryCalls += 1;
    if (repositoryCalls === 1) return response(403, {message: 'API rate limit exceeded'});
    return response(200, {repository: 'f5-sales-demo/example'});
  },
});
assert.deepEqual(primaryRequestSleeps, [125]);
assert.equal(primaryUrls.filter((url) => url.endsWith('/rate_limit')).length, 1);

const exactSource = '1'.repeat(40);
const exactTitle = `Enforce Repository Settings @ ${exactSource}`;
const dispatchResponses = [
  response(200, {workflow_runs: [{
    id: 101,
    event: 'workflow_dispatch',
    display_title: exactTitle,
    status: 'completed',
    conclusion: 'failure',
    html_url: 'https://github.example/runs/101',
  }]}),
  response(503, {message: 'Service unavailable'}),
  response(200, {workflow_runs: [{
    id: 102,
    event: 'workflow_dispatch',
    display_title: exactTitle,
    status: 'in_progress',
    conclusion: null,
    html_url: 'https://github.example/runs/102',
  }]}),
];
const dispatchRequests = [];
const dispatchSleeps = [];
const recoveredDispatch = await dispatchWorkflow({
  repository: 'f5-sales-demo/example',
  sourceSha: exactSource,
  token: 'synthetic-token',
  jitterSeconds: 0,
  sleepSeconds: async (seconds) => dispatchSleeps.push(seconds),
  onProgress: () => {},
  fetch: async (url, options) => {
    dispatchRequests.push({url, options});
    return dispatchResponses.shift();
  },
});
assert.equal(recoveredDispatch.state, 'recovered');
assert.equal(recoveredDispatch.run.id, 102);
assert.deepEqual(dispatchSleeps, [5]);
assert.deepEqual(dispatchRequests.map(({options}) => options.method), ['GET', 'POST', 'GET']);
assert.equal(
  dispatchRequests.filter(({options}) => options.method === 'POST').length,
  1,
  'an ambiguous mutation must recover its exact receipt instead of posting twice',
);
assert.deepEqual(JSON.parse(dispatchRequests[1].options.body), {
  ref: 'main',
  inputs: {source_sha: exactSource},
});

const existingRequests = [];
const existingDispatch = await dispatchWorkflow({
  repository: 'f5-sales-demo/example',
  sourceSha: exactSource,
  token: 'synthetic-token',
  fetch: async (url, options) => {
    existingRequests.push({url, options});
    return response(200, {workflow_runs: [{
      id: 103,
      event: 'workflow_dispatch',
      display_title: exactTitle,
      status: 'completed',
      conclusion: 'success',
      html_url: 'https://github.example/runs/103',
    }]});
  },
});
assert.equal(existingDispatch.state, 'existing');
assert.equal(existingRequests.length, 1);
assert.equal(existingRequests[0].options.method, 'GET');

const limitedResponses = [
  response(200, {workflow_runs: []}),
  response(403, {message: 'secondary rate limit'}, {'Retry-After': '7'}),
  response(200, {workflow_runs: []}),
  response(204, null),
];
const limitedRequests = [];
const limitedSleeps = [];
const limitedDispatch = await dispatchWorkflow({
  repository: 'f5-sales-demo/example',
  sourceSha: exactSource,
  token: 'synthetic-token',
  jitterSeconds: 0,
  sleepSeconds: async (seconds) => limitedSleeps.push(seconds),
  onProgress: () => {},
  fetch: async (url, options) => {
    limitedRequests.push({url, options});
    return limitedResponses.shift();
  },
});
assert.equal(limitedDispatch.state, 'dispatched');
assert.deepEqual(limitedSleeps, [7]);
assert.deepEqual(limitedRequests.map(({options}) => options.method), ['GET', 'POST', 'GET', 'POST']);
assert.equal(
  limitedRequests.some(({url}) => url.endsWith('/rate_limit')),
  false,
  'secondary dispatch cooldown must not poll GitHub',
);

await assert.rejects(
  dispatchWorkflow({
    repository: 'f5-sales-demo/example',
    sourceSha: 'not-a-sha',
    token: 'synthetic-token',
  }),
  /source SHA/,
);

console.log('[OK] GitHub API retry classifications and wait contract');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
NODE

fail=0
check() {
  local label="$1"
  shift
  if "$@"; then
    printf '[OK] %s\n' "$label"
  else
    printf '[FAIL] %s\n' "$label" >&2
    fail=1
  fi
}

skip_source_contract() {
  printf '[SKIP] %s -- docs-control-only subject is absent\n' "$1"
}

# shellcheck disable=SC2329 # Invoked indirectly through check.
validate_downstream_caller() {
  python3 - "$@" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
job, reusable_workflow, pull_request_permission, *secret_names = sys.argv[2:]
text = path.read_text(encoding="utf-8")


def reject(message):
    print(f"{path}: {message}", file=sys.stderr)
    raise SystemExit(1)


def indented_block(name):
    matches = list(re.finditer(rf"(?m)^    {re.escape(name)}:\s*(?:#.*)?$", text))
    if len(matches) != 1:
        reject(f"expected one job-level {name} block, found {len(matches)}")
    lines = text[matches[0].end():].splitlines()
    values = {}
    for line in lines:
        if not line.strip():
            continue
        indentation = len(line) - len(line.lstrip(" "))
        if indentation <= 4:
            break
        match = re.fullmatch(r"      ([A-Za-z0-9_-]+):\s*(.*?)\s*", line)
        if not match:
            reject(f"invalid {name} entry: {line.strip()}")
        key, value = match.groups()
        value = re.sub(r"\s+#.*$", "", value)
        if key in values:
            reject(f"duplicate {name} entry: {key}")
        values[key] = value
    return values


if len(re.findall(r"(?m)^permissions:\s*\{\}\s*$", text)) != 1:
    reject("workflow-level permissions must be exactly permissions: {}")

job_matches = re.findall(rf"(?m)^  {re.escape(job)}:\s*$", text)
if len(job_matches) != 1:
    reject(f"expected exactly one {job} job")

uses_pattern = (
    rf"(?m)^    uses: f5-sales-demo/docs-control/\.github/workflows/"
    rf"{re.escape(reusable_workflow)}@([0-9a-f]{{40}})\s*$"
)
pins = re.findall(uses_pattern, text)
if len(pins) != 1:
    reject(f"expected one immutable {reusable_workflow} pin, found {len(pins)}")

input_block = re.search(r"(?m)^    inputs:\s*$", text)
if not input_block:
    reject("workflow_dispatch inputs block is absent")
input_lines = text[input_block.end():].splitlines()
declared_inputs = []
for line in input_lines:
    if not line.strip():
        continue
    indentation = len(line) - len(line.lstrip(" "))
    if indentation <= 4:
        break
    match = re.fullmatch(r"      ([A-Za-z0-9_-]+):\s*", line)
    if match:
        declared_inputs.append(match.group(1))
expected_inputs = ["pr_number", "expected_base_sha", "expected_head_sha"]
if job == "translate":
    expected_inputs.append("reconcile_all")
if declared_inputs != expected_inputs:
    reject(f"unexpected workflow_dispatch inputs: {declared_inputs}")

expected_with = {
    "pr_number": "${{ inputs.pr_number }}",
    "expected_base_sha": "${{ inputs.expected_base_sha }}",
    "expected_head_sha": "${{ inputs.expected_head_sha }}",
}
if job == "translate":
    expected_with["reconcile_all"] = "${{ inputs.reconcile_all }}"
if indented_block("with") != expected_with:
    reject("job must pass only the approved exact pull-request inputs")

expected_permissions = {
    "contents": "read",
    "pull-requests": pull_request_permission,
}
if indented_block("permissions") != expected_permissions:
    reject(f"unexpected job permissions; expected {expected_permissions}")

expected_secrets = {name: f"${{{{ secrets.{name} }}}}" for name in secret_names}
if indented_block("secrets") != expected_secrets:
    reject(f"unexpected secret mappings; expected {sorted(expected_secrets)}")
PY
}

watcher="$repo_root/.github/workflows/antigravity-fleet-watcher.yml"
watcher_collector="$repo_root/scripts/collect-antigravity-fleet-state.sh"
review="$repo_root/.github/workflows/antigravity-review.yml"
translation="$repo_root/.github/workflows/antigravity-translate.yml"
translation_caller="$repo_root/workflows/antigravity-translate.yml"
content_reconciler="$repo_root/.github/workflows/reconcile-fleet-content.yml"
settings_reconciler="$repo_root/.github/workflows/reconcile-fleet-settings.yml"
repo_settings="$repo_root/.github/config/repo-settings.json"

credential_files=("$review")
if [ -f "$watcher" ]; then
  credential_files+=("$watcher")
fi
if [ -f "$translation_caller" ]; then
  credential_files+=("$translation_caller")
fi

check 'unconfigured GitHub App credentials are absent' \
  bash -c '! grep -qE '\''AUTOMATION_APP_ID|AUTOMATION_APP_PRIVATE_KEY|create-github-app-token'\'' "$@"' \
  _ "${credential_files[@]}"

if [ -f "$watcher" ]; then
  check 'antigravity-review.yml loads the governed retry helper' \
    grep -qF 'github-api-resilience.cjs' "$review"
  check 'antigravity-review.yml uses bounded GitHub retry' \
    grep -qF 'retryGitHub' "$review"

  check 'review receipts are exact-head markers' \
    grep -qE 'antigravity-pr-review:\$\{?[^}]*HEAD|antigravity-pr-review:\$\{report[.]receipt[.]head_sha\}' "$review"
else
  check 'downstream review caller has an immutable exact least-privilege contract' \
    validate_downstream_caller "$review" review antigravity-review.yml write \
    ANTIGRAVITY_TOKEN GCP_PROJECT_ID
fi

if [ -f "$watcher" ]; then
  check 'fleet watcher uses the existing fleet token' \
    grep -qF 'secrets.REPO_SETTINGS_TOKEN' "$watcher"
  check 'antigravity-fleet-watcher.yml loads the governed retry helper' \
    grep -qF 'github-api-resilience.cjs' "$watcher_collector"
  check 'antigravity-fleet-watcher.yml uses bounded GitHub retry' \
    grep -qF 'retryGitHub' "$watcher"
  check 'watcher redispatches failed or unpublished exact reviews' \
    grep -qF 'reviewNeedsRecovery' "$watcher_collector"
  check 'watcher emits per-repository progress heartbeats' \
    grep -qE '\[PROGRESS\].*repository' "$watcher_collector"
  check 'Free-tier contract remains explicit' \
    grep -qF 'GitHub Free-compatible' "$watcher"
  check 'central content reconciler uses the hosted release-automation route' \
    grep -qF 'runs-on: ubuntu-latest' "$content_reconciler"
  check 'central content reconciler has an explicit job name' \
    grep -qF '    name: Reconcile fleet content' "$content_reconciler"
  check 'central content reconciler binds secrets to the repository-settings environment' \
    grep -qF '    environment: repository-settings' "$content_reconciler"
  check 'central settings reconciler remains ARC-routed, push-driven, and manually dispatchable without cron' \
    bash -c "grep -qF 'runs-on: managed-socketless' '$settings_reconciler' && grep -qF 'push:' '$settings_reconciler' && grep -qF 'workflow_dispatch:' '$settings_reconciler' && ! grep -qF 'schedule:' '$settings_reconciler'"
  check 'central settings reconciler has an explicit job name' \
    grep -qF '    name: Reconcile fleet settings' "$settings_reconciler"
  check 'central settings reconciler binds secrets to the repository-settings environment' \
    grep -qF '    environment: repository-settings' "$settings_reconciler"
  check 'central workflows react to reconciliation engine changes' \
    bash -c "grep -qF -- \"- 'scripts/fleet-reconciler.cjs'\" '$content_reconciler' && grep -qF -- \"- 'scripts/github-api-resilience.cjs'\" '$content_reconciler' && grep -qF -- \"- 'scripts/fleet-reconciler.cjs'\" '$settings_reconciler' && grep -qF -- \"- 'scripts/github-api-resilience.cjs'\" '$settings_reconciler'"
  check 'central reconcilers prefer GitHub App credentials with cutover fallback' \
    bash -c "grep -qF 'create-github-app-token' '$content_reconciler' && grep -qF 'REPO_SETTINGS_TOKEN' '$content_reconciler'"
  check 'central reconciler app tokens are limited to governed repositories' \
    bash -c "grep -qF 'repositories: \${{ steps.repository-scope.outputs.repositories }}' '$content_reconciler' && grep -qF 'repositories: \${{ steps.repository-scope.outputs.repositories }}' '$settings_reconciler'"
  check 'content reconciliation requests only its required app permissions' \
    bash -c "grep -qF 'permission-contents: write' '$content_reconciler' && grep -qF 'permission-issues: write' '$content_reconciler' && grep -qF 'permission-pull-requests: write' '$content_reconciler' && grep -qF 'permission-statuses: write' '$content_reconciler'"
  check 'settings reconciliation requests only its required app permissions' \
    bash -c "grep -qF 'permission-actions: write' '$settings_reconciler' && grep -qF 'permission-administration: write' '$settings_reconciler' && grep -qF 'permission-pull-requests: read' '$settings_reconciler'"
else
  skip_source_contract 'fleet watcher wiring contract'
fi

check 'operator guidance documents secondary cooldown without polling' \
  bash -c "grep -qF 'Secondary limits never poll during cooldown' '$repo_root/CONTRIBUTING.md' && \
    grep -qF 'Retry-After' '$repo_root/CONTRIBUTING.md'"

if [ -f "$repo_root/scripts/fleet-reconciler.cjs" ]; then
  check 'central reconciliation uses the shared bounded retry helper' \
    grep -qF 'requestGitHubApi' "$repo_root/scripts/fleet-reconciler.cjs"
else
  skip_source_contract 'central reconciliation implementation contract'
fi

if [ -f "$watcher" ]; then
  check 'retry helper is managed fleet-wide' jq -e \
    '.managed_files.files | any(.src == "scripts/github-api-resilience.cjs" and .dest == "scripts/github-api-resilience.cjs")' \
    "$repo_settings"
else
  skip_source_contract 'managed-file inventory contract'
fi

check 'retry helper is governance-protected' jq -e \
  '.protected_files | index("scripts/github-api-resilience.cjs") != null' \
  "$repo_root/.claude/governance.json"

if [ -f "$watcher" ]; then
  downstream_fixture=$(mktemp -d)
  trap 'rm -rf "$downstream_fixture"' EXIT
  mkdir -p \
    "$downstream_fixture/.claude" \
    "$downstream_fixture/.github/config" \
    "$downstream_fixture/.github/workflows" \
    "$downstream_fixture/scripts" \
    "$downstream_fixture/tests"
  printf '{"repository":"downstream-local"}\n' \
    >"$downstream_fixture/.github/config/repo-settings.json"
  cp "$repo_root/.claude/governance.json" "$downstream_fixture/.claude/governance.json"
  cp "$repo_root/workflows/antigravity-review.yml" \
    "$downstream_fixture/.github/workflows/antigravity-review.yml"
  cp "$repo_root/CONTRIBUTING.md" "$downstream_fixture/CONTRIBUTING.md"
  cp "$repo_root/scripts/github-api-resilience.cjs" \
    "$downstream_fixture/scripts/github-api-resilience.cjs"
  cp "$repo_root/tests/test-github-api-resilience.sh" \
    "$downstream_fixture/tests/test-github-api-resilience.sh"

  check 'downstream fixture uses the managed review caller bytes' \
    cmp -s "$repo_root/workflows/antigravity-review.yml" \
    "$downstream_fixture/.github/workflows/antigravity-review.yml"

  if downstream_output=$(cd "$downstream_fixture" &&
    bash tests/test-github-api-resilience.sh 2>&1); then
    printf '[OK] downstream-shaped managed checkout with local repo settings passes\n'
  else
    printf '%s\n' "$downstream_output" >&2
    printf '[FAIL] downstream-shaped managed checkout with local repo settings passes\n' >&2
    fail=1
  fi

  assert_downstream_contract_rejects() {
    local label="$1"
    local relative_path="$2"
    local mutation="$3"
    local target="$downstream_fixture/$relative_path"
    local backup="$target.contract-baseline"
    cp "$target" "$backup"
    python3 - "$target" "$mutation" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
mutation = sys.argv[2]
text = path.read_text(encoding="utf-8")
replacements = {
    "mutable-pin": (r"(@)[0-9a-f]{40}", r"\1main"),
    "misbound-input": (
        re.escape("      expected_head_sha: ${{ inputs.expected_head_sha }}"),
        "      expected_head_sha: ${{ inputs.expected_base_sha }}",
    ),
    "elevated-permission": (
        r"      pull-requests: write(?=\s+#)",
        "      pull-requests: admin",
    ),
}
pattern, replacement = replacements[mutation]
mutated, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit(f"could not apply {mutation} mutation to {path}")
path.write_text(mutated, encoding="utf-8")
PY
    if (
      cd "$downstream_fixture"
      bash tests/test-github-api-resilience.sh >/dev/null 2>&1
    ); then
      printf '[FAIL] %s\n' "$label" >&2
      fail=1
    else
      printf '[OK] %s\n' "$label"
    fi
    mv "$backup" "$target"
  }

  assert_downstream_contract_rejects \
    'downstream contract rejects a mutable reusable-workflow pin' \
    '.github/workflows/antigravity-review.yml' mutable-pin
  assert_downstream_contract_rejects \
    'downstream contract rejects a misbound exact-head input' \
    '.github/workflows/antigravity-review.yml' misbound-input
  assert_downstream_contract_rejects \
    'downstream contract rejects elevated review permissions' \
    '.github/workflows/antigravity-review.yml' elevated-permission
fi

exit "$fail"
