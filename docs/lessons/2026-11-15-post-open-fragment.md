# A new PR reached CI with its fragment still `pr: TBD`, 2026-11-15

## Fill the PR number right after opening, then sign the moved head

- **Date:** 2026-11-15
- **Source / evidence:** Helper change #1838 (closes #238, M54 B2): the
  first repo-guard run on the opened head failed (Actions run 43431296230),
  the builder's round-0 `ci-fix` note at `b248eb9`, the round-1 verdict at
  the same head citing green CI (run 43431698819), and intake card #1844.
  Related: the post-open linkage correction on #1822, not counted as a
  second failed run. Affected files: `changes/unreleased/<issue>-<slug>.md`
  fragments, `scripts/check-changelog-pr.py` (`fragment_pr_errors()`) and
  `templates/policy/builder/build-pass.md` step 4.
- **Finding:** A fragment is written before its PR exists, so it carries
  `pr: TBD` (`CONTRIBUTING.md`, Changelog). #1838 opened with that
  placeholder. The PR-aware guard, `check-changelog-pr.py --pr 1838`, failed
  the first CI run because the fragment it adds has `pr: TBD`, not
  `pr: 1838`. The builder then committed `b248eb9`, which changed only that
  field, and posted a round-0 `ci-fix` note at it. CI went green and the
  verdict passed at that head. The build procedure named no post-open step:
  filling the number was left to the contributing rule and to red CI.
- **Impact:** One red CI run and one extra push and note on #1838, before
  review. Nothing wrong merged: the guard caught it, and main CI on the
  merge commit (run 43435222419) passed.
- **Fix:** The builder build pass now names the step. Right after opening,
  before `done:`, set the fragment's `pr:` to the new number, pass
  `scripts/check-changelog-pr.py --base origin/<default-branch> --pr <pr>`,
  push, read the new head, and post a round-0 `ci-fix` note at it. Since
  #1878, review of a head pushed after opening, before any verdict, waits
  for that note (`docs/runtimes/tmux.md`, review readiness), so the step
  cannot be skipped silently. The PR-aware guard stays the enforcement, and
  no new changelog automation is added. CI on the opened head can still
  fail on `TBD`: the number is assigned only when the PR is opened, so that
  first run races the fill. A red first run with a green filled head is
  expected, not a new failure.
- **Status:** applied: `templates/policy/builder/build-pass.md` step 4
  carries the post-open step on `main`; `scripts/check-changelog-pr.py`
  enforces the number in PR CI. No `scripts/check-repo.py` check enforces
  the step itself, so it is not `encoded`.
- **Linked issue/PR:** #1844, #1838, #1878
