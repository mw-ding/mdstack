# Merge enforcement

> - **Status:** design
> - **Applies to:** this repo's default branch on GitHub
> - **Current rules:** the [§7 merge gate](protocol.md#7-merge-gate-synthesizer), enforced by the synthesizer, not the platform
> - **Built:** nothing applied; on 2026-11-07 `main` still had no branch protection (404) and no rulesets
> - **Last checked:** 2026-11-07 at `02ca805`

P11 / issue #67, M4 batch: back the [§7 merge gate](protocol.md#7-merge-gate-synthesizer)
with platform rules while preserving Vera's review and Sam's serial squash
merge roles. This runbook documents a target; **nothing has been applied**.

## Current state: mdstack (2026-10-28)

A read-only inspection found `mw-ding/mdstack` private, user-owned,
with default branch `main`. The `mw-ding` token has `permissions.admin: true`.
However, GET requests for repository rulesets, `branches/main/protection`,
and `rules/branches/main` all returned HTTP 403:

```text
Upgrade to GitHub Pro or make this repository public to enable this feature.
```

The gap is the account plan, not token admin permission: GitHub Free personal
accounts cannot protect private repositories. `main` is unprotected; Sam-only
merging and no force-push are conventions. Squash, merge commits and rebase
merges are all currently enabled. There is no live ruleset ID to link yet;
record it here after application and verification.

This plan-level blocker is tracked in **[#80](https://github.com/mw-ding/eng-crew/issues/80)**
(Blocked: Free-plan GitHub ruleset cannot enforce Sam-only merge on private
repos). Keep #80 open until the account can apply the target ruleset (or an
App-based alternative lands); then close it with what was applied.

## Target rules: mdstack

| Rule | Value | Why | §7 gate backed |
|---|---|---|---|
| Default-branch PR | PR required on `~DEFAULT_BRANCH` | Prevent direct pushes to `main` | PR state |
| Approval | 1 non-author approval; no code-owner or last-push requirement | `<reviewer-account>` (Vera's write-collaborator account) is the only qualifying non-author today; the user's `/crew merge-ok` is also posted as a `<reviewer-account>` APPROVE | Formal approval |
| Required checks | `markdownlint`, `links`, `repo-guard`; GitHub Actions app 15368 | Exact job names observed on `main` at `8eda267` | CI green at head |
| Up-to-date branch | `strict_required_status_checks_policy=false` | Synthesizer updates behind PR branches itself; avoid extra merge-ups | CI / mergeability |
| Stale approvals | `dismiss_stale_reviews_on_push=false` | SHA-bound markers and merge-up re-approval remain protocol checks | Formal approval at head |
| Merge method | Squash only | Preserve serial squash landing | Synthesizer merge procedure |
| Force-push / deletion | Both forbidden | Preserve default-branch history | Safety of merge procedure |
| Bypass actors | Empty, including no admin bypass | Bind owner/admin `mw-ding` to the same rules | Approval + CI |

### What stays convention

Ben and Sam both use owner/admin `mw-ding`. GitHub cannot distinguish their
actions. Personal repositories cannot restrict push/merge to named users or
apps; their ruleset bypass actors are limited to repository admin role and
deploy keys. Identity-level Sam-only enforcement needs Sam's own identity
(for example a GitHub App) in an organization repository that can restrict
merging to it. Sam retains the merge lock and serial merge duty meanwhile.

The platform approval count does not validate SHA-bound crew markers, user
permission, validation, watches, mirror holds or other §7 conditions; the
synthesizer still checks all of §7. Optional CODEOWNERS (`* @<reviewer-account>` plus
`require_code_owner_review`) could pin the reviewer, but is not recommended
now: it auto-requests review on every PR and fires `review-requested`, which
Vera's V2 listens to.

## Prerequisites and application: mdstack

MD must upgrade `mw-ding` to GitHub Pro, or move the repository to a paid
organization (reassess this personal-repo recipe after a move). Making the
repository public is not an option: it is private by design. MD applies only
after MD's/Ash's explicit go; Ash records the result. This documentation
authorizes no settings change. The Free-plan gap is the blocked issue
[#80](https://github.com/mw-ding/eng-crew/issues/80); do not invent a waiver.

After the plan prerequisite and go, first read the existing rulesets to avoid
creating a duplicate. If none implements this gate, write the following file
and apply it as MD:

```bash
cat > ruleset.json <<'EOF'
{
  "name": "main: crew merge gate (P11)",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["squash"] } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": false,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "markdownlint", "integration_id": 15368 },
          { "context": "links", "integration_id": 15368 },
          { "context": "repo-guard", "integration_id": 15368 } ] } }
  ]
}
EOF
GH_TOKEN=$(gh auth token --user mw-ding) \
  gh api -X POST repos/mw-ding/mdstack/rulesets --input ruleset.json
```

Optionally, with the same go, make repository merge settings squash-only too.
GitHub update-branch merge-ups on PR branches are unaffected:

```bash
GH_TOKEN=$(gh auth token --user mw-ding) \
  gh api -X PATCH repos/mw-ding/mdstack \
  -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false
```

## Verify: mdstack

```bash
GH_TOKEN=$(gh auth token --user mw-ding) gh api repos/mw-ding/mdstack/rulesets
GH_TOKEN=$(gh auth token --user mw-ding) gh api repos/mw-ding/mdstack/rules/branches/main
```

Expect one active gate ruleset and effective rules `deletion`,
`non_fast_forward`, `pull_request`, `required_status_checks`. Inspect its
parameters against the target table and save its ID and returned ruleset URL
here with the application date; until then this gate is **not live**.
On the next crew PR, before approval, run `gh pr view` with that PR's number,
`-R mw-ding/mdstack --json mergeStateStatus,reviewDecision`: expect
`BLOCKED` / `REVIEW_REQUIRED`. After Vera's APPROVE and green checks, expect
`CLEAN`; still check every §7 condition before merging. Do not test by
force-pushing `main`.

## Rollback: mdstack

MD/admin can disable the created ruleset, using its ID from verification:

```bash
GH_TOKEN=$(gh auth token --user mw-ding) \
  gh api -X PUT repos/mw-ding/mdstack/rulesets/<ruleset-id> -f enforcement=disabled
```

Alternatively delete it with `gh api -X DELETE
repos/mw-ding/mdstack/rulesets/<ruleset-id>` under the same identity. If the
optional merge-settings PATCH was applied, restore the observed settings with:

```bash
GH_TOKEN=$(gh auth token --user mw-ding) \
  gh api -X PATCH repos/mw-ding/mdstack \
  -F allow_squash_merge=true -F allow_merge_commit=true -F allow_rebase_merge=true
```

Ash records the rollback; §7 remains in force.

## Gate contract and fail-open

Under the [gate contract](protocol.md#gate-contract), this platform gate is
satisfied by the verified active ruleset: required checks, one non-author
approval, squash only, no force-push/deletion, no bypass. GitHub enforces it
at merge time. Vera's APPROVE (or the user's `/crew merge-ok` steer posted as
`<reviewer-account>` APPROVE) and green CI already satisfy §7, so it adds no new wait.

While it is not live (today — see [#80](https://github.com/mw-ding/eng-crew/issues/80)),
the synthesizer's §7 checks remain the only enforcement, by convention;
nothing changes for the crew. If a live ruleset
blocks a merge §7 would permit (for example a renamed check), use the
[owner-decision path](protocol.md#gate-contract): the coordinator escalates;
MD/admin fixes the check list or temporarily sets `enforcement=disabled`.
Never merge through red CI or bypass by force-pushing.

## Other repositories

For `<owner>/<repo>`, discover `<check-name>` and its app identity, account
plan, default branch, reviewers and existing protections using
[runbook Step 4](runbook-new-repo.md#step-4-check-ci-and-branch-protection).
Adapt the rules only with that owner's go; keep shared-identity limitations
and the §7 checks explicit.

Separate follow-up, observed 2026-10-28: public `mw-ding/agentconnect` already
has classic protection on `main`, requiring `CI OK` and `Conventional PR`
(app 15368), one approval and admin enforcement. With its owner's go,
consider an equivalent ruleset with squash-only and no force-push/deletion.
Identity-level Sam-only has the same shared-account gap. This follow-up has
not been applied.
