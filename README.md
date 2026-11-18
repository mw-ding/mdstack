# mdstack

mdstack is a versioned, reviewed rulebook for running a GitHub repo with a
small crew of bots. Each bot has one job: coordinate, build, review and
validate, or merge. Together they take an issue from spec to merged PR with
CI, evidence and a human-readable trail at every step. It exists because
"let an AI write code" falls apart without clear roles, gates and a record of
who did what; this repo writes those rules down and keeps them testable.

New here? Start with the [Quickstart](#quickstart-tmux): zero to a running
tmux crew in seven steps. Adopting the crew or running a role? The
[reading paths](docs/reading-paths.md) show what each role reads and when.
Changing this repository itself? Follow [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

A coordinator turns a spec into issues with numbered acceptance criteria. A
builder picks each issue up and opens a PR with evidence. CI runs. A reviewer
and validator, a different identity from the author, post a verdict. When the
gate passes, the synthesizer merges and the coordinator closes out. Loops are
capped, and every handoff is a marker on the PR.

- How it fits together: the canonical
  [deployment, wake and release diagram](docs/architecture.md#deployment-wakes-and-releases)
- Stages, markers, rounds and the merge gate: [docs/protocol.md](docs/protocol.md)
- Roles, tiers and engines: [docs/roles.md](docs/roles.md)

## Who it's for

- Maintainers who want bots to build and review changes in their repo without
  giving up a merge gate.
- Engineers adopting the crew on a new repo, via the
  [onboarding runbook](docs/runbook-new-repo.md).

## What you get

- A staged protocol with typed evidence, review rounds and a merge gate.
- Routine and listener templates per role, with placeholders only
  ([templates/](templates/README.md)).
- A seed README for product repos ([templates/product-readme.md](templates/product-readme.md)).
- Guard scripts that scan for secrets and check docs and links in CI.
- A lessons log and a changelog of every change.
- Versioned releases of the installable parts: what ships, how it is
  versioned and what each version promises is in
  [docs/deliverables.md](docs/deliverables.md); how a release is cut is in
  [docs/release.md](docs/release.md). Install a tagged version from
  [GitHub Releases](https://github.com/mw-ding/mdstack/releases), as in
  [Install](#install).

## Quickstart (tmux)

Zero to a running local crew. Each step links to the runbook for depth;
the [tmux binding](docs/runtimes/tmux.md) owns every command's exact
behaviour. `<repo>` is your target repo, cloned at `~/<repo>`, `<mdstack>`
the extracted bundle under `~/.mdstack/releases/`, and `mdstack` below is
the launcher [Install](#install) step 5 puts on your `PATH`. Everything installed lives in `~/.mdstack/`; only
the checkout is outside it
([home-level layout](docs/runtimes/tmux.md#home-level-layout-1178)). Coming
from 6.x or older? 7.0.0 is a fresh install
([migration](docs/guides/migration.md)).

1. **Install and verify** the release bundle: [Install](#install) steps 1 to 5.
2. **Write `config.toml`** at `~/.mdstack/config.toml`, the user-level
   config every command uses with no profile flag, from
   [profiles/tmux.toml](profiles/tmux.toml) plus `[repo]` (its default
   `[paths]` block already names the `~/.mdstack/` layout)
   ([Set up the target repo](docs/runbook-new-repo.md#set-up-the-target-repo)),
   then check it:
   `python3 <mdstack>/core/crew-config.py validate ~/.mdstack/config.toml`.
   Create the `crew:*` labels
   ([Step 1](docs/runbook-new-repo.md#step-1-create-the-crew-labels)) and
   make sure a CI check runs on every PR.
3. **Bootstrap:** `mdstack bootstrap --dry-run`;
   review it and run it again without `--dry-run`
   ([Bootstrap](docs/runbook-new-repo.md#bootstrap-recommended)).
4. **Start:** `mdstack start`, from any directory. It runs `mdstack up`,
   which renders the briefs and starts the session with `ash` and the
   enabled leads (table below), then attaches this terminal to window 0;
   run it again later to reattach
   ([mdstack start](docs/runtimes/tmux.md#mdstack-start)).
5. **Trust, once, per harness.** A Claude Code `ash` waits at its
   folder-trust dialog (`mdstack status` shows `ambiguous`): run
   `mdstack attach ash --rw` and accept it; never press a blind
   Enter, which picks `No, exit`. That one answer covers the role worktrees.
   Codex windows are pre-trusted per process, but `mdstack up` refuses until
   every hook in your host Codex config is trusted once in plain `codex`.
   Pi, Cursor and Muse: see each
   [harness adapter](docs/runtimes/harness-adapters.md)'s trust row.
6. **First issue:** open an issue with numbered acceptance criteria, label it
   `crew:ready` and assign it, or ask `ash` in window 0 to file one. `ash`
   hands it to the builder lead and the pipeline runs; you give the merge-ok
   ([Owner duties](docs/runbook-new-repo.md#run-the-crew)).
7. **Watch and stop:** `mdstack status` (one row per window with its
   liveness), `mdstack attach <window>` (read-only without `--rw`), and
   `mdstack down` to stop every window
   and the session. Problems:
   [tmux troubleshooting](docs/runbook-new-repo.md#tmux-troubleshooting).

### Bringing up the team

Default profile names; window indexes from the
[tmux binding](docs/runtimes/tmux.md#layout-and-naming). See any window with
`mdstack status`, and look or type with `mdstack attach <window>` (`--rw` to type).

| Role | Window | Started by |
|---|---|---|
| Coordinator | `ash` (0) | `mdstack up` |
| Builder lead | `ben-lead` (2) | `mdstack up`, unless the [launch topology](docs/runtimes/tmux.md#launch-topology) or `--coordinator-only` says otherwise |
| Reviewer lead | `vera-lead` (3) | `mdstack up`, same exception |
| Builder | `ben-<issue>` (10–19) | The builder lead, when `ash` hands it a ready issue and the scheduler admits it; fix rounds reuse the window |
| Reviewer-validator | `vera-<pr>-r<k>-<pass>` (20–29) | The reviewer lead, one fresh window per pass: review on each new head (CI pending or red included), validate after a passed review when the flavor requires it, recheck on its handoff. Green CI gates the merge, not the review |
| Synthesizer | `sam` (1) | `ash`, with `mdstack spawn synthesizer` at the first land; it then stays for the session |
| Researcher | `riley-<issue>`, `riley-sweep` or `riley-docs` (40–44) | `ash`, per research request, triage sweep or docs pass; closed after its `done:` |

## Install

1. **Needs:** Python 3.11+, and `gh` logged in (it downloads the release;
   the repo is public, so the assets are also on the
   [Releases](https://github.com/mw-ding/mdstack/releases) page). The tmux
   runtime also needs tmux.
2. **Download and verify** the latest release (to pin a version, pass its
   tag: `gh release download vX.Y.Z ...`):

   ```bash
   gh release download -R mw-ding/mdstack --pattern 'mdstack-*.tar.gz' --pattern SHA256SUMS -D mdstack-release
   cd mdstack-release && shasum -a 256 -c SHA256SUMS  # Linux: sha256sum -c SHA256SUMS
   ```

3. **Extract** into the home root:
   `mkdir -p ~/.mdstack/releases && tar -xzf mdstack-*.tar.gz -C ~/.mdstack/releases`. The `mdstack-<version>/`
   directory is `<mdstack>` in the runbook, and its `VERSION` file
   (`cat ~/.mdstack/releases/mdstack-<version>/VERSION`) is the version to record
   ([release.md: Update path](docs/release.md#update-path)).
4. **Check the tools run:**
   `python3 ~/.mdstack/releases/mdstack-<version>/core/crew-config.py validate ~/.mdstack/releases/mdstack-<version>/profiles/default.toml`
   and `~/.mdstack/releases/mdstack-<version>/cli/mdstack --help`.
5. **Put `mdstack` on `PATH`:**
   `~/.mdstack/releases/mdstack-<version>/cli/mdstack install`. It points
   `~/.mdstack/releases/current` at that bundle, writes the launcher
   `~/.mdstack/bin/mdstack` and links it into a user directory already on
   your `PATH` (for example `~/.local/bin`), or prints the one line to add to
   your shell profile; it never edits one. `mdstack --version` then prints
   the tag.
6. **Next:** write `~/.mdstack/config.toml` and continue at the runbook's
   [Step 0](docs/runbook-new-repo.md#step-0-write-validate-and-render-the-profile)
   (Grok Bot) or its [tmux runtime](docs/runbook-new-repo.md#tmux-runtime)
   section. Upgrades follow [release.md: Update path](docs/release.md#update-path):
   `mdstack upgrade --version vX.Y.Z` (or `--latest`) fetches, verifies and
   re-renders, then moves `releases/current`, so the launcher follows with no
   `PATH` change; the previous tag rolls back.

The `v2.0.0` bundle lacks a file the install CLI needs, so step 4 fails on it;
use a release with the [#275](https://github.com/mw-ding/eng-crew/issues/275) fix.

tmux users upgrading to 2.1: read the "Upgrade note (2.1)" entry in the
[release notes](https://github.com/mw-ding/mdstack/releases) and the
runbook's [tmux prerequisites](docs/runbook-new-repo.md#tmux-prerequisites).

## Status

Release and work status are recorded here:

- Shipped versions and their notes:
  [GitHub Releases](https://github.com/mw-ding/mdstack/releases).
- Work in progress and done:
  [open milestones](https://github.com/mw-ding/mdstack/milestones) and
  [closed milestones](https://github.com/mw-ding/mdstack/milestones?state=closed).
- Every change: [CHANGELOG.md](CHANGELOG.md). Per-slice status:
  [docs/specs/portable.md](docs/specs/portable.md) §5.
- Platform merge enforcement and its limits:
  [docs/merge-enforcement.md](docs/merge-enforcement.md).

M51 personnel delivery is built in source (PR #1805); its team/project
routing design and approved T1–T4 breakdown landed in PR #1802; M56
later built T1–T4 (below)
([M51 status](docs/specs/portable.md#m51-personnel-boundary-and-team-routing-design)).
These landed after the 7.11.0 cut; they do not imply a released personnel
bundle or live host adoption. M51 closes after status sync #1790 lands.

M52 completion routing is built in source: the policy-only idle exception
(PR #1804) and signed posted-round verdict wakes (PR #1803) have landed
([M52 status](docs/specs/portable.md#m52-completion-routing)). Its opening
spec and both build issues are closed; M52 closes after status sync #1799
lands. No release containing M52 has shipped: v7.11.0 predates these changes,
and source completion does not imply a live installation.

M53 brief headroom and grant lifecycle is built in source: bounded grant
references (PR #1826), builder/researcher entry headroom (PR #1825), the
24-card learning batch (PR #1824) and owner-confirmed grant pruning
(PR #1833, after the owner's proofs A and B). All member issues are closed;
M53 closes after status sync #1815 lands
([M53 outcome](docs/specs/portable.md#m53-outcome-and-lessons)). v7.12.0
ships all of these except pruning, which landed after that cut and is in no
release yet.

M54 coordinator helpers are built in source: issue briefs and checked acks
(PR #1834), review/verdict/recheck commands (PR #1838), owned merge-ups
(PR #1837), and coordinator scratch cleanup (PR #1831). All four build
issues are closed; M54 closes after status sync #1820 lands
([M54 outcome and brief sizes](docs/specs/portable.md#delivered-outcome-and-lessons)).
They landed after the 7.12.0 cut and establish no live installation.

M55 runtime routing repairs are built in source: dispatcher-owned typed
waits for held reviewer requests (PR #1865), a `merge-ok-recorded` wake for
the synthesizer (PR #1867) and item tiers carried through every spawn
(PR #1868), plus one learning record (PR #1852). All member issues are
closed; M55 closes after status sync #1848 lands
([M55 outcome](docs/specs/portable.md#m55-outcome-and-lessons)). All three
repairs landed after the 7.12.0 cut and are in no release yet.

M56 team/project routing is built in source for the terminal runtime:
closed project context and qualified routing (PR #1866), one team
admission ledger (PR #1875), shared team leads and worker lifecycle
(PR #1876) and repo-bound landing (PR #1877), on the opening spec
(PR #1863). All member issues are closed; M56 closes after status sync
issue #1860 lands ([M56 outcome](docs/specs/team.md#m56-outcome-and-lessons)).
The proof is isolated (disposable repos, fake backends); none of it is in
a release yet, and it shows no live team adoption.

M57 delivery, campaign and shared status is built in source: review
readiness on the published builder record (PR #1904), busy-worker delivery
(PR #1906), relay disposition (PR #1909), `mdstack up --attach` (PR #1894),
per-scenario campaign files (PR #1897), opt-in shared status for
independent crews (design PR #1896, build PR #1905) and six lessons. All
member issues are closed; M57 closes after status sync #1890 lands
([M57 outcome](docs/specs/portable.md#m57-outcome-and-lessons)). None of it
is in a release: v7.13.0 predates every unit. Installation is a separate
step; no live shared-status registration or terminal adoption is claimed.

M59 native owner entry is built in source: `mdstack start`, one
start-or-reattach command from any directory, with `<home>/start` delegating
to it (PR #1930), on the opening spec (PR #1928), plus four lessons carried
in from M57. All member issues are closed; M59 closes after status sync #1926
lands ([M59 outcome](docs/specs/portable.md#m59-outcome-and-lessons)). None
of it is in a release: v7.14.0 predates every unit. Installation is a
separate step; no terminal adoption is claimed.

M60 lessons indexing, triage hardening and cleanup is built in source: a
lessons index generated from each lesson's metadata (PRs #1943 and #1949),
one triage write allowlist at one apply entry point (PR #1944), readable
emoji-led post titles (PR #1951), a verdict summary card (PR #1953) and a
bare `mdstack attach` (PR #1954), on the opening spec (PR #1940), plus one
lesson; the orphan inventory found nothing to delete. All member issues are
closed; M60 closes after status sync #1937 lands
([M60 outcome](docs/specs/portable.md#m60-outcome-and-lessons)). None of it
is in a release: v7.15.0 predates every unit. Installation is a separate
step; no live apply-mode sweep or terminal adoption is claimed.

M61 team ergonomics is built in source: `mdstack up --team` adds or removes a
repo on a running team without a restart (PR #1975), and the owner CLI takes
no `--project`, using the installed team and `--repo <key>` (PR #1976), on
the opening spec (PR #1974). All member issues are closed; M61 closes after
status sync #1973 lands
([M61 outcome](docs/specs/portable.md#m61-outcome-and-lessons)). None of it
is in a release: v7.16.0 predates every unit. Installation is a separate
step; no live hot-add or owner-shell adoption is claimed.

Content is built by the crew itself through the normal PR pipeline; every
change is recorded in `CHANGELOG.md`.

## More

- Specs: [docs/specs/team.md](docs/specs/team.md) (module layout, four
  axes, dependency rules), [docs/specs/portable.md](docs/specs/portable.md)
  (invariants, extension mechanism) and
  [docs/specs/framework.md](docs/specs/framework.md) (original requirements
  R1–R8)
- Adopting or running a role: [reading paths](docs/reading-paths.md) ·
  every doc: [docs index](docs/README.md)
- Lessons log: [docs/lessons/](docs/lessons/README.md)
- Changes: [CHANGELOG.md](CHANGELOG.md) · Contributing to this repository:
  [CONTRIBUTING.md](CONTRIBUTING.md)
- No secrets or tokens are ever committed here. Per-repo specifics are templates
  with placeholders.
