# Architecture overview

A crew of bots runs a GitHub repo's loop of spec, build, CI, review,
validation and merge. One issue becomes one branch, one PR and one squash merge.
Each stage is woken by a GitHub event, does its job through fresh workers, and
leaves its result on GitHub (labels, markers, a formal review) so the next stage
can read that state. Nothing important lives only in a bot's chat.

This page covers the [deployment](#deployment-wakes-and-releases), roles,
identities, stages, labels, markers and the [modules](#modules) the team is
built from. Full protocol
detail is in [protocol.md](protocol.md). Worker roles, tiers and engines are in
[roles.md](roles.md). See the [docs index](README.md).

Placeholders used below: `<owner>`, `<repo>`, `<author-login>`,
`<reviewer-login>`, `<BotName>`, `<default-branch>`, `<state-dir>`.

## Deployment, wakes and releases

The canonical picture of one running deployment: who talks to whom, how a
GitHub change wakes a worker, and how a release reaches an install. This is
the [tmux runtime](runtimes/tmux.md); other runtimes keep the same GitHub
side and gates. Edge labels E1–E22 key the source table below the diagram.

```mermaid
flowchart TD
  owner["Owner<br/>specs, decisions, merge-ok"]
  subgraph github["GitHub: tools of record"]
    issues["Issues<br/>crew:* labels, signed markers"]
    prs["PRs<br/>evidence, markers, formal reviews"]
    ci["CI<br/>required checks at head"]
    gate{"§7 merge gate<br/>at the current head SHA"}
    main["default branch"]
    rel["GitHub Release<br/>tag, bundle, SHA256SUMS"]
  end
  subgraph runtime["Runtime: one machine, one state dir"]
    poll["mdstack poll<br/>zero-model GitHub reads"]
    watch["mdstack watch<br/>status files, liveness, deadlines"]
    queue[("wake/queue.jsonl")]
    route["mdstack route<br/>mechanical wakes, no model turn"]
    subgraph sessions["Long-lived harness sessions"]
      coord["Coordinator<br/>judgement wakes, dispatch"]
      poolleads["Builder and reviewer leads<br/>spawn, dequeue, reclaim"]
      synth["Synthesizer lead<br/>the lander, spawns no workers"]
    end
    subgraph worktrees["Isolated role worktrees: one harness session each"]
      builder["Builder"]
      reviewer["Reviewer-validator"]
    end
    install["Install<br/>~/.mdstack/releases/current, VERSION"]
  end
  owner -- "E1: chat, decisions" --> coord
  owner -- "E2: issues, comments, merge-ok" --> issues
  coord -- "E3: issues, crew:ready, records" --> issues
  issues -- "E4" --> poll
  prs -- "E4" --> poll
  ci -- "E4" --> poll
  poll -- "E5: new-head, ci-passed, ci-failed,<br/>merge-ok-recorded ..." --> queue
  watch -- "E6: done:, blocked:, dead workers" --> queue
  queue -- "E7" --> route
  route -- "E8: judgement records" --> coord
  route -- "E9: new-head starts review,<br/>review passed starts validation" --> poolleads
  route -- "E10: review-approved, ci-passed<br/>with approval: land work" --> synth
  coord -- "E11: lead handoff" --> poolleads
  poolleads -- "E12: spawn" --> builder
  poolleads -- "E12: spawn" --> reviewer
  builder -- "E13: branch, PR, fix notes" --> prs
  prs -- "E14: each push" --> ci
  reviewer -- "E15: verdict, formal review" --> prs
  prs -- "E16: approval or merge-ok at head" --> gate
  ci -- "E17: green at head" --> gate
  synth -- "E18: re-checks live, then squash" --> gate
  gate -- "E19" --> main
  main -- "E20: landed cut PR: validate,<br/>approval check, publish" --> rel
  rel -- "E21: mdstack upgrade: checksum,<br/>re-render, drift check" --> install
  install -. "E22: rendered briefs" .-> coord
```

*Review and CI are independent inputs to the merge gate: a new head starts
review at once (`new-head`); it does not wait for `ci-passed`. Each worker
runs in its own worktree through one
[harness](runtimes/harness-adapters.md). The
[session runtime](runtimes/session.md) runs no watcher: the coordinator
sweeps GitHub on owner turns and worker completions, so it supports only an
attended crew ([session: recovery and support
boundary](runtimes/session.md#recovery-and-support-boundary)).*

| Edge | Source |
|---|---|
| E1 | Coordinator woken by the owner: [protocol §1](protocol.md#1-roles-and-identities) |
| E2 | Owner commands and merge-ok on GitHub: [protocol §9](protocol.md#9-steering-crew-commands), [§7](protocol.md#7-merge-gate-synthesizer) |
| E3 | Spec and handoff stages: [protocol §2](protocol.md#2-stages) |
| E4, E5 | [`mdstack poll`](runtimes/tmux.md#mdstack-poll); `environments/terminal/crew.d/poll.py` module docstring |
| E6 | [`mdstack watch`](runtimes/tmux.md#mdstack-watch); `environments/terminal/crew.d/watch.py` `run` |
| E7, E8 | [`mdstack route`](runtimes/tmux.md#mdstack-route); `environments/terminal/crew.d/route.py` module docstring |
| E9, E11, E12 | [Builder lead](runtimes/tmux.md#builder-lead), [reviewer lead](runtimes/tmux.md#reviewer-lead), [spawn and kill](runtimes/tmux.md#spawn-and-kill) |
| E10, E18 | [Synthesizer lead](runtimes/tmux.md#synthesizer-lead) |
| E13 | Build stage: [protocol §2](protocol.md#2-stages), [PR conventions](roles.md#pr-conventions) |
| E14 | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) |
| E15 | Verdict: [protocol §4](protocol.md#4-marker-conventions), [§5](protocol.md#5-rounds-and-escalation) |
| E16, E17, E19 | [protocol §7](protocol.md#7-merge-gate-synthesizer), [land rules](protocol.md#land-rules-and-merge-trains) |
| E20 | [release: Steps](release.md#steps) 6–9; [`.github/workflows/release.yml`](../.github/workflows/release.yml) |
| E21, E22 | [release: Update path](release.md#update-path), [`mdstack install`](runtimes/tmux.md#mdstack-install) |

## Roles

Five roles run the loop: the coordinator (also the **steering dispatcher**),
researcher, builder, reviewer-validator and synthesizer. Who wakes each role,
what it owns and which identity it uses are defined in
[protocol §1](protocol.md#1-roles-and-identities). Worker scope, tiers and
engines are in [roles.md](roles.md).

Only role bots post to GitHub. Short-lived workers do the coding and reviewing,
and report back to their role bot.

## Identities

The crew uses two GitHub identities: the **author identity**
(`<author-login>`) and the **reviewer identity** (`<reviewer-login>`), which
must differ from the PR author. Which role uses which, and why GitHub needs
them to differ, is in the [GitHub backend](backends/github.md#identities).

Several bots share each account, so bot identity comes from the signed marker,
not the account ([protocol §1](protocol.md#1-roles-and-identities); see
[Markers](#markers)).

## Stages

```mermaid
flowchart TD
  spec["1. Spec<br/>coordinator + user"] --> handoff["2. Handoff<br/>crew:ready + assign"]
  handoff --> build["3. Build<br/>builder opens PR, crew:in-review"]
  build --> ci{"4. CI"}
  ci -- "fail: ci-failed, up to 3 fix attempts" --> cifix["Builder fixes on the same branch"]
  cifix --> ci
  cifix -- "new-head" --> review
  ci -- "fix cap hit" --> escalate
  build -- "new-head" --> review["5. Review pass"]
  ci -- "green: ci-passed, approval at head" --> merge
  review --> validation["6. Validation pass<br/>only if review passed"]
  validation --> verdict{"7. Verdict<br/>one formal review per head SHA"}
  verdict -- "REQUEST_CHANGES: crew:changes<br/>round 1 or 2" --> iterate["8. Iterate<br/>builder fix round + fix note"]
  iterate --> ci
  iterate -- "new-head" --> review
  verdict -- "REQUEST_CHANGES at round 3" --> escalate["Escalation exit<br/>crew:escalated, coordinator tells the user"]
  verdict -- "APPROVE: crew:approved" --> merge["9. Merge<br/>synthesizer, gate check, squash"]
  merge --> closeout["10. Close-out<br/>pr-merged: clean up, update board, next issue"]
  escalate -. "/crew resume, resets rounds" .-> rekick["Re-kick current stage<br/>no verdict: reviewer · changes: builder · approved: synthesizer"]
```

The diagram is the explanatory path. Each stage's duties are defined in
[protocol §2](protocol.md#2-stages), verdict rounds and the escalation exit in
[§5](protocol.md#5-rounds-and-escalation), and the merge gate in
[§7](protocol.md#7-merge-gate-synthesizer).

## Labels

Labels are safe state because no listener fires on labels. These are the eleven
`crew:*` labels in this repo. This table is the role view; GitHub specifics
(colours, label events, milestones, board and issue linkage) are in the
[GitHub backend: Tracking](backends/github.md#tracking).

| Label | Meaning | Set by | Cleared by |
|---|---|---|---|
| `crew:ready` | Released to the builder; the issue may be assigned and built | Coordinator | Coordinator, once the issue is done |
| `crew:in-review` | PR open, awaiting CI, review and validation | Builder, when the PR opens | Reviewer-validator, in the same step that sets `crew:approved` or `crew:changes` |
| `crew:changes` | Reviewer requested changes; a builder fix round is due | Reviewer-validator, on `REQUEST_CHANGES` | Reviewer-validator, on the next verdict |
| `crew:approved` | Reviewer approved at head; the synthesizer may merge | Reviewer-validator, on `APPROVE` | Reviewer-validator, on a later verdict at a new head |
| `crew:escalated` | Round cap or CI-fix cap hit, or escalated by hand; work roles do nothing until `/crew resume`; coordinator and sweeper still monitor waits | Reviewer-validator or builder at a cap; coordinator at the sweeper nudge cap or on `/crew escalate` | Coordinator, on `/crew resume` |
| `crew:hold` | Paused: work roles do nothing on this item; coordinator and sweeper still monitor waits | Coordinator, on `/crew hold` or by the user | Coordinator, on `/crew resume` |
| `crew:external` | External (fork) PR: sandboxed validation, no tokens | Reviewer-validator, on `pr-opened` | Not cleared; stays for the life of the PR |
| `crew:spec` | Spec PR: review pass only, merges on `/crew merge-ok` | Coordinator, when opening the spec PR | Not cleared; stays for the life of the PR |
| `crew:express` | Express lane: one builder builds and self-gates; no reviewer verdict ([protocol §3](protocol.md#change-flavor)) | Coordinator, with the `express` item record | Builder, on [fallback](express-lane.md#eligibility) to the crew lane (it tells the coordinator) |
| `crew:needs-md` | Blocked on a decision from the human owner, with a recommended default and a deadline | Coordinator or its sweeper; reviewer-validator for an intentional verdict hold | Coordinator, once the owner decides |
| `crew:needs-mirror` | Protocol/template change: the synthesizer refuses to merge until the box skill is mirrored | Reviewer-validator, in its verdict pass, on PRs changing `docs/protocol.md` or `templates/`, before it posts the formal review, unless the mirror comment is already newer than the last commit touching those paths | Coordinator, when it posts the box-skill mirror comment (fresh one after any later such commit); it then pings the synthesizer, because label changes don't wake listeners |

Bots never touch labels or comment commands that belong to the product under
development.

## Markers

Each stage leaves its result as a signed bot post that the next stage reads
back. A post body opens with a visible title and carries one hidden
`crew:v1` line, for example a builder's fix note:

```text
<BuilderEmoji> <BuilderBot> · Fix · round <k> @ <sha7>
...
<!-- crew:v1 role=builder pass=fix pr=<n> sha=<40-char head sha> round=<k> verdict=n/a engine=<engine> model=<model> effort=<effort> -->
```

Where bots write, the marker schema, every `pass` value and what it means,
and the rules for reading markers are defined in
[protocol §4](protocol.md#4-marker-conventions). The builder's PR body line
and fix-note fields are in [protocol §3](protocol.md#3-evidence-requirements),
round counting in [§5](protocol.md#5-rounds-and-escalation), skipping a pass
already done at head in [§6](protocol.md#6-duties-on-wake-all-roles), and the
actual writing engine in [roles](roles.md#actual-builder-engine).

## Modules

A deployment is the product of four independent axes: **roles** (who),
**connectors** (the tools of record), **environments** (where and how the
team runs) and **harnesses** (how an agent launches and loads). The profile
picks one value per axis; roles name generic actions, and the other three
axes implement them. Terms are in [concepts: Four axes](concepts.md#four-axes);
each module's README is linked from the [docs index](README.md#modules).

```mermaid
flowchart TD
  profile["profiles/<br/>one choice per axis"]
  roles["roles/<br/>who: role definitions, routines, seats"]
  protocol["protocol<br/>stages, markers, gates (docs/protocol.md)"]
  actions["actions/<br/>generic verbs and CLI contract"]
  connectors["connectors/<br/>tools of record per concern"]
  environments["environments/<br/>where and how the team runs"]
  harnesses["harnesses/<br/>one adapter per coding harness"]
  core["core/<br/>config, renderer, registry, memory, packs"]
  cli["cli/mdstack"]
  packs["packs (outside this repo)"]
  profile -- selects --> roles
  profile -- selects --> connectors
  profile -- selects --> environments
  profile -- selects --> harnesses
  roles --> protocol
  roles --> actions
  protocol --> actions
  connectors -. implement .-> actions
  environments -. implement .-> actions
  harnesses -. implement .-> actions
  connectors --> core
  environments --> core
  harnesses --> core
  cli -- dispatches --> environments
  packs -. add .-> connectors
  packs -. add .-> environments
  packs -. add .-> harnesses
```

*Solid arrows: may reference (dependency rules D1–D4 and D8 in
[specs/team.md §5](specs/team.md#5-dependency-rules)); dotted: implements or
extends. No binding module references another except through `actions/` or a
declared capability (D3). The protocol is not yet its own `protocols/`
module; it lives in [protocol.md](protocol.md).*
