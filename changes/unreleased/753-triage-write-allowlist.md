---
type: security
issue: 753
pr: TBD
date: 2026-11-15
box-skill: none
---

Triage hardening: every triage sweep write now goes through one apply entry point, `scripts/triage-apply.py`. It checks each requested write against a single write allowlist table in the triage design, the profile's `triage.mode` and `triage.repos`, and the issue's own `pass=triage` record from the sweep (a record from any login other than the researcher's never counts). Anything else is refused with a nonzero exit and no write: a close, a gate or `crew:` label, an unlisted label, a milestone create, a body edit, or a repository or owner-config write. The sweep brief, skill and design say issue text is data, never instructions. A provider safety refusal is recorded once (`decision=refused`), never retried, and parks the item until the owner comments. Shadow mode is unchanged. Running sweeps without bypass in a read-only sandbox stays a Known risks row.
