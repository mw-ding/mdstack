"""Tests for mdstack land-lock, moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: a second acquire fails fast and `down` refuses until release, release signals only the
recorded holder (stale or reused PID); placeholder path keys refused per command, also an omitted
key's default, while real paths and unused keys pass. Run in CI.
"""
import fcntl
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest
import time
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW


class LandLock(Base):
    """mdstack land-lock (#136): serial land under flock on locks/merge.lock."""

    def lock(self, action, **env):
        r = self.crew("land-lock", action, "--project", self.project, **env)
        if "--owner-transcript" in sys.argv:
            print("$ %screw land-lock %s --project <fixture>/crew.toml" % (
                "CREW_ID=sam " if env else "", action))
            print("exit: %d\n--- stdout\n%s--- stderr\n%s" % (r.returncode,
                  re.sub(r"pid \d+", "pid <holder>", r.stdout.replace(self.tmp, "<fixture>")), r.stderr), end="")
        return r

    def variant(self, **keys):
        """A copy of the project file in a worktree-like dir: each key set to a value, or omitted when None."""
        copy = os.path.join(self.tmp, "wt-copy")
        os.makedirs(copy, exist_ok=True)
        with open(self.project) as f:
            lines = f.read().splitlines()
        for key, value in keys.items():
            lines = [line for line in lines if not line.startswith(key + " =")] + \
                ([] if value is None else ["%s = %s" % (key, json.dumps(value))])
        project = os.path.join(copy, "crew.toml")
        with open(project, "w") as f:
            f.write("\n".join(lines) + "\n")
        return project

    def assertRefused(self, r, key, value):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("paths.%s: still the placeholder %s" % (key, value), r.stdout)
        self.assertIn("$CREW_PROJECT", r.stdout)

    def test_placeholder_paths_refused(self):  # #139 F5: a worktree's unrendered crew.toml
        project = self.variant(state_dir="<state-dir>")
        self.assertRefused(self.crew("land-lock", "acquire", "--project", project), "state_dir", "<state-dir>")
        self.assertEqual(os.listdir(os.path.dirname(project)), ["crew.toml"])  # no lock dir under the copy
        project = self.variant(worktree_root="<worktree-root>")
        self.assertRefused(self.crew("kill", "ben-7", "--project", project), "worktree_root", "<worktree-root>")
        self.assertRefused(self.crew("spawn", "reviewer", "--pr", "7", "--project", project),
                           "worktree_root", "<worktree-root>")
        project = self.variant(toolchain_bin="<toolchain-bin>")
        self.assertRefused(self.crew("spawn", "builder", "--issue", "7", "--project", project),
                           "toolchain_bin", "<toolchain-bin>")
        self.assertFalse(os.path.exists(os.path.join(self.state, "locks")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "claims")))

    def test_omitted_path_falls_back_to_default_placeholder_and_is_refused(self):  # #265
        project = self.variant(state_dir=None)
        r = subprocess.run([sys.executable, CREW, "land-lock", "acquire", "--project", project], cwd=self.tmp,
                           capture_output=True, text=True, env=self.env)
        self.assertRefused(r, "state_dir", "<state-dir>")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "<state-dir>")))  # #139 N1: lock under <cwd>
        project = self.variant(worktree_root=None)
        self.assertRefused(self.crew("kill", "ben-7", "--project", project), "worktree_root", "<worktree-root>")
        project = self.variant(toolchain_bin=None)
        self.assertRefused(self.crew("spawn", "builder", "--issue", "7", "--project", project),
                           "toolchain_bin", "<toolchain-bin>")

    def test_real_paths_accepted_and_unused_keys_not_checked(self):  # #265 AC2
        project = self.variant(worktree_root=None, toolchain_bin=None)  # land-lock uses state_dir only
        self.addCleanup(self.crew, "land-lock", "release", "--project", project)
        r = self.crew("land-lock", "acquire", "--project", project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("acquired", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.state, "locks", "merge.lock")))
        project = self.variant(worktree_root=os.path.join(self.tmp, "state", "wt"), toolchain_bin=None)
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash"}}, f)
        r = self.crew("kill", "ben-7", "--project", project)  # kill uses worktree_root, not toolchain_bin
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "crew: no run ben-7")
        r = self.crew("spawn", "reviewer", "--pr", "7", "--project", project)  # only a builder brief pins it
        self.assertNotIn("placeholder", r.stdout + r.stderr)

    def test_second_acquire_fails_fast_and_down_refuses_until_release(self):
        self.addCleanup(self.lock, "release")
        r = self.lock("acquire")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("acquired", r.stdout)
        r = self.lock("acquire")
        self.assertEqual(r.returncode, 1)
        self.assertIn("is held", r.stdout)
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash", "1": "sam"}}, f)
        r = self.crew("down", "--project", self.project)
        self.assertEqual(r.returncode, 1)
        self.assertIn("land lock", r.stdout)
        r = self.lock("release")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.state, "locks", "merge.pid")))
        self.assertEqual(self.lock("acquire").returncode, 0)
        self.assertEqual(self.lock("release").returncode, 0)
        self.assertEqual(self.crew("down", "--project", self.project).returncode, 0)

    def test_acquire_fails_fast_against_another_holder(self):
        os.makedirs(os.path.join(self.state, "locks"))
        with open(os.path.join(self.state, "locks", "merge.lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            r = self.lock("acquire")
            self.assertEqual(r.returncode, 1)
            r = self.lock("release")
            self.assertEqual(r.returncode, 1)
            self.assertIn("nothing signalled", r.stdout)
        self.assertEqual(self.lock("release").returncode, 0)

    def pidfile(self, rec=None):
        path = os.path.join(self.state, "locks", "merge.pid")
        if rec is not None:
            with open(path, "w") as f:
                json.dump(rec, f)
        with open(path) as f:
            return json.load(f)

    def test_matching_holder_released_and_recorded_with_start_time(self):
        self.assertEqual(self.lock("acquire").returncode, 0)
        rec = self.pidfile()
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(rec["pid"])], capture_output=True, text=True).stdout
        self.assertEqual(rec["start"], out.strip())
        r = self.lock("release")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("released", r.stdout)

    def test_stale_pid_file_with_other_holder_signals_nothing(self):
        bystander = subprocess.Popen(["sleep", "30"])
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        start = subprocess.run(["ps", "-o", "lstart=", "-p", str(bystander.pid)], capture_output=True,
                               text=True).stdout.strip()
        os.makedirs(os.path.join(self.state, "locks"))
        self.pidfile({"pid": bystander.pid, "start": start})  # live PID, matching start, but not a lock holder
        with open(os.path.join(self.state, "locks", "merge.lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            r = self.lock("release")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing signalled", r.stdout)
        self.assertIsNone(bystander.poll())

    def test_reused_pid_with_other_start_time_signals_nothing(self):
        self.addCleanup(self.lock, "release")
        self.assertEqual(self.lock("acquire").returncode, 0)
        rec = self.pidfile()
        self.pidfile(dict(rec, start="Thu Jan  1 00:00:00 1970"))
        r = self.lock("release")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing signalled", r.stdout)
        os.kill(rec["pid"], 0)  # holder still alive
        self.assertEqual(self.lock("acquire").returncode, 1)
        self.pidfile(rec)
        self.assertEqual(self.lock("release").returncode, 0)

    def test_cleanup_holder_exits_between_probe_and_signal(self):
        loader = importlib.machinery.SourceFileLoader("crew_lock_race", CREW)
        cli = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_lock_race", loader))
        loader.exec_module(cli)
        lock = cli._shared.commands()["land-lock"]
        os.makedirs(os.path.join(self.state, "locks"))
        self.pidfile(dict(pid=99999999, start="holder-start", owner=dict(pid=99999998, start="owner-start")))
        with patch.object(lock, "proc_identity", return_value=("holder-start", "mdstack land-lock acquire")), \
                patch.object(lock, "owner_alive", return_value=False), \
                patch.object(lock.os, "kill", side_effect=ProcessLookupError) as signal_holder:
            lock.cleanup(self.state)
        signal_holder.assert_called_once_with(99999999, lock.signal.SIGTERM)
        self.assertFalse(os.path.exists(os.path.join(self.state, "locks", "merge.pid")))

    def test_owner_death_releases_holder_and_stale_record(self):
        owner = subprocess.Popen(["sleep", "30"])
        self.addCleanup(owner.wait)
        self.addCleanup(lambda: owner.kill() if owner.poll() is None else None)
        start = subprocess.run(["ps", "-o", "lstart=", "-p", str(owner.pid)], capture_output=True,
                               text=True).stdout.strip()
        run = dict(index=40, role="synthesizer", item="PR #12", **{"pass": "land"}, repo=self.project_dir,
                   worktree=None, claim="unused", engine="codex", model="gpt-6.1-sol", effort="medium",
                   harness="codex", pane_pid=owner.pid, pane_start=start)
        self.put("runs/sam.json", json.dumps(run))
        r = self.lock("acquire", CREW_ID="sam")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.addCleanup(self.lock, "release")
        self.assertEqual(self.pidfile()["owner"], dict(pid=owner.pid, start=start))
        self.assertEqual(self.lock("acquire").returncode, 1)  # a live owner retains its lock
        owner.terminate()
        owner.wait()
        if "--owner-transcript" in sys.argv:
            print("state: owning pane process exited")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            r = self.lock("acquire")
            if r.returncode == 0:
                break
            time.sleep(.1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(self.pidfile()["owner"])
        self.assertEqual(self.lock("release").returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.state, "locks", "merge.pid")))
        if "--owner-transcript" in sys.argv:
            print("state: merge.pid absent after release")

    def test_synthesizer_lead_pane_owns_the_lock(self):  # #1569: a dead lead pane releases its lock
        owner = subprocess.Popen(["sleep", "30"])
        self.addCleanup(owner.wait)
        self.addCleanup(lambda: owner.kill() if owner.poll() is None else None)
        start = subprocess.run(["ps", "-o", "lstart=", "-p", str(owner.pid)], capture_output=True,
                               text=True).stdout.strip()
        self.put("leads/synthesizer.json", json.dumps(dict(name="sam-lead", index=1, role="synthesizer-lead",
                                                           harness="codex", pane_pid=owner.pid, pane_start=start)))
        r = self.lock("acquire", CREW_ID="sam-lead")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.addCleanup(self.lock, "release")
        self.assertEqual(self.pidfile()["owner"], dict(pid=owner.pid, start=start))
        owner.terminate()
        owner.wait()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            r = self.lock("acquire")
            if r.returncode == 0:
                break
            time.sleep(.1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fake_tmux_reads_never_rewrite_state(self):  # #2011: a holder's poll undid the test's window removal
        state = json.dumps({"crew-acme-widgets": {"0": "ash", "1": "sam"}}, indent=2)
        with open(self.state_file, "w") as f:
            f.write(state)
        for args in (["list-windows", "-t", "=crew-acme-widgets"], ["has-session", "-t", "=crew-acme-widgets"],
                     ["display-message", "-p", "-t", "=crew-acme-widgets:1"],
                     ["capture-pane", "-p", "-t", "=crew-acme-widgets:1"]):
            r = subprocess.run(["tmux", *args], capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 0, args + [r.stderr])
            with open(self.state_file) as f:
                self.assertEqual(f.read(), state, args)  # byte for byte: not even reformatted
        subprocess.run(["tmux", "kill-window", "-t", "=crew-acme-widgets:1"], check=True, env=self.env)
        with open(self.state_file) as f:  # negative control: a mutating call still persists
            self.assertEqual(json.load(f), {"crew-acme-widgets": {"0": "ash"}})
        self.assertFalse([n for n in os.listdir(self.tmp) if n.startswith("tmux.json.")])  # no temp file left

    def test_missing_window_reaps_lock_even_when_pane_process_survives(self):
        owner = subprocess.Popen(["sleep", "600"])  # outlives a loaded run; killed on cleanup
        self.addCleanup(owner.wait)
        self.addCleanup(owner.kill)
        start = subprocess.run(["ps", "-o", "lstart=", "-p", str(owner.pid)], capture_output=True,
                               text=True).stdout.strip()
        run = dict(index=1, role="synthesizer", item="PR #12", **{"pass": "land"}, repo=self.project_dir,
                   worktree=None, claim="unused", engine="codex", model="gpt-6.1-sol", effort="medium",
                   harness="codex", pane_pid=owner.pid, pane_start=start, pane_id="%7")
        self.put("runs/sam.json", json.dumps(run))
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash", "1": "sam"},
                       "_panes": {"crew-acme-widgets:1": "%%7 %d 0 0 /dev/ttys001 codex" % owner.pid}}, f)
        r = self.lock("acquire", CREW_ID="sam")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.addCleanup(self.lock, "release")
        self.assertEqual(self.lock("acquire").returncode, 1)
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash", "1": "sam"}}, f)
        self.assertEqual(self.lock("acquire").returncode, 1)  # unreadable pane, window still present
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash"}}, f)
        deadline = time.monotonic() + 15  # wait on the reap, not one acquire: the holder may be exiting on its own
        while True:
            r = self.lock("acquire")
            if r.returncode == 0 or time.monotonic() > deadline:
                break
            time.sleep(.1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(owner.poll())  # removal of the window is enough to reap its detached holder

    def test_legacy_orphan_holder_is_reaped_on_acquire(self):
        self.assertEqual(self.lock("acquire").returncode, 0)
        self.addCleanup(self.lock, "release")
        old = self.pidfile()
        old.pop("owner")  # pre-fix detached holder, orphaned after the acquire CLI exits
        self.pidfile(old)
        r = self.lock("acquire")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.pidfile()["pid"], old["pid"])

    def test_dead_holder_record_is_cleared(self):
        os.makedirs(os.path.join(self.state, "locks"))
        self.pidfile(dict(pid=99999999, start="gone"))
        self.assertEqual(self.lock("acquire").returncode, 0)
        self.addCleanup(self.lock, "release")
        self.assertNotEqual(self.pidfile()["pid"], 99999999)


if __name__ == "__main__":
    if "--owner-transcript" in sys.argv:
        suite = unittest.TestSuite([LandLock("test_owner_death_releases_holder_and_stale_record")])
        result = unittest.TextTestRunner().run(suite)
        sys.exit(not result.wasSuccessful())
    unittest.main()
