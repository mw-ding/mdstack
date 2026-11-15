"""Tests for mdstack layout and the paths.root resolver (#1178); fixtures in crew_testlib.py (stdlib only).

Covers: relative children resolve under paths.root from any caller cwd, CREW_ROOT overrides paths.root, a profile
without paths.root keeps its values, absolute children and placeholders stay as they are, --write writes runnable
start wrappers whose quoting survives spaces (start-owner in the profile directory, #1316), an unmarked wrapper file is
refused and left unchanged, and without --project the user-level ~/.mdstack/config.toml (or $MDSTACK_CONFIG) is the
profile, merged with state/, runs/ and live/ in one directory (#1316); $CREW_PROJECT outranks $MDSTACK_CONFIG, a
writing command names its config on stderr, and $CREW_ROOT moves the default config to <root>/config.toml (#1324).
Run in CI.
"""
import os
import shlex
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW, PROFILE


class Layout(Base):
    def write_root_profile(self, root, extra=""):
        text = PROFILE.format(runtime="tmux", engine="claude-code", state="x").replace(
            'state_dir = "x"\nworktree_root = "x/wt"\n',
            'root = "%s"\nstate_dir = ".crew/state"\nworktree_root = ".crew/runs/widgets"\nlive_dir = ".crew/live"\n'
            'mdstack = ".crew/state/acme__widgets/mdstack"\ncheckout = "mdstack"\n%s' % (root, extra))
        self.project_dir = os.path.join(root, "crew home")
        os.makedirs(self.project_dir, exist_ok=True)
        self.project = os.path.join(self.project_dir, "crew.toml")
        with open(self.project, "w") as f:
            f.write(text)

    def layout(self, *args, cwd=None, **env):
        r = subprocess.run([sys.executable, CREW, "layout",
                            "--project", self.project, *args], capture_output=True, text=True,
                           env=dict(self.env, **env), cwd=cwd or self.tmp)
        rows = dict(line.split(None, 1) for line in r.stdout.splitlines() if line and not line.startswith(("wrote", "crew:")))
        return r, rows

    def test_children_resolve_under_root_from_any_cwd(self):
        root = os.path.join(self.tmp, "my root")
        self.write_root_profile(root)
        seen = []
        for cwd in (self.tmp, "/"):
            r, rows = self.layout(cwd=cwd)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            seen.append(rows)
        self.assertEqual(seen[0], seen[1])
        rows = seen[0]
        self.assertEqual(rows["root"], root)
        self.assertEqual(rows["state"], os.path.join(root, ".crew/state/acme__widgets"))
        self.assertEqual(rows["worktree_root"], os.path.join(root, ".crew/runs/widgets"))
        self.assertEqual(rows["live_dir"], os.path.join(root, ".crew/live"))
        self.assertEqual(rows["checkout"], os.path.join(root, "mdstack"))
        self.assertEqual(rows["home"], os.path.join(root, "crew home"))
        self.assertEqual(rows["cli"], os.path.join(root, ".crew/state/acme__widgets/mdstack/cli/mdstack"))

    def test_crew_root_overrides_paths_root(self):
        self.write_root_profile(os.path.join(self.tmp, "old"))
        moved = os.path.join(self.tmp, "mdstack")
        r, rows = self.layout(CREW_ROOT=moved)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rows["root"], moved)
        self.assertEqual(rows["state"], os.path.join(moved, ".crew/state/acme__widgets"))
        self.assertEqual(rows["checkout"], os.path.join(moved, "mdstack"))

    def test_without_root_values_are_unchanged(self):
        r, rows = self.layout(CREW_ROOT=os.path.join(self.tmp, "ignored"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rows["root"], "(unset)")
        self.assertEqual(rows["state"], self.state)
        self.assertEqual(rows["worktree_root"], os.path.join(self.tmp, "state", "wt"))
        self.assertEqual(rows["checkout"], self.project_dir)

    def test_write_makes_runnable_quoted_wrappers(self):
        root = os.path.join(self.tmp, "my root")
        self.write_root_profile(root)
        cli = os.path.join(root, ".crew/state/acme__widgets/mdstack/cli/mdstack")
        os.makedirs(os.path.dirname(cli))
        with open(cli, "w") as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        os.chmod(cli, 0o755)
        os.makedirs(os.path.join(root, "mdstack"))
        r, _ = self.layout("--write", "--owner-cmd", "pwd")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        start = os.path.join(root, "crew home", "start")
        owner = os.path.join(root, "crew home", "start-owner")
        self.assertIn("wrote " + start, r.stdout)
        self.assertIn("wrote " + owner, r.stdout)
        out = subprocess.run([start, "--coordinator-only"], capture_output=True, text=True, cwd="/").stdout
        self.assertEqual(out.splitlines(), ["start", "--project", self.project, "--coordinator-only"])  # #1919
        out = subprocess.run([owner], capture_output=True, text=True, cwd="/").stdout
        self.assertEqual(os.path.realpath(out.strip()), os.path.realpath(os.path.join(root, "mdstack")))
        self.assertEqual(self.layout("--write")[0].returncode, 0)  # its own files are rewritten
        r, _ = self.layout("--write")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(start) as f:
            text = f.read()
        self.assertIn("# Generated by mdstack layout", text)
        self.assertIn(shlex.quote(cli) + " start --project", text)

    def test_write_refuses_an_unmarked_file(self):
        root = os.path.join(self.tmp, "root")
        self.write_root_profile(root)
        start = os.path.join(root, "crew home", "start")
        with open(start, "w") as f:
            f.write("#!/bin/sh\necho mine\n")
        r, _ = self.layout("--write")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("refusing layout --write", r.stdout)
        with open(start) as f:
            self.assertEqual(f.read(), "#!/bin/sh\necho mine\n")
        self.assertFalse(os.path.exists(os.path.join(root, "crew home", "start-owner")))

    def write_user_config(self, home):
        """The default one-root layout: ~/.mdstack/config.toml with state/, runs/ and live/ beside it (#1316)."""
        text = PROFILE.format(runtime="tmux", engine="claude-code", state="x").replace(
            'state_dir = "x"\nworktree_root = "x/wt"\n',
            'root = "~/.mdstack"\nstate_dir = "state"\nworktree_root = "runs/widgets"\nlive_dir = "live"\n'
            'mdstack = "state/acme__widgets/mdstack"\ncheckout = "~/widgets"\n')
        os.makedirs(os.path.join(home, ".mdstack"))
        with open(os.path.join(home, ".mdstack", "config.toml"), "w") as f:
            f.write(text)

    def test_user_level_config_is_the_default(self):  # #1316 AC3, AC5, AC7
        home = os.path.join(self.tmp, "home")
        self.write_user_config(home)
        r = subprocess.run([sys.executable, CREW, "layout"], capture_output=True, text=True,
                           env=dict(self.env, HOME=home), cwd="/")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = dict(line.split(None, 1) for line in r.stdout.splitlines())
        root = os.path.join(home, ".mdstack")
        self.assertEqual(rows["root"], root)
        self.assertEqual(rows["home"], root)
        self.assertEqual(rows["state"], os.path.join(root, "state", "acme__widgets"))
        self.assertEqual(rows["worktree_root"], os.path.join(root, "runs", "widgets"))
        self.assertEqual(rows["live_dir"], os.path.join(root, "live"))
        self.assertEqual(rows["mdstack"], os.path.join(root, "state", "acme__widgets", "mdstack"))
        self.assertEqual(rows["checkout"], os.path.join(home, "widgets"))
        r = subprocess.run([sys.executable, CREW, "layout"], capture_output=True, text=True,
                           env=dict(self.env, HOME=home, MDSTACK_CONFIG=self.project), cwd="/")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("state         %s" % self.state, r.stdout)  # MDSTACK_CONFIG beats the user-level file
        r = subprocess.run([sys.executable, CREW, "layout", "--project", os.path.join(root, "config.toml")],
                           capture_output=True, text=True, env=dict(self.env, HOME=home, MDSTACK_CONFIG=self.project))
        self.assertIn("home          %s" % root, r.stdout)  # --project beats both

    def test_explicit_config_outranks_the_user_level_one_and_crew_root_moves_it(self):  # #1324 AC1, AC2
        home = os.path.join(self.tmp, "home")
        self.write_user_config(home)
        user = os.path.join(home, ".mdstack", "config.toml")
        r = subprocess.run([sys.executable, CREW, "layout"], capture_output=True, text=True, cwd="/",
                           env=dict(self.env, HOME=home, CREW_PROJECT=self.project, MDSTACK_CONFIG=user))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("state         %s" % self.state, r.stdout)  # a role window's CREW_PROJECT beats both
        self.assertIn("mdstack: config %s\n" % self.project, r.stderr)
        r = subprocess.run([sys.executable, CREW, "layout", "--project", self.project], capture_output=True,
                           text=True, cwd="/", env=dict(self.env, HOME=home))
        self.assertIn("state         %s" % self.state, r.stdout)
        self.assertEqual(r.stderr, "mdstack: config %s\n" % self.project)
        other = os.path.join(self.tmp, "crew-b")
        os.makedirs(other)
        shutil.copyfile(user, os.path.join(other, "config.toml"))
        r = subprocess.run([sys.executable, CREW, "layout"], capture_output=True, text=True, cwd="/",
                           env=dict(self.env, HOME=home, CREW_ROOT=other))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = dict(line.split(None, 1) for line in r.stdout.splitlines())
        self.assertEqual((rows["root"], rows["state"]), (other, os.path.join(other, "state", "acme__widgets")))
        self.assertIn("mdstack: config %s\n" % os.path.join(other, "config.toml"), r.stderr)

    def test_shipped_tmux_profile_defaults_to_the_one_root_layout(self):  # #1316 AC1
        home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(home, ".mdstack"))
        with open(os.path.join(os.path.dirname(os.path.dirname(CREW)), "profiles", "tmux.toml")) as f:
            text = f.read().replace("<author-login>", "acme-bot")
        with open(os.path.join(home, ".mdstack", "config.toml"), "w") as f:
            f.write('[repo]\nowner = "acme"\nname = "widgets"\n\n' + text)
        r = subprocess.run([sys.executable, CREW, "layout"], capture_output=True, text=True,
                           env=dict(self.env, HOME=home), cwd="/")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = dict(line.split(None, 1) for line in r.stdout.splitlines())
        root = os.path.join(home, ".mdstack")
        self.assertEqual((rows["root"], rows["home"]), (root, root))
        self.assertEqual(rows["state"], os.path.join(root, "state", "acme__widgets"))
        self.assertEqual(rows["worktree_root"], os.path.join(root, "runs", "widgets"))
        self.assertEqual(rows["live_dir"], os.path.join(root, "live"))
        self.assertEqual(rows["mdstack"], os.path.join(root, "state", "acme__widgets", "mdstack"))
        self.assertEqual(rows["checkout"], os.path.join(home, "widgets"))

    def test_missing_user_level_config_fails_without_fallback(self):  # #1316 AC9
        home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(home, ".mdstack"))
        with open(os.path.join(home, ".mdstack", "crew.toml"), "w") as f:
            f.write(PROFILE.format(runtime="tmux", engine="claude-code", state="x"))
        r = subprocess.run([sys.executable, CREW, "layout"], capture_output=True, text=True,
                           env=dict(self.env, HOME=home), cwd="/")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(os.path.join(home, ".mdstack", "config.toml"), r.stdout)


if __name__ == "__main__":
    unittest.main()
