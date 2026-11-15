---
title: A detached test child inherited the `capture_output` pipe, so each launch waited about 60 s for EOF and CI timed out; give such children DEVNULL stdio (#1637)
date: 2026-11-11
status: applied
source: The M43 fix review on #1637 (round 2, ci-red repair), intake card #1649
---

# Detached fixture child and the capture pipe, 2026-11-11

## A detached fixture child must not inherit the capture pipe

- **Date:** 2026-11-11
- **Source / evidence:** The M43 fix review on #1637 (round 2, ci-red
  repair), intake card #1649, and the cancelled repo-guard CI run it cites.
  Repaired path: `wrapper_upgrade` in
  `dev/tests/environments/test-crew-upgrade.py`.
- **Finding:** The wrapper-upgrade fixture launched each fake pane process
  through `subprocess.run([python, -c, Popen(sleep 60)], capture_output=True)`.
  The `Popen` used `start_new_session=True`, so the `sleep` outlived its
  parent, but it inherited the parent's stdout and stderr, which were the
  pipes `capture_output` reads. `subprocess.run` then waits for EOF on those
  pipes, and EOF only comes when every writer closes them, so each launch
  blocked until the orphaned `sleep` exited, about 60 seconds. Two launches
  ran per CLI case. Detaching a child from its session does not detach it
  from inherited file descriptors.
- **Impact:** Repo-guard CI was cancelled at its 25-minute job limit with the
  upgrade test file unfinished; every other file reported `ok`. The builder
  published these measurements; they were not remeasured for this lesson:
  one launch took about 60 s before the fix and 0.16 s after, and the file
  took 1614.8 s before and 499.8 s after on the same loaded host. No product
  code was involved.
- **Fix:** Architecture, at the fixture: the detached child gets explicit
  `stdin`, `stdout` and `stderr` of `subprocess.DEVNULL`, so it holds no
  end of the capture pipe and `subprocess.run` returns as soon as the
  launcher prints the PID. The test assertions are unchanged; only the
  child's stdio changed. When a test helper starts a process meant to
  outlive the call, give it its own stdio (DEVNULL or a file) rather than
  the captured pipes. #1654 (merged as #1664) later added watcher-exit and
  cleanup waits to the same test file; that is a separate race, not this
  pipe, and it keeps the DEVNULL helper.
- **Status:** applied: the DEVNULL stdio is on `main` in `wrapper_upgrade`
  in `dev/tests/environments/test-crew-upgrade.py`, with a comment naming
  the pipe (#1637). Not encoded: no check flags a detached test child that
  inherits a capture pipe, so the class could recur in another fixture.
- **Linked issue/PR:** #1637, #1649
