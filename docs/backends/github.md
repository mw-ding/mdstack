# GitHub backend

How the GitHub backend expresses the core rules in
[protocol.md](../protocol.md) (portable mdstack, roadmap 13.3,
[#115](https://github.com/mw-ding/mdstack/issues/115), and 13.4,
[#116](https://github.com/mw-ding/mdstack/issues/116)). GitHub is today's
backend for every concern ([concepts: backend](../concepts.md#backend)). The
core states each rule; this page states the GitHub mechanics for it. Neither
page changes a rule, gate, cap, marker field or label.

## Reviews, markers and identities

### Identities

The crew uses two GitHub accounts
([architecture: Identities](../architecture.md#identities)):

- **Author identity** (`<author-login>`): coordinator, researcher, builder and
  synthesizer. It opens branches and PRs, posts narrative and lands.
- **Reviewer identity** (`<reviewer-login>`): the reviewer-validator's verdicts,
  and the coordinator's steering signals.

**Why the reviewer identity must differ from the PR author.** GitHub refuses
`APPROVE` and `REQUEST_CHANGES` reviews from a PR's author. A separate reviewer
account keeps the formal verdict accepted and from a different party than the
author (invariant I1, [portable spec §3](../specs/portable.md#3-invariants)).
Roadmap PRs under the single-identity rule post verdicts as COMMENT reviews
instead ([portable spec §6](../specs/portable.md#6-decisions)).

**Selecting the identity.** Each `gh` call picks its account through the
token, for example `GH_TOKEN=$(gh auth token --user <author-login>)`, or
`--user <reviewer-login>` for verdicts and steering signals. Never switch the
machine's logged-in account.

**Shared accounts.** Several bots share each account, so GitHub actor filters
cannot tell bots apart. The core rule applies: a bot action's identity comes
from its signed marker ([protocol §4](../protocol.md#4-marker-conventions)).

### Review types and the events they fire

Bots never post plain PR conversation comments or inline comments. Those fire
`pr-comment` / `inline-review-comment` and wake the steering dispatcher for
nothing. Bot output on PRs goes in review bodies:

| Core post | GitHub form | Events it fires |
|---|---|---|
| Narrative post (ack, fix notes, merge-up, merge, cutover, escalation, steering acks) | **COMMENT** review. The author identity may comment-review its own PR | `review-commented` (nobody subscribes) and also `pr-comment` (the steering dispatcher no-ops it cheaply) |
| Verdict or steering signal | **Formal** `APPROVE` / `REQUEST_CHANGES` review. Cite `file:line` in the body instead of inline comments | `review-approved` / `review-changes-requested` |
| Never by a bot | Plain PR conversation comment or inline comment | `pr-comment` / `inline-review-comment` |

Ownership records are coordinator comments on the repo control issue
([protocol §4](../protocol.md#ownership-record)); they are read on every wake,
not consumed as steering commands.

### Markers

The signed header is the first line of the review body, and the hidden
`crew:v1` line is an HTML comment in the same body, so it does not render. The
marker format itself is core ([protocol §4](../protocol.md#4-marker-conventions)).

### Land and merge-up

- **Land:** `gh pr merge <n> --squash --match-head-commit <sha>` with the
  author identity. `--match-head-commit` makes GitHub refuse the merge if the
  head moved after the gate check
  ([protocol §7](../protocol.md#7-merge-gate-synthesizer)).
- **Head branch (#395):** for a same-repository head that is neither the
  default nor the base branch, the land adds `--delete-branch`, so the merge
  deletes the branch and close-out makes no separate DELETE call. The
  briefs' `-R <o>/<r>` keeps `gh` from touching local branches. A fork,
  default or base head lands without it and is retained. `gh` exits non-zero
  if the merge lands but the delete fails: `mdstack train land` re-reads the
  state and records `delete failed` for a `MERGED` PR, a direct land's next
  live read shows the PR merged, and close-out's guarded delete is the
  fallback. The repository setting `delete_branch_on_merge` is the
  alternative
  ([merge settings](../runbooks/github-ci-protection.md#merge-settings-and-enforcement-limits));
  with it, `gh` treats the already-deleted branch as done.
- **Merge-up:** GitHub update-branch (a merge commit, never a rebase) for a PR
  synchronized at land, or a builder conflict-resolution merge. A passing
  verdict carries only after protocol §7 proves identical content and green
  CI at the new head; otherwise route builder → delta re-review. Never
  update every open branch merely because the default branch advanced.

## Tracking

### Labels

Each state tag is a GitHub label in the `crew:*` namespace. These are the thirteen
labels. What each means and who sets and clears it is the role view in
[architecture: Labels](../architecture.md#labels); the commands that create
them are in [runbook Step 1](../runbook-new-repo.md#step-1-create-the-crew-labels).

| Label | Colour | GitHub description |
|---|---|---|
| `crew:ready` | `0E8A16` | Released to the builder; issue may be assigned and built |
| `crew:in-review` | `1D76DB` | PR open, awaiting CI + review/validation |
| `crew:changes` | `D93F0B` | Reviewer requested changes; builder fix round due |
| `crew:approved` | `5319E7` | Reviewer approved at head; synthesizer may merge |
| `crew:escalated` | `B60205` | Round/CI-fix cap hit or escalated; bots no-op until /crew resume |
| `crew:hold` | `FBCA04` | Paused: every bot no-ops on this item |
| `crew:external` | `C5DEF5` | External/fork PR: sandboxed validation, no tokens |
| `crew:spec` | `0052CC` | Spec PR: review pass only, merges on /crew merge-ok |
| `crew:needs-md` | `F9D0C4` | Blocked on an owner decision (recommended default + deadline) |
| `crew:needs-mirror` | `E99695` | Protocol/template change: merge blocked until the box skill is mirrored |
| `crew:sensitive` | `B60205` | Requires per-change owner merge-ok; no standing grant applies. |
| `crew:express` | `BFD4F2` | Express lane: builder builds and self-gates; no reviewer verdict |
| `crew:solo` | `FEF2C0` | Solo lane: the owner session builds and fixes; reviewer stays independent |

The [always-on triage](../triage.md) sweep adds its own labels, outside the
`crew:*` namespace and never state tags ([protocol §4](../protocol.md#4-marker-conventions)):

| Label | Colour | GitHub description |
|---|---|---|
| `triage:proposed` | `D4C5F9` | Triage proposal awaits the owner's answer on this issue |
| `triage:duplicate` | `CFD3D7` | Exact duplicate, linked; the close is proposed |
| `triage:card-extracted` | `BFDADC` | Triage posted the intake-card fields as a comment |
| `triage:log` | `EDEDED` | Daily triage log; every sweep skips it |
| `P0` … `P3` | `B60205`, `D93F0B`, `FBCA04`, `C2E0C6` | Triage priority band |

**No listener fires on labels.** No crew routine subscribes to a label
event, so labels are safe state: setting or clearing one wakes nobody. A role
that clears a label another role waits on pings that role by message, for
example the coordinator pings `<SynthesizerBot>` after removing
`crew:needs-mirror` ([protocol §6](../protocol.md#6-duties-on-wake-all-roles)).
Roles read labels when they re-read live state on a wake.

### Milestones and board

The tracker is GitHub issues, Milestones and a Project (v2) board
([protocol §6](../protocol.md#6-duties-on-wake-all-roles), Repo tracking).
Setup commands are in
[runbook Step 3](../runbook-new-repo.md#step-3-create-milestones-and-link-a-github-project-v2).

- **Milestones** are named `M1`, `M2`, …. Each issue goes to an open `M*`. A
  closed milestone is frozen: no new issues; follow-ups go to the next `M*`.
- **Project (v2) board**, recommended, not required, with a Status field of exactly Todo, In Progress, In
  Review and Done. The coordinator adds issues and keeps item status current
  (Todo for new issues, In Progress while a PR is built, In Review while it is
  under review, Done after merge). The builder adds its PR by hand. Board
  auto-add and status workflows must not conflict with that; a built-in "item
  closed" → Done workflow is fine. With no board, board status is skipped;
  `mdstack doctor` reports a `human` step with the owner's create and link
  commands when its identity cannot create one (a bot login on a user-owned
  repo, or no `project` scope), and bootstrap proceeds.

### Linkage

- **PR to issue.** The PR body's `## Context` carries `Closes #<n>`, so the
  squash merge closes the issue. If the repo forbids closing keywords, the
  builder writes `Refs #<n>`; that satisfies the linked-issue gate and the
  coordinator closes the issue after merge
  ([protocol §7](../protocol.md#7-merge-gate-synthesizer),
  [runbook Step 5](../runbook-new-repo.md#step-5-product-safety-checks)).
  Spec, external and cutover PRs are exempt.
- **Release cut to release issue.** A release cut PR (its diff adds a new
  version heading to `CHANGELOG.md`) names the release issue with `Refs #<n>`
  plus one whole line `Release issue: #<n>`, same repository, and never a
  closing keyword for it; that satisfies the linked-issue gate. The publish
  job reads that line, posts the release link and then closes the issue
  ([release steps](../release.md#steps), #1416). Any other `Refs` satisfies
  nothing beyond the forbidden-keyword case above.
- **Builder linkage check (#1418).** Before opening, the builder reads the
  item's newest signed allocation: the newest coordinator-signed record on
  the item that says which issue the PR closes (its `pass=flavor` record, or
  a later `pass=steer` that reallocates it). It cites that record's URL in
  `## Context` and runs `scripts/check-pr-linkage.py --body-file <file>
  --closes <n> --allocation <url>` (a release cut: `--release <n>`), fixing
  every finding before opening. Each allocated issue needs exactly one whole
  `Closes #<n>` line; every other closing keyword is flagged, descriptive
  mentions of closed issues included: write `#20, now closed`, not
  `closed #20`. If a newer allocation names another issue after the PR
  opens, the builder reports the mismatch to the coordinator in a signed
  note and never edits the body. This is a builder duty, not a merge gate,
  and runs whether or not the
  [pre-review check](../protocol.md#builder-pre-review-check) is enabled.
- **Umbrella and TRD issues are never auto-closed.** A child issue says
  `Part of #<n>` for its umbrella, never a closing keyword.
- **Dependencies.** An issue body lists `Depends on #<n>`; dependent PRs merge
  in that order ([protocol §6](../protocol.md#6-duties-on-wake-all-roles)).

### Steering limits

`/crew` commands arrive as PR conversation comments or inline review comments,
which fire `pr-comment` / `inline-review-comment` for the steering dispatcher
([protocol §9](../protocol.md#9-steering-crew-commands)). There is no
issue-comment event, so **issues cannot be steered by comment**. Steer an issue
with assignment (`issue-assigned` wakes the builder), labels (`crew:ready`,
`crew:hold`), or chat with the coordinator.

## Interface mapping

How GitHub implements each operation of the
[backend interfaces](../interfaces.md) (roadmap 13.9,
[#121](https://github.com/mw-ding/mdstack/issues/121)). `<o>/<r>` is
`<owner>/<repo>`. Every call runs under the identity named in
[Identities](#identities): the reviewer identity for verdicts and steering
signals, the author identity for everything else.

| Concern | Operation | `gh` command or API call |
|---|---|---|
| change | Open, linked to an item | `gh pr create --base <default-branch> --head <branch> --title <t> --body-file <f>`, body with `Closes #<n>` ([Linkage](#linkage)) |
| change | Push | `git push origin <branch>` (never `--force`) |
| change | Read head | `gh pr view <n> --json headRefOid -q .headRefOid` |
| change | Read diff paths | `gh pr diff <n> --name-only` |
| change | Read diff | `git fetch -q origin <default-branch> +refs/pull/<n>/head && git diff --no-color --no-renames origin/<default-branch>...<sha>` in any clone of the repository: the unified diff at head against its merge base, without rename folding (`gh pr diff` folds renames) |
| change | Update from base | `gh pr update-branch <n>` (merge; never `--rebase`), or `git merge origin/<default-branch>` and push |
| change | Land | `gh pr merge <n> --squash --match-head-commit <sha>` |
| change | Delete on land | `--delete-branch`, added to Land |
| change | Close | `gh pr close <n>` |
| change | List open | `gh pr list --state open --json number,headRefName,closingIssuesReferences` |
| change | Read state | `gh pr view <n> -R <o>/<r> --json state,headRefName,headRepositoryOwner,headRepository,isCrossRepository,baseRefName` |
| change | Read default branch | `gh repo view <o>/<r> --json defaultBranchRef` |
| change | Delete branch | `gh api -X DELETE repos/<o>/<r>/git/refs/heads/<branch>` |
| change | CLI conventions | `gh`; `-R <o>/<r>`; `gh api` (takes no `-R`) |
| review | Post verdict pinned to head | `gh api repos/<o>/<r>/pulls/<n>/reviews -f commit_id=<sha> -f event=APPROVE` (or `REQUEST_CHANGES`) `-F body=@<f>` |
| review | Post narrative | `gh pr review <n> --comment --body-file <f>` |
| review | List verdicts | `gh api --paginate repos/<o>/<r>/pulls/<n>/reviews`: `user.login`, `state`, `commit_id`, `body`, `submitted_at` |
| review | Request re-review | `gh pr edit <n> --add-reviewer <reviewer-login>` |
| tracker | Create item | `gh issue create --title <t> --body-file <f> --milestone <M>` |
| tracker | Assign | `gh issue edit <n> --add-assignee <login>` |
| tracker | Link change ↔ item | `Closes #<n>` in the PR body; read with `gh pr view <n> --json closingIssuesReferences`; a release cut's `Release issue: #<n>` line is read from `body` |
| tracker | Milestone | `gh issue edit <n> --milestone <M>`; read with `gh issue view <n> --json milestone` |
| tracker | Board status | `gh project item-add <project> --owner <owner> --url <url>`, then `gh project item-edit --project-id <id> --id <item> --field-id <status-field> --single-select-option-id <option>` |
| tracker | List items | `gh issue list -R <o>/<r> --state all --limit 500 --json number,title,body,labels,milestone,state,stateReason,createdAt,url,comments` |
| tracker | Label | `gh issue edit <n> -R <o>/<r> --add-label <label>` (or `--remove-label <label>`); read with `gh issue view <n> --json labels` |
| tracker | Comment | `gh issue comment <n> -R <o>/<r> --body-file <f>` |
| tracker | Close item | `gh issue close <n> -R <o>/<r> --comment <reason>` |
| state tags | Set / clear / read | `gh issue edit <n>` or `gh pr edit <n>` with `--add-label` / `--remove-label crew:<tag>`; read with `gh pr view <n> --json labels` ([Labels](#labels)) |
| state tags | Set approved / set changes | `gh pr edit <n> -R <o>/<r> --add-label crew:approved --remove-label crew:in-review --remove-label crew:changes` (or `crew:changes`, removing `crew:approved`) |
| markers | Write | In the body of a narrative post or verdict (rows above); the `crew:v1` line is an HTML comment ([Markers](#markers)). Never edit a posted review except the synthesizer's diagnostic `pass=gate-status` COMMENT review, updated in place across heads |
| markers | Read | List verdicts (above) and parse each `body`; the builder marker from `gh pr view <n> --json body` |
| markers | Write item | `gh issue comment <n> --body-file <file>` on the repo control issue |
| markers | Read item | `gh api --paginate --slurp repos/<owner>/<repo>/issues/<n>/comments`, preserving post order and login |
| markers | Edit status | `gh api --method PUT repos/<o>/<r>/pulls/<n>/reviews/REVIEW_ID -F body=@<f>` |
| CI | Required-check status at head | `gh pr checks <n> --required --json name,state,link`, after confirming the head SHA; with no branch protection the required set is the profile's [`[ci] required_checks`](../profile.md#ci), each of which must be present at head (#1536) |
| CI | Failing job names | `gh pr checks <n> --json name,state,link`, then `gh run view <run-id> --log-failed` |
| events | Subscribe or poll | Webhooks: `issues` assigned, `pull_request` opened / review_requested / closed (merged or not), `check_suite` completed, `pull_request_review` submitted, `issue_comment` and `pull_request_review_comment` for steering; on Grok Bot, routine triggers ([wake wiring](../runtimes/grok-bot.md#wake-wiring-event-to-consuming-role)). Poll: `gh api repos/<o>/<r>/issues/events` plus the reads above |
| owner channel | Ask with default and deadline | Asked over the runtime's owner channel ([C8](../runtimes/README.md#c8-owner-channel-and-sla)), recorded with `gh issue edit <n> --add-label crew:needs-md` and `gh pr review <n> --comment --body-file <f>` (default and deadline); the answer is recorded as a `steer` post the same way |
| owner channel | Notify | Sent over the runtime's owner channel; recorded with `gh pr review <n> --comment --body-file <f>` (or `gh issue comment <n> --body-file <f>` on an issue) |
| release | Cut | `python3 scripts/changelog-cut.py <version>` on a branch, then Open (above) as the cut PR ([release steps](../release.md#steps) 1–2) |
| release | Approve check | `.github/workflows/release.yml` `prepare`, `ci-gate`, `validate` and the publish job's approval step; read with `gh run view <run-id> --json jobs` |
| release | Record release | The publish job's annotated tag `v<version>` and GitHub Release; read with `gh release view v<version> --json tagName,targetCommitish` |
| release | Notify | The publish job's link on the release issue, then closing it; read with `gh issue view <n> --json state,comments` |
| status | Read records | `connectors/github/status.py read-records` (map `[status]`): `gh api user`, `gh api repos/<o>/<r>/issues/<n>`, then `gh api "repos/<o>/<r>/issues/<n>/comments?per_page=100&page=<k>"` until an empty page; a failed page reports the listing incomplete ([status concern](../interfaces.md#status), #1313) |
| status | Publish record | `connectors/github/status.py publish-record`: `gh api user` equal to the publisher, then one `gh api -X POST repos/<o>/<r>/issues/<n>/comments` (register) or `gh api -X PATCH repos/<o>/<r>/issues/comments/<comment_id>`, body on stdin; HTTP 4xx is `rejected`, no account or another account `not-sent`, anything else short of a success naming the comment `uncertain` |

**Capability declaration.** With two identities, every operation is
`supported`. With one account for all roles, GitHub refuses formal verdicts
from the PR author, so `review.post verdict` is
`emulated (COMMENT-review verdict + recorded owner merge-ok)`, posted with
`gh pr review <n> --comment`; see
[interfaces: Single-identity profile](../interfaces.md#single-identity-profile).
