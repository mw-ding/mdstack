# Lessons log

Dated record of what the crew learned from pilots, incidents and bottleneck
reviews. Each lesson is written down here first, then turned into an issue and a
PR (see [CONTRIBUTING.md](../../CONTRIBUTING.md)). Add the lesson file with its
metadata; do not edit the index: it is generated (see [Index](#index)).

Repeated small smells go to the findings buffer, [docs/findings/](../findings/README.md),
first and are batched into one issue (the M5 batch), not one lesson each.
Lessons stay for incidents that have a written analysis.

Entries are sanitized per spec R1: no tokens, keys, email addresses, private chat
quotes or real box paths. Use placeholders (`<state-dir>`, `<owner>/<repo>`) and
bot role names (coordinator, builder, reviewer-validator, synthesizer).

## File naming

One file per analysis or incident: `YYYY-MM-DD-<slug>.md`, where the date is when
the analysis was done. A file holds one or more entries.

## Metadata

Each lesson file opens with one front-matter block of exactly these four
single-line keys, once each and non-empty:

```markdown
---
title: <one-line summary; no pipe character; it is the index Summary cell>
date: YYYY-MM-DD
status: encoded | applied | superseded | open | mixed
source: <one-line pointer to the evidence origin, from the entry's Source / evidence field>
---
```

`date` equals the filename's date. A single-entry file copies its entry's
Status word. A file holding more than one entry takes `status: mixed` and a
file-level source; each entry's own Status field stays authoritative. `mixed`
on a single-entry file fails, and so does any other key.

## Entry format

Every entry uses these fields, in this order. A file may group related entries
under a table or a list, but each entry still answers every field.

| Field | Meaning |
|---|---|
| Date | When the lesson was observed or written up (`YYYY-MM-DD`) |
| Source / evidence | Where the finding comes from: the pilot, PR, timeline or analysis. Sanitized; worked-example references are plain text, not links |
| Finding | What happened, in one or two sentences |
| Impact | The cost, in time, rounds or risk. Give a number only when the source gives one |
| Fix | The change that addresses it, or the proposed change |
| Status | `encoded` (a check in `scripts/check-repo.py` or lint enforces the fix; name the check in Fix), `applied` (the fix is in effect: it is in the protocol, role docs, templates or scripts on `main`, or the source confirms it live), `superseded` (replaced by a different fix or entry; name it) or `open` (not applied, only proposed, an accepted limit, or the evidence does not settle it). Follow the status word with a short reason that names the evidence, such as a file, section or PR. Never guess |
| Linked issue/PR | The issue or PR in this repo that tracks the fix, or `none yet` |

Template:

```markdown
### <short title>

- **Date:** YYYY-MM-DD
- **Source / evidence:** <where it comes from>
- **Finding:** <what happened>
- **Impact:** <cost>
- **Fix:** <change>
- **Status:** open | applied | superseded | encoded
- **Linked issue/PR:** none yet | <owner>/<repo>#N
```

### Status vocabulary

One vocabulary: `encoded`, `applied`, `superseded`, `open`. It replaces the
earlier `shipped` and `documented`, which both map onto `applied`; the evidence after
the word says where the fix lives (for example "`docs/roles.md` Quota routing"
or "box configuration, per the source"). A fix the docs prescribe is `applied`
once it is on `main`. Whether a box skill copy matches is a separate question,
answered by the
[drift check](../../scripts/README.md#skill-drift-check-coordinator).

Hygiene pass: when a PR changes a protocol, role or template rule that a lesson
describes, re-check that lesson's status in the same PR. Verify against `main`
(`docs/`, `templates/`, `scripts/`, `CHANGELOG.md`, merged PRs); if the evidence
does not settle it, keep `open` and say why.

## Correction hierarchy

When a lesson needs a fix, fix it at the highest level that works, and write
prose last:

1. **Architecture:** remove the failure mode by design, so the step cannot go
   wrong or no longer exists.
2. **Types / schemas:** make the bad state unrepresentable, for example a fixed
   marker format with one required field shape.
3. **Lint:** a linter rule (markdownlint and similar) catches it.
4. **CI check:** a check in `scripts/check-repo.py`, with a failing-then-passing
   test in `scripts/test-check-repo.py`, catches it before merge.
5. **Skill or protocol prose:** a written rule. Last resort, because prose is
   only followed when someone reads it.

Each entry's **Fix** names the level it uses. A fix at level 5 must say
**"prose only, because ..."** and give the reason. That exception is allowed
only when the rule cannot be checked from repo files: it depends on live
GitHub state, timing, bot behaviour or judgement. "It was quicker to write a
sentence" is not a reason.

Status `encoded` means a structural check enforces the fix (level 4 or above)
and the Fix names it; it is a stronger form of `applied`. Prose written
alongside the check stays, but the check is what holds the line. Existing entries keep their status until someone encodes
them; encoding every lesson is not required.

## Index

Generated from each lesson's metadata, ordered by date, then filename. A lesson
PR adds only its own file and never edits this table: `python3
scripts/check-repo.py` validates every file's metadata and each committed row,
and passes a valid file with no row yet as pending. The milestone's opening and
closing bookend PRs (or an on-demand sync) run `python3 scripts/check-repo.py
--fix` and commit the regenerated table.

<!-- lessons:begin: generated from docs/lessons/*.md front matter by `python3 scripts/check-repo.py --fix` -->

| File | Date | Summary |
|---|---|---|
| [2026-10-19-bottlenecks.md](2026-10-19-bottlenecks.md) | 2026-10-19 | Bottleneck analysis of 22 pilot PRs: headline timings, five ranked losses, other lessons |
| [2026-10-20-actual-builder-engine.md](2026-10-20-actual-builder-engine.md) | 2026-10-20 | A fix round was written by Codex while the builder marker said claude-code; the reviewer engine must differ from the engine that actually wrote the round (#21) |
| [2026-10-20-evidence-on-pr-head.md](2026-10-20-evidence-on-pr-head.md) | 2026-10-20 | Evidence a verdict relies on goes on the PR head, never a side branch (PR #12 incident) |
| [2026-10-20-merge-up-rounds.md](2026-10-20-merge-up-rounds.md) | 2026-10-20 | Merge-ups must not burn review rounds; an ack cannot satisfy the merge gate, so a clean merge-up after an approval gets a formal re-approve (#20) |
| [2026-10-20-validation-gate.md](2026-10-20-validation-gate.md) | 2026-10-20 | A failed validation pass was overridden by an APPROVE on #16; the rule that a validation fail blocks APPROVE is now documented (#24) |
| [2026-10-23-builder-watch-attach.md](2026-10-23-builder-watch-attach.md) | 2026-10-23 | The builder's per-PR watch B2 silently failed to attach on PR #35 and the PR stalled about 62 min; B2 attachment is now verified, recorded and swept (#36) |
| [2026-10-23-merge-gate-watch-race.md](2026-10-23-merge-gate-watch-race.md) | 2026-10-23 | PR #41 merged before the builder's B2 hand-off reached its parent turn, so no watch or marker existed; the merge gate now requires the `pass=watch` marker (#43) |
| [2026-10-23-watch-handoff-first-run.md](2026-10-23-watch-handoff-first-run.md) | 2026-10-23 | First live run of the verified B2 hand-off on PR #38: pin the routine folder id, parent-turn-only marker, full 40-char SHA in markers (#39) |
| [2026-10-25-lighter-lane-routing.md](2026-10-25-lighter-lane-routing.md) | 2026-10-25 | Lighter-lane templates skip B2/watch and mirror holds; explicit messages route changes requests, red CI and cleanup (#57) |
| [2026-10-29-metrics-to-decisions.md](2026-10-29-metrics-to-decisions.md) | 2026-10-29 | Metrics baselines existed but no sensor turned a slow streak or rework wave into a harness fix; the rollup gate and per-repo follow-up are documented, with `metrics-decide.py` (#86) |
| [2026-10-29-self-improve-intake.md](2026-10-29-self-improve-intake.md) | 2026-10-29 | Failures die in chat; intake queue plus repo lesson store plus a scoped harness PR, with a weekly stuck sweep as the one live trigger (#89) |
| [2026-10-29-step-summary-observe.md](2026-10-29-step-summary-observe.md) | 2026-10-29 | Long agent runs were invisible mid-flight; builders write short step summaries and promote them onto the PR, raw logs stay local instead of a full tmux scrollback in chat (#85) |
| [2026-10-29-synthesizer-hold-race.md](2026-10-29-synthesizer-hold-race.md) | 2026-10-29 | The synthesizer squashed past an open coordinator hold-until (#78) and an open rereview (#74); both are now §7 merge blockers that merge-ok does not override (#81) |
| [2026-10-29-typed-verify-evidence.md](2026-10-29-typed-verify-evidence.md) | 2026-10-29 | Verdicts rested on diff and CI; typed runtime evidence per shape (web, CLI, service, API, mobile) is now a merge gate with builder, validator and synthesizer duties (#83) |
| [2026-10-30-mirror-drift-gate.md](2026-10-30-mirror-drift-gate.md) | 2026-10-30 | The mirror hold waited on a hand copy with nothing checking it; the mirror comment now needs a deployed render and a clean drift check (#128) |
| [2026-10-30-tmux-dry-runs.md](2026-10-30-tmux-dry-runs.md) | 2026-10-30 | Two local dry runs and three live runs of the tmux crew for #139: 6 manual unblocks in dry run 1, then a land lock on a placeholder path and an auto-apply merge-ok offer live, until the final run passed pass bar a–g; each finding mapped to its fix PR or backlog issue (#269, #270) |
| [2026-11-01-coordinator-saturation.md](2026-11-01-coordinator-saturation.md) | 2026-11-01 | Mechanical routing consumed coordinator turns at about 20 windows; owner replies come first (#434) |
| [2026-11-01-inline-evidence.md](2026-11-01-inline-evidence.md) | 2026-11-01 | Inline proof in the change record; reject committed evidence |
| [2026-11-03-model-switch-evidence.md](2026-11-03-model-switch-evidence.md) | 2026-11-03 | A model switch turned 6 of 8 changes verdicts into CLI-evidence blocks; captures now come from `evidence-cli.py` (#652) |
| [2026-11-03-standard-default.md](2026-11-03-standard-default.md) | 2026-11-03 | Unset projects ran `thorough`; validation found problems after a passing review in 2 of 217 rounds, so unset now resolves `standard`, flagged (#632) |
| [2026-11-08-complete-contract.md](2026-11-08-complete-contract.md) | 2026-11-08 | 13 repaired cards where a gate or action read part of its contract and took the gap as permission; fail closed on the whole contract (#1342) |
| [2026-11-08-real-entrypoint-fixtures.md](2026-11-08-real-entrypoint-fixtures.md) | 2026-11-08 | 7 repaired cards where a test or check bypassed the production path; test through it and fail closed, with three leftovers filed (#1342) |
| [2026-11-08-sandbox-every-effect.md](2026-11-08-sandbox-every-effect.md) | 2026-11-08 | 5 repaired cards where the campaign sandbox checked one channel once; check the boundary at every effect, with a decoy per channel (#1342) |
| [2026-11-08-terminal-record-consumers.md](2026-11-08-terminal-record-consumers.md) | 2026-11-08 | 7 repaired cards where a terminal record was lost downstream; match records by stable identity and test each consumer with the runtime record (#1342) |
| [2026-11-11-detached-fixture-capture-pipe.md](2026-11-11-detached-fixture-capture-pipe.md) | 2026-11-11 | A detached test child inherited the `capture_output` pipe, so each launch waited about 60 s for EOF and CI timed out; give such children DEVNULL stdio (#1637) |
| [2026-11-14-resolved-profile-context.md](2026-11-14-resolved-profile-context.md) | 2026-11-14 | `profile()` added derived `context.*` keys to the resolved values, so `grant prune`'s equality check never matched and CI failed on #1866; compute derived values separately so the resolved values stay exactly the profile (#1883) |
| [2026-11-14-runtime-state-row.md](2026-11-14-runtime-state-row.md) | 2026-11-14 | A cleanup change shipped with its allocated runtime state-file row describing the old behaviour; reviewers read that row beside the command and retention tests (#1843) |
| [2026-11-14-watcher-process-timing.md](2026-11-14-watcher-process-timing.md) | 2026-11-14 | Four watcher process tests failed in validation on #1374 and passed on independent reruns; keep the failure facts until a clean rerun or repair settles it, and label an unmeasured host-load cause as inference (#1444) |
| [2026-11-14-worker-repo-tags.md](2026-11-14-worker-repo-tags.md) | 2026-11-14 | Two valid repos differing only in punctuation shared a worker tag on #1876, so the second same-ID spawn failed; the tag is now one-to-one, held by punctuation-pair and escaped-literal regressions (#1882) |
| [2026-11-15-inline-guard-controls.md](2026-11-15-inline-guard-controls.md) | 2026-11-15 | Fix rounds on #1876 and #1877 added guards but described the failing run or posted no note; the fix procedure now points at §3's copyable fail-then-pass control, pasted as captured (#1884) |
| [2026-11-15-post-open-fragment.md](2026-11-15-post-open-fragment.md) | 2026-11-15 | #1838 reached CI with its fragment still `pr: TBD` and the PR-aware guard failed it; the build pass now fills the number right after opening and signs the moved head with a round-0 `ci-fix` note (#1844) |
| [2026-11-15-published-head-readback.md](2026-11-15-published-head-readback.md) | 2026-11-15 | The #1923 post-open note and `done:` named the opened head, not the head after the fragment fill; a signed merge-up corrected both, and the cause of the stale readback is unconfirmed (#1933) |
| [2026-11-15-session-builder-budget.md](2026-11-15-session-builder-budget.md) | 2026-11-15 | A shared build-pass step on #1908 fit the tmux brief but put the session builder brief 14 bytes over budget, caught only by full-suite CI; keep the compact step, the budget and the session-profile upgrade test as the regression (#1915) |
| [2026-11-15-status-connector-help-exit.md](2026-11-15-status-connector-help-exit.md) | 2026-11-15 | The status connector answered `--help` with a stderr usage error and exit 2 on #1905; repo-guard's `--help` sweep caught it, and help now prints to stdout with exit 0 while malformed arguments still exit 2 (#1914) |
| [2026-11-15-status-malformed-record.md](2026-11-15-status-malformed-record.md) | 2026-11-15 | A wrong-typed item URL in one status record raised `TypeError` through `status --all` on #1905 and hid a valid instance; the parser now diagnoses every wrong type, held by a field-by-type matrix and a CLI matrix with a valid control (#1913) |
| [2026-11-15-uncertain-remote-write.md](2026-11-15-uncertain-remote-write.md) | 2026-11-15 | The #1896 shared-status draft kept only a hash of the pending record and retried after a timeout, so a delayed write could overwrite a newer one; the receipt now keeps the exact pending body and an uncertain send stops publication until readback confirms it (#1912) |
| [2026-11-21-opened-pr-number.md](2026-11-21-opened-pr-number.md) | 2026-11-21 | #2006's builder labelled neighbouring #2005 and wrote `pr: 2005` from a predicted number before opening; the build pass now uses only the number opening returned for labels, fragment and posts (#2019) |

<!-- lessons:end -->
