---
type: added
issue: 1912
pr: TBD
date: 2026-11-15
box-skill: none
---

Lessons log: a new entry records the shared-status draft on #1896, which kept only a hash of the pending record and retried after a timed-out write, so a delayed request could overwrite a newer record. The repaired contract keeps the exact pending body, sends each write once and stops on an uncertain outcome until readback shows that body. It names the `test-status-shared.py` regressions from #1905 and is marked applied, not encoded.
