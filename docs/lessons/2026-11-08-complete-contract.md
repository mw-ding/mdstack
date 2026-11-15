---
title: 13 repaired cards where a gate or action read part of its contract and took the gap as permission; fail closed on the whole contract (#1342)
date: 2026-11-08
status: applied
source: 13 repaired intake cards, group H01 of the #1337 clustering, retained by #1342
---

# Complete gate and action contracts, 2026-11-08

## Fail closed on the whole contract, not the part a consumer reads

- **Date:** 2026-11-08
- **Source / evidence:** 13 repaired intake cards, group H01 of the #1337
  clustering, retained by #1342. Cards and repairs: #1134 (#979), #1135
  (#981), #1136 (#984), #1137 (#991), #1144 (#1008), #1147 (#996), #1205
  (#1154, #1119), #1206 (#1163), #1292 (#1275), #1293 (#1280, #1277), #1294,
  #1295 and #1296 (#1280).
- **Finding:** Each consumer read only part of a gate or action contract and
  treated what was absent as permission. The gaps were a linked-item field a
  fixture supplied but the train view never requested (#1134), unresolved
  placeholders in an optional classifier command (#1135), a land status cut to
  its first line (#1136), a diff cut inside a file header read as clean
  (#1137), a resume that skipped the landed-revision CI step (#1144), a spec
  path without its label (#1147), a changes request after the verdict
  (#1205), a hold gated on a retired option (#1206), a lifecycle path that
  bypassed the ownership guard (#1292), a keyed retry that repeated its side
  effect (#1293), a heartbeat with no run record (#1294), `unsupported`
  answered before parsing (#1295) and a replayed ownership read (#1296).
- **Impact:** Each gap let a gate pass or an action run when it should have
  refused. Examples are a fresh land request, an express train past a spec
  path, a reviewer dispatched on a held change and another actor's claim
  rewritten. No card measured time lost.
- **Fix:** Types / schemas, one regression test per site. Request and validate
  every field the consumer uses. Treat extra, truncated or missing input as
  unknown, never as clean. Parse before answering `unsupported`. Re-read live
  authority (ownership, holds, later requests) at the moment of action and
  never replay it. Test fakes return only the fields that were requested. Each
  card's regression test survives the 7.0 moves and passes at `main`
  `739fdbe`. Examples:
  `dev/tests/environments/test-crew-train.py` `SelfgateKeys` and
  `LaterChangesRequest`, `dev/tests/environments/test-crew-land.py`
  `test_unknown_status_never_requests`, `dev/tests/core/test-crew-config.py`
  `SensitiveDiffTest` and `dev/tests/environments/test-crew-action.py`.
- **Status:** applied: every repair is on `main`, and each card's regression
  test runs under `dev/tests/` (#1342 survival table). No leftover
  prevention requirement; three soft limits stay accepted. #1294's
  session-runtime `unsupported` declaration is in the docs only. #1293 has no
  explicit retry-across-restart case. #1144's CI wait is a rendered brief
  step.
- **Linked issue/PR:** #1342; the direct-land route gap #1339 is separate
  and not covered by #1144's repair.
