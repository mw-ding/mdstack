---
type: added
issue: 1871
pr: TBD
date: 2026-11-15
box-skill: none
---

A reviewer pool's relayed review, validate or recheck changes event no longer looks like a delivered fix at the builder lead. The new `mdstack lead relay builder ID` writes it as the typed wait `waiting: #<n> fix id=<id>`, awaiting coordinator fix, and settles it with `done:` only once a coordinator `fix` for that PR and head reached a worker (its acknowledgement, or a fix pass spawned at that head) or the PR closed or moved; it never sends or starts anything and refuses, writing nothing, an id that is not the repo's acknowledged pending relay or whose event is missing. A `fix` wait's token-free fingerprint includes the PR's `fix` handoffs and receipts, so the coordinator's same-head `fix` wakes it. The coordinator's explicit `fix` stays the only fix trigger; the builder-lead and coordinator recipes and the tmux runtime doc say so.
