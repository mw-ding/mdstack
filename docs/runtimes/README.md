# Runtime contract

What every runtime must provide so the core protocol keeps its guarantees,
whichever runtime runs the crew (portable mdstack, roadmap 13.8,
[#120](https://github.com/mw-ding/mdstack/issues/120); contract set decided on
[#130](https://github.com/mw-ding/mdstack/issues/130)). Terms are in
[concepts.md](../concepts.md). This page adds no rule, gate, cap, marker field
or label; the [protocol](../protocol.md) still owns them. Each binding
([grok-bot.md](grok-bot.md); [tmux.md](tmux.md), shipped in M14 and M14.1) fills in
a contract table against it. The [session binding](session.md) is partly
built and attended-only: its selector, briefs, `mdstack brief`, `mdstack up`
and `mdstack upgrade` are built, while worker lifecycle stays a manual
procedure and its runner is design only. [Support](#support) lists what each
runtime and harness ships.

Naming: in the [four axes](../concepts.md#four-axes) a runtime is an
**environment**; this directory keeps the older word and its paths. The
terminal environment's code is in
[../../environments/](../../environments/README.md) and harness adapters in
[../../harnesses/](../../harnesses/README.md).

## Support

What ships today, per runtime, session backend and harness. Status is one
of **shipped** (built and runs a crew unattended), **attended or manual**
(built parts need a person at the lifecycle or setup step) and **design**
(described, not built). Each gap is declared in the linked page's contract
table or adapter, in the [gap format](#gap-declaration); this table
summarizes them and changes none.

| Component | Kind | Status | Declared gaps and limits | Page |
|---|---|---|---|---|
| tmux | Runtime | Shipped: the `mdstack` CLI, watcher, poll, leads and land | C1, C5, C7, C8 partial; C9 unsupported (manual pause before another runtime starts); no work moves while the machine sleeps | [tmux.md](tmux.md#runtime-contract) |
| Multi-device tmux | tmux extension | Shipped in part: host inventory, runner hosts, placement, remote lifecycle, attach and wakes, proved on fakes and a lab host; the rest is design | Those of tmux; an unreachable host's runs are reconciled or abandoned with a tombstone | [multi-device.md](multi-device.md) |
| session | Runtime | Attended or manual: selector, briefs, `mdstack brief`, `mdstack up`, `mdstack upgrade`, triage sweep. Design: the lifecycle runner, durable receipts, identity probes, worktree enforcement, locks, ownership guards, token-free wake | C1, C3, C5, C6, C8, C9 partial; unattended progress unsupported; no merge trains | [session.md](session.md#runtime-contract) |
| Grok Bot | Runtime | Attended or manual: routine templates and rendered skills ship; a person creates and removes each routine on the bot | C1, C2, C3, C5, C6 partial; C9 unsupported (manual hold and routine removal); no merge train window | [grok-bot.md](grok-bot.md#runtime-contract) |
| tmux | Session backend | Shipped (default) | None beyond the tmux runtime | [session-backends.md](session-backends.md#tmux-tmux) |
| herdr | Session backend | Shipped, local only | C1, C3, C6, C8 partial; no in-place `mdstack upgrade`; no remote hosts | [session-backends.md](session-backends.md#herdr-capability-gaps) |
| Claude Code | Harness | Shipped: role and coordinator launch, `Stop`-hook turn-end guard | Folder trust accepted once by the owner | [harness-adapters.md](harness-adapters.md#claude-code-claude-code) |
| Codex | Harness | Shipped: role and coordinator launch | C1 partial: `mdstack up` does not install the turn-end `notify` recipe; the watcher's typed wake covers it | [harness-adapters.md](harness-adapters.md#codex-codex) |
| Pi | Harness | Shipped with gaps: launch in `bypass` mode only | C1 partial: no turn-end guard, live wake timing unverified; C5 partial: custom extension dialogs not recognized | [harness-adapters.md](harness-adapters.md#pi-pi) |
| Cursor | Harness | Shipped with gaps: launch in `bypass` mode only | C1 partial: no turn-end guard, wake timing unverified on the real CLI; C5 partial: trust and login screens not detected; effort not enforceable | [harness-adapters.md](harness-adapters.md#cursor-cursor) |
| Muse | Harness | Shipped with gaps: launch in `bypass` mode only | C1 partial: no turn-end guard, live wake timing not exercised | [harness-adapters.md](harness-adapters.md#muse-muse) |
| OpenCode | Harness | Review engine only: no interactive launch, so not a role or coordinator choice | Not spawned from a tier order | [harness-adapters.md](harness-adapters.md#opencode-opencode) |

A harness or backend not listed is unsupported. Bootstrap install pointers
for a harness add no runtime ([bootstrap Q4](../bootstrap.md#q4-install-targets)).

## Contract

| # | Capability | Guarantee it protects |
|---|---|---|
| C1 | Wake on event | Every stage starts without a human nudge; nothing idles blind while work is in flight; waiting costs no model turns |
| C2 | One consumer per event (spec R8) | No double work; each event is handled once |
| C3 | Messages by reference, with proof of delivery | No payload in messages; no hand-off is silently lost |
| C4 | Status protocol `done` / `blocked` / `paused` / `failed` / `ack` | The coordinator always knows a run's outcome without reading its session |
| C5 | Liveness classes `alive` / `dead` / `missing` / `ambiguous` | Stuck work is detected; a restart never starts a duplicate run |
| C6 | Isolation | Runs never share or damage a checkout; no orphans; teardown never deletes work that has not landed |
| C7 | Serial land | One land at a time |
| C8 | Owner channel and SLA | Asks reach the owner and are answered or defaulted within the protocol SLA |
| C9 | Ownership handoff | One runtime acts on a repo at a time; work moves to another runtime with nothing lost or done twice |

### C1. Wake on event

A state change (new tracker item, new change head, CI signal, verdict, land,
steering command, run status) wakes the role that consumes it, by push or by
poll. A role with work in flight never ends a turn without a pending wake
source: either a subscribed event or a scheduled re-check. A missed wake is
picked up by the next wake's sweep ([protocol §6](../protocol.md#6-duties-on-wake-all-roles)
step 3) or by a scheduled backstop.

Waiting costs no model turns. Only an actionable event (a state change its
consumer must act on) or a due backstop starts a turn; the wait between them
is token-free, such as a platform push or a plain-script watcher with no
model. A backstop's interval backs off while nothing is in flight. A
token-free poller, such as tmux's `mdstack poll`, reads the tool of record
without a model and is not model-turn polling.

A runtime that cannot run a token-free wait may instead start model turns on
a timer (model-turn polling), only with the same backoff, and declares it as
a C1 gap in its contract table ([gap declaration](#gap-declaration)), naming
the interval and its backoff.

### C2. One consumer per event

Each event is delivered to exactly one consuming role. Any exception is named
in the binding with its reason and must be cleanup-only (it may not start a
pass). Re-delivery of the same event is a no-op through the idempotency rule
in [protocol §6](../protocol.md#6-duties-on-wake-all-roles) step 2: an existing
marker or lock for this pass at this head ends the wake.

### C3. Messages by reference, with proof of delivery

A message between roles names state; it never carries it. It holds only
references: tracker item, change, full head SHA, a link to the post holding
findings or evidence, or a file path. The receiver re-reads live state before
acting. The sender gets proof that the message arrived (a receipt or an `ack`
naming the message) and retries or escalates when no proof arrives in a
bounded time. Lifecycle actions (interrupt, stop, restart) never travel as
message text.

### C4. Status protocol

Every run reports exactly one of these, recorded where the coordinator reads
it without opening the run's session:

| Status | Meaning |
|---|---|
| `ack` | Run accepted the work or message and started |
| `done` | Pass finished; its output (change, marker, post) exists |
| `blocked` | Cannot continue without another role or the owner; names what it needs |
| `paused` | Stopped on purpose (hold, steering); resumes on an explicit command |
| `failed` | Stopped on an error it cannot fix; names the error |

A run that ends without reporting a status is treated as `missing` under C5.

### C5. Liveness

The runtime classifies every in-flight run without relying on the run itself
to report:

| Class | Meaning | Allowed action |
|---|---|---|
| `alive` | The run exists and is working or waiting on a known wake | None |
| `dead` | The run existed and has exited without a final status | Restart in a fresh worktree |
| `missing` | A run is recorded as in flight but none exists with its recorded identity | Restart in a fresh worktree |
| `ambiguous` | The runtime cannot tell (no progress signal, probe failed) | Re-check, then escalate to the coordinator after a bounded time; never restart, except the tmux binding's two kill-and-respawns: a window whose launch options should have prevented its dialog, once (the coordinator brief's dialog rule), and a stuck synthesizer after a failed nudge, once per PR ([Q7](tmux.md#q7-failure), [#312](https://github.com/mw-ding/mdstack/issues/312)) |

A run is identified by a unique handle plus its start time, both recorded at
spawn. A probe that finds a different handle or start time classifies the run
as `missing`, never `alive`, so a same-named replacement is never taken for
the recorded run. The start time is required because a runtime may reuse a
handle (for example, after a server restart).

Only `dead` or `missing` authorizes a restart, so a slow run is never
duplicated. The nudge cap and escalation of
[protocol §5](../protocol.md#5-rounds-and-escalation) still apply.

### C6. Isolation

Each run works in its own unique worktree
([roles: worker isolation](../roles.md#worker-isolation-worktrees)), never the
main checkout and never a branch-named shared path. The worktree starts from a
fresh base: the current remote default branch, or the parent change's branch
for stacked work. Spawn refuses a path that breaks these rules. Teardown
deletes that run's worktree and build output only. Where several crews share
a host, the terminal binding also claims each run's working copy host-wide,
so another crew's run never starts in it
([working-copy claims](multi-device.md#working-copy-claims)).

Teardown never removes a worktree whose work has not landed (decision
[#160 row 3](https://github.com/mw-ding/mdstack/issues/160#issuecomment-6531125583)).
It removes one only when either holds:

- **Provably landed.** The worktree has no uncommitted or untracked paths
  (ignored build output does not count), and every commit on its head is
  contained in a freshly fetched remote ref: the default branch, the run's
  branch or the change head. A check that cannot run, such as a failed
  fetch, counts as not landed.
- **Explicitly discarded.** The owner decided to discard the work, and the
  reason, with the list of unlanded paths and commits, is recorded on the
  run's change or tracker item before anything is removed. If the record
  fails, nothing is removed.

Otherwise the run may still be stopped, but its worktree stays and the
runtime names the unlanded paths and commits.

### C7. Serial land

At most one land runs per repo at a time, under an exclusive lock taken before
the final [§7 gate](../protocol.md#7-merge-gate-synthesizer) re-check and
released after the merge post. The land is bound to the head the gate checked.

A backend that declares an asynchronous land with `serializes = true`
meets C7 itself: it lands at most one change per repo at a time, each on the
tip the previous land left, so no local lock is taken. A bare asynchronous
land holds the lock from the final gate re-check until the terminal land
status and the merge post
([asynchronous land](../interfaces.md#asynchronous-land-design), #873).

### C8. Owner channel and SLA

Owner asks go through one channel owned by the coordinator, recorded on the
tool of record (invariant I5), with the 2h awake-hours SLA, recommended
default and auto-apply time of
[protocol §6](../protocol.md#6-duties-on-wake-all-roles). No role asks the
owner only inside its own session.

### C9. Ownership handoff

Only one runtime instance may act on a repo at a time
([protocol §8](../protocol.md#8-safety)), and the owner can move that
ownership to another runtime and back
([handoff design](../handoff.md), #157). Who owns the repo is recorded on
the tool of record (the ownership record lands with
[#210](https://github.com/mw-ding/mdstack/issues/210)). A runtime:

- **Guards.** It reads the ownership record at the start of every wake and
  again right before each push, post and land. When it is not the owning
  runtime, or ownership is moving, it runs read-only: it reads and reports,
  and never starts a pass, posts a pass marker, sets a state tag or lands.
  A repo with no record yet keeps today's behaviour; an unreadable record
  counts as not owning, for that wake.
- **Drains.** On the owner's handoff command it starts no new pass. Its
  runs end by themselves, or stop at once when the owner chose to stop; a
  land past its final gate re-check (C7) always finishes, and unlanded work
  stays (C6).
- **Stops promptly.** Once the incoming runtime acknowledges, or the owner
  commands a takeover, every wake source of the outgoing runtime stops or
  no-ops within one wake or poll interval, including one in the middle of a
  wait.
- **Resumes.** As the incoming runtime, it reconciles from the tool of
  record (the handoff manifest is a hint; live state wins), acknowledges
  once per handoff id, and continues each item from its current stage
  without resetting rounds.

## Role-lead design

A binding that delegates worker lifecycle to role leads describes their
authority, profile caps, scheduling inputs, recorded handoffs, liveness and
recovery against C1–C6 and C9. A lead schedules independent review passes;
it does not supply their verdicts or merge permission. The tmux
[proposed role-lead contract](tmux.md#role-leads-proposed-521) awaits design
review before implementation; it adds no capability or protocol gate.

## Gap declaration

A binding that cannot meet a capability fully declares it in its contract
table, in this form:

```text
<C#> <capability>: <unsupported | partial>, compensated by <mechanism>; residual risk: <what can still go wrong>
```

Rules:

- Every gap names a compensating mechanism. A gap with none makes the profile
  **unsupported**.
- A gap that would weaken an invariant from
  [portable spec §3](../specs/portable.md#3-invariants) makes the profile
  unsupported. It is never silently weakened.
- A gap declaration changes no protocol rule; the compensation must already
  exist in the binding or the protocol.

## Harness adapter interface

A runtime that launches agent CLIs (harnesses) in role sessions describes
each one as an adapter in [harness-adapters.md](harness-adapters.md): launch
line, trust and first-run dialogs, turn-end and wake recipe, idle detection
and expected foreground process, each tied to the capability it serves (C1,
C3 or C5). Claude Code and Codex are filled in.

## Session backend interface

A runtime that hosts role sessions in a terminal multiplexer or a similar
program (a session backend) describes it in
[session-backends.md](session-backends.md): create in the background,
attach (read-only by default), doorbell, identity probe (handle plus start
time, per [C5](#c5-liveness)), state read and kill, each tied to the
capability it serves. tmux is filled in.
