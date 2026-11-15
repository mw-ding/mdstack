# A timed-out remote write left recovery unsafe in the shared-status draft, 2026-11-15

## Keep the exact pending bytes and stop until the outcome is known

- **Date:** 2026-11-15
- **Source / evidence:** Design change #1896 (closes #1889, M57 SD), repaired
  before merge; intake card #1912. The round-1 verdict at `2ab9d7f` raised
  two 🔴 findings against `docs/specs/shared-status.md`; the builder's round-1
  fix note at `ceb6f13` repaired both. The repaired rules are on `main` in
  §4 (receipt `pending`, `register` steps 3, 4 and 7) and §5 (write-phase
  table, Outcomes). ST, #1905 (closes #1313), built them with the
  regressions in `dev/tests/environments/test-status-shared.py`. Related:
  #1293 covers duplicate action effects, a different class.
- **Finding:** The draft receipt kept only `pending = {sequence,
  content_sha256}`, and the draft retried an update when a later readback
  still showed the confirmed record. First, a run stopped after writing
  `pending` but before the send left the bytes nowhere: the slot still held
  the old record, and fresh collector data and timestamps could not rebuild
  a body from its hash. Second, the draft read an old readback as a failed
  write, and claimed the local lock kept older writes from landing last.
  But a timed-out request can still apply later. If A (sequence N) times
  out, a retry B writes N, then N+1 confirms, A can land last and overwrite
  N+1 with N. No local lock fences a request whose client has exited.
  `register` had the same gap: a lost create not yet visible led to a new
  `registration_id` and a second create.
- **Impact:** Two 🔴 findings and one fix round on #1896, before ST built
  anything. Nothing unsafe reached `main` or a release.
- **Fix:** Architecture (correction level 1): the contract removes the
  unsafe retry. The receipt now keeps `pending = {op, state, sequence,
  content_sha256, body}` with the exact slot body bytes, written
  atomically before any send and validated on load (`receipt-invalid`
  otherwise). Each create or update is sent once and reports exactly one
  of `applied`, `rejected`, `not-sent` or `uncertain`. An `uncertain` send
  is never resent and nothing newer is built after it: later runs only read
  back, and confirm when the slot shows exactly `pending.body`. Fresh
  collector data never replaces a pending body. A pending `create` keeps its
  `registration_id`, and `register` never creates again for that instance.
  If the body never appears, the owner re-registers under a new
  `instance_id`. The old receipt, `pending` included, is archived, so a
  delayed write can land only in the abandoned old slot. The regressions
  are `Recovery` tests in `dev/tests/environments/test-status-shared.py`,
  run by PR CI's full suite: `test_delayed_and_never_applied_timeouts`,
  `test_uncertain_create_is_never_created_again`,
  `test_reregistration_then_the_old_send_lands_late`,
  `test_interrupted_runs_keep_the_original_pending_bytes` and
  `test_corrupt_pending_and_conflicting_slots`. They use the fake status
  API's `delay:K` and `never` faults in `dev/tests/status_testlib.py`.
- **Status:** applied: `docs/specs/shared-status.md` §4 and §5 carry the
  repaired contract on `main` (#1896); `environments/terminal/crew.d/` status
  code implements it and the named `test-status-shared.py` tests hold it
  (#1905). Not `encoded`: no `scripts/check-repo.py` or lint check enforces
  the condition. The regressions test this implementation, not every writer
  of a remote record.
- **Linked issue/PR:** #1896, #1889, #1905, #1912
