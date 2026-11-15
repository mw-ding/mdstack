---
title: Mechanical routing consumed coordinator turns at about 20 windows; owner replies come first (#434)
date: 2026-11-01
status: open
source: mw-ding/eng-crew#434, the run with about 20 concurrent windows
---

# Lesson: coordinator saturation during a tmux run

## Mechanical wakes delayed owner replies

- **Date:** 2026-11-01
- **Source / evidence:** mw-ding/eng-crew#434, the run with about 20 concurrent
  windows: five builders, up to eight reviewers and the synthesizer.
- **Finding:** The coordinator spent model turns on spawning validation,
  killing terminal windows, dequeuing work, checking markers, clearing labels
  and deleting merged branches. Owner messages arriving during those turns
  sometimes waited several minutes.
- **Impact:** Owner responsiveness fell while purely mechanical wakes consumed
  the coordinator's queue and model budget.
- **Fix:** Architecture: #429 automates queue handoff, launch environment and
  verdict glue; #430 removes the duplicate local merge-train suite and records
  mirror deferral in the profile; #434 routes mechanical wakes in `crew route`
  before the watcher wakes the coordinator. Fake tmux and gh regression tests
  in `scripts/test-crew-route.py` cover routing and cleanup. Owner replies come
  before routing, and a repeated manual step becomes a builder issue at once:
  prose only, because identifying repetition and answering an owner message
  depend on live conversations and judgement.
- **Status:** open. #429, #430 and #434 track the automation; the new router and
  owner-first brief need to land and be deployed before the fix is in effect.
- **Linked issue/PR:** mw-ding/eng-crew#429, mw-ding/eng-crew#430,
  mw-ding/eng-crew#434; mw-ding/eng-crew#445
