---
type: added
issue: 1962
pr: 2042
date: 2026-11-21
box-skill: none
---

Verified exported packs: `core/crew-pack.py lock <checkout> <export>` writes a `pack.lock` recording the clean checkout's commit, each file's sha256 and a digest over them. Bootstrap and upgrade accept a pack directory outside version control, including one whose declared `[vcs]` tool is not installed, only when its `pack.lock` verifies, and record the lock's commit as `pack.commit`. A changed, added or removed file is refused, naming the first mismatched path; a VCS checkout installs as before and a plain directory without a lock keeps today's refusal.
