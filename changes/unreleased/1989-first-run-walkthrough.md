---
type: changed
issue: 1989
pr: 2002
date: 2026-11-18
box-skill: none
---

First-run walkthrough: `docs/guides/getting-started.md` is now the one complete path from install to a first merged PR. It gives a copyable `~/.mdstack/config.toml` block checked with `crew-config.py resolve`, the identity choice (one account with emulated verdicts, or a separate reviewer) and its merge permission, two engines for an independent reviewer, `mdstack doctor --fix --milestone M1` for labels and milestone, bootstrap, start, a first issue via `mdstack bootstrap --smoke --yes`, and the build, review, CI, merge-ok and merge results to expect, with recovery links. `docs/runbooks/tmux-onboarding.md` and `docs/runbooks/profile-install.md` drop the owner `--project` / `CREW_PROJECT` examples for 8.0.0 owner commands (crew windows keep `--project`) and no longer say labels and milestones are manual. The README Quickstart checks the config with `resolve`, since `validate` rejects a layered user config on its own.
