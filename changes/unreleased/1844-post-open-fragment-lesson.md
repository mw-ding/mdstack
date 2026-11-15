---
type: added
issue: 1844
pr: 1908
date: 2026-11-15
box-skill: none
---

Add a lesson on a new PR that reached CI with its changelog fragment still `pr: TBD`, and name the post-open step in the builder build pass: right after opening, set the fragment's PR number, pass `check-changelog-pr.py`, push and post a round-0 `ci-fix` note at the new head, which review readiness already waits for. The PR-aware guard stays the enforcement; CI on the opened head can still race the number.
