# Harness adapter interface

What a runtime must know about one agent CLI (a harness) to launch it in a
role session, wake it and probe it, so adding a harness means filling in one
adapter here, not editing the runtime (portable mdstack, roadmap 15.4,
[#177](https://github.com/mw-ding/mdstack/issues/177); fields from
[#160 row 13](https://github.com/mw-ding/mdstack/issues/160#issuecomment-6532100410)).
Each field names the [runtime contract](README.md#contract) capability it
serves. This page adds no rule, gate, cap, marker field or label; the
[protocol](../protocol.md) still owns them.

The Claude Code and Codex adapters record what the tmux binding does today
([tmux.md](tmux.md), M14 and M14.1). A value tmux.md marks as not yet
verified on the real CLI is marked the same way here.

## Fields

| Field | The adapter states | Serves |
|---|---|---|
| Launch line | The command that starts the harness interactively in the run's directory, with the role run's model and effort. The brief goes by pointer only: one short fixed line naming `$CREW_BRIEF`, never the brief in argv or typed keys. Any flag the run needs to write its status file. | C3 |
| Trust and first-run dialogs | Each prompt the harness can show before it reads the pointer, how to avoid it (a pre-trust flag or a one-time owner step) and the screen text that identifies it. A run waiting at one probes `ambiguous`, never `alive`. | C5 |
| Turn-end and wake recipe | How a finished coordinator turn is started again when the watcher exits, the turn-end guard that keeps a turn from ending blind, and how a typed line starts a turn in a role session. | C1 |
| Idle detection | How the runtime tells that the harness is waiting for input, so a typed wake line goes only into an idle session. | C1 |
| Expected foreground process | The process name the liveness probe and the spawn start check expect in the session's foreground while the harness runs. Any other name probes `ambiguous`. | C5 |
| Transient-error text | The harness's own error line for a retried gateway error (HTTP 429 or 5xx, rate limit), anchored so tool output, file names, diffs and quoted text on the pane never match. `mdstack watch` matches it on each live run's screen and appends each new line to `schedule/errors.jsonl`, a [scheduler input](../scheduling.md#inputs); the same text from the same run within 10 minutes counts once. None declared: nothing is recorded for that harness. | C5 |
| Usage-limit text | The harness's own line saying the account is out of quota, anchored like the transient-error text. A run whose pane shows it probes `quota`, and `mdstack restart` relaunches it once, in place, on the next eligible engine in its role's order (#631). None declared: that harness never probes `quota`. | C5 |
| Code-review skill | The harness-native code-review skill or subcommand a self-gate review sub-session loads beside the protocol §3 rubric ([express lane](../express-lane.md#self-gate-loop)), and how a non-interactive run invokes it. None declared: the sub-session uses the rubric alone. | Express self-gate (no contract capability) |
| Session usage | How to read a run's token totals (input, cached input, output) and model from the harness's local session log, for the informational [usage line](../roles.md#usage-line). None declared: the line says `tokens n/a`. | Usage line (no contract capability) |
| Install pointer | The project-local discovery files or launch prompt that point at the rendered brief, their exclude entries, and files the installer must never edit. Bootstrap's `--harness` selection installs them without launching a session. A pack's own pointers for an adapter with this field install the same way ([pack harness pointers](../bootstrap.md#pack-harness-pointers-design), #883). | C3 |

## Adapter modules

Each adapter is one module, `harnesses/<engine>/adapter.py`, named by the
profile's engine id. `harnesses/crew-harness.py` discovers them in sorted
name order and derives every engine table from them (#1182):

- the profile's engine choices (tier orders, `fallback_engine`, pack
  capabilities) and the coordinator choices;
- the executable aliases that `mdstack doctor`, remote readiness (`mdstack host
  check` and the host's `check` verb) and the liveness probe use;
- the `mdstack bootstrap --harness` choices and the built-in install targets no
  pack pointer may claim.

`mdstack spawn`, `mdstack up`, `mdstack upgrade` reload, `mdstack doctor`, `mdstack status`,
`mdstack watch`, `mdstack send` and remote readiness consume the module; none of
them names a harness. A module states:

| Name | Required | Field it implements |
|---|---|---|
| `EXECUTABLE`, `TITLE` | yes | the CLI on `PATH` and the expected foreground process; the name in refusals |
| `ENGINE_RANK`, `LAUNCH_RANK` | no | position in the engine and coordinator choice lists; unranked adapters follow, by engine id |
| `LOGIN_STATUS` | no (default `auth status`) | the read-only login check `mdstack host check` runs |
| `PERMISSION`, `PERMISSION_REFUSAL` | with a launch | flags per supported `permission_mode`; an absent mode is refused with the message |
| `launch_refusal(mode, uid)` | no | why a role window cannot launch in `mode` on a host whose effective uid is `uid`, or `None`; the core asks before the window opens, on the execution host (Claude Code: `bypass` as root, #738) |
| `role_cwd(wt)` | no | startup directory for a local role launch or restart; absent means the assigned worktree. Claude Code uses the stable parent for run copies and tells tools to work in the assigned copy |
| `builder_checks(values)` | no | run-copy trust rows: doctor reports them; up, local builder spawn and restart warn before launch |
| `role_argv(model, effort, wt, state, flags)` | with a launch | role launch line (C3); without it the engine is schema-only and `mdstack spawn` skips it |
| `coordinator_argv(project_dir, state, flags)`, `RESUME` | with a launch | coordinator launch line, and its `launch.resume` verb (none: refused) |
| `coordinator_setup(project_dir, state)` | no | turn-end guard `mdstack up` installs for this coordinator (C1) |
| `host_checks()`, `coordinator_checks(values, project_dir)`, `role_checks(values, checkout)` | no | trust and preflight rows: `mdstack up` refuses on a failed host check; `mdstack doctor` prints all three, role checks against the checkout role worktrees come from (C5) |
| `sandbox_roots(values)` | no | the writable roots its launcher grants a session by default, or `None` when it sandboxes none: `mdstack doctor`'s `sandbox` row and `mdstack up` refuse when none covers the checkout's `.git` and no `sandbox_env` is set ([mdstack doctor](tmux.md#mdstack-doctor), #1544) |
| `PROCESS`, `foreground_tty(tty)` | no | other foreground names, or a tty signature, that count as the harness (C5) |
| `PROMPTS`, `FATAL` | no | blocking-dialog heading and footer pairs, and the fatal API error line (C5) |
| `BUSY`, `COMPOSER` | no | mid-turn screen text `mdstack upgrade` waits out, and the composer's prompt glyph (C1) |
| `TRANSIENT` | no | transient-error text (C5) |
| `QUOTA` | no | the harness's own usage-limit line: the run probes `quota`, and `mdstack restart` relaunches it once, in place, on the next eligible engine in its role's order (C5, #631) |
| `usage(directory, start)` | no | session usage: `{input, cached, output, model}` totals since `start` (epoch seconds) from the logs of runs in `directory`, or `None` with no log entry; [`scripts/run-usage.py`](../../scripts/README.md#run-usage-helper) prints `tokens n/a` then |
| `install_targets(project, state, pointer, check)`, `INSTALL_TARGETS`, `install_launch(project, pointer, notes)` | no | install pointer files, their paths, and a printed launch line that pack launch notes extend (C3) |

Policy stays in the crew core. Engine independence picks the engine, model
and effort and the adapter receives them. The core checks the permission mode
and the [contributor-tier rule](../roles.md#hard-rules) (an adapter with
`CONTRIBUTOR_TIER = True` launches only on a verified public repository)
before it calls `role_argv` or `coordinator_argv`.

Out of scope here: creating the window, attaching, delivering the doorbell
line, probing run identity and stopping the run belong to the
[session backend](session-backends.md). The tmux stop
signals the process group because Codex ignores the `SIGHUP` that closing a
tmux window sends ([mdstack kill](tmux.md#mdstack-kill)).

Every launch line below runs in the window's own shell after
`export GH_TOKEN="$(gh auth token --user "$CREW_IDENTITY")"; exec`, so no
token reaches argv ([tmux.md Q5](tmux.md#q5-identities)). `<pointer>` is
`"Read your brief at $CREW_BRIEF and follow it."`, double-quoted so the shell
expands the path.

## Claude Code (`claude-code`)

| Field | Claude Code |
|---|---|
| Launch line (C3) | Role: `claude --model <model> --effort <effort> --add-dir <state-dir>/<owner>__<repo> <mode-flags> <pointer>`, `<mode-flags>` per `runtime.options.permission_mode` ([mdstack spawn](tmux.md#mdstack-spawn)); default `bypass`: `--permission-mode bypassPermissions --settings '{"skipDangerousModePermissionPrompt":true}'`. Coordinator: `claude <pointer>` in the project directory, with no model or effort flags. |
| Trust and first-run dialogs (C5) | Folder trust, with no documented per-project trust option. The dialog's default answer is `No, exit`, so a blind Enter exits. The owner accepts it once with `mdstack attach <window> --rw` for the coordinator's project directory. Claude Code keys a linked worktree's trust on its repository root (Claude Code 2.1.310), so role windows need the checkout they come from trusted: the coordinator's answer covers it only when the checkout is the project directory. With `paths.checkout` elsewhere (the `~/.mdstack/` layout), the owner runs `claude` once in the checkout and picks `Yes, I trust this folder` before dispatch; `mdstack doctor` lists it as the `claude role trust` human step until then (#408). Independent builder copies instead launch from the stable `paths.worktree_root`, with `--add-dir <copy>` and an appended instruction to use explicit `cd <copy>` for shell commands and absolute file paths. Trust that root once per host; `doctor` lists `claude copy trust`, and up, spawn and restart warn before launching when it is missing (#1792). mdstack never writes the Claude Code config. Identified by `trust` and `No, exit` on the pane's screen. Later stops that also probe `ambiguous` ([mdstack status](tmux.md#mdstack-status), #289): a permission prompt in `auto` and `safe`, `Do you want to …?` over an `Esc to cancel` last line, and a fatal `⎿  API Error: <4xx or 5xx> {"type":"error",…}` line. |
| Turn-end and wake recipe (C1) | Coordinator: its background `mdstack watch` command completes and the harness starts a turn. Backup: the watcher types `wake: watcher` into an idle window 0 unless run with `--no-nudge` or a dialog is on its screen (#315). Turn-end guard: a `Stop` hook running `mdstack guard --state <state-dir>/<owner>__<repo>`, which `mdstack up` adds to `<project>/.claude/settings.local.json`; it blocks at most once per stop cycle (`stop_hook_active`) and is a safety net, not the only wake path ([#160 row 4](https://github.com/mw-ding/mdstack/issues/160#issuecomment-6531265464)). Role session: a typed line plus Enter is a new prompt (the `inbox: <msg-id>` nudge). |
| Idle detection (C1) | `claude` in the foreground and no pane output for `--idle` seconds (default 30), read from tmux's window activity time; no screen parsing. |
| Transient-error text (C5) | Claude Code's own error line: `⎿  API Error` at the result gutter (at most two spaces in), followed directly by 429 or a 5xx status, for example `⎿  API Error (529 …) · Retrying in 2 seconds… (attempt 1/10)`. The fatal `API Error: <5xx>` line also matches. Tool output, file names, diffs and quoted text never count, even when they name `rate limit`, `429` or `API Error` (#1366). |
| Usage-limit text (C5) | Claude Code's own limit line at the same gutter: `⎿  Claude usage limit reached …`, `⎿  You've hit your limit · resets …`, `⎿  5-hour limit reached …` or `⎿  Weekly limit reached …` (#631). |
| Expected foreground process (C5) | `claude`: as `#{pane_current_command}` or any foreground process of the pane's tty, within the spawn `--timeout` (default 15 s) and then in every probe. The spawn start check also takes the name of the file `claude` resolves to on `PATH` as the pane command, since tmux reports the native installer's symlink by its target's name, the version (for example `2.1.314`, [#286](https://github.com/mw-ding/mdstack/issues/286)). `node` probes `ambiguous`. |
| Session usage | Transcripts `<config>/projects/<directory with each non-alphanumeric character as ->/**/*.jsonl` (`<config>` is `$CLAUDE_CONFIG_DIR`, default `~/.claude`), subagent logs included. Each assistant entry since the start counts once per message and request id: input is `input_tokens` plus cache-write and cache-read tokens, cached is the cache reads, output is `output_tokens`; the model is the entry's `message.model`. |
| Code-review skill | `code-review`: name `/code-review` in the `claude -p` review prompt (listed as a built-in skill in Claude Code 2.1.310). |
| Install pointer (C3) | `mdstack bootstrap --harness claude-code`: `.claude/agents/crew-<role>.md` for builder, reviewer and synthesizer, plus `.claude/skills/crew-coordinator/SKILL.md`, each with frontmatter and a one-line brief pointer; `.claude/settings.local.json` gets the Stop hook. Each path is excluded locally and hash-recorded. Tracked, unowned or edited targets and symlinked project paths are refused; tracked `AGENTS.md` / `CLAUDE.md` and home files are never edited. See [bootstrap Q4](../bootstrap.md#q4-install-targets). |

## Codex (`codex`)

| Field | Codex |
|---|---|
| Launch line (C3) | Role: `codex -m <model> -c model_reasoning_effort=<effort> -c 'projects={"<worktree>"={trust_level="trusted"},"<repo-root>"={trust_level="trusted"}}' <mode-flags> --add-dir <state-dir>/<owner>__<repo> <pointer>`, `<mode-flags>` per `runtime.options.permission_mode` ([mdstack spawn](tmux.md#mdstack-spawn)); default `bypass`: `--dangerously-bypass-approvals-and-sandbox`. `--add-dir` lets every pass write `$CREW_STATUS` and `verdicts/` (C4) in `auto` and `safe`. Coordinator: `codex -c 'projects={"<project-dir>"={trust_level="trusted"},"<repo-root>"={trust_level="trusted"}}' <pointer>` (real paths; the repo root only in a git repository), with no model or effort flags. |
| Trust and first-run dialogs (C5) | Folder trust: avoided by the `projects` table, for the worktree (coordinator: the project directory) and its repository root, where Codex applies a linked worktree's trust; the `projects."<dir>".trust_level` form did not avoid it on codex-cli 0.164 ([#262](https://github.com/mw-ding/mdstack/issues/262)). Hooks review: one untrusted hook in the host's own Codex config shows `Hooks need review` in every Codex window; `mdstack up` refuses before rendering while a host `hooks.json` or inline `config.toml` hook lacks stored trust; review/trust it once in plain `codex`, since answering one window does not persist. The check never writes config or recomputes hashes; stale hashes and plugin/project hooks still rely on the live dialog check. Identified by `Hooks need review` on the pane's screen. Folder trust shown anyway: `Trust this folder?` over an `enter continue · esc …` last line. Later stops that also probe `ambiguous` ([mdstack status](tmux.md#mdstack-status), #289): an approval prompt in `auto` and `safe` (for example `gh` with no network, [#269](https://github.com/mw-ding/mdstack/issues/269)), `Would you like to …?` over a `Press enter to confirm or esc to cancel` last line, and a fatal `■ {"type":"error","status":<4xx or 5xx>,…}` line. |
| Turn-end and wake recipe (C1) | Coordinator: a completed background command does not start a turn, so the watcher types `wake: watcher` into an idle window 0 (on by default; never into a dialog, #315). Turn-end guard: Codex runs its `notify` program after each turn; the [documented recipe](tmux.md#mdstack-guard) points it at `mdstack guard` and types `wake: turn-end guard` into window 0 when it blocks, at most once per stop cycle (not installed by `mdstack up`; verified on codex-cli 0.164.0, [#170](https://github.com/mw-ding/mdstack/issues/170)). Role session: a typed line plus Enter is a new prompt (the `inbox: <msg-id>` nudge). |
| Idle detection (C1) | `codex` in the foreground and no pane output for `--idle` seconds (default 30), read from tmux's window activity time; no screen parsing. |
| Transient-error text (C5) | Codex's own error banner, a line opening with `■`, that carries a `"status": 429` or 5xx field, as in the fatal `■ {"type":"error","status":503,…}` line; 429 or a 5xx code followed by its status text or `retry`, for example `■ exceeded retry limit, last status: 429 Too Many Requests`; or `rate limit`. Tool output, file names, diffs and quoted text never count (#1366). |
| Usage-limit text (C5) | Codex's own banner, `■ You've hit your usage limit. … try again in …` (#631). |
| Expected foreground process (C5) | `codex`: as `#{pane_current_command}` or any foreground process of the pane's tty, within the spawn `--timeout` (default 15 s) and then in every probe; the start check also takes the name of the file `codex` resolves to on `PATH` as the pane command. Any other name probes `ambiguous`. |
| Session usage | Session logs `$CODEX_HOME/sessions/**/*.jsonl` (default `~/.codex`) whose `session_meta` cwd is the directory. Per log, the last `token_count` event's cumulative `total_token_usage` less the last one before the start: `input_tokens` (which already counts cached input), `cached_input_tokens` and `output_tokens`; the model is the last `turn_context` model. |
| Code-review skill | `codex review`: `codex review -c model=<model> "<rubric prompt>" </dev/null`, the prompt naming the self-gate brief file and the `git diff <merge-base>...HEAD` scope. On codex-cli 0.164.0 `--base`, `--commit` and `--uncommitted` cannot be combined with a prompt (exit 2), so the prompt carries both the rubric and the scope. |
| Install pointer (C3) | `mdstack bootstrap --harness codex`: print and record the coordinator launch command with the rendered brief pointer and per-process pre-trust override. No project discovery file; tracked `AGENTS.md` and `~/.codex/` are never edited. Role launches keep `mdstack spawn`'s model, effort and state access flags. See [bootstrap Q4](../bootstrap.md#q4-install-targets). |

## Pi (`pi`)

| Field | Pi |
|---|---|
| Launch line (C3) | Role: `pi --approve --model <model> --thinking <effort> <pointer>`. Coordinator: `pi --approve <pointer>`, using Pi's configured model and thinking level. Select `engines.coordinator = "pi"` or put `pi/<provider>/<model>` in a tier order; the provider prefix is passed intact to `--model`. Authentication uses the provider's existing login or environment variables, never `--api-key`. |
| Trust and first-run dialogs (C5) | `--approve` trusts project-local resources for this process and avoids the built-in project trust prompt. Configure provider credentials once before dispatch. Pi has no built-in per-tool approval or sandbox, so this adapter supports only `runtime.options.permission_mode = "bypass"`; `auto` and `safe` are refused. The process can read the brief and write state without `--add-dir`. Custom extension dialogs are not recognized by the probe: disable such extensions before unattended dispatch. |
| Turn-end and wake recipe (C1) | Coordinator: the watcher types `wake: watcher` into idle window 0 by default. Role: a typed `inbox: <msg-id>` line plus Enter starts a new turn. Pi's extension `agent_end` event could invoke `mdstack guard` and arrange a wake, but no extension is installed here. Gap: automatic turn-end guard integration is unimplemented; keep the watcher running. |
| Idle detection (C1) | `pi` in the foreground and no pane output for `--idle` seconds (default 30), using tmux's window activity time. This is the same activity heuristic as the other adapters; real Pi wake timing is not yet verified. |
| Busy and composer screen (C1) | Gap: none declared, so `mdstack upgrade` reads no mid-turn screen text from this pane (it still waits on a live child process and an unfinished status line), and `mdstack send` finds no composer glyph, so it cannot clear stale nudges or confirm a nudge was submitted. Declare `BUSY` and `COMPOSER` only from verified screen captures. |
| Transient-error text (C5) | Gap: none declared, so the watcher records no gateway errors from this harness's pane. |
| Usage-limit text (C5) | Gap: none declared, so a usage-limit screen on this harness's pane never probes quota and gets no next-engine restart. |
| Expected foreground process (C5) | `pi` (Pi sets its process title): the pane command or a foreground process name on its tty at spawn and in each probe. The spawn check also accepts the resolved executable's basename. A generic `node` process alone probes `ambiguous`. Run identity, dead and missing checks are unchanged. |
| Code-review skill | Gap: none declared, so a self-gate review on this harness uses the protocol §3 rubric alone. |
| Install pointer (C3) | The launch prompt points to `$CREW_BRIEF`; no project or home discovery files are written. Gap: `mdstack bootstrap --harness pi` is not implemented. Use the existing rendered tmux briefs with `mdstack up` / `mdstack spawn`. |

Pi is a harness, not a model subscription: select the provider explicitly and
apply the [contributor-tier rule](../roles.md#hard-rules) to that provider.
Never route private repositories to contributor-tier or free-credit providers;
use an eligible authenticated provider. This adapter does not change the
default tier orders or grant pay-per-use permission.

Launch flags and trust behavior follow Pi's
[CLI reference](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md)
and [security notes](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/security.md).
Fake-binary tests cover launch and liveness; a live provider session has not
been exercised.

## Cursor (`cursor`)

| Field | Cursor |
|---|---|
| Launch line (C3) | Role: `cursor-agent --force --model <model> <pointer>`. Coordinator: `cursor-agent --force <pointer>`, using its configured model. Select `engines.coordinator = "cursor"` or an explicitly permitted `cursor/<model>` tier entry. Cursor has no CLI effort flag: effort stays in attribution but cannot be enforced by this adapter. Authentication uses an existing `cursor-agent login` session or `CURSOR_API_KEY`, never `--api-key`. |
| Trust and first-run dialogs (C5) | Authenticate and accept workspace trust once with the owner attached before unattended dispatch. `--force` allows commands unless explicitly denied; it does not override workspace trust or configured deny rules. `--trust` is headless-only, so it is not passed to this interactive launch. This adapter supports only `permission_mode = "bypass"`; `auto` and `safe` are refused. Gap: Cursor-specific trust/login screen detection has not been verified; a foreground process alone cannot prove these dialogs are absent. |
| Turn-end and wake recipe (C1) | Coordinator: keep the watcher running; it types `wake: watcher` into idle window 0. Role: a typed `inbox: <msg-id>` line plus Enter starts a turn. Gap: no Cursor turn-end hook or guard is installed. Interactive wake timing has not been verified on the real CLI. |
| Idle detection (C1) | Expected Cursor foreground process and no pane output for `--idle` seconds (default 30), from tmux window activity. This is an activity heuristic, not proof that Cursor is ready to accept input. |
| Busy and composer screen (C1) | Gap: none declared, so `mdstack upgrade` reads no mid-turn screen text from this pane (it still waits on a live child process and an unfinished status line), and `mdstack send` finds no composer glyph, so it cannot clear stale nudges or confirm a nudge was submitted. Declare `BUSY` and `COMPOSER` only from verified screen captures. |
| Transient-error text (C5) | Gap: none declared, so the watcher records no gateway errors from this harness's pane. |
| Usage-limit text (C5) | Cursor's own line, `Error: Weekly usage limit reached. It resets in 1 day.`, as reported from cursor-agent 2026.10.01 (#631); taken from that report, not a live worker run, since eng workers never use Cursor. |
| Expected foreground process (C5) | `cursor-agent` as the pane command or a foreground process on its tty. The bundled Node launcher also qualifies only when the foreground argv starts with the resolved launcher's adjacent `node` and `index.js` absolute paths. Generic `node` alone is `ambiguous`. Run identity, dead and missing checks still apply. |
| Code-review skill | Gap: none declared, so a self-gate review on this harness uses the protocol §3 rubric alone. |
| Install pointer (C3) | Only the launch prompt points to `$CREW_BRIEF`; no discovery files or home config are edited. Gap: `mdstack bootstrap --harness cursor` is not implemented. Use rendered tmux briefs with `mdstack up` / `mdstack spawn`. |

This adapter supplies launch mechanics, not quota permission. The
[hard rules](../roles.md#hard-rules) still prohibit eng workers from using
Cursor and require owner permission for paid Claude/GPT models inside Cursor.
Default orders stay unchanged. Contributor-tier and free-credit providers
must never receive private repositories. Fake-binary tests exercise role
launches without consuming Cursor quota; no live agent turn was run.

Flags follow Cursor's [CLI parameters](https://cursor.com/docs/cli/reference/parameters)
and the installed `cursor-agent --help`. The shell-to-bundled-Node layout was
checked on Cursor Agent 2025.08.09; newer layouts without a recognized
foreground signature probe `ambiguous`.

## Muse (`muse`)

| Field | Muse |
|---|---|
| Launch line (C3) | Role: `muse --yolo --model <model> --reasoning-effort <effort> <pointer>`. Coordinator: `muse --yolo <pointer>`, retaining its configured model and effort. Select `engines.coordinator = "muse"` or a `muse/<model>` tier entry. Credentials use the existing Muse login or environment, never argv. |
| Trust and first-run dialogs (C5) | `--yolo` trusts the workspace and disables the CLI's approvals and sandbox for this process. Only `permission_mode = "bypass"` is supported; `auto` and `safe` are refused. Sign in once before dispatch. A remaining `Do you trust this workspace?` dialog ending in `Use Up/Down or 1/2, then Enter. Esc quits.`, or `Sign in at this page:` ending in `Esc cancel`, probes `ambiguous`. No dialog is answered automatically. |
| Turn-end and wake recipe (C1) | The watcher types `wake: watcher` into idle window 0; a role receives `inbox: <msg-id>` plus Enter. Gap: automatic turn-end guard integration is unimplemented; keep the watcher running. Live wake timing has not been exercised. |
| Idle detection (C1) | Expected Muse foreground process and no pane output for `--idle` seconds (default 30), using tmux's window activity time. This activity heuristic does not inspect Muse's session logs. |
| Busy and composer screen (C1) | Gap: none declared, so `mdstack upgrade` reads no mid-turn screen text from this pane (it still waits on a live child process and an unfinished status line), and `mdstack send` finds no composer glyph, so it cannot clear stale nudges or confirm a nudge was submitted. Declare `BUSY` and `COMPOSER` only from verified screen captures. |
| Transient-error text (C5) | Gap: none declared, so the watcher records no gateway errors from this harness's pane. |
| Usage-limit text (C5) | Gap: none declared, so a usage-limit screen on this harness's pane never probes quota and gets no next-engine restart. |
| Expected foreground process (C5) | `muse` or a versioned `muse-bin-<version>` foreground name, at startup, probe and watcher wake. Startup also accepts the resolved executable's basename. A generic `node` or unrelated process probes `ambiguous`; run identity, dead and missing checks remain required. |
| Code-review skill | Gap: none declared, so a self-gate review on this harness uses the protocol §3 rubric alone. |
| Install pointer (C3) | The positional launch prompt points to `$CREW_BRIEF`; no discovery or home files are written. Gap: `mdstack bootstrap --harness muse` is unimplemented. Use rendered tmux briefs with `mdstack up` / `mdstack spawn`. |

Muse is a contributor-tier harness: each launch reads repository visibility
through the configured GitHub repository API and refuses private repositories
or unreadable visibility, per the [contributor-tier rule](../roles.md#hard-rules).
This adapter changes no default tier order or pay-per-use permission.
Launch flags, dialog text and versioned process names follow the prior-art
Muse adapter's recorded CLI observations (Muse Code 0.1.0-R708.1).
Fake-binary tests exercise launches, probes and cleanup; a live Muse session
has not been exercised for mdstack.

## OpenCode (`opencode`)

A tier-order and pack-capability engine with no interactive launch: its
module declares no `role_argv`, so `mdstack spawn` skips it in a tier order and
it is not a coordinator choice. Its non-interactive review command is in
[roles.md](../roles.md). `mdstack doctor` checks `opencode --version`.

## Adding a harness

1. Add `harnesses/<engine>/adapter.py` with the [module](#adapter-modules)
   fields and its tests (fake binaries; see `dev/tests/harnesses/test-harness-adapters.py`).
   No consumer changes: spawn, coordinator start and wake, reload, doctor,
   remote readiness and, with `install_targets`, bootstrap pick it up.
2. Add its section on this page and fill in every field.
3. A field the harness cannot meet is a gap against the capability that
   field serves. Each binding offering the harness declares it in its
   contract table, in the [gap format](README.md#gap-declaration).
4. Engine policy still applies: tier orders, reviewer independence and the
   contributor-tier rule are profile and core decisions, not adapter ones.

The field list follows #160 row 13; the per-harness layout borrows the
pattern of [firstmate](https://github.com/kunchenguid/firstmate)'s harness
adapter docs (MIT license). No code or text is copied.
