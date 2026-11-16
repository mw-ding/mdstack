---
type: added
issue: 1942
pr: 1954
date: 2026-11-15
box-skill: none
---

A bare `mdstack attach` (no target, no `--project`) now types into the coordinator window of the installed team. It resolves the profile as other owner commands do (`$CREW_PROJECT`, `$MDSTACK_CONFIG`, `<root>/config.toml`) and then falls back to the root's only `<team>.toml` team file, the #1348 home layout honouring `[team] name`. A multi-repo team file needs no `#<repo>`, since the session is per team. A team that is down starts first, as `mdstack up --team` (persistent watcher included) or `mdstack up --project` for a one-repo profile, and is not attached when that start fails. As with `mdstack start`, it attaches interactively to window 0, switches the client instead of nesting from inside the crew's tmux server, and refuses a crew pane or a client of another tmux server before anything starts. `mdstack attach coordinator` also accepts a team file without `#<repo>`. Every targeted `mdstack attach WINDOW|ROLE|builders [--rw]` form, remote runs included, is unchanged and still read-only by default.
