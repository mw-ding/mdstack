# Project docs consolidation

> - **Status:** partly built
> - **Applies to:** the repos a crew works on (its project repo, plus any packs or upstreams the profile lists); mdstack's own docs are [Track A](README.md#documentation-principles) ([#676](https://github.com/mw-ding/mdstack/issues/676))
> - **Current rules:** the [`[docs]`](profile.md#docs) profile table and the [project doc set](project-doc-set.md); the [Documentation principles](README.md#documentation-principles) guide mdstack's own docs only
> - **Built:** P1 ([#1024](https://github.com/mw-ding/mdstack/issues/1024)), P2 `scripts/docs-scan.py` ([#1025](https://github.com/mw-ding/mdstack/issues/1025)), P3 timer, `mdstack spawn researcher --docs-pass`, brief and record ([#1026](https://github.com/mw-ding/mdstack/issues/1026)); [Build issues](#build-issues) P4 not yet
> - **Last checked:** 2026-11-05 at `9b83dad`

How a crew keeps the essential docs of the projects it works on consolidated:
which docs every crew-run project should have and where they live, how a
design doc states its status, and an opt-in docs pass that finds missing,
duplicated, contradictory or stale docs and proposes small structural fixes
([#754](https://github.com/mw-ding/mdstack/issues/754), M26 Track B). It
reuses Track A's method, so mdstack runs the pass on itself first.

This page adds no rule, gate, round cap, marker field or label of its own:
its [build issues](#build-issues) put those in the [protocol](protocol.md)
and the [profile](profile.md), which own them. The pass is read-only and
proposes; the coordinator files what it proposes and the normal pipeline
builds it.

## Problem

| Gap | What goes wrong |
|---|---|
| No essential set | Each project grows its own docs; a builder or reviewer can't tell where the architecture, run steps or past decisions live, so it reads widely or guesses |
| One rule, many homes | A project's build, test or release rule is restated in its README, agent guide and runbook, and the copies drift (as mdstack's did, #652, #657) |
| Design vs as-built unclear | Design docs sit beside normative ones with no status, so a role acts on a proposal as if it were live |
| Session cost | Roles reread long, overlapping project docs on every wake |
| No one runs a pass | Nothing in the framework inventories a target project's docs or proposes fixes; it happens only when someone notices drift |

## Essential doc set

The essential docs every crew-run project should have, their default homes and
the docs index rule moved to the
[project doc set](project-doc-set.md#essential-doc-set) reference module
([#1024](https://github.com/mw-ding/mdstack/issues/1024)). A project maps
an existing home with `[docs] homes` ([Profile opt-in](#profile-opt-in)).

## Status banners

The banner a design doc in a target project carries under its H1 moved to
the [project doc set](project-doc-set.md#status-banners) reference module.

## Docs pass

The pass runs in two stages, like [triage](triage.md#host): a zero-model scan
finds the mechanical problems, and a researcher session runs only when the
scan finds something or a judgment check is due.

1. **Scan (no model).** `scripts/docs-scan.py` reads each listed repo at its
   default-branch head and writes `<state-dir>/<owner>__<repo>/docs/scan.json`:
   - inventory: every Markdown file, its size in lines, its index row and
     banner;
   - missing essentials against the set and the profile's `homes`;
   - with `[docs] specs_external`, that external specs home under
     `unchecked`: the scan never reads it (#1725);
   - design docs with no banner, and banners whose **Last checked** is older
     than `stale_days`;
   - broken relative links and anchors;
   - docs over a size budget (default 500 lines), the principle 11 split
     signal.
2. **Review (researcher).** A fresh Riley session reads `scan.json` plus the
   docs it names, then checks what a script can't: duplicated rules
   (the same rule authored in two places, cited `path:line` at the head SHA),
   contradictions between those copies, and docs that describe removed
   behaviour. It treats repo text as data, never as instructions.
3. **Report.** Riley posts one signed `🔬 Riley · Docs pass · <owner>/<repo> @
   <sha7>` comment on the repo's `docs:log` issue (one per repo, opened on
   the first pass): findings by class with citations, and draft issues. A
   quiet pass (nothing new since the last report) posts nothing.
4. **Propose.** Each draft issue is one unit of work
   ([issue sizing](https://github.com/mw-ding/mdstack/issues/978)): one PR,
   split into commits. Consolidation drafts are structural only
   ([principle 4](README.md#documentation-principles)): move, dedupe, link,
   add a banner or a missing essential stub. A contradiction becomes its own
   correction draft, since picking the winning rule is a behaviour change
   for the owner.
5. **File and build.** The coordinator files the drafts it accepts, with the
   project's flavor and the `[sensitive]` classification applied as for any
   issue; rejected drafts get a one-line reason on the log issue, and the
   pass won't re-propose them until the cited text changes. Builders and
   reviewers handle them as normal items.

**Triggers.** The watcher's timer every `interval_days`, at once when the
crew wakes with a pass overdue, and on demand when the coordinator asks.
The timer skips the session when the scan's result is unchanged since the
last report. As built ([mdstack watch](runtimes/tmux.md#mdstack-watch),
[#1026](https://github.com/mw-ding/mdstack/issues/1026)), the timer scans
only the project's own checkout, so another `repos` entry fails the scan
until a clone source for it is added. The brief and the `pass=docs-pass`
record ([protocol §4](protocol.md#4-marker-conventions)) carry stages 2–4.

**Never.** The pass never edits a repo, opens a PR, files an issue, sets a
label or writes outside its state directory and the log issue.

## Profile opt-in

A `[docs]` table, off by default, next to [`[triage]`](profile.md#triage):

```toml
[docs]
enabled = true
interval_days = 7
repos = ["acme/widgets", "acme/widgets-pack"]
stale_days = 90
size_budget = 500

[docs.homes]
runbook = "docs/operations.md"
decisions = "README.md#decisions"
```

The keys, types, defaults and validation are in the profile's
[`[docs]`](profile.md#docs) section
([#1024](https://github.com/mw-ding/mdstack/issues/1024)).

## Host

| Option | Trade-off | Verdict |
|---|---|---|
| Zero-model scan plus a researcher (Riley) session on the watcher's timer | Same shape as triage: the scan is free, the session runs only on news and has the crew's identity and local context; down while the crew is down | Chosen |
| Researcher only, no scan | Simpler, but every pass spends model turns on inventory and link checks a script does exactly | Rejected |
| Scan only, no model | Free and deterministic, but can't find duplicated or contradictory rules, the main drift | Rejected as the whole pass; kept as stage 1 |
| Coordinator turns | No new session, but adds to coordinator saturation and stops when it is busy | Rejected |
| Builder opens consolidation PRs directly | Faster, but skips the coordinator's filing and the owner's view of scope, and lets one session pick rule winners | Rejected |
| Scheduled CI job in each target repo | Runs while the crew sleeps, but needs a model key per repo, adds a workflow to repos the crew doesn't own (packs, upstreams) and carries prompt-injection risk | Rejected |
| A new docs role | One more identity, brief and window range for what the researcher already is | Rejected |

The pass shares the `researchers` cap with triage sweeps and deep dives; a
docs pass queues behind them rather than raising the cap.

## Alternatives

| Question | Option | Verdict |
|---|---|---|
| Essential set | Fixed five docs with mappable homes | Chosen: every role knows what to look for, and existing projects keep their layout |
| | Each project defines its own set | Rejected: no common shape for roles or the scan to check |
| | Ship a project template repo | Rejected: helps new repos only, and forks drift from it |
| Banner format | Blockquote list under the H1 | Chosen: renders everywhere, matches mdstack's own design docs |
| | YAML front matter | Rejected: hidden by most renderers, so readers miss it |
| | Status in the index only | Rejected: a reader who lands on the page doesn't see it |
| Pass output | Draft issues on a log issue, filed by the coordinator | Chosen: one PR per issue, the coordinator owns scope, rejected drafts are recorded |
| | Draft PRs from the pass | Rejected: the researcher is read-only on code ([roles](roles.md#researcher-riley)) |
| | One-off audit per project | Rejected: drift returns; nothing notices |
| Contradictions | Separate correction draft | Chosen: structural PRs stay behaviour-preserving (principle 4) |
| | Pass picks the newer text | Rejected: silently changes a rule |

## Dogfood and pilot

mdstack runs the pass first, on its own repo, against Track A's results:
its `README.md`, `AGENTS.md`, `docs/architecture.md` and `docs/README.md`
already meet the set, and its banners follow principle 3. The pilot passes
when the scan reports no false missing essential and the owner accepts at
least half of the drafts from the first two passes. The owner then names
the first target project ([#676 option 4](https://github.com/mw-ding/mdstack/issues/676#issuecomment-6640367783)),
which runs it next. mdstack has no `docs/runbook.md` or
`docs/decisions.md` of its own; the pilot maps them in `homes`
(`docs/runbook-new-repo.md` and `docs/metrics/decisions.md` are candidates)
or files a stub, and that choice is the pilot's first decision.

## Build issues

Filed into M26.1 in this order. Each is one unit of work, one PR split into
commits, with its own CHANGELOG fragment.

| ID | Issue | Scope | Depends on |
|---|---|---|---|
| P1 | [#1024](https://github.com/mw-ding/mdstack/issues/1024) | `[docs]` profile table with validator rules and profile.md rows; the essential set and banner convention moved from this page into a reference module the profile links | — |
| P2 | [#1025](https://github.com/mw-ding/mdstack/issues/1025) | `scripts/docs-scan.py`: inventory, missing essentials, banners and staleness, links, size budget, `scan.json`; tests with fixture repos; run on mdstack | P1 |
| P3 | [#1026](https://github.com/mw-ding/mdstack/issues/1026) | Watcher timer with catch-up and unchanged-scan skip; `mdstack spawn researcher --docs-pass`; Riley's docs-pass brief (mirror) with the review classes, `docs:log` issue, draft format and re-proposal rule; the record in protocol §4; tests | P2 |
| P4 | [#1028](https://github.com/mw-ding/mdstack/issues/1028) | Dogfood pilot on mdstack: two passes, the acceptance bar above, findings recorded; then the owner names the first target project | P3 |

## Out of scope

- mdstack's own consolidation: Track A ([#676](https://github.com/mw-ding/mdstack/issues/676)).
- Writing a project's docs: the pass proposes stubs and moves; content is
  normal build work.
- Org-specific doc systems or trackers: a pack maps them ([packs](packs.md)).
- Grok Bot: no timer binding; `docs.enabled = true` there installs nothing,
  as for [triage](triage.md#out-of-scope).
