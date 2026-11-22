# Migration guide

Each section moves an install from one release line to the next, newest
first. Upgrades within a line follow
[release.md: Update path](../release.md#update-path); the
[CHANGELOG](../../CHANGELOG.md) entries are the record. Sections for older
releases are version history: their commands are the forms that release
took.

## 7.x to 8.0.0: owner commands without `--project`

8.0.0 removes `--project` from the owner CLI (#1965). An owner shell (no
`CREW_ROLE`) uses the installed team: `$MDSTACK_CONFIG`, else
`~/.mdstack/config.toml`, else the root's only `<team>.toml`. `--project`
in any spelling, and a `<home>/start` written before 8.0.0, exit 2 before
any read or write:

```text
mdstack: --project is disabled; mdstack uses the installed team (<path>). Set MDSTACK_CONFIG to override.
```

Crew windows are unchanged: they keep `--project` and `$CREW_PROJECT`
([owner shell](../runtimes/tmux.md#user-level-and-project-level-config-1316)).

1. **Upgrade:** from 7.16.0, `mdstack upgrade --latest --dry-run`, then
   `--yes` ([bootstrap Q8](../bootstrap.md#q8-idempotency-upgrade-and-uninstall)).
   This plain command works when the target is the first release after
   8.1.0 or later: from it on, 8.x accepts the 7.x bootstrap's verified
   `upgrade --project` re-exec (#2024). Upgrading straight to 8.0.0 or 8.1.0
   refuses that re-exec with the `--project is disabled` line above; run
   `MDSTACK_INTERNAL=1 mdstack upgrade --latest --dry-run` (or
   `--version v8.1.0`), then the same with `--yes`. The profile needs no
   edit. For a profile other than the default, set `MDSTACK_CONFIG` to its
   path, which 7.x also reads.
2. **Drop `--project` from owner commands and scripts:** shell aliases,
   wrappers, cron jobs and hooks that call `mdstack`.

   | 7.x | 8.0.0 |
   |---|---|
   | `mdstack up --project ~/.mdstack/config.toml` | `mdstack up` |
   | `mdstack doctor --project <team file>#<repo>` | `mdstack doctor --repo <repo>` |
   | `mdstack up --project <other config.toml>` | `MDSTACK_CONFIG=<other config.toml> mdstack up` |

   A single-repo team needs no `--repo`. In a multi-repo team, `up`,
   `start` and a bare `attach` take the whole team; every other command
   needs `--repo <key>` (`--team-repo <key>` for `content` and `feedback`)
   and exits 2 naming the keys without it. Give `MDSTACK_CONFIG` an
   absolute path; it may name `<file>#<repo>`.
3. **Regenerate the wrappers:** `mdstack layout --write` (with the same
   `--owner-cmd` as before) rewrites `<home>/start` to set
   `MDSTACK_CONFIG` ([mdstack layout](../runtimes/tmux.md#mdstack-layout)).
4. **Check:** `mdstack doctor`, then `mdstack start`.

Leave crew-side commands alone: role briefs, `$CREW_BIN` calls in crew
windows, and the low-level tools (`core/crew-config.py`,
`core/crew-render.py`, `scripts/changelog-cut.py`) keep `--project`.

## 6.x or older to 7.0.0: reinstall from scratch (version history)

7.0.0 is a fresh install. It carries no 6.x or older install forward: no
compatibility shims, aliases, links or migration steps (#1312). The commands
below are the 7.x forms; on 8.0.0, drop `--project` as above.

### What to do, in order

1. **Stop the old crew:** `down --preserve` with the old install's CLI, and
   land or park any open work.
2. **Install 7.0.0** from the release bundle
   ([README: Install](../../README.md#install)): download and check
   `mdstack-<version>.tar.gz`, extract it, and run
   `<mdstack>/cli/mdstack bootstrap --project ~/.mdstack/config.toml --dry-run`,
   then `--yes`.
3. **Update your profile and scripts** to the 7.0.0 names below: shell
   aliases, wrappers, cron jobs, hooks, remote forced commands and
   `CREW_BIN` name `<mdstack>/cli/mdstack` and the module paths. Rerun
   `mdstack layout --project ~/.mdstack/config.toml --write` for the start
   wrappers.
4. **Update your pack**, if you have one ([packs](#packs)).
5. **Start:** `mdstack up --project ~/.mdstack/config.toml`, then check with
   `mdstack doctor --project ~/.mdstack/config.toml`.
6. Remove the old install by hand: the `<state>/eng-crew` link and the
   `eng-crew-<version>/` bundle.

### Product names (7.0.0)

7.0.0 renames the product from `eng-crew` to `mdstack`, after the repo moved
to `github.com/mw-ding/mdstack`. The old names are not accepted:

| Old name | 7.0.0 name |
|---|---|
| Release bundle `eng-crew-<version>.tar.gz`, top directory `eng-crew-<version>/` | `mdstack-<version>.tar.gz`, `mdstack-<version>/` |
| Host toolkit `toolkit/eng-crew-<version>/` | `toolkit/mdstack-<version>/` |
| Install link `<state>/eng-crew` | `<state>/mdstack` |
| Profile key `paths.eng_crew` | `paths.mdstack` |
| Pack key `pack.eng_crew_version` | `pack.mdstack_version` |
| CLI `crew` (`cli/crew`, `scripts/crew`) | `mdstack` (`cli/mdstack`) |

`crew:` labels, markers, the `crew.d/` module directory and the `CREW_*`
variables keep their names. 7.1 renames the profile to `config.toml` and
moves the default layout under `~/.mdstack/` (#1316), with no fallback to
`crew.toml` or the old `~/crew-home/` and `~/.crew/` defaults.

### Old paths to modules

6.0.0 moved each file to its module
([module layout](../specs/team.md#4-target-module-layout)); 7.0.0 removed
the old paths:

| Old path | Path |
|---|---|
| `scripts/crew` | `cli/mdstack` |
| `scripts/crew-config.py`, `crew-render.py`, `crew-roles.py` | `core/` |
| `scripts/crew.d/*` | `environments/terminal/crew.d/*` |
| `scripts/crew-session.py`, `crew-proc.py` | `environments/terminal/` |
| `scripts/crew-remote.py` | `environments/terminal/remote/crew-remote.py` |
| `scripts/session.d/<backend>.py` | `environments/terminal/sessions/<backend>/adapter.py` |
| `scripts/crew-harness.py` | `harnesses/crew-harness.py` |
| `scripts/harness.d/<engine>.py` | `harnesses/<engine>/adapter.py` |
| `scripts/crew-repo.py` | `connectors/github/crew-repo.py` |
| `packs/github/manifest.toml` | `connectors/github/manifest.toml` |
| `scripts/test-*.py` | `dev/tests/<module>/test-*.py` |

An adapter left in `scripts/harness.d/` or `scripts/session.d/` is no longer
discovered.

### Packs

- Rename `eng_crew_version` to `mdstack_version` in the pack manifest, or
  give a `pack.toml` `framework` range that includes 7.0.0, such as
  `">=7.0.0, <8.0.0"`; bootstrap refuses a pack outside its range
  ([install pin and upgrade](../packs.md#install-pin-and-upgrade)).
- Move a harness adapter kept in `scripts/harness.d/` into the pack as
  `harnesses/<name>/adapter.py` and list it under `[provides]`.
- Read the GitHub manifest from `connectors/github/`.
- Replace `crew` with `mdstack` in the pack's docs and CI, and run
  `mdstack pack test <dir>` there ([pack author guide](pack-authoring.md)).
