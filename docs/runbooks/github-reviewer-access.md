# GitHub reviewer access

Onboarding module for giving the reviewer identity write access to the target
repo, split out of the [onboarding runbook](../runbook-new-repo.md) under the
M26 modular organization principle
([#676](https://github.com/mw-ding/mdstack/issues/676)). It is the runbook's
Step 2, between
[Step 1: create the `crew:*` labels](../runbook-new-repo.md#step-1-create-the-crew-labels)
and
[Step 3: create Milestones and link a GitHub Project (v2)](../runbook-new-repo.md#step-3-create-milestones-and-link-a-github-project-v2).
The two crew identities, `<author-login>` and `<reviewer-login>`, are defined
in the runbook's prerequisite
[Identities](../runbook-new-repo.md#identities) section, and the per-command
credential rule in
[Per-identity `gh` usage](../runbook-new-repo.md#per-identity-gh-usage).

## Step 2: add the reviewer as a collaborator

The reviewer identity needs **write** access so its reviews are binding and
counted by branch protection. On a user-owned repo that is an invitation the
reviewer account must accept.

1. Invite, as the repo admin. The response carries the invitation id.

   ```bash
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api -X PUT repos/<owner>/<repo>/collaborators/<reviewer-login> \
     -f permission=push --jq '{id, invitee: .invitee.login, permissions}'
   ```

   On an org repo where `<reviewer-login>` is already an org member, access is
   granted at once and the call returns no body; skip to the verify step.

2. Accept, as the reviewer identity.

   ```bash
   GH_TOKEN=$(gh auth token --user <reviewer-login>) \
     gh api user/repository_invitations --jq '.[] | {id, repo: .repository.full_name}'
   GH_TOKEN=$(gh auth token --user <reviewer-login>) \
     gh api -X PATCH user/repository_invitations/<invitation-id>
   ```

   If the reviewer account cannot be driven from the box, the invitation link
   in its email or notifications does the same thing; record how it was done.

3. Verify (capture this output):

   ```bash
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api repos/<owner>/<repo>/collaborators/<reviewer-login>/permission \
     --jq '{user: .user.login, permission}'
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api repos/<owner>/<repo>/invitations --jq 'length'
   ```

   Expect `permission` of `write` and no pending invitation (`0`).

Also confirm the author identity has push access to the repo (and, if the repo
is a fork, to its own branches; builders never push to someone else's fork).
