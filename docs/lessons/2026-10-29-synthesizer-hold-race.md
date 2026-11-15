---
title: The synthesizer squashed past an open coordinator hold-until (#78) and an open rereview (#74); both are now §7 merge blockers that merge-ok does not override (#81)
date: 2026-10-29
status: applied
source: mw-ding/eng-crew#78 and #74
---

# Lessons: synthesizer race past a coordinator hold

## Entries

### Synthesizer squashed past an open hold-until and an open rereview

- **Date:** 2026-10-29
- **Source / evidence:** mw-ding/eng-crew#78 and #74. On #78 the coordinator
  posted hold-until-#75, and the synthesizer squash-merged on a standing
  doc-only merge-ok before the hold took effect. On #74 the synthesizer held
  for an engine-diversity re-verdict at head 92eb08a; the coordinator then
  posted `steer cmd=rereview` plus merge-ok, and the synthesizer squashed on the
  prior Claude APPROVE before the Codex verdict landed (the reviewer stopped
  the Codex pass). Merge commit 00040a7.
- **Finding:** The synthesizer treated §7 as clear while a coordinator hold was
  still open. The standing doc-only merge-ok was read as overriding an explicit
  hold-until, and merge-ok plus an older APPROVE was read as satisfying an open
  rereview.
- **Impact:** Two merges the coordinator had asked to wait. #74 merged without
  the engine-diverse re-verdict it required. Neither was reverted; no number is
  given by the source.
- **Fix:** Prose only, because both checks depend on live GitHub state and
  timing (a hold or `steer cmd=rereview` posted after the approval wake, and
  whether a verdict has landed at a SHA), which an offline repo check cannot
  see. Protocol §7 and the Gate registry now name two blockers: an explicit
  coordinator hold-until-X (or crew hold command) on the PR or in the inbox
  overrides standing doc-only merge-ok, and an open `steer cmd=rereview` at the
  current head blocks squash until a fresh `pass=verdict` lands at that SHA on
  an engine different from the actual builder engine; merge-ok overrides
  neither. `templates/runtimes/grok-bot/synthesizer.md` lists both in the pre-merge gate. A
  `check-repo.py` static guard (`synthesizer-blockers`, with a fixture test) only keeps those two
  rules present in the protocol and template. The structural fix is the
  merge ruleset in [merge-enforcement](../merge-enforcement.md).
- **Status:** applied. Protocol §7 and Gate registry, and
  `templates/runtimes/grok-bot/synthesizer.md`, in #81.
- **Linked issue/PR:** mw-ding/eng-crew#81
