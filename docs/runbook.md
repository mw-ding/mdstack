# Runbook

mdstack's runbook entry point in the
[essential doc set](project-doc-set.md#essential-doc-set)
([#1219](https://github.com/mw-ding/eng-crew/issues/1219)): how to install,
run, release, operate and recover a crew. Navigation only. Each link goes to
the doc that owns those steps, and this page adds no rule, step or default of
its own.

This is the **operator** route of the [docs index](README.md#find-your-path).
The other routes start elsewhere: a **user** at
[guides/getting-started.md](guides/getting-started.md), a **contributor** at
[../CONTRIBUTING.md](../CONTRIBUTING.md), **reference** lookups at the
[index table](README.md#available-now) and **history** at
[decisions.md](decisions.md).

## Install and onboard

| Task | Owner doc |
|---|---|
| First run: install into the home root, first `up`, the team head, on-demand roles | [guides/getting-started.md](guides/getting-started.md) |
| Put the crew on a new repo, end to end | [runbook-new-repo.md](runbook-new-repo.md) |
| Check prerequisites and identities first | [runbooks/prerequisites.md](runbooks/prerequisites.md) |
| Install from a profile with `mdstack bootstrap` | [runbooks/profile-install.md](runbooks/profile-install.md) |
| Onboard a local tmux crew | [runbooks/tmux-onboarding.md](runbooks/tmux-onboarding.md) |
| Onboard a Grok Bot crew | [runbooks/grok-onboarding.md](runbooks/grok-onboarding.md) |
| Preflight checks with `mdstack doctor` | [bootstrap.md, Q5](bootstrap.md#q5-preflight-checks) |
| Pick connectors and add a knowledge source | [guides/connectors.md](guides/connectors.md) |

## Run and operate

| Task | Owner doc |
|---|---|
| Start a tmux crew or reattach to it (`mdstack start`) | [runbooks/tmux-onboarding.md, Start and reattach](runbooks/tmux-onboarding.md#start-and-reattach) |
| Attach: targeted views never start the crew; a bare `mdstack attach` can | [runbooks/tmux-onboarding.md, Attach modes](runbooks/tmux-onboarding.md#attach-modes) |
| Check status and read a run's logs | [runbooks/tmux-onboarding.md, Status and logs](runbooks/tmux-onboarding.md#status-and-logs) |
| Pause and resume work, or stop the crew safely | [runbooks/tmux-onboarding.md, Pause, resume and stop](runbooks/tmux-onboarding.md#pause-resume-and-stop) |
| Every `mdstack` command | [runtimes/tmux.md, Usage](runtimes/tmux.md#usage) |
| Land changes and run merge trains | [runtimes/tmux.md, mdstack train](runtimes/tmux.md#mdstack-train) |
| Steer the crew (`/crew` commands) | [protocol.md §9](protocol.md#9-steering-crew-commands) |
| Read crew PR cycle time and review rounds | [metrics/README.md](metrics/README.md) and [metrics/decisions.md](metrics/decisions.md) |
| Replay the regression drills after a protocol or harness change | [metrics/regression-drills.md](metrics/regression-drills.md) |

## Release and upgrade

| Task | Owner doc |
|---|---|
| Cut and publish a release | [release.md, Steps](release.md#steps) |
| Upgrade a running tmux crew (`mdstack upgrade`) | [runbooks/tmux-onboarding.md, Upgrade](runbooks/tmux-onboarding.md#upgrade) |
| Upgrade an install to a new release | [release.md, Update path](release.md#update-path) and [bootstrap.md, Q8](bootstrap.md#q8-idempotency-upgrade-and-uninstall) |
| Move from the old layout and the `crew` CLI name | [guides/migration.md](guides/migration.md) |

## Recover

| Task | Owner doc |
|---|---|
| Restart a dead run, the coordinator, or a crew after a reboot | [runbooks/tmux-onboarding.md, Recover](runbooks/tmux-onboarding.md#recover) |
| Fix a tmux crew that misbehaves | [runbooks/tmux-onboarding.md, tmux troubleshooting](runbooks/tmux-onboarding.md#tmux-troubleshooting) |
| Recover duplicate or lost runs | [runtimes/tmux.md, Deduplication and recovery](runtimes/tmux.md#deduplication-and-recovery) |
| Roll back a release | [release.md, Rollback](release.md#rollback) |
| Take the crew off a repo | [runbooks/offboarding.md](runbooks/offboarding.md) |
| Rename the repo (owner-run) | [runbooks/repo-rename.md](runbooks/repo-rename.md) |
