# Spec: 8.x crew reliability fixes

**Status: open (M65, [#2095](https://github.com/mw-ding/mdstack/issues/2095)).**
This spec is the opening slice S0 ([#2093](https://github.com/mw-ding/mdstack/issues/2093)).
It records each member's settled fix, its numbered acceptance criteria and the
order between members that touch the same code. Member statuses live in
[portable spec, M65](portable.md#m65-8x-crew-reliability). Plan-ok:
[#985 c7225981037](https://github.com/mw-ding/mdstack/issues/985#issuecomment-7225981037).

M65 fixes defects the crew hit while running 8.1.0: dispatch that drops or
repeats work, a watcher that dies or wakes on the wrong signal, validation
that refuses its own instructions, builder evidence the review gate rejects,
and an engine failure that leaves a run idle. Every member card said "for
triage"; the fixes below are decided here from each card and its latest
triage record. The fixes ship as 8.3.0 after S1. Target environment: N/A;
these are not platform items. Owner prerequisites: none.

This spec adds no permission, merge-gate rule, marker field, label or
validation-eligibility change. A member that finds it needs one stops and
gets its own approval. Where a fix tightens dispatch, it only skips, defers
or de-duplicates work; it never lets a pass or a land through that is
refused today.

## 1. Members

Standard flavor, tier default. Sizes are changed lines excluding tests, a
planning range, not a limit. Each member's issue may add ACs; the ACs below
are its minimum. Every member keeps the repository rules: one PR, a
`changes/` fragment marking a fix for the next release, `check-repo.py`,
`check-changelog-pr.py` and the tests named for each changed script
([AGENTS.md](../../AGENTS.md)). A member that changes a template also runs
the render and parity tests.

| ID | Issue | Fix and named paths | Size | Depends on |
|---|---|---|---|---|
| A1 | #2032 | Route turns a ready item's `issue-assigned` into a builder `build` handoff. `route.py` | 30–60 | #2093 |
| A2 | #2036 | Retained `pr-merged` record forwards each dependent once; drain takes the route lock. `route.py`, `drain.py` | 40–80 | #2032 |
| W1 | #2050 | Watcher loop survives a transient spawn failure. `watch.py` | 30–60 | #2093 |
| W2 | #2072 | Delivery probe reads a busy pane with queued steers as busy; one idle wake per message and run. `send.py`, `watch.py`, Claude Code adapter | 40–90 | #2050 |
| W3 | #2081 | Owner-answer count skips crew-signed posts from a shared login. `poll.py` | 20–50 | #2093 |
| V1 | #2075 | Validator instructions and lead scheduling follow the existing skip actor and eligibility rules. Reviewer policy templates, `lead.py` | 40–80 | #2093 |
| V2 | #2076 | Kill without `--discard` retains a finished validate section. `_shared.py`, `kill.py` | 30–60 | #2075 |
| E1 | #2044 | Build pass requires the guard negative-control pair before `done:`. `templates/policy/builder/build-pass.md`, `cli-evidence.md` | 20–50 | #2093 |
| E2 | #2061 | Builder brief names the `PROOF` presence forms. `build-pass.md`, `fix-rounds.md` | 20–50 | #2044 |
| N1 | #2089 | Provider policy block fails and reports the run; a transport error takes the run's one restart. Codex adapter, `watch.py`, `restart.py` | 60–120 | #2093 |
| S1 | #2094 | Status and tracker sync, acceptance ledger, M65 close | 60–120 | Every admitted member landed |

### Order between members

- **A1 → A2 (route, drain, scheduler).** Both edit the builder-lead handoff
  in `route_record()`. A1 is smaller and lands first; A2 merges up.
- **W1 → W2 (watcher poll loop, delivery probe).** Both edit `watch.py`'s
  scan loop. W1 wraps the loop body and lands first; W2's delivery wake
  change merges up onto it. W3 edits only `poll.py`, which the loop calls as
  a source command, so it has no fixed order with W1 or W2.
- **V1 → V2 (validation scheduling, actor, reclaim).** V1 changes when the
  reviewer lead starts a validate pass; V2 changes what a reclaim of that
  pass keeps. V1 lands first so V2's test uses V1's dispatch rule.
- **E1 → E2 (builder evidence formats).** Both edit `build-pass.md` and
  regenerate the same render fixtures. E1 lands first; E2 merges up and
  regenerates the fixtures.
- **N1** shares no function with another member. Where it meets W1 in
  `watch.py` (a different branch of the scan), the member landing second
  merges up.
- The member landing second merges up with the declared update strategy and
  its builder resolves any conflict; a published branch is never rebased or
  force-pushed.

### Member ACs

- **A1 (#2032).** Fix: when an `issue-assigned` record names an item
  labelled `crew:ready`, route sends the builder lead the same `build`
  handoff it sends a ready dependent, not a `work` notice the scheduler
  cannot rank. (1) A test replays an `issue-assigned` record for a
  `crew:ready` item; the builder lead inbox gets a `build` message and
  `schedule decide` ranks it as a build. (2) An item without `crew:ready`
  gets no `build` handoff (negative control). (3) Solo mode is unchanged.
- **A2 (#2036).** Fix: the retained `pr-merged` record carries the
  dependents already handed off, and a later route pass hands off only
  dependents not in that set; `mdstack drain` takes `route.lock` before it
  renames the queue, so it never runs between route's rename and its
  write-back. (1) A test routes the same retained record three times; each
  ready dependent gets exactly one `build` handoff. (2) A dependent that
  becomes ready on a later pass is handed off then. (3) A test holds
  `route.lock` and shows drain waits, then returns the written-back record.
- **W1 (#2050).** Fix: the persistent loop catches `BlockingIOError` and
  `OSError` with `EAGAIN` or `ENOMEM` from a spawn, logs one line, sleeps a
  bounded back-off and continues; its pid file stays. Any other exception
  still ends the watcher as today. (1) A test makes the source spawn raise
  `EAGAIN` once; the watcher keeps its pid file and routes on the next scan.
  (2) A non-transient exception still exits (negative control).
- **W2 (#2072).** Fix: the cause is unconfirmed, so the member first
  captures the busy pane (spinner line with steers queued in the composer)
  as an adapter fixture. `worker()` classifies that fixture busy, and the
  watcher emits at most one `delivery … worker idle` wake per message and
  run. (1) The captured fixture classifies busy. (2) A real idle composer
  still classifies idle (negative control). (3) A test with a worker idle
  across ten scans emits one delivery wake.
- **W3 (#2081).** Fix: a comment or review counts as an owner answer only
  when its login is in `owners` and it carries no crew signature line or
  `crew:v1` marker. A genuine owner answer from a shared login, unsigned,
  still counts. (1) With owners `["mw-ding", "md-mt"]`, a signed role post by
  `md-mt` changes no count. (2) An unsigned `md-mt` comment and an
  `mw-ding` comment each count. (3) The existing distinct-login test passes.
- **V1 (#2075).** Fix: align producers with the rules `verdict.py` enforces;
  no eligibility or actor rule changes. The reviewer brief says the review
  actor alone records an eligible skip, that behaviour-mode eligibility needs
  every changed path to be Markdown under `docs/` (so a `changes/` fragment
  makes it ineligible), and that a dispatched validate pass always runs
  bounded validation. The reviewer lead does not start a validate pass
  after a review that recorded a skip. (1) The rendered reviewer brief
  carries the three statements. (2) A docs-plus-fragment PR's dispatched
  validate pass posts a real validation that `verdict.py` accepts. (3) A
  test shows no validate dispatch after a recorded skip.
- **V2 (#2076).** Fix: `mdstack kill` without `--discard` moves a finished
  validate section and its round `-verdict` file under `retained/reviewer/`
  with a run suffix before removal, so a same-named respawn cannot reuse the
  path. `--discard` still deletes. (1) A kill-then-respawn test keeps the
  first pass's section byte-identical under `retained/`. (2) `--discard`
  removes it (negative control). (3) Review-file retention is unchanged.
- **E1 (#2044).** Fix: extend the existing
  [inline guard-control lesson](../lessons/2026-11-15-inline-guard-controls.md)
  from fix notes to the initial build. The build pass adds a step before
  `done:`: a new or changed guard pastes its fail-then-pass pair, run through
  the shipped entry point with exit codes unmasked (protocol §3). No new
  evidence rule or gate. (1) The rendered builder brief carries the step.
  (2) Render fixtures are updated and parity passes.
- **E2 (#2061).** Fix: the build pass and fix-round text name the three
  forms the route `PROOF` check accepts (a fenced block, an attachment URL,
  or `N/A — because …`) and say inline backticks alone fail it. The check is
  unchanged. (1) The rendered builder brief carries the forms. (2) Render
  fixtures are updated and parity passes.
- **N1 (#2089).** Decision: a provider policy block (HTTP 403, content
  policy or "temporarily blocked") fails the run and reports it. The Codex
  adapter declares the line in `FATAL`, so the watcher escalates on the next
  scan with the provider's line, and the run neither restarts nor moves to
  another engine. Retrying the next engine after a policy block would
  reframe a provider safety refusal, which the
  [triage autonomy rule](../triage.md#autonomy) forbids; that is **owner
  decision OD1**, not settled here. A transport error ("stream disconnected",
  "connection reset") is not a refusal: an idle run whose last error line is
  one takes the run's existing one restart on the same engine, and a second
  failure escalates. (1) A fixture with the 403 line escalates on one scan,
  with no restart and no engine change. (2) A transport fixture restarts
  once, then escalates. (3) An idle screen with neither line keeps today's
  stale path (negative control).

## 2. Closing slice

S1 records each member's PR and status in the portable-spec M65 table, runs
every member AC's named test at the final SHA and lists command, result and
SHA in an acceptance ledger on #2094. A check that cannot run is recorded as
not run, with the reason. A member that is not landed is `dropped` with a
recorded reason, never silently deferred.

## 3. Not in M65

OD1 (engine fallback after a policy block), any validation-eligibility or
actor-rule change, cap or scheduler setting changes, and the `mdstack kill`
worktree refusal on the crew's own `.crew-resolved-config.tmp` that #2089
also reports (a follow-up card).
