---
type: fixed
issue: 1878
pr: 1904
date: 2026-11-14
box-skill: none
---

A fresh review no longer races a builder's fix evidence: the reviewer pool starts a review pass only once the head's published, builder-signed record for its operation is readable (the PR body for the opened head, else a `fix`, `ci-fix` or `merge-up` note at head after the newest verdict or reset, with inline proof or a reasoned N/A), checked live on every admission path before any claim, reservation or spawn. Until then the request is a `waiting: #<n> evidence` wait that a new builder note at head wakes, even when the builder's `done:` was lost; there is no time-based waiver. The builder fix procedure now captures proof before the push and posts the note at once.
