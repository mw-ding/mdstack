# Role registry (design)

> - **Status:** built
> - **Applies to:** the engineering role definitions `roles/eng/<role>.toml`
> - **Current rules:** [protocol](protocol.md) for gates and markers; [roles](roles.md)
> - **Built:** [Schema](#schema) and [Validation contract](#validation-contract) (#317, #318); the validator, renderer and tmux runtime read the registry; [Lifecycle](#lifecycle) (#1231)
> - **Design only:** none; [Hard-coded locations to replace](#hard-coded-locations-to-replace) is the migration inventory, kept as history
> - **Last checked:** 2026-11-07 at `70f11f7`

`roles/<domain>/<role>.toml` describes one role of a domain as data (roadmap
15.7, [#317](https://github.com/mw-ding/eng-crew/issues/317), part of #110).
Each file is that role's one authored definition, and its file stem is the
role ID. The registry is the union of a domain's files, in `rank` order with
unranked roles after, by ID (#1185).
This schema records today's four orchestration roles and the read-only
researcher (#584). `eng-backend`,
`eng-web` and `eng-infra` are worker areas, not extra runtime roles.
The profile validator, renderer and tmux runtime read the engineering registry.
The [protocol](protocol.md) still owns gates and markers.

## Schema

TOML 1.0, Python 3.11+ `tomllib`: one file per role, each a closed top-level
table starting `schema_version = 1`. Domain and role IDs match
`[a-z][a-z0-9-]*`; role IDs are data, not an enum compiled into the machinery.
A selected domain has one registry, with no layering or cross-domain relations
in this version. Every key below is required unless marked optional.

| Key | Type / meaning |
|---|---|
| `schema_version` | Integer `1`. |
| `rank` | Optional positive integer; registry order. Unranked roles follow the ranked ones, by ID. |
| `display_name` | Nonempty string; fallback name, overridden by the identity's profile `name`. |
| `class` | `owner-facing` (a seat the owner addresses directly) or `internal` (staff that never faces the owner); see [Role classes](#role-classes). |
| `seat` | Seat ID (`[a-z][a-z0-9-]*`), as in [`roles/seats/<seat>/`](../roles/seats/TEMPLATE.md): the seat an owner-facing role holds, or an internal role's owning seat. |
| `escalation` | Required for an `internal` role, absent for an `owner-facing` one: ordered, distinct other role IDs of this registry, ending at the owner-facing role holding the same `seat`. |
| `head` | Optional boolean; exactly one role per registry is the team head (`head = true`). |
| `identity_key` | String naming an `identities.<role-id>` profile table; login stays in the profile. |
| `marker_role` | Nonempty string used in existing markers; reviewer uses `reviewer-validator`. |
| `passes` | Ordered, nonempty list of distinct pass IDs; first is the default. |
| `inputs` | Table with exactly the pass IDs as keys; each value is a list containing `issue`, `change`, both, or neither. |
| `change_pass` | Optional pass ID; default when a change is supplied (builder `fix`). |
| `engine_source` | `coordinator` (profile `engines.coordinator`) or `tier` (profile tier order and effort). |
| `identity_independent_of` | Optional role ID; preserve the reviewer/builder identity invariant and its existing emulated-capability exception. |
| `engine_independent_of` | Optional role ID; exclude that role's actual engines under the existing [engine rules](roles.md#actual-builder-engine). |
| `templates` | Table keyed by supported runtime, each a nonempty list of template paths relative to the repo root. |
| `events` | Table keyed by supported runtime, each a list of consumed event IDs; empty is allowed. |
| `window_band` | Two integers, inclusive tmux index range; singleton for session roles. |
| `window_name` | Pattern using only `{name}`, `{issue}`, `{change}`, `{round}`, `{pass}`; `name` is the resolved display name in lowercase. |
| `lifetime` | `session`, `issue` or `pass`, matching the [tmux layout](runtimes/tmux.md#layout-and-naming). |
| `cap_key` | Optional profile integer key; omitted means the band alone limits concurrency. |
| `cap_default` | Optional integer; with a `runtime.options.<name>` `cap_key`, the tmux default for that cap. |
| `cap_min` | Optional `0` or `1` (default `1`); `0` lets a profile set the cap to 0 to run no such role, and then renders none of its templates. |
| `identity_defaults` | Table of `name`, `title` and `emoji` strings: the core defaults of the role's profile identity. |
| `identity_optional` | Optional boolean; a profile may leave the identity out, and its `gh_user` resolves to the coordinator's author login. |
| `default_tier` | Optional `trivial`, `default` or `deep`; the tier `mdstack spawn` uses without `--tier` (default `default`). |
| `completion` | Required for a `tier` role, else absent: `done` (a `done:` or `failed:` status line ends the run) or `failed` (only `failed:` does; the run stays after `done:`, as a builder stays for fixes). |
| `relay` | Required for a `tier` role, else absent: `core` (an explicit core handler routes the result) or `coordinator` (`mdstack route` closes the finished run and leaves its wake for the coordinator to relay). `coordinator` needs `completion = "done"`. |
| `placement` | Optional list of the role's passes that [host placement](runtimes/multi-device.md) may route; a `tier` role only. |
| `discovery` | Optional table keyed by binding ID: the rendered brief name (`runtime/<name>.md`) bootstrap's self-test requires. Runtimes other than tmux check the `grok-bot` name. |
| `lifecycle` | Optional table: the role's on-demand [lifecycle](#lifecycle) (`policy`, `min`, `max`, `idle_ttl`, `wake`); a `tier` role without `cap_key` only. |
| `knowledge` | Optional list of distinct source names (`[a-z][a-z0-9-]*`) the role may read and propose edits to through the [knowledge concern](interfaces.md#knowledge) (#1229). Only names: the install's private config maps each to its page and credential. Without it the role reaches no source. |

`window_band`, `window_name`, `lifetime`, `cap_key`, `cap_default`,
`cap_min`, `default_tier`, `completion` and `relay` describe tmux;
other runtimes use their binding's session mechanisms. `templates` and
`events` use binding IDs (`tmux` and `grok-bot` today). Template paths must name
existing files, remain inside the repo and contain no traversal components.
No credentials, commands, plugin callbacks or gate expressions are allowed.

## Lifecycle

`lifecycle` (#1231) lets any role run in the terminal on demand. Its keys,
all required:

| Key | Type / meaning |
|---|---|
| `policy` | `always-on` (`min = max`), `elastic`, a lead plus elastic workers (`1 <= min < max`), or `ephemeral` (`min = 0`). |
| `min` | Integer >= 0: instances `mdstack up` starts with the session, and the floor scale-down keeps. |
| `max` | Integer >= 1 and >= `min`, within `window_band`: the role's cap, so `cap_key` is not allowed. |
| `idle_ttl` | Integer seconds >= 0: an instance idle this long is killed down to `min`; `0` never idles out. |
| `wake` | Nonempty list of distinct triggers: `manual` (`mdstack up <role>`), `routine` (a due [routine](routines.md) of the role, #1247) or tmux event IDs. |

The role's first pass takes no inputs and its `window_name` uses only
`{name}` and `{pass}`: an instance has no item. The tmux runtime:

- `mdstack up` starts `min` instances of each lifecycle role
  after the pool leads (`roles = "tmux"` only).
- `mdstack up <role>`, with the session running, starts one
  more instance of a role whose `wake` has `manual`, through `mdstack spawn`.
  Instances are named `window_name`, then with `2`, `3` up to `max` appended.
  At `max` it refuses, exit 1; a role without a lifecycle or the `manual`
  wake is refused, exit 2.
- `mdstack watch` scales down on every scan: an instance with no pane output
  and no inbox message for `idle_ttl` seconds, and no unacknowledged
  message, gets `mdstack kill`, longest idle first, until `min` remain. A
  session backend that reports no pane activity (herdr) never scales down.

Event IDs in `wake` are declared only: the watcher starts no instance on an
event yet. With `routine`, the watcher starts an instance for a due routine
and messages it the routine ([routines](routines.md#terminal)); with none
due, the role starts nothing. A role without `lifecycle`, every engineering role among them,
keeps its `lifetime` behaviour: the coordinator is always on, builders and
reviewers are elastic workers under their pool leads, and the researcher is
ephemeral per pass.

## Validation contract

The future loader rejects unknown keys, wrong types (including booleans as
integers), unsupported schema versions, missing required fields and secret
patterns, using the [profile validator conventions](profile.md#format).
Errors identify `roles/<domain>/<id>.toml:<key>: reason`; invalid input
writes nothing.
It also rejects unresolved identity/cap keys, nonpositive caps, invalid or
overlapping bands, unknown relation targets or self-relations, a `change_pass`
not in `passes`, input/pass key mismatches and unavailable pattern inputs.
For the lifecycle keys it also rejects a missing `identity_defaults` field, a
cap below `cap_min`, cap keys outside `runtime.options`, an unknown
`default_tier`, a `tier` role without `completion` and `relay` (or a
coordinator-sourced role with them), `relay = "coordinator"` without
`completion = "done"`, `placement` naming another role's pass and
`discovery` naming an unknown binding, and a `lifecycle` that breaks the
[Lifecycle](#lifecycle) rules.
For role classes it rejects a missing `class` or `seat`, an unknown class, an
invalid seat ID, an owner-facing role with an `escalation` path, an internal
role whose path is missing, repeats a role, names itself or an unknown role,
or does not end at the owner-facing role holding its seat, and a registry
without exactly one team head.
Pass IDs and event IDs must match the selected binding's declared vocabulary;
adding a role reuses that vocabulary without adding a machinery role switch.

One event has one consumer per runtime and scope, preserving
[protocol §8](protocol.md#8-safety). Grok Bot's existing per-change terminal
watch exception is retained by its binding: builder B2 and reviewer V2 both
receive terminal events; the repo-wide coordinator event is a different scope.
The tmux lists below reproduce `CONSUMER`. Grok Bot event scopes and its
watch routing remain in the binding; steering, timers and ownership wakes
also keep their binding-specific routing; no new subscriptions
or merge permissions follow from registry membership.

## Role classes

Each role is an **owner-facing seat** or **internal staff**
([team spec REQ-20 to REQ-22](specs/team.md#seats-staff-and-team-heads), #1227).
Only an owner-facing seat delivers owner asks and reports
([protocol §2](protocol.md#2-stages)); internal staff escalate along their
`escalation` path to their owning seat, which decides or carries the ask.
Technical matters go to the technical seat, `cto`. A registry is one team, with
one head that coordinates it. A team head that faces the owner is that team's
seat; a head under another seat is internal staff whose path ends at that seat
(team spec Q1). In the engineering registry the coordinator is the team head and
holds the `cto` seat; the builder, reviewer, synthesizer and researcher are
internal staff with `seat = "cto"` and `escalation = ["coordinator"]`. Classes
change no gate, marker, subscription or merge permission.

## Worked registry: engineering domain

[roles/eng/](../roles/eng/) holds one file per current role, filled for tmux:
`coordinator`, `builder`, `reviewer`, `synthesizer` and `researcher`.
Grok Bot retains its existing templates and scoped events
in [wake wiring](runtimes/grok-bot.md#wake-wiring-event-to-consuming-role);
these tmux entries must never supply subscriptions for that runtime.
The coordinator's `coordinate` pass names its existing session duty, not a new
`mdstack spawn` command. tmux `new-head` includes first PR discovery; Grok Bot
uses `pr-opened`. `fix-at-head` is tmux's existing evidence-only fix wake.
The researcher's file, as an example:

```toml
# roles/eng/researcher.toml
schema_version = 1
rank = 5
display_name = "Riley"
class = "internal"
seat = "cto"
escalation = ["coordinator"]
identity_key = "identities.researcher"
marker_role = "researcher"
passes = ["research"]
inputs = { research = ["issue"] }
engine_source = "tier"
templates = { tmux = ["templates/runtimes/tmux/researcher.md", "templates/runtimes/tmux/researcher-triage.md"] }
events = { tmux = [] }
window_band = [40, 44]
window_name = "{name}-{issue}"
lifetime = "pass"
cap_key = "runtime.options.researchers"
identity_defaults = { name = "Riley", title = "Researcher", emoji = "🔬" }
identity_optional = true
cap_default = 2
cap_min = 0
default_tier = "deep"
completion = "done"
relay = "coordinator"
```

## Adding a role

A role that reuses an existing lifecycle (its passes, events, completion and
relay values already exist) is one role definition plus tests: add
`roles/<domain>/<role>.toml` and the brief its `templates` names. The profile
schema, identities, cap, `mdstack spawn`, rendering, completion and relay,
bootstrap discovery and `mdstack kill` read it without edits. Make the identity
`identity_optional` (or add it to the profile) and the cap `cap_default`, so
existing profiles still resolve, and `relay = "coordinator"`: `core` names
the explicit build, review, validation and land handlers, which stay core
contracts keyed by role and are not taken over by a new definition.
A new pass, event, lifecycle or gate is a machinery and protocol change, not
a registration.

Validate them with `python3 core/crew-roles.py roles/eng` (optionally
`--project config.toml` for resolved identity and cap keys). The equivalence test
compares them with runtime metadata and the remaining renderer constants.

## Personnel import design

The [M51 import contract](specs/team.md#96-pinned-personnel-import-and-host-binding)
selects pinned content by stable domain/role ID and attaches a thin host
binding. #1180 implements it; it introduces no registry layering or external
role discovery here. Presentation, engine and additive-skill settings retain
provenance and existing checks. Role class/escalation, marker/pass semantics,
reviewer independence and synthesizer-only land cannot be replaced through
imported data, a binding or a prose overlay.

## Hard-coded locations to replace

| Location | Registry data that replaces the role-specific knowledge |
|---|---|
| [crew.d/_shared.py](../environments/terminal/crew.d/_shared.py) | `BANDS`, `PASSES`, `NAMES`, `CAPS`, `brief_src` template selection and `window_env` identity lookup. |
| [crew.d/poll.py](../environments/terminal/crew.d/poll.py) | `CONSUMER` becomes the inverse of the selected runtime's event lists. |
| [crew.d/spawn.py](../environments/terminal/crew.d/spawn.py) | Role/pass CLI choices, default fix pass, input checks, window/item/run/claim/worktree names, reviewer round/verdict handling and `pick_engine` independence branch. |
| [crew.d/up.py](../environments/terminal/crew.d/up.py) | Coordinator name, index 0, identity, brief and engine source. |
| [crew-config.py](../core/crew-config.py) | Identity role list, `PLACED_PASSES` host/placement choices, coordinator engine source and reviewer/builder identity relation in capability validation. |
| [crew-render.py](../core/crew-render.py) | `ROLES`, role template jobs and role-specific `MAPPED` identity/display-name placeholders. |

This is the migration inventory, not authorization to change those files now.
Profile tier routing, harness support, lifecycle safety and stage 7 remain
owned by their existing contracts; registry data must preserve their behavior.

## Pinned content import

[Personnel import](personnel.md#import-settings-and-authority) selects stable
`eng/role` IDs at a full producer commit and records settings provenance.
It permits presentation, routed engine selection and pinned additive skills;
it refuses authority replacement, missing roles and colliding selections.
This does not add registry layering or external role discovery.
