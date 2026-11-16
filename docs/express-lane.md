# Express lane (design)

> - **Status:** partly built
> - **Applies to:** tmux; Grok Bot runs express items in the crew lane
> - **Current rules:** [change flavor](protocol.md#change-flavor), [gate registry](protocol.md#gate-registry), [flavors](flavors.md)
> - **Built:** X1–X8 in [Build issues](#build-issues) (#668–#675; #672 is the routing switch)
> - **Design only:** the lane experiment and Grok Bot express routing ([Out of scope](#out-of-scope))
> - **Last checked:** 2026-11-04 at `217cec5`

An opt-in **express** flavor in which one builder builds, self-reviews and
tests end to end, and the change lands on green CI with no independent
review or validation ([#636](https://github.com/mw-ding/eng-crew/issues/636);
tracking [#611](https://github.com/mw-ding/eng-crew/issues/611); umbrella
[#110](https://github.com/mw-ding/eng-crew/issues/110)). It carries the
owner's decisions of 2026-11-03: the scoped floor exceptions and exclusions
(about 06:38Z), the self-review on a different model as the middle ground
(about 06:42Z) and the self-review flip between `same` and `different`
(about 06:45Z).

The [build issues](#build-issues) X1–X8 shipped in M18.2. This page adds no
rule, gate, round cap, marker, knob value or label. The
[protocol](protocol.md) and [flavors](flavors.md) still own those, and
GitHub stays the tool of record (invariant I5). On tmux, an item labelled
`crew:express` runs the express lane by program (X5, #672); on Grok Bot it
runs the crew lane. The experiment that compares the lanes is
out of scope (owner: later); this page only defines the
[metric columns](#metric-columns) it will need.

## Problem

Every crew change pays for an independent review pass, an independent
validation pass for behaviour changes, and the queue time in front of each.
On the verdict markers of 241 PRs, the validation pass found a problem after
a passing review in 2 of 217 rounds since 2026-11-01 (0.9%, #611). Under the
`standard` flavor the review is already thin: red only for an AC, a §7
gate, CI or security. For small, well-specified work the reviewer queue is
often the longest wait between the builder's push and the land.

firstmate runs review as a step inside the builder's own loop and merges on
green CI. Express brings that model into mdstack as a scoped lane, so it
can run beside the crew lane and be measured against it, without weakening
the floor for any other item.

## Overview

```text
 triage ── coordinator: item record flavor=express (Reason:), crew:express
   │       eligibility: not crew:sensitive, not crew:spec (owner per-item override only)
   ▼
 build ─── builder: code, targeted local checks, precheck steps
   │
 self-gate loop (in the builder's session, at most caps[0] reviews per head)
   │   ┌─► fresh review sub-session on selfgate_engine (same | different)
   │   │     rubric: protocol §3 Review section + adapter code-review skill
   │   │     input: diff at head, ACs, builder's stated intent and decisions
   │   └── builder fixes findings in context, reruns checks
   ▼
 open PR ─ body: precheck marker + evidence; builder posts the selfgate record
   │       (reviewer pool skips crew:express)
   ▼
 CI ────── red: builder ci-fix (caps[1]), new self-gate at the new head
   │       green + selfgate pass at head: poll routes to the synthesizer
   ▼
 land ──── synthesizer: §7 with the express gate row; serial land, trains,
           holds, ownership and merge permission unchanged
```

## Decisions

| Question | Decision | Alternatives considered | Section |
|---|---|---|---|
| Unit | A preset `express`, selected per item by a coordinator item record and the `crew:express` state tag. Never a project flavor | A project-wide `review = off`: every item in the project would skip review, so the floor exception would not be scoped. A label alone: unsigned, and carries no reason (the [flavors](flavors.md#decisions) record rule) | [Knobs](#flavor-knobs) |
| Floor exceptions | For `crew:express` changes only: F4's verdict post and I1 (author ≠ reviewer). I2 only when `selfgate_engine = same`. F1, F2, F3, F5, F6, F7, I3, I4 and I5 stay | Relax I2 always (#611's first draft): the owner chose the middle ground at about 06:42Z. Relax F3 so the builder lands (firstmate): one role then both judges and lands | [Floor](#floor) |
| Eligibility | Not `crew:sensitive`, not `crew:spec`, unless the owner overrides per item. A change that matches a tightening class rule at head leaves the lane | Every item: sensitive paths would land without a second identity looking. Coordinator judgment: not reproducible | [Eligibility](#eligibility) |
| Self-review engine | One knob, `selfgate_engine`: `different` (proposed default) or `same` | Always `different`: no fastest arm to measure. Always `same`: the floor exception grows to I2 for every express change | [Self-review flip](#self-review-flip) |
| Self-review rubric | Both modes load the reviewer's rubric: protocol §3 Review section (ranked findings, AC check, evidence and claim checks) plus any harness-native code-review skill the adapter declares | The precheck self-review step alone: it publishes no findings and runs in the builder's own anchored context | [Self-gate loop](#self-gate-loop) |
| Audit trail | A signed builder `pass=selfgate` record at head on the PR, with checks, findings, resolutions, mode and both engines | The precheck marker only: it has no findings and no engine fields. A chat or pane log: not the tool of record (I5) | [Marker](#selfgate-marker) |
| Merge permission | `merge = auto`, backed by a recorded owner grant scoped to express changes; otherwise per-change merge-ok | `merge = docs`: every code change would wait for a per-change merge-ok, which undoes the lane. `per-change`: the same | [Flavor knobs](#flavor-knobs) |
| Routing | Reviewer pool skips `crew:express`; `mdstack poll` routes `ci-passed` with a selfgate pass at head, and a new selfgate pass with CI green, to the synthesizer | The reviewer lead auto-approves: a fake independent verdict under the reviewer identity | [Routing](#routing) |
| Runtimes | tmux first. On Grok Bot an express item runs the crew lane (mirror deferral) | Both runtimes at once: Grok Bot routines have no in-session sub-session spawn to reuse | [Routing](#routing) |

## Flavor knobs

The `express` preset, beside the [presets](flavors.md#presets):

| Knob | `express` | Why |
|---|---|---|
| `review` | `off` (new value, valid only in `express`) | The independent review is replaced by the self-gate. `review = off` stays rejected for every other flavor (F4) |
| `validation` | `off` | No independent validation worker. The self-gate review checks evidence presence and AC claims, as an authorized validation skip does today |
| `selfgate_engine` | `different` (proposed default) · `same` | The [flip](#self-review-flip); `different` is stricter. Only express reads it |
| `diversity` | `waivable` | Applies to the self-gate review engine under `different`; `same` is the scoped I2 exception |
| `caps` | `[3, 3]` | `caps[0]` is the self-gate review cap per head (no verdict rounds exist); `caps[1]` is the CI-fix cap, as today |
| `evidence` | `typed` | No validator re-runs proof, so the proof in the body is the only proof (I3) |
| `merge` | `auto` | Express exists to land on green. `auto` needs a recorded owner grant covering express changes; the knob grants nothing itself |
| `precheck` | `on` | The seven precheck steps still run and record their marker; the self-gate adds the review record |
| `lighter_lane` | `docs` | Runtime knob, unchanged |
| `validation_scope` | `bounded` | No validator runs; the default scope is kept for consistency |
| `builder` | `crew` | A `crew:solo` item is not express; solo keeps its independent reviewer |

**Express resolution.** Today the change flavor is the knob-wise strictest
of the item record and the class flavor of the change's paths, and a path
that matches no class gets the project flavor. That rule can never yield
`review = off` on a `standard` project, so express needs its own: when the
newest item record names `express` and the change carries `crew:express`,
the express knobs apply unless a change path at head matches a class rule
stricter than the project flavor on any rigor knob (a tightening class such
as `src/auth/**`). Paths that match no class, or a class at or below the
project flavor, do not raise an express change. A tightening match, an
invalid or unreadable resolution, or a missing label resolves the normal
way and the change runs the crew lane. The rule is read by program at every
builder, poll and synthesizer wake, never by judgment.

## Floor

Scoped to a change whose effective flavor is `express` under the rule above.
Every other change keeps the [floor](flavors.md#floor) as written.

| Item | Express | How the intent still holds |
|---|---|---|
| F1 CI never waived | Kept | CI green at head is the express gate's core condition; the CI-fix cap is `caps[1]` |
| F2 No secrets | Kept | Unchanged secret scan |
| F3 Only the synthesizer lands | Kept | The builder never lands; land, merge lock and trains are unchanged |
| F4 Audit trail | Relaxed: no reviewer verdict post | The flavor record, the selfgate record at head and the `merge` marker stay on the PR |
| F5 Owner can always hold | Kept | `crew:hold`, `crew:escalated` and coordinator holds stop the builder and the synthesizer |
| F6 Gate-contract changes need the owner | Kept | This design's build issues change gates and need the owner's per-change merge-ok |
| F7 `crew:sensitive` needs per-change merge-ok | Kept | Sensitive items are ineligible; a sensitive path added later leaves the lane |
| I1 Author ≠ reviewer | Relaxed | The builder identity posts the selfgate record about its own change |
| I2 Reviewer engine ≠ builder engine | Kept under `different`; relaxed under `same` | The record names both engines; the synthesizer checks them |
| I3 Evidence on the change record | Kept | Proof inline in the body or signed builder reviews, never committed |
| I4, I5 | Kept | Synthesizer lands; GitHub holds the trail |

Hard rules stay: caps of at most 3, a serial land, and a per-change merge-ok
for `crew:spec` changes. The portable spec's "never silently weakened"
clause holds because the exception is written into §3 for one label, not
inferred by a runtime.

## Eligibility

- **Triage.** The coordinator records the item flavor `express` with a
  `Reason:` line (it is a lowering) and applies `crew:express`, only on the
  owner's words or within a recorded owner grant for express items. It runs
  the [sensitive classifier](protocol.md#sensitive-class) on the paths the
  issue names. A `crew:sensitive` or `crew:spec` item is refused unless the
  owner overrides for that item; the record quotes the owner.
- **PR open and every push.** The builder runs the sensitive classifier and
  express resolution on the full diff paths, both rename paths included. A
  new sensitive match, or a tightening class match, takes the change out of
  express: the builder records the reason in its next signed note, removes
  `crew:express` from the PR and tells the coordinator. The change then
  enters normal review at head.
- **Fallback to the crew lane.** The same path applies when the self-gate
  hits `caps[0]` with a blocking finding open, or when the owner asks. The
  coordinator re-records the item flavor at its default. Nothing already
  posted is edited.

## Self-review flip

| | `different` (proposed default) | `same` |
|---|---|---|
| Review sub-session engine | First engine in the `[engines]` order for the builder's tier, minus the engine that actually wrote the round, with the filter of [reviewer engine selection](roles.md#reviewer-engine-selection) | The builder's own engine and model |
| I2 | Holds | Scoped exception |
| Cost | One cross-engine spawn per self-gate review; quota on a second engine | No second engine; fastest |
| Failure mode | No other engine available: the builder waits, uses the [quota diversity waive](roles.md#quota-diversity-waive) record, or falls back to the crew lane | Shared blind spots: the reviewer misses what the builder's model misses |

The proposed default is `different`. It keeps the floor exception at F4 and
I1, which is the middle ground the owner chose at about 06:42Z, and it costs
one sub-session spawn, not a queue wait. `same` is the arm to measure pure
speed against it. The owner confirms the default when the first build issue
lands.

## Self-gate loop

The builder runs the loop after its local checks pass, before it opens the
PR, and again at every later head it pushes.

1. **Brief.** Write a short self-gate brief in the worktree's `.crew/`: the
   issue's ACs, the builder's stated intent, decisions and known risks, the
   full diff against the merge base, and the effective knobs.
2. **Review.** Spawn a fresh, read-only review sub-session on the engine the
   mode picks, through the harness's own non-interactive form
   ([how to run each engine](roles.md#how-to-run-each-engine)). It loads the
   rubric: the [Review section](protocol.md#3-evidence-requirements) of
   protocol §3 (verdict, findings ranked 🔴 / 🟡 / 🟢 with `file:line` and
   the AC or claim each contradicts; AC coverage, design fit, correctness,
   tests, security, scope creep) plus the evidence and claim checks an
   authorized validation skip requires. When the harness adapter declares a
   native code-review skill (a new adapter field), it loads that too. It
   returns a verdict and the findings; it never edits.
3. **Fix.** The builder fixes 🔴 and 🟡 findings in its own context, reruns
   the affected checks and commits. A finding it rejects needs a one-line
   reason; a deferred one needs a follow-up issue. 🟢 findings may be
   deferred without an issue.
4. **Repeat** from step 2 with a new fresh sub-session, until a review
   returns `pass` with no open 🔴, or `caps[0]` reviews have run at this
   head. A cap with an open 🔴 posts `verdict=changes` and takes the
   [fallback](#eligibility).
5. **Record.** Post the [selfgate record](#selfgate-marker) for the head.

A CI-only fix or a builder merge-up after a passing self-gate reviews only
the new hunks in a fresh sub-session (the light re-check shape of §6) and
posts a new record at the new head. A clean tool-performed update by the
synthesizer reuses the record at verified H under
[verdict portability](protocol.md#verdict-portability-and-delta-re-review).
`scripts/crew-precheck.py` checks the record the way it checks the precheck
marker: same builder-signature filter, full-SHA head binding and field
validation, behind a new `--pass selfgate` switch. The builder passes
`--item` with the item the change closes; the record's key field must name
the current change, or that item under `marker_key = item` (field table
below).

## Selfgate marker

A narrative post (a COMMENT review) by the builder identity. Its visible
part:

```text
<BuilderEmoji> <BuilderBot> · Selfgate · <pass|changes> @ <sha7>

Mode: <same|different>. Builder: <engine> <model>. Reviewer: <engine> <model>. Skill: <name|none>.
Effective knobs: <review, validation, evidence, caps, merge, selfgate_engine>.

| Check | Command | Result |
|---|---|---|
| <check> | `<command>` | <pass|fail|n/a: reason> |

| # | Rank | Finding (`file:line`) | Resolution |
|---|---|---|---|
| 1 | 🔴 | <finding> | fixed in <sha7> / rejected: <reason> / follow-up #<n> |

<!-- crew:v1 role=builder pass=selfgate pr=<n> sha=<40-char head sha> base=<40-char merge-base sha> round=n/a verdict=<pass|changes> mode=<same|different> builder-engine=<engine>/<model> reviewer-engine=<engine>/<model> reviews=<k> findings=<f> open=<o> checks=<pass|fail> -->
<BuilderSignature> · <harness> · <model>
```

| Field | Meaning |
|---|---|
| `pr` | The change id, matching `ids.change` (a GitHub PR number by default). When the change backend declares `marker_key = item`, `issue=<item id>` matching `ids.item` replaces it ([id keys](protocol.md#precheck-and-selfgate-id-keys)) |
| `sha`, `base` | Full head SHA the record covers, and the merge base the reviews read, as in the verdict marker |
| `round` | Always `n/a`: a selfgate record is not a §5 verdict round and never counts as one |
| `verdict` | `pass` only when the last review passed, `open=0` for 🔴, and `checks=pass` |
| `mode` | The effective `selfgate_engine` |
| `builder-engine` | The engine and model that actually wrote the head's commits (`Engine:` trailers win) |
| `reviewer-engine` | The engine and model of the last review sub-session; under `different` it differs from every builder engine on the PR |
| `reviews` | Review sub-sessions run at this head, 1 to `caps[0]` |
| `findings`, `open` | 🔴 and 🟡 findings raised at this head, and those still open |
| `checks` | All listed checks `pass` or reasoned `n/a` |

Readers parse only the hidden line, as for every marker. Existing readers
ignore it: `crew-precheck.py` and `metrics-refresh.py` match only the passes
they know, and `mdstack poll` reads only reviewer-validator verdicts. A newer
record at the same head supersedes an older one.

## Express gate

The §7 row, as the [gate registry](protocol.md#gate-registry) would carry it:

| Gate | Satisfied by | Who / how fast | Fail-open | Binding |
|---|---|---|---|---|
| Express self-gate (replaces formal approval for express changes) | Effective flavor `express` by [express resolution](#flavor-knobs), with `crew:express` on the change; the latest builder `pass=selfgate verdict=pass` at the full head SHA, or at verified H under verdict portability, whose `mode` is the effective `selfgate_engine` and, under `different`, whose `reviewer-engine` differs from every builder engine on the change; not `crew:sensitive` and not `crew:spec` unless the owner's recorded per-item override; CI green at head; merge permission per the effective `merge` | Builder before PR open and after every push (minutes); synthesizer re-reads live immediately before each land | Owner's per-change `/crew merge-ok` at head, or the crew lane: drop `crew:express` and route normal review and validation. Never a CI waiver | core |

For an express change it replaces the formal approval gate, and "Required
evidence" reads the selfgate record in place of validation at head. Every
other §7 gate applies unchanged: ownership, merge permission, sensitive
merge-ok, no changes request or hold, no landing stop, no coordinator hold,
engine disagreement (against the self-gate reviewer under `different`),
the precheck gate, runtime gates, tested with the default branch, CI and
change state, and the linked issue.

## Routing

tmux, per [`mdstack poll`](runtimes/tmux.md#mdstack-poll) and the leads:

| Event | Today | Express change |
|---|---|---|
| `new-head`, `fix-at-head` | reviewer | Not emitted; the reviewer lead also skips any queued review for a `crew:express` PR or linked issue |
| `ci-passed` | synthesizer, only with an approval at head | synthesizer when a selfgate pass is at head |
| New selfgate pass at head with CI green (`selfgate-passed`, new) | none | synthesizer |
| `ci-failed` | builder, held while a review pass runs | builder, never held (no review pass exists) |
| `merge-up` | synthesizer | synthesizer, checking the selfgate record's portability |
| Lane fallback (label removed) | none | the coordinator hands normal review to the reviewer lead at head |

The builder lead treats an express builder like any other: the same window
for the item's life, `ci-red` and merge-up conflict rounds by inbox. The
synthesizer composes trains as today; an express member's approval check is
the express gate. Grok Bot is out of scope for the first build: an express
item there runs the crew lane, and the protocol and template changes take
the tmux mirror deferral.

## Trade-offs

| | Crew lane (`standard`) | Express, `different` | Express, `same` |
|---|---|---|---|
| Speed | Review and validation queues after every push | No queue; one cross-engine sub-session per review | No queue; fastest |
| Shared context | Reviewer starts cold; may miss the builder's intent | Reviewer gets the stated intent and decisions; the builder fixes in context | Same as `different` |
| Same-model blind spots | Engine diversity on every verdict | Diversity kept | Shared with the builder |
| Independence and anchoring | Separate identity and session | Same identity; fresh session, but briefed by the builder | Same identity, same model; briefed by the builder |
| Independent validation | For behaviour changes | None: the builder's inline proof is the only proof | None |
| Cost | Two to three sessions per round | Builder plus one review sub-session per review | Builder plus one same-engine sub-session |
| Audit | Verdict post with review and validation sections | Selfgate record with findings and resolutions | Same |
| When it fails | Changes verdict, builder fix round | Fallback to the crew lane at the cap | Same |

## Alternatives considered

- **`fast` with `review = light`.** Keeps a light independent pass, but the
  reviewer queue, which is the cost express removes, stays.
- **Precheck self-review as the gate.** The precheck's step 4 publishes only
  a result and runs in the builder's anchored context; it gives no findings
  to audit and no engine choice.
- **Review after land.** Land on green CI, review the merged change later
  and revert on findings. The verdict would not exist at land (F4), and a
  revert costs more than a pre-land review.
- **Auto-approval by the reviewer identity.** Keeps the formal approval gate
  as written but makes the approval a fake independent verdict.
- **Builder lands (full firstmate).** Removes the synthesizer hop but breaks
  F3 and the serial land with trains.
- **A lane label with no flavor record.** Faster to wire, but the rigor
  change would be unsigned and carry no reason.

## Metric columns

New `prs.csv` columns for a later lane comparison. The comparison itself,
sample selection and decision rule are the experiment design, out of scope
here.

| Field | Type | How derived |
|---|---|---|
| `lane` | `crew`, `express` or `solo` | `crew:express` or `crew:solo` on the PR at close; otherwise `crew` |
| `selfgate_mode` | `same`, `different` or blank | `mode=` on the latest builder `pass=selfgate` marker; blank when none |
| `selfgate_reviews` | integer | Sum of `reviews=` over distinct selfgate markers (distinct by `sha`) |
| `selfgate_findings` | integer | Sum of `findings=` over the same markers |
| `dispatch_to_merge_min` | integer minutes | `merged_at` minus the author time of the PR's first commit with an `Engine:` trailer; blank if not merged |
| `ci_red_rounds` | integer | Distinct head SHAs on the PR whose required-check rollup ended red, for every lane, so the targeted-local-tests decision of 2026-11-03 (#617) can be checked against the same data |
| `merge_ups` | integer | Distinct `pass=merge-up` markers |
| `reverted` | `reverted` or blank | A merged revert PR naming this PR within 72 hours of its merge |

Existing columns (`open_to_merge_min`, `ci_fix_rounds`, `escaped_defects`,
`engine_runs`) carry over per lane unchanged.

## Build issues

Proposed follow-ups for the coordinator to file, about 100 lines each plus
tests, in dependency order. Each adds its own CHANGELOG fragment. X1 and X2
change gates: they are `crew:sensitive` in mdstack and need the owner's
per-change merge-ok (F6, F7).

| ID | Scope | Depends on |
|---|---|---|
| X1 | Flavors and schema: the `express` preset, `review = off` valid only in it, the `selfgate_engine` knob, the scoped floor rows; `crew-config.py` validator (`review = off` outside express still fails as `floor F4`) and express resolution in `class-flavor`; `item-flavor.py` accepts `express`; tests per rule | — |
| X2 | Protocol: §3 express resolution and the selfgate record, §4 `pass=selfgate` and the `crew:express` state tag, §7 express gate row and registry row, the portable spec §3 scoped exception; architecture label and pass tables; mirror deferral | X1 |
| X3 | `crew-precheck.py --pass selfgate`: parse and bind the record, mode and engine checks, `open` and `checks` rules; tests for missing, stale, malformed, `changes`, engine clash under `different` | X2 |
| X4 | Builder self-gate loop in the tmux builder brief and renderer: brief file, sub-session spawn per mode, rubric load, fix loop, record post, fallback; the harness adapter's code-review skill field; render and parity tests | X2, X3 |
| X5 | Routing: `mdstack poll` suppresses reviewer events for express, routes `ci-passed` and `selfgate-passed` to the synthesizer; reviewer lead skip; coordinator fallback handoff; tests per event | X3, X6 |
| X6 | Synthesizer: express gate in the brief and the gate-status and train helpers, portability of the selfgate record; tests for a mixed train and a stale record | X3 |
| X7 | Coordinator triage: eligibility check, `crew:express`, owner override record, the triage-flavor template; tests | X1 |
| X8 | Metrics: the [metric columns](#metric-columns) in `metrics-refresh.py` and metrics README; offline tests | X2 |

X7 and X8 can run beside X3. X5 is the switch: before it, an express PR
still gets reviewed; after it, the reviewer pool skips it. It waits for X6
so that an express PR is never left with neither a reviewer nor a gate that
lands it.

## Out of scope

- The experiment: sample size, assignment, run length and the keep, widen
  or remove decision (owner, later).
- Grok Bot express routing.
- Express for `crew:sensitive`, `crew:spec`, release cut and `crew:solo`
  items, other than by the owner's per-item override for the first two.
- Changes to the crew lane's review, validation, caps or merge gates.
