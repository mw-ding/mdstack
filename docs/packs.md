# Packs

A pack is a backend's adapter: its capability declaration, its command
mapping and, for an organization, the profile values that pick it. The
GitHub pack ships here as the GitHub connector
([connectors/github/](../connectors/github/manifest.toml));
an organization's own pack lives in its own repo, outside mdstack, pinned
to an mdstack version (portable mdstack, roadmap 13.15,
[#127](https://github.com/mw-ding/mdstack/issues/127);
[portable spec P5, P6](specs/portable.md#2-requirements)).

This page adds no rule, gate, cap, marker field or label; the
[protocol](protocol.md) owns them. Writing, hosting or fetching an org pack
is out of scope.

## Direction rule

Packs reference mdstack; mdstack never references a pack outside this
repo. No file here names an organization's internal tools, commands, URLs
or specs (spec P6). The [denylist check](#denylist-check) guards it.

## Layout

| Path in the pack | Required | Contents |
|---|---|---|
| `manifest.toml` | yes | `[pack]` (`name`, `commands`; `mdstack_version` for a pack outside mdstack; optional `version`, the [pack's own release](#pack-version)) and the [capability declaration](#capability-declaration) |
| `profile.toml` | no | Org-layer values for [`resolve`](profile.md#layers-and-precedence): any `config.toml` key, usually `backends.<concern>.name` and overrides |
| `docs/` | yes | Binding docs: one command or API call per operation of [interfaces](interfaces.md), as [backends/github.md](backends/github.md#interface-mapping) does for GitHub; `commands` points at it |
| `render/` | no | Per-file [render overlay](#render-overlay): `backends/<name>.toml` and any template to change, laid out like `templates/` |
| `harness.toml` (any name `pack.harness` gives) | no | [Harness pointers](#harness-pointers) the pack declares for `mdstack bootstrap --harness` |

`crew-config.py validate <pack>/manifest.toml` checks a manifest
([Pack manifest](profile.md#pack-manifest)).

## Version pin

`pack.mdstack_version` names the mdstack version the pack was checked
against by its release id: a release tag once mdstack tags releases, until
then the full 40-character commit SHA of mdstack `main`. Where the
installed mdstack is released with `release_id = "commit"`
([commit release id](release.md#commit-release-id)), the pin is the full
40-character hash of a landed cut commit recorded by
`release.record-release`; any other hash is not a release. Compatibility rule:

- A pack is supported only at its pinned version. Install the mdstack
  checkout that matches the pin, by tag or by hash.
- To move the pin, run `validate` on the manifest and `resolve` with the
  pack's profile against the new checkout; both must pass. Then bump the
  pin in the pack's repo.
- An operation added to [interfaces](interfaces.md) after the pin is
  undeclared in an older manifest, so it counts as `unsupported`; if that
  leaves an invariant, `resolve` fails closed rather than weakening it.

### Pack version

`pack.version` is optional and names the pack's own release, for a pack
released on its own schedule. It is a SemVer string with the
[Versioning](deliverables.md#versioning) rules but no leading `v`
(`0.5.0`, `1.2.0-rc.1`). It differs from the pin: `mdstack_version` names
the mdstack release the pack was checked against; `version` names the
pack's release and gates nothing.

- `validate` refuses a malformed `version`; a manifest without one stays
  valid.
- `resolve` with an external pack prints it after the profile keys as
  `pack.version = "<version>"  # pack:<name>`. Without an external manifest
  version, a wired [`pack.toml`](#pack-plug-ins) pack's `[pack] version`
  prints the same way. It is metadata only: the effective profile gets no
  `pack` table.
- Bootstrap and upgrade record `"pack": {"name", "version"}` in
  `install.json`, and `mdstack doctor` shows it as the `pack` row. Upgrade
  updates the record when only the pack version changed.
- Without `version`, none of these outputs or fields appear.

## Capability declaration

`[capabilities.<concern>]` lists every operation of that concern as
`supported`, `unsupported` or `emulated (<how>)`, the
[capability declaration](interfaces.md#capability-declaration) of
13.9. `resolve` folds the manifest of each chosen backend
(`connectors/<name>/manifest.toml`, or the explicit external manifest) under every config layer: a profile's
`backends.<concern>.capabilities` value wins, and the output names the
manifest as `pack:<name>`. An operation neither declares counts as
`unsupported` in the unsupported-invariant rule.

## Wiring

A project picks backends by name in its `config.toml`
(`backends.<concern>.name`) and points at an org pack when it resolves:

```sh
python3 core/crew-config.py resolve --project config.toml \
  --org-profile <pack-path>/profile.toml \
  --pack-manifest <pack-path>/manifest.toml
```

The project can instead record the pack directory in its own `config.toml`:

```toml
[paths]
pack = "<pack-path>"
```

`resolve` reads that directory's optional `profile.toml` as the org layer.
Relative directories resolve from the project file, independent of the
current directory. An explicit `--org-profile` overrides this selection.
Missing directories and malformed profiles fail; a pack without a profile
adds no org layer. Core/default/org/project precedence is unchanged.
Bootstrap checks the recorded pack's version pin just as it does for an
explicit `--org-profile`.

The pack path stays with the install, never in mdstack. `--pack-manifest`
loads and validates the external manifest, then admits its `pack.name` as
a backend alongside `github`. With an explicit or recorded org profile, its adjacent
`manifest.toml` is used when present, unless `--pack-manifest` overrides it;
a recorded pack directory without `profile.toml` still supplies its `manifest.toml`.
Names use lowercase letters and digits
separated by hyphens; new backends require `pack.mdstack_version`.
`validate config.toml --pack-manifest <pack-path>/manifest.toml` uses the same
declaration. Unknown names still fail. External capabilities fold below
profile overrides with provenance `external-pack`; other backends continue
to use their bundled manifests. Invalid or unreadable external manifests fail.
A pack that binds the optional release concern ships `[backends.release]`
and `[release]` together, normally both in its `profile.toml`; `resolve`
refuses either half alone
([release pairing](interfaces.md#capability-declaration)).

## Render overlay

The renderer searches a pack's `render/` directory per file before
`templates/` (or `--inputs`). The pack directory is the org profile's
directory, else `paths.pack`. A pack that only adds a backend holds
`render/backends/<name>.toml`; a pack that changes one brief adds that one
file, such as `render/runtimes/tmux/builder.md`. Every other file still comes
from upstream, so the output equals the upstream render except for the
overridden files and the pack's mapped commands. `crew-render.py`,
`mdstack bootstrap` (self-test and preview), `mdstack up`, `mdstack upgrade` and
`check-skill-drift.py --project` all apply it. Lookup order:
[scripts](../scripts/README.md#renderer).

Every backend command in the tmux briefs goes through an
`<op:<concern>.<operation>>` token, so a pack's backend map replaces all of
them. That includes the brief's CLI conventions (`change.cli-name`,
`change.cli-repo-flag`, `change.cli-unscoped`) and the state-tag and
gate-status edits ([interfaces](interfaces.md)). A pack declares a
capability for each one as usual. A map value is substituted as written, so
a multi-line value keeps the brief's line breaks.

The sensitive classifier is the one token a map does not replace (#880):
`<op:classify.sensitive>` always renders the core
`core/crew-config.py sensitive`; a pack's
`[classify] sensitive` command is an extension that core runs and unions
with the built-in rules, so it can add matches but never remove one
([bindable sensitivity](interfaces.md#bindable-sensitivity-design)).

### Placeholder declaration

Command values may use the renderer's run-time placeholders. A backend
whose identifiers differ declares its own in its backend map:

```toml
[placeholders]
kept = ["item-id", "version-id"]

[change]
list-open = "<cli> list --open --item <item-id>"
```

Declared names (`[a-z][a-z0-9-]*`, never an install-time placeholder such
as `<owner>`) render verbatim inside that map's commands. An undeclared
name still fails with `unknown placeholder <name>`.

### ID declaration

A backend map's optional `[ids]` table declares the full-match pattern of
its item ids (`item`, read from the tracker backend) and change ids
(`change`, read from the change backend), digits by default. `resolve`
prints both as `ids.item` and `ids.change` with `backend-map:<name>`
provenance, and `repo.control_item` is checked against `ids.item`
([handoff](handoff.md#id-declaration), #936). It is the one copy the
consumers read: `mdstack handoff` matches native dependency links with
`ids.item` (#937), and the precheck and selfgate keys use both (#876).

The change backend's table may also set `marker_key = "change"` (the
default: the selfgate record keys on `pr=`) or `"item"` (it keys on
`issue=`, for a backend with no separate change number). See
[protocol](protocol.md#precheck-and-selfgate-id-keys) (#876).

### Harness pointers

An optional `pack.harness` names a registry file in the pack. Each
`[[pointer]]` entry gives a harness with an install pointer adapter, a
project-relative `target` and a pack `source` written by `copy` or
`pointer`, or a Codex `launch_note`. `mdstack bootstrap --harness` installs the
entries for the selected harnesses under its own refusals, excludes, hashes
and uninstall; no entry runs pack code. See
[bootstrap](bootstrap.md#pack-harness-pointers-design) (#883).

### Update strategy

A pack manifest's optional `[strategy]` table declares
`update_from_base = "merge" | "rebase"` (default `merge`), and
`retains_prior_heads = true`, which `rebase` requires. Under `rebase` the
rendered briefs say "rebase onto `<default-branch>` and upload" and
`mdstack train build` and `bisect` refuse
([interfaces](interfaces.md#rebase-update-from-base), #874).

### Render-time notes

`runtime.options.notes.render.<role>` lists files appended to that role's
rendered brief at render time. Any role in the registry and the `builder-lead`
and `reviewer-lead` briefs are accepted
([profile](profile.md#runtime)). Unlike launch-time notes, they
count toward `size_budget` and the drift check covers them.

## Pack plug-ins

A pack that brings its own connector, harness or environment code adds a
`pack.toml` at the pack directory's root (#1236). The pack directory is the
same one [Wiring](#wiring) selects: the org profile's directory or
`paths.pack`. A pack without `pack.toml` keeps the config-only behaviour
above.

```toml
[pack]
name = "example"
version = "0.1.0"                # optional, SemVer
framework = ">=5.3.0, <6.0.0"    # mdstack release versions the pack supports

[provides]
connectors = ["example-tracker"]  # connectors/<name>/manifest.toml
harnesses = ["example-agent"]     # harnesses/<name>/adapter.py
environments = ["tmux"]           # environments/<name>/defaults.toml
skills = ["example-review"]       # skills/<name>/SKILL.md
```

`framework` is a comma-separated list of comparators (`>=`, `>`, `<=`, `<`,
`==`) on `X.Y.Z`. It replaces the single `pack.mdstack_version` pin, so a
connector manifest inside the pack needs no pin of its own.

### Discovery

`core/crew-pack.py` loads the pack and checks each item with the loader its
built-in kind already uses:

| Kind | Pack path | Checked as | Resolved through |
|---|---|---|---|
| Connector | `connectors/<name>/manifest.toml` | `validate_manifest`, like `connectors/github/` | `backends.<concern>.name`; its capabilities fold in as `pack:<name>` |
| Harness | `harnesses/<name>/adapter.py` | the harness `discover()`, like `harnesses/<engine>/` | engine names in `[engines]`; `mdstack spawn` launches it |
| Environment defaults | `environments/<runtime>/defaults.toml` | the profile schema | the `pack` layer when `runtime.name` matches |
| Skill | `skills/<name>/SKILL.md` | Agent Skills frontmatter (`name`, `description`) | listed by name beside the built-in role skills |

Resolve layers a pack as core → default profile → pack (environment
defaults, then the pack's `profile.toml`) → project. The project still wins.
A pack adds names and never replaces a built-in one: a connector, harness or
skill with a built-in name is refused. Pack harnesses join every engine
table except the `bootstrap --harness` install choices. `mdstack pack list
--project <file>` prints each item's kind, name, source (`core`,
`pack:<name>` or `core+pack:<name>`) and path.

### Install pin and upgrade

Bootstrap and upgrade refuse a pack whose `framework` does not admit the
installed stable release tag. Pre-releases and `--dev` commits satisfy no
range. The pack directory must be a clean checkout or a verified export.
Install records `"pack": {"name", "version", "framework", "commit"}` in
`install.json`. A
new pack commit makes `mdstack upgrade` re-plan, and uncommitted changes are
refused.

By default the clean check and the commit read run `git` in the pack
directory. A pack whose working copy belongs to another version control
tool, such as a subdirectory of a monorepo, declares both commands in
`pack.toml` (#1326). They run in the pack directory:

```toml
[vcs]
clean = ["hg", "status"]                           # exits 0, prints nothing when clean
commit = ["hg", "log", "-r", ".", "-T", "{node}"]  # exits 0, prints the commit
```

A failing command, an empty commit or any output from `clean` refuses the
pack.

A host with no checkout of the pack's repository can install an exported
copy instead (#1962). The exporter writes a `pack.lock` into the export from
a clean checkout:

```sh
python3 core/crew-pack.py lock <checkout> <export>
```

It refuses an export file that differs from the checkout's file at the same
path. The lock records the checkout's `commit`, each file's `sha256` under
`[files]`, and a `sha256` over the sorted lines `<path>\0<file sha256>\n`;
`pack.lock` itself is excluded. When the commit read fails, or its command
is not installed, and the directory holds a `pack.lock`, bootstrap and
upgrade verify the export against it. A changed, added or removed file
refuses the pack, naming the first mismatched path in sorted order; a
verified export records the lock's `commit` as `pack.commit`. A plain
directory without `pack.lock` keeps the checkout refusal.

### Floors

A pack may tighten rules, such as a stricter flavor, extra sensitive paths,
`builder.precheck` or extra skills. It can never loosen a core floor. The
loader refuses a pack whose `profile.toml` or environment defaults:

- set a floor control (F1–F7, such as `ci_waiver` or
  `hold_label_blocks = false`) in the `[flavor]` table, its custom
  flavors and classes, or `runtime.options`. A key elsewhere that only
  shares a name, such as the `[backends.ci]` selector, is not a floor
  control;
- set a `merge_grant` other than `none`, because a merge grant is the
  owner's;
- define a custom flavor that is less strict than the core default,
  `standard`, on any rigor knob or cap. The loader checks each file and
  the definition merged across the pack's layers;
- select a project or class flavor that is less strict than `standard`, or
  one that is neither a preset nor defined by the pack. A definition in the
  environment defaults and a selection in `profile.toml` are checked
  together.

### Conformance kit

`mdstack pack test <pack-dir>` runs the public contract tests in
[actions/contract.py](../actions/contract.py) against the pack's adapters,
using fakes. A pack runs it in its own CI. Exit 0 means every check passed.

- **Connector:** the manifest validates. An optional `[actions]` table names
  an `entry` (a `.py` file runs with the same Python) and declares each
  action from [actions/README.md](../actions/README.md#capability-declaration);
  an action left out counts as `unsupported`. The entry runs against a fake
  project, with `CREW_ACTIONS_FAKE` naming a scratch state directory, and must
  keep the [CLI contract](../actions/cli.md): `--capabilities` matches the
  declaration; every result is one JSON envelope whose outcome agrees with
  its exit code; an unknown action is refused with `usage` (exit 2); an
  unsupported one is refused with `unsupported` (exit 6); a short `--head`
  is refused; without `--json`, stdout is one outcome line.
- **Harness:** the adapter has the module interface the built-ins have
  (`EXECUTABLE`, `TITLE`, regex `PROMPTS` and screen patterns). Its login,
  role-launch and coordinator argv each run a fake executable placed first on
  `PATH`, and the role argv passes the chosen model.

The fixture pack `dev/tests/core/fixtures/packs/example` (a fake connector and
harness) passes the kit, and `dev/tests/core/test-crew-pack.py` covers discovery,
version refusal, floor refusal and conformance.

## Denylist check

`check-repo.py --only denylist` reads the file named by `CREW_DENYLIST`
(one name per line, outside this repo) and fails on any whole-word,
case-insensitive match in a tracked file. Unset means skip. See
[scripts](../scripts/README.md#denylist).

## Personnel consumers

A host may consume [pinned role content with a thin binding](personnel.md)
while supplying its own control plane. This content import does not extend
pack discovery to external role definitions or authorize role inheritance.
