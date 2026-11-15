---
title: Unset projects ran `thorough`; validation found problems after a passing review in 2 of 217 rounds, so unset now resolves `standard`, flagged (#632)
date: 2026-11-03
status: applied
source: #632; owner learning 2026-11-03
---

# Standard as the unset flavor, 2026-11-03

## Thorough by default paid for validation that rarely found anything

- **Date:** 2026-11-03
- **Source / evidence:** #632; owner learning 2026-11-03. eng-crew ran with
  no project flavor all of 2026-11-02, so every PR resolved `thorough`: a full
  review and a separate validation session. Verdict markers since 2026-11-01
  show validation found problems after a passing review in 2 of 217 rounds
  (0.9%).
- **Finding:** The unset fallback was the strictest preset, while bootstrap
  already proposed `standard` and the design calls it right for most work.
  Unset projects got `thorough` rigor without anyone choosing it.
- **Impact:** Every PR paid for an extra validation session and its queue
  time; 215 of 217 rounds gained nothing from it.
- **Fix:** An unset project flavor resolves `standard`, still flagged
  (`flavor.name = "standard"  # core (unset: flagged)`), and the rendered
  briefs carry its baseline line. Item records and class rules still raise
  rigor; `thorough` stays the preset for releases, security and
  gate-contract work, and [flavors](../flavors.md#class-rule) recommends a
  `thorough` class for gate-defining paths. Migration: set
  `[flavor] name = "thorough"` to keep the old behaviour.
- **Status:** applied: `scripts/crew-config.py` (`UNSET_FLAVOR`) and
  [flavors](../flavors.md) in the #632 change.
- **Linked issue/PR:** #632
