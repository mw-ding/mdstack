---
type: fixed
issue: 1957
pr: 2060
date: 2026-11-22
box-skill: none
---

Session `mdstack up` parity: window 0's command exports the `CREW_*` variables instead of `tmux new-session -e`, so a window the owner opens in the crew session carries none; the new `runtime.options.launch.cwd` sets the coordinator's working directory (default: the profile's directory) for `up`, `restart` and an upgrade reload; `mdstack start` and `mdstack up --attach` attach a session-runtime crew; and the coordinator's launch line derives `GH_TOKEN` only when a backend is bound to `github` (GitHub renders unchanged).
