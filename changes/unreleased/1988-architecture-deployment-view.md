---
type: changed
issue: 1988
pr: 2001
date: 2026-11-18
box-skill: none
---

Architecture: `docs/architecture.md` opens with a canonical Mermaid deployment, wake and release diagram (owner → coordinator and leads → isolated role worktrees; GitHub issues, PRs, CI and markers; poll/watch → queue → route; runtime and harness boundaries; cut → bundle → install), showing review and CI as independent merge-gate inputs, review starting on `new-head` and the synthesizer lead as the lander, with a table citing a code or doc anchor for every edge. The README links it in place of the pilot PNG, and `docs/diagrams/README.md` lists it first and keeps the pilot flow only as history, off the newcomer path.
