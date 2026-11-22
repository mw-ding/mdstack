# Profile (`config.toml`)

One install-time file picks the runtime, a backend per concern, identities,
engines and paths for one repo (portable mdstack, roadmap 13.10,
[#122](https://github.com/mw-ding/mdstack/issues/122);
[portable spec P4](specs/portable.md#2-requirements)). It replaces the
hand-filled placeholders of the [templates](../templates/README.md#placeholders)
and the per-repo [wiring doc](../templates/runtimes/grok-bot/wiring.md).
`core/crew-config.py validate <file>` rejects a bad profile before anything
renders ([scripts](../scripts/README.md#profile-validator)).

This page adds no rule, gate, cap, marker field or label; the
[protocol](protocol.md) owns them. `validate` checks one complete file;
`resolve` merges the config layers (13.11,
[#123](https://github.com/mw-ding/mdstack/issues/123); see
[Layers and precedence](#layers-and-precedence)) on top of the
[default profile](../profiles/default.toml) (13.12,
[#124](https://github.com/mw-ding/mdstack/issues/124)).

## Where the file lives

The default is the user-level `~/.mdstack/config.toml` (`<root>/config.toml`
under a set `CREW_ROOT`): every `mdstack` and `core/crew-config.py` command
uses it when given no `--project`, no `CREW_PROJECT` and no
`MDSTACK_CONFIG`; an explicitly named file always wins (#1324). A project-level `config.toml`, passed with
`--project FILE`, is the secondary option for a separate project-group
stack. The two never merge; precedence and what belongs where are in
[user-level and project-level config](runtimes/tmux.md#user-level-and-project-level-config-1316)
(#1316). There is no `crew.toml` fallback.

## Format

[TOML](https://toml.io/en/v1.0.0), read with Python's stdlib `tomllib`
(3.11+). Every table and key below is closed: an unknown key fails. A key
marked *required* has no default. Values name identities by mechanism only
(a login, never a token): any string that matches a
[secret pattern](../scripts/README.md#what-it-checks) of `check-repo.py`
fails, unless written as a placeholder such as `<token>`.

## Example

```toml
[repo]
owner = "<owner>"
name = "<repo>"
default_branch = "main"

[runtime]
name = "tmux"
options = { builders = 5, reviewers = 2 }

[backends.change]
name = "github"
[backends.review]
name = "github"
capabilities = { post-verdict = "emulated (COMMENT-review verdict + recorded owner merge-ok)" }
[backends.tracker]
name = "github"
[backends.state-tags]
name = "github"
[backends.markers]
name = "github"
[backends.ci]
name = "github"
[backends.events]
name = "github"
[backends.owner-channel]
name = "github"

[identities]
owners = ["<user-login>"]
coordinator = { gh_user = "<author-login>" }
builder = { gh_user = "<author-login>" }
reviewer = { gh_user = "<author-login>" }
synthesizer = { gh_user = "<author-login>" }

[engines]
coordinator = "claude-code"
trivial = { order = ["claude-code/sonnet", "codex/gpt-6.1-sol"] }
default = { order = ["codex/gpt-6.1-sol", "claude-code/sonnet"] }
deep = { order = ["codex/gpt-6.1-sol", "claude-code/sonnet"], effort = "high" }

[paths]
state_dir = "<state-dir>"
worktree_root = "<worktree-root>"
```

This example is a single-identity profile (reviewer = author), so it
declares the review emulation of
[interfaces: Single-identity profile](interfaces.md#single-identity-profile).

## Keys

### `[flavor]`

Optional named rigor configuration; the [flavor schema](flavors.md#profile-schema)
defines `name`, `goal`, custom compositions and class declarations. The validator
accepts `thorough`, `standard`, `fast` and `solo`; the solo lane uses the
`crew:solo` item label for builder routing.
`resolve` supplies an unset name as `standard` with `core (unset: flagged)`
provenance. Custom tables merge by key; class arrays replace as a whole.
Schema validation does not activate runtime gate modes or precheck defaults:
those integrations remain the flavor design's follow-ups A and B. Existing
`builder.precheck.enabled` and the recorded `runtime.options.merge_grant`
continue to govern runtime behavior until that integration.

### `[repo]`

| Key | Type | Default | Replaces |
|---|---|---|---|
| `owner` | string | *required* | `<owner>` |
| `name` | string | *required* | `<repo>` |
| `default_branch` | string | `"main"` | `<default-branch>` |
| `control_item` | positive integer, or a string matching the tracker's `ids.item` | none (legacy operation) | ownership control issue ([protocol](protocol.md#ownership-record)) |

A string `control_item` must fully match the item pattern the tracker
backend's map declares in `[ids]`
([ID declaration](handoff.md#id-declaration), #936); without one, `validate`
refuses a string. Ownership, `mdstack handoff` and `mdstack doctor` read and post
it through the markers backend's `read-item` and `write-item`
([handoff](handoff.md#tracker-native-control-item), #937).

Item and change id patterns are not profile keys: a backend map's `[ids]`
table declares them ([packs](packs.md#id-declaration)), and a
profile layer cannot set them. The precheck and selfgate markers keying on
those ids, and the change map's optional `marker_key` (`change` by default,
or `item` for a backend with no separate change number), are in
[protocol](protocol.md#precheck-and-selfgate-id-keys) (#876).

### `[runtime]`

Moved to
[Runtime options: `[runtime]`](configuration/runtime-options.md#runtime):
the `name`, `options`, `timezone` and `instance` keys with the `instance`
condition, and the `max_active_milestones` coordinator option every runtime
accepts, with its priority, in-flight and default behavior. The `tmux`
options with their presence/away caps, the standing and render-time `notes`
and the pack render overlay moved to
[Runtime options: `tmux` options](configuration/runtime-options.md#tmux-options).
The `tmux` launch topology (`[runtime.options.launch]`) with its
absent-table fallback, keys and example moved to
[Runtime options: Launch topology](configuration/runtime-options.md#launch-topology).

### `[builder.precheck]`

Optional pre-review check settings, supplied by the project or an org profile.
Tables merge by key; project values override org values.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | `false` | Include the ordered pre-review steps in the builder brief |
| `lint` | string | none | Shell command for lint / format |
| `test` | string | none | Shell command for tests / build |
| `docs` | string | none | Optional shell command for docs checks |
| `max_fix_attempts` | positive integer | `2` | Maximum fixes per failing command, rerunning after each |
| `owners` | string | none | Shell command that takes one changed path and prints its owning test targets, one per line |
| `no_owner_ok` | array of globs | none | Paths that may have no owner, such as build files and docs |

When enabled, the renderer adds the [pre-review steps](protocol.md#builder-pre-review-check)
to the core builder brief and the runtime's build intake brief. Missing, empty
or whitespace-only commands render as `n/a`, never `pass`; required docs and
changelog updates still apply. When disabled or omitted, the builder brief
and existing builder duties are unchanged. No merge gate is added.

With `owners` set, the builder pipes the changed paths to
`core/crew-config.py precheck-scope --project <file>`, which runs the
query once per path and prints each path's class (`owned`, `no-owner-ok` or
`unowned`) and the owning targets as JSON. The builder pipes every changed
path, both rename paths included, from the worktree at head; a path absent
there (a deletion or a rename source) is `removed`, gets no owners query and
no targets, and never counts as unowned
([#1345](https://github.com/mw-ding/mdstack/issues/1345)). It exits 3 on
unowned code and 4 when a query fails; both stop the check. `no_owner_ok` uses the
[`sensitive`](#sensitive) glob syntax. Without `owners`, behaviour and
render are unchanged ([#881](https://github.com/mw-ding/mdstack/issues/881)).

```toml
[builder.precheck]
enabled = true
lint = "python3 scripts/check-repo.py"
test = "python3 dev/tests/core/test-crew-config.py"
max_fix_attempts = 2
```

### `[sensitive]`

Optional `paths`: an array of repo-relative globs extending the mandatory
defaults; `[]` adds none. Layers replace this array; defaults always remain.
`**` crosses `/`; `*` and `?` stay in one segment; matching is case-sensitive.
Empty patterns, absolute paths and `..` segments are invalid.

Defaults: `.github/workflows/**`, and root or nested directories named `auth`,
`secrets`, `permissions`, `access-control`, `migrations` or `deletions`. Add the
project's other security/irreversible paths (including files outside these
directories). For mdstack, add `docs/protocol.md`, `docs/verification.md`,
`docs/flavors.md` and `core/crew-config.py` to protect its gate contract.

```toml
[sensitive]
paths = ["infra/iam/**", "scripts/drop-*.py"]
```

Run `python3 core/crew-config.py sensitive --project config.toml` with full
diff paths on stdin (`--paths-only` at triage; `--diff` with
[content rules](#content-rules-879)). JSON output names `label`
(`crew:sensitive` or `null`) and `matches` (path → matching rules); exit 1
means invalid configuration, never a non-sensitive result. Label duties and the owner override are in
[the protocol](protocol.md#sensitive-class).

#### Content rules (#879)

The PR check classifies with these rules as the
[protocol](protocol.md#sensitive-class) describes, and `resolve` requires
the change backend's conditional `read-diff` operation once any are
declared. The section also fixes the JSON contract that #880's bindable
classifier shares.

Optional `[[sensitive.content]]` entries match the text of changed lines,
for an owner rule about a kind of text rather than a place, such as merge or
land rule text wherever it lives:

```toml
[[sensitive.content]]
name = "merge-rules"
pattern = '(?i)\b(merge|land)(ing)?[- ](gate|rule|permission|grant)s?\b'
paths = ["docs/**", "templates/**"]
reason = "merge or land rule text is sensitive wherever it lives"
```

- `name`: required, nonempty, unique across the array. `reason`: required,
  nonempty. `pattern`: required, a Python `re` pattern that must compile;
  it is searched, unanchored, in each added and removed line without its
  `+`/`-` prefix. `paths`: optional scope globs with the `paths` syntax
  above; unset means every path.
- Layers replace the whole array, as with `paths`. There are no default
  content rules, so a profile without entries classifies exactly as today.
- Input: `sensitive --diff` reads a unified diff of the change at head
  against its merge base on stdin, made without rename folding (in a
  checkout, `git diff --no-color --no-renames <merge-base> <head>`), so a
  moved file shows as removed plus added lines. Path rules run on every old
  and new path in it. Without `--diff`, stdin stays a path list; when
  content rules exist, that input exits 3, as does an empty or malformed
  diff, any rename or copy header (rename folding was on) or a quoted
  path header. The exception is `--paths-only`, for triage, where an issue
  has no diff: it runs path rules only on the list and prints no
  `content`. A file block is complete only as a text patch with
  hunks, a binary change, an empty file added or deleted, or a mode-only
  change; any other block was cut inside its header and exits 3. Exit 3 means classification is incomplete, never "not
  sensitive"; exit 1 still means invalid configuration.
- Matching is deterministic. Only added lines (side `new`, numbered in the
  new file) and removed lines (side `old`, numbered in the old file) match;
  file headers, hunk headers, context lines and binary files never do. A
  scoped rule applies to a file when its old or its new path matches a
  scope glob.

Output, the one contract `sensitive` and #880 bindings share:

```json
{"label": "crew:sensitive",
 "matches": {"docs/protocol.md": ["docs/protocol.md"]},
 "content": [{"rule": "merge-rules", "path": "notes/lanes.md", "side": "old", "line": 12}]}
```

`label` and `matches` keep today's meaning. `content` is present only when
content rules are configured: `[]` when none matched, otherwise records
sorted by path, side, line and rule, without the line text. `label` is
`crew:sensitive` when `matches` or `content` is nonempty. #880 may add
fields for extension errors but never changes these three.

With a pack extension bound
([bindable sensitivity](interfaces.md#bindable-sensitivity-design), #880), the output
adds `errors`, `[]` after a clean extension run, otherwise one line per
failure naming the pack and the cause. A nonempty `errors` also makes
`label` `crew:sensitive`. Extension matches carry their rule names, and
content records their `rule`, prefixed `<pack>:`. An extension prints the
same three fields; core validates them and never takes its `label` alone.

### `[spec]`

Optional `paths`: an array of repo-relative globs for spec changes, in the
[`sensitive`](#sensitive) glob syntax. Unlike `sensitive.paths`, it
replaces the default `["docs/specs/**"]`; `[]` leaves only the `crew:spec`
label. Layers replace this array. A change is a spec change when it carries
`crew:spec` or any path, including both sides of a rename, matches one of
these globs. The definition and the opt-in
[`merge_grant_scope`](configuration/runtime-options.md#merge_grant_scope)
are [§7 spec change](protocol.md#spec-change-definition-and-spec-grant-scope)
(#398); `mdstack train check` and `mdstack train land` apply both.

```toml
[spec]
paths = ["docs/specs/**", "rfcs/**"]
```

### `[backends.<concern>]`

One table per concern of [interfaces](interfaces.md#concerns). Eight are
*required*: `change`, `review`, `tracker`, `state-tags`, `markers`, `ci`,
`events`, `owner-channel`. `release` is optional; a profile with a
[`[release]`](#release) table needs it. Any other concern fails.
`classify` is optional too (#880): it binds a pack's
[sensitivity extension](interfaces.md#bindable-sensitivity-design), and
without it the built-in classifier runs alone, as today.

| Key | Type | Default | Replaces |
|---|---|---|---|
| `name` | string: `github` ([backend](backends/github.md)) or the explicitly supplied external manifest's `pack.name` | *required* | none (was implicit: GitHub) |
| `capabilities` | table: operation → `supported`, `unsupported` or `emulated (<how>)` | `{}` | none |

`capabilities` carries the
[capability declaration](interfaces.md#capability-declaration); an
undeclared operation counts as `unsupported` there. Operation keys per
concern, in the interfaces order:

| Concern | Operation keys |
|---|---|
| `change` | `open`, `push`, `read-head`, `read-diff-paths`, `update-from-base`, `land`, `close` |
| `review` | `post-verdict`, `post-narrative`, `list-verdicts`, `request-rereview` |
| `tracker` | `create-item`, `assign`, `link`, `milestone`, `board-status`, `list-items`, `label`, `comment`, `close-item` |
| `state-tags` | `set-clear-read` |
| `markers` | `write`, `read`, `write-item`, `read-item` |
| `ci` | `check-status`, `failing-jobs` |
| `events` | `subscribe-or-poll` |
| `owner-channel` | `ask`, `notify` |
| `release` | `cut`, `approve-check`, `record-release`, `notify` |
| `classify` | `sensitive` (`supported` or `unsupported`; `emulated` is refused) |

`change` also accepts the conditional keys `publish`, `land-status` and
`read-landed`, which only an
[asynchronous land](interfaces.md#asynchronous-land-design) needs; a `sync` backend leaves them out. `change` also accepts
`read-branch-head` and `tracker` accepts `unlabel`, which only
`mdstack handoff` runs, with `repo.control_item` and a non-GitHub tracker or
change backend ([handoff](handoff.md#handoff-live-reads)). `read-diff` is
conditional too: `resolve` refuses a profile with
[content rules](#content-rules-879) whose effective `change.read-diff` is
`unsupported` or undeclared.

`resolve` refuses a `[backends.classify]` whose effective
`classify.sensitive` is not `supported` (the bundled `github` declares no
extension), and one whose backend map has no `[classify] sensitive`
command or holds an unfilled `<placeholder>` in it. The map is the pack's
`render/backends/<name>.toml` overlay ([packs](packs.md)), else the bundled
`templates/backends/<name>.toml`. `resolve` prints the bound command after
the profile as `classify.sensitive = "<command>"  # pack:<name>`.
`core/crew-config.py sensitive` runs that command beside the built-in
rules and adds its matches, fail-closed
([union](interfaces.md#union-fail-closed)).

For tmux, `owner-channel` also accepts `name = "slack"`. Only `notify`
uses Slack; `ask` remains a recorded GitHub ask. No other concern accepts
Slack. Configure the secret by environment variable name, never its value:

```toml
[backends.owner-channel]
name = "slack"
[runtime.options]
slack_webhook_env = "CREW_SLACK_WEBHOOK_URL"
slack_digest_interval = 3600
```

Export the webhook in the launching environment before `mdstack up`; do not
put it in a profile, command argument, run record or log. The
[tmux notification binding](runtimes/tmux.md#slack-progress-notifications)
describes events, retries, digests and the return brief.

### `[release]`

Optional: how the project cuts and records releases through the
[release operations](release.md#release-operations)
([#585](https://github.com/mw-ding/mdstack/issues/585)). Without the table
nothing changes; mdstack's own release on GitHub needs none, since every
default below is today's behaviour.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `changelog` | string | `"CHANGELOG.md"` | CHANGELOG path, relative to the profile |
| `fragments` | string | `"changes/unreleased"` | Per-change fragment directory, relative to the profile |
| `versioning` | string: `semver` | `"semver"` | [Versioning](deliverables.md#versioning) scheme for version sections |
| `release_id` | string: `tag` or `commit` | `"tag"` | What `release.record-release` writes: a tag, or the full 40-character hash of the landed cut commit ([commit release id](release.md#commit-release-id)) |

```toml
[release]
changelog = "docs/HISTORY.md"
fragments = "notes/next"
release_id = "commit"
```

With the table, `resolve` requires `backends.release` with
`approve-check` and `record-release` kept (not `unsupported` or undeclared);
otherwise the profile is unsupported for release
([release rule](interfaces.md#capability-declaration)).
`changelog-cut.py --project config.toml` reads `changelog` and `fragments`;
its flags override them.

### `[ci]`

Optional, new in #1536: the expected-check baseline a green CI read needs at
the exact head. Without the table, every observed check at head decides as
before; a repo whose branch protection lists no required checks has no other
source for the set.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `required_checks` | list of unique, nonempty check names | none | Check run or status context names that must each be present and green at head |

```toml
[ci]
required_checks = ["markdownlint", "links", "repo-guard"]
```

`mdstack poll`, the synthesizer's gate-status CI item and `mdstack train`
build and wait read the same decision: a named check absent at head (never
created, not registered yet) keeps CI pending, never passed, and gate-status
names the missing checks. A failed or infrastructure-failed check still reads
as failed or infra. A check left out of the list, such as an optional job,
stays optional.

### `[install]`

Optional ([#882](https://github.com/mw-ding/mdstack/issues/882)): where
`--version` and `mdstack host prepare` fetch a release (`github`, `url`,
`mirror` or `git`; default `github`). The validator checks the table
([#943](https://github.com/mw-ding/mdstack/issues/943)): each source's
required keys, the pin formats, and a refusal for a key the source does not
use. Bootstrap and upgrade `--version` fetch from `url` and `mirror`
([#944](https://github.com/mw-ding/mdstack/issues/944)) and `git`
([#945](https://github.com/mw-ding/mdstack/issues/945)); with the table set,
`mdstack host prepare` installs the primary's pinned toolkit on each host and
`mdstack host check` verifies it. Keys and checks:
[release sources](bootstrap.md#release-sources-design).

### `[triage]`

Optional: the [always-on triage](triage.md) sweep
([#748](https://github.com/mw-ding/mdstack/issues/748)). Off by default.
When enabled, `mdstack watch` starts a fresh researcher session with
`mdstack spawn researcher --sweep` every `interval_hours`, at once when the
crew wakes with a sweep overdue, and skips the slot when
`<state-dir>/<owner>__<repo>/triage/queue.json` lists no items (no unplaced
issue and no owner reply). The timer costs no model turn; its last slot is
in `triage/sweep.json` ([mdstack watch](runtimes/tmux.md#mdstack-watch)).
On `runtime.name = "session"`, a hosted routine trigger runs the same loop
([session binding](runtimes/session.md#triage-sweep-routine), #1404).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | `false` | Run the sweep timer |
| `interval_hours` | integer, at least 1 | `6` | Hours between sweep slots |
| `repos` | list of `owner/name` strings (non-empty) | the project's `repo.owner/repo.name` | Tracker repos a sweep reads |
| `trackers` | list of tracker ids (non-empty, no spaces) | none (one read for the project) | A non-GitHub tracker backend only: each id fills `<tracker>` in its `tracker.list-items` binding for the scan; a GitHub tracker refuses it and reads `repos` (#1404) |
| `rules` | string: file path | none (built-in defaults) | The owner's class rules file (label maps, P0 signals, cooldowns); Riley never writes it |
| `mode` | string: `shadow` or `apply` | `"shadow"` | `shadow` writes records and proposals only; the owner sets `apply` after [calibration](triage.md#shadow-mode-and-calibration) |

### `[reflection]`

Optional: scheduled [reflection](self-improve.md#reflection)
([#1521](https://github.com/mw-ding/mdstack/issues/1521)). Off by default.
When enabled, `mdstack watch` starts `mdstack spawn researcher --reflection`
for the last full ISO week every Monday and for a milestone's window at once
when it closes, one run at a time with overlapping windows coalesced. It is
independent of `[triage]`; its pending, request and completed windows are in
`<state-dir>/<owner>__<repo>/reflection/ledger.json`
([mdstack watch](runtimes/tmux.md#mdstack-watch)).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | `false` | Run the reflection timer |

### `[status]`

Optional: shared status for independent crews
([shared status](specs/shared-status.md),
[#1313](https://github.com/mw-ding/mdstack/issues/1313)). Several installs
(crews, projects or hosts, each with its own state dir and decision log)
each publish one compact pointer/count record into one comment of one
owner-chosen issue, and `mdstack status --all` reads them back as one view
([mdstack status](runtimes/tmux.md#mdstack-status)). Off until configured:
absent, every key takes its default and `resolve` prints no `status` key. It
is team-level: in a [team file](configuration/team-files.md) the table sits
beside `[team]`, and a `[repos.<name>]` section that sets it is refused.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | `false` | The watcher's publish timer runs `mdstack status publish`; needs `destination`, `instance_id` and `decision_log` |
| `destination` | string | unset | The issue holding every instance's comment; must fully match the status backend map's `[ids] status-destination` (GitHub: `https://github.com/<owner>/<repo>/issues/<n>`) |
| `instance_id` | string | unset | This install's identity on the destination, `[a-z0-9][a-z0-9-]{0,62}`; never defaulted from `runtime.instance`, a repo, team, host or path. Different installs need different IDs |
| `decision_log` | string | unset | The crew's decision log, an issue URL; published as a pointer |
| `publish_interval` | integer | `300` | Seconds between the timer's attempts, 60-3600 |
| `stale_after` | integer | `900` | Seconds after which `status --all` marks a record stale, from 2 x `publish_interval` to 86400 |

`validate` refuses an unknown key, a wrong type (a boolean, string or float
where an integer is due), an out-of-range value and `enabled = true` with a
required key unset. `mdstack status register` creates this install's one
slot comment once; the receipt binding it lives in
`<state-dir>/<owner>__<repo>/status/receipt.json` (a team file's team root).
Binding and resolve refusals: [status concern](interfaces.md#status).

### `[docs]`

Optional: the project [docs pass](project-docs.md#docs-pass)
([#754](https://github.com/mw-ding/mdstack/issues/754)). Off by default:
with no `[docs]` table nothing runs and no key resolves; with a table, the
defaults below fill each missing key. `homes` maps a project's existing home
for an [essential doc](project-doc-set.md#essential-doc-set) instead of
moving it.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | `false` | Run the scan timer and docs-pass sessions |
| `interval_days` | integer, at least 1 | `7` | Days between passes |
| `repos` | list of `owner/name` strings (non-empty) | the project's `repo.owner/repo.name` | Repos the pass reads (project, packs, upstreams); read access only |
| `stale_days` | integer, at least 1 | `90` | Age of a banner's **Last checked** that counts as stale |
| `size_budget` | integer, at least 1 | `500` | Lines above which a doc is reported as a split candidate |
| `homes` | table: essential name to repo-relative path or `path#anchor` | the [default homes](project-doc-set.md#essential-doc-set) | Where this project keeps each essential doc; keys `overview`, `agent_guide`, `architecture`, `runbook`, `decisions`, `specs` (a directory, no anchor; #1225), any other fails |
| `specs_external` | string: an absolute URL | none | A specs home outside the repository: the tracker item or document the spec bookends name in place of a directory (#1725). A reference only, never a path or a command; it fails beside an explicit `homes.specs`. Bootstrap seeds no local spec and the scan records it unchecked. Spec-first, `[spec] paths` and every merge and evidence rule are unchanged |

### `[report]`

Optional. The [report skeleton](roles.md#report-skeleton-every-role)'s status
set and the install-wide emoji switch (#431). Changes no marker or gate.

| Key | Type | Default | Replaces |
|---|---|---|---|
| `emoji` | boolean | `true` | `false` renders `<report-status>`, `<RoleSignature>`, every `<RoleEmoji>` and every post title ([protocol §4](protocol.md#4-marker-conventions)) without emoji |
| `status.<status>` | string: emoji for `pass`, `changes`, `landed`, `escalated` or `blocked`; any other key fails | `✅` / `🔁` / `🚢` / `⛔` / `🚧`; `""` shows the word alone | `<report-status>` |

### `[identities]`

| Key | Type | Default | Replaces |
|---|---|---|---|
| `owners` | list of strings (non-empty) | *required* | `<user-logins>` |
| `team` | string: `[a-z0-9-]`, 1–63 characters, or empty | `""` | `<TeamName>`; when set, tmux window 0 is `<coordinator name>-<team>` (`ash-mdp-m4`) and `ash` stays an alias ([tmux layout](runtimes/tmux.md#layout-and-naming)) |
| `coordinator.gh_user` | string | *required* | `<author-login>` |
| `builder.gh_user` | string | *required* | `<author-login>` |
| `synthesizer.gh_user` | string | *required* | `<author-login>` |
| `reviewer.gh_user` | string | *required* | `<reviewer-login>` |
| `researcher` | table: `gh_user`, `name`, `title`, `emoji` | optional; `gh_user` resolves to `coordinator.gh_user`, then `Riley` / `Researcher` / `🔬` | the [researcher](roles.md#researcher-riley)'s author identity: `<author-login>`, `<ResearcherBot>`, `<ResearcherTitle>`, `<ResearcherEmoji>` |
| `<role>.name` | string: role display name, also the tmux window name | `Ash` / `Builder` / `Reviewer` / `Synthesizer` | `<CoordinatorBot>`, `<BuilderBot>`, `<ReviewerBot>`, `<SynthesizerBot>` |
| `<role>.title` | string: role display title | `CTO` / `Builder` / `Reviewer-validator` / `Synthesizer` | `<CoordinatorTitle>`, `<BuilderTitle>`, `<ReviewerTitle>`, `<SynthesizerTitle>` |
| `<role>.emoji` | string: signature and post-title emoji | `🔥` / `🛠️` / `🔎` / `🔀` | `<CoordinatorEmoji>`, `<BuilderEmoji>`, `<ReviewerEmoji>`, `<SynthesizerEmoji>` |

Every role signs authored posts and owner-facing replies as
`— <emoji> <name> (<title>) · <team> · <harness> · <model actually used>`,
rendered as `<RoleSignature> · <harness> · <model>` (`<BuilderSignature>` and
so on). Name, title and emoji resolve from the profile; `report.emoji = false`
drops the emoji ([`[report]`](#report)). The team is a
[team file](configuration/team-files.md)'s resolved `team.name`, else its file
name, else `identities.team`; a legacy single-repo install without
`identities.team` omits the `· <team>` part (#1291). Harness and model are
filled at run time by the authoring session, including fallback. Engine
attribution still records effort; signatures change no marker or gate.

`gh_user` is the only mechanism today: a GitHub login whose token is derived
at use, `GH_TOKEN=$(gh auth token --user <login>)` (on tmux via
`CREW_IDENTITY`, [Q5](runtimes/tmux.md#q5-identities)). A reviewer equal to
the author is the single-identity profile; `validate` allows it.

### `[engines]`

| Key | Type | Default | Replaces |
|---|---|---|---|
| `coordinator` | string: `claude-code`, `codex`, `pi` or `cursor` | `"claude-code"` | none ([tmux Q3](runtimes/tmux.md#q3-coordinator-engine)) |
| `fallback_engine` | string: an `<engine>` below | none | `<fallback-engine>` |
| `trivial`, `default`, `deep` | table, *required* each | *required* | the [current routing](roles.md#current-routing) row of that tier |
| `<tier>.order` | list of `<engine>/<model>` strings, first choice first | *required* | `<engine>`, `<model>` |
| `<tier>.effort` | string: `low`, `medium` or `high` | `low` / `medium` / `high` by tier ([tiers](roles.md#tiers)) | `<effort>` |
| `roles.<role>.order` | list of `<engine>/<model>` strings, first choice first; `<role>` is a spawned role (`builder`, `reviewer`, `synthesizer`) | none: the tier's `order` | none ([per-role override](roles.md#per-role-engine-override)) |

`<engine>` is one of `claude-code`, `codex`, `muse`, `opencode`, `pi`, `cursor`
([harness adapters](runtimes/harness-adapters.md)); any other engine
fails. The [hard rules](roles.md#hard-rules) still apply to whatever the order
names. A `[engines.roles]` entry replaces the tier's `order` for that role's
workers at every tier; the tier still sets `effort`, and reviewer independence
still filters the role's order. Role leads keep the `default` tier order. Pi accepts provider-qualified models (for example
`pi/anthropic/claude-sonnet-4-5`) and requires `permission_mode = "bypass"`.

### `[size_budget]`

Optional per-role limits for bootstrap's [self-test](bootstrap.md#q7-self-test)
(#194). Keys are `coordinator`, `builder`, `reviewer` and `synthesizer`;
each is a positive integer, default **16384 bytes** (16 KiB). For example:

```toml
[size_budget]
coordinator = 12288
builder = 8192
```

The limit applies to the path-normalized UTF-8 bytes of each rendered Markdown file for that role:
`briefs/<role>.md` and `runtime/<role>.md` or `runtime/<role>-*.md`.
For this measurement only, every install-time placeholder mapped to `paths.*`
is rendered as the fixed six-byte token `<path>`; other profile values remain
expanded. Install-path length cannot change the result. Deployed files retain
their real paths. Shared installation instructions (`wiring.md`) are excluded. A file exactly
at the limit passes; an oversized file fails the self-test, naming its
render-relative path, path-normalized UTF-8 byte count, role and budget. Missing keys use
the default; org and project overrides follow normal layer precedence.

Every successful `crew-render` also prints this measure to stderr, one line per role
file, as `crew-render: budget <file> <bytes>/<budget> bytes (<percent>%), delivered <bytes> bytes`.
The delivered size is the deployed file, core memory and render notes included. A file within 5% of
its budget, or over it, adds a `crew-render: WARNING` line. The exit code does not change (#1056).

### `[tools.<name>]`

Optional doctor checks for tools the profile names (#193). `running` and
`installed` are required, nonempty argv arrays for read-only version probes;
doctor runs them without a shell, with a 30-second timeout. The running
probe must query the existing session, rather than launch a fresh copy of
the installed tool. The profile supplies the tool-specific probe.

```toml
[tools.example]
running = ["example-session", "version"]
installed = ["example", "--version"]
pin = "2.10.0"
```

Each probe prints a numeric release version `X.Y.Z` (optional `v` prefix
and surrounding text). Optional `pin` is a minimum `X.Y.Z` or `vX.Y.Z`,
compared numerically. Prerelease/build versions are not supported.
Matching versions at or above the pin print `ok`. A running/installed
mismatch or either version below the pin prints `warn` with a restart or
upgrade hint. Failed or unreadable probes print `warn`; they never count
as a match. Drift warnings do not change doctor's exit code, and `--fix`
never upgrades or restarts tools. With no `[tools]`, no probes run.

### `[paths]`

| Key | Type | Default | Replaces |
|---|---|---|---|
| `state_dir` | string | *required* | `<state-dir>` |
| `worktree_root` | string | *required* | `<worktree-root>` |
| `toolchain_bin` | string | none | `<toolchain-bin>` |
| `live_dir` | string: the deployed live copy, laid out like `crew-render.py --out` | none | none (read by `check-skill-drift.py --project`, #128) |
| `pack` | string: pack directory, absolute or relative to this project file | none | records the org pack for resolution |
| `mdstack` | string: absolute path of the mdstack checkout, so briefs cite its docs in any repo | none | `<mdstack>` |
| `checkout` | string: the git checkout that role worktrees, trains and host prepare use, absolute or relative to this project file (to `root` when set) | the project file's directory | none (lets a non-git runtime home name its repo checkout, #1178; a team file sets it per repo as `[repos.<name>] checkout`, #1287) |
| `root` | string: one movable base; each relative `state_dir`, `worktree_root`, `live_dir`, `mdstack` and `checkout` resolves under it, and `<owner>` and `<repo>` in those values take `[repo]` owner and name (#1316). A set `CREW_ROOT` overrides it | none (relative values keep resolving as before); `profiles/tmux.toml` sets `~/.mdstack` | none ([home-level layout](runtimes/tmux.md#home-level-layout-1178), #1178) |

A key with default "none" may be left out of one file; the
[default profile](../profiles/default.toml) sets them except the optional `pack`.

### `[hosts.<name>]` and `[placement]`

Optional: the host inventory and project affinity of a multi-device tmux
crew (20.2, [#204](https://github.com/mw-ding/mdstack/issues/204); design in
[multi-device](runtimes/multi-device.md#host-inventory-profile-extension)).
With no `[hosts]` table the crew runs on one machine, as today. A host is
named by its overlay network name only, never by an address, user, port or
credential (spec R1). Keep these tables in the host-local project
`config.toml` or the org layer, never in mdstack. They replace no template
placeholder; `validate` checks them, and `mdstack spawn` places role runs
from them ([placement](runtimes/multi-device.md#placement), #207). A
`runtime.name = "session"` profile may also carry `[hosts]` so
`mdstack host check` and `host prepare` report on its hosts (#1122); it takes
no `[placement]`, since only tmux spawn places runs.

```toml
[hosts.host-a]
primary = true
capabilities = { os = "macos", arch = "arm64", engines = ["claude-code", "codex"] }
max_runs = 2

[hosts.host-b]
capabilities = { os = "macos", arch = "arm64", devices = ["ios-simulator"], engines = ["codex"] }
max_runs = 1
roles = ["reviewer"]

[placement]
hosts = ["host-a"]

[[placement.rules]]
role = "reviewer"
pass = "validate"
paths = ["ios/**"]
needs = { devices = ["ios-simulator"] }
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `hosts.<name>` | table; `<name>` is a DNS label (`[a-z0-9-]`, 1–63 characters) | none | The host's overlay network name, also its SSH destination unless `address` is set |
| `hosts.<name>.address` | string: a dotted DNS name (`[a-z0-9-]` labels; no IP literal, `user@` or `:port`) | the label | The SSH destination in place of the label, for a host reached by its fully qualified name; the label stays the inventory key |
| `hosts.<name>.primary` | boolean | `false` | Exactly one host is `true`; it runs the coordinator and synthesizer |
| `hosts.<name>.capabilities.os` | string: `linux` or `macos` | *required* | The host's OS |
| `hosts.<name>.capabilities.arch` | string: `x86_64` or `arm64` | *required* | The host's architecture |
| `hosts.<name>.capabilities.devices` | list from `ios-simulator`, `ios-device`, `android-emulator`, `android-device` | `[]` | Attached devices; a new kind is a schema change |
| `hosts.<name>.forge` | boolean | `true` | `false` marks a [forge-less host](runtimes/multi-device.md#forge-less-hosts-remote-test-runner): runner jobs only, never a role session. It needs no `engines`; `validate` refuses it as the primary, with a non-empty `roles` or in `placement.hosts`. `mdstack host check` shows its logins check as `n/a`, or `warn` if a forge login is found there |
| `hosts.<name>.capabilities.engines` | list of `<engine>` (non-empty) | *required*; none when `forge = false` | Engines logged in on that host |
| `hosts.<name>.max_runs` | integer ≥ 1 | *required* | This crew's concurrent role runs on that host; its concurrent runner jobs on a forge-less host |
| `hosts.<name>.roles` | list from `builder`, `reviewer` | both | Roles placed there |
| `hosts.<name>.root` | string: path on that host | `~/.mdstack` | Mirrors, worktrees and host state |
| `hosts.<name>.toolchain_bin` | string: path on that host | none | `<toolchain-bin>` for builders there |
| `hosts.<name>.checkout` | string: `mirror` or `command` | `mirror` | `command`: `mdstack host prepare` runs the checkout command that host declares in `<root>/checkout/<owner>__<repo>.json` in place of the git mirror or seed steps, for a checkout made by its own VCS ([command checkout](runtimes/multi-device.md#command-checkout), #1035); on the primary it runs locally and its declared `path` must be the project checkout (#1723) |
| `hosts.<name>.connect.alias` | string: a DNS label, unique across host names and aliases | none | A short name for [`mdstack connect`](runtimes/multi-device.md#connect-to-a-host); the host name always works too |
| `hosts.<name>.connect.transport` | string: `ssh`, `mosh` or `et` | `ssh` | The owner's login transport for `mdstack connect` |
| `hosts.<name>.connect.proxy` | string: an SSH `ProxyCommand` | none | Passed to `ssh -o ProxyCommand=` (directly, or through mosh's `--ssh` with `--experimental-remote-ip=remote`); `validate` refuses it with `et`, which reads it from the owner's SSH config |
| `hosts.<name>.connect.options` | list of strings | `[]` | Fixed transport options, before any passed through on the command line |
| `placement.hosts` | list of host names (non-empty), preferred first | the primary | Project affinity |
| `placement.rules` | array of tables: `role` and `needs` *required*, `pass` and `paths` optional | `[]` | Capability exceptions; first match wins |

In a rule, `role` is `builder` or `reviewer`, `pass` is one of that role's
`mdstack spawn` passes (`build`, `fix`; `review`, `validate`), `paths` is a
non-empty list of changed-path globs, and `needs` is a table of `os`, `arch`
and `devices` with the values above.

`validate` also fails on: a host name that is not a DNS label (so an IP
literal, `@` or `:`); zero or several primaries; `[placement]` without
`[hosts]`; a `placement.hosts` entry that names no host; a `roles` entry
other than `builder` or `reviewer` (the coordinator and synthesizer run on
the primary only); a role that no `placement.hosts` host takes; a rule whose
`needs` no host taking its role meets; and `[hosts]` with a runtime other
than `tmux`.

### Pack manifest

`connectors/<backend>/manifest.toml` is a backend's own
[capability declaration](interfaces.md#capability-declaration):
`[pack]` with `name` (lowercase letters and digits separated by hyphens), `commands` (the doc holding its
command mapping), for a pack outside mdstack, `mdstack_version`
([packs](packs.md#version-pin)), an optional SemVer `version` naming the
pack's own release, distinct from that pin ([pack version](packs.md#pack-version)),
an optional `harness` naming a pack-relative
[harness pointer registry](bootstrap.md#pack-harness-pointers-design) file
(#883),
and `[capabilities.<concern>]` with every operation key of
that concern, all *required*. `[capabilities.release]` is optional; when present, all four keys are required. `[capabilities.classify]` is optional; when present, `sensitive` is required. A profile's `capabilities` table overrides it; `resolve` folds it in
(see [Layers and precedence](#layers-and-precedence)).
`validate` treats a file with a `[pack]` table as a manifest; today's is
[connectors/github/manifest.toml](../connectors/github/manifest.toml).

`validate` and `resolve` check a `pack.harness` registry statically
([#964](https://github.com/mw-ding/mdstack/issues/964), slice B1 of #883):
the file and every `source` and `launch_note` must resolve, symlinks
followed, to a regular UTF-8 file inside the pack directory, and the
registry is a list of `[[pointer]]` tables. An entry with `launch_note` takes
only `harness` (`codex`) and `launch_note`; any other entry takes `harness`
(`claude-code` or `codex`), `target`, `source`, an optional `mode`
(`copy` or `pointer`) and an optional `root` (`project`, the default, or
`home`, the per-user agent home, #1032). An adapter without an install pointer (`pi`, `muse`,
`opencode`, `cursor`) and an unknown name are refused. A `target` must be
relative to its root and normalized (no leading `/` or `~`, no empty, `.`, `..`
or `.git` component), unique within its root, and, for a project root, none
of the built-in bootstrap targets.
`mdstack bootstrap --harness` installs the entries and records them under
`harness_pointers` ([#965](https://github.com/mw-ding/mdstack/issues/965)).

An optional `[land]` table declares the
[asynchronous land](interfaces.md#declaration) (#873): `mode` (`sync` or
`async`, default `sync`), and the booleans `opens_draft`, `serializes` and
`tests_against_tip` (default `false`). Under `async` it also takes
`change_placeholder`, `head_guard` and a `[land.status]` table (#1042, see
[Declaration](interfaces.md#declaration)). Without it the backend is `sync`.
A [stack land](interfaces.md#stack-land) adds `stack`,
`stack_tests_against_tip` and, from #1722, `stack_status` (`stack` or
`per-change`); a sync stack binding also takes `change_placeholder`, and a
per-change one a `[land.status]` table.
`validate` rejects `async` with `change.land-status` undeclared or
`unsupported`, `opens_draft = true` with `change.publish` undeclared or
`unsupported`, and any of the three booleans true under `sync`. `resolve`
repeats both capability checks on the effective `change` capabilities of the
backend bound to `change`, refuses `async` under a runtime without an async
land binding (every runtime but `tmux` and `session`, #1351), and prints the declared keys after
the profile as `land.<key> = <value>  # <pack layer>`, outside the profile.
The schema is all that is in effect yet: no role reads it until the later
slices of #873 land.

An optional `[strategy]` table declares how the backend
[updates a change from its base](interfaces.md#declaration-2) (#874):
`update_from_base` (`merge` or `rebase`, default `merge`) and the boolean
`retains_prior_heads` (default `false`). Without it the backend updates by
merge. `validate` rejects `rebase` unless `retains_prior_heads = true`, and
`retains_prior_heads = true` under `merge`. `resolve` repeats both checks on
the manifest of the backend bound to `change` and prints the declared keys
after the profile as `strategy.<key> = <value>  # <pack layer>`, outside the
profile. The renderer reads the resolved `update_from_base` for the brief
wording, and `mdstack train build` and `bisect` refuse under `rebase`.

## Validate

Moved to
[Configuration resolution: Validate](configuration/resolution.md#validate):
both `validate` command variants, the `file:key: reason` problem format and
exit codes, the full rejection list, and the `--install` check that rejects
install-time placeholders while allowing run-time ones, including the same
check on the effective profile through `resolve --install`.

## Layers and precedence

Moved to
[Configuration resolution: Layers and precedence](configuration/resolution.md#layers-and-precedence):
the `resolve` command and its four-layer table, the merge rule and its
`identities`, `backends` and `engines` exceptions, the cross-key checks
(unsupported invariant with pack-manifest fill, single identity, integer
limit), and the provenance output, problem format and example.

## Team files

Moved to [Team files](configuration/team-files.md):
[schema and example](configuration/team-files.md#schema-and-example) (the
team file's location and name, the optional `team.name`, the `[team]` tables with the `pack`,
`personas` and `accounts` shorthands, the `[repos.<name>]` allowlist and its
refusals, and an example with two repo sections),
[resolution and the team instance](configuration/team-files.md#resolution-and-team-instance)
(project references, clone location, the shared state root and session, and
`mdstack up --team`), and the migration below.

### Migration: two `config.toml` files to one team file

Moved to
[Migration: two `config.toml` files to one team file](configuration/team-files.md#migration-two-configtoml-files-to-one-team-file):
the five steps from two `config.toml` files to one team file, with the
`resolve` comparison and the stop, state-move and start order.
