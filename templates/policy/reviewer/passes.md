1. Re-read the PR live (`<mdstack>/docs/protocol.md` §6 step 1). If the head
   is not Base, or the PR is closed, merged or escalated, or has `crew:hold`,
   report
   `$CREW_BIN action report --status done --ref '#<n>' --ref stale`
   and exit. Pin diff, CI and verdict reads to Base; if the head moves
   mid-pass, discard them and report stale. If docs this brief cites are unreadable, append
   `blocked: #<n> spec-unreadable` and exit. Rigor comes only from flavor
   records and path classes; report an unrecorded brief floor as
   `flavor-unrecorded`. Stop the same way if this
   pass already has a marker at head for round `<k>` (§6 step 2); a marker
   from an earlier round at the same head does not count. A coordinator
   `pass=steer cmd=rereview sha=<head-sha>` posted after that marker
   overrides the existing-marker stop: do the requested fresh pass at head.
   For `recheck`, use the final `pass=verdict` marker for this duplicate check.
   Before any pass or intake-start ack, apply protocol's builder pre-review
   gate when `builder.precheck.enabled` resolves true. Check the live body
   and builder-signed reviews with `<mdstack>/scripts/crew-precheck.py`, passing
   `--item <issue#>` when the PR closes exactly one issue; missing, stale,
   malformed, other-item or failed results block. Check inline N/A reasons. Only recorded
   owner per-change merge-ok at head waives this gate, never standing grants.
   On failure append `blocked: #<n> precheck` and exit without a verdict round.
2. Your engine must differ from every `Engine:` trailer on the PR (invariant
   I2, `<mdstack>/docs/roles.md`); if not, write `blocked: #<n> engine` and
   exit.
3. Intake ack, on a `review` pass for round `<k>` = 1 only (never the
   `validate` pass or a later round). After steps 1 and 2, and unless the PR is
   a draft or the live PR already has a `pass=ack` marker at this head, whatever
   its title (so a respawned pass posts nothing), post one
   COMMENT review `<title:reviewer/ack> · intake @ <sha7>` (`<op:markers.write>`)
   saying review has started at this head, with the marker
   `<!-- crew:v1 role=reviewer-validator pass=ack pr=<n> sha=<head-sha> round=n/a verdict=n/a -->`
   (the `pr-opened` ack, §6). Post it before the review work, so the PR shows
   the pickup. It is narrative only: no round, no verdict, no state tag change,
   and never an approval.
4. On `recheck`, do the §6 merge-up light re-check in this one fresh session:
   verify Base has exactly two parents and the first parent is the previous
   approved head; re-read its latest verdict and keep that approval's round
   `<k>`. Check that the second parent belongs to `<default-branch>`.
   Inspect only the conflict-resolution hunks with
   `git show --remerge-diff --format= Base` (replace Base with the run's SHA).
   Empty output is the clean update-branch fast path: go straight to rerunning
   the acceptance checks at Base. Do not review the whole PR again.
   If the merge or prior approval cannot be confirmed, an open rereview steer
   requires full review, or resolution changes behaviour or content beyond a
   mechanical merge, post no verdict; append
   `done: #<n> <head-sha> recheck escalate` and exit. The coordinator starts
   normal review and validation at this head.
   Otherwise write both Review (hunk check) and Validation (rerun checks)
   sections, with their own `pass=review` and `pass=validate` markers per §3.
   Record observed CI as information only; independently reproduced failures
   produce `verdict=changes`, and a pass requires both sections to pass.
   Save both sections to the `recheck` verdict file (step 5), re-read live
   state and ownership before posting, and post one COMMENT review
   `<title:reviewer/verdict> · round <k> (merge-up re-approve)` (`<op:markers.write>`)
   with both sections and the final `pass=verdict` marker from step 6 at Base.
   For failed acceptance checks use the normal changes verdict header instead.
   Set the state tags as in step 6, then append
   `done: #<n> <head-sha> recheck <pass|changes>` and exit; no separate
   validation session runs. Every §7 merge gate still applies at the new head.
   On a multi-commit `review`, read the round's commits in order and judge
   the combined diff at head (§3 Review section).
   When a `review` changes what a shutdown or scratch cleanup removes,
   keeps or refuses, read the runtime state-file row its allocation
   names beside the command and its retention and refusal tests; a row
   still describing the old behaviour is a missing allocated path.
   On other passes, do the pass per §3: `review` writes the Review section, `validate` runs
   its own checks in the worktree and writes the Validation section, each
   with its own literal section marker (choose `pass` or `changes`):

   ```text
   <!-- crew:v1 role=reviewer-validator pass=review pr=<n> sha=<head-sha> base=<reviewed-base-sha> round=<k> verdict=<pass|changes> -->
   <!-- crew:v1 role=reviewer-validator pass=validate pr=<n> sha=<head-sha> base=<reviewed-base-sha> round=<k> verdict=<pass|changes> -->
   ```

   On `validate`, the scope is the effective `validation_scope` knob,
   resolved live with the other knobs (render baseline
   `<flavor-validation-scope>`). `bounded`, the default: run the issue's
   acceptance checks and only the checks that cover the files changed in the
   full diff at head: the configured test command <precheck-test>, limited
   to those paths (if `n/a`, only the tests the repo's `AGENTS.md` names for
   those paths). Run no repo-wide check under `bounded`. `repo`, only when
   the flavor or a class rule sets it: also run the configured lint
   <precheck-lint> and test <precheck-test> commands over the whole repo (if
   `n/a`, the repo-wide checks `AGENTS.md` names). Cite green PR CI at head for the full
   suite instead of rerunning it locally. Red or missing CI at
   head is reported as the CI gate, never "fixed" by a local full run. The
   Validation section lists the tests run, why they cover the changed files,
   and the CI state and link at head. Re-run each CLI repro pair at head and
   diff it; a named test command is the pair for a command that only runs
   against test fakes (verification Q2).
   A CLI, service or API capture without the `evidence-cli.py` or template
   script header line (`Proof R1 · ... · sha ... · cwd ...`), or whose
   `sh` block does not reproduce at head, is one finding; paste your exact
   re-run output (preferably from `<mdstack>/scripts/evidence-cli.py`) in it.
   Apply verification Claim scope: a claim wider than its read, or a
   fail-closed tool proved only by a function return, is `disagrees`.
   Replay each guard's negative control (protocol §3); a missing one is
   `disagrees` under `evidence = typed`, a 🟡 under `inline`.

   Round `<k>` per §5.
   Start on the new head without waiting for CI. Record the CI state observed
   (pending, red or green) as information only in either section; CI state
   alone never fails an acceptance criterion or changes the verdict. Judge
   independently reproduced failures normally. CI green at head remains a
   synthesizer merge gate (§7), including after a light merge-up re-check.
   For a CI fix after approval, inspect the fix hunks and rerun acceptance
   checks in fresh review and validation sessions (§6); use the approval's
   round number. Broader behavioural edits require normal review.
5. Write the section to the verdict file
   `<state-dir>/<owner>__<repo>/verdicts/pr<n>-<sha7>-r<k>-<pass>.md`. Keep
   the `review` file until the PR merges, closes or the head moves, including
