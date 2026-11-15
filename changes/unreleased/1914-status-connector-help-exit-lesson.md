---
type: added
issue: 1914
pr: 1924
date: 2026-11-15
box-skill: none
---

Add a lesson on the status connector answering `--help` with a usage error on #1905: it printed usage to stderr with exit 2 until repo-guard's `--help` sweep in `test-check-repo.py` caught it. The repair prints help to stdout with exit 0 and keeps exit 2 for malformed arguments. Status `applied`: the sweep holds the help half, and nothing enforces the exit-2 half.
