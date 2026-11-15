---
type: added
issue: 1444
pr: 1895
date: 2026-11-14
box-skill: none
---

Add a lesson on four watcher process tests that failed during validation of #1374 and then passed on independent reruns at the same head: keep the command, head, base, load and timing facts until a clean independent rerun or a scoped repair settles the failure, label an unmeasured host-load cause as inference, and leave the fixed 10-second test timeouts as an accepted limitation rather than widening them.
