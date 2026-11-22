"""Upgrade tests: fake-host CLI install transitions and in-flight/reload checks without live sessions."""
from argparse import Namespace
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW

spec = importlib.util.spec_from_file_location("bootstrap_tests", Path(__file__).with_name("test-crew-bootstrap.py"))
bootstrap_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_tests)
# The extensionless CLI uses the source loader.
spec = importlib.util.spec_from_loader("crew_cli", SourceFileLoader("crew_cli", CREW))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
upgrade = cli.commands()["upgrade"]


class Upgrade(bootstrap_tests.Bootstrap):
    share_bundle = False  # edits its bundle

    def test_reload_cursor_coordinator_preserves_harness(self):
        values = {"engines.coordinator": "cursor", "runtime.options.permission_mode": "bypass"}
        with mock.patch.object(upgrade, "runs", return_value=[]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]), \
                mock.patch.object(upgrade, "stop_pane", return_value=None), \
                mock.patch.object(upgrade, "window_env", return_value={}), \
                mock.patch.object(upgrade, "role_notes", return_value=""), \
                mock.patch.object(upgrade.tmux.backends["tmux"], "tmux", return_value=Namespace(returncode=0)) as respawn, \
                mock.patch.object(upgrade, "wait_harness") as wait:
            upgrade.reload(values, "session", self.state, Namespace(project=self.project, timeout=1), [(0, "ash")])
        self.assertIn('exec cursor-agent --force "Read your brief at $CREW_BRIEF and follow it."', respawn.call_args_list[1].args[-1])
        wait.assert_called_once_with("session", 0, "ash", "cursor-agent", 1)

    def test_reload_pi_coordinator_preserves_harness(self):
        values = {"engines.coordinator": "pi", "runtime.options.permission_mode": "bypass"}
        with mock.patch.object(upgrade, "runs", return_value=[]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]), \
                mock.patch.object(upgrade, "stop_pane", return_value=None), \
                mock.patch.object(upgrade, "window_env", return_value={}), \
                mock.patch.object(upgrade, "role_notes", return_value=""), \
                mock.patch.object(upgrade.tmux.backends["tmux"], "tmux", return_value=Namespace(returncode=0)) as respawn, \
                mock.patch.object(upgrade, "wait_harness") as wait:
            upgrade.reload(values, "session", self.state, Namespace(project=self.project, timeout=1), [(0, "ash")])
        self.assertIn('exec pi --approve "Read your brief at $CREW_BRIEF and follow it."', respawn.call_args_list[1].args[-1])
        wait.assert_called_once_with("session", 0, "ash", "pi", 1)

    def setUp(self):
        super().setUp()
        self.real_git()
        subprocess.run(["git", "init", "-q", self.project_dir], check=True)
        result = self.bootstrap("--yes", "--harness", "codex")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def upgrade(self, *args):
        return subprocess.run([sys.executable, str(self.cli), "upgrade", "--project", self.project, *args],
                              input="", capture_output=True, text=True, env=self.env)

    def test_no_change_writes_nothing(self):
        before = self.manifest.stat().st_mtime_ns
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no changes", result.stdout)
        self.assertEqual(self.manifest.stat().st_mtime_ns, before)
        self.assertEqual(self.calls(), [])

    def test_rules_changed_preview_and_apply(self):
        source = self.bundle / "templates/runtimes/tmux/builder.md"
        source.write_text(source.read_text() + "\nNew reviewed rule.\n")
        before = self.manifest.read_bytes()
        result = self.upgrade("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("+New reviewed rule.", result.stdout)
        self.assertEqual(self.manifest.read_bytes(), before)
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("New reviewed rule.", (Path(self.state) / "render/runtime/builder.md").read_text())

    def test_core_memory_near_its_limits_upgrades_and_deploys(self):  # #1230 review R1; #1537 remote revision
        checkout, upstream, origin = Path(self.project).parent, Path(self.tmp) / "upstream", Path(self.tmp) / "origin.git"
        git = ["git", "-c", "user.name=t", "-c", "user.email=t"]
        subprocess.run(git + ["init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        subprocess.run(git + ["clone", "-q", str(origin), str(upstream)], check=True, capture_output=True)
        memory = upstream / "memory"
        (memory / "roles").mkdir(parents=True)
        (memory / "owner.md").write_text("# Owner\n\n" + "A" * 2980 + "\n")
        (memory / "roles/coordinator.md").write_text("# C\n\n" + "B" * 1990 + "\n")
        for args in (["add", "-A"], ["commit", "-q", "-m", "memory"], ["push", "-q", "origin", "HEAD:main"]):
            subprocess.run(git + ["-C", str(upstream)] + args, check=True)
        subprocess.run(git + ["-C", str(checkout), "remote", "add", "origin", str(origin)], check=True)  # never pulled
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("exceeds", result.stdout)
        brief = (Path(self.state) / "render/runtime/coordinator.md").read_text()
        self.assertIn("\n## Core memory\n", brief)
        self.assertIn("B" * 1990, brief)

    def test_pin_changed_with_same_rules(self):
        (self.bundle / "VERSION").write_text("v2.2.0\n")
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.manifest.read_text())["tag"], "v2.2.0")

    def test_pack_version_only_change_updates_record(self):
        self.pack_version("0.5.0")
        self.assertEqual(self.bootstrap("--yes").returncode, 0)
        self.assertIn("crew upgrade: no changes", self.upgrade("--yes").stdout)
        self.pack_version("0.6.0")
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("no changes", result.stdout)
        record = json.loads(self.manifest.read_text())
        self.assertEqual((record["tag"], record["pack"]), ("v2.1.0", {"name": "github", "version": "0.6.0"}))
        self.assertIn("no changes", self.upgrade("--yes").stdout)

    def test_pack_toml_framework_and_commit_pin(self):
        """#1236: install records the pack.toml pack's commit; upgrade re-plans on a new commit and refuses a dirty
        checkout or a framework range that excludes the installed tag."""
        pack = Path(self.tmp) / "plugin-pack"
        shutil.copytree(Path(__file__).resolve().parents[1] / "core/fixtures/packs/example", pack)

        def commit(framework):
            text = (pack / "pack.toml").read_text()
            (pack / "pack.toml").write_text(re.sub(r'framework = ".*"', 'framework = "%s"' % framework, text))
            git = ["git", "-C", str(pack), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            subprocess.run(git + ["init", "-q"], check=True)
            subprocess.run(git + ["add", "-A"], check=True)
            subprocess.run(git + ["commit", "-qm", framework], check=True)
            return subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        head = commit(">=2.0.0, <3.0.0")
        self.project_path.write_text(self.project_path.read_text() +
                                     'pack = "%s"\n' % os.path.relpath(pack, self.project_path.parent))
        result = self.bootstrap("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.manifest.read_text())["pack"], {
            "name": "example", "version": "0.1.0", "framework": ">=2.0.0, <3.0.0", "commit": head})
        self.assertIn("no changes", self.upgrade("--yes").stdout)
        head = commit(">=2.1.0, <3.0.0")
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.manifest.read_text())["pack"]["commit"], head)
        (pack / "profile.toml").write_text("")
        result = self.upgrade("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has uncommitted changes", result.stdout + result.stderr)
        before = self.manifest.read_bytes()
        commit(">=3.0.0")
        result = self.upgrade("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("pack example supports mdstack >=3.0.0; v2.1.0 is incompatible", result.stdout + result.stderr)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_pack_toml_declared_vcs_commit_pin(self):
        """#1326: a pack in a non-git working copy pins through its declared [vcs] commands; a dirty one is refused."""
        pack = Path(self.tmp) / "vcs-pack"
        shutil.copytree(Path(__file__).resolve().parents[1] / "core/fixtures/packs/example", pack)
        fake = [sys.executable, str(Path(__file__).resolve().parents[1] / "core/fixtures/vcs/fake-vcs.py")]
        text = re.sub(r'framework = ".*"', 'framework = ">=2.0.0, <3.0.0"', (pack / "pack.toml").read_text())
        (pack / "pack.toml").write_text(text + "\n[vcs]\nclean = %s\ncommit = %s\n" % (
            json.dumps(fake + ["status"]), json.dumps(fake + ["rev"])))
        subprocess.run(fake + ["commit"], cwd=pack, check=True)
        rev = json.loads((pack / ".fakevcs/state.json").read_text())["rev"]
        self.project_path.write_text(self.project_path.read_text() +
                                     'pack = "%s"\n' % os.path.relpath(pack, self.project_path.parent))
        result = self.bootstrap("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.manifest.read_text())["pack"]["commit"], rev)
        (pack / "profile.toml").write_text("")
        result = self.upgrade("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has uncommitted changes", result.stdout + result.stderr)

    def test_pack_toml_verified_export(self):
        """#1962: bootstrap installs an exported pack whose pack.lock verifies and records its commit; a modified
        export is refused naming the path, and a plain directory without a lock keeps today's refusal."""
        pack, export = Path(self.tmp) / "checkout-pack", Path(self.tmp) / "export-pack"
        shutil.copytree(Path(__file__).resolve().parents[1] / "core/fixtures/packs/example", pack)
        text = re.sub(r'framework = ".*"', 'framework = ">=2.0.0, <3.0.0"', (pack / "pack.toml").read_text())
        (pack / "pack.toml").write_text(text)
        git = ["git", "-C", str(pack), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "pack"]):
            subprocess.run(git + args, check=True)
        head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        shutil.copytree(pack, export, ignore=shutil.ignore_patterns(".git"))
        self.project_path.write_text(self.project_path.read_text() +
                                     'pack = "%s"\n' % os.path.relpath(export, self.project_path.parent))
        result = self.bootstrap("--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not a git checkout; install pins a pack at a commit", result.stdout + result.stderr)
        lock = subprocess.run([sys.executable, str(Path(CREW).parents[1] / "core/crew-pack.py"), "lock", str(pack),
                               str(export)], capture_output=True, text=True)
        self.assertEqual(lock.returncode, 0, lock.stdout + lock.stderr)
        result = self.bootstrap("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.manifest.read_text())["pack"], {
            "name": "example", "version": "0.1.0", "framework": ">=2.0.0, <3.0.0", "commit": head})
        self.assertIn("no changes", self.upgrade("--yes").stdout)
        before = self.manifest.read_bytes()
        (export / "profile.toml").write_text("")
        result = self.bootstrap("--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match its pack.lock: profile.toml is changed", result.stdout + result.stderr)
        self.assertEqual(self.manifest.read_bytes(), before)

    mirror_release = bootstrap_tests.ReleaseSources.mirror_release
    source = bootstrap_tests.ReleaseSources.source

    def test_source_change_without_version_is_refused(self):
        before = self.manifest.read_bytes()
        mirror = Path(self.tmp) / "mirror"
        self.source("mirror", mirror)
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("install source changed to mirror %s; this bundle was not fetched from it" % mirror, result.stdout)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_version_fetch_from_mirror_records_transport_then_no_changes(self):
        self.mirror, self.gh_log = Path(self.tmp) / "mirror", Path(self.tmp) / "gh.log"
        destination, sha = self.mirror_release()
        self.source("mirror", self.mirror)
        result = self.upgrade("--version", "v2.2.0", "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads(self.manifest.read_text())
        self.assertEqual((record["tag"], record["bundle_sha256"], record["transport"]["kind"]), ("v2.2.0", sha, "mirror"))
        self.cli = destination / "cli/mdstack"
        self.assertIn("crew upgrade: no changes", self.upgrade("--yes").stdout)
        self.assertFalse(self.gh_log.exists())

    def test_version_after_dry_run_reuses_verified_bundle_and_records_transport(self):
        """#1089: --dry-run leaves the bundle extracted; --yes and later retries re-verify it and keep provenance."""
        self.mirror, self.gh_log = Path(self.tmp) / "mirror", Path(self.tmp) / "gh.log"
        destination, sha = self.mirror_release()
        self.source("mirror", self.mirror)
        result = self.upgrade("--version", "v2.2.0", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(destination.is_dir())
        (destination / "scripts/__pycache__").mkdir(exist_ok=True)
        (destination / "scripts/__pycache__/x.pyc").write_bytes(b"cache")
        result = self.upgrade("--version", "v2.2.0", "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("reusing matching %s" % destination.resolve(), result.stdout)
        record = json.loads(self.manifest.read_text())
        self.assertEqual((record["tag"], record["bundle_sha256"], record["transport"]["kind"]), ("v2.2.0", sha, "mirror"))
        # A record that lost its provenance (the old direct-run hint) is repaired by --version, not looped.
        del record["transport"]
        record["bundle_sha256"] = None
        self.manifest.write_text(json.dumps(record))
        self.cli = destination / "cli/mdstack"
        self.assertIn("install source changed to mirror", self.upgrade("--dry-run").stdout)
        result = self.upgrade("--version", "v2.2.0", "--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads(self.manifest.read_text())
        self.assertEqual((record["bundle_sha256"], record["transport"]["kind"]), (sha, "mirror"))
        self.assertIn("crew upgrade: no changes", self.upgrade("--yes").stdout)
        self.assertFalse(list(Path(self.tmp).glob(".crew-refetch-*")))
        self.assertFalse(self.gh_log.exists())

    def test_adopts_a_verified_user_level_install_without_a_record(self):  # #1616
        self.manifest.unlink()
        result = self.upgrade("--yes")  # negative control: no releases/current beside the bundle
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("foreign layout", result.stdout)
        self.assertFalse(self.manifest.exists())
        (self.bundle.parent / "current").symlink_to(self.bundle.name, target_is_directory=True)
        result = self.upgrade("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("would adopt the v2.1.0 install", result.stdout)
        self.assertFalse(self.manifest.exists())
        source = self.bundle / "templates/runtimes/tmux/builder.md"
        source.write_text(source.read_text() + "\nNew reviewed rule.\n")
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("adopted the v2.1.0 install", result.stdout)
        record = json.loads(self.manifest.read_text())  # the upgrade's bootstrap rewrote the adopted record
        self.assertEqual((record["tag"], record["status"], record["source"]), ("v2.1.0", "installed", str(self.bundle.resolve())))
        self.assertIn("New reviewed rule.", (Path(self.state) / "render/runtime/builder.md").read_text())
        self.assertIn("crew upgrade: no changes", self.upgrade("--yes").stdout)  # no refuse/bootstrap loop

    def test_unverified_install_without_a_record_is_not_adopted(self):  # #1616
        self.manifest.unlink()
        (self.bundle.parent / "current").symlink_to(self.bundle.name, target_is_directory=True)
        state = Path(self.state)
        empty = Path(self.tmp) / "mdstack-v0.0.0"
        empty.mkdir()
        cases = [("VERSION mismatch", lambda: (state / "VERSION").write_text("v2.0.0\n"),
                  lambda: (state / "VERSION").write_text("v2.1.0\n")),
                 ("mismatched project", lambda: (state / "config.toml").write_text("# other\n"),
                  lambda: (state / "config.toml").write_bytes(Path(self.project).read_bytes())),
                 ("missing release", lambda: ((state / "mdstack").unlink(), (state / "mdstack").symlink_to(empty)),
                  lambda: ((state / "mdstack").unlink(), (state / "mdstack").symlink_to(self.bundle)))]
        for message, break_it, restore in cases:
            with self.subTest(message):
                break_it()
                result = self.upgrade("--yes")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("does not verify: " + message, result.stdout)
                self.assertFalse(self.manifest.exists())
                restore()
        self.assertEqual(self.upgrade("--dry-run").returncode, 0)  # positive control once restored

    def test_upgrade_deploys_without_harness_pointers(self):
        record = json.loads(self.manifest.read_text())
        record["harnesses"] = []
        record["targets"] = {p: sha for p, sha in record["targets"].items()
                             if not Path(p).is_relative_to(Path(self.state) / "render")}
        self.manifest.write_text(json.dumps(record))
        (self.bundle / "VERSION").write_text("v2.2.0\n")
        source = self.bundle / "templates/runtimes/tmux/builder.md"
        source.write_text(source.read_text() + "\nNew reviewed rule.\n")
        result = self.upgrade("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.manifest.read_text())["self_test"]["deploy"], "ok")
        self.assertIn("New reviewed rule.", (Path(self.state) / "render/runtime/builder.md").read_text())

    def test_session_profile_applies_without_tmux(self):  # #1541
        record = json.loads(self.manifest.read_text())
        record["harnesses"] = []
        self.manifest.write_text(json.dumps(record))
        self.project_path.write_text(self.project_path.read_text().replace('name = "tmux"', 'name = "session"'))
        result = self.bootstrap("--yes")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.tool("tmux", 'case "$1" in -L|-S) shift 2;; esac; case "$1" in list-windows) echo "10 ben-7";; esac')
        source = self.bundle / "templates/runtimes/session/builder.md"
        source.write_text(source.read_text() + "\nNew reviewed rule.\n")
        before = self.manifest.read_bytes()
        result = self.upgrade("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("+New reviewed rule.", result.stdout)
        self.assertEqual(self.manifest.read_bytes(), before)
        result = self.upgrade("--yes", "--wait-timeout", "0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("in-flight", result.stdout)
        self.assertIn("session runtime: restart the coordinator", result.stdout)
        self.assertIn("New reviewed rule.", (Path(self.tmp) / "live/runtime/builder.md").read_text())
        self.assertEqual(json.loads(self.manifest.read_text())["runtime"], "session")
        self.assertIn("no changes", self.upgrade("--yes").stdout)

    def test_inflight_timeout_leaves_install_untouched(self):
        (self.bundle / "VERSION").write_text("v2.2.0\n")
        self.tool("tmux", 'case "$1" in -L|-S) shift 2;; esac; case "$1" in list-windows) echo "10 ben-7";; esac')
        before = self.manifest.read_bytes()
        result = self.upgrade("--yes", "--wait-timeout", "0")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("in-flight pass ben-7", result.stdout)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_waits_then_applies_and_reloads(self):
        args = Namespace(project=self.project, org_profile=None, version=None, dev=False, pre=False,
                         uninstall=False, remove_labels=False, routines_removed=False, smoke=False,
                         dry_run=False, yes=True, wait_timeout=5, timeout=1)
        bootstrap = cli.commands()["bootstrap"]
        values, _ = cli.crew_render.resolve(self.project, None)
        with mock.patch.object(upgrade, "profile", return_value=(values, "session", self.state)), \
                mock.patch.object(upgrade, "require_ownership", return_value=True), \
                mock.patch.object(bootstrap, "source", return_value="v2.2.0"), \
                mock.patch.object(bootstrap, "run", return_value=0) as apply, \
                mock.patch.object(upgrade, "busy", side_effect=["ben-7", None]) as busy, \
                mock.patch.object(upgrade, "reload") as reload, \
                mock.patch.object(upgrade, "time", mock.Mock(wraps=upgrade.time, sleep=mock.Mock())) as clock, \
                mock.patch.object(cli.commands()["down"], "stop_watcher", return_value=None) as stop, \
                mock.patch.object(cli.commands()["up"], "watcher") as start, \
                mock.patch.dict(os.environ, self.env):
            sleep = clock.sleep  # upgrade's own wait only: render's git calls poll the real time.sleep (#1537)
            calls = mock.Mock()
            calls.attach_mock(stop, "stop"), calls.attach_mock(reload, "reload"), calls.attach_mock(start, "start")
            self.assertEqual(upgrade.run(args), 0)
            self.assertEqual(busy.call_count, 2)
            sleep.assert_called_once_with(0.2)
            self.assertEqual(apply.call_count, 2)
            reload.assert_called_once()
            # #1346: the watcher is stopped before the install and started again after the reload
            self.assertEqual([c[0] for c in calls.mock_calls], ["stop", "reload", "start"])
            apply.reset_mock(), start.reset_mock()
            stop.return_value = 4242
            busy.side_effect = [None]
            self.assertEqual(upgrade.run(args), 1)  # a watcher outliving its grace: nothing installed
            self.assertEqual(apply.call_count, 1)  # the dry run only
            start.assert_not_called()

    def test_upgrade_stops_a_lock_holding_watcher_whose_pid_file_was_lost(self):  # #1346 review R2
        wake = Path(self.state) / "wake"
        wake.mkdir(parents=True, exist_ok=True)
        code = ("import fcntl, os, sys, time\nf = open(sys.argv[1], 'w')\nfcntl.flock(f, fcntl.LOCK_EX)\n"
                "f.write('%d\\n' % os.getpid()); f.flush()\nprint('ready', flush=True)\ntime.sleep(60)\n")
        holder = subprocess.Popen([sys.executable, "-c", code, str(wake / "watcher.lock"), "watch"],
                                  stdout=subprocess.PIPE, text=True)  # a watcher with no wake/watcher.pid
        self.addCleanup(lambda: holder.poll() is None and holder.kill())
        self.assertEqual(holder.stdout.readline(), "ready\n")
        args = Namespace(project=self.project, org_profile=None, version=None, dev=False, pre=False,
                         uninstall=False, remove_labels=False, routines_removed=False, smoke=False,
                         dry_run=False, yes=True, wait_timeout=5, timeout=1)
        bootstrap = cli.commands()["bootstrap"]
        values, _ = cli.crew_render.resolve(self.project, None)
        installs = []

        def apply(a):  # the real install runs only once the watcher exited
            if a.dry_run:
                installs.append(True)
                return 0
            try:  # the lock frees before the exiting holder is reapable, so poll() can still see it (#1654)
                installs.append(holder.wait(timeout=5))
            except subprocess.TimeoutExpired:
                installs.append(None)  # never stopped: it sleeps 60 s
            return 0
        with mock.patch.object(upgrade, "profile", return_value=(values, "session", self.state)), \
                mock.patch.object(upgrade, "require_ownership", return_value=True), \
                mock.patch.object(bootstrap, "source", return_value="v2.2.0"), \
                mock.patch.object(bootstrap, "run", side_effect=apply), \
                mock.patch.object(upgrade, "busy", return_value=None), \
                mock.patch.object(upgrade, "reload"), \
                mock.patch.object(cli.commands()["up"], "watcher"), \
                mock.patch.dict(os.environ, dict(self.env, PATH=self.env["PATH"] + os.pathsep + "/bin")):  # ps
            self.assertEqual(upgrade.run(args), 0)
        self.assertEqual(installs, [True, -15])  # the dry run, then the install after SIGTERM

    def test_active_pane_waits_after_terminal_status(self):
        self.put("status/ben-7.status", "done: #7 #9 head\n")
        with mock.patch.object(upgrade, "runs", return_value=[("ben-7", {"role": "builder"})]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]), \
                mock.patch.object(upgrade.tmux, "pane", return_value={"pid": "123", "command": "claude"}), \
                mock.patch.object(upgrade.proc, "live_child", return_value=False):
            for screen in ("✽ Recombobulating… (5s · ↓ 159 tokens)", "Working (esc to interrupt)"):
                with mock.patch.object(upgrade.tmux, "capture", return_value=screen):
                    self.assertEqual(upgrade.busy({}, self.state, "session", [(10, "ben-7")]), "ben-7: harness mid-turn")

    def test_unacked_inbox_after_terminal_status_waits(self):
        self.put("status/ben-7.status", "done: #7 #9 head\n")
        with mock.patch.object(upgrade, "runs", return_value=[("ben-7", {"role": "builder"})]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]):
            for kind in ("fix", "owner-policy"):
                with self.subTest(kind=kind):
                    self.put("inbox/ben-7.jsonl", json.dumps({"id": "m1", "kind": kind, "refs": []}) + "\n")
                    self.assertEqual(upgrade.busy({}, self.state, "session", [(10, "ben-7")]),
                                     "ben-7: unacknowledged inbox message")

    def test_adapter_without_composer_keeps_the_live_child_rule(self):
        self.put("status/ben-7.status", "done: #7 #9 head\n")
        with mock.patch.object(upgrade, "runs", return_value=[("ben-7", {"role": "builder", "harness": "pi"})]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]), \
                mock.patch.object(upgrade.tmux, "pane", return_value={"pid": "123", "command": "pi"}), \
                mock.patch.object(upgrade.tmux, "capture", return_value="Loading…\n"):
            for child, expected in ((True, "ben-7: live child process"), (False, None)):
                with mock.patch.object(upgrade.proc, "live_child", return_value=child):
                    self.assertEqual(upgrade.busy({}, self.state, "session", [(10, "ben-7")]), expected)

    def wrapper_upgrade(self, screen, ps_fails=False, child=True, before=None):
        """upgrade --yes through the CLI: window 0's pane is a launcher wrapper (a real sleep in its own session) whose
        live child is a session leader that is not the harness executable (the native harness, #1618)."""
        (self.bundle / "VERSION").write_text("v2.2.0\n")
        pids = []
        for _ in range(2):  # orphaned, so the stop on reload leaves no zombie holding the process group
            pid = int(subprocess.run([sys.executable, "-c", "import subprocess as s; print(s.Popen(['sleep', '60'], "
                                      "start_new_session=True, stdin=s.DEVNULL, stdout=s.DEVNULL, stderr=s.DEVNULL).pid)"],
                                     capture_output=True, text=True).stdout)  # no inherited pipe: run returns at once
            self.addCleanup(lambda pid=pid: subprocess.run(["kill", "-9", str(pid)], capture_output=True))
            pids.append(pid)
        (Path(self.tmp) / "screen.txt").write_text(screen)
        self.tool("tmux", 'case "$1" in -L|-S) shift 2;; esac\ncase "$1" in\nlist-windows) echo "0 ash";;\n'
                  'display-message) case "$*" in *pane_id*) echo "%%1 %d 0 0 /dev/ttys999 claude";; *cursor*) ;; '
                  '*) echo claude;; esac;;\ncapture-pane) while IFS= read -r l; do printf "%%s\\n" "$l"; done < %s;;\nesac' % (pids[0], Path(self.tmp) / "screen.txt"))
        tree = 'echo "%d 1 Ss claude"' % pids[0] + ('; echo "%d %d Ss node"' % (pids[1], pids[0]) if child else "")
        self.tool("ps", "exit 1" if ps_fails else 'case "$1" in -axo) %s;; *) echo "S+ claude";; esac' % tree)
        if before:
            before()
        installed = self.manifest.read_bytes()
        result = self.upgrade("--yes", "--wait-timeout", "0")
        return result, self.manifest.read_bytes() != installed

    def test_undelivered_coordinator_message_waits_until_acked(self):
        screen = Path(self.tmp) / "screen.txt"
        sent = []

        def send_into_dialog():  # mdstack send while a dialog is up: nothing typed, exit 4; then the dialog clears
            screen.write_text("Do you trust the files in this folder?\n❯ 1. Yes\nEnter to confirm · Esc to cancel\n")
            sent.append(subprocess.run([sys.executable, str(self.cli), "send", "ash", "blocked", "#7", "--project",
                                        self.project], input="", capture_output=True, text=True, env=self.env))
            screen.write_text("────\n❯\u00a0\n────\n")
        result, written = self.wrapper_upgrade("", before=send_into_dialog)
        self.assertEqual(sent[0].returncode, 4, sent[0].stdout + sent[0].stderr)
        msg = json.loads((Path(self.state) / "inbox/ash.jsonl").read_text().splitlines()[-1])["id"]
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("in-flight pass ash: undelivered inbox message " + msg, result.stdout)
        self.assertFalse(written)
        self.put("status/ash.status", "ack: %s\n" % msg)  # the window settles it
        result, written = self.wrapper_upgrade("────\n❯\u00a0\n────\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(written)

    def test_wrapper_child_with_idle_screen_applies(self):
        result, written = self.wrapper_upgrade("● Done.\n\n────\n❯\u00a0\n────\n  ? for shortcuts\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("in-flight", result.stdout)
        self.assertIn("reloaded ash", result.stdout)
        self.assertTrue(written)

    def test_wrapper_child_busy_or_unknown_screen_stays_busy(self):
        nudge = "────\n❯\u00a0inbox: 20261111T044605Z-4741d0\n────\n"  # the coordinator's message not yet submitted
        for screen, child, reason in (
                ("✽ Recombobulating… (5s · esc to interrupt)\n❯\u00a0\n", True, "harness mid-turn"),
                ("Loading…\n", True, "no idle prompt on screen"),
                ("Loading…\n", False, "no idle prompt on screen"),  # no tool-session child: the screen still decides
                ("", False, "no idle prompt on screen"),  # an empty capture
                ("Do you want to proceed?\n❯ 1. Yes\n  2. No\nEsc to cancel\n", True, "no idle prompt on screen"),
                (nudge, True, "unsubmitted inbox nudge on screen")):
            with self.subTest(screen=screen, child=child):
                result, written = self.wrapper_upgrade(screen, child=child)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("in-flight pass ash: %s; wait timed out; no install written" % reason, result.stdout)
                self.assertFalse(written)

    def test_failed_process_probe_stays_busy(self):
        result, written = self.wrapper_upgrade("❯\u00a0\n", ps_fails=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("in-flight pass ash: crew: process probe unavailable; wait timed out", result.stdout)
        self.assertFalse(written)

    def test_reload_keeps_metadata_and_coordinator_last(self):
        state = Path(self.state)
        brief = state / "runs/ben-7.brief.md"
        brief.parent.mkdir(exist_ok=True)
        brief.write_text("Old rule\n\n## This run\n\n- Worktree: kept\n")
        rec = dict(role="builder", index=10, worktree=self.project_dir, engine="codex", model="gpt-6.1-sol",
                   effort="medium", claim="kept", restarts=1)
        values = {"engines.coordinator": "claude-code", "runtime.options.permission_mode": "safe"}
        with mock.patch.object(upgrade, "runs", return_value=[("ben-7", rec)]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]), \
                mock.patch.object(upgrade, "stop_pane", return_value=None), \
                mock.patch.object(upgrade, "window_env", return_value={}), \
                mock.patch.object(upgrade, "identity", return_value={"pane_id": "%new"}), \
                mock.patch.object(upgrade, "role_notes", return_value=""), \
                mock.patch.object(upgrade.tmux.backends["tmux"], "tmux", return_value=Namespace(returncode=0)) as respawn, \
                mock.patch.object(upgrade, "wait_harness"), \
                mock.patch.object(upgrade.tmux.backends["tmux"], "server", return_value=[]):  # the shim pins -S
            upgrade.reload(values, "session", self.state, Namespace(project=self.project, timeout=1),
                           [(0, "ash"), (10, "ben-7")])
        self.assertEqual([c.args[3] for c in respawn.call_args_list if c.args[0] == "respawn-window"],
                         ["=session:10", "=session:0"])
        self.assertEqual([c.args[:5] for c in respawn.call_args_list if c.args[0] == "set-option"][:2],
                         [("set-option", "-w", "-t", "=session:10", "remain-on-exit"),
                          ("set-option", "-w", "-u", "-t", "=session:10")])
        self.assertIn("## This run\n\n- Worktree: kept", brief.read_text())
        saved = json.loads((state / "runs/ben-7.json").read_text())
        self.assertEqual((saved["claim"], saved["restarts"], saved["pane_id"]), ("kept", 1, "%new"))

    @unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
    def test_reload_on_real_tmux_keeps_the_window(self):
        sock, shim = Path(self.tmp) / "tmux.sock", Path(self.tmp) / "real-tmux"
        shim.mkdir()
        (shim / "tmux").write_text('#!/bin/sh\nexec %s -f /dev/null -S %s "$@"\n' % (shutil.which("tmux"), sock))
        (shim / "tmux").chmod(0o755)
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        env["PATH"] = "%s:%s" % (shim, env["PATH"])
        brief = Path(self.state) / "runs/ben-7.brief.md"
        brief.parent.mkdir(exist_ok=True)
        brief.write_text("Old rule\n\n## This run\n\n- Worktree: kept\n")
        rec = dict(role="builder", index=1, worktree=self.project_dir, engine="codex", model="m", effort="e")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(upgrade, "runs", return_value=[("ben-7", rec)]), \
                mock.patch.object(cli.commands()["lead"], "records", return_value=[]), \
                mock.patch.object(upgrade, "window_env", return_value={}), \
                mock.patch.object(upgrade, "role_notes", return_value=""), \
                mock.patch.object(upgrade, "harness", return_value=["sleep", "300"]), \
                mock.patch.object(upgrade, "LAUNCH", "exec %s #%s"), \
                mock.patch.object(upgrade, "wait_harness"), \
                mock.patch.object(upgrade.tmux.backends["tmux"], "server", return_value=[]):  # the shim pins -S
            self.addCleanup(subprocess.run, [str(shim / "tmux"), "kill-server"], capture_output=True)
            tmux = upgrade.tmux.tmux
            self.assertEqual(tmux("new-session", "-d", "-s", "s", "sleep 300").returncode, 0)
            self.assertEqual(tmux("new-window", "-d", "-t", "=s:1", "-n", "ben-7", "exec sleep 300").returncode, 0)
            before = upgrade.tmux.pane("s", 1)["pid"]
            upgrade.reload({"runtime.options.permission_mode": "safe"}, "s", self.state,
                           Namespace(project=self.project, timeout=1), [(1, "ben-7")])
            self.assertIn((1, "ben-7"), upgrade.tmux.list_windows("s"))
            self.assertNotEqual(upgrade.tmux.pane("s", 1)["pid"], before)
            self.assertEqual(tmux("show-options", "-w", "-v", "-t", "=s:1", "remain-on-exit").stdout, "")


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Upgrade(name) for name in Upgrade.__dict__ if name.startswith("test_"))


def evidence():
    fixture = Upgrade()
    fixture.setUp()
    try:
        print("create: bootstrap --yes --harness codex; exit 0; installed v2.1.0")
        result = fixture.upgrade("--yes")
        assert result.returncode == 0 and "no changes" in result.stdout
        print("upgrade --yes: exit 0; crew upgrade: no changes")
        source = fixture.bundle / "templates/runtimes/tmux/builder.md"
        source.write_text(source.read_text() + "\nNew reviewed rule.\n")
        result = fixture.upgrade("--dry-run")
        assert result.returncode == 0 and "+New reviewed rule." in result.stdout
        print("upgrade --dry-run: exit 0; +New reviewed rule.; install unchanged")
        result = fixture.upgrade("--yes")
        assert result.returncode == 0
        assert "New reviewed rule." in (Path(fixture.state) / "render/runtime/builder.md").read_text()
        print("upgrade --yes: exit 0; changed rule deployed; install self-test ok")
        (fixture.bundle / "VERSION").write_text("v2.2.0\n")
        fixture.tool("tmux", 'case "$1" in list-windows) echo "10 ben-7";; esac')
        before = fixture.manifest.read_bytes()
        result = fixture.upgrade("--yes", "--wait-timeout", "0")
        assert result.returncode == 1 and fixture.manifest.read_bytes() == before
        print("upgrade --yes --wait-timeout 0: exit 1; in-flight pass ben-7; install unchanged")
    finally:
        fixture.doCleanups()
    assert not Path(fixture.tmp).exists()
    print("delete: temporary project, install, state and fake host removed")


def adopt_evidence():
    """#1616 lifecycle: a user-level install with no install.json is adopted and upgraded, upgraded again, then the
    fake host is deleted."""
    fixture = Upgrade("test_adopts_a_verified_user_level_install_without_a_record")
    fixture.setUp()
    try:
        fixture.manifest.unlink()
        (fixture.bundle.parent / "current").symlink_to(fixture.bundle.name, target_is_directory=True)
        state = Path(fixture.state)
        print("create: user-level install v2.1.0; install.json exists: %s; link -> %s" % (
            fixture.manifest.exists(), (state / "mdstack").resolve().name))
        builder = fixture.bundle / "templates/runtimes/tmux/builder.md"
        deployed = state / "render/runtime/builder.md"
        for rule in ("Adopted rule.", "Second rule."):
            builder.write_text(builder.read_text() + "\n%s\n" % rule)
            result = fixture.upgrade("--yes")
            lines = [line for line in result.stdout.splitlines() if line.startswith("crew upgrade: adopted")]
            record = json.loads(fixture.manifest.read_text())
            print("upgrade --yes: exit %d; %s" % (result.returncode, lines[0] if lines else "(record already present)"))
            print("update: record tag=%s status=%s; %r deployed: %s" % (
                record["tag"], record["status"], rule, rule in deployed.read_text()))
        result = fixture.upgrade("--yes")
        print("upgrade --yes: exit %d; %s" % (result.returncode, result.stdout.strip().splitlines()[-1]))
    finally:
        fixture.doCleanups()
    print("delete: fake host, install record and state removed: %s" % (not Path(fixture.tmp).exists()))


if __name__ == "__main__":
    if sys.argv[1:] == ["--evidence"]:
        evidence()
    elif sys.argv[1:] == ["--evidence-adopt"]:
        adopt_evidence()
    else:
        unittest.main()
