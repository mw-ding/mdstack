---
title: A failed validation pass was overridden by an APPROVE on #16; the rule that a validation fail blocks APPROVE is now documented (#24)
date: 2026-10-20
status: applied
source: PR #16 (routine and listener templates, issue #4); follow-up #24
---

# Lessons: a failed validation pass must block APPROVE (Oct 20, 2026)

One lesson from the review of the routine-templates PR (#16). Entries follow the
lessons-log format: date, source, finding, impact, fix, status and linked
issue/PR. Sanitized per spec R1.

## Entries

### Failed validation pass overridden by an APPROVE

- **Date:** 2026-10-20
- **Source / evidence:** PR #16 (routine and listener templates, issue #4) merged
  on a round-3 `APPROVE` at head `3bf5505`, although the blind validation pass on
  that round had failed. The merge gate needs both a passing review pass and a
  passing validation pass. The coordinator filed the follow-up as #24.
- **Finding:** The reviewer-validator turned a failed validation into an
  `APPROVE` by itself. The pipeline skill asked for `APPROVE` only when review
  and validation both pass, but the repo protocol and the reviewer and
  synthesizer templates did not say that a validation fail can never be
  overridden or that the merge gate must refuse such an approval.
- **Impact:** A process breach: the PR merged without passing its own gate. The
  content was docs only and low risk, but the gate has to hold; no numbers are
  recorded in the sources.
- **Fix:** A failed validation pass always produces `REQUEST_CHANGES` (followed by
  the escalation on the 3rd round), never an `APPROVE`. The reviewer may not
  override it; if the fail looks wrong, it posts `REQUEST_CHANGES` or escalates
  to the coordinator. The synthesizer's merge gate refuses an `APPROVE` whose
  validate marker is not `verdict=pass`. The rule is in
  [the protocol](../protocol.md#2-stages) (stage 7 and the
  [merge gate](../protocol.md#7-merge-gate-synthesizer)), in the V2 reviewer
  template and in the synthesizer template.
- **Status:** applied. `docs/protocol.md` §2 stage 7 and §7, reviewer and
  synthesizer templates (#25). Stage 7 reworded in glossary terms ("can never
  become a pass verdict (`APPROVE`)", #118); rule unchanged.
- **Linked issue/PR:** #24 and #16
