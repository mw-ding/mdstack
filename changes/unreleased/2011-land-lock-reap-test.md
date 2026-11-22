---
type: fixed
issue: 2011
pr: 2058
date: 2026-11-22
box-skill: none
---

Flaky land-lock reap test: the test fixtures' fake `tmux` no longer writes its state file back on a read, and a write replaces the file whole, so the land-lock holder's liveness poll can no longer undo a test's window removal or show a reader a truncated file. `test_missing_window_reaps_lock_even_when_pane_process_survives` waits on the reap with a bounded deadline instead of acquiring once, and its owner process outlives a loaded run. A new test pins that fake reads leave the state file byte for byte.
