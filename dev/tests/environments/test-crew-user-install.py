"""Tests for the user-level install (#1317) on a fake host whose HOME is a temp dir: `mdstack install` (refused
outside ~/.mdstack/releases/, a dry run writes nothing, the releases/current link and the launcher, a PATH link
into a user directory or the one line to add, never over another mdstack, idempotent), `mdstack --version`, the
doctor launcher and PATH rows (missing, stale, ok, resolves elsewhere), and `mdstack upgrade` through the launcher
(--latest takes the latest release's tag and refuses with --version; re-renders, flips releases/current so the
launcher follows, --version of the previous tag rolls back to the release on disk; a dry run flips nothing; the
other projects the install serves are upgraded first, including a prior-format install.json recovered from its
`Run mdstack up --project` step, and a failed or unrecoverable one keeps current). Run in CI.
"""
from argparse import Namespace
import importlib.util
import io
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bootstrap_tests", HERE / "test-crew-bootstrap.py")
bootstrap_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_tests)
spec = importlib.util.spec_from_loader("crew_cli", SourceFileLoader("crew_cli", CREW))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
install = cli.commands()["install"]


class UserInstall(bootstrap_tests.Bootstrap):
    share_bundle = False  # renames its bundle

    def setUp(self):
        super().setUp()
        self.root = Path(self.home) / ".mdstack"
        self.releases = self.root / "releases"
        self.releases.mkdir(parents=True)
        self.bundle = self.bundle.rename(self.releases / "mdstack-2.1.0")
        self.cli = self.bundle / "cli" / "mdstack"
        self.launcher = self.root / "bin" / "mdstack"
        self.tool("python3", 'exec %s "$@"' % sys.executable)  # the launcher runs cli/mdstack by its shebang
        self.tool("tmux", "exit 1")  # no live session, as the python fake tmux saw before python3 was on PATH

    def install(self, *args, cli=None):
        return subprocess.run([sys.executable, str(cli or self.cli), "install", *args], capture_output=True,
                              text=True, env=self.env)

    def run_launcher(self, *args):
        return subprocess.run([str(self.launcher), *args], input="", capture_output=True, text=True, env=self.env)

    def test_refused_outside_releases(self):
        r = self.install(cli=CREW)
        self.assertEqual(r.returncode, 1)
        self.assertIn("run mdstack install from a release bundle extracted into", r.stdout)
        self.assertFalse(self.launcher.exists())

    def test_dry_run_writes_nothing(self):
        r = self.install("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("would write link", r.stdout)
        self.assertIn("would write launcher " + str(self.launcher), r.stdout)
        self.assertFalse((self.releases / "current").is_symlink() or self.launcher.exists())

    def test_install_without_a_user_path_dir_prints_the_line(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.1.0")
        self.assertTrue(os.access(self.launcher, os.X_OK))
        self.assertIn('export PATH="$HOME/.mdstack/bin:$PATH"', r.stdout)
        v = self.run_launcher("--version")
        self.assertEqual((v.returncode, v.stdout), (0, "mdstack v2.1.0\n"), v.stderr)

    def test_install_links_into_a_user_path_dir_and_reruns_clean(self):
        local = Path(self.home) / ".local" / "bin"
        local.mkdir(parents=True)
        self.env["PATH"] = os.pathsep.join([self.bindir, str(local)])
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(Path(os.readlink(local / "mdstack")), self.launcher)
        self.assertNotIn("not on PATH", r.stdout)
        self.assertEqual(shutil.which("mdstack", path=self.env["PATH"]), str(local / "mdstack"))
        r = self.install()
        self.assertEqual(r.stdout, "crew install: no changes\n")

    def test_install_never_replaces_another_mdstack_on_path(self):
        local = Path(self.home) / ".local" / "bin"
        local.mkdir(parents=True)
        self.tool("mdstack", "echo other")
        self.env["PATH"] = os.pathsep.join([self.bindir, str(local)])
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((local / "mdstack").exists())
        self.assertIn("mdstack is not on PATH", r.stdout)
        self.assertEqual(Path(self.bindir, "mdstack").read_text(), "#!/bin/sh\necho other\n")

    def test_doctor_rows(self):
        r = self.doctor()
        self.assertEqual(self.rows(r)["launcher"], "warn")
        self.assertIn("missing", self.detail(r, "launcher"))
        self.assertEqual(self.rows(r)["mdstack on PATH"], "warn")
        self.assertEqual(self.install().returncode, 0)
        self.env["PATH"] = os.pathsep.join([str(self.launcher.parent), self.bindir])
        r = self.doctor()
        self.assertEqual((self.rows(r)["launcher"], self.rows(r)["mdstack on PATH"]), ("ok", "ok"), r.stdout)
        self.assertIn("-> mdstack-2.1.0", self.detail(r, "launcher"))
        self.env["PATH"] = os.pathsep.join([self.bindir, str(self.launcher.parent)])
        self.tool("mdstack", "echo other")
        self.launcher.write_text("#!/bin/sh\nexec /old/cli/mdstack \"$@\"\n")
        r = self.doctor()
        self.assertIn("stale", self.detail(r, "launcher"))
        self.assertIn("resolves to %s/mdstack, not the launcher" % self.bindir, self.detail(r, "mdstack on PATH"))

    def second_root(self, name="mdstack-b"):
        other = Path(self.home) / "crew-b"
        shutil.copytree(self.bundle, other / "releases" / "mdstack-2.1.0", symlinks=True)
        r = self.install("--name", name, cli=other / "releases" / "mdstack-2.1.0" / "cli" / "mdstack")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return other, other / "bin" / name

    def owner_config(self, launcher, **env):
        """The config a launcher's bare `doctor` resolves in an owner shell: no --project, no CREW_*/MDSTACK_*."""
        clean = {k: v for k, v in self.env.items() if not k.startswith(("CREW_", "MDSTACK_"))}
        r = subprocess.run([str(launcher), "doctor"], input="", capture_output=True, text=True, env=dict(clean, **env))
        line = next((x for x in r.stderr.splitlines() if x.startswith("mdstack: config ")), r.stdout + r.stderr)
        return line.removeprefix("mdstack: config ").split("#")[0]

    def test_a_non_default_root_launcher_reads_its_own_config(self):  # #2023 AC1-AC3
        other, launcher = self.second_root()
        self.assertEqual(self.install().returncode, 0)
        for root in (self.root, other):  # the default root's config is the decoy a bare launcher used to read
            shutil.copy(self.project, root / "config.toml")
        self.assertIn("CREW_ROOT=%s exec " % other, launcher.read_text())
        self.assertEqual(self.owner_config(launcher), str(other / "config.toml"))
        self.assertEqual(self.owner_config(launcher, MDSTACK_CONFIG=self.project), self.project)
        self.assertEqual(self.owner_config(launcher, CREW_PROJECT=self.project), self.project)
        self.assertNotIn("CREW_ROOT", self.launcher.read_text())
        self.assertEqual(self.owner_config(self.launcher), str(self.root / "config.toml"))

    def test_install_rewrites_a_stale_launcher(self):  # #2023 AC4
        other, launcher = self.second_root()
        fresh = launcher.read_text()
        launcher.write_text(install.LAUNCHER_HEAD + 'exec %s "$@"\n' % (other / "releases/current/cli/mdstack"))
        cli = other / "releases" / "mdstack-2.1.0" / "cli" / "mdstack"
        r = self.install("--name", "mdstack-b", "--dry-run", cli=cli)
        self.assertIn("would write launcher " + str(launcher), r.stdout)
        self.assertNotEqual(launcher.read_text(), fresh)
        r = self.install("--name", "mdstack-b", cli=cli)
        self.assertIn("wrote launcher " + str(launcher), r.stdout)
        self.assertEqual(launcher.read_text(), fresh)

    def test_upgrade_flips_current_and_rolls_back(self):
        self.real_git()
        subprocess.run(["git", "init", "-q", self.project_dir], check=True)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.bootstrap("--yes").returncode, 0)
        self.gh(["acme-bot", "acme-reviewer"], "v2.2.0")  # --latest reads this tag
        _, sha = self.release()
        new = self.releases / "mdstack-2.2.0"
        r = self.run_launcher("upgrade", "--project", self.project, "--version", "v2.2.0", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.1.0")
        r = self.run_launcher("upgrade", "--project", self.project, "--latest", "--version", "v2.2.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--latest needs the github source and no --version", r.stdout)
        r = self.run_launcher("upgrade", "--project", self.project, "--latest", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("releases/current -> mdstack-2.2.0", r.stdout)
        self.assertNotIn("write launcher", r.stdout)  # the ~/.mdstack launcher is current as written (#2023)
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.2.0")
        record = json.loads(self.manifest.read_text())
        self.assertEqual((record["tag"], record["source"], record["bundle_sha256"], record["project"]),
                         ("v2.2.0", str(new.resolve()), sha, self.project))
        self.assertEqual(self.run_launcher("--version").stdout, "mdstack v2.2.0\n")
        self.release("v2.1.0")  # rollback: the same bundle, already on disk, is fetched again and reused
        r = self.run_launcher("upgrade", "--project", self.project, "--version", "v2.1.0", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reusing matching " + str(self.bundle.resolve()), r.stdout)
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.1.0")
        self.assertEqual(self.run_launcher("--version").stdout, "mdstack v2.1.0\n")
        self.assertEqual(json.loads(self.manifest.read_text())["tag"], "v2.1.0")

    def test_a_second_root_installs_bootstraps_and_upgrades_apart(self):  # #1324 AC1, AC3
        self.real_git()
        subprocess.run(["git", "init", "-q", self.project_dir], check=True)
        local = Path(self.home) / ".local" / "bin"
        local.mkdir(parents=True)
        self.env["PATH"] = os.pathsep.join([self.bindir, str(local)])
        other = Path(self.home) / "crew-b"
        shutil.copytree(self.bundle, other / "releases" / "mdstack-2.1.0", symlinks=True)
        project = Path(self.project_dir) / "crew-b.toml"  # a project-level config beside the trusted checkout
        project.write_text(self.project_path.read_text().replace(str(Path(self.tmp) / "state"), str(other / "state"))
                           .replace(str(Path(self.tmp) / "live"), str(other / "live")))
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.bootstrap("--yes").returncode, 0)
        first = {p: (os.readlink(p) if p.is_symlink() else p.read_bytes()) for p in Path(self.home, ".mdstack").rglob("*")
                 if p.is_symlink() or p.is_file()}
        r = self.install("--name", "mdstack-b", cli=other / "releases" / "mdstack-2.1.0" / "cli" / "mdstack")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        launcher = other / "bin" / "mdstack-b"
        self.assertEqual(Path(os.readlink(local / "mdstack-b")), launcher)
        self.assertEqual(Path(os.readlink(local / "mdstack")), self.launcher)  # the first root keeps its name
        self.assertEqual(os.readlink(other / "releases" / "current"), "mdstack-2.1.0")
        b = lambda *a: subprocess.run([str(launcher), *a], input="", capture_output=True, text=True, env=self.env)
        self.assertEqual(b("doctor", "--project", str(project), "--fix").returncode, 0)  # its own state layout
        r = b("bootstrap", "--project", str(project), "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("mdstack: config %s\n" % project, r.stderr)
        self.release()
        fresh = launcher.read_text()  # a launcher from before #2023 pinned no root; upgrade rewrites it (AC4)
        launcher.write_text(install.LAUNCHER_HEAD + 'exec %s "$@"\n' % (other / "releases/current/cli/mdstack"))
        r = b("upgrade", "--project", str(project), "--version", "v2.2.0", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("would write launcher " + str(launcher), r.stdout)
        self.assertNotEqual(launcher.read_text(), fresh)
        r = b("upgrade", "--project", str(project), "--version", "v2.2.0", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("wrote launcher " + str(launcher), r.stdout)
        self.assertEqual(launcher.read_text(), fresh)
        self.assertEqual(os.readlink(other / "releases" / "current"), "mdstack-2.2.0")
        self.assertEqual(b("--version").stdout, "mdstack v2.2.0\n")
        self.release("v2.1.0")
        r = b("upgrade", "--project", str(project), "--version", "v2.1.0", "--yes")  # rollback, also apart
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(other / "releases" / "current"), "mdstack-2.1.0")
        self.assertEqual(json.loads((other / "state" / "acme__widgets" / "install.json").read_text())["tag"], "v2.1.0")
        self.assertEqual({p: (os.readlink(p) if p.is_symlink() else p.read_bytes())
                          for p in Path(self.home, ".mdstack").rglob("*") if p.is_symlink() or p.is_file()}, first)
        self.assertEqual(self.run_launcher("--version").stdout, "mdstack v2.1.0\n")
        self.env["PATH"] = os.pathsep.join([str(local), self.bindir])
        r = subprocess.run([str(launcher), "doctor", "--project", str(project)], capture_output=True, text=True,
                           env=dict(self.env, CREW_ROOT=str(other)))  # this profile sets no paths.root
        self.assertIn("ok    launcher           %s -> mdstack-2.1.0" % launcher, r.stdout)
        self.assertIn("ok    mdstack-b on PATH  %s" % (local / "mdstack-b"), r.stdout)


class LauncherText(unittest.TestCase):  # #2023 AC3: the ~/.mdstack launcher stays byte-identical
    def test_only_a_non_default_root_is_pinned(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            self.assertEqual(install.launcher_text(Path(home) / ".mdstack"),
                             "#!/bin/sh\n# mdstack launcher, written by mdstack install (#1317): runs the current "
                             'release.\nexec %s/.mdstack/releases/current/cli/mdstack "$@"\n' % home)
            self.assertEqual(install.launcher_text(Path(home) / "crew b"),
                             "#!/bin/sh\n# mdstack launcher, written by mdstack install (#1317): runs the current "
                             "release.\nCREW_ROOT='%s/crew b' exec '%s/crew b/releases/current/cli/mdstack' \"$@\"\n"
                             % (home, home))

    def test_a_stale_launcher_keeps_the_root_spelling_it_names(self):  # a re-exec'd bundle path is resolved
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HOME": tmp}):
            real, link = Path(tmp) / "real", Path(tmp) / "link"
            (real / "bin").mkdir(parents=True)
            link.symlink_to(real)
            (real / "bin" / "b").write_text(install.LAUNCHER_HEAD + 'exec %s/releases/current/cli/mdstack "$@"\n' % link)
            (real / "bin" / "other").write_text("#!/bin/sh\nexec true\n")
            self.assertEqual(install.stale_launchers(real), [(link / "bin" / "b", link)])
            install.write_launcher(link / "bin" / "b", link)
            self.assertIn("CREW_ROOT=%s exec " % link, (real / "bin" / "b").read_text())
            self.assertEqual(install.stale_launchers(real), [])


class Follow(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.releases = self.tmp / "releases"
        (self.releases / "mdstack-2.2.0").mkdir(parents=True)
        (self.releases / "mdstack-2.1.0").mkdir()
        (self.releases / "current").symlink_to("mdstack-2.1.0")
        self.projects = {}
        for name, source in (("primary", "mdstack-2.1.0"), ("other", "mdstack-2.1.0"), ("elsewhere", None)):
            project = self.tmp / name / "config.toml"
            project.parent.mkdir()
            project.write_text("x")
            self.projects[name] = str(project)
            state = self.tmp / "state" / ("acme__" + name)
            state.mkdir(parents=True)
            (state / "install.json").write_text(json.dumps(
                {"project": str(project), "source": str(self.releases / source) if source else "/opt/mdstack-2.1.0"}))
        resolved = {"paths.state_dir": str(self.tmp / "state")}
        patcher = mock.patch.object(install.crew_render, "resolve", return_value=(resolved, []))
        patcher.start()
        self.addCleanup(patcher.stop)

    def follow(self, returncode=0, dry_run=False):
        argv = ["python3", "cli/mdstack", "upgrade", "--project", self.projects["primary"], "--yes"]
        args = Namespace(project=self.projects["primary"], dry_run=dry_run, version="v2.2.0")
        with mock.patch.object(install.subprocess, "run", return_value=Namespace(returncode=returncode)) as run:
            code = install.follow(args, self.releases / "mdstack-2.2.0", argv, {})
        return code, [call.args[0][4] for call in run.call_args_list]

    def test_other_served_projects_then_current(self):
        self.assertEqual(install.served(self.projects["primary"], self.releases), ([self.projects["other"]], []))
        self.assertEqual(self.follow(), (0, [self.projects["other"]]))
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.2.0")

    def legacy(self, copy="x", project=None):
        """Rewrite the other project's install.json in the format before #1317: no `project` field."""
        state = self.tmp / "state" / "acme__other"
        (state / "install.json").write_text(json.dumps({"source": str(self.releases / "mdstack-2.1.0"),
                                                        "pending_human_steps": ["Run mdstack up --project %s" % (
                                                            project or self.projects["other"])]}))
        (state / "config.toml").write_text(copy)
        return str(state / "install.json")

    def test_a_prior_format_install_is_recovered_and_upgraded_before_current(self):  # R1
        self.legacy()
        self.assertEqual(install.served(self.projects["primary"], self.releases), ([self.projects["other"]], []))
        self.assertEqual(self.follow(), (0, [self.projects["other"]]))
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.2.0")

    def test_an_unrecoverable_prior_format_install_keeps_current(self):  # R1
        for manifest in (self.legacy(copy="edited since install"), self.legacy(project=self.tmp / "gone.toml")):
            self.assertEqual(install.served(self.projects["primary"], self.releases), ([], [manifest]))
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(self.follow(), (1, []))
            self.assertIn("no project file found for " + manifest, out.getvalue())
            self.assertIn("--version v2.2.0 --project <its config.toml>", out.getvalue())
            self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.1.0")

    def test_a_failed_project_or_dry_run_keeps_current(self):
        self.assertEqual(self.follow(returncode=1), (1, [self.projects["other"]]))
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.1.0")
        self.assertEqual(self.follow(dry_run=True)[0], 0)
        self.assertEqual(os.readlink(self.releases / "current"), "mdstack-2.1.0")

    def test_no_user_level_install_is_left_alone(self):
        (self.releases / "current").unlink()
        self.assertEqual(self.follow(), (0, []))
        self.assertFalse((self.releases / "current").is_symlink())


def load_tests(loader, tests, pattern):
    """Only this file's own tests, not the inherited bootstrap ones."""
    return unittest.TestSuite(case(name) for case in (UserInstall, Follow) for name in case.__dict__
                              if name.startswith("test_"))


if __name__ == "__main__":
    unittest.main()
