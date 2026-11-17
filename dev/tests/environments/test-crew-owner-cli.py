"""Tests for the owner CLI without --project (#1965); fixtures in crew_testlib.py (stdlib only).

Covers the M61 P1 matrix (docs/specs/portable.md): in an owner shell (no CREW_ROLE, no MDSTACK_INTERNAL) --project in
either spelling exits 2 with one stderr line and writes nothing (P1.1), no command's --help shows it (P1.2), up, start
and attach take the installed multi-repo team file whole (P1.3), a per-repo command selects its repo with --repo KEY,
the only repo, or exits 2 naming the keys (P1.4), MDSTACK_CONFIG still overrides (P1.5), and a crew window or an
mdstack child process keeps --project exactly as before (P1.6). The tmux adapter starts no server carrying
MDSTACK_INTERNAL, so an owner pane on it stays an owner shell.
Run in CI.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW, INPUTS, ROOT_DIR, Base

TEAM = ('[team]\nname = "eng"\n[team.runtime]\nname = "tmux"\n[team.identities]\nowners = ["acme-owner"]\n'
        '[team.paths]\nstate_dir = "{state}"\nworktree_root = "{state}/wt"\ntoolchain_bin = "/opt/node/bin"\n'
        '[repos.widgets]\nrepo = "acme/widgets"\n[repos.gadgets]\nrepo = "acme/gadgets"\n'
        '[repos.gizmos]\nrepo = "acme/gizmos"\n')
REFUSED = "mdstack: --project is disabled; mdstack uses the installed team (%s). Set MDSTACK_CONFIG to override.\n"


class OwnerCli(Base):
    def setUp(self):
        super().setUp()
        for name in ("CREW_ROLE", "TMUX", "TMUX_PANE", "MDSTACK_INTERNAL"):  # an owner shell, not the test runner's
            self.env.pop(name, None)
        self.env["TMUX_TMPDIR"] = os.path.join(self.tmp, "tmux-tmp")
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(self.root)
        self.env["CREW_ROOT"] = self.root
        self.team = os.path.join(self.root, "my-team.toml")
        with open(self.team, "w") as f:
            f.write(TEAM.format(state=os.path.join(self.tmp, "state")))

    def owner(self, *args, **env):
        return subprocess.run([sys.executable, CREW, *args], capture_output=True, text=True, cwd="/",
                              env=dict(self.env, **env))

    def names(self):
        return [c[0] for c in self.calls()]

    def rows(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return dict(line.split(None, 1) for line in r.stdout.splitlines() if line.strip())

    def tree(self):
        return sorted(os.path.relpath(os.path.join(d, n), self.tmp) for d, ds, fs in os.walk(self.tmp) for n in ds + fs)

    def test_p1_1_project_in_either_spelling_exits_2_and_writes_nothing(self):
        before = self.tree()
        for argv in (["status"], ["up"], ["start"], ["attach"], ["attach", "coordinator"], ["down"], ["doctor"],
                     ["layout", "--write"], ["host", "check", "h"], ["send", "ash", "steer", "#1"]):
            for flag in (["--project", self.team], ["--project=" + self.team], ["--proj", self.team]):
                with self.subTest(argv=argv, flag=flag[0][:10]):
                    r = self.owner(*argv, *flag)
                    self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "", REFUSED % self.team))
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.tree(), before)
        rows = self.rows(self.owner("layout", "--repo", "widgets"))  # control: the same tree, no flag, runs
        self.assertEqual(rows["state"], os.path.join(self.tmp, "state", "eng", "acme__widgets"))

    def test_p1_1_refusal_names_mdstack_config_when_set(self):
        r = self.owner("status", "--project", self.team, MDSTACK_CONFIG=self.project)
        self.assertEqual((r.returncode, r.stderr), (2, REFUSED % self.project))

    def test_p1_2_no_help_shows_project(self):
        parsers = [[name[:-3]] for name in sorted(os.listdir(os.path.join(ROOT_DIR, "environments", "terminal",
                                                                            "crew.d")))
                   if name.endswith(".py") and not name.startswith("_")]
        parsers += [["host", "check"], ["host", "prepare"], ["runner", "run"], ["runner", "logs"]]
        for argv in parsers:
            with self.subTest(argv=argv):
                r = self.owner(*argv, "--help")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertNotIn("--project", r.stdout)
        r = self.owner("layout", "--help")
        self.assertIn("--repo KEY", r.stdout)
        r = self.owner("up", "--help", CREW_ROLE="builder")  # control: a crew window's help is today's
        self.assertIn("--project PROJECT", r.stdout)
        self.assertNotIn("--repo", r.stdout)

    def test_p1_3_up_and_start_run_the_installed_team(self):
        r = self.owner("up", "--inputs", INPUTS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, "mdstack: config %s\n" % self.team)
        new = [c for c in self.calls() if c[0] == "new-session"]
        self.assertEqual([c[c.index("-s") + 1] for c in new], ["crew-team-eng"])
        for repo in ("widgets", "gadgets", "gizmos"):
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, "state", "eng", "acme__" + repo, "render")), repo)
        other = os.path.join(self.tmp, "other.toml")  # control: an explicit --team stays
        with open(other, "w") as f:
            f.write(TEAM.replace('name = "eng"', 'name = "ops"').format(state=os.path.join(self.tmp, "state")))
        r = self.owner("up", "--team", other, "--inputs", INPUTS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c[c.index("-s") + 1] for c in self.calls() if c[0] == "new-session"],
                         ["crew-team-eng", "crew-team-ops"])
        r = self.owner("start", "--inputs", INPUTS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew-team-eng already running", r.stdout)
        self.assertEqual(self.names().count("new-session"), 2)
        self.assertEqual([c for c in self.calls() if c[0] == "attach-session"],
                         [["attach-session", "-t", "=crew-team-eng:0"]])

    def test_p1_3_attach_bare_and_coordinator_take_the_team(self):
        r = self.owner("attach")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.names().count("new-session"), 1)
        with open(self.state_file, "w") as f:
            json.dump({"crew-team-eng": {"0": "ash", "10": "ben-7-widgets"}}, f)
        r = self.owner("attach", "coordinator")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c for c in self.calls() if c[0] == "attach-session"][-1],
                         ["attach-session", "-r", "-t", "=crew-team-eng:0"])

    def test_p1_4_per_repo_command_selects_by_key(self):
        rows = self.rows(self.owner("layout", "--repo", "gadgets"))
        self.assertEqual(rows["state"], os.path.join(self.tmp, "state", "eng", "acme__gadgets"))
        for argv, line in ((["layout"], "lists repos widgets, gadgets, gizmos; name one with --repo KEY"),
                           (["layout", "--repo", "nope"], "--repo nope: %s has no such repo (repos: widgets, "
                                                           "gadgets, gizmos)" % self.team),
                           (["up", "--repo", "nope"], "--repo nope: %s has no such repo" % self.team)):
            with self.subTest(argv=argv):
                r = self.owner(*argv)
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn(line, r.stderr)
        self.assertEqual(self.calls(), [])
        with open(self.team, "w") as f:
            f.write(TEAM.format(state=os.path.join(self.tmp, "state")).split("[repos.gadgets]")[0])
        rows = self.rows(self.owner("layout"))  # a single-repo team needs no --repo
        self.assertEqual(rows["state"], os.path.join(self.tmp, "state", "eng", "acme__widgets"))

    def test_p1_4_own_repo_option_selects_by_team_repo(self):
        """content and feedback keep their own --repo; their team repo is --team-repo KEY (#1976 round 1)."""
        content = ("content", "HEAD", "HEAD", "HEAD", "HEAD", "--repo", ROOT_DIR)
        feedback = ("feedback", "--class", "owner-cli", "--summary", "x", "--repo", "acme/mdstack", "--dry-run")
        for argv in (content, feedback):
            with self.subTest(cmd=argv[0]):
                r = self.owner(*argv)
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn("lists repos widgets, gadgets, gizmos; name one with --team-repo KEY", r.stderr)
                r = self.owner(*argv, "--team-repo", "nope")
                self.assertEqual(r.returncode, 2)
                self.assertIn("--team-repo nope: %s has no such repo" % self.team, r.stderr)
        r = self.owner(*content, "--team-repo", "gadgets")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("content=identical carried-from="), r.stdout)
        r = self.owner(*feedback, "--team-repo", "widgets")  # past the resolver: it acts under FILE#widgets
        self.assertIn("mdstack: config %s#widgets\n" % self.team, r.stderr)
        self.assertNotIn("lists repos", r.stderr)
        rows = self.rows(self.owner("layout", "--team-repo", "gizmos"))  # an alias of --repo elsewhere
        self.assertEqual(rows["state"], os.path.join(self.tmp, "state", "eng", "acme__gizmos"))

    def test_p1_5_mdstack_config_overrides(self):
        rows = self.rows(self.owner("layout", MDSTACK_CONFIG=self.project))
        self.assertEqual(rows["state"], self.state)
        rows = self.rows(self.owner("layout", MDSTACK_CONFIG=self.team + "#gizmos"))
        self.assertEqual(rows["state"], os.path.join(self.tmp, "state", "eng", "acme__gizmos"))
        r = self.owner("layout", "--repo", "x", MDSTACK_CONFIG=self.project)  # a plain profile has no repo keys
        self.assertEqual((r.returncode, r.stderr), (2, "mdstack: --repo x: %s has no such repo (repos: none)\n"
                                                    % self.project))

    def test_p1_6_crew_window_and_mdstack_child_keep_project(self):
        for env in ({"CREW_ROLE": "builder"}, {"MDSTACK_INTERNAL": "1"}):
            with self.subTest(env=env):
                rows = self.rows(self.owner("layout", "--project", self.project, **env))
                self.assertEqual(rows["state"], self.state)
                rows = self.rows(self.owner("layout", CREW_PROJECT=self.project, **env))  # default_config(), as today
                self.assertEqual(rows["state"], self.state)
                r = self.owner("layout", "--repo", "widgets", **env)
                self.assertEqual(r.returncode, 2)
                self.assertIn("unrecognized arguments: --repo widgets", r.stderr)

    def test_main_marks_its_children_internal(self):
        r = subprocess.run([sys.executable, "-c", "import os, runpy, sys; m = runpy.run_path(sys.argv[1]); "
                            "m['main'](['layout', '--repo', 'widgets']); print(os.environ.get('MDSTACK_INTERNAL'))",
                            CREW], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[-1], "1")

    def test_tmux_adapter_drops_the_marker(self):
        fake = os.path.join(self.tmp, "bin", "tmux")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nprintf '%s' \"${MDSTACK_INTERNAL-unset}\"\n")
        spec = importlib.util.spec_from_file_location("tmux_adapter", os.path.join(
            ROOT_DIR, "environments", "terminal", "sessions", "tmux", "adapter.py"))
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ.update(PATH=self.env["PATH"], TMUX_TMPDIR=self.env["TMUX_TMPDIR"], MDSTACK_INTERNAL="1")
        self.assertEqual(adapter.tmux("new-session").stdout, "unset")
        self.assertEqual(subprocess.run(["tmux"], capture_output=True, text=True).stdout, "1")  # control: inherited


if __name__ == "__main__":
    unittest.main()
