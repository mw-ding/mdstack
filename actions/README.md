# Actions contract

Status: draft v0.1 (2026-11-07). The terminal environment implements
`check-ownership`, `heartbeat`, `notify`, `ack` and `report` as
[`mdstack action`](../docs/runtimes/tmux.md#mdstack-action) (#1232); the rest of
the implementation is milestone M32. Issue
[#1218](https://github.com/mw-ding/eng-crew/issues/1218); tracking
[#1180](https://github.com/mw-ding/eng-crew/issues/1180).

This directory is the `actions/` module of the
[proposed module layout](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703508949):
the generic verbs a role uses to coordinate, whatever environment, connector
or harness carries them out. Roles name an action; an environment or
connector implements it.

| File | What it owns |
|---|---|
| [README.md](README.md) (this file) | The vocabulary: each action's semantics, inputs, outputs and outcomes |
| [cli.md](cli.md) | The CLI contract: command names, arguments, exit codes and JSON output |
| [mapping.md](mapping.md) | How tmux, herdr and Grok Bot implement each action today, with gaps marked |
| [contract.py](contract.py) | The conformance kit: contract tests `mdstack pack test` runs against a pack's adapters with fakes ([packs](../docs/packs.md#conformance-kit), #1236) |

Sources: the action families A1–A20 come from the
[#1213 research finding](https://github.com/mw-ding/eng-crew/issues/1213#issuecomment-6702910041);
the choice to own these semantics, expose them through a CLI or API (MCP
optional) and use CloudEvents/CDEvents names for events comes from the
[#1214 standards survey](https://github.com/mw-ding/eng-crew/issues/1214#issuecomment-6703298207).

## Scope and authority

This contract adds no rule, gate, cap, marker field or label. The
[protocol](../docs/protocol.md) still owns every gate, marker schema, round
and permission; the [runtime contract](../docs/runtimes/README.md) still owns
the C1–C9 guarantees. An action is the generic way to perform a step those
documents already require. Where this file and the protocol disagree, the
protocol wins and this file is the one to fix.

An action never grants authority. Which role may call it, and when, stays
with the protocol and the role's procedure. Calling `land` does not make the
caller the synthesizer, and a `completed` `post-marker` is not the effect the
marker records.

## Common envelope

Every call carries these inputs where they apply. An action lists only the
inputs it adds.

| Input | Meaning |
|---|---|
| `actor` | The signed identity making the call (role display name and login) |
| `role` | The calling role: coordinator, builder, reviewer, synthesizer or researcher |
| `project` | The project the call acts on (profile path or project id) |
| `item` | Tracker item or change the call is about, when it has one |
| `head` | Expected full 40-character head SHA, when the effect is head-bound |
| `key` | Idempotency key: the same key and inputs never cause a second effect |

Messages and results carry references (item, change, full SHA, link, path),
never payloads such as findings or evidence text
([C3](../docs/runtimes/README.md#c3-messages-by-reference-with-proof-of-delivery)).

## Outcomes

Every call ends in exactly one outcome. A caller acts on the outcome, never
on text or timing.

| Outcome | Meaning | Caller's next step |
|---|---|---|
| `completed` | The effect happened, or the read returned current state; the result names its durable reference | Continue |
| `pending` | The request was accepted and is not finished, such as a queued spawn, an async land or an unacknowledged message | Wait on the named reference or re-read later; never treat as done |
| `stale` | The trigger no longer matches live state: the head moved, the item closed, or the pass already has its record | Stop this step with no effect; re-read and start over if still needed |
| `refused` | A precondition failed before any effect: no authority, held, unsupported, invalid input, existing claim | Do not retry unchanged; report or route |
| `failed` | The effect was attempted and did not happen | Retry within the step's bound, then report `failed` or `blocked` |
| `unknown` | The caller cannot tell whether the effect happened, such as a timeout after a write | Read back before any retry; never treat as success or as failure |

`unknown` never becomes `completed` by waiting. A blind retry after
`unknown` is forbidden for effects that are not idempotent under `key`
(`post-marker`, `publish-change`, `land`).

## Capability declaration

Each environment and connector declares, per action, one of:

- `supported`: implemented with every guarantee listed for the action;
- `emulated`: implemented another way with the same guarantees, named in the
  declaration;
- `unsupported`: not available; a call returns `refused` with reason
  `unsupported`.

A partial implementation that drops a guarantee is `unsupported` plus a gap
declaration ([runtime contract gap declaration](../docs/runtimes/README.md#gap-declaration)),
never `supported`. A familiar tool name is not evidence of support.

## Events

`wait` names the events it waits for. Event names use the CloudEvents 1.0
`type` attribute. Where a CDEvents 0.5.1 event matches the occurrence, use
its full versioned type; otherwise use an mdstack type under `dev.eng-crew.`.

| Occurrence | Event type |
|---|---|
| Change opened | `dev.cdevents.change.created.0.4.0` |
| Change reviewed (any result) | `dev.cdevents.change.reviewed.0.3.0` |
| Change merged | `dev.cdevents.change.merged.0.3.0` |
| CI run finished (any result) | `dev.cdevents.pipelinerun.finished.0.3.0` |
| New head pushed on a change | `dev.eng-crew.change.head-moved` |
| Tracker item ready or changed | `dev.eng-crew.item.changed` |
| Milestone closed | `dev.eng-crew.milestone.closed` |
| Message for a role | `dev.eng-crew.message.sent` |
| Run status reported | `dev.eng-crew.run.reported` |
| Owner steering command | `dev.eng-crew.owner.command` |
| Deadline or backstop due | `dev.eng-crew.timer.due` |

An event only wakes its consumer. A `reviewed`, `finished` or `merged`
event is never a verdict, green CI or merge permission: the consumer reads
live state before any effect. Duplicate events are detected by CloudEvents
`source` plus `id`.

## Actions

Twenty-two families, A1–A22. Some families have operations (`claim` /
`release`); the CLI names them as subcommands ([cli.md](cli.md)). For each
action, the outcomes row lists only outcomes with an action-specific
meaning; the others keep their meaning from [Outcomes](#outcomes).

### A1 `read`

Load live tool-of-record state (item, change, head, CI, labels, markers,
control records) or a pinned local artifact, with its version and source.

- **Inputs:** `ref` (what to read), `kind` (item, change, ci, markers,
  control, artifact), optional `at` (pinned revision; default live).
- **Outputs:** the state, its version (head SHA, updated time or revision)
  and provenance (source and read time).
- **Outcomes:** `completed` returns current state; `stale` when `head` was
  given and live differs; `failed` or `unknown` when required state cannot be
  read. A caller that needed the state blocks; it never assumes a clear value.

### A2 `resolve-policy`

Compute the effective rigor for an item at a head: flavor knobs, lane,
sensitive class and the gates and capabilities that apply. Computes only; it
applies no label.

- **Inputs:** `item`, `head`, `paths` (full diff paths, both rename paths).
- **Outputs:** effective review, validation, evidence, caps and merge modes;
  lane; sensitive matches; the records the result came from.
- **Outcomes:** `completed` with a missing flavor record returns thorough and
  flags `flavor-missing`; `failed` when resolution is unreadable, and the
  caller blocks.

### A3 `check-ownership`

Check that this runtime may take an action on the project now, under the
ownership state machine ([protocol §4](../docs/protocol.md)). Called before
every start, write and land.

- **Inputs:** `action` (start, write or land).
- **Outputs:** the ownership state and owning runtime.
- **Outcomes:** `completed` means permitted; `refused` when another runtime
  owns the project, a handoff is in transit, or a draining runtime asks to
  start or land. Unreadable ownership is `refused`. No merge-ok or grant
  overrides it.

### A4 `claim` / `release`

Reserve one logical unit of work (item, pass, head, round) atomically, so
only one run handles it; release it after the result is recorded.

- **Inputs:** `claim-key` (item, pass, head and round); for `release`, the
  claim handle.
- **Outputs:** a claim handle and its creation time.
- **Outcomes:** `refused` when a live claim exists; reclaim needs the
  liveness conditions of [C5](../docs/runtimes/README.md#c5-liveness), and an
  old timestamp alone never proves the holder dead. `release` of a claim not
  held is `stale`.

### A5 `heartbeat`

Record that a claimed run is still making progress, at least every five
minutes and after each commit, push and post. Separate from the
environment's own liveness probe.

- **Inputs:** claim handle, UTC time.
- **Outputs:** the recorded heartbeat time.
- **Outcomes:** `refused` when the claim is not held by the caller. A missing
  heartbeat is a silence signal for supervision, never proof of death or a
  restart reason on its own.

### A6 `notify` / `ack`

Deliver a reference-only handoff to a role with a message id; the receiver
acknowledges pickup before processing.

- **Inputs:** `to` (role or run), `kind` (handoff kind such as fix, ci-red,
  review, land), `refs`; for `ack`, the message id.
- **Outputs:** message id; for `notify` once acknowledged, the receipt
  reference.
- **Outcomes:** `completed` only once an ack or receipt names the message;
  `pending` when sent without receipt yet; `refused` for payload content or
  invalid refs; `unknown` when the sender cannot tell whether the message was
  submitted. A typed or posted message alone is not delivery. The bounded
  re-nudge and escalation stay as in C3.

### A7 `wait`

Keep an actionable wake source armed while work is in flight, then return
when an event in the set arrives or the deadline passes. Waiting costs no
model turns where the environment supports it.

- **Inputs:** `events` (event types from [Events](#events) with their refs),
  `deadline`, `backstop` (re-check interval).
- **Outputs:** the event that fired (type, `source`, `id`, refs) or the timer
  that came due.
- **Outcomes:** `completed` on an event or due timer; `refused` when no wake
  source can be armed. Silence never means an event happened; a missed event
  is found by the next sweep or backstop.

### A8 `report`

Record a run's status where the coordinator reads it without opening the
run: `ack`, `done`, `blocked`, `paused` or `failed`
([C4](../docs/runtimes/README.md#c4-status-protocol)).

- **Inputs:** `status`, `refs` (output record, PR, head), `reason` for
  blocked, paused or failed.
- **Outputs:** the status record reference.
- **Outcomes:** `refused` for `done` without an output reference. Pass
  completion is reported separately from run teardown.

### A9 `spawn-worker`

Start, or queue, one fresh run for one pass: pinned item, pass and base, a
brief, an identity, the actual engine, model and effort, an isolated
workspace and a claim. Routed through the role's lead where the protocol
requires it.

- **Inputs:** `pass`, `item`, `base`, `engine`, `model`, `effort`, brief
  reference, claim handle.
- **Outputs:** run handle and start time (the C5 identity), workspace path.
- **Outcomes:** `pending` when queued for capacity (never reported as
  started); `refused` for a missing field, unsupported harness or missing
  brief; `failed` after start failure, with the workspace cleaned up safely.

### A10 `supervise`

Probe, stop or restart a run by its external identity.

- **Inputs:** run handle and start time; `op` (probe, stop or restart).
- **Outputs:** for probe, the C5 class (`alive`, `dead`, `missing`,
  `ambiguous`); for stop, proof that all the run's processes ended.
- **Outcomes:** probe `completed` returns a class, and `ambiguous` is a class,
  not an outcome; `refused` for restart unless the class is `dead` or
  `missing` (or a binding's declared exception); stop `unknown` when
  processes may survive, which keeps the workspace.

### A11 `workspace`

Create a unique checkout at a fresh base for a run, or remove one run's
checkout under the [C6](../docs/runtimes/README.md#c6-isolation) rules.

- **Inputs:** `op` (create or remove), run handle, `base`; for remove, an
  optional owner discard reason.
- **Outputs:** path; for remove, the unlanded paths and commits found, if
  any.
- **Outcomes:** `refused` for a shared, primary or existing path on create,
  or unlanded work on remove without a recorded discard; `failed` when the
  fresh fetch fails (create) or the landed check cannot run (remove keeps
  the checkout).

### A12 `artifact`

Write, append, update or remove a typed local artifact: a brief, a review
section, a step summary, a deadline, a land intent, a queue entry.

- **Inputs:** `op`, `type`, `ref`, content reference.
- **Outputs:** the artifact reference and version.
- **Outcomes:** `refused` for an operation the type does not allow (such as
  update of an append-only artifact) or removal while it is still
  referenced. A consumer that needs a missing artifact blocks; it never
  substitutes transcript memory.

### A13 `post-marker`

Publish one signed protocol record (verdict, fix note, ack, research,
gate-status and the other record types in [protocol §4](../docs/protocol.md))
and return its reference. The backend picks the post form (issue comment,
COMMENT review or formal review) from the record type and identity mode.

- **Inputs:** `target` (item or change), `type` (record type), body
  reference, `head` and round where the record type has them.
- **Outputs:** the post reference and the marker as posted.
- **Outcomes:** `refused` for the wrong role, type, head or round, a
  malformed record, or a duplicate for this pass at this head; `unknown` when
  delivery is uncertain, and the caller reads back before posting again.
  Only diagnostic gate-status records may be edited in place.

### A14 `tracker`

Apply one tracker mutation: create, edit, assign, place on a board, label or
close an item, after re-reading it.

- **Inputs:** `op`, `ref`, fields.
- **Outputs:** the item reference and its new state.
- **Outcomes:** `refused` for a duplicate item or disposition, a mutation of
  held work the calling procedure does not allow, or closing an umbrella
  through incidental linkage; `stale` when the item changed since the read.

Tracker reads are backend operations, not actions: the triage scan reads
`tracker.list-items` and, when a backend binds it, the conditional
`tracker.read-comments` per open item
([interfaces](../docs/interfaces.md#tracker), #1960).

### A15 `run-check`

Run a permitted check, repro, capture or drift step at a pinned head and
return its result with provenance. The calling procedure decides whether it
is builder precheck, independent validation or mirror proof.

- **Inputs:** `command` (named check), `head`, `scope`, `proof-kind`.
- **Outputs:** exit code, captured output reference, head, where it ran.
- **Outcomes:** `completed` means the check ran, whatever its exit code; the
  check's pass or fail is in the result. `refused` for an unset or
  unpermitted command, which the caller records as a reasoned N/A. A red or
  unknown CI result is never turned into a local pass.

### A16 `publish-change`

Push tested commits and open, update or publish one linked, non-draft change;
prune a terminal, owned branch.

- **Inputs:** `op` (open, upload, publish or prune), branch, `item`, body
  reference.
- **Outputs:** change reference and head.
- **Outcomes:** `refused` when an open change already closes the item (adopt
  it instead), for a force-push to a shared branch, or an edit to an original
  body; `unknown` when the push or open may have happened, and the caller
  reads back before retrying.

### A17 `update-base`

Bring a change up to date with its base at land time by the backend's
declared merge or rebase strategy, without editing content.

- **Inputs:** change, `head`, strategy.
- **Outputs:** new base and head SHAs; the earlier head stays readable.
- **Outcomes:** `stale` when the head moved first; `refused` on a conflict or
  content change, which goes to the builder.

### A18 `compare-content`

Compare the reviewed patch (base B, head H) to the applied patch (B2, H2),
keeping paths, modes, whitespace and binary changes.

- **Inputs:** B, H, B2, H2.
- **Outputs:** `equal` or `different`, with the differing paths.
- **Outcomes:** `completed` with either result; `failed` when a patch is
  unavailable. Equality is evidence a verdict may carry; it is not landing
  permission.

### A19 `land`

Synthesizer only: take the land exclusion, re-run every live gate, land the
checked head and record the result. Operations: `acquire`, `request`,
`status`, `finish`, `release`.

- **Inputs:** change, `head`, land rule (direct or train member).
- **Outputs:** landed revision; for async backends, the land intent
  reference.
- **Outcomes:** `refused` when the lock is held, a gate fails or the caller
  is not the synthesizer; `stale` when the head moved; `pending` while an
  async land is queued or landing; `unknown` after an uncertain request, and
  the caller reads status back, never resends. Only `completed` with a landed
  revision permits the merge record.

### A20 `owner-channel`

Coordinator only: send the owner an outcome or an ask with its durable
tracker record, track the awake-hours deadline and record the owner's
actual decision.

- **Inputs:** `op` (ask, update or close), `refs`, deadline and default for
  an ask, decision text for close.
- **Outputs:** the ask or decision record reference.
- **Outcomes:** `refused` for an unverified commenter or a duplicate command
  id; `pending` while an ask is open. Silence never becomes permission, a
  cleared stop or a handoff; only the posted default applies at the deadline.

### A21 `knowledge-read`

Read one knowledge source the calling role declares (`knowledge` in its
[role definition](../docs/roles-registry.md#schema)) from the owner's
external knowledge service, into a local file. Knowledge is context only:
no verdict, marker, state tag or gate input comes from it
([portable spec P3](../docs/specs/portable.md)).

- **Inputs:** `source` (a source name the role declares), `out` (a local
  path that git ignores or that is outside any work tree).
- **Outputs:** the out path, the source's page reference, title and last
  edited time.
- **Outcomes:** `refused` when the role does not declare the source, the
  install's private config has no pointer or credential for it, the config
  is tracked by git, or `out` could be committed; `failed` when the service
  cannot be read.

### A22 `knowledge-propose-edit`

Propose a change to one declared knowledge source. A role never changes owner
knowledge directly: the proposal waits for the owner, or the backend's own
review step, to accept it.

- **Inputs:** `source` (a source name the role declares), body reference (a
  local file with the proposed text).
- **Outputs:** the proposal reference (such as a comment id).
- **Outcomes:** `completed` with the earlier proposal, and no second one,
  when the same key and inputs were already proposed; `refused` as for
  `knowledge-read`, for an empty or oversized body, or when the key already
  names a different proposal; `unknown` when delivery is uncertain, and the
  caller reads the source back before proposing again.

## Personnel binding

The [personnel consumer](../docs/personnel.md#thin-binding-and-consumer-loading)
supplies these actions through its own host. Its reviewed binding declares
capabilities and maps operations; importing content executes no action.
