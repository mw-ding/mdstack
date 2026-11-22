---
type: changed
issue: 2082
pr: 2084
date: 2026-11-22
box-skill: none
---

A full `scripts/run-tests.py` run first writes the repo's bytecode, since `mdstack` turns bytecode writing off and each CLI call a test made recompiled its modules. The runner also starts the slowest test files first, in their recorded CI order (`SLOW_FIRST`), so a long file never starts at the end of a run. Its default worker count is now 1.5 times the CPU count (still at most 8), since test files mostly wait on subprocesses, and its summary line now also reports the CPU seconds the test files used, a measure of whether more workers would help. Both aim to keep the full suite inside `repo-guard`'s 25-minute job limit without a workflow change.
