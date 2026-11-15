---
title: PR #41 merged before the builder's B2 hand-off reached its parent turn, so no watch or marker existed; the merge gate now requires the `pass=watch` marker (#43)
date: 2026-10-23
status: applied
source: PR #41 timeline (Oct 23, 2026, PT)
---

# Lessons: the merge gate must require the builder's watch marker (Oct 23, 2026)

One lesson from PR #41 (issue #43). Entries follow the lessons-log format: date,
source, finding, impact, fix, status and linked issue/PR. Sanitized per spec R1.

## Entries

### PR merged before the B2 hand-off reached the builder's parent turn

- **Date:** 2026-10-23
- **Source / evidence:** PR #41 timeline (Oct 23, 2026, PT). The builder's
  routine run sent its "please create the B2 watch" hand-off to its parent turn.
  The parent turn received it at 12:52 PM, after #41 had already merged at
  12:51 PM. No watch was created and no `pass=watch` marker was posted.
- **Finding:** Hand-off latency, not a template gap. The verified hand-off
  (#36, #39) only checks the watch after the fact, and the reviewer's
  cross-check only flagged the missing marker to the coordinator. Nothing
  stopped a fast PR from merging while the watch was still unattached.
- **Impact:** The PR merged with no B2 watch, so `ci-failed` and
  `review-changes-requested` would have had no consumer had the PR needed
  another round. The loss was latent here because the PR merged cleanly.
- **Fix:** The merge gate (protocol §7 and the synthesizer template) requires
  the builder's `pass=watch` marker with a full 40-char `sha=` of any commit on
  the PR (the rule from #42). If it is missing, the PR is held and the
  synthesizer pings the builder with priority; it never merges and never
  creates the watch. The reviewer's first verdict also pings the builder with
  priority, and still never creates B2.
- **Status:** applied. `docs/protocol.md` §7 and the synthesizer template (#45).
  Lighter-lane PRs are exempt. Since #119, §7 lists it as a runtime gate and
  the full rule lives in `docs/runtimes/grok-bot.md` (Builder watch gate);
  rule unchanged.
- **Linked issue/PR:** #43; Refs #41; Refs #42; PR #45
