---
type: fixed
issue: 1970
pr: TBD
date: 2026-11-21
box-skill: none
---

Review readiness now takes a release cut PR's item from its non-closing linkage: with no closing reference, a body that passes `check-pr-linkage.py`'s release form (one `Release issue: #N` line, `Refs #N`, no closing keyword) binds item N, so a cut with a matching builder record is no longer parked as `item N conflicts with <empty>`. Builder identity, head, epoch and proof checks are unchanged, and a non-cut PR with no closing reference is still refused.
