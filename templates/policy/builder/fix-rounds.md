<strategy:merge>For a fix dispatched from a train, read the referenced train record (or
<strategy:merge>`$CREW_STATE/trains/train-*.json` on a new fix run). If this PR is a dropped
<strategy:merge>conflict with `merge_up=builder`, or on kind `merge-up`, merge the default branch, resolve the
<strategy:merge>conflict, and use the existing merge-up note and re-check; no rebase or force-push.
<strategy:rebase>For a base-update conflict routed by <SynthesizerBot> (this backend has no trains),
<strategy:rebase>rebase onto the default branch, resolve the conflict, upload the result as a new head
<strategy:rebase>of the change, and use the existing merge-up note and re-check; earlier heads must
<strategy:rebase>stay readable, so never push to a ref that drops them.
Kind `fix`: address each finding and any linked CI failure in the same fix,
capture the note's inline proof at the committed head, then push and at once post the
`<title:builder/fix> · round <k> @ <sha7>` COMMENT review (`<op:markers.write>`) with its `pass=fix`
marker (§3). Kind `ci-red`: fix CI and post a `CI fix` note the same way (round 0 before any
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
`selfgate_engine` (profile `<flavor-selfgate-engine>`) and runs this loop
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
5. Record: post the `<title:builder/selfgate> · <pass|changes> @ <sha7>` COMMENT
   review (`<op:markers.write>`) with its `pass=selfgate` line per protocol
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

<include:docs/roles.md#pr-conventions>
