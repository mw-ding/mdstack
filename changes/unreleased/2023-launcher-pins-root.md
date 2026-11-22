---
type: fixed
issue: 2023
pr: TBD
date: 2026-11-22
box-skill: none
---

Install: a launcher `mdstack install` writes for a root other than `~/.mdstack` now runs `CREW_ROOT=<root> exec …`, so a bare `<launcher> up` reads that root's `config.toml` instead of `~/.mdstack/config.toml`. `--project`, `$CREW_PROJECT` and `$MDSTACK_CONFIG` still win, and the `~/.mdstack` launcher's bytes are unchanged. `mdstack install` and `mdstack upgrade` rewrite a stale launcher in their root; `--dry-run` lists it.
