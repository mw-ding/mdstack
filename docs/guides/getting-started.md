# Getting started

A first run on the terminal (tmux) environment: install into the home root,
start the team, talk to its head and add a role on demand. This guide is
navigation only. Each step links to the doc that owns its exact behaviour,
and the [tmux binding](../runtimes/tmux.md) owns every command. Already
running an older install? Read the [migration guide](migration.md) first.

## Before you start

- Python 3.11+, tmux, `gh` logged in, and at least one coding harness
  ([harness adapters](../runtimes/harness-adapters.md)).
- A target repo you own, with a CI check on every PR and two GitHub
  identities: an author and a different reviewer
  ([prerequisites](../runbooks/prerequisites.md)).

## 1. Install into the home root

The default layout keeps every installed piece in one place, `~/.mdstack/`,
with only your repo checkout outside it
([home-level layout](../runtimes/tmux.md#home-level-layout-1178)):

| Path | Holds |
|---|---|
| `~/.mdstack/` | The home root: `config.toml`, the `start` and `start-owner` wrappers, `releases/mdstack-X.Y.Z/` bundles with the `releases/current` link, and the `bin/mdstack` launcher. It is not a git checkout |
| `~/.mdstack/state/` | State, including the install link |
| `~/.mdstack/runs/<repo>/` | Role worktrees |
| `~/.mdstack/live/` | The live copy |
| `~/<repo>/` | Your repo's checkout (`paths.checkout`), the only thing outside |

`~/.mdstack/config.toml` is the user-level config: every command uses it
when you pass no `--project`. A project-level `config.toml`, passed with
`--project FILE`, is the secondary option for a separate project-group stack
([user-level and project-level config](../runtimes/tmux.md#user-level-and-project-level-config-1316)).

Download, verify and extract a release bundle into `~/.mdstack/releases/`
([README Install](../../README.md#install) steps 1 to 4). Write
`~/.mdstack/config.toml` from the bundle's `profiles/tmux.toml`, with your
`[repo]` and identities; its default `[paths]` block already names this layout
([Set up the target repo](../runbook-new-repo.md#set-up-the-target-repo)).
Put a stable `mdstack` on your `PATH`, then install with one command, a dry
run first:

```sh
~/.mdstack/releases/mdstack-X.Y.Z/cli/mdstack install
mdstack bootstrap --dry-run
mdstack bootstrap --yes
```

`mdstack install` writes the launcher `~/.mdstack/bin/mdstack`, which runs
the release `~/.mdstack/releases/current` points at, and links it into a
user directory already on your `PATH` (for example `~/.local/bin`), or
prints the one line to add to your shell profile; it never edits one
([mdstack install](../runtimes/tmux.md#mdstack-install)).

Bootstrap checks the bundle, validates and records the profile, sets up the
repo side (the `crew:*` labels, a milestone, the reviewer invitation),
renders the briefs and records the install in `install.json`. Its refusals and outputs are in
[bootstrap](../bootstrap.md#home-level-layout-and-relocation-1178) and the
[profile install runbook](../runbooks/profile-install.md). Then write the
one-command start wrappers:

```sh
mdstack layout --write
```

Later releases upgrade in place, like any end-user tool:
`mdstack upgrade --version vX.Y.Z` (or `--latest`) fetches and verifies the
release, re-renders every project this install serves and moves
`releases/current`, so `mdstack --version` reports the new tag; the same
command with the previous tag rolls back
([update path](../release.md#update-path)).

## 2. First `up`

```sh
mdstack start             # or ~/.mdstack/start: start the crew, or reattach to window 0
mdstack status
```

`mdstack start` runs `mdstack up`, which renders the briefs and starts one
tmux session holding the coordinator `ash` (window 0) and the pool leads
([Bringing up the team](../../README.md#bringing-up-the-team)), then attaches
this terminal to window 0; run again, it reattaches without a second session
([mdstack start](../runtimes/tmux.md#mdstack-start)). On the first start,
accept each harness's trust dialog once: a Claude Code `ash` waits at its
folder-trust dialog in window 0
([Quickstart step 5](../../README.md#quickstart-tmux)). Stop everything with
`mdstack down`.

## 3. Talk to the team head

The coordinator, `ash`, is the engineering team's head and holds the `cto`
seat. It is the one role that faces you; every other role is internal staff
that escalates to it ([role classes](../roles-registry.md#role-classes)).

- **Live:** `mdstack attach ash --rw` and type.
  Without `--rw` the attach is read-only.
- **On the tracker:** open an issue with numbered acceptance criteria, label
  it `crew:ready` and assign it, or ask `ash` to file one. `ash` routes it and
  the pipeline runs; you give the merge-ok
  ([owner duties](../runbook-new-repo.md#run-the-crew)).
- **Steering:** `/crew` commands on an issue or PR
  ([protocol §9](../protocol.md#9-steering-crew-commands)).

## 4. Add an on-demand role

Builders, reviewers, the synthesizer and researchers start by themselves
as work arrives. A role whose definition has a
[`lifecycle`](../roles-registry.md#lifecycle) with the `manual` wake also
starts when you ask:

```sh
mdstack up <role>
```

Each call starts one more instance, up to the role's `max`. The watcher kills
an instance that stays idle for `idle_ttl` seconds, down to `min`, so an
`ephemeral` role scales to zero. The engineering roles have no `lifecycle`,
so `up <role>` refuses them (exit 2).

To add a new role, write `roles/<domain>/<role>.toml` with a `lifecycle` table
and the brief its `templates` names, then validate it:

```sh
python3 core/crew-roles.py roles/<domain> --project ~/.mdstack/config.toml
```

See [Adding a role](../roles-registry.md#adding-a-role) for what a definition
may reuse, and [routines](../routines.md) for a role that wakes on a schedule.

## Next

- Pick tools other than GitHub, or add a knowledge source:
  [configuring connectors](connectors.md).
- Rigor per project or item: [flavors](../flavors.md).
- Upgrade, recover or relocate: the [runbook](../runbook.md).
