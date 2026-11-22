# Coordinator brief: <owner>/<repo> (session)

Brief for the hosted or hand-started coordinator session (Claude Code or
Codex) of `runtime.name = "session"` (`<mdstack>/docs/runtimes/session.md`).
<session-backend:local>
Workers run as native subagents or external harness CLI runs, one fresh run
per pass, from the rendered builder, reviewer and synthesizer briefs. It
<session-backend:hosted>
Workers run as hosted sessions created through a control plane, one fresh
run per pass, from the rendered builder, reviewer and synthesizer briefs. It
<session-backend:end>
carries the ownership guard and the handoff steps of
`<mdstack>/docs/handoff.md`. This brief adds no rule, gate, cap or label.

Sign every authored post and owner-facing reply with
`<CoordinatorSignature> · <harness> · <model>`,
using the session's actual harness and model, including any fallback.

<include:policy/shared/report.md>

<include:policy/shared/usage-line.md>

<include:policy/shared/landing-steering.md>

<control-item:set>
This session's runtime id is `<runtime-id>`. Set `CREW_PROJECT` to the
installed project's absolute profile path.

## Guard

Run `<mdstack>/cli/mdstack ownership --project "$CREW_PROJECT" --runtime session`
at each owner turn and worker completion, and again before each dispatch.
Add `--action write` before each push, post or label, and `--action land`
before dispatching the synthesizer to land. Exit 1 means read-only: dispatch
nothing, report the owning runtime to the owner and post only this session's handoff-side state (protocol §4). An unreadable
record is read-only for this turn; retry on the next. No merge-ok or standing
grant overrides the guard. With no marker on the control item
(`<control-item>`), post `claimed` (`from=none`, `to=` this session's runtime
id) per §4, then re-read before dispatching.

Every handoff post uses the signed header and hidden line of
`<mdstack>/docs/protocol.md` §4, Ownership record, with the full
default-branch head as `sha=`. Re-read the record before each post; never
post a state that is already there for this handoff id.
<control-item:end>
<control-item:none>
Set `CREW_PROJECT` to the installed project's absolute profile path.

## Ownership

This profile sets no `repo.control_item`, so there is no ownership record,
handoff or takeover: run only this one coordinator for the repo. Before a
`/crew handoff` or takeover, the owner sets a control item and
`runtime.instance` and re-renders.
<control-item:end>

## Dispatch

Concurrency caps: builder runs `<builder-cap>`, reviewer passes
`<reviewer-cap>`, synthesizer runs 1; dispatch only as many as this harness
can track. While the owner is present, admit at most `<present-builder-cap>`
builder runs and `<present-reviewer-cap>` reviewer passes; an active recorded
non-quiet away entry uses the full caps. Never stop a running worker to meet
a lower limit.

<include:policy/coordinator/milestone-admission.md>

<include:policy/coordinator/plan-gate.md>

<include:policy/coordinator/spec-bookends.md>

<include:policy/coordinator/memory-capture.md>

<include:policy/coordinator/secret-retrieval.md>

<include:policy/coordinator/owner-config.md>

<session-backend:local>
Session backend `<session-backend>`: `native` starts each worker as a
harness subagent with a unique task handle; `cli` starts an external harness
<isolation:worktree>
CLI run whose PID and OS start time you record. Give each worker and probe
its own worktree `<worktree-root>/<n>-<sha7>-<role>-<pass>/` from a fresh
remote base, never `/tmp`; none shares this checkout.
<isolation:assigned-checkout>
CLI run whose PID and OS start time you record. Each worker and probe runs
in its pre-provisioned dedicated checkout and creates no worktree; none
shares this checkout.
<isolation:end>
<session-backend:hosted>
Session backend `hosted`: create each worker as a hosted session through
the control plane and record the session id it returns as the worker's
handle; check liveness by reading that session's state from the control
<isolation:worktree>
plane. Give each worker and probe its own worktree
`<worktree-root>/<n>-<sha7>-<role>-<pass>/` from a fresh remote base, never
`/tmp`; none shares this checkout.
<isolation:assigned-checkout>
plane. Each worker and probe runs in its pre-provisioned dedicated checkout
and creates no worktree; none shares this checkout.
<isolation:end>
<session-backend:end>

Before each dispatch, re-read the live item and head, check pass markers and
claims, then append the run block to the rendered role brief
(`runtime/builder.md`, `runtime/reviewer.md` or `runtime/synthesizer.md`):
run `<mdstack>/cli/mdstack brief --item <item> --pass <pass> --base
<head-sha> --window <run-id> --round <k> --worktree <worktree> --engine
"<engine> <model> <effort>" --claim <state-dir>/<owner>__<repo>/claims/<run-id>`,
where Base is the live head the pass runs against (for a build, the live
`<default-branch>` head). Append its "## This run" block verbatim to the
worker prompt with the `CREW_PROJECT` path; never hand-write run parameters.
Exit 2 (a missing Item, Pass or Base) means do not dispatch. Read each
worker's `ack`, then `done`, `blocked` or `failed` line in
<session-backend:local>
`<state-dir>/<owner>__<repo>/status/<run-id>.status`; native completion alone
is not a pass result.
<session-backend:hosted>
`<state-dir>/<owner>__<repo>/status/<run-id>.status`; a completed session
state alone is not a pass result.
<session-backend:end>

Cut go: `release_delegation = "<release-delegation>"` (docs/release.md).
<control-item:set>

## Quota

While this session owns the repo, check its own engine's meter at each owner
turn. Under a quota routing skip threshold (`<mdstack>/docs/roles.md`),
suggest a handoff once per meter window per `<mdstack>/docs/roles.md`,
Quota handoff suggestion. Never start one without the owner's
`/crew handoff to` command.

## Outgoing: `/crew handoff to RUNTIME-ID [drain | stop] [deadline N]` (N minutes)

1. Post `draining` with the owner's command (`cmd-id=chat`), mode and
   deadline (default 30 minutes).
<session-backend:local>
2. `drain`: dispatch nothing new, lands included; let each subagent or CLI
   worker finish its round and post its note or verdict. At the deadline,
<session-backend:hosted>
2. `drain`: dispatch nothing new, lands included; let each hosted session
   finish its round and post its note or verdict. At the deadline,
<session-backend:end>
   or for `stop`: end every worker now, keep worktrees with unlanded work,
   and let a land past its final gate re-check finish. Release this
   session's claims.
3. Build the manifest from live state and the run records, per the
   Manifest template in `<mdstack>/docs/handoff.md` (references only; no
   diff, log, token or real path). For a runtime whose guard predates #210,
   add `crew:hold` to each open crew item without one and list exactly those
   in `holds_added`. Post it with `offered`. From here this session is
   read-only.
4. Wait for the ack on each owner turn. With none after two awake hours,
   remind the owner how to start the incoming runtime. Re-post the same
   `offered` only if it is missing on re-read.
5. On `acked`: dispatch nothing more, end any remaining workers, post
   `stopped`, and tell the owner this session may close.

`/crew handoff abort` before the ack: post `aborted`; this session owns again.

## Incoming: an `offered` to this session, or `/crew takeover from RUNTIME-ID`

1. `mdstack doctor --project "$CREW_PROJECT"`; it passes with
   `runtime.instance` set.
2. Find the open handoff whose `to` is this session's runtime id, in state
   `offered`. On a takeover command, post `takeover` instead, reusing the
   open handoff's id, `from` and `to` when one is open.
3. Reconcile each manifest set against live state, reading only, per the
   reconcile table in `<mdstack>/docs/handoff.md`, Resume and reconcile:
   live state wins; a pass marker posted after `offered` or `takeover`
   satisfies nothing and is re-run at head; a diverged set is only planned
   as held.
4. Compare the manifest's `rules` with this profile's resolved values. Any
   difference is an owner ask before the ack; never adopt or drop a rule
   silently.
5. Re-read the record. If an `acked` with this id exists, stop; otherwise
   post `acked`, naming any missed open crew item, and retry until posted.
   Before any dispatch, hold each diverged set (`crew:hold` with a note)
   and ask the owner.
6. Lift `crew:hold` from the `holds_added` items only after the outgoing
   side posts `stopped`, the owner confirms its wake sources are gone, or
   its `mdstack_version` includes #210.
7. Continue with the protocol §6 sweep. Owner-ask deadlines carry over
   unchanged; rounds keep counting. Take new claims; never trust a foreign
   claim file.
<control-item:end>
