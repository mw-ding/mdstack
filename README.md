# mdstack

mdstack is a multi-agent engineering crew for a GitHub repo. A small team of
agent roles takes an issue from spec to merged PR, with CI, typed evidence and
a human-readable trail at every step, while you keep the merge decision. It
ships as an installable launcher and runtime plus the versioned, reviewed
rules the roles follow, so "let an AI write code" comes with clear roles,
gates and a record of who did what.

New here? Check the [prerequisites](#prerequisites), then follow the
[Quickstart](#quickstart-tmux), or the full
[getting-started walkthrough](docs/guides/getting-started.md). Running a role?
The [reading paths](docs/reading-paths.md) show what each role reads and when.
Changing this repository itself? Follow [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

Each role has one job. The default profile gives each role a persona name,
which is also its tmux window:

| Role | Job | Default persona |
|---|---|---|
| Coordinator | Turns a spec into issues with numbered acceptance criteria, routes work and closes out | Ash |
| Builder | Picks up an issue and opens a PR with evidence | Ben |
| Reviewer-validator | A different identity or engine from the author; reviews and validates, then posts a verdict | Vera |
| Synthesizer | Checks every merge gate and lands the PR | Sam |
| Researcher | Answers research requests, triage sweeps and docs passes | Riley |

CI runs on every PR. When review and CI both pass the merge gate, the
synthesizer merges and the coordinator closes out. Loops are capped, and every
handoff is a marker on the PR.

- How it fits together: the canonical
  [deployment, wake and release diagram](docs/architecture.md#deployment-wakes-and-releases);
  stage and module diagrams in [docs/architecture.md](docs/architecture.md)
- Stages, markers, rounds and the merge gate: [docs/protocol.md](docs/protocol.md)
- Roles, tiers and engines: [docs/roles.md](docs/roles.md)
- Rigor per item (review depth, evidence, caps): [docs/flavors.md](docs/flavors.md)

## Who it's for

- Maintainers who want agents to build and review changes in their repo
  without giving up a merge gate.
- Engineers adopting the crew on a new repo, via the
  [onboarding runbook](docs/runbook-new-repo.md).

## What you get

- The `mdstack` launcher and the terminal (tmux) runtime that starts, watches
  and stops the crew.
- A staged protocol with typed evidence, review rounds and a merge gate.
- Role briefs rendered from templates with placeholders only
  ([templates/](templates/README.md)), and a seed README for product repos
  ([templates/product-readme.md](templates/product-readme.md)).
- Guard scripts that scan for secrets and check docs and links in CI.
- A lessons log and a changelog of every change.
- Versioned releases: what ships and what each version promises is in
  [docs/deliverables.md](docs/deliverables.md); how a release is cut is in
  [docs/release.md](docs/release.md).

## Prerequisites

Have these before you install:

- **Tools:** Python 3.11+, git, tmux, and `gh` logged in.
- **A coding harness:** at least one supported agent CLI, logged in, such as
  Claude Code or Codex ([harness adapters](docs/runtimes/harness-adapters.md)).
  The reviewer-validator's engine must differ from the builder's
  ([reviewer engine selection](docs/roles.md#reviewer-engine-selection)), so
  plan for two, such as Claude Code and Codex.
- **A target repo** you can administer, with a CI check that runs on every PR.
- **An identity choice:**
  - one GitHub account for every role, as in the sample
    [profiles/tmux.toml](profiles/tmux.toml): verdicts are emulated, and you
    record a merge-ok for each change
    ([single-identity profile](docs/interfaces.md#single-identity-profile)); or
  - a separate reviewer account, so the reviewer-validator posts real
    approvals ([identities](docs/runbooks/prerequisites.md#identities)).
- **You, as owner:** available to answer the crew's decisions and give the
  merge-ok ([owner duties](docs/runbook-new-repo.md#run-the-crew)).

The full checklist, with token scopes, is
[runbooks/prerequisites.md](docs/runbooks/prerequisites.md).

## Install

1. **Download and verify** the latest release (to pin a version, pass its
   tag: `gh release download vX.Y.Z ...`; the repo is public, so the assets
   are also on the [Releases](https://github.com/mw-ding/mdstack/releases)
   page):

   ```bash
   gh release download -R mw-ding/mdstack --pattern 'mdstack-*.tar.gz' --pattern SHA256SUMS -D mdstack-release
   cd mdstack-release && shasum -a 256 -c SHA256SUMS  # Linux: sha256sum -c SHA256SUMS
   ```

2. **Extract** into the home root:
   `mkdir -p ~/.mdstack/releases && tar -xzf mdstack-*.tar.gz -C ~/.mdstack/releases`.
   The `mdstack-<version>/` directory is `<mdstack>` below, and its `VERSION`
   file is the version to record
   ([release.md: Update path](docs/release.md#update-path)).
3. **Check the tools run:**
   `python3 <mdstack>/core/crew-config.py validate <mdstack>/profiles/default.toml`
   and `<mdstack>/cli/mdstack --help`.
4. **Put `mdstack` on `PATH`:** `<mdstack>/cli/mdstack install`. It points
   `~/.mdstack/releases/current` at that bundle, writes the launcher
   `~/.mdstack/bin/mdstack` and links it into a user directory already on
   your `PATH` (for example `~/.local/bin`), or prints the one line to add to
   your shell profile; it never edits one. `mdstack --version` then prints
   the tag.

Upgrades: `mdstack upgrade --version vX.Y.Z` (or `--latest`) fetches,
verifies and re-renders, then moves `releases/current`, so the launcher
follows with no `PATH` change; the previous tag rolls back
([release.md: Update path](docs/release.md#update-path)). Coming from an
older install, read the [migration guide](docs/guides/migration.md) first:
8.0.0 drops `--project` from owner commands. Older bundles carry
version-specific caveats (the `v2.0.0` bundle fails step 3; tmux users
upgrading to 2.1 need its upgrade note) in the
[release notes](https://github.com/mw-ding/mdstack/releases).

## Quickstart (tmux)

The compact launch path. The
[getting-started walkthrough](docs/guides/getting-started.md) is the one
complete guide, with the copyable config, the first issue and the expected
review, CI and merge results; the [tmux binding](docs/runtimes/tmux.md) owns
every command. `<repo>` is your target repo, cloned at `~/<repo>`.
Everything installed lives in `~/.mdstack/`
([home-level layout](docs/runtimes/tmux.md#home-level-layout-1178)).

1. **Install** as [above](#install).
2. **Write `~/.mdstack/config.toml`** from
   [profiles/tmux.toml](profiles/tmux.toml) plus your `[repo]` and
   identities ([copyable block](docs/guides/getting-started.md#2-write-the-config)),
   and check it resolves:
   `python3 <mdstack>/core/crew-config.py resolve --project ~/.mdstack/config.toml`.
   Owner commands take no `--project`: they use `$MDSTACK_CONFIG`, else this
   file. Create the `crew:*` labels and a milestone with
   `mdstack doctor --fix --milestone M1`
   ([Step 1](docs/runbook-new-repo.md#step-1-create-the-crew-labels)).
3. **Bootstrap:** `mdstack bootstrap --dry-run`, review it, then run it
   without `--dry-run`
   ([Bootstrap](docs/runbook-new-repo.md#bootstrap-recommended)).
4. **Start:** `mdstack start`, from any directory. It starts the session with
   `ash` and the enabled leads and attaches to window 0; run it again to
   reattach ([mdstack start](docs/runtimes/tmux.md#mdstack-start)).
5. **Trust each harness once.** A Claude Code `ash` waits at its folder-trust
   dialog (`mdstack status` shows `ambiguous`): run `mdstack attach ash --rw`
   and accept it; never press a blind Enter, which picks `No, exit`. Codex
   needs every hook in your host Codex config trusted once in plain `codex`.
   Other harnesses: each [adapter](docs/runtimes/harness-adapters.md)'s
   trust row.
6. **First issue:** open an issue with numbered acceptance criteria, label it
   `crew:ready` and assign it, or ask `ash` in window 0 to file one. The pipeline runs; you
   give the merge-ok.
7. **Watch and stop:** `mdstack status`, `mdstack attach <window>`
   (read-only without `--rw`) and `mdstack down`. Problems:
   [tmux troubleshooting](docs/runbook-new-repo.md#tmux-troubleshooting);
   day-to-day tasks: the [operations runbook](docs/runbook.md).

### Bringing up the team

Default profile names; window indexes from the
[tmux binding](docs/runtimes/tmux.md#layout-and-naming).

| Role | Window | Started by |
|---|---|---|
| Coordinator | `ash` (0) | `mdstack up` |
| Builder lead | `ben-lead` (2) | `mdstack up`, unless the [launch topology](docs/runtimes/tmux.md#launch-topology) or `--coordinator-only` says otherwise |
| Reviewer lead | `vera-lead` (3) | `mdstack up`, same exception |
| Builder | `ben-<issue>` (10–19) | The builder lead, when `ash` hands it a ready issue and the scheduler admits it; fix rounds reuse the window |
| Reviewer-validator | `vera-<pr>-r<k>-<pass>` (20–29) | The reviewer lead, one fresh window per pass: review on each new head (CI pending or red included), validate after a passed review when the flavor requires it, recheck on its handoff. Green CI gates the merge, not the review |
| Synthesizer | `sam` (1) | `ash`, with `mdstack spawn synthesizer` at the first land; it then stays for the session |
| Researcher | `riley-<issue>`, `riley-sweep` or `riley-docs` (40–44) | `ash`, per research request, triage sweep or docs pass; closed after its `done:` |

## Runtimes and harnesses

The terminal (tmux) runtime is the shipped way to run a crew. Which runtimes
and harnesses are supported, attended-only or design, and their declared
gaps: the [support table](docs/runtimes/README.md#support) and the
[harness adapters](docs/runtimes/harness-adapters.md).

## Release and support

- **Released:** 8.0.0 (2026-11-18) is the newest release
  ([CHANGELOG.md](CHANGELOG.md),
  [GitHub Releases](https://github.com/mw-ding/mdstack/releases)).
- **Current source:** `main` carries changes since that cut as fragments in
  `changes/unreleased/` until the next release (the [Unreleased](CHANGELOG.md#unreleased)
  section stays empty until then). Source on
  `main` is not a release, and installing one is a separate step.
- **Support:** only the latest release is supported; fixes go forward as a new
  release ([versioning](docs/deliverables.md#versioning)). Report bugs and ask
  questions in [GitHub issues](https://github.com/mw-ding/mdstack/issues).
- **History:** per-milestone delivery status is in
  [docs/specs/portable.md](docs/specs/portable.md) and the
  [closed milestones](https://github.com/mw-ding/mdstack/milestones?state=closed);
  platform merge enforcement and its limits are in
  [docs/merge-enforcement.md](docs/merge-enforcement.md).

The crew builds this repository itself through the normal PR pipeline.

## More

- Specs: [docs/specs/team.md](docs/specs/team.md) (module layout, four
  axes, dependency rules), [docs/specs/portable.md](docs/specs/portable.md)
  (invariants, extension mechanism) and
  [docs/specs/framework.md](docs/specs/framework.md) (original requirements
  R1–R8)
- Every doc: [docs index](docs/README.md)
- Lessons log: [docs/lessons/](docs/lessons/README.md)
- No secrets or tokens are ever committed here. Per-repo specifics are templates
  with placeholders.
