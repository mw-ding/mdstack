#!/usr/bin/env python3
"""Fixture test for scripts/campaign-run.py (offline, temp dirs only).

Covers scenario selection, the five distinct statuses, the per-step guard recheck, the command exit captured apart from the capture, explicit
completion waits (matched and deadline), the {source} placeholder and stub env, no operator forge or SSH agent credentials in a step (#1106), the guard refusal, the committed A03/A05 fixture steps failing closed on an earlier assertion, a step with an unhandled assertion or a child-shell `exit` refused before it runs while explicit refusal oracles still pass, expected-fail and accepted dispositions reported apart from PASS (a passing one FAILs; #1412), the A12 reproduction helper agreeing only with a capture at head, the A22 duplicate-key oracle passing on a run id with capitals (#1177), the A23 fake SSH transport's loopback and fault modes, the A19 ledger matching every shipped adapter and declared row and failing a gap claimed as conformant (#1443), the A19 smoke running in a linked worktree of its source and blocking on unmet checkout trust (#1470), a seeded rerun reproducing events and failure, and the
decoy sentinel failing a run whose step reaches an inherited TMUX (#817; throwaway sockets only, with the runner's TMUX_TMPDIR restored after, #818). Run in CI.
"""
import contextlib
import importlib.machinery
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
from unittest import mock

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cg, cr = load("campaign_guard", "campaign-guard.py"), load("campaign_run", "campaign-run.py")

PROFILE = """[repo]
owner = "%s"
name = "%s"
default_branch = "main"

[runtime]
name = "tmux"

[paths]
state_dir = "%s/state"
worktree_root = "%s/wt"
live_dir = "%s/live"
"""

SCENARIOS = {
    "A01": {"steps": [{"name": "emit", "run": "echo \"$CAMPAIGN_SEED $CREW_STATE\" > {state_dir}/a01.status &"},
                      {"name": "done", "wait": "{state_dir}/a01.status", "match": "^\\d+ $", "deadline": 5}]},
    "A02": {"steps": [{"name": "ok", "run": "echo out; echo err >&2"},
                      {"name": "bad", "run": "echo partial; exit 3"}, {"name": "never", "run": "true"}]},
    "A03": {"requires": ["no-such-tool-784"], "steps": [{"name": "x", "run": "true"}]},
    "A04": {"limitation": "level b needs an owner sandbox repo", "steps": []},
    "A05": {"steps": [{"name": "hang", "wait": "{state_dir}/never", "match": "done", "deadline": 0.2}]},
}


class CampaignRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.realpath(self.tmp.name)
        prof = {}
        for name, owner, repo in (("prod", "mw-ding", "eng-crew"), ("sand", "acme", "sandbox")):
            prof[name] = os.path.join(self.d, name + ".toml")
            self.write(prof[name], PROFILE % ((owner, repo) + (self.d + "/" + name,) * 3))
        src = os.path.join(self.d, "src")
        subprocess.run(["git", "init", "-q", src], check=True)
        subprocess.run(["git", "-C", src, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "c"], check=True)
        self.write(os.path.join(self.d, "outside.txt"), "untouched\n")
        os.makedirs(self.d + "/sand/state")
        self.manifest = self.d + "/sand/state/m.json"
        argv = ["manifest", "--sandbox", prof["sand"], "--production", prof["prod"], "--source", src,
                "--release", "v4.0.0", "--run-id", "r1", "--sentinel", self.d + "/outside.txt", "--out",
                self.manifest]
        for sid in ("A01", "A02", "A03", "A04", "A05", "A06"):
            argv += ["--scenario", sid]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cg.main(argv), 0)
        self.sdir = os.path.join(self.d, "scenarios")
        os.makedirs(self.sdir)
        for sid, sc in SCENARIOS.items():
            self.write(os.path.join(self.sdir, sid + ".json"), json.dumps(dict(sc, id=sid)))
        self.out = self.d + "/sand/state/results.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        with open(path, "w") as fh:
            fh.write(text)

    def run_cmd(self, *extra, out=None):
        os.environ["CREW_STATE"] = "/production/state"
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                code = cr.main([self.manifest, "--scenarios", self.sdir, "--out", out or self.out] + list(extra))
        finally:
            del os.environ["CREW_STATE"]
        return code, buf.getvalue()

    def results(self, path=None):
        with open(path or self.out) as fh:
            doc = json.load(fh)
        return doc, {r["id"]: r for r in doc["results"]}

    def test_statuses_distinct_and_exit_captured(self):
        code, out = self.run_cmd("--seed", "7")
        self.assertEqual(code, 1, out)
        doc, res = self.results()
        self.assertEqual({k: r["status"] for k, r in res.items()},
                         {"A01": "PASS", "A02": "FAIL", "A03": "BLOCKED", "A04": "LIMITATION", "A05": "FAIL",
                          "A06": "NOT RUN"})
        ok, bad = res["A02"]["steps"]
        self.assertEqual((ok["capture"], ok["exit"], ok["stdout"], ok["stderr"]), ("ok", 0, "out\n", "err\n"))
        self.assertEqual((bad["capture"], bad["exit"], bad["want"], bad["stdout"]), ("ok", 3, 0, "partial\n"))
        self.assertEqual(len(res["A02"]["steps"]), 2, "a failed step stops the scenario")
        self.assertEqual(res["A05"]["events"], ["wait hang: deadline"])
        self.assertIn("missing tool: no-such-tool-784", res["A03"]["reason"])
        with open(self.d + "/sand/state/a01.status") as fh:
            self.assertEqual(fh.read(), "7 \n", "child got CAMPAIGN_SEED and no inherited CREW_STATE")

    def test_selection_marks_rest_not_run(self):
        code, out = self.run_cmd("--scenario", "A01", "--seed", "1")
        self.assertEqual(code, 1, "NOT RUN is never a pass")
        doc, res = self.results()
        self.assertEqual(doc["selected"], ["A01"])
        self.assertEqual(res["A01"]["status"], "PASS")
        self.assertEqual(res["A02"], {"id": "A02", "status": "NOT RUN", "reason": "not selected", "events": []})
        self.assertEqual(self.run_cmd("--scenario", "A01")[0], 1)
        self.assertEqual(self.run_cmd("--scenario", "A99")[0], 2)

    def test_source_and_stub_env_reach_steps(self):
        st = self.d + "/sand/state"
        spec = {"steps": [{"name": "env", "run": 'git -C {source} rev-parse HEAD > {state_dir}/src.txt; '
                           'echo "$CAMPAIGN_GH_DIR $CAMPAIGN_STUB_LOG $CAMPAIGN_GH_LOG" > {state_dir}/env.txt'}]}
        self.write(os.path.join(self.sdir, "A01.json"), json.dumps(spec))
        self.assertEqual(self.run_cmd("--scenario", "A01")[0], 1, "the other scenarios stay NOT RUN")
        self.assertEqual(self.results()[1]["A01"]["status"], "PASS")
        with open(st + "/src.txt") as fh, open(self.manifest) as mf, open(st + "/env.txt") as env:
            self.assertEqual(fh.read().strip(), json.load(mf)["source"]["sha"])
            self.assertEqual(env.read().split(), [st + "/gh", st + "/stub.log", st + "/gh.log"])

    def test_operator_credentials_do_not_reach_steps(self):
        # #1106: the A23 sample listed the inherited GH_TOKEN and SSH_AUTH_SOCK from a step that exported nothing.
        st = self.d + "/sand/state"
        spec = {"steps": [{"name": "env", "run": "env | sed 's/=.*//' | sort > {state_dir}/names.txt; "
                           "echo \"$GH_CONFIG_DIR\" > {state_dir}/ghconf.txt"}]}
        self.write(os.path.join(self.sdir, "A01.json"), json.dumps(spec))
        creds = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "SSH_AUTH_SOCK",
                 "SSH_AGENT_PID")
        with mock.patch.dict(os.environ, dict({k: "x" for k in creds}, GH_CONFIG_DIR="/owner/.config/gh")):
            self.assertEqual(self.run_cmd("--scenario", "A01")[0], 1, "the other scenarios stay NOT RUN")
        self.assertEqual(self.results()[1]["A01"]["status"], "PASS")
        with open(st + "/names.txt") as fh, open(st + "/ghconf.txt") as conf:
            names, ghconf = fh.read().split(), conf.read().strip()
        self.assertEqual(set(creds) & set(names), set())
        self.assertIn("PATH", names)
        self.assertEqual(ghconf, st + "/gh-config", "gh reads only the sandbox config")

    def test_all_pass_exits_zero(self):
        passing = {"steps": [{"name": "ok", "run": "exit 4", "exit": 4}]}
        for sid in ("A01", "A02", "A03", "A04", "A05", "A06"):
            self.write(os.path.join(self.sdir, sid + ".json"), json.dumps(passing))
        self.assertEqual(self.run_cmd()[0], 0)

    def test_rerun_seed_reproduces_events_and_failure(self):
        self.run_cmd("--seed", "42")
        first = self.d + "/sand/state/first.json"
        os.replace(self.out, first)
        os.remove(self.d + "/sand/state/a01.status")
        self.assertEqual(self.run_cmd("--rerun", first)[0], 1)
        a, b = self.results(first)[0], self.results()[0]
        self.assertEqual((a["seed"], a["order"]), (b["seed"], b["order"]))
        strip = [{k: r.get(k) for k in ("id", "status", "reason", "events")} for r in a["results"]]
        self.assertEqual(strip, [{k: r.get(k) for k in ("id", "status", "reason", "events")} for r in b["results"]])
        self.assertEqual(self.results()[1]["A02"]["reason"], "run bad: exit 3 (want 0)")

    def test_guard_rechecked_before_each_run_step(self):
        drift = {"steps": [{"name": "drift", "run": "printf '\\n' >> \"$CREW_PROJECT\""},
                           {"name": "later", "run": "echo ran > {state_dir}/after-drift"}]}
        self.write(os.path.join(self.sdir, "A01.json"), json.dumps(drift))
        code, out = self.run_cmd("--scenario", "A01", "--scenario", "A02", "--seed", "0")
        self.assertEqual(code, 2, out)
        self.assertFalse(os.path.exists(self.d + "/sand/state/after-drift"), "no mutation after a refusal")
        doc, res = self.results()
        self.assertEqual(res["A01"]["status"], "BLOCKED")
        self.assertIn("refused: profile:", res["A01"]["reason"])
        self.assertEqual(res["A01"]["events"], ["run drift: exit 0 (want 0)"])
        self.assertEqual(doc["order"], ["A01", "A02"])
        self.assertEqual(res["A02"]["status"], "NOT RUN")
        self.assertEqual(res["A02"]["reason"], "run stopped: guard refused")

    def test_guard_refusal_writes_nothing(self):
        for out in (self.d + "/results.json", self.d + "/prod/state/results.json"):
            code, text = self.run_cmd(out=out)
            self.assertEqual(code, 2)
            self.assertIn("refused: out:", text)
            self.assertFalse(os.path.exists(out))
        with open(self.d + "/sand.toml", "a") as fh:
            fh.write("\n")
        code, text = self.run_cmd()
        self.assertEqual(code, 2)
        self.assertIn("refused: profile:", text)
        self.assertFalse(os.path.exists(self.out))

    @unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
    def test_decoy_fails_a_step_that_reaches_inherited_tmux(self):
        kill = {"steps": [{"name": "cleanup", "run": "tmux kill-server; true"}]}
        self.write(os.path.join(self.sdir, "A01.json"), json.dumps(kill))
        self.write(os.path.join(self.sdir, "A02.json"), json.dumps({"steps": [{"name": "ok", "run": "true"}]}))
        before = os.environ.get("TMUX_TMPDIR")
        orig = cr.scenario_env
        # A stripped bare call finds no server; the runner's own TMUX_TMPDIR comes back after (#818: a `del` here sent
        # later tests' bare tmux calls to the caller's default server).
        with mock.patch.dict(os.environ, TMUX_TMPDIR=os.path.join(self.d, "no-server")):
            os.makedirs(os.environ["TMUX_TMPDIR"])
            try:
                self.run_cmd("--scenario", "A01", "--scenario", "A02", "--seed", "0")
                self.assertEqual([self.results()[1][s]["status"] for s in ("A01", "A02")], ["PASS", "PASS"])
                cr.scenario_env = lambda m, seed, base: dict(orig(m, seed, base), TMUX=base["TMUX"])  # the regression
                code, out = self.run_cmd("--scenario", "A01", "--scenario", "A02", "--seed", "0")
            finally:
                cr.scenario_env = orig
        self.assertEqual(os.environ.get("TMUX_TMPDIR"), before)
        self.assertEqual(code, 1, out)
        res = self.results()[1]
        self.assertEqual((res["A01"]["status"], res["A01"]["reason"]),
                         ("FAIL", "decoy: a tmux server outside the sandbox was killed"))
        self.assertEqual((res["A02"]["status"], res["A02"]["reason"]), ("NOT RUN", "run stopped: decoy killed"))

    def one(self, *steps):
        """Run A01 with STEPS; return its result."""
        self.write(os.path.join(self.sdir, "A01.json"), json.dumps({"steps": list(steps)}))
        self.run_cmd("--scenario", "A01", "--seed", "0")
        return self.results()[1]["A01"]

    def test_failed_assertion_chain_before_a_passing_tail_fails(self):
        # #1412: plain `sh -c` exits 0 here, since only the last command's exit counts.
        masked = "test 1 -eq 2 && grep -q x /dev/null; echo tail"
        self.assertEqual(subprocess.run(["sh", "-c", masked], capture_output=True).returncode, 0)
        res = self.one({"name": "ok", "run": "true"}, {"name": "masked", "run": masked})
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(res["reason"].startswith("step masked refused: unhandled assertion"), res["reason"])
        self.assertEqual(res["events"], ["run ok: exit 0 (want 0)"], "the refused step does not run")
        self.assertEqual(self.one({"name": "lone", "run": "test 1 -eq 2; echo tail"})["status"], "FAIL")
        res = self.one({"name": "fn", "run": "f() { test 1 -eq 2; }; f; echo tail"})
        self.assertEqual((res["status"], res["events"]), ("FAIL", []), "a dropped failing function call (#1677 review)")
        res = self.one({"name": "fn-if", "run": "f() if true; then test 1 -eq 2; fi; f; echo tail"})
        self.assertEqual((res["status"], res["events"]), ("FAIL", []), "an if-bodied function (#1677 review r2)")
        for src in ("f() (test 1 -eq 2 || exit 1); f; echo tail", "f() { test 1 -eq 2 || return; }; f; echo tail",
                    "test 1 -eq 2 || (exit 1); echo tail", "f() { test 1 -eq 2 || (exit 1); }; f; echo tail",
                    "test 1 -eq 2 || { true || exit 1; }; echo tail", "{ test 1 -eq 2; } &",
                    "if test 1 -eq 2; true; then echo tail; fi", "test 1 -eq 2 || true | exit 1; echo tail",
                    "test 1 -eq 2 || { echo bad; exit 1; } | cat; echo tail",
                    "f() { test 1 -eq 2 || exit 1; }; f | cat; echo tail",
                    "test 1 -eq 2 || { echo bad; exit 1 & }; echo tail",
                    "for r in a; do test 1 -eq 2 || exit 1; done | cat; echo tail",
                    "x=$(test 1 -eq 2 || exit 1); echo tail",
                    "f() { if test 1 -eq 2 || exit 1; then :; fi; }; f | cat; echo tail",
                    "f() { while test 1 -eq 2 || exit 1; do break; done; }; x=$(f); echo tail",
                    "f() { if test 1 -eq 2 || return 1; then :; fi; }; f | cat; echo tail",
                    "f() { while test 1 -eq 2 || return 1; do break; done; }; f; echo tail",
                    "f() { if test 1 -eq 2 || return 1; then :; fi; }; x=$(f); echo tail"):
            res = self.one({"name": "local-exit", "run": src})
            self.assertEqual((res["status"], res["events"]), ("FAIL", []), "%s (#1677 review r3-r7, #1684, #1687 r1-r2)" % src)
        res = self.one({"name": "helper", "run": "f() { test 1 -eq 2 || exit 1; }; f; echo tail"})
        self.assertEqual((res["status"], res["steps"][0]["exit"]), ("FAIL", 1), "a foreground exiting helper ends the step")
        for src in ("test 1 -eq 1 || exit 1; echo tail", "test 1 -eq 1 || { echo bad; exit 1; }; echo tail",
                    "f() { test 1 -eq 1 || exit 1; }; f; echo tail",
                    "test -e / && echo foreground", "if test 1 -eq 2; then echo yes; fi; echo tail"):
            self.assertEqual(self.one({"name": "supported", "run": src})["status"], "PASS", src)
        res = self.one({"name": "handler", "run": "test 1 -eq 2 || { echo bad; exit 1; }; echo tail"})
        self.assertEqual((res["status"], res["steps"][0]["exit"]), ("FAIL", 1), "an unconditional handler fails the step")

    def test_explicit_refusal_oracles_still_pass(self):
        capture = "sh -c 'echo no >&2; exit 1' 2> o.txt; rc=$?; cat o.txt; test $rc -eq 1 && grep -qx no o.txt"
        res = self.one({"name": "rc", "run": "cd {state_dir} && " + capture},
                       {"name": "exit", "run": "echo refused; exit 3", "exit": 3},
                       {"name": "guarded", "run": "test 1 -eq 1 && grep -q . /etc/hosts || exit 1; echo tail"})
        self.assertEqual((res["status"], len(res["events"])), ("PASS", 3), res)
        res = self.one({"name": "rc", "run": "cd {state_dir} && " + capture.replace("exit 1", "exit 0")})
        self.assertEqual(res["status"], "FAIL", "a wrong refusal still fails")

    def test_dispositions_are_reported_apart_from_pass(self):
        for state, status in (("expected-fail", "EXPECTED FAIL"), ("accepted", "ACCEPTED")):
            disp = {"state": state, "reason": "waits for #9"}
            res = self.one({"name": "known", "run": "exit 2", "disposition": disp}, {"name": "after", "run": "true"})
            self.assertEqual((res["status"], res["reason"]), (status, "run known: exit 2 (want 0); %s: waits for #9" % state))
            self.assertEqual(res["steps"][0]["disposition"], disp)
        self.assertEqual(self.run_cmd("--scenario", "A01", "--seed", "0")[0], 1, "never counted as PASS")
        res = self.one({"name": "fixed", "run": "true", "disposition": {"state": "expected-fail", "reason": "x"}})
        self.assertEqual((res["status"], res["reason"]),
                         ("FAIL", "run fixed: exit 0 (want 0), but the step is recorded expected-fail: drop the disposition"))
        res = self.one({"name": "bare", "run": "exit 2", "disposition": {"state": "expected-fail", "reason": " "}})
        self.assertEqual((res["status"], res["events"]), ("FAIL", []))
        self.assertIn("disposition needs a state", res["reason"])


# A fake `crew` for the committed fixture steps: FAKE_UP_RC, FAKE_SPAWN_RC and FAKE_ADOPT (restart rewrites the record
# as its PR's fix pass) pick its behaviour.
FAKE_CREW = """import json, os, sys
cmd, s = sys.argv[1], os.environ["FAKE_S"]
if cmd == "up":
    sys.exit(int(os.environ.get("FAKE_UP_RC", "0")))
if cmd == "spawn":
    open(os.path.join(s, "spawned"), "w").close()
    sys.exit(int(os.environ.get("FAKE_SPAWN_RC", "1")))
if cmd == "restart":
    path = os.path.join(s, "runs", sys.argv[2] + ".json")
    rec = json.load(open(path))
    if os.environ.get("FAKE_ADOPT"):
        rec.update({"pass": "fix", "item": "issue #3, PR #7"}, args={"issue": 3, "pr": 7})
        open(path[:-5] + ".brief.md", "a").write("- Restarted after done: as Pass fix\\n")
    json.dump(rec, open(path, "w"))
    print("crew: restarted %s in its worktree %s" % (sys.argv[2], rec["worktree"]))
"""


class FixtureStepTest(unittest.TestCase):
    """The committed A03/A05 steps fail when an assertion before their last command fails (#1066 review)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.realpath(self.tmp.name)
        self.s = os.path.join(self.d, "state", "campaign__sandbox-r1")
        for sub in ("runs", "status"):
            os.makedirs(os.path.join(self.s, sub))
        os.makedirs(os.path.join(self.d, "cli"))
        with open(os.path.join(self.d, "cli", "mdstack"), "w") as fh:
            fh.write(FAKE_CREW)
        self.m = {"roots": {"state_dir": self.d + "/state", "worktree_root": self.d + "/wt", "live_dir": self.d + "/live"},
                  "source": {"path": self.d}, "run_id": "r1"}

    def tearDown(self):
        self.tmp.cleanup()

    def builder(self, n, wt):
        os.makedirs(wt, exist_ok=True)
        subprocess.run(["git", "init", "-q", wt], check=True)
        with open(os.path.join(self.s, "runs", "builder-%d.json" % n), "w") as fh:
            json.dump({"worktree": wt, "pass": "build", "item": "issue #%d" % n, "args": {"issue": n}}, fh)
        with open(os.path.join(self.s, "runs", "builder-%d.brief.md" % n), "w") as fh:
            fh.write("".join("- %s: x\n" % k for k in ("Item", "Pass", "Base", "Worktree", "Engine", "Claim")))

    def step(self, sid, name, **env):
        with open(os.path.join(TESTS, "scripts", "fixtures", "campaign", sid + ".json")) as fh:
            st = next(x for x in json.load(fh)["steps"] if x["name"] == name)
        ok, _, rec = cr.run_step(st, self.m, 1, dict(os.environ, CREW_PROJECT=self.d + "/p.toml", FAKE_S=self.s, **env))
        return ok, rec

    def test_a03_duplicate_worktrees_fail(self):
        self.builder(2, self.d + "/wt/a")
        self.builder(3, self.d + "/wt/b")
        self.assertTrue(self.step("A03", "unique-worktrees-and-run-block")[0])
        self.builder(3, self.d + "/wt/a")
        self.assertFalse(self.step("A03", "unique-worktrees-and-run-block")[0])

    def test_a03_coordinator_only_fails_when_up_fails(self):
        self.assertFalse(self.step("A03", "coordinator-only-topology", FAKE_UP_RC="1")[0])

    def test_a05_failed_adoption_fails_before_duplicate_spawn(self):
        self.builder(3, self.d + "/wt/b")
        ok, rec = self.step("A05", "done-builder-restarts-as-fix-in-same-worktree")
        self.assertFalse(ok, rec)
        self.assertFalse(os.path.exists(os.path.join(self.s, "spawned")), "no duplicate spawn after failed adoption")
        self.assertTrue(self.step("A05", "done-builder-restarts-as-fix-in-same-worktree", FAKE_ADOPT="1")[0])
        self.assertFalse(self.step("A05", "done-builder-restarts-as-fix-in-same-worktree", FAKE_ADOPT="1",
                                   FAKE_SPAWN_RC="0")[0], "an accepted duplicate spawn fails the step")


class IssueFixtureFieldsTest(unittest.TestCase):
    """Every committed scenario's issue-list.json literal carries the fields route.dependents() requests (#1174).
    The campaign gh stub serves that file to every unlabelled `gh issue list`, whatever `--json` asks for."""

    def test_issue_list_literals_carry_dependents_fields(self):
        with open(os.path.join(os.path.dirname(SCRIPTS), "environments", "terminal", "crew.d", "route.py")) as fh:
            body = fh.read().split("def dependents(", 1)[1].split("\ndef ", 1)[0]
        fields = set(re.search(r'"--json", "([^"]+)"', body).group(1).split(","))
        self.assertIn("body", fields)
        root, seen = os.path.join(TESTS, "scripts", "fixtures", "campaign"), 0
        for name in sorted(os.listdir(root)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(root, name)) as fh:
                steps = json.load(fh)["steps"]
            for st in steps:
                for lit in re.findall(r"'(\[[^']*\])' > \$G/issue-list\.json", st.get("run", "")):
                    for issue in json.loads(lit):
                        seen += 1
                        self.assertFalse(fields - set(issue), "%s step %s: issue %s lacks %s"
                                         % (name, st["name"], issue.get("number"), sorted(fields - set(issue))))
        self.assertGreater(seen, 1, "the literal scan found the A04 and A08 issue fixtures")


class A12ReproTest(unittest.TestCase):
    """The A12 validator reproduction: agrees at head, refuses a stale capture, and diffs changed output."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.join(self.tmp.name, "repo")
        git = lambda *a: subprocess.run(["git", "-C", self.d, *a], check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", self.d], check=True)
        with open(os.path.join(self.d, "say"), "w") as fh:
            fh.write("echo hi; echo oops >&2; exit 4\n")
        git("add", "say")
        git("-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "t")
        self.head = subprocess.run(["git", "-C", self.d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def repro(self, sha, text):
        path = os.path.join(self.tmp.name, "capture.md")
        with open(path, "w") as fh:
            fh.write("Proof R1 · `scripts/evidence-cli.py` · sha `%s` · cwd `.`\n\n```sh\nsh say\n```\n\n```text\n%s```\n" % (sha, text))
        return subprocess.run(["python3", os.path.join(TESTS, "scripts", "fixtures", "campaign", "A12-sample", "repro.py"), path, self.d],
                              capture_output=True, text=True)

    def test_agrees_at_head_ignoring_notes(self):
        p = self.repro(self.head, "# volatile: none\nexit: 4\n--- stdout\nhi\n--- stderr\noops\n")
        self.assertEqual((p.returncode, p.stdout), (0, "agrees\n"), p.stderr)

    def test_stale_capture_refused(self):
        p = self.repro("0" * 40, "exit: 4\n--- stdout\nhi\n--- stderr\noops\n")
        self.assertEqual((p.returncode, p.stdout), (1, "stale: capture %s, head %s\n" % ("0" * 40, self.head)))

    def test_changed_exit_or_output_disagrees(self):
        for text in ("exit: 0\n--- stdout\nhi\n--- stderr\noops\n", "exit: 4\n--- stdout\nho\n--- stderr\noops\n"):
            p = self.repro(self.head, text)
            self.assertEqual(p.returncode, 1)
            self.assertTrue(p.stderr.startswith("disagrees\n"), p.stderr)


class A23TransportTest(unittest.TestCase):
    """The A23 fake SSH: loops back to the real entrypoint; `down` never reaches the host, `lost` acts then drops."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.realpath(self.tmp.name)
        self.root = os.path.join(self.d, "host")
        os.makedirs(os.path.join(self.d, "bin"))
        os.makedirs(os.path.join(self.d, "a23"))
        shutil.copy(os.path.join(TESTS, "scripts", "fixtures", "campaign", "a23", "ssh"), os.path.join(self.d, "bin", "ssh"))
        with open(os.path.join(self.d, "a23", "hosts.json"), "w") as fh:
            json.dump({"loop": {"entry": os.path.join(os.path.dirname(SCRIPTS), "environments", "terminal", "remote", "crew-remote.py"), "root": self.root},
                       "gone": {"entry": None, "root": self.root}}, fh)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, host, rid):
        req = {"verb": "job", "version": "dev", "request_id": rid, "root": self.root, "project": "a__b", "job_id": "j"}
        return subprocess.run(["python3", os.path.join(self.d, "bin", "ssh"), "-T", host, "crew-host"],
                              input=json.dumps(req), capture_output=True, text=True)

    def acted(self, rid):
        return os.path.exists(os.path.join(self.root, "requests", rid + ".json"))

    def test_loopback_and_faults(self):
        with open(os.path.join(self.d, "a23", "faults"), "w") as fh:
            fh.write("loop job down\nloop job lost\n")
        p = self.call("loop", "r1")
        self.assertEqual((p.returncode, p.stdout, self.acted("r1")), (255, "", False))
        p = self.call("loop", "r2")
        self.assertEqual((p.returncode, p.stdout, self.acted("r2")), (255, "", True))
        p = self.call("loop", "r3")
        self.assertEqual(json.loads(p.stdout), {"result": "refused", "reason": "project mirror not prepared"})
        self.assertEqual(self.call("gone", "r4").returncode, 127)
        with open(os.path.join(self.d, "a23", "ssh.log")) as fh:
            self.assertEqual([json.loads(line)["fault"] for line in fh], ["down", "lost", None, None])


class A19LedgerTest(unittest.TestCase):
    """A19's ledger names every shipped adapter and declared row; a gap claimed as an oracle fails (#1443)."""
    A19 = os.path.join(TESTS, "scripts", "fixtures", "campaign", "a19")

    def replay(self, ledger):
        return subprocess.run(["python3", os.path.join(self.A19, "replay.py"), os.path.dirname(SCRIPTS), ledger,
                               "--no-tests"], capture_output=True, text=True)

    def test_shipped_ledger_and_claimed_gap(self):
        ledger = os.path.join(self.A19, "ledger.json")
        p = self.replay(ledger)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("A19: 6 harness x 20 rows, 2 backends x 10 rows;", p.stdout)
        with open(ledger) as fh:
            d = json.load(fh)
        d["harness"]["adapters"]["cursor"]["TRANSIENT"] = {"oracle": True, "tests": [
            "environments/test-crew-watch.py:test_scan_records_adapter_transient_text_once"]}
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "ledger.json"), "w") as fh:
                json.dump(d, fh)
            p = self.replay(os.path.join(tmp, "ledger.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("FAIL cursor TRANSIENT: oracle but the adapter lacks it", p.stdout)

    def test_live_ledger_names_every_binding_with_its_link(self):
        """A missing live binding, a block without its environment fields or a fail without its finding fails (#1439)."""
        with open(os.path.join(self.A19, "ledger.json")) as fh:
            d = json.load(fh)
        del d["live"]["codex/tmux"]
        d["live"]["grok-bot/mirror-watch"]["block"].pop("account")
        d["live"]["claude-code/tmux"].pop("finding")
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "ledger.json"), "w") as fh:
                json.dump(d, fh)
            p = self.replay(os.path.join(tmp, "ledger.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("FAIL live bindings:", p.stdout)
        self.assertIn("FAIL live claude-code/tmux: a fail needs its filed finding", p.stdout)
        self.assertIn("FAIL live grok-bot/mirror-watch: a block names installation, version, account and sandbox",
                      p.stdout)

    def test_smoke_blocks_every_binding_without_installed_clis(self):
        """smoke.py with no harness or backend CLI on PATH runs nothing and blocks each binding (#1439)."""
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "bin"))
            os.symlink(shutil.which("git"), os.path.join(tmp, "bin", "git"))
            p = subprocess.run([sys.executable, os.path.join(self.A19, "smoke.py"), os.path.dirname(SCRIPTS),
                                os.path.join(tmp, "runs")], capture_output=True, text=True,
                               env=dict(os.environ, PATH=os.path.join(tmp, "bin")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "runs")))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        recs = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(len(recs), 12)
        self.assertTrue(all(r["result"] == "blocked" and r["block"].startswith("installation: ") for r in recs))

    def smoke_claude(self, tmp, trusted):
        """smoke.py --only claude-code/tmux on a shared clone of this source. The fake claude records its worktree's git
        common dir and HEAD, says ready, acks the inbox line and sleeps; its symlink target is named `sleep`, so the
        exec'd sleep is the expected foreground. Claude Code trust is read from a temp config dir (#1470)."""
        src, cfg, bin_, real = (os.path.join(tmp, d) for d in ("src", "cfg", "bin", "real"))
        subprocess.run(["git", "clone", "-q", "--shared", os.path.dirname(SCRIPTS), src], check=True)
        for d in (cfg, bin_, real):
            os.makedirs(d)
        with open(os.path.join(cfg, ".claude.json"), "w") as fh:
            json.dump({"projects": {os.path.realpath(src): {"hasTrustDialogAccepted": True}} if trusted else {}}, fh)
        with open(os.path.join(real, "sleep"), "w") as fh:
            fh.write('#!/bin/sh\ncase "$*" in *--version*) echo "fake 1.0"; exit 0;; esac\n'
                     'git rev-parse --path-format=absolute --git-common-dir HEAD > "%s/seen"\n'
                     'echo ready >> "$CREW_STATUS"\n'
                     '(while ! [ -s "$CREW_INBOX" ]; do sleep 0.2; done\n'
                     ' sed -n \'s/.*"id": "\\([^"]*\\)".*/ack: \\1/p\' "$CREW_INBOX" >> "$CREW_STATUS") &\n'
                     'exec /bin/sleep 30\n' % tmp)
        os.chmod(os.path.join(real, "sleep"), 0o755)
        os.symlink(os.path.join(real, "sleep"), os.path.join(bin_, "claude"))
        sock = tempfile.mkdtemp(prefix="a19", dir="/tmp")  # a socket path under a long temp dir is too long
        self.addCleanup(shutil.rmtree, sock, True)
        p = subprocess.run([sys.executable, os.path.join(self.A19, "smoke.py"), src, os.path.join(tmp, "runs"),
                            "--only", "claude-code/tmux"], capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"], CLAUDE_CONFIG_DIR=cfg,
                                    TMUX_TMPDIR=sock))
        recs = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{")]
        return os.path.realpath(src), p, recs

    def test_smoke_blocks_claude_on_unmet_checkout_trust(self):
        """An untrusted source checkout blocks claude-code with doctor's role trust fix and creates no run (#1470)."""
        with tempfile.TemporaryDirectory() as tmp:
            src, p, recs = self.smoke_claude(tmp, trusted=False)
            self.assertFalse(os.path.exists(os.path.join(tmp, "runs")))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([r["result"] for r in recs], ["blocked"])
        self.assertTrue(recs[0]["block"].startswith("precondition: claude role trust not accepted for %s: before "
                                                    "dispatch, run claude once in %s" % (src, src)), recs[0]["block"])

    @unittest.skipUnless(shutil.which("tmux"), "tmux not on PATH")
    def test_smoke_runs_in_a_linked_worktree_of_the_source_and_removes_only_it(self):
        """The run's worktree is a detached linked worktree of SOURCE at its HEAD, removed after the stop (#1470)."""
        with tempfile.TemporaryDirectory() as tmp:
            src, p, recs = self.smoke_claude(tmp, trusted=True)
            with open(os.path.join(tmp, "seen")) as fh:
                seen = fh.read().split()
            head = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
            worktrees = subprocess.run(["git", "-C", src, "worktree", "list", "--porcelain"], capture_output=True,
                                       text=True).stdout
            self.assertFalse(os.path.exists(os.path.join(tmp, "runs", "tmux", "claude-code", "wt")))
        self.assertEqual(seen, [os.path.join(src, ".git"), head.strip()], p.stdout + p.stderr)
        self.assertEqual(worktrees.count("worktree "), 1, worktrees)
        steps = recs[0]["steps"]
        self.assertEqual((recs[0]["source"], steps["ready"], steps["ack"]), (head.strip(), "ok", "ok"))
        self.assertTrue(steps["stop"].startswith("ok: "), steps)


class A22OracleTest(unittest.TestCase):
    """A22's duplicate-key oracle on the real triage scan of its seeded forge: a run id with capitals passes (#1177)."""

    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("crew_cli", os.path.join(os.path.dirname(SCRIPTS), "cli", "mdstack"))
        cls.crew = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(cls.crew)
        with open(os.path.join(TESTS, "scripts", "fixtures", "campaign", "A22.json")) as fh:
            run = json.load(fh)["steps"][0]["run"]
        cls.forge = run.split("cat > {state_dir}/forge.py <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        cls.oracle = re.search(r'python3 -c "(import json,sys; i=\{e\[.ref.\]: e[^"]*)" \$S/triage/queue\.json \$R', run)[1]

    def oracle_on(self, run_id):
        repo = "campaign/sandbox-" + run_id
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "forge.py"), "w") as fh:
                fh.write(self.forge)
            subprocess.run(["python3", os.path.join(d, "forge.py"), "seed", repo], check=True,
                           env=dict(os.environ, CAMPAIGN_GH_DIR=d))
            items = []
            for s in ("open", "closed"):
                with open(os.path.join(d, "issue-list-%s.json" % s)) as fh:
                    items.append(json.load(fh))
            entries = self.crew.triage_scan(repo, *items, self.crew.TRIAGE_RULES, {"sandbox-owner"},
                                            self.crew.triage_card_fields(), ("sandbox-coordinator", "Ash"))
            with open(os.path.join(d, "queue.json"), "w") as fh:
                json.dump({"items": entries}, fh)
            return subprocess.run(["python3", "-c", self.oracle, os.path.join(d, "queue.json"), repo],
                                  capture_output=True, text=True)

    def test_source_key_is_case_insensitive(self):
        for run_id in ("m25f-A22", "m25f-a22"):
            p = self.oracle_on(run_id)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("source:campaign/sandbox-%s#20" % run_id.lower(), p.stdout)


if __name__ == "__main__":
    unittest.main()
