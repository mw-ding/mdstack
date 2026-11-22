---
title: The 7.16.0 → 8.x upgrade exited 2 because 8.x refused the 7.x bootstrap's own `upgrade --project` re-exec as an owner-shell `--project`; 8.x now accepts it when the verified bundle sha is set (#2024)
date: 2026-11-22
status: applied
source: Runtime blocker on mw-ding/mdstack#1976, intake issue #2024
---

# An 8.x guard refused the 7.x bootstrap's re-exec, 2026-11-22

## Test a cross-release handoff from the old release's real caller

- **Date:** 2026-11-22
- **Source / evidence:** Issue #2024 and its root-cause comment: on 7.16.0,
  `mdstack upgrade --latest --dry-run` verified the 8.1.0 bundle, then exited
  2 with `mdstack: --project is disabled; ...`. Affected files:
  `environments/terminal/crew.d/_shared.py` (`owner_shell()`, `main()`),
  `environments/terminal/crew.d/bootstrap.py` (the tmux human step) and
  `docs/guides/migration.md` (7.x to 8.0.0).
- **Finding:** 7.16.0 `bootstrap.fetch` re-execs
  `<8.x>/cli/mdstack upgrade --project <file> ...`, adding only
  `CREW_BOOTSTRAP_BUNDLE_SHA256` to the environment. 8.0.0 (#1965) refuses
  `--project` from any process without `CREW_ROLE` or `MDSTACK_INTERNAL`. An
  8.x parent sets `MDSTACK_INTERNAL` for its children, so 8.x → 8.x passed
  every test; nothing exercised the 7.x parent, which sets neither. The
  migration guide documented a command that could not run from any owner
  shell. The 8.x bootstrap also still printed `Human step: Run mdstack up
  --project <file>`, which the same guard refuses.
- **Impact:** The documented upgrade to 8.1.0 failed for every owner until
  the `MDSTACK_INTERNAL=1` workaround was found. Nothing was written: the
  refusal comes before any read or write.
- **Fix:** 8.x `main()` accepts `--project` for `upgrade` when
  `CREW_BOOTSTRAP_BUNDLE_SHA256` is set. Every other owner-shell `--project`
  stays refused. `test-crew-upgrade.py` re-execs the CLI exactly as 7.16.0's
  `fetch` does, with refusal controls. The human step names a command 8.x
  accepts. The migration guide keeps the workaround for 8.0.0 and 8.1.0
  targets. Correction level: a regression test at the real entry point
  ([real-entrypoint fixtures](2026-11-08-real-entrypoint-fixtures.md)).
- **Status:** applied: `bootstrap_reexec()` in `_shared.py` and the
  `test_7x_bootstrap_reexec_from_an_owner_shell` test (#2024). No
  `scripts/check-repo.py` check enforces it.
- **Linked issue/PR:** #2024, #1965, #1976
