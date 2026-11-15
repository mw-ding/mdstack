# Campaign harness contract

**Status:** level-a contract, built by #783 (M25 item 25.01). The scenario
runner (25.02, #784) is `scripts/campaign-run.py`; the disposable sandbox
setup (25.03, #785) is `scripts/campaign-sandbox.py`. Design:
the M25 integration campaign proposal on
[#782](https://github.com/mw-ding/eng-crew/issues/782).

Every M25 run touches only a recorded disposable sandbox: its own repo (a
local repo with a bare origin at level a), state root, worktree root, live
directory and tmux session. It never touches the live crew's session or
state, or the production repo. This page is the contract a run follows
before, during and after it mutates anything.
`scripts/campaign-guard.py` enforces its first two parts.

## Run manifest

Before any mutation the harness writes a run manifest with
`campaign-guard.py manifest`. It resolves the sandbox profile and pins:

- **repo:** the sandbox profile's `owner/name`;
- **profile:** the sandbox profile's absolute path and sha256, plus the
  production profile's path (the reference the guard compares against);
- **source:** the mdstack checkout under test and its full `HEAD` SHA;
- **release:** the installed release id the run exercises;
- **target:** the tmux session and the absolute `paths.state_dir`,
  `paths.worktree_root` and `paths.live_dir`;
- **sentinel:** an outside-sandbox file and its sha256;
- **run:** the run id and the scenario IDs (Axx) it covers.

The manifest is written only when the refusal check below passes and
`--out` resolves, symlinks followed, inside a sandbox root; any other
destination is refused with `refused: out:`. Raw run
logs stay under the sandbox state root; results are promoted to the run
issue as inline proof, never committed.

## Refusal before mutation

`campaign-guard.py check MANIFEST` runs before every mutating step (setup,
`mdstack up`, spawn, teardown). It re-resolves both profiles and exits 2,
printing one `refused: <reason>` line per problem, when:

- the sandbox names the production repo;
- the sandbox session is the production session;
- a sandbox root equals, contains or sits inside a production root;
- a sandbox root is still a `<placeholder>`;
- the sandbox profile changed since the manifest, its resolved repo, session
  or roots differ from the pins, or the source checkout moved off the pinned
  SHA.

Exit 0 prints `ok: run <id> targets <repo> (session <name>)`. A refusal
stops the run; never edit the manifest to get past one. Write a new
manifest for a new run instead.

Every child the harness starts gets the sandbox project file explicitly
(`--project` and `CREW_PROJECT`), so an inherited production `CREW_PROJECT`
or `CREW_STATE` cannot select the target. Use session-targeted tmux
operations only: never `kill-server` or global options.

An inherited `$TMUX` beats `TMUX_TMPDIR`: from a crew pane, a bare
`TMUX_TMPDIR=<sandbox> tmux kill-server` kills the owner's default server
([#817](https://github.com/mw-ding/eng-crew/issues/817)). So every harness
tmux call pins the sandbox socket, `<state>/tmux/tmux-<uid>/default`, with
`-S` and drops `TMUX` and `TMUX_PANE`. Scenario steps get the same pin from
the `<state>/bin/tmux` shim. It refuses any `-L`, and any `-S` naming
another socket, with exit 2. When debugging from a crew pane, run
`unset TMUX TMUX_PANE` first and call tmux only through the shim or with
`-S` on a throwaway socket.

## Scenario runner and results

`campaign-run.py MANIFEST --scenarios DIR --out FILE` runs the guard check
first; a refusal writes nothing and exits 2. It reruns the check before
every `run` step; a refusal there marks the scenario `BLOCKED`, the rest
`NOT RUN`, stops the run and exits 2. Select scenarios with
`--scenario Axx` (default: every manifest scenario); an ID outside the
manifest is refused. Each `DIR/<Axx>.json` lists public-CLI `run` steps with
an expected exit, and explicit `wait` steps that poll a file for a match up
to a deadline instead of sleeping a fixed time. `{source}` expands to the
pinned mdstack checkout, so a step calls its CLIs.

The committed specs live in `dev/tests/scripts/fixtures/campaign/`, one
`<Axx>.json` per scenario; the [scenario index](#scenario-index) lists them.

Profile changes a run needs, such as precheck on, path classes or a role
engine order standing in for a quota steer, go in an `--org-profile` file
under the sandbox state root. The pinned sandbox profile never changes, so
the guard check still passes.

Children get the sandbox profile as `CREW_PROJECT`, no other inherited
`CREW_*` variable, no `TMUX` or `TMUX_PANE`, no forge token (`GH_TOKEN`,
`GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`), no SSH
agent (`SSH_AUTH_SOCK`, `SSH_AGENT_PID`), `GH_CONFIG_DIR` set to
`<state>/gh-config`, `<state>/bin` first on `PATH`,
the stub logs `<state>/stub.log` and `<state>/gh.log`, the fake forge
directory `<state>/gh` as `CAMPAIGN_GH_DIR`, and the run seed as
`CAMPAIGN_SEED`.

Scenarios that change crew state each run in a fresh sandbox: one `setup`,
`campaign-run.py --scenario Axx` and `teardown` per scenario. The index's
`Sandbox` column marks them `fresh`.

When tmux is installed, the runner starts a decoy session on a throwaway
socket outside the sandbox and exports it as `TMUX`. If the decoy is gone
after a scenario, that scenario is `FAIL` (`decoy: ...`), the rest are
`NOT RUN` and the run stops: an inherited `TMUX` reached a server outside
the sandbox.

Results keep seven statuses apart:

- `PASS`: every step met its expected exit or match;
- `FAIL`: a command exit differed or a wait hit its deadline;
- `BLOCKED`: a tool the scenario requires is missing;
- `LIMITATION`: the scenario declares a known gap and is not run; only the
  owner can accept it;
- `NOT RUN`: a manifest scenario not selected or without a spec;
- `EXPECTED FAIL` and `ACCEPTED`: a step recorded with that disposition
  failed (see Fail-closed steps below); neither counts as a pass.

Each step records the command's own exit, stdout and stderr apart from the
capture outcome, so a working capture never reads as a pass. The results
file is rewritten atomically after each scenario, only inside a sandbox root.
The seed (random unless `--seed` is given) fixes the scenario order and
`CAMPAIGN_SEED`; `--rerun RESULTS` replays the same selection and seed, so
the same events and failure recur. The runner exits 0 only when every
result is `PASS`.

Fail-closed steps (#1412): a `run` step runs under `sh -c`, so its result
is its last command's exit. `scripts/campaign-lint.py` refuses a step with
an unhandled assertion: a `test`, `[`, `grep -q` or `!` pipeline whose exit
is neither the step's result, nor captured by a following `rc=$?`, nor
handled by a `||` after it, nor guarded by a trailing `|| exit 1`. An
assertion in a loop body must carry its own `|| exit 1`. A call to a
function defined in the step counts as an assertion when the function's
return can carry a failure (a nonzero `return`, `false`, or an unguarded
assertion at its tail); a helper that runs `exit 1` itself ends the step.
The lint is an allowlist (#1677): simple commands, pipelines and
`&&`/`||` chains; a `|| exit N` handler or a `|| { ...; exit N; }` group
ending in an unconditional `exit N`; `if`/`case`; loops; `name() { ...; }`
functions; subshells with no assertion, `exit` or `return`. Anything else
is refused by name, including other brace groups, a subshell that can fail,
a backgrounded compound command or assertion, `eval` and `trap`. In a
condition list only the final item is the predicate; an earlier assertion
there is refused.

Termination model (#1684): the lint decides where an `exit` or `return`
stops by one rule, not per form. `exit` ends the step, and `return` its
function, only when it runs in the step's own shell. These run in a child
shell, where `exit` ends only the child and the step goes on:

- a subshell, `( ... )`;
- every command of a multi-command pipeline, `a | b`;
- a backgrounded list, `... &`;
- a command substitution, `$( ... )` or backticks.

A function call runs in its caller's shell, so a helper that can `exit`
ends the step when called in the step shell and only the child when called
in one of the forms above. The lint refuses any `exit`, `return` or call
to such a helper in a child and names the child, for example
`f() { test -e a || exit 1; }; f | cat` or
`test -e a || { echo bad; exit 1 & }`. A `|| exit N` or
`|| { ...; exit N; }` handler counts only when its `exit` runs in the step
shell. A command substitution's status is dropped, so a call there to a
helper whose return can carry a failure (including a `return` in an `if`
or `while` condition) is refused too. To keep a loop's output, redirect it to a file rather than piping
it; to use a helper's output, have the helper fail through its status
(`a && b`) and assert the value.
Restructure such a step into the allowed forms. The runner checks
each step before it runs and `FAIL`s a refused one unrun, and so does a
step that does not parse. A deliberate refusal keeps its explicit oracle:
capture the exit with `rc=$?` and assert it in the final chain, or declare
the step's `exit`.

Required cases: every step of a committed scenario, `<Axx>/<step name>`, is
a required case. A case that fails today carries
`"disposition": {"state": "expected-fail", "reason": "..."}` (waiting for a
fix) or `"state": "accepted"` (accepted as is). The reason is required. A
disposition step that passes `FAIL`s, so the record is dropped once the fix
lands. `check-repo.py` (rule `campaign`) compares the committed cases with
the merge base of `origin/main`: a case there that is gone at head must be
listed with a reason in `retired-cases.json` beside the scenarios. Deleting
a case together with its disposition, renaming a step or deleting a
scenario is caught. A reason never waives CI, an approval or acceptance
evidence.

### Scenario index

Each scenario has its own file under
[campaign-scenarios/](campaign-scenarios/A01.md): its source issue, its
committed spec (or, for a driver-only scenario such as A29, the driver that
runs it), whether it needs a fresh sandbox, and its notes. Edit the scenario
file, never this table. A29 has no JSON spec: `a28/teams.py --handoff` runs it
from an operator shell.

<!-- scenarios:begin: generated from docs/campaign-scenarios/ by `python3 scripts/check-repo.py --fix` -->

| ID | Source | Spec | Sandbox |
|---|---|---|---|
| [A01](campaign-scenarios/A01.md) | #786 | `A01.json` | shared |
| [A02](campaign-scenarios/A02.md) | #786 | `A02.json` | shared |
| [A03](campaign-scenarios/A03.md) | #787 | `A03.json` | fresh |
| [A04](campaign-scenarios/A04.md) | #787 | `A04.json` | fresh |
| [A05](campaign-scenarios/A05.md) | #787 | `A05.json` | fresh |
| [A06](campaign-scenarios/A06.md) | #788 | `A06.json` | fresh |
| [A07](campaign-scenarios/A07.md) | #788 | `A07.json` | fresh |
| [A08](campaign-scenarios/A08.md) | #789 | `A08.json` | fresh |
| [A09](campaign-scenarios/A09.md) | #789 | `A09.json` | fresh |
| [A10](campaign-scenarios/A10.md) | #789 | `A10.json` | fresh |
| [A11](campaign-scenarios/A11.md) | #790 | `A11.json` | shared |
| [A12](campaign-scenarios/A12.md) | #791 | `A12.json` | shared |
| [A13](campaign-scenarios/A13.md) | #792 | `A13.json` | fresh |
| [A14](campaign-scenarios/A14.md) | #793 | `A14.json` | fresh |
| [A15](campaign-scenarios/A15.md) | #794 | `A15.json` | fresh |
| [A16](campaign-scenarios/A16.md) | #794 | `A16.json` | fresh |
| [A17](campaign-scenarios/A17.md) | #795 | `A17.json` | fresh |
| [A18](campaign-scenarios/A18.md) | #795 | `A18.json` | fresh |
| [A19](campaign-scenarios/A19.md) | #797 | `A19.json` | shared |
| [A20](campaign-scenarios/A20.md) | #796 | `A20.json` | fresh |
| [A21](campaign-scenarios/A21.md) | #798 | `A21.json` | fresh |
| [A22](campaign-scenarios/A22.md) | #799 | `A22.json` | fresh |
| [A23](campaign-scenarios/A23.md) | #802 | `A23.json` | fresh |
| [A24](campaign-scenarios/A24.md) | #803 | `A24.json` | shared |
| [A25](campaign-scenarios/A25.md) | #804 | `A25.json` | fresh |
| [A26](campaign-scenarios/A26.md) | #804 | `A26.json` | fresh |
| [A27](campaign-scenarios/A27.md) | #800 | `A27.json` | fresh |
| [A28](campaign-scenarios/A28.md) | #801 | `A28.json` | shared |
| [A29](campaign-scenarios/A29.md) | #1441 | driver | n/a |
| [A31](campaign-scenarios/A31.md) | #804 | `A31.json` | fresh |
| [A32](campaign-scenarios/A32.md) | #790 | `A32.json` | shared |

<!-- scenarios:end -->

## Cleanup checks

After teardown the run records both checks below in its result:

1. **Sentinel:** `campaign-guard.py sentinel MANIFEST` re-hashes the
   outside-sandbox file. Exit 0 prints `sentinel unchanged`; exit 1 (changed
   or missing) is a P0 isolation finding.
2. **Retained work:** teardown uses `mdstack kill` and `mdstack down`, which keep a
   worktree with uncommitted or unlanded work and record it. The run lists
   every retained worktree and its unlanded commits. A discard happens
   only with an explicit recorded discard, which is the owner's choice and is
   never part of an automatic cleanup. Evidence and logs under the sandbox
   state root stay until the run's results are posted.

A run whose cleanup checks were not recorded counts as `NOT RUN`, not as a
pass.

## Sandbox setup and runbook

`scripts/campaign-sandbox.py` (25.03) sets up and tears down the disposable
sandbox. Level a is built; level b is a print-only plan; level c reuses the
owner-run issues.

### Level a: local repo and bare origin

```sh
python3 scripts/campaign-sandbox.py setup --root "$SANDBOX" --run-id "$RUN" \
  --production config.toml --source . --release "$RELEASE" \
  --sentinel "$OUTSIDE_FILE" --scenario A01
python3 scripts/campaign-run.py "$SANDBOX/state/manifest.json" \
  --scenarios "$SCENARIOS" --out "$SANDBOX/state/results.json"
python3 scripts/campaign-sandbox.py teardown "$SANDBOX/state/manifest.json"
```

`setup` refuses before any write when `$SANDBOX` exists and is not empty
or overlaps a production root. It then creates:

- `origin.git`, a bare origin, and `repo`, its clone seeded on `main` with
  `ci.sh`, the local CI fixture (a scenario sets `CI_RESULT` to replay a red
  run);
- `repo/crew.toml`, the sandbox profile, excluded from git because
  `mdstack spawn` takes the repo from the profile's checkout: repo
  `campaign/sandbox-<run>`, tmux session `crew-campaign-<run>`, `state`,
  `wt` and `live` roots under `$SANDBOX`, and `toolchain_bin` set to
  `state/bin`;
- `state/bin/claude` and `state/bin/codex`, engine stubs with no model.
  Each runs bash under the engine's name, so the liveness probe sees that
  harness. It acks each `inbox: <id>` line in `$CREW_STATUS` and runs a
  typed `campaign-exec: <sh>` line. `state/bin/gh` is the fake forge: it
  logs every call and answers from `$CAMPAIGN_GH_DIR/<cmd>-<sub>[-<arg>].json`
  (for example `pr-list.json` or `pr-view-5.json`), written by the scenario.
  A `--label L` query reads `<cmd>-<sub>-label-L.json` first, so held
  items (`issue-list-label-crew:hold.json`) differ from the open issue list.
  A call with `--state S` reads `<cmd>-<sub>-S.json` next, so open and closed
  issue lists can differ. A `--body-file -` call's body is appended to
  `$CAMPAIGN_GH_DIR/bodies.log` after a `--- gh <args>` line.
  Once the scenario writes `$CAMPAIGN_GH_DIR/api.json`, a map from paths below
  `repos/<owner>/<name>/` to answers, `gh api` reads from it and keeps each
  posted comment, so a control item holds its handoff record. Its `fail`
  count fails the next posts, with `fail_mode: lost` landing them first, and
  a `post-probe` script's output is kept on each comment it posts;
- `state/sandbox.json`, the control item (number 1, label
  `integration:run`), the ten crew labels plus `integration:finding` and
  `integration:run`, the fixture identities and the CI fixture;
- `state/manifest.json`, the guarded run manifest above;
- when tmux is installed, `state/bin/tmux`, the socket-pinning shim, with
  its socket under `state/tmux/` (recorded as `tmux` in `sandbox.json`).

`teardown` runs the guard check first and refuses on drift. It also
refuses when a team's profile or `--org-profile` changed since setup, or
resolves a root outside `$SANDBOX` or on a production root. For each team
in `state/sandbox.json` it runs `mdstack down --preserve`, then kills only
that team's exact session on the sandbox socket
(`tmux -S <socket> kill-session -t =<session>`). It lists every
repo or worktree with uncommitted or unpushed work, and checks the sentinel.
It records all three in `state/cleanup.json`. Exit 1 means the sentinel
changed: a P0 isolation finding. After the results are posted,
`teardown --remove` deletes `$SANDBOX`, but only when nothing is retained,
the sentinel is unchanged and `state/sandbox.json` marks it as a sandbox.
Otherwise it keeps the tree for the owner's recorded discard.

### Level b: forge sandbox (blocked, owner account access)

Level b needs a disposable forge repo and accounts from the owner. Never
create one yourself, and never use the production repo. To print the
operations the owner's setup performs, without running any of them:

```sh
python3 scripts/campaign-sandbox.py plan-forge --repo OWNER/NAME --production config.toml
```

The plan covers the private repo, the ten crew labels and the two
`integration:*` labels, collaborator invitations for the builder and
reviewer identities, the seed push with `.github/workflows/ci.yml` copied from
the source, and the control issue. Once the owner has provided the repo:

1. Run the plan's operations as the owner, or have the owner approve them.
2. Write a sandbox profile naming that repo, its identities, its own session
   and absolute roots outside every production root.
3. Write the manifest with `campaign-guard.py manifest`, then follow
   [docs/runbook-new-repo.md](runbook-new-repo.md) for the first crew run.
   Each scenario passes only on its recorded markers, heads, CI and cleanup.

### Lab hosts in Docker

`environments/terminal/remote/lab/crew-lab-docker.py` (M20.1 lab C, #1357)
adds role-host containers, built from the [lab image](runtimes/multi-device.md#remote-acceptance-criteria-and-the-local-lab),
to a level-a run. Each command runs the guard check first.

```sh
python3 environments/terminal/remote/lab/crew-lab-docker.py setup "$SANDBOX/state/manifest.json" \
  --image "$LAB_IMAGE" --stage "$BUNDLE_STAGE" --tag "$TAG" [--source-sha SHA] [--n3]
python3 environments/terminal/remote/lab/crew-lab-docker.py n3 "$SANDBOX/state/manifest.json"
python3 environments/terminal/remote/lab/crew-lab-docker.py teardown "$SANDBOX/state/manifest.json"
```

- **Manifest.** `setup` adds a `lab` section to the run manifest: the Docker
  context and its endpoint, the run ID, the owner label, the image ID, the
  staged bundle hashes, and each network, container and volume ID as Docker
  returns it, with each host's published port and activation record (bundle,
  SHA256SUMS and source SHA); a host that activated another bundle or source
  SHA than the staged one stops setup. It refuses before any Docker mutation when the
  manifest already has a `lab` section, an alias is not lowercase, or a
  container or network with a planned name or the run's label exists. A new
  lab run needs a new manifest.
- **Isolation.** Every child gets only `PATH` and locale plus the run's own
  `HOME` and config directories under `state/lab/`: no inherited
  `CREW_*`, forge token, SSH agent, `TMUX` or `TMUX_PANE`. Docker calls go
  to the pinned endpoint. No host gets a mount: not the owner's home, the
  Docker socket or a tmux socket. SSH is published on `127.0.0.1` only, and
  `state/lab/home/.ssh/config` maps each alias to `127.0.0.1:<port>` with
  a per-run key and `known_hosts`.
- **N3.** Each host gets its own network. With `--n3` those networks are
  internal, nothing is published, and a driver container joins all of them.
  `n3` probes from each host to the other hosts, the Mac and the internet,
  with the driver reaching each host as the positive control; with `--n3`
  each host maps `host.docker.internal` to the host gateway, so the Mac
  probe tests routing, not name lookup. It reports `n3: unproved` (exit 1)
  unless every lateral probe is denied; an unresolved name is not denied,
  and a loopback setup is always unproved.
- **Teardown.** It first inspects every recorded ID and refuses, removing
  nothing, when the context now points at another endpoint or a live ID lost
  the run's owner or run label. Otherwise it saves each resource's inspect
  JSON and logs under `state/lab/evidence/`, then removes only those IDs. It
  never prunes, removes by wildcard or kills a tmux server. It records the
  sentinel check and a tmux decoy's survival in `state/lab/cleanup.json`;
  exit 1 means a changed sentinel or a lost decoy.

### Lab runner scenarios

`environments/terminal/remote/lab/crew-lab-scenarios.py` (M20.1 lab F, #1360)
drives `mdstack runner` over the real hardened SSH call to a loopback lab
host, between `setup` and `teardown`:

```sh
python3 environments/terminal/remote/lab/crew-lab-scenarios.py "$SANDBOX/state/manifest.json" \
  --stage "$BUNDLE_STAGE" [--host lab-a] [--only NAME]
```

- **Client.** The primary runs the staged bundle itself, verified by
  `scripts/crew-install.py` into `state/lab/toolkit/` and refused unless
  its digest is the one the hosts activated, so both ends run one version.
  macOS `ssh` reads `~/.ssh/config` from the account's home, never `HOME`,
  so `state/lab/bin/ssh` adds `-F state/lab/home/.ssh/config` to `ssh -G`
  only. Each call still runs the client's own `-F none` argv. The client
  carries a decoy `GH_TOKEN`, `GITHUB_TOKEN`, `SSH_AUTH_SOCK` and `CREW_*`.
- **Sample.** Branch `lab` of the sandbox repo has a `check-repo` that prints
  its OS and any forge, crew or agent variable it sees, and
  `dev/tests/lab/test-lab.py`, which each scenario commits red, green or
  slow.
- **Scenarios.** They start from A23's oracles. `exact-head`: the stored
  result at HEAD matches the same commands run locally, and the host job
  sees a clean env. `red`: a red run, not a fallback. `idempotent`: a
  repeated request ID returns its first reply, and a new one for the job ID
  returns the first job. `stale`: a stale head is refused before any call,
  and an unseeded head by the host.
- **Injections.** Each one is confirmed by a `version` call that fails
  while it holds and answers once it is lifted. `disconnect` is
  `docker network disconnect` mid-job, with the container and runner pids
  kept: the client falls back locally, and after reconnect the same job's
  result is pulled, with no second job at that head. `pause` is the
  unresponsive host: the client falls back, and the job finishes after
  `unpause`. `runner` kills the runner only: the supervisor starts a new
  one, `sshd` keeps its pid, and a job passes. `recreate` replaces the
  container mid-job (label-checked, with a new ID, host key and port, the
  manifest and SSH config updated): the client falls back, the host never
  reports the lost job done, and a fresh job passes. `partition` (#347)
  places a builder on the host with the real `mdstack up` and `mdstack
  spawn` in the sandbox session (a stub engine and `gh` on the host, the
  host's mirror seeded from a bundle as its own origin). Behind a
  `disconnect`, three watcher host scans (`pull_hosts`) give one
  `unreachable` escalate wake, `mdstack status` reads `unreachable since`,
  `mdstack restart` is refused, spawning the item again queues it (never
  placed elsewhere) and the claim is unchanged. After reconnect, reconcile
  finds the same pane alive and the mirror holds every line once. Before
  the outage, the watcher's pulls mirror the placed run's status lines, and
  `mdstack send --wait-ack` is typed into its pane on the host and gets its
  ack back through the mirror (A30, #1442). Behind a
  second `disconnect`, `mdstack kill --discard` writes a tombstone and drops
  the record and claim; on return the run is stopped on the host with its
  unlanded file kept. `status-pull` (#346) starts a stub role run in the
  runner's session that writes a status line every half second and acks
  each typed nudge. The toolkit's own offset pull is `unreachable` behind a
  `disconnect` while the run keeps writing; after reconnect, a repeated
  pull and a fresh primary module, the mirror holds every line once and in
  order, and a `send` through the host returns its ack through the mirror.
- **Attach (#348).** A run is planted as the runner account in the
  runner's tmux session, since `spawn` needs a forge (#345 proves it on
  fakes). Over real SSH, `capture` shows its pane and `logs` its step
  summary tail. A client on a pty attaches through the `restrict,pty` key
  line, read-only, so typed keys never reach the pane, and detaches with
  exit 0. Attach without a TTY and `version` with one are refused.
- **Report.** Each scenario prints `PASS` or `FAIL`, and
  `state/lab/scenarios.json` keeps what it saw. Exit 1 on any `FAIL`, 2 on
  a refusal.
- **Evidence.** Each run writes `state/lab/runs/<started>.json` and a
  Markdown copy with `crew-lab-evidence.py` (M20.1 lab G, #1361). They
  record lab C, each host's container, network, port, host key and
  activated bundle and source SHA, the image digest, the staged bundle
  hashes, the client bundle, the transport, every injected event with its
  Docker control, and a timeline. The record is `simulated` and never
  `real_device`: the loopback SSH path and each injection are labelled
  simulated, and the sample checks and the engine, forge and mirror
  origin behind the partition's placed run are labelled stubs. A scenario `--only` left out is `skipped` with
  `evidence: false`, so it supplies no evidence for #207 or #345–#348.
  With `partition` and `exact-head` both run, the record adds the A30
  remote-builder journey (#209, #1442): the placed builder, its mirrored
  status and acked send, the outage and reconcile, the abandon and the
  local comparison, labelled a simulated host with its physical limits
  (one machine, a loopback port rather than an overlay, a Docker network
  control rather than a lost link, a stub engine and forge). `teardown`
  adds its cleanup record to each run record.
- **Opt-in CI.** The `lab` job in `.github/workflows/ci.yml` (M20.1 lab H,
  #1362) runs on a PR labelled `lab`, from its next push, on an ARM64 runner.
  It pulls `LAB_BASE`, a repo variable naming the owner-approved base image
  pinned by digest, builds the lab image, and runs setup, every scenario and
  teardown, keeping `state/lab` as the `lab-evidence` artifact. With no
  `LAB_BASE`, Docker or ARM64 it records `lab: skipped (<why>); no lab
  evidence` and passes. It is no required check; the other jobs still run.

### Level c: owner-run devices and second environment

Level c reuses
[#209](https://github.com/mw-ding/eng-crew/issues/209),
[#716](https://github.com/mw-ding/eng-crew/issues/716) and
[#213](https://github.com/mw-ding/eng-crew/issues/213), with the same
scenario IDs and manifest. Record each host's capability, OS, runtime, bundle
and profile fingerprints in the run issue. Loopback counts as simulated. A
real-device criterion stays open until the owner records the run.

### Attended owner-channel and sleep run

`scripts/campaign-attended.py` (#1463, part of #804) runs A26 around an
actual sleep of the owner's Mac, with one real sandbox Slack delivery. It
splits A26 at its first `resume-*` step. Before the sleep it runs the
handled head and the forge moving while paused. It then sends one `ask`
through `mdstack notify` under a sandbox away record, starts builder #3 as
existing work, and snapshots the claims, worktrees and tmux windows. After
the wake it checks the snapshot is unchanged and takes the receipt code. It
then runs the resume steps: the missed head, red CI and one overdue sweep,
each caught up exactly once. The result holds the before-sleep and
after-resume timestamps, the sleep length and each owner unblock.

Rehearsal first, by the crew at any time, with no owner step:

```sh
python3 scripts/campaign-sandbox.py setup --root /tmp/att-r1 --run-id att-r1 \
  --production config.toml --source . --release "$RELEASE" \
  --sentinel "$OUTSIDE_FILE" --scenario A26
python3 scripts/campaign-attended.py /tmp/att-r1/state/manifest.json \
  --scenarios dev/tests/scripts/fixtures/campaign \
  --out /tmp/att-r1/state/attended.json --dry-run
python3 scripts/campaign-sandbox.py teardown /tmp/att-r1/state/manifest.json
```

Keep the root short: the tmux socket path must fit the OS limit. A dry run
posts to a loopback webhook and never sleeps. It prints and records
`rehearsal` and `evidence: false`, so it never counts as #804 evidence.

The owner's part, at a time agreed on #804 with no other lab journey
running on the Mac:

1. Before: create a Slack incoming webhook on a sandbox channel the live
   crew does not use. In the owner's own terminal, not a crew pane, run
   `export CAMPAIGN_WEBHOOK=<url>`. Never paste the URL into the tracker, a
   file or a crew window. The driver refuses a URL that is not https or that
   equals the live crew's own webhook.
2. Start: run the setup and driver commands above, without `--dry-run`,
   in that terminal.
3. Sleep: when the driver prints `owner: sleep this machine now`, choose
   Apple menu > Sleep, or close the lid. Stay asleep for at least `--gap`
   (default 60 s); 10 minutes is better. While asleep, read the receipt
   code from the Slack message on another device.
4. Wake: log in. The driver sees the wall-clock jump and asks for the code.
   Type it.
5. After: the crew posts the result's summary inline on #804, runs
   teardown and records the sentinel and retained-work checks.

Physical test boundary. The run proves:

- a real OS sleep of one Mac with every sandbox process suspended;
- the channel accepted the message and the owner read it on a device;
- the missed state and the overdue sweep catch up once after the wake;
- the claims, worktrees and windows survive the sleep.

It does not prove a forge that moves during the sleep: the forge is local,
and A26 moves it just before the sleep. Nor does it prove overdue time from
the sleep itself (A26 backdates the triage slot), delivery while asleep,
network or power loss, a second device or real GitHub (level b). The sandbox
uses its own profile and session. The live crew's profile is read only to
refuse its webhook; its channels and webhook are never used or changed.
