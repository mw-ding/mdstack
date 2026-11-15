---
type: added
issue: 1915
pr: TBD
date: 2026-11-15
box-skill: none
---

Add a lesson on a shared builder build-pass step that fit the tmux brief but pushed the session runtime brief 14 bytes over its 16384-byte budget on #1908, which only full-suite CI caught: keep the compact step, the unchanged budget and the session-profile upgrade test as the regression, and check session headroom when shared builder text grows.
