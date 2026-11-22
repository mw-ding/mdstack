# Multi-device tmux crew (design)

> - **Status:** partly built
> - **Applies to:** a tmux primary plus forge-less runner hosts
> - **Current rules:** [tmux binding](tmux.md), [protocol](../protocol.md)
> - **Built:** host inventory, `mdstack host check`, `mdstack hosts`, `mdstack host prepare`, the remote call and runner, [Forge-less hosts](#forge-less-hosts-remote-test-runner) and its [runbook](#runbook-add-a-runner-host), the [role-host runbook](#runbook-add-or-remove-a-role-host), the [host OS adapter](#host-os-adapters) dispatch and the `macos` and `linux` adapters, [placement](#placement) in `mdstack spawn`, the [remote run lifecycle](#remote-run-lifecycle) (`spawn`, `kill`, `restart`, `down`), [remote attach and logs](#observability), [remote wakes and messages](#remote-wakes-and-messages) (`pull`, `send`, `host_scan_interval`), the owner's [`mdstack connect`](#connect-to-a-host) login, [partition handling](#failure-and-partition) (`unreachable`, reconcile, abandon with a tombstone), proved on fakes, and the pull through a disconnect and a placed run's partition on lab C (#204–#208, #345–#349, #726–#729, #1358, #1359, #1363), plus the two-host dry run on lab C as a simulated host (#209, #1442), and a declared [command checkout](#command-checkout) on the primary (#1723)
> - **Last checked:** 2026-11-12 at `8b6ebe4`

How one coordinator runs role sessions on several hosts (laptops, a
desktop, cloud VMs, a machine with a simulator or phone attached) joined by
a private overlay network (portable mdstack roadmap 20.1,
[#158](https://github.com/mw-ding/mdstack/issues/158); umbrella
[#110](https://github.com/mw-ding/mdstack/issues/110)). It extends the
[tmux binding](tmux.md); it is not a new binding. It carries out the
owner's [#160 row 6 decision](https://github.com/mw-ding/mdstack/issues/160#issuecomment-6531687881)
and does not re-decide it. It began as a design; a built part names its
script, and the build issues are under [Build issues](#build-issues).

This page adds no rule, gate, cap, marker field or label; the
[protocol](../protocol.md) still owns them, and GitHub stays the tool of
record (invariant I5). Every tmux mechanism not named here is unchanged.

## Decisions

Rows citing row 6 restate the owner's decision; the others are this
design's choices within it, including answers to #158's open questions
Q1–Q5.

| Question | Decision | Alternatives considered | Section |
|---|---|---|---|
| What goes on a host (row 6) | One role run: a worktree and a window | A whole home per host, as firstmate's secondmates do: splits the record and the merge lock (row 6) | [Placement](#placement) |
| Placement policy (#158 Q1; row 6) | Project affinity by default; capability exceptions from profile rules; least-loaded among eligible hosts | Static per role: leaves spare capacity idle. Load only: every host must be prepared for every project | [Placement](#placement) |
| Who places (row 6) | A pure function inside `mdstack spawn`; the coordinator only overrides, with a reason posted on the item | The coordinator choosing by judgment: not reproducible across turns, not testable | [Placement](#placement) |
| Separate binding or tmux capability (#158 Q5) | A capability of the tmux binding: same CLI, session layout and run records, plus a host per run | A `remote-tmux` binding: `runtime.name` picks one binding, but one crew mixes local and remote runs, and every C1–C8 mechanism would be duplicated | [Contract across hosts](#runtime-contract-across-hosts) |
| Engine auth and quota per host (#158 Q2) | Each host keeps its own logins; the profile lists them per host; the tier's engine order is walked first, then hosts. Quota routing stays manual ([roles](../roles.md#quota-routing)): steering around one host's exhausted subscription is a `--host` override or a profile edit | Host first: a warm host would override the owner's engine order (row 7). Shipping logins to hosts: breaks R1 and least privilege. Automatic per-host quota: row 7 defers quota headroom | [Placement](#placement), [Security](#security-model) |
| Merge lock (#158 Q3) | On the primary only. If the primary is gone, nothing lands (fail closed); moving the primary is a runtime handoff ([#157](https://github.com/mw-ding/mdstack/issues/157)) | Per-host locks: two lands at once. A lock on the tool of record: the backend interfaces offer no atomic lock, and #157's planned ownership marker says who may land | [Contract across hosts](#runtime-contract-across-hosts) |
| Security model (#158 Q4) | Credentials follow roles; the crew SSH key can run one fixed entrypoint only; no forwarding; no secret crosses the wire | Plain SSH with a shell: a leaked primary key is a shell on every host | [Security](#security-model) |
| Remote transport (row 6) | Hardened SSH call to a fixed entrypoint; a per-account runner on the host owns the runs | Runs as children of the SSH session: die with the link and may not see the account's logins. Detached `nohup`: survives, but has no supervisor and the same login gap | [Remote call](#remote-call-and-runner) |
| Wake across hosts | The primary pulls new status lines from each host by offset; hosts never call the primary | Hosts push to the primary: role hosts would need a credential for the primary. A long-lived stream: loses lines when the link drops | [Contract across hosts](#runtime-contract-across-hosts) |
| Unreachable host (row 6) | `unreachable` liveness class: never restarted, here or elsewhere; escalate; reconcile on return | Treat as `dead`: duplicate agents on one item. A fifth C5 class in the contract: deferred until a second runtime has remote runs | [Failure](#failure-and-partition) |
| Review file between passes on two hosts | The primary pulls the review pass's verdict file and hands it to the validate spawn | Pin validate to the review host: blocks a simulator-only validate. Post the review on GitHub first: changes how a verdict is posted | [Placement](#placement) |

## Terms

| Term | Meaning |
|---|---|
| Host | A machine in the profile's inventory, reached by its overlay network name |
| Primary | The one host that runs the coordinator (`ash`), the synthesizer (`sam`), `mdstack poll`, the watcher, the wake queue, claims and the land lock. It may also run role runs |
| Role host | Any other host. It runs builder and reviewer-validator runs only |
| Project mirror | A persistent clone of one repo on one host. Never a working checkout; every worktree on that host starts from it |
| Ready | `mdstack host check` passed for this (host, project) |
| Entrypoint | The one command the crew SSH key may run on a host |
| Runner | A per-account service on a host that starts and owns that host's role runs |

## Overlay network assumptions

| # | Assumption | Why | If not met |
|---|---|---|---|
| N1 | Every host joins one private overlay network (any WireGuard-style mesh, for example a Tailscale tailnet) | Hosts in different places reach each other with nothing exposed publicly | Not supported. No host or port is ever exposed publicly |
| N2 | The overlay gives each host a stable name that resolves on the primary | The profile names hosts, never addresses (spec R1) | `mdstack host check` fails *reachable* |
| N3 | Overlay access rules let the primary open SSH to role hosts; role hosts need no route to the primary or to each other | Commands flow one way; a compromised role host has no lateral path | Works with a wider blast radius; the runbook lists it as a human step |
| N4 | SSH on each host listens on the overlay only | Nothing public | Human step |
| N5 | Role hosts reach GitHub and the engine vendors over their own internet access | Runs fetch, push, post and call engines themselves; the overlay carries crew control traffic only | `mdstack host check` fails *project mirror* or *logins*. A host that cannot is a [forge-less host](#forge-less-hosts-remote-test-runner): runner jobs only |
| N6 | mdstack configures no overlay | Direction rule; no product names, keys or rules in mdstack or a profile | n/a |

## Host inventory (profile extension)

Proposal for [#204](https://github.com/mw-ding/mdstack/issues/204),
building on the [profile schema](../profile.md) (#122). All keys are
optional, so every existing profile stays valid; with no `[hosts]` table the
crew is today's single-machine tmux crew.

```toml
[runtime]
name = "tmux"
options = { builders = 5, reviewers = 2, host_scan_interval = 15 }

[hosts.host-a]
primary = true
capabilities = { os = "macos", arch = "arm64", engines = ["claude-code", "codex"] }
max_runs = 2

[hosts.host-b]
capabilities = { os = "linux", arch = "x86_64", engines = ["codex", "claude-code"] }
max_runs = 4
roles = ["builder", "reviewer"]

[hosts.host-c]
capabilities = { os = "macos", arch = "arm64", devices = ["ios-simulator"], engines = ["claude-code", "codex"] }
max_runs = 1
roles = ["reviewer"]

[placement]
hosts = ["host-b", "host-a"]

[[placement.rules]]
role = "reviewer"
pass = "validate"
paths = ["ios/**"]
needs = { devices = ["ios-simulator"] }
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `hosts.<name>` | table; `<name>` is a DNS label (`[a-z0-9-]`, 1–63 characters) | none | The host's overlay name, also its SSH destination unless `address` is set; user, port and key come from the primary's SSH config, by mechanism |
| `hosts.<name>.address` | string: a dotted DNS name (`[a-z0-9-]` labels, no IP literal, `user@` or `:port`) | the label | The SSH destination when the label is not reachable by itself, such as `host-a.region.example.com`; the label stays the key everywhere else (#1034) |
| `hosts.<name>.primary` | boolean | `false` | Exactly one host is `true` |
| `hosts.<name>.capabilities.os` | `linux` or `macos` | *required* | Checked against the host by `mdstack host check` |
| `hosts.<name>.capabilities.arch` | `x86_64` or `arm64` | *required* | Same |
| `hosts.<name>.capabilities.devices` | list from `ios-simulator`, `ios-device`, `android-emulator`, `android-device` | `[]` | Attached devices; a new kind is a schema change |
| `hosts.<name>.capabilities.engines` | non-empty list of `<engine>` ([profile](../profile.md#engines)) | *required* | Engines logged in on that host |
| `hosts.<name>.max_runs` | integer ≥ 1 | *required* | This crew's concurrent role runs on that host, on top of the band caps |
| `hosts.<name>.roles` | list from `builder`, `reviewer` | both | Roles placed there; the primary also runs the coordinator and synthesizer |
| `hosts.<name>.root` | string: path on that host | `~/.mdstack` | Mirrors, worktrees and host state; ignored on the primary, which uses [`[paths]`](../profile.md#paths) |
| `hosts.<name>.toolchain_bin` | string: path on that host | none | `<toolchain-bin>` for builders there |
| `hosts.<name>.connect` | `{ alias?, transport?, proxy?, options? }` | `ssh`, no alias | The owner's [`mdstack connect`](#connect-to-a-host) login; not crew traffic ([profile](../profile.md#hostsname-and-placement)) |
| `placement.hosts` | non-empty list of host names, preferred first | the primary | Project affinity |
| `placement.rules` | array of `{ role, pass?, paths?, needs }` | `[]` | Capability exceptions; first match wins; `needs` takes `os`, `arch`, `devices` |
| `runtime.options.host_scan_interval` | integer ≥ 1 (seconds) | `15` | How often the watcher pulls each role host |

`validate` also fails on: an IP literal, `@` or `:` in a host name; zero or
several primaries; `placement` without `hosts`; a `placement.hosts` entry
that names no host; a role host listing a coordinator or synthesizer role;
a role (`builder`, `reviewer`) that no `placement.hosts` host takes; a rule
whose `needs` no host taking that role can meet; `[hosts]` with a runtime
other than `tmux`; and the existing secret-pattern and unknown-key checks.

**Where it lives.** Host names are not secrets, but they are environment
facts. Keep `[hosts]` and `[placement]` in the project `config.toml`, which is
already host-local (it holds absolute paths), or in the org / environment
layer shared by several projects; never in mdstack. `resolve` merges
`hosts` tables by key like any table ([layers](../profile.md#layers-and-precedence)).
One coordinator still runs one repo, so `max_runs` is this crew's budget on
a host; another crew on the same host has its own.

## Placement

`mdstack spawn` gathers facts, then calls a pure function, tested offline on
fixtures like `mdstack poll`'s decision function (#134):

```text
place(request, profile, facts) -> (host, engine) | queue(reason) | refuse(reason)
```

- **request:** role, pass, item, tier, the PR's changed paths (none for a
  build), engines to skip (reviewer diversity, invariant I2), and an
  optional override.
- **facts:** per host, ready for this project (which includes its engine
  logins, check 6), reachable, and this crew's live runs there (from the
  primary's run records).

Steps:

1. No `[hosts]`: return the primary, today's behaviour.
2. Coordinator and synthesizer: always the primary (C7).
3. Needs: the `needs` of the first rule matching role, pass and, when
   given, a changed-path glob. No match: no needs.
4. Candidates: no needs, the `placement.hosts` list in order; with needs,
   every host whose capabilities hold them all, affinity hosts first in
   their order, then the rest by name. Drop hosts whose `roles` exclude the
   role.
5. Engine: the first engine of the tier's order, minus skipped engines,
   that some candidate lists. It depends on the profile and the request
   only, never on load, so the engine order stays deterministic (row 7). No
   such engine, or no candidate: refuse with a `blocked:` line, which the
   coordinator escalates.
6. Host: among candidates listing that engine that are ready, reachable and
   below `max_runs`, the lowest ratio of live runs to `max_runs`; ties go by
   candidate order.
7. None: queue in `spawn-queue.jsonl` with one reason per host
   (`host-b: at cap 4/4; host-c: unreachable`). `mdstack dequeue` retries when
   a run closes and when a host turns ready or reachable.

The band caps ([Q6](tmux.md#q6-concurrency)) are checked before placement,
as today.

**Override.** `mdstack spawn ... --host <h> --reason "<why>"` replaces steps 4
to 6 with `<h>` and the first engine in order that `<h>` lists. It still
refuses a host that lacks a need, excludes the role, is not ready, is
unreachable, is at cap or lists no eligible engine, and it never moves the
coordinator or synthesizer. Before the spawn it posts the reason on the
item (a narrative post on the PR, else an issue comment), as
`mdstack kill --discard` does; if the post fails, nothing is spawned.

**Later passes.** A builder's fix rounds reuse its window, so they stay on
its host. A clean restart re-runs placement; an in-place restart (unlanded
work, [mdstack restart](tmux.md#mdstack-restart)) stays where the worktree is. A
validate pass may land on another host than its review pass: on the review
pass's `done:` line the primary pulls its verdict file, and the validate
spawn carries it to the validate host.

**Record.** The run record gains `host`, `placement` (`local`, `affinity`,
`capability` or `override` with the post link) and the per-host rejection
reasons. A default placement is a computed fact and stays local; an
override is a decision, so it is on the tool of record.

## Host readiness

`mdstack host check <host> [--project <config.toml>] [--fix]` has the shape
of `mdstack doctor` ([#190](https://github.com/mw-ding/mdstack/issues/190)):
read-only by default, `--fix` repairs what it can and lists the steps only a
person can take, exit 1 on any `fail`.

| # | Check | Read-only probe | `--fix` | Human step |
|---|---|---|---|---|
| 1 | Reachable | The entrypoint's `version` verb answers in time | none | Join the overlay; fix the SSH config or host key |
| 2 | Version | The host's mdstack version equals the primary's; with `[install]`, a `toolkit` row: the project's pinned toolkit matches the primary's install record and every file hash ([host toolkit](../bootstrap.md#host-toolkit)) | `mdstack host prepare` installs the pinned toolkit (with `[install]`) | Install the pinned version on the host (bootstrap, [#144](https://github.com/mw-ding/mdstack/issues/144)) |
| 3 | Runner | The runner service is up | Install or restart the user-level runner | none |
| 4 | Host doctor | The host's own `mdstack doctor` checks (tools, Python, tmux, state root) | Its `--fix` | Its human steps |
| 5 | Capabilities | Declared `os` and `arch` match; each device is present (device adapter TBD: `unverified` until one exists, as in [verification](../verification.md)) | none | Correct the profile |
| 6 | Logins | `gh` holds each identity of the host's roles; each listed engine is logged in (harness adapter, [#177](https://github.com/mw-ding/mdstack/issues/177)) | none: never changes auth | Log in on the host |
| 7 | Project mirror | The mirror exists, fetches, and has the default branch; builders' toolchain path exists | `mdstack host prepare` | Give the host's identity repo access |
| 8 | Capacity | Free disk under `root` above a floor; live runs against `max_runs` | none | Free disk |

The result is kept on the primary per (host, project) with its time.
`mdstack spawn` re-runs checks 1–3 (one cheap call) before it places a run
there.

`mdstack host prepare <host> [--project <config.toml>]` creates the project
mirror with the host's own `gh` login, or fetches an existing one, creates
the host's worktree and state directories, then runs `mdstack host check`. It
is idempotent; a failed step leaves the host not ready and names the step
(`fail prepare <step>`). On the primary it fetches the project checkout. On
a [forge-less host](#forge-less-hosts-remote-test-runner) it fetches the
primary's checkout and seeds a full bundle of the default branch (`seed`).
With an `[install]` table, both calls also carry the primary's toolkit pin,
and the host installs that release under `toolkit/`; `--prune` removes the
toolkit versions no project on the host pins
([host toolkit](../bootstrap.md#host-toolkit)).

### Command checkout

A host whose project checkout is made by its own VCS's clone command (no git
mirror, no bundle), such as a virtual-filesystem checkout of a large
monorepo, sets `hosts.<name>.checkout = "command"`
([profile](../profile.md)). The command is declared on the host, never sent
over SSH: `<root>/checkout/<owner>__<repo>.json` holds
`{"argv": [...], "path": "..."}`, `path` relative to `root` or absolute.
`mdstack host prepare` then sends `prepare` with `checkout=command`, forge-less
or not; the host runs `argv` with no shell, from `root`, and requires a zero
exit and `path` to exist, else `fail prepare checkout`. It records
`state/<owner>__<repo>/checkout.json` and makes the worktree and state
directories and the toolkit install as for a mirror. `mdstack host check`
then requires a `project checkout` row in place of `project mirror`: `ok`
once the command has run and its declared path exists. Run worktrees and
runner jobs on such a host still need a mirror (follow-up).

The primary may set it too, for a primary on a non-git checkout (#1723).
Its declaration lives under its own `root` (default `~/.mdstack`), and
`mdstack host prepare <primary>` runs it locally with the same checks and
receipt, in place of the git fetch. `mdstack host check <primary>` reads the
receipt and never runs the command: `ok project checkout` replaces the
`project mirror` row only when the command has run, its path exists and is
the profile's project checkout (`paths.checkout`, else the profile's
directory). Doctor and engine-login rows still gate ready as for a git
primary.

### Working-copy claims

Project ownership keeps two crews off each other's projects, not off each
other's working copies. When more than one crew can place runs on a host
(one owner's standing and ad-hoc crews, say), every run claims its working
copy host-wide before it starts there (#391):

- **Store and key.** One directory per host user, shared by every crew and
  state root on that host: `~/.mdstack/copy-claims/`. A claim is keyed by the
  copy's real path, so a symlink, `..` or a trailing slash name one claim.
- **Record.** Host, path, crew (the holder's state root), run, item and the
  time it was taken. It is published complete with an atomic hard link, so
  of two concurrent claims exactly one wins.
- **Acquire before launch.** `mdstack spawn` claims a fresh worktree before
  it adds it, and a role host's `spawn` verb does the same under `root`; a
  claim held by another crew or run refuses the spawn before any worktree or
  window, and a refused or failed launch releases its own claim. A
  coordinator dispatching into an existing copy (a hand-dispatched pack run,
  a [command checkout](#command-checkout)) runs
  `mdstack copy-claim acquire --path <copy> --run <id> --item <item>` first
  and does not dispatch on exit 1, which names the holder.
- **Release by the holder only.** `mdstack kill` (the host's `kill` verb on a
  role host) releases the claim once it removes the run; kept unlanded work
  keeps the claim. A hand-dispatched run's coordinator runs
  `mdstack copy-claim release` after its cleanup. Another crew's release is
  refused.
- **No reclamation by age.** No age, liveness guess or other crew reclaims a
  claim. A claim left by a crew that is gone is removed by hand on the
  owner's decision (`mdstack copy-claim show --path <copy>` names it).

`mdstack hosts [--project <config.toml>]` prints one row per host: name,
primary, OS and arch, devices, engines, roles, ready projects, reachability
(`reachable`, or `unreachable` since a time) and load (this crew's runs
against `max_runs`, and the host's total from its runner).

Host-side layout under `root`:

| Path | Holds |
|---|---|
| `mirrors/<owner>__<repo>.git` | Project mirror |
| `checkout/<owner>__<repo>.json` | A [command checkout](#command-checkout)'s declared `argv` and `path`, written by the host's operator |
| `wt/<n>-<sha7>-<role>-<pass>/` | Run worktrees ([C6](README.md#c6-isolation)) |
| `~/.mdstack/copy-claims/` | Host-wide [working-copy claims](#working-copy-claims), outside `root` so every crew on the host shares them |
| `state/<owner>__<repo>/` | `status/`, `inbox/` and `verdicts/` of the runs on this host, their run identity and brief, and the runner's request results |
| `requests/<request-id>.json` | The first reply to each mutating call, replayed on a retry |
| `runner.json` | The runner's heartbeat: pid, time, interval and its tmux session |

## Remote call and runner

Contract for [#208](https://github.com/mw-ding/mdstack/issues/208)
(firstmate's remote transport, as contracts only):

| Property | Contract |
|---|---|
| Transport | SSH over the overlay to the host's profile name. Never prompts (batch mode); strict host-key checking, so a changed key fails and is never auto-accepted |
| Forwarding | None: no agent, X11, TCP or stream forwarding, and no environment sent |
| Dead peer | Bounded connect timeout and keepalive, so a dead link fails in under a minute instead of hanging |
| Entrypoint | The crew key's `authorized_keys` line forces one command and restricts everything else (a TTY only for `attach`). Arguments arrive as one encoded payload, decoded and checked against the verb's schema; never a shell string, never evaluated |
| Verbs | Closed set: `version`, `check`, `prepare`, `spawn`, `probe`, `pull`, `send`, `kill`, `logs`, `capture`, `attach`, plus `seed`, `job` and `result` for [forge-less hosts](#forge-less-hosts-remote-test-runner). Anything else is refused |
| Paths | Every path stays under the host's `root`; `..` and absolute paths elsewhere are refused |
| Idempotency | Mutating verbs carry a request id; a retry with the same id returns the first result, so a retried `spawn` never opens a second window |
| Results | Structured: `ok`, `refused: <reason>` or `failed: <error>`. Only a transport failure, seen by the client, can yield `unreachable` |
| Version | The entrypoint refuses a call from a different mdstack version: no silent skew after an upgrade |
| One primary per run | The runner tags each run with the primary that spawned it and refuses lifecycle verbs on it from any other primary, so two coordinators never drive one run |
| Runner | A user-level service of the host account (for example a launchd agent or a systemd user unit), never root. It owns the host's crew tmux server, so runs outlive the SSH session and the client, and they start in the account's own session, where some harnesses keep their logins |
| Probe | `probe` and `pull` read tmux and `ps` directly, so liveness still answers while the runner is down; `spawn` needs the runner |

Built in `environments/terminal/remote/crew-remote.py` (#208): the entrypoint, the runner and the
primary-side client `call()`. The crew key's `authorized_keys` line is
`command="python3 <bundle>/environments/terminal/remote/crew-remote.py --root <root>",restrict,pty <key>`,
and the runner runs `crew-remote.py --root <root> runner` as the account's
service. The runner makes the default tmux socket's directory itself: tmux
does not make it for a socket named by path, and still exits 0. Built verbs: `version`, `check`, `prepare`, `seed`, `job`,
`result`, `spawn`, `probe` and `kill` ([remote run lifecycle](#remote-run-lifecycle)), and
`attach`, `capture` and `logs` ([observability](#observability)), and `pull` and
`send` ([remote wakes and messages](#remote-wakes-and-messages)).
`version` reports the host's version and whether the runner is `up` (a
fresh heartbeat and its tmux session) or `down`. Every other verb in the set
is refused as not built until its issue lands.

The client keeps the primary's SSH config for auth only. It resolves the
host with `ssh -G` and keeps the host name, user, port, identity and
certificate files, identity agent, known-hosts files and host-key alias.
It then calls with `-F none` plus those settings and the hardened options,
so no `SendEnv`, `SetEnv`, forwarding, proxy or other option from the user
or system config reaches the call. `ProxyJump` and `ProxyCommand` are
dropped too: the overlay routes to each host directly. The entrypoint reads
no environment but `SSH_ORIGINAL_COMMAND`.

### Failure semantics

Every call ends in exactly one of four results. The first three come from
the entrypoint; only the client can produce the fourth.

| Result | When | Caller does | Never |
|---|---|---|---|
| `ok` | The verb ran | Uses the reply | |
| `refused: <reason>` | The entrypoint declined before acting: unknown or not-built verb, version skew, an SSH command other than `crew-host`, a `root` or path outside the host's root, a mutating verb without a request id | Treats the host as not ready for that call and reports the reason; the fix is a human or profile step (upgrade, host key, profile) | Retry unchanged, or count it toward `unreachable` |
| `failed: <error>` | The verb raised, or the reply was not a structured result (non-zero entrypoint exit, bad JSON) | Reports it; a mutating verb may retry with the same request id, which replays the first reply instead of acting twice | Count it toward `unreachable` |
| `unreachable` | Transport only: `ssh` exits 255 (no route, refused, changed host key), the 10 s connect timeout or the 10 s keepalive fails, the call outlives its timeout, or `ssh` cannot start | Counts toward the 3-calls-in-a-row rule ([Failure](#failure-and-partition)); retries a mutating verb with the request id the result carries | Restart or re-place the run; treat a late reply as fresh |

Runs live under the runner's tmux session, never under the SSH session, so
a dropped link ends only the call: the run keeps going, and the next call
sees it. A runner that is down leaves `version` and the read-only verbs
answering; only verbs that start runs need it.

### Remote run lifecycle

Built in #345 (`crew-remote.py` verbs, `environments/terminal/crew.d/_remote.py`
on the primary), proved on fakes; the lab C and V runs are separate
evidence.

| Command | On the primary | On the host |
|---|---|---|
| `mdstack spawn` placed on a role host | Renders the brief as for a local run, its Worktree line naming the host's path, and keeps the run record (`remote`, `host`), claim and brief copy. A validate pass sends the PR's retained `-review.md` files at that head | `spawn` needs the runner up. It fetches the run's ref into the mirror without moving any mirror ref and refuses unless it is the given head (no stale base), adds the detached worktree `wt/<n>-<sha7>-<role>-<pass>`, writes the brief and review files under `state/<owner>__<repo>/`, then starts the engine's harness in a window of the runner's tmux session named `<owner>__<repo>/<window>`, so projects sharing a host never collide, with the argv built on the host from checked fields. The run record there keeps the pane identity and the spawning primary |
| `mdstack kill` | Posts a `--discard` reason first, as for a local run, then removes its own record, claim and brief copy | `kill` stops the window, then runs the unlanded-work check (uncommitted paths, and commits on none of the default branch, the worktree's branch on origin or the run's PR heads). Unlanded work keeps the worktree and lists it; only `discard` removes it anyway |
| `mdstack restart` | Asks the host's `probe` (`unreachable` refuses, as `ambiguous` does) | `kill` without discard: unlanded work relaunches in its own worktree (`spawn` with `relaunch`, the brief sent again); a clean worktree is removed, and the primary spawns again, so placement re-runs |
| `mdstack down` | Stops every remote run through `kill`, even when the primary's session is gone; `--preserve` sends `keep` (stop only) | A run the host cannot stop or clear (unlanded work, unreachable) keeps its records, and `down` exits 1 naming it |

A run on another primary is refused by `spawn`, `probe` and `kill` (one
primary per run), and `kill` touches no window without its project's run
record. A run on a role host counts toward its role's pool cap,
reads `ambiguous` to the local probe (never restarted from here) and shows
its host's probe in `mdstack status`. Its status lines, wakes and
`mdstack send` are [below](#remote-wakes-and-messages); the watcher still
queues no liveness wake for it. Attach and logs are built
([observability](#observability), #348), and so is [partition
handling](#failure-and-partition) (#347). The window gets no `CREW_PROJECT` there, so
the brief's `mdstack ownership` and `action heartbeat` steps do not run
there yet (a follow-up). Worktrees
come from a `--mirror` clone, so they have no `refs/remotes/origin/*`; spawn
turns `remote.origin.mirror` off so a run can push a refspec.

### Remote wakes and messages

Built in #346 (`pull` and `send` in `crew-remote.py`, `pull` and `send` in
`crew.d/_remote.py`), proved on fakes and, for the pull through a network
disconnect and a send's ack, on lab C (the `status-pull`
[lab scenario](../campaign-harness.md#lab-runner-scenarios)).

| Piece | Behaviour |
|---|---|
| `pull` (host, read-only) | For each named run of the calling primary, the complete status lines past the primary's offset (at most 256 KiB a call; the rest on the next pull), the file's size and the run's probe. The primary sends its mirror's size as the offset and the mirror's SHA-256; a digest that is not the host file's prefix (a rewritten, shorter or torn file) answers from offset 0 |
| Status mirror (primary) | `status/<window>.status` is a byte copy of the host's file. Its own size is the offset, so an interrupted, repeated or concurrent pull and a primary restart neither lose nor double a line; a pull answered from 0 replaces the mirror, a removed mirror is rebuilt, and an empty or missing host file leaves it as it is. `status/.pull.lock` serializes pulls, so the watcher and `mdstack acked` never append the same lines twice |
| `mdstack watch` | Every `host_scan_interval` (default 15 s), one `pull` per role host with runs, before the scan; pulled lines wake as local status lines do. A missing mirror keeps the scan's offsets until the next pull rebuilds it. Each host's last result, time and run probes are kept under `pulls` in `wake/watch-state.json`. One attempt per scan: the next scan is the retry |
| `mdstack send` | A run on a role host gets the refs-only message through `send`, retried with its request id while unreachable: the host appends it to its `inbox/<window>.jsonl` and types the fixed nudge into the run's window, confirming the submit as on the primary (no key into a dialog; Enter retried only). An unreachable host fails after the bounded call (exit 1), never queued; a nudge not submitted exits 4 |
| `mdstack acked`, `send --wait-ack` | Pull the run's status lines into the mirror before each check, then read `ack: <msg-id>` from the mirror |

### Host OS adapters

Owner, 2026-11-07 ([#1281](https://github.com/mw-ding/mdstack/issues/1281)
decision 2): the host side is OS-neutral, and `macos` and `linux` are
adapters. The dispatch, `macos` and `linux` are built in
`environments/terminal/remote/hostos/` (#1358 and #1359, lab items D and
E, proved on fakes); no verb calls their install, start, stop or
uninstall yet. The entrypoint picks the
adapter from its own `uname -s` and reports it in `version` and `check`;
`mdstack host check` and `mdstack host prepare` compare it with
`hosts.<name>.capabilities.os`, and a mismatch fails check 5. An adapter
adds no verb: it backs `check`, `prepare`, `probe` and the runbook steps.

| Operation | Contract | `macos` | `linux` | `linux` supervised |
|---|---|---|---|---|
| Install | Defines the runner (`crew-remote.py --root <root> runner`) as a service of the runner account that restarts on exit; never root; idempotent; names the file it wrote | A launchd agent in `~/Library/LaunchAgents/` with `KeepAlive` and `RunAtLoad`, bootstrapped into the account's `gui/<uid>` domain | A systemd user unit in `~/.config/systemd/user/` with `Restart=always`, enabled with `systemctl --user` | Writes nothing: `n/a: supervised`. The container's PID-1 supervisor owns the runner |
| Start, stop | Act on that service only, never on another account's or a system service | `launchctl kickstart`, `launchctl bootout` | `systemctl --user start`, `stop` | `refused: supervised` |
| Status | `up` still means a fresh `runner.json` heartbeat and its tmux session; the service manager's state is reported beside it and never counts as `up` alone | `launchctl print` | `systemctl --user is-active`, plus `Linger=yes` from `loginctl show-user` (else `warn`: the runner stops at logout) | Heartbeat only |
| Uninstall | Stops and removes the definition (runbook **Remove a host**) | `bootout`, delete the plist | `disable --now`, delete the unit | `n/a` |
| Process start time | One value in whole epoch seconds on the host's own clock, for C5's pane pid and start-time compare; a missing pid reads `missing` | `ps -o lstart= -p <pid>` under `LC_ALL=C` | `/proc/<pid>/stat` start ticks plus boot time, else `ps -o lstart=` | As `linux` |
| SSH listener (N4) | Read-only, as the runner account, which cannot see root's `sshd` by process: lists the TCP listeners on the SSH port the client resolved with `ssh -G` and sent in the call; `warn` on a wildcard or a non-private address. Never `fail` or `--fix`: N4 stays a human step | `netstat -an -p tcp` | `ss -Hltn` | As `linux`; the run's port publishing is checked by the lab, not the host |
| Key line | Read-only. The crew key's `authorized_keys` line forces the entrypoint and carries `restrict` (plus `pty` only as [attach](#remote-acceptance-criteria-and-the-local-lab) allows); `warn` otherwise | Same | Same | Same |
| Prerequisites | `python3` 3.11 or later, `git`, `tmux` and the service tool on the runner account's `PATH`, as check 4 | `launchctl` | `systemctl --user`, `loginctl` | A supervisor, named in the image spec |
| Engine logins | Presence only, by the read-only status commands in [Login locations](#login-locations); never read, copied or moved ([#1281](https://github.com/mw-ding/mdstack/issues/1281) decision 5) | The runner runs in the account's `gui/<uid>` domain, so a login in the login keychain stays readable to its harness | Files under the home, or the Secret Service keyring when one runs | Synthetic logins in lab runs |

#### Login locations

Check 6 runs each harness's own read-only status command as the runner
account, in the runner's session, and reads only its exit and logged-in
state. mdstack never opens a credential file or keychain item, never puts a
token in argv, a reply or a log, and never moves one between hosts. The
locations below tell the owner where a host's login lives (the human step)
and which session can see it.

| Login | Status command | macOS | Linux |
|---|---|---|---|
| Claude Code | `claude auth status` | The login keychain (`Claude Code-credentials`), settings in `~/.claude/` | `~/.claude/.credentials.json`; `CLAUDE_CONFIG_DIR` moves the directory |
| Codex | `codex login status` | `$CODEX_HOME/auth.json` (default `~/.codex/`), or the keychain when its `cli_auth_credentials_store` says so | Same file, or the Secret Service keyring by the same setting |
| GitHub (`gh`) | `gh auth status` | The keychain, with `~/.config/gh/hosts.yml` naming the account; `GH_CONFIG_DIR` moves it | The Secret Service keyring when one runs, else the token in `hosts.yml` |
| Other harnesses | The adapter's `LOGIN_STATUS` ([harness adapters](harness-adapters.md)) | Not specified: a gap until a host runs that harness | Same |

A keychain or keyring login needs the account's own session: a launchd
agent outside `gui/<uid>`, or a container or headless Linux host without a
Secret Service, sees no login, so check 6 fails there. The fix is the runner's domain on
macOS, or a file-backed store where the harness offers one (Codex, `gh`).

The supervised fallback is for containers without systemd. It is chosen
by the image, never by a missing systemd: the lab `Dockerfile` writes the
root-owned `/etc/mdstack/supervised` naming its supervisor, and only that
file selects the `linux` supervised column. A Linux host with neither
systemd nor that file reports `no user manager` beside the heartbeat. On a
systemd host, `check` adds a `linger` row, `warn` while `Linger` is off.
The fallback proves the runner and entrypoint, not systemd: a real user
unit with lingering needs a systemd-capable Linux host or VM.

## Runtime contract across hosts

How each [capability](README.md#contract) holds when a run is on a role
host. Runs on the primary use the [tmux table](tmux.md#runtime-contract)
unchanged. Gaps use the [gap format](README.md#gap-declaration).

| Capability | Across hosts | Gap |
|---|---|---|
| C1 Wake on event | Every `host_scan_interval` the watcher makes one `pull` per role host with a run: new status lines since each mirror's offset (its size, checked by a prefix digest), plus probe results kept in `wake/watch-state.json`. It appends the lines to the primary's `status/<window>.status` mirror and wakes as for a local line. `mdstack poll` stays on the primary | C1 wake on event: partial, compensated by offset-based pulls that resume losslessly and the §6 step 3 sweep after a host returns; residual risk: wakes from an unreachable host wait until it returns or the owner abandons its runs, and remote wakes lag by up to one scan interval |
| C2 One consumer per event | Unchanged: one `mdstack poll` on the primary decides every consumer; role hosts never read GitHub events. Runs there still fetch, push and post to GitHub themselves | None |
| C3 Messages by reference, proof of delivery | `mdstack send` calls `send`: the host appends the refs to its `inbox/<window>.jsonl` and types the fixed nudge locally. Proof is still `ack: <msg-id>`, read from the mirrored status file. An unreachable host makes `mdstack send` fail after the bounded timeout (exit 1), never queue silently; the coordinator then probes | None |
| C4 Status protocol | Runs append to the host's status file; the mirror on the primary is a cache rebuilt by pulling from offset 0. The coordinator reads only primary files | None |
| C5 Liveness | `probe` runs the [Q7](tmux.md#q7-failure) probe on the host, comparing pane id, pane pid and start time on that host's own clock, so clock skew between hosts cannot fake `alive`. Calls failing for 3 scans in a row make the run `unreachable`, a binding class ([Failure](#failure-and-partition)); under C5 it takes `ambiguous`'s action (never restart) and adds: never re-placed | None |
| C6 Isolation | `spawn` fetches the host's project mirror (a failed fetch refuses: no stale base) and creates the worktree from it, with tmux's refusals (the mirror, a branch-named path, an existing path). `kill` runs the unlanded-work check on the host ([mdstack kill](tmux.md#mdstack-kill)) and removes only that run's worktree; never the mirror | None |
| C7 Serial land | The synthesizer and `locks/merge.lock` stay on the primary; no host has a lock. Primary gone: no land until it returns or a #157 handoff moves the crew | None |
| C8 Owner channel and SLA | Unchanged: the coordinator's terminal on the primary plus the GitHub post. Remote asks arrive as mirrored `blocked:` lines | As [tmux](tmux.md#runtime-contract) (unchanged); asks from an unreachable host fall under C1's residual risk |
| C9 Ownership handoff | The ownership record is on GitHub, so the guard is unchanged: `mdstack poll` on the primary reads it each tick, and a run on a role host runs `mdstack ownership` itself before each push and post (it never lands). Moving the primary is a handoff between two tmux instances ([handoff](../handoff.md#terms)); the runner's one-primary-per-run rule keeps the incoming primary off the outgoing runs. Prompt stop: `mdstack handoff stopped` on the outgoing primary runs `mdstack down`, which stops remote runs through `kill` and keeps their worktrees on their hosts; `stopped` names each kept worktree with its host, and the manifest's runs carry the host | C9 ownership handoff: partial, compensated by each run's own guard (read-only once the record moves) and the owner's abandon on the item ([Failure](#failure-and-partition)); residual risk: a run on an unreachable host cannot be stopped, so `mdstack down` exits 1 naming it and `stopped` is not posted until the host returns or the owner abandons the run; kept worktrees stay on their role hosts |

## Failure and partition

| Case | Detection | Action | Never |
|---|---|---|---|
| Host drops off (link, sleep, power) | Calls to it fail for 3 scans in a row | Its runs become `unreachable`; claims stay; placement skips the host; queued work waits with the reason. After the watcher's `--stale` time, one `escalate` wake per outage: the coordinator escalates on the item and the owner channel ([§5](../protocol.md#5-rounds-and-escalation)) | Restart or re-place the runs |
| Host returns | A call succeeds | Reconcile each run: probe, pull missed lines from the stored offsets, re-read GitHub (§6 step 1). `alive` continues; `dead` or `missing` follows tmux's restart rules on that host | Assume progress from memory |
| Host rebooted | Reachable; probe finds other handles or start times | `missing`; restart once ([Q7](tmux.md#q7-failure)), in place if work is unlanded | Treat a new same-named window as the run |
| Runner down | `spawn` refused, `probe` still answers | Host not ready; `mdstack host check --fix` restarts the runner; live runs keep going | Count it as `unreachable` |
| Partition, both sides alive | Primary cannot reach the host; the run still reaches GitHub | GitHub stays the truth: `mdstack poll` still sees its pushes and markers and routes them. No duplicate starts, since the claim stays | Force-push: two writers cannot silently overwrite a branch |
| Owner abandons a host | The owner's decision on the item | On an `unreachable` run, `mdstack kill <window> --discard --reason "<why>"` posts the reason, drops the run record and claim on the primary (the window cannot be reached) and writes a tombstone; placement may then start a fresh run. On return, reconcile stops the tombstoned run and keeps its worktree for the unlanded-work check | Delete unlanded work |
| Primary down | No scans, wakes or lands | Role runs continue and write status locally; `mdstack up` reconciles every host from offsets, run records and GitHub | Land from a role host |
| Version skew, changed host key | Entrypoint refuses; host-key check fails | Host not ready; human step in `mdstack host check` | Auto-update or auto-accept |

`mdstack down` stops remote runs through `kill`. A run on an unreachable host
keeps its records, and `mdstack down` exits 1 naming it, as it does for
unlanded work.

Built in #347 (`pull_hosts` in `crew.d/watch.py`, the outage and tombstone
helpers in `crew.d/_remote.py`, `kill_run` in `crew.d/_shared.py`), proved
on fakes and on lab C (the `partition`
[lab scenario](../campaign-harness.md#lab-runner-scenarios), a run placed by
`mdstack spawn`):

| Piece | Behaviour |
|---|---|
| Outage | Only an `unreachable` pull counts; `refused` and `failed` reset the count but leave a reached outage's reconcile pending. The watcher keeps each host's `fails`, `since` and `escalated` under `pulls` in `wake/watch-state.json`; at 3 the host's runs are `unreachable` and `mdstack status` reads `unreachable since <time>` |
| Escalate | One `unreachable` wake (`action: escalate`) per outage, once it is older than the watcher's `--stale`. It names the host and runs; nothing restarts or re-places them, and their claims stay |
| Reconcile | The first `ok` pull after the outage (a `refused` or `failed` reply carries no probes, so it waits) queues a `reconcile` wake naming each run's probe, so the coordinator re-reads GitHub (§6 step 1). The pull itself brought the missed lines from the mirror's offset. Each run found `dead` or `missing` also gets the local `stale` wake (`action: restart`, or `escalate` after one restart), so `mdstack restart` runs on that host |
| Abandon | `mdstack kill <window> --discard --reason "<why>"` whose host call is `unreachable` posts the reason, writes `tombstones/<window>.json` (host, reason, time and the run record) and drops the run record, claim, brief and mirror on the primary |
| Tombstone | Each host scan tries a tombstoned run's `kill` once (not while its host is in an outage). A clean worktree goes with the tombstone; unlanded work stays on the host, and the tombstone is kept, marked `stopped` with the host's list. Either way a `reconcile` wake says which |

## Security model

| Asset | Lives on | Used for | Never |
|---|---|---|---|
| Overlay membership | Each host's overlay client | The network | In mdstack, a profile or a brief |
| Crew SSH client key | The primary only, by mechanism (agent or key file) | The remote call | On a role host, forwarded, or in a profile |
| Its public half | Each role host's `authorized_keys`, forced to the entrypoint | Entrypoint verbs | A shell |
| Host keys | The primary's known-hosts | Host authentication | Accepted on change without the owner |
| GitHub login | Each host, for the identities of its `roles` only | `GH_TOKEN` derived in the window at launch ([Q5](tmux.md#q5-identities)) | Sent over SSH, put in argv, or written to disk by mdstack |
| Engine logins | Each host, for the engines it lists | Harness launch | Copied between hosts |
| Repo contents | Mirrors and worktrees | Runs | On a host the owner does not control |

Rules:

- **Credentials follow roles.** A host holds only the logins its `roles`
  need. A reviewer-only host in a profile with a separate reviewer identity
  holds no credential that can push (#158 Q4). A single-identity profile
  ([#111](https://github.com/mw-ding/mdstack/issues/111)) cannot split
  privilege by token; that residual risk is the same as on one machine.
- Remote reviewer runs keep the single-host engine sandbox
  ([mdstack spawn](tmux.md#mdstack-spawn)); being remote adds no write path.
- **Blast radius.** A stolen primary key drives the closed verb set on each
  role host, not a shell. A compromised role host exposes its own logins
  and repos only; it has no route or key to the primary (N3).
- Only hosts the owner controls join; shared or multi-tenant hosts are out
  of scope.

## Observability

| Command | Across hosts |
|---|---|
| `mdstack status` | Adds a `host` column; liveness may read `unreachable since <time>`; remote rows show the age of the last pull |
| `mdstack attach <window>\|<role>` | For a remote window, `ssh -t` to the `attach` verb, which runs the host's `tmux attach-session`, read-only unless `--rw`. A role counts its remote runs too; a remote window needs no local session |
| `mdstack attach builders` | Adds one pane per remote builder that prints its host's `capture` reply every 15 s; host_scan_interval (#346) replaces that interval |
| `mdstack logs` | The `logs` verb returns the step summary tail (`-n`, at most 500 lines); never raw logs. `-f` is local only |
| `mdstack hosts` | The inventory view above |
| `mdstack connect <alias> [<session>]` | The owner's own shell or tmux session on a host ([Connect to a host](#connect-to-a-host)); not a crew window |

## Connect to a host

`mdstack connect` ([#1036](https://github.com/mw-ding/mdstack/issues/1036))
is the owner's one command to get a shell on an inventory host from any
machine that has the profile, usually a laptop:

```sh
mdstack connect [--project <config.toml>] <alias> [<session>] [-- <transport args>...]
```

- `<alias>` is a host name or its `connect.alias`. An unknown alias prints
  the known ones and exits 1.
- With `<session>` it runs `tmux new-session -A -s <session>` on the host,
  so the same command creates the session the first time and reattaches it
  later. Detaching (tmux prefix, then `d`) leaves it running. Without a
  session it opens a plain login shell.
- The transport, its proxy command and fixed options are profile data under
  `hosts.<name>.connect`, so one verb serves an SSH-only setup and a
  reconnecting one (mosh, Eternal Terminal). Words after the alias and
  session that start with `-` (for example a port tunnel) go to the
  transport; mdstack's own options go before the alias.
- It replaces itself with the transport, under the owner's SSH config and
  keys. It never uses the [crew SSH key](#security-model), whose forced
  entrypoint gives no shell, and it changes no crew state.

| `transport` | Plain shell | With `<session>` | `proxy` |
|---|---|---|---|
| `ssh` (default) | `ssh <host>` | `ssh -t <host> tmux new-session -A -s <session>` | `-o ProxyCommand=<proxy>` |
| `mosh` | `mosh <host>` | `mosh <host> -- tmux new-session -A -s <session>` | `--ssh=ssh -o ProxyCommand=<proxy>` plus `--experimental-remote-ip=remote`, since mosh's own remote-IP discovery uses the ProxyCommand slot |
| `et` | `et <host>` | `et <host> -c 'tmux new-session -A -s <session>'` | Refused; set `ProxyCommand` in the SSH config |

Profile options and passed-through arguments go between the transport and
the host. The destination is the host's `address` when set, else its name,
as for every other call (#1034), so user, port and key come from the SSH
config; `connect.alias` stays a lookup name only.

**Laptop to server, end to end.** The owner's laptop holds a profile with
the inventory; `host-b` is a Linux server reached over a reconnecting
transport behind an org proxy:

```toml
[hosts.host-b]
capabilities = { os = "linux", arch = "x86_64", engines = ["codex"] }
max_runs = 4
connect = { alias = "b", transport = "mosh", proxy = "corp-proxy %h %p" }
```

1. `mdstack connect b work` opens `work` on `host-b`, creating it the first
   time: `mosh --ssh='ssh -o ProxyCommand=…' --experimental-remote-ip=remote
   host-b -- tmux new-session -A -s work`.
2. Work, then detach with the tmux prefix and `d`, or close the laptop; mosh
   rides out a network change or sleep while the session keeps running.
3. Later, from home or another laptop with the same profile, `mdstack
   connect b work` reattaches the same session.
4. On an `ssh` host, `mdstack connect host-a -- -L 8080:localhost:8080`
   opens a plain shell with the port forward passed to `ssh`; mosh has no
   port forwards.
5. `mdstack connect x` with no such host prints
   `crew connect: unknown host alias x; known: b, host-a, host-b` and exits 1.

## Forge-less hosts: remote test runner

Owner, 2026-11-03 ([#715](https://github.com/mw-ding/mdstack/issues/715)):
the first second host has no access to the forge (GitHub), so M20 builds a
remote test runner first and moves remote role sessions to a follow-up.
A forge-less host is reached over SSH from the primary only. It cannot
clone, fetch, push or post, so it never runs a role session. It still takes
the heaviest local load: the check runs builders and reviewers repeat on
the primary.

**Capability.** `[hosts.<name>] forge = false` (default `true`). A
forge-less host takes runner jobs only. It needs no `engines` or `roles`,
and `max_runs` caps its concurrent jobs. `validate` refuses a forge-less
primary, a forge-less host with `roles`, and one in `placement.hosts`.
Placement never picks it. Host names stay in the untracked profile only
(spec R1).

**The primary is the forge gateway.** Code only reaches the host from the
primary, over the [hardened call](#remote-call-and-runner):

1. The primary writes a `git bundle` of the head, incremental against the
   tip the host mirror last reported, or full on the first seed.
2. A `seed` verb streams it to the host, which fetches it into its project
   mirror under `refs/crew/heads/<sha>` and reports the new tip.
3. `mdstack host prepare` on a forge-less host seeds the default branch the
   same way. The host never fetches from the forge and holds no forge login.

**Command set.** A `job` verb (`job_id`, `project`, `head`, `commands`) is
refused unless `head` is a commit in the host's project mirror. It runs, at
that head in a detached scratch worktree `jobs/<job-id>/wt/` under `root`,
a closed set of forge-free checks in the background, in a scrubbed env (only
`PATH`, `HOME`, locale, `TMPDIR` and the user name pass):

| Command | Runs |
|---|---|
| `check-repo` | `scripts/check-repo.py` |
| `tests` | The named `dev/tests/*/test-*.py`, checked against the glob, in parallel with `scripts/run-tests.py`. Selection is unchanged: the targeted local set ([AGENTS.md](../../AGENTS.md)) |
| `evidence` | One offline `scripts/evidence-cli.py` capture with its `--setup` file |

Anything else is refused. What stays on the primary: anything that needs
the forge (`gh`, `mdstack poll`, trains, releases), live tmux runtime evidence,
link checks (they need the internet; CI owns them) and every model session.

**Results by reference.** The host writes `jobs/<job-id>/result.json`: head
sha, and per command the exit code, duration and log path. Logs stay on the
host. A `result` verb returns `running` or the result with capped log tails.
A retried `job_id` returns the first job and never reruns it; jobs untouched
for 7 days are removed on the next `job` call.
The primary's `mdstack runner` client stores it under
`$CREW_STATE/runner/<job-id>/` and prints `runner:<host>/<job-id>
head=<sha>`; a full log is fetched on demand. Built in
`environments/terminal/crew.d/runner.py` (#728):
`mdstack runner run --head <sha> [--host <h>] -- check-repo test-*.py...`
picks `--host`, else the ready forge-less host with the lowest load against
`max_runs`, seeds a full bundle of the head (incremental seeding is a
follow-up) and polls `result` every few seconds;
`mdstack runner logs <job-id> [<command>]` prints the capped log tails again.
As evidence, a runner capture
names the host, the job and the head sha. At the PR head it counts as a
local run of the same commands; at another head it does not count.
`scripts/evidence-cli.py --runner <job-id>` renders the stored result as
that capture and refuses one at another head (#729,
[verification](../verification.md#q2-validator-reproduction)).

**Failure and fallback.** The runner adds no gate and never blocks one. PR
CI stays the full-suite gate.

| Case | Action |
|---|---|
| No forge-less host in the profile | Run locally, as today |
| Transport fails for 3 polls in a row (`unreachable`) | Run the same commands locally; record `runner: <host> unreachable; ran locally`. A late remote result is discarded |
| `refused` (not ready, version skew, at cap, head not seeded) | Same, with the reason |
| A command exits non-zero on the runner | A red run, not a fallback. A suspected host-only failure is rerun locally at the same head; the local result decides and the drift gets a finding |

**Security.** The [security model](#security-model) holds, plus:

- The hardened call is the only path: forced-command key, closed verbs, no
  agent, X11, TCP or environment forwarding.
- No forge credential exists on the host. The job env is scrubbed of
  tokens, the SSH agent and profile values. `mdstack host check` reports the
  logins check `n/a` and warns if a forge login is found there.
- A job runs repo code at the head as the runner account, as a local test
  run does. Only owner-controlled hosts join. The host has no route or key
  to the primary (N3).

Cases that need a real forge-less host (seeding, a real run matching a
local one, an unreachable fallback) are logged in
[#716](https://github.com/mw-ding/mdstack/issues/716) and stay open until
the owner records them there.

## Runbook: add a runner host

Adds one [forge-less host](#forge-less-hosts-remote-test-runner) that runs
the targeted local set for the primary (20.12,
[#349](https://github.com/mw-ding/mdstack/issues/349)). Every step is the
owner's. `<host>` is the host's overlay name, `<root>` its `root`
(default `~/.mdstack`), and `<bundle>` the mdstack release bundle extracted on
the host. Real-device proof of each step is logged in
[#716](https://github.com/mw-ding/mdstack/issues/716).

1. **Overlay.** Join the host to the overlay (N1) and check that `<host>`
   resolves on the primary (N2). Set the access rules so the primary can
   open SSH to the host while the host has no route to the primary (N3), and
   make SSH listen on the overlay only (N4). mdstack configures none of
   this (N6).
2. **Toolchain and mdstack.** The host needs `python3`, `git` and `tmux`
   on the runner account's `PATH`. Copy the primary's release bundle
   (`mdstack-<version>.tar.gz` and `SHA256SUMS`,
   [bootstrap](../bootstrap.md)) to the host, check the sum, then extract it
   to `<bundle>`. The host has no forge login, so it cannot download the
   bundle itself. The entrypoint refuses a call from a different version, so
   upgrade the host whenever the primary upgrades.
3. **Crew key.** On the primary, make a key used for the crew call only. Give
   `<host>` a `Host` entry in the primary's SSH config with its user, port,
   `IdentityFile` and `IdentitiesOnly yes`. The client keeps only those auth
   and host-key settings; a `ProxyJump` or forwarding line is dropped
   ([Remote call](#remote-call-and-runner)). On the host, add the key's
   public half to the runner account's `authorized_keys`, forced to the
   entrypoint:

   ```text
   command="python3 <bundle>/environments/terminal/remote/crew-remote.py --root <root>",restrict,pty <public-key>
   ```

   `pty` lets the entrypoint take a TTY for the `attach` verb only; it
   refuses every other verb with one ([#348 TTY contract](#remote-acceptance-criteria-and-the-local-lab)).
   Strict host-key checking never accepts a new key. Add the host's key to
   the primary's known-hosts once, after checking its fingerprint out of
   band.
4. **Runner.** Run `python3 <bundle>/environments/terminal/remote/crew-remote.py --root <root>
   runner` as a user-level service of the runner account that restarts on
   exit: a launchd agent with `KeepAlive`, or a systemd user unit with
   `Restart=always` and lingering on. Never run it as root. The runner owns
   the host's crew tmux session and writes `<root>/runner.json` as its
   heartbeat.
5. **Smoke test.** From the primary:

   ```sh
   echo '{"verb": "version"}' | ssh -T <host> crew-host
   ssh -T <host> id </dev/null
   ```

   The first prints `"result": "ok"`, the primary's version and
   `"runner": "up"`. The second prints `refused`: the key runs the
   entrypoint only.
6. **Profile.** Add the host to the project `config.toml`, never to mdstack
   (spec R1). A forge-less host takes no `engines`, `roles` or
   `placement.hosts` entry:

   ```toml
   [hosts.<host>]
   forge = false
   capabilities = { os = "linux", arch = "x86_64" }
   max_runs = 2
   ```

   With a first `[hosts]` table, the primary needs its own table too, with
   `primary = true` and its `engines`. Run
   `core/crew-config.py validate <project>/config.toml`.
7. **Seed.** `mdstack host prepare <host> [--project <config.toml>]`
   fetches the primary's checkout and seeds the default branch into the
   host's mirror (`ok prepare seed: project mirror`). It then runs
   `mdstack host check`, which reports the logins check as `n/a`, or `warn`
   when a forge login is present on the host. The entrypoint's `check` verb
   ([#743](https://github.com/mw-ding/mdstack/issues/743)) also reports
   `tools`, `project mirror`, `runner` and `capacity`; with all of them `ok`
   the host prints `ready`, and `mdstack runner run` without `--host` may pick
   it.
8. **First job.** From a checkout at the head:

   ```sh
   mdstack runner run --head "$(git rev-parse HEAD)" --host <host> -- check-repo test-run-tests.py
   ```

   It prints `runner:<host>/<job-id> head=<sha>` and each command's exit.
   Run the same commands locally at the same head; the results must match
   (#716 case 2). `mdstack runner logs <job-id>` fetches the log tails again.

**Remove a host.** Delete its `[hosts.<host>]` table, remove the
`authorized_keys` line, stop and remove the runner service, then delete
`<root>`. Job results already stored on the primary under
`$CREW_STATE/runner/` stay.

## Runbook: add or remove a role host

Extends the [runner-host runbook](#runbook-add-a-runner-host) to a
[role host](#terms): one with its own forge access (N5) that takes builder
and reviewer runs (20.12 from [#1281](https://github.com/mw-ding/mdstack/issues/1281),
[#1363](https://github.com/mw-ding/mdstack/issues/1363)). Every step is the
owner's. Placement, the remote run lifecycle, attach and remote wakes and
messages are built (#207, #345, #346, #348), and so is partition handling
(#347).

**Add a role host.** Runner-host steps 1 (overlay), 3 (crew key) and 5
(smoke test) apply unchanged. The others change:

| Step | Runner host | Role host |
|---|---|---|
| 2. Toolchain | `python3`, `git`, `tmux`; the bundle copied from the primary | Also `gh`, each listed engine's CLI and the OS service tool (below); `python3` 3.11 or later. Copy the primary's bundle too, so the versions match |
| Logins | None; a forge login warns | On the host itself, never copied (#1281 decision 5): `gh` for the identities of its `roles` only, and each engine in `capabilities.engines`. Where each lives: [Login locations](#login-locations) |
| 4. Runner | A user-level service | Per OS, below |
| 6. Profile | `forge = false` | `capabilities.engines`, `roles`, `max_runs` and a `placement.hosts` entry; `toolchain_bin` if builders need one |
| 7. Prepare | Seeds from the primary | Creates the mirror with the host's own `gh` login |

No verb calls the [host OS adapter](#host-os-adapters)'s install yet, so the
owner writes the service by hand as the runner account, with the adapter's
names, so a later install finds the same file:

- **macOS (launchd).** Write `~/Library/LaunchAgents/dev.mdstack.runner.plist`
  with `Label` `dev.mdstack.runner`, `ProgramArguments` `python3
  <bundle>/environments/terminal/remote/crew-remote.py --root <root> runner`,
  `KeepAlive` and `RunAtLoad` true and `WorkingDirectory` `<root>`. Load it
  with `launchctl bootstrap gui/$(id -u) <plist>` from the account's own
  login session: outside `gui/<uid>` the runner cannot read keychain logins.
  `launchctl print gui/$(id -u)/dev.mdstack.runner` shows `state = running`.
- **Linux (systemd).** Write `~/.config/systemd/user/mdstack-runner.service`
  with that `ExecStart`, `WorkingDirectory=<root>`, `Restart=always` and
  `WantedBy=default.target`. Run `systemctl --user daemon-reload`, then
  `systemctl --user enable --now mdstack-runner.service`, then
  `loginctl enable-linger "$USER"`; without lingering the runner stops at
  logout and check's `linger` row warns. On a headless host with no Secret
  Service, use the file-backed login stores ([Login locations](#login-locations)).
- **Linux supervised.** Lab containers only, chosen by the image's
  `/etc/mdstack/supervised`; its PID-1 supervisor runs the runner, so there
  is no service step. Never a way onto a real host.

**Ready.** `mdstack host prepare <host>` makes the mirror, then runs
`mdstack host check <host>`. The `runner` row reads `up` with the service
state beside it (`macos running`, `linux active` or `linux supervised`); a
systemd host adds `linger`. `logins` stays a human step until every login
is present. With every row `ok` the host is `ready`.

**Remove a role host.**

1. Take it out of `placement.hosts` and any `placement.rules`, so no new run
   lands there. Once remote runs exist, wait until `mdstack hosts` shows no
   live run on it; their worktree guards ([#345](https://github.com/mw-ding/mdstack/issues/345))
   still apply, so unlanded work is never deleted.
2. Delete its `[hosts.<host>]` table and run `core/crew-config.py validate`.
3. On the primary, remove its SSH config `Host` entry and its known-hosts
   line (`ssh-keygen -R <host>`); on the host, the `authorized_keys` line.
4. Stop and remove the service: on macOS `launchctl bootout
   gui/$(id -u)/dev.mdstack.runner` and delete the plist; on Linux
   `systemctl --user disable --now mdstack-runner.service`, delete the unit
   and run `systemctl --user daemon-reload`.
5. Delete `<root>`. Logging out of `gh` and the engines, turning lingering
   off and leaving the overlay are the owner's call; mdstack never changes
   auth.

**What the lab proves, and what it does not.** The local lab is the
[C and V hosts above](#remote-acceptance-criteria-and-the-local-lab): C is
the #1356 image, brought up by the guarded setup (lab C, #1357) and
driven by the real-SSH scenarios (lab F, #1360), with the manifest and
evidence of lab G (#1361); V is a macOS VM, a later M25.1 item. Lab C needs
the owner's Docker seat and a running daemon. A lab run does steps 1 to 3
for its own containers (run-scoped networks, `activate`, `authorize`).

| Step | Lab C (Linux, supervised) | Lab V (macOS VM) | Still needs the real device or overlay |
|---|---|---|---|
| Overlay (N1–N4) | An analogue only: run-scoped networks and loopback-published SSH | Same, through a localhost forward | All of N1–N4 on a real overlay; listener `warn` rows on a real host |
| Crew key, smoke test | Real `sshd`, forced command and host key | Same | none |
| Runner service | Supervised only | launchd agent, `KeepAlive`, logout and reboot | A systemd user unit with lingering: a systemd-capable Linux host or VM |
| Logins | Synthetic | Synthetic | Real vendor and `gh` logins, keychain and Secret Service visibility |
| Prepare, check | Against a fake forge | Same | A mirror fetched with a real `gh` login |
| Role runs | After #345–#348, stub engines | Same | Real partition and attach ([#716](https://github.com/mw-ding/mdstack/issues/716) cases 3 and 4); attached devices |
| Remove | Keys, `<root>`, profile | Plus `bootout` | `systemctl --user disable` on a real unit |

## Remote acceptance criteria and the local lab

Acceptance criteria for the remote issues, and what the M20.1 local lab can
prove ([#1353 finding](https://github.com/mw-ding/mdstack/issues/1353#issuecomment-6725433939)).
**C**: Linux containers on the primary over loopback-published SSH. **V**: a
macOS VM on the primary. **R**: a real second device, logged in
[#716](https://github.com/mw-ding/mdstack/issues/716), whose cases stay open
until the owner records them. A lab run says which of C or V it used, and a
stub-engine run proves lifecycle and transport, not vendor logins or quota.

The C host is built from `environments/terminal/remote/lab/` (#1356): a
`Dockerfile` over an owner-approved, preloaded ARM64 Linux base pinned by
digest that downloads nothing, a key-only `sshd_config`, and
`crew-lab-host.py`. Its `supervise` mode is PID 1: it makes the container's
own SSH host key at first start (the image deletes any the base carried),
then keeps `sshd` and the
runner up, restarting either on exit, with the runner as the non-root
`crew` user in a scrubbed env; `ready`, the image health check, is the
runner heartbeat. `activate` verifies the bundle and `SHA256SUMS` that
`docker cp` copied in before moving it into place, and records the tag,
digests and, for a dev tag, the exact source SHA. `authorize` writes the
run's key as the only `authorized_keys` line, forced and `restrict`. No
login, token, SSH agent or home is copied in. Container setup and teardown
(#1357) is `crew-lab-docker.py` on the primary, described in the
[campaign harness](../campaign-harness.md#lab-hosts-in-docker). Its runner
scenarios and failure injection (#1360) are
[`crew-lab-scenarios.py`](../campaign-harness.md#lab-runner-scenarios).

**Lab base.** `LAB_BASE` comes from `base.Dockerfile` beside it (#1430):
official `debian:bookworm-slim` pinned by its `linux/arm64` manifest
digest, plus only `python3` (3.11), git, tmux, `openssh-server` and
procps, with the package's host keys deleted. Its pinned ref, the
`name@sha256:<64 hex>` the owner's Docker Desktop holds, is recorded in
`environments/terminal/remote/lab/base.ref`. Rebuild and re-pin from the
repo root, then commit `base.ref` (apt packages are not pinned, so each
rebuild gets a new digest):

```sh
docker build -f environments/terminal/remote/lab/base.Dockerfile \
  -t mdstack-lab-base:bookworm environments/terminal/remote/lab
docker image inspect --format '{{index .RepoDigests 0}}' \
  mdstack-lab-base:bookworm > environments/terminal/remote/lab/base.ref
DOCKER_BUILDKIT=0 docker build -f environments/terminal/remote/lab/Dockerfile \
  --build-arg LAB_BASE="$(cat environments/terminal/remote/lab/base.ref)" .
```

The lab image build uses the classic builder: BuildKit resolves a
digest-pinned `FROM` against the registry and fails on this local-only
image, which is never pushed.

| Issue | Acceptance criteria | Lab | Real device |
|---|---|---|---|
| Host OS adapters | Each operation in the [adapter table](#host-os-adapters) on its OS; a mismatch fails check 5 | C: `linux` supervised; V: `macos` launchd | A systemd user unit with lingering needs a systemd host or VM |
| [#345](https://github.com/mw-ding/mdstack/issues/345) | `spawn` places and starts a role run on the host through the runner; it survives the SSH call ending; brief and verdict file reach the host; `kill`, `restart` and `down` keep the C6 worktree guards there | C, V | none |
| [#346](https://github.com/mw-ding/mdstack/issues/346) | Offset pulls survive an interrupted or repeated pull and a primary restart with no lost or doubled line; `mdstack send` delivers and its `ack` returns through the mirror | C | none |
| [#347](https://github.com/mw-ding/mdstack/issues/347) | A both-alive partition keeps the claim and starts no duplicate; reconcile on return; abandon writes a tombstone | C, by network disconnect (a pause is the unresponsive case, not a partition) | #716 case 3 |
| [#348](https://github.com/mw-ding/mdstack/issues/348) | Attach to a real remote pane, read-only unless `--rw`; `attach builders` captures; `logs` returns the step summary tail. Runner-job logs alone do not meet it | C, V | #716 case 4 |
| 20.12 | The [runner-host runbook](#runbook-add-a-runner-host) extended to role hosts, with per-OS steps ([written](#runbook-add-or-remove-a-role-host), #1363) | C: Linux supervised; V: launchd | Overlay and attached devices |
| [#209](https://github.com/mw-ding/mdstack/issues/209) | Runner first, as row 20.7 says ([#715](https://github.com/mw-ding/mdstack/issues/715)): the primary plus a forge-less runner host | Recorded on C, a simulated host ([#1492](https://github.com/mw-ding/mdstack/pull/1492) R1) | #716 case 2 completes it |
| #716 cases 1 and 5 | Seed, job, result parity with a local run, unreachable fallback | Rehearsal on C | Completion |

**#209 boundary.** Its body's "builder on a remote host" is the role-host
run, not #209: it follows #345–#348 as a new #716 row on the real host
([#1281](https://github.com/mw-ding/mdstack/issues/1281) decision 4).

**#348 TTY contract** (built). The key line is `restrict,pty`; the client
passes `-t` for `attach` only and `-T` for every other verb. With `-t`,
stdin is the TTY, so the attach request travels in the SSH command as
`crew-host <payload>`, its JSON base64url-encoded, and the entrypoint
decodes and checks it as any other request. The host's tmux client runs
with the `TERM` that `ssh` sends, so the host needs that terminal's
terminfo entry. The entrypoint refuses
`attach` without a TTY and every other verb with one, so the key still
runs the closed verb set, never a shell. A read-only attach (tmux `-r`)
can only detach or switch clients. `--rw` is the owner typing into the
run's pane, which includes tmux's own command prompt, so it is as strong
as a shell as the runner account on that host; it is never the default.

## Build issues

The milestone M20 issues
([#160 milestones](https://github.com/mw-ding/mdstack/issues/160#issuecomment-6532947853)),
mapped onto this design and re-scoped runner first (#715). The follow-up
milestone holds the remote role sessions part.

| ID | Issue | Scope from this design | Depends on | Milestone |
|---|---|---|---|---|
| 20.2 | [#204](https://github.com/mw-ding/mdstack/issues/204) | [Host inventory](#host-inventory-profile-extension) keys and `validate` rules | #158 | M20 (done) |
| 20.3 | [#205](https://github.com/mw-ding/mdstack/issues/205) | `mdstack host check` and `mdstack hosts` ([Host readiness](#host-readiness)) | #204, #190 | M20 (done) |
| 20.4 | [#206](https://github.com/mw-ding/mdstack/issues/206) | `mdstack host prepare` and the host-side layout; on a forge-less host it seeds the mirror from the primary (`seed` verb) | #205, #208 | M20 |
| 20.6 | [#208](https://github.com/mw-ding/mdstack/issues/208) | [Remote call and runner](#remote-call-and-runner): client, entrypoint and verbs, runner, and the failure-semantics doc section | #158 | M20 |
| 20.7 | [#209](https://github.com/mw-ding/mdstack/issues/209) | Two-host dry run: primary plus a forge-less runner host. Owner-run ([#716](https://github.com/mw-ding/mdstack/issues/716) case 2) | 20.13–20.16 | M20 |
| 20.12 | [#349](https://github.com/mw-ding/mdstack/issues/349) | Runbook "add a runner host" (overlay, forced-command key, runner, seed) and host rows in the tmux contract table | 20.15 | M20 |
| 20.13 | [#726](https://github.com/mw-ding/mdstack/issues/726) | `forge = false` host key, its `validate` rules, `mdstack hosts` and `mdstack host check` | #204, #205 | M20 |
| 20.14 | [#727](https://github.com/mw-ding/mdstack/issues/727) | Runner `job` and `result` verbs, closed command set, scrubbed env | #208, #206 | M20 |
| 20.15 | [#728](https://github.com/mw-ding/mdstack/issues/728) | `mdstack runner` client, results by reference, local fallback | #726, #727, #206 | M20 |
| 20.16 | [#729](https://github.com/mw-ding/mdstack/issues/729) | Runner capture as evidence; `docs/verification.md` row | #728 | M20 |
| 20.5 | [#207](https://github.com/mw-ding/mdstack/issues/207) | `place()`, `--host --reason`, the run record fields and the `mdstack status` host column | #204 | Follow-up |
| 20.8 | [#345](https://github.com/mw-ding/mdstack/issues/345) | Remote run lifecycle: `mdstack spawn`, `kill`, `restart` and `down` executed on the placed host; brief and review-file hand-off | #206, #207, #208 | Follow-up |
| 20.9 | [#346](https://github.com/mw-ding/mdstack/issues/346) | Remote wake and messages: watcher pulls and status mirror (C1, C4), `mdstack send` and `mdstack acked` through `send` (C3), `host_scan_interval` | 20.8 | Follow-up |
| 20.10 | [#347](https://github.com/mw-ding/mdstack/issues/347) | Partition handling for role runs: `unreachable`, reconcile on return, owner-approved abandon with tombstone. Runner jobs use the fallback above | 20.9 | Follow-up |
| 20.11 | [#348](https://github.com/mw-ding/mdstack/issues/348) | Remote `mdstack attach`, `mdstack attach builders` and `mdstack logs` for role windows. Runner logs come by reference (20.15) | 20.8 | Follow-up |
| — | not filed | A forge relay through the primary, if remote role sessions on forge-less hosts are ever needed | 20.8 | Follow-up |

## Design credit

The hardened remote call, the account-owned runner, the readiness check with
a repair mode and "an unreachable remote is never silently replaced" are
adapted from firstmate's remote secondmates
([firstmate](https://github.com/kunchenguid/firstmate), MIT license).
mdstack takes the contracts only, as for the [tmux binding](tmux.md#design-credit):
no code or text is copied. Not adopted: whole homes per host, a
sub-supervisor per host, and per-host merging (#160 row 6).
