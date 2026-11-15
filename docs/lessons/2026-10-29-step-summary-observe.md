---
title: Long agent runs were invisible mid-flight; builders write short step summaries and promote them onto the PR, raw logs stay local instead of a full tmux scrollback in chat (#85)
date: 2026-10-29
status: applied
source: Gap-table row 9 (agent runtime / observe) in the M8 gap analysis, issue #85 in this repo
---

# Lessons: step-summary observe, not full tmux into chat

## Entries

### Long agent runs were invisible; dumping the pane into chat is worse

- **Date:** 2026-10-29
- **Source / evidence:** Gap-table row 9 (agent runtime / observe) in the M8
  gap analysis, issue #85 in this repo. Long builds and test runs gave other
  roles nothing to read until the PR opened.
- **Finding:** During a long build or test run nobody can see progress, so
  retries are blind and "it passed" cannot be checked. The obvious remedy,
  attaching to tmux or pasting full scrollback into chat, floods the
  reviewer-validator, coordinator and synthesizer with raw output.
- **Impact:** No measured number in the source. The cost is unverifiable
  claims, blind retries and no lesson fuel for the findings buffer. Row 9 goes
  from Far to Partial; tmux attach and device runtime stay out of scope.
- **Fix:** Protocol prose plus a helper, no structural enforcement: step
  summaries are written by the builder with `scripts/step-summary.py`, the
  short summary is promoted in a signed review body, and raw logs stay local
  and gitignored. See [observe](../observe.md). Checked structurally only in
  part: `scripts/test-step-summary.py` (run in CI) pins the format, truncation
  and redaction, `scripts/required-docs.txt` pins the doc, headings, helper
  and this lesson, and `.gitignore` keeps `steps/` logs out of commits. Prose
  only for the rest, because whether a builder wrote and promoted a summary
  depends on live bot behaviour and PR state, which an offline repo check
  cannot see.
- **Status:** applied. `docs/observe.md`, `scripts/step-summary.py`, the
  builder, reviewer and synthesizer templates, in #85.
- **Linked issue/PR:** mw-ding/eng-crew#85
