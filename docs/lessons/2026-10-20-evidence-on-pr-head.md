---
title: Evidence a verdict relies on goes on the PR head, never a side branch (PR #12 incident)
date: 2026-10-20
status: superseded
source: PR #12 in this repo
---

# Evidence on the PR head, 2026-10-20

Entry format: see [README.md](README.md).

## Evidence a verdict relies on must be on the PR head

- **Date:** 2026-10-20
- **Source / evidence:** PR #12 in this repo: images in the merged PR body broke
  after the side branch holding the evidence was deleted. Requested by the
  reviewer-validator. Related: the off-head evidence stall in
  [2026-10-19-bottlenecks.md](2026-10-19-bottlenecks.md#evidence-that-lives-off-the-pr-head-can-stall-the-review-loop).
- **Finding:** Evidence kept on a side branch is lost when that branch is
  deleted after merge, so images in the merged PR body no longer render.
- **Impact:** broken evidence in a merged PR; no figure given.
- **Fix:** commit any evidence a verdict relies on (screenshots, crops, logs,
  other artifacts) on the PR branch so it is in the head commit; never use a
  side branch. If evidence changes without the code changing, the coordinator
  posts a rereview steer (`steer cmd=rereview`). See
  [protocol.md](../protocol.md#3-evidence-requirements).
- **Status:** superseded by #143's inline-only evidence rule in protocol §3
  and §7. See [2026-11-01-inline-evidence.md](2026-11-01-inline-evidence.md):
  the change record holds durable proof without committing review artifacts.
- **Linked issue/PR:** mw-ding/eng-crew#19; replacement #143 / PR #448
