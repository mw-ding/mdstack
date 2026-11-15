---
title: The builder's per-PR watch B2 silently failed to attach on PR #35 and the PR stalled about 62 min; B2 attachment is now verified, recorded and swept (#36)
date: 2026-10-23
status: applied
source: PR #35 timeline (Oct 23, 2026, PT)
---

# Lessons: verify the builder's per-PR watch attached (Oct 23, 2026)

One lesson from the stalled docs PR #35 (issue #34). Entries follow the
lessons-log format: date, source, finding, impact, fix, status and linked
issue/PR. Sanitized per spec R1.

## Entries

### Builder per-PR watch B2 never attached; the PR stalled with no consumer

- **Date:** 2026-10-23
- **Source / evidence:** PR #35 timeline (Oct 23, 2026, PT). 12:14 AM: the
  builder's worker pushed and opened PR #35 and the label `crew:in-review` was
  added. 12:15 AM: the reviewer posted its ack. 12:23 AM: the reviewer posted a
  round-1 `REQUEST_CHANGES` and the label went to `crew:changes`. From then on
  no B2 watch existed for #35, so `review-changes-requested` had no consumer: no
  builder claim, fix note, worktree or push. 1:25 AM: the hourly stuck-PR
  sweeper flagged it (about 62 min, empty claims dir) and nudged the builder,
  whose parent turn created the missing B2 and relaunched the fix. 1:27 AM: fix
  pushed. 1:35 AM: round-2 APPROVE and merge.
- **Finding:** The B2 creation hand-off from the builder routine to its parent
  turn was fire-and-forget. Nothing confirmed that B2 was created or recorded
  its ID, and nothing checked for a missing watch. The protocol's builder event
  list also omitted `review-changes-requested`, and the runbook put B2 creation
  at the `pr-opened` step, which only wakes the reviewer.
- **Impact:** About 62 minutes of dead time on a 3-line CHANGELOG fix, roughly
  75% of the PR's roughly 81 minutes from open to merge. The failure is silent;
  the same gap drops `ci-failed` and the `pr-merged` / `pr-closed` cleanup for
  that PR. With an hourly sweep and a 30-min threshold, the worst case is about
  90 minutes before the first nudge.
- **Fix:** The builder's parent turn verifies B2 after creating it (exactly
  `ci-failed`, `review-changes-requested`, `pr-merged`, `pr-closed`), records
  the watch ID in `<state-dir>/<owner>__<repo>/watches/pr-<n>.b2`, messages the
  coordinator if it cannot confirm, and posts a `pass=watch` marker on the PR.
  The sweeper gets a `no-builder-watch` condition (> 10 min after PR open) and
  documents that an hourly cron stretches the 30-min threshold to a 30-90 min
  detection window. The reviewer's first verdict flags a missing `pass=watch`
  marker to the coordinator. The protocol event list and the runbook (B2 is
  created by the builder's parent turn after the worker opens the PR, not at
  `pr-opened`) are corrected.
- **Status:** applied. `docs/runtimes/grok-bot.md` (verified hand-off, moved
  from `docs/protocol.md` §6 in #114), builder B1 and sweeper templates,
  runbook (#37). Does not cover lighter-lane PRs, which skip B2.
- **Linked issue/PR:** #36 and #35; fix PR #37

### Dry run (PR #37)

AC1 of issue #36 (a dry run on a test PR leaves a marker file naming the watch
ID) was run on PR #37 itself. The builder's parent turn created watch B2 for
PR #37, verified it by listing routines (enabled, events exactly `ci-failed`,
`review-changes-requested`, `pr-merged`, `pr-closed`), and recorded it in
`<state-dir>/mw-ding__eng-crew/watches/pr-37.b2`:

```text
watch=b2 pr=37 repo=mw-ding/eng-crew
watch_id=13758541-9c2b-58ec-b0d3-8466e44cc3b0
folder=eng-crew-37-watch-ben-b2
events=ci-failed,review-changes-requested,pr-merged,pr-closed
verified=2026-10-23T12:05-07:00 via routine get (enabled); fired on review-changes-requested 2026-10-23T19:01:44Z (review 5633174843)
```

The watch then fired on the round-1 `REQUEST_CHANGES` (review 5633174843),
which started this fix round.
