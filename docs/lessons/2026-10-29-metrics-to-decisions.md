---
title: Metrics baselines existed but no sensor turned a slow streak or rework wave into a harness fix; the rollup gate and per-repo follow-up are documented, with `metrics-decide.py` (#86)
date: 2026-10-29
status: applied
source: mw-ding/eng-crew#86 and the metrics artifact in docs/metrics (#75)
---

# Lessons: metrics without decisions

## Entries

### Baselines existed but nothing used them

- **Date:** 2026-10-29
- **Source / evidence:** mw-ding/eng-crew#86 and the metrics artifact in
  [docs/metrics](../metrics/README.md) (#75). The pilot data showed a median
  open-to-merge of about 110 minutes for eng-crew since Oct 15 and about 91
  minutes for agentconnect, yet no rule compared a later window to those
  numbers.
- **Finding:** Velocity and quality numbers were recorded but never tied to an
  action. A slow streak or a wave of reviewer-validator rework would not have
  forced a harness change, and feature work would have carried on regardless.
- **Impact:** The harness could degrade unnoticed while `M*` feature issues
  kept being released. No number is given by the source for a missed regression.
- **Fix:** Prose plus a script, level 5 with a level 4 helper: the
  [metrics decisions protocol](../metrics/decisions.md) defines two sensors
  (median open-to-merge up more than 30% against the prior window; rework rate
  above 20%), a rollup that decides the gate and a per-repo layer that only
  files a project follow-up. `scripts/metrics-decide.py` computes the verdict
  from `prs.csv` with fixture tests in CI. Prose only for the trigger and the
  hold, because filing the issue and holding `M*` work depend on live GitHub
  state and the owner's decisions. The rework rate is a proxy (reopened, or
  three or more changes verdicts) until the CSV carries event order, and the
  thresholds are drafts to tune after false trips.
- **Status:** applied. `docs/metrics/decisions.md`,
  `scripts/metrics-decide.py` and `templates/metrics-regression-issue.md` on
  `main` in the PR for #86. The thresholds are drafts; tuning them after the
  first false trip is expected, not a gap in this fix.
- **Linked issue/PR:** mw-ding/eng-crew#86
