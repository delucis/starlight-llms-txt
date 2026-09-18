#!/usr/bin/env bash
# Hermetic test for scripts/lint-mdx-prose.sh — the gate that lints MDX prose.
#
# Neither of the two linters that own prose can see .mdx on its own. pre-commit's
# markdownlint hook selects `types: [markdown]` and `identify` tags .mdx as `mdx`;
# Super-Linter v8.7.0 routes only the `md` extension into MARKDOWN and
# NATURAL_LANGUAGE. So a repository whose documentation is .mdx — multi-cloud-networking's docs/en is
# 100% .mdx — passes both gates without either having opened a file.
#
# The linters are stubbed on PATH so this test asserts our selection and exit
# behaviour without a network round trip or a pinned tool version.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT="${REPO_ROOT}/scripts/lint-mdx-prose.sh"

FAIL=0
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin"

# Stubs record their arguments and honour a failure switch, so a test can assert
# both "was this linter asked about this file" and "does a finding fail the gate".
for tool in markdownlint-cli2 textlint; do
  cat >"$WORK/bin/$tool" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$@" >>"$WORK/${tool}.args"
if [ -n "\${STUB_FAIL_${tool//-/_}:-}" ]; then exit 1; fi
exit 0
STUB
  chmod +x "$WORK/bin/$tool"
done

reset_calls() { rm -f "$WORK"/markdownlint-cli2.args "$WORK"/textlint.args; }

run_gate() { # run_gate <paths...> -> echoes exit code
  local rc=0
  MDX_LINT_MARKDOWNLINT_BIN="$WORK/bin/markdownlint-cli2" MDX_LINT_TEXTLINT_BIN="$WORK/bin/textlint" \
    bash "$SCRIPT" "$@" >"$WORK/out" 2>&1 || rc=$?
  echo "$rc"
}

ok() { echo "[OK] $1"; }
bad() {
  echo "[FAIL] $1"
  FAIL=1
}

workflow_routes_mdx_gate() {
  local workflow=$1

  grep -Eq '^[[:space:]]*(-[[:space:]]+)?(run:[[:space:]]*)?bash[[:space:]]+scripts/lint-mdx-prose\.sh([[:space:]]|$)' "$workflow" ||
    grep -Eq '^[[:space:]]*uses:[[:space:]]*f5-sales-demo/docs-control/\.github/workflows/super-linter\.yml@[0-9a-f]{40}([[:space:]]*(#.*)?)?$' "$workflow"
}

# --- fixtures -------------------------------------------------------------
mkdir -p "$WORK/docs/en"
printf -- '---\ntitle: Good\n---\n\nSome prose.\n' >"$WORK/docs/en/good.mdx"
printf -- '---\ntitle: Also good\n---\n\nMore prose.\n' >"$WORK/docs/en/other.mdx"
printf -- '# Plain markdown\n' >"$WORK/docs/en/plain.md"

# --- cases ----------------------------------------------------------------

reset_calls
rc=$(run_gate)
if [ "$rc" -eq 0 ] && [ ! -f "$WORK/markdownlint-cli2.args" ]; then
  ok "no arguments: exits 0 and invokes no linter"
else
  bad "no arguments should be a clean no-op (rc=$rc)"
fi

reset_calls
rc=$(run_gate "$WORK/docs/en/plain.md")
if [ "$rc" -eq 0 ] && [ ! -f "$WORK/textlint.args" ]; then
  ok ".md only: no-op, because Super-Linter already owns that extension"
else
  bad ".md must not be linted here — it would double-report (rc=$rc)"
fi

reset_calls
rc=$(run_gate "$WORK/docs/en/good.mdx")
if [ "$rc" -ne 0 ]; then
  bad "a clean .mdx must pass (rc=$rc): $(cat "$WORK/out")"
elif ! grep -qF "$WORK/docs/en/good.mdx" "$WORK/markdownlint-cli2.args" 2>/dev/null; then
  bad "markdownlint was not asked about the .mdx file"
elif ! grep -qF "$WORK/docs/en/good.mdx" "$WORK/textlint.args" 2>/dev/null; then
  bad "textlint was not asked about the .mdx file"
else
  ok "a .mdx file reaches both markdownlint and textlint"
fi

reset_calls
rc=$(run_gate "$WORK/docs/en/good.mdx")
if grep -q -- '--plugin' "$WORK/textlint.args" && grep -q 'mdx' "$WORK/textlint.args"; then
  ok "textlint is invoked with the mdx plugin"
else
  bad "textlint must be given --plugin mdx or it cannot parse the file"
fi

reset_calls
rc=$(run_gate "$WORK/docs/en/good.mdx" "$WORK/docs/en/other.mdx" "$WORK/docs/en/plain.md")
if [ "$(grep -c '\.mdx$' "$WORK/markdownlint-cli2.args" 2>/dev/null || echo 0)" -eq 2 ] &&
  ! grep -q '\.md$' "$WORK/markdownlint-cli2.args"; then
  ok "a mixed list is filtered to .mdx only"
else
  bad "mixed list filtering is wrong: $(cat "$WORK/markdownlint-cli2.args" 2>/dev/null)"
fi

reset_calls
rc=$(
  STUB_FAIL_markdownlint_cli2=1 MDX_LINT_MARKDOWNLINT_BIN="$WORK/bin/markdownlint-cli2" \
    MDX_LINT_TEXTLINT_BIN="$WORK/bin/textlint" bash "$SCRIPT" "$WORK/docs/en/good.mdx" >/dev/null 2>&1
  echo $?
)
if [ "$rc" -ne 0 ]; then
  ok "a markdownlint finding fails the gate"
else
  bad "markdownlint findings must fail the gate, got rc=$rc"
fi

reset_calls
rc=$(
  STUB_FAIL_textlint=1 MDX_LINT_MARKDOWNLINT_BIN="$WORK/bin/markdownlint-cli2" \
    MDX_LINT_TEXTLINT_BIN="$WORK/bin/textlint" bash "$SCRIPT" "$WORK/docs/en/good.mdx" >/dev/null 2>&1
  echo $?
)
if [ "$rc" -ne 0 ]; then
  ok "a textlint finding fails the gate"
else
  bad "textlint findings must fail the gate, got rc=$rc"
fi

reset_calls
rc=$(run_gate "$WORK/docs/en/deleted.mdx")
if [ "$rc" -eq 0 ]; then
  ok "a path that no longer exists is skipped, not an error"
else
  bad "a deleted file in a changed-file list must not fail the gate (rc=$rc)"
fi

# --- --textlint-only: the local gate for plain Markdown --------------------
# CI lints .md prose through Super-Linter's NATURAL_LANGUAGE; pre-commit had no
# equivalent, so a finding cost a full CI run to discover.

reset_calls
rc=$(run_gate --textlint-only "$WORK/docs/en/plain.md")
if [ "$rc" -ne 0 ]; then
  bad "--textlint-only must accept .md (rc=$rc)"
elif ! grep -qF "$WORK/docs/en/plain.md" "$WORK/textlint.args" 2>/dev/null; then
  bad "--textlint-only did not pass the .md file to textlint"
elif [ -f "$WORK/markdownlint-cli2.args" ]; then
  bad "--textlint-only must not run markdownlint — the markdownlint hook owns .md"
else
  ok "--textlint-only lints .md with textlint and skips markdownlint"
fi

reset_calls
rc=$(run_gate --textlint-only "$WORK/docs/en/good.mdx")
if [ "$rc" -eq 0 ] && grep -qF "$WORK/docs/en/good.mdx" "$WORK/textlint.args" 2>/dev/null; then
  ok "--textlint-only still accepts .mdx"
else
  bad "--textlint-only should accept .mdx too (rc=$rc)"
fi

# --- the routing facts this gate exists to compensate for -----------------

mkdir -p "$WORK/workflows"
cat >"$WORK/workflows/direct.yml" <<'EOF'
jobs:
  lint:
    steps:
      - run: bash scripts/lint-mdx-prose.sh --changed origin/main
EOF
cat >"$WORK/workflows/reusable.yml" <<'EOF'
jobs:
  lint:
    uses: f5-sales-demo/docs-control/.github/workflows/super-linter.yml@0123456789abcdef0123456789abcdef01234567
EOF
cat >"$WORK/workflows/unrelated.yml" <<'EOF'
jobs:
  lint:
    uses: example/actions/.github/workflows/lint.yml@0123456789abcdef0123456789abcdef01234567
EOF

if workflow_routes_mdx_gate "$WORK/workflows/direct.yml"; then
  ok "a direct workflow invocation routes the MDX prose gate"
else
  bad "a direct workflow invocation must route the MDX prose gate"
fi

if workflow_routes_mdx_gate "$WORK/workflows/reusable.yml"; then
  ok "a governed reusable-workflow caller routes the MDX prose gate"
else
  bad "a governed reusable-workflow caller must route the MDX prose gate"
fi

if workflow_routes_mdx_gate "$WORK/workflows/unrelated.yml"; then
  bad "an unrelated reusable workflow must not satisfy MDX prose routing"
else
  ok "a workflow with no MDX prose route is rejected"
fi

# The gate must be reachable locally as well as in CI, and both must run the same
# script — a hook that only widened markdownlint would still leave textlint blind.
if grep -q 'lint-mdx-prose' "${REPO_ROOT}/.pre-commit-config.yaml"; then
  ok "pre-commit invokes the MDX prose gate"
else
  bad "pre-commit does not invoke scripts/lint-mdx-prose.sh"
fi

# Managed-file synchronization writes downstream files through the GitHub
# contents API, which does not preserve the executable bit. Invoke the script
# through bash so both hooks remain runnable when the synced file is mode 0644.
for hook_id in lint-mdx-prose textlint-markdown; do
  hook_entry=$(
    awk -v hook_id="$hook_id" '
      $0 ~ "- id: " hook_id "$" { in_hook = 1; next }
      in_hook && /entry:/ { print; exit }
    ' "${REPO_ROOT}/.pre-commit-config.yaml"
  )
  if printf '%s' "$hook_entry" | grep -Eq 'entry:[[:space:]]+bash[[:space:]]+scripts/lint-mdx-prose\.sh([[:space:]]|$)'; then
    ok "pre-commit hook $hook_id tolerates a non-executable managed script"
  else
    bad "pre-commit hook $hook_id must invoke the managed script through bash, got: ${hook_entry}"
  fi
done

mdx_hook_types=$(awk '/id: lint-mdx-prose$/,/^$/' "${REPO_ROOT}/.pre-commit-config.yaml" | grep -E 'types(_or)?:' || true)
if printf '%s' "$mdx_hook_types" | grep -q 'mdx'; then
  ok "the pre-commit MDX hook selects mdx files"
else
  bad "the pre-commit MDX hook must select types: [mdx], got: ${mdx_hook_types}"
fi

if grep -q 'textlint-only' "${REPO_ROOT}/.pre-commit-config.yaml"; then
  ok "pre-commit lints plain Markdown prose locally too"
else
  bad "pre-commit has no local textlint for .md — CI would be the first to know"
fi

if workflow_routes_mdx_gate "${REPO_ROOT}/.github/workflows/super-linter.yml"; then
  ok "super-linter workflow invokes the MDX prose gate"
else
  bad "super-linter workflow does not invoke scripts/lint-mdx-prose.sh"
fi

if [ "$FAIL" -eq 0 ]; then
  echo "PASS: MDX prose gate selects and fails as specified"
else
  echo "FAIL: MDX prose gate is wrong"
fi
exit "$FAIL"
