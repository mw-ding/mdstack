# Crew scheduler

How the tmux crew decides which worker to start next, crew-wide, from the
crew's demand, each item's priority, the workers' state, the machine's state
and owner presence ([#587](https://github.com/mw-ding/mdstack/issues/587);
umbrella [#110](https://github.com/mw-ding/mdstack/issues/110)). It replaces
the per-pool admission of the [builder lead](runtimes/tmux.md#builder-lead)
and [reviewer lead](runtimes/tmux.md#reviewer-lead) with one shared
decision. It carries out the owner's rescope of 2026-11-02 (about 22:55Z):
"design a more comprehensive workload like scheduling based on the business
of the entire crew and also the current machine".

Built: the [build issues](#build-issues) have landed, and both leads admit
through `mdstack schedule decide`. S8 was closed unbuilt by the owner's
2026-11-03 [overlap](#overlap) decision. This page adds no rule, gate, round
cap, marker field or label. The [protocol](protocol.md) still owns those, and
GitHub stays the tool of record (invariant I5). The tmux binding's
[Q6](runtimes/tmux.md#q6-concurrency) and
[Scaling policy inputs](runtimes/tmux.md#scaling-policy-inputs) point here.

## Problem

Today each lead admits workers on its own, with `min(queued, cap - active)`
bounded by two on/off machine gates: running suites (`max_suites`, default
`cpus // 4`) and one-minute load at or above the CPU count. On 2026-11-02
this showed five failure modes:

| # | Seen | Cause |
|---|---|---|
| F1 | Admission swung between serializing, where one suite blocked both pools, and surging, where 5–6 suites pushed load to 110–170 on 16 CPUs and caused model gateway 503 stalls | On/off gates with no hysteresis and no ramp limit; the one-minute load average lags each burst of starts |
| F2 | Reviews and merge-ups for nearly done PRs waited behind new builds, and M19 fill-in blocked M18 validations | Each pool admits in arrival order; nothing ranks work across pools or by distance to landing |
| F3 | Same-file PRs ran in parallel and then conflicted one after another; each merge-up cost 30–60 minutes, and the median open→merge time doubled from 30 to 61 minutes | Dispatch ignores file overlap; the train drops overlapping members instead of trying them together |
| F4 | Idle builders and orphan processes held slots ([#572](https://github.com/mw-ding/mdstack/issues/572)) | Worker state was not an admission input; fixed by #586 for idle builders |
| F5 | Owner presence needed manual cap edits ([#577](https://github.com/mw-ding/mdstack/issues/577)) | Presence was not an input; fixed by #582 |

## Overview

```text
             builder lead wake                 reviewer lead wake
                    │                                  │
                    ▼                                  ▼
          mdstack schedule decide --pool builder   mdstack schedule decide --pool reviewer
                    │        (one flock: schedule/lock)     │
                    └──────────────┬───────────────────────┘
                                   ▼
   snapshot ── demand (both pools) + priority + worker state + machine + presence
                                   │
   rank ────── finish-before-start classes, then milestone, critical path, age
                                   │
   budget ──── crew-wide target T (hysteresis, ramp limit) ≤ presence caps
                                   │                pool floors: one slot each
   decide ──── admit / defer / reclaim for the calling pool, each with reasons
                                   │
                     schedule/decisions.jsonl  +  one summary line
```

Each lead still spawns, delivers, restarts and reclaims its own workers. The
only change in a lead is that it asks `mdstack schedule decide` what to admit,
instead of running its own per-pool capacity check. The
decision is a deterministic function of files under `$CREW_STATE` and live
reads; it costs no model turn.

## Decisions

| Question | Decision | Alternatives considered | Section |
|---|---|---|---|
| Who decides (AC1) | One `mdstack schedule decide` function under a crew-wide file lock, called by each lead for its own pool. Each call computes the whole crew's plan and returns the caller's share; only the caller's grants are reserved, and the other pool's higher-ranked items hold budget for that call only | Per-lead admission (today): both leads spend the same machine budget twice and nothing ranks work across pools (F1, F2). The coordinator decides: model turns and tokens on every wake, and scheduling moved out of the coordinator for that reason. A third long-lived scheduler window: one more session to supervise and restart, for a decision a pure function can make | [Model](#model) |
| Unit of budget | A busy worker (a builder with a live harness that is not idle-retained, or a reviewer pass), cost 1 each | Per-suite cost: suites start and stop inside a worker, so admission cannot hold them to a count. Weighted cost per role: no data yet to set weights; revisit with metrics | [Model](#model) |
| Priority (AC3) | Finish before start: eight classes across both pools, then milestone order, critical path and age | First in, first out per pool (today, F2). One global first in, first out: a fill-in build queued early still beats a merge-up | [Priority](#priority) |
| Machine target (AC3) | A crew-wide target T that moves by one per interval between watermarks, with a ramp limit on starts | On/off gates (today, F1). Caps only (this profile's interim): surges to 503 stalls. A PID controller: tuning effort for a signal sampled once a minute | [Target](#target) |
| Starvation (AC3) | Every pool with demand and no busy worker may admit one, whatever T; freed slots go to the highest class crew-wide | A reserved share per pool: idles slots when one pool has no demand. Aging across classes: lets fill-in overtake finishing work | [Floors and starvation](#floors-and-starvation) |
| Overlap (AC3) | Owner decision 2026-11-03 (D + S9): builds run in parallel with no overlap sequencing; approved overlapping PRs land together in one train, and only a real conflict merges up | Sequence builds by declared footprint (S8, closed): under the standard flavor a merge-up loop (about 25 minutes) costs half a sequenced cycle (about 50 minutes), and builders stay independent. Per-path leases: needs every builder to declare paths before it starts editing. Model-predicted footprints: not observable or reproducible | [Overlap](#overlap) |
| Presence (AC3) | Presence sets the caps (#577); T never exceeds them. One set of watermarks | Separate present watermarks: no data yet that the owner needs a lower load target beyond lower caps | [Presence](#presence) |
| Unknown inputs | An unknown machine signal holds T (no growth, no shrink); an unknown demand read defers only that pool | Defer everything on any unknown (today): one failed probe stops the crew | [Inputs](#inputs) |
| Observability (AC4) | Every admit, defer and reclaim is a JSON line with reasons; the coordinator sees one summary line and a stuck alarm for finishing work only | A coordinator message per deferral: the wake noise #578 removes | [Observability](#observability) |

## Model

`mdstack schedule decide --pool builder|reviewer --project FILE` runs under
`$CREW_STATE/schedule/lock` (`fcntl.flock`). It reads one snapshot of the
[inputs](#inputs), ranks the whole crew's demand, and walks it in rank order,
granting a slot while all of these hold:

1. the item's pool has a free slot under its presence cap (`pool_cap`) and
   physical band;
2. the crew's busy workers plus reservations plus holds are below the
   target T;
3. the crew's starts in the current `schedule_interval`, plus holds, are
   fewer than `schedule_ramp` (default 2);
4. any optional hard ceiling (`max_suites`, `max_load`) is not exceeded.

A pool's [floor](#floors-and-starvation) waives conditions 2, 3 and 4 for
its top-ranked item. The first failed condition is the item's defer reason.

A suite wait waives only `max_suites`. When a counted builder's newest
status line is a typed `waiting: #<m> KIND id=<id>` with nothing after it,
the walk may admit `#<m>` past `max_suites` while every other condition
holds. The grant's reason is `suite-wait`, and its decision log line carries
the wait (`window`, `line`). This keeps a builder that holds a slot while it
waits on another item from blocking that item (#1950). No cap value changes.

Builder demand already running is skipped. When a busy builder works the
item's ref (the worker's `pr`, or any `#n` in its item), the walk neither
admits nor holds the item and does not count it against the cap, T or the
ramp limit; the busy worker is already counted. The item stays in demand
until its lead marks it done. Reviewer demand is never skipped this way: it
leaves the reviewer lead's inbox when its pass starts, and a busy reviewer
on the same PR is running another pass or round.

The walk treats the two pools differently, so that only the lead that will
spawn an item ever commits it:

- **Caller's item granted:** it becomes a reservation in
  `schedule/reservations.json` (ref, pool, time), returned in the call's
  JSON. A reservation counts as a busy worker of its own pool until a run
  record for that ref appears (`mdstack spawn` drops it once the run starts, so
  a run reaped before the next decision cannot revive it), the lead releases
  it after a spawn failure, or `reservation_ttl` (default 600 seconds)
  passes.
- **Other pool's item that would be granted:** it becomes a hold for the
  rest of this walk only. A hold counts against T and the ramp limit for
  lower-ranked items, so the caller cannot take budget that belongs to
  higher-ranked work in the other pool. It never takes a slot in the other
  pool, never suppresses that pool's floor and is never written down: each
  call recomputes holds from live demand. The other lead's next call grants
  the item itself, through the same walk. When a walk produces a hold, the
  call nudges the owning lead through its existing backstop wake, so the item
  is claimed without waiting for the next tick. A hold for a pool whose lead
  probes `dead`, `missing` or `ambiguous` is dropped and recorded as
  `lead-down`, so a stopped lead cannot freeze the other pool.

Example: caps builder 1 and reviewer 1, T = 2, nothing busy, one review and
one build queued. If the builder lead calls first, the review (class 5) ranks
above the build (class 7) and becomes a hold, and the build is granted and
reserved. The reviewer lead then finds its own slot free and grants the
review. If the reviewer lead calls first, it reserves the review and the
build becomes a hold that blocks nothing; the builder lead then grants the
build. Repeated builder calls never reserve the review. With T = 1, each pool
still starts its item through its floor.

Reclaim keeps today's rules: idle-retained builders are reclaimed when a
granted build needs a physical band slot, or after `idle_builder_ttl`; a
terminal reviewer pass is reclaimed before its successor is admitted. The
scheduler never stops a busy worker. When T falls below the busy count, it
admits nothing until workers finish.

## Inputs

All inputs are observable from files under `$CREW_STATE`, the process table
or a live tracker read. None is a model judgement.

| Input | Source | Unknown |
|---|---|---|
| Builder demand: build, fix, ci-red, merge-up | Builder lead's pending inbox ids (`lead.pending`) and `spawn-queue.jsonl`, by kind | Defer the builder pool; record `demand-unreadable` |
| Reviewer demand: review, validate, recheck | Reviewer lead's pending inbox ids and the `work` event files they name | Defer the reviewer pool; record `demand-unreadable` |
| In-flight work | Run records with live identity ([C5](runtimes/tmux.md#q7-failure)), reservations, open trains in `trains/` | Count the run as busy |
| Lands | Synthesizer inbox and open trains | Not admitted by the scheduler: a land is never deferred, and the serial land lock is unchanged |
| Holds | Open issues and PRs labelled `crew:hold` (whatever the deprecated `hold_label_blocks` says, #1124), plus open PRs that close a held issue (#712) | Defer the caller's pool; record `holds-unreadable`. A blocking label that cannot be read never counts as eligible. The summary shows `held unknown` |
| Milestone order | The item's milestone, open milestones in order, `max_active_milestones` (#566) | Treat as the latest active milestone |
| Critical path | `Depends on #n` lines in open issue bodies ([§2](protocol.md#2-stages) item bodies): the number of open items that wait on this one, directly or transitively | Zero |
| Distance to landing | The demand kind (its [class](#priority)) | — |
| Red default-branch fixes | Open issues whose title starts with `main-red`: the coordinator's blocking fix issue after `blocked: main red` ([land rules](protocol.md#land-rules-and-merge-trains)). Their builds, and fix or ci-red rounds on a PR whose run record names the issue, rank class 1 | None: the fix ranks by its kind |
| Worker state | Busy: live harness and not idle (`idle_builder`). Idle-retained: last status `done:`, no pending inbox, no live child. Orphaned: a live tool process with no run record, or a run whose item is closed (already excluded by `mdstack lead suites`) | Busy |
| Normalized load | `os.getloadavg()[0] / os.cpu_count()` | Hold T |
| Memory pressure | macOS: `sysctl kern.memorystatus_vm_pressure_level` (1 normal, 2 warn, 4 critical). Linux: `/proc/pressure/memory` `some avg10` against two thresholds. The snapshot's `memory_high` is the effective [memory threshold](#memory-threshold) | Hold T |
| Local suites | `mdstack lead suites` (live tool sessions across both pools) | Recorded only; used by the optional `max_suites` ceiling |
| Gateway errors | Lines in `schedule/errors.jsonl`: HTTP 429 or 5xx and rate-limit text seen by crew scripts (`train_transient` already classifies them) and by the liveness probe matching a harness adapter's declared transient-error text on the pane it already captures | Zero |
| Owner presence | `pool_cap`: present limits, recorded away mode, quiet, the away `--cap` (#577, #198) | Unreadable away state blocks admission until reconciled, as today |

The snapshot, with every input's value or `unknown`, is written once per
decision as the first line of that decision's records, so each defer can be
traced to the numbers behind it.

## Policy

### Priority

Demand from both pools is ranked in one list. Class first:

| Class | Kind | Pool | Why here |
|---|---|---|---|
| 1 | Fix for a red default branch | builder | Blocks every land |
| 2 | Recheck after a merge-up | reviewer | One pass from landing |
| 3 | Merge-up of an approved PR | builder | Approved; only the conflict stands between it and landing |
| 4 | Validation | reviewer | Review passed |
| 5 | Review of a new head | reviewer | A PR exists and waits on a verdict |
| 6 | Fix or ci-red round | builder | A PR exists and waits on its builder |
| 7 | New build in the earliest active milestone | builder | Start work |
| 8 | Fill-in build from a later active milestone | builder | Uses capacity the earlier milestone cannot use |

Lands are not in the list: they never wait on the scheduler. Within a class,
ties break by milestone order, then by critical path (more items waiting
first), then by age (oldest first). A class 8 build is admitted only when no
class 7 build is eligible, which is #566's rule stated as an admission order.
Holds, escalations, solo lanes and stale heads are filtered out before
ranking, exactly as the leads do today. A pending handoff whose issue or PR
is held is never granted and is not demand: `decide` returns it under
`held` and the summary counts it. Its inbox id stays pending, so when the
hold lifts the next decision ranks it again with no new handoff. A handoff
the lead already marked `done:` is never reused: re-sending the same kind and
refs starts a new handoff (#712).

### Target

T is the crew-wide number of busy workers the machine should carry. Its
ceiling is the sum of both pools' presence caps; its floor is 1. It starts at
the busy count when the scheduler first runs, so a restart causes no surge.

Each signal is `high`, `low` or in between, with separate enter and exit
thresholds:

| Signal | High at | Low below | Default basis |
|---|---|---|---|
| Normalized load | `load_high`, default 6.0 per CPU | `load_low`, default 4.0 per CPU | 2026-11-02 on 16 CPUs: 503 stalls at 110–170 (7–10 per CPU); healthy work at about 60 (under 4 per CPU) |
| Memory pressure | macOS: the [memory threshold](#memory-threshold) level or above. Linux: `some avg10` 10.0 at `warn`, 40.0 at `critical` | macOS: below the threshold. Linux: `some avg10` under 1.0 | The OS's own levels. Linux 40.0: some task stalled on memory for 40% of the last 10 seconds, sustained thrashing |
| Gateway errors | `error_high`, default 3 in the last 10 minutes | none in the last 10 minutes | Stalls arrive in bursts |

At most once per `schedule_interval` (default 120 seconds, longer than the
one-minute load average's lag):

- any signal high: T = max(1, min(T, busy) − 1);
- every signal low and demand waiting: T = min(ceiling, T + 1);
- otherwise T holds.

Between the thresholds nothing changes, so a load hovering at one value does
not flap admission. The ramp limit (`schedule_ramp` starts per interval)
stops the burst of 5–6 simultaneous starts that the lagging load average
cannot see. T and its last change time live in `schedule/target.json`.

#### Memory threshold

The memory threshold is `warn` or `critical` (#1282). The
`runtime.options.memory_high` profile option sets it. Unset, it follows the
speed mode:

- **Full speed**, every pool's effective cap equal to its full cap (recorded
  away mode, or present caps equal to `builders` and `reviewers`):
  `critical`. macOS `warn` counts as low, so T can grow while load and errors
  are low.
- **Light mode**, any effective cap below its full cap (a present cap or an
  away `--cap`): `warn`, so `warn` and above count as high.

With caps unreadable and no option set, the threshold and the memory signal
are `unknown` and T holds. The snapshot records the threshold as
`memory_high`, and the [summary](#observability) shows it after the memory
value, as in `mem warn (high at critical)` or `mem psi 2.5 (high at psi 40.0)`.

### Floors and starvation

A pool with eligible demand and no busy worker or reservation may admit its
top-ranked item even when T is reached, a signal is high, the ramp limit is
spent or an optional ceiling is exceeded, as the empty reviewer pool does
today. With a pool cap of at least 1, that makes reviewer starvation
impossible: builder suites can slow reviews but not stop them. Above the
floors, every freed slot goes to the highest-ranked item crew-wide, so
finishing work (classes 1–6) takes freed slots before new builds. The only
stop a floor does not pass is a pool cap of 0, which the away `--cap` can
produce when other runs use the whole bound.

### Overlap

Admission never gates on overlap (owner decision 2026-11-03, D + S9). Builds
run in parallel whatever paths they touch, and items carry no declared
footprint. Overlap is handled at landing instead.

For approved PRs, `train_compose` keeps overlapping members in dependency
then approval order and merges each onto the train branch in turn, dropping
a member only when its merge actually conflicts. Train CI tests the combined result, as for any
train, so the land gate is unchanged; overlapping PRs that merge cleanly
land in one train instead of one merge-up each.

### Presence

Presence changes the caps and nothing else: `pool_cap` (present, away,
quiet, away `--cap`) bounds each pool and so the ceiling of T. Entering away
mode raises the ceiling, and T climbs one per interval while the machine
signals stay low; leaving it lowers the ceiling at once, and busy workers
drain naturally. This keeps #577's contract: never kill a running worker to
meet a lower cap.

## Observability

Each decision appends JSON lines to `schedule/decisions-<yyyymmdd>.jsonl`
(UTC day, 7 days kept). The files live under `schedule/`, never under
`runs/`, which `mdstack watch` reads as run records.

- One `snapshot` line: every input value, T, the ceiling and the caps.
- One line per admit, defer or reclaim: `{"pool", "action", "ref", "kind",
  "class", "reasons": [...]}`. A defer repeated with the same reasons on the
  next decision is not written again; a change of reason is.

`mdstack schedule summary` prints one line from the latest decision, for
example:

```text
schedule: builders 4/6 reviewers 3/8 target 8 (load 5.1/cpu mem normal (high at critical) errors 0) queued merge-up 1 fix 1 build 5; deferred 5 (overlap 2, target 3); held 1 #639; orphans 0; terminal 0
```

The watcher attaches the latest summary to every coordinator wake it already
sends. Deferrals never wake the coordinator. One alarm does: finishing work
(classes 1–6) deferred for longer than `stuck_after` (default 1800 seconds)
sends one `schedule-stuck` wake with the item, its reasons and the snapshot,
deduplicated like today's identical block reports. Orphan processes are
listed in the summary with their process ids for the coordinator to clean up,
and `terminal` counts and names reviewers that wrote their final `done:` but
still hold a slot (#719);
the scheduler never kills an unrecorded process.

## What this subsumes

| Item | Role in this design |
|---|---|
| #572 / #586 idle builders hold slots | Input, kept as built: idle-retained builders are not busy; reclaim rules unchanged |
| #577 / #582 presence caps | Input, kept as built: `pool_cap` sets each pool's bound and T's ceiling |
| [#598](https://github.com/mw-ding/mdstack/issues/598) dequeue uses the full cap | Precondition: dequeue and the scheduler must read the same `pool_cap` |
| #566 two-milestone rule | Input: classes 7 and 8 and the milestone tie-break |
| [#578](https://github.com/mw-ding/mdstack/issues/578) wake noise | Shares the summary line and the rule that deferrals never wake the coordinator |
| `max_suites` (#573), default `cpus // 4` | Subsumed: no longer a default gate. Kept as an optional owner ceiling, unset by default |
| Hard-coded load gate `load >= cpus` | Subsumed: replaced by the load watermarks of [Target](#target). An optional `max_load` ceiling replaces it for owners who want a hard stop above the floors |
| Empty reviewer pool keeps one slot | Generalized: the floor applies to both pools |
| #587's original admission ACs (caps-only default, optional gates) | Build issue S1, the first step: it stops the current zero-admission state before the scheduler exists |

## Team admission

Built by #1857 (M56 T2, [team §9.4](specs/team.md#94-admission-and-shared-pools)).
A [team file](configuration/team-files.md) referenced as `FILE#<repo>` admits
through one scheduler for all its repos. A one-repo `config.toml` is its own
singleton team: its `schedule/` stays in its repo state, and its decisions,
outputs and reservations are unchanged.

- **One lock, target and ledger.** `schedule/` sits at the team root
  (`<state_dir>/<team>/`), so two repos' leads deciding at once serialize on
  one lock and never over-admit the last slot. Each repo's `errors.jsonl`
  stays in its repo state and counts once.
- **Every repo counted once.** The snapshot reads each repo's run records,
  suites and orphans into team totals, and each repo's demand, tracker,
  holds, ownership and pause under `repos`. Pool caps, presence, T, the ramp
  limit, ceilings and [floors](#floors-and-starvation) apply once to team
  totals: a floor belongs to the team pool, not to a repo.
- **Per-repo eligibility.** A repo's demand in a pool is left out, and
  recorded under `blocked`, when its ownership does not permit starting
  work (`ownership-<mode>`), it is `paused`, its holds or tracker are
  unreadable (`holds-unreadable`, `tracker-unreadable`) or that pool's
  demand is unreadable (`demand-unreadable`). Its running workers still
  count. Another repo stays eligible. A team repo's `crew:escalated` items
  are held like `crew:hold` ones, each read through that repo's
  `repo.labels`. Within an eligible repo each item must also pass, read
  positively in its own repo: not held or escalated (`held`); every PR pass
  (each kind but a build) names a readable head (`head-unreadable`) equal to
  its open PR's live head (`heads-unreadable`, `stale-head`); a build's local
  `Depends on` issues are closed (`depends-open`). An unknown input refuses like a
  mismatch, only that item is refused, and it takes no reservation; decide
  lists such items under `waiting` with the reason. An acknowledged wait
  whose ref is unchanged (`lead.parked`, #1836) is not demand, so one repo's
  parked waits never take another's budget.
- **Unknown shared state refuses.** Unreadable caps, workers (a repo that
  does not resolve included) or ledger defer every team decision as
  `caps-unreadable`, `workers-unreadable` or `reservations-unreadable`. An
  unreadable ledger is never rewritten or read as zero busy work; this holds
  for a one-repo config too.
- **Local ranking, team order.** Each repo's demand is classed against its
  own tracker: milestone order (`repo.milestones` when set), `Depends on`
  critical paths and `main-red` fixes stay local. Class 7 is each repo's
  earliest active milestone, and a class 8 build runs only when no class 7
  build in the team is eligible: while one has not started, a class 8 build
  defers as `class-7`, even with a free slot. Within a class, ties break by
  milestone order, critical path and age, then canonical repo, ref and kind.
  A red default branch in A ranks A's fix class 1 and leaves B's work and
  lands alone.
- **Caller lane.** A decision grants and reserves only the caller's lane,
  its `(repo, pool)`. Another lane's would-be grants hold budget for that
  walk only, as the other pool's do, and wake that lane's lead; a lane whose
  lead is down is dropped as `lead-down`.
- **Qualified reservations.** A team reservation records `repo`, `project`,
  `kind` and `round` beside `ref`, `pool` and `time`. It matches by repo,
  pool and ref, and a reviewer pass's kind and round. So A's `#7` and B's
  `#7`, or one PR's review and validation, are separate grants. The reviewer
  lead starts a pass only on a grant of that pass and round, so a validation
  grant never starts a review. It transfers only to a run of that repo (and
  reviewer pass and round), and `mdstack spawn` and `mdstack schedule
  release` drop only the caller repo's grant.
- **Observability.** Team outputs are additive: every action and `held`
  entry names its `repo`, and team actions also carry `project`; decide
  adds `team`, `repo`, `blocked` and `waiting`; release adds `repo`. The decision log
  records `block` lines. `deferred.json` keys a team defer as `<repo> #<n>`.
  The summary lists unread demand per repo and ends with `blocked <repo>
  <pool> <reason>`. A team watcher reads the team summary and raises
  `schedule-stuck` only for its own repo.

The shared `(team, pool)` lead (#1858) decides for each message's repo,
passing its `context.project`, so its root inbox counts as demand only for
the repo each message names, through the same predicates and one ledger.

## Build issues

Proposed follow-ups for the coordinator to file, about 100 lines each plus
tests, in dependency order. Each adds its own CHANGELOG fragment.

| ID | Scope | Depends on |
|---|---|---|
| S1 | Caps-only default admission: remove the hard-coded load gate from `lead.admission`; `max_suites` default unset; new optional `max_load` (positive number, compared with the one-minute load); unknown observations defer only when a configured gate needs them; tmux.md, profile.md and both lead briefs; tests for high load and running suites with no gate, and each gate deferring | — |
| S2 | `mdstack schedule snapshot`: read every [input](#inputs) into one JSON object with `unknown` values; memory pressure on macOS and Linux; tests with fixture state dirs | #598 |
| S3 | Gateway error record: append HTTP 429/5xx and rate-limit failures from crew scripts and adapter-declared pane text to `schedule/errors.jsonl`; add the transient-error text field to [harness adapters](runtimes/harness-adapters.md); tests | S2 |
| S4 | Ranking: the eight classes and tie-breaks as a pure function over the snapshot, including `Depends on` critical-path counts; tests per class and tie-break | S2 |
| S5 | Target: watermarks, interval, ramp limit, `target.json`; profile options `load_high`, `load_low`, `error_high`, `schedule_interval`, `schedule_ramp` with validator rules and profile.md rows; tests for hold, grow, shrink and no flapping | S2 |
| S6 | `mdstack schedule decide` with caller-only reservations, cross-pool holds, floors and the decision log; the builder lead calls it instead of `mdstack lead capacity`; builder-lead brief (mirror); tests for both call orders, repeated calls by one lead, the other lead down, reservation expiry and floors | S4, S5 |
| S7 | Reviewer lead on `mdstack schedule decide` instead of `reviewer-pool` capacity; reviewer-lead brief (mirror); tests for reviewer floor under builder load and for a review held by a builder call being granted on the next reviewer call | S6 |
| S8 | Overlap-aware dispatch from declared footprints. Closed unbuilt by the owner's 2026-11-03 [overlap](#overlap) decision | S6 |
| S9 | Overlap trains: `train_compose` keeps clean overlapping members and drops only on conflict; synthesizer brief (mirror); tests | — |
| S10 | `mdstack schedule summary`, the watcher attaching it, and the `schedule-stuck` alarm; coordinate with #578; tests | S6, #578 |
| S11 | Docs consolidation: tmux.md [Scaling policy inputs](runtimes/tmux.md#scaling-policy-inputs), Q6 and both lead sections point here as built; remove `mdstack lead capacity` once no brief calls it | S7, S10 |

S1 and S9 are independent of the rest and can start first. S6 is the switch:
before it, leads admit as today; after it, the builder pool follows the
scheduler while the reviewer pool keeps its own check until S7.

## Out of scope

- Placement across hosts: [multi-device](runtimes/multi-device.md) places
  one run on a host; this design decides whether to start it. A multi-host
  crew needs per-host machine signals, left to that design's build issues.
- The Grok Bot runtime: its routines have no worker pools to admit.
- Engine and quota routing ([roles](roles.md#quota-routing)): the scheduler
  decides when, not which engine.
- Lands, merge gates, round caps, holds and the synthesizer's serial land:
  unchanged.
- Killing busy workers or unrecorded processes to meet a target.
