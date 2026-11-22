# Backend interfaces

The minimum operations a backend must support for each concern, the guarantee
each operation gives, and the invariant it protects (portable mdstack, roadmap
13.9, [#121](https://github.com/mw-ding/eng-crew/issues/121)). Terms are in
[concepts.md](concepts.md). Invariants are numbered as in
[portable spec §3](specs/portable.md#3-invariants): I1 author ≠ reviewer, I2
reviewer engine ≠ writing engine, I3 evidence on the change record, validated at head, I4 only the
synthesizer lands, I5 the tool of record holds the audit trail. R is the
release gate ([release](#release)).

This page adds no rule, gate, cap, marker field or label. The
[protocol](protocol.md) owns them; the merge gates are in
[§7](protocol.md#7-merge-gate-synthesizer) and the
[gate registry](protocol.md#gate-registry). Today's GitHub commands for every
operation are in [GitHub backend: Interface mapping](backends/github.md#interface-mapping).
The runtime side (wake, one consumer, liveness, serial land) is the
[runtime contract](runtimes/README.md).

## Concerns

### change

| Operation | Guarantee | Protects |
|---|---|---|
| Open, linked to an item | The new change names its tracker item; landing closes it unless it is an umbrella | I5 |
| Push | Adds commits to the change branch; never rewrites shared history (under a declared [`rebase` update](#rebase-update-from-base): uploads a new head, every earlier head stays readable) | I3 |
| Read head | Returns the full 40-character head revision: the published one, never a local commit or an unpublished draft. It is the change's [authoritative revision](protocol.md#6-duties-on-wake-all-roles) | I3 |
| Read diff paths | Lists the paths changed at head, for path-derived gates | I3 |
| Read diff (`read-diff`) | Returns the unified diff at head against its merge base, without rename folding, for a role with no checkout to run [content rules](profile.md#content-rules-879) on | I3 |
| Update from base | Merges the base into the change (never a rebase), making a new head; a backend that declares a [`rebase` update](#rebase-update-from-base) rebases onto the base and uploads instead | I3 |
| Land (squash, head-pinned) | One squash commit on the default branch; refused if the head moved from the given revision | I3, I4 |
| Close | Ends the change without landing; the record stays readable | I5 |
| List open (`list-open`) | Lists the open changes with their branches and linked items, so a build adopts an existing change | none |
| Read state (`read-state`) | Returns a change's state, head branch, head repository, cross-repository flag and base branch | none |
| Read default branch (`read-default-branch`) | Returns the repository's default branch | none |
| Delete branch (`delete-branch`) | Deletes a landed change's head branch | none |
| Delete on land (`land-delete-arg`) | Brief text: the argument added to Land so the land also deletes the change's head branch; added only for a same-repository head that is neither the default nor the base branch | none |
| CLI conventions (`cli-name`, `cli-repo-flag`, `cli-unscoped`) | Brief text: the backend's command-line tool, its per-repository scope flag and the call that takes no scope flag | none |

`read-diff` is conditional (#879): `resolve` requires it only when the
resolved profile declares content rules; a manifest without it stays valid
otherwise.

`land-delete-arg` is conditional (#395): with it mapped, the sync tmux and
session synthesizer briefs add it to an eligible land, so the land itself
deletes the head branch; `mdstack train land` does the same for each member
on GitHub. Without it, the land keeps the branch and close-out's guarded
`delete-branch` removes it.

A backend whose VCS forbids merge commits declares a rebase update, with
every earlier head kept readable in place of the no-rewrite guarantee
([rebase update from base](#rebase-update-from-base), #874).

### review

| Operation | Guarantee | Protects |
|---|---|---|
| Post verdict (pass / changes) pinned to head | Bound to one head; posted by an identity other than the change author; the body holds the markers | I1, I2, I3 |
| Post narrative | Non-binding; never counts as a verdict; wakes no work role | I5 |
| List verdicts | Every verdict with its author identity, head, state, body and order | I1, I3, I4 |
| Request re-review | Wakes the reviewer for a fresh verdict at the current head | I2, I3 |

### tracker

| Operation | Guarantee | Protects |
|---|---|---|
| Create item | Durable item with goal and acceptance criteria | I5 |
| Assign | Records who builds the item; the runtime may wake on it | I5 |
| Link change ↔ item | Readable from both sides | I5 |
| Milestone | Set and read an item's milestone; a closed milestone takes no new items | I5 |
| Board status | Set and read Todo / In Progress / In Review / Done | I5 |
| List items (`list-items`) | Lists open and closed items with title, body, labels, milestone, state, close reason, creation time and comments, for a [triage](triage.md) lookup | I5 |
| Label (`label`) | Sets, clears and reads a non-state label on an item (the triage and priority labels of [protocol §4](protocol.md#4-marker-conventions)) | I5 |
| Comment (`comment`) | Appends a signed post with its marker line to any item (a triage record, a log entry, an extracted card); never edited | I5 |
| Close item (`close-item`) | Closes an item with a reason; it stays readable | I5 |

### state tags

| Operation | Guarantee | Protects |
|---|---|---|
| Set / clear / read | Durable on an item or change; setting or clearing wakes no role (or the runtime ignores the tag event) | I4, I5 |
| Set approved / set changes (`set-approved`, `set-changes`) | The reviewer's state-tag change right after its verdict: one tag set, the other review tags cleared | none |

I4 because the land reads hold and escalation tags.

### markers

| Operation | Guarantee | Protects |
|---|---|---|
| Write | A signed header plus the `crew:v1` line inside a post on the change, carrying the full head SHA ([protocol §4](protocol.md#4-marker-conventions)); append-only, never edited or deleted | I1, I3, I5 |
| Read | Every marker on the change in post order, with the posting identity | I1, I3, I5 |
| Write item (`write-item`) | Append-only coordinator ownership post on the control item | I4, I5 |
| Read item (`read-item`) | All control-item markers in backend post order with posting identity | I4, I5 |
| Edit status (`edit-status`) | Updates the synthesizer's diagnostic `pass=gate-status` post in place; the only edited marker post, never a verdict or permission | none |

The signed marker is the role identity when several roles share an account.
Item-level ownership markers use the same append-only guarantees on the
repo control item, read in post order with the posting identity
([ownership record](protocol.md#ownership-record)); change markers keep
using the existing `write` and `read` operations.
The backend-neutral `read-item` output, the `write-item` retry rule and the
`<control-item>` placeholder for a tracker-native control item id are in
[handoff](handoff.md#tracker-native-control-item) (#875, #937). So are
the output `mdstack handoff` reads from `tracker.list-items`,
`change.list-open`, `change.read-head` and `markers.read` for a non-GitHub
install, and the two conditional operations it alone runs there:
`change.read-branch-head` (the default-branch head) and `tracker.unlabel`
(clears a label, for the hold lift).

### CI

| Operation | Guarantee | Protects |
|---|---|---|
| Required-check status at head | Pass / fail / pending of every required check for that exact head, never an older one | I3 |
| Failing job names | Names and log links of the failing jobs at head | I3 |

### events

| Operation | Guarantee | Protects |
|---|---|---|
| Subscribe or poll | Delivers the state-transition events of [protocol §8](protocol.md#8-safety) and the steering comment events, each naming the item or change, the head and the actor | I1, I4 |

The actor lets steering accept commands only from the owner's accounts
([§9](protocol.md#9-steering-crew-commands)). One consumer per event and
re-delivery are runtime duties ([C1, C2](runtimes/README.md#contract)).

### owner channel

| Operation | Guarantee | Protects |
|---|---|---|
| Ask with default and deadline | Reaches the owner with a recommended default and auto-apply time; the ask and the answer are recorded on the tool of record | I5 |
| Notify | One-way message to the owner, also recorded | I5 |

### release

Optional: a backend may leave the whole concern undeclared, and only a
profile with a [`[release]` table](profile.md#release) needs it
([release operations](release.md#release-operations),
[#585](https://github.com/mw-ding/eng-crew/issues/585)). R is the
[release gate](protocol.md#gate-registry): no release is published without
the owner's per-change merge-ok at the landed cut's head.

| Operation | Guarantee | Protects |
|---|---|---|
| Cut | Produces the cut change (the CHANGELOG version section plus the consumed fragments) as a normal change for review and the [§7 merge gate](protocol.md#7-merge-gate-synthesizer); never writes the default branch directly | I4, R |
| Approve check | After the cut lands and before any release id is written, verifies the owner's per-change merge-ok at the landed cut change's head, release validation green and required CI green at the landed revision; refuses otherwise | R |
| Record release | Writes the release id once, on the landed cut revision: a tag, or the full 40-character commit hash ([`release_id`](profile.md#release)); never moves or rewrites it | R, I5 |
| Notify | Posts the release link or id on the release item and closes it | I5 |

### status

Optional: a backend may leave the whole concern undeclared, and only a
profile with a [`[status]` table](profile.md#status) that sets a destination
or `enabled = true` needs it
([shared status](specs/shared-status.md#7-optional-seam-s6),
[#1313](https://github.com/mw-ding/mdstack/issues/1313)). It carries one
diagnostic status record per install into one owner-chosen place; a record
is never a `crew:v1` marker, gate input or permission to act, so no
invariant depends on it. Like `classify` it is not an `<op:>` token: the
runtime's `mdstack status` commands run the bound backend map's `[status]`
commands through `sh -c`, each with one JSON request on stdin and one JSON
object on stdout, and bootstrap and a team's pack never bind it.

| Operation | Guarantee | Protects |
|---|---|---|
| Read records (`read-records`) | Request `{destination}`; returns `{login, issue, complete, comments}`: the authenticated account, the destination's state (`open`, `closed`, `missing`, `unknown`), every comment's `{id, author, body}` and whether every page read; never writes | none (diagnostic) |
| Publish record (`publish-record`) | Request `{destination, publisher, op, comment_id, body}`; verifies the authenticated account, then sends one create (`register` only) or one edit of the instance's own slot and returns `{outcome, comment_id, error}`, outcome exactly one of `applied`, `rejected`, `not-sent`, `uncertain`; never retries by itself, never edits the destination body, another comment or a label, never deletes | none (diagnostic) |

`resolve` refuses `enabled = true` unless both operations are `supported`
(`emulated` is refused), and a set `destination` unless `read-records` is
`supported`; with no destination and status off the concern is not checked.
The status backend's map declares `[ids] status-destination`, the pattern a
destination must fully match. With a `[status]` table and no
`[backends.status]`, `resolve` binds the bundled `github` backend (provenance
`default`); without the table nothing about status prints.

```toml
# pack manifest.toml
[capabilities.status]
read-records = "supported"
publish-record = "supported"
# pack render/backends/<pack>.toml
[status]
read-records = "<cli> status read"
publish-record = "<cli> status publish"
[ids]
status-destination = "https://boards\\.example\\.test/[0-9]+"
```

A map command takes no `<placeholder>`; the runtime sets `MDSTACK_ROOT`
(the install) and `MDSTACK_PYTHON` in its environment. The bundled GitHub map
now has an `[ids]` table for `status-destination`; a pack map built from a
copy of it adds its own `[ids]` keys there, since TOML allows one `[ids]`
table.

### knowledge

Optional, and outside the profile: no profile binds it. A knowledge
connector reaches the owner's external notes service
([team spec REQ-17](specs/team.md#req-17-knowledge-in-external-services),
[#1229](https://github.com/mw-ding/eng-crew/issues/1229)). Its manifest may
declare this concern alone, without the core concerns. Knowledge is context
only: no verdict, marker, state tag or gate input lives there, so I5 is
unchanged. A role reaches a source only if its
[role definition](roles-registry.md#schema) lists it in `knowledge`; the
source's page pointer and the credential live in the install's private
config, never in a repo. The first backend is
[Notion](backends/notion.md). Search, the third operation in
[portable spec P3](specs/portable.md), is not declared yet.

| Operation | Guarantee | Protects |
|---|---|---|
| Read | Returns the declared source's current content into a local file that git ignores, with the source's last edited time | REQ-17 |
| Propose edit | Records the proposed text where the owner accepts or declines it; never changes the source itself | REQ-18 |

## Capability declaration

A backend declares every operation above, one line each:

```text
<concern>.<operation>: supported
<concern>.<operation>: emulated (<how>)
<concern>.<operation>: unsupported
```

Rules:

- An operation not declared counts as `unsupported`.
- `emulated` names the mechanism and must give the same guarantee. An
  emulation that weakens the guarantee is `unsupported`.
- **Unsupported-invariant rule.** If an `unsupported` operation leaves an
  invariant it protects with no other operation in the profile that keeps
  it, the profile is **unsupported**. It is never silently weakened (portable
  spec §3). The only documented substitute is the single-identity rule below.
- **Release rule.** A profile with a `[release]` table must keep
  `release.approve-check` and `release.record-release`; if either is
  `unsupported` or undeclared, `resolve` fails closed: the profile is
  unsupported for release. Without the table the concern is not checked.
- **Release pairing.** With an external pack, `[release]` and a pack-bound
  `[backends.release]` bind together
  ([#910](https://github.com/mw-ding/eng-crew/issues/910)). `resolve`
  fails closed on a `[release]` table whose `[backends.release]` still comes
  from the bundled default while the pack's manifest declares release
  capabilities, and on a `[backends.release]` that a layer above the
  default binds to the pack with no `[release]` table. The error names the missing half and the file it
  belongs in. There is no opt-out; a binding set by any layer other than
  the default, such as an explicit `name = "github"`, is kept.
- **Status rule.** `enabled = true` in [`[status]`](profile.md#status) needs
  `status.read-records` and `status.publish-record` both `supported`; a set
  `destination` needs `status.read-records` `supported`. Without either the
  concern is not checked, so every existing profile and manifest resolves
  unchanged ([#1313](https://github.com/mw-ding/mdstack/issues/1313)).
- A declaration changes no protocol rule. The profile file that carries it is
  13.10 ([#122](https://github.com/mw-ding/eng-crew/issues/122)).

## Single-identity profile

One account acts for every role (the roadmap setup decided in
[#111](https://github.com/mw-ding/eng-crew/issues/111),
[portable spec §6](specs/portable.md#6-decisions)).

- **What breaks: I1.** Author and reviewer are the same account, so
  `review.post verdict` cannot hold literally. A backend that refuses formal
  verdicts from the change author (GitHub does) cannot post one at all, and
  `review.list verdicts` cannot tell the parties apart by account.
- **Allowed compensation.** `review.post verdict` is declared
  `emulated (COMMENT-review verdict + recorded owner merge-ok)`:
  - the verdict is a narrative post headed `<ReviewerEmoji> <ReviewerBot> · Verdict · round <k> @ <sha7>`,
    with review and validate markers and a final `pass=verdict` marker; the
    signed marker, not the account, identifies the reviewer;
  - the owner OKs each change, and the coordinator records it on the change as
    a `steer` post with `pass=steer cmd=merge-ok cmd-id=chat` at head, or an
    owner standing merge grant covers it (see Scope);
  - the synthesizer re-checks every §7 gate and lands head-pinned.
- **What still holds.** This replaces only the formal-approval gate in the
  [gate registry](protocol.md#gate-registry). Every other gate is unchanged; CI
  is never waived. I2 still holds through the engine in the markers and commit
  trailers. I4 stays a convention backed by the synthesizer's `merge` marker,
  as in [§7](protocol.md#7-merge-gate-synthesizer).
- **Events.** No verdict event fires, so the runtime wakes on its own
  re-check rather than on a verdict event.
- **Scope.** Merge permission comes from a recorded owner merge-ok per
  change, or from an owner standing merge grant recorded on the tracker for
  changes in its scope (for #110 roadmap changes, the grant on
  [#111](https://github.com/mw-ding/eng-crew/issues/111), with its listed
  exclusions). A spec change is in a grant's scope only when
  `merge_grant_scope` lists `spec` and the recorded grant authorizes spec
  coverage ([§7 spec change](protocol.md#spec-change-definition-and-spec-grant-scope)).
  A grant gives permission only, never the approval
  ([§7](protocol.md#7-merge-gate-synthesizer)). Without either, the
  compensation is absent and the profile is unsupported. Today it applies to
  #110 roadmap changes only.

## Asynchronous land (design)

**Status: active on tmux** ([#873](https://github.com/mw-ding/eng-crew/issues/873)
slices D and B1 to B4). Without a `[land]` table every backend is `sync`, the
land is the one head-pinned call in [change](#change), and
[protocol §7](protocol.md#7-merge-gate-synthesizer) applies as written. The
gate alternatives below are stated in protocol §7 and its gate registry.
Owner decisions:
[#649](https://github.com/mw-ding/eng-crew/issues/649) (2026-11-05): the
final gate check runs before queue admission, a head change triggers
re-verification, and a land that was never requested is told apart from a
failed one.

On some backends, changes open as drafts, and a land is a request into a
queue that rebases, tests and lands minutes later, or fails. A backend like
that declares an asynchronous land instead of the pack carrying its own
publish step, polling loop and written waiver.

### Declaration

The pack manifest gets an optional `[land]` table. Without it, the backend
is `sync`, and an unchanged manifest stays valid. That keeps the change
within a minor release.

| Key | Values (default) | Meaning |
|---|---|---|
| `mode` | `sync` \| `async` (`sync`) | `async`: `change.land` is a request; the final state comes from `change.land-status` |
| `opens_draft` | bool (`false`) | Changes open as drafts that cannot land until `change.publish` runs |
| `serializes` | bool (`false`) | The backend lands at most one change per repo at a time, each on the tip the previous land left |
| `tests_against_tip` | bool (`false`) | The backend tests the exact patch it lands on the current tip, and refuses the land on red |
| `change_placeholder` | placeholder name (`n`) | The token `mdstack land` fills with the change id in `change.land`, `change.land-status`, `change.read-head`, `change.read-landed` and `change.read-revision-id`, for a backend whose `<n>` names the tracker item. List it in the backend map's `[placeholders] kept` |
| `head_guard` | bool (`true`) | `change.land` refuses a moved head and carries `<head-sha>`. `false` declares that the backend has no such guard. The head is still re-read right before the request, and a stale head sends no request |
| `status` | table (none) | Native `land-status` output to state: each key is a regular expression matched against the whole output, each value one of `none`, `queued`, `landing`, `landed`, `failed`. A `landed` pattern may capture `(?P<revision>...)`, and a `failed` one `(?P<reason>...)`. Without a revision group, `change.read-landed` prints the landed revision |

`resolve` fails before dispatch when `async` is declared with
`change.land-status` unsupported, when `opens_draft = true` is declared with
`change.publish` unsupported, or when `serializes`, `tests_against_tip` or
`opens_draft` is true under `sync`. It also fails when `head_guard = false`,
`change_placeholder` or `status` is declared under `sync`, when a `status`
value is not one of the five states, and when a `landed` pattern has no
revision group and `change.read-landed` is unsupported. `mdstack land` refuses
a `change.land` without `<head-sha>` unless `head_guard = false`. With
`status` declared, output that no pattern matches, or that more than one
matches, is unknown. A runtime without an async binding
(Grok Bot today) refuses `async` the same way. The new operations are
conditional: a `sync` manifest never needs them.

### Operations

| Operation | Guarantee | Protects |
|---|---|---|
| Publish (`publish`) | Makes a draft change reviewable and landable; running it again is harmless; supplies no approval, verdict or gate | I5 |
| Land, async (`land`) | A request pinned to the given head that returns at once. It is refused if the head moved. A repeated request for the same change and head never lands twice | I3, I4 |
| Land status (`land-status`) | For a change and head, returns `none` (never requested at this head), `queued`, `landing`, `landed <full revision>` or `failed <reason>`; a head change while queued ends in `failed` | I3, I4 |

An unreadable or malformed status is unknown, never `none`, and is never
taken as permission to request again.
A backend whose CLI prints its own words maps them with `[land.status]`
above. The read-landed operation (`read-landed`) prints the full landed revision of a
landed change, for a mapping that cannot capture it.

### Synthesizer loop

1. **Final gate check before admission.** Re-check every §7 gate at the
   pinned head right before the request, as for a sync land. Publication
   satisfies "not draft" and nothing else.
2. **Intent first.** Record a land intent keyed by change and head in
   runtime state, read `land-status`, and request only on `none`. A lost
   acknowledgement is resolved by reading the status again, never by a
   blind resend. On `none` after a lost acknowledgement, the gate check
   reruns before the next request.
3. **Poll.** Read `land-status` every `land_poll_interval` seconds (profile
   option, default 60) until `landed` or `failed`, or until `land_timeout`
   (default 3600, at least the interval). Both options are optional and
   validated as positive integers.
4. **Record.** Only `landed` posts `merge`, with `sha=` the checked head and
   the landed revision named, which may differ from the head after a backend
   rebase. Default-branch CI is then checked at the landed revision, as after
   a direct land. `failed`, a timeout and an unknown status report
   `blocked:` and post no `merge`. A timeout keeps the intent, so a later
   `landed` still gets its record.
5. **Restart.** On every wake, read `land-status` for each recorded intent
   before anything else. `queued` or `landing` resumes polling, and `landed`
   posts a missing record. Neither requests the land again.
6. **Head change.** A new head ends the old request (`failed`). The new head
   needs every §7 gate again, a fresh verdict or verdict portability
   included, before a new intent.

### Gate alternatives

A bare `async` changes no gate: the synthesizer holds the land lock from the
final gate check until the terminal status and the `merge` post, and
tested-with-`<default-branch>` must hold at the request as today.

- **C7.** With `serializes = true`, the backend meets
  [C7](runtimes/README.md#c7-serial-land) itself and no local land lock is
  taken. The runtime contract table declares this in the gap format.
- **Tested with `<default-branch>`.** With `tests_against_tip = true`, the
  backend's land check meets the gate for the exact patch it lands. The
  synthesizer runs no update-from-base and builds no train. `mdstack train`
  refuses with a reason that names `land.tests_against_tip`. The merge record
  names the backend check and the landed revision. A backend rebase that
  changes the patch must fail the land, not change it.

The tested with `<default-branch>` gate registry row and the tmux runtime
contract's C7 row name these backend alternatives. No merge-ok or standing
grant substitutes for either flag, and CI is never waived.

### GitHub

GitHub stays `sync`: its manifest gets no `[land]` table, and every GitHub
render stays byte-identical.

### Slices

| Slice | Paths | Adds |
|---|---|---|
| B1 | `scripts/crew-config.py`, `docs/profile.md` | `[land]` schema, conditional operations, `land_poll_interval` and `land_timeout`, the `resolve` refusals |
| B2 | `scripts/crew.d/land.py` (new), `dev/tests/environments/test-crew-land.py` | Request and status handling: queued to landed, failed, timeout, stale head, lost acknowledgement |
| B3 | `scripts/crew.d/land.py`, protocol §7 | Persisted intent, restart read-back, the merge record's landed revision |
| B4 | `scripts/crew-render.py`, tmux builder and synthesizer templates, `scripts/crew.d/train.py`, protocol §7 and the gate registry | Rendered `<op:change.publish>`, `<op:change.land>` and `<op:change.land-status>` steps when async (the sync render stays byte-identical), no-lock and train refusal under the flags |

## Stack land

**Status: active on the session runtime** (#1605). Session lands go one per
run, and merge trains are tmux-only. A backend whose review tool lands a
linear stack of changes atomically, with CI on the combined result, may bind
that operation instead, so a milestone's stack lands in one request. Without
the binding nothing changes.

### Declaration

Four optional keys join the `[land]` table above. They are independent of
`mode`: a `sync` backend may declare a stack land beside its individual
land.

| Key | Values (default) | Meaning |
|---|---|---|
| `stack` | bool (`false`) | The backend lands a linear stack atomically through `change.land-stack`, read back by `change.stack-status` |
| `stack_tests_against_tip` | bool (`false`) | The stack land tests the combined stack on the current tip and refuses on red; its readback names the check |
| `stack_status` | `stack` \| `per-change` (`stack`) | `per-change` reads the stack back from each member's `change.land-status`, mapped by `[land.status]` (with `change.read-landed` for a revision it does not capture), instead of `change.stack-status` (#1722) |
| `stack_separator` | `" "` \| `","` (`" "`) | Joins the member ids in `<stack-changes>` and the revision ids in `<stack-revisions>`; `","` passes a review tool whose stack-land flag takes one comma-separated list a single argument. `<stack>` stays space-separated (#1956) |

`resolve` fails when `stack = true` is declared with `change.land-stack`
unsupported, or with its readback unsupported: `change.stack-status`, or
`change.land-status` under `per-change`. It fails when
`stack_tests_against_tip = true`, `stack_status` or `stack_separator` is
declared without `stack = true`, and when `per-change` is declared with
`stack_tests_against_tip = true`, since three landed statuses are no receipt
of a combined test. A `sync` stack binding may declare `change_placeholder`,
which fills every per-member stack command; `[land.status]` is valid under
`sync` only with `per-change`. The operations are conditional, so a
manifest without `stack` never needs them. Only the session runtime renders
or runs the stack land; `mdstack land stack` refuses a tmux profile.

### Operations

| Operation | Guarantee | Protects |
|---|---|---|
| Land stack (`land-stack`) | One atomic request for the stack in `<stack>`: space-separated `<change>:<head-sha>` pairs, base first. Refused, landing nothing, if any member's head moved. All members land, or none. A repeated request for the same stack never lands twice | I3, I4 |
| Stack status (`stack-status`) | For the stack in `<stack>`, one line per member in stack order: `<change> none`, `queued`, `landing`, `landed <full revision>` or `failed <reason>`. With the combined-stack check run, a last line `check <reference>` | I3, I4 |
| Read revision id (`read-revision-id`) | For a change and `<head-sha>`, the backend's immutable revision id of that head, one token; refuses any other head. Needed only by a `land-stack` naming `<stack-revisions>` | I3 |

Instead of `<stack>`, `land-stack` may name the stack the way a review tool
does: `<stack-top>` (the last member's id, the representative change),
`<stack-changes>` (member ids, base first, joined by `stack_separator`) and
`<stack-revisions>` (each member's revision id, same order). A request must
carry `<stack>` or `<stack-revisions>`, so it is pinned to the checked heads,
and the backend refuses it when any member's revision id is no longer
current. Each id must be one token of letters, digits and `._:+@-`, checked
before it is substituted. `mdstack land stack` reads the ids at each
member's checked head and records them in the intent before the first
status read; a rerun or resume uses the recorded set, never a new one. A
revision id is request metadata: `sha=` and `landed=` stay full hashes.

Atomic means every member reads the same state. A missing, extra,
reordered or malformed member line, or members in different states, is
unknown: never `none`, never permission to request, never a merge record.
Under `stack_tests_against_tip`, a landed readback without its `check` line
is unknown, since the declaration alone is no receipt of the combined test.
`stack-status` uses the core grammar above. Under `per-change`, each
member's mapped `land-status` stands in for its line with the same rules:
every member in one state, or unknown. Queued beside landing is unknown in
this mode, so the pass records nothing and keeps the intent for resume;
the legacy readback still polls that pair.

### Synthesizer loop

1. **Every member's gates.** Check every §7 gate for every member at that
   member's own head. One failing member refuses the whole stack, and no
   request is sent.
2. **Intent first.** `mdstack land stack --stack <n>:<head-sha>,...`
   records one intent for the stack (with any revision ids), reads
   `stack-status`, or each member's status under `per-change`, and requests only
   when every member reads `none` and `change.read-head` still returns each
   member's checked head. A lost acknowledgement is read back, never resent.
3. **Poll and record.** It polls as for an asynchronous land. On a complete
   landed readback it prints one merge record line and marker per member,
   each with that member's landed revision, and, when declared, the
   combined-stack check. Default-branch CI is then checked at the last
   member's landed revision. `failed` drops the intent; a timeout or an
   unknown state keeps it.
4. **Restart.** `mdstack land resume` reads every stack intent back and
   never requests; `mdstack land stack-done` clears a landed one after the
   merge posts.

### GitHub

GitHub declares no stack land: its manifest has no `land.stack`, and every
GitHub render stays byte-identical.

## Bindable sensitivity (design)

**Status: in effect** ([#880](https://github.com/mw-ding/eng-crew/issues/880)
slices B1 to B3); the [protocol](protocol.md#sensitive-class) holds the
operative rule. Owner
decision ([#649](https://github.com/mw-ding/eng-crew/issues/649),
2026-11-05): a pack binding can add matches but never remove built-in ones.

An org that keeps its sensitivity policy in its own source (ownership files,
a policy registry) binds that check as an extension. The built-in classifier
always runs, and the extension can only add to its result.

### Declaration

`classify` is an optional concern with one operation, `sensitive`, like
[release](#release). Without a `[backends.classify]` table there is no
extension, every existing manifest and profile stays valid, and
classification is today's.

| Operation | Guarantee | Protects |
|---|---|---|
| Classify sensitive (`sensitive`) | An extension command that reads the classifier's input on stdin and prints the [shared JSON result](profile.md#content-rules-879); core adds its matches to the built-in ones and never lets it remove one | I4 |

I4 because the land reads the sensitive label.

A pack binds it in three places:

```toml
# pack profile.toml
[backends.classify]
name = "<pack>"
# pack manifest.toml
[capabilities.classify]
sensitive = "supported"
# pack render/backends/<pack>.toml
[classify]
sensitive = "<cli> policy classify --stdin --json"
```

`resolve` fails when `[backends.classify]` names a backend whose
`classify.sensitive` is not `supported` (the bundled `github` declares no
extension), when the backend map has no `[classify] sensitive` command, or
when that command holds a placeholder. `emulated` is refused: an extension
either runs or does not. `resolve` prints the bound command with its
`pack:<name>` provenance.

### One entry point

`<op:classify.sensitive>` always renders the core entry
`core/crew-config.py sensitive`, whatever the backend. The renderer never
substitutes a backend map's `[classify] sensitive` value into a brief, so no
pack can replace the core run. The three rendered call sites
(`templates/runtimes/tmux/builder.md`, `templates/runtimes/tmux/coordinator.md`,
`templates/runtimes/grok-bot/builder-b1.md`) use the token and keep their own
arguments around it, so the default render is byte-identical to today's.
`templates/triage-flavor.md` is read unrendered, so it names the core
command itself.

### Union, fail-closed

`core/crew-config.py sensitive` (its runner may move to a
`scripts/crew-sensitive.py` helper with #879):

1. Validates the resolved profile. Invalid configuration exits 1 before any
   classifier runs, as today. Missing or incomplete diff input under
   [content rules](profile.md#content-rules-879) exits 3 and runs no
   extension.
2. Runs the built-in path rules (mandatory defaults plus profile `paths`)
   and any content rules.
3. With an extension bound, runs its command through `sh -c` in the current
   directory, with the same stdin bytes (the path list, or the diff under
   `--diff`), the inherited environment and a 120-second limit. The
   extension never sees the built-in result.
4. Adds each extension path match to `matches`, its rule names prefixed
   `<pack>:` so the record shows the source, and each extension `content`
   record to `content`, with the same prefix on `rule`. Results are sorted
   as in the shared contract.
5. Counts the extension as failed on a nonzero exit, a timeout, stdout that
   is not one JSON object, `label` other than `null` or `crew:sensitive`, a
   `matches` that is not an object of path to rule-name lists, a malformed
   `content` record, or `label = "crew:sensitive"` with no match to record.
   Unknown fields are ignored. A failure adds one line to `errors` naming
   the pack and the cause, with no extension matches.
6. Sets `label` to `crew:sensitive` when `matches`, `content` or `errors`
   is nonempty. Exit is 0 for every result from a valid configuration,
   including a failed extension.

So an extension negative never clears a built-in positive, and a broken
extension reads as sensitive, never as clean. `errors` is present only when
an extension is bound: `[]` after a clean run. Without an extension the
output and exit codes are byte-identical to today's.

### Slices

| Slice | Paths | Adds |
|---|---|---|
| B1 ([#961](https://github.com/mw-ding/eng-crew/issues/961)) | `scripts/crew-config.py`, `docs/profile.md` | Optional `classify` concern, the backend-map command lookup and fold, the `resolve` refusals |
| B2 ([#962](https://github.com/mw-ding/eng-crew/issues/962)) | `scripts/crew-config.py` or `scripts/crew-sensitive.py`, their tests | The union runner: built-in positive with extension negative, extension-only positive, failure, malformed JSON, no extension, shared content records |
| B3 ([#963](https://github.com/mw-ding/eng-crew/issues/963)) | `scripts/crew-render.py`, the three rendered call sites, protocol Sensitive class | The fixed token value, the call sites on the token, the operative protocol wording; default render byte-identical |

## Rebase update from base

**Status: active** ([#874](https://github.com/mw-ding/eng-crew/issues/874):
design slice D, schema B1, briefs, protocol wording and train refusal
B2+B3). A backend with no `[strategy]` table updates by merge, and
[change](#change) and the [protocol](protocol.md) apply as written. Owner
decision 3 on
[#649](https://github.com/mw-ding/eng-crew/issues/649) (2026-11-05): rebase
is allowed only with the guarantee that every earlier head stays readable,
merge stays the default, rebase disables trains, and there is no weaker
emulated mode.

On a VCS that forbids merge commits, where the review backend keeps every
uploaded version of a change, the only update is to rebase and upload. Such a
backend declares that strategy instead of the pack declaring
`change.update-from-base` `unsupported`, or `emulated` with a guarantee the
[capability rule](#capability-declaration) forbids weakening.

### Declaration

The pack manifest gets an optional `[strategy]` table. Without it, the
backend updates by merge, and an unchanged manifest stays valid. That keeps
the change within a minor release.

| Key | Values (default) | Meaning |
|---|---|---|
| `update_from_base` | `merge` \| `rebase` (`merge`) | How `change.update-from-base` makes the new head |
| `retains_prior_heads` | bool (`false`) | The review backend keeps every earlier head of a change readable, by full revision, for as long as the change record exists |

`validate` and `resolve` refuse `rebase` without `retains_prior_heads = true`,
and `retains_prior_heads` under `merge`. The table is the only way to
declare a rebase: an `emulated` note on `change.update-from-base` that
describes a rebase is `unsupported`. The backend map binds the commands as
today, for example
`update-from-base = "<cli> rebase --onto <default-branch> && <cli> upload <change-id>"`.
`resolve` exposes the resolved strategy to the renderer, the precheck and
`mdstack train`.

### Guarantees under `rebase`

| Operation | Guarantee | Protects |
|---|---|---|
| Push | Uploads a new head as a new version of the same change; every earlier head stays readable on the review backend | I3 |
| Update from base | Rebases the change onto the given base and uploads the result as a new head; earlier heads stay readable; stacked children are restacked onto the new head and uploaded with it | I3 |

"Never rewrites shared history" protects I3: every verdict, marker and proof
stays checkable against the head it names. Under `rebase`, retained heads
give that protection instead, so a new version replaces the tip only through
the bound `push` or `update-from-base` upload, never a raw force-push to a
ref that does not retain. Under `merge` the no-force-push and
no-shared-branch-rewrite rules apply unchanged. A GitHub repo that requires
linear history needs no rebase: that rule governs the default branch, and
the squash land already keeps it linear.

### Protocol under `rebase`

- **Hard rules.** "Merge-up uses a merge commit or the backend's
  update-branch" reads "update from base by the declared strategy"; the
  no-force-push rule names `merge` backends.
- **Precheck step 1.** An unpublished change still rebases. A published
  change uses the declared update, "rebase onto `<default-branch>` and
  upload" under `rebase`, and merge-up under `merge`. The precheck marker's
  `rebase=` field is unchanged.
- **Verdict portability.** Unchanged. The synthesizer compares B→H with the
  updated base→updated head by `mdstack content` with all four SHAs. H stays
  fetchable because the backend retains it; an unfetchable H blocks the
  carry. A conflict or a differing patch goes to the builder, whose signed
  conflict note records both pairs, then to delta review and validation.
  Each restacked child is its own base-update push.
- **Markers.** `pass=merge-up`, the merge-up ack and every other marker
  name stay. Only the rendered instruction text changes.

### Briefs

The renderer picks the update wording from the resolved strategy: "rebase
onto `<default-branch>` and upload" under `rebase`, and merge-up under
`merge`, through `<strategy:merge>` and `<strategy:rebase>` template lines
and the `<tested-update>` placeholder
([templates](../templates/README.md#placeholders)). That covers the
generated precheck step, the builder's and solo briefs' merge-up and
no-rebase lines, the synthesizer's tested-with-default-branch row and its
one-at-a-time land under `rebase`, and the Grok Bot builder and synthesizer
briefs. The PR conventions included from [roles](roles.md) keep their
shared-branch force-push ban, which the bound upload never breaks. Every
GitHub render stays byte-identical.

### Trains

`mdstack train build` and `mdstack train bisect` stack merge commits, so they
refuse on a `rebase` backend before creating any worktree, branch or change,
with a reason that names `strategy.update_from_base = "rebase"`. The
synthesizer lands ready changes one at a time: the declared update,
required CI green at the new head, verdict portability, then the
head-pinned land. A backend that declares
[`tests_against_tip`](#asynchronous-land-design) meets
tested-with-`<default-branch>` itself. No local train is offered as a
fallback.

### GitHub

GitHub stays `merge`: its manifest gets no `[strategy]` table, and every
GitHub render stays byte-identical.

### Slices

| Slice | Paths | Adds |
|---|---|---|
| B1 [#951](https://github.com/mw-ding/eng-crew/issues/951) | `scripts/crew-config.py`, `docs/profile.md` | `[strategy]` schema, the `validate` and `resolve` refusals, the resolved strategy in metadata |
| B2 [#952](https://github.com/mw-ding/eng-crew/issues/952) | `scripts/crew-render.py`, tmux builder, solo and synthesizer templates, Grok Bot briefs, `docs/roles.md`, protocol hard rules, precheck and portability | Strategy wording in renders, a rebase-backend render fixture, the operative protocol text |
| B3 [#953](https://github.com/mw-ding/eng-crew/issues/953) | `scripts/crew.d/train.py`, `docs/runtimes/tmux.md` | The early `train build` and `train bisect` refusal |

Tests: `dev/tests/core/test-crew-config.py` (default, refusals, metadata),
render tests (rebase fixture, unchanged GitHub bytes), `dev/tests/environments/test-crew-train.py`
(refusal before any side effect) and `dev/tests/environments/test-crew-content.py`
(identical and differing patch pairs across a rebase).
