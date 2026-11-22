---
type: fixed
issue: 1958
pr: 2059
date: 2026-11-22
box-skill: none
---

Builder brief: the build pass now renders the GitHub linkage check only for a GitHub change backend, the post-open fragment step only for a GitHub change backend or a declared `[release]`, and its local-check list from a new optional `builder.local_checks`. Unset, a GitHub render keeps today's list and another backend names "the project's own checks from its `AGENTS.md`". GitHub renders are byte-identical.
