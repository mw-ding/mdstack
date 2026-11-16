# Scripts

Repo guard for the spec's hard requirements (R1 no secrets, R6 CI green), the
tmux crew CLI, and the role and release helpers. Python 3 standard library
only; no dependencies. The guard needs no network; `metrics-refresh.py` and
`metrics-baseline.py` call the `gh` CLI (read-only).

## Per-script docs

Each script's usage lives in the script itself: its module docstring says
what it does, how to call it (a `Usage:` line) and whether CI runs it.
`--help` prints that docstring:

```sh
python3 scripts/<script>.py --help
python3 cli/mdstack --help             # lists the mdstack commands
python3 cli/mdstack <command> --help   # one command, from crew.d/<command>.py
```

This page has no per-script table. One shared table was a merge hotspot:
nearly every scripts PR edited a row of it, so each merge put the next PR in
conflict ([#325](https://github.com/mw-ding/eng-crew/issues/325)). A new or
changed script carries its docs in its own file instead, and `check-repo.py`
enforces it (rule `script-doc`): every `*.py` file directly under `scripts/`,
`crew` and every `crew.d/*.py` file needs a module docstring. A script you
run (it has a `__main__` block and is not a `test-*.py`) and a `crew` command
(`crew.d/<command>.py` without a leading `_`) need a `Usage:` line in it too.

- Tests are `test-<name>.py`; the docstring says what each covers. They live
  in `dev/tests/<module>/`, by the module that holds the code under test:
  `core`, `environments`, `harnesses`, `connectors`, or `scripts` for code not
  moved out of `scripts/` yet. Fixtures sit in that module's `fixtures/`;
  fixtures several modules share, and `crew_testlib.py`, sit in `dev/tests/`.
  `check-repo.py` (rule `test-layout`) fails a test anywhere else. Tests take
  no arguments (`python3 dev/tests/<module>/test-<name>.py`). CI runs them all
  in the `repo-guard` job of `.github/workflows/ci.yml` with `run-tests.py`,
  which picks up every `dev/tests/*/test-*.py` by glob and runs each
  once, in parallel.
- Helper modules that other scripts import, such as `crew_testlib.py`,
  `harnesses/crew-harness.py`, `environments/terminal/crew-session.py`,
  `environments/terminal/crew-proc.py` and
  `environments/terminal/crew.d/_shared.py`, are not run directly; the
  docstring says what they hold. `harnesses/<engine>/adapter.py` holds one
  harness adapter each
  ([harness adapters](../docs/runtimes/harness-adapters.md#adapter-modules))
  and `environments/terminal/sessions/<backend>/adapter.py` one session
  backend adapter each
  ([session backends](../docs/runtimes/session-backends.md#adapter-modules)).
- The crew CLI and its modules moved out of `scripts/` into `cli/`, `core/`,
  `environments/`, `harnesses/` and `connectors/` (#1222); 7.0.0 removed the
  old paths.
- `required-docs.txt` and `deliverables.txt` are `check-repo.py` config; each
  starts with a comment that gives its format (see
  [Required docs](#required-docs)).
- `fixtures/` holds test inputs (see [Fixtures](#fixtures)).

## Run it

From the repo root:

```sh
python3 scripts/check-repo.py            # all checks
python3 scripts/check-repo.py --only secrets   # or docs / links / markers / blockers / shapes / denylist / deliverables / spec-status / design-headers / fragments / script-docs / index / evidence / markdown (repeatable)
python3 scripts/check-repo.py --fix      # also rewrite the generated inventory table in docs/deliverables.md
python3 dev/tests/scripts/test-check-repo.py       # fixture and structural tests
python3 scripts/check-markdown.py        # markdown lint on changed *.md files (--all: every tracked one)
```

Every problem prints as `file:line: [rule] reason`; the exit code is 1 if there
is any problem, 0 otherwise. CI runs both commands in the `repo-guard` job
(`.github/workflows/ci.yml`) on every pull request and push to `main`.

In a git work tree the checks read tracked files only (`git ls-files`), so
`check-repo.py` also prints `check-repo: warning: N untracked file(s) not
checked ...` on stderr, naming each non-ignored untracked file (ignored files
stay quiet). It is a warning, not a failure: `git add` new files, then rerun
before claiming a passing check (#1414).

## What it checks

| Rule | Fails on |
|---|---|
| `github-token` | GitHub tokens with the `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` prefixes |
| `github-pat` | fine-grained tokens with the `github_pat_` prefix |
| `sk-key` | `sk-` style API keys (20+ key characters) |
| `aws-access-key` | AWS access key ids (`AKIA`, `ASIA`, and related prefixes) |
| `private-key` | `-----BEGIN ... PRIVATE KEY-----` blocks |
| `bearer-header` | an `Authorization` header with a literal bearer value |
| `url-credentials` | URLs with a literal `user:password@` part |
| `missing-file`, `missing-section` | an entry in `required-docs.txt` that is absent |
| `marker-sha` | a `crew:v1` marker (also wrapped over lines, also inside fences) in `*.md` whose `sha=` is a literal that is not 40 hex characters, or a placeholder naming a short SHA (`sha7`, `short`). Placeholders like `<head-sha>` and `<40-char head sha>` pass. Encodes the lesson in `docs/lessons/2026-10-23-watch-handoff-first-run.md` (issue #69) |
| `synthesizer-blockers` | `docs/protocol.md` or `templates/runtimes/grok-bot/synthesizer.md` (when present) no longer names the `hold-until` blocker or an open `steer cmd=rereview`. Static presence guard only; live hold and rereview state is not checkable offline. Lesson `docs/lessons/2026-10-29-synthesizer-hold-race.md` (issue #81) |
| `verification-shapes` | `docs/verification.md` (when present) has a shape table without a row whose first cell is each of Web, CLI, Service, API and Mobile. Static presence guard; whether a PR attached the right evidence is judged by the validator. Lesson `docs/lessons/2026-10-29-typed-verify-evidence.md` (issue #83) |
| `denylist` | a whole-word, case-insensitive match of a name from the `CREW_DENYLIST` file in any scanned file (see [Denylist](#denylist)); skipped when the variable is unset |
| `unclassified`, `double-classified` | a tracked path (`git ls-files`) that matches no row, or more than one row, of `deliverables.txt`. Globs: `**` matches across `/`, `*` and `?` stay inside one segment. A bad or missing manifest fails as `deliverables-config`; outside a git work tree the check is skipped. Issue #235 |
| `index-stale`, `index-order`, `docs-index` | the index files that every PR would otherwise append to ([Index files](#index-files)): the inventory table in `docs/deliverables.md` differs from the one generated from `deliverables.txt` (or its markers are missing); an entry of `deliverables.txt`, `required-docs.txt` or a `docs/README.md` table row that sorts before the one above it; a second `docs/README.md` row for one doc, or none for a deliverable doc. Issue #325 |
| `changelog-fragment` | a file under `changes/` that is not a valid fragment directly in `changes/unreleased/`: name `<issue>-<slug>.md`, front matter with exactly `type`, `issue` (the file name's), `pr` (a number or `TBD`), `date` and `box-skill`, then one paragraph of entry text ([CONTRIBUTING](../CONTRIBUTING.md#changelog)). Issue #264 |
| `script-doc` | a `*.py` file directly under `scripts/`, `cli/mdstack`, a `*.py` file under `core/`, `harnesses/`, `connectors/` or `environments/`, or a `dev/tests/<module>/test-*.py` test or `dev/tests/crew_testlib.py` without a module docstring, or a script run directly (a `__main__` block, not a `test-*.py`) or `crew` command whose docstring has no line starting `Usage:` ([Per-script docs](#per-script-docs)). A file that does not parse fails too. Issue #325 |
| `markdown` | a markdownlint rule this repo configures and has failed in CI, run on every tracked `*.md` file by `check-markdown.py` ([Markdown lint](#markdown-lint)). Issue #644 |
| `test-layout` | a tracked `test-*.py` outside `dev/tests/<module>/` (module one of `actions`, `cli`, `connectors`, `core`, `environments`, `harnesses`, `protocols`, `roles`, `scripts`), or a test name already used in another module; a `test-*.py` under a `fixtures/` directory is test input and is skipped ([Per-script docs](#per-script-docs)). Issue #1224 |
| `deps`, `deps-baseline` | a file in a module of the [team spec layout](../docs/specs/team.md#4-target-module-layout) that breaks a [dependency rule](../docs/specs/team.md#5-dependency-rules) D1–D9, or, under `roles/` and `protocols/`, names a runtime word (REQ-11: `tmux`, `herdr`, inbox, window, the terminal's `CREW_*` variables, a `crew <command>` or `$CREW_BIN`). A module reference is a path naming another module; in Python it is a string literal that is a whole repo path, an import of a module package (`from connectors.github import x`), or a module name or path joined into a path (`ROOT / "harnesses"`, `os.path.join(ROOT, "core", ...)`). Words follow D5–D7. Python and TOML comments, Python docstrings, `docs/` and `dev/` are not checked. A `path<TAB>rule<TAB>why` row in `deps-baseline.txt` passes that pair; a row that no longer matches, or has no reason, fails as `deps-baseline`. Issue #1224 |
| `broken-link` | a relative markdown link (or image) whose target file does not exist, or that points outside the repo |

Every file is scanned for secrets (binary files are skipped). In a git work
tree (the repo root is the top level) the file list is `git ls-files`, so
everything tracked is scanned, including a tracked `node_modules/`, and an
untracked or ignored directory such as a local `node_modules/` is not; `git add`
a new file for local runs to see it (CI only has tracked files anyway). Outside
a git work tree (or if `git` fails) every file except `.git/` is scanned.

Token patterns use alnum-only boundaries, not `\b`, so a token wrapped in `_`
(Markdown emphasis, such as `_ghp_<36 chars>_`) is still caught. Git history is
not scanned.

Links are checked in `*.md` files; `http(s):`, `mailto:` and fragment-only
links are ignored. Fragment (`#anchor`) checks stay with the `links` CI job
(lychee). Destinations are URL-decoded (`other%20file.md`) and may contain
balanced parentheses (`other(v1).md`) or be written as `<other file.md>`.

Code fences follow CommonMark. A fence opens with 3+ backticks or tildes (up to
3 spaces of indent), also after list markers (`-`, `*`, `+`, `1.`, `1)`, nested
to any depth) and block-quote `>` prefixes, and closes only on a fence of the
same character, at least as long as the opener, with nothing but whitespace
after it (inside a list item or quote the closer may be indented as far as the
content). Fenced lines are skipped by the link check, and a heading inside a
fence never satisfies a required section.

Safety rule for stray fences: CommonMark runs an unclosed fence to the end of
the file, which would let one unrecognised opener (or a lone closer of a fence
the scanner did not see) hide every later link. So for the link check an
unclosed opener is treated as plain text: nothing after it is skipped. The
section check stays strict and fails closed instead: a heading after an
unclosed fence does not count, and the `missing-section` message names the
line of the unclosed fence. The only way a fence hides lines is therefore a
recognised opener with a matching closer, and a fence the scanner opens that
CommonMark would not (for example inside an indented code block) can hide only
the lines up to its closer.

Inline code spans are skipped: a backtick run closes at the next run of the
same length, a backslash-escaped backtick is literal, and an unmatched run is
literal (the text after it is still checked). HTML comments (`<!-- ... -->`,
also across lines; an unclosed one runs to the end of the file) never satisfy a
required heading; links inside comments are still checked.

Known limits:

- A link split across lines (`[x](` then the destination on the next line) and
  a reference definition whose destination is on the next line are not checked.
- Code spans are matched within one line; a span that wraps lines is not
  skipped, so a link inside it is checked (this can only add findings).
- A fence or comment marker inside an HTML comment is not understood: a lone
  fence line in a comment is read as a fence opener (an unclosed one is
  harmless for links but makes the section check fail closed).

## Markdown lint

`check-markdown.py` is a dependency-free subset of markdownlint, so a builder
catches the common `markdownlint` CI failures without the binary. CI's
markdownlint job (`.markdownlint-cli2.yaml`) stays the authority: this check
aims to flag nothing markdownlint would not (the whole repo passes), but it does
not catch everything markdownlint does.

```sh
python3 scripts/check-markdown.py              # *.md changed since the merge base with origin/main, incl. uncommitted and untracked
python3 scripts/check-markdown.py --base main  # another base ref
python3 scripts/check-markdown.py --all        # every tracked *.md file
python3 scripts/check-markdown.py docs/a.md    # named files
```

Each finding prints `path:line rule message`; the exit code is 1 on any
finding, 2 if the file list cannot be built. `check-repo.py` runs it on every
tracked `*.md` file as its `markdown` check (`file:line: [markdown] rule
message`), so the targeted local set needs no extra step.

| Rule | Covered |
|---|---|
| MD001 | heading level jumps by more than one |
| MD003 | heading style differs from the first heading (ATX, closed ATX, setext) |
| MD009 | trailing whitespace, except exactly 2 spaces (hard break) |
| MD012 | more than one consecutive blank line |
| MD018 | `#` at line start followed by text with no space (`#102: ...`) |
| MD022 | no blank line above or below a heading |
| MD031 | no blank line above or below a fenced code block |
| MD032 | no blank line above or below a top-level list (lazy continuation lines belong to the list) |
| MD040 | fenced code block without a language |
| MD047 | file does not end with a newline |
| MD056 | table row cell count differs from the header row |

Front matter, fenced code and HTML comment lines are skipped, and a line that is
only an HTML comment counts as blank, as in markdownlint. Indented code blocks,
block quotes and nested lists are only partly understood, so findings there are
left to CI. A new rule goes in with a pass and a fail fixture in
`test-check-markdown.py`.

## Denylist

Portable spec P6: mdstack never names an organization's internal tools
([docs/packs.md](../docs/packs.md#direction-rule)). The names themselves are
never committed here. Keep them in a file outside the repo, one per line
(`#` comments and blank lines are ignored), and point `CREW_DENYLIST` at it:

```sh
CREW_DENYLIST=<path-to-denylist> python3 scripts/check-repo.py --only denylist
```

A hit prints `file:line: [denylist]` with the denylist line number, never the
name, so CI logs do not leak it. Matching is case-insensitive and whole-word
(`\w` boundaries): an entry inside a longer word does not match. With the
variable unset the check is skipped (a note goes to stderr); a set variable
naming an unreadable file fails. The `repo-guard` CI job reads the repo-level
Actions secret `CREW_DENYLIST`, writes it to a private runner temp file for
this step, and deletes it on success or failure. Secret values are passed
through an environment variable and never echoed. With no secret (including
fork PRs), the check retains its explicit skip behavior.

## CLI evidence helper

`evidence-cli.py` captures one command/output pair for inline PR evidence in
the [CLI adapter](../templates/evidence/cli-exit-stdout.md) shape. It runs the
command in the current directory and prints a `Proof <label> · ... · sha ... ·
cwd ...` header, a copyable `sh` block and a `text` block with `exit:`,
`--- stdout` and `--- stderr`. `--setup FILE` prepends a shell setup (temp
repo, fake `gh`) to the `sh` block and runs both as one `sh -c` script.
`--scrub-env VAR` values, the working directory, `$HOME` and token shapes are
scrubbed with `# scrubbed:` notes; `--volatile NOTE` adds `# volatile:` notes.
It reuses `step-summary.py`'s token patterns but not its generic `key=value`
rule, which would rewrite ordinary output and break the `sh` block; name
secrets with `--scrub-env`. Standard library only.

```sh
python3 scripts/evidence-cli.py --label R1 -- python3 scripts/check-repo.py --only shapes
python3 dev/tests/scripts/test-evidence-cli.py
```

## Run usage helper

`run-usage.py` prints the usage line a role puts just above the signature of
every pass-reporting post ([roles](../docs/roles.md#usage-line), #1557):
wall-clock time from the run start, tokens read from the harness's local
session log by its adapter's `usage` reader
([harness adapters](../docs/runtimes/harness-adapters.md#adapter-modules)),
and the model and effort. A harness without a reader, or no log entry since
the start, prints `tokens n/a`. It prints no path or credential.

```sh
python3 scripts/run-usage.py --run "$CREW_STATE/runs/$CREW_ID.json"
python3 scripts/run-usage.py --engine codex --dir "$PWD" --start 2026-11-10T07:00:00Z
python3 dev/tests/scripts/test-run-usage.py
```

## Step summary helper

`step-summary.py` is the thin builder helper for the
[observe protocol](../docs/observe.md). It creates
`.crew/runs/<issue-or-pr>/<run-id>/summary.md` with a header on the first call
and appends one block per call: step, status (`ok`, `fail`, `warn`, `skip`),
duration, a 1-3 line outcome and an optional log path.

```sh
python3 scripts/step-summary.py --ref issue-<n> --run-id r1 \
  --step build --status ok --duration 42 --outcome "built 3 targets"
python3 scripts/step-summary.py --ref issue-<n> --run-id r1 \
  --step tests --status fail --duration 3m04s \
  --outcome-from-log steps/tests.log --log steps/tests.log
python3 dev/tests/scripts/test-step-summary.py
```

The outcome is cut to 3 lines of 200 characters and obvious token patterns
(GitHub and `sk-` keys, AWS key ids, bearer values, URL credentials,
`password=` style pairs) are replaced by `<redacted>`. It never echoes or
copies a raw log; `--outcome-from-log` reads only the last three lines (at most
32 KiB, `TAIL_MAX_BYTES`, read from the end of the file, so a log ending in one
huge line yields only its tail) and resolves a relative path against the run
dir. A relative path that leaves the run dir (`..` or a symlink, checked with
`realpath`) is rejected; absolute paths work as given, the caller's choice.
`--ref` and `--run-id` must match `[A-Za-z0-9._-]+` and not be only dots. The redaction is best effort, not a secret scanner. Standard library only.

## Allowlist: placeholder form only

There is no ignore comment and no path exclusion. A secret-looking value is
accepted only when written as a placeholder, a name in angle brackets:

- `ghp_<token>`, `sk-<key>` (the `<` stops the token pattern from matching)
- `Authorization: Bearer <token>`
- `https://<user>:<password>@host/path`

Anything else, including well-known documentation example keys, fails. Refer to
credentials by mechanism instead (see spec R1).

## Required docs

Edit `required-docs.txt`. One entry per line: `path` requires the file;
`path :: ## Heading` requires that exact heading line (outside code fences
and HTML comments, as defined above).
Blank lines and lines starting with `#` are ignored. Add entries in the same PR
that lands the doc, at their sorted place (see [Index files](#index-files)).

## Index files

The files every PR touches to register something are kept conflict-free
([#325](https://github.com/mw-ding/eng-crew/issues/325); rule in
[CONTRIBUTING](../CONTRIBUTING.md#shared-files)):

- `deliverables.txt` (`glob<TAB>class<TAB>runtime<TAB>why`, the last column
  optional), `required-docs.txt` and the table rows of `../docs/README.md` are
  sorted bytewise by the whole line, one entry per line, so a new entry lands at
  its own place and not at the end. `check-repo.py --only index` fails on an
  entry that sorts before the one above it (`index-order`).
- The inventory table in `../docs/deliverables.md`, between its
  `inventory:begin` and `inventory:end` comments, is generated from
  `deliverables.txt`, one row per manifest row, in file order.
  `check-repo.py --fix` rewrites it; without `--fix` a table that differs
  fails (`index-stale`). Never edit it by hand.
- `../docs/README.md` has one row per doc and a row for every doc the manifest
  classifies `deliverable` under `docs/` (`docs-index`).

## Fixtures

`fixtures/bad/*.txt` holds fake samples per rule (including `_`-wrapped
variants named `*-underscore.txt`), always on line 3, with the
rule id on the `# expect:` line. Each token is stored **defanged**: a `~~`
marker splits the string, so the repo never contains a matching (or
push-protection-triggering) value. `test-check-repo.py` strips the marker into a
temp directory and requires `check-repo.py` to fail with `<file>:3: [<rule>]`.
`fixtures/good/` holds the placeholder forms and must pass.

Because the fixtures are inert, the real scan does not exclude them, and
verifies it by scanning them as ordinary files. Fixtures are `.txt` so
markdownlint and lychee ignore them. Structural cases (missing file or section,
broken link) are built in temp directories by the test, not stored as `.md`.

To add a pattern: add it to `PATTERNS` in `check-repo.py`, add
`fixtures/bad/<name>.txt` with a defanged sample, and extend the table above.

## Skill drift check (coordinator)

`docs/protocol.md` and `docs/roles.md` are the reviewed copies of the box skills
`eng-pr-pipeline` and `eng-crew-roles` (spec R4). `check-skill-drift.py` reports
where they have diverged. It needs the box files, so it is **not** part of CI.

**Who runs it:** the coordinator (Ash), (1) when a PR carries `crew:needs-mirror`,
after mirroring the box skill and before posting the mirror comment, which
must carry the clean result inline
([mirror hold gate](../docs/runtimes/grok-bot.md#mirror-hold-gate)), and (2)
after any merged PR that touches `docs/protocol.md` or `templates/`. A non-zero
exit means the mirror is not finished; fix the box copy (or this repo) and rerun
before removing `crew:needs-mirror`.

```sh
python3 scripts/check-skill-drift.py \
  --pipeline-skill <skill-dir>/eng-pr-pipeline/SKILL.md \
  --roles-skill <skill-dir>/eng-crew-roles/SKILL.md      # add -v for first differing words
```

The paths can also come from `ECREW_PIPELINE_SKILL` and `ECREW_ROLES_SKILL`;
`--only pipeline|roles` checks one pair. The check only reads the files.

What it compares (not bytes, since the skills have frontmatter and box wording):

- `protocol.md` against the pipeline skill, per `##`/`###` section. Text is
  normalized (links, backticks, whitespace). A section is `OK` (identical),
  `WORDING` (text differs, but the key facts match) or `DRIFT` (key facts
  differ). Key facts are single-word code spans (labels, markers such as
  `pass=watch`, event names, flags; spans over 40 characters are skipped;
  placeholders such as `<sha7>` are stripped inside a span) and quantities such
  as `3 rounds`, `40-char` or `5 minutes`, also when written inside a code span.
  `char`/`character(s)` and `min`/`minute(s)` count as the same unit.
  Link destinations (`](#5-rounds-and-escalation)`, reference-style
  definitions) are dropped first, so a link fragment is never a quantity.
  A fact found only as a code span on one side is not reported when the other
  side has the same word unformatted (bold, plain text); link destinations,
  reference labels and reference definitions do not count as that text, so a
  changed fact cannot hide in a URL or `#fragment`. What is reported reads
  "not found in skill/repo", meaning absent from that section (for roles, from
  the whole file); a per-section compare can still list a fact that the other
  file has in a different section. A section only in one file is `MISSING` or
  `EXTRA`. The `Worked example / pilot notes` section and the roles example
  with historical quota percentages are skipped as repo-only
  (`--ignore-heading` adds more).
- `roles.md` against the roles skill, by the same key facts over the whole file
  including the text before the first heading, because the skill's headings do not line up with the reviewed doc.
- `templates/` are not compared: the box skills carry no template copies.

Exit codes: 0 no drift, 1 drift, 2 usage error or a missing skill file (never a
silent pass; also for a file that cannot be read or decoded as UTF-8). Existing drift is a finding for the coordinator, not a bug in the
check. `WORDING` is informational and does not fail.

### Render vs live (`--project`)

```sh
python3 scripts/check-skill-drift.py --project <config.toml> [--org-profile <path>] \
  [--live-dir <live-dir>]                                # add -v for first differing words
```

Renders the profile with the [renderer](#renderer) (same layers and inputs; for
the default profile, the Grok Bot runtime files that `test-render-parity.py`
covers) into a temp dir and compares each
rendered file with the same relative path under the live copy dir, laid out
like `crew-render.py --out` (`runtime/...`, `briefs/...`). The live dir comes
from `--live-dir`, else `ECREW_LIVE_DIR`, else the profile's `paths.live_dir`
([profile](../docs/profile.md#paths)). Files are compared per section; the
text before the first `##` heading counts as a `(preamble)` section. This mode
is exact, with no `WORDING` tolerance: the deploy must equal the render, so any
difference in a section's text (a code span, including a multi-word command,
an HTML comment, or appended live-only text) is `DRIFT` (exit 1), printed with
the first differing words as `render:` and `live:`. The doc-vs-skill heading
exclusions (`--ignore-heading` and the built-in ones) do not apply, so a
live-only section under such a heading is `EXTRA` (exit 1). A rendered file missing from the live copy, a live dir
that is unset, still a placeholder (`<live-dir>`) or absent, and a profile
that does not resolve or render are exit 2; a live file the render does not
produce is `EXTRA` (exit 1). It only reads the live copy; deploying it stays
with the coordinator. Not run in CI.

```sh
python3 dev/tests/scripts/test-check-skill-drift.py   # synthetic fixtures, no box files
```

## Intake sweep (weekly stuck pass)

`intake-sweep.py` is the one live trigger of the
[self-improve intake](../docs/self-improve.md). It reads the JSON that
`gh pr list --json number,title,url,labels,updatedAt,isDraft` prints, from a
file or stdin, and prints one markdown candidate card per open PR that is
labelled `crew:blocked` or has had no update for more than `--stale-days`.
Cards follow [templates/intake-candidate.md](../templates/intake-candidate.md);
Scope defaults to `repo:` with a "(triage: confirm or promote)" hint. Draft PRs
are skipped. Python 3 standard library only; it makes no network call, files no
issue and edits no skill.

```sh
gh pr list --repo <owner>/<repo> --state open --limit 200 \
  --json number,title,url,labels,updatedAt,isDraft \
  | python3 scripts/intake-sweep.py --repo <owner>/<repo>
```

Then the coordinator reviews the drafts and files the keepers as mdstack
issues. Options: `--stale-days N` (default 7), `--label NAME` (default
`crew:blocked`), `--repo OWNER/REPO` (shown on cards), `--now
YYYY-MM-DDTHH:MM:SSZ` (override the clock). Empty input prints nothing and
exits 0; unreadable input exits 2.

```sh
python3 dev/tests/scripts/test-intake-sweep.py   # offline, no gh
```

## Docs scan (project docs pass, stage 1)

`docs-scan.py` is the zero-model first stage of the
[docs pass](../docs/project-docs.md#docs-pass) (#1025). For each
[`[docs]`](../docs/profile.md#docs) `repos` entry it reads the git tree of a
local clone at the default-branch head (`--ref` to pin one; else
`origin/<default_branch>` for the project's own repo, `origin/HEAD`, then
`HEAD`) and writes `<state-dir>/<owner>__<repo>/docs/scan.json`: the Markdown
inventory (lines, docs index row and kind, banner), `missing` essentials
against the [project doc set](../docs/project-doc-set.md) and `homes`
(`path#anchor` homes need the heading), `unbannered` design docs, `stale`
banners, `broken_links` (file or anchor) and `oversize` docs. It reads git
objects only, never fetches or touches a work tree, and writes nothing but
each scan.json. `--state-dir DIR` writes under `DIR` in place of the
profile's state dir; a `--ref` scan needs it, so a branch or worktree scan
never overwrites the live default-branch scan.json (#1320). With no `[docs]`
table it does nothing and exits 0. With
`[docs] enabled`, `mdstack watch`'s docs-pass timer runs it on the project's own
checkout every `interval_days` before a docs-pass session (#1026).

```sh
python3 scripts/docs-scan.py --project config.toml --checkout <owner>/<repo>=<clone>
python3 scripts/docs-scan.py --project config.toml --checkout <owner>/<repo>=<worktree> \
  --ref <owner>/<repo>=HEAD --state-dir <worktree>/.crew/docs-state
python3 dev/tests/scripts/test-docs-scan.py   # fixture git repos, no network
```

## Triage metrics

`triage-metrics.py` measures [always-on triage](../docs/triage.md) in shadow
mode (#750). It reads the JSON of the researcher's `list-items`
dump (`gh issue list --state all --json
number,url,state,stateReason,labels,createdAt,comments`, repos concatenated)
and the `pass=triage` / `pass=triage-log` lines on it. `sample --sweep ID`
prints the 10 spot-check refs of a calibration sweep, the same for every run;
`bar --sweep ID` counts the owner's `owner-accepted`, `owner-rejected` and
`owner-adjusted` answers on them (exit 0 at 8 of 10 accepted, 1 below or
pending); `rolling` scores the newest 10 owner answers on applied records the
same way and, below the bar, prints a proposal to return to shadow mode
(#835); `report` prints accuracy, owner override rate, reopen rate, time to
triage, proposals per day, tokens per sweep, owner feedback on applied
records and cluster counts from `pass=triage-cluster` records and
`cluster:<slug>` labels (`--sweep ID` adds what that sweep recorded); `eval-freeze --sweep ID --out FILE` writes the
owner-confirmed records as the eval set and `eval-score --set FILE --answers
FILE` scores a re-classification against it. Python 3 standard library only;
no network. Unreadable input exits 2.

```sh
python3 scripts/triage-metrics.py bar --items .crew/triage-items.json --sweep 20261104T0600Z
python3 dev/tests/scripts/test-triage-metrics.py   # offline, no gh
```

## Triage clusters

`triage-clusters.py` groups related but distinct open issues into
[triage clusters](../docs/triage.md#clusters) (#1298). It reads the JSON of
`gh issue list --json number,url,state,title,body,labels,milestone,comments`
(repos concatenated; closed issues, pull requests and `triage:log` issues are
skipped). Deterministic keys place each issue in at most one cluster: the
Failure class slug, the Source issue, `Depends on #n` targets and the first
two segments of each named path, in that order. The slug comes from the
placing key, and `--prior` (the last `--out`) keeps recorded slugs first and
lists the members new since then. `--model FILE` adds members, each with a
one-line reason, and sets a cluster's summary, band, milestone or tracking
proposal; both carry over in `--out`. A new cluster proposal (`tracking`,
or `milestone:<title>`, where a changed title is new) costs one of
`--cap-left` (default 10) whatever its size; the rest print as
`skipped: cap`. It prints one line per cluster with its members for the log.
Python 3 standard library only; no network. Unreadable input, or a model
member without a reason, exits 2.

```sh
python3 scripts/triage-clusters.py --items .crew/triage-open.json --sweep 20261108T1800Z \
  --prior "$CREW_STATE/triage/clusters.json" --cap-left 7 --out .crew/clusters.json
python3 dev/tests/scripts/test-triage-clusters.py   # offline, no gh
```

## Triage apply

`triage-apply.py` is the one entry point for a triage sweep's tracker writes
([write allowlist](../docs/triage.md#write-allowlist), #753). It reads a
requests file (`{"sweep", "signature", "requests"}`) and checks every request
against the allowlist, the profile's `triage.mode` and `triage.repos`, and
the issue's own `pass=triage` record from this sweep, posted in the same
batch or by the researcher's login, before it writes anything. One refused
request refuses the batch: each reason on stderr, exit 1, no write.
Otherwise it writes through `gh`, skips a write already in effect and lists
both on stdout. Exit 2 is unreadable input or a non-GitHub tracker (no apply
binding); exit 3 is a forge command that failed mid-batch, and a rerun skips
the writes already made. Python 3 standard library and `gh` only.

```sh
python3 scripts/triage-apply.py --project "$CREW_PROJECT" --requests .crew/triage-requests.json
python3 dev/tests/scripts/test-triage-apply.py   # offline, fake forge and fake gh
```

## Profile validator

`crew-config.py validate <file>` checks one install-time profile
(`config.toml`) against the schema in [../docs/profile.md](../docs/profile.md):
required keys, closed tables (unknown keys, concerns, runtimes, backends and
engines fail), types, capability values, the host inventory and placement
rules, and token-shaped values anywhere in the file. The token check reuses
`PATTERNS`, `BEARER`, `URL_CRED` and the placeholder allowlist of
`check-repo.py` (imported, not copied). Python 3.11+ standard library only
(`tomllib`); no network.

```sh
python3 core/crew-config.py validate config.toml
python3 core/crew-config.py validate connectors/github/manifest.toml   # a file with [pack] is a pack manifest
python3 dev/tests/core/test-crew-config.py   # offline; also checks the docs/profile.md example
```

Every problem prints as `file:key: reason` (dotted key path); exit 1 on any
problem, 0 otherwise (2 on a usage error).

`crew-config.py resolve --project <config.toml> [--org-profile <path>]` merges
core defaults, `profiles/default.toml` (if present), the org profile and the
project file, folds each backend's `connectors/<name>/manifest.toml` capabilities
under them, validates the result, runs the cross-key checks and prints
`key = value  # layer` per key (`pack:<name>` for a manifest value). Layers, merge rule and checks:
[Layers and precedence](../docs/profile.md#layers-and-precedence).
The CLI prints from `resolve_profile(project, org_profile=None)`, which
returns the merged profile, a per-key provenance map, the problems and the
layer names, so other scripts can resolve in-process.

## Renderer

`crew-render.py` produces role briefs and runtime artifacts from render
inputs and the resolved profile, so the live copy is generated, not
hand-edited ([portable spec P4](../docs/specs/portable.md#2-requirements)).
It resolves the profile in-process with `resolve_profile` from
`crew-config.py` (same layers and checks; a resolve problem is printed as is
and stops the run).
Flavor placeholders expand the resolved preset plus custom knobs. With
`--diff-paths FILE`, newline-separated repo-relative paths (including both
rename paths) select class rigor through `crew-config.py`'s matcher; no paths
uses the project baseline. Classes never change the project builder mode.
The baseline is one line in builder, reviewer and synthesizer briefs in both
bindings; it supplies no item record or owner permission. Unset flavor is
`standard` and renders its baseline line like an explicit name; explicit precheck settings and recorded legacy grants retain their
existing behavior. The `solo` preset renders its owner-driven builder mode.
Reviewer briefs render the validation scope baseline and name the configured
`builder.precheck` test and lint commands (`n/a` when unset), never a fixed
repo-wide script list (#648).
Python 3.11+ standard library only; no network.

```sh
python3 core/crew-render.py --project config.toml [--org-profile <path>] \
  [--inputs <inputs-dir>] --out <out-dir>
python3 dev/tests/core/test-crew-render.py   # golden files under fixtures/render/
python3 dev/tests/core/test-render-parity.py # real templates vs pre-conversion text
```

Inputs layout. `--inputs` defaults to the repo's real input tree,
[`templates/`](../templates/README.md): the Grok Bot templates under
`runtimes/grok-bot/`, the tmux role briefs under `runtimes/tmux/` (14.8,
[#137](https://github.com/mw-ding/eng-crew/issues/137)), the session briefs
under `runtimes/session/` (#914) and the GitHub command
mapping `backends/github.toml` (13.14, [#126](https://github.com/mw-ding/eng-crew/issues/126)).
It has no `core/` yet, so it renders no `briefs/`; the fixture tree
`fixtures/render/inputs/` has all three parts:

| Input | Output |
|---|---|
| `core/<role>.md`, required for each of `coordinator`, `builder`, `reviewer`, `synthesizer` when `core/` exists | `briefs/<role>.md` |
| `runtimes/<runtime>/**`, only the profile's `runtime.name`; required. With `runtime.options.researchers = 0`, the researcher's registry templates are skipped (#926) | `runtime/**` |
| `backends/<backend>.toml`: `[<concern>] <operation> = "<command>"` | substituted for `<op:<concern>.<operation>>`, as written (a multi-line value keeps the brief's line breaks) |

Overlay lookup order (#580). A pack's `render/` directory overlays the
inputs per file. The pack directory is the org profile's directory
(`--org-profile`), else `paths.pack` resolved from the project file. For each
relative path (`core/<role>.md`, `runtimes/<runtime>/**`,
`backends/<backend>.toml`), the renderer reads `<pack>/render/<path>` when it
exists, else `<inputs>/<path>`. The runtime files rendered are the union of
both trees, so an overlay can change one template or add a backend map
without copying the rest. Without a `render/` directory the output is
unchanged. `mdstack up`, `mdstack bootstrap`, `mdstack upgrade` and
`check-skill-drift.py --project` render through this script, so they all
apply the same overlay.

Pack-declared placeholders: a backend file may declare extra run-time
placeholders for its own command values with `[placeholders] kept =
["<name>", ...]` (names `[a-z][a-z0-9-]*`, never an install-time
placeholder). They render verbatim inside that backend's commands; an
undeclared one still fails with `unknown placeholder`.

Update strategy lines: a template line that starts with `<strategy:merge>`
or `<strategy:rebase>` renders, without the prefix, only when the change
backend's resolved `strategy.update_from_base` matches (`merge` when the
pack declares no `[strategy]`). The builder precheck's fresh-base step picks
"use merge-up" or "rebase onto `<default-branch>` and upload" the same way
([update strategy](../docs/interfaces.md#rebase-update-from-base), #874).

Control-item blocks: a template line exactly `<control-item:set>` or
`<control-item:none>` opens a block that a line exactly
`<control-item:end>` closes. The block renders, without its marker lines,
only when `repo.control_item` is set (a tracker-native item counts) or
unset, respectively; the session briefs use it to drop inert ownership
text (#914).

Session-backend blocks: a template line exactly `<session-backend:hosted>`
or `<session-backend:local>` opens a block that a line exactly
`<session-backend:end>` closes. The block renders, without its marker
lines, only when `runtime.options.session_backend` is or is not `hosted`,
respectively, and may sit inside a control-item block; the session briefs
use it to give hosted control-plane sessions their own dispatch and
liveness text (#1052).

Policy includes: a template line exactly `<include:policy/<dir>/<name>.md>`
is replaced by `templates/policy/<dir>/<name>.md` (the pack overlay's copy
first). The fragment's lines then render like the including file's, so
placeholders, operations, strategy lines and control-item blocks work inside
it, and problems report the fragment's own `file:line`. Bounded: one level,
so an include line inside a fragment fails closed, as does a missing
fragment or an include that is not a whole line (#1184).

Render-time notes: each file in `runtime.options.notes.render.<role>` (path
relative to the project file) is appended verbatim to that role's
`briefs/<role>.md` or `runtime/<role>.md`, under `## Render note: <path>`,
after the precheck block. The size budget and the render-vs-live drift check
see them like any other brief text. A nonempty list for a role with no such
brief in the selected runtime fails the render, naming the key and runtime.

Every `<name>` token is a placeholder. Install-time placeholders are
replaced from resolved profile keys (the "Replaces" columns of
[docs/profile.md](../docs/profile.md#keys)):

| Placeholder | Profile key |
|---|---|
| `<owner>`, `<repo>`, `<default-branch>` | `repo.owner`, `repo.name`, `repo.default_branch` |
| `<author-login>` | `identities.<role>.gh_user` of coordinator, builder and synthesizer; they must be equal |
| `<reviewer-login>` | `identities.reviewer.gh_user` |
| `<user-logins>` | `identities.owners`, joined with `", "` so `["<user-logins>"]` becomes one JSON string per login |
| `<state-dir>`, `<worktree-root>`, `<toolchain-bin>` | `paths.state_dir`, `paths.worktree_root`, `paths.toolchain_bin` |
| `<timezone>` | `runtime.timezone` |
| `<mdstack>`, `<merge-grant>`, `<hold-label-blocks>` | `paths.mdstack`, `runtime.options.merge_grant`, `runtime.options.hold_label_blocks` (a boolean renders as `true` / `false`) |
| `<release-delegation>` | `runtime.options.release_delegation` (`none` when absent) |
| `<merge-grant-scope>`, `<spec-paths>` | `runtime.options.merge_grant_scope`, `spec.paths`, rendered as JSON arrays; absent keys render the defaults `["approved"]` and `["docs/specs/**"]` |
| `<spec-home>` | the coordinator spec bookend's specs home: ``the external spec home `<url>` `` for `docs.specs_external`, else `docs.homes.specs` with a trailing `/`, else `` `docs/specs/` ``; the Grok Bot `<include:docs/roles.md>` names the same home in its bookend rule |
| `<fallback-engine>` | `engines.fallback_engine` |
| `<tested-update>` | `strategy.update_from_base` from the change backend's pack manifest (`merge` when undeclared), as the synthesizer's update wording |
| `<CoordinatorBot>`, `<BuilderBot>`, `<ReviewerBot>`, `<SynthesizerBot>` | `identities.<role>.name` |
| `<CoordinatorTitle>`, `<CoordinatorEmoji>` (and each role's equivalent) | `identities.<role>.title`, `identities.<role>.emoji` |
| `<op:<concern>.<operation>>` | the command in `backends/<backend>.toml` for the concern's backend; the operation must not be `unsupported` |
| `<op:<concern>.<operation>\|<concern>.<operation>>` | the first listed operation the backend supports; with none, it fails on the first |

Run-time placeholders are kept verbatim, because they are filled per task:
the rest of the [templates table](../templates/README.md#placeholders)
(`<n>`, `<sha7>`, `<head-sha>`, `<k>`, `<pass>`, `<role>`, ...) and
`<issue#>`, `<pr>`, `<tier>`, `<engine>`, `<model>`, `<effort>` from
[docs/roles.md](../docs/roles.md). A test keeps every placeholder in the
templates table known to the renderer, and the parity test keeps every
placeholder in the real inputs in that table with its profile key.

Parity (`test-render-parity.py`): renders `templates/` from
`profiles/default.toml`, alone and layered with the parity project values
(`fixtures/parity/crew.toml`), and diffs each `runtime/*.md` against the
pre-conversion template text (`fixtures/parity/pre/*.md.txt`) filled in by
plain string replacement, with trailing whitespace normalized. Any diff fails.
A template edit therefore updates its `pre/` copy in the same PR.

Fail closed: every problem prints as `file:line: reason` and the run exits 1
without writing any file. Reasons: `unknown placeholder <name>`, `unknown
operation <concern>.<operation>`, `unsupported capability
<concern>.<operation>` (the profile's `capabilities` override the pack
manifest `connectors/<backend>/manifest.toml`; undeclared is unsupported), and
`missing mapping` (a profile key not set or ambiguous, no command in the
backend file, a missing role brief or runtime binding), `invalid
placeholders.kept` and an unreadable render-time note. On success it prints
each written path and exits 0.

## Release workflow

`.github/workflows/release.yml` (the release gate in the
[protocol gate registry](../docs/protocol.md#gate-registry); design in
[release.md](../docs/release.md#steps)). It never commits: the cut
(`changelog-cut.py`) lands first as a normal crew PR.

- **Release on cut merge (approved design, #274; workflow follows in #387):**
  landing the CHANGELOG cut PR triggers validation and bundle build on the
  pushed merge commit, then tagging and publishing in the same run. The cut
  PR's CI validates the real cut before landing. The publish job posts the
  release link on the linked release issue and closes it.
- **Other release PRs:** PRs touching the workflow or release scripts
  validate and build on a simulated cut; they never tag or publish.
- **Approval:** the owner gives per-PR `pass=steer cmd=merge-ok sha=<head>`
  on the cut PR at its head, or the coordinator's there citing a recorded
  [release delegation](../docs/release.md#release-delegation); the standing
  merge grant never covers a cut PR. Before
  tagging, the publish job verifies the marker on the merged cut PR and that
  the push actor matches the repository variable `RELEASE_OWNER`.
- **Dispatch fallback** on `main` with `version` (`X.Y.Z`, no `v`) and
  `dry_run` (default `true`) remains. Dry runs validate and build without
  tagging or publishing. Only the owner dispatches a real fallback, with the
  same cut-PR approval and actor check. Until #387 lands, the existing
  dispatch workflow is the manual fallback.
- **Owner setup:** set `RELEASE_OWNER` to the owner's login; unset means
  publishing refuses. Private repos on GitHub Free cannot require reviewers
  on the `release` environment, and shared owner-level accounts pass the
  actor check, so no role invents owner merge-ok authorization. Neither a
  standing grant nor an auto-applied default publishes a release.
