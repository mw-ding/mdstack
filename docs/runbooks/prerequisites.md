# Onboarding prerequisites

Onboarding module for what must be true before the target repo's install
starts, split out of the [onboarding runbook](../runbook-new-repo.md) under the
M26 modular organization principle
([#676](https://github.com/mw-ding/mdstack/issues/676)). It holds the opening
of the runbook's
[Prerequisites](../runbook-new-repo.md#prerequisites) and its
[Identities](#identities),
[Per-identity `gh` usage](#per-identity-gh-usage),
[Token scopes](#token-scopes),
[Shared state dir](#shared-state-dir) and
[Other prerequisites](#other-prerequisites) subsections, and the runbook's
command placeholder values in [Command values](#command-values), before
[Step 0: write, validate and render the profile](../runbook-new-repo.md#step-0-write-validate-and-render-the-profile).

## Prerequisites

Do not start until every item here is true. Record the evidence in the
checklist.

### Identities

The crew uses two GitHub accounts ([architecture.md](../architecture.md#identities)):

- **Author identity** `<author-login>`: used by the coordinator, builder and
  synthesizer. It pushes branches, opens PRs and merges.
- **Reviewer identity** `<reviewer-login>`: used by the reviewer-validator for
  formal `APPROVE` / `REQUEST_CHANGES` reviews, and by the coordinator for
  steering signals. GitHub refuses a verdict from the PR's own author, so this
  account must be a different one.

The author identity is normally the repo owner or an admin of the repo, because
steps 1, 3 and 4 need admin rights. Setup can also be done by any account that
has admin on the repo; it does not have to be one of the two crew identities.

### Per-identity `gh` usage

Several accounts are logged in to `gh` on the same box. Never switch the active
account (`gh auth switch`, `gh auth login`, `gh auth logout`). Select the
credential per command instead:

```bash
# act as the author identity
GH_TOKEN=$(gh auth token --user <author-login>) gh <command> ...

# act as the reviewer identity
GH_TOKEN=$(gh auth token --user <reviewer-login>) gh <command> ...
```

To run several commands as one identity in a shell, export it for that shell
only: `export GH_TOKEN=$(gh auth token --user <author-login>)`. Never print,
paste or commit a token value. Docs, wiring files, logs and evidence name the
mechanism only.

Check both identities exist on the box:

```bash
gh auth status
GH_TOKEN=$(gh auth token --user <author-login>) gh api user --jq .login
GH_TOKEN=$(gh auth token --user <reviewer-login>) gh api user --jq .login
```

### Token scopes

| Identity | Needs | Used for |
|---|---|---|
| `<author-login>` | `repo`; `workflow` only if workers may push files under `.github/workflows/`; `project` for Projects v2 | Branches, PRs, labels, merge, Project items |
| `<reviewer-login>` | `repo`; `project` if it updates the Project | Reviews, labels, steering signals |
| Whoever runs steps 1, 3 and 4 | Admin on the repo; `project` for step 3 | Labels, collaborators, Project, branch protection |

With fine-grained tokens the equivalents are: contents, pull requests and
issues read/write, metadata read, actions read, administration write for the
setup account, and the Projects permission on the owner.

Check the scopes of a classic token (the header lists them):

```bash
GH_TOKEN=$(gh auth token --user <login>) gh api -i user | grep -i '^x-oauth-scopes'
```

If `project` is missing for an identity, there are two options. Pick one and
record it in the wiring doc:

1. Add the scope to that identity: `gh auth refresh -h github.com -s project`.
   It needs a person at a browser to approve the device code, and it refreshes
   whichever account is active in `gh`. Do not switch the box's active account
   for this; have the account owner run it where that account is already
   active, or use option 2.
2. Do all Project operations as whichever identity already has `project`.
   (In the pilot, project operations ran as the reviewer identity while the
   author token lacked the scope.)

A GitHub Project is required for every crew repo. Resolve missing scope or
delegate Project operations before completing onboarding; skipping is not an
onboarding option.

### Shared state dir

All bots on the box share one directory per repo:
`<state-dir>/<owner>__<repo>/`. Create it once ([step 6](../runbook-new-repo.md#step-6-state-dir-and-wiring-doc)):

| Path | Holds |
|---|---|
| `claims/` | Per-pass claim files `<role>-pr<n>-<sha7>`, taken atomically, deleted after posting |
| `locks/merge.lock` | The synthesizer's serial-merge lock (`flock`) |
| `config.toml` | The profile this install was rendered from ([Step 0](../runbook-new-repo.md#step-0-write-validate-and-render-the-profile)) |
| `wiring.md` | The filled-in wiring doc for this repo |
| `reviewer-engines.md` | The reviewer's current engine choice |
| `sweeper-state.json` | The stuck-PR sweeper's dedup state |

It must be writable by every bot account on the box and must not live inside
any repo checkout. It holds no credentials.

### Other prerequisites

- The reviewer-validator can run a different engine from the builder
  ([roles.md](../roles.md#reviewer-engine-selection)). Private repos allow only
  Claude Code or Codex.
- The repo's required toolchain is known (for example the Node version and
  `COREPACK_HOME`), so builder and fix workers can pin it before any commit or
  push ([step 5](../runbook-new-repo.md#step-5-product-safety-checks) records it).
- A human owner is available to approve things bots cannot: accepting the
  invitation if the reviewer account is not scriptable, a missing token scope,
  and branch-protection choices.

### Command values

Every `<name>` in a command in the runbook and its modules is a value from
your resolved profile (`crew-config.py resolve` prints each key; `<owner>` is `repo.owner`,
`<author-login>` is `identities.builder.gh_user`, and so on, per the "Replaces"
column of [profile.md: Keys](../profile.md#keys)), except the few that come from
the output of the step using them, such as `<invitation-id>` (Step 2),
`<project-number>` (Step 3) and `<n>` (an issue or PR number). In every
command, `<owner>/<repo>` is the target repo.
