# Profile install

Onboarding module for installing the crew from a profile with
`mdstack bootstrap`, split out of the [onboarding runbook](../runbook-new-repo.md)
under the M26 modular organization principle
([#676](https://github.com/mw-ding/eng-crew/issues/676)). It is the
recommended path of the runbook's
[Step 0: write, validate and render the profile](../runbook-new-repo.md#step-0-write-validate-and-render-the-profile),
after the [Prerequisites](../runbook-new-repo.md#prerequisites), and holds its
[manual fallback](#manual-fallback). The onboarding Steps 1–8 stay in the
runbook.

## Bootstrap (recommended)

Start with an extracted, checksum-verified release bundle from
[README: Install](../../README.md#install), or a checkout at an exact stable
release tag. Use a release that includes `mdstack bootstrap`; check
`<mdstack>/cli/mdstack bootstrap --help`. An untagged development checkout
requires `--dev`, records its commit SHA and satisfies no version pin.

Write the profile using item 1 of the [manual fallback](#manual-fallback).
For tmux, write `~/.mdstack/config.toml` as in
[Write the config](../guides/getting-started.md#2-write-the-config), the
copyable first-run path. Set every path used by the install to a real path;
for tmux, `paths.mdstack` must be `<state-dir>/<owner>__<repo>/mdstack`, the
link bootstrap creates to the bundle. Owner commands take no `--project`
(8.0.0): they read `$MDSTACK_CONFIG` (an absolute path), else
`~/.mdstack/config.toml`, and refuse `--project` with exit 2
([migration guide](../guides/migration.md)):

```bash
mdstack bootstrap --dry-run
mdstack bootstrap
```

Pass `--org-profile <pack>/profile.toml` to both commands if a pack applies.
Review the render diff, target paths and human steps before confirming apply.
In a non-interactive shell, use `--yes` only after reviewing the dry run.
A failed preflight stops the install; follow its hints, use
`mdstack doctor --fix` for
missing state directories, then retry. Never overwrite a tracked, edited or
unowned target to get past a refusal.

Capture the dry-run and apply output. Expect `crew bootstrap: dry-run; no
install written`, then `crew bootstrap: installed <path-to-install.json>`.
Apply records `VERSION`, `install.json`, a profile copy and the `mdstack`
link in the shared state directory. Grok Bot receives the deployed render at
`paths.live_dir`; tmux receives a render preview, with deployment and hooks
left to `mdstack up`. See [bootstrap](../bootstrap.md) for the design and build slices.

Complete Steps 1–5 and the remaining wiring in [Step 6](../runbook-new-repo.md#step-6-state-dir-and-wiring-doc).
`mdstack doctor --fix --milestone M1` creates the crew labels, the milestone
and, where its login can, the Project, and sends the reviewer invitation. The
current core does not automate collaborator acceptance, protection choices or
the end-to-end smoke test: `mdstack bootstrap --smoke` only queues its issue
([first run](../guides/getting-started.md#6-first-issue)). Record every
pending human step from the install manifest. Bootstrap does not start roles:
create Grok Bot routines in [Step 7](../runbook-new-repo.md#step-7-listener-wiring-per-bot), or run
`mdstack up` for [tmux](../runbook-new-repo.md#run-the-crew), then complete Step 8 and the checklist.

## Manual fallback

Use these steps when the installed release lacks bootstrap or bootstrap cannot
run. The same prerequisites, product-safety checks and verification checklist
apply; record the fallback and its reason in `wiring.md`.

Needs Python 3.11+ and a checkout of this repo (`<path-to-this-repo>`); run
the commands from its root; `config.toml` below stands for the path to your
profile file. Usage of both scripts:
[scripts: Profile validator](../../scripts/README.md#profile-validator) and
[Renderer](../../scripts/README.md#renderer).

1. **Write `config.toml`.** Copy [profiles/default.toml](../../profiles/default.toml)
   (GitHub for every concern, Grok Bot runtime) and replace every `<...>`
   value: `repo.owner`, `repo.name`, `repo.default_branch`, the logins in
   `[identities]` from [Identities](../runbook-new-repo.md#identities) (`owners` are the user's own
   logins; `reviewer.gh_user` must differ from the other three), the bot
   display names, `runtime.timezone`, and `[paths]` with the
   [shared state dir](../runbook-new-repo.md#shared-state-dir), the worker worktree root and the
   [toolchain](../runbook-new-repo.md#other-prerequisites) `PATH` entry. Keep the `[engines]` routing
   unless the owner chose otherwise. Every key is in
   [profile.md: Keys](../profile.md#keys).

2. **Validate** the file on its own:

   ```bash
   python3 core/crew-config.py validate config.toml
   ```

   Expect exit 0. Each problem prints as `file:key: reason`. A value still
   written as a placeholder passes validation, so also check
   `grep -n '<' config.toml` prints nothing.

3. **Resolve** the layers (core defaults, the default profile, your file):

   ```bash
   python3 core/crew-config.py resolve --project config.toml
   ```

   Expect `crew-config: OK` and one `key = value  # layer` line per key, with
   no `<...>` value left (a key you deleted falls back to the default profile's
   placeholder). Capture the output: it is the value list for every command
   below. Add `--org-profile <path>` only if an org pack applies
   ([Layers and precedence](../profile.md#layers-and-precedence)).

4. **Render** the role briefs and runtime artifacts:

   ```bash
   python3 core/crew-render.py --project config.toml --out <out-dir>
   ```

   `--inputs` defaults to the real input tree, `templates/` (the Grok Bot
   templates and `backends/github.toml`). Expect `crew-render: OK (<k> files)`
   and the written paths: the Grok Bot routines under `runtime/` (role briefs
   under `briefs/` only once the input tree has `core/`). On any problem it
   prints `file:line: reason` and writes nothing. The parity check
   `python3 dev/tests/core/test-render-parity.py` proves the rendered default profile
   equals the template text
   ([scripts: Renderer](../../scripts/README.md#renderer)).

**Hand-fill fallback.** Without rendered routines (if the renderer cannot
run), copy each template under
`templates/runtimes/grok-bot/` ([templates](../../templates/README.md)) and replace each install-time placeholder with its resolved value from item 3
([templates: Placeholders](../../templates/README.md#placeholders)). Record in
the wiring doc which path was used.
