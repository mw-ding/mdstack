# Runtime options

Configuration module for the profile's runtime keys and the coordinator
option shared by every runtime, split out of the
[profile reference](../profile.md) under the M26 modular organization
principle ([#676](https://github.com/mw-ding/mdstack/issues/676)). It holds
the `[runtime]` key table and the shared `max_active_milestones` option with
its priority and default behavior, the
[`tmux` options](#tmux-options) with the standing and render-time notes,
the [`session` options](#session-options), the
[per-role runtime](#per-role-runtime) and the `tmux`
[launch topology](#launch-topology).
`control_item`, which `instance` is required with, stays in the profile's
[`[repo]`](../profile.md#repo) table.

## `[runtime]`

| Key | Type | Default | Replaces |
|---|---|---|---|
| `name` | string: `grok-bot`, `tmux` or `session` ([runtimes](../runtimes/README.md)) | *required* | none (was implicit: Grok Bot) |
| `options` | table, keys per runtime below | `{}` | none |
| `timezone` | string (IANA name) | none | `<timezone>` |
| `instance` | string: `[a-z0-9-]`, 1–63 characters | none; required with `control_item` | owner-chosen instance label, never a host name or path |

Every runtime accepts this coordinator option:

| Option | Type | Default | Replaces |
|---|---|---|---|
| `max_active_milestones` | integer, at least 1 | `1` | `<max-active-milestones>`: dispatch new builds from at most N open milestones, in milestone order |

The earliest active milestone keeps priority. A later milestone only fills
builder capacity the earlier one cannot use because its remaining items are
blocked by dependencies or already in flight. In-flight PRs in any milestone
still finish. The default preserves dispatch from one milestone at a time.

## `tmux` options

`tmux` also accepts ([binding](../runtimes/tmux.md)). Present limits provide
owner-friendly parallelism; an active recorded non-quiet away entry uses the
full caps. Switching takes effect on the next lead wake without restarting
sessions; running workers drain naturally when the cap drops:

| Option | Type | Default | Replaces |
|---|---|---|---|
| `session` | string | `crew-<owner>-<repo>` | the session name in [Layout and naming](../runtimes/tmux.md#layout-and-naming) |
| `session_backend` | string: `tmux` or `herdr` | `"tmux"` | The local [session adapter](../runtimes/session-backends.md). `runtime.name` stays `tmux`; herdr uses the existing local default server, with one labelled workspace per run |
| `tmux_server` | string: `default` or `dedicated` | `"default"` | The tmux server every crew call uses ([mdstack up](../runtimes/tmux.md#mdstack-up), #1327). `default`: the owner's default server, so plain `tmux ls` and `tmux attach -t <session>` find the crew, but a stray `tmux kill-server` from a pane also takes down the owner's own sessions. `dedicated`: the crew's own `tmux -L <session>` server (#818), out of reach of a pane's bare `tmux`; attach with `tmux -L <session> attach -t <session>`. The tmux session backend only |
| `builders` | integer | `5` | builder band cap ([Q6](../runtimes/tmux.md#q6-concurrency)) |
| `reviewers` | integer | `2` | reviewer pass cap ([Q6](../runtimes/tmux.md#q6-concurrency)) |
| `researchers` | nonnegative integer | `2` | researcher session cap ([roles.md Researcher](../roles.md#researcher-riley)); 2 so a [triage sweep](../triage.md#host) never blocks a deep dive. `0` runs no researcher: the render writes no researcher brief and needs none of its operations, and `triage.enabled = true` is refused |
| `present_builders` | integer, at least 1 | resolved `builders` | owner-present admission limit, bounded by `builders` |
| `present_reviewers` | integer, at least 1 | resolved `reviewers` | owner-present admission limit, bounded by `reviewers` |
| `idle_builder_ttl` | nonnegative integer | `1800` | Seconds idle before reclaiming a clean/pushed builder without queue pressure; `0` disables expiry. Output and step summaries are retained |
| `max_suites` | integer, at least 1 | none (no gate) | optional observed local suite gate for both leads: at or above it, or with suites unobserved, defer expansion. Unset, admission is caps only. An empty reviewer pool may admit one worker at a reached gate |
| `max_load` | positive number | none (no gate) | optional gate for both leads on the one-minute load average (not per CPU): at or above it, or with load unobserved, defer expansion. Unset, load never defers admission. An empty reviewer pool may admit one worker at a reached gate |
| `load_high` | positive number, above `load_low` | `6.0` | Scheduler [target](../scheduling.md#target): normalized one-minute load (per CPU) at or above which load is high and the target shrinks |
| `load_low` | positive number, below `load_high` | `4.0` | Scheduler [target](../scheduling.md#target): normalized load below which load is low; between the two the target holds |
| `memory_high` | string: `warn` or `critical` | none (by speed mode) | Scheduler [memory threshold](../scheduling.md#memory-threshold): the memory pressure at which memory is high (Linux `some avg10` 10.0 or 40.0). Unset, `critical` at full speed and `warn` in light mode |
| `error_high` | integer, at least 1 | `3` | Scheduler [target](../scheduling.md#target): gateway errors in the last 10 minutes at which errors are high; low means none |
| `schedule_interval` | integer, at least 1 | `120` | Seconds: the scheduler target changes at most once per interval, and the ramp limit counts starts per interval |
| `schedule_ramp` | integer, at least 1 | `2` | Scheduler ramp limit: crew-wide starts allowed per `schedule_interval` |
| `stuck_after` | integer, at least 1 | `1800` | Seconds finishing work (scheduler classes 1–6) stays deferred before one `schedule-stuck` coordinator wake ([observability](../scheduling.md#observability)) |
| `slack_webhook_env` | string: environment variable name | none; required with Slack | Incoming webhook secret read only from the environment; a missing variable refuses `mdstack up` |
| `slack_digest_interval` | positive integer | `3600` | Seconds without urgent progress before an away digest |
| `poll_interval` | integer | `60` | seconds between `mdstack poll` runs, and the default `mdstack watch --source-interval` ([mdstack poll](../runtimes/tmux.md#mdstack-poll), #1300) |
| `host_scan_interval` | integer, at least 1 | `15` | Seconds between the watcher's `pull` calls to each role host with runs ([remote wakes](../runtimes/multi-device.md#remote-wakes-and-messages), #346) |
| `land_poll_interval` | integer, at least 1 | `60` | Seconds between `change.land-status` reads after an [asynchronous land](../interfaces.md#synthesizer-loop) request; read only under `land.mode = "async"` once its slices land (#873) |
| `land_timeout` | integer, at least `land_poll_interval` | `3600` | Seconds an asynchronous land may stay unfinished before the synthesizer reports `blocked:`; the intent is kept ([synthesizer loop](../interfaces.md#synthesizer-loop)) |
| `lone_pr_land` | string: `train` or `direct` | `"train"` | `<lone-pr-land>`: `train` retains the tested-with-default-branch gate and batching rules; `direct` lands exactly one ready PR immediately without update-branch or a one-member train, records the gate waiver and checks default-branch CI for its merge commit; two or more ready PRs train ([land rules](../protocol.md#land-rules-and-merge-trains)) |
| `train_min` | integer, at least 2 | `2` | `<train-min>`: train ready PRs at once at this threshold; below it, wait only if another PR is close to approval, otherwise land alone ([land rules](../protocol.md#land-rules-and-merge-trains)) |
| `train_window` | integer, at least 1 | `600` | `<train-window>`: maximum wait in seconds after the first PR becomes ready when another is close to approval; at expiry train two or more ready PRs, or land the single ready PR alone |
| `merge_grant` | string | `"none"` | `<merge-grant>` renders a bounded live-resolved profile lookup instead of quoting this grant/history; the value remains the owner's standing merge grant scope, with its source (e.g. `#110 roadmap PRs per #111`); `none` means a recorded owner merge-ok per PR. It gives permission only ([§7](../protocol.md#7-merge-gate-synthesizer)). [`merge_grant_scope`](#merge_grant_scope) can extend it to spec changes |
| `release_delegation` | string | `"none"` | `<release-delegation>`: the owner's recorded standing go for release cuts, with a `https://` link to the record (e.g. `"make releases https://github.com/<owner>/<repo>/issues/<n>#issuecomment-<id>"`); `none` keeps a per-cut owner merge-ok. Set only by an owner account (a pack is refused). With it set, the coordinator's `cmd-id=release-delegation` merge-ok at a cut PR's head stands in for the owner's; never for a `crew:sensitive` cut, and never a CI, validation, actor or hold waiver ([release delegation](../release.md#release-delegation)) |
| `train_local_checks` | boolean | `false` | Opt in to the local full suite before opening the train PR; `--local` also enables it. Default builds record `local=skipped`. A local pre-check is a future CI-velocity option, not a merge gate; green train CI is still required |
| `mirror_deferral` | string | `"none"` | `<mirror-deferral>`: source and scope of a recorded owner standing mirror deferral (e.g. `#110 roadmap PRs per #140`). The synthesizer checks coverage, excludes live Grok Bot behaviour changes and records use in the merge post; this gives no merge permission ([§7](../protocol.md#7-merge-gate-synthesizer)) |
| `mirror` | string: `live-copy` or `none` | `"live-copy"` | `none` declares this install has no live copy outside the render `mdstack up` deploys, so the mirror gate resolves to `n/a` and the merge record says `Mirror: n/a (profile)`. Refused with a `mirror_deferral` other than `"none"`; Grok Bot refuses the key. Supplies no approval or merge permission ([No live copy to mirror](../runtimes/tmux.md#no-live-copy-to-mirror-877), [§7](../protocol.md#7-merge-gate-synthesizer)) |
| `hold_label_blocks` | boolean | `true` | Deprecated and ignored (#1124): `crew:hold` always stops the tmux builder, reviewer and synthesizer dispatch, as `crew:escalated` and a coordinator hold-until do. The #111 lane-label meaning (`false`) is retired; the key is still accepted and renders as `<hold-label-blocks>` |
| `permission_mode` | string: `bypass`, `auto` or `safe` | `"bypass"` | none: the role windows' permission flags ([mdstack spawn](../runtimes/tmux.md#mdstack-spawn), #293). `bypass` lets agents run any command in their worktree without asking; `auto` and `safe` keep the harness's approval checks, which can stop a window on a prompt |
| `confinement` | string: `enforce` or `off` | `"off"` | none: builder confinement ([Confinement](../runtimes/tmux.md#confinement), #1252). `enforce` refuses a builder launch that cannot confine the run to its own copy, before any claim or window; `off` launches it and marks the run unconfined in its record and `mdstack doctor` |
| `sandbox_env` | string: `NAME=VALUE` | `""` | none: sandbox variable passed to every window by `mdstack up`, `mdstack spawn` and `mdstack restart`; `CREW_SANDBOX_ENV` in the launching environment overrides it. Windows also receive `CREW_SANDBOX_ENV` so subsequent launches keep the setting |
| `notes` | table: role name → list of file paths | `{}` | Standing runtime notes appended at launch, in list order, under headings naming each file. Roles: `coordinator`, `builder`, `reviewer`, `synthesizer`; relative paths resolve from `<state-dir>/<owner>__<repo>`, absolute paths are used as given. Missing or unreadable files fail closed ([mdstack spawn](../runtimes/tmux.md#mdstack-spawn)). The `render` subtable holds render-time notes for any role, leads included (below) |
| `launch` | table: `coordinator`, `roles`, `resume`, `reconcile`, `cwd` | none (today's topology) | The `mdstack up` launch topology; see [Launch topology](#launch-topology) ([mdstack up](../runtimes/tmux.md#mdstack-up)) |
| `role_runtime` | table: role name → runtime name | none | Render that role's brief from another runtime's templates; see [Per-role runtime](#per-role-runtime) |

Configure standing policy once; each launch reads the current file contents.
Omitted roles and empty lists append nothing.
Render-time notes go in the `render` subtable: `notes.render.<role>`, for any
role in the registry plus `builder-lead` and `reviewer-lead`, lists files
appended verbatim to that role's rendered brief under `## Render note: <path>`.
Relative paths resolve from the project file. They are part of the render,
so they count toward [`size_budget`](../profile.md#size_budget) and
`check-skill-drift.py --project` covers them. A missing file fails the
render, and so does a note for a role the selected runtime renders no brief
for (such as `builder-lead` under `session`), naming the key and the runtime. Launch-time notes are unchanged. `mdstack spawn` handles worker
notes; `mdstack up` handles coordinator notes. The note text is included verbatim,
without placeholder substitution. For example:

```toml
[runtime.options.notes]
builder = ["policies/local-tools.md", "policies/merge-up-tests.md"]
reviewer = ["policies/recheck.md"]
synthesizer = ["policies/landing.md"]

[runtime.options.notes.render]
builder-lead = ["policies/lead-routing.md"]
```

A pack's `render/` directory overlays the render inputs per file, and its
backend map may declare extra run-time placeholders with
`[placeholders] kept = [...]` ([packs](../packs.md#render-overlay)).

## `session` options

`session` also accepts ([binding](../runtimes/session.md), #914). The
coordinator brief renders the pool limits and backend; the synthesizer
brief renders the land options as for `tmux`:

| Option | Type | Default | Replaces |
|---|---|---|---|
| `session_backend` | string: `native`, `cli` or `hosted` | `"native"` | `<session-backend>`: `native` dispatches workers as harness subagents with task handles; `cli` as external harness CLI runs with a recorded PID and start time; `hosted` as hosted sessions created through a control plane, addressed by the returned session id and probed by a control-plane state read (#1052) |
| `isolation` | string: `worktree` or `assigned-checkout` | `"worktree"` | the coordinator brief's worker isolation sentence: `worktree` gives each worker and probe its own `<worktree-root>/<n>-<sha7>-<role>-<pass>/` worktree; `assigned-checkout` says each runs in its pre-provisioned dedicated checkout and creates no worktree, for a venue whose workers run in checkouts on other hosts. The [C6 checks](../runtimes/session.md#runtime-contract) are unchanged (#1959) |
| `builders` | integer | `5` | `<builder-cap>`: concurrent builder runs |
| `reviewers` | integer | `2` | `<reviewer-cap>`: concurrent reviewer passes |
| `present_builders` | integer, at least 1, at most `builders` | resolved `builders` | `<present-builder-cap>`: owner-present builder limit, as in `tmux`; a value above `builders` is refused (#1053) |
| `present_reviewers` | integer, at least 1, at most `reviewers` | resolved `reviewers` | `<present-reviewer-cap>`: owner-present reviewer limit, as in `tmux`; a value above `reviewers` is refused |
| `researchers` | nonnegative integer | `0` | nothing rendered: concurrent [triage sweep](../runtimes/session.md#triage-sweep-routine) runs, the binding's only researcher pass (#1404). Opt-in (#1724): unset or `0` writes no researcher brief, and `triage.enabled = true` is refused; a positive cap writes the sweep brief |
| `merge_grant`, `merge_grant_scope`, `lone_pr_land`, `train_min`, `train_window`, `train_local_checks`, `mirror_deferral`, `mirror`, `hold_label_blocks` | as in [`tmux` options](#tmux-options) | as in `tmux` | the same placeholders in the session builder, reviewer and synthesizer briefs; session lands have no merge train, so the `train_*` options have no effect ([binding](../runtimes/session.md#selector-options-and-briefs)) |
| `land_poll_interval`, `land_timeout` | as in [`tmux` options](#tmux-options) | as in `tmux` | none: the poll interval and bound `mdstack land request` and `resume` use for an [asynchronous land](../interfaces.md#synthesizer-loop) under `land.mode = "async"` (#1351) |
| `release_delegation` | as in [`tmux` options](#tmux-options) | `"none"` | `<release-delegation>` in the session coordinator brief, as in the `tmux` one (#1542); set only by an owner account, a pack is refused ([release delegation](../release.md#release-delegation)) |
| `notes` | table | `{}` | its `render` subtable holds render-time notes, as for `tmux`; `mdstack up` appends the `coordinator` list to the coordinator brief (#1548); no launcher reads worker notes |
| `session` | string | `crew-<owner>-<repo>` | none: the tmux session `mdstack up` opens for the coordinator (#1548) |
| `permission_mode` | as in [`tmux` options](#tmux-options) | `"bypass"` | none: the coordinator harness flags `mdstack up` launches with |
| `launch` | table: `coordinator`, `resume`, `cwd` | none | `coordinator`, `resume` and `cwd` as in [Launch topology](#launch-topology); `roles` has no effect, since `mdstack up` never opens role windows on `session` and workers stay dispatched per pass |
| `role_runtime` | table | none | as in `tmux`; see [Per-role runtime](#per-role-runtime) |

## Per-role runtime

`role_runtime` lets a crew adopt another runtime one role at a time (#1055).
Each key is a registry role and each value a runtime other than
`runtime.name`. The render drops the role's template for the selected
runtime (its registry `templates` entry) and renders
`templates/runtimes/<runtime>/<role>.md` to `runtime/<role>.md` in its place,
with the profile's values and the usual placeholder checks. Every other brief
renders unchanged, and a profile without the key, or with an empty table,
renders byte-identically. A value equal to `runtime.name` or an unknown role is
refused, as is `researcher = "session"`, since the session researcher brief
runs only the triage sweep (#1404); a role with no template for the selected runtime, or a runtime
with no `<role>.md`, fails the render. A role with a cap of 0 renders nothing,
as before. Only the render changes: the launcher, poller and worker dispatch
follow `runtime.name`, so the swapped brief must suit the runtime that starts
it. For example, a `tmux` crew piloting the session coordinator:

```toml
[runtime]
name = "tmux"
options = { role_runtime = { coordinator = "session" } }
```

## `merge_grant_scope`

In effect (#398). `validate` checks this key and the
[`[spec]` paths](../profile.md#spec); `mdstack train check` and `mdstack train land`
read both, and the synthesizer brief renders them as `<merge-grant-scope>`
and `<spec-paths>`. The rule is
[§7 spec change](../protocol.md#spec-change-definition-and-spec-grant-scope).

| Option | Type | Default | Replaces |
|---|---|---|---|
| `merge_grant_scope` | list of strings: `approved`, `spec` | `["approved"]` | none: what the standing `merge_grant` covers. `spec` extends it to spec changes (`crew:spec` or a [spec-glob](../profile.md#spec) path) only when the recorded owner decision that `merge_grant` names authorizes it; refused with `merge_grant = "none"`. Unknown values and `[]` are refused too |

```toml
[runtime.options]
merge_grant = "all approved changes per #110"
merge_grant_scope = ["approved", "spec"]
```

With the key absent, the grant covers what it covers today. The scope never
covers sensitive, gate-contract or release-approval changes, `unverified`
evidence or an open rereview.

## Launch topology

`[runtime.options.launch]` makes the launch topology a profile setting
(#606). With the table absent, `mdstack up` behaves as before: a tmux
coordinator, tmux lead windows and a fresh coordinator conversation.

| Key | Values | Default | Meaning |
|---|---|---|---|
| `coordinator` | `tmux` or `none` | `"tmux"` | `none`: `mdstack up` runs its preflight (profile, Slack variable, Codex hook trust, render, coordinator notes) and starts no session |
| `roles` | `tmux`, `hosted` or `none` | `"tmux"` | `tmux` starts the pool lead windows as today. `hosted`: the coordinator dispatches role passes as hosted sessions on remote worker hosts, so `mdstack up` opens no role windows. `none` starts no role windows (`mdstack up --coordinator-only` does the same for one run). `tmux` needs `coordinator = "tmux"` |
| `resume` | `fresh`, `ask` or a session id (`[A-Za-z0-9._:-]`, up to 128 characters) | `"fresh"` | The coordinator's harness conversation. A session id resumes it with the brief pointer; `ask` opens the harness's resume picker, without the pointer. `mdstack up --resume <id>` overrides it for one run (#1548). Claude Code and Codex only; another coordinator engine refuses `mdstack up` before any write |
| `cwd` | directory path | the profile's directory | The coordinator's working directory (window 0), for `mdstack up`, `mdstack restart` and an upgrade reload; relative to the profile's directory, `~` expanded. `mdstack up` refuses a path that is not a directory (#1957) |
| `reconcile` | `backend` | `"backend"` | Reconciliation reads go through the configured backends' read operations, never a hard-coded GitHub call ([reconcile binding](../runtimes/tmux.md#launch-topology)) |

The window name, `CREW_ROLE`, `CREW_PROJECT`, `CREW_STATE` and the other
tags are the same in every topology. They are exported by window 0's own
command, never set on the tmux session, so a window the owner opens in the
crew session carries no `CREW_*` (#1957). The launch line derives
`GH_TOKEN` only when a backend is bound to `github`. For example, a local resumable
coordinator with hosted role sessions on a pack backend:

```toml
[runtime.options.launch]
coordinator = "tmux"
roles = "hosted"
resume = "ask"
reconcile = "backend"
```
