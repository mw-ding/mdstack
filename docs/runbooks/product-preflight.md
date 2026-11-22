# Product preflight

Onboarding module for the product-safety checks done before the crew goes
live on the target repo, split out of the
[onboarding runbook](../runbook-new-repo.md) under the M26 modular
organization principle
([#676](https://github.com/mw-ding/mdstack/issues/676)). It holds the runbook's
[Step 5: product-safety checks](../runbook-new-repo.md#step-5-product-safety-checks)
with its items 1 to 3 in
[Automation, namespace and fork preflight](#automation-namespace-and-fork-preflight)
and its items 4 to 8 in
[Workflow, repo-contract, toolchain and cutover checks](#workflow-repo-contract-toolchain-and-cutover-checks),
before
[Step 6: state dir and wiring doc](../runbook-new-repo.md#step-6-state-dir-and-wiring-doc).

## Step 5: product-safety checks

### Automation, namespace and fork preflight

Do these before installing any routine; installing routines is what makes the
crew live. The wiring doc's section 0 ("Facts found in the repo") is where the
answers go.

1. **One automation system per repo.** The protocol allows only one automation
   system to own a repo at a time ([protocol.md](../protocol.md#8-safety)). Look for
   others and decide who owns what before continuing:

   ```bash
   gh api repos/<owner>/<repo>/hooks --jq '.[] | {name, events, active}'
   gh label list -R <owner>/<repo> --limit 200
   gh api repos/<owner>/<repo>/contents/.github --jq '.[].name'
   ```

   Look for webhooks, GitHub Apps, dependency bots, merge queues, auto-merge,
   other bots that react to labels or comments, and a product-side
   orchestrator. If any of them also assigns issues, opens PRs, reviews or
   merges, they must be switched off for the repo or scoped away from crew PRs
   before you continue. Write the decision into the wiring doc.

2. **Do not touch the product's own labels or commands.** The crew uses only
   `crew:*` labels and comment commands that begin with the steering prefix.
   If the product has its own labels, slash commands, PR completion contracts,
   or live E2E flows that open and close issues or PRs on the same repo, list
   them, and make sure no crew routine acts on them. A scratch or E2E PR still
   fires `pr-opened`; the reviewer's intake prompt must name how it ignores
   them (a title tag, a base-branch pattern). Never rename, delete or recolor
   a product label, even to "tidy up".

3. **Fork PRs and external contributors.** PRs from forks are untrusted
   ([protocol.md](../protocol.md#8-safety)):
   - The reviewer intake routine has no allowlist, so it labels them
     `crew:external` and runs validation in an isolated sandbox with **no
     tokens**.
   - A first-time contributor's workflows may wait for a maintainer's "Approve
     and run" click; until then there is no CI and no `ci-passed`. The
     reviewer flags it to the coordinator, who tells the user.
   - The steering dispatcher's allowlist gates the PR **author**, so it does not
     fire on external PRs. A per-PR comment watch is added only when the user
     wants to steer one.
   - Builders never push to fork branches.
   - If the repo itself is a fork of an upstream, upstream syncs have to go
     through a PR when branch protection is on; the sync button and direct
     pushes will be blocked.
   - Check `Settings > Actions > General > Fork pull request workflows` so
     that fork PRs do not get repo secrets.

### Workflow, repo-contract, toolchain and cutover checks

<!-- markdownlint-disable MD029 -->

4. **No workflow deletion that removes push CI on the default branch** (pilot
   lesson, Oct 19, 2026). In the pilot, the test workflow was only called by a
   release workflow; deleting the failing release workflow would have removed
   the repo's only push CI on `<default-branch>`. The fix was to keep the
   release workflows but make them manual-only (`workflow_dispatch`), and to add
   a push trigger on `<default-branch>` to the test workflow. Before touching
   any workflow file:

   ```bash
   grep -rn -E 'workflow_call|workflow_dispatch|^on:|^  push:|^  pull_request:|uses: \./\.github/workflows' .github/workflows
   ```

   Work out which workflow actually runs tests on push to `<default-branch>`,
   and which workflows call which. Disable a noisy workflow by trigger change
   or `gh workflow disable`, never by deletion, unless something else provides
   the same push CI. After the change, push or merge once and confirm a push run
   appears (`gh run list --branch <default-branch> --event push`).

5. **Repo rules that change the crew's wording.** Read the repo's contributor
   docs (`CONTRIBUTING`, agent instructions, PR templates). If the repo forbids
   closing keywords in PR bodies, the builder writes `Refs #<n>`; that satisfies
   the merge gate, and the coordinator closes the issue after merge
   ([wiring.md pilot findings](../../templates/runtimes/grok-bot/wiring.md#8-pilot-findings)). If it
   mandates a commit or PR-title convention (for example conventional titles),
   put it in every worker brief.

6. **Toolchain.** Find what hooks and CI need (pre-push hooks that need a
   particular runtime, package-manager caches that need a writable home). Record
   the `PATH` and environment setup as `<toolchain-bin>` (`paths.toolchain_bin`
   in `config.toml`; re-run Step 0 if it changed); every build and fix worker
   brief sets it before any commit or push.

7. **Existing open PRs and issues.** `pr-opened` never fires for PRs that
   already exist, and issues need `crew:ready` plus assignment. Decide whether
   to run the cutover for each open PR
   ([cutover](../runbook-new-repo.md#cutover-for-existing-open-prs)) or to leave them with their
   authors.

8. **Deploy secrets.** Record shared deploy secret names and consuming hosts
   in the wiring doc; add the
   [protocol §3 sync AC](../protocol.md#3-evidence-requirements) to new deploy
   milestones/issues.

<!-- markdownlint-enable MD029 -->
