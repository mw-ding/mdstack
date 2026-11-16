---
title: The #1923 post-open note and `done:` named the opened head, not the head after the fragment fill; a signed merge-up corrected both, and the cause of the stale readback is unconfirmed (#1933)
date: 2026-11-15
status: open
source: Lesson change #1923 (closes #1915), its round-0 ci-fix note and merge-up correction, intake card #1933
---

# A post-open note named a stale published head, 2026-11-15

## Read the head back after the push, and keep the cause open until it is known

- **Date:** 2026-11-15
- **Source / evidence:** Lesson change #1923 (closes #1915, M59): the
  builder's round-0 `ci-fix` note (18:36:42Z), the builder's signed
  merge-up note (19:02:08Z, its correction 2) and the PR's commit list;
  intake card #1933. Related, not the established cause: #376 (a local hash
  invalidated by a backend commit rewrite) and #1367 (a shared
  `FETCH_HEAD` spawn race). Affected file:
  `templates/policy/builder/build-pass.md` step 4.
- **Finding:** #1923 opened at `f49deb6`, the lesson commit. The post-open
  fill commit `45aba8e` (`pr: TBD` to `pr: 1923`) was pushed at 18:36:17Z.
  The round-0 note posted 25 s later named `f49deb6` as the filled head in
  its title, text, marker `sha=` and next-actor line, and the builder's
  `done:` used it too. The PR's commit list has `f49deb6` before
  `45aba8e`, and the forge recorded the note's own review at `45aba8e`, so
  the note named the opened head, not a commit that was ever the filled
  head. The builder's merge-up note corrected the note and `done:` before
  merge and named it a stale head readback. Whether the readback ran before
  the push landed, read a cached value, or reused the opened-head read is
  not established: no worker status file or provider response was checked.
  One later observation, on this lesson's own PR #1945: a PR head read
  (`gh pr view --json headRefOid`) right after a push returned the previous
  head, and a re-read seconds later from four sources (that command, the
  branch ref, `git ls-remote` and the pull request record) returned the
  pushed commit. That fits a readback taken before the forge reflects the
  push, but it is one observation, not a confirmed cause.
- **Impact:** One wrong SHA in one note's marker and one `done:` line, both
  corrected by the next signed note about 25 min later. Nothing wrong
  merged: the correction preceded the merge (19:49:09Z), and no review or
  gate is shown to have acted on the stale SHA. Any delay is not measured.
- **Fix:** Prose only, because whether the SHA a note names is the head
  after the push depends on live forge state at post time, which repo files
  cannot check. Keep the existing rule in
  `templates/policy/builder/build-pass.md` step 4: after each push, read
  the head back from the backend and use that full SHA, never a local hash,
  in markers, evidence and `done:`. No new rule or automation is proposed
  until the stale-read cause is found. One signal for that work: the forge
  attaches each review to the head at post time, so a marker `sha=` that
  differs from its own review's commit is visible after the fact.
- **Status:** open: the readback rule was already in
  `templates/policy/builder/build-pass.md` step 4 on `main` and did not
  prevent this; the cause is unconfirmed, so no fix is applied or encoded.
- **Linked issue/PR:** #1933, #1923, #1915, #1945
