# Changelog

All notable changes to this repo are recorded here, in the style of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Every PR adds an entry
(spec R5: date, PR number, summary) and says whether the box skill copy was mirrored (spec R4). See
[CONTRIBUTING.md](CONTRIBUTING.md).

## [Unreleased]

## [7.13.0] - 2026-11-14

### Added

- Release 7.13.0: M55, runtime routing repairs, then #1774's owner-confirmed grant pruning, then M56, one team with several project contexts and pools. M55: a held review parks under a typed `waiting:` id instead of re-nudging the reviewer lead (#1836), a coordinator merge-ok recorded after CI is green wakes the synthesizer lead (#1835), and an item's execution tier from its signed flavor record reaches every builder and reviewer spawn (#1830), with the M55 spec slice (#1847), learning card (#1813) and status sync (#1848). #1774: owner-confirmed `mdstack grant prune` and interactive `mdstack down` archive finished finite grant clauses, with dry-run previews and `down --keep-grant`. M56: team files gain closed per-repo project keys and a durable `context` envelope on wake records and inbox messages (#1856); a team's repos share one scheduler with repo-scoped reservations (#1857) and run one lead per pool (#1858); landing, trains, merge locks and stack intents are bound to the selected repo (#1859); with the M56 team spec (#1861) and closing status sync (#1860). **Breaking:** a team file listing one repo in two sections, or setting `merge_grant` or `merge_grant_scope` under `[team.runtime.options]`, now fails to resolve (#1856); the owner chose a minor for it. Migration: keep one section per repo and move a landing grant into each `[repos.<name>]` it covers. The cut also includes M54's brief and acknowledgement helpers (#237), review and recheck helpers (#238) and checked merge-up command (#239), `mdstack down` scratch cleanup (#369), the M53 and M54 status syncs (#1815, #1820) and the findings-buffer count updates (#1862, #1873, #1887). Upgrade: from 7.12.0, `mdstack upgrade --latest --yes` applies as before; only a team file that lists one repo twice or sets a team-level `merge_grant` needs the #1856 migration, and one-repo configs need no edit. The owner upgrades the live install after publication, which ends the coordinator's #1830, #1835 and #1836 workarounds. (issue #1872, PR #1893, 2026-11-14) Box skill copy: none.
- Landing is bound to the repo `--project` selects (team §9.5). `mdstack train` records the selected project's `context` in its train and delegation records and, before any clone, branch, record, push, CI dispatch, merge or cleanup, reads first, then writes: every record and delegation an action names and the predecessor train each builds on, every member qualifier (`<owner>/<name>#<n>`) and the full lookup of every change the action can write for (build and delegate members; for land, wait, bisect, route and close every member and a pending merge record's change, and every read route decides a dropped member's merge-up on: its full view, hold dependencies and solo labels), which land, route and build then act on; `train land` also reads train CI, the default branch and the member's gate (change, landing control issue, hold dependencies) before the pending merge record or any other write. One foreign or unreadable read refuses the whole action with nothing written (an unresolvable hold, control issue, CI or gate view no longer closes the train or records a pause), so another repo's verdict, merge-ok or train result at the same number and SHA never counts and never closes the train; `train check` reports such a read as a blocked gate. Async land and stack intents record the `context`, `land request|resume|done`, `land stack|stack-done` and resume refuse an intent naming another repo before any read, request or drop, and `land stack --stack` takes `<owner>/<name>#<n>:<sha>` members, refusing the whole stack when one names another repo. `land-lock` records the repo's `context` and the acquiring window in `locks/merge.pid` and refuses a record naming another repo before any cleanup, signal or removal; each repo keeps its own lock. The tmux synthesizer lead brief gains a team-land paragraph. In a one-repo config a record written before this change, without `context`, stays the selected repo's; gate satisfaction, actors, fail-open paths and markers are unchanged. (issue #1859, PR #1877, 2026-11-14) Box skill copy: none.
- A team runs one lead per pool: `mdstack up --team` records each repo in `<team-root>/team.json` and ensures one `(team, pool)` lead per enabled pool through the first repo whose render, pause and ownership allow it (a repeat run starts none), with its record, inbox, status and brief at the team root. Every repo's route hands it messages carrying that repo's `context` envelope; a repo's watcher sees, parks and retries only its own messages, and the lead's `$CREW_PROJECT` is the team file, so a command without the message's project refuses for a multi-repo team. The three lead briefs gain a team-pool paragraph. Team runs take a team-global run ID and window slot under one team-root lock; their window names carry a one-to-one repo tag (`ben-42-<owner>__<repo>`, other characters outside `[a-z0-9-]` escaped as `_<hex>`), their worktrees are `<worktree-root>/<owner>__<repo>/<run-id>/`, their run records add `run_id`, `context`, `project`, `checkout` and `handoff` (`mdstack spawn --handoff`, kept through the spawn queue), and every restart takes a new run ID and keeps the handoff; a restart in its own worktree refuses when another process holds the run's pane. In a team, `mdstack kill` stops a window only at the run's recorded slot, pane and live process (pid and start time), removes a worktree only under its own repo's tag and releases only its own repo's allocation. One-repo names, paths, records and outputs are unchanged. (issue #1858, PR #1876, 2026-11-13) Box skill copy: none.
- A team file's repos now share one crew scheduler. `mdstack schedule` keeps one lock, target and reservation ledger under the team root's `schedule/`, so two repos' leads deciding at once never over-admit the last slot. It counts every repo's workers once against the team's pool caps, floors, target and ramp limit. Each repo's demand is filtered by that repo's ownership, pause, holds and `crew:escalated` label, read through its `repo.labels`. An unreadable repo, its tracker included, blocks only its own demand, recorded as `blocked`. A PR pass whose requested head is missing or unreadable, no longer matches its open PR's live head, or cannot be checked because the live heads are unreadable, and a build whose `Depends on` issue is still open in its own repo are not admitted and are listed under `waiting` with the reason. Unreadable caps, workers or ledger refuse every team decision. Each repo's demand is ranked by its own tracker: milestone order, which honours `repo.milestones`, plus `Depends on` and `main-red`. Ties break by canonical repo and work identity. A later milestone's build waits, deferred as `class-7`, while any repo's earliest-milestone build has not started. An acknowledged wait that is still parked is not demand. A decision grants only the caller's `(repo, pool)` lane. A team reservation records its repo, project and reviewer pass kind and round, so the same `#n` in two repos, or one PR's passes and rounds, stay separate grants. The reviewer lead starts a pass only on a grant of that pass and round. It transfers only to that repo's run, and `mdstack spawn` and `mdstack schedule release` drop only the caller repo's grant. Decisions, held items, releases, the decision log, the summary line and the watcher's `schedule-stuck` alarm name the repo. These team outputs are additive. One-repo configs keep their outputs. One change applies to every config: an unreadable `reservations.json` now defers each decision as `reservations-unreadable` and is left as it is, where before it was read as empty and overwritten. (issue #1857, PR #1875, 2026-11-13) Box skill copy: none.
- `mdstack spawn` now carries an item's execution tier to every launch: the coordinator's signed `pass=flavor` record takes an optional `tier=trivial|default|deep`, and a builder or reviewer spawn without `--tier` takes the newest such allocation (a later flavor-only record keeps it) before the role default. A review, validation or recheck reads the PR's linked issues and refuses conflicting tiers; a malformed tier or unreadable item refuses before any claim, queue entry or window. Route and train fix and review dispatch no longer force the default tier, and the queue and run records keep the resolved tier through dequeue, restart and quota relaunch. (issue #1830, PR #1868, 2026-11-13) Box skill copy: none.
- Team files gain five closed per-repo project keys, `control_item`, `labels`, `milestones`, `doc_home` and `flavor` (a table with only `name` that may only tighten the strictest flavor of any lower layer, refusing a looser knob or cap with the key and the source of the floor). `labels` renames state tags on the tracker, read and written through by `mdstack poll` and `mdstack route`. A project's identity is its resolved team and canonical repo, a one-repo `config.toml` deriving the team `repo:<owner>/<name>`; aliases, symlinks and an omitted selector give one identity. `mdstack poll` and `mdstack send` stamp a closed `context` work envelope (team, project, repo, item, change, head, pass, round, `null` when absent) on wake records and inbox messages, `mdstack send --context` refuses a foreign one, and `mdstack route` refuses a malformed or foreign envelope, or one lacking or differing from any id its record, completion line or run names, an item or change read from another repo (read before any lead handoff), a completion line whose ids disagree with its run (or, in a team file, that has no run), or an envelope-less team-file record not bound to a run in that repo, before any spawn, post or handoff. Markers, status lines and one-repo resolution are unchanged. **Breaking:** a team file listing one repo in two sections, or setting `merge_grant` or `merge_grant_scope` under `[team.runtime.options]`, now fails to resolve. Migration: keep one section per repo and move a landing grant into each `[repos.<name>]` it covers. (issue #1856, PR #1866, 2026-11-13) Box skill copy: none.
- Specify M56's team/project delivery in the team spec: S0, T1–T4 and S1 rows with dependencies and M55 integration prerequisites, applied choices D1–D5, the five closed project-key shapes, the durable envelope, the team/repo state split and the zero-mutation refusal cases, replacing the stale "T1–T4 remain unadmitted" status. (issue #1861, PR #1863, 2026-11-13) Box skill copy: none.
- Record the M55 learning card for the personnel template placeholder link: one repaired near-miss, the whole-link composition prevention, retained producer and release coverage, and why it is applied rather than encoded. (issue #1813, PR #1852, 2026-11-13) Box skill copy: none.
- Specify M55's runtime routing repairs: slice rows, applied choices D1–D4, member acceptance criteria, tier allocation, version and sensitivity forecast, and the affected test matrix before member builds. (issue #1847, PR #1849, 2026-11-13) Box skill copy: none.
- Add review and recheck commands over the existing fresh reviewer passes, and a checked head/round-bound COMMENT verdict poster with section, actor, skip and reset refusals. Compact tmux pointers use the helpers; live render deployment stays with the coordinator. (issue #238, PR #1838, 2026-11-13) Box skill copy: none.
- Add an owned, checked mechanical merge-up command that refuses busy or dirty copies, restores the original head on unresolved conflicts, and posts a signed note at the published head while leaving approval carry and differing-content review to the existing pipeline. (issue #239, PR #1837, 2026-11-13) Box skill copy: none.
- Add issue briefs over rendered role instructions and checked intake, clean merge-up and owner steering acknowledgements, preserving existing run-block output and inbox delivery without granting approval power. Regression checks reject stale rendered run instructions and reversed merge parents. (issue #237, PR #1834, 2026-11-13) Box skill copy: none.
- Owner-confirmed `mdstack grant prune` and interactive `mdstack down` archive finished finite grant clauses before a grant-only profile edit, preserving standing permission, restrictions, unknown scope and existing shutdown safeguards. Milestone identifiers resolve within descriptive titles, and cut versions with or without `v` resolve to the published `vX.Y.Z` tag. Dry-run previews and `down --keep-grant` provide inspection and opt-out; role, noninteractive and preserve shutdowns skip pruning. (issue #1774, PR #1833, 2026-11-13) Box skill copy: none.

### Changed

- Findings buffer: the M56-close triage sweep's accepted count updates are recorded. "Consumer reads part of a gate or action contract and treats the gap as permission" goes from 14 to 18 (#1866, #1875, #1876, #1877), "Test or check bypasses the path production uses" from 11 to 12 (#1877), "Terminal record lost or mismatched by a downstream consumer" from 7 to 8 (#1876) and "Optional pack input assumed present, or a floor checked per layer" from 2 to 3 (#1866, linking #1273, now closed), each with its source links. (issue #1887, PR #1888, 2026-11-14) Box skill copy: none.
- Record M56 completion (PR #1880) in the team spec: S0, T1–T4 and S1 marked built with their PRs and passing verdicts, the applied scope decisions (T3 before T2, T4's `errors.jsonl` boundary), lessons and follow-ups, and closed member issues. Team routing, admission, leads and landing headers now say built for the terminal runtime, with isolated proof only and no release or live adoption claim; the spec stays partly built. (issue #1860, PR #1880, 2026-11-14) Box skill copy: none.
- Findings buffer: the M55-close triage sweep's accepted count updates are recorded. "Consumer reads part of a gate or action contract and treats the gap as permission" goes from 13 to 14 (#1868 empty-present tier) and "Test or check bypasses the path production uses" from 9 to 11 (#1865, #1868 campaign stub), each with its source links. (issue #1873, PR #1874, 2026-11-14) Box skill copy: none.
- Record M55 completion: landed PR and review/validation references, settled decisions and lessons, closed member issues, and that none of the three runtime repairs is released or installed yet; update README Status and the flavors design header without implying live adoption. (issue #1848, PR #1869, 2026-11-13) Box skill copy: none.
- Findings buffer: the M53-close triage sweep's accepted count bumps are recorded. "Test or check bypasses the path production uses" goes from 7 to 9 (#1825, #1833) and "Moved or quoted prose loses its consumer contract" from 9 to 10 (#1851 MD038), each with its source links. (issue #1862, PR #1864, 2026-11-13) Box skill copy: none.
- Record M53 completion: landed PR, owner-proof and validation references, settled decisions and lessons, closed member issues and L1 source cards, and which members shipped in v7.12.0; update README Status without implying live adoption. (issue #1815, PR #1851, 2026-11-13) Box skill copy: none.
- Record M54 helper completion, landed PR and validation references, settled decisions and integrated brief reserves; update README and runtime/release status without implying release or live adoption. (issue #1820, PR #1840, 2026-11-13) Box skill copy: none.

### Fixed

- A coordinator merge-ok recorded after CI is already green now wakes the synthesizer lead. `mdstack poll` keeps an authenticated permission identity per open crew PR (this runtime's coordinator `pass=steer cmd=merge-ok` record at the current full head SHA, scoped by repository, PR, head and command) and emits one new `merge-ok-recorded` event to the synthesizer when it appears, whatever CI shows. Duplicate copies, unchanged polls, prose, other authors or runtimes, other heads or PRs and malformed markers emit nothing, and a poll state written before this change seeds the identity quietly. `mdstack route` forwards the event to the synthesizer lead as durable `work` while the merge-ok is still at the live head; a superseded head, a closed PR or a merge-ok no longer at head consumes it, and a held PR stays queued for the coordinator. The event only prompts a fresh gate check: it is never approval, hold clearance or a CI waiver. The #1832 release cut sat idle about 25 minutes waiting for this wake. (issue #1835, PR #1867, 2026-11-13) Box skill copy: none.
- A held review no longer re-nudges the reviewer lead in a loop. `mdstack reviewer-pool` now writes the typed `waiting: #<n> owner|hold id=<id>` line itself, after its ack, for a review, validate, recheck or `work` request whose PR is live `crew:escalated` or `crew:hold`, and keeps the id pending. The lead backstop's wait fingerprint now uses only the polled PR's state, head and CI, plus its hold, owner answers and ask. Mergeability and verdict churn no longer wake a parked id, and poll catching up on a hold the dispatcher already saw becomes the new baseline. The #1833 incident's five re-nudges in about 15 minutes came from those wakes, not from the repeated acks; a hold release, CI or head change, owner answer or ask still wakes the id once. (issue #1836, PR #1865, 2026-11-13) Box skill copy: none.
- Plain mdstack down removes regular coordinator scratch files after a successful stop,
  including when no session remains, while preserving them during maintenance
  stops and refusals and retaining symlinks. Remove an unused import from the coordinator guard. (issue #369, PR #1831, 2026-11-13) Box skill copy: none.

## [7.12.0] - 2026-11-13

### Added

- Release 7.12.0: M51, personnel delivery and team/project design, then M52, completion routing. M51 exports pinned personnel content with explicit host bindings and integrity checks (#1180), and specifies team/project composition, shared admission and repo-qualified routing without shipping shared pools (#1318). M52 lets finished builders expire after informational messages and their acknowledgments (#1772), and wakes builders or synthesizers once per new signed verdict round at the same head (#1777). Fixes: Claude Code builders use a stable run-copy trust root with doctor/up/spawn/restart guidance (#1792); personnel test snapshots exclude bytecode caches (#1807) and tolerate the absent changes directory after a cut (#1821), with a pinned checkout-version fixture (#1828). The cut also includes M53 brief headroom (#1566), bounded standing-grant references (#1746), repaired learning cards (#1793) and its opening specification (#1814), plus the M54 opening specification (#1819). No new breaking changes. Upgrade: from 7.11.0, `mdstack upgrade --latest --yes` applies as before; follow the one-time run-copy trust step reported by `mdstack doctor` before launching Claude Code builders (#1792). The owner upgrades the live install and restores Opus-first builders after publication. (issue #1817, PR #1832, 2026-11-13) Box skill copy: none.
- Capture 24 repaired learning cards in one M53 findings batch, retaining 27 incident occurrences, regression and procedure references, uncertainty and source-card dispositions. (issue #1793, PR #1824, 2026-11-13) Box skill copy: none.
- Specify M54's coordinator helper surfaces, applied posting and merge-up contracts, member dependencies and acceptance criteria, brief budgets, and affected test matrix before member builds. (issue #1819, PR #1822, 2026-11-13) Box skill copy: none.
- Specify M53's brief headroom and grant lifecycle slices, applied choices, member acceptance criteria, owner-shell prerequisites and version forecasts before build dispatch. (issue #1814, PR #1816, 2026-11-13) Box skill copy: none.
- Export pinned personnel content with explicit host bindings, integrity and setting provenance, refusal of authority overrides, and fake-host import proof without terminal machinery. Document the personnel, producer and host execution boundary. (issue #1180, PR #1805, 2026-11-13) Box skill copy: none.
- Specify M52 completion routing before its builds: the idle-only informational message exception and same-head verdict wake identity, with acceptance criteria, affected tests, build order and patch forecast. (issue #1798, PR #1800, 2026-11-12) Box skill copy: none.

### Changed

- Move tmux builder fix and researcher triage procedures into mandatory rendered companions, preserving their instructions and reserving 2 KiB of baseline entry-brief headroom. (issue #1566, PR #1825, 2026-11-13) Box skill copy: none.
- Record M52 completion routing as built in source, with landed PRs and review/validation evidence, its settled idle and verdict identity questions, and lessons from dependent consumers. Update README status and distinguish source completion from a published release or live installation. (issue #1799, PR #1811, 2026-11-13) Box skill copy: none.
- Sync M51 spec and README status with the landed opening spec, routing design and personnel delivery PRs; record settled questions and lessons while keeping shared-pool routing design only and T1–T4 unadmitted. (issue #1790, PR #1806, 2026-11-13) Box skill copy: none.
- Specify the team/project boundary, pinned personnel import and thin host binding, shared admission and repo-qualified routing, and per-repo landing isolation. The M51 design extends existing team files without shipping shared pools; derived implementation units require separate plan records. (issue #1318, PR #1802, 2026-11-12) Box skill copy: none.
- The portable spec opens M51 (personnel boundary and team routing design, #1779): two planned rows, #1318 (design and approved work breakdown) and #1180 (personnel delivery rows A–D, after #1318's approved contract), with ACs, paths, sizes and dependencies. It records the coordinator's applied choices (narrowed #1180 rows, closed `[team]`/`[repos.*]` composition, repo-qualified admission and per-repo land, T1–T4 not admitted) and classifies #1318 as patch and #1180 as minor, flagging its role-import contract. The team spec gains a planned-M51 header line and two open questions. (issue #1789, PR #1797, 2026-11-13) Box skill copy: none.

### Fixed

- Pin the personnel bundle test's checkout CHANGELOG independently of the repository release, retaining an exact version assertion across release cuts. (issue #1828, PR #1829, 2026-11-13) Box skill copy: none.
- Render standing merge grants as bounded live-profile lookup instructions so accumulated grant history cannot overflow role brief budgets; preserve source verification and per-PR permission requirements. (issue #1746, PR #1826, 2026-11-13) Box skill copy: none.
- Allow the personnel bundle test to snapshot a post-cut checkout without a changes directory, while preserving failure for missing required sources. (issue #1821, PR #1823, 2026-11-13) Box skill copy: none.
- Exclude Python bytecode caches from personnel test source snapshots so parallel bytecode writes cannot race the copy and fail CI. (issue #1807, PR #1808, 2026-11-13) Box skill copy: none.
- Finished builders can expire after informational owner-policy messages or their trailing acknowledgments. Pending work and unidentified acknowledgments still block idle detection, while upgrade delivery barriers and reclaim safeguards remain intact. (issue #1772, PR #1804, 2026-11-12) Box skill copy: none.
- Wake the builder or synthesizer once for a new signed verdict round at an unchanged head, using the posted round and coordinator reset epoch independently of the next review round. Duplicate verdict posts retain their canonical review provenance without another wake, and existing poll state seeds the new identity without replaying an unchanged verdict. (issue #1777, PR #1803, 2026-11-12) Box skill copy: none.
- Claude Code builders launch from a stable run-copy trust root while keeping their assigned copy and independent Git metadata. Doctor reports the one-time owner trust step, and up, spawn and restart warn before launch when trust is missing. (issue #1792, PR #1801, 2026-11-12) Box skill copy: none.

## [7.11.0] - 2026-11-12

### Added

- Release 7.11.0: M49, responsive runs and attributable failures, then M50, portable session contracts and stack binding. **Breaking:** protocol §7 gains a runtime-bound "No project pause" gate row with the new `mdstack pause` and `mdstack resume`, a work pause that keeps the coordinator and the watcher running while every other window stops and every gate that starts work refuses (#1714). Migration: none; an install with no `pause.json` behaves as before. **Breaking:** on the session runtime the researcher triage sweep is opt-in, so an unset `runtime.options.researchers` now defaults to `0` (#1724). Migration: a session profile that runs the triage sweep, including one with `triage.enabled = true` that relied on an omitted cap, sets `runtime.options.researchers` to a positive value, for example `researchers = 1`; tmux keeps its default of 2. The owner chose a minor for both. M49, responsive runs and attributable failures: the lead backstop backs off unchanged demand and honours typed `waiting:` lines (#1715), a builder's `[<Builder>/merge-up]` note starts its delta re-review (#1682), the builder lead completes a lifecycle reclaim with its pool's kill (#1701), `mdstack dequeue` names a lead-managed pool instead of `no free slot` (#1100), `RemoteRun` spawn tests refresh the runner heartbeat (#1659), bootstrap smoke tests pin the host sandbox probe (#1668), a watcher gone before SIGTERM counts as stopped (#1757), the M49 spec slice (#1748) and the M49 status sync (#1768). M50, portable session contracts and stack binding: a primary host on a command checkout (#1723), the configured specs home with the new `[docs] specs_external` (#1725), a VCS-neutral negative-control requirement (#1726), the one-time session bootstrap step in the session upgrade guide (#1727), session stack land by top change with revision ids and per-change readback (#1722), the M50 spec slice (#1749) and the M50 status sync (#1769). Upgrade: from 7.10.0, `mdstack upgrade --latest --yes` applies as before; only a session profile that runs the triage sweep needs the `researchers` edit (#1724). From 7.6.0, the same command applies without `down`/`up` (#1618); a profile without `[ci] required_checks` keeps its CI behaviour (#1536), `runtime.options.confinement` defaults to `off` (#1252), and a cut PR body uses `Refs #N` plus `Release issue: #N` (#1416). (issue #1771, PR #1780, 2026-11-12) Box skill copy: none.
- **Breaking:** new `mdstack pause` and `mdstack resume` give the owner a work pause that keeps the coordinator in window 0 and the watcher, instead of `mdstack down`, which ends window 0. Pause first writes a durable `pause.json` barrier in the state dir; while a land holds the lock it prints `pausing` and exits 75 with nothing stopped. Otherwise it stops every other window and each role-host run with every worktree, record, claim, inbox and status file kept. A surviving process or an unanswering host is an incomplete pause (exit 1, barrier kept). While the barrier exists or is unreadable, plain `down` (not `down --preserve`), dispatch, messages, review pools, restarts, trains, land-lock acquire (rechecked under the lock), land requests, `gc --apply`, route, lead and lifecycle starts and `ownership --action start|land` refuse. `mdstack up` starts no role window, and the watcher only queues events: no scan, timer, routine, route or nudge. Resume checks ownership, removes only the barrier, re-reads each stopped run's issue and PR live and restarts it once without spending its one restart; a closed or held item, a reviewer whose PR head moved, a failed read, an open ask or a `done:` run stays stopped, restarts leads and lifecycle floors, and queues one `resume` wake for the coordinator. Protocol §7 gains a runtime-bound "No project pause" gate and §9 a Project pause section; the coordinator brief maps an owner pause to `mdstack pause`. Migration: none; an install with no `pause.json` behaves as before. (issue #1714, PR #1767, 2026-11-12) Box skill copy: none.
- Session stack land for backends whose stack request names one representative change plus every member's revision id. `change.land-stack` may bind `<stack-top>` (the last member), `<stack-changes>` (member ids, base first) and `<stack-revisions>` (each member's immutable revision id, read by the new conditional `change.read-revision-id` at its checked head, one safe token, recorded in the intent before the first status read and reused, never re-resolved, by a rerun or resume). `land.stack_status = "per-change"` reads the stack back from each member's `change.land-status` through `[land.status]` and `change.read-landed` instead of `change.stack-status`; members in different states, queued beside landing included, are unknown and record nothing. A sync stack binding may now declare `land.change_placeholder`. Per-change readback refuses `land.stack_tests_against_tip`, so it never meets the tip gate. Legacy `<stack>` operation and every GitHub or unbound render are unchanged. (issue #1722, PR #1766, 2026-11-12) Box skill copy: deferred to the coordinator mirror (protocol §7 stack text).
- The coordinator's spec bookends now name the project's configured specs home instead of a fixed `docs/specs/`: `[docs] homes.specs` when set, or the new `[docs] specs_external`, an absolute URL naming a tracker item or document outside the repository (mutually exclusive with `homes.specs`; a reference, never a path or command). With an external home, `mdstack bootstrap` seeds no local spec and `docs-scan.py` records the home under `unchecked` instead of reporting a missing directory. Unset profiles render byte-identically; spec-first, `[spec] paths` and every merge and evidence rule are unchanged. (issue #1725, PR #1758, 2026-11-12) Box skill copy: none.
- `hosts.<primary>.checkout = "command"` is accepted, so a primary on a non-git checkout (such as a virtual-filesystem monorepo) can read ready. `mdstack host prepare <primary>` runs the declaration under the primary's own `root` (`checkout/<owner>__<repo>.json`, argv with no shell and a checked exit) in place of the git fetch and writes the same receipt as a remote command checkout; `mdstack host check <primary>` reads that receipt, never runs the command, and prints `ok project checkout` in place of `project mirror` only when the declared path exists and is the profile's project checkout. Doctor and engine-login rows still gate ready. Git primaries and remote command checkouts are unchanged. (issue #1723, PR #1756, 2026-11-12) Box skill copy: none.

### Changed

- `docs/specs/portable.md` records M50's outcome: all six rows are done with their PRs (#1756, #1759, #1758, #1763, #1762, #1766). The section adds the settled D1 opt-in researchers, D2 `specs_external` and D3 additive stack-binding choices, the deferred upgrade, the #1766 owner-shell stack-land lab capture lesson, merge permission as the owner's merge-ok for all PRs, and says M50 ships in 7.11.0, a minor by the owner's choice despite #1724's `**Breaking:**` default change. The session, multi-device and bootstrap design headers list what M50 built (#1722, #1723, #1724, #1725, #1727). (issue #1769, PR #1778, 2026-11-12) Box skill copy: none.
- `docs/specs/portable.md` records M49's outcome: all seven rows are done with their PRs (#1755, #1754, #1775, #1767, #1752, #1753, #1760), #1701's disposition reproduced a gap and took the code path, and the main-red fix #1757 (PR #1761) is noted as an M49 addition. The section adds the settled #1714 work-pause and #1715 hybrid-backoff choices, the deferred upgrade, the #1682 delivery-path and #1766 owner-shell evidence-placement lessons, merge permission as the owner's merge-ok for all PRs, and says M49 ships in 7.11.0, a minor by the owner's choice despite #1714's new §7 row. (issue #1768, PR #1776, 2026-11-12) Box skill copy: none.
- The negative-control section of `templates/evidence/cli-exit-stdout.md` now states its N1 requirement without Git: a throwaway snapshot of the guarded paths at the checked head, plus what the guard needs to run. A partial copy must name every copied path and dependency, keep their content at the head except for the mutation, and be recreated on verifier replay. The `git archive` setup stays as a labelled Git example. N1/N2 semantics, verifier replay and evidence acceptance rules are unchanged. (issue #1726, PR #1763, 2026-11-12) Box skill copy: none.
- The session runtime doc's Upgrading section now names the one-time step for a session crew set up by `mdstack install` and a manual render: with no `install.json`, `mdstack upgrade` refuses it because adoption verifies tmux installs only, so bootstrap once: with dispatch paused, move the manual render and any state `mdstack` link, `VERSION` and `config.toml` into a backup (bootstrap refuses files it does not own), run `bootstrap --project <absolute profile>` from the chosen release bundle's own `cli/mdstack` (dry-run, then `--yes`) to re-render, re-link and write `install.json`, then diff against the backup and upgrade as usual. Runtime behaviour is unchanged. (issue #1727, PR #1762, 2026-11-12) Box skill copy: none.
- **Breaking:** on the session runtime the researcher triage sweep is now opt-in: an unset `runtime.options.researchers` defaults to `0`, so `crew-render` writes the four ordinary session briefs (coordinator, builder, reviewer, synthesizer) with the same bytes as before and no `runtime/researcher.md`, restoring the shape a profile without the key had before the sweep brief arrived (#1404). A positive cap writes the sweep brief as before. `triage.enabled = true` with an unset or zero cap is refused, as `0` already was. The session options table now gives the default as `0`, and the session guide and sample profile say the same. Tmux keeps its default of 2. Migration: a session profile that runs the triage sweep, including one with `triage.enabled = true` that relied on an omitted cap, sets `runtime.options.researchers` to a positive value, for example `researchers = 1`; a profile without the sweep needs no edit. (issue #1724, PR #1759, 2026-11-12) Box skill copy: none.
- The portable spec opens M49 (responsive runs and attributable failures): seven planned members with their ACs, paths, sizes and dependencies (each after the 7.10.0 upgrade; #1714 after #1715), the owner's choices of a work pause for #1714 and the hybrid re-nudge backoff for #1715, and each gate change's version classification for the next cut: #1714's pause barrier is major as specified, #1682's merge-up detection is a patch. (issue #1748, PR #1751, 2026-11-12) Box skill copy: none.
- The portable spec opens M50 (portable session contracts and stack binding, #1747): six planned rows (#1723, #1724, #1725, #1726, #1727, #1722) with ACs, paths, sizes and dependencies on this slice and the live 7.10.0 upgrade. It records the owner's three choices (opt-in session researchers with a forward `**Breaking:**` migration, a specs-only `[docs] specs_external` reference, the additive stack binding) and classifies #1724 as major and #1722's stage 7 stack text as minor. (issue #1749, PR #1750, 2026-11-12) Box skill copy: none.

### Fixed

- The builder lead now treats a `lifecycle` `reclaim` work event as a request to remove that builder rather than a notice that it is gone. It runs its pool's `mdstack kill WINDOW`, reports a refusal as `lead-fault` and marks the id done only after the window and run record are gone. Before this, the lead brief named no action for the event, so a merged PR's close-out reached the lead and was acked, but the finished builder kept its slot until a manual terminal re-send (#1701's four windows). (issue #1701, PR #1775, 2026-11-12) Box skill copy: none.
- `mdstack down`, `mdstack upgrade` and `mdstack handoff stopped` no longer exit 1 with a `ProcessLookupError` traceback when the watcher exits between the PID read and the SIGTERM: a process that is already gone counts as stopped. `mdstack land-lock release` does the same for a recorded holder that exits after its identity check. Any other signal error (for example `PermissionError`) still raises. (issue #1757, PR #1761, 2026-11-12) Box skill copy: none.
- The bootstrap smoke tests no longer depend on the host's session sandbox: their fixture pins `CREW_SANDBOX_ENV` in the environment the copied bundle's subprocess inherits, so a host that denies writes in the checkout's `.git` reaches the smoke assertion instead of stopping at doctor's sandbox row. A new test denies that probe and shows both smoke outcomes still run, and that the unpinned host does stop there. Doctor's own sandbox tests keep the real probe. (issue #1668, PR #1760, 2026-11-12) Box skill copy: none.
- The watcher's lead backstop no longer re-wakes a lead every 60 seconds with no state change. Unchanged pending demand now backs off 60, 120, 240, 480, then every 900 seconds, restarting when the pending set changes, and the timer survives a watcher restart. A lead marks an acknowledged id that waits on the owner, a hold or CI with `waiting: #<n> owner|hold|ci id=<id>`; no backstop, slot release or coordinator backstop re-types it while the ref's token-free fresh state (poll-state's observed PR, its hold and owner-answer count, an open owner ask) is unchanged, and a change wakes it on that scan. Other ids keep their own retries, untyped lines silence nothing, and an acknowledged admission deferral keeps #1502's 60-second admission recheck, which types only that id once its ref is admissible. The three lead templates gain the Waits paragraph. (issue #1715, PR #1755, 2026-11-12) Box skill copy: none.
- A builder's published merge-up note now starts the delta re-review it asks for. Merge-up delta detection in `mdstack route` accepted only `[<Builder>/fix]` or `[<Builder>/ci-fix]` notes with a `pass=fix` or `pass=ci-fix` marker and "resolved ... conflict" wording, so the signed, head-pinned `[Ben/merge-up]` note on #1656 ("two text conflicts and one semantic conflict, and all three are resolved") sent its conflict-resolved merge-up to the synthesizer and the reviewer lead got nothing until a manual handoff. Detection now also accepts the `[<Builder>/merge-up]` header with a `pass=merge-up` marker and "conflicts ... resolved" wording; the round carries from the approved head, and a replayed event starts no second review. Clean merge-ups, moved heads, unsigned or foreign notes, holds and express keep their current handling, and no marker or gate changes. (issue #1682, PR #1754, 2026-11-12) Box skill copy: none.
- The `RemoteRun` spawn tests in `test-crew-spawn.py` no longer depend on setup finishing within the fake host's runner freshness window. Their spawn helper rewrites the runner heartbeat just before each spawn, so a loaded host whose setup takes longer than 3 × interval no longer gets a `runner down` refusal. Every spawn assertion now prints the spawn's stdout and stderr, so a future failure shows why. A new case ages the heartbeat past the window: an unrefreshed spawn is still refused with `runner down`, then the refreshed spawn starts the run. Production freshness (`crew-remote.py`) is unchanged, and this does not prove the original failure's cause. (issue #1659, PR #1753, 2026-11-12) Box skill copy: none.
- `mdstack dequeue` no longer reports `no free slot` when a queued request is held back only because its pool's lead owns dispatch: it names the lead-managed pool and the operator path (`use the builder lead or CREW_POOL=builder`), keeps `no free slot` for a truly full band, says `none match --ref` for an unmatched ref and lists both reasons for mixed pools. Which requests dequeue may start is unchanged. (issue #1100, PR #1752, 2026-11-12) Box skill copy: none.

## [7.10.0] - 2026-11-12

### Added

- Release 7.10.0: M48, release integrity and consistent reports, then M46's close-out and all of M47; 7.9.0 is skipped. **Breaking:** a release cut PR now links its release issue with `Refs #N` plus one whole line `Release issue: #N` instead of `Closes #N`, so landing the cut no longer closes the issue before publication, which changes how the Linked issue merge gate is satisfied for a cut (#1416); the owner chose a minor for it. Migration: write a cut PR body with `Refs #<release issue>` and the `Release issue: #<release issue>` line, not `Closes`; installs need no edit. M48, release integrity and consistent reports: a release cut refuses a minor or patch that breaks the published predecessor's pack manifests (#1415), released CHANGELOG sections are immutable (#1417), moved or quoted prose keeps its qualifiers with the `check-pr-linkage.py` allocation check (#1418), one outcome-first report skeleton for every role with the team in signatures (#431, #1291), work-unit issues with one PR each (#978), the auto-apply deadline never supplies a merge-ok (#258), the coordinator's owner-config authorization rule (#372), the `examples/agentconnect/` example removed (#1314), the M48 spec slice (#1697) and the M48 status sync (#1721). M46 close-out: the campaign lint's one termination model (#1684) and the M46 status sync (#1690). M47: a bootstrap re-run with nothing changed writes nothing (#1090), team-file `#<repo>` references bootstrap the selected repo (#1344), briefs read core memory at the remote default branch (#1537), `mdstack connect` uses the host `address` (#1595), the repo guard stays out of the bundle (#281), builder runs own their Git metadata and can run confined, with the new `runtime.options.confinement` (B5, #1252; its live confinement proof moved to #1739), the new `mdstack gc` merged-only worktree sweep, also run by `mdstack route` on each backstop wake (B6, #316), the M47 spec slice (#1691) and the M47 status sync (#1735). Upgrade: from 7.8.0, `mdstack upgrade --latest --yes` applies as before; `runtime.options.confinement` defaults to `off`, so no profile edit is needed (an unconfined builder gets a `mdstack doctor` warning), and only how a cut PR body is written changes (#1416). (issue #1720, PR #1742, 2026-11-12) Box skill copy: none.
- New `mdstack gc` sweeps run working copies that lifecycle reaping missed: a run record whose window is gone and a directory directly under `paths.worktree_root` that no run names. It is a dry run by default, listing each candidate as `keep` or `remove` with its reason. A copy is removable only when its PR is merged (the run's PR, else a merged PR whose head is the copy's `HEAD`, so a squash merge with a deleted branch still proves) and the C6 check finds nothing unlanded. It keeps live windows, claimed or referenced copies, recent orphans, nested worktrees, open or closed-unmerged PRs and unlanded or unreadable copies, with reasons. `--apply` re-checks each candidate, removes at most `--max` (default 10) with `git worktree remove` (never `--force`) or, for a builder's own copy, by deleting its directory, then drops the run's records through the kill path; a failed removal is reported and exits 1. `mdstack route` runs it with `--apply --max 5` on each backstop wake, so a lost `pr-merged` event no longer leaves a merged run behind. Session-runtime worker and probe worktrees now use the same `paths.worktree_root`. Git stays the only worktree provider: treehouse was considered and deferred, as recorded in the tmux and session runtime docs. (issue #316, PR #1740, 2026-11-11) Box skill copy: pending the coordinator's mirror of templates/runtimes/session/coordinator.md.
- Moved or quoted prose keeps its meaning. A doc move records a source-to-destination qualifier comparison (trigger, runtime scope, conditions, exceptions) in the PR body, per a new Doc moves section in `CONTRIBUTING.md` (#1125). Before opening a PR, the builder cites the item's newest signed coordinator allocation and runs the new role helper `scripts/check-pr-linkage.py`: each allocated issue needs exactly one whole `Closes #N` line, a release cut uses #1416's release-only form, and every other closing keyword is flagged by line, descriptive mentions of closed issues included (#1131, #1211). A later reallocation is reported in a signed note, never fixed by a body edit. It is a builder duty in the build pass and PR conventions, not a merge gate. (issue #1418, PR #1719, 2026-11-11) Box skill copy: none.
- Every role's human-facing reports share one outcome-first skeleton, documented once in the roles doc (Report skeleton): a headline that ends with one status from a fixed set (pass, changes, landed, escalated, blocked), then TL;DR, numbered changes or findings, evidence and the next actor. A new optional `[report]` profile table sets each status emoji (neutral defaults) and turns every emoji off install-wide (`emoji = false`). Signatures now carry the crew team (#1291): a team file's resolved `team.name`, else its file name, else `identities.team`; legacy single-repo installs omit it. Briefs render them through the new `<RoleSignature>` and `<report-status>` placeholders; every role brief, researcher and synthesizer included, carries the resolved status set. Builder signature readers (precheck and merge-up delta routing) accept a signature with no emoji, a custom emoji or a team. No marker, gate or label changes. (issue #431, PR #1709, 2026-11-11) Box skill copy: none.
- Release validation now refuses a minor or patch cut that breaks a pack manifest the published predecessor accepted. `scripts/release-compat.py`, run by `release.yml` `validate`, pins the greatest stable tag below the cut version. It checks a named corpus from that tree, the shipped GitHub manifest and an external pack derived from it, with the baseline's validator and then the candidate's. A newly failing manifest names the baseline, the manifest, the failing requirement and the major to cut. A major cut allows the break; an unreadable baseline fails with a repair step. (issue #1415, PR #1705, 2026-11-11) Box skill copy: none.

### Changed

- `docs/specs/portable.md` records M47's outcome: B5 (#1252, PR #1707) and B6 (#316, PR #1740) are done, with B5's live confinement proof moved to #1739 by the owner's choice; the section adds the settled #1465 owner-shell proof question and the #1732–#1734 lessons, and says all of M47 ships in 7.10.0 (7.9.0 skipped). (issue #1735, PR #1741, 2026-11-11) Box skill copy: none.
- The portable spec's M48 section (release integrity and reports) gets its status-sync slice: all nine rows `done` (#1415, #1416, #1417, #1418, #978, #258, #372, #431 with #1291, #1314). It records the 7.10.0 outcome (#1720): a minor by the owner's choice despite #1416's `**Breaking:**` entry, with 7.9.0 skipped. It also records the questions M48 settled and two lessons: an owner merge-ok on a sensitive PR lost on a clean merge-up (#1717), and the lead backstop re-nudge loop (#1715). M47 stays open: its five landed rows (#1344, #1537, #1090, #1595, #281) get Status `done` and ship in 7.10.0, while B5 #1252 (PR #1707) and B6 #316 stay `open` for the next release. (issue #1721, PR #1730, 2026-11-12) Box skill copy: none.
- **Breaking:** a release cut PR now links its release issue in a release-only non-closing form, `Refs #N` plus one whole line `Release issue: #N` in the same repository, instead of `Closes #N`, so landing the cut no longer closes the issue before publication; this changes how the Linked issue merge gate is satisfied for a cut. `release-trigger.py linkage` checks the form on the cut PR, and `authorize` reads the issue from the body at publish; a missing, ambiguous or foreign target, or a closing keyword for it, refuses with a correction step. The publish job posts the release URL and only then closes the issue; any earlier failure leaves it open. Ordinary PRs keep `Closes #N`. Migration: write a cut PR body with `Refs #<release issue>` and the `Release issue: #<release issue>` line, not `Closes`. (issue #1416, PR #1711, 2026-11-11) Box skill copy: none.
- Work-unit issues: an issue is a unit of work (a feature, fix or design), not a slice cut to a line budget, and each issue gets one PR split into logical commits that pass their tests where tests apply. The rule is in the coordinator planning duty in `docs/roles.md`, protocol stage 1, the coordinator dispatch skill and the builder's PR conventions. Reviewers read a multi-commit round commit by commit and judge the combined diff at head. Separate work, owner-decision or design-first items, gate-contract changes approved on their own and cross-area splits keep separate issues; M26 principle 9 (doc moves) stays. The portable spec's ~100-line slice sizing is now historical, not a budget. No gate changes. (issue #978, PR #1710, 2026-11-11) Box skill copy: none.
- Coordinator briefs now carry an owner-config rule (in full for session and the Grok Bot routines; the tmux brief points to it to fit its size budget): before editing the owner's profile, team file or config, the coordinator reads the recorded owner authorization and its scope. A covered edit is applied and reported with its key and authorizing record, with no new ask; a documented repair stays within its stated authority; an uncovered edit or unusable path keeps the owner's config, is reported with the reason and goes to the §6 owner-decision path. Owner-only settings keep their restrictions. `docs/roles.md` gains the matching coordinator section. (issue #372, PR #1708, 2026-11-11) Box skill copy: none.
- The repo guard `scripts/check-repo.py` no longer ships in the release bundle. The secret-scan patterns, path glob and markdown scanning it shared with the install CLI now live in shipped `core/secret-patterns.py`, `core/path-glob.py` and `core/markdown-scan.py`, which `crew-config.py`, `docs-scan.py` and the guard all load, so detection and glob matching are unchanged. The bundle smoke test asserts the guard is absent and runs `check-markdown.py` and `docs-scan.py --help` from the bundle. (issue #281, PR #1700, 2026-11-11) Box skill copy: none.
- Protocol §6 and the tmux runtime's C8 row now say the auto-apply deadline only wakes the coordinator to apply a permitted default: elapsed time never supplies a merge-ok, and a merge still needs the repository's own recorded standing grant or the owner's per-change merge-ok at head, plus every applicable gate. This clarifies the shipped coordinator brief; it adds no timer or permission rule. (issue #258, PR #1699, 2026-11-11) Box skill copy: none.
- The portable spec opens M48 (release integrity and reports): nine planned builds with their ACs, paths and dependencies (#978 and #1416 before #1418), the settled D1–D3 decisions with #1291 folded into #431, and each gate change's version classification for the v7.10.0 cut: #1416's release-only linkage exemption is major, #1415's cut-time refusal is minor. (issue #1697, PR #1698, 2026-11-11) Box skill copy: none.
- The portable spec opens M47 (installs and working copies): seven planned builds with their dependencies (B1 and B2 before B3, B5 before B6), the settled memory-source, cleanup and deferred-provider decisions with #316's AC4 revised, and the enforcing boundary for #1252: per-run Git metadata plus an OS write sandbox, with unsupported configurations refused under `runtime.options.confinement = "enforce"`. (issue #1691, PR #1693, 2026-11-11) Box skill copy: none.
- The portable spec's M46 section (verification exercises the real path) gets its status-sync slice: Status `done` for B1 #1614, B2 #1412 with its split #1684, B3 #1411, B4 #1413, B5 #1414, B6 #1493, B7 #1470 with #1469 (its owner-run A19 proof still pending) and F1 #1649; the M45 capture #1688 stays `open` until its PR merges. It records the questions M46 settled (#1469 into #1470, #1649 learning-only, the #1677 split and the one termination model) and its lessons (fail closed early; measure fixture impact before a sweeping lint rule). (issue #1690, PR #1692, 2026-11-11) Box skill copy: none.

### Removed

- Removed the `examples/agentconnect/` worked example (the October 2026 pilot wiring), with its required-doc entries, docs index row, the links to it from the onboarding runbooks, `templates/README.md`, `scripts/README.md` and the framework spec, and the now-empty `examples/**` row of the deliverables manifest and its generated `docs/deliverables.md` row. The parity fixture keeps its values; only its provenance comment changed. (issue #1314, PR #1702, 2026-11-11) Box skill copy: none.

### Fixed

- `mdstack bootstrap` re-run with nothing changed now prints `crew bootstrap: no changes`, exits 0 and writes nothing: no target, link, exclude or `install.json` rewrite and no self-test. It compares the full planned install (record fields, target bytes, link, exclude lines, pending removals and scaffolding, and any deployed render) with the live one; a changed input or a failed previous install still re-applies, and edited-target refusals are unchanged. (issue #1090, PR #1716, 2026-11-11) Box skill copy: none.
- A builder run can no longer remove another run's working copy when its launch is confined (#1252, M47 B5). Spawn gives each builder its own Git metadata (a local copy borrowing the shared checkout's objects read-only) instead of a linked worktree, and Codex in `safe` or `auto` runs it under an OS write sandbox whose writable roots are only that copy and the state dir (`/tmp` and `$TMPDIR` dropped, `TMPDIR` moved into the copy). The new `runtime.options.confinement` (`enforce` or `off`, default `off`) refuses an unconfined builder spawn or restart under `enforce`, including a host where `codex sandbox -- true` fails (a launcher that already sandboxes Codex nests the sandbox); under `off` the run record marks it unconfined and `mdstack doctor` warns. `mdstack migrate` moves each builder copy with the crew. (issue #1252, PR #1707, 2026-11-11) Box skill copy: none.
- `mdstack bootstrap --project <team file>#<repo>` bootstraps the selected repo of a multi-repo team file instead of proposing a literal `#<repo>` profile: the reference reaches resolve, doctor, render, the `--version` release source and `install.json`, the team file is read and copied as TOML, repo-local pointers and excludes go in the selected repo's `paths.checkout`, uninstall cleans them there, and `mdstack upgrade --version` follows such a recorded install. (issue #1344, PR #1706, 2026-11-11) Box skill copy: none.
- `scripts/check-changelog-pr.py` now fails a PR that changes a released `CHANGELOG.md` section: every `##` (level-two) section below `## [Unreleased]` must stay byte for byte as at the merge base, whitespace and line endings included, so a PR, a cut included, may only add a new version section on top and edit `[Unreleased]`. The check runs before the exempt-path and fragment success paths, so a new fragment no longer lets a released-section edit through, and the failure names each changed section. CONTRIBUTING states the rule next to the fragment rules: restore the released section and record the correction in a new fragment. Replaying the guard over `CHANGELOG.md` history passes the 7.6.0, 7.7.0 and 7.8.0 cuts and flags only the two past late-fragment folds into an already cut section (#920, #1434), which the cut freeze (#1433) now prevents. (issue #1417, PR #1704, 2026-11-11) Box skill copy: none.
- Rendered briefs no longer inject core memory from a stale local checkout: each render reads `memory/owner.md` and the role files at the tip of the checkout's remote default branch (`repo.default_branch` on `origin`), resolved once and shared by every role output, and names that revision on stderr. A merged memory PR reaches the next `mdstack up` or `mdstack upgrade` without pulling the checkout, and local unmerged edits never enter a brief. A failed resolve, fetch or read fails the render closed; a root with no `origin` remote and no `memory/` adds nothing, as before. (issue #1537, PR #1703, 2026-11-11) Box skill copy: none.
- `mdstack connect` now uses the inventory host's `address` (#1034) as the `ssh`, `mosh` or `et` destination when set, falling back to the host label as `host check` and `host prepare` already do, so a host whose label does not resolve no longer needs an SSH config alias. Hosts without `address` keep today's argv, and `connect.alias` stays a lookup name only. (issue #1595, PR #1695, 2026-11-11) Box skill copy: none.
- The campaign lint now decides where an `exit` or `return` stops by one stated termination model instead of per-form patches: `exit` ends the step only in the step's own shell, so an `exit`, `return` or call to a helper that can `exit` inside a subshell, pipeline, background job or command substitution is refused by name. This closes the two forms left open by #1677 (an exiting helper called in a pipeline, a backgrounded `exit` in a handler group), and `docs/campaign-harness.md` documents the model. A04, A25 and A31 fixture steps were restructured with unchanged oracles. (issue #1684, PR #1687, 2026-11-11) Box skill copy: none.

## [7.8.0] - 2026-11-11

### Added

- Release 7.8.0: M45, recover runs and preserve queue state, then the first M46 items (verification exercises the real path). M45, recover runs and preserve queue state: absent required CI checks never read as green, with a configurable `[ci] required_checks` baseline (#1536), stalled-builder recovery after Claude Code API and capacity errors (#1633), reviewer rounds reset after the canonical steer resume (#1005), next-eligible-engine selection when an engine is out of quota or unavailable (#631, #1074), the root plus `bypass` Claude Code spawn refusal (#738), malformed reviewer work isolated instead of stalling the queue (#1020), tmux session creation verified (#1480) and leads reconciled after a handoff ack (#1082), both already shipped early in 7.7.0, and the deflaked upgrade and `mdstack up` watcher tests (#1654). M46 already landed: the stack land lab against the real session synthesizer (#1614), pack discovery without optional files (#1411), the shared `render_template` test helper (#1413), the untracked-files warning in `check-repo.py` (#1414), the unbuffered lab stub (#1493), the A19 smoke in a linked worktree and the doctor's herdr server row (#1470, #1469), campaign steps that fail closed with the `campaign-lint.py` inventory (#1412), and the detached-fixture capture-pipe lesson (#1649). No breaking changes; from 7.7.0, `mdstack upgrade --latest --yes` applies as before, and a profile without `[ci] required_checks` keeps today's CI behaviour (#1536). (issue #1685, PR #1686, 2026-11-11) Box skill copy: none.
- A stack land lab (`dev/tests/scripts/fixtures/stack-land/run.py`) runs the production session synthesizer against a stub stack-land backend. It covers a held member, red per-member CI and a missing approval (each with zero `land-stack` requests), a fully passing stack (exactly one request), an incomplete readback (no merge post) and a lost acknowledgement (read back, not resent). `test-stack-land-lab.py` checks its plumbing in CI with a scripted engine. (issue #1614, PR #1680, 2026-11-11) Box skill copy: none.
- `scripts/check-repo.py` now warns on stderr when a git work tree has non-ignored untracked files, naming each one: its path checks (deliverables and the rest) read `git ls-files`, so a run before `git add` silently skipped new files. Ignored files stay quiet, the exit code is unchanged (no new gate), and once the files are added they are checked as usual. (issue #1414, PR #1676, 2026-11-11) Box skill copy: none.
- Template tests now have one shared helper, `render_template` in `dev/tests/crew_testlib.py`, that renders a file through `core/crew-render.py`'s production `render()`: includes are expanded and control, backend and strategy lines are filtered before placeholders are filled. The grok-bot ownership guard test now uses it instead of calling `Renderer.line` on hand-expanded template text. A new render test shows a template with a shared policy include rendering cleanly through the helper. Token-level `Renderer.line` unit tests are unchanged. (issue #1413, PR #1674, 2026-11-11) Box skill copy: none.
- Tests only: two regression cases in `dev/tests/core/test-crew-pack.py` resolve a `pack.toml` plug-in pack through project `paths.pack` discovery, never `--pack-manifest`. With its optional `profile.toml` removed, the pack still provides its connector, harness and skill, layers resolve as `core, default, pack, project` with the pack's environment defaults, and the flavor falls back to the core default `standard`. With no backend render map for its tracker connector, `resolve` keeps the default numeric item and change ids and still refuses a native string control item; adding the map on the same path makes it accepted. No behaviour changes. (issue #1411, PR #1673, 2026-11-11) Box skill copy: none.
- Lessons log: new lesson on a detached test-fixture child that inherited the `capture_output` pipe, so each launch waited about 60 seconds for EOF and repo-guard CI hit its job limit. It records the DEVNULL stdio repair from #1637, the unchanged assertions and the published measurements. (issue #1649, PR #1672, 2026-11-11) Box skill copy: none.
- The portable spec gains the M46 section (verification exercises the real path): its scope, one slice row per item (#1614, #1412, #1411, #1413, #1414, #1493, #1470 with #1469, #1649) with Status and dependencies, and the decisions it settles: #1469 folds into #1470, #1649 is a learning only, no protocol or merge-gate change, and the owner steps for the A19 proof. (issue #1669, PR #1671, 2026-11-11) Box skill copy: none.

### Changed

- The portable spec gains the M45 section (recover runs and preserve queue state) as its status-sync slice: one row per landed item with Status `done` (#1536, #1633, #1639 diagnosis only, #1020, #1005, #631 with #1074, #738, #1480, #1082, follow-ups #1654 and #1665), #1003 `dropped` as covered by #1163, the settled questions (B1's required-check baseline, #1639 as caller error) and its lessons (flaky default-branch tests, environment-dependent bootstrap smoke #1668). (issue #1670, PR #1683, 2026-11-11) Box skill copy: none.

### Fixed

- The A19 smoke runs each binding in a detached linked worktree of its source checkout, as `mdstack spawn` does, and removes only that worktree after the run stops; an unmet Claude Code role trust check for the source's repository root blocks the binding instead of stopping at the folder-trust dialog (#1470). `mdstack doctor` gains a `session server` row for herdr: runs inherit the shared server's environment and sandbox, so a server whose holders read sandboxed (macOS `sandbox_check`) fails, with unknown provenance a warning and a stopped server a human step; mdstack still never starts or stops that server (#1469). (issue #1470, PR #1681, 2026-11-11) Box skill copy: none.
- Campaign steps fail closed on the assertion forms the new lint proves, and required failing cases stay recorded: a new `scripts/campaign-lint.py` parses each scenario step and refuses an unhandled assertion (a `test`, `[`, `grep -q` or `!` whose exit neither becomes the step's result nor is captured, handled or guarded by `|| exit`), so a failed assertion chain followed by a passing command can no longer read as PASS; the lint is an allowlist of forms whose failure propagation it proves, and any other construct (a brace group other than an unconditional `|| { ...; exit N; }` handler, a subshell that can fail, a backgrounded compound command, `eval`, `trap`, a non-brace function body) is refused by name. `campaign-run.py` refuses such a step before it runs, as well as one that does not parse. A step may record a required failing case as `expected-fail` or `accepted` with a reason, reported as EXPECTED FAIL or ACCEPTED and never as PASS. `check-repo.py` (rule `campaign`) checks against the merge base of `origin/main` that no required case was deleted without a reason in `retired-cases.json`. The lint found and fixed masked assertion chains in the A01 and A18 fixtures; A12, A13, A22, A24, A28 and A32 steps were restructured into the allowed forms with unchanged oracles. Explicit refusal oracles (`rc=$?` captures and declared exits) are unchanged. Remaining failure-propagation forms (an exiting helper called in a pipeline, a backgrounded `exit` in a handler group) are tracked in #1684. (issue #1412, PR #1677, 2026-11-11) Box skill copy: none.
- The lab `status-pull` scenario's stub role run now reads typed input from fd 0 with `os.read` and splits it into complete newline-delimited lines, as the placed-run host stub does since #1492. Before, `select` on `sys.stdin` followed by a buffered `readline()` left a second inbox line typed in the same write in Python's buffer, so its ack was never written until more input arrived. A partial line is now kept and completes on the next write. Lab test fixture only; no runtime or gate behaviour changes. (issue #1493, PR #1675, 2026-11-11) Box skill copy: none.
- Two watcher tests no longer flake in CI. The upgrade test that stops a lock-holding watcher whose PID file was lost now waits for the stopped holder to exit instead of polling it once, since the kernel frees the lock before the exiting process can be reaped. The `mdstack up` persistent-watcher test now waits until its watcher frees `wake/watcher.lock` before the temporary directory is removed, so a scan still writing `wake/` no longer fails the teardown. The upgrade and watcher code was already correct and is unchanged. (issue #1654, PR #1664, 2026-11-11) Box skill copy: none.
- A reviewer `work` handoff whose ref is not a readable JSON object (a markdown note, a missing file, a JSON list) no longer stalls the reviewer queue or hides its admission. `mdstack reviewer-pool` records it as `blocked: <id> invalid-work-ref <path> <reason>` in the reviewer lead's status, which route keeps for the coordinator, marks the handoff done and goes on to the next message. `mdstack schedule snapshot` lists it as an unranked `invalid-work` item with its `error` instead of making the whole reviewer demand `unknown`. Valid work behind it is still dispatched, and deferred valid work still replays. (issue #1020, PR #1660, 2026-11-10) Box skill copy: none.
- A missing expected CI check no longer reads as green. The new optional `[ci] required_checks` profile list names the checks that must each be present at head: `mdstack poll`, `ready_sample`, the gate-status CI item (which now names the missing checks) and `mdstack train` build and wait keep CI pending while one is absent (a train times out rather than passing), even when every observed check passed. Failed and infrastructure-failed checks still read as failed or infra, unlisted checks such as `lab` stay optional, and a profile without the table keeps today's behaviour. (issue #1536, PR #1658, 2026-11-10) Box skill copy: none.
- A worker whose engine is out of quota now moves to the next eligible engine instead of sitting idle. `mdstack spawn` filters the role's engine order before picking: a local launch skips an engine whose executable is not on PATH, and a contributor-tier engine (Muse) is skipped on a private or unverified repository, so a Muse-first order starts the next engine rather than refusing (closes #1074); the launch policy still refuses a contributor-tier launch. The Claude Code, Codex and Cursor adapters declare `QUOTA`, their own usage-limit line. A run whose harness shows it probes `quota`, not `alive` or a trust dialog, and the watcher queues one `quota` wake for it. `mdstack restart` relaunches a quota run once on the next eligible engine in its role's order. It always relaunches in place, in the same worktree, head, claim and inbox, and lists unacknowledged inbox IDs in the brief. It skips every engine the run exhausted and records `exhausted` and the engine actually used. It refuses when no engine is left, or for a reviewer whose PR head moved. The builder-lead brief and the tmux liveness table name the new class. (issue #631, PR #1657, 2026-11-10) Box skill copy: pending the coordinator's mirror of templates/runtimes/tmux/builder-lead.md.
- Reviewer rounds now restart after the coordinator's canonical `pass=steer cmd=resume` (or `cmd=cutover`) record, as protocol §5 and §9 already say. Before, `mdstack poll` reset the count only on a legacy `pass=resume` or `pass=cutover` marker, so after an owner-approved resume the pool dispatched a resumed fix head as round 4 instead of round 1. Legacy coordinator records still reset. With the profile, poll and reviewer dispatch derive the round the same way: they count only this runtime's reviewer verdicts and resets signed by its coordinator. Builder notes, other steer commands, ownership handoffs and other runtimes' records reset nothing. Merge-ups keep the round of the approval they renew. Round caps and gates are unchanged. (issue #1005, PR #1656, 2026-11-10) Box skill copy: none.
- A builder left idle at its prompt after a Claude Code API error now reaches its lead. The Claude Code adapter's transient-error text also matches `⎿  API Error: Connection lost mid-response` and the gateway's `429 … capacity … exhausted` line, still at the harness's own indent only, so each counts once per error window in `schedule/errors.jsonl`. `mdstack watch` wakes the builder lead with a `stale` wake of liveness `claim` when an alive builder holding acknowledged unfinished work (an `ack:` with no later `done:`, `blocked:` or `failed:`) has a claim heartbeat older than 15 minutes, even while the supervisor heartbeat keeps its status file fresh. It fires once per claim silence and never for a mid-turn harness, a held item or a builder waiting after `done:`. Existing liveness, identity and one-restart rules are unchanged. (issue #1633, PR #1655, 2026-11-11) Box skill copy: none.
- Spawn preflight for Claude Code as root: Claude Code exits at once in `bypass` permission mode when it runs as root, which left a worker window that vanished and surfaced only as missing probes. `mdstack spawn` (and restart and lead launches) now refuses a Claude Code role window in `bypass` when the launching process's effective uid is 0, before the window opens, with an error naming root plus bypass and the two fixes: run the crew as a non-root user, or set `runtime.options.permission_mode` to `auto` or `safe`. A remote run is checked on its execution host by that host's uid, never the primary's. The adapter contract gains an optional `launch_refusal(mode, uid)`. Non-root and non-bypass launches, and other engines, are unchanged. (issue #738, PR #1652, 2026-11-10) Box skill copy: none.

## [7.7.0] - 2026-11-11

### Added

- Release 7.7.0: crew runtime reliability (M43), coordinator safety and process (M44) and org-pack requests (M42). M43, crew runtime reliability: a persistent watcher that outlives coordinator turns (#1346), obsolete recovery wakes consumed instead of waking the coordinator (#1476), acknowledged admission deferrals no longer re-nudged (#1502), a held-only backstop backoff (#394), private per-invocation fetch refs (#1367), a passing verdict that reconciles PR labels (#1464), rereview identity kept through restarts (#1477), conflicting PRs routed to the builder (#1398), and the upgrade fixes: adopting an install with no `install.json` (#1616) and applying under a launcher wrapper (#1618). M44, coordinator safety and process: the secret-retrieval rule (#397), the plan gate and environment preflight (#444, #396), spec bookends (#259), land-authority provenance (#314), head-branch deletion in the land itself (#395) and the coordinator brief trim (#1635). M42, org-pack requests: evidence and role contracts (#1604), session stack land (#1605), host-wide working-copy claims (#391), team-ref migration and explicit team names (#1347, #1348), and the home-root harness target (#1032). Early M45 fixes: `mdstack up` ensures leads on a running session after the handoff ack (#1082), and the tmux `new_session` raises when `new-session` exits 0 without a session (#1480). No breaking changes; from 7.6.0, `mdstack upgrade --latest --yes` should now apply without `down`/`up` (#1618). (issue #1661, PR #1663, 2026-11-11) Box skill copy: none.
- Spec bookends: every milestone opens with a spec slice and closes with a status-sync slice. The rule is in `docs/roles.md` and in a new shared fragment `templates/policy/coordinator/spec-bookends.md`, included in the tmux, session and Grok Bot coordinator briefs and listed in the dispatch skill. The status-sync slice sets Status cells, the README and runtime headers, settled questions and lessons, adds a row for each mid-milestone addition, and confirms every landed or superseded item is closed. A new `check-repo.py --only design-headers` check fails a doc whose H1 says "(design)" or "in design" unless that H1 or its banner names an open milestone of `docs/specs/portable.md` section 5. A closed milestone or an unknown reference fails, unless the doc is listed with a reason in `scripts/design-headers.txt`. `docs/deliverables.md` drops its stale "(design)" header. Merge gates are unchanged. (issue #259, PR #1648, 2026-11-10) Box skill copy: none.
- Plan gate: the coordinator creates implementation items, adds a new `crew:ready` or dispatches a new build only for an item in an owner-approved plan (a milestone or project). "Start building" counts as a request to propose a plan, never approval. The owner's OK is a signed `[<CoordinatorBot>/steer] plan approved` comment with a `pass=steer cmd=plan-ok` marker on the plan's tracking issue, defined in protocol §6. The rule records open decisions before items are derived, reconciles a later owner change in one steer, and keeps the fix, CI, follow-up and owner-requested trivial-docs exceptions. It also adds the #396 environment preflight: a platform item becomes ready only when its spec cites dated, observed host, toolchain and device facts and lists every owner-only prerequisite up front. A new shared fragment `templates/policy/coordinator/plan-gate.md` puts the rule in the tmux, session and Grok Bot coordinator briefs. `templates/spec.md` gains Target environment and Owner prerequisites sections, and onboarding Step 8 records plan approval before the first `crew:ready`. Merge gates are unchanged. (issue #444, PR #1625, 2026-11-10) Box skill copy: none.
- Session stack land (M42 B4). A change backend may declare `land.stack = true` with the conditional `change.land-stack` and `change.stack-status` operations, and `land.stack_tests_against_tip` for a combined-stack test on the current tip; `resolve` checks both. The session synthesizer brief then renders a stack-land recipe: every §7 gate is checked for every member at its own head, one failing member refuses the whole stack, and otherwise `mdstack land stack --stack <n>:<head-sha>,...` records one intent, re-reads every member head and sends one atomic request only when every member reads `none`. A lost acknowledgement is read back, never resent. Only a complete per-member readback succeeds, printing one merge record and marker per member with its landed revision and, when declared, the named combined-stack check; a missing, reordered, malformed or split readback is unknown and records nothing. `mdstack land resume` reads stack intents back without requesting and `mdstack land stack-done` clears a landed one. Without the binding, session lands stay one per run; tmux renders and trains are unchanged. (issue #1605, PR #1613, 2026-11-10) Box skill copy: none.
- Runs now claim their working copy host-wide, so two crews on one host (one owner's standing and ad-hoc crews, say) can no longer start runs in the same copy. A claim lives in `~/.mdstack/copy-claims/`, shared by every crew and state root on the host, is keyed by the copy's real path (symlink and `..` aliases are one claim) and records host, path, crew, run, item and time. `mdstack spawn` and a role host's `spawn` verb claim each fresh worktree before adding it and refuse another holder's claim before any worktree or window; a refused or failed launch releases its own claim, and `mdstack kill` releases it once the run is removed (kept unlanded work keeps it). New `mdstack copy-claim acquire|release|show` lets a coordinator claim an existing copy before a hand-dispatched run. Only the holder releases a claim; no age or other crew reclaims one. (issue #391, PR #1610, 2026-11-10) Box skill copy: none.
- A team file can set `[team] name = "<team>"` (`[a-z0-9-]`, 1–63 characters) as its stable identity: it keys the team's state root and `crew-team-<team>` tmux session, so a conventional `~/.mdstack/config.toml`, a renamed file or a symlink to the file resolve the same team, and the file name no longer has to follow the team-name rule. A file without `team.name` keeps its file-name identity unchanged. Changing the name moves the state root and session, so stop the crew and move the state with `mdstack migrate` first. (issue #1348, PR #1608, 2026-11-10) Box skill copy: none.
- A `pack.harness` file entry can now set `root = "home"` to install its target under the agent home of the user running `mdstack bootstrap` (`$HOME`), for packs whose agents read instructions from a per-user home. The target stays relative and normalized (absolute and `~` targets are still refused) and gets the same refusals, target hash, `drift:` report and uninstall removal as a project target, with no `.git/info/exclude` line; the plan names each home write. Packs without home entries are unchanged. (issue #1032, PR #1607, 2026-11-10) Box skill copy: none.

### Changed

- The tmux coordinator brief is 911 bytes smaller (15,300 to 14,389 path-normalized bytes against its 15,360-byte budget), freeing room for M44's pending brief additions. Long route bullets are reworded without dropping any rule, marker or command, and the merged-PR close-out detail, which `mdstack route` performs, moves to the tmux binding's `mdstack route` section behind a one-line pointer. The session coordinator brief and the size-budget constants are unchanged. (issue #1635, PR #1638, 2026-11-10) Box skill copy: none.
- Head branches are now deleted by the land itself, not by a later close-out call that a host may refuse as destructive. A change backend may map the conditional `change.land-delete-arg` operation, the argument that makes a land also delete the head branch; GitHub maps it to `--delete-branch`. With it, the sync tmux and session synthesizer briefs add it to the land only for a same-repository head that is neither the default nor the base branch, and `mdstack train land` adds it to each member's merge under the same check in code. A fork, default, base or unreadable head lands without it. Each train merge record says `Head branch: deleted at merge`, `retained (<reason>)` or `delete failed (<reason>)`, and a non-zero exit after a landed merge is read back as a landed merge with a failed delete. Route's close-out still runs its guarded delete only when the branch is still there after the merge, as a fallback, and names why it kept a branch. (issue #395, PR #1636, 2026-11-10) Box skill copy: none.
- A new synthesizer policy fragment, `templates/policy/synthesizer/authority-sources.md`, states where land authority comes from: marker lines, CI, labels and the recorded `merge_grant` (its source decision, scope and the merge gate's exclusions), re-read live and pinned to the head at every land. Inbox and ref payloads, event files, PR body prose and narrative summaries name a candidate only and supply no approval or permission, and a post never creates a grant. The tmux synthesizer lead (the long-lived lander) and the session synthesizer brief include it; `docs/runtimes/tmux.md` (Synthesizer lead) carries the same rule. The shared merge gate and the tmux synthesizer land procedure are unchanged, which keeps that brief inside its size budget headroom. New `docs/roles.md` section Grant references in posts: coordinator and synthesizer posts link the recorded grant decision instead of restating the permission, and the tmux coordinator brief points to it. Render cases cover a profile with and without a recorded grant. The fresh-window design in the original issue is superseded by the long-lived lead (#1569). No gate, marker or merge rule changes. (issue #314, PR #1632, 2026-11-10) Box skill copy: none.
- Evidence and role contracts (M42 B1). Typed evidence now asks for a negative control for each new or changed guard: the guard fails on a mutated copy or the nearest wrong input, then passes at head, as a fail-then-pass pair in the CLI adapter. Missing, it is `disagrees` under `evidence = typed` and a soft finding under `inline`; a test-only guard change is no longer exempt, and a change with no guard keeps a reasoned N/A (#1604). A new Claim scope section in `docs/verification.md` bounds a claim to the read behind it (#423), asks for schema/code equivalence cases on a changed validator (#424) and proves a changed fail-closed tool through its shipped entry point with a nonzero exit on rejection (#373). Protocol §6 names the backend read head as a change's one authoritative revision: the builder reads it back after each push for markers and evidence, and each review, validate, gate or land pass pins its reads to one head (#377, #376). Worker briefs must cite framework docs readable on the worker's host at the pin, or block with `spec-unreadable` (#375), keep required reporting writes apart from commands under test (#378), and take rigor only from flavor records and path classes; the coordinator raises rigor through an item record, never a hand-written brief floor (#745). The builder, reviewer and coordinator briefs carry short pointers to these rules; no marker format, cap or label changes. (issue #1604, PR #1609, 2026-11-10) Box skill copy: none.

### Fixed

- `mdstack up` on a tmux crew whose session already runs now ensures the enabled leads and lifecycle floors instead of returning at "already running", so an incoming runtime that ran `mdstack up` before its handoff ack (window 0 only, leads refused while read-only) gets its builder, reviewer and synthesizer leads from the `mdstack up` it runs after the ack and holds. `lead.ensure` keeps its ownership gate and is a no-op for a live lead, so a repeated up starts no duplicate, and `--coordinator-only` and `launch.roles` other than `tmux` are still respected. `docs/handoff.md` resume step 6 and the tmux return path now name that post-ack `mdstack up`. (issue #1082, PR #1651, 2026-11-10) Box skill copy: none.
- The tmux adapter's `new_session()` now confirms the session exists after `tmux new-session` returns and raises otherwise. tmux can print `error creating …` and still exit 0, which left the remote runner beating with no session and `version` reporting `runner: down` indefinitely. The runner now stops with that error instead of writing `runner.json`. #1487's creation of the default socket directory (mode 0700) is unchanged. (issue #1480, PR #1650, 2026-11-10) Box skill copy: none.
- `mdstack upgrade --yes` now applies on a host whose role windows run under a launcher wrapper. Its in-flight wait counted any live child process under a role pane as a running pass, so an idle window whose wrapper keeps the native harness and MCP servers alive read as busy until `--wait-timeout`, and the upgrade exited without writing the install. A window whose harness adapter declares a composer glyph (Claude Code, Codex) is now judged by its screen whatever processes live under the pane: it is idle only when a row opens with that glyph, no mid-turn text or blocking dialog shows and no unsubmitted `inbox:` nudge sits on the composer, besides the existing status and inbox checks (now also an unacknowledged inbox message after a run's `done:`). A message whose `mdstack send` nudge was never submitted (exit 4, for example into a dialog) is now recorded in `inbox/<window>.undelivered`, and the upgrade waits on it until the window acks it or the operator clears the file, so a coordinator message stays pending after the dialog clears. Other adapters keep the live-child rule. A mid-turn, dialog, empty or unrecognized screen, or a failed process probe, still counts as busy, and the timeout message names the reason, for example `in-flight pass ash: no idle prompt on screen`. (issue #1618, PR #1637, 2026-11-10) Box skill copy: none.
- A reviewer pass now keeps its rereview identity across a clean restart and the spawn queue: `mdstack spawn` takes `--rereview-id` (reviewer only, with `--pr` and `--head`) and writes it into the run record before the harness starts, a queued request carries it to `mdstack dequeue`, and a clean `mdstack restart` passes it with the run's head, so a moved head refuses as stale instead of inheriting the old steer. The reviewer route hands the steer to spawn instead of patching the record afterwards, so a restart after a session loss no longer opens a duplicate same-head review and round-cap escalation. (issue #1477, PR #1634, 2026-11-10) Box skill copy: none.
- A crew PR that turns `CONFLICTING` now reaches a builder without waiting for CI or a coordinator sweep: GitHub runs no `pull_request` CI on a conflicting PR, so approved PRs that conflicted after another land stalled with no checks. `mdstack poll` keeps each PR's last known mergeability and emits one `pr-conflicting` wake per head and conflict (an `UNKNOWN` read is no conflict and changes nothing), and `mdstack route` re-reads the PR and hands the builder lead one `merge-up` handoff, which the builder resolves with the existing merge-up note and delta review. A closed PR, moved head or resolved conflict consumes the wake; held, escalated, solo or lead-less work stays with the coordinator; a conflict that clears and returns hands off again. (issue #1398, PR #1631, 2026-11-10) Box skill copy: none.
- The watcher's backstop no longer wakes the coordinator every 30 minutes while only held or owner-blocked work is open. `mdstack poll` records `held` in `poll-state.json` (open crew PRs and `crew:ready` issues labelled `crew:hold`, `crew:escalated` or `crew:needs-md`, and the issues such a PR closes). When every recorded run's item is in that list or has an open `asks/<n>.json`, and no lead has pending work, `mdstack watch` waits its idle cap (16 × the stale-sweep period, at least 4 h) instead of the short backstop. A run that is live, unrelated or unclassified, or a pending lead message, keeps the 30-minute backstop. Each scan recomputes the decision both ways, so work that becomes held extends the wait and live work restores the short backstop. When the owner lifts a hold from an open item, `mdstack poll` emits one `hold-released` record and the coordinator is woken at once (the coordinator brief resumes the item); for held items and items with an open ask only, a new owner comment or PR review emits one `owner-answer` record while the hold and the ask stay. Ask-deadline and other poll wakes are unchanged. (issue #394, PR #1628, 2026-11-10) Box skill copy: none.
- `mdstack upgrade` now adopts a running user-level install that has no `install.json`, such as one set up by `mdstack install`, `layout --write` and `up`. It first checks the `paths.mdstack` link, the release `VERSION` beside a `releases/current` link and the state's `config.toml` copy, then writes the record and upgrades. Before this, it refused with "run mdstack bootstrap first", and bootstrap then refused the same install. An install that does not verify is refused, and the refusal names the mismatch. `mdstack doctor --fix` now resets a `crew:*` runbook label's color and description instead of failing the labels check when no install record owns it. Only an extra `crew:*` name still collides. (issue #1616, PR #1626, 2026-11-10) Box skill copy: none.
- The builder lead's 60-second admission backstop no longer re-types an acknowledged, deferred handoff into the lead window on every poll. `mdstack lead report builder REASON REF... --id ID` records the handoff's inbox id on its `deferred:` status line; the backstop then re-runs the scheduler walk, persisting only the target's progression so a throttled target recovers, and nudges only when that ref is admissible. Slot releases and the coordinator backstop still nudge it, an unacknowledged or unreported id keeps the normal retry, and the handoff stays pending demand until a worker record exists. (issue #1502, PR #1624, 2026-11-10) Box skill copy: none.
- `mdstack route` now consumes obsolete recovery wakes instead of waking the coordinator. A `blocked:` line from a lead or a gone run is consumed when every item it names is closed or merged, or when its pinned PR head or review round is superseded. An open issue, the current head, an untyped line (such as `blocked: main red after #N`), a live worker's block or an unreadable item still reaches the coordinator. An idle builder reclaim records the reclaimed run's identity, and the watcher's stale wakes now carry their run identity. A dead or missing stale wake for that same run is consumed (#1552), but a replacement run under the same window name still wakes. (issue #1476, PR #1622, 2026-11-10) Box skill copy: none.
- Each crew fetch now resolves its own result: the shared fetch helper used by `mdstack spawn`, merge trains (including the fetches between member lands) and uninstall fetches into an invocation-unique private ref (`refs/crew/fetch/<pid>-<random>`) with `--no-write-fetch-head`, an empty `--refmap` and `--no-tags`, resolves that ref and deletes it. Concurrent builder, reviewer, train and spawn fetches in one checkout therefore no longer read each other's `FETCH_HEAD` (a reviewer spawn refused as stale against main's head, #1367) or race on `refs/remotes/origin/*` (`incorrect old value provided`, which stopped a train, #1584). A real fetch failure still fails, and a changed PR head still refuses a stale spawn. (issue #1367, PR #1621, 2026-11-10) Box skill copy: none.
- The tmux watcher no longer depends on a coordinator turn ending cleanly. `mdstack up` (and `mdstack upgrade`, after its reload) now starts a persistent, token-free watcher in its own session (`mdstack watch --persistent --detach`, output in `wake/watcher.log`). It nudges the coordinator and keeps scanning instead of exiting, and nudges again while `wake/queue.jsonl` stays undrained, so polling, routing and ask-deadline wakes continue after a model-gateway error without an owner re-arm; a fatal API error over the coordinator's idle composer still gets the wake line, which only a real approval prompt withholds. One watcher runs per state dir: it holds `wake/watcher.lock` for its whole life, code-change re-execs included, so a second or simultaneous start exits 0 naming the armed PID; PID-file cleanup stays PID-checked. `mdstack guard` names a live watcher whose PID file is missing instead of blocking, and `mdstack down` and `mdstack upgrade` stop the watcher first (found through the lock when its PID file is lost; an unidentified holder is refused, never signalled), `down` even with no session left. `CREW_WATCHER=off` keeps the coordinator-armed one-shot watcher (#399). (issue #1346, PR #1620, 2026-11-10) Box skill copy: none.
- A passing verdict after a changes round no longer leaves `crew:changes` on the PR for the synthesizer to refuse the land on (#1464, #1483). Before `mdstack route` forwards `review-approved` or an approved `ci-passed` to the synthesizer lead, it sets `crew:approved`, removes a superseded `crew:changes` or `crew:in-review` and reads the tags back, but only for a passing verdict at head from this runtime's reviewer (its login and signature). A failed readback keeps the event queued for the coordinator, and a replayed approval edits nothing. A stale, foreign or later changes verdict, a later formal changes request, an open rereview, a hold or an escalation leaves the tags alone, and the land gate still blocks on `crew:changes`. (issue #1464, PR #1619, 2026-11-10) Box skill copy: none.
- `mdstack migrate` accepts a team reference `<file>#<repo>` for `--project` and `--to`: it previously opened the reference as a literal path (`FileNotFoundError`) and used the team file's directory as the git checkout. It now splits the reference, rewrites the team file itself, checks the repo section's declared `checkout`, so a team file outside every clone relocates, and leaves a sibling repo's state folder and `[repos.<name>]` section untouched. Operational records keep the `#<repo>` suffix, and the printed next steps name the new reference. The live-session, land-lock and existing-destination refusals are unchanged. (issue #1347, PR #1608, 2026-11-10) Box skill copy: none.

### Security

- Coordinator briefs (tmux, session and the Grok Bot routines) now include a
  secret-retrieval rule: never suggest a command that prints a secret value,
  since output the owner runs through a harness shell passthrough such as `!`
  enters the transcript. Coordinators give a clipboard pipe or the revealing UI
  instead and verify by fingerprint, length or last 4 characters. The bootstrap
  design's secrets table records the rule. (issue #397, PR #1629, 2026-11-10) Box skill copy: none.

## [7.6.0] - 2026-11-10

### Added

- Release 7.6.0: session-runtime and org-pack parity (M40). A session crew now runs the same pipeline as tmux. `mdstack upgrade` runs on a session profile (#1541), `mdstack bootstrap` passes its `briefs` self-test there (#1540), the session synthesizer brief carries gate-status reporting and verdict portability again (#1539), session profiles accept `runtime.options.release_delegation` (#1542), and an async land binding lands through `mdstack land request` (#1351). `runtime.options.session_backend = "hosted"` runs workers as hosted sessions created through a control plane (#1052), a session crew can run always-on triage, including on a non-GitHub tracker (#1404), and `runtime.options.role_runtime` adopts a runtime one role at a time (#1055). Hosts: an inventory host can carry its DNS name as `[hosts.<name>] address` (#1034), `mdstack host prepare` supports a checkout made by a declared command (#1035), and `mdstack connect <alias> [session]` opens the owner's shell on a host (#1036). For org packs: the release bundle ships `scripts/changelog-cut.py` (#1033), `precheck-scope` classifies removed and renamed paths (#1345), and `resolve` prints a `pack.toml` pack's version again (#1350). Crew runtime: `mdstack doctor` and `mdstack up` preflight the launcher sandbox and `mdstack restart` relaunches the coordinator in place (#1544), route wakes the coordinator on a milestone-closing or release-cut merge (#1559), role posts end with a usage line of time, tokens and model (#1557), and the tmux synthesizer is a long-lived lead in window 1 that takes land events straight from route (#1569). No breaking changes; upgrade a 7.5.0 install with `mdstack upgrade --version v7.6.0`, after which the watcher or the next `mdstack up` starts the synthesizer lead, and `mdstack spawn synthesizer` refuses. (issue #1598, PR #1600, 2026-11-10) Box skill copy: none.
- Role posts that report a pass now end with a usage line just above the signature, for example `Run: 23m 10s · 1.24M in (1.1M cached) / 38.2k out · claude-opus-5-5 (high)`. New `scripts/run-usage.py` prints it from a run record (or `--engine`, `--dir` and `--start` for the coordinator): wall-clock time from the run start to now, token totals and the model. Harness adapters gain an optional `usage(directory, start)` reader of their local session log; Claude Code (transcript JSONL, each streamed message counted once, cache reads as cached) and Codex (cumulative `token_count` events, less any total before the start) ship one, and any other harness prints `tokens n/a`, never an estimate. A new shared fragment `templates/policy/shared/usage-line.md` puts the instruction in the tmux and session builder and reviewer briefs and the session synthesizer and coordinator briefs; the tmux coordinator, synthesizer and researcher briefs, at their size budget, carry a one-line pointer to the `docs/roles.md` rule, and the researcher's reflection report format carries the line inline. An unreadable log also prints `tokens n/a`. The figures are informational only: no gate, verdict, flavor or scheduler decision reads them, markers, signatures and effort attribution are unchanged, and no path or credential is printed. `docs/roles.md` (new Usage line section) and `docs/flavors.md` record the owner's reversal of "off the record" for role posts. (issue #1557, PR #1592, 2026-11-09) Box skill copy: none.
- The session runtime now has an async land binding: `resolve` accepts `land.mode = "async"` with its change placeholder and `[land.status]` map under `runtime.name = "session"`, `mdstack land request|resume|done` run on a session profile, and the rendered session synthesizer brief's step 3 lands through `mdstack land request`, which polls the declared status map within `land_timeout` and refuses on `failed`, a stale head or an unknown status. Sync session renders and every tmux render are unchanged. (issue #1351, PR #1591, 2026-11-10) Box skill copy: none.
- A session crew can run always-on triage. `mdstack poll --triage-only` runs one triage scan on a tmux or session profile. A non-GitHub tracker backend is scanned through its `tracker.list-items` binding (never `gh`), once per id in the new `[triage] trackers` key. `crew-render` writes a session researcher sweep brief that carries the tmux Triage sweep policy, now a shared policy fragment. The session runtime accepts `runtime.options.researchers`. `docs/runtimes/session.md` documents the hosted `triage-sweep` routine trigger: its schedule comes from `triage.interval_hours`, an empty queue skips the run, and the run prompt names the routine file and skill. tmux behaviour is unchanged. (issue #1404, PR #1590, 2026-11-10) Box skill copy: none.
- An inventory host can now carry its reachable DNS name: optional `[hosts.<name>] address` (a dotted DNS name such as `host-a.region.example.com`; no IP literal, `user@` or `:port`) beside the short label, which stays the stable key for placement, run records and `mdstack host check <name>`. `mdstack host check` and `host prepare`, role runs on the host (spawn, probe, kill, pull, send, attach) and `mdstack runner` jobs all connect to the address; a host without one still connects to its label, so existing profiles are unchanged. `core/crew-config.py validate` refuses an address that is not a dotted DNS name. (issue #1034, PR #1589, 2026-11-10) Box skill copy: none.
- The session runtime's `runtime.options.session_backend` accepts `hosted` for workers that are hosted sessions created through a control plane, addressed by the returned session id and probed by a control-plane state read. A hosted profile's coordinator and worker briefs render that dispatch and liveness text with no subagent, task-handle or PID language, through new `<session-backend:hosted>` and `<session-backend:local>` template blocks; `native` and `cli` profiles render byte-identically to before. (issue #1052, PR #1588, 2026-11-10) Box skill copy: none.
- `mdstack connect <alias> [session]` opens the owner's own shell on an inventory host from any machine with the profile: with a session it runs `tmux new-session -A -s <session>` there (create or reattach), without one a plain login shell. The alias is the host name or `hosts.<name>.connect.alias`; the transport (`ssh`, `mosh` or `et`), proxy command and fixed options are profile data under `hosts.<name>.connect`, and arguments after `--` pass through to the transport. An unknown alias lists the known ones and exits 1. Docs: [Connect to a host](docs/runtimes/multi-device.md#connect-to-a-host). (issue #1036, PR #1587, 2026-11-10) Box skill copy: none.
- `runtime.options.role_runtime` (tmux and session) renders one role's brief from another runtime's templates, so a crew can adopt a runtime one role at a time, for example the session coordinator alongside tmux workers. The render swaps that role's registry template for `templates/runtimes/<runtime>/<role>.md` and fails closed on an unknown role, the selected runtime itself or a missing template; profiles without the key render byte-identically. (issue #1055, PR #1586, 2026-11-10) Box skill copy: none.
- `mdstack host prepare` supports a host whose project checkout is made by a declared command instead of a git mirror: with `hosts.<name>.checkout = "command"`, the host runs the argv it declares in `<root>/checkout/<owner>__<repo>.json` (no shell, checked exit, never sent over SSH), requires the declared path to exist, then makes its worktree and state directories and installs the toolkit as before. `mdstack host check` reports such a host ready once the command has run, through a `project checkout` row in place of `project mirror`. Mirror-based hosts send and check exactly what they did before. (issue #1035, PR #1576, 2026-11-10) Box skill copy: none.

### Changed

- The tmux synthesizer is now a long-lived lead. `mdstack up` starts it in window 1 next to the builder and reviewer leads, and the watcher supervises and restarts it the same way. `mdstack route` hands `review-approved`, `selfgate-passed`, `ci-passed` with an approval or self-gate pass at head, and approved `merge-up` events straight to its durable inbox, which is its land queue. Every §7 gate is still checked live before each land. Route still does merged-PR close-out and now also queues the away-only Slack land message and hands ready `Depends on` dependents to the builder lead, and the coordinator is woken only for exceptions: owner merge-ok, `crew:sensitive`, holds, `main red` and lead faults. With the lead installed, `mdstack spawn synthesizer` refuses, and the coordinator recovers a land with `mdstack lead handoff synthesizer land`. (issue #1569, PR #1596, 2026-11-10) Box skill copy: none.
- `scripts/changelog-cut.py` now ships in the release bundle as a Deliverable, so a pack on a host with only the installed bundle can run the `release.cut` binding without a clone of mdstack. `docs/release.md` names the bundled command, and `test-release-bundle.py` cuts a scratch pack's changelog with the script taken from a freshly built bundle. (issue #1033, PR #1574, 2026-11-09) Box skill copy: none.

### Fixed

- Session profiles (`runtime.name = "session"`) now accept `runtime.options.release_delegation` instead of refusing it as an unknown key, so `crew-config.py resolve` and `crew-render.py` no longer exit 1 on an owner's recorded release delegation (#1435 parity). The session coordinator brief renders it in the same `Cut go:` line as the tmux coordinator brief, `none` when absent. The link check and the pack refusal apply as on tmux; tmux behaviour is unchanged. (issue #1542, PR #1581, 2026-11-09) Box skill copy: none.
- `mdstack doctor` gains a tmux `sandbox` row, and `mdstack up` (and `mdstack up <role>`) refuse before starting any window, when a launcher sandboxes sessions with no writable root over the checkout's `.git` and neither `runtime.options.sandbox_env` nor `CREW_SANDBOX_ENV` is set: a create-and-remove probe in that `.git` is denied, or a used engine's harness adapter declares `sandbox_roots(values)` that do not cover it. The one-line fix names `runtime.options.sandbox_env`. `mdstack restart <coordinator-window> [--resume <id>]` relaunches the live coordinator in place with the current `sandbox_env` and `CREW_*` environment, resuming its conversation, and refuses while the land lock is held or when run from window 0 itself. (issue #1544, PR #1580, 2026-11-10) Box skill copy: none.
- `mdstack route` now keeps a merged PR's `pr-merged` wake queued for the coordinator, noted `milestone-complete`, when the merge closes the last open item of an active milestone or is a release cut (its `CHANGELOG.md` diff adds a version heading). The coordinator then closes the milestone and admits the next one at once instead of waiting for the owner. Other merged close-outs stay mechanical. (issue #1559, PR #1577, 2026-11-09) Box skill copy: none.
- `crew-config.py precheck-scope` now classifies a changed path that is absent from the worktree at head (a deletion or a rename source) as `removed`: it gets no owners query and no targets and never counts as unowned, so a pure directory move runs the destinations' targets and a deletion-only change is `tests: n/a` instead of failing with exit 3. The output gains a `removed` list, and the builder brief's pre-review step 3 says to pipe every changed path from the worktree at head. (issue #1345, PR #1573, 2026-11-09) Box skill copy: none.
- `mdstack upgrade` now runs on a session-runtime profile: it previews and applies the re-render to `paths.live_dir` (and fetches with `--version` or `--latest`) without the tmux in-flight wait or window reload, then says to restart the coordinator with `mdstack up`. `mdstack bootstrap` on a session profile no longer fails its `briefs` self-test, which looked for the Grok Bot brief names instead of the session runtime's tmux-named briefs. tmux upgrades are unchanged. (issue #1541, PR #1572, 2026-11-09) Box skill copy: none.
- The session synthesizer brief carries gate-status reporting and the verdict-portability line again. Both were dropped when #1041 inlined the land rules, while the shared merge gate still pointed "below" to them. They now live in one fragment, `templates/policy/synthesizer/gate-status.md`, that the tmux and session briefs both include. The tmux render is unchanged, and a render test pins the session brief. (issue #1539, PR #1571, 2026-11-09) Box skill copy: none.
- `mdstack bootstrap` on a session profile (`runtime.name = "session"`) no longer fails its `briefs` self-test: the check now looks for the session runtime's own `runtime/<role>.md` briefs instead of the Grok Bot names (`runtime/builder-b1.md` and others) it used for every runtime but tmux. The Grok Bot "Create the routines" human step is printed only for `grok-bot`; a session install prints `Run mdstack up --project <file>`, which starts its coordinator. tmux and grok-bot behaviour is unchanged. (issue #1540, PR #1570, 2026-11-09) Box skill copy: none.
- `crew-config.py resolve` prints `pack.version = "<version>"  # pack:<name>` for a wired `pack.toml` pack again, read from its `[pack] version`, so a pack that moved from a config-only manifest to the plug-in tree keeps its release identity in the resolution output. An external manifest's version still takes precedence and prints as before; a pack with no version prints nothing. (issue #1350, PR #1568, 2026-11-10) Box skill copy: none.

## [7.5.0] - 2026-11-10

### Added

- Release 7.5.0: periodic reflection over learnings (M39). The protocol now reflects on its own record and proposes fixes, without approving them itself. The reflection contract and authority boundary in `docs/self-improve.md` (#1517), the deterministic evidence scan `scripts/reflection-scan.py` (#1518) and the effect measures `scripts/reflection-measures.py` (#1524) shipped in 7.4.0; this release completes the loop. The researcher's `protocol-reflection` procedure posts one ranked, evidence-linked report per window (#1519), run as `mdstack spawn researcher --reflection` with its run ID, log issue, input SHA and window carried through the cap queue, dequeue and restart (#1520). Opt-in `[reflection] enabled` schedules a weekly reflection and one per closed milestone, and `mdstack reflection` prints the ledger (#1521). `scripts/reflection-candidates.py` files recurring-pattern cards with Decision `pending`, never approving them (#1522). The coordinator relays one digest per report, records each decision, and turns accepted proposals into normal build issues (#1523). `scripts/reflection-effects.py` evaluates every accepted proposal in later reports and recommends keep, revise or revert (#1525). Also in this release: on a session profile `mdstack up` starts (or attaches to) the interactive coordinator instead of refusing it as not tmux (#1548), and campaign scenario A29 drives the handoff round trip between two full teams (#1441). No breaking changes; upgrade a 7.4.0 install with `mdstack upgrade --version v7.5.0`. Reflection stays off until a profile sets `[reflection] enabled = true`. (issue #1543, PR #1558, 2026-11-10) Box skill copy: none.
- Reflection reports now evaluate every accepted proposal (#1403 R9). New `scripts/reflection-effects.py` joins the proposal, issue and merged PR chain from the coordinator's reflection-decision comments with the effect ledger and measures of `reflection-measures.py`. Each proposal gets one row: activation, its effect measure before and after, sample sizes, the repo and class cohort, missing data, status and the next evaluation date. Before and after are equal-length windows (the baseline's 14 days), both computed from inputs limited to the proposal's repos and Failure class, and each side shows its sample coverage. A row stays pending until the change is merged, activated and a whole window has passed, and insufficient when the inputs cannot place rows in the cohort, under 3 PRs on a side or with unknown counter coverage. An evaluated row recommends keep, revise or revert, never claiming a cause and reverting nothing. The researcher's `protocol-reflection` procedure attaches the table as an Effects section of each report, and `docs/metrics/decisions.md` points to it without changing any metrics-gate threshold. (issue #1525, PR #1556, 2026-11-09) Box skill copy: none.
- Reflection reports now reach the owner and become build work through the coordinator (#1403 R7). A new coordinator `protocol-reflection` skill relays one digest per report, only its top three proposals with links and recommended defaults, and an unanswered digest changes nothing. Each accept, reject or correction is recorded explicitly in a `reflection-decision` comment on the reflection log issue, which the researcher's cooldown now reads. An accepted proposal becomes one normal issue per independent deliverable, reusing an open issue that covers it, with acceptance criteria, exact paths, the source proposal and an effect measure; protocol, template, gate, spec and profile-default changes are marked for the owner's per-change merge-ok. Memory, profile and pack findings route to their owners. `docs/self-improve.md` gains a Coordinator handoff subsection and the tmux coordinator brief points to the skill. (issue #1523, PR #1554, 2026-11-09) Box skill copy: none.
- Opt-in `[reflection] enabled` (default `false`) schedules protocol reflections. The researcher's new `protocol-reflection` routine makes the last full ISO week pending each Monday, and `mdstack watch` makes a milestone's window pending at once when it closes, independent of `[triage]` and its milestone ledger. Pending windows coalesce into one `mdstack spawn researcher --reflection` run at a time. The ledger in `reflection/ledger.json` survives sleep and a full researcher pool. Only the posted `pass=reflection` report completes a window. A failed start retries under the same run ID without a second queue entry, and a missed week catches up once. `mdstack reflection` prints the ledger. (issue #1521, PR #1553, 2026-11-09) Box skill copy: none.
- `mdstack up` accepts a session profile (`runtime.name = "session"`) instead of refusing it as "not tmux": it starts only the interactive coordinator, in window 0 of the tmux session `runtime.options.session` (default `crew-<owner>-<repo>`), launched by its harness adapter with `CREW_ROLE=coordinator`, `CREW_PROJECT`, `CREW_STATE` and the rendered `runtime/coordinator.md` brief, and opens no role windows, so workers stay dispatched per pass. A running session prints its attach line instead. Session profiles now accept `runtime.options.session`, `permission_mode` and `launch` (`coordinator`, `resume`). A new `mdstack up --resume <id>` flag overrides `launch.resume` for one run, on tmux too. Other tmux behaviour is unchanged. (issue #1548, PR #1549, 2026-11-09) Box skill copy: none.
- `mdstack spawn researcher --reflection WINDOW [--log N] [--input-sha SHA] [--run-id ID]` starts a reflection run, riley-reflection, in a fresh worktree at the input SHA, under the existing researcher cap. Its run ID, reflection log issue, input SHA and window are fixed at the request and carried intact through the cap queue, `mdstack dequeue` and `mdstack restart`. Restart first rechecks the log for a posted report covering the window and refuses when one is there. A `done: reflection <window> <url>` completion puts the report URL on the wake relayed to the coordinator, and reaps only the run for that window. Combining it with `--issue`, `--pr`, `--sweep`, `--docs-pass` or `--train` is refused. (issue #1520, PR #1547, 2026-11-09) Box skill copy: none.
- Reflection now files recurring-pattern cards without approving them (#1403 R6). New `scripts/reflection-candidates.py` reads `reflection-scan.py`'s evidence index, the forge snapshots and the findings buffer offline. It selects findings rows at count 3 or more and classes with 3 or more distinct incidents in the window. A fixed or applied row, or a pattern whose card closed, gives no new work without an occurrence after the fix. It matches open and closed work by proposal prefix, Failure class and batch issue, and answers `file`, `append`, `none` or `skip`. The researcher's `protocol-reflection` procedure gains a threshold-card step: it files an unchanged intake card with Decision `pending` inside the report cap and cooldown, or appends the new evidence. It rechecks before each post so a retried run reconciles a card it already filed, and it never edits the buffer, readiness labels or milestones. `docs/self-improve.md` points the threshold paragraph at both. (issue #1522, PR #1546, 2026-11-09) Box skill copy: none.
- The researcher gains a `protocol-reflection` procedure (`templates/policy/researcher/skills/protocol-reflection/SKILL.md`) for #1403's reflection loop: it reads `reflection-scan.py`'s evidence index and the sources it cites as data, searches existing work and owner decisions first, applies the rejection cooldown and the 3-new-proposal cap inside triage's noise cap, and posts one signed report on the `reflection:log` issue with stable-ID proposals (exact targets, correction layer, incident count, measured impact or `unknown`, rank reason, recommended default), a top-three digest and gaps. It rechecks ownership and the `pass=reflection` completion marker before posting, and a signed coordinator request runs it by hand before any schedule exists. The tmux researcher brief points to it, and a sample report fixture for the scan test's window is checked against the index. (issue #1519, PR #1529, 2026-11-09) Box skill copy: none.
- Campaign scenario A29 runs the handoff round trip between two full teams (#213, #157). `dev/tests/scripts/fixtures/campaign/a28/teams.py --handoff` seeds the fake forge from `a29/handoff.py` with team a's claim, a dependency set, a change in review, a pending owner ask and a backlog item. Team b, which does not own the repo, starts read-only with only its coordinator. Once both teams are ready, the driver runs the real `mdstack handoff` commands a → b in drain mode and b → a in stop mode, and starts the new owner's whole team each way. The run fails unless the control item holds each state once per handoff id with exactly one ack, exactly one team (or none in transit) may write after every step, each `stopped` post finds the outgoing session gone, both manifests hold the same sets, stages and heads, the kept run is named, and nothing else was posted on or written to the forge. `docs/handoff.md` states the owner assumption and replaces the 21.5 row's Grok Bot example with the two-team environment. (issue #1441, PR #1504, 2026-11-09) Box skill copy: none.

## [7.4.0] - 2026-11-09

### Added

- Release 7.4.0: portable installs honor their declared contracts (M38). Portable installs: a pack outside a git checkout passes the install pin through its `pack.toml` `[vcs]` `clean` and `commit` commands (#1326), a backend map's `[ids]` admits `marker_key` and carries it into the resolved ids (#1031), and `mdstack doctor` checks `gh` only when a concern binds the `github` backend or the release source is `github`, so an all-own-backend pack bootstraps with no `gh` (#1123); this completes the pack floor scan scope (#1325) and git-free evidence provenance (#1330) that shipped in 7.3.0. Session runtime parity: the session synthesizer lands each ready PR alone instead of copying the tmux train recipe (#1041), owner-present caps `present_builders` and `present_reviewers` (#1053), `researchers = 0` as a no-op (#1057), and `mdstack host check` and `host prepare` for a session profile (#1122). Render checks and headroom: a render note for a role the runtime does not render fails the render (#1054), and `crew-render` reports each brief's `size_budget` headroom and warns within 5% of it (#1056). Release safety: a cut PR can no longer land on a stale merge ref, and fragment PRs hold while a cut is open (#1433), and the owner can record a standing release delegation for cut PRs (#1435). M39's first pieces (R1, R2, R8): `docs/self-improve.md` defines the reflection contract and authority boundary (#1517), `scripts/reflection-scan.py` builds a deterministic reflection evidence index (#1518), and reflection effect measures with `scripts/reflection-measures.py` (#1524). Also in this release: the two-host dry run recorded as met on a simulated host (#209). No breaking changes; upgrade a 7.3.0 install with `mdstack upgrade --version v7.4.0`. One check is stricter: a profile with a `runtime.options.notes.render.<role>` entry for a role its runtime renders no brief for (for example `researcher` under `session`) now fails `crew-render` naming the key; remove that entry before upgrading. (issue #1530, PR #1532, 2026-11-09) Box skill copy: none.
- Added reflection effect measures (#1524). `mdstack poll` now records a sanitized ready sample per crew PR when its head, CI, verdict, mergeable state or hold changes, with the previous poll time as its sampling bound, and `mdstack watch` records one stall per new stale wake, closed by the run's next status line; both go to `metrics/observations.jsonl` in the state dir. The new offline `scripts/reflection-measures.py` joins these samples with the metrics CSV and explicitly confirmed false-throttle incidents to report verdict and CI-fix rounds per PR, observed ready-to-land minutes, unioned stall minutes and the false-throttle count, each with refs and coverage; missing history stays unknown and unconfirmed errors stay unclassified. Its ledger keeps each proposal's merge ref and confirmed activation, and saves a baseline only before activation. Operational ready is a sampled measure, never merge authorization. (issue #1524, PR #1528, 2026-11-09) Box skill copy: none.
- `docs/self-improve.md` gains a Reflection section, the contract for #1403's reflection loop: weekly and milestone-close windows, stable incident and proposal IDs, one ranked evidence-linked report per run with at most 3 new proposals inside triage's 10-per-day noise cap, rejection cooldowns from the triage reasons, and a `pass=reflection` completion note that is never a verdict or gate. The researcher may post reports and pending threshold cards only; the coordinator owns acceptance, disposition and one owner digest per report. `docs/protocol.md` §4 defines the marker, and `docs/triage.md`, `docs/roles.md` and the tmux researcher and coordinator briefs carry short pointers. Nothing runs a reflection yet. (issue #1517, PR #1527, 2026-11-09) Box skill copy: none.
- `scripts/reflection-scan.py` builds a deterministic JSON evidence index for a reflection window (M39 R2). Offline, it reads forge snapshots, the lessons and findings buffer at a named SHA, owner decisions and sanitized runtime observations. It selects every issue or PR opened, closed or corrected in the window whatever its placement, and keeps older linked lessons as context. One incident per card and fix chain, and one per class and site however many cards report it, keyed by `triage-clusters.py`'s own keys; triage stays open-only. Evidence stays `reported`, `confirmed` or `superseded`, and a missing input is listed and null, never zero. (issue #1518, PR #1526, 2026-11-09) Box skill copy: none.
- A recorded standing release delegation: the owner can set `runtime.options.release_delegation` once to their recorded words with a `https://` link, instead of replying in chat for every cut. While it is set, the coordinator's head-pinned merge-ok on a release cut PR (`cmd-id=release-delegation`), citing the delegation, satisfies the synthesizer's §7 cut check and `release.approve-check`. The default `none` keeps today's per-cut owner merge-ok. A pack cannot set the key, and a set value must carry a link. The `RELEASE_OWNER` actor check, CI, release validation, holds and `crew:sensitive` are unchanged; a sensitive cut still needs the owner's own words. `docs/release.md`, the release gate registry row and the runtime options table describe it; the tmux coordinator brief renders the key and point to `docs/release.md`. (issue #1435, PR #1516, 2026-11-09) Box skill copy: deferred to #140 (profile mirror_deferral).
- The `session` runtime now accepts `runtime.options.present_builders` and `present_reviewers`, the owner-present admission limits that were tmux-only. They default to the full `builders` and `reviewers` caps, a value above the full cap is refused, and the session coordinator brief renders them. tmux behaviour is unchanged. (issue #1053, PR #1514, 2026-11-09) Box skill copy: none.
- `crew-render` now prints, after a successful render, one stderr line per role brief with its path-normalized bytes against its `[size_budget]` (the measure bootstrap's self-test checks) and its delivered bytes, which add core memory and render notes. It warns when a brief is within 5% of its budget or over it, so a pack sees template growth before a release breaks its render. Written paths on stdout and exit codes are unchanged. (issue #1056, PR #1512, 2026-11-09) Box skill copy: none.
- A `pack.toml` pack whose directory is not a git checkout, such as a subdirectory of a monorepo served by another version control tool, can now pass the install pin: an optional `[vcs]` table declares a `clean` command (exits 0 and prints nothing when the working copy is clean) and a `commit` command (prints the commit), which bootstrap and upgrade run in the pack directory instead of `git`. A failing command, an empty commit or any `clean` output still refuses the pack, and the loader checks the table's shape. Packs without `[vcs]` keep the git checks. (issue #1326, PR #1503, 2026-11-09) Box skill copy: none.

### Changed

- `mdstack host check` and `mdstack host prepare` now run for a `runtime.name = "session"` profile instead of exiting 1 with `runtime.name is session, not tmux` before any readiness row. `validate` accepts a `[hosts]` inventory on a session profile (still not `[placement]`, which only tmux spawn uses); the primary gets `mdstack doctor`'s session rows, engine login and project mirror rows with load 0, and other hosts get the same remote rows as under tmux. The shared profile guard takes the runtimes a command supports, so every other command and tmux behaviour are unchanged; `hosts`, `layout` and `upgrade` stay tmux-only. (issue #1122, PR #1513, 2026-11-09) Box skill copy: none.
- Recorded the two-host dry run (#209) as met on a simulated host. The M25.1 evidence ledger now marks #158 AC3 met and #716 case 2 recorded, both from the A30 run on lab C (PR #1492, R1), with follow-up #1493. The multi-device design lists the dry run as built and no longer as design only. Real-device proof stays with #716. (issue #209, PR #1498, 2026-11-09) Box skill copy: none.

### Fixed

- A backend map's `[ids]` table now admits `marker_key`, the documented selfgate key choice that `crew-precheck.py` reads: `"change"` (key on `pr=`) or `"item"` (key on `issue=`). `crew-config.py` validates it in every map, refusing any other value by naming the allowed ones, carries it from the change backend's map into the resolved `ids`, and `resolve` prints `ids.marker_key` with `backend-map:<name>` provenance. Previously a map declaring it failed with `ids.marker_key: unknown key`. Maps without the key resolve as before. (issue #1031, PR #1515, 2026-11-09) Box skill copy: none.
- A release cut no longer lands on a stale merge ref. `mdstack train check` gains a `release-cut` gate that blocks a cut PR (its diff adds a new version heading to the CHANGELOG) until its head contains the current default branch, so update-branch re-runs `release.yml` `validate` there and the `lone_pr_land = "direct"` waiver never takes a stale cut. While a cut PR is open, the state-permission gate in `train check` and `train land` holds every other PR that adds a `changes/unreleased/` fragment until the cut lands, and an unreadable open-PR list or CHANGELOG patch holds too (a cut whose patch is missing is blocked, never read as a non-cut). This replaces the coordinator's hand-posted `hold-until` that 7.1.0 needed and 7.2.0 lacked (main-red #1432). `docs/release.md` (Cut freeze), protocol §7 and the coordinator brief describe the rule; the `release-cut` reason itself tells the synthesizer to update-branch. (issue #1433, PR #1511, 2026-11-09) Box skill copy: deferred to #140 (profile mirror_deferral).
- A `runtime.name = "session"` profile now accepts `runtime.options.researchers = 0`, the documented no-researcher statement, instead of refusing it as an unknown key, so a profile migrated from tmux keeps it. It is a no-op: the session binding has no researcher and renders the same briefs. Any other value is refused with a message saying the session runtime has no researcher. tmux handling is unchanged. (issue #1057, PR #1510, 2026-11-09) Box skill copy: none.
- `crew-render.py` now fails when a `runtime.options.notes.render.<role>` entry names a role the selected runtime renders no brief for (for example `builder-lead` or `researcher` under `session`), naming the key and the runtime, instead of dropping the note silently. Notes for rendered roles behave as before. (issue #1054, PR #1508, 2026-11-09) Box skill copy: none.
- `mdstack doctor`, and so bootstrap's preflight and self-test, checks for `gh`, its logins and the GitHub repo checks only when a concern binds the `github` backend or the `[install]` source is `github`. A pack whose backends are all its own can now bootstrap from a staged release with no `gh` on `PATH`; doctor prints `gh not checked: no github backend or release source` instead. GitHub-bound installs still fail preflight without `gh`. (issue #1123, PR #1506, 2026-11-09) Box skill copy: none.
- The session synthesizer brief no longer copies the tmux merge-train recipe: `mdstack train` refuses a session profile, so session lands each ready PR alone, one per run, under a session land rule. The shared merge gate now resolves express with `core/crew-config.py class-flavor --express` instead of `mdstack train check`. `docs/runtimes/session.md` states that merge trains and `land.mode = "async"` are tmux-only, and a render test pins that the session brief runs no `train`, `land` or `land-lock` command. (issue #1041, PR #1505, 2026-11-09) Box skill copy: none.

## [7.3.0] - 2026-11-09

### Added

- Release 7.3.0 brings remote role sessions and the local multi-device lab (M20.1, with M25.1 integration work). Remote role sessions: `mdstack spawn` places each run with a `[hosts]` inventory (#207), and a run placed on a role host starts, is killed, restarted and stopped there with the worktree guards intact (#345). Its status lines wake the coordinator through a pulled mirror, and `mdstack send` and `acked` reach it through the host (#346). A partitioned host's runs turn `unreachable` without losing their claims, reconcile when the host returns, and can be abandoned only by the owner, leaving a tombstone (#347). `mdstack attach` and `mdstack logs` reach remote runs (#348). The local multi-device lab: a pinned base image (#1430), Docker role-host setup and teardown (lab C, #1357), `mdstack runner` scenarios with failure injection over the hardened SSH call (lab F, #1360), a per-run evidence record marked simulated (lab G, #1361) and an opt-in `lab` CI job (lab H, #1362), on top of the host OS adapters that shipped in 7.2.0 (#1358, #1359). Integration follow-ups: the attended owner-channel sleep run driver (#1463), the A28 two-full-team preflight and lifecycle for #213 (#1440, via #1478) and the A30 remote-builder journey on the lab for #209 (#1442), with the M25.1 evidence ledger that audits #157 and #158 (#1445). Evidence closures: the ledger records #158 AC3 as met on a simulated host from the A30 run (#1494), and its #716 case index links a simulated-host lab run for each of the five real-device cases (#1495); real-device proof stays with #716. Crew safety: a bare `tmux kill-*` run from a worker or lead window can no longer reach the crew's server (#1475). The main-red fix scopes the attended-run test's fake clock to its own module (#1479). Also in this release: a lone surviving train member collapses to a direct land and a `train-merge` survey gate (#1425), triage clusters (#1298), A19 installed-adapter smoke and declared-operation replay (#1439, #1443), the A31 campaign-history report (#1462), `evidence-cli.py --sha` and `--root` for a working copy git does not serve (#1330), a pack's own CI backend selection passing `crew-pack.py check` (#1325), `crew-install.py` on Python 3.11.0 to 3.11.3 (#1447), the triage P0 re-fire fix (#1093), a reason for an unreadable `mdstack feedback` answer (#1096), a route test flake (#1453) and the Pi, Cursor and Muse `BUSY`/`COMPOSER` gap (#1459). No breaking changes; upgrade a 7.2.0 install with `mdstack upgrade --version v7.3.0`. A role host authorized before this release keeps working, but `mdstack attach` to it needs its key line rewritten as `restrict,pty` (re-run the lab host's `authorize`, or edit `authorized_keys` per the multi-device role-host runbook). (issue #1489, PR #1496, 2026-11-09) Box skill copy: none.
- `scripts/evidence-cli.py` takes `--sha <full head>` and `--root <dir>`, so a capture in a working copy that git does not serve carries the real head and a root-relative cwd in its header instead of `sha unknown (not a git checkout)`. When git reports a HEAD that differs from `--sha`, the helper refuses (exit 2) rather than record the capture. Without the flags the output is unchanged. (issue #1330, PR #1499, 2026-11-09) Box skill copy: none.
- The M20.1 lab now proves the A30 remote-builder journey for #209. In the `partition` scenario, the builder that `mdstack spawn` places on the lab host has its status lines pulled into the primary's mirror, and an `mdstack send --wait-ack` reaches its pane over the hardened SSH call and gets the ack back through the mirror. With `partition` and `exact-head` both run, the evidence record adds an A30 journey section: placement, status and ack, the disconnect and reconcile, the abandon, the local comparison and the physical limits of a simulated host. `crew-lab-docker.py teardown` adds its cleanup record to each run's evidence record. (issue #1442, PR #1492, 2026-11-08) Box skill copy: none.
- Runs on a role host now survive a partition. When `mdstack watch`'s pulls to a host fail 3 scans in a row, its runs are `unreachable`: their claims stay, nothing restarts or re-places them, `mdstack status` reads `unreachable since <time>`, and once the outage is older than `--stale` one `unreachable` escalate wake goes to the coordinator. The first successful pull after it (a refused or failed reply keeps this pending) queues a `reconcile` wake with each run's probe (the missed status lines come with the pull), plus a restart wake for each run found dead or missing. An owner's `mdstack kill <window> --discard --reason` on an unreachable run posts the reason, drops the primary's records and claim and writes `tombstones/<window>.json`; when the host returns, the watcher stops that run there and keeps its worktree if it holds unlanded work. The lab `partition` scenario now places a real run with `mdstack spawn` and proves all of this through a network disconnect. (issue #347, PR #1490, 2026-11-08) Box skill copy: none.
- `mdstack attach` and `mdstack logs` now reach a run placed on a role host (multi-device observability). Attaching to a remote window, or to a role whose only run is remote, runs `ssh -t` to the host's new `attach` verb, which attaches to the run's pane in the runner session, read-only unless `--rw`. The crew key line becomes `restrict,pty`; the request travels base64url-encoded in the SSH command, and the entrypoint refuses `attach` without a TTY and every other verb with one. `mdstack attach builders` adds one pane per remote builder showing its host's `capture` reply every 15 s. `mdstack logs` prints the tail of the run's newest step summary from the host's `logs` verb, never raw logs; `-f` stays local only. The lab host's `authorize` writes the new key line, and a new lab `attach` scenario proves it over real SSH. Fixed: on a host where tmux had never run, the runner never got its tmux session, because tmux does not create the directory of a socket named by path and still exits 0. The runner now creates it. (issue #348, PR #1488, 2026-11-08) Box skill copy: none.
- Runs on a role host now wake the coordinator and take messages. Every `runtime.options.host_scan_interval` (default 15 s) `mdstack watch` makes one `pull` per role host with runs and copies new status lines into the primary's `status/<window>.status` mirror, which wakes as a local status file does. The mirror's own size is the offset and a prefix digest guards it, so an interrupted or repeated pull and a primary restart lose and double no line. `mdstack send` delivers through the host's new `send` verb (inbox line and verified nudge there; exit 1 when the host is unreachable, never queued), and `mdstack acked` and `send --wait-ack` pull before reading the ack. The lab gains a `status-pull` scenario that proves the pull through a network disconnect. (issue #346, PR #1487, 2026-11-08) Box skill copy: none.
- CI has an opt-in `lab` job for the M20.1 Linux Docker/SSH lab. It runs only on a PR labelled `lab`, on an ARM64 runner, from the base image named by the `LAB_BASE` repo variable (pinned by digest). It runs the lab setup, every runner scenario and teardown, and keeps the evidence as an artifact. Without `LAB_BASE`, Docker or ARM64 it records an explicit skip and passes. It is not a required check, and every other CI job still runs. (issue #1362, PR #1486, 2026-11-09) Box skill copy: none.
- Each M20.1 lab scenario run now writes an evidence record under `state/lab/runs/`, as JSON plus a Markdown copy to paste into a PR. The new `environments/terminal/remote/lab/crew-lab-evidence.py` writes it. The record covers the hosts, the image digest, the bundle and source hashes, the transport, every injected event and a timeline. The whole record is marked simulated and not a real device, and each Docker network control is labelled simulated. The sample checks and the partition's claim are labelled stubs. A scenario that did not run is `skipped` with `evidence: false`. (issue #1361, PR #1485, 2026-11-09) Box skill copy: none.
- Campaign scenario A28 gains a two-full-team preflight and lifecycle for the handoff round trip (#213). `campaign-sandbox.py setup --teams 2` builds a second team in the sandbox. It gets its own clone of the one origin, its own session and roots, and an `--org-profile` file that sets its `runtime.instance` and the one control item. `--engine ENGINE/MODEL` leaves that engine unstubbed for both teams. `teardown` refuses when a team's profile changed since setup or resolves a root outside the sandbox or on a production root. Otherwise it runs `mdstack down --preserve` for every team before it kills that team's session. `dev/tests/scripts/fixtures/campaign/a28/teams.py` first tears down every earlier run under its root through that run's manifest, never with a bare tmux call (#1474), and refuses a run without a valid manifest. It then checks the preflight: separate roots, sessions and runtime instances, and the same repo, control item, source, release and skills. It then starts both full teams with `mdstack up` and waits until the coordinator and each enabled lead probe alive. It tears down with both teams stopped, each team's unlanded commit retained and the sentinel unchanged. (issue #1440, PR #1478, 2026-11-08) Box skill copy: none.
- The M20.1 local lab can now run `mdstack runner` scenarios over the real hardened SSH call to its Docker hosts with `environments/terminal/remote/lab/crew-lab-scenarios.py`. The client is the staged bundle, verified with the hosts' activated digest. A23's oracles (exact head against a local run, red results, idempotent request IDs, stale and unseeded heads, a scrubbed job env) run alongside failure injection. A network disconnect and a pause mid-job fall back locally, and the job's result is pulled afterwards. A runner-only kill keeps SSH answering and passes only once a new runner beats and reports `up`, and a recreated container never reports its lost job done. A partitioned role host is unreachable, so placement queues and the claim stays. Each disconnect and pause is confirmed to break the SSH path. (issue #1360, PR #1472, 2026-11-09) Box skill copy: none.
- `scripts/campaign-attended.py` drives #804's attended run: A26 around an actual sleep of the owner's Mac, with one real sandbox Slack delivery whose receipt code the owner types after the wake. It records the before-sleep and after-resume timestamps, checks that claims, worktrees and tmux windows survive the sleep, runs A26's resume steps (missed changes and the overdue sweep caught up once) and records each owner unblock. `--dry-run` rehearses end to end with a loopback webhook and no sleep, labelled `rehearsal` and `evidence: false`. `docs/campaign-harness.md` gains the runbook: the owner's steps and timing, and the physical test boundary. A26's watcher ticks pass `--source-interval 0`, so its resume scan polls again within the 60 s source interval that #1300 added. (issue #1463, PR #1471, 2026-11-08) Box skill copy: none.
- The A31 campaign-history report reads actual campaign records (#804). `scripts/campaign-report.py capture` stores one milestone's crew PRs, closed in a window, as `metrics-refresh.py` rows, together with the decision log's `[Ash/decision]` records from that window. `report` renders the per-lane counts and denominators for the standard, express and solo lanes, the timing medians and the owner decisions. Empty lanes print `n/a`, and blank fields, a missing decision log and token counts are listed as missing. `docs/metrics/a31-campaign-report.md` is the M25 report rendered from the recorded capture, and `dev/tests/scripts/test-campaign-report.py` pins it and checks the per-PR rounds against `baseline-m25.md`. (issue #1462, PR #1468, 2026-11-08) Box skill copy: none.
- A run placed on a role host now starts there (multi-device remote run lifecycle). `mdstack spawn` sends the rendered brief, and for a validate pass the PR's review files, to the host's new `spawn` verb, which fetches the head into its mirror without moving mirror refs, adds the worktree and starts the harness in the runner's tmux session, so the run outlives the SSH call. `mdstack kill`, `restart` and `down` act through the host's `kill` and `probe` verbs and keep the worktree guards there: unlanded work is kept and listed unless the owner's discard reason is posted, a restart with unlanded work relaunches in its own worktree, and an unreachable host keeps the run's records. Lifecycle verbs refuse another primary's run. Remote runs count toward the role's pool cap and show their host's liveness in `mdstack status`; remote wakes, messages, partition handling and attach remain #346–#348. (issue #345, PR #1467, 2026-11-08) Box skill copy: none.
- Campaign scenario A19 gains an installed-adapter smoke and a live evidence ledger (#797). `dev/tests/scripts/fixtures/campaign/a19/smoke.py` runs once per installed harness and session backend binding, from an operator shell. On one disposable run it drives launch, the `mdstack send` doorbell, the inbox `ack:`, the C5 probe and the pane stop through the runtime's own code. tmux runs on a dedicated server; herdr closes only its own workspace. Each result pins the source SHA, the adapter file hashes and the harness and backend versions. A binding that is not installed, has no interactive launch or is skipped by policy is reported as blocked. The `live` section of `a19/ledger.json` names every binding and the Grok Bot mirror and watch. Each entry links to its evidence, links to a failed run and the finding filed for it, links to a block that states the installation, version, account and sandbox facts, or quotes why the binding is unsupported. `replay.py` fails a missing binding, an entry without a link, a failure without its finding or a block that leaves out one of those facts. (issue #1439, PR #1461, 2026-11-08) Box skill copy: none.
- Campaign scenario A19 replays every declared harness and session backend operation (#797). `dev/tests/scripts/fixtures/campaign/a19/replay.py` discovers the shipped adapters and reads the declared rows from `docs/runtimes/harness-adapters.md` and `docs/runtimes/session-backends.md`. `a19/ledger.json` must give each adapter and row a spec-linked oracle that the named fake-binary tests replay, a default, or a quoted gap or unsupported entry. It also records the refusal and ambiguous cases and the Grok Bot runtime gaps, including C1, C2, C3 and C5, which the owner accepted under #150. The run fails on a gap claimed as conformant, a missing row or adapter, a stale quote or an unknown test. `docs/campaign-harness.md` lists A19 and documents the scenario. (issue #1443, PR #1458, 2026-11-08) Box skill copy: none.
- With a `[hosts]` inventory, `mdstack spawn` places each role run with a pure decision function (multi-device placement): project affinity, capability rules by role, pass and changed path, the tier's engine order before load, then the least-loaded ready, reachable host below `max_runs`. With no eligible host it queues the request with one reason per host; with no engine it refuses. `--host <h> --reason "<why>"` overrides the host and posts the reason on the item first, and a failed post spawns nothing. The run record keeps `host`, `placement` and the rejections, and `mdstack status` gains a HOST column. A placement on a host other than the primary refuses until remote run lifecycle (#345) lands. (issue #207, PR #1457, 2026-11-08) Box skill copy: none.
- Triage sweeps now group related but distinct open issues into clusters. The new `scripts/triage-clusters.py` places each open issue in at most one cluster by deterministic keys (failure class, Source, `Depends on` target, path prefix), keeps each slug stable across sweeps, lets the model add members with a one-line reason, and counts a cluster proposal (a tracking issue or a whole-cluster milestone move) once toward the noise cap. The researcher's sweep brief posts one `pass=triage-cluster` record per new or changed cluster on the day's log, labels members `cluster:<slug>` in `apply` mode, and never closes or merges a member. `scripts/triage-metrics.py report` adds cluster counts, and `docs/triage.md` gains a Clusters section. (issue #1298, PR #1455, 2026-11-08) Box skill copy: none.
- Added the M25.1 evidence ledger (`docs/metrics/m25-1-evidence-ledger.md`): it audits #157 and #158 AC1, AC2 and AC4 against the handoff and multi-device designs, C9, the manifest template and the filed build issues (all met, with citations), indexes #716 cases 1 to 5 by the run that will close each one and its stated physical limits under the owner's simulated-host acceptance, and reports four wording contradictions to their owning issues. #157 AC3 and #158 AC3 stay open for #1441 and #1442. (issue #1445, PR #1448, 2026-11-08) Box skill copy: none.
- The M20.1 local lab has a base image recipe: `environments/terminal/remote/lab/base.Dockerfile` builds `LAB_BASE` from the official `debian:bookworm-slim` pinned by its `linux/arm64` manifest digest, adding only Python 3.11, git, tmux, the OpenSSH server and procps and deleting the package's SSH host keys. The ref built on the owner's Docker Desktop is recorded in `environments/terminal/remote/lab/base.ref`, and `docs/runtimes/multi-device.md` gives the rebuild and re-pin commands. The lab image builds with the classic builder (`DOCKER_BUILDKIT=0`), because BuildKit resolves a digest-pinned `FROM` against the registry and the base is never pushed. (issue #1430, PR #1431, 2026-11-08) Box skill copy: none.
- The M20.1 local lab can now set up and tear down its Docker role hosts with `environments/terminal/remote/lab/crew-lab-docker.py`. `setup` extends the campaign run manifest with the pinned Docker context and endpoint, the image ID, the bundle hashes and every container, network and volume ID. It refuses before any Docker mutation on a name or run-label collision. Hosts get no mounts, SSH is published on `127.0.0.1` only, and a per-run SSH config maps lowercase aliases to loopback ports. Every child runs with an isolated HOME and without inherited `CREW_*`, forge tokens, SSH agents or `TMUX`. `--n3` puts each host on its own internal network with a driver, and `n3` reports N3 unproved unless every lateral probe is denied. `teardown` refuses, removing nothing, if any recorded ID lost its owner or run label; otherwise it saves evidence, removes only the manifest-owned IDs, and checks the state sentinel and a tmux decoy. An unresolved probe target never counts as denied. (issue #1357, PR #1427, 2026-11-08) Box skill copy: none.

### Changed

- The M25.1 evidence ledger's #716 case index now links a recorded "simulated host" run on the M20.1 Docker lab for each of the five real-device cases. Each row gives what the run shows and what still needs a real device, and the index states that physical sleep, power loss and overlay-network loss stay unproven. (issue #716, PR #1495, 2026-11-09) Box skill copy: none.
- The M25.1 evidence ledger (`docs/metrics/m25-1-evidence-ledger.md`) now records #158 AC3 (two-host dry run, builder remote, coordinator local) as met on a simulated host: it links #1442's A30 run from PR #1492, summarizes placement, status and ack, the disconnect and reconcile, hashes, the local comparison and teardown, states the physical limits, and marks contradiction 4 as met by that record. Real-device proof stays with #716. (issue #158, PR #1494, 2026-11-09) Box skill copy: none.
- `mdstack train build` decides a train's path from its surviving members before any push and records it as `path` in the train record and `train-report`: `train` for two or more (or one with no drop), `none` when every PR dropped, and `direct` when drops leave exactly one member on the default branch under `runtime.options.lone_pr_land = "direct"`. A `direct` build pushes no train branch, opens no train PR and waits for no CI. It closes the record with `path_reason` `collapsed-to-direct: train <n> dropped #<pr> (<reason>)`, prints `direct pr=<pr> head=<sha>`, and leaves its drops queued for `train route <n>` after the direct land. The synthesizer then lands that PR by the direct land rule, with every §7 gate at its head and the lone-ready re-survey under the land lock, and its merge record copies the collapse reason. With `lone_pr_land = "train"` nothing changes. `mdstack train check` gains a `train-merge` gate, a survey-time pre-filter that runs the build's conflict and patch-portability checks for each PR alone on the current default branch with `git merge-tree`, so failing PRs go to merge-up before a train forms. The gate also blocks a PR still at the head a collapsed train dropped while that train's survivor is open, so the lone-ready re-survey sees the survivor alone instead of re-training the same conflicting pair. (issue #1425, PR #1460, 2026-11-08) Box skill copy: deferred to #140 (profile mirror_deferral).

### Fixed

- `crew-pack.py check` no longer refuses a pack that selects its CI backend in its own layer. The floor scan matched a floor-control key name (`ci`, `hold`, `record` and the rest) at any depth, so `[backends.ci] name = "<connector>"` in a pack's `profile.toml` or environment defaults failed as floor F1 and every project had to repeat the selection. The scan now looks only where floor controls live: the `[flavor]` table with its custom flavors and classes, and `runtime.options`. A real loosening such as a custom flavor's `ci_waiver = true`, `hold_label_blocks = false`, a looser flavor or a merge grant is still refused. (issue #1325, PR #1500, 2026-11-09) Box skill copy: none.
- A bare `tmux kill-server`, `kill-session` or `kill-window` run from a worker or lead window no longer reaches the crew's server: the tmux adapter opens every role window with `TMUX=/dev/null/mdstack-worker,0,0`, a socket no server can listen on, while crew commands keep naming their server with `-S` or `-L` with the crew still on the owner's default server and no private socket (#1474, #1155, #817). The builder, reviewer and researcher tmux briefs carry the rule for destructive tmux calls and targeted test runs, and a decoy test runs the bare calls against a throwaway crew server. (issue #1475, PR #1482, 2026-11-08) Box skill copy: none.
- `dev/tests/scripts/test-campaign-attended.py` no longer fails on Linux CI with "the receipt is not asked once the snapshot changed". Its fake clock patched `time.sleep` on the shared `time` module, so the changed-window test's fake sleep, which rewrites the tmux window list, also ran inside `subprocess.run`'s timed wait loop while a pre-sleep A26 step's child was being reaped. That rewrote the window list before the before-sleep snapshot was taken, so both snapshots matched. The tests now give `campaign-attended.py` its own fake `time` namespace, so other callers keep the real clock. (issue #1479, PR #1481, 2026-11-08) Box skill copy: none.
- The Pi, Cursor and Muse sections of the harness adapter docs now name their missing `BUSY` and `COMPOSER` declarations as a gap: `mdstack upgrade` reads no mid-turn screen text from these panes, and `mdstack send` finds no composer glyph to clear stale nudges or confirm a submit. The A19 ledger quotes the new gap instead of recording an undocumented finding. (issue #1459, PR #1473, 2026-11-08) Box skill copy: none.
- `test-crew-route.py`'s queued researcher `done:` test (#1092) no longer flakes when both researcher spawns land in the same UTC second. The fake tmux reports no pane identity, so the two runs differed only by their second-granularity `start` and the test's "different run" assertion could see equal identities. The test now backdates the first run's recorded `start` before building the queued `done:` from it. Real tmux gives each pane a unique id, so product behaviour is unchanged. (issue #1453, PR #1456, 2026-11-08) Box skill copy: none.
- `scripts/crew-install.py` runs on every Python 3.11 again, as the README promises. Both extract sites (the release bundle and the git source's `scripts/` archive) now go through one `extract` helper that passes `filter="data"` only where `tarfile` has it (3.11.4+); on 3.11.0 to 3.11.3, such as Debian bookworm's 3.11.2, the member checks alone gate the extract. Those checks refuse any member that is not a regular file or directory under the expected root, or that has a `..` part, so symlinks, hard links, devices, FIFOs and absolute paths never reach `extractall`. The git source archive had no member checks before and now gets the same ones. This unblocks `crew-lab-host.py activate` in the bookworm lab containers. (issue #1447, PR #1452, 2026-11-08) Box skill copy: none.
- `mdstack poll`'s triage scan no longer queues a second `triage-p0` coordinator wake when the owner answers the triage record of a P0 item. A recorded item leaves `triage/queue.json`, so owner feedback re-queued it as an unseen P0 candidate; the wake now fires only for a `new` entry, an item with no `pass=triage` record yet, and owner feedback is still queued as `owner-feedback`. (issue #1093, PR #1451, 2026-11-08) Box skill copy: none.
- `mdstack feedback` now says why it could not list the open intake cards when `gh issue list` exits 0 with an answer that is not JSON, such as a proxy's `HTTP 502: Bad Gateway` page. Before, the refusal ended in `gh`'s empty stderr, so the line gave no reason. Now it prints `unreadable answer:` and the answer's first line, redacted and cut at 120 characters (`empty` for no output). A non-zero `gh` exit still prints `gh`'s stderr, and nothing is filed in either case. (issue #1096, PR #1450, 2026-11-08) Box skill copy: none.

## [7.2.0] - 2026-11-08

### Added

- Release 7.2.0 brings a trustworthy runtime and usable throughput (M36). `mdstack doctor` now catches a half-finished install: a checkout whose `origin` names another repo fails its `checkout` row and stops `mdstack up` (#1323), and a `claude role trust` row checks Claude Code folder trust for the checkout role worktrees come from (#408). Capacity and progress hold up: a fresh builder spawn ends its own build reservation (#1266), a builder whose `build` nudge was never acked counts as idle once its `done:` names the issue (#1302), and `mdstack watch` reports a run whose pane has printed nothing for `--idle-stall` seconds as stalled (#1283). Review state and run generations stay safe: a reviewer engine is read from every `Engine:` line (#442), another runtime's markers no longer suppress this runtime's reviewer pass (#1290), the approved and changes state tags render on one line each (#823), a reviewer done line with a trailing note routes like the bare line (#1343), a retained status file is no longer replayed as fresh wakes (#819), and a queued researcher wake reaps only the run that wrote it (#1092). Post-land close-out keeps the synthesizer through the default-branch CI run (#1339) and closes linked issues GitHub's auto-close missed (#846). `mdstack watch` runs its `--source` polls at most once per `--source-interval` and backs off on a rate limit, so a shared GitHub login keeps its quota (#1300). The bootstrap suite runs 58 cheaper tests instead of 97 (#1333). The watcher's gateway-error match counts only a harness's own error line (#1366). A builder now builds every merge train while the synthesizer keeps landing (#1391). CI hardening: the changelog check refuses a fragment whose `pr:` is `TBD` or another PR's number (#1257), and the `links` job retries a cached, pinned lychee download (#1352). Also in this release: the M20.1 host OS adapter contract and lab test-host image (#1355, #1356), the macOS and Linux host OS adapters (#1358, #1359) and the role-host runbook (#1363), a team file's per-repo `checkout` (#1287), a private-state `docs-scan.py --ref` (#1320), the memory changelog exemption (#1386), a milestone-close triage sweep that no longer waits behind a dequeued sweep slot (#1175), campaign A22/A23 oracle fixes and the A04 issue fixture body (#1177, #1174), M35 core memory (#1377) and the lessons from the repaired H01–H08 intake cards (#1342). No breaking changes; upgrade a 7.1.0 install with `mdstack upgrade --version v7.2.0`. (issue #1421, PR #1424, 2026-11-08) Box skill copy: none.
- A role-host runbook in the multi-device design: how the owner adds and removes a host that takes builder and reviewer runs, as the runner-host runbook's differences (toolchain, logins on the host itself, profile, prepare) plus per-OS runner service steps for a macOS launchd agent, a Linux systemd user unit with lingering, and the lab-only supervised container. A proof-limits table states what the local lab's Linux containers and macOS VM can show and what still needs the real second device (#716) and a real overlay (N1 to N4). Docs only; placement and remote role runs (#207, #345 to #348) are still not built. (issue #1363, PR #1429, 2026-11-08) Box skill copy: none.
- The `linux` host OS adapter: the runner as a systemd user unit with `Restart=always`, enabled with `systemctl --user` and lingering asked for (install, start, stop, status, uninstall), procfs start times with a `ps` fallback, and a read-only SSH listener row from `ss`. `mdstack host check` on a systemd host adds a `linger` row that warns while lingering is off. A lab container is supervised only when its image says so: the lab `Dockerfile` writes `/etc/mdstack/supervised`, and then the adapter writes no unit and refuses start and stop; a Linux host with neither systemd nor that file reports `no user manager` instead of falling back. Proof uses fakes only; a real user unit with lingering needs a systemd-capable Linux guest. (issue #1359, PR #1426, 2026-11-08) Box skill copy: none.
- The host entrypoint now picks a host OS adapter from `hosts.<name>.capabilities.os`, checked against its own uname: `mdstack host check` gains a `capabilities` row that fails on a mismatch (check 5), and `mdstack host prepare` fails step `capabilities` before changing anything. The first adapter is `macos`: a launchd agent with `KeepAlive` in the account's `gui/<uid>` domain (install, start, stop, status, uninstall), Darwin `ps` start times, and a read-only SSH listener row that warns on a wildcard or public address on the port the client resolves. The runner row also shows the launchd state next to the heartbeat. Proof uses fakes only; real launchd proof waits for the macOS VM or the owner's host. The `linux` adapter is lab item E. (issue #1358, PR #1410, 2026-11-08) Box skill copy: none.
- The M20.1 local lab now has a test-host image spec in `environments/terminal/remote/lab/`: a Dockerfile over an owner-approved, preloaded ARM64 Linux base pinned by digest that installs nothing from the internet, a key-only sshd config, and `crew-lab-host.py`. Its PID-1 `supervise` mode keeps sshd and the runner up and restarts either on exit, with the runner always under the non-root `crew` user in a scrubbed env, and its `ready` health check reads the runner heartbeat. `activate` verifies the bundle and SHA256SUMS copied in with `docker cp` before moving it into place and records the exact source SHA for a dev run; `authorize` writes the run's key as the only, forced and `restrict` authorized_keys line. No login, token, SSH agent or home is copied in. Proving it in a container needs the owner's Docker daemon. (issue #1356, PR #1407, 2026-11-08) Box skill copy: none.
- The multi-device design now specs the host OS adapter contract for remote hosts: runner service install, start, stop, status and uninstall (a launchd agent on macOS, a systemd user unit with lingering on Linux, and a supervised fallback for containers without systemd), the process start-time read behind the liveness probe, read-only SSH listener and key-line checks, prerequisites and engine login presence. It also clarifies the acceptance criteria of the remote role issues (#345–#348), keeps the #209 dry run runner first, sets the attach TTY contract against today's `restrict` key and `-T` client, and states which criteria a local container or macOS VM can prove and which stay real-device in #716 (docs/runtimes/multi-device.md, Host OS adapters and Remote acceptance criteria and the local lab). Design only. (issue #1355, PR #1387, 2026-11-08) Box skill copy: none.
- `scripts/check-changelog-pr.py` gains `--pr N`, and CI passes the PR's number on `pull_request` events: a fragment the PR adds or changes whose `pr:` is `TBD` or another PR's number now fails the changelog check, naming the fragment, so a fragment can no longer merge with `pr: TBD` and surface only at the next cut. A merge-train PR (`crew/train-*`) carries its members' fragments and is refused only for `pr: TBD`. Push events and release cuts behave as before. `CONTRIBUTING.md` says to fill in the number before review. (issue #1257, PR #1376, 2026-11-08) Box skill copy: none.

### Changed

- The 60 repaired historical intake cards (groups H01 to H08 from the #1337 clustering) now have their lessons recorded: one findings-buffer entry per failure pattern and four lessons (complete gate and action contracts, sandbox boundary at every effect, fixtures through the real entrypoint, terminal records reaching their consumers). Every card's regression test was confirmed to survive the 7.0 moves and pass at main, and the nine uncovered prevention criteria are filed as #1411 to #1419. Docs only; no runtime change. (issue #1342, PR #1423, 2026-11-08) Box skill copy: none.
- On tmux a builder now builds every merge train, so the synthesizer keeps surveying, gating and landing other ready PRs while a train assembles, waits for CI or bisects. `mdstack train delegate <pr>...` reserves the next train number in `trains/delegated-<n>.json` (base, member heads, synthesizer window) and hands the builder lead a refs-only `train` handoff; the lead starts a train worker with `mdstack spawn builder --train <n>`, which runs `mdstack train build --train <n>` on exactly the recorded base and heads, bisects a red train with `train bisect`, and reports the record to the synthesizer. A base that moved because of a land made meanwhile closes the train unbuilt, and a member whose head moved drops as `head-moved`. A train worker that fails twice ends with `train close <n>`, which now also closes a delegation that has no record yet. Only the synthesizer lands, and every §7 gate, including tested-with-default-branch at `train land`, is unchanged. (issue #1391, PR #1401, 2026-11-08) Box skill copy: deferred (profile mirror_deferral).
- `dev/tests/environments/test-crew-bootstrap.py` runs fewer, cheaper tests. It now runs 58 tests instead of 97: `HarnessTargets`, like `ReleaseSources`, no longer re-runs every inherited `Bootstrap` test. Tests also no longer copy the whole bundle (about 300 files) into every test's temp directory and delete it again: they share one read-only v2.1.0 bundle per process. Only tests that edit the bundle or fetch a release beside it take a private copy with `own_bundle()`, and a cleanup check fails any test that changes the shared bundle without one. The copy and delete cost about 5 seconds per test on a loaded host, where endpoint agents scan every file touched. The `Upgrade` and `UserInstall` subclasses, which edit or rename their bundle, keep a private copy per test. (issue #1333, PR #1399, 2026-11-08) Box skill copy: none.
- Core memory now records what "full speed" means in the owner profile and four coordinator lessons from M35: researcher requests come as signed comments, hold next-milestone PRs until the release cut, watch `main` CI after a direct land until #1339 ships, and re-run a CI job that fails downloading its own tool. (issue #1377, PR #1380, 2026-11-08) Box skill copy: none.

### Fixed

- The watcher's triage timer no longer lets a `queued` slot in `triage/sweep.json` hold back a milestone-close sweep after the queued sweep left `spawn-queue.jsonl`. Before, once a capped sweep was dequeued and started, the slot kept reading `queued`, so a milestone closed after that sweep waited up to `interval_hours` for the next sweep. Now the `queued` exemption holds only while a sweep request is still queued (an unreadable queue counts as holding one), and a later closed milestone sweeps at once, as `docs/triage.md` describes for a milestone close. (issue #1175, PR #1409, 2026-11-08) Box skill copy: none.
- The committed A04 campaign scenario passes at `main` again: its `issue-list.json` fixture now carries the `body` field that real `gh issue list --json number,body` always returns, which `route.py`'s `dependents()` has requested since #1063. Committed scenarios do not run in CI, so `dev/tests/scripts/test-campaign-run.py` now checks that every committed scenario's `issue-list.json` literal carries the fields `dependents()` requests; it reads those fields from `route.py`, so the next requested field fails CI instead of a campaign rerun. The M25 `variants.py` no longer patches the body in itself. (issue #1174, PR #1408, 2026-11-08) Box skill copy: none.
- Campaign scenario A22 no longer fails on a run id with capital letters: its duplicate-key check now expects the lowercased `source:` key that the triage scan writes, so `m25f-A22` passes like `m25f-a22`. A new `test-campaign-run.py` case runs A22's seeded forge through the real triage scan and its oracle for both run ids. A23's note on automatic pick no longer says the host entrypoint lacks a `check` verb, which #1117 built. It now says why pick still falls back in the sandbox: the check reports the runner down, and the runner service cannot start there because it opens tmux on the default socket, which the sandbox shim refuses. (issue #1177, PR #1406, 2026-11-08) Box skill copy: none.
- `scripts/docs-scan.py` no longer lets a branch or worktree scan overwrite the live docs scan. A new `--state-dir DIR` writes each `scan.json` under `DIR` in place of the profile's state dir, and a `--ref` scan now exits 2 unless `--state-dir` is given, so the live `<state-dir>/<owner>__<repo>/docs/scan.json` that the docs-pass timer and researcher read always holds the default-branch scan. The watcher's default-branch scan is unchanged. (issue #1320, PR #1405, 2026-11-08) Box skill copy: none.
- The watcher's gateway-error match now counts only a harness's own error line: Claude Code's `⎿  API Error <429|5xx>` line at the result gutter and Codex's `■` error banner. Tool output, file names, diffs and quoted issue bodies that name `rate-limit`, `429` or `API Error` no longer land in `schedule/errors.jsonl`, so they cannot push the scheduler's error signal high and cut its target. `docs/runtimes/harness-adapters.md` describes the anchored lines. (issue #1366, PR #1400, 2026-11-08) Box skill copy: none.
- `scripts/check-changelog-pr.py` now exempts `memory/**`, so a memory PR, which `docs/memory.md` says changes only `memory/`, passes the changelog check without a fragment. A PR that changes `memory/` together with other content still needs one. `docs/memory.md` and `CONTRIBUTING.md` say so. (issue #1386, PR #1397, 2026-11-08) Box skill copy: none.
- `mdstack watch` now reports a working run as stalled when its tmux pane has printed nothing for `--idle-stall` seconds (default 1800, 30 min; `0` turns it off), even while its claim, heartbeat or status file keeps being refreshed: the wake is `stale` with liveness `idle` and action `escalate`, once per silence, and the reviewer pool escalates it rather than treating a re-probed `alive` worker as plain silence. A builder after `done:`, a finished run and a lead or synthesizer with no work are not flagged, and the herdr backend, which reports no pane activity, is not checked. The builder and reviewer briefs now forbid background loops that refresh the claim, heartbeat or status file; a long wait uses the harness's own background-task notification. Before this, a builder's self-refreshing claim loop hid it idle at its prompt for about 2h50m. (issue #1283, PR #1396, 2026-11-08) Box skill copy: none.
- `mdstack watch` no longer spends a shared GitHub login's quota on every 5 s scan. Its `--source` commands now run at most once per `--source-interval` (default `runtime.options.poll_interval`, 60 s), and the next due time survives a re-arm. A rate-limited `gh` read in `mdstack poll` is no longer a non-transient failure that woke the coordinator and made the watcher exit on every poll. It is never retried: poll reads the reset from `gh api rate_limit` (60 s for a secondary limit), prints `rate-limited until <UTC>` and exits 75, and the watcher records an incident and holds its sources until that reset, at most an hour. Without `--once`, poll sleeps until the reset. (issue #1300, PR #1395, 2026-11-08) Box skill copy: none.
- A reviewer's done line with a trailing note after the verdict, such as `done: #<n> <sha> review pass validation required; CI red`, now routes like the bare line: `mdstack route` records the reviewer event, the reviewer lead starts validation, the scheduler ranks the event as the pass it starts, and a `changes` verdict still goes to the builder lead. Before, the anchored match dropped the line, so validation never started and the pass was never reclaimed. A note that contains the word `stale` no longer reads as a stale line. A builder's done line already allowed a trailing note (#695). (issue #1343, PR #1393, 2026-11-08) Box skill copy: none.
- `mdstack route`'s merged-PR close-out now checks each issue in the PR's `closingIssuesReferences` and, if GitHub's auto-close missed it (seen on train lands), closes it with a close-out note, so dependents no longer read a landed issue as unfinished. An issue that was reopened stays open, so an issue that must stay open until a later release keeps that state. (issue #846, PR #1392, 2026-11-08) Box skill copy: none.
- A builder whose spawn `build` nudge landed in a trust dialog, so it never acked it, now counts as idle once its `done:` line names that issue. Before, the unacked message kept the finished, pushed builder busy forever, which blocked `dequeue` idle reclaim and held scheduler capacity. Unacked fix, CI and other-issue messages still keep it busy. (issue #1302, PR #1389, 2026-11-08) Box skill copy: none.
- The CI `links` job no longer fails on a transient lychee download error. It installs the pinned lychee release (version and sha256 explicit in the job's `env`) from an `actions/cache` keyed on both, and on a cache miss retries the download up to 5 times with backoff, verifies the checksum, then runs the same offline link check. A broken link, an exhausted retry or a checksum mismatch still fails the job, the last two with a clear `::error::`. (issue #1352, PR #1385, 2026-11-08) Box skill copy: none.
- A passing review no longer leaves `crew:changes` beside `crew:approved`. The GitHub backend wrote the `set-approved` and `set-changes` state-tag commands across two lines, so the rendered reviewer brief split each command. The first line of `set-approved` is a valid command by itself, so a reviewer that ran only that line added `crew:approved` and kept the round-1 `crew:changes`, and the merge gate refused the land until someone removed the tag by hand. Both commands now render on one line, and the reviewer brief says to run the command whole, read the PR's tags back and run it again if `crew:in-review` or the other verdict tag is still set. (issue #823, PR #1379, 2026-11-08) Box skill copy: none.
- `mdstack watch` no longer replays a retained status file as fresh wakes. It used to reset a window's read offset whenever the run identity changed, so a lead restart (which keeps `status/<lead>.status`, and saves its record once without and once with the new pane identity) re-queued every historical `blocked:`/`delivered:` line, up to twice per restart. The offset now carries a SHA-256 digest of the read prefix in `wake/watch-state.json`: reading resumes at the offset while that prefix is unchanged, and starts over only for a file shorter than its offset or with a changed prefix (a new run's file, as in #369). `mdstack migrate` drops the digest of each status file it rewrites, so its recomputed offset is trusted. (issue #819, PR #1375, 2026-11-08) Box skill copy: none.
- A researcher's queued `done:` or `failed:` wake no longer kills a fresh run that reuses its window name (`riley-sweep`, `riley-<n>`). Each status wake from `mdstack watch` now names the run that wrote it (its start time, pane and worktree), and `mdstack route` reaps a researcher only when the wake's run matches the live record. Before, the wake stayed queued for the coordinator and every later route pass applied it again, so a sweep or follow-up deep dive started before the coordinator drained was killed at the next watch tick. Wakes queued before this change, which carry no run, still reap as before. (issue #1092, PR #1374, 2026-11-08) Box skill copy: none.
- `mdstack route` no longer lets another runtime's posted review, validation or verdict markers suppress this runtime's reviewer pass. Its posted-marker dedup now counts only reviews authored by `identities.reviewer.gh_user` and signed with `identities.reviewer.name`, so a record from another login, or from another runtime sharing the login under a different signature, starts the local pass instead of leaving the PR without a verdict until a rereview steer. The head-verdict check that gates a new-head or post-build reviewer spawn, and the approval check that lets a pure merge-up skip review, apply the same rule, so another runtime's `pass=verdict` no longer consumes the wake; builder fix notes and coordinator rereview steers still count. Live, queued and section-file dedup are unchanged. (issue #1290, PR #1373, 2026-11-08) Box skill copy: none.
- `mdstack route` no longer kills the synthesizer on `pr-merged` while it is still checking the default-branch CI run at a direct land's merge commit. A synthesizer started with `--pr <n>` gets its first PR from its spawn arguments, not an inbox land request, so the merged close-out saw no pending land and reaped it, and a red main after a direct land went unreported. Close-out now keeps a synthesizer whose spawn PR is the merged one until its status has `done: #<n>`, `blocked: #<n>` or `blocked: main red after #<n>`; its later `done:` line reaps it as before. (issue #1339, PR #1371, 2026-11-08) Box skill copy: none.
- `mdstack spawn reviewer` no longer starts a Claude Code reviewer on a Claude-built PR whose builder engine it could not parse. It reads every `Engine:` line in the PR's commit messages, including one written outside the trailer block (before `Co-Authored-By:`). With none, it uses the PR-body builder marker and the builder run records for the PR or its closing issues. When the engine is still unknown, spawn refuses instead of assuming non-Claude. (issue #442, PR #1370, 2026-11-08) Box skill copy: none.
- A regression test now covers a fresh builder spawn ending its own build reservation: a build grant for `#<issue>`, then `mdstack spawn builder --issue <issue>`, leaves no entry in `schedule/reservations.json`, and the decide-side matcher drops the grant against the spawned run record whatever its window state reads. A later grant with no new run record still stays live, and a refused spawn keeps its grant for the lead's release or the TTL. The three manual releases reported on 2026-11-07 came from a crew home older than the `mdstack spawn` release of #1050 (PR #1150); the test fails with that release removed and passes at the current head, so the scheduler is unchanged. (issue #1266, PR #1369, 2026-11-08) Box skill copy: none.
- `mdstack doctor` and `mdstack up` now catch a half-finished install. When the checkout (`paths.checkout`, else the project directory) has a forge `origin` URL naming a repo other than `[repo]`, doctor's new `checkout` row fails and `up` refuses before rendering, so builders never branch off the wrong repo. A path, `file://` or missing origin only warns. Doctor's new `install` and `mdstack link` rows report bootstrap's `install.json` and the `paths.mdstack` link. Both warn before bootstrap, since bootstrap runs doctor first, and a recorded install whose link is missing fails. `up` refuses a set but missing `paths.mdstack`, so rendered briefs never cite missing docs. (issue #1323, PR #1368, 2026-11-08) Box skill copy: none.
- A team file's `[repos.<name>]` section now takes `checkout`, that repo's `paths.checkout` (absolute, or relative to the team file's directory or to `paths.root` when set). `mdstack spawn` and `mdstack train` found every repo's clone from the team file's directory, so with a team file outside a clone every builder and reviewer spawn failed with `git rev-parse failed: fatal: not a git repository`. Without the key, resolution is unchanged. (issue #1287, PR #1365, 2026-11-08) Box skill copy: none.
- `mdstack doctor` now checks Claude Code folder trust for the checkout role worktrees come from, as a `claude role trust` row. Claude Code keys a linked worktree's trust on its repository root, so with `paths.checkout` outside the profile's directory (the `~/.mdstack/` layout) the coordinator's trust answer no longer covered role windows, and every Claude Code builder or reviewer on a fresh clone stopped at the trust dialog. Until the checkout is trusted the row is a human step: run `claude` once in the checkout and pick `Yes, I trust this folder`. mdstack never writes the Claude Code config; there is no supported per-process pre-trust flag. The tmux onboarding runbook lists the step as a prerequisite and the Claude Code adapter docs describe it. (issue #408, PR #1364, 2026-11-08) Box skill copy: none.

## [7.1.0] - 2026-11-08

### Added

- Release 7.1.0 brings the user-level install (M35). Everything mdstack installs now lives in one root, `~/.mdstack/` (`config.toml`, `releases/`, `bin/`, `state/`, `runs/`, `live/`), with only the repo checkout outside it (#1316). The user-level `~/.mdstack/config.toml` is the default config, so `mdstack` commands need no `--project`; a project-level `config.toml` passed with `--project FILE` stays the secondary option for a separate project-group stack, and the two never merge. `mdstack install` puts a stable `mdstack` launcher on your `PATH`, and `mdstack upgrade --version vX.Y.Z` or `--latest` upgrades it in place: fetch and verify into `releases/`, re-render every project, then flip `releases/current`, with rollback to the bundle already on disk (#1317). A second crew can share the machine under its own root with `CREW_ROOT` and its own launcher name (#1324). Also in this release: role emoji on tmux and herdr tabs (#1157), an optional `identities.team` name for the coordinator window (#1329), the crew session on the owner's default tmux server (#1327), the full thirteen-label `crew:*` set in bootstrap and doctor (#1322) and an optional project board (#1328). Upgrading a 7.0.0 install: reinstall it fresh under `~/.mdstack/` (`docs/guides/getting-started.md`); there is no fallback to `crew.toml` or the old `~/crew-home/` and `~/.crew/` defaults. (issue #1319, PR #1372, 2026-11-08) Box skill copy: none.
- A second independent crew can share a machine with the first, one root each. `~/.mdstack` is now only the default root: with `CREW_ROOT` set, the default config is `<root>/config.toml` and bootstrap's proposal writes that root. An explicitly named config always wins: commands take `--project`, else `CREW_PROJECT` (every role window's own file), else `MDSTACK_CONFIG`, else the root's `config.toml`, and every command that can write prints the file it acts under on stderr as `mdstack: config <path>`. `mdstack install` writes the launcher under the root its bundle sits in, and `--name NAME` links it onto `PATH` under its own name, so it never takes the first root's `mdstack`; `upgrade` and rollback flip only that root's `releases/current`, and `mdstack doctor` checks the profile root's launcher (docs/runtimes/tmux.md, A second root on one machine). (issue #1324, PR #1354, 2026-11-08) Box skill copy: none.
- A user-level install puts a stable `mdstack` on your `PATH`. `mdstack install`, run from a bundle extracted into `~/.mdstack/releases/`, points `releases/current` at it and writes the launcher `~/.mdstack/bin/mdstack`, which runs `releases/current/cli/mdstack`; it links the launcher into a user directory already on `PATH` (for example `~/.local/bin`) or prints the one line to add, and never edits a shell rc file. `mdstack upgrade --version vX.Y.Z`, or the new `--latest`, then upgrades like an end-user tool: it fetches and verifies the release into `releases/`, re-renders `--project` and every other project whose `install.json` (which now records the project path; an older record gives it through its `Run mdstack up --project` step) runs from that `releases/` directory, and only then flips `releases/current`, so the launcher follows with no `PATH` change; the previous tag rolls back to the bundle already on disk. `mdstack --version` prints the running tag, and `mdstack doctor` warns on a missing or stale launcher and on a `PATH` that resolves `mdstack` to something else (docs/runtimes/tmux.md, mdstack install). (issue #1317, PR #1349, 2026-11-08) Box skill copy: none.
- Each role's tab now shows its configured `[identities]` emoji beside its name, display-only: on tmux through a per-window `@crew_icon` option prefixed to the window status formats of crew windows only (never `-g`), and on herdr as an emoji-and-space label prefix (`<emoji> <label>`) that every lookup strips. Window names and labels stay the targeting identity. A variation selector (`U+FE0F`, as in the default builder 🛠️) is dropped, and an empty or multi-codepoint emoji (a ZWJ sequence) shows the name only, so the tmux status bar keeps its width. Session adapters gain an optional `icon` capability. (issue #1157, PR #1341, 2026-11-07) Box skill copy: none.
- The profile takes an optional team name, `identities.team` (`[a-z0-9-]`, 1–63 characters, default empty). When it is set, tmux window 0 is named `<coordinator name>-<team>` (`ash-mdp-m4`); `up`, `send`, `attach`, the builder lead and the merge train resolve that name from the profile, `status`, `guard` and the watcher keep addressing window 0 by index, and `mdstack attach ash` and `mdstack send ash` still reach it. Templates can use a new `<TeamName>` placeholder, empty when unset. With the key unset or empty, rendered briefs and window names are unchanged, and an invalid value fails `validate`. (issue #1329, PR #1340, 2026-11-07) Box skill copy: none.

### Changed

- **Breaking:** every installed piece now lives in one place, `~/.mdstack/`, with only the repo checkout outside it, and the profile is `config.toml`. The user-level `~/.mdstack/config.toml` is the default: every `mdstack` and `core/crew-config.py` command uses it when given no `--project` and no `MDSTACK_CONFIG`, so `--project` is no longer required. A project-level `config.toml` passed with `--project FILE` stays the secondary option for a separate project-group stack; the two never merge (docs/runtimes/tmux.md, User-level and project-level config). The default layout is `~/.mdstack/` (profile directory: `config.toml`, the `start` and `start-owner` wrappers, `releases/`), `~/.mdstack/state/`, `~/.mdstack/runs/<repo>/` and `~/.mdstack/live/`; `profiles/tmux.toml` ships it as its default `[paths]` block (`<owner>` and `<repo>` in a path take the `[repo]` owner and name at resolve, so only `[repo]` needs filling in) and a tmux bootstrap proposal writes it, taking the repo from the profile directory's git origin, else the current directory's. `mdstack layout --write` now writes `start-owner` beside `start` in the profile directory instead of under the checkout's `.crew/`. Host and runner job roots default to `~/.mdstack`. Bootstrap records the profile copy as `<state>/config.toml`. Doctor, and so bootstrap, now refuse a `state_dir` or `worktree_root` inside a git checkout, while a profile directory that also holds `state/`, `runs/` and `live/` passes. There is no fallback to `crew.toml` or the old `~/crew-home/` and `~/.crew/` defaults (7.x installs are fresh); `crew:` labels, markers and `CREW_*` variables keep their names. (issue #1316, PR #1338, 2026-11-07) Box skill copy: none.
- The tmux runtime now runs the crew on the owner's default tmux server by default, so plain `tmux ls` lists the session and `tmux attach -t <session>` attaches; the dedicated `tmux -L <session>` server from #818 is opt-in with `runtime.options.tmux_server = "dedicated"`. The trade-off: on the default server a stray `tmux kill-server` from a pane also takes down the owner's own sessions; the #817 guard stays the primary protection. A crew session still running on the other server is used there until its next `mdstack up`, and an unknown value fails `validate`. (issue #1327, PR #1335, 2026-11-07) Box skill copy: none.

### Fixed

- `mdstack bootstrap` and `mdstack doctor` no longer report a `crew:*` namespace collision on a repo that uses the sensitive class. The crew label set now has thirteen labels: it adds `crew:sensitive` (the color and description already on the framework repo), `crew:express` and `crew:solo`, the other `crew:*` labels the protocol applies. An unknown `crew:*` label still fails as a collision. The GitHub tracking runbook and the GitHub backend label table list the full set. (issue #1322, PR #1336, 2026-11-07) Box skill copy: none.
- `mdstack doctor` no longer reports a missing crew board as `fail` when its identity cannot create one under the repo owner (a bot login on a user-owned repo, or a classic token without the `project` scope). It reports a `human` step naming the owner's `gh project create` and `gh project link` commands instead, so `mdstack bootstrap` proceeds. `doctor --fix` still creates and links the board when the identity can. The bootstrap, GitHub backend and GitHub tracking docs now say the board is recommended, not required. (issue #1328, PR #1334, 2026-11-07) Box skill copy: none.

## [7.0.0] - 2026-11-08

### Added

- Four guides under `docs/guides/` give new and existing installs a clear path. `getting-started.md` covers the one-command bootstrap into the home root, the first `mdstack up`, talking to the team head (`ash`, the `cto` seat) and adding an on-demand role with `mdstack up <role>`. `connectors.md` shows picking one connector per concern and setting up the knowledge connector: the role names the source in git, the page pointer lives in the private config, and the token stays in an environment variable. `pack-authoring.md` covers the pack format and `pack.toml`, the plug-in points, wiring with `paths.pack` and `mdstack pack list`, and the conformance kit `mdstack pack test`. `migration.md` covers the move from the old layout and CLI name: the ordered steps, the `crew` → `mdstack` shim kept for one release, the 6.0.0 old-path-to-module table and the shim removal in 7.0.0, and pack updates. The docs index, runbook and deliverables manifest list them. Navigation only; no rule, gate, marker or default changes. (issue #1238, PR #1310, 2026-11-07) Box skill copy: none.
- `mdstack migrate --rename-to <owner>/<new>` plans and applies a repository rename for a stopped crew: the state directory `<owner>__<name>` moves, and the profile (its `[repo]` name, quoted slugs and state paths), the operational state files, bootstrap's `install.json` and the home's turn-end guard are rewritten in place. The preview also lists the tmux session and host job roots derived from the repo, and the product names that stay until a release renames them. The GitHub rename and the redirect check stay owner steps, done before `--apply`. The owner-run runbook is `docs/runbooks/repo-rename.md`. The train's mirror check now recognises eng-crew's own checkout by its `cli/mdstack` entry point, not by the repo name, so it keeps firing after a rename. (issue #1234, PR #1304, 2026-11-07) Box skill copy: none.
- The decisions doc now carries the public-safe content of the owner's old private design repo, which is to be archived: the six owner-facing seats with their personas, ownership and hand-offs, contexts as packs with a starting seat action vocabulary, seats as content on this machinery, and the 2026-11-07 design decisions (roles as portable employees with continuity, a role and protocol layer with one owned terminal environment, specialist roles with team heads and front doors, CLI-backed generic actions). Personal and organisation-internal content was left out. (issue #1235, PR #1299, 2026-11-07) Box skill copy: none.
- Role classes (team spec REQ-20 to REQ-22): every role definition declares its `class` (`owner-facing` seat or `internal` staff) and `seat`, internal staff declare an `escalation` path ending at the owner-facing role holding their seat, and each registry names exactly one team head. `crew-roles.py` validates them. The engineering head, the coordinator, holds the `cto` seat; the other roles are internal staff under it. The protocol now states that only owner-facing seats deliver owner asks, and team spec Q1 is settled. (issue #1227, PR #1286, 2026-11-07) Box skill copy: none.
- Role routines: each role package gets a `routines/` folder of recurring jobs, `routines/<routine>.toml` with a schedule (an interval with jitter and a profile key, or cron in the owner's timezone), the skill it runs, generic actions, inputs, outputs, a deadline and a miss policy (`skip`, `catch-up-once`, `escalate`). `core/crew-routines.py` validates them and decides when one is due; check-repo's new `routines` check holds them to the actions contract. The researcher's triage sweep, milestone-close sweep and docs pass and the coordinator's backstop (`stale-sweep`) now take their cadence from routine files with unchanged behaviour; metrics refresh and decision-log status are declared but stay manual (`enabled = false`). A lifecycle role whose `wake` lists `routine` is started by a due routine and stays at zero with none due. Seat packages get an empty `routines/`. Adds the `dev.eng-crew.milestone.closed` event type. See `docs/routines.md`. (issue #1247, PR #1285, 2026-11-07) Box skill copy: none.
- `crew action`, the terminal binding of the actions CLI contract: it keeps the contract's JSON envelope, exit codes and `--capabilities`, and implements `check-ownership`, `heartbeat`, `notify`, `ack` and `report` over the same control item, claim, inbox and status files the tmux and herdr runtimes read today. An explicit `--key` replays the first outcome of a repeated call with no second effect, and `heartbeat` writes only the claim the caller's run record names. Every other action answers `unsupported` (exit 6). The builder, reviewer and synthesizer policy fragments now call `crew action heartbeat` and `crew action report` instead of editing the claim or status file by hand; the status lines they write are unchanged. (issue #1232, PR #1280, 2026-11-07) Box skill copy: none.
- Core memory layer: an owner profile (`memory/owner.md`) and one core memory file per role (`memory/roles/<role>.md`), curated in git with size limits (3000 and 2000 bytes). The renderer appends them to every role's rendered brief, so terminal, session and Grok Bot roles start with them; a lint problem fails the render closed. `core/crew-memory.py` (and check-repo's new `memory` check) refuses personal data and routes it to the knowledge connector. The coordinator's new memory-capture skill proposes promotions from platform scratch as a memory PR. See `docs/memory.md`. (issue #1230, PR #1278, 2026-11-07) Box skill copy: none.
- A first `knowledge` connector: Notion. The actions contract gains A21 `knowledge-read` and A22 `knowledge-propose-edit`, and `connectors/notion/knowledge.py` implements both under the CLI contract (one JSON envelope, exit code as outcome). `knowledge-read` writes a page's title and top-level blocks as plain text to a local file that git ignores; `knowledge-propose-edit` posts the proposal as a page comment and never edits the page; the comment names the idempotency key, and a private key ledger (`CREW_KNOWLEDGE_KEYS`, digests and comment ids only) plus a read-back of the page's open comments make a retry with the same key and inputs return the earlier comment instead of posting again, even after the owner resolves it. A role reaches only the sources its definition lists in the new optional `knowledge` key of `roles/<domain>/<role>.toml`. Page pointers and the token come only from the install's private config (`CREW_KNOWLEDGE_CONFIG`, default `~/.config/eng-crew/knowledge.toml`, which names the token's environment variable); a config tracked by git is refused, and `.gitignore` ignores `knowledge.toml`. A connector manifest may now declare the `knowledge` concern alone. See `docs/backends/notion.md`. (issue #1229, PR #1277, 2026-11-07) Box skill copy: none.
- Any role can now run in the terminal on demand. A role definition may declare a `lifecycle` table: `policy` (`always-on`, `elastic` for a lead plus elastic workers, or `ephemeral`), `min` and `max` instances, `idle_ttl` in seconds and `wake` triggers (`manual` or tmux event IDs). `crew-roles.py` validates it: a tier-sourced role without `cap_key`, `max` within its window band, the policy's bounds, and a first pass with no inputs. `crew up` starts each lifecycle role's `min` instances after the pool leads. `crew up <role> --project <file>` starts one more instance of a role with the `manual` wake and refuses at `max`. On every scan the watcher kills instances that have had no pane output, no inbox message and no unacknowledged message for `idle_ttl` seconds, down to `min`, so ephemeral roles scale to zero. Event wakes are declared only for now. Roles without a `lifecycle`, all the engineering roles among them, behave as before. (issue #1231, PR #1275, 2026-11-07) Box skill copy: none.
- Seat placeholders: `roles/seats/{ceo,cto,cpo,coo,cdo,cfo}/` each hold an empty role package (`role.toml`, `SKILL.md`, `skills/`) for content authored elsewhere, and `roles/seats/TEMPLATE.md` documents what to fill in. No personal data; the role registry still reads `roles/eng/` only. (issue #1228, PR #1268, 2026-11-07) Box skill copy: none.

### Changed

- **Breaking:** 7.0.0 is a fresh install: reinstall from scratch (docs/guides/migration.md); no 6.x or older install is carried forward. The product is now named mdstack, after the repo moved to `github.com/mw-ding/mdstack`: the release bundle is `mdstack-<version>.tar.gz` with top directory `mdstack-<version>/` (its `SHA256SUMS` entry follows), the host toolkit is `toolkit/mdstack-<version>/`, the install link is `<state>/mdstack`, the profile key is `paths.mdstack` and the pack pin is `pack.mdstack_version`, and docs, templates and the README use the new name and repo URL. The old names are not accepted (no alias for `paths.eng_crew` or `pack.eng_crew_version`, no `<state>/eng-crew` link, no `eng-crew-<version>` bundle or toolkit lookup), and the pre-7.0 compatibility layer is removed: the `crew` CLI shim (`cli/crew`), the 6.0.0 old-path shims under `scripts/` (`scripts/crew`, `scripts/crew-*.py`, `scripts/crew.d/`, `scripts/session.d/`, `scripts/harness.d/`) with old-directory adapter discovery, the `packs/github/manifest.toml` copy, the old `crew` turn-end guard and start-wrapper recognition, and `test-compat-shims.py`. `crew:` labels, markers, `CREW_*` variables, issue links and historical records keep their names. (issue #1312, PR #1315, 2026-11-07) Box skill copy: deferred to #140.
- **Breaking:** Release 7.0.0 is a fresh start: reinstall from scratch, following `docs/guides/migration.md`. It carries no 6.x or older install forward and ships no compatibility aliases or shims: `mdstack` (`cli/mdstack`) is the only CLI, the release bundle is `mdstack-7.0.0.tar.gz`, and the old `eng-crew` names and 6.0.0 `scripts/` paths are not accepted. For a code pack, rename `pack.eng_crew_version` to `pack.mdstack_version` or give a `pack.toml` `framework` range that includes 7.0.0 (for example `">=7.0.0, <8.0.0"`), since bootstrap refuses a pack outside its range. The release rounds up M29–M34, the move from one engineering crew in `scripts/` to a modular team framework. M29 wrote the specs and contracts (the team spec, the generic actions contract, specs in the essential doc set and baseline metrics). M30 and M31 decoupled the code and moved it into modules along four independent axes, roles, connectors, environments and harnesses, plus `core/`, `cli/`, `profiles/`, `packs/` and `dev/`, shipped in 6.0.0 with code packs (`pack.toml`, `mdstack pack list`, `mdstack pack test`). M32 took the team beyond engineering: role classes with owner-facing seats, internal staff and one team head (the coordinator, Ash, holds the `cto` seat and now signs as CTO), C-suite seat placeholders, on-demand role lifecycles that scale to zero, role routines, a core memory layer in git, `mdstack action` as the terminal binding of the generic actions, and connectors that now include knowledge, with Notion as the first. M33 renamed the CLI to `mdstack`, added `mdstack migrate --rename-to` with an owner-run repository rename runbook. M34 consolidated the public docs (module READMEs, reading paths, the four-axes glossary) and added getting-started, connector, pack author and migration guides. (issue #1239, PR #1311, 2026-11-07) Box skill copy: none.
- The public docs read as one set for the modular structure. Each module (`roles/`, `connectors/`, `environments/` and `environments/terminal/`, `harnesses/`, `core/`, `cli/`, `profiles/`, `packs/`, `dev/`; `actions/` already had one) has a short README with its purpose, contents and how it plugs in, shipped in the bundle. `docs/README.md` replaces its role-by-role list, a copy of `reading-paths.md`, with reading paths for user, operator, pack author and contributor, and adds a module table that says where the not-yet-split `protocols/` and `install/` content lives. `docs/concepts.md` adds the four axes (role, connector, environment, harness) and the team terms (generic action, seat, staff and team head, routine, core memory, module), and maps runtime, backend and profile onto them. `docs/architecture.md` gains a Modules section with a Mermaid diagram of the axes and the layout. `docs/specs/framework.md` marks its bootstrap layout, sources and slices historical while R1–R8 stay cited, and the README's spec link names the team and portable specs too. Four design docs the docs scan flagged gain status banners. No rule, gate, marker or default changes. (issue #1237, PR #1309, 2026-11-07) Box skill copy: none.
- The CLI is renamed `crew` → `mdstack`: `cli/mdstack` is the entry point, `$CREW_BIN` and the Claude Code turn-end guard hook now name it, and the docs, templates, briefs, command usage lines and tests say `mdstack <command>`. `cli/crew` stays for one release as a shim that prints a deprecation note on stderr and then runs `cli/mdstack` unchanged; `scripts/crew` still runs it. A guard hook that names the old `crew` path is recognised and re-pointed at `mdstack` by `mdstack up` and `mdstack migrate`. Anchors to the `docs/runtimes/tmux.md` command sections are now `#mdstack-<command>`. Environment variables (`CREW_*`), the `crew.d/` module directory, `crew.toml`, state paths and `crew:` labels and markers keep their names. (issue #1233, PR #1301, 2026-11-07) Box skill copy: none.
- At full speed (every pool's effective cap equal to its full cap), the
  scheduler now counts memory as high only at `critical`: macOS `warn` counts
  as low, so the target T can grow again, and the Linux `some avg10` high
  threshold moves from 10.0 to 40.0. Light mode keeps `warn` as high. The new
  `runtime.options.memory_high` option (`warn` or `critical`) overrides the
  mode rule, and the snapshot (`memory_high`) and summary line
  (`mem warn (high at critical)`) show the effective threshold. (issue #1282, PR #1284, 2026-11-07) Box skill copy: none.
- Ash's default display title is now `CTO`, so a fresh default render signs
  coordinator posts `— 🔥 Ash (CTO) · <harness> · <model>`. The pipeline role
  id `coordinator`, the `<CoordinatorBot>` / `<CoordinatorTitle>` placeholders
  and coordinator templates are unchanged; a profile that sets
  `identities.coordinator.title` keeps its own value. Away-record parsing now
  matches the resolved coordinator title instead of a hardcoded `(Coordinator)`,
  and still accepts that legacy sign on records posted before the change. (issue #781, PR #1279, 2026-11-07) Box skill copy: none.

## [6.0.0] - 2026-11-07

### Added

- Packs can now bring their own code. A pack directory with a `pack.toml` declares the eng-crew release versions it supports (`framework`, such as `">=5.3.0, <6.0.0"`) and what it provides: connectors, harness adapters, environment defaults and skills. The new loader, `core/crew-pack.py`, checks each item with the loader its built-in kind already uses. Resolve then layers the pack as core, default profile, pack, project: a pack connector is selectable by `backends.<concern>.name`, a pack harness by engine name (and `crew spawn` launches it), and environment defaults apply when the runtime matches. A pack never replaces a built-in name. Bootstrap and upgrade refuse a pack whose range excludes the installed release tag, or whose checkout is not clean. `install.json` records the pack's name, version, framework range and git commit. The loader refuses a pack that loosens a core floor: a floor control, a merge grant, or a flavor less strict than `standard`. `crew pack list --project <file>` lists built-in and pack items. `crew pack test <dir>` runs the new actions/ conformance kit (`actions/contract.py`) against a pack's connector action binding and harness adapters with fakes, for the pack's own CI. Packs without `pack.toml` work as before. (issue #1236, PR #1265, 2026-11-07) Box skill copy: none.
- `crew bootstrap` now scaffolds the specs home of the essential doc set: when the checkout's `docs/specs/` (or the profile's `[docs] homes.specs`) holds no Markdown spec, the plan prints a `scaffold` repo operation and apply writes `project.md` from the spec template's skeleton, for the owner to commit; it never overwrites a file or seeds beside an existing spec, and the seed is not an owned install target. `[docs] homes` accepts a `specs` key (a directory, no anchor), and `docs-scan.py` reports a specs home with no Markdown spec under it as missing. (issue #1225, PR #1262, 2026-11-07) Box skill copy: none.
- The essential project doc set now has six docs: `docs/specs/` joins it as every project's source of truth, each spec carrying the design-doc status banner. A new spec template (`templates/spec.md`) seeds one with stable `REQ-` requirements (applies when, obligation, acceptance criteria, verification), open questions and a change table. eng-crew adopts its own doc set: `docs/decisions.md` is seeded from the #985 decision log, and `docs/runbook.md` is the runbook entry point linking the install, run, release and recover owner docs. The `[docs] homes` key and docs-pass check for specs come with the bootstrap scaffold (#1225). (issue #1219, PR #1244, 2026-11-06) Box skill copy: deferred to #140.
- `scripts/metrics-baseline.py` reports, for closed crew PRs over a chosen window (optionally one milestone), the medians of issue-to-PR, PR-to-first-verdict, verdict-to-land, handoff ack latency, rounds per PR, defects caught by review or validation, and recorded engine runs per PR, with a per-PR table. The first baseline, covering M25, is committed as `docs/metrics/baseline-m25.md` so the reorganization can be compared against it. Measurement only; no crew behaviour changes. (issue #1220, PR #1243, 2026-11-06) Box skill copy: none.
- New `actions/` contract, documentation only: `actions/README.md` defines the twenty generic actions (A1–A20) roles use to coordinate, each with its semantics, inputs, outputs and the six outcomes `completed`, `pending`, `stale`, `refused`, `failed` and `unknown`, plus the capability declaration and CloudEvents/CDEvents event names; `actions/cli.md` fixes the `crew action` command names, arguments, exit codes and JSON output; `actions/mapping.md` maps each action to how tmux, herdr and Grok Bot carry it out today, with gaps marked. No command implements it yet (M32), and no gate, marker or label changes. (issue #1218, PR #1242, 2026-11-07) Box skill copy: none.
- New spec `docs/specs/team.md` (v0.1) carries the owner's 2026-11-07 team design as structured requirements REQ-01–REQ-24, each with applies-when, obligation, acceptance criteria, verification and delivering issues: portable role packages in Agent Skills format, four independent axes (roles, connectors, environments, harnesses), generic actions with a CLI as the terminal implementation, the terminal fast lane with per-host session backends, a `knowledge` connector for personal knowledge kept outside git, owner-facing seats versus internal staff with team heads, and self-hosted specs; plus the target module layout, dependency rules D1–D9, a P1–P8 mapping to `portable.md` and open questions. Docs only; no live gate or marker rule changes. (issue #1216, PR #1240, 2026-11-06) Box skill copy: none.
- `docs/metrics/m25-report.md` is the M25 final report (25.27). It reruns the 29 committed campaign scenarios at the final `main` SHA `a135a4d`, one fresh level-a sandbox each: 28 pass, and A04 fails on a stale fixture (#1174). It also runs the merged-head reruns the fix loop owed, the register rows carried to #806, the observed real-engine journeys, cost and usability, inventory-to-scenario traceability, and the limitations for the owner to accept before M25 closes. `scripts/fixtures/campaign/m25-final/` holds the per-scenario driver (`run.sh`) and the variant builder (`variants.py`) the report ran. (issue #806, PR #1186, 2026-11-07) Box skill copy: none (internal report and campaign fixtures; no template or box-skill changes).
- A crew can now live in a home-level layout under one movable root. `paths.checkout` names the git checkout that spawn, train, host prepare, the docs timer and bootstrap's `.crew/` exclude use, so the runtime home (`~/crew-home`) need not be a git checkout; it defaults to the profile's directory. `paths.root`, which a set `CREW_ROOT` overrides, resolves each relative `state_dir`, `worktree_root`, `live_dir`, `eng_crew` and `checkout` under it, so a later move such as `~/.mdstack/` changes one value. `crew layout` prints the resolved layout and `--write` writes the one-command `<home>/start` and `<checkout>/.crew/start-owner` wrappers, never user-level config. `crew down --preserve` stops the watcher and panes but keeps every run's work, and `crew migrate --project OLD --to NEW` previews and, with `--apply`, performs the relocation: state, live and registered worktree moves, operational path rewrites that keep message ids and reconcile watcher offsets, the settings copy, a journal with rollback commands and a path map, with Claude Code memory and trust left as owner steps. (issue #1178, PR #1181, 2026-11-06) Box skill copy: none.
- `scripts/worktree-purge.py` is a one-off purge of stale git worktrees on the crew host, an early slice of #316. It lists every worktree of the repo with branch, head, PR state read back from GitHub, a `keep` or `remove` classification and the reason, and is a dry run by default. A row is `remove` only when it is not the main worktree, a protected checkout or the current directory; no run record, claim or tmux pane references it; `git status` is clean apart from `.crew/` scratch; and its head is in `origin/main`, or a merged or closed PR has exactly that head and its remote branch matches or is gone. `--apply` runs `git worktree remove` without `--force` on `remove` rows only, then `git worktree prune`, and leaves local branches alone. (issue #1161, PR #1164, 2026-11-06) Box skill copy: none.
- The M25 campaign gains the A17 (express self-gate and fallback) and A18 (solo) scenario specs in `scripts/fixtures/campaign/` (25.13), at level a on sandbox tmux with the fake forge. A17 proves that the default `selfgate_engine` stays `different` and that same mode runs only from an isolated `--org-profile`. An express record needs a Reason and is refused for `crew:sensitive` or `crew:spec` without an owner override, and always for `crew:solo`. The selfgate record is checked for schema, head, key, signature, verdict, open findings, mode and engine diversity. A resolved express change starts no reviewer and reaches the synthesizer only on a selfgate pass with green CI, while CI, holds, rereview and merge permission still block. A cap with an open finding, a sensitive label or a tightening rename path returns the change to the crew lane with a fresh review at head. A18 proves that a solo item never gets a crew builder, and that its PR keeps an engine-diverse independent reviewer and the synthesizer's §7 gate. (issue #795, PR #1121, 2026-11-06) Box skill copy: none (internal campaign fixture and doc; no template or box-skill changes).
- The M25 campaign gains the A15 (direct land and negative merge gates) and A16 (stop-landing, grants and owner steer) scenario specs in `scripts/fixtures/campaign/` (25.12), at level a on sandbox tmux with the A14 fake forge. A lone ready PR behind main lands directly under `lone_pr_land = "direct"`, with no update-branch and no train PR, and two ready PRs land through a train. Each unsatisfied §7 gate blocks `crew train check`, and the land-time gates stop `crew train land` with nothing squashed. A head moved after the check is refused at the forge. A standing grant supplies only permission. A hold posted after approval stops the land. A project stop survives control-item close, restart and a moved head until its matching resume. Merge-ok counts only at the current head. The run filed #1118. (issue #794, PR #1119, 2026-11-06) Box skill copy: none (internal campaign fixture and doc; no template or box-skill changes).
- The M25 campaign gains the A14 (train, overlap and serial land) scenario spec in `scripts/fixtures/campaign/` (25.11). It runs at level a on sandbox tmux, with a fake forge that squashes for real. Two PRs editing one shared file stay in one train, and a third on the same line drops as a conflict. A red train lands nothing, and no successor builds on it. A successor built on its predecessor's tip waits for it, then lands on the final squash. Under one land lock, each member lands in order at its exact tested head, with the train step's tree. A head that moves mid-land is refused at the forge. A default branch that moves mid-land stops the train and rebuilds the successor on the new main. Every draft train PR is closed. (issue #793, PR #1115, 2026-11-06) Box skill copy: none (internal campaign fixture and doc; no template or box-skill changes).
- The M25 campaign gains the A13 (merge-up portability and conflict chain) scenario spec in `scripts/fixtures/campaign/` (25.10). It runs at level a on sandbox tmux with the fake forge. A clean tool merge-up pins all four SHAs, and identical content with green CI carries the passing verdict from H with no new round. The owner's merge-ok at H does not carry to the updated head. Whitespace, path and mode changes and an unavailable base never carry. A train over three PRs editing one shared line keeps the clean member and drops the two conflicts. `crew train close` routes them to builders with no update-branch call and no synthesizer edit. Each builder resolves the conflict and records the four SHAs in a signed fix note, and the differing patch needs a new head-pinned delta verdict. A verdict without a base drops as `no-verified-base` and routes to the reviewer. (issue #792, PR #1108, 2026-11-06) Box skill copy: none (internal campaign fixture and doc; no template or box-skill changes).
- The M25 campaign gains the A23 (forge-less runner) scenario spec in `scripts/fixtures/campaign/` (25.20), with a fake SSH transport, sample checks and step helpers in `a23/`. It runs at level a: `crew runner` loops back over the fake transport to the real host entrypoint. An exact-head job stores its result, prints its runner reference and keeps its logs on the host, and the runner capture names host, job and head. The host sees only `seed`, `job` and `result`, its job env is scrubbed, and it makes no forge, engine or role call. A duplicate job id or request id returns the first job. A red remote test is a red run. Unreachable, refused and failed transport run the same commands locally and name the reason, and a late result is discarded. A stale head, a capture at another head and an unseeded head are refused. (issue #802, PR #1107, 2026-11-06) Box skill copy: none (internal campaign fixtures, test and doc; no template or box-skill changes).
- The M25 campaign gains the A24 (release cut, bundle and exact-SHA CI and approval gate) scenario spec in `scripts/fixtures/campaign/` (25.21). At level a it cuts a release in a bare clone of the source: the cut PR consumes the fragments and lands as a merge commit. The dry run then detects the cut, validates it and bundles that exact SHA with a checked `SHA256SUMS`. A non-cut push is a green no-op. Each refusal case refuses: a wrong or missing actor, approval at an earlier head or the merge commit, a non-owner marker, a non-cut or missing merged PR, missing, pending, red, cancelled, skipped or timed-out CI at the landed SHA, and a duplicate tag. A retry after green CI passes. No tag or release is written. The commit release id binding cuts and checks with the profile's paths. (issue #803, PR #1105, 2026-11-06) Box skill copy: none (internal campaign fixtures and doc; no template or box-skill changes).
- The M25 campaign gains three scenario specs in `scripts/fixtures/campaign/` (25.22), run on real sandbox tmux at level a. A25 covers owner presence, the ask SLA and notifications: an owner ask wakes the watcher once at its PT deadline, and an unreadable one at once. Present caps queue the next build. A recorded away entry gives full caps, still after its `until` passed, and its words lift no hold. A quiet entry keeps present caps, so busy builders drain without a kill. The Slack notifier, played by a loopback webhook, retries a refused delivery, never resends an uncertain one, dedupes a replay and never prints the webhook. After the owner's return it cancels pending messages and reports each outcome. A26 covers sleep and resume: nothing is queued while paused, the new head and red CI catch up once, a head handled before the pause is not replayed, three missed intervals start one overdue sweep, an empty queue starts no researcher, and a capped sweep takes its closed milestone only when its window starts. A31 covers metrics: a two-repo refresh counts rounds per PR and attributes lanes, a thin window cannot trip, a single-repo trip holds nothing, and a rollup trip holds only new feature work until the owner's waiver. An accepted intake card routes to the builder lead with its rigor unchanged. This is level-a coverage only: the real owner channel, a metric report from campaign records and a recorded sleep schedule stay open on #804 for a level-b run. (issue #804, PR #1101, 2026-11-06) Box skill copy: none (internal campaign fixtures and doc; no template or box-skill changes).
- The M25 campaign gains the A27 scenario spec (intake, milestone close and refusal recovery) in `scripts/fixtures/campaign/` (25.18). It runs on real sandbox tmux at level a. `crew feedback` files one redacted runtime-blocker card per failure class, comments on an open card of the same class, and files nothing when the card list is unreadable. A closed milestone stays queued, and is not taken, while the researchers cap holds its sweep back; it is taken once when that sweep starts. The played milestone-close sweep files `crew:` and `repo:` cards, adds evidence to a matching card and links a matching lesson. A provider safety refusal is parked once as `needs-owner` and never retried, and a worker's refusal status wakes the coordinator once with the window kept. The sandbox `gh` stub now keeps each `--body-file -` body in `bodies.log`. (issue #800, PR #1097, 2026-11-06) Box skill copy: none (internal campaign fixture, sandbox stub and doc; no template or box-skill changes).
- The M25 campaign gains the A22 scenario spec (triage scan, shadow proposals and calibration) in `scripts/fixtures/campaign/` (25.17). It runs on real sandbox tmux at level a. The poll scan skips placed, flavored, recorded, log and pull-request items, records a malformed item, hints an exact duplicate and wakes a P0 once. The sweep timer skips an empty queue and catches up when overdue. Shadow records cite what they used, extract a card once and apply nothing. The owner's sample answers are recorded, and the ten-sample bar is met at 8 of 10 and frozen into the eval set, while mode stays shadow with no `crew:ready`. The noise cap, the rejection cooldown and repeat sweeps hold. The sandbox `gh` stub now answers an `issue list --state S` call from its own file. (issue #799, PR #1094, 2026-11-06) Box skill copy: none (internal campaign fixture, sandbox stub and doc; no template or box-skill changes).
- The M25 campaign gains the A20 (install, doctor, upgrade, rollback and uninstall) scenario spec in `scripts/fixtures/campaign/` (25.14). It runs on real sandbox tmux at level a. It installs from a checksum-verified local bundle with a `mirror` source and an org pack pin. The steps cover doctor's fail, fix, ownership and tool-drift rows. They check that dry-run writes nothing, and that the self-test and install record are complete. They refuse a drifted render, an edited or tracked target, a pin mismatch and a bad checksum, each leaving the install untouched. An upgrade waits for a busy pass, applies from the verified bundle and rolls back to the previous one. Uninstall pauses items and keeps unlanded work, then archives the state and keeps an edited target. A reinstall and an upgrade with a running crew then check that each role reloads, coordinator last. (issue #796, PR #1091, 2026-11-06) Box skill copy: none (internal campaign fixtures and doc; no template or box-skill changes).
- The M25 campaign gains the A28 scenario spec (ownership, two-team handoff and detached teardown) in `scripts/fixtures/campaign/` (25.19). It runs two sandbox teams on one repo on real sandbox tmux at level a. It covers one writer with an untrusted claim ignored, drain then abort, a lost offer response retried to one post, a partial reconcile that holds the diverged set and flags the stale in-transit marker, kept run and rule difference, a lost ack response acked once, `crew handoff stopped` typed in the outgoing session posting `stopped` only after the session and watcher are gone while keeping unlanded work, a return in stop mode that posts nothing on a change, a mid-way takeover reusing the handoff id, and the detached stop repeated 20 times under parallel load with counts. The sandbox `gh` stub now answers `gh api` from a scenario path map that keeps posted comments, with injected lost posts and a post-time probe. (issue #801, PR #1083, 2026-11-06) Box skill copy: none (internal campaign harness, fixture and doc; no template or box-skill changes).
- The M25 campaign gains the A12 (typed and inline evidence) scenario spec in `scripts/fixtures/campaign/` (25.09), with a sample CLI, service and API and a validator reproduction helper in `A12-sample/`. It runs at level a. CLI create→complete→delete, service, API and web-view captures reproduce exit, stdout and stderr in a fresh clone at the PR head. A failed command's capture keeps its own exit line, so the helper's exit 0 never reads as a pass. A stale capture or a changed head is refused, and a recapture at head agrees. `crew train check` blocks missing artifact-shaped paths, ignores prose, template and scratch paths and counts builder-signed fix proof only at head. Its last step expects a user-attachments screenshot, and a missing-artifact citation repaired by signed proof at head, to read `manual` (fixed by #1078 and #1079). The mobile gap is stated explicitly. (issue #791, PR #1080, 2026-11-06) Box skill copy: none (internal campaign fixtures, test and doc; no template or box-skill changes).
- The M25 campaign gains the A21 scenario spec (Riley research dispatch and sweep coexistence) in `scripts/fixtures/campaign/` (25.16). It runs on real sandbox tmux at level a. A clear signed request gets a fresh deep-tier session and one cited, signed finding on the source issue, and its window is reaped once. Unclear and non-owner requests block with nothing posted. No run takes a code, PR-branch or gate action. The researchers cap admits a deep dive while a sweep runs, then queues the next deep dive, and queues a sweep behind two deep dives. (issue #798, PR #1077, 2026-11-06) Box skill copy: none (internal campaign fixture and doc; no template or box-skill changes).
- The M25 campaign gains the A11 (standard PR pipeline, precheck, rigor and rounds) and A32 (engines, quota steers and overrides) scenario specs in `scripts/fixtures/campaign/` (25.08). They run on real sandbox tmux at level a. A11 covers standard and missing item records, a tightening path, a build with seeded red CI that is reviewed but not validated, the CI fix with a fresh review, precheck refusals repaired to a pass, changes returned once, a round-2 fresh review and validation with no copied verdict, approval to the synthesizer, close-out on merge and an escalated change that starts no review. A32 covers tier order and effort matching the launch, a role override, reviewer diversity against actual builder engines, refusal when no diverse engine is left, a quota steer and Muse never launched on a private or unverified repo. (issue #790, PR #1075, 2026-11-06) Box skill copy: none (internal campaign fixtures and doc; no template or box-skill changes).
- The M25 campaign gains the A08 (rank and reservations), A09 (held demand and release) and A10 (rate limit, pressure and floors) scheduler scenario specs in `scripts/fixtures/campaign/` (25.07). They run on real sandbox tmux at level a. `docs/campaign-harness.md` maps scheduler build issues S1–S7 and S9–S11 to scenario steps and excludes S8, which was closed unbuilt. The fake forge answers a `gh ... --label L` query from its own file, so held items differ from the open issue list. A08's last step ranks a red default-branch fix (an open `main-red` issue) as class 1; the run found and filed #1072, fixed by #1081. (issue #789, PR #1073, 2026-11-05) Box skill copy: none (internal campaign fixtures, fake-forge stub and doc; no template or box-skill changes).
- The M25 campaign gains the A06 (leads, refs and withdrawn handoffs) and A07 (reap and retention) scenario specs in `scripts/fixtures/campaign/` (25.06). They run on real sandbox tmux at level a. A06 covers refs-only send and ack, pending and lost-ack replay reusing one id, completed and withdrawn ids never reported as the new ack, a single dispatch per resend, and a lead restarted once after it exits holding a pending id. A07 covers review, validate, changes and external-merge (#811) terminals in router-first and lead-first order and through `crew kill`, retained verdict sections, a freed reviewer slot admitting the queued pass, the terminal summary, and idle-builder reclaim that leaves a busy builder alone. The run filed #1070. (issue #788, PR #1071, 2026-11-05) Box skill copy: none (internal campaign fixtures and doc; no template or box-skill changes).
- M25 campaign scenarios A01 (config layers and provenance, two-repo team files, malformed capability, flavor floor lowering, fix-and-rerun recovery, external pack pin and bootstrap pin) and A02 (render overlay and runtime notes, missing mapping and note, drift detection and restore, long install path, size budget and render, parity and bootstrap tests) are committed as `scripts/fixtures/campaign/A01.json` and `A02.json` with their fixture profiles; each step stages its fixtures from `{source}`. Harness specs only. The level-a run's results are posted inline on the PR; its one failed oracle (render-vs-live drift passing an altered command or appended live text) was filed as #1064 and fixed there, and A02 passes on rerun. (issue #786, PR #1067, 2026-11-05) Box skill copy: none.
- The M25 campaign gains the A03 (tmux lifecycle), A04 (wake, route and watcher) and A05 (liveness and recovery) scenario specs in `scripts/fixtures/campaign/` (25.05). They run on real sandbox tmux at level a. The sandbox now writes its profile into the sandbox clone, as `crew spawn` takes the repo from the profile's checkout, and installs engine stubs plus a scriptable fake forge (`gh`) in `state/bin`. `campaign-run.py` expands `{source}` and passes the stub logs and the fake forge directory to each step. A03 tears down with `kill-session` on the sandbox socket, never `kill-server` (#817). (issue #787, PR #1066, 2026-11-05) Box skill copy: none (internal campaign scripts, fixtures and doc; no template or box-skill changes).

### Changed

- **Breaking:** Release 6.0.0 is the one major cutover for the modular layout (M31: #1222, #1223, #1224, #1225, #1236), so installs and packs that name old paths must move to the new ones. Old to new paths: `scripts/crew` is `cli/crew`; `scripts/crew-config.py`, `scripts/crew-render.py` and `scripts/crew-roles.py` are under `core/`; `scripts/crew.d/*` is `environments/terminal/crew.d/*`, `scripts/crew-session.py` and `scripts/crew-proc.py` are under `environments/terminal/`, `scripts/crew-remote.py` is `environments/terminal/remote/crew-remote.py` and `scripts/session.d/<backend>.py` is `environments/terminal/sessions/<backend>/adapter.py`; `scripts/crew-harness.py` is `harnesses/crew-harness.py` and `scripts/harness.d/<engine>.py` is `harnesses/<engine>/adapter.py`; `scripts/crew-repo.py` is `connectors/github/crew-repo.py`; `packs/github/manifest.toml` is `connectors/github/manifest.toml`; and `scripts/test-*.py` is `dev/tests/<module>/test-*.py`. Shims: through every 6.x release each of the 56 moved script paths stays a compatibility shim that runs the moved file (so `scripts/crew`, `$CREW_BIN`, the Stop hook and the remote forced command keep working), an adapter left in `scripts/harness.d/` or `scripts/session.d/` is still discovered, and `packs/github/manifest.toml` stays a copy of the connector's manifest; tests have no shim, and `run-tests.py` accepts a bare test name. The shims, the old adapter discovery and the `packs/github/` copy are removed in 7.0.0, the next major release (team spec REQ-23: one major version). Pack updates: a pack's own code (connectors, harness adapters, environment defaults, skills) now loads through a `pack.toml` whose `framework` range must include the installed release, such as `">=6.0.0, <7.0.0"`, since bootstrap and upgrade refuse a pack whose range excludes it; run `crew pack test <dir>` in the pack's CI. Migration: before 7.0.0, point profiles, wrappers, hooks, `CREW_BIN`, remote forced commands and pack docs at the new paths; move a harness adapter kept in `scripts/harness.d/` into the pack as `harnesses/<name>/adapter.py`, declared under `[provides]` in its `pack.toml`; read the GitHub manifest from `connectors/github/`; and widen any `pack.toml` range that stops below 6.0.0. (issue #1226, PR #1267, 2026-11-07) Box skill copy: none.
- Tests and fixtures are organized per module: every `scripts/test-*.py` moves to `dev/tests/<module>/` by the module holding the code under test (`core`, `environments`, `harnesses`, `connectors`, or `scripts` for code not moved yet), with its fixtures beside it, and `crew_testlib.py` and the shared render fixtures in `dev/tests/`. `run-tests.py`, `crew train`'s local checks, `crew runner` and the forge-less host find tests there, and accept a bare test name. `check-repo.py` gains two checks: `test-layout` fails a test outside `dev/tests/<module>/` or a test name used twice, and `deps` enforces the team spec's dependency rules D1–D9 and the runtime-word lint over `roles/` and `protocols/`; in Python a reference is a whole repo path literal, an import of a module package or a module joined into a path. Today's known couplings are listed with a reason in `scripts/deps-baseline.txt`, which only shrinks. The builder brief's local-checks paragraph names `dev/tests/*/test-*.py`. (issue #1224, PR #1264, 2026-11-07) Box skill copy: none.
- The GitHub backend's capability declaration moves from `packs/github/manifest.toml` to `connectors/github/manifest.toml`, beside the GitHub repository checks, so the GitHub connector declares every concern operation from `connectors/github/`. `crew-config.py resolve` and `validate` and `crew-render.py` read built-in backend manifests from `connectors/<name>/`; profiles resolve to the same values and provenance (`pack:github`), and briefs render unchanged. For one release `packs/github/manifest.toml` stays as a copy of the connector's manifest, held equal to it by `test-compat-shims.py`, so org packs and tools that name the old path keep working. External org packs load as before through `--pack-manifest`, `--org-profile` or `paths.pack`. (issue #1223, PR #1263, 2026-11-07) Box skill copy: none.
- The crew CLI and its modules move out of `scripts/` into the team spec's module layout, with no behaviour change: `scripts/crew` to `cli/crew`; `crew-config.py`, `crew-render.py` and `crew-roles.py` to `core/`; the command modules, session discovery, process helpers, session adapters and remote call to `environments/terminal/` (`crew.d/`, `sessions/<backend>/adapter.py`, `remote/`); harness discovery and one adapter per harness to `harnesses/` (`harnesses/<engine>/adapter.py`); and the GitHub repository checks to `connectors/github/`. Every old path is a compatibility shim for one release that runs the moved file, and an adapter left in the old `scripts/harness.d/` or `scripts/session.d/` is still discovered for that release, so `scripts/crew`, the Stop hook, `$CREW_BIN`, the remote forced command and every documented `scripts/...` command keep working, and briefs render byte-identical except the builder's shared-plumbing list, which now names the new paths. Protocol docs, templates, role definitions, packs and the repo QA and release scripts stay where they are for now. (issue #1222, PR #1261, 2026-11-07) Box skill copy: none.
- Each session backend is now one adapter module, `scripts/session.d/<name>.py`, declaring its CLI, its place among the choices and its capabilities (`doorbell`, `reload`, `dead-keeps-pid`) beside its create, attach, doorbell, identity and state, window, kill and reload operations. `scripts/crew-session.py` discovers the modules and derives the `runtime.options.session_backend` choices and the active backend; `crew doctor` takes the CLI to look for from the adapter. The OS process helpers move out of the tmux adapter into `scripts/crew-proc.py`. `crew send`, `crew watch`, the liveness probe, the merge lock's owner check, `crew up`'s attach hint and `crew upgrade` now branch on declared capabilities and operation results instead of `name == "herdr"` or raw tmux verbs, so adding a backend means adding its module and tests. Unknown activity, unavailable probes, failed delivery and surviving processes keep their ambiguous or refusal results, and tmux and herdr behave as before. (issue #1183, PR #1259, 2026-11-07) Box skill copy: none.
- Each role is now one definition file, `roles/eng/<role>.toml`, replacing `roles/eng.toml`. Besides its existing keys it carries its identity defaults, whether a profile may leave the identity out, an optional cap with its default and minimum, its default tier, how a run completes (`completion`) and who relays its result (`relay`), the passes host placement may route, and the rendered brief bootstrap's self-test requires (`discovery`). The profile's core identity defaults, optional identities, tmux role caps, placement passes, the renderer's optional roles, `crew spawn`'s default tier, run completion, `crew route`'s coordinator relay and bootstrap's self-test derive from those files, so an auxiliary role that reuses an existing lifecycle is one definition, its brief and tests. `crew-roles.py` now validates the directory. Review, validation and land stay explicit core contracts; existing roles render, resolve and behave as before, and no gate or marker rule changes. (issue #1185, PR #1255, 2026-11-07) Box skill copy: none.
- Every eng role's shared policy now has one source in the Agent Skills format. Each role directory under `templates/policy/` (builder, reviewer, synthesizer, coordinator, researcher) has an entry `SKILL.md`, and each procedure has a `skills/<skill>/SKILL.md`. Each skill file has `name` and `description` front matter and names the fragments it is made of. Skill files never render. More repeated policy moved into fragments: the flavor header (8 builder, reviewer and Grok Bot synthesizer templates), the builder signing rule, the local-tools rule, the Grok Bot coordinator signing rule, the landing-authority-and-steering paragraph (coordinators and synthesizers) and coordinator milestone admission. A new parity test checks the skill front matter, links and fragment coverage. Every rendered brief for the default, tmux, session, parity-fixture and eng-crew profiles is byte-identical to before. (issue #1221, PR #1253, 2026-11-07) Box skill copy: none (every rendered brief is byte-identical).
- `docs/specs/portable.md` is now v0.4. It adds the four axes (roles, connectors, environments, harnesses), names runtimes environments and keeps them apart from connectors, and adds the `knowledge` concern to P2/P3. A new P11 (generic actions) references the actions contract (#1218). A new §9 specifies the generic extension mechanism: the pack format, plug-in points, config layering, install flow and conformance kit. The section 4 layout and the M15–M21 plan are marked superseded, and section 5 gains the M29–M34 slice tables. No live gate or marker rule changes. (issue #1217, PR #1241, 2026-11-06) Box skill copy: none (spec only; no template or box-skill changes).
- Role policy shared across runtime templates is now authored once. The renderer replaces a template line exactly `<include:policy/<dir>/<name>.md>` with that fragment from `templates/policy/` (pack overlay first), renders its lines like the including file's and reports problems at the fragment's own file:line; one level only, so a nested, missing or inline include fails closed. The reviewer flavor-validation, delta re-review and pass steps, the builder build-pass, CLI evidence and fix-round blocks, the synthesizer gate, land-rule and merge-train sections, and the Grok Bot landing-authority input list now each live in one fragment, while wake, delivery and worktree lines stay in the tmux, session and Grok Bot templates. Every rendered brief for the default, tmux, session, parity-fixture and eng-crew profiles is byte-identical to before. markdownlint's MD029 (ordered list prefix) is off, since an include line splits a raw template's numbered list; rendered briefs keep their numbering. (issue #1184, PR #1190, 2026-11-06) Box skill copy: none (every rendered brief is byte-identical).
- Each harness is now one adapter module, `scripts/harness.d/<engine>.py`, holding its role and coordinator launch and resume, permission modes, trust and preflight checks, process, dialog, busy, transient-error and composer rules, login check and install pointer. `scripts/crew-harness.py` discovers the modules and derives the profile's engine and coordinator choices, the executable aliases, the `crew bootstrap --harness` choices and the built-in install targets. `crew spawn`, `crew up`, `crew upgrade` reload, `crew doctor`, `crew status`, `crew watch`, `crew send` and remote readiness read the adapters and no longer name a harness, so adding a harness means adding its module and tests. Contributor-tier and engine-independence policy stay in the core, and existing harnesses behave as before. OpenCode becomes a schema-only adapter with no interactive launch, as it was before. (issue #1182, PR #1188, 2026-11-06) Box skill copy: none.
- An owner grant that is recorded, time-boxed and explicitly names gate-contract changes in its scope now satisfies per-change merge-ok for a gate-contract change, once the coordinator records a merge-ok at head citing it, per the owner's 2026-11-06 decision. Protocol §3 and §7, the gate registry, the tmux, session and Grok Bot synthesizer templates and flavors floor F6 say so consistently; the grant still supplies no approval, validation, CI or hold clearance, and `crew:sensitive`, spec and release-cut rules are unchanged. (issue #1167, PR #1170, 2026-11-06) Box skill copy: deferred to #140 (Grok Bot synthesizer template line; tmux and session render from this repo).
- `docs/campaign-harness.md` is marked `merge=union` in a new `.gitattributes`, so a local merge-up of two M25 campaign PRs that append scenario lines or notes sections at the same place keeps both sides with no manual resolution. The `.gitattributes` header and a contributor note in the page say union merge suits append-only edits only (a reorder or rewrite still needs a normal review of the merged result) and that GitHub's server-side mergeability check is not documented to honour the attribute, so the builder's local merge-up is still needed. `scripts/check-repo.py` gains an `attributes` check that fails when the line goes missing. (issue #1112, PR #1113, 2026-11-06) Box skill copy: none.
- `docs/campaign-harness.md` is restructured for append-only edits, with no content change: the committed-spec list and the fresh-sandbox list carry one scenario per line in ID order, and each scenario's notes (A06 and A07, A08 to A10, A11 and A32, A12, A20, A21, A22, A28) sit under their own heading in ID order, after the shared runner, environment, decoy and results text. A new campaign then adds lines without touching its neighbours, so merge-ups of M25 campaign PRs stop re-resolving the same line. (issue #1103, PR #1104, 2026-11-06) Box skill copy: none.

### Fixed

- Twenty unreleased changelog fragments that merged with a TBD PR number now carry their PR numbers, each taken from the merge commit that added the fragment. `scripts/changelog-cut.py` refused them, so the `release.yml` simulated cut failed on every PR touching a release file and the next release cut was blocked. (issue #1256, PR #1258, 2026-11-07) Box skill copy: none.
- A tmux synthesizer that stops on a `land` message without posting (the PR is closed or merged, or the event SHA is stale) now appends `done: #<n> <sha> stale` (`done: #<n> stale` when the message named no SHA), and that line completes the acknowledged message, so each fresh synthesizer spawn no longer replays every historical land and re-checks each PR on GitHub before the current land; `crew route` treats the stale `done:` as a terminal synthesizer line, reaping an idle synthesizer instead of waking the coordinator. (issue #1187, PR #1254, 2026-11-07) Box skill copy: none.
- `scripts/worktree-purge.py` now keeps a worktree whose path sits inside a path referenced by a run record, claim or tmux pane, with the reason `inside a referenced run`. Before, the guard matched only the exact path, so a nested worktree such as a live builder's `.crew/base` snapshot was classified `remove` and `--apply` would have deleted it. Worktrees under a protected checkout were already kept. (issue #1250, PR #1251, 2026-11-07) Box skill copy: none.
- `crew lead ensure` now creates the state root's `status/` directory before it starts a pool lead, so a fresh lead on a new install can append its first `ack:` to `$CREW_STATUS` and `crew send ... --wait-ack` sees it instead of timing out with `no ack`. Existing state roots already had the directory and are unaffected. (issue #1176, PR #1249, 2026-11-07) Box skill copy: none.
- `scripts/worktree-purge.py --apply` now fails closed. Before removing anything it checks that every `remove` row's work tree and parent are writable, and if any is not it names the paths, removes nothing and exits non-zero. A removal that still fails is reported as `failed` with git's error, stops further removals, skips `git worktree prune`, reports an `orphan` when git dropped the admin entry anyway, and exits non-zero; the summary reads `removed N, failed M, kept K`. Every run also lists `orphan` rows, a directory under a scanned root (each worktree's parent and every `--root`) whose `.git` names a missing gitdir. Before this, a failed `git worktree remove` was counted as `kept`, the run exited 0, and 32 orphaned directories went unreported. (issue #1171, PR #1172, 2026-11-06) Box skill copy: none.
- `scripts/test-docs-scan.py` no longer flakes when git's background maintenance creates or removes a transient file such as `.git/objects/maintenance.lock` during the writes-only-scan.json test: the before/after snapshot skips `.git/objects/**` and lock files under `.git/`, and the fixture repos turn off auto-maintenance (`gc.auto=0`, `maintenance.auto=false`). A regression test proves the comparison ignores that churn and still catches an extra work-tree write. (issue #1168, PR #1169, 2026-11-06) Box skill copy: none.
- The tmux crew now runs on its own server, `tmux -L <session>`, so an agent's bare `tmux` inside a crew pane (which follows the pane's `$TMUX`) can no longer take down the owner's default server or another crew; a session started before this change keeps working on the default server, named by path and never through an inherited `$TMUX`, until its next `crew up`, and `crew up` prints the `tmux -L` attach line. After a lost server, `crew up` also stops a recorded pool lead whose pane process survived (Codex ignores `SIGHUP`), matched by its recorded pid, start time and parent pid 1, and leaves every other process alone. The campaign sandbox tmux shim now lets a crew's `-L NAME` through, since its pinned `-S` socket overrides `-L`. (issue #818, PR #1165, 2026-11-06) Box skill copy: none.
- `crew:hold` now always stops dispatch: `crew route`, the reviewer pool, the scheduler's holds input, the train gate and train merge-ups block a held PR or issue whatever `runtime.options.hold_label_blocks` says, and the tmux and session builder, reviewer and synthesizer briefs drop the condition. The #111 lane-label meaning is retired; `hold_label_blocks` is still accepted but deprecated and ignored. A `new-head` or `fix-at-head` for a head that already carries the newest round's verdict, with no builder fix note or open rereview after it, now opens no new round. Before, a poll `new-head` with `hold_label_blocks = false` started review passes on held PRs #1039 and #1101, the second a round 2 at an unchanged head. (issue #1124, PR #1163, 2026-11-06) Box skill copy: deferred to #140.
- A non-GitHub backend can bind the asynchronous land by config alone: the manifest's `[land]` table now takes `change_placeholder` (the token `crew land` fills with the change id, default `n`), `head_guard = false` (the backend's land has no head-match flag; the head re-read before the request still holds) and a `[land.status]` table mapping native status output to `none`, `queued`, `landing`, `landed` or `failed`, with the new conditional `change.read-landed` reading the revision when the status line has none. Output no declared pattern matches still reads unknown and never requests a land, and `crew land` refuses a `change.land` without `<head-sha>` unless `head_guard = false` is declared. GitHub stays sync and unchanged. (issue #1042, PR #1162, 2026-11-06) Box skill copy: none.
- `scripts/run-tests.py` now starts every test file without `TMUX` or `TMUX_PANE` and with its own fresh, private, short `TMUX_TMPDIR`, removed when the file finishes, so a bare `tmux kill-server` in a test can no longer reach the caller's tmux server (follow-up to the #818 server loss). A failing file's output is also written to a retained per-file log as soon as it finishes, named on its `FAIL` line (`--log-dir` picks the directory), so an interrupted suite no longer ends with bare `FAIL` lines and no output. (issue #1156, PR #1160, 2026-11-06) Box skill copy: none.
- `crew upgrade --version` (and `crew bootstrap --version`) now finishes with a verified record when an earlier `--version --dry-run` or a busy-pass timeout already extracted the version directory. Before, `fetch` refused any existing version directory, and its "run its bootstrap directly" hint recorded the install with `bundle_sha256: null` and no `transport`; under a `url` or `mirror` source, plain `crew upgrade` then refused as a source change and `--version` refused because the directory existed, until an owner deleted it by hand (found by the M25 A20 run). `fetch` now fetches and verifies the release again into a staging directory and reuses the existing directory only when its files match (interpreter caches aside), passing the digest and transport on; a directory that differs is refused and left in place. The upgrade it starts skips the source-change refusal for that just-verified bundle and re-records a record that lost its digest or transport instead of reporting `no changes`. The A20 campaign step now expects the retry to apply with the digest and transport recorded. (issue #1089, PR #1159, 2026-11-06) Box skill copy: none.
- `crew train check` and `crew train land` now block a PR that has a later
  changes request at head (protocol §7): a `steer cmd=rework` marker at head, or
  a reviewer-identity `CHANGES_REQUESTED` review, posted after the passing
  verdict. Before, both passed and land squashed the PR; only a changes verdict
  marker at head was caught. A fresh verdict at head answers the request. (issue #1118, PR #1154, 2026-11-06) Box skill copy: none.
- The Claude Code turn-end guard Stop hook now names the resolved bundle path, and `crew up`, `crew bootstrap` and `crew upgrade` re-point any existing crew guard for the same state instead of appending another. Before, `crew up` through the `paths.eng_crew` link added a second guard naming the link, and each upgrade added one for the new bundle, so `.claude/settings.local.json` no longer matched its `install.json` hash and every later `crew bootstrap` or `crew upgrade` refused with `target edited or unowned` (found by the M25 A20 run on #796). (issue #1088, PR #1153, 2026-11-06) Box skill copy: none.
- `campaign-run.py` no longer passes the operator's forge tokens (`GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`) or SSH agent (`SSH_AUTH_SOCK`, `SSH_AGENT_PID`) into sandbox scenario steps, and points `GH_CONFIG_DIR` at `<state>/gh-config`, so a step that calls `gh` by absolute path or `git` over SSH cannot use the owner's live credentials. (issue #1106, PR #1152, 2026-11-06) Box skill copy: none (campaign runner script, its test and the harness doc; no template or box-skill changes).
- `crew spawn` now drops a builder or reviewer run's own `schedule decide` reservation (same pool, its `#issue` or `#PR` ref) as soon as the run starts. Before, `live_reservations` ended a grant only when a later decision saw a busy worker on the ref or one started since the grant, so a pass that started and was reaped between two decisions revived as a live reservation and held a pool slot until `reservation_ttl` (600 seconds), deferring other PRs with `cap` and no worker running (#1070, found by the M25 A07 run). Expired reservations were already ignored on `main`; spawn failures still leave the grant for the lead's `crew schedule release`. (issue #1050, PR #1150, 2026-11-06) Box skill copy: none.
- `crew watch` now runs the triage sweep timer after each scan's `--source` commands instead of before them, so the timer's empty-queue check reads the `triage/queue.json` that scan's `crew poll` just wrote. Before, on the first scan after the machine resumed, the timer read the pre-pause queue, recorded the overdue slot as `skipped: empty queue`, and left the issues opened during the pause waiting a full `interval_hours` for their sweep. (issue #1098, PR #1149, 2026-11-06) Box skill copy: none.
- `crew upgrade --yes` now reloads roles on real tmux instead of destroying the first role's window. The reload stopped the pane's process group, which was the window's only process, so tmux removed the window and the following `respawn-window -k` failed with `can't find window`, leaving the new install recorded with no role reloaded. Each reload now sets the window's `remain-on-exit` before the stop and unsets it after the respawn, so the window survives and every role restarts in place, coordinator last. A new test runs the reload against a real tmux server on a private socket. Found by the M25 A20 run on #796. (issue #1087, PR #1148, 2026-11-06) Box skill copy: none.
- `crew host check` can now report a remote host `ready` against the real entrypoint. `crew-remote.py` builds the `check` verb: it returns the `tools`, `project mirror`, `logins`, `runner` and `capacity` rows, the prepared `projects` and the `load` (jobs still running). `inspect_host` now sends the request through the hardened, versioned `call()`. Before, the entrypoint refused every check, first for version skew and then as `verb check not built`, so `crew host prepare` on a forge-less host exited 1 after a good seed and `crew runner run` without `--host` never picked a host. A new test runs `crew host prepare` and `crew host check` through a loopback `ssh` that execs `crew-remote.py` and shows the forge-less host `ready`. `--fix` still repairs nothing on a remote host; each failing row's hint names the step. (issue #743, PR #1117, 2026-11-06) Box skill copy: none.
- `crew train check` no longer treats an `evidence/` path quoted in a PR body or builder fix review as a required artifact. Fenced code blocks and code spans are quotes: a path inside them is ignored, such as `` `![R1](evidence/r1.png)` `` in a table cell, a rule name like `` `evidence/citation` `` or a path in a `sh`/`text` capture. The documented citation forms still count: a link or image, a code span holding just one artifact-shaped `evidence/` path (a subdirectory or a file extension, like `` `evidence/1/dir` `` or `` `evidence/run.log` ``), or a bare file path in prose. Found when #1080's body blocked its land. (issue #1102, PR #1110, 2026-11-06) Box skill copy: none.
- `crew train check` no longer blocks the evidence gate for good when a PR body cites an `evidence/` path that is not in the head tree. A builder `pass=fix` or `pass=ci-fix` review at head that carries an inline `sh`/`text` reproduction now supersedes the stale body paths: the gate reports `manual` ("missing artifacts superseded by inline fix proof at head: ...; verify the proof and validation") instead of `blocked`. The body is never edited and `evidence/` cannot be committed, so the block used to leave the PR no way out, although verification Q5 counts the inline proof and treats a path as no evidence. With no inline proof in a head-bound fix review, or proof only in the body, a missing path still blocks. Found by the M25 A12 run on #791. (issue #1079, PR #1085, 2026-11-05) Box skill copy: none.
- `crew train check` now reports the evidence gate as `manual` when the only proof is a GitHub user-attachments image or video URL in `## Acceptance Evidence` or a head-bound builder fix review, the media form the protocol requires for web and mobile changes. Before, it reported `blocked` ("no evidence artifacts or reasoned N/A"), so a correct web-only or mobile-only PR never entered a train. Other media hosts, and URLs outside those posts, still block. (issue #1078, PR #1084, 2026-11-05) Box skill copy: none.
- Priority class 1 (a fix for a red default branch) is now reachable: the scheduler's tracker read takes each open issue's title and records the open `main-red` issues as `red_fixes`, and `rank` (so `crew schedule decide`, the target growth check and the summary) defaults to that set, ranking a build of such an issue, and a fix or ci-red round on a PR whose run record names it, ahead of every recheck, merge-up, validation and review. Before, `decide` never passed `red_fixes`, so a red-main fix ranked as an ordinary class 6, 7 or 8 item and could wait behind the review queue whenever the target was tight. The coordinator brief, the protocol land rules and the tmux runtime now title the blocking fix issue `main-red: <summary>`, and the scheduling inputs table lists the new input. (issue #1072, PR #1081, 2026-11-05) Box skill copy: deferred to #140 (tmux coordinator template only; Grok Bot renders unchanged).
- `scripts/check-skill-drift.py --project` (render-vs-live mode) now compares each section exactly: any difference in the raw section text, including an edited multi-word command span, a changed HTML comment or appended live-only text, is DRIFT (exit 1), and the doc-vs-skill heading exclusions no longer apply, so a live-only section under one of those headings is EXTRA (exit 1), printed with its first differing words as `render:` and `live:`, where it used to pass as WORDING because only single-word code spans and quantities counted as key facts. Doc-vs-skill mode keeps its WORDING tolerance unchanged. Found by the M25 A02 run on #786. (issue #1064, PR #1069, 2026-11-05) Box skill copy: none.
- A reviewer that stops with `done: #<n> stale` because its PR merged or closed is now reaped once, keeping its section files, whoever merged it, another runtime or GitHub account included. `crew route` returned early on every `stale` line, and the reviewer lead could not match it to a PR and head, so the run record kept its reviewer slot until a manual reclaim; a replay after the reap now retires. (issue #811, PR #1065, 2026-11-05) Box skill copy: none (tmux CLI only; no template changes).
- A dependency merge now wakes the coordinator within one watcher poll instead of waiting for the 30-minute backstop: on `pr-merged`, `crew route` still runs the mechanical close-out, then lists open issues and, when any `Depends on` block names the merged PR or an issue it closes, leaves the wake queued with `consumer=coordinator` and `dependents` (the waiting issue refs) so the coordinator dispatches the unblocked work at once. `crew watch` now ignores route's added notes (`consumer`, `dependents`) when it matches a kept record against the wake it routed, so the annotated record still ends the scan and wakes window 0; before, any record route annotated looked new and the watcher slept on. A merge nothing depends on is still consumed without a coordinator turn; a failed issue read leaves the wake queued, so the coordinator is woken rather than missed. (issue #814, PR #1063, 2026-11-05) Box skill copy: none.

## [5.3.0] - 2026-11-05

### Added

- The project docs pass now runs (M26.1 P3, `docs/project-docs.md`): with `[docs] enabled`, each `crew watch` scan runs a docs-pass timer that, once `interval_days` passed since the last slot in `docs/pass.json` (at once when a crew wakes with a pass overdue), fetches the default branch, runs `scripts/docs-scan.py` on the project's own checkout and starts `crew spawn researcher --docs-pass`, recording `skipped: scan unchanged` without a session when the scans (head, date and banner ages left out) match the last started or queued pass. `crew spawn researcher --docs-pass` starts a `riley-docs` window whose Item names each repo's scan.json, shares the `researchers` cap and queue, and is refused unless `docs.enabled` is true. The tmux researcher brief gains a Docs pass section that runs stages 2–4 of `docs/project-docs.md` on each scan (duplicated rules, contradictions and removed behaviour; structural drafts, one per unit of work, contradictions as separate correction drafts): read-only, with no edits, PRs, issue filing or labels beyond opening the repo's one `docs:log` issue, `path:line` citations at the head SHA, no re-proposal of a rejected draft until its cited text changes, and quiet passes posting nothing; it stays under the researcher brief's size budget. Protocol §4 defines the `pass=docs-pass` record on each `[Riley/docs-pass]` comment, a note and never a gate input. (issue #1026, PR #1058, 2026-11-05) Box skill copy: deferred to #140.
- `scripts/docs-scan.py`, the zero-model first stage of the project docs pass: for each `[docs] repos` entry it reads a local clone's git tree at the default-branch head (or a pinned `--ref`) and writes `<state-dir>/<owner>__<repo>/docs/scan.json` with the Markdown inventory (lines, docs index row and kind, status banner), essentials missing against the project doc set and `[docs] homes` (a `path#anchor` home needs that heading), design docs with no banner, banners whose Last checked is missing or older than `stale_days`, broken relative links and anchors, and docs over `size_budget`. Read-only: it reads git objects only and writes nothing but each scan.json; with no `[docs]` table it does nothing. (issue #1025, PR #1049, 2026-11-05) Box skill copy: none.
- Profile: an optional `[docs]` table for the project docs pass (`enabled`, off by default, `interval_days`, `repos`, `stale_days`, `size_budget` and `homes`), checked by `crew-config.py validate` (types, minimums, non-empty `owner/name` repos, `homes` keys limited to the five essential docs with repo-relative `path` or `path#anchor` values) and given its defaults by `resolve` only when the table is present. The essential doc set and the status banner convention moved from the project docs design into a new `docs/project-doc-set.md` reference module the profile links. (issue #1024, PR #1044, 2026-11-05) Box skill copy: none.

### Changed

- The onboarding runbook's whole Rollback and offboarding section moves verbatim
  into the new module `docs/runbooks/offboarding.md` (M26 modular organization,
  batch 3), keeping the bootstrap uninstall preview and apply, unlanded-run and
  edited-target preservation, the Grok Bot manual routine removal and
  `--routines-removed` retry, the human settings steps and held-PR disposition,
  then all nine manual steps in order with every fence, condition, routine ID,
  archival and hand-back and recording instruction; the runbook keeps the exact
  Rollback and offboarding heading as a direct module link, so incoming links
  still resolve; the module gets its deliverable manifest, inventory and catalog
  rows; it moves documentation only and runs no offboarding command; no rule,
  gate, marker or default changes. (issue #908, PR #1059, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's command-value paragraph moves into
  `docs/runbooks/prerequisites.md` under `Command values`, keeping the
  profile-derived and output-derived value qualifications and the target-repo
  rule, and its tmux runtime command-convention paragraph moves into
  `docs/runbooks/tmux-onboarding.md` under `Command conventions`, keeping the
  Grok Bot and tmux distinction, the `crew` path and the absolute
  `CREW_PROJECT` export with the tmux binding link (M26 modular organization,
  batch 3, folded-in #909); only the wording that pointed at the runbook's own
  position changes; the runbook links both subsections and the tmux module's
  introduction points to its local conventions; no rule, gate, marker or
  default changes. (issue #908, PR #1059, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook `docs/runbook-new-repo.md` is now a navigation entry
  (M26 modular organization, batch 3, folded-in #909): it keeps its H1, purpose,
  read-first links, runtime choice and prerequisite-before-steps order, and all
  33 original H2 and H3 headings verbatim and in order, including the batch 1
  and 2 redirects; each heading now carries only a direct link to its
  destination module section instead of an inherited procedural summary, and
  no command fence, checklist, table, example or Known gaps text remains in the
  entry; every incoming link to a runbook anchor still resolves; no rule, gate,
  marker or default changes. (issue #908, PR #1059, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Verification checklist` moves intact into
  `docs/runbooks/onboarding-proof.md` (M26 modular organization, batch 3,
  folded-in #906), with its evidence-file and no-token opening, the V2 and S1
  merge-up check, every P1–P3 and 1–23 row with its evidence and pass
  conditions, the Grok-specific rows and parity label, and the complete item-20
  GraphQL fence; the runbook keeps the exact heading as a direct module link,
  and the moved `#step-*` links and row 23's rollback reference point at the
  runbook entry; no rule, gate, marker or default changes. (issue #904, PR #1048, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Expected event and marker sequence` and `Optional
  steering smoke test` move verbatim into `docs/runbooks/onboarding-proof.md`
  (M26 modular organization, batch 3, folded-in #905), with the whole stage
  table including the conditional iterate row 9a, its events, channels, markers
  and rounds, the timestamp and evidence condition, the round-1 expectation and
  two-nudge limit, and the live-dispatcher-only steering check; the runbook
  keeps both exact headings as direct module links; no rule, gate, marker or
  default changes. (issue #904, PR #1048, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Step 8: first test issue` opening and its
  `Template issue` move verbatim into the new module
  `docs/runbooks/onboarding-proof.md` (M26 modular organization, batch 3), with
  the trivial docs-only choice, the full Markdown issue fence (goal,
  acceptance criteria, out of scope, role and tier hint), the credential,
  creation and assignment fence, the label-then-assign event ordering and the
  milestone, Project and closing-keyword qualifications; the runbook keeps both
  exact headings as direct module links and names the expected sequence and
  checklist as still below; the module gets its deliverable manifest,
  inventory and catalog rows; no rule, gate, marker or default changes. (issue #904, PR #1048, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Evidence timeline` and `Known gaps` move verbatim
  into `docs/runbooks/onboarding-proof.md` (M26 modular organization, batch 3,
  folded-in #907), completing the onboarding proof module: the full timeline
  table, the one-timezone, fix-round, merge-up and nudge row instructions, the
  gap-filing rule, and every known gap, link and limitation unchanged apart
  from relative-link prefixes; the runbook keeps both exact headings as direct
  module links; no rule, gate, marker or default changes. (issue #904, PR #1048, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Step 6: state dir and wiring doc` opening and its
  four setup items move verbatim into the new module
  `docs/runbooks/grok-onboarding.md` (M26 modular organization, batch 3), with
  the `VERSION`, install, profile and pending-human-step checks, the
  bootstrap-owned file restrictions, the deployed versus manual-fallback
  distinction and the complete manual setup fence, the `wiring.md` sources and
  status transitions, the reviewer-engine ownership and private-repo condition
  and the README-seed safety requirement; the runbook keeps the exact Step 6
  heading as a direct module link and the worked example and Step 7 stay below;
  the module gets its deliverable manifest, inventory and catalog rows; no rule,
  gate, marker or default changes. (issue #900, PR #1047, 2026-11-05) Box skill copy: none (docs-only).
- The rest of the onboarding runbook's Step 7, the per-routine details and the
  `Steering wiring` and `Cutover for existing open PRs` subsections, moves
  verbatim into `docs/runbooks/grok-onboarding.md` (M26 modular organization,
  batch 3, folded-in #903), with all B1 to A3 details, the record and live-date
  instruction, the assigner, author and commenter distinctions, the parent and
  watch IDs and full-SHA requirements, the complete cutover exemption, its end
  and the hold-and-ping qualification and the no-body-edit instruction; the
  runbook keeps the exact Step 7 parent with a direct per-routine-details link
  and both exact child headings as direct module links; no rule, gate, marker
  or default changes. (issue #900, PR #1047, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Step 7: listener wiring per bot` opening, through
  both routine ownership and creation-order tables, moves verbatim into
  `docs/runbooks/grok-onboarding.md` (M26 modular organization, batch 3,
  folded-in #902), with the rendered and hand-fill routine origins, the linked
  Grok Bot cross-runtime limits, the merge-up distinctions and `pass=ack`
  exclusion, the five rules for all routines, both full tables, the parent-turn
  creation and verification and the lighter-lane qualification; the runbook
  keeps the exact Step 7 heading as a direct module link and names the
  per-routine details, steering wiring and cutover as still below;
  `scripts/test-render-parity.py` reads the cross-runtime-limits link from the
  module instead of the runbook; no rule, gate, marker or default changes. (issue #900, PR #1047, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's complete `Filled-in wiring.md (derived from the
  template)` subsection moves verbatim into `docs/runbooks/grok-onboarding.md`
  (M26 modular organization, batch 3, folded-in #901), with the entire
  four-backtick worked-example fence, its inner headings, tables and
  placeholders, the pilot-observation-versus-default qualification, the routine
  IDs and event exclusions and the trailing note on template sections 3, 5, 6
  and 7; the runbook keeps the exact heading as a direct module link; the
  template and example claims are unchanged; no rule, gate, marker or default
  changes. (issue #900, PR #1047, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's Step 5 opening and its items 1 to 3 move verbatim
  into the new module `docs/runbooks/product-preflight.md` (M26 modular
  organization, batch 3), with the before-routines-live condition and the wiring
  doc section 0 destination, the automation discovery commands and ownership
  decision, the product label, command and E2E PR ignore rules, and the full
  fork PR handling (no-token sandbox, workflow approval wait, author-gated
  steering, no builder pushes to forks, upstream-sync limitation, fork workflow
  secrets); the runbook keeps the exact Step 5 heading as a direct link to the
  module's subsection and names items 4 to 8 as still below; the module gets its
  deliverable manifest, inventory and catalog rows; no rule, gate, marker or
  default changes. (issue #898, PR #1046, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's Step 5 items 4 to 8 move verbatim into
  `docs/runbooks/product-preflight.md` (M26 modular organization, batch 3,
  folded-in #899), keeping their original numbering, the full workflow search
  fence and the push CI preservation and verification condition, the closing
  keyword and title convention rules, the toolchain environment and Step 0
  re-render condition, the open item cutover decision and link, and the shared
  deploy secret names and hosts with the linked sync AC; the runbook keeps the
  exact Step 5 heading, now linking both completed module subsections; no
  workflow, secret, toolchain, rule, gate, marker or default changes. (issue #898, PR #1046, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's Step 4 opening and items 1 to 4 move verbatim into
  the new module `docs/runbooks/github-ci-protection.md` (M26 modular
  organization, batch 3), with workflow and trigger discovery, the push-CI
  check on the default branch and its after-merge `ci-failed` listener
  condition, noisy-job handling, exact required-check naming and the aggregate
  check qualification, and the protection, ruleset and merge-settings reads with
  the normal 404; the runbook keeps the exact Step 4 heading as a direct module
  link and names items 5 to 7 as still below; the module gets its deliverable
  manifest, inventory and catalog rows; no rule, gate, marker or default
  changes. (issue #895, PR #1043, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's Step 4 items 6 and 7 and its final capture
  instruction move verbatim into `docs/runbooks/github-ci-protection.md` under
  `Merge settings and enforcement limits` (M26 modular organization, batch 3,
  folded-in #897), keeping numbering 6 and 7, the PR-branch versus
  default-branch merge distinction, the full settings command, the
  shared-account enforcement limitation, the merge-enforcement link and the
  instruction to capture the outputs of items 1 to 6; the runbook keeps the
  exact Step 4 heading with direct links to discovery, protection choice and
  merge settings; no rule, gate, marker or default changes. (issue #895, PR #1043, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's Step 4 item 5, the owner's protection choice, moves
  verbatim into `docs/runbooks/github-ci-protection.md` under `Protection
  choice` (M26 modular organization, batch 3, folded-in #896), keeping item
  number 5, the three protection levels and their costs, owner choice and
  reversibility, the complete protection JSON, apply and remove fence, the
  `app_id` explanation, the stale-approval rationale and the default-branch
  workflow warning; rollback links through the stable runbook entry; the
  runbook's Step 4 links the subsection and names items 6 and 7 as still below;
  it moves documentation only and applies no settings; no rule, gate, marker or
  default changes. (issue #895, PR #1043, 2026-11-05) Box skill copy: none (docs-only).

## [5.2.0] - 2026-11-05

### Added

- Profiles now accept `runtime.name = "session"` for a hosted or hand-started
  coordinator session whose workers run as native subagents or external
  harness CLI runs. Its options are `max_active_milestones`, `session_backend`
  (`native` or `cli`), the `builders` and `reviewers` pool limits, and the tmux
  land-policy options the synthesizer brief renders. `crew-render` writes the
  full session brief set: the coordinator and new builder, reviewer and
  synthesizer briefs, each one pass per run and ending where the coordinator
  appends the `crew brief` run block. The session synthesizer serializes lands
  with an atomic `mkdir` lock under the state dir, since `crew land-lock`
  accepts tmux profiles only. A new `<control-item:set>` /
  `<control-item:none>` template block renders only with or without
  `repo.control_item` (a tracker-native item counts), so a profile with no
  control item gets a coordinator brief without inert ownership and handoff
  text. The example profile is `profiles/session.toml`. tmux and Grok Bot
  profiles validate, resolve and render as before. (issue #914, PR #1040, 2026-11-05) Box skill copy: none (no Grok Bot template or render changes).
- Added the project docs consolidation design (`docs/project-docs.md`, M26 Track B): the essential doc set every crew-run project should have with profile-mappable homes, the design-doc status banner convention, an opt-in docs pass (a zero-model scan plus a read-only researcher session) that drafts structural issues for the coordinator, the proposed `[docs]` profile table, host options and alternatives, and the build issues that implement it. Design only; it adds no rule until those land. (issue #754, PR #1029, 2026-11-05) Box skill copy: none.

### Changed

- The tmux coordinator brief no longer restates the owner-feedback intake recipe. On owner feedback it now reads and follows the self-improve Owner-feedback recipe in full before filing a card, and it points to the reading-paths trigger table. The recipe already holds every qualifier the restatement carried. The brief is shorter and no rule changed (#676 row 8). (issue #766, PR #1027, 2026-11-05) Box skill copy: deferred to #140 (tmux coordinator template only; Grok Bot renders unchanged).
- The onboarding runbook's `Step 3: create Milestones and link a GitHub Project
  (v2)` moves verbatim into the existing module `docs/runbooks/github-tracking.md`
  (M26 modular organization, batch 3), with milestone use and freeze, the board
  status responsibilities, all five Project setup and verification units, the
  scope refusal and delegation, the empty-project-only GraphQL option
  replacement, the expected four statuses and linked-project output, and the
  wiring records; the runbook keeps the heading and anchor between Steps 2 and 4
  as a direct module link, and the module's Step 3 pointer becomes a local
  section link; no rule, gate, marker or default changes. (issue #891, PR #1023, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's Prerequisites opening and its `Identities` and
  `Per-identity gh usage` subsections move verbatim into the new module
  `docs/runbooks/prerequisites.md` (M26 modular organization, batch 3,
  folded-in #892), with the do-not-start and evidence condition, the author
  and reviewer roles and different-account restriction, the setup-admin qualification, the
  account-switch prohibition, both credential-selection fences, the shell-export
  and no-token-recording rule and the identity checks; the runbook keeps the
  three exact headings as direct module links and names Token scopes, Shared
  state dir and Other prerequisites as still below; the module gets its
  deliverable manifest, inventory and catalog rows; no rule, gate, marker or
  default changes. (issue #891, PR #1023, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's `Shared state dir` and `Other prerequisites`
  subsections move verbatim into `docs/runbooks/prerequisites.md` (M26 modular
  organization, batch 3, folded-in #894), with the entire six-row state table,
  the external, writable and no-credential constraints, the Step 6 and Step 0
  links, the reviewer engine and private-repo conditions, the pinned-toolchain
  requirement and the human approvals; the runbook keeps both exact headings as
  direct module links and its Prerequisites parent now routes all five
  prerequisite subsections to the module; no rule, gate, marker or default
  changes. (issue #891, PR #1023, 2026-11-05) Box skill copy: none (docs-only).
- The onboarding runbook's complete `Token scopes` prerequisite moves verbatim
  into `docs/runbooks/prerequisites.md` (M26 modular organization, batch 3,
  folded-in #893), with the whole identity and scope table, the fine-grained
  equivalents, the scope-inspection command, both missing-Project-scope options
  with their active-account and browser qualifications, the pilot delegation
  example and the required-Project, no-skip condition; the runbook keeps the
  exact `### Token scopes` heading and anchor as a direct module link, so
  existing `#token-scopes` links still resolve; no rule, gate, marker or default
  changes. (issue #891, PR #1023, 2026-11-05) Box skill copy: none (docs-only).

### Fixed

- A pack that does not run the researcher, or whose markers backend declares
  `markers.write-item` unsupported, no longer fails the render on the
  researcher brief or needs a copied template overlay. `runtime.options.researchers`
  now accepts `0` to run no researcher: the render skips the researcher's
  registry templates and so needs none of its operations, and `resolve` refuses
  `researchers = 0` with `triage.enabled = true`. A new `<op:a.b|c.d>` operation
  placeholder renders the first listed operation the backend supports; the
  researcher brief records its finding with `markers.write-item`, else
  `tracker.comment`. Profiles that run the researcher on a backend with
  `write-item`, including the tmux and Grok Bot profiles, validate, resolve and
  render as before. (issue #926, PR #1038, 2026-11-05) Box skill copy: none (the GitHub render is byte-identical).
- `docs/triage.md` no longer hard-codes a decision-log issue number. The triage sweep reads owner decisions from the project's decision-log issue, the tracking issue that `away-control.json` names (protocol §6 Owner away mode), and from the item. #110, the issue it first named, was closed on 2026-11-05, and the decision log moved to #985. Links to past #110 comments stay as history. (issue #986, PR #1022, 2026-11-05) Box skill copy: none (docs-only).

## [5.1.0] - 2026-11-05

### Added

- Content rules for the sensitive class are now in force (#879 slice B3).
  `change.read-diff` is a conditional operation: the GitHub manifest declares
  it and the backend map binds it to a `git fetch` of the PR head and a
  `git diff --no-renames` against the merge base, and `resolve` requires it
  only when a profile declares `[[sensitive.content]]` rules. `crew-config.py
  sensitive --paths-only` classifies an issue's named paths at triage with
  path rules only, so content rules no longer stop triage. The tmux builder
  and Grok Bot builder briefs pipe the worktree diff to `sensitive --diff`
  when content rules exist, the tmux coordinator uses the backend's
  `read-diff` and `--paths-only` at triage, and the triage template passes
  `--paths-only`. The protocol Sensitive class wording is operative: an owner
  override covers its recorded path matches and its recorded content matches
  by rule and path, and a new pair on any push needs the owner's
  reconsideration. Profiles without content rules classify as before. (issue #935, PR #1017, 2026-11-05) Box skill copy: deferred to #140.
- `crew bootstrap --harness` installs a pack's `pack.harness` registry
  entries for the selected harnesses (slices B2 and B3 of #883): `copy`
  writes the source bytes, `pointer` writes one `Read <source> and follow
  it.` line, and a Codex `launch_note` extends the printed launch prompt.
  Every registry target gets the built-in refusals (tracked, symlinked,
  edited or unowned, all listed before any write), an anchored exclude line
  and a target hash; `install.json` gains `harness_pointers` only when a
  registry target installs. `crew upgrade` re-plans on a changed registry or
  source even with an unchanged render and tag, rewrites unchanged targets,
  reports edited ones as `drift:` without writing, and removes unchanged
  targets of dropped entries. Uninstall now also removes the anchored exclude
  lines bootstrap writes. Without a registry, output and `install.json` are
  unchanged. (issue #965, PR #1016, 2026-11-05) Box skill copy: none (scripts and reference docs; no rendered template change).
- The ownership guard, every `crew handoff` action and `crew doctor` read
  and post a tracker-native control item, such as `OPS-1042`, only through
  the markers backend's `read-item` and `write-item` (F2–F4 of the
  tracker-native control item design). `crew up` records `write-item`
  beside `read-item`. A string id fills `<control-item>`, never `<n>`.
  `read-item` may print native posts (`author`, `body`, `created`, optional
  `id`) or the GitHub comment shape; a mixed or incomplete output is
  unreadable. A failed post is uncertain, so the core re-reads before
  posting again. With a non-GitHub tracker or change backend, the manifest,
  reconcile, ack, stopped and lift read open items, changes, heads, the
  default-branch head and in-transit markers through declared operations
  (new conditional `change.read-branch-head` and `tracker.unlabel`) and
  make no `gh` call. Manifest items, run records, claims and `holds_added`
  carry native ids as strings, and the doctor row prints the id as
  written. GitHub calls and output are unchanged. (issue #937, PR #1009, 2026-11-05) Box skill copy: none (scripts and reference docs; no rendered template change).
- Asynchronous land, persisted intent and restart (#873 slice B3). `crew land
  request` records a land intent keyed by change and head before its first
  status read, and `landed` prints the merge record's landed revision and a
  `pass=merge` marker with `sha=` the checked head and `landed=` the landed
  revision. New `crew land resume` reads the status of every recorded intent
  on a wake and never requests: an in-flight land resumes polling, a landed
  one prints its pending record, and a never-requested one is dropped. New
  `crew land done` clears an intent only once it is marked landed. Protocol §7
  states the asynchronous land record and restart rules. Asynchronous land,
  rendered and gated (#873 slice B4). With `land.mode = "async"`, the tmux
  synthesizer brief's step 3 renders `crew land request`, the merge record and
  `crew land resume` from `<op:>` tokens, and the builder brief runs
  `change.publish` after opening when the backend declares `land.opens_draft`.
  `land.serializes` takes no land lock (C7) and `land.tests_against_tip` meets
  tested-with-default-branch by the backend's land check; the Land rule then
  lands every ready PR alone, and `crew train build` and `bisect` refuse,
  naming that key. Every completion, including one found by `crew land
  resume`, checks default-branch CI at the landed revision before `crew land
  done`. A bare `async` changes no gate. Protocol §7, its gate registry and
  the tmux C7 row name the backend alternatives. Sync renders, GitHub
  included, stay byte-identical; Grok Bot still refuses `async`. (issue #931, PR #1008, 2026-11-05) Box skill copy: deferred (standing owner mirror deferral, #985; protocol §7 and tmux template wording, no live Grok Bot behaviour change since Grok Bot refuses async).
- Owners can give feedback on any triage record, shadow or applied, by
  replying on the item with `triage: accept`, `triage: reject <reason>` or
  `triage: adjust priority=P2 type=bug`; a signed `[Ash/decision]` quoting the
  owner's words and time counts the same, on the item or naming it on the
  decision log. `crew poll` now queues an item for that feedback even after an
  applied record placed it, and the triage sweep records it as
  `owner-accepted`, `owner-rejected` or `owner-adjusted`, reverting or
  correcting the applied record's reversible changes and backfilling relayed
  answers it missed. `triage-metrics.py` counts the feedback in accuracy and
  the override rate, reports it per sweep (`report --sweep`), and adds
  `rolling`, which scores the newest 10 owner answers on applied records and,
  below 8 accepted, proposes a return to shadow mode. In apply mode the first
  sweep each day asks for 3 spot checks. No gate, flavor, merge-permission or
  owner-config change. (issue #835, PR #1007, 2026-11-05) Box skill copy: deferred to #140.
- `scripts/crew-config.py sensitive` runs a bound `classify.sensitive`
  extension beside the built-in rules (#880 slice B2). The extension reads
  the same stdin and its matches and content records are added, rule names
  prefixed `<pack>:`; it can never clear a built-in match. A nonzero exit, a
  timeout (120 s) or output that breaks the shared JSON contract adds a line
  to a new `errors` field and makes the result `crew:sensitive`, exit 0.
  `errors` appears only with an extension bound. Without one, output and exit
  codes are unchanged. The tmux and Grok Bot briefs now reach the classifier
  through `<op:classify.sensitive>`, which always renders the core command, so
  a pack binding never replaces the built-in run and the default render is
  byte-identical (#880 slice B3); the protocol's Sensitive class wording for
  extensions is in force. (issue #962, PR #1006, 2026-11-05) Box skill copy: deferred to #140 (protocol Sensitive class wording; rendered briefs byte-identical).
- A backend that declares `[strategy] update_from_base = "rebase"` now gets
  rebase wording and no merge trains (#874 slices B2 and B3). The renderer
  reads the resolved strategy: template lines prefixed `<strategy:merge>` or
  `<strategy:rebase>` render only under that strategy, the new
  `<tested-update>` placeholder fills the synthesizer's
  tested-with-default-branch row, and the builder precheck's fresh-base step
  says "rebase onto the default branch and upload" for an existing PR. The
  tmux builder, solo and synthesizer briefs and the Grok Bot builder and
  synthesizer briefs carry the rebase lines. Protocol hard rules, precheck step
  1 and verdict portability now read the declared strategy, and `crew train
  build` and `crew train bisect` refuse on a rebase backend before creating any
  clone, branch or PR. GitHub and every manifest without `[strategy]` stay
  `merge`, and their renders are byte-identical. (issue #952, PR #1001, 2026-11-04) Box skill copy: deferred to #140.
- Release sources slice B3: `[install] source = "git"` works in `crew
  bootstrap --version` and `crew upgrade --version`. The tag is fetched into
  a temporary bare repository with no checkout and no hooks, refused unless it
  peels to the pinned `git_commit`, and only then built by that commit's own
  `scripts/release-bundle.py`; the built bundle passes the same member,
  `VERSION` and entry point checks before it moves into place, and
  `install.json` records the commit. No `gh` call is made. Slice B4: with an
  `[install]` table, `crew host prepare` sends the primary's `install.json`
  (tag, bundle digest, transport) as a toolkit pin in the `prepare` and `seed`
  calls, and the host installs that release into `toolkit/eng-crew-<v>/` from
  the same source with the same verifier, staging it first and writing its
  record (pin, digest, SHA-256 of every file) last; a verified existing
  version is reused and a tampered or partial one is installed again; the
  active version is replaced only after the new one verifies, so a refused
  release leaves the previous install usable, and the entrypoint writes no
  bytecode into the toolkit it runs from, so running it keeps the toolkit
  verified. Slice
  B5: `crew host check` then adds a required `toolkit` row, from the `version`
  call with the pin, that fails when the project pins no toolkit or another
  tag on the host, or the version's record or any file hash differs; `crew
  host prepare --prune` removes the toolkit versions and staging leftovers no
  project on the host pins and lists them. Without `[install]`, host prepare
  and check send no pin and print the same output as before. (issue #945, PR #1000, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- The tmux `runtime.options.mirror = "none"` setting now reaches the
  synthesizer brief and the protocol, slice B3 of #877. A new `<mirror-gate>`
  render placeholder fills the synthesizer's mirror paragraph from the
  setting: `live-copy` or unset renders today's standing-deferral paragraph
  byte for byte, and `none` says instead that the mirror gate is `n/a` by
  profile, to record `Mirror: n/a (profile)` on direct lands, to list no
  mirror item in gate-status, never to wait on or ask for a mirror or
  deferral, and to ignore `crew:needs-mirror`. The protocol §7 gate registry
  row and No mirror hold bullet name the setting, the tmux runtime options
  table gains the `mirror` row, and the tmux design section is no longer
  marked proposed. The reviewer and coordinator briefs carry no mirror
  instruction under either value, and Grok Bot wording is unchanged. The
  setting supplies no approval or merge permission. (issue #942, PR #998, 2026-11-04) Box skill copy: deferred to #140.
- The #398 spec grant scope is in effect. A spec change is one carrying
  `crew:spec` or with any changed path, both rename paths, matching
  `spec.paths` (default `docs/specs/**`). `crew train check` and
  `crew train land` now classify every member this way, including ordinary
  crew-lane changes: a spec change needs the owner's merge-ok at head unless
  `runtime.options.merge_grant_scope` lists `spec` beside a standing
  `merge_grant`, and an unreadable path set blocks. Sensitive spec changes and
  open rereviews stay excluded. Express eligibility reads the same
  definition: a path-only spec change needs an `Owner override:` record, as
  `crew:spec` does, before `crew train build` admits it on its selfgate. A merge record that used the grant for a spec
  change names the grant and says it covered a spec change. The tmux
  synthesizer brief renders `<merge-grant-scope>` and `<spec-paths>`. With
  neither key set, a labelled or `docs/specs/` change needs merge-ok as the
  protocol already required, and non-spec records are unchanged. (issue #928, PR #996, 2026-11-04) Box skill copy: deferred to #140.
- `crew-config.py sensitive --diff` reads a `git diff --no-renames` unified
  diff on stdin and classifies it (#879 slice B2): path rules run on every old
  and new path, and `[[sensitive.content]]` rules match added and removed
  lines, reported as `content` records (rule, path, side, line) beside
  `matches`. Hunk counts bound each hunk, so a changed line that looks like a
  header is still content. An empty or malformed diff, a rename or copy header,
  a file block cut inside its header or a quoted path exits 3 (classification incomplete), never a clean result.
  Profiles without content rules print the same `label` and `matches` as
  before; call sites still pass path lists until slice B3. (issue #934, PR #991, 2026-11-04) Box skill copy: none (config tool and reference docs only; no rendered template change).
- Release sources slice B2: `crew bootstrap --version` and `crew upgrade
  --version` fetch from the profile's `[install]` source. `url` (an HTTP GET)
  and `mirror` (a file copy) read `eng-crew-<v>.tar.gz` and `SHA256SUMS` from
  `<location>/v<v>/`, make no `gh` call, and verify with the shared verifier
  (optional `SHA256SUMS` pin, exactly one matching entry, member checks,
  `VERSION`) before anything is extracted or run; a refused release leaves the
  previous bundle, link and record untouched. `install.json` records a
  `transport` (kind, location, `SHA256SUMS` digest, pinned) for those sources,
  and `crew doctor` shows it in an `install source` row and skips the
  latest-release query. Plain `crew upgrade` refuses when the profile's source
  no longer matches the running bundle's record. `git` is refused until slice
  B3. Without `[install]`, output and records are unchanged. (issue #944, PR #990, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- New `crew land status|request --pr <n> --head <head-sha>` for an
  asynchronous land (#873 slice B2). It refuses a `sync` change backend and
  runs the backend map's `change.land-status`, `change.read-head` and
  `change.land`. `request` requests only on a `none` status at an unmoved
  head, resolves a lost acknowledgement by reading the status back instead of
  resending, then polls every `land_poll_interval` seconds until `landed`
  (exit 0, landed revision printed) or `failed`, an unknown status or
  `land_timeout` (`blocked:`, exit 1). It takes no land lock and builds no
  train. The renderer now accepts the conditional `change.publish` and
  `change.land-status` operations in `<op:>` tokens. Nothing calls the command
  yet, and every sync backend, GitHub included, is unchanged. (issue #930, PR #984, 2026-11-04) Box skill copy: none (a new crew command and reference docs; no rendered template change).
- Pack manifests accept an optional `pack.harness` naming a harness pointer
  registry file (slice B1 of #883). `crew-config.py validate` and `resolve`
  check it statically: the registry and every `source` and `launch_note`
  resolve, symlinks followed, to a regular UTF-8 file inside the pack;
  `[[pointer]]` entries take the file or Codex launch-note keys only, name an
  adapter bootstrap installs for (`claude-code` or `codex`), use mode `copy`
  or `pointer`, and give a unique, normalized project-relative target that is
  not a built-in bootstrap target. Bootstrap does not install the entries yet
  (#965, #966). Manifests without `pack.harness` validate as before. (issue #964, PR #983, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- Pack manifests accept an optional `[strategy]` table for the update from base
  (#874 slice B1): `update_from_base` (`merge` or `rebase`, default `merge`) and
  the boolean `retains_prior_heads`. `crew-config.py validate` rejects `rebase`
  unless `retains_prior_heads = true`, and `retains_prior_heads = true` under
  `merge`; `resolve` repeats both checks on the manifest of the backend bound to
  `change` and prints the declared `strategy.*` keys as pack metadata. Nothing
  reads the schema yet, and GitHub and every unchanged manifest stay `merge`
  with unchanged `resolve` output. (issue #951, PR #982, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- Profiles and pack manifests accept an optional `classify` concern with one
  operation, `sensitive` (#880 slice B1): a pack binds its sensitivity
  extension with `[backends.classify]`, `[capabilities.classify] sensitive =
  "supported"` and a `[classify] sensitive` command in its backend map.
  `emulated` is refused. `crew-config.py resolve` refuses a binding whose
  effective capability is not `supported`, whose backend map has no command
  or whose command holds an unfilled placeholder, and prints the bound
  command as `classify.sensitive` pack metadata. Undeclared means the
  built-in classifier alone, so every existing profile and manifest, the
  bundled `github` pack, bootstrap and the default render are unchanged.
  Nothing runs the extension until slice B2. (issue #961, PR #981, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- `crew train check` and `crew train land` read the tmux
  `runtime.options.mirror` setting, slice B2 of #877. With `mirror = "none"`,
  the mirror gate reports `status=pass reason="n/a: profile mirror = none"`
  for every PR, before #911's repo and path applicability and whether or not
  `crew:needs-mirror` is present; every other hold still blocks. The train
  merge record then says `- Mirror: n/a (profile).` instead of
  `- Mirror deferral used: <value>.`, and `--mirror-deferred` still refuses
  because no deferral can be set alongside `none`. The pass is diagnostic, not
  an approval or grant. An unset or `live-copy` profile keeps today's check
  output and merge record byte-identical. (issue #941, PR #980, 2026-11-04) Box skill copy: none (script only; no docs/protocol.md or rendered template change).
- `crew-precheck.py` checks precheck `issue=` and selfgate `pr=` against the
  resolved `ids.item` and `ids.change` patterns, all digits when none is
  declared. `ids.marker_key = item` keys the selfgate record on `issue=`.
  New optional `--item` and `--change` arguments carry the independently
  known keys. A marker naming another item or change now blocks with
  `marker for <value>, expected <id>`, and a selfgate read with neither
  `--change` nor a record `number` blocks with `missing change key`.
  `crew train`'s express gate passes the PR number and its one linked issue.
  Slice B1 of #876; marker examples and operative wording follow in #958. (issue #957, PR #979, 2026-11-04) Box skill copy: none (scripts only; no rendered template change).
- `crew-config.py validate` accepts two optional keys from the #398 spec grant
  design: a `[spec]` table whose `paths` globs replace the default
  `["docs/specs/**"]`, and `runtime.options.merge_grant_scope` (`approved`,
  `spec`), which refuses unknown values, `[]` and `spec` with
  `merge_grant = "none"`. Team files allow `spec` under `[team]` and both keys
  in a `[repos.<name>]` section. No gate reads either key until slice B2;
  without them, resolution and behaviour are unchanged. (issue #927, PR #977, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- `crew-config.py validate` and `resolve` accept optional
  `[[sensitive.content]]` rules (#879 slice B1): unique nonempty `name`, a
  `pattern` that compiles as a Python regex, a nonempty `reason` and optional
  repo-relative `paths` scope globs. A layer replaces the whole array. Diff
  matching is not in yet, so `sensitive` exits 3 (classification incomplete)
  on a profile that declares content rules; profiles without them classify
  exactly as before. (issue #933, PR #976, 2026-11-04) Box skill copy: none (config tool and reference docs only; no rendered template change).
- Release sources slice B1: `crew-config.py validate` and `resolve` accept an
  optional `[install]` table (`source` = `github`, `url`, `mirror` or `git`;
  default `github`). They require `location` for `url`, `mirror` and `git`
  (`https`, or `http` only to a loopback host, for `url`) and a full
  `git_commit` for `git`, check the `sha256sums_digest` and `git_commit`
  formats, and refuse a key the chosen source does not use. A new
  `scripts/crew-install.py` holds the shared verifier (an optional pin on the
  `SHA256SUMS` digest, exactly one matching entry, archive member checks,
  `VERSION` and entry point, all before the bundle moves into place, with
  nothing extracted before the checksum checks) and the `install.json`
  `transport` record, where a record without one reads as `github`. No command
  reads the table or calls the verifier yet; bootstrap, upgrade and host
  prepare adopt them in slices B2 to B5. Without `[install]`, output and
  records are unchanged. (issue #943, PR #975, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- Design note for pack-declared harness pointers in `docs/bootstrap.md`, not
  yet active: an optional `pack.harness` registry whose `[[pointer]]` entries
  name a harness with an install pointer adapter (`claude-code` or `codex`), a
  project-relative target and a pack source written by `copy` or `pointer`, or
  a Codex launch note added to the printed launch line. `validate` checks
  targets, collisions with the built-in targets and source containment;
  bootstrap installs the entries under the existing refusals, exclude lines,
  hashes and uninstall, and records an optional `harness_pointers` field;
  upgrade re-plans on pack changes, reports drift on edited targets and removes
  dropped entries. Without a registry, behaviour and `install.json` stay
  byte-identical. `docs/packs.md`, `docs/profile.md` and the harness adapter
  install pointer link to it. Implementation slices B1 to B3 (#964 to #966)
  follow. (issue #883, PR #973, 2026-11-04) Box skill copy: none (reference docs only; no rendered doc or template changed).
- `repo.control_item` may be a string id that fully matches the item pattern
  the tracker backend's map declares in an optional `[ids]` table (F1 of the
  tracker-native control item design). `crew-config.py resolve` loads `[ids]`
  from the tracker and change backend maps, pack overlay first, and prints
  `ids.item` and `ids.change` with `backend-map:<name>` provenance, defaulting
  to today's GitHub number pattern. `validate` and `resolve` refuse a string
  without a declared pattern, a non-matching or marker-unsafe string, a
  boolean or a float, and a pattern that does not compile or matches an empty
  or marker-unsafe id; a profile layer cannot set `[ids]`. An integer
  `control_item` and GitHub rendering are unchanged; ownership and
  `crew handoff` keep integer items until F2–F4. (issue #936, PR #972, 2026-11-05) Box skill copy: none (scripts and reference docs; no rendered template change).
- `crew-config.py` accepts an optional tmux `runtime.options.mirror`
  (`live-copy` or `none`, default `live-copy`), slice B1 of #877. `validate`
  and `resolve` refuse any other value, refuse the key under Grok Bot
  (unknown key), and refuse `mirror = "none"` together with a
  `mirror_deferral` other than `"none"`, since an install with no live copy
  has nothing to defer. A team file's `[repos.<name>]` section may set it.
  `resolve` now prints `runtime.options.mirror = "live-copy"` for an unchanged
  tmux profile; nothing reads the value until B2 (#941) and B3 (#942) land. (issue #940, PR #971, 2026-11-04) Box skill copy: none (script only; no docs/protocol.md or rendered template change).
- Pack manifests accept an optional `[land]` table for an asynchronous land
  (#873 slice B1): `mode` (`sync` or `async`, default `sync`) and the booleans
  `opens_draft`, `serializes` and `tests_against_tip`. The `change` concern
  accepts the conditional operations `publish` and `land-status`, which a
  `sync` manifest leaves out. `crew-config.py validate` rejects `async`
  without `change.land-status`, `opens_draft` without `change.publish`, and the
  booleans under `sync`; `resolve` repeats those checks on the effective
  capabilities, refuses `async` on a runtime without an async binding (every
  runtime but tmux) and prints the declared `land.*` keys as pack metadata.
  New tmux options `land_poll_interval` (default 60) and `land_timeout`
  (default 3600, at least the interval) are validated. Nothing reads the
  schema yet, and GitHub and every unchanged manifest stay `sync` with
  unchanged output, apart from the two new option lines in `resolve`. (issue #929, PR #970, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).
- Design note (proposed, not in effect) for precheck and selfgate markers
  keyed on a backend's declared item or change id. Protocol §2 gains a
  proposal section: `crew-precheck.py` checks `issue=` against the tracker
  map's `ids.item` and `pr=` against the change map's `ids.change` from the
  ID declaration of #875, digits when undeclared; an optional
  `marker_key = "item"` in the change map keys the selfgate record on
  `issue=` instead of `pr=`; each mode has an exact field set; and the key is
  compared with an independently supplied `--item` or `--change` id, never
  the marker's own value. §4, `profile.md` and `packs.md` point to it. No
  gate, key or behaviour changes until build slices #957 and #958 land. (issue #876, PR #969, 2026-11-04) Box skill copy: deferred to #140.
- Design note for a bindable sensitivity classifier, marked proposed and not
  yet in force. `docs/interfaces.md` sets out an optional `classify` concern
  with one operation, `sensitive`: a pack binds its own policy check as an
  extension, and without the binding every manifest and profile stays valid
  and classification is unchanged. `<op:classify.sensitive>` always renders
  the core `scripts/crew-config.py sensitive`, which runs the built-in rules,
  then the extension on the same input, and unions the results: an extension
  can add matches (prefixed `<pack>:`) but never remove one, and a failed,
  timed-out or unreadable extension adds an `errors` line and makes the
  change sensitive. `docs/profile.md` adds `errors` to the shared JSON
  contract, `docs/packs.md` notes the one token a pack map cannot replace,
  and `docs/protocol.md` records the override scope. Slices B1 to B3 (#961
  to #963) implement it. (issue #880, PR #968, 2026-11-05) Box skill copy: none (reference docs only; no rendered template change).
- Design note for a rebase update from base in `docs/interfaces.md`, not yet
  active: an optional pack-manifest `[strategy]` table
  (`update_from_base = "merge" | "rebase"`, default `merge`, so unchanged
  manifests stay valid) and `retains_prior_heads`, which `rebase` requires. It
  states the replacement guarantee (every earlier head stays readable on the
  review backend, stacked children restack with their parent), keeps verdict
  portability and the `pass=merge-up` marker unchanged, renders the update
  wording from the declared strategy with GitHub renders byte-identical, and
  refuses `crew train build` and `crew train bisect` on a rebase backend. It
  follows owner decision 3 on #649. The protocol, `docs/packs.md` and the tmux
  train section point to it. Build slices B1 to B3 (#951 to #953) follow. (issue #874, PR #960, 2026-11-04) Box skill copy: deferred to #140.
- Design note for release sources in `docs/bootstrap.md`, not yet active: an
  optional `[install]` table (`source` = `github`, `url`, `mirror` or `git`;
  default `github`, so unchanged profiles and install records stay as they
  are), one verifier shared by bootstrap, upgrade and host prepare that checks
  `SHA256SUMS` (with an optional pin on its digest) before anything is
  extracted or run, a Git source verified by a pinned full commit rather than
  as a checksummed bundle, a `transport` field in `install.json` shown by
  `crew doctor`, and a host toolkit installed at the primary's pin, checked
  file by file by `crew host check` and pruned by `crew host prepare --prune`.
  `docs/profile.md`, the release update path and host readiness link to it.
  Implementation slices B1 to B5 (#943 to #947) follow. (issue #882, PR #956, 2026-11-04) Box skill copy: none (reference docs only; no rendered doc or template changed).
- Design for `runtime.options.mirror = "live-copy" | "none"` in
  `docs/runtimes/tmux.md`: a tmux install with no live copy outside its
  render opts in to `none`, and the no-mirror-hold gate resolves to a
  recorded `n/a` (`train check` reason `n/a: profile mirror = none`, merge
  record `Mirror: n/a (profile)`). It specifies validation (refused for Grok
  Bot or with a mirror deferral), the gate order, an inert existing
  `crew:needs-mirror` label, brief changes and build issues B1–B3
  (#940–#942). Design only: nothing changes until those land, and the
  default keeps today's behaviour byte-identical. `runtime-options.md`
  points to it as proposed. (issue #877, PR #954, 2026-11-04) Box skill copy: none (design doc only; no docs/protocol.md or rendered template change).
- Design note for deterministic content rules in the sensitive class, marked
  proposed and not yet in force. `docs/profile.md` sets out optional
  `[[sensitive.content]]` entries (name, regex pattern, optional path scope,
  reason), the `sensitive --diff` input made without rename folding, exit 3
  for missing or incomplete diff input, and the JSON output that #880's
  bindable classifier shares: `label` and `matches` are unchanged and
  `content` lists rule, path, side and line. `docs/interfaces.md` proposes an
  optional `change.read-diff` operation, needed only when content rules exist.
  `docs/protocol.md` records the override scope: an owner override covers
  recorded rule and path matches, and a new pair needs reconsideration.
  Classification is unchanged until the implementation slices land. (issue #879, PR #950, 2026-11-04) Box skill copy: none (reference docs only; no rendered template change).
- Tracker-native control item design in `docs/handoff.md`: a backend map's
  optional `[ids]` table declares item and change id patterns once; a
  `repo.control_item` may be an integer or a string matching the tracker
  backend's item pattern; control-item commands use `<control-item>`, and a
  legacy `<n>` map still works for integer ids. It specifies the
  backend-neutral `read-item` output (author, body, created, optional id),
  the `write-item` re-read-before-retry rule, the `crew handoff` live reads
  through declared operations, and build issues F1–F4 (#936–#939). Design
  only: nothing changes until those land, and every addition is optional
  with today's GitHub behaviour as the default. `interfaces.md`, `profile.md`
  and `packs.md` point to it as proposed. (issue #875, PR #949, 2026-11-04) Box skill copy: none (design doc only; no rendered template change).
- Design note (proposed, not in effect) for a deterministic spec change
  definition and an opt-in spec scope for the standing merge grant. Protocol
  §7 gains a proposal section: a change is a spec change when it carries
  `crew:spec` or any path, rename sides included, matches a spec glob
  (default `docs/specs/**`), and an optional `merge_grant_scope` (default
  `["approved"]`) may add `spec` only when the recorded owner grant authorizes
  it. Sensitive, gate-contract and release-approval changes, `unverified`
  evidence and open rereviews stay excluded. The runtime options reference
  lists the proposed key. No gate, key or behaviour changes until the B1 and
  B2 slices land. (issue #398, PR #948, 2026-11-04) Box skill copy: deferred to #140.
- Design note for an asynchronous land in `docs/interfaces.md`, not yet
  active: an optional pack-manifest `[land]` table (`mode`, `opens_draft`,
  `serializes`, `tests_against_tip`; default `sync`, so unchanged manifests
  stay valid), conditional `change.publish` and `change.land-status`
  operations, the synthesizer's intent, poll, record and restart loop, and the
  gate alternatives for C7 and tested with the default branch. It follows the
  owner's #649 decisions: the final gate check before queue admission,
  re-verification on a head change, and a never-requested land told apart from
  a failed one. GitHub stays `sync`. `docs/concepts.md`, the runtime contract
  C7 and the tmux land lock link to it. Implementation slices B1 to B4 follow. (issue #873, PR #925, 2026-11-04) Box skill copy: none (reference docs only; no rendered doc or template changed).
- Pack manifests accept an optional SemVer `pack.version` for the pack's own
  release, distinct from the `eng_crew_version` pin. `crew-config.py validate`
  checks its shape, `resolve` prints it as pack metadata with `pack:<name>`
  provenance, bootstrap and upgrade record it in `install.json` (an upgrade
  that changes only the pack version no longer reports `no changes`), and
  `crew doctor` shows it. Without it, output and records are unchanged. A
  `paths.pack` directory without `profile.toml` now also supplies its
  `manifest.toml` to `resolve`. (issue #878, PR #919, 2026-11-04) Box skill copy: none (scripts and reference docs; no rendered template change).

### Changed

- The precheck and selfgate id keys from #876 are now operative protocol
  wording: the precheck marker's `issue=` is the tracker item id and the
  selfgate record keys on `pr=`, or on `issue=` when the change backend declares
  `marker_key = item`, all digits until a backend map declares `[ids]`. The
  express lane, the tmux builder, reviewer and synthesizer briefs and the Grok
  Bot reviewer and synthesizer briefs pass `crew-precheck.py --item` with the
  issue the PR closes, and treat a marker for another item as blocking. Slice B2
  of #876. (issue #958, PR #999, 2026-11-04) Box skill copy: deferred to #140.
- Triage calibration (`docs/triage.md`, researcher triage-sweep brief): the
  learning lookup gains a "still applies?" step before classification
  (implemented or changed since filing, cited as a PR, a commit on a named path
  or a CHANGELOG line, with `Not checked:`), where a fully overtaken item gets a
  proposed close (`overtaken: implemented` or `overtaken: changed`) and a partly
  overtaken one is banded for its remaining gap only. Priority bands follow the
  owner's criteria: P0 is mainly the owner's explicit call, otherwise only a
  failure happening now on this crew or backend; P1 needs recurrence, a
  measured throughput or cost hit or an owner report; P2 covers new features and
  single unreproduced reports; each record names its criterion and the sweep
  checks for under-rating. Similar open issues get a consolidation proposal
  naming the survivor, with occurrences counted across them. The coordinator can
  ask for an on-demand recalibration sweep with a signed `recalibrate` comment on
  the day's triage log; it re-checks the unanswered proposals and draws a fresh
  spot-check sample. Closes stay proposals in every mode. (issue #987, PR #993, 2026-11-04) Box skill copy: deferred to #140.

### Fixed

- `crew schedule decide` skips builder demand that a busy builder is already
  running, matched on the worker's `pr` or any `#n` in its item. Such
  an item is no longer admitted, held or counted against the pool cap, the
  target or the ramp limit, so one in-progress item (for example a merge-up
  whose run record has `pr: null`) no longer uses up `schedule_ramp` and
  defers the rest of its pool with reason `ramp`. The item stays in demand
  until its lead marks it done. Reviewer demand is not skipped: a busy
  reviewer on the same PR runs another pass or round. (issue #988, PR #992, 2026-11-04) Box skill copy: none (script and docs/scheduling.md only; no docs/protocol.md or rendered template change).
- `crew-config.py resolve` now refuses a half-declared release concern when an
  external pack is loaded. A `[release]` table whose `[backends.release]` still
  comes from the bundled default, while the pack's manifest declares release
  capabilities, fails naming `[backends.release]` and the file to add it to,
  so a release no longer silently runs the GitHub backend on a host without
  GitHub. A `[backends.release]` naming the pack with no `[release]` table
  fails naming `[release]`. Both halves present, neither present, an unrelated
  pack and explicit GitHub bindings resolve as before. There is no opt-out. (issue #910, PR #921, 2026-11-04) Box skill copy: none (script and reference docs; no rendered doc changed).

## [5.0.0] - 2026-11-04

### Added

- `[builder.precheck]` takes optional `owners` (a shell command that maps one
  changed path to its owning test targets) and `no_owner_ok` (globs for paths
  such as build files and docs that may have no owner). The new
  `crew-config.py precheck-scope` reads changed paths on stdin, one per line so
  spaces survive, and prints each path's class (`owned`, `no-owner-ok`,
  `unowned`) and the owning targets as JSON. It exits 3 on unowned code and 4
  when the owners query fails; both stop the check. `tests=n/a` now holds only
  when every path is no-owner-ok. With `owners` set, the rendered pre-review
  step tells the builder to run the helper. Without `owners`, behaviour and
  render are unchanged. (issue #881, PR #916, 2026-11-04) Box skill copy: pending coordinator mirror (docs/protocol.md changed).
- `docs/README.md` gets a Documentation principles section: the 11
  owner-approved M26 principles (one rule-sized bullet and reason each, linking
  the #676 design and decision record) and the principle-2 ownership map; no
  rule, gate, marker or default changes. (issue #837, PR #838, 2026-11-04) Box skill copy: none (docs-only).
- Add a tmux Quickstart and a "Bringing up the team" table to the root `README.md` (M26 26.A): install, `crew.toml`, bootstrap, `crew up`, per-harness first-run trust, a first issue, `crew status` / `crew down`, and which role window each command or trigger starts. Fix stale facts: the repo is public (README Install), and default `crew up` starts the enabled leads as well as `ash` (runbook Run the crew). Linked first from `docs/README.md`; navigation only, no rule changes. (issue #758, PR #830, 2026-11-04) Box skill copy: deferred to #140.
- Add `docs/reading-paths.md` (M26 26.2): per role, what to read at start, re-read every wake and load when a trigger fires, with exact links to the canonical sections; navigation only, no rule, gate or marker changes; indexed in `docs/README.md`. (issue #760, PR #825, 2026-11-04) Box skill copy: deferred to #140.
- `scripts/campaign-sandbox.py` sets up the M25 level-a disposable sandbox (25.03): a bare origin and seeded clone with a local CI fixture, an isolated sandbox profile (own repo slug, tmux session and roots), a control item with labels and fixture identities, and the guarded run manifest, refusing a non-empty or production-overlapping root before any write. `teardown` kills only the sandbox session, records retained work and the sentinel check, and removes the sandbox only when nothing is retained. `plan-forge` prints the level-b forge setup without running it; level b is blocked on owner account access. `docs/campaign-harness.md` gains the level a/b/c runbook. (issue #785, PR #816, 2026-11-04) Box skill copy: none (internal campaign script and doc; no template or box-skill changes).
- `scripts/campaign-run.py` is the M25 reusable scenario runner (25.02). It runs the campaign guard check first and again before every run step (a refusal stops the run, exit 2), selects scenarios by `--scenario Axx`, runs public-CLI steps and explicit deadline-bound completion waits, and writes durable results that keep PASS, FAIL, BLOCKED, LIMITATION and NOT RUN distinct, with each command's own exit, stdout and stderr recorded apart from the capture. A seed fixes the scenario order and the children's `CAMPAIGN_SEED`; `--rerun RESULTS` replays the same selection and seed. `docs/campaign-harness.md` documents the runner. (issue #784, PR #815, 2026-11-04) Box skill copy: none (internal campaign script and doc; no template or box-skill changes).
- Grok Bot gets the researcher (Riley) parent handoff. The new `templates/runtimes/grok-bot/researcher.md` worker brief and the wiring doc's section 2e have the coordinator's parent turn post one signed request on the source issue, then start one fresh read-only worker from the brief plus a `crew brief` run block naming the engine it actually runs. The worker signs with that engine, posts one signed `[Riley/research]` finding with its `pass=research` marker and returns the URL; the parent verifies the URL before relaying the TL;DR. No listener, routine, research gate or tmux command is involved. `docs/roles.md` and `templates/README.md` name the Grok handoff, and `test-render-parity.py` pins the rules. The box-skill mirror of this Grok template change is deferred to #140. (issue #780, PR #813, 2026-11-03) Box skill copy: deferred to #140.
- `scripts/campaign-guard.py` is the M25 campaign harness contract (25.01). `manifest` writes a run manifest that pins the sandbox repo, profile (path and sha256), source checkout SHA, installed release id, tmux session, state/worktree/live roots and an outside-sandbox sentinel. `check` refuses with exit 2, before any mutation, when the sandbox names the production repo or session, a sandbox root equals or nests with a production root, a root is still a placeholder, or a pin drifted; `manifest` also refuses an `--out` that does not resolve inside a sandbox root. `sentinel` re-hashes the sentinel after teardown. `docs/campaign-harness.md` documents the contract, including the retained-work cleanup check. (issue #783, PR #810, 2026-11-04) Box skill copy: none (internal campaign script and doc; no template or box-skill changes).
- The Grok Bot binding gains a cross-runtime limits section. It lists the supported defaults: `lighter_lane = "docs"`, CI-first review, and manual trains that batch two or more ready PRs at once, with members merging one at a time after a red train. It also lists the tmux-only features with the Grok Bot behaviour used instead: the direct lone-PR land waiver, the forge-less runner, the scheduler and role leads, window reaping and the triage timer. A provenance table for #140 AC3 records that #418 and #425 have no mirror deferral record (a gap the #140 render closes, with no owner approval added after the fact) and marks #402, #428, #433 and #436 N/A, since none changes a Grok template, the protocol or roles. Step 7 of the new-repo runbook points at the section. No template changed; deploying the box skills is deferred to #140. (issue #779, PR #809, 2026-11-03) Box skill copy: deferred to #140.
- Add run-blocker intake cards (M24 T7, `docs/triage.md`): `crew feedback --class SLUG --summary TEXT [--window NAME]` files a `runtime-blocker` card in `<owner>/eng-crew` (or `--repo`), prefilled from the window's run record (Source, role, engine, launch args) and redacted per spec R1 (credentials via the `step-summary.py` redactor, emails, `<state-dir>` / `<worktree>` / `<home>` paths and any other absolute path as `<path>`). When an open card already has that Failure class, it comments there instead, and it files nothing if it cannot list the cards. `docs/self-improve.md` adds the `runtime-blocker` trigger and recipe, the intake card lists the trigger, and the tmux coordinator brief tells the coordinator to report a crew defect in the same turn, unasked, without editing eng-crew. (issue #299, PR #776, 2026-11-04) Box skill copy: deferred to #140.
- Add the milestone-close triage sweep (M24 T6, `docs/triage.md`): with `[triage] enabled`, `crew poll` lists each project-repo milestone closed since its baseline under `milestones` in `triage/queue.json`; the watcher's sweep timer starts a sweep at once for a milestone no sweep took yet (unless a queued sweep will take it); `crew spawn researcher --sweep` names the untaken milestones in its Item and records them in `triage/milestones-taken.json` only once its window starts; the researcher brief drafts one intake card per failure class from the milestone's changes verdicts, steers, escalations and near-misses, deduped against existing intake issues, Trigger `milestone-close` (new in `templates/intake-candidate.md`). (issue #374, PR #775, 2026-11-04) Box skill copy: deferred to #140.
- Add triage shadow mode's precision bar (M24 T4, `docs/triage.md`): `scripts/triage-metrics.py` draws the calibration sweep's 10-record spot check (deterministic per sweep id), scores the 8-of-10 bar from `owner-accepted` / `owner-rejected` records, reports accuracy, owner override rate, reopen rate, time to triage, proposals per day and tokens per sweep, and freezes and re-scores the eval set of owner-confirmed records. The researcher's triage-sweep brief gains Calibration (the first sweep records the whole backlog without the noise cap and lists the spot check in the day's log) and Measures bullets, and never sets `triage.mode`: only the owner sets `apply`. The `pass=triage-log` line gains `tokens=`; the GitHub `list-items` mapping adds `stateReason,createdAt`. (issue #750, PR #774, 2026-11-04) Box skill copy: deferred to #140.
- Add an intake-card issue template (M24 T5, `docs/triage.md`): `.github/ISSUE_TEMPLATE/intake-card.md` carries the `templates/intake-candidate.md` fields, and `config.yml` keeps blank issues allowed, so the card format is recommended, never required. The researcher's triage-sweep Card step now says when to extract: an empty queue `card` (rules could not parse the fields) gets one model-extracted comment in the card block shape, `unknown` for missing fields, and the `triage:card-extracted` label; nothing is gated on format. `docs/self-improve.md` points at the template; tests check that the template's fields match the card and parse. (issue #751, PR #773, 2026-11-03) Box skill copy: deferred to #140.
- **Breaking:** Add the researcher's triage-sweep brief (M24 T3, `docs/triage.md`): a `## Triage sweep` section in the tmux researcher template with the skip rules, rules-first learning lookup with `used:` citations, P0–P3 bands and the in-band score, the auto-apply / propose / never split (shadow mode proposes everything), the noise cap of 10 proposals per day, reason-specific cooldowns, owner replies recorded as decisions, and one `Triage log YYYY-MM-DD` issue per day labelled `triage:log`, one comment per sweep, closing the previous log. Protocol §4 defines the `pass=triage` record and the `pass=triage-log` line (notes, never gate inputs) and the triage labels (`triage:proposed`, `triage:duplicate`, `triage:card-extracted`, `triage:log`, `P0`–`P3`); `docs/interfaces.md` declares the tracker operations `list-items`, `label`, `comment` and `close-item`, mapped to `gh` in the GitHub backend and pack manifest. The four tracker operations are required in every pack manifest, so a v4.0.0 manifest without them now fails `crew-config.py validate`. Migration: declare `list-items`, `label`, `comment` and `close-item` under `[capabilities.tracker]` in the pack manifest (`supported`, `unsupported` or `emulated (<how>)`) and map each in the pack's backend binding. (issue #749, PR #772, 2026-11-04) Box skill copy: deferred to #140.
- Add the always-on triage switch and sweep timer (M24 T2, `docs/triage.md`): an optional `[triage]` profile table (`enabled` default false, `interval_hours` default 6, `repos` default the project's repo, `rules`, `mode` `shadow` | `apply` default `shadow`) with validator rules; the tmux `researchers` cap now defaults to 2; `crew spawn researcher --sweep` starts a `riley-sweep` window with no item; and `crew watch` starts that sweep, with no model turn and no wake, once `interval_hours` passed since the last slot in `triage/sweep.json` or at once when overdue on wake, skipping the slot when `triage/queue.json` lists no items. (issue #748, PR #767, 2026-11-04) Box skill copy: none.
- `crew poll` runs the always-on triage scan when `triage.enabled` is set (T1 of the triage design): with no model call it writes `triage/queue.json` with the unplaced issues and owner replies to triage records in each `triage.repos` tracker, skipping `triage:log` issues, placed or flavor-recorded issues and pull requests; each entry carries exact-key duplicate hints across open and closed issues, intake-card fields parsed from the card template and P0 signals from the rules file or built-in defaults. Unreadable repos and items are recorded, and a newly seen P0 candidate queues one `triage-p0` wake for the coordinator. (issue #747, PR #757, 2026-11-03) Box skill copy: none.
- Add `docs/triage.md`, the always-on triage design (M24): a fresh researcher session sweeps new and changed issues and intake cards every `interval_hours` (default 6) on the watcher's timer, after a zero-model scan in `crew poll` that also starts an immediate sweep for a P0 candidate. Each decision looks up duplicates, lessons, findings and recorded owner decisions first and cites them; rules decide before the model, and ambiguity fails closed to a proposal. Low-risk, reversible changes may auto-apply, closes and active-milestone moves are only proposed, and gates, flavors, merge permission and owner config are never touched. A sweep acts only on unplaced issues and owner replies to its own proposals, skipping its `triage:log` issues, placed or already-recorded issues and pull requests. Proposals live on the items with a daily log issue and nothing is sent to the owner; sweeps start in shadow mode until 8 of 10 owner spot checks pass. It supersedes #427, folds in #374 and #299 and lists build issues #747–#751. A Known risks section records two deferred risks (untrusted issue text in a bypass-mode session, provider safety refusals; #753). Design only: it adds no rule until those land. (issue #659, PR #752, 2026-11-04) Box skill copy: none.
- `docs/runtimes/multi-device.md` gains a runbook for adding a forge-less runner host. It covers the overlay, a copied and checked release bundle, a crew key forced to the `crew-remote.py` entrypoint, the user-level runner service, a `version` smoke test, the `forge = false` profile table, seeding with `crew host prepare` and a first `crew runner run --host`, plus how to remove a host. Until the remote `check` verb is built (issue #743), `crew host check` keeps a remote host `not ready`, so the runbook names the host with `--host`. The tmux runtime contract adds one row per kind of host: the primary (unchanged), a forge-less runner host (unchanged, with a local fallback) and a role host (not built). (issue #349, PR #744, 2026-11-03) Box skill copy: none.
- `scripts/evidence-cli.py --runner <job_id>` renders a stored `crew runner` result as a capture: the header names `runner:<host>/<job_id>` and the head sha, and the text block lists each command's exit code and log tail with a `result: pass|red` line. It refuses a result whose head is not the checkout's HEAD. `--runner-fallback "<line>"` adds the runner's `ran locally` line to a local capture. `crew runner` now stores the command set it ran so the capture's `sh` block can name it. `docs/verification.md` adds a row: a runner capture at the PR head counts as a local run of the same commands, a capture at another head does not, and PR CI stays the full-suite gate. (issue #729, PR #742, 2026-11-03) Box skill copy: none (evidence helper and docs; no Grok Bot template change).
- `crew runner run --head <sha> [--host <h>] -- check-repo test-*.py...` runs the targeted local set on a forge-less host. It picks `--host`, else the ready forge-less host with the lowest load against `max_runs`, seeds a bundle of the head, starts a `job`, polls `result`, stores the result under `$CREW_STATE/runner/<job_id>/` and prints `runner:<host>/<job_id> head=<sha>` with each command's exit code. A transport failure on 3 calls in a row, or a `refused` or `failed` reply, runs the same commands locally and prints `runner: <host> <reason>; ran locally`; a late remote result is discarded. With no forge-less host it runs locally. A red remote command is a red run, not a fallback. `crew runner logs <job_id> [<command>]` prints a job's log tails. The tmux builder brief names `crew runner` as an option for the targeted local set. (issue #728, PR #739, 2026-11-03) Box skill copy: none (tmux CLI and the tmux builder brief; no Grok Bot template change).
- The host entrypoint (`scripts/crew-remote.py`) gains the forge-less runner's `job` and `result` verbs. `job` refuses a head that is not a commit in the host's project mirror and any command outside the closed set (`check-repo`, `tests` naming `scripts/test-*.py` files at that head, and one `evidence` capture). It then runs the commands in a detached worktree `jobs/<job_id>/wt/` in the background, with an env scrubbed of forge tokens, the SSH agent and profile values, and writes `jobs/<job_id>/result.json` with each command's exit code, duration and log path. `result` returns `running`, or the result with log tails capped. A retried `job_id` returns the first job, and jobs older than 7 days are removed. (issue #727, PR #736, 2026-11-03) Box skill copy: none (host entrypoint only; no template changes).
- `crew host prepare <host>` sets a project up on an inventory host and then runs `crew host check`. On a role host the hardened `prepare` call creates the project mirror under `mirrors/<owner>__<repo>.git` with the host's own `gh` login, or fetches it, and makes the `wt/` and `state/<owner>__<repo>/` directories. On a forge-less host the primary fetches its checkout and seeds the mirror with a full bundle of the default branch through the new `seed` verb, so the host never reaches the forge. On the primary it fetches the project checkout. A failed step prints `fail prepare <step>` and leaves the host not ready. (issue #206, PR #735, 2026-11-03) Box skill copy: none (tmux CLI and host entrypoint only; no template changes).
- `[hosts.<name>] forge = false` marks a forge-less host that takes runner jobs only. It needs no `engines`, and `validate` refuses it as the primary, with a non-empty `roles` or in `placement.hosts`, so placement never puts a role session there. `crew hosts` gains a `FORGE` column, and `crew host check` on a forge-less host shows the logins check as `n/a`, or `warn` when the runner finds a forge login there. (issue #726, PR #734, 2026-11-03) Box skill copy: none (tmux CLI and profile schema only; no template changes).
- `scripts/crew-remote.py` adds the hardened remote call for multi-device hosts. It has three parts. The entrypoint is the crew key's forced command: it takes one JSON request on stdin, never a shell string, and refuses unknown or not-built verbs, version skew, other SSH commands, paths outside its root and mutating verbs without a request id; a retried request id replays the first reply. The runner is a user-level service that keeps the host's crew tmux session alive, so runs outlive the SSH session, and writes a heartbeat. The primary's client `call()` takes only auth and host-key settings from the SSH config, then calls with `-F none`, batch mode, strict host keys, no forwarding or sent environment and bounded dead-peer timeouts, and returns `ok`, `refused`, `failed` or, on a transport failure only, `unreachable`. Only the `version` verb is built so far. The multi-device design gains a failure-semantics section. (issue #208, PR #733, 2026-11-03) Box skill copy: none (host script and multi-device doc only; no template changes).
- The coordinator gains a quota handoff suggestion duty (build issue D in `docs/handoff.md`): at each wake the owning coordinator checks its own runtime's orchestration meter against the quota routing skip thresholds (15% of the short window, 10% of the weekly or monthly limit) and, under one, suggests a handoff to the owner once per meter window with the meter, reset time, target runtime and the work that would move. The suggestion is not an owner ask (no deadline, no default; silence means no handoff) and only the owner's `/crew handoff to` starts one. Grok Bot exposes no meter, so there it runs only on an owner-given reading. The tmux and session coordinator briefs point at the duty. (issue #640, PR #722, 2026-11-03) Box skill copy: none (docs and the tmux and session coordinator briefs; no Grok Bot template change).
- Add the researcher, Riley, to the tmux runtime (part 2 of 3 for the researcher role). `roles/eng.toml` registers a `researcher` role with one `research` pass on an issue, windows 40–44 (`riley-<issue>`), a fresh session per request and the `researchers` cap, so `crew spawn researcher --issue N` starts it (at the deep tier by default) or queues it when the cap is full. The tmux example profile routes it on the research row (`[engines.roles] researcher`: Codex `gpt-6.1-sol`, then Claude Code `opus`, then OpenCode DeepSeek); without that override the deep tier order applies. The identity stays optional: `gh_user` resolves to the coordinator's author login, with the name Riley, title Researcher and emoji 🔬. The new `templates/runtimes/tmux/researcher.md` brief covers the read-only scope, citation rules, the direction rule and the signed `[Riley/research]` finding with its `pass=research` marker. A researcher's `done:` (or `failed:`) is terminal: `crew route` closes its window and leaves the wake for the coordinator to relay. The coordinator rule follows in part 3. (issue #584, PR #720, 2026-11-03) Box skill copy: none.
- Runtime handoff resume and prompt stop (roadmap 21.4). On tmux, `crew handoff reconcile` now prints the whole reconcile table: `adopt`, `hold` (a head or stage tag moved), `skip`, `gone`, `rerun` for kept runs and for pass markers posted in transit, `missed` items and `rule` differences. `crew handoff ack` posts `acked` with that plan once per handoff id, refusing while a rule difference has no owner answer; a takeover's ack carries the manifest. `crew handoff lift` removes `crew:hold` only from the manifest's `holds_added`, once `stopped` is posted, the owner confirms or the outgoing release reads the record. On the outgoing side, `crew poll` queues one `ownership: lost` wake after the ack, `crew watch` refuses to re-arm, and `crew handoff stopped` does the teardown from a process detached from the crew session: it disarms the watcher, runs `crew down` keeping every worktree, and posts `stopped` with the kept worktree names once the watcher and session are gone. The resume steps now apply a diverged set's hold after the ack and before dispatch, and the Grok Bot wiring template gains the stop and return checklist. (issue #212, PR #718, 2026-11-03) Box skill copy: pending coordinator mirror.
- Define the researcher role, Riley (part 1 of 3 for the researcher role). `docs/roles.md` and the concepts glossary describe a read-only role that takes deep dives off the coordinator: it never pushes to a PR branch, builds, reviews or lands, holds no gate, answers with a signed issue comment or a requested design-doc PR, runs on the research engine row, and gets one fresh session per request. The profile validator accepts an optional `[identities] researcher` table (with a required `gh_user`) and a tmux `researchers` cap (integer, at least 1, default 1); `profiles/tmux.toml` names the identity Riley. The brief, spawn path and coordinator rule follow in the next PRs. (issue #584, PR #717, 2026-11-03) Box skill copy: none.
- `crew doctor` adds the runtime handoff rows (build issue C in `docs/handoff.md`): `control item` (ok when `repo.control_item` is set and its ownership record reads; `warn` when unset, which keeps legacy operation; `fail` when unreadable, since every wake is then read-only), `runtime instance` (`warn` when `runtime.instance` is unset) and `owning runtime` (ok when this instance owns the repo; `warn` when another instance owns it, a handoff is draining or in transit, or no `claimed` marker exists yet). The bootstrap preflight table gains the matching row 22. (issue #639, PR #714, 2026-11-03) Box skill copy: none (tmux CLI only; no template changes).

### Changed

- The profile's `tmux` launch topology (`[runtime.options.launch]`) moves
  verbatim into a new `## Launch topology` section of
  `docs/configuration/runtime-options.md` (M26 modular organization, batch 2):
  the absent-table fallback, the four-row key table with every value, default
  and refusal constraint, the unchanged window-name and tag statement and the
  complete TOML example. Only relative-link prefixes and the `launch` row's
  pointer change; the profile keeps the `` ### `[runtime]` `` heading and anchor
  with direct links to runtime keys and shared options, `tmux` options and the
  launch topology; no rule, gate, marker or default changes. (issue #861, PR #890, 2026-11-04) Box skill copy: none (docs-only).
- The profile's `tmux` option block moves verbatim into a new `` ## `tmux` options ``
  section of `docs/configuration/runtime-options.md` (M26 modular organization,
  batch 2): the presence/away-cap introduction, the whole option table with
  every value, default, limit and exception, and the standing and render-time
  `notes` qualifications with the notes example and the pack render-overlay
  link. Only relative-link prefixes and the `launch` row's pointer change; the
  profile keeps the `` ### `[runtime]` `` heading and anchor with a direct link
  to the new section, and the launch topology stays in the profile; no rule,
  gate, marker or default changes. (issue #860, PR #889, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's `Step 1: create the crew:* labels` moves verbatim
  into the new module `docs/runbooks/github-tracking.md` (M26 modular
  organization, batch 2), with the `crew:*` namespace pre-check and collision
  refusal, the ten-label guarded `--force` creation loop, the API example and
  the exact ten-row verification; the runbook keeps the heading and anchor
  between Steps 0 and 2 as a direct module link, and the module links the
  still-unmoved Step 3 milestones and Project procedure; no rule, gate, marker
  or default changes. (issue #854, PR #888, 2026-11-04) Box skill copy: none (docs-only).
- The profile's `## Layers and precedence` section moves verbatim into
  `docs/configuration/resolution.md` (M26 modular organization, batch 2): the
  `resolve` command with its four-layer table, the merge rule and the
  `identities`, `backends` and `engines` exceptions, the unsupported-invariant,
  single-identity and integer cross-key checks with the pack-manifest fill, and
  the provenance output, problem format and example; the profile keeps the
  `## Layers and precedence` heading and anchor as a direct module link, and the
  module's Validate section now links its own layers section; no rule, gate,
  marker or default changes. (issue #858, PR #885, 2026-11-04) Box skill copy: none (docs-only).
- The profile's `[runtime]` key table and the `max_active_milestones`
  coordinator option both runtimes accept move verbatim into the new module
  `docs/configuration/runtime-options.md` (M26 modular organization, batch 2),
  with the `instance` condition, the timezone type and the option's priority,
  in-flight and default behavior; the profile keeps the `` ### `[runtime]` ``
  heading and anchor with a link to the module, and the `tmux` options, notes
  and launch topology stay in the profile; no rule, gate, marker or default
  changes. (issue #859, PR #884, 2026-11-04) Box skill copy: none (docs-only).
- `AGENTS.md` keeps its `## Map` heading but replaces the topic-by-topic list
  with three navigation destinations: `docs/reading-paths.md` for role reading,
  `docs/README.md` for the full doc catalog and `CONTRIBUTING.md` for
  contribution mechanics. In Build posture, "CHANGELOG entry" now links to
  `CONTRIBUTING.md#changelog` and the direction-rule link targets
  `docs/packs.md#direction-rule`. Every build and review instruction keeps its
  words; Review posture is unchanged; no rule, gate, marker or default changes. (issue #867, PR #872, 2026-11-04) Box skill copy: none (docs-only).
- `CONTRIBUTING.md` links its protocol freeze, spec change and mirror summaries
  to their owning sections in `docs/protocol.md`, `docs/specs/framework.md`,
  `scripts/README.md` and the runtime docs instead of restating them; no rule
  changes. (issue #866, PR #871, 2026-11-04) Box skill copy: none (docs-only).
- The root `README.md` `## Status` section no longer carries a dated
  milestone and release snapshot (M26 repo-root docs): it now links GitHub
  Releases, the open and closed milestone views, `CHANGELOG.md`, the
  per-slice status in `docs/specs/portable.md` §5 and
  `docs/merge-enforcement.md` for enforcement limits. The retired snapshot
  (M1–M14.3 and R1 completion lines, the #80 hold line and the Notion
  "Canonical heading" note) stays readable at base `dcd2722`, `README.md`
  lines 144–168. The front-door sentence and `## More` now point to
  `docs/reading-paths.md` for adoption and role navigation and to
  `CONTRIBUTING.md` for repository contribution. No heading, rule, gate,
  command or default changes. (issue #865, PR #870, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's `### Manual fallback` subsection of Step 0 moves
  verbatim into `docs/runbooks/profile-install.md` (M26 modular organization,
  batch 2), with its prerequisite and fallback-reason introduction, the four
  numbered write, validate, resolve and render units with their commands,
  expected outputs and refusal behavior, and the hand-fill fallback; the
  runbook keeps the `### Manual fallback` heading and anchor as a direct module
  link, and Step 0 now lists both module subsections in order; no rule, gate,
  marker or default changes. (issue #853, PR #869, 2026-11-04) Box skill copy: none (docs-only).
- The profile's `## Validate` section moves verbatim into the new module
  `docs/configuration/resolution.md` (M26 modular organization, batch 2): both
  `crew-config.py validate` command variants, the `file:key: reason` problem
  format and exit codes, the full rejection list and the install-time versus
  run-time placeholder distinction, including the `resolve --install` check on
  the effective profile; the profile keeps the `## Validate` heading and anchor
  with a link to the module, and layers and precedence stay in the profile; no
  rule, gate, marker or default changes. (issue #857, PR #868, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's `### Bootstrap (recommended)` subsection of Step 0
  moves verbatim into the new module `docs/runbooks/profile-install.md` (M26
  modular organization, seventh slice), with the verified-release and `--dev`
  distinction, the dry-run and apply commands, the refusal and human-review
  conditions, the expected outputs, the Grok Bot and tmux deployment
  distinction and the remaining Steps 1–8; the runbook keeps the Step 0 and
  Bootstrap headings and anchors as a link to it, and the module links the
  still-unmoved manual fallback and onboarding steps; no rule, gate, marker or
  default changes. (issue #852, PR #864, 2026-11-04) Box skill copy: none (docs-only).
- The rest of the profile's `## Team files` section moves verbatim into
  `docs/configuration/team-files.md` (M26 modular organization, batch 2):
  resolution through the layer pipeline, project references, clone location,
  the legacy `crew.toml` qualification, the shared state root and session,
  `crew up --team` and its limits, and the five-step migration from two
  `crew.toml` files; the profile keeps the `## Team files` and
  `### Migration: two crew.toml files to one team file` headings with direct
  module links; no rule, gate, marker or default changes. (issue #856, PR #863, 2026-11-04) Box skill copy: none (docs-only).
- The opening of the profile's `## Team files` section moves verbatim into the
  new module `docs/configuration/team-files.md` (M26 modular organization,
  batch 2): the team file's location and name contract, the `[team]` tables
  with the `pack`, `personas` and `accounts` shorthands and their precedence,
  the per-repo allowlist and refusals and the two-repo example; the profile
  keeps the `## Team files` heading and anchor with a link to the module, and
  resolution, the team instance and migration stay below it; no rule, gate,
  marker or default changes. (issue #855, PR #862, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's `Step 2: add the reviewer as a collaborator` moves
  verbatim into the new module `docs/runbooks/github-reviewer-access.md` (M26
  modular organization, sixth slice), with the invitation and acceptance
  commands, the existing-org-member path, the `write` permission and
  zero-pending-invitation check and the author push-access confirmation; the
  runbook keeps the heading and anchor between Steps 1 and 3 as a link to it,
  and the module links the prerequisite identity sections; no rule, gate,
  marker or default changes. (issue #844, PR #851, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's dated `End-to-end run (2026-10-30)` moves verbatim
  into the new history module `docs/runbooks/tmux-onboarding-history.md` (M26
  modular organization, fifth slice), with both tables, timestamps, evidence
  links and the pass bar, labelled as history for eng-crew `main` at
  `7eb454d`; the runbook keeps the heading and anchor as a link to it, its
  `tmux runtime` section becomes navigation, and the tmux onboarding module
  links the history; no rule, gate, marker or default changes. (issue #843, PR #850, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's `tmux troubleshooting` table moves verbatim into
  `docs/runbooks/tmux-onboarding.md` (M26 modular organization, fourth slice),
  with every symptom, cause and fix and the no-blind-input instructions; the
  runbook keeps the heading and anchor as a link to it; the module's links to
  troubleshooting now point at its own section; no rule, gate, marker or
  default changes. (issue #842, PR #849, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's tmux `Run the crew` step moves verbatim into
  `docs/runbooks/tmux-onboarding.md` (M26 modular organization, third slice),
  with its command table, first-start trust answer, one-shot watcher
  requirement, close-out conditions and owner duties; the runbook keeps the
  heading and anchor as a link to it; the module now runs prerequisites, setup,
  run, then links to the unmoved troubleshooting; no rule, gate, marker or
  default changes. (issue #841, PR #848, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's tmux `Set up the target repo` step moves verbatim
  into `docs/runbooks/tmux-onboarding.md` (M26 modular organization, second
  slice), with its profile placeholders and refusals, label and CI
  qualifications; the runbook keeps the heading and anchor as a link to it; the
  module now runs prerequisites, setup, then links to the unmoved run
  procedure; no rule, gate, marker or default changes. (issue #840, PR #847, 2026-11-04) Box skill copy: none (docs-only).
- The onboarding runbook's tmux prerequisites move verbatim into a new
  `docs/runbooks/tmux-onboarding.md` operator module (M26 modular organization,
  first slice); the runbook keeps the `tmux prerequisites` heading as a link to
  it, the parent tmux runtime introduction and the unmoved setup, run and
  troubleshooting steps; the module gets its manifest, inventory and docs index
  rows; no rule, gate, marker or default changes. (issue #839, PR #845, 2026-11-04) Box skill copy: none (docs-only).
- `docs/verification.md` and `docs/roles.md` no longer restate evidence
  placement. Protocol §3 owns placement (inline only, body written once, late
  evidence in a signed fix or ci-fix review, rereview); `docs/verification.md`
  owns shape, N/A, reproduction and each role's evidence duty. The verification
  intro, its builder placement and late-evidence bullets, and the roles.md
  evidence-duty and handoff copies now link to those owners. Every removed
  qualifier already lives there. The rendered `## PR conventions` copy and the
  `templates/evidence/*.md` adapters are unchanged. Structural only; no rule,
  gate or marker change. (issue #765, PR #834, 2026-11-04) Box skill copy: pending coordinator mirror (Grok Bot `eng-crew-roles` renders `docs/roles.md`).
- `docs/roles.md` no longer restates the metrics-gate, knowledge-routing,
  self-improve intake and land-rule duties in full. Each paragraph keeps the
  owning role and its authority, then links the canonical home:
  `docs/metrics/decisions.md` (trigger path and gate), `docs/self-improve.md`
  (knowledge routing, always-loaded files, roles) and protocol §7 land rules
  and merge trains. Every removed qualifier already lives there. Structural
  only; no rule, gate or marker change. (issue #764, PR #833, 2026-11-04) Box skill copy: pending coordinator mirror (Grok Bot `eng-crew-roles` renders `docs/roles.md`).
- `docs/triage.md` gets a lifecycle banner (built for tmux in M24, live in
  shadow mode, #753 mitigations unbuilt, no Grok Bot timer or sweep) in place of
  its stale design-only line, and its `docs/README.md` index row follows; no
  rule, gate, marker or default changes. (issue #831, PR #832, 2026-11-04) Box skill copy: none (docs-only).
- `docs/architecture.md` drops its second marker catalog: the where-bots-write, signed-header and hidden-line prose, the field table, the reading rules and the pass-values table give way to one compact fix-note example and links to protocol §3, §4, §5 and §6 and roles. The per-pass meanings move into the protocol §4 `pass` list, now a table, so each qualifier keeps one home; no rule, gate or marker changes (row 5 of the #676 structural plan). (issue #763, PR #826, 2026-11-04) Box skill copy: deferred to #140.
- `docs/runtimes/grok-bot.md` records the owner decision accepting Grok Bot
  runtime gaps C1, C2, C3 and C5 as declared; no behavior change. (issue #150, PR #821, 2026-11-04) Box skill copy: none (docs-only).
- The Grok Bot B1, B2 and V2 prompts now build every build, fix, review and validate worker turn's run block with `crew brief` (Item, Pass, Base at the live head, Round, Claim, Engine and Worktree) and append its `## This run` block verbatim to the worker prompt, refusing to dispatch when `crew brief` exits 2. V2 states that review and validation each run in a fresh, independent session that reuses neither the builder's conversation nor the other pass's session, and that validation never sees the review output. `scripts/test-render-parity.py` renders the real templates and parses each recipe through `crew brief` to prove the fields reach the worker. (issue #778, PR #808, 2026-11-03) Box skill copy: deferred to #140 (coordinator posts the per-PR mirror deferral record).
- Grok Bot routes express items through the crew lane. Express stays an option there but is not enabled, and no self-gate runs. B1, V1, V2 and S treat a `crew:express` label or express item record as the crew lane (normal resolution, independent review and validation, approval to land) and route the item back to the coordinator. The wiring doc's new section 2d has the coordinator post a signed `pass=flavor` record with the item's normal flavor and remove `crew:express` before dispatch. On grok-bot, `crew doctor` adds a `triage` row: `ok` when off, `warn` when `triage.enabled = true`, because Grok Bot installs no triage timer and triage stays coordinator dispositions. Bootstrap's plan says the same and never claims a timer install. The bootstrap preflight table gains row 23. (issue #777, PR #807, 2026-11-03) Box skill copy: deferred to #140.
- `docs/architecture.md` drops its duplicated actor and stage detail: the Roles table, the Identities prose, the numbered stage list and the escalation-exit paragraph now give a short summary and link the canonical definitions in protocol §1, §2, §5 and §7, roles.md and the GitHub backend identities. The flow diagram, the required headings and the Labels and Markers sections are unchanged; no rule, gate or marker changes (row 4 of the #676 structural plan). (issue #762, PR #771, 2026-11-03) Box skill copy: none.
- The nine design-titled docs (bootstrap, deliverables, express-lane, flavors, handoff, release, roles-registry, runtimes/multi-device and runtimes/session) gain a lifecycle status banner under the H1: status (`built` or `partly built`), what it applies to, the current rule homes, the built and design-only sections with issue evidence, and the base checked. Banners classify evidence only; no rule, gate, marker, heading or path changes (row 3 of the #676 structural plan; stale intro sentences stay for #756). (issue #761, PR #770, 2026-11-04) Box skill copy: none.
- The docs index (`docs/README.md`) gains a "Find your path" section with role and task navigation that links the docs owning each rule and adds none of its own, and its sorted catalog gains Purpose, Audience and Kind columns with a legend; every Contents cell, row order and destination is unchanged (row 1 of the #676 structural plan). (issue #759, PR #768, 2026-11-03) Box skill copy: none.
- The targeted local set for template or render fixture changes adds `scripts/test-crew-bootstrap.py`, which holds the brief size budget check, next to `test-crew-render.py`, `test-render-parity.py` and `test-tmux-briefs.py`. AGENTS.md's build posture, the reviewer-validator rule in `docs/verification.md`, and the tmux and Grok Bot builder briefs name it. (issue #725, PR #740, 2026-11-03) Box skill copy: pending coordinator mirror (grok-bot builder-b1 brief text changed).
- The tmux coordinator brief hands owner deep dives to the researcher, Riley (part 3 of 3 for the researcher role). When the owner asks for a deep dive (more than a few lookups), the coordinator files or links an issue and hands it to Riley per `docs/roles.md`, Researcher, instead of researching inline, answers the owner's other questions meanwhile and relays Riley's TL;DR. `docs/roles.md` states the same rule. To keep the brief inside its size budget, a few coordinator lines are reworded more tersely; no rule changes. (issue #584, PR #731, 2026-11-03) Box skill copy: none.
- M20 is re-scoped runner first: the multi-device design gains forge-less hosts (`forge = false`) that take remote test runner jobs only, with the primary as the forge gateway seeding the host mirror over the hardened call, a closed forge-free command set, results by reference, a local fallback that never blocks a gate, and the security model. The spec moves M20 after M21, files the runner build issues (20.13–20.16) and moves the remote role session issues to a follow-up milestone. (issue #715, PR #730, 2026-11-03) Box skill copy: none.
- Runtime contract tables gain their C9 ownership handoff rows (roadmap 21/E). The multi-device design's contract across hosts now says how the guard, prompt stop and kept worktrees work when runs sit on role hosts, with the unreachable-host gap. The session binding's C9 row now follows the #212 prompt stop and resume steps, and names the tmux-only `crew handoff` tooling as its residual risk. (issue #641, PR #723, 2026-11-03) Box skill copy: not needed (docs-only design tables).

### Fixed

- `crew train check` now treats `docs/protocol.md` and `templates/` as mirrored
  paths only when the train runs on the eng-crew repo itself (`repo.name =
  "eng-crew"`). A product repo with its own top-level `templates/` folder or a
  `docs/protocol.md` gets `mirror: pass (no mirrored paths)` instead of blocking
  on "no coordinator mirror/drift record". The `crew:needs-mirror` label still
  blocks on every repo, and eng-crew's own mirror gate is unchanged. (issue #911, PR #915, 2026-11-04) Box skill copy: none (script-only).
- `docs/roles.md` no longer describes every worker as fire-and-forget. Roles
  keeps the isolation constraint (one unique worktree per run, never delete
  another run's tree or unlanded work) and now defers retention and safe
  reclaim to the runtime binding, linking contract C6 and the tmux Q2,
  `crew dequeue` and `crew kill` sections. No gate change. (issue #756, PR #829, 2026-11-04) Box skill copy: none (docs-only).
- `docs/observe.md` no longer allows committing a run's `summary.md` to the PR
  branch when a verdict relies on it, which contradicted the evidence placement
  rule. Protocol §3 owns placement: evidence is inline in the PR body or signed
  reviews, and the run summary reaches the PR only as promoted text. No gate
  change. (issue #756, PR #828, 2026-11-04) Box skill copy: none (docs-only).
- Three stale doc statements found by the #676 inventory are corrected:
  `docs/express-lane.md` no longer says the lane is unbuilt (X1–X8 shipped in
  M18.2), the role-leads review prerequisite in `docs/runtimes/tmux.md` is
  marked historical now the builder and reviewer leads ship, and
  `docs/metrics/README.md` labels the committed `prs.md` and `prs.csv` as a
  2026-10-29 snapshot. No rule or gate change. (issue #756, PR #824, 2026-11-04) Box skill copy: none (docs-only).
- The M25 campaign harness can no longer reach a tmux server outside its sandbox. An inherited `$TMUX` beats `TMUX_TMPDIR`, so a bare sandbox `tmux kill-server` from a crew pane killed the owner's default server. `scripts/campaign-sandbox.py setup` now installs a `state/bin/tmux` shim that pins every call to the sandbox socket with `-S`, drops `TMUX` and `TMUX_PANE`, and refuses `-L` or a foreign `-S`. `teardown` kills the sandbox session on that socket. `scripts/campaign-run.py` puts the shim first on the scenario `PATH`, strips `TMUX` and `TMUX_PANE`, and runs a decoy session on a throwaway socket, exported as `TMUX`. A scenario that kills the decoy FAILs and stops the run. (issue #817, PR #820, 2026-11-04) Box skill copy: none (internal campaign scripts and doc; no template or box-skill changes).
- Fix a flaky `test-crew-handoff.py` prompt-stop test that failed on `main` with an empty `handoff-stop.log`. The detached `handoff stopped` actor posts `stopped` and only then prints its `posted stopped` line, and its stdout is the log file, buffered until it exits. The test stopped waiting when the post appeared and could read the log before the line was flushed. It now waits for the actor's final log line, its completion signal, before checking the log and the post. `handoff stopped` itself is unchanged. (issue #755, PR #769, 2026-11-03) Box skill copy: none (test only).
- `crew schedule decide` no longer grants a pending handoff whose issue or PR is under a blocking `crew:hold`, or a PR that closes a held issue. The snapshot gains a `holds` input; held demand is left out of the ranking and the target's demand test, returned under `held` and shown as `held <n> <refs>` in `crew schedule summary`. An unreadable hold read defers the caller's pool as `holds-unreadable` (`held unknown` in the summary), so a held item is never granted on a failed read. The handoff stays pending, so the item is ranked again once the hold lifts. `crew lead handoff` no longer reuses a prior message the lead already marked `done:`; re-sending the same kind and refs after a withdrawal starts a new handoff instead of reporting `acked`. (issue #712, PR #746, 2026-11-03) Box skill copy: none (scheduler and lead scripts and docs; no Grok Bot template change).
- `crew train check` counts only artifact-shaped `evidence/` references as required artifacts: a path with a file extension, a markdown link or image target, or a backticked path. Prose such as "scope, evidence/citation, direction rule" no longer blocks a land with a missing-artifact result, and a missing artifact-shaped path still blocks. (issue #721, PR #741, 2026-11-03) Box skill copy: none.
- A finished reviewer pass (review with no successor, validate, recheck) is reaped once, keeping its review, validate and verdict section files, even when its PR has merged, closed, moved to a new head or been held. Since S7 (#625) the reviewer lead saves a `crew kill` reclaim as the worker's `done:` completion, and `crew route` returned early on such a PR without reaping, so finished validate workers kept their run records and filled the reviewer cap. `crew schedule summary` now ends with `terminal N <windows>`, naming reviewers that wrote their final `done:` but still hold a slot. (issue #719, PR #724, 2026-11-03) Box skill copy: none (tmux CLI only; no template changes).

## [4.0.0] - 2026-11-03

### Added

- Route express changes (X5, the switch in `docs/express-lane.md`). `crew poll` resolves the express lane the way `crew train` does (`crew:express`, the item record and class rules; an unreadable resolution runs the crew lane). For an express change it emits no `new-head` or `fix-at-head`, emits `ci-passed` only with a builder selfgate pass at head (or one carried by a `merge-up` that poll now recognises from the selfgate pass at the previous head), and emits the new `selfgate-passed` event to the synthesizer when a selfgate pass lands with CI green. When the change falls back to the crew lane, poll emits `new-head` at its head so normal review starts. `crew route` never starts a reviewer pass for an express change, so the reviewer lead skips any queued review, and the tmux coordinator brief routes express `ci-passed` and `selfgate-passed` to land, sends `ci-red` without holding, and hands review back on fallback. A synthesizer gate-status block that only waits on `selfgate` (with `ci`, `review`, `validation` or `train`) is now recorded without a coordinator wake, since `selfgate-passed` wakes it. (issue #672, PR #711, 2026-11-03) Box skill copy: deferred (tmux mirror deferral; Grok Bot runs express items in the crew lane).
- `crew schedule summary` prints one line from the latest scheduler decision: busy workers against each pool's cap, the target, the machine signals, queued demand by kind, deferrals by reason and orphans (live tool sessions of closed-item runs or of unrecorded crew windows) with their process ids. `crew watch` prints that line after every exit line, and finishing work (classes 1–6) deferred for `stuck_after` seconds (new profile option, default 1800) sends one `schedule-stuck` wake with the item, its reasons and the latest snapshot. Deferrals themselves never wake the coordinator. (issue #628, PR #706, 2026-11-03) Box skill copy: none (tmux only).
- Add the express gate to the tmux synthesizer and `crew train`. `crew train` resolves a `crew:express` change by program: the newest signed coordinator item record on its one linked issue must resolve `express` (`item-flavor.py`, with the issue and PR labels), and no changed path, both rename paths, may match a tightening class (`class-flavor --express`). Only a change resolved express takes the latest builder `pass=selfgate verdict=pass` at head (checked with `crew-precheck.py --pass selfgate`) in place of the formal approval; any other change, labelled or not, needs the crew-lane verdict. `build` carries an express member by its selfgate record's `base` and `sha` and drops an unreadable one (`express-unreadable`); `check` reports the selfgate result and an `express` gate (crew lane, unreadable resolution, or `crew:spec` without merge-ok block); `land` re-resolves at head and stops on a missing or stale record; the merge record names `pass=selfgate`. The synthesizer brief's step 2 names the express approval, with doc pointers shortened to keep the brief inside its size budget headroom. (issue #673, PR #705, 2026-11-03) Box skill copy: deferred (tmux mirror deferral; Grok Bot runs express items in the crew lane).
- Add the express self-gate loop to the tmux builder brief. On an express change (the `express` item record plus `crew:express`, resolved by `class-flavor --express`), the builder writes a self-gate brief in `.crew/`, runs a fresh read-only review sub-session on the `selfgate_engine` mode's engine with the protocol §3 review rubric and the adapter's code-review skill, fixes findings until a pass or `caps[0]`, posts the `pass=selfgate` record and checks it with `crew-precheck.py --pass selfgate`, and falls back to the crew lane on a capped open finding, a new sensitive or tightening match, or the owner's ask. The renderer fills `<flavor-selfgate-engine>` from `flavor.selfgate_engine` (default `different`), and harness adapters gain a code-review skill field (Claude Code `code-review`, Codex `codex review`; none declared for Pi, Cursor and Muse). (issue #671, PR #704, 2026-11-03) Box skill copy: deferred (tmux mirror deferral; Grok Bot runs express items in the crew lane).
- `scripts/metrics-refresh.py` adds the express-lane metric columns to `prs.csv` and `prs.md`: `lane`, `selfgate_mode`, `selfgate_reviews`, `selfgate_findings`, `dispatch_to_merge_min`, `ci_red_rounds` (every lane), `merge_ups` and `reverted`. The metrics README defines each field. Offline tests cover every column through a fake `gh`. (issue #675, PR #697, 2026-11-03) Box skill copy: none.
- Add `crew-precheck.py --pass selfgate` for express changes. It reads the latest signed builder `pass=selfgate` record at the full head SHA, rejects a malformed record (exact field set, full `base`, `round=n/a`, `pr` matching the PR, `reviews` from 1 to the express cap, `open` at most `findings`), and fails a `changes` verdict, a `pass` with open findings or failed checks, a `mode` other than the profile's effective `selfgate_engine`, and, under `different`, a reviewer engine (before the first `/`; model IDs may contain `/`) that matches the record's builder engine or any commit's `Engine:` trailer. The precheck pass is unchanged. (issue #670, PR #696, 2026-11-03) Box skill copy: none.
- Make release a backend concern. `docs/interfaces.md` adds an optional `release` concern (`cut`, `approve-check`, `record-release`, `notify`), declared in the GitHub pack, mapped in `templates/backends/github.toml` and named in the default profile. An optional `[release]` profile table (`changelog`, `fragments`, `versioning`, `release_id = "tag" | "commit"`) defaults to today's behaviour; with it, `resolve` fails closed unless `approve-check` and `record-release` are kept. The release gate row is backend-neutral with the same satisfaction, and `docs/release.md` gives the GitHub binding (unchanged `release.yml`) plus a commit-hash reference binding covering the version pin, update path and rollback. `scripts/changelog-cut.py` no longer loads `check-repo.py`, takes paths from `--project` or flags, and accepts fragments with only `type`; eng-crew's own cut output is byte-identical. (issue #585, PR #693, 2026-11-03) Box skill copy: none (rendered briefs unchanged; no template uses the release operations).
- `crew brief` prints the `## This run` block (required `Item`, `Pass`, `Base`; optional `Window`, `Round`, `Slot`, `Host`, `Worktree`, `Engine`, `Claim`, `Flavor`, `Comments`) for any runtime or session backend, and exits 2 with no block when a required field is missing. `crew spawn` builds its tmux block with the same helper (output unchanged). The session runtime docs show hosted dispatch with it, and the worker brief rules say a pass does not start without the block. (issue #647, PR #692, 2026-11-03) Box skill copy: pending coordinator mirror.
- `crew schedule decide --pool builder|reviewer` makes the crew scheduler's admission decision under `schedule/lock`. It ranks both pools' demand, grants the caller's items within the pool cap, the target T, the ramp limit and the optional `max_suites`/`max_load` ceilings, and reserves only the caller's grants in `schedule/reservations.json` (they expire after 600 seconds or when a run record appears). The other pool's would-be grants become holds for that walk only: they are dropped as `lead-down` when that pool's lead is down, and otherwise the owning lead gets a backstop nudge. Each pool's floor admits its top item past T, the ramp and the ceilings. Every decision appends a snapshot line and its admits, holds and new defers to `schedule/decisions-<yyyymmdd>.jsonl` (7 days kept). `crew schedule release` frees a reservation after a failed spawn. `crew dequeue --ref #N` starts only that queued request, so the lead starts the scheduler's grant instead of the oldest request. The builder lead brief now calls `schedule decide` instead of `crew lead capacity`; the reviewer lead is unchanged until S7. (issue #624, PR #691, 2026-11-03) Box skill copy: none.
- Add coordinator triage for the express lane. `item-flavor.py --labels` checks an `express` record's eligibility: a `crew:sensitive` or `crew:spec` item needs a whole-line `Owner override:` quote in the record, a `crew:solo` item never qualifies, and a missing `--labels` fails closed. An ineligible record resolves to the default with status `express-ineligible`, its `blockers`, and exit 1. `templates/triage-flavor.md` adds the express steps: sensitive classifier first, the check, then `crew:express` only on a recorded express flavor. (issue #674, PR #689, 2026-11-03) Box skill copy: none.
- Add `[runtime.options.launch]` to the tmux profile: `coordinator` (`tmux` or `none`, a preflight-only `crew up`), `roles` (`tmux`, `hosted` or `none`; `crew up --coordinator-only` for one run), `resume` (`fresh`, `ask` or a Claude Code or Codex session id) and `reconcile` (`backend`). With the table absent `crew up` is unchanged; with hosted or no roles it opens only the coordinator window, tagged as before, and starts no lead windows. The control-item ownership read now follows `backends.markers.name`: for a non-GitHub backend, `crew up` records its rendered `markers.read-item` command and the read runs it instead of `gh api`, failing closed to read-only. The tmux runtime doc lists each reconciliation read by backend operation, with a placeholder non-GitHub pack binding. (issue #606, PR #688, 2026-11-03) Box skill copy: none.
- Write the express lane into the protocol. §3 adds express resolution (`class-flavor --express`, tightening and sensitive/spec exclusions, `review = off` only for express) and the builder's selfgate record with its `pass=selfgate` hidden line. §4 adds the `selfgate` pass and the `crew:express` state tag. §7 and the gate registry add the express self-gate, which replaces formal approval for an express change and keeps every other gate. The portable spec §3 records the scoped I1 and I2 exception, and `docs/architecture.md` adds the label and pass rows. Until the routing build issue lands, an express change is still reviewed as usual. (issue #669, PR #687, 2026-11-03) Box skill copy: deferred (tmux mirror deferral; Grok Bot runs express items in the crew lane).
- Team files: one `<config-home>/teams/<team>.toml` holds a crew's team-only settings under `[team]`, with `pack`, `personas` and `accounts` shorthands. Each repo gets a small `[repos.<name>]` section that may set only an allowlist: repo, default branch, precheck, sensitive paths and landing overrides. A project reference `<file>#<repo>` resolves as core < default < org < team < repo. A legacy `crew.toml` resolves byte-identically. `crew up --team <file>` starts one session and coordinator for every repo, with a render per repo under `<state_dir>/<team>/<owner>__<repo>`. docs/profile.md gains a migration note from two `crew.toml` files to one team file. (issue #634, PR #686, 2026-11-03) Box skill copy: none (config tooling and docs; no template changes).
- Packs can extend the rendered briefs without copying `templates/`. A pack's `render/` directory overlays the render inputs per file (`crew-render.py`, `crew bootstrap`, `crew up`, `crew upgrade` and `check-skill-drift.py`). Every `gh` call in the tmux briefs now goes through a backend operation, with new `change`, `state-tags` and `markers` operations; the GitHub render is byte-identical. A backend map can declare extra run-time placeholders with `[placeholders] kept`. `runtime.options.notes.render` appends notes for any role, leads included, at render time, where `size_budget` and the drift check see them. (issue #580, PR #685, 2026-11-03) Box skill copy: none.
- Add the item-only `express` flavor preset (`review = off`, `validation = off`, `merge = auto`) and the `flavor.selfgate_engine` knob (`different` by default, or `same`). The validator rejects `express` as a project, class or custom base flavor, and `review = "off"` anywhere else still fails as `floor F4`. `crew-config.py class-flavor --express` applies the express knobs unless a path matches a tightening class, and reports `lane` and `tightening`. `item-flavor.py` accepts an `express` record that has a `Reason:` line, but never accepts `express` as a default. `docs/flavors.md` adds the preset and the scoped F4, I1 and I2 exceptions. (issue #668, PR #680, 2026-11-03) Box skill copy: none.
- The crew scheduler computes its crew-wide target T in `schedule/target.json`: T starts at the busy count, stays between 1 and the sum of the pool caps, and moves by one at most once per `schedule_interval`, down on any high signal (load, memory pressure, gateway errors) and up when every signal is low and demand waits; unknown signals hold it. A ramp limit counts starts per interval. New profile options `load_high`, `load_low`, `error_high`, `schedule_interval` and `schedule_ramp` are validated. No command calls the target yet; admission is unchanged. (issue #623, PR #678, 2026-11-03) Box skill copy: none.
- Gateway errors now reach the crew scheduler's input `schedule/errors.jsonl`. `crew watch` matches each live run's screen against its harness adapter's new transient-error text (Claude Code and Codex declare it; Pi, Cursor and Muse declare none) and appends each new line, and `crew train land` appends a stop or pause whose reason names HTTP 429, a 5xx or a rate limit. The same text from the same source within 10 minutes counts once. `crew schedule snapshot` already counts the file's last 10 minutes; nothing admits on it yet. (issue #621, PR #667, 2026-11-03) Box skill copy: none.
- The crew scheduler ranks both pools' demand from a schedule snapshot in one list: the eight finish-before-start classes of the scheduling design, then milestone order, `Depends on` critical path (open items waiting, directly or transitively) and age. It is a pure function with no command yet and changes no admission. (issue #622, PR #665, 2026-11-03) Box skill copy: none.
- `scripts/evidence-cli.py` captures CLI, service and API evidence mechanically: a header with proof label, capture SHA and working directory, a copyable `sh` block with optional setup, and the exit code, stdout and stderr in separate sections with scrub notes. Builder briefs now require CLI proof from the helper or the template script, never hand-written, with executable setup and deferred AC evidence in a signed fix review; reviewer briefs make a capture without the header, or one that does not reproduce, one finding with the re-run output. This keeps evidence quality independent of the builder and reviewer models. (issue #652, PR #658, 2026-11-02) Box skill copy: pending coordinator mirror.
- Add a paste-ready coordinator-session brief (`templates/runtimes/session/coordinator.md`) that carries the ownership guard and the runtime handoff outgoing and incoming steps until the session binding exists, and `crew ownership --runtime session`, which checks the record as `session@<runtime.instance>`. This is build issue B of the runtime handoff design. (issue #638, PR #656, 2026-11-03) Box skill copy: none (session template; no Grok Bot routine changes).
- Builders can now catch common markdownlint failures locally without the binary: the new dependency-free `scripts/check-markdown.py` covers MD001, MD003, MD009, MD012, MD018, MD022, MD031, MD032, MD040, MD047 and MD056 (the rules this repo configures and has failed in CI, such as MD018 and MD056). It checks the changed `*.md` files by default (`--all` for every tracked file) and prints `path:line rule message`. `check-repo.py` runs it on every tracked `*.md` file as a new `markdown` check, so the targeted local set and the tmux builder brief pick it up without an extra step. The whole repo passes, and CI's markdownlint stays the authority (`scripts/README.md#markdown-lint`). (issue #644, PR #655, 2026-11-02) Box skill copy: pending coordinator mirror.
- Owner handoff chat commands: protocol §9 now defines `/crew handoff to <runtime-id> [drain | stop] [deadline <minutes>]`, `/crew handoff abort` and `/crew takeover from <runtime-id>`, given in the coordinator chat and recorded with `cmd-id=chat`. On tmux the new `crew handoff to|abort|takeover` re-reads the ownership record, refuses an illegal transition and posts the signed `draining`, `aborted` or `takeover` state on the control item. A drain writes `asks/handoff.json` so the watcher wakes the coordinator at the deadline, and the Stop guard now keeps its normal block while draining so the coordinator sees in-flight runs end. This is build issue A of the runtime handoff design. (issue #637, PR #654, 2026-11-02) Box skill copy: pending coordinator mirror.
- Express lane design doc: an opt-in `express` flavor where one builder builds, self-reviews and tests end to end, and the change lands on green CI with no independent review or validation. It scopes the floor exceptions to `crew:express` changes (F4's verdict post and I1, plus I2 only when the `selfgate_engine` flip is `same`), excludes sensitive and spec items unless the owner overrides per item, and defines the self-gate loop that loads the reviewer rubric in a fresh sub-session, the signed `pass=selfgate` record, the §7 express gate row, tmux routing, trade-offs, per-lane metric columns and build issues. Design only: it adds no rule until its build issues land. (issue #636, PR #651, 2026-11-02) Box skill copy: none (design doc only).
- `scripts/run-tests.py` runs the `scripts/test-*.py` suite in parallel (`-j N`, default the CPU count up to 8), prints per-file durations and the slowest files, shows the output of every failing file and exits non-zero on any failure. CI's `repo-guard` job runs the full suite with it in one step instead of one step per test. (issue #613, PR #650, 2026-11-02) Box skill copy: none.
- `crew schedule snapshot` prints one JSON object with every crew scheduler input from the scheduling design: both pools' pending demand by kind, worker state, reservations, open trains, open milestones and issue dependencies, normalized load, memory pressure on macOS and Linux, local suites, recent gateway errors and each pool's cap. A failed read is `unknown` for that input only. It is read-only and changes no admission yet. (issue #620, PR #642, 2026-11-02) Box skill copy: none.
- Add `crew handoff manifest` and `crew handoff reconcile` with the `templates/handoff-manifest.md` template. The outgoing coordinator's manifest lists open crew items as dependency-closed sets, by reference only, secret-scanned and within one post. Posting re-reads the control item first and posts `offered` only once per handoff id, so a retry never makes a second handoff and nothing is posted after the ack. The incoming side's read-only plan adopts each set, holds a set whose PR head moved, and skips sets it already claims. Tests cover retry, partial and duplicate-ack cases. (issue #211, PR #633, 2026-11-02) Box skill copy: none.

### Changed

- **Breaking:** The reviewer lead now admits through `crew schedule decide --pool reviewer` instead of `crew reviewer-pool`'s own capacity check. Before each reviewer spawn, the dispatcher starts the pass only when decide admits its PR, and it releases the grant if the spawn fails. A deferral prints `crew: reviewer admission deferred: #PR REASON` and the request stays pending. A review held by a builder-lead call is granted on the next reviewer call, and the reviewer floor admits one pass under builder load. The scheduler snapshot now ranks a reviewer `work` event as the pass it starts: a new head, fix at head, merge-up, built PR or recheck escalation as a review, and a passing review as a validation. Before dispatching a stale, dialog or lifecycle wake whose worker has written `done:`, the reviewer lead saves the event as that status wake (line and round), so a review reclaimed through `crew kill` still ranks its validation and a deferral keeps it pending until a later call starts it. `crew reviewer-pool` no longer takes `--suites`. Migration: drop `--suites` from `crew reviewer-pool` calls; admission is `crew schedule decide`. (issue #625, PR #707, 2026-11-03) Box skill copy: none.
- **Breaking:** Validation scope is bounded by default. A new rigor knob, `validation_scope` (`repo` · `bounded`), sets how far the validate pass reaches: `bounded` (every preset but `thorough`) runs the item's acceptance checks and only the checks covering the files changed at head, using the configured `builder.precheck` test command for those paths, and cites green CI at head for the rest. `repo` (thorough, or a custom flavor or class rule) adds the configured repo-wide lint and test commands. The tmux and Grok Bot reviewer briefs render the scope baseline and the configured commands instead of a fixed `scripts/check-repo.py` / `scripts/test-*.py` list; docs/flavors.md adds a validation cost note. Migration: set `validation_scope = "repo"` in a custom flavor or class rule, or `[flavor] name = "thorough"`, to keep the repo-wide validate pass. (issue #648, PR #698, 2026-11-03) Box skill copy: pending coordinator mirror (reviewer templates).
- **Breaking:** An unset project flavor now resolves `standard` (thin review, validation for behaviour changes only) instead of `thorough`, still flagged as `flavor.name = "standard"  # core (unset: flagged)`. Rendered briefs for unset projects now carry the standard `Flavor:` baseline line, and `item-flavor.py`, class matching and class validation use the same default. Item records and class rules still raise rigor; `thorough` stays the preset for releases, security and gate-contract work, and the flavor docs recommend a `thorough` class for gate-defining paths. Unset all of 2026-11-02, validation found problems after a passing review in 2 of 217 rounds (0.9%). Migration: set `[flavor] name = "thorough"` to keep the old behaviour. (issue #632, PR #681, 2026-11-03) Box skill copy: pending coordinator mirror.
- **Breaking:** The release gate now also requires a green `ci.yml` push run at the cut's exact SHA. `release.yml` adds a `ci-gate` job that waits up to 40 minutes for that run and refuses publishing on a red, cancelled, missing or still-pending run; `workflow_dispatch` runs the same check at the dispatched commit. The `validate` job drops its own `check-repo.py` and every-test loop (now 10 minutes) and keeps only release-specific checks; `ci.yml` runs the suite once. `ci.yml` cancels superseded runs only for pull requests and groups `main` runs per commit, so a quick second merge no longer cancels the cut's CI. A publishing run whose actor is not `RELEASE_OWNER` now fails in `prepare`, before validation, naming the fix (dispatch as the owner account, or have the synthesizer merge). Migration: after a CI refusal, re-run CI to green, then re-run the failed release jobs. The release design and gate registry row describe the sequenced gate. (issue #615, PR #677, 2026-11-03) Box skill copy: none.
- CLI evidence for a command that only runs against test fakes (a fake tmux, a fake `gh`, a temp git origin) may use a named test command as its repro pair, when no real-environment run is possible without the fakes. The test must invoke the changed command and assert its exit code, stdout and stderr; the validator re-runs it at head and diffs it like any other pair. The verification CLI row and Q2, protocol §3, the tmux builder and reviewer briefs, Grok Bot B1, the reviewer-validator and V2 watch prompts, and their render and parity fixtures carry the rule. (issue #653, PR #660, 2026-11-02) Box skill copy: pending coordinator mirror.
- `crew train build` keeps approved PRs that change the same paths together in one train, in the dependency then approval order the synthesizer supplies, and drops a member only when its merge actually conflicts (`reason=conflict`). It no longer defers clean overlapping members with `reason=overlap` for a merge-up after the train. Train CI still tests the combined result, so the land gate is unchanged. The tmux synthesizer brief and the crew train docs say the same (crew scheduler design S9, #587). (issue #627, PR #645, 2026-11-02) Box skill copy: deferred to #140 (tmux synthesizer brief only).
- Lead admission is caps only by default: the hard-coded one-minute load gate (`load >= cpus`) is gone and `max_suites` no longer defaults to `cpus // 4`. Two optional gates, both unset by default, defer expansion when reached: `max_suites` on observed local suites and the new `max_load`, a positive number compared with the one-minute load average. A missing load or suite observation defers admission only when a configured gate needs it, and an empty reviewer pool still keeps one slot at a reached gate. This is build issue S1 of the crew scheduler design. (issue #619, PR #643, 2026-11-02) Box skill copy: none (tmux only).
- A release cut PR may carry a release-pipeline fix (`release.yml`, `ci.yml`, `scripts/release-*.py` or `scripts/changelog-cut.py`) without a fragment: `check-changelog-pr.py` recognises a cut diff and instead requires a new entry naming the issue in the new version section. Any other change in a cut, or a non-cut change without a fragment, is still refused. (issue #616, PR #618, 2026-11-02) Box skill copy: none.
- Builders run a targeted local test set instead of the full suite on builds, fix rounds and release cuts: `check-repo.py` and `check-changelog-pr.py` always, the test named for each changed script, render and parity tests when templates or fixtures change, and release and changelog tests for a cut. Diffs touching shared plumbing (`scripts/crew.d/_shared.py`, `scripts/crew`, the config and render cores) still run the full suite locally. The PR Testing section lists the set and its coverage reason; PR CI runs the full suite, and red CI still returns as a ci-red round. AGENTS.md, the tmux builder brief, Grok Bot B1 and their render and parity fixtures follow the new rule. (issue #614, PR #617, 2026-11-03) Box skill copy: pending coordinator mirror.

### Removed

- **Breaking:** Retire `crew lead capacity` and its `--suites`/`--queued` flags: both leads now admit through `crew schedule decide`, and no brief calls it. `docs/scheduling.md` is marked built and records the owner's 2026-11-03 overlap decision (D + S9): builds are not overlap-sequenced, S8 (#626) is closed unbuilt and the `Touches:` triage footprint is dropped, while overlap trains (#627) stay. The tmux binding's Q6, builder lead section and Scaling policy inputs point to the scheduler as built. Migration: call `crew schedule decide --pool builder|reviewer` instead of `crew lead capacity`. (issue #629, PR #709, 2026-11-03) Box skill copy: none.

### Fixed

- **Breaking:** Stop transient GitHub failures from waking the coordinator. `crew poll` retries its PR and issue list reads when one fails with a 5xx, timeout or connection reset (three retries, 1, 2 and 4 s apart) and exits 75 (`EX_TEMPFAIL`) if the failure persists. `crew watch` records a source cut off at `--source-timeout` (now 60 s by default) or exiting 75 as a line in `wake/incidents.jsonl` instead of waking, and sends one `source-failing` wake with the count after `--source-failures` (default 3) in a row; a clean run resets the count. The watcher also re-execs itself in place, before it queues or routes a scan's wakes, when `scripts/crew`, `crew.d/*.py` or `crew-*.py` change on disk, so a crew-home update no longer leaves an old process validating new profile keys (folds in #703). Migration: a wrapper of `crew poll --once` that read exit 1 as any failure should treat exit 75 as a transient failure and retry. (issue #702, PR #708, 2026-11-03) Box skill copy: none (tmux CLI only).
- `crew kill` and idle-builder reclaim no longer report a squash-merged builder worktree as unlanded when the builder's `done: #<issue> #<pr> <sha>` line carries a trailing note. The PR number is now read from a done line with text after the SHA, so the `pull/<n>/head` commits count as landed after the branch is deleted. (issue #695, PR #699, 2026-11-03) Box skill copy: none (tmux only).
- `crew train check` now accepts an inline `sh` + `text` reproduction anywhere in the PR body, such as captures under `## Test Output` that the Acceptance Evidence table references, as well as in signed builder fix or ci-fix reviews at head. Required `evidence/` artifact paths are still read only from the Acceptance Evidence section and those builder reviews, and reviewer or coordinator posts still count for neither. (issue #679, PR #684, 2026-11-03) Box skill copy: none.
- `crew train check` no longer blocks on prefixed paths such as `templates/evidence/cli-exit-stdout.md` or `.crew/evidence/<file>`: only a repo-root `evidence/<path>` counts as a required artifact. The evidence gate reads only the PR body's `## Acceptance Evidence` section and signed builder fix or ci-fix reviews at head, so another role's mention creates no requirement, and it accepts inline reproductions in those reviews and in `~~~` fences. (issue #657, PR #666, 2026-11-03) Box skill copy: none.
- The release workflow's `validate` job timeout is raised from 10 to 25 minutes, matching CI's `repo-guard`. It runs the same full suite, so the v3.2.0 cut's release run was cancelled at the 10-minute limit with no failing test, and the release could not publish. No other workflow job runs the full suite. (issue #610, PR #612, 2026-11-02) Box skill copy: none.

## [3.2.0] - 2026-11-03

### Added

- Added the crew scheduler design (docs/scheduling.md): one crew-wide `crew schedule decide` that both pool leads call, built from observable crew demand, item priority, worker state, machine load, memory pressure, gateway errors and owner presence. It ranks finishing work before new builds, moves a crew-wide concurrency target between load watermarks with a ramp limit instead of on/off gates, keeps one slot per pool so reviews cannot starve, sequences builds that touch the same files, records every admit, defer and reclaim with reasons, and lists eleven follow-up build issues. Design only: admission is unchanged until those land. (issue #587, PR #604, 2026-11-02) Box skill copy: none.
- Add an optional per-role engine override, `[engines.roles.<role>] order = [...]`, for spawned roles. It replaces the tier order for that role's workers (the tier still sets effort), reviewer independence still filters it, and `validate`, `resolve`, `crew doctor` and `crew up` read it. (issue #597, PR #602, 2026-11-03) Box skill copy: none (profile schema and spawn engine choice; no box skill change).
- Add the Cursor harness adapter with interactive launch, coordinator reload and foreground probing, fake-binary coverage and explicit trust, effort and bootstrap gaps. Engine quota and contributor-tier rules still apply. (issue #201, PR #593, 2026-11-02) Box skill copy: none.
- Add a profile-selected local herdr session adapter with background run workspaces,
  read-only observation, verified doorbells and OS-backed identity and process
  cleanup, covered by fake-binary tests. Document backend capability gaps. (issue #203, PR #590, 2026-11-02) Box skill copy: none.
- Muse can launch coordinator, worker and pool-lead sessions through the tmux harness adapter with model, reasoning effort and brief pointers. Versioned foreground processes are recognized at startup, probe and wake; trust and login dialogs remain ambiguous. Private repositories, unreadable visibility and unverified permission modes are refused. Fake-binary lifecycle tests cover launch, completion and cleanup; the adapter records remaining live-session, turn-end guard and bootstrap gaps. (issue #202, PR #589, 2026-11-02) Box skill copy: none.
- Role briefs in both runtimes render project flavor review, validation, evidence, caps, merge and builder values from presets and custom knobs. Optional diff paths apply class rigor at render time; absent flavor remains thorough, with existing precheck settings and owner grants preserved. Live item/path resolution and every merge gate still apply. (issue #351, PR #588, 2026-11-02) Box skill copy: eng-pr-pipeline, eng-crew-roles.
- Pi can launch coordinator, worker and pool-lead sessions through the tmux harness adapter, preserving provider-qualified models, thinking effort and brief pointers. Fake-binary tests cover launch, liveness and cleanup; unsupported approval modes are refused. The adapter documents provider eligibility and remaining live-wake, turn-end guard and bootstrap gaps. (issue #200, PR #583, 2026-11-02) Box skill copy: none.
- Add optional owner-present builder and reviewer limits. Both pools switch admission live between owner-friendly present limits and full away caps, preserve running workers, and honor an optional away bound. Restore the coordinator brief’s owner-away and first-return-message instructions after the merge-up. (issue #577, PR #582, 2026-11-02) Box skill copy: pending coordinator mirror.
- Add `/crew away --cap <n>` to limit concurrent runs while away and `--quiet` to batch notifications while the owner stays present, with the normal SLA clock and every authority gate unchanged. Extend the away record and contract tests. (issue #199, PR #579, 2026-11-02) Box skill copy: pending coordinator mirror.
- Add an away-only Slack notification binding with environment-only webhook credentials, durable event deduplication, bounded retry backoff, progress digest wakes and delivery failure evidence for the return brief. Recorded asks and approvals remain on GitHub. (issue #495, PR #576, 2026-11-02) Box skill copy: deferred to #140.
- Record project flavor in bootstrap profiles and item rigor at triage, with a coordinator contract, signed record template and offline resolver tests for defaults and refused reasonless lowering. (issue #196, PR #575, 2026-11-02) Box skill copy: pending coordinator mirror.
- Add runtime.options.max_active_milestones (integer at least 1, default 1) to both
  runtimes. Coordinator briefs render the limit and prioritize the earliest
  milestone, using later milestones only for spare builder capacity while
  in-flight PRs in any milestone finish. (issue #566, PR #571, 2026-11-02) Box skill copy: pending coordinator mirror.
- Add the solo coding-agent lane, its crew:solo routing label and flavor preset, and a paste-ready session brief sharing the builder PR and fix contract. Builder dispatch and fix delivery skip solo items; independent review, inline evidence, the floor and synthesizer landing remain required. (issue #102, PR #569, 2026-11-02) Box skill copy: pending coordinator mirror.
- Add deterministic path class flavor matching with a JSON CLI, knob-wise strictest rigor, layered class rules, and fail-closed invalid input. Document recorded owner overrides and keep sensitive classification and merge authority separate. (issue #197, PR #568, 2026-11-02) Box skill copy: none.
- Record owner away mode on the project tracking issue, batch notifications while preserving SLA defaults and every authority gate, and send one standalone return brief on the first owner message back. Add steering and coordinator instructions, the return template, and contract tests. (issue #198, PR #565, 2026-11-02) Box skill copy: pending coordinator mirror.
- Validate named thorough, standard and fast flavors, custom knob compositions and class declarations against closed profile tables and the seven floor rules. Check class lowering reasons, caps, resource limits and engine routes; resolve an unset project flavor to thorough with flagged provenance. Runtime gate application remains a separate integration. (issue #195, PR #564, 2026-11-02) Box skill copy: none.

### Changed

- Cut coordinator wake noise from `crew watch`. An idle live lead or synthesizer, with no queued or in-flight work, no longer raises a stale wake. A synthesizer gate-status block that only waits on CI, review, validation or a train now carries `wait=<items>` and is recorded without a wake. `ci-failed` records for a superseded head are dropped by the poller and by route. A lead's `unblocked` message for a block that resolved itself is recorded in the coordinator inbox without a nudge. (issue #578, PR #600, 2026-11-02) Box skill copy: none (tmux only).
- Define change flavor rules for review, validation, evidence, caps and merge permission in protocol §3/§5/§7 and the gate registry. Role templates resolve item/path rigor at head, record justified validation skips and optionally name the effective flavor on verdicts. Existing owner standing grants retain their recorded scope until the renderer migration; grants remain scoped and sensitive/spec gate changes require owner permission. (issue #350, PR #581, 2026-11-02) Box skill copy: pending coordinator mirror.
- Document separate Cursor parent-turn and CLI worker quota meters, diagnostic per-stage wake targets, reference-only handoffs, stable worker sessions and prefixes, and sequential issue lanes unless independence is recorded. Tie cost choices to tier and flavor configuration while preserving all merge gates; defer the quiet-week comparison until metrics data exists. (issue #109, PR #570, 2026-11-02) Box skill copy: pending coordinator mirror.

### Fixed

- CI's `repo-guard` job timeout is raised from 10 to 25 minutes. The suite had grown to about 10 minutes, so main and PR runs were cancelled at the limit with no failing test, and nothing could land. Splitting the job into parallel jobs is left as a follow-up. (issue #607, PR #608, 2026-11-02) Box skill copy: none.
- Verify the Codex coordinator wake path on codex-cli 0.164.0 and fix its turn-end notify recipe: the recipe now pipes Codex's turn payload to `crew guard`, types the wake line with a 0.3 s settle before Enter (a single send-keys left it unsent in the composer), and `crew guard` treats a turn started by its own wake line as already continuing, so it blocks once per stop cycle instead of looping every few seconds. `crew up` still does not install the recipe. (issue #170, PR #605, 2026-11-02) Box skill copy: none.
- `crew dequeue` now decides idle-builder reclaim against the same effective builder pool cap as admission (the owner-present cap, or the recorded-away cap), not the full `builders` cap, so a full builder band with the present cap reached no longer reclaims an idle builder whose slot it cannot use. (issue #598, PR #601, 2026-11-02) Box skill copy: none.
- Stop `crew watch` crashing when a run record is reaped between listing and stat: the scan and `heartbeat()` now skip a record that disappears mid-scan. A watcher started while another live `crew watch` is armed exits 1 without touching its PID file or watch state, and a watcher removes `wake/watcher.pid` on exit only when the file holds its own PID. (issue #591, PR #599, 2026-11-02) Box skill copy: none (tmux only).
- Count only busy builders for admission, reclaim the longest-idle pushed builder with output retained when windows are full, and expire idle builders after a configurable 30 minutes. Stop descendant process groups during cleanup and exclude closed or merged items from lead suite probes, so finished work cannot block new builds. (issue #572, PR #586, 2026-11-02) Box skill copy: none (tmux only).
- Pool leads admit workers while running suites stay below the profile max_suites cap (defaulting to one per four CPUs) and CPU load stays below the CPU count. An empty reviewer pool retains one slot under known load or suite pressure; unavailable observations still defer admission. (issue #567, PR #573, 2026-11-02) Box skill copy: none.
- Retry pending lead admission when any worker finishes and every 60 seconds while requests remain pending. Start delta review and independent validation after a signed builder fix records a resolved merge-up conflict or differing patch at the new head; identical merge-ups retain synthesizer verdict portability. (issue #547, PR #563, 2026-11-02) Box skill copy: none.
- Builder lead records admission deferrals locally and reports only actionable blocks to the coordinator, deduplicating identical notifications across restarts. The router consumes deferred status wakes without coordinator action. (issue #542, PR #562, 2026-11-02) Box skill copy: none.

## [3.1.0] - 2026-11-02

### Added

- Profile validate and resolve support --install to reject unfilled install-time placeholders while retaining the renderer's run-time placeholders and ordinary template validation. (issue #166, PR #556, 2026-11-02) Box skill copy: none.
- Bootstrap proposes missing project profiles from local git config, records owner-confirmed or edited TOML once, and preserves the flavor answer as a comment pending M18. Existing profiles remain authoritative. (issue #191, PR #555, 2026-11-02) Box skill copy: none.
- Projects can record an org pack directory in paths.pack, resolving its optional profile without repeating --org-profile and preserving explicit overrides and layer precedence. (issue #166, PR #554, 2026-11-02) Box skill copy: none.
- Profile validation and resolution accept an explicit external pack manifest declaring a new backend, while retaining capability checks, profile overrides and bundled GitHub defaults. (issue #166, PR #553, 2026-11-02) Box skill copy: none.
- `crew upgrade` previews and re-renders a pinned tmux install, waits for active passes, and restarts roles in place with the coordinator last. Worktrees, claims and inboxes survive; unchanged installs do not restart. (issue #192, PR #545, 2026-11-02) Box skill copy: none.
- Grok Bot renders eng-pr-pipeline and eng-crew-roles skills from the bundle's reviewed docs alongside routines, so deployment and render-vs-live drift checks replace hand mirroring. Budget measurement uses fixed path tokens for included skill links, keeping byte counts independent of the install root. (issue #341, PR #543, 2026-11-02) Box skill copy: deferred to #140.
- Design the single-session runtime binding with explicit C1–C9 contract gaps, harness and worker lifecycle boundaries, attended operation, safe recovery and implementation follow-ups. The proposed `session` profile selector remains unimplemented; bootstrap pointers provide no new runtime capabilities. (issue #340, PR #541, 2026-11-02) Box skill copy: none.
- Long-lived reviewer lead in reserved window 3 owns review, validation, recheck escalation and terminal reclaim through durable serialized handoffs, cap/load/suite admission and one-restart supervision. Replay recovers missing validation and deduplicates fresh passes while preserving synthesizer verdict portability. Failed Actions jobs with no started steps are infrastructure incidents: validation may proceed, but green CI remains required for landing. Scaling, replay and recovery fixtures accompany the change. (issue #531, PR #537, 2026-11-01) Box skill copy: deferred to #140.
- Long-lived builder lead with a reserved session window, durable reference handoffs, cap/load/suite admission decisions, and one identity-checked restart with its inbox and workers preserved. The coordinator hands builder lifecycle to the lead; automatic cross-pool dequeue stops for lead-owned builders. Fixtures cover scaling, replay, restart, ambiguity, and cleanup boundaries. Part of the role-lead split under issue #521. (issue #530, PR #534, 2026-11-01) Box skill copy: deferred to #140.

### Changed

- CI feeds the repository CREW_DENYLIST secret to the repo guard through a private temporary file, without logging its terms, and removes the file on success or failure. (issue #166, PR #557, 2026-11-02) Box skill copy: none.

### Fixed

- Bootstrap measures role brief budgets with install-time path placeholders rendered as a fixed token, so install-path length cannot change the result. Diagnostics and profile/bootstrap docs name the path-normalized UTF-8 byte measure. The tmux coordinator and synthesizer briefs reference the full protocol landing rules instead of repeating them, restoring at least 1 KiB of default-budget headroom. Tests cover short and long roots, UTF-8 boundaries and over-budget rejection. (issue #540, PR #544, 2026-11-02) Box skill copy: deferred to #140.

## [3.0.0] - 2026-11-02

### Added

- `crew train bisect` tests ordered halves of a red train, identifies failing members and rebuilds survivors together on the default branch for normal head-bound landing. Failed predecessors cannot seed `--after`; green combined retries recover flaky trains. (issue #463, PR #526, 2026-11-01) Box skill copy: none.
- Proposed builder and reviewer role-lead contract in the tmux binding: pool authority, durable handoffs, scaling inputs, pass deduplication, and worker/lead recovery. This is the required design review before implementation; current runtime behavior is unchanged, and the builder/reviewer code and fixture coverage remain pending. (issue #521, PR #525, 2026-11-01) Box skill copy: none.
- tmux profiles can configure ordered standing runtime note files per role in `runtime.options.notes`. Each launch appends the current file contents under a heading naming the file; missing or unreadable notes block launch. Worker spawns and coordinator startup load their own notes, and omitted notes leave briefs unchanged. The profile and runtime docs explain configuration, and the coordinator brief uses this option instead of repeated manual policy sends. (issue #492, PR #514, 2026-11-01) Box skill copy: deferred to #140.
- Metrics refresh records builder precheck markers and reports rounds per PR, request-changes verdict rate and mean PR-to-merge time by repo and recorded versus unrecorded precheck cohort. Counts and empty denominators are explicit; unrecorded checks do not establish that the profile switch was disabled. Offline fixtures cover marker parsing, duplicate verdicts, closed unmerged PRs and the CSV/Markdown CLI output. No gate thresholds changed. (issue #183, PR #513, 2026-11-01) Box skill copy: none.
- Gate review, validation and every land on the enabled builder pre-review check:
  require fresh passing or reasoned N/A step results, with only an owner’s
  per-change override. Add a shared marker checker and missing, stale, failed
  and passing fixtures; update reviewer and synthesizer instructions. (issue #182, PR #497, 2026-11-01) Box skill copy: pending coordinator mirror.
- Optional `builder.precheck` profile settings supply lint, test and docs commands
  and a positive fix-attempt limit. Enabled profiles render ordered builder steps;
  disabled profiles retain existing briefs, and missing commands render as `n/a`.
  Validator and renderer tests cover the switch and layered overrides. No merge
  gate change. (issue #181, PR #470, 2026-11-01) Box skill copy: pending coordinator mirror.
- Record today's engineering orchestration roles in `roles/eng.toml`, with a schema validator and equivalence tests for tmux constants, including reviewer recheck and merge-up wakes. The runtime continues using its existing constants (roadmap 15.8). (issue #318, PR #467, 2026-11-01) Box skill copy: none.
- Bootstrap self-test enforces per-role UTF-8 byte budgets for rendered briefs
  and role-owned runtime Markdown files. The optional `size_budget` profile
  table defaults each role to 16 KiB per file; oversized files fail installation
  verification with their rendered path, byte count, role and limit. (issue #194, PR #459, 2026-11-01) Box skill copy: none.
- The tmux runtime detects approved default-branch merge-ups and routes one fresh recheck session to inspect resolution hunks, rerun acceptance checks and post a merge-up re-approve at the new head. Non-mechanical resolutions return to full review and validation; the approval round and merge gates stay unchanged. (issue #454, PR #456, 2026-11-01) Box skill copy: coordinator deploy required.
- Prepare successor merge trains while a predecessor runs CI or lands, with
  `train build --after N --no-wait` and `train wait N`; rebuild a successor
  on current main after its predecessor stops. Landing stays serial and
  head-bound. `train check` reports read-only gate snapshots, with manual
  verification named explicitly. Pairwise merge checks defer likely conflicts
  before a train merge, while clean shared-file pairs stay together. (issue #451, PR #455, 2026-11-01) Box skill copy: tmux brief rendered; live deployment deferred to coordinator.
- Role registry schema (15.7): closed TOML fields and validation contract, worked examples for all four current roles, and the hard-coded migration inventory. Documentation only; runtime migration remains in 15.9 and 15.10. (issue #317, PR #453, 2026-11-01) Box skill copy: none.
- Doctor compares running and installed tool versions from profile-defined read-only probes, checks optional minimum pins, and reports drift with restart or upgrade hints without changing tools. (issue #193, PR #447, 2026-11-01) Box skill copy: none.
- Route mechanical tmux wakes before waking the coordinator: start review and
  validation with head-bound deduplication, clean up terminal role windows and
  dequeue, and close out merged PRs. Keep judgement records for the coordinator,
  prioritize owner replies in its brief, and record the saturation lesson. (issue #434, PR #445, 2026-11-01) Box skill copy: coordinator deploy required.
- Bootstrap now validates and re-renders every role after installation, checks deployed content and target hashes, reruns doctor, and records failed checks. Explicit `--smoke` queues one docs-only pipeline test issue per install after checks pass; dry-run creates no issue. (issue #342, PR #443, 2026-11-01) Box skill copy: none.
- Added bootstrap offboarding with a dry-run and confirmation: pause active crew items, stop the runtime, remove unchanged install targets, optionally remove crew labels, and archive state with a removal record. Unlanded work blocks tmux cleanup; edited targets and leftover worktrees are preserved. Routine removal and access or protection changes remain explicit human steps. (issue #343, PR #436, 2026-11-01) Box skill copy: none.
- Add `crew host check` and `crew hosts` for per-project readiness and live host capabilities, prepared projects, reachability and load. Remote checks use a fixed SSH entrypoint contract for the runner in #208; `--fix` requests safe repairs and reports human steps, while missing logins or an unavailable runner keep hosts unready. (issue #205, PR #435, 2026-11-01) Box skill copy: none.
- Bootstrap can install Claude Code subagent and coordinator skill pointers with the existing Stop hook, and print a Codex launch pointer with per-process trust. Selected harnesses deploy one render, exclude every project target locally and record hashes; tracked or edited targets are refused, and tracked instruction files and home files are never written. Harness selection is forwarded to fetched release bundles; installed pointers and renders participate in the post-apply self-test. (issue #339, PR #433, 2026-11-01) Box skill copy: none.
- Bootstrap can fetch a release with `--version`, verify its SHA256SUMS before extraction, and run it from a separate version directory. Existing bundles and live installs remain protected, rc tags require `--pre`, and an org pack must pin the stable installed tag. The install record retains the verified bundle checksum. Fetching preserves post-apply self-tests and the opt-in smoke request. (issue #337, PR #428, 2026-11-01) Box skill copy: none.
- CI requires a newly added changelog fragment for PR content changes, using
  the PR merge base and a documented exempt path list. Cut output, fragment-only
  changes, verification artifacts and empty diffs pass without a new fragment;
  pushes to main skip the requirement. (issue #421, PR #426, 2026-11-01) Box skill copy: none.
- Merge-train land records include the literal land rule. The tmux synthesizer uses configurable train_min (default 2) and train_window (default 600 seconds), waits only when another PR is close to approval, and lands a single ready PR alone when none is close. (issue #321, PR #425, 2026-11-01) Box skill copy: coordinator render required.
- Publish releases when a CHANGELOG cut PR lands on main, after validating the real cut and verifying the owner's merge-ok at the merged PR head and release actor. Non-cut pushes skip cleanly; dispatch remains for dry runs and approved fallback publishing. Releases attach the bundle and checksums, then notify and close the linked release issue. (issue #387, PR #419, 2026-11-01) Box skill copy: none.
- Add owner-feedback intake with too-slow, too-costly and missed-bug classes,
  owner verification, source links, duplicate checks and normal coordinator
  triage in both runtime bindings. Cards feed future flavor suggestions and
  never apply a flavor or change merge permission. (issue #353, PR #418, 2026-11-01) Box skill copy: coordinator deploy required.
- Add offline flavor suggestions with six feedback signals, tighten precedence,
  metrics-gate and cooldown guards, scope attribution, custom knob steps and
  owner decision defaults. Add the suggestion issue template and coordinator
  triage duty; missing dated defect evidence blocks relaxation. (issue #354, PR #416, 2026-11-01) Box skill copy: deferred to coordinator mirror.
- Profile role personas: identity name, title and emoji keys render into both
  runtime templates, with Ash and a neutral Coordinator title by default.
  Signatures name the harness and model actually used, including fallback;
  marker formats and effort attribution are unchanged. Validator, renderer,
  tests and golden briefs are updated. (issue #187, PR #415, 2026-11-01) Box skill copy: deferred to #140.
- Synthesizer templates now maintain one gate-status review per change listing all unmet merge gates and who owes each item, update it across heads, clear it when satisfied, and wake the coordinator. Gate rules remain unchanged; rendered fixture checks cover the item list and reporting contract. (issue #185, PR #414, 2026-11-01) Box skill copy: coordinator deploy required.
- Added trusted repo-level handoff markers and ownership guards in Grok Bot templates and tmux, keeping non-owners read-only and preventing land while ownership is moving or unreadable. (issue #210, PR #410, 2026-11-01) Box skill copy: deferred to coordinator mirror.
- Metrics refresh adds flavor at the verdict head, escaped defects linked by whole-line issue-body references, and an engine-run proxy from commit trailers and attributed review/validation sections. Coordinator triage and the intake card gain the optional `Escaped from:` source line; unknown flavor and engine attribution stay blank. Offline tests cover the derivation and CSV/Markdown output. No merge gate changes. (issue #352, PR #403, 2026-11-01) Box skill copy: deferred to #140.
- `crew doctor` checks and repairs GitHub repository prerequisites: the runbook's
  crew labels, a confirmed current milestone, a linked Project with four Status
  options, and the reviewer invitation. `--dry-run` prints plans without local
  or remote writes. Namespace collisions stop label repairs, populated boards
  keep their Status options, and CI and branch protection remain human steps.
  Bootstrap passes the new doctor options explicitly for its prerequisite checks.
  Post-apply bootstrap and primary host checks also pass these options, and doctor retains the
  profile's tool drift checks alongside repository repairs. (issue #338, PR #402, 2026-11-01) Box skill copy: none.
- Added crew bootstrap to locate a stable bundle or explicit development clone, resolve the project, preflight with doctor, preview changes, apply on confirmation and record the install. Dry runs write no install, and existing targets must match their recorded hashes. The crew entry point and command modules are now available to every runtime. (issue #336, PR #401, 2026-11-01) Box skill copy: none.
- `crew doctor` checks whether a host can run the crew and prints one `ok`, `warn`, `fail` or `human` line per check with its fix hint: tools, `gh` logins, engines (the coordinator's, and a second one so the reviewer engine can differ), Codex hook trust and Claude Code folder trust for tmux, placeholder paths, the state dir layout, and the installed version against the latest release. It is read-only by default; `--fix` creates the missing state dir layout, and the steps only a person can take are listed at the end. Exit 1 on any `fail`. (issue #190, PR #364, 2026-11-01) Box skill copy: none.
- Runtime handoff (design): `docs/handoff.md` proposes how the owner pauses one crew runtime on a repo and resumes the same work in another, both ways (for example Grok Bot to a Claude Code or Codex session when orchestration quota runs short). One runtime instance owns a repo at a time, recorded by `pass=handoff` markers on a control item; every other runtime runs read-only. It covers drain, stop and takeover modes, a references-only handoff manifest with its template, an `acked` marker keyed by a handoff id so a retry is never a second handoff, reconcile against live state in dependency-closed sets, prompt stop of the outgoing runtime's wake sources, the return path, session rules as profile and flavor settings, and the build issues (#210 to #213 plus proposed follow-ups). The runtime contract gains C9 Ownership handoff, which the Grok Bot and tmux bindings declare unsupported today, compensated by the manual pause. Roadmap 21.1; part of #110. (issue #157, PR #363, 2026-11-01) Box skill copy: none.

### Changed

- Trim tmux coordinator and synthesizer briefs to restore headroom against the
  16 KiB per-role budget. Repeated owner communication, flavor suggestion and
  train checks refer to their existing reviewed rules; marker semantics and
  merge gates are unchanged. Refresh rendered fixtures and keep the existing
  budget unchanged; the 14 KiB trim target is not a new permanent limit. (issue #527, PR #532, 2026-11-01) Box skill copy: deferred to #140.
- Retain tmux builders after completion until their PR merges or closes, count only busy builders toward the cap, reclaim the oldest safely pushed idle builder when the physical band fills, and route later fix messages to a replacement automatically. (issue #493, PR #523, 2026-11-01) Box skill copy: deferred to #140.
- Reviewer validation runs acceptance checks, the repo guard, and tests covering changed files, citing green PR CI at head for the full suite. Verdicts list the local tests and CI link; red or missing CI remains the merge gate and cannot be replaced by a local full run. Both runtime templates and their render/parity fixtures follow this scope. (issue #503, PR #520, 2026-11-01) Box skill copy: deferred to #140.
- Reviewer bindings gain delta re-review of builder-resolved base updates with independent validation and a new head-pinned verdict, and record the reviewed base SHA. The router leaves clean merge-up events queued for synthesizer dispatch; missing reviewed bases trigger fresh review and validation through the coordinator. Approved merge-up events route to the synthesizer for patch identity rather than an automatic reviewer session. Coordinator dispatch never sends a change back solely for being behind and treats overlap as a risk signal, serializing only semantic dependencies, shared mutable external state or incompatible migrations. Final slice of #502. (issue #502, PR #519, 2026-11-01) Box skill copy: coordinator mirror required.
- Give the synthesizer sole landing decisions under the protocol and profile, limit coordinator inputs to recorded steers, and define urgency and project stop/resume markers. All runtime briefs carry the rules; the train gate reads durable landing-control reviews and refuses outstanding stops without weakening any merge gate. The Grok dispatcher records resumes on the same landing-control issue as their stops. (issue #496, PR #517, 2026-11-01) Box skill copy: pending coordinator mirror.
- The content helper compares verified and tool-updated patches without ignoring whitespace, paths, modes or binary changes. With a recorded review base, trains check each applied patch before inclusion and again at land, route differing patches to the builder and record content=identical with the full carried-from SHA. Both synthesizer bindings carry only a passing verdict with green live CI and recheck every other gate. Unchanged-head legacy train approvals remain eligible without claiming content portability. Second slice of #502. (issue #507, PR #516, 2026-11-01) Box skill copy: coordinator mirror required.
- Protocol §7 and its gate registry permit passing verdicts to carry across clean tool-performed base updates only with exact changed-line equality and green CI at the updated head. Conflicts or differing patches route through the builder and delta re-review; owner permission, holds, rereview and runtime gates remain live checks. First slice of #502; synthesizer and reviewer bindings follow separately. (issue #506, PR #512, 2026-11-01) Box skill copy: coordinator mirror required.
- Profile identity and engine validation and rendered role placeholders now read the engineering role registry. Existing profile behavior and rendered briefs are unchanged. (issue #320, PR #499, 2026-11-01) Box skill copy: none.
- Add the tmux lone_pr_land profile option: direct lands a single ready PR without a default-branch catch-up, records the gate waiver and checks merge-commit CI; a red default branch triggers a blocking coordinator fix issue. The default train policy and all other merge gates remain required. (issue #491, PR #498, 2026-11-01) Box skill copy: deferred to #140.
- The tmux runtime reads role bands, passes, names, caps, event consumers and spawn metadata from the engineering role registry, preserving existing behavior and leaving profile and renderer migration to the next slice. Bootstrap and offboarding test bundles include the role registry, and release bundle tests verify it is shipped with the CLI. (issue #319, PR #477, 2026-11-01) Box skill copy: none.
- Builders running a merge-up (a push whose only new commit merges the default branch) now run `check-repo.py` and only the `scripts/test-*.py` covering the conflicted files, and list them with the reason in the merge-up note; PR CI and the recheck pass cover the rest. Normal builds and fix rounds keep the full local run. (issue #464, PR #469, 2026-11-02) Box skill copy: coordinator deploy required.
- Make runtime evidence inline only in the change body and signed reviews, with
  copyable text recipes, GitHub media attachments and explicit size limits.
  Update the evidence merge gate, adapters and role templates; remove committed
  evidence from this tree and reject a root `evidence/` directory. No history
  rewrite; existing product evidence cleanup remains a separate change per repo.
  Keep the incoming builder pre-review checklist consistent with inline proof,
  and remove evidence files added on main before this change lands, including
  the subsequent repository-fixer, routing and merge-up recheck captures. (issue #143, PR #448, 2026-11-01) Box skill copy: coordinator mirror required.
- The new-repo runbook now leads with crew bootstrap preview and confirmed apply, verifies its recorded state before completing wiring, and retains manual profile, render and state setup as the fallback. It distinguishes the current core from pending automation and keeps routine creation, tmux startup and the smoke test explicit. (issue #344, PR #441, 2026-11-01) Box skill copy: none.
- Merge trains skip the duplicate local suite by default, with `--local` or a profile option to opt in and green train CI still required. A scoped, recorded owner mirror deferral can satisfy the tmux mirror gate for covered PRs that do not change live Grok Bot behaviour; merge records name its use and gate changes still require per-PR owner permission. (issue #430, PR #439, 2026-11-01) Box skill copy: deferred to #140.
- Builder pre-review check (16.1): protocol and worker role text now specify fresh-base synchronization, bounded lint/test fixes, private self-review, docs/changelog, typed evidence gathered during testing, and a head-bound `pass=precheck` marker with each step's result. Record the six drawbacks from #160; profile switching and review/merge enforcement remain separate. (issue #180, PR #411, 2026-11-01) Box skill copy: deferred to #140.
- Start tmux review on each opened or pushed head alongside CI, combine held CI failures with review findings in one builder handoff, and treat CI as information during review and validation. CI green at head remains a merge gate. Update the reviewed protocol and declare the Grok Bot review-start gap; live Grok Bot impact is none until mirrored (deferred to #140). (issue #380, PR #392, 2026-11-01) Box skill copy: deferred to #140.
- Grok Bot and tmux bindings declare supported harness adapters and session backends against runtime contract v2 (roadmap 15.6). Grok Bot uses platform-managed turns, with no terminal adapter/backend, and explicitly declares its missing handle-plus-start-time identity probe; tmux declares Claude Code, Codex and tmux support, including the uninstalled and unverified Codex coordinator guard. Existing waiting-cost and unlanded-work teardown gaps remain declared. Docs only; no rule, gate or code change. (issue #179, PR #390, 2026-11-01) Box skill copy: none.
- **Breaking:** Release approval is the owner's per-PR merge-ok at the CHANGELOG cut PR's head, checked by the publish job with the RELEASE_OWNER actor check; landing the cut triggers validation, tagging the merge commit, publishing and release-issue notice. Migration: approve each cut PR at its head instead of approving a deployment after dispatch; workflow implementation follows in #387. Dispatch remains for dry runs and owner-only manual fallback; no standing grant or auto-applied default publishes. The release design, release-approval registry row and workflow usage docs agree (#274). (issue #386, PR #389, 2026-11-01) Box skill copy: deferred to #140.
- The merge train is now a standing synthesizer skill in the rules (#321, part
  2a; part of #110). Protocol §7 gains the "tested with the default branch"
  gate and its gate-registry row: the head contains the current default
  branch, or the change is the next member of a green train on it. A new §7
  section gives the owner's land rules (train two or more ready changes, merge
  a lone or urgent one alone, wait briefly for one close to approval, never
  past the window), and each merge record names its rule in a `Land rule:`
  line. `docs/roles.md`, both synthesizer templates and the tmux runtime doc
  follow it; the `train_min` and `train_window` profile options come in part
  2b. (issue #321, PR #367, 2026-11-01) Box skill copy: deferred to #140.

### Fixed

- The tmux watcher refreshes heartbeats for live windows with live tool sessions or recent output; persistent helpers sharing the harness session do not mask a stale window. Mechanical routing starts full review after recheck escalation and allows validation after zero-step CI startup failures, reporting ci-infra to the coordinator while preserving the green-CI merge gate. (issue #494, PR #524, 2026-11-01) Box skill copy: none.
- Keep the synthesizer alive during an unfinished land, held land lock or open
  train, including merged-PR cleanup. Save pending lands in run state and restore
  them after kill or crash; name open trains and recovered inbox IDs on spawn.
  Unacknowledged retries ignore historical completions for the same PR.
  Bind detached land-lock holders to the owning pane's process identity, and
  clean up dead or orphaned holders without signalling a live owner or reused PID.
  Allow the expanded repo-guard suite ten minutes in CI. (issue #510, PR #515, 2026-11-01) Box skill copy: none.
- Mechanical routing consumes approved merge-up builder completions without starting a full review and routes merge-up events to one deduplicated recheck at the approval round. An open rereview steer keeps normal review, as do ordinary fix pushes. (issue #468, PR #504, 2026-11-01) Box skill copy: none.
- Keep the synthesizer window alive after a completion while another land request
  or undelivered inbox message remains. Serialize inbox appends with the route's
  check and reap so a pending request cannot disappear during cleanup. (issue #472, PR #500, 2026-11-01) Box skill copy: none.
- Merge train gates recognize hold-until dependencies only in coordinator posts,
  so quoted test strings in reviewer, builder and synthesizer posts no longer
  block landing. Missing or unreadable dependencies produce a clear blocked
  gate result instead of an unhandled lookup error. (issue #485, PR #489, 2026-11-01) Box skill copy: none.
- Merge trains preserve green CI across transient landing stops, select members by changed-file overlap, automatically route deferred members for merge-up after landing, and report members, lands, drops and stop causes in one line. HTTP retry codes require an explicit HTTP status prefix, so numbers in changed SHAs and hold references remain real stops. Pipelined successors retain their CI while a predecessor is transiently paused, and resume serial landing after it completes. (issue #460, PR #465, 2026-11-01) Box skill copy: deferred to #140.
- Automatically dequeue the freed role band after crew kill, persist sandbox env through the profile and window launches, and spell out reviewer section markers, rereview overrides and retained reviews for re-validation. Cover the existing builder scratch-file policy in brief tests. Keep the reviewer parity fixture aligned with the ownership guard and actual-run signature on main. (issue #429, PR #437, 2026-11-01) Box skill copy: coordinator deployment of rendered tmux briefs required.
- Skip scratch JSON in tmux run discovery, reset watcher status offsets when a
  window's run identity changes, retain builders' opened PRs for cleanup after
  squash landing, and require a prompt heading plus a final footer when detecting
  older trust and hooks-review dialogs so quoted output stays usable. (issue #369, PR #420, 2026-11-01) Box skill copy: none.
- `crew up` refuses before rendering when a profile can use Codex and a host
  `hooks.json` or inline `config.toml` hook lacks stored trust. The read-only
  check shares `crew doctor`'s host-hook check, tells the operator to review
  hooks once in plain Codex, and never writes config or recomputes trust hashes. (issue #370, PR #406, 2026-11-01) Box skill copy: none.
- The tmux builder, reviewer and synthesizer briefs and `AGENTS.md` now say: never download or install a binary from the internet, never bypass OS code-signing or quarantine, never use an alternate or mirror package registry; when a CI tool is missing or its registry fails, skip that one local check, say so in the PR evidence, and leave it to CI. The tmux briefs also say role scratch files go in the worktree's `.crew/`, and only `$CREW_ID.body.md` goes in `$CREW_STATE/runs/`, since a stray `runs/*.json` crashed `crew watch` (#369). (issue #400, PR #405, 2026-11-01) Box skill copy: none.
- `crew watch` skips stale wakes for runs without `start` while their run-record
  mtime is less than 60 seconds old, avoiding a false missing-run restart during
  spawn. Older unfinished spawns and started runs with missing windows still
  wake as missing and restartable. Regression tests cover all three cases. (issue #361, PR #393, 2026-11-01) Box skill copy: none.
- `crew spawn` and an in-place `crew restart` now pass `--add-dir <git common dir>` to every Codex role window, in every permission mode, next to the state dir. A linked worktree keeps its refs and objects there, so a host sandbox that allows writes only under the working directory and `--add-dir` paths no longer stops a Codex builder from creating a branch, committing or pushing. (issue #384, PR #385, 2026-11-01) Box skill copy: none.

### Security

- **Breaking:** Sensitive path classification now requires per-change owner merge-ok; no standing grant covers `crew:sensitive`. Profiles can extend mandatory path defaults. Migrate by classifying changes at triage/open/push and recording owner overrides; synthesizers and merge trains enforce the label. (issue #184, PR #413, 2026-11-01) Box skill copy: deferred to #140.

## [2.1.1] - 2026-11-01

### Added

- Session backend interface: `docs/runtimes/session-backends.md` defines what a
  runtime needs from the program hosting its role sessions (create in the
  background, attach read-only by default, doorbell, identity probe, state read,
  kill), each tied to the runtime contract capability it serves. The identity
  probe restates C5 as backend operations: a unique handle plus a start time,
  recorded at spawn, and a different handle or start time probes `missing`,
  never `alive`. tmux is filled in from `scripts/crew-tmux.py` and the tmux
  binding. The runtime contract links it from a new `## Session backend
  interface` section; the docs index, deliverables inventory and manifest, and
  required-docs list gain its row. Docs only; no rule, gate or code change.
  Roadmap 15.5. (issue #178, PR #360, 2026-11-01) Box skill copy: none.
- Host inventory and project affinity in the profile (20.2): optional
  `[hosts.<name>]` tables (primary, capabilities, `max_runs`, roles) and a
  `[placement]` table (affinity hosts and capability rules), documented in
  `docs/profile.md`. `scripts/crew-config.py validate` names hosts by overlay
  network name only (an IP literal, `@` or `:` fails) and rejects an unknown
  capability, zero or several primaries, unknown placement hosts, uncovered
  roles, unmeetable rule needs and `[hosts]` outside the tmux runtime; the
  secret-pattern scan covers every host value. Part of #110. (issue #204, PR #358, 2026-11-01) Box skill copy: none.

### Changed

- M14.3 tmux polish close-out (part of #110): the README Status marks M14.3
  done (#301, #303, #312, #270, #262), and `docs/specs/portable.md` §5 gains
  an M14.3 table with each slice `done` and its merged PR (status only, no
  requirement changes). The runtime contract's C5 `ambiguous` row in
  `docs/runtimes/README.md` no longer says a flat "never restart": it names
  the tmux binding's two kill-and-respawn exceptions, the dialog rule and one
  respawn of a stuck synthesizer after a failed nudge (#312), and links Q7 of
  `docs/runtimes/tmux.md`. (issue #368, PR #379, 2026-11-01) Box skill copy: none.
- Conflict-free index files, part 2 of #325 (part of #110). The inventory table in `docs/deliverables.md` is now generated from `scripts/deliverables.txt` (one row per manifest row; the manifest gained an optional Why column), and `python3 scripts/check-repo.py --fix` rewrites it. `scripts/deliverables.txt`, `scripts/required-docs.txt` and the `docs/README.md` rows are sorted, so a new entry lands at its own place instead of the end of the file, where every PR appended. The new `check-repo.py` check `index` (rules `index-stale`, `index-order`, `docs-index`) fails on a stale table, an unsorted file, a duplicate row, or a deliverable doc missing from the index. CONTRIBUTING.md and the worker brief rules in `docs/roles.md` gain the rule: no new shared append-hotspot files, one file per item or a generated aggregate. `test-check-repo.py` proves that two branches that each add a script, a doc and their index rows merge with no conflict, and that the same additions appended at the end of the files conflict. (issue #325, PR #362, 2026-11-01) Box skill copy: deferred to #140.
- The tmux coordinator brief now treats a window as `ambiguous` when `crew send` exits 4 (nudge not submitted) or an ack is still missing after the re-nudge, even if it probes `alive`, and still never restarts it, with one exception (#312, split from #308 ask 2; part of #110). The synthesizer window holds no worktree work, so the coordinator may kill and respawn it once per PR (`crew kill`, then `crew spawn synthesizer --pr <n>`), only while no land is in flight (`locks/merge.pid` absent), re-sends any other pending `land` because the kill drops its inbox, and asks the owner on a second miss. `docs/runtimes/tmux.md` names the exception in the Q7 failure policy. The brief-lint test gains a rule against restarting an `ambiguous` window outside this exception, and the rendered coordinator brief golden carries the new text. (issue #312, PR #359, 2026-11-01) Box skill copy: deferred to #140.
- Per-script docs replace the shared usage table in `scripts/README.md`, a merge
  hotspot that nearly every scripts PR edited (#325, part 1 of 2; part of #110).
  Each script's usage now lives in its module docstring, and `--help` prints it
  (`crew --help` and `crew <cmd> --help` too); `scripts/README.md` keeps a short
  guide and the long-form sections. A new `check-repo.py` check, `script-docs`
  (rule `script-doc`), fails when a script under `scripts/` has no module
  docstring, or a script you run or a `crew` command has no `Usage:` line.
  `test-check-repo.py` proves that two branches that each add a script with its
  docs merge with no conflict. Index files (deliverables, required docs, docs
  index) follow in part 2. (issue #325, PR #335, 2026-11-01) Box skill copy: none.

### Fixed

- tmux: a Codex coordinator now starts pre-trusted like a role window. `crew up`
  still launched it with `-c projects."<project-dir>".trust_level="trusted"`, the
  key form that did not stop codex-cli 0.164's `Trust this folder?` dialog, and
  with the project path as given rather than its real path (on macOS a temp path
  under `/var` is really under `/private/var`). It now gets the same per-process
  `projects` table as role windows (#293), from a new `codex_trust()` helper in
  `scripts/crew.d/_shared.py` that `harness()` also uses: the real project
  directory and, in a git repository, its repository root, where Codex applies a
  linked worktree's trust. `~/.codex/config.toml` is still never edited. The
  detection half of #262 shipped in #289: a window showing the dialog probes
  `ambiguous` and wakes the coordinator. Pre-resolving Codex's `Hooks need review`
  gate stays the owner's host-level step; a safe design for it is proposed in
  the PR, not built. `scripts/test-crew-up.py` tests both launches;
  `docs/runtimes/tmux.md` and `docs/runtimes/harness-adapters.md` show the new
  coordinator launch. (issue #262, PR #365, 2026-11-01) Box skill copy: none.
- Under the tmux runtime the reviewer now posts the protocol §6 intake ack (#303, part of #110). Before this, no
  reviewer posted it: `crew poll` has no `pr-opened` event and the reviewer brief had no ack duty, so the first
  thing on a PR was the final verdict. The rendered tmux `reviewer.md` brief has a new step 3: the round-1 `review`
  pass, after its live re-read and engine check, posts one COMMENT review `[<ReviewerBot>/ack] intake @ <sha7>` with
  a `pass=ack` marker (`round=n/a verdict=n/a`). It skips a draft and a head that already has one, so a respawned
  pass adds none, and the `validate` pass and later rounds never post it. The ack is narrative only: it wakes
  nobody, counts no round and is never an approval. `docs/runtimes/tmux.md` records the choice over a `pr-opened`
  poll event. `test-tmux-briefs.py` checks the rendered brief's ack step and `test-crew-poll.py` proves a
  `pass=ack` marker emits no event. (issue #303, PR #357, 2026-11-01) Box skill copy: deferred to #140.
- The tmux role briefs now say where a `gh` `--body-file` scratch file goes
  (#270, from the #139 final live run L1; part of #110). Builder, reviewer and
  synthesizer write it to `$CREW_STATE/runs/$CREW_ID.body.md`, which `crew kill`
  and `crew down` delete with the run's other `runs/<window>.*` files; before,
  roles wrote bodies to `/tmp` and to the parent of the state dir, where they
  outlived the run. The coordinator, whose window is never killed, writes
  `runs/coordinator.body.md` and deletes it after the post. The brief lint in
  `test-tmux-briefs.py` fails a brief that uses `--body-file` without that
  location or names a `/tmp` scratch file, and `test-crew-kill.py` pins that kill
  removes `runs/<window>.body.md`. `templates/backends/github.toml` is unchanged,
  and the Grok Bot runtime templates do not use it, so their rendered text is
  unchanged. (issue #270, PR #356, 2026-11-01) Box skill copy: deferred to #140.
- tmux turn-end guard counts open owner asks (restores documented
  behaviour): Q1 step 4 in `docs/runtimes/tmux.md` said `crew guard` blocks
  the coordinator's stop while an owner ask is open and no watcher is armed,
  but the guard counted only run records and a non-empty
  `wake/queue.jsonl`, so the coordinator could end its turn with an ask open
  and nothing armed to wake it at the deadline. Since #287 gave each open
  ask a record, `asks/<n>.json`, the guard now counts any record there as
  work in flight, an unreadable one included. The `crew guard` section of
  `docs/runtimes/tmux.md` and the guard's docstring say so; the Q1 step 2
  reason list and the `crew watch` usage already named the `ask:` wake.
  Test in `scripts/test-crew-guard.py`. Grok Bot runtime unchanged.
  Refs #110. (issue #301, PR #355, 2026-11-01) Box skill copy: none.

## [2.1.0] - 2026-11-01

### Added

- `crew train`, a merge train for the tmux runtime (part 1 of #321): approved
  PRs are tested together once, then land with no catch-up between them, in
  place of the merge queue GitHub does not offer private repos on GitHub Free.
  `crew train build <pr>...` merges each PR head onto the freshly fetched
  default branch as `crew/train-<n>` in a temporary clone that ignores local
  merge attributes, so a local `merge=union` cannot hide a conflict GitHub
  would hit (a PR that conflicts is dropped). It runs the local checks,
  pushes the branch with a draft train PR and waits for CI after a grace
  period, since `gh pr checks` fails until checks register.
  `crew train land <n> <pr>` lands the next member with
  `--match-head-commit`. The synthesizer re-runs the whole §7 check at that
  head right before each call, and `land` itself stops unless the default
  branch is still the train's tested state, the head is the tested head, a
  pass verdict and merge permission are at head, there is no
  `crew:escalated`, `crew:changes`, blocking `crew:hold`, open rereview or
  open hold-until, and GitHub reports the PR mergeable. It posts a merge
  record citing the train branch, SHA and CI run; a stop or the last member
  closes the train PR and deletes its branch, and `crew train close` ends a
  train early. `crew train bisect` is not built yet. The tmux synthesizer
  brief uses the train for two or more PRs waiting to land,
  `docs/runtimes/tmux.md` documents it, and `scripts/test-crew-train.py`
  covers it with a fake `gh` and a logging `git`.
  The protocol §7 and gate registry wording follow in part 2. Part of #110. (issue #321, PR #326, 2026-11-01) Box skill copy: deferred to #140.
- Crew flavors (design): `docs/flavors.md` proposes per-project rigor
  presets (`thorough`, `standard`, `fast`, `solo`) built from eleven knobs
  (review depth, validation, engine diversity, caps, evidence, merge
  permission, pre-review check, lighter lane, parallelism, engine routing,
  builder); the floor F1–F7 (CI never waived, no secrets, synthesizer-only
  land, audit on the record, owner hold, gate changes need the owner,
  `crew:sensitive` needs a per-change merge-ok) with validator rules; a
  `[flavor]` profile schema proposal; project / item / change resolution
  per #160 row 15 (flavor chosen at intake, item flavor recorded at
  triage, a stated reason to lower, no flavor = `thorough`, path-based
  class rule, uncertain → stricter); a mapping of every existing one-off
  knob; and the metrics feedback loop (inputs, thresholds T1–T3 and R1–R3,
  suggestion issue, owner accept path, never auto-applied). Maps onto
  build issues #195–#199, #102 and #109. `docs/flavors.md` is classified
  as a deliverable and pinned in `scripts/required-docs.txt`. Adds no
  rule, gate, cap, marker field or label. Roadmap 18.1. (issue #156, PR #307, 2026-10-31) Box skill copy: none.
- Multi-device design: `docs/runtimes/multi-device.md` designs role runs on
  several hosts of a private overlay network under one primary host, as a
  capability of the tmux runtime (not a new binding), carrying out the #160
  row 6 decision. It covers overlay assumptions, a host inventory profile
  extension (`[hosts.<name>]` with capabilities, `max_runs`, roles;
  `[placement]` affinity and capability rules; proposal for #204), the
  `place()` function in `crew spawn` with a recorded `--host --reason`
  override, `crew host check` / `prepare` and `crew hosts`, the hardened
  remote call and per-account runner, C1–C8 across hosts with gap lines,
  failure and partition handling (the `unreachable` class is never
  restarted or re-placed), the security model, alternatives per decision,
  and a map onto build issues #204–#209 plus proposed 20.8–20.12. Docs
  only; no rule, gate, cap, marker field or label changes. Roadmap 20.1. (issue #158, PR #306, 2026-10-31) Box skill copy: none.
- Bootstrap design: `docs/bootstrap.md` answers the ten #144 questions,
  with the alternatives considered for each. `crew bootstrap` runs from an
  extracted, checksum-verified release bundle at a tag. It resolves the
  config layers, proposing a project file when there is none (#191), and
  runs `crew doctor` (21 preflight checks, each with a fix hint, failing
  closed; includes the nested-sandbox quirk through `CREW_SANDBOX_ENV`).
  It plans first (`--dry-run`), applies idempotent `crew:*`-only repo
  fixers, renders once into the state dir and installs untracked pointers
  per harness. It records `VERSION` and `install.json`, then self-tests.
  The doc also has a per-runtime install-target table (Claude Code, Codex,
  Grok Bot, tmux) with contract gaps, upgrade with role reload (#192),
  uninstall as automated offboarding, secrets by mechanism, and a mapping
  onto #165, #166 and #190–#194 plus proposed build issues. Indexed in
  `docs/README.md`, classified as an install doc in
  `docs/deliverables.md` and `scripts/deliverables.txt`, and listed in
  `scripts/required-docs.txt`. No rule or gate changes. Roadmap 17.1. (issue #144, PR #304, 2026-10-31) Box skill copy: none.
- Inline-only evidence design (#143, part 1 of 2, owner decision pending): a
  design section in `docs/verification.md` that answers the five open
  questions and lists the alternatives considered for each. It recommends:
  media only as GitHub user-attachments URLs, attached with
  `gh pr create --attach` (`gh` 2.99.0 or later), and for posts after the
  change opens a text recipe plus the validator's own reproduction; text
  evidence as a copyable repro pair (an `sh` block, then a `text` block with
  the exit code, stdout and stderr); size budgets under GitHub's
  65,536-character limit; deleting `evidence/` from each tree going forward,
  with no history rewrite; and a new Required evidence gate registry row. No
  live rule, gate, template or marker changes: protocol §3 and §7, the
  registry and the templates change in the build PR. (issue #143, PR #302, 2026-10-31) Box skill copy: none.
- Knowledge routing and correct-not-add for always-loaded files:
  `docs/self-improve.md` gains a `## Knowledge routing` table (owner
  profile, product-repo `AGENTS.md` via `repo:`, org pack, eng-crew
  harness via `crew:`, or lesson only; most specific owner first; profile
  and org-pack cards close as routed) and an `## Always-loaded files`
  section (any role may correct wrong text; a learning adds text only
  through an accepted intake card and its PR; prune before adding).
  `docs/roles.md` gets a matching **Knowledge routing** paragraph. No gate,
  cap, marker field or label changes; no size budget (M17, #194).
  Decision: #160 row 18. Roadmap 16.9. (issue #188, PR #297, 2026-10-31) Box skill copy: deferred to #140.
- CHANGELOG fragments, part 1 (tooling and `CONTRIBUTING.md`): a PR records
  its change as `changes/unreleased/<issue>-<slug>.md` (front matter `type`,
  `issue`, `pr`, `date`, `box-skill`, then one paragraph) instead of editing
  `CHANGELOG.md`. `scripts/changelog-cut.py` turns each fragment into an entry
  under its Keep a Changelog heading in the cut section, together with any
  entries already under `[Unreleased]`, then deletes the fragments; it refuses
  a malformed fragment or `pr: TBD`. `scripts/release-check.py` refuses a
  release while a fragment is left, and `scripts/check-repo.py --only
  fragments` checks every fragment's format. `changes/**` is classified
  internal. The process text for roles, release and the briefs follows in a
  part 2 PR. (issue #264, PR #292, 2026-10-31) Box skill copy: none.
- Coordinator owner-communication rules: a new `## Owner communication
  (coordinator)` section in `docs/roles.md` (outcomes first, a final message
  that stands alone with every outcome, decision and full URL, escalations as
  evidence → consequence → options → recommendation, plain words in chat while
  markers keep exact terms, reach the owner only for review-ready work,
  findings, gate decisions, blockers, destructive or security-sensitive actions
  and credentials, full URLs copied from the record, and one fixed neutral
  reply for a true no-op), rendered into the tmux coordinator brief
  (`templates/runtimes/tmux/coordinator.md`, golden refreshed). Credits
  firstmate's etiquette as prior art, persona removed (decision #160 row 14).
  Roadmap 16.7. (issue #186, PR #284, 2026-10-31) Box skill copy: deferred to #140.
- Spec slice for M15–M21: `docs/specs/portable.md` goes to v0.3 with §5
  slice tables for M15–M21 (every issue from the #160 review with its
  dependencies, the moved design and backlog
  issues #150, #143, #144, #165, #166, #156, #102, #109, #170, #158
  and #157, and 15.7 #264), each milestone linked to its #160 row comments;
  the missing 14.1j (#265), 14.1k (#266) and R1.9–R1.11 (#275–#277) rows; §2
  P10 (per-PR changelog fragments under `changes/unreleased/`, assembled at
  cut); and four §6 decisions (#160 option A, the 14.11 M14 freeze
  exception, changelog at cut time, M15+ hold lifted). No rule changes. Spec
  PR: the owner approves the merge per PR. Roadmap 15.0. (issue #173, PR #283, 2026-10-31) Box skill copy: none.
- Harness adapter interface: `docs/runtimes/harness-adapters.md` defines
  the fields a runtime needs per agent CLI (launch line with the brief by
  pointer, trust and first-run dialogs, turn-end and wake recipe, idle
  detection, expected foreground process), each tied to the runtime
  contract capability it serves (C1, C3 or C5), and fills them in for
  Claude Code and Codex from what the tmux binding does today. The runtime
  contract links it from a new `## Harness adapter interface` section; the
  docs index, deliverables inventory and manifest, and required-docs list
  gain its row. Docs only; no rule, gate or code change. Roadmap 15.4.
  (issue #177, PR #294, 2026-10-31) Box skill copy: none.

### Fixed

- tmux nudges never type into a prompt (safety fix): `crew watch` typed its
  `wake: watcher` line plus `Enter` into an idle window 0, and `crew send`
  typed its `inbox: <msg-id>` nudge into a role window, even when the pane
  showed a blocking prompt. Claude Code's permission prompt and Codex's
  approval prompt preselect yes, so that `Enter` could approve a command
  nobody reviewed. Both now check `dialog()` (the prompt and fatal-error
  screens of #289) first and press no key when it matches. `crew send` still
  appends the inbox line, prints `dialog: a prompt is on its screen; nothing
  typed` with `treat <window> as ambiguous` and exits 4; it also re-checks
  before each `Enter` retry. The watcher queues a `dialog` wake for window 0
  (liveness `ambiguous`, action `escalate`) instead of the wake line. A
  normal screen still gets the nudge. (issue #315, PR #331, 2026-11-01) Box skill copy: none.
- tmux stuck detection (patch): a role window sitting on a Codex command
  approval prompt, the Codex `Trust this folder?` screen, a Claude Code
  permission prompt (`Do you want to proceed?`, `Do you want to make this
  edit to …?`) or idle after a fatal API error (`"type":"error"` with a 4xx
  or 5xx status) probed `alive`, so `crew status` showed it healthy and
  `crew watch` sent no `dialog` wake. `dialog()` in
  `scripts/crew.d/_shared.py` now matches each prompt by its heading on a
  line of its own plus its footer as the last screen line, and the error by
  the harness's own error line (`■` in Codex, `⎿  API Error:` in Claude
  Code), so text quoted in a prompt echo or diff does not match. Such a
  window probes `ambiguous` and the watcher wakes the coordinator with
  `dialog` on its next scan. `scripts/fixtures/dialog/` holds captured
  screens of each case plus working screens that quote the same text;
  `scripts/test-crew-status.py` and `scripts/test-crew-watch.py` test them.
  `docs/runtimes/tmux.md`, `docs/runtimes/harness-adapters.md` and
  `scripts/README.md` describe it. Part of #110; refs #262. (issue #289, PR #313, 2026-10-31) Box skill copy: none.
- `crew send` nudges no longer pile up unsent in a Codex composer: an
  `Enter` sent right behind the typed `inbox: <msg-id>` landed in Codex's
  paste burst and added a newline, so each nudge stacked under the last and
  none was submitted. The adapter's `send_keys` now waits 0.3 s before
  `Enter` (the watcher's `wake: watcher` line too), and `crew send` follows
  firstmate's verified-submit pattern: it reads the composer at the cursor,
  clears earlier `inbox:` lines with `C-u` when they are all it holds (other
  text is never cleared), types the nudge once, retries `Enter` up to 3
  times while the nudge is still in the composer, and exits 4 with
  `crew: nudge not submitted: ...; treat <window> as ambiguous` if it never
  submits. `scripts/test-crew-send.py` adds the composer check on captured
  Codex and Claude Code screens and a fake-composer test; `docs/runtimes/tmux.md`
  and `scripts/README.md` describe it. (issue #308, PR #310, 2026-10-31) Box skill copy: none.
- `crew spawn` and `crew restart` rejected Claude Code windows on a native
  install (patch): the installer's `claude` is a symlink, and tmux reports
  `#{pane_current_command}` as the target file's name, the version (for
  example `2.1.314`), so the exact `claude` match failed each `claude-code`
  launch there, reviewers and `trivial`-tier builders included. The start check
  (`wait_harness`) now takes the evidence liveness takes: `claude` or
  `codex` among the pane tty's foreground process names, or a pane command
  equal to that name or to the name of the file it resolves to on `PATH`.
  A version-shaped name alone still fails, and a dead pane still fails at
  once. `scripts/test-crew-spawn.py` and `scripts/test-crew-restart.py` add
  version-string pane tests; `docs/runtimes/tmux.md`, the expected
  foreground process rows in `docs/runtimes/harness-adapters.md` and
  `scripts/README.md` describe the check. Part of #110. (issue #286, PR #309, 2026-10-31) Box skill copy: none.
- tmux watcher owner-ask deadline (restores documented behaviour): the C8
  row and Q1 in `docs/runtimes/tmux.md` said the watcher wakes the
  coordinator at an owner ask's §6 auto-apply time, but `crew watch` had no
  such timer, and its backstop backs off to 16 × `--backstop` while no run
  is recorded, so a deadline could pass hours before the coordinator woke.
  The coordinator brief now writes each open ask's deadline to
  `<state-dir>/<owner>__<repo>/asks/<n>.json` (`{"deadline": ...}`, ISO
  8601 with its UTC offset) and deletes it when the ask closes. `crew watch`
  queues one `ask: <n> deadline <time>` wake per deadline on the first scan
  at or after it, cuts its scan sleep short so that scan lands on the
  deadline, whatever the backstop, and wakes at once on an unreadable
  deadline. The C8 row, Q1 and the `crew watch` source list in
  `docs/runtimes/tmux.md` name the `ask:` wake. Tests in
  `scripts/test-crew-watch.py` use an injected clock; golden
  `scripts/fixtures/render/tmux/runtime/coordinator.md` updated; Grok Bot
  renders unchanged. Refs #110. (issue #287, PR #300, 2026-10-31) Box skill copy: deferred to #140.
- `crew watch` flakes (patch): a `--source` was cut off after `--interval`
  seconds, so at the tests' `--interval 0.05` even `printf` could time out
  on a loaded runner, and a slow `crew poll --once` risked the same. The
  source timeout is now `--source-timeout` (new flag), default `--interval`
  with a 5 s floor. A SIGTERM, SIGINT or SIGHUP that landed while the
  watcher was starting a `tmux`, `ps` or `--source` child left that child
  running after the watcher exited (it then wrote into the test's temp dir,
  failing cleanup with `Directory not empty`); a signal during a scan is
  now held until the scan's children exit, and the watcher exits at once
  between scans or on a second signal. `scripts/test-crew-watch.py` adds a
  slow-source floor test, a held-signal test and a second-signal test, and
  gives the timed-out source `--source-timeout 1`. `docs/runtimes/tmux.md`
  and `scripts/README.md` describe both. (issue #272, refs #110, PR #305,
  2026-10-31) Box skill copy: none.

### Changed

- Upgrade note (2.1): tmux role windows now launch with permission prompts
  off by default (`runtime.options.permission_mode = "bypass"`, following
  firstmate), so agents run any command in their worktree without asking;
  set `"auto"` or `"safe"` in `crew.toml` to opt out. Each project needs a
  one-time Claude Code folder trust on its first `crew up`: accept the trust
  dialog once in the coordinator's window, which also covers the role
  worktrees. Codex windows trust the worktree and its repo root
  automatically. Details:
  [docs/runtimes/tmux.md](https://github.com/mw-ding/eng-crew/blob/main/docs/runtimes/tmux.md#crew-spawn)
  and the runbook's
  [tmux runtime](https://github.com/mw-ding/eng-crew/blob/main/docs/runbook-new-repo.md#tmux-runtime)
  section. (issue #328, PR #329, 2026-11-01) Box skill copy: none.
- tmux role-window launch policy (behaviour change: role windows no longer
  stop on permission or approval prompts): new profile key
  `runtime.options.permission_mode`, `bypass` | `auto` | `safe`, default
  `bypass` (firstmate's default, owner decision on #110). `harness()` in
  `scripts/crew.d/_shared.py` gives Claude Code `--add-dir
  <state-dir>/<owner>__<repo>` in every mode, then `--permission-mode
  bypassPermissions --settings '{"skipDangerousModePermissionPrompt":true}'`
  (per process; the user's settings are never edited), `auto`, or
  `acceptEdits` (`safe`, the old launch). Codex gets
  `--dangerously-bypass-approvals-and-sandbox`, or `workspace-write` with
  network on (plus `-a on-request` for `auto`), always with `--add-dir
  <state>`. Codex pre-trust is now one `-c projects={...}` table for the
  worktree and its repo root: the old `projects."<dir>".trust_level` form did
  not stop the trust dialog on codex-cli 0.164. `crew spawn` and `crew
  restart` pass the mode, `crew-config.py` validates it, and
  `profiles/tmux.toml`, `docs/profile.md`, `docs/runtimes/tmux.md`,
  `docs/runtimes/harness-adapters.md` and the runbook document it, with the
  `auto` / `safe` residual gap. Tests: argv per mode and engine and an unknown
  mode refused (`test-crew-spawn.py`), the validator (`test-crew-config.py`)
  and the restart launch (`test-crew-restart.py`). The coordinator's `crew up`
  launch is unchanged. (issue #293, PR #311, 2026-10-31) Box skill copy: none.
- Runtime contract C6 provable landing: `docs/runtimes/README.md` C6 now
  says teardown never removes a worktree unless its work has provably
  landed (no uncommitted or untracked paths, and every commit on a freshly
  fetched default branch, run branch or change head; a check that cannot
  run counts as not landed) or the owner discarded it, with the reason and
  the unlanded list recorded on the change or tracker item first.
  `docs/runtimes/tmux.md` cites `crew kill`'s existing unlanded-work check
  and `--discard --reason` (#172) as its C6 answer.
  `docs/runtimes/grok-bot.md` declares a partial C6 gap: cleanup runs only
  after a pass pushes or on `pr-merged` / `pr-closed`, with no landed check
  before the delete. No code or routine change. Roadmap 15.3,
  decision #160 row 3. (issue #176, PR #295, 2026-10-31) Box skill copy: none.
- Resolver as a function (structural, no behaviour change):
  `scripts/crew-config.py` exposes `resolve_profile(project,
  org_profile=None)`, which returns the merged profile, per-key provenance,
  the problems and the layer names. The `resolve` CLI prints from it, and
  `scripts/crew-render.py` calls it directly instead of running
  `resolve_main` and parsing its printed `key = value  # layer` lines. The
  `resolve` output (stdout, stderr, exit code) and the render goldens are
  unchanged. (issue #165, PR #290, 2026-10-31) Box skill copy: none.
- Runtime contract C1 (`docs/runtimes/README.md`) says what waiting may
  cost: waiting costs no model turns, only an actionable event or a due
  backstop starts a turn, and a backstop's interval backs off while nothing
  is in flight. Token-free pollers such as `crew poll` are not model-turn
  polling; a runtime that cannot wait token-free may poll with model turns
  only with backoff, declared as a C1 gap. Both binding tables re-checked:
  Grok Bot declares its fixed hourly sweeper and no-op dispatcher wakes,
  tmux its default watcher nudge (a possible second, empty turn per wake
  for a Claude Code coordinator). Roadmap 15.1, decision #160 row 4. (issue #174, PR #285, 2026-10-31) Box skill copy: none.
- Runtime contract C5 run identity: `docs/runtimes/README.md` C5 now says a
  run is identified by a unique handle plus its start time, recorded at
  spawn, and a probe that finds a different handle or start time classifies
  the run as `missing`, never `alive`. `docs/runtimes/tmux.md` makes its
  decisions table, C5 contract row and Q7 classes consistent with the
  identity probe `crew` already runs (pane id, pane pid and that process's
  start time), so a same-named replacement window never probes `alive`. No
  probe code change. Roadmap 15.2, decision #160 row 5.
  (issue #175, PR #282, 2026-10-31) Box skill copy: none.

## [2.0.1] - 2026-10-31

### Added

- R1 close-out (the #259 closing slice for R1): a README `## Install`
  section that installs from a GitHub Release (`gh release download`,
  `shasum -a 256 -c SHA256SUMS`, extract, record `VERSION`, check
  `crew-config.py validate` and `crew --help` run, then the runbook), with a
  one-line caveat that the `v2.0.0` bundle fails the tool check until #275
  ships. Status sync, status-only: the README Status marks R1 done with
  `v2.0.0` released through `release.yml`, and "What you get" no longer says
  `v2.0.0` is unpublished; the tmux runbook prerequisites accept an extracted
  bundle as `<eng-crew>`; `docs/release.md` records the `v2.0.0` cut and
  adds bundle extraction to the "Before bootstrap" update row;
  `docs/deliverables.md` says the bundle build and release workflow are
  implemented; `docs/specs/portable.md` §5 marks R1.4 (#219) `done`. No
  rule or gate wording changes. Roadmap R1.10. (issue #276, PR #278,
  2026-10-31) Box skill copy: none.

### Fixed

- Release bundle install CLI (patch: restores documented behaviour): the
  v2.0.0 bundle left out `scripts/check-repo.py`, which `crew-config.py`
  imports for its secret-scan patterns, so `crew-config.py`,
  `crew-render.py` and `crew` failed with `FileNotFoundError` from an
  extracted bundle. `scripts/check-repo.py` is now a deliverable (install
  CLI, runtime `all`) in `scripts/deliverables.txt` and the
  `docs/deliverables.md` inventory. `scripts/test-release-bundle.py` now
  extracts the bundle built from the current repo and requires
  `scripts/crew --help`,
  `scripts/crew-config.py validate profiles/default.toml` and
  `scripts/crew-render.py --project profiles/default.toml --out <tmp>` to
  exit 0, so every release validate run gates this. Roadmap R1.9.
  (issue #275, refs #110, PR #280, 2026-10-31) Box skill copy: none.

## [2.0.0] - 2026-10-31

### Added

- tmux runtime runbook: a `## tmux runtime` section in
  `docs/runbook-new-repo.md` (prerequisites including Codex hook trust on
  the host, target-repo setup with placeholder-path refusal, the one-time
  trust dialog, the `crew` operator commands with `--project
  "$CREW_PROJECT"`, the wake path, close-out, owner duties with a hold
  default for merge-ok, troubleshooting from the dry and live runs, and the
  final live sandbox run's timeline and pass bar a–g, all PASS), and the
  lesson `docs/lessons/2026-10-30-tmux-dry-runs.md` mapping the findings of
  two dry runs and three live runs to their fix PRs or backlog issues (#269,
  #270). Roadmap 14.10. (issue #139, PR #249, 2026-10-30) Box skill copy:
  none.
- tmux brief lint: `scripts/test-tmux-briefs.py` renders the tmux briefs
  from `profiles/tmux.toml` and fails on the prose bugs from the dry runs
  and the #139 live run: typing or pressing keys (or `tmux send-keys`) in a
  role window, a `--project` other than `"$CREW_PROJECT"` (or its escaped
  or owner-facing `PATH` forms), a merge-ok auto-applied, defaulted or recorded without the owner's words under
  `merge_grant = "none"`, a raw `flock` instead of `crew land-lock`, and a
  `gh` command without `-R` (except `gh api`) when the brief lacks the
  blanket `-R` rule. Prose that forbids the action passes. Each rule has a
  bad and a forbidding fixture, and the real rendered briefs must pass.
  Wired into the CI `repo-guard` job.
  Roadmap 14.1i. (issue #257, refs #139, PR #261, 2026-10-30) Box skill
  copy: none.
- Spec sync, part 1 of 2 (post-M14): `docs/specs/portable.md` goes to v0.2
  with a Status column (`open`, `done`, `dropped`, from live issue state) on
  every §5 slice table, the missing 14.11 (#172) row, new M14.1 and R1 slice
  tables, four new §6 decisions (standing grant for all milestones and
  status-only spec edits, inline-only evidence, release owner and gate, spec
  bookends), and Q8 moved to "revisit with M15". `docs/specs/framework.md`
  R4 now describes the post-#128 render-and-drift-check mirror. New
  `check-repo.py --only spec-status` guard fails a §5 slice row without a
  valid Status cell, with tests. Spec PR: the owner approves the merge per
  PR. (issue #259, PR #263, 2026-10-30) Box skill copy: none.
- Release bundle attached: in `.github/workflows/release.yml` the `validate`
  job runs `scripts/release-bundle.py "$VERSION"` at the validated SHA,
  checks `SHA256SUMS` with `sha256sum -c`, and uploads
  `eng-crew-<version>.tar.gz` and `SHA256SUMS` as the `release-bundle`
  artifact, replacing the `TODO(#236)` placeholder; the pull request dry run
  builds it for the simulated version. The `publish` job downloads the
  artifact and attaches both files to `gh release create --verify-tag`. No
  other workflow behaviour changes. `crew:sensitive`: the owner approves the
  merge per PR. Roadmap R1.7. (issue #246, PR #248, 2026-10-30) Box skill
  copy: none.
- Release bundle build: `scripts/release-bundle.py <version>` builds
  `eng-crew-<version>.tar.gz` (the paths `scripts/deliverables.txt` classifies
  `deliverable`, at their repo paths under one top-level
  `eng-crew-<version>/` folder, plus `VERSION`) and `SHA256SUMS`,
  deterministically (sorted entries, fixed mtime from `SOURCE_DATE_EPOCH` or
  the commit time, uid/gid 0). Relative links from bundled Markdown to
  internal paths are rewritten to the file at the `v<version>` tag (`raw/`
  URLs for images, so they render inline), then an
  offline link check runs on the bundle. Tests in
  `scripts/test-release-bundle.py`, run in CI. Attaching the bundle in
  `release.yml` is a separate `crew:sensitive` PR. Roadmap R1.6. (issue #236,
  PR #245, 2026-10-30) Box skill copy: none.
- Release workflow: `.github/workflows/release.yml`, dispatched on `main`
  with `version` and `dry_run` (default `true`). A read-only `validate` job
  runs the repo guard, every `scripts/test-*.py` (render parity included),
  markdownlint, the link check and the new `scripts/release-check.py`
  (`[Unreleased]` empty, top section `[<version>]`, tag new and greater than
  the latest), and uploads the notes; pull requests touching the release
  files run it as a dry run on a simulated cut. The `publish` job, behind
  the `release` environment and only with `dry_run=false`, creates the
  annotated tag `v<version>` and the GitHub Release; it never commits, and
  refuses unless the actor is the `RELEASE_OWNER` repository variable (a
  stopgap: GitHub Free private repos have no required reviewers). Bundle
  step left as a placeholder for #236. New release gate row in the
  `docs/protocol.md` gate registry (guards publishing, not merging; no
  fail-open, only defer or cancel). Tests in `scripts/test-release-check.py`,
  run in CI. Roadmap R1.3. (issue #218, PR #243, 2026-10-30) Box skill
  copy: deferred to #140.
- Deliverables manifest: `scripts/deliverables.txt` is the machine-readable
  copy of the `docs/deliverables.md` inventory (#229), one
  `glob<TAB>class<TAB>runtime` row per line. A new `check-repo.py` check,
  `deliverables`, fails on a tracked path that matches no row
  (`unclassified`) or more than one row (`double-classified`).
  `scripts/changelog-cut.py`, not in the #229 table, is classified internal.
  Tests in `scripts/test-check-repo.py`. Roadmap R1.5. (issue #235, PR #242,
  2026-10-30) Box skill copy: none.
- tmux crew watcher hardening, from the #139 dry run (B1, F10, F11, F12):
  `scripts/crew watch` runs each `--source` with a timeout of one scan
  interval (killed and queued as a `source-timeout` wake), so a looping
  source no longer wedges it; sources are documented as one-shot
  (`crew poll --once`). It also wakes when `wake/queue.jsonl` grows (byte
  offset in `watch-state.json`), so a `crew poll` loop in its own window
  works, and ignores the stdout of a source that queued its own records, so
  poll events are queued once. New `crew drain` prints and empties the
  queue under `wake/queue.lock`, which every append takes, so no concurrent
  record is lost. SIGTERM / SIGINT remove `watcher.pid` and save
  `watch-state.json`, which is now saved after every scan. Tests in
  `scripts/test-crew.py`. Roadmap 14.1a. (issue #230, refs #139, PR #241,
  2026-10-30) Box skill copy: none.
- Deliverables and versioned release (design, R1.1): `docs/deliverables.md`
  classifies every path as deliverable or internal (runtime, source or
  generated), packages one bundle per release rendered at install, and sets
  SemVer rules (what is breaking: gates, marker fields, state tags, profile
  keys, pack and interface operations, CLI flags and output, placeholders),
  the compatibility promise to packs and installs, and the first versions
  (`v1.0.0` retro-tag of M12, `v2.0.0` after M14). `docs/release.md`
  designs the release: manual dispatch, the CHANGELOG cut as a normal PR,
  validate and build, owner approval through a protected environment, tag
  and GitHub Release, a draft release-gate row (fail-open: none), rollback,
  the pull-only update path and the session-tooling helpers to upstream.
  Spec P9 and layout rows in `docs/specs/portable.md`; README "What you
  get" points at it. (issue #145, PR #229, 2026-10-30) Box skill copy: none.
- CHANGELOG cut: `scripts/changelog-cut.py <version>` turns `## [Unreleased]`
  into `## [x.y.z] - YYYY-MM-DD` (default today in UTC, `--date` to pin it,
  `--dry-run` to print only), keeps its subsections and entries byte for
  byte and leaves an empty `## [Unreleased]` above. It refuses an empty
  Unreleased, a non-SemVer version, an existing version and a version not
  greater than the latest, leaving the file untouched. Tests in
  `scripts/test-changelog-cut.py`, run in CI. Roadmap R1.2. (issue #217,
  PR #228, 2026-10-30) Box skill copy: none.
- tmux crew watcher: `scripts/crew watch` is the zero-token watcher
  (`docs/runtimes/tmux.md` Q1). It writes `wake/watcher.pid`, blocks on
  new role status lines, runs that probe `dead` / `missing` or stay silent
  past `--stale` (default 15 min), and `--source` event commands (the
  `crew poll` hook), appends each wake to `wake/queue.jsonl`, and exits
  with one reason line so the coordinator is re-invoked. A stale wake says
  `restart` only for a first `dead` / `missing` run and `escalate`
  otherwise. It also types `wake: watcher` into an idle coordinator
  (`--no-nudge` to turn off), and a backstop wake's interval doubles while
  nothing is in flight. `crew restart` no longer loses unlanded work
  (#172): a dead or missing run with unlanded work is relaunched in its own
  worktree, brief and claim instead of being killed and respawned fresh.
  Fake-clock and fake-tmux tests in `scripts/test-crew.py`. Part 2 of 2. (issue #135, PR #222, 2026-10-30)
  Box skill copy: none.
- Render-vs-live drift mode: `scripts/check-skill-drift.py --project
  <crew.toml>` renders the profile with `crew-render.py` and compares every
  rendered file with the same path under the live copy dir (`--live-dir`,
  `ECREW_LIVE_DIR`, else the new optional profile key `paths.live_dir`),
  per section with the existing OK / WORDING / DRIFT classification; a
  rendered file missing from the live copy, an absent or placeholder live
  dir, or a failed render is exit 2, and a live file the render does not
  produce is `EXTRA`. Tests on the render fixtures (match, wording, drift,
  missing, extra, path sources) in `scripts/test-check-skill-drift.py`.
  PR (a) of two; the mirror gate change follows. (issue #128, PR #226,
  2026-10-30) Box skill copy: none.
- tmux role briefs: `templates/runtimes/tmux/{coordinator,builder,reviewer,synthesizer}.md`
  tell each window how to work in this runtime: the coordinator drains the
  wake queue, routes by `crew spawn` / `crew send` / `crew kill`, keeps the
  watcher armed and never pastes payloads; the builder keeps its window for
  the issue, takes fix rounds from its inbox with `ack: <id>` and writes
  `done:` / `blocked:` to `$CREW_STATUS`; the reviewer-validator runs one
  pass in a fresh session, writes its verdict file and `done:`, then exits;
  the synthesizer lands serially under `flock`. They render from the new
  example profile `profiles/tmux.toml`; golden files in
  `scripts/fixtures/render/tmux/`. `crew up --inputs` now defaults to
  `templates/`, and `crew up` / `crew spawn` fall back to
  `render/runtime/<role>.md` when no core brief is rendered. (issue #137,
  PR #225, 2026-10-30) Box skill copy: deferred to #140.
- tmux crew liveness: `crew spawn` records the run identity (pane id, pane
  pid and that process's start time) and its spawn arguments in
  `runs/<window>.json`; `scripts/crew status` prints window, role, item,
  head, heartbeat age, liveness and last status line per run, where
  liveness is the C5 probe from tmux and `ps` (`missing` on any identity
  mismatch, so a new window with the same name and harness is never
  `alive`; `dead` on a dead pane; `alive` when `claude` / `codex` is the
  pane command or a foreground process; otherwise `ambiguous`, `node`
  included); `scripts/crew restart <window>` restarts only a `dead` or
  `missing` run, only once, never a finished one; `crew up` on a dead
  session rebuilds `ash` from disk and lists the recorded runs without
  respawning them. Tests with a fake `tmux` and a fake `ps` in
  `scripts/test-crew.py`; usage in `docs/runtimes/tmux.md`. Part 1 of 2;
  the watcher follows. (issue #135, PR #220, 2026-10-30) Box skill copy:
  none.
- tmux crew serial land and caps: `scripts/crew land-lock acquire|release`
  takes a fail-fast `flock` on `locks/merge.lock`, held by a detached
  holder until release, so a second land fails fast and `crew down`
  refuses meanwhile. `crew spawn` beyond the band cap
  (`runtime.options.builders`, default 5; `runtime.options.reviewers`,
  default 2) creates no window and appends the request to
  `spawn-queue.jsonl`, printing `queued:`; `crew dequeue` spawns the oldest
  queued request whose band has a free slot. Tests in
  `scripts/test-crew.py`; usage in `docs/runtimes/tmux.md`. (issue #136,
  PR #215, 2026-10-30) Box skill copy: none.
- tmux crew CLI: `scripts/crew poll [--once]` is the GitHub wake source:
  read-only `gh` JSON for open crew PRs (head SHA, CI rollup, verdicts
  from hidden `crew:v1` lines at head, merged or closed) and assigned
  `crew:ready` issues is diffed against `poll-state.json` by a pure
  decision function, and each change becomes one wake record in
  `wake/queue.jsonl` naming one consumer (ci-passed → reviewer, ci-failed
  or changes → builder, approved → synthesizer, merged or closed →
  coordinator, newly assigned ready issue → builder). The first run
  records a baseline only. New profile option
  `runtime.options.poll_interval` (default 60). Tests on recorded `gh`
  JSON fixtures in `scripts/fixtures/poll/` and a fake `gh` in
  `scripts/test-crew.py`; usage in `docs/runtimes/tmux.md`. (issue #134,
  PR #223, 2026-10-30) Box skill copy: none.
- tmux crew observe: `scripts/crew attach <window>|<role>` attaches
  read-only by default (`tmux attach-session -r`; `--rw` to type), and
  `crew attach builders` opens a temporary tiled view of the builder band in
  a separate session (one `capture-pane` snapshot pane per builder window),
  killed on detach, so no crew window moves. `scripts/crew logs <window>
  [-n N] [-f]` tails the newest `.crew/runs/**/summary.md` in the run's
  worktree, never raw logs. `docs/observe.md` gains a tmux section that
  replaces the deferred-attach note; usage in `docs/runtimes/tmux.md`; tests
  with the fake `tmux` in `scripts/test-crew.py`. (issue #138, PR #216,
  2026-10-30) Box skill copy: none.
- tmux crew CLI: `scripts/crew send <window> <kind> <ref>...` messages a
  role window by reference: it refuses anything but refs (issue or PR
  number, full SHA, https link, path; no whitespace, no diff or traceback
  markers, 1024-byte line cap), appends one JSON line `{id, kind, refs,
  from, ts}` to `inbox/<window>.jsonl` and types the fixed nudge
  `inbox: <msg-id>` through the tmux adapter. Delivery is proven only by
  `ack: <msg-id>` in the window's status file: `--wait-ack <secs>` or
  `crew acked <window> <msg-id>`. Tests with the fake `tmux` in
  `scripts/test-crew.py`; usage in `docs/runtimes/tmux.md`. (issue #133,
  PR #214, 2026-10-30) Box skill copy: none.
- tmux crew CLI: `scripts/crew spawn <role> --issue <n> | --pr <n>
  [--pass build|fix|review|validate|land]` creates a role window in the
  repo's session at the next free index of its band (`ben-<issue>`,
  `vera-<pr>-r<k>-<pass>`, `sam`), in a unique worktree
  `<worktree-root>/<n>-<sha7>-<role>-<pass>/` from a fresh fetch (refusing
  the primary checkout and existing paths), with engine, model and effort
  from the profile tier routing (a reviewer skips the PR's `Engine:`
  trailer engines), `CREW_*` env via `-e` and the login `CREW_IDENTITY`
  only (the token is derived inside the window), a per-run brief, an atomic
  claim and a run record; Codex is pre-trusted per worktree, and a window
  whose harness is not in the foreground within the timeout is reported
  `failed:` and cleaned up. `scripts/crew kill <window>` stops the window
  and removes only that run's worktree, build output and state files;
  `crew down` now calls it for each role window. Tests with a fake `tmux`
  and a temp git repo in `scripts/test-crew.py`; usage in
  `docs/runtimes/tmux.md`. (issue #132, PR #171, 2026-10-30) Box skill
  copy: none.
- Grok Bot templates as render inputs, with a parity check: `templates/` is
  now the renderer's default `--inputs` tree (`runtimes/grok-bot/`, plus the
  new `backends/github.toml` command mapping for every operation, from
  `docs/backends/github.md` Interface mapping); `crew-render.py` renders
  briefs only when the tree has a `core/` directory and keeps the templates'
  remaining run-time placeholders verbatim. `scripts/test-render-parity.py`
  (run in CI) renders `profiles/default.toml`, alone and with the
  agentconnect example values, and diffs each template against its
  pre-conversion text (`scripts/fixtures/parity/pre/`); a seeded one-word
  drift fails. The `templates/README.md` placeholder table gains a "Profile
  key" column. No template text changes. (issue #126, PR #169, 2026-10-30)
  Box skill copy: deferred to #140.
- tmux crew CLI: `scripts/crew up --project <crew.toml> --inputs <dir>`
  resolves a `runtime.name = "tmux"` profile, renders the briefs into
  `<state-dir>/<owner>__<repo>/render/` and starts the detached session
  `crew-<owner>-<repo>` with the coordinator engine (Claude Code or Codex) in
  window 0 pointed at its brief; `GH_TOKEN` is derived inside the window,
  never in argv or a file. `up` on a running session changes nothing. For a
  Claude Code coordinator it installs the turn-end guard (`crew guard`, a
  Stop hook in the project's `.claude/settings.local.json`); the Codex
  recipe is documented. `crew down` refuses while the land lock is held,
  then kills role windows and the session. All tmux calls go through
  `scripts/crew-tmux.py`; tests with a fake `tmux` in `scripts/test-crew.py`,
  run in CI; usage in `docs/runtimes/tmux.md`. Design credit: firstmate's
  turn-end guard (contract only, no code copied). (issue #131, PR #168,
  2026-10-30) Box skill copy: none.
- Onboarding runbook leads with install by profile: `docs/runbook-new-repo.md`
  gains Step 0 (copy `profiles/default.toml` to `crew.toml`, `crew-config.py
  validate`, `crew-config.py resolve`, `crew-render.py`), maps command
  placeholders to resolved profile keys instead of a placeholder table, keeps
  the GitHub install mechanics (labels, collaborator, milestones and board,
  CI) as Steps 1 to 4 linked from the GitHub backend's Tracking section,
  installs routines from the rendered output with hand-fill as a short
  fallback, and adds checklist rows P1 profile validates, P2 render clean and
  P3 parity (once #126 lands). (issue #129, PR #167, 2026-10-30) Box skill
  copy: none.
- External pack contract and internal-name guard: `docs/packs.md` defines
  the pack layout (`manifest.toml`, optional `profile.toml`, binding docs,
  render overrides), the `eng_crew_version` pin and its compatibility rule,
  the capability declaration and wiring by `resolve --org-profile`, plus the
  direction rule (packs reference eng-crew, never the reverse; also in
  `AGENTS.md`). `check-repo.py --only denylist` fails on a whole-word,
  case-insensitive match of any name in the file named by `CREW_DENYLIST`
  (skipped when unset; no names committed). `crew-config.py resolve` folds
  each backend's `packs/<name>/manifest.toml` capabilities under every
  layer (`# pack:<name>`), and the unsupported-invariant check counts
  undeclared operations as unsupported; manifests accept
  `pack.eng_crew_version`. Tests in `scripts/test-check-repo.py` and
  `scripts/test-crew-config.py`. (issue #127, PR #164, 2026-10-30) Box
  skill copy: none.
- Renderer: `scripts/crew-render.py --project <crew.toml> [--org-profile
  <path>] --inputs <dir> --out <dir>` resolves the profile in-process
  (`crew-config.py resolve`), then writes one brief per role
  (`briefs/<role>.md`) and the profile runtime's artifacts (`runtime/**`)
  from render inputs, replacing install-time `<name>` placeholders from
  profile keys and `<op:<concern>.<operation>>` from a backend command
  mapping. Run-time placeholders stay verbatim. Fails closed with
  `file:line: reason` and writes nothing on an unknown placeholder, missing
  mapping or unsupported capability. Golden-file tests on a fixture profile
  and inputs in `scripts/test-crew-render.py` and `scripts/fixtures/render/`,
  run in CI; usage and placeholder map in `scripts/README.md`. (issue #125,
  PR #163, 2026-10-30) Box skill copy: none.
- Default GitHub profile and pack manifest: `profiles/default.toml` (Grok
  Bot runtime, `github` for all eight concerns, placeholder identities,
  engine routing from `docs/roles.md` Current routing for private repos) and
  `packs/github/manifest.toml` (the GitHub backend's capability declaration,
  every operation `supported`). The schema gains role display names
  (`identities.<role>.name`), `runtime.timezone`, `engines.fallback_engine`
  and `paths.toolchain_bin`; `crew-config.py validate` accepts them and
  validates a pack manifest. Tests in `scripts/test-crew-config.py`. (issue
  #124, PR #161, 2026-10-30) Box skill copy: none.
- Layered config resolver: `scripts/crew-config.py resolve --project
  <crew.toml> [--org-profile <path>]` merges core defaults, the default
  profile (`profiles/default.toml`, when present), an optional org profile
  read by path only and the project file. Tables merge by key; scalars and
  arrays replace; dropping a key under `identities`, `backends` or `engines`
  is an error. The result must pass `validate` plus cross-key checks: the
  unsupported-invariant rule of `docs/interfaces.md`, the single-identity
  `emulated` verdict requirement (#111) and integer options >= 1. Prints
  each key with the layer that set it. Documented in `docs/profile.md`
  (Layers and precedence); tests in `scripts/test-crew-config.py`.
  (issue #123, PR #162, 2026-10-30) Box skill copy: none.
- Profile schema and validator: `docs/profile.md` documents the `crew.toml`
  install-time profile (`[repo]`, `[runtime]` with tmux options,
  `[backends.<concern>]` for the eight interface concerns with an optional
  capability declaration, `[identities]` by `gh_user` login, `[engines]` tier
  routing, `[paths]`): every key, type, default and the placeholder it
  replaces. `scripts/crew-config.py validate <file>` (stdlib `tomllib`)
  prints `file:key: reason` and exits 1 on a missing or unknown key, unknown
  concern, runtime, backend or engine, wrong type, bad capability or a
  token-shaped value (patterns imported from `check-repo.py`); tests in
  `scripts/test-crew-config.py`, run in the CI `repo-guard` job. Indexed in
  `docs/README.md`, pinned in `scripts/required-docs.txt`. (issue #122,
  PR #159, 2026-10-30) Box skill copy: none.
- Backend interfaces (`docs/interfaces.md`): the minimum operations for each
  of the eight concerns (change, review, tracker, state tags, markers, CI,
  events, owner channel), the guarantee of each and the invariant (I1–I5) it
  protects; the capability declaration format (`supported | emulated (how) |
  unsupported`) with the unsupported-invariant rule; and the single-identity
  analysis (I1 breaks; compensation is COMMENT-review verdicts plus a recorded
  owner merge-ok, #111). `docs/backends/github.md` gains an Interface mapping
  section: one `gh` command or API call per operation. Adds no rule, gate,
  cap, marker field or label; `docs/protocol.md` untouched. Indexed in
  `docs/README.md`, pinned in `scripts/required-docs.txt`. (issue #121,
  PR #154, 2026-10-30) Box skill copy: none.
- tmux runtime binding design (`docs/runtimes/tmux.md`): answers #110 Q1
  wake (status files, inbox nudges and `crew poll` feed a zero-token watcher;
  turn-end guard), Q2 lifetime, Q3 coordinator engine, Q5 identities, Q6
  concurrency and Q7 failure (process-identity liveness probe), each with
  alternatives; contract table C1–C8 with C1 and C8 gaps declared; window
  layout with index bands; spawn and kill mechanics from #132. Watcher,
  turn-end guard, delivery-ack and liveness patterns credited to firstmate
  (MIT), no code copied. Indexed in `docs/README.md`, pinned in
  `scripts/required-docs.txt`. (issue #130, PR #152, 2026-10-30) Box skill
  copy: none.
- GitHub backend (`docs/backends/github.md`), section Tracking: the ten
  `crew:*` labels with GitHub colours and descriptions, why no listener fires
  on labels, Milestones and Project (v2) board, `Closes #n` / `Refs #n` /
  `Part of #n` / `Depends on #n` linkage, and the no-issue-comment steering
  limit. Protocol §4, §6, §7 and §9, `architecture.md` (label table kept as the
  role view), the runbook Steps 1 and 3 and `concepts.md` link it. Text move
  only; no rule, gate, cap, marker field or label changes. Indexed in
  `docs/README.md`, pinned in `scripts/required-docs.txt`. (issue #116,
  PR #149, 2026-10-30) Box skill copy: deferred to #140.
- GitHub backend (`docs/backends/github.md`), section Reviews, markers and
  identities: COMMENT vs formal reviews and the events each fires, why bots
  never post plain or inline comments, `gh` identity selection, why GitHub
  refuses self-approve, and the land (`--match-head-commit`) and
  update-branch mechanics. Protocol §1 and §4 keep the rules and link the
  mapping. Text move only; no rule, gate, cap, marker field or label changes.
  Indexed in `docs/README.md`, pinned in `scripts/required-docs.txt`; lesson
  hygiene note in `docs/lessons/2026-10-19-bottlenecks.md`. (issue #115,
  PR #146, 2026-10-30) Box skill copy: deferred to #140.
- Runtime contract (`docs/runtimes/README.md`): eight capabilities every
  runtime provides (wake on event, one consumer per event, messages by
  reference with proof of delivery, status protocol, liveness classes,
  isolation, serial land, owner channel and SLA), each with the guarantee it
  protects, plus a gap-declaration format. Contracts adapted from firstmate
  (`kunchenguid/firstmate`), no code copied (#130 decision).
  `docs/runtimes/grok-bot.md` gains a contract table with gaps declared.
  Pinned in `scripts/required-docs.txt`, indexed in `docs/README.md`.
  (issue #120, PR #148, 2026-10-30) Box skill copy: none.
- Concepts glossary (`docs/concepts.md`): one entry per abstract protocol
  term (change, change head, verdict, narrative post, state tag, marker, CI
  signal, wake event, tracker item / milestone / board, owner channel, land,
  runtime, backend, profile / pack) with its definition, the invariant it
  touches and today's GitHub / Grok Bot mapping. Terms only; no rule moves.
  Linked from `docs/README.md` and the `AGENTS.md` map; pinned in
  `scripts/required-docs.txt`. (issue #113, PR #142, 2026-10-29) Box skill
  copy: none.
- Portable eng-crew spec (`docs/specs/portable.md`): requirements P1–P8
  for runtime and per-concern tool abstraction, install-time profile and
  config layers; invariants every runtime + backend keeps; target layout;
  M13/M14 slices with dependencies; dated decisions from #110, #111, #112
  and #140; open questions mapped to the issues that settle them. Indexed
  in `docs/README.md` and pinned in `scripts/required-docs.txt`.
  (issue #110, 2026-10-29) Box skill copy: none (spec only; no protocol or
  template change).
- Standing quota diversity waive for reviewer engines: prefer available,
  cheap DeepSeek before reset, else allow Codex for one round's verdict
  under the documented risk, identity and recording rules.
  (issue #104, 2026-10-29) Box skill copy: eng-crew-roles (roles) and
  eng-pr-pipeline (protocol) need mirror (coordinator mirrors before merge;
  `crew:needs-mirror` holds the PR until then).
- Coordinator soft-finding follow-up after squash: file and dispatch a
  `crew:ready` issue in the same awake window, unless the user parked softs
  for a named cut; includes an issue template and duplicate check. Softs
  never block §7 squash. (issue #105, 2026-10-29) Box skill copy:
  eng-pr-pipeline (protocol §6) needs mirror (coordinator mirrors before
  merge; `crew:needs-mirror` holds the PR until then).
- Deploy secret sync AC for new deploy milestones: compare shared secrets
  across consuming hosts with safe fingerprints and name the GitHub secret
  store the workflow reads. New-repo wiring records secret names and hosts.
  (issue #103, 2026-10-29) Box skill copy: eng-pr-pipeline (protocol §3)
  needs mirror (coordinator mirrors; `crew:needs-mirror` until mirrored).
- Mutation evidence rule: behaviour-changing PRs that add or change a
  user-visible create, update or complete (or equivalent) mutation paste an
  inline happy-path snippet (create an entity, progress/complete it, then
  delete it: item and/or list delete with cascade, where the snippet also
  shows the child items are gone) in `## Test Output` and
  `## Acceptance Evidence`; the reviewer-validator checks it and reproduces
  where possible, else `disagrees`. Docs-only and non-CRUD PRs unchanged.
  (issue #100, 2026-10-29) Box skill copy: eng-pr-pipeline (protocol §3)
  needs mirror (coordinator mirrors before merge; `crew:needs-mirror` holds
  the PR until then).
- Inline evidence rule for PR bodies: `## Test Output` and `## Acceptance
  Evidence` must paste command → output snippets and/or screenshots;
  path-only `evidence/` pointers are insufficient; `evidence/` stays the
  durable audit trail. Example in protocol §3; roles PR template and
  verification builder duty updated. (issue #98, 2026-10-29) Box skill copy:
  eng-pr-pipeline (protocol §3) needs mirror (coordinator mirrors after
  merge).
- README rewritten for first-time readers: what and why, plain-words how it
  works with the diagram, who it is for, what you get, and the v1 cut block
  kept. (issue #96, 2026-10-29) Box skill copy: no box skill change.
- Product-repo README seed `templates/product-readme.md`, a README install
  step in `docs/runbook-new-repo.md` (Step 6) and a normative README rule in
  `docs/protocol.md` section 8. (issue #96, 2026-10-29) Box skill copy: needed
  for `docs/protocol.md` and `templates/` (`crew:needs-mirror` until mirrored).
- README Status / v1 cut section: M1–M12 closed, in-cut vs out-of-cut (#80
  hold, product prove-its), Notion brief as gap-table north star. (#95,
  issue #94, 2026-10-29) Box skill copy: no box skill change.
- Root `AGENTS.md` thin review/build posture (blocking only for failed ACs,
  stage 7 gate, CI or security; wording and script edge cases are yellow
  follow-ups), required reading in the B1, B2, V1 and V2 templates, and a
  findings entry for the #74/#77/#88 round-burners (#93, issue #92,
  2026-10-29) Box skill copy: eng-pr-pipeline and eng-crew-roles get the "read
  AGENTS.md" line (coordinator mirrors after merge).
- Self-improve intake (M11): `docs/self-improve.md` (triggers, candidate card,
  accept/close, lesson path, `repo:` vs `crew:` scope, risks),
  `templates/intake-candidate.md`, the offline `scripts/intake-sweep.py` helper
  with `scripts/test-intake-sweep.py` (CI step), a weekly intake note in the
  stuck-PR sweeper template, coordinator/builder notes in `docs/protocol.md`
  and `docs/roles.md`, lesson `2026-10-29-self-improve-intake.md` and a
  findings entry. (#90, issue #89, 2026-10-29) Box skill copy:
  eng-pr-pipeline and eng-crew-roles (coordinator mirrors after merge).
- Metrics to decisions: `docs/metrics/decisions.md` (latency and rework
  sensors, windows, tunable thresholds, rollup vs per-repo, the `metrics-gate`
  issue, hold/waiver/lift), `scripts/metrics-decide.py` with fixture tests and
  a CI step, `templates/metrics-regression-issue.md`, gate notes in protocol
  section 6, `docs/roles.md` and the coordinator, builder, reviewer-validator
  and synthesizer templates, lesson `2026-10-29-metrics-to-decisions.md` and a
  findings entry. (#88, issue #86, 2026-10-29) Box skill copy:
  eng-pr-pipeline and eng-crew-roles (Ash mirrors before merge:
  `crew:needs-mirror` blocks the squash until the mirror comment is posted,
  protocol sections 6 and 7).
- Step-summary observe protocol (M8): `docs/observe.md` (when to write a step
  line, fields, `.crew/runs/` paths, promote the short summary onto the PR,
  what reviewers skim, risks), helper `scripts/step-summary.py` with
  `scripts/test-step-summary.py` (run in CI), `templates/step-summary.md`,
  builder, reviewer and synthesizer template notes, protocol §3 and roles
  pointers, `.gitignore` for raw step logs, lesson
  `2026-10-29-step-summary-observe.md` and a findings entry. (#87, issue
  #85, 2026-10-29) Box skill copy: eng-pr-pipeline and eng-crew-roles
  (coordinator mirrors before merge; `crew:needs-mirror` holds the PR until then).
- Verification protocol: typed runtime evidence as a merge gate. New
  `docs/verification.md` (shape table for web, CLI, service, API and mobile;
  docs-only N/A; fail-open), role duties in `docs/roles.md`, protocol §3, §7
  and Gate registry, and the B1, V1, V2 and synthesizer templates; starter
  adapters `templates/evidence/` (CLI exit/stdout, web screenshot); lesson
  `2026-10-29-typed-verify-evidence.md`, findings entry, required-docs pins and
  a `check-repo.py` `verification-shapes` rule with tests. (#84, issue #83,
  2026-10-29) Box skill copy: eng-pr-pipeline and eng-crew-roles (the mirror comment must land and clear `crew:needs-mirror` before merge).
- Synthesizer merge blockers: an open coordinator hold-until-X (or crew hold
  command) overrides standing doc-only merge-ok, and an open `steer cmd=rereview`
  at the current head blocks squash until a fresh `pass=verdict` lands on a
  different engine; protocol §7 and Gate registry, `templates/synthesizer.md`,
  lesson `2026-10-29-synthesizer-hold-race.md`, findings entry, and a
  `check-repo.py` static guard. (#82, issue #81, 2026-10-29) Box skill copy:
  eng-pr-pipeline (Ash mirrors before merge: `crew:needs-mirror` blocks the squash
  until the mirror comment is posted, protocol sections 6 and 7).
- Correction hierarchy in `docs/lessons/README.md` (architecture, types, lint, CI,
  prose last; "prose only, because ..." exception; new `encoded` status) and the
  first encoded lesson: `check-repo.py` rule `marker-sha` fails a `crew:v1` marker
  whose `sha=` is not a full 40-char SHA, with tests. (#77, issue #69,
  2026-10-28) Box skill copy: no box skill change.
- Merge-enforcement runbook with target rules, plan blocker, application,
  verification, rollback and fail-open; protocol §7 and onboarding pointers.
  (#67, 2026-10-28) Box skill copy: mirror needed (docs/protocol.md §7 pointer).
- Cycle-time and rounds metrics artifact: `docs/metrics/` (README, `prs.md`,
  `prs.csv`), `scripts/metrics-refresh.py` and its offline test, and a metrics
  refresh note in the stuck-PR sweeper template. (#75, issue #63,
  2026-10-28) Box skill copy: not mirrored here; templates/ note to be mirrored
  by the coordinator.
- Owner-SLA drill plan: `docs/metrics/owner-sla-drill.md` (synthetic hold, expected
  timestamps, checks, results table; coordinator owns the clock). (#71, issue #66,
  2026-10-28) Box skill copy: no mirror needed (no protocol or template change).
- Gardening findings buffer: `docs/findings/README.md` (how to append a smell,
  when to batch, ownership, entry template) and `docs/findings/buffer.md`
  seeded with the recurring builder B2 watch smell (PRs #35, #38, #41); lessons
  README points to it. (#78, issue #68, 2026-10-28) Box skill copy: no box
  skill change.
- Lessons log: `docs/lessons/README.md` (entry format and index) and
  `docs/lessons/2026-10-19-bottlenecks.md`. Added `CONTRIBUTING.md` (iteration
  process) and this changelog. (#15, 2026-10-20) Box skill copy: no box skill
  change.
- Architecture overview and docs index. (#8, 2026-10-20) Box skill copy: no box
  skill change.
- Crew collaboration-flow diagram. (#10, 2026-10-19) Box skill copy: no box skill
  change.
- Crew protocol doc: `docs/protocol.md` ports the eng-pr-pipeline protocol into
  the repo. (#14, 2026-10-20) Box skill copy: no box skill change.
- Roles, tiers and engines: `docs/roles.md` ports the `eng-crew-roles` box skill.
  (#13, 2026-10-20) Box skill copy: not edited (the doc is a port with no new
  policy).
- Routine and listener templates per role (`templates/`) and AgentConnect
  examples. (#16, 2026-10-20) Box skill copy: no mirror needed (new files only).
- Crew-flow diagram embedded in `docs/architecture.md`. (#22, 2026-10-20) Box skill
  copy: no box skill change.
- Onboarding runbook for a new repo: `docs/runbook-new-repo.md`. (#26, 2026-10-20)
  Box skill copy: no box skill change.
- CI repo guard: `scripts/check-repo.py` checks for secrets, required docs and
  sections, and relative links, with fixture tests. (#17, 2026-10-20) Box skill
  copy: no box skill change.
- Protocol: evidence a reviewer's verdict relies on is committed on the PR head,
  never a side branch; evidence-only changes get a rereview steer
  (`docs/protocol.md` §3, §6). New lessons entry
  `docs/lessons/2026-10-20-evidence-on-pr-head.md`. (#23, issue #19, 2026-10-20)
  Box skill copy: Ash (coordinator) updated the box eng-pr-pipeline skill in
  sync with this change.
- Lesson statuses use one vocabulary (`applied` / `superseded` / `open`) and were
  re-verified against `main`; new drift check `scripts/check-skill-drift.py`
  (with `scripts/test-check-skill-drift.py`) compares `docs/protocol.md` and
  `docs/roles.md` to the box skills, run by the coordinator on
  `crew:needs-mirror` and after protocol/template PRs. (#74, issue #70,
  2026-10-28) Box skill copy: not mirrored here; mirror by the coordinator if
  protocol/templates changed (this change touches neither).

### Changed

- `crew` CLI split per command (structural, no behaviour change):
  `scripts/crew` is a thin entry point that loads `scripts/crew.d/<cmd>.py`
  in sorted order (each module has `register(subparsers)` and `run(args)`),
  with the shared helpers in `scripts/crew.d/_shared.py`.
  `scripts/test-crew.py` is split into one `scripts/test-crew-<cmd>.py` per
  command, with its fixtures in `scripts/crew_testlib.py`; CI runs them by
  glob. `scripts/README.md` has one row per module and test file, and
  `docs/runtimes/tmux.md` one `### crew <cmd>` section per command with its
  usage line. No flag, output, exit code or file written changes, and
  `crew --help` lists the same 16 commands, now in sorted order. Adding a
  command now adds files only. (issue #224, PR #254, 2026-10-30) Box skill
  copy: none.
- Spec sync, part 2 of 2 (the #259 closing slice for M14 and M14.1),
  status-only: `docs/specs/portable.md` §5 marks 14.10 (#139), 14.1e
  (#234), 14.1h (#255) and 14.1i (#257) `done` from live issue state
  (#140 and #219 stay `open`); the README Status section lists `v1.0.0`
  (released, linked), M13 done except #140, M14 and M14.1 done, and R1 in
  progress with `v2.0.0` next; `docs/runtimes/README.md`,
  `docs/runtimes/tmux.md` (H1, intro) and the `docs/README.md` index drop
  "design" for shipped wording, with the pinned H1 updated in
  `scripts/required-docs.txt`; and the tmux placeholder-refusal paragraph
  now states the shipped #268 behaviour (resolved value, per command key).
  No requirement, rule or gate wording changes. Status-only spec edit under
  the owner's standing grant (#111). Refs #259, #110. (PR #271, 2026-10-30)
  Box skill copy: none.
- Post-R1 / M14.1 cleanups: `docs/release.md` drops "Nothing here is
  implemented yet" and the "R1.3 adds the row" wording, and names the merged
  workflow, bundle build and bundle attach PRs and the hand-released
  `v1.0.0`; `docs/interfaces.md` single-identity Scope allows an owner
  standing merge grant (the #111 grant) as an alternative to a per-change
  merge-ok, with no gate change; `docs/runtimes/tmux.md` documents
  `paths.eng_crew` next to the other profile paths; and
  `.github/workflows/release.yml` adds `scripts/release-bundle.py` and
  `scripts/test-release-bundle.py` to its `pull_request.paths` filter only.
  `crew:sensitive`: the owner approves the merge. Refs #110, #145, #233.
  (PR #252, 2026-10-30) Box skill copy: none.
- tmux briefs work in any repo (14.1d): every brief cites eng-crew docs as
  `<eng-crew>/docs/...` (new optional profile key `paths.eng_crew`), runs
  `crew` as `$CREW_BIN` and adds `-R <owner>/<repo>` to every `gh` command.
  The builder writes step summaries with `scripts/step-summary.py` to
  `.crew/runs/issue-<n>/build/summary.md` (fix rounds `pr-<pr>/fix-<k>/`).
  The coordinator drains with `crew drain`, arms the watcher with a
  one-shot `crew poll --once` source, starts validation only after the
  review pass says `pass`, and spawns the next round when a builder `done:`
  comes at the round's verdict head. The reviewer's idempotency check is per
  round, and a failing review pass posts the `changes` verdict itself. The
  synthesizer uses `crew land-lock acquire/release` and reads two new tmux
  options: `merge_grant` (standing grant scope, default `"none"`: per-PR
  merge-ok) and `hold_label_blocks` (default `true`); a grant gives
  permission only. Golden render fixtures and tests updated; `scripts/crew`
  docstring marks `--inputs` optional. Grok Bot templates unchanged. Refs
  #139. (issue #233, PR #244, 2026-10-30) Box skill copy: deferred to #140.
- Mirror hold gate is a drift check (#128): for a change touching
  `docs/protocol.md` or `templates/`, the coordinator's mirror comment counts
  only if it records the rendered output deployed to the live dir and
  `check-skill-drift.py --project` (plus `--only pipeline` when
  `docs/protocol.md` changed) exiting 0 at the last touching commit, with the
  commands and output inline. Who, label, lighter-lane exemption and
  fail-open are unchanged. Protocol §6, §7 and Gate registry, Grok Bot
  mirror hold gate, `CONTRIBUTING.md` "Two copies", portable spec P4 and §8,
  `scripts/README.md`, and a lesson. (issue #128, PR #227, 2026-10-30) Box
  skill copy: deferred to #140.
- Protocol preamble, §6, protocol freeze, gate contract, gate registry and §7
  reworded in glossary terms (`docs/concepts.md`): change, change head,
  verdict, narrative post, state tag, CI signal, wake event, tracker item /
  board, land, owner channel, backend. The gate registry gains a **Binding**
  column (core / runtime / backend). Builder watch and mirror hold become
  runtime gates in §7; their Grok Bot satisfaction rules move verbatim to
  `docs/runtimes/grok-bot.md` (Runtime gates). `docs/architecture.md` role
  table column "GitHub identity" is now "Identity", linked to the GitHub
  backend. Lesson hygiene note in the merge-gate watch-race lesson. Anchors
  and the `synthesizer-blockers` guard text are unchanged. No rule, gate, cap,
  marker field or label changes meaning. Closes M13 Phase A. (issue #119,
  PR #155, 2026-10-30) Box skill copy: deferred to #140.
- Protocol hard rules and §1–§5 reworded in glossary terms
  (`docs/concepts.md`): change, change head, verdict, narrative post, state
  tag, marker, CI signal, wake event, tracker item / board, land, owner
  channel, backend. GitHub and Grok Bot specifics stay only where the
  sentence links `docs/backends/github.md` or `docs/runtimes/grok-bot.md`;
  wake event names, labels, marker fields and `APPROVE` / `REQUEST_CHANGES`
  are kept. §1 is now "Roles and identities" (column "Identity"), with the
  old `#1-roles-and-github-identities` anchor kept; §2 stage 3 points to the
  runtime binding for the per-change watch. Lesson statuses re-checked;
  hygiene notes in the evidence-on-head and validation-gate lessons. No rule,
  gate, cap, marker field or label changes meaning. (issue #118, PR #153,
  2026-10-30) Box skill copy: deferred to #140.
- Routine templates moved under `templates/runtimes/grok-bot/` (`git mv`,
  contents unchanged apart from relative-link depth): B1, B2, V1, V2, S1,
  A1–A3, `wiring.md` and `reviewer-engines.md`. Runtime-neutral templates
  (evidence adapters, `step-summary.md`, `product-readme.md`,
  `intake-candidate.md`, `metrics-regression-issue.md`) stay in
  `templates/`. `templates/README.md` indexes both trees; links in docs,
  examples and lessons, `scripts/required-docs.txt` and the
  `synthesizer-blockers` guard path updated. The `crew:needs-mirror` rule
  keys on the `templates/` prefix and still covers the moved files; no rule,
  gate, cap, marker field or label changes meaning. (issue #117, PR #151,
  2026-10-30) Box skill copy: deferred to #140.

- Grok Bot runtime binding (`docs/runtimes/grok-bot.md`): routine-only
  mechanics moved verbatim out of the core. From protocol §6: per-PR watches,
  the verified B2 hand-off, comment-listener wakes and the lighter-lane
  routing paragraph; from the protocol: the pilot notes; from
  `templates/README.md`: event to consuming role, the lighter-lane routing
  note and routine limits. Each source spot keeps a one-line pointer; no
  rule, gate, cap, marker field or label changes meaning. Pinned in
  `scripts/required-docs.txt`, indexed in `docs/README.md`; lesson status
  paths updated. (issue #114, PR #147, 2026-10-30) Box skill copy: deferred
  to #140.

- Builder heartbeat and stuck-PR sweeper watchdog: builder workers refresh a
  `heartbeat:` line in their claim file every 5 min; the sweeper's `builder-silent`
  row flags a claim silent for 15 min and messages the builder. Bottleneck lesson
  #2 marked documented. (#72, issue #65, 2026-10-28) Box skill copy: not mirrored
  here; mirror by the coordinator.
- Templates match the lighter lane's B2/watch and mirror exemptions; reviewer
  verdict-pass messages route REQUEST_CHANGES, and sweeper/coordinator messages
  route red CI and close-out to the builder. Lane membership uses the full
  diff at head; fixes leaving the lane attach B2. Follows up the lighter-lane
  notes (Refs #55). (issue #57, 2026-10-25)
  Box skill copy: not mirrored here; mirror by the coordinator.

- The coordinator owns triage: a window at least once per awake half-day, and
  every open issue leaves it `crew:ready`, `crew:spec`, `crew:needs-md`,
  deferred to the next milestone, or closed with a reason. The stuck-PR sweeper
  promotes `crew:hold` / `crew:escalated` items waiting on the user for more
  than 2h (awake, PT) to `crew:needs-md`, routes nudge-cap escalations through
  the coordinator, skips held and needs-md PRs for stall nudges but lists them,
  and reports open issues with no `crew:*` state label older than one awake
  day. A reviewer-validator that holds its verdict for a user decision adds
  `crew:needs-md` and posts a `pass=hold` COMMENT review with `verdict=n/a`
  naming the open item (folds in #48). (#56, issue #51, 2026-10-25)
  Box skill copy: not mirrored here; mirror by the coordinator.

- Protocol and templates change in milestone batches, with a blocking-gate
  exception governed by a gate contract and registry. The lighter lane for
  non-protocol docs skips B2 and the mirror hold, keeps CI and review/validation,
  and routes fixes to the builder by message. (#55, issue #50, 2026-10-25)
  Box skill copy: not mirrored here; mirror by the coordinator.

- Owner decisions have a 2h awake-hours PT SLA, `crew:needs-md` escalation,
  timed defaults, and asks only through the coordinator. Standing doc-only
  merge-ok (excluding code, `.github/`, `templates/`, and `docs/protocol.md`)
  preserves all other merge gates. Onboarding requires Milestones and a
  Project board; closed milestones are frozen. (#54, issue #49, 2026-10-25)
  Box skill copy: not mirrored here; mirror by the coordinator.

- Merge gate requires the builder's `pass=watch` marker (full 40-char `sha=` of
  any commit on the PR, same rule as the reviewer cross-check) in protocol §7
  and the synthesizer template; a PR without it is held and the synthesizer
  pings the builder with priority. The reviewer's first verdict pings the
  builder with priority (still never creating B2). New lessons entry
  `docs/lessons/2026-10-23-merge-gate-watch-race.md` for the PR #41 hand-off
  race. A PR changing `docs/protocol.md` or `templates/` gets a
  `crew:needs-mirror` label from the reviewer's verdict pass; the merge gate
  refuses to merge while it is present, and the coordinator removes it on
  posting the box-skill mirror comment, then pings the synthesizer (new label in
  the runbook, architecture, wiring and role templates). The gate's external and
  cutover exemptions are now explicit with reasons, plus a third for
  coordinator-opened `crew:spec` PRs (no builder, no B2; merge on `/crew
  merge-ok`). A cutover PR is gated again as soon as its builder posts its watch
  review or any `crew:v1` marker after the cutover (by post time, covering B2
  attached at the unchanged cutover SHA), independent of the marker. The
  reviewer adds `crew:needs-mirror` before posting the verdict, but skips it
  when the coordinator's mirror comment is newer than the last
  protocol/template-touching commit (a later such commit needs a fresh mirror
  comment); the synthesizer uses the same freshness rule, and the synthesizer derives the
  hold from the changed paths, not only the label. (#45, issue #43, 2026-10-23) Box
  skill copy: not mirrored here; mirroring the box eng-pr-pipeline skill is for
  Ash.
- Reviewer watch cross-check accepts a `pass=watch` marker whose full 40-char
  `sha=` is any commit on the PR, not only the head (the marker is posted once
  per PR, so a CI-fix push before the first verdict must not look like a missing
  watch); `<sha7>` wording in the protocol now includes review headers; the
  "Stale known-gap bullet" lessons entry gains its status and linked-issue
  fields. (#44, issue #42, 2026-10-23) Box skill copy: mirror of the box
  `eng-pr-pipeline` skill is for the coordinator (Ash).
- Watch hand-off: the routine folder id is the single identifier written to
  `watches/pr-<n>.b2`; the B1 run only requests the hand-off and the parent turn
  alone verifies, writes the marker file and posts `pass=watch`; every marker's
  `sha=` is the full 40-char head SHA and the reviewer cross-check matches on it.
  Stale #19 known-gap bullet updated. New lessons entry
  `docs/lessons/2026-10-23-watch-handoff-first-run.md`. (#41, issue #39,
  2026-10-23) Box skill copy: mirror of the box `eng-pr-pipeline` skill is for
  the coordinator (Ash).
- `docs/protocol.md` links `docs/roles.md` (and its worktree isolation section)
  directly instead of calling it planned; removed the resolved #29 entry from the
  runbook's known gaps. `docs/README.md` moves `scripts/` to Available now, and
  the Planned section now says nothing is planned. (#40, issue #29, 2026-10-23)
  Box skill copy: no box skill change.
- Aligned the live `crew:needs-md` label description on eng-crew with the runbook
  ("Blocked on an owner decision (recommended default + deadline)") and removed
  the resolved #28 entry from the runbook's known gaps. (#38, issue #28, 2026-10-23)
  Box skill copy: no box skill change.
- Engine-steer example uses the actual-builder-engine wording and links
  `docs/roles.md#actual-builder-engine`. (#35, issue #34, 2026-10-23) Box skill
  copy: no box skill change.
- Merge-ups use no review round: a clean merge-up after an APPROVE gets a formal
  merge-up re-approve with the same round; after CHANGES it gets an ack with no
  round and no verdict; a conflict resolution that changes behavior is a normal
  round. The #16 ack-based merge-gate exception is removed from the reviewer,
  synthesizer and sweeper templates. (#32, 2026-10-21) Box skill copy: the box
  eng-pr-pipeline skill already has this rule; the repo mirrors it.
- Actual builder engine: a round's builder engine is the engine that actually
  wrote its commits, named in the fix note, an `Engine:` commit trailer and the
  builder marker; the reviewer must differ from it. If the builder marker and the
  fix note or commit trailer disagree on the engine, the note or trailer wins,
  and before merge the reviewer re-checks at head (fresh review + validation) on
  an engine different from the actual builder engine, triggered by the
  coordinator's rereview steer. (#33, 2026-10-21) Box skill copy:
  the box eng-pr-pipeline skill already reads the engine that actually wrote the
  round; the eng-crew-roles box skill still needs the mirror (flagged to the
  coordinator).
- Builder per-PR watch B2 attachment is verified and observable: builder parent
  turn lists routines, confirms the four events, records `watches/pr-<n>.b2`
  and posts a `pass=watch` marker; sweeper `no-builder-watch` row and
  detection-window note; reviewer first-verdict cross-check; protocol event
  list and runbook B2 creation point corrected. New lessons entry
  `docs/lessons/2026-10-23-builder-watch-attach.md`. (#37, issue #36,
  2026-10-23) Box skill copy: the box `eng-pr-pipeline` skill mirror (the `watch`
  pass value in §4, B2 events `ci-failed`, `review-changes-requested`,
  `pr-merged`, `pr-closed` in the §6 builder line, and the attach-verification
  step) is applied by the coordinator before merge per R4. AC1 dry run on PR #37
  recorded in the lessons entry.

### Fixed

- tmux crew placeholder paths (#139 N1): `crew` now checks the **resolved**
  `paths.*` value, whichever layer set it, so a project `crew.toml` that
  omits `paths.state_dir` (falling back to `<state-dir>` in
  `profiles/default.toml`) is refused, exit 1, instead of putting the land
  lock under `<cwd>/<state-dir>/`. Each command checks only the keys it
  uses: every command checks `state_dir`; `spawn`, `kill`, `down` and
  `restart` also check `worktree_root`; only `spawn builder`, whose brief
  pins `<toolchain-bin>`, checks `toolchain_bin`. Tests in
  `scripts/test-crew.py` cover an omitted key, an explicit placeholder and
  real paths. Also (#139 N6): `crew kill` of a validate run removes the
  round's `verdicts/pr<n>-<sha7>-r<k>-verdict.md`, and kill removes the run's
  `runs/**/<window>[.-]*` files, including subdirectories such as
  `runs/body/`, never another window's. Roadmap 14.1j. (issue #265, refs
  #139, PR #268, 2026-10-30) Box skill copy: none.
- tmux verdict state tags and owner asks from the #139 live run (N5, N4):
  the reviewer pass that posts the verdict then sets the state tags per
  protocol §4 (`pass`: add `crew:approved`, remove `crew:in-review` and
  `crew:changes`; `changes`: add `crew:changes`, remove `crew:in-review` and
  `crew:approved`). The coordinator's `pr-merged` close-out also removes
  `crew:in-review` and `crew:changes` if present. The coordinator posts and
  closes owner asks on a PR as COMMENT reviews (`[<CoordinatorBot>/ask]`)
  with a `pass=steer cmd=ask` / `cmd=ask-closed` marker, never as plain PR
  comments. Golden fixtures under `scripts/fixtures/render/tmux/` updated.
  Roadmap 14.1k. (issue #266, refs #139, PR #267, 2026-10-30) Box skill
  copy: deferred to #140.
- tmux briefs from the #139 live run (F4, F5 brief side, F6): the
  coordinator brief renders the profile `merge_grant`; a merge-ok ask never
  carries an auto-apply merge default (its deadline default is `hold` or an
  escalation), and a merge-ok is recorded only from the owner's own words or
  a profile `merge_grant` that covers the PR, never from a repo-specific
  grant in eng-crew's protocol prose such as §6's standing doc-only
  merge-ok. The synthesizer brief agrees: with `merge_grant = "none"` it
  lands only with a per-PR owner merge-ok marker at head. Both briefs pass
  `--project "$CREW_PROJECT"` (the absolute project `crew.toml`), never a
  relative `crew.toml`. On `pr-merged` the coordinator removes
  `crew:approved` and `crew:hold` from the PR and `crew:ready` from the
  closed issue, and deletes the merged head branch only for a merged
  same-repo PR, using its `headRefName`, never the default or base branch
  (else it skips and says why). Golden fixtures under
  `scripts/fixtures/render/tmux/` updated; Grok Bot renders unchanged.
  Roadmap 14.1h. (issue #255, refs #139, PR #256, 2026-10-30) Box skill
  copy: deferred to #140.
- tmux crew restart, hooks dialog and state fixes from dry run 2 (#234 N2,
  N3 code side, N4, N5, N7, N8, F15) and the #139 live run (F5, F7):
  `crew restart` of a builder whose last line is `done: #n #pr sha` restarts
  as `--pass fix --pr <pr>`, never a second build pass; the watcher queues a
  `dialog` wake (action `escalate`) on the next scan when a run shows a
  trust or Codex hooks-review dialog, instead of after `--stale`; every
  Codex pass runs `-s workspace-write --add-dir <state-dir>/<owner>__<repo>`,
  so review and validate can write `$CREW_STATUS` and `verdicts/`; `crew
  spawn` adds `.crew/` to the worktree's `info/exclude`; every window gets
  `CREW_PROJECT`; the watcher handles SIGHUP like SIGTERM; the stale wake
  key ignores the liveness class; commands refuse a profile whose
  `state_dir`, `worktree_root` or `toolchain_bin` is still a placeholder;
  `crew kill` removes all of the run's `runs/<window>.*` files. Tests in
  `scripts/test-crew.py`; `docs/runtimes/tmux.md` updated. Roadmap 14.1f.
  (issue #250, refs #139, PR #260, 2026-10-30) Box skill copy: none.
- tmux briefs from dry run 2 (#234 N1, N2 and N3, brief side): the
  coordinator brief never types into a role window on a `dialog` wake or an
  `ambiguous` `stale:` wake; it kills and respawns the window once when its
  launch options should have prevented the prompt, else asks the owner with
  the window name and `crew attach WINDOW --rw`. The builder build pass looks
  for an open PR that closes the issue and adopts it as a fix round instead
  of opening a duplicate. The builder branch is `builder/<n>-<slug>`, not an
  unrendered `<role>/`. Golden fixtures under `scripts/fixtures/render/tmux/`
  updated; Grok Bot renders unchanged. Roadmap 14.1g. (issue #251, refs #139,
  PR #253, 2026-10-30) Box skill copy: deferred to #140.
- tmux crew review rounds, claims and probes from the #139 dry run (B2 code
  side, F3, F4, F7, F17, F18, F20, F21, `verdicts/` cleanup): `crew poll`
  emits `fix-at-head` (to the reviewer, with round `k`) when a builder fix
  note lands at the head of a `verdict=changes`, so an evidence-only fix no
  longer deadlocks round 2, and `ci-passed` records carry the round `k`;
  reviewer claims (`reviewer-pr<n>-<sha7>-r<k>-<pass>`) and worktrees carry
  the round and pass, so review and validate run in parallel; `done:` is
  terminal (no restart, skipped by the watcher) only for reviewer and
  synthesizer runs, so a builder that dies after `done:` is detected and
  restartable; Codex's `Hooks need review` dialog probes `ambiguous`; the
  synthesizer takes the tier's first engine as is; a dead pane reads `dead`
  at spawn, not `export`; `crew kill` removes a reviewer run's verdict
  files. Tests in `scripts/test-crew.py`; `docs/runtimes/tmux.md` updated.
  Roadmap 14.1c. (issue #232, refs #139, PR #247, 2026-10-30) Box skill
  copy: none.
- tmux crew process, env and safety fixes from the #139 dry run:
  `crew kill` and `crew down` SIGTERM the pane's process group, SIGKILL
  what is left after 2 s and check it is gone (Codex ignores the SIGHUP of
  `kill-window`); `crew guard` is a no-op unless `CREW_ROLE=coordinator`,
  so the project Stop hook no longer blocks role windows; a Codex
  coordinator is pre-trusted for the project, and a Claude Code trust
  dialog is documented and probes `ambiguous` in `crew status`, which now
  has a coordinator row; `CREW_SANDBOX_ENV` reaches every window, not only
  Codex role windows; `crew up` prints render output only on failure; every
  window gets `CREW_BIN`, the absolute path of this checkout's
  `scripts/crew`. (issue #231, refs #139, PR #240, 2026-10-30) Box skill
  copy: none.
- `crew kill` refuses to remove unlanded work: before removing a run's
  worktree it lists uncommitted and untracked paths and commits not
  contained in a fresh fetch of the default branch, the run's branch or the
  run's PR head; if any, it still stops the window but keeps the worktree
  and state files, prints the items and exits 1. `crew kill --discard
  --reason "<why>"` removes anyway after posting the reason on the run's PR
  or issue; `--discard` without `--reason` is refused. `crew down` keeps the
  session and names the windows holding unlanded work. Tests with a temp git
  repo and a bare remote in `scripts/test-crew.py`; `docs/runtimes/tmux.md`
  kill section updated. (issue #172, PR #221, 2026-10-30) Box skill copy:
  none.
- Crew-flow diagram: builder engine order and escalation arrow. (#12, 2026-10-20) Box
  skill copy: no box skill change.
- A failed validation pass never becomes an APPROVE: protocol (stage 7 and merge
  gate) and templates now say so; AC4 consumers and a stale live claim corrected.
  (#25, 2026-10-20) Box skill copy: the gate rule and the AC4 exception are both in
  the box skill; the repo mirrors them.

## Bootstrap (2026-10-19)

### Added

- Framework spec (`docs/specs/framework.md`), README and CI (markdownlint and an
  offline link check). Direct commit to main (no PR). Box skill copy: no box skill change.
