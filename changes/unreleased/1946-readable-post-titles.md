---
type: changed
issue: 1946
pr: TBD
date: 2026-11-15
box-skill: none
---

Role post titles are now readable and bracket-free, led by the role's identity emoji: `🔎 Vera · Verdict · round 1 @ abc1234 · 🔁 changes` instead of `[Vera/verdict] round 1 @ abc1234 · 🔁 changes`. The format is defined once in protocol §4 and `core/post-title.py`; every role template renders it through the new `<title:<role>/<pass>>` placeholder, and the crew.d posters (verdict, ack, merge-up, train merge, handoff, close-out, placement, kill) build it through one helper. With `report.emoji = false` titles drop the emoji. Machine parsing never depends on the title: intake-ack dedupe, merge-up delta review, train coordinator holds, triage decision relays and the campaign report's decision count now read the hidden `crew:v1` marker, and old bracketed titles on existing posts still read through their markers. Report tooling that reads a title without a marker (reflection scan, reflection effects, triage clusters, the grant-prune historical-source check) accepts both forms. A table-driven test covers every role, pass and status. No marker, gate or label changes.
