# Observe: step summaries

> **Mirror note.** This doc is the reviewed copy. The builder duty is also
> carried by `docs/protocol.md` §3 and the builder templates, which are
> mirrored to the box skill `eng-pr-pipeline` (spec R4).

Long builds and test runs are invisible mid-flight. Without a record, a
builder retries blind, an "it passed" claim cannot be checked, and the
coordinator flies blind. Dumping a full tmux scrollback into chat is no
answer: it swamps the reviewer-validator, coordinator and synthesizer, whose
context is the scarce resource.

The protocol is: **short structured step summaries are the primary artifact;
raw logs stay local and are break-glass only.**

## When to write a step line

A builder worker writes one step line each time a unit of work with a visible
pass or fail ends:

- a build, a test suite, a lint or typecheck run, a migration or install that
  can fail;
- each fix attempt in a fix round or CI-fix, and the re-run that follows it;
- a retry, with the reason in the outcome.

Do not write a line per command, per file or per test case. One line per step
that someone would want to read when the run goes wrong. Aim for under ~15
lines per run (see [Risks](#risks)).

**N/A.** A pure docs one-shot with no multi-step run (edit, lint, push) needs
no summary; say `N/A: no multi-step run` in the evidence. Lighter-lane PRs
([protocol §6](protocol.md#6-duties-on-wake-all-roles)) are usually N/A. A
docs PR that runs a long link check or a script test suite may still log it.

## Fields

| Field | Rule |
|---|---|
| step | Short name: `build`, `unit-tests`, `fix-1 retest` |
| status | `ok`, `fail`, `warn` or `skip` |
| duration | Seconds or text such as `3m04s` |
| outcome | 1-3 lines: the result, or the error tail. At most 200 characters a line |
| log | Optional path to the full log, only when someone may need to dig |

## Local path convention

```text
.crew/runs/<issue-or-pr>/<run-id>/summary.md
.crew/runs/<issue-or-pr>/<run-id>/steps/*.log     (raw logs, optional)
```

`<issue-or-pr>` is `issue-<n>` while no PR exists and `pr-<n>` for runs
started after the PR opens (fix rounds). `<run-id>` is unique per run, for
example a UTC timestamp or `r1`, `r2`. The path lives under the worker's own
`<worktree>`.

**Everything stays local.** The run tree is never committed. `summary.md`
reaches the PR only as promoted text ([Promote onto the PR](#promote-onto-the-pr));
evidence placement is owned by
[protocol §3](protocol.md#3-evidence-requirements) (inline in the body or
signed reviews, no committed review artifact). `steps/` is ignored by
`.gitignore` and must never be added: raw logs stay on disk, or are attached
as a CI artifact or a linked file for break-glass use. They are never pasted
into chat, a PR body or another agent's inbox.

## The helper

`scripts/step-summary.py` appends one step block and creates `summary.md`
with a header on the first call. It reads no log except the last three lines
when asked, never echoes a log, cuts the outcome to 3 lines, and redacts
obvious token patterns (see [Risks](#risks)).

```sh
python3 scripts/step-summary.py --ref issue-<n> --run-id r1 \
  --step build --status ok --duration 42 --outcome "built 3 targets"
python3 scripts/step-summary.py --ref issue-<n> --run-id r1 \
  --step unit-tests --status fail --duration 3m04s \
  --outcome-from-log steps/unit-tests.log --log steps/unit-tests.log
```

Run it from the worktree root, or pass `--root <worktree>`. A relative
`--outcome-from-log` path is resolved against the run dir, so
`steps/unit-tests.log` means `.crew/runs/<ref>/<run-id>/steps/unit-tests.log`;
a relative path that resolves outside the run dir (`..`, or a symlink
pointing out) is rejected, while absolute paths are used as given, the
caller's choice. `--dir
<run-dir>` replaces `--root/--ref/--run-id`. A skeleton is in
[../templates/step-summary.md](../templates/step-summary.md). See
[scripts/README.md](../scripts/README.md#step-summary-helper).

## Promote onto the PR

Local summaries are for the run; the PR is where others read. When the PR
exists, the builder promotes the short summary, not the logs:

- Include the run's `summary.md` text (steps only, a few lines) as a
  `### Run summary` section in the `<BuilderEmoji> <BuilderBot> · Fix` or
  `<BuilderEmoji> <BuilderBot> · CI fix` COMMENT review. Builders post only signed COMMENT
  review bodies and never plain PR conversation comments. The PR body is
  written once and never edited, so the first run summary goes in the first
  builder review or in the PR body at creation, when the run already
  finished.
- Never commit `summary.md` to the PR branch, even when a verdict relies on
  it. Evidence lives on the change record, not the head
  ([protocol §3, Evidence on the change record](protocol.md#3-evidence-requirements);
  [verification](verification.md)).

Readers then open the one PR URL they already have. No new channel exists.

## tmux: attach and logs

On the [tmux runtime](runtimes/tmux.md) each role runs in its own window, and
the owner can watch live without adding anything to another role's context
([usage](runtimes/tmux.md#mdstack-attach)):

- `mdstack logs <window>` prints the tail of that run's newest step summary,
  `<worktree>/.crew/runs/**/summary.md`, and `-f` follows it. This is the
  default way to check progress. It never prints `steps/` logs.
- `mdstack attach <window>` attaches to the window read-only (`--rw` to type).
  `mdstack attach builders` opens a temporary tiled view of the builder band that
  is torn down on detach and never changes the mdstack layout.
- A run on a role host works the same way through its host's verbs
  ([multi-device observability](runtimes/multi-device.md#observability)):
  attach over `ssh -t`, a `capture` pane per remote builder in the builders
  view, and the `logs` tail without `-f`.

Both are for the owner's terminal only. Pane scrollback is never streamed or
pasted into another agent, a PR or an inbox; roles still read the promoted
summary on the PR.

## Who reads what

| Role | Skims | Digs |
|---|---|---|
| Reviewer-validator | The run summary on the PR: statuses and durations against the builder's evidence | The `log` path or an artifact, only when a step contradicts a claim. It reruns checks itself in its own worktree and does not need the builder's logs for the verdict |
| Coordinator | Step counts and statuses to spot blind retries | Never raw logs; asks the builder |
| Synthesizer | Nothing: the merge gate is unchanged and needs no summary or logs | Never |
| Builder | Its own summary before each retry | Its own logs |

## Risks

Called out, not all solved here:

- **Naming race.** Before the PR opens only the issue number exists, so early
  runs use `issue-<n>` and later ones `pr-<n>`. The two trees must be read
  together; the promoted text names the issue. A different run can reuse a
  `<run-id>` if ids are not unique; use a timestamp.
- **Summary spam.** Too fine-grained steps turn the summary into a log.
  Keep to the ~15-line budget; fold related commands into one step.
- **Secrets in promoted text or logs.** The helper redacts obvious token
  shapes in the outcome only. It cannot catch every secret, and a raw log can
  hold anything. Never paste or commit a log. The repo guard
  ([scripts/README.md](../scripts/README.md)) scans committed files, not
  local ones.
- **Box-disk wipe.** Logs and unpromoted summaries live on the box. If the
  worktree is deleted (`pr-merged` cleanup, a disk wipe) before promotion,
  they are gone. Promote the summary before the cleanup; treat a missing log
  as acceptable, a missing summary as a builder gap.
- **Trust.** A summary is the builder's own claim. It makes claims easier to
  check but does not replace the validation pass.

Out of scope: streaming pane scrollback into other agents (owner attach is
in [tmux: attach and logs](#tmux-attach-and-logs)), device or simulator
runtime, verification evidence formats, and merge
policy. Lesson:
[2026-10-29-step-summary-observe.md](lessons/2026-10-29-step-summary-observe.md).
