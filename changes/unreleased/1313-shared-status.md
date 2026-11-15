---
type: added
issue: 1313
pr: 1905
date: 2026-11-14
box-skill: none
---

Add opt-in shared status for independent crews (`docs/specs/shared-status.md`): an optional `[status]` table (off until configured, team-level in a team file), the closed version-1 record schema in `core/status-record.py`, the optional `status` backend concern with the bundled GitHub connector `connectors/github/status.py`, `mdstack status register` and `mdstack status publish [--check]` with the zero-write read phase, receipt, publish lock and readback-only recovery of uncertain sends, the watcher's publish timer, and the read-only `mdstack status --all` view with fresh, stale, invalid and conflict rows. Existing profiles, manifests and plain `mdstack status` are unchanged.
