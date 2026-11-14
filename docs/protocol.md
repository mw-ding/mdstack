# Stage protocol

> **Two copies, kept in sync (spec R4).** The box skill `eng-pr-pipeline` is the
> **live** copy the bots load. This document is the **reviewed** copy. Any
> change to one must be mirrored to the other in the same change, through a PR
> in this repo plus a matching edit to the box copy. See
> [the spec](specs/framework.md).

One [tracker item](concepts.md#tracker-item--milestone--board) → one branch →
one [change](concepts.md#change) → one squash merge. Each stage is woken by a
[wake event](concepts.md#wake-event) (on Grok Bot, a GitHub-triggered routine
on that bot; see the
[runtime binding](runtimes/grok-bot.md#wake-wiring-event-to-consuming-role)),
does its job through fresh workers, and leaves its result **on the
[backend](concepts.md#backend)** (GitHub today: state tags, markers, a verdict)
so the next stage can read it. Nothing important lives only in a bot's chat.
On Grok Bot, a per-repo wiring doc (trigger JSON per bot) lives in the shared
state dir at `<state-dir>/<owner>__<repo>/wiring.md`.

Engines, tiers, worker briefs, branch naming, PR body sections, worktree
isolation and cleanup are covered by the roles doc
([roles.md](roles.md), worktree isolation in
[Worker isolation](roles.md#worker-isolation-worktrees); the box skill is
`eng-crew-roles`). This document adds the stage
protocol on top of it. For a shorter overview with a diagram, see
[architecture.md](architecture.md).

**Hard rules, everywhere:**

- Reviewer engine ≠ builder engine (the engine that actually wrote the round),
  except under the [quota diversity waive](roles.md#quota-diversity-waive);
  reviewer identity must still differ from the builder / author of the
  [change](concepts.md#change).
- Never `--no-verify`.
- On a `merge` backend, never force-push a shared branch.
- Update from base by the backend's declared
  [strategy](interfaces.md#rebase-update-from-base) (`merge` by default).
  Under `merge`, merge-up uses a merge commit or the backend's update-branch
  ([GitHub update-branch](backends/github.md#land-and-merge-up)), never a
  shared-branch rewrite. A backend may perform a clean rebase at land when
  [verdict portability](#verdict-portability-and-delta-re-review) is proved.
  Under `rebase`, the change is rebased onto the base and uploaded as a new
  head through the bound `push` or `update-from-base`; every earlier head
  stays readable on the review backend, and nothing is pushed to a ref that
  drops them.
- Squash-merge only.
- Only the synthesizer merges.
- `crew:sensitive` requires the owner's per-change merge-ok; no standing grant covers it.
- Eng workers never use Cursor CLI.
- One [verdict](concepts.md#verdict) per [change head](concepts.md#change-head) (a clean merge-up after changes gets a merge-up ack instead; see [Duties on wake](#6-duties-on-wake-all-roles)).
- Max 3 verdict rounds and ≤3 CI-fix attempts per change.
- Workers never post to a [backend](concepts.md#backend) (GitHub today); only
  role bots post.

Placeholders: `<owner>/<repo>`, `<state-dir>`, `<default-branch>`,
`<author-login>`, `<reviewer-login>`, `<user-logins>`, `<CoordinatorBot>`,
`<BuilderBot>`, `<ReviewerBot>`, `<SynthesizerBot>`.

<a id="1-roles-and-github-identities"></a>

## 1. Roles and identities

See [architecture.md](architecture.md) for the identity model. How each role
selects its identity on a backend is in the backend binding
([GitHub backend](backends/github.md#identities)).

"Woken by" names today's [wake events](concepts.md#wake-event); how the
runtime delivers each one is in the runtime binding
([Grok Bot wake wiring](runtimes/grok-bot.md#wake-wiring-event-to-consuming-role)).

| Role | Woken by | Owns | Identity |
|---|---|---|---|
| Coordinator (also **steering dispatcher**) | The user ([owner channel](concepts.md#owner-channel)), escalations, `pr-merged`, `pr-comment` / `inline-review-comment` | Spec, [tracker items and board](concepts.md#tracker-item--milestone--board), escalations, next assignment, `/crew` commands | Author identity (`<author-login>`); reviewer identity (`<reviewer-login>`) for steering signals |
| Researcher | The coordinator's message | Research notes for specs; no changes unless asked | Author identity |
| Builder | `issue-assigned`, `review-changes-requested`, `ci-failed` | Branches, commits, changes, fix rounds, conflict resolution | Author identity |
| Reviewer-validator | `pr-opened`, `new-head`, `review-requested` | Review pass, validation pass, the one verdict | **Reviewer identity** (`<reviewer-login>`), which must differ from the change author ([why, on GitHub](backends/github.md#identities)) |
| Synthesizer (sole landing decision-maker) | `review-approved`, `ci-passed` (with approval at head) | Merge gate check, land rules and merge trains, serial squash [land](concepts.md#land), update-branch of changes that are behind ([land and merge-up on GitHub](backends/github.md#land-and-merge-up)) | Author identity (later: its own identity, such as a GitHub App) |

The bots share accounts, so **the account cannot tell bots apart**. A bot
action's identity comes from its **signed [marker](concepts.md#marker)**, not
the account (see [Marker conventions](#4-marker-conventions)).

## 2. Stages

1. **Spec (coordinator + user, researcher on demand).** The coordinator writes
   `docs/specs/<topic>.md` plus incremental sub-specs (one per buildable
   slice, a slice being one unit of work, not a line budget), lands them through a `crew:spec` change (review pass only, merges
   on `/crew merge-ok`), then opens one
   [tracker item](concepts.md#tracker-item--milestone--board) per slice. Each
   item body: goal, numbered testable acceptance criteria, out-of-scope, spec
   link, role + tier hint, dependencies (`Depends on #n`;
   [linkage on GitHub](backends/github.md#linkage)). Add each item to the
   board. Items follow the work-unit rule ([roles](roles.md)):
   one issue per feature, fix or design, one PR per issue, split into
   logical commits. Heavy research goes to the researcher in the background so the
   coordinator keeps talking with the user.
2. **Handoff.** The coordinator adds the `crew:ready`
   [state tag](concepts.md#state-tag) and assigns the tracker item to the
   author identity. The assignment (`issue-assigned`) wakes the builder.
3. **Build.** The builder fans out one worker per tracker item (see
   [Duties on wake](#6-duties-on-wake-all-roles)). The worker builds, follows
   the [builder pre-review check](#builder-pre-review-check), and opens a **non-draft** change that links the item
   (`Closes #n`, or a release cut's `Release issue: #n`;
   [linkage on GitHub](backends/github.md#linkage)) with the
   evidence body ([Evidence requirements](#3-evidence-requirements)). The builder tags it
   `crew:in-review`, then attaches and verifies the per-change watch its
   runtime requires (except lighter-lane changes), as the runtime binding
   states ([Grok Bot verified hand-off](runtimes/grok-bot.md#verified-hand-off);
   [§6](#6-duties-on-wake-all-roles)).
4. **CI (parallel with review).** The [CI signal](concepts.md#ci-signal)
   must settle green before merge. A red signal (`ci-failed`) wakes the
   builder (fix on the same branch, up to the effective CI-fix cap, then escalate). On
   tmux, the coordinator holds it while a pass runs and hands the builder
   both CI failures and review findings together. A green signal (`ci-passed`)
   lets the synthesizer retry a pending merge; it never starts review.
5. **Review pass.** Each new change head (`new-head`, opened or pushed)
   starts review immediately, alongside CI. A fresh worker reviews code,
   design and implementation
   against the change body **and** the tracker item/spec.
6. **Validation pass.** Only if review passed and the effective flavor requires
   validation ([§3](#change-flavor)); otherwise record the authorized skip.
   When required, a *separate* fresh worker that
   has **not** seen the review gathers its own evidence (checks out head,
   reruns acceptance tests, exercises each criterion, re-derives numbers) and
   judges whether the builder's evidence matches the spec.
7. **Verdict.** The reviewer-validator submits **one verdict per change
   head**: pass (`APPROVE`) iff review = pass and (validation passed or was validly
   skipped under §3), else
   changes requested (`REQUEST_CHANGES`) (a clean merge-up after changes gets
   a merge-up ack instead; see [§6](#6-duties-on-wake-all-roles)). **A failed
   validation pass can never become a pass verdict (`APPROVE`)**: the reviewer
   may not override it, and if the fail looks wrong, it posts
   `REQUEST_CHANGES`, followed by escalation at the effective verdict-round cap, and flags it to the
   coordinator. The body carries the review section, the validation section (or
   "skipped: review failed") and the verdict marker with the round number.
   State tag → `crew:approved` or `crew:changes`. How a verdict is posted on
   GitHub: [GitHub backend](backends/github.md#review-types-and-the-events-they-fire).
8. **Iterate.** A changes-requested verdict (`review-changes-requested`) wakes
   the builder, which relaunches a worker on the same branch with the findings.
   Push → CI and step 5 in parallel. Max effective `caps[0]` verdict rounds (default **3**); a
   `REQUEST_CHANGES` at that cap escalates
   ([Rounds and escalation](#5-rounds-and-escalation)).
9. **Merge.** A pass verdict (`review-approved`) wakes the synthesizer, which
   picks a [land rule](#land-rules-and-merge-trains), checks the gate
   ([Merge gate](#7-merge-gate-synthesizer)) and lands the change by
   squash-merge, serially, alone or in a merge train. After a lone land, or
   once a train ends, it surveys other ready changes. Base synchronization
   happens at land, with verdict portability for identical patches; conflicts
   or changed patches go to the builder for delta re-review.
10. **Close-out.** The land (`pr-merged`) wakes the builder (clean worktree)
    and the coordinator (tick the board item, unblock dependents, assign the
    next `crew:ready` tracker item, file the soft-finding follow-up (§6)).

### Builder pre-review check

When the profile's `builder.precheck.enabled` is true, before handing off an
initial build, the builder runs these steps in order. When disabled or omitted,
existing builder duties apply without this additional check or marker.
Commands and the per-command fix limit come from
[`builder.precheck`](profile.md#builderprecheck); `max_fix_attempts` defaults to two.

1. **Fresh base.** Fetch the current `<default-branch>` and rebase the private,
   unpublished branch onto it. On conflict, abort, report to the coordinator
   and stop. For an existing change, use the declared update instead: merge-up
   under `merge`, where the no-rebase and no-force-push rules for shared
   branches still apply, or "rebase onto `<default-branch>` and upload" under
   `rebase`.
2. **Lint / format.** Run the repository's configured lint and format commands.
   Allow at most `max_fix_attempts` bounded auto-fix attempts, rerunning the check after each.
3. **Tests / build.** Run relevant tests and the configured build, including
   the checks CI runs. Allow at most `max_fix_attempts` fix attempts per failing check and
   rerun it after each. Gather typed runtime evidence during these runs, per
   [verification.md](verification.md), and paste key command/output excerpts.
   With a configured `owners` query, classify each changed path with
   `precheck-scope` ([profile](profile.md#builderprecheck)) and run the
   owning targets. Unowned code fails the step and a query failure stops
   it; neither is ever `n/a`. A path absent at head is `removed`, not
   unowned, and adds no targets.
4. **Self-review.** Check the diff against every acceptance criterion, scope
   and repository rules. Publish only the result, never the self-review
   reasoning, so the independent reviewer is not anchored by it.
5. **Docs / changelog.** Update required docs and the changelog. If this or
   self-review changes the diff, rerun affected checks before handoff.
6. **Evidence.** Confirm required typed proof collected during testing is
   embedded inline in the change body or signed fix / ci-fix reviews. Record
   a reasoned N/A for docs-only or other exempt shapes. Check each claim
   against the [claim scope](verification.md#claim-scope) rules: a claim no
   wider than its read, equivalence cases for a changed validator, and a
   changed fail-closed tool refusing through its shipped entry point.
7. **Handoff.** Commit the final tested state and open the non-draft change with
   the per-step results and precheck marker below. After a fix or merge-up,
   refresh the results for the new head in the signed fix or merge-up note;
   never edit the original change body.

Never delete or loosen tests, lint configuration or checks to get a pass.
After the bounded attempts, report a remaining failure to the coordinator
and stop the handoff. These local attempts do not change verdict-round or
CI-fix caps. Commands come from the repository or its external pack; the
core protocol names no organization-specific tools. A command step with no
configured command is `n/a`, never `pass`; state the reason inline.

**Marker schema.** Put this additional hidden line in the initial change body
before the builder signature (or in the later signed narrative note):

```text
<!-- crew:v1 role=builder pass=precheck issue=<item id> sha=<40-char head sha> round=n/a verdict=n/a rebase=<pass|fail|n/a> lint=<pass|fail|n/a> tests=<pass|fail|n/a> build=<pass|fail|n/a> self-review=<pass|fail|n/a> docs=<pass|fail|n/a> evidence=<pass|fail|n/a> -->
```

`issue=` is the tracker item's id, the GitHub issue number by default
([id keys](#precheck-and-selfgate-id-keys)).
Each step field is required. `pass` means completed successfully on this
head, `fail` means attempted but unsuccessful, and `n/a` means inapplicable
with an inline reason. `rebase` records fresh-base synchronization (merge-up
for an existing change). List the commands, key outputs, N/A reasons and
typed inline proof labels alongside the results; retain the existing
builder engine marker. `sha` binds the results to the final full head SHA;
a result for an older head does not describe the current change.
With `owners`, `tests=n/a` only when every changed path is no-owner-ok or
removed (absent at head). With a mix, `tests` is `pass` or `fail` from the
owned code paths, and the no-owner-ok paths are listed beside the marker.

**Drawbacks and limits** (decision [#160, row 8](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531125583)
and [row 11](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6531918771)):

- A checklist can be skipped; a marker is a report, not independent proof.
- It delays the first change and costs more tokens, especially for trivial work.
- Self-review shares the builder engine's blind spots and can give false
  confidence; publish results only and keep independent review and validation.
- Auto-fix can mask a defect; the prohibition on weakening checks still applies.
- Local lint/tests duplicate CI and environments can drift; CI is authoritative.
- Repositories must supply commands; missing commands are explicit N/A results.

**Pre-review gate.** When enabled in the resolved profile, before starting any
review, validation or merge-up re-check, and again immediately before landing
(each train member too), read the change body and builder-signed narrative
reviews. Require the latest `role=builder pass=precheck` marker at the full
current head SHA, with all seven step fields `pass` or reasoned `n/a`.
Missing, stale, malformed or failed results block. A newer failed marker at
head supersedes an earlier pass. Check N/A reasons inline; a marker alone
is not independent proof. Run the helper from the installed mdstack tree with the resolved project
profile (and `--org-profile` when that layer is configured):

```sh
gh pr view <n> --json body,reviews,headRefOid | python3 scripts/crew-precheck.py --project <project> --item <item id>
```

`--item` is the item the change closes; omit it when the change links no
item or several ([id keys](#precheck-and-selfgate-id-keys)).

The helper exits 1 on a blocked marker and 0 on pass/disabled; callers still
verify N/A reasons and owner steering independently. A failed fetch is not a
passing report. Disabled or omitted `builder.precheck.enabled` adds no gate.

The reviewer reports the blocker to the coordinator without starting a pass,
posting an intake-start ack or consuming a verdict round. The synthesizer
lists it in gate-status and does not land. The builder refreshes the report
in a signed note at head after bounded fixes, including after a fix or merge-up;
re-read the live record when it arrives. Fail-open is only the owner's recorded
per-change `merge-ok` at this head, verified through the existing steering
path; standing grants never waive this check. This waives only the precheck
gate, never CI, ownership or another merge gate. The marker supplies no approval.

### Precheck and selfgate id keys

> **Status: in effect** (#876, owner decision 6 on #649), built by B1 (#957)
> and B2 (#958). The `[ids]` declaration itself comes from #875: until a
> backend map declares it, every id is all digits and `marker_key` is
> `change`, so GitHub markers and results are unchanged.

**Why.** On a backend whose item and change ids are not integers, such as a
tracker item `OPS-1042` and a review-backend change `D4711`, the helper
refuses every `issue=` and `pr=` value, so the pre-review gate blocks every
land. A backend with no separate change number has no `pr=` value to write.

**Id patterns.** The helper reads the one
[ID declaration](handoff.md#id-declaration) that #875 adds: `ids.item` from
the tracker backend's map and `ids.change` from the change backend's map,
each a full-match pattern loaded by `resolve`. The helper keeps no regex of
its own. A map with no `[ids]` table keeps today's check, all digits, so no
GitHub record that passes today fails.

**Marker key.** The change backend's `[ids]` table may also declare which
id keys the selfgate record:

```toml
# <pack>/render/backends/<name>.toml (the change backend's map)
[ids]
change = "D[0-9]+"
marker_key = "item"   # "change" (default) | "item"
```

| `marker_key` | Use |
|---|---|
| `change`, the default and the behaviour when absent | The selfgate record keys on `pr=<change id>`, as today |
| `item` | For a backend with no separate change number: the selfgate record keys on `issue=<item id>` and carries no `pr=` |

`resolve` reads `marker_key` only from the map bound to `backends.change`,
refuses any other value, and, as for the patterns, a profile layer cannot
set it. It prints `ids.marker_key` with
`backend-map:<name>` provenance, as for the patterns.

**Field sets.** Each hidden line carries exactly one key field. Every id is
compared as a string after a full match, so a malformed foreign id never
reaches a numeric conversion.

| Marker | `marker_key = change` | `marker_key = item` |
|---|---|---|
| `pass=precheck` | `issue=<item id>` matching `ids.item`; other fields as today | The same; a `pr=` field is refused |
| `pass=selfgate` | The §3 field set exactly, with `pr=<change id>` matching `ids.change` | The §3 field set exactly, with `issue=<item id>` matching `ids.item` in place of `pr=` |

A duplicate field, a missing key field, the other mode's key field
(`issue=` on a change-mode selfgate, `pr=` on an item-mode one) or a value
that fails its pattern is a malformed marker and blocks. The other fields,
full-head binding, newest signed builder record, the seven step results,
selfgate count bounds and engine-diversity checks are unchanged.

**Independent key.** The helper compares the key field with a current id
the caller knows from outside the marker, never with the marker's own
value:

| Argument | Meaning | When absent |
|---|---|---|
| `--item <id>` | The tracker item the change is linked to (on GitHub, the issue it closes) | Precheck in change mode keeps today's shape-only check. An item-mode selfgate blocks: `missing item key` |
| `--change <id>` | The change under check | The record's `number` field, as in the documented `--json number,...` read. With neither, a selfgate blocks: `missing change key` (today it fell back to the marker's own `pr=`) |

The argument must match its pattern too; a bad argument exits 1 before any
record is read. A key field naming another item or change than the
argument blocks: `marker for <value>, expected <id>`. `mdstack train`'s
selfgate consumer passes the ids it already holds from its live view (B1).
The rendered builder, reviewer and synthesizer briefs pass `--item` with the
item the change closes, when it links exactly one.

**Out of scope.** The helper still reads the GitHub-shaped record
(`gh pr view --json body,reviews,headRefOid`); packs on other backends keep
translating their reads into that shape. A backend-neutral input built from
`markers.read` and `change.read-head` is a separate card if wanted.

**Compatibility.** Optional `[ids]` keys and optional arguments only. With
them absent, GitHub markers, fixtures, helper output and exit codes are
unchanged, except that a selfgate read with no `number` and no `--change`
blocks instead of passing on the marker's own value; every documented
selfgate read supplies `number`. No marker, field, label, command or exit
code is removed or renamed. Historical GitHub markers keep `issue=<n>` and
`pr=<n>`.

**Gate contract (for B1).** The precheck and express self-gate rows of the
[gate registry](#gate-registry) keep their satisfied-by, who and fail-open
columns; B1 changes only how the key field is checked, and lands with the
owner's per-change merge-ok as gate and marker work.

**Slices.** D: this note, with the §4 and reference-doc pointers. B1 (#957):
`scripts/crew-precheck.py` key checks and arguments, `environments/terminal/crew.d/train.py`
consumer, `dev/tests/scripts/test-crew-precheck.py` cases: alphanumeric ids pass;
another valid item, a missing independent id, a wrong field, a bad pattern,
a stale head and duplicate fields fail; GitHub defaults pass unchanged. B2
(#958): operative wording here and in §3/§4, `docs/express-lane.md` and the
tmux and Grok Bot builder, reviewer and synthesizer marker examples.

## 3. Evidence requirements

### Change flavor

At every wake, the builder, reviewer-validator and synthesizer read the newest
coordinator-signed item `pass=flavor` record and resolve the profile and full
diff paths at head, including both rename paths, using
`core/crew-config.py class-flavor`. Apply the knob-wise strictest of item
and path rigor, per [flavor resolution](flavors.md#resolution). No item record
means `thorough` and a `flavor-missing` report to the coordinator; a lowering
record without `Reason:` is refused and its default applies. Invalid or
unreadable resolution blocks the pass or land; never relax from partial data.
Record the effective knobs in the evidence/verdict section. A later tightening
applies immediately: an older verdict qualifies only if its recorded review,
validation and evidence still satisfy the current knobs; otherwise request a
fresh verdict. The floor, ownership, holds and CI apply to every flavor.

**Express resolution.** When the newest item record names `express` and the
change carries `crew:express`, resolve with `class-flavor --express`: the
[express](flavors.md#express) knobs apply, with `selfgate_engine` from the
profile, unless a change path at head matches a class stricter than the
project flavor on any rigor knob or cap (`lane=crew`). A tightening match, a
missing label, or an invalid or unreadable resolution resolves the normal way
and the change runs the crew lane. A `crew:sensitive` or `crew:spec` change is
never express without the owner's recorded per-item override. Builder, poll
and synthesizer read this by program at every wake, never by judgment. Only an
express change resolves `review = off`: no reviewer verdict and no validation
worker; the selfgate record (below) replaces both, under
the scoped F4, I1 and I2 exceptions in [flavors](flavors.md#scoped-express-exceptions).
The loop and routing are in the [express lane design](express-lane.md); until
its routing build issue lands, an express change is still routed to normal
review and a passing verdict satisfies §7 as usual. On Grok Bot an express
item runs the crew lane (tmux mirror deferral).

| Knob | Satisfaction rule |
|---|---|
| `review` | `full`: ranked findings and the checks below. `thin`: blocking only for an AC, a §7 gate, CI or security; other findings are follow-ups. `light`: one light pass against those same blockers. `off`: express only; the selfgate record replaces review. Review is never omitted outside express |
| `validation` | `always`: independent validation after passing review. `behaviour`: independent validation only when the full change alters observable behaviour. `off`: no independent validation worker. A permitted skip uses the section/marker rule below |
| `evidence` | `typed`: shape-specific proof per verification.md, including mutation evidence. `inline`: command/output or media excerpts supporting each AC in the body or signed builder reviews; no additional shape-specific capture is required. Both modes require proof or reasoned N/A, obey inline placement/size limits and never commit evidence |
| `caps` | First entry: verdict-round cap; second: CI-fix cap (§5), each 1–3 |
| `merge` | `per-change`: owner merge-ok at head. `docs`: a qualifying recorded standing doc-only grant, otherwise per-change. `auto`: a recorded owner project grant covering the change, otherwise per-change. The knob itself grants no authority; sensitive changes always need per-change permission, gate-contract changes need it unless a gate-contract grant (below) covers them, and so does a spec change outside the [spec grant scope](#spec-change-definition-and-spec-grant-scope) |

**Legacy grant transition.** Until follow-up B migrates legacy grants, a
recorded legacy `merge_grant` or other existing owner standing grant satisfies
merge permission within its recorded scope regardless of the `merge` knob.
This preserves current authority; the knob cannot extend the grant or create
one. Sensitive changes still require owner merge-ok at head, gate-contract
changes do unless a gate-contract grant covers them, and so does a spec change
unless the opt-in
[spec grant scope](#spec-change-definition-and-spec-grant-scope) covers it. The transition supplies no approval and
waives no other gate.

**Gate-contract grant.** A gate-contract change needs the owner's per-change
merge-ok at head, or an owner grant that is recorded, time-boxed and still
valid, and whose recorded scope explicitly names gate-contract (gate) changes.
Under such a grant the coordinator records a merge-ok at head that cites the
grant; that record satisfies per-change permission at a head with a passing
verdict and green CI. Without such a grant, per-change merge-ok is still
required. The grant supplies permission only: never approval, validation, CI
or hold clearance. It never covers a `crew:sensitive` change, a spec change
outside the [spec grant scope](#spec-change-definition-and-spec-grant-scope)
or a release cut.

**Skipped validation.** After passing review, when `validation = off`, or
`behaviour` with a justified no-behaviour change, the reviewer-validator writes
`skipped (flavor NAME)` in the Validation section, naming the effective knobs
and why the skip applies (use `mixed` when no flavor name exactly matches).
It writes the normal head/round-bound
`pass=validate verdict=pass` marker with the additional field
`validation=skipped`. This reports an authorized skip, not an independent
run; no validator worker is dispatched. Review checks required evidence
presence and AC claims in that case. A failed review skips validation with
`skipped: review failed` and produces `verdict=changes`, never this skip marker.
A failed validation cannot be relabelled as a flavor skip. §7 checks the skip
against the live resolved knobs; absent justification or an ineligible skip
blocks. Required independent engine-disagreement/rereview checks still run.

The final `pass=verdict` marker may add `flavor=NAME` when the effective rigor
equals a named preset or custom flavor. A mixed result with no exact name
omits the field and lists its knobs in the section. This field is diagnostic,
never permission or a substitute for the item record or live resolution.
Legacy markers without it remain valid when their proof satisfies current rigor.

**Change body (builder).** The description the builder writes when it opens
the change (the PR body on [GitHub](backends/github.md#linkage)). Sections
from the roles doc: `## Context` with
`Closes #n`, `## Changes Made`, `## Testing Done`, `## Test Output`, signature
last. Plus:

- `## Acceptance Evidence`: one row per acceptance criterion: criterion → how it
  is met → proof (test name + result, command + output excerpt, or screenshot,
  plus the proof label). "N/A" needs a reason. For a
  behaviour-changing criterion, name the shape (web, CLI, service, API,
  mobile) and the inline proof label, as set out in the
  [verification protocol](verification.md).
- **Inline evidence only.** All text, images and video live in the change
  body at creation or signed reviews, never in the repo or a side branch.
  CLI, API and service proof is a copyable `sh` command block followed by a
  `text` block with exit code, stdout and stderr (plus service logs or API
  status/body). For a command that only runs against test fakes, the `sh`
  block may be a named test command that invokes it and asserts its exit,
  stdout and stderr ([verification Q2](verification.md#q2-validator-reproduction)).
  Each proof cell names its block below the table and pastes
  key output. Web uses an embedded GitHub user-attachments image with route,
  viewport and capture SHA; mobile uses an image or bare video URL with
  device, build id and SHA. A path, repo-file link or media on another host
  does not count. See [verification](verification.md#inline-embedding-decisions-143)
  and the adapters for capture and reproduction.
- **Size limits.** Keep each body/review under 60,000 characters. Cut text
  over 100 lines or 8,000 characters to the command, claim-bearing lines and
  tail, marking the omission and linking the CI log at the capture SHA (or
  naming the command to re-run). The inline excerpt is durable; CI logs may
  expire. Images are at most 10 MB; videos at most 10 MB and about 60 seconds.
  Truncate rather than split evidence across extra posts.

- **Mutation evidence.** A behaviour-changing change that adds or changes a
  user-visible create, update or complete (or equivalent) mutation must
  show, in both `## Test Output` and `## Acceptance Evidence`, an inline
  happy-path snippet that creates at least one entity, progresses or
  completes (or updates) it, then deletes it (item DELETE and/or a list or
  parent DELETE with cascade) and shows it is gone (404 or absent from the
  list). An update-only change still shows the full create → update → delete
  sequence. Unit-pass lines or path pointers alone do not meet this. Example
  (generic):

  ```text
  $ curl -s -X POST localhost:8080/todos \
      -H 'Content-Type: application/json' -d '{"title":"buy milk"}'
  {"id":1,"title":"buy milk","completed":false}
  $ curl -s -X POST localhost:8080/todos/1/complete
  {"id":1,"title":"buy milk","completed":true}
  $ curl -s localhost:8080/todos
  [{"id":1,"title":"buy milk","completed":true}]
  $ curl -s -o /dev/null -w '%{http_code}\n' -X DELETE localhost:8080/todos/1
  204
  $ curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/todos/1
  404
  ```

  With lists, a list DELETE with cascade also counts. Record the child item
  IDs before the delete (`GET /lists/1/todos` → ids `2`, `3`), run
  `DELETE /lists/1` → `204`, then show the children are gone too:
  `GET /todos/2` → `404` and `GET /todos/3` → `404` (or `GET /todos` no
  longer lists them). A `404` on the list alone does not prove the cascade.

  An app with no delete endpoint shows create → progress/update and states
  in the snippet or `## Risks / Not Done` that it has no delete; the
  validator checks that claim.

  Docs-only and no-behaviour changes stay N/A with a reason. Non-CRUD behaviour
  shapes keep their existing shape-specific rules; this rule only adds
  create+progress+delete where such mutations are in scope.

- **Guard negative control (#1604).** A change that adds or changes a guard
  (a test, sweep, pattern or check whose job is to fail on a bad state)
  records a negative control for each new or changed guard: undo or mutate
  the guarded line, or feed the nearest wrong input, show the actual guard
  fail, then restore and show it pass. It goes inline in the change body or
  a signed builder fix / ci-fix note, as the
  [fail-then-pass pair](../templates/evidence/cli-exit-stdout.md#negative-control)
  of the CLI adapter. A test-only change that adds or changes a guard is not
  exempt as "no behaviour change". Under effective `evidence = typed` the
  control is required: missing, it is missing required evidence
  (`disagrees`, `verdict=changes`). Under `inline` it is a soft 🟡 finding,
  unless an acceptance criterion claims the guard catches the bad state,
  which then needs the control as its supporting excerpt. A change that adds
  or changes no guard states N/A with a reason; nothing else changes for it.
  Updating a golden or expected-output fixture in step with the output it
  pins is not a changed guard.

- **Deploy secret sync.** New deploy milestones must include an AC in the
  milestone/tracker-item ACs: before the first gated production deploy,
  assert each shared secret is equal across GitHub Actions secrets, Fly secrets, Vercel
  env and every other named host that consumes it. Verify this before
  declaring the milestone done. Name the GitHub store the workflow actually
  reads: repo-level or Environment secrets. GitHub Free-plan Path A uses
  repo-level Actions secrets when Environment protection rules (such as
  required reviewers) are unavailable on the plan/private repo. A mismatch
  between repo and Environment stores is itself drift.

  Show redactable command/output comparing SHA-256 fingerprints (or short
  prefixes), or a dashboard screenshot showing the hosts match. Never put
  plaintext secrets in the change, tracker item or `evidence/`. GitHub
  Actions secrets are write-only via API: get that fingerprint from a workflow step that
  prints only the hash, or re-set all hosts from one source in one step and
  show set timestamps/digests. Example output (fake SHA-256 prefixes):

  ```text
  NAME gh repo <app>       sha256: 012345abcdef
  NAME fly <app>           sha256: 012345abcdef
  NAME vercel <app> prod   sha256: 012345abcdef
  NAME comparison: MATCH
  ```

  Existing repos may file a soft follow-up tracker item; this is not a
  blocker for them. New deploy milestones must carry the AC. Docs-only and
  non-deploy changes stay N/A with a reason.

- `## Risks / Not Done`: known gaps, follow-ups, deliberate scope cuts.
- A hidden line right before the signature:
  `<!-- crew:v1 role=builder issue=<n> tier=<tier> engine=<engine> model=<model> -->`.
- Write the body once when the change opens. **Never edit it afterwards**:
  body edits
  rerun some CI workflows and re-wake the reviewer. Later evidence goes in a
  fix-round note.

**Evidence on the change record.** The body plus signed reviews holds the
review evidence; no review artifact is committed. Builder evidence after
creation goes in a signed fix or ci-fix review with the existing builder
marker and a full `sha=` of the head or an earlier commit of the change.
The validator confirms it still holds at the current head; the synthesizer
checks presence and that validation, without re-running evidence.

- Evidence added after a verdict without a new commit leaves the head
  unchanged and wakes nobody. The coordinator posts a rereview steer
  (`steer cmd=rereview`), with the ack and re-request mechanics in
  [Steering](#9-steering-crew-commands). A code push still wakes normal review.
- If media cannot be uploaded into a signed review, use the capture recipe
  and validator reproduction fallback in
  [verification Q1](verification.md#q1-how-bots-attach-images-and-video).
  Unreproducible evidence is `unverified`, requiring per-change merge-ok.
- Lesson record:
  [2026-11-01-inline-evidence.md](lessons/2026-11-01-inline-evidence.md), which
  supersedes [the PR-head rule](lessons/2026-10-20-evidence-on-pr-head.md).

**Typed runtime evidence.** A change that alters behaviour attaches evidence
matched to the software shape under `evidence = typed`; `inline` uses the
AC excerpts defined above. [verification.md](verification.md) states, per
shape, when evidence is required or N/A, what the builder attaches, what the
validation pass checks and when the synthesizer may merge. Docs-only changes are
N/A with a stated reason.

**Fix-round note (builder, after each push).** A
[narrative post](concepts.md#narrative-post) headed
`[<BuilderBot>/fix] round <k> @ <sha7>`: each finding → what changed (commit) → proof.
The note names the engine, model and effort that actually wrote the round, and
every commit of the round carries an `Engine: <engine> <model> <effort>` trailer.
The note's hidden line carries the engine too (same for `pass=ci-fix`):

```text
<!-- crew:v1 role=builder pass=fix pr=<n> sha=<head-sha> round=<k> verdict=n/a engine=<engine> model=<model> effort=<effort> -->
```

`<k>` is the verdict round the fix answers
([Rounds and escalation](#5-rounds-and-escalation)); a ci-fix before any verdict
uses `round=0`. See [Actual builder engine](roles.md#actual-builder-engine).

**Selfgate record (builder).** For an express change, after the
[self-gate loop](express-lane.md#self-gate-loop) passes or hits `caps[0]`, the
builder posts a narrative post headed
`[<BuilderBot>/selfgate] <pass|changes> @ <sha7>`: mode, builder and reviewer
engine and model, code-review skill, effective knobs, a checks table (check,
command, result) and a findings table (rank, `file:line`, resolution: fixed in
a commit, rejected with a reason, or a follow-up issue). Hidden line:

```text
<!-- crew:v1 role=builder pass=selfgate pr=<n> sha=<head-sha> base=<merge-base-sha> round=n/a verdict=<pass|changes> mode=<same|different> builder-engine=<engine>/<model> reviewer-engine=<engine>/<model> reviews=<k> findings=<f> open=<o> checks=<pass|fail> -->
```

`sha` and `base` are full SHAs. `round` is always `n/a`; the record is never a
§5 verdict round. `verdict=pass` only when the last review passed, no 🔴
finding is open and `checks=pass`. `mode` is the effective `selfgate_engine`.
`builder-engine` is the [actual builder engine](roles.md#actual-builder-engine)
of the head's commits; under `different`, `reviewer-engine` differs from every
builder engine on the change. The key field is `pr=<change id>`; when the
change backend declares `marker_key = item`, `issue=<item id>` replaces it
([id keys](#precheck-and-selfgate-id-keys)). `reviews` counts review
sub-sessions at this
head (1 to `caps[0]`); `findings` and `open` count 🔴 and 🟡 findings raised
and still open. The review checks evidence presence and AC claims, as an
authorized validation skip does. A CI-only fix or builder merge-up reviews only
the new hunks and posts a new record at the new head. A newer record at the
same head supersedes an older one.

**Run summary (builder).** A multi-step run (build, tests, fix attempts)
writes short step lines with `scripts/step-summary.py` and promotes the
summary in its signed narrative post (the fix, ci-fix or first builder note),
never the raw logs. Raw logs stay local under the worktree. Protocol, paths,
what the reviewer skims and the risks are in [observe.md](observe.md). A pure
docs one-shot says `N/A: no multi-step run`.

**Review section.** Verdict (`pass` / `changes`), findings ranked 🔴 blocking /
🟡 should-fix / 🟢 nit, each with `file:line` and the spec clause or
change-body claim it contradicts. Check: does it do what the tracker item
asks, does the design fit the spec, correctness, do the tests actually cover
the criteria, security, scope creep. On a multi-commit change, read the
round's commits in order and judge the combined diff at head; a commit that
breaks its own tests is a 🟡 unless it also breaks the head.

**Validation section.** Per acceptance criterion: builder's claim → validator's
own evidence (command, output excerpt, artifact) → `agrees` / `disagrees` /
`unverified`. `pass` only if every criterion `agrees` (or has a justified N/A)
and no builder claim is contradicted. List what was **not** independently
checked.
An authorized flavor skip instead uses the skipped-validation rule above;
it must not claim those checks were independently run.

## 4. Marker conventions

**Where bots write.** Bots never post plain conversation comments or inline
comments on a change
([on GitHub](backends/github.md#review-types-and-the-events-they-fire):
PR conversation comments and inline review comments); they would wake the
steering dispatcher for nothing. Bot output on changes goes in **post bodies** of two
kinds:

- A **[narrative post](concepts.md#narrative-post)**
  ([on GitHub](backends/github.md#review-types-and-the-events-they-fire),
  a COMMENT review) for ack, fix notes, merge-up, merge, cutover, escalation
  and steering acks. The author identity may post one on its own change.
- The **formal verdict post**
  ([on GitHub](backends/github.md#review-types-and-the-events-they-fire),
  a formal `APPROVE` / `REQUEST_CHANGES` review) for
  [verdicts](concepts.md#verdict) and steering signals. Cite `file:line` in
  the body instead of inline comments.
- **No bot text ever starts with `/crew`**, in any comment, post or commit
  message.

Which events each GitHub review type and comment fires, and so why bots
never post plain or inline comments: see the
[GitHub backend](backends/github.md#review-types-and-the-events-they-fire).

Every bot-authored post body starts with a visible signed header and has a
hidden machine line:

```text
[<BotName>/<pass>] <short status>
...
<!-- crew:v1 role=<role> pass=<pass> pr=<n> sha=<40-char head sha> round=<k> verdict=<pass|changes|n/a> -->
```

In **every** marker, `sha=` is the full 40-character change head SHA, never an
abbreviation. `<sha7>` is for human-readable names only (claim files, worktree
names, post headers such as `@ <sha7>`); markers always carry the full SHA.
Readers match markers on the full SHA, so a short SHA is treated as a missing
marker.

`pr=` and `issue=` carry the backend's declared change and item ids, GitHub
numbers by default. An item-keyed selfgate record carries `issue=` in place
of `pr=`. See
[precheck and selfgate id keys](#precheck-and-selfgate-id-keys) (#876).

`pass` is one of:

| `pass` | Written when |
|---|---|
| `ack` | The reviewer-validator acknowledges a newly opened change, or a clean merge-up after changes (no round, no verdict) |
| `precheck` | The builder records its pre-review step results and head SHA (schema above) |
| `review` | The review section of a verdict |
| `validate` | The validation section of a verdict |
| `verdict` | The formal verdict post; its body holds the review and validation sections, each with its own marker line |
| `hold` | The reviewer-validator holds its verdict for a user decision and adds `crew:needs-md` (narrative post; `round=n/a verdict=n/a`) |
| `watch` | The builder's parent turn confirms the per-change watch is attached (adds `watch=b2 status=attached`; see below); no round, no verdict |
| `fix` | The builder pushes a fix round |
| `ci-fix` | The builder pushes a CI fix |
| `merge-up` | The synthesizer brings a change up to date with `<default-branch>` |
| `merge` | The synthesizer merges the change |
| `escalation` | A change is escalated |
| `resume` | `/crew resume` clears a hold or escalation and resets rounds |
| `cutover` | Control of a change moves from another system to the crew |
| `steer` | The steering dispatcher acknowledges a `/crew` command (adds `cmd=<command> cmd-id=<comment id>`) |
| `selfgate` | The builder records the self-gate for an express change at head (schema in §3; no round; `verdict=pass` or `changes`) |
| `triage` | A triage sweep records its decision on a tracker item (schema below; no SHA, no round); a note, never a gate input |
| `triage-log` | A triage sweep's one comment on the day's log issue (schema below) |
| `reflection` | A reflection report's completion note on the reflection log issue (schema below); a note, never a gate input |

A merge-up ack uses `round=n/a verdict=n/a`.

The builder's watch status marker (`pass=watch`) states that the builder's
per-change watch is attached (B2 on Grok Bot, see the
[runtime binding](runtimes/grok-bot.md#verified-hand-off)). It uses
`round=n/a verdict=n/a` and adds `watch=b2 status=attached`:

```text
<!-- crew:v1 role=builder pass=watch pr=<n> sha=<full-40-char-head-sha> round=n/a verdict=n/a watch=b2 status=attached -->
```

It is posted once per change by the builder, only after it has verified the
watch (see [builder duties](#6-duties-on-wake-all-roles)). On Grok Bot the
builder's parent turn alone posts it, after verifying B2, and the builder
routine run never posts it
([verified hand-off](runtimes/grok-bot.md#verified-hand-off)). It is not a
round and not a verdict. Because it is posted once, it is a per-change fact:
its `sha=` is the full SHA of the commit that was the head when it was posted,
and readers accept it for any commit on the change.

The researcher's **triage record** (`pass=triage`) goes on a tracker item, not
a change, from an [always-on triage](triage.md) sweep. It carries no `sha=`,
`pr=`, `round=` or `verdict=`:

```text
<!-- crew:v1 role=researcher pass=triage issue=<n> decision=<outcome> priority=<P0|P1|P2|P3> mode=<shadow|apply> sweep=<sweep-id> -->
```

`decision` is the [outcome](triage.md#outcomes) slug (for example
`classify`, `duplicate`, `place`, `propose-close`, `needs-owner`,
`owner-accepted`, `owner-rejected`, `owner-adjusted`); `sweep` is the sweep's UTC start,
`YYYYMMDDTHHMMZ`. A sweep writes a new record only when the item or an owner
reply changed since the newest one, so repeated sweeps are idempotent, and
`mdstack poll` skips an item whose newest record has no later
[owner feedback](triage.md#owner-feedback) and, while unplaced, no later
owner comment.
Each sweep's one comment on the day's `Triage log YYYY-MM-DD` issue ends with
`<!-- crew:v1 role=researcher pass=triage-log sweep=<sweep-id> applied=<n> proposed=<n> skipped=<n> tokens=<n> -->`
(`tokens` is the session's count or `unknown`);
the `proposed=` sum over a day's log is the noise-cap count (10 per day), where
a [cluster](triage.md#clusters) proposal counts once. Each cluster record, one
comment on the day's log issue, ends with
`<!-- crew:v1 role=researcher pass=triage-cluster cluster=<slug> size=<n> new=<n> band=<P0|P1|P2|P3> proposed=<0|1> sweep=<sweep-id> -->`
(`new` counts members since the last sweep; `proposed` is 1 when the record
makes a new tracking-issue or milestone proposal). All three are notes, never
a verdict, gate input or permission. **Triage labels**, set
only by the sweep and never state tags: `triage:proposed` (a proposal awaits
the owner), `triage:duplicate` (an exact duplicate, linked), `triage:card-extracted`
(the sweep posted the card fields), `triage:log` (a daily log issue, skipped
by every sweep), `cluster:<slug>` (a cluster member, `apply` mode only) and the
priority bands `P0`–`P3`.

The researcher's **reflection record** (`pass=reflection`) ends each
`[<ResearcherBot>/reflection] <window-id>` report on the tracker's reflection
log issue ([reflection](self-improve.md#reflection)). It carries no
`issue=`, `pr=`, `round=` or `verdict=`:

```text
<!-- crew:v1 role=researcher pass=reflection window=<window-id> sha=<input-sha> proposals=<n> new=<n> incidents=<n> -->
```

`window` is the window ID, joined with `+` when windows coalesce; `sha` is
the full default-branch SHA the run read; `proposals` counts the report's
proposals, `new` those that count against the noise cap (at most 3), and
`incidents` the distinct incident IDs. A quiet window posts `proposals=0`.
The record marks the window's run complete; it is a note, never a verdict,
gate input or permission.

The researcher's **docs-pass record** (`pass=docs-pass`) ends each
`[<ResearcherBot>/docs-pass] <owner>/<repo> @ <sha7>` comment a
[docs pass](project-docs.md#docs-pass) posts on that repo's log issue. It
carries no `issue=`, `pr=`, `round=` or `verdict=`:

```text
<!-- crew:v1 role=researcher pass=docs-pass repo=<owner>/<repo> sha=<head-sha> findings=<n> drafts=<n> -->
```

`sha` is the full default-branch head the pass read; `findings` and `drafts`
count the comment's findings and draft issues. A quiet pass posts no comment
and no record. The record is a note, never a verdict, gate input or
permission, and filing a draft stays the coordinator's call. The log issue
carries the label `docs:log`, set only by the pass when it opens that issue
and never a state tag.

Parse **only** the hidden line (exception: to find a round's actual builder
engine, the fix note and commit trailers also count and win over the marker; see
[roles](roles.md#actual-builder-engine)). Markers are append-only; a newer SHA supersedes.

**[State tags](concepts.md#state-tag)** (no wake event fires on a state tag,
so they are safe state; on GitHub each is a `crew:*` label): `crew:ready`,
`crew:in-review`, `crew:changes`, `crew:approved`, `crew:escalated`,
`crew:needs-md` (user decision needed; coordinator or its
[sweeper](runtimes/grok-bot.md#runtime-contract) adds it,
reviewer-validator adds it for an intentional verdict hold; coordinator clears
it under §6), `crew:hold` (work roles no-op), `crew:external`, `crew:spec`,
`crew:needs-mirror` (a change touching `docs/protocol.md` or `templates/`; blocks
the merge until the box skill is mirrored), `crew:express` (express lane:
the coordinator sets it with the `express` item record; the builder removes it
on [fallback](express-lane.md#eligibility)). See
[architecture.md](architecture.md#labels) for who sets and clears each, and the
[GitHub backend](backends/github.md#labels) for colours and label events. Never
touch state tags (labels) or comment commands that belong to the product under
development.

### Ownership record

The repo's `repo.control_item` holds append-only coordinator posts. On GitHub
this is a long-lived issue locked to collaborators: read all comments with
`gh api --paginate --slurp repos/<owner>/<repo>/issues/<n>/comments`; post with
`gh issue comment <n> --body-file <file>`. These are item-level marker reads
and writes; they never reset a PR's rounds. A post has this signed header
and marker (full default-branch SHA):

```text
[<CoordinatorBot>/handoff] <state> <from> → <to> (<handoff-id>)
<!-- crew:v1 role=coordinator pass=handoff handoff=<handoff-id> state=<state> from=<runtime-id> to=<runtime-id> cmd-id=chat sha=<default-branch-head-sha> round=n/a verdict=n/a -->
```

Handoff ids are `yyyymmdd-<6 hex>`. Runtime ids are
`runtime.name@runtime.instance`. Only well-formed markers
from a profile owner or role login count, in backend post order. The first
`claimed` (`from=none`) wins; later claims are ignored. On first configured
start the coordinator reads, posts `claimed` if no record exists, then
re-reads before dispatching. `cmd-id` is `chat` or `n/a`.
`draining` or `takeover` opens one handoff only if `from` is the current owner; a second
opener is ignored. A takeover may reuse the open id, from and to when its
outgoing runtime stopped answering. Subsequent states must match all three.

| State | Ownership / allowed action |
|---|---|
| `claimed` | `to` owns and may act |
| `draining` | `from` finishes in-flight writes; no new pass or land |
| `offered`, `takeover` | In transit: nobody acts; `to` reconciles by reading |
| `acked` | First matching ack closes the handoff; `to` owns |
| `aborted` | Matching abort closes the handoff; `from` owns |
| `stopped` | Ownership unchanged |

Every role reads at wake start and again before dispatch, push, post, tag
or land. A non-owner or unreadable record is read-only: reads and reports,
never starts work, pushes, posts pass markers, tags, creates watches or
lands. The coordinator may post only its handoff-side state. No control
item or no marker preserves legacy operation. Owner commands are in
[§9](#owner-handoff-commands); resume, hold lift and prompt stop follow
[handoff](handoff.md#resume-and-reconcile).

## 5. Rounds and escalation

- **Round** = 1 + the number of reviewer-identity verdicts
  ([on GitHub](backends/github.md#review-types-and-the-events-they-fire),
  formal reviews) with marker `pass=verdict verdict=changes`, counted after
  the latest `cutover` or `resume` marker. Derived from the backend (GitHub today) each time, never
  from memory.
- At the effective `caps[0]` (default 3), a changes-requested verdict (`REQUEST_CHANGES`) (a failed
  validation pass counts as one, never as an `APPROVE`) → the
  reviewer-validator adds `crew:escalated`, posts a `[<ReviewerBot>/escalation]` narrative post (open
  blockers, what was tried, decision needed) and messages the coordinator, who
  brings it to the user over the [owner channel](concepts.md#owner-channel).
- A merge-up push uses no round. A merge-up re-approve keeps the round number
  of the approval it renews; a merge-up ack has `round=n/a`. See the
  merge-up rule in [Duties on wake](#6-duties-on-wake-all-roles).
- Builder: at most effective `caps[1]` CI-fix attempts per change (default 3),
  then the same escalation. Derive attempts from the change's CI-fix records.
  Tightening a cap never resets either count; if already exhausted, escalate
  before another attempt. Neither cap exceeds 3 or changes resume/merge-up rules.
- Sweeper (the runtime's stuck-work check; on Grok Bot the stuck-PR sweeper,
  see the [runtime binding](runtimes/grok-bot.md#runtime-contract)): after the
  third nudge for the same key with no progress, report to the coordinator.
  The coordinator adds `crew:escalated` only for a crew change in a loop and
  escalates on the backend (GitHub today) and over the owner channel under §6.
- Work roles waking on a `crew:escalated` or `crew:hold` change do nothing. The
  coordinator and its sweeper still monitor and escalate waits under §6; they
  do not restart work. Restart via `/crew resume`
  ([Steering](#9-steering-crew-commands)), which resets the round count.

## 6. Duties on wake (all roles)

Use the [orchestration cost targets and handoff hygiene](roles.md#orchestration-cost)
to reduce parent turns under the flavor `cost` goal. These diagnostic targets
change no duties, event routing, round caps or merge gates.

Every wake, in order:

1. **Ownership first:** check the [ownership record](#ownership-record).
   A non-owner reads/reports only; unreadable is read-only for this wake.
   Repeat before dispatch, push, post, tag and land. Then **re-read live state**: current [change head](concepts.md#change-head)
   SHA, [state tags](concepts.md#state-tag), posts (verdicts, steering
   signals, narrative posts), markers, not just the payload. If the event
   SHA ≠ head, or the change is
   closed, merged, `crew:hold` or `crew:escalated`, stop. The coordinator and
   its sweeper still perform the triage and owner-decision duties below on
   held/escalated items.
2. **Idempotency.** If a marker for *this pass at this head SHA* exists, stop.
   Otherwise take a claim file
   `<state-dir>/<owner>__<repo>/claims/<role>-pr<n>-<sha7>` atomically
   (`set -o noclobber` or `flock`). For the builder's tracker-item stage (from
   issue-assigned until the change opens) there is no change yet, so the claim
   is `builder-issue<n>`. If the claim exists and is under 2h old,
   stop. Delete the claim after posting.
3. **Sweep.** Also pick up other changes in the same state that missed a wake,
   up to the fan-out cap.
4. **Fan out.** One fresh worker per change or tracker item, max **5 in
   parallel per role**. Queue the rest. The role bot only briefs, collects
   results and posts markers; no coding in its own chat.
5. **Report.** Post the marker, set state tags, update the board item. Message
   the coordinator only on escalation or blockage.

**Worker heartbeat (builder).** While a builder worker is building, fixing or
fixing CI, it refreshes a `heartbeat: <UTC ISO-8601 timestamp>` line in the
claim file the role bot took in step 2 at least every **5 minutes**, and also
after each commit, push and post on the backend. The worker owns the write,
not the role bot; the worker brief must give it the absolute claim-file path
and write access to that file, since a sandboxed worker (e.g. Codex
`workspace-write`) cannot write outside its worktree by default. It is a file
write, not a backend post; its `[<BuilderBot>/<pass>]`
[narrative posts](concepts.md#narrative-post) and pushes already count as
visible activity, and no heartbeat marker is added to changes. **Silence** is
a heartbeat (or, if the line is missing, the claim file's mtime) older than
**15 minutes** while the claim still exists, for any builder claim on an open
crew change or tracker item that is not held, escalated, merged or closed
(including a ci-fix on a `crew:approved` change). The sweeper (on Grok Bot the
stuck-PR sweeper; [runtime binding](runtimes/grok-bot.md#runtime-contract))
flags it as `builder-silent` and messages `<BuilderBot>`, which checks worker
liveness, restarts the work in a fresh unique worktree and may take over a
silent claim despite the 2h rule in step 2. The sweeper's nudge cap and
escalation (§5) apply. Reviewer-validator workers are not covered here.

**Authoritative revision (#377, #376).** The backend's read head
(`change.read-head`, [interfaces](interfaces.md#change)) is a change's one
authoritative revision.

- **Writers.** After each publish or push, the builder reads the head back
  from the backend and puts that full SHA in markers, evidence headers,
  `done:` lines and handoffs. A local hash is never relabelled as the tested
  revision. If the backend head differs from the local commit (the backend
  rewrote the commit on upload, or the push did not land), proof captured at
  the local commit does not describe that head: recapture at the backend head.
- **Readers.** Each review, validate, gate or land pass reads the head once
  at its start and pins its diff, CI, verdict, merge-ok and evidence reads to
  that SHA. A local revision or a newer unpublished draft is never the head.
  If the published head changes during the pass, its observations are void:
  stop, as in step 1, and the next pass starts at the new head.

**Coordinator triage window.** The coordinator owns triage and runs a window
at least once per awake half-day (the user's awake hours in PT). Every open
tracker item leaves the window with exactly one disposition: `crew:ready`,
`crew:spec`, `crew:needs-md`, moved to the next milestone (deferred), or
closed with a reason. Resolve conflicting triage state tags. Include the
sweeper's report of open tracker items with no `crew:*` state tag older than
one awake day in the next window.

**Plan gate (#444, #396).** The coordinator creates implementation items,
adds a new `crew:ready` or dispatches a new build only for an item listed in
an owner-approved plan: a milestone (its description gives scope and order)
or a project. Ambiguous encouragement such as "start building" or "in
parallel we can start" is a request to propose a plan, never approval.

- **Plan.** The proposal lists the items, their order and dependencies, the
  engine and tier, the executor (which runtime builds it) and the owner-only
  prerequisites. Before items are derived from it, the coordinator walks the
  plan's open decisions and records each owner answer; items come only from
  settled decisions.
- **Approval record.** The owner's OK is recorded once, as a signed comment
  on the milestone's or project's tracking issue: a first line
  `[<CoordinatorBot>/steer] plan approved: <plan>`, a link to (or exact quote
  and time of) the owner's message, a link to the approved plan text, then
  the marker
  `<!-- crew:v1 role=coordinator pass=steer cmd=plan-ok plan=<milestone-or-project-id> cmd-id=<source-id> sha=<default-branch-head> round=n/a verdict=n/a -->`
  and the coordinator signature. `cmd-id` is the owner's source comment id or
  a unique chat message id; only profile owner logins count, and ignore
  records from anyone else. It covers the items the plan listed at approval;
  adding an item needs a new record. An unreadable record means no approval.
- **Later owner change.** One recorded steer on the tracking issue lists
  every affected unmerged item and its acceptance-criteria change, and the
  coordinator applies them together.
- **Exceptions.** Fix rounds, CI fixes and follow-ups on already-approved
  work (including the soft-finding follow-up below), and a trivial single
  docs item the owner explicitly asks to be built now.
- **Environment preflight.** A platform or device item (host toolchain,
  target device or OS) becomes `crew:ready` only when its spec's Target
  environment section cites dated, observed host model, OS, architecture and
  toolchain facts and the target device model and OS, with the command that
  showed each. An unknown or incompatible fact blocks readiness. The spec's
  Owner prerequisites list names every owner-only step (accounts, admin
  password, device trust, signing) with owner and deadline, and the
  coordinator asks for them in one batch. A non-platform spec states N/A
  with a reason ([spec template](../templates/spec.md)).

**Metrics gate.** When `scripts/metrics-decide.py` trips on the rollup, the
coordinator opens a `metrics-gate` tracker item in the control-plane repo and
holds new `M*` feature work (no `crew:ready`, `crew:hold` with
`hold-until-#<n>` on unstarted ready tracker items) until the harness fix
merges or the owner waives it. It is not a merge gate: open changes and the
fix merge as usual. Details, waiver and lift:
[metrics decisions](metrics/decisions.md).

**Soft-finding follow-up (after squash).** When the reviewer-validator's
pass [verdict](concepts.md#verdict) (`APPROVE`) carried soft 🟡 findings or
deferred non-blockers, the coordinator files a `crew:ready` follow-up in the
same awake window (the user's awake hours in PT), assigns it to the merged
change's author and kicks `<BuilderBot>` without waiting for a new user ask.
Respect the 5-builder ceiling and `crew:hold`. Skip if a follow-up tracker
item for that change already exists or the `APPROVE` had no 🟡/deferred
items. If the user said "defer softs" for a named
cut (for example, a milestone or release cut), park until that cut ends,
then file the follow-up and dispatch it. Soft findings never block §7 squash;
the merge gate is unchanged. Use this tracker item title and body (a GitHub
issue today):

```markdown
Title: Follow-up: soft findings from #<pr>

## Context
- Merged PR: <merged-pr-url>
- Verdict review: <verdict-review-url>
- Follow-up to #<pr> / Part of #<parent>

## Soft findings
- [ ] <file:line> — <finding>

## Out of scope
- <work excluded from this follow-up>

## Acceptance criteria
- [ ] Resolve each soft finding listed above.
```

**Self-improve intake.** Failures and near-misses become candidate cards, not
chat. The coordinator accepts or closes each card in the same triage window,
tags it `repo:` or `crew:`, and an accepted card is a normal builder tracker
item. The lesson (`docs/lessons/`, plus a findings-buffer one-liner) is the
memory; triage never edits a skill, and harness changes merge only through the
normal gate. Details in [self-improve.md](self-improve.md). For each
[reflection](self-improve.md#reflection) report the coordinator relays one
owner digest and records each proposal's disposition in this window.

**Owner decisions: one channel and a 2h SLA.** Only owner-facing seats
deliver owner asks and reports
([role classes](roles-registry.md#role-classes)). Internal staff never ask the
owner directly; they escalate along their declared path to their owning seat,
which decides or carries the ask. Technical matters go to the technical seat
(CTO). In this crew the coordinator is the team head and holds the CTO seat,
and every other role is internal staff under it, so owner asks go only through
the coordinator, posted on the backend (on GitHub, a PR review body or issue
comment) and over the [owner channel](concepts.md#owner-channel) (the
coordinator's chat with the user). Builders and reviewer-validators never ask
the user only in their own chat. If that happens, the coordinator re-posts the
ask on the backend and over the owner channel; the originating role links the
backend post from its own chat.

The coordinator monitors any `crew:hold`, `crew:escalated`, or pending
`/crew merge-ok` waiting on the user. After more than **2h of the user's awake
hours, measured in Pacific Time (PT)**, it adds `crew:needs-md` and pings the
user through that channel with: the change/tracker-item link, a one-line
question, a **recommended default**, and an **auto-apply time** (explicit date
and time in PT). This coordinator duty still runs on held or escalated items;
work roles continue to no-op. The coordinator's sweeper (on Grok Bot the
stuck-PR sweeper) performs this routine promotion only for held/escalated
changes and tracker items whose latest hold/escalation asks the user for a
decision, adding `crew:needs-md` only if absent and naming them in its summary
for the coordinator to ping. Lane/dependency holds carry a coordinator note
naming the blocking change/tracker item and are not promoted. It leaves
existing hold/escalation state tags in place. An intentional reviewer verdict
hold gets `crew:needs-md` immediately; the coordinator routes that ask through
the same channel and SLA.

At the auto-apply time, if the user has not answered, the coordinator applies
the posted default and records it on the change/tracker item. The deadline
only wakes the coordinator to apply a permitted default: elapsed time never
supplies a merge-ok. Allowed defaults are:

- **Merge:** only 🟢/🟡 doc-only changes with green CI that this
  repository's own recorded standing grant covers (§7 Merge permission), or
  that already carry the owner's per-change merge-ok at head; the coordinator
  hands the merge to the synthesizer, which re-checks every §7 gate. Without
  such a grant or merge-ok (for example under `merge_grant = "none"`), hold or
  escalate instead. Never auto-apply a merge to code, workflow, or
  `docs/protocol.md` changes.
- **Defer:** close as not planned, with a note explaining when to reopen.
- **Keep hold:** leave the item on hold and record that decision.

The coordinator clears `crew:needs-md` once the user answers or the default
is applied; it does not clear other holds merely because the SLA expired.

### Owner away mode

The owner sends `/crew away [--cap <n>] [--quiet] [until <time>] [words]` to the coordinator's
chat or through the PR steering dispatcher. The coordinator records it on
the project's tracking issue before batching notifications. Issue comments
alone do not wake a role: deliver the command through chat on that runtime.
Only profile owner logins count; ignore edits and already-recorded source ids.
`until` accepts an ISO 8601 timestamp with UTC offset; if ambiguous, ask for
clarification before entering away mode. Omitted `until` is `null`. Flags come
first; `--cap` takes an integer of 1 or more, else ask for clarification. Store the
remaining words exactly, including whitespace, using JSON escaping only.

Persist `away-control.json` containing `{"issue": N}` in the per-project
state directory (`$CREW_STATE` on tmux). It locates the tracking issue across
restarts; the signed append-only issue comments are authoritative. Re-read
them on each coordinator wake. An unreadable record requires reconciliation,
never inferred permission. Each entry has this fenced JSON record followed
by a `role=coordinator pass=steer cmd=away cmd-id=<source-id>` marker and the
coordinator signature; `sha=` is the full default-branch head and
`round=n/a verdict=n/a`. Ignore records from anyone else:

```json
{"state":"away","entry":"source-id","started":"2026-11-02T17:00:00Z","until":null,"cap":null,"quiet":false,"words":"keep #123 on hold"}
```

An entry supersedes the previous away entry without erasing it. `entry` is
the source comment id, or a unique chat message id (recorded once on receipt).
Away changes notifications, decision handling and admission capacity, never authority:
batch owner pings, but keep posting asks and closures on GitHub and tracking
their deadlines. The normal PT awake-hours SLA and allowed defaults apply
on schedule; `until` does not pause or replace that clock. Away words may
answer a specific pending question through the existing owner-decision path;
never parse them into standing grants, merge-ok, flavor acceptance or a gate
waiver. Every §7 gate still applies.

On tmux and session, owner-present admission uses `runtime.options.present_builders` and
`present_reviewers` (integers of at least 1, defaulting to the full caps;
session refuses a value above its full cap).
An active recorded non-quiet away entry uses full `builders` and `reviewers`
caps: present means owner-friendly parallelism, away means full speed within
the caps. A quiet owner remains present. Leads re-read the authoritative away
record on each admission check. Entering or leaving away mode changes admission
on the next wake without restarting sessions; never kill running workers to
meet a lower cap, let the pool drain naturally. Unreadable away state requires
reconciliation before admission.

`cap` (default `null`, no limit) bounds concurrent runs while the entry is
current. Admission only: the coordinator starts no new run while the live run
count is at or above `cap`, queues the work in its normal order, and never stops
a live run, skips a gate or changes a round cap. `quiet` (default `false`) marks
an owner who is present but wants no interruptions: it batches notifications like
away mode and keeps the normal SLA clock and defaults, and the owner's own
messages do not end it. A quiet entry ends at `until`, or when the owner sends
`/crew away --end`; either appends the `returned` record and brief below. Without
`--quiet`, `--end` is not needed.

The first subsequent owner message ends a non-quiet away mode before handling that
message, unless it is another away command. Reaching `until` only makes an away return due;
it does not prove the owner returned. On return, append
`{"state":"returned","entry":"source-id","returned":"2026-11-02T18:00:00Z"}`
with a signed `pass=steer cmd=away-return cmd-id=<return-source-id>` marker.
Send one standalone [return brief](../templates/owner-return-brief.md) in the
owner channel and on the tracking issue, covering the entry-to-return interval.
Append a signed delivery receipt with `entry` and `brief_url` on that issue
to prevent repeat briefs after restart; reconcile a pending delivery before
sending again. Copy full URLs from live
records. Include landed work, defaults applied, waiting decisions with deadlines,
and the next ask; write `None` for empty sections. Resume normal notifications.

**Standing doc-only merge-ok (user grant, 2026-10-25).** The user grants standing
merge-ok for doc-only changes with no code, no `.github/`, no `templates/`, and
no `docs/protocol.md` changes, only 🟢/🟡 findings, and green CI. The
synthesizer may merge qualifying changes without a per-change `/crew merge-ok`.
This substitutes only for that per-change permission: all other §7 gates still
apply, including review and validation approval. The lighter-lane exemptions
below apply to the builder watch and mirror hold. Spec changes still require
the user's per-change merge-ok.

**Lighter lane.** A change qualifies if it touches only docs, with no code, no
`.github/`, no `templates/**`, and no `docs/protocol.md` changes. The builder
installs no per-change watch (B2 on Grok Bot) and posts no `pass=watch`
marker; `crew:needs-mirror` never applies. Green CI and the usual
reviewer/validator pass (a pass verdict, `APPROVE`) are still required, with
per-change or standing merge-ok as applicable. The standing grant supplies
permission only; the user's per-change merge-ok has its usual §7 override
semantics.

Grok Bot runtime: how fixes, red CI and cleanup reach the builder without B2
is in [lighter-lane routing](runtimes/grok-bot.md#lighter-lane-routing).

**Per-PR watches (routine limits).** Grok Bot runtime: see
[per-PR watches](runtimes/grok-bot.md#per-pr-watches).

**The hand-off is verified, not fire-and-forget.** Grok Bot runtime: see
[verified hand-off](runtimes/grok-bot.md#verified-hand-off).

**Comment reviews do wake comment listeners.** Grok Bot runtime: see
[comment-listener wakes](runtimes/grok-bot.md#comment-listener-wakes).

Further duties:

- **Label hygiene.** Whoever sets `crew:approved` or `crew:changes` (the
  reviewer's verdict pass) removes `crew:in-review` in the same step. The same
  verdict pass adds `crew:needs-mirror` to a change that touches
  `docs/protocol.md` or `templates/`, and does so **before** posting the
  verdict, because `review-approved` wakes the synthesizer at once and the hold
  must already exist. A re-review skips re-adding the state tag when the
  coordinator's mirror comment is already on the change and is newer than the
  last commit touching `docs/protocol.md` or `templates/` (nothing
  mirrored-relevant changed since the mirror); if a later commit changed those
  paths, it re-adds the state tag. Lighter-lane changes never get
  `crew:needs-mirror` ([mirror hold gate](runtimes/grok-bot.md#mirror-hold-gate)).
- **Box-skill mirror.** The coordinator deploys the rendered output for the
  live profile to the live dir (and, for a `docs/protocol.md` change, edits the
  `eng-pr-pipeline` box skill), then runs the drift check at the change head
  ([mirror hold gate](runtimes/grok-bot.md#mirror-hold-gate)). Only on a clean
  result does it post the box-skill mirror comment (for example
  `[Ash] box skill mirrored`) with the command and output inline, remove
  `crew:needs-mirror` and then ping `<SynthesizerBot>`, because state tag
  changes wake nobody.
  Re-confirm duty: if a later commit changes `docs/protocol.md` or `templates/`
  after the mirror comment, the state tag is re-added and the coordinator posts
  a fresh mirror comment and removes the state tag again. Lighter-lane changes
  have no box-skill mirror hold.
- **Unique worktrees.** Every worker run uses its own directory
  `<worktree-root>/<pr>-<sha7>-<role>-<pass>/` (see the roles doc). Never share
  `<worktree-root>/<branch>` across runs; a mid-pass delete of a shared tree is
  unsafe even if the review falls back to a code trace.
- **Worker toolchain.** Builder and fix workers pin the repo's required
  toolchain (e.g. Node version on `PATH`, `COREPACK_HOME`) before any commit or
  push, so pre-push hooks don't fail on the box's defaults.
- **Default-branch CI.** If the default branch runs CI on push, the
  coordinator also wakes on a red [CI signal](concepts.md#ci-signal) on the
  default branch (on Grok Bot, its after-merge routine listens for `ci-failed`
  with `ciBranch` set to the default branch), and files a `crew:ready` fix
  tracker item instead of touching the default branch.
- **Repo tracking.** Every crew repo requires milestones (M1, M2, …) and a
  board ([on GitHub](backends/github.md#tracking), GitHub Milestones and a
  GitHub Project board); the coordinator resolves missing setup using the
  onboarding runbook. Closed milestones are frozen: no new tracker items;
  follow-ups go to the next `M*`. Board and linkage mechanics:
  [GitHub backend: Tracking](backends/github.md#tracking).

Role specifics:

- **Builder / `issue-assigned`.** Needs `crew:ready` and no open change or
  branch for it already. Skip `crew:solo`: the owner's session builds/fixes
  and the coordinator posts findings, CI and conflict refs on the PR for pickup.
  Pick role, tier and engine per the roles doc. After
  the change opens: tag it, add it to the board, attach the per-change watch
  the runtime requires, verify it and post the full-SHA `pass=watch` marker.
  On Grok Bot that watch is B2 (`ci-failed`, `review-changes-requested`,
  `pr-merged`, `pr-closed`), and the parent turn alone verifies it, records the
  routine folder id and posts the marker
  ([verified hand-off](runtimes/grok-bot.md#verified-hand-off)).
  Lighter-lane changes skip watch attachment, verification and the marker;
  fixes and cleanup arrive by message as described in
  [lighter-lane routing](runtimes/grok-bot.md#lighter-lane-routing).
  - **`review-changes-requested`:** relaunch on the same branch, preferably the
    same engine; post `fix` after pushing.
  - **`ci-failed`:** ignore cancelled or superseded runs; fix real failures on
    head; post `ci-fix`.
  - **Conflicts** handed over by the synthesizer: merge `<default-branch>` in
    with a merge commit, resolve, push.
  - **`pr-merged` / `pr-closed`:** delete the worktree and build output.
- **Reviewer-validator / `pr-opened`.** Post an `ack` narrative post, attach
  the reviewer's per-change watch for `new-head`, `review-requested`,
  `pr-merged`, `pr-closed` (Grok Bot still uses `ci-passed` in place of
  `new-head` until mirrored; [declared gap](runtimes/grok-bot.md#review-start-gap)), tag external changes
  `crew:external`. Skip the ack on drafts. When posting its first verdict on a
  crew change outside the lighter lane, if no builder `pass=watch` marker (full
  40-char SHA of any commit on the change, not only the head) is on the
  change, the reviewer (on Grok Bot, its parent turn) pings `<BuilderBot>`
  with priority to attach the watch and post the marker, and tells
  `<CoordinatorBot>`. The reviewer never creates the builder's watch. The
  synthesizer also holds the merge until the marker is present
  ([builder watch gate](runtimes/grok-bot.md#builder-watch-gate)), unless
  exempt. Do not ping for a builder watch on lighter-lane or `crew:solo` changes.
  - **`new-head` (opened or pushed):** review engine ≠ the builder's (the
    engine that actually
    wrote the round under review; see [roles](roles.md#actual-builder-engine)).
    The [quota diversity waive](roles.md#quota-diversity-waive) permits a
    matching engine for one round's verdict; reviewer identity must still differ.
    Review, then validation, without waiting for CI. Both passes record the
    observed CI state as information only; CI state alone never fails an
    acceptance criterion or changes a verdict. Independently reproduced
    failures remain findings. CI green at head stays a §7 merge gate.
    - **Intentional verdict hold.** If the verdict must wait for a user
      decision, add `crew:needs-md` and post a narrative post headed
      `[<ReviewerBot>/hold] @ <sha7>` naming the open item and decision needed,
      with marker
      `<!-- crew:v1 role=reviewer-validator pass=hold pr=<n> sha=<full-40-char-head-sha> round=n/a verdict=n/a -->`.
      This is neither a verdict nor a round. Route the ask via the coordinator
      under the owner SLA above; do not leave the wait only in chat. A failed
      validation still requires `REQUEST_CHANGES`; a hold cannot override it.
      When the user answers, the coordinator clears `crew:needs-md` and posts
      the [rereview steer marker](#3-evidence-requirements), then
      [re-requests review](#9-steering-crew-commands). The marker plus the
      review request wakes the reviewer to review, validate and issue the verdict.
    - **CI fix after approval.** The pushed head starts a light re-check in
      fresh review and validation sessions: inspect the CI-fix hunks and rerun
      acceptance checks. Record CI as information only. If clean, post the
      normal pass verdict with both pass sections at the new head using the
      approval's round number. Broader behavioural edits require normal review;
      independently reproduced failures require a changes verdict as usual.
      This is no per-PR CI-only path: approval and all §7 gates still apply.
    - **Base-update push.** A tool-performed merge-up or clean rebase of a
      previously approved change goes to the synthesizer for
      [verdict portability](#verdict-portability-and-delta-re-review), not a
      new review session merely because its SHA changed. No round is consumed
      for identical content. If the previous verdict requested changes, a
      clean update gets only the existing `pass=ack round=n/a verdict=n/a`
      merge-up ack; findings remain open. A conflict or differing patch goes
      to the builder, then review and independent validation of the delta,
      producing a new head-pinned verdict under the normal round cap.
  - **`review-requested`** for the reviewer identity with a `steer cmd=rereview`
    marker newer than the last verdict: fresh full review and validation at
    head, even if the head is a merge-up (the merge-up shortcut applies only to
    `new-head` wakes).
- **Synthesizer / `review-approved`, `merge-up`, or `ci-passed` with a
  passing verdict at head or a candidate portable verdict.** Synchronize the
  base at land, prove identical content and check every live gate; a candidate
  alone supplies no approval. Stop on a conflict or differing patch and route
  to the builder. Survey other ready changes after landing; do not send
  builders or reviewers work solely because a change is behind.
- **Coordinator / `pr-merged`.** Update the board, advance the parent
  sub-spec, tag and assign the next unblocked tracker item. Escalations from
  others arrive as messages.
- **Coordinator / steering dispatcher.** When evidence changes without a new
  head commit, post the rereview steer
  ([Evidence requirements](#3-evidence-requirements)).

## Protocol freeze

`docs/protocol.md` and `templates/` change only in milestone batches for the
open `M*`. A lesson found mid-milestone is filed as a tracker item on the next
milestone, rather than merged as a one-off protocol change. The exception is a
fix for a gate that is blocking merges right now; that fix must follow the gate
contract below.

The M2 success drill (issue #52) verifies this freeze, SLA and triage batch
end-to-end; it is not itself a protocol change.

## Gate contract

Any new or changed merge gate must state in the same change:

- What satisfies it: the exact marker, state tag (label) or check.
- Who can satisfy it and how fast.
- Its fail-open path if it cannot be satisfied. The default is the user's
  per-change `/crew merge-ok`, or the standing doc-only merge-ok from §6 where
  applicable.

A gate with no fail-open path is not merged. Fail-open must respect §7: it is
not a blanket waiver. Where no override exists, use the §6 owner-decision
path: the coordinator escalates, adds `crew:needs-md` after more than 2h of
awake hours PT, and posts a recommended default and auto-apply time. The user
can decide how to resolve the blocker, defer/close, or keep hold. An allowed
default may apply at that time; it never clears another gate or hold by itself.
CI is never waived by merge-ok: failed checks need a fix or a decision to
defer/close, not a merge through red CI.

### Gate registry

This table summarizes the §7 gates; their detailed conditions and exemptions
remain in §7, or, for a runtime gate, in the runtime binding §7 links. The
owner-decision path below means the §6 SLA above, not permission to merge with
an unsatisfied gate. **Binding** says where the gate's satisfaction rule is
stated: `core` (this protocol), `runtime` (the
[runtime binding](runtimes/README.md)) or `backend` (the backend binding). Every
gate applies whatever its binding.

| Gate | Satisfied by | Who / how fast | Fail-open | Binding |
|---|---|---|---|---|
| Owning runtime | Record names this instance with no open handoff, or no record exists; unreadable blocks | Coordinator posts the owner's command; synthesizer re-reads before land | Owner aborts or commands takeover; no merge-ok or standing-grant waiver | core |
| Formal approval at head or portable verdict | Reviewer-identity formal approval (`APPROVED`): `pass=verdict verdict=pass` with review + validate pass markers at head (validation may be a justified §3 flavor skip), or at verified H after a clean tool update with identical patch and CI green at the updated head; `pass=steer cmd=merge-ok` remains head-pinned | Synthesizer proves patch identity at land; conflicts or differing patches go to builder then reviewer for delta re-review and a new head-pinned verdict | User's per-change `/crew merge-ok`; standing permission alone never supplies approval; unreadable identity proof blocks carry | core |
| Express self-gate (replaces formal approval for express changes) | Effective flavor `express` by §3 express resolution, with `crew:express` on the change; the latest builder `pass=selfgate verdict=pass` at the full head SHA, or at verified H under verdict portability, whose `mode` is the effective `selfgate_engine` and, under `different`, whose `reviewer-engine` differs from every builder engine on the change; not `crew:sensitive` and not a [spec change](#spec-change-definition-and-spec-grant-scope) unless the owner's recorded per-item override; CI green at head; merge permission per the effective `merge` | Builder before PR open and after every push (minutes); synthesizer re-reads live immediately before each land | Owner's per-change `/crew merge-ok` at head, or the crew lane: drop `crew:express` and route normal review and validation. Never a CI waiver | core |
| Merge permission | Effective `merge` (§3), with existing recorded owner standing grants preserved within their scope regardless of the knob until follow-up B migrates them; sensitive changes require per-change permission; gate-contract changes do too unless a §3 gate-contract grant (recorded, time-boxed, scope explicitly naming gate changes) covers them, with the coordinator's merge-ok at head citing it; and so does a spec change unless the [spec grant scope](#spec-change-definition-and-spec-grant-scope) covers it | User via coordinator; standing grant immediately if qualified, otherwise §6 SLA | Standing grant where applicable; otherwise owner-decision path | core |
| No later changes request or hold/escalation | No later reviewer-identity changes request (any `REQUEST_CHANGES`: a changes verdict or a steering signal such as `steer cmd=rework`); no `crew:hold` / `crew:escalated`, unless user's per-change merge-ok | Reviewer resolves findings; coordinator dispatches user steering under §6 SLA | User's per-change `/crew merge-ok`; `/crew resume` clears hold/escalated and re-kicks the stage, but supplies no approval | core |
| Engine disagreement resolved | Note/trailer wins; fresh review + validation verdict at head on an engine different from the actual builder, after `steer cmd=rereview`. An open rereview at the current head blocks squash until that verdict lands; `merge-ok` and a prior `APPROVE` do not satisfy it | Coordinator steers; reviewer-validator on `review-requested` | Owner-decision path; no `merge-ok` or standing-grant waiver of the re-check | core |
| No open project landing stop | No unmatched coordinator `pass=steer cmd=stop-landing` in the recorded landing control or candidate change reviews; re-read before every direct land or train member | Coordinator records incident/owner stop and explicit release; synthesizer checks live records | Recorded `cmd=resume-landing stop-id=<stop cmd-id>` for each stop; no urgent, merge-ok or standing-grant waiver | core |
| No project pause | No project pause barrier in the runtime's state; an unreadable one counts as a pause. The land and train paths refuse before taking the land lock and again under it | Owner asks the coordinator to pause or resume; synthesizer and train re-read the barrier before each land | Only the owner's explicit resume; no merge-ok or standing-grant waiver | runtime ([tmux](runtimes/tmux.md#mdstack-pause)) |
| No open coordinator hold | No explicit hold-until-X or crew hold command on the change or in the synthesizer inbox; it overrides standing doc-only merge-ok until the hold clears or dependency X lands | Coordinator posts and clears the hold; synthesizer re-reads the change and inbox right before merging | Coordinator releases the hold or the dependency lands; owner-decision path if neither; no standing-grant waiver | core |
| Required evidence | For a behaviour-changing change, proof required by effective `evidence` (§3) is inline in `## Acceptance Evidence` or `## Test Output` of the body, or a builder-signed fix / ci-fix review whose marker `sha=` is the head or an earlier commit of the change, and validation at head (or verified H under verdict portability) says `agrees`, or review checks presence/claims with a justified §3 validation skip; or a reasoned N/A. Text is a repro pair or fenced block; media is a GitHub user-attachments URL, or the capture recipe plus validator reproduction fallback ([verification Q1](verification.md#q1-how-bots-attach-images-and-video)). Paths, repo-file links and other media hosts do not count. Docs-only and no-behaviour changes are N/A; lighter-lane changes are N/A unless they change behaviour | Builder at creation or in a fix-round review; reviewer-validator on `new-head` / rereview; synthesizer re-reads body and reviews just before merging (seconds) | User’s per-change `/crew merge-ok` for `unverified`, including impossible embedding; standing doc-only grant never covers behaviour changes; owner-decision path for disputes; no waiver of CI | core |
| Builder pre-review check | When enabled, latest builder `pass=precheck` at full head SHA with all seven steps `pass` or reasoned `n/a`; disabled/omitted exempt | Builder before handoff and after every fix/merge-up; reviewer before any pass, synthesizer immediately before each land | Owner’s recorded per-change `/crew merge-ok` at head only; no standing-grant or CI waiver | core |
| Builder watch | `role=builder pass=watch watch=b2 status=attached`, full SHA of any commit on the change; external, cutover, coordinator-opened spec, crew:solo and lighter-lane exemptions per the [builder watch gate](runtimes/grok-bot.md#builder-watch-gate) | Builder parent turn right after the change opens, after verifying B2 | Synthesizer pings builder with priority; builder attaches/posts, tells coordinator if unable; unresolved blocker goes through owner-decision path, with no new watch waiver | runtime ([Grok Bot](runtimes/grok-bot.md#builder-watch-gate)) |
| No mirror hold | Path-derived: for `docs/protocol.md` or `templates/`, no `crew:needs-mirror` and a coordinator mirror comment newer than the last touching commit, recording the rendered output deployed to the live dir and a clean drift check at that commit (`check-skill-drift.py` exit 0: no `DRIFT`, `MISSING` or `EXTRA`; `WORDING` allowed), command and output inline; or, on tmux only, a profile-named recorded owner standing mirror deferral whose source the synthesizer reads and whose scope covers this PR, with no live Grok Bot behaviour change, named in the merge record ([tmux](runtimes/tmux.md#mdstack-train)); on tmux, profile `runtime.options.mirror = "none"` resolves the gate to `n/a`, named in the merge record as `Mirror: n/a (profile)` ([tmux](runtimes/tmux.md#no-live-copy-to-mirror-877)); lighter lane exempt ([mirror hold gate](runtimes/grok-bot.md#mirror-hold-gate)) | Reviewer tags before verdict; coordinator deploys, runs the check (seconds), posts the comment, removes state tag and pings synthesizer on its next turn after the verdict | Owner-decision path if the deploy or a clean check cannot be completed; tmux may use only the recorded scoped mirror deferral above, which supplies no merge permission; no standing merge-grant waiver | runtime ([Grok Bot](runtimes/grok-bot.md#mirror-hold-gate)) |
| Tested with `<default-branch>` | The head contains the current `<default-branch>` tip, or the change is the next member of a green merge train whose tested state is the current `<default-branch>` (the train base, then the commit the previous member's land made), at the head the train tested; that member's merge record cites the train branch, SHA and CI run; or tmux `lone_pr_land="direct"` with exactly one ready PR and the waiver named in its merge record ([land rules](#land-rules-and-merge-trains)); or, backend alternative, an asynchronous land whose backend declares `land.tests_against_tip = true`: its land check tests the exact patch it lands on the current tip, and the merge record names that check and the landed revision ([asynchronous land](interfaces.md#asynchronous-land-design)); or a session stack land whose backend declares `land.stack_tests_against_tip = true` and whose readback names the combined-stack check, named in each member's merge record ([stack land](interfaces.md#stack-land)) | Synthesizer at land time: update-branch, then CI (minutes) and every gate again at the new head; or one train CI run for all members | Only `lone_pr_land="direct"` with exactly one ready PR waives this gate (record it), and only `land.tests_against_tip` on an asynchronous land meets it by the backend (no update-branch or train, and `mdstack train` refuses); otherwise update-branch applies; a real conflict goes to the builder; owner-decision path if neither resolves it; no merge-ok or standing-grant waiver, since it guards CI on the landed result; differing patches route through builder and delta re-review | core |
| CI and change state | All required checks green at head; not draft, mergeable, base = `<default-branch>` | CI normally minutes; builder fixes CI (effective `caps[1]`, at most 3 attempts) and conflicts; author corrects draft/base | CI-fix cap then escalation → user decision (fix, defer/close); merge-ok never waives CI. Unresolved change state also uses owner-decision path | core |
| Linked issue | `Closes #n`; spec, external and cutover exemptions; a release cut change instead names exactly one same-repo release item in the release-only non-closing form (`Refs #n` plus a whole line `Release issue: #n`, no closing keyword for it), closed by the release run after publication ([release steps](release.md#steps)); never auto-close umbrella or TRD | Builder when the change opens; correct linkage before merge; a missing, ambiguous or foreign release item, or a closing keyword for it, fails the cut's release check, which names the correction | Owner-decision path if linkage cannot be resolved; no new exemption | backend ([GitHub linkage](backends/github.md#linkage)) |
| Release approval (guards publishing, not merging; §7 does not check it; [design](release.md#release-gate)) | The owner's per-change `pass=steer cmd=merge-ok sha=<head>` marker at the landed cut change's head, or the coordinator's `cmd-id=release-delegation` merge-ok there while the owner-set profile key `runtime.options.release_delegation` is not `none` ([release delegation](release.md#release-delegation)), verified by the backend's `release.approve-check` ([interfaces](interfaces.md#release)) on the landed cut change before `release.record-release` writes the release id, with release validation green, required CI green at the landed cut revision (missing, red, cancelled or pending past the bound refuses) and the publishing actor matching the configured release owner (checked first, so a wrong actor fails before validation). Landing the cut change starts validation and the CI wait, then recording the release id and notifying in one run; the standing merge grant never covers a cut change, and a recorded release delegation never covers a `crew:sensitive` cut or waives the actor check, CI, validation or a hold. Shared owner-level accounts ([merge enforcement](merge-enforcement.md)) mean the actor check alone cannot distinguish a bot from the owner: no role invents owner authorization. A manual run remains for dry runs and an owner-only fallback with the same approval and actor check | Owner on the cut change before landing, on the coordinator's ask under the §6 owner SLA; approve-check verifies before the release id is written | None for publishing: no standing merge grant or auto-applied default publishes a release; a recorded release delegation is the owner's go, not a fail-open. The §6 owner-decision path may only defer or cancel it | backend (`release` concern; bindings in [release operations](release.md#release-operations)) |

## Sensitive class

At triage and PR open (and after each push), the coordinator or builder runs
`python3 core/crew-config.py sensitive --project config.toml` with the full
repo-relative diff paths on stdin, including both old and new rename paths.
At triage use the paths explicitly named by the issue, with `--paths-only`;
the PR check uses the actual diff. Apply `crew:sensitive` to the item/change when a path matches,
recording the matched paths and rules on the tool of record. An issue already
labelled sensitive transfers that label to its PR. Defaults cover CI/release
workflows, auth, secrets, permissions/access control, migrations and deletions;
[profile additions](profile.md#sensitive) extend them.

With [content rules](profile.md#content-rules-879) configured, the PR check
classifies the change's diff instead (`sensitive --diff`): the builder pipes
`git diff --no-color --no-renames origin/<default-branch>...HEAD` from its
checkout, and a role without one pipes the backend's `change.read-diff`
([interfaces](interfaces.md#change)). Triage classifies named paths with
`--paths-only`, path rules only, since an issue has no diff. Record each
content match as rule, path, side and line beside the path matches. Exit 3
(missing or incomplete diff) blocks classification like exit 1; neither is a
clean result.

Only the owner may override the classification: record their words and reason
on the item/change before clearing the label. Re-check on every push; a prior
override covers only its recorded path matches and its recorded content
matches by rule and path, so line moves stay covered. A new path, or a rule
and path pair it does not name, found on any push, needs the owner's
reconsideration before the label is cleared again. The synthesizer reads the
current label and the owner record; it never reclassifies at merge time.

With a pack's [sensitivity extension](interfaces.md#bindable-sensitivity-design)
bound (#880), the same command also runs it and unions its matches, recorded with
their `<pack>:` rule prefix. Nonempty `errors` (the extension failed, timed
out or printed an unreadable result) applies `crew:sensitive` like a match;
record the errors with the matches. An extension never clears a built-in
match. An owner override covers the matches and errors it records; a new
extension match, or any extension error on a later push, needs the owner's
reconsideration before the label is cleared again. Briefs reach the command
through `<op:classify.sensitive>`, which always renders this core entry, so
no pack replaces the built-in run.

## Solo coding-agent lane

Use solo for attended deep work in one owner-driven coding session; use the
full crew for queued work with managed builders. The owner decision for #102
is options 1 + 3: lane/label rules and a shared-source session brief. Thin
listen needs no separate tmux wiring: the poller already routes new PR heads
to independent review.

The coordinator records the choice and sets `crew:solo` on the issue and its
PR. This is the runtime selector for `builder = solo`; item flavor records
remain the rigor audit trail in [flavors](flavors.md#resolution). The label
alone changes no rigor knob or merge permission. The coordinator and builder
lead skip builder dispatch, merge-up/conflict and fix/CI routing for a marked
item. The session owns those tasks; findings and red CI refs go on the PR for
pickup. Label reads include linked issues and occur before dispatch/delivery.
Removing the label returns builder routing to the full crew after the
coordinator records the handoff; never run two builders on the item.

No B2 watch is installed for a solo item. Independent reviewer approval,
engine diversity, issue linkage, inline evidence (including mutation proof),
F1–F7 and the synthesizer's §7 squash gate remain required. Holds and round
caps still apply. The [solo brief](roles.md#solo-session) shares the builder's
PR and fix contract; the original PR body is never edited.

## 7. Merge gate (synthesizer)

All of these must hold **at the current head SHA**, re-checked right before
merging:

- The ownership record names this runtime with no open handoff, or no record
  exists. An unreadable record blocks land. Neither merge-ok nor a standing
  grant overrides this gate.

- A formal approval from the reviewer identity at head, or a passing verdict
  carried from verified H under [verdict portability](#verdict-portability-and-delta-re-review) (a pass
  [verdict](concepts.md#verdict) or a merge-ok steering signal;
  [on GitHub](backends/github.md#review-types-and-the-events-they-fire), a
  formal `APPROVED` review) carrying
  **either** `pass=verdict verdict=pass sha=<head>` (with review + validate
  sections whose own markers both say `verdict=pass`; validation may be a
  justified §3 flavor skip, checked against live rigor; an `APPROVE` over a failed
  validate marker does **not** count) **or**
  `pass=steer cmd=merge-ok sha=<head>`. `merge-ok` is the user's override; it
  skips validation and escalation but never CI. A
  [spec change](#spec-change-definition-and-spec-grant-scope) merges only on `merge-ok`, unless the opt-in spec grant
  scope covers it. A [narrative post](concepts.md#narrative-post) (such as a
  merge-up ack; on GitHub a COMMENT review) never satisfies this gate; only the
  formal approval (`APPROVED`) does.
- **Express self-gate.** For a change whose effective flavor is `express` by
  §3 express resolution, with `crew:express` on it, this replaces the formal
  approval above: the latest builder `pass=selfgate verdict=pass` at the full
  head SHA, or at verified H under verdict portability, whose `mode` is the
  effective `selfgate_engine` and, under `different`, whose `reviewer-engine`
  differs from every builder engine on the change; not `crew:sensitive` or a
  spec change unless the owner's recorded per-item override; CI green at
  head. Required evidence reads the selfgate record in place of validation at
  head. A missing, stale, malformed or `changes` record blocks. Engine
  disagreement checks the self-gate reviewer under `different`. Every other
  gate here applies unchanged. Fail-open: the owner's per-change merge-ok at
  head, or the crew lane (drop `crew:express`, route normal review and
  validation); never a CI waiver.
- Merge permission satisfies the effective `merge` knob in §3: owner's
  per-change merge-ok at head, or a recorded owner standing grant within the
  allowed `docs`/`auto` scope. The §3 legacy grant transition still applies until follow-up B migrates
  existing grants; their recorded scope is preserved regardless of this knob.
  A standing grant substitutes only for
  per-change permission; it never supplies a formal approval, skips
  validation, overrides a hold/escalation, or exempts sensitive changes from
  per-change merge-ok. It covers a gate-contract change only as a §3
  gate-contract grant: recorded, time-boxed, its scope explicitly naming gate
  changes, with the coordinator's merge-ok at head citing it. It covers a spec
  change only within the [spec grant scope](#spec-change-definition-and-spec-grant-scope).
- A `crew:sensitive` change has the owner's per-change merge-ok at the current
  head. No standing grant (including doc-only or project grants) covers it.
  A recorded owner classification override may clear the label as above.
- No later changes request (`REQUEST_CHANGES`) from the reviewer identity,
  whether a changes verdict or a steering signal such as `steer cmd=rework`
  ([Steering](#9-steering-crew-commands)); on GitHub, no later
  `REQUEST_CHANGES` review from the reviewer identity. No `crew:hold` /
  `crew:escalated` (unless the user's per-change `merge-ok`).
- No open project landing stop. Check the stable landing-control record and
  candidate reviews, regardless of head movement or closure of the control issue.
  Only a matching `resume-landing stop-id=<id>` releases that stop.
- No open coordinator hold. An explicit coordinator hold-until-X (or a crew
  hold command) already on the change or in the synthesizer's inbox
  **overrides** the standing doc-only merge-ok. Do not squash until the hold
  clears or the named dependency X has landed on `<default-branch>`. Re-read the
  change and the inbox right before merging; a hold posted after the approval
  wake still counts.
- If the builder marker and the fix note or commit trailer disagree on the
  engine, the note or trailer wins, and before merge the reviewer re-checks at
  head (fresh review + validation) on an engine different from the actual
  builder engine. The coordinator posts the rereview steer
  (`steer cmd=rereview`) at head, with the same ack and re-request mechanics as
  the evidence-only rereview in §3 and [Steering](#9-steering-crew-commands).
  Do not merge until that re-check verdict is posted. An open
  `steer cmd=rereview` at the **current head** (engine diversity or a disputed
  engine) blocks the squash until a fresh reviewer-validator verdict
  (`pass=verdict`) lands at that SHA on an engine different from the actual
  builder engine. `merge-ok` does not override it, and a prior `APPROVE` from
  the same or another engine does not satisfy it.
- The [builder pre-review gate](#builder-pre-review-check) is satisfied when
  enabled: latest builder `pass=precheck` at the full current head, every step
  `pass` or reasoned `n/a`, or the owner’s recorded per-change merge-ok at head.
  Missing, stale, malformed or failed markers block, including train members.
  Standing grants do not waive it; all other gates still apply.
- Required evidence is present inline. For a behaviour-changing change,
  proof required by effective `evidence` (§3) is in the body or a builder-signed
  fix / ci-fix review
  whose marker `sha=` is the head or an earlier commit of the change, and
  validation **at head**, or at verified H under verdict portability, marks
  it `agrees` (or accepts a reasoned N/A). With an authorized validation skip,
  require the passing review to check proof presence and claims and the
  justified `pass=validate verdict=pass validation=skipped` marker; do not
  require an independent run. A flavor never waives missing required proof.
  Text is a repro pair or fenced block; media is a GitHub user-attachments
  URL, or the capture recipe plus validator reproduction fallback in
  [verification Q1](verification.md#q1-how-bots-attach-images-and-video).
  Paths, repo-file links and other media hosts do not count. `unverified`
  needs the user's per-change merge-ok; `disagrees` blocks. Missing evidence
  without a reasoned N/A blocks. Docs-only and no-behaviour changes are N/A.
  The synthesizer checks presence and the verdict, without re-running proof;
  the validator confirms earlier captures still hold at head. Fail-open is
  per-change merge-ok for impossible capture or embedding, never the standing
  grant or a CI waiver. Detail: [verification](verification.md).
- **Runtime gates.** Every runtime gate the runtime binding declares is
  satisfied at head. The binding states, for each one, what satisfies it, its
  exemptions and what the synthesizer does while it is unsatisfied; its
  registry row gives who satisfies it and its fail-open
  ([Gate registry](#gate-registry)). While a runtime gate is unsatisfied, do
  not merge. Today's Grok Bot binding declares two
  ([runtime gates](runtimes/grok-bot.md#runtime-gates)):
  - **Builder watch:** the builder's `pass=watch` marker
    (`role=builder pass=watch watch=b2 status=attached`) with `sha=` the full
    40-char SHA of **any** commit on the change. Exempt: external, cutover
    (until its builder posts after the cutover), coordinator-opened
    `crew:spec`, `crew:solo` and lighter-lane changes
    ([builder watch gate](runtimes/grok-bot.md#builder-watch-gate)).
  - **No mirror hold:** a change touching `docs/protocol.md` or `templates/`
    has no `crew:needs-mirror` and a coordinator box-skill mirror comment,
    newer than the last commit touching those paths, that carries a clean
    drift check at that commit, derived from the changed paths, not only the
    state tag. On tmux, a profile-named recorded owner standing mirror
    deferral may satisfy this gate for a PR within its verified scope that
    does not change live Grok Bot behaviour; the synthesizer reads the source
    decision and names the deferral in the merge record, without needing a
    per-PR coordinator comment or label removal. An uncovered PR or an
    unreadable source still needs a real mirror. This supplies no merge
    permission; gate changes still require the owner's per-PR merge-ok
    ([tmux](runtimes/tmux.md#mdstack-train)). On tmux, profile
    `runtime.options.mirror = "none"` resolves this gate to `n/a` for every
    PR, whatever its paths or `crew:needs-mirror` label, and the merge record
    says `Mirror: n/a (profile)`; it supplies no approval or merge permission
    ([tmux](runtimes/tmux.md#no-live-copy-to-mirror-877)). Lighter-lane
    changes are exempt
    ([mirror hold gate](runtimes/grok-bot.md#mirror-hold-gate)).
- **Tested with `<default-branch>`.** The head contains the current
  `<default-branch>` tip, or the change is the next member of a green merge
  train whose tested state is the current `<default-branch>` (the train base,
  then the commit the previous member's land made), at the head the train
  tested ([land rules](#land-rules-and-merge-trains)). On tmux, when the profile sets
  `runtime.options.lone_pr_land = "direct"` and exactly one PR is ready, waive
  only this gate for that PR, even if its head is behind the default branch:
  no update-branch and no one-member train. Re-survey under the merge lock
  immediately before squashing; two or more ready PRs use a train. Every
  other §7 gate still applies at head, including passing verdict, review and
  validate markers, CI green, no open rereview or hold, sensitive merge-ok,
  mirror and `MERGEABLE`. The merge record names
  `Tested-with-default-branch waiver: lone_pr_land=direct, exactly one ready PR`.
  A release cut (a change adding a new version section to the CHANGELOG)
  never takes this waiver, and while one is open every other change adding a
  release fragment holds until it lands
  ([release](release.md#cut-freeze); tmux `mdstack train check` gate
  `release-cut`, #1433).
  Otherwise update-branch it at land; prove verdict portability at the new
  head, then require CI and every other gate here again. Being behind alone
  never sends it back. Backend alternative: on an
  [asynchronous land](interfaces.md#asynchronous-land-design) whose backend
  declares `land.tests_against_tip = true`, the backend's land check meets
  this gate for the exact patch it lands on the current tip. Run no
  update-from-base and build no train (`mdstack train` refuses); the merge
  record names the backend check and the landed revision. A bare `async`
  declaration meets nothing: the gate must hold at the request as above.
  On a session [stack land](#7-merge-gate-synthesizer), a backend declaring
  `land.stack_tests_against_tip = true` meets it for the combined stack on
  the current tip when its readback names the check, and each member's
  merge record names that check.
- The [CI signal](concepts.md#ci-signal) is green at head (all required
  checks). The change is not draft, is mergeable, and its base is
  `<default-branch>`.
- Tracker item linked (`Closes #n`) unless it is a spec, external or cutover
  change; a release cut links its release item only in the release-only
  non-closing form (`Refs #n` plus a whole line `Release issue: #n`), never a
  closing keyword; never auto-close an umbrella or TRD tracker item
  ([linkage on GitHub](backends/github.md#linkage)).

Then take the repo merge lock, [land](concepts.md#land) the change bound to
the head the gate checked
([on GitHub](backends/github.md#land-and-merge-up):
`gh pr merge <n> --squash --match-head-commit <sha>`), post `merge`, and
release the lock. If head moved, stop.

**Asynchronous land.** When the change backend declares
`land.mode = "async"` ([interfaces](interfaces.md#asynchronous-land-design)),
the land is a head-pinned request into the backend's queue. After the final
gate check at the pinned head, record a land intent keyed by change and
head, read `land-status` and request only on `none` (tmux:
`mdstack land request`). A lost acknowledgement is read back, never resent.
Poll until `landed` or `failed`, or until `land_timeout`. Only `landed`
posts `merge`: its record keeps `sha=` the checked head and names the
landed revision (`landed=<revision>` in the marker), which may differ from
the head after a backend rebase; default-branch CI is then checked at the
landed revision. `failed`, a timeout and an unknown status post no `merge`
and report blocked; a timeout or an unknown status keeps the intent. On
every wake, before anything else, read `land-status` for each recorded
intent (tmux: `mdstack land resume`): `queued` or `landing` resumes polling,
`landed` posts the missing record unless a `pass=merge` marker for that
change and head already exists and then checks default-branch CI at the
landed revision, and `none` means never requested, so the gate check reruns
before any request. None of them requests the land again. Clear the intent
only after the merge post and that CI check (green, or red reported as
after a direct land), whatever `lone_pr_land` is. A head change needs every gate
here again before a new intent. The repo merge lock is held from the final
gate check until the terminal status and the merge post, unless the backend
declares `land.serializes = true`, which meets
[C7](runtimes/README.md#c7-serial-land) itself, so no local lock is taken.
No merge-ok or standing grant substitutes for either backend flag, and CI is
never waived.

**Stack land.** On the session runtime, a change backend that declares
`land.stack = true` ([interfaces](interfaces.md#stack-land)) may land two or
more ready changes that form one linear `Depends on` stack in one atomic
request, instead of one per run. Check every gate above for every member at
that member's own head: verdict markers, precheck, flavor, merge permission,
holds and stops, and CI. If any member fails, refuse the whole stack and
request nothing. Otherwise record one intent for the stack, with each
member's revision id when the request names them, read `stack-status` (or
each member's `land-status` under `land.stack_status = "per-change"`),
re-read every member's head, and request `land-stack` once, only when every
member reads `none` and every head is unmoved (`mdstack land stack`). A
lost acknowledgement is read back, never resent; a rerun or resume uses the
recorded revision ids, never new ones. Success needs a complete readback:
every member, in stack order, `landed` with its own revision. A missing,
extra, reordered or malformed member line, or members in different states
(under `per-change`, queued beside landing too), is unknown: no `merge`
posts and the intent is kept for `mdstack land resume`, which never
requests. A revision id never replaces a full head or landed SHA in a
record. On
landed, post one `merge` record per member, each naming its landed revision
under the unchanged marker. Tested with `<default-branch>` must hold for
every member at the request unless the backend declares
`land.stack_tests_against_tip = true`; then the backend's combined-stack
test on the current tip meets it, but only when the readback names the
check (`check <reference>`), and each member's merge record names that
check. A declaration without that reference is no receipt, and per-change
readback names none, so it never meets the tip gate. The repo lock
is held as for an asynchronous land, unless `land.serializes = true`.
Without `land.stack`, session lands stay one per run; tmux trains are
unchanged.

Merge-only-by-synthesizer is **convention** until the backend enforces review +
checks (on GitHub, branch protection) and the synthesizer has its own identity
(e.g. a GitHub App) that alone may merge.
The M4 [merge-enforcement runbook](merge-enforcement.md) documents the target
ruleset; it is not live on this repo yet (2026-10-28: account-plan gap).
Its fail-open path keeps this §7 convention gate in place until application,
and uses the owner-decision path for a live ruleset blocker without waiving CI.

### Spec change definition and spec grant scope

In effect (#398, owner decision 1a on #649). `mdstack train check` and
`mdstack train land` apply it, and the synthesizer brief carries it.

**Spec change.** A change is a spec change when either holds at head:

- it carries `crew:spec`; or
- any change path, including both the old and new path of a rename, matches
  a spec glob. Globs come from [`spec.paths`](profile.md#spec), default
  `["docs/specs/**"]`.

The label alone is enough, and so is a path match alone: a `docs/specs/`
edit without the label is a spec change. Every reader uses this one test:
crew and express eligibility, direct land, train membership and land-time
merge permission. An unreadable label or path set blocks the land; no reader
treats an unclassified change as non-spec.

**Spec grant scope.** An optional key, `runtime.options.merge_grant_scope`,
lists what the standing `merge_grant` covers:

- `["approved"]`, the default and the behaviour when the key is absent:
  approved non-spec changes, as today.
- `["approved", "spec"]`: approved spec changes too.

`validate` rejects unknown values, and rejects `spec` when
`merge_grant = "none"`. The key grants nothing by itself: `spec` takes effect
only when the recorded owner decision that `merge_grant` names as its source
authorizes spec coverage. A broader grant string or scope list without that
record covers no spec change.

**What a covered spec change still needs.** Everything else in §7 at head:
the passing verdict (formal approval), CI green, required evidence, ownership,
holds and every other gate. The scope never covers a sensitive spec change
(F7), gate-contract work (F6), release approval, `unverified` evidence or an
open rereview; each keeps its own permission rule. It supplies no approval,
validation skip or express eligibility: a `crew:spec` change still runs the
crew lane without the owner's recorded per-item override.

**Records.** The rendered synthesizer brief names the spec definition and the
effective scope. Every merge post that uses the grant for a spec change names
the grant source and says it covered a spec change: `Permission:
merge_grant = "<grant>" with merge_grant_scope = [...]: covered a spec change.`

**Gate contract.** Satisfied by: a recorded owner standing grant
whose source authorizes `spec`, plus `merge_grant_scope` containing `spec`,
read live by the synthesizer before each land. Who: the owner records the
grant once, through the coordinator. Fail-open: the owner's per-change merge-ok at head,
today's path.

**Compatibility.** Optional keys only; with them absent, behaviour and
records are unchanged. No key, marker, label or command is removed or
renamed. A `sensitive` scope is out of scope here (#924).

**Slices.** D: this note. B1: the `merge_grant_scope` and spec glob schema in
`core/crew-config.py`, documented in the profile and team-file references.
B2: train, render and synthesizer template enforcement with the operative
§3/§7 wording; gate-contract work, landing only with the owner's per-change
merge-ok.

### Verdict portability and delta re-review

Review judges the patch at verified head H against base B. Record B's full
SHA in the review and verdict markers' `base=` field when the review starts.
Builders do not chase the default branch; reviewers never reject a change
solely for being behind. When §7 requires synchronization, the synthesizer performs it at land using
a clean, tool-performed update (forge merge, train merge or backend rebase), never edits
content and never force-pushes a shared branch.

Before carrying a verdict, compare B→H with updated base→updated head. Use
`mdstack content B H UPDATED_BASE UPDATED_HEAD --repo WORKTREE` (installed crew
CLI), or equivalent changed-line equality. This ignores blob-index hashes and
hunk positions only: whitespace, paths, modes and binary changes count.
A whitespace-insensitive patch-id alone is insufficient. Pin all four SHAs;
an unavailable verified base or failed comparison blocks carry. For a train,
compare each member's patch with its applied step, and check green CI on the
combined train SHA and the existing tested-default-branch rule.

Identical patch plus green required CI at the updated head carries the
passing review, validation and verdict from H, with no new round or reviewer
session. Inline proof from the verified change remains eligible after a
rebase even when its capture SHA is no longer an ancestor; the passing
validation at H must have accepted it. It carries no owner permission: head-pinned merge-ok, sensitive/spec
permission, later changes requests, holds, engine disagreement, an open
rereview and every runtime gate still apply at the live head. Only a real
passing reviewer verdict can carry; an ack, failed validation or candidate
identity result cannot. Bind the merge to that checked head. The merge marker
adds `content=identical carried-from=` with H's full 40-character SHA; `sha=`
remains the current PR head, and a train record also cites its tested SHA.

On a conflict or differing patch, stop land and route `change.update-from-base`
to the builder. The builder resolves it and records the verified B/H pair and
the updated base/head pair in a signed fix note. The reviewer performs a
**delta re-review** of the changed patch hunks, reading surrounding context
and dependencies as needed. Independent validation reruns affected acceptance
checks at the new head; the resulting verdict is head-pinned and obeys the
normal round cap. If the delta cannot be bounded or changes wider behavior,
use full review and validation. Neither differing content nor a conflict may
be resolved by the synthesizer.

A backend that declares a rebase update keeps this comparison unchanged,
with every earlier head kept readable so H stays fetchable; an unfetchable H
blocks the carry
([rebase update from base](interfaces.md#rebase-update-from-base), #874).

### Land rules and merge trains

Landing authority: the synthesizer alone decides direct land or train, batch
membership, order, isolating a failed member, and closing or rebuilding a batch.
Decide by protocol §7 and the resolved profile, never per-project steering.
Record each decision and reason in the train or merge report.

Coordinator inputs are a closed list of recorded pass=steer markers:

- cmd=land routes an approved change; re-read it and every gate before choosing how to land.
- cmd=hold with hold-until-#N and cmd=hold-release record a hold or its release,
  with a reason; wait until released or the dependency lands.
- cmd=merge-ok records the owner's permission at head; cmd=mirror-deferral
  records the owner's scoped mirror decision; cmd=profile records the owner's
  landing policy through the resolved profile. None supplies a gate waiver
  beyond the protocol's explicit allowance.
- cmd=urgent expedites one change alone ahead of batching, at its recorded head,
  with every §7 gate still applying. Urgency means a release blocker, security
  fix, explicit owner request or stop-the-line incident; record the reason.
- cmd=stop-landing stops the whole project's line on a red default branch,
  CI provider outage or owner request; cmd=resume-landing releases only the
  stop named by stop-id. Read all outstanding stops immediately before every
  squash, including direct lands and each train member. No merge-ok, standing
  grant or urgent marker overrides an open stop.

Everything else from the coordinator is advisory; the synthesizer may ignore it.

Landing control: before the first stop, the coordinator writes
`<state-dir>/<owner>__<repo>/landing-control.json` containing {"issue": N}, where N
is the tracker issue holding the project's signed stop/resume comments. On tmux use
`$CREW_STATE/landing-control.json`. Keep this reference across restarts and issue
closure; never relocate or delete it to clear a stop. Post all project stops
and resumes there with role=coordinator pass=steer, cmd-id identifying the
stop and stop-id identifying the stop a resume releases. Stop/resume is
project-scoped, survives a moved head, and never resets verdict rounds.
Unreadable control state blocks landing. Before each land read that issue's live
comments, even if closed, and the candidate PR's reviews; any unmatched stop
blocks. The tmux train gate performs this check too.

Batching approved changes into a merge train is a standing synthesizer skill
in every runtime: a train tests them together once, then lands them with no
catch-up between them. A change is **ready** when every gate above holds at
its head except tested with `<default-branch>`. At each wake the synthesizer
surveys every open crew change and picks one land rule:

| Situation | Land rule |
|---|---|
| `train_min` or more changes ready at once | Train them all now |
| Fewer ready, none close (no other change in review or re-check that should pass within `train_window`) | Merge each alone now: directly if its head contains `<default-branch>`, else update-branch first |
| Fewer ready, another close within `train_window` | Wait for it, then train |
| A ready change is urgent: a release blocker, a security fix or an owner request | Merge it alone now, whatever the batch |
| A change has waited `train_window` | Stop waiting: train what is ready, or merge it alone |

On tmux, `runtime.options.lone_pr_land` is `"train"` by default, preserving
these rules. With `"direct"`, exactly one ready PR lands immediately without
waiting, update-branch or a one-member train, using only the §7
tested-with-default-branch waiver above. Two or more ready PRs train,
regardless of `train_min`; all other gates remain required at head. The
merge record names the waiver and `Land rule: alone, direct`.

Train membership is decided before any train CI (#1425). At survey time,
`mdstack train check` runs step 1's drop checks for each candidate alone on
the current `<default-branch>` (gate `train-merge`): a conflict or a changed
patch routes that change to its builder for a merge-up first, so a train
forms only from members that will survive. After step 1, the surviving
members choose the path, recorded as `path=` in the train record and
report: two or more train (`train`); none means no train (`none`), and
dropped changes route to merge-up as before; exactly one, left by drops on
`<default-branch>` with `lone_pr_land = "direct"`, closes the train
unpushed (`direct`, reason `collapsed-to-direct`) and lands that change
directly under the rule above, at its own head with CI green there and the
lone-ready re-survey under the merge lock. A change the collapse dropped
is not ready at that head while the survivor is open, and routes to
merge-up after the direct land. Ready changes that arrive meanwhile train
with it instead. Its merge record also names the collapse
reason. With `"train"`, a one-member train still runs as before.

After a direct land, the synthesizer reads the PR's merge commit SHA and
waits for the default-branch push CI run at that exact SHA, checking every
required job. On tmux, keep the synthesizer alive through this check even
after the `pr-merged` event. The PR-head run or a run for another commit is not evidence;
missing or pending CI is not green. On red, report
`blocked: main red after #<n> <run-url>`. The coordinator files a blocking
`crew:ready` fix issue titled `main-red: <summary>` linking the landed PR
and that run, prioritizes the fix over new feature work (the scheduler ranks
it [class 1](scheduling.md#priority)) and keeps the blocker open until
default-branch CI is green. This fix-forward path grants no merge permission or CI waiver.

`train_min` defaults to 2 and `train_window` to 600 seconds (10 minutes).
On tmux they are the [profile options](profile.md)
`runtime.options.train_min` and `runtime.options.train_window`. Nothing waits
past the window, so a runtime with no timer wake for the synthesizer does not wait (Grok Bot today). Each
`[<SynthesizerBot>/merge]` record names its rule in one line, for example
`Land rule: train of 3 (ready at once)`, `Land rule: alone, urgent (release
blocker)` or `Land rule: waited 6 min to batch with #A and #B`.

1. **Build.** Branch `crew/train-<n>` from the current `<default-branch>`
   (the train base) and merge each ready change's head into it with a merge
   commit, in `Depends on` order, then approval order. A change that
   conflicts is dropped and goes to its builder.
2. **Test once.** Push the branch and run CI on it through a draft change
   that is for CI only and never lands.
3. **Land.** Only on green CI, under the merge lock: land each member in
   order, bound to the head the train tested, re-checking every gate above
   right before its squash. No update-branch runs between members. At the
   first miss, stop; the rest go to a new train or land alone.
4. **Red.** On red CI nothing lands; isolate failing members with bisection
   where available (tmux `mdstack train bisect`), or land the members one at a time.
5. **Record and close.** Each member's merge record cites the train branch,
   its SHA and the CI run as its tested-with-`<default-branch>` evidence.
   When the train ends, close the draft change and delete the branch.

On tmux, `mdstack train` runs these steps
([mdstack train](runtimes/tmux.md#mdstack-train)). The synthesizer
delegates steps 1, 2 and 4 to a builder worker through the builder lead
(handoff kind `train`: the train number, the base and each member's full
head SHA) and keeps surveying, gating and landing other ready changes
meanwhile, still one land at a time under the merge lock. The builder
reports the train record and never squashes, lands or posts a verdict. A
land made meanwhile moves `<default-branch>`, so that train no longer holds
its tested state and its members train again. Steps 3 and 5 and every gate
above stay with the synthesizer. A train builder that dies is restarted
once; a second failure closes the train and the synthesizer re-surveys.

## Multi-project isolation design reference

The [M51 team/project design](specs/team.md#9-team-and-project-separation-1318-design-only)
qualifies ownership, claims, evidence, verdicts and landing permission by
repo. Its [landing contract](specs/team.md#95-landing-authority-and-refusals)
is implemented for the terminal runtime (#1859,
[Team pools](runtimes/tmux.md#team-pools)): a land reads the selected repo's
records only, locks per repo, and refuses a train, stack, intent or lock
record naming another repo before any write. It changes no marker or gate
satisfaction, actor or fail-open rule. The stage 7 gate registry remains
authoritative for each repository.

## 8. Safety

- Work roles listen only to state-transition events: `issue-assigned`,
  `pr-opened`, `new-head`, `ci-passed`, `ci-failed`, `review-requested`, `review-approved`,
  `review-changes-requested`, `pr-merged`, `pr-closed`. **Only the steering
  dispatcher** subscribes to `pr-comment` / `inline-review-comment`. Nobody
  subscribes to `review-commented`.
- Each event has exactly one consuming role, with one narrow exception:
  PR-scoped `pr-merged` / `pr-closed` are terminal events that may reach both
  the builder's per-PR watch (B2) and the reviewer-validator's per-PR watch (V2).
  A routine run cannot delete another routine, so each watch must receive the
  terminal event itself to clean up its own state (the builder's worktrees and
  build output) and then delete itself. Every other event, including the
  repo-wide `pr-merged` the coordinator consumes, keeps exactly one consumer.
  Loops are bounded by the round cap and the CI-fix cap.
- External (fork) PRs: validation runs the code in an isolated sandbox with
  **no tokens**. First-time contributors' workflows may need manual approval
  before CI fires: flag it to the coordinator. Builders never push to fork
  branches.
- Only one automation system may own a repo at a time, enforced by the
  [ownership record](#ownership-record) when configured.
- Product repos MUST ship a human-readable root `README.md` with the sections of
  [templates/product-readme.md](../templates/product-readme.md) (problem, what it
  is, how to run / use, how the crew works, status); a seed PR that skips it is
  red.
- Workers never post to GitHub; only role bots post.
- Every wake costs a full bot turn: keep listeners tight and end no-op wakes
  within a few tool calls.

## 9. Steering: `/crew` commands

The user steers a PR with a PR conversation comment or inline review comment
whose **first line** starts with `/crew`:

| Command | Owner | Effect | Dispatcher hands it off via |
|---|---|---|---|
| `/crew hold` | Coordinator | Add `crew:hold` | Acts itself |
| `/crew resume` | Coordinator | Remove hold / escalated, post `resume` marker (resets rounds), re-kick the current stage | No verdict at head → re-request the reviewer; last verdict changes → `REQUEST_CHANGES` steer review; approved at head → `APPROVE` steer review `cmd=resume` |
| `/crew rework: <note>` | Builder | Relaunch on the branch with the note (+ `file:line` if inline) | `REQUEST_CHANGES` as reviewer identity, `steer cmd=rework`; not a round |
| `/crew rereview` | Reviewer-validator | Fresh review + validation at head | `steer cmd=rereview` ack, then re-request the reviewer identity |
| `/crew merge-ok` | Synthesizer | User override: merge once CI is green; required for spec PRs | `APPROVE` as reviewer identity, `steer cmd=merge-ok sha=<head>` |
| `/crew urgent: <reason>` | Synthesizer | Expedite this head alone for a qualifying urgency; every §7 gate applies | COMMENT review `pass=steer cmd=urgent sha=<head>` with reason, then notify synthesizer |
| `/crew stop-landing: <reason>` | Synthesizer | Stop the project line for a red default branch, CI provider outage or owner request | Signed issue comment on the stable landing-control issue `pass=steer cmd=stop-landing cmd-id=<comment id>`, then notify synthesizer |
| `/crew resume-landing: <stop-id>` | Synthesizer | Release the named project stop after recovery or owner release; other stops and gates remain | Signed issue comment on the same control issue `pass=steer cmd=resume-landing stop-id=<stop cmd-id>`, then notify synthesizer |
| `/crew escalate` | Coordinator | Add `crew:escalated`, post summary, bring to the user | Acts itself |
| `/crew away [--cap <n>] [--quiet] [until <time>] [words]` | Coordinator | Record project away or quiet mode; batch notifications, optionally cap concurrent runs, preserve authority and SLA | Acts itself; [away record and return](#owner-away-mode) |

Rules:

- **Accepted only** from the user's own accounts (`<user-logins>`), checked
  against the **commenter** login (listener allowlists gate the PR author, not
  the commenter).
- Unknown command, wrong commenter, or non-command comment: no-op, no reply.
- **Ack.** The dispatcher posts a COMMENT review
  `[<CoordinatorBot>/steer] ack <cmd> @ <sha7>` with marker
  `pass=steer cmd=<cmd> cmd-id=<comment id>`. A `cmd-id` already acked is never
  re-run; edited comments are ignored.
- Commands respect `crew:hold` except `resume`, `escalate`, `merge-ok`, `stop-landing` and `resume-landing`.
  `away` is project-scoped and also works on a held PR; it releases no hold.
- **Issues can't be steered by comment** (no issue-comment event): use
  assignment, labels (`crew:ready`, `crew:hold`), or chat with the coordinator
  ([steering limits on GitHub](backends/github.md#steering-limits)).

### Project pause

The owner pauses the whole project in conversation with the coordinator, not
with a `/crew` comment. A pause keeps the coordinator for owner conversation
and control and stops every other role with its work kept; nothing
dispatches, reviews, validates, lands, restarts, runs a routine or cleans up
until the owner's explicit resume. A land already started finishes first.
Resume rechecks ownership, heads, holds, CI and retained demand, starts
eligible work once and clears only the pause: never a hold, round count or
landing stop. A runtime binds the commands, such as the tmux runtime's
[mdstack pause and mdstack resume](runtimes/tmux.md#mdstack-pause); a full
shutdown is not a pause.

### Owner handoff commands

The owner moves repo ownership between runtimes in the **coordinator chat**,
not by comment. The coordinator re-reads the
[ownership record](#ownership-record), refuses a transition it does not
allow, and records the command in its state post with `cmd-id=chat` (bot
text never starts with `/crew`):

| Command | Given to | Allowed when | Posts | Then |
|---|---|---|---|---|
| `/crew handoff to <runtime-id> [drain \| stop] [deadline <minutes>]` | Owning coordinator | It owns with no handoff open | `draining` with a new id, the mode and, for `drain`, the deadline | `drain` (default): start no pass or land; runs finish their round; at the deadline (default 30 minutes) act as `stop`. `stop`: end its runs now, keeping unlanded work; a land past its final gate re-check finishes |
| `/crew handoff abort` | The coordinator that opened the open handoff | Before `acked` | `aborted` with the open id | `from` owns again and resumes |
| `/crew takeover from <runtime-id>` | Incoming coordinator | `<runtime-id>` owns and cannot act; no other handoff open | `takeover`, reusing the open id with the same `from` and `to` | Reconcile by reading; every guard of `from` turns read-only |

The drain ends with the manifest and `offered`, and a takeover with
`acked` ([handoff](handoff.md#manifest)). Each runtime binding names its
command (tmux: [`mdstack handoff`](runtimes/tmux.md#ownership-fallback)).

## Worked example / pilot notes

Grok Bot runtime: the agentconnect pilot notes are in
[runtimes/grok-bot.md](runtimes/grok-bot.md#pilot-notes).
