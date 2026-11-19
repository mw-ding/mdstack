# Repository rename

Owner-run runbook for renaming a crew's GitHub repository
([#1234](https://github.com/mw-ding/eng-crew/issues/1234)). The repo name
keys the install's state: the state directory `<state_dir>/<owner>__<name>`,
the tmux session `crew-<owner>-<name>`, each host's job root
`<root>/<owner>__<name>`, the profile's `[repo]` table and slugs, and the
turn-end guard's `--state` argument. `mdstack migrate --rename-to` plans and
applies that move. GitHub itself keeps the old URLs working.

Use the copy of this runbook in the release the install runs. The crew never
renames a repo itself: every step below is the owner's.

## What changes and what stays

- **Changes:** the repo slug, the state directory, the tmux session name,
  each host's job root, the profile's `[repo]` name and every quoted
  `"<owner>/<old>"` slug in it, state paths cited by the profile, the
  operational state files and bootstrap's `install.json`, and the guard in
  the home's `.claude/settings.local.json`.
- **Stays:** the owner (a rename keeps it; a transfer is out of scope), the
  checkout, the worktrees and their paths, the CLI name, `crew:` labels and
  markers, `CREW_*` variables and historical records (verdicts, trains,
  CHANGELOG, issue links). Product names are not the repo name: 7.0.0
  renamed them (`mdstack-<version>` bundle and toolkit, `<state>/mdstack`
  link, `paths.mdstack` and `pack.mdstack_version` keys) with no
  compatibility path; a 6.x install is reinstalled
  ([migration](../guides/migration.md#product-names-700)).
- **Old URLs:** GitHub redirects the old repo URL, API path, git remote and
  issue and PR links to the new name, so old slugs in records, packs and
  remotes keep working. The redirect breaks if anyone later creates a repo
  with the old name under the same owner. Never do that.

## Steps

1. **Dry run**, any time, with the crew running or not. It writes nothing:

   ```sh
   cli/mdstack migrate --rename-to <owner>/<new>
   ```

   Read the plan:
   - `map` and `move` show the state directory's new path.
   - `name` lines show the repo slug and the session.
   - `keep` lines show any profile path that holds the old name by
     choice. A later `mdstack migrate --to` can move those.
   - `rewrite` lines show the profile, the settings and each state file.
   - `owner:` lines are steps the crew never takes: the GitHub rename, each
     host root to move and the optional remote URL.
   - `blocked:` lines must be cleared before `--apply`.
2. **Stop the crew:** `cli/mdstack down --preserve`. Wait for no open land lock.
3. **Rename on GitHub**, as an identity with admin rights on the repo:
   `gh repo rename <new> -R <owner>/<old>`.
4. **Check the redirect.** Each of these must answer for the new name:

   ```sh
   gh api repos/<owner>/<old> --jq .full_name     # <owner>/<new>
   git ls-remote https://github.com/<owner>/<old>.git HEAD
   gh issue view 1 -R <owner>/<old> --json url --jq .url   # .../<owner>/<new>/issues/1
   ```

5. **Apply** only after step 4 passes: rerun step 1's command with
   `--apply`. It refuses while anything is blocked. It moves the state
   directory, then rewrites the profile, the settings and the state files,
   saving each original under `<new state>/migration/<stamp>/`.
6. **Owner steps** from the plan:
   - Move each host's `<root>/<owner>__<old>` to `<root>/<owner>__<new>`
     before the next `mdstack host prepare`.
   - Optionally point the checkout at the new URL: `git -C <checkout> remote
     set-url origin https://github.com/<owner>/<new>.git`. Worktrees share
     the checkout's remote.
   - Update pack pins and bookmarks that name the old URL when convenient.
     The redirect covers them meanwhile.
7. **Restart:** `cli/mdstack layout --write`, then
   `cli/mdstack up --coordinator-only`, then `cli/mdstack doctor`. The session now runs as
   `crew-<owner>-<new>`.

## Rollback

- **A failed apply** prints the completed steps and their rollback commands.
  Run them newest first. Each original is under
  `<new state>/migration/<stamp>/originals/`.
- **To undo a finished rename:** stop the crew, run `gh repo rename <old> -R
  <owner>/<new>`, check the redirect from the new name, then run
  `mdstack migrate --rename-to <owner>/<old> --apply`.

See [mdstack migrate](../runtimes/tmux.md#mdstack-migrate) for the full plan
format.
