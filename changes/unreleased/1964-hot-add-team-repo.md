---
type: added
issue: 1964
pr: TBD
date: 2026-11-17
box-skill: none
---

`mdstack up --team` on a running team session now reconciles the team without a restart. A repo added to the team file gets the fresh start's preflight, render, binding, `team.json` row, Stop hook and persistent watcher. A repo deleted from it has its watcher stopped and its row dropped, its state kept. It refuses, writing nothing, on a failed preflight, a removed repo with a live run, or the coordinator's own repo. When the set changed, the coordinator and live lead briefs are regenerated and each window gets one `brief` inbox message; a repeat with no change writes nothing.
