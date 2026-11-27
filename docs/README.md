# Docs index

The index for mdstack's docs. mdstack runs a repository with a team of
agent roles that keep their identity wherever they are deployed. A
deployment is the product of four independent axes: **roles** (who),
**connectors** (the tools of record), **environments** (where and how the
team runs) and **harnesses** (how an agent launches and loads); see
[concepts.md](concepts.md#four-axes) and [architecture.md](architecture.md#modules).

The framework is generic. Per-repo values appear as placeholders such as
`<owner>`, `<repo>`, `<author-login>` and `<reviewer-login>`. No secrets or
tokens are stored in this repo.

## Reading paths

Navigation only: these links point at the docs that own each rule and add no
rule of their own. A role's rendered brief stays its operating instruction;
what each role reads at start, every wake and on a trigger is in
[reading-paths.md](reading-paths.md).

<a id="find-your-path"></a>

Five routes, one per kind of reader, each in reading order. Every page
under `docs/` is reachable from this index, directly or through a subindex
([lessons](lessons/README.md), [findings](findings/README.md),
[metrics](metrics/README.md) and [campaign scenarios](campaign-harness.md)).

- **User** (you own a repo and want the team to work on it):
  [guides/getting-started.md](guides/getting-started.md) (then
  [guides/configuration.md](guides/configuration.md) to tune it), or
  [../README.md](../README.md) and its [Quickstart](../README.md#quickstart-tmux),
  then [architecture.md](architecture.md) for how work flows,
  [flavors.md](flavors.md) for rigor and
  [protocol §9](protocol.md#9-steering-crew-commands) for steering and the
  decisions the team asks of you.
- **Operator** (you install, run, upgrade or recover a team):
  [runbook.md](runbook.md) is the task table; it leads to
  [runbook-new-repo.md](runbook-new-repo.md), [bootstrap.md](bootstrap.md),
  [profile.md](profile.md), [guides/connectors.md](guides/connectors.md),
  [guides/migration.md](guides/migration.md) for older installs, the environment binding
  ([runtimes/tmux.md](runtimes/tmux.md),
  [runtimes/grok-bot.md](runtimes/grok-bot.md) or
  [runtimes/session.md](runtimes/session.md)) and
  [release.md](release.md#update-path) for upgrades.
- **Contributor** (you change mdstack itself):
  [../CONTRIBUTING.md](../CONTRIBUTING.md), [../AGENTS.md](../AGENTS.md),
  the specs ([specs/team.md](specs/team.md) for the module layout and
  dependency rules, [specs/portable.md](specs/portable.md) for the
  invariants), [protocol.md](protocol.md), [verification.md](verification.md)
  and [../scripts/](../scripts/README.md). A **pack author** (you add a
  connector, environment, harness or org specifics) starts at
  [guides/pack-authoring.md](guides/pack-authoring.md), then
  [concepts.md](concepts.md), the module READMEs below,
  [interfaces.md](interfaces.md),
  [runtimes/README.md](runtimes/README.md),
  [runtimes/harness-adapters.md](runtimes/harness-adapters.md),
  [../actions/README.md](../actions/README.md),
  [profile.md](profile.md), [roles-registry.md](roles-registry.md) and
  [packs.md](packs.md).
- **Reference** (you need the exact rule, key, schema or contract):
  [Available now](#available-now) lists every doc with its kind (`rule`,
  `reference`, `design`, `history`); the [ownership map](#documentation-principles)
  names the one page that owns each topic. Start with
  [concepts.md](concepts.md) for vocabulary,
  [architecture.md](architecture.md) for the flow (diagram sources in
  [diagrams/](diagrams/README.md)), [protocol.md](protocol.md) for stages
  and gates, [profile.md](profile.md) for keys and [roles.md](roles.md) for
  role contracts.
- **History** (you want why something is the way it is, or what happened):
  [decisions.md](decisions.md), the
  [lessons sub-index](lessons/README.md), the
  [findings sub-index](findings/README.md), the
  [metrics sub-index](metrics/README.md) (dated reports, the
  [PR snapshot](metrics/prs.md) and the
  [regression drills](metrics/regression-drills.md)),
  [runbooks/tmux-onboarding-history.md](runbooks/tmux-onboarding-history.md),
  the specs' delivery sections and [../CHANGELOG.md](../CHANGELOG.md). A
  history page is a dated record, not a current rule.

## Modules

One README per module says its purpose, contents and how it plugs in. The
target layout and dependency rules D1–D9 are in
[specs/team.md](specs/team.md#4-target-module-layout).

| Module | Axis or role | README |
|---|---|---|
| `roles/` | Roles axis: role definitions, routines, seat placeholders | [roles/](../roles/README.md) |
| `actions/` | Generic action vocabulary, CLI contract, conformance kit | [actions/](../actions/README.md) |
| `connectors/` | Connectors axis: tools of record per concern | [connectors/](../connectors/README.md) |
| `environments/` | Environments axis: team machinery and action implementations | [environments/](../environments/README.md), [terminal/](../environments/terminal/README.md) |
| `harnesses/` | Harnesses axis: one adapter per coding harness | [harnesses/](../harnesses/README.md) |
| `core/` | Shared libraries: config, renderer, registry, routines, memory, packs | [core/](../core/README.md) |
| `cli/` | The `mdstack` entry point | [cli/](../cli/README.md) |
| `profiles/` | Install-time profiles | [profiles/](../profiles/README.md) |
| `packs/` | Pack extension point | [packs/](../packs/README.md) |
| `dev/` | Repo QA: tests and fixtures | [dev/](../dev/README.md) |
| `protocols/` | Not split out yet: stages, markers, gates and flavors still live in [protocol.md](protocol.md), [flavors.md](flavors.md), [verification.md](verification.md) and [express-lane.md](express-lane.md) | none yet |
| `install/` | Not split out yet: bootstrap, upgrade and release bundle tooling still lives in `environments/terminal/` and [../scripts/](../scripts/README.md) | none yet |
| `docs/` | Narrative only: this index, architecture, concepts, specs, runbooks, lessons, findings | this page |

Supporting directories: [../templates/](../templates/README.md) (brief and
evidence templates), [../scripts/](../scripts/README.md) (guard, release and
role helper scripts) and `memory/` ([core memory](memory.md)).

## Available now

Audience: O owner, A adopter, P pack author, C coordinator, B builder, V
reviewer-validator, S synthesizer, R researcher; `all` means every one. Kind:
`rule` (normative: stages, gates, contracts), `reference` (schemas,
inventories, runbooks, overviews), `design` (proposal or build plan, possibly
partly built) or `history` (dated record, not a current rule). A doc with two
kinds mixes them; lifecycle status stays in each doc.

<!-- Keep the rows sorted by the first cell, one row per doc (check-repo.py checks both); a new doc's row goes at its sorted place, not at the end. -->

| Doc | Purpose | Audience | Kind | Contents |
|---|---|---|---|---|
| [../AGENTS.md](../AGENTS.md) | Agent build and review posture | B, V, R | rule | Thin agent guide: doc map, build posture, review posture (what blocks, what is a yellow follow-up) |
| [../CHANGELOG.md](../CHANGELOG.md) | Released change history | all | history | Record of every change |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | How to change the framework | B, V, C, S | rule | Process for iterating on the framework |
| [../scripts/](../scripts/README.md) | Guard and tooling guide | B, V, C | reference | Secret and token scan, required-docs check, relative link check, guard tests; runs in CI as `repo-guard` |
| [../templates/](../templates/README.md) | Template catalog | A, C, P | reference | Templates and their audience per runtime: rendered tmux and session briefs, hand-copied Grok Bot routines with trigger JSON and `wiring.md`, core seeds, shared policy fragments |
| [architecture.md](architecture.md) | Explanatory overview | all | reference | Canonical deployment, wake and release diagram; roles, identities, stages diagram, label reference, marker reference |
| [backends/github.md](backends/github.md) | GitHub backend mapping | C, B, V, S, P, A | rule | GitHub backend: reviews, markers and identities (review types and the events they fire, identity selection, land and merge-up) (13.3, #115); tracking (labels, milestones and board, linkage, steering limits) (13.4, #116); interface mapping: a `gh` command or API call per operation (13.9, #121) |
| [backends/notion.md](backends/notion.md) | Notion knowledge backend | C, B, V, R, A | reference | Notion knowledge connector (#1229): role source declarations, the private config (`CREW_KNOWLEDGE_CONFIG`, page pointer, `token_env`), `knowledge-read` and `knowledge-propose-edit` calls, binding reason codes |
| [bootstrap.md](bootstrap.md) | Install, pin and preflight | A, C, P | reference, design | Bootstrap (design): `mdstack bootstrap` entry point, release-bundle pin and record, config resolution, per-runtime install targets with contract gaps, `mdstack doctor` preflight with fix hints, repo-side setup, self-test, upgrade and uninstall, secrets, build issues (17.1, #144) |
| [campaign-harness.md](campaign-harness.md) | M25 campaign harness contract | C, B, V, R | rule | Campaign harness contract (25.01, #783): run manifest pins (repo, profile, source, release, target, sentinel), refusal of a production repo, session or root before mutation (`scripts/campaign-guard.py`), sentinel and retained-work cleanup checks; scenario runner and durable results (25.02, #784, `scripts/campaign-run.py`); disposable sandbox setup, teardown and level b/c runbook (25.03, #785, `scripts/campaign-sandbox.py`); generated index of the per-scenario files in `campaign-scenarios/` (#1419) |
| [concepts.md](concepts.md) | Vocabulary | all | reference | Glossary of abstract protocol terms (change, verdict, state tag, marker, ...) mapped to today's GitHub and Grok Bot terms (13.1, #113) |
| [configuration/resolution.md](configuration/resolution.md) | Profile validation module | O, C, P, A | reference | Profile validation split from the profile (26.M12, #857): `crew-config.py validate` with and without `--install`, the `file:key: reason` problem format and exit codes, the full rejection list, install-time versus run-time placeholders and the `resolve --install` check on the effective profile; layers and precedence stay in the profile |
| [configuration/runtime-options.md](configuration/runtime-options.md) | Runtime options module | O, C, P, A | reference | Runtime keys split from the profile (26.M14, #859): the `[runtime]` table (`name`, `options`, `timezone`, `instance` with its `control_item` condition) and the `max_active_milestones` coordinator option both runtimes accept, with its priority, in-flight and default behavior; `tmux` options, notes and launch topology stay in the profile |
| [configuration/team-files.md](configuration/team-files.md) | Team file schema module | O, C, P, A | reference | Team file schema split from the profile (26.M10, #855): `<config-home>/teams/<team>.toml` location and name, `[team]` tables and the `pack` / `personas` / `accounts` shorthands with their precedence, the `[repos.<name>]` allowlist and refusals, an example with two repo sections; resolution, team instance and migration stay in the profile |
| [decisions.md](decisions.md) | mdstack decisions | O, C, R | history | mdstack's own decisions doc in the essential doc set (#1219): dated owner decisions with their reasons and rejected options, newest first, seeded from the #985 decision log; operating state stays on #985 |
| [deliverables.md](deliverables.md) | Deliverable inventory and versioning | A, P, C | reference | Deliverables: inventory of every path as deliverable or internal, packaging as one bundle per release, SemVer breaking rules, compatibility promise to packs and installs, first versions (R1.1, #145) |
| [express-lane.md](express-lane.md) | Express lane | O, C, B, V, S | rule, design | Express lane (design): opt-in `express` flavor where one builder builds, self-reviews and tests, and the change lands on green CI; scoped F4/I1 (and, under `same`, I2) exceptions, sensitive/spec exclusions, the `selfgate_engine` flip, self-gate loop with the reviewer rubric, `pass=selfgate` record, §7 express gate row, routing, trade-offs, per-lane metric columns, build issues (M18.2, #636) |
| [flavors.md](flavors.md) | Rigor knobs and presets | O, C, B, V, S, P, A | rule, design | Crew flavors (design): rigor knobs, presets `thorough` / `standard` / `fast` / `solo`, the floor no flavor crosses, profile schema proposal and floor validator rules, project / item / change resolution with the path-based class rule, mapping of existing one-off knobs, metrics feedback loop with thresholds, suggestion issue and owner accept path, build issues (18.1, #156) |
| [guides/configuration.md](guides/configuration.md) | Configuration guide | O, A | reference | Configuring a crew by task (#1990): which file applies, identities, engines and tiers, team and repo selection, concurrency and speed controls apart from the rigor flavor, linking the profile, runtime-options, team-files and flavors schemas |
| [guides/connectors.md](guides/connectors.md) | Connector configuration guide | O, A | reference | Configuring connectors (#1238): one connector per concern in `[backends]`, validate and resolve, and the knowledge connector's three pieces (role source name in git, private config pointer, token in the environment) with no secrets in git |
| [guides/getting-started.md](guides/getting-started.md) | Getting-started guide | O, A | reference | First tmux run (#1238): one-command bootstrap into the home root, first `mdstack up`, talking to the team head, adding an on-demand role with `mdstack up <role>` |
| [guides/migration.md](guides/migration.md) | Migration guide | O, A, P | reference | 7.x to 8.0.0 first (#1965): owner commands without `--project`, `MDSTACK_CONFIG` and `--repo`, wrapper regeneration; then moving to 7.0.0 as version history (#1238, #1312): a fresh install, the old-to-new names and module paths, pack updates |
| [guides/pack-authoring.md](guides/pack-authoring.md) | Pack author guide | P | reference | Writing a pack (#1238): pack format and `pack.toml`, the plug-in points, wiring with `paths.pack` and `mdstack pack list`, the conformance kit `mdstack pack test` |
| [handoff.md](handoff.md) | Runtime ownership handoff | O, C, P, A | rule, design | Runtime handoff (design): one owning runtime per repo recorded on a control item, read-only fallback, drain or stop, the handoff manifest with its template, resume and reconcile, prompt stop, return path, session rules as config, runtime guards, the C9 contract capability, the tracker-native control item design (#875), build issues (21.1, #157) |
| [interfaces.md](interfaces.md) | Backend operation contract | P, C, A | rule | Backend interfaces: minimum operations per concern (change, review, tracker, state tags, markers, CI, events, owner channel), the invariant each protects, capability declaration, single-identity analysis (13.9, #121) |
| [lessons/README.md](lessons/README.md) | Lessons sub-index | C, R | history | Lessons log: entry format and index; first entry is [2026-10-19-bottlenecks.md](lessons/2026-10-19-bottlenecks.md) |
| [memory.md](memory.md) | Core memory layer | O, C, B, V, S, R, A | rule | Core memory (#1230): three memory layers (core in git, personal knowledge in services, platform memory as scratch), `memory/owner.md` and `memory/roles/<role>.md` with size limits, injection into every rendered brief per environment, the `core/crew-memory.py` lint that refuses personal data, and the coordinator's capture skill that proposes promotions as a memory PR |
| [merge-enforcement.md](merge-enforcement.md) | Platform merge protection target | O, C, S, A | design | M4 target merge rules, current plan blocker, application recipe, verification, rollback and fail-open |
| [metrics/README.md](metrics/README.md) | Metric field reference | O, C, R | reference | Cycle-time and rounds metrics artifact: field definitions, refresh command, committed `prs.md` / `prs.csv` |
| [metrics/a31-campaign-report.md](metrics/a31-campaign-report.md) | A31 campaign-history report | O, C | history | M25's crew PRs from actual forge records: counts and denominators per standard, express and solo lane, timing, the owner decision records in the window and the data named as missing (#1462) |
| [metrics/decisions.md](metrics/decisions.md) | Metrics sensors and thresholds | O, C, B, R | rule | Metrics to decisions: sensors, windows, thresholds, rollup vs per-repo, the `metrics-gate` issue and what blocking `M*` feature work means, waiver and lift |
| [metrics/m25-1-evidence-ledger.md](metrics/m25-1-evidence-ledger.md) | M25.1 evidence ledger | O, C | history | #157/#158 AC1, AC2 and AC4 audit with citations, the #716 case index naming each closing run and its stated physical limits, and wording contradictions for their owners (#1445) |
| [metrics/m25-report.md](metrics/m25-report.md) | M25 final report | O, C | history | M25 final regression at `a135a4d`, merged-head reruns, register rows 34–46, real-engine journeys, cost/usability, traceability and the limitations for the owner to accept (25.27, #806) |
| [metrics/owner-sla-drill.md](metrics/owner-sla-drill.md) | Owner-SLA drill | C, R | design, history | Owner-SLA drill plan (P7): synthetic hold, expected timestamps, pass/fail checks, results table |
| [observe.md](observe.md) | Step summaries | C, B, V, R | rule | Step-summary observe protocol: step lines, `.crew/runs/` paths, promote onto the PR, what reviewers skim, risks |
| [packs.md](packs.md) | Pack contract | P, A, C | rule | Packs: layout (`manifest.toml`, `profile.toml`, binding docs, render overrides), `mdstack_version` pin and compatibility rule, capability folding, wiring by `--org-profile`, direction rule, denylist check (13.15, #127) |
| [personnel.md](personnel.md) | Personnel content boundary and pinned host import | O, C, B, P | reference | Producer content install, host binding and authority-preserving import (#1180) |
| [profile.md](profile.md) | Profile schema and defaults | O, C, P, A | reference | `config.toml` profile schema: every key, type, default and the placeholder it replaces; validated by `core/crew-config.py validate` (13.10, #122) |
| [project-doc-set.md](project-doc-set.md) | Project doc set module | O, C, R, A | reference | Essential doc set split from the project docs design (26.B P1, #1024): the six docs every crew-run project should have (overview, agent guide with crew profile notes, architecture, runbook, decisions, and specs as the source of truth, #1219) with default homes the `[docs] homes` profile key maps, the docs index and small-project rules, and the status banner a target project's design doc carries |
| [project-docs.md](project-docs.md) | Target project docs consolidation | O, C, R, A | design | Project docs consolidation (design): the essential doc set for every crew-run project (moved to project-doc-set.md), the status banner convention (moved too), a docs pass (zero-model scan plus a researcher session) that reports missing, duplicated, contradictory or stale docs and drafts structural issues for the coordinator, the `[docs]` profile opt-in, host options, alternatives, mdstack dogfood pilot, build issues (M26 Track B, #754) |
| [protocol.md](protocol.md) | Stages, markers and gates | C, B, V, S, R, P | rule | Stage protocol: evidence, rounds, duties on wake, merge gate, safety, `/crew` steering |
| [reading-paths.md](reading-paths.md) | Role reading paths | C, B, V, S, R, O, A, P | reference | Reading paths: what each role reads at start, re-reads every wake and loads when a trigger fires, with exact canonical links; navigation only, no rules (26.2, #760) |
| [release.md](release.md) | Release cut and publish | O, C, S, A, P | rule, design | Release workflow (design): cut-PR merge trigger, head-bound owner approval, validate and build, tag and GitHub Release, release gate, rollback, update path, session-tooling upstreaming (R1.1, #145) |
| [roles-registry.md](roles-registry.md) | Role registry schema | P, C, A | reference, design | Role registry schema (design): closed keys, all four current roles, validation and migration inventory (15.7, #317) |
| [roles.md](roles.md) | Role, engine and PR contracts | C, B, V, S, R | rule | Worker roles, tiers, engines and quota routing, worktree rules, worker brief and PR templates, coordinator owner-communication rules |
| [routines.md](routines.md) | Role routines | O, C, R, A | rule | Role routines (#1247): each role's recurring jobs in `routines/<routine>.toml` (schedule, skill, generic actions, inputs, outputs, deadline, miss policy), miss handling in `core/crew-routines.py`, the terminal binding on the watcher's timers and lifecycle `routine` wakes, and the migrated triage, docs-pass and backstop cadences |
| [runbook-new-repo.md](runbook-new-repo.md) | Onboarding runbook | A, C, P, O | reference, history | Onboarding runbook for a new repo: install by profile (`config.toml`, validate, resolve, render), prerequisites, labels, collaborators, Project, CI and protection, product-safety checks, listener wiring, first test issue, verification checklist, rollback |
| [runbook.md](runbook.md) | Runbook entry point | O, A, C | reference | mdstack's runbook entry point in the essential doc set (#1219): navigation only, one table each for install and onboard, run and operate, release and upgrade, and recover, linking the doc that owns each task |
| [runbooks/github-ci-protection.md](runbooks/github-ci-protection.md) | GitHub CI and branch protection module | A, O | reference | Onboarding Step 4 items 1–4 split from the runbook (26.M24, #895): workflow and trigger discovery, push CI on the default branch with the after-merge `ci-failed` listener condition and noisy-job handling, exact required-check names and the aggregate check, current protection, ruleset and merge-settings reads with the normal 404; the protection choice, merge settings and enforcement limits remain in runbook Step 4 |
| [runbooks/github-reviewer-access.md](runbooks/github-reviewer-access.md) | GitHub reviewer access module | A, O | reference | Onboarding Step 2 split from the runbook (26.M6, #844): invite the reviewer identity with write access, accept the invitation or take the existing-org-member path, verify `write` permission and zero pending invitations, confirm author push access |
| [runbooks/github-tracking.md](runbooks/github-tracking.md) | GitHub tracking module | A, O | reference | Onboarding Step 1 split from the runbook (26.M9, #854): `crew:*` namespace pre-check and collision refusal, the ten-label guarded `--force` creation loop and API example, verification of exactly ten rows; milestones and the Project board remain in runbook Step 3 |
| [runbooks/grok-onboarding.md](runbooks/grok-onboarding.md) | Grok Bot onboarding module | A, O | reference | Onboarding Step 6 split from the runbook (26.M29, #900): bootstrap install-state verification (`VERSION`, `install.json`, profile copy, pending human steps), bootstrap-owned file restrictions, deployed versus manual-fallback state setup, `wiring.md` sources and `planned`/`applied`/`live` status, reviewer-engine ownership and private-repo condition, the README-seed safety requirement; the filled-in wiring example and Step 7 remain in the runbook |
| [runbooks/offboarding.md](runbooks/offboarding.md) | Offboarding module | A, O | reference | Onboarding rollback and offboarding split from the runbook (26.M37, #908): bootstrap uninstall preview and apply, unlanded-run and edited-target preservation, the Grok Bot manual routine removal and `--routines-removed` retry, human settings steps and held-PR disposition, then all nine manual steps in order (pause, routines, collaborator, enforcement, labels, Project, state dir, open PRs, record) |
| [runbooks/onboarding-proof.md](runbooks/onboarding-proof.md) | Onboarding proof module | A, O | reference | Onboarding Step 8 opening split from the runbook (26.M33, #904): trivial docs-only smoke issue choice, the full template issue (goal, acceptance criteria, out of scope, role and tier hint), creation with `crew:ready` then assignment to the author identity as the event, milestone and Project placement, the `Refs` closing path; the expected sequence, checklist and evidence timeline remain in the runbook |
| [runbooks/prerequisites.md](runbooks/prerequisites.md) | Onboarding prerequisites module | A, O | reference | Onboarding prerequisites split from the runbook (26.M21, #891): do-not-start condition and checklist evidence, the author and reviewer identities (different accounts) and the setup-admin qualification, per-command credential selection without switching the active `gh` account, shell-only export, no token recording, identity checks |
| [runbooks/product-preflight.md](runbooks/product-preflight.md) | Product preflight module | A, O | reference | Onboarding Step 5 product-safety checks split from the runbook (26.M27, #898): do them before any routine is installed (that makes the crew live) and record the answers in wiring doc section 0; one automation system per repo (discovery commands, ownership decision in the wiring doc); never touch product labels or commands, E2E PR ignore rule; fork PRs and external contributors (`crew:external`, no-token sandbox, workflow approval wait, author-gated steering, no builder pushes to forks, upstream-sync limit, fork workflow secrets) |
| [runbooks/profile-install.md](runbooks/profile-install.md) | Profile install module | A, C, P, O | reference | Onboarding Step 0 bootstrap split from the runbook (26.M7, #852): install from a verified release bundle or exact tag (`--dev` for an untagged checkout), `mdstack bootstrap` dry-run and apply, refusal and review conditions, expected outputs, runtime-specific deployment, remaining Steps 1–8 |
| [runbooks/repo-rename.md](runbooks/repo-rename.md) | Repository rename runbook | O, A | reference | Owner-run repo rename (33.2, #1234): what the repo name keys and what stays (product names until a release), the `mdstack migrate --rename-to` dry run, stop, `gh repo rename`, redirect checks for the old URLs, apply, host-root and remote owner steps, restart and rollback |
| [runbooks/tmux-onboarding-history.md](runbooks/tmux-onboarding-history.md) | tmux onboarding history | A, O | history | Dated end-to-end tmux run for #139 (2026-10-30, mdstack `main` at `7eb454d`) split from the onboarding runbook (26.M5, #843): timeline and the pass bar adopted then; history, not current instructions |
| [runbooks/tmux-onboarding.md](runbooks/tmux-onboarding.md) | tmux onboarding module | A, C, P, O | reference | tmux onboarding operator module split from the onboarding runbook (26.M1, #839; 26.M2, #840; 26.M3, #841; 26.M4, #842): tmux prerequisites (tools and logins, engines, permission mode, Codex hook trust, bundle or checkout, nested-sandbox variable), target-repo setup (profile, labels, CI), the run procedure (commands, first-start trust, wake path, close-out, owner duties) and the troubleshooting table |
| [runtimes/README.md](runtimes/README.md) | Runtime contract (C1–C9) | P, A, C | rule | Runtime contract: the eight capabilities every runtime provides, the guarantee each protects, gap-declaration format (13.8, #120) |
| [runtimes/grok-bot.md](runtimes/grok-bot.md) | Grok Bot binding | C, B, V, S, A, P | rule | Grok Bot runtime binding: wake wiring, per-PR watches, verified B2 hand-off, comment-listener wakes, lighter-lane routing, routine limits, pilot notes (13.2, #114) |
| [runtimes/harness-adapters.md](runtimes/harness-adapters.md) | Harness adapter contract | P, A, C | rule | Harness adapter interface: launch line, trust and first-run dialogs, turn-end and wake recipe, idle detection, expected foreground process, each tied to C1, C3 or C5; Claude Code and Codex filled in (15.4, #177) |
| [runtimes/multi-device.md](runtimes/multi-device.md) | Multi-host runner | O, C, B, V, P, A | rule, design | Multi-device tmux crew (design): role runs placed on hosts of a private overlay network under one primary; overlay assumptions, host inventory profile keys, placement function, host readiness, hardened remote call and runner, C1–C8 across hosts, failure and partition, security model, forge-less runner hosts with an add-a-runner-host runbook and a role-host add and remove runbook with per-OS steps and lab proof limits (20.12), build issues (20.1, #158) |
| [runtimes/session-backends.md](runtimes/session-backends.md) | Session backend contract | P, A, C | rule | Session backend interface: create in the background, attach (read-only default), doorbell, identity probe (handle plus start time, C5), state read and kill, each tied to a contract capability; tmux filled in (15.5, #178) |
| [runtimes/session.md](runtimes/session.md) | Session binding | C, B, V, S, R, P, A | rule, design | Session runtime binding (design): proposed `session` selector, coordinator and worker lifecycle, adapters, C1–C9 gaps, attended operation and implementation boundary (17.13, #340) |
| [runtimes/tmux.md](runtimes/tmux.md) | tmux binding | all | rule | tmux runtime binding (shipped in M14 and M14.1): answers to #110 Q1, Q2, Q3, Q5, Q6, Q7 with alternatives, contract table, window layout and naming, spawn and kill mechanics, the `mirror = "none"` setting for installs with no live copy (#877), firstmate design credit (14.1, #130) |
| [scheduling.md](scheduling.md) | Crew scheduler | O, C, B, V, R | rule | Crew scheduler (built): one crew-wide `mdstack schedule decide` for both leads; observable inputs (demand, priority, worker state, machine load, memory, suites, gateway errors, presence); finish-before-start classes, hysteresis target with ramp limit, pool floors against starvation, overlap trains; decision log and one summary line; what it subsumes; build issues (M18.1, #587) |
| [self-improve.md](self-improve.md) | Self-improve intake | C, B, V, S, R | rule, design | Self-improve intake: triggers, candidate card, accept/close, lesson path, `repo:` vs `crew:` scope, risks |
| [specs/framework.md](specs/framework.md) | Framework spec | O, C, R, P | reference, history | Original spec for this repo: goal and requirements R1–R8 (still cited); the bootstrap layout, source material and slices are historical (#1237) |
| [specs/land-triage-ergonomics.md](specs/land-triage-ergonomics.md) | Land, triage and bootstrap ergonomics spec | O, C, B, R | reference, history | Spec for M64 (#2026, for #2030): member fixes and ACs for the stack-land separator, session assigned-checkout isolation, per-item tracker comment read, verified exported packs, the named permission-dialog escalation (#1968), three learning cards (#2017–#2019), the publication ledger PL1–PL8 with its re-scan (#1995), and closing checks G1–G5 (run at S1, #2028) |
| [specs/portable.md](specs/portable.md) | Portable spec | O, C, R, P, A | reference, history | Spec for portable mdstack (#110): runtime and tool abstraction, config layers, invariants, target layout, M13/M14 slices, decisions, open questions |
| [specs/public-docs.md](specs/public-docs.md) | Public-docs spec | O, C, B, R | reference, history | Spec for M62 public onboarding and documentation (#1985, for #1984): owner decisions PD1–PD4 (MIT license, the mdstack name, private vulnerability reporting, publication boundaries out of scope), writing rules, member rows D1–D9 with ACs, closing checks C1–C6 (run at S1, #1996; the C4 render and C5 dry run deferred to #2013) |
| [specs/shared-status.md](specs/shared-status.md) | Shared-status spec | O, C, B, P | design | Contract for publishing independent crews' status to one shared place (#1889, for #1313): `[status]` configuration, closed version-1 record and collectors, instance registration, zero-write boundary, sequence recovery, `status --all`, optional `status` concern, fixtures and acceptance matrix S.1–S.6 (not implemented) |
| [specs/team.md](specs/team.md) | Team spec | O, C, R, P, A | reference, design | Spec for the team and modular design (#1216): requirements REQ-01–REQ-24 (portable roles, four axes, generic actions, terminal fast lane, knowledge connector, seats and staff, self-hosted specs), target module layout, dependency rules D1–D9, relation to portable.md P1–P8, open questions; §9 team/project separation, its M56 delivery rows (#1854) and M56 outcome and lessons (built for the terminal runtime, isolated proof) |
| [specs/v8-crew-reliability.md](specs/v8-crew-reliability.md) | 8.x crew reliability spec | O, C, B, R | reference | Spec for M65 8.x crew reliability fixes (#2093, for #2095): settled fixes and ACs for members A1–A2, W1–W3, V1–V2, E1–E2 and N1 (issue-assigned admission, dependent handoff once and drain locking, watcher spawn-failure survival, delivery busy-pane probe, owner-answer crew-post filter, validation skip alignment, validate-section retention, guard negative control, `PROOF` forms, policy-block failure and transport restart), member order A1→A2, W1→W2, V1→V2 and E1→E2, owner decision OD1 left open, closing slice S1 (#2094) |
| [specs/v8-reliability.md](specs/v8-reliability.md) | 8.x reliability spec | O, C, B, R | reference, history | Spec for M63 8.x reliability fixes (#2025, for #2029): settled fixes and ACs for members R1–R11 (7.x→8.x upgrade re-exec, launcher install root, primary host root, team change through the handoff record, merge-up delta review, land-lock test, release-cut readiness, research artifacts, suite-wait admission, session `up` parity, backend-aware builder brief), member order R1→R2→R3 and R7→R4, closing slice S1 (acceptance ledger run at S1, #2027) |
| [triage.md](triage.md) | Always-on triage | O, C, R | design | Always-on triage (built for tmux in M24, live in shadow mode; #753 risk mitigations unbuilt): a recurring sweep by a fresh researcher session on the watcher's timer, a zero-model scan in `mdstack poll` with P0 detection, learning lookup over duplicates, lessons, findings and owner decisions with citations, rules first and fail closed, auto-apply / propose / never autonomy, P0–P3 bands, `pass=triage` records, a daily log issue and owner replies on the item, shadow mode with an 8-of-10 precision bar, feedback metrics, build issues (M24, #659) |
| [verification.md](verification.md) | Typed runtime evidence | B, V, S, C | rule | Verification protocol: typed runtime evidence per shape (web, CLI, service, API, mobile), role duties, N/A rules, fail-open |

## Planned

Nothing is planned right now. Every doc in the spec's slices has landed and is
listed under Available now.

## Documentation principles

Owner-approved on 2026-11-04 for editing these docs. They guide how a doc is
written, moved or split and add no rule, gate, marker or default of their
own. The full design, with reasons and rejected alternatives, is
[Riley's design on #676](https://github.com/mw-ding/mdstack/issues/676#issuecomment-6638520989);
the approval and principle 11 are in the
[decision record](https://github.com/mw-ding/mdstack/issues/676#issuecomment-6640367783).

1. **One authored definition per rule.** Each rule lives in one owner
   section carrying all its conditions and exceptions; other mentions link to
   it, and examples illustrate without redefining. Why: copies drift into
   competing instructions.
2. **Ownership follows topic, not reader.** A role page links to the topic
   owner below instead of becoming a second owner. Why: role views repeat
   rules for every reader.
3. **Lifecycle is evidence-backed and scoped.** A design page states
   `design`, `partly built`, `built` or `superseded` under its H1, with scope,
   current-rule links, evidence and a last-checked date or SHA; kind stays
   separate. Why: readers must tell shipped mechanisms from proposals.
4. **Structural consolidation preserves behaviour.** A move or dedup changes
   no rule, gate, marker, default or runtime support, shows source-to-target
   correspondence and files a contradiction as its own correction issue. Why:
   review checks preservation, and no cleanup silently picks a winning rule.
5. **Executable copies have a different boundary.** Generated includes and
   instructions a brief needs to run may stay copied; other handwritten policy
   copies are tracked debt with an owner and follow-up. Why: a required
   instruction must not become an optional link.
6. **Reading paths separate start, every wake and triggers.** Navigation
   gives exact links for each, adds no duty or waiver and keeps conditional
   material off unrelated paths. Why: neither full rereads every wake nor
   summaries that drop mandatory checks.
7. **New files stay packaged and reachable.** A new doc gets its manifest
   row, generated inventory row and index row; prefer existing sections. Why:
   an unclassified file fails checks or drops out of bundles.
8. **Sensitivity survives structural-only status.** A move touching a
   sensitive path still needs `crew:sensitive` and per-change owner merge-ok.
   Why: unchanged wording in a new place can still change gate reading.
9. **Sequence by dependencies and changed hunks.** Aim near 100 authored
   changed lines per PR, under 200 where practical, counting both sides of a
   move; serialize overlapping hunks. Why: small, ordered slices review well
   and avoid parallel rewrites.
10. **Guardrails prove mechanics, not meaning.** Green `check-repo.py` and
    link checks do not prove fragments, ownership or preserved meaning; keep
    old anchors and check destination headings by hand. Why: the checks do not
    cover those.
11. **Modular organization.** One concern per file, with boundaries that
    follow the ownership map. An oversized multi-concern doc is split over
    time; its original path stays as a stable entry point with its old
    anchors kept as link targets, cross-module references are links only, and
    each split is a section-sized move under principles 4, 7, 8 and 9. Why:
    cohesive modules are easier to own, read and change.

Principle 2 ownership map, as approved:

| Topic | Authored home |
|---|---|
| Vocabulary; explanatory flow | [concepts.md](concepts.md); [architecture.md](architecture.md) |
| Stages, duties, marker schemas, evidence placement, rounds, gates, steering | [protocol.md](protocol.md) |
| Keys and defaults; rigor and preset semantics | [profile.md](profile.md); [flavors.md](flavors.md) |
| Evidence shapes, N/A and reproduction | [verification.md](verification.md) |
| Runtime guarantees; concrete mechanisms and support gaps | [runtimes/README.md](runtimes/README.md); the selected runtime binding and interface or adapter docs |
| Role boundaries, engines and identities, worktrees, PR and fix contracts | [roles.md](roles.md) |
| Triage workflow and autonomy; intake; scheduling; observation; metrics decisions | [triage.md](triage.md); [self-improve.md](self-improve.md); [scheduling.md](scheduling.md); [observe.md](observe.md); [metrics/decisions.md](metrics/decisions.md) |
| Unbuilt alternatives and decision history | Design or history sections, explicitly labelled, with current rules linked above them |
| Executable render inputs and capture or body recipes | [../templates/](../templates/README.md), derived from and linked to the policy home |
