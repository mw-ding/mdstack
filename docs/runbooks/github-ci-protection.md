# GitHub CI and branch protection

Onboarding module for the target repo's CI and branch protection setup,
split out of the [onboarding runbook](../runbook-new-repo.md) under the M26
modular organization principle
([#676](https://github.com/mw-ding/mdstack/issues/676)). It holds the
runbook's whole Step 4, between
[Step 3: create Milestones and link a GitHub Project (v2)](../runbook-new-repo.md#step-3-create-milestones-and-link-a-github-project-v2)
and
[Step 5: product-safety checks](../runbook-new-repo.md#step-5-product-safety-checks):
CI discovery and current protection inspection, items 1 to 4; the owner's
protection choice, item 5, in [Protection choice](#protection-choice); and
merge settings and enforcement limits, items 6 and 7, in
[Merge settings and enforcement limits](#merge-settings-and-enforcement-limits).
The `<author-login>` identity is defined in the runbook's prerequisite
[Identities](../runbook-new-repo.md#identities) section.

## Step 4: check CI and branch protection

The crew is driven by CI results (`ci-passed`, `ci-failed`) and gated on
required checks, so read what the repo has before wiring anything.

1. List the workflows and when they run:

   ```bash
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api repos/<owner>/<repo>/actions/workflows --jq '.workflows[] | {name, path, state}'
   gh api repos/<owner>/<repo>/contents/.github/workflows --jq '.[].name'
   ```

   Open each workflow file and write down its `on:` triggers. For each,
   record whether it runs on `pull_request` (and which activity types: PR title
   or body edits and `ready_for_review` change what fires `ci-passed`), on push
   to `<default-branch>`, on a schedule, or only on `workflow_dispatch` or
   `workflow_call`.

2. Check **push CI on the default branch**. If a workflow runs on push to
   `<default-branch>`, the coordinator's after-merge routine must also listen
   for `ci-failed` with `ciBranch` set to `<default-branch>`
   ([coordinator-after-merge.md](../../templates/runtimes/grok-bot/coordinator-after-merge.md)). If
   none does, drop that listener, and consider adding push CI to the test
   workflow so a bad merge is noticed.

   ```bash
   gh run list -R <owner>/<repo> --branch <default-branch> --event push --limit 10 \
     --json workflowName,conclusion,headSha,createdAt
   ```

   A workflow that fails on every push for a reason that is not code (for
   example a release job with no credentials on a fork) would fire `ci-failed`
   on every merge. Record it as known noise with an issue, and fix it by making
   the job manual-only, not by deleting it
   ([Step 5](../runbook-new-repo.md#step-5-product-safety-checks)).

3. Find the required check names. Use the names of the checks on a green PR
   head, exactly as GitHub reports them:

   ```bash
   gh api repos/<owner>/<repo>/commits/<green-head-sha>/check-runs \
     --jq '.check_runs[] | {name, conclusion, app: .app.slug}'
   ```

   Prefer one aggregate check (a final job that depends on the others and still
   reports when suites are skipped) over listing matrix job names. If the
   workflow can skip, make sure the aggregate still reports.

4. Read the current protection and merge settings:

   ```bash
   gh api repos/<owner>/<repo>/branches/<default-branch>/protection
   gh api repos/<owner>/<repo>/rulesets
   gh api repos/<owner>/<repo> \
     --jq '{squash: .allow_squash_merge, merge: .allow_merge_commit, rebase: .allow_rebase_merge, delete_branch: .delete_branch_on_merge, auto_merge: .allow_auto_merge}'
   ```

   A 404 "Branch not protected" from the first call is the normal answer for an
   unprotected branch.

### Protection choice

<!-- markdownlint-disable MD029 -->
<!-- Items 5 to 7 continue the Step 4 list across subsections. -->

5. Choose a protection level with the owner. All are reversible
   ([Rollback](../runbook-new-repo.md#rollback-and-offboarding)); the crew works at every level.

   | Level | What it adds | Cost |
   |---|---|---|
   | A. Convention only | Nothing. The synthesizer checks the merge gate itself ([protocol.md](../protocol.md#7-merge-gate-synthesizer)) | Anyone with write access, including a bot with the wrong token, can merge or push |
   | B. Required checks | Required status checks on `<default-branch>` | Merges blocked while checks are red or missing |
   | C. Checks plus 1 review (pilot) | B, plus one approving review, administrators included, no force pushes or deletions | Blocks the owner's own manual merges and direct pushes too, unless they go through the same gate or the setting is toggled |

   Apply level C (adjust the checks; drop what you did not choose):

   ```bash
   cat > protection.json <<'EOF'
   {
     "required_status_checks": {
       "strict": false,
       "checks": [ { "context": "<aggregate-check-name>", "app_id": 15368 } ]
     },
     "required_pull_request_reviews": {
       "required_approving_review_count": 1,
       "dismiss_stale_reviews": false,
       "require_code_owner_reviews": false,
       "require_last_push_approval": false
     },
     "enforce_admins": true,
     "restrictions": null,
     "allow_force_pushes": false,
     "allow_deletions": false
   }
   EOF
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api -X PUT repos/<owner>/<repo>/branches/<default-branch>/protection --input protection.json
   rm protection.json
   ```

   `app_id` 15368 is GitHub Actions; use `-1` to accept the check from any
   source. Stale approvals stay valid on purpose: the synthesizer's SHA-bound
   marker check keeps approvals current, and turning on
   `dismiss_stale_reviews` makes every merge-up need a fresh approval.
   Before turning protection on, make sure no workflow pushes to
   `<default-branch>` (release jobs often do); the review gate would block it.

### Merge settings and enforcement limits

6. Squash-only merges and branch cleanup. Merge-ups by update-branch still
   create merge commits on PR branches; this setting only affects how a PR
   lands on `<default-branch>`:

   ```bash
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api -X PATCH repos/<owner>/<repo> \
     -F allow_squash_merge=true -F allow_merge_commit=false \
     -F allow_rebase_merge=false -F delete_branch_on_merge=true
   ```

7. "Only the synthesizer merges" stays a **convention** while bots share an
   account. Real enforcement needs the synthesizer on its own identity (for
   example a GitHub App) in an org repo where merge restrictions can name it.
   Record that as a known gap, not a blocker.
   See [merge enforcement](../merge-enforcement.md) for a ruleset alternative,
   squash-only merging and personal-repository limits.

<!-- markdownlint-enable MD029 -->

Capture the outputs of items 1 to 6 for the checklist.
