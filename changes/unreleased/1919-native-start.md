---
type: added
issue: 1919
pr: TBD
date: 2026-11-15
box-skill: none
---

Add `mdstack start`, the owner's native start-or-reattach command for a tmux crew, listed in `mdstack --help`. It runs exactly `mdstack up --attach`, which stays as its alias: one session and watcher, `switch-client` from a client of the crew's server, and the same refusals of a foreign tmux client (exit 1) and a crew pane (exit 2) before anything starts. Without `--project` it uses the default config like other owner commands (`$CREW_PROJECT`, `$MDSTACK_CONFIG`, then `<user root>/config.toml`) and names it on stderr, so it works from any directory; a missing, invalid or ambiguous config, or `--team` or a role, refuses before anything starts. `mdstack layout --write` now writes `<home>/start` to run `mdstack start` and accepts a redundant `--attach`; a wrapper written earlier still runs `mdstack up` and keeps working, and an unmarked file at that path is still refused. Plain `mdstack up` is unchanged.
