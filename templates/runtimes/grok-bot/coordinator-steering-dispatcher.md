# Coordinator routine: steering dispatcher

Owner: `<CoordinatorBot>`. One standing routine per repo. It is the **only**
routine in the crew that subscribes to comment events. See
[README.md](../../README.md) for placeholders and the event ownership table.

## Trigger

```json
{
  "type": "github",
  "repo": "<owner>/<repo>",
  "events": ["pr-comment", "inline-review-comment"],
  "userAllowlist": ["<user-logins>"]
}
```

`<user-logins>` expands to the user's own GitHub logins, one JSON string each.
The allowlist gates the **PR author**, not the commenter, so the routine fires
for every comment from anyone on PRs authored by those logins. That covers all
crew PRs without a per-PR watch. The prompt checks the commenter itself.

## Prompt

```text
Ownership first: apply protocol §4's control-item guard using the profile's
control item=<control-item>, runtime=<runtime-id>, at wake start and before
dispatch, push, post, label or land. Non-owning, in transit or unreadable:
read/report only. Draining: in-flight writes only, no new pass or land.

<include:policy/coordinator/signing.md>

<include:policy/shared/report.md>

<include:policy/shared/landing-authority.md>

<include:policy/coordinator/secret-retrieval.md>

<include:policy/coordinator/owner-config.md>

A comment landed on a PR in <owner>/<repo>. Follow the eng-pr-pipeline skill
(section 9, steering) and <state-dir>/<owner>__<repo>/wiring.md section 2a.

Cheap check first, then stop silently if it fails: the commenter is one of
<user-logins> AND the first line of the comment starts with the steering prefix.
Skip a comment id that already has a steer ack. Ignore edits. Unknown command
or wrong commenter: no reply, no post.

Re-read live PR state (head SHA, labels, reviews, markers). Respect crew:hold
for every command except resume, escalate, merge-ok, stop-landing and resume-landing.
Also allow project-scoped away on a held PR; it releases no hold.

Ack with one COMMENT review "<title:coordinator/steer> · ack <cmd> @ <sha7>" and a
hidden marker "crew:v1 ... pass=steer cmd=<cmd> cmd-id=<comment id>". Then
dispatch:
- hold: add crew:hold.
- resume: remove crew:hold and crew:escalated, post a resume marker (resets
  rounds), re-emit the stage signal: no verdict at head -> re-request the
  reviewer; last verdict was changes -> REQUEST_CHANGES steer review; approved
  at head -> APPROVE steer review with cmd=resume.
- rework: <note>: as <reviewer-login>, REQUEST_CHANGES with a steer marker
  cmd=rework and the note (file:line if the comment was inline). Not a round.
- rereview: ack, then re-request <reviewer-login> as a reviewer.
- merge-ok: as <reviewer-login>, APPROVE with a steer marker cmd=merge-ok
  sha=<head-sha>.
- urgent: record the qualifying reason and sha, then wake the synthesizer to
  consider this change alone; do not supply approval.
- stop-landing: record on the landing-control issue before delivery, then notify
  the synthesizer to stop the project line.
- resume-landing: record stop-id on that same landing-control issue, then wake the synthesizer;
  all other stops and gates still apply.
- escalate: add crew:escalated, post an escalation COMMENT review, tell the user.
- away (optional time and words): follow protocol §6, Owner away mode, in full;
  record verbatim words on the tracking issue and persist away-control.json in
  the per-project state directory. Batch owner pings, keep GitHub asks and
  scheduled SLA defaults, and infer no new authority. Re-read the record each
  coordinator wake; on the first owner message back, use
  <mdstack>/templates/owner-return-brief.md once. `until` alone is not a return.

Box-skill mirror: when you post the box-skill mirror comment on a PR (for
example "[<CoordinatorBot>] box skill mirrored"), remove crew:needs-mirror, then
message <SynthesizerBot> to re-check the merge gate, because label changes don't
wake listeners.

Never post plain PR comments or inline comments. Never write a line that starts
with the steering prefix. Use GH_TOKEN=$(gh auth token --user <author-login>)
for labels and acks, and --user <reviewer-login> for reviewer signals.
Notify the user only on escalate or on dispatch failure.
An away acknowledgement and the return brief also reach the owner channel.
Result goes to: no one, except escalate, away acknowledgement and return brief (the user).
```

## Notes

- Every bot review body also fires `pr-comment`, so this routine wakes once per
  bot post and must end those wakes in one cheap check. Keep bot posts to one
  per pass.
- External (fork) PRs are not covered, because the author is not allowlisted.
  To steer one, add a per-PR watch with `pr-comment`, `inline-review-comment`,
  `pr-merged` and `pr-closed` when the reviewer flags it `crew:external`.
- Issue comments cannot wake anyone. Steer issues by assignment, labels, or chat.
