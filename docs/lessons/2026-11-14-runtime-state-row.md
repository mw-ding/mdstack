---
title: A cleanup change shipped with its allocated runtime state-file row describing the old behaviour; reviewers read that row beside the command and retention tests (#1843)
date: 2026-11-14
status: applied
source: PR #1831 (issue #369, the M54 B4 slice), intake card #1843
---

# Runtime state-file row left stale by a cleanup change, 2026-11-14

## A shutdown or scratch change must update its allocated runtime row

- **Date:** 2026-11-14
- **Source / evidence:** PR #1831 (issue #369, the M54 B4 slice): round-1
  review, the builder's round-1 fix note and the round-2 verdict; intake card
  #1843. The B4 allocation in `docs/specs/portable.md` named three paths:
  `down.py`, `guard.py` and the runtime state-file row.
- **Finding:** #1831 made plain `mdstack down` sweep regular
  `runs/coordinator.*` scratch after a successful stop, but left the
  `runs/<window>.body.md` row of the state table in `docs/runtimes/tmux.md`
  saying `down` leaves window 0's files. The code and its tests were correct;
  the allocated documentation row described the reverse of what shipped.
- **Impact:** One review round on #1831 (round 1 `changes`, round 2 `pass`).
  The row and an explicit symlink exclusion, with a failing-then-restored
  control, were repaired before merge, so no stale row reached `main`.
- **Fix:** Skill or protocol prose: the reviewer pass in
  `templates/policy/reviewer/passes.md` now says that when a review changes
  what a shutdown or scratch cleanup removes, keeps or refuses, the reviewer
  reads the runtime state-file row its allocation names beside the command
  and its retention and refusal tests, and treats a row still describing the
  old behaviour as a missing allocated path. Prose only, because which row an
  allocation names, and whether the row's wording covers the changed
  semantics, is review judgment: no repo file maps a code path to the prose
  row that describes it. The row at `docs/runtimes/tmux.md` keeps the
  repaired plain-down, `--preserve`, refusal and symlink semantics.
- **Status:** applied: the reviewer reminder is on `main` in
  `templates/policy/reviewer/passes.md` (#1843), and the repaired row is on
  `main` in `docs/runtimes/tmux.md` (#1831). Not encoded: no check ties a
  lifecycle change to its state-file row.
- **Linked issue/PR:** #1831, #1843
