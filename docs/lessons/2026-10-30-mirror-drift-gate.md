---
title: The mirror hold waited on a hand copy with nothing checking it; the mirror comment now needs a deployed render and a clean drift check (#128)
date: 2026-10-30
status: applied
source: spec R4 and the umbrella mw-ding/eng-crew#110
---

# Lessons: mirror hold as a drift check

## Entries

### The mirror hold waited on a hand copy of the box skills

- **Date:** 2026-10-30
- **Source / evidence:** spec R4 and the umbrella mw-ding/eng-crew#110: every
  PR touching `docs/protocol.md` or `templates/` carried `crew:needs-mirror`
  until the coordinator hand-edited the box skills. During M13 the hold was
  deferred to #140 for roadmap PRs
  ([portable spec §6](../specs/portable.md#6-decisions)).
- **Finding:** The mirror gate was satisfied by a comment saying the box
  skill was mirrored, with nothing checking that the live copy matched the
  reviewed copy.
- **Impact:** Each protocol or template PR waited on a manual step, and a
  wrong or partial mirror could pass the gate. No number is given by the
  source.
- **Fix:** Architecture plus a check, run by the coordinator rather than CI
  because it needs the live copy: templates reach the live dir as
  `crew-render.py` output (#125, #126), and the mirror comment only counts if it
  carries a clean `check-skill-drift.py --project` result (plus the pipeline
  skill pair when `docs/protocol.md` changed) at the last touching commit,
  inline ([mirror hold gate](../runtimes/grok-bot.md#mirror-hold-gate),
  drift mode in #226).
- **Status:** applied. Protocol §6, §7 and Gate registry, and the Grok Bot
  mirror hold gate, in #227.
- **Linked issue/PR:** mw-ding/eng-crew#128
