---
title: First live run of the verified B2 hand-off on PR #38: pin the routine folder id, parent-turn-only marker, full 40-char SHA in markers (#39)
date: 2026-10-23
status: mixed
source: PR #37 and PR #38: the verified hand-off from issue #36 run live
---

# Lessons: first live run of the verified B2 hand-off (Oct 23, 2026)

Three wording gaps found when the verified hand-off from issue #36 ran live on
PR #38. Entries follow the lessons-log format. Sanitized per spec R1.

## Entries

### The hand-off recorded two different watch identifiers

- **Date:** 2026-10-23
- **Source / evidence:** PR #37 and PR #38 marker files. PR #37's run recorded a
  platform UUID that it read from inside a routine run. PR #38's run recorded the
  routine folder id. The builder's parent (main-chat) turn cannot see a platform
  UUID, because the routine `get` call returns only the folder id.
- **Finding:** The protocol, the builder B1 template and the runbook said only
  "watch ID", so each run picked a different identifier.
- **Impact:** A marker file that the parent turn, the sweeper or a later reader
  cannot cross-check against the routine list.
- **Fix:** Name one identifier everywhere: the routine folder id, which both a
  routine run and the parent turn can see.
- **Status:** applied. Merged in #41 (`docs/protocol.md`, B1 template, runbook);
  the hand-off text now lives in `docs/runtimes/grok-bot.md` (#114).
- **Linked issue/PR:** #39; PR #41

### B1 read as though it could post the `pass=watch` marker

- **Date:** 2026-10-23
- **Source / evidence:** The B1 template's hand-off paragraph on PR #38.
- **Finding:** B2 exists only after the parent-turn hand-off, so the B1 run
  cannot verify it, write the marker file or post the marker, yet the template
  wording blurred who does which.
- **Impact:** Risk of a marker posted before any watch exists, or by nobody.
- **Fix:** The B1 run only requests the hand-off (writes the B2 spec to its log
  dir and asks the parent turn). Verifying, writing `watches/pr-<n>.b2` and
  posting `pass=watch` belong to the parent turn only.
- **Status:** applied. Merged in #41 (`docs/protocol.md`, B1 template, runbook);
  the hand-off text now lives in `docs/runtimes/grok-bot.md` (#114).
- **Linked issue/PR:** #39; PR #41

### The `pass=watch` marker carried a 7-char SHA

- **Date:** 2026-10-23
- **Source / evidence:** PR #38. The builder's marker had a 7-char `sha=`. The
  reviewer's first-verdict cross-check caught the missing marker, and the builder
  fixed it in round 2.
- **Finding:** The cross-check matches on the head SHA, and a short SHA did not
  match. The protocol's `pass=watch` example showed `<head-sha>` without saying
  how long it is.
- **Impact:** One extra round on PR #38 for a marker that was present but
  unreadable.
- **Fix:** Every marker's `sha=` is the full 40-char head SHA, `pass=watch`
  included, and the reviewer cross-check matches on the full SHA. Encoded at
  level 4 of the [correction hierarchy](README.md#correction-hierarchy): the
  `marker-sha` rule (`check_markers`) in `scripts/check-repo.py` fails any
  `crew:v1` marker in repo markdown whose `sha=` is a literal that is not 40 hex
  characters, or a placeholder naming a short SHA (`<sha7>`, `<short-sha>`).
  Tests are in `scripts/test-check-repo.py`.
- **Status:** encoded. `marker-sha` check in `scripts/check-repo.py` (#77);
  the rule itself merged in #41 (`docs/protocol.md`, B1 template, runbook).
- **Linked issue/PR:** #39; PR #41; #69

### Stale known-gap bullet

- **Date:** 2026-10-23
- **Source / evidence:** PR #38 review. The runbook's Known gaps bullet still
  pointed at closed issue #19.
- **Finding:** The bullet was stale after the protocol gained the section that
  covers the gap.
- **Impact:** A reader follows a pointer to a closed issue instead of the
  current protocol text.
- **Fix:** The bullet now refers to the protocol section that covers it.
- **Status:** applied. Merged in #41 (`docs/protocol.md`, B1 template, runbook).
- **Linked issue/PR:** #39; PR #41; Refs #42
