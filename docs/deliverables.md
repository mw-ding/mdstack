# Deliverables and versioning

> - **Status:** built
> - **Applies to:** every release bundle from `v2.0.0`
> - **Current rules:** [protocol](protocol.md); release gate in the [gate registry](protocol.md#gate-registry)
> - **Built:** [Inventory](#inventory) as `scripts/deliverables.txt`, [Packaging](#packaging) by `scripts/release-bundle.py` (#236), [Versioning](#versioning) and [First versions](#first-versions) (#219)
> - **Design only:** further harness layouts as render targets ([Packaging](#packaging)), decided in [bootstrap](bootstrap.md#q4-install-targets)
> - **Last checked:** 2026-11-04 at `217cec5`

What mdstack ships, how it is packaged, how it is versioned and what each
version promises (roadmap R1.1,
[#145](https://github.com/mw-ding/eng-crew/issues/145); umbrella
[#110](https://github.com/mw-ding/eng-crew/issues/110);
[portable spec P9](specs/portable.md#2-requirements)). How a version is cut
and taken is in [release.md](release.md).

This page adds no rule, gate, cap, marker field or label; the
[protocol](protocol.md) owns them. The bundle build
([#236](https://github.com/mw-ding/eng-crew/issues/236)) and the release
workflow with the bundle attach
([#218](https://github.com/mw-ding/eng-crew/issues/218),
[#246](https://github.com/mw-ding/eng-crew/issues/246)) are implemented
([release.md](release.md)).

## Terms

- **Deliverable:** a path an environment installs or loads at run time (a
  role reads it, a script runs, the renderer consumes it). Deliverables are
  the public surface that [versioning](#versioning) covers.
- **Internal:** a path only maintainers of this repo use. Changing it never
  changes the version number.
- **Source / generated:** this repo holds only source. Rendered briefs and
  routines, and the release bundle, are generated and never committed
  (golden test fixtures excepted).

## Inventory

Every tracked path falls in exactly one row. Runtime `all` means every
runtime; `grok-bot`, `tmux` and `session` are the
[runtime bindings](runtimes/README.md). The table is generated from
[`scripts/deliverables.txt`](../scripts/deliverables.txt), one row per manifest
row (a row may be a glob), so the manifest is the source and no PR edits the
table by hand: add or change a manifest row at its sorted place, then run
`python3 scripts/check-repo.py --fix`. `check-repo.py` fails on a stale table
and on an unsorted manifest, which would bring back the append point every PR
conflicts on ([#325](https://github.com/mw-ding/eng-crew/issues/325)).

<!-- inventory:begin generated from scripts/deliverables.txt by `python3 scripts/check-repo.py --fix`; do not edit -->

| Path | Class | Runtime(s) | Why |
|---|---|---|---|
| `.gitattributes` | Internal | n/a | Repo process and CI: rules for building mdstack itself |
| `.github/**` | Internal | n/a | Repo process and CI: rules for building mdstack itself |
| `.gitignore` | Internal | n/a | Repo process and CI: rules for building mdstack itself |
| `.markdownlint-cli2.yaml` | Internal | n/a | Repo process and CI: rules for building mdstack itself |
| `AGENTS.md` | Internal | n/a | Repo process and CI: rules for building mdstack itself |
| `CHANGELOG.md` | Deliverable | all | Bundle front page and release notes: shipped as is |
| `CONTRIBUTING.md` | Internal | n/a | Repo process and CI: rules for building mdstack itself |
| `README.md` | Deliverable | all | Bundle front page and release notes: shipped as is |
| `actions/*.md` | Internal | n/a | Design contract: generic action vocabulary, CLI contract and per-environment mapping; implemented in M32 ([#1218](https://github.com/mw-ding/eng-crew/issues/1218)) |
| `actions/contract.py` | Deliverable | all | Conformance kit: the actions/ contract tests `mdstack pack test` runs against a pack's adapters ([#1236](https://github.com/mw-ding/eng-crew/issues/1236)) |
| `changes/**` | Internal | n/a | Unreleased CHANGELOG fragments: assembled into `CHANGELOG.md` at the cut, then deleted ([CONTRIBUTING](../CONTRIBUTING.md#changelog)) |
| `cli/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `cli/mdstack` | Deliverable | all | Runtime CLI: mdstack entry point, including bootstrap and doctor |
| `connectors/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `connectors/github/crew-repo.py` | Deliverable | all | Install CLI: shared GitHub repository checks and dry-run fixers |
| `connectors/github/manifest.toml` | Deliverable | all | Connector: GitHub capability declaration ([#1223](https://github.com/mw-ding/eng-crew/issues/1223)) |
| `connectors/notion/knowledge.py` | Deliverable | all | Knowledge connector: Notion binding of knowledge-read and knowledge-propose-edit ([#1229](https://github.com/mw-ding/eng-crew/issues/1229)) |
| `connectors/notion/manifest.toml` | Deliverable | all | Connector: Notion knowledge capability declaration ([#1229](https://github.com/mw-ding/eng-crew/issues/1229)) |
| `core/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `core/crew-config.py` | Deliverable | all | Install CLI: validate and resolve a profile; imports `core/secret-patterns.py` and `core/path-glob.py` ([#281](https://github.com/mw-ding/eng-crew/issues/281)) |
| `core/crew-memory.py` | Deliverable | all | Install CLI: core memory lint (layout, size limits, no personal data) and the section the renderer appends to each brief ([#1230](https://github.com/mw-ding/eng-crew/issues/1230)) |
| `core/crew-pack.py` | Deliverable | all | Install CLI: pack plug-in loader (pack.toml, discovery, version range, floors, commit pin) ([#1236](https://github.com/mw-ding/eng-crew/issues/1236)) |
| `core/crew-render.py` | Deliverable | all | Install CLI: render briefs from the resolved profile |
| `core/crew-roles.py` | Deliverable | all | Install CLI: validate a domain's role definitions |
| `core/crew-routines.py` | Deliverable | all | Install CLI: validate role routines (schedule, skill, generic actions, miss policy) and decide when one is due ([#1247](https://github.com/mw-ding/eng-crew/issues/1247)) |
| `core/markdown-scan.py` | Deliverable | all | Shared module: markdown fence, code-span, comment and link scanning for `docs-scan.py` and the repo guard ([#281](https://github.com/mw-ding/eng-crew/issues/281)) |
| `core/path-glob.py` | Deliverable | all | Shared module: path glob matching for `crew-config.py` and the repo guard ([#281](https://github.com/mw-ding/eng-crew/issues/281)) |
| `core/secret-patterns.py` | Deliverable | all | Shared module: secret-scan patterns for `crew-config.py` and the repo guard ([#281](https://github.com/mw-ding/eng-crew/issues/281)) |
| `core/status-record.py` | Deliverable | all | Shared module: shared-status record S v1 schema, slot body and content identity for `crew-config.py` and the status commands ([#1313](https://github.com/mw-ding/mdstack/issues/1313)) |
| `dev/**` | Internal | n/a | Guards and tests: tests per module, shared test helpers and fixtures (dev/tests/), run by CI and release validation, not installed |
| `docs/README.md` | Internal | n/a | Maintainer docs: the docs index, not loaded by roles |
| `docs/architecture.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/backends/github.md` | Deliverable | all | Protocol bundle (backend binding): GitHub backend binding |
| `docs/backends/notion.md` | Deliverable | all | Protocol bundle (backend binding): Notion knowledge backend binding ([#1229](https://github.com/mw-ding/eng-crew/issues/1229)) |
| `docs/bootstrap.md` | Deliverable | all | Install and upgrade docs: how to install, pin and upgrade |
| `docs/campaign-harness.md` | Internal | n/a | Guards and tests: M25 integration campaign contract ([#783](https://github.com/mw-ding/eng-crew/issues/783)) |
| `docs/concepts.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/configuration/resolution.md` | Deliverable | all | Profile and pack contract: profile validation reference split from the profile ([#857](https://github.com/mw-ding/eng-crew/issues/857)) |
| `docs/configuration/runtime-options.md` | Deliverable | all | Profile and pack contract: runtime keys and shared coordinator option split from the profile ([#859](https://github.com/mw-ding/eng-crew/issues/859)) |
| `docs/configuration/team-files.md` | Deliverable | all | Profile and pack contract: team file schema and example split from the profile ([#855](https://github.com/mw-ding/eng-crew/issues/855)) |
| `docs/decisions.md` | Internal | n/a | Maintainer docs: mdstack's own decisions log, seeded from the #985 decision log ([#1219](https://github.com/mw-ding/eng-crew/issues/1219)) |
| `docs/deliverables.md` | Deliverable | all | Install and upgrade docs: how to install, pin and upgrade |
| `docs/diagrams/**` | Internal | n/a | Maintainer docs: diagrams, not loaded by roles |
| `docs/express-lane.md` | Deliverable | tmux | Profile and pack contract: express flavor design for the tmux binding ([#636](https://github.com/mw-ding/eng-crew/issues/636)) |
| `docs/findings/**` | Internal | n/a | Maintainer docs: findings buffer, not loaded by roles |
| `docs/flavors.md` | Deliverable | all | Profile and pack contract: flavor keys and the floor ([#156](https://github.com/mw-ding/eng-crew/issues/156)) |
| `docs/guides/*.md` | Deliverable | all | Install and upgrade docs: getting-started, connector, pack author and migration guides ([#1238](https://github.com/mw-ding/eng-crew/issues/1238)) |
| `docs/handoff.md` | Deliverable | all | Coordinator procedure: runtime handoff the coordinator runs (#157) |
| `docs/interfaces.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/lessons/**` | Internal | n/a | Maintainer docs: lessons log, history not loaded by roles |
| `docs/memory.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/merge-enforcement.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/metrics/README.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/a31-campaign-report.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/baseline-m25.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/decisions.md` | Deliverable | all | Coordinator procedure: metrics gates the coordinator runs |
| `docs/metrics/m25-1-evidence-ledger.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/m25-report.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/owner-sla-drill.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/prs.csv` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/prs.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/metrics/regression-drills.md` | Internal | n/a | Maintainer docs: metrics and drills, not loaded by roles |
| `docs/observe.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/packs.md` | Deliverable | all | Profile and pack contract: schema packs and installs validate against |
| `docs/personnel.md` | Deliverable | all | Personnel content boundary, pinned host import and fake-host consumer proof (#1180) |
| `docs/profile.md` | Deliverable | all | Profile and pack contract: schema packs and installs validate against |
| `docs/project-doc-set.md` | Deliverable | all | Protocol bundle (core): essential doc set and status banners for target projects, split from the project docs design ([#1024](https://github.com/mw-ding/eng-crew/issues/1024)) |
| `docs/project-docs.md` | Deliverable | all | Protocol bundle (core): project docs consolidation design for target projects ([#754](https://github.com/mw-ding/eng-crew/issues/754)) |
| `docs/protocol.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/reading-paths.md` | Deliverable | all | Protocol bundle (core): role reading paths, navigation to the text roles load and cite ([#760](https://github.com/mw-ding/eng-crew/issues/760)) |
| `docs/release.md` | Deliverable | all | Install and upgrade docs: how to install, pin and upgrade |
| `docs/roles-registry.md` | Deliverable | all | Role registry contract: schema for domain roles (15.7, #317) |
| `docs/roles.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/routines.md` | Deliverable | all | Role routines contract: routine file schema, miss handling and environment bindings (#1247) |
| `docs/runbook-new-repo.md` | Deliverable | all | Install and upgrade docs: how to install, pin and upgrade |
| `docs/runbook.md` | Deliverable | all | Install and upgrade docs: runbook entry point linking the install, run, release and recover owner docs ([#1219](https://github.com/mw-ding/eng-crew/issues/1219)) |
| `docs/runbooks/github-ci-protection.md` | Deliverable | all | Install and upgrade docs: onboarding Step 4 CI discovery and current branch protection inspection, split from the runbook ([#895](https://github.com/mw-ding/eng-crew/issues/895)) |
| `docs/runbooks/github-reviewer-access.md` | Deliverable | all | Install and upgrade docs: onboarding Step 2, reviewer collaborator access, split from the runbook ([#844](https://github.com/mw-ding/eng-crew/issues/844)) |
| `docs/runbooks/github-tracking.md` | Deliverable | all | Install and upgrade docs: onboarding Step 1 `crew:*` label setup, split from the runbook ([#854](https://github.com/mw-ding/eng-crew/issues/854)) |
| `docs/runbooks/grok-onboarding.md` | Deliverable | all | Install and upgrade docs: onboarding Step 6 Grok Bot install-state verification and wiring setup, split from the runbook ([#900](https://github.com/mw-ding/eng-crew/issues/900)) |
| `docs/runbooks/offboarding.md` | Deliverable | all | Install and upgrade docs: onboarding rollback and offboarding, bootstrap uninstall and the ordered manual steps, split from the runbook ([#908](https://github.com/mw-ding/eng-crew/issues/908)) |
| `docs/runbooks/onboarding-proof.md` | Deliverable | all | Install and upgrade docs: onboarding Step 8 first smoke issue template and dispatch, split from the runbook ([#904](https://github.com/mw-ding/eng-crew/issues/904)) |
| `docs/runbooks/prerequisites.md` | Deliverable | all | Install and upgrade docs: onboarding prerequisites, identities and per-identity `gh` usage, split from the runbook ([#891](https://github.com/mw-ding/eng-crew/issues/891)) |
| `docs/runbooks/product-preflight.md` | Deliverable | all | Install and upgrade docs: onboarding Step 5 product-safety preflight (automation ownership, product namespace, fork PRs), split from the runbook ([#898](https://github.com/mw-ding/eng-crew/issues/898)) |
| `docs/runbooks/profile-install.md` | Deliverable | all | Install and upgrade docs: onboarding Step 0 bootstrap install from a profile, split from the runbook ([#852](https://github.com/mw-ding/eng-crew/issues/852)) |
| `docs/runbooks/repo-rename.md` | Deliverable | all | Install and upgrade docs: owner-run repository rename with `mdstack migrate --rename-to` ([#1234](https://github.com/mw-ding/eng-crew/issues/1234)) |
| `docs/runbooks/tmux-onboarding-history.md` | Deliverable | tmux | Install and upgrade docs: dated tmux onboarding run (2026-10-30) split from the runbook as history ([#843](https://github.com/mw-ding/eng-crew/issues/843)) |
| `docs/runbooks/tmux-onboarding.md` | Deliverable | tmux | Install and upgrade docs: tmux onboarding operator module split from the runbook ([#839](https://github.com/mw-ding/eng-crew/issues/839)) |
| `docs/runtimes/README.md` | Deliverable | all | Protocol bundle (runtime contract): contract every binding answers |
| `docs/runtimes/grok-bot.md` | Deliverable | grok-bot | Protocol bundle (runtime binding): runtime gates, watches, routines |
| `docs/runtimes/harness-adapters.md` | Deliverable | all | Protocol bundle (harness adapter interface): how a runtime launches, wakes and probes each agent CLI |
| `docs/runtimes/multi-device.md` | Deliverable | tmux | Protocol bundle (runtime binding): multi-device design for the tmux binding ([#158](https://github.com/mw-ding/eng-crew/issues/158)) |
| `docs/runtimes/session-backends.md` | Deliverable | all | Protocol bundle (session backend interface): how a runtime creates, shows, rings, probes and stops role sessions |
| `docs/runtimes/session.md` | Deliverable | all | Protocol bundle (runtime binding): single-session binding and declared contract gaps (#340, #914) |
| `docs/runtimes/tmux.md` | Deliverable | tmux | Protocol bundle (runtime binding): tmux binding and `mdstack` usage |
| `docs/scheduling.md` | Deliverable | tmux | Protocol bundle (runtime binding): crew-wide scheduler design for the tmux binding ([#587](https://github.com/mw-ding/eng-crew/issues/587)) |
| `docs/self-improve.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `docs/specs/**` | Internal | n/a | Maintainer docs: specs and planning, not loaded by roles |
| `docs/triage.md` | Deliverable | tmux | Protocol bundle (runtime binding): always-on triage design for the tmux binding ([#659](https://github.com/mw-ding/eng-crew/issues/659)) |
| `docs/verification.md` | Deliverable | all | Protocol bundle (core): the text roles load and cite |
| `environments/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `environments/terminal/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `environments/terminal/copy-claim.py` | Deliverable | all | Runtime CLI: host-wide working-copy claims across crews, shared by spawn, the remote entrypoint and `mdstack copy-claim` ([#391](https://github.com/mw-ding/mdstack/issues/391)) |
| `environments/terminal/crew-proc.py` | Deliverable | tmux | Runtime CLI: OS process helpers every session backend shares ([#1183](https://github.com/mw-ding/eng-crew/issues/1183)) |
| `environments/terminal/crew-session.py` | Deliverable | tmux | Runtime CLI: session backend adapter discovery from `sessions/<backend>/adapter.py` ([#1183](https://github.com/mw-ding/eng-crew/issues/1183)) |
| `environments/terminal/crew.d/**` | Deliverable | all | Runtime CLI: per-command modules ([#224](https://github.com/mw-ding/eng-crew/issues/224)) |
| `environments/terminal/remote/crew-remote.py` | Deliverable | tmux | Runtime CLI: hardened remote call: host entrypoint, runner and client ([#208](https://github.com/mw-ding/eng-crew/issues/208)) |
| `environments/terminal/remote/hostos/*.py` | Deliverable | tmux | Runtime CLI: one host OS adapter per OS the remote entrypoint runs on ([#1358](https://github.com/mw-ding/mdstack/issues/1358)) |
| `environments/terminal/remote/lab/**` | Internal | n/a | Local lab: test-host image spec and PID-1 supervisor for testing remote hosts in containers ([#1356](https://github.com/mw-ding/eng-crew/issues/1356)) |
| `environments/terminal/sessions/**` | Deliverable | tmux | Runtime CLI: one adapter module per session backend ([#1183](https://github.com/mw-ding/eng-crew/issues/1183)) |
| `harnesses/*/adapter.py` | Deliverable | all | Runtime CLI: one adapter module per harness ([#1182](https://github.com/mw-ding/eng-crew/issues/1182)) |
| `harnesses/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `harnesses/crew-harness.py` | Deliverable | all | Runtime CLI: harness adapter discovery and the engine tables derived from `harnesses/<engine>/adapter.py` ([#1182](https://github.com/mw-ding/eng-crew/issues/1182)) |
| `memory/**` | Internal | n/a | mdstack's own crew core memory (owner profile, per-role files), injected into its briefs; another project keeps its own ([#1230](https://github.com/mw-ding/eng-crew/issues/1230)) |
| `packs/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `profiles/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `profiles/default.toml` | Deliverable | grok-bot | Profile: default profile (spec P7) |
| `profiles/session.toml` | Deliverable | session | Example profile: session example profile |
| `profiles/tmux.toml` | Deliverable | tmux | Example profile: tmux example profile |
| `roles/README.md` | Deliverable | all | Module README: purpose, contents and how the module plugs in ([#1237](https://github.com/mw-ding/eng-crew/issues/1237)) |
| `roles/eng/**` | Deliverable | tmux | Domain registry: one engineering role definition per file, loaded by the tmux runtime, and each role's `routines/` |
| `roles/seats/**` | Deliverable | all | Owner-facing seat placeholder packages and the seat template; content authored elsewhere |
| `scripts/README.md` | Deliverable | all | Script usage: script guide and guard rules; each script's own usage is its module docstring, printed by `--help` |
| `scripts/campaign-attended.py` | Internal | n/a | Guards and tests: M25 attended owner-channel and sleep run driver, not installed ([#1463](https://github.com/mw-ding/mdstack/issues/1463)) |
| `scripts/campaign-guard.py` | Internal | n/a | Guards and tests: M25 campaign run-manifest and isolation guard, not installed ([#783](https://github.com/mw-ding/eng-crew/issues/783)) |
| `scripts/campaign-lint.py` | Internal | n/a | Guards and tests: campaign step assertion lint and required-case retention, not installed ([#1412](https://github.com/mw-ding/mdstack/issues/1412)) |
| `scripts/campaign-report.py` | Internal | n/a | Maintainer tool: A31 campaign-history report from actual campaign records ([#1462](https://github.com/mw-ding/mdstack/issues/1462)) |
| `scripts/campaign-run.py` | Internal | n/a | Guards and tests: M25 campaign scenario runner and durable results, not installed ([#784](https://github.com/mw-ding/eng-crew/issues/784)) |
| `scripts/campaign-sandbox.py` | Internal | n/a | Guards and tests: M25 disposable sandbox setup, teardown and level-b plan, not installed ([#785](https://github.com/mw-ding/eng-crew/issues/785)) |
| `scripts/changelog-cut.py` | Deliverable | all | Release helper: cut the CHANGELOG and fragments into a version section; the `release.cut` binding runs it from the installed bundle ([#1033](https://github.com/mw-ding/mdstack/issues/1033)) |
| `scripts/check-changelog-pr.py` | Internal | n/a | Guards and tests: PR fragment requirement, run by CI, not installed |
| `scripts/check-markdown.py` | Deliverable | all | Install CLI: local markdownlint parity; `check-repo.py` loads it for its `markdown` check ([#644](https://github.com/mw-ding/eng-crew/issues/644)) |
| `scripts/check-pr-linkage.py` | Deliverable | all | Role helper: builder's PR body linkage check, allocation and closing keywords ([#1418](https://github.com/mw-ding/mdstack/issues/1418)) |
| `scripts/check-repo.py` | Internal | n/a | Guards and tests: the repo guard, run by CI and builders, not installed; shared primitives ship in `core/` ([#281](https://github.com/mw-ding/eng-crew/issues/281)) |
| `scripts/check-skill-drift.py` | Deliverable | all | Drift check: render-vs-live check ([#128](https://github.com/mw-ding/eng-crew/issues/128)) |
| `scripts/crew-install.py` | Deliverable | all | Install CLI: shared release verifier and `transport` record for bootstrap, upgrade and host prepare ([#882](https://github.com/mw-ding/eng-crew/issues/882)) |
| `scripts/crew-precheck.py` | Deliverable | all | Role helper: check enabled builder pre-review markers at head |
| `scripts/deliverables.txt` | Internal | n/a | Guards and tests: the manifest this inventory is generated from |
| `scripts/deps-baseline.txt` | Internal | n/a | Guards and tests: dependency-rule baseline of known couplings, run by CI, not installed |
| `scripts/design-headers.txt` | Internal | n/a | Guards and tests: design-header allowlist for the `design-headers` check, run by CI, not installed ([#259](https://github.com/mw-ding/eng-crew/issues/259)) |
| `scripts/docs-scan.py` | Deliverable | all | Role helper: zero-model project docs scan ([#1025](https://github.com/mw-ding/eng-crew/issues/1025)) |
| `scripts/evidence-cli.py` | Deliverable | all | Role helper: capture CLI evidence pairs mechanically ([#652](https://github.com/mw-ding/eng-crew/issues/652)) |
| `scripts/flavor-suggest.py` | Deliverable | all | Role helper: offline flavor signals and owner-decided suggestions |
| `scripts/intake-sweep.py` | Deliverable | all | Role helpers: builder and coordinator helpers |
| `scripts/item-flavor.py` | Deliverable | all | Role helper: item rigor records, defaults and lowering reasons |
| `scripts/metrics-baseline.py` | Internal | n/a | Maintainer tool: baseline pipeline metrics before the reorganization ([#1220](https://github.com/mw-ding/eng-crew/issues/1220)) |
| `scripts/metrics-decide.py` | Deliverable | all | Role helpers: builder and coordinator helpers |
| `scripts/metrics-refresh.py` | Deliverable | all | Role helpers: builder and coordinator helpers |
| `scripts/personnel-bundle.py` | Deliverable | all | Producer-only personnel content exporter (#1180) |
| `scripts/personnel-files.txt` | Deliverable | all | Explicit personnel content manifest (#1180) |
| `scripts/reflection-candidates.py` | Deliverable | all | Role helper: offline reflection threshold candidates (findings rows and recurring classes) matched to existing cards ([#1522](https://github.com/mw-ding/mdstack/issues/1522)) |
| `scripts/reflection-effects.py` | Deliverable | all | Role helper: offline reflection effect table, a before/after row and keep/revise/revert recommendation per accepted proposal ([#1525](https://github.com/mw-ding/mdstack/issues/1525)) |
| `scripts/reflection-measures.py` | Deliverable | all | Role helpers: offline reflection effect measures from poll and watch observations ([#1524](https://github.com/mw-ding/mdstack/issues/1524)) |
| `scripts/reflection-scan.py` | Deliverable | all | Role helper: offline reflection evidence index over forge snapshots, lessons and findings at a SHA ([#1518](https://github.com/mw-ding/mdstack/issues/1518)) |
| `scripts/release-bundle.py` | Internal | n/a | Guards and tests: release tooling, run by the release workflow, not installed |
| `scripts/release-check.py` | Internal | n/a | Guards and tests: release tooling, run by the release workflow, not installed |
| `scripts/release-compat.py` | Internal | n/a | Guards and tests: release tooling, run by the release workflow, not installed |
| `scripts/release-trigger.py` | Internal | n/a | Guards and tests: release tooling, run by the release workflow, not installed |
| `scripts/required-docs.txt` | Internal | n/a | Guards and tests: required docs and sections, run by CI |
| `scripts/run-tests.py` | Internal | n/a | Guards and tests: parallel test runner, run by CI, not installed |
| `scripts/run-usage.py` | Deliverable | all | Role helper: a pass's usage line, wall-clock time, tokens from the harness session log, and model ([#1557](https://github.com/mw-ding/mdstack/issues/1557)) |
| `scripts/step-summary.py` | Deliverable | all | Role helpers: builder and coordinator helpers |
| `scripts/triage-clusters.py` | Deliverable | all | Role helper: triage clusters of related open issues with stable slugs and cap-counted proposals ([#1298](https://github.com/mw-ding/mdstack/issues/1298)) |
| `scripts/triage-metrics.py` | Deliverable | all | Role helper: triage shadow-mode spot check, precision bar, metrics and eval set ([#750](https://github.com/mw-ding/eng-crew/issues/750)) |
| `scripts/worktree-purge.py` | Internal | n/a | Guards and tests: one-off crew-host worktree purge, dry-run first, not installed ([#1161](https://github.com/mw-ding/eng-crew/issues/1161)) |
| `templates/README.md` | Deliverable | all | Templates: evidence adapters, product README seed, cards and step lines |
| `templates/backends/github.toml` | Deliverable | all | Render input: `<op:...>` command mapping |
| `templates/backends/slack.toml` | Deliverable | tmux | Render input: away-only Slack notify and recorded GitHub asks |
| `templates/evidence/**` | Deliverable | all | Templates: evidence adapters, product README seed, cards and step lines |
| `templates/flavor-suggestion-issue.md` | Deliverable | all | Template: owner-decided flavor suggestion issue |
| `templates/handoff-manifest.md` | Deliverable | all | Template: runtime handoff manifest that `mdstack handoff manifest` fills ([#211](https://github.com/mw-ding/eng-crew/issues/211)) |
| `templates/intake-candidate.md` | Deliverable | all | Templates: evidence adapters, product README seed, cards and step lines |
| `templates/metrics-regression-issue.md` | Deliverable | all | Templates: evidence adapters, product README seed, cards and step lines |
| `templates/owner-return-brief.md` | Deliverable | all | Template: standalone owner return brief for recorded away mode |
| `templates/personnel/**` | Deliverable | all | Personnel composition input for hosts bringing their own machinery (#1180) |
| `templates/policy/**` | Deliverable | all | Render input: role policy fragments the runtime templates include, and role skills (Agent Skills format) that index them ([#1184](https://github.com/mw-ding/eng-crew/issues/1184), [#1221](https://github.com/mw-ding/eng-crew/issues/1221)) |
| `templates/product-readme.md` | Deliverable | all | Templates: evidence adapters, product README seed, cards and step lines |
| `templates/runtimes/grok-bot/**` | Deliverable | grok-bot | Render input: routines and trigger JSON, rendered at install |
| `templates/runtimes/session/**` | Deliverable | session | Template: session coordinator and worker briefs |
| `templates/runtimes/tmux/**` | Deliverable | tmux | Render input: coordinator and role briefs, rendered at install |
| `templates/spec.md` | Deliverable | all | Template: spec seed for a project's `docs/specs/` with banner and structured requirements ([#1219](https://github.com/mw-ding/eng-crew/issues/1219)) |
| `templates/step-summary.md` | Deliverable | all | Templates: evidence adapters, product README seed, cards and step lines |
| `templates/triage-flavor.md` | Deliverable | all | Template: coordinator item rigor record and lowering reason |

<!-- inventory:end -->

Coordinator session helpers are not in the repo yet; they become
deliverables once upstreamed ([release.md](release.md#upstreaming-the-session-tooling)).

Issue templates: this repo's own `.github/ISSUE_TEMPLATE/` (the intake card)
stays internal with `.github/**`. Product-repo issue templates would be
deliverables under `templates/`.

A new tracked path must be classified when it lands: the manifest is the
machine-readable source of this table, and the bundle build and the repo guard
fail on an unclassified path ([release.md](release.md#follow-up-issues)).

## Packaging

| Decision | Choice | Alternatives considered |
|---|---|---|
| Unit | One bundle per release, `mdstack-<version>.tar.gz`, holding every deliverable at its repo path, plus `VERSION` and `SHA256SUMS` | One tarball per runtime: more build and install paths for a few small files; revisit when a runtime's files outgrow this. A committed `dist/<runtime>/` tree: generated files in git drift, the same problem as hand mirroring |
| Per-runtime selection | At install: the renderer reads only the profile's `runtime.name` inputs, so one bundle serves every runtime | Rendering per runtime at release time: the render needs project values (`repo.owner`, identities, paths), which only the install has |
| Rendered output | Generated at install by `crew-render.py` from the bundle and the resolved profile, then deployed and drift-checked ([#128](https://github.com/mw-ding/eng-crew/issues/128)) | Shipping a reference render of `profiles/default.toml`: its values are placeholders, so it adds nothing over the templates |
| Harness layouts (Claude Code subagents and skills, Codex prompts, Grok Bot box skills) | Future render targets of the same bundle, decided by bootstrap ([#144](https://github.com/mw-ding/eng-crew/issues/144) install targets) | A Claude Code plugin as the release unit: one harness only |
| Links | A relative link from a deliverable to an internal path is rewritten to the file at the release tag on GitHub, so the bundle has no broken link and stays small | Shipping lessons and specs: they are history, not rules |
| Source archive | GitHub's automatic source archive of the tag stays available for a full checkout | none |

`cli/mdstack` is an entry point plus per-command modules in
`environments/terminal/crew.d/`
([#224](https://github.com/mw-ding/eng-crew/issues/224),
[#1222](https://github.com/mw-ding/eng-crew/issues/1222)); the bundle ships the
whole module directory, so the split changes no packaging rule.

## Versioning

SemVer, tagged `vMAJOR.MINOR.PATCH` (owner decision, R1 milestone). The
release id is what `release.record-release` writes
([release operations](release.md#release-operations)): a tag here, or, for a
project with `release_id = "commit"` in its
[`[release]` table](profile.md#release), the full 40-character hash of the
landed cut commit ([commit release id](release.md#commit-release-id)). The
version number and the rules below are the same for both. The
public surface is the deliverables above. A change is breaking when an
environment installed at the previous version, or a pack pinned to it, would
stop working or stop complying without edits.

| Bump | Change to a deliverable |
|---|---|
| Major | A [§7](protocol.md#7-merge-gate-synthesizer) merge gate or the release gate added, removed, or satisfied differently; a `crew:v1` marker field removed, renamed, newly required or changed in meaning; a `crew:*` state tag removed, renamed or changed in meaning; a profile key removed, renamed, newly required or retyped; a pack manifest field or [interface](interfaces.md) operation removed or newly required; a runtime contract capability newly required; a `crew` command or flag removed, or a changed exit code or parsed output; a render placeholder removed or renamed |
| Minor | An optional profile key with a default; a new optional marker field old readers ignore; a new command, flag, template, script, runtime or backend binding; a new role duty that adds no gate |
| Patch | A fix that restores documented behaviour; wording that changes no rule; docs and test-only changes to deliverables |
| None | Any change to internal paths only |

Rules:

- A breaking CHANGELOG entry starts with `**Breaking:**` and carries a
  one-line migration step. The entries since the last tag decide the
  smallest allowed bump; the release approver checks the cut PR's version
  against them ([release.md](release.md#steps)). Release validation also
  refuses a minor or patch when a manifest the published predecessor's
  validator accepted fails the new one
  ([manifest compatibility](release.md#manifest-compatibility)).
- Pre-release versions (`vX.Y.Z-rc.N`) are allowed for a smoke run and never
  satisfy a pin, whatever the release id.
- Only the latest release is supported. Fixes go forward as a new release;
  there are no backport branches unless the owner asks for one.

## Compatibility promise

| To | Promise |
|---|---|
| Packs ([#127](https://github.com/mw-ding/eng-crew/issues/127)) | The [version pin](packs.md#version-pin) rule is unchanged: a pack is supported at its pinned version. Once tags exist the pin is a tag, not a SHA; under a commit release id the pin is the recorded hash. Within one major, a manifest and pack profile that pass `validate` and `resolve` at the pin also pass at any later minor or patch, so moving the pin inside a major needs no pack edit |
| Installed environments ([#144](https://github.com/mw-ding/eng-crew/issues/144)) | Within one major, upgrading is re-render, drift check, deploy, with no profile edit. Across a major, the `**Breaking:**` entries list every edit the profile, pack or live copy needs |
| Live roles | A role's behaviour changes only when its environment takes a new version; nothing auto-updates ([release.md](release.md#update-path)) |

## First versions

Owner decisions (R1 milestone, [#219](https://github.com/mw-ding/eng-crew/issues/219)),
reflected here, not re-decided:

| Tag | Commit | Why |
|---|---|---|
| `v1.0.0` | The M12 cut: the commit that locked the README "v1 cut" (candidate `b2144a28198f26f6dc6cc0a8b2135a1e38d852ba`, PR #95; [#219](https://github.com/mw-ding/eng-crew/issues/219) confirms it) | Retro-tag of M1–M12 |
| `v2.0.0` | The M14 cut, after the [#139](https://github.com/mw-ding/eng-crew/issues/139) smoke | Major: M13/M14 change the profile layout, the runtime and the gates (the mirror gate is now a drift check), all breaking under the table above |

No `v1.x` release is cut between them. `v1.0.0` has no bundle (the bundle
build lands later); its source archive is the artifact.
