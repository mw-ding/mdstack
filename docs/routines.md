# Role routines

A routine is one of a role's recurring jobs, such as a triage sweep, a
docs pass or a daily brief. Each role package keeps its routines in a
`routines/` folder next to `role.toml`, `SKILL.md`, `skills/` and memory
(owner, 2026-11-07, [#1247](https://github.com/mw-ding/mdstack/issues/1247);
[team spec §4](specs/team.md#4-target-module-layout)). A routine says
what runs and when. Each environment decides how to run it with its own
scheduler.

## Files

`roles/<team>/<role>/routines/<routine>.toml`, one file per job, named in
kebab case. The engineering roles are still single files
(`roles/eng/<role>.toml`), so their routines sit in a folder of the same
name next to that file: `roles/eng/researcher/routines/`. Each seat package
has an empty `routines/` folder that holds only `.gitkeep`.

| Key | Type / meaning |
|---|---|
| `description` | Required. One line: what the job does. |
| `skill` | Required. The skill it runs, a kebab-case ID. When the package has `skills/`, the ID must name a folder there. |
| `actions` | Required. A nonempty list of the [actions contract](../actions/README.md#actions) names the job uses. |
| `schedule` | Required table. Exactly one of `every` or `cron` (below). |
| `inputs` | Required list: the artifacts the job reads. May be empty. |
| `outputs` | Required nonempty list: the artifacts and reports it writes. |
| `deadline` | Required duration: the SLA. A slot not started within this time after it falls due is missed. |
| `on_miss` | Required: `skip`, `catch-up-once` or `escalate` ([miss handling](#miss-handling)). |
| `retry` | Optional duration: after a failed run, it falls due again this long after. Without it, the next slot. |
| `due_on` | Optional list of [event types](../actions/README.md#events). An event after the last run makes the job due at once. |
| `enabled` | Optional boolean, default true. `false` declares the job without scheduling it. |
| `enabled_key` | Optional profile key whose value turns the job on, such as `triage.enabled`. Not with `enabled`. |
| `idle_backoff` | Optional integer >= 1: each idle run doubles the wait, up to this many times the period. |

A duration is a whole number and a unit, `s`, `m`, `h` or `d`: `90s`,
`10m`, `6h`, `7d`.

**Schedule.** `every` is an interval. `every_key` names the profile key
that overrides it, in the unit its suffix gives (`_seconds`, `_minutes`,
`_hours` or `_days`), and `every` is the default. `jitter` (default `0s`,
shorter than `every`) delays each slot by a stable amount up to that
length. `cron` is five fields: minute, hour, day of month, month and day of
week (0 is Sunday). Each field takes `*`, numbers, ranges, lists and
`/step`. `timezone` is `"owner"`, the default: cron times are in the
profile's `runtime.timezone`, and in UTC when that is unset.

**Generic only.** A routine names skills, generic actions, contract event
types and profile keys. It names no environment, command, session or file
of a runtime. The repo lint (`check-repo.py`, check `routines`, and the
[runtime-word lint](specs/team.md#5-dependency-rules)) rejects any routine
that does.

```toml
description = "Triage every queued item: place it, record its flavor and log the sweep."
skill = "triage-sweep"
actions = ["read", "tracker", "post-marker", "report"]
schedule = { every = "6h", every_key = "triage.interval_hours", jitter = "0s", timezone = "owner" }
enabled_key = "triage.enabled"
inputs = ["triage queue", "triage log"]
outputs = ["triage records", "triage log entry", "owner digest"]
deadline = "1h"
on_miss = "catch-up-once"
retry = "10m"
```

## Miss handling

`core/crew-routines.py` decides when a routine is due, and every
environment uses that decision:

1. A routine that never ran runs now. Its first run anchors the schedule.
2. A failed last run with `retry` falls due `retry` after it.
3. An event in `due_on` that came after the last run makes it due now.
4. Otherwise the slot is the latest one at or before now. For an interval
   it is a whole number of periods after the last run; for cron it is the
   latest matching minute. Earlier slots in a gap were missed.
5. A slot is on time until `deadline` after it starts. Past that, the
   slot is missed and `on_miss` decides what happens:

| `on_miss` | Effect |
|---|---|
| `skip` | The slot is recorded unrun. The next one runs on time. |
| `catch-up-once` | One run now, for every missed slot. |
| `escalate` | The miss is reported to the team head, then one run now. |

## Environments

Each environment schedules routines with its own tools.

### Terminal

The terminal environment runs routines from its zero-token watcher
([mdstack watch](runtimes/tmux.md#mdstack-watch)). Nothing new runs in the
background.

- **Migrated timers.** Three jobs were already watcher timers. They keep
  their code and now take their cadence, retry and on/off switch from the
  routine file:
  - the triage sweep (and the milestone-close sweep, which shares its slot);
  - the docs pass;
  - the backstop, which is the coordinator's `stale-sweep`.
- **Lifecycle roles.** A role with a [lifecycle](roles-registry.md#lifecycle)
  whose `wake` lists `routine` is woken by its due routines. On each scan
  the watcher calls `mdstack up`'s `routine_tick`. For a due routine, it
  starts an instance when none runs, up to `max`. Then it runs
  `mdstack send <instance> routine <routine file>`. The slot is recorded in
  `routines/<role>.<routine>.json` in the state dir. An escalated miss is
  also a `routine-missed` watcher wake for the coordinator.
- **Scale to zero.** A role with no due routine starts nothing, and the
  watcher's scale-down kills idle instances as before. An ephemeral role
  with no due work stays at zero.

### Other environments

A hosted platform maps each routine to its own routine trigger: the
schedule becomes the trigger's schedule, and the run prompt names the
routine file and its skill. The session binding documents its
[`triage-sweep` trigger](runtimes/session.md#triage-sweep-routine)
(#1404); its other routines have no trigger yet. The Grok Bot binding does not read routine
files yet. Its routines are still rendered from
[its templates](runtimes/grok-bot.md), and binding them is follow-up work.

## Migrated jobs

| Role | Routine | Cadence | Before #1247 |
|---|---|---|---|
| Researcher | `triage-sweep` | Every `[triage] interval_hours` (6 h), retry 10 m, catch up once | Watcher triage timer ([triage](triage.md#triggers-and-cadence)) |
| Researcher | `milestone-close-sweep` | At once on `dev.eng-crew.milestone.closed`, else with the triage sweep | Watcher triage timer, closed-milestone path (#374) |
| Researcher | `protocol-reflection` | Monday 00:00 owner time and at once on `dev.eng-crew.milestone.closed`, retry 10 m, catch up once (new, #1521) | None: `[reflection] enabled` turns on the watcher reflection timer |
| Researcher | `docs-pass` | Every `[docs] interval_days` (7 d), retry 10 m, catch up once | Watcher docs-pass timer ([project docs](project-docs.md#docs-pass)) |
| Coordinator | `stale-sweep` | Every 30 m, doubling while idle up to 16 times, missed backstops skipped | Watcher `--backstop` default |
| Coordinator | `metrics-refresh` | Declared, `enabled = false`: still run by hand at each milestone close | Manual ([metrics trigger path](metrics/decisions.md#trigger-path)) |
| Coordinator | `decision-log-status` | Declared, `enabled = false`: still posted by hand | Manual ([decisions](decisions.md)) |

The parity tests in `dev/tests/core/test-crew-routines.py` pin these
cadences. The watcher tests confirm the timers behave as before.
