---
type: fixed
issue: 1850
pr: TBD
date: 2026-11-14
box-skill: none
---

A busy worker no longer turns a late acknowledgement into a lead fault. `mdstack send` records each worker message and nudge in a per-run delivery ledger; a duplicate send keeps the pending id, types nothing while the worker is busy or held, re-nudges an idle one once, and names the restart or escalation otherwise. `mdstack acked --delivery` prints the message's separate delivery, worker and disposition axes and next action (additive; legacy exits unchanged), only the target's own ack recorded after the message settles it, the watcher wakes the pool lead once per changed actionable delivery state without a model turn, and a busy lead gets no retyped nudge.
