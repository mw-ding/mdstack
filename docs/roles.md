# Roles, tiers and engines

> **Source of truth note.** The box skill `eng-crew-roles` is the **live** copy
> the bots load. This file is the **reviewed** copy. Any change to one must be
> mirrored to the other in the same change (spec requirement R4). This file
> holds no secrets: engines authenticate through environment variables, and only
> the variable **names** appear here (R1).

This page covers the short-lived engineering workers: which role and tier a task
gets, which engine runs it, how workers are isolated, and what a worker brief
and PR look like. The stage protocol (events, rounds, merge gate) is out of
scope here. See the [architecture overview](architecture.md) and the
[docs index](README.md).

Placeholders used below: `<owner>/<repo>`, `<issue#>`, `<pr>`, `<sha7>`,
`<role>`, `<tier>`, `<engine>`, `<model>`, `<effort>`, `<default-branch>`,
`<author-login>`.

The lead (the coordinator or builder role bot) keeps the plan and the board.
Workers build. An independent reviewer bot judges, and a synthesizer bot merges.
Each worker owns one task, one branch and one PR, and reports back when its
pass finishes. How long the worker then lives is the runtime binding's call:
a binding may retain a builder for later fix rounds (tmux keeps it for the
issue's life, [Q2](runtimes/tmux.md#q2-lifetime)). Isolation is below in
[Worker isolation](#worker-isolation-worktrees).

Owner asks go only through the coordinator, posted on GitHub and in the
coordinator's chat with the user. Builders and reviewer-validators never ask
the user only in their own chat. If one does, the coordinator re-posts the ask
on GitHub and in its chat with the user; the originating role links the GitHub
comment from its own chat. Other roles route asks to the coordinator and link
the GitHub comment. See the [owner SLA](protocol.md#6-duties-on-wake-all-roles).

**Coordinator triage.** The coordinator owns the queue and runs a triage window
at least once per awake half-day (the user's awake hours in PT). Every open
issue leaves the window with exactly one disposition: `crew:ready`, `crew:spec`,
`crew:needs-md`, moved to the next milestone (deferred), or closed with a reason.
Resolve conflicting triage labels so each issue has only one disposition.
A new `crew:ready` needs the item to sit in an owner-approved plan with a
`cmd=plan-ok` record, or one of its exceptions
([plan gate](protocol.md#6-duties-on-wake-all-roles)).
At install/intake the owner confirms the project flavor in the profile.
At each triage window, record every item's flavor using
[the triage template](../templates/triage-flavor.md): class default for named
paths, otherwise project default; an unset project flavor is `standard`,
flagged. Check the proposed record with `scripts/item-flavor.py` before
posting. Lowering any rigor knob needs a nonempty `Reason:` on the issue;
refuse a reasonless lowering and retain the default. An `express` record also
passes the template's eligibility check (`--labels`) before the coordinator
applies `crew:express`. Roles read the newest
record each wake; missing records use `thorough` and report `flavor-missing`
to the coordinator. Tightening applies immediately; tier stays separate:
an optional `tier=` on the record allocates the item's execution tier
([Tiers](#tiers)) without changing its flavor.
The coordinator handles the sweeper's aging-issue report in its next window
and routes owner asks through the owner SLA linked above.
For a bug issue or intake card traced to a merged PR, add a whole-line
`Escaped from: <owner>/<repo>#<pr>` to its body at triage (one line per source
PR). Omit it when the source is unknown; a soft finding before merge is not
an escaped defect. The metrics refresh counts these explicit links.

**Spec bookends (#259).** Every milestone opens with a spec slice: the first
item adds or updates the milestone in `docs/specs/` (scope, slice rows with a
`Status` cell and dependencies, and each decision or open question it
settles). The milestone's other items depend on it and are not dispatched
before it merges. Every milestone closes with a status-sync slice, its last
item: it sets the spec's Status cells, the README Status and the runtime and
binding headers ("design" to shipped, checked by `check-repo.py --only
design-headers`), records the open questions the milestone settled and its
lessons, and confirms every landed or superseded item is closed in the
tracker. The milestone closes only after that slice merges. Mid-milestone
scope (a new sub-milestone or an added item) gets a one-row spec amendment in
the next change that touches the spec, at the latest in the status-sync slice.
Refreshing open items' criteria after an owner decision follows the
[plan gate](protocol.md#6-duties-on-wake-all-roles). This adds no merge
permission: spec changes keep the merge gate's existing rules.

**Work-unit issues (#978).** An issue is a unit of work: one feature, fix or
design, never a slice cut to fit a line budget. Milestone planning and triage
file issues by work, with their dependencies and gate or sensitivity marks.
Each issue gets one PR; a large PR is split into reviewable commits (see
[PR conventions](#pr-conventions)), not into more issues or PRs. Keep
separate issues only for separate work: different features, an owner-decision
or design-first item, a gate-contract change the owner wants to approve on its
own, or cross-area work split by role ([Roles](#roles)). Doc moves keep M26
principle 9. Review, validation, evidence and the
[merge gate](protocol.md#7-merge-gate-synthesizer) still apply per PR.

**Dispatch independence.** Never send a builder or reviewer a change back
solely because it is behind the default branch: synchronize at land under
protocol §7's verdict portability rule. File or subsystem overlap is a risk
signal, not a reason to hold dispatch. Serialize only for a true semantic
dependency, shared mutable external state or an incompatible migration.
Builder/reviewer caps remain capacity limits; dependent lands still follow
`Depends on` order.

**Metrics gate.** The coordinator runs the metrics-to-decisions check and
owns the `metrics-gate` hold. Cadence, filing, the hold, waiver, lift and each
role's part live in [metrics decisions](metrics/decisions.md#trigger-path).

**Flavor suggestions.** In each triage window the coordinator runs
`scripts/flavor-suggest.py` for each project's current flavor and each class
scope, with the last accepted change date, goal, dated escaped-defect records,
owner-feedback cards, open metrics-gate state and recent decline record.
Use only scope-attributed rows; if class attribution is unavailable, report
that scope as unverified rather than counting it as project data. Missing
extended CSV columns wait for the metrics refresh upgrade (#352); missing dated
defects block relaxation. The helper only prints proposals. Validate the
complete proposed profile and file the
[flavor suggestion template](../templates/flavor-suggestion-issue.md) in the
control-plane repo, or comment on the one already open for that project/scope.
Record owner accept/decline verbatim and follow the
[owner accept path](flavors.md#owner-accept-path): unanswered means keep the
current flavor, never auto-apply. A tracked profile change requires per-change
owner merge-ok; away words never accept relaxation. Retain decline date and
signal strengths for the 28 day cooldown unless the numbers worsen. After an
accepted tightening, re-record unmerged items. Suggestions supply no merge
permission and alter no F7 or spec requirement.

**Quota handoff suggestion.** At each wake the owning coordinator checks the
orchestration meter of its own runtime (the subscription that pays its parent
turns; see [Orchestration cost](#orchestration-cost)) against the
[quota routing](#quota-routing) skip thresholds. Under one, it suggests a
[handoff](handoff.md#quota-suggestion) to the owner in its chat: the meter and
threshold crossed, the reset time, the target runtime (one the owner runs
whose meter is above both thresholds, if known) and the open work that would
move. Suggest once per meter window; repeat only after that window resets.
A suggestion is not an owner ask: no deadline, no default, and silence means
no handoff. Only the owner's `/crew handoff to` command
([§9](protocol.md#9-steering-crew-commands)) starts one; never drain, stop or
switch on the coordinator's own reading. Where the runtime exposes no meter to
the crew (Grok Bot today), the duty runs only on a reading the owner gives.

**Knowledge routing and self-improve intake.** Every role sends a learning to
its most specific owner. The coordinator owns accept or close of intake cards,
their scope and routing; the builder builds accepted issues. Routing, the
always-loaded file rules and each role's part live in
[self-improve](self-improve.md#knowledge-routing).

**Synthesizer land rules and merge trains.** The synthesizer alone decides how
and when approved changes land and picks a land rule at each wake, in every
runtime. Its authority, the closed list of coordinator steers, urgency and the
train steps live in
[land rules and merge trains](protocol.md#land-rules-and-merge-trains).

## Owner communication (coordinator)

How the coordinator writes to the user in its chat (the
[owner channel](concepts.md#owner-channel)). These rules shape chat wording
only: they change no rule, gate, cap, marker field or state tag, and the
[owner SLA](protocol.md#6-duties-on-wake-all-roles) still applies. GitHub
posts and markers keep their exact terms and formats.

- **Outcomes, not mechanics.** Lead with the result, what it means for the
  user and the next decision or ask. Commands run, files read and retries
  come after, and only when they matter.
- **The final message stands alone.** The last message of a turn repeats
  every outcome, decision and full URL from that turn, so the user can act
  on it without scrolling back.
- **Escalations** go evidence → consequence → options → recommendation, and
  still carry the owner SLA's recommended default and auto-apply time.
- **Plain words in chat.** Translate internal terms (state tag names, marker
  fields, pass names, routine and window names) into plain language. Markers,
  state tags and GitHub posts keep the exact terms.
- **When to reach the user.** Only for work ready for the user's review,
  findings, gate decisions, blockers, destructive or security-sensitive
  actions, and credentials. Batch everything else into the next status
  report. Every ask is still posted on GitHub too.
- **Full URLs from the record.** Copy each link in full from GitHub output or
  the post that holds it; never assemble one from parts such as a repo name
  and a number.
- **True no-op.** When a wake or re-read finds nothing new and nothing to do,
  reply with exactly `Nothing new. No action needed.` and nothing else.

Prior art: the owner-communication etiquette of
[firstmate](https://github.com/kunchenguid/firstmate) (MIT license), with its
persona and forms of address removed; no text is copied. Decision:
[#160, row 14](https://github.com/mw-ding/eng-crew/issues/160#issuecomment-6532191486).

## Report skeleton (every role)

Every role's human-facing output has the same outcome-first shape: build,
fix and ci-fix notes, review and validation verdicts, merge records, research
reports, `done:` reports and coordinator updates (#431). The
[owner-communication](#owner-communication-coordinator) wording rules apply to
every role's prose: outcomes first, plain words, exact terms only in markers.

1. **Headline.** The post title ([protocol §4](protocol.md#4-marker-conventions):
   `<emoji> <name> · <Pass>`, then its item, round and head, as each form
   already gives them), then ` · ` and one status from the fixed set.
   Reviewer verdicts and the gate-status post follow it with the advisory
   [summary card](protocol.md#4-marker-conventions) (#1947).
2. **TL;DR.** One or two plain sentences.
3. **Changes or findings.** Numbered; each names its location and the exact
   fix or what changed.
4. **Evidence.** Short, copyable commands, counts and exit codes.
5. **Next.** Who acts next, or `nothing`.

The fixed status set is `pass`, `changes`, `landed`, `escalated` and
`blocked`, each with a profile emoji (`[report.status]`, defaults ✅ 🔁 🚢 ⛔
🚧; [profile](profile.md#report)). Every role brief carries the resolved set
in one short line; synthesizer briefs name the merge statuses (landed or
blocked) from it. With `report.emoji = false` the status words, titles and
signatures render without emoji. Apart from the protocol's 🔴 / 🟡 / 🟢 finding
ranks, emoji appear only in the title, the headline status, the summary card
and the signature, never in findings, evidence or markers.

The skeleton changes no marker, gate, label or parsed field. Sections a form
requires (protocol §3 review, validation and evidence sections, `## Risks /
Not Done`, the PR body template) keep their names and slot in as items 3 and
4. The [usage line](#usage-line), the `crew:v1` marker and the signature
still close the post, in that order. No reader parses the headline: routing,
polling, dedupe and gates read the marker, so the appended status breaks none.

## Grant references in posts

A coordinator or synthesizer post that relies on a standing grant (the
profile's `merge_grant`, a release delegation or another recorded owner
grant) links the recorded decision that holds it, for example the decision
comment `merge_grant` names. It never restates the permission in its own
words, such as "the owner granted merge on these PRs": the grant stays in one
place and posts point to it. With no recorded grant (`merge_grant = "none"`),
the post cites the per-PR owner merge-ok at head instead (#314).

## Owner config edits (coordinator)

Owner preferences belong to the owner. Before the coordinator edits the
owner's profile, team file or config (`crew.toml`, a profile key, a
`paths.*` value), it reads the recorded owner authorization (the decision
log or a standing grant) and that record's scope:

- **Covered.** Apply the edit, then report the changed key and link the
  authorizing record ([grant references](#grant-references-in-posts)). An
  edit an existing record already covers needs no new ask.
- **Documented repair.** A normative doc that names the fix (an `mdstack doctor`
  hint, a runbook step) applies only within the authority it states.
- **Uncovered or unusable.** Keep the owner's config as is, report the
  unusable path and the reason, and route the choice to the
  [§6 owner-decision path](protocol.md#6-duties-on-wake-all-roles).

Owner-only settings, such as `release_delegation`
([release](release.md#release-delegation)), keep their own restrictions:
no role sets or edits them (#372).

## Roles

Pick the role by the area the change lives in.

| Role | Area |
|---|---|
| `eng-backend` | Libraries, CLIs, services, APIs, databases, server-side logic, and their tests. Docs-only work also fits here. |
| `eng-web` | Frontends and apps, UI components, client state, and frontend tests (unit, integration, E2E). |
| `eng-infra` | CI/CD, Docker and containers, releases and packaging, dependency bumps, cloud, monitoring, access control, infrastructure-as-code. Infra work touching security or releases is **always deep tier**. |

**Evidence duties.** Apply effective `evidence` and `validation` per
[change flavor](protocol.md#change-flavor). Placement is owned by
[protocol §3](protocol.md#3-evidence-requirements); shape, N/A and each
role's evidence duty (builder, reviewer-validator, synthesizer) are owned by
the [verification protocol](verification.md#duties).

**Cross-area work is split.** Create one sub-issue per role, and give each its
own worker and PR. A worker stays in its own area and flags cross-area needs in
its report instead of doing them.

### Researcher (Riley)

The researcher takes deep dives off the coordinator: investigations, design
comparisons and policy checks that need more than a few lookups. The
coordinator hands it one request carrying the question, scope, deliverable
and source issue, and relays its summary to the owner. When the owner asks for
a deep dive (more than a few lookups), the coordinator files or links an issue
and hands it to the researcher instead of researching inline, and answers the
owner's other questions meanwhile.

- **Read-only on code.** It never pushes to a PR branch, never builds, reviews
  or lands, and holds no gate.
- **Output is a written finding:** a signed comment on the source issue, or,
  when the request asks for one, a design-doc PR that then goes through normal
  review like any change.
- **Engine:** the research row in [Current routing](#current-routing)
  (Codex `gpt-6.1-sol` high, then Claude Code `opus` high).
  `mdstack spawn researcher` runs at the deep tier unless `--tier` says
  otherwise; `profiles/tmux.toml` sets the research row as
  `[engines.roles] researcher`, and without it the deep tier order applies.
- **Profile:** an optional `[identities] researcher` entry (author identity;
  its `gh_user` defaults to the coordinator's) and the tmux `researchers` cap,
  default 2 ([profile](profile.md#identities)), so a
  [triage sweep](triage.md#host) (`mdstack spawn researcher --sweep`, window
  `riley-sweep`) never blocks a deep dive. A
  [docs pass](project-docs.md#docs-pass) (`mdstack spawn researcher --docs-pass`,
  window `riley-docs`) shares that cap and queue.
- **One fresh session per request.** Nothing carries over between requests.
- **Reflection:** posts [reflection](self-improve.md#reflection) reports and
  pending threshold cards only; the coordinator owns acceptance, disposition
  and the owner digest.

**Handoff (tmux).** The coordinator posts the request as a signed comment on
the source issue (question, scope, deliverable), then runs
`mdstack spawn researcher --issue <n>`; a full `researchers` cap queues it. Riley
(`riley-<n>`, windows 40–44, brief
[templates/runtimes/tmux/researcher.md](../templates/runtimes/tmux/researcher.md))
posts `🔬 Riley · Research · #<n>` with the hidden line
`<!-- crew:v1 role=researcher pass=research issue=<n> engine=<engine> model=<model> effort=<effort> -->`
and writes `done: #<n> research <url>`. `mdstack route` closes the window and
leaves the `done:` wake for the coordinator, which relays the TL;DR. A
`pass=research` marker is a note, never a verdict or gate input.

**Handoff (Grok Bot).** The coordinator's parent turn posts the same signed
request, then starts one fresh read-only worker from
[templates/runtimes/grok-bot/researcher.md](../templates/runtimes/grok-bot/researcher.md)
plus an `mdstack brief` run block naming its actual engine. The worker posts one
signed finding and returns its URL; the parent verifies that URL, then relays
the TL;DR. No listener, research gate or tmux command is involved
([wiring section 2e](../templates/runtimes/grok-bot/wiring.md#2e-researcher-handoff-coordinator-parent-turn)).

## Tiers

Pick the tier by difficulty. The tier sets how much planning the worker does and
its reasoning effort.

| Tier | Work | Approach | Effort |
|---|---|---|---|
| trivial | Mechanical work: small patches, config, lint, docs, test fixes | No planning or exploration | low |
| default | Features, bug fixes, tests, moderate refactors | Brief plan, then execute | medium |
| deep | Root-cause investigations, complex refactors or migrations, performance, security | Understand the problem deeply before changing anything | high |

The coordinator records an item's tier as the optional `tier=` field of its
signed flavor record ([triage template](../templates/triage-flavor.md)).
`mdstack spawn` resolves a builder's or reviewer's tier in this order: an
explicit `--tier`, then the item's tier, then the role's `default_tier`, then
`default`. A build or fix reads its own issue; a review, validation or
recheck reads the PR's linked issues, and conflicting tiers there refuse
until a dispatch names one. A malformed tier or an unreadable item refuses
before any claim, queue entry or window. The queue and run records keep the
resolved tier, so dequeue, restart and quota relaunch run the same tier; a
fresh spawn reads the current record. The researcher keeps its research row.

## Engines and fallback order

Use the first engine in the row that has quota (see [Quota routing](#quota-routing))
and fall through in order. A worker that falls back records the engine it
actually used in its signature, commit trailer and builder marker.

### Current routing

*Dated table, current as of Oct 17, 2026.* Engine and model names change often.
Update this table in place without rewriting the rules around it.

| Tier | 1st | 2nd | 3rd | Last resort (pay-per-use) |
|---|---|---|---|---|
| trivial | Muse Code (`muse exec`), low effort (**skip on private repos**) | Claude Code `sonnet` (Sonnet 5.5), low effort | Codex `gpt-6.1-sol`, low | OpenCode + DeepSeek `deepseek/deepseek-v4-pro`, then Codex `-p openrouter` |
| default | Codex `gpt-6.1-sol`, medium | Claude Code `sonnet`, medium | Muse Code, medium (public repos only) | OpenCode + DeepSeek `deepseek/deepseek-v4-pro` (or Codex `-p deepseek`), then Codex `-p openrouter` |
| deep / risky | Codex `gpt-6.1-sol`, **high** | Claude Code `sonnet`, high | Muse Code, high (public repos only) | OpenCode + DeepSeek `deepseek/deepseek-v4-pro` (or Codex `-p deepseek`), then Codex `-p openrouter` |

Policy behind the table (owner rule, Oct 17, 2026): Codex `gpt-6.1-sol` is
primary for all major build work, Claude Code `sonnet` is the first fallback,
and Muse Code is the second. Trivial work starts on Muse Code only because it is
cheap and public-only.

Research and coding experiments: Codex `gpt-6.1-sol` high, then Claude Code
`opus` high, then OpenCode + DeepSeek `deepseek/deepseek-v4-pro`.

### Per-role engine override

The tier order applies to every spawned role unless the profile sets
`[engines.roles]` (#597). An entry such as
`synthesizer = { order = ["codex/gpt-6.1-sol"] }` replaces the tier's order for
that role's workers at every tier, so flipping the builder and reviewer tiers
does not move the synthesizer. The tier still sets the effort. A reviewer
override is still filtered by [reviewer engine selection](#reviewer-engine-selection):
an engine that wrote the round is skipped, and an order with no other engine
refuses the spawn. The spawn record (`runs/<window>.json`) and the brief's
`Engine:` line name the engine actually picked. See
[profile `[engines]`](profile.md#engines).

### Hard rules

- **Eng workers never use Cursor CLI**, at any tier, even when every other
  subscription is exhausted. This covers builders, reviewers, validators and
  researchers' coding runs. Cursor quota is reserved for another bot's own use
  (Oct 16–17, 2026). Queue the work and tell the lead instead.
- **Contributor-tier and free-credit engines never run on private repos.** Muse
  Code runs on free credits that the vendor may use for training and product
  improvement, so keep it off private repos entirely. Trivial private-repo work
  goes straight to Claude Code `sonnet`. Keep any contributor-tier model off
  private repos too.
- **Pay-per-use only as a last resort.** Muse Code via API key, DeepSeek, and
  OpenRouter via Codex profile files spend real money. DeepSeek and OpenRouter
  via Codex also carry about 70k tokens of overhead per run. Use them only after
  every subscription ahead of them is exhausted, and **say so in the report**.
- **Cursor models only.** Cursor's included usage covers only Cursor models
  (Composer, Grok, Auto). Claude or GPT inside Cursor needs paid credits, so
  never pick them without the owner's OK.

### How to run each engine

| Engine | Command shape | Auth (env var name only) |
|---|---|---|
| Codex | `codex exec -m <model> -c model_reasoning_effort=<level> ... </dev/null` (or `-p <profile>`; add `-s read-only` for review runs) | Codex login or profile file |
| Claude Code | `claude -p --model <alias>` | Claude Code login |
| Muse Code | `muse exec --reasoning-effort <low\|medium\|high\|ultra> "<prompt>" </dev/null` | `META_API_KEY` |
| OpenCode | `cd <repo> && OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER=1 opencode run -m deepseek/deepseek-v4-pro "<prompt>" </dev/null` (built-in `deepseek` provider) | `DEEPSEEK_API_KEY` (without it the run hangs) |

Always close stdin with `</dev/null` for non-interactive runs.

## Reviewer engine selection

**The reviewer engine must differ from the builder engine.** The builder engine
is the engine that actually wrote the round under review (see
[Actual builder engine](#actual-builder-engine)). If it is unknown, do not
guess: never treat an unknown engine as non-Claude (#442).

| Builder engine | Reviewer engine |
|---|---|
| Codex | Muse Code `muse exec "<prompt>" </dev/null --reasoning-effort ultra` (public repos only), or Claude Code when it has room (`opus` high, else `sonnet` high). |
| Claude Code or Muse Code | Codex `gpt-6.1-sol`, high. |
| Any, private repo | Never Muse. Codex-built PRs get Claude Code, and the rest get Codex. |
| Any, nothing else available | OpenCode + DeepSeek `deepseek/deepseek-v4-pro` (last resort). Cursor is never an option. |

### Quota diversity waive

- **Flavor:** `diversity = required` requires the owner's per-change OK for
  every waive; `waivable` permits the standing quota grant below. Neither
  removes reviewer independence or the engine-disagreement re-check.
- **Trigger:** the preferred diversity-keeping reviewer engine is under 15%
  of its short window (session / 5-hour), or hard rate-limited, when the
  review is due.
- **Preference:** keep diversity with last-resort OpenCode + DeepSeek
  `deepseek/deepseek-v4-pro` when cheap, available and able to finish before
  the preferred engine resets. Otherwise (DeepSeek unavailable or slower
  than waiting for reset), the coordinator may waive engine diversity and
  use Codex `gpt-6.1-sol` high, even if Codex built the round. Never Cursor.
- **Scope:** one PR at a time, for one round's verdict. Reviewer identity
  must still differ from the builder / PR author (Vera ≠ builder identity);
  only the engine may match.
- **Grant:** MD's standing waive from 2026-10-29 lets the coordinator (Ash)
  grant this for LOW/MED risk PRs without a per-PR ask to MD. HIGH-risk PRs
  (security, releases, deep tier) still need MD's per-PR OK through the
  owner-decision path.
- **Record:** the coordinator posts the grant on the PR in a COMMENT review
  body. The review/verdict signature names the engine actually used and
  includes `diversity-waive: quota`.
- **Unchanged:** mutation-evidence rules, required-evidence, APPROVE-on-head,
  merge-up re-approval and every stage 7 merge gate still apply. This waive
  does not apply to the engine-disagreement re-check (`steer cmd=rereview`
  on a disputed engine): it still needs an engine different from the actual
  builder engine.

### Actual builder engine

A round's builder engine is the engine that **actually wrote that round's
commits**, not the engine that was planned, briefed or named in the PR body.
The round under review is every builder commit pushed since the previous verdict
(before the first verdict: everything in the PR, the initial build). `round=<k>`
is always a verdict round number as
[protocol §5](protocol.md#5-rounds-and-escalation) counts it. A fix or ci-fix
note carries the `k` of the latest verdict whose findings it answers, so the
first fix after a round-1 `REQUEST_CHANGES` is `<BuilderEmoji> <BuilderBot> · Fix · round 1`. A
ci-fix pushed before any verdict answers no verdict and carries `round=0`. The
initial build is not a numbered round: its engine is named in the PR-body
signature, the PR-body builder marker and the commit trailers. A rereview at
the same head keeps the commit range and engine attribution of the verdict it
re-checks.

Three places name it, each with engine, model and effort (for example
`codex gpt-6.1-sol medium` or `claude-code sonnet medium`):

1. **The fix note.** The `<BuilderEmoji> <BuilderBot> · Fix · round <k> @ <sha7>` COMMENT review
   (for the initial build, the PR body signature).
2. **The commit trailer** on every commit of that round:
   `Engine: <engine> <model> <effort>`. A pure merge-up commit says
   `Engine: none (pure merge-up, plain git)` and does not count as a round's
   builder engine.
3. **The `crew:v1` builder marker.** The initial build: the PR-body line
   `<!-- crew:v1 role=builder issue=<n> tier=<tier> engine=<engine> model=<model> -->`.
   A fix round: the fix note's hidden line, which also carries the engine:
   `<!-- crew:v1 role=builder pass=fix pr=<n> sha=<head-sha> round=<k> verdict=n/a engine=<engine> model=<model> effort=<effort> -->`
   (same for `pass=ci-fix`).

The initial build's PR-body marker keeps its existing format (engine and model
only); effort for the initial build is in the signature and the trailers.

Rules:

- If a worker falls back mid-round (for example Claude Code hits a limit and
  Codex finishes), the round names the engine that wrote the commits. If two
  engines wrote commits in one round, name both. The reviewer must then differ
  from both.
- The reviewer-validator picks the reviewer engine from the actual builder
  engine of the round under review, read from that round's fix note, commit
  trailers or marker.
- **Precedence and re-check:** If the builder marker and the fix note or commit
  trailer disagree on the engine, the note or trailer wins, and before merge the
  reviewer re-checks at head (fresh review + validation) on an engine different
  from the actual builder engine. The coordinator posts the rereview steer
  (`steer cmd=rereview`) at head, with the same ack and re-request mechanics as
  the evidence-only rereview in
  [protocol §3](protocol.md#3-evidence-requirements) and
  [Steering](protocol.md#9-steering-crew-commands). The synthesizer must not
  merge until that re-check verdict is posted.

### Related rules

- The validation pass uses the same engine family as the review pass but a
  **fresh session** that has not seen the review output.
- Docs-only re-checks: keep to one light pass to save quota. Merge-up pushes follow the merge-up rule in [the protocol](protocol.md#6-duties-on-wake-all-roles) (re-approve after an approval, ack after changes).
- The reviewer's current choice lives in a per-repo file edited only by the
  reviewer's main chat. See the example in the next section.

## Quota routing

Check quota **before each launch**.

For reviews due at low quota, see the [quota diversity waive](#quota-diversity-waive).

- **Skip a subscription** when it is under **15%** of its short window (session
  or 5-hour) or under **10%** of its weekly or monthly limit.
- **Mid-task limit:** if a worker hits a limit part-way through, relaunch the
  next engine in the row **on the same branch**. The new worker continues from
  the pushed commits.
- Quota can also be steered by a person. A steer re-orders the engines for a
  period, but it never overrides the hard rules above.

### Example: a quota steer on the reviewer side

On Oct 19, 2026 the Codex weekly quota was at 38% until Oct 24 while Claude Code
was about 99% free. The reviewer's engine file was updated to prefer Claude Code
as the first choice:

- Builder = Codex (or other non-Claude): Claude Code Opus (high).
  Fallback: Muse Code with `--reasoning-effort ultra` (`xhigh` if ultra is
  gated). Public repos only.
- Builder = Claude Code (any model): Codex `codex exec -s read-only`
  (`gpt-6.1-sol`, high). Fallback when Codex is rate-limited: Muse Code as
  above. **Do not wait** for the limit to reset.
- Never Cursor or Grok. Skip OpenRouter and DeepSeek.

Lesson (Oct 19, 2026): route by quota. Claude-first while Codex weekly is low
kept reviews moving without breaking the different-engine rule.

## Worker isolation (worktrees)

- **Unique worktree per run:** `<worktree-root>/<pr>-<sha7>-<role>-<pass>/`, for
  example `414-fc778cd-reviewer-review`, where `<worktree-root>` is the
  directory your runtime binding puts worktrees in. Use your own clone or
  worktree, never a shared checkout.
- **Never a branch-named shared path** such as `<worktree-root>/<branch>`. Reusing
  one lets a stale or concurrent run delete the tree mid-pass. This happened
  once: a shared worktree was deleted during a run.
- **Cleanup:** when the run ends, delete **that run's** worktree and its build
  output (for example Rust `target/`). Delete leftovers again on `pr-merged`
  and `pr-closed`. Never delete another run's directory, and never a worktree
  whose work has not landed
  ([runtime contract C6](runtimes/README.md#c6-isolation)). Disk on the
  shared machine is limited.
- **Retention and reclaim:** when a run ends is the binding's call. A
  one-shot run ends when its pass finishes. A retained builder ends at reap or
  reclaim; on tmux that is `pr-merged`, `pr-closed` or reclaim of clean,
  pushed idle work ([Q2](runtimes/tmux.md#q2-lifetime),
  [mdstack dequeue](runtimes/tmux.md#mdstack-dequeue),
  [mdstack kill](runtimes/tmux.md#mdstack-kill)).
- **Toolchain pinning:** before any commit or push, pin the toolchain the repo
  expects (for example set `PATH` to the pinned Node and `COREPACK_HOME`) and
  select the credential for the author identity with
  `GH_TOKEN=$(gh auth token --user <author-login>)`. Do not switch the machine's
  logged-in account.

## Solo session

Use the [solo lane](protocol.md#solo-coding-agent-lane) for attended deep work
in one owner-driven Claude Code or Codex session. Use the full crew for queued
work that needs builder lifecycle management. The session owns builds, fixes,
red CI and conflict resolution; the coordinator posts pickup refs on the PR.
The reviewer remains independent and the synthesizer alone lands.

Paste the rendered `runtime/solo.md` from `crew-render.py` into the session,
then supply the issue, worktree, engine/model/effort and acceptance criteria.
Its PR contract is included from [PR conventions](#pr-conventions), the same
source included by the tmux builder brief; enabled precheck commands render
for both. It needs no builder window, B2 watch, claim or inbox.

## Usage line

Every role post that reports a pass (builder build, fix and ci-fix; reviewer
review, validate, recheck and verdict; synthesizer merge; researcher report;
coordinator status) ends with one line just above its marker and signature,
printed by [`scripts/run-usage.py`](../scripts/README.md#run-usage-helper):

`Run: 23m 10s · 1.24M in (1.1M cached) / 38.2k out · claude-opus-5-5 (high)`

A role run passes `--run "$CREW_STATE/runs/$CREW_ID.json"`. The
coordinator, which has no run record, passes `--engine <engine> --dir "$PWD"
--start <UTC time the status cycle began>`. Wall-clock time runs from the run start to now. Tokens come from the
harness's local session log through its adapter's `usage` reader
([harness adapters](runtimes/harness-adapters.md#adapter-modules)); a harness
without one prints `tokens n/a`, never an estimate. The owner reversed the
earlier rule that token figures stay off the record, for role posts only
(#1557, 2026-11-10; [flavors](flavors.md#feedback-loop)). The line is
informational: no gate, verdict, flavor, scheduler or routing decision reads
it, and it changes no marker, signature or effort attribution. It never
prints a path or credential.

## Orchestration cost

For the flavor [goal `cost`](flavors.md#feedback-loop), measure two meters
separately. In the Grok Bot runtime, Cursor pays for the coordinator,
builder, reviewer-validator and synthesizer's parent turns, including
routine wakes, no-op comment-dispatcher and sweeper turns, and Peace Room
turns. Researcher bot turns also count when run there. CLI builder, review,
validation and research sessions spend their own Codex / Claude Code (or
fallback engine) quota; their tokens do not debit Cursor. In tmux, role
sessions spend the engine they actually run; there is no Cursor parent meter.
An engine-run count is a proxy, not a Cursor billing estimate.

### Parent-turn targets

Targets for one clean PR head in Grok Bot, counted across parent bots for
that stage; worker sessions are separate. These are diagnostic targets,
not caps that suppress required work.

| Stage | Target maximum parent wakes | Work bundled in the turn |
|---|---|---|
| Ack / handoff | 1 | Read live state, claim, dispatch and acknowledge |
| Verdict | 3 | Dispatch review, collect it and dispatch validation, collect validation and post one verdict |
| Merge | 2 | Gate check and land; one retry when a pending gate clears |
| Mirror, when required | 1 | Deploy, drift check and record the result |

Count excess wakes with their reason: fixes, CI failures, stale events,
holds, owner steering and additional gate retries still get handled. A
budget never waives evidence, reviewer independence or engine diversity,
head-bound approval, synthesizer-only squash, or the mirror hold. Existing
round caps and every [merge gate](protocol.md#7-merge-gate-synthesizer) apply.
Peace Room FYIs never request a priority wake; batch progress for the next
normal turn. Escalations and actionable handoffs use the existing routing.

### Handoff and worker hygiene

Orchestrator messages carry references and a short action, not pasted diffs
or raw logs. Use this handoff shape; the receiving worker loads the issue,
PR, review and evidence itself at the pinned head before acting:

```text
Issue: <issue URL>; PR: <PR URL or none>; head: <full SHA>
Action: <build | review | validate | fix>; tier: <tier>; effort: <effort>
Findings / evidence: <review URL or evidence reference>; scope: <AC numbers>
Result: <short outcome or blocker>; summary: <step-summary reference>
```

References in messages never replace the inline
[acceptance evidence](protocol.md#3-evidence-requirements). Keep raw
logs local and promote only key output, per [observe.md](observe.md).
Builders, reviewers and validators follow the worker brief hygiene below.
Stable prefixes help reuse cached input; they do not guarantee a cache hit
or reduce Cursor parent wakes ([OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)).

Cost choices use tier or flavor configuration (`engines`, `parallelism`,
`caps`), per [flavor cost levers](flavors.md#decisions); no router model picks
routes. The later quiet-week comparison in #109 waits for #352 data: compare
local Cursor percentage per merged PR / merged SHA and parent turns with
the hot baseline week, separately from CLI engine runs. No savings are
claimed before that measurement.

## Worker brief template

Give each worker the complete brief. Copy, then fill every placeholder.

````markdown
# Worker brief: <repo> issue #<issue#>

- Role: <role>. Tier: <tier> (<effort> effort).
- Engine and model: <engine> / <model>. Name the engine, model and effort you
  actually ran as (including any fallback) in the PR signature or fix note, in
  an `Engine: <engine> <model> <effort>` trailer on every commit, and in the
  `crew:v1` builder marker.
- Repo: <owner>/<repo>. Base branch: <default-branch>.
- Your worktree: <worktree-root>/<pr>-<sha7>-<role>-<pass>/ (unique to this run).
  Work only there. Clean it up per roles.md Worker isolation and your
  runtime binding.
- Branch: <role>/<issue#>-<short-slug>. For review feedback on an existing PR,
  push to that PR's branch.
- Issue: <issue URL>

## Issue body

<issue URL; worker reads the full live body and triage decisions>

## Review feedback to address (if any)

<review URL and pinned head SHA, or write "none">

## Acceptance criteria

<numbered, testable criteria from the issue>

## Rules

- Start a pass only from a brief that ends in a `## This run` block with
  `Item`, `Pass` and `Base` filled, built by `mdstack brief` (the tmux runtime
  appends it at spawn; [hosted dispatch](runtimes/session.md#run-parameters-for-hosted-dispatch)).
  Without it, report `blocked:` with the missing fields and do not start.
- Start a fresh session per issue; in Claude Code, `/clear` between unrelated
  issues is also acceptable. Review and validation each use their required
  separate fresh session; never reuse the builder's conversation.
- Keep the reusable instructions and tool definitions first and stable;
  append issue/PR/SHA references and changing evidence after that prefix.
  Load referenced bodies and evidence yourself before doing the pass.
- Match effort to the tier table (or its recorded profile override). Keep
  model, tools and schemas stable during a pass; a required fallback starts
  a fresh session and records the engine actually used.
- Resolve change flavor at every wake using the newest signed item record and
  full diff paths at head (protocol §3). Apply its review, validation, evidence,
  caps and merge modes; no record means thorough and report flavor-missing.
  Never lower rigor yourself; unresolved data blocks rather than relaxes.
  Rigor comes only from that resolution; a brief floor with no record behind
  it is reported as `flavor-unrecorded` ([flavors](flavors.md#resolution)).
- Read the framework text your brief cites before the pass (#375). The
  dispatch names a copy readable on the worker's host at the framework pin
  (the pinned toolkit's `docs/` on a remote host,
  [host toolkit](bootstrap.md#host-toolkit)), or pastes pinned excerpts of
  the cited sections. If cited text is missing or unreadable there, report
  `blocked: <ref> spec-unreadable` and do no pass; never accept a citation
  on trust. This holds on a host with no access to the source repo.
- Keep required reporting writes apart from commands under test (#378). The
  role's reporting writes are its ack, fix or verdict post and markers,
  state tags, status and `done:` lines and the claim heartbeat. A rule that
  restricts the sends or writes being tested (for example "send nothing to
  the real channel") never forbids an otherwise authorized reporting write,
  and grants no write authority beyond it.
- Stay in your role's area. Flag cross-area needs in the report.
- Follow the repo's commit-message convention (check `git log`).
- When `builder.precheck.enabled` is true, before handoff follow the builder
  pre-review check in protocol.md using the profile's commands and
  `max_fix_attempts` (default two): fresh base → lint/format → tests/build
  (gather typed evidence) → self-review against ACs
  → docs/changelog → confirm evidence → open the PR with `pass=precheck`
  step results at the final full head SHA. Stop and report a rebase conflict
  or remaining failure. Never loosen tests, lint config or checks to pass.
  A command step without a configured command is `n/a`, never `pass`.
  Publish step results and test output, never self-review reasoning.
- Open a non-draft PR with `gh pr create`, never `--fill`, using the PR
  conventions below. A release cut PR links its release issue with
  `Refs #<n>` plus one whole line `Release issue: #<n>`, never `Closes`; the
  publish job closes it after publication ([release steps](release.md#steps)).
- Never merge, never approve your own work, never force-push a shared branch.
- Do not scope-creep. Note deeper problems in the report and stop. If the task is
  ambiguous, flag it instead of guessing.
- Add no new shared append-hotspot file (a table or list that every PR edits at
  the end): one file per item, or a generated aggregate. Put an entry in a
  sorted index file at its sorted place (see CONTRIBUTING, Shared files).

## Report (final message)

PR URL and number, head SHA, summary of changes, test results, the engine and
model and effort actually used (including any fallback), and follow-ups or ambiguities. Then exit,
unless your runtime binding retains you for later rounds.
````

For a multi-step run the worker also writes step summaries
(`scripts/step-summary.py`, local `.crew/runs/<issue-or-pr>/<run-id>/`) and
names the summary path in its report; the role bot promotes the short summary
in its signed review body and keeps raw logs local. Raw logs are break-glass
only, never chat. See [observe.md](observe.md).

## PR conventions

- **Branch:** `<role>/<issue#>-<short-slug>`, for example
  `infra/187-align-rust-base-images`; tooling routes follow-ups by it.
- **Commits:** one PR per issue, in logical commits that pass their tests.
  Follow repo convention; end each with `Engine: <engine> <model> <effort>`,
  the engine that actually wrote it ([Actual builder engine](#actual-builder-engine)).
- **Evidence:** for behaviour changes, embed runtime proof inline in the body
  or signed fix / ci-fix reviews ([verification](verification.md)); never
  commit evidence. Docs-only PRs state N/A and why.
- **Pre-review check:** when enabled in the profile, follow the ordered steps, bounded fixes and
  `pass=precheck` schema in [the protocol](protocol.md#builder-pre-review-check)
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
signature ([architecture overview](architecture.md)). See the
[stage protocol](protocol.md) for the other crew additions: `## Acceptance Evidence`
(with the shape and inline proof label per the [verification protocol](verification.md))
and `## Risks / Not Done`. Test Output and Acceptance Evidence must paste key
output and/or screenshots inline; paths and repo-file links do not count. A
behaviour-changing PR that adds or
changes a user-visible create, update or complete (or equivalent) mutation
pastes a create→complete→delete happy-path snippet (for list delete with
cascade, also show the child items are gone); see
[protocol §3](protocol.md#3-evidence-requirements).

### Fix note (crew and solo builders)

After addressing findings and linked CI, push, then post a `… · Fix · round <k>
@ <sha7>` COMMENT review (§4); a CI-only fix uses `CI fix`, `pass=ci-fix` and
round 0 before any verdict.
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

## Parallelism

Within an issue, worker lanes run sequentially by default. The coordinator
marks lanes independent before concurrent dispatch: no semantic dependency,
shared mutable external state or incompatible migration. Independent PRs
retain the dispatch independence rule and review fan-out below. This does
not serialize all project admission or change capacity ceilings.
The [concurrency study cited in #109](https://arxiv.org/html/2610.10263)
reports a 1.41–3.31× token tax; treat it as a study result, not a forecast for
this crew. Use concurrency for independent work and required independent
validation, within the project's `parallelism` configuration.

Soft ceilings (set Oct 15, 2026). Queue work past them.

| Activity | Limit | Notes |
|---|---|---|
| Builders | up to **5** concurrent sessions | Each has its own worktree, branch and PR. |
| Reviews | up to **5** concurrent sessions | **Fan out by default:** one review session per waiting PR, each with one engine, one PR and one verdict. |
| Merge | **serial only** | The synthesizer lands one approved PR at a time, so branch races, squash order and board updates stay clean. A merge train tests several together first, then lands them one by one. |

After the PR opens, the reviewer reviews automatically. If it requests changes,
the lead relaunches the same role on the same branch with the review attached.
If it approves, the synthesizer merges under the merge policy. Event-driven
detail belongs to the stage protocol.
