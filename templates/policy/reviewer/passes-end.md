   at the same head, reuse it; a full `cmd=rereview` still runs both passes.
6. The `validate` pass, after writing its own section, reads the `review`
   file (missing: `blocked: #<n> review` and exit) and posts one COMMENT
   review `<title:reviewer/verdict> · round <k> @ <sha7>` (`<op:markers.write>`)
   with both sections and a final marker
   `<!-- crew:v1 role=reviewer-validator pass=verdict pr=<n> sha=<head-sha> base=<reviewed-base-sha> round=<k> verdict=<pass|changes> -->`;
   `pass` only if both sections pass. Every verdict body opens with the
   advisory summary card (§4) from `<mdstack>/core/summary-card.py`
   (`mdstack verdict` adds it). A `review` pass that says `changes`
   posts that verdict itself, with the Review section only and
   `verdict=changes`; no validation runs (§2 step 6). One identity: never a
   formal review. Changes at effective caps[0] (maximum 3) escalate per §5.
   Before posting, check the assembled verdict body has exactly three
   `pass=` markers: `pass=review`, `pass=validate` and `pass=verdict`; a
   review-only `changes` body has exactly two: `pass=review` and
   `pass=verdict`. Each marker must name this PR, full head SHA and round,
   and its actual result. If the check fails, fix the body before posting.
   Right after posting the verdict, the same pass sets the state tags (§4)
   with one command, never split: on `pass`, `<op:state-tags.set-approved>`;
   on `changes`, `<op:state-tags.set-changes>`. Then read the PR's tags
   back; if `crew:in-review` or the other verdict tag is still set, run the
   command again.
7. Report `$CREW_BIN action report --status done --ref '#<n>' --ref <head-sha>
   --ref <pass> --ref <pass|changes>` (this pass's section result), then exit.

Asks go in `blocked:` lines, never to the owner here. Never post plain PR
comments. A ban on tested sends never forbids your required reporting writes
(ack, verdict, tags, report) and grants no others. Never start a line with the steering prefix.
