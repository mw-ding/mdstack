# Offboarding

Onboarding module for removing the crew from a repo, split out of the
[onboarding runbook](../runbook-new-repo.md) under the M26 modular
organization principle
([#676](https://github.com/mw-ding/eng-crew/issues/676)). It holds the
runbook's whole
[Rollback and offboarding](../runbook-new-repo.md#rollback-and-offboarding)
section: the bootstrap-managed uninstall, then the ordered manual steps. The
routine IDs in step 2 are the ones recorded in item 9 of the runbook's
[Verification checklist](../runbook-new-repo.md#verification-checklist), and
the merge settings in step 4 are the evidence captured in
[Step 4: check CI and branch protection](../runbook-new-repo.md#step-4-check-ci-and-branch-protection).
Nothing in this module runs by itself; each command is an operator step.

## Rollback and offboarding

From a host terminal outside the crew session, preview a bootstrap-managed
install with `mdstack bootstrap [--repo <key>]
--uninstall --dry-run`, then apply with `--uninstall --yes`. This pauses open
crew PRs and ready issues, stops tmux while preserving run files and worktrees,
removes unchanged untracked install targets and their exclude entries, and archives
state beside its original location. Unlanded runs block target removal and
archival after the runtime stops. Edited targets, leftover worktrees, wiring
and evidence are kept. Labels stay unless `--remove-labels` is explicit.
Grok Bot pauses items first and waits for manual routine removal; after marking
the IDs in `wiring.md` removed and checking no new wakes, retry with
`--routines-removed`. Project, collaborator and protection changes stay human
steps. The archived `install.json` records removed and kept paths. Open PRs
remain held until their authors take them back.

Everything the runbook did is reversible. Do it in this order so no bot acts on
a half-removed setup.

1. **Pause.** Add `crew:hold` to every open crew PR and `crew:ready` issue so
   every bot no-ops: `gh pr edit <n> -R <owner>/<repo> --add-label crew:hold`.
   Tell the user which PRs and issues are in flight.
2. **Remove the routines**, newest first, using the IDs recorded in checklist
   item 9. A routine run cannot delete routines, so this is done from each
   bot's parent turn:
   - The per-PR watches B2 and V2 for every open PR.
   - The standing routines B1, V1, S1, A1, A2 and A3.
   Mark each row `removed` with a date in the wiring doc. Confirm no wake
   arrives for a new comment or assignment.
3. **Revoke the collaborator** if the reviewer account should no longer have
   access. This also stops its reviews from counting:

   ```bash
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api -X DELETE repos/<owner>/<repo>/collaborators/<reviewer-login>
   # a pending, unaccepted invitation instead:
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api -X DELETE repos/<owner>/<repo>/invitations/<invitation-id>
   ```

4. **Undo enforcement** if the owner wants the old settings back: remove or
   relax branch protection, and restore the merge settings recorded in the
   evidence from step 4:

   ```bash
   GH_TOKEN=$(gh auth token --user <author-login>) \
     gh api -X DELETE repos/<owner>/<repo>/branches/<default-branch>/protection
   ```

5. **Labels are optional.** The ten `crew:*` labels are harmless and can stay.
   To remove them, delete each one (this also strips it from issues and PRs;
   do it only after step 1 has paused everything):

   ```bash
   for l in ready in-review changes approved escalated hold external spec needs-md needs-mirror; do
     GH_TOKEN=$(gh auth token --user <author-login>) gh label delete "crew:$l" -R <owner>/<repo> --yes
   done
   ```

6. **Project.** Unlink or keep it: `gh project unlink <project-number> --owner <owner> --repo <repo>`.
   Close or delete it only if the owner agrees.
7. **State dir.** Archive `<state-dir>/<owner>__<repo>/` (keep `wiring.md` and
   the evidence file) and remove `claims/` and `locks/`. Delete leftover worker
   worktrees and build output for the repo.
8. **Open PRs.** Hand them back to their authors. Do not post a farewell
   comment; remove `crew:hold` once the routines are gone.
9. **Record it.** Add a dated entry to the wiring doc and the evidence file
   saying what was removed and what was kept, and file an issue for anything
   that did not roll back cleanly.
