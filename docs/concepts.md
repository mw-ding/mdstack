# Concepts

Shared vocabulary for the abstract protocol (portable mdstack, roadmap 13.1,
[#113](https://github.com/mw-ding/mdstack/issues/113)). Later M13 changes use
these terms when they split the core from its bindings. The
[four axes](#four-axes) and the [team and module terms](#team-and-modules)
come from the team spec ([specs/team.md](specs/team.md), #1216). Each entry
gives the definition, the invariant it touches, and today's mapping.

This page defines terms only. It changes no rule, gate, cap, marker field or
label. Where a term and an existing doc disagree, the existing doc wins until
a later roadmap PR moves the rule. Invariants are numbered as in
[portable spec §3](specs/portable.md#3-invariants): I1 author ≠ reviewer, I2
reviewer engine ≠ writing engine, I3 evidence on the change record, validated at head, I4 only the
synthesizer lands, I5 the tool of record holds the audit trail.

## Terms

### change

- **Definition:** one reviewable unit of work that builds one tracker item and
  lands as one commit on the default branch.
- **Invariants:** I4, I5.
- **Today:** a PR. One issue → one branch → one PR → one squash.

### change head

- **Definition:** the exact revision of a change that evidence, verdicts and
  the land refer to. A new commit makes a new head.
- **Invariants:** I3.
- **Today:** the PR head SHA. Markers carry it as the full 40-character `sha=`.

### verdict

- **Definition:** the reviewer's binding decision on a change head: pass or
  changes requested.
- **Invariants:** I1, I2, I3.
- **Today:** a formal `APPROVE` / `REQUEST_CHANGES` review carrying a
  `pass=verdict` marker. Roadmap PRs under the single-identity rule use a
  COMMENT review with a `pass=verdict` marker instead
  ([portable spec §6](specs/portable.md#6-decisions)).

### narrative post

- **Definition:** a non-binding bot post on a change: ack, fix note, merge-up,
  merge, escalation, steering ack.
- **Invariants:** I5.
- **Today:** a COMMENT review. Never a plain PR comment or inline comment.

### state tag

- **Definition:** a durable flag on a tracker item or change that records
  pipeline state without waking any role.
- **Invariants:** I5.
- **Today:** a `crew:*` label ([architecture: Labels](architecture.md#labels),
  [GitHub backend: Labels](backends/github.md#labels)).

### marker

- **Definition:** the machine-readable identity of a bot post: who wrote it,
  which pass, which change, which head, which round, which verdict.
- **Invariants:** I1, I3, I5.
- **Today:** a visible title `<RoleEmoji> <BotName> · <Pass>` for people plus
  a hidden `crew:v1` line that every reader parses
  ([protocol §4](protocol.md#4-marker-conventions)).

### CI signal

- **Definition:** the pass or fail result of the required automated checks at
  a change head.
- **Invariants:** I3.
- **Today:** the required GitHub Actions checks at head, surfaced to routines
  as `ci-passed` / `ci-failed`.

### wake event

- **Definition:** an external event that starts a role's turn.
- **Invariants:** none directly; it only decides who acts next.
- **Today:** a GitHub event (`issue-assigned`, `pr-opened`, ...) that the
  terminal environment's watcher polls for, or a Grok Bot routine trigger
  fires on (see [templates](../templates/README.md)).

### tracker item / milestone / board

- **Definition:** the unit of planned work, a group of items with a shared
  goal, and the view of their status.
- **Invariants:** I5.
- **Today:** a GitHub issue, Milestone and Project (v2)
  ([GitHub backend: Tracking](backends/github.md#tracking)).

### owner channel

- **Definition:** where the owner steers the crew and is asked for decisions.
- **Invariants:** I5 (a decision only counts once recorded on the tool of
  record).
- **Today:** chat with the coordinator, plus the matching GitHub post
  (`/crew` command or recorded steer).

### land

- **Definition:** integrating a change into the default branch, bound to the
  change head the gate checked.
- **Invariants:** I3, I4.
- **Today:** `gh pr merge --squash --match-head-commit <sha>` by the
  synthesizer ([protocol §7](protocol.md#7-merge-gate-synthesizer)).
- **Designed, not active:** an asynchronous land for a backend whose land is
  a queued request, polled until `landed` or `failed`
  ([interfaces](interfaces.md#asynchronous-land-design), #873).

### researcher

- **Definition:** a read-only role that answers one research request from
  the coordinator (question, scope, deliverable, source issue) with a written
  finding; it never builds, reviews or lands and holds no gate
  ([roles](roles.md#researcher-riley)).
- **Invariants:** none held; a design-doc PR it opens is a change like any
  other (I1–I4).
- **Today:** Riley, an optional identity; a signed issue comment, or a
  design-doc PR on request.

### runtime

- **Definition:** the older name for an [environment](#environment): where
  roles run and how they wake, start, stop and pass state. Docs written
  before the four axes, and the `[runtime]` profile table, keep the word.
- **Invariants:** must keep I1–I5.
- **Today:** the terminal environment (tmux, [runtimes/tmux.md](runtimes/tmux.md)),
  Grok Bot (routines, per-PR watches, parent turns and workers) and the
  single-session binding ([runtimes/session.md](runtimes/session.md)).

### backend

- **Definition:** the tool implementing one concern (change, review, tracker,
  state tags, comments and markers, CI, events, owner channel, knowledge),
  reached through a [connector](#connector).
- **Invariants:** must keep I1–I5, or the profile is unsupported.
- **Today:** GitHub for every core concern; Notion for `knowledge`
  ([backends/notion.md](backends/notion.md)).

### profile / pack

- **Definition:** a profile is the install-time selection of one value per
  axis: an environment, a connector per concern, harnesses per tier and the
  roles; a pack is an external bundle of connectors, harnesses, environment
  defaults, skills and a profile layer that a profile can pick from.
- **Invariants:** a profile that cannot keep I1–I5 is unsupported.
- **Today:** [../profiles/](../profiles/README.md) ships the default (Grok
  Bot + GitHub), tmux and session profiles; packs follow
  [packs.md](packs.md) and live outside this repo.

## Four axes

A deployment is the product of four independent axes. Changing the choice on
one axis edits no module on another
([REQ-06](specs/team.md#req-06-four-independent-axes)).

### role

- **Definition:** who an employee is: what it owns, its procedures, refusals
  and handoffs, written as a runtime-neutral package that names
  [generic actions](#generic-action) only.
- **Invariants:** the role split carries I1 and I4; review, validation and
  land stay core contracts, not role settings.
- **Today:** the engineering team's five roles in
  [../roles/](../roles/README.md) (`roles/eng/<role>.toml`), validated against
  the [role registry](roles-registry.md).

### connector

- **Definition:** the module that reaches one tool of record for one or more
  concerns and declares its capabilities. Only a connector names a tool's CLI
  or API.
- **Invariants:** I5; a connector missing a capability an invariant needs is
  rejected at profile validation.
- **Today:** [../connectors/](../connectors/README.md): GitHub (every core
  concern) and Notion (knowledge).

### environment

- **Definition:** where and how the team runs: it runs the team machinery
  (wake, spawn, teardown, delivery, liveness) and implements the generic
  actions with its own tools. Not a connector: it reaches tools of record
  only through connectors.
- **Invariants:** must keep I1–I5 and answer the
  [runtime contract](runtimes/README.md) C1–C9.
- **Today:** the terminal environment
  ([../environments/terminal/](../environments/terminal/README.md)), Grok
  Bot and the single-session binding.

### harness

- **Definition:** the coding agent program a role runs in, and its adapter:
  launch line, trust, hooks, skill loading, resume and idle detection.
- **Invariants:** I2 compares harness engines and models.
- **Today:** [../harnesses/](../harnesses/README.md): Claude Code, Codex,
  Cursor, Muse, OpenCode and Pi
  ([harness adapter contract](runtimes/harness-adapters.md)).

## Team and modules

### generic action

- **Definition:** an environment-neutral verb a role uses to coordinate
  (`notify`, `ack`, `report`, `heartbeat`, `check-ownership`, `land`, ...), with
  arguments, result, failure behaviour and durable record.
- **Invariants:** an action never grants authority; the protocol still says
  who may call it.
- **Today:** the [actions contract](../actions/README.md); the terminal
  environment implements part of it as `mdstack action` subcommands.

### seat / staff / team head

- **Definition:** a seat is an owner-facing role; staff are internal roles
  that never face the owner and escalate to their owning seat; a team head
  coordinates one team.
- **Invariants:** none held; owner decisions still count only once recorded
  (I5).
- **Today:** seat placeholders under `roles/seats/`; the coordinator is the
  engineering team head and holds the `cto` seat, and the other engineering
  roles are internal staff under it
  ([role classes](roles-registry.md#role-classes)).

### routine

- **Definition:** a role's recurring job: schedule, skill, generic actions,
  inputs, outputs, deadline and miss policy.
- **Invariants:** none held.
- **Today:** `routines/<routine>.toml` in a role package
  ([routines.md](routines.md)).

### core memory

- **Definition:** what every rendered brief carries about the owner and each
  role, curated in git; personal knowledge stays in the knowledge connector.
- **Invariants:** none held.
- **Today:** `memory/owner.md` and `memory/roles/<role>.md`
  ([memory.md](memory.md)).

### module

- **Definition:** a top-level directory holding one concern of the layout
  (roles, actions, connectors, environments, harnesses, core, cli, profiles,
  packs, dev, docs), bound by dependency rules D1–D9.
- **Invariants:** none directly; the rules keep the axes independent.
- **Today:** the [module table](README.md#modules) and
  [specs/team.md §4–§5](specs/team.md#4-target-module-layout).
