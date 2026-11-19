# Session runtime binding

> - **Status:** partly built
> - **Applies to:** hand-dispatched or hosted sessions; profiles with `runtime.name = "session"`
> - **Current rules:** [protocol](../protocol.md), [runtime contract](README.md#contract)
> - **Built:** [Run parameters for hosted dispatch](#run-parameters-for-hosted-dispatch) via `mdstack brief` (#647); the [selector, options and briefs](#selector-options-and-briefs) (#914); [starting the coordinator](#starting-the-coordinator) via `mdstack up` (#1548); [upgrading](#upgrading) via `mdstack upgrade` (#1541); the [triage sweep routine](#triage-sweep-routine) (#1404), opt-in since #1724; stack land by top change with revision ids and per-change readback (#1722); the one-time bootstrap for an install without `install.json` in [upgrading](#upgrading) (#1727)
> - **Design only:** everything in [Implementation follow-ups](#implementation-follow-ups)
> - **Last checked:** 2026-11-18 at `f7e4938`

`runtime.name = "session"` runs one interactive coordinator session,
with short-lived workers as native subagents or external harness CLI runs
(roadmap 17.13, [#340](https://github.com/mw-ding/mdstack/issues/340), after
[#179](https://github.com/mw-ding/mdstack/issues/179)). This describes the
single-session mode used to build mdstack on 2026-10-29: a Claude Code
coordinator, subagent builders and an independent Codex reviewer.

Support level: **attended only** ([support table](README.md#support)). The
validator and renderer accept the selector, `mdstack brief` fills each
worker's run block, `mdstack up` starts the coordinator and
`mdstack upgrade` upgrades the install. Dispatch, liveness, receipts,
worktrees, locks and ownership guards remain manual procedures run by the
coordinator with a person attended, and bootstrap's
[harness pointers](../bootstrap.md#q4-install-targets) do not implement this
runtime. Unattended progress needs the tmux runtime. It adds no rule, gate,
cap, marker field or label: the [protocol](../protocol.md) and
[runtime contract](README.md#contract) apply.

## Selector, options and briefs

A profile selects the binding with `runtime.name = "session"`
([options](../configuration/runtime-options.md#session-options)):
`max_active_milestones`, `session_backend` (`native` subagents, `cli`
runs or `hosted` control-plane sessions), the `builders` and `reviewers` pool limits, and the synthesizer's
land-policy options. `crew-render` writes four briefs from
`templates/runtimes/session/`: the coordinator, and the builder, reviewer
and synthesizer worker briefs, plus the researcher sweep worker brief when
`researchers` is positive. Each worker brief carries the tmux role's
contract for one pass per run and ends where the coordinator appends the
`mdstack brief` run block (below); workers set their own `CREW_*` paths, since
no runtime sets them. The researcher brief runs only the
[triage sweep](#triage-sweep-routine), carrying the tmux brief's Triage
sweep policy. The sweep is opt-in: `researchers` defaults to 0, which writes
no researcher brief, so a sweep sets a positive cap (#1404, #1724).

Session lands go alone, one per run (#1041), unless the change backend
declares a [stack land](../interfaces.md#stack-land) (below). A sync backend lands under the
brief's `mkdir` repo lock. A change backend that declares `land.mode =
"async"` with its `[land]` table, change placeholder and `[land.status]` map
is accepted on a session profile too (#1351): the synthesizer brief's step 3
then runs `mdstack land request`, which polls the declared status map every
`land_poll_interval` seconds up to `land_timeout` and exits 1 on `failed`, a
stale head, a timeout or an unknown status, and each run starts with
`mdstack land resume`. `mdstack land` resolves tmux and session profiles;
`mdstack land-lock` stays tmux-only, so a non-serializing backend keeps the
`mkdir` lock until the terminal status and the merge post. Merge trains are
tmux-only, since every `mdstack train` action refuses a session profile:
`train_min`, `train_window` and `train_local_checks` have no effect.

A change backend that declares `land.stack = true`, with `change.land-stack`
and `change.stack-status` bound, adds a stack land (#1605): when two or more
ready PRs form one linear `Depends on` stack, the synthesizer brief checks
every [§7 gate](../protocol.md#7-merge-gate-synthesizer) for every member at
that member's own head and refuses the whole stack, requesting nothing, if
any member fails. Otherwise it runs
`mdstack land stack --stack <n>:<head-sha>,...` (base first) once. That
records the intent, re-reads every member's head, sends one atomic request
only when every member's status reads `none`, polls as above, and on a
complete per-member readback prints one merge record and marker per member,
each with its landed revision. A missing, reordered or malformed member
line, or members in different states, is unknown and records nothing.
`mdstack land resume` reads stack intents back without requesting, and
`mdstack land stack-done` clears a landed one after the merge posts and the
default-branch CI check. With `land.stack_tests_against_tip = true` the
backend's combined-stack test on the current tip meets tested with the
default branch, but only when the readback names the check, which each
member's record then cites. Without `land.stack` the brief renders no stack
recipe and lands stay one per run; tmux renders and trains are unchanged.
A backend whose request names one representative change and every
member's revision id binds `<stack-top>` and `<stack-revisions>`, with
`change.read-revision-id`; with `land.stack_status = "per-change"` the
readback is each member's mapped `change.land-status` (#1722,
[interfaces](../interfaces.md#stack-land)).

The stack land lab (#1614) runs that recipe end to end with a real
synthesizer session. Run
`python3 dev/tests/scripts/fixtures/stack-land/run.py [--scenario NAME] [--model M]`
from a checkout, in a shell where `claude` starts. For each scenario it
renders the production session briefs against a fixture pack that binds
`change.land-stack` and `change.stack-status` to a stub. It appends the
`mdstack brief` run block for a two-member stack and runs one `claude -p`
synthesizer session in the checkout. A stub `gh` comes first on `PATH`, and
no forge token or `CREW_*` variable is passed. The stub serves each member's
head, markers, labels and CI, and it logs every call. The lab then counts
the stub's `land-stack` requests, per-PR merges and merge posts. Scenarios:
`held`, `red-ci` and `unapproved` (one member fails, so zero requests),
`pass` (exactly one request), `malformed` (an incomplete readback, so no
merge post) and `lost-ack` (one request, read back, never resent). The
`rev-pass`, `rev-held`, `rev-red-ci` and `rev-lost-ack` scenarios (#1722)
bind a three-member stack by `<stack-top>` and `<stack-revisions>` with
per-change readback and expect the same request counts. Exit 0
means every scenario met its expectation and 1 means one did not. Exit 2
means unverified: the session never acknowledged the run.
`dev/tests/scripts/test-stack-land-lab.py` checks the lab's plumbing in CI
with a scripted engine. It never stands in for the live run.

A session profile may carry a `[hosts]` inventory, without `[placement]`.
`mdstack host check` and `mdstack host prepare` then run as for tmux: the
primary gets `mdstack doctor`'s session rows, the engine login rows and the
project mirror row, with load 0 since session workers hold no tmux windows;
any other host gets the same remote rows as under tmux (#1122). Other host
and runtime commands (`hosts`, `layout`) stay tmux-only.

## Upgrading

`mdstack upgrade` runs on a session profile
(#1541): `--dry-run` previews the re-render, `--yes` applies it to
`paths.live_dir` and `--version` or `--latest` fetch and verify a bundle,
as for tmux ([bootstrap Q8](../bootstrap.md#q8-idempotency-upgrade-and-uninstall)).
With no role windows, it skips the in-flight wait and window reload and
restarts nothing. Finish or pause dispatch first, then exit the coordinator
and run `mdstack up` so it loads the new briefs.

A session crew set up by `mdstack install` and a manual render has no
`install.json`, and upgrade refuses it with `adoption covers a tmux install
only`: adoption of a running install without a record (#1616) verifies tmux
installs only. Bootstrap once instead (#1727). Bootstrap overwrites only
the files it owns, and with no record it owns none, so it refuses the
existing render and state files as `target edited or unowned`. To fix that:

1. Finish or pause dispatch and exit the coordinator.
2. Move these into a backup directory, keeping them: the
   `paths.live_dir` render, and any `mdstack` link, `VERSION` and
   `config.toml` in the state directory (`<paths.state_dir>/<owner>__<repo>`).
3. From the release bundle you chose, run its own `cli/mdstack`, not the
   moved link:
   `MDSTACK_CONFIG=<absolute config.toml> <bundle>/cli/mdstack bootstrap --dry-run`
   (`--version` fetches a release). Review the output, then repeat with
   `--yes`
   ([bootstrap Q8](../bootstrap.md#q8-idempotency-upgrade-and-uninstall)).
   That re-renders `paths.live_dir`, re-creates the link and writes
   `install.json`.
4. Diff the new render against the backup. Move any hand edit you want
   to keep into the profile, since upgrade never overwrites a hand-edited
   render file, then delete the backup and run `mdstack up`.

Later upgrades and coordinator restarts follow the steps above.

With `repo.control_item` set, a GitHub issue or a tracker-native item, the
coordinator brief carries the ownership guard and the handoff steps. Without
one, `mdstack ownership` always permits, so the render drops that inert text:
one paragraph says there is no ownership record or handoff, and the worker
briefs omit their ownership line.

With `session_backend = "hosted"` (#1052), each worker is a hosted session
that the coordinator creates through a control plane, addresses by the
session id it returns and probes by a control-plane state read; it is never
a local subagent or process. The coordinator and worker briefs then render
that dispatch and liveness text in place of the subagent, task-handle and
PID text, through `<session-backend:hosted>` and `<session-backend:local>`
template blocks. `native` and `cli` profiles render as before.

## Starting the coordinator

`mdstack up` on a session profile starts the
interactive coordinator only (#1548): window 0 of the tmux session
`runtime.options.session` (default `crew-<owner>-<repo>`) runs the
coordinator's [harness adapter](harness-adapters.md) with `CREW_ROLE=coordinator`,
`CREW_PROJECT`, `CREW_STATE`, `CREW_BIN`, `CREW_IDENTITY` and `CREW_BRIEF`
set from the resolved profile, and the first prompt points at the rendered
`render/runtime/coordinator.md`, with any `runtime.options.notes.coordinator`
files appended. It runs the same preflight as tmux (coordinator notes, host
checks, `launch.resume`, the checkout row) and opens no role windows, pool
leads or lifecycle instances, and installs no tmux Stop-hook guard: workers
stay dispatched per pass. If the session already runs, `mdstack up` prints
its attach line. `launch.coordinator = "none"` is preflight only, and
`launch.resume` or `mdstack up --resume <id>` resumes an existing Claude Code
or Codex coordinator conversation
([launch options](../configuration/runtime-options.md#launch-topology)).

## Triage sweep routine

With `[triage] enabled = true` and a positive `runtime.options.researchers`
(an unset or zero cap is refused), a session crew runs the
[triage](../triage.md) scan → queue → sweep → record → daily log loop as
tmux does, in shadow mode first; the owner loop, noise cap, cooldowns and
calibration are unchanged (#1404). The scan is
`mdstack poll --triage-only --project <config.toml>`: one zero-model scan
into `<state-dir>/<owner>__<repo>/triage/queue.json`, then exit. A GitHub
tracker reads `[triage] repos` through `gh`; a non-GitHub tracker backend
reads its `tracker.list-items` binding once per `[triage] trackers` id
(the `<tracker>` placeholder; list it in the map's `placeholders.kept`),
comments included for owner replies, and lists no closed milestones.

No watcher runs on session, so a hosted scheduler maps
`roles/eng/researcher/routines/triage-sweep.toml` to its own routine
trigger ([routines](../routines.md#other-environments)):

- **Schedule:** every `triage.interval_hours` hours (the routine's
  `every_key`; default 6), with its 10-minute retry and one catch-up run
  when a slot was missed.
- **Skip:** the trigger first runs the scan. When `triage/queue.json` lists
  no `items` and no `milestones`, the run ends there and starts no model
  session.
- **Run prompt:** names the routine file
  `roles/eng/researcher/routines/triage-sweep.toml` and its skill
  `triage-sweep`, and dispatches the rendered
  `render/runtime/researcher.md` with its run block:

```sh
{ cat "<state-dir>/<owner>__<repo>/render/runtime/researcher.md"
  cli/mdstack brief --window riley-sweep --item "triage sweep" \
    --pass research --base "<default-branch-head-sha>" \
    --engine "<engine> <model> <effort>"
} > "<dispatch-brief>"
```

A P0 candidate also appends a `triage-p0` record to `wake/queue.jsonl`; with
no watcher, the coordinator reads it on its next §6 sweep. A crew whose
host sleeps still misses slots; the catch-up run covers the gap.

## Decisions

| Concern | Session decision |
|---|---|
| Lifetime | One coordinator for the owner's interactive session; one builder run per item, fresh review and validation runs per pass. GitHub and disk retain state when the session closes. |
| Engines | Claude Code coordinator with native subagents or external CLI workers; Codex coordinator with external CLI workers is a manual alternative. Each run follows tier routing and records its actual engine, model and effort. |
| Independence | The coordinator schedules and combines outputs; separate workers review and validate. Validation never receives the review. Reviewer identity and engine diversity remain subject to the existing rules and recorded waivers. |
| Dispatch | Re-read ownership and live item/head, check markers and claims, then pass a brief pointer and refs. A native subagent must enter its assigned unique worktree before changing files. |
| Confinement | Session workers are unconfined (#1252, [tmux Confinement](tmux.md#confinement)): a native subagent runs in the coordinator's process and sandbox, and an external CLI worker gets no OS write sandbox mdstack sets. #1252's guarantee that a builder cannot remove another run's working copy is not claimed on `session`. |
| Concurrency | Profile caps remain ceilings, with the owner-present limits `present_builders` and `present_reviewers` as on tmux ([runtime options](../configuration/runtime-options.md#session-options)); dispatch only as many independent workers as the harness can track. No worker shares the coordinator checkout. |
| Landing | The synthesizer remains the landing role and selects the land rule; it lands each ready PR alone, with no merge train; an async backend lands through `mdstack land` (above). The coordinator dispatches it; one repo lock covers the final gate through the merge post. |
| Persistence | Claims, run identities, inbox refs, status, summaries and unlanded worktrees live on disk; evidence and markers live on GitHub. Transcript memory is not recovery state. |
| Worktrees | One root for every worker and probe worktree: `paths.worktree_root`, as on tmux (#316). Teardown keeps the manual C6 checks; [mdstack gc](tmux.md#mdstack-gc) is tmux-only, since session runs keep no run records it could read. Git stays the only worktree provider; treehouse was considered and deferred ([provider decision](tmux.md#mdstack-gc)). |

## Harness adapters and session backends

| Interface | Proposed use | Limits |
|---|---|---|
| [Claude Code adapter](harness-adapters.md#claude-code-claude-code) | Interactive coordinator; native subagents via bootstrap's project-local pointers; external `claude` workers via the adapter's CLI recipe | Native subagents use harness task handles, not tmux foreground/idle probes. The existing Stop hook invokes a tmux watcher guard; it is not a session wake implementation. |
| [Codex adapter](harness-adapters.md#codex-codex) | External `codex exec` worker with model, effort, worktree and brief pointer; interactive coordinator only with manual wakes | No typed doorbell without a session backend; the tmux notify recipe does not wake a hand-started session. Worker execution uses the non-interactive recipe in [roles](../roles.md#how-to-run-each-engine). |
| Session backend | None: native harness task operations and OS process supervision only | No tmux or herdr support is implied. A supervised CLI needs its PID and OS start time recorded; native tasks need a unique handle and start time from the harness. If these cannot be probed, C5 remains partial. |

The six [backend operations](session-backends.md#operations) still bound
the design: create a worker in its worktree; expose the coordinator's live
view; deliver refs with an ack; probe identity before reading task/process
state; and stop all worker processes before cleanup. Native tasks without
attach or doorbell use the coordinator's view and a new pass after confirmed
completion. An unprovable stop preserves the worktree and is escalated.
Other adapters and backends are undeclared and unsupported here.

## Runtime contract

The mechanisms below are manual operating procedures using the existing
protocol, harness and OS facilities. An automated session runner remains
follow-up work; these rows do not claim it exists. Every partial capability
uses the [gap declaration](README.md#gap-declaration) format.

| Capability | Mechanism | Gap |
|---|---|---|
| C1 Wake on event | Coordinator sweeps GitHub and claims on each owner turn and worker completion; supported harness task completion can return control to it. No model-turn polling is prescribed. | C1 wake on event: partial, compensated by the §6 sweep on the next owner turn or delivered worker completion; residual risk: CI, steering, deadlines and other changes wait while the coordinator is idle or closed. Claude Code background completion is harness-dependent; Codex needs an owner turn without a backend. |
| C2 One consumer per event | Coordinator routes each live event to the protocol's one consumer, checking the pass/head marker and claim before dispatch; duplicate receipts do not create another pass. | None under this manual procedure; no shared event listener is claimed. |
| C3 Messages by reference, proof of delivery | Brief pointers, item/PR/full SHA and finding links go through native task dispatch or the CLI prompt. The receiver re-reads live state and writes an ack in durable status. | C3 messages by reference: partial, compensated by checking the ack and applying the protocol's bounded retry/escalation on the next coordinator wake; residual risk: no independent timer detects a lost handoff while the session is idle. A dispatch handle alone is not delivery proof. |
| C4 Status protocol | Each worker writes `ack`, then `done`, `blocked`, `paused` or `failed` with refs to its status file; coordinator reads these without the worker transcript. A missing final status goes to C5. | None under this manual procedure; native completion alone is not a pass result. |
| C5 Liveness | Inspect native task state, the recorded CLI PID/start time or, for `hosted`, the control plane's state for the recorded session id externally; confirmed exit or absent identity means dead/missing. An unqueryable task, hung subagent or failed probe is ambiguous. | C5 liveness: partial, compensated by claim heartbeats, the §6 sweep and bounded re-check then escalation of ambiguous runs; residual risk: a native task lacking a probeable handle/start time cannot be proven alive or missing. Never restart it solely for stale progress. |
| C6 Isolation | Coordinator creates each unique worktree, worker and probe alike, under `paths.worktree_root` as `<n>-<sha7>-<role>-<pass>/` (the tmux runtime's one root, #316; never `/tmp` or another ad hoc path) from a fresh remote base and assigns it explicitly; teardown follows both C6 landed/discard checks, recording and preserving unlanded work. | C6 isolation: partial, compensated by explicit worktree assignment and manual C6 checks before removal; residual risk: native subagents may inherit the coordinator's cwd and bypass the assignment. If the harness cannot keep writes in the assigned worktree, that worker configuration is unsupported. |
| C7 Serial land | Synthesizer takes the repo's exclusive lock (an atomic `mkdir` of `$CREW_STATE/locks/merge.lock.d`, per the [synthesizer brief](../../templates/runtimes/session/synthesizer.md)) before the §7 re-check and holds it through head-bound land and merge post; inability to hold the lock blocks land. | None under this manual procedure; being in one chat is not a lock. |
| C8 Owner channel and SLA | Coordinator's interactive chat plus matching GitHub asks, with the protocol's awake-hours SLA, recommended default and auto-apply time. | C8 owner channel and SLA: partial, compensated by GitHub notifications and checking due asks at the next coordinator wake; residual risk: no session deadline watcher enforces timely defaults while the session is idle or closed. |
| C9 Ownership handoff | Run `mdstack ownership --runtime session` from the rendered [coordinator brief](../../templates/runtimes/session/coordinator.md) each wake and before dispatch, push, post or land; a non-owner or moving/unreadable record means read-only. Outgoing, the brief's steps drain, post the manifest with `offered` and, on `acked`, [stop](../handoff.md#prompt-stop): dispatch nothing more, end every worker keeping unlanded worktrees, post `stopped`, and the session ends. Incoming, it walks the [resume](../handoff.md#resume-and-reconcile) steps by hand: reconcile against live state, ack once per handoff id, hold diverged sets before dispatch, and lift `holds_added` only after `stopped`, the owner's confirmation or a guarded release. | C9 ownership handoff: partial, compensated by the brief's manual steps and the owner closing the outgoing session; residual risk: the tmux `mdstack handoff reconcile`, `ack`, `lift` and `stopped` tooling does not run here, so the plan, the single ack and the stop rest on the coordinator following the brief, and no runner stops wake sources while the session is idle. A takeover waits for confirmed stop and any land past its final gate. |

## Run parameters for hosted dispatch

A hosted or hand-dispatched session gets no runtime-filled run block, so the
coordinator builds it with the same helper `mdstack spawn` uses for tmux
([#647](https://github.com/mw-ding/mdstack/issues/647)) and never
hand-writes run parameters:

```sh
{ cat "<rendered-brief>"
  cli/mdstack brief --item "PR #42" --pass review --base "<full-head-sha>" \
    --round 2 --host "<session-host>" --engine "codex gpt-6.1-sol medium" \
    --flavor standard --comments "<review-comment-ids>"
} > "<dispatch-brief>"
```

`Item`, `Pass` and `Base` (the full head SHA the pass runs against) are
required; `mdstack brief` exits 2 and prints no block when one is missing or
empty. The optional fields are `Window`, `Round`, `Slot`, `Host`,
`Worktree`, `Engine`, `Claim`, `Flavor` and `Comments`; an omitted one is
left out. Re-read the live head just before building the block. A worker
whose brief lacks the block, or one of its required fields, does not start
the pass ([worker brief rules](../roles.md#worker-brief-template)).

The Grok Bot B1, B2 and V2 prompts follow this recipe for every build, fix,
review and validate worker turn, with the claim, engine and worktree filled
([#778](https://github.com/mw-ding/mdstack/issues/778)).

## Recovery and support boundary

On reopening, read ownership first, then GitHub heads, verdicts, CI, claims
and durable status. Reconcile each item from its current stage without
resetting rounds. Resume a builder on the existing PR branch; do not create
a second PR. Restart only externally confirmed dead/missing workers, in a
fresh worktree. Slow or unqueryable workers remain ambiguous and are
escalated; preserve their checkout until their processes are proven stopped.

The design is suitable only for an attended crew that accepts the declared
wake and SLA delays. A requirement for unattended progress cannot be met
by this binding. Any configuration that cannot preserve independent review,
isolation, exclusive landing or trusted ownership is **unsupported**, per
the contract's invariant floor; a gap never waives a merge gate.

## Implementation follow-ups

Profiles accept `session`, the renderer writes its briefs (#914) and
`mdstack up` starts the coordinator (#1548); the triage scan and sweep brief
run from a hosted trigger (#1404). Still to build: the lifecycle runner, durable receipts/status, external task/process identity probes,
worktree enforcement and safe teardown, lock handling and ownership guards.
Add a token-free wake/backstop and deadline path per supported coordinator
adapter, or retain the declared attended-only gaps. Verify real harness
completion and stop behaviour, lost acknowledgements, ambiguous runs,
session closure/recovery, unlanded cleanup and ownership transfer before
claiming any gap closed. Bootstrap targets alone supply none of these.
