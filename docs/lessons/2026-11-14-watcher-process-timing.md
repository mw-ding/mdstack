---
title: Four watcher process tests failed in validation on #1374 and passed on independent reruns; keep the failure facts until a clean rerun or repair settles it, and label an unmeasured host-load cause as inference (#1444)
date: 2026-11-14
status: open
source: The round-1 verdict on #1374 (closes #1092, M36), intake card #1444
---

# Watcher process tests failing during validation, 2026-11-14

## Keep a timing failure's facts until a clean rerun or a repair settles it

- **Date:** 2026-11-14
- **Source / evidence:** The round-1 verdict on #1374 (closes #1092, M36),
  the builder's round-1 fix note, the round-2 verdict on the same head, and
  intake card #1444. Head `356377d`, base `3d275f7`. Affected file:
  `dev/tests/environments/test-crew-watch.py`.
- **Finding:** The round-1 validator ran
  `python3 dev/tests/environments/test-crew-watch.py` at head: 49 tests in
  1675.780 s, `FAILED (failures=2, errors=2)`. The four were
  `test_watch_never_types_into_a_coordinator_prompt` (a `communicate` call
  hit its 10 s timeout), `test_watcher_removes_only_its_own_pid_file`
  (`watcher.pid` missing), `test_watch_reexecs_before_routing_with_a_new_profile_key`
  (exit 1, `reload_probe: unknown key`) and `test_watch_sighup_like_sigterm`
  (return code -1, expected 129). The validator's isolated retry of two of
  them took 184.145 s and still failed. The prompt timeout came back for five
  prompt cases, but the profile reload passed. The PR changed only
  the run identity on status wakes and the reap guard in `route.py`; none
  of the four tests calls that code. The validator recorded the failure as
  `changes` and did not decide whether host load or an existing defect caused
  it. The builder then ran the four tests at head and at base in parallel,
  and both runs passed in about 73 s. The full watch suite passed (49 tests,
  417.767 s) and so did the route suite (48 tests, 334.984 s). The builder
  reported a host load average of about 140–190 and called the failure a
  host-load flake. That cause is the builder's **inference**: no read here
  measured load against the failures. The round-2 validator then
  reran the four tests and both suites independently at the same head
  (watch 49 tests OK in 514.080 s, route 48 OK in 383.465 s). That run
  cleared the failed checks for the verdict and said explicitly that it did
  not establish host load as the cause.
- **Impact:** One extra review round on #1374. The run time of the same
  watch suite varied about fourfold across the published runs (1675.780 s,
  417.767 s, 514.080 s). These are the published numbers, not remeasured
  for this lesson. No product regression was found.
- **Fix:** Prose only, because the failure depends on host timing and load,
  which no repo-file check can see. The rule is already in
  [verification.md](../verification.md): a claim is no stronger than its
  read ([Claim scope](../verification.md#claim-scope)), and independently
  reproduced failures change the verdict while CI state alone does not
  ([Reviewer-validator](../verification.md#reviewer-validator)). Applied
  here: when a process-control test fails during validation, record the
  command, head, base, host load if read and the test and suite timings.
  Keep the failure open until a clean independent rerun at head clears it
  or a scoped repair fixes its cause. Label any cause that was not measured
  as inference. Do not widen timeouts, retry until green or add a
  speculative process repair to the PR under review. A green rerun clears
  the check but does not confirm a cause.
- **Status:** open: #1374's round-2 validation cleared the failed checks
  with a clean independent rerun, but the cause is unsettled. The fixed
  10 s `communicate(timeout=10)` limits in
  `dev/tests/environments/test-crew-watch.py` remain at base `d29d4b9`
  and are an accepted limitation, not repaired. No check enforces the
  rule.
- **Linked issue/PR:** #1374, #1092, #1444
