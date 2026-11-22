#!/usr/bin/env python3
"""Renderer for mdstack: resolved profile + inputs to role briefs and runtime artifacts. Python 3.11+ stdlib only.

Usage: crew-render.py --project FILE [--org-profile FILE] [--inputs DIR] [--diff-paths FILE] --out DIR
Inputs (default: the repo's templates/): core/<role>.md for each role, if core/ exists -> briefs/<role>.md;
runtimes/<runtime>/** of the profile's runtime -> runtime/** (runtime.options.role_runtime swaps one role's
template for runtimes/<other>/<role>.md, #1055); backends/<backend>.toml maps each
<op:concern.operation> to a command, and its [placeholders] kept list declares extra run-time placeholders.
Pack overlay: a render/ directory in the org profile's directory (else paths.pack) is searched per file
before the inputs. runtime.options.notes.render files are appended verbatim to that role's rendered brief.
Core memory (docs/memory.md): each role's rendered brief (a lead's carries its pool role's; on a runtime whose
briefs are per-routine files, the role's discovery file) gets the owner profile and the role's memory file from
memory/ in the checkout (paths.checkout, else the profile's directory), read at the tip of its remote default
branch (repo.default_branch on origin), resolved once per render and never from the local tree (#1537); stderr
names the revision. Before any render note; inside the closing fence when the brief ends in one (a fenced routine
prompt). A memory lint problem or a failed resolve, fetch or read fails closed; a root with no origin remote (or no
git) and no memory/ adds none. The size-budget render (normalize_paths) leaves memory out: its files have their
own limits.
Budget headroom (#1056): after a successful render, stderr gets one line per role brief with its path-normalized
bytes against [size_budget] (the bootstrap measure) and its delivered bytes (core memory and render notes
included), and a WARNING inside BUDGET_BAND of the budget or over it. Output paths and exit codes are unchanged.
Fails closed: every problem (an unknown placeholder, a missing mapping, an unsupported capability) prints as
`file:line: reason`; exit 1 and write nothing if any, else 0.
Placeholder map: scripts/README.md (Renderer).
<merge-grant> keeps none literal; other values render a bounded live-profile lookup, never grant prose.
Enabled builder.precheck appends ordered steps and profile commands to builder briefs.
Flavor placeholders use the project preset/custom knobs; --diff-paths supplies newline-separated
repo-relative paths (both rename paths) for class rigor. Without paths, classes wait for live resolution.
Unset flavor resolves standard and renders its baseline line like an explicit name.
This render baseline supplies no item record or merge authority; explicit precheck settings stay in force.
Grok Bot SKILL.md inputs include the reviewed docs with <include:docs/protocol.md>
or <include:docs/roles.md>. Included docs keep their illustrative placeholders;
relative Markdown links point into the installed bundle, not the skill directory.
Builder and solo session briefs include the PR conventions section from docs/roles.md;
its illustrative placeholders stay literal and its link labels render as plain text.
A template line starting <strategy:merge> or <strategy:rebase> renders, without that prefix, only when the change
backend's resolved strategy.update_from_base (default merge) matches.
A line exactly <control-item:set> or <control-item:none> opens a block, closed by a line exactly <control-item:end>,
that renders, without its marker lines, only when repo.control_item is set (any tracker item) or unset.
A line exactly <session-backend:hosted> or <session-backend:local> opens a block, closed by a line exactly
<session-backend:end>, that renders, without its marker lines, only when runtime.options.session_backend is or is
not "hosted"; it may sit inside a control-item block (#1052).
<op:a.b|c.d> renders the first listed operation the backend supports. A researchers cap of 0 renders no
researcher template, so it needs none of the researcher's operations.
A line exactly <include:policy/DIR/NAME.md> is replaced by templates/policy/DIR/NAME.md (pack overlay first), so
a role's shared policy is authored once; its lines then render like the including file's. Bounded: one level, so
an include line inside a fragment fails closed, as does a missing fragment.
<title:ROLE/PASS> renders the role's post title head, `<emoji> <name> · <Pass>`, from core/post-title.py (#1946).
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("crew_config", os.path.join(HERE, "crew-config.py"))
crew_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crew_config)
_spec = importlib.util.spec_from_file_location("crew_memory", os.path.join(HERE, "crew-memory.py"))
crew_memory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crew_memory)
_spec = importlib.util.spec_from_file_location("post_title", os.path.join(HERE, "post-title.py"))
post_title = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post_title)

ROLES = crew_config.ROLE_REGISTRY
BUDGET_BAND = 0.05  # warn when a role brief is within 5% of its size_budget (#1056)
# Install-time placeholder -> resolved profile keys (docs/profile.md "Replaces"); several keys must agree.
MAPPED = {
    "control-item": ["repo.control_item"], "runtime-id": ["runtime.name", "runtime.instance"],
    "owner": ["repo.owner"], "repo": ["repo.name"], "default-branch": ["repo.default_branch"],
    "author-login": [r["identity_key"] + ".gh_user" for r in ROLES.values() if "identity_independent_of" not in r],
    "reviewer-login": [r["identity_key"] + ".gh_user" for r in ROLES.values() if "identity_independent_of" in r],
    "user-logins": ["identities.owners"],
    "state-dir": ["paths.state_dir"], "worktree-root": ["paths.worktree_root"], "toolchain-bin": ["paths.toolchain_bin"],
    "mirror-deferral": ["runtime.options.mirror_deferral"], "mirror-gate": ["runtime.options.mirror"],
    "max-active-milestones": ["runtime.options.max_active_milestones"],
    "builder-cap": ["runtime.options.builders"], "reviewer-cap": ["runtime.options.reviewers"],
    "present-builder-cap": ["runtime.options.present_builders"],
    "present-reviewer-cap": ["runtime.options.present_reviewers"],
    "session-backend": ["runtime.options.session_backend"],
    "lone-pr-land": ["runtime.options.lone_pr_land"],
    "train-min": ["runtime.options.train_min"], "train-window": ["runtime.options.train_window"],
    "mdstack": ["paths.mdstack"], "merge-grant": ["runtime.options.merge_grant"],
    "merge-grant-scope": ["runtime.options.merge_grant_scope"], "spec-paths": ["spec.paths"],
    "release-delegation": ["runtime.options.release_delegation"],
    "hold-label-blocks": ["runtime.options.hold_label_blocks"], "timezone": ["runtime.timezone"], "fallback-engine": ["engines.fallback_engine"],
    "tested-update": ["strategy.update_from_base"],
    "land-step": ["land.mode"], "land-publish": ["land.opens_draft"], "land-rule": ["land.tests_against_tip"],
    "land-stack": ["land.stack"], "spec-home": ["docs.homes.specs", "docs.specs_external"],
    "local-checks": ["builder.local_checks"], "linkage-check": ["backends.change.name"],
    "fragment-step": ["release.fragments"],
}
for role, metadata in ROLES.items():
    MAPPED[role.title() + "Bot"] = [metadata["identity_key"] + ".name"]
    for field in ("title", "emoji"):
        MAPPED[role.title() + field.title()] = [metadata["identity_key"] + "." + field]
for knob in ("name", "review", "validation", "evidence", "caps", "merge", "builder"):
    MAPPED["flavor-" + knob] = ["flavor." + knob]
MAPPED["flavor-validation-scope"] = ["flavor.validation_scope"]
MAPPED["flavor-selfgate-engine"] = ["flavor.selfgate_engine"]
MAPPED["TeamName"] = ["identities.team"]  # optional; empty when unset (#1329)
# <RoleSignature>: `— <emoji> <name> (<title>) · <team>`, harness and model follow it in the template (#431, #1291);
# <report-status>: the profile's fixed status set (docs/roles.md Report skeleton); <report-merge-status>: its landed and
# blocked statuses, for synthesizer merge posts. All read [report]; no marker changes.
for role, metadata in ROLES.items():
    MAPPED[role.title() + "Signature"] = [metadata["identity_key"] + ".name"]
MAPPED["report-status"] = MAPPED["report-merge-status"] = ["report.emoji"]
# <mirror-gate>: the tmux synthesizer's mirror-gate paragraph by runtime.options.mirror (#877, docs/runtimes/tmux.md).
MIRROR_GATE = {
    "live-copy": "Mirror deferral: read the recorded owner decision named by `mirror_deferral`\n"
                 "   unless `none`; verify scope and ensure covered PRs\n"
                 "   do not change live Grok Bot behaviour. These satisfy the mirror gate even with\n"
                 "   `crew:needs-mirror` and no per-PR comment. Record\n"
                 "   `Mirror deferral used: <mirror-deferral>` in the merge post.\n"
                 "   Uncovered PRs, unreadable decisions or live behaviour changes need a real\n"
                 "   mirror. No merge permission is supplied; gate changes need per-PR owner merge-ok.",
    "none": "Mirror: `mirror = \"none\"` declares no live copy outside the render, so the\n"
            "   mirror gate is `n/a` by profile. Record `Mirror: n/a (profile)` on direct lands\n"
            "   and list no mirror item in gate-status. Never wait on or ask for a mirror or\n"
            "   deferral, and ignore `crew:needs-mirror`. This supplies no approval or merge\n"
            "   permission; every other gate still applies at head.",
}
# <land-step>: the tmux synthesizer's step 3 by the change backend's land.mode; async adds the land.serializes and
# land.tests_against_tip alternatives (#873, docs/interfaces.md#asynchronous-land-design). <land-publish>: the
# builder's publish line under land.opens_draft, else nothing, so every sync render stays byte-identical.
LAND_SYNC = ("If it holds, run `$CREW_BIN land-lock acquire --project \"$CREW_PROJECT\"`\n"
             "   (absolute repo profile, never relative `config.toml`), run `<op:change.land>`, post\n"
             "   `<title:synthesizer/merge>` naming the merge-ok or grant used and its\n"
             "   `Land rule:` line (`<op:markers.write>`), then\n"
             "   `$CREW_BIN land-lock release --project \"$CREW_PROJECT\"`. If the head moved, release\n"
             "   and stop.")
# <land-step> when the change backend maps change.land-delete-arg (#395): the land itself deletes an eligible head
# branch, so close-out needs no separate delete (docs/interfaces.md#change); otherwise the sync text renders unchanged.
LAND_DELETE = [("`<op:change.land>`, post\n   `<title:synthesizer/merge>` naming the merge-ok or grant used and its\n"
                 "   `Land rule:` line",
                 "`<op:change.land>`, add\n   `<op:change.land-delete-arg>` if same-repo, not default/base, post\n"
                 "   `<title:synthesizer/merge>` naming merge-ok or grant used, its `Land rule:`\n"
                 "   line and `Head branch: deleted|retained (<reason>)|delete failed` (exit>0,\n"
                 "   `MERGED`)"),
               ("`<op:change.land>` bound to that head, post `<title:synthesizer/merge>` naming\n"
                "   the merge-ok or grant used and its `Land rule:` line",
                "`<op:change.land>` bound to that head, add `<op:change.land-delete-arg>` if\n"
                "   same-repo, not default/base, post `<title:synthesizer/merge>` naming merge-ok\n"
                "   or grant used, its `Land rule:` line and `Head branch: deleted|retained\n"
                "   (<reason>)|delete failed` (exit>0, `MERGED`)")]
LAND_ASYNC = (
    "If it holds, land asynchronously (`land.mode = \"async\"`, protocol §7).\n"
    "   %s\n"
    "   Run `$CREW_BIN land request --project \"$CREW_PROJECT\" --pr <n> --head <head-sha>`:\n"
    "   it records the intent, sends `<op:change.land>` only when\n"
    "   `<op:change.land-status>` reads `none` at an unmoved head, and polls to the end.\n"
    "   Never run either command yourself. On exit 1 (failed, stale head, timeout or\n"
    "   unknown status) post no `merge` and report its `blocked:` line. On exit 0,\n"
    "   complete the land: (a) post `<title:synthesizer/merge>` naming the merge-ok or\n"
    "   grant used, its `Land rule:` line and the printed `record:` line, with the\n"
    "   printed `marker:` line as its marker (`<op:markers.write>`); (b) whatever\n"
    "   `lone_pr_land` is, check default-branch CI as step 4 does, at the printed landed\n"
    "   revision, reporting red with step 4's `blocked:` line; (c) once CI is green or\n"
    "   red is reported, run\n"
    "   `$CREW_BIN land done --project \"$CREW_PROJECT\" --pr <n> --head <head-sha>`.\n"
    "   %s\n"
    "   On every wake, before step 1, run `$CREW_BIN land resume --project \"$CREW_PROJECT\"`.\n"
    "   It never requests a land again. Complete each landed intent it prints through\n"
    "   (a) to (c) with that intent's PR and head, skipping only (a) when\n"
    "   `<op:markers.read>` already shows `pass=merge` at that PR and head; resume\n"
    "   polling, CI waits included, before any new land.")
LAND_LOCK = {True: "The backend serializes lands (`land.serializes`, C7): take no land lock.",
             False: "First run `$CREW_BIN land-lock acquire --project \"$CREW_PROJECT\"`; hold the\n"
                    "   lock until the terminal status and, on landed, the merge post, then run\n"
                    "   `$CREW_BIN land-lock release --project \"$CREW_PROJECT\"`."}
LAND_TIP = {True: "The backend tests the landed patch on the tip (`land.tests_against_tip`):\n"
                  "   land each ready PR alone through this step, even behind the default branch,\n"
                  "   with `Land rule: alone, backend queue`; never run\n"
                  "   `<op:change.update-from-base>` or a merge train (`mdstack train` refuses).",
            False: "Tested with the default branch must hold at the request, as for a sync land."}
# Session binding (#1351): the session synthesizer's step 3 takes the repo lock by an atomic mkdir, since
# `mdstack land-lock` is tmux-only; sync keeps today's text byte for byte, async runs `mdstack land` the same way.
SESSION_LOCK = ("`mkdir -p \"$CREW_STATE/locks\" && mkdir \"$CREW_STATE/locks/merge.lock.d\"` takes\n"
                "   the repo lock atomically. If it fails, the lock is held: append\n"
                "   `blocked: #<n> land lock held` to `$CREW_STATUS` and stop; never remove a lock\n"
                "   you did not create.")
SESSION_LAND_SYNC = ("Serial land (session C7; `mdstack land-lock` serves tmux profiles only, never run it):\n"
                     "   " + SESSION_LOCK + " Holding it, repeat the step 2 check at the live head, run\n"
                     "   `<op:change.land>` bound to that head, post `<title:synthesizer/merge>` naming\n"
                     "   the merge-ok or grant used and its `Land rule:` line (`<op:markers.write>`), then\n"
                     "   release with `rmdir \"$CREW_STATE/locks/merge.lock.d\"`. If the gate fails or the\n"
                     "   head moved, release and stop.")
SESSION_LAND_ASYNC = (
    "Serial land, asynchronously (`land.mode = \"async\"`, protocol §7; session C7;\n"
    "   `mdstack land-lock` serves tmux profiles only, never run it).\n"
    "   %s\n"
    "   Repeat the step 2 check at the live head; if it fails, release any lock you\n"
    "   hold and stop. Then run\n"
    "   `$CREW_BIN land request --project \"$CREW_PROJECT\" --pr <n> --head <head-sha>`:\n"
    "   it records the intent, fills the backend's change placeholder, sends\n"
    "   `<op:change.land>` only when `<op:change.land-status>` reads `none` at an\n"
    "   unmoved head, maps each status read through the declared `land.status`, and\n"
    "   polls every `land_poll_interval` seconds for at most `land_timeout` seconds.\n"
    "   Never run either command yourself. On exit 1 (failed, stale head, timeout or\n"
    "   unknown status) post no `merge`, release any lock you hold and report its\n"
    "   `blocked:` line. On exit 0, complete the land: (a) post\n"
    "   `<title:synthesizer/merge>` naming the merge-ok or grant used, its `Land rule:`\n"
    "   line and the printed `record:` line, with the printed `marker:` line as its\n"
    "   marker (`<op:markers.write>`); (b) whatever `lone_pr_land` is, check\n"
    "   default-branch CI as step 4 does, at the printed landed revision, reporting\n"
    "   red with step 4's `blocked:` line; (c) once CI is green or red is reported, run\n"
    "   `$CREW_BIN land done --project \"$CREW_PROJECT\" --pr <n> --head <head-sha>`.\n"
    "   %s\n"
    "   At the start of every run, before step 1, run\n"
    "   `$CREW_BIN land resume --project \"$CREW_PROJECT\"`. It never requests a land\n"
    "   again. Complete each landed intent it prints through (a) to (c) with that\n"
    "   intent's PR and head, skipping only (a) when `<op:markers.read>` already shows\n"
    "   `pass=merge` at that PR and head; on exit 1 report its `blocked:` lines and\n"
    "   request no new land in this run.")
SESSION_LAND_LOCK = {True: "The backend serializes lands (`land.serializes`, C7): take no repo lock.",
                     False: SESSION_LOCK + " Hold it until the terminal status and, on landed, the\n"
                            "   merge post, then release with `rmdir \"$CREW_STATE/locks/merge.lock.d\"`."}
# The session Land rule's backend-queue line, appended after its two rules.
SESSION_LAND_RULE = ("\n\nBackend queue (`land.tests_against_tip`): the two rules above do not apply.\n"
                     "Land every ready PR alone through step 3, one per run, even behind the default\n"
                     "branch, recording `Land rule: alone, backend queue`. Never run\n"
                     "`<op:change.update-from-base>` or `mdstack train` (it refuses).")
# <land-stack>: the session synthesizer's stack-land recipe under land.stack (#1605); nothing otherwise, so every
# render without the binding stays byte-identical and keeps one land per run.
SESSION_LAND_STACK = (
    "\n\nStack land (`land.stack`, protocol §7): when two or more ready PRs form one\n"
    "linear `Depends on` stack, land them in one request instead of one per run.\n"
    "%s\n"
    "Check every step 1 and 2 gate (verdict markers, precheck, flavor, merge\n"
    "permission, holds, CI) for every member at that member's own live head. If\n"
    "any member fails one, refuse the whole stack: one held member (`crew:hold`,\n"
    "an open hold-until or stop), one with red, pending or missing CI, one without\n"
    "its passing verdict or merge permission, or one whose head moved means zero\n"
    "requests. Never run `$CREW_BIN land stack` then; release any lock you hold and\n"
    "append `blocked: #<n> stack` naming each failing member and gate to\n"
    "`$CREW_STATUS`. Otherwise run\n"
    "`$CREW_BIN land stack --project \"$CREW_PROJECT\" --stack <n>:<head-sha>,...`\n"
    "with every member, base first. It records the intent, re-reads each member's\n"
    "head and sends `<op:change.land-stack>` once, only when\n"
    "%s reads `none` for every member; never run either\n"
    "yourself. On exit 1 post no `merge`, release any lock and report its\n"
    "`blocked:` line. On exit 0 post one `<title:synthesizer/merge>` per member,\n"
    "naming the merge-ok or grant used, its `Land rule:` line and that member's\n"
    "printed `record:` line, with that member's printed `marker:` line as its\n"
    "marker (`<op:markers.write>`). Check default-branch CI as step 4 does at the\n"
    "last member's landed revision, append one `done:` per member, then run\n"
    "`$CREW_BIN land stack-done --project \"$CREW_PROJECT\" --stack <n>:<head-sha>,...`.\n"
    "%s\n"
    "At the start of every run, before step 1, run\n"
    "`$CREW_BIN land resume --project \"$CREW_PROJECT\"`; it never requests. Complete\n"
    "each landed stack it prints the same way, skipping a member's post when\n"
    "`<op:markers.read>` already shows `pass=merge` at its PR and head; on exit 1\n"
    "report its `blocked:` lines and request no new land in this run.")
SESSION_STACK_LOCK = {True: "The backend serializes lands (`land.serializes`, C7): take no repo lock.",
                      False: "First, " + SESSION_LOCK + " Hold it until the stack's terminal\n"
                             "   status and, on landed, every merge post, then release with\n"
                             "   `rmdir \"$CREW_STATE/locks/merge.lock.d\"`."}
SESSION_STACK_TIP = {
    True: "The backend tests the combined stack on the current tip\n"
          "(`land.stack_tests_against_tip`): the stack may land behind the default branch,\n"
          "and each merge post records `Land rule: stack of <k>, backend combined test`\n"
          "with the check its `record:` line names. Never run `<op:change.update-from-base>`.",
    False: "Tested with the default branch must hold for every member at the request;\n"
           "each merge post records `Land rule: stack of <k>`."}
# <land-rule>: appended to the Land rule section's opening, before its train decision; only
# land.tests_against_tip replaces that decision, so every other render adds nothing.
LAND_RULE = ("\nBackend queue (`land.tests_against_tip`): the rules below and the merge train\n"
             "section do not apply. Land every ready PR alone through step 3, one at a time\n"
             "in `Depends on` then approval order, even behind the default branch, recording\n"
             "`Land rule: alone, backend queue`. Never run `<op:change.update-from-base>` or\n"
             "`mdstack train` (it refuses).")
LAND_PUBLISH = ("\n   The backend opens drafts (`land.opens_draft`): run `<op:change.publish>`\n"
                "   right after opening, and again if the change is still a draft at handoff;\n"
                "   it is harmless twice and supplies no approval, verdict or gate.")
# Builder build-pass steps bound to a GitHub change backend, [release] or builder.local_checks (#1958): a GitHub
# render keeps today's text byte for byte; another backend drops the linkage check and, without [release], the
# fragment step, and names the project's own checks unless builder.local_checks names them.
LOCAL_CHECKS = (
    "Local checks: a build or fix round runs a targeted set before pushing, not\n"
    "   the full suite: `scripts/check-repo.py` and `scripts/check-changelog-pr.py`\n"
    "   always (check-repo's `markdown` check is local markdownlint parity); the\n"
    "   `dev/tests/*/test-*.py` named for each changed script;\n"
    "   `test-crew-render.py`, `test-render-parity.py`, `test-tmux-briefs.py` and\n"
    "   `test-crew-bootstrap.py` when templates or fixtures change;\n"
    "   `test-changelog-cut.py`, `test-check-changelog-pr.py` and\n"
    "   `test-release-*.py` for a release cut. With a forge-less host in the\n"
    "   profile, `$CREW_BIN runner run --head <head-sha> -- check-repo test-*.py...`\n"
    "   may run that set there; it falls back to a local run by itself. A diff\n"
    "   touching shared plumbing (`environments/terminal/crew.d/_shared.py`,\n"
    "   `cli/mdstack`, `core/crew-config.py` or `core/crew-render.py`) runs every\n"
    "   `dev/tests/*/test-*.py` locally, with the parallel runner once it exists. The PR\n"
    "   Testing section lists the set, why it covers the diff, and that PR CI runs\n"
    "   the full suite. Red CI still comes back as a ci-red round; CI is never\n"
    "   waived. A merge-up (a push whose only new commit merges the default branch)\n"
    "   runs `check-repo.py` and only the tests covering the conflicted files (the\n"
    "   test named for a changed script; render and parity tests when templates or\n"
    "   fixtures conflicted); PR CI and the recheck pass cover the rest. The\n"
    "   merge-up note lists the tests run and why that set covers the conflict.")
LOCAL_CHECKS_DECLARED = (
    "Local checks: a build or fix round runs %s before pushing.\n"
    "   The PR Testing section lists them and why they cover the diff. Red CI\n"
    "   still comes back as a ci-red round; CI is never waived.")
LINKAGE_CHECK = (" Cite the newest signed\n   allocation and pass `<mdstack>/scripts/check-pr-linkage.py` before opening\n"
                 "   (`<mdstack>/docs/backends/github.md` Builder linkage check).")
FRAGMENT_STEP = ("\n   Right after opening, before `done:`, set the fragment's `pr:` to the PR\n"
                 "   number, pass `scripts/check-changelog-pr.py --base origin/<default-branch> --pr <pr>`,\n"
                 "   push and post a round-0 `CI fix` note at the new head; review\n"
                 "   waits for it. CI on the opened head may still fail on `TBD`, written\n"
                 "   before the number existed (#1844).")
# Configured check commands named in the reviewer brief; unset renders n/a (#648).
OPTIONAL = {"precheck-lint": "builder.precheck.lint", "precheck-test": "builder.precheck.test"}
MAPPED.update({name: [key] for name, key in OPTIONAL.items()})

# Run-time placeholders (templates/README.md, docs/roles.md): filled per task, kept verbatim.
KEPT = {"n", "sha7", "head-sha", "reviewed-base-sha", "k", "pass", "role", "pass|changes", "cmd", "comment id", "note", "parent",
        "planned | applied | live", "date", "reason", "issue#", "pr", "tier", "engine", "model", "effort",
        "UTC timestamp", "file", "full-40-char-head-sha", "new-head-sha", "gate", "run-id", "worktree",
        "run-url", "harness", "branch", "t", "M", "login", "project", "url", "id", "item", "status-field", "option", "tag",
        "version", "APPROVE|REQUEST_CHANGES", "sweep-id", "outcome", "band", "shadow|apply", "stack",
        "stack-top", "stack-changes", "stack-revisions"}
TOKEN = re.compile(r"<([^<>\s!/=-][^<>\n]*)>")
OP = re.compile(r"op:(.*)\.(.*)")
TITLE = re.compile(r"title:([a-z]+)/([a-z-]+)")
PLACEHOLDER = re.compile(r"[a-z][a-z0-9-]*")
STRATEGY_LINE = re.compile(r"<strategy:(merge|rebase)>")
CONTROL_BLOCK = re.compile(r"<control-item:(set|none|end)>\n?")
BACKEND_BLOCK = re.compile(r"<session-backend:(hosted|local|end)>\n?")
INCLUDE_LINE = re.compile(r"<include:policy/([a-z0-9-]+/[a-z0-9-]+\.md)>\n?")
# Operations that always render the core entry, whatever the backend (docs/interfaces.md#one-entry-point): core runs a
# bound extension itself, so no backend map can replace the core run.
CORE_OPS = {("classify", "sensitive"): "core/crew-config.py sensitive"}
# Roles a profile may leave out: a cap of 0 renders none of their templates or operations (#926).
OPTIONAL_ROLES = [r for r, v in ROLES.items() if v.get("cap_min", 1) == 0]


class Unsupported(ValueError):
    """An operation the backend declares unsupported; <op:a.b|c.d> then tries the next one."""


def pack_overlay(project, org, values):
    """The pack's render/ overlay: beside the org profile, else under paths.pack; None when absent."""
    if org:
        base = os.path.dirname(os.path.abspath(org))
    elif values.get("paths.pack"):
        base = os.path.join(os.path.dirname(os.path.abspath(project)), os.path.expanduser(values["paths.pack"]))
    else:
        return None
    overlay = os.path.join(base, "render")
    return overlay if os.path.isdir(overlay) else None


def resolve(project, org, paths=None):
    """Resolve the layered profile with crew_config.resolve_profile; return ({dotted key: value}, problems)."""
    meta = {}
    merged, _, problems, _ = crew_config.resolve_profile(project, org, meta=meta)
    if problems:
        return None, problems
    flavor = merged["flavor"]
    named = dict(crew_config.FLAVOR_PRESETS)
    for name, knobs in flavor.get("custom", {}).items():
        named[name] = dict(named[knobs["base"]], **{k: v for k, v in knobs.items() if k != "base"})
    name = flavor["name"]
    knobs = dict(named[name])
    if paths is not None:
        try:
            knobs.update(crew_config.class_flavor(merged, paths)["rigor"])
        except ValueError as e:
            return None, ["diff-paths:1: " + str(e)]
        keys = set(crew_config.FLAVOR_ORDER) | {"caps"}
        if any(knobs[k] != named[name][k] for k in keys):
            name = next((n for n, candidate in named.items() if all(knobs[k] == candidate[k] for k in keys)), "mixed")
    values = dict(crew_config.leaves(merged))
    values.update({key: value for key, (value, _) in meta.items() if key.startswith("land.")})
    values.update({"flavor." + k: v for k, v in knobs.items()})
    values["flavor.name"] = name
    values["flavor.selfgate_engine"] = flavor.get("selfgate_engine", "different")  # read only for express changes
    if "team.name" in meta:  # a team file's resolved name, for signatures (#1291)
        values["team.name"] = meta["team.name"][0]
    if "strategy.update_from_base" in meta:  # undeclared: merge (docs/interfaces.md#rebase-update-from-base)
        values["strategy.update_from_base"] = meta["strategy.update_from_base"][0]
    values.setdefault("runtime.options.merge_grant_scope", ["approved"])  # absent keys keep today's scope (§7 spec change)
    values.setdefault("spec.paths", crew_config.SPEC_PATHS)
    if "release" in merged:  # a declared [release] table, even empty, names its fragment directory (#1958)
        values.setdefault("release.fragments", "changes/unreleased")
    return values, []


class Renderer:
    def __init__(self, values, inputs, normalize_paths=False, overlay=None):
        self.values, self.inputs, self.tables = values, inputs, {}
        self.normalize_paths, self.overlay, self.kept = normalize_paths, overlay, set()
        self.template = None  # runtime of the runtimes/<runtime>/ template being rendered, set per job

    def find(self, *parts):
        """An input file: the pack overlay's copy when present, else the inputs' copy."""
        if self.overlay and os.path.isfile(os.path.join(self.overlay, *parts)):
            return os.path.join(self.overlay, *parts)
        return os.path.join(self.inputs, *parts)

    def expand(self, src, lines, problems):
        """(path, line number, text) for a template's lines, each <include:policy/...> line replaced by its fragment."""
        out = []
        for i, text in enumerate(lines, 1):
            include = INCLUDE_LINE.fullmatch(text)
            if not include:
                out.append((src, i, text))
                continue
            path = self.find("policy", *include.group(1).split("/"))
            try:
                with open(path, encoding="utf-8") as f:
                    fragment = f.read().splitlines(keepends=True)
            except (OSError, UnicodeDecodeError) as e:
                problems.append("%s:%d: missing policy fragment %s (%s)" % (src, i, include.group(1), e))
                continue
            for j, line in enumerate(fragment, 1):
                if INCLUDE_LINE.fullmatch(line):
                    problems.append("%s:%d: nested include: a policy fragment cannot include another" % (path, j))
                else:
                    out.append((path, j, line))
        return out

    def table(self, path):
        if path not in self.tables:
            try:
                with open(path, "rb") as f:
                    self.tables[path] = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                self.tables[path] = {}
        return self.tables[path]

    def op(self, concern, op):
        if (concern, op) in CORE_OPS:
            return CORE_OPS[concern, op], set()
        if op not in crew_config.OPERATIONS.get(concern, []) + crew_config.CONDITIONAL_OPERATIONS.get(concern, []):
            raise ValueError("unknown operation %s.%s" % (concern, op))
        backend = self.values["backends.%s.name" % concern]
        manifest = self.table(os.path.join(os.path.dirname(HERE), "connectors", backend, "manifest.toml"))
        cap = self.values.get("backends.%s.capabilities.%s" % (concern, op),
                              manifest.get("capabilities", {}).get(concern, {}).get(op, "unsupported"))
        if cap == "unsupported":
            raise Unsupported("unsupported capability %s.%s (backend %s)" % (concern, op, backend))
        mapping = self.table(self.find("backends", backend + ".toml"))
        cmd = mapping.get(concern, {}).get(op)
        if not isinstance(cmd, str):
            raise ValueError("missing mapping: no command for %s.%s in backends/%s.toml" % (concern, op, backend))
        kept = mapping.get("placeholders", {}).get("kept", [])
        if not isinstance(kept, list) or not all(isinstance(k, str) and PLACEHOLDER.fullmatch(k) for k in kept):
            raise ValueError("invalid placeholders.kept in backends/%s.toml: expected a list of names "
                             "([a-z][a-z0-9-]*)" % backend)
        clash = sorted(set(kept) & set(MAPPED))
        if clash:
            raise ValueError("invalid placeholders.kept in backends/%s.toml: <%s> is an install-time placeholder"
                             % (backend, clash[0]))
        return cmd, set(kept)

    def fill(self, m):
        name = m.group(1)
        if name in ("include:docs/protocol.md", "include:docs/roles.md", "include:docs/roles.md#pr-conventions"):
            source = os.path.join(os.path.dirname(HERE), name[len("include:"):].split("#", 1)[0])
            try:
                with open(source, encoding="utf-8") as f:
                    text = f.read()
                if name == "include:docs/roles.md":  # the bookend rule names the configured specs home (#1725)
                    text = text.replace("milestone in `docs/specs/`", "milestone in " + self.spec_home())
                if name.endswith("#pr-conventions"):
                    text = text.split("## PR conventions\n", 1)[1].split("## Parallelism\n", 1)[0]
                    text = ("## PR conventions\n" + text).rstrip()
                    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
            except (OSError, UnicodeDecodeError) as e:
                raise ValueError("cannot read included doc %s (%s)" % (source, e)) from e
            bundle = "<path>" if self.normalize_paths else self.values["paths.mdstack"].rstrip("/")

            def link(match):
                target = match.group(1)
                if target.startswith(("#", "/")) or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    return match.group(0)
                return "](" + bundle + "/" + os.path.normpath("docs/" + target) + ")"

            return re.sub(r"\]\(([^)\s]+)\)", link, text)
        if OP.fullmatch(name):
            first = None
            for choice in name[3:].split("|"):  # the first operation the backend supports, else the first refusal
                try:
                    cmd, kept = self.op(*OP.fullmatch("op:" + choice).groups())
                    break
                except Unsupported as e:
                    first = first or e
            else:
                raise first
            outer, self.kept = self.kept, kept
            try:
                return self.line(cmd)
            finally:
                self.kept = outer
        title = TITLE.fullmatch(name)
        if title and title.group(1) in ROLES:
            key = ROLES[title.group(1)]["identity_key"]
            return post_title.title(self.values[key + ".name"], title.group(2),
                                    emoji=self.emoji(key + ".emoji", "").strip())
        if name in KEPT or name in self.kept:
            return m.group(0)
        if name in OPTIONAL:
            command = str(self.values.get(OPTIONAL[name], "")).strip()
            return "`%s`" % (command or "n/a")
        if name not in MAPPED:
            raise ValueError("unknown placeholder <%s>" % name)
        if name == "control-item":
            return str(self.values.get("repo.control_item", "none"))
        if name == "spec-home":
            return self.spec_home()
        if name == "tested-update":  # undeclared: merge (docs/interfaces.md#rebase-update-from-base)
            return ("rebase onto the default branch and upload (no trains)"
                    if self.values.get("strategy.update_from_base") == "rebase" else "update-branch or green train")
        if name == "mirror-gate":
            return self.line(MIRROR_GATE[self.values.get("runtime.options.mirror", "live-copy")])
        if name == "land-step":
            session = self.session_template()
            if self.values.get("land.mode", "sync") == "sync":
                text = SESSION_LAND_SYNC if session else LAND_SYNC
                try:
                    self.op("change", "land-delete-arg")
                    for old, new in LAND_DELETE:
                        text = text.replace(old, new)
                except ValueError:  # unsupported or unmapped: the land keeps the branch for close-out
                    pass
                return self.line(text)
            lock = (SESSION_LAND_LOCK if session else LAND_LOCK)[bool(self.values.get("land.serializes"))]
            text = SESSION_LAND_ASYNC if session else LAND_ASYNC
            return self.line(text % (lock, LAND_TIP[bool(self.values.get("land.tests_against_tip"))]))
        if name == "land-rule":
            if not self.values.get("land.tests_against_tip"):
                return ""
            return self.line(SESSION_LAND_RULE if self.session_template() else LAND_RULE)
        if name == "land-stack":
            if not (self.values.get("land.stack") and self.session_template()):
                return ""
            lock = SESSION_STACK_LOCK[bool(self.values.get("land.serializes"))].replace("\n   ", "\n")
            readback = ("each member's `<op:change.land-status>`" if self.values.get("land.stack_status") == "per-change"
                        else "`<op:change.stack-status>`")  # per-change readback (#1722)
            return self.line(SESSION_LAND_STACK % (lock, readback,
                                                   SESSION_STACK_TIP[bool(self.values.get("land.stack_tests_against_tip"))]))
        if name == "land-publish":
            return self.line(LAND_PUBLISH) if self.values.get("land.opens_draft") else ""
        github = self.values.get("backends.change.name") == "github"
        if name == "local-checks":
            declared = str(self.values.get("builder.local_checks", "")).strip()
            if not declared and github:
                return self.line(LOCAL_CHECKS)
            return LOCAL_CHECKS_DECLARED % (declared or "the project's own checks from its `AGENTS.md`")
        if name == "linkage-check":
            return self.line(LINKAGE_CHECK) if github else ""
        if name == "fragment-step":
            return self.line(FRAGMENT_STEP) if github or "release.fragments" in self.values else ""
        if name == "TeamName":
            return str(self.values.get("identities.team", ""))
        if name == "report-status":
            return ", ".join(self.emoji("report.status." + k, mark) + k
                             for k, mark in crew_config.REPORT_STATUS.items())
        if name == "report-merge-status":
            return " or ".join(self.emoji("report.status." + k, crew_config.REPORT_STATUS[k]) + k
                               for k in ("landed", "blocked"))
        if name.endswith("Signature") and name[:-len("Signature")].lower() in ROLES:
            key = ROLES[name[:-len("Signature")].lower()]["identity_key"]
            team = self.values.get("team.name") or self.values.get("identities.team")
            return "— %s%s (%s)%s" % (self.emoji(key + ".emoji", ""), self.values[key + ".name"],
                                      self.values[key + ".title"], " · " + team if team else "")
        if name.endswith("Emoji") and self.values.get("report.emoji") is False:
            return ""
        if name == "runtime-id":
            return self.values["runtime.name"] + "@" + self.values.get("runtime.instance", "unconfigured")
        keys = MAPPED[name]
        missing = [k for k in keys if k not in self.values]
        if missing:
            raise ValueError("missing mapping: <%s> needs %s, not set in the resolved profile" % (name, missing[0]))
        if len({json.dumps(self.values[k]) for k in keys}) > 1:
            raise ValueError("missing mapping: <%s> is ambiguous (%s differ)" % (name, ", ".join(keys)))
        if self.normalize_paths and all(k.startswith("paths.") for k in keys):
            return "<path>"
        value = self.values[keys[0]]
        if name == "merge-grant" and value != "none":
            return ('Standing-grant candidate: resolve `runtime.options.merge_grant` live with '
                    '`<mdstack>/core/crew-config.py resolve --project "$CREW_PROJECT"` '
                    'with `--org-profile` when configured and the selected team/repo context; '
                    'Before use, read named decisions on the configured tool of record; verify authorized attribution, '
                    'matching project, exact scope, exclusions and later applicable revocations. '
                    'Copied archives, narrative summaries, unrecognized locators, foreign/mismatched records '
                    'and unreadable profiles or sources supply no standing permission. '
                    'Valid per-PR owner merge-ok remains the fallback.').replace(
                        "<mdstack>", "<path>" if self.normalize_paths else self.values["paths.mdstack"])
        if name in ("flavor-caps", "merge-grant-scope", "spec-paths"):
            return json.dumps(value)
        if isinstance(value, bool):
            return json.dumps(value)
        return '", "'.join(value) if isinstance(value, list) else str(value)

    def line(self, text):
        return TOKEN.sub(self.fill, text)

    def spec_home(self):
        """The specs home the bookend rule names: [docs] specs_external, else homes.specs, else docs/specs/ (#1725)."""
        if self.values.get("docs.specs_external"):
            return "the external spec home `%s`" % self.values["docs.specs_external"]
        return "`%s/`" % self.values.get("docs.homes.specs", "docs/specs/").rstrip("/")

    def emoji(self, key, fallback):
        """The profile emoji at key (else fallback) plus a space; nothing with report.emoji = false (#431)."""
        mark = "" if self.values.get("report.emoji") is False else self.values.get(key, fallback)
        return mark + " " if mark else ""

    def session_template(self):
        """True while rendering a session runtime template, whatever the profile's runtime (role_runtime, #1055)."""
        return (self.template or self.values.get("runtime.name")) == "session"

    def precheck(self):
        if not self.values.get("builder.precheck.enabled", False):
            return ""
        attempts = self.values.get("builder.precheck.max_fix_attempts", 2)
        commands = {step: self.values.get("builder.precheck." + step, "").strip()
                    for step in ("lint", "test", "docs")}
        lines = ["\n## Builder pre-review check\n\n",
                 "Before handoff, follow protocol.md's builder pre-review check in order:\n\n",
                 "1. Fresh base: fetch and rebase the unpublished branch; %s for an existing PR.\n"
                 % ("rebase onto `%s` and upload" % self.values["repo.default_branch"]
                    if self.values.get("strategy.update_from_base") == "rebase" else "use merge-up"),
                 "2. Lint / format.\n"]
        for number, step, label in ((2, "lint", "Lint / format"), (3, "test", "Tests / build")):
            if number == 3:
                lines.append("3. Tests / build: gather typed runtime evidence.\n")
                if self.values.get("builder.precheck.owners", "").strip():
                    lines.append("   Pipe the changed paths, one per line, to `core/crew-config.py precheck-scope "
                                 "--project <file>` and append its `targets` to the test command. Exit 3 (unowned "
                                 "code) or 4 (owners query failed) stops the check; `tests=n/a` only when every "
                                 "path is no-owner-ok or removed, and list the `no_owner_ok` paths beside the marker. "
                                 "Pipe every changed path, both rename paths included, from the worktree at head: "
                                 "a path absent there is `removed`, with no owners query and no targets.\n")
            lines.append("\n```sh\n%s\n```\n\n" % commands[step] if commands[step] else
                         "\n%s: `n/a` (no configured command).\n\n" % label)
        lines += ["4. Self-review against the acceptance criteria and repo rules.\n",
                  "5. Docs / changelog: update required docs and the changelog.\n",
                  "\n```sh\n%s\n```\n\n" % commands["docs"] if commands["docs"] else
                  "\nDocs command: `n/a` (no configured command).\n\n",
                  "6. Confirm required evidence and inline excerpts.\n",
                  "7. Open the non-draft PR with per-step results and `pass=precheck` at the final full head SHA.\n\n",
                  "Allow at most %d fix attempts per failing command, rerunning after each.\n" % attempts,
                  "Stop and report a base conflict or remaining failure; never loosen tests, lint or checks.\n",
                  "Rerun affected checks if self-review or docs changes the diff. Missing commands are `n/a`,\n",
                  "never `pass`; report build separately as `n/a` if no build command applies.\n",
                  "Publish step results and command output, never self-review reasoning.\n"]
        return "".join(lines)


def memory_root(project, values):
    """The checkout holding memory/: paths.checkout (relative to the profile's directory), else that directory."""
    base = os.path.dirname(os.path.abspath(project))
    path = values.get("paths.checkout")
    return os.path.abspath(os.path.join(base, os.path.expanduser(path))) if path else base


def render(args, paths, normalize_paths):
    """Render every job in memory: (values, dst -> text, problems); main writes files only when problems is empty."""
    values, problems = resolve(args.project, args.org_profile, paths)
    jobs, overlay = [], None
    if values is not None:
        overlay = pack_overlay(args.project, args.org_profile, values)
        roots = [args.inputs] + ([overlay] if overlay else [])
        if any(os.path.isdir(os.path.join(root, "core")) for root in roots):
            jobs = [("core/%s.md" % r, os.path.join("briefs", r + ".md"), r) for r in ROLES]
        rt = os.path.join("runtimes", values["runtime.name"])
        if not any(os.path.isdir(os.path.join(root, rt)) for root in roots):
            problems.append("%s:1: missing mapping: no runtime binding for %s"
                            % (os.path.join(args.inputs, rt), values["runtime.name"]))
        found = set()
        for root in roots:
            for parent, dirs, names in os.walk(os.path.join(root, rt)):
                found |= {os.path.relpath(os.path.join(parent, n), os.path.join(root, rt)) for n in names}
        idle = [r for r in OPTIONAL_ROLES if values.get(ROLES[r]["cap_key"]) == 0]
        unused = {os.path.relpath(t, "templates")
                  for r in idle for t in ROLES[r]["templates"].get(values["runtime.name"], [])}
        if values["runtime.name"] == "session":  # unregistered binding: an idle role's <role>.md brief (#1404)
            unused |= {os.path.join(rt, r + ".md") for r in idle}
        moved = []  # runtime.options.role_runtime: the role's own template swapped for <runtime>/<role>.md (#1055)
        for r in ROLES:
            other = values.get("runtime.options.role_runtime." + r)
            if other is None or r in idle:
                continue
            own = ROLES[r]["templates"].get(values["runtime.name"], [])
            src = os.path.join("runtimes", other, r + ".md")
            if not own:
                problems.append("%s:1: runtime.options.role_runtime.%s: role %s declares no %s template to replace"
                                % (args.project, r, r, values["runtime.name"]))
            elif not any(os.path.isfile(os.path.join(root, src)) for root in roots):
                problems.append("%s:1: missing mapping: no %s template for role %s"
                                % (os.path.join(args.inputs, src), other, r))
            else:
                unused |= {os.path.relpath(t, "templates") for t in own}
                moved.append((src, os.path.join("runtime", r + ".md"), None))
        jobs = [job for job in jobs if job[2] not in idle]
        jobs += [(os.path.join(rt, rel), os.path.join("runtime", rel), None)
                 for rel in sorted(found, key=lambda rel: [(1, d) for d in rel.split(os.sep)[:-1]] + [(0, rel)])
                 if os.path.join(rt, rel) not in unused] + moved
    renderer, rendered, snap = Renderer(values, args.inputs, normalize_paths, overlay), {}, None
    for rel, dst, role in jobs:
        src = renderer.find(rel)
        parts = rel.split(os.sep)
        renderer.template = parts[1] if parts[0] == "runtimes" and len(parts) > 2 else None
        try:
            with open(src, encoding="utf-8") as f:
                lines = f.read().splitlines(keepends=True)
        except (OSError, UnicodeDecodeError) as e:
            problems.append("%s:1: missing mapping: no brief for role %s (%s)" % (src, role, e) if role else
                            "%s:1: cannot read (%s)" % (src, e))
            continue
        out, strategy, keep, backend_keep = [], values.get("strategy.update_from_base", "merge"), True, True
        hosted = values.get("runtime.options.session_backend") == "hosted"
        for where, i, text in renderer.expand(src, lines, problems):
            block = CONTROL_BLOCK.fullmatch(text)
            if block:
                keep = block.group(1) == "end" or (block.group(1) == "set") == ("repo.control_item" in values)
                continue
            block = BACKEND_BLOCK.fullmatch(text)
            if block:
                backend_keep = block.group(1) == "end" or (block.group(1) == "hosted") == hosted
                continue
            if not (keep and backend_keep):
                continue
            only = STRATEGY_LINE.match(text)
            if only and only.group(1) != strategy:
                continue
            text = text[only.end():] if only else text
            try:
                out.append(renderer.line(text))
            except ValueError as e:
                problems.append("%s:%d: %s" % (where, i, e))
        if role == "builder" or dst in ("runtime/builder.md", "runtime/builder-b1.md", "runtime/solo.md"):
            precheck = renderer.precheck()
            if dst == "runtime/builder-b1.md" and precheck:
                prompt, closing = "".join(out).rsplit("\n```", 1)
                out = [prompt, precheck.replace("```", "~~~"), "\n```", closing]
            else:
                out.append(precheck)
        note_role = os.path.splitext(os.path.basename(dst))[0]
        memory_role = note_role.removesuffix("-lead") if note_role in crew_config.NOTE_ROLES else next(
            (r for r, d in ROLES.items() if d.get("discovery", {}).get(values["runtime.name"]) == note_role), None)
        if memory_role and not normalize_paths and dst in ("briefs/%s.md" % note_role, "runtime/%s.md" % note_role):
            root = memory_root(args.project, values)
            if snap is None:  # one remote-default revision per render, shared by every role output (#1537)
                snap = crew_memory.snapshot(root, values.get("repo.default_branch", "main"))
                if snap[1]:
                    print("crew-render: core memory from %s (%s)" % (snap[1], root), file=sys.stderr)
            memory, issues = crew_memory.section(snap[0], memory_role)
            problems += [m for m in ("%s:%d: [%s] %s" % (os.path.join(root, rel), n, rule, why)
                                     for rel, n, rule, why in snap[2] + issues) if m not in problems]  # once each
            body, fence, tail = "".join(out).rpartition("\n```")
            out = [body, memory.replace("```", "~~~"), fence, tail] if fence and not tail.strip() else out + [memory]
        if dst in ("briefs/%s.md" % note_role, "runtime/%s.md" % note_role):
            for path in values.get("runtime.options.notes.render." + note_role, []):
                note = os.path.join(os.path.dirname(os.path.abspath(args.project)), os.path.expanduser(path))
                try:
                    with open(note, encoding="utf-8") as f:
                        out.append("\n## Render note: %s\n\n%s" % (path, f.read()))
                except (OSError, UnicodeDecodeError) as e:
                    problems.append("%s:1: cannot read runtime.options.notes.render.%s file (%s)" % (note, note_role, e))
        rendered[dst] = "".join(out)
    briefs = {os.path.splitext(dst)[0].split("/", 1)[1] for _, dst, _ in jobs if dst.count("/") == 1}
    for note_role in crew_config.NOTE_ROLES if values is not None else []:
        if values.get("runtime.options.notes.render." + note_role) and note_role not in briefs:
            problems.append("%s:1: runtime.options.notes.render.%s: runtime %s renders no %s brief (note dropped)"
                            % (args.project, note_role, values["runtime.name"], note_role))
    return values, rendered, problems


def budget_report(args, paths, values, delivered):
    """Print each role brief's size_budget headroom to stderr; never changes the exit code."""
    _, budgeted, problems = render(args, paths, normalize_paths=True)
    for dst in [] if problems else sorted(budgeted):
        role = os.path.splitext(os.path.basename(dst))[0].split("-")[0]
        if not dst.endswith(".md") or role not in ROLES:
            continue
        size, budget = len(budgeted[dst].encode("utf-8")), values["size_budget." + role]
        print("crew-render: budget %s %d/%d bytes (%d%%), delivered %d bytes" % (
            dst, size, budget, 100 * size // budget, len(delivered[dst].encode("utf-8"))), file=sys.stderr)
        if size > budget:
            print("crew-render: WARNING %s is %d bytes over the %s size_budget" % (dst, size - budget, role),
                  file=sys.stderr)
        elif size >= budget * (1 - BUDGET_BAND):
            print("crew-render: WARNING %s is within %d%% of the %s size_budget (%d bytes left)" % (
                dst, round(BUDGET_BAND * 100), role, budget - size), file=sys.stderr)


def main(argv=None, normalize_paths=False):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--org-profile")
    ap.add_argument("--inputs", default=os.path.join(os.path.dirname(HERE), "templates"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--diff-paths", help="file of repo-relative diff paths, including both rename paths")
    args = ap.parse_args(argv)
    paths = None
    if args.diff_paths:
        try:
            with open(args.diff_paths, encoding="utf-8") as f:
                paths = f.read().splitlines()
        except (OSError, UnicodeDecodeError) as e:
            print("%s:1: cannot read diff paths (%s)" % (args.diff_paths, e))
            return 1
    values, rendered, problems = render(args, paths, normalize_paths)
    for p in problems:
        print(p)
    if problems:
        print("crew-render: FAILED (%d problem%s)" % (len(problems), "" if len(problems) == 1 else "s"), file=sys.stderr)
        return 1
    for dst, text in rendered.items():
        path = os.path.join(args.out, dst)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(path)
    print("crew-render: OK (%d files)" % len(rendered), file=sys.stderr)
    if not normalize_paths:
        budget_report(args, paths, values, rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
