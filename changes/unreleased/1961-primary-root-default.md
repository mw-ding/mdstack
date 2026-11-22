---
type: fixed
issue: 1961
pr: 2068
date: 2026-11-22
box-skill: none
---

Hosts: a primary host with no `root` now uses the profile's resolved `paths.root` (else `$CREW_ROOT` or `~/.mdstack`) for `mdstack host prepare` and its checkout-receipt read, so a crew installed under another root no longer looks for its command checkout under `~/.mdstack`. An explicit `hosts.<primary>.root` is unchanged.
