"""Tests for mdstack attach, moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: read-only by default, by role, the builders view leaves the layout unchanged, unknown
window and missing session refused, and a run on a role host through `ssh -t` and `capture` (#348).
The bare form (#1942): the installed profile (<root>/config.toml or the root's one <team>.toml), a multi-repo
team file with no #REPO, start-if-down through `mdstack up --team`, switch-client inside tmux and its refusals.
Run in CI.
"""
import json
import os
import subprocess
import unittest
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW, Base, ObserveBase

TEAM = ('[team]\nname = "eng"\n[team.runtime]\nname = "tmux"\n[team.identities]\nowners = ["acme-owner"]\n'
        '[team.paths]\nstate_dir = "{state}"\nworktree_root = "{state}/wt"\ntoolchain_bin = "/opt/node/bin"\n'
        '[repos.widgets]\nrepo = "acme/widgets"\n[repos.gadgets]\nrepo = "acme/gadgets"\n'
        '[repos.gizmos]\nrepo = "acme/gizmos"\n')


class Attach(ObserveBase):
    def attach(self, *args):
        return self.crew("attach", *args, "--project", self.project)

    def attaches(self):
        return [c for c in self.calls() if c[0] == "attach-session"]

    def test_attach_window_read_only_by_default(self):
        r = self.attach("ben-7")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.attaches(), [["attach-session", "-r", "-t", "=crew-acme-widgets:10"]])
        self.assertEqual(self.attach("ben-8", "--rw").returncode, 0)
        self.assertEqual(self.attaches()[1], ["attach-session", "-t", "=crew-acme-widgets:11"])

    def test_attach_by_role(self):
        for role, index in [("reviewer", 20), ("coordinator", 0), ("synthesizer", 1)]:
            self.assertEqual(self.attach(role).returncode, 0, role)
            self.assertEqual(self.attaches()[-1], ["attach-session", "-r", "-t", "=crew-acme-widgets:%d" % index])
        r = self.attach("builder")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ben-7, ben-8", r.stdout)
        self.assertEqual(len(self.attaches()), 3)

    def test_attach_team_window_0_by_name_alias_or_role(self):  # #1329
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('owners = ["acme-owner"]\n', 'owners = ["acme-owner"]\nteam = "mdp-m4"\n'))
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": dict(self.session, **{"0": "ash-mdp-m4"})}, f)
        for target in ("ash-mdp-m4", "ash", "coordinator"):
            self.assertEqual(self.attach(target).returncode, 0, target)
            self.assertEqual(self.attaches()[-1], ["attach-session", "-r", "-t", "=crew-acme-widgets:0"])

    def test_attach_refuses_unknown_window_and_missing_session(self):
        r = self.attach("ben-99")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no window ben-99", r.stdout)
        os.remove(self.state_file)
        r = self.attach("ben-7")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not running", r.stdout)
        self.assertEqual(self.attaches(), [])

    def test_attach_builders_temporary_tiled_view_keeps_layout(self):
        r = self.attach("builders")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.calls()
        new = [c for c in calls if c[0] == "new-session"]
        self.assertEqual(len(new), 1)
        view = new[0][new[0].index("-s") + 1]
        self.assertTrue(view.startswith("crew-acme-widgets-builders-"), view)
        splits = [c for c in calls if c[0] == "split-window"]
        self.assertEqual(len(splits), 1)
        self.assertIn("capture-pane -p -t '=crew-acme-widgets:10' ", new[0][-1])
        self.assertIn("capture-pane -p -t '=crew-acme-widgets:11' ", splits[0][-1])
        self.assertIn(["select-layout", "-t", "=%s:" % view, "tiled"], calls)
        self.assertEqual(self.attaches(), [["attach-session", "-r", "-t", "=" + view]])
        self.assertEqual(calls[-1], ["kill-session", "-t", "=" + view])
        crew_targets = [c for c in calls if "-t" in c and c[c.index("-t") + 1].startswith("=crew-acme-widgets")
                        and not c[c.index("-t") + 1].startswith("=" + view)]
        self.assertEqual({c[0] for c in crew_targets}, {"has-session", "list-windows"})
        with open(self.state_file) as f:
            self.assertEqual(json.load(f), {"crew-acme-widgets": self.session})

    def test_attach_builders_without_builders(self):
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash"}}, f)
        r = self.attach("builders")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no builder windows", r.stdout)
        self.assertEqual([c for c in self.calls() if c[0] in ("new-session", "attach-session")], [])


class AttachRemote(ObserveBase):  # #348: a run on a role host, through its host's attach and capture verbs
    def attach(self, *args, **env):
        return self.crew("attach", *args, "--project", self.project, **env)

    def attaches(self):
        return [c for c in self.calls() if c[0] == "attach-session"]

    def test_attach_remote_window_over_ssh_tty(self):
        self.remote_run("ben-12")
        os.remove(self.state_file)  # no local session needed for a remote run
        r = self.attach("ben-12")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.attach("ben-12", "--rw").returncode, 0)
        calls = self.ssh_calls()
        self.assertEqual([(c["request"]["verb"], c["request"]["window"], c["request"]["rw"]) for c in calls],
                         [("attach", "ben-12", False), ("attach", "ben-12", True)])
        self.assertEqual(calls[0]["request"]["project"], "acme__widgets")
        self.assertIn("-t", calls[0]["argv"])
        self.assertNotIn("-T", calls[0]["argv"])
        self.assertTrue(calls[0]["argv"][-1].startswith("crew-host "))
        r = self.attach("ben-12", FAKE_SSH_EXIT="255")
        self.assertEqual(r.returncode, 255)
        self.assertIn("crew: host-b unreachable", r.stdout)

    def test_attach_role_counts_remote_runs(self):
        self.remote_run("ben-12")
        r = self.attach("builder")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ben-7, ben-8, ben-12", r.stdout)
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash"}}, f)
        self.assertEqual(self.attach("builder").returncode, 0)
        self.assertEqual([c["request"]["window"] for c in self.ssh_calls()], ["ben-12"])
        self.assertEqual(self.attaches(), [])

    def test_attach_builders_adds_a_capture_pane_per_remote_builder(self):
        self.remote_run("ben-12")
        self.remote_run("vera-13", role="reviewer")
        r = self.attach("builders")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        splits = [c for c in self.calls() if c[0] == "split-window"]
        self.assertEqual(len(splits), 2)
        self.assertIn("attach ben-12 --capture --project %s" % self.project, splits[1][-1])
        self.assertIn("'ben-12 on host-b'", splits[1][-1])
        self.assertIn("sleep 15", splits[1][-1])
        self.assertNotIn("vera-13", json.dumps(self.calls()))
        self.assertEqual(self.ssh_calls(), [])  # the view's pane polls; opening it calls no host

    def test_capture_prints_the_remote_pane_once(self):
        self.remote_run("ben-12", capture=dict(result="ok", text="$ make test\nok"))
        r = self.attach("ben-12", "--capture")
        self.assertEqual((r.returncode, r.stdout), (0, "$ make test\nok\n"))
        self.assertEqual(self.ssh_calls()[0]["request"]["verb"], "capture")
        self.remote_run("ben-12", capture=dict(result="refused", reason="no run ben-12 on this host"))
        r = self.attach("ben-12", "--capture")
        self.assertEqual((r.returncode, r.stdout), (1, "crew: host-b refused: no run ben-12 on this host\n"))
        r = self.attach("ben-7", "--capture")
        self.assertEqual((r.returncode, r.stdout), (1, "crew: no remote run ben-7\n"))


class AttachBare(Base):  # #1942: a bare `mdstack attach` types into the installed team's coordinator
    def setUp(self):
        super().setUp()
        for name in ("CREW_ROLE", "TMUX", "TMUX_PANE"):  # this suite may itself run in a crew pane
            self.env.pop(name, None)
        self.env["TMUX_TMPDIR"] = os.path.join(self.tmp, "tmux-tmp")
        self.socket = os.path.join(self.env["TMUX_TMPDIR"], "tmux-%d" % os.getuid(), "default")
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(self.root)
        self.env["CREW_ROOT"] = self.root
        self.team = os.path.join(self.root, "my-team.toml")  # [team] name, not the file name, keys the session
        with open(self.team, "w") as f:
            f.write(TEAM.format(state=os.path.join(self.tmp, "state")))

    def bare(self, *args, **env):
        return subprocess.run([sys.executable, CREW, "attach", *args], capture_output=True, text=True, cwd="/",
                              env=dict(self.env, **env))

    def names(self):
        return [c[0] for c in self.calls()]

    def joins(self):
        return [c for c in self.calls() if c[0] in ("attach-session", "switch-client")]

    def test_team_toml_home_starts_the_team_once_then_attaches_interactive(self):
        r = self.bare()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, "mdstack: config %s\n" % self.team)
        new = [c for c in self.calls() if c[0] == "new-session"]
        self.assertEqual([c[c.index("-s") + 1] for c in new], ["crew-team-eng"])
        env = self.session_env(new[0])
        self.assertEqual((env["CREW_TEAM"], env["CREW_STATE"]), (self.team, os.path.join(self.tmp, "state", "eng")))
        for repo in ("widgets", "gadgets", "gizmos"):  # up --team renders every repo
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, "state", "eng", "acme__" + repo, "render")), repo)
        self.assertEqual(self.joins(), [["attach-session", "-t", "=crew-team-eng:0"]])  # no -r: typing enabled
        self.assertEqual(self.names()[-1], "attach-session")
        r = self.bare()  # running: no second session
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew-team-eng already running", r.stdout)
        self.assertEqual(self.names().count("new-session"), 1)
        self.assertEqual(self.joins(), [["attach-session", "-t", "=crew-team-eng:0"]] * 2)

    def test_config_toml_home_wins_and_starts_its_crew(self):
        os.rename(self.project, os.path.join(self.root, "config.toml"))
        r = self.bare()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stderr, "mdstack: config %s\n" % os.path.join(self.root, "config.toml"))
        self.assertEqual(self.names().count("new-session"), 1)
        self.assertEqual(self.joins(), [["attach-session", "-t", "=crew-acme-widgets:0"]])

    def test_env_overrides_and_explicit_project_win_over_the_home(self):
        for argv, env in (([], {"MDSTACK_CONFIG": self.project}), (["--project", self.project], {})):
            with self.subTest(argv=argv, env=sorted(env)):
                r = self.bare(*argv, **env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(r.stderr, "mdstack: config %s\n" % self.project)
                self.assertEqual(self.joins()[-1], ["attach-session", "-t", "=crew-acme-widgets:0"])

    def test_two_team_files_or_none_fail_before_any_start(self):
        with open(os.path.join(self.root, "other.toml"), "w") as f:
            f.write(TEAM.replace('name = "eng"', 'name = "other"').format(state=os.path.join(self.tmp, "state")))
        missing = os.path.join(self.root, "config.toml")
        for case in ("two", "none"):
            with self.subTest(case=case):
                r = self.bare()
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertEqual(r.stderr, "mdstack: config %s\n" % missing)
                self.assertEqual(r.stdout, "%s:(file): cannot read (No such file or directory)\n" % missing)
                self.assertEqual(self.calls(), [])
                for path in (self.team, os.path.join(self.root, "other.toml")):
                    if os.path.exists(path):
                        os.remove(path)

    def test_failed_start_attaches_nothing(self):
        with open(self.team, "a") as f:
            f.write('[team.runtime.options.notes]\ncoordinator = ["policy.md"]\n')
        r = self.bare()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("cannot read runtime.options.notes.coordinator file policy.md", r.stdout)
        self.assertNotIn("new-session", self.names())
        self.assertEqual(self.joins(), [])

    def test_inside_tmux_switches_the_client_instead_of_nesting(self):
        r = self.bare(TMUX="%s,4242,3" % self.socket)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.names().count("new-session"), 1)
        self.assertEqual(self.joins(), [["switch-client", "-t", "=crew-team-eng:0"]])

    def test_crew_pane_or_foreign_server_refuses_before_any_start(self):
        r = self.bare(CREW_ROLE="builder")
        self.assertEqual((r.returncode, r.stdout), (2, "crew: refusing attach: run from a crew pane (CREW_ROLE="
                                                       "builder); it is the owner's terminal shortcut\n"))
        r = self.bare(TMUX="%s,4242,3" % os.path.join(os.path.dirname(self.socket), "other"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("crew: refusing attach: this tmux client is on another server", r.stdout)
        self.assertFalse([c for c in self.calls() if c[0] != "has-session"], self.calls())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "state")))

    def test_coordinator_target_takes_a_multi_repo_team_file_read_only(self):
        with open(self.state_file, "w") as f:
            json.dump({"crew-team-eng": {"0": "ash", "10": "ben-7-widgets"}}, f)
        r = self.crew("attach", "coordinator", "--project", self.team)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.joins(), [["attach-session", "-r", "-t", "=crew-team-eng:0"]])
        r = self.crew("attach", "builder", "--project", self.team)  # control: a repo-scoped target still needs #REPO
        self.assertEqual(r.returncode, 1)
        self.assertIn("lists 3 repos; select one as %s#<repo>" % self.team, r.stdout)
        self.assertEqual(len(self.joins()), 1)


if __name__ == "__main__":
    unittest.main()
