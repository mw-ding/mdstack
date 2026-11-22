#!/usr/bin/env python3
"""Tests for scripts/run-tests.py (offline, temp dir only).

Covers pass and fail exit codes, failing-file output capture, per-file
duration and slowest lines, serial files, slow-first start order, the
summary's CPU seconds, a missing file, tmux isolation of
each file (a decoy server on its own -S socket survives a bare kill-server)
and the per-file failure log. Run in CI.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")
RUNNER = os.path.join(SCRIPTS, "run-tests.py")


class RunTestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, body):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as fh:
            fh.write(body)
        return path

    def run_runner(self, *args, env=None):
        proc = subprocess.run([sys.executable, RUNNER, *args], capture_output=True, text=True, env=env)
        return proc.returncode, proc.stdout

    def test_all_pass_exits_zero_and_hides_output(self):
        a = self.write("test-a.py", "print('quiet a')\n")
        b = self.write("test-b.py", "print('quiet b')\n")
        code, out = self.run_runner("-j", "2", a, b)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"ok +\d+\.\ds  .*test-a\.py")
        self.assertRegex(out, r"ok +\d+\.\ds  .*test-b\.py")
        self.assertIn("slowest:", out)
        self.assertIn("2 files, 0 failed", out)
        self.assertNotIn("quiet a", out)

    def test_failure_exits_nonzero_and_shows_its_output(self):
        ok = self.write("test-ok.py", "print('fine')\n")
        bad = self.write("test-bad.py",
                         "import sys\nprint('to stdout')\nprint('to stderr', file=sys.stderr)\nsys.exit(3)\n")
        code, out = self.run_runner(ok, bad)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"FAIL +\d+\.\ds  .*test-bad\.py")
        self.assertRegex(out, r"===== FAIL .*test-bad\.py \(exit 3\) =====")
        self.assertIn("to stdout", out)
        self.assertIn("to stderr", out)
        self.assertNotIn("fine", out)
        self.assertIn("2 files, 1 failed", out)

    def test_runs_in_parallel_and_lists_slowest_first(self):
        slow = self.write("test-slow.py", "import time\ntime.sleep(3.0)\n")
        fast = self.write("test-fast.py", "import time\ntime.sleep(2.0)\n")
        code, out = self.run_runner("-j", "2", "--slowest", "1", slow, fast)
        self.assertEqual(code, 0, out)
        slowest = out.split("slowest:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("test-slow.py", slowest)
        self.assertNotIn("test-fast.py", slowest)
        wall = float(out.rsplit("failed, ", 1)[1].split("s wall", 1)[0])
        self.assertLess(wall, 4.5, out)

    def test_serial_file_runs_after_parallel_batch(self):
        spec = importlib.util.spec_from_file_location("run_tests", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        a = self.write("test-a.py", "")
        s = self.write("test-serial.py", "")
        mod.SERIAL = {"test-serial.py"}
        order = []
        real = mod.run_one
        mod.run_one = lambda path: (order.append(os.path.basename(path)), real(path))[1]
        with contextlib.redirect_stdout(io.StringIO()):
            code = mod.main([s, a])
        self.assertEqual(code, 0)
        self.assertEqual(order, ["test-a.py", "test-serial.py"])

    def test_slow_first_files_start_first_in_their_order(self):  # #2082
        spec = importlib.util.spec_from_file_location("run_tests", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        files = [self.write(n, "") for n in ("test-a.py", "test-b.py", "test-c.py", "test-d.py")]
        mod.SLOW_FIRST = ("test-d.py", "test-gone.py", "test-b.py")
        order = []
        real = mod.run_one
        mod.run_one = lambda path: (order.append(os.path.basename(path)), real(path))[1]
        with contextlib.redirect_stdout(io.StringIO()):
            code = mod.main(["-j", "1", *files])
        self.assertEqual(code, 0)
        self.assertEqual(order, ["test-d.py", "test-b.py", "test-a.py", "test-c.py"])

    def test_full_run_precompiles_and_named_files_do_not(self):  # #2082
        spec = importlib.util.spec_from_file_location("run_tests", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        os.makedirs(os.path.join(self.tmp.name, "tests", "mod"))
        test = self.write(os.path.join("tests", "mod", "test-a.py"), "")
        mod.TESTS = os.path.join(self.tmp.name, "tests")
        calls = []
        mod.precompile = lambda: calls.append("precompile")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main([test]), 0)
            self.assertEqual(calls, [])
            self.assertEqual(mod.main([]), 0)
        self.assertEqual(calls, ["precompile"])

    def test_precompile_writes_bytecode_outside_dot_dirs(self):  # #2082
        spec = importlib.util.spec_from_file_location("run_tests", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for d in ("pkg/sub", ".hidden"):
            os.makedirs(os.path.join(self.tmp.name, d))
        kept = self.write("pkg/sub/mod-a.py", "X = 1\n")
        hidden = self.write(".hidden/mod-b.py", "X = 1\n")
        mod.ROOT = self.tmp.name
        mod.precompile()
        self.assertTrue(os.path.exists(importlib.util.cache_from_source(kept)))
        self.assertFalse(os.path.exists(importlib.util.cache_from_source(hidden)))

    def test_summary_reports_the_files_cpu_seconds(self):  # #2082
        busy = self.write("test-busy.py", "import time\nt = time.process_time()\n"
                                          "while time.process_time() - t < 0.5:\n    pass\n")
        code, out = self.run_runner(busy)
        self.assertEqual(code, 0, out)
        cpu = float(re.search(r"\n1 files, 0 failed, [\d.]+s wall, -j \d+, ([\d.]+)s cpu\n", out).group(1))
        self.assertGreaterEqual(cpu, 0.5, out)

    def test_each_file_gets_private_tmux_tmpdir_without_tmux_vars(self):
        probe = (
            "import json, os, stat, sys\n"
            "d = os.environ.get('TMUX_TMPDIR')\n"
            "rec = {'tmux': os.environ.get('TMUX'), 'pane': os.environ.get('TMUX_PANE'), 'dir': d,\n"
            "       'mode': stat.S_IMODE(os.stat(d).st_mode), 'empty': os.listdir(d) == []}\n"
            "open(sys.argv[0] + '.json', 'w').write(json.dumps(rec))\n"
        )
        a = self.write("test-a.py", probe)
        b = self.write("test-b.py", probe)
        env = dict(os.environ, TMUX="/tmp/not-a-socket,1,0", TMUX_PANE="%9", TMUX_TMPDIR=self.tmp.name)
        code, out = self.run_runner("-j", "2", a, b, env=env)
        self.assertEqual(code, 0, out)
        recs = []
        for p in (a, b):
            with open(p + ".json") as fh:
                recs.append(json.load(fh))
        for rec in recs:
            self.assertIsNone(rec["tmux"])
            self.assertIsNone(rec["pane"])
            self.assertNotEqual(rec["dir"], self.tmp.name)
            self.assertEqual(rec["mode"], 0o700)
            self.assertTrue(rec["empty"])
            self.assertLess(len(rec["dir"]), 40, rec["dir"])
            self.assertFalse(os.path.exists(rec["dir"]), "TMUX_TMPDIR not removed")
        self.assertNotEqual(recs[0]["dir"], recs[1]["dir"])

    def test_bare_tmux_kill_in_a_test_spares_inherited_server(self):
        if shutil.which("tmux") is None:
            print("skip: tmux not installed", file=sys.stderr)
            self.skipTest("tmux not installed")
        sockdir = tempfile.mkdtemp(prefix="rtt.", dir="/tmp" if os.path.isdir("/tmp") else None)
        self.addCleanup(shutil.rmtree, sockdir, True)
        sock = os.path.join(sockdir, "decoy")
        tenv = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        tenv["TMUX_TMPDIR"] = sockdir

        def tmux(*args):
            return subprocess.run(["tmux", "-S", sock, *args], env=tenv, capture_output=True, text=True)

        self.assertEqual(tmux("-f", "/dev/null", "new-session", "-d", "-s", "decoy").returncode, 0)
        self.addCleanup(tmux, "kill-server")
        pid = tmux("display-message", "-p", "#{pid}").stdout.strip()
        killer = self.write("test-killer.py",
                            "import subprocess\n"
                            "subprocess.run(['tmux', 'kill-session'])\n"
                            "subprocess.run(['tmux', 'kill-server'])\n")
        env = dict(os.environ, TMUX="%s,%s,0" % (sock, pid), TMUX_PANE="%0")
        code, out = self.run_runner(killer, env=env)
        self.assertEqual(code, 0, out)
        self.assertEqual(tmux("has-session", "-t", "decoy").returncode, 0, "decoy server was killed")

    def test_failure_log_is_written_when_the_file_finishes(self):
        logs = os.path.join(self.tmp.name, "logs")
        bad = self.write("test-bad.py", "import sys\nprint('boom output')\nsys.exit(4)\n")
        waiter = self.write("test-waiter.py",
                            "import os, sys, time\n"
                            "log = %r\n"
                            "for _ in range(200):\n"
                            "    if os.path.exists(log):\n"
                            "        sys.exit(0)\n"
                            "    time.sleep(0.05)\n"
                            "sys.exit(1)\n" % os.path.join(logs, "test-bad.py.log"))
        code, out = self.run_runner("-j", "2", "--log-dir", logs, bad, waiter)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"ok +\d+\.\ds  .*test-waiter\.py")
        log = os.path.join(logs, "test-bad.py.log")
        self.assertRegex(out, r"FAIL +\d+\.\ds  .*test-bad\.py  log: " + re.escape(log))
        with open(log) as fh:
            self.assertIn("boom output", fh.read())
        self.assertFalse(os.path.exists(os.path.join(logs, "test-waiter.py.log")))

    def test_failure_log_defaults_to_a_kept_temp_dir(self):
        bad = self.write("test-bad.py", "print('kept')\nraise SystemExit(2)\n")
        code, out = self.run_runner(bad)
        self.assertEqual(code, 1, out)
        log = re.search(r"log: (\S+)", out).group(1)
        self.addCleanup(shutil.rmtree, os.path.dirname(log), True)
        with open(log) as fh:
            self.assertIn("kept", fh.read())

    def test_missing_file_is_an_error(self):
        code, _ = self.run_runner(os.path.join(self.tmp.name, "test-nope.py"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
