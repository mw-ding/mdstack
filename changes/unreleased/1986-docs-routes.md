---
type: changed
issue: 1986
pr: 1999
date: 2026-11-18
box-skill: none
---

Docs routes: the docs index now has five reader routes (user, operator, contributor, reference, history), with the pack-author path folded into the contributor route and the old "by task" list folded into the reference and history routes. The runbook names itself the operator route and points to the other four, and links the metrics and regression-drill pages. The metrics sub-index links `prs.md`, `regression-drills.md` and the dated M25 records, so every page under `docs/` is reachable from the index.
