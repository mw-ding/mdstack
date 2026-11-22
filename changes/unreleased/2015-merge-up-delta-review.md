---
type: fixed
issue: 2015
pr: TBD
date: 2026-11-22
box-skill: none
---

A builder merge-up that resolved a conflict now reliably starts its delta review. Poll can see the merge-up push before the builder's signed note is posted. When that happens, route sends the merge-up to the synthesizer for portability, and the builder's `done:` can reach the reviewer lead before the note reads back. The reviewer lead used to consume that `done:` as an identical merge-up and start nothing (#2000). It now parks the request as a `waiting: #<n> evidence` wait until a signed builder note is at the head; the note wakes it, and a resolved conflict or differing patch then starts the review. A clean note still needs no delta review. The coordinator can also hand the reviewer lead `rereview '#PR' HEAD`: the lead starts a review of that head at the live round through the usual admission and deduplication. The handoff supplies no verdict, merge-ok or gate input. Test plumbing: the fake tmux wrappers now refuse to exec themselves when one is renamed over `tmux-base`, so a doubled wrap can no longer leave a runaway process chain.
