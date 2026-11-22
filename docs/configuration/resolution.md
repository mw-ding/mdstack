# Configuration resolution

Configuration module for checking and resolving a profile, split out of the
[profile reference](../profile.md) under the M26 modular organization
principle ([#676](https://github.com/mw-ding/mdstack/issues/676)). It holds
the profile's former [Validate](../profile.md#validate) section: both command
variants, the problem format and exit codes, the rejection list and the
install-time placeholder check. It also holds the profile's former
[Layers and precedence](../profile.md#layers-and-precedence) section: the
layers `resolve` merges into the effective profile, the merge rule, the
cross-key checks and the provenance output. The key schema, host inventory
and pack manifest stay in the profile's [Keys](../profile.md#keys) section.

## Validate

```sh
python3 core/crew-config.py validate config.toml
python3 core/crew-config.py validate config.toml --install
```

Each problem prints as `file:key: reason`, where `key` is the dotted path
(`backends.change.name`, `engines.default.order[0]`); exit 1 on any problem,
0 otherwise. It fails on: invalid TOML, a missing required key, an unknown
key, concern, runtime, backend, engine or effort, a wrong type, a malformed
capability, a host inventory problem (`[hosts.<name>]` and `[placement]`
in the profile's
[Keys](../profile.md#hostsname-and-placement)), a pack manifest's
`pack.harness` registry problem ([Pack manifest](../profile.md#pack-manifest)),
and a token-shaped value anywhere in the file.

`--install` rejects remaining install-time placeholders, including embedded
placeholders and entries in lists. The renderer's run-time placeholders
(such as `<n>` and `<head-sha>`) stay allowed. Ordinary validation keeps
allowing template profiles. `resolve --project config.toml --install` applies
the same check to the effective profile after all layers and overrides
(see [Layers and precedence](#layers-and-precedence)),
so defaults replaced with concrete project/org values do not fail.

## Layers and precedence

`core/crew-config.py resolve --project <config.toml> [--org-profile <path>]`
builds the effective profile from four layers, lowest precedence first
([portable spec P5](../specs/portable.md#2-requirements), #110 decision):

| Layer | Source | Present |
|---|---|---|
| `core` | Schema defaults in the script: `repo.default_branch`, role names/titles/emojis, `engines.coordinator`, each tier's `effort`, the `[triage]` defaults (`repos` from `[repo]`), the `[docs]` defaults when that table is present (`repos` from `[repo]`), and the chosen runtime's integer options | always |
| `default` | `profiles/default.toml` in mdstack (13.12, [#124](https://github.com/mw-ding/mdstack/issues/124)) | skipped while absent |
| `org` | The org / environment pack profile, read from `--org-profile`, or `paths.pack/profile.toml` in the project; mdstack never holds or names one | only when given or recorded |
| `project` | The project's `config.toml` (`--project`) | always |

Merge rule: tables merge by key; scalars and arrays replace the lower
layer's value whole. TOML has no null, so a layer drops keys only by
replacing a table with a non-table. Doing that to a key under `identities`
(I1, I4), `backends` (capability declarations, I1–I5) or `engines` (I2) is
an error.

The merged profile must then pass every `validate` check, plus these
cross-key checks:

- the [unsupported-invariant rule](../interfaces.md#capability-declaration):
  an operation declared `unsupported` whose invariant no other operation
  keeps fails the profile. Before the check, `resolve` fills each backend's
  operations that no layer declares from its pack manifest
  (`connectors/<name>/manifest.toml`, #124, #1223; [packs](../packs.md#capability-declaration)),
  printed with the layer `pack:<name>`. An operation still undeclared counts
  as `unsupported`;
- [single identity](../interfaces.md#single-identity-profile): if
  `identities.reviewer.gh_user` equals `identities.builder.gh_user`,
  `backends.review.capabilities.post-verdict` must be `emulated (<how>)`;
- integer options, such as `runtime.options.builders`, must be at least 1;
- [release pairing](../interfaces.md#capability-declaration): with an
  external pack, a `[release]` table on the default-layer
  `[backends.release]` while the pack declares release capabilities fails
  naming `[backends.release]`, and a pack-bound `[backends.release]` with no
  `[release]` table fails naming `[release]`.

On success it prints one `key = value  # layer` line per leaf key, naming
the layer that set it, and exits 0. Each problem prints as
`file:key: reason`, where `file` is the layer file that set the key, or
`(resolved)` for a key no layer set; exit 1.

```text
$ python3 core/crew-config.py resolve --project config.toml
repo.owner = "acme"  # project
repo.default_branch = "main"  # core
runtime.options.builders = 3  # project
runtime.options.reviewers = 2  # core
```
