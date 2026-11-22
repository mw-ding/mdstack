---
type: fixed
issue: 2083
pr: 2085
date: 2026-11-22
box-skill: none
---

test-check-repo: the #2017 bundle-link negative control now writes and stages its own `changes/unreleased/` fragment in the clone before it injects the README link. At a cut head, `changes/unreleased/` has no tracked files, so the clone lacked the directory and the plain link check fired instead of `[bundle-link]`, which failed every cut. A new case runs the control on a clone with `changes/unreleased/` removed and also asserts no `[broken-link]`.
