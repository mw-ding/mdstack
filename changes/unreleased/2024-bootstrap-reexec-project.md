---
type: fixed
issue: 2024
pr: 2051
date: 2026-11-22
box-skill: none
---

7.x → 8.x upgrade: 8.x accepts `--project` on `mdstack upgrade` when `CREW_BOOTSTRAP_BUNDLE_SHA256` is set, the verified re-exec a 7.16.0 bootstrap makes from an owner shell, so a plain `mdstack upgrade --latest` from 7.16.0 no longer exits 2. Every other owner-shell `--project` stays refused. The bootstrap "Human step" now reads `Run mdstack up` (`--repo KEY` in a multi-repo team) or `Run MDSTACK_CONFIG=<file> mdstack up`, never the `--project` form 8.x refuses. The migration guide says upgrading straight to 8.0.0 or 8.1.0 still needs `MDSTACK_INTERNAL=1`.
