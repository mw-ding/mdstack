---
type: fixed
issue: 1948
pr: TBD
date: 2026-11-15
box-skill: none
---

The lessons index test X1.7 now checks that a second `check-repo.py --only lessons --fix` on a copy of the live lessons tree changes nothing and leaves exactly one row per lesson, and that the live tree plus a valid lesson with no row passes the plain check unchanged. It no longer asserts equality with the committed index, so a lesson-only PR passes CI without editing `docs/lessons/README.md`.
