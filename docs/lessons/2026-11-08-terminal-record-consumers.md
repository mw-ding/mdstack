---
title: 7 repaired cards where a terminal record was lost downstream; match records by stable identity and test each consumer with the runtime record (#1342)
date: 2026-11-08
status: applied
source: 7 repaired intake cards, group H06 of the #1337 clustering, retained by #1342
---

# Terminal records reach their consumers, 2026-11-08

## A record must reach every consumer, matched by stable identity

- **Date:** 2026-11-08
- **Source / evidence:** 7 repaired intake cards, group H06 of the #1337
  clustering, retained by #1342. Cards and repairs: #1141 (#1007), #1145
  (#1009), #1195 (#1063, #1186), #1196 (#1063), #1197 (#1065, #1071), #1199
  (#1081, #1073), #1070 (#1150, through #1050).
- **Finding:** A terminal or derived record was produced correctly and then
  lost or mismatched downstream:
  - a later unanswered classification dropped an earlier answered record
    from triage accuracy (#1141);
  - handoff parsed change handles with the item pattern, so change runs and
    claims vanished (#1145);
  - a dependency merge did not wake the coordinator after cleanup (#1195);
  - the watcher compared wake records by full equality, so routing
    annotations hid a merge wake (#1196);
  - a reviewer kept its slot after a merge outside the runtime (#1197);
  - the scheduler never received `red_fixes`, so a red-main repair ranked
    class 7, not class 1 (#1199);
  - a reaped reviewer's schedule grant came back as a live reservation
    (#1070).
- **Impact:** Dependents waited for the backstop, slots stayed held until a
  manual reclaim or `reservation_ttl`, a red-main fix queued behind normal
  work and accuracy metrics lost decisions. No card measured time lost.
- **Fix:** CI check per consumer. Key each record by stable identity, never by
  full equality or a borrowed pattern. Test each consumer with the record as
  the runtime produces it: produce it, annotate or evolve it the way the
  runtime does, and assert the consumer still sees it. The regression tests
  survive at `main` `739fdbe` and pass:
  `dev/tests/scripts/test-triage-metrics.py`
  `test_accuracy_keeps_answered_applied_records_once`,
  `dev/tests/environments/test-crew-handoff.py`
  `test_runs_and_claims_by_native_change_id`,
  `dev/tests/environments/test-crew-route.py`
  `test_dependency_merge_reaches_coordinator_after_cleanup` and
  `test_watcher_wakes_coordinator_on_dependency_merge`,
  `dev/tests/environments/test-crew-reviewer-pool.py`
  `test_stale_done_after_external_merge_is_reaped_once`,
  `dev/tests/environments/test-crew-schedule.py`
  `test_open_main_red_issue_and_its_pr_rank_class_1_by_default` and
  `dev/tests/environments/test-crew-spawn.py`
  `test_started_run_ends_its_own_reservation`.
- **Status:** applied: every repair is on `main` and each regression test runs
  (#1342 survival table). No card's prevention requirement is left.
- **Linked issue/PR:** #1342. #1070's fix does not cover the later capacity
  incidents in #1266. The run-generation reports #819 and #1092 are separate.
