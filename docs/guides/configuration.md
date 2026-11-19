# Configuration guide

How to configure a crew once the [first run](getting-started.md) works,
organized by task: which file applies, who the roles are, which engines run
them, which repos they serve, how many run at once and how much rigor each
change gets. Every section links the page that owns the exact keys and
defaults; this guide adds no key, rule, gate or default of its own.

Two controls are easy to mix up. **Speed** (caps, presence and the
scheduler) sets how many workers run at once. **Rigor** (the
[flavor](../flavors.md)) sets how much review, validation and evidence each
change needs. Changing one never changes the other.

## 1. Know which file applies

Owner commands read `$MDSTACK_CONFIG`, else the user-level
`~/.mdstack/config.toml`, else the root's only team file. An owner shell
refuses `--project` (exit 2); crew windows keep it
([user-level and project-level config](../runtimes/tmux.md#user-level-and-project-level-config-1316)).
Every command that can write prints the file it acts under as
`mdstack: config <path>`.

Check an edit before you use it:

```sh
python3 ~/.mdstack/releases/current/core/crew-config.py resolve --project ~/.mdstack/config.toml
```

`resolve` merges your file over the shipped
[default profile](../../profiles/default.toml) and any org pack, and prints
each key with the layer it came from. `validate` checks one complete file
alone, so it reports a short layered file's inherited keys as missing
([resolution](../configuration/resolution.md)). `mdstack up` renders the
role briefs from the resolved profile
([mdstack up](../runtimes/tmux.md#mdstack-up)). All keys:
[profile.md: Keys](../profile.md#keys).

## 2. Set identities

`[identities]` names the owners and a GitHub login (`gh_user`) for each role:
coordinator, builder, reviewer, synthesizer and the optional researcher. A
token is derived per login at use, so `gh` must be logged in as every login
you name ([`[identities]`](../profile.md#identities)).

- **One account.** Every `gh_user` is your login. GitHub refuses an author's
  own approval, so the verdict is a signed COMMENT review and the review
  backend declares `post-verdict` as emulated
  ([single-identity profile](../interfaces.md#single-identity-profile)).
- **Separate reviewer.** `reviewer.gh_user` is a second account that can
  approve; drop the emulated `[backends.review]` block
  ([identities](../runbooks/prerequisites.md#identities)).

`<role>.name`, `title` and `emoji` set the persona each role signs with and
its tmux window name; `identities.team` names a single-repo team. Neither choice
grants merge permission: that stays a recorded owner merge-ok per PR, or a
standing [`merge_grant`](../configuration/runtime-options.md#tmux-options).
The walkthrough's [Choose identities](getting-started.md#choose-identities)
table compares both.

## 3. Choose engines

`[engines]` routes work to coding harnesses
([`[engines]`](../profile.md#engines),
[harness adapters](../runtimes/harness-adapters.md)):

| Key | What it sets |
|---|---|
| `coordinator` | The coordinator's harness |
| `trivial`, `default`, `deep` | Per [tier](../roles.md#tiers): an `order` of `<engine>/<model>` choices, first with quota wins, and an `effort` |
| `roles.<role>.order` | Replaces the tier order for one spawned role at every tier ([per-role override](../roles.md#per-role-engine-override)) |
| `fallback_engine` | The engine to fall back to |

The coordinator records each item's tier on its flavor record; a spawn uses
it unless a dispatch names another. Whatever your orders say, the reviewer's
engine must differ from the engine that built the round
([reviewer engine selection](../roles.md#reviewer-engine-selection)), so
configure at least two working engines. The
[hard rules](../roles.md#hard-rules) apply to every order.

## 4. Select teams and repos

| You run | Use | Owner commands select a repo with |
|---|---|---|
| One repo | A `config.toml` with `[repo]` | nothing: it is the only repo |
| One crew for several repos | A [team file](../configuration/team-files.md): the crew once under `[team]`, one `[repos.<name>]` section per repo | `--repo <key>` |
| A separate crew | Its own file, picked with `MDSTACK_CONFIG` (`<file>` or `<file>#<repo>`) | its own file |

A team file's `[repos.<name>]` sections hold only what differs per repo:
`repo`, `checkout`, `default_branch`, sensitive and spec paths, the project
keys and the landing overrides such as `merge_grant`. Anything else is
team-only, and a landing grant never spans the team
([schema and example](../configuration/team-files.md#schema-and-example)).
`mdstack up`, `start` and a bare `attach` take the whole team; every other
owner command is per repo, and a multi-repo team without `--repo` exits 2
naming the keys. One session and one state root serve every repo of a team
([team instance](../configuration/team-files.md#resolution-and-team-instance)).
A project's optional `milestones` key lists its milestones in priority
order ([project keys](../configuration/team-files.md#project-keys)).

## 5. Set concurrency and speed

Speed lives in `[runtime] options`
([`tmux` options](../configuration/runtime-options.md#tmux-options);
[`session` options](../configuration/runtime-options.md#session-options)).
The shipped defaults:

| Control | Keys | Default |
|---|---|---|
| Pool caps | `builders`, `reviewers`, `researchers` | 5, 2, 2 on tmux (researchers 0 on session) |
| Owner-present limits | `present_builders`, `present_reviewers` | the full cap |
| Optional machine ceilings | `max_suites`, `max_load` | none: admission is caps only |
| Scheduler target | `load_high`, `load_low`, `error_high`, `memory_high` | 6.0, 4.0, 3, by speed mode |
| Ramp | `schedule_interval`, `schedule_ramp` | 120 s, 2 starts per interval |
| Milestones dispatched at once | `max_active_milestones` | 1 |
| Idle builder reclaim | `idle_builder_ttl` | 1800 s |

While you are present the leads admit up to the present limits; in a
recorded [away mode](../protocol.md#owner-away-mode) they use the full caps,
optionally bounded by an away `--cap`. A switch applies on the next lead
wake, and running workers drain rather than being stopped
([builder lead](../runtimes/tmux.md#builder-lead)). Within those caps the
[crew scheduler](../scheduling.md) ranks demand crew-wide and grows or
shrinks its target from machine load, memory and gateway errors. The
scheduler calls it **full speed** when every effective cap equals its full
cap and **light mode** when any is lower
([memory threshold](../scheduling.md#memory-threshold)). The lead windows
run outside the caps, and land stays serial
([Q6](../runtimes/tmux.md#q6-concurrency)).

A deployment may name its own sets of these values, such as a "light",
"normal" or "full speed" preset for its machine and quota. Those are that
deployment's preferences, recorded in its own config or decision log, not
product defaults; size yours to your machine and engine quotas, starting
from the defaults above.

## 6. Pick the rigor (flavor)

`[flavor] name` picks a preset for the project: `thorough`, `standard`,
`fast` or `solo`. Unset, it is `standard`, and `resolve` flags the gap
([profile schema](../flavors.md#profile-schema)). Each preset sets the rigor
knobs: review depth, validation, engine diversity, round and CI-fix caps,
evidence, merge permission, the pre-review check and validation scope
([presets](../flavors.md#presets), [knobs](../flavors.md#knobs)).

- **Per path.** `[[flavor.classes]]` gives matching paths another flavor; a
  class below the project flavor needs a `reason`
  ([class rule](../flavors.md#class-rule)).
- **Per item.** The coordinator records an item flavor on the issue; lowering
  it needs a `Reason:` line. `express` is item-only
  ([resolution](../flavors.md#resolution), [express lane](../express-lane.md)).
- **Per change.** Each role takes the knob-wise strictest of the item and
  path flavors at head.

The flavor's `caps` knob is the review round and CI-fix cap, not a
concurrency cap; the flavor's `parallelism` knob is validated against the
runtime caps, and the leads admit by the runtime options above. The `merge`
knob and `merge_grant` give permission only: they never supply an approval
or skip CI. No flavor crosses the [floor](../flavors.md#floor), so
`crew:sensitive` changes still need a per-change owner merge-ok.

## Next

- Connectors other than GitHub, or a knowledge source:
  [configuring connectors](connectors.md).
- Every key with its type and default: [profile.md](../profile.md),
  [runtime options](../configuration/runtime-options.md),
  [team files](../configuration/team-files.md) and
  [flavors](../flavors.md).
- Run, upgrade or recover a crew: the [runbook](../runbook.md).
