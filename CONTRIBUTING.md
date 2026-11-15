# Contributing

This repo is the reviewed source of truth for the crew framework. Changes arrive
by PR, built by the crew through the normal pipeline (spec R7). This page is the
iteration process.

## From lesson to PR

1. **Record the lesson.** Write a dated entry under
   [docs/lessons/](docs/lessons/README.md) in the documented entry format, with
   its evidence, impact, proposed fix and status.
2. **Raise an issue.** The coordinator turns each actionable lesson into an
   issue with a goal, acceptance criteria and a link to the spec. Link the issue
   from the lesson entry.
3. **Land it by PR.** The builder opens a non-draft PR that closes the issue. The
   normal review loop applies: CI, review, validation, then merge by the
   synthesizer. Update the lesson entry's status and linked PR in the same PR.

Protocol and template changes follow the
[protocol freeze](docs/protocol.md#protocol-freeze).

## Spec changes

Changes to `docs/specs/framework.md` are spec changes. They take the spec
path in [protocol Stages](docs/protocol.md#2-stages) and merge only with the
permission in [stage 7](docs/protocol.md#7-merge-gate-synthesizer).

## Doc moves

A PR that moves, extracts, splits or quotes prose into another file (a doc
move under [documentation principle 4](docs/README.md#documentation-principles),
an onboarding or quickstart extract, a module split) compares the moved text
with its source before review, sentence by sentence. Check every qualifier:
the role or trigger it applies to, its runtime or backend scope, conditions
(`when`, `only`, `unless`, `before`), exceptions and the scope of each
`never` or `every`. The builder records the comparison in the PR body under
`## Doc move comparison`: one row per moved rule with the source
`path:line`, the destination `path:line` and `kept` or what changed. A
qualifier the destination drops or widens is a defect to fix in the same PR;
a contradiction found in the source is filed as its own correction issue
(#1125). Green checks do not
prove this: `check-repo.py` checks links and anchors, not meaning.

## Two copies, one change

The box skills are the **live** copies the bots load; this repo is the
**reviewed** copy. Keep them in sync in the same change per
[spec R4](docs/specs/framework.md#2-requirements).

Say in the PR which way it was mirrored, or that there is no box skill change.
The live copy is the [renderer](scripts/README.md#renderer) output, deployed by
the coordinator. Mirror holds follow the
[gate registry](docs/protocol.md#gate-registry), the
[mirror hold gate](docs/runtimes/grok-bot.md#mirror-hold-gate) and, on tmux,
[mdstack train](docs/runtimes/tmux.md#mdstack-train).

## CHANGELOG

Every PR records its change as a fragment instead of editing
[CHANGELOG.md](CHANGELOG.md): one new file `changes/unreleased/<issue>-<slug>.md`
(lowercase slug) with front matter, then one paragraph of entry text, the
change:

```markdown
---
type: fixed
issue: 123
pr: 456
date: 2026-10-31
box-skill: none
---

What changed and why, in one paragraph.
```

- `type`: `added`, `changed`, `removed`, `fixed` or `security`, the Keep a
  Changelog heading the entry goes under.
- `issue`: the issue number, as in the file name.
- `pr`: the PR number. Write `TBD` until the PR opens, then fill it in with a
  follow-up commit before review: on a PR, CI fails a fragment the PR adds or
  changes whose `pr` is `TBD` or another PR's number (a merge train only for
  `TBD`).
- `date`: `YYYY-MM-DD`, the merge date in America/Los_Angeles; for an unmerged
  PR, the date it was written.
- `box-skill`: whether the box skill copy was mirrored, for example `none` or
  `deferred to #140`.

Use no relative links in the entry text: their paths break when it moves into
`CHANGELOG.md`. `scripts/check-repo.py` checks every fragment's format.

CI also runs `scripts/check-changelog-pr.py` against the PR's merge base.
It fails unless the PR adds a new `changes/unreleased/<issue>-<slug>.md`
fragment or changes only exempt paths. The exempt path list lives in that
script's `EXEMPT_PATHS`; it covers cut output, fragment-only changes,
verification artifacts and core memory (`memory/`). An empty diff, including a CI-only train PR whose
changes are already in its base, also passes. A train with content changes
needs a fragment like any other PR. Pushes to `main` skip the requirement.
Editing an existing fragment does not satisfy a PR that changes other content.
A release cut PR may also carry a small release-pipeline fix without a
fragment, since `scripts/release-check.py` refuses a cut that leaves one. This
applies only when the diff is a cut (`CHANGELOG.md` changed, fragments deleted,
a new top version section) and every other changed path is in the script's
`RELEASE_PATHS`: `.github/workflows/release.yml`, `.github/workflows/ci.yml`,
`scripts/release-*.py` and `scripts/changelog-cut.py`. Write the fix's entry
directly into the new version section, in the cut's entry format with
`(issue #<issue>, PR #<pr>, <date>)`; the guard requires a new entry naming an
issue beyond the ones the deleted fragments produce. A cut that also changes any
other path still needs a fragment, which fails the release check, so ship that
change in its own PR.
Released sections are immutable. Every `##` (level-two) section below
`## [Unreleased]` in `CHANGELOG.md` stays byte for byte as released,
whitespace and line endings included: a PR, a cut included, may only add a
new version section on top and edit `[Unreleased]`. The same guard
fails a PR that rewords, moves or deletes a released section or entry, before
any exempt-path or fragment check, so a new fragment does not satisfy it. Fix
the red check by restoring the released section and recording the correction
in a new fragment for the next release (#1306, #1417); a late fragment goes into
the next cut, not into an already cut section. CI is never waived for it.
To run locally: `python3 scripts/check-changelog-pr.py --base origin/main`.

At the cut, `scripts/changelog-cut.py <version>` turns each fragment into one
entry, `<text> (issue #<issue>, PR #<pr>, <date>) Box skill copy: <box-skill>.`,
so every entry still has its change, date, PR number and box skill status
(spec R5). It puts them under their headings in the new version section,
together with any entries already under `[Unreleased]` (those stay valid),
then deletes the fragments. It refuses a fragment that is malformed or still
says `pr: TBD`, and `scripts/release-check.py` refuses a release while any
fragment is left.

## Shared files

No new shared append-hotspot files: one file per item, or a generated
aggregate. A file that most PRs edit at the same place makes each merge put
the next PR in conflict, which costs a builder merge-up and a re-check
([#325](https://github.com/mw-ding/eng-crew/issues/325)). Per-item files
already exist for the changelog ([fragments](#changelog)) and for script usage
(a script's module docstring). The index files follow the same rule:

- `scripts/deliverables.txt`, `scripts/required-docs.txt` and the table rows of
  `docs/README.md` are sorted, one entry per line. Put your entry at its sorted
  place, never at the end, so concurrent PRs touch different lines;
  `check-repo.py` fails on an unsorted file (`index-order`).
- The inventory table in `docs/deliverables.md` is generated from the manifest,
  `scripts/deliverables.txt`. Add the manifest row (the last column is the
  Why), then run `python3 scripts/check-repo.py --fix`; never edit the table by
  hand (`check-repo.py` fails on a stale one, `index-stale`).
- `docs/README.md` has one row per doc and a row for every deliverable doc
  (`docs-index`).
- Each campaign scenario has its own `docs/campaign-scenarios/<Axx>.md`. Edit
  that file, then run `python3 scripts/check-repo.py --fix`; the scenario index
  in `docs/campaign-harness.md` is generated from those files and fails closed
  on a missing, duplicate, stale or dangling entry (`scenario-index`). A
  scenario with a driver and no JSON spec is also listed in
  `dev/tests/scripts/fixtures/campaign/driver-only.txt`. Two PRs
  whose index rows conflict: merge `main`, then run `--fix`.
- Two PRs that add entries at the same sorted place (adjacent names) still
  conflict: merge `main`, keep both lines, run `--fix`. A `merge=union`
  attribute is not used: it only resolves a merge that runs locally, so a
  merge-up or a [merge train](docs/runtimes/tmux.md) could look clean while
  GitHub still reports the conflict (train 4, #321).

## No secrets

Never commit tokens, API keys, auth headers, email addresses, private chat
quotes or real box paths (spec R1). Refer to credentials by mechanism only, and
use placeholders such as `<owner>/<repo>` and `<state-dir>` (spec R2). Use role
names such as coordinator, builder, reviewer-validator and synthesizer.

## Decisions needing the user

When work is blocked on a decision only the user can make, the coordinator labels
the item `crew:needs-md` and raises it with:

- a recommended default, and
- a deadline, after which the default applies unless the user says otherwise.

Requests are batched into one digest per day rather than sent one by one. This
keeps decisions from stalling the pipeline for hours (see
[the bottleneck analysis](docs/lessons/2026-10-19-bottlenecks.md)).

## Checks

<!-- Script usage for local checks is added here later. -->

CI runs markdownlint and an offline link check on every PR and on `main`.

Run the test suite with `python3 scripts/run-tests.py`: every
`dev/tests/*/test-*.py` once, in parallel (`-j N` workers, default the CPU count
up to 8). It prints each file's duration and the slowest files, shows the
output of every failing file and exits non-zero if any file fails. Pass test
files to run only those, for example the targeted set of a build
([AGENTS.md](AGENTS.md)). CI's `repo-guard` job runs the full suite this way.
The runner isolates tmux: each file runs without `TMUX` or `TMUX_PANE` and with
its own private `TMUX_TMPDIR`, and a failing file's output goes to a log named
on its `FAIL` line.

A new or changed script documents itself in its module docstring (a script
you run also gets a `Usage:` line there, which `--help` prints), never in a
shared table that every scripts PR edits; `scripts/check-repo.py` checks this
([per-script docs](scripts/README.md#per-script-docs)).
