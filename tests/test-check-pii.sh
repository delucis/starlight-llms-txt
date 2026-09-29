#!/usr/bin/env bash
# Hermetic contract tests for the managed PII scanner. The fixtures are created
# in throwaway Git repositories so the test never depends on this checkout and
# never sends fixture values to an external service.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SCANNER="${REPO_ROOT}/scripts/check-pii.sh"
PYTHON_SCANNER="${REPO_ROOT}/scripts/check_pii.py"
SYNTHETIC_USER=realperson

FAIL=0
WORK=$(mktemp -d)
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

if [ -x "$PYTHON_SCANNER" ]; then
  echo "[FAIL] Python scanner is executable — invoke it through the shell wrapper"
  FAIL=1
else
  echo "[OK] Python scanner is a non-executable module"
fi

if head -n 1 "$PYTHON_SCANNER" | grep -q '^#!'; then
  echo "[FAIL] Python scanner has a shebang — invoke it through the shell wrapper"
  FAIL=1
else
  echo "[OK] Python scanner has no executable shebang"
fi

new_repo() {
  local dir="${WORK}/$1"
  mkdir -p "$dir"
  git -C "$dir" init -q -b main
  git -C "$dir" config user.email test@example.com
  git -C "$dir" config user.name "PII Scanner Test"
  printf '# Example\n' >"${dir}/README.md"
  git -C "$dir" add -A
  git -C "$dir" commit -qm baseline
  echo "$dir"
}

run_scan() {
  local dir="$1"
  shift
  local rc=0
  (cd "$dir" && bash "$SCANNER" "$@") >"${WORK}/stdout" 2>"${WORK}/stderr" || rc=$?
  printf '%s' "$rc"
}

assert_clean() {
  local label="$1" dir="$2"
  shift 2
  local rc
  rc=$(run_scan "$dir" "$@")
  if [ "$rc" -eq 0 ]; then
    echo "[OK] $label -> clean"
  else
    echo "[FAIL] $label — expected clean (0), got $rc"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
  fi
}

assert_violation() {
  local label="$1" dir="$2"
  shift 2
  local rc
  rc=$(run_scan "$dir" "$@")
  if [ "$rc" -eq 1 ]; then
    echo "[OK] $label -> rejected"
  else
    echo "[FAIL] $label — expected finding (1), got $rc"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
  fi
}

assert_customer_identifier() {
  local label="$1" dir="$2"
  shift 2
  local rc
  rc=$(run_scan "$dir" "$@" --format json)
  if [ "$rc" -ne 1 ]; then
    echo "[FAIL] $label — expected finding (1), got $rc"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
    return
  fi
  if python3 - "${WORK}/stdout" <<'PY'; then
import json
import sys

findings = json.load(open(sys.argv[1], encoding="utf-8"))["findings"]
if len(findings) != 1 or findings[0]["category"] != "customer-identifier":
    raise SystemExit(1)
PY
    echo "[OK] $label -> one customer-identifier finding"
  else
    echo "[FAIL] $label — expected exactly one customer-identifier finding"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
  fi
}

assert_single_finding() {
  local label="$1" dir="$2" category="$3" severity="$4"
  shift 4
  local rc
  rc=$(run_scan "$dir" "$@" --format json)
  if [ "$rc" -ne 1 ]; then
    echo "[FAIL] $label — expected finding (1), got $rc"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
    return
  fi
  if python3 - "${WORK}/stdout" "$category" "$severity" <<'PY'; then
import json
import sys

findings = json.load(open(sys.argv[1], encoding="utf-8"))["findings"]
expected = (sys.argv[2], sys.argv[3])
actual = [(finding["category"], finding["severity"]) for finding in findings]
if actual != [expected]:
    raise SystemExit(1)
PY
    echo "[OK] $label -> one $severity $category finding"
  else
    echo "[FAIL] $label — expected exactly one $severity $category finding"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
  fi
}

assert_error() {
  local label="$1" dir="$2"
  shift 2
  local rc
  rc=$(run_scan "$dir" "$@")
  if [ "$rc" -eq 2 ]; then
    echo "[OK] $label -> usage/environment error"
  else
    echo "[FAIL] $label — expected scanner error (2), got $rc"
    sed 's/^/  /' "${WORK}/stdout" "${WORK}/stderr"
    FAIL=1
  fi
}

repo=$(new_repo clean)
assert_clean "synthetic baseline" "$repo" --scope head --mode enforce

repo=$(new_repo reserved-values)
cat >"${repo}/fixture.yaml" <<'EOF'
email: dana@example.com
phone: 800-555-0107
mobile: +1-555-0100
telephone: +1 212-555-0199
full_name: Dana R.
tenant: example-corp
namespace: demo-app
account_id: 123456789012
project_id: example-project
subscription_name: example-plan
customer_id: 0
project: agent
subscription: 000000
client_ip: 192.0.2.10
origin_ip: 198.51.100.20
service_ip: 203.0.113.30
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm synthetic
assert_clean "reserved synthetic values" "$repo" --scope head --mode enforce

repo=$(new_repo shell-positional-identities)
cat >"${repo}/fixture.sh" <<'EOF'
NAMESPACE=$2
EOF
git -C "$repo" add fixture.sh
git -C "$repo" commit -qm shell-positional-identities
assert_clean "shell positional identity inputs are dynamic" "$repo" --scope head --mode enforce

repo=$(new_repo shell-literal-identity)
cat >"${repo}/fixture.sh" <<'EOF'
NAMESPACE=private-customer
EOF
git -C "$repo" add fixture.sh
git -C "$repo" commit -qm shell-literal-identity
assert_customer_identifier "unquoted shell identity literals remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo localization-message-labels)
mkdir -p "${repo}/l10n"
cat >"${repo}/l10n/bundle.l10n.json" <<'EOF'
{
  "Namespace": "Resource namespace",
  "Account": "Cloud account",
  "Namespace unavailable": "Unable to load namespace: {0}"
}
EOF
git -C "$repo" add l10n/bundle.l10n.json
git -C "$repo" commit -qm localization-labels
assert_clean "top-level localization source labels are not identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo localization-nested-identity)
mkdir -p "${repo}/l10n"
cat >"${repo}/l10n/bundle.l10n.json" <<'EOF'
{
  "Message": "Example resource",
  "configuration": {
    "namespace": "private-customer"
  }
}
EOF
git -C "$repo" add l10n/bundle.l10n.json
git -C "$repo" commit -qm localization-nested-identity
assert_customer_identifier "nested identity fields remain enforced in localization files" "$repo" --scope head --mode enforce

repo=$(new_repo vscode-context-tag)
cat >"${repo}/package.json" <<'EOF'
{
  "contributes": {
    "menus": {
      "view/item/context": [
        {
          "when": "view == example.resources && viewItem == namespace:resource"
        },
        {
          "when": "view === example.resources && viewItem === account:resource"
        }
      ]
    }
  }
}
EOF
git -C "$repo" add package.json
git -C "$repo" commit -qm vscode-context-tag
assert_clean "typed VS Code viewItem context tags are not identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo vscode-context-identity)
cat >"${repo}/package.json" <<'EOF'
{
  "contributes": {
    "menus": {
      "view/item/context": [
        {
          "when": "viewItem == resource && namespace: private-customer"
        }
      ]
    }
  }
}
EOF
git -C "$repo" add package.json
git -C "$repo" commit -qm vscode-context-identity
assert_customer_identifier "identity fields outside viewItem tags remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo vscode-snippet-placeholders)
cat >"${repo}/fixture.ts" <<'EOF'
const direct = `${indent}"namespace": "\${${tabstop++}:demo-app}",`;
const nested = `${indent}"namespace": "\${${tabstop++}:\${1:demo-app}}",`;
const choices = `${indent}"namespace": "\${1|demo-app,shared|}",`;
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm vscode-snippet-placeholders
assert_clean "escaped VS Code snippet placeholders validate safe defaults" "$repo" --scope head --mode enforce

repo=$(new_repo vscode-snippet-literal-default)
cat >"${repo}/fixture.ts" <<'EOF'
const nested = `${indent}"namespace": "\${${tabstop++}:\${1:private-customer}}",`;
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm vscode-snippet-literal-default
assert_customer_identifier "nested VS Code snippet defaults remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo vscode-simple-snippet-literal-default)
cat >"${repo}/fixture.json" <<'EOF'
{"namespace": "${1:private-customer}"}
EOF
git -C "$repo" add fixture.json
git -C "$repo" commit -qm vscode-simple-snippet-literal-default
assert_customer_identifier "direct VS Code snippet defaults remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo source-field-aliases)
cat >"${repo}/aliases.ts" <<'EOF'
const aliases = { first_name: "first_name" };
type NameField = { first_name: "given_name" };
type IdentityField = { account: "account" };
const multiline = {
  first_name: "given_name",
  account: "account",
};
EOF
cat >"${repo}/README.md" <<'EOF'
# Source field aliases

```typescript
const aliases = { first_name: "first_name" };
type NameField = { first_name: "given_name" };
type IdentityField = { account: "account" };
```
EOF
git -C "$repo" add -A
git -C "$repo" commit -qm source-field-aliases
assert_clean "source field aliases are schema names rather than personal values" "$repo" --scope head --mode enforce

repo=$(new_repo source-field-alias-boundary)
cat >"${repo}/fixture.ts" <<'EOF'
const record = { first_name: "Private Person", account: "private-customer" };
// first_name: "given_name"
/* account: "account" */
const serialized = '{ first_name: "given_name", account: "account" }';
const prefixed = { first_name: "given_name-person", account: "account-customer" };
EOF
cat >"${repo}/generated.json" <<'EOF'
{"first_name": "given_name", "account": "account"}
EOF
git -C "$repo" add -A
git -C "$repo" commit -qm source-field-alias-boundary
assert_violation "comments, serialized records and identity fixtures remain enforced" "$repo" --scope head --mode enforce
if ! python3 - "${WORK}/stdout" <<'PYTEST'; then
import sys
from pathlib import Path
output = Path(sys.argv[1]).read_text()
assert all(f"fixture.ts:{line}" in output for line in range(1, 6)), output
assert "generated.json:1" in output, output
PYTEST
  echo "[FAIL] each non-structural field remains enforced"
  FAIL=1
fi

repo=$(new_repo numeric-enum-members)
cat >"${repo}/fixture.ts" <<'EOF'
export enum ResourceKind
{
  Namespace = 1,
  Label = "}",
  Account = 2,
}
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm numeric-enum-members
assert_clean "numeric source enum members are not serialized identifiers" "$repo" --scope head --mode enforce

repo=$(new_repo numeric-identifier-assignment)
printf 'export const namespace = 987654321;\n' >"${repo}/fixture.ts"
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm numeric-identifier-assignment
assert_customer_identifier "numeric identifiers outside enum scope remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo source-code-fixture)
cat >"${repo}/protocol.source" <<'EOF'
pub struct DynamicToolCallParams {
    pub namespace: Option<String>,
    pub project_id: Option<String>,
}
EOF
git -C "$repo" add protocol.source
git -C "$repo" commit -qm source-code-fixture
assert_clean "typed declarations in source-code fixtures are not customer identifiers" "$repo" --scope head --mode enforce

repo=$(new_repo source-code-fixture-literal)
printf 'const namespace = "private-customer";\n' >"${repo}/protocol.source"
git -C "$repo" add protocol.source
git -C "$repo" commit -qm source-code-fixture-literal
assert_customer_identifier "literal identities in source-code fixtures remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo string-shaped-enum-declaration)
cat >"${repo}/fixture.ts" <<'EOF'
const source = "enum ResourceKind {";
const account = 987654321,
  status = "active";
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm string-shaped-enum-declaration
assert_customer_identifier "enum-shaped strings cannot exempt numeric identifiers" "$repo" --scope head --mode enforce

repo=$(new_repo ambiguous-display-name)
cat >"${repo}/fixture.ts" <<'EOF'
const subscription = { display_name: "Primary subscription" };
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm ambiguous-display-name
assert_clean "context-free display names do not block enforcement" "$repo" --scope head --mode enforce
assert_single_finding "context-free display names require audit review" "$repo" display-name-review review --scope head --mode audit

repo=$(new_repo explicit-person-name)
cat >"${repo}/fixture.ts" <<'EOF'
const profile = { full_name: "Synthetic Person" };
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm explicit-person-name
assert_single_finding "explicit person-name fields remain enforced" "$repo" person-name high --scope head --mode enforce

repo=$(new_repo documentation-expressions)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
curl "https://example.com/api/config/namespaces/xEXAMPLE_NAMESPACEx/resources" \
  | jq '{namespace: .metadata.namespace}'
jq -n '{metadata: {namespace: "xEXAMPLE_NAMESPACEx"}}'
jq -n '{detail: "Namespace: write denied — create it before continuing"}'
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm expressions
assert_clean "schematic variables and documentation expressions" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-prose-value)
cat >"${repo}/fixture.mdx" <<'EOF'
Status: "Namespace: write denied — create it before continuing"
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm quoted-prose
assert_clean "identity-shaped text inside another quoted value is prose" "$repo" --scope head --mode enforce

repo=$(new_repo documentation-prose-labels)
cat >"${repo}/fixture.mdx" <<'EOF'
<Note>
Every customer: "Use the documented example tenant." Continue with the setup instructions.
For every customer: use the documented example tenant.
Each account: "Use the synthetic placeholder value."
For every customer: use the customer's documented example tenant.
</Note>
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm prose-labels
assert_clean "identity words used as prose labels" "$repo" --scope head --mode enforce

repo=$(new_repo prose-shaped-structured-data)
printf 'Every tenant: tenant-literal\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm structured-prefix
assert_violation "prose-shaped prefixes outside documentation" "$repo" --scope head --mode enforce

repo=$(new_repo expression-shaped-literals)
cat >"${repo}/fixture.mdx" <<'EOF'
```yaml
namespace: xcustomer-namespacex
```
```json
{"namespace": ".customer-namespace"}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm literals
assert_violation "expression-shaped identity literals remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo compact-json-later-field)
cat >"${repo}/fixture.json" <<'EOF'
{"other":1,"tenant":"real-customer"}
EOF
git -C "$repo" add fixture.json
git -C "$repo" commit -qm compact-json
assert_customer_identifier "identity fields after another compact JSON field" "$repo" --scope head --mode enforce

repo=$(new_repo compact-json-nested-field)
cat >"${repo}/fixture.json" <<'EOF'
{"outer":{"namespace":"private-customer"}}
EOF
git -C "$repo" add fixture.json
git -C "$repo" commit -qm nested-json
assert_customer_identifier "identity fields nested in compact JSON" "$repo" --scope head --mode enforce

repo=$(new_repo log-prefixed-identity)
cat >"${repo}/fixture.mdx" <<'EOF'
INFO tenant: private-customer
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm log-prefix
assert_customer_identifier "identity fields after a log-level prefix" "$repo" --scope head --mode enforce

repo=$(new_repo timestamp-prefixed-identity)
cat >"${repo}/fixture.txt" <<'EOF'
2026-08-01 customer_id: acct-481516
EOF
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm timestamp-prefix
assert_customer_identifier "identity fields after a timestamp prefix" "$repo" --scope head --mode enforce

repo=$(new_repo blockquote-identity)
cat >"${repo}/fixture.md" <<'EOF'
> tenant: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm blockquote
assert_customer_identifier "identity fields in blockquotes" "$repo" --scope head --mode enforce

repo=$(new_repo indented-list-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
items:
  - tenant: private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm indented-list
assert_customer_identifier "identity fields in indented list items" "$repo" --scope head --mode enforce

repo=$(new_repo markdown-table-identity)
cat >"${repo}/fixture.md" <<'EOF'
| tenant: private-customer |
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm markdown-table
assert_customer_identifier "identity fields in Markdown tables" "$repo" --scope head --mode enforce

repo=$(new_repo decorated-log-identity)
cat >"${repo}/fixture.txt" <<'EOF'
2026-08-01T12:00:00Z INFO auth-service tenant: private-customer
EOF
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm decorated-log
assert_customer_identifier "identity fields after decorated log prefixes" "$repo" --scope head --mode enforce

repo=$(new_repo dot-prefixed-yaml-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: .private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm dot-prefixed-yaml
assert_customer_identifier "dot-prefixed YAML identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo numbered-list-identity)
cat >"${repo}/fixture.md" <<'EOF'
1. tenant: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm numbered-list
assert_customer_identifier "identity fields in numbered list items" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-dot-json-identity)
cat >"${repo}/fixture.json" <<'EOF'
{"tenant":".private-customer"}
EOF
git -C "$repo" add fixture.json
git -C "$repo" commit -qm quoted-dot-json
assert_customer_identifier "quoted dot-prefixed JSON identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-delimited-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: "example-corp#private-customer"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm quoted-delimited-value
assert_customer_identifier "safe quoted prefixes cannot hide identity suffixes" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-comma-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: "example-corp,private-customer"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm quoted-comma-value
assert_customer_identifier "quoted commas cannot truncate identity inspection" "$repo" --scope head --mode enforce

repo=$(new_repo plain-hash-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: example-corp#private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm plain-hash-value
assert_customer_identifier "plain YAML hashes without whitespace remain value content" "$repo" --scope head --mode enforce

repo=$(new_repo plain-comma-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: example-corp,private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm plain-comma-value
assert_customer_identifier "plain YAML commas remain block-scalar value content" "$repo" --scope head --mode enforce

repo=$(new_repo placeholder-prefix-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: $TENANT-private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm placeholder-prefix
assert_customer_identifier "placeholder prefixes cannot hide literal identity suffixes" "$repo" --scope head --mode enforce

repo=$(new_repo angle-placeholder-prefix-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: <tenant>-private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm angle-placeholder-prefix
assert_customer_identifier "angle placeholders cannot hide literal identity suffixes" "$repo" --scope head --mode enforce

repo=$(new_repo template-placeholder-prefix-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: {{ tenant }}-private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm template-placeholder-prefix
assert_customer_identifier "template placeholders cannot hide literal identity suffixes" "$repo" --scope head --mode enforce

repo=$(new_repo whole-placeholder-identities)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: $TENANT
customer: ${CUSTOMER}
tenant_id: ${TENANT:=default}
account: <account>
project: {project}
namespace: {{ namespace }}
subscription: [% subscription %]
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm whole-placeholders
assert_clean "whole identity placeholders remain synthetic" "$repo" --scope head --mode enforce

repo=$(new_repo prose-adjacent-placeholders)
cat >"${repo}/fixture.md" <<'EOF'
You are connected to tenant: {{context.tenant}}, namespace: {{context.namespace}}.
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm prose-adjacent-placeholders
assert_clean "adjacent prose identity placeholders remain synthetic" "$repo" --scope head --mode enforce

repo=$(new_repo prose-adjacent-placeholder-literal)
cat >"${repo}/fixture.md" <<'EOF'
You are connected to tenant: {{context.tenant}}, namespace: private-customer.
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm prose-adjacent-placeholder-literal
assert_customer_identifier "a later prose identity literal remains enforced" "$repo" --scope head --mode enforce

repo=$(new_repo prose-wildcard-namespace)
cat >"${repo}/fixture.md" <<'EOF'
Use `params: {namespace: "*"}` to query every namespace.
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm prose-wildcard-namespace
assert_clean "the product wildcard namespace is a schema sentinel" "$repo" --scope head --mode enforce

repo=$(new_repo prose-quoted-namespace-literal)
cat >"${repo}/fixture.md" <<'EOF'
Do not use `params: {namespace: "private-customer"}` in published examples.
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm prose-quoted-namespace-literal
assert_customer_identifier "quoted prose namespace literals remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo prose-synthetic-terminal-punctuation)
cat >"${repo}/fixture.md" <<'EOF'
The configured value is safe (namespace: example-corp).
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm prose-synthetic-terminal-punctuation
assert_clean "terminal prose punctuation preserves a synthetic identity" "$repo" --scope head --mode enforce

repo=$(new_repo prose-literal-terminal-punctuation)
cat >"${repo}/fixture.md" <<'EOF'
The configured value is unsafe (namespace: private-customer).
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm prose-literal-terminal-punctuation
assert_customer_identifier "terminal prose punctuation cannot hide a literal identity" "$repo" --scope head --mode enforce

repo=$(new_repo placeholder-comma-suffix)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: ${TENANT},private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm placeholder-comma-suffix
assert_customer_identifier "YAML block commas cannot terminate placeholders" "$repo" --scope head --mode enforce

repo=$(new_repo placeholder-hash-suffix)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: $TENANT#private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm placeholder-hash-suffix
assert_customer_identifier "YAML hashes without whitespace cannot terminate placeholders" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-doubled-quote-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: 'example-corp''private-customer'
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm doubled-quote-value
assert_customer_identifier "YAML doubled quotes cannot truncate identity inspection" "$repo" --scope head --mode enforce

repo=$(new_repo quantified-literal-identity)
cat >"${repo}/fixture.mdx" <<'EOF'
Every customer: "private-customer"
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm quantified-literal
assert_customer_identifier "quantified literal identity values" "$repo" --scope head --mode enforce

repo=$(new_repo log-sentence-identity)
cat >"${repo}/fixture.mdx" <<'EOF'
INFO customer: "Use the documented example tenant."
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm log-sentence
assert_customer_identifier "sentence-shaped identity values after log prefixes" "$repo" --scope head --mode enforce

repo=$(new_repo article-sentence-identity)
cat >"${repo}/fixture.mdx" <<'EOF'
The customer: "Private Customer Inc."
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm article-sentence
assert_customer_identifier "article-prefixed identity labels" "$repo" --scope head --mode enforce

repo=$(new_repo quantified-organization-name)
cat >"${repo}/fixture.mdx" <<'EOF'
Every customer: "Private Customer Inc." Continue with setup.
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm quantified-organization
assert_customer_identifier "quantified prose cannot hide organization names" "$repo" --scope head --mode enforce

repo=$(new_repo quantified-organization-with-safe-continuation)
cat >"${repo}/fixture.mdx" <<'EOF'
Every customer: "Private Customer Inc." Continue with the documented example.
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm quantified-organization-continuation
assert_customer_identifier "later safe prose cannot hide an organization name" "$repo" --scope head --mode enforce

repo=$(new_repo safe-prose-before-organization)
cat >"${repo}/fixture.mdx" <<'EOF'
Every customer: Use the documented example tenant. Private Customer Inc.
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm safe-prose-before-organization
assert_customer_identifier "safe prose cannot prefix a hidden organization name" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-safe-prose-before-organization)
cat >"${repo}/fixture.mdx" <<'EOF'
Every customer: "Use the documented example tenant." Private Customer Inc.
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm quoted-safe-prose-before-organization
assert_customer_identifier "quoted safe prose cannot hide trailing organization names" "$repo" --scope head --mode enforce

repo=$(new_repo unrelated-jq-prefix)
cat >"${repo}/fixture.mdx" <<'EOF'
jq . input.json; tenant: .private-customer
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm unrelated-jq
assert_customer_identifier "an earlier jq command cannot exempt a later field" "$repo" --scope head --mode enforce

repo=$(new_repo jq-expressions)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
/usr/bin/jq '{tenant: input.tenant, namespace: env.NAMESPACE}' input.json
jq '{
  namespace: .pool.namespace,
  tenant: (.tenant // "default")
}' input.json
```
```jq
{tenant: input.tenant, namespace: env.NAMESPACE}
```
EOF
cat >"${repo}/filter.jq" <<'EOF'
{tenant: input.tenant, namespace: env.NAMESPACE}
EOF
git -C "$repo" add fixture.mdx filter.jq
git -C "$repo" commit -qm jq-expressions
assert_clean "jq filters are executable expressions" "$repo" --scope head --mode enforce

repo=$(new_repo jq-options-and-indentation)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
  jq '{tenant: .metadata.tenant}' input.json
jq --arg label 'sample' '{namespace: .metadata.namespace}' input.json
command jq '{tenant: input.tenant}' input.json
command -- jq '{tenant: input.tenant}' input.json
sudo jq '{tenant: input.tenant}' input.json
sudo -n jq '{tenant: input.tenant}' input.json
sudo -u user jq '{tenant: input.tenant}' input.json
sudo -n -u user jq '{tenant: input.tenant}' input.json
sudo -nE jq '{tenant: input.tenant}' input.json
sudo --preserve-env jq '{tenant: input.tenant}' input.json
sudo -H jq '{tenant: input.tenant}' input.json
sudo -- jq '{tenant: input.tenant}' input.json
sudo -n env -i jq '{tenant: input.tenant}' input.json
env JQ_COLORS=off jq '{tenant: input.tenant}' input.json
/usr/bin/env jq '{tenant: input.tenant}' input.json
/usr/bin/env -i jq '{tenant: input.tenant}' input.json
env -u JQ_COLORS jq '{tenant: input.tenant}' input.json
env --unset=JQ_COLORS jq '{tenant: input.tenant}' input.json
LC_ALL=C jq '{tenant: input.tenant}' input.json
xargs jq '{tenant: input.tenant}'
xargs -n1 jq '{tenant: input.tenant}'
xargs -n 1 jq '{tenant: input.tenant}'
xargs -P 2 jq '{tenant: input.tenant}'
xargs -0 jq '{tenant: input.tenant}'
xargs --null jq '{tenant: input.tenant}'
xargs -I {} jq '{tenant: input.tenant}'
xargs --max-args 1 jq '{tenant: input.tenant}'
time jq '{tenant: input.tenant}' input.json
/usr/bin/time jq '{tenant: input.tenant}' input.json
env --unset JQ_COLORS jq '{tenant: input.tenant}' input.json
env --ignore-environment jq '{tenant: input.tenant}' input.json
sudo --user nobody jq '{tenant: input.tenant}' input.json
sudo --preserve-env=PATH jq '{tenant: input.tenant}' input.json
nice jq '{tenant: input.tenant}' input.json
nice -n 10 jq '{tenant: input.tenant}' input.json
/usr/bin/nice jq '{tenant: input.tenant}' input.json
nice -10 jq '{tenant: input.tenant}' input.json
nohup jq '{tenant: input.tenant}' input.json
timeout 5 jq '{tenant: input.tenant}' input.json
stdbuf -oL jq '{tenant: input.tenant}' input.json
exec jq '{tenant: input.tenant}' input.json
xargs -r jq '{tenant: input.tenant}'
xargs -L 1 jq '{tenant: input.tenant}'
xargs -d '\n' jq '{tenant: input.tenant}'
xargs --replace jq '{tenant: input.tenant}'
sudo -S jq '{tenant: input.tenant}' input.json
sudo -k jq '{tenant: input.tenant}' input.json
sudo -g staff jq '{tenant: input.tenant}' input.json
jq --argfile data input.json '{tenant: .tenant}' input.json
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-options
assert_clean "jq indentation and option arguments preserve filter context" "$repo" --scope head --mode enforce

repo=$(new_repo jq-person-field-expression)
cat >"${repo}/fixture.sh" <<'EOF'
jq -n --arg repo "$repo_name" '{full_name: $repo}'
EOF
git -C "$repo" add fixture.sh
git -C "$repo" commit -qm jq-person-field-expression
assert_clean "computed person fields inside jq filters do not crash the scanner" "$repo" --scope head --mode enforce

repo=$(new_repo jq-person-field-literal)
cat >"${repo}/fixture.sh" <<'EOF'
jq -n '{full_name: "Literal Person"}'
EOF
git -C "$repo" add fixture.sh
git -C "$repo" commit -qm jq-person-field-literal
assert_single_finding "literal person fields inside jq filters remain enforced" \
  "$repo" person-name high --scope head --mode enforce

repo=$(new_repo jq-numeric-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
jq -n '{account_id: 987654321}'
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-numeric
assert_customer_identifier "numeric identity literals inside jq remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo direct-jq-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: 987654321}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm direct-jq-numeric
assert_customer_identifier "numeric identity literals in jq files remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo jq-quote-state-boundary)
cat >"${repo}/fixture.mdx" <<'EOF'
jq ".foo\\"; tenant: .private-customer
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-quote-boundary
assert_customer_identifier "closed jq filters cannot exempt later fields" "$repo" --scope head --mode enforce

repo=$(new_repo jq-string-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
jq -n '{tenant: "real-customer"}'
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-literal
assert_customer_identifier "quoted literals inside jq filters remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo jq-double-shell-string-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
jq "{tenant: \"real-customer\"}"
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-double-shell-literal
assert_customer_identifier "escaped literals inside double-quoted jq filters remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo jq-interpolated-strings)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
jq '{tenant: "prefix-\(.suffix)"}' input.json
jq "{namespace: \"prefix-\\(.suffix)\"}" input.json
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-interpolation
assert_clean "jq interpolated strings are executable expressions" "$repo" --scope head --mode enforce

repo=$(new_repo jq-interpolation-inner-quotes)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "example-\("corp")"}
{tenant: "\(")")"}
{tenant: "example-\("corp" | .)"}
{account_id: "\(987654321 | . == 0)"}
{tenant: "\("example-" + "corp")"}
{tenant: "\(["example", "corp"] | join("-"))"}
{tenant: "example-\(123)"}
{tenant: "example-\(123 | .)"}
{tenant: "\("example-" | .)\(123 | .)"}
{tenant: "example-\(false)-corp"}
{tenant: "example-\(true)-corp"}
{tenant: "example-\(null)-corp"}
{account_id: "\(1.23456789012e11)"}
{account_id: "\(123456789012e0)"}
{tenant: "\("example-\("corp")")"}
{tenant: "\("example-\(123)")"}
{tenant: "\("example-\(false)-corp")"}
{tenant: "\(("example-\("corp")") | (.))"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-interpolation-inner-quotes
assert_clean "quotes inside jq interpolation do not terminate the outer string" "$repo" --scope head --mode enforce

repo=$(new_repo jq-constant-interpolation-literal)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\("private-customer")"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-constant-interpolation-literal
assert_customer_identifier "constant jq interpolation cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-computed-interpolation-literal)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\("private-customer" | .)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-computed-interpolation-literal
assert_customer_identifier "computed jq interpolation cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-computed-interpolation-number)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: "\(987654321)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-computed-interpolation-number
assert_customer_identifier "numeric jq interpolation cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-piped-interpolation-number)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: "\(987654321 | .)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-piped-interpolation-number
assert_customer_identifier "piped numeric jq interpolation cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-adjacent-placeholder-composition)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "example-corp\("example-corp" | .)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-adjacent-placeholder-composition
assert_customer_identifier "adjacent jq placeholders cannot compose an identity" "$repo" --scope head --mode enforce

repo=$(new_repo jq-multiple-interpolation-composition)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\("example-corp" | .)\("example-corp" | .)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-multiple-interpolation-composition
assert_customer_identifier "multiple jq interpolations compose before classification" "$repo" --scope head --mode enforce

repo=$(new_repo jq-grouped-interpolation-string)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\("private-customer" | ((.)))"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-grouped-interpolation-string
assert_customer_identifier "redundant jq groups cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-grouped-interpolation-number)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: "\(987654321 | (((.))))"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-grouped-interpolation-number
assert_customer_identifier "grouped jq no-op filters cannot hide numeric identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-grouped-noop-chain)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\(("private-customer" | (. | .)))"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-grouped-noop-chain
assert_customer_identifier "grouped jq identity chains cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-adjacent-number-composition)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: "\(123456789012)\(123456789012)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-adjacent-number-composition
assert_customer_identifier "adjacent numeric jq constants compose before classification" "$repo" --scope head --mode enforce

repo=$(new_repo jq-placeholder-number-composition)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "example-corp\(123456789012)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-placeholder-number-composition
assert_customer_identifier "numeric jq constants cannot suffix placeholder identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-scientific-interpolation-canonicalization)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "example-\(1e6)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-scientific-interpolation-canonicalization
assert_customer_identifier "jq numeric interpolation uses canonical stringification" "$repo" --scope head --mode enforce

repo=$(new_repo jq-nested-constant-interpolation)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\("private-\("customer")")"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-nested-constant-interpolation
assert_customer_identifier "nested jq constants compose before classification" "$repo" --scope head --mode enforce

repo=$(new_repo jq-expression-literals)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: "private-customer-\(.suffix)"}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-interpolated-literal
assert_customer_identifier "jq interpolation cannot hide literal identity fragments" "$repo" --scope head --mode enforce

repo=$(new_repo jq-fallback-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: input.tenant // "private-customer"}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-fallback-literal
assert_customer_identifier "jq fallbacks cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-punctuated-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: "private-customer,division"}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-punctuated-literal
assert_customer_identifier "jq punctuation cannot truncate literal inspection" "$repo" --scope head --mode enforce

repo=$(new_repo jq-nested-object-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: {name: "default", org: "private-customer"}.org}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-nested-object
assert_customer_identifier "nested jq objects cannot hide output identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-array-output-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: ["private-customer"][0]}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-array-output
assert_customer_identifier "jq array indexing cannot hide output identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-branch-array-output-literal)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: (if true then ["private-customer"][0] else input.tenant end)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-branch-array-output
assert_customer_identifier "jq branch arrays cannot hide output identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-reduce-array-output-literal)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: (reduce ["private-customer"][] as $x (null; $x))}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-reduce-array-output
assert_customer_identifier "jq reducer arrays cannot hide output identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-container-numeric-literals)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: [987654321][0]}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-container-numeric
assert_customer_identifier "jq arrays cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-object-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: {id: 987654321}.id}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-object-numeric
assert_customer_identifier "jq objects cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-branch-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: (if true then 987654321 else input.account_id end)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-branch-numeric
assert_customer_identifier "jq branches cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-function-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: first(987654321)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-function-numeric
assert_customer_identifier "jq output functions cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-arithmetic-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: 987654321 + 0}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-arithmetic-numeric
assert_customer_identifier "jq constant arithmetic cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-pipe-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: (.account_id | 987654321)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-pipe-numeric
assert_customer_identifier "jq pipes cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-positional-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: limit(1; 987654321)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-positional-numeric
assert_customer_identifier "jq generator arguments retain numeric literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-until-output-string-literal)
cat >"${repo}/filter.jq" <<'EOF'
null | {tenant: until(. != null; "private-customer")}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-until-output-string
assert_customer_identifier "jq until update strings retain literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-until-output-number-literal)
cat >"${repo}/filter.jq" <<'EOF'
null | {account_id: until(. != null; 987654321)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-until-output-number
assert_customer_identifier "jq until update numbers retain literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-range-output-number-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: range(987654321; 987654322)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-range-output-number
assert_customer_identifier "identifier-sized jq range bounds retain literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-signed-fallback-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: .account_id // -987654321}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-signed-fallback-numeric
assert_customer_identifier "jq signed fallbacks retain numeric literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-scientific-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: 9.87654321e8}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-scientific-numeric
assert_customer_identifier "jq scientific notation retains numeric literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-dynamic-arithmetic-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: (.account_id + 987654321)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-dynamic-arithmetic-numeric
assert_customer_identifier "jq dynamic arithmetic retains identifier-sized literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-small-dynamic-arithmetic-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id: ((.account_id * 0) + 12345)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-small-dynamic-arithmetic-numeric
assert_customer_identifier "jq cancelled arithmetic retains small numeric literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-compact-arithmetic-numeric-literal)
cat >"${repo}/filter.jq" <<'EOF'
{account_id:(.account_id+987654321)}
{account_id:(.account_id-987654321)}
{account_id:(((.account_id//0)*0)+12345)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-compact-arithmetic-numeric
assert_violation "compact jq arithmetic operators cannot hide numeric identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-safe-object-index)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: {"private-customer": "example-corp"}["private-customer"]}
{tenant: env["private-customer"]}
{tenant: input["private-customer"]}
{tenant: objects["private-customer"]}
{tenant: payload["private-customer"]}
{account_id: .ids[0] + 1}
{account_id: range(0; 10)}
{account_id: range(0; 1; 987654321)}
{account_id: range(0; 10; first(100000))}
{account_id: range(0; 10; limit(1; 100000))}
{account_id: range(0; 10; [100000][0])}
{account_id: select(.account_id == 987654321)}
{account_id: .ids[987654321]}
{account_id: indices(987654321)}
{account_id: flatten(987654321)}
{account_id: .account_id // 0}
{account_id: .account_id // 123456789012}
{account_id: .account_id + 0e999}
{account_id: .account_id // 0e999}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-safe-object-index
assert_clean "jq indexes and arithmetic constants remain expressions" "$repo" --scope head --mode enforce

repo=$(new_repo jq-even-backslash-string)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "example-corp\\"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-even-backslash
assert_clean "jq even backslashes preserve closing-quote parity" "$repo" --scope head --mode enforce

repo=$(new_repo jq-escaped-interpolation-literal)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\\(private-customer)"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-escaped-interpolation-literal
assert_customer_identifier "escaped jq interpolation cannot hide literal identities" "$repo" --scope head --mode enforce

repo=$(new_repo jq-unicode-placeholder)
cat >"${repo}/filter.jq" <<'EOF'
{tenant: "\u0065xample-corp"}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-unicode-placeholder
assert_clean "jq Unicode escapes resolve before placeholder comparison" "$repo" --scope head --mode enforce

repo=$(new_repo jq-expression-message-strings)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: input.tenant // error("tenant is required")}
{tenant: select(.status == "active")}
{tenant: getpath(["tenant"])}
{tenant: has("tenant")}
{tenant: .["tenant"]}
{tenant: if .kind == "customer" then .tenant else empty end}
{tenant: sub("private"; "example-corp")}
{tenant: gsub("private"; "example-corp")}
{tenant: if "customer" == .kind then .tenant else empty end}
{tenant: startswith("customer")}
{tenant: test("customer")}
{tenant: match("customer")}
{tenant: capture("(?<tenant>customer)").tenant}
{tenant: delpaths([["customer"]])}
{tenant: split("customer")}
{tenant: ltrimstr("customer")}
{tenant: rtrimstr("customer")}
{tenant: inside("customer")}
{tenant: rindex("customer")}
{tenant: bsearch("customer")}
{tenant: setpath(["customer"]; input.tenant)}
{tenant: strptime("%Y-customer-%m")}
{tenant: scan("customer")}
{tenant: sort_by(.kind == "customer")}
{tenant: unique_by(.kind == "customer")}
{tenant: group_by(.kind == "customer")}
{tenant: min_by(.kind == "customer")}
{tenant: max_by(.kind == "customer")}
{tenant: any("customer")}
{tenant: all("customer")}
{tenant: isempty("customer")}
{tenant: IN("customer")}
{tenant: combinations(2)}
{tenant: splits("private-customer")}
{tenant: "private-customer" | in({"private-customer": true})}
{tenant: if "private-customer" then "example-corp" else . end}
{tenant: until("private-customer"; .)}
{tenant: paths("private-customer")}
{tenant: sub("private"; "example-corp"; "g")}
{tenant: gsub("private"; "example-corp"; "g")}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-message-strings
assert_clean "jq function arguments are not output identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-transform-replacement-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: sub("public"; "private-customer")}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-transform-replacement
assert_customer_identifier "jq transform replacements retain literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-nested-transform-replacement-literal)
cat >"${repo}/filter.jq" <<'EOF'
"x" | {tenant: sub("x"; if limit(1; true) then "private-customer" else "example-corp" end)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-nested-transform-replacement
assert_customer_identifier "nested jq separators cannot hide sub replacement literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-nested-gsub-replacement-literal)
cat >"${repo}/filter.jq" <<'EOF'
"x" | {tenant: gsub("x"; if limit(1; true) then "private-customer" else "example-corp" end)}
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-nested-gsub-replacement
assert_customer_identifier "nested jq separators cannot hide gsub replacement literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-setpath-value-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
```jq
{tenant: setpath(["customer"]; "private-customer")}
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-setpath-value
assert_customer_identifier "jq setpath output values retain literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo jq-comment-in-shell-filter)
cat >"${repo}/fixture.mdx" <<'EOF'
```bash
jq '{
  # tenant: private-customer
}' input.json
```
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm jq-filter-comment
assert_customer_identifier "shell-quoted jq comments cannot hide identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo compact-identity-delimiters)
cat >"${repo}/fixture.txt" <<'EOF'
[INFO]tenant=private-customer
EOF
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm compact-delimiter
assert_customer_identifier "compact log delimiters cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo compact-markdown-identity)
cat >"${repo}/fixture.md" <<'EOF'
|tenant: private-customer|
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm compact-table
assert_customer_identifier "compact Markdown tables cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo marked-up-identity-key)
cat >"${repo}/fixture.md" <<'EOF'
`tenant`: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm marked-key
assert_customer_identifier "Markdown key markup cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo whole-inline-identity-field)
cat >"${repo}/fixture.md" <<'EOF'
`tenant: private-customer`
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm whole-inline-field
assert_customer_identifier "inline code cannot hide whole identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo whole-inline-identity-expression)
cat >"${repo}/fixture.md" <<'EOF'
Use `tenant: input.tenant` in this example.
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm whole-inline-expression
assert_clean "inline identity expressions are executable examples" "$repo" --scope head --mode enforce

repo=$(new_repo nested-markup-identity-key)
cat >"${repo}/fixture.md" <<'EOF'
***tenant***: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm nested-markup-key
assert_customer_identifier "nested Markdown key markup cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo mixed-markup-identity-key)
cat >"${repo}/fixture.md" <<'EOF'
**`tenant`**: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm mixed-markup-key
assert_customer_identifier "mixed Markdown key markup cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo emphasized-identity-key)
cat >"${repo}/fixture.md" <<'EOF'
*tenant*: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm emphasized-key
assert_customer_identifier "Markdown emphasis around keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo struck-identity-key)
cat >"${repo}/fixture.md" <<'EOF'
~~tenant~~: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm struck-key
assert_customer_identifier "Markdown strike markup cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-identity-key)
printf '\033[32mtenant=private-customer\033[0m\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-key
assert_customer_identifier "ANSI decoration cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-inside-identity-key)
printf 'ten\033[31mant=private-customer\033[0m\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-inside-key
assert_customer_identifier "ANSI escapes inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-csi-inside-identity-key)
printf 'ten\033[0Kant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-csi-inside-key
assert_customer_identifier "ANSI CSI controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-osc-inside-identity-key)
printf 'ten\033]8;;https://example.com\007\033]8;;\007ant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-osc-inside-key
assert_customer_identifier "ANSI OSC controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-c1-inside-identity-key)
printf 'ten\302\2330Kant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-c1-inside-key
assert_customer_identifier "ANSI C1 CSI controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-c1-osc-inside-identity-key)
printf 'ten\302\2358;;https://example.com\302\234\302\2358;;\302\234ant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-c1-osc-inside-key
assert_customer_identifier "ANSI C1 OSC controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-raw-controls-inside-identity-key)
printf 'te\2330Kn\2358;;https://example.com\234\220payload\234\033(Bant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-raw-controls-inside-key
assert_customer_identifier "raw ANSI controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo ansi-control-strings-inside-identity-key)
printf 'te\302\230payload\302\234n\302\236payload\302\234\302\237payload\302\234ant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm ansi-control-strings-inside-key
assert_customer_identifier "ANSI control strings inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo consecutive-osc-controls-inside-identity-key)
printf 'te\033]0;one\033\\n\033]0;two\033\\ant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm consecutive-osc-controls-inside-key
assert_customer_identifier "consecutive OSC controls cannot consume key text" "$repo" --scope head --mode enforce

repo=$(new_repo terminal-controls-inside-identity-key)
printf 'te\007n\010a\177nt=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm terminal-controls-inside-key
assert_customer_identifier "terminal controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo unicode-format-controls-inside-identity-key)
printf 'te\342\200\213n\342\200\214a\342\201\240n\302\255t=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm unicode-format-controls-inside-key
assert_customer_identifier "Unicode format controls inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo unicode-default-ignorable-inside-identity-key)
printf 'te\357\270\217n\315\217a\341\240\213nt=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm unicode-default-ignorable-inside-key
assert_customer_identifier "Unicode default-ignorable marks cannot hide identity fields" "$repo" --scope head --mode enforce

for codepoint in 0xE0000 0xE0080 0xE01F0 0xE0FFF; do
  repo=$(new_repo "unicode-plane-14-${codepoint}")
  python3 - "$codepoint" "${repo}/fixture.txt" <<'PY'
import pathlib
import sys

pathlib.Path(sys.argv[2]).write_text(
    f"ten{chr(int(sys.argv[1], 0))}ant=private-customer\n",
    encoding="utf-8",
)
PY
  git -C "$repo" add fixture.txt
  git -C "$repo" commit -qm "unicode-plane-14-${codepoint}"
  assert_customer_identifier "Plane-14 default-ignorable ${codepoint} cannot hide identity fields" "$repo" --scope head --mode enforce
done

repo=$(new_repo unicode-filler-controls-inside-identity-key)
printf 'te\341\236\264n\341\205\237a\343\205\244n\357\276\240t=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm unicode-filler-controls-inside-key
assert_customer_identifier "Unicode invisible fillers cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo nul-inside-identity-key)
printf 'ten\000ant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm nul-inside-key
assert_customer_identifier "NUL bytes inside keys cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo multiline-ansi-string-inside-identity-key)
printf 'ten\033Ppayload\nmore\033\\ant=private-customer\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm multiline-ansi-string-inside-key
assert_customer_identifier "multiline ANSI control strings cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo html-identity-field)
cat >"${repo}/fixture.mdx" <<'EOF'
<td>tenant: private-customer</td>
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm html-field
assert_customer_identifier "HTML delimiters cannot hide identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo non-field-identity-suffixes)
cat >"${repo}/fixture.mdx" <<'EOF'
multi-tenant: enabled
non-customer: behavior is documented.
https://example.com/customer: read the guide.
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm non-fields
assert_clean "hyphenated words and URL paths are not identity fields" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-anchor-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: &customer private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm anchored-value
assert_customer_identifier "YAML anchors cannot hide literal identity values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-alias-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared private-customer
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm aliased-value
assert_customer_identifier "YAML aliases cannot hide literal identity values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-alias-document-scope)
cat >"${repo}/fixture.yaml" <<'EOF'
---
actual: &shared private-customer
tenant: *shared
---
actual: &shared example-corp
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm alias-document-scope
assert_customer_identifier "YAML aliases resolve in declaration and document order" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-alias-fake-redefinition)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared private-customer
tenant: *shared
# &shared example-corp
note: "use &shared example-corp"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm alias-fake-redefinition
assert_customer_identifier "comments and strings cannot redefine YAML anchors" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-indirect-alias-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &default private-customer
copy: &shared *default
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm indirect-alias
assert_customer_identifier "indirect YAML aliases cannot hide literal values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-safe-alias-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared example-corp
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm safe-alias
assert_clean "YAML aliases to synthetic values remain clean" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-safe-flow-alias)
cat >"${repo}/fixture.yaml" <<'EOF'
values: [&shared example-corp]
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm safe-flow-alias
assert_clean "YAML flow anchors resolve only their scalar node" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-safe-flow-map-alias)
cat >"${repo}/fixture.yaml" <<'EOF'
{actual: &shared example-corp, tenant: *shared}
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm safe-flow-map-alias
assert_clean "YAML flow mappings resolve aliases on the same line" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-flow-anchor-order)
cat >"${repo}/fixture.yaml" <<'EOF'
{first: &shared example-corp, use: *shared, later: &shared private-customer}
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm flow-anchor-order
assert_customer_identifier "multiple YAML flow anchors apply in event order" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-flow-alias-use-order)
cat >"${repo}/fixture.yaml" <<'EOF'
{first: &shared private-customer, tenant: *shared, later: &shared example-corp}
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm flow-alias-use-order
assert_customer_identifier "YAML aliases use anchor state at their position" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-anchored-doubled-quote)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared 'example-corp''private-customer'
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm anchored-doubled-quote
assert_customer_identifier "YAML anchored doubled quotes retain complete values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-anchor-comma-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared example-corp,private-customer
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm anchor-comma-value
assert_customer_identifier "YAML anchor commas remain block scalar content" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-anchor-hash-identity)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared example-corp#private-customer
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm anchor-hash-value
assert_customer_identifier "YAML anchor hashes without whitespace remain scalar content" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-anchor-tag-order)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared !!str example-corp
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm anchor-tag-order
assert_clean "YAML tags after anchors preserve scalar safety" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-anchor-nonspecific-tag)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared ! example-corp
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm anchor-nonspecific-tag
assert_clean "YAML non-specific tags after anchors preserve scalar safety" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-direct-tags)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: !!str example-corp
tenant: &shared !!str example-corp
tenant: !!str "*shared"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm direct-tags
assert_clean "YAML tags on identity values preserve scalar safety" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-tag-handles)
cat >"${repo}/fixture.yaml" <<'EOF'
%TAG !e! tag:example.com,2020:
---
actual: &shared !e!str example-corp
tenant: *shared
other: &encoded !foo%20bar example-corp
customer: *encoded
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm tag-handles
assert_clean "YAML tag handles preserve anchored scalar safety" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-local-tag-uri-characters)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: !foo@bar example-corp
customer: !foo;bar example-corp
account: !foo&bar example-corp
project: !foo=bar example-corp
namespace: !foo?bar example-corp
actual: &shared !foo$~,'(bar) example-corp
tenant: *shared
tagged: !foo#bar &local_fragment example-corp
tenant: *local_fragment
verbatim: !<tag:example#fragment> &verbatim_fragment example-corp
tenant: *verbatim_fragment
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm local-tag-uri-characters
assert_clean "YAML local-tag URI characters preserve scalar safety" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-local-tag-uri-unsafe-value)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: !foo@bar private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm local-tag-uri-unsafe-value
assert_customer_identifier "YAML local tags cannot hide identity values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-quoted-alias-literal)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared private-customer
tenant: "*shared"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm quoted-alias-literal
assert_clean "quoted YAML alias syntax remains literal content" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-nested-flow-context)
cat >"${repo}/fixture.yaml" <<'EOF'
{metadata: {}, tenant: example-corp, other: default}
{metadata: {}, full_name: Dana R., other: default}
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm nested-flow-context
assert_clean "nested YAML flow collections preserve field delimiters" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-anchor-state)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared private-customer
note: |
  &shared example-corp
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-anchor-state
assert_customer_identifier "YAML block text cannot redefine anchors" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-safe-block-alias)
cat >"${repo}/fixture.yaml" <<'EOF'
actual: &shared |
  example-corp
tenant: *shared
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm safe-block-alias
assert_clean "YAML aliases resolve safe anchored block scalars" "$repo" --scope head --mode enforce

repo=$(new_repo emphasized-identity-value)
cat >"${repo}/fixture.md" <<'EOF'
tenant: **private-customer**
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm emphasized-value
assert_customer_identifier "Markdown emphasis cannot hide literal identity values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-scalar)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: |
  documented example text
namespace: >-
  documented example text
account: |2-
    documented example text
project: |
  Use the documented example tenant.
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-scalar
assert_clean "YAML block-scalar indicators are syntax" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-scalar-literal)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: |
  private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-scalar-literal
assert_customer_identifier "YAML block scalars cannot hide literal identity values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-scalar-organization)
cat >"${repo}/fixture.yaml" <<'EOF'
customer_name: |
  Private Customer Inc.
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-scalar-organization
assert_customer_identifier "YAML block scalars inspect multiword organization values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-scalar-comment)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: |
  private-customer # division
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-scalar-comment
assert_customer_identifier "YAML block scalar comments cannot hide identity values" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-scalar-safe-prefix)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: |
  example-corp # private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-scalar-safe-prefix
assert_customer_identifier "safe block prefixes cannot hide identity suffixes" "$repo" --scope head --mode enforce

repo=$(new_repo yaml-block-scalar-hash-content)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: |
  # private-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm block-scalar-hash-content
assert_customer_identifier "hash-prefixed block content remains identity data" "$repo" --scope head --mode enforce

repo=$(new_repo markdown-yaml-block-scalar-literal)
cat >"${repo}/fixture.md" <<'EOF'
```yaml
tenant: |
  private-customer
```
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm markdown-block-scalar
assert_customer_identifier "Markdown YAML blocks inspect identity scalar bodies" "$repo" --scope head --mode enforce

repo=$(new_repo fenced-source-expressions)
cat >"${repo}/fixture.md" <<'EOF'
```javascript
const context = { tenant: input.tenant };
```
```go
context := Config{Namespace: input.Namespace}
```
```hcl
tenant = var.tenant
```
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm fenced-expressions
assert_clean "fenced source expressions are not identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo attributed-fenced-source-expression)
cat >"${repo}/fixture.md" <<'EOF'
```{.javascript}
const context = { tenant: input.tenant };
```
```{js}
const context = { tenant: input.tenant };
```
```{#example .javascript}
const context = { tenant: input.tenant };
```
```{.js,#example}
const context = { tenant: input.tenant };
```
```{python, echo=FALSE}
context = {"tenant": input.tenant}
```
```{python,echo=FALSE}
context = {"tenant": input.tenant}
```
```javascript
```not-a-closing-fence
const context = { tenant: input.tenant };
```
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm attributed-fence
assert_clean "attributed source fences preserve expression context" "$repo" --scope head --mode enforce

repo=$(new_repo blockquoted-source-fences)
cat >"${repo}/fixture.md" <<'EOF'
> ```javascript
> const context = { tenant: input.tenant };
> ```
> ```jq
> {tenant: .tenant}
> ```
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm blockquoted-fences
assert_clean "blockquoted source fences preserve expression context" "$repo" --scope head --mode enforce

repo=$(new_repo list-item-source-fences)
cat >"${repo}/fixture.md" <<'EOF'
- ```javascript
  const context = { tenant: input.tenant };
  ```
- - ```javascript
    const context = { tenant: input.tenant };
    ```
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm list-item-fences
assert_clean "list-item source fences preserve expression context" "$repo" --scope head --mode enforce

repo=$(new_repo indented-invalid-source-fence)
cat >"${repo}/fixture.md" <<'EOF'
    ```javascript
tenant: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm indented-invalid-source-fence
assert_customer_identifier "four-space Markdown fences cannot create source context" "$repo" --scope head --mode enforce

repo=$(new_repo long-ordered-invalid-source-fence)
cat >"${repo}/fixture.md" <<'EOF'
1234567890. ```javascript
account: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm long-ordered-invalid-source-fence
assert_customer_identifier "ten-digit list markers cannot create source fences" "$repo" --scope head --mode enforce

repo=$(new_repo backtick-info-invalid-source-fence)
cat >"${repo}/fixture.md" <<'EOF'
```javascript `invalid
customer: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm backtick-info-invalid-source-fence
assert_customer_identifier "backticks invalidate backtick-fence info strings" "$repo" --scope head --mode enforce

repo=$(new_repo indented-invalid-source-fence-closer)
cat >"${repo}/fixture.md" <<'EOF'
```javascript
    ```
const context = { tenant: input.tenant };
```
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm indented-invalid-source-fence-closer
assert_clean "four-space fence-like lines do not close top-level source fences" "$repo" --scope head --mode enforce

repo=$(new_repo tab-invalid-source-fence-closer)
printf '```javascript\n\t```\nconst context = { tenant: input.tenant };\n```\n' >"${repo}/fixture.md"
git -C "$repo" add fixture.md
git -C "$repo" commit -qm tab-invalid-source-fence-closer
assert_clean "tab-indented fence-like lines do not close source fences" "$repo" --scope head --mode enforce

repo=$(new_repo list-padding-invalid-source-fence)
cat >"${repo}/fixture.md" <<'EOF'
-     ```javascript
tenant: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm list-padding-invalid-source-fence
assert_customer_identifier "excess list padding cannot create source fences" "$repo" --scope head --mode enforce

repo=$(new_repo blockquote-padding-invalid-source-fence)
cat >"${repo}/fixture.md" <<'EOF'
>     ```javascript
tenant: private-customer
EOF
git -C "$repo" add fixture.md
git -C "$repo" commit -qm blockquote-padding-invalid-source-fence
assert_customer_identifier "excess blockquote padding cannot create source fences" "$repo" --scope head --mode enforce

repo=$(new_repo source-file-expressions)
cat >"${repo}/fixture.tf" <<'EOF'
locals {
  tenant = var.tenant
}
EOF
git -C "$repo" add fixture.tf
git -C "$repo" commit -qm source-expression
assert_clean "Terraform expressions are not identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo source-attribute-literal)
cat >"${repo}/fixture.tf" <<'EOF'
config.tenant = "private-customer"
EOF
git -C "$repo" add fixture.tf
git -C "$repo" commit -qm source-attribute-literal
assert_customer_identifier "source attribute assignments retain literal enforcement" "$repo" --scope head --mode enforce

repo=$(new_repo source-comment-literal)
cat >"${repo}/fixture.ts" <<'EOF'
// tenant: private-customer
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm comment-literal
assert_customer_identifier "source comments cannot hide identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo source-comment-expression)
cat >"${repo}/fixture.ts" <<'EOF'
// tenant: input.tenant
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm comment-expression
assert_clean "source comments can document identity expressions" "$repo" --scope head --mode enforce

repo=$(new_repo jq-comment-literal)
cat >"${repo}/filter.jq" <<'EOF'
# tenant: private-customer
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-comment-literal
assert_customer_identifier "jq comments cannot hide identity literals" "$repo" --scope head --mode enforce

repo=$(new_repo jq-comment-expression)
cat >"${repo}/filter.jq" <<'EOF'
# tenant: input.tenant
EOF
git -C "$repo" add filter.jq
git -C "$repo" commit -qm jq-comment-expression
assert_clean "jq comments can document identity expressions" "$repo" --scope head --mode enforce

repo=$(new_repo public-ip-contexts)
cat >"${repo}/fixture.txt" <<'EOF'
rfc6598=100.64.0.1/10
mdns=224.0.0.251
browser=Mozilla/5.0 Chrome/136.0.0.0 Safari/537.36
terminal={ TERM_PROGRAM_VERSION: "1.22.103.0" }
EOF
svg_coordinate="4.254."
svg_coordinate+="141.138"
printf '<svg><path d="M0 0 %s Z"/></svg>\n' "$svg_coordinate" >>"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm contexts
assert_clean "protocol, version, and SVG coordinate syntax is not a public IP" "$repo" --scope head --mode audit

repo=$(new_repo public-ip)
public_ip="8.8."
public_ip+="4.4"
printf 'version=1; origin_ip=%s\n' "$public_ip" >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm public-ip
assert_violation "globally routable unicast address" "$repo" --scope head --mode audit

repo=$(new_repo action-reference)
printf 'uses: f5-sales-demo/docs-control@main\nremote: git@github.com:f5-sales-demo/docs-control.git\n' >"${repo}/workflow.yaml"
git -C "$repo" add workflow.yaml
git -C "$repo" commit -qm action
assert_clean "GitHub action references are not emails" "$repo" --scope head --mode enforce

repo=$(new_repo non-contact-at-syntax)
cat >"${repo}/fixture.txt" <<'EOF'
clone=https://x-access-token:${TOKEN}@github.com/example/repository.git
credential=https://user:secret@github.com/example/repository.git
ssh=ssh://git@gitlab.com/example/repository.git
patch=owner/repository@1.2.3.patch
anchor=`@line.chunk.path
EOF
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm syntax
assert_clean "URI, package, and anchor syntax are not contact emails" "$repo" --scope head --mode enforce

repo=$(new_repo scoped-npm-coordinate)
cat >"${repo}/package.json" <<'EOF'
{
  "patchedDependencies": {
    "@tobilu/qmd@2.8.3": "patches/@tobilu%2Fqmd@2.8.3.patch"
  }
}
EOF
cat >"${repo}/bun.lock" <<'EOF'
"patchedDependencies": {
  "@tobilu/qmd@2.8.3": "patches/@tobilu%2Fqmd@2.8.3.patch",
}
EOF
git -C "$repo" add package.json bun.lock
assert_clean "staged scoped npm package coordinates are not contact emails" "$repo" --scope staged --mode enforce

repo=$(new_repo email)
printf 'email: person@customer.local\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm email
assert_violation "personal email" "$repo" --scope head --mode enforce

repo=$(new_repo phone)
printf 'phone: +1 212 555 1234\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm phone
assert_violation "non-fictional phone" "$repo" --scope head --mode enforce

repo=$(new_repo person-name)
printf 'full_name: Jane Doe\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm name
assert_violation "literal structured person name" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-person-name)
cat >"${repo}/fixture.yaml" <<'EOF'
full_name: "Dana R., Private Customer"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm quoted-person-name
assert_violation "quoted punctuation cannot truncate person-name inspection" "$repo" --scope head --mode enforce

repo=$(new_repo quoted-personal-record)
cat >"${repo}/fixture.yaml" <<'EOF'
street_address: "default,private-location"
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm quoted-personal-record
assert_violation "quoted punctuation cannot truncate personal-record inspection" "$repo" --scope head --mode enforce

repo=$(new_repo numeric-person-fields)
printf 'first_name: 101\nlast_name: "202"\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm numeric-name
assert_clean "numeric person fields are not names" "$repo" --scope head --mode enforce

repo=$(new_repo home-path)
printf 'cache=/Users/%s/.cache/tool\n' "$SYNTHETIC_USER" >"${repo}/config.ini"
git -C "$repo" add config.ini
git -C "$repo" commit -qm path
assert_violation "personal home path" "$repo" --scope head --mode enforce

repo=$(new_repo placeholder-paths)
SYNTHETIC_SERVICE_USER=xcsh
printf 'mac=/Users/you/work ci=/home/runner/work service=/home/%s/.config variable=/home/${USERNAME}/work route=/home/%s\n' \
  "$SYNTHETIC_SERVICE_USER" index >"${repo}/config.ini"
git -C "$repo" add config.ini
git -C "$repo" commit -qm paths
assert_clean "placeholder, CI, service, and variable home paths" "$repo" --scope head --mode enforce

repo=$(new_repo embedded-home-tokens)
printf 'keys=Shift+page/%s/%s route=service/%s/%s windows=prefixC:\\%s\\%s\n' home end Users list Users record >"${repo}/config.ini"
git -C "$repo" add config.ini
git -C "$repo" commit -qm tokens
assert_clean "embedded home-like tokens are not absolute paths" "$repo" --scope head --mode enforce

repo=$(new_repo tenant)
printf 'tenant: real-customer\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm tenant
assert_violation "literal customer tenant" "$repo" --scope head --mode enforce

repo=$(new_repo compact-json-after-field)
printf '{"status":"active","tenant":"tenant-literal"}\n' >"${repo}/fixture.json"
git -C "$repo" add fixture.json
git -C "$repo" commit -qm compact-json
assert_violation "compact JSON tenant after another field" "$repo" --scope head --mode enforce

repo=$(new_repo nested-compact-json)
printf '{"metadata":{"namespace":"namespace-literal"}}\n' >"${repo}/fixture.json"
git -C "$repo" add fixture.json
git -C "$repo" commit -qm nested-json
assert_violation "nested compact JSON namespace" "$repo" --scope head --mode enforce

repo=$(new_repo bracket-delimited-flow-yaml)
printf '[tenant: tenant-literal]\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm flow-yaml
assert_violation "bracket-delimited YAML tenant" "$repo" --scope head --mode enforce

repo=$(new_repo log-level-prefix)
printf 'INFO tenant: tenant-literal\n' >"${repo}/fixture.mdx"
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm log-prefix
assert_violation "tenant after a log-level prefix" "$repo" --scope head --mode enforce

repo=$(new_repo timestamp-prefix)
printf '2026-08-01T12:34:56Z customer_id: customer-record\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm timestamp-prefix
assert_violation "customer identifier after an ISO timestamp" "$repo" --scope head --mode enforce

repo=$(new_repo markdown-blockquote)
printf '> tenant: tenant-literal\n' >"${repo}/fixture.mdx"
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm blockquote
assert_violation "tenant inside a Markdown blockquote" "$repo" --scope head --mode enforce

repo=$(new_repo indented-yaml-list)
printf 'items:\n  - tenant: tenant-literal\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm yaml-list
assert_violation "tenant inside an indented YAML list" "$repo" --scope head --mode enforce

repo=$(new_repo markdown-table)
printf '| tenant: tenant-literal |\n' >"${repo}/fixture.mdx"
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm markdown-table
assert_violation "tenant inside a Markdown table" "$repo" --scope head --mode enforce

repo=$(new_repo decorated-log-prefix)
printf '2026-08-01T12:34:56Z INFO api-component tenant: tenant-literal\n' >"${repo}/fixture.txt"
git -C "$repo" add fixture.txt
git -C "$repo" commit -qm decorated-log
assert_violation "tenant after a decorated log prefix" "$repo" --scope head --mode enforce

repo=$(new_repo dot-prefixed-yaml-literal)
printf 'namespace: .namespace-literal\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm dot-literal
assert_violation "dot-prefixed YAML identity literal" "$repo" --scope head --mode enforce

repo=$(new_repo suffixed-customer-identifiers)
printf 'project_id: customer-project\nsubscription_name: customer-plan\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm identifiers
assert_violation "suffixed project and subscription identifiers" "$repo" --scope head --mode enforce

repo=$(new_repo code-expressions)
cat >"${repo}/fixture.ts" <<'EOF'
interface Context {
  tenant: string;
  namespace?: string;
  full_name: string;
}
const namespace = namespaceOverride ?? defaults.namespace;
const context = {
  tenant: status.activeTenant,
  namespace: String(input.namespace),
  full_name: user.displayName,
};
const typed: { tenant: string | null } = context;
const fallback = { namespace: status.activeNamespace ?? "default" };
const indexed = { tenant: tenants["active"] };
EOF
cat >"${repo}/fixture.cpp" <<'EOF'
auto namespace = context->namespace;
auto tenant = Context::resolve(input);
EOF
git -C "$repo" add fixture.ts fixture.cpp
git -C "$repo" commit -qm expressions
assert_clean "code types and expressions are not literal identity values" "$repo" --scope head --mode enforce

repo=$(new_repo source-template-and-signature-expressions)
cat >"${repo}/fixture.ts" <<'EOF'
if (accountId) identifiers.add(`account:${accountId}`);
parts.push(`Tenant: ${pageState.tenant ?? "unknown"} (${pageState.environment ?? "unknown"} environment)`);
const message = `namespace: ${currentNamespace}. Target this namespace for subsequent operations.`;
#build(manifest: ResourceManifest, namespace: string): Record<string, unknown> {
  return { manifest, namespace };
}
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm source-template-and-signature-expressions
assert_clean "source template expressions and signatures are not YAML data" "$repo" --scope head --mode enforce

repo=$(new_repo source-template-literal-composition)
cat >"${repo}/fixture.ts" <<'EOF'
const literal = `tenant:${"private-customer"}`;
const composed = `namespace:${namespaceName}-customer`;
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm source-template-literal-composition
assert_violation "template interpolation cannot hide literal identity output" "$repo" --scope head --mode enforce

repo=$(new_repo code-string-literal)
cat >"${repo}/fixture.ts" <<'EOF'
const context = { tenant: "real-customer", full_name: "Jane Doe" };
const raw = { namespace: `real-customer` };
EOF
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm literal
assert_violation "quoted identity literals in code" "$repo" --scope head --mode enforce

repo=$(new_repo code-numeric-literal)
printf 'const context = { account_id: 987654321 };\n' >"${repo}/fixture.ts"
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm numeric
assert_violation "numeric identity literals in code" "$repo" --scope head --mode enforce

repo=$(new_repo embedded-serialized-schema)
printf 'export const schema = "params:\\n  namespace:\\n    required: true\\n";\n' >"${repo}/fixture.ts"
git -C "$repo" add fixture.ts
git -C "$repo" commit -qm schema
assert_clean "escaped serialized key headings are not field values" "$repo" --scope head --mode enforce

repo=$(new_repo escaped-structured-placeholder)
cat >"${repo}/fixture.mdx" <<'EOF'
Example: `{NAMESPACE=\"example-namespace"}`
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm escaped-structured-placeholder
assert_clean "escaped structured placeholder remains clean" "$repo" --scope head --mode enforce

repo=$(new_repo escaped-structured-literal)
cat >"${repo}/fixture.mdx" <<'EOF'
Example: `{NAMESPACE=\"private-namespace"}`
EOF
git -C "$repo" add fixture.mdx
git -C "$repo" commit -qm escaped-structured-literal
assert_customer_identifier "escaped structured literal remains enforced" "$repo" --scope head --mode enforce

repo=$(new_repo schematic-identities)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: staging
namespace: default
project: demo
account: value
extension_namespace: x-f5xc-
tenant: x-f5xc-tenant
namespace: x-f5xc-tenant-namespace
example_namespace: user_namespace
security_namespace: security
domain: tenant_and_identity
display_name: xc container services
person_name: xc kubernetes service
empty_tenant: {}
empty_namespace: []
zip_code: '90210'
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm schematic
assert_clean "generic environment, schema identities, and reserved records" "$repo" --scope head --mode enforce

repo=$(new_repo x-f5xc-customer-identifier)
printf 'tenant: x-f5xc-real-customer\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm x-f5xc-customer
assert_violation "x-f5xc customer identifiers remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo composite-schematic-identities)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: example-corp|staging
account_name: example-partners|production
namespace: library
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm composite-schematic
assert_clean "composite and public schema identities" "$repo" --scope head --mode enforce

repo=$(new_repo composite-customer-identifiers)
cat >"${repo}/fixture.yaml" <<'EOF'
tenant: real-customer|staging
account_name: example-corp|real-customer
EOF
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm composite-customer
assert_violation "composite literal customer identifiers" "$repo" --scope head --mode enforce

repo=$(new_repo json-schema-identity-context)
cat >"${repo}/fixture.json" <<'EOF'
{
  "description": "Set namespace: customer-selected and first_name: customer-selected.",
  "properties": {
    "namespace": {"type": "string"},
    "first_name": {"type": "string"},
    "zip_code": {"type": "string"}
  }
}
EOF
git -C "$repo" add fixture.json
git -C "$repo" commit -qm json-schema-context
assert_clean \
  "JSON schema prose and property containers are not literal identity values" \
  "$repo" --scope head --mode enforce

repo=$(new_repo json-scalar-identity)
printf '%s\n' \
  '{"namespace":"customer-selected","first_name":"Customer Selected","zip_code":"12345"}' \
  >"${repo}/fixture.json"
git -C "$repo" add fixture.json
git -C "$repo" commit -qm json-scalar-identity
assert_violation "JSON scalar identity values remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo json-array-identity)
printf '%s\n' '{"tenant":["customer-selected"]}' >"${repo}/fixture.json"
git -C "$repo" add fixture.json
git -C "$repo" commit -qm json-array-identity
assert_violation "JSON identity arrays remain enforced" "$repo" --scope head --mode enforce

repo=$(new_repo sensitive-query)
printf 'redirect=/done?email=person%%40customer.local\n' >"${repo}/config.ini"
git -C "$repo" add config.ini
git -C "$repo" commit -qm query
assert_violation "PII in URL query parameter" "$repo" --scope head --mode enforce

repo=$(new_repo legal-attribution)
printf 'Copyright Example Author <author@upstream.local>\n' >"${repo}/LICENSE"
git -C "$repo" add LICENSE
git -C "$repo" commit -qm license
assert_clean "legal attribution" "$repo" --scope head --mode enforce

repo=$(new_repo git-provenance)
git -C "$repo" config user.email contributor@users.noreply.github.com
printf 'change\n' >>"${repo}/README.md"
git -C "$repo" add README.md
git -C "$repo" commit -qm change
assert_clean "Git author provenance is not scanned" "$repo" --scope history --mode enforce

repo=$(new_repo commit-trailer-provenance)
printf 'change\n' >>"${repo}/README.md"
git -C "$repo" add README.md
git -C "$repo" commit -qm $'change\n\nCo-authored-by: Example Contributor <contributor@upstream.local>'
assert_clean "commit attribution trailers are provenance" "$repo" --scope history --mode enforce

repo=$(new_repo staged)
printf 'email: person@customer.local\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
assert_clean "HEAD ignores staged-only content" "$repo" --scope head --mode enforce
assert_violation "staged scope reads the index" "$repo" --scope staged --mode enforce

repo=$(new_repo staged-excludes-unchanged)
printf 'email: person@customer.local\n' >"${repo}/unchanged.yaml"
git -C "$repo" add unchanged.yaml
git -C "$repo" commit -qm existing-finding
printf 'clean staged content\n' >"${repo}/changed.txt"
git -C "$repo" add changed.txt
assert_clean \
  "staged scope excludes unchanged tracked blobs" \
  "$repo" --scope staged --mode enforce

repo=$(new_repo staged-modification)
printf 'clean\n' >"${repo}/modified.yaml"
git -C "$repo" add modified.yaml
git -C "$repo" commit -qm clean-fixture
printf 'email: person@customer.local\n' >"${repo}/modified.yaml"
git -C "$repo" add modified.yaml
assert_violation "staged scope reads modified blobs" "$repo" --scope staged --mode enforce

repo=$(new_repo staged-unusual-path)
unusual_path=$'line\nbreak.yaml'
printf 'email: person@customer.local\n' >"${repo}/${unusual_path}"
git -C "$repo" add "$unusual_path"
assert_violation "staged scope is NUL-safe" "$repo" --scope staged --mode enforce

repo=$(new_repo staged-deletion)
printf 'email: person@customer.local\n' >"${repo}/deleted.yaml"
git -C "$repo" add deleted.yaml
git -C "$repo" commit -qm existing-finding
git -C "$repo" rm -q deleted.yaml
assert_clean "staged scope excludes deleted blobs" "$repo" --scope staged --mode enforce

repo=$(new_repo staged-unmerged)
printf 'base\n' >"${repo}/conflict.txt"
git -C "$repo" add conflict.txt
git -C "$repo" commit -qm conflict-base
git -C "$repo" switch -q -c other
printf 'other\n' >"${repo}/conflict.txt"
git -C "$repo" commit -qam conflict-other
git -C "$repo" switch -q main
printf 'main\n' >"${repo}/conflict.txt"
git -C "$repo" commit -qam conflict-main
git -C "$repo" merge other >/dev/null 2>&1 || true
assert_error "staged scope rejects an unmerged index" "$repo" --scope staged --mode enforce

repo=$(new_repo staged-gitlink)
gitlink_oid=$(git -C "$repo" rev-parse HEAD)
git -C "$repo" update-index --add --cacheinfo "160000,$gitlink_oid,vendor/module"
assert_clean "staged scope ignores gitlink entries" "$repo" --scope staged --mode enforce

repo=$(new_repo untracked)
printf 'email: person@customer.local\n' >"${repo}/scratch.yaml"
assert_clean "untracked files are out of scope" "$repo" --scope staged --mode enforce

repo=$(new_repo history)
printf 'email: person@customer.local\n' >"${repo}/removed.yaml"
git -C "$repo" add removed.yaml
git -C "$repo" commit -qm add
git -C "$repo" rm -q removed.yaml
git -C "$repo" commit -qm remove
assert_clean "removed PII is absent from HEAD" "$repo" --scope head --mode enforce
assert_violation "reachable historical blob is scanned" "$repo" --scope history --mode enforce

repo=$(new_repo history-path-alias)
printf 'synthetic pixels\n' >"${repo}/a-safe.txt"
cp "${repo}/a-safe.txt" "${repo}/z-review.png"
git -C "$repo" add a-safe.txt z-review.png
git -C "$repo" commit -qm aliases
git -C "$repo" rm -q z-review.png
git -C "$repo" commit -qm remove-media-alias
assert_clean \
  "removed media alias is absent from HEAD" \
  "$repo" --scope head --mode audit
assert_single_finding \
  "history scans removed aliases of still-reachable blobs" \
  "$repo" media-review review --scope history --mode audit

repo=$(new_repo history-tree-ref)
printf 'synthetic pixels\n' >"${repo}/a-safe.txt"
cp "${repo}/a-safe.txt" "${repo}/z-review.png"
git -C "$repo" add a-safe.txt z-review.png
tree=$(git -C "$repo" write-tree)
git -C "$repo" update-ref refs/tags/tree-only "$tree"
assert_single_finding \
  "history scans every path in a tree-only ref" \
  "$repo" media-review review --scope history --mode audit

repo=$(new_repo commit-message)
printf 'change\n' >>"${repo}/README.md"
git -C "$repo" add README.md
git -C "$repo" commit -qm 'Contact person@customer.local'
assert_violation "commit message is scanned without author metadata" "$repo" --scope history --mode enforce

repo=$(new_repo media)
printf '\x89PNG\r\n\x1a\nsynthetic-image' >"${repo}/screen.png"
git -C "$repo" add screen.png
git -C "$repo" commit -qm media
assert_clean "media inventory is advisory in enforce mode" "$repo" --scope head --mode enforce
assert_violation "media requires review in audit mode" "$repo" --scope head --mode audit
grep -q 'media-review' "${WORK}/stdout" || {
  echo "[FAIL] audit media finding did not identify its category"
  FAIL=1
}

repo=$(new_repo binary-metadata)
printf '\x89PNG\r\n\x1a\nAuthor\x00person@customer.local\x00' >"${repo}/screen.png"
git -C "$repo" add screen.png
git -C "$repo" commit -qm metadata
assert_violation "PII-shaped binary metadata" "$repo" --scope head --mode enforce

repo=$(new_repo binary-package-syntax)
printf '\x89PNG\r\n\x1a\nowner/repository@1.2.3.patch\x00' >"${repo}/screen.png"
git -C "$repo" add screen.png
git -C "$repo" commit -qm metadata
assert_clean "email-like binary package syntax is not contact metadata" "$repo" --scope head --mode enforce

repo=$(new_repo binary-compression-token)
printf '\x89PNG\r\n\x1a\nA@b.Co\x00' >"${repo}/screen.png"
git -C "$repo" add screen.png
git -C "$repo" commit -qm metadata
assert_clean "short binary compression token is not contact metadata" "$repo" --scope head --mode enforce

repo=$(new_repo media-compression-email)
printf 'RIFFfixture@bytes.invalidWEBP' >"${repo}/screen.webp"
git -C "$repo" add screen.webp
git -C "$repo" commit -qm media
assert_clean "email-shaped media bytes without a metadata key are ignored" "$repo" --scope head --mode enforce

repo=$(new_repo odd-filename)
printf 'email: person@customer.local\n' >"${repo}/- odd name.yaml"
git -C "$repo" add -- '- odd name.yaml'
git -C "$repo" commit -qm odd
assert_violation "option-like filename containing spaces" "$repo" --scope head --mode enforce
assert_violation \
  "history preserves option-like filenames containing spaces" \
  "$repo" --scope history --mode enforce

repo=$(new_repo symlink)
ln -s "/Users/${SYNTHETIC_USER}/private" "${repo}/linked"
git -C "$repo" add linked
git -C "$repo" commit -qm symlink
assert_clean "scanner does not dereference symlinks" "$repo" --scope head --mode enforce
assert_clean \
  "history scanner does not dereference symlinks" \
  "$repo" --scope history --mode enforce

repo=$(new_repo json-output)
printf 'email: person@customer.local\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm json
assert_violation "JSON output still reports findings" "$repo" --scope head --mode enforce --format json
python3 -m json.tool "${WORK}/stdout" >/dev/null || {
  echo "[FAIL] --format json did not emit valid JSON"
  FAIL=1
}

repo=$(new_repo no-suppression)
printf 'email: person@customer.local # pii:allow\n' >"${repo}/fixture.yaml"
git -C "$repo" add fixture.yaml
git -C "$repo" commit -qm suppression
assert_violation "inline suppression markers are not an escape hatch" "$repo" --scope head --mode enforce

mkdir -p "${WORK}/not-a-repository"
assert_error "non-repository fails closed" "${WORK}/not-a-repository" --scope head --mode enforce

if [ "$FAIL" -ne 0 ]; then
  echo "check-pii tests FAILED"
  exit 1
fi
echo "check-pii tests passed"
