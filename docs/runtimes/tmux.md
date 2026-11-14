# tmux runtime binding

Binding for a local tmux crew (portable mdstack), designed in roadmap 14.1
([#130](https://github.com/mw-ding/eng-crew/issues/130)) and shipped in M14
and M14.1. It answers the
runtime questions #110 left open (Q1, Q2, Q3, Q5, Q6, Q7) and maps the
[runtime contract](README.md#contract) to tmux mechanisms. The `crew` CLI
landed in M14 (14.2–14.9 and 14.11, #131–#138 and #172) and was hardened in
M14.1 (14.1a–14.1k); [Usage](#usage) covers it. It
adds no rule, gate, cap, marker field or label; the [protocol](../protocol.md) still owns them,
and GitHub stays the tool of record (invariant I5).

M54's additive brief/ack, review/verdict/recheck and owned merge-up helpers,
plus coordinator scratch cleanup, are built in source
(PRs #1834, #1838, #1837 and #1831). [M54 status](../specs/portable.md#m54-coordinator-helper-surfaces)
records evidence and integrated brief budgets. These landed after the
7.12.0 cut; this binding makes no live deployment claim.

## Decisions

| #110 question | Decision | Section |
|---|---|---|
| Q1 wake model | Status files, inbox nudges and `mdstack poll` feed one zero-token watcher; it routes mechanical wakes before its exit wakes the coordinator; a turn-end guard keeps it armed | [Q1](#q1-wake) |
| Q2 session lifetime | Coordinator and synthesizer for the session; builder window per issue; reviewer and validator windows per pass | [Q2](#q2-lifetime) |
| Q3 coordinator engine | Claude Code or Codex, chosen by profile; role engines by tier routing | [Q3](#q3-coordinator-engine) |
| Q5 identities | Per-role identity from the profile, token derived inside the window at launch; single-identity rule from #111 | [Q5](#q5-identities) |
| Q6 concurrency | Per-band caps, default 5 busy builders and 2 reviewer passes; serial land under `flock` | [Q6](#q6-concurrency) |
| Q7 failure | Liveness probe from tmux that matches the run identity recorded at spawn (pane id, pane pid and that process's start time), plus watcher stale timers; restart only on `dead` / `missing` / `quota` (on the next eligible engine), plus one synthesizer respawn after a failed nudge | [Q7](#q7-failure) |
| Worktree root, cleanup and provider (#316) | One root, `paths.worktree_root`, for every local run (`<n>-<sha7>-<role>-<pass>/`) in both runtimes; lifecycle reaping stays, plus the merged-only, dry-run-first [mdstack gc](#mdstack-gc) backstop; Git stays the only provider (treehouse considered, deferred) | [mdstack gc](#mdstack-gc) |

## Layout and naming

One tmux session per repo, `crew-<owner>-<repo>`. One window (tab) per
running agent, never several agents in one window. Index bands keep roles
grouped and stable:

| Index | Window name | Role | Lifetime |
|---|---|---|---|
| 0 | `ash`, or `ash-<team>` with `identities.team` set | Coordinator | Session |
| 1 | `sam` | Synthesizer | Session; idle between lands |
| 2 | `ben-lead` | Builder lead | Session; owns builder scheduling and lifecycle |
| 10–19 | `ben-<issue>` | Builder | One per issue; fix rounds reuse it; closed with its worktree on merge, close or escalation |
| 20–29 | `vera-<pr>-r<k>-review`, `vera-<pr>-r<k>-validate`, `vera-<pr>-r<k>-recheck` | Reviewer-validator | One pass each, fresh session; closed after its status line |
| 40–44 | `riley-<issue>` | Researcher | One research request each, fresh session; closed by `mdstack route` after its `done:` ([roles.md](../roles.md#researcher-riley)) |
| 30 | `crew-status` | Optional dashboard | Runs `mdstack status` on a loop: role, item, head SHA, last status, liveness |

Window names are the profile's role display names; the defaults are shown.
With `identities.team` set (`mdp-m4`), window 0 is `ash-mdp-m4`; every command
resolves it from the profile, and `mdstack attach ash` and `mdstack send ash`
still reach it (#1329).
`mdstack spawn` takes the next free index in the role's band. The owner watches
or types by attaching (`mdstack attach <window>`, read-only by default);
`mdstack attach builders` opens a temporary tiled view without changing the
layout (#138).

Runtime state lives under `<state-dir>/<owner>__<repo>/`, never only in a pane:

| Path | Holds |
|---|---|
| `render/` | Rendered coordinator and role briefs (#131, #137) |
| `runs/<window>.json` | Run record: index, role, item, worktree, engine, expected harness, start time, run identity (pane id, pane pid and that process's start time), spawn arguments, restart count |
| `runs/<window>.body.md` | Scratch body a role writes for a `gh` `--body-file` (`$CREW_STATE/runs/$CREW_ID.body.md`, never `/tmp`; the briefs say so, #270); `mdstack kill` deletes it with the record. The coordinator deletes `runs/coordinator.body.md` after posting. Plain `mdstack down` also sweeps regular `runs/coordinator.*` scratch files after a successful stop, including when nothing is running; symlinks, `--preserve` and refusals retain them |
| `inbox/<window>.jsonl` | Messages to a window, one JSON line each, with a `msg-id` |
| `leads/builder.json`, `leads/builder.brief.md` | Builder lead identity/restart record and brief; separate from worker runs |
| `leads/builder-events/` | Durable event files referenced by the lead's inbox; retained while work is pending |
| `status/<window>.status` | Append-only status lines from a window (`$CREW_STATUS`) |
| `wake/queue.jsonl` | Durable wake queue the coordinator drains each turn (`mdstack drain`) |
| `pause.json` | The project pause barrier ([mdstack pause](#mdstack-pause)): `at`, `reason`, `state` (`pausing` or `paused`) and the `stopped` runs; dispatch, land and cleanup refuse while it exists or is unreadable, and [mdstack resume](#mdstack-resume) removes it |
| `wake/queue.lock` | Lock held around each queue append and `mdstack drain`'s rename |
| `wake/watcher.pid` | PID of the armed watcher; the turn-end guard reads it |
| `wake/watcher.lock` | Held (flock) by the one live watcher for its whole life, re-execs included (#399) |
| `wake/watcher.log` | Output of the persistent watcher `mdstack up` starts (#1346) |
| `poll-state.json` | Last GitHub state seen by `mdstack poll` |
| `claims/` | Claim files per [protocol §6](../protocol.md#6-duties-on-wake-all-roles) step 2 |
| `spawn-queue.jsonl` | Spawn requests refused by a cap |
| `locks/merge.lock` | Land lock |
| `trains/train-<n>.json` | Merge train: base, train SHA, members (head, train commit), dropped PRs, train PR, CI result and run links, landed and stopped PRs ([mdstack train](#mdstack-train)) |
| `trains/delegated-<n>.json` | Delegated train build: reserved number, base, member heads, `after`, `synthesizer` window and `closed` ([mdstack train](#mdstack-train)) |

Profile paths ([`[paths]`](../profile.md#paths)): `<state-dir>` is
`paths.state_dir` and `<worktree-root>` is `paths.worktree_root`.
`<mdstack>` is `paths.mdstack` (#244), the absolute path of the mdstack
checkout, so rendered briefs cite its docs and scripts (`<mdstack>/docs/`)
from any repo.

### Home-level layout (#1178)

The default layout keeps every installed piece in one place, `~/.mdstack/`,
with only the repo checkout outside it (#1316). Every crew path sits under
one movable root (`paths.root = "~/.mdstack"`):

| Path | `[paths]` key | Holds |
|---|---|---|
| `~/.mdstack/` | `root`; the profile's directory | `config.toml`, the `start` and `start-owner` wrappers, `releases/mdstack-X.Y.Z/` bundles with the `releases/current` link, and the `bin/mdstack` launcher ([mdstack install](#mdstack-install)); the coordinator and leads start here, and it is not a git checkout |
| `~/.mdstack/state/` | `state_dir = "state"` | `<owner>__<repo>/` state, including the install link `mdstack` |
| `~/.mdstack/runs/<repo>/` | `worktree_root = "runs/<repo>"` | Role worktrees |
| `~/.mdstack/live/` | `live_dir = "live"` | The deployed live copy, when one is used |
| `~/<repo>/` | `checkout = "~/<repo>"` | The repo checkout role worktrees and trains come from; the owner's session runs here (`~/.mdstack/start-owner`). The only thing outside the root |

```toml
[paths]
root = "~/.mdstack"
state_dir = "state"
worktree_root = "runs/widgets"
live_dir = "live"
mdstack = "state/acme__widgets/mdstack"
checkout = "~/widgets"
```

`profiles/tmux.toml` ships this block as its default, with `<owner>` and
`<repo>` taking the `[repo]` owner and name at resolve, and
`mdstack bootstrap` proposes it with your repo filled in. With `paths.root`
set, each relative `state_dir`, `worktree_root`, `live_dir`, `mdstack` and
`checkout` resolves under it; absolute and `~` values stay as they are. A set
`CREW_ROOT` overrides `paths.root`, so a later move of the whole layout
changes one value; moving the files is
[mdstack migrate](#mdstack-migrate)'s job. Without `paths.root` every value
resolves as before. Doctor and bootstrap accept a profile directory that
also holds `state/`, `runs/` and `live/`, and refuse a `state_dir` or
`worktree_root` inside a git checkout. `mdstack layout` prints the resolved
layout and writes the start wrappers ([mdstack layout](#mdstack-layout)).

### User-level and project-level config (#1316)

Every command takes its profile from the first of (#1324):

1. `--project FILE`;
2. `$CREW_PROJECT`, which every role window sets to its own crew's file;
3. `$MDSTACK_CONFIG`;
4. the user-level `<root>/config.toml`, where root is `$CREW_ROOT`, else
   `~/.mdstack`.

An explicitly named file always wins over the user-level default, and the
two never merge. Every command that can write (`bootstrap`, `upgrade`,
`up`, `spawn`, `action` and the rest) prints the file it acts under on
stderr as `mdstack: config <path>`.

- **User-level (the default).** `~/.mdstack/config.toml` is the owner's own
  install: one repo, or a [team file](../configuration/team-files.md) for
  several. Commands need no `--project`.
- **Project-level (secondary).** A project or project group that needs its
  own stack keeps its own `config.toml`, for example beside a group's
  checkouts, and passes it with `--project FILE` (or `MDSTACK_CONFIG`). It is
  a separate crew: its own `[repo]`, identities, `[paths]` and session. Its
  state must still live outside every git checkout.

#### A second root on one machine (#1324)

Two independent crews, each with its own pinned release, config, state and
identities, can share one machine with one root each. `~/.mdstack` is only
the default root. A second crew sets `CREW_ROOT=<root>`, or its own
`paths.root`, and gets the same layout under it: `<root>/config.toml`, its
state, `releases/` and `bin/` launcher. Bootstrap's proposal writes that root.
Run its bundle's `mdstack install --name <name>` so its launcher,
`<root>/bin/<name>`, links onto `PATH` under a name of its own and never
replaces the first root's `mdstack`. Its `upgrade` and rollback fetch into
its own `releases/` and flip only its own `current`. A command run for it
without `--project` needs `CREW_ROOT` or `MDSTACK_CONFIG` set; with neither
set it acts under the first root's config, and prints that path.

The two files never merge: the chosen file is the `project` layer of
[layers and precedence](../profile.md#layers-and-precedence), on top of the
shipped default and any org pack. Owner-wide choices (paths, identities,
engines, merge grant) belong in the user-level file; a project-group stack
repeats what it needs in its own file.

## Harness adapters and session backends

Supported here means `mdstack` uses the adapter or backend today; it claims
no support for an undeclared one (roadmap 15.6, #179).

| Interface | Supported | Limits / gaps |
|---|---|---|
| [Claude Code adapter](harness-adapters.md#claude-code-claude-code) | `claude-code` for role sessions and the coordinator | Launch, dialogs, wake recipe, idle detection and foreground process are declared by the adapter; the default backup nudge can add an empty coordinator turn (C1 below). |
| [Codex adapter](harness-adapters.md#codex-codex) | `codex` for role sessions; partial for the coordinator | The watcher types the coordinator wake line and the notify recipe works on codex-cli 0.164.0 (#170), but `mdstack up` does not install it ([mdstack guard](#mdstack-guard)); C1 gap below. |
| [Cursor adapter](harness-adapters.md#cursor-cursor) | `cursor` for role sessions and the coordinator, subject to engine policy | Only bypass mode; no effort flag or installed turn-end hook. Trust/login screen detection and live wake timing are unverified; C1/C5 gaps below. |
| [tmux backend](session-backends.md#tmux-tmux) | `tmux` through `environments/terminal/sessions/tmux/adapter.py` | Declares all six operations: create, attach, doorbell, identity probe, state read and kill. C5 compares pane id, pid and start time; C6 checks unlanded work before teardown. |
| [herdr backend](session-backends.md#herdr-herdr) | Local default server through `environments/terminal/sessions/herdr/adapter.py`, selected by `runtime.options.session_backend` | Background workspace per run; no backend hook dependency. Screen-only composer checks, no activity timestamp, no private coordinator environment or tiled attach; see the contract gaps below. |

`mdstack spawn` skips other engines in the tier order. Engine tier routing alone does
not declare adapter support.

## Runtime contract

How tmux meets each capability, with gaps in the
[gap format](README.md#gap-declaration). Mechanisms only; no rule changes.

| Capability | How tmux meets it | Gap |
|---|---|---|
| C1 Wake on event | Watcher blocks on status files, stale timers and `mdstack poll`; it applies mechanical routes before its exit re-invokes the coordinator for judgement, which routes retained wakes by `mdstack send` or `mdstack spawn`; turn-end guard blocks an idle coordinator with no armed watcher ([Q1](#q1-wake)); waiting is token-free: the watcher and `mdstack poll` are plain scripts, and the backstop doubles per idle wake while no run is recorded, capped at 16 × `--backstop` ([mdstack watch](#mdstack-watch)) | C1 wake on event: partial, compensated by `mdstack poll` diffing against `poll-state.json` and the §6 step 3 sweep on the first wake after the machine resumes; residual risk: no work moves while the machine sleeps or the tmux server is down<br>C1 wake on event (waiting cost): partial, compensated by `--no-nudge` for a coordinator whose exit wake works ([mdstack watch](#mdstack-watch)); residual risk: with the default nudge, kept so that no single harness feature is the only wake path ([#160](https://github.com/mw-ding/eng-crew/issues/160) row 4), a Claude Code coordinator may take a second, empty turn per wake<br>C1 wake on event (Codex turn-end guard): partial, compensated by the watcher's typed wake and the documented [notify recipe](#mdstack-guard); residual risk: `mdstack up` does not install that recipe (verified on codex-cli 0.164.0, #170), so a Codex coordinator without it that ends a turn without re-arming the watcher can idle blind<br>C1 wake on event (Pi): partial, compensated by the watcher's typed wake ([Pi adapter](harness-adapters.md#pi-pi)); residual risk: live wake timing is unverified and no turn-end guard extension is installed, so ending without re-arming the watcher can idle blind<br>C1 wake on event (Cursor): partial, compensated by the watcher's typed wake ([Cursor adapter](harness-adapters.md#cursor-cursor)); residual risk: live timing is unverified and no turn-end hook is installed, so ending without re-arming the watcher can idle blind |
| C2 One consumer per event | `mdstack poll`'s decision function maps each GitHub change to one consumer ([protocol §8](../protocol.md#8-safety)); each wake record names one window; terminal `pr-merged` is handled by `mdstack route`; `pr-closed` goes to the coordinator, which runs `mdstack kill`, so the Grok Bot two-watch exception is not needed | None |
| C3 Messages by reference, proof of delivery | `mdstack send` appends refs only (issue, PR, full SHA, link, path) to `inbox/<window>.jsonl`, then types a fixed nudge `inbox: <msg-id>` and confirms it left the composer (exit 4 if not, or if a dialog is on screen, when nothing is typed; that id is then recorded in `inbox/<window>.undelivered`, and `mdstack upgrade` waits until the window acks it or the operator clears it); delivery is proven only by `ack: <msg-id>` in the window's status file; no ack in the profile timeout → one re-nudge, then a liveness check; lifecycle goes through `mdstack kill` and spawn, never message text | None |
| C4 Status protocol | One line per event in `status/<window>.status`: `ack:`, `done:`, `blocked:`, `paused:`, `failed:`, each with refs; the matching GitHub marker stays the record; a window that exits with no `done:` / `failed:` is `missing` or `dead` under C5 | None |
| C5 Liveness | Probe from tmux and `ps`, not the agent: window present, run identity (`#{pane_id}`, `#{pane_pid}` and that process's start time) vs the run record, `#{pane_dead}`, then `#{pane_current_command}` and the pane's foreground process names vs the run record's expected harness ([Q7](#q7-failure)); a different pane id, pid or start time is `missing`, never `alive`, and a failed probe or adapter dialog is `ambiguous` | C5 liveness (Pi extension dialogs): partial, compensated by `--approve` avoiding built-in project trust and disabling extensions that prompt before unattended dispatch; residual risk: custom extension dialogs are not recognized and may probe alive<br>C5 liveness (Cursor dialogs): partial, compensated by authenticating and accepting workspace trust once with the owner attached before unattended dispatch; residual risk: Cursor-specific login/trust dialogs are not recognized and may probe alive |
| C6 Isolation | `mdstack spawn` creates a unique worktree from a fresh base and refuses the main checkout, a branch-named path or an existing path; `mdstack kill` removes that run's worktree, build output and state files only ([Spawn and kill](#spawn-and-kill)), and only when its unlanded-work check (uncommitted or untracked paths; commits not on a fresh fetch of the default branch, the run's branch or `refs/pull/<n>/head`; a failed check counts as unlanded) finds nothing, or after `--discard --reason` posts the owner's reason and that list on the run's PR or issue; otherwise it keeps them and exits 1 ([mdstack kill](#mdstack-kill), #172). `mdstack down` and `mdstack restart` keep unlanded worktrees the same way | None |
| C7 Serial land | `sam` takes `flock` on `locks/merge.lock` before the [§7](../protocol.md#7-merge-gate-synthesizer) re-check and holds it through the head-bound squash and the merge post; `mdstack down` refuses while it is held. With an [asynchronous land](../interfaces.md#asynchronous-land-design), `sam` holds it until the terminal land status and the merge post | C7 serial land (async backend with `land.serializes = true`): partial, compensated by the backend's declared serialization, which lands one change per repo at a time on the tip the previous land left, and by `mdstack land`'s head-pinned request and intent read-back; residual risk: `sam` takes no local lock, so serialization rests on the backend's declaration |
| C8 Owner channel and SLA | Coordinator's terminal (`ash`) plus the matching GitHub post; roles send asks as `blocked:` lines, never to the owner in their own window; the coordinator writes each open ask's §6 auto-apply time to `asks/<n>.json` (`{"deadline": ...}`, ISO 8601 with its UTC offset) and deletes it when the ask closes; the deadline only wakes the coordinator to apply a permitted §6 default, so elapsed time supplies no merge-ok and a merge still needs the repository's covering recorded grant or the owner's per-PR merge-ok, plus every applicable gate; the watcher queues one `ask:` wake per deadline on the first scan at or after it, and cuts its sleep short so that scan lands on the deadline, even while the backstop is backed off; an unreadable deadline wakes at once | C8 owner channel: partial, compensated by the GitHub post (the owner's GitHub notifications) and the §6 recommended default with auto-apply time; residual risk: an owner away from the machine sees the ask only through GitHub, and an ask posted without its `asks/` record gets no deadline wake |
| C9 Ownership handoff | Ownership record and read-only guard implemented ([protocol](../protocol.md#ownership-record)); `mdstack handoff` posts the owner commands (#637), builds and reconciles the manifest (#211), and acks, lifts `holds_added` and posts `stopped`, with poll's `lost` wake and a watcher that will not re-arm as the prompt stop (#212) ([Ownership fallback](#ownership-fallback)); [mdstack down](#mdstack-down) stops every window and the watcher, refusing while the land lock is held and keeping unlanded worktrees, and `mdstack up` reconciles from disk and GitHub ([Q7](#q7-failure)) | C9 ownership handoff: unsupported, compensated by the owner's manual pause: `mdstack down` before another runtime starts, plus `crew:hold` on open crew items for a runtime that honours it; residual risk: without a configured control item, a second crew can still act; runs are killed or kept, not drained; the incoming runtime rebuilds its context from GitHub ([#210](https://github.com/mw-ding/eng-crew/issues/210)–[#212](https://github.com/mw-ding/eng-crew/issues/212)) |

With `session_backend = "herdr"`, the runtime keeps the contract above,
using the [herdr operations](session-backends.md#herdr-herdr), with these
additional gaps:

| Capability | Gap |
|---|---|
| C1 Wake on event | C1 wake on event (herdr activity): partial, compensated by status-file progress, OS child-process probes and the existing stale re-check/escalation; residual risk: no last-output timestamp means output alone cannot refresh a heartbeat |
| C3 Messages by reference | C3 delivery (herdr composer): partial, compensated by requiring an empty visible composer before typing, checking for a new empty composer afterward and requiring the inbox ack; residual risk: unrecognizable or busy composers fail with exit 4 and need a bounded re-check |
| C6 Isolation | C6 coordinator environment (herdr): partial, compensated by refusing private environment delivery before creating a workspace and selecting tmux for those profiles; residual risk: a coordinator needing private environment delivery cannot start on herdr |
| C8 Owner channel | C8 observation (herdr): partial, compensated by individual read-only snapshot streams and explicit interactive attach; residual risk: no scrollback navigation or tiled builders view |

In-place upgrade is refused before stopping any herdr run; stop and restart
the crew using the updated install. These gaps change no protocol gate.

With a `[hosts]` inventory ([multi-device](multi-device.md)), each kind of
host keeps the contract as follows. With no `[hosts]` table, the machine is
the primary.

| Host | Runs there | Contract |
|---|---|---|
| Primary | The coordinator, the synthesizer, `mdstack poll`, the watcher, claims, the land lock, and every role run while M20 lasts | The table above, unchanged |
| Forge-less runner host (`forge = false`) | `mdstack runner` jobs only: `check-repo`, named tests and offline evidence captures, run at a seeded head. Never a role session, model call or forge access | Unchanged. No wake, status line, inbox, claim or lock lives on the host. A role run on the primary starts the job and gets its result back by reference under `$CREW_STATE/runner/`. Unreachable or refused falls back to a local run ([Failure and fallback](multi-device.md#forge-less-hosts-remote-test-runner)). Added by the [runbook](multi-device.md#runbook-add-a-runner-host) |
| Role host | Builder and reviewer runs, placed by `mdstack spawn` ([#345](https://github.com/mw-ding/eng-crew/issues/345)) | The [contract across hosts](multi-device.md#runtime-contract-across-hosts), with its C1 and C9 gaps. The [run lifecycle](multi-device.md#remote-run-lifecycle) and [attach and logs](multi-device.md#observability) and [wakes and messages](multi-device.md#remote-wakes-and-messages) are built, and so is [partition handling](multi-device.md#failure-and-partition) (#347) |

## Q1. Wake

**Decision.** Event-driven hybrid with one wake path into the coordinator:

1. Role windows append status lines; `mdstack poll` turns GitHub state changes
   into wake records routed to one consumer (#134). Each opened or pushed
   head starts review alongside CI; held CI failures join the findings in
   one builder handoff ([mdstack poll](#mdstack-poll)). Stale timers fire for
   runs with no status progress, and an ask timer fires at each open owner
   ask's deadline (`asks/<n>.json`, [C8](#runtime-contract)).
2. A zero-token watcher (a plain script, no model) runs persistently:
   `mdstack up` starts it in its own session, independent of coordinator
   turns, so a turn that ends on a model-gateway error stops neither polling,
   routing nor deadline wakes (#1346). It blocks on those sources, appends
   each actionable event to `wake/queue.jsonl`, runs `mdstack route` for mechanical
   work, and for retained judgement records prints one reason line
   (`status:`, `poll:`, `stale:`, `ask:`) and types `wake: watcher` into an
   idle coordinator. The one-shot form, which exits instead, stays for a
   coordinator that arms its own.
3. The nudge (or a one-shot watcher's exit) re-invokes the coordinator ([Q3](#q3-coordinator-engine)).
   On a turn with an owner message it answers briefly before routing, then
   drains the retained queue and acts (`mdstack send`, `mdstack spawn`, `mdstack kill`, a
   GitHub post). A queue left undrained is nudged again after `--renudge`.
4. **No turn ends blind.** A turn-end guard refuses to let the coordinator
   stop while work is in flight (a live run record, a non-empty queue or an
   open owner ask) and no watcher is armed. Claude Code: a Stop hook that
   `mdstack up` installs (#131). It names the resolved bundle, so a run through
   the `mdstack` link adds nothing, and a newer bundle re-points the state's
   one guard (#1088). Codex: its turn-complete notify program runs
   the same check and, if it fails, types a fixed wake line into `ash`.

Roles never read GitHub events themselves and never message each other;
everything goes through the coordinator (hub and spoke). The queue is on
disk, so a coordinator restart loses no wake.

**Alternatives.**

- *GitHub as the only bus, each role polling.* Rejected: N pollers spend
  tokens on no-op wakes and two roles can race on one event (C2).
- *Coordinator nudges and polls on its own loop.* Rejected: costs a model
  turn per tick, and the coordinator went idle forever when no notification
  arrived (Claude Code session runtime, 2026-10-29).
- *Heartbeat-driven wake.* Rejected for wake and for liveness; see
  [Q7](#q7-failure).

## Q2. Lifetime

**Decision.** Lifetime follows what each role gains from context:

- `ash` and `sam` live for the tmux session. Both keep only references;
  state is re-read from GitHub on every wake (§6 step 1).
- `ben-<issue>` lives for the issue. Fix rounds arrive in the same window by
  inbox, so the builder keeps its understanding of the change (#137).
  A `done:` line leaves it idle and assigned to that issue/PR; route reaps it
  when it sees `pr-merged` or `pr-closed`. Idle windows do not count toward
  the busy-builder cap. If all ten builder indices are occupied and queued
  work can run under that cap, dequeue reclaims the longest-idle builder
  whose work is pushed. A later `fix` or `ci-red` message to its old window
  queues refs for route to spawn a replacement automatically (#493).
- `vera-...-review` and `vera-...-validate` are one fresh session per pass.
  Validation never sees the review's context, and no reviewer carries a
  previous round's opinion forward. Review starts on `new-head` without
  waiting for CI, and validation starts only after review passes. Both record
  CI as information only; CI green at head is checked at merge.
- `vera-...-recheck` is an explicit CI-fix or recovery session: inspect
  conflict-resolution hunks and rerun acceptance checks, then post both
  sections in one merge-up re-approve verdict. A clean update-branch skips
  straight to the checks when this recovery is requested; identical clean
  base updates normally use synthesizer portability with no reviewer session.
  Content or behaviour changes in the resolution
  return to normal review and validation ([§6](../protocol.md#6-duties-on-wake-all-roles)).

**Alternatives.**

- *Every role long-lived.* Rejected: context grows without bound (#109) and
  a long-lived reviewer anchors on its earlier verdicts.
- *Fresh session for every pass, builder included.* Rejected: each fix round
  re-reads the issue, diff and findings, the cost #109 targets, for no
  independence gain on the author side.

## Q3. Coordinator engine

**Decision.** The profile picks Claude Code, Codex, Pi or Cursor for `ash`. They run
interactively in window 0 so the owner can type to them. Each meets the wake
path in its own way:

| Need | Claude Code | Codex | Pi | Cursor |
|---|---|---|---|---|
| Re-invoked on watcher exit | Background command completion starts a turn | Watcher types a fixed wake line into `ash` on exit | Watcher types a fixed wake line into `ash` on exit; live timing unverified | Watcher types a fixed wake line into `ash` on exit; live timing unverified |
| Turn-end guard | Stop hook | Turn-complete notify program | Extension `agent_end` event; integration unimplemented | No integration installed |

Role windows take engine, model and effort from profile tier routing
([roles](../roles.md#engines-and-fallback-order)). A reviewer or validator
engine differs from the engine that actually wrote the round (invariant I2,
[reviewer engine selection](../roles.md#reviewer-engine-selection)).

**Alternatives.** *Claude Code only*: rejected, because quota steering
([roles](../roles.md#quota-routing)) needs a second coordinator engine.
*Any engine as coordinator*: deferred; an engine qualifies once it can run a
background command or accept a typed wake, and has a turn-end hook.

## Q5. Identities

**Decision.** The profile names a GitHub identity per role. `mdstack spawn`
passes only the login (`CREW_IDENTITY`); the window's launch line derives
the token inside its own shell, `GH_TOKEN=$(gh auth token --user
"$CREW_IDENTITY")`, then starts the harness. The token is never written to
disk, never in argv and never on the tmux command line. With one identity
for all roles, the single-identity rule of #111 applies: verdicts are
COMMENT reviews with `pass=verdict` markers and a recorded owner merge-ok
([portable spec §6](../specs/portable.md#6-decisions)).

**Alternatives.** *`gh auth switch`*: rejected, it changes a machine-wide
setting and races between windows. *`tmux new-window -e GH_TOKEN=...`*:
rejected, the token lands in argv. *Per-window `gh` config dirs*: rejected,
they duplicate credential stores on disk. *A GitHub App per role*: later; it
also unblocks branch protection ([merge enforcement](../merge-enforcement.md)).

## Q6. Concurrency

**Decision.** Caps per band from the profile: default 5 busy builders and
2 reviewer passes; one land at a time. Beyond a cap, `mdstack spawn` creates
no window and appends to `spawn-queue.jsonl`; the builder lead drains its
own pool on completion or window cleanup (#136, #493). Reviewer dispatch and
reclaim belong to its reviewer lead. Within the caps, both leads admit through
the crew scheduler's `mdstack schedule decide` ([scheduling](../scheduling.md)).
Land is serial: `sam` holds `locks/merge.lock` ([C7](#runtime-contract)).

**Alternatives.** *No cap*: rejected, one machine and engine quotas are the
limit. *2 builders* (the first proposal): raised to 5 to match the
[parallelism](../roles.md#parallelism) ceiling and the kickoff choice.
*5 reviewer passes*: reviews run a second engine and the tests, so the
default starts at 2, still within the ceiling.

## Q7. Failure

**Decision.** Detect from outside the agent; restart only when it is safe:

| Class | Probe result | Action |
|---|---|---|
| `alive` | Window present with the recorded run identity, pane live, expected harness in the foreground | None; a wedge timer with no status progress turns it `ambiguous` |
| `dead` | Window present with the recorded pane id and pid, pane dead or harness gone, no `failed:` (nor `done:` for a reviewer or synthesizer run) | Restart once |
| `missing` | Run record or claim present, and no window, or a window whose pane id, pane pid or that pid's start time differs from the run record | Restart once |
| `quota` | Window present with the recorded run identity, pane live, and the run's own harness adapter's usage-limit line (`QUOTA`) on screen (#631) | Restart once, in place (same worktree, head, claim and inbox), on the next eligible engine in the role's order, skipping every engine the run exhausted; a reviewer whose PR head moved, or none left, refuses and escalates |
| `ambiguous` | Probe failed, unexpected foreground process, a blocking prompt (trust, hooks review, Codex approval, Claude Code permission) or a fatal API error on screen, or wedge timer expired | Re-probe; after a bounded time escalate to the coordinator; never restart, except one kill-and-respawn of the synthesizer after a failed nudge (below) |

**Failed nudge** (#308, #312). A window that `mdstack send` could not nudge
(exit 4; a `dialog:` reason is a dialog, which this rule leaves alone) or
that still has no ack after one re-nudge counts as `ambiguous` for the
coordinator, even when the probe says `alive` (an idle harness with the
nudge unsubmitted or unread), so it is never restarted. One exception: the
synthesizer window `sam` holds no worktree work, so the coordinator may
`mdstack kill` it and `mdstack spawn synthesizer --pr <n>` once per PR; a second
miss on that PR escalates to the owner. It does so only while
`locks/merge.pid` does not exist, so a land is never cut off mid-flight, and
it re-sends every other pending `land`, because the kill drops `sam`'s
inbox. This is firstmate's default of recovering a stuck worker without
waiting for the backstop, narrowed to the synthesizer. `mdstack restart` is
unchanged: it still refuses a run that does not probe `dead` or `missing`.

**Run identity** ([C5](README.md#c5-liveness)). `mdstack spawn`, and an
in-place `mdstack restart`, records the pane's `#{pane_id}`, `#{pane_pid}` and
that process's start time (from `ps`) in the run record. The probe compares
them before it looks at the harness, so a same-named window running the same
harness (a racing respawn, a manual relaunch) probes `missing`, never
`alive`. Pane ids are unique only while a tmux server lives, so the start
time is required.

A restart is a fresh window and a fresh worktree from the change's branch;
a second failure on the same item escalates (`crew:escalated`, owner channel)
under [protocol §5](../protocol.md#5-rounds-and-escalation). If the tmux
server or `ash` dies, `mdstack up` reconciles from disk and GitHub: run records,
status files, the wake queue and a probe of every recorded window.

**Alternatives.** *Heartbeat file per run* (the first proposal): rejected,
it depends on the agent remembering to write it, and silent workers froze
for hours on 2026-10-19
([bottlenecks lesson](../lessons/2026-10-19-bottlenecks.md)). *GitHub-only
sweeper*: kept as a backstop shape, too slow as the detector.

## Spawn and kill

`mdstack spawn <role> --issue <n> | --pr <n> --pass <pass>` (#132):

1. Check the band cap; on refusal queue the request ([Q6](#q6-concurrency)).
2. Create the worktree `<worktree-root>/<n>-<sha7>-<role>-<pass>/` from the
   current remote default branch, or from the PR branch for fix, review and
   validate passes. Refuse the main checkout, a branch-named path or an
   existing path.
3. Preflight: pre-trust the worktree for the harness (or expect the trust
   dialog to probe `ambiguous`); for a nested sandboxed Codex, set the
   sandbox-inheritance variable the org pack names; confirm the coordinator
   can reach the tmux socket.
4. Create the window in the background, so focus stays on `ash`:
   `tmux new-window -d -t crew-<owner>-<repo>:<index> -n <name> -c <worktree>
   -e CREW_ROLE=... -e CREW_ID=... -e CREW_STATUS=... -e CREW_INBOX=...
   -e CREW_BRIEF=... -e CREW_IDENTITY=... -e TMUX=/dev/null/mdstack-worker,0,0
   '<launch>'`. The last `-e` is the worker guard below.
5. `<launch>` derives `GH_TOKEN` ([Q5](#q5-identities)) and starts the
   harness interactively with the profile's permission flags
   ([mdstack spawn](#mdstack-spawn)) and a short pointer only, for example
   `claude --add-dir <state-dir>/<owner>__<repo> --permission-mode
   bypassPermissions ... 'Read your brief at $CREW_BRIEF and follow it.'`.
   Briefs never travel through `send-keys` or argv.
6. Verify start: within the profile timeout, the expected harness must be a
   foreground process of the pane's tty, as for liveness, or
   `#{pane_current_command}`; through a symlinked install that reads as the
   name of the file the link resolves to, which also counts. Otherwise
   record `failed:` and no live run.
7. Write the run record and the claim. The run brief is the rendered role
   brief plus the `## This run` block from `mdstack brief`'s helper, the same
   block every runtime uses ([hosted dispatch](session.md#run-parameters-for-hosted-dispatch)).

Worker guard (#1475): every role window the tmux adapter opens
(`mdstack spawn`, `restart` and `lead ensure`) or reloads in place
(`mdstack upgrade`) gets `TMUX=/dev/null/mdstack-worker,0,0`, a socket no
server can listen on; the coordinator's window 0 keeps the crew's. A bare
`tmux kill-server`, `kill-session` or `kill-window` from the agent's shell
follows `$TMUX` ahead of `TMUX_TMPDIR`, so it fails with `Not a directory`
instead of ending the crew's server, even with the host tmux first on `PATH`.
This closes the mechanism behind the session loss in
[#1474](https://github.com/mw-ding/mdstack/issues/1474), the same one
[#817](https://github.com/mw-ding/mdstack/issues/817) found (also
[#1155](https://github.com/mw-ding/mdstack/issues/1155)). It needs no
dedicated or private crew socket: the crew stays on the owner's default
server (#1327). Crew commands
(`mdstack send`, `acked`, `status`, `kill`, the leads' spawn and kill) are
unaffected: the adapter always names the server with `-S` or `-L` and never
follows `$TMUX` (#818). A call that names the crew's socket, or unsets `TMUX`
and lands on a default-server crew, still reaches it, so the builder, reviewer
and researcher briefs carry the rule: destructive calls name
`-S <sandbox-socket>` with `TMUX` and `TMUX_PANE` unset, or go through
`scripts/campaign-sandbox.py teardown`. `dev/tests/environments/test-worker-tmux-guard.py`
runs the bare calls from such a window against a throwaway crew server.

`mdstack kill <window>`: stop the pane's processes, `tmux kill-window`, then remove only that run's
worktree, build output, run record, inbox, status file and claim, and only
when its work has landed or was explicitly discarded (#172).

## Builder lead

The default tmux renderer installs `builder-lead.md`; `mdstack up` starts its
long-lived session in reserved window 2, outside the `builders` cap.
The coordinator routes work with `mdstack lead handoff builder KIND REF...`;
the lead owns builder spawn, dequeue, reclaim and restart. Custom bindings
without this brief keep their declared scheduling; a missing/dead lead in
an installed binding never falls back to coordinator worker spawns.

Owner-present admission uses `runtime.options.present_builders` and
`present_reviewers`, each defaulting to its full cap. Active recorded non-quiet
away mode uses full `builders` and `reviewers`: owner-friendly parallelism
while present, full speed within the caps while away. The optional away
`--cap` remains an additional bound across concurrent runs, defaulting to no
cap. Both leads read `away-control.json` and its authoritative signed issue
records on each admission check. Entering or leaving away mode changes
admission on the next lead wake without restarting sessions; never kill
running workers to meet a lower cap, let the pool drain naturally.

Admission asks `mdstack schedule decide --pool builder`
([scheduling](../scheduling.md#model)): it ranks both pools' demand
crew-wide under the presence caps, the machine target, the ramp limit and the
optional `max_suites` and `max_load` ceilings, and the lead starts exactly
the builder items it admits. Never stop an active worker to reduce load. Idle
builders do not count toward admission; retention preserves continuity only while capacity is spare,
even with open findings. Reclaim clean/pushed idle builders on demand or
after `idle_builder_ttl` seconds (default 1800; 0 disables expiry), retaining
output and step summaries. Later fixes resume from the adopted PR.
`mdstack lead suites builder` (or `reviewer`) counts live tool sessions across
both pools, excluding closed/merged items and untracked orphan processes.
An unavailable process or live-state probe fails the command. `mdstack lead
capacity` is retired: no brief calls it since both leads use the scheduler.

`mdstack lead report builder REASON REF... --detail "observed inputs"` records
`capacity`, `load`, `suites` and `probe-unavailable` deferrals in
`leads/builder-admission.md` and the lead's `deferred:` status. The router
consumes those status wakes without involving the coordinator; keep the
handoff pending for a backstop or slot release. With `--id ID`, the lead's
inbox id for the deferred handoff, the status line ends `id=ID`; once that id
is acknowledged, the watcher's 60-second admission recheck stops re-typing it and instead re-runs
the scheduler walk, persisting only the target's progression (no
reservation, decision log or deferral), and nudges only when the ref is now
admissible, so a target throttled under high load recovers on that cadence.
A worker's `done:` (slot release) and the coordinator backstop still nudge it,
an unacknowledged or unreported id keeps the normal retry, and a re-sent
handoff gets a new id.

The watcher's lead backstop (#1715) retries a lead's actionable pending ids
after 60, 120, 240, 480, then every 900 seconds while that set is unchanged;
a changed set restarts at 60 seconds, and the timer survives a watcher restart
in `wake/watch-state.json`. An id that can move only on the owner, a hold or
CI is a wait: the lead acknowledges it and appends
`waiting: #<n> owner|hold|ci id=<id>` (the lead templates' Waits paragraph).
`mdstack reviewer-pool` writes that line itself after its ack for a review,
validate, recheck or `work` request whose PR is live `crew:escalated`
(`owner`) or `crew:hold` (`hold`), keeps the id pending and writes it again
on each re-run while the label stays (#1836); `done:` stays for dispatched
or obsolete work. While the ref's fresh state is unchanged, no path re-types
that id (lead backstop, slot release or coordinator backstop) and route
consumes the line; a repeated ack never re-arms it. Fresh state is
token-free: the state, head and CI of `mdstack poll`'s `observed` entry, its
`held` list and owner-answer count (`answers`) in `poll-state.json` and an
open `asks/<n>.json`, recorded per wait in `leads/waits.json`, which survives
restarts. A change wakes the id on that scan, without waiting for a deadline;
it stays actionable until a later `waiting:` line. Mergeability and verdict
churn are not wait state, and a hold appearing (poll catching up on the
label the dispatcher saw live) only becomes the new baseline, so its later
release still wakes the id. New handoffs, such as the coordinator's land re-send on an
owner answer or route's `ci-passed` event, are new ids and wake at once.
An acknowledged admission deferral keeps its 60-second token-free
`admission recheck`, which types only that id and only once its ref is
admissible, so admission becoming available wakes the lead within a minute
whatever the backed-off retry. Other ids keep their own retries; a line without a listed kind or an
acknowledged `id=` silences nothing. Events wake leads and supply no
permission. Only `spawn-failure`,
`missing-dependency`, `owner-decision` and `lead-fault` reasons send a
`blocked` coordinator inbox message with a durable block note. Identical
reason, refs and detail reuse that message across lead restarts; changed
refs or details notify again.

Handoffs use the existing inbox, status and delivery-ack interface. Event
files have stable identities for replay. The lead reconciles pending ids,
worker claims and live GitHub state on start; completed ids are no-ops.
`mdstack kill` hands builder reclaim to its lead as a `lifecycle` `reclaim`
work event, a request the lead completes with its own pool's `mdstack kill`
before marking the id done (#1701), and automatic dequeue cannot
dispatch another lead's pool. The watcher observes lead identity/status and
nudges deferred inbox work on its token-free backstop. It restarts a dead
or missing lead once through `mdstack lead ensure builder`, keeping its inbox
and live workers. Ambiguity or a second failure reaches the coordinator's
owner channel for explicit repair. Stopping a lead keeps its inbox; a
successful `mdstack down` clears lead identity while keeping pending handoffs
for the next start. Synthesizer lands go to the [synthesizer lead](#synthesizer-lead).

### Team pools

In a [team file](../configuration/team-files.md#resolution-and-team-instance)
each pool has one lead keyed `(team, pool)` (#1858,
[team §9.3–§9.4](../specs/team.md#93-qualified-work-and-state)). Its record,
inbox, status and brief live at the team root; every repo's route hands it
messages carrying that repo's `context` envelope, and a repo's watcher sees,
parks and retries only its own messages, fingerprinted from its own poll
state. The lead brief lists each repo's rendered lead brief, and
`$CREW_PROJECT` is the team file, so a command without the message's
`context.project` refuses in a multi-repo team. A repo whose ownership
refuses gets no handoff; the lead keeps serving the others.

One lock at the team root (`allocations/.lock`) mints a team-global run ID
and takes the window slot before any worktree or window. A team run's window
name carries its repo tag (`ben-42-<owner>__<repo>`), its worktree is
`<worktree-root>/<owner>__<repo>/<run-id>/`, and its run record adds
`run_id`, `context`, `project`, `checkout` and `handoff` (`spawn --handoff`).
The tag is one-to-one: `/` becomes `__` and every other character outside
`[a-z0-9-]` becomes `_<hex>`, so `example/alpha.foo` is
`example__alpha_2efoo` and never meets `example/alpha-foo`.
Claims, worker inbox and status stay in repo state. Every restart takes a new
run ID and keeps the run's `handoff`; a restart in its own worktree refuses,
changing nothing, when the run's window shows another process. `mdstack kill`
in a team stops a window
only at the run's recorded slot, pane, pane pid and process start time (a dead
pane matches as the liveness probe reads it), removes a worktree only under this repo's
tag, and releases only this repo's allocation, so A's kill, restart or
replay never touches B's same-number run.

Landing is bound to the repo the command's `--project` selects (#1859,
[team §9.5](../specs/team.md#95-landing-authority-and-refusals)). The land
lock lives in that repo's state, so one land runs at a time inside A while
B's lock, and B's red default branch, never block A; `locks/merge.pid`
records the repo's `context` and the acquiring `window` (a shared lead's
too). Train and delegation records and async land and stack intents record
the `context` as well. Before any write, `train` compares every record and
delegation it names, every member qualifier (`<owner>/<name>#<n>`, also
`<owner>/<name>#<n>:<sha>` in `land stack --stack`) and, for `build` and
`delegate`, each member's URL read back from the backend; `train land` reads
the member's verdict, permission, landing control and holds only when their
URLs are the selected repo's. `land request|resume|done`, the stack land and
`land-lock acquire|release` refuse a record naming another repo before any
read, request, cleanup or drop. One foreign or unreadable source refuses the
whole action with nothing written; in a one-repo config a record written
before #1859, without `context`, stays the selected repo's. Gate
satisfaction, actors and fail-open paths are unchanged.

## Reviewer lead

The default binding installs `reviewer-lead.md` and starts the reviewer lead
in reserved window 3, outside the reviewer cap. The router records durable
`work` events for new heads, builder completion, pass completion and worker
liveness. Coordinator recovery uses `mdstack lead handoff reviewer
review|validate|recheck '#PR' HEAD ROUND`; add a rereview steer id as a fourth
reference for a fresh request at the same head. The coordinator never
spawns or reclaims reviewer workers directly in this binding.

The lead calls `mdstack reviewer-pool`. Dispatch
is serialized under `leads/reviewer/dispatch.lock`; inbox ids stay pending across interruption
until dispatch, matching output or live obsolescence is observed. Before each
spawn, admission asks `mdstack schedule decide --pool reviewer`
([scheduling](../scheduling.md#model)) and starts the pass only when its PR is
admitted; the reviewer floor keeps one slot, so builder suites cannot starve
reviews. Terminal output survives reclaim; slot release
never automatically dequeues a pool with a lead. Existing active passes stay
running when load rises. The watcher backstop nudges deferred work.

Dispatch deduplicates PR/full head/pass/round across worker records, queued
requests, retained sections and posted markers. An open rereview ignores
output before its steer. Passing review replay starts missing validation
even after review cleanup. `recheck escalate` starts normal review and then
validation; a completed recheck needs no extra validation. Identical
merge-ups continue through synthesizer verdict portability, preserving the
current protocol. Findings travel to the builder lead with retained refs.

A failed Actions run whose observed jobs all have zero steps is `ci-infra`:
coordinator handles the incident, validation may proceed, and no builder
CI fix is dispatched. Missing or incomplete observations remain CI failures.
Infrastructure is never green CI and never waives a merge gate.

Worker recovery rechecks live head and holds before one dead/missing restart;
ambiguous or twice-failed workers require coordinator escalation. Supervisor
lead recovery uses the same identity and one-restart rules as builder lead
recovery, preserving workers, pending inbox ids and evidence.

## Synthesizer lead

The default binding installs `synthesizer-lead.md`; `mdstack up` starts the
synthesizer lead in window 1 (the synthesizer's band), outside the role caps,
and the watcher supervises it like the builder and reviewer leads: one
restart of a dead or missing lead through `mdstack lead ensure synthesizer`,
coordinator repair after that or when ambiguous (#1569). Unlike the pool
leads, it is the lander itself: it reads the rendered `synthesizer.md` as its
land procedure and never spawns synthesizer workers. With it installed,
`mdstack spawn synthesizer` refuses, and nothing reaps it after a land.

`mdstack route` writes `review-approved`, `selfgate-passed`, `ci-passed`
with a passing verdict, self-gate or coordinator `merge-ok` steer at head,
or on an approved merge-up head
(an express `ci-passed` is already gated by `mdstack poll`), and approved
`merge-up` events as durable `work` events into its inbox. They no longer stay queued for the
coordinator. A `merge-ok-recorded` event whose authenticated merge-ok is still
at the live head goes there too, so permission recorded after CI went green
wakes the land; permission before CI gets a gate check that waits, and the
later `ci-passed` retries (#1835). A closed PR or a merge-ok no longer at
head consumes it. A land event for a superseded head is dropped; an unapproved
`ci-passed` is consumed unless held CI refs (`ci/<n>-*.json`) wait on it.
A merge-up with an open rereview or a resolved conflict still goes to
the reviewer lead. Coordinator recovery uses
`mdstack lead handoff synthesizer land '#PR' HEAD`.

The inbox is the land queue: every message without a `done: <id>` status
line is pending, across restarts and `mdstack down`. The lead lands
serially under the existing land lock (`locks/merge.pid`, never taken
from a live holder), trains two or more ready PRs per the land rule, and
re-checks every [§7](../protocol.md#7-merge-gate-synthesizer) gate live
before each land (F3). Staying long-lived does not carry authority between
lands: for every land it re-reads the head-pinned gate and permission
sources (marker lines, CI, labels and the recorded `merge_grant` with its
source decision, scope and exclusions). Inbox and ref payloads, event files
and narrative summaries only name a candidate; they supply no approval or
permission, and with `merge_grant = "none"` no standing grant exists (#314). After a direct land it settles the id only once the
merge commit's CI is green or `blocked: main red after #<n> <run-url>` is
written. A replayed id whose land already happened finds the PR merged at
step 1; after a direct land it resumes the merge-commit CI watch before
settling. `mdstack land-lock acquire` records the lead's pane as the lock
owner, so a lock left by a dead lead pane is released and the restarted lead
can take it. Train delegations name the lead as the `synthesizer` window,
so `train-done` and `train-failed` reach it.

Route consumes the lead's `ack:`, `done:` and waiting gate-status lines
(`wait=ci`, `review`, `validation`, `selfgate`, `train`), and a clean
`train-report` (`dropped=none stop=none`). Its other
`blocked:` lines stay queued for the coordinator: owner merge-ok,
`crew:sensitive`, holds and `main red`; lead faults arrive as `stale` or
`dialog` wakes. Merged-PR close-out stays in route (labels, closing the
issue, a fallback branch deletion under the existing rules when the land
left the branch, builder reclaim through the
builder lead), so a land needs no coordinator turn. With a Slack owner
channel, route also queues the away-only `land` notification through
`mdstack notify` (stable id `land-<n>`, the train number or `direct`, the
milestone or `None`). Open issues whose `Depends on` names the merged PR go
to the builder lead as `build` handoffs when they carry `crew:ready`; only a
dependent that is not ready still wakes the coordinator.

## Usage

`cli/mdstack` (Python 3.11+ stdlib) is the CLI: a thin entry point that loads
one module per command, `environments/terminal/crew.d/<cmd>.py`, with the
shared helpers in `environments/terminal/crew.d/_shared.py`, and
`mdstack --help` lists the commands. Every tmux call goes through
`environments/terminal/sessions/tmux/adapter.py`, so the tests
(`dev/tests/environments/test-crew-<cmd>.py`, one file per command) run it against a fake
`tmux` on `PATH`. Run it from an mdstack checkout. Each command's usage
line is in its own section below.

Every command that resolves the profile (all but `mdstack guard`) refuses, exit
1, while the **resolved** value of a `paths.*` key it uses is still a
`<placeholder>`, whichever layer set it, so an omitted key that falls back to
the shipped default is refused too (#265). Each command checks only the keys
it uses: every command checks `paths.state_dir`; `spawn`, `kill`, `down`,
`restart` and `train build` also check `paths.worktree_root`; only
`spawn builder` also checks
`paths.toolchain_bin`. An unrendered copy, such as the `config.toml` inside a
worktree, would put the land lock and state under the worktree. In a window,
use `--project "$CREW_PROJECT"`.

### mdstack up

```sh
cli/mdstack up [--project <config.toml>] [--org-profile <path>] [--inputs <inputs-dir>] [--coordinator-only] [--resume <id>]
cli/mdstack up --team <config-home>/teams/<team>.toml [--org-profile <path>] [--inputs <inputs-dir>]
cli/mdstack up <role> [--project <config.toml>] [--org-profile <path>]
```

`mdstack up <role>` starts one more instance of a role with a `lifecycle`
whose `wake` has `manual`, up to its `max`, and the watcher scales idle
instances back down to `min` ([role lifecycle](../roles-registry.md#lifecycle), #1231).

`--resume <id>` (or `ask`) overrides `launch.resume` for one run
([launch topology](../configuration/runtime-options.md#launch-topology)). On a
`session` profile, `mdstack up` starts only the coordinator
([session binding](session.md#starting-the-coordinator), #1548).

`--team` starts one instance for every repo of a
[team file](../profile.md#team-files) (#634): one session and coordinator,
and a render per repo under the team state root. The steps below apply to
each repo. It then records each repo in `<team-root>/team.json` and ensures
one `(team, pool)` lead per enabled pool, through the first repo whose render,
pause and ownership allow it; a repeat run finds the leads live and starts
none (#1858, [team pools](#team-pools)).

`mdstack up` (#131):

1. Resolves the profile and refuses unless `runtime.name` is `tmux`.
2. If the session (`runtime.options.session`, default `crew-<owner>-<repo>`)
   is already running, prints the attach command and changes nothing.
   Every crew tmux call runs on one server, `runtime.options.tmux_server`
   (#1327). `"default"` (the default) is the owner's default server, named
   by path (`${TMUX_TMPDIR:-/tmp}/tmux-<uid>/default`), never by an
   inherited `$TMUX`, so plain `tmux ls` lists the session and
   `tmux attach -t <session>` attaches. `"dedicated"` is the crew's own
   server, `tmux -L <session>` (#818), so a pane's bare `tmux` (which
   follows the pane's `$TMUX`) reaches only that server; attach with
   `tmux -L <session> attach -t <session>`. The trade-off: on the default
   server a stray `tmux kill-server` from a pane also takes down the
   owner's own sessions; the sandbox guard from #817 stays the primary
   protection. A crew session still running on the other server (for
   example one started before #818, or before the option changed) is used
   there until its next `mdstack up`. `mdstack up` and `mdstack attach`
   print or run the matching command.
3. If the profile can use Codex (coordinator, tier order or fallback), checks
   host `hooks.json` and inline `config.toml` hooks under `$CODEX_HOME`
   (default `~/.codex`). Refuses, exit 1, if any hook has no stored
   `trusted_hash`, before rendering or creating a session. Run plain `codex`
   on the host and review/trust those hooks once, then retry. This check
   never writes Codex config or recomputes its hashes: changed hooks with
   stale hashes, plugin hooks and project hooks still rely on the live
   dialog check.
   Also refuses, exit 1 and before rendering, when the checkout
   (`paths.checkout`, else the project directory) has a forge `origin` URL
   naming another repo than `[repo]`, or when `paths.mdstack` is set but
   missing, so the briefs would cite missing docs; run `mdstack bootstrap`
   (#1323).
   Also refuses, exit 1 and before rendering, on a failed
   [doctor `sandbox` row](#mdstack-doctor): a launcher sandboxes sessions,
   no writable root covers the checkout's `.git` and no `sandbox_env` is set
   (#1544).
   Renders the briefs with `crew-render.py` into
   `<state-dir>/<owner>__<repo>/render/`, printing the renderer's output
   only when it fails. `--inputs` defaults to
   `templates/`, whose [tmux briefs](../../templates/README.md) render to
   `render/runtime/<role>.md` (#137); `mdstack up` and `mdstack spawn` use
   `render/briefs/<role>.md` when the inputs have a `core/`, else that file.
4. For a Claude Code coordinator, adds the turn-end guard to
   `<project>/.claude/settings.local.json` as a `Stop` hook running
   `mdstack guard --state <state-dir>/<owner>__<repo>`, once, keeping every other
   setting. Role windows in worktrees of the project load it too; the guard
   is a no-op there (`CREW_ROLE` is not `coordinator`).
5. Creates the session detached, with window 0 named after
   `identities.coordinator.name` (`ash`), then `-<identities.team>` when
   set, in the project directory. The
   window gets `CREW_ROLE=coordinator`, `CREW_STATE`, `CREW_BRIEF`,
   `CREW_IDENTITY`, `CREW_BIN`, `CREW_PROJECT` and the sandbox variable
   (see `mdstack spawn`);
   its launch line derives `GH_TOKEN` in the window's shell
   ([Q5](#q5-identities)) and execs `claude` or `codex` with the pointer
   `Read your brief at $CREW_BRIEF and follow it.` A Codex coordinator gets
   the per-process `projects` table of a role window
   ([mdstack spawn](#mdstack-spawn), Pre-trust) for the real project directory
   and, in a git repository, its repository root, so it skips the
   `Trust this folder?` dialog (#262). Claude Code has no
   documented per-project trust option, so a Claude Code coordinator starts
   at its trust dialog in a new project, whose default answer is `No, exit`:
   attach with `mdstack attach ash --rw` and accept it once. Until then
   `mdstack status` shows `ash` as `ambiguous`.
   It sets `renumber-windows off` and `base-index 0` on that session only
   (never `-g`), and `mdstack spawn` / `mdstack kill` set them again, so a user
   config cannot renumber the index bands.
6. Before creating the session, stops each recorded pool lead whose pane
   process outlived a lost tmux server (#818): Codex ignores the `SIGHUP`
   a dying server sends. Only the recorded `pane_pid` counts, with its
   recorded start time, reparented to init (parent pid 1). It gets the
   `mdstack kill` stop (`SIGTERM` to its process groups, then `SIGKILL`) and
   `mdstack up` prints `stopped orphaned lead <name>`. Any other process,
   including one whose parent is alive, is left alone.
7. Starts the enabled pool lead windows, unless the profile's launch
   topology says otherwise ([Launch topology](#launch-topology)), then
   `min` instances of each role with a [lifecycle](../roles-registry.md#lifecycle).

#### Launch topology

`[runtime.options.launch]` ([profile](../profile.md#runtime), #606) picks
what `mdstack up` starts. With the table absent, every step above runs as
before.

- `coordinator = "none"`: steps 1 to 3 and the coordinator notes run as a
  preflight for that topology, then `mdstack up` prints
  `launch.coordinator = none, so no session started` and exits 0. It
  installs no turn-end guard and creates no session. With `--team`, every
  repo renders and records its ownership binding first.
- `roles = "hosted"` or `"none"`, or `--coordinator-only` for one run:
  window 0 starts exactly as in step 5, with the same name and tags, and
  step 7 starts no lead windows (`started no role windows`). With `hosted`,
  the coordinator dispatches builder, reviewer and synthesizer passes as
  hosted sessions on remote worker hosts through its own dispatch tool;
  `mdstack spawn` and the leads are not used for them.
- `resume`: `fresh` launches as in step 5. A session id launches
  `claude --resume <id>` or `codex … resume <id>` with the brief pointer, so
  the resumed conversation re-reads the freshly rendered brief. `ask` launches
  `claude --resume` or `codex … resume` with no pointer, because the picker
  would take it as a search term or an id; tell the coordinator to re-read
  `$CREW_BRIEF` after picking. Another coordinator engine refuses before any
  write.
- `reconcile = "backend"` (the only value) is the rule below.

**Reconcile binding.** After a rebuild `mdstack up` itself reads only disk: run
records, status files and the wake queue ([Q7](#q7-failure)). Every other
reconciliation read goes through a backend operation of
[interfaces](../interfaces.md), bound by the configured backend (GitHub:
[Interface mapping](../backends/github.md#interface-mapping); a pack: its
`docs/` binding, [packs](../packs.md#layout)):

| Read | Operation | Who reads it |
|---|---|---|
| Ownership record on the control item | `markers.read-item` | lead start (`roles = "tmux"` with `repo.control_item`), and the coordinator on every wake |
| Open items, milestones, board status | `tracker.milestone`, `tracker.board-status` | coordinator §6 sweep |
| Open changes, heads and their items | `change.read-head`, `change.read-diff-paths`, tracker link | coordinator §6 sweep |
| Verdicts and markers at head | `review.list-verdicts`, `markers.read` | coordinator §6 sweep |
| Hold and escalation tags | `state-tags.set-clear-read` | coordinator §6 sweep |
| CI at head | `ci.check-status`, `ci.failing-jobs` | coordinator §6 sweep |

Non-GitHub reference binding: a pack backend named `<pack>` binds each of
those reads to one command of its own tool, documented in the pack's
`docs/`, never in mdstack ([direction rule](../packs.md#direction-rule)).
For example:

| Operation | `<pack>` binding (placeholder form) |
|---|---|
| `markers.read-item` | `<pack-cli> item comments <control-item> --order posted --with-author` |
| `tracker.board-status` | `<pack-cli> item list --open --fields status,milestone` |
| `change.read-head` | `<pack-cli> change show <change> --field head` |
| `review.list-verdicts` | `<pack-cli> change reviews <change> --with-author --with-head` |
| `ci.check-status` | `<pack-cli> ci status <change> --head <sha>` |

The ownership read (`mdstack ownership`, lead start, route, notify) follows
`backends.markers.name`. GitHub keeps its `gh api` call. For any other
backend with `repo.control_item`, `mdstack up` renders that backend's
`markers.read-item` and `markers.write-item` commands from
`<inputs>/backends/<backend>.toml` and records them in
`render/bindings.json` (with `--team`, under each repo's state directory),
with `mdstack handoff`'s live reads for a non-GitHub tracker or change
backend ([handoff](../handoff.md#bindings)). The ownership read runs
`read-item`, after replacing `<control-item>` (and `<n>` for an integer
id), `<owner>` and `<repo>`, with no shell and never `gh`. The command
prints the control item's posts in post order as JSON, in the
[read-item output contract](../handoff.md#read-item-output-contract):
`[{"author": "...", "body": "...", "created": "..."}]`, or the GitHub
comment shape. The trusted-author and marker rules are unchanged. A
missing or unsupported mapping, a string id with only `<n>`, a non-zero
exit or unparsable output reads as `read-only`, so nothing starts or
writes. With `roles = "hosted"` or `"none"`, `mdstack up`
makes no backend call. The shipped coordinator brief writes the GitHub
binding's commands; a pack supplies its own through the render overlay
(#580).

### mdstack down

```sh
cli/mdstack down [--project <config.toml>] [--org-profile <path>] [--keep-grant]
```

`mdstack down` refuses while `locks/merge.lock` is held, runs `mdstack kill` on
each role window (highest index first), stops window 0's processes the same
way (unless `mdstack down` runs inside that process group), then kills the
session. If any
window holds unlanded work, it keeps that worktree, names the windows, keeps
the session and exits 1. With no session and no watcher running it is a no-op.

After the land-lock refusal, both forms first stop the armed watcher, the
live PID in `wake/watcher.pid` or else the `wake/watcher.lock` holder's
(SIGTERM, then waiting for the lock to be released; refusing while it is
still armed after a short grace, or when a lock holder names no live
`mdstack watch`, which is never signalled), even when no session is left, so a persistent watcher never restarts what down stops
(#1346).

`mdstack down --preserve` is the maintenance stop before a migration (#1178).
After the watcher it stops every
pane's processes and the session, but keeps each run's worktree, record,
claim, inbox and status file. Lead identity records are removed as usual;
`mdstack up` writes fresh ones.

In an attended owner terminal, plain `down` previews finished `merge_grant`
clauses before shutdown and offers an explicit `prune` confirmation. Declining
keeps the grant and continues shutdown. An affirmative choice edits authority
only after every shutdown safeguard passes and teardown succeeds; changed
profile/scope facts or lost ownership refuse the edit. `--keep-grant`,
`--preserve`, role shells and noninteractive `down` skip pruning and retain
their shutdown behavior. No unattended confirmation flag is available.

### mdstack grant prune

```sh
cli/mdstack grant prune [--project <config.toml>] [--org-profile <path>] [--dry-run]
```

`--dry-run` prints removed/kept clauses, reasons and source/finished-state
links without posting, backing up or writing. Applying requires an attended
owner shell, the configured owner's forge identity and explicit `prune`
confirmation. Standalone application refuses while crew writers or the land
lock remain; use owner-run `down` to stop them first. A refusal exits 1;
decline, no-op and dry-run exit 0. Read failures keep everything and explain why.

Recognition is conservative: only top-level semicolons split whole clauses.
Finite milestone PR grants and release-cut grants need local source comment
locators (`#<issue> comment <id>` or their full GitHub URLs). Every named
milestone must be closed and every named cut must have a non-draft published
release. Mixed clauses require both. Standing/open/unknown grants, ranges,
restrictions, archive annotations and mixed or unsupported prose are kept.
Milestones match their complete leading identifier (`M35` or `M35 — …`),
requiring exactly one match; `M35.1` and `M350` never match `M35`. Cut versions
with or without `v` resolve to the repository's `vX.Y.Z` release tag; a cut
PR's merge does not prove publication. Source reads verify signed, trusted attribution and
local locators. History remains history.

The supported decision log is the single local issue identified by the
removed clauses' source locators. Ambiguous logs and non-GitHub tracker,
release or marker bindings are refused/kept; no new backend operation or
profile key is required. Only the explicitly selected project's uniquely
located, single-line string in `[runtime.options]` is writable. Inherited,
team, inline-table, multiline and symlink layouts are kept/refused without
materializing an override.

Immediately before application, the command re-reads ownership for `write`,
the layered profile and scope/source facts. It keeps a collision-safe,
timestamped byte-for-byte `runs/grant-backup-*.toml.bak`, then posts one signed,
owner-triggered archive with verbatim removed clauses, source/finished-state
links and before/after profile hashes. The archive supplies no authority and
has no grant, steer or gate marker. Uncertain posts are reconciled by read-back,
including on retry. Only confirmed archive success permits atomic replacement;
original bytes are compared again before replacement. Backup, archive or write
failure leaves the profile intact. Only the grant value changes; exact kept
clauses, restrictions and all other raw/effective values remain intact.

### mdstack pause

```sh
cli/mdstack pause [--project <config.toml>] [--org-profile <path>] [--reason <text>]
```

`mdstack pause` is the owner's work pause (#1714): the coordinator in window 0
and the watcher stay, everything else stops with its work kept. Map an owner's
"pause" to it, never to `mdstack down`, which ends window 0.

1. It writes the durable project barrier `pause.json` in the state dir
   (fsynced, renamed into place, read back) before anything stops.
2. While another process holds `locks/merge.lock`, an atomic land already
   started, it prints `crew: pausing: ...`, stops nothing and exits 75; run
   it again once the land ends. The barrier stays, so no new land starts.
3. It stops every window but window 0 (SIGTERM, then SIGKILL, as
   `mdstack down`) and each run on a role host with its work kept. Every
   worktree, run record, claim, inbox and status file stays; lead identity
   records are dropped, so resume starts fresh leads on their kept inboxes.
   `pause.json` lists the stopped runs.
4. A surviving process or a host that does not answer is an incomplete pause:
   it names them and exits 1 with the barrier kept; pause again. Success
   prints `crew: paused`. Pausing a paused project is safe.

While `pause.json` exists, or cannot be read, these refuse with
`crew: project paused (...); refusing <what>`: `spawn`, `send`, `dequeue`,
`kill`, plain `down` (`down --preserve` keeps every run's work and is
allowed), `reviewer-pool`, `restart` of any window but window 0, `train`
(except `check`), `land-lock acquire` (rechecked under the lock, so a land
racing the pause stops), `land request`, `gc --apply`, `route`, lead start,
lifecycle instance start, and `ownership --action start|land`. `mdstack up`
starts window 0 and the watcher, but no role window. The watcher only
observes: each scan runs its sources and queues their events in
`wake/queue.jsonl`, but runs no status or liveness scan, role-host pull,
timer, routine, scale-down, route, backstop or nudge, and a one-shot watcher
does not exit. Owner asks, holds, rounds and landing stops are untouched.

### mdstack resume

```sh
cli/mdstack resume [--project <config.toml>] [--org-profile <path>] [--timeout <secs>]
```

`mdstack resume` ends a pause, and only on the owner's word. It refuses unless
ownership permits `start`, and while `pause.json` is unreadable (`mdstack
pause` rewrites it). It removes only `pause.json`: no hold, round count or
landing stop. Then:

- before each restart it re-reads the run's issue and PR live: a closed
  item, a `crew:hold` or `crew:escalated` label, a reviewer whose PR head
  moved off its recorded head, or a failed read keeps the run stopped (fail
  closed), as do an open ask, `held` in `poll-state.json` and a last line
  `done:`; its lead or the coordinator admits it later;
- each other run the pause stopped restarts once through `mdstack restart`,
  with its rechecks (a finished run and a refused host stay stopped), without
  spending its one restart, so pause and resume repeat safely;
- the enabled leads start on their kept inboxes and the lifecycle floors
  return, as in `mdstack up`;
- one `resume` wake naming what restarted and what stayed stopped is queued,
  so the coordinator rechecks CI and the remaining demand.

Window 0 is untouched. With no pause it prints `crew: not paused`.

### mdstack layout

```sh
cli/mdstack layout [--project <config.toml>] [--org-profile <path>] [--write] [--owner-cmd <cmd>]
```

`mdstack layout` prints the resolved `root`, `home` (the profile's directory),
`checkout`, `state`, `worktree_root`, `live_dir`, `mdstack` and the CLI the
wrappers run. `--write` writes two one-command starts: `<home>/start` runs
`mdstack up --project <project>` from any cwd (extra arguments pass through,
for example `--coordinator-only`), and `<home>/start-owner` starts
the owner's session (`--owner-cmd`, default `claude`) in the checkout. Both
hold absolute, shell-quoted paths and a generated marker line; rerun
`--write` after the layout moves. A wrapper file without the marker is
refused and left unchanged. It writes nothing under `~/.claude` or other
user-level config; an alias to either wrapper is the owner's choice.

### mdstack install

```sh
<bundle>/cli/mdstack install [--name NAME] [--dry-run]
```

`mdstack install` (#1317) puts a stable `mdstack` on your `PATH`. Run it
from a bundle extracted into `<root>/releases/` (`~/.mdstack/releases/` by
default); elsewhere it refuses. It points that root's `releases/current` at
the bundle and writes the launcher `<root>/bin/mdstack`, a shell script that
runs `releases/current/cli/mdstack`. When `<root>/bin` is not on `PATH`, it
links `mdstack` into the first directory on `PATH` under your home that it
can write (for example `~/.local/bin`), unless another `mdstack` is already
on `PATH`; otherwise it prints the one line to add to your shell profile. It
never edits a shell rc file. `--name NAME` names the launcher and its link
`NAME` instead, for a [second root](#a-second-root-on-one-machine-1324).
`--dry-run` prints the plan; a re-run with
nothing to change prints `no changes`. `mdstack --version` prints the
running bundle's tag.

`mdstack upgrade --version vX.Y.Z` (or `--latest`, the latest GitHub
release) then works like an end-user upgrade: it fetches and verifies the
bundle into `releases/`, upgrades `--project`, then every other project whose
`install.json`, under the same state root, runs from that `releases/`
directory, and only then flips `releases/current`, so the launcher follows
with no `PATH` change. Bootstrap records the project path in `install.json`;
a record from before #1317 gives it through its `Run mdstack up --project`
step when that file still matches the state's `config.toml` copy. A dry run,
a failed project or a record whose project cannot be found leaves `current`
where it was, and the last names the `--project` upgrade to run first. Rollback is the same
command with the previous tag: the bundle still on disk is fetched again,
reused once it matches, and `current` flips back
([bootstrap Q8](../bootstrap.md#q8-idempotency-upgrade-and-uninstall)).
`mdstack doctor` warns on a missing or stale launcher in the profile's
root (`paths.root`, else `$CREW_ROOT` or `~/.mdstack`) and on a `PATH` that
resolves its name to something else.

A user-level install set up by `mdstack install`, `layout --write` and `up`
has no `install.json`. `mdstack upgrade` adopts it before it upgrades
(#1616): the `paths.mdstack` link must point at a release with a `VERSION`
and `cli/mdstack` that has a `releases/current` link beside it. The state's
`VERSION` must match that release, and its `config.toml` copy must match
`--project`. `--dry-run` reports the adoption and stops; `--yes` writes the
record, then upgrades. An install that does not verify is not adopted: the
refusal names the mismatch and points at `mdstack bootstrap`. Adoption covers
a tmux install only.

Create `crew:*` labels only with `mdstack doctor --fix`. Never make them by
hand. `--fix` also resets a runbook label's color and description to the
runbook's values. An extra `crew:*` name is still a namespace collision.

### mdstack migrate

```sh
cli/mdstack migrate --project <old>/config.toml --to <new>/config.toml [--org-profile <path>]
```

`mdstack migrate` previews moving a stopped crew from the old profile's layout
to the new one's (#1178); both must name the same repo. It writes nothing and
prints:

- `map OLD -> NEW`: each changed path, most specific first. A whole-path
  reference to an old directory resolves as the checkout before the home (a
  run record's `repo`); a path under it as the state, worktree root, live dir
  or bundle before the home.
- `move` of the project's state directory and the live dir; `copy-move`
  of each builder run copy under the old worktree root (its own clone
  borrowing the checkout's objects, [confinement](#confinement));
  `worktree-move` of each registered worktree there;
  `keep` of each other directory there; `archive` of the old lead and
  watcher process identities.
- `rewrite FILE (N refs)` for each operational state file (run records and
  briefs, lead briefs and events, inboxes, status files, the spawn and wake
  queues, the watcher state) and the new profile that cite an old path.
  Historical evidence (verdicts, trains, retained, ci, triage, schedule)
  moves with the state directory unchanged.
- `copy` of the home's `.claude/settings.local.json` with its paths
  rewritten.
- `owner:` steps crew never takes: Claude Code memory and Codex trust are
  keyed by absolute path, so carrying them is the owner's call.
- `blocked:` reasons, exit 1: the old session or watcher is live (run
  `mdstack down --preserve` first), the land lock is held, the two checkouts are
  not one git repository, a destination exists, or a settings hook other than
  the mdstack guard cites an old path whose new path needs shell quoting.

`--apply` runs the same plan and refuses while anything is blocked. It moves
the state directory, archives the process identities and saves each file's
original before rewriting it, all under `<new state>/migration/<stamp>/`,
moves each builder run copy as a directory and repairs its own linked
worktrees (a nested evidence tree) with `git worktree repair`, moves each
registered worktree with `git worktree move`, rewrites the
operational files and copies the settings (the mdstack guard is re-quoted
argument by argument; any other hook keeps its shell text with only the paths
replaced). Message ids and `ack:`/`done:` lines are kept, and each status
file's watcher offset is recomputed from its rewritten prefix, so nothing
replays or is skipped. Each completed step goes to `journal.json`; on a
failure it prints the completed steps and their shell-quoted rollback commands and exits
with 1. It ends with `map.json` (old to new, rewritten and kept paths) and the
next steps: `mdstack layout --write`, then `mdstack up --coordinator-only` with the
new profile. Unregistered directories stay where they are for the owner's
cleanup.

`--project` and `--to` may each be a team reference `<file>#<repo>` (#1347).
The file is the profile that moves and is rewritten, and it may sit outside
every clone: the repo section's `checkout` names the git repository both
sides must share. Only that repo's state folder, its `[repos.<repo>]` section
and the `[team]` table change; a sibling repo's state folder and section
stay as they are. Operational records keep the `#<repo>` suffix, and
the next steps name the new reference. With an explicit `team.name`
([team files](../configuration/team-files.md#schema-and-example)), a new file
name such as `config.toml` keeps the team's state root and session.

```sh
cli/mdstack migrate --project ~/.mdstack/config.toml --rename-to <owner>/<new> [--apply]
```

`--rename-to` plans a repository rename in place of `--to` (#1234,
[runbooks/repo-rename.md](../runbooks/repo-rename.md)). The new profile is
the old one with the repo name changed, so only the state directory
`<owner>__<name>` moves; the owner must stay. On top of the plan above it
prints `name` lines for the repo slug and the tmux session, `keep` lines for
profile paths that hold the old name by choice, `rewrite` of the profile (the
`[repo]` name, quoted slugs and state paths) and of the home's `.claude/settings.local.json` in place, and
`owner:` steps: the GitHub rename, which comes before `--apply`, each host's
job root and the optional remote URL.

### mdstack spawn

```sh
cli/mdstack spawn <role> --issue <n> | --pr <n> | --sweep | --docs-pass | --reflection <window> [--log <n>] [--input-sha <sha>] [--run-id <id>] [--pass <pass>] [--round <k>] [--head <sha>] [--rereview-id <id>] [--tier <tier>] [--project <config.toml>]
```

`mdstack spawn` (#132) follows [Spawn and kill](#spawn-and-kill) steps 2 to 7;
step 1, the band cap queue, is under [mdstack dequeue](#mdstack-dequeue) (#136):

- Roles and passes: `builder --issue <n>` (`build`), `builder --issue <n>
  --pr <n> --pass fix` (a restart; fix rounds normally reuse the window),
  `reviewer --pr <n> [--pass review|validate|recheck] [--round <k>]` and
  `synthesizer --pr <n>` (`land`), and `researcher --sweep`, a
  [triage sweep](../triage.md#host) with no item (window `riley-sweep`,
  claim `researcher-sweep`, worktree `sweep-<sha7>-researcher-research/`).
  A sweep's Item names, after `milestone close:`, the queued closed
  milestones it takes; they are recorded as taken in
  `triage/milestones-taken.json` only once its window started (#374).
  `researcher --docs-pass` is a [docs pass](../project-docs.md#docs-pass)
  with no item (window `riley-docs`, claim `researcher-docs`, worktree
  `docs-<sha7>-researcher-research/`); its Item names each `[docs] repos`
  scan, `<state-dir>/<owner>__<repo>/docs/scan.json`. It shares the
  `researchers` cap and queue, and refuses before any claim, queue entry or
  window unless `[docs] enabled` is true (#1026). `researcher --reflection
  <window>` is a [reflection](../self-improve.md#reflection) run with no
  item (window `riley-reflection`, claim `researcher-reflection`, worktree
  `reflection-<sha7>-researcher-research/` at the input SHA). Its run ID
  (default minted at the request), log issue, input SHA (default the
  default branch head at the request) and window are fixed when requested
  and kept through the queue, dequeue and restart; restart refuses once the
  log holds a report covering the window, and `route` relays the
  `done: reflection` report URL and reaps only that window's run. It shares
  the `researchers` cap and refuses with `--issue`, `--pr`, `--sweep`,
  `--docs-pass` or `--train` (#1520). It refuses when the session is not
  reachable (the socket check), the window name is taken, the band is full,
  the claim exists or `mdstack up` has not rendered the role brief.
- Worktree: a detached checkout of a fresh `git fetch` of
  `origin/<default-branch>`, or of `refs/pull/<n>/head` for a `--pr` pass,
  at `<worktree-root>/<n>-<sha7>-<role>-<pass>/` (a reviewer's is
  `<n>-<sha7>-reviewer-r<k>-<pass>/`, so each round gets its own). A failed fetch refuses (no
  stale base); so do a path inside the primary checkout and an existing path.
- Engine: the first `claude-code` or `codex` entry of `engines.<tier>.order`
  with that tier's effort. The tier is `--tier`, else for a builder or
  reviewer the item's recorded `tier=`
  ([Tiers](../roles.md#tiers)), else the role's `default_tier`, else
  `default`; the queue entry and run record keep it. A reviewer or
  validator skips every engine named on an `Engine:` line in the PR's commit
  messages, in the trailer block or not (`none` merge-ups excluded). With no
  such line it skips the engine in the PR-body builder marker and in each
  builder run record for the PR or its closing issues. With none of these
  the builder engine is unknown and spawn refuses; it never assumes
  non-Claude (#442).
  The synthesizer takes the tier's first engine as is, like a builder.
  Muse Code and OpenCode have no interactive launch yet and are skipped.
- Window: `-e` passes `CREW_ROLE`, `CREW_ID`, `CREW_STATE`, `CREW_STATUS`,
  `CREW_INBOX`, `CREW_BRIEF`, the login `CREW_IDENTITY`, `CREW_BIN`, the
  absolute path of this checkout's `cli/mdstack`, and `CREW_PROJECT`, the
  absolute path of the `config.toml` given to `mdstack up`; never a token.
  `CREW_BRIEF` is `runs/<window>.brief.md`: the rendered role brief plus the
  run's item, pass, worktree, base SHA, engine and claim path.
- Standing notes: `runtime.options.notes` maps each role to an ordered list
  of file paths ([profile](../profile.md#runtime)). `mdstack spawn` appends the
  current contents verbatim after the run details, each under
  `## Runtime note: <path>` naming the configured file. Absolute paths are
  used as given; relative paths resolve from `<state-dir>/<owner>__<repo>`.
  A missing or unreadable file fails the spawn with its role and path before
  creating a claim, worktree or window. No configured notes leaves the brief
  unchanged. `mdstack up` applies coordinator notes before creating window 0.
  Configure standing policy once instead of sending files to every new window.
- `--pass recheck` starts one fresh reviewer session at the merge head, using
  the previous approval's `--round <k>`. It checks `git show --remerge-diff`
  for resolution hunks and reruns acceptance checks, then posts Review and
  Validation sections and one final `pass=verdict` marker. It never starts a
  separate validation session. Non-mechanical resolution posts no verdict
  and reports `done: #<n> <sha> recheck escalate`; `mdstack route` starts full
  review at that head and approval round, then validation on a review pass.
  Every merge gate still applies.
- Step summaries: `.crew/` is added to the worktree's `info/exclude`, so
  `.crew/runs/**` never counts as unlanded work.
- Permissions: `runtime.options.permission_mode` picks the window's flags
  (#293). The default, `bypass`, follows firstmate: agents run any command
  in their worktree without asking, with no approval prompt and, for Codex,
  no sandbox. The worktree and the role's identity are the boundary.

  | Mode | Claude Code | Codex |
  |---|---|---|
  | `bypass` (default) | `--permission-mode bypassPermissions --settings '{"skipDangerousModePermissionPrompt":true}'`: no bypass warning screen, set for this process only; the user's settings are never edited | `--dangerously-bypass-approvals-and-sandbox` |
  | `auto` | `--permission-mode auto` | `-s workspace-write -a on-request -c sandbox_workspace_write.network_access=true` |
  | `safe` | `--permission-mode acceptEdits` (the launch before #293) | `-s workspace-write -c sandbox_workspace_write.network_access=true` |

  Every mode adds `--add-dir <state-dir>/<owner>__<repo>`, so a pass reads
  its brief and writes `$CREW_STATUS` and `verdicts/` there (#234 F15).
  Claude Code gets it before the mode flags: its `--add-dir` takes several
  values and would swallow the pointer. Residual gap in `auto` and `safe`:
  Claude Code still asks for commands no allow rule covers, and Codex
  `workspace-write` keeps a linked worktree's git metadata
  (`<repo>/.git/worktrees/<name>`) read-only, so `git commit` and
  `git push` can still prompt or fail (#288). Crew roles never answer a
  prompt; those modes suit only a host that auto-approves.
  Codex also gets `--add-dir <real path of the worktree's git common dir>`
  in every mode. A linked worktree keeps its refs and objects there,
  outside the worktree, so a host that wraps Codex in an external sandbox
  writable only under the working directory and `--add-dir` paths would
  otherwise block `git branch`, `commit` and `push` (#384).
  Claude Code exits at once on `bypass` as root, before any session, so
  spawn, restart and lead launches refuse a Claude Code role window in
  `bypass` when the launching process's effective uid is 0, before the
  window opens, naming the cause and the two fixes: run the crew as a
  non-root user, or use `auto` or `safe`. A remote run is checked on its
  execution host, by that host's uid (#738).
- Pre-trust: Codex gets one `-c 'projects={"<worktree>"={trust_level="trusted"},"<repo-root>"={trust_level="trusted"}}'`
  (real paths), a `projects` table for that process only;
  `~/.codex/config.toml` is never edited. For a linked worktree Codex
  applies trust to the repository root, the parent of
  `git rev-parse --git-common-dir` (#288), and the old
  `projects."<dir>".trust_level` form did not stop its `Trust this folder?`
  dialog on codex-cli 0.164 (#262). Claude Code has no per-process trust
  option. It keys a linked worktree's trust on the repository root, so
  accepting `ash`'s trust dialog once in the project covers the role
  worktrees; a trusted parent directory did not (Claude Code 2.1.310). An
  untrusted window waits at the dialog with `claude` in the foreground,
  which liveness probes `ambiguous`.
- <a id="confinement"></a>Confinement (#1252, the
  [M47 B5 boundary](../specs/portable.md#m47-installs-and-working-copies)):
  a builder's worktree is its own copy, not a linked worktree. Spawn runs
  `git init`, points `objects/info/alternates` at the shared checkout's
  object store (read-only borrowing), adds `origin` with the checkout's
  fetch and push URLs, sets `origin/<default>` to the fetched default head
  and detaches at the run's head. Its refs, index and worktree list belong
  to the run; a nested evidence worktree registers in the copy. Other roles
  keep linked worktrees. Claude Code builders start the harness in the
  stable `paths.worktree_root`, with the run copy added by `--add-dir` and
  an appended instruction to run shell commands with an explicit `cd` to
  the assigned copy and use absolute file paths. Trusting that startup root
  (or a parent outside a repository) once per host covers future spawns and
  restarts; trust on the checkout alone does not cover independent copies.
  Before dispatch, run `mkdir -p <worktree-root> && cd <worktree-root> && claude`,
  pick `Yes, I trust this folder`, then `/exit`. `mdstack doctor` reports
  missing trust as `claude copy trust`; `up`, spawn and restart warn before
  creating a window (spawn before its claim). mdstack never writes user-level
  harness config. Linked reviewer and researcher launches retain their
  checkout trust boundary. A builder launch is **confined** when its harness
  applies an OS write sandbox whose writable roots mdstack sets: today Codex
  with `permission_mode` `safe` or `auto`. Its roots are then the worktree,
  its own `.git` and the state dir: the launch adds
  `-c sandbox_workspace_write.exclude_slash_tmp=true -c sandbox_workspace_write.exclude_tmpdir_env_var=true`
  and sets `TMPDIR=<worktree>/.crew/tmp`, so sibling copies and the shared
  checkout, its `.git` included, are read-only and a raw
  `git -C <shared> worktree remove`, `rm -rf` of a sibling or a write into
  its metadata fails. Unconfined: `bypass` on any harness, Claude Code, Pi,
  Cursor, Muse, a role-host builder, a `paths.worktree_root` or checkout
  inside the state dir, and a restart in a worktree spawned before #1252.
  `runtime.options.confinement = "enforce"` refuses an unconfined builder
  spawn or restart before any claim or window, naming the reason; `off`
  (default) launches it and records `"confined": false` with the reason in
  the run record, and `mdstack doctor` warns with each unconfined live
  builder run. #1252's guarantee is never claimed for an unconfined run.
  Owner step for a confined crew: none beyond a Codex that can apply its
  sandbox on the host. Spawn, restart and `mdstack doctor` check that with
  `codex sandbox -- true`. A `codex` on `PATH` that is a launcher already
  running Codex inside its own OS sandbox fails it: macOS refuses the
  nested sandbox (`sandbox_apply`, exit 71). The launcher's sandbox is not
  the boundary either, since it leaves sibling copies writable. The run is
  unconfined there: `enforce` refuses it, `off` records the probe's
  reason. The probe runs where `mdstack spawn` runs, so a spawn from inside
  an agent sandbox fails it too. The live check of a host is
  `MDSTACK_LIVE_CONFINEMENT=1 python3 dev/tests/environments/test-crew-spawn.py -v ConfinementLive`
  from a shell outside any agent sandbox: two builders through spawn and a
  real Codex launch, where A's session fails to remove B or write the shared
  metadata and removes its own nested tree. On a host that fails the probe
  its first spawn stops at once with the cause. It spends model tokens and
  never runs in CI. `mdstack migrate` moves a builder copy as a directory.
- Sandbox inheritance: `runtime.options.sandbox_env = "<NAME>=<value>"`
  sets the sandbox variable for every window, including window 0. The
  launching environment's `CREW_SANDBOX_ENV=<NAME>=<value>` overrides it.
  Every window gets both `-e <NAME>=<value>` and `CREW_SANDBOX_ENV`, so
  later spawn/restart commands retain the setting. mdstack never names the
  org's variable.
- Verify start: within `--timeout` seconds (default 15), `claude` or
  `codex` must be a foreground process of the pane's tty (the evidence
  [mdstack status](#mdstack-status) takes for `alive`), or
  `#{pane_current_command}` must be that name or the name of the file it
  resolves to on `PATH`. tmux reports a symlinked binary by its target's
  name, so the native Claude Code installer's `claude` reads as its version,
  such as `2.1.314` (#286); a version-shaped name never counts on its own.
  A dead pane reads as `dead`, not
  as its launch's first word (`export`), and fails at once. Otherwise it prints `failed:`,
  cleans up as `mdstack kill` does and records no run.
- Records: the claim (`claims/builder-issue<n>` for a build,
  `claims/reviewer-pr<n>-<sha7>-r<k>-<pass>` for a reviewer, so review and
  validate at one head coexist, else `claims/<role>-pr<n>-<sha7>`, created
  atomically) and `runs/<window>.json`. A reviewer's record also names its
  verdict file, `verdicts/pr<n>-<sha7>-r<k>-<pass>.md`.

### mdstack kill

```sh
cli/mdstack kill <window> [--discard --reason "<why>"] [--project <config.toml>]
```

`mdstack kill <window>` refuses window 0. It sends `SIGTERM` to the pane's
process group (the group of `#{pane_pid}`), waits up to 2 s, sends `SIGKILL`
to anything left, waits again and checks the group is gone; Codex ignores
the `SIGHUP` that `kill-window` sends. Before signaling, it collects descendant
process groups too, so detached tool sessions are terminated during kill,
reap and reclaim. If a group survives, it keeps the
window, worktree and state files and exits 1. Otherwise it kills the window, removes the
worktree named in `runs/<window>.json` (with the build output inside it)
only when it sits directly under `<worktree-root>`, then deletes that run's
`runs/<window>.*` files (record, brief and any scratch file such as a PR
body), inbox, status file and claim, and a reviewer run's verdict
file, except the `review` file: it survives both reviewer windows for
re-validation at the same head. The coordinator removes retained review files
when that PR's head moves or it merges/closes. On a successful kill, the oldest
queued spawn in the freed band starts automatically through `mdstack dequeue`;
other bands stay queued. The watcher reports terminal status to the coordinator
and does not reap windows itself.

It never removes work that has not landed (#160 row 3). Before removing the
worktree it lists:

- every uncommitted or untracked path (`git status --porcelain
  --untracked-files=all`; ignored build output does not count);
- every commit on `HEAD` not contained in a fresh fetch of
  `origin/<default-branch>`, of the worktree's branch on `origin`, or of
  `refs/pull/<n>/head` for a run on PR `<n>`. A failed default-branch fetch
  counts as unlanded too.

If the list is not empty, the window is still stopped but the worktree, run
record, brief and claim stay; `mdstack kill` prints the paths and commit SHAs
and exits 1. Reviewer and validator worktrees normally hold nothing and pass.
`mdstack kill <window> --discard --reason "<why>"` removes anyway, after
posting the reason and the list as a coordinator note on the run's item: a
narrative post on its PR (`gh pr review <n> --comment`), else a comment on
its issue (`gh issue comment <n>`). If the post fails, nothing is removed.
`--discard` without `--reason` is refused before anything is stopped.

### mdstack gc

```sh
cli/mdstack gc [--apply] [--max <n>] [--project <config.toml>]
```

Lifecycle reaping removes a run's worktree at kill, close-out and idle
reclaim. `mdstack gc` is the backstop for what it missed: a run record whose
window is gone (a refused kill, a lost `pr-merged` event) and a directory
directly under `<worktree-root>` that no run record names. It never scans
outside that root, so legacy trees elsewhere and #1166's keep list stay
untouched, and runs on a role host are left to their host. A symlink under
the root is listed as kept and never followed, and `--apply` checks the
boundary again right before it deletes anything.

The default is a dry run: one line per candidate, `path`, run, `keep` or
`remove`, and the reason. A candidate is `remove` only when its PR is merged
(the run's PR, else a merged PR whose head is the copy's `HEAD`, so a
squash-merged copy with its branch deleted still proves) and the C6 check
in [mdstack kill](#mdstack-kill) finds nothing unlanded. It is kept, with
the reason, when its window is live, another run or a
[working-copy claim](#mdstack-copy-claim) references it, it is an orphan
younger than an hour (a spawn in progress), it holds nested worktrees, its
PR is open or closed without merging, no merged PR matches, it has unlanded
work or it cannot be read. Closed-unmerged work is never removed here; it
needs `mdstack kill --discard --reason` on the owner's decision.

`--apply` re-checks each candidate just before removing it and removes at
most `--max` (default 10): a linked worktree with `git worktree remove`
(never `--force`), a builder's own copy (#1252) by deleting its directory,
then the run's records through the kill path. A failed removal prints
`failed` with the error, keeps the run's records and makes the command exit
1; nothing falls back to a forced removal. A rerun with nothing left removes
nothing. [mdstack route](#mdstack-route) runs `mdstack gc --apply --max 5`
on each watcher backstop wake and writes its report to
`<state-dir>/<owner>__<repo>/gc/backstop.txt`, not the watcher's output;
only a failure prints one line naming that file.

**Provider decision (#316, M47).** Git stays the only worktree provider and
there is no provider profile key. The alternative considered was
[treehouse](https://github.com/kunchenguid/treehouse), which pools
worktrees and leases one per task with an owner claim. It is deferred: it
would add lease identity, return, reset and recovery, and role-host
contracts that #316 did not settle. Builder copies now own their Git
metadata (#1252), which a pooled linked worktree would undo. A later
provider needs its own spec slice.

### mdstack guard

```sh
cli/mdstack guard --state <state-dir>/<owner>__<repo>
```

`mdstack guard` is the turn-end guard ([Q1](#q1-wake)). Unless `CREW_ROLE` is
`coordinator` it exits 0 with no output. It blocks the turn end
(`{"decision": "block", ...}` on stdout) when work is in flight, meaning a
run record in `runs/`, a non-empty `wake/queue.jsonl` or an open owner ask
record in `asks/<n>.json` ([C8](#runtime-contract); an unreadable record
still counts), and no watcher is armed, meaning `wake/watcher.pid` names no
live process. When the PID file is missing or stale but a live watcher holds
`wake/watcher.lock`, it does not block and prints a `systemMessage` naming
that case instead (#399). It blocks at most once per stop cycle: when the hook input has
`stop_hook_active: true` (the coordinator is already continuing because of
this hook), it allows the stop with a `systemMessage` warning instead, so it
never loops. Empty or malformed hook input counts as not active.

Codex recipe (documented, not installed by `mdstack up`; verified on
codex-cli 0.164.0, #170): Codex runs its `notify` program after each turn,
with the `agent-turn-complete` JSON as the last argument. Feed that JSON to
the same check and type the fixed wake line into `ash` when it blocks:

```toml
notify = ["sh", "-c", "printf %s \"$1\" | python3 <mdstack>/cli/mdstack guard --state <state-dir>/<owner>__<repo> | grep -q block && { tmux send-keys -t crew-<owner>-<repo>:0 -l 'wake: turn-end guard'; sleep 0.3; tmux send-keys -t crew-<owner>-<repo>:0 Enter; }", "crew-guard"]
```

A payload whose `input-messages` ends with `wake: turn-end guard` (the
turn this recipe started) counts as `stop_hook_active`, so the guard blocks
at most once per stop cycle here too. Without that, a coordinator that
ends the wake turn without re-arming the watcher looped one turn every few
seconds on the real CLI. The line is typed with `-l` and `Enter` follows
0.3 s later: typed in one `send-keys` with `Enter`, it stayed in the composer
unsent (the paste burst of #308). On a thread's first turn Codex also
notifies for its title turn, so a second wake line can follow; it joins the
same wake turn or the next, which the guard then lets end.

### mdstack send

`mdstack send <window> <kind> <ref>... [--project <config.toml>]
[--wait-ack <secs>]` (#133) messages a role window by reference
([C3](#runtime-contract)):

- Refs only: each ref is an issue or PR number (`#171`), a full 40-character
  SHA, an `https://` link or a path, at most 200 characters, with no
  whitespace. A ref that opens a diff hunk (`---`, `+++`, `@@`) or holds
  `Traceback` is refused, and so is a message line over 1024 bytes. `<kind>`
  is a short lower-case word such as `fix` or `ci-red`. A refusal writes
  nothing and exits 2.
- It refuses (exit 1) when the window is not in the session. Otherwise it
  appends one JSON line `{"id", "kind", "refs", "from", "ts"}` to
  `inbox/<window>.jsonl` (`from` is `$CREW_ID`, else `$CREW_ROLE`, else
  `coordinator`), nudges the window through the adapter and prints
  `crew: sent <msg-id> to <window>`. The inbox file is the message; the
  nudge carries no payload.
- The nudge is typed once and its submit confirmed (#308). `mdstack send`
  reads the composer at the cursor (`capture-pane` and
  `#{cursor_x} #{cursor_y}`): the rows from the prompt glyph (Codex `›`,
  Claude Code `❯`) down to the cursor row. When they hold nothing but earlier
  `inbox: <msg-id>` lines and the cursor ends them, it clears them with
  `C-u`, twice per line (in both TUIs `C-u` clears a line, then joins the
  empty line to the one above; `Escape` is not used: it interrupts a running
  turn, and Codex keeps the draft). Other text is never cleared. Then it
  types `inbox: <msg-id>` (`send-keys -l`), waits 0.3 s (an `Enter` right
  behind typed text lands in Codex's paste burst and adds a newline instead
  of submitting, which stacked the nudges in #308) and presses `Enter`.
  While the nudge is still in the composer it retries `Enter` up to 3
  times, never retyping. If the nudge stays, or the clear left earlier
  lines, it prints `crew: nudge not submitted: <msg-id> to <window>: ...;
  treat <window> as ambiguous` and exits 4 without waiting for an ack; the
  inbox line stays. A screen with no composer at the cursor counts as
  submitted.
- A window showing a dialog (the list under [mdstack status](#mdstack-status))
  gets no key at all (#315): a Claude Code permission or Codex approval
  prompt preselects yes, so the nudge's `Enter` could approve a command
  nobody reviewed. `mdstack send` checks before the clear and before each
  `Enter` retry; on a dialog it prints the exit-4 line above with the reason
  `dialog: ...` and exits 4, and the inbox line stays. The watcher's next
  scan reports the same run as a `dialog:` wake.
- Delivery is proven only by a line `ack: <msg-id>` in
  `status/<window>.status`; the composer check proves only the submit.
  `--wait-ack <secs>`
  waits for it, and `mdstack acked <window> <msg-id> [--wait <secs>]` checks
  later: exit 0 when acked, 3 with `crew: no ack: ...` when not. The
  re-nudge and liveness check after a missed ack are the coordinator's;
  what follows an exit 4 or a second miss is under [Q7](#q7-failure).
- Lifecycle (interrupt, exit, relaunch) never goes through a message; use
  `mdstack kill` and `mdstack spawn`.

### mdstack brief

```sh
cli/mdstack brief --issue <n> --role builder --tier default --engine 'codex gpt-6.1-sol medium' --base <full-sha> --project <config.toml>
```

Issue mode (#237) prints the selected rendered role instructions, the live
issue URL/title and fenced task body (including acceptance criteria), launch
notes, then the existing `## This run` block. Task text is data, not operating
instructions. Render the role first; unavailable role/issue inputs or invalid
role, tier, engine/model/effort, pass, base or run fields refuse with exit 2
and no partial brief. It creates no claim, worktree or session. The caller
still resolves live flavor and dispatches through the lead.

Without `--issue`, every existing flag, byte of run-block output and exit
code is preserved. `--item` in issue mode must match the selected issue;
`--pass` defaults to the selected role's first pass. Other run-block flags
remain available. This helper reads GitHub issues; unavailable tracker reads
refuse. `mdstack brief --help` lists all flags.

### mdstack merge-up

```sh
cli/mdstack merge-up <pr> --head <H> --actor <builder-run> --repo <owned-copy> --check 'python3 scripts/check-repo.py' --check 'python3 scripts/run-tests.py <affected-test-files>' --project <config.toml>
```

The coordinator dispatches the actual builder/operator who owns the copy.
The caller's builder run must name this PR or its linked issue; retained
issue builders use their current copy/head, not the original launch head.
The copy must belong to the configured checkout, be on the live PR branch
at full H, and have no dirty tracked/untracked work or Git operation.
Another writer's run or host-wide copy claim refuses; the associated run
and its own claim are allowed. Ownership, pause, held/closed/escalated PRs,
forks, foreign push destinations and a rebase strategy refuse before merge.

Fetch the default branch through a private ref, pin merge base B and updated
base U, then create a two-parent H/U merge using only declared Git drivers.
No attributes are added and unresolved feature conflicts restore H without
push/post. A current copy exits 0 with no note. Each required `--check`
is parsed as argv and run in the copy without shell evaluation; a failed
check restores H. Select checks under the existing merge-up testing policy.

After checks and a fresh live H/ownership/pause read, push normally to the
verified branch and read back the published full head. Post one signed
actual-builder COMMENT note at that head with B/H/U/new-head, merge and
configured-union paths, strict patch comparison and check output. The
`pass=merge-up` marker retains `round=n/a verdict=n/a`; success never
approves or changes tags. A differing patch explicitly requires delta
review through the existing router; approval carry stays with the synthesizer.

Exit 2 reports refusal/failure. After a push attempt, retain the local merge
and report the published head or an unconfirmed push for reconciliation.
If a note response is lost, read reviews back before retrying; a confirmed
note succeeds once. A failed note requires readback/reconciliation without
another push. No rebase, force-push, squash or approval is performed.

### mdstack ack

```sh
cli/mdstack ack intake <pr> --head <full-sha> --actor <run> --project <config.toml>
cli/mdstack ack merge-up <pr> --head <full-sha> --actor <run> --verified-base <B> --verified-head <H> --updated-base <U> --project <config.toml>
cli/mdstack ack steer <pr> --head <full-sha> --actor <coordinator-window> --source <comment-id> --command hold --engine 'claude-code sonnet medium' --harness claude-code --start <UTC-time> --project <config.toml>
```

Marker acknowledgement (#237) is separate from inbox delivery (`action ack`
and `acked`). It posts a native head-bound COMMENT review with the existing
marker and actual author's signature/usage, never approval or a state-tag
change. Exit 0 means posted or already acknowledged; exit 2 is refusal.

- `intake`: actual reviewer run, non-draft live review round 1, after the
  precheck gate and actual builder-engine exclusion. Once per intake/head.
- `merge-up`: actual reviewer at the current review round, after the latest
  signed changes verdict at B/H. Verify two parents H/U, U on the default
  branch, empty remerge hunks and strict B/H versus U/new-head patch identity.
  Retain unresolved findings; this ack supplies no passing verdict or
  portable approval. Once per merge-up/head.
- `steer`: actual coordinator, recognized command and an unedited owner
  comment on this PR, once per source `cmd-id`. It records receipt only:
  no command execution, round reset or hold removal. Only `hold` and
  `escalate` qualify; only `escalate` is permitted on a held PR. Commands
  whose markers have downstream effects refuse: `merge-ok`, `resume`,
  `cutover`, `plan-ok`, `rereview`, `away`, `away-return`, `rework`, `urgent`,
  `stop-landing`, `resume-landing` and `hold-release`. Use the existing
  owner-decision dispatcher for those commands. This implements the
  [coordinator's clarification](https://github.com/mw-ding/mdstack/issues/237#issuecomment-6851108497)
  without changing consumers or marker schemas.

The actor must match the calling role and run record, PR/head and active
GitHub identity. A coordinator without a run record supplies its actual
engine/model/effort, harness and pass start as shown above, and uses its
configured window name. Pause, unavailable ownership, short/stale SHA,
wrong phase/role/source and unsupported live reads refuse before posting.
Live state is re-read under a per-PR lock just before posting. Failed post
responses are reconciled by readback; an uncertain result requires another
live read before retry. No inbox receipt proves a marker acknowledgement.

### mdstack review, verdict and recheck

```sh
cli/mdstack review <pr> --head <full-sha> --round <k> --project <config.toml>
cli/mdstack verdict <pr> --head <full-sha> --base <reviewed-base> --round <k> --actor <run> --project <config.toml>
cli/mdstack recheck <pr> --head <full-sha> --round <approval-round> --project <config.toml>
```

The #238 helpers reuse the existing lead, pool and native checked poster.
`review` hands the explicit head/round to the reviewer lead, preserving
admission, claims, precheck, flavor and actual builder-engine exclusion.
After passing review its completion routes a separate fresh validation
session when required. The coordinator runs neither pass. An open full
rereview needs `--rereview-id <steer-id>`; completed/running requests are
deduplicated, and pending handoffs retain the lead's existing identity.

`verdict` consumes completed `## Review` and `## Validation` sections. Its
defaults read the retained review file and the actor's verdict file;
`--review` and `--validation` can name completed section files explicitly.
Review changes supplies only Review and `skipped: review failed`; recheck
supplies both sections in its single file. The poster assembles the final
marker, actual-author signature and usage. It runs no review or validation
and invents no evidence. Section results determine pass/changes; failed
validation produces changes. An eligible skip is submitted by the review
actor, includes the normal skipped-validation marker and `Reason:`, and
must satisfy live item/path rigor. Under `behaviour`, the helper accepts
that skip only for justified `docs/*.md` wording changes; other shapes
use independent validation. `validation = off` also permits a justified skip.

Wrong actor, unavailable/full-SHA bindings, missing/duplicate sections or
markers, inconsistent results, obsolete reset/rereview and already-completed
passes refuse with exit 2 and no review/tag writes. Ownership, pause and
live head are rechecked before posting one COMMENT review at the native
full head. Approved/changes tags are set together and read back; changes
at the live round cap also sets escalated and directs blockers to the
coordinator. A lost post response is reconciled by readback. A posted
verdict with failed tag readback needs tag reconciliation, never a second
verdict. These tmux helpers install no mirror hold, as in the existing tmux
binding; the synthesizer still checks the mirror gate before land.

`recheck` requests the existing explicit fresh pass for an approved
two-parent merge, retaining the prior approval round. The worker checks
bounded remerge hunks and reruns acceptance checks in that one session.
Unconfirmed merges or an open full rereview route normal review; broader
content escalates through the existing completion path. Behind alone never
requests recheck, and clean-update verdict portability remains the default.
These commands have no approval or landing power and no delete endpoint.

### mdstack acked

```sh
cli/mdstack acked <window> <msg-id> [--wait <secs>] [--project <config.toml>]
```

`mdstack acked` (#133) checks delivery of an `mdstack send` message: its exit codes
and the `ack: <msg-id>` rule are under [mdstack send](#mdstack-send).

### mdstack action

```sh
cli/mdstack action <name> [<op>] [--actor <run>] [--item <ref>] [--head <sha>] [<action flags>] [--json] [--project <config.toml>]
cli/mdstack action --capabilities [--json] [--project <config.toml>]
```

`mdstack action` (#1232) is this runtime's binding of the
[actions CLI contract](../../actions/cli.md): names, flags, exit codes and
the JSON result are the contract's, and the role policy fragments call it
instead of editing state files by hand. It works the same on the tmux and
herdr session backends and from session runs, since it acts on the files
those already read. The run is `--actor` (default `$CREW_ID`) and the
profile `--project` (default `$CREW_PROJECT`).

| Action | What it does here |
|---|---|
| `check-ownership --for start\|write\|land` | Reads the control item as [`mdstack ownership`](#ownership-fallback) does; refused `not-owner` when it would exit 1 |
| `heartbeat [--claim <handle>]` | Rewrites the `heartbeat:` line in the claim the run's record (`runs/<run>.json`) names; refused `not-held` for any other claim or with no run record. tmux runtime only |
| `notify --to <run> --kind <kind> --ref <ref>...` | [`mdstack send`](#mdstack-send) after the `start` ownership check; `pending` until the receiver's ack. tmux runtime only |
| `ack --message <id>` | Appends `ack: <id>` to `status/<run>.status` once, for a message in the run's inbox; `mdstack acked` then exits 0 |
| `report --status <s> --ref <ref>... [--reason <text>]` | Appends `<status>: <refs> <reason>` to `status/<run>.status`, the line route, watch and `mdstack status` read |

Every other action is `unsupported` (exit 6) until it is wired; `--capabilities`
lists them. Their documented flags are still checked first, so a bad command
line is `usage` (exit 2). An explicit `--key` is kept under
`actions/keys/`: a repeat with the same inputs returns the first `completed`,
`pending` or `unknown` outcome with no second effect (a repeated `notify`
reads its receipt and answers `completed` once acked); `check-ownership` is a
read and always checks the control item now. Without `--key` the
key is the derived one plus a nonce, so a re-nudge or a repeated status line
stays a new effect, as today. Reason codes this binding adds: `not-held`,
`no-recipient` (no such window), `solo` (a solo item's fix refs, which are
never delivered to a builder) and `key-conflict` (a `--key` reused with
other inputs). Other `crew` commands keep their own exit codes.

### mdstack feedback

```sh
cli/mdstack feedback --class <slug> --summary <text> [--window <name>] [--repo <owner>/<repo>] [--sign <text>] [--dry-run] [--project <config.toml>]
```

`mdstack feedback` (#299) files a `runtime-blocker` intake card, or comments on
the open card with the same Failure class. It follows the
[runtime-blocker recipe](../self-improve.md#runtime-blocker-recipe). It reads
open issues with `gh issue list`, then posts with `gh issue create` or
`gh issue comment`, after the `write` ownership check.

### mdstack poll

```sh
cli/mdstack poll [--once] [--project <config.toml>]
```

`mdstack poll [--once] [--project <config.toml>]` (#134) is the GitHub wake
source of [Q1](#q1-wake) and the decision function of [C2](#runtime-contract).
It needs no model and makes read-only `gh` calls only, with the logged-in
identity:

- `gh pr list --state open --json number,state,headRefOid,labels,statusCheckRollup,reviews,mergeable`;
  a PR counts as a crew PR when it has a `crew:*` label. A tracked PR missing
  from that list is read with `gh pr view <n>` for its merged or closed state.
- `gh issue list --state open --label crew:ready --json number,labels,assignees`.
- For a changed head with a live pass verdict at the previous head,
  `gh api repos/<owner>/<repo>/commits/<head>` and
  `gh api repos/<owner>/<repo>/compare/<second-parent>...<default-branch>`
  confirm exactly two parents, first parent equal to the previous head, and
  second parent on the default branch (`identical` or `ahead`). Other pushes
  remain `new-head`; the synthesizer checks patch identity; changed patches route to the builder
  and delta re-review.

Per crew PR it keeps the head SHA, the CI rollup (`passed`, `failed` or
`pending`) and the latest verdict at head, read only from hidden `crew:v1`
lines with `role=reviewer-validator pass=verdict sha=<head>`
([protocol §4](../protocol.md#4-marker-conventions)). It compares them with
`poll-state.json` in a pure function and emits one event per change, each to
exactly one consuming role ([protocol §8](../protocol.md#8-safety)):

| Change | Event | Consumer |
|---|---|---|
| Opened or pushed crew PR has a new head, regardless of CI state | `new-head` | reviewer |
| Only new commit is a default-branch merge atop a previously approved head | `merge-up` | synthesizer (patch identity and live gates) |
| CI rollup at head turns green | `ci-passed` | synthesizer (retry only with approval at head) |
| CI rollup at head turns red after a job started, or startup evidence is unknown | `ci-failed` | builder |
| Failed Actions jobs have zero steps, with no other code failure | `ci-infra` | coordinator (infrastructure recovery; never a builder fix) |
| New `verdict=changes` at head | `review-changes-requested` | builder |
| New `verdict=pass` at head | `review-approved` | synthesizer |
| New builder `pass=fix` marker at head after a `verdict=changes` there (an evidence-only fix: no new commit, so no `new-head`) | `fix-at-head` | reviewer |
| Tracked PR merged / closed | `pr-merged` / `pr-closed` | coordinator |
| Owner lifts `crew:hold`, `crew:escalated` or `crew:needs-md` from an open crew PR or `crew:ready` issue (it leaves `poll-state.json`'s `held`) | `hold-released` | coordinator (#394) |
| A held item (in `held`) or one with an open `asks/<n>.json` gains an owner comment or PR review, hold and ask unchanged | `owner-answer` | coordinator (#394) |
| `crew:ready` issue newly assigned | `issue-assigned` | builder |
| Open crew PR head turns `CONFLICTING` (`UNKNOWN` is no conflict), including after another land | `pr-conflicting` | builder (merge-up via the builder lead, before any CI) |
| Express change: new builder `pass=selfgate verdict=pass` at head with CI green | `selfgate-passed` | synthesizer |
| New authenticated coordinator `pass=steer cmd=merge-ok` record at the current full head SHA, whatever CI shows; duplicates, other heads or authors and a legacy state entry emit none (#1835) | `merge-ok-recorded` | synthesizer (a reason to re-read gates; never approval or a CI waiver) |

A change that resolves express ([express lane](../express-lane.md#routing),
`crew:express` plus the item record and class rules, read as `mdstack train`
does) emits no `new-head` or `fix-at-head`, and emits `ci-passed` only with a
selfgate pass at head. A merge-up atop a head with a selfgate pass emits
`merge-up` and carries that pass to the merged head for `ci-passed`; the
synthesizer checks its portability. An unreadable resolution runs the crew lane. When an
express change falls back to the crew lane, poll emits `new-head` at its
current head so normal review starts.

With `triage.enabled` ([always-on triage](../triage.md), set by the
`[triage]` profile of #748), each poll also runs the zero-model triage scan.
For each `triage.repos` tracker (default: the project repo) it reads
`gh issue list --state open` and `--state closed` and rewrites
`triage/queue.json`: the open issues that pass the
[skip rules](../triage.md#skip-rules), plus issues whose newest `pass=triage`
record has a later owner comment, each with exact-key duplicate hints
(failure class, Source, named paths, normalized title), the
`templates/intake-candidate.md` card fields and P0 signals from the
`triage.rules` file (built-in defaults when unset or unreadable). An
unreadable repo or item is recorded there, not dropped. A newly seen P0
candidate appends one `triage-p0` wake for the coordinator, which starts the
single-item sweep; the scan wakes no one else. The scan also reads the
project repo's closed milestones (`gh api .../milestones?state=closed`) and
lists each one closed since the previous scan (the first scan records a
baseline in `triage/milestones.json`) under `milestones` in the queue, until
a started sweep records it in `triage/milestones-taken.json`
(milestone-close sweep, #374).

No change emits nothing. Each event is one wake record appended to
`wake/queue.jsonl` before `poll-state.json` is saved (at least once):

```json
{"id": "poll-<ts>-<hex>", "source": "poll", "reason": "poll", "event": "new-head", "consumer": "reviewer", "refs": ["#171", "<head-sha>"], "round": 1, "ts": "<ts>"}
```

`new-head` and `fix-at-head` records also carry `round`: the verdict round
`k` the review pass is for, 1 + the `verdict=changes` verdict markers since
the latest `cutover` or `resume` marker
([protocol §5](../protocol.md#5-rounds-and-escalation)). A `fix-at-head`
record is the code side of the coordinator's rule for a builder `done:` at
the round's verdict head: spawn the review pass at that head with
`--round <k>`. A `new-head` or `fix-at-head` for a head that already has
the newest round's verdict, with no builder fix note or open rereview after
it, opens no new round (#1124).

A `merge-up` record replaces `new-head` and carries `previous_head` (the
approved first parent) and the approval's `round`. The coordinator sends
it to the synthesizer for protocol §7 verdict portability; a later CI-green
wake retries the same candidate. `mdstack route` leaves clean `merge-up` records
queued for this handoff. Identical content needs no reviewer session. If the
synthesizer reports `no-verified-base`, the coordinator re-reads head/holds
and dispatches normal review and independent validation at that head to
record the base, then retries portability.
Conflicts or differing patches route through the builder, then delta
re-review and independent validation at the updated head. GitHub runs no
`pull_request` CI on a conflicting PR, so poll emits `pr-conflicting` once
per head and conflict (an `UNKNOWN` read keeps the head's last known value),
and `mdstack route` re-reads the PR and hands the builder lead one `merge-up`
handoff (`#<pr> <head-sha>`) without waiting for checks or a sweep (#1398).
A closed PR, moved head or resolved conflict consumes the wake; held,
escalated, draft, solo or lead-less work stays queued for the coordinator.
A conflict that clears and returns emits again. An open rereview
steer at head always routes full review and validation. Explicit `recheck`
recovery and CI-fix passes remain available; they are not required for an
identical clean base update. A `recheck escalate` status routes full review at
the same head and round, followed by independent validation on a pass.

`reason` and the string `event` are the keys every queue record shares with
the watcher (#135); `refs` are `mdstack send` refs. The coordinator drains the queue and routes each
record to the consumer's window by `mdstack send`, or `mdstack spawn` when the
window does not exist; poll itself types into no window. The first run, with
no `poll-state.json`, records a baseline and emits nothing; the
[§6](../protocol.md#6-duties-on-wake-all-roles) step 3 sweep covers anything
older. Without `--once` it polls every `runtime.options.poll_interval` seconds
(default 60), in a dedicated window or under the watcher (#135); a failed `gh`
call is printed and retried on the next tick, and exits 1 with `--once`.
A rate-limited `gh` read is never retried: poll reads the exhausted quota's
reset from `gh api rate_limit` (60 s for a secondary limit), prints
`crew: gh <cmd> rate-limited until <UTC>: <error>`, sleeps until then without
`--once`, and exits 75 with it (#1300).
Labels such as `crew:hold` are not filtered: the consumer applies its own
guard.

**Intake ack (#303).** `mdstack poll` has no `pr-opened` event. The
[§6](../protocol.md#6-duties-on-wake-all-roles) `pr-opened` ack comes from
the reviewer instead: the round-1 `review` pass posts it as its first act
after the live re-read and engine check (reviewer brief, step 3), a COMMENT
review `[<ReviewerBot>/ack] intake @ <sha7>` with a `pass=ack` marker and
`round=n/a verdict=n/a`. It is once per head, never from the `validate` pass
or a later round, and a respawned pass finds the post and adds none. It
appears when review starts on the opened head, even with CI pending or red.
The same `new-head` event starts review after a push; it does not add another
round-1 intake ack where an ack already exists at that head.

**CI and review handoff (#380).** `ci-passed` never spawns review. It wakes the
synthesizer to retry a merge only when an approval exists at head; all §7 gates
still apply. The coordinator holds `ci-failed` while that head's review or
validation is running or queued, persisting refs in
`ci/<n>-<head-sha>.json`. When the active pass reports, it
re-reads head, CI and findings and sends one builder fix carrying both CI
failures and review/validation refs. Zero-step startup failures are
`ci-infra`: the coordinator handles infrastructure recovery without a builder
fix, and validation proceeds after a passed review. CI must still be green
before merge. If review passed but CI is still red from a started or unknown job,
it sends `ci-red` with the review refs instead of starting validation on a
head about to move. If CI recovered, it drops the held failure and continues
validation or land. A red signal with no pass in flight goes straight to the
builder, including after approval. A CI fix after approval starts the light
re-check at the new head: fresh review and validation sessions inspect the
fix hunks and rerun acceptance checks using the approval's round number
(protocol §6). Other builder pushes get normal review; no per-PR CI-only
fast path is introduced. Status and poll events are
de-duplicated by PR/head/pass/round; held refs for older heads are discarded.
Files referenced in a handoff remain until the builder reports `done:` or
posts its fix marker, so it can read both CI failures and findings.
An evidence-only fix still starts the next review once through `fix-at-head`
or the builder's `done:` line. Review and validation record observed CI state
as information only, and independently reproduced failures remain findings.

### mdstack attach

```sh
cli/mdstack attach <window>|<role>|builders [--rw] [--project <config.toml>]
```

`mdstack attach` (#138) is the owner's live view of a window:

- `<window>` is a window name (`ben-7`, `crew-status`). `<role>` (`builder`,
  `reviewer`, `synthesizer`, `coordinator`) picks the role's only window in
  its band; with several it lists them and refuses.
- It runs `tmux attach-session -r -t =<session>:<index>`: read-only, so
  keystrokes never reach the agent; detach with the tmux prefix and `d`.
  `--rw` attaches interactively, for typing to the agent.
- Attaching selects that window as the session's current window, which other
  clients attached to the session also see. The layout (indices, names) does
  not change.
- `mdstack attach builders` opens a temporary tiled view of the builder band
  (10–19): a separate session `crew-<owner>-<repo>-builders-<pid>` with one
  pane per builder window, each showing the last lines of that window's
  screen (`capture-pane`, refreshed every second). It never moves, joins or
  renumbers a crew window, and the view session is killed on detach.

### mdstack connect

```sh
cli/mdstack connect [--project <config.toml>] <alias> [<session>] [-- <transport args>...]
```

`mdstack connect` (#1036) opens the owner's own shell on an inventory host,
or reattaches-or-creates a tmux session there, through the transport in
`hosts.<name>.connect`. See
[Connect to a host](multi-device.md#connect-to-a-host).

### mdstack logs

```sh
cli/mdstack logs <window> [-n <lines>] [-f] [--project <config.toml>]
```

`mdstack logs` (#138) prints the last `-n` lines (default 20) of the run's step
summary: the newest `<worktree>/.crew/runs/**/summary.md` under the worktree
in `runs/<window>.json` ([observe.md](../observe.md#tmux-attach-and-logs)).
`-f` follows it with `tail -f`. It never prints raw logs (`steps/`).

### mdstack copy-claim

```sh
cli/mdstack copy-claim acquire|release|show --path <dir> [--run <id>] [--item <text>] [--project <config.toml>]
```

Host-wide working-copy claim (#391,
[working-copy claims](multi-device.md#working-copy-claims)). Before a run
uses an existing copy, its coordinator runs `acquire`; a claim held by
another crew (another state root) or run exits 1 and names the holder, and
the run is not dispatched. `release` drops the claim only for its holder
(same state root and `--run`) and exits 1 for anyone else; no claim is a
no-op. `show` prints the claim record as JSON, or `null`. `mdstack spawn`
claims each worktree it adds and `mdstack kill` releases it.

### mdstack land-lock

```sh
cli/mdstack land-lock acquire|release [--project <config.toml>]
```

Serial land ([C7](#runtime-contract), #136). `sam` runs `acquire` before the
[§7](../protocol.md#7-merge-gate-synthesizer) re-check and `release` after the
merge post. `acquire` takes `flock` on `locks/merge.lock` without waiting
and leaves a detached holder process with the lock open (its PID and
process start time in `locks/merge.pid`), so the lock outlives the command.
While it is held, a second `acquire` fails fast (exit 1, `land lock ... is
held`) and `mdstack down` refuses. `release` signals the holder only while the
lock is held and the live process with the recorded PID has the recorded
start time and is an `mdstack land-lock acquire`; otherwise (a stale or reused
PID, or a lock held by another process) it signals nothing and exits 1.
It then waits for the unlock and removes `merge.pid`; with no lock held it
is a no-op. The lock is local to the machine and to the selected repo:
`merge.pid` records its `context` and both commands refuse one naming another
repo ([Team pools](#team-pools), #1859).

Under an asynchronous land, `sam` holds the lock until the terminal land
status and the merge post, and takes no lock when the backend declares
`serializes = true`
([asynchronous land](../interfaces.md#asynchronous-land-design), #873).

### mdstack land

```sh
cli/mdstack land status|request|done [--project <config.toml>] --pr <n> --head <head-sha>
cli/mdstack land resume [--project <config.toml>]
```

Request, status and restart handling for an
[asynchronous land](../interfaces.md#asynchronous-land-design) (#873 slices
B2 to B4). Under `land.mode = "async"` the synthesizer brief's step 3
renders it in place of the locked land, and the builder brief runs
`change.publish` after opening when the backend declares
`land.opens_draft`. It refuses a change backend whose `land.mode` is `sync`, and
runs the backend map's `change.land-status`, `change.read-head` and
`change.land` with `<n>` and `<head-sha>` filled. `status` reads the land
status once and prints it, exiting 1 when it is unknown. `request` first
records a land intent, `land/<n>-<head-sha>.json` in the state dir, then
reads the status and requests only on `none`, and only while the change head
still equals `--head` (a stale head sends nothing). A failed request call is
resolved by reading the status again, never by a resend; `none` after it
blocks until the gate check reruns. It then polls every
`land_poll_interval` seconds. `landed <revision>` exits 0, marks the intent
landed and prints the merge record's `record:` line (the landed revision,
the checked head and, under `land.tests_against_tip`, the backend check) and
its `marker:` line (`pass=merge` with `sha=` the checked head and
`landed=` the landed revision). `failed`, an unknown or malformed status and
`land_timeout` print `blocked:` and exit 1; `failed`, a stale head and a
`none` after the request drop the intent, while a timeout or an unknown
status keeps it.

`resume` runs on every wake before anything else. For each recorded intent
it reads the status and never requests: `queued` or `landing` polls as
above, `landed` prints the pending record lines, and `none` (never requested
at that head) or `failed` drops the intent with a `blocked:` line. `done`
clears an intent after its merge post and the default-branch CI check at the
landed revision, and refuses one not marked landed, so
only a confirmed `landed` completes a land. It takes no land lock and builds
no train. `mdstack train build` and `bisect` refuse when the backend declares
`land.tests_against_tip`, naming that key.

### mdstack schedule

```sh
cli/mdstack schedule snapshot [--project <config.toml>]
cli/mdstack schedule summary [--project <config.toml>]
```

`mdstack schedule snapshot` (#620) prints one JSON object with every
[scheduler input](../scheduling.md#inputs): both pools' pending demand by
kind, run records with their worker state (`busy`, `idle` or `exited`),
reservations, outstanding land messages in the synthesizer inbox, open trains,
open milestones and open issues with their
`Depends on #n` refs, normalized load, memory pressure (macOS pressure level;
Linux `/proc/pressure/memory` `some avg10`), local suites, gateway errors in
the last 10 minutes and each pool's cap. A failed read is `unknown` for that
input only. It is read-only: it writes nothing and admits nothing; the
scheduler's decision step is a later build issue.

The [target](../scheduling.md#target) T (#623) is a function over a snapshot,
kept with its last change time and recent starts in `schedule/target.json`;
no command calls it until the decision step. Its watermarks and ramp are the
`load_high`, `load_low`, `error_high`, `schedule_interval` and
`schedule_ramp` [profile options](../profile.md). Linux memory pressure is high
at `some avg10` 10.0, or 40.0 under the `critical`
[memory threshold](../scheduling.md#memory-threshold), and low below 1.0.

`mdstack schedule summary` (#628) prints the
[one-line summary](../scheduling.md#observability) of the latest decision:
busy workers and reservations against each pool's cap, T, the machine
signals, queued demand by kind, current deferrals by first reason, held
demand by ref (an issue or PR under `crew:hold`, never granted), and
orphans with their pane process ids: live tool sessions of runs whose item
is closed, and of crew windows (other than window 0) with no run or lead
record. `terminal` counts and names reviewer runs whose last status line is
`done:` and that still hold a slot. The scheduler never stops them. `mdstack watch` prints it after its exit line. Finishing work
(classes 1–6) deferred for `stuck_after` seconds (default 1800) is one
`schedule-stuck` wake per (pool, ref, first deferral), carrying the latest
snapshot; `schedule/deferred.json` keeps each current defer's first time.

### mdstack train

```sh
cli/mdstack train check <pr>... [--project <config.toml>]
cli/mdstack train build <pr>... [--after <n>] [--no-wait] [--local] [--grace <s>] [--interval <s>] [--timeout <s>] [--project <config.toml>]
cli/mdstack train build --train <n> [--no-wait] [--local] [--grace <s>] [--interval <s>] [--timeout <s>] [--project <config.toml>]
cli/mdstack train delegate <pr>... [--after <n>] [--project <config.toml>]
cli/mdstack train wait <n> [--project <config.toml>]
cli/mdstack train land <n> <pr> [--mirror-deferred] [--project <config.toml>]
cli/mdstack train close <n> [--project <config.toml>]
cli/mdstack train route <n> [--project <config.toml>]
cli/mdstack train bisect <n> [--project <config.toml>]
```

A merge train (#321) tests approved PRs together once, then lands them with
no catch-up between them: the merge queue GitHub does not offer private
repos on GitHub Free. `sam` uses it when two or more PRs are ready at once
([land rules](../protocol.md#land-rules-and-merge-trains), the synthesizer
brief). [§7](../protocol.md#7-merge-gate-synthesizer) counts a green train
whose tested state is the current default branch as tested with it.

The profile option `runtime.options.lone_pr_land` defaults to `"train"`,
which retains the tested-with-default-branch gate and batching rules. With
`"direct"`, exactly one ready PR lands immediately, even behind the default
branch, without update-branch or a one-member train. Two or more ready PRs
still train, regardless of `train_min`. Under the land lock, re-survey the
ready set before squashing; only the tested-with-default-branch gate is
waived, and the merge record names `lone_pr_land=direct` and the lone-ready
condition. Every other §7 gate still applies at head. When a train's drops
leave exactly one member, `train build` collapses it to that direct land
(below, #1425).

After a direct land, the synthesizer waits for the default-branch push CI run
at the PR's exact merge commit SHA, checking all required jobs. On
`pr-merged`, `mdstack route` keeps a synthesizer whose spawn PR is the merged
one alive until it writes `done: #<n>` or `blocked:` for it. Missing or
pending CI is not green. On red it reports
`blocked: main red after #<n> <run-url>`; the coordinator files a blocking
`crew:ready` fix issue titled `main-red: <summary>` linking the landed PR and
run, prioritizes it over new feature work and keeps the blocker open until
default-branch CI is green.

A builder builds every train, so `sam` stays free for other lands (#1391).
`train delegate <pr>...` reserves the next train number with
`trains/delegated-<n>.json` (the base, each member's full head SHA, `after`
and the `synthesizer` window to report to) and hands the build to the
builder lead as kind `train`, refs only: `train-<n>`, the base, then
`#<pr> <head-sha>` per member. When the handoff fails, the delegation closes
and `sam` runs `train build` itself. The lead starts a train worker,
`ben-train<n>`, with `mdstack spawn builder --train <n>` (no issue; a full
band queues it, and `dequeue --ref train-<n>` starts it). The worker runs
`train build --train <n>`: it builds the recorded members on the recorded
base and waits for CI. A base that moved (a land made meanwhile) saves a
closed record with `stopped` and builds nothing. A member whose head moved
is dropped as `head-moved` and is never routed for merge-up. On `ci=fail`
the worker runs `train bisect <n>`. It then sends `sam`
`train-done train-<n> <record>` and appends `done: train-<n> <record>`.
It never squashes, lands, approves or posts a verdict. While it builds,
`sam` keeps surveying, gating and landing ready PRs that are not members,
serially under the land lock; `open_trains` counts an open delegation, so
`mdstack route` keeps `sam` alive until it ends. A dead or missing train
worker restarts once through the lead; on a second failure the lead sends
`sam` `train-failed train-<n>`, and `train close <n>` ends the delegation
(and its train, if built) before `sam` re-surveys. `train land` still
re-checks the tested default branch, so a train that a concurrent land made
stale stops there and its members train again.

`train check` is read-only: it reports `gate pr=... sha=... name=...
status=pass|blocked|manual reason=...` for every requested PR, and exits 1
if any gate is blocked. It checks head verdict markers (including formal
approval and passing review/validate), state/permission, sensitive merge-ok,
CI and evidence artifact presence. Gate `train-merge` is the survey-time
pre-filter (#1425): it runs `build`'s drop checks for each PR alone on the
freshly fetched default branch, with `git merge-tree` in a temporary bare
clone without `info/attributes`, never a worktree merge. A conflict, a
changed verified patch (`content-different`) or `no-verified-base` blocks
it; route that PR to merge-up before it joins a train. It also blocks a
PR still at the head an open collapsed train dropped (step 6) while that
train's survivor is open. Gate `release-cut` (#1433) blocks a release cut
(its diff adds a new version heading to the CHANGELOG) whose head does not
contain the fetched default branch: update-branch it so `release.yml`
`validate` re-runs on current `main`; the direct land never takes a stale
cut. While a cut is open, gate `state-permission` (and `train land`) holds
every other PR that adds a fragment under `changes/unreleased/` until the
cut lands. An unreadable open-PR list or `CHANGELOG.md` patch blocks both. Mirror deployment freshness, evidence
agreement or reasoned N/A, grant scope, engine attribution, linkage and
runtime/inbox gates explicitly require manual verification. Filter blockers
before building and resolve manual gates with the synthesizer's §7 check.
A snapshot supplies no merge authorization and never replaces the land check.

`build --no-wait` pushes and records `ci=pending`, then returns exit 0
without waiting; `train wait <n>` collects CI and records its result. Build
N+1 with `--after N --no-wait` while N runs CI or lands: its base is N's
tested tip, and members already in N are excluded. A predecessor with
`ci=fail` is refused, even if its close has not completed. Preparation overlaps;
landing remains serial under C7. N+1 cannot land until N completes and its
final squash tree exactly matches N+1's tested base. After a predecessor's
real stop (including red CI or an early close), `wait` or `land` closes the old
successor and rebuilds its members on the newly fetched default branch,
using a new train number and fresh CI. Read the new record before landing.
No speculative result is used after its predecessor stops. A transient
predecessor pause keeps the successor and its CI for resumption.

`train build` takes ready PRs in dependency order, then approval order, and
keeps that order. PRs that change the same paths stay in the train together
([overlap](../scheduling.md#overlap)): each merges onto the train branch in
turn, and a PR is dropped only when its merge actually conflicts
(`reason=conflict`). Train CI tests the combined result, so the land gate is
unchanged. Each member's changed paths from its head's merge base are still
recorded.

The build then:

1. Numbers the train one above the highest `crew/train-<n>` branch on the
   remote and `trains/train-<n>.json` record, so it never reuses a live
   train branch or a recorded number.
2. In a temporary clone `<worktree-root>/train-<n>-<base7>` (objects shared
   with the repo) at the freshly fetched default branch (the train base),
   merges each PR head (`refs/pull/<pr>/head`) with `--no-ff`, in order.
   PRs touching common paths that merge cleanly stay members. A conflicting
   train merge is aborted and that PR is dropped. The clone has no
   `info/attributes` and the merges ignore a global attributes file: a local
   merge driver such as `merge=union` hid conflicts that GitHub's merge then
   hit (train 4).
3. Skips the local full suite by default and records `local=skipped`.
   `--local` or `runtime.options.train_local_checks = true` opts in to
   `scripts/check-repo.py` and every `dev/tests/*/test-*.py` the train has
   (`local=none` when there are none). An opted-in failure stops before
   any push. A local pre-check is a future CI-velocity option, not a merge
   gate; green train CI remains required.
4. Pushes `crew/train-<n>` (never a force push) and opens a draft PR titled
   `mdstack train <n> (CI only, do not merge)`. It has no `crew:*` label, so
   `mdstack poll` ignores it.
5. Waits `--grace` seconds (default 20), since `gh pr checks` exits
   non-zero until checks register, then reads `gh pr checks --json` every
   `--interval` seconds (default 20), counting no checks yet as pending,
   until all are done or `--timeout` (default 1800) passes. A red or
   timed-out train's PR is closed and its branch deleted.
6. Decides the path from the surviving members before step 3 and records
   it as `path` (#1425): `train` for two or more, or one with no drop;
   `none` when every PR dropped; `direct` when drops leave exactly one
   member on the default branch (no `--after`, not a bisect half) and
   `runtime.options.lone_pr_land = "direct"`. A `direct` build skips steps
   3–5: no local suite, push, train PR or CI wait. It saves the record
   closed with `ci=none` and `path_reason` `collapsed-to-direct: train <n>
   dropped #<pr> (<reason>), ...`, keeps its drops queued and prints
   `direct pr=<pr> head=<sha> reason=<path_reason>`. `sam` then lands that
   PR by the direct land rule: every §7 gate at its own head, CI green
   there, the lone-ready re-survey under the land lock (two or more ready
   PRs build a new train instead), and the merge record names
   `lone_pr_land=direct` and the `path_reason`. In that re-survey a PR the
   collapse dropped is not ready while it is still at its dropped head and
   the survivor is open (`train check` gate `train-merge`), so the same
   conflicting pair never re-trains. After the direct land, or when `sam`
   gives it up, `train route <n>` routes the drops: only then does main hold
   the conflict a merge-up resolves. `train land` refuses the
   collapsed train. With `lone_pr_land = "train"`, the one-member train runs
   as before.
7. Removes the clone, saves the record and prints these lines; exit 0
   on green CI, pending CI with `--no-wait`, or `path=direct`:

```text
member pr=<pr> head=<head-sha> step=<train commit after this member>
dropped pr=<pr> reason=conflict
deferred pr=<pr> reason=predecessor-member
ci-link <CI run URL>
direct pr=<pr> head=<head-sha> reason=collapsed-to-direct: train <n> dropped #<pr> (conflict)
train n=<n> branch=crew/train-<n> base=<sha> sha=<train-sha> pr=<train-pr> local=skipped ci=pass
```

A profile may name a recorded owner standing mirror deferral with
`runtime.options.mirror_deferral` (default `"none"`), including its source and
scope, for example `"#110 roadmap PRs per #140"`. The synthesizer reads that
decision and verifies each PR is covered and does not change live Grok Bot
behaviour. For those PRs it satisfies the mirror gate without a per-PR
coordinator comment or label removal, and names the deferral in the merge
record. Uncovered PRs, unreadable decisions and live Grok Bot behaviour changes
still require a real mirror. This gives no merge permission and gate changes
still need the owner's per-PR merge-ok. For a train member using it, pass
`--mirror-deferred` to record the configured source; without that flag the
record says `Mirror deferral used: none`. The flag refuses to land when no
profile deferral is configured; scope checking remains the synthesizer's duty.

`train land <n> <pr>` lands one member, under the land lock
([C7](#runtime-contract)). `<pr>` must be the next unlanded member, so `sam`
re-runs the whole [§7](../protocol.md#7-merge-gate-synthesizer) check at
that member's head right before each call (synthesizer brief). It refuses a
train without green CI or already closed. Right before the squash it
re-checks, and stops on the first miss:

- the default branch is still the train's tested state: the train base, then
  the commit the previous member's land made;
- the PR head is the head the train tested;
- no `crew:escalated`, `crew:changes` or `crew:hold`;
- a pass verdict at that head, read as `mdstack poll` reads it;
- no open rereview: no `pass=steer cmd=rereview` at head without a later
  verdict at head;
- no open coordinator hold: no `hold-until-#<n>` in a review or comment
  whose item `#<n>` is still open;
- a `pass=steer cmd=merge-ok` marker at head, or a `merge_grant` other than
  `none` (`sam` checks the grant's scope); a
  [spec change](../protocol.md#spec-change-definition-and-spec-grant-scope)
  (`crew:spec` or a `spec.paths` match, both rename paths, read from the PR's
  files) also needs `merge_grant_scope` to list `spec`, and an unreadable
  path set stops the land;
- GitHub reports the PR `MERGEABLE` against the current default branch.
  `UNKNOWN` and transient API errors are retried up to 10 reads, at most
  3 seconds apart (`--interval` can shorten that);
- the train CI is still green; a pending re-run pauses, and red CI closes it.

It then runs `gh pr merge <pr> --squash --match-head-commit <head>`, checks
that the squash sits on the previous state with the tree of that member's
train commit, and posts the `[<SynthesizerBot>/merge]` record citing the
train branch, SHA, base, train PR and CI run. A real gate failure, or the last
member, ends the train: it closes the train PR and deletes the train branch.
A transient stop prints `paused`, retains the branch and green CI, and can
resume with the same `train land` call. A transient merge-record post failure
retains the completed squash and retries only its post, never another squash.
Resuming re-checks the current default
branch against the tested state; a moved branch closes the train.
`train close <n>` is for a real failure in `sam`'s own check, never an
unsettled mergeability or API read.
On completion or a real stop, deferred/dropped members are automatically
routed: mergeable PRs get a head-bound `update-branch` API call; real conflicts
go by `fix` inbox to an attached builder, or spawn a builder for the linked
issue (respecting the band cap). Holds and transient errors stay queued.
`train route <n>` retries queued entries on a later synthesizer wake without
a coordinator turn; successful routes are not dispatched twice. Each dropped
entry records its merge-up status and last error. A builder reads the train
record to resolve the conflict and uses the existing merge-up re-check.

Each call prints:

```text
landed pr=<pr> head=<head-sha> merge=<merge-sha>
stopped pr=<pr> reason=<why>
paused pr=<pr> reason=<transient cause>
merge-up pr=<pr> status=updated|builder|queued
train-report n=<n> members=<prs> landed=<prs> dropped=<pr:reason,...> stop=<cause> path=train|direct:collapsed-to-direct|none:no-member
train n=<n> landed=<k>/<m> next=<pr>
train n=<n> landed=<k>/<m> pr-closed=yes branch-deleted=yes
```

The record's `report` field and every member merge record carry the same
`train-report` fields. The synthesizer copies that line into its status file
after every build, land, pause or close, so the coordinator can report the
whole outcome in one line.

`train bisect <n>` takes a red, unlanded train and splits its members into
halves, preserving landing order. It builds each half on the default branch,
waits for CI, and recurses on every red half until it reports `culprit pr=<pr>`
for a failing singleton. Diagnostic trains close without landing. Changed heads,
a moved diagnostic base, incomplete composition or pending/timed-out CI stop
bisection without inferring a culprit from that test.

Culprits are recorded as `dropped=<pr>:ci-culprit` in the original train report.
The remaining members are rebuilt together on the freshly fetched default
branch, with fresh CI and no `--after` on a failed train. The command prints
`bisect train=<n> remaining=<new-n> ci=pass`; the synthesizer reads that new
record, checks every §7 gate, and lands its members in order through the normal
head-bound `train land <new-n> <pr>` path. Bisection supplies no merge permission.
If both halves pass, the combined retry must also pass before reporting
`culprit=none green-on-retry`. A red combined retry remains unresolved (an
interaction or flake); nothing lands.

On a backend that declares a rebase update, `train build` and
`train bisect` refuse before creating any clone, branch or PR, and `sam`
lands ready PRs one at a time
([rebase update from base](../interfaces.md#rebase-update-from-base), #874).

### mdstack dequeue

```sh
cli/mdstack dequeue [--project <config.toml>] [--timeout <seconds>]
```

Caps per band ([Q6](#q6-concurrency), #136): `runtime.options.builders`
(default 5) for busy builders in windows 10–19 and `runtime.options.reviewers`
(default 2) for reviewer passes 20–29. A builder is idle after `done:` until
an inbox message arrives; an unacknowledged message or an `ack:` after the
last completion or a running tool child makes it busy. Idle time comes from
its status-file timestamp. The watcher routes expiry through the builder lead
(or mechanically with no lead) using `mdstack dequeue --idle-only`; it only
reclaims idle clean/pushed work, with output in `retained/builders/`.
When busy builders reach their cap, or all physical band slots are occupied,
`mdstack spawn` creates no window, worktree or claim; it appends the request
(role, issue, PR, pass, round, tier, queued time) as one JSON line to
`spawn-queue.jsonl`, prints `queued: <role> <pass> <item> ...` and exits 0.
A window name already running is still refused, not queued.

`mdstack kill` runs the dequeue step automatically for the freed band.
`mdstack route` also dequeues after removing a terminal window; the coordinator
does the same in recovery. Explicit dequeue takes the oldest queued request
whose band has a free slot, removes it from the queue
and spawns it as `mdstack spawn` does; requests for a full band stay queued in
order. When the builder band is physically full but its busy cap permits
queued work, dequeue reclaims the oldest idle builder with no unpushed or
uncommitted work, then spawns the queued request. Builder `done:` also runs
dequeue; capped builder spawns queue a mechanical wake so the watcher runs
route promptly. With no eligible request, the spawn stays queued and
`nothing to dequeue` names why: a pool whose lead owns it (outside that lead
or `CREW_POOL=<role>`), no free slot, or no request matching `--ref` (#1100).

### mdstack route

```sh
cli/mdstack route [--project <config.toml>] [--timeout <seconds>]
```

The watcher calls this step before waking window 0 (#434). It consumes
`new-head` by spawning review, passed-review `done:` by spawning validation,
and terminal reviewer or synthesizer `done:` by killing and dequeuing.
A backstop wake also runs [mdstack gc](#mdstack-gc) `--apply --max 5`
(#316).
A synthesizer's `done: #<n> <sha> stale` (`done: #<n> stale` for a message
with no SHA) completes the acknowledged `land` message with those refs, so a
closed, merged or superseded land is never restored on the next spawn (#1187).
A terminal reviewer is reaped once even when its PR has since merged, closed,
moved to a new head or been held, whether the router or the reviewer lead
(including an `mdstack kill` reclaim saved as the completion) routes it first (#719).
A reviewer's `done: #<n> stale` for a PR merged or closed by anyone, another
runtime included, is terminal the same way (#811).
Builder completion retains the builder and runs dequeue; it and `fix-at-head` also start review once; an older head's
reviewer windows are removed before starting the new head.
`recheck escalate` starts review at the same head and round, then validation
on a pass; the recheck window is removed.
Red CI after a passed review stays queued for the combined findings handoff;
failed Actions jobs with zero steps become `ci-infra` for the coordinator
and allow validation to start. Job steps are read from the Actions jobs API;
unknown evidence or any started failed job remains `ci-failed`. Neither
classification waives green CI at merge. A `ci-failed` record whose head is
no longer the PR head is dropped, here and by `mdstack poll` in the queue. A
synthesizer `blocked: ... gate-status REVIEW_URL wait=<items>` line, whose
only unmet items are `ci`, `review`, `validation`, `selfgate` (an express
change, woken by `selfgate-passed`) or `train`, is recorded
without a coordinator wake; other gate-status blocks still wake it. A lead's
`mdstack send` of `unblocked` to the coordinator with the refs of an earlier
`blocked` message is appended to its inbox without a nudge (#578). Changes results retain their section
files after cleanup. Merged PRs get the close-out below; item windows are cleaned
up too.
`pr-closed` reaps the assigned builder without merged-PR label or branch cleanup.
A `fix` or `ci-red` send to a missing `ben-<issue>` with PR/head refs queues a
`builder-message` wake. Route checks the live PR, linkage and head, spawns the
builder's fix pass (or waits for its queued spawn), then delivers the refs.
Live builder messages continue through the existing inbox, including train
merge-ups; combined CI/review handoff rules remain in effect.

Merged-PR close-out (the coordinator brief points here, #1635): remove
`crew:approved`, `crew:hold`, `crew:in-review` and `crew:changes` (each if
present) from the PR, remove `crew:ready` from the issue it closed, and close
that issue with a note if GitHub left it open (never a reopened one, #846).
The land deletes an eligible head branch itself where the change backend maps
`change.land-delete-arg` (#395), so an ordinary land leaves nothing to delete.
Only if the head branch outlived the land, delete it with
`change.delete-branch`, and only when ALL of these hold, read from
`change.read-state` and `change.read-default-branch`: the PR is merged;
`isCrossRepository` is false; `<branch>` is read only from `headRefName`; the
branch differs from both the default branch and `baseRefName`. Otherwise skip
deletion and say why in the close-out note.

Spawns are deduplicated by PR/head/pass/round against live and queued runs,
section files and posted pass markers. An expected `--head` travels through
spawn and dequeue, so a head that changes after a read is refused. Ownership,
holds, escalation, draft and stale-head checks precede routing. Interrupted
batches stay under `wake/queue.jsonl.route-*` for retry. Failed actions and
records needing judgement remain queued for the coordinator. Mechanical
batches leave the watcher running without a model turn or coordinator nudge.

### mdstack watch

```sh
cli/mdstack watch [--project <config.toml>] [--stale <s>] [--idle-stall <s>] [--backstop <s>] [--source <command>]... [--source-timeout <s>] [--source-failures <n>] [--no-nudge] [--persistent [--renudge <s>]] [--detach]
```

The zero-token watcher of [Q1](#q1-wake) (#135). `mdstack up` (and
`mdstack upgrade`, after its reload) starts it with `--detach`: a
`--persistent` watcher with the `mdstack poll --once` source, in its own
session, its output appended to `wake/watcher.log`; `CREW_WATCHER=off` skips
that, for a coordinator that arms its own one-shot watcher (#1346). One
watcher runs per state dir: it holds `wake/watcher.lock` (flock) for its
whole life and writes its PID into that file too, so a second start,
simultaneous or not, exits 0 with
`crew: a watcher is already armed (pid N)` and touches neither the PID file
nor the watch state (#591, #399). Under that lock it writes its PID to
`wake/watcher.pid` (removed on exit only while it holds its own PID), then scans every `--interval` seconds
(default 5) and blocks until one of these is actionable:

- `status:` a new line in any `status/<window>.status` of a recorded run
  (read offsets persist in `wake/watch-state.json` with a digest of the read
  prefix, so a line wakes once, across watcher restarts and run-identity
  changes such as a lead restart that keeps its status file; a file shorter
  than its offset or with a changed prefix is a new run's and is read from the
  start, #819);
- `stale:` a run that probes `dead` or `missing`, or one with no status
  progress (status file, else run record) for `--stale` seconds (default 900),
  with no live tool session and no pane output within that interval. Tool
  commands launch separate process sessions; `ps stat` marks their leaders
  with `s`. The watcher walks helper descendants to find those live leaders. For a
  verified live pane, either signal appends a supervisor `heartbeat:` instead
  of waking the coordinator; persistent helpers sharing the harness session,
  harness wrappers and zombie children do not count. Dialogs still wake
  immediately. The supervisor never refreshes a dead or replaced pane,
  skipping a run still starting (no `start` and run-record mtime less than 60 s old),
  unless its last line is `failed:`, or `done:` for a reviewer or
  synthesizer run; a builder after `done:` is not flagged while live (it
  waits for fix rounds) but is when `dead` or `missing`; each (window, last
  progress) fires once, whatever its class; the record's `action` is `restart` for a first
  `dead` / `missing`, otherwise `escalate`, never a restart of a live run.
  A live lead with no undone inbox message, or a live synthesizer with no
  unacked message, uncompleted land, open train or held land lock, is idle,
  not stale (#578). A live run with work whose tmux pane printed nothing for
  `--idle-stall` seconds (default 1800, 30 min; `0` turns it off) is idle at
  its prompt with no tool call or turn: it wakes `stale` with liveness `idle`
  and action `escalate`, once per silence, however fresh its claim, heartbeat
  or status file and whatever runs beneath it (#1283); the reviewer pool
  escalates it even when its re-probe says `alive`. A builder after `done:`
  is exempt, and the herdr backend reports no pane activity, so it is not
  checked there. A long wait belongs in the harness's own background-task
  notification, never in a loop that refreshes a liveness file;
- `dialog:` a run that probes `ambiguous` with a blocking prompt or a
  fatal API error on its screen (the list under
  [mdstack status](#mdstack-status)), on the next scan (well inside
  60 s), not after `--stale`; once per (window, last progress), action
  `escalate`. The coordinator escalates to the owner and never types into
  the role window. Also window 0, when the watcher would have typed its
  wake line into a dialog (below);
- `poll:` each stdout line of a `--source` command (repeatable; the
  `mdstack poll` hook for #134). A source must be one-shot, for example
  `--source "cli/mdstack poll --once [--project <config.toml>]"`: each
  run is cut off after `--source-timeout` seconds (default 60, so a slow
  `mdstack poll` on a bad GitHub minute is not cut off) and killed, so a
  looping source never wedges the watcher. `mdstack poll` retries a transient
  `gh` failure (5xx, timeout, connection reset) with bounded backoff and
  exits 75 (`EX_TEMPFAIL`) if it persists. A cut-off run or an exit 75 is a
  line in `wake/incidents.jsonl`, not a wake; `--source-failures`
  (default 3) of them in a row from one source send one `source-failing:`
  wake with the count, and a clean run resets the count (#702). The
  sources run at most once per `--source-interval` seconds (default
  `runtime.options.poll_interval`, 60), not on every `--interval` scan, and
  the next due time persists in `wake/watch-state.json`, so a re-armed
  watcher does not poll at once. An exit-75 line
  `rate-limited until <UTC>` holds every source until that reset, at most
  an hour, so the watchers and roles sharing one GitHub login stop spending
  its quota (#1300). A
  source that grows `wake/queue.jsonl` itself during the call, as
  `mdstack poll` does, has its stdout ignored, so its events are queued once;
- `poll:` (or the record's own `reason`) new records in `wake/queue.jsonl`
  from another writer, such as an `mdstack poll` loop in its own window. The
  queue's inode, byte size and mtime persist in `wake/watch-state.json`; the
  records are already queued, so they are not appended again;
- `ask:` an open owner ask whose deadline has passed. The coordinator
  records each open ask's deadline in `asks/<n>.json` as
  `{"deadline": ...}` (ISO 8601 with its UTC offset;
  [C8](#runtime-contract)). Each (ask, deadline) fires once, on the first
  scan at or after the deadline, and the scan sleep is cut short so that
  scan lands on it, whatever the backstop. An unreadable deadline wakes at
  once;
- with `[triage] enabled` ([profile](../profile.md#triage)), no wake: each
  scan runs the triage sweep timer after its `--source` commands, so the
  timer reads the queue that scan's `mdstack poll` wrote, also on the first scan
  after a resume (#1098). The timer starts
  `mdstack spawn researcher --sweep` once `interval_hours` passed since the last
  slot in `triage/sweep.json` (at once with no slot recorded, so a crew waking
  overdue sweeps on its first scan), records the slot as `started`,
  `queued` or `failed: <reason>` (retried after 600 s), and records
  `skipped: empty queue` without a spawn when `triage/queue.json` has
  `"items": []`. An unreadable queue sweeps (#748). A queued milestone no
  sweep started with yet makes the slot due at once, unless the last slot is
  `queued`: that sweep takes every untaken milestone when it starts (#374);
- with `[docs] enabled` ([profile](../profile.md#docs)), no wake: each scan
  runs the docs-pass timer. Once `interval_days` passed since the last slot
  in `docs/pass.json` (at once with no slot recorded, so a crew waking with a
  pass overdue runs it on its first scan), it fetches the default branch into
  the project's checkout, runs `scripts/docs-scan.py` on it (no model), and
  starts `mdstack spawn researcher --docs-pass`. It records the slot as
  `started`, `queued` or `failed: <reason>` (retried after 600 s), and
  `skipped: scan unchanged` without a spawn when every scan, leaving out its
  head, scan date and banner ages, matches the one the last `started` or
  `queued` slot recorded. The timer passes only the project's own checkout,
  so a `[docs] repos` entry naming another repo fails the scan (#1026);
- with `[reflection] enabled` ([profile](../profile.md#reflection)), no
  wake: each scan runs the reflection timer, kept in
  `reflection/ledger.json` and independent of `[triage]` and its milestone
  ledger. The researcher's `protocol-reflection` routine (Monday 00:00
  owner time) makes the last full ISO week pending; a missed week catches
  up once. A project-repo milestone closed since the ledger's baseline,
  read at most once per `poll_interval`, makes `close-<n>` pending at once.
  With no request in flight, every pending window coalesces into one
  `mdstack spawn researcher --reflection <A+B> --run-id <id>`, recorded as
  `started`, `queued` or `failed: <reason>`. A started or queued request is
  never completion: once no run record or `spawn-queue.jsonl` entry holds
  its window, the posted `pass=reflection` report on the reflection log
  completes each window it names, with its URL; with none the request
  failed. A failed request retries after 600 s under the same run ID, and
  an unreadable log never starts a second run. `mdstack reflection` prints
  the ledger (#1521);
- no wake: each scan scales idle instances of roles with a `lifecycle` down
  to their `min` with `mdstack kill` ([role lifecycle](../roles-registry.md#lifecycle), #1231);
- `backstop:` none of these within `--backstop` seconds (default 1800). While
  no run is recorded the interval doubles per idle backstop, capped at 16 ×
  `--backstop`, so waiting costs no model turns. While every recorded run's
  item is held or owner-blocked (an open `asks/<n>.json`, or a ref in
  `poll-state.json`'s `held`, which `mdstack poll` fills from `crew:hold`,
  `crew:escalated` and `crew:needs-md`) and no lead has pending work, the
  backstop waits that cap, at least 4 h from arming (`due (held in flight)`).
  Each scan recomputes it both ways: work becoming held extends the wait, and
  a live, unrelated or unclassified run, or a pending lead message, restores
  the short backstop. Ask deadlines and poll wakes still wake at once, and an
  owner lifting a hold is a `hold-released` poll wake, an owner comment on a
  held or asked item an `owner-answer` one (#394).

It appends each wake to `wake/queue.jsonl` as one JSON line (under
`wake/queue.lock`), saves `wake/watch-state.json` after every scan, and runs
`mdstack route`. If the new records were all mechanical it keeps scanning.
Otherwise it prints one
reason line (`stale: ben-7 dead, silent 1200s, restart`) and exits 0, which
re-invokes the coordinator. A `--persistent` watcher instead nudges and keeps
scanning, restarting its backstop timer as a re-armed watcher would; while
`wake/queue.jsonl` stays non-empty with no new wake it nudges again every
`--renudge` seconds (default 300, a `renudge:` line), so a coordinator turn that
ended on an error is woken without an owner. It re-reads ownership with each
source run and exits 1 once it is `lost`. So that no single hook or harness feature is the
only wake path ([#160](https://github.com/mw-ding/eng-crew/issues/160)
row 4), it also types the fixed line `wake: watcher` into window 0 when the
coordinator is idle: `claude` or `codex` in the foreground and no output for
`--idle` seconds (default 30), the path the Codex recipe uses; like the
`mdstack send` nudge, it waits 0.3 s before `Enter`. When window 0 shows a
blocking prompt it types nothing (#315) and queues a `dialog:` wake for window 0
instead (liveness `ambiguous`, action `escalate`). A fatal API error over an
idle composer is not a prompt, so a coordinator stopped by a gateway error
still gets the wake line (#1346). `--no-nudge`
turns this off, for a Claude Code coordinator whose exit wake works and
which would otherwise take a second, empty turn per wake. On SIGTERM,
SIGINT or SIGHUP it removes `wake/watcher.pid`, saves `wake/watch-state.json` and exits
128 + the signal number, so a killed watcher neither looks armed to the
guard nor replays old status lines. A signal that arrives during a scan is
held until the scan's `--source`, `tmux` and `ps` children have exited, so
none is left running after the watcher; between scans, or on a second
signal, it exits at once. Each scan, before it queues or routes wakes, it
compares the mtimes of `cli/mdstack`, `crew.d/*.py` and `crew-*.py` with
those at start; when an mdstack update changes one, it re-execs itself in
place (same PID and inherited lock, so `wake/watcher.pid` stays valid) without committing that
scan, so the new code finds the same events and resolves any new profile
keys (#702).

### mdstack drain

```sh
cli/mdstack drain [--project <config.toml>]
```

How the coordinator empties the wake queue at the start of each turn,
instead of reading and truncating `wake/queue.jsonl` itself. Under
`wake/queue.lock` it renames the queue to `queue.jsonl.drain-<pid>-<hex>`,
then prints every record as one JSON line, oldest first, and deletes the
renamed file. Every writer (`mdstack poll`, `mdstack watch`) appends under the same
lock, so a record appended during a drain lands either in the renamed file or
in a new `queue.jsonl`, never in a deleted file. A renamed file left by an
interrupted drain is printed first by the next drain. With no queue it prints
nothing. Exit 0.

### mdstack status

```sh
cli/mdstack status [--project <config.toml>]
```

A `coordinator` row for window 0 (liveness only: `alive` with `claude` or
`codex` in the foreground, `dead`, or `ambiguous`), then one row per run
record: window, role, item, worktree head (7 characters),
heartbeat age (minutes since the last status line, else since spawn),
liveness and the last status line. Liveness is the C5 probe
([Q7](#q7-failure)), from tmux and `ps`, never from the agent:

- `missing`: no window at the recorded index under that name, or the pane id,
  pane pid or that pid's start time differs from the run record (`mdstack spawn`
  records all three), so a new window with the same name and harness is
  never taken for the run;
- `dead`: the pane is dead (`#{pane_dead}`);
- `alive`: the expected harness (`claude` or `codex`) is
  `#{pane_current_command}` or a foreground process of the pane's tty;
- `ambiguous`: a dialog on the pane's screen (`tmux capture-pane`, the
  visible screen only), anything else in the foreground, `node` included,
  or tmux cannot answer. A dialog is:
  - a blocking prompt (#289): its heading on a line of its own and its
    footer as the last line on screen. Codex approval:
    `Would you like to …?` over `Press enter to confirm or esc to cancel`;
    Codex folder trust: `Trust this folder?` over `enter continue · esc …`;
    Claude Code permission: `Do you want to …?` (proceed, make this edit,
    create) over `Esc to cancel`. Older Claude Code folder trust uses
    `Do you trust the files in this folder?`, newer versions use
    `Accessing workspace:`, both over `Enter to confirm · Esc to cancel`.
    Codex's `Hooks need review` uses `enter confirm · esc skip` as the final
    line. A prompt echo, diff or file quoting the
    same text has the harness's composer below it, so it never counts;
  - a fatal API error line, after which the harness idles at its prompt
    (#289): Codex `■ {"type":"error","status":4xx|5xx,…}`, Claude Code
    `⎿  API Error: 4xx|5xx {"type":"error",…}`.

### mdstack restart

```sh
cli/mdstack restart <window> [--project <config.toml>]
cli/mdstack restart <coordinator-window> [--project <config.toml>] [--resume <id>]
```

On the coordinator's window (window 0, or its bare name `ash`) it relaunches
the live coordinator in place (#1544): it stops window 0's process group and
respawns the pane with the current `sandbox_env` and `CREW_*` environment
(as `mdstack up` sets them), resuming `--resume <id>` (`fresh`, `ask` or an
id; default `launch.resume`). It refuses while the land lock is held, when
run from window 0 itself (beneath its pane process; the stop would kill it
first: run it from the owner's terminal), for a team reference
(`--project <team>.toml#<repo>`) and for an engine that cannot resume. Use it after
setting `runtime.options.sandbox_env` on a crew that started without it.

Restarts a run once: it refuses unless the run probes `dead` or `missing`,
refuses a run whose last status line is `failed:`, or `done:` for a
reviewer or synthesizer run (a builder stays for fix rounds after `done:`,
so a dead one restarts), and refuses a
run already restarted (escalate: `crew:escalated` and the owner channel,
[protocol §5](../protocol.md#5-rounds-and-escalation)). Otherwise it
checks the run's worktree for unlanded work, the same check `mdstack kill`
uses (uncommitted or untracked paths, commits not on the fetched default
branch, run branch or PR head; a failed check counts as unlanded):

- Clean worktree: `mdstack kill`, then `mdstack spawn` with the recorded
  arguments, giving a fresh window and worktree from a fresh fetch.
- Unlanded work: nothing is deleted and `--discard` is never used. It
  kills the dead window and opens a new one at the recorded index (or the
  next free one in the band) in the same worktree, with the same brief,
  claim, engine, model and effort. It verifies the harness start like
  `mdstack spawn`, records the new pane identity and lists the kept items. If
  the harness does not start, it closes that window and keeps the worktree,
  claim and run record.

Either way the run record gets `restarts: 1`.

A builder whose last line is `done: #<issue> #<pr> <sha>` restarts as
`--pass fix --pr <pr>`, never as a second build pass: the fresh spawn
checks out the PR head, and an in-place relaunch records the fix pass and
appends it to the brief.

When the tmux server or `ash` died, `mdstack up` rebuilds the session and `ash`
from disk (render, guard, the existing wake queue) and lists the recorded
runs, which now probe `missing`. It never respawns role windows; the
coordinator decides per run with `mdstack status` and `mdstack restart`.

### mdstack doctor

```sh
cli/mdstack doctor [--project <config.toml>] [--org-profile <path>] [--fix]
```

Checks whether this host can run the crew, a subset of the
[bootstrap preflight](../bootstrap.md#q5-preflight-checks) (#190), and
prints one `ok`, `warn`, `fail` or `human` line per check with its fix
hint. It is read-only; `--fix` creates the missing state dir layout and
nothing else. It never changes auth, the repo or a harness config: those
steps (a `gh` login, Codex hook trust, Claude Code folder trust) are listed
at the end for a person. Exit 1 on any `fail`. It also runs for a non-tmux
profile, without the tmux checks. `mdstack doctor --help` lists the checks.
The `checkout` row fails when the checkout's forge `origin` URL names
another repo than `[repo]` and warns when it has none. The `install` and
`mdstack link` rows warn before bootstrap (which runs doctor before it
writes `install.json` and the link); once `install.json` exists, a
missing `paths.mdstack` fails (#1323).

The `sandbox` row (tmux only, #1544) fails when a launcher sandboxes
sessions and no writable root covers the checkout's git directory (the
common directory for a linked worktree, whose `.git` is a file), unless
`runtime.options.sandbox_env` or `CREW_SANDBOX_ENV` is set. It detects that
two ways: a create-and-remove probe in that directory is denied to doctor's own
process (it runs inside such a session), or a used engine's harness adapter
declares `sandbox_roots(values)`, the writable roots its launcher grants a
session by default, none of which covers `.git`. The fix: set
`runtime.options.sandbox_env = "<NAME>=<checkout>/.git"` with the
launcher's writable-roots variable, which the org pack names. `mdstack up`
and `mdstack up <role>` refuse on the same check before starting any window.

## Role leads (proposed, #521)

**Review prerequisite (historical).** This design was the first slice of #521
and was reviewed before implementation. The builder and reviewer leads have
since shipped in #534 and #537 ([Builder lead](#builder-lead),
[Reviewer lead](#reviewer-lead)), so this section no longer describes a
future binding. The synthesizer joined this contract in #1569
([Synthesizer lead](#synthesizer-lead)).

Delivery is three separately reviewed PRs: [1/3] this design, [2/3] the
builder lead, and [3/3] the reviewer lead. The first two reference #521;
only the last closes it after AC2–AC4 are satisfied. Review of the design
does not claim the implementation is complete.

### Authority and continuity

One long-lived builder lead and one long-lived reviewer lead manage their
own pools. They keep references and scheduling context, re-read GitHub on
every wake, and use the existing role identities and profile engine routing.
The reviewer lead schedules passes; it never writes a review or validation
verdict. Review, validation and recheck workers remain fresh per pass, with
the existing engine diversity rules. A builder worker stays with its issue
through fix rounds, including while waiting after its build reports `done:`.

| Actor | May decide | Must hand off |
|---|---|---|
| Coordinator | Triage, work routing, owner decisions and incident escalation | Builder and reviewer lifecycle to the owning lead |
| Builder lead | Spawn, dequeue, reclaim and restart builder workers within `builders` | Spec ambiguity, exhausted retries, unsafe cleanup and owner asks to coordinator |
| Reviewer lead | Spawn review, validate and recheck; deduplicate, reclaim and restart reviewer workers within `reviewers` | Disputed evidence, exhausted retries and owner asks to coordinator |
| Token-free supervisor | Ensure one session per lead; probe recorded identity; restart a dead or missing lead once | Ambiguous lead or second failure to coordinator |

Leads cannot change gates, round caps, CI-fix caps, ownership, holds, flavors
or merge permission. Decisions use the protocol and resolved profile, with
no project-specific steering. Supervisor recovery grants no permission to
manage workers: the restarted lead reconciles its own pool.

### Recorded handoffs and single consumers

The coordinator records reference-only work for the owning lead. A handoff
names its id, kind, issue or PR, full head SHA where applicable, round and
finding/CI references. Each lead has its own durable queue under
`leads/<role>/`, separate from `runs/`, plus inbox and append-only status
files using C3 delivery and C4 status. The sender retains the handoff until
its `ack:`; a queue item remains pending until a worker's matching output
exists or live state makes the request obsolete. Acknowledgment proves
receipt, not completion.

The watcher and router deliver each pool event to exactly one lead. New
heads, passed review sections, recheck escalation, terminal pass status and
pool liveness events go to the reviewer lead; build/fix handoffs and builder
liveness or terminal issue events go to the builder lead. The coordinator
retains owner asks, triage and incidents. Existing synthesizer routes and
serial-land protection remain in place for this slice.

Queue append, claim and completion are serialized per role. Records move to
an in-flight batch under that lock before dispatch; an interrupted batch is
replayed before newer work. Replayed handoffs are deduplicated against live
workers, pending requests, claims and output markers before any spawn.
Neither coordinator recovery nor `mdstack kill` may dequeue another pool as a
side effect: slot release wakes the owning lead. Manual lifecycle commands
remain available for owner-directed operations; the coordinator brief uses
only recorded lead handoffs for builder and reviewer lifecycle.

### Scaling policy inputs

Built as the crew scheduler: both leads admit through `mdstack schedule decide`.
Its [inputs](../scheduling.md#inputs) and [policy](../scheduling.md#policy)
(ranking, target, floors, presence) are the admission rules. Lead sessions
use separate reserved windows outside worker bands; they do not consume a
worker slot or enlarge a cap. A lead still retains held work, retires closed
or superseded requests after a live-state check, never dispatches a stale
fix, and follows profile engine routing and fallback.

Load is an admission input, not evidence that a worker died. Step summaries
provide completed-step evidence; an in-flight suite needs a recorded step
start, worker identity and child-process probe. A recorded start alone never
keeps a worker alive indefinitely. No model turns poll queue depth or load:
the plain-script watcher schedules the backstop and wakes the lead when
deferred work becomes eligible. Scaling down means reclaiming terminal
workers, never interrupting an active build or test to meet a load target.

### Deduplication and recovery

Builder dispatch is keyed by issue, with the adopted open PR and head on
fix requests. It checks both recorded and actual windows and queued work,
adopts an existing closing PR, and resumes a finished build as a fix pass.
It never opens a second PR or treats a waiting builder as a free slot.

Reviewer dispatch is keyed by PR/full head/pass/round, with a rereview steer's
id distinguishing a fresh requested pass at the same head. Live runs,
queued requests, retained section files and posted markers all participate.
The steer id goes to `mdstack spawn --rereview-id` (reviewer only, with
`--pr` and `--head`), which writes it into the run record before the harness
starts; a queued request, dequeue and a clean restart carry it, and the
restart pins the run's head, so a moved head refuses as stale instead of
inheriting the old steer (#1477).
Review starts with CI pending; validation follows a passing review subject
to the existing held-CI policy; recheck follows the existing merge-up rules.
A replay of a passing review still starts missing validation even if the
review window was already reclaimed. Older-head sections never suppress
current-head work. Retain sections until their consumers finish; cleanup
must not lose evidence referenced by a pending builder handoff.

Worker and lead probes use C5 identity (pane id, pid and process start time).
Known child build/test processes and recent progress keep a long suite from
being reclaimed solely for status silence. Failed probes, stale progress or
an expired suite deadline are `ambiguous`: re-probe and escalate under Q7,
never launch a duplicate. Only `dead` or `missing` permits one restart;
existing explicit dialog exceptions and all retry caps stay unchanged.
Unlanded work and failed teardown checks keep the worktree under C6.

On lead death, the supervisor preserves queues, in-flight batches, inboxes,
claims, worker records and referenced evidence. It restarts only the lead,
with a new recorded identity; workers continue. Before dispatch the lead
reconciles these records with live GitHub state and actual worker identities,
reattaches live workers, recovers missing outputs, and replays unfinished
handoffs once. A second failure or an ambiguous lead blocks that pool and
wakes the coordinator. Ownership loss stops dispatch and writes under C9;
recovery never resets rounds or clears a hold.

### Implementation and fixture review

After design review, implement the builder lead and its coordinator handoff
first, then the reviewer lead and router handoff. Remove automatic cross-pool
dequeue before enabling either lead so two authorities cannot dispatch the
same work. Supervisor bootstrap and lead queues must be available when the
new coordinator brief is deployed; there is no silent fallback to coordinator
spawns when a lead is absent.

Fixtures for each lead must cover cap exhaustion, released capacity, load
deferral/resumption, duplicate handoffs, held/stale work, dead/missing restart,
ambiguous non-restart, retry exhaustion and interrupted dispatch replay.
Builder fixtures also cover waiting continuity and adoption of an existing
PR. Reviewer fixtures cover fresh passes, same-head rereview, missing
validation after review cleanup, and a long local suite without duplicate
spawn. Supervisor fixtures cover lead death with live workers and intact
queued work. Run the full local suite and render/parity checks before each
implementation push. Runtime evidence must show recorded handoff → lead
dispatch → worker completion → slot reclaim and lead restart with queued
work preserved. This design PR carries no implementation evidence.

## No live copy to mirror (#877)

Design for [#877](https://github.com/mw-ding/eng-crew/issues/877): a tmux
install whose only live copy is the render `mdstack up` deploys can say so in
its profile. The no-mirror-hold gate then resolves to a recorded,
deterministic `n/a`, and no role asks for a mirror or a deferral. Today a
pack that has nothing to mirror writes "mirror: n/a" into every merge
record by hand, and only prose holds that rule.

Build issues B1–B3 (#940–#942, [below](#build-issues-877)) made it
normative. B2 and B3 change what satisfies the
[No mirror hold](../protocol.md#gate-registry) gate, so they land under the
[gate contract](../protocol.md#gate-contract) with the owner's per-change
merge-ok.

Every addition is optional. An unchanged profile resolves to `live-copy`,
today's behaviour: Grok Bot and default tmux briefs, `mdstack train check`
output and merge records stay byte-identical. No key, marker, state tag,
label, notify kind, command or exit code is removed or renamed.

**Today.** The gate is path-derived: a change touching `docs/protocol.md`
or `templates/` needs a coordinator mirror comment with a clean drift check
([Grok Bot](grok-bot.md#mirror-hold-gate)), or on tmux the recorded owner
deferral named by `mirror_deferral` ([mdstack train](#mdstack-train)).
`mdstack train check` applies the path rule only to the mdstack repo (#911)
and blocks on a `crew:needs-mirror` label wherever it sees one. Every train
merge record carries `Mirror deferral used: <value>`. No tmux brief applies
`crew:needs-mirror`; only the Grok Bot reviewer does.

### Setting

```toml
[runtime.options]
mirror = "none"   # live-copy (default) | none
```

| Value | Meaning |
|---|---|
| `live-copy` | Default. A live copy exists outside the render (for mdstack, the box skill), so the gate applies as today |
| `none` | The owner declares that this install has no live copy outside the render `mdstack up` deploys. There is nothing to mirror and no drift to check |

`mirror` is a tmux option. Setting `none` is the owner's explicit opt-in,
recorded like any profile change. It is a fact about the install, not a
deferral or a grant: it supplies no approval and no merge permission, and
every other §7 gate still applies at head.

### Validation (B1)

`crew-config.py validate` and `resolve` check the setting. `resolve` prints
`runtime.options.mirror`, defaulting to `live-copy`.

| Profile | Result |
|---|---|
| `mirror` unset, `"live-copy"` or `"none"` on tmux | Accepted |
| Any other value | Refused by the existing choice check: `runtime.options.mirror: unknown value 'x' (expected one of: live-copy, none)` |
| `mirror` under `runtime.name = "grok-bot"` | Refused: `runtime.options.mirror: unknown key`. Grok Bot keeps its box-skill mirror |
| `mirror = "none"` with `mirror_deferral` other than `"none"` | Refused: `runtime.options.mirror: "none" conflicts with mirror_deferral "<value>"; an install with no live copy has nothing to defer` |

An existing deferral is never silently converted: the owner clears
`mirror_deferral` in the same profile change that sets `none`.

### Gate resolution (B2)

`mdstack train check` decides the mirror gate in this order:

1. `mirror = "none"`: pass for every PR, before path applicability and
   whether or not `crew:needs-mirror` is present.
2. Otherwise, today's rule unchanged: the label blocks, then #911's
   repo and path applicability, then a mirror comment or deferral.

The result keeps the existing diagnostic format:

```text
gate pr=<pr> sha=<head-sha> name=mirror status=pass reason="n/a: profile mirror = none"
```

The pass is diagnostic, like every `train check` line. It is not an approval
or a grant and never replaces the synthesizer's §7 check.

Under `none`, a `crew:needs-mirror` label already on a PR is inert. The
check, gate-status and the synthesizer's land-time §7 check all ignore it,
so they agree. Any role may remove it, but removal is cleanup, not a gate
step. `crew:hold`, `crew:escalated`, a coordinator hold-until and every
other hold still stop the PR.

`train land` writes the record line from the setting:

| `mirror` | Merge record line |
|---|---|
| `live-copy` | `- Mirror deferral used: <value>.`, as today |
| `none` | `- Mirror: n/a (profile).` |

`--mirror-deferred` already refuses with no profile deferral, so under
`none` it refuses as today. The record line is prose, not a marker field;
no parser reads it.

### Briefs and protocol activation (B3)

- **Synthesizer:** under `none`, the rendered brief leaves out the mirror
  deferral paragraph and says instead: the gate is `n/a` by profile; record
  `Mirror: n/a (profile)` on direct lands and list no mirror item in
  gate-status; never wait on or ask for a mirror or deferral, and ignore
  `crew:needs-mirror`. Under `live-copy`, the rendered bytes are unchanged.
  The renderer has no conditional text today, so B3 adds one derived
  placeholder filled from `runtime.options.mirror`: today's paragraph
  verbatim for `live-copy`, the line above for `none`.
- **Coordinator:** under `none`, it opens no `mirror` owner ask and queues
  no `mirror` notify event. The `mirror` kind stays for `live-copy`
  installs.
- **Reviewer:** the tmux brief applies no mirror label today, so it needs
  no text. B3 adds a render test that the `none` reviewer and coordinator
  briefs carry no mirror instruction.
- **Protocol:** the [gate registry](../protocol.md#gate-registry) row and
  the §7 No mirror hold bullet gain one clause: on tmux, profile
  `mirror = "none"` resolves the gate to `n/a`, named in the merge record.
  The [runtime options](../configuration/runtime-options.md#tmux-options)
  table gains the `mirror` row. Grok Bot runtime wording is unchanged.

B3's protocol edit changes the bytes of every generated skill that includes
`docs/protocol.md`. That is the expected included-doc change and is
reviewed as such; the Grok Bot procedural branches stay byte-identical.

### Build issues (#877)

| Slice | Issue | Paths | Gate | Tests |
|---|---|---|---|---|
| B1 | #940 | `scripts/crew-config.py` option table and conflict check | none | `test-crew-config.py`: both values, unset default, bad value, Grok Bot, conflicting deferral |
| B2 | #941 | `scripts/crew.d/train.py` check and merge record | [G] | `test-crew-train.py`: check line and record text for both values; label present under each; #911 product-repo case unchanged |
| B3 | #942 | `scripts/crew-render.py`, `templates/runtimes/tmux/synthesizer.md` (and coordinator only if needed), `docs/protocol.md`, `docs/configuration/runtime-options.md` | [G/P] | `test-crew-render.py`, `test-render-parity.py`, `test-tmux-briefs.py`: `live-copy` goldens unchanged, a `none` fixture without deferral wording |

Each slice depends on the one before. #877's ACs map to them: validation
to B1; the check line and record text to B2; the registry row, tmux
binding and briefs to B3; tests to each.

## Design credit

The watcher, turn-end guard, delivery-ack and liveness-probe patterns, and
the `bypass` default for role-window permissions, are adapted from
[firstmate](https://github.com/kunchenguid/firstmate)
(MIT license). mdstack takes the contracts only: no code or text
is copied. Delivery proof differs on purpose: an `ack:` status line instead
of checking the composer; `mdstack send` reads the composer only to clear its
own stale nudges and confirm its `Enter` submitted (#308). Its
owner-communication etiquette, persona removed, became the coordinator's
[owner communication](../roles.md#owner-communication-coordinator) rules
(#186). Not adopted: its persona and forms of address, relay, remote homes,
the away-mode daemon, non-tmux backends and its dispatch and task-lifecycle
modes.

## Ownership fallback

Configure `repo.control_item` and `runtime.instance` ([profile](../profile.md)).
`mdstack ownership --project FILE --action start|write|land` reads the shared
[record](../protocol.md#ownership-record). Non-owners read/report only.
`spawn`, `restart`, `send`, `train`, discard and land-lock acquisition refuse; the
Stop guard permits ending the turn while read-only, and keeps its normal block
while draining so the coordinator sees in-flight runs end. Poll emits one
coordinator `ownership:` wake per mode change, with no work events while
read-only or draining. Role briefs repeat the check before pushes, posts, tags
and lands. Draining permits only in-flight writes.

The owner's [handoff chat commands](../protocol.md#owner-handoff-commands) map
to `mdstack handoff`:

```sh
cli/mdstack handoff to <runtime-id> [--mode drain|stop] [--deadline <minutes>] --signature <signature> --project FILE
cli/mdstack handoff abort --signature <signature> --project FILE
cli/mdstack handoff takeover <runtime-id> --signature <signature> --project FILE
```

Each re-reads the record, refuses an illegal transition (exit 1, nothing
posted) and posts one signed `draining`, `aborted` or `takeover` state on the
control item with the default-branch head and `cmd-id=chat`; `--dry-run`
prints it instead. In drain mode `to` writes `asks/handoff.json` with the
deadline, so the watcher wakes the coordinator then ([C8](#runtime-contract))
and the Stop guard holds the turn; the coordinator deletes it when the drain
ends, and `abort` deletes it. Draining, the coordinator dispatches nothing,
lets each run finish its round, then releases claims. In stop mode, or at the
deadline, it runs `mdstack kill` on each run except a synthesizer holding the land
lock; `mdstack kill` keeps unlanded worktrees. The drain ends with
`mdstack handoff manifest --post` (`offered`, #211).

Resume and prompt stop (#212, [handoff](../handoff.md#resume-and-reconcile)):

```sh
cli/mdstack handoff reconcile --project FILE
cli/mdstack handoff ack [--rules-confirmed] --signature <signature> --project FILE
cli/mdstack handoff lift [--owner-confirmed] [--keep <n>]... --project FILE
cli/mdstack handoff stopped --signature <signature> --project FILE
```

The incoming coordinator runs `mdstack up`, `reconcile` (read-only), then
`ack`, which refuses while a `rule` difference has no owner answer and posts
`acked` with the plan once per handoff id. Before any dispatch it holds each
`hold` set with a note, then runs `lift` once the outgoing side posted
`stopped` (or the owner confirms, or the manifest's release reads the
record), keeping those holds with `--keep`; it re-creates `asks/<n>.json`
for each owner ask still open. On the outgoing side, after the ack poll's
mode becomes `lost`: it queues one `ownership:` wake, the watcher exits and
`mdstack watch` refuses to re-arm. The coordinator runs `mdstack handoff stopped`.
Because `mdstack down` kills window 0, `stopped` re-runs itself detached from
the session (log `handoff-stop.log`; `--foreground` from a shell outside
it). It disarms any watcher, runs `mdstack down` keeping every worktree
(retrying while the land lock is held), and posts `stopped` with the kept
worktree names once no watcher and no session remain.

## Slack progress notifications

With the [Slack owner-channel profile](../profile.md#backendsconcern), the
coordinator queues notifications only during recorded
[away mode](../protocol.md#owner-away-mode). GitHub remains the tool of record:
post asks there with deadlines and defaults first; Slack may link them but
never supplies answers, approvals, merge-ok or a replacement return brief.

After each event's GitHub record exists, write JSON to a local scratch file
and run `mdstack notify --project FILE --event-file EVENT_FILE`. Use a stable
`id` from that record (same ID on replay), `kind`, and its full HTTPS `url`.
With this binding, mechanical merge cleanup leaves `pr-merged` for the
coordinator to queue its land message after cleanup, unless the
[synthesizer lead](#synthesizer-lead) is installed: then route queues it.
Every required field below is a nonempty string; use `None` for empty digest
sections and `direct` for a land without a train. Copy URLs from live records.

| Kind | Additional fields | Record / message |
|---|---|---|
| `land` | `title`, `train`, `milestone` | One per landed PR, its train number and milestone advanced |
| `milestone` | `title` | One per completed milestone |
| `release-cut`, `release-published` | `title` | One per release transition |
| `ask`, `sensitive`, `mirror` | `title`, `deadline`, `default` | One per open owner blocker; deadline includes timezone; merge permission has no automatic grant default |
| `main-red` | `title` | Red default-branch run after land; link the run |
| `stop` | `title` | CI provider / billing outage or runtime down; link the incident |
| `digest` | `landed`, `in_flight`, `blocked` | Fresh progress with links to the items in each section |

```json
{"id":"record-id","kind":"land","url":"https://github.com/<owner>/<repo>/pull/123","title":"Result","train":"4","milestone":"M16"}
```

Quiet otherwise: do not queue individual review passes. `mdstack watch` wakes
the coordinator with `notify-digest` after the profile interval without a
new progress event, including when no PR has landed yet. Build a fresh digest
from live records; use the wake's entry and slot as its stable ID. Reconcile
away state first and skip a digest if newer urgent progress made it obsolete.

The helper re-reads signed coordinator away/return records on the tracking
issue before each delivery; an unreadable record defers delivery. Reaching
`until` alone never ends away mode. State under `notifications/` holds
messages, dedupe IDs and outcomes, never the webhook. Dedupe survives restart
and is scoped to an away entry, event kind and record ID. The watcher polls
away changes at most once per minute when no message is due; every actual
post uses a fresh read. Only one due message is attempted per scan with a
bounded network timeout. Confirmed rejection or connection refusal logs a
sanitized failure and retries after 30, 60, 120 seconds, up to hourly.

Incoming webhooks provide no idempotency guarantee after an ambiguous
transport timeout. Such attempts become `uncertain` and require reconciliation
instead of an automatic resend that could duplicate the event. No failure
blocks builds, reviews or lands; the helper returns success for notification
failures. A running crew requires the webhook in its inherited environment.

On return, record `away-return` first, run `mdstack notify --project FILE --flush`
to cancel pending messages, and include `mdstack notify --project FILE --status`
output in the standalone return brief, including recovered failures and
uncertain deliveries. Deliver the brief by the existing recorded owner channel
and tracking issue; Slack stops with away mode. Keep the failure records for
audit. Network delivery of an already-started request may finish during return.
