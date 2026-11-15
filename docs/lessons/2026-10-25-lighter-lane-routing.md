---
title: Lighter-lane templates skip B2/watch and mirror holds; explicit messages route changes requests, red CI and cleanup (#57)
date: 2026-10-25
status: applied
source: mw-ding/eng-crew#55 introduced the lighter lane; issue #57 records the template and routing follow-up
---

# Lessons: lighter-lane template sync and routing

## Entries

### Removing B2 needs explicit message routes

- **Date:** 2026-10-25
- **Source / evidence:** mw-ding/eng-crew#55 introduced the lighter lane;
  issue #57 records the template and routing follow-up. Refs #55.
- **Finding:** The protocol exempted qualifying docs-only PRs from B2, watch
  markers and mirror holds, but templates still required the watch. Without
  B2, red CI and changes requests need an explicit route to the builder.
- **Impact:** Templates could impose an unnecessary hold or leave a fix
  waiting for a listener that is intentionally absent.
- **Fix:** Align template exemptions; have the reviewer's verdict-pass parent
  turn message the builder on REQUEST_CHANGES, with the sweeper as backstop.
  Route red CI through the sweeper/coordinator and close-out through the
  coordinator. Re-check the full diff at head and attach B2 if a fix leaves
  the lane.
- **Status:** applied. Template and routing sync merged in #60 (sweeper, reviewer
  and builder templates, `docs/protocol.md`); the routing paragraph now lives
  in `docs/runtimes/grok-bot.md` (#114).
- **Linked issue/PR:** mw-ding/eng-crew#57
