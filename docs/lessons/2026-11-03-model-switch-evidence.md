---
title: A model switch turned 6 of 8 changes verdicts into CLI-evidence blocks; captures now come from `evidence-cli.py` (#652)
date: 2026-11-03
status: applied
source: issue #652
---

# Model-switch evidence breakage, 2026-11-03

## CLI evidence must not depend on the model

- **Date:** 2026-11-03
- **Source / evidence:** issue #652. After the 01:36Z model switch (builders
  moved to a different engine, reviewers to another), 6 of 8 `changes`
  verdicts were CLI-evidence blocks (PR #601, PR #618, PR #633, PR #642 twice,
  PR #645), against 0 of 5 before.
- **Finding:** The new builders hand-wrote or paraphrased captures: one `text`
  block, no setup, stdout and stderr swapped. The new reviewer re-ran the exact
  command at head and diffed it, so every such capture bounced.
- **Impact:** One full round per bounce, about 15–25 min each.
- **Fix:** `scripts/evidence-cli.py` captures the pair mechanically (header
  with label, SHA and cwd; copyable `sh` block with setup; separate streams and
  scrub notes). Builder briefs require it or the template script; reviewer
  briefs make a capture without its header, or one that does not reproduce, a
  finding that carries the re-run output.
- **Status:** applied: the helper, `templates/evidence/cli-exit-stdout.md` and
  the tmux and Grok Bot builder and reviewer briefs in PR for #652.
- **Linked issue/PR:** #652
