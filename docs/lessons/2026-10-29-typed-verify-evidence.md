---
title: Verdicts rested on diff and CI; typed runtime evidence per shape (web, CLI, service, API, mobile) is now a merge gate with builder, validator and synthesizer duties (#83)
date: 2026-10-29
status: applied
source: Gap-table row 8 (Verification / prove-it) in the framework gap analysis, and the validation pass in protocol §2
---

# Lessons: typed runtime evidence as a merge gate

## Entries

### Verdicts rested on diff and CI, not on proof the change works

- **Date:** 2026-10-29
- **Source / evidence:** Gap-table row 8 (Verification / prove-it) in the
  framework gap analysis, and the validation pass in
  [protocol §2](../protocol.md#2-stages), which says to exercise each criterion
  but names no artifact type. Related incident:
  [2026-10-20-evidence-on-pr-head.md](2026-10-20-evidence-on-pr-head.md).
- **Finding:** The reviewer-validator mostly signed off on the diff and green CI.
  Nothing said what proof a CLI, web, service, API or mobile change should
  carry, or that a missing artifact blocks the merge, so a change could be
  approved without showing it works for the kind of software it is.
- **Impact:** Risk of merging behaviour that was never exercised. The source
  gives no count of affected PRs.
- **Fix:** Level 4 (CI check) for the table, prose for the judgement.
  [docs/verification.md](../verification.md) defines the five shapes (mobile
  fully specified, adapter TBD), the artifact, verifier check and merge
  condition for each, the docs-only N/A rule and fail-open. Builder, validator
  and synthesizer duties are in `docs/roles.md`, the V1/V2/S1/B1 templates, and
  protocol §3, §7 and the Gate registry. Two adapters ship under
  `templates/evidence/` (CLI exit/stdout, web screenshot). The
  `check-repo.py` rule `verification-shapes` fails when the shape table lacks
  any of the five shapes. The rest is prose only, because whether a PR changes
  behaviour and whether an artifact matches a claim is judgement on live PR
  content, which no offline check can see.
- **Status:** applied. `docs/verification.md`, protocol §7 and Gate registry,
  and `templates/evidence/` in #83; the shape table is guarded by
  `verification-shapes`.
- **Linked issue/PR:** mw-ding/eng-crew#83
