---
type: changed
issue: 1965
pr: 1976
date: 2026-11-17
box-skill: none
---

The owner CLI takes no `--project`: in an owner shell (no `CREW_ROLE`, and not an mdstack child process, which `MDSTACK_INTERNAL` marks) every command hides `--project` from `--help` and uses the installed team (`$MDSTACK_CONFIG`, else `<root>/config.toml`, else the root's only `<team>.toml`). `up`, `start` and a bare or `coordinator` `attach` take a multi-repo team file whole, `up` and `start` as `up --team`; every other command picks its repo with the new `--repo <key>` (also `--team-repo <key>`, the only spelling for `content` and `feedback`, whose own `--repo` means something else), needs none for a single-repo team, and exits 2 naming the keys when it is missing or unknown. Crew windows keep `--project` and `$CREW_PROJECT` exactly as before; the argument parsing stays, and `OWNER_PROJECT = True` in `crew.d/_shared.py` re-enables the flag. `mdstack layout --write` now writes a `<home>/start` that sets `MDSTACK_CONFIG` instead. **Breaking:** an owner shell's `--project`, in any spelling, now exits 2 with `mdstack: --project is disabled; mdstack uses the installed team (<path>). Set MDSTACK_CONFIG to override.` before any read or write, and so does a `<home>/start` written before this release. Migration: drop `--project` from owner commands and scripts (use `--repo <key>` or `MDSTACK_CONFIG`), and rerun `mdstack layout --write`.
