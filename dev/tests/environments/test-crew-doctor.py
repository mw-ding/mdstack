"""Tests for mdstack doctor (#190) on a fake host; fixtures in crew_testlib.py (stdlib only).

Covers: only fake tools on `PATH` and a fake home with Claude Code and Codex configs; a ready host passes (a missing
tier-order engine warns), a missing tool or coordinator engine fails, one working engine fails diversity, a missing
state dir fails read-only and `--fix` creates it idempotently, human steps (a `gh` login, an untrusted Codex hook,
Claude Code folder trust) are listed with exit 0 and never fixed, trust on a parent counts, role-window trust is checked
on a paths.checkout outside the project directory (#408), a placeholder path fails
without touching state, grok-bot skips the tmux checks, a profile problem exits 1, and the installed version against the
latest release (latest, behind, unreadable, no VERSION), and the handoff rows (no control item warns; this runtime owns,
another owns, draining, in transit and no record; an unreadable control item fails; a native string id is shown as
written and read through the same read-item binding as the guard, #937), and the grok-bot triage row
(off is ok; triage.enabled warns that no Grok timer is installed; no row on tmux), the pack row (the install's
recorded pack name and version; no row without one), the install source row (a recorded non-github transport; no row
without one), no latest-release query under a non-github source, the checkout row (a clone of another repo fails,
no or a path origin warns, https and ssh URLs of [repo] pass), the install and mdstack link rows (#1323; a sibling repo's link fails only once it is installed, #1344),
and when gh
is needed: a github-bound concern or the github release source (#1123), and the sandbox row (#1544). Run in CI.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW, SCRIPTS, write_pack

HOOK_KEY = "%s:session_start:0:0"


def read(path):
    with open(path) as f:
        return f.read()


class DoctorBase(Base):
    def setUp(self):
        super().setUp()
        self.bindir = os.path.join(self.tmp, "bin")
        self.home = os.path.join(self.tmp, "home")
        self.codex = os.path.join(self.home, ".codex")
        os.makedirs(self.codex)
        self.env["PATH"] = self.bindir  # nothing from the real host
        self.env["HOME"] = self.home
        for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
            self.env.pop(var, None)
        for tool in ("git", "claude", "codex"):
            self.tool(tool)
        self.gh(["acme-bot", "acme-reviewer"], "v2.1.0")
        self.trust_claude()
        self.hooks(trusted=True)
        for d in ("claims", "inbox", "status", "wake", "locks"):
            os.makedirs(os.path.join(self.state, d))
        open(os.path.join(self.state, "locks", "merge.lock"), "w").close()

    def tool(self, name, body="echo 1.0"):
        path = os.path.join(self.bindir, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n%s\n" % body)
        os.chmod(path, 0o755)

    def gh(self, logins, latest, labels=None):
        lines = "".join("echo '  ✓ Logged in to github.com account %s (keyring)'\n" % u for u in logins)
        labels = labels if labels is not None else [{"name": n, "color": c, "description": d} for n, c, d in
                  re.findall(r"^(crew:[^|]+)\|([^|]+)\|(.+)$", read(os.path.join(os.path.dirname(CREW), "..", "docs", "runbooks", "github-tracking.md")), re.M)]
        self.tool("gh", 'case "$1 $2" in\n"auth status") echo github.com\n%s;;\n"auth token") echo fixture-token;;\n"release view") echo %s;;\n'
                  '"api repos/acme/widgets/labels?per_page=100") echo \'%s\';;\n'
                  '"label create") echo "$*" >> "$HOME/gh-label.log";;\n'
                  '"api repos/acme/widgets/collaborators/acme-reviewer/permission") echo \'{"permission":"write"}\';;\n'
                  '"api repos/acme/widgets/milestones?state=all&per_page=100") echo \'[[{"title":"M1","state":"open"}]]\';;\n'
                  '"project list") echo \'{"totalCount":1,"projects":[{"id":"P1","number":1,"title":"widgets crew board","closed":false}]}\';;\n'
                  '"api graphql") echo \'{"data":{"repository":{"projectsV2":{"nodes":[{"id":"P1"}],"pageInfo":{"hasNextPage":false}}}}}\';;\n'
                  '"project field-list") echo \'{"fields":[{"id":"F1","name":"Status","options":[{"name":"Todo"},{"name":"In Progress"},{"name":"In Review"},{"name":"Done"}]}]}\';;\n'
                  '"api --paginate") exec /bin/cat "$FAKE_COMMENTS";;\n'
                  "*) exit 1;;\nesac" % (lines, latest, json.dumps([labels])))

    def trust_claude(self, accepted=True):
        with open(os.path.join(self.home, ".claude.json"), "w") as f:
            json.dump({"projects": {os.path.realpath(self.project_dir): {"hasTrustDialogAccepted": accepted}}}, f)

    def hooks(self, trusted):
        path = os.path.join(self.codex, "hooks.json")
        with open(path, "w") as f:
            json.dump({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "x"}]}]}}, f)
        with open(os.path.join(self.codex, "config.toml"), "w") as f:
            f.write('[hooks.state."%s"]\ntrusted_hash = "sha256:00"\n' % (HOOK_KEY % path) if trusted else "")

    def doctor(self, *args):
        return self.crew("doctor", "--project", self.project, *args)

    def rows(self, r):
        """{check: status} from the report lines: status, check name (18 wide), detail and hint."""
        return {line[6:24].strip(): line[:5].strip() for line in r.stdout.split("\n\n")[0].splitlines()}

    def detail(self, r, check):
        return [line[25:] for line in r.stdout.splitlines() if line[6:24].strip() == check][0]

    def humans(self, r):
        return r.stdout.split("Steps only a person can take:\n")[1].splitlines() if "Steps only" in r.stdout else []



class Doctor(DoctorBase):
    def test_claude_copy_trust_is_separate_and_never_written(self):
        config = os.path.join(self.home, ".claude.json")
        before = read(config)
        for args in ((), ("--fix",)):
            r = self.doctor(*args)
            self.assertEqual(self.rows(r)["claude copy trust"], "human", r.stdout)
            self.assertIn("mkdir -p", "\n".join(self.humans(r)))
            self.assertIn("once per host", "\n".join(self.humans(r)))
        self.assertEqual(read(config), before)
        root = os.path.join(self.tmp, "state", "wt")
        data = json.loads(before)
        data["projects"][os.path.realpath(root)] = {"hasTrustDialogAccepted": True}
        with open(config, "w") as f:
            json.dump(data, f)
        self.assertEqual(self.rows(self.doctor())["claude copy trust"], "ok")

    def test_ready_host_passes(self):
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.rows(r)
        for check in ("python", "git", "gh", "tmux", "gh acme-bot", "gh acme-reviewer", "engine claude-code",
                      "engine codex", "codex hooks", "claude trust", "state dir"):
            self.assertEqual(rows[check], "ok", r.stdout)
        self.assertEqual(rows["engine opencode"], "warn")  # a tier-order engine the order falls through
        self.assertEqual(rows["version"], "warn")  # a checkout has no VERSION
        self.assertNotIn("fail", rows.values())
        self.assertEqual(len(self.humans(r)), 2)  # branch protection stays human

    def test_recorded_pack_version_row(self):
        manifest = os.path.join(self.state, "install.json")
        with open(manifest, "w") as f:
            json.dump({"tag": "v2.1.0"}, f)
        self.assertNotIn("pack", self.rows(self.doctor()))
        with open(manifest, "w") as f:
            json.dump({"tag": "v2.1.0", "pack": {"name": "acme", "version": "0.5.0"}}, f)
        r = self.doctor()
        self.assertEqual(self.rows(r)["pack"], "ok", r.stdout)
        self.assertEqual(self.detail(r, "pack"), "acme 0.5.0")

    def test_recorded_install_source_row(self):
        manifest = os.path.join(self.state, "install.json")
        with open(manifest, "w") as f:
            json.dump({"tag": "v2.1.0", "bundle_sha256": "ab" * 32}, f)
        self.assertNotIn("install source", self.rows(self.doctor()))
        with open(manifest, "w") as f:
            json.dump({"tag": "v2.1.0", "bundle_sha256": "ab" * 32, "transport": {
                "kind": "mirror", "location": "/srv/releases", "sha256sums_sha256": "cd" * 32, "pinned": True}}, f)
        r = self.doctor()
        self.assertEqual(self.rows(r)["install source"], "ok", r.stdout)
        self.assertEqual(self.detail(r, "install source"),
                         "mirror /srv/releases; bundle sha256 %s; SHA256SUMS pinned" % ("ab" * 32))

    def test_missing_tool_fails(self):
        os.remove(os.path.join(self.bindir, "tmux"))
        r = self.doctor()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.rows(r)["tmux"], "fail")
        self.assertEqual(self.detail(r, "tmux"), "not on PATH; install tmux")

    def test_missing_coordinator_engine_fails_and_one_engine_breaks_diversity(self):
        os.remove(os.path.join(self.bindir, "claude"))
        r = self.doctor()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.rows(r)["engine claude-code"], "fail")
        self.assertEqual(self.detail(r, "engine claude-code"),
                         "claude --version exit 127; install it, or drop it from [engines]")
        self.assertEqual(self.rows(r)["engine diversity"], "fail")

    def test_missing_state_dir_is_read_only_until_fix(self):
        for name in ("inbox", "wake"):
            os.rmdir(os.path.join(self.state, name))
        os.remove(os.path.join(self.state, "locks", "merge.lock"))
        r = self.doctor()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.detail(r, "state dir"),
                         "missing locks/merge.lock, inbox/, wake/ in %s; mdstack doctor --fix creates them" % self.state)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox")))
        r = self.doctor("--fix")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stderr, "mdstack: config %s\n" % self.project)  # a writing command names its config (#1324)
        self.assertEqual(self.rows(r)["state dir"], "ok")
        self.assertEqual(self.detail(r, "state dir"), "created locks/merge.lock, inbox/, wake/ in " + self.state)
        self.assertTrue(os.path.isfile(os.path.join(self.state, "locks", "merge.lock")))
        self.assertTrue(os.path.isdir(os.path.join(self.state, "wake")))
        r = self.doctor("--fix")  # idempotent
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.rows(r)["state dir"], self.detail(r, "state dir")), ("ok", self.state))

    def test_dry_run_does_not_create_local_state(self):
        os.rmdir(os.path.join(self.state, "inbox"))
        r = self.doctor("--fix", "--dry-run")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox")))

    def test_merged_profile_directory_is_the_default_and_passes(self):  # #1316 AC3, AC7
        root = os.path.join(self.home, ".mdstack")
        os.makedirs(root)
        with open(self.project) as f:
            text = f.read().replace('state_dir = "%s"\nworktree_root = "%s/wt"\n' % ((os.path.join(self.tmp, "state"),) * 2),
                                    'root = "~/.mdstack"\nstate_dir = "state"\nworktree_root = "runs/widgets"\n'
                                    'live_dir = "live"\n')
        with open(os.path.join(root, "config.toml"), "w") as f:
            f.write(text)
        for d in ("runs/widgets", "live"):
            os.makedirs(os.path.join(root, d))
        shutil.copytree(os.path.join(self.tmp, "state"), os.path.join(root, "state"))
        r = self.crew("doctor")  # no --project: the user-level ~/.mdstack/config.toml
        rows = self.rows(r)
        self.assertEqual(rows["state dir"], "ok", r.stdout)
        self.assertEqual(self.detail(r, "state dir"), os.path.join(root, "state", "acme__widgets"))
        self.assertNotIn("paths", rows)

    def test_state_or_worktree_root_inside_a_git_checkout_fails(self):  # #1316 AC3
        os.remove(os.path.join(self.bindir, "git"))
        os.symlink(shutil.which("git", path=os.environ["PATH"]), os.path.join(self.bindir, "git"))
        checkout = os.path.join(self.tmp, "checkout")
        subprocess.run(["git", "init", "-q", checkout], check=True)
        with open(self.project) as f:
            text = f.read().replace('worktree_root = "%s/wt"' % os.path.join(self.tmp, "state"),
                                    'worktree_root = "%s/runs"' % checkout)
        with open(self.project, "w") as f:
            f.write(text)
        r = self.doctor()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.rows(r)["paths"], "fail")
        self.assertIn("paths.worktree_root is inside the git checkout %s" % os.path.realpath(checkout), r.stdout)
        self.assertNotIn("paths.state_dir", r.stdout)
        self.assertNotIn("state dir", self.rows(r))

    def real_git(self):
        os.remove(os.path.join(self.bindir, "git"))
        os.symlink(shutil.which("git", path=os.environ["PATH"]), os.path.join(self.bindir, "git"))

    def test_checkout_of_another_repo_fails(self):  # #1323
        self.real_git()
        subprocess.run(["git", "init", "-q", self.project_dir], check=True)
        r = self.doctor()
        self.assertEqual(self.rows(r)["checkout"], "warn", r.stdout)
        self.assertEqual(self.detail(r, "checkout"),
                         "%s has no forge origin URL; set paths.checkout to a clone of acme/widgets" % self.project_dir)
        git = ["git", "-C", self.project_dir, "remote"]
        subprocess.run(git + ["add", "origin", "https://github.com/other/widgets.git"], check=True)
        r = self.doctor()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.detail(r, "checkout"), "%s is a clone of other/widgets, not acme/widgets; set "
                         "paths.checkout to a clone of acme/widgets, or clone acme/widgets there" % self.project_dir)
        subprocess.run(git + ["set-url", "origin", os.path.join(self.tmp, "other", "widgets.git")], check=True)
        r = self.doctor()  # a path origin names no forge repo: warn, never fail
        self.assertEqual((r.returncode, self.rows(r)["checkout"]), (0, "warn"), r.stdout)
        for url in ("https://github.com/acme/widgets.git", "git@github.com:Acme/widgets", "ssh://git@ghe.example:22/acme/widgets/"):
            subprocess.run(git + ["set-url", "origin", url], check=True)
            r = self.doctor()
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(self.rows(r)["checkout"], "ok", r.stdout)

    def test_install_record_and_mdstack_link(self):  # #1323
        link = os.path.join(self.state, "mdstack")
        with open(self.project, "a") as f:
            f.write('mdstack = "%s"\n' % link)
        r = self.doctor()  # before bootstrap: both only warn, as bootstrap runs doctor first
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((self.rows(r)["install"], self.rows(r)["mdstack link"]), ("warn", "warn"), r.stdout)
        self.assertEqual(self.detail(r, "install"), "no install.json in %s; run mdstack bootstrap" % self.state)
        with open(os.path.join(self.state, "install.json"), "w") as f:
            json.dump({"tag": "v2.1.0"}, f)
        r = self.doctor()  # a recorded install without its link
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.rows(r)["install"], "ok", r.stdout)
        self.assertEqual(self.detail(r, "mdstack link"), "paths.mdstack %s is missing; run mdstack bootstrap, "
                         "which links the installed release there" % link)
        os.makedirs(link)
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.rows(r)["mdstack link"], "ok", r.stdout)
        # A team's shared paths.mdstack naming a sibling repo's link fails only once that repo is installed (#1344).
        sibling = os.path.join(os.path.dirname(self.state), "acme__gadgets", "mdstack")
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('mdstack = "%s"' % link, 'mdstack = "%s"' % sibling))
        r = self.doctor()
        self.assertEqual((r.returncode, self.rows(r)["mdstack link"]), (0, "warn"), r.stdout)
        os.makedirs(os.path.dirname(sibling))
        with open(os.path.join(os.path.dirname(sibling), "install.json"), "w") as f:
            json.dump({"tag": "v2.1.0"}, f)
        r = self.doctor()
        self.assertEqual((r.returncode, self.rows(r)["mdstack link"]), (1, "fail"), r.stdout)

    def test_invalid_milestone_is_rejected(self):
        r = self.doctor("--fix", "--milestone", "release")
        self.assertEqual(r.returncode, 2)
        self.assertIn("milestone must be M followed by a number", r.stderr)

    def test_human_steps_listed_and_never_fixed(self):
        self.gh(["acme-bot"], "v2.1.0")
        self.trust_claude(accepted=False)
        self.hooks(trusted=False)
        configs = [os.path.join(self.home, ".claude.json"), os.path.join(self.codex, "config.toml")]
        before = [read(p) for p in configs]
        for args in ((), ("--fix",)):
            r = self.doctor(*args)
            self.assertEqual(r.returncode, 0, r.stdout)  # a human step is not a fail
            rows = self.rows(r)
            for check in ("gh acme-reviewer", "codex hooks", "claude trust"):
                self.assertEqual(rows[check], "human", r.stdout)
            self.assertIn("1 untrusted in %s" % os.path.join(self.codex, "hooks.json"), r.stdout)
            steps = self.humans(r)
            self.assertEqual(len(steps), 5, r.stdout)
            self.assertIn("- gh auth login as acme-reviewer (never gh auth switch)", steps)
            self.assertTrue(any("trust every hook under Review hooks" in s for s in steps), steps)
            self.assertTrue(any("mdstack attach ash --rw" in s for s in steps), steps)
        self.assertEqual([read(p) for p in configs], before)

    def test_claude_trust_on_a_parent_counts(self):
        with open(os.path.join(self.home, ".claude.json"), "w") as f:
            json.dump({"projects": {os.path.realpath(self.tmp): {"hasTrustDialogAccepted": True}}}, f)
        self.assertEqual(self.rows(self.doctor())["claude trust"], "ok")

    def test_claude_role_trust_keys_on_the_checkout(self):  # #408
        self.assertNotIn("claude role trust", self.rows(self.doctor()))  # the coordinator's answer covers it
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        with open(self.project, "a") as f:
            f.write('checkout = "%s"\n' % repo)
        config = os.path.join(self.home, ".claude.json")
        before = read(config)
        for args in ((), ("--fix",)):
            r = self.doctor(*args)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(self.rows(r)["claude trust"], "ok", r.stdout)
            self.assertEqual(self.rows(r)["claude role trust"], "human", r.stdout)
            self.assertEqual(self.detail(r, "claude role trust"), "not accepted for " + repo)
            self.assertIn("- before dispatch, run claude once in %s and pick Yes, I trust this folder, then /exit "
                          "(never a blind Enter: it picks No, exit)" % repo, self.humans(r))
        self.assertEqual(read(config), before)  # never written
        with open(config, "w") as f:
            json.dump({"projects": {os.path.realpath(p): {"hasTrustDialogAccepted": True}
                                    for p in (self.project_dir, repo)}}, f)
        r = self.doctor()
        self.assertEqual(self.rows(r)["claude role trust"], "ok", r.stdout)
        self.assertEqual(self.detail(r, "claude role trust"), os.path.realpath(repo))

    def test_placeholder_path_fails_without_touching_state(self):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('worktree_root = "%s/wt"' % os.path.join(self.tmp, "state"),
                                 'worktree_root = "<worktree-root>"'))
        r = self.doctor("--fix")
        self.assertEqual(r.returncode, 1)
        self.assertIn("paths.worktree_root: still the placeholder <worktree-root>", r.stdout)
        self.assertNotIn("state dir", self.rows(r))

    def test_grok_bot_runtime_skips_tmux_checks(self):
        self.write_profile(runtime="grok-bot")
        os.remove(os.path.join(self.bindir, "tmux"))
        for name in ("status", "wake"):
            os.rmdir(os.path.join(self.state, name))
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout)
        rows = self.rows(r)
        for check in ("tmux", "codex hooks", "claude trust"):
            self.assertNotIn(check, rows)
        self.assertEqual(rows["state dir"], "ok")
        self.assertEqual(self.detail(r, "triage"), "off: no Grok timer; coordinator dispositions")

    def test_grok_bot_triage_enabled_warns_no_timer(self):
        self.write_profile(runtime="grok-bot")
        with open(self.project, "a") as f:
            f.write("\n[triage]\nenabled = true\n")
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.rows(r)["triage"], "warn")
        self.assertEqual(self.detail(r, "triage"), "enabled: grok-bot installs no Grok timer; triage stays coordinator "
                         "dispositions; set triage.enabled = false (docs/triage.md)")
        self.assertNotIn("timer installed", r.stdout)
        self.write_profile()
        with open(self.project, "a") as f:
            f.write("\n[triage]\nenabled = true\n")
        self.assertNotIn("triage", self.rows(self.doctor()))  # tmux runs the scan from mdstack poll

    def test_profile_problem_exits_1(self):
        with open(self.project, "w") as f:
            f.write("[repo]\nowner = 1\n")
        r = self.doctor()
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("python", r.stdout)


class ToolDrift(DoctorBase):
    def probes(self, running="2.10.0", installed="2.10.0", pin="2.9.0"):
        self.tool("session-version", "echo 'example v%s'" % running)
        self.tool("installed-version", "echo 'example %s'" % installed)
        with open(self.project, "a") as f:
            f.write('\n[tools.example]\nrunning = ["session-version"]\ninstalled = ["installed-version"]\n')
            if pin:
                f.write('pin = "%s"\n' % pin)

    def test_matching_versions_above_numeric_pin(self):
        self.probes()
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows(r)["tool example"], "ok")
        self.assertEqual(self.detail(r, "tool example"), "running 2.10.0, installed 2.10.0, pin >= 2.9.0")

    def test_fix_canonicalizes_a_hand_made_crew_label(self):  # #1616
        labels = [{"name": n, "color": c, "description": d} for n, c, d in self.crew_labels()]
        express = next(x for x in labels if x["name"] == "crew:express")
        express.update(color="000000", description="hand made")
        log = os.path.join(self.home, "gh-label.log")
        self.gh(["acme-bot", "acme-reviewer"], "v2.1.0", labels)
        r = self.doctor()  # negative control: read-only reports it and writes nothing
        self.assertEqual(self.rows(r)["crew labels"], "fail", r.stdout)
        self.assertFalse(os.path.exists(log))
        r = self.doctor("--fix")
        self.assertEqual(self.rows(r)["crew labels"], "ok", r.stdout)
        self.assertEqual(read(log).splitlines(), ["label create crew:express -R acme/widgets --color %s --description %s "
                                                  "--force" % next((c, d) for n, c, d in self.crew_labels()
                                                                   if n == "crew:express")])
        os.remove(log)
        self.gh(["acme-bot", "acme-reviewer"], "v2.1.0", labels + [{"name": "crew:foreign", "color": "000000",
                                                                     "description": "x"}])
        r = self.doctor("--fix")  # an extra crew:* name still collides and writes nothing
        self.assertEqual(self.rows(r)["crew labels"], "fail", r.stdout)
        self.assertIn("crew namespace collision", r.stdout)
        self.assertFalse(os.path.exists(log))

    def crew_labels(self):
        return re.findall(r"^(crew:[^|]+)\|([^|]+)\|(.+)$", read(os.path.join(
            os.path.dirname(CREW), "..", "docs", "runbooks", "github-tracking.md")), re.M)

    def test_dry_run_keeps_state_read_only_and_reports_repo_and_tool_checks(self):
        self.probes(running="2.9.0", pin=None)
        os.rmdir(os.path.join(self.state, "inbox"))
        r = self.doctor("--fix", "--dry-run")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        rows = self.rows(r)
        self.assertEqual(rows["state dir"], "fail")
        self.assertEqual(rows["crew labels"], "ok")
        self.assertEqual(rows["tool example"], "warn")
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox")))

    def test_installed_update_is_inert_and_fix_does_not_restart(self):
        self.probes(running="2.9.0", pin=None)
        for args in ((), ("--fix",)):
            r = self.doctor(*args)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.rows(r)["tool example"], "warn")
            self.assertEqual(self.detail(r, "tool example"),
                             "running 2.9.0, installed 2.10.0; restart the session using the installed tool")
        self.assertIn("2.9.0", read(os.path.join(self.bindir, "session-version")))

    def test_below_pin_even_when_versions_match(self):
        self.probes(running="2.9.0", installed="2.9.0", pin="v2.10.0")
        r = self.doctor()
        self.assertEqual(self.rows(r)["tool example"], "warn")
        self.assertIn("upgrade to at least v2.10.0 and restart the session", r.stdout)

    def test_unreadable_or_failed_probe_warns(self):
        self.probes()
        for body in ("echo unknown", "echo 2.10.0; exit 1", "echo 2.10.0-beta"):
            self.tool("session-version", body)
            r = self.doctor()
            self.assertEqual(self.rows(r)["tool example"], "warn")
            self.assertIn("check the profile's read-only version probes", r.stdout)

    def test_no_configured_tools_skips_probes(self):
        self.assertFalse(any(k.startswith("tool ") for k in self.rows(self.doctor())))


class Handoff(DoctorBase):
    SHA = "a" * 40

    def setUp(self):
        super().setUp()
        self.env["FAKE_COMMENTS"] = os.path.join(self.tmp, "comments.json")
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace("[repo]\n", "[repo]\ncontrol_item = 99\n").replace(
                "[runtime]\n", '[runtime]\ninstance = "laptop"\n'))

    def record(self, *markers):
        """Coordinator handoff posts by a trusted login: (state, from, to) each, all under one handoff id."""
        with open(self.env["FAKE_COMMENTS"], "w") as f:
            json.dump([[{"user": {"login": "acme-bot"}, "body": "<!-- crew:v1 role=coordinator pass=handoff "
                         "handoff=20261103-abc123 state=%s from=%s to=%s cmd-id=chat sha=%s round=n/a verdict=n/a -->"
                         % (state, src, dst, self.SHA)} for state, src, dst in markers]], f)

    def owning(self, *markers):
        self.record(*markers)
        r = self.doctor()
        rows = self.rows(r)
        self.assertEqual((rows["control item"], rows["runtime instance"]), ("ok", "ok"), r.stdout)
        self.assertEqual(self.detail(r, "control item"), "#99")
        return rows["owning runtime"], self.detail(r, "owning runtime")

    def test_no_control_item_warns_without_an_owner_row(self):
        self.write_profile()
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout)
        rows = self.rows(r)
        self.assertEqual((rows["control item"], rows["runtime instance"]), ("warn", "warn"))
        self.assertEqual(self.detail(r, "control item"),
                         "not set: no ownership record; set repo.control_item (docs/handoff.md)")
        self.assertNotIn("owning runtime", rows)

    def test_this_runtime_owns(self):
        self.assertEqual(self.owning(("claimed", "none", "tmux@laptop")), ("ok", "tmux@laptop (this runtime)"))

    def test_another_runtime_owns(self):
        self.assertEqual(self.owning(("claimed", "none", "grok-bot@box")),
                         ("warn", "grok-bot@box; this runtime is tmux@laptop; read-only here until a handoff to it"))

    def test_draining_and_in_transit(self):
        claim, drain = ("claimed", "none", "tmux@laptop"), ("draining", "tmux@laptop", "session@laptop")
        self.assertEqual(self.owning(claim, drain), ("warn", "tmux@laptop, draining to session@laptop "
                                                             "(20261103-abc123); it starts no new pass"))
        self.assertEqual(self.owning(claim, drain, ("offered", "tmux@laptop", "session@laptop")),
                         ("warn", "in transit tmux@laptop → session@laptop (20261103-abc123); "
                                  "read-only until session@laptop acks or the owner aborts"))

    def test_no_record_yet(self):
        self.assertEqual(self.owning(), ("warn", "no record yet; this runtime's first start posts claimed"))

    def test_unreadable_control_item_fails(self):
        r = self.doctor()  # no comments file: the read exits 1
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.rows(r)["control item"], "fail")
        self.assertIn("#99 unreadable", self.detail(r, "control item"))
        self.assertNotIn("owning runtime", self.rows(r))

    def test_native_id_shown_as_written_through_the_read_item_binding(self):
        github = read(os.path.join(SCRIPTS, "..", "templates", "backends", "github.toml"))
        write_pack(os.path.join(self.project_dir, "pack"), mapping=github.replace("\n[ids]\n", '\n[ids]\nitem = "[A-Z][A-Z0-9]+-[0-9]+"\n'))
        with open(self.project) as f:
            text = f.read().replace("control_item = 99", 'control_item = "OPS-1042"')
        with open(self.project, "w") as f:
            f.write(text + 'pack = "pack"\n')
        self.put("render/bindings.json", json.dumps({"markers.read-item": "ex item comments <control-item>"}))
        self.tool("ex", '[ "$3" = OPS-1042 ] && exec /bin/cat "$FAKE_COMMENTS"')
        with open(self.env["FAKE_COMMENTS"], "w") as f:
            json.dump([{"author": "acme-bot", "created": "2026-11-04T17:05:00Z", "body": "<!-- crew:v1 role=coordinator "
                        "pass=handoff handoff=20261103-abc123 state=claimed from=none to=tmux@laptop cmd-id=chat sha=%s "
                        "round=n/a verdict=n/a -->" % self.SHA}], f)
        r = self.doctor()
        rows = self.rows(r)
        self.assertEqual((rows["control item"], self.detail(r, "control item")), ("ok", "OPS-1042"), r.stdout)
        self.assertEqual(self.detail(r, "owning runtime"), "tmux@laptop (this runtime)")
        os.remove(self.env["FAKE_COMMENTS"])
        r = self.doctor()
        self.assertEqual(self.rows(r)["control item"], "fail")
        self.assertIn("OPS-1042 unreadable", self.detail(r, "control item"))


class Version(DoctorBase):
    """The installed VERSION against the latest release (docs/release.md update path, Learn), in-process."""

    def version(self, have, values=None):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        doctor = mod.commands()["doctor"]
        path = os.path.join(self.tmp, "VERSION-%s" % have)
        if have:
            with open(path, "w") as f:
                f.write(have + "\n")
        with mock.patch.dict(os.environ, self.env), mock.patch.object(doctor, "VERSION_FILE", path):
            return doctor.version(values or {})[0]

    def test_latest_is_ok(self):
        self.assertEqual(self.version("v2.1.0"), ("ok", "version", "v2.1.0 (latest)", ""))

    def test_behind_warns_with_the_update_path(self):
        self.gh(["acme-bot"], "v2.2.0")
        status, _, detail, hint = self.version("v2.1.0")
        self.assertEqual((status, detail), ("warn", "v2.1.0 installed, v2.2.0 is the latest release"))
        self.assertIn("docs/release.md update path", hint)

    def test_non_github_source_makes_no_release_query(self):
        log = os.path.join(self.tmp, "gh.log")
        self.tool("gh", 'echo "$@" >> %s; exit 1' % log)
        self.assertEqual(self.version("v2.1.0", {"install.source": "mirror"}),
                         ("ok", "version", "v2.1.0; latest not checked (source mirror)", ""))
        self.assertFalse(os.path.exists(log))

    def test_unreadable_release_or_no_version_warns(self):
        self.tool("gh", "exit 1")
        self.assertEqual(self.version("v2.1.0")[0], "warn")
        self.assertEqual(self.version(None)[2], "no VERSION: not a release bundle")


class Forge(DoctorBase):
    """gh is needed only for a github-bound concern or the github release source (#1123)."""

    def test_github_binding_or_source_needs_gh(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        forge = mod.commands()["doctor"].forge
        packed = {"backends.change.name": "example", "backends.release.name": "github", "install.source": "mirror"}
        self.assertFalse(forge(packed))
        self.assertTrue(forge(dict(packed, **{"release.changelog": "CHANGELOG.md"})))
        self.assertTrue(forge(dict(packed, **{"backends.markers.name": "github"})))
        self.assertTrue(forge(dict(packed, **{"install.source": "github"})))
        self.assertTrue(forge({"backends.change.name": "example"}))


class Sandbox(DoctorBase):
    """A session sandbox with no writable root over the checkout's .git fails unless sandbox_env is set (#1544)."""

    def test_unwritable_checkout_git_fails_until_sandbox_env(self):
        os.remove(os.path.join(self.bindir, "git"))
        os.symlink(shutil.which("git", path=os.environ["PATH"]), os.path.join(self.bindir, "git"))
        subprocess.run(["git", "init", "-q", self.project_dir], check=True)
        git = os.path.realpath(os.path.join(self.project_dir, ".git"))  # git reports the resolved path
        self.env.pop("CREW_SANDBOX_ENV", None)
        self.assertEqual(self.rows(self.doctor())["sandbox"], "ok")
        os.chmod(git, 0o500)
        self.addCleanup(os.chmod, git, 0o755)
        r = self.doctor()
        self.assertEqual((r.returncode, self.rows(r)["sandbox"]), (1, "fail"), r.stdout)
        self.assertEqual(self.detail(r, "sandbox"), "this session sandboxed with no writable root over %s; set "
                         'runtime.options.sandbox_env = "<NAME>=%s" with the launcher\'s writable-roots variable (or '
                         "export CREW_SANDBOX_ENV), then rerun" % (git, git))
        self.env["CREW_SANDBOX_ENV"] = "CREW_TEST_SANDBOX=" + git
        self.assertEqual(self.rows(self.doctor())["sandbox"], "ok")
        self.assertFalse([n for n in os.listdir(git) if n.startswith("mdstack-probe-")])

    def test_linked_worktree_checkout_probes_the_common_dir(self):
        os.remove(os.path.join(self.bindir, "git"))
        os.symlink(shutil.which("git", path=os.environ["PATH"]), os.path.join(self.bindir, "git"))
        main = os.path.join(self.tmp, "main")
        subprocess.run(["git", "init", "-q", main], check=True)
        subprocess.run(["git", "-C", main, "-c", "user.name=t", "-c", "user.email=t", "commit", "-q", "--allow-empty",
                        "-m", "base"], check=True)
        linked = os.path.join(self.tmp, "linked")
        subprocess.run(["git", "-C", main, "worktree", "add", "-q", linked], check=True)
        with open(self.project, "a") as f:
            f.write('checkout = "%s"\n' % linked)
        common = os.path.realpath(os.path.join(main, ".git"))
        os.chmod(common, 0o500)
        self.addCleanup(os.chmod, common, 0o755)
        self.env.pop("CREW_SANDBOX_ENV", None)
        r = self.doctor()
        self.assertEqual(self.rows(r)["sandbox"], "fail", r.stdout)
        self.assertIn("no writable root over %s" % common, self.detail(r, "sandbox"))

    def test_adapter_declared_roots(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        sandbox = mod.commands()["doctor"].sandbox
        adapter = mod.harnesses.ADAPTERS["claude-code"]
        values = {"engines.coordinator": "claude-code"}
        git = os.path.join(self.project_dir, ".git")
        with mock.patch.dict(os.environ, {"CREW_SANDBOX_ENV": ""}):
            self.assertEqual(sandbox(values, self.project)[0][0], "ok")  # no declaration: no sandbox
            alias = os.path.join(self.tmp, "alias")
            os.symlink(self.project_dir, alias)  # a root named through a symlink still covers the resolved .git
            for roots, status in ([self.tmp], "ok"), ([alias], "ok"), ([os.path.join(self.tmp, "other")], "fail"):
                with mock.patch.object(adapter, "sandbox_roots", lambda v: roots, create=True):
                    row = sandbox(values, self.project)[0]
                self.assertEqual(row[0], status, row)
            self.assertIn("claude-code's launcher sandboxed with no writable root over " + git, row[2])
            with mock.patch.object(adapter, "sandbox_roots", lambda v: [], create=True), \
                    mock.patch.dict(os.environ, {"CREW_SANDBOX_ENV": "CREW_TEST_SANDBOX=1"}):
                self.assertEqual(sandbox(values, self.project)[0], ("ok", "sandbox", "sandbox_env set", ""))


LABELS_PY = """import json, sys
path = sys.argv[1]
labels = json.load(open(path))
if sys.argv[2] == "list":
    print(json.dumps([labels]))
else:
    a = sys.argv[2:]
    new = dict(name=a[2], color=a[a.index("--color") + 1], description=a[a.index("--description") + 1])
    json.dump([x for x in labels if x["name"] != a[2]] + [new], open(path, "w"))
"""


def label_evidence():
    """#1616 lifecycle: a hand-made crew:express label on a stateful fake GitHub is repaired by doctor --fix, then
    the fake host is deleted."""
    fixture = ToolDrift("test_fix_canonicalizes_a_hand_made_crew_label")
    fixture.setUp()
    try:
        store = os.path.join(fixture.tmp, "labels.json")
        labels = [{"name": n, "color": c, "description": d} for n, c, d in fixture.crew_labels()]
        canonical = dict(next(x for x in labels if x["name"] == "crew:express"))
        next(x for x in labels if x["name"] == "crew:express").update(color="000000", description="hand made")
        with open(store, "w") as f:
            json.dump(labels, f)
        with open(os.path.join(fixture.tmp, "labels.py"), "w") as f:
            f.write(LABELS_PY)
        fixture.gh(["acme-bot", "acme-reviewer"], "v2.1.0")
        os.rename(os.path.join(fixture.bindir, "gh"), os.path.join(fixture.bindir, "gh-std"))
        py = "%s %s %s" % (sys.executable, os.path.join(fixture.tmp, "labels.py"), store)
        fixture.tool("gh", 'case "$1 $2" in\n"api repos/acme/widgets/labels?per_page=100") exec %s list;;\n'
                     '"label create") exec %s "$@";;\n*) exec %s "$@";;\nesac' % (
                         py, py, os.path.join(fixture.bindir, "gh-std")))

        def express():
            return next(x for x in json.load(open(store)) if x["name"] == "crew:express")
        print("create: fake GitHub crew:express = %s" % json.dumps(express(), sort_keys=True))
        r = fixture.doctor()
        print("doctor: exit %d; crew labels %s; crew:express unchanged: %s" % (
            r.returncode, fixture.rows(r)["crew labels"], express()["color"] == "000000"))
        r = fixture.doctor("--fix")
        print("doctor --fix: exit %d; crew labels %s" % (r.returncode, fixture.rows(r)["crew labels"]))
        print("update: fake GitHub crew:express = %s; canonical: %s" % (
            json.dumps(express(), sort_keys=True), express() == canonical))
        r = fixture.doctor()
        print("doctor (rerun): exit %d; crew labels %s" % (r.returncode, fixture.rows(r)["crew labels"]))
    finally:
        fixture.doCleanups()
    print("delete: fake host and label store removed: %s" % (not os.path.exists(fixture.tmp)))


class Confinement(unittest.TestCase):
    """Live builder runs whose record marks them unconfined (#1252)."""

    def test_unconfined_builder_runs_warn(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        doctor = mod.commands()["doctor"]
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        values = {"paths.state_dir": tmp, "repo.owner": "acme", "repo.name": "widgets"}
        self.assertEqual(doctor.confinement(values), [("ok", "confinement", "confinement=off; no unconfined builder run", "")])
        runs = os.path.join(tmp, "acme__widgets", "runs")
        os.makedirs(runs)
        base = dict(index=10, item="i", repo="r", worktree="w", claim="c", engine="codex", model="m", effort="e",
                    harness="codex", role="builder")
        for name, extra in (("ben-1", dict(confined=True)), ("ben-2", dict(confined=False, unconfined="why")),
                            ("ben-3", {}), ("vera-9", dict(role="reviewer"))):
            with open(os.path.join(runs, name + ".json"), "w") as f:
                json.dump(dict(base, **{"pass": "build"}, **extra), f)
        values["runtime.options.confinement"] = "enforce"
        self.assertEqual(doctor.confinement(values), [(
            "warn", "confinement", "confinement=enforce; unconfined: ben-2 (why); ben-3 (spawned before #1252)",
            "docs/runtimes/tmux.md#confinement")])
        bindir = os.path.join(tmp, "bin")  # a Codex that cannot apply its sandbox here (a nesting launcher)
        os.makedirs(bindir)
        with open(os.path.join(bindir, "codex"), "w") as f:
            f.write('#!/bin/sh\necho "sandbox-exec: sandbox_apply: Operation not permitted" >&2\nexit 71\n')
        os.chmod(os.path.join(bindir, "codex"), 0o755)
        values["runtime.options.permission_mode"] = "safe"
        with mock.patch.dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"]):
            rows = doctor.confinement(values)
        self.assertEqual(rows[0], ("warn", "confinement", "Codex cannot apply its OS write sandbox on this host "
                                   "(`codex sandbox -- true` exited 71: sandbox-exec: sandbox_apply: Operation not "
                                   "permitted)", "docs/runtimes/tmux.md#confinement"))
        values["runtime.options.permission_mode"] = "bypass"
        with mock.patch.dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"]):
            self.assertEqual(len(doctor.confinement(values)), 1)


class SessionServer(unittest.TestCase):
    """A shared session server's sandbox, which its runs inherit, from the backend's server_pids() (#1469)."""

    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        cls.doctor = mod.commands()["doctor"]

    def row(self, pids, sandboxed=None):
        def server_pids():
            if isinstance(pids, Exception):
                raise pids
            return pids
        adapter = mock.Mock(EXECUTABLE="herdr", server_pids=server_pids)
        with mock.patch.object(self.doctor.proc, "sandboxed", lambda pid: (sandboxed or {}).get(pid)):
            return self.doctor.session_server(adapter)

    def test_absent_sandboxed_clean_and_unknown(self):
        start = ("start `herdr server` from an ordinary terminal opened outside any agent session: its runs inherit "
                 "that terminal's environment and sandbox")
        self.assertEqual(self.row([]), [("human", "session server", "herdr server not running", start)])
        status, _, detail, hint = self.row([7], {7: True})[0]
        self.assertEqual((status, detail), ("fail", "pid 7 runs sandboxed; every run inherits it"))
        self.assertEqual(hint, "in an idle window for all its users, stop it with `herdr server stop`, then " + start)
        self.assertEqual(self.row([7, 8], {7: False, 8: False})[0][:3], ("ok", "session server", "pid 7, 8 not sandboxed"))
        for pids, found in ([7], {}), ([7, 8], {7: True, 8: False}):  # unreadable (non-macOS) or mixed holders
            status, _, detail, hint = self.row(pids, found)[0]
            self.assertEqual(status, "warn", detail)
            self.assertIn("sandbox unknown or mixed", detail)
            self.assertTrue(hint.startswith("if it was started from an agent session, restart it with `herdr server`"))
        status, _, detail, _ = self.row(RuntimeError("no process holds /s"))[0]
        self.assertEqual((status, detail), ("warn", "sandbox unknown: no process holds /s"))

    def test_backend_without_a_shared_server_has_no_row(self):
        self.assertEqual(self.doctor.session_server(mock.Mock(spec=["EXECUTABLE"])), [])

    def test_os_sandbox_read(self):
        """macOS reads launchd as unsandboxed and a gone pid as unknown; other platforms are unknown."""
        dead = subprocess.Popen(["true"])
        dead.wait()
        expected = (False, None) if sys.platform == "darwin" else (None, None)
        self.assertEqual((self.doctor.proc.sandboxed(1), self.doctor.proc.sandboxed(dead.pid)), expected)


if __name__ == "__main__":
    if sys.argv[1:] == ["--evidence-labels"]:
        label_evidence()
    else:
        unittest.main()
