---
title: Merge-ups must not burn review rounds; an ack cannot satisfy the merge gate, so a clean merge-up after an approval gets a formal re-approve (#20)
date: 2026-10-20
status: applied
source: Decided by the coordinator on Oct 20, 2026 after PR #15; refined after the review of #16
---

# Lessons: merge-ups must not burn review rounds (Oct 20, 2026)

One lesson from the review rounds of PR #15 and the review of the routine
templates PR (#16). Entries follow the lessons-log format: date, source,
finding, impact, fix, status and linked issue/PR. Sanitized per spec R1.

## Entries

### Merge-ups consumed rounds, and the ack exception split the merge gate

- **Date:** 2026-10-20
- **Source / evidence:** Decided by the coordinator on Oct 20, 2026 after PR #15,
  whose head had to merge `<default-branch>` in repeatedly. Refined the same day
  after the review of #16 found that a COMMENT ack cannot satisfy the merge
  gate's formal-approval requirement, and the #16 templates had shipped an
  ack-based exception.
- **Finding:** The protocol required a full verdict on every merge-up, so a
  merge-up on a PR still waiting for a fix drew another `REQUEST_CHANGES` and used
  up a round. The #16 templates worked around this with a
  COMMENT ack saying "verdict stands", which the synthesizer accepted as a
  merge-gate exception and the sweeper counted as "approved". A COMMENT review
  is not a formal approval and fires no `review-approved`.
- **Impact:** Merge-ups would otherwise burn rounds toward the 3-round cap. The
  ack exception split the gate into two paths and relied on a sweeper nudge for
  the merge to happen. No numbers are recorded in the sources.
- **Fix:** A merge-up push (its only new commit merges `<default-branch>` into
  the PR branch) never uses up a round. The reviewer-validator checks the
  conflict-resolution hunks and reruns the acceptance checks at the new head. A
  clean merge-up after an `APPROVE` gets a formal merge-up re-approve at the new
  head with the same round number, which fires `review-approved`. A clean
  merge-up after `REQUEST_CHANGES` gets a COMMENT ack with `round=n/a
  verdict=n/a` and no label change. A conflict resolution that changes behavior
  or content gets a normal round. The ack-based exception is removed from the
  reviewer, synthesizer and sweeper templates; the merge gate is again only a
  formal `APPROVED` review at head. See
  [the protocol](../protocol.md#6-duties-on-wake-all-roles) and the
  [merge gate](../protocol.md#7-merge-gate-synthesizer).
- **Status:** applied. `docs/protocol.md` §6 and §7, reviewer, synthesizer and
  sweeper templates (#32).
- **Linked issue/PR:** #20, #15 and #16
