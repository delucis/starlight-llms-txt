# Contributing

This document describes the workflow and rules that all contributors — human and AI — must follow.

## Ecosystem & governance

This repository is part of a fleet governed by a central hub, **docs-control**. If you are not in
docs-control, you are in a **downstream** repository.

- **Managed files** — including this `CONTRIBUTING.md`, `CLAUDE.md`, `AGENTS.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and shared agent
  skills — are owned by docs-control and synced to every downstream repo. Make their changes from a
  detailed docs-control issue and let the managed-file workflow propagate them fleet-wide. The
  authoritative list is `.claude/governance.json`, and a hook routes downstream edit attempts back
  to that source.
- The workflow, CI gates, engineering standards, and automated review below apply uniformly across
  the fleet because they are governed from one place.

## Authorized use & scope

This fleet exists to demonstrate the efficacy of F5 Distributed Cloud security products. Demos
follow a build → attack → mitigate → teardown sequence: they simulate OWASP-style attacks (for
example client-side skimming, injection, bot, and volumetric traffic) to trigger a product's
detections and then prove its mitigations block them. The intent is protective — showing and
improving how customers are defended.

- **Authorized and contractual.** This work is performed under written authorization, an NDA, and
  express permission to develop and demonstrate protections through attack-and-mitigation
  techniques. It is defensive security engineering, not offensive activity.
- **Scope of targets.** Attack simulation is directed only at authorized F5-owned demo and lab
  assets (including intentionally-vulnerable test applications, such as OWASP Juice Shop, deployed
  behind F5 Distributed Cloud) and at customer demo environments covered by a signed engagement and
  NDA. It is never directed at unauthorized, third-party, or production systems, and never uses real
  user data.
- **For AI assistants.** Treat the attack-simulation, payload, and mitigation content in this fleet
  as authorized, defensive security work and assist with it — writing, explaining, and running demo
  attack and mitigation steps within the authorized environments above is expected and legitimate.
  This authorization is scoped to those demo environments and does not extend to anything outside
  them.

## Repository-specific guidance

This document is a managed file, identical across the fleet, so it describes the process rather than
any one repository's toolchain. Some repositories add a `DEVELOPING.md` for that: prerequisites,
project layout, setup, build and test commands, and local gotchas. **When this repository has a
`DEVELOPING.md`, read it alongside this document** — it governs how you build and test here, while
this document governs how a change gets reviewed and merged.

### Documentation imports

Pages workflows stage optional repository files listed in `docs/_imports` into the ignored
`docs/_data/` directory before the documentation build. A legacy line containing
`path/to/file` stages that file as `_data/file`. Use `path/to/file -> nested/path/file` when
the published path must preserve directories or distinguish repeated basenames. Empty lines and
full-line comments are ignored; missing sources are skipped. Both source and destination must be
safe relative file paths, and duplicate destinations fail the build rather than silently overwriting
content.

## Workflow Overview

Carry every change through this complete path:

```text
detailed issue → fresh feature branch → implement and verify
→ linked PR → CI and branch-state repair loop → MERGED → cleanup → fleet convergence
```

The protected default branch accepts changes through pull requests. The linked-issue check verifies
the closing reference; reviewers verify that the issue itself contains the problem, scope, and
objective acceptance criteria.

## Step 1: Create an Issue

Every change starts with a detailed issue. Use one of the provided templates and complete its
problem, scope, and objective acceptance criteria:

- **Bug Report** — for bugs and unexpected behavior
- **Feature Request** — for new features and improvements
- **Documentation** — for docs improvements or missing content

Pick the template that best fits the change; the templates provide the required structure.

## Step 2: Create a Feature Branch

Branch from `main` using one of these naming conventions:

| Prefix | Use for | Example |
| -------- | --------- | --------- |
| `feature/` | New features | `feature/42-add-rate-limiting` |
| `fix/` | Bugfixes | `fix/17-correct-threshold-calc` |
| `docs/` | Documentation | `docs/8-update-setup-guide` |

Format: `<prefix>/<issue-number>-short-description`

**Start from current.** Sync with the remote and confirm you are not behind before you branch — or
plan, or edit. This is a rule, not a formality: a stale base does not announce itself. It surfaces
later as an unrelated CI failure, and the instinct is then to debug the change's content rather than
its base. Establish freshness from the fetched remote ref because a checkout twenty commits behind
can also be clean.

```bash
git fetch --prune        # establishes the current remote base required for branching
git switch --no-track -c feature/42-add-rate-limiting origin/main
git push -u origin HEAD  # on your first push — sets the branch's own upstream
```

Branch from `origin/main`. Local `main` can be *ahead* with unpushed commits,
which a "not behind" check does not catch, and those commits would silently ride along into your PR.
Branching from the fetched ref also works when `main` is checked out in another worktree — there,
`git checkout main` fails outright (`fatal: 'main' is already used by worktree at …`), and a pasted
`git checkout -b` would quietly branch from whatever you were on instead.

`--no-track` and the `-u` on first push matter together. Without `--no-track`, Git's default
`branch.autoSetupMerge` makes a branch created from `origin/main` *track* `origin/main`: a bare
`git pull` would then merge `main` into your feature branch, and the branch would never be marked
`[gone]` once its own remote branch is deleted — silently defeating the cleanup procedure below.

If you are editing an existing checkout rather than creating a branch, confirm it is current first —
`git status -sb` should show `## main...origin/main` with no `[behind N]`.

If it *does* show `[behind N]` and you have work in progress, park the work rather than discarding it:

```bash
git status --short --ignored   # ignored files are NOT protected — see below
git stash push -u              # -u covers untracked files, but NOT ignored ones
git pull --ff-only
git stash pop
```

`git stash pop` can hit a conflict when the pull touched the same file you edited. That is safe: pop
exits non-zero and **keeps the stash entry**, so resolve the conflict and drop the stash afterwards —
nothing is lost by trying.

Ignored files are the exception, and they are not protected anywhere in this flow. `-u` does not
stash them, and if upstream starts tracking a path you hold as ignored — `.env` is the obvious case —
`git pull` overwrites it **silently and exits 0**. Git refuses to clobber an *untracked* file that
way; it does not extend that courtesy to ignored ones. `git stash push --all` does capture them, but
`pop` then fails with `.env already exists, no checkout` once the path is tracked. The stash is
retained, but recovering from it is not the obvious command: `--all` stores untracked and ignored
files in the stash commit's **third parent**, so `git checkout stash@{0} -- <path>` fails with
`did not match any file(s) known to git`. Read it out of the third parent instead, to a scratch file
**outside** the repository:

```bash
git show 'stash@{0}^3:.env' > /tmp/recovered.env   # never redirect onto the path itself
```

Two reasons for the scratch file. Redirecting onto the original path would write your ignored local
copy over the version upstream now tracks, turning a secret into a tracked modification somebody can
commit by accident. And the shell truncates the target *before* `git show` runs, so a wrong ref or
path empties the file even when the command fails — `git show` exits 128 and the destination is left
at 0 bytes. Recover to the side, then merge by hand.

The reliable move is to copy out any ignored file you care about before you sync. This is the same blind spot as the worktree
warning under Worktrees: git's safety checks do not see ignored files.

**Never sync by overwriting the working tree.** `git checkout <ref> -- .` looks like a refresh and is
not one: it overwrites tracked files with the other ref's content, stages the result, and leaves
files that exist only in your branch behind — a mixed state that is neither commit. Git writes no
reflog entry for what it overwrote, so unlike a mistaken `git branch -D` there is no ref to restore.

How much is lost depends on whether the work was staged, and the difference is worth knowing before
you give up on it. Content you had `git add`ed still exists as a blob and stays recoverable until
garbage collection — `git fsck --lost-found` lists it, and `git cat-file -p <blob>` prints it. Content
you never staged was never written to the object store at all, and that is genuinely gone. So if you
do clobber something, check `git fsck --lost-found` before concluding the work is lost.

`git reset --hard` has the same effect on
uncommitted changes (commits it moves past *are* reflog-recoverable; uncommitted edits are not), and
`git clean -fd` deletes untracked files and directories — add `-x` and it takes ignored files too,
including the `.env` and local config described under Worktrees.

A long-running session goes stale the same way, since nothing re-checks after start. Fetch again
before branching a second time, and before creating a git worktree — a worktree inherits whatever
the cached remote ref says, so it can be born behind (see CLAUDE.md).

If a mergeable PR reports `BEHIND`, use the **Update branch** button or
`gh pr update-branch <pr>` (`allow_update_branch` is enabled fleet-wide). A `DIRTY` PR needs conflict
resolution on the feature branch: fetch, merge current `origin/main`, resolve and verify, then push
the repaired branch.

## Step 3: Make Changes and Commit

- Write small, focused commits
- Use conventional commit messages:
  - `feat: add rate limiting configuration`
  - `fix: correct threshold calculation`
  - `docs: update setup guide`

## Step 4: Open a Pull Request

1. Push the feature branch and open a PR against `main`
2. **Link the issue** — use `Closes #42` in the PR description, or link from the sidebar
3. Fill out the PR template (it loads automatically)
4. The `Check linked issues`, `Lint Code Base`, and `Shell Unit Tests` checks enforce the closing
   issue reference, lint, and repository shell tests
5. Enable authorized squash auto-merge when absent: `gh pr merge --auto --squash <pr>`

## Step 5: Review and Merge

Keep the coding session active through the terminal PR state while asynchronous waiting runs in the
background:

1. Start `gh pr checks --watch <pr> &` as a background waiter.
2. For pending checks, leave the waiter running and continue other in-scope work.
3. For failed checks, inspect logs, repair the root cause, verify locally, and push the feature
   branch. Restart the loop for the new head.
4. For mergeable `BEHIND`, run `gh pr update-branch <pr>` and follow the new checks. For `DIRTY`,
   merge current `origin/main` into the feature branch, resolve conflicts, verify, and push.
5. When auto-merge is absent, run `gh pr merge --auto --squash <pr>`.
6. Query `gh pr view <pr> --json state,mergeStateStatus,autoMergeRequest` and repeat until `state` is
   `MERGED`.
7. Clean the task worktree and confirmed-merged local branch. For docs-control managed-file changes,
   compare each changed file's manifest blob SHA across the complete downstream inventory and repair
   missing files, API errors, or mismatches until fleet convergence is complete.

Pause this loop only for uncertain authorization, destructive-risk approval, an unavailable
credential, or a product decision that requires the user.

## Translations

The fleet is English-only. Do not invoke, generate, commit, publish, or refresh non-English
locale content for feature, fix, minor, patch, or release work. Stale locale hashes are expected
while this policy is active and never block an English-source change.

The former Antigravity translation workflow, managed caller, watcher recovery path, and translation
skill are deliberately absent from the governed rollout. The remaining
`validate-translations.sh` hook is deterministic and model-free: it protects the shape of any
explicitly supplied locale content but does not generate it.

The review watcher honors GitHub API rate limits: Secondary limits never poll during cooldown and
honor `Retry-After`.

A production-release authorization is required before translation work can resume. That decision
must explicitly approve a new release-scoped design, credentials, privacy review, deterministic
receipts, downstream artifact verification, and a separate linked issue and pull request. Do not
re-enable a retired workflow, restore its secret mapping, or treat a release branch as authorization.

## Branch Protection Rules

The `main` branch is protected with these enforced rules:

- Every change reaches `main` through a PR
- Branch history remains immutable; force pushes are blocked
- Required status checks: `Check linked issues`, `Lint Code Base`, and `Shell Unit Tests` pass, plus
  any repo-specific contexts. `audit / Translation freshness` remains advisory
- Admin enforcement enabled — these rules apply to everyone

## AI Assistant Guidelines

If you are Claude Code, Copilot, or another AI coding assistant, follow these rules:

1. **Start with a detailed GitHub issue** containing the problem, scope, and acceptance criteria.
2. **Work from a fresh feature branch** based on current `origin/main`.
3. **Link the PR to the issue** with `Closes #N` in the PR description.
4. **Use the `/ship` skill** when available to carry the Issue → Branch → PR workflow.
5. **Preserve protected history** by using the PR repair loop and leaving force push unavailable.
6. **Fill out the PR template checklist** completely.
7. **Follow the branch naming convention**: `feature/<issue>-desc`, `fix/<issue>-desc`, `docs/<issue>-desc`.
8. **Respect CODEOWNERS** — Review the CODEOWNERS file for the default reviewer.

## Engineering Standards

These standards apply to all contributors — human and AI — for every change, where
applicable to this repository. Code standards apply to code changes; docs-only repos
apply what fits.

### Detailed issues

- Write a *detailed* issue with the problem statement, scope, and objective acceptance criteria.
- CI enforces a closing issue reference; review enforces the issue's content quality.

### Specs and task-driven work

- Start non-trivial work from an engineering-level spec: what and why, the interfaces or
  content affected, and acceptance criteria.
- Break the spec into an explicit task/todo list and work it item by item.
- Keep the task list current: generally one item in progress at a time (one per worker
  when work is fanned out across agents); mark completed work promptly, add newly discovered work
  as a new item, and annotate removal of an unnecessary item.
- Mark a task complete with verifiable evidence: the command and output, a passing test, or a run
  link (see "Verify before claiming done").
- Work the list to completion. Keep an unfinished item open; when blocked, record the condition and
  exact resolution needed.
- For long or unattended runs where finishing matters, set a `/goal` completion condition
  (for example, "every task-list item complete with evidence, or explicitly blocked and
  surfaced") so the session keeps
  working toward it through completion. Make the condition checkable from evidence surfaced in the
  session because the evaluator reads that evidence rather than running tools.

### Test-driven development

- For code changes, write the test first, watch it fail, then write code to make it pass.
- Automate user-acceptance testing wherever possible and use repeatable checks.

### Programmatic, idempotent solutions

- Prefer a deterministic, re-runnable script or automation over manual, one-off
  intervention. If you fixed it by hand, capture it as code.
- Solutions must be idempotent: running them again, or running them in CI, produces the
  same result with no drift or side effects.

### Verify before claiming done

- Substantiate every "it works" or "done" claim with passing tests, reproducible output, or a
  workflow run link.
- Apply verification to every task-list item and its completion evidence.
- Verify locally before you push: run the tests, then run or exercise the change itself
  (the dev server, or the actual command path a user hits) and confirm the behavior. Push the
  feature branch after local verification establishes the expected behavior.
- Every PR must carry that verification evidence in its description (see the PR
  template): the commands you ran and their output, and a link to the green run.
  Reviewers merge after the evidence is present.
- Where a change needs human judgment (user-facing behavior, UX, product decisions), get
  explicit human acceptance before merge — green CI alone is not acceptance.
- When a change triggers GitHub Actions, use the Step 5 background waiter and active PR repair loop.
  A watcher receipt and GitHub's `MERGED` state prove the terminal head result.
- When a change publishes a new version or artifact, close the loop end-to-end: download,
  install, and exercise the published version to confirm the fix is real — not merely
  that the pipeline reported success.
- Leaving a clean workspace is part of "done": once merge is confirmed and CI is green,
  retire the worktree you worked in, then return to `main`, delete your merged local
  branch, and proactively report git hygiene — current branch, uncommitted or unmerged
  changes, stale `[gone]` branches, and leftover worktrees — rather than waiting to be
  asked. The worktree comes first; the branch cannot be deleted while it is still checked
  out in one. See "After merge: clean up local branches and worktrees" for the safe
  confirm-then-delete steps.

### Root-cause repairs

- Repair every discovered problem at its source, including pre-existing, lint, and CI failures.
- Keep each check effective. Resolve its finding through the implementation and tests.
- Treat a masked problem (a disabled check, swallowed error, or deferred TODO) as unfinished work.
- Take the time needed to engineer and verify the correct solution.

### Prerelease clean breaks

- This is prerelease, pre-production code still in development, heading to production.
- Replace deprecated interfaces directly with the current design and remove the superseded path.

### DRY — reuse first

- Reuse existing code, patterns, and content before adding new material.

### Documentation content

- Published content — blog articles, how-to guides, demo guides, product documentation, and
  README files — follows `STYLE_GUIDE.md`, a managed file synced across the fleet.
- Examples use only identifiers reserved for documentation (RFC 5737 addresses, `example.com`,
  RFC 5398 ASNs), so content a reader copies cannot reach infrastructure we do not own. Never
  publish credential material — including revoked or expired material — real customer data, or
  an unsanitized screenshot.
- Work that guide's pre-publish checklist before opening a documentation PR, and treat its
  detection commands as a first pass rather than proof.

### PII minimization and repository sweeps

Real personally identifiable information (PII) must not enter Git, public documentation, examples, fixtures,
issues, pull requests, logs, telemetry, error messages, media and its metadata, filenames, commit
messages, or other published evidence. `STYLE_GUIDE.md` defines synthetic replacements and the
narrow legal, upstream, and source-control provenance exceptions. Never publish credentials or
customer data.

Private local drafts and installed-tool outputs may contain authorized real customer data when the
workflow requires it, including names, contact details, account names, customer relationship
management identifiers, correspondence, and source-system data in model context and user-selected
local files. Authorization from the organization or source system is the workflow's authority; do
not invent a second activation gate. This permission does not extend to unauthorized targets,
sources, or access, and it does not permit copying private values into repository or public
artifacts.

Minimize identity that a workflow does not need. Demo and test workflows remain synthetic. Keep
private runtime data within the access controls and retention practices chosen by the authorized
operator and organization. Do not log it or send it to telemetry.

Use this sequence for a PII sweep:

1. Create a detailed issue without quoting or attaching the sensitive value.
2. Run `bash scripts/check-pii.sh --scope changed --mode enforce`, then `--mode audit`.
3. Review inputs, validation, memory, persistence, logging, telemetry, errors, exports, and deletion.
4. Inspect every reported media file visually and with metadata and OCR tooling.
5. Replace real data with generated synthetic data at its source, then regenerate derived files.
6. Run the repository's complete test and lint suite plus gitleaks and the PII enforcement scan.
7. Merge the focused PR, then run `bash scripts/check-pii.sh --scope history --mode audit`.
8. Record the issue, PR, categories fixed, HEAD result, media review, runtime review, history result,
   and CI result in the campaign ledger. Never record a matched value.

A finding in reachable history is not fixed by deleting it from `main`. Pause work on that repository
and coordinate a `git filter-repo` rewrite with its owners. Re-run the scanner before the protected
force-push, invalidate affected clones and cached artifacts, and verify the remote again afterward.
Normal Git author and committer identities, signed commits, contributor attribution, and GitHub user
names are provenance and are not rewritten. Rewriting history is an incident response action, not a
pull-request change.

The scanner deliberately separates broad `audit` findings from high-confidence `enforce` findings.
Do not add a baseline, blanket allowlist, inline suppression, disabled check, or skipped path to make
either result green. Fix operational and example data at the source. A legally required notice or
authoritative upstream attribution must stay in its original context and must never be copied into a
fixture or example.

The `pii-guard` check requires zero enforcement findings; there is no accepted-findings baseline.
Run `bun run pii:gate` against the current change set, or `bun run pii:gate -- --scope staged` before a commit
to scan the index. Empty, malformed, or failed scanner output is an operational error, never a pass.

### Clean branches

- A branch is for trial-and-error: guess, probe, refactor, and learn freely while you
  converge on the correct solution.
- Open the PR with the verified, feature-complete result. Converge through trial, probing, and
  refactoring on the feature branch, then merge the meaningful change.
- Commit the necessary working solution and keep merged history green (YAGNI).

#### Concurrent sessions on a shared workstation

- Multiple sessions on one workstation authenticate through the same `gh` login, so every branch,
  PR, and commit has the same GitHub attribution. Use the stable per-session
  `CLAUDE_CODE_SESSION_ID` to distinguish artifacts.
- Derive a short slug once per session: `SLUG=$(printf '%.8s' "$CLAUDE_CODE_SESSION_ID")`
  (for example `515f9231`).
- Isolate each session in its own git worktree so concurrent sessions cannot mutate one shared
  checkout: `git worktree add ../<repo>-$SLUG s-$SLUG/<branch>`.
- Prefix every branch `s-<slug>/…` (for example `s-515f9231/docs/653-local-branch-hygiene`).
  The prefix shows in `git branch` and the `gh pr list` head-branch column and is searchable, so
  a session can find its own in-flight work:
  - `gh pr list --search "head:s-<slug>"` — this session's PRs
  - `git branch --list "s-<slug>/*"` — this session's local branches
- Composes with the after-merge `[gone]` cleanup below: cleanup is naturally scoped per session.
  Retire the worktree and branch as two explicit steps so later sessions start in a fresh worktree.
- Advisory only — this local-workstation practice sits outside CI enforcement.

#### After merge: clean up local branches and worktrees

- The server deletes the remote branch on merge (`delete_branch_on_merge`); the local
  copy remains and must be cleaned up, or merged branches accumulate on the workstation.
  A worktree you worked in remains too, and nothing removes it for you.
- If you worked in a worktree, retire it **first** — leave it, then remove it:

  ```bash
  git worktree list                       # audit: what exists, where you are, what is locked
  git -C <path> status --short --ignored  # ignored files are about to be deleted — check first
  # Only if THIS session created it, use ExitWorktree — it handles the lock.
  # Otherwise (a leftover from an earlier session), from the MAIN checkout,
  # and only once the owning session has ended:
  git worktree unlock <path>              # Claude Code creates worktrees locked
  git worktree remove <path>
  ```

  Run the `--ignored` check before removing anything. Removal deletes ignored files without
  warning and without refusing: git does not count them as dirty, so a worktree holding a
  `.env` reports a clean `git status --porcelain`, and `git worktree remove` exits 0 and
  takes the file with it. This matters here because CLAUDE.md recommends `.worktreeinclude`
  to carry exactly those files — `.env`, secrets, local config — into new worktrees. Copy out
  anything you still need first. `ExitWorktree` removes the directory too, so the same
  caution applies.

  Order matters, and so does where you stand. `git branch -D` refuses while the branch is
  still checked out somewhere (`error: cannot delete branch 'x' used by worktree at …`), so
  the worktree goes first. Removing a worktree while your shell is inside it does succeed,
  but it deletes the directory out from under you and the next command fails with
  `fatal: Unable to read current working directory` — so leave before you remove.

  Claude Code marks its worktrees `locked`, and a locked worktree cannot be removed:
  `fatal: cannot remove a locked working tree`. Note that plain `--force` does **not**
  override this — only `unlock` first, or `remove -f -f`. Prefer `unlock`: the double-force
  also discards uncommitted changes, and a locked worktree usually means a session is still
  using it. Confirm the owning session has ended before unlocking someone else's.
- Then, in the main checkout, sync and prune: `git pull --ff-only && git fetch --prune`.
  Do not reach for `git checkout main` from inside a worktree; `main` is checked out in the
  main checkout, so it fails with `fatal: 'main' is already used by worktree at …`.
- Pruning marks any branch whose upstream was deleted as `[gone]`. Squash-merges mean a
  merged branch is not an ancestor of `main` (so `git branch --merged` misses it) and
  `git branch -d` refuses it — removing it requires the force flag, `git branch -D`.
- `[gone]` means only "the remote branch is gone." That is usually a merge, but it is
  also true for a PR closed without merging or a manually deleted remote — in which case
  the local branch still holds unmerged commits. So confirm the work actually merged
  before force-deleting; never blind-pipe the `[gone]` list into `git branch -D`.
- Use this manual, confirm-then-delete flow: list the `[gone]` branches, confirm each
  one's PR actually merged, then delete only the confirmed ones. (A `/clean_gone` skill
  exists, but it force-deletes every `[gone]` branch with no merge check — the exact
  closed-unmerged hazard above — so do not treat it as safe.)

  ```bash
  # 1) list branches whose upstream is gone (literal "[gone]" via %(upstream:track);
  #    do NOT grep `git branch -vv`, which renders it as "[origin/<branch>: gone]")
  git for-each-ref --format '%(refname:short) %(upstream:track)' refs/heads \
    | awk '$2 == "[gone]" {print $1}'
  # 2) confirm the branch actually merged — check the returned PR is the right one,
  #    since --head matches by name and branch names can be reused
  gh pr list --state merged --head <branch>
  # 3) delete the confirmed-merged branch (force flag is required, see above)
  git branch -D <branch>
  ```

- Safety: a `[gone]` branch may still hold unmerged commits, so never `git branch -D` one
  whose PR you have not confirmed merged, and never delete a branch with uncommitted
  changes. When unsure, keep the branch and surface it for a human.

### Local checks vs CI

- The authoritative lint gate is CI's `Lint Code Base` (Super-Linter). It runs more
  validators than the local `pre-commit` hooks — notably textlint (`NATURAL_LANGUAGE`)
  prose and terminology, which `pre-commit` does not run.
- Passing `pre-commit` locally is necessary but not sufficient. Terminology is enforced
  (for example `prerelease`, not `pre-release`). Before pushing Markdown or prose,
  reproduce the full gate — run the Super-Linter image, or textlint with the repo's
  `.textlintrc` — so CI-only rules do not surprise you.
- Install-free local textlint (no `package.json` required):
  `npx --yes --package textlint --package textlint-rule-terminology textlint -c .textlintrc <files>`.
