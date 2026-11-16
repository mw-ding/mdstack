# Always-on triage

> - **Status:** built (M24); live in shadow mode on this repo's own crew
> - **Applies to:** tmux: the `mdstack poll` scan, the watcher's sweep timer and Riley's sweep; session: `mdstack poll --triage-only`, a hosted routine trigger and the session sweep brief ([session binding](runtimes/session.md#triage-sweep-routine), #1404); not Grok Bot, which has no triage timer or sweep ([Out of scope](#out-of-scope), #777)
> - **Current rules:** [protocol §4](protocol.md#4-marker-conventions) (`pass=triage` record); [`[triage]` profile keys](profile.md#triage); coordinator dispositions in [§6](protocol.md#6-duties-on-wake-all-roles)
> - **Built:** T1–T7 in [Build issues](#build-issues) (#757, #767, #772–#776)
> - **Mode:** `mode = "shadow"` is the default and this crew's setting since 2026-11-04 ([#110](https://github.com/mw-ding/eng-crew/issues/110#issuecomment-6638329797)): sweeps write records and proposals only; `apply` is not on, and only the owner sets it after [calibration](#shadow-mode-and-calibration)
> - **Built (#753):** the [write allowlist](#write-allowlist) at one apply entry point, issue text as data and the provider refusal record
> - **Not built:** sweeps without bypass in a read-only sandbox ([Known risks](#known-risks))
> - **Last checked:** 2026-11-05 at `996ff71`

How every new issue and intake card gets a triage decision without anyone
remembering to run it, decided from what the crew already learned instead of
from a cold read
([#659](https://github.com/mw-ding/eng-crew/issues/659); umbrella
[#110](https://github.com/mw-ding/eng-crew/issues/110)). It records the
owner's answers of 2026-11-04 (walkthrough about 00:45–01:30Z, the
[decision post](https://github.com/mw-ding/eng-crew/issues/659#issuecomment-6620065225))
and the skip-rule addendum of about 01:40Z
([addendum](https://github.com/mw-ding/eng-crew/issues/659#issuecomment-6620173411)),
which override the initial draft wherever they differ.

This page adds no rule, gate, round cap, marker field or label of its own:
its [build issues](#build-issues) put those in the [protocol](protocol.md)
and the [profile](profile.md#triage), which own them. The coordinator still
owns every disposition
([§6 triage window](protocol.md#6-duties-on-wake-all-roles)), and GitHub
stays the tool of record (invariant I5). The
[self-improve intake](self-improve.md) keeps its card, lesson path and scope
rules; this design adds the recurring pass that reads them.

## Problem

| # | Seen | Cause |
|---|---|---|
| G1 | About 25 org-pack intake cards filed on 2026-11-01 waited untriaged ([#427](https://github.com/mw-ding/eng-crew/issues/427)); #372–#378, #391 and #422–#424 still wait | The only live trigger is the manual weekly sweep; the coordinator's triage window runs only while it is awake and not saturated |
| G2 | About 45 open issues carry no milestone | Placement happens only when the owner or coordinator looks |
| G3 | Duplicates and already-decided items get re-filed and re-asked (for example the parked #140 and the milestone scope rule) | Nothing checks closed issues, lessons, findings or recorded owner decisions before an item is triaged |
| G4 | Milestone learnings and runtime blockers reached mdstack only when the owner asked ([#374](https://github.com/mw-ding/eng-crew/issues/374), [#299](https://github.com/mw-ding/eng-crew/issues/299)) | Intake triggers are per-PR events; nothing fires at milestone close or on a run blocker |
| G5 | Triage in coordinator turns adds to the saturation seen on 2026-11-01 ([lesson](lessons/2026-11-01-coordinator-saturation.md)) | Triage is a coordinator duty with no other host |

## Overview

```text
  mdstack poll (no model)                    watcher timer (no model)
  new or changed item ── scan ──┐         every interval_hours, or overdue on wake
  duplicate hints, card fields, │                    │
  P0 signals                    ▼                    ▼
                         triage/queue.json ──► mdstack spawn researcher --sweep
                         P0 candidate ──────► single-item sweep, at once
                                                     │
                       fresh Riley session (read-only on code)
                                                     │
   lookup ───── duplicates, lessons, findings, owner decisions, metrics
   classify ─── rules first, model second; ambiguous ⇒ propose or needs-owner
   prioritize ─ P0–P3 band, then the in-band score
   act ──────── auto-apply (low risk) │ propose (labels + record) │ never
                                                     │
   triage record on each item ── one comment per sweep on the day's log issue
                                                     │
   next sweep: reads owner replies as decisions, cooldowns, metrics
```

Riley never builds, reviews, lands or releases an item to a builder. The
coordinator still moves an accepted item to `crew:ready`, and the
[scheduler](scheduling.md) still sets run order. Triage sets importance and
placement only.

## Decisions

| Question | Decision | Alternatives considered | Section |
|---|---|---|---|
| Learning lookup (Q1) | Deterministic keys first (failure class, Source link, paths, title tokens), then a model ranking over the shortlist. Every record cites what it used | Model-only similarity: not reproducible and cannot cite. Keyword search only: misses reworded duplicates | [Learning lookup](#learning-lookup) |
| What may run unattended (Q2, Q5) | Split by risk: auto-apply low-risk, reversible changes; propose the rest on the issue; never touch gates, flavors, merge permission or owner config | Everything proposed: the owner reviews labels too. Everything applied: closes and milestone moves are not safely reversible | [Autonomy](#autonomy) |
| Closes | Never automatic. Exact duplicates are labelled and linked; the close is proposed | Auto-close exact duplicates: a wrong close hides a live report | [Autonomy](#autonomy) |
| Priority (Q2) | P0–P3 bands, then impact × frequency × confidence ÷ effort with age and blocking bonuses | One numeric score: hides the P0 escalation. First in, first out: the backlog problem itself | [Priority](#priority) |
| Triggers (Q3) | A timer every `interval_hours` (default 6), a deterministic scan in `mdstack poll`, an immediate single-item sweep for a P0 candidate, a milestone-close sweep and run-blocker cards | Daily only: a P0 waits up to a day. New-item only: the backlog never gets a first pass | [Triggers and cadence](#triggers-and-cadence) |
| Host (Q4) | The researcher, Riley: a fresh local session per sweep, started by the watcher's timer; `researchers` cap 2 | A CI cron, the coordinator's turns, an always-on host, a new role | [Host](#host) |
| Owner loop (Q5) | Nothing is sent to the owner. Proposals live on the items; one log issue per day; the owner answers on the item | A batched digest message: one more channel to read. Per-item mentions: noise | [Owner loop](#owner-loop) |
| Start (Q6, Q7) | Shadow mode first; auto-apply turns on at 8 of 10 owner spot-checks accepted as is | Auto-apply from day one: no measured precision | [Shadow mode and calibration](#shadow-mode-and-calibration) |
| Feedback (Q6) | Owner replies become decisions with reasons; repeated rejections become findings rows; accuracy, override and reopen rates are measured against an eval set from this backlog | Unmeasured heuristics: the next pass is no better | [Feedback](#feedback) |
| Scope of a sweep | Unplaced issues and owner replies to triage's own proposals only; skip log issues, placed or already-recorded issues, and pull requests | Every open item: re-triages what the coordinator already filed and placed | [Skip rules](#skip-rules) |
| Related issues (#1298) | Clusters from deterministic keys first, then model-added members with reasons; members stay separate issues and get a `cluster:<slug>` label in `apply` | Consolidate them: loses distinct units of work. Model-only grouping: not reproducible | [Clusters](#clusters) |
| Card format | Recommended, never required: an intake-card issue template; blank issues stay allowed | A required template: rejects useful reports from humans and other crews | [Inputs](#inputs) |

## Inputs

One sweep reads, per tracker repo in `[triage] repos` (per tracker id in
`[triage] trackers` for a non-GitHub tracker backend, whose scan reads its
`tracker.list-items` binding instead of `gh`, #1404):

| Input | Source | Unreadable |
|---|---|---|
| Queue | `triage/queue.json` from the `mdstack poll` scan: open issues that pass the [skip rules](#skip-rules) | Sweep every open issue that passes the skip rules, capped by the noise cap |
| Item | Live title, body, labels, milestone, comments | Skip the item; log it as `skipped: unreadable` |
| Intake card fields | Rules parse `templates/intake-candidate.md` fields; otherwise the model extracts them and posts the extracted card as a comment labelled `triage:card-extracted` | Treat the item as a plain issue; nothing is gated on format |
| Owner replies | [Owner feedback](#owner-feedback) after the newest triage record, placed or not; on an unplaced issue, any owner comment, label or milestone change after it | Leave the proposal open |
| Owner decisions | Coordinator decision records (`pass=steer cmd=decision`; older posts titled `[Ash/decision]` count too) on the project's decision-log issue (the tracking issue that `away-control.json` names, [§6 Owner away mode](protocol.md#owner-away-mode)) and on the item | Fail closed: propose instead of applying |
| Prior learnings | [Lessons](lessons/README.md), the [findings buffer](findings/buffer.md), [metrics](metrics/README.md) (escaped defects, flavor columns) | Lookup proceeds without that store; the record says so |
| Class rules | The owner's rules file named by `[triage] rules` (label maps, P0 signals, cooldowns); editable config Riley never writes | Use the built-in defaults; the record says so |
| Milestones | Open milestones in order and `max_active_milestones` (#566) | Place nothing; propose |

### Skip rules

A sweep acts only on unplaced issues and on the owner's replies to its own
proposals. The scan and the sweep both skip:

- triage's own daily log issues, labelled `triage:log`;
- issues that already have a milestone, a `pass=triage` record or a flavor
  record, for example an issue the coordinator filed and placed;
- pull requests.

Owner answers after the newest triage record are the exception: the sweep
reads [owner feedback](#owner-feedback) on any recorded issue, placed or not,
and any other owner reply on an unplaced one, and records the decision. A
skipped issue is not listed in the log.

## Learning lookup

For each item, in this order, before it is classified
([#987](https://github.com/mw-ding/eng-crew/issues/987)):

1. **Still applies?** Check whether the item was overtaken since its
   creation date, with cited evidence for each case:
   - **Implemented:** merged PRs, closed issues or released CHANGELOG entries
     since filing cover the ask.
   - **Changed:** the commands, flags, paths, doc sections or config keys the
     item names have changed, been renamed or been removed since filing
     (history on those paths).

   A fully overtaken item gets a proposed close with reason
   `overtaken: implemented` or `overtaken: changed`. A partly overtaken item
   is classified and banded for only the remaining gap, and the record states
   what shipped. An item that still applies gets a record saying the check
   ran.
2. **Duplicates and similar items.** Exact keys first: the same failure
   class slug, the same Source link, an overlapping set of named paths, or a
   normalized title match, across open and closed issues. The `mdstack poll`
   scan already computes these hints. Then the model ranks the shortlist and
   may add reworded matches, each with a one-line reason.
   - **Exact duplicate:** labelled `triage:duplicate` and linked; new
     evidence in it becomes a comment on the existing issue, and the close is
     proposed.
   - **Similar:** two or more open issues that describe the same problem or
     overlapping asks (for example #376 and #377, head and CI read
     inconsistently on versioned backends) get a consolidation proposal. It
     names the survivor, lists what moves into it (ACs, evidence, occurrence
     counts), proposes closing the rest as `consolidated into #<n>`, and cites
     the matching keys or a one-line reason per pair. Occurrence counts from
     the merged issues feed the survivor's band, so recurrence across issues
     counts.
3. **Lessons and findings.** Match on failure class, path and keyword
   against lesson titles, Fix fields and findings smells. A match on a
   findings row is a proposed count bump on that row, never a new row or a
   new card. A match on a lesson with Status `documented` or later links the
   lesson and asks whether its fix regressed.
4. **Recorded owner decisions.** Match the item's topic against decision
   records. An item a decision already settles (for example "#140 parked in
   M15.1", the milestone scope rule, overlap policy D + S9) is placed or
   proposed exactly as the decision says, citing it.

Each triage record lists every match it used under `used:` as links, and the
rule or model step that produced each; still-applies evidence is a PR, a
commit on a named path or a CHANGELOG line. `Not checked:` lists what could
not be checked. A decision with nothing to cite says `used: none` and cannot
be auto-applied above P2.

**Rules first, model second, fail closed.** A rule match decides. The model
decides only what no rule covers, and only at high confidence. Any conflict
between rules, between a rule and a decision record, or a low-confidence
model answer becomes a proposal or a `needs-owner` record, never an applied
change.

## Clusters

Duplicates and similar items describe one problem. A cluster groups issues
that are **related but distinct**: the same failure class, component or
root cause, where each member stays its own unit of work (#1298). Each sweep
runs [`scripts/triage-clusters.py`](../scripts/README.md#triage-clusters)
over the open issues after the per-item records:

1. **Keys first.** Each open issue's deterministic keys: the Failure class
   slug, the Source issue, its `Depends on #n` targets (the open target
   carries the key too) and the first two segments of each named path. A key
   two or more issues share is a candidate. Candidates run in that order,
   then the ones the last sweep recorded, then by size; each issue joins at
   most one cluster. The same issues give the same clusters, and every
   member cites the keys that placed it.
2. **Model second.** The model may add an issue to a cluster with a one-line
   reason, and set a cluster's summary, band, milestone or tracking issue.
   These carry over to later sweeps while the cluster stands.
3. **Stable slug.** The slug comes from the placing key alone, for example
   `class-scheduler-stall` or `depends-mw-ding-mdstack-1266`, so new members
   never rename a cluster.

**Cluster record.** One per cluster: slug, members with their keys or
reasons, summary, suggested band (the highest member band unless the model
sets one) and suggested milestone (the milestone every member shares, the
model's suggestion, or `backlog`). The sweep posts it on the day's log
issue when the cluster is new or changed, with a `pass=triage-cluster`
line ([protocol §4](protocol.md#4-marker-conventions)). `triage/clusters.json`
in the state directory keeps the last result for the next sweep.

**Applying it.** Clustering never closes, merges or consolidates anything;
[similar items](#learning-lookup) keep their consolidation rule.

- In `apply` mode, each member gets the `cluster:<slug>` label and one
  comment linking the cluster record; a member that leaves loses the label.
  In `shadow` mode the record lists the labels instead.
- A cluster **tracking issue**, or moving the **whole cluster into a
  milestone**, is a proposal on the cluster record.
- The [noise cap](#owner-loop) counts one cluster proposal as one, whatever
  its size. An open cluster proposal costs nothing at later sweeps.

**Reporting.** The day's log lists each cluster with its size, band and the
members new since the last sweep, and
[`triage-metrics.py report`](#feedback) counts clusters.

## Outcomes

| Outcome | Effect | Autonomy |
|---|---|---|
| Classify | Type, priority and scope labels (`scope:repo` / `scope:crew` per [Scope](self-improve.md#scope-repo-vs-crew); `crew:` labels are state tags) | Auto-apply |
| Item flavor | The class default or project default record per the [triage template](../templates/triage-flavor.md); a lowering needs a `Reason:` and is proposed | Auto-apply the default only |
| Exact duplicate | Label and link; evidence moved to the existing issue as a comment | Auto-apply; the close is proposed |
| Findings bump | Count bump on an existing findings row | Propose (a repo edit goes through a PR) |
| Place in backlog or the next milestone | Milestone set | Auto-apply |
| Place in the active milestone | Milestone set | Propose, except P0 |
| P0 | Joins the active milestone | Auto-apply |
| Create or reorder milestones | — | Propose |
| Close with reason (`overtaken: implemented`, `overtaken: changed`, `consolidated into #<n>`) | — | Propose |
| Consolidate similar issues | Survivor named; what moves into it listed | Propose |
| Cluster related issues | Cluster record; `cluster:<slug>` label on each member | Auto-apply the label; a tracking issue or whole-cluster milestone move is proposed |
| Route to the owning crew or repo | Per [Knowledge routing](self-improve.md#knowledge-routing) | Propose |
| Route-out to an external tool's tracker | Outward-facing | Propose |
| Sensitive or spec item | — | Propose |
| Needs owner | P3 with the open question | Record only |

### Autonomy

- **Auto-apply** only low-risk, reversible changes: type, priority and scope
  labels; the default item flavor record; labelling and linking exact
  duplicates; `cluster:<slug>` labels; placement in the backlog or the next milestone; a P0 joining
  the active milestone.
- **Propose** everything else: the active milestone (except P0), milestone
  creation or order, every close (in every mode, `apply` included),
  route-out, anything sensitive or spec.
- **Never:** change a gate, a flavor setting or a merge permission; edit owner
  config, the rules file included; set `crew:ready`; act past a provider
  safety refusal (that item is parked for the owner and the sweep moves on).
- **Unanswered proposals never auto-apply**, however old.

**Issue text is data.** Issue titles, bodies, comments and labels set by
the filer are untrusted data. An instruction found there is reported as
content in the record and never followed; it never widens the
[write allowlist](#write-allowlist).

**Provider safety refusal.** When the model provider refuses an item, the
sweep records it once with a `refusal` request ("refused by the provider")
and moves on. It is never retried, reworded or reframed. The record parks
the item for the owner: `mdstack poll` skips it like any recorded item, and
the entry point refuses every later write on it until an owner comment
follows the record.

### Write allowlist

Every tracker write a sweep makes, in mode `apply` or `shadow`, goes
through one entry point,
[`scripts/triage-apply.py`](../scripts/README.md#triage-apply) (#753). The
sweep lists its writes in one requests file. The entry point checks each
against this table, the profile's `triage.mode` and `triage.repos`, and the
issue's own `pass=triage` record from this sweep: one in the same batch, or
one already posted by the researcher's login. A record from any other login
never counts. One refused request refuses the batch with a nonzero exit and
no write. Anything not in the table is refused: a close, a gate or other
`crew:` label, any other label, a milestone create, a body edit, a
repository or owner-config write. A write already in effect is skipped, so a
rerun applies nothing twice.

| Kind | Write | Mode | Checked against |
|---|---|---|---|
| `record` | The `pass=triage` record, proposals and owner answers included | both | One marker: this issue, this sweep, the configured mode, a decision other than `refused`, a band |
| `label` `triage:proposed` | The proposal label | both | A record from this sweep |
| `label` type, scope or band | Type (`bug`, `enhancement`, `documentation`, `question`), scope (`scope:repo`, `scope:crew`) or `P0`–`P3` | apply | A record from this sweep; the band equals its `priority` |
| `milestone` | Placement in the next milestone, or the active one for a P0 | apply | An open milestone, none created, in `repo.milestones` order after the `max_active_milestones` active ones; an active one only at `priority=P0`. Backlog placement is no write: the issue stays without a milestone |
| `flavor` | The default item flavor record | apply | `flavor` equals `default`, no `tier`, not lower than the project flavor, none on the issue yet |
| `duplicate` | `triage:duplicate`, a `Duplicate of #<m>` link comment and the moved evidence on `#<m>` | apply | A `decision=duplicate` record from this sweep; `#<m>` another issue |
| `label` / `unlabel` `cluster:<slug>` | Cluster membership; a new member also gets one comment naming the log issue | apply | The cluster's `pass=triage-cluster` record in the same batch lists the member, or no longer does |
| `unlabel`, `milestone` cleared | Revert or correct an applied label, duplicate label or placement | apply | An `owner-rejected` or `owner-adjusted` record from this sweep; `triage:proposed` comes off with any owner answer |
| `card` | The extracted card comment and `triage:card-extracted` | both | The intake card's Source and Failure class fields; no card yet |
| `refusal` | The provider refusal record (`decision=refused priority=P3`); the entry point writes its text | both | Not parked already |
| `log`, `cluster-record` | A `pass=triage-log` or `pass=triage-cluster` comment on today's `Triage log` issue, created with `triage:log` when missing; older open log issues are closed | both | One marker of that pass with this sweep id |
| `intake-card` | A milestone-close card: no milestone, Decision `pending` | both | Trigger `milestone-close`; a title starting `intake:`, not filed yet |
| `intake-evidence` | New evidence on an existing card | both | An `intake:` issue |

Only record, flavor, log and cluster bodies carry a `crew:v1` marker, one
each; every other body carries none. A parked item takes no write, through
any kind or as a duplicate's evidence destination, until an owner comment
follows its refusal record; an item refused in a batch takes no other write
in that batch, and one refusal per item. The entry point needs a GitHub
tracker: on another tracker backend it refuses every write, since it has no
apply binding there yet.

### Priority

Bands follow the owner's calibration of 2026-11-05
([#987](https://github.com/mw-ding/eng-crew/issues/987)):

| Band | Criterion |
|---|---|
| P0 | **Mainly the owner's call.** An explicit owner P0 (a `P0` label, or a signed owner comment calling it P0) sets P0 at once, and triage never re-rates it. Without that call, P0 only for a failure happening now on this project's own crew or backend: pipeline blocked, a wrong merge happening or about to happen, a secret, data loss. A latent gap in a gate, or a report from another crew's backend, is P1 until reproduced here |
| P1 | A recurring failure (two or more occurrences), a measured hit to throughput or cost, or an owner missed-bug or too-slow report |
| P2 | New features, single unreproduced reports, and the remaining gap of a partly overtaken item unless that gap meets P1 on its own |
| P3 | Icebox, or needs the owner |

**Both directions.** Each record names the criterion that set its band. The
sweep also checks for under-rating: a P2 or P3 item with recurring
occurrences (counted across consolidated issues) or a fresh failure moves up,
citing them.

Inside a band, a shortest-job-first score orders items: impact × frequency ×
confidence ÷ effort, plus an age bonus and a bonus for each open item that
waits on it (`Depends on #n`, the critical-path count the
[scheduler](scheduling.md#inputs) already reads). The score orders proposals
under the noise cap and placement within a milestone; it never changes run
order, which stays the scheduler's.

### Triage record

Each triaged item gets one signed comment per decision change, carrying a
hidden line in the existing marker style:

```text
<!-- crew:v1 role=researcher pass=triage issue=<n> decision=<outcome> priority=<P0-P3> mode=<shadow|apply> sweep=<id> -->
```

It lists the decision, what was applied and what is proposed, `used:`
citations, and the cooldown that applies if the proposal is rejected. A
sweep writes a new record only when the item or an owner reply changed since
the newest record, so repeated sweeps are idempotent. A `pass=triage` record
is a note, never a verdict or a gate input. The exact fields land with build
issue T3 in [protocol §4](protocol.md#4-marker-conventions).

## Triggers and cadence

| Trigger | Fires when | What runs |
|---|---|---|
| Scheduled | `interval_hours` (default 6) have passed since the last sweep, or the crew wakes with a sweep overdue | A full sweep of the queue, resuming from the last log entry |
| New item | `mdstack poll` sees an issue opened or changed that passes the skip rules | The deterministic scan only; the issue joins the queue for the next sweep |
| P0 candidate | The scan matches a P0 signal from the rules | An immediate single-item sweep |
| Milestone close (#374) | `mdstack poll` sees a project-repo milestone closed since its baseline and lists it under `milestones` in `triage/queue.json` | A sweep at once, not waiting for the interval, that drafts cards from the milestone's changes verdicts, steers, escalations and near-misses; the sweep names them in its Item and records them in `triage/milestones-taken.json` once its window starts, so a capped sweep or a later close loses none |
| Run blocker (#299) | A coordinator in any repo hits a crew defect | The coordinator files or updates a card; the next sweep triages it, or the scan flags it P0 |
| Weekly sweep | `scripts/intake-sweep.py` drafts cards for stuck PRs | Its drafts become sweep inputs, not a second triage |

**Nothing is triaged twice.** Every trigger feeds the same queue, and the
[skip rules](#skip-rules) drop any issue that is already placed or recorded.
The
coordinator's triage window reads triage records and the day's log, keeps its
disposition duty (`crew:ready`, `crew:spec`, `crew:needs-md`, defer, close)
and does not re-triage an item with a current record.

The crew is down, triage is down: no sweep runs while the machine sleeps or
the tmux server is stopped. On wake, an overdue sweep runs at once.

## Host

| Option | Trade-off | Verdict |
|---|---|---|
| Researcher (Riley), local, on the watcher's timer | Full local context and the crew's identity; no extra key. Down while the crew is down; uses the research engine's quota | Chosen |
| Scheduled CI job | Runs while the crew sleeps, but needs a separate paid model key, carries prompt-injection risk from issue text in a public repo and sees less context | Rejected |
| Coordinator turns | No new session, but adds to coordinator saturation (G5) and stops when it is busy | Rejected |
| Watcher or backstop running a model | The watcher is zero-token by design; it only starts the session | Rejected as a host; used as the timer |
| Always-on host ([M20](runtimes/multi-device.md)) | Runs while the laptop sleeps, once role hosts exist | Later: the same brief can run there unchanged |
| A new triage role | One more identity, brief and window range for what the researcher already is | Rejected |

**Session.** Each sweep is a fresh Riley session: `mdstack spawn researcher
--sweep` with the triage-sweep brief. Nothing carries over in memory; state
lives in triage records, the log issue and `triage/queue.json`. The
`researchers` cap rises to 2 so a sweep never blocks a deep dive.

**Cost.** The scan and the timer cost no model turns. The timer skips the
spawn when the queue is empty and no owner reply arrived since the last log
entry, so a quiet interval costs nothing. A sweep's cost scales with queued
items, each one lookup plus one classification, bounded by the noise cap for
proposals. T4 measures tokens per item and per sweep from run records before
auto-apply turns on.

## Owner loop

Nothing is sent to the owner: no digest message, no mention, no chat.

- **Proposals live on the item**, in the project's tracker repo, as labels
  plus the triage record. A proposed item carries `triage:proposed`.
- **One log issue per day**, titled `Triage log YYYY-MM-DD` and labelled
  `triage:log`. Each sweep
  appends one comment listing what it applied, what it proposed (linked) and
  what it skipped, with reasons. Opening the next day's log closes the
  previous one.
- **The owner answers on the item** by comment, label or milestone change,
  or by [owner feedback](#owner-feedback). The next sweep records the answer
  as a decision record, keeping a rejection's reason.
- **Noise cap:** at most 10 new proposals per day across repos, highest band
  and score first; a [cluster](#clusters) proposal counts as one. The rest
  are logged as `skipped: cap` and wait.
- **Cooldowns:** a rejected proposal is not re-proposed until its
  reason-specific cooldown ends, from the rules file (for example 30 days for
  a rejected duplicate), unless new evidence arrives on the item.

**Reflection is separate.** A sweep never runs a
[reflection](self-improve.md#reflection) or acts on its proposals. A
reflection report's new proposals share this noise cap and its rejection
reasons and cooldowns. This section's no-message rule binds triage only: the
coordinator relays one owner digest per reflection report.

### Owner feedback

One form works on any triage record, shadow or applied (#835). Owner how-to:

> Reply on the item with `triage: accept`, `triage: reject <reason>` or
> `triage: adjust priority=P2 type=bug`. The next sweep applies it.

Only `[identities] owners` count. A signed coordinator decision (its
`pass=steer cmd=decision` marker, or an older `[Ash/decision]` title) that quotes the
owner's words and time counts as the owner's answer, on the item or naming
it on the decision-log issue ([Inputs](#inputs)). `mdstack poll` queues the item for any of these, placed
or not, and the sweep records each as an `owner-accepted`, `owner-rejected`
or `owner-adjusted` decision, including answers posted before this form
existed and answers on closed issues (the sweep's full dump, not the queue). On an applied record, a reject reverts that record's reversible
label, duplicate-link and placement changes, and an adjust corrects them;
anything else it asks for becomes a proposal. The reason feeds the
cooldowns and the [feedback](#feedback) loop.

## Shadow mode and calibration

`[triage] mode` starts at `shadow`: the sweep writes records and proposals
only, and the auto-apply column is proposed too. The first run calibrates on
the backlog: it proposes for the roughly 45 unplaced issues and the 11 intake
cards, logged in that day's log. The owner spot-checks 10 sampled records.
At 8 of 10 accepted as is, the owner sets `mode = "apply"`; Riley never flips
it. Below the bar, the rejected reasons become rule edits the owner makes or
approves, and calibration repeats. The calibration sweep is not held to the
noise cap. [`scripts/triage-metrics.py`](../scripts/README.md#triage-metrics)
draws the sample (deterministic per sweep id) and scores the bar from the
`owner-accepted` and `owner-rejected` records (#750).

### Spot checks in apply mode

In mode `apply`, quality stays measured without owner-initiated feedback.
The first sweep each day that writes records lists a sample of 3,
`triage-metrics.py sample --sweep <sweep-id> --n 3`, under `Spot check`, and
the owner answers with [owner feedback](#owner-feedback). Every log comment
adds the `triage-metrics.py rolling` line over the newest 10 owner answers on
applied records. Below 8 accepted as is, the log proposes a return to
`shadow`; only the owner changes `mode`. An unanswered sample applies nothing.

### Recalibration on demand

When the method changes or the owner asks, the coordinator asks for a
recalibration sweep; it never runs on its own, including when a method change
lands:

1. The coordinator posts a signed `<CoordinatorEmoji> <CoordinatorBot> · Recalibrate` comment on
   the day's `Triage log` issue (creating it per the [owner loop](#owner-loop)
   if none is open), naming the reason, then starts a sweep with
   `mdstack spawn researcher --sweep`.
2. A sweep that finds that request with no `pass=triage-log` comment after it
   is a recalibration. It re-checks every open `triage:proposed` item whose
   newest `pass=triage` record has no owner answer after it, with the current
   method ([learning lookup](#learning-lookup) and [bands](#priority)), and
   writes one new record per item under its own sweep id, even when the
   decision is unchanged. It is not held to the noise cap or the record
   skip rule.
3. Its log comment lists the fresh sample of 10,
   `triage-metrics.py sample --sweep <sweep-id>`, under `Spot check`, and later
   sweeps add the `bar --sweep <sweep-id>` line that scores the owner's
   answers.

The 2026-11-05 recalibration ran by hand with this method (owner about
05:29Z; [#923](https://github.com/mw-ding/eng-crew/issues/923#issuecomment-6650542813)).

## Feedback

- **Decisions become memory.** Each owner answer is a decision record on the
  item; a rejection's reason feeds the cooldown and, when the same reason
  repeats, a proposed findings row (the [findings](findings/README.md) batch
  threshold applies). A rule that misfires twice becomes a proposed rules-file
  edit for the owner.
- **Accuracy.** Compare each record's classification and placement with the
  item's actual resolution when it closes, or, for an applied record the
  owner answered, with that answer.
- **Metrics:** time to triage (opened to first record), owner override rate
  (rejects and adjusts), reopen rate of closed-as-proposed items, proposals
  per day, skipped by cap, tokens per sweep, owner feedback on applied
  records, which also counts in accuracy and the override rate, and cluster
  counts.
- **Eval set.** A frozen sample of owner-confirmed records from this backlog,
  re-scored whenever the rules file or the sweep brief changes.

`triage-metrics.py report --sweep <sweep-id>` computes these from the issues'
records and the log's `pass=triage-log` lines, and names the applied-record
feedback that sweep recorded (`tokens=` is the sweep's self-reported count);
`eval-freeze` writes the eval set from the calibration sweep's accepted
records, and `eval-score` compares a re-classification with it.

## Known risks

Deferred by the owner on 2026-11-04 ("let's worry later") and tracked in
[#753](https://github.com/mw-ding/eng-crew/issues/753). M60 built the
[write allowlist](#write-allowlist) at one apply entry point, the
issue-text-as-data rule and the
[provider refusal](#autonomy) record. The allowlist bounds what the brief
authorizes; it does not confine a bypass-mode session, which can still run
any command. Revisit the row below before triage leaves shadow mode or is
enabled on a repo with untrusted filers.

| Risk | Candidate mitigation |
|---|---|
| Untrusted issue text in a bypass-mode session: a sweep reads public issue text while running with the project's `permission_mode`, which is bypass today, so text written as instructions could reach a session that can run commands | Not built: sweeps run without bypass, in a read-only sandbox with network access to the forge only. Built (#753): writes go through the allowlisted entry point, and the brief treats issue text as data |

## What this reconciles

| Item | Role in this design |
|---|---|
| [#427](https://github.com/mw-ding/eng-crew/issues/427) scheduled triage pass | Superseded: its scheduled pass is T2, its `pass=triage` markers, tracker operations and owner-approved route-out are T3, and its CI-job host option is rejected ([Host](#host)) |
| [#374](https://github.com/mw-ding/eng-crew/issues/374) milestone-close trigger | Folded in as build issue T6 |
| [#299](https://github.com/mw-ding/eng-crew/issues/299) run-blocker cards | Folded in as build issue T7: its cards feed the sweep |
| #354 flavor suggestions | Unchanged: project flavor stays with `flavor-suggest` and the owner; the sweep writes only the default item flavor record |
| Weekly sweep (`intake-sweep.py`) | Kept; its drafts become sweep inputs |
| Coordinator triage window | Kept for dispositions; reads triage records instead of re-triaging |

## Build issues

Filed into M24 in this order, about 100 lines each plus tests. Each adds its
own CHANGELOG fragment.

| ID | Issue | Scope | Depends on |
|---|---|---|---|
| T1 | [#747](https://github.com/mw-ding/eng-crew/issues/747) | Poll scan with the skip rules: deterministic duplicate hints, card-field parse and P0 signals in `mdstack poll`, writing `triage/queue.json`; a P0 candidate queues a single-item sweep; tests with fixtures | — |
| T2 | [#748](https://github.com/mw-ding/eng-crew/issues/748) | `[triage]` profile (`enabled`, `interval_hours`, `repos`, `rules`, `mode`) with validator rules and profile.md rows; `researchers` cap 2; the watcher's sweep timer with catch-up and the empty-queue skip; tests | — |
| T3 | [#749](https://github.com/mw-ding/eng-crew/issues/749) | Riley's triage-sweep brief (mirror): lookup, outcomes, autonomy, the `pass=triage` record in protocol §4, the skip rules, labels, the `triage:log` daily log issue, owner replies, cooldowns, noise cap; tests | T1, T2 |
| T4 | [#750](https://github.com/mw-ding/eng-crew/issues/750) | Shadow mode and the precision bar: `mode = shadow` default, the 10-sample spot check, accuracy, override and reopen metrics, the eval set; tests | T3 |
| T5 | [#751](https://github.com/mw-ding/eng-crew/issues/751) | Intake-card issue template with blank issues allowed; `triage:card-extracted` comments; tests | T3 |
| T6 | [#374](https://github.com/mw-ding/eng-crew/issues/374) | Milestone-close sweep that drafts cards | T3 |
| T7 | [#299](https://github.com/mw-ding/eng-crew/issues/299) | Run-blocker cards from coordinators, deduped and redacted | — |

T1, T2 and T7 can start first. T3 is the switch: before it, triage stays in
the coordinator's window; after it, sweeps run in shadow mode until T4's bar
is met.

## Out of scope

- Run order and admission: the [scheduler](scheduling.md) keeps them.
- Building, reviewing, landing or setting `crew:ready`: unchanged roles.
- Org-specific tracker bindings: a pack maps the tracker operations itself
  ([packs](packs.md)).
- Any message to the owner outside the tracker.
- Grok Bot: no timer, scan queue or sweep binding. There `triage.enabled =
  true` installs no timer, `mdstack doctor` warns, and triage stays the
  coordinator's dispositions ([#777](https://github.com/mw-ding/eng-crew/issues/777)).
