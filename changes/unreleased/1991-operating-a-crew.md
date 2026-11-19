---
type: changed
issue: 1991
pr: TBD
date: 2026-11-18
box-skill: none
---

Operating a crew is now discoverable: `docs/runbooks/tmux-onboarding.md` splits "Run the crew" into start and reattach (`mdstack start`), attach modes (a bare `mdstack attach` can start a stopped crew; a targeted attach never does and is read-only without `--rw`), status and logs, pause and resume beside `down`, `down --preserve` and `kill` with what each stops and keeps, upgrade, and a recovery table (dead run, hung coordinator, tmux server loss or reboot, a paused crew after restart). `docs/runbook.md` routes each of these tasks to its section. `docs/runtimes/tmux.md` says owners run the installed `mdstack` launcher, points `mdstack down` at `mdstack pause` for a stop that keeps the coordinator, and drops the owner `--project` wording from `mdstack upgrade`.
