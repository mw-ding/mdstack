---
title: #2006's builder labelled neighbouring #2005 and wrote `pr: 2005` from a predicted number before opening; the build pass now uses only the number opening returned for labels, fragment and posts (#2019)
date: 2026-11-21
status: applied
source: PR #2006 builder note and repo-guard run 44464031994, intake card #2019
---

# A builder wrote to a predicted PR number before opening, 2026-11-21

## Use only the number opening returned

- **Date:** 2026-11-21
- **Source / evidence:** PR #2006: the builder's signed note records a
  predicted number `2005`, an actual number `2006`, and a `crew:in-review`
  label applied to neighbouring #2005 at 05:16:28Z. Repo-guard run
  44464031994 failed `check-changelog-pr` with `has pr: 2005, want pr: 2006`.
  Intake card #2019. Related: #2005's own fragment mismatch, not counted as a
  second wrong-label write. Affected file:
  `templates/policy/builder/build-pass.md` step 4.
- **Finding:** The builder guessed the next PR number and used it for a side
  effect before the PR existed. The guess was taken by a concurrent change,
  so the label landed on another builder's PR and the fragment carried the
  wrong number. The build pass said to fill the number after opening
  (#1844) but did not forbid writing to a predicted one.
- **Impact:** One red CI run and a fragment repair on #2006, and one stray
  label on #2005, left in place because #2005's builder used it. Nothing
  wrong merged: the PR-aware guard caught the fragment.
- **Fix:** Build-pass step 4 now says to use only the number that opening
  the change returned for labels, the fragment and posts, never a predicted
  one. The post-open fragment step and its lesson
  (`2026-11-15-post-open-fragment.md`) stay. `check-changelog-pr.py` still
  catches a wrong fragment number; no check catches a label on the wrong PR.
- **Status:** applied: `templates/policy/builder/build-pass.md` step 4
  carries the rule on `main` and the rendered builder briefs include it. No
  check enforces the label side, so it is not `encoded`.
- **Linked issue/PR:** #2019, #2006
