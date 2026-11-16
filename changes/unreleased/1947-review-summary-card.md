---
type: added
issue: 1947
pr: TBD
date: 2026-11-16
box-skill: none
---

Every reviewer verdict and the synthesizer's gate-status post now opens with a two-line summary card between the title and the TL;DR: **Status** with a colored emoji (🟢 passed or ready to land, 🟡 changes requested, 🔴 blocked or escalated, ⚪ pending) and **Landing risk** (🟢 low, 🟡 medium, 🔴 high) with a one-line reason. One rule, in `core/summary-card.py` and documented in protocol §4, derives the risk from facts already in the post: open blocking findings (verdict at head), `crew:sensitive`, gate-contract/protocol paths, runtime code versus docs, CI at head and round versus cap; any missing input makes it ⚪ unknown, never low. `mdstack verdict` renders the card; the gate-status template prints it with the script. The card is advisory only: no marker, gate, label or approval rule changes.
