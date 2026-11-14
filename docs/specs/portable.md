# Spec: portable mdstack (pluggable runtimes and tools)

Status: v0.4 (2026-11-07). Owner: coordinator. Changes land through
`crew:spec` PRs (review pass only, merge on the owner's merge-ok). Umbrella:
[#110](https://github.com/mw-ding/eng-crew/issues/110).

v0.4 ([#1217](https://github.com/mw-ding/eng-crew/issues/1217)) adds the
2026-11-07 design: four axes (roles, connectors, environments, harnesses),
the `knowledge` concern, generic actions
([P11](#2-requirements)) and the generic
[extension mechanism](#9-extension-mechanism). It also marks the sections
the M29–M34 plan supersedes. The new team spec
([#1216](https://github.com/mw-ding/eng-crew/issues/1216)) cites P1–P8 and
does not restate them. v0.4 changes no live gate or marker rule: the
[protocol](../protocol.md) still owns those.

## 1. Goal

Make mdstack **installable on more than one agent runtime** and **workable
against more than one toolset**, chosen at install time. The protocol core
becomes runtime- and tool-agnostic; runtimes and tools become configurable
bindings. The first new runtime is a local tmux crew: one coordinator session
(Claude Code or Codex) that creates, briefs, monitors and tears down one
session per role, which the owner can attach to. The Grok Bot runtime with
GitHub stays a supported default profile with no behaviour change, and every
merge gate in [protocol §7](../protocol.md#7-merge-gate-synthesizer) still
holds. Every roadmap issue in milestones M13 and M14 links this spec.

## 2. Requirements

- **P1. Runtime abstraction.** The core protocol does not assume a runtime.
  Each runtime binding answers the same questions: how a role is woken, how a
  role session or worker is created and torn down, how state passes between
  roles, and how stuck or crashed work is detected. Runtime-specific
  mechanics (per-PR watches, routine limits, the stuck-PR sweeper) move out of
  the core into the Grok Bot binding. Bindings: Grok Bot (today), CLI / tmux
  (M14), other runtimes later. (#110) From v0.4, a runtime is called an
  **environment**: it runs roles and implements the
  [generic actions](#2-requirements) (P11) with its own tools (tmux, herdr,
  Grok Bot). An environment is never a connector, and a connector never
  runs roles.
- **P2. Tool abstraction per concern.** The protocol speaks in abstract terms
  (change, verdict, state tag, marker, CI signal) defined in a glossary. Each
  concern is a named interface with swappable backends; GitHub is the first
  backend for all of them. (#110) A backend of one or more concerns is a
  **connector**. It reaches an external tool, such as the forge or a
  knowledge service.

  **Four axes (v0.4).** A profile varies along four independent axes:

  | Axis | Answers | Contract |
  |---|---|---|
  | Roles | Who does the work, in generic action terms | Role skills (M30, #1184, #1221) |
  | Connectors | Which external tools hold the record and knowledge | The concerns below ([interfaces](../interfaces.md)) |
  | Environments | Where roles run and how generic actions happen (P1) | [Runtime contract](../runtimes/README.md) and the actions contract (P11) |
  | Harnesses | Which agent CLI a role session launches and how it is woken and probed | [Harness adapters](../runtimes/harness-adapters.md) |

  A harness is its own axis, not a concern or an environment. One
  environment can run different harnesses per role, and one harness runs
  in several environments.

  | Concern | Today (GitHub) |
  |---|---|
  | Change (code hosting + change requests) | PRs, squash merge |
  | Review + verdicts | Formal `APPROVE` / `REQUEST_CHANGES` reviews |
  | Tracker | Issues, milestones, Projects |
  | State tags | `crew:*` labels |
  | Comments + markers | COMMENT reviews with hidden `crew:v1` lines |
  | CI signals | GitHub Actions checks |
  | Events / wake sources | GitHub webhooks via routines |
  | Owner channel | Chat with the coordinator |
  | Knowledge (v0.4) | None: repo docs only. First backend: Notion (M32, #1229) |

- **P3. Minimum backend contract.** Each concern interface lists the minimum
  operations a backend must support and the invariant each protects. A
  backend declares what it cannot do. (#110, settled in #121)
  - **`knowledge` (v0.4).** The minimum operations are read, search and
    propose-edit. A role never writes owner knowledge directly. Knowledge
    is context only: no verdict, marker, state tag or gate input lives
    there, so the tool of record (invariant 5) is unchanged. Pointers to
    private pages stay in the install, never in this repo (P6). The
    interface lands with its first backend (#1229).
  - **Harness adapters (v0.4).** The same rule applies on the harness axis.
    An adapter states each field of the
    [harness adapter interface](../runtimes/harness-adapters.md#fields) or
    declares it absent, and that interface defines what an absent field
    means. M30 (#1182) moves each harness's recipe into one adapter module.
- **P4. Install-time profile.** One profile picks one runtime and one backend
  per concern, plus identities and engines (for example `runtime=tmux,
  change=github, tracker=github`). From v0.4 it also picks a harness per
  role and, optionally, a `knowledge` backend. A validator rejects a bad profile before
  anything renders. A renderer produces the role briefs and runtime templates
  from core + bindings + resolved profile, so the live copy is generated from
  this repo instead of mirrored by hand (spec R4 in
  [framework.md](framework.md), `crew:needs-mirror`). The mirror gate is then
  a drift check: the coordinator deploys the render to the live dir and its
  mirror comment carries a clean `check-skill-drift.py --project` result at
  the last touching commit
  ([mirror hold gate](../runtimes/grok-bot.md#mirror-hold-gate)).
  (#110, #122, #125, #128)
- **P5. Config layers.** The effective config resolves from four layers,
  lowest to highest precedence (#110 decision comment, resolver in #123):
  1. **Core defaults** (in mdstack): abstract protocol, role rules,
     invariants, concern interfaces.
  2. **Default profile** (in mdstack): today's GitHub setup for external
     projects.
  3. **Org / environment pack** (outside mdstack, optional): an
     organization's own adapter pack and profile, kept in its own repo and
     pinned to an mdstack version. It overrides default backends per
     concern. From v0.4 a pack can also plug in connectors, harnesses,
     environment defaults, extra skills and tightening-only rules
     ([§9](#9-extension-mechanism)).
  4. **Per-project config** (in the target project or the local install):
     runtime, backend per concern, identities, engines, overrides.
- **P6. No org-internal names here.** mdstack never contains
  organization-internal tool names, commands, URLs or specs. Packs reference
  mdstack, never the reverse. (#110, guard in #127)
- **P7. Default profile stays complete.** The default GitHub profile is a
  complete, working setup on its own, with no org pack. (#110, #124)
- **P8. GitHub + Grok Bot keeps working after every merge.** Each roadmap PR
  leaves today's runtime and backend working; structural (move/reword) and
  behavioural changes never share a PR. Box skills follow the mirror
  deferral in [§6](#6-decisions). (#110, #112, #140)
- **P9. Versioned releases.** mdstack ships named deliverables as SemVer
  releases: a tag and a GitHub Release with one bundle, cut by a workflow
  only after the owner approves it. Packs pin a tag and installs record
  one; nothing auto-updates an environment. Inventory, packaging and
  compatibility in [deliverables.md](../deliverables.md); workflow, release
  gate, rollback and update path in [release.md](../release.md). (#145,
  #217, #218, #219)
- **P10. Changelog fragments.** Changes are recorded as per-PR fragments
  under `changes/unreleased/` and assembled into `CHANGELOG.md` at release
  cut. (owner, 2026-10-30, #264)
- **P11. Generic actions (v0.4).** Role and protocol text names actions
  generically, for example notify a role, wait for an event, claim an item,
  record a heartbeat, report status, post a marker or spawn a worker. It
  never names one environment's commands. Each environment maps every
  action to its own tools and marks the gaps. The **actions contract**
  ([#1218](https://github.com/mw-ding/eng-crew/issues/1218), M29) defines
  each action's semantics, inputs, outputs and outcomes, plus a CLI
  contract and the per-environment mapping table. Its vocabulary comes
  from the [#1213](https://github.com/mw-ding/eng-crew/issues/1213)
  inventory. Connectors, environments and harnesses implement it. The
  terminal CLI implementation is M32
  ([#1232](https://github.com/mw-ding/eng-crew/issues/1232)). Until then,
  today's briefs and commands stay in force. (owner, 2026-11-07, #1180)

## 3. Invariants

Every runtime + backend combination must keep these (#110):

1. **Author ≠ reviewer identity**, or the documented single-identity rule:
   verdicts as COMMENT reviews with `pass=verdict` markers and a recorded
   owner merge-ok ([§6](#6-decisions), #111).
2. **Reviewer engine ≠ the engine that actually wrote the round**, unless a
   recorded waive applies (see [roles.md](../roles.md)).
3. **Evidence on the change record.** Every piece of evidence a verdict relies
   on is inline in the body or signed reviews, never committed to the repo.
   Captures at or before head count only when validation at head confirms
   they still apply ([verification](../verification.md)).
4. **Only the synthesizer lands** the change.
5. **The tool of record holds the audit trail** (tracker item → change →
   verdict → land), never only a chat or a terminal pane.

A backend or runtime that cannot express an invariant makes that profile
**unsupported**. It is never silently weakened. (#110)

**Scoped express exception.** Only for a change whose effective flavor is
`express` ([protocol §3](../protocol.md#change-flavor)) and that carries
`crew:express`: invariant 1 is relaxed, since the builder identity posts the
selfgate record about its own change in place of a reviewer verdict, and
invariant 2 is relaxed only when `selfgate_engine = same`. Invariants 3–5
hold. The exception is written here for one label and never inferred by a
runtime, so it is not a silent weakening. A runtime that cannot run the
self-gate runs an express item in the crew lane.

## 4. Target layout

**Superseded (v0.4).** This table records the M13–R1 layout as built. The
target layout is now the modular one (`roles/`, `protocols/`, `actions/`,
`connectors/`, `environments/`, `harnesses/`, `core/`, `cli/`), with
dependency rules. It is specified in the team spec
([#1216](https://github.com/mw-ding/eng-crew/issues/1216)) and moved in M31
([#1222](https://github.com/mw-ding/eng-crew/issues/1222)). Until that move
lands, the paths below are current.

| Path | Contents | Created by |
|---|---|---|
| `docs/concepts.md` | Glossary of abstract terms, mapped to GitHub / Grok Bot | 13.1 (#113) |
| `docs/runtimes/README.md` | Runtime contract: what every runtime provides | 13.8 (#120) |
| `docs/runtimes/grok-bot.md` | Grok Bot binding: routines, watches, sweeper | 13.2 (#114) |
| `docs/runtimes/tmux.md` | tmux binding design and contract table | 14.1 (#130) |
| `docs/backends/github.md` | GitHub binding: reviews, markers, identities, tracking, labels | 13.3 (#115), extended by 13.4 (#116) |
| `docs/interfaces.md` | Concern interfaces and capability declaration | 13.9 (#121) |
| `docs/profile.md` | `crew.toml` schema, layers and precedence | 13.10 (#122), extended by 13.11 (#123) |
| `docs/packs.md` | External pack layout, version pin, direction rule | 13.15 (#127) |
| `templates/runtimes/grok-bot/` | Grok Bot routine templates | 13.5 (#117) |
| `templates/runtimes/tmux/` | tmux coordinator and role briefs | 14.8 (#137) |
| `profiles/default.toml` | Default GitHub + Grok Bot profile | 13.12 (#124) |
| `packs/github/manifest.toml` | GitHub pack manifest | 13.12 (#124) |
| `scripts/crew-config.py` | Profile `validate` and layered `resolve` | 13.10 (#122), 13.11 (#123) |
| `scripts/crew-render.py` | Renderer: profile to role briefs and templates | 13.13 (#125) |
| `scripts/crew` | tmux crew CLI (`up`, `down`, `spawn`, `kill`, ...) | 14.2 (#131) |
| `docs/deliverables.md` | Deliverables inventory, packaging, SemVer and compatibility rules | R1.1 (#145) |
| `docs/release.md` | Release workflow, release gate, rollback, update path | R1.1 (#145) |
| `scripts/changelog-cut.py` | Cuts `[Unreleased]` into a version section | R1.2 (#217) |
| `.github/workflows/release.yml` | Release workflow: validate, build, owner approval, tag, publish | R1.3 (#218) |

## 5. Milestones and slices

Each slice is one issue → one PR, sized by its unit of work (#978): a large
PR splits into logical commits, not more issues. The line counts in the
tables below are historical estimates, not a budget. Child issues say "Part of #110" and never
close the umbrella. Project board:
<https://github.com/users/md-mt/projects/10>. **Status** is the issue's
state: `open`, `done` or `dropped` (closed without landing); CI checks every
row has one (`check-repo.py --only spec-status`). A doc whose H1 says
"(design)" or "in design" names, in that H1 or its banner, an issue or
milestone here that is still open, or is listed with a reason in
`scripts/design-headers.txt` (`check-repo.py --only design-headers`).

**Superseded plan (v0.4).** The M15–M21 tables below are the v0.3 plan
and keep their v0.3 Status values; they are not re-synced here. M22–M28
were tracked as GitHub milestones only. The current plan is
[M29–M34](#m29-specs-and-contracts) (owner, 2026-11-07). M28 closed as
superseded and its issues moved to M30. Grok Bot and Hermes
adapters and herdr agent-API support are dropped for now. The deferred
M20.1 (remote role sessions) and M25.1 (owner environment) backlogs stay
open and are not dispatched.

M15–M21 carry out the #160 review
([final conclusion](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532414226),
[milestones](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532947853),
[backlog placement](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6533072952)).
Order: M15, M16 and M17 in parallel after M13; M18 after M16 and M17; M19
after M14 and M15; M20 after M14, M15, M17 and M21 (owner, 2026-11-03,
[#715](https://github.com/mw-ding/eng-crew/issues/715)); M21 after M17. Existing design
and backlog issues moved into a milestone carry the IDs given here.

### Pre-work

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| P1 | #111 | Review and merge identity for roadmap PRs (decided) | none | done |
| P2 | #112 | Protocol freeze window for M13 Phase A | P1 | done |

### M13 Phase A: split (structural)

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 13.1 | #113 | Concepts glossary | P2 | done |
| 13.2 | #114 | Extract Grok Bot runtime binding | 13.1 | done |
| 13.3 | #115 | Extract GitHub binding: reviews, markers, identities | 13.1 | done |
| 13.4 | #116 | Extract GitHub binding: tracking, labels, linkage | 13.3 | done |
| 13.5 | #117 | Move routine templates under `templates/runtimes/grok-bot/` | 13.2 | done |
| 13.6 | #118 | Core protocol §1–§5 in abstract terms | 13.3, 13.4 | done |
| 13.7 | #119 | Core §6, §7 and gate registry in abstract terms; lifts freeze | 13.6 | done |

```mermaid
graph LR
  P2[P2 freeze] --> A1[13.1 glossary]
  A1 --> A2[13.2 Grok Bot binding]
  A1 --> A3[13.3 GitHub reviews]
  A3 --> A4[13.4 GitHub tracking]
  A2 --> A5[13.5 templates move]
  A3 --> A6[13.6 core §1-§5]
  A4 --> A6
  A6 --> A7[13.7 core §6-§7]
```

### M13 Phase B: interfaces, profiles, rendering

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 13.8 | #120 | Runtime contract | 13.2 | done |
| 13.9 | #121 | Backend interfaces and capability declaration | 13.7 | done |
| 13.10 | #122 | `crew.toml` profile schema and validator | 13.9 | done |
| 13.11 | #123 | Layered config resolver | 13.10 | done |
| 13.12 | #124 | Default GitHub profile and pack manifest | 13.10 | done |
| 13.13 | #125 | Renderer: profile to role briefs | 13.11, 13.12 | done |
| 13.14 | #126 | Templatize Grok Bot templates with a parity check | 13.5, 13.13 | done |
| 13.15 | #127 | External pack contract and internal-name guard | 13.12 | done |
| 13.16 | #128 | Replace manual mirroring with render-vs-live drift | 13.14 | done |
| 13.17 | #129 | Runbook: install by profile | 13.13 | done |
| 13.18 | #140 | Sync live box skills to `main` after M13 | 13.7; preferred after 13.14, 13.16 | open |

### M14: tmux crew runtime

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 14.1 | #130 | tmux runtime design doc | 13.8 | done |
| 14.2 | #131 | `mdstack up` / `mdstack down`: coordinator session | 14.1, 13.13 | done |
| 14.3 | #132 | `mdstack spawn` / `mdstack kill`: role sessions | 14.2 | done |
| 14.4 | #133 | `mdstack send`: reference-only messaging | 14.3 | done |
| 14.5 | #134 | `mdstack poll`: GitHub event poller, one consumer | 14.4 | done |
| 14.6 | #135 | Liveness heartbeat, `mdstack status`, watchdog | 14.3 | done |
| 14.7 | #136 | Serial land lock and concurrency cap | 14.3 | done |
| 14.8 | #137 | tmux render targets: coordinator and role briefs | 14.2, 14.3, 14.4, 14.5 | done |
| 14.9 | #138 | Observe: `mdstack attach`, `mdstack logs`, step summaries | 14.3 | done |
| 14.10 | #139 | End-to-end smoke on a sandbox repo and tmux runbook | 14.5–14.9 | done |
| 14.11 | #172 | `mdstack kill` refuses to remove unlanded work | 14.3 | done |

### M14.1: tmux hardening (dry-run fixes)

Fixes from the 14.10 dry runs and live sandbox run; 14.1a–d gate the 14.10
live run.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 14.1a | #230 | Watcher never wedges; wake on queue growth; `mdstack drain` | 14.10 dry run | done |
| 14.1b | #231 | Process, env and safety: no orphans, coordinator-only guard, pre-trust, sandbox env | 14.10 dry run | done |
| 14.1c | #232 | Rounds, claims and probes: no deadlock on unchanged head, per-pass claims, restart after done | 14.10 dry run | done |
| 14.1d | #233 | Briefs: crew path, land lock, docs paths, step summaries, `gh -R`, standing grant, validate order | 14.10 dry run | done |
| 14.1e | #234 | Second local dry run: zero manual unblocks | 14.1a–14.1d | done |
| 14.1f | #250 | Restart without duplicate PRs, Codex hooks gate, read-only state writes, `.crew` exclude | 14.1e dry run | done |
| 14.1g | #251 | Briefs: dialog handling, adopt an existing PR, render the role | 14.1e dry run | done |
| 14.1h | #255 | Coordinator never auto-applies a merge-ok | 14.10 live run | done |
| 14.1i | #257 | CI lint for rendered tmux briefs (regression guard) | 14.1h | done |
| 14.1j | #265 | `crew`: refuse placeholder paths in RESOLVED profile values (closes F5 bypass) | 14.10 live run | done |
| 14.1k | #266 | tmux briefs: state labels follow the verdict; asks closed by COMMENT review | 14.10 live run | done |

### M14.3: tmux polish

Small tmux fixes that don't block usability, after the M14.2 release (owner,
2026-11-01). Each Scope cell names the merged PR.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 14.3a | #301 | `mdstack guard` counts open owner asks as work in flight (PR #355) | M14.2 | done |
| 14.3b | #270 | tmux briefs write `--body-file` scratch files under the state dir (PR #356) | M14.2 | done |
| 14.3c | #303 | The reviewer posts the §6 intake ack when it picks up a PR (PR #357) | M14.2 | done |
| 14.3d | #312 | One kill-and-respawn for a stuck synthesizer after a failed nudge (PR #359) | M14.2 | done |
| 14.3e | #262 | Codex trust: `mdstack up` pre-trusts a Codex coordinator with the `projects` table (PR #365) | M14.2 | done |

### R1: versioned release

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| R1.1 | #145 | Deliverables and versioned release CI/CD (design) | 13.13, 13.14, 13.15 | done |
| R1.2 | #217 | CHANGELOG cut script | R1.1 | done |
| R1.3 | #218 | Release workflow with owner approval | R1.1, R1.2 | done |
| R1.4 | #219 | First cuts: retro-tag v1.0.0 and cut v2.0.0 after M14 | R1.3, 14.10 | done |
| R1.5 | #235 | Deliverables manifest and unclassified-path check | R1.1 | done |
| R1.6 | #236 | Release bundle build | R1.5 | done |
| R1.7 | #246 | Attach the release bundle in `release.yml` | R1.6 | done |
| R1.9 | #275 | Ship `check-repo.py` in the release bundle and smoke-test the extracted bundle | R1.4 | done |
| R1.10 | #276 | R1 close-out: README status sync and install-from-release steps | R1.4 | done |
| R1.11 | #277 | Release v2.0.1 (bundle fix #275, install steps #276) | R1.9, R1.10 | done |

### M15: runtime contract v2

Runtime contract amendments and the harness and session-backend interfaces
(#160 rows
[3](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531125583),
[4](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531265464),
[5](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531284681),
[13](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532100410)).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 15.0 | #173 | Spec: add M15–M21 and 14.11 to the portable spec | M13 | open |
| 15.1 | #174 | C1: waiting costs no model turns | 13.8 | open |
| 15.2 | #175 | C5: run identity is a handle plus start time | 13.8 | done |
| 15.3 | #176 | C6: teardown only after provable landing | 13.8 | open |
| 15.4 | #177 | Harness adapter interface | 13.8 | done |
| 15.5 | #178 | Session backend interface | 15.2 | open |
| 15.6 | #179 | Bindings declare harness adapters and session backends | 15.1, 15.3, 15.4, 15.5 | open |
| 15.7 | #264 | Changelog fragments assembled at cut (tracker; parts 1–3) | R1.4 | open |
| 15.7a | #296 | Changelog fragments part 1: format, cut-time assembly, tree guards | — | done |
| 15.8 | #150 | Grok Bot runtime: close or accept the declared contract gaps (C1, C2, C3, C5) | 15.6 | open |
| 15.9 | #287 | Watcher wakes by the earliest owner-ask deadline (C8 doc/code mismatch) | — | open |

### M16: quality and governance

Inline pre-review check, `crew:sensitive`, gate-status comment,
owner-communication rules, persona in the profile and knowledge hygiene (#160
rows
[8](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531125583),
[9](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531795606),
[11](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531918771),
[14](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532191486),
[18](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532327593)).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 16.1 | #180 | Pre-review check: builder protocol | M13 | open |
| 16.2 | #181 | Pre-review check: profile switch | 16.1 | open |
| 16.3 | #182 | Pre-review check: reviewer and synthesizer gates | 16.1, 16.2 | open |
| 16.4 | #183 | Pre-review check: before/after metrics | 16.3 | open |
| 16.5 | #184 | `crew:sensitive` class from deterministic path rules | M13 | open |
| 16.6 | #185 | Synthesizer gate-status comment | M13 | open |
| 16.7 | #186 | Owner-communication rules for the coordinator | M13 | open |
| 16.8 | #187 | Persona and signature in the profile | M13 | open |
| 16.9 | #188 | Knowledge routing and correct-not-add for always-loaded files | M13 | open |
| 16.10 | #189 | Upstream contribution gate | M13 | open |
| 16.11 | #143 | Evidence inline in PRs only; stop committing `evidence/` artifacts (lands before 16.1) | 13.7 | open |

### M17: bootstrap and doctor

Bootstrap design with `mdstack doctor`, propose-confirm-record, upgrade reload,
tool drift and a size budget (#160 rows
[12](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531985646),
[15](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532247500),
[17](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532308283)).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 17.1 | #144 | Bootstrap: install mdstack into a new environment (design) | 13.8, 13.11, 13.13, 13.15, 14.1, R1.1–R1.4 | open |
| 17.2 | #190 | `mdstack doctor`: read-only checks, `--fix` and human steps | 17.1 | open |
| 17.3 | #191 | Bootstrap proposes, owner confirms, profile records | 17.1 | open |
| 17.4 | #192 | Upgrade: re-render and reload running roles | 17.1 | open |
| 17.5 | #193 | Doctor: tool-drift check | 17.2 | open |
| 17.6 | #194 | Self-test: size budget for always-loaded files | 17.1 | open |
| 17.7 | #165 | `crew-config`: expose resolve as a function returning the merged profile (structural refactor; lands before 17.3) | — | open |
| 17.8 | #166 | Packs: let an external pack add a new backend; record the pack path in `crew.toml`; feed the denylist in CI | — | open |

### M18: flavors and away mode

Crew flavors with intake and triage rigor discipline, and a recorded owner
away mode (#160 rows
[15](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532247500),
[19](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532357093)).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 18.1 | #156 | Crew flavors: per-project rigor/optimization presets with a metrics feedback loop (design) | — | open |
| 18.2 | #195 | Flavor schema and floor validator | 18.1, 16.2, 16.5 | open |
| 18.3 | #196 | Rigor decided at intake and triage | 18.2, 17.3 | open |
| 18.4 | #197 | Class rule inside one project | 18.2 | open |
| 18.5 | #198 | `/crew away`: recorded away mode with return brief | 16.7 | open |
| 18.6 | #199 | `/crew away --cap` and `--quiet` | 18.5 | open |
| 18.7 | #102 | Solo coding-agent lane (Claude/Codex deep sessions), as a `solo` flavor preset | — | open |
| 18.8 | #109 | Quota: cut Cursor/Grok Bot orchestration burn while Claude Code/Codex do the builds | — | open |

### M19: harness and backend adapters

Minimum harness targets beyond Claude Code and Codex, and the herdr session
backend (#160
[row 13](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532100410)).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 19.1 | #200 | Harness adapter: Pi | 15.6, 14.10 | open |
| 19.2 | #201 | Harness adapter: Cursor | 15.6, 14.10 | open |
| 19.3 | #202 | Harness adapter: Muse | 15.6, 14.10 | open |
| 19.4 | #203 | Session backend: herdr | 15.6, 14.10 | open |
| 19.5 | #170 | tmux runtime: verify Codex as coordinator (wake line + turn-end notify) on the real CLI | — | open |

### M20: multi-device

Host inventory, host readiness and hardened remote calls (#160
[row 6](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531687881)),
**runner first** (owner, 2026-11-03,
[#715](https://github.com/mw-ding/eng-crew/issues/715)). The first second
host has no forge access, so M20 delivers a remote test runner on
forge-less hosts: the primary is the forge gateway and seeds the host over
the hardened call, the host runs the forge-free checks at a head, results
come back by reference, and an unreachable runner falls back to a local run
without blocking a gate. Design:
[multi-device, forge-less hosts](../runtimes/multi-device.md#forge-less-hosts-remote-test-runner).
Remote role sessions (placement, remote lifecycle, wake, partition, attach)
and any forge relay move to a follow-up milestone. Real-device cases are
logged in [#716](https://github.com/mw-ding/eng-crew/issues/716).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 20.0 | #715 | Forge-less hosts, remote test runner first (design update and re-scope) | 20.1 | open |
| 20.1 | #158 | Multi-device crew: coordinator runs role sessions across devices on a private overlay network (design) | — | open |
| 20.2 | #204 | Host inventory and project affinity in the profile | 20.1 | done |
| 20.3 | #205 | `mdstack host check` and `mdstack hosts` | 20.2, 17.2 | done |
| 20.4 | #206 | `mdstack host prepare`; seeds a forge-less host's mirror from the primary | 20.3, 20.6 | open |
| 20.6 | #208 | Hardened remote call and remote runner | 20.1 | open |
| 20.7 | #209 | Two-host dry run: primary plus a forge-less runner host (owner-run, #716) | 20.13–20.16 | open |
| 20.12 | #349 | Add-a-runner-host runbook and host rows in the tmux contract table | 20.15 | open |
| 20.13 | #726 | Forge-less host capability: `forge = false` | 20.2, 20.3 | open |
| 20.14 | #727 | Runner job verbs: forge-free checks at a head | 20.4, 20.6 | open |
| 20.15 | #728 | `mdstack runner` client with local fallback | 20.13, 20.14 | open |
| 20.16 | #729 | Runner results as evidence | 20.15 | open |

Moved to the remote role sessions follow-up milestone: 20.5 (#207,
placement in `mdstack spawn`), 20.8 (#345, remote run lifecycle), 20.9 (#346,
remote wake and messages), 20.10 (#347, partition handling for role runs)
and 20.11 (#348, remote attach and logs), plus a forge relay if one is
needed later.

### M21: runtime handoff

Cross-runtime handoff with read-only fallback, idempotent transfer and
retry-until-ack (#160
[row 16](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532279114)).

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 21.1 | #157 | Runtime handoff: pause one crew runtime and resume the same work in another (design) | — | open |
| 21.2 | #210 | Ownership marker and read-only fallback | 21.1 | open |
| 21.3 | #211 | Handoff manifest and idempotent transfer | 21.2 | open |
| 21.4 | #212 | Prompt stop and resume | 21.3 | open |
| 21.5 | #213 | Dry-run handoff | 21.4 | open |

### M29: specs and contracts

The roadmap the owner approved on 2026-11-07
([#1180](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703873341),
[M34](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703974869)).
Order: M29, M30, M31, M32, M33, M34. Within a milestone, the order follows
each issue's `Depends on` lines, shown below. The review level per
milestone is the issue's recorded flavor. Docs only.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 29.1 | #1216 | Team spec: requirements, module layout, dependency rules | — | open |
| 29.2 | #1217 | This spec at v0.4 | — | open |
| 29.3 | #1218 | Actions contract: vocabulary, CLI contract, per-environment mapping | — | open |
| 29.4 | #1219 | `docs/specs/` in the essential project doc set | — | open |
| 29.5 | #1220 | Baseline metrics before the reorganisation | — | open |

### M30: decouple in place

Refactor only: no behaviour change and no silent fixture changes.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 30.1 | #1184 | Reviewer role skills pilot: one canonical source plus runtime fragments | — | open |
| 30.2 | #1221 | Canonical role skills for the other roles | 30.1 | open |
| 30.3 | #1182 | Harness adapters: one module per harness | — | open |
| 30.4 | #1183 | Session-backend capability boundary | 30.3 | open |
| 30.5 | #1185 | Role registry from each role's canonical skill | 30.1 | open |

### M31: modular reorganisation

One cutover and a major release.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 31.1 | #1222 | Move-only reorganisation into the modules | — | open |
| 31.2 | #1223 | `packs/github` becomes `connectors/github` | 31.1 | open |
| 31.3 | #1224 | Tests per module; dependency rules in `check-repo` | 31.1 | open |
| 31.4 | #1225 | Bootstrap scaffolds `docs/specs/` | 29.4 | open |
| 31.5 | #1187 | Synthesizer inbox full replay | — | open |
| 31.6 | #1176 | Lead first ack without a status dir | — | open |
| 31.7 | #1236 | Pack plug-in loading and conformance kit ([§9](#9-extension-mechanism)) | 31.2, 29.3 | open |
| 31.8 | #1226 | Major release cut and migration note | 31.1–31.7 | open |
| 31.9 | #1178 | Home-level layout cutover | 31.8 | done |

### M32: team beyond eng

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 32.1 | #1227 | Role classes: owner-facing seats, internal staff, team heads | 29.1 | open |
| 32.2 | #781 | Coordinator display title | — | open |
| 32.3 | #1228 | Seat placeholders and a seat template | — | open |
| 32.4 | #1229 | `knowledge` connector: first backend | 29.3 | open |
| 32.5 | #1230 | Core memory layer | — | open |
| 32.6 | #1231 | On-demand role lifecycles | — | open |
| 32.7 | #1232 | Generic-action CLI subcommands (P11) | 29.3 | open |

### M33: rename

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 33.1 | #1233 | CLI rename with a compatibility shim | 31.8 | open |
| 33.2 | #1234 | Repository rename and repo-keyed state names | 33.1 | open |
| 33.3 | #1235 | Settle the owner's old private design repo | — | open |

### M34: public documentation and major release

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| 34.1 | #1237 | Docs consolidation for the modular structure | 33.1, 33.2 | open |
| 34.2 | #1238 | Getting-started, pack-author and migration guides | 34.1 | open |
| 34.3 | #1239 | Major release cut with release notes for M29–M34 | 34.1, 34.2 | open |

### M45: recover runs and preserve queue state

Added by its status-sync slice #1670, part of
[#1644](https://github.com/mw-ding/mdstack/issues/1644). M45 opened before
the spec bookends (#259) landed, so this section is a one-time amendment
made at close. Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1644#issuecomment-6788963909):
nine builds from ten members, plus two follow-ups. Every row has shipped.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| B1 | #1536 | A missing expected CI check never reads as green (PR #1658) | — | done |
| B2 | #1633 | Wake the lead for a builder idle after an API error (PR #1655) | — | done |
| B3 | #1639 | Reviewer notify refusal: diagnosis only, caller error, no PR | — | done |
| B4 | #1020 | Isolate malformed reviewer work refs in the pool and scheduler (PR #1660) | — | done |
| B5 | #1005 | Count reviewer rounds after the canonical steer resume (PR #1656) | — | done |
| B6 | #631, #1074 | Select the next eligible engine; quota-stopped runs restart on it (PR #1657) | — | done |
| B7 | #738 | Refuse Claude Code bypass as root before the worker window (PR #1652) | — | done |
| B8 | #1480 | tmux `new_session` raises when new-session exits 0 without a session (PR #1650) | — | done |
| B9 | #1082 | `mdstack up` ensures leads on a running session after the handoff ack (PR #1651) | — | done |
| F1 | #1654 | Deflake the upgrade lost-PID-file and persistent-watcher tests (PR #1664) | — | done |
| F2 | #1665 | M44 close capture (PR #1667) | — | done |
| — | #1003 | Reviewer verdict dedupe: closed as covered by PR #1163 | — | dropped |

Open questions M45 settled:

- **B1's required-check baseline.** The repo has no branch protection or
  ruleset to read, so the expected set is an explicit profile setting:
  `markdownlint`, `links` and `repo-guard` required, `lab` optional
  ([owner decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6789266394)).
- **#1639 was a caller error.** The reviewer passed window index `0` to
  `action notify --to`, which resolves window names; no socket or lookup
  defect, so no code PR
  ([diagnosis](https://github.com/mw-ding/mdstack/issues/1639#issuecomment-6789247738)).
- **#1003 needed no build.** A current-path reproduction started no
  duplicate review at the same head and round.

Lessons:

- **Flaky default-branch tests.** A timing-dependent watcher test from
  #1620 failed main CI once and passed on rerun (#1654); F1 deflaked it.
  Rerun a flaky job, never waive it, and file the flake as an item.
- **Environment-dependent bootstrap smoke.** Inherited host probes can fail
  the bootstrap smoke before its intended assertion (#1668); fixture
  isolation is a follow-up outside M45.

Merge permission for M45 gate-contract and spec text was the owner's
[M45–M48 grant](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6789266394).
M45 closes, and v7.8.0 is cut, after this slice merges.

### M46: verification exercises the real path

Opened by the spec slice #1669, part of
[#1645](https://github.com/mw-ding/mdstack/issues/1645). M35–M44 were
tracked as GitHub milestones only. Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1645#issuecomment-6793843567):
seven survivor items and one follow-up, so that each check runs the path
it claims to prove. Statuses were set by the status-sync slice #1690:
every build row has shipped; B7's owner-run A19 proof is still pending.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| B1 | #1614 | Synthesizer refusal lab: the production session synthesizer against a stub stack backend (PR #1680) | #1669 | done |
| B2 | #1412, #1684 | Campaign assertions and retained failing cases (PR #1677); remaining failure-propagation forms split to #1684 under the stop rule (PR #1687) | #1669 | done |
| B3 | #1411 | Discovery-path absence tests (PR #1673) | #1669, after B1 and B2 start | done |
| B4 | #1413 | Production template test helper (PR #1674) | #1669, after B1 and B2 start | done |
| B5 | #1414 | Visible untracked files in `check-repo.py` (PR #1676) | #1669, after B1 and B2 start | done |
| B6 | #1493 | Unbuffered lab status-pull input (PR #1675) | #1669, after B1 and B2 start | done |
| B7 | #1470, #1469 | Faithful A19 source (linked worktree) and shared-server preconditions (PR #1681); the owner-run pinned-source A19 proof is still pending | #1669, after B1 and B2 start | done |
| F1 | #1649 | Detached-fixture capture-pipe lesson (docs) (PR #1672) | #1669 | done |
| F2 | #1688 | M45 close capture (PR #1689, approved, not yet merged) | — | open |

Decisions M46 settled:

- **#1469 consolidated into #1470.** The same A19 journey needs source and
  trust parity and the shared-server precondition before its failed
  bindings rerun; B7 carried both issues' criteria and evidence.
- **#1649 is a learning only.** Its fixture fix already shipped in #1637;
  F1 recorded the lesson and changed no test.
- **The #1677 split.** B2's rounds 3–7 each closed one failure-propagation
  form and the next review found another. Under the
  [cap-2 stop rule](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6795892864),
  #1677 landed the proven parts and #1684 took the remaining forms.
- **One termination model.** #1684 replaced per-form patches with one rule:
  `exit` ends the step, and `return` its function, only in the step's own
  shell; an `exit`, `return` or exiting helper in a child shell (subshell,
  pipeline, background list, command substitution) is refused by name
  ([campaign harness](../campaign-harness.md)).
- **No protocol or merge-gate change.** B1 exercised the existing gate.
- **Owner steps for B7.** Checkout trust is already accepted for the
  checkout; the owner re-accepts it only if doctor reports it unmet. The
  live proof is a pinned-source A19 run from an ordinary terminal opened
  outside any agent session. mdstack never stops or restarts the shared
  server.

Lessons:

- **Fail closed early.** When each review round finds a new edge case,
  switch to rejecting what cannot be proven, and set a stop rule that
  splits the proven part from a follow-up (#1677, #1684).
- **Measure fixture impact before a sweeping lint rule.** A lint that
  changes what existing scenarios may contain needs its effect on those
  fixtures measured before it is tightened, not discovered round by round.

Merge permission for M46 spec, protocol, template and gate-contract text was
the owner's
[M45–M48 grant](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6789266394),
recorded at each head. M46 has no release cut of its own; it ships in
7.10.0 (#1720) with M47's landed work and M48, and 7.9.0 is skipped. M46
closes after this slice merges.

### M47: installs and working copies

Opened by the spec slice #1691, part of
[#1646](https://github.com/mw-ding/mdstack/issues/1646). Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1646#issuecomment-6797511860):
seven builds, one PR per issue. No item below dispatches before this slice
merges. B3 waits for B1 and B2, and B6 waits for B5; every other row
depends only on this slice. Statuses were set by the status-sync
slice #1721 for the first five landed builds and by the closing
status-sync slice #1735 for B5 and B6: every row has landed.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| B1 | #1344 | Project references (`FILE#repo`) kept through bootstrap, fetch and install (PR #1706) | #1691 | done |
| B2 | #1537 | Revision-bound memory: render reads core memory at one fresh remote-default SHA (PR #1703) | #1691 | done |
| B3 | #1090 | A true bootstrap no-op: an unchanged install writes nothing (PR #1716) | #1691, B1, B2 | done |
| B4 | #1595 | `mdstack connect` dials the inventory host's address (PR #1695) | #1691 | done |
| B5 | #1252 | A builder run cannot remove another run's working copy (PR #1707): run-owned Git metadata, `runtime.options.confinement` and a host guard that refuses `enforce` where the Codex sandbox cannot apply; items 2 and 5 (the live production-launch confinement proof) moved to #1739 by the [owner's choice](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6816385952) | #1691 | done |
| B6 | #316 | Worktree root parity and conservative GC: `mdstack gc`, merged-only and dry-run first (PR #1740) | #1691, B5 | done |
| B7 | #281 | Ship the shared secret and glob primitives; keep `check-repo.py` internal (PR #1700) | #1691 | done |

Decisions M47 settles (the
[coordinator's record](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6797570240)
under the owner's standing pre-approval; any of them changes on the owner's
word):

- **#1537 memory source.** Each render fetches the project's remote default
  branch once and reads core memory from that full SHA, frozen across the
  render's role outputs. A fetch or read failure refuses the render; it
  never falls back to stale or local memory. Core authority stays the
  reviewed project `memory/`.
- **#316 cleanup.** Lifecycle cleanup stays, plus a bounded, dry-run-first
  GC. Automatic removal covers merged work only, with C6 proof; every
  ambiguous case is kept and reported. Legacy keep lists stay, and #1166's
  recorded default (keep) is unchanged.
- **#316 provider deferred.** Git stays the only worktree provider.
  #316's AC4 is revised to: "The provider decision, with the treehouse
  alternative considered and deferred, is recorded under AC1; no provider
  profile key and no fake-`treehouse` tests." Its AC1–AC3 and AC5 stand.
  A later provider needs its own spec slice.
- **Sensitive heads.** B5, B6 (working-copy removal) and B7 (secret
  pattern move) get the full-diff sensitive check at each head; a
  sensitive head still needs the owner's per-change reason.

**B5's enforcing boundary (#1252).** A helper, claim check or prompt alone
does not satisfy #1252, because a raw shell can bypass them. B5 builds this
boundary:

1. **Own Git metadata per builder run.** Spawn gives each builder run a
   working copy with its own Git administrative directory (a local clone
   that borrows objects read-only from the shared checkout), not a linked
   worktree of the shared checkout. Its refs, index and worktree list
   belong to the run, so a commit or fetch never writes the shared
   checkout's metadata.
2. **OS write boundary.** The worker process runs under an OS-enforced
   write sandbox whose writable roots are exactly that run's working copy
   and the reporting paths the brief names (the crew state directory).
   Sibling run roots and the shared checkout, its common Git directory
   included, are read-only, so `git -C <shared> worktree remove`, `rm -rf`
   of a sibling and a write into a sibling's metadata all fail.
3. **Supported configurations.** A configuration enforces confinement
   only when its harness applies an OS write sandbox whose writable roots
   mdstack sets at launch. Today that is Codex with `permission_mode`
   `safe` or `auto` (workspace-write), with the shared common directory
   dropped from its added directories. `bypass` on any harness, Pi, Muse,
   Claude Code without an OS-sandboxed launch, and session-runtime workers
   (subagents in the coordinator's process) do not enforce. B5 may add a
   harness to the supported set only with the same proof. A role host
   applies the same rule on its host.
4. **Refusal.** A profile setting, `runtime.options.confinement`, takes
   `enforce` or `off`. Under `enforce`, spawn refuses an unsupported
   builder configuration before it claims a working copy or opens a
   window, naming the reason. B5 ships `off` as the default so a running
   crew keeps launching. Under `off`, the run record and `mdstack doctor`
   mark the run unconfined, and #1252's guarantee is not claimed for it.
5. **Proof.** Two live builder runs A and B through the production spawn
   and launch path, B with a nested evidence worktree: each of A's
   removal attempts on B fails and B stays usable, while A removes its own
   clean nested tree. C6 landed and discard checks stay as they are.

Owner steps: none for B1–B4 and B7, whose tests use fakes. B5 lists any
launcher or sandbox step its supported configurations need. Legacy #1166
trees stay an owner keep-list decision, not a B6 removal.

Decisions M47 settled:

- **The owner-shell confinement proof (#1465).** A crew worker already
  runs inside the host sandbox, so it cannot apply the nested Codex
  sandbox that B5's live proof needs (exit 71). The proof cannot run from
  a crew session; by the
  [owner's choice](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6816385952)
  #1707 landed the host guard instead, and the live proof moved to #1739,
  which needs owner-shell preconditions.

Lessons (learning cards from the milestone close):

- **Keep a configured root's path semantics (#1732).** A
  repository-relative listing passed to a directory-relative
  `git ls-tree` silently rendered no memory below the Git root; #1703
  added `--full-tree` and a below-root regression.
- **Test both install orders (#1733).** A fresh team bootstrapped
  sibling-first failed doctor on a link its first repo had not yet
  installed; #1706 warns until the owning repo has an install record.
- **Mock a module's reference, not the shared module (#1734).** Patching
  `time.sleep` through the upgrade module also counted
  `subprocess.run` polling; #1703 replaced only the module-local
  reference.

Merge permission for M47 spec, protocol, template and gate-contract text was
the owner's
[M45–M48 grant](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6789266394),
recorded at each head. M47 closes after this slice merges.

Release: all of M47 ships in 7.10.0 (#1720); 7.9.0 is skipped by the
owner's choice.

### M48: release integrity and reports

Opened by the spec slice #1697, part of
[#1647](https://github.com/mw-ding/mdstack/issues/1647). Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1647#issuecomment-6798439318):
nine builds, one PR per issue. No item below dispatches before this slice
merges. B4 (#1418) also waits for B5 (#978) and B2 (#1416); every other
row depends only on this slice. Statuses were set by the status-sync
slice #1721: every row has landed.

| ID | Issue | Scope | Depends on | Status |
|---|---|---|---|---|
| B1 | #1415 | Release cut checks the bump class against the published predecessor's pack manifests (PR #1705) | #1697 | done |
| B2 | #1416 | Release cut PRs use a non-closing release-issue reference; the issue closes after publication (PR #1711) | #1697 | done |
| B3 | #1417 | Released CHANGELOG sections are immutable outside a cut (PR #1704) | #1697 | done |
| B4 | #1418 | Moved or quoted prose keeps its meaning: qualifiers, slice linkage and closing keywords (PR #1719) | #1697, B5, B2 | done |
| B5 | #978 | Work-unit rule: an issue is a unit of work; one PR per issue, split into commits (PR #1710) | #1697 | done |
| B6 | #258 | C8 and §6: a deadline applies only a permitted default and supplies no merge-ok (PR #1699) | #1697 | done |
| B7 | #372 | The coordinator edits owner config only under a recorded authorization (PR #1708) | #1697 | done |
| B8 | #431, #1291 | One report skeleton for every role, with the team in signatures (PR #1709) | #1697 | done |
| B9 | #1314 | Remove `examples/agentconnect/` and every reference to it (PR #1702) | #1697 | done |

ACs and paths per row (the readiness pass has the full text and line
citations):

- **B1 (#1415).** Pin the published predecessor (D1) and a named positive
  manifest corpus; show they pass that release's validator, then run the
  candidate validator on them. A newly failing manifest refuses a
  same-major minor or patch, naming baseline, manifest, failing requirement
  and the required major. A major permits the break; an unreadable baseline
  fails with a repair step. Paths: `scripts/release-check.py` (or a new
  `scripts/release-compat.py`), `.github/workflows/release.yml`,
  `docs/release.md`, `docs/deliverables.md`, release-check tests and
  fixtures.
- **B2 (#1416).** A genuine cut carries exactly one same-repo release-issue
  reference in D2's form. That form satisfies linkage, is discovered for
  publication and never closes at merge. A successful publish posts the
  release URL, then closes the issue; a failure leaves it open. A missing,
  ambiguous or foreign target refuses with a correction step. Paths:
  `docs/release.md`, `docs/backends/github.md`, `docs/protocol.md` (Linked
  issue row and §7), `docs/roles.md`, `scripts/release-trigger.py`, the
  release workflow, builder and synthesizer policy fragments, the tmux
  linkage instruction and its tests.
- **B3 (#1417).** Against the merge base, `check-changelog-pr.py` rejects
  edits to or deletions of released sections, even with a valid new
  fragment, before either success path. A cut may add its section and
  consume fragments. Paths: `scripts/check-changelog-pr.py`,
  `CONTRIBUTING.md`, its test.
- **B4 (#1418).** (a) A doc move records a source-to-destination comparison
  of qualifiers, exceptions and scope. (b) Before opening a slice PR, the
  builder cites the newest signed allocation and compares its issue with the
  PR's link; a later change is reported in a signed note, never fixed by a
  body edit. (c) A body check flags every closing keyword outside the one
  intended closing line, honouring D2's form. It is a builder duty, not a
  new gate. Paths: `CONTRIBUTING.md`, `templates/policy/builder/build-pass.md`,
  `docs/roles.md`, a new `scripts/check-pr-linkage.py` and its test.
- **B5 (#978).** Coordinator planning and stage 1 state the owner's
  work-unit rule: one PR per issue, logical commits that pass where tests
  apply, review by commit and by the combined PR. Separate work keeps
  separate issues; M26 principle 9 (doc moves) stays. The ~100-line slice
  sizing in this section's preface stops being normative; historical tables
  stay. Paths:
  `docs/roles.md`, `docs/protocol.md`, this spec, the coordinator dispatch
  skill, builder and reviewer policy fragments.
- **B6 (#258).** C8 and §6 say a deadline wakes the coordinator to apply
  only a permitted default; elapsed time is never a merge-ok. A merge still
  needs a covering recorded grant or a per-PR owner record plus every gate.
  Paths: `docs/runtimes/tmux.md`, `docs/protocol.md` §6.
- **B7 (#372).** Before editing owner profile, team or config, the
  coordinator reads the recorded authorization and its scope. A covered edit
  is applied and reported with its key and record, with no new ask; an
  uncovered edit keeps the owner's config and goes to the owner-decision
  path. Paths: a coordinator policy fragment and its `SKILL.md` index,
  `docs/roles.md`, render fixtures.
- **B8 (#431, #1291).** `docs/roles.md` defines one outcome-first skeleton
  (headline, TL;DR, numbered changes or findings, compact evidence, next
  actor) and a fixed status set, applied to every role's human reports
  without changing markers, evidence sections or the usage line. Profile
  emoji have neutral fallbacks and one install-wide off switch. Signatures
  carry the team: resolved `team.name`, else the team-file basename; legacy
  single-repo installs omit it. Paths: `docs/roles.md`, `docs/profile.md`,
  `core/crew-config.py`, `core/crew-render.py`, `profiles/default.toml`,
  signing and report fragments, runtime templates and parity fixtures.
- **B9 (#1314).** Delete only `examples/agentconnect/`, its required-doc
  entries, links and catalog rows, and the `examples/**` manifest row;
  regenerate `docs/deliverables.md`; update the parity fixture's provenance
  comment only. Paths: the four files and the references the readiness pass
  lists.

Decisions M48 settles (the
[coordinator's record](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6798475405)
under the owner's standing pre-approval; any of them changes on the owner's
word):

- **D1, #1415 baseline.** The latest published stable predecessor, pinned
  once per cut: v7.8.0 now, v7.9.0 if it publishes first. The corpus is
  named positive manifests plus an external-pack fixture from that snapshot.
- **D2, #1416 linkage.** A release-only non-closing form: `Refs #N` plus a
  whole-line `Release issue: #N`, exactly one same-repo target on a genuine
  cut. Ordinary PRs keep `Closes`. The release issue closes after the
  release URL exists and the notice succeeds.
- **D3, #431 and #1291.** Adopt the report skeleton and fold #1291's
  team-signature AC into #431: B8's one PR closes both issues.

Version classification, against the
[Versioning](../deliverables.md#versioning) table, for the v7.10.0 cut:

- **#1416 is major.** It adds a release-only exemption to the Linked issue
  gate, which §7 checks: a merge gate satisfied differently.
- **#1415 is minor.** The release approval gate's condition, release
  validation green, is unchanged; the new refusal only rejects a version the
  Versioning rules already forbid. If B1 changes the release approval row
  itself, it becomes major and is reclassified in its PR.
- **The rest add no gate.** B3 changes internal paths only (none); B4, B5
  and B7 add role duties and B8 optional profile keys with defaults
  (minor); B6 and B9 are wording or docs changes (patch). B8 changes no
  marker field or parsed output; if it does, it is major.

So with B2 as specified, v7.10.0 cannot be a minor. Before the cut, the
coordinator takes it to the owner, as the decision record requires: a
major cut with a `**Breaking:**` entry, or the owner's other call. No break
goes through as a minor.

Sensitive heads: B1–B3 (release and CI) and B9 (deletions) are forecast;
every build runs the full-diff sensitive check at each head, and a
sensitive head still needs the owner's per-change reason. Owner steps: none
for the nine builds; publication keeps the owner-actor approval flow.

Merge permission for M48 spec, protocol, template and gate-contract text is
the owner's
[M45–M48 grant](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6789266394),
recorded at each head. A status-sync slice closes the milestone.

Questions M48 settled at close:

- **Release class.** The owner chose 7.10.0 (#1720) as a minor despite
  #1416's `**Breaking:**` entry; the entry and its migration step stay in
  the notes, and 7.9.0 is skipped
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6814282786)).
  This was the owner's other call the classification above allows.
- **Order.** The cut ran before this status-sync slice, and the cut freeze
  held the slice until it landed, so the slice ships in the release after
  7.10.0.
- **D1 baseline.** 7.9.0 never published, so v7.8.0 stayed the pinned
  predecessor for the 7.10.0 cut.

Lessons:

- **A sensitive merge-ok is head-pinned (#1717).** A clean merge-up with an
  identical patch dropped #1711's owner merge-ok, though a verdict ports
  across it, so the owner had to answer the same ask again and the PR sat
  owner-blocked about 1.5 hours. Whether an owner merge-ok ports across
  an identical-patch merge-up is for triage under #1717; until then it
  does not.
- **Backstop re-nudge loop (#1715).** The lead backstop re-woke a lead
  every 60 seconds for land ids blocked on an owner `crew:sensitive`
  reason, with no state change, and each `blocked:` line re-woke the
  coordinator. Until #1715 is triaged, the lead settles owner-blocked land
  ids and the coordinator re-sends the land on the owner's answer.

### M49: responsive runs and attributable failures

Opened by the spec slice #1748, part of
[#1744](https://github.com/mw-ding/mdstack/issues/1744). Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1744#issuecomment-6819217773),
§4: seven members, one PR per issue; #1701 adds a PR only if its evidence
reproduces a gap. Every row was planned with its issue `open`. No row
dispatches before this slice merges and the owner has upgraded the live
install to 7.10.0 from an operator terminal with dispatch paused ("upgrade"
below). B4 (#1714) also lands after B1 (#1715), so it integrates the settled
wait and wake contract. Sizes are non-test implementation lines, then test
lines, then the dispatch tier and effort. Statuses were set by the closing
status-sync slice #1768: every row has landed, and #1757 (PR #1761) was
added during the milestone as a main-red fix.

| ID | Issue | Scope | Size | Depends on | Status |
|---|---|---|---|---|---|
| B1 | #1715 | Lead re-nudge backoff: hybrid retries, no timed re-nudge for acknowledged waits (PR #1755) | 100–180; 100–180; default/medium | #1748, upgrade | done |
| B2 | #1682 | Merge-up delta detection accepts the published merge-up note (PR #1754) | 30–80; 60–120; default/medium | #1748, upgrade | done |
| B3 | #1701 | Finished-builder reclaim: evidence disposition first, code only if a gap reproduces. A gap reproduced: the builder lead brief named no action for a `lifecycle` `reclaim` event, so it now runs its pool's `mdstack kill` and marks the id done only once the window and run record are gone (PR #1775) | 0 unless a gap reproduces; 60–120 if needed; default/medium | #1748, upgrade | done |
| B4 | #1714 | Work pause and resume: the coordinator stays, workers stop with work retained; adds the §7 "No project pause" row (PR #1767) | 300–500 in 4–6 commits; 180–300; deep/high | #1748, upgrade, B1 | done |
| B5 | #1100 | Dequeue refusal names lead pool ownership, not a missing slot (PR #1752) | 10–35; 30–60; default/medium | #1748, upgrade | done |
| B6 | #1659 | RemoteRun spawn fixture: visible diagnostics, explicit runner freshness (PR #1753) | 0; 40–90; default/medium | #1748, upgrade | done |
| B7 | #1668 | Bootstrap smoke fixtures isolate irrelevant host doctor probes (PR #1760) | 0; 40–90; default/medium | #1748, upgrade | done |
| A1 | #1757 | Main-red fix, added during M49: `down` counts a watcher already gone before SIGTERM as stopped (PR #1761) | n/a | none | done |

ACs and paths per row (the readiness pass has the full text and line
citations; runtime files are under `environments/terminal/crew.d/`, tests
under `dev/tests/environments/`):

- **B1 (#1715).** Unchanged acknowledged owner, hold or CI waits produce no
  repeated model nudge; other demand follows D2's cap; mixed waiting and
  actionable ids stay independent; a relevant new state wakes the lead at
  once; a watcher restart keeps timers and waits; ack and done identity and
  #1502's admission suppression stay correct. Paths: `watch.py`, `lead.py`,
  `route.py`, `docs/runtimes/tmux.md`, the builder, reviewer and
  synthesizer lead templates under `templates/runtimes/tmux/` for explicit
  wait association. Tests: `test-crew-watch.py`, `test-crew-lead.py`,
  `test-crew-route.py`, `test-crew-reviewer-pool.py`.
- **B2 (#1682).** Replay the original signed, head-pinned #1656 note and a
  conflict-resolved or differing merge-up through poll, route, the reviewer
  lead inbox and admission, keeping round 2 and creating no duplicate pass.
  Clean eligible merge-ups, moved heads, holds, foreign signatures and
  express keep their current handling. Accept the published merge-up form;
  never rewrite history to `fix`. Paths: `route.py`; `poll.py` or
  `reviewer-pool.py` only if the regression shows another delivery gap;
  conditional guidance in `templates/runtimes/tmux/builder.md`. Tests:
  `test-crew-route.py`, `test-crew-reviewer-pool.py`, `test-crew-poll.py`
  if touched.
- **B3 (#1701).** Trace merged builder, lifecycle reclaim, lead ack and
  completion, physical slot release and the next admissible build, with no
  manual terminal re-send. Keep the four-PR report and tell apart missed
  delivery, an unsafe-reap refusal, a busy child and a historical unknown.
  If existing behaviour suffices, record the evidence and learning and
  close; otherwise fix the reproduced gap in this issue. Add no second
  reaper and no weaker unlanded-work check; a retry defect belongs to B1.
  Paths to inspect: `route.py`, `kill.py`, `lead.py`, `dequeue.py`,
  `_shared.py`, `gc.py`, `templates/runtimes/tmux/builder-lead.md`.
  Coverage: `test-crew-route.py`, `test-crew-lead.py`, `test-crew-kill.py`,
  `test-crew-dequeue.py` if changed.
- **B4 (#1714).** A durable project barrier is written before any work
  stops. The coordinator survives; after pause success nothing dispatches,
  reviews, lands, restarts, runs a routine or cleans up, including direct
  CLI and queued work. Worktrees, records, claims, inboxes and status stay.
  A busy atomic land, a remote refusal, a surviving process or unreadable
  pause state never reports success. Repeated pause and resume are safe;
  restart and `up` cannot bypass a pause; resume rechecks live state,
  starts work once and clears no other stop or hold. Paths: new `pause.py`
  and `resume.py`; `_shared.py`, `down.py`, `watch.py`, `lead.py`, `up.py`
  and the admission and writer boundaries in `spawn.py`, `dequeue.py`,
  `route.py`, `reviewer-pool.py`, `land.py` and `train.py`, reusing the
  existing process, lock and preservation helpers; `docs/protocol.md`,
  `docs/runtimes/tmux.md` and the coordinator and lead templates. Tests:
  new `test-crew-pause.py` and `test-crew-resume.py`, plus the affected
  down, watch, lead, route, spawn, land, train and remote lifecycle cases.
- **B5 (#1100).** An eligible request excluded by lead ownership names the
  pool and the operator path; exhausted capacity still says capacity; an
  empty queue stays empty; mixed pools and `--ref` classify correctly.
  Dispatch and reclaim eligibility are unchanged. Paths: `dequeue.py`,
  `test-crew-dequeue.py`, `docs/runtimes/tmux.md` if help changes.
- **B6 (#1659).** RemoteRun spawn failures show stdout and stderr. The
  expected-healthy runner's freshness is explicit at the spawn boundary:
  show delayed setup with a controlled heartbeat age, then refresh the
  fixture heartbeat or use a bounded fixture interval. Production
  freshness, stale and down refusal coverage and the remote down
  preservation and removal assertions stay. Paths: `test-crew-spawn.py`,
  `test-crew-remote.py` if refusal coverage needs it; no product change.
- **B7 (#1668).** Smoke fixtures isolate only host-dependent doctor
  prerequisites, including in the copied subprocess bundle, so a failing
  irrelevant prerequisite cannot preempt the intended smoke assertion. Real
  CLI bootstrap, render and deploy, opt-in and dry-run safety, the
  started-session requirement, the creation-failure manifest and
  queue-once checks stay; real doctor failures keep separate coverage. A
  parent-only mock that cannot reach the subprocess is not enough. Paths:
  `test-crew-bootstrap.py`, `test-crew-doctor.py`; no product change.
  Guidance: `docs/lessons/2026-11-08-real-entrypoint-fixtures.md`.

Decisions M49 settles (the owner's
[decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6831237295)
applies the coordinator's
[recommendations](https://github.com/mw-ding/mdstack/issues/1744#issuecomment-6819242524);
any of them changes on the owner's word):

- **D1, #1714 is a work pause.** Window 0 stays for owner conversation and
  control, and the watcher stays in observation mode: it keeps events but
  routes nothing, nudges no model and runs no GC or automatic default.
  Leads and workers are terminated with all work retained. An atomic land
  already started finishes first; while its lock is held, pause reports
  pausing or busy. A surviving process or unreachable host means an
  incomplete pause. Only an explicit owner resume ends it: resume rechecks
  ownership, heads, holds, CI and retained demand, starts eligible work
  once, keeps window 0, and clears only the project pause, never another
  hold, round count or landing stop.
- **D2, #1715 is the hybrid backoff.** Ordinary retries wait 60, 120, 240,
  480, then 900 seconds, capped per lead and keyed to unchanged pending
  demand and head identity. An acknowledged owner, hold or CI wait gets no
  timed model re-nudge while unchanged: demand is kept and fresh state is
  observed without a model. The lead wakes on the next relevant event
  without waiting for the deadline: a new handoff or head, a hold release
  or owner answer, a terminal CI state, a prerequisite pass or train
  completion, or admission becoming available. Only affected demand
  resets; timers and waits persist across a watcher restart, and a
  token-free fresh-state comparison recovers missed events. Untyped or
  unassociated status never silences other ids. Events wake leads and
  supply no permission. The intervals are defaults, not measured optimums.

Version classification, against the
[Versioning](../deliverables.md#versioning) table, for the next cut:

- **#1714 is major as specified.** A durable pause barrier that the land
  and train paths refuse on adds a condition to the
  [§7](../protocol.md#7-merge-gate-synthesizer) merge gate, and §9 gains
  project pause and resume control. If B4 instead stops landing only
  through the existing `stop-landing` and `resume-landing` record,
  unchanged, and adds commands and duties alone, it is minor and is
  reclassified in its PR.
- **#1682 is patch.** It makes dispatch recognize a merge-up note the
  protocol already allows, beside
  [verdict portability](../protocol.md#verdict-portability-and-delta-re-review);
  the portability gate and its marker fields are unchanged. If B2 changes
  §7 portability text or a marker's meaning, it is major.
- **The rest add no gate.** #1715 adds runtime behaviour and lead duties
  (minor); it becomes major if it newly requires a status or marker field.
  #1100 rewords a refusal (patch) with its exit code and any parsed output
  unchanged; a changed exit code or parsed output is major. #1701 is
  evidence or a fix restoring documented behaviour (patch or none); #1659
  and #1668 are test-only (patch).

So with B4 as specified, the next cut cannot be a minor. Before the cut,
the coordinator takes it to the owner: a major cut with a `**Breaking:**`
entry, or the owner's other call. No break goes through as a minor.

Sensitive heads: B3's conditional teardown fix and B4's stopping and
restarting of work are forecast; every build runs the full-diff sensitive
check at each head, and a sensitive head still needs the owner's
per-change reason. Shared plumbing: a change to `_shared.py` (B3 if it
reaches code, B4) selects dependent-component tests under the
[affected-tests policy](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6763423100).
Owner steps: the 7.10.0 upgrade before any build; after B4 lands, one
supported-host pause and resume acceptance showing the coordinator survives
with no worker or land activity, batched with any upgraded B3 trace.

Questions M49 settled at close:

- **D1 and D2.** The owner's go-with-suggestions direction
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6831237295))
  took the work pause for #1714 and the hybrid backoff for #1715, both as
  recommended; #1767 and #1755 shipped them.
- **Upgrade.** The owner deferred the 7.10.0 upgrade
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6832180374)),
  so the builds ran on the 7.6.0 install instead of waiting for it; the
  owner upgrades after the 7.11.0 cut.
- **#1701.** Its evidence disposition reproduced a gap, so it took the
  conditional code path (#1775) rather than closing on evidence alone.
- **Release class.** #1714 is major as specified: it adds the §7 "No
  project pause" row. The owner chose a minor anyway: M49 ships in 7.11.0
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6840322691)),
  with #1714's `**Breaking:**` entry and its migration step kept in the
  notes, as for 7.10.0. This was the owner's other call the classification
  above allows.

Lessons:

- **Replay through the whole delivery path (#1682).** #1656's signed
  `[Ben/merge-up]` note, a form the protocol allows, never reached delta
  re-review: `route.merge_up_delta` recognized only `fix` and `ci-fix`
  notes, and the reviewer lead got nothing until a manual handoff about
  45 minutes later. #1754 replays the verbatim note through poll, route,
  the reviewer lead inbox and admission, so a delivery gap fails a test
  instead of stalling a PR.
- **Owner-shell captures go in a builder-signed review (#1766).** A
  passing owner-shell capture posted as a coordinator PR comment still
  failed §3 and the §7 Required evidence gate; it took an extra round to
  copy it verbatim, with the owner's attribution, into a builder-signed
  fix review at the capture SHA. Place such a capture there from the start.

Merge permission for M49 spec, protocol, template and gate-contract text was
the owner's merge-ok for all PRs
([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6832180374)),
recorded per PR at each head. M49 closes after this slice merges.

Release: all of M49 ships in 7.11.0, a minor by the owner's choice.

### M50: portable session contracts and stack binding

Opened by the spec slice #1749, part of
[#1747](https://github.com/mw-ding/mdstack/issues/1747). Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1747#issuecomment-6819946824):
six builds, one PR per issue, larger PRs split into reviewable commits. No
item below dispatches before this slice merges and the live install is
upgraded to 7.10.0 (U: an owner-terminal step with dispatch paused, after
the dry run succeeds; the install record still read 7.6.0 at the readiness
pass). Every row was planned with its issue `open`. The order below is
priority, not a dependency; #1722 is last by risk. Sizes are estimated
changed non-test lines. Statuses were set by the closing status-sync
slice #1769: every row has landed, and the builds ran on the 7.6.0 install,
since the owner deferred U (see below).

| ID | Issue | Scope | Size | Depends on | Status |
|---|---|---|---|---|---|
| B1 | #1723 | A primary host accepts a declared command checkout (PR #1756) | 120–220 | #1749, U | done |
| B2 | #1724 | Session researchers are opt-in: an unset cap resolves to 0 (D1), with a forward `**Breaking:**` fragment (PR #1759) | 50–100 | #1749, U | done |
| B3 | #1725 | Spec bookends follow the configured spec home or a specs-only external reference (D2) (PR #1758) | 180–300 | #1749, U | done |
| B4 | #1726 | VCS-neutral negative control in the CLI evidence template (PR #1763) | 15–35 | #1749, U | done |
| B5 | #1727 | Session Upgrading documents the one-time bootstrap prerequisite (PR #1762) | 10–25 | #1749, U | done |
| B6 | #1722 | Additive stack binding: revision IDs and per-change readback (D3); stays minor, as per-change status never meets the tip gate (PR #1766) | 350–550 | #1749, U | done |

ACs and paths per row (the readiness pass has the full text and line
citations):

- **B1 (#1723).** Accept an explicit `hosts.<primary>.checkout =
  "command"`. `host prepare` runs the host-owned `{argv, path}` declaration
  with checked exit and no shell, then writes the existing checkout
  receipt; `host check` reads the receipt and path and never runs the
  command. Only a declared, prepared checkout prints `ok project checkout`;
  a missing declaration, receipt or path, or a failed prepare, stays not
  ready. Git primaries and remote command checkout are unchanged. Prove
  accepted and refused cases with a local stub. Paths:
  `core/crew-config.py`, `environments/terminal/crew.d/host.py`, reusing
  `environments/terminal/remote/crew-remote.py`, `docs/profile.md`,
  `docs/runtimes/multi-device.md`, and their tests.
- **B2 (#1724).** Per D1, an unset session `researchers` cap resolves to 0
  and renders the four ordinary session briefs; a positive cap renders the
  sweep brief. Tmux keeps its default. The refusal for `triage.enabled =
  true` with zero researchers stays. The options table, session guidance
  and sample profile agree; the retained four briefs keep their bytes.
  Paths: `core/crew-config.py`, `docs/configuration/runtime-options.md`,
  `docs/runtimes/session.md`, `profiles/session.toml`, a new forward
  fragment, config and render tests.
- **B3 (#1725).** Bookends render the configured `docs.homes.specs`, with
  the default keeping today's `docs/specs/` bytes in every runtime. Per D2,
  an external reference makes the bookends name it, bootstrap create no
  local spec directory, and `docs-scan.py` record the external content as
  not checked. Spec-first opening and closing status-sync stay; a spec home
  supplies no merge permission or evidence waiver, and `[spec] paths`
  classification still covers repository spec changes. Paths:
  `core/crew-config.py`, `core/crew-render.py`,
  `templates/policy/coordinator/spec-bookends.md`,
  `environments/terminal/crew.d/bootstrap.py`, `scripts/docs-scan.py`,
  `docs/roles.md`, `docs/profile.md`, `docs/project-doc-set.md`,
  `docs/bootstrap.md`, `docs/project-docs.md`, their tests and render
  parity.
- **B4 (#1726).** State the requirement as a throwaway snapshot of the
  guarded paths at the checked head, with the guard's dependencies; label
  `git archive` as one Git recipe. A partial copy names what it copied and
  recreates setup on replay. The Git recipe, mutation assertion, guard
  argv, N1 nonzero / N2 zero and replay comparison are unchanged. Paths:
  `templates/evidence/cli-exit-stdout.md`, render and parity gates.
- **B5 (#1727).** Session Upgrading names a missing `install.json` as the
  condition for a one-time `mdstack bootstrap --project <absolute
  profile>` (pause dispatch, preview, apply), then normal upgrade, and says
  tmux-only adoption does not cover it. No adoption code. Paths:
  `docs/runtimes/session.md`, linking `docs/bootstrap.md`.
- **B6 (#1722).** Per D3, `change.land-stack` binds `<stack-top>`,
  `<stack-changes>` and `<stack-revisions>`; an optional
  `change.read-revision-id` binds each ID to that member's checked full
  head SHA. `land.change_placeholder` is honoured for every per-member
  operation in sync and async stack modes, and `land.stack_status =
  "per-change"` uses individual status, `[land.status]` and
  `change.read-landed` instead of `change.stack-status`. One accepted
  three-member stack sends exactly one request and records each member only
  after complete landed readback; a moved head, invalid ID, held member or
  red CI sends none. Every member still gets its own §7 checks. Paths:
  `core/crew-config.py`, `core/crew-render.py`,
  `environments/terminal/crew.d/land.py`,
  `environments/terminal/crew.d/_land_stack.py`, `docs/interfaces.md`,
  `docs/profile.md`, `docs/runtimes/session.md`, `docs/protocol.md`, the
  stack-land fixture pack, land and stack-land lab tests, render parity.

Decisions M50 settles (the
[owner's choices](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6831237295),
applying the
[coordinator's recommendations](https://github.com/mw-ding/mdstack/issues/1747#issuecomment-6819967642);
any of them changes on the owner's word):

- **D1, #1724 opt-in researchers.** An unset session `researchers` cap
  resolves to 0. B2 ships a forward `**Breaking:**` fragment with the
  migration: a session profile that relies on the sweep, including one
  whose enabled triage relied on an omitted cap, sets a positive cap.
  Released CHANGELOG sections stay byte-identical.
- **D2, #1725 external spec home.** A specs-only `[docs] specs_external =
  "<canonical tracker-item or document URL>"`, mutually exclusive with an
  explicitly configured `homes.specs`. It is a reference, never a path or a
  command; other doc homes are unchanged, and no external fetch or write is
  added.
- **D3, #1722 additive stack binding.** List order is base-first and the
  last member is the representative change. Revision IDs are nonempty
  single safe tokens, checked before substitution, and persisted per member
  in the intent before the first status read or request; resume uses the
  recorded set and never re-resolves or resends. A revision ID is request
  metadata, never the head or landed SHA: `sha=` and `landed=` stay full
  hashes. In per-change mode, differing member states, queued versus
  landing included, are unknown for that pass: the intent is kept and no
  record is printed. Per-change mode refuses `stack_tests_against_tip =
  true` until a real combined-check receipt can be read. Legacy `<stack>`
  and `change.stack-status` operation, and every unbound or GitHub render,
  are unchanged.

Version classification, against the
[Versioning](../deliverables.md#versioning) table:

- **#1724 is major.** No §7 gate changes, but an installed session profile
  that omits `researchers` and relies on the sweep stops sweeping without
  an edit, which is the table's definition of breaking. Hence D1's
  `**Breaking:**` fragment and migration.
- **#1722 is minor.** Its stage 7 stack text adds an opt-in binding: new
  placeholders, an optional `land.stack_status` key with a legacy default,
  and a conditional operation required only when its placeholder is used.
  Every §7 gate, the tip gate and the full-SHA merge record are satisfied
  as before, and legacy mode is unchanged. Its request-identity and
  unknown-state rules still take the gate-contract path. If B6 lets
  per-change status satisfy a §7 gate, such as the tip gate, it is major
  and is reclassified in its PR.
- **The rest add no gate.** #1723 and #1725 add optional behaviour and an
  optional key (minor); #1726 and #1727 are wording and docs (patch).

So with B2 as specified, the release carrying M50 cannot be a minor. Before
that cut, the coordinator takes the class to the owner: a major with B2's
`**Breaking:**` entry, or the owner's other call. No break goes through as
a minor.

Sensitive heads: B1 (primary checkout command execution) and B6 (land
authority and status handling) are forecast; every build runs the
full-diff sensitive check at each head, and a sensitive head still needs
the owner's per-change reason. Owner steps: applying the compact
`merge_grant` profile line, then U (its dry run waited on that
compaction, #1746). A real non-Git primary checkout is an operator
deployment step; B1's acceptance uses a stub.

Questions M50 settled at close:

- **D1, D2 and D3.** All three shipped as decided above. #1724 (PR #1759)
  took the owner's opt-in: an unset session `researchers` cap resolves to
  0, with the forward `**Breaking:**` fragment and its migration. #1725
  (PR #1758) added `[docs] specs_external` as a specs-only reference,
  refused beside an explicit `homes.specs`. #1722 (PR #1766) added the
  binding without touching legacy `<stack>` operation; per-change mode
  refuses `stack_tests_against_tip`, so it stayed minor.
- **Upgrade.** The owner deferred U
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6832180374)),
  so the builds ran on the 7.6.0 install instead of waiting for it; the
  owner upgrades after the 7.11.0 cut
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6840286560)).
- **Release class.** With B2 as specified the release could not be a
  minor without the owner's call. The coordinator proposed 8.0.0; the
  owner chose a minor: M50 ships in 7.11.0
  ([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6840322691)),
  with #1724's `**Breaking:**` default change and its migration kept in
  the notes, as for 7.10.0.

Lesson:

- **A live harness lab needs an owner-shell capture (#1766).** B6's
  acceptance required the production-synthesizer stack-land lab with the
  new three-member `rev-*` scenarios. Builder sessions cannot start a
  nested harness, and the scripted-engine plumbing test never stands in for
  the live run, so the PR waited a review round for the owner to run the
  lab from an ordinary terminal (all four scenarios passed,
  [capture](https://github.com/mw-ding/mdstack/pull/1766#issuecomment-6840144650)).
  Ask for such a capture as soon as the lab scenarios exist, and place it
  in a builder-signed review from the start (the M49 lesson).

Merge permission for M50 spec, protocol, template and gate-contract text was
the owner's merge-ok for all PRs
([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6832180374)),
recorded per PR at each head. M50 closes after this slice and the release
cut land.

Release: all of M50 ships in 7.11.0, a minor by the owner's choice.

### M51: personnel boundary and team routing design

Opened by the spec slice #1789, part of
[#1779](https://github.com/mw-ding/mdstack/issues/1779). Scope comes from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1779#issuecomment-6844208107)
§2–§5: two members, one PR per issue, split into logical commits. M51 was
admitted after M49 and M50 closed and 7.11.0 was cut
([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846260224)).
The opening slice landed in PR #1797. Statuses below are synced by #1790:
The #1318 design landed in PR #1802, then #1180's personnel delivery in
PR #1805, and all three landed items are closed in the tracker. Personnel
delivery is built; shared-pool routing is designed, with T1–T4 still
unadmitted. Sizes retain the opening plan's estimates, excluding tests.
M51 closes after this status-sync slice (#1790, PR #1806) lands.

| ID | Issue | Scope | Size | Depends on | Status |
|---|---|---|---|---|---|
| S0 | #1789 | Opening M51 spec and applied choices (PR #1797) | docs only | none | done |
| B1 | #1318 | Team/project boundary, profile and role import, repo-qualified admission and per-repo land: design and approved T1–T4 work breakdown only (PR #1802) | S–M, 220–350 prose | #1789 | done |
| B2 | #1180 | Built personnel delivery, rows A–D: content bundle, boundary map, consumer binding, pinned role import (PR #1805) | M, 250–450 implementation + 380–620 prose | #1789, #1318's approved contract | done |

ACs and paths per row (the readiness pass has the full text and line
citations):

- **B1 (#1318), design only.** Update the team spec with the decisions
  below (D1–D3), schema and precedence examples, authority and state
  boundaries, failure behaviour and the derived units T1–T4. A two-repo
  example with the same issue number, change number and head SHA shows
  distinct identities, claims, reservations, worktrees and verdict and
  grant lookup. It covers A held while B is eligible, an unknown repo, a
  mismatched grant or verdict, and a mixed-repo train refusal, and it
  separates specified tests from observed results. Single-repo
  resolution, today's marker meaning and the existing runtime gaps are
  preserved. The design names repo qualification of ownership, claims,
  evidence, verdicts and land permission. The owner's decisions are
  recorded, and an approved work breakdown is linked before any T unit
  becomes ready. No shared-pool code ships here. Paths:
  `docs/specs/team.md`, `docs/configuration/team-files.md`,
  `docs/roles-registry.md`, `docs/scheduling.md`, and the relevant
  `docs/protocol.md` contract references.
- **B2 (#1180), rows A–D.**
  - **A, content bundle.** From a pinned producer checkout, generate and
    locally install a versioned personnel bundle: role descriptors,
    canonical skills and policies, the required specs, protocol and marker
    contracts, and role briefs composed with an explicit thin host
    binding. Record the source version, the selected roles and binding,
    and file hashes. The destination holds and needs no terminal
    scheduler, leads, trains, reap or runner, wake adapters, sweepers,
    terminal CLI or resolver. A fake host loads every selected role's
    brief and procedure with the terminal tree absent; policy references
    resolve and no required action token is unbound. An invalid or missing
    binding yields no usable install, and an identical rerun is
    idempotent. Render in the producer, install only content at the
    consumer; no `--runtime personnel` flag is invented.
  - **B, boundary map.** A file and path map separating content, producer
    dependencies and host execution: `roles/eng/*.toml` and `roles/seats/`
    as descriptors, `templates/policy/` as canonical skill content, the
    specs, protocol, flavors, verification and `actions/*.md` as governing
    contracts, `environments/terminal/` as owned machinery, `harnesses/`
    and `connectors/` as host-selected adapters, and the
    resolver/renderer dependency named. Inert terminal metadata in an
    exported descriptor is binding metadata, not execution or authority.
    No broad module moves.
  - **C, consumer binding.** Name Grok Bot and a generic host as
    consumers. Show how a host loads the content and supplies wake and
    delivery, run identity, claims and status, generic actions, connector
    access and head-bound land enforcement, with a fake-host import
    example and a no-terminal dependency check. Declared capability gaps
    stay declared; importing content starts no routine and grants no gate
    or merge permission. Live platform adoption is not an AC.
  - **D, pinned role import.** A host selects a pinned exported role by
    stable domain and role ID, attaches its mechanical binding, and applies
    allowed presentation, engine and extra-skill settings with provenance.
    Collision and missing-role handling are defined. Role class and
    escalation, marker and pass semantics, reviewer independence and
    synthesizer-only land are preserved; replacing them through this path
    is refused. External role discovery and generic role inheritance stay
    named future work.

  Paths: `scripts/personnel-bundle.py` (new), a content manifest (new,
  proposed `scripts/personnel-files.txt`), `templates/personnel/` (new),
  `templates/policy/`, `scripts/deliverables.txt`, `docs/deliverables.md`,
  `docs/bootstrap.md`, `docs/personnel.md` (new), `roles/README.md`,
  `docs/specs/team.md`, `docs/roles-registry.md`,
  `templates/policy/README.md`, `docs/runtimes/grok-bot.md`,
  `actions/README.md`, `actions/cli.md`, `docs/packs.md`, and a
  fake-host fixture and producer, selection and refusal tests under
  `dev/tests/scripts/`. A needed `core/crew-render.py` edit is flagged in
  the PR and widens its local test set.

Decisions M51 settles (the coordinator applied the readiness pass's
recommendations under the owner's
[standing direction](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6831237295),
recorded in
[c6846260224](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846260224);
the owner reviews later, and any of them changes on the owner's word):

- **D1, #1180 keeps rows A–D, narrowed** as in B2 above: content bundle,
  boundary map, consumer binding, and pinned role import that cannot
  replace authority fields. Superseded: repository consolidation, the
  home move, the canonical-skill, adapter and registry rebuild, and a
  fresh private-role inventory.
- **D2, #1318 extends `[team]` and `[repos.*]`** rather than adding
  `[[projects]]`. The team owns roles and seats, identities, engines,
  capacity, base flavor, host and runtime, and shared adapter defaults; a
  project owns its repo, checkout, default branch, tracker milestones and
  labels, spec and doc homes, control record, rigor overrides and recorded
  land permission. Composition is closed: `core < default < pack/org <
  team < repo`, approved project keys only, and project rigor tightens but
  never relaxes. Roles are pinned content plus a thin binding.
- **D3, #1318 routing.** One team admission budget and shared pools, with
  work envelopes qualified by project, full repo identity, item or change,
  head, pass and round: designed, not built. Claims, evidence and inboxes
  stay in repo state; missing, unknown or mismatched repo context is
  refused and never falls back to the first repo. Land is per repo, with
  per-repo serialization; a mixed-repo train or stack is refused with zero
  mutation. A shared synthesizer is an executor, not shared permission.
- **T1–T4 are derived units, not admitted to M51:** T1 project contexts
  and qualified routing, T2 team admission, T3 shared leads and worker
  lifecycle, T4 repo-bound land execution. #1318's design names them;
  each needs its own plan record.

Version classification, against the
[Versioning](../deliverables.md#versioning) table:

- **#1318 is patch.** Design and spec text, plus contract references that
  change no rule. It adds no gate, marker field or profile key; any such
  change belongs to a T unit and is classified in that unit's plan.
- **#1180 is minor.** A new script, template set and deliverable entries
  add surface and remove none. Its role-import contract restates existing
  authority (role class, markers, reviewer independence, synthesizer-only
  land) and must not change it. Flag: if that contract edits authority
  text so that a §7 gate, a marker field or a role's authority is
  satisfied differently, it is major, takes the gate-contract path and is
  reclassified in its PR.

M51 lessons: distinguish producer dependencies from consumer content;
verify pinned imports and authority preservation through a fake host, without
claiming live adoption. A shared team profile alone does not prove shared
pools or repo-isolated execution: keep T1–T4's scenarios as future tests.

M51's design and personnel delivery landed after the 7.11.0 cut; the
personnel surface is built in source,
not a claim of a released bundle or live host installation. The release
carrying M51 is expected to be a minor.

Sensitive heads: none on the named paths; role-import and land-authority
text get the content-rule `--diff` check at each head, and a match needs
the owner's per-change reason. Owner steps: none for the design or the
content-bundle proof; a live shared-team rollout is an operator step
outside M51.

Merge permission for M51 spec, protocol, template and gate-contract text is
the owner's merge-ok for all M49–M51 PRs
([decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6832180374)),
recorded per PR at each head. A status-sync slice (#1790) closes the
milestone.

### M52: completion routing

Opening spec slice #1798 (PR #1800) and closing status-sync slice #1799
(PR #1811) are the bookends for [#1794](https://github.com/mw-ding/mdstack/issues/1794).
Scope and ACs come from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1794#issuecomment-6846602283),
§2–§3, with the
[coordinator's applied choices](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846633558).
The opening spec merged before the independent B1 and B2 builds. Both fixes
are now built in source: #1772 landed in PR #1804 and #1777 in PR #1803.
Those issues and #1798 are closed in the tracker; no additional M52 build
items were admitted. M52 closes after #1799 lands. Completion never implies
installation. One issue → one PR; larger changes used focused commits.
Sizes below are the planned non-test Python lines, then test lines; both
builds used the default tier, medium effort.

| ID | Issue | Scope | Size | Depends on | Status | PR / evidence |
|---|---|---|---|---|---|---|
| D | #1798 | Opening spec and applied choices | docs | none | done | [PR #1800](https://github.com/mw-ding/mdstack/pull/1800) |
| B1 | #1772 | Informational inbox/ack idle exception; work, upgrade and unlanded safeguards | 40–90; 120–200 | #1798 | done | [PR #1804](https://github.com/mw-ding/mdstack/pull/1804), [review / validation](https://github.com/mw-ding/mdstack/pull/1804#pullrequestreview-5888121459) |
| B2 | #1777 | Same-head posted-round verdict wake identity and duplicate suppression | 60–110; 160–240 | #1798 | done | [PR #1803](https://github.com/mw-ding/mdstack/pull/1803), [final review / validation](https://github.com/mw-ding/mdstack/pull/1803#pullrequestreview-5888493326) |

Settled questions and lessons:

- **Idle eligibility:** only `owner-policy` and its identifiable ack are
  informational for idle detection. Actionable or unknown messages, active
  tools and unlanded work still block reclaim; upgrade still requires delivery
  acknowledgement. Completion, delivery and reclaim eligibility need separate
  checks: ignoring policy chatter for idle detection must not bypass upgrade.
- **Verdict identity:** wake deduplication uses
  `(head, reset_epoch, posted_round, verdict)`; review ID is provenance and
  next-dispatch round stays separate. Duplicate posts do not create new wakes,
  and legacy state seeds without replaying an unchanged verdict. Latest-snapshot
  polling does not recover intermediate verdict history or promise delivery
  exactly once across crashes.
- **Dependent consumers:** B2's first CI run exposed legacy utility callers
  that need roundless/latest-post verdict selection. The final fix preserves
  that no-profile mode while configured production poll keeps signed posted
  rounds ([CI fix and validation](https://github.com/mw-ding/mdstack/pull/1803#pullrequestreview-5888493326)).
  Targeted poll/route checks supported the build; full CI caught the train and
  content dependents and stayed required before land.

**Release / installation:** as of 2026-11-13, the latest published release is
[v7.11.0](https://github.com/mw-ding/mdstack/releases/tag/v7.11.0), cut before
M52's bookends and fixes landed. No release containing M52 has shipped;
these source changes establish no live installation or host adoption.

**Target environment: N/A** — local runtime logic, no new platform or device
dependency. **Owner prerequisites: none** under Codex-first routing, tmux,
standard flavor; reviewer routing uses the actual builder engine. #1792's
trust-dialog repair stays separate. M52's spec edits stay in this file;
`docs/specs/team.md`, `docs/configuration/team-files.md`,
`docs/roles-registry.md` and role-import code are outside its scope. Serialize
the bookends with M51 edits to this file.

#### B1: idle eligibility (#1772)

The applied choice is an **idle-only `owner-policy` allowlist with a matching
informational-ack filter**. New informational kinds need a later explicit
decision. Runtime paths below are under `environments/terminal/crew.d/`;
readiness line citations refer to base
`f4a79465f2d774244a760b791c4000dc7db02c12`.

1. With completed status and no active tool session, an unacked
   `owner-policy` message does not make `idle_builder()` return `None`.
   Ignore its matching trailing `ack: <id>` when finding the last work-status
   line. Keep heartbeat handling and the matching-build completion exception.
2. Unacked `fix`, `ci-red`, `merge-up`, unmatched `build` and unknown kinds
   remain busy. An actionable ack after the latest `done:` remains busy
   until later completion; a later informational ack cannot hide it. An ack
   with no identifiable inbox entry is conservative/busy.
3. No `done:`, a later work/progress/block/failure line or a live tool session
   remains ineligible. Preserve the active-child check; an informational
   exception never creates completion.
4. Preserve the status-file mtime clock, TTL boundary and `ttl=0` disable
   behaviour. A trailing informational ack may restart ordinary TTL grace,
   but cannot permanently prevent eligibility. At expiry the watcher emits
   once through the existing lead/dequeue path; add no new clock/state format.
5. Preserve the unlanded-work refusal (`dequeue.py:31`), retained
   output/status/step summaries and capacity rules. Dirty/untracked paths
   and commits absent from fetched default/run/PR refs still refuse reclaim;
   this is not simply a PR-merged check. A clean published PR may remain
   open while its idle window expires under the existing retention contract.
6. Confine the exception to idle detection: `upgrade.busy()` keeps the
   `unacked()` delivery barrier (`upgrade.py:57`). A narrow helper or optional
   ignored-kind argument defaults to existing caller behaviour; prove an
   unacked policy message still blocks upgrade.

Paths: `_shared.py`, its dependent tests and a #1772 fragment; an optional
short clarification in `docs/runtimes/tmux.md`. Preserve the consumers in
`watch.py`, `dequeue.py`, `route.py` and `schedule.py`; no shared-plumbing
refactor or second reaper.

Local test selection uses the
[affected-tests policy](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6763423100),
as explicitly applied by the coordinator: run `python3 scripts/run-tests.py
 test-crew-lead.py test-crew-dequeue.py test-crew-upgrade.py test-crew-watch.py
 test-crew-route.py`. Expand lead coverage for policy messages and acks,
actionable/unknown/unidentified acks, later work status, active tools and one
expiry; dequeue coverage for real reclaim, retention, unlanded work and
pending fix/CI-red/merge-up; upgrade coverage for the unchanged policy-message
barrier. Watch and route protect expiry delivery and existing consumers.

#### B2: verdict wake identity (#1777)

The applied choice is **`(head, reset_epoch, posted_round, verdict)`**, with PR
implicit in per-PR state and the canonical review ID retained as provenance
only. It changes private wake deduplication, not marker or round-cap meaning.

1. Select the latest valid `role=reviewer-validator pass=verdict` at the full
   current head, from the configured reviewer login and visible signature
   using `signed_by()`. Keep posted round separate from next-dispatch `round`.
   Ack/review/validate/fix notes, wrong-head and foreign/unsigned records
   cannot create a signed verdict wake. Preserve profile identities in
   production poll and the existing no-profile utility mode where needed.
2. Use the logical identity above. `reset_epoch` is the latest accepted
   signed coordinator resume/cutover source, or a stable legacy/default value.
   Review ID is not an independent wake reason; existing review `id` and
   `submittedAt` suffice, with no per-verdict fetch or new marker field.
3. At unchanged head/verdict text, round 2 → round 4 `changes` emits exactly
   one `review-changes-requested` to builder. A new `pass` identity emits one
   `review-approved` to synthesizer. A signed reset followed by a reused
   round number is a fresh epoch.
4. Re-polling, repeated input or another post with the same logical identity
   emits no additional verdict wake, even with a different review ID. Keep
   canonical identity for duplicates; builder fixes/unrelated notes do not
   change it. Preserve §5's formal-verdict counting and caps.
5. Additive private `poll-state.json` fields accept legacy state without a
   profile edit. Seed missing identity fields without replaying an unchanged
   known verdict; use existing head/verdict/derived-round differences for
   the first transition, then logical identity. Preserve the baseline-only
   first poll with no previous state. Test legacy seeding and a new same-head
   round arriving against legacy state.
6. Preserve CI classification, merge-up portability, express routing, event
   names/consumers/refs, evidence-only `fix-at-head`, next-review round
   calculation and reset handling. Verdict wakes keep their builder or
   synthesizer mapping and never accidentally dispatch a reviewer.

Paths: `poll.py`, `dev/tests/environments/test-crew-poll.py` and a #1777
fragment; optional short binding clarification. Keep `route.py` consumers
and refs. Prefer inline test records over shared render-fixture edits.
Run `python3 scripts/run-tests.py test-crew-poll.py test-crew-route.py`;
add signed same-head/different-round, duplicate/new-ID, reset epoch,
irrelevant/foreign notes and legacy-state/baseline cases. Route coverage
protects consumers and reviewer replay guards. This remains latest-snapshot
sampling, not event-history reconstruction or a crash-exactly-once promise.

All four PRs run `python3 scripts/check-repo.py` and
`python3 scripts/check-changelog-pr.py`; bookends also check
`--only design-headers --only spec-status`. PR CI runs the full suite.
If templates or shared fixtures change, add the render, parity, tmux-briefs
and bootstrap tests; such growth returns to the coordinator before dispatch.

Version forecast against [Versioning](../deliverables.md#versioning): both
runtime fixes are **patch**, restoring documented behaviour; internal spec
bookends alone have **no bump**. No protocol, template or gate-contract change
is planned. Preserve §4 markers, §5 counting/caps and §7 gates; a required or
reinterpreted marker or changed gate needs replanning and major classification.
Classify the full actual diff at each head, especially B1's reclaim
eligibility; a sensitive head still needs the owner's per-change reason.
Merge permission is the owner's
[merge-ok for all M52–M54 PRs](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846545711),
recorded per PR at its actual head. It supplies permission only, never
approval, CI, hold clearance or missing AC evidence.

### M53: brief headroom and grant lifecycle

Opening spec slice #1814 and closing status-sync slice #1815 are the
bookends for [#1795](https://github.com/mw-ding/mdstack/issues/1795).
Scope and member ACs come from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1795#issuecomment-6849391872)
§2–§4, with the
[coordinator's applied choices](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6849413256).
S0 is recorded as done for this opening slice (PR #1816), effective on merge.
No member dispatches before #1814 merges. B1, B2 and L1 then build
independently in parallel; prioritize B2 if only one slot is available.
B3 follows B1's landed reference contract and requires the owner proofs below
before completion. File overlap between B1/B2 requires integrated testing,
not a semantic dependency. One issue → one PR, with small logical commits.
Bookends and B1/B2/L1 use default tier/medium effort; B3 uses deep/high.

| ID | Issue | Scope | Size | Depends on | Status | PR / evidence |
|---|---|---|---|---|---|---|
| S0 | #1814 | Opening scope, ACs, applied choices and prerequisites (PR #1816) | docs only | none | done | [PR #1816](https://github.com/mw-ding/mdstack/pull/1816) |
| B1 | #1746 | Constant-size grant lookup pointer and existing authority resolution | 30–70 Python; 25–50 prose; 100–180 tests | #1814 | done | [PR #1826](https://github.com/mw-ding/mdstack/pull/1826), [review / validation](https://github.com/mw-ding/mdstack/pull/1826#pullrequestreview-5889464177) |
| B2 | #1566 | Builder/researcher entry headroom and rendered procedure companions | 50–90 prose/registry excluding moved text; 100–170 tests | #1814 | done | [PR #1825](https://github.com/mw-ding/mdstack/pull/1825), [final review / validation](https://github.com/mw-ding/mdstack/pull/1825#pullrequestreview-5889639261) |
| B3 | #1774 | Owner-confirmed archive/prune with preservation and refusal proof | 180–280 Python; 35–60 prose; 300–500 tests | #1814, #1746; owner proofs A/B | done | [PR #1833](https://github.com/mw-ding/mdstack/pull/1833), [owner proofs A/B](https://github.com/mw-ding/mdstack/pull/1833#pullrequestreview-5898353333), [review / validation](https://github.com/mw-ding/mdstack/pull/1833#pullrequestreview-5898453431) |
| L1 | #1793 | One 24-card learning/disposition batch PR in 2–3 commits | 110–170 Markdown; no product/test code | #1814 | done | [PR #1824](https://github.com/mw-ding/mdstack/pull/1824), [review](https://github.com/mw-ding/mdstack/pull/1824#pullrequestreview-5889388989) |
| S1 | #1815 | Final statuses, decisions, lessons and tracker reconciliation | docs only | #1746, #1566, #1774, #1793 | open | [PR #1851](https://github.com/mw-ding/mdstack/pull/1851); pending land |

#### M53 outcome and lessons

S0, B1, B2, B3 and L1 are built in source. Their issues, #1814, #1746,
then #1566, #1774 and #1793, are closed in the live tracker (2026-11-13). So are
all 24 L1 source cards: #1381–#1384, #1446, #1466, #1561–#1565, #1601, the
privacy near-miss #1602, then #1696, #1732–#1734 and #1782–#1788. Each links
to its row in [docs/findings/m53-learning.md](../findings/m53-learning.md).
No card was superseded and no missing prevention stayed open. No additional
M53 build items were admitted. S1 (#1815) stays open until this sync lands;
then the tracking issue #1795 and M53 close.

- **B1 settled as applied:** a non-`none` grant renders a fixed-length
  instruction to resolve `merge_grant` live and read its named decisions;
  `none` stays literal. Short and ~96 KB historical grants render
  byte-identical output. Follow-up: the instruction names a team/repo
  context that `crew-config.py resolve` does not take.
- **B2 settled as applied:** builder fix and researcher triage procedures
  moved unchanged into `runtime/builder-fix.md` and
  `runtime/researcher-triage.md`, with the 2,048-byte entry reserve
  asserted. Round 1 went red on `test-crew-roles.py` because the
  role-registry doc example and a single-template assertion missed the new
  companion. A relocation must update every consumer that lists role
  templates, not only the renderer.
- **B3 settled as applied, with live-tracker fixes:** round 1 found that
  exact `M<n>` title matching and `v`-less cut names (`the 7.6.0 cut`) made
  every clause unreadable on this repo's real tracker. Fixtures with bare
  `M35` titles hid it. The fix also accepts titles that begin with `M<n>` and a
  space (as in `M42 — Org-pack requests`) and resolves bare versions to `v` tags. Lesson: validate a recognizer against the real
  tracker's shapes, not fixture-only shapes. Rounds 2–3 were evidence-only
  `changes` until the owner ran proofs A and B at `8650751` from their own
  terminal. After a resume, the fresh round passed. A's exit codes, the
  fixture socket log and B's `ownership --action write` output were not
  captured; the reviewer judged the saved records sufficient.
- **Amended AC5 held:** after B1, grant length no longer sizes entry briefs,
  so B3 claims no brief shrinkage from pruning.
- **L1 settled as applied:** one batch of 24 cards counts 27 incidents, with
  no new guard and no live proof claimed.

**Merged / released / installed:** S0, B1, B2 and L1 merged before the
7.12.0 cut (PR #1832) and ship in
[v7.12.0](https://github.com/mw-ding/mdstack/releases/tag/v7.12.0), published
2026-11-13. B3 (PR #1833) merged after that cut and is in no release. On the
owner's machine, the release link `~/.mdstack/releases/current` resolved to
`mdstack-7.12.0` when read on 2026-11-13. That read proves no host adoption,
and `mdstack grant prune` is not in any installed release.

**Target environment: N/A** — local runtime logic, no new platform or device
dependency. Standard flavor, tmux, Codex-first routing; reviewer selection
uses the actual builder engine. Serialize spec bookend edits/lands with
M52's closing sync and refresh `main` before each, preserving both sections.
M53 stays in this spec; no second milestone spec, portable-design rewrite
or M52 runtime change belongs here.

#### B1: grant reference (#1746)

Applied choice: a constant-size pointer to the existing resolved
`runtime.options.merge_grant`, followed by the authoritative decisions it
names. Preserve the string key and `none` behaviour.

1. A non-`none` grant renders a compact instruction to resolve the field
   live from `$CREW_PROJECT` and its configured layers, then read its named
   decisions before use. Use `core/crew-config.py resolve --project ...`
   with configured org/team context; raw project TOML is not necessarily
   effective. Quote no permission/history. `none` retains explicit per-PR
   owner merge-ok. Rendering need not query the network or grant authority.
2. The reader checks authorized attribution, exact scope, exclusions and
   later applicable revocations on the configured tool of record, and links
   the decision actually relied upon. Copied archives, narrative summaries,
   unrecognized locators, foreign/mismatched records or unreadable
   profiles/sources supply no standing permission; valid per-PR owner
   merge-ok remains the fallback.
3. Preserve `merge_grant_scope`, spec globs, ownership, sensitive/gate-contract
   exclusions, head-bound permission, CI and release approval. Add no marker,
   profile type or required backend operation. Keep `<merge-grant>` available
   to overlays and adjust bundled prose so the pointer is not quoted grant text.
4. Test `none`, ordinary/very long grants, multiple/historical references,
   layered selection and provenance wording. Compare short/long renders for
   bounded entry size; retain entry-point refusal/authority cases. A render
   proves the pointer only, not a successful live authority check.

Paths: `core/crew-render.py`, all bundled `<merge-grant>` uses (tmux
coordinator, synthesizer merge-gate/authority-sources and session text),
`docs/configuration/runtime-options.md`, render/parity/bootstrap fixtures
and tests, and a #1746 fragment. Doctor-specific preflight warnings and
release-delegation/history compaction remain follow-ups.

#### B2: entry headroom (#1566)

Applied choice: **2,048 bytes of baseline reserve** for builder/researcher
entry briefs, normalized **≤14,336 bytes** at the unchanged 16,384 default.
Keep coordinator/synthesizer's 15,360-byte assertions. This is a checked-in
baseline regression target, not a tighter installation limit for custom
budgets, prechecks or notes.

1. Replace inline builder fix-round procedure with a mandatory pointer to
   rendered `runtime/builder-fix.md`, including existing
   `policy/builder/fix-rounds.md`. Preserve fix/ci-red, base-update, express
   self-gate, step-summary and PR conventions. Load it for fix/ci-red/base-update
   or express self-gate, including an initial express build; unreadable means
   stop/report.
2. Replace inline researcher triage with a mandatory triage-sweep pointer to
   rendered `runtime/researcher-triage.md`, including unchanged
   `policy/researcher/triage-sweep.md`. Keep Scope/Evidence/Output and the short
   docs-pass procedure inline; keep reflection's existing pointer.
3. Both pointers name `$CREW_STATE/render/runtime/<file>`, not raw fragments
   with unresolved operation/profile tokens. Register companions in
   `roles/eng/builder.toml` and `roles/eng/researcher.toml` for role-runtime
   replacement and disabled-role omission. At researcher cap 0, neither its
   companion nor its operations is required.
4. Always load ownership/live-state/holds, flavor, actual-engine signing,
   body/scratch placement, evidence/negative-control duties, main build steps,
   heartbeat, inbox ack/stale-head stops, train boundary, `done:`/`blocked:`
   lifecycle and no-owner-ask/no-land rules. Move only triggered procedure
   bodies with identical permission and marker semantics.
5. Assert the entry ceiling at short/long installation paths; role-owned
   companions keep ordinary `size_budget`. Preserve normalized/delivered
   diagnostics and memory/note handling. An added-prose mutant fails the
   regression; restoration passes. Instruction-presence/lint checks inspect
   the entry plus its companion at the trigger, retaining triage/express checks.
6. Preserve fragment-edit sentinel parity; prove rendered commands/tokens,
   disabled roles, missing-reference handling and reachability. Update the
   triage skill's section pointer. No renderer rewrite or new lazy-loader.

Paths: tmux builder/researcher and new companion templates, the two role
registries, triage skill pointer, render/bootstrap/brief and role-registration
tests with matching goldens, and a #1566 fragment. Shared policy bodies and
`docs/protocol.md` need no behavioural edit. Separate relocation/metadata
from coverage in logical commits; moved text can exceed the line estimate.

#### B3: conservative pruning (#1774)

Applied choice: deterministic recognition of whole clauses in the existing
string; keep ambiguous clauses. `mdstack grant prune --dry-run` previews;
application needs an attended owner shell and explicit confirmation.

1. Remove only recognized finite scopes with identifiable source records.
   Every named milestone must be closed and every named cut must have a
   non-draft published release; mixed clauses require all scopes finished.
   Item closure/cut-PR merge is insufficient. Keep standing/open/unknown/
   partly-finished clauses, §7/sensitive restrictions, archive annotations and
   mixed boundaries. Split only at safe top-level boundaries, never commas
   inside archived milestone lists. Read exact named scopes; any unreadable
   tracker/release/source response keeps everything with a reason.
2. Dry-run lists removed/kept clauses, reasons and source links with no write,
   backup or archive post. Refuse role-launched/noninteractive application
   and unattended `--yes`. `down --keep-grant`, noninteractive `down` and
   `down --preserve` skip pruning while retaining shutdown behaviour.
3. Preview/confirmation precedes shutdown effects; decline keeps the grant
   and continues ordinary shutdown. Affirmative pruning passes shutdown
   blockers, stops writers and completes teardown before authority changes.
   A stop/retention refusal cannot prune. Immediately before archive/write,
   re-read ownership for `write`, profile and all scope/source facts; refusal
   or changed preview requires a new attempt. Keep pause, watcher, land-lock
   and unlanded safeguards.
4. Edit only a uniquely located `merge_grant` owned by the explicitly selected
   writable project file. Keep/refuse inherited org/team grants or unsupported
   TOML with a reason, never materializing an override. Support the documented
   single-string representation conservatively; preserve other bytes and
   exact kept clauses. Reparse/check no authority widened or other effective
   value changed.
5. Take a collision-safe timestamped byte-for-byte backup under
   `<state-dir>/runs/` with a non-JSON extension. Post one signed owner-triggered
   archive to the configured decision log: removed clauses verbatim,
   source/finished-state links and before/after identity. It is history with
   no grant/steer/gate marker. Confirm archive success before atomic replacement
   and compare original bytes again. Backup/archive/write failure leaves the
   profile intact; uncertain posts require read-back reconciliation, not
   blind reposting. An archived but refused write is a historical attempt.
6. Test shipped commands for finished/mixed scopes, standing/open/unknown/
   annotations, unreadable state, layered/unsupported profiles, role and
   noninteractive refusal, decline/opt-out/preserve, ownership loss,
   backup/archive/write failures, concurrent edits and repeated no-op.
   Retain shutdown lock/watcher/pause/unlanded cases. Positive proof shows
   archive-before-replacement, recoverable backup and exact untouched
   keys/restrictions. Unsupported decision-log/scope bindings refuse;
   use existing ownership/backend helpers, no new connector requirement.
7. **Amended #1774 AC5:** after B1, grant length no longer sizes entry briefs.
   Prove the long historical fixture renders within budget before and after
   pruning and preserves B2's static headroom. Do not claim pruning shortened
   constant-size pointers or waive the budget.

Paths: new `environments/terminal/crew.d/grant.py`, `down.py`, shared write
inventory in `_shared.py`, grant/down usage in `docs/runtimes/tmux.md`, new
grant tests plus down/pause/ownership tests and a #1774 fragment. Use roughly
three logical code commits with tests (recognizer, transaction, down
integration). General TOML rewriting and structured grants stay follow-ups.

**Owner prerequisites — proofs A and B, after B3 builds:** reserve one attended
owner slot in a separate ordinary shell at a coordinated safe stop. No proof
has run here; current standing-only live scope cannot prove positive removal.

- **A, disposable positive prune.** Builder supplies concrete absolute CLI,
  profile, stub-bin and forge-fixture paths plus a complete executable recipe:
  isolated profile/state/fake forge/fake tmux, signed sandbox sources, closed
  milestones/published cuts, standing/open/unknown/protected clauses. Unset
  `TMUX`, `TMUX_PANE`, `CREW_ROLE` and `CREW_ID`; pin every destructive tmux
  operation to `-S <sandbox-socket>` (`TMUX_TMPDIR` alone is insufficient).
  Owner runs `grant prune --dry-run`, then plain `down`, types confirmation
  and captures exit/output, archive read-back, backup and grant-only diff.
  Add no historical text to the live profile.
- **B, live preservation/opt-out.** Select the built/installed CLI and actual
  owner profile; sequentially run `ownership --action write`,
  `grant prune --dry-run` and `down --keep-grant`, each with `--project`.
  Stop on refusal. Dry-run keeps standing scope, restrictions and archive
  annotation; opt-out changes no profile/authority. Restart is a scheduled
  coordinator follow-up. B3 stays open until human-confirmed positive `down`
  proof and preservation/refusal evidence are inline on its change; automated
  yes-input tests or standing-only no-ops are insufficient.

#### L1: learning capture (#1793)

Applied choice: one bounded batch document/PR in 2–3 logical commits.

1. Give every one of #1793's 24 source IDs a row: class, source/repair PR,
   retained test/procedure path at head, later occurrence/count, uncertainty
   and explicit lesson/findings disposition. Link cards and reuse applicable
   lessons; the PR closes #1793 alone.
2. Retain #1446's #1368/#1527 and #1565's #1528/#1592/#1719 occurrences.
   Count incidents, not repeated comments/triage. Distinguish #1466's
   synthetic credential near-miss from established exposure and #1602's
   log-path disclosure from secret exposure.
3. For #1696, retain normal-runner discovery checks: definitions precede
   main invocation and normal-run output/count includes added classes/cases,
   not merely imported selection. Build no new general discovery guard.
4. Missing prevention stays an open separately named work unit. After merge,
   coordinator closes only fully captured/dispositioned cards. Claim no live
   campaign proof or new product fix; #1788 retains migration procedure,
   not session-adoption implementation.

Paths: proposed `docs/findings/m53-learning.md`, appropriate short buffer/index
pointer, applicable existing lessons only, and a #1793 fragment. Compare all
24 IDs/links and disposition/occurrence rows directly with sources; these
are capture records, not committed runtime evidence or a source dump.

#### Checks, forecast and closing

All six PRs run `python3 scripts/check-repo.py` and
`python3 scripts/check-changelog-pr.py --base origin/main`; bookends also run
`check-repo.py --only design-headers --only spec-status`. Local selection
follows the owner's standing
[affected-tests policy](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6763423100),
explicitly applied to M53: shared plumbing does not require a full local suite.
B1 covers render/parity/tmux-briefs/bootstrap and affected authority consumers;
B2 adds role-registration/roles coverage, and drift/install tests only if
those behaviours change. B3 covers grant/down/pause/ownership and touched
dependents, plus render/bootstrap for long-grant integration. Template/fixture
changes retain all four render/parity/brief/bootstrap tests. L1/bookends need
guards and source comparison, no Python test for prose alone. Each PR lists
its selection/results and coverage; **PR CI runs the full suite**. New guards
need accepted/refused entry-point proof; headroom needs fail-then-pass proof.

Forecast against [Versioning](../deliverables.md#versioning): B1 **patch**
(templates and authority-source presentation, gate-contract-adjacent), B2
**minor** (new rendered procedure templates/role registry, relocated authority
instructions), B3 **minor** (new command/flag, likely `crew:sensitive` for owner
authority removal), L1 **none** (internal capture), spec-only S0/S1 **none**.
Deliverable status wording in S1 is patch if needed. Forecast M53 as minor,
not a release cut/version choice. A new required grant schema, changed §7
satisfaction, marker meaning, installation limit, old exit/parsed-output or
flag contract needs major replanning before implementation. Classify every
actual full diff at head; B3 requires the owner's per-change sensitive reason.

S1 records landed PR/proof references, settled choices, lessons and tracker
reconciliation for members and completed L1 cards. Explicit supersession
requires a settled disposition. Distinguish merged, released and installed;
update README Status/binding/design headers only where truth changed. S1/M53
stay open with missing B3 owner proof or any unfinished member. Merge
permission is the owner's
[merge-ok for all M52–M54 PRs](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846545711),
recorded per PR at its actual head; it supplies no approval, CI waiver,
hold clearance, sensitive reason or missing AC proof.

### M54: coordinator helper surfaces

Opening spec #1819 (S0) and closing status sync #1820 (S1) bookend
[#1796](https://github.com/mw-ding/mdstack/issues/1796). Scope, member ACs,
size estimates and test selection come from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1796#issuecomment-6849761412),
§2–§5, with D1–D4
[applied by the coordinator](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6849853362)
and the [member AC refresh](https://github.com/mw-ding/mdstack/issues/1796#issuecomment-6849862577).
These are additive command surfaces over the existing runtime; one issue
gets one PR, with focused commits. Runtime module paths below are under
`environments/terminal/crew.d/`. Estimates exclude tests and are planning
ranges, not limits; member work is default/medium except B2, deep/high.

| ID | Issue | Scope | Size (Python; docs/templates) | Depends on | Status | Version | PR / evidence |
|---|---|---|---|---|---|---|---|
| S0 | #1819 | Opening spec and applied choices | 100–170 docs | none | done | none | [PR #1822](https://github.com/mw-ding/mdstack/pull/1822) |
| B1 | #237 | Additive issue brief and checked marker acks | 180–280; 50–90 | #1819, #1566, #1746 | done | minor | [PR #1834](https://github.com/mw-ding/mdstack/pull/1834), [review / validation](https://github.com/mw-ding/mdstack/pull/1834#pullrequestreview-5890873205) |
| B2 | #238 | Review, verdict and recheck commands | 250–400; 60–100 | #1819, #1566, #1746, B1 posting contract | done | minor | [PR #1838](https://github.com/mw-ding/mdstack/pull/1838), [review / validation](https://github.com/mw-ding/mdstack/pull/1838#pullrequestreview-5891895807) |
| B3 | #239 | Mechanical local merge-up and signed note | 160–250; 40–70 | #1819, #1566, #1746, B1 posting contract | done | minor | [PR #1837](https://github.com/mw-ding/mdstack/pull/1837), [review / validation](https://github.com/mw-ding/mdstack/pull/1837#pullrequestreview-5892054638) |
| B4 | #369 | Coordinator scratch cleanup and unused import | 15–35; 5–15 | #1819, #1566, #1746 | done | patch | [PR #1831](https://github.com/mw-ding/mdstack/pull/1831), [review / validation](https://github.com/mw-ding/mdstack/pull/1831#pullrequestreview-5890057874) |
| S1 | #1820 | Status, evidence, lessons and tracker sync | 35–70 docs | B1–B4 | open | none | [PR #1840](https://github.com/mw-ding/mdstack/pull/1840); pending land |

S0 can be prepared while M53 builds. All members wait for S0 and M53
items #1566 and #1746 to land. B1 and independent B4 start first; B2/B3 may prepare against
B1's specified posting interface but integrate after it lands. B3 has no
B2 dependency. S1 lands last, linking member PRs/evidence, recording settled
questions and lessons, and confirming landed/superseded tracker items are
closed. Preserve M52/M53 spec rows and #1774's shutdown branches. The
7.12.0 cut (#1817 / PR #1818) temporarily holds fragment-bearing lands.
Codex-first builders continue until the separate installation/upgrade;
reviewer routing excludes the actual builder engines.

#### Delivered outcome and lessons

S0 and B1–B4 are built in source; #1819, #237, #238, #239 and #369
are closed in the live tracker (2026-11-13). No additional M54 build items
were admitted. S1 (#1820) stays open until this closing sync lands;
M54 closes afterward. M53's #1774 later landed separately in PR #1833.

- **D1 settled:** the existing fresh reviewer/validator pipeline supplies
  the sections; the checked COMMENT poster assembles them at H/k and
  reconciles tags. Helpers add no approval or evidence authority (PR #1838).
- **D2 settled with a narrower steer set:** issue mode is additive and
  legacy run-block/inbox output stays intact. Receipt-only steering acks
  accept only `hold` and `escalate`; effect-bearing commands, including
  resets and `merge-ok`, refuse. This supersedes the broader recognized-command
  wording below, per the [consumer-safety clarification](https://github.com/mw-ding/mdstack/issues/237#issuecomment-6851108497).
  A receipt marker can trigger consumers even when its writer performs no
  action; classify its downstream effects before calling it an ack.
- **D3 settled:** the builder owns clean/configured-driver merge-ups;
  conflicts restore the prior head and posted notes use backend head readback.
  PR #1837's second round restored pre-push rollback after a moved head;
  approval carry remains the synthesizer's strict content comparison.
- **D4 preserved:** no protocol, gate predicate, marker schema, grant scope
  or approval-power change. #369 now retains symlinks and directories and
  documents cleanup; grant archives and #1774's branches remain intact.
  Integrated checks complement fake-backend refusal proof; neither proves
  live adoption, and full CI remains required.

**Release / installation:** B1–B3 are additive minor command surfaces; B4
is patch. All four landed after the 7.12.0 cut (PR #1832), so that release
contains none of them. Source completion supplies no live install/upgrade
or sensitive permission.

#### Applied decisions and acceptance criteria

**D1 / B2 (#238):** `mdstack verdict` consumes completed Review/Validation
sections and posts one checked COMMENT review at pinned head H under this
single-identity binding. It runs neither pass and invents no evidence.
Existing markers retain PR, full head H, reviewed base B, positive round k,
actual results and actual-author signature/usage. A complete verdict has
three section/final markers; review-only changes has two, with
`skipped: review failed` and no validation session. A legitimate flavor skip
still has a Validation section and its existing skipped-validation marker.
Pass requires both passes or an eligible skip; failed validation is changes.

1. `review` explicitly hands H/k to the existing reviewer lead, preserving
   admission, claims, freshness, precheck, flavor and actual-builder-engine
   exclusion. Passing review starts separate fresh validation when required;
   review changes produces the existing changes verdict. The coordinator
   model runs neither pass.
2. `verdict` refuses missing/duplicate sections or markers, inconsistent
   results, short/unavailable SHAs, wrong PR/head/base/round, an ineligible
   skip, wrong actor, an already-completed pass or obsolete reset/rereview
   binding. Re-read ownership and live head, bind the native review to H,
   and produce no review/tag effect on refusal. After acceptance, perform
   and read back existing approved/changes tags, holds and cap handling.
   Install any required mirror hold first; reconcile a lost response by
   readback before retrying.
3. `recheck` exposes the existing explicit fresh pass for a two-parent
   merge: first parent previously approved H, second on default branch,
   same approval round, bounded remerge hunks and acceptance checks.
   Broader/unconfirmed content or an open full-rereview steer uses the
   existing normal escalation path. Being behind alone never dispatches it;
   clean-update portability remains the default.
4. Fake-backend/fake-harness process tests prove session order/freshness,
   engine exclusion, duplicate suppression, D1 refusals, valid skip, failed
   validation → changes, caps and explicit recheck/escalation. Fragment and
   green CI are required.

Paths: new `review.py`, `verdict.py`, `recheck.py`, B1's posting helper;
compact tmux coordinator/reviewer pointers; `docs/runtimes/tmux.md` and
`docs/release.md`. Reuse the current pool/route passes and native head-bound
mapped posting operations, without another pipeline or forge client.

**D2 / B1 (#237):** add `mdstack brief --issue …` and marker-posting
`mdstack ack` modes. Inbox receipt remains `mdstack action ack` / `acked`.

1. Issue mode prints resolved rendered role instructions, live issue
   reference/title and delimited task/AC data, launch notes and the existing
   run block. Validate role/tier/engine/run fields and unavailable inputs;
   print no partial brief, stale identifiers or unfilled required fields.
   Issue text is task data. Create no claim, worktree or session; preserve
   existing brief flags, byte output, exits and `run_block` callers.
2. `intake`: actual reviewer, non-draft round 1 after live-state/precheck
   and engine checks, once at H; existing ack marker, n/a round/result,
   no approval or tag change. `merge-up`: actual reviewer, verified clean
   update after changes; retain unresolved findings, without substituting
   for a passing verdict or portable approval.
3. `steer`: actual coordinator, verified owner source and recognized command,
   once per source `cmd-id`; existing steer marker at H with n/a round/result.
   It acknowledges without executing, resetting rounds or clearing a hold;
   apply command-specific hold exceptions. Generic ack refuses `merge-ok`:
   authorization stays in the owner-decision/dispatcher path.
4. Every mode validates live actor/source/head/phase and ownership, signs the
   actual author and is idempotent at its existing identity key. Invalid,
   short, stale, foreign or missing input has no posting effect. Process
   tests cover output/posts, missing inputs, intake/duplicate intake,
   merge-up after changes, wrong source/head/role and unchanged inbox
   delivery. Fragment and green CI are required.

Paths: `brief.py`, new `ack.py`, a small private `_helper-posts.py` shared
only by the three concrete posters; runtime/release docs and compact tmux
reviewer pointer. Reuse #224's discovered per-command modules; no entry-point
or core config/render rewrite or generic workflow framework.

**D3 / B3 (#239):** local Git merge-up uses only declared merge drivers,
with no automatic feature-conflict resolution. The actual builder/operator
owns the target copy; the coordinator dispatches that actor.

1. Refuse another writer's active run/copy claim, dirty tracked/untracked
   work, an in-progress Git operation, wrong branch/repo/head, held/closed/
   escalated PR, unavailable ownership or rebase update strategy. The
   caller's associated run is not a competing writer. Preserve H and work
   on every pre-push refusal.
2. Fetch via existing private refs, pin old H and updated base U; current is
   exit-0/no note. Merge clean/configured-union cases; unresolved conflict
   aborts and restores H without push/post. Add no union attributes. Never
   rebase, force-push, squash or approve. Re-read live H before a normal
   push to the verified branch, then read the authoritative published head.
3. Post one signed actual-actor `pass=merge-up` note at that head, n/a
   round/result, with B/H/U/new-head, merge/union paths, strict content
   comparison and targeted checks. Approval carry stays with the
   synthesizer; differing content/union rewrites require delta review.
   Report a pushed head whose note failed for readback/reconciliation,
   without pushing again.
4. Disposable-Git/fake-backend process tests cover current no-op, clean and
   configured-union merges, rewrite/differing-content routing, conflict
   rollback, busy/dirty/strategy/claim refusal, moved backend head and
   push/post failures. Fragment and green CI are required.

Paths: new `merge-up.py`, B1's helper, reused `content.py`, runtime/release
reference and M53's tmux `builder-fix.md` companion.

**B4 (#369):** after successful plain `down`, including already-not-running,
sweep only regular scratch files in `runs/coordinator.*`. Refusal and
`--preserve` retain them. Follow no symlinks; retain worker records, claims,
inbox/status, grant archives and every other prefix. Remove only unused
`runs` from `guard.py`; preserve guard behavior and #1774 shutdown/pruning.
Tests cover success/no-session/repeated cleanup, refusal/preserve, unrelated
retention and existing stop-order/land-lock/watcher cases; guard tests,
fragment and green CI remain required. Paths: `down.py`, `guard.py` and the
runtime state-file row. Shipped #420/#437/#392 work stays outside scope.

**D4:** no edits to protocol behavior, gate predicates, marker schema,
grant scope or approval power. COMMENT, ack, CI and helper success gain no
approval authority. Dual-identity formal posting, adjacent parser/pipeline
hardening, union expansion and live install/trust/upgrade are follow-ups.
Against [Versioning](../deliverables.md#versioning), B1–B3 are minor, B4
patch, internal spec bookends none. A changed gate satisfaction/marker
meaning, required new field or replaced brief output needs replanning and
major classification before dispatch.

#### Brief budgets, flags and verification

| Member | Rendered change | Maximum net entry growth | Status |
|---|---|---| --- |
| B1 | Generated task output; compact reviewer ack pointer | Reviewer ≤100 bytes; other entries 0 | done |
| B2 | Replace coordinator lead handoff; extend reviewer pointer | Coordinator ≤0; reviewer ≤150 additional bytes; others 0 | done |
| B3 | Builder-fix companion invocation and reference | Entries 0; companion about 100–200 bytes | done |
| B4 | Runtime state-file description only | Entries 0 | done |

After M53, measure integrated normalized UTF-8 renders: builder/researcher
≤14,336 bytes at the unchanged 16,384-byte budget (2,048 reserve),
coordinator/synthesizer keep the existing 1,024-byte fixture reserve,
reviewer ≤16,384 with combined growth ≤250 bytes. Baseline live free bytes
were coordinator 786, builder 58, reviewer 1,648, researcher 13 and
synthesizer 978; shipped coordinator had only 8 bytes beyond its reserve.
These are readiness measurements at `4d807440f521b5f602b3b53e8b7361a9ee3c441f`,
not post-M53 evidence. Retain all always-loaded duties, keep long command
reference in docs, and report delivered task data, launch notes/core memory
and run-block sizes separately. Consuming new builder/researcher reserve
needs an explicit coordinator AC change.

Integrated measurement at `73a23b531a348a6bc35635979f64f6a05c251878`
(2026-11-13): production renderer, `profiles/tmux.toml` example fixture,
normalized paths, UTF-8 bytes; baseline is post-M53 `e6c4e621`.

| Entry | Integrated bytes | Free of 16,384 | M54 delta | Required reserve | Status |
|---|---|---|---|---|---|
| Coordinator | 15,319 | 1,065 | −23 | 1,024 | done |
| Builder | 9,652 | 6,732 | 0 | 2,048 | done |
| Reviewer | 14,910 | 1,474 | +179 | Combined growth ≤250 | done |
| Researcher | 4,552 | 11,832 | 0 | 2,048 | done |
| Synthesizer | 15,264 | 1,120 | 0 | 1,024 | done |

All envelopes pass. B1 adds 65 reviewer bytes; B2 adds 114 and removes
23 coordinator bytes. Separately loaded companions: builder-fix 7,519
bytes (+153); researcher-triage 12,104 (unchanged). Task data, launch notes,
core memory and run block each contribute 0 bytes in this normalized
fixture: they are excluded, not measured live-delivery sizes. Their delivered
sizes vary by issue, profile, memory revision and run fields; no fixture
headroom claim applies to the complete live prompt.

| Unit | Protocol / gates | Templates / budget | Sensitive / owner-shell | Status |
|---|---|---|---| --- |
| S0/S1 | Existing contract only | No new entry; truthful headers if needed | Spec permission at head; no shell step | open |
| B1 | No gate/marker change | Compact reviewer pointer; additive task output | Path forecast no match; fake backend | done |
| B2 | Existing checked writer only | Coordinator replacement/reviewer pointer | Deep head/round/identity review; fake harness | done |
| B3 | No approval carry by helper | Builder-fix companion only | Disposable Git boundary tests | done |
| B4 | No protocol/grant lifecycle change | No entry change | Disposable state; isolated tmux | done |

All members apply ownership, pause, config attribution and item holds even
for new command names. Reclassify every actual full diff, including tests
and helper paths: readiness's paths-only no-match forecast is not content
classification. A sensitive head still needs the owner's per-change reason.
**Target environment: N/A** — existing local Git/tmux; no new platform,
account, device, host, credential, trust-config or owner-shell prerequisite.
Merge permission is the owner's
[merge-ok for all M52–M54 PRs](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6846545711),
recorded per PR at each actual head; it supplies no CI waiver or AC proof.

Every build runs `python3 scripts/check-repo.py` and
`python3 scripts/check-changelog-pr.py --base origin/main`; bookends also
check `--only design-headers --only spec-status`. Use
`python3 scripts/run-tests.py <selected names...>` under the
[affected-tests policy](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6763423100).
Refusal proof invokes shipped commands and asserts nonzero exit and no
effect. Tests below are planned coverage, refined to each actual diff;
`done` records accepted member completion from the linked reviews, not a
claim that every forecast test was rerun locally;
full PR CI at exact head and integration stays required.

| Unit | Affected local tests | Coverage | Status |
|---|---|---| --- |
| S0/S1 | Required checks; `test-check-repo.py` only if checker behavior changes | Spec cells, links, fragment and truthful headers | open |
| B1 | `test-crew-brief.py`, `test-crew-spawn.py`, `test-crew-acked.py`, `test-crew-action.py`, `test-crew-send.py`; new `test-crew-ack.py` | Run composition, inbox compatibility, checked posts/refusals | done |
| B2 | New `test-crew-review.py`, `test-crew-verdict.py`, `test-crew-recheck.py`; `test-crew-reviewer-pool.py`, `test-crew-route.py`, `test-crew-spawn.py`, `test-crew-poll.py`, `test-crew-lead.py`, `test-crew-schedule.py`, `test-crew-content.py`, `test-crew-train.py`, `test-crew-precheck.py` | Fresh pass chaining, engines, admission, rounds/duplicates, utility dependents, portability/precheck | done |
| B3 | New `test-crew-merge-up.py`; `test-crew-content.py`, `test-crew-copy-claim.py`, `test-crew-route.py`, `test-crew-train.py`; ack/verdict tests if helper changes | Git rollback, copy ownership, head readback and delta/carry consumers | done |
| B4 | `test-crew-down.py`, `test-crew-guard.py`, `test-crew-pause.py`, `test-crew-migrate.py`, `test-crew-uninstall.py`; integrated #1774 tests | Cleanup/refusal/preserve boundaries, stop order and grant preservation | done |

Template/fixture edits add `test-crew-render.py`, `test-render-parity.py`,
`test-tmux-briefs.py`, `test-crew-bootstrap.py`. Shared plumbing or reused
dispatchers add affected direct/dependent tests; new write guards add
ownership/pause tests. Preserve one PR per issue and refresh stale member
ACs through the coordinator; never silently waive a full-local-run AC or
reuse #238's old multi-PR wording.

### M55: runtime routing repairs

Opening spec slice #1847 (S0) and closing status-sync slice #1848 (S1)
bookend [#1846](https://github.com/mw-ding/mdstack/issues/1846). Scope,
member ACs, sizes and test selection come from
[Riley's readiness pass](https://github.com/mw-ding/mdstack/issues/1846#issuecomment-6865558054)
§2–§6, with D1–D4
[applied by the coordinator](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6865577362)
and the [member AC refresh](https://github.com/mw-ding/mdstack/issues/1846#issuecomment-6865588755).
Runtime module paths below are under `environments/terminal/crew.d/`;
`path:line` citations refer to base `f8d3d5a62cc08b1945b394c55a3743e90c310644`.
S0 is recorded as done for this opening slice (PR #1849), effective on merge.
No member dispatches before #1847 merges. Order: B1 → B2 → B3 → S1; L1 runs
after S0 beside the repairs. B1–B3 share route/wait consumers, so the order
reduces integration churn; it is not a semantic dependency except B2's
integrated wait/resume acceptance on B1. One issue → one PR, with focused
commits. Estimates exclude tests and are planning ranges, not limits.

| ID | Issue | Scope | Size (Python; docs/registry) | Depends on | Version | PR / evidence | Status |
|---|---|---|---|---|---|---|---|
| S0 | #1847 | Opening scope, ACs, D1–D4, allocation, flags and test matrix (PR #1849) | 80–130 docs | none | none | [PR #1849](https://github.com/mw-ding/mdstack/pull/1849), [review](https://github.com/mw-ding/mdstack/pull/1849#pullrequestreview-5898517490) | done |
| B1 | #1836 | Reproduced held-id wait repair | 40–100; 10–25 | #1847 | patch | [PR #1865](https://github.com/mw-ding/mdstack/pull/1865), [round 2 review / validation](https://github.com/mw-ding/mdstack/pull/1865#pullrequestreview-5899616033) | done |
| B2 | #1835 | Signed permission-change wake | 70–130; 15–30 | #1847; #1836 for integrated wait/resume acceptance | patch | [PR #1867](https://github.com/mw-ding/mdstack/pull/1867), [review / validation](https://github.com/mw-ding/mdstack/pull/1867#pullrequestreview-5900285513) | done |
| B3 | #1830 | Item-tier resolution and launch preservation | 100–180; 25–50 | #1847; integrate against #1836/#1835 | minor | [PR #1868](https://github.com/mw-ding/mdstack/pull/1868), [round 2 review / validation](https://github.com/mw-ding/mdstack/pull/1868#pullrequestreview-5901450160) | done |
| L1 | #1813 | One retained learning record | 25–45 docs | #1847 | none | [PR #1852](https://github.com/mw-ding/mdstack/pull/1852), [review](https://github.com/mw-ding/mdstack/pull/1852#pullrequestreview-5898806445), [m55-learning.md](../findings/m55-learning.md) | done |
| S1 | #1848 | Status, evidence, decisions, lessons and tracker reconciliation | 35–70 docs | #1847, #1836, #1835, #1830, #1813 | none | [PR #1869](https://github.com/mw-ding/mdstack/pull/1869); pending land | open |

#### M55 outcome and lessons

S0, B1, B2, B3 and L1 are built in source. Their issues (#1847, #1836,
then #1835, #1830 and #1813) are closed in the live tracker (2026-11-13),
and L1's record is [docs/findings/m55-learning.md](../findings/m55-learning.md). No
row was superseded and no additional M55 build items were admitted. S1
(#1848) stays open until this sync lands; then the tracking issue #1846 and
M55 close.

- **D1–D4 built as applied:** each member PR implements its decision as recorded.
- **B1 settled as applied, with a reproduced mechanism:** the repeated ack
  was not the cause. `reviewer-pool` acked and skipped a held id without a
  typed wait, and the lead's wait fingerprint woke the parked id on poll
  catching up on a label already seen live and on mergeability churn. The
  dispatcher now writes the wait and the fingerprint takes only PR state,
  head, CI, holds, owner answers and the ask. Round 1 went `changes`: the
  fixture covered direct `review` and durable `work` but not the
  `validate`/`recheck` handoffs the AC enumerated. Lesson: when an AC lists
  handoff kinds, the fixture covers each one by name. Follow-up: route's
  held-work return for the builder and synthesizer leads is unchanged.
- **B2 settled as applied:** an authenticated, head-pinned
  `merge-ok-recorded` poll event reaches the synthesizer through the durable
  land handoff; passed round 1. Follow-up: route's existing `ci-passed`
  merge-ok check still accepts an unauthenticated coordinator-role marker.
- **B3 settled as applied:** spawn resolves explicit `--tier`, then the
  item's `tier=`, then the role default, and queue and run records keep it.
  Round 1 went `changes`: the field regex dropped an empty `tier=`, so a
  malformed present tier fell back to the default instead of refusing.
  Lesson: a parser for an optional field distinguishes absent from empty.
- **L1 settled as applied:** one near-miss caught by CI before merge,
  recorded `applied`; no new guard and no live proof claimed.

**Merged / released / installed:** S0 (PR #1849) and L1 (PR #1852) are
docs-only. B1 (PR #1865), B2 (PR #1867) and B3 (PR #1868) merged after the
[v7.12.0](https://github.com/mw-ding/mdstack/releases/tag/v7.12.0) cut, and
no later release exists, so none of the three repairs ships yet. On the
owner's machine, `~/.mdstack/releases/current` resolved to `mdstack-7.12.0`
when read on 2026-11-13, so the running crew has none of them. The three
workaround clauses in `memory/roles/coordinator.md` (explicit deep tier,
hand-off of land after merge-ok on green CI, lead settling held ids) are
therefore kept: they are fixed in source but not installed. Removing them
needs an installed release containing PRs #1865, #1867 and #1868, then a
reviewed memory PR. Keep passing `--tier deep` explicitly until B3 ships.

**Target environment: N/A** — existing local runtime and disposable
fake-forge/process fixtures; no new platform or device requirement.
Standard flavor, tmux lane. B1–B3 use deep tier/high effort, passed as an
explicit `--tier deep` at dispatch until B3 is installed; L1 and both
bookends use default tier/medium effort. Execution choice: Claude Code
builders first
([c6865476254](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6865476254)),
superseding the readiness pass's Codex-first line; reviewer selection
excludes the actual builder engine. M55 stays in this spec; no second spec,
portable-design rewrite, #1717 permission portability, #1774 proof change
or M56 scope belongs here.

#### Applied decisions

- **D1 (#1830):** optional `tier=` on signed `pass=flavor` records,
  resolved independently of flavor. Spawn selects centrally: explicit
  `--tier`, then the item's tier, then the role default; queue and run
  records keep the selection. No new helper command or parsed output.
- **D2 (#1835):** a signed, head-pinned `merge-ok-recorded` poll event to
  the synthesizer. It is a reason to re-read gates, never approval, hold
  clearance or a CI waiver.
- **D3 (#1836):** after a production-path reproduction, the dispatcher
  writes the existing typed wait after ack and keeps the id; it resumes on a
  fingerprint change. Re-send only genuinely new work or explicit
  coordinator recovery.
- **D4 (#1813):** one docs-only learning PR; S1 links it.

#### B1: held-id wait (#1836)

Source finding: a repeated ack does not invalidate a correctly typed earlier
wait (`lead.py:207`, `lead.py:222`), but `reviewer-pool` acks every pending
request and skips held/escalated direct handoffs without a typed wait
(`reviewer-pool.py:102`, `reviewer-pool.py:137`); route's held-work return can
leave a durable work event pending (`route.py:613`). This is a candidate
mechanism; the incident's exact cause is unconfirmed.

1. First retain a failing production-path fixture: inbox handoff →
   `reviewer-pool` ack/live-hold decision → route where applicable →
   watcher/lead backstop, for direct review/validate/recheck and durable
   `work` messages. Record the exact missing/wrong wait or changed
   fingerprint; do not assume an appended ack alone is the cause.
2. For a live owner/hold-blocked ref, the dispatcher writes
   `waiting: #N owner|hold id=ID` after ack, with the actual inbox id, and
   keeps it pending. Re-running dispatch or another ack does not rearm an
   unchanged wait; unrelated actionable ids continue. `done: ID` stays for
   dispatched/completed or obsolete work, not an unresolved hold.
3. Unchanged held state across the reported fifteen-minute interval, normal
   lead backstops, slot release, coordinator backstop and lead/watcher
   restart produce zero re-nudges of the parked id. Keep admission-deferral
   timing and delivery/restart caps.
4. Owner answer, hold release, PR/head/CI change or ask change makes the
   retained id actionable; the dispatcher re-reads live eligibility and
   parks again if still held. A new handoff stays independently actionable.
   Moved/closed work retires; no hold is cleared and no duplicate worker
   starts. Keep the missed-event recovery test.

Paths: `reviewer-pool.py`; `lead.py` only if the reproduction proves a reader
gap; `templates/runtimes/tmux/reviewer-lead.md` and, if needed,
`templates/policy/shared/lead-waits.md`; `docs/runtimes/tmux.md`. The fix
follows the reproduced path and does not broadly suppress acked ids.

#### B2: permission wake (#1835)

Source finding: PR snapshots carry verdict identity but no permission
identity (`poll.py:167`), and owner-answer reads cover only held/asked refs
(`poll.py:180`, `poll.py:225`), so an already-green, unheld PR can gain
permission without a land event.

1. Diff an authenticated coordinator merge-ok identity at the PR's current
   full SHA, using the existing `pass=steer cmd=merge-ok` record. Emit one
   `merge-ok-recorded` event to the synthesizer when a new valid identity
   appears, including when CI was already green. Duplicates and unchanged
   polls emit none; prose, other authors, malformed markers and other-head
   records emit none. Scope identity by repository/PR/head/source command;
   never transfer permission across heads (protocol §7, Merge permission).
2. Register the event with the synthesizer role and route it through the
   existing durable land handoff. Permission before CI may trigger a gate
   check/wait; the later CI transition still retries.
3. Fake-forge proof starts with the green head's CI event consumed, posts
   permission, polls/routes and observes one synthesizer work request.
   Replay and simultaneous approval/CI/permission wakes reconcile to at most
   one land of that head. Cover stale head, held/closed PR,
   permission-before-CI and restart/legacy state seeding. First startup
   stays baseline plus recovery sweep.

Paths: `poll.py`, `route.py`, `roles/eng/synthesizer.toml`,
`docs/runtimes/tmux.md`, and the event list in
`templates/runtimes/tmux/synthesizer-lead.md`.

#### B3: item tier (#1830)

Source finding: the lead build recipe omits `--tier`
(`templates/runtimes/tmux/builder-lead.md:26`), spawn replaces an absent tier
with the role default (`spawn.py:195`), and route hardcodes default for
reviewer dispatch and an absent builder's adopted fix (`route.py:240`,
`route.py:654`). Queue and restart already preserve a selected tier.

1. Accept optional `tier=trivial|default|deep` on authenticated coordinator
   `pass=flavor issue=N` records; the newest record containing `tier=`
   supplies the allocation, and a later flavor-only record leaves it intact.
   Resolve explicit `--tier`, then item tier, then role default, then
   `default`. Missing item metadata keeps legacy behaviour; a malformed
   tier or unreadable required lookup refuses before claim/queue/window
   creation. Tier is a separate author-checked scan; flavor resolution is
   unchanged.
2. Resolve in spawn before enqueue/engine selection. Build and adopted
   fix/ci-red/merge-up spawns use the source issue; PR-only
   review/validate/recheck resolve the linked issue. Agreeing linked tiers
   are usable; conflicting tiers need explicit allocation, never first-link
   selection.
3. Persist the tier in queue and run args and use it for model effort and
   the brief. Dequeue, recorded-run restart/quota fallback and
   preserved-work relaunch retain it; a missing-run respawn resolves the
   current item record. Reallocating a pending request is an explicit
   coordinator replacement, not a silent running-session change.
4. Fixture proof covers build → fix, ci-red and merge-up recovery with a
   retained and an absent worker; capped enqueue → dequeue; clean restart and
   preserved-work relaunch; reviewer dispatch; explicit override and legacy
   fallback. Every run/brief has the selected tier/effort and replay creates
   no second worker. Keep hold/solo/refusal and engine-diversity gates.

Paths: `spawn.py`, `route.py`; `templates/triage-flavor.md`,
`templates/runtimes/tmux/builder-lead.md`, `docs/roles.md`,
`docs/runtimes/tmux.md`; `restart.py`/`dequeue.py` only if the preservation
fixture exposes a gap.

#### L1: learning record (#1813)

One docs-only PR closing #1813: add `docs/findings/m55-learning.md` and its
index link in `docs/findings/README.md`. Record the source/repair PR (#1805),
failure class, one reported occurrence, evidence limits, whole-link
composition prevention and retained producer/release coverage. Use `applied`
with named structural evidence; claim `encoded` only if a named check
enforces that exact source-template condition. Do not extend #1793's
completed batch. No product or test code.

#### Checks, forecast and closing

Against [Versioning](../deliverables.md#versioning): D1 adds an optional
marker field, so B3 is **minor**; B1/B2 restore documented wait/routing
behaviour, **patch** if they add no gate, duty or required marker field; L1
and S0 are **none**; S1's truthful shipped README/runtime wording is
**patch** if needed. Forecast M55 as at least **minor**; this is not a
release cut. A required existing-marker field, changed gate satisfaction,
state-tag meaning or command exit/parsed-output contract needs major
replanning before implementation.

| Unit | Protocol / templates | Sensitive forecast | Affected local tests | Status |
|---|---|---|---|---|
| S0/S1 | `docs/specs/portable.md`; S1 may touch README, `docs/runtimes/tmux.md`, coordinator memory | Spec permission at head; paths-only no match | Required checks; `--only design-headers --only spec-status` | open |
| B1 | Reviewer-lead/shared wait text if needed; existing status format | Hold suppression affects dispatch safety; classify actual diff | `test-crew-reviewer-pool.py`, `test-crew-lead.py`, `test-crew-watch.py`, `test-crew-route.py`, `test-crew-schedule.py`, `test-crew-poll.py` | done |
| B2 | Synthesizer event registry/runtime docs; synthesizer-lead event list | Permission author/head parsing is authority-related; classify actual diff | `test-crew-poll.py`, `test-crew-route.py`, `test-crew-lead.py`, `test-crew-land.py`, `test-crew-train.py`, `test-crew-roles.py` | done |
| B3 | `templates/triage-flavor.md`, builder-lead template, runtime/role docs; no F1–F7 change | Allocation authentication is authority-related; classify actual diff | `test-crew-spawn.py`, `test-crew-dequeue.py`, `test-crew-restart.py`, `test-crew-route.py`, `test-crew-reviewer-pool.py`; `test-item-flavor.py` if its helper changes | done |
| L1 | Internal findings/index only | Paths-only no match | Required checks | done |

Every PR runs `python3 scripts/check-repo.py` and
`python3 scripts/check-changelog-pr.py --base origin/main`, with selected
tests via `python3 scripts/run-tests.py <names...>` under the
[affected-tests policy](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6763423100).
Template or fixture changes add `test-crew-render.py`,
`test-render-parity.py`, `test-tmux-briefs.py` and `test-crew-bootstrap.py`.
Shared plumbing adds its affected dependent tests. Each PR lists its
selection and results, carries its own changelog fragment, and **PR CI runs
the full suite**. Template changes follow the protocol freeze and mirror
rules. The readiness pass's paths-only no-match forecast is not content
classification: classify every actual full diff at head; a sensitive head
needs the owner's per-change reason. No new gate contract is planned; one
appearing in a build is reclassified before review.

S1 sets completed rows to `done` with landed PR and acceptance-proof refs
and leaves unfinished rows `open` unless supersession is settled. It
reconciles all six issue closures, links L1, records D1–D4 and lessons, and
updates README Status and touched runtime/binding headers only where truth
changed, keeping merged, released and installed outcomes separate. The three
workaround clauses in `memory/roles/coordinator.md` are removed or narrowed
only after the installed behaviour is confirmed, through a reviewed memory
PR; otherwise they stay with a source-versus-installation note. M55 closes
only after S1 lands.

M53's closing sync #1815 edits this spec and the same status/header
surfaces: serialize those bookend edits, refresh `main` before each, and
preserve M53's rows and #1774's outstanding owner proofs. M55 code work and
completion do not wait on those proofs. Merge permission is the owner's
[merge-ok for all M55–M57 PRs](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6865236268),
recorded per PR at each actual head; it supplies no approval, CI waiver,
hold clearance, sensitive reason or missing AC proof.

### M57: delivery, campaign and shared status

Opening spec slice #1891 (S0) and closing status-sync slice #1890 (S1)
bookend [#1885](https://github.com/mw-ding/mdstack/issues/1885). Scope,
member ACs, sizes and test selection come from
[Riley's M57 readiness pass](https://github.com/mw-ding/mdstack/issues/1885#issuecomment-6884328732)
§2–§5, with five choices
[applied by the coordinator](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6884417656)
under the owner's
[next-round approval](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6884105830).
Runtime module paths below are under `environments/terminal/crew.d/`;
`path:line` citations refer to base `4202c823a7c028a19044a16991ba60d02ab628dd`.
S0 is recorded as done for this opening slice (PR #1892), effective on merge.
No member dispatches before #1891 merges. Order: S0 → D1, D2 and SD together;
D3, O1, C1 and L1–L6 fill spare slots; ST after SD merges; S1 last. D3
integrates after D2 if it reuses D2's pending-delivery bookkeeping, and L6
after D1's edit to the same fix fragment; shared files otherwise need a normal
merge-up, not serialized dispatch. One issue → one PR, with focused commits.
Sizes are non-test lines (C1 excludes relocated prose), planning ranges, not
limits.

| ID | Issue | Scope / named paths | Size | Depends on | Tier | Status |
|---|---|---|---|---|---|---|
| S0 | #1891 | This section (PR #1892) | 110–170 docs | Signed M57 scope and applied choices | default | done |
| D1 | #1878 | Review readiness: `route.py`, `poll.py`, `reviewer-pool.py`, `review.py`; `lead.py`/`watch.py` for retained waits; `_review_ready.py` only if needed; tmux runtime doc, builder fix fragment | 180–320 | #1891; integrate with D2 and L6 | deep | open |
| D2 | #1850 | Busy delivery: `send.py`, `acked.py`, `lead.py`, `watch.py`; `_shared.py` only for a necessary primitive; builder-lead template, tmux runtime doc | 160–280 | #1891 | deep | open |
| D3 | #1871 | Relay disposition: `reviewer-pool.py`, `lead.py`, `watch.py` if its wait fingerprint changes; builder-lead/coordinator templates, tmux runtime doc | 40–90 | #1891; after D2 if sharing its pending state | default | open |
| O1 | #1845 | Owner start/attach: `up.py`, `environments/terminal/sessions/tmux/adapter.py`, tmux runtime doc; `layout.py` wrapper stays the entry wrapper | 70–120 | #1891 | default | open |
| C1 | #1419 | Scenario files and index: `docs/campaign-harness.md`, new `docs/campaign-scenarios/Axx.md`, `.gitattributes`, `scripts/check-repo.py`, `scripts/deliverables.txt`; anchor consumers if changed | 50–100 + ~350–600 relocated | #1891 | default | open |
| L1 | #1444 | Watcher timing lesson; `docs/verification.md` only for the scoped reminder | 25–45 docs | #1891 | default | open |
| L2 | #1843 | Runtime-row lesson; `templates/policy/reviewer/passes.md` | 25–45 docs | #1891 | default | open |
| L3 | #1844 | Post-open fragment lesson; `templates/policy/builder/build-pass.md` | 25–45 docs | #1891; integrate with D1's initial/CI-fix cases | default | open |
| L4 | #1882 | Repaired repo-tag collision lesson | 20–35 docs | #1891 | default | open |
| L5 | #1883 | Resolved-profile compatibility lesson | 20–35 docs | #1891 | default | open |
| L6 | #1884 | Inline guard controls lesson; `templates/policy/builder/fix-rounds.md` | 25–45 docs | #1891; after D1's edit to the same fragment | default | open |
| SD | #1889 | Shared-status contract: new `docs/specs/shared-status.md`; its M57 reference here | 120–190 docs | #1891; precedes ST | deep | open |
| ST | #1313 | Shared status: new `core/status-record.py`, `connectors/github/status.py`; `core/crew-config.py`, GitHub manifest/map, `status.py`, new `_status_shared.py`, `watch.py`; interface/profile/backend/runtime docs; deliverables manifest | 350–600 | #1889 merged; D1–D3 states as observations | deep | open |
| S1 | #1890 | Status, evidence, decisions, lessons and tracker reconciliation | 40–80 docs | All thirteen members landed or explicitly superseded | default | open |

Lesson units add a dated `docs/lessons/YYYY-MM-DD-<slug>.md` (actual creation
date) and its lesson Index row, cite the source repair and set Status from
source evidence. Estimated total ~1,260–2,200 non-test lines plus the campaign
relocation.

**Target environment: N/A** — every acceptance path uses disposable state, a
fake forge and fake tmux; no new platform or device requirement. **Owner
prerequisites: none.** Live shared-status registration on a real issue and
real terminal adoption of `up --attach` are optional later operator choices,
not M57 acceptance. Standard flavor, tmux lane, normal capacity. D1, D2, SD
and ST use deep tier, passed as explicit `--tier deep` until 7.13.0 is
installed; the rest use default tier. Fragment PRs, this one included, may wait
for the open 7.13.0 cut (#1872).

#### Applied decisions

- **#1878 readiness:** the published, authenticated builder record for the
  classified operation is authoritative; `done:`, head events and the backstop
  are wake signals only; missing notifications reconcile by re-reading
  published records; no time-based waiver.
- **#1850 delivery:** delivery, liveness and disposition are separate axes;
  the original message ID is retained while a matching worker is busy;
  token-free re-probe; existing bounded idle/dead recovery; legacy exits
  unchanged.
- **#1845 entry point:** `mdstack up --attach` (also `start --attach`);
  same-server `switch-client`; a foreign-server client refuses with a
  detach/retry instruction before any start.
- **#1313 status:** closed pointer/count schema; explicit unique install
  registration; one per-instance comment on one owner-selected issue;
  `status --all`; off until configured; 300 s publish / 900 s stale as
  proposed defaults.
- **#1419 index:** committed generated Markdown index, checked and regenerated
  by `check-repo.py` from per-scenario records.

Unresolved boundaries, left to the named unit: SD settles the source
collectors, the install-specific registration binding and the exact
field/enum/default rules before ST starts. The 300 s / 900 s values are
proposed defaults, not existing settings. O1's foreign-server refusal is a
source-informed inference (`environments/terminal/sessions/tmux/adapter.py:21`,
`:157`); fake tests establish the contract, and no interactive client
migration was performed.

#### D1: review readiness (#1878)

Internal readiness identity **R**: `{team/repo context, item, PR, full
published head, kind, reset/changes epoch, requested round, originating
request identity, builder author + signature, published record reference}`.
For `fix` the requested round is the changes round; CI fixes before any
verdict use round 0; pure merge-up notes use `n/a`. Derive the epoch from
authenticated reset/verdict history and durable handoff records; add no
required public marker field. Check readiness at every reviewer admission
path (explicit `review.py` handoffs, durable work events, recovery), keep
waits in the existing queue/lead machinery with an evidence wait reason whose
fingerprint includes the note/request identity, and treat an unknown
operation class as a recoverable named wait, not an initial build.

| AC | Fail-closed rule over R / state | Table-driven proof shape | Status |
|---|---|---|---|
| D1.1 Binding | Fix-review admission needs a complete, consistent R at the live head and a matching published builder record, authenticated by login/signature, after the relevant request/epoch. Missing, truncated, foreign or conflicting fields create no reviewer claim, reservation or spawn. | One valid record; vary each field once, incl. same IDs and SHA in repo A/B, copied signatures, previous epoch, short SHA, unreadable live reads. Rejections preserve reviewer state; the valid counterpart dispatches once. | open |
| D1.2 Publication | A new head during a pending fix retains demand until its signed note has the required inline proof or justified N/A. A push, trailer, local file or `done:` alone is not the note. Readiness checks presence/placement; the reviewer judges correctness. | Head→note and note→head-event, missing note, note without proof, valid N/A, failed/uncertain post reconciled by readback. No reviewer before readiness, exactly one after. | open |
| D1.3 Persistence | Pending→ready survives lead/router/watcher restart and duplicate events; only the current epoch/head discharges. Superseded/closed retires its own demand; a hold parks it; unknown stays pending with a named reason. | Both arrival orders with interruption before/after dispatch; H1 superseded by H2; hold→release; two repos with equal IDs. One live successor, no cross-repo cleanup, no lost event. | open |
| D1.4 Recovery | The token-free backstop re-reads published records; a published note releases a wait even if `done:` was lost or the builder reclaimed. Missing/unreadable records stay pending under existing liveness/escalation, never a time-based waiver. | Delete the local completion signal after a valid note, restart, reconcile. Then remove the note: no admission, visible unresolved wait, existing bounded recovery. | open |
| D1.5 Other paths | Initial build: signed PR body plus proof. CI fix: `ci-fix`, incl. round 0. Same-head evidence fix: a new note after the current epoch. Clean merge-up keeps identity/carry/recheck rules; a differing patch waits for its note and delta review; a no-op merge-up waits for no note. | Cross `{initial, fix-new-head, fix-same-head, ci-fix-before-verdict, ci-fix-after-verdict, merge-up-identical, merge-up-different, merge-up-no-op}` with valid/missing/wrong-kind records and restart. Keep express self-gate routing, round caps and green-CI-at-land. | open |

#### D2: busy delivery (#1850)

Delivery input **D**: `{context, recipient window + recorded
pane/process/start identity, original message ID, kind/refs, inbox presence,
submit result, actual ack, live probe class, busy/idle observation,
retry/restart counters, observation time}`. Axes: delivery
`recorded/submitted/acked/failed`; worker
`busy/idle/dead/missing/ambiguous/quota/unreachable`; disposition
`pending/dispatched/superseded/blocked`. Unobservable busy/idle is unknown,
not idle. Inspection is additive (for example `acked --delivery`); legacy
`send --wait-ack`, `acked` exits and output are unchanged. Invalid input means
zero writes, telemetry included. Reuse declared adapter busy patterns without
harness-name branches in shared code. Never raise a timeout or return an
ack-like success for busy work.

| AC | Fail-closed rule over D | Table-driven proof shape | Status |
|---|---|---|---|
| D2.1 Truthful receipt | Inbox/queued/submitted/busy cannot create `ack:` or imply acceptance; only the target's matching actual ack discharges. An old run's ack cannot settle a successor's message. | Inbox, submitted composer, transcript echo, actual ack and wrong ID/run/context; only the actual valid receipt is acked. | open |
| D2.2 Busy retention | A live, identity-matching busy worker without ack stays pending under the same ID past the old 45 s wait and one retry: no fault, duplicate, restart, reclaim or repeated Enter. | Fake clock and adapter screens: busy past two waits→ack; duplicate caller; busy→idle→late ack; watcher/lead restart. One inbox message, retained counters. | open |
| D2.3 Bounded recovery | Busy→dead/missing uses the existing one-restart policy after fresh identity/hold checks, keeping the ID. Idle/unacked gets one re-nudge then a named block; dialog/ambiguous/unreachable gets no input or restart; quota keeps the eligible-engine path. | Busy→dead, replacement process with the same window name, idle/no ack, dialog before/after typing, unknown probe, exhausted retry/restart, held item, quota. No keys in dialogs, no second restart, no discarded work. | open |
| D2.4 Durable progress | The watcher/backstop re-probes pending delivery without model polling; a changed worker/ack state yields one actionable transition. Invalid context refuses before inbox/nudge/state writes; pending reads are never read as delivered. | Dispatcher→inbox→nudge→status→lead/backstop with fake tmux/clock, interruption at each boundary, duplicate wake, foreign A/B records; snapshot delivery/inbox/worker state and the tmux key log. | open |

#### D3, O1 and C1

**D3 (#1871).** The coordinator stays the fix owner, with explicit `fix` refs
including held CI (`reviewer-pool.py:84`, `route.py:804`). ACs: (1) a valid
relayed changes event is acked and visibly classified **awaiting coordinator
fix** with PR, full head, changes epoch, round and relay ID, and launches no
fix; (2) it stays a typed wait until a matching explicit coordinator fix
reaches the worker or the request turns terminal/superseded, and `done:` never
asserts an unstarted fix; (3) the coordinator handoff keeps findings and CI
refs, and its matching receipt settles the wait without a second handoff; (4)
replay, either arrival order, restart, hold/release, stale head, a missing
referenced event and foreign context keep the correct pending record. The fix
handoff/receipt is in the wait fingerprint, so a same-head fix releases it.
Proof runs reviewer result → builder-lead inbox/status → coordinator fix →
worker ack, with omitted-handoff and positive controls.

**O1 (#1845).** ACs: (1) a running crew attaches to window 0 on the resolved
server; (2) an absent crew runs the existing start path and attaches only
after successful creation, with one session and watcher; (3) a client on that
server uses `switch-client` to window 0 rather than nesting, and a
foreign-server client refuses with a detach/retry instruction before any
start; (4) `CREW_ROLE` refuses before session, watcher, wrapper or terminal
mutation; (5) help and runtime docs name the shortcut, plain `up` and
read-only `attach` keep their behaviour, and the generated wrapper keeps its
marker, quoting and refusal rules; (6) fake-tmux tests cover the four paths,
startup failure, replay and configured server selection (`up.py:350`,
`attach.py:24`, `layout.py:44`).

**C1 (#1419).** ACs: (1) each scenario has its own
`docs/campaign-scenarios/Axx.md` with notes, source and fixture or driver
reference, keeping IDs, oracles, accepted limitations and owner-run
obligations; (2) `docs/campaign-harness.md` keeps the common safety/runbook
contract and a sorted generated Markdown index checked by `check-repo.py`,
regenerated by `--fix`, failing closed on index or source-reference mismatch;
(3) the index covers the 30 committed Axx JSON specs plus the driver-only A29;
(4) the union attribute and its union-required guard/tests go in the same
migration, replaced by missing/duplicate/stale/dangling index controls; (5)
existing anchors stay via forwarding sections or every tracked consumer
(a19 ledger/smoke, a28/a29 helpers) is updated; (6) a two-branch fixture
rewrites different scenarios and regenerates the index after merge without
losing either edit. No scenario execution behaviour changes; the relocation
and the new check are separate commits.

#### Learning captures (L1–L6)

Each keeps its own PR. L1/L4/L5 may be lesson-only where the existing
contract and controls capture the remedy; L2/L3/L6 update only the smallest
relevant procedure, and the existing checker or guard stays the enforcement.
No repaired code reopens to justify a lesson.

- **L1 (#1444):** failed watcher tests, head/base reruns and the retained
  fixed-timeout limit; host load labelled inference. No timeout widening,
  retry-until-green claim or speculative repair.
- **L2 (#1843):** the repaired runtime-row omission, plus a narrow reviewer
  check that a shutdown/scratch change reads its allocated runtime state row
  (`docs/runtimes/tmux.md:62`).
- **L3 (#1844):** after open, fill the fragment's PR number, run
  `check-changelog-pr.py --base origin/main --pr N`, publish, read the new
  head; a moved head needs its signed note, incl. round-0 `ci-fix`
  (`scripts/check-changelog-pr.py:65`). No new automation.
- **L4 (#1882):** punctuation aliases and the injective repo encoding; keep
  the same-ID worker and escaped-literal controls (`_team.py:67`).
- **L5 (#1883):** derived context leaking into resolved values and grant
  pruning; no new resolve-output keys (`_shared.py:113`, `route.py:166`).
- **L6 (#1884):** both omissions (#1876, #1877); the fix procedure points to
  the existing inline failing-then-restored guard control (`docs/protocol.md:512`).
  No new gate; separate from D1's timing remedy.

#### SD and ST: shared status (#1889, #1313)

SD settles the contract in `docs/specs/shared-status.md` before ST starts.
Record **S** is a closed version-1 schema: `schema_version`, owner-selected
`instance_id` unique within the destination, opaque `registration_id`,
monotonic `sequence`, `observed_at`, `published_at`; canonical source repos,
runtime kind, decision-log URL; pointer/count sections for active milestones,
PRs (URL, closed stage enum), owner asks, blockers/incidents, merged/24h,
queue depth and scheduler target; an unavailable section is `unknown` with its
observation time, never empty, zero or healthy. No free text, raw titles,
personal identities, host names, paths, environment dumps, tokens or private
content. `schema_version` is not `crew:v1`: records are diagnostics, never
pass/verdict/steering markers, and an observation is not permission to act.
Config is optional (`[status] enabled=false`, destination and instance unset),
with an optional backend concern `publish-record` / `read-records`. The
connector edits only its own bound comment on the configured issue; its
receipt holds `{destination, instance_id, registration_id, publisher identity,
comment_id, last sequence/content identity}` under a local publisher lock.

| AC | Fail-closed rule | Table-driven acceptance shape | Status |
|---|---|---|---|
| S.1 Schema/privacy | Closed schema, correct types/enums/URLs, finite nonnegative counts, ordered sequence and valid UTC times. Missing/extra fields, unknown versions, disallowed payload and conflicting identity refuse before any write; unobserved sections stay unknown. | Valid minimal record plus each missing/wrong/extra field; string/bool numbers, raw payload, invalid URL, future/bad times, unavailable observations; through the CLI/connector entrypoint. | open |
| S.2 Off/authority | Off or unconfigured: no destination access, registration or publication. Invalid config, lost ownership, pause, unauthorized publisher or foreign registration: zero writes, incl. receipts, locks, queue and telemetry; locks only after acceptance. | Off/unset/invalid destination or ID, wrong account, workers/pools, lost ownership, pause; local snapshots plus fake API audit of POST/PATCH/DELETE; each refusal paired with an authorized positive case. | open |
| S.3 Destination/isolation | Publication needs the configured issue, authenticated publisher and matching install/registration/comment binding; full pagination and duplicate checks precede mutation; distinct A/B publishers change only their own comment. | N=0–3 installs, equal display names, reused instance ID, copied receipt, wrong issue/comment/author, duplicates on later pages, concurrent distinct publishes; unrelated comments and issue body unchanged. | open |
| S.4 Idempotency/recovery | Same sequence/content writes nothing; conflicting content, lower sequence or an ambiguous response never blindly writes; uncertain writes reconcile by readback; restart keeps registration and latest accepted state. | Failure before write, after remote write before receipt, lost create/update response, older publication last, interrupted restart; exactly one registration, no older snapshot wins. | open |
| S.5 Freshness/view | `mdstack status --all` is read-only, works without a local session, lists every valid instance with age/stale/blocked/unknown. Freshness uses observation time; age >= threshold is stale; future/invalid/unsupported records never look fresh. | Fake clock at threshold−1/0/+1, delayed republish, future times, unknown sections, malformed/unknown-version comments, closed destination, API and pagination errors; partial-failure diagnostics, no writes. | open |
| S.6 Optional seam | Existing profiles/packs validate unchanged with status off/absent; no new required capability. Schema in `core/`, connector in `connectors/`, collection in terminal modules; bounded timer with no model wake that stops on off/pause/lost authority; plain `status` unchanged. | Old manifests/profile outputs, fake optional status pack, unsupported capability, timer→off/pause/ownership loss, missing collector data, duplicate tick; fake CLI create→progress→read-all updates only the intended comment. | open |

SD ACs: specify S.1–S.6 with exact field/enum/default/time/identity/registration
rules and the zero-write boundary, name collectors and unknown handling,
define optional operations, configuration, lifecycle and fixtures, and flag
prospective sensitive or gate changes before implementation. ST ACs:
implement S.1–S.6, docs, the built-in connector, optional pack seam and
`status --all`, with CLI evidence and a valid control for every refusal;
lifecycle proof shows registration → update → disable with no later write.
No removal command is added only to manufacture a delete example.

#### Checks, forecast and closing

Against [Versioning](../deliverables.md#versioning), M57 forecasts as
**minor**, subject to actual compatibility; this is not a release cut. S0,
SD, C1 and lesson-only units are **none**; L2/L3/L6 reminders **patch**;
D1–D3 **minor** for an added non-gating duty or optional inspection; O1
**minor** (additive flag); ST **minor** if old profiles, manifests and plain
`status` work unchanged; S1 **patch** for deliverable wording. A required
marker field, changed §7 satisfaction, ack/`done:` meaning, required
capability or parsed output/exit is **major** and is replanned before
review. `docs/protocol.md` and the §7 registry stay untouched; an
implementation that edits them is reclassified as gate-contract work.

| Unit | Affected local tests (refine against the actual diff) | Status |
|---|---|---|
| S0/S1/SD | Required checks; `test-check-repo.py` only if checker behaviour changes | open |
| D1 | `test-crew-route.py`, `test-crew-poll.py`, `test-crew-reviewer-pool.py`, `test-crew-review.py`, `test-crew-recheck.py`, `test-crew-merge-up.py`; `test-crew-lead.py`, `test-crew-watch.py`, `test-crew-schedule.py` when waits/admission change; `test-crew-team.py` | open |
| D2 | `test-crew-send.py`, `test-crew-acked.py`, `test-crew-lead.py`, `test-crew-watch.py`, `test-crew-status.py`, `test-crew-restart.py`, `test-crew-team.py`; adapter tests if adapters change; `_shared.py` dependents such as `test-crew-upgrade.py` | open |
| D3 | `test-crew-reviewer-pool.py`, `test-crew-lead.py`, `test-crew-route.py`, `test-crew-watch.py`, `test-crew-team.py`; `test-crew-schedule.py` if admission changes | open |
| O1 | `test-crew-up.py`, `test-crew-attach.py`, `test-crew-layout.py`, `test-session-adapters.py`, `test-crew-team.py` | open |
| C1 | `test-check-repo.py`, `test-campaign-lint.py`, `test-campaign-run.py`; touched fixture consumers such as `test-campaign-sandbox.py` | open |
| L1–L6 | Required checks; `test-check-changelog-pr.py`, `test-crew-team.py`, `test-crew-grant.py` / `test-crew-config.py` only if their guards or controls change | open |
| ST | New `dev/tests/core/test-status-record.py`, `dev/tests/connectors/test-github-status.py`; `test-crew-status.py`, `test-crew-watch.py`, `test-crew-config.py`, `test-crew-pack.py`, `test-crew-grant.py`; bootstrap/upgrade if deliverable paths change | open |

Every PR runs `python3 scripts/check-repo.py` and
`python3 scripts/check-changelog-pr.py --base origin/main --pr N`, with
selected tests via `python3 scripts/run-tests.py <names...>` under the
[affected-tests policy](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6763423100).
Template or fixture changes add `test-crew-render.py`,
`test-render-parity.py`, `test-tmux-briefs.py` and `test-crew-bootstrap.py`.
New behavioural tests exercise production CLI/pool paths and paste
failing-then-restored controls inline. **PR CI runs the full suite.** Likely
sensitive candidates are D1's authenticated dispatch/recovery, D2's restart
and retained-work decisions, D3's event/actor binding and ST's publication
authority and zero-write guarantees; O1 keeps the agent-terminal refusal.
This forecast is not classification: classify each actual full diff at head,
and a sensitive head needs the owner's per-change reason.

S1 sets each member row `done` with PR and acceptance-proof refs, or
`dropped` with recorded supersession; an unfinished member stays `open` and
blocks closing M57. It keeps README, status-design and touched binding
banners truthful about source delivery, release and installation
separately, links the applied decisions and all six learning captures, and
confirms every landed or superseded member is closed; S1 and M57 close after
S1 merges. M25.2 and the conditional M58 stay outside this closeout. Merge
permission is the owner's next-round approval
([c6884105830](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6884105830)),
recorded per PR at each actual head; it supplies no approval, CI waiver,
hold clearance, sensitive reason or missing AC proof.

## 6. Decisions

| Date | Decision | Source |
|---|---|---|
| 2026-10-29 | **Config layers:** core defaults → default GitHub profile → org / environment pack outside mdstack → per-project config. No org-internal names here; packs declare what they cannot support; default profile stays complete. | #110 (decision comment) |
| 2026-10-29 | **Where the abstraction lives (Q9):** docs + `crew.toml` profile + renderer + small CLI. | [#110](https://github.com/mw-ding/eng-crew/issues/110) body, "Open questions → where they are settled" table, row Q9 ("decided: docs + `crew.toml` profile + renderer + small CLI"); approved by the owner with the roadmap |
| 2026-10-29 | **Single identity:** all roles act from one GitHub account in the coordinator session. For roadmap PRs, verdicts are COMMENT reviews headed `[Vera/verdict] round <k> @ <sha7>` with review and validate markers and a final `pass=verdict` marker; this replaces the formal `APPROVED` gate for #110 roadmap PRs only. Every other §7 gate is unchanged; CI is never waived. | #111 |
| 2026-10-29 | **Chat merge-ok:** the owner OKs each roadmap PR in the coordinator chat; the coordinator records it as an `[Ash/steer] merge-ok (owner, chat) @ <sha7>` COMMENT review with a `pass=steer cmd=merge-ok cmd-id=chat` marker; the synthesizer pass re-checks §7 and squashes with `--match-head-commit`. Roadmap PRs carry `crew:hold` so the live Grok Bot crew no-ops. Folded into #130 as the single-identity profile rule. | #111 |
| 2026-10-29 | **Protocol freeze:** `docs/protocol.md`, `templates/` and `docs/roles.md` frozen for M13 Phase A (#113–#119) except Phase A roadmap PRs; lifts when #119 merges. | #112 |
| 2026-10-29 | **Mirror deferral:** roadmap PRs touching `docs/protocol.md` or `templates/` merge without the per-PR box-skill mirror; the coordinator posts the deferral to #140 and removes `crew:needs-mirror` (documented fail-open). A PR that changes live Grok Bot behaviour still waits for a real mirror. Box skills sync once after M13 in #140. | #112, #140 |
| 2026-10-29 | **Kickoff choices:** builders run as Claude subagents; the reviewer runs on Codex CLI; up to 5 independent issues in parallel; M13 before M14. | Owner kickoff, recorded on [#110](https://github.com/mw-ding/eng-crew/issues/110#issuecomment-6516621437) |
| 2026-10-29 | **Inline-only evidence:** roadmap PRs carry their evidence inline, not under `evidence/`. | [#143](https://github.com/mw-ding/eng-crew/issues/143#issuecomment-6516943883), [#111 addendum](https://github.com/mw-ding/eng-crew/issues/111#issuecomment-6516944152) |
| 2026-10-30 | **Standing merge grant, all milestones:** extended from M13/M14 to every milestone of this project; it also covers status-only spec edits. | [#111 (all milestones)](https://github.com/mw-ding/eng-crew/issues/111#issuecomment-6535532827), [#111 (status-only spec edits)](https://github.com/mw-ding/eng-crew/issues/111#issuecomment-6537919568) |
| 2026-10-30 | **Release owner and gate:** the release owner identity and the release approval gate's interim convention. | [#219](https://github.com/mw-ding/eng-crew/issues/219#issuecomment-6537273776), [#243](https://github.com/mw-ding/eng-crew/pull/243#issuecomment-6536532290) |
| 2026-10-30 | **Spec bookends:** every milestone opens with a spec slice and closes with a status-sync slice. | [#259](https://github.com/mw-ding/eng-crew/issues/259), [#259 point 5](https://github.com/mw-ding/eng-crew/issues/259#issuecomment-6537919839) |
| 2026-10-30 | **Runtime direction, option A (#160):** mdstack keeps its own runtime and adopts firstmate's patterns and disciplines as contracts only, reimplemented with no code copied (#130 stands). The 19 row decisions are the overarching design for M15–M21 ([§5](#5-milestones-and-slices)). | [#160 final conclusion](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532414226) |
| 2026-10-30 | **M14 freeze exception (14.11):** one owner-approved addition to the frozen M14 scope, #172 (`mdstack kill` refuses to remove unlanded work), a data-loss fix. | [#160 M14 update](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532824780) |
| 2026-10-30 | **Changelog at cut time:** changes are recorded as per-PR fragments and assembled into `CHANGELOG.md` at release cut ([§2 P10](#2-requirements)), for every future milestone. Owner decision, recorded verbatim in #264. | [#264](https://github.com/mw-ding/eng-crew/issues/264) |
| 2026-10-31 | **M15+ hold lifted:** the owner lifted the M15+ hold for overnight autonomous execution. Still held for the owner (the standing #111 exclusions): substantive spec edits, merge-gate changes, live Grok Bot rule changes, `crew:sensitive` and any release beyond v2.0.1. | [#110 comment](https://github.com/mw-ding/eng-crew/issues/110#issuecomment-6540455617) |
| 2026-11-07 | **Four axes and generic actions:** roles, connectors, environments and harnesses vary independently ([P2](#2-requirements)). Roles name generic actions, and each environment implements them (P11). An environment is not a connector. | [#1213](https://github.com/mw-ding/eng-crew/issues/1213), [#1180 module structure](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703508949) |
| 2026-11-07 | **Self-hosted specs:** this repo keeps `docs/specs/` as its source of truth. Shape-changing work, such as the modular reorganisation, is specified here first. | [#1180 decision](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703556457) |
| 2026-11-07 | **Roadmap M29–M34:** the plan in [§5](#m29-specs-and-contracts). M28 is superseded. Grok Bot and Hermes adapters and herdr agent-API support are dropped for now. | [#1180 roadmap](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703873341), [#1180 M34](https://github.com/mw-ding/eng-crew/issues/1180#issuecomment-6703974869) |
| 2026-11-07 | **Generic extension mechanism:** this repo specifies the pack format, plug-in points, install flow and conformance kit in generic wording ([§9](#9-extension-mechanism)). A concrete pack is its own project, with its own specs in its own repo. | [#1217 scope addition](https://github.com/mw-ding/eng-crew/issues/1217#issuecomment-6703950176) |

## 7. Open questions

| Question | Settled in |
|---|---|
| Q1 wake model, Q2 session lifetime, Q3 coordinator engine, Q6 concurrency, Q7 failure handling | #130 |
| Q4 protocol split (core vs Grok Bot specific) | #114–#119 |
| Q5 identities on one machine | #132 |
| Q8 relation to #102 (solo lane) and #109 (quota) | revisit with M15 (owner to confirm) |
| Q10 minimum backend contract and capability declaration | #121 |
| Q11 which second backend proves the abstraction | deferred for the GitHub concerns; the `knowledge` concern's first backend is #1229 (v0.4) |
| Profile schema | #122 |
| Merge / override semantics between config layers | #123 |

## 8. Out of scope

- Organization-internal adapter packs (they live outside this repo; P6).
- Other agent runtimes beyond Grok Bot and tmux, and a second non-GitHub
  backend (Q11).
- Chat-platform owner channels (deferred).
- Changing any [§7](../protocol.md#7-merge-gate-synthesizer) merge gate for
  the Grok Bot runtime, other than the mirror gate in 13.16 (#128), which
  merges only on the owner's approval.
- Remote or cloud hosting of the tmux crew (local first).
- Product code of any repo the crew works on.
- A concrete pack's contents, even a public one: each pack is its own
  project ([§9](#9-extension-mechanism)).

## 9. Extension mechanism

Target design (v0.4). Pack loading and the conformance kit are built in
M31 ([#1236](https://github.com/mw-ding/eng-crew/issues/1236)). Until then,
today's config-only packs ([packs](../packs.md): `manifest.toml`,
`profile.toml`, render overlay, harness pointers) stay current. This
section adds no gate, marker or label.

**Pack format.** A pack is a directory with a `pack.toml` (today's
`manifest.toml` grows into it; #1236 settles the migration). It declares:

- the pack's name and its own version;
- the framework versions it supports, a pin or a range of releases (P9);
- what it provides at each plug-in point below, by name;
- the capability declaration of each connector it provides (P3).

**Plug-in points.** Built-in and pack adapters use the same interfaces and
are discovered by name:

| Point | A pack may add | Contract |
|---|---|---|
| Connectors | A backend for one or more concerns, `knowledge` included | P2, P3, [interfaces](../interfaces.md) |
| Harnesses | A harness adapter | [Harness adapters](../runtimes/harness-adapters.md) |
| Environment defaults | Default values for an environment it targets, such as session backend or host settings | [Runtime contract](../runtimes/README.md) and P11 |
| Extra skills | Role skills or skill variants beside the core ones | Role skills (M30) |
| Rules | Tightening only: a stricter flavor, extra gates or required skills | [Protocol](../protocol.md) floors |

A pack never loosens a core floor, gate, cap or invariant, and the loader
refuses a pack that tries. It never replaces the protocol or a core role.

**Config layering.** Pack values resolve as layer 3 of P5, between the
default profile and per-project config. Precedence is unchanged.

**Install flow.**

1. `install --pack <source>` fetches the pack at an exact commit or tag and
   checks its supported versions against the installed release. An
   unsupported version fails closed.
2. The install provenance records the pack's name, version, source and
   commit next to the framework release, as it already does for the
   framework.
3. Upgrade re-checks every installed pack against the new release and
   refuses one that does not support it. Nothing updates a pack on its own
   (P9).

**Conformance kit.** A `pack test` command runs the public actions-contract
and concern tests against the pack's adapters with fakes, so a pack can
run it in its own CI.

**Direction and wording.** Packs reference mdstack, never the reverse, and
this section stays generic (P6). An organisation's integrations are a pack
in that organisation's repo, with its own `docs/specs/`, applied at install
time.
