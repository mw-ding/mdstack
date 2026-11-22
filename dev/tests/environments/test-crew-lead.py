"""Pool-lead fixtures: presence caps, idle and busy builders, identity-based restart, durable handoff
replay and cleanup boundaries. Fake tmux and GitHub; no model or network calls. Run in CI.
"""
import argparse
import json
import os
import shutil
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import LivenessBase, SendBase

TRANSCRIPT = "--transcript" in sys.argv or "--presence-transcript" in sys.argv


class BuilderLead(LivenessBase):
    def test_pi_pool_lead_uses_adapter_and_probes_alive(self):
        with open(self.project, "a") as f:
            f.write('\n[engines.default]\norder = ["pi/anthropic/claude-sonnet-4-5"]\n')
        self.assertEqual(self.ensure(), 0)
        self.assertIn("exec pi --approve --model anthropic/claude-sonnet-4-5 --thinking medium ",
                      self.lead_windows()[0][-1])
        self.assertEqual(self.lead_record()["harness"], "pi")
        self.assertEqual(self.snapshot()["readiness"], "alive")

    def setUp(self):
        super().setUp()
        self.lead = self.mod.commands()["lead"]
        self.args = argparse.Namespace(project=self.project, org_profile=None, timeout=1)
        self.put("render/runtime/builder-lead.md", "Manage the builder pool; never build.\n")

    def ensure(self):
        with mock.patch.dict(os.environ, self.env):
            return self.lead.ensure(self.args, "builder")

    def lead_record(self):
        return dict(self.lead.records(self.state))["ben-lead"]

    def lead_windows(self):
        return [c for c in self.calls() if c[0] == "new-window" and c[c.index("-n") + 1] == "ben-lead"]

    def snapshot(self):
        with mock.patch.dict(os.environ, self.env):
            windows = dict((n, i) for i, n in self.mod.tmux.list_windows("crew-acme-widgets"))
            ready = self.mod.probe("crew-acme-widgets", "ben-lead", self.lead_record(), windows)
        return dict(lead_restarts=self.lead_record()["restarts"], pending=len(self.lead.pending(self.state, "ben-lead")),
                    worker_present=os.path.isdir(self.record("ben-7")["worktree"]), readiness=ready)

    def test_solo_build_and_fix_handoffs_never_start_lead_or_worker(self):
        self.env["FAKE_SOLO_ISSUE"] = "8"
        self.env["FAKE_SOLO_PR"] = "12"
        with mock.patch.dict(os.environ, self.env):
            for kind, refs in (("build", ["#8"]), ("fix", ["#12", "a" * 40]),
                               ("ci-red", ["#12", "a" * 40]), ("merge-up", ["#12", "a" * 40])):
                self.assertEqual(self.lead.handoff(self.args, "builder", kind, refs), 0)
        self.assertEqual(self.lead_windows(), [])
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ben-lead.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "ben-8.json")))


    def test_presence_switches_both_pools_without_stopping_workers(self):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('name = "tmux"\n',
                                'name = "tmux"\noptions = { builders = 5, reviewers = 4, present_builders = 1, present_reviewers = 1, max_suites = 1 }\n'))
        self.put("away-control.json", '{"issue": 99}')
        comments = []
        worker = self.record("ben-7")
        original = self.mod.subprocess.run

        def backend(argv, **kwargs):
            if argv[:2] == ["gh", "api"]:
                return mock.Mock(returncode=0, stdout=json.dumps([comments]))
            return original(argv, **kwargs)

        def record(state, entry, source, **flags):
            data = dict(state=state, entry=entry, **flags)
            cmd = "away" if state == "away" else "away-return"
            record_text = "`" + json.dumps(data) + "`\n" if state == "returned" else "```json\n" + json.dumps(data) + "\n```\n"
            comments.append(dict(user=dict(login="acme-bot"), body=(
                record_text +
                "<!-- crew:v1 role=coordinator pass=steer cmd=%s cmd-id=%s sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa round=n/a verdict=n/a -->\n"
                "— Ash (CTO) · codex · gpt-6.1-sol" % (cmd, source))))

        def check(expected):
            for role, cap in zip(("builder", "reviewer"), expected):
                self.assertEqual(self.mod.pool_cap(self.mod.profile(self.args)[0], role, self.state), cap)
                if TRANSCRIPT:
                    print("presence %s: cap=%d" % (role, cap))
            self.assertEqual(self.mod.over_cap(self.mod.profile(self.args)[0], "builder", {"ben-7": 10}, self.state), expected[0] <= 1)
            self.assertEqual(self.record("ben-7"), worker)
            self.assertTrue(os.path.isdir(worker["worktree"]))

        with mock.patch.dict(os.environ, self.env), mock.patch.object(self.mod.subprocess, "run", side_effect=backend), \
                mock.patch("os.getloadavg", return_value=(0, 0, 0)), mock.patch("os.cpu_count", return_value=4):
            check((1, 1))
            record("away", "a", "a", until="2020-01-01T00:00:00Z")
            check((5, 4))  # until alone is not a return
            record("returned", "a", "b")
            check((1, 1))
            record("away", "c", "c", quiet=True)
            check((1, 1))
            record("away", "d", "d", cap=1)
            check((1, 0))  # existing builder consumes the global bound
            record("away", "e", "e")
            comments[-1]["user"]["login"] = "untrusted"
            check((1, 0))
            self.assertFalse(any(c[0] == "kill-window" for c in self.calls()))
            if TRANSCRIPT:
                print("present -> away -> returned -> quiet -> away cap=1; live worker preserved; exit 0")

    def test_away_record_sign_matches_current_or_legacy_coordinator_title(self):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('name = "tmux"\n',
                                'name = "tmux"\noptions = { builders = 5, reviewers = 4, present_builders = 1, present_reviewers = 1 }\n'))
        self.put("away-control.json", '{"issue": 99}')
        for title, cap in (("CTO", 5), ("Coordinator", 5), ("Builder", 1)):
            body = ("```json\n" + json.dumps(dict(state="away", entry="a")) + "\n```\n"
                    "<!-- crew:v1 role=coordinator pass=steer cmd=away cmd-id=a sha=%s round=n/a verdict=n/a -->\n"
                    "— Ash (%s) · codex · gpt-6.1-sol" % ("a" * 40, title))
            out = mock.Mock(returncode=0, stdout=json.dumps([[dict(user=dict(login="acme-bot"), body=body)]]))
            with mock.patch.dict(os.environ, self.env), mock.patch.object(self.mod.subprocess, "run", return_value=out):
                self.assertEqual(self.mod.pool_cap(self.mod.profile(self.args)[0], "builder", self.state), cap, title)

    def test_recovery_decisions_do_not_restart_ambiguous_or_active(self):
        for state in ("dead", "missing"):
            self.assertEqual(self.lead.recovery(state, 0), "restart")
            self.assertEqual(self.lead.recovery(state, 1), "blocked")
        self.assertEqual(self.lead.recovery("ambiguous", 0), "blocked")
        self.assertEqual(self.lead.recovery("alive", 0), "none")

    def test_live_lead_is_unique_and_outside_worker_cap(self):
        worker = self.record("ben-7")
        self.assertEqual(self.ensure(), 0)
        self.assertEqual(self.ensure(), 0)
        self.assertEqual(len(self.lead_windows()), 1)
        self.assertEqual(self.lead_record()["index"], 2)
        self.assertEqual(self.record("ben-7"), worker)
        call = self.lead_windows()[0]
        env = [call[i + 1] for i, arg in enumerate(call) if arg == "-e"]
        self.assertIn("CREW_POOL=builder", env)
        self.assertNotIn("GH_TOKEN", " ".join(env))

    def test_fresh_lead_can_append_its_first_ack(self):  # #1176: a fresh state root has no status/
        shutil.rmtree(os.path.join(self.state, "status"), ignore_errors=True)
        self.assertEqual(self.ensure(), 0)
        call = self.lead_windows()[0]
        status = next(call[i + 1] for i, arg in enumerate(call) if arg == "-e" and call[i + 1].startswith("CREW_STATUS="))
        with open(status.split("=", 1)[1], "a") as f:
            f.write("ack: work-1\n")

    def test_restart_preserves_live_workers_and_pending_queue(self):
        self.assertEqual(self.ensure(), 0)
        inbox = "inbox/ben-lead.jsonl"
        self.put(inbox, json.dumps(dict(id="work-1", kind="build", refs=["#8"])) + "\n")
        if TRANSCRIPT:
            print("before restart: " + json.dumps(self.snapshot()))
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 2)
        self.assertEqual(self.ensure(), 0)
        self.assertEqual(self.lead_record()["restarts"], 1)
        self.assertEqual(self.lead.pending(self.state, "ben-lead")[0]["id"], "work-1")
        self.assertTrue(os.path.isdir(self.record("ben-7")["worktree"]))
        if TRANSCRIPT:
            print("after restart: " + json.dumps(self.snapshot()))
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 2)
        self.assertEqual(self.ensure(), 1)
        self.assertEqual(len(self.lead_windows()), 2)
        if TRANSCRIPT:
            print("second recovery: blocked; no duplicate lead; worker and handoff preserved")

    def test_ambiguous_lead_stays_and_escalates(self):
        self.assertEqual(self.ensure(), 0)
        self.set_pane(2, command="sleep")
        self.assertEqual(self.ensure(), 1)
        self.assertEqual(len(self.lead_windows()), 1)

    def test_handoff_replay_reuses_durable_event_and_message(self):
        wake = dict(event="issue-assigned", refs=["#8"])
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.event(self.args, "builder", wake), 0)
            self.assertEqual(self.lead.event(self.args, "builder", wake), 0)
        pending = self.lead.pending(self.state, "ben-lead")
        self.assertEqual(len(pending), 1)
        self.assertTrue(os.path.isfile(pending[0]["refs"][0]))
        self.put("status/ben-lead.status", "ack: %s\ndone: %s\n" % (pending[0]["id"], pending[0]["id"]))
        self.assertEqual(self.lead.pending(self.state, "ben-lead"), [])

    def test_resend_after_done_starts_a_new_handoff(self):  # #712: a withdrawn id is never reported acked
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.handoff(self.args, "builder", "build", ["#639"]), 0)
            first = self.lead.pending(self.state, "ben-lead")
            self.put("status/ben-lead.status", "ack: %s\ndone: %s\n" % (first[0]["id"], first[0]["id"]))
            self.assertEqual(self.lead.handoff(self.args, "builder", "build", ["#639"]), 0)
        again = self.lead.pending(self.state, "ben-lead")
        self.assertEqual([(m["kind"], m["refs"]) for m in again], [("build", ["#639"])])
        self.assertNotEqual(again[0]["id"], first[0]["id"])

    def test_train_handoff_reaches_the_lead_and_its_worker_dequeues_by_train_ref(self):  # #1391
        refs = ["train-5", "b" * 40, "#12", "a" * 40]
        with mock.patch.dict(os.environ, self.env, FAKE_SOLO_PR="12"):  # no solo lookup: a train has no item
            self.assertEqual(self.lead.handoff(self.args, "builder", "train", refs), 0)
        self.assertEqual([(m["kind"], m["refs"]) for m in self.lead.pending(self.state, "ben-lead")], [("train", refs)])
        self.put("spawn-queue.jsonl", json.dumps(dict(role="builder", issue=None, pr=None, train=5, **{
            "pass": "train", "round": 1, "tier": "default", "head": None})) + "\n")
        self.crew("dequeue", "--ref", "#None", "--project", self.project, CREW_POOL="builder")
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "ben-train5.json")))
        result = self.crew("dequeue", "--ref", "train-5", "--project", self.project, CREW_POOL="builder")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.record("ben-train5")["args"]["train"], 5)

    def test_other_pool_cannot_dequeue_builder_and_lead_can(self):
        self.put("spawn-queue.jsonl", json.dumps(dict(role="builder", issue=8, pr=None, **{
            "pass": "build", "round": 1, "tier": "default", "head": None})) + "\n")
        self.assertEqual(self.crew("dequeue", "--project", self.project).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "ben-8.json")))
        result = self.crew("dequeue", "--project", self.project, CREW_POOL="builder")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.state, "runs", "ben-8.json")))

    def test_done_builder_with_running_tool_session_still_counts(self):
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % ("a" * 40))
        with open(self.ps, "w") as f:
            json.dump({"children": [[42, 9000010, "S", "codex.real"], [43, 42, "Ss", "python3"]]}, f)
        with mock.patch.dict(os.environ, self.env):
            self.assertIsNone(self.mod.idle_builder(self.state, "ben-7"))
        if TRANSCRIPT:
            print("done builder with running Python child: busy, not reclaimable")

    def test_helpers_are_idle_reclaimable_and_not_suites_but_tool_sessions_are_busy(self):
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % ("a" * 40))
        status = os.path.join(self.state, "status", "ben-7.status")
        os.utime(status, (100, 100))
        values, _, _ = self.mod.profile(self.args)
        dequeue = self.mod.commands()["dequeue"]
        for harness in ("codex", "claude"):
            rec = self.record("ben-7")
            rec["harness"] = harness
            self.put("runs/ben-7.json", json.dumps(rec))
            self.set_pane(10, command=harness)
            helpers = [[42, 9000010, "S+", harness + ".real"], [43, 42, "S", "mcp-server"],
                       [44, 43, "S", "python3"], [45, 42, "S", "sleep"]]
            for busy in (False, True):
                with self.subTest(harness=harness, busy=busy):
                    with open(self.ps, "w") as f:
                        json.dump({"children": helpers + ([[46, 43, "Ss", "python3"]] if busy else [])}, f)
                    with mock.patch.dict(os.environ, self.env), \
                            mock.patch.object(self.mod.commands()["route"], "gh", return_value={"state": "OPEN"}), \
                            mock.patch.object(dequeue, "unlanded", return_value=[]), \
                            mock.patch.object(dequeue, "kill_run", return_value=[]) as kill:
                        self.assertEqual(self.mod.idle_builder(self.state, "ben-7"), None if busy else 100)
                        self.assertEqual(self.lead.suites(values, self.state), int(busy))
                        wakes = self.mod.scan(self.state, "crew-acme-widgets", 1900, 900, {"offsets": {}, "keys": {}})
                        self.assertEqual(any(w["reason"] == "idle-builder" for w in wakes), not busy)
                        dequeue.reclaim(values, "crew-acme-widgets", self.state, {"ben-7": 10})
                        self.assertEqual(kill.call_count, 0 if busy else 1)
                    if TRANSCRIPT:
                        print("%s: helpers only=%s; active=%d suites=%d reclaim=%s expiry=%s" %
                              (harness, not busy, busy, busy, not busy, not busy))

    def test_suite_probe_excludes_closed_and_merged_items(self):
        with open(self.ps, "w") as f:
            json.dump({"children": [[42, 9000010, "Ss", "python3"]]}, f)
        values, _, _ = self.mod.profile(self.args)
        route = self.mod.commands()["route"]
        for state, expected in (("OPEN", 1), ("CLOSED", 0), ("MERGED", 0)):
            with mock.patch.dict(os.environ, self.env), mock.patch.object(route, "gh", return_value={"state": state}):
                self.assertEqual(self.lead.suites(values, self.state), expected)
        if TRANSCRIPT:
            print("suite probe: live item=1; same processes attached to closed/merged item=0")

    def test_suite_probe_records_a_counted_builders_unwoken_wait(self):  # #1950
        with open(self.ps, "w") as f:
            json.dump({"children": [[42, 9000010, "Ss", "python3"]]}, f)
        values, _, _ = self.mod.profile(self.args)
        route = self.mod.commands()["route"]
        line = "waiting: #1949 fix id=s1"
        cases = [("OPEN", "ack: s1\n%s\n" % line, "builder", 1, [dict(window="ben-7", ref="#1949", line=line)]),
                 ("OPEN", "%s\nack: s2\n" % line, "builder", 1, []), ("OPEN", "%s\n" % line, "reviewer", 1, []),
                 ("OPEN", "waiting: #1949\n", "builder", 1, []), ("CLOSED", "%s\n" % line, "builder", 0, [])]
        for state, status, role, count, expected in cases:
            with self.subTest(state=state, status=status, role=role):
                self.put("status/ben-7.status", status)
                self.put("runs/ben-7.json", json.dumps(dict(self.record("ben-7"), role=role)))
                waits = []
                with mock.patch.dict(os.environ, self.env), mock.patch.object(route, "gh", return_value={"state": state}):
                    self.assertEqual(self.lead.suites(values, self.state, None, waits), count)
                self.assertEqual(waits, expected)

    def test_done_builder_with_unacked_spawn_build_message_is_idle(self):
        status = os.path.join(self.state, "status", "ben-7.status")
        cases = [("build", ["#7"], 100), ("build", ["#8"], None), ("fix", ["#12", "a" * 40], None)]
        for kind, refs, idle in cases:
            with self.subTest(kind=kind, refs=refs):
                self.put("status/ben-7.status", "done: #7 #12 %s\n" % ("a" * 40))
                os.utime(status, (100, 100))
                self.put("inbox/ben-7.jsonl", json.dumps(dict(id="lost", kind=kind, refs=refs)) + "\n")
                with mock.patch.dict(os.environ, self.env):
                    self.assertEqual(self.mod.idle_builder(self.state, "ben-7"), idle)
        if TRANSCRIPT:
            print("done #7 with unacked build #7: idle; unacked build #8 or fix: busy")

    def test_watcher_expires_idle_builder_and_preserves_busy_child(self):
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % ("a" * 40))
        status = os.path.join(self.state, "status", "ben-7.status")
        os.utime(status, (100, 100))
        with mock.patch.dict(os.environ, self.env):
            seen = {"offsets": {}, "keys": {}}
            self.assertFalse(any(w["reason"] == "idle-builder" for w in self.mod.scan(self.state, "crew-acme-widgets", 1899, 900, seen)))
            self.assertTrue(any(w["reason"] == "idle-builder" for w in self.mod.scan(self.state, "crew-acme-widgets", 1900, 900, seen)))
            self.assertFalse(any(w["reason"] == "idle-builder" for w in self.mod.scan(self.state, "crew-acme-widgets", 2000, 900, seen)))
            with open(self.ps, "w") as f:
                json.dump({"children": [[42, 9000010, "Ss", "python3"]]}, f)
            self.assertFalse(any(w["reason"] == "idle-builder" for w in self.mod.scan(self.state, "crew-acme-widgets", 3000, 900, seen)))

    def test_policy_messages_only_relax_idle_detection(self):
        done = "done: #7 #12 %s\n" % ("a" * 40)
        policy = dict(id="policy", kind="owner-policy", refs=[])
        cases = [(done, [policy], True), (done + "ack: policy\nheartbeat: now\n", [policy], True),
                 ("ack: policy\n", [policy], False), (done + "ack: missing\nack: policy\n", [policy], False)]
        for kind in ("fix", "ci-red", "merge-up", "build", "unknown"):
            work = dict(id="work", kind=kind, refs=["#8"])
            cases += [(done, [work, policy], False),
                      (done + "ack: work\nack: policy\n", [work, policy], False),
                      ("ack: work\n" + done + "ack: policy\n", [work, policy], True)]
        for line in ("working: #7", "progress: #7", "blocked: #7", "failed: #7"):
            cases.append((done + line + "\nack: policy\n", [policy], False))
        status = os.path.join(self.state, "status", "ben-7.status")
        for text, messages, idle in cases:
            with self.subTest(status=text, messages=messages):
                self.put("status/ben-7.status", text)
                self.put("inbox/ben-7.jsonl", "".join(json.dumps(m) + "\n" for m in messages))
                os.utime(status, (100, 100))
                with mock.patch.dict(os.environ, self.env):
                    self.assertEqual(self.mod.idle_builder(self.state, "ben-7"), 100 if idle else None)
        self.put("status/ben-7.status", done + "ack: policy\n")
        self.put("inbox/ben-7.jsonl", json.dumps(policy) + "\n")
        os.utime(status, (100, 100))
        with mock.patch.dict(os.environ, self.env):
            seen = {"offsets": {}, "keys": {}}
            for now, count in ((1899, 0), (1900, 1), (2000, 0)):
                wakes = self.mod.scan(self.state, "crew-acme-widgets", now, 900, seen)
                self.assertEqual(sum(w["reason"] == "idle-builder" for w in wakes), count)
            with open(self.ps, "w") as f:
                json.dump({"children": [[42, 9000010, "Ss", "python3"]]}, f)
            self.assertIsNone(self.mod.idle_builder(self.state, "ben-7"))

    def test_last_suite_completion_retries_pending_requests_in_both_pools(self):
        self.assertEqual(self.ensure(), 0)
        self.put("render/runtime/reviewer-lead.md", "Manage the reviewer pool.\n")
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.ensure(self.args, "reviewer"), 0)
        for name in ("ben-lead", "vera-lead"):
            self.put("inbox/" + name + ".jsonl", json.dumps(dict(id="deferred", kind="build", refs=["#8"])) + "\n")
            self.put("status/" + name + ".status", "ack: deferred\n")
        rec = self.record("ben-7")
        rec["role"] = "reviewer"
        rec["args"]["pr"] = 12
        self.put("runs/ben-7.json", json.dumps(rec))
        gh = os.path.join(self.tmp, "bin", "gh")  # the reviewer's PR is still open: no reap (#811)
        with open(gh, "w") as f:
            f.write("#!/usr/bin/env python3\nimport json\nprint(json.dumps({'state': 'OPEN', 'labels': []}))\n")
        os.chmod(gh, 0o755)
        before = len(self.calls())
        self.put("wake/queue.jsonl", json.dumps(dict(reason="status", window="ben-7", line="done: stale")) + "\n")
        result = self.crew("route", "--project", self.project, "--timeout", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        nudges = [c for c in self.calls()[before:] if c[0] == "send-keys" and "inbox: deferred" in c]
        self.assertEqual({c[c.index("-t") + 1] for c in nudges}, {"=crew-acme-widgets:2", "=crew-acme-widgets:3"})
        if TRANSCRIPT:
            print("last suite completed: both pending pools nudged; no coordinator handoff")

    def test_pending_admission_has_recurring_backstop_until_completed(self):
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="deferred", kind="build", refs=["#8"])) + "\n")
        self.put("status/ben-lead.status", "ack: deferred\n")
        now = 2_000_000_000
        self.assertFalse(any(w["reason"] == "lead-backstop" for w in self.scan(now)))
        self.assertFalse(any(w["reason"] == "lead-backstop" for w in self.scan(now + 59, self.seen)))
        wakes = [w for w in self.scan(now + 60, self.seen) if w["reason"] == "lead-backstop"]
        self.assertEqual([w["window"] for w in wakes], ["ben-lead"])
        before = len(self.calls())
        self.put("wake/queue.jsonl", json.dumps(wakes[0]) + "\n")
        self.assertEqual(self.crew("route", "--project", self.project, "--timeout", "1").returncode, 0)
        self.assertTrue(any(c[0] == "send-keys" and "inbox: deferred" in c for c in self.calls()[before:]))
        self.assertFalse(any(w["reason"] == "lead-backstop" for w in self.scan(now + 179, self.seen)))
        self.assertEqual([w["reason"] for w in self.scan(now + 180, self.seen) if w["reason"] == "lead-backstop"],
                         ["lead-backstop"])
        self.put("status/ben-lead.status", "ack: deferred\ndone: deferred\n")
        self.assertFalse(any(w["reason"] == "lead-backstop" for w in self.scan(now + 2000, self.seen)))
        if TRANSCRIPT:
            print("deferral backstop: retry at 60 s, again 120 s later; completed request stops retries")

    def retries(self, start, probes, seen=None):
        """Offsets in `probes` (seconds after `start`, scanned in order, state carried) whose scan woke the lead."""
        self.seen, times = seen or {"offsets": {}, "keys": {}}, []
        for t in sorted(set(probes) | {0}):  # the scan that first sees the demand arms its timer
            if any(w["reason"] == "lead-backstop" for w in self.scan(start + t, self.seen)):
                times.append(t)
        return times

    @staticmethod
    def edges(*due):
        """Each due offset and the second before it: a wake must land on the first and never the second."""
        return {t for d in due for t in (d - 1, d)}

    def poll(self, ci, held=()):
        self.put("poll-state.json", json.dumps({"observed": {"19": {"head": "a" * 40, "ci": ci}}, "held": list(held)}))

    def test_unchanged_demand_backs_off_to_the_cap_and_changed_demand_restarts(self):  # #1715
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="a", kind="build", refs=["#8"])) + "\n")
        self.put("status/ben-lead.status", "ack: a\n")
        now = 2_000_000_000
        schedule = [60, 180, 420, 900, 1800, 2700]
        self.assertEqual(self.retries(now, self.edges(*schedule)), schedule)
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(dict(id=i, kind="build", refs=["#8"])) + "\n"
                                                 for i in ("a", "b")))
        self.assertEqual(self.retries(now + 2701, self.edges(60, 180), self.seen), [60, 180])  # new set: 60 s again
        restarted = json.loads(json.dumps(self.seen))  # watch-state.json across a watcher restart
        self.assertEqual(self.retries(now + 2902, self.edges(219), restarted), [219])  # 240 s after +2881: kept
        if TRANSCRIPT:
            print("unchanged demand: 60/120/240/480/900/900; new id restarts at 60; restart keeps the timer")

    def test_acknowledged_waits_never_renudge_until_their_state_changes(self):  # #1715
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(dict(id=i, kind="land", refs=["#19", "a" * 40])) + "\n"
                                                 for i in ("owner", "ci")))
        self.poll("pending")
        waits = "ack: owner\nack: ci\nwaiting: #19 owner id=owner\nwaiting: #19 ci id=ci\n"
        self.put("status/ben-lead.status", waits)
        now = 2_000_000_000
        self.assertEqual(self.retries(now, range(0, 3601, 120)), [])  # an hour of unchanged waits: no wake
        self.assertEqual(self.backstop(waits), ([], []))
        self.assertEqual(self.backstop(waits, recheck=False), ([], []))  # slot release or coordinator backstop
        restarted = json.loads(json.dumps(self.seen))
        self.poll("success")  # terminal CI state, seen token-free in mdstack poll's snapshot
        wakes = [w for w in self.scan(now + 3601, restarted) if w["reason"] == "lead-backstop"]
        self.assertEqual([w["window"] for w in wakes], ["ben-lead"])  # on that scan, not after a deadline
        self.assertEqual(self.backstop(waits), (["owner"], []))
        self.put("status/ben-lead.status", waits + "waiting: #19 owner id=owner\nwaiting: #19 ci id=ci\n")
        self.assertEqual(self.retries(now + 3602, range(0, 3601, 120), self.seen), [])  # re-reported: quiet again
        if TRANSCRIPT:
            print("owner and CI waits: 0 wakes in 1 h; CI success wakes at once; re-reported waits are quiet")

    def test_incident_acks_and_hold_churn_never_rearm_a_wait(self):  # #1836: vera-lead's #1833 status shape
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="h", kind="work", refs=["/e.json"])) + "\n")
        sample = dict(state="OPEN", head="a" * 40, ci="pending", verdict=None, mergeable="MERGEABLE", hold=False,
                      ready=False)
        poll = {"observed": {"19": sample}, "held": [], "answers": {}}

        def update(status=None, **fields):
            def apply():
                sample.update(fields)
                held = sample["hold"]
                poll.update(held=["#19"] if held else [], answers={"#19": 3} if held else {})
                self.put("poll-state.json", json.dumps(poll))
                if status:
                    self.put("status/ben-lead.status", status)
            return apply

        waits = "ack: h\nwaiting: #19 owner id=h\n"
        update(waits)()
        changes = {60: update(hold=True, verdict="changes"),  # poll catches up on the escalation the lead saw live
                   120: update(waits + "ack: h\n"), 180: update(waits + "ack: h\nack: h\n"),  # dispatcher re-acks
                   870: update(mergeable="UNKNOWN"), 930: update(mergeable="MERGEABLE")}  # GitHub recomputes
        now, woke = 2_000_000_000, []
        self.seen = {"offsets": {}, "keys": {}}
        for t in range(0, 961, 30):
            if t in changes:
                changes[t]()
            if any(w["reason"] == "lead-backstop" for w in self.scan(now + t, self.seen)):
                woke.append(t)
        self.assertEqual(woke, [])
        self.assertEqual(self.backstop(waits + "ack: h\n"), ([], []))
        update(hold=False)()  # the hold released after it was absorbed: still wakes
        self.assertEqual(self.backstop(waits + "ack: h\n"), (["h"], []))
        if TRANSCRIPT:
            print("owner wait: 15 min of re-acks, hold catch-up and mergeable churn: 0 wakes; hold release wakes h")

    def drive(self, now, admit=()):
        """One watcher scan at `now`, each lead-backstop wake routed in-process with `admit` as the scheduler walk;
        the inbox ids typed into the lead."""
        route, before = self.mod.commands()["route"], len(self.calls())
        with mock.patch.dict(os.environ, self.env), mock.patch.object(
                self.mod.commands()["schedule"], "admissible", return_value=set(admit)):
            for w in self.mod.scan(self.state, "crew-acme-widgets", now, 900, self.seen):
                if w["reason"] == "lead-backstop":
                    self.assertTrue(route.route_record(self.args, route.profile(self.args)[0], self.state, w))
        return [a[len("inbox: "):] for c in self.calls()[before:] if c[0] == "send-keys"
                for a in c if a.startswith("inbox: ")]

    def test_admission_becoming_available_wakes_between_backed_off_retries(self):  # #1715 r1, #1502
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="d", kind="build", refs=["#8"])) + "\n")
        self.put("status/ben-lead.status", "ack: d\ndeferred: #8 load /p id=d\n")
        self.seen, now = {"offsets": {}, "keys": {}}, 2_000_000_000
        for t in (0, 60, 180, 420, 900):  # backed off to the 900 s cap; load stays high: nothing typed
            self.assertEqual(self.drive(now + t), [])
        self.assertEqual(self.seen["lead_retries"]["ben-lead"]["due"], now + 1800)
        self.assertEqual(self.drive(now + 959, admit={"#8"}), [])  # load freed at +901
        self.assertEqual(self.drive(now + 960, admit={"#8"}), ["d"])  # the 60 s recheck, not the +1800 retry
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(dict(id=i, kind="build", refs=["#8"])) + "\n"
                                                 for i in ("d", "e")))
        self.put("status/ben-lead.status", "ack: d\ndeferred: #8 load /p id=d\nack: e\n")
        self.seen = {"offsets": {}, "keys": {}}
        self.assertEqual(self.drive(now + 2000), [])
        self.assertEqual(self.drive(now + 2060), ["e"])  # e's first retry
        self.assertEqual(self.drive(now + 2120), [])  # an admission recheck never re-types e
        self.assertEqual(self.drive(now + 2180), ["e"])  # e's 120 s step
        if TRANSCRIPT:
            print("load deferral freed at +901: typed at +960 (retry cap +1800); rechecks never re-type other ids")

    def test_owner_answer_recovers_a_missed_event_without_a_new_id(self):  # #1715 r1
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="o", kind="land", refs=["#19", "a" * 40])) + "\n")
        self.put("asks/19.json", json.dumps({"deadline": "2099-01-01T00:00:00+00:00"}))
        poll = {"observed": {"19": {"head": "a" * 40, "ci": "success"}}, "held": [], "answers": {"#19": 1}}
        self.put("poll-state.json", json.dumps(poll))
        status = "ack: o\nwaiting: #19 owner id=o\n"
        self.assertEqual(self.backstop(status), ([], []))
        poll["answers"]["#19"] = 2  # the owner answered; head, CI, hold and the ask are unchanged
        self.put("poll-state.json", json.dumps(poll))
        self.assertEqual(self.backstop(status), (["o"], []))
        self.assertTrue(self.lead.waits(self.state, "ben-lead")["o"]["woke"])
        if TRANSCRIPT:
            print("owner wait: answers 1 -> 2 with nothing else changed wakes o with no new handoff")

    def test_mixed_waits_and_untyped_status_keep_other_ids_retrying(self):  # #1715
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(dict(id=i, kind="build", refs=["#19"])) + "\n"
                                                 for i in ("w", "x")))
        self.poll("pending", held=["#19"])
        status = "ack: w\nwaiting: #19 hold id=w\nack: x\n"
        self.assertEqual(self.backstop(status), (["x"], []))
        self.put("status/ben-lead.status", status)
        self.assertEqual(self.retries(2_000_000_000, self.edges(60, 180)), [60, 180])
        for untyped in ("waiting: #19 hold\n", "waiting: #19 lunch id=x\n", "waiting: #19 hold id=y\n",
                        "blocked: #19 owner id=x\n"):
            with self.subTest(untyped=untyped):
                self.assertEqual(self.backstop(status + untyped), (["x"], []))
        self.poll("pending")  # hold released
        self.assertEqual(self.backstop(status + "done: x\n"), (["w"], []))
        self.assertEqual(self.backstop("waiting: #19 hold id=w\nack: w\n"), (["w"], []))  # never acked when written
        if TRANSCRIPT:
            print("hold wait w + actionable x: x retries on schedule; untyped lines silence nothing; release wakes w")

    def backstop(self, status, admit=(), recheck=True):
        """One lead retry with `status` as the lead status and `admit` as the scheduler walk; (nudged ids, walks)."""
        self.put("status/ben-lead.status", status)
        before = len(self.calls())
        with mock.patch.dict(os.environ, self.env), mock.patch.object(
                self.mod.commands()["schedule"], "admissible", return_value=set(admit)) as walk:
            self.lead.retry_pending(self.args, "ben-lead", recheck=recheck)
        nudged = [a[len("inbox: "):] for c in self.calls()[before:] if c[0] == "send-keys"
                  for a in c if a.startswith("inbox: ")]
        return nudged, [c.args[1] for c in walk.call_args_list]

    def test_busy_lead_gets_no_retyped_nudge_from_backstop_or_replayed_handoff(self):  # #1850 D2.2
        self.assertEqual(self.ensure(), 0)
        harness = self.lead_record()["harness"]
        busy, idle = "• Working (9s • esc to interrupt)\n\n› Ask\n", "• Done.\n\n› Ask\n"
        with mock.patch.dict(os.environ, self.env):
            self.set_pane(2, command=harness, screen=busy)
            self.assertEqual(self.lead.handoff(self.args, "builder", "build", ["#639"]), 0)  # the first nudge only
            first = self.lead.pending(self.state, "ben-lead")[0]["id"]
            before = len(self.calls())
            self.assertEqual(self.lead.handoff(self.args, "builder", "build", ["#639"]), 0)  # a replayed handoff
        self.assertEqual([c for c in self.calls()[before:] if c[0] == "send-keys"], [])
        self.assertEqual([m["id"] for m in self.lead.pending(self.state, "ben-lead")], [first])
        self.assertEqual(self.backstop(""), ([], []))  # busy: the backstop retries later, typing nothing
        self.set_pane(2, command=harness, screen=idle)
        self.assertEqual(self.backstop(""), ([first], []))  # the valid counterpart: an idle lead is nudged
        if TRANSCRIPT:
            print("busy lead: replayed handoff and backstop typed 0; idle lead nudged %s" % first)

    def test_backstop_waits_and_deferrals_use_the_one_receipt_rule(self):  # #1850 round 3
        self.assertEqual(self.ensure(), 0)
        self.set_pane(2, command=self.lead_record()["harness"], screen="• Done.\n\n› Ask\n")
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="w", kind="fix", refs=["#19"])) + "\n")
        early = "ack: w\n"
        for name, status, record, silenced in [
                ("ack before record", early + "waiting: #19 hold id=w\n", len(early), False),
                ("wrong id", "ack: v\nwaiting: #19 hold id=w\n", 0, False),
                ("valid ack", early + "waiting: #19 hold id=w\n", 0, True)]:
            with self.subTest(name):
                self.put("leads/waits.json", "{}")
                self.put("runs/ben-lead.delivery.jsonl", json.dumps(dict(id="w", event="recorded", status=record)) + "\n")
                self.assertEqual(self.backstop(status), ([] if silenced else ["w"], []))
                deferred = status.replace("waiting: #19 hold id=w", "deferred: #19 capacity /s/a.md id=w")
                self.put("status/ben-lead.status", deferred)
                with mock.patch.dict(os.environ, self.env):
                    self.assertEqual(self.lead.deferred_ids(self.state, "ben-lead"), {"w"} if silenced else set())

    def test_acknowledged_deferral_backstop_waits_for_admission(self):  # #1502
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="d1", kind="build", refs=["#8"])) + "\n")
        deferred = "ack: d1\ndeferred: #8 capacity /s/leads/builder-admission.md id=d1\n"
        for _ in range(10):  # ten unchanged capacity deferrals on the 60 s backstop: no inbox typing
            self.assertEqual(self.backstop(deferred), ([], ["builder"]))
        self.assertEqual(self.backstop(deferred, admit={"#9"}), ([], ["builder"]))
        self.assertEqual(self.backstop(deferred, admit={"#8"}), (["d1"], ["builder"]))  # slot or load freed
        self.assertEqual(self.backstop(deferred, recheck=False), (["d1"], []))  # slot release still nudges
        self.assertEqual(self.lead.pending(self.state, "ben-lead")[0]["id"], "d1")  # demand stays pending
        if TRANSCRIPT:
            print("acked capacity deferral: 10 backstops nudged 0; admissible #8 nudged d1; slot release nudged d1")

    def test_unacknowledged_or_other_id_deferral_keeps_normal_retry(self):  # #1502
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(dict(id=i, kind="build", refs=["#8"])) + "\n"
                                                 for i in ("d1", "d2")))
        self.assertEqual(self.backstop("deferred: #8 capacity /p id=d1\n"), (["d1"], []))  # never acked
        self.assertEqual(self.backstop("ack: d1\ndeferred: #8 capacity /p\n"), (["d1"], []))  # no id recorded
        self.assertEqual(self.backstop("ack: d0\ndeferred: #8 capacity /p id=d0\n"), (["d1"], []))  # old handoff
        self.assertEqual(self.backstop("ack: d1\ndeferred: #8 capacity /p id=d1\n"), (["d2"], []))  # d2 undelivered
        self.assertEqual(self.backstop("ack: d1\ndeferred: #8 capacity /p id=d1\ndone: d2\n"), ([], ["builder"]))

    def test_idle_lead_is_not_stale_until_work_is_pending(self):  # #578
        self.assertEqual(self.ensure(), 0)
        now = 2_000_000_000
        self.assertFalse(any(w.get("window") == "ben-lead" for w in self.scan(now)))
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="w1", kind="build", refs=["#8"])) + "\n")
        self.assertEqual([w["liveness"] for w in self.scan(now) if w.get("window") == "ben-lead"], ["alive"])
        self.put("status/ben-lead.status", "ack: w1\ndone: w1\n")
        os.utime(os.path.join(self.state, "status", "ben-lead.status"), (now - 1000, now - 1000))
        self.assertFalse(any(w.get("window") == "ben-lead" and w["reason"] == "stale" for w in self.scan(now)))

    def test_watcher_routes_missing_lead_restart(self):
        self.assertEqual(self.ensure(), 0)
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 2)
        wakes = self.scan(2_000_000_000)
        wake = next(w for w in wakes if w.get("window") == "ben-lead")
        self.put("wake/queue.jsonl", json.dumps(wake) + "\n")
        r = self.crew("route", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lead_record()["restarts"], 1)

    def test_router_consumes_deferred_lead_status_without_coordinator(self):
        self.assertEqual(self.ensure(), 0)
        self.put("status/ben-lead.status", "deferred: #8 capacity\n")
        wake = next(w for w in self.scan(2_000_000_000) if w.get("line", "").startswith("deferred:"))
        self.put("wake/queue.jsonl", json.dumps(wake) + "\n")
        result = self.crew("route", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("mechanical wakes consumed", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ash.jsonl")))
        if TRANSCRIPT:
            print("watcher deferral status routed mechanically; coordinator inbox absent")

    def test_killing_lead_keeps_its_inbox(self):
        self.assertEqual(self.ensure(), 0)
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="work-1", kind="build", refs=["#8"])) + "\n")
        r = self.crew("kill", "ben-lead", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.lead.pending(self.state, "ben-lead")), 1)
        self.assertEqual(self.ensure(), 0)
        self.assertEqual(self.lead_record()["restarts"], 1)

    def test_worker_kill_is_handed_to_lead_and_explicit_lead_cleanup_works(self):
        result = self.crew("kill", "ben-7", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.state, "runs", "ben-7.json")))
        self.assertEqual(len(self.lead.pending(self.state, "ben-lead")), 1)
        result = self.crew("kill", "ben-7", "--project", self.project, CREW_POOL="builder")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "ben-7.json")))


class SynthesizerLead(LivenessBase):
    """#1569: the long-lived synthesizer lead in window 1; its inbox is the land queue."""

    def setUp(self):
        super().setUp()
        self.lead = self.mod.commands()["lead"]
        self.args = argparse.Namespace(project=self.project, org_profile=None, timeout=1)
        self.put("render/runtime/synthesizer-lead.md", "Land approved PRs; never build.\n")

    def ensure(self):
        with mock.patch.dict(os.environ, self.env):
            return self.lead.ensure(self.args, "synthesizer")

    def test_lead_takes_window_1_with_the_synthesizer_identity(self):
        self.assertEqual(self.ensure(), 0)
        rec = dict(self.lead.records(self.state))["sam-lead"]
        self.assertEqual((rec["index"], rec["role"]), (1, "synthesizer-lead"))
        call = next(c for c in self.calls() if c[0] == "new-window" and c[c.index("-n") + 1] == "sam-lead")
        env = [call[i + 1] for i, arg in enumerate(call) if arg == "-e"]
        self.assertIn("CREW_POOL=synthesizer", env)
        self.assertIn("CREW_ROLE=synthesizer-lead", env)

    def test_land_queue_survives_lead_restart(self):
        self.assertEqual(self.ensure(), 0)
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.event(self.args, "synthesizer", dict(event="review-approved",
                                                                            refs=["#12", "a" * 40])), 0)
            self.assertEqual(self.lead.event(self.args, "synthesizer", dict(event="selfgate-passed",
                                                                            refs=["#13", "b" * 40])), 0)
        queued = self.lead.pending(self.state, "sam-lead")
        self.put("status/sam-lead.status", "ack: %s\ndone: #12 %s\ndone: %s\nack: %s\n" % (
            queued[0]["id"], "a" * 40, queued[0]["id"], queued[1]["id"]))  # #13 acked, its land in flight
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 1)
        self.assertEqual(self.ensure(), 0)
        self.assertEqual(dict(self.lead.records(self.state))["sam-lead"]["restarts"], 1)
        self.assertEqual([m["id"] for m in self.lead.pending(self.state, "sam-lead")], [queued[1]["id"]])
        with open(self.lead.pending(self.state, "sam-lead")[0]["refs"][0]) as f:
            self.assertEqual(json.load(f)["refs"], ["#13", "b" * 40])
        if TRANSCRIPT:
            print("synthesizer lead restarted once; unsettled land #13 still queued")

    def test_spawn_synthesizer_refuses_while_the_lead_is_installed(self):
        r = self.spawn("synthesizer", "--pr", "12")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("the synthesizer lead owns lands", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "sam.json")))


class BuilderReports(SendBase):
    def report(self, reason, ref="#8", detail=""):
        return self.crew("lead", "report", "builder", reason, ref, "--detail", detail,
                         "--project", self.project, CREW_ID="ben-lead")

    def test_admission_deferrals_stay_local(self):
        for reason in ("capacity", "load", "suites", "probe-unavailable"):
            result = self.report(reason, detail="admit=0 active=5 load=10.6")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with open(os.path.join(self.state, "leads", "builder-admission.md")) as f:
                note = f.read()
            self.assertIn("Reason: " + reason, note)
            self.assertIn("Refs: #8", note)
            self.assertIn("admit=0 active=5 load=10.6", note)
            if TRANSCRIPT:
                print(result.stdout.strip())
        with open(os.path.join(self.state, "status", "ben-lead.status")) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(line.startswith("deferred: #8 ") for line in lines))
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ash.jsonl")))
        self.assertEqual([c for c in self.calls() if c[0] == "send-keys"], [])
        if TRANSCRIPT:
            print("lead status: 4 deferred entries; coordinator inbox absent; nudges=0")

    def test_deferral_records_the_handoff_id(self):  # #1502
        result = self.crew("lead", "report", "builder", "capacity", "#8", "--id", "d1", "--detail", "cap 10/10",
                           "--project", self.project, CREW_ID="ben-lead")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(os.path.join(self.state, "status", "ben-lead.status")) as f:
            self.assertEqual(f.read(), "deferred: #8 capacity %s id=d1\n"
                             % os.path.join(self.state, "leads", "builder-admission.md"))
        self.assertEqual([c for c in self.calls() if c[0] == "send-keys"], [])

    def test_real_blocks_notify_once_across_fresh_processes(self):
        for reason in ("spawn-failure", "missing-dependency", "owner-decision", "lead-fault"):
            for attempt in range(2):
                result = self.report(reason, detail="action needed")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if attempt:
                    self.assertIn("identical block already reported", result.stdout)
        messages = self.inbox("ash")
        self.assertEqual(len(messages), 4)
        with open(os.path.join(self.state, "status", "ben-lead.status")) as f:
            self.assertEqual(len(f.readlines()), 4)
        self.assertTrue(all(m["kind"] == "blocked" and m["from"] == "ben-lead" for m in messages))
        for message in messages:
            self.assertEqual(message["refs"][0], "#8")
            with open(message["refs"][1]) as f:
                self.assertIn("action needed", f.read())
        self.assertEqual(len([c for c in self.calls() if c[0] == "send-keys"]), 8)
        changed = self.report("spawn-failure", detail="different failure")
        self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
        self.assertEqual(len(self.inbox("ash")), 5)
        if TRANSCRIPT:
            print("4 real block reasons x 2 fresh processes: coordinator messages=4; duplicates=0")
            print("changed failure detail: coordinator messages=5")

    def test_unknown_reason_is_rejected(self):
        result = self.report("ordinary-wait")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ash.jsonl")))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "BuilderLead.test_presence_switches_both_pools_without_stopping_workers"] if "--presence-transcript" in sys.argv else [sys.argv[0], "BuilderLead.test_done_builder_with_running_tool_session_still_counts",
                       "BuilderLead.test_done_builder_with_unacked_spawn_build_message_is_idle",
                       "BuilderLead.test_helpers_are_idle_reclaimable_and_not_suites_but_tool_sessions_are_busy",
                       "BuilderLead.test_suite_probe_excludes_closed_and_merged_items",
                       "BuilderLead.test_restart_preserves_live_workers_and_pending_queue",
                       "BuilderLead.test_last_suite_completion_retries_pending_requests_in_both_pools",
                       "BuilderLead.test_pending_admission_has_recurring_backstop_until_completed",
                       "BuilderReports.test_admission_deferrals_stay_local",
                       "BuilderLead.test_router_consumes_deferred_lead_status_without_coordinator",
                       "BuilderReports.test_real_blocks_notify_once_across_fresh_processes"] if TRANSCRIPT else None)
