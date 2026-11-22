---
type: changed
issue: 2082
pr: TBD
date: 2026-11-22
box-skill: none
---

`scripts/run-tests.py` starts the slowest test files first, in their recorded CI order (`SLOW_FIRST`), so a long file never starts at the end of a run. Its summary line now also reports the CPU seconds the test files used, a measure of whether more workers would help. Both aim to keep the full suite inside `repo-guard`'s 25-minute job limit without a workflow change.
