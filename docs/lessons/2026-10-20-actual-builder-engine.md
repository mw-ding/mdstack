---
title: A fix round was written by Codex while the builder marker said claude-code; the reviewer engine must differ from the engine that actually wrote the round (#21)
date: 2026-10-20
status: applied
source: PR #13 (roles doc, issue #3)
---

# Lessons: name the engine that actually wrote the round (Oct 20, 2026)

One lesson from the review of the roles-doc PR (#13). Entries follow the
lessons-log format: date, source, finding, impact, fix, status and linked
issue/PR. Sanitized per spec R1.

## Entries

### Reviewer engine keyed off a marker that did not match what ran

- **Date:** 2026-10-20
- **Source / evidence:** PR #13 (roles doc, issue #3): a fix round was written by
  Codex while the PR's builder marker said claude-code. The coordinator decided
  the rule on Oct 20, 2026.
- **Finding:** Reviewer-engine separation was keyed off a marker that did not
  match what actually ran, so the reviewer could have used the same engine as the
  real builder.
- **Impact:** A risk to the independent-review rule; no numbers are recorded in
  the sources.
- **Fix:** A round's builder engine is the engine that actually wrote that
  round's commits. The fix note, an `Engine:` trailer on every commit and the
  round's builder marker each name engine, model and effort (the initial
  build's PR-body marker names engine and model only; effort is in the
  signature and the trailers). If the builder marker and the fix note or commit
  trailer disagree on the engine, the note or trailer wins, and before merge the
  reviewer re-checks at head (fresh review + validation) on an engine different
  from the actual builder engine. See
  [roles](../roles.md#actual-builder-engine).
- **Status:** applied. `docs/roles.md` Actual builder engine (#33).
- **Linked issue/PR:** #21 and #13
