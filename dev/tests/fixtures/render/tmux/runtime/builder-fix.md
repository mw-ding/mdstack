# Builder fix procedure: <owner>/<repo> (tmux)

Read with the entry brief at its fix, ci-red, base-update or express trigger.
The entry brief’s ownership, live-state, signing, scratch and lifecycle rules apply.

Mechanical merges may use `mdstack merge-up` with the owned run, pinned head
and targeted checks; see `<mdstack>/docs/runtimes/tmux.md`, mdstack merge-up.

For a fix dispatched from a train, read the referenced train record (or
`$CREW_STATE/trains/train-*.json` on a new fix run). If this PR is a dropped
conflict with `merge_up=builder`, or on kind `merge-up`, merge the default branch, resolve the
conflict, and use the existing merge-up note and re-check; no rebase or force-push.
Kind `fix`: address each finding and any linked CI failure in the same fix,
capture the note's inline proof at the committed head, then push and at once post the
`🛠️ Ben · Fix · round <k> @ <sha7>` COMMENT review (`gh pr review <n> --comment --body-file <file>`) with its `pass=fix`
marker (§3). Kind `ci-red`: fix CI and post `🛠️ Ben · CI fix` the same way (round 0 before any
verdict); at the effective caps[1] limit write `blocked:` to escalate (§5).
For a new or changed guard, either note pastes the copyable fail-then-pass
control of protocol §3 Guard negative control as captured, not a sentence
saying the guard failed (#1884). Review of the new
head waits for that signed note with its proof or reasoned N/A; a push or `done:` alone starts
none (#1878). Then `done:` with the new head.

Express self-gate (`<mdstack>/docs/express-lane.md`): only when the newest
item record names `express` and the change carries `crew:express`. Pipe the
full diff paths at head, both rename paths included, to
`core/crew-config.py class-flavor --project "$CREW_PROJECT" --express`.
Lane `crew` (a tightening class match, a missing label or an unreadable
resolution) runs the crew lane as written. Lane `express` uses its
`selfgate_engine` (profile `different`) and runs this loop
after local checks pass, before the PR opens and after every later push:

1. Brief: write `.crew/selfgate-<sha7>.md` in the worktree with the issue's
   ACs, your stated intent, decisions and known risks, the full diff against
   the merge base and the effective knobs.
2. Review: start a fresh, read-only review sub-session in the engine's
   non-interactive form (roles.md How to run each engine, stdin closed),
   pointed at that file. Mode `different`: the first engine in your tier's
   `[engines]` order unlike every actual builder engine on the change,
   filtered as in roles.md Reviewer engine selection; with none left, wait,
   use the quota diversity waive record or fall back. Mode `same`: your own
   engine and model. Its rubric is the protocol §3 Review section (verdict;
   🔴 / 🟡 / 🟢 findings with `file:line` and the AC or claim each
   contradicts; AC coverage, design fit, correctness, tests, security, scope
   creep), the evidence-presence and AC-claim checks of an authorized
   validation skip, and the code-review skill the reviewer engine's harness
   adapter declares (`<mdstack>/docs/runtimes/harness-adapters.md`), if any.
   It returns a verdict and findings and never edits.
3. Fix 🔴 and 🟡 findings in your own context, rerun the affected checks and
   commit. A rejected finding gets a one-line reason, a deferred one a
   follow-up issue; 🟢 may be deferred without an issue.
4. Repeat from step 2 in a new sub-session until a review returns `pass`
   with no open 🔴, or effective caps[0] reviews ran at this head. After a
   passing self-gate, a CI-only fix or merge-up reviews only the new hunks.
5. Record: post the `🛠️ Ben · Selfgate · <pass|changes> @ <sha7>` COMMENT
   review (`gh pr review <n> --comment --body-file <file>`) with its `pass=selfgate` line per protocol
   §3 at the full head SHA, keyed `pr=<pr>`, or `issue=<issue#>` in place of
   `pr=` when `ids.marker_key` resolves `item` (protocol id keys). Then check
   it by piping `gh pr view <n> --json number,body,reviews,headRefOid,commits`
   into `scripts/crew-precheck.py --project "$CREW_PROJECT" --pass selfgate --item <issue#>`.

Fallback to the crew lane: the cap with a 🔴 still open (the record says
`verdict=changes`), a new sensitive or tightening match at head, or the
owner's ask. Give the reason in your next signed note, remove `crew:express`
from the PR and report `express-fallback` to the coordinator; never edit a
posted record.

Step summaries (`<mdstack>/docs/observe.md`): after each build, test or
lint run, and each fix attempt, append one step line with
`python3 <mdstack>/scripts/step-summary.py --root <worktree> --ref issue-<n>
--run-id build --step NAME --status ok|fail --duration SECS --outcome TEXT`.
It writes `<worktree>/.crew/runs/issue-<n>/build/summary.md`; in fix round
`<k>` use `--ref pr-<pr> --run-id fix-<k>`. Never add `steps/` logs.

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
