---
type: fixed
issue: 1941
pr: TBD
date: 2026-11-22
box-skill: none
---

Researcher artifacts no longer strand a worktree: the tmux researcher brief now writes any artifact that is not the deliverable (a visual summary, a draft) under the worktree's `.crew/`, which spawn already excludes, and moves a tool's stray output there before `done:`. Close-out's unlanded-work guard is unchanged: any other untracked file still keeps the worktree.
