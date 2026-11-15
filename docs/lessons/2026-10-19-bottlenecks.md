---
title: Bottleneck analysis of 22 pilot PRs: headline timings, five ranked losses, other lessons
date: 2026-10-19
status: mixed
source: Bottleneck analysis of 22 pull requests from the agentconnect pilot, plus the pilot evidence log for agentconnect issue 579 / PR 585 and the pilot wiring notes
---

# Bottleneck analysis, 2026-10-19

Entry format: see [README.md](README.md).

- **Date:** 2026-10-19 (two follow-on lessons dated 2026-10-20 are noted below)
- **Source / evidence:** Bottleneck analysis of 22 pull requests from the
  agentconnect pilot (worked example, per spec R3), plus the pilot evidence log
  for agentconnect issue 579 / PR 585 and the pilot wiring notes.
- **Linked issue/PR:** none yet for any open fix (see each entry).

## Headline timings

After the cutover to the full pipeline, the happy path was fast:

| Step | Time |
|---|---|
| CI green to reviewer-validator verdict | 4–29 min |
| Approval to merge | under 3 min |
| Small fixes | 3–8 min |
| Pilot PR 585: assignment to merge | 54 min 48 s, 2 verdict rounds, 0 manual nudges |

The losses below are therefore not in the steady-state loop. They are stalls,
waits and rework around it.

## Ranked losses

Ranked by cost on the critical path.

### 1. Dropped handoffs

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** Changes were requested around 12:30 AM on Oct 18 and nothing
  happened until 11 PM. Nothing detected stale state.
- **Impact:** about 22.6 h on the critical path.
- **Fix:** an hourly stuck-PR sweeper.
- **Status:** applied. `templates/runtimes/grok-bot/coordinator-stuck-pr-sweeper.md` and
  `docs/protocol.md` §6 (#16).
- **Linked issue/PR:** none yet (no mirror issue in this repo; the sweeper is
  documented in
  [the sweeper template](../../templates/runtimes/grok-bot/coordinator-stuck-pr-sweeper.md), added
  by #16).

### 2. Builder workers frozen mid-run

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** Background builder workers showed multi-hour gaps with no
  activity. A 30 s sleep took 180 min, and only about 1.6 h of a 9 h run on one
  PR was real work. It was not quota. The inferred cause is that background
  workers stall when no bot turn is active.
- **Impact:** about 12.7 h.
- **Fix:** workers write a heartbeat to their claim file; a 15-minute watchdog
  restarts or escalates a silent worker; keep the dispatching turn alive, or
  split work into short workers.
- **Status:** applied. Protocol §6 defines the builder claim-file
  heartbeat (5 min cadence, 15 min silence) and the sweeper's `builder-silent`
  row messages the builder to restart (#72). Whether the box skill copy matches
  is a drift-check question, not part of this status. Keeping the dispatching
  turn alive and short workers are not covered.
- **Linked issue/PR:** #65 (PR #72).

### 3. Serial holds and sibling-merge conflicts

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** Holds were placed on textual dependencies, not semantic ones.
  Stacked branches, shared hot files and squash merges produced sibling-merge
  conflicts.
- **Impact:** about 11 h.
- **Fix:** land shared code first as its own PR; do not stack lanes; hold only
  on semantic dependencies; issue immediate merge-up-only briefs; auto-lift
  `Depends-on` holds.
- **Status:** open. `main` only notes lane/dependency holds in a coordinator
  comment (`docs/protocol.md` §6) and has no shared-code-first or no-stacking
  rule. Partial mitigation: `templates/runtimes/grok-bot/coordinator-after-merge.md:44` has a
  "Lane resume" rule that lifts `crew:hold` on the next step's PRs when a lane
  PR merges; there is no auto-lift for `Depends-on` holds.
- **Linked issue/PR:** none yet.

### 4. Waiting on decisions from the user

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs; pilot wiring notes
  (a hold issue waiting on a choice between three options).
- **Finding:** One pilot issue waited about 18 h for a decision and was
  resolved 4 min after the decision was made.
- **Impact:** about 18 h on that issue.
- **Fix:** a `crew:needs-md` label, a recommended default and a deadline on
  every decision request, batched daily. The process is written up in
  [CONTRIBUTING.md](../../CONTRIBUTING.md).
- **Status:** applied. `crew:needs-md`, recommended default and auto-apply time
  in `docs/protocol.md` §6; daily digest in `CONTRIBUTING.md`.
- **Linked issue/PR:** none yet.

### 5. Review round churn

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** About 2 change-request rounds per PR.
- **Impact:** about 2 change-request rounds per PR; no time figure given.
- **Fix:** the builder runs the reviewer checklist and the validation commands
  before pushing.
- **Status:** open. No rule in `docs/roles.md` or `docs/protocol.md` makes the
  builder run the reviewer checklist before pushing (the worker brief only says
  to run the relevant tests).
- **Linked issue/PR:** none yet.

## Other lessons

### Unique worktree per worker run

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** A shared worktree was deleted while a worker was still using it.
- **Impact:** a lost worker run; no figure given.
- **Fix:** one worktree per worker run, named
  `<worktree-root>/<pr>-<sha7>-<role>-<pass>/`.
- **Status:** applied. `docs/roles.md` Worker isolation and `docs/protocol.md` §6.
- **Linked issue/PR:** none yet.

### Do not delete a workflow that others call

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** Deleting the release workflow would have removed push CI on the
  default branch, because the test workflow was only called by the release
  workflow.
- **Impact:** averted; it would have removed push CI.
- **Fix:** disable the release workflow through `workflow_dispatch` instead of
  deleting it, and add a push trigger for the default branch to the test
  workflow. The pilot notes record the test workflow running on push to the
  default branch afterwards.
- **Status:** applied (pilot repo only, per the pilot notes; not checkable from
  this repo).
- **Linked issue/PR:** none yet.

### Reviewer engine must differ from builder engine

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis; pilot PR 585 held the rule
  (builder and reviewer used different engines).
- **Finding:** A reviewer on the same engine as the builder is a weaker check.
- **Impact:** review quality; no figure given.
- **Fix:** keep the reviewer engine different from the builder engine.
- **Status:** applied. `docs/roles.md` Hard rules and Reviewer engine selection;
  held in the pilot.
- **Linked issue/PR:** none yet.

### Route work by quota

- **Date:** 2026-10-19
- **Source / evidence:** Bottleneck analysis, 22 pilot PRs.
- **Finding:** Engine choice should follow remaining quota, for example prefer
  one engine while the other's weekly quota is low.
- **Impact:** avoids quota stalls; no figure given.
- **Fix:** route by quota.
- **Status:** applied. `docs/roles.md` Quota routing (check before each launch,
  skip an engine under its threshold, relaunch the next on a mid-task limit).
- **Linked issue/PR:** none yet.

### Evidence that lives off the PR head can stall the review loop

- **Date:** 2026-10-20
- **Source / evidence:** A diagram PR in this repo, where before/after crops were
  kept on a side branch.
- **Finding:** When a crop-only fix landed, the PR head did not move. The
  reviewer-validator's watch never woke and a manual re-review steer was needed.
- **Impact:** a manual steer; no time figure given.
- **Fix:** proposed: commit evidence a verdict depends on to the PR branch (for
  example under `evidence/`, pruned at squash), or post a re-review steer
  automatically when the evidence changes.
- **Status:** superseded by the adopted rule in
  [2026-10-20-evidence-on-pr-head.md](2026-10-20-evidence-on-pr-head.md)
  (`docs/protocol.md` §3). The `evidence/` folder idea was not adopted.
- **Linked issue/PR:** #19, #23; the rule is recorded in
  [2026-10-20-evidence-on-pr-head.md](2026-10-20-evidence-on-pr-head.md).

### Git credential helper pointed at the wrong binary

- **Date:** 2026-10-20
- **Source / evidence:** Box setup issue noticed the same day.
- **Finding:** The global git credential helper pointed at a path where `gh` is
  not installed.
- **Impact:** pushes by workers could not authenticate; no figure given.
- **Fix:** the helper path was corrected on the box.
- **Status:** applied (box configuration, per the source; no repo change to
  verify).
- **Linked issue/PR:** none.

## Gaps from the pilot evidence

Findings from the pilot of agentconnect issue 579 / PR 585, with status as the
pilot notes record it.

### Pre-push hook environment

- **Date:** 2026-10-18
- **Source / evidence:** Pilot PR 585, first push failed.
- **Finding:** The pre-push hook needs a newer Node and a writable
  `COREPACK_HOME`; the default box Node failed. The builder recovered on its own.
- **Impact:** one failed push, recovered without a nudge.
- **Fix:** builder and fix workers set `PATH` to the newer Node and
  `COREPACK_HOME` to a writable directory before pushing.
- **Status:** applied. `docs/roles.md` Toolchain pinning and `docs/protocol.md` §6
  Worker toolchain.
- **Linked issue/PR:** none yet.

### Default branch has push CI

- **Date:** 2026-10-19
- **Source / evidence:** Pilot PR 585: a test run started on the merge commit.
- **Finding:** The wiring assumed tests ran on PRs only, so the coordinator's
  merge listener missed failures on the default branch.
- **Impact:** a push-CI failure would go unseen.
- **Fix:** the coordinator also listens for CI failure on the default branch.
- **Status:** applied. `templates/runtimes/grok-bot/coordinator-after-merge.md` (second listener);
  the pilot notes record the live routine updated on 2026-10-19.
- **Linked issue/PR:** none yet.

### Label hygiene

- **Date:** 2026-10-18
- **Source / evidence:** Pilot PR 585.
- **Finding:** The reviewer-validator left `crew:in-review` in place when it set
  `crew:approved`, and the issue kept `crew:ready` after close.
- **Impact:** stale labels; the coordinator cleared them at close-out.
- **Fix:** the reviewer-validator swaps labels on verdict; the coordinator
  removes `crew:ready` at merge. See the label table in
  [architecture.md](../architecture.md#labels).
- **Status:** applied. `docs/protocol.md` §6 (verdict pass removes
  `crew:in-review`); [architecture.md](../architecture.md#labels) label table
  (coordinator removes `crew:ready` at close-out).
- **Linked issue/PR:** none yet.

### Per-PR watches need a parent turn

- **Date:** 2026-10-18
- **Source / evidence:** Pilot PR 585.
- **Finding:** Routine runs cannot create routines, so creating per-PR watches
  costs one extra parent turn per bot per PR.
- **Impact:** one extra turn per bot per PR.
- **Fix:** none; known limit, handled by the prompts handing off.
- **Status:** open (accepted limit). `docs/runtimes/grok-bot.md` (moved from
  `docs/protocol.md` §6 in #114) still hands B2 creation to the builder's
  parent turn; lighter-lane PRs skip B2.
- **Linked issue/PR:** none.

### Every bot review wakes the coordinator

- **Date:** 2026-10-18
- **Source / evidence:** Pilot PR 585 had 5 bot reviews.
- **Finding:** Each bot review body fires the coordinator's PR-comment listener
  for a cheap no-op.
- **Impact:** up to 5 extra coordinator wakes on that PR.
- **Fix:** none yet; accepted, revisit if volume is high.
- **Status:** open (accepted for now). The event mapping (a COMMENT review
  fires `pr-comment`) is in `docs/backends/github.md`, Reviews, markers and
  identities (#115).
- **Linked issue/PR:** none yet.

### Other open risks recorded in the pilot notes

Not entries yet; each needs verification before it becomes one:

- Listener semantics are unverified (one CI-passed event per head or per
  workflow; cancelled runs; assignee filtering; concurrent wakes of one bot).
- PR body edits rerun the title check and wake the reviewer-validator; evidence
  updates belong in fix notes instead.
- Bots must use review bodies, never plain PR comments, to keep steering cheap.
- Bots share identities with the user's logins, so safety rests on bots never
  writing steering commands and workers never posting to GitHub directly.
- Draft-to-ready PRs trigger no CI and no wake; builders open non-draft PRs.
- Conflicts stall CI silently; the synthesizer's post-merge sweep is the only
  automatic recovery.
- Outside contributors' PRs need sandboxed validation and a manual approve to
  run workflows.
- Enforce-for-admins blocks the user's own direct merges and pushes unless they
  go through the same gate.
- Project board access needs a token with project scope.
