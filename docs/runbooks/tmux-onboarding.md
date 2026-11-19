# tmux onboarding

Operator module for onboarding a repo onto a local tmux crew, split out of the
[onboarding runbook](../runbook-new-repo.md) under the M26 modular
organization principle ([#676](https://github.com/mw-ding/mdstack/issues/676)).
It holds the tmux prerequisites, the target-repo setup, the run procedure
and the troubleshooting table. The runbook keeps the parent
[tmux runtime](../runbook-new-repo.md#tmux-runtime) entry with the runtime
choice; the `mdstack` and `CREW_PROJECT` conventions used here are in
[Command conventions](#command-conventions).
The dated 2026-10-30 end-to-end run is history, not current instructions:
[tmux onboarding history](tmux-onboarding-history.md#end-to-end-run-2026-10-30).

## Command conventions

The runbook's Steps 0 to 8 describe the Grok Bot wiring after bootstrap. This
module runs the same pipeline as a local tmux crew instead: one tmux session per repo, one window
per agent, driven by the `mdstack` CLI. The design and every command's exact
behaviour are in the [tmux binding](../runtimes/tmux.md#usage); this is the
operator's path; the first run from install to a merged PR, with a copyable
config, is the [getting-started walkthrough](../guides/getting-started.md).
Below, `mdstack` is the launcher `mdstack install` puts on your `PATH`. Owner
commands take no `--project` (8.0.0): they read `$MDSTACK_CONFIG`, else
`~/.mdstack/config.toml`, and refuse `--project` with exit 2; `--repo KEY`
picks one repo of a team file. Crew windows keep `--project "$CREW_PROJECT"`:
every window gets `CREW_PROJECT`, the absolute path of the config `mdstack up`
used ([migration guide](../guides/migration.md)).

## tmux prerequisites

- tmux, Python 3.11+, `git`, and `gh` logged in as every login the profile
  names ([Q5](../runtimes/tmux.md#q5-identities)). One identity for every role
  is the default: verdicts are COMMENT reviews and each merge needs an owner
  merge-ok or a standing grant ([single-identity profile](../interfaces.md#single-identity-profile)).
- Claude Code and Codex installed, so the reviewer engine can differ from the
  builder engine ([roles.md](../roles.md#reviewer-engine-selection)).
- **Permission mode.** Role windows launch with
  `runtime.options.permission_mode`, default `bypass`: agents run any command
  in their worktree without asking, with no approval prompt and, for Codex,
  no sandbox ([mdstack spawn](../runtimes/tmux.md#mdstack-spawn)). Run the crew only
  on a machine, and with GitHub logins, where you accept that. `auto` and
  `safe` keep the harness's approval checks, but a window then waits on any
  prompt the host does not auto-approve; crew roles never answer one.
- **Codex hook trust on the host.** Every hook in the host's own Codex
  config must be trusted before `mdstack up`. One untrusted host hook shows
  `Hooks need review` in every Codex window; the crew then escalates to the
  owner and never types into the window ([Troubleshooting](#tmux-troubleshooting)).
- **Claude Code folder trust for the checkout.** Role worktrees take their
  folder trust from the repo checkout they come from, so a fresh clone stops
  every Claude Code role window at the trust dialog. When `paths.checkout` is
  outside the profile's directory, run `claude` once in the checkout, pick
  `Yes, I trust this folder`, then `/exit`, before dispatch. `mdstack doctor`
  lists it as the `claude role trust` human step until then (#408).
- An extracted release bundle ([README: Install](../../README.md#install)) or
  an mdstack checkout at `<mdstack>`, and a clone of the target repo at
  `paths.checkout` (`~/<repo>` by default).
- In a nested sandbox (an agent session that is itself sandboxed), the org
  pack's sandbox variable, passed as `CREW_SANDBOX_ENV=<NAME>=<value>` in the
  shell that runs `mdstack up` ([Troubleshooting](#tmux-troubleshooting)).

Next: [Set up the target repo](#set-up-the-target-repo).

## Set up the target repo

1. **Profile.** Write `~/.mdstack/config.toml` (or the file `$MDSTACK_CONFIG`
   names) from [profiles/tmux.toml](../../profiles/tmux.toml) plus `[repo]`,
   `identities.owners` and `paths.toolchain_bin`, as in
   [Write the config](../guides/getting-started.md#2-write-the-config).
   Any of `paths.state_dir`, `paths.worktree_root`, `paths.toolchain_bin` and
   `paths.live_dir` left unset falls back to a placeholder: set each to a real
   local path.
   `mdstack` refuses (exit 1) while a path it uses still resolves to a
   `<placeholder>`, including one inherited from the default profile because
   the key is missing (#265), so a stray copy such as the `config.toml` inside
   a worktree can never put state or the land lock under the worktree.
   Set `paths.mdstack` to `<state-dir>/<owner>__<repo>/mdstack` for bootstrap,
   or directly to `<mdstack>` for the manual fallback, so the briefs cite
   its docs in a repo that has none. Set `runtime.options.merge_grant` (default `none`: a
   merge-ok per PR), `hold_label_blocks` and `permission_mode` (default
   `bypass`) only if the owner chose otherwise
   ([profile.md: Keys](../profile.md#keys)). Preview and apply with
   [bootstrap](../runbook-new-repo.md#bootstrap-recommended). For the [manual fallback](../runbook-new-repo.md#manual-fallback),
   validate and resolve the profile; `mdstack up` renders in either path.
2. **Labels, milestone and reviewer.** `mdstack doctor --fix --milestone M1`
   creates the `crew:*` labels and an open `M1` milestone and invites a
   separate reviewer login; the manual equivalents are
   [Step 1](../runbook-new-repo.md#step-1-create-the-crew-labels) to Step 3.
3. **CI.** At least one check must run on every PR: review starts on each new
   head whatever its CI, but `sam` lands only when the CI rollup at head is
   green ([CI and review handoff](../runtimes/tmux.md#mdstack-poll)). Branch protection is
   unavailable on a private Free-plan repo, so the check cannot be made
   required there; the §7 re-check of CI at head is then the only guard
   ([Step 4](../runbook-new-repo.md#step-4-check-ci-and-branch-protection)).

Next: [Run the crew](#run-the-crew).

## Run the crew

Every command below runs from your own terminal, never from a crew window.
Each links to its exact behaviour in the [tmux binding](../runtimes/tmux.md#usage).

### Start and reattach

| Command | What it does |
|---|---|
| `mdstack start` (or `<home>/start`) | The everyday entry: starts the crew if it is down, then attaches your terminal to `ash` in window 0. A running crew gets no second session or watcher, so it is also how you reattach. Inside the crew's tmux server it switches your client instead of nesting; a client of another tmux server is refused (exit 1: detach first). A team file starts the whole team unless `--repo <key>` names one repo ([mdstack start](../runtimes/tmux.md#mdstack-start)) |
| `mdstack up` | Starts without attaching: renders the briefs, installs the coordinator's turn-end guard, starts the session with `ash` in window 0 and the enabled builder and reviewer leads, unless the [launch topology](../runtimes/tmux.md#launch-topology) or `--coordinator-only` starts none ([README: Bringing up the team](../../README.md#bringing-up-the-team)). On a running session it only prints the attach command; a running team session also picks up repos added to or removed from its team file ([mdstack up](../runtimes/tmux.md#mdstack-up)) |

### Attach modes

| Command | Starts the crew? | What you get |
|---|---|---|
| `mdstack attach` (no target) | **Yes**, when it is down | The same path as `mdstack start` for the installed team: an interactive terminal on `ash` |
| `mdstack attach <window>` or `<role>` | Never | A read-only view: keystrokes never reach the agent. Add `--rw` to type to it, as in `mdstack attach ash --rw` |
| `mdstack attach builders` | Never | A temporary tiled read-only view of the builder band, removed when you detach |

Use a target when you only mean to look; a bare `attach` on a stopped crew
starts it. Detach with the tmux prefix and `d`: detaching stops nothing.
Attaching selects that window for every client on the session
([mdstack attach](../runtimes/tmux.md#mdstack-attach)).

### Status and logs

| Command | What it does |
|---|---|
| `mdstack status` | A `coordinator` row, then one row per run: role, item, head, heartbeat age, liveness (`alive`, `dead`, `missing`, `ambiguous`), last status line ([mdstack status](../runtimes/tmux.md#mdstack-status)) |
| `mdstack logs <window> [-f]` | The run's step summary, never raw logs ([mdstack logs](../runtimes/tmux.md#mdstack-logs)) |
| `mdstack drain` | Prints and empties the wake queue; `ash` runs it each turn, so run it by hand only to inspect a stuck queue |

### Pause, resume and stop

| Command | Stops | Keeps |
|---|---|---|
| `mdstack pause [--reason <text>]` | Every role window | `ash`, the watcher, and every run's worktree, record, claim, inbox and status file. The `pause.json` barrier blocks new spawns and lands until `resume` |
| `mdstack resume` | Nothing | Ends the pause on your word: rechecks each stopped run live, restarts the ones still open and not held, starts the leads, and wakes `ash` |
| `mdstack down --preserve` | The watcher, every window and the session | Every run's work, for maintenance such as a migration; allowed while paused |
| `mdstack down` | The watcher, every role window, then the session | Any window with unlanded work: it names them and exits 1. Refused while the land lock is held or the crew is paused |
| `mdstack kill <window>` | One window's process group | Nothing: it removes the worktree and state, and refuses unlanded work unless `--discard --reason "<why>"` (step summaries under `.crew/` do not count) |

To stop work while you are away, pause: it is the safe shutdown that keeps
`ash` able to answer and the queue filling. `pause` exits 75 while a land is
in progress (run it again once the land ends) and 1 when a process survived
(pause again); `crew: paused` means done
([mdstack pause](../runtimes/tmux.md#mdstack-pause),
[mdstack resume](../runtimes/tmux.md#mdstack-resume)). Use `down` only to
end the session, `ash` included
([mdstack down](../runtimes/tmux.md#mdstack-down)). Never use
`tmux kill-server`: it skips the process-group stop
([troubleshooting](#tmux-troubleshooting)).

### Upgrade

`mdstack upgrade --version vX.Y.Z` (or `--latest`) fetches and verifies the
bundle, re-renders this project and every other project the install serves,
then moves `releases/current`, so the launcher follows. `--dry-run` previews
the plan. On a running crew it waits for every current pass to finish
(`--wait-timeout`, default 300 seconds; a timeout changes nothing), then
restarts the roles with their worktrees, claims and inboxes kept, `ash` last.
Rolling back is the same command with the previous tag. A major version waits
for your OK after its `**Breaking:**` entries
([release.md: Update path](../release.md#update-path),
[mdstack install](../runtimes/tmux.md#mdstack-install)).

### Recover

| Situation | Do |
|---|---|
| A run shows `dead` or `missing` | `ash` decides per run. By hand: `mdstack restart <window>` restarts it once, keeping unlanded work in its worktree; a second failure escalates ([mdstack restart](../runtimes/tmux.md#mdstack-restart)) |
| `ash` hangs or died | `mdstack restart ash` from your own terminal relaunches the coordinator in place, resuming per `launch.resume` |
| The tmux server died, the machine rebooted, or after `down --preserve` | `mdstack start` rebuilds the session and `ash` from disk with the existing wake queue. Recorded runs probe `missing`; `up` never respawns them, and `ash` decides per run with `mdstack restart` |
| The crew was paused before the restart | It stays paused: `mdstack start` brings back only `ash` and the watcher. Run `mdstack resume` |
| Duplicate or lost runs | [Deduplication and recovery](../runtimes/tmux.md#deduplication-and-recovery) |
| Anything else | [tmux troubleshooting](#tmux-troubleshooting) |

### First start, wake path and owner duties

**First start: the trust dialog.** A Claude Code coordinator opens at its
folder-trust dialog, whose default answer is `No, exit`, and `mdstack status`
shows `ash` as `ambiguous`. Run `mdstack attach ash --rw` once and accept it.
That answer also covers the role worktrees only when the checkout is the
profile's directory; otherwise trust the checkout as in the
[prerequisites](#tmux-prerequisites).

**Wake path.** `ash` keeps one watcher armed as a background command,
`$CREW_BIN watch --source "$CREW_BIN poll --once --project \"$CREW_PROJECT\"" --project "$CREW_PROJECT"`,
and re-arms it every turn; the turn-end guard blocks a stop with work in
flight and no watcher. The source must be one-shot (`--once`): a looping
source is cut off and recorded in `wake/incidents.jsonl`, waking as
`source-failing` after three in a row. To check it is
armed, `wake/watcher.pid` under `<state-dir>/<owner>__<repo>/` must name a
live `mdstack watch` process. Start work by assigning a `crew:ready` issue.

**Close-out.** On `pr-merged`, `ash` kills the item's windows, removes
`crew:approved`, `crew:hold`, `crew:in-review` and `crew:changes` from the PR
and `crew:ready` from the issue, and deletes the head branch only when the
PR is merged, its head is in the same repo, and the branch is its
`headRefName` and neither the default nor the base branch (#255, #266).

**Owner duties.**

- **CI:** keep the PR check working; a red check on the default branch is
  yours to fix or file.
- **Merge-ok:** after the verdict passes, `ash` asks for your merge-ok. The
  ask's default at its deadline is to keep the PR on hold: nothing
  auto-applies a merge-ok (#255). Tell `ash` in window 0 that PR `<n>` has
  your merge-ok; it records the `pass=steer cmd=merge-ok` marker at the full
  head SHA from your words only, and the synthesizer lands. A standing
  `merge_grant` in the profile replaces this for PRs in scope.
- **Asks:** answer what `ash` raises in window 0 and on GitHub
  (`crew:needs-md`), including dialog escalations, which come with a
  runnable `mdstack attach <window> --rw` command.

Next: [tmux troubleshooting](#tmux-troubleshooting).

## tmux troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ash` or a Claude Code window stays `ambiguous` | Its folder-trust dialog is waiting | `mdstack attach <window> --rw` and accept it. Never type a blind Enter: it picks `No, exit`. For role windows, also trust the checkout once ([prerequisites](#tmux-prerequisites)) so the next one starts clean |
| Every Codex window shows `Hooks need review`; `ash` posts an owner ask | An untrusted hook in the host's own Codex config (a host prerequisite, not a crew setting) | Trust that hook in the host's Codex config, then let `ash` respawn the windows. Answering one window by `mdstack attach <window> --rw` does not persist; crew roles never type into a window |
| A command exits 1 naming a `<placeholder>` path | A path in the resolved profile is still a placeholder, set or inherited (#265) | Set the key to a real path in `config.toml`; in a window, use `--project "$CREW_PROJECT"`, never a relative `config.toml` |
| `mdstack kill` or `mdstack down` exits 1, or harness processes outlive the session | The pane's process group did not stop (Codex ignores the `SIGHUP` from `kill-window`); `tmux kill-server` skips the group stop entirely | Use `mdstack kill` / `mdstack down`, never `kill-server`. List leftovers with `ps -axo pid,pgid,command`, then `kill -TERM -<pgid>` |
| Panes die at once; the harness exits 71 with `sandbox_apply: Operation not permitted` | Nested sandbox: the window did not inherit the outer sandbox setting | `mdstack down`, export `CREW_SANDBOX_ENV=<NAME>=<value>` (the org pack names it), `mdstack up`. Every window, window 0 included, gets it |
| A role window waits on an approval or permission prompt (`gh`, `git commit`, a read of its brief) | `runtime.options.permission_mode` is `auto` or `safe` and the host does not auto-approve (#269, #288, #293) | Set `permission_mode = "bypass"` (the default) in `config.toml`, then `mdstack kill` the window and spawn it again; or approve on the host |
| The guard lets `ash` stop with work in flight, or never blocks | Stale `wake/watcher.pid`: a watcher killed with `SIGKILL` cannot remove it, and a reused PID looks armed | If `ps -p "$(cat wake/watcher.pid)" -o command=` is not `mdstack watch`, delete the file; `ash` re-arms on its next turn |
| A run never moves; queue records pile up | No watcher armed, or a looping `--source` | `mdstack drain` to see the records, then have `ash` re-arm with `poll --once` |
