# Crew flavors (design)

> - **Status:** built
> - **Applies to:** both runtimes' rendered briefs; `crew-config.py`, `item-flavor.py`, `flavor-suggest.py`
> - **Current rules:** [change flavor](protocol.md#change-flavor), [gate registry](protocol.md#gate-registry)
> - **Built:** 18.2–18.8 (#195–#199, #102, #109) and follow-ups A–E (#350–#354) in [Build issues](#build-issues); the optional item `tier=` field in M55 (#1830, PR #1868). The intro's "remains follow-up B" predates #351
> - **Design only:** none found
> - **Last checked:** 2026-11-04 at `217cec5`

Named, per-project rigor presets in the profile, a floor that no flavor
crosses, and a metrics feedback loop that suggests when a project's flavor
should change (roadmap 18.1,
[#156](https://github.com/mw-ding/eng-crew/issues/156); umbrella
[#110](https://github.com/mw-ding/eng-crew/issues/110)). Owner decisions:
[#160 row 15](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532247500)
(rigor presets), [row 8](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531125583)
(pre-review check) and
[row 9](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531795606)
(`crew:sensitive`). This page reflects them; it does not re-decide them.

The schema and path matcher are built. The protocol now defines the core
review, validation, evidence, caps and merge modes and the optional verdict
field ([change flavor](protocol.md#change-flavor)); runtime rendering of
project values remains follow-up B. Other proposed controls land through
the [build issues](#build-issues). A change
to what satisfies a gate lands under the
[gate contract](protocol.md#gate-contract), with the owner's merge-ok. Until
then the [protocol](protocol.md) applies as written.

## Decisions

| Question | Choice | Alternatives considered |
|---|---|---|
| Unit | A named flavor per project, built from [knobs](#knobs). Presets are `thorough`, `standard`, `fast` and `solo`; a custom flavor sets knobs on top of a preset | One rigor level for every project: the problem this solves. A project mode plus an autonomy flag (firstmate): two switches cannot set review, validation, evidence and caps separately |
| Core or binding (#156 Q1) | Rigor knobs are core: each picks how a §3, §5 or §7 rule is met. `lighter_lane`, `parallelism` and `builder` are runtime knobs. `merge` also needs the backend to record a standing grant on the tracker ([single identity](interfaces.md#single-identity-profile)) | All core: the lighter lane exists only because of Grok Bot's per-PR watch limits. All binding: the same project would get different rigor on different runtimes |
| When rigor is decided | The project flavor at install or intake: bootstrap proposes it, the owner confirms, the profile records it ([#191](https://github.com/mw-ding/eng-crew/issues/191), 17.3). The item flavor at triage, recorded on the item | Each role decides on wake: roles guess and disagree. Profile only: no way to lower one item |
| Lowering | An item flavor below its default needs a `Reason:` line in its record. A record that lowers without one is refused, and the default applies | Free lowering: rigor erodes silently. Owner-only lowering: routine items stall, though class rules already cover most of them |
| No setting | No project flavor means `standard`. `resolve`, `mdstack doctor` ([#190](https://github.com/mw-ding/eng-crew/issues/190)) and one note on the tracking issue flag the gap. An item with no record is `thorough`, and roles tell the coordinator | The project flavor for an unrecorded item: it rewards skipping triage |
| Granularity (#156 Q2) | The project flavor plus a deterministic path-based [class rule](#class-rule). An owner override is an item record with the owner's words as its reason. Uncertain means stricter | Per project only: docs and scripts get the same rigor. Class labels applied by hand: judgment at merge time, but the synthesizer only reads |
| Combining flavors | Knob-wise strictest: for each rigor knob, the stricter value wins | A total order of presets: custom flavors have no place in it, and a mixed change would lose a strict value |
| Record (#156 Q3) | Item: a coordinator-signed post on the item with a `pass=flavor` marker. Project: the profile diff, by PR, or, for an untracked profile, posted on the tracking issue before it applies | A `flavor:<name>` label: unsigned, carries no reason, and a label change records neither who nor why. Chat: not the tool of record (invariant I5) |
| Default for new projects (#156 Q5) | Bootstrap proposes `standard`; the owner confirms or edits it. An unset flavor is also `standard`, flagged ([#632](https://github.com/mw-ding/eng-crew/issues/632)). `thorough` stays the preset for releases, security and gate-contract work, raised by [class rules](#class-rule) and item records | Proposing `thorough`, or `thorough` when unset: safe but heavy. Unset all of 2026-11-02, validation caught a problem after a passing review in 2 of 217 rounds (0.9%), while every PR paid for the extra session ([lesson](lessons/2026-11-03-standard-default.md)) |
| Feedback loop | Metrics and owner feedback produce a [suggestion issue](#suggestion-issue). It is never auto-applied; the owner accepts or declines | Auto-apply: changes authority without the owner (out of scope in #156). Folding it into the [metrics gate](metrics/decisions.md): that gate is harness-wide and pauses work, while a flavor is per project and changes nothing until accepted |
| Cost levers | Tier and flavor config only (`engines`, `parallelism`, `caps`), never a router model that picks routes (#160 row 7; [#109](https://github.com/mw-ding/eng-crew/issues/109) guardrail) | Routing by quota headroom: deferred by #160 row 7 |
| Upgrade | `thorough` turns on the pre-review check, so the first release with flavors changes unset projects. That entry is `**Breaking:**` ([versioning](deliverables.md#versioning)); its migration step is an explicit `[builder.precheck].enabled = false`. The unset default moving to `standard` (#632) is also `**Breaking:**`: unset projects skip validation for non-behaviour changes. Its migration step is `[flavor] name = "thorough"` | `thorough` exactly as today: then the strictest preset has fewer checks than `standard` |

## Knobs

Values are listed strictest first. "Today" is the protocol as written.

| Knob | Key | Values | Binding | Today |
|---|---|---|---|---|
| Review depth | `review` | `full`: findings ranked per [§3](protocol.md#3-evidence-requirements). `thin`: red only for an AC, a §7 gate, CI or security (the [AGENTS.md](../AGENTS.md) posture). `light`: one light pass. `off`: no independent review, valid only in the item-only [`express`](#express) preset | core | `full` |
| Validation | `validation` | `always` · `behaviour` (behaviour-changing changes only) · `off` | core ([stage 6](protocol.md#2-stages), §7 approval) | `always` |
| Engine diversity | `diversity` | `required`: every waive needs the owner's per-change OK. `waivable`: the [quota diversity waive](roles.md#quota-diversity-waive) with its standing grant | core (I2) | `waivable` |
| Round cap / CI-fix cap | `caps` | `[3, 3]` · `[2, 2]` · `[1, 1]`; each entry 1–3 | core ([§5](protocol.md#5-rounds-and-escalation)) | `[3, 3]` |
| Evidence | `evidence` | `typed`: per shape, inline ([verification](verification.md)). `inline`: excerpts in the change body only ([#143](https://github.com/mw-ding/eng-crew/issues/143)) | core (§3, §7 required evidence) | `typed` |
| Merge permission | `merge` | `per-change` · `docs`: today's standing doc-only merge-ok · `auto`: any change once every §7 gate passes | core (§7 merge permission); backend: the grant is recorded on the tracker | `docs` |
| Pre-review check | `precheck` | `on` · `off`. Sets the default of `[builder.precheck].enabled` ([#181](https://github.com/mw-ding/eng-crew/issues/181), 16.2) | core (16.1–16.3) | not built |
| Validation scope | `validation_scope` | `repo`: the validator also runs the repo-wide lint and test commands. `bounded`: the item's ACs, the files changed at head, the configured test command for those paths, and green CI at head ([#648](https://github.com/mw-ding/eng-crew/issues/648); [cost](#validation-cost)) | core (stage 6) | `repo` |
| Lighter lane | `lighter_lane` | `off` · `docs` · `docs+tests` | runtime ([Grok Bot](runtimes/grok-bot.md#lighter-lane-routing)) | `docs` |
| Parallelism | `parallelism` | `{ builders = <n>, reviewers = <n> }`, 1 ≤ n ≤ the runtime cap | runtime | 5 / 5 ([roles](roles.md#parallelism)); tmux 5 / 2 |
| Engine routing | `engines` | Per-tier `order` and `effort` overrides, in the shape of `[engines]` ([profile](profile.md#keys)) | core ([tiers](roles.md#tiers)) | `[engines]` |
| Builder | `builder` | `crew` · `solo`: one owner-driven session builds and fixes ([#102](https://github.com/mw-ding/eng-crew/issues/102)) | runtime | `crew` |
| Self-gate engine | `selfgate_engine` | `different`: the self-gate review runs on another engine (I2 holds). `same`: the builder's own engine and model. Set once as `flavor.selfgate_engine`; only [`express`](#express) reads it | core | `different` |

- **Rigor knobs** are the first nine; `selfgate_engine` is read only for an express change and never combines. Only they combine knob-wise and count
  as lowering. `parallelism` and `engines` are resource knobs and come from
  the project flavor; `builder` comes from the item record.
- `merge` gives permission only. It never supplies the approval, never skips
  CI, and never covers a `crew:sensitive` ([F7](#floor)) or `crew:spec`
  change.
- Under `validation = behaviour` or `off`, the verdict's validation section
  says `skipped (flavor <name>)`. The section and marker must satisfy
  [protocol §3](protocol.md#change-flavor); §7 checks the live knobs.

## Presets

| Knob | `thorough` | `standard` | `fast` | `solo` | `express` |
|---|---|---|---|---|---|
| Use for | Product code, security, releases: every check on | Most work: thin review, validation for behaviour changes | Docs, prototypes, spikes | One owner-driven session builds | Item only: one builder builds, self-gates and lands on green CI |
| `review` | `full` | `thin` | `thin` | `thin` | `off` |
| `validation` | `always` | `behaviour` | `off` | `behaviour` | `off` |
| `diversity` | `waivable` | `waivable` | `waivable` | `waivable` | `waivable` |
| `caps` | `[3, 3]` | `[3, 3]` | `[2, 2]` | `[3, 3]` | `[3, 3]` |
| `evidence` | `typed` | `typed` | `inline` | `typed` | `typed` |
| `merge` | `docs` | `docs` | `auto` | `docs` | `auto` |
| `precheck` | `on` | `on` | `off` | `on` | `on` |
| `lighter_lane` | `docs` | `docs` | `docs+tests` | `docs` | `docs` |
| `validation_scope` | `repo` | `bounded` | `bounded` | `bounded` | `bounded` |
| `parallelism`, `engines` | project values | project values | project values | project values | project values |
| `builder` | `crew` | `crew` | `crew` | `solo` | `crew` |
| `selfgate_engine` | n/a | n/a | n/a | n/a | `flavor.selfgate_engine` (default `different`) |

`thorough` differs from today only in `precheck = on`, once M16 lands.
`solo` keeps the independent reviewer on an engine different from the
session's, the synthesizer and the floor. The owner picked options 1 + 3
for #102: the [lane and label](protocol.md#solo-coding-agent-lane) and a
[shared-source brief](roles.md#solo-session). `crew:solo` selects builder
routing now; selecting the preset alone supplies no item dispatch decision.

### Validation cost

A validation pass costs roughly what it reads and runs. Unbounded, a validator
explores the whole tree and runs repo-wide checks it often cannot run: one
small docs-only pass on a pack backend read millions of input tokens
([#648](https://github.com/mw-ding/eng-crew/issues/648)). `bounded` keeps
the pass proportional to the diff. Repo-wide coverage still comes from green
CI at head, a §7 gate under every flavor ([F1](#floor)). Set `repo` in a
custom flavor or class rule only for changes whose risk is repo-wide.

### Express

`express` is the [express lane](express-lane.md) preset ([#636](https://github.com/mw-ding/eng-crew/issues/636)).
It is an item flavor only: a coordinator item record names it (with a
`Reason:`, since it lowers) and the change carries `crew:express`. It is never
a project flavor, a class flavor or a custom `base`, so the validator rejects
`flavor.name`, `flavor.classes[].flavor` and `flavor.custom.<name>.base`
set to `express`. `caps[0]` counts self-gate reviews per head; `merge = auto`
grants nothing without a recorded owner grant covering express changes. The
self-gate, its record, gate and routing land through the express lane's
build issues; until then an express item runs the crew lane.

## Floor

No flavor, preset, class rule or item record may cross these. The
[#195](https://github.com/mw-ding/eng-crew/issues/195) validator rejects a
flavor that tries, with a message naming the item.

| # | Floor item | No flavor may | Enforced by | Source |
|---|---|---|---|---|
| F1 | CI never waived | Land with a required check red, pending or skipped | No knob touches CI; the CI-fix cap is at least 1 | [Gate contract](protocol.md#gate-contract) |
| F2 | No secrets | Carry a token-shaped value | The profile secret scan covers the flavor tables | Spec R1 |
| F3 | Only the synthesizer lands | Let another role or session land | No knob names a landing role; `builder = solo` never lands | I4 |
| F4 | Audit trail on the tool of record | Skip the flavor record, the verdict post, a waive record or the `merge` marker | `review = off` exists only in the item-only `express` preset; anywhere else it fails as F4. Express keeps every record but the verdict post ([scoped exceptions](#scoped-express-exceptions)) | I5 |
| F5 | The owner can always hold | Stop `crew:escalated` or a coordinator hold-until from stopping every role | No flavor knob touches holds | [§5](protocol.md#5-rounds-and-escalation), [§9](protocol.md#9-steering-crew-commands) |
| F6 | Gate-contract changes need the owner | Change what satisfies a gate, or change a project's flavor without the owner | Knob values pick only gate modes the protocol defines; gate-contract changes need the owner's authorization, either per-change or through a grant that explicitly names that scope ([gate-contract grant](protocol.md#change-flavor)); a flavor change lands by the owner's per-change merge-ok | [Gate contract](protocol.md#gate-contract) |
| F7 | `crew:sensitive` needs a per-change merge-ok | Let `merge` cover a `crew:sensitive` change | No standing grant applies; deterministic [sensitive classification](protocol.md#sensitive-class) sets the label, only a recorded owner override clears it | #160 rows 9, 15; [#184](https://github.com/mw-ding/eng-crew/issues/184) |

The rest of [portable spec §3](specs/portable.md#3-invariants) binds every
flavor too, as part of a profile: I1 (author ≠ reviewer, or the
single-identity rule), I2 (so `diversity` has no `off`) and I3 (evidence on
the change head). So do the protocol's hard rules: caps of at most 3, a
serial land, and a per-change merge-ok for `crew:spec` changes. In mdstack
itself, the gate-defining paths (`docs/protocol.md`, `docs/runtimes/*.md`,
`docs/verification.md`, `docs/flavors.md`, `core/crew-config.py`) become
`crew:sensitive` path rules in its own profile (a scope note for #184). That
way F6 holds at merge time through F7.

### Scoped express exceptions

Only for a change whose effective flavor is `express` by
[express resolution](#class-rule). Every other change keeps the floor above.

| Item | Express change | How the intent holds |
|---|---|---|
| F4 | Relaxed: no reviewer verdict post | The flavor record, the builder's selfgate record at head and the `merge` marker stay on the change |
| I1 | Relaxed | The builder identity posts the selfgate record about its own change |
| I2 | Kept under `selfgate_engine = different`; relaxed under `same` | The selfgate record names both engines |
| F1–F3, F5–F7, I3–I5 | Kept | `crew:sensitive` and `crew:spec` items are ineligible unless the owner overrides per item |

## Profile schema

Schema validation is implemented by
[#195](https://github.com/mw-ding/eng-crew/issues/195) (18.2). Path class matching
is implemented by #197 (18.4), on top of
the [profile](profile.md) (#122) and its [layers](profile.md#layers-and-precedence) (#123).

```toml
[flavor]
name = "standard"      # a preset or a flavor.custom name; unset: standard, flagged
goal = "quality"       # quality | speed | cost; read only by the feedback loop

[flavor.custom.docs-site]
base = "fast"          # a preset; no chains
merge = "docs"

[[flavor.classes]]
paths = ["docs/**", "*.md"]
flavor = "fast"
reason = "docs only; markdownlint and the link check run in CI"

[[flavor.classes]]
paths = ["src/auth/**", "migrations/**"]
flavor = "thorough"
```

| Key | Type | Default |
|---|---|---|
| `flavor.name` | string: a preset or a `flavor.custom` name | none: `standard`, flagged |
| `flavor.goal` | string: `quality`, `speed` or `cost` | `quality` |
| `flavor.selfgate_engine` | string: `different` or `same`; read only for express changes | `different` |
| `flavor.custom.<name>.base` | string: a preset | *required* |
| `flavor.custom.<name>.<knob>` | per [Knobs](#knobs) | the base's value |
| `flavor.classes[].paths` | list of globs, non-empty | *required* |
| `flavor.classes[].flavor` | string: a preset or a `flavor.custom` name | *required* |
| `flavor.classes[].reason` | string | none; *required* when the class is below `flavor.name` on any rigor knob |

Validator rules, each with a test:

1. Closed tables and enums per [Knobs](#knobs): an unknown key or value
   fails.
2. Names resolve. A custom name never shadows a preset, and `base` is a
   preset.
3. Each `caps` entry is 1–3; each `parallelism` entry is at least 1 and at
   most the runtime cap; `engines` follows the `[engines]` rules and the
   [hard rules](roles.md#hard-rules).
4. A class below `flavor.name` without a `reason` fails.
5. A key or value that would cross F1–F7 fails as `floor F<k>: <item>`, even
   when it is also an unknown key, so the message names the floor.
6. `express` as `flavor.name`, a class flavor or a custom `base` fails:
   it is an item flavor only. `selfgate_engine` is valid only at
   `flavor.selfgate_engine`.

The schema accepts `thorough`, `standard`, `fast` and `solo`, plus `express`
for item records only.
Flavor controls named `ci`/`ci_waiver` (F1),
`land`/`landing_role` (F3), `audit`/`record` or `review = "off"` (F4),
`hold`/`hold_label_blocks` (F5), `gate_changes`/`flavor_changes` (F6), and
`sensitive_merge` (F7) are rejected with floor diagnostics. Secrets anywhere
in flavor tables fail F2. Every other unknown control also fails the closed
schema. Runtime rendering, including precheck defaults and replacing the legacy
merge grant, remains follow-up B; selecting a flavor supplies no new merge
authority. Protocol §3 preserves existing recorded owner grants within their
scope regardless of the merge knob until follow-up B migrates them;
sensitive/spec changes still need per-change merge-ok, and gate-contract
changes do unless an owner grant explicitly names that scope.

Layers: `flavor` and `flavor.custom.*` merge by key; a higher layer replaces
`flavor.classes` whole. `resolve` prints the gap as
`flavor.name = "standard"  # core (unset: flagged)`.

## Resolution

| Level | When | Who | Result |
|---|---|---|---|
| Project | Install or intake (17.3) | The owner confirms the bootstrap proposal | `flavor` in the profile; unset means `standard`, flagged |
| Item | Triage window ([§6](protocol.md#6-duties-on-wake-all-roles)) | Coordinator | The item record below. Its default is the class flavor of the paths the item names, or the project flavor when it names none |
| Change | Every builder, reviewer and synthesizer wake, at head | Each role, by program, not by judgment | Knob-wise strictest of the item flavor and the class flavor of the change's paths at head (`change.read-diff-paths`); F7 then applies |

Item record (18.3), posted on the item:

```text
<CoordinatorEmoji> <CoordinatorBot> · Flavor · #<n>: <flavor> (default <default>)
Reason: <one line; required when <flavor> is below <default> on any rigor knob>
<!-- crew:v1 role=coordinator pass=flavor issue=<n> flavor=<flavor> default=<default> -->
```

- The newest record wins. Roles re-read it on every wake (§6 step 1), so a
  later record that tightens applies at once.
- A record that lowers without a `Reason:` is refused: roles use the
  default and tell the coordinator. The `Reason:` line is read with the
  marker, the record's only parsed line besides it.
- No record: `thorough`, and roles tell the coordinator (`flavor-missing`).
- An optional `tier=<tier>` field allocates the item's execution tier
  ([roles](roles.md#tiers)). It is read apart from the flavor and changes no
  rigor knob or gate.
- The owner may set any item flavor; the coordinator records the owner's
  words as the reason. Builders and reviewers never lower a flavor; they ask
  the coordinator.
- No unrecorded floor (#745). Effective rigor is only what this resolution
  yields. The coordinator never hand-writes an extra rigor floor into a
  dispatch brief (for example "validation always", "full local suite" or
  "screenshots required" on a `standard` item). To raise rigor it first posts
  a newer item record whose `Reason:` line says why, so the raise is visible
  on the item. Path tightening by a [class rule](#class-rule) or the
  sensitive class stays effective without a record. A worker that finds an
  unrecorded floor in its brief applies the resolved knobs and reports
  `flavor-unrecorded` to the coordinator. For example: a `standard` item
  with no raise runs `standard`; a record `thorough` with
  `Reason: release cut` runs `thorough`; a `standard` item whose diff touches
  a `thorough` class path runs `thorough` with no record.

### Class rule

`python3 core/crew-config.py class-flavor --project config.toml` reads
newline-separated repo-relative paths on stdin and prints JSON with the
project name, combined `rigor` knobs and `matches` (zero-based class rule
indexes per path). `--org-profile` uses the same layers as `resolve`;
the project replaces the org's whole class list. Include both old and new
rename paths. Invalid profiles or noncanonical paths fail with exit 1 and
no result; never use a partial match to relax rigor.

- Globs use the dialect of `scripts/deliverables.txt`: `**` crosses `/`,
  while `*` and `?` stay inside one path segment.
- A path that matches several classes gets the strictest of them. A path
  that matches none gets the project flavor. A change's class flavor is the
  strictest over all its paths.
- A change that touches paths beyond its item's class is raised, never
  lowered, because the change flavor is the strictest of the item and its
  paths.
- `crew:sensitive` path rules (#184) are separate. They only add F7.
- **Express resolution.** `--express` means the newest item record names
  `express` and the change carries `crew:express`. The express knobs then
  apply, with `selfgate_engine` from the profile, unless a path matches a
  class stricter than the project flavor on any rigor knob or cap. Output
  adds `lane` (`express` or `crew`) and `tightening` (those class indexes);
  any tightening match resolves the normal way, and the change runs the
  crew lane.
- With no paths, the matcher returns the project rigor; an unset project
  flavor is `standard`. Enum knobs combine by their documented strictness
  order, and each cap takes the maximum. Resources and the item `builder`
  knob are excluded. A combined result may have no preset name.
- Recommended: because the unset default is `standard`, declare a
  `thorough` class for the paths that define your gates, such as the
  protocol, flavor and profile docs, the config validator and the CI
  workflows. Releases and security work get `thorough` through their item
  record. For mdstack:

  ```toml
  [[flavor.classes]]
  paths = ["docs/protocol.md", "docs/flavors.md", "docs/profile.md", "core/crew-config.py", ".github/workflows/**"]
  flavor = "thorough"
  ```

- Owner overrides still require the coordinator's item record above with
  the owner's words and reason. The matcher supplies no override flag or
  merge permission. Item-record parsing and role/gate application remain
  the separate build issues below; roles must combine item and path rigor
  before applying a flavor.

## Existing knobs

| Existing knob | Where today | Becomes | Note |
|---|---|---|---|
| Lighter lane | [§6](protocol.md#6-duties-on-wake-all-roles), Grok Bot binding | `lighter_lane` | Code, `.github/`, `templates/**` and `docs/protocol.md` never qualify; `docs+tests` adds test-only paths. The mirror hold stays path-derived |
| Standing doc-only merge-ok (2026-10-25) | §6, §7 | `merge = "docs"` | The owner's grant stays the record that the value cites |
| tmux `merge_grant` | `runtime.options` ([profile](profile.md#keys)) | `merge` | #195 replaces it, or checks that both agree, so there is one source |
| Thin review posture | mdstack [AGENTS.md](../AGENTS.md) | `review = "thin"` in mdstack's own profile | Product repos keep their own `AGENTS.md` for repo specifics |
| Quota diversity waive | [roles](roles.md#quota-diversity-waive) | `diversity` | Its trigger, preference, record and per-PR owner OK for HIGH risk stay in roles; `required` removes the coordinator's standing grant |
| Tiers | [roles](roles.md#tiers) | Stay separate | A tier measures difficulty, not rigor. `engines` may override a tier's order or effort; security and release infra work stays deep |
| Round cap, CI-fix cap | Protocol hard rules, [§5](protocol.md#5-rounds-and-escalation) | `caps` | 3 stays the maximum |
| Parallelism ceilings | [roles](roles.md#parallelism); tmux `builders`, `reviewers` | `parallelism` | Land stays serial (C7). `/crew away --cap` ([#199](https://github.com/mw-ding/eng-crew/issues/199)) lowers it while away; the lower value applies |
| Pre-review switch | `[builder.precheck]` (16.2) | `precheck` sets its default | Commands stay in `[builder.precheck]`; an explicit `enabled` wins |
| tmux `hold_label_blocks` | `runtime.options` | Stays separate | Deprecated and ignored (#1124): `crew:hold` always blocks; F5 also holds through `crew:escalated` and a coordinator hold-until |
| Owner-SLA auto-apply defaults | §6 | Stay separate | Owner-absence handling, not rigor; away mode ([#198](https://github.com/mw-ding/eng-crew/issues/198)) changes no authority |
| Metrics gate | [metrics decisions](metrics/decisions.md) | Stays separate | A harness-wide pause; it blocks relax suggestions while open |

## Feedback loop

### Inputs

| Input | Source on the tool of record | Status |
|---|---|---|
| Cycle time | `open_to_merge_min` | In `prs.csv` ([metrics](metrics/README.md)) |
| Rounds | `changes_verdicts`, `builder_fix_rounds`, `ci_fix_rounds` | In `prs.csv` |
| Rework | `reopened`, or changes verdicts at the cap (the [rework proxy](metrics/decisions.md#rework-proxy-and-its-limits)) | In `prs.csv` |
| Flavor per change | An optional `flavor=<effective>` field on the `pass=verdict` marker | New (follow-up A) |
| Escaped defects | A bug item or intake card with `Escaped from: <owner>/<repo>#<pr>`, which the coordinator adds at triage | New (follow-up C) |
| Quota spend | Engine runs per change: distinct `Engine:` trailers per round, plus the reviewer and validator runs named in verdict signatures. Quota-% figures stay local to the runtime. Since #1557 (owner direction, 2026-11-10) each pass-reporting role post carries an informational [usage line](roles.md#usage-line) with its tokens; it is still not an input | New (follow-up C) |
| Owner feedback | An [intake card](self-improve.md#triggers) with trigger `owner-feedback` and class `too-slow`, `too-costly` or `missed-bug` | New trigger (follow-up D) |

### Thresholds

Initial drafts, tunable like the [metrics gate](metrics/decisions.md#tuning).
Computed per project over changes merged under its current flavor; a change
raised by a class rule counts for that class instead.

| # | Signal | Window | Suggests |
|---|---|---|---|
| T1 | At least 2 escaped defects | Last 30 days | Tighten one step |
| T2 | One `missed-bug` owner card | None | Tighten one step |
| T3 | Rework rate above 20% | Last 20 merged changes, at least 5 | Tighten one step |
| R1 | 20 merged changes with no changes verdict and no escaped defect | Last 20 merged changes | Relax one step |
| R2 | A `too-slow` or `too-costly` owner card, with no escaped defect | Last 30 days | Relax one step |
| R3 | Goal `speed`: median cycle time more than 30% above the project's baseline. Goal `cost`: engine runs per change more than 30% above it. No escaped defect in 30 days | 14 + 14 days, as in the [sensors](metrics/decisions.md#sensors) | Relax one step |

- Any T signal blocks every R signal.
- No relax while a `metrics-gate` issue is open, or within 28 days of the
  last flavor change. A tighten can fire at any time.
- One step means `thorough` ↔ `standard` ↔ `fast` for a preset, and one
  value step on the knobs behind the signal for a custom flavor. `solo`
  steps like `standard` and keeps `builder = solo`.
- `goal` only enables R3; a `quality` project relaxes on R1 and R2 only.
- A suggestion never crosses the floor, and never touches F7 or `crew:spec`.

### Suggestion issue

Title `flavor: <tighten|relax> <owner>/<repo> <from> → <to> (<as-of>)`, with
the plain label `flavor-suggestion` (not a `crew:*` state tag). It is filed in
the control-plane repo, like the metrics gate. At most one is open per
project and scope; a later signal comments on it.

```markdown
## Signal

<T1–T3 or R1–R3> as of <date> (UTC). Scope: project | class `<paths>`. Goal: <goal>.

## Evidence

| Change | Flavor | Changes verdicts | Escaped defects | Cycle time (min) | Engine runs |
|---|---|---|---|---|---|
| <owner>/<repo>#<n> | <flavor> | <k> | <link or 0> | <m> | <r> |

## Proposed change

<from> → <to>. Knobs: <knob> <old> → <new>, ...

~~~toml
[flavor]
name = "<to>"
~~~

Validator: `crew-config.py validate` → <output>.

## Decision

Owner: `accept flavor: <to>` or `decline flavor: <reason>`.
Default if unanswered: keep <from>. A flavor change is never applied by default.
```

### Owner accept path

1. The coordinator files the suggestion, or comments on the open one.
2. The owner answers on the issue, or in chat, which the coordinator records
   verbatim on the issue. The [§6](protocol.md#6-duties-on-wake-all-roles)
   owner SLA applies, and its default is always to keep the current flavor.
   Away words may accept a tighten, never a relax: away mode never changes
   authority (#160 row 19).
3. On accept, the coordinator makes the profile change. For a tracked
   profile it opens a PR with the validator output inline; the PR needs the
   owner's per-change merge-ok, and no standing grant covers it (F6). For an
   untracked profile, the coordinator posts the diff on the issue and applies
   it after the owner's words.
4. Once applied, the coordinator closes the issue with the link. The new
   flavor applies to items triaged after it; after a tighten, the coordinator
   re-records open items that have not merged.
5. On decline, the issue closes as not planned, with the reason. The same
   signal is not filed again within 28 days unless the numbers get worse.

## Build issues

| ID | Issue | Builds | Depends on |
|---|---|---|---|
| 18.2 | [#195](https://github.com/mw-ding/eng-crew/issues/195) | [Profile schema](#profile-schema): presets, custom flavors, validator with a test per floor item, the `resolve` gap line | 18.1, 16.2, 16.5 |
| 18.3 | [#196](https://github.com/mw-ding/eng-crew/issues/196) | Project flavor at intake; item record, default, lowering and refusal; coordinator contract and triage template | 18.2, 17.3 |
| 18.4 | [#197](https://github.com/mw-ding/eng-crew/issues/197) | [Class rule](#class-rule) matcher, knob-wise strictest, change flavor at head | 18.2 |
| 18.5 | [#198](https://github.com/mw-ding/eng-crew/issues/198) | `/crew away`; it changes no flavor and accepts no relax | 16.7 |
| 18.6 | [#199](https://github.com/mw-ding/eng-crew/issues/199) | `/crew away --cap` lowers `parallelism` while away; `--quiet` | 18.5 |
| 18.7 | [#102](https://github.com/mw-ding/eng-crew/issues/102) | The `solo` preset: the `builder = solo` runtime path | 18.2 |
| 18.8 | [#109](https://github.com/mw-ding/eng-crew/issues/109) | The `cost` goal and its levers; its own ACs stay in #109 | 18.2 |

Proposed follow-ups, for the coordinator to file:

| ID | Builds | Depends on |
|---|---|---|
| A | Knobs in the protocol: §3, §5, §7 and gate-registry wording for `review`, `validation`, `evidence`, `caps` and `merge`; the optional `flavor=` verdict marker field; builder, reviewer and synthesizer templates read the change flavor. Gate contract, `crew:needs-mirror`, owner merge-ok; likely two PRs | 18.2, 18.4 |
| B | Renderer: the project flavor's values in the rendered briefs | A |
| C | Metrics: `flavor`, `escaped_defects` and `engine_runs` columns in `metrics-refresh.py`; the `Escaped from:` triage line | A |
| D | The `owner-feedback` intake trigger and its three classes | none |
| E | `flavor-suggest`: T1–T3, R1–R3 and the guards on the CSV, with offline tests; the suggestion issue template; the coordinator's triage duty | C, D |
