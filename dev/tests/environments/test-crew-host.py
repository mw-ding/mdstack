"""Host readiness and inventory tests with fake SSH responses; no network or real host changes.

Usage: python3 dev/tests/environments/test-crew-host.py [--evidence]

--evidence prints reproducible CLI success, failure, repair and inventory transcripts from fake hosts.
"""
import contextlib
import io
import json
import os
import platform
import subprocess
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW
import importlib.machinery
import importlib.util
from argparse import Namespace

OS = {"Darwin": "macos"}.get(platform.system(), "linux")  # the simulated host is this machine


class Host(Base):
    def setUp(self):
        super().setUp()
        self.add_hosts()
        self.ssh_log = os.path.join(self.tmp, "ssh.log")
        self.env["FAKE_SSH_LOG"] = self.ssh_log
        self.env["FAKE_SSH_REPLY"] = json.dumps(self.reply())
        self.env["FAKE_SSH_EXIT"] = "0"
        self.env["CREW_PROJECT"] = self.project
        for tool in ("git", "gh", "codex", "claude"):
            path = os.path.join(self.tmp, "bin", tool)
            with open(path, "w") as f:
                f.write("#!/bin/sh\nexit %d\n" % (0 if tool == "git" else 1))
            os.chmod(path, 0o755)
        with open(os.path.join(self.tmp, "bin", "ssh"), "w") as f:
            f.write('#!/usr/bin/env python3\nimport json, os, sys\n'
                    'if "-G" in sys.argv:\n'
                    '    print("hostname " + sys.argv[-1])\n'
                    '    sys.exit(0)\n'
                    'request = json.load(sys.stdin)\n'
                    'with open(os.environ["FAKE_SSH_LOG"], "a") as f:\n'
                    '    f.write(json.dumps({"argv": sys.argv[1:], "request": request}) + "\\n")\n'
                    'if request["verb"] == "prepare":\n'
                    '    print(os.environ.get("FAKE_PREPARE_REPLY", \'{"result": "ok", "step": "clone"}\'))\n'
                    '    sys.exit(0)\n'
                    'if request["verb"] == "version":\n'
                    '    print(os.environ.get("FAKE_VERSION_REPLY", \'{"result": "ok", "version": "dev"}\'))\n'
                    '    sys.exit(0)\n'
                    'if request["verb"] == "seed":\n'
                    '    print(\'{"result": "ok", "step": "seed", "tip": "abc"}\')\n'
                    '    sys.exit(0)\n'
                    'reply = json.loads(os.environ["FAKE_SSH_REPLY"])\n'
                    'if request["fix"] and os.environ.get("FAKE_REPAIR"):\n'
                    '    reply["checks"][0]["status"] = "ok"\n'
                    '    reply["checks"][0]["detail"] = "state layout repaired"\n'
                    'print(json.dumps(reply))\nsys.exit(int(os.environ["FAKE_SSH_EXIT"]))\n')
        os.chmod(os.path.join(self.tmp, "bin", "ssh"), 0o755)

    def add_hosts(self):
        with open(self.project, "a") as f:
            f.write('\n[hosts.host-a]\nprimary = true\nmax_runs = 2\n'
                    'capabilities = { os = "linux", arch = "x86_64", engines = ["codex", "claude-code"] }\n'
                    '[hosts.host-b]\nroot = "~/.crew"\nmax_runs = 3\nroles = ["reviewer"]\n'
                    'capabilities = { os = "macos", arch = "arm64", devices = ["ios-simulator"], engines = ["codex"] }\n')

    def reply(self):
        return dict(result="ok", checks=[dict(status="ok", check=n, detail="passed") for n in
                                         ("tools", "logins", "project mirror")], projects=["acme__widgets"], load=1)

    def check(self, *args):
        return self.crew("host", "check", "host-b", *args)

    def calls(self):
        with open(self.ssh_log) as f:
            return [json.loads(line) for line in f]

    def test_ready_and_safe_request(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("host-b: ready", r.stdout)
        call = self.calls()[0]
        self.assertEqual(call["argv"][-2:], ["host-b", "crew-host"])
        for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "ClearAllForwardings=yes", "ConnectTimeout=10"):
            self.assertIn(option, call["argv"])
        self.assertEqual(call["request"]["identities"], {"reviewer": "acme-reviewer"})
        self.assertEqual(call["request"]["project"], "acme__widgets")
        self.assertFalse(call["request"]["fix"])
        self.assertNotIn("GH_TOKEN", json.dumps(call))

    def test_address_is_the_ssh_destination(self):
        """#1034: with an `address`, check and prepare connect to that DNS name; the label stays the key."""
        with open(self.project) as f:
            text = f.read().replace('root = "~/.crew"', 'root = "~/.crew"\naddress = "host-b.region.example.com"')
        with open(self.project, "w") as f:
            f.write(text)
        r = self.prepare()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("host-b: ready", r.stdout)
        self.assertEqual([(c["request"].get("verb"), c["argv"][-2]) for c in self.calls()],
                         [("prepare", "host-b.region.example.com"), ("check", "host-b.region.example.com")])
        r = self.crew("host", "check", "host-b.region.example.com")
        self.assertEqual((r.returncode, r.stdout), (1, "crew host: unknown inventory host host-b.region.example.com\n"))

    def test_failure_human_unverified_and_missing_checks_block(self):
        for status in ("fail", "human", "unverified", "warn"):
            reply = self.reply()
            reply["checks"][1].update(status=status, hint="log in on the host")
            self.env["FAKE_SSH_REPLY"] = json.dumps(reply)
            r = self.check("--fix")
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("log in on the host", r.stdout)
        checks = self.reply()["checks"]
        for reply in (dict(result="ok", checks=[], projects=[], load=0),
                      dict(result="ok", checks=checks[:1], projects=["acme__widgets"], load=0),
                      dict(result="ok", checks=checks, projects=[], load=0),
                      dict(result="ok", checks=[dict(status="surprise")], projects=[], load=0),
                      dict(result="refused", reason="verb check not built on this host")):
            self.env["FAKE_SSH_REPLY"] = json.dumps(reply)
            self.assertEqual(self.check().returncode, 1)

    def test_read_only_and_idempotent_fix(self):
        reply = self.reply()
        reply["checks"][0]["status"] = "fail"
        self.env.update(FAKE_SSH_REPLY=json.dumps(reply), FAKE_REPAIR="1")
        self.assertEqual(self.check().returncode, 1)
        for _ in range(2):
            r = self.check("--fix")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("state layout repaired", r.stdout)
        self.assertEqual([c["request"]["fix"] for c in self.calls()], [False, True, True])

    def test_unreachable_and_missing_runner(self):
        for code, line in ((255, "fail reachable: SSH unavailable"), (127, "entrypoint exit 127")):
            self.env["FAKE_SSH_EXIT"] = str(code)
            r = self.check()
            self.assertEqual(r.returncode, 1)
            self.assertIn(line, r.stdout)

    def test_unknown_host_and_invalid_profile_never_call_ssh(self):
        self.assertEqual(self.crew("host", "check", "-bad").returncode, 2)
        self.assertEqual(self.crew("host", "check", "host-c").returncode, 1)
        with open(self.project, "a") as f:
            f.write("unknown = 1\n")
        self.assertEqual(self.check().returncode, 1)
        self.assertFalse(os.path.exists(self.ssh_log))

    def test_inventory_remote_facts_and_unknown_load(self):
        self.env["FAKE_SSH_EXIT"] = "255"
        r = self.crew("hosts")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("host-b no yes macos/arm64 ios-simulator codex reviewer - unreachable no ?/3", r.stdout)
        self.env["FAKE_SSH_EXIT"] = "0"
        r = self.crew("hosts")
        self.assertIn("host-b no yes macos/arm64 ios-simulator codex reviewer acme__widgets reachable yes 1/3", r.stdout)

    def add_runner(self):
        with open(self.project, "a") as f:
            f.write('[hosts.host-c]\nforge = false\nmax_runs = 4\ncapabilities = { os = "linux", arch = "x86_64" }\n')

    def test_forge_less_logins_na_or_warn(self):
        self.add_runner()
        r = self.crew("host", "check", "host-c")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("n/a logins: forge-less host; runner jobs only", r.stdout)
        self.assertIn("host-c: ready", r.stdout)
        request = self.calls()[-1]["request"]
        self.assertEqual((request["forge"], request["roles"], request["identities"]), (False, [], {}))
        reply = self.reply()
        reply["checks"][1].update(status="fail", detail="gh logged in")
        self.env["FAKE_SSH_REPLY"] = json.dumps(reply)
        r = self.crew("host", "check", "host-c")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("warn logins: forge login present on a forge-less host; remove it", r.stdout)
        self.assertNotIn("gh logged in", r.stdout)
        del reply["checks"][1]
        self.env["FAKE_SSH_REPLY"] = json.dumps(reply)
        r = self.crew("host", "check", "host-c")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("n/a logins", r.stdout)
        self.assertEqual(self.check().returncode, 1)

    def test_inventory_forge_column(self):
        self.add_runner()
        r = self.crew("hosts")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("HOST PRIMARY FORGE OS/ARCH "))
        self.assertIn("host-c no no linux/x86_64 - - - acme__widgets reachable yes 1/4", r.stdout)

    def prepare(self, host="host-b"):
        return self.crew("host", "prepare", host)

    def test_prepare_fresh_and_refresh_then_check(self):
        for step in ("clone", "fetch"):
            self.env["FAKE_PREPARE_REPLY"] = json.dumps(dict(result="ok", step=step))
            r = self.prepare()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("ok prepare %s: project mirror" % step, r.stdout)
            self.assertIn("host-b: ready", r.stdout)
        verbs = [c["request"].get("verb", "check") for c in self.calls()]
        self.assertEqual(verbs, ["prepare", "check", "prepare", "check"])
        request = self.calls()[0]["request"]
        self.assertEqual((request["project"], request["root"], request["os"]), ("acme__widgets", "~/.crew", "macos"))
        check = self.calls()[1]["request"]
        self.assertEqual((check["capabilities"]["os"], check["ssh_port"]), ("macos", None))
        self.assertRegex(request["request_id"], "^[0-9a-f]{32}$")
        self.assertIn("-F", self.calls()[0]["argv"])
        self.assertNotIn("GH_TOKEN", json.dumps(self.calls()))

    def test_prepare_failure_is_reported_and_skips_check(self):
        for reply, line in ((dict(result="failed", step="clone", error="repository not found"),
                             "fail prepare clone: repository not found"),
                            (dict(result="refused", reason="version skew"), "fail prepare refused: version skew")):
            self.env["FAKE_PREPARE_REPLY"] = json.dumps(reply)
            r = self.prepare()
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn(line + "\nhost-b: not ready", r.stdout)
        self.assertEqual({c["request"]["verb"] for c in self.calls()}, {"prepare"})
        self.env["FAKE_SSH_EXIT"] = "255"
        self.env["FAKE_PREPARE_REPLY"] = ""
        self.assertIn("fail prepare failed:", self.prepare().stdout)

    def test_prepare_forge_less_seeds_from_the_primary(self):
        self.add_runner()
        with open(os.path.join(self.tmp, "bin", "git"), "w") as f:
            f.write('#!/bin/sh\necho "$@" >> %s/git.log\n[ "$3" = bundle ] && printf BUNDLE > "$6"\nexit 0\n' % self.tmp)
        r = self.prepare("host-c")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok prepare seed: project mirror", r.stdout)
        self.assertIn("host-c: ready", r.stdout)
        request = self.calls()[0]["request"]
        self.assertEqual((request["verb"], request["project"], request["branch"]), ("seed", "acme__widgets", "main"))
        self.assertEqual(request["bundle"], "QlVORExF")
        with open(os.path.join(self.tmp, "git.log")) as f:
            log = f.read().splitlines()
        self.assertEqual([line.split()[2] for line in log], ["fetch", "bundle"])
        self.assertTrue(log[1].endswith(" refs/remotes/origin/main"), log)
        with open(os.path.join(self.tmp, "bin", "git"), "w") as f:
            f.write('#!/bin/sh\n[ "$3" = bundle ] && { echo "fatal: bad revision" >&2; exit 128; }\nexit 0\n')
        r = self.prepare("host-c")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail prepare bundle: fatal: bad revision\nhost-c: not ready", r.stdout)
        self.assertEqual(len(self.calls()), 2)

    def test_forge_less_ready_through_the_real_entrypoint(self):
        """#743: a loopback ssh runs the real crew-remote.py as the forced command; prepare seeds, check is ready."""
        root, origin = os.path.join(self.tmp, "host-root"), os.path.join(self.tmp, "origin.git")
        with open(self.project, "a") as f:
            f.write('[hosts.host-c]\nforge = false\nroot = "%s"\nmax_runs = 4\n'
                    'capabilities = { os = "%s", arch = "x86_64" }\n' % (root, OS))
        os.remove(os.path.join(self.tmp, "bin", "git"))
        with open(os.path.join(self.tmp, "bin", "ssh"), "w") as f:
            f.write('#!/usr/bin/env python3\nimport os, subprocess, sys\n'
                    'if "-G" in sys.argv:\n    print("hostname " + sys.argv[-1])\n    sys.exit(0)\n'
                    'env = {k: v for k, v in os.environ.items() if k in ("PATH", "MDSTACK_COPY_CLAIMS") or k.startswith("FAKE_TMUX_")}\n'
                    'env["SSH_ORIGINAL_COMMAND"] = sys.argv[-1]\n'
                    'sys.exit(subprocess.run([sys.executable, %r, "--root", %r], env=env).returncode)\n'
                    % (os.path.join(os.path.dirname(os.path.dirname(CREW)), "environments", "terminal", "remote", "crew-remote.py"), root))
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", self.project_dir]
        for argv in (["git", "init", "-q", "--bare", origin], git + ["init", "-q", "-b", "main"],
                     git + ["add", "crew.toml"], git + ["commit", "-qm", "seed"],
                     git + ["remote", "add", "origin", origin], git + ["push", "-q", "origin", "main"]):
            subprocess.run(argv, check=True, capture_output=True)
        r = self.crew("host", "check", "host-c")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("fail project mirror: acme__widgets has no main; run mdstack host prepare", r.stdout)
        self.assertIn("fail runner: down", r.stdout)
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(CREW)), "environments", "terminal", "remote", "crew-remote.py"), "--root", root,
                        "runner", "--once"], env=self.env, check=True)
        r = self.prepare("host-c")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("ok prepare seed: project mirror", "ok tools: git, tmux", "ok capabilities: os " + OS,
                     "ok project mirror: acme__widgets has main", "n/a logins: forge-less host; runner jobs only",
                     "ok runner: up", "host-c: ready"):
            self.assertIn(line, r.stdout)
        self.assertRegex(r.stdout, r"ok capacity: [0-9.]+ GiB free, 0 running")
        self.assertEqual(self.crew("host", "check", "host-c").returncode, 0)

    def test_checkout_command_requests_and_required_row(self):
        """#1035: a checkout = "command" host sends checkout=command on prepare and check and needs `project checkout`;
        a mirror host's requests carry no checkout field."""
        with open(self.project, "a") as f:
            f.write('[hosts.host-d]\ncheckout = "command"\nmax_runs = 1\nroles = ["reviewer"]\n'
                    'capabilities = { os = "linux", arch = "x86_64", engines = ["codex"] }\n')
        self.prepare("host-b")
        self.env["FAKE_PREPARE_REPLY"] = json.dumps(dict(result="ok", step="checkout", path="/v/acme"))
        r = self.prepare("host-d")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)  # the fake reply has project mirror, no checkout row
        self.assertIn("ok prepare checkout: project checkout", r.stdout)
        self.assertIn("host-d: not ready", r.stdout)
        mirror_prepare, mirror_check, prepare, check = [c["request"] for c in self.calls()]
        self.assertNotIn("checkout", mirror_prepare)
        self.assertNotIn("checkout", mirror_check)
        self.assertEqual((prepare["verb"], prepare["checkout"], check["checkout"]), ("prepare", "command", "command"))
        reply = self.reply()
        reply["checks"][2]["check"] = "project checkout"
        self.env["FAKE_SSH_REPLY"] = json.dumps(reply)
        self.assertIn("host-d: ready", self.crew("host", "check", "host-d").stdout)

    def test_checkout_command_ready_through_the_real_entrypoint(self):
        """#1035: a forge-less host with a declared checkout command prepares with no git mirror and checks ready."""
        root = os.path.join(self.tmp, "host-root")
        with open(self.project, "a") as f:
            f.write('[hosts.host-c]\nforge = false\ncheckout = "command"\nroot = "%s"\nmax_runs = 4\n'
                    'capabilities = { os = "%s", arch = "x86_64" }\n' % (root, OS))
        os.remove(os.path.join(self.tmp, "bin", "git"))
        remote = os.path.join(os.path.dirname(os.path.dirname(CREW)), "environments", "terminal", "remote",
                              "crew-remote.py")
        with open(os.path.join(self.tmp, "bin", "ssh"), "w") as f:
            f.write('#!/usr/bin/env python3\nimport os, subprocess, sys\n'
                    'if "-G" in sys.argv:\n    print("hostname " + sys.argv[-1])\n    sys.exit(0)\n'
                    'env = {k: v for k, v in os.environ.items() if k in ("PATH", "MDSTACK_COPY_CLAIMS") or k.startswith("FAKE_TMUX_")}\n'
                    'env["SSH_ORIGINAL_COMMAND"] = sys.argv[-1]\n'
                    'sys.exit(subprocess.run([sys.executable, %r, "--root", %r], env=env).returncode)\n'
                    % (remote, root))
        subprocess.run([sys.executable, remote, "--root", root, "runner", "--once"], env=self.env, check=True)
        r = self.prepare("host-c")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail prepare checkout: no valid checkout/acme__widgets.json under root", r.stdout)
        os.makedirs(os.path.join(root, "checkout"))
        decl = os.path.join(root, "checkout", "acme__widgets.json")
        with open(decl, "w") as f:
            json.dump(dict(argv=["false"], path="vfs/widgets"), f)
        self.assertIn("fail prepare checkout: exit 1\nhost-c: not ready", self.prepare("host-c").stdout)
        r = self.crew("host", "check", "host-c")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("fail project checkout: acme__widgets checkout command has not run; run mdstack host prepare",
                      r.stdout)
        with open(decl, "w") as f:
            json.dump(dict(argv=["mkdir", "-p", "vfs/widgets"], path="vfs/widgets"), f)
        r = self.prepare("host-c")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("ok prepare checkout: project checkout",
                     "ok project checkout: acme__widgets at %s" % os.path.join(root, "vfs", "widgets"),
                     "n/a logins: forge-less host; runner jobs only", "ok runner: up", "host-c: ready"):
            self.assertIn(line, r.stdout)
        self.assertNotIn("project mirror", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(root, "mirrors")))
        self.assertEqual(self.crew("host", "check", "host-c").returncode, 0)

    def test_prepare_primary_fetch_failure(self):
        with open(os.path.join(self.tmp, "bin", "git"), "w") as f:
            f.write("#!/bin/sh\necho 'fatal: could not read from remote' >&2\nexit 1\n")
        r = self.prepare("host-a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail prepare fetch: fatal: could not read from remote\nhost-a: not ready", r.stdout)
        self.assertFalse(os.path.exists(self.ssh_log))

    def install(self, record=True):
        """An [install] table, and the primary's install.json when record is set."""
        with open(self.project, "a") as f:
            f.write('\n[install]\nsource = "mirror"\nlocation = "/srv/releases"\n')
        self.pin = dict(tag="v5.1.0", bundle_sha256="b" * 64, transport=dict(
            kind="mirror", location="/srv/releases", sha256sums_sha256="c" * 64, pinned=False))
        if record:
            os.makedirs(self.state, exist_ok=True)
            with open(os.path.join(self.state, "install.json"), "w") as f:
                json.dump(dict(self.pin, source="/x/mdstack-5.1.0", runtime="tmux"), f)

    def test_no_install_table_sends_no_toolkit(self):
        self.prepare()
        self.crew("host", "prepare", "host-b", "--prune")
        self.assertEqual([c["request"]["verb"] for c in self.calls()][:2], ["prepare", "check"])
        self.assertFalse([c for c in self.calls() if "toolkit" in c["request"]])
        self.assertEqual(self.calls()[2]["request"]["prune"], True)

    def test_prepare_sends_the_pin_and_check_requires_the_toolkit_row(self):
        self.install()
        self.env["FAKE_PREPARE_REPLY"] = json.dumps(dict(result="ok", step="fetch", toolkit=dict(
            tag="v5.1.0", state="installed"), pruned=["mdstack-5.0.0"]))
        self.env["FAKE_VERSION_REPLY"] = json.dumps(dict(result="ok", version="dev", toolkit=dict(
            status="ok", detail="mdstack v5.1.0 verified")))
        r = self.crew("host", "prepare", "host-b", "--prune")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok prepare toolkit: mdstack v5.1.0 installed\nok prepare prune: mdstack-5.0.0\n", r.stdout)
        self.assertIn("ok toolkit: mdstack v5.1.0 verified\nhost-b: ready", r.stdout)
        prepare, check, version = [c["request"] for c in self.calls()]
        self.assertEqual((prepare["toolkit"], prepare["prune"]), (self.pin, True))
        self.assertEqual((version["verb"], version["project"], version["toolkit"]), ("version", "acme__widgets", self.pin))
        for reply, line in ((dict(result="ok", version="dev", toolkit=dict(status="fail", detail="mdstack-5.1.0 files "
                             "differ from its record")), "fail toolkit: mdstack-5.1.0 files differ from its record; run "
                             "mdstack host prepare"),
                            (dict(result="ok", version="dev"), "fail toolkit: no toolkit facts: host entrypoint predates"),
                            (dict(result="refused", reason="version skew"), "fail toolkit: no toolkit facts: version skew")):
            with self.subTest(line=line):
                self.env["FAKE_VERSION_REPLY"] = json.dumps(reply)
                r = self.check()
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(line, r.stdout)
                self.assertIn("host-b: not ready", r.stdout)

    def test_no_primary_release_install_fails_toolkit(self):
        self.install(record=False)
        r = self.prepare()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fail prepare toolkit: no release install on the primary to pin", r.stdout)
        self.assertFalse(os.path.exists(self.ssh_log))
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fail toolkit: no release install on the primary to pin; run mdstack bootstrap --version", r.stdout)

    def test_primary_reuses_doctor_and_human_blocks(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        with mock.patch.dict(os.environ, self.env):
            args = Namespace(project=self.project, org_profile=None, fix=True, host="host-a", action="check")
            doctor = mod.commands()["doctor"]
            for message, code in (("ok tools ready", 0), ("human logins missing", 1)):
                def report(a):
                    self.assertTrue(a.fix)
                    self.assertFalse(a.dry_run)
                    self.assertIsNone(a.milestone)
                    print(message)
                    return 0
                with mock.patch.object(doctor, "run", side_effect=report), mock.patch.object(doctor, "sh", return_value=(0, "")):
                    self.assertEqual(mod.commands()["host"].run(args), code)
            with mock.patch.object(doctor, "run", return_value=0), mock.patch.object(doctor, "sh", return_value=(1, "")):
                self.assertEqual(mod.commands()["host"].run(args), 1)
            with mock.patch.object(doctor, "run", return_value=0), mock.patch.object(doctor, "sh",
                                   side_effect=lambda *cmd: (0 if cmd[0] == "git" else 1, "")):
                self.assertEqual(mod.commands()["host"].run(args), 1)
        self.assertFalse(os.path.exists(self.ssh_log))

    def primary_command_checkout(self, extra, root):
        """host-a as a primary with checkout = "command" plus extra lines; (host(action) -> (code, out),
        declare(argv, path) writing the declaration under root). git must not run."""
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace("[hosts.host-a]\nprimary = true\n",
                                 '[hosts.host-a]\nprimary = true\ncheckout = "command"\n' + extra))
        with open(os.path.join(self.tmp, "bin", "git"), "w") as f:
            f.write("#!/bin/sh\necho 'git must not run' >&2\nexit 1\n")
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        doctor, decl = mod.commands()["doctor"], os.path.join(root, "checkout", "acme__widgets.json")

        def declare(argv, path=self.project_dir):
            os.makedirs(os.path.dirname(decl), exist_ok=True)
            with open(decl, "w") as f:
                json.dump(dict(argv=argv, path=path), f)

        def host(action):
            args = Namespace(project=self.project, org_profile=None, fix=False, prune=False, host="host-a",
                             action=action)
            out = io.StringIO()
            with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out), \
                    mock.patch.object(doctor, "run", return_value=0), \
                    mock.patch.object(doctor, "sh", side_effect=lambda *cmd: (1 if cmd[0] == "git" else 0, "")):
                return mod.commands()["host"].run(args), out.getvalue()
        return host, declare

    def test_primary_command_checkout(self):
        """#1723: a primary with checkout = "command" prepares by running its own declaration (no git fetch) and
        checks the receipt (never the command, never git) against the project checkout; missing, failed or
        mismatched stays not ready."""
        root = os.path.join(self.tmp, "primary-root")
        host, declare = self.primary_command_checkout('root = "%s"\n' % root, root)
        ran = os.path.join(self.tmp, "ran.log")
        code, out = host("check")
        self.assertEqual(code, 1, out)
        self.assertIn("fail project checkout: acme__widgets checkout command has not run; run mdstack host prepare\n"
                      "host-a: not ready", out)
        self.assertNotIn("project mirror", out)
        code, out = host("prepare")
        self.assertEqual(code, 1, out)
        self.assertIn("fail prepare checkout: no valid checkout/acme__widgets.json under root", out)
        declare(["false"])
        self.assertEqual(host("prepare"), (1, "fail prepare checkout: exit 1\nhost-a: not ready\n"))
        declare(["sh", "-c", "echo ran >> " + ran])
        code, out = host("prepare")
        self.assertEqual(code, 0, out)
        for line in ("ok prepare checkout: project checkout\n", "ok engine login codex: logged in\n",
                     "ok project checkout: acme__widgets at %s\n" % self.project_dir, "host-a: ready\n"):
            self.assertIn(line, out)
        with open(os.path.join(root, "state", "acme__widgets", "checkout.json")) as f:
            self.assertEqual(json.load(f)["path"], self.project_dir)
        self.assertEqual(host("check")[0], 0)
        with open(ran) as f:
            self.assertEqual(f.read(), "ran\n")  # check never ran the command
        declare(["false"])  # success, then a failed prepare at the same path: the old receipt no longer counts
        self.assertEqual(host("prepare"), (1, "fail prepare checkout: exit 1\nhost-a: not ready\n"))
        code, out = host("check")
        self.assertEqual(code, 1, out)
        self.assertIn("fail project checkout: acme__widgets checkout command has not run", out)
        declare(["true"])
        self.assertEqual(host("prepare")[0], 0)  # repaired
        self.assertEqual(host("check")[0], 0)
        other = os.path.join(self.tmp, "elsewhere")
        declare(["mkdir", "-p", other], other)
        code, out = host("prepare")
        self.assertEqual(code, 1, out)
        self.assertIn("fail project checkout: declared path %s is not the project checkout %s; fix "
                      "checkout/acme__widgets.json or paths.checkout\nhost-a: not ready" % (other, self.project_dir), out)
        declare(["true"])
        self.assertEqual(host("check")[0], 1)  # the receipt names another path: the declared one has not run
        self.assertFalse(os.path.exists(self.ssh_log))

    def set_paths_root(self, root):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace("[paths]\n", '[paths]\nroot = "%s"\n' % root, 1))

    def test_primary_root_defaults_to_paths_root(self):
        """#1961: a primary with no `root` prepares and reads its receipt under the resolved paths.root, not
        ~/.mdstack, and reaches ready without setting `root`."""
        install = os.path.join(self.tmp, "install-root")
        self.set_paths_root(install)
        host, declare = self.primary_command_checkout("", install)
        declare(["true"])
        code, out = host("prepare")
        self.assertEqual(code, 0, out)
        self.assertIn("ok project checkout: acme__widgets at %s\nhost-a: ready\n" % self.project_dir, out)
        self.assertTrue(os.path.exists(os.path.join(install, "state", "acme__widgets", "checkout.json")))
        self.assertEqual(host("check")[0], 0)

    def test_primary_root_without_paths_root_is_user_root(self):
        """#1961: with neither `root` nor paths.root, the primary's root is user_root() ($CREW_ROOT here)."""
        user = os.path.join(self.tmp, "user-root")
        self.env["CREW_ROOT"] = user
        host, declare = self.primary_command_checkout("", user)
        declare(["true"])
        self.assertEqual(host("prepare")[0], 0)
        self.assertTrue(os.path.exists(os.path.join(user, "state", "acme__widgets", "checkout.json")))

    def test_primary_explicit_root_wins_over_paths_root(self):
        """#1961: an explicit primary `root` is unchanged by paths.root; the declaration under paths.root is unread."""
        install, explicit = os.path.join(self.tmp, "install-root"), os.path.join(self.tmp, "explicit-root")
        self.set_paths_root(install)
        host, declare = self.primary_command_checkout('root = "%s"\n' % explicit, install)
        declare(["true"])
        code, out = host("prepare")
        self.assertEqual(code, 1, out)
        self.assertIn("fail prepare checkout: no valid checkout/acme__widgets.json under root", out)
        os.renames(os.path.join(install, "checkout"), os.path.join(explicit, "checkout"))
        self.assertEqual(host("prepare")[0], 0)
        self.assertTrue(os.path.exists(os.path.join(explicit, "state", "acme__widgets", "checkout.json")))
        self.assertFalse(os.path.exists(os.path.join(install, "state", "acme__widgets", "checkout.json")))

    def test_session_runtime_gets_a_host_report(self):
        self.write_profile(runtime="session")
        self.add_hosts()
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stdout, "ok tools: passed\nok logins: passed\nok project mirror: passed\nhost-b: ready\n")
        self.assertEqual(self.calls()[0]["request"]["project"], "acme__widgets")
        r = self.crew("host", "prepare", "host-b")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("ok prepare clone: project mirror", r.stdout)
        r = self.crew("host", "check", "host-a")
        self.assertNotIn("not tmux", r.stdout)
        self.assertIn("project mirror: default branch main", r.stdout)
        self.assertTrue(r.stdout.endswith("host-a: ready\n") or r.stdout.endswith("host-a: not ready\n"), r.stdout)
        self.assertFalse(os.path.exists(self.log))  # no tmux call for a session crew

    def test_other_runtimes_still_refused(self):
        self.write_profile(runtime="grok-bot")
        self.add_hosts()
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("a host inventory needs runtime tmux or session, got 'grok-bot'", r.stdout)
        self.assertFalse(os.path.exists(self.ssh_log))

    def test_timeout_and_malformed_response(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        import subprocess
        host = mod.commands()["host"]
        with mock.patch.dict(os.environ, self.env):
            args = Namespace(project=self.project, org_profile=None, fix=False, host="host-b")
            values, session, state = mod.profile(args)
            for effect in (OSError("missing"), subprocess.TimeoutExpired("ssh", 45)):
                with mock.patch.object(host.subprocess, "run", side_effect=effect):
                    facts = host.inspect_host(args, values, session, state, "host-b")
                    self.assertFalse(facts["reachable"])
            with mock.patch.object(host.subprocess, "run", return_value=Namespace(returncode=0, stdout="not JSON")):
                self.assertFalse(host.inspect_host(args, values, session, state, "host-b")["ready"])


def evidence():
    fixture = Host()
    fixture.setUp()
    try:
        for label, args in (("ready", ()), ("repair", ("--fix",)), ("human", ("--fix",)), ("unreachable", ())):
            reply = fixture.reply()
            if label == "repair":
                reply["checks"][0]["status"] = "fail"
                fixture.env["FAKE_REPAIR"] = "1"
            if label == "human":
                reply["checks"][1].update(status="human", detail="login required", hint="log in on the host")
            fixture.env.update(FAKE_SSH_REPLY=json.dumps(reply), FAKE_SSH_EXIT="255" if label == "unreachable" else "0")
            r = fixture.check(*args)
            print("$ mdstack host check host-b" + (" --fix" if args else "") + " [fake SSH: " + label + "]")
            print("exit:", r.returncode)
            print(r.stdout, end="")
        r = fixture.crew("hosts")
        print("$ mdstack hosts [fake SSH: unreachable; host-b row]")
        print("exit:", r.returncode)
        print(next(line for line in r.stdout.splitlines() if line.startswith("host-b ")))
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    if "--evidence" in sys.argv:
        evidence()
    else:
        unittest.main()
