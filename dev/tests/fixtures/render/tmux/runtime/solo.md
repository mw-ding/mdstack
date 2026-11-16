# Solo session brief: <owner>/<repo> (tmux)

Flavor: standard; review=thin; validation=behaviour; evidence=typed; caps=[3, 3]; merge=docs; builder=crew.
One owner-driven session builds and fixes this item. Fill in the issue number,
worktree, acceptance criteria and actual engine/model/effort before starting.
Read the live issue and PR, the repo's `AGENTS.md`, and
`<mdstack>/docs/protocol.md`. Adopt any open PR closing the issue.

Mark the issue and PR `crew:solo`. This skips builder dispatch, B2 watches,
merge-up and fix delivery to builder windows. Findings and red CI are posted
on the PR for this session to pick up. No builder claim or inbox is required.
The reviewer uses a different engine from this session; the synthesizer alone
squashes under §7. Keep the floor F1–F7, holds, CI, inline mutation evidence
and the existing merge permission rules.

Before work and each push or post, run
`<mdstack>/cli/mdstack ownership --project "$CREW_PROJECT"` (add `--action write`
for pushes and posts). Set `CREW_PROJECT` to the installed project's absolute profile path.
On refusal, read/report only. Pin `PATH` with `<toolchain-bin>` and work only
in the supplied worktree on `builder/<n>-` plus a short slug.
Add `-R <owner>/<repo>` to every `gh` command except `gh api`.
Use local `.crew/` files for drafts and logs. Run the repo's CI checks before
pushing; never download tools, bypass quarantine or use a mirror registry.
Report unavailable checks in PR evidence and leave those checks to CI.

Open a non-draft PR with the contract below and label it `crew:in-review`.
Handle findings, red CI and merge conflicts in this same session. Use a merge
commit for updates from `main`; never force-push a shared branch.
After each fix, post its head-pinned fix note. Never merge or self-approve.

## PR conventions

- **Branch:** `<role>/<issue#>-<short-slug>`, for example
  `infra/187-align-rust-base-images`; tooling routes follow-ups by it.
- **Commits:** one PR per issue, in logical commits that pass their tests.
  Follow repo convention; end each with `Engine: <engine> <model> <effort>`,
  the engine that actually wrote it (Actual builder engine).
- **Evidence:** for behaviour changes, embed runtime proof inline in the body
  or signed fix / ci-fix reviews (verification); never
  commit evidence. Docs-only PRs state N/A and why.
- **Pre-review check:** when enabled in the profile, follow the ordered steps, bounded fixes and
  `pass=precheck` schema in the protocol
  before handoff. For infra changes, confirm safety before anything is applied.
- **PR:** `gh pr create` with a detailed body, never `--fill`. Add the PR to the
  project board if there is one, and link the issue.
- **Never** merge, approve your own work, or force-push a shared branch.

### PR body template

The signature must be the last thing in the body. Use the real values
actually used, including any fallback, never placeholders.

````markdown
## Context

<why this change is needed>

Closes #<issue#>

## Changes Made

- `<path>`: <what changed and why>

## Testing Done

- <each test, and the scenario it confirms>

## Test Output

~~~text
$ <command>
<key output lines>
~~~

---
<!-- crew:v1 role=builder issue=<issue#> tier=<tier> engine=<engine> model=<model> -->
*Built by <role>-<tier> (<engine>, <model>, <effort>)*
````

Crew PRs must carry the hidden `crew:v1` builder marker line right before the
signature (architecture overview). See the
stage protocol for the other crew additions: `## Acceptance Evidence`
(with the shape and inline proof label per the verification protocol)
and `## Risks / Not Done`. Test Output and Acceptance Evidence must paste key
output and/or screenshots inline; paths and repo-file links do not count. A
behaviour-changing PR that adds or
changes a user-visible create, update or complete (or equivalent) mutation
pastes a create→complete→delete happy-path snippet (for list delete with
cascade, also show the child items are gone); see
protocol §3.

### Fix note (crew and solo builders)

After addressing findings and linked CI, push, then post a COMMENT review
titled `… · Fix · round <k> @ <sha7>` (§4). For a CI-only fix use `CI fix` and
`pass=ci-fix`; before any verdict, its round is 0.
List findings addressed, commands and inline proof, unresolved risks, and the
actual engine/model/effort. Keep the body of the original PR unchanged.

```text
<!-- crew:v1 role=builder pass=fix pr=<n> sha=<head-sha> round=<k> verdict=n/a engine=<engine> model=<model> effort=<effort> -->
<BuilderSignature> · <harness> · <model>
```

Include a dated CHANGELOG fragment with the PR number and box-skill mirror
status according to the repo's contributing rules. Record the mirror status
in the PR too. Recheck sensitive classification after every push and carry
the issue's sensitive label. Only a recorded owner override clears it.
