"""Worker tmux guard (#1475, #1474, #817): a bare destructive tmux call from a role window misses the crew's server.

Run through scripts/run-tests.py. The fake tmux checks spawn's new-window carries the guard; the decoy check starts a
real crew server only on a private socket under a temp TMUX_TMPDIR, never the owner's server, and every cleanup pins
that socket (#1156).
"""
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import SCRIPTS, SpawnBase

ADAPTER = os.path.join(os.path.dirname(SCRIPTS), "environments", "terminal", "sessions", "tmux", "adapter.py")
GUARD = "TMUX=/dev/null/mdstack-worker,0,0"


class FakeTmux(SpawnBase):
    def test_spawned_window_env_names_no_server(self):
        r = self.spawn("builder", "--issue", "7")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        window = self.windows()[-1]
        self.assertIn(GUARD, [window[i + 1] for i, a in enumerate(window) if a == "-e"])


@unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
class Decoy(unittest.TestCase):
    """AC 2: a throwaway crew server survives the bare kill calls run from a window launched the way spawn does, or
    reloaded the way upgrade does."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wg", dir="/tmp")  # short: the socket path has a length limit
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = patch.dict(os.environ, {"TMUX_TMPDIR": self.tmp, "HOME": self.tmp})
        env.start()
        self.addCleanup(env.stop)
        for var in ("TMUX", "TMUX_PANE"):
            os.environ.pop(var, None)
        spec = importlib.util.spec_from_file_location("guard_tmux", ADAPTER)
        self.tmux = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tmux)

    def start(self, name, tmux_server):
        self.tmux.bind(name, tmux_server)
        self.tmux.new_session(name, "ash", self.tmp, {}, "sleep 60")
        sock = self.tmux.tmux("display-message", "-p", "#{socket_path}").stdout.strip()
        self.assertTrue(os.path.realpath(sock).startswith(os.path.realpath(self.tmp)), sock)
        self.addCleanup(subprocess.run, ["tmux", "-S", sock, "kill-server"], capture_output=True)

    def wait(self, out):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if os.path.exists(out) and open(out).read().endswith("done\n"):
                return open(out).read()
            time.sleep(0.1)
        self.fail("window never finished: %r" % (open(out).read() if os.path.exists(out) else None))

    def worker(self, name, reload=False):
        """Window 10 as spawn opens it (adapter.new_window with role env), or as upgrade reloads it (hold, respawn);
        its shell runs the bare calls with the host tmux directory first on PATH, then a crew command's own check
        through the adapter."""
        out = os.path.join(self.tmp, "out")
        check = ("import importlib.util as u; s = u.spec_from_file_location('a', %r); a = u.module_from_spec(s); "
                 "s.loader.exec_module(a); a.bind(%r, %r); print('crew', a.has_session(%r))") % (
                     ADAPTER, name, "dedicated" if self.tmux.DEDICATED else "default", name)
        script = "; ".join([
            "export PATH=%s:$PATH" % shlex.quote(os.path.dirname(shutil.which("tmux"))),
            "echo \"TMUX=$TMUX\"",
            *("tmux %s; echo %s=$?" % (c, c.split()[0]) for c in (
                "kill-window", "kill-session", "kill-session -t " + name, "kill-server")),
            "env -u TMUX_TMPDIR TMUX_TMPDIR=%s/sbx tmux kill-server; echo tmpdir=$?" % self.tmp,
            "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(check)),
        ])
        env, command = {"CREW_ROLE": "builder", "CREW_ID": "ben-7"}, "{ %s; } > %s 2>&1; echo done >> %s; sleep 60" % (
            script, out, out)
        self.tmux.new_window(name, 10, "ben-7", self.tmp, env, "sleep 60" if reload else command)
        if reload:
            self.tmux.hold(name, 10)
            self.tmux.respawn(name, 10, self.tmp, env, command)
        return self.wait(out)

    def check(self, name, reload=False):
        log = self.worker(name, reload)
        self.assertIn(GUARD, log)
        for call in ("kill-window", "kill-session", "kill-server", "tmpdir"):
            self.assertIn("%s=1" % call, log)
        self.assertIn("crew True", log)
        self.assertTrue(self.tmux.has_session(name))
        self.assertEqual(self.tmux.list_windows(name), [(0, "ash"), (10, "ben-7")])

    def test_default_server_survives(self):
        self.start("crew-guard", "default")
        self.check("crew-guard")

    def test_dedicated_server_survives(self):
        self.start("crew-guard", "dedicated")
        self.check("crew-guard")

    def test_upgrade_reload_keeps_the_guard(self):
        self.start("crew-guard", "default")
        self.check("crew-guard", reload=True)

    def test_owner_window_inherits_no_crew_variables(self):
        """#1957 R10 (1): window 0 sees the env new_session was given; a window opened later in the session sees none."""
        for var in ("CREW_ROLE", "CREW_PROJECT"):  # the server's global env is this process's; the suite may run in a crew pane
            os.environ.pop(var, None)
        self.tmux.bind("crew-env", "default")
        zero, other = os.path.join(self.tmp, "zero"), os.path.join(self.tmp, "other")
        probe = "echo \"role=${CREW_ROLE-unset} project=${CREW_PROJECT-unset}\" > %s; echo done >> %s; sleep 60"
        self.tmux.new_session("crew-env", "ash", self.tmp, {"CREW_ROLE": "coordinator", "CREW_PROJECT": "/p q"},
                              probe % (zero, zero))
        sock = self.tmux.tmux("display-message", "-p", "#{socket_path}").stdout.strip()
        self.addCleanup(subprocess.run, ["tmux", "-S", sock, "kill-server"], capture_output=True)
        self.assertEqual(self.wait(zero), "role=coordinator project=/p q\ndone\n")
        r = self.tmux.tmux("new-window", "-d", "-t", "=crew-env:", probe % (other, other))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.wait(other), "role=unset project=unset\ndone\n")

    def test_coordinator_reload_keeps_the_crew_tmux(self):
        self.start("crew-guard", "default")
        out = os.path.join(self.tmp, "coordinator")
        self.tmux.hold("crew-guard", 0)
        self.tmux.respawn("crew-guard", 0, self.tmp, {}, "echo \"$TMUX\" > %s; echo done >> %s; sleep 60" % (out, out))
        self.assertTrue(self.wait(out).startswith(self.tmux.default_socket() + ","))


if __name__ == "__main__":
    unittest.main()
