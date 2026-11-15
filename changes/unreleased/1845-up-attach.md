---
type: added
issue: 1845
pr: TBD
date: 2026-11-14
box-skill: none
---

Add `mdstack up --attach`, also `<home>/start --attach`: the owner's one start-or-reattach command for a tmux crew. It runs `mdstack up`, so a running crew gets no second session or watcher, then attaches the terminal interactively to window 0 on the server `runtime.options.tmux_server` resolves, or switches a client of that server there with `switch-client` instead of nesting. A client of another tmux server, or a crew pane with `CREW_ROLE` set, is refused before anything starts.
