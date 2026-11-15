---
type: changed
issue: 1419
pr: 1897
date: 2026-11-14
box-skill: none
---

Move each campaign scenario's notes to its own `docs/campaign-scenarios/<Axx>.md` with its source, spec or driver and sandbox fields, so rewrites of different scenarios never share lines. `docs/campaign-harness.md` keeps the common contract and a generated, sorted scenario index that `check-repo.py` checks (`scenario-index`: missing, duplicate, stale or dangling entries) and regenerates with `--fix`; the driver-only A29 stays listed through a `driver-only.txt` record beside the specs. The page's `merge=union` attribute and its guard are removed.
