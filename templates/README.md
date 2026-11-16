# Routine and listener templates

One file per routine, each with a `json` trigger block and a prompt block.
Copy a template onto the bot, replace every placeholder, and keep the wiring
doc ([wiring.md](runtimes/grok-bot/wiring.md)) in sync. These are templates only: nothing here
creates or changes a live routine. For the roles and markers they rely on, see
[../docs/architecture.md](../docs/architecture.md) and the
[docs index](../docs/README.md).

## Files

Two trees. Runtime-neutral (core) templates stay at the top of `templates/`,
so their paths and the scripts that read them are unchanged. Templates bound
to one runtime live under `templates/runtimes/<runtime>/`:
[Grok Bot](../docs/runtimes/grok-bot.md), [tmux](../docs/runtimes/tmux.md)
and [session](../docs/runtimes/session.md). Role policy shared across
runtimes lives once under [`templates/policy/`](policy/README.md) and is
included by the runtime templates. The `crew:needs-mirror` path rule keys on
the `templates/` prefix, so it covers every tree.

### Core (runtime-neutral)

| File | Purpose | Owner |
|---|---|---|
| [flavor-suggestion-issue.md](flavor-suggestion-issue.md) | Owner-decided flavor suggestion; never auto-applied | `<CoordinatorBot>` |
| [handoff-manifest.md](handoff-manifest.md) | Runtime handoff `offered` post that `mdstack handoff manifest` fills ([handoff](../docs/handoff.md#manifest)) | `<CoordinatorBot>` |
| [intake-candidate.md](intake-candidate.md) | Self-improve intake candidate card (issue body) | `<CoordinatorBot>` |
| [metrics-regression-issue.md](metrics-regression-issue.md) | Issue body for the metrics gate (`harness: latency/quality regression`) | `<CoordinatorBot>` |
| [owner-return-brief.md](owner-return-brief.md) | Standalone return brief for recorded owner away mode | `<CoordinatorBot>` |
| [product-readme.md](product-readme.md) | Seed `README.md` for a product or prove-it repo (problem, what it is, how to run, how the crew works, status); not a routine | `<CoordinatorBot>`, `<BuilderBot>` |
| [evidence/README.md](evidence/README.md) | Evidence adapters index: [cli-exit-stdout.md](evidence/cli-exit-stdout.md), [web-screenshot.md](evidence/web-screenshot.md) | `<BuilderBot>`, `<ReviewerBot>` |
| [spec.md](spec.md) | Seed for a spec in a project's `docs/specs/` ([essential doc set](../docs/project-doc-set.md#essential-doc-set)): status banner, stable `REQ-` requirements with applies-when, obligation, acceptance criteria and verification; not a routine | `<CoordinatorBot>`, `<BuilderBot>` |
| [step-summary.md](step-summary.md) | `summary.md` skeleton for a builder run (see [observe](../docs/observe.md)); not a routine | `<BuilderBot>` |
| [triage-flavor.md](triage-flavor.md) | Issue rigor record, default and reason for lowering | `<CoordinatorBot>` |

### Grok Bot runtime (`runtimes/grok-bot/`)

| File | Routines | Owner |
|---|---|---|
| [coordinator-steering-dispatcher.md](runtimes/grok-bot/coordinator-steering-dispatcher.md) | Steering dispatcher | `<CoordinatorBot>` |
| [coordinator-after-merge.md](runtimes/grok-bot/coordinator-after-merge.md) | After merge (`pr-merged`, `ci-failed` on `<default-branch>`) | `<CoordinatorBot>` |
| [coordinator-stuck-pr-sweeper.md](runtimes/grok-bot/coordinator-stuck-pr-sweeper.md) | Stuck-PR sweeper (schedule) | `<CoordinatorBot>` |
| [builder-b1.md](runtimes/grok-bot/builder-b1.md) | B1 build intake (`issue-assigned`) | `<BuilderBot>` |
| [builder-b2.md](runtimes/grok-bot/builder-b2.md) | B2 per-PR watch | `<BuilderBot>` |
| [reviewer-validator.md](runtimes/grok-bot/reviewer-validator.md) | V1 PR intake (`pr-opened`) | `<ReviewerBot>` |
| [reviewer-v2-watch.md](runtimes/grok-bot/reviewer-v2-watch.md) | V2 per-PR watch | `<ReviewerBot>` |
| [reviewer-engines.md](runtimes/grok-bot/reviewer-engines.md) | Reviewer engine choice (state file) | `<ReviewerBot>` |
| [synthesizer.md](runtimes/grok-bot/synthesizer.md) | S1 `review-approved` | `<SynthesizerBot>` |
| [researcher.md](runtimes/grok-bot/researcher.md) | Researcher worker brief (no routine; wiring section 2e) | `<CoordinatorBot>` |
| [wiring.md](runtimes/grok-bot/wiring.md) | Per-repo wiring doc template | all |

Grok Bot also renders `skills/eng-pr-pipeline/SKILL.md` and
`skills/eng-crew-roles/SKILL.md` beneath `runtime/`. These inputs include
`docs/protocol.md` and `docs/roles.md` from the running bundle, respectively,
with skill frontmatter. The include directives are restricted to those two
reviewed docs. Their illustrative placeholders remain literal; relative
Markdown links point into `paths.mdstack`. Deploy the whole render to
`paths.live_dir` so the existing render-vs-live drift check covers skills
and routines together. Box skill installation uses these rendered files;
routine creation remains a human step.

### tmux runtime (`runtimes/tmux/`)

Role briefs for the [tmux runtime](../docs/runtimes/tmux.md), rendered from
[profiles/tmux.toml](../profiles/tmux.toml) and read by `mdstack up` /
`mdstack spawn`; golden files in `dev/tests/fixtures/render/tmux/`.

Builder and solo briefs include `docs/roles.md#pr-conventions` from the
running bundle. This restricted include keeps the PR and fix contract in one
source; illustrative placeholders remain for the session to fill, and link
labels render as plain text for a portable paste-ready contract.

| File | Brief | Owner |
|---|---|---|
| [coordinator.md](runtimes/tmux/coordinator.md) | Window 0: drain the wake queue, spawn / send / kill, keep the watcher armed | `<CoordinatorBot>` |
| [builder.md](runtimes/tmux/builder.md) | Builder window per issue: build, then fix rounds by inbox with `ack:` | `<BuilderBot>` |
| [solo.md](runtimes/tmux/solo.md) | Paste-ready owner-driven session; shares the builder PR contract and rendered precheck | owner session |
| [reviewer.md](runtimes/tmux/reviewer.md) | One review or validate pass, fresh session, verdict file, `done:`, exit | `<ReviewerBot>` |
| [synthesizer.md](runtimes/tmux/synthesizer.md) | Session window: §7 gate, serial land under `flock` | `<SynthesizerBot>` |
| [researcher.md](runtimes/tmux/researcher.md) | One research request, fresh session: signed finding on the source issue, `done:`, window closed | `<ResearcherBot>` |

### session runtime (`runtimes/session/`)

Rendered for `runtime.name = "session"` ([binding](../docs/runtimes/session.md)).
Each worker brief ends where the coordinator appends the `mdstack brief` run
block; workers start without a runtime-set environment.

| File | Brief | Owner |
|---|---|---|
| [coordinator.md](runtimes/session/coordinator.md) | Hosted or hand-started coordinator session: ownership guard (`mdstack ownership --runtime session`), dispatch caps and the `mdstack brief` recipe, and the [handoff](../docs/handoff.md) outgoing and incoming steps; with no control item, one paragraph replaces the guard and handoff sections | `<CoordinatorBot>` |
| [builder.md](runtimes/session/builder.md) | One build or fix pass per run: the tmux builder contract, status in `$CREW_STATUS` | `<BuilderBot>` |
| [reviewer.md](runtimes/session/reviewer.md) | One review, validate or recheck pass per run: the tmux reviewer contract | `<ReviewerBot>` |
| [synthesizer.md](runtimes/session/synthesizer.md) | One land run per dispatch: the tmux synthesizer contract, land lock and merge trains | `<SynthesizerBot>` |

### Backend command mappings (`backends/`)

| File | Contents |
|---|---|
| [github.toml](backends/github.toml) | The `gh` command per operation, from the [GitHub interface mapping](../docs/backends/github.md#interface-mapping); renderer input for `<op:<concern>.<operation>>` |

## Placeholders

Profile key: the resolved [profile](../docs/profile.md#keys) key the
[renderer](../scripts/README.md#renderer) fills the placeholder from. Run-time
placeholders are filled per task and render as written. An operation
placeholder `<op:<concern>.<operation>>` renders as that operation's command in
`backends/<backend>.toml`, for example [backends/github.toml](backends/github.toml).
`<op:a.b|c.d>` renders the first listed operation the backend supports, so
the researcher brief posts with `tracker.comment` where `markers.write-item` is
unsupported.
A line that starts with `<strategy:merge>` or `<strategy:rebase>` is not a
placeholder: it renders, without that prefix, only when the change backend's
[update strategy](../docs/interfaces.md#rebase-update-from-base) matches
(`merge` when undeclared), so a merge render stays byte-identical.
A line exactly `<control-item:set>` or `<control-item:none>` opens a block
that a line exactly `<control-item:end>` closes; the block renders, without
its marker lines, only when `repo.control_item` is set (a tracker-native
item counts) or unset, respectively.
A line exactly `<include:policy/<dir>/<name>.md>` is replaced by that
[policy fragment](policy/README.md), whose lines then render like the
including file's, so a role's shared policy is authored once (#1184).
A title placeholder `<title:<role>/<pass>>` renders the head of that role's
post title, `<emoji> <name> · <Pass>`, from the role's `identities` name and
emoji (no emoji with `report.emoji = false`), through the one canonical
format in `core/post-title.py` ([protocol §4](../docs/protocol.md#4-marker-conventions), #1946).

| Placeholder | Meaning | Profile key |
|---|---|---|
| `<owner>` | GitHub owner of the repo | `repo.owner` |
| `<repo>` | Repo name | `repo.name` |
| `<control-item>` | Repo ownership control issue; `none` preserves legacy operation | `repo.control_item` |
| `<runtime-id>` | Runtime name joined to instance with `@`; absent instance renders `unconfigured` | `runtime.name`, `runtime.instance` |
| `<default-branch>` | The repo's default branch (PR base, merge target, `ciBranch`) | `repo.default_branch` |
| `<author-login>` | Author identity: opens branches and PRs, merges. Shared by coordinator, builder, synthesizer, researcher | `identities.coordinator.gh_user`, `identities.builder.gh_user`, `identities.synthesizer.gh_user`, `identities.researcher.gh_user` (must be equal; the researcher's defaults to the coordinator's) |
| `<reviewer-login>` | Reviewer identity: posts formal verdicts and steering signals. Must differ from `<author-login>` | `identities.reviewer.gh_user` |
| `<user-logins>` | The user's own GitHub logins, used as `userAllowlist` and as the accepted commenters for steering. Expands to one JSON string per login | `identities.owners` |
| `<state-dir>` | Shared state directory on the bot box; per-repo state is `<state-dir>/<owner>__<repo>/` (claims, locks, wiring, sweeper state) | `paths.state_dir` |
| `<CoordinatorBot>` | Name of the coordinator bot (also the steering dispatcher) | `identities.coordinator.name` |
| `<BuilderBot>` | Name of the builder bot | `identities.builder.name` |
| `<ReviewerBot>` | Name of the reviewer-validator bot | `identities.reviewer.name` |
| `<SynthesizerBot>` | Name of the synthesizer bot | `identities.synthesizer.name` |
| `<ResearcherBot>` | Name of the researcher bot | `identities.researcher.name` |
| `<CoordinatorTitle>` | Coordinator persona title | `identities.coordinator.title` |
| `<CoordinatorEmoji>` | Coordinator persona emoji | `identities.coordinator.emoji` |
| `<BuilderTitle>` | Builder persona title | `identities.builder.title` |
| `<BuilderEmoji>` | Builder persona emoji | `identities.builder.emoji` |
| `<ReviewerTitle>` | Reviewer persona title | `identities.reviewer.title` |
| `<ReviewerEmoji>` | Reviewer persona emoji | `identities.reviewer.emoji` |
| `<SynthesizerTitle>` | Synthesizer persona title | `identities.synthesizer.title` |
| `<SynthesizerEmoji>` | Synthesizer persona emoji | `identities.synthesizer.emoji` |
| `<ResearcherTitle>` | Researcher persona title | `identities.researcher.title` |
| `<ResearcherEmoji>` | Researcher persona emoji | `identities.researcher.emoji` |
| `<TeamName>` | The crew's team name; empty when unset (for signatures, #1291) | `identities.team` |
| `<CoordinatorSignature>` | Coordinator signature head: `— <emoji> <name> (<title>) · <team>`; emoji and team optional (#431, #1291) | `identities.coordinator.name` |
| `<BuilderSignature>` | Builder signature head: `— <emoji> <name> (<title>) · <team>`; emoji and team optional (#431, #1291) | `identities.builder.name` |
| `<ReviewerSignature>` | Reviewer signature head: `— <emoji> <name> (<title>) · <team>`; emoji and team optional (#431, #1291) | `identities.reviewer.name` |
| `<SynthesizerSignature>` | Synthesizer signature head: `— <emoji> <name> (<title>) · <team>`; emoji and team optional (#431, #1291) | `identities.synthesizer.name` |
| `<ResearcherSignature>` | Researcher signature head: `— <emoji> <name> (<title>) · <team>`; emoji and team optional (#431, #1291) | `identities.researcher.name` |
| `<report-status>` | The report skeleton's fixed status set, with emoji unless `report.emoji = false` (#431) | `report.emoji` |
| `<report-merge-status>` | Its `landed` and `blocked` statuses, for synthesizer merge posts (#431) | `report.emoji` |
| `<flavor-name>` | Render baseline name; live item/path resolution still applies | `flavor.name` |
| `<flavor-review>` | Render baseline review; live item/path resolution still applies | `flavor.review` |
| `<flavor-validation>` | Render baseline validation; live item/path resolution still applies | `flavor.validation` |
| `<flavor-evidence>` | Render baseline evidence; live item/path resolution still applies | `flavor.evidence` |
| `<flavor-caps>` | Render baseline caps; live item/path resolution still applies | `flavor.caps` |
| `<flavor-merge>` | Render baseline merge; live item/path resolution still applies | `flavor.merge` |
| `<flavor-builder>` | Render baseline builder; live item/path resolution still applies | `flavor.builder` |
| `<flavor-validation-scope>` | Render baseline validation scope (`repo` or `bounded`); live item/path resolution still applies | `flavor.validation_scope` |
| `<flavor-selfgate-engine>` | Profile self-gate engine (`different` or `same`, default `different`); read only for an express change | `flavor.selfgate_engine` |
| `<precheck-test>` | Configured test command, in backticks; unset renders `` `n/a` `` | `builder.precheck.test` |
| `<precheck-lint>` | Configured lint command, in backticks; unset renders `` `n/a` `` | `builder.precheck.lint` |
| `<reviewed-base-sha>` | Full merge-base SHA pinned when the review starts; reused by validation and final verdict | none (run-time) |
| `<n>` | A PR or issue number. In a trigger it is a JSON number once filled in | none (run-time) |
| `<sha7>` / `<head-sha>` | Short or full 40-character head commit SHA | none (run-time) |
| `<k>` | Verdict round number, starting at 1 | none (run-time) |
| `<pass>` | Review pass name, used in worktree names (for example `review`, `validate`) | none (run-time) |
| `<role>` | Role short name, used in worktree names | none (run-time) |
| `<worktree-root>` | Directory holding per-run worktrees; each run uses its own `<worktree-root>/<n>-<sha7>-<role>-<pass>/` | `paths.worktree_root` |
| `<pass\|changes>` | Verdict value in a marker: `pass` or `changes` | none (run-time) |
| `<cmd>` | A steering command name | none (run-time) |
| `<comment id>` | ID of the PR comment that carried a steering command (`cmd-id` in the marker) | none (run-time) |
| `<note>` | Free-text note after a steering command such as `rework` | none (run-time) |
| `<fallback-engine>` | Second allowed engine for the reviewer fallback (private repos: Claude Code or Codex only) | `engines.fallback_engine` |
| `<tested-update>` | The synthesizer's tested-with-default-branch fix: `update-branch or green train`, or under a `rebase` backend `rebase onto the default branch and upload (no trains)` | `strategy.update_from_base` (resolved from the change backend's pack manifest; `merge` when undeclared) |
| `<planned \| applied \| live>` | Status of a wiring step; pick one and add a date | none (run-time) |
| `<timezone>` | IANA timezone for a schedule trigger | `runtime.timezone` |
| `<toolchain-bin>` | Directory of the repo's required toolchain, put on `PATH` before any commit or push | `paths.toolchain_bin` |
| `<mdstack>` | Absolute path of the mdstack checkout; tmux briefs cite `<mdstack>/docs/` | `paths.mdstack` |
| `<max-active-milestones>` | Maximum open milestones for new coordinator build dispatch, in milestone order | `runtime.options.max_active_milestones` |
| `<builder-cap>`, `<reviewer-cap>` | session coordinator's concurrent builder runs and reviewer passes | `runtime.options.builders`, `runtime.options.reviewers` |
| `<present-builder-cap>`, `<present-reviewer-cap>` | session coordinator's owner-present builder and reviewer limits | `runtime.options.present_builders`, `runtime.options.present_reviewers` |
| `<session-backend>` | session coordinator's worker launcher: `native` subagents or `cli` runs; `hosted` renders control-plane session text instead (#1052) | `runtime.options.session_backend` |
| `<lone-pr-land>` | tmux lone-ready-PR landing policy | `runtime.options.lone_pr_land` |
| `<train-min>`, `<train-window>` | tmux synthesizer batching threshold and maximum wait in seconds | `runtime.options.train_min`, `runtime.options.train_window` |
| `<merge-grant>`, `<hold-label-blocks>` | bounded live-profile grant lookup (`none` stays literal) and whether `crew:hold` blocks | `runtime.options.merge_grant`, `runtime.options.hold_label_blocks` |
| `<merge-grant-scope>`, `<spec-paths>` | tmux synthesizer's grant scope list and spec globs, as JSON arrays; absent keys render `["approved"]` and `["docs/specs/**"]` | `runtime.options.merge_grant_scope`, `spec.paths` |
| `<spec-home>` | Coordinators' spec bookend home: the configured specs directory, default `` `docs/specs/` ``, or ``the external spec home `<url>` `` | `docs.homes.specs`, `docs.specs_external` |
| `<release-delegation>` | tmux and session coordinators' recorded owner release delegation (words and link), or `none` | `runtime.options.release_delegation` |
| `<mirror-deferral>` | tmux synthesizer's recorded standing mirror deferral source and scope | `runtime.options.mirror_deferral` |
| `<mirror-gate>` | tmux synthesizer's mirror-gate paragraph: the standing-deferral rule for `live-copy`, the `n/a` by profile rule for `none` ([tmux](../docs/runtimes/tmux.md#no-live-copy-to-mirror-877)) | `runtime.options.mirror` |
| `<land-step>` | tmux and session synthesizer's step 3: today's locked land for `sync` (the session one by its `mkdir` lock); for `async`, `mdstack land request`, the merge record and `mdstack land resume`, with the `land.serializes` and `land.tests_against_tip` alternatives ([asynchronous land](../docs/interfaces.md#asynchronous-land-design)) | `land.mode` (change backend's manifest) |
| `<land-publish>` | tmux builder's publish line after opening the PR, only when the backend opens drafts; otherwise nothing | `land.opens_draft` (change backend's manifest) |
| `<land-rule>` | tmux synthesizer's Land rule opening (session: after its two rules): under `land.tests_against_tip`, every ready PR lands alone through step 3 with no update-from-base or train; otherwise nothing | `land.tests_against_tip` (change backend's manifest) |
| `<land-stack>` | session synthesizer's Land rule, after `<land-rule>`: under `land.stack`, the stack-land recipe (every member's gates at its own head, the whole stack refused on one failure, one `mdstack land stack` request, one merge post per member, `stack-done` and resume, with the `land.serializes` and `land.stack_tests_against_tip` alternatives; [stack land](../docs/interfaces.md#stack-land)); otherwise nothing, and tmux never renders it | `land.stack` (change backend's manifest) |
| `<parent>` | Number of the parent spec issue | none (run-time) |
| `<date>`, `<reason>` | Date and reason recorded in a state file (for example a quota steer) | none (run-time) |
| `<sweep-id>`, `<outcome>`, `<band>`, `<shadow\|apply>` | A triage sweep's UTC start, a triage record's decision slug, its priority band `P0`–`P3` and the sweep's `triage.mode` ([protocol §4](../docs/protocol.md#4-marker-conventions)) | none (run-time) |
| `<UTC timestamp>` | Time written on a claim file's `heartbeat:` line | none (run-time) |
| `<full-40-char-head-sha>` / `<new-head-sha>` | Full 40-character head SHA in a marker; `<new-head-sha>` is the head after a merge-up | none (run-time) |
| `<issue#>` | The issue a PR closes, the tracker item passed as `crew-precheck.py --item` | none (run-time) |
| `<harness>` | Harness actually used by the authoring session, including fallback | none (run-time) |
| `<pr>`, `<engine>`, `<model>`, `<effort>` | PR number of an evidence path; engine, model and effort that wrote a round ([roles](../docs/roles.md)) | none (run-time) |
| `<worktree>`, `<run-id>`, `<file>` | A run's worktree path, step-summary run ID or CI run ID, and a file path | none (run-time) |
| `<run-url>` | Default-branch CI run URL in a direct-land blocker | none (run-time) |
| `<gate>` | Issue number a coordinator hold-until note waits on | none (run-time) |
| `<branch>`, `<t>`, `<M>`, `<login>`, `<tag>`, `<version>` | Command arguments in [backends/github.toml](backends/github.toml): branch, title, milestone, login, state tag, release version | none (run-time) |
| `<project>`, `<url>`, `<id>`, `<item>`, `<status-field>`, `<option>` | Project board arguments in [backends/github.toml](backends/github.toml) | none (run-time) |
| `<APPROVE\|REQUEST_CHANGES>` | Formal verdict event in [backends/github.toml](backends/github.toml) | none (run-time) |

Quoted placeholders such as `"<n>"` in JSON blocks keep the template valid
JSON. Replace the whole quoted string with a number when filling it in.

## Event to consuming role

Grok Bot runtime: see
[wake wiring](../docs/runtimes/grok-bot.md#wake-wiring-event-to-consuming-role)
and [lighter-lane routing](../docs/runtimes/grok-bot.md#lighter-lane-routing).

## Open items

None.

## Routine limits

Grok Bot runtime: see [routine limits](../docs/runtimes/grok-bot.md#routine-limits).

## Credentials

Templates refer to credentials only by mechanism, for example
`GH_TOKEN=$(gh auth token --user <author-login>)`. Never paste a token, key or
header into a template or a wiring doc.
