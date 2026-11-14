# Spec: team and modular design

> - **Status:** partly built
> - **Applies to:** this repo's layout, axes, roles, actions and modules
> - **Current rules:** the [protocol](../protocol.md) and its gate registry; each requirement's **Delivered by** issues
> - **Built:** M29–M33 (roles, connectors, environments, harnesses, core, cli and dev modules; the dependency lint; the actions CLI in part; the `mdstack` rename); M51 personnel delivery, #1180 rows A–D (PR #1805)
> - **Design only:** the `protocols/` and `install/` modules ([§4](#4-target-module-layout)) and the rest of the actions implementation
> - **M51 design delivered:** #1318's [team/project contract](#9-team-and-project-separation-1318-design-only) and approved T1–T4 breakdown (PR #1802); shared-pool routing remains design only
> - **M56 delivery:** T1–T4 admitted under [#1854](https://github.com/mw-ding/mdstack/issues/1854) as #1856–#1859, bookended by #1861 and #1860; rows, choices and order in [§9.8](#98-m56-delivery-1854); all four planned, not built
> - **Last checked:** 2026-11-13 at `aacfb7e` (M51 personnel delivery landed)

Status: v0.1 (2026-11-07). Owner: coordinator. Changes land through
`crew:spec` PRs (review pass only, merge on the owner's merge-ok). Tracking:
[#1180](https://github.com/mw-ding/eng-crew/issues/1180). Issue:
[#1216](https://github.com/mw-ding/eng-crew/issues/1216).

## 1. Goal

Turn mdstack from one engineering crew into a **team of portable
employees**: roles that keep their identity and procedures wherever they are
deployed, built from four independent axes, coordinated through generic
actions, and laid out as modules with enforced dependency rules. This repo
uses its own protocol, so this spec is the source of truth for its shape
([REQ-24](#req-24-self-hosted-specs)).

The requirements come from the owner's design discussion of 2026-11-07,
recorded on #1180:
[decoupling plan](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6702507670),
[session backends per host](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703445339),
[modular structure](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703508949),
[self-hosted specs](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703556457)
and the [roadmap](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703873341).

This spec builds on [portable.md](portable.md) and does not restate it.
[§6](#6-relation-to-portablemd) maps its P1–P8 onto the requirements here.
This spec changes no live gate or marker rule; the protocol and its gate
registry stay authoritative until a later change edits them.

## 2. Requirement format

Each requirement has a stable ID, `REQ-01` to `REQ-24`. An ID is never
reused or renumbered; a dropped requirement keeps its ID and is marked
dropped. Each one has five fields:

- **Applies when:** the situation or artifact the requirement governs.
- **Obligation:** what must hold, in MUST / MUST NOT terms.
- **Acceptance criteria:** numbered, checkable statements.
- **Verification:** the proof a change claiming the requirement needs:
  a lint, a test, a review check or a recorded owner decision.
- **Delivered by:** the roadmap issue(s) that implement it. Until those
  land, the requirement is a target, not a description of today.

The key words MUST, MUST NOT and MAY are used as in RFC 2119.

## 3. Requirements

### Roles as portable employees

#### REQ-01. Runtime-neutral role package

- **Applies when:** a role is defined or changed.
- **Obligation:** a role MUST be defined as a runtime-neutral package that
  says who the employee is, what it owns, its procedures, refusals and
  handoffs. The same package MUST work unchanged in every supported
  environment and harness, so the role keeps its identity wherever it runs.
- **Acceptance criteria:**
  1. Every role has one package directory under `roles/` ([§4](#4-target-module-layout)).
  2. Deploying a role in a different environment or harness changes no file
     in its package.
- **Verification:** the runtime-word lint of REQ-11; a render test that
  renders one role package into two environments.
- **Delivered by:** #1184, #1221, #1222.

#### REQ-02. One canonical definition per role

- **Applies when:** role policy is written or edited.
- **Obligation:** each piece of role policy MUST be authored once, in the
  role's canonical files. Runtime-specific operating text MUST live in an
  environment fragment, never in a copy of the role policy.
- **Acceptance criteria:**
  1. No role policy paragraph appears in more than one runtime template.
  2. Changing a role rule edits one file plus, at most, its tests.
- **Verification:** a duplication check over rendered briefs; reviewer
  check that a role-policy diff touches only canonical files.
- **Delivered by:** #1184, #1221.

#### REQ-03. Role metadata as data

- **Applies when:** a role's identity defaults, authority, lifecycle or
  skill index is declared.
- **Obligation:** these MUST be declared as data in the role's `role.toml`,
  not encoded in shared orchestration code. Review, validation and land
  stay explicit core contracts and MUST NOT become role-configurable.
- **Acceptance criteria:**
  1. Each role package has a `role.toml` with identity defaults, authority,
     lifecycle and skill index.
  2. Orchestration code reads lifecycle from the registry and has no
     per-role branches for it.
- **Verification:** registry schema validation in `check-repo`; a test that
  a registered role with an existing lifecycle spawns with no code edit.
- **Delivered by:** #1185.

#### REQ-04. Agent Skills format

- **Applies when:** a role skill is written.
- **Obligation:** role skills MUST use the Agent Skills format: one entry
  `SKILL.md` per role and one `skills/<skill>/SKILL.md` per procedure.
  A harness-specific delta MAY live under `variants/<harness>/` only where
  the harness needs it.
- **Acceptance criteria:**
  1. Every skill file has the format's front matter (name, description).
  2. Each `variants/<harness>/` file states why the shared skill cannot
     serve that harness.
- **Verification:** a format lint over `roles/**/SKILL.md`.
- **Delivered by:** #1184, #1221.

#### REQ-05. Adding a role is cheap

- **Applies when:** a new role is added whose lifecycle already exists.
- **Obligation:** adding it MUST take one role package plus its tests, with
  no edits to environments, harnesses or connectors.
- **Acceptance criteria:**
  1. A conformance test adds a fixture role and runs it in the terminal
     environment with no change outside `roles/` and tests.
- **Verification:** that conformance test in CI.
- **Delivered by:** #1185, #1224.

### Four axes

#### REQ-06. Four independent axes

- **Applies when:** a deployment is configured or a module is added.
- **Obligation:** a deployment MUST be the product of four independent
  axes: **roles** (who), **connectors** (the tools of record),
  **environments** (where and how the team runs) and **harnesses** (how an
  agent launches and loads). Changing the choice on one axis MUST NOT
  require editing a module on another.
- **Acceptance criteria:**
  1. The profile selects one value or set per axis.
  2. Swapping one harness or session backend in a profile changes no file
     under `roles/`, `connectors/` or another axis's module.
- **Verification:** the dependency lint of [§5](#5-dependency-rules); a
  profile matrix test.
- **Delivered by:** #1217, #1222, #1224.

#### REQ-07. Connectors

- **Applies when:** the team reads or writes a tool of record.
- **Obligation:** each tool concern MUST be reached through a connector
  that implements that concern's interface. Connectors are separate from
  environments: an environment never talks to a tool of record except
  through a connector.
- **Acceptance criteria:**
  1. GitHub access lives only in `connectors/github/`.
  2. The `knowledge` concern ([REQ-17](#req-17-knowledge-in-external-services))
     is a connector concern like the others.
- **Verification:** dependency lint rule D6 ([§5](#5-dependency-rules)).
- **Delivered by:** #1217, #1223.

#### REQ-08. Environments

- **Applies when:** a team is run somewhere: a terminal, a hosted bot
  platform, a single session.
- **Obligation:** an environment MUST implement the generic actions
  ([REQ-12](#req-12-actions-contract)) with its own tools and MUST run the
  team machinery (wake, spawn, teardown, delivery, liveness). Roles MUST NOT
  depend on which environment runs them.
- **Acceptance criteria:**
  1. Each environment has a mapping from every generic action it supports
     to its implementation, and declares the ones it lacks
     ([REQ-10](#req-10-declared-capabilities)).
- **Verification:** an environment conformance test per supported
  environment.
- **Delivered by:** #1183, #1222, #1232.

#### REQ-09. Harnesses

- **Applies when:** an agent is launched, briefed or resumed in a coding
  harness.
- **Obligation:** everything harness-specific (launch flags, trust, hooks,
  skill loading, resume) MUST live in one adapter per harness. Adding a
  harness MUST mean adding an adapter and its tests, with no edits to its
  consumers.
- **Acceptance criteria:**
  1. Shared plumbing has no branch on a harness name.
  2. Each adapter supplies the complete recipe its consumers need.
- **Verification:** adapter contract tests; a lint for harness names in
  shared code (D7).
- **Delivered by:** #1182.

#### REQ-10. Declared capabilities

- **Applies when:** an environment, connector or harness cannot do
  something a role or invariant needs.
- **Obligation:** it MUST declare the gap. Consumers MUST branch on declared
  capabilities, never on a module's name. A combination that cannot keep a
  [portable.md invariant](portable.md#3-invariants) is unsupported and MUST
  be rejected at profile validation, never silently weakened.
- **Acceptance criteria:**
  1. Each module ships a capability declaration.
  2. Profile validation rejects a combination with a missing required
     capability, and names it.
- **Verification:** validator tests with a fake module that lacks a
  capability.
- **Delivered by:** #1183, #1217, #1236.

### Generic actions

#### REQ-11. Role text uses generic actions only

- **Applies when:** role or protocol text needs an operation such as
  notifying a role, waiting for an event, claiming work, recording a
  heartbeat or reporting done.
- **Obligation:** it MUST name the generic action, never the runtime
  command, file, window or variable that implements it.
- **Acceptance criteria:**
  1. Canonical role and protocol files contain no runtime words (session
     backend names, inbox, window, runtime environment variables, CLI
     subcommands of an environment).
- **Verification:** a `check-repo` runtime-word lint over `roles/` and
  `protocols/` (D5).
- **Delivered by:** #1185, #1221.

#### REQ-12. Actions contract

- **Applies when:** a generic action is added, changed or implemented.
- **Obligation:** the vocabulary MUST be defined once, in `actions/`, with
  each action's arguments, semantics, result and failure behaviour. Roles,
  protocols and environments MUST use only actions the contract defines.
- **Acceptance criteria:**
  1. Every action has a stable name, arguments, result, failure behaviour
     and the invariant it protects.
  2. Each environment mapping covers the contract or declares the gaps.
- **Verification:** a contract lint that every action named in `roles/` or
  `protocols/` exists in `actions/`.
- **Delivered by:** #1218 (vocabulary from #1213).

#### REQ-13. CLI as the terminal implementation

- **Applies when:** the terminal environment implements generic actions.
- **Obligation:** it MUST expose them as CLI subcommands with stable names,
  arguments, exit codes and JSON output, as the actions contract specifies.
  A tool-server protocol MAY come later and is not required.
- **Acceptance criteria:**
  1. Each supported action has a subcommand whose exit codes and JSON match
     the contract.
  2. Today's terminal behaviour is preserved underneath.
- **Verification:** CLI contract tests asserting exit code, stdout JSON and
  stderr.
- **Delivered by:** #1232.

#### REQ-14. Durable record over ephemeral delivery

- **Applies when:** an action delivers a message or changes work state.
- **Obligation:** ephemeral delivery (a prompt typed into a session, a
  push notification) MUST NOT be the only record. The durable copy MUST
  stay in the environment's replayable queue and the audit trail in the
  tool of record ([portable.md invariant 5](portable.md#3-invariants)).
- **Acceptance criteria:**
  1. Every state-changing action names its durable record in the contract.
- **Verification:** contract review; a replay test after a lost delivery.
- **Delivered by:** #1218, #1232.

### Terminal fast lane

#### REQ-15. Terminal environment is the owned fast lane

- **Applies when:** the team runs locally in terminal sessions.
- **Obligation:** the terminal environment is this project's own,
  lowest-latency environment and its reference implementation of the
  generic actions. Speed MUST come from orchestration (waking without
  model turns, parallel sessions, local checks), never from skipping a
  gate the protocol requires.
- **Acceptance criteria:**
  1. Every protocol gate holds in the terminal environment.
  2. Other environments are tested against the same actions contract.
- **Verification:** the existing campaign and regression suites at each
  release.
- **Delivered by:** #1222, #1232.

#### REQ-16. Session backend chosen per host

- **Applies when:** the terminal environment starts sessions on a host.
- **Obligation:** the session backend MUST be chosen per host: an enhanced
  backend where it is installed and healthy, and a universally available
  default (tmux) as the fallback. Installing a backend MUST NOT be required.
  Roles MUST NOT change with the backend.
- **Acceptance criteria:**
  1. The profile or auto-detection picks a backend per host and falls back
     to the default when the preferred one is missing or unhealthy.
- **Verification:** backend selection tests with fake backends.
- **Delivered by:** #1183.

### Personal knowledge

#### REQ-17. Knowledge in external services

- **Applies when:** a role needs the owner's personal knowledge or memory.
- **Obligation:** personal knowledge MUST live in an external service and be
  reached through a `knowledge` connector concern. It MUST NOT be committed
  to any repository the team works on, this one included.
- **Acceptance criteria:**
  1. The concern table in portable.md lists `knowledge`.
  2. No personal knowledge content is tracked in git.
- **Verification:** the secret and denylist scans; reviewer check.
- **Delivered by:** #1217, #1229.

#### REQ-18. Read and propose-edit

- **Applies when:** a role reads or changes knowledge.
- **Obligation:** the connector MUST offer `knowledge-read` and
  `knowledge-propose-edit`. A role MUST NOT change knowledge except as a
  proposal the owner or the backend's review step accepts. The first
  backend is a hosted notes service (Notion).
- **Acceptance criteria:**
  1. Both actions are in the actions contract.
  2. Backend tests use fakes with no network.
- **Verification:** connector tests with fakes.
- **Delivered by:** #1229.

#### REQ-19. Private source pointers

- **Applies when:** a deployment configures where knowledge lives.
- **Obligation:** source pointers and credentials MUST come only from
  private or local config, never from committed files. Each role MUST
  declare the knowledge sources it needs.
- **Acceptance criteria:**
  1. Committed config holds only source names, never locations or
     credentials.
  2. A role that uses knowledge declares its sources in `role.toml`.
- **Verification:** the secret scan; a config test that rejects a committed
  pointer; sensitive-class review.
- **Delivered by:** #1229.

### Seats, staff and team heads

#### REQ-20. Role classes

- **Applies when:** a role is registered.
- **Obligation:** each role MUST declare its class: an **owner-facing seat**
  (directly addressable by the owner) or **internal staff** (never faces the
  owner). Internal staff MUST declare their owning seat and escalation path.
- **Acceptance criteria:**
  1. `role.toml` carries class, owning seat and escalation path.
  2. Registry validation rejects internal staff without an owning seat.
- **Verification:** registry schema tests.
- **Delivered by:** #1227.

#### REQ-21. Only seats face the owner

- **Applies when:** a role needs an owner decision or reports to the owner.
- **Obligation:** only owner-facing seats MUST deliver owner asks and
  reports. Internal staff MUST escalate to their owning seat, which decides
  or carries the ask. Technical matters go to the technical seat (CTO).
- **Acceptance criteria:**
  1. The protocol states the rule.
  2. No internal staff brief tells the role to ask the owner directly.
- **Verification:** a brief lint for owner-ask wording in internal roles;
  reviewer check.
- **Delivered by:** #1227, #781.

#### REQ-22. Team heads and seat placeholders

- **Applies when:** a team of roles is defined.
- **Obligation:** each team MUST have one head that coordinates it, as the
  coordinator does today. The engineering team's head maps to the technical
  seat. Seat content MAY be authored elsewhere; this repo MUST provide seat
  packages in the role-package shape, with no personal data.
- **Acceptance criteria:**
  1. Each team declares its head in metadata.
  2. Seat placeholder packages and a seat template exist.
- **Verification:** registry tests; denylist and personal-data review.
- **Delivered by:** #1227, #1228, #781.

### Modules and self-hosting

#### REQ-23. Modular layout with enforced dependency rules

- **Applies when:** a file is added or moved, or a module references
  another.
- **Obligation:** the repo MUST follow the layout in [§4](#4-target-module-layout)
  and the rules in [§5](#5-dependency-rules), enforced by a lint. The
  reorganisation MUST land as move-only changes kept apart from behaviour
  changes, with compatibility shims at old paths for one major version.
- **Acceptance criteria:**
  1. The dependency lint passes on `main` and fails a fixture that breaks
     each rule.
  2. Old entry points keep working for one major version.
- **Verification:** the lint's tests; the release smoke test of an
  extracted bundle.
- **Delivered by:** #1222, #1224, #1226.

#### REQ-24. Self-hosted specs

- **Applies when:** a change alters how this project is shaped (layout,
  axes, roles, actions, gates).
- **Obligation:** it MUST be specified in `docs/specs/` first and land
  through a `crew:spec` PR on the owner's merge-ok, as for any project the
  crew runs. `docs/specs/` is this repo's source of truth.
- **Acceptance criteria:**
  1. Each shape-changing roadmap issue cites the spec requirement it
     implements.
- **Verification:** reviewer check against the cited `REQ-` ID.
- **Delivered by:** this spec; #1219 and #1225 extend the rule to every
  project.

## 4. Target module layout

The layout is the target of the M31 move-only reorganisation (#1222). Each
row names today's sources.

| Module | Holds | Today |
|---|---|---|
| `roles/<team>/<role>/` | Portable role packages: `role.toml`, entry `SKILL.md`, `skills/<skill>/SKILL.md`, `routines/<routine>.toml` (recurring jobs, [routines](../routines.md), #1247), rare `variants/<harness>/` | `roles/eng.toml`, `templates/runtimes/*` |
| `roles/seats/<seat>/` | Owner-facing seat packages (placeholders) | none |
| `protocols/eng/` | Stages, markers, rounds, gates, flavors, evidence | `docs/protocol.md`, `docs/flavors.md`, `docs/verification.md`, `docs/express-lane.md` |
| `protocols/conventions/` | Signatures, owner communication, decision log, triage | `docs/triage.md`, protocol sections |
| `actions/` | Generic action vocabulary and CLI contract | none (#1213 research) |
| `connectors/<tool>/` | Tool concerns: change, review, tracker, labels, markers, CI, events, knowledge | `packs/github/`, `docs/backends/github.md`, `templates/backends/` |
| `environments/terminal/` | Watcher, router, leads, scheduler, spawn and kill, inbox bus; `sessions/<backend>/`; `remote/` | `scripts/crew`, `scripts/crew.d/*`, session backend scripts, `docs/runtimes/multi-device.md` |
| `environments/<platform>/` | Hosted-platform and single-session bindings | `templates/runtimes/grok-bot/`, `docs/runtimes/session.md` |
| `harnesses/<harness>/` | Launch, trust, hooks and skill loading per harness | `scripts/crew.d/_shared.py`, `docs/runtimes/harness-adapters.md` |
| `core/` | Shared libraries only: config schema and resolver, renderer, state store | `scripts/crew-config.py`, `scripts/crew-render.py` |
| `cli/` | The `mdstack` entry point, dispatching actions to the active environment | `scripts/crew` |
| `profiles/` | Install-time profiles and presets | `profiles/` |
| `install/` | Bootstrap, upgrade, release bundle | install and release scripts |
| `dev/` | Repo QA: check-repo, markdown, changelog, campaign harness, metrics, tests and fixtures | `scripts/check-*.py`, `scripts/test-*.py` |
| `docs/` | Narrative only: architecture, concepts, specs, runbooks, lessons, findings, pointing into the modules | `docs/` |

## 5. Dependency rules

A lint in `dev/` enforces these (#1224). "References" means imports, path
references and, for text modules, naming the other module's concepts.

| ID | Rule |
|---|---|
| D1 | `roles/` references only `protocols/` and `actions/`. |
| D2 | `protocols/` references only `actions/`. |
| D3 | `connectors/`, `environments/` and `harnesses/` implement `actions/` and may use `core/`; none of them references another of the three except through `actions/` or a declared capability. |
| D4 | `core/` depends on no module above it. |
| D5 | Only `environments/terminal/` names session backends, inboxes, windows or the terminal's environment variables. |
| D6 | Only `connectors/` names a tool of record's CLI or API. |
| D7 | Only `harnesses/` names harness launch flags, hooks or trust settings. |
| D8 | `cli/` dispatches to environments through `actions/`; it holds no role policy. |
| D9 | `docs/` may reference any module; no module depends on `docs/`. |

## 6. Relation to portable.md

This spec cites [portable.md §2](portable.md#2-requirements) and does not
restate it. #1217 updates portable.md to v0.4 with the harness axis, the
`knowledge` concern and the extension mechanism.

| portable.md | Used here by |
|---|---|
| P1 runtime abstraction | REQ-01, REQ-08: environments are the runtime bindings |
| P2 tool abstraction per concern | REQ-07, REQ-17: connectors implement concerns; `knowledge` joins them |
| P3 minimum backend contract | REQ-10: capability declarations extend to environments and harnesses |
| P4 install-time profile | REQ-06: the profile selects one value per axis |
| P5 config layers | REQ-19: knowledge pointers sit only in private or local layers |
| P6 no org-internal names | REQ-22 and this spec's own wording; packs supply org specifics |
| P7 default profile stays complete | REQ-06: the default profile picks a complete value on every axis |
| P8 keeps working after every merge | REQ-23: move-only and behaviour changes never share a PR |

## 7. Open questions

| Question | Settled in |
|---|---|
| Q1. Are team heads themselves seats, or internal staff with a seat above them? | #1227: either; a head facing the owner is its team's seat (the eng head holds `cto`), a head under another seat is internal staff ([roles-registry.md](../roles-registry.md#role-classes)) |
| Q2. Which actions are required for every environment, and which are optional capabilities? | #1218 |
| Q3. Does `knowledge-propose-edit` land through the owner's review in the service, or through a team proposal record? | #1229 |
| Q4. Does the runtime-word lint (D5) run before the reorganisation, against today's paths? | #1185 |
| Q5. How long do the compatibility shims at old paths stay: one major version, or until packs confirm? | #1226 |
| Q6. Do role classes and seats belong in `docs/specs/` of every project, or only here? | #1219 |
| Q7. What does a team profile own versus a project, how do profiles and roles compose, and how do admission, claims and land stay inside one repo? | #1318 (PR #1802): [§9](#9-team-and-project-separation-1318-design-only), design delivered; T1–T4 planned under #1854 ([§9.8](#98-m56-delivery-1854)); applied M51 choices in [portable.md §5](portable.md#m51-personnel-boundary-and-team-routing-design) |
| Q8. How does a host import a personnel bundle and pinned roles without the terminal machinery or a change to role authority? | #1180 rows A–D built (PR #1805), on [§9.6](#96-pinned-personnel-import-and-host-binding)'s import and binding contract; fake-host proof, no live adoption claim |

## 8. Out of scope

- Org-specific connectors, environments or seat content (packs; P6).
- Adapters for further hosted platforms, and a session backend driven by an
  agent-state API (dropped for now by the owner, 2026-11-07).
- The CLI and repo rename (M33), beyond keeping the layout rename-ready.
- Any change to a live merge gate or marker rule.

## 9. Team and project separation (#1318, design only)

**Status: routing design delivered (PR #1802); personnel content built
(PR #1805).** Shared admission, pools and routing remain design only. The
[applied decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846260224)
adopts [readiness §3–§4](https://github.com/mw-ding/mdstack/issues/1779#issuecomment-6844208107).
It replaces #1318's draft `[[projects]]` proposal with the existing
`[team]` / `[repos.<name>]` schema. The implementation breakdown is §9.7;
its units need separate plan records before admission.

M51 status, synced by #1790; the landed items are closed in the tracker.
The milestone closes after its status-sync slice (#1790, PR #1806) lands.

| ID | Issue | Scope | Status |
|---|---|---|---|
| S0 | #1789 | Opening spec (PR #1797) | done |
| B1 | #1318 | Routing design and approved T1–T4 breakdown (PR #1802) | done |
| B2 | #1180 | Personnel delivery, rows A–D (PR #1805) | done |

Lessons: pinned content and a thin host binding preserve role authority
without exporting terminal execution. Fake-host import proves the content
boundary; shared-pool and repo-isolation scenarios in §9.7 remain future
tests, and live host adoption remains outside M51.

### 9.1 Ownership and composition

A team is roles and seats, identities, engines, capacity and policy serving
several projects. A project is a repository context, never a second team.
The mdstack source repository is one project the team can work on.

| Team owns | Project owns |
|---|---|
| Role selection, seats, identity and engine defaults | Full repo identity, checkout and default branch |
| Host, environment, harness and connector defaults | Tracker labels and milestone order |
| Shared pool caps, presence, load target and reservations | Spec/doc homes and ownership/control record |
| Base flavor and policy floors | Rigor tightening and recorded landing permission |

Composition stays closed: `core < default < pack/org < team < repo`.
Pack defaults and an explicit org layer retain their existing order and
floor validation; the notation does not introduce another layer. Each
resolved value records its originating layer and file, including the repo
section. Roles and adapters initially inherit from the team. A repo cannot
replace identities, role authority, engines, host placement or shared caps.
Unknown keys fail before rendering or dispatch.

The [team-files reference](../configuration/team-files.md#schema-and-example)
is the schema. Its existing keys continue to resolve, and T1 (#1856) adds
the keys below with the closed shapes in §9.8:

| Repo key | Target / validation |
|---|---|
| `control_item` | `repo.control_item`; tracker-valid control record in this repo |
| `flavor` | Closed flavor declaration; resolve item/path rigor against the team floor |
| `labels` | Closed mapping of existing state-tag names to nonempty tracker label names |
| `milestones` | Ordered, distinct tracker milestone IDs belonging to this repo |
| `doc_home` | Project-relative documentation directory, no escape from checkout |

Existing `spec` selects spec paths. The checkout locates both docs and code;
no knowledge content or credentials enter these keys. T1 must define the
exact nested types through the existing backend ID/capability declarations
and reject unrecognized fields. It must not accept these sketches as an
unvalidated free-form table.

Rigor is the knob-wise strictest of core/pack floors, team base, project,
item and path records, using [flavor resolution](../flavors.md#resolution).
Project settings may tighten, never relax that floor: fewer rounds and
stronger review, validation, evidence or permission requirements win under
the existing comparison. An attempted relaxation is refused with the key
and source, not silently applied. Landing grants retain their recorded
scope; a team default cannot grant authority over every project.

### 9.2 Two projects, one team

This example uses only shipped keys; future routing fields are separate.
`<config-home>` and `<state-dir>` are operator-selected roots.

```toml
[team]
name = "engineering"
pack = "github"
accounts = { all = "<bot-login>", reviewer = "<reviewer-login>" }
runtime = { name = "tmux", options = { builders = 5, reviewers = 5 } }
paths = { state_dir = "<state-dir>", worktree_root = "<worktree-root>" }
flavor = { name = "standard" }

[repos.a]
repo = "example/alpha"
checkout = "<checkout-a>"
default_branch = "main"

[repos.b]
repo = "example/beta"
checkout = "<checkout-b>"
default_branch = "trunk"
```

References are `<config-home>/teams/engineering.toml#a` and `#b` on that
same file. Resolve each reference to its full repo identity; aliases, file
symlinks or an omitted selector for a one-repo file must resolve to the same
canonical project identity. Duplicate entries for one repo in a team are
refused. There is no first-repo fallback when several repos are configured.

Existing one-repo `config.toml` resolution is preserved. **Migration is not
needed: 7.0+ is fresh**, with no compatibility conversion in this design.
An operator changing an already-running team name/state location still
follows the existing stop/move instructions; this design does not perform
that rollout or move any live state.

### 9.3 Qualified work and state

Every handoff and result carries a work envelope with team identity,
project reference, full repo identity, item/change IDs as applicable, full
head SHA when a change exists, pass and round. A new build has no change/head
yet; use explicit absence, never an invented SHA. The receiver resolves the
reference and compares the repo against the independently fetched item's or
change's repository before acting. Missing, unknown, conflicting or
unreadable context is a refusal before claim, spawn, post or land.

The durable envelope supplies repo context outside existing marker lines.
Markers keep today's field sets, signatures, head and round meaning; a
marker parsed from repo A is never a record for repo B. Backend reads and
writes name the selected repo explicitly. No new marker field ships here.

Assume both projects have issue `42`, change `7`, pass `review`, round `1`
and the identical full head `1111111111111111111111111111111111111111`.
Equality of those values proves no cross-repo identity:

| Artifact | A | B |
|---|---|---|
| Work identity | `(engineering, example/alpha, 42, 7, head, review, 1)` | `(engineering, example/beta, 42, 7, head, review, 1)` |
| Repo state | `<state-dir>/engineering/example__alpha/` | `<state-dir>/engineering/example__beta/` |
| Claim and inbox | A state, A envelope | B state, B envelope |
| Reservation | Team ledger, A work identity | Team ledger, B work identity |
| Worktree | `<worktree-root>/example__alpha/<run-id>/` | `<worktree-root>/example__beta/<run-id>/` |
| Verdict/evidence/grant read | `example/alpha` change 7 and its control records | `example/beta` change 7 and its control records |

Team-global run IDs and physical session/window allocation prevent two
issue-42 workers taking the same slot/name. Run records bind that allocation
to the repo envelope. Claims, inboxes, evidence references, rounds, holds,
trains and completion status stay under repo state; reservation ownership
and aggregate capacity stay under team state. A `done` for A releases only
A's reservation and run. Recovery/reclaim compares the run ID, repo context
and live process identity, never a bare `#42` or window name.

### 9.4 Admission and shared pools

One coordinator and one set of pool leads serve the team session. One team
scheduler lock protects the target, aggregate busy count and reservation
ledger across all projects. A reservation counts once, then transfers to
its matching run under the existing spawn/release/expiry rules. Team pool
caps and presence bounds apply to totals, not once per repo.

Collect demand from each repo, then apply its ownership, holds, escalation,
head and dependency checks before ranking. An unreadable project's state
blocks that project's demand; it cannot supply eligibility. Unknown shared
busy counts or ledger state block team admission rather than undercounting
capacity. A held A issue leaves B eligible. Existing runs still count
against the shared budget even if their project stops admitting work.

Keep [scheduling priority](../scheduling.md#priority): finishing work before
new builds, caller-only reservations, cross-pool holds, pool floors and no
killing busy workers. Floors are per team pool, not per project. Milestone
order and dependency graphs are local to each repo; compare within class by
local milestone ordinal, critical-path count, age, then canonical repo and
work identity for a deterministic tie. Class 7 is each repo's earliest
eligible active milestone; class 8 runs only when no class 7 work in the
team is eligible. Cross-repo dependency declarations are not introduced.
A red default branch blocks that repo's landing, and its repair ranks
class 1 in team demand; it does not stop another repo's land.

The shared lead grants only its own pool and dispatches the full envelope
into repo state. Watchers route events to the correct lead without creating
another pool. Observability names the repo on every decision, reservation,
refusal and completion. A shared queue cannot turn A's fix into B's build.
Lands remain outside admission budgeting.

### 9.5 Landing authority and refusals

A shared synthesizer executes separately authorized repo work. Before any
mutation it resolves the selected project, reads that repo's ownership and
control records, head, verdict, evidence, CI, holds and permission, and
checks every [stage 7 gate](../protocol.md#7-merge-gate-synthesizer). Any
mismatch or unreadable required record blocks. Same change number or head
SHA never makes a verdict, merge-ok, grant or train result portable across
repos. Existing verdict portability applies only inside the selected repo.

Serialization and land locks are per canonical repo: one land at a time
inside A, one inside B. A shared executor must not overlap two lands for A;
separate repos need no shared permission or land lock. Every train/stack
has one repo, that repo's base and qualified members. Validate the complete
membership before branch creation, push, CI dispatch or merge. A mixed-repo
train or stack is refused with **zero mutation**, including cleanup writes
or partial execution. Each result routes back to its original project.

These rules are the future isolation contract, not an edit to the gate
registry's satisfied-by, actor or fail-open columns. T4 must preserve those
columns; any proposed change to them needs the gate-contract path. Import,
shared capacity and operator silence never waive CI, ownership, sensitive
permission, holds or reviewer independence.

### 9.6 Pinned personnel import and host binding

The #1180 [personnel delivery](../personnel.md) documents the actual path
boundary and implements the producer entry at `scripts/personnel-bundle.py`.

For #1180, compose in the full producer checkout and export content only.
The host selects stable `domain/role` IDs at a pinned source version/commit.
A manifest records source pin, selected IDs, binding ID/version, file hashes
and setting provenance. A missing role or two sources defining the same ID
is refused; no last-writer replacement or unpinned lookup is permitted.
External role discovery and generic inheritance remain future work.

The exported content includes descriptors and seats, canonical skills and
policies, required spec/protocol/marker/action contracts, and composed role
briefs. The consumer does not require the terminal CLI, resolver, renderer,
scheduler, leads, trains, runner/reap, wake adapters or sweepers. The producer
may require those dependencies; labeling all of `core/` portable is wrong.
Inert terminal descriptor fields are binding metadata, not an executable
runtime or authority. #1180 publishes the actual file/path boundary map.

A thin host binding supplies wake/delivery, durable queues, run identity,
claims/status, generic action implementations, connector access and
head-bound land enforcement. It declares required capabilities and gaps
under REQ-10. A missing binding, unresolved policy reference, unbound required
action or unsupported invariant produces no usable install; verify before
publishing output. Identical inputs produce an idempotent install.

Allowed customization is presentation through profile identities, engine
selection through existing routing/independence checks, and additive skills
with provenance. Neither imported descriptors, bindings nor prose overlays
may replace role class/escalation, marker/pass semantics, reviewer
independence or synthesizer-only land. Validate data and review composed
prose; schema validation alone cannot prove authority preservation.

Grok Bot and a generic fake host consume this content. Import starts no
routine and grants no permission. Existing hosted binding gaps and accepted
exceptions remain declared; fake-host import is not proof of live adoption.
Issue #1180 proves every selected brief/procedure loads with the terminal tree
absent and all required policy/action references bound.

### 9.7 Derived work and acceptance matrix

The applied M51 decision approves the design direction and names T1–T4;
it did not admit them. M56 (#1854) files and orders them; their issues,
status and delivery references are in [§9.8](#98-m56-delivery-1854). Each is one
work-unit PR in logical commits; sizes below exclude tests.

| Unit | Scope and minimum proof | Paths | Depends on / estimate |
|---|---|---|---|
| T1 | Closed project keys, canonical context, qualified handoff/result routing; one-repo regression and absent/unknown/mismatch refusals | `core/crew-config.py`, terminal `send.py`, `poll.py`, `route.py`; config/routing tests | Approved #1318; 250–450 lines |
| T2 | One admission lock/budget/ledger; qualified matching, A held/B eligible, finish-first ranking and team pool floors | Terminal `schedule.py`, `lead.py`; schedule tests and scheduling reference | T1; 300–550 lines |
| T3 | One set of leads; unique windows/runs/worktrees; repo-state dispatch and correct recovery/reclaim | Terminal `up.py`, `lead.py`, `spawn.py`, `route.py`, `watch.py`, `_shared.py`; pool templates and lifecycle tests | T1, integrated with T2; 400–700 lines |
| T4 | Repo-bound gates, locks and result routing; wrong verdict/grant and mixed train/stack rejected before mutation | Terminal `land.py`, `land-lock.py`, `train.py`, `_land_stack.py`; synthesizer templates, protocol, land-lock/stack tests | T1; integration after T3; 250–450 lines |

The routing scenarios below specify future tests, **not observed runtime
results**. Personnel import/refusal scenarios were exercised by #1180
(PR #1805); that proof does not establish shared-pool routing or live host
adoption.

| Scenario | Required result / future proof owner |
|---|---|
| A and B have the same issue, change, head, pass and round | Distinct envelopes, claims, reservations, worktrees and verdict/grant reads; T1–T4 |
| A held, B eligible with a free shared slot | A gets no reservation; B can start, and aggregate caps still hold; T2 |
| No repo, unknown selector, or reference names A but envelope names B | Refusal before claim/spawn/post/land; T1, T3, T4 |
| A verdict or grant supplied for B at the identical SHA | No land request for B; T4 |
| Train or stack contains A and B | No branch, push, CI, merge or cleanup mutation; T4 |
| Team caps reached; another repo queues work | No extra per-repo budget; existing team pool floor rules only; T2 |
| A completes/restarts while B has matching numeric IDs | Only A's run/reservation changes; B's state is untouched; T3 |
| One-repo profile and existing marker | Same resolution and marker semantics; T1–T4 regressions |
| Pinned role missing/colliding, authority override or incomplete binding | No usable personnel install; #1180 |
| Valid pinned content loaded by fake host without terminal tree | Every selected brief/procedure and required action resolves, rerun idempotent; #1180 |

### 9.8 M56 delivery (#1854)

M56 implements §9.1–§9.5 and §9.7 for one team serving several repos.
§9.1–§9.7 stay the contract; this section records only rows, applied
choices, order and proof boundaries. Member acceptance criteria live in
their issues, from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1854#issuecomment-6866509757)
§3–§6, under the
[M56 plan record](https://github.com/mw-ding/mdstack/issues/1854#issuecomment-6866347368).
S0 is recorded `built` for this opening slice, effective on merge; T1 is
recorded `built` by #1856's change, effective on its merge; T3 by #1858's,
effective on its merge; T4 by #1859's, effective on its merge. No
member dispatches before #1861 merges. One issue → one PR in logical
commits; the four units are not split further to meet a line budget.
Estimates exclude tests and are planning ranges, not limits.

| ID | Issue | Scope | Size | Depends on / integration prerequisite | Status |
|---|---|---|---|---|---|
| S0 | #1861 | Contract choices, issue references, refusal and proof matrix | 80–140 docs | M56 plan record; D1–D5 | built |
| T1 | #1856 | Closed project context and qualified durable routing (§9.1–§9.3) | 250–450 | S0 | built |
| T2 | #1857 | Shared admission lock, target and ledger (§9.4) | 300–550 | T1; M55 #1836 shared waits | planned |
| T3 | #1858 | Shared leads and worker lifecycle (§9.3–§9.4) | 400–700 | T1; integrated T2; M55 #1836 and #1830 | built |
| T4 | #1859 | Repo-bound land, locks and train/stack refusals (§9.5) | 250–450 | T1; integrated T3; M55 #1835 and #1836 | built |
| S1 | #1860 | Delivery references, headers, tracker closure, lessons | 40–90 docs | T1–T4 and M56 acceptance evidence | planned |

Each later land updates its row through the existing delivery references;
S1 performs the final sync. The overall spec stays **partly built**: the
`protocols/` and `install/` modules and the rest of the actions work
(§4) remain design only after M56.

Execution: standard flavor, tmux lane, Claude Code builders first
([c6865476254](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6865476254)).
T1–T4 use deep tier, passed explicitly at dispatch until #1830 ships; both
bookends use default tier. Reviewer selection excludes the builder engine.

#### Applied choices D1–D5

[Applied by the coordinator](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6866530837).
These M56 choices are unrelated to the §5 dependency rules of the same
letters.

- **D1 (context):** durable closed context whose identity is
  `(resolved team, canonical repo)`. `FILE#selector` is a locator, not the
  identity. A single-repo config derives a deterministic singleton team.
- **D2 (admission):** one team-root `schedule/` lock, target and ledger of
  qualified identities. Repo eligibility stays separate; unknown aggregate
  state refuses.
- **D3 (leads and runs):** one `(team, pool)` lead with atomic team
  allocation, immutable execution IDs plus live process identity, repo-state
  worker records and `<worktree-root>/<repo-slug>/<run-id>/`.
- **D4 (land):** repo-bound reads and references, per-repo land locks, and
  train/intent membership qualified before any write. Markers and the
  §7 registry's satisfied-by, actor and fail-open columns are unchanged.
- **D5 (surface):** additive team interfaces; one-repo outputs and gate
  satisfaction unchanged. Milestone version forecast: minor.

The five closed project keys (T1), each rejecting unknown nested fields:

| Key | Closed shape |
|---|---|
| `control_item` | Existing `repo.control_item` ID types and tracker-pattern checks, plus same-repo lookup before use |
| `flavor` | Table with only `name`: a known non-express preset or team-defined flavor, compared against team/core/pack floors; no repo engine, identity, placement or cap fields |
| `labels` | Closed map from existing canonical state-tag names to nonempty tracker labels; identity when omitted; no colliding destinations; applied to reads and writes |
| `milestones` | Ordered, distinct native tracker milestone IDs in the binding's existing ID type, same-repo checked; omitted means existing discovery and order |
| `doc_home` | Nonempty project-relative directory, defaulting to the existing docs home; absolute paths and normalized or symlink escapes refused |

#### Envelope and state split

The durable envelope carries team identity, project reference, canonical
repo identity, item ID, change ID and full head SHA when a change exists,
pass and round. A new build's envelope has no `change` or `head`: they are
explicitly absent, never a guessed SHA. The checkout and base revision a
build starts from are run-record data, not a published change head, and a
run record's existing checkout-valued `repo` is not the canonical repo.
Local completion binds to its run record; a bare `done:` line supplies no
repo authority. `crew:v1` markers, signatures and status-line meanings are
unchanged.

| Team root | Repo state |
|---|---|
| `schedule/` lock, target and reservation ledger | Claims, worker inbox and status, evidence references, rounds |
| `(team, pool)` lead inbox, status and handoff record | Holds, escalation, trains, stack intents and completion |
| Run-ID and physical slot allocation | Land lock and land serialization |

#### Zero-mutation refusals

Each case refuses before the named action and changes no state, including
cleanup writes.

| Case | Refused before | Proof owner |
|---|---|---|
| Multi-repo file without selector, unknown selector or duplicate canonical repo | Render or dispatch | T1 |
| Unknown nested key, project rigor relaxation or `doc_home` escape | Render or dispatch | T1 |
| Envelope missing, unreadable or naming a repo other than the item's or change's | Claim, spawn, post or land | T1, T3, T4 |
| Unreadable aggregate workers or ledger | Any team admission (unreadable A state blocks only A) | T2 |
| Replay or old completion for A matching B's numeric IDs | Kill, reap or settle of B | T3 |
| A's verdict, merge-ok, grant or train result offered for B at an identical SHA | B's land request | T4 |
| Train, stack or persisted intent with a foreign member or base | Allocation, branch, push, CI, merge, resume or cleanup | T4 |

#### Integration order with M55

S0 merges first; T1 develops beside M55. After T1, T2 and T3 may develop
together, but T2 integrates first. #1836 lands before T2/T3 wait
acceptance, #1830 before T3 tier acceptance, and #1835 after #1836 and
before T4 permission and resume acceptance. T4 may prepare isolated gate
and membership work after T1, then integrates after T3. S1 follows all four.
File overlap alone does not hold dispatch.

#### Environment, prerequisites and classification

**Target environment: N/A.** Implementation and isolated conformance use
existing terminal and fake fixtures, disposable repos and a fake backend;
no target-device or host-launch claim. **Owner prerequisites: none** for
this bounded proof. Live team adoption and state moves remain a later
operator step (§9.2).

Permission and sensitivity are separate from owner-shell prerequisites.
Merge permission is the owner's merge-ok for all M55–M57 PRs
([c6865236268](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6865236268)),
recorded per PR at head. Sensitivity is classified per diff at triage and
on every push; T1–T4's authority, capacity, reclaim and land content are
candidates, not recorded matches. A `crew:sensitive` match needs the
owner's per-change reason and is not covered by the bulk merge-ok.

The §9.7 routing scenarios remain future tests. This slice records no
runtime result, and isolated proof will not assert live adoption.
