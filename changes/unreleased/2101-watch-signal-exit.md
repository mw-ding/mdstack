---
type: fixed
issue: 2101
pr: TBD
date: 2026-11-27
box-skill: none
---

`mdstack watch` now always exits with `128+signum` when a signal stops it: once it commits to the signal exit it blocks further `SIGTERM`, `SIGINT` and `SIGHUP`, so a signal repeated during cleanup or interpreter teardown no longer kills it by the signal (`-15`) or skips the PID file removal. The #272 guarantee is unchanged. This fixes the flaky `test_watch_second_signal_exits_at_once`, and a new signal-flood test covers the race.
