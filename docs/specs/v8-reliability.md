# Spec: 8.x reliability fixes

**Status: built (M63, [#2029](https://github.com/mw-ding/mdstack/issues/2029));
every member landed, and the closing slice S1
([#2027](https://github.com/mw-ding/mdstack/issues/2027)) ran the acceptance ledger.**
Outcome, ledger summary and lessons:
[portable spec, M63 outcome](portable.md#m63-outcome-and-lessons).
This spec was the opening slice S0 ([#2025](https://github.com/mw-ding/mdstack/issues/2025)).
It records each member's settled fix, its numbered acceptance criteria and the
order between members that touch the same code. Member statuses live in
[portable spec, M63](portable.md#m63-8x-reliability-fixes). Plan-ok:
[#985 c7074684349](https://github.com/mw-ding/mdstack/issues/985#issuecomment-7074684349).

M63 fixes defects found while running and adopting the 8.x line: the
7.x → 8.x upgrade, second install roots, cross-team ownership, review and
land dispatch, a flaky test, and session and backend parity. The fixes ship
in the next release after S1. Target environment: N/A; these are not
platform items. Owner prerequisites: none.

This spec adds no permission, merge-gate rule, marker field or label. A
member that finds it needs one stops and gets its own approval. Where a fix
below tightens dispatch, it only skips or defers work; it never lets a pass
or a land through that is refused today.

## 1. Members

Standard flavor, tier default. Sizes are changed lines excluding tests, a
planning range, not a limit. Each member's issue may add ACs; the ACs below
are its minimum. Every member keeps the repository rules: one PR, a
`changes/` fragment marking a fix for the next release, `check-repo.py`,
`check-changelog-pr.py` and the tests named for each changed script
([AGENTS.md](../../AGENTS.md)).

| ID | Issue | Fix and named paths | Size | Depends on |
|---|---|---|---|---|
| R1 | #2024 | 7.x bootstrap re-exec of `upgrade --project`; bootstrap human step; migration guide. `_shared.py`, `bootstrap.py`, `docs/guides/migration.md` | 40–80 | #2025 |
| R2 | #2023 | Launcher pins its install root. `install.py`, `upgrade.py` | 40–80 | #2024 |
| R3 | #1961 | Primary host root defaults to the resolved `paths.root`. `host.py` | 20–40 | #2023 |
| R4 | #1979 | Owner-directed team change goes through the handoff record; route skips PRs with no run record here. `route.py`, `docs/handoff.md`, coordinator policy | 60–120 | #1970 |
| R5 | #2015 | Merge-up delta review reaches the reviewer lead; coordinator `rereview` steer. `route.py`, `lead.py` | 60–120 | #2025 |
| R6 | #2011 | Deterministic land-lock reap test. `dev/tests/environments/test-crew-land-lock.py` | 20–60 | #2025 |
| R7 | #1970 | Readiness resolves a release cut's item from its non-closing linkage. `route.py` | 30–60 | #2025 |
| R8 | #1941 | Research artifacts go under the excluded `.crew/`. Researcher policy | 20–50 | #2025 |
| R9 | #1950 | Suite admission admits the item a counted builder waits on. `schedule.py`, `lead.py` | 40–80 | #2025 |
| R10 | #1957 | Session `up`: window-scoped variables, `launch.cwd`, `start`/`--attach`, conditional `GH_TOKEN`. `up.py`, `sessions/tmux/adapter.py`, `_shared.py` | 100–160 | #2025 |
| R11 | #1958 | Backend-aware builder brief. `templates/policy/builder/build-pass.md`, `crew-render.py` | 60–120 | #2025 |
| S1 | #2027 | Status and tracker sync, acceptance ledger, M63 close | 60–120 | Every admitted member landed |

### Order between members

- **R1 → R2 → R3 (bootstrap, launcher, install root).** R1 lands first: it
  repairs the upgrade path that carries R2's launcher rewrite to existing
  hosts. R2 then pins the root in the launcher and in `upgrade`. R3 merges
  up onto R2 and reads the same resolved root (`CREW_ROOT` set by the
  launcher, else `paths.root`, else `user_root()`).
- **R7 → R4 (route readiness).** Both edit the readiness `want` table in
  `route.py`. R7 is the smaller change and lands first; R4 merges up.
- **No fixed order:** R1 and R10 (different functions in `_shared.py`), R5
  and R9 (different functions in `lead.py`), R5 and R4/R7 (merge-up routing
  versus readiness in `route.py`). The member landing second merges up with
  the declared update strategy and its builder resolves any conflict; a
  published branch is never rebased or force-pushed.

### Member ACs

- **R1 (#2024).** (1) With `CREW_BOOTSTRAP_BUNDLE_SHA256` set, `main()`
  accepts `--project` for `upgrade` only; every other owner-shell refusal of
  `--project` stays. (2) A test re-execs the CLI as 7.16.0 `fetch` does
  (owner-shell env, `upgrade --project <file>`, the variable set) and exits
  0 in dry-run; without the variable it is still refused with exit 2.
  (3) Bootstrap's human step prints `mdstack up` when the file is the
  installed config, else `MDSTACK_CONFIG=<file> mdstack up`; never
  `--project`. (4) The migration guide's 7.x → 8.0.0 section says the plain
  command works from the fixed release on, and that a direct upgrade to
  8.1.0 needs `MDSTACK_INTERNAL=1`. (5) The PR adds the lesson and findings
  entry the card asks for.
- **R2 (#2023).** Fix: a launcher for a non-default root runs
  `CREW_ROOT=<root> exec <root>/releases/current/cli/mdstack "$@"`; the
  `~/.mdstack` launcher text stays byte-identical. (1) A non-default-root
  launcher, run with no `--project` and no `CREW_*`/`MDSTACK_CONFIG`,
  resolves `<root>/config.toml`. (2) `CREW_PROJECT` and `MDSTACK_CONFIG`
  still win, as `default_config()` orders them. (3) The default launcher's
  text and behaviour are unchanged (byte test). (4) `install` and `upgrade`
  both rewrite a stale launcher in their root; `--dry-run` lists it.
- **R3 (#1961).** (1) A primary with no `root` resolves to the profile's
  resolved `paths.root`, or `user_root()` when that is unset, for both
  prepare and the checkout-receipt read. (2) An explicit `root` is
  unchanged. (3) A test with `paths.root` outside `~/.mdstack` reaches
  `ready` without setting `root`.
- **R4 (#1979).** Fix: a team change is a handoff, not a prose decision.
  (1) The coordinator policy and `docs/handoff.md` say an owner decision
  that moves a repo to another team is carried out with the existing
  `takeover` handoff on the repo's control item; the decision comment alone
  moves nothing. (2) With such a record, the losing runtime's
  `mdstack ownership --action write` exits nonzero (test on a fake control
  item). (3) Both crews may post as one login under the same persona names,
  so a signature cannot tell them apart. Route readiness therefore also
  needs a run record in this crew's state (a builder claim or `done:` line)
  that names the PR; a builder that adopts an open PR (protocol §6 step 1)
  writes one. A PR with none is skipped with reason `foreign team`. This crew's own PRs are unaffected
  (positive and negative tests). No marker field, label or merge-gate rule
  changes.
- **R5 (#2015).** Fix: route the delta-review handoff to the reviewer lead
  whenever `route.py` detects a delta from the signed merge-up note.
  (1) A test replays the #2000 shape (resolved conflict, differing patch)
  and asserts a reviewer-lead event that starts a review worker, not a
  synthesizer-only event or an empty-pool `done`. (2) A coordinator steer
  kind `rereview` starts a review of the current head through the same lead
  path; it supplies no verdict, no merge-ok and no gate input. (3) A
  merge-up with no delta still needs no delta review (negative control).
- **R6 (#2011).** Fix: the test waits on the reap condition with a bounded
  deadline instead of acquiring once right after the window goes. If the
  investigation shows the race is in `land-lock.py` itself, the product fix
  is in scope with its own test. (1) The two existing checks stay: a present
  window with an unreadable pane never reaps; a missing window reaps while
  the pane process survives. (2) 50 consecutive runs under
  `scripts/run-tests.py -j 4` load pass, recorded in the PR.
- **R7 (#1970).** Fix: when a PR has no closing reference and its body
  passes the release-cut linkage (`Release issue: #N` plus `Refs #N`, as
  `check-pr-linkage.py` validates it), readiness takes `{N}` as the item.
  (1) A cut PR with that linkage and a matching builder record is ready.
  (2) Builder identity, head, epoch and proof checks are unchanged. (3) A
  non-cut PR with no closing reference is still refused (negative control).
- **R8 (#1941).** Fix: the researcher policy writes any artifact that is
  not its deliverable (a visual summary, a draft) under the worktree's
  `.crew/`, which spawn already excludes, and moves a tool's stray output
  there before `done:`. The unlanded-work guard is unchanged. (1) The
  rendered researcher brief carries the rule. (2) A close-out test with a
  file under `.crew/` removes the worktree; one with another untracked file
  still refuses (negative control).
- **R9 (#1950).** Fix: the scheduler may start a deferred item past
  `max_suites` only when a counted builder's recorded un-woken wait names
  that item. No cap value changes. (1) A test with `max_suites = 2`, two
  slot holders and one waiting on the deferred item starts it. (2) Without
  such a wait the deferral stands (negative control). (3) The decision log
  line names the wait that admitted it.
- **R10 (#1957).** (1) `CREW_*` reach only the coordinator's window
  command, not `tmux new-session -e`; a new window in the crew session has
  none. (2) `launch.cwd` sets the coordinator's working directory and
  defaults to the profile directory. (3) `start` and `up --attach` attach a
  session-runtime crew. (4) The launch line exports `GH_TOKEN` only when a
  GitHub backend is bound; tmux GitHub renders are unchanged.
- **R11 (#1958).** Fix: the linkage-check sentence renders only for a
  GitHub change backend; the post-open fragment step only for a GitHub
  change backend or a profile that declares `[release]` (settled at S1: the
  shipped GitHub profiles declare no `[release]`, so a `[release]`-only
  condition would break AC (2)); a new `builder.local_checks` string replaces the
  local-check list, and when unset a GitHub render keeps today's text while
  another backend renders "the project's own checks from its `AGENTS.md`".
  (1) A non-GitHub render without `[release]` omits all three. (2) Existing
  GitHub render fixtures are byte-identical (render and parity tests).

## 2. Closing slice

S1 records each member's PR and status in the portable-spec M63 table, runs
every member AC's named test at the final SHA and lists command, result and
SHA in an acceptance ledger on #2027. A check that cannot run is recorded as
not run, with the reason. A member that is not landed is `dropped` with a
recorded reason, never silently deferred.

## 3. Not in M63

Changing which callers count as internal beyond R1, a new ownership
mechanism beyond the existing handoff record, cap or scheduler setting
changes, a declared `change.check-linkage` binding, and the owner's
clean-profile dry run (#2013, M25.2).
