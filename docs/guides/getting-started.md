# Getting started

The one complete first run on the terminal (tmux) environment: from an
empty machine to your first merged PR. It owns the copyable config, the
identity choice, the first issue and the results to expect at each step.
Each step links to the doc that owns its exact behaviour, and the
[tmux binding](../runtimes/tmux.md) owns every command. Already running an
older install? Read the [migration guide](migration.md) first: 8.0.0 owner
commands take no `--project`.

## Before you start

- Python 3.11+, git, tmux and `gh` logged in as every login the config names.
- Two coding harnesses, logged in, such as Claude Code and Codex: the
  reviewer-validator's engine must differ from the builder's
  ([reviewer engine selection](../roles.md#reviewer-engine-selection),
  [harness adapters](../runtimes/harness-adapters.md)).
- A target repo you administer, cloned at `~/<repo>`, with a CI check that
  runs on every PR. Review starts on each new head, but the crew lands only
  on green CI ([Step 4](../runbook-new-repo.md#step-4-check-ci-and-branch-protection)).
- A machine and logins where you accept that role windows run any command in
  their worktree without asking (`permission_mode = "bypass"`, the default;
  [tmux prerequisites](../runbooks/tmux-onboarding.md#tmux-prerequisites)).

### Choose identities

| Choice | Config | Verdict | Merge permission |
|---|---|---|---|
| One account (the sample) | Every `gh_user` is your login | A signed COMMENT review, since GitHub refuses an author's own approval ([single-identity profile](../interfaces.md#single-identity-profile)) | Your merge-ok per PR, recorded by `ash` |
| Separate reviewer | `reviewer.gh_user` is a second account; drop the `[backends.review]` block | A real approval from that account ([identities](../runbooks/prerequisites.md#identities)) | The same per-PR merge-ok |

Either way nothing merges without a recorded owner merge-ok, unless you set a
standing [`merge_grant`](../configuration/runtime-options.md#tmux-options) in
the config. The rest of this guide uses one account.

## 1. Install

Download, verify and extract a release, then put `mdstack` on your `PATH`
([README: Install](../../README.md#install) steps 1 to 4):

```sh
~/.mdstack/releases/mdstack-X.Y.Z/cli/mdstack install
mdstack --version
```

Everything installed lives under `~/.mdstack/`; only your checkout is outside
([home-level layout](../runtimes/tmux.md#home-level-layout-1178)). Later
releases upgrade in place with `mdstack upgrade --version vX.Y.Z` (or
`--latest`); the previous tag rolls back ([update path](../release.md#update-path)).

## 2. Write the config

Owner commands read `$MDSTACK_CONFIG`, else `~/.mdstack/config.toml`. Set the
three values, then paste the block; it writes the
[tmux sample](../../profiles/tmux.toml) with your values filled in:

```sh
OWNER=<owner> REPO=<repo> LOGIN=<your-login>
cat > ~/.mdstack/config.toml <<EOF
[repo]
owner = "$OWNER"
name = "$REPO"
default_branch = "main"

[runtime]
name = "tmux"
options = { permission_mode = "bypass" }

[backends.review]
name = "github"
capabilities = { post-verdict = "emulated (COMMENT-review verdict + recorded owner merge-ok)" }

[identities]
owners = ["$LOGIN"]
coordinator = { gh_user = "$LOGIN", name = "Ash" }
builder = { gh_user = "$LOGIN", name = "Ben" }
reviewer = { gh_user = "$LOGIN", name = "Vera" }
synthesizer = { gh_user = "$LOGIN", name = "Sam" }
researcher = { gh_user = "$LOGIN", name = "Riley", title = "Researcher", emoji = "🔬" }

[paths]
root = "~/.mdstack"
state_dir = "state"
worktree_root = "runs/$REPO"
live_dir = "live"
mdstack = "state/${OWNER}__$REPO/mdstack"
checkout = "~/$REPO"
toolchain_bin = "$(dirname "$(command -v gh)")"
EOF
python3 ~/.mdstack/releases/current/core/crew-config.py resolve --project ~/.mdstack/config.toml | grep -c '<'
```

Expect `crew-config: OK (layers: core, default, project)` on stderr and a
count of `0`: no `<placeholder>` is left in any resolved key. `resolve`
layers your file over the default profile; `validate` checks one file alone,
so it reports this short file's inherited keys as missing. Every key:
[profile.md: Keys](../profile.md#keys).

## 3. Prepare the repo and the harnesses

```sh
mdstack doctor --fix --milestone M1
```

It creates the state directories, the `crew:*` labels and an open `M1`
milestone, and invites a separate reviewer; CI and branch protection stay
yours ([mdstack doctor](../runtimes/tmux.md#mdstack-doctor)). It also needs
two working engines. Fix each `fail` row and rerun it; the `mdstack link`
warning clears at bootstrap. Then trust each harness
once: run `claude` in `~/<repo>`, pick `Yes, I trust this folder` and `/exit`;
trust every hook in your host Codex config in plain `codex`
([tmux prerequisites](../runbooks/tmux-onboarding.md#tmux-prerequisites)).

## 4. Bootstrap

```sh
mdstack bootstrap --dry-run
mdstack bootstrap --yes
mdstack layout --write
```

Review the dry run first. Expect `crew bootstrap: dry-run; no install
written`, then `crew bootstrap: installed <path>/install.json`. Bootstrap
records the profile and install and renders the briefs; it starts no role
([profile install](../runbooks/profile-install.md)). `layout --write` adds the
`~/.mdstack/start` wrapper.

## 5. Start the crew

```sh
mdstack start
```

It starts one tmux session with the coordinator `ash` (window 0) and the
builder and reviewer leads, then attaches to window 0; run it again to
reattach ([mdstack start](../runtimes/tmux.md#mdstack-start)). A Claude Code
`ash` first waits at its folder-trust dialog: accept it there (never a blind
Enter, which picks `No, exit`). Detach with the tmux prefix and `d`;
`mdstack status` then shows `ash` and both leads `alive`.

## 6. First issue

```sh
mdstack bootstrap --smoke --yes
```

It opens a docs-only issue (add `docs/crew-smoke-test.md`) labelled
`crew:ready` and assigned to the builder login, once per install
([bootstrap Q7](../bootstrap.md#q7-self-test)). For your own work, open an
issue with numbered acceptance criteria, label it `crew:ready` and assign it,
or ask `ash` in window 0 to file one.

## 7. From issue to merged PR

Watch with `mdstack status` and `mdstack attach <window>` (read-only without
`--rw`). Expect, in order:

| Stage | What you see |
|---|---|
| Build | A `ben-<issue>` window opens; a PR that closes the issue appears, labelled `crew:in-review`, with acceptance evidence and a changelog note |
| Review | A `vera-<pr>-r1-review` window posts `Vera · Verdict · round 1 @ <sha7>` at the head; on a pass the PR gets `crew:approved`. Changes requested bring a fix round in the same `ben-<issue>` window, capped ([protocol §5](../protocol.md#5-rounds-and-escalation)) |
| CI | Your check runs on every head; the land waits for it to be green at head |
| Permission | `ash` asks for your merge-ok on the PR and in window 0. Run `mdstack attach ash --rw` and say `PR <n> has my merge-ok`; `ash` records it at the full head SHA |
| Merge | `sam` re-checks every [merge gate](../protocol.md#7-merge-gate-synthesizer) and squash-merges; `ash` closes the issue, clears the `crew:*` labels and the item's windows |

Confirm with `gh pr list -R <owner>/<repo> --state merged --limit 1`. Stop the
crew with `mdstack down`.

If it stalls: a window `ambiguous` or a dialog, harness exits and stuck
queues are in [tmux troubleshooting](../runbooks/tmux-onboarding.md#tmux-troubleshooting);
an item labelled `crew:needs-md` or `crew:escalated` waits for your answer in
window 0; resume an escalated PR with a `/crew resume` comment
([protocol §9](../protocol.md#9-steering-crew-commands)).

## Talk to the team head

`ash` holds the `cto` seat and is the one role that faces you; every other
role escalates to it ([role classes](../roles-registry.md#role-classes)).
Talk live with `mdstack attach ash --rw`, on the tracker through issues, or
by `/crew` commands on a PR.

## Add an on-demand role

A role whose definition has a [`lifecycle`](../roles-registry.md#lifecycle)
with the `manual` wake starts on `mdstack up <role>`, one instance per call
up to its `max`; the engineering roles have none, so `up <role>` refuses them
(exit 2). New roles: [Adding a role](../roles-registry.md#adding-a-role).

## Next

- Identities, engines, repos, concurrency and rigor, by task:
  [configuration guide](configuration.md).
- Pick tools other than GitHub, or add a knowledge source:
  [configuring connectors](connectors.md).
- Rigor per project or item: [flavors](../flavors.md).
- Upgrade, recover or relocate: the [runbook](../runbook.md).
