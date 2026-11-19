---
type: changed
issue: 1993
pr: 2005
date: 2026-11-18
box-skill: none
---

Upgrade docs for 8.0.0: `docs/guides/migration.md` now opens with an ordered 7.x to 8.0.0 owner migration (upgrade, drop `--project` from owner commands and scripts in favour of `--repo <key>` or `MDSTACK_CONFIG`, rerun `mdstack layout --write`, check; crew windows and the low-level tools keep `--project`), and keeps the 7.0.0 reinstall recipe below it, labelled as version history with its 7.x command forms. `docs/release.md` points the major-upgrade decision and update path at the migration, and the docs index and operations router link both sections. Owner command examples in `docs/bootstrap.md`, `docs/roles-registry.md`, `docs/runbooks/repo-rename.md`, `docs/runbooks/offboarding.md`, `docs/specs/shared-status.md`, `docs/configuration/team-files.md` and `docs/runtimes/session.md` drop `--project` for the installed team, `--repo` or `MDSTACK_CONFIG`; crew-window and low-level `--project` examples are unchanged.
