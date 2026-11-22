# GitHub tracking

Onboarding module for the target repo's GitHub tracking setup, split out of
the [onboarding runbook](../runbook-new-repo.md) under the M26 modular
organization principle
([#676](https://github.com/mw-ding/mdstack/issues/676)). It holds the
runbook's Step 1, the `crew:*` label setup, between
[Step 0: write, validate and render the profile](../runbook-new-repo.md#step-0-write-validate-and-render-the-profile)
and
[Step 2: add the reviewer as a collaborator](../runbook-new-repo.md#step-2-add-the-reviewer-as-a-collaborator),
and the runbook's Step 3, Milestones and the GitHub Project board, in
[Step 3: create Milestones and link a GitHub Project (v2)](#step-3-create-milestones-and-link-a-github-project-v2),
before
[Step 4: check CI and branch protection](../runbook-new-repo.md#step-4-check-ci-and-branch-protection).
The `<author-login>` identity is defined in the runbook's prerequisite
[Identities](../runbook-new-repo.md#identities) section.

## Step 1: create the `crew:*` labels

Thirteen labels. Labels are safe state because no listener fires on them
([architecture.md](../architecture.md#labels) says who sets and clears each;
[GitHub backend: Labels](../backends/github.md#labels) has the label mechanics). The
names, colors and descriptions below are the ones used on the framework repo.
The `crew:needs-md` description says "owner decision" instead of a person's initials.

Before creating labels, list the existing namespace and capture the output:

```bash
export GH_TOKEN=$(gh auth token --user <author-login>)
gh label list -R <owner>/<repo> --search crew: --json name,color,description
```

If it returns no labels, proceed. If it returns exactly the thirteen labels below,
with these colors and descriptions, and
`<state-dir>/<owner>__<repo>/wiring.md` exists, this is an existing crew install;
rerunning with `--force` is safe. Any other result (other `crew:*` names,
different colors or descriptions, or no wiring doc) is a namespace collision.
Stop: another automation may own it
([step 5](../runbook-new-repo.md#step-5-product-safety-checks)).

After that pre-check:

```bash
while IFS='|' read -r name color desc; do
  gh label create "$name" -R <owner>/<repo> --color "$color" --description "$desc" --force
done <<'EOF'
crew:ready|0E8A16|Released to the builder; issue may be assigned and built
crew:in-review|1D76DB|PR open, awaiting CI + review/validation
crew:changes|D93F0B|Reviewer requested changes; builder fix round due
crew:approved|5319E7|Reviewer approved at head; synthesizer may merge
crew:escalated|B60205|Round/CI-fix cap hit or escalated; bots no-op until /crew resume
crew:hold|FBCA04|Paused: every bot no-ops on this item
crew:external|C5DEF5|External/fork PR: sandboxed validation, no tokens
crew:spec|0052CC|Spec PR: review pass only, merges on /crew merge-ok
crew:needs-md|F9D0C4|Blocked on an owner decision (recommended default + deadline)
crew:needs-mirror|E99695|Protocol/template change: merge blocked until the box skill is mirrored
crew:sensitive|B60205|Requires per-change owner merge-ok; no standing grant applies.
crew:express|BFD4F2|Express lane: builder builds and self-gates; no reviewer verdict
crew:solo|FEF2C0|Solo lane: the owner session builds and fixes; reviewer stays independent
EOF
```

`--force` updates the color and description if the label already exists, so the
command is safe to rerun only after the pre-check above. The same call through
the API, for one label:

```bash
gh api -X POST repos/<owner>/<repo>/labels \
  -f name='crew:ready' -f color='0E8A16' \
  -f description='Released to the builder; issue may be assigned and built'
```

Verify (capture this output):

```bash
gh label list -R <owner>/<repo> --search crew: --json name,color,description
```

Expect exactly thirteen rows, no extra `crew:*` label, and every color/description
as above.

## Step 3: create Milestones and link a GitHub Project (v2)

Every crew repo requires GitHub Milestones **M1, M2, …**; a GitHub Project
board is recommended, not required
([GitHub backend: Milestones and board](../backends/github.md#milestones-and-board)).
Create the current milestone before handoff and assign issues to the
appropriate open `M*`. A **closed milestone is frozen**: no new issues may be
added to it; follow-ups go to the next `M*`. Capture the milestone list and
issue assignments as onboarding evidence.

The coordinator keeps the board item status current: Todo for new issues,
In Progress while a PR is being built, In Review while it is under review,
Done after merge.

1. Check the scope first. `project` must be on the identity that will run the
   commands (see [Token scopes](../runbook-new-repo.md#token-scopes)). If it is not, follow the
   missing-scope options there before completing this step. A symptom of a
   missing scope is a GraphQL error that names the `project` scope or the
   `read:project` scope.

2. Create it and link it to the repo:

   ```bash
   export GH_TOKEN=$(gh auth token --user <login-with-project-scope>)
   gh project create --owner <owner> --title "<repo> crew board" --format json
   gh project link <project-number> --owner <owner> --repo <repo>
   ```

   Note `number` from the JSON output; that is `<project-number>`.

3. Set the Status field to exactly four options: Todo, In Progress, In Review,
   Done. A new project has the built-in Status field with Todo, In Progress and
   Done; In Review has to be added. List the field:

   ```bash
   gh project field-list <project-number> --owner <owner> --format json
   ```

   If the Status field already shows all four options, you are done. Otherwise
   add the missing option in the Project's settings page (field "Status", add
   option "In Review"), or replace the option list through GraphQL while the
   project is still empty (replacing options on a project that has items can
   clear their status values):

   ```bash
   gh api graphql -f query='
     mutation($field: ID!) {
       updateProjectV2Field(input: {
         fieldId: $field,
         singleSelectOptions: [
           {name: "Todo",        color: GRAY,   description: ""},
           {name: "In Progress", color: YELLOW, description: ""},
           {name: "In Review",   color: PURPLE, description: ""},
           {name: "Done",        color: GREEN,  description: ""}
         ]
       }) { projectV2Field { ... on ProjectV2SingleSelectField { options { name } } } }
     }' -f field='<status-field-id>'
   ```

   `<status-field-id>` is the `id` of the Status field in the `field-list`
   output. If the mutation is rejected on your GitHub version, use the settings
   page.

4. Make sure the board's auto-add and status workflows do not conflict with the
   crew: the coordinator adds issues and the builder adds PRs by hand. A
   built-in "item closed" → Done workflow is fine.

5. Verify (capture this output):

   ```bash
   gh project view <project-number> --owner <owner> --format json --jq '{number, title, url}'
   gh project field-list <project-number> --owner <owner> --format json \
     --jq '.fields[] | select(.name=="Status") | .options[].name'
   gh api graphql -f query='query($o: String!, $r: String!) { repository(owner: $o, name: $r) { projectsV2(first: 10) { nodes { number title } } } }' \
     -f o=<owner> -f r=<repo>
   ```

   Expect four option names in order, and the project listed under the repo's
   linked projects.

Record `<project-number>` and the current `M*` milestone in the wiring doc.
