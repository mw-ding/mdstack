---
type: added
issue: 1913
pr: TBD
date: 2026-11-15
box-skill: none
---

Lessons log: a new entry records how one wrong-typed URL in a shared-status record crashed `mdstack status --all` on #1905 and hid a valid instance, the repair that diagnoses every wrong-typed field and refuses over-deep records, and the two regressions in `dev/tests/core/test-status-record.py` that hold it.
