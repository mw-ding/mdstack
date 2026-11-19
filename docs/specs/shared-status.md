# Spec: shared status for independent crews

**Status: design delivered (SD, [#1889](https://github.com/mw-ding/mdstack/issues/1889),
PR #1896); built in source by ST ([#1313](https://github.com/mw-ding/mdstack/issues/1313),
PR #1905), M57.** Source delivery is not a release: v7.13.0 predates both, so
no release carries shared status yet. Nor is it an installation: no crew is
claimed to be registered or publishing to a real issue. Milestone row and decision record:
[portable spec, M57](portable.md#sd-and-st-shared-status-1889-1313).

Several independent mdstack installs (crews, projects, hosts; each with its
own coordinator, state directory and decision log) each publish one compact
status record into one owner-chosen place, and `mdstack status --all` reads
them back as one view. This file settles the contract S.1–S.6 that ST
implements and tests.
It applies the
[coordinator's M57 decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6884417656):
a closed pointer/count schema; explicit unique install registration; one
per-instance comment on one owner-selected issue; `status --all`; off until
configured; 300 s publish and 900 s stale defaults. Source analysis:
[readiness pass §5](https://github.com/mw-ding/mdstack/issues/1885#issuecomment-6884328732).

A record is a **diagnostic**. It is not a `crew:v1` marker, carries no pass,
verdict, steering or gate meaning, and an observation in it is never
permission to act. This design adds no protocol rule, gate, marker field,
label or required backend operation.

## 1. Terms

| Term | Meaning |
|---|---|
| Install | One resolved mdstack configuration with one state dir (`$CREW_STATE`): a one-repo profile or one team file |
| Instance | The install's owner-configured `instance_id`, unique within the destination |
| Registration | The opaque `registration_id` an explicit `mdstack status register` creates once for an instance |
| Destination | The configured issue holding every instance's comment |
| Slot | The one comment an instance owns on the destination |
| Publisher | The authenticated account that writes the slot: the install's `identities.coordinator.gh_user` |
| Receipt | Local file binding the instance to its registration, slot and last confirmed write |
| Section | One pointer/count part of the record, `known` or `unknown` |

## 2. Configuration (S.2, S.6)

An optional `[status]` table. It is team-level: in a
[team file](../configuration/team-files.md) it sits beside `[team]`, and a
`[repos.<name>]` section that sets it is refused. Absent, every key takes its
default, status is off, and `validate`/`resolve` behave exactly as today:
`resolve` prints `[status]` only when a layer sets it.

| Key | Type and rule | Default |
|---|---|---|
| `enabled` | boolean. `true` starts the watcher's publish timer; needs `destination`, `instance_id` and `decision_log` | `false` |
| `destination` | string fully matching the bound status backend map's `[ids] status-destination` pattern; the bundled GitHub map declares `https://github.com/<owner>/<repo>/issues/<n>` | unset |
| `instance_id` | string `[a-z0-9][a-z0-9-]{0,62}`. Never defaulted from `runtime.instance`, a repo, team, host or path | unset |
| `decision_log` | string, an issue URL under the §3.4 URL rule | unset |
| `publish_interval` | integer seconds, 60–3600 | `300` |
| `stale_after` | integer seconds, from 2 × `publish_interval` to 86400; the reader's own threshold | `900` |

`validate` refuses an unknown key, a wrong type (a TOML boolean or string
where an integer is due, a float), an out-of-range value and `enabled = true`
with a required key unset, in the existing `file:key: reason` format.

Binding: an optional concern `status` ([§7](#7-optional-seam-s6)). The
bundled default layer binds `[backends.status] name = "github"`. `resolve`
refuses `enabled = true` unless the effective `status.publish-record` and
`status.read-records` are both `supported` (`emulated` is refused, as for
`classify`), and a set `destination` unless `status.read-records` is
`supported`. With `destination` unset the concern is not checked, so every
existing profile and manifest resolves unchanged.

## 3. Record S, version 1 (S.1)

### 3.1 Slot body

A slot body is exactly: line 1 `<!-- mdstack-status v=1 -->`, then one fenced
block with info string `json` holding the record, then nothing but an
optional final newline. A comment whose first line is not that marker is not
a status comment and is ignored. A comment with the marker and any other
deviation is an **invalid** status comment. The marker never contains
`crew:v1`, and no protocol parser reads it.

### 3.2 Top-level fields

Every field is required; any other field refuses.

| Field | Rule |
|---|---|
| `schema_version` | JSON integer `1`. Any other value: unknown version |
| `instance_id` | `[status] instance_id` pattern |
| `registration_id` | `r-` then 32 lowercase hex digits (128 random bits, made once by `register`) |
| `sequence` | JSON integer, 1 to 2^53−1; strictly increasing per registration |
| `observed_at` | UTC time; equals the earliest section `observed_at` |
| `published_at` | UTC time, not before `observed_at` or any section `observed_at` |
| `source` | object, exactly `repos`, `runtime`, `decision_log` |
| `sections` | object, exactly the six keys of §3.3 |

`source.repos`: 1–32 strings `<owner>/<name>` (`[A-Za-z0-9-]+/[A-Za-z0-9._-]+`),
sorted and distinct: the install's `repo.owner/repo.name`, or every
`[repos.<name>]` of a team file. `source.runtime`: `runtime.name`, one of
`tmux`, `session`, `grok-bot`. `source.decision_log`: the configured value.

### 3.3 Sections and collectors

A section is `{"state": "known", "observed_at": T, <payload keys>}` or
`{"state": "unknown", "observed_at": T, "reason": R}`, with R one of
`read-failed`, `unsupported`, `over-limit`. A known section has exactly its
payload keys, an unknown one none. A collector that did not complete a fresh
read reports `unknown`; it never reports empty, zero or healthy in its place.
Each read is per source repo; one failed or partial (unpaginated) repo read
makes the whole section `read-failed`. A list above its limit is
`over-limit`, never truncated. `observed_at` is the time of the read.

| Section | Payload | Item rule | Limit | Collector source |
|---|---|---|---:|---|
| `milestones` | `items`: `[{url, completed, total}]` | Milestone URL in a source repo; `0 <= completed <= total` | 20 | Tracker `milestone` read: open milestones in the active window (`max_active_milestones`, in milestone order; a team repo's `milestones` list when set); `completed` closed items, `total` all items |
| `prs` | `items`: `[{url, stage}]` | PR URL in a source repo; stage enum below | 100 | `change.list-open` and `state-tags` labels per source repo |
| `owner_asks` | `items`: `[{url, deadline}]` | Item URL in a source repo; `deadline` a UTC time or `null` | 50 | Open items labelled `crew:needs-md`. The GitHub collector writes `deadline: null`: today's auto-apply time is prose, and prose is never parsed. A pack collector may fill it only from a structured field |
| `blockers` | `items`: `[{url, kind}]` | Item or PR URL in a source repo; one entry per URL; kind `escalated`, `main-red`, `held`, first match wins | 50 | Open items labelled `crew:escalated` or `crew:hold`; open issues whose title starts with `main-red` |
| `throughput` | `merged_24h` | Count | — | Change backend's merged list: PRs in source repos merged in the 86400 s up to the read |
| `queue` | `depth`, `target` | Counts | — | Newest `snapshot` line of the scheduler's `schedule/decisions-<yyyymmdd>.jsonl` (team root for a team file): `depth` = builder plus reviewer demand entries, `target` = its `target`; `observed_at` = its `ts`. Demand `unknown`, no readable line, or a `ts` at least `stale_after` old: `read-failed`. A runtime with no scheduler (`session`, `grok-bot`): `unsupported` |

PR `stage`, first match wins: `escalated` (`crew:escalated`), `held`
(`crew:hold`), `changes` (`crew:changes`), `approved` (`crew:approved`),
`in-review` (`crew:in-review`), `other` (none of these).

### 3.4 Value rules

- **Strings:** every string is an enum value, an ID pattern, a UTC time or a
  URL under this rule. No field takes free text, so titles, summaries,
  names, host names, paths, environment values and conversation text have
  no place to go. The serialized record also passes the repo's
  `core/secret-patterns.py` scan; a match refuses.
- **URL:** `https://github.com/<owner>/<repo>/` followed by `issues/<n>`,
  `pull/<n>` or `milestone/<n>` (`<n>` a positive integer), for the bundled
  backend; no user info, port, query or fragment. A pack's map declares its
  own patterns in `[ids]`.
- **Counts:** JSON integers 0–1,000,000. A string, boolean, float, negative
  or larger number refuses.
- **UTC time:** `YYYY-MM-DDTHH:MM:SSZ`, a real calendar time. A time more
  than 120 s after the checker's clock is **future**: the publisher refuses
  it; a reader marks the record invalid. `deadline` is exempt from the future
  check.
- **Size:** the slot body is at most 60,000 bytes UTF-8; larger refuses.
- **Content identity:** SHA-256 of the record's canonical JSON (sorted keys,
  `,`/`:` separators, no whitespace, UTF-8).

## 4. Identity and registration (S.3)

`instance_id` is the only identity readers use; display labels, repo sets and
runtime kinds never identify an instance, so two installs with equal labels
stay distinct. Different installs need different instance IDs. An exact
clone of an install is not distinguishable from a restart by the destination
alone, so the receipt carries a local **binding**: SHA-256 of the host name,
the real path of `$CREW_STATE` and the real path of the resolved config file.
The binding is stored only in the receipt, never published.

Receipt `$CREW_STATE/status/receipt.json`, closed object: `schema_version`
(1), `destination`, `instance_id`, `registration_id`, `publisher`,
`comment_id` (`null` until registration is confirmed), `binding`,
`sequence` and `content_sha256` of the last confirmed write, and `pending`.
`pending` is `null` or `{op, state, sequence, content_sha256, body}`: `op`
is `create` or `update`, `state` is `prepared` or `uncertain`, and `body` is
the exact slot body bytes (§3.1) to be sent. Every receipt write is atomic:
a temporary file in `status/`, flushed and synced, renamed over the
receipt, then the directory synced. A run that loads a receipt validates
`pending` first: `body` parses as a slot body whose record passes §3.2–§3.4
(except the future check), carries this `instance_id` and
`registration_id`, has `sequence` equal to `pending.sequence` (receipt
`sequence + 1`, or 1 for `create`) and has content identity
`content_sha256`. Anything else refuses `receipt-invalid` with no write.

`mdstack status register [--repo KEY]` is the only path that creates a
registration or a slot; the timer never registers. Since 8.0.0 an owner
shell names the profile with `--repo` or `MDSTACK_CONFIG`; crew windows and
the timer still pass `--project FILE`
([owner shell](../runtimes/tmux.md#user-level-and-project-level-config-1316)).
In order:

1. Run the §5 read phase with no receipt required.
2. A receipt for this `destination` and `instance_id` with a matching binding
   and a confirmed slot: print `registered <instance_id>` and write nothing.
3. A receipt for this instance with a `create` still pending: adopt the one
   publisher-authored status comment holding its `registration_id`
   (any page) when it is exactly `pending.body`, and confirm, with no write
   to the destination; other content refuses `conflict`. With no such
   comment, refuse `uncertain` (§5 Outcomes): never generate another
   `registration_id` and never create again for this instance.
4. A receipt for another destination or instance ID: archive it, `pending`
   included, as `status/receipt-<registration_id>.json` in step 7; never
   delete it.
5. Any other status comment on the destination with this `instance_id`
   refuses. A copied receipt (binding mismatch) refuses.
6. Duplicate status comments for one `instance_id` or one `registration_id`
   anywhere on the destination refuse.
7. Take the lock, generate `registration_id`, build the sequence-1 body,
   write the receipt with `pending` (`create`, `prepared`), create the slot
   once, and apply the §5 outcome rules.

A refused `register` names the conflicting comment URL. Recovering a lost
state dir, separating a clone or leaving an unresolved uncertain write means
choosing a new `instance_id` and running `register`; the old slot then ages
stale, and a delayed write can land only there.

## 5. Publication and the zero-write boundary (S.2, S.4)

`mdstack status publish [--repo KEY] [--check]` writes one record: it is
what the timer runs. `--check` runs only the read phase and prints the
record it would publish, or the refusal, writing nothing.

**Read phase.** Every step is a read. A refusal at any step means **zero
writes**: no destination POST, PATCH or DELETE, and nothing under the state
dir (no receipt, lock file, `status/` directory, queue, inbox, wake, status
line, `schedule/errors.jsonl` entry or other telemetry). The reason goes to
stderr with exit 1. Success exits 0; a usage error exits 2. `register`
shares these exits.

1. Config resolves and validates; `[status]` is enabled with every required
   key (for `publish`; `register` needs all but `enabled`).
2. The caller is the watcher or an owner shell: a run with `CREW_ROLE` set to
   any role other than `coordinator` (builders, reviewers, pool leads)
   refuses.
3. `mdstack ownership --action write` permits, and no project pause barrier
   exists or is unreadable.
4. The backend's authenticated account equals `identities.coordinator.gh_user`.
5. For `publish`, the receipt exists, parses, matches the configured
   `destination` and `instance_id`, its binding matches this install, and
   its registration is confirmed (a `register` still pending refuses: rerun
   `register`).
6. The destination is open and every page of its comments reads. For
   `publish`, the bound slot exists, is publisher-authored, is on the
   configured issue and holds this `instance_id` and `registration_id`. No
   other status comment holds either.
7. Collectors run (§3.3) and the record validates (§3.2–§3.4).

**Write phase.** Only after acceptance: take an exclusive lock on
`$CREW_STATE/status/publish.lock`, re-read the receipt and the bound slot,
and refuse if either changed since the read phase. Then:

| Bound slot shows | Receipt `pending` | Action |
|---|---|---|
| The confirmed record (receipt `sequence` and `content_sha256`) | `null` | Build the record at `sequence + 1`, write `pending` (`update`, `prepared`) with its exact body, send it once, apply the outcome rules |
| Exactly the `pending.body` record | set | Confirm: set receipt `sequence` and `content_sha256` from it, clear `pending`; no write |
| The confirmed record | set (`prepared` or `uncertain`) | The earlier send may still apply: refuse `uncertain`; no write. Never resend `pending.body` and never build a newer record |
| Anything else: lower, higher or same sequence with other content | any | Refuse `conflict`: publication stops until the owner resolves it; no write |

**Outcomes.** The status connector reports each create or update as exactly
one of:

- `applied`: a success response naming the slot. Read it back; confirm
  only when the slot holds exactly `pending.body`, else refuse `conflict`.
- `rejected`: a response that the backend definitively did not apply
  (for GitHub, a 4xx with a body). Clear `pending`; no retry in this run.
- `not-sent`: the request failed before any byte reached the backend.
  Clear `pending`.
- `uncertain`: anything else (timeout, lost connection, a 5xx, a run that
  stopped while `pending` was `prepared`). Set `pending.state` to
  `uncertain`.

An uncertain send is never repeated, and nothing newer is sent after it:
the bundled GitHub backend has no conditional write, so a request whose
outcome is unknown may still apply later and no later write can be fenced
against it. Each later run only reads back. When the slot shows exactly
`pending.body`, that send applied: confirm and resume. While it does not,
publication stays stopped, the row ages stale in `status --all`, and
`status publish --check` prints `uncertain` with the pending sequence. The
owner either waits or re-registers under a new `instance_id` (§4). Replaying
a record whose sequence and content identity the slot already shows writes
nothing. A restart keeps the receipt, so it keeps the registration, the
latest confirmed sequence and any pending body byte for byte; fresh
collector data never replaces a pending body.

**Timer.** The watcher runs `status publish` as a subprocess on a scan at
least `publish_interval` after its last attempt: no model or coordinator
wake, and its stderr is discarded (`--check` reproduces a refusal). It does
not run while `enabled` is false, the project is paused (the watcher's
observation mode runs no timer) or ownership is lost. A duplicate tick in
the same interval meets the lock or the interval check and writes nothing.

## 6. Aggregate view: `status --all` (S.5)

`mdstack status --all [--repo KEY]` is read-only: it never takes the lock
or writes the destination or the state dir, and it needs no running tmux
session. Plain `mdstack status` keeps its current output and exits. It reads
every page of the configured destination and prints one row per instance,
sorted by `instance_id`:

```text
INSTANCE  REPOS  RUNTIME  AGE  STATE  BLOCKED  UNKNOWN  PRS  ASKS  QUEUE
```

- `AGE` is reader now minus the record's `observed_at`, so republishing old
  observations never refreshes it. `STATE` is `fresh` when age <
  `stale_after`, `stale` when age >= `stale_after`, `invalid` for a
  malformed, unknown-version or future-dated record, and `conflict` for
  duplicate instance or registration IDs. Invalid and conflicting rows are
  never fresh.
- On a valid row, `BLOCKED` is `yes` when `blockers` is known and
  non-empty, `unknown` when it is unknown, else `no`. `UNKNOWN` lists unknown sections, or `-`. An
  invalid or conflicting row shows `-` in every column after `STATE`.
- Then one `diagnostic:` line per invalid comment or failed read, naming the
  comment URL and the reason.

Exits: 0, every page read (stale, invalid and conflicting rows included);
1, incomplete read (API error, a page failed, destination closed or
missing), printing the rows read so far and a `partial:` line; 2, a usage or
config error; 3, `destination` unset (`status --all: unconfigured`). With
`enabled = false` and a destination set, it still reads.

## 7. Optional seam (S.6)

A new optional concern `status`, like `release` and `classify`; the eight
required concerns, their operations and every existing manifest are
unchanged. A manifest may declare `[capabilities.status]`; when present,
both keys are required.

| Operation | Guarantee |
|---|---|
| `read-records` | Returns every comment of the destination with its id, author and body, and whether the listing is complete (all pages) and the destination open; never writes |
| `publish-record` | Sends one create (only for `register`) or one edit of the instance's own slot after verifying the authenticated account, and reports exactly one outcome: `applied`, `rejected`, `not-sent` or `uncertain` (§5 Outcomes); never retries by itself, never edits the destination body, another comment or a label, and never deletes |

Bundled GitHub mapping, in `templates/backends/github.toml` `[status]`:
`read-records` reads the issue and `--paginate`s
`repos/<owner>/<repo>/issues/<n>/comments`; `publish-record` POSTs a comment
(register) or PATCHes `issues/comments/<comment_id>`. A pack supplies its own
map entries and `[ids] status-destination`; the direction rule holds.
Placement: pure schema and validation in `core/status-record.py`; the
connector in `connectors/github/status.py`; collectors, receipt, lock and
timer in terminal modules (`_status_shared.py`, `status.py`, `watch.py`),
invoked only through the declared capability.

## 8. Lifecycle

Unconfigured → configured (`destination`, `instance_id`, `decision_log`) →
`register` (slot at sequence 1) → `enabled = true` (timer publishes) →
`enabled = false` (no later write; the slot ages stale) → optional re-enable
(sequence continues from the receipt). An `uncertain` outcome pauses
publication for the instance until readback confirms it, or until the owner
re-registers under a new `instance_id`. No removal command is part of ST;
deletion, if ever added, needs its own mutation proof.

## 9. Test fixtures and acceptance matrix

Fixtures, all disposable:

- **Fake status API:** in-memory comments per issue, configurable page size
  (2 by default, so page 2+ is exercised), an audit log of every POST, PATCH
  and DELETE, an authenticated-login setting, and faults: fail before send
  (`not-sent`), definitive 4xx (`rejected`), apply then lose the response,
  time out and apply only after K later reads or after a restart (delayed
  application), time out and never apply, 5xx, a failed page N, closed and
  missing issue; each for create and update.
- **Interrupted run:** stop the publisher after the receipt holds `pending`
  (`prepared`) and before the send, and after the send before its outcome
  is recorded; restart with changed collector data.
- **Fake clock** through a test-only seam ST names, used for every UTC check.
- **State snapshot:** recursive file list with SHA-256 of the state dir
  before and after; a refusal row asserts equality.
- **Collector stubs** per section: value or failure.
- **Fake optional status pack:** manifest with and without
  `[capabilities.status]`, map with `[status]` commands and `[ids]`.

Each AC is one table-driven test over its field or state set. Every row
asserts exit, stdout/stderr substrings, the API audit and the state snapshot,
through the shipped CLI entry point, and every refusal row names its valid
control row.

| AC | Refusal rows (each paired with a valid control) |
|---|---|
| S.1 | Missing, extra and wrong-typed field per §3.2/§3.3 key; version 0/2; string, boolean, float, negative and too-large counts; `completed > total`; bad, foreign-repo and credentialed URLs; malformed and future times; unsorted or duplicate repos; known section with `reason`; over-limit list; secret-pattern match; oversize body. Control: a valid minimal record with every section unknown, and a full one |
| S.2 | Off, unset destination, instance ID or decision log; invalid config; worker or pool-lead caller; ownership refused; pause barrier present and unreadable; wrong authenticated account; foreign registration. Control: the authorized publish |
| S.3 | N = 0/1/2/3 instances; equal repos and runtime labels; reused instance ID with another registration; copied receipt (binding mismatch); wrong issue, comment or author; duplicates on a later page; concurrent distinct publishers A and B. Control: each changes only its own slot, other comments and the issue body unchanged |
| S.4 | Same content (no write); `not-sent` and `rejected` (pending cleared, no retry in that run); lost response then readback (confirm, no resend); timeout with delayed application: no resend and no newer record until readback shows the pending body, then confirm; timeout that never applies: publication stays stopped and `register` never creates again for that instance; re-registration under a new `instance_id`, then the old send lands late in the old slot only; interrupted runs replay nothing and keep the original pending bytes despite changed collector data; corrupt or mismatched `pending`; slot showing a higher or conflicting sequence; `applied` with a different readback. Control: each confirmed outcome, exactly one registration per instance and the newest confirmed record in each slot |
| S.5 | Clock at `stale_after` − 1/0/+1; delayed republish of old observations; future time; unknown sections; malformed and unknown-version comments; duplicates; closed or missing destination; API and page failures; unconfigured. Control: complete fresh view, no writes |
| S.6 | Old manifests and profiles resolve byte-identical; status pack declared/undeclared/`emulated`; enabled timer then off, pause, ownership loss; collector failure; duplicate tick; plain `status` output unchanged. Control: fake CLI register → publish → publish → `status --all` with only the intended slot changed, then disable with no later write |

## 10. Prospective sensitive and gate changes

- **Gate contract: none.** `docs/protocol.md`, the §7 gate registry,
  markers, labels and the required concerns stay untouched. A record grants
  nothing. An ST change that touches any of these is gate-contract work and
  is reclassified before review.
- **Sensitive:** the path rules forecast no match for ST's named paths
  (`core/crew-config.py sensitive --paths-only` on them returned no label).
  The prospective sensitive content is ST's publication authority (the §5
  caller, ownership, pause and publisher checks), the destination binding
  and the zero-write boundary. Classify ST's actual full diff at each head;
  a sensitive head needs the owner's per-change reason.
- **Version:** ST forecasts **minor** if old profiles, manifests and plain
  `status` stay unchanged; making the concern required, or changing existing
  `status` output or exits, is **major** and is replanned. This design alone
  is **none** (internal spec).

## 11. Out of scope

A second built-in destination, a UI, deletion or garbage collection of
slots, authenticating other installs' records (a reader validates schema and
uniqueness only; records grant nothing), parsing prose deadlines, and any
change to how `crew:v1` markers, holds, escalation or scheduling work.
