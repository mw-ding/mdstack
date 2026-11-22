---
type: fixed
issue: 1950
pr: TBD
date: 2026-11-22
box-skill: none
---

Suite admission no longer deadlocks on a dependency wait. When a counted builder's newest status line is a typed `waiting: #<m> KIND id=<id>`, the scheduler may start `#<m>` past `max_suites`. The grant's reason is `suite-wait` and its decision log line names the wait. Every other condition still applies, and no cap value changes.
