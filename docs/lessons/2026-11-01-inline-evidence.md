---
title: Inline proof in the change record; reject committed evidence
date: 2026-11-01
status: open
source: #143 and design PR #302; owner preference recorded 2026-10-29
---

# Inline evidence, 2026-11-01

## Keep review proof in the change record

- **Date:** 2026-11-01
- **Source / evidence:** #143 and design PR #302; owner preference recorded
  2026-10-29. Snapshot: 123 evidence files in one product tree, 11 in another;
  12 in this eng-crew build's base tree.
- **Finding:** Committed review artifacts squash into the product tree and
  remain in history, duplicating the inline proof and becoming stale.
- **Impact:** Tree clutter and permanent history growth; side-branch images
  also broke in PR #12 after branch deletion.
- **Fix:** Architecture: use the body and signed reviews as the record,
  copyable commands/output for text and GitHub user-attachments for media.
  CI guard: `check-repo.py --only evidence` rejects a root `evidence/` path.
  Media fallback and same-head rereview are prose only, because they depend
  on upload availability, reproduction and live review state.
- **Status:** open: implemented in this #143 build; application and the live
  mirror await merge. Supersedes the committed-proof fix in
  [2026-10-20-evidence-on-pr-head.md](2026-10-20-evidence-on-pr-head.md).
- **Linked issue/PR:** #143 / PR #448
