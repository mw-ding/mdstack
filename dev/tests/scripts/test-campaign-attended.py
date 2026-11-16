#!/usr/bin/env python3
"""Fixture test for scripts/campaign-attended.py (#1463; offline, temp dirs only, fake mdstack and tmux).

Covers the refusals (A26 outside the manifest, a non-https webhook, the live crew's webhook) writing nothing, the
dry-run rehearsal passing end to end without sleep and labelled not evidence, the attended run passing only after a
wall-clock jump and a matching receipt code, and failing on no sleep, a wrong code, an undelivered message, an
unreadable snapshot or a changed tmux window across the sleep. Run in CI.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import time
import types
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cg, ca = load("campaign_guard", "campaign-guard.py"), load("campaign_attended", "campaign-attended.py")

PROFILE = """[repo]
owner = "%s"
name = "%s"
default_branch = "main"

[runtime]
name = "tmux"

[runtime.options]
slack_webhook_env = "LIVE_HOOK"

[paths]
state_dir = "%s/state"
worktree_root = "%s/wt"
live_dir = "%s/live"
"""

# Fake crew CLI: notify posts the event's title to a loopback webhook (an https one is not dialled) and records the
# delivery as FAKE_STATUS or sent; spawn writes a claim.
FAKE_CREW = r"""#!/usr/bin/env python3
import json, os, sys, urllib.request
a, s = sys.argv[1:], os.environ["FAKE_S"]
if a[0] == "notify":
    ev = json.load(open(a[a.index("--event-file") + 1]))
    hook, status = os.environ["CAMPAIGN_WEBHOOK"], os.environ.get("FAKE_STATUS", "sent")
    if hook.startswith("http://"):
        urllib.request.urlopen(urllib.request.Request(hook, data=json.dumps({"text": ev["title"]}).encode()))
    os.makedirs(s + "/notifications", exist_ok=True)
    json.dump({"status": status}, open(s + "/notifications/n.json", "w"))
elif a[0] == "spawn":
    os.makedirs(s + "/claims", exist_ok=True)
    os.makedirs(s + "/status", exist_ok=True)
    open(s + "/claims/builder-issue3", "w").write("heartbeat: x\n")
"""
FAKE_TMUX = "#!/bin/sh\n[ -z \"$FAKE_TMUX_FAIL\" ] || { echo \"no server\" >&2; exit 1; }\ncat \"$FAKE_WINDOWS\"\n"
STEPS = [{"name": "baseline", "run": "echo baseline >> {state_dir}/order"},
         {"name": "paused", "run": "echo paused >> {state_dir}/order"},
         {"name": "resume-catch-up", "run": "echo resume >> {state_dir}/order"}]


def fake_time(clock, sleep):
    """A time module for campaign-attended.py alone: patching time.sleep globally also fires inside subprocess.run's
    wait loop while a pre-sleep step's child is being reaped (#1479), so the fake must not reach other callers."""
    return types.SimpleNamespace(time=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep,
                                 strftime=time.strftime, gmtime=time.gmtime)


class CampaignAttendedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = d = os.path.realpath(self.tmp.name)
        prof = {}
        for name, owner, repo in (("prod", "mw-ding", "eng-crew"), ("sand", "acme", "sandbox")):
            prof[name] = os.path.join(d, name + ".toml")
            self.write(prof[name], PROFILE % ((owner, repo) + (d + "/" + name,) * 3))
        src = os.path.join(d, "src")
        os.makedirs(src + "/cli")
        self.write(src + "/cli/mdstack", FAKE_CREW)
        subprocess.run(["git", "init", "-q", src], check=True)
        subprocess.run(["git", "-C", src, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "c"], check=True)
        subprocess.run(["git", "init", "-q", d + "/sand/repo"], check=True)  # the sandbox clone campaign-sandbox.py makes
        self.write(d + "/outside.txt", "untouched\n")
        self.state = d + "/sand/state"
        for sub in ("bin", "gh", "acme__sandbox"):  # campaign-sandbox.py setup makes these
            os.makedirs(os.path.join(self.state, sub))
        self.write(self.state + "/bin/tmux", FAKE_TMUX)
        os.chmod(self.state + "/bin/tmux", 0o755)
        self.windows = self.state + "/windows"
        self.write(self.windows, "ash\nbuilder-3\n")
        self.manifest = self.state + "/m.json"
        self.make_manifest(prof, "A26")
        self.sdir = d + "/scenarios"
        os.makedirs(self.sdir)
        self.write(self.sdir + "/A26.json", json.dumps({"id": "A26", "steps": STEPS}))
        self.out = self.state + "/attended.json"
        self.env = mock.patch.dict(os.environ, {"FAKE_S": self.state + "/acme__sandbox", "FAKE_WINDOWS": self.windows})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def write(self, path, text):
        with open(path, "w") as fh:
            fh.write(text)

    def make_manifest(self, prof, *scenarios):
        argv = ["manifest", "--sandbox", prof["sand"], "--production", prof["prod"], "--source", self.d + "/src",
                "--release", "v1", "--run-id", "r1", "--sentinel", self.d + "/outside.txt", "--out", self.manifest]
        for sid in scenarios:
            argv += ["--scenario", sid]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cg.main(argv), 0)

    def run_cmd(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = ca.main([self.manifest, "--scenarios", self.sdir, "--out", self.out] + list(extra))
        return code, buf.getvalue()

    def doc(self):
        with open(self.out) as fh:
            return json.load(fh)

    def order(self):
        with open(self.state + "/order") as fh:
            return fh.read().split()

    def code(self, _prompt=""):
        with open(self.state + "/ev.json") as fh:
            return json.load(fh)["title"].split("receipt code ")[1]

    def attended(self, jump, receipt=None, **env):
        """Run attended with a fake clock: each 5 s poll advances the wall clock by `jump` seconds."""
        clock = [1_000_000.0]

        def sleep(secs):
            clock[0] += jump

        env = dict(CAMPAIGN_WEBHOOK="https://hooks.invalid/T/x", **env)
        with mock.patch.dict(os.environ, env), mock.patch.object(ca, "time", fake_time(clock, sleep)), \
                mock.patch("builtins.input", receipt or self.code):
            return self.run_cmd("--max-wait", "60")

    def test_refusals_write_nothing(self):
        cases = [({"CAMPAIGN_WEBHOOK": "http://hooks.invalid/x"}, "channel: CAMPAIGN_WEBHOOK is not an https URL"),
                 ({"CAMPAIGN_WEBHOOK": "https://hooks.invalid/live", "LIVE_HOOK": "https://hooks.invalid/live"},
                  "channel: CAMPAIGN_WEBHOOK is the live crew's webhook")]
        for env, reason in cases:
            with mock.patch.dict(os.environ, env):
                code, out = self.run_cmd()
            self.assertEqual(code, 2, out)
            self.assertIn("refused: " + reason, out)
        self.make_manifest({"sand": self.d + "/sand.toml", "prod": self.d + "/prod.toml"}, "A25")
        code, out = self.run_cmd("--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("refused: scenario: A26 is not in the manifest", out)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(self.state + "/order"))

    def test_dry_run_rehearsal_passes_without_sleep(self):
        code, out = self.run_cmd("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("REHEARSAL (not evidence) rehearsal PASS", out)
        doc = self.doc()
        self.assertEqual((doc["mode"], doc["evidence"], doc["status"]), ("rehearsal", False, "PASS"))
        self.assertEqual(doc["sleep"], {"slept": False, "label": "rehearsal: the machine was not slept"})
        self.assertEqual(doc["channel"]["status"], ["sent"])
        self.assertTrue(doc["channel"]["receipt"]["match"])
        self.assertEqual(doc["before"]["claims"], ["builder-issue3"])
        self.assertTrue(doc["preserved"])
        self.assertEqual(self.order(), ["baseline", "paused", "resume"])
        with open(self.state + "/gh/api---paginate---slurp.json") as fh:
            cmds = [re.search(r" cmd=(\S+)", c["body"]).group(1) for c in json.load(fh)[0]]  # the marker (#1946)
        self.assertEqual(cmds, ["away", "away-return"])

    def test_attended_passes_after_sleep_and_matching_code(self):
        code, out = self.attended(jump=900)
        self.assertEqual(code, 0, out)
        doc = self.doc()
        self.assertEqual((doc["mode"], doc["evidence"], doc["status"]), ("attended", True, "PASS"))
        self.assertTrue(doc["sleep"]["slept"])
        self.assertEqual(doc["sleep"]["seconds"], 900)
        self.assertEqual([u["what"] for u in doc["unblocks"]], ["owner slept and woke the machine",
                                                                 "owner confirmed receipt of the sandbox channel message"])
        self.assertNotIn("hooks.invalid", json.dumps(doc) + out)

    def test_attended_fails_closed(self):
        cases = [(dict(jump=5), "sleep: no wall-clock jump over 60s within 60s", ["baseline", "paused"]),
                 (dict(jump=900, receipt=lambda _p: "000000"), "channel: receipt code does not match",
                  ["baseline", "paused"]),
                 (dict(jump=900, FAKE_STATUS="uncertain"), "channel: delivery status ['uncertain']",
                  ["baseline", "paused"])]
        for kw, reason, order in cases:
            os.remove(self.state + "/order") if os.path.exists(self.state + "/order") else None
            code, out = self.attended(**kw)
            self.assertEqual(code, 1, out)
            self.assertIn(reason, self.doc()["reason"])
            self.assertEqual(self.order(), order, "A26's resume steps never run after a failed check")

    def test_unreadable_snapshot_fails_before_sleep(self):
        code, out = self.attended(jump=900, FAKE_TMUX_FAIL="1")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.doc()["reason"], "snapshot: tmux exited 1: no server")
        self.assertEqual(self.order(), ["baseline", "paused"])

    def test_changed_window_across_sleep_fails(self):
        def receipt(_prompt):
            raise AssertionError("the receipt is not asked once the snapshot changed")

        clock = [1_000_000.0]

        def sleep(secs):
            clock[0] += 900
            self.write(self.windows, "ash\n")

        with mock.patch.dict(os.environ, CAMPAIGN_WEBHOOK="https://hooks.invalid/T/x"), \
                mock.patch.object(ca, "time", fake_time(clock, sleep)), mock.patch("builtins.input", receipt):
            code, out = self.run_cmd()
        self.assertEqual(code, 1, out)
        self.assertIn("preserved: claims, worktrees or tmux windows changed", self.doc()["reason"])


if __name__ == "__main__":
    unittest.main()
