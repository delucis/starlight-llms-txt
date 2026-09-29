# Documentation style guide

Conventions for every piece of published content this fleet produces: blog articles, how-to
guides, demo guides, lab walkthroughs, product documentation, README files, code comments, and
conference material.

This is a **managed file** owned by docs-control and synced to every downstream repository. Do
not edit it in a downstream repo — a hook blocks it. To change a rule, open an issue in
docs-control and the change propagates fleet-wide. See `CONTRIBUTING.md`.

Two goals, in priority order:

1. **Nothing in an example can cause harm if a reader copies and pastes it.** No traffic sent to
   infrastructure we do not own, no live credentials, no real customer data.
2. **Examples are consistent, so a reader learns the pattern once.** Someone who sees
   `203.0.113.10` in three different demo guides knows it is a placeholder without being told.

Goal 1 is not negotiable. Goal 2 is a strong default.

## Reserved network identifiers

Use only identifiers that the IETF, IANA, or ICANN has reserved for documentation. These are
guaranteed not to route, not to resolve, and not to belong to anyone.

| Identifier | Use this | Reservation |
| --- | --- | --- |
| IPv4, public-facing | `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` | RFC 5737 (TEST-NET-1/2/3) |
| IPv6 | `2001:db8::/32` | RFC 3849 |
| IPv6, large topologies | `3fff::/20` | RFC 9637 |
| Registrable domains | `example.com`, `example.net`, `example.org` | RFC 2606 |
| Top-level domains | `.example`, `.test`, `.invalid`, `.localhost` | RFC 2606, RFC 6761 |
| Internal and private hostnames | `.internal` | ICANN, July 2024 — never delegated |
| Autonomous system numbers | `64496`-`64511` (16-bit), `65536`-`65551` (32-bit) | RFC 5398 |
| MAC and EUI-48 addresses | `00-00-5E-00-53-00` through `00-00-5E-00-53-FF` | RFC 7042 |
| Phone numbers, United States | `800-555-0100` through `800-555-0199` | NANP fictional-use range |

### Which IPv4 range to reach for

- **TEST-NET-1/2/3 for anything representing a public address**: origin server addresses, load
  balancer addresses, DNS `A` records, advertised prefixes, service policy allowlists and
  blocklists, and `curl` targets. This is where a real-looking address does actual damage — a
  reader pastes an allowlist entry into production and now a stranger's host is trusted.
- **RFC 1918 space (`10/8`, `172.16/12`, `192.168/16`) for private and lab addressing.** Do not
  substitute TEST-NET here. If the reader will genuinely configure `10.1.0.0/16` on a cloud
  virtual network, write `10.1.0.0/16` — a fabricated public address in that position is less
  accurate and no safer.
- **`100.64.0.0/10` (RFC 6598)** when the example is specifically about carrier-grade address
  translation.
- **RFC 6996 private ASNs (`64512`-`65534`)** in lab routing configuration a reader will paste;
  the RFC 5398 documentation ASNs in prose and diagrams.

### Assign ranges by role, and stay consistent

Pick one convention and reuse it everywhere, so the ranges themselves carry meaning:

| Role | Range |
| --- | --- |
| Client, attacker, or traffic source | `192.0.2.0/24` |
| Origin servers and origin pool members | `198.51.100.0/24` |
| Published service addresses and load balancer addresses | `203.0.113.0/24` |

### Use IPv6 that reflects reality

`2001:db8::/32` is too small to demonstrate credible IPv6 address planning — a per-site `/48`
allocation does not fit inside a `/32`. When the example is about address architecture, use
`3fff::/20`, reserved by RFC 9637 in 2024 for exactly this reason. For a single illustrative
address, `2001:db8::/32` remains the better-recognized choice.

### Domains and hostnames

- Default to `example.com`. When you need several names, prefer subdomains
  (`api.example.com`, `shop.example.com`, `origin.example.com`) over inventing new registrable
  domains. A subdomain of a reserved domain is itself safe.
- When a scenario genuinely involves two separate organizations, use `example.com` and
  `example.net`.
- Lab and internal hostnames: `ce01.lab.internal`, `origin.example.test`.
- Never use a domain you have not verified as reserved or F5-owned. "It looks fake" is not a
  reservation. `acme.com`, `mycompany.com`, `test.com`, `foo.com`, and `example.io` all resolve
  to real parties.

## Fictitious organizations and people

### Do not use ACME as a placeholder

Two independent reasons:

1. **It is not a cleared placeholder.** "Acme" is a live trademark in several classes and
   multiple operating companies use it. Placeholders that are genuinely safe — Microsoft's
   Contoso, Google's Altostrat — were trademark-cleared and their domains are company-owned and
   redirected. ACME has neither property.
2. **In networking and TLS content the name is already taken.** The Automated Certificate
   Management Environment (ACME) service, protocol, and challenge flow are legitimate registered
   concepts defined by RFC 8555. They underpin Let's Encrypt, automated certificate management in
   F5 Distributed Cloud, and most modern platforms. "ACME certificate renewal" in one of our
   documents is a genuine technical reference, not a fictional organization.

This restriction applies only to fictitious organizations, tenants, people, and other placeholder
values. Use ACME when the content genuinely documents the registered service, protocol, or
challenge flow, and keep that terminology exact. Rename existing ACME placeholders as you touch
the surrounding content; no separate cleanup sweep is required.

### Organization names

Use the `Example` pattern. It needs no trademark clearance and no domain registration, it maps
onto the reserved `example.com`, and it is self-documenting:

| Role | Name | Domain |
| --- | --- | --- |
| Primary customer or tenant | Example Corp | `example.com` |
| Second party, partner, or acquisition | Example Partners | `example.net` |
| Vertical-specific scenarios | Example Retail, Example Bank, Example Health | subdomain or `example.org` |

If a scenario needs a name that reads less generic, clear it through F5 legal first and add it to
this table. Do not coin one ad hoc.

### Person names

Use short, culture-neutral given names with a surname initial: `Dana R.`, `Kiran M.`,
`Quinn N.`, `Alex T.`, `Yuri S.`, `Amal B.`, `Noam K.`, `Rosario L.`

- Use **they/them** for placeholder people unless the scenario has a specific reason to do
  otherwise. Do not assign gender to roles.
- Do not distribute names by stereotype. The security engineer, the finance approver, and the
  attacker in a scenario should not be drawn from predictable demographics.
- Never cast a real colleague, customer contact, or executive as an example persona.

### Email addresses

A placeholder name at a reserved domain: `dana@example.com`, `kiran.m@example.net`. Role
addresses are fine: `security@example.com`, `noreply@example.com`.

### Keep public content synthetic

Every repository example, template, and fixture remains fictional or placeholder-based. Generate
realistic-looking data for public documentation, demo tenants, screenshots, issues, pull requests,
logs, telemetry, and other published evidence. A sanitized real dataset is still a real dataset;
treat removal of identifying details as unreliable and synthesis as the public-content default.

Private local drafts and installed-tool outputs may contain authorized real customer data when a
workflow requires it. This includes model context and user-selected local files containing names,
contact details, account names, customer relationship management identifiers, correspondence, or
source-system data. Authorization from the organization or source system is sufficient; the tool
does not need to add a second authorization mode or activation gate. Keep that data within the
operator's approved access and retention boundary, and never copy it into Git or public artifacts.

### Personally identifiable information across the repository

Do not commit personally identifiable information (PII) to source code, fixtures, test snapshots,
generated files, logs, telemetry examples, error output, media metadata, filenames, or commit
messages. PII includes direct identifiers and values that can
identify or single out a party when combined:

- Real names, person-specific email addresses, phone numbers, postal addresses, avatars, and
  precise locations
- User names embedded in local filesystem paths
- Customer, tenant, account, subscription, project, support-case, and other party-specific
  identifiers
- Internet Protocol (IP) addresses, device identifiers, session identifiers, and provider subject
  identifiers when they are associated with a person or customer

Keep exact product names, public API paths, schema field names, error codes, and other facts that
describe the system. Preserve legally required license and copyright notices, authoritative
upstream attribution, and normal Git or GitHub contributor provenance. These are narrow provenance
exceptions, not permission to reuse their values as examples or fixtures.

Repository PII sweeps replace stored personal values with synthetic data; they do not remove
collection functions, inspection commands, profile interfaces, authentication behavior, or schema
field names that support authorized private workflows. Source aliases and type declarations describe
the system; literal personal values in source fixtures, comments, generated content, and serialized
records remain subject to the publication boundary.

Minimize personal data that a workflow does not need. Keep authorized private runtime processing,
including provider identity and profile persistence, within the operator's approved access and
retention boundary. Do not copy private values into published logs, telemetry, errors, or evidence.

Use the managed scanner as a first pass; it cannot prove that free-form prose or pixels are clean:

```bash
bash scripts/check-pii.sh --scope staged --mode enforce
bash scripts/check-pii.sh --scope changed --mode audit
bash scripts/check-pii.sh --scope history --mode audit
```

The audit reports review-required media even when it finds no embedded text. Inspect every image,
Portable Document Format (PDF) file, and video visually, check metadata, and use optical character
recognition (OCR) as a second check. Never paste a matched value into an issue, pull request, build
log, or audit ledger; record the category and remediation instead.

## Secrets, credentials, and identifiers

### Placeholder convention

Use angle brackets with uppercase snake_case (`<UPPERCASE_SNAKE_CASE>`) for all code, parameter, URL, and configuration placeholders:

```text
<XC_TENANT>
<XC_API_TOKEN>
<XC_NAMESPACE>
<ORIGIN_POOL_NAME>
<BRANCH>
<SERVER_NAME>
```

This form is searchable, obviously non-functional, and survives a paste into a shell as a visible
syntax error rather than a silent misconfiguration. Do not use `YOUR_TOKEN_HERE`, `xxxxx`,
`changeme`, `foo`, or anything that looks like a real value.

### Never publish a real-shaped credential

Not even a revoked, expired, or rotated one. A reader cannot tell that it is dead, secret
scanners flag it and burn reviewer attention, and "revoked" is discovered to be wrong more often
than anyone expects. This covers API tokens, JSON web tokens, session cookies, certificate
private keys, cluster configuration files, cloud access keys, and webhook signing secrets.

When output genuinely must be shown:

- Truncate and label it: `eyJhbGciOiJSUzI1NiIsInR5… (truncated)`.
- Or replace the value with the placeholder form above.
- For certificate and key material, generate a throwaway self-signed pair specifically for the
  document and say so in a note. Never excerpt from a real chain.

### Tenant, namespace, and account identifiers

Treat these as sensitive even though they are not secrets. They identify a real customer and
often gate support and billing conversations.

| Thing | Use |
| --- | --- |
| Tenant name | `example-corp` |
| Namespace | `demo-app`; genuine reserved namespace names such as `shared` and `system` are fine |
| Account or project identifier | `123456789012` — twelve digits, obviously synthetic |
| Cloud region | Real values are fine; regions are public and identify nobody |

Product names, API paths, configuration field names, error codes, and HTTP status codes are
**not** anonymized. Genericizing those makes a document useless. The line is: anything that
identifies a party gets replaced, anything that describes the system stays exact.

### Screenshots

The highest-risk surface, because the sensitive content is usually outside the region you were
thinking about. Before publishing any screenshot, check:

- [ ] Address bar — session tokens, tenant names, query parameters
- [ ] Adjacent browser tabs — titles leak account names and message subjects
- [ ] Desktop notifications, chat badges, calendar popups
- [ ] Dock, taskbar, menu bar, system tray
- [ ] File paths in terminals and editors — these contain your user name
- [ ] Terminal scrollback above the region of interest
- [ ] The signed-in user chip, avatar, and email in the product's own header
- [ ] Screen-sharing and recording indicators

Redaction must remove pixels. A black rectangle drawn in a layered editor and exported to a
format that preserves layers is not redaction. Flatten, then verify by reopening the exported
file.

## Prose and structure

### Voice and tone

- **Second person, present tense, active voice.** "You create an origin pool," not "an origin
  pool is created" and not "we will create."
- **Imperative for steps with actionable rationale.** "Select **Add Item** to open the
  configuration modal." Lead each step with an imperative verb and explain why or what happens.
  Not "You should now select Add Item."
- **State the outcome before the procedure.** Lead each section with what the reader gets.
- **Eliminate conversational fillers and condescending language.** Avoid "simply", "just",
  "easy", and "obviously". If a step is straightforward, the reader will notice; if it is not, the
  word creates frustration. Adhere to Microsoft Writing Style Guide principles on professional respect.
- **Spaced em-dashes for parenthetical thought or emphasis.** Use ` — ` (an em-dash surrounded by
  spaces) rather than hyphens (`-`, `--`) or unspaced em-dashes to maintain clear readability.
- **Expand every acronym on first use in each document**, including familiar ones. Readers arrive
  from search engines, part-way down the page.

### Structure

- **One level-one heading per document**, matching the title. Sentence case for all headings
  (H1 through H6) without mixed title casing.
- **Numbered lists only for ordered steps.** Bulleted lists for everything else. Bulleted list
  items that are complete sentences must end with a period; fragments do not.
- **Open every how-to and demo guide with Prerequisites** — required access, service tier,
  licenses, tool versions, prior setup — and an estimate of how long the walkthrough takes.
- **Close with Verify and Clean up.** Show how the reader confirms success and what output to
  expect, followed by how to tear the environment down. A demo guide with no teardown section
  leaves billable resources running.
- **One action per step.** If a step contains "and", it is two steps.

### Semantic cohesion and DRY principles

- **Do Not Repeat Yourself (DRY).** Avoid repeating conceptual explanations across multiple
  documents. Reference canonical architecture guides, configuration docs, or specs instead of
  duplicating prose.
- **Consolidate comparative details into conceptual tables.** Use Markdown tables to compare
  options, runtime modes, flags, and matrix dimensions rather than sprawling paragraphs.
- **Use canonical sequence diagrams.** For multi-component or asynchronous workflows, include
  clear ASCII or Mermaid sequence diagrams that map message flow and lifecycle states directly to
  implementation contracts.
- **Anchor claims with concrete implementation file references.** Link directly to repository files,
  APIs, and schemas so the documentation stays verifiable against code.

### Code and commands

- Tag every fence with a language: `bash`, `json`, `yaml`, `hcl`, `text`.
- No `$` or `%` prompt characters — they break a copy and paste.
- Put commands and their output in separate blocks. A combined block cannot be copied.
- Break long commands across lines with `\` continuations, one option per line.
- Prefer a runnable command over a schematic one. Where it cannot be runnable, say so instead of
  leaving the reader to discover it.

### Terminology

- Use the current official product name on first reference, then a defined short form. Verify it
  against F5 product marketing before publishing; names change, and a stale name dates content
  immediately.
- One term per concept per document, never varied for style. "Origin pool" throughout, not
  alternating with "backend pool" and "server group".
- User interface elements in **bold**, matching the product's own capitalization. File paths,
  values, field names, and command options in `code`.
- The `Lint Code Base` gate enforces house terminology through textlint. Reproduce it locally
  before pushing prose, as described in `CONTRIBUTING.md`.

## Pre-publish checklist

- [ ] Heading levels (H1–H6) in sentence case
- [ ] Every public-facing address is in TEST-NET-1/2/3, `2001:db8::/32`, or `3fff::/20`
- [ ] Every private address is RFC 1918 and consistent across the document
- [ ] Every domain is `example.com`, `example.net`, `example.org`, a reserved top-level domain,
      or F5-owned
- [ ] Every ASN and MAC address is in the documentation range
- [ ] No ACME used as a placeholder; legitimate protocol and challenge references remain exact
- [ ] No real person's name, email address, or contact details
- [ ] No PII in fixtures, snapshots, logs, telemetry, errors, filenames, or commit messages
- [ ] No credential, token, key, or certificate material — live, expired, or otherwise
- [ ] Code and parameter placeholders formatted as `<UPPERCASE_SNAKE_CASE>`
- [ ] No real tenant, namespace, or account identifier
- [ ] Screenshots checked against the list above and verified flat
- [ ] Em-dashes formatted with surrounding spaces (` — `)
- [ ] No conversational filler words (`simply`, `just`, `easy`, `obviously`)
- [ ] Prose follows DRY principles with conceptual tables and sequence diagrams where appropriate
- [ ] Managed PII enforcement and audit scans run; every media-review finding inspected
- [ ] Every command can be copied and run; every fence is language-tagged
- [ ] Prerequisites, Verify, and Clean up sections present
- [ ] Product names current
- [ ] Secret scan clean (`gitleaks detect`)

### Detection heuristics

Neither command is authoritative and both need a human pass, but they catch the common misses.

Flag IPv4 literals outside the documentation and private ranges:

```bash
rg -oN --no-heading '\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b' . \
  | grep -Ev '(192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|100\.6[4-9]\.|127\.0\.0\.|0\.0\.0\.0|255\.255\.)'
```

Expect false positives from network masks, version strings, and timestamps.

Flag hostnames in links that are neither reserved nor an approved reference:

```bash
rg -oN --no-heading 'https?://[a-zA-Z0-9.-]+' . \
  | grep -Ev 'example\.(com|net|org)|\.(example|test|invalid|internal|localhost)\b|localhost|f5\.com|github\.com|rfc-editor\.org|ietf\.org|icann\.org|cloudflare\.com|google\.com|microsoft\.com'
```

Extend the allowlist with legitimate reference domains as you go.

## References

Reservations:

- [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737.html) — IPv4 address blocks reserved for documentation
- [RFC 3849](https://www.rfc-editor.org/rfc/rfc3849.html) — IPv6 address prefix reserved for documentation
- [RFC 9637](https://www.rfc-editor.org/rfc/rfc9637.html) — Expanding the IPv6 documentation space (`3fff::/20`)
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606.html) — Reserved top level DNS names
- [RFC 6761](https://www.rfc-editor.org/rfc/rfc6761.html) — Special-use domain names
- [RFC 5398](https://www.rfc-editor.org/rfc/rfc5398.html) — Autonomous system number reservation for documentation use
- [RFC 7042](https://www.rfc-editor.org/rfc/rfc7042.html) — IANA considerations and IETF protocol usage for IEEE 802 parameters
- [ICANN reserves `.internal` for private use](https://www.icann.org/en/announcements/details/icann-seeks-feedback-on-proposed-top-level-domain-string-for-private-use-24-01-2024-en)

Prior art in vendor style guides:

- [Cloudflare Style Guide — example values](https://developers.cloudflare.com/style-guide/formatting/example-values)
- [Google developer documentation style guide — example domains and names](https://developers.google.com/style/examples)
- [Microsoft Writing Style Guide — fictitious names, domains, and addresses](https://learn.microsoft.com/en-us/writing-style-guide-msft-internal/legal-content/fictitious-names-domains-and-addresses)
