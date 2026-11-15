---
title: Failures die in chat; intake queue plus repo lesson store plus a scoped harness PR, with a weekly stuck sweep as the one live trigger (#89)
date: 2026-10-29
status: applied
source: Issue #89 (M11) and the lessons already in this log
---

# Lessons: self-improve intake

## Entries

### Failures die in chat; intake queue, repo lesson store, scoped harness PR

- **Date:** 2026-10-29
- **Source / evidence:** Issue #89 (M11) and the lessons already in this log.
  Earlier incidents (the watch-attach stall, the merge-gate race, the
  synthesizer hold race) each became a lesson only because someone remembered
  to write one after the fact; stuck and blocked PRs left no record at all.
- **Finding:** Failures and near-misses surfaced in chat and PR threads and
  stayed there. Nothing turned them into a backlog of harness changes, and
  nothing separated a product-local quirk from a crew-wide gap, so the same
  failure class could recur across repos unnoticed.
- **Impact:** Lessons landed late or not at all, and a recurring failure class
  was only seen once a human connected the repeats. The source gives no number.
- **Fix:** Intake protocol in [self-improve.md](../self-improve.md): triggers
  (event and schedule), a short candidate card
  ([template](../../templates/intake-candidate.md)) filed as an eng-crew issue,
  coordinator accept or close, the lesson store in the repo (this directory
  plus the findings buffer), a `repo:` vs `crew:` scope tag with a promotion
  rule, and an accepted card shipped as a normal PR. One trigger is real in v1:
  the weekly stuck sweep, via the offline helper `scripts/intake-sweep.py`
  (a tested script prints the cards, so listing stuck PRs does not depend on
  memory), with `scripts/test-intake-sweep.py` run in the CI
  `repo-guard` job and the doc, template, helper and this lesson pinned in
  `scripts/required-docs.txt` (level 4 for the pinned files only). The rest
  is level 5, prose only, because it depends on
  live GitHub state, timing and coordinator judgement that an offline repo
  check cannot see: whether a card was filed, whether Scope is right, whether a
  duplicate exists, and whether an accepted card got its lesson. The other three
  triggers (`REQUEST_CHANGES` or reopen, red CI after the builder reported
  ready, tripwire issue) are documented recipes only; no check pins their use.
- **Status:** applied. `docs/self-improve.md`,
  `templates/intake-candidate.md`, `scripts/intake-sweep.py` and the weekly
  intake note in the stuck-PR sweeper template land with this lesson. Not
  `encoded`: the helper prints candidates, but no check enforces that cards get
  filed or scoped.
- **Linked issue/PR:** mw-ding/eng-crew#89
