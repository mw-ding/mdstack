Verdict portability: apply protocol §7's full content, CI, live-gate and
merge-marker rules.

Gate-status reporting (diagnostic only; changes no gate or exemption):

- On every wake and sweep, for each open PR at the live head, collect ALL unmet
  applicable §7 items, including blocking holds, before returning blocked.
  Stop without posting for a closed/merged PR or a stale event SHA.
- Maintain one COMMENT review per PR, headed
  "<title:synthesizer/gate-status> · @ <sha7>", with the full current head marker
  <!-- crew:v1 role=synthesizer pass=gate-status pr=<n> sha=<head-sha> round=n/a verdict=n/a status=blocked -->
  List only unmet items below, with the concrete missing condition and who owes
  it. Split evidence presence from validation; list both if both are missing.
  Apply the existing gate's overrides and runtime exemptions before listing.

| Missing item | Who owes it |
|---|---|
| Approval at head / later changes request | <ReviewerBot>: review or fix verdict; <BuilderBot>: requested fixes |
| Validation at head | <ReviewerBot> (validator): validation verdict |
| Owner merge-ok | Owner, via <CoordinatorBot>: per-PR permission unless an existing grant applies |
| Blocking hold / escalation | <CoordinatorBot>: clear hold or route owner decision / dependency |
| Open rereview / engine disagreement | <CoordinatorBot>: request re-check; <ReviewerBot>: fresh verdict |
| Builder pre-review check | <BuilderBot>: fresh passing marker or reasoned N/A at head; owner via <CoordinatorBot>: per-change override |
| Required inline evidence | <BuilderBot>: inline proof validated at head or reasoned N/A |
| Runtime builder watch | <BuilderBot>: attach watch and post valid marker, only where required |
| Runtime mirror hold | <CoordinatorBot>: mirror, clean drift check and clear label, only where required |
| Tested with default branch | <SynthesizerBot>: <tested-update>; <BuilderBot>: conflicts |
| CI green / draft / mergeable / base | <BuilderBot>: failing checks or PR state; CI provider: pending checks |
| Linked tracker item | <BuilderBot>: link the issue unless exempt |

- Find the existing review by your identity and pass=gate-status marker across
  ALL heads, not by sha alone. Create with <op:review.post-narrative> only if absent;
  otherwise edit that review body in place with <op:markers.edit-status>.
  A gate-status marker never supplies approval, permission, a verdict or a round,
  and never triggers the section 6 pass-marker idempotency stop.
- When blocked, wake <CoordinatorBot> with the PR, head, review link and missing
  items (append blocked: #<n> <head-sha> gate-status REVIEW_URL to
  $CREW_STATUS +wait=CSV if only ci/review/validation/selfgate/train pend). Do not re-run evidence, tests, review or validation: inspect
  presence and verdict only. Repeated unchanged wakes reuse the same review.
- If no items remain, edit an existing gate-status review to "No unmet gate
  items at this head", status=clear and the current sha; do not create an empty
  review. Re-check §7 before landing; status=clear is not a merge signal.
