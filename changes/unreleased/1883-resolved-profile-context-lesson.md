---
type: added
issue: 1883
pr: TBD
date: 2026-11-14
box-skill: none
---

Add a lesson on derived routing-context keys that leaked into the resolved profile during #1866 and broke `grant prune`'s equality check: keep derived values such as the work context in separate functions so the resolved values stay exactly the profile, with the existing grant-prune tests as the regression.
