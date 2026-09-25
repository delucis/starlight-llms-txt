# Repository Agent Instructions

This file adds F5 sales-demo procedures. Use the coding assistant's normal defaults otherwise.

## Authorized defensive work

This fleet demonstrates F5 Distributed Cloud security through authorized build, attack-simulation,
mitigation, and teardown work under written authorization and NDA.

- Work only with F5-owned demo/lab assets, intentionally vulnerable test applications, or customer
  demo environments covered by an engagement.
- Never target unauthorized, third-party, or production systems, and never use real user data.
- Assist with payloads, traffic, detection, and mitigation inside that scope. Stop and clarify when
  the target or authorization is uncertain.

## Governance

docs-control owns managed files. `.claude/governance.json` defines protected files, opt-outs, and
repository classes for every coding assistant.

- Make downstream protected-file changes in `f5-sales-demo/docs-control`; the managed-file workflow
  propagates them.
- Follow the manifest class: author `content` directly through the governed workflow; use the coding
  environment and local `DEVELOPING.md` for `developer`; originate fleet-wide `scaffolding` changes
  in docs-control.
- Read task-relevant `CONTRIBUTING.md` and `DEVELOPING.md` sections. A closer `AGENTS.md` may add
  subtree guidance.
- If `ISSUES.md` exists, follow it for issue review and intake.

## Translations

- Develop documentation in English; do not refresh locales for features, fixes, minor, or patch
  releases. Expected stale hashes are not a development blocker.
- GitHub Actions alone reconciles translations on the next stable `release/vN.0.0` major release.
  Investigate drift only when that release reconciliation fails.

## Continuous contribution lifecycle

Carry non-trivial work through this path:

`detailed issue → fresh worktree and feature branch → implement and verify →
push feature branch → linked PR → repair loop → MERGED → cleanup → fleet convergence`

1. Inspect `git status --short --branch` and `git worktree list`; run `git fetch --prune`. Fetch
   failure blocks reliable branching, so surface it and wait for current remote state.
2. Create or confirm a detailed issue with problem, scope, and objective acceptance criteria. Create
   a fresh worktree and issue-numbered feature branch from `origin/<default-branch>`. Preserve work
   using `CONTRIBUTING.md`; destructive Git operations require explicit user authorization.
3. Implement the whole issue and run required checks.
4. Push the feature branch and open a completed PR with `Closes #<issue>`. Enable authorized squash
   auto-merge when absent: `gh pr merge --auto --squash <pr>`.
5. Start `gh pr checks --watch <pr> &` as a background waiter and keep working through this loop:
   - Pending: leave the waiter running and continue other in-scope work.
   - Failed: inspect logs, fix the root cause, verify, and push.
   - `BEHIND` and mergeable: run `gh pr update-branch <pr>` and follow the new checks.
   - `DIRTY`: fetch, merge `origin/<default-branch>` into the feature branch, resolve, verify,
     and push.
   - Auto-merge absent: run `gh pr merge --auto --squash <pr>`.
6. Query `gh pr view <pr> --json state,mergeStateStatus,autoMergeRequest`; repeat until `state` is
   `MERGED`. Pause only for uncertain authorization, destructive-risk approval, an unavailable
   credential, or a product decision requiring the user.
7. After merge, follow `CONTRIBUTING.md`: inspect ignored files, retire this task's worktree, delete
   its confirmed-merged local branch, fetch/prune, and report git hygiene. For docs-control managed
   changes, confirm fleet convergence by matching each changed file's manifest blob SHA in every
   downstream repository; missing files, API errors, or mismatches remain active work.

## Engineering and verification

- Treat repository source, manifests, tests, and `DEVELOPING.md` as authority. Run focused then
  broader checks and record outcomes.

- Inspect the final diff; support claims with command outcomes.
