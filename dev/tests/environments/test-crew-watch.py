"""Tests for mdstack watch (and its scan), moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: scan with a fake clock (fresh, silent, dead -> restart, twice -> escalate, status line once; a builder
after `done:` flagged when dead, a reviewer's `done:` terminal; each status wake naming its run, #1092), exit with a reason line and queue record, PID
file, `--source` events, typed wake line only into an idle coordinator and never into one showing a captured
stuck screen (a `dialog` wake queued instead, #315), backstop backoff while idle, a never-exiting source cut
off at `--source-timeout` as an incident, waking as `source-failing` at `--source-failures`, a source slower than a
short `--interval` not cut off, transient (exit 75) source failures recorded without a wake until N in a row and a
success resetting the count, sources run once per `--source-interval` with the next due time kept across a re-arm
and held until a rate-limited source's reset, capped at an hour (#1300), a re-exec in place when the crew code changes on disk (#702), a wake on queue growth with no re-queue, a self-queueing source queued once, SIGTERM removing the PID
file and saving state, a signal during a scan waiting for the running child, a second signal exiting at once,
SIGHUP like SIGTERM, a dialog waking at once (each captured stuck screen in `fixtures/dialog/`; a working
screen never), a stale key that ignores the liveness class, an owner ask waking at its deadline once per
deadline (an unreadable one at once), the scan sleep cut short to land on a deadline, an ask wake while the
backstop is backed off; unfinished spawns skip liveness wakes for 60 s, then wake as missing, while started missing
runs wake immediately; a run record reaped between listing and stat skipped, a second watcher a no-op (exit 0, naming the armed PID)
without touching the armed one's PID file, simultaneous starts leaving exactly one watcher through `wake/watcher.lock` (#399), and a watcher removing the PID file only when it holds its own PID
(#591); a `--persistent` watcher nudging the coordinator and scanning on, nudging an undrained queue again
after `--renudge` and stopping once it is drained, and `--detach` starting one in its own session, a second a no-op
(#1346), a gateway-error screen over an idle composer still woken and re-nudged, never a
`dialog` wake, and `mdstack down` stopping a watcher whose PID file was lost through its lock, refusing an
unidentified holder without a signal (#1346 review); finishing work deferred past `stuck_after` waking once as `schedule-stuck` with the snapshot, and the exit
line followed by the schedule summary (#628); the triage sweep timer (#748): due, overdue on wake, an empty queue
skipped, disabled, queued and failed spawns, never a wake, and closed milestones swept at once and kept until a started sweep takes them (#374), a later closed milestone
swept at once once the queued sweep was dequeued (#1175), and the timer
running after the scan's `--source` commands, so a resumed crew's overdue slot reads the queue that scan's poll wrote
(#1098); a run whose pane printed nothing for `idle_stall` waking stale with liveness `idle` despite a fresh claim,
status file and live child, once per silence and never after `done:` (#1283); an alive builder with acked unfinished work and a claim
silent past 900 s waking stale with liveness `claim` despite a fresh supervisor heartbeat, once per silence, never
while mid-turn, held, after `done:` or without an ack (#1633); the reflection timer (#1521): disabled
never reads or spawns, a weekly window queued or started never counts as complete until its posted report, a missed
week caught up once and coalesced with a milestone close, a failed start retried under the same run ID with no second
queue entry, and a run that ended without a report rerun, never over an unreadable log; a worker's pending delivery
re-probed token-free (#1850, D2.4): no wake on first sight, busy or a repeat, one `delivery` wake per changed
actionable state (idle -> nudge, dead -> restart), none for another project's record, the book pruned once acked
or superseded, and the wake handed to the pool lead. Run in CI.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW, DeliveryBase, HEAD, LivenessBase, NOW, screen, STUCK, WORKING


class Watch(LivenessBase):
    def test_active_child_or_recent_output_refreshes_heartbeat(self):
        for activity, children in [(NOW - 30, []), (0, [[42, 9000010, "S", "codex.real"],
                                                       [43, 42, "Ss", "python3"]])]:
            with self.subTest(activity=activity, children=children):
                self.put("status/ben-7.status", "heartbeat: old\n")
                os.utime(os.path.join(self.state, "status", "ben-7.status"), (NOW - 1000, NOW - 1000))
                self.set_pane(10, activity=str(activity), command="node" if children else "codex")
                with open(self.ps, "w") as f:
                    json.dump({"children": children}, f)
                wakes = self.scan(NOW)
                self.assertFalse(any(w["reason"] == "stale" for w in wakes))
                self.assertEqual(self.mod.heartbeat(self.state, "ben-7"),
                                 ("heartbeat: 2033-05-18T03:33:20Z", NOW))
                self.assertEqual([w["reason"] for w in self.scan(NOW + 1, self.seen)], ["status"])
                with open(self.ps, "w") as f:
                    json.dump({}, f)
                self.set_pane(10, activity=str(activity))
                self.assertEqual([w["reason"] for w in self.scan(NOW + 901, self.seen)], ["stale"])

    def test_idle_pane_with_fresh_claim_is_stalled(self):  # #1283
        claim = os.path.join(self.state, "claims", "builder-issue7")
        self.put("claims/builder-issue7", "heartbeat: 2033-05-18T03:33:00Z\n")
        os.utime(claim, (NOW, NOW))
        self.beat(NOW - 10)
        with open(self.ps, "w") as f:  # the refresh loop: a live detached child beneath the harness
            json.dump({"children": [[42, 9000010, "S", "codex.real"], [43, 42, "Ss", "sh"]]}, f)
        self.set_pane(10, activity=str(NOW - 1799))
        self.assertEqual(self.scan(NOW), [])
        self.set_pane(10, activity=str(NOW - 1800))
        self.assertEqual([(w["reason"], w["liveness"], w["action"], w["silent"]) for w in self.scan(NOW)],
                         [("stale", "idle", "escalate", 1800)])
        self.assertEqual(self.scan(NOW + 60, self.seen), [])  # once per silence
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.mod.scan(self.state, "crew-acme-widgets", NOW, 900, {"offsets": {}, "keys": {}},
                                           idle_stall=0), [])  # off
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % HEAD)
        self.assertEqual([w["reason"] for w in self.scan(NOW)], ["status"])  # after done: it waits for its inbox

    def test_silent_claim_with_acked_work_wakes_its_lead_despite_supervisor_heartbeat(self):  # #1633
        claim = os.path.join(self.state, "claims", "builder-issue7")
        self.put("claims/builder-issue7", "heartbeat: 2033-05-18T03:18:20Z\n")
        os.utime(claim, (NOW - 900, NOW - 900))
        self.put("status/ben-7.status", "ack: 20331118T031000Z-abc123\nheartbeat: x\n")
        status = os.path.join(self.state, "status", "ben-7.status")
        os.utime(status, (NOW - 10, NOW - 10))  # the supervisor heartbeat keeps the status file fresh
        idle = "  ⎿  API Error: Connection lost mid-response\n\n❯ \n"
        self.set_pane(10, activity=str(NOW - 60), screen=idle)
        seen = {"offsets": {"ben-7": os.path.getsize(status)}, "keys": {}}
        self.assertEqual(self.scan(NOW, dict(seen, keys={})), [])  # 900 s is not past the limit
        wakes = self.scan(NOW + 1, json.loads(json.dumps(seen)))
        self.assertEqual([(w["reason"], w["window"], w["liveness"], w["action"], w["silent"]) for w in wakes],
                         [("stale", "ben-7", "claim", "escalate", 901)])
        self.assertEqual(self.scan(NOW + 60, self.seen), [])  # once per claim silence
        for name, screen_text, lines in [
                ("busy", "✻ Running tests… (2m 3s · esc to interrupt)\n", "ack: x\n"),
                ("done", idle, "ack: x\ndone: #7 #12 %s\n" % HEAD),
                ("blocked", idle, "ack: x\nblocked: #7 hold\n"),
                ("no ack", idle, "")]:
            with self.subTest(name):
                self.put("status/ben-7.status", lines + "heartbeat: x\n")
                os.utime(status, (NOW - 10, NOW - 10))
                self.set_pane(10, activity=str(NOW - 60), screen=screen_text)
                state = {"offsets": {"ben-7": os.path.getsize(status)}, "keys": {}}
                self.assertEqual(self.scan(NOW + 1, state), [])
        self.put("status/ben-7.status", "ack: x\nheartbeat: x\n")
        os.utime(status, (NOW - 10, NOW - 10))
        self.set_pane(10, activity=str(NOW - 60), screen=idle)
        self.put("poll-state.json", json.dumps({"held": ["#7"]}))
        self.assertEqual(self.scan(NOW + 1, {"offsets": {"ben-7": os.path.getsize(status)}, "keys": {}}), [])

    def observations(self):
        path = os.path.join(self.state, "metrics", "observations.jsonl")
        with open(path) if os.path.exists(path) else open(os.devnull) as f:
            return [json.loads(line) for line in f]

    def test_stale_wake_opens_one_stall_and_the_next_status_line_closes_it(self):  # #1524
        self.beat(NOW - 60)
        self.set_pane(10, command="node")
        self.scan(NOW + 900)
        self.scan(NOW + 1000, self.seen)  # same silence: no second sample
        replay = json.loads(json.dumps(self.seen))
        self.put("status/ben-7.status", "heartbeat: x\nblocked: #7 waiting\n")
        os.utime(os.path.join(self.state, "status", "ben-7.status"), (NOW + 1100, NOW + 1100))
        self.scan(NOW + 1100, self.seen)
        self.scan(NOW + 1100, replay)  # a re-exec replays the scan from the uncommitted state
        since = self.mod.utc(NOW - 60)
        self.assertEqual([(o["source"], o["kind"], o["key"], o["since"]) for o in self.observations()],
                         [("watch", "stall", "run:ben-7", since)] + [("watch", "resume", "run:ben-7", since)] * 2)
        self.assertEqual(self.observations()[0]["liveness"], "ambiguous")
        self.assertNotIn(self.state, json.dumps(self.observations()))  # sanitized: no state or worktree paths

    def test_persistent_helpers_only_are_stale_but_detached_work_refreshes(self):
        for harness in ("codex", "claude"):
            with self.subTest(harness=harness):
                rec = self.record("ben-7")
                rec["harness"] = harness
                self.put("runs/ben-7.json", json.dumps(rec))
                self.set_pane(10, command=harness)
                self.put("status/ben-7.status", "heartbeat: old\n")
                os.utime(os.path.join(self.state, "status", "ben-7.status"), (NOW - 1000, NOW - 1000))
                helpers = [[42, 9000010, "S+", harness + ".real"], [43, 42, "S+", "mcp-server"],
                           [44, 43, "S+", "python3"], [45, 42, "S+", "keep-awake"]]
                with open(self.ps, "w") as f:
                    json.dump({"children": helpers}, f)
                self.assertEqual([w["reason"] for w in self.scan(NOW)], ["status", "stale"])
                with open(self.ps, "w") as f:
                    json.dump({"children": helpers + [[46, 43, "Ss", "python3"]]}, f)
                self.assertEqual(self.scan(NOW, self.seen), [])
                self.assertEqual(self.mod.heartbeat(self.state, "ben-7")[1], NOW)
                with open(self.ps, "w") as f:
                    json.dump({"children": helpers}, f)
                self.assertEqual([w["reason"] for w in self.scan(NOW + 901, self.seen)], ["status", "stale"])

    def test_idle_synthesizer_is_not_stale_until_it_has_work(self):  # #578
        rec = self.record("ben-7")
        rec["role"] = "synthesizer"
        self.put("runs/ben-7.json", json.dumps(rec))
        self.beat(NOW - 1000)
        self.assertEqual(self.scan(NOW), [])
        self.put("inbox/ben-7.jsonl", json.dumps(dict(id="m1", kind="land", refs=["#12"])) + "\n")
        self.beat(NOW - 1000)
        self.assertEqual([w["reason"] for w in self.scan(NOW)], ["stale"])
        os.remove(os.path.join(self.state, "inbox", "ben-7.jsonl"))
        self.put("trains/train-1.json", json.dumps(dict(n=1, members=[dict(pr=12)], landed=[])))
        self.beat(NOW - 1000)
        self.assertEqual([w["reason"] for w in self.scan(NOW)], ["stale"])
        self.set_pane(10, dead="1")
        os.remove(os.path.join(self.state, "trains", "train-1.json"))
        self.beat(NOW - 1000)
        self.assertEqual([w["liveness"] for w in self.scan(NOW)], ["dead"])

    def test_zombie_unrelated_child_and_reused_pane_do_not_mask_stale(self):
        with open(self.ps, "w") as f:
            json.dump({"children": [[42, 9000010, "S", "codex.real"], [43, 42, "Z", "python3"],
                                    [44, 999, "S", "python3"]]}, f)
        self.beat(NOW - 1000)
        self.assertEqual([w["reason"] for w in self.scan(NOW)], ["stale"])
        self.set_pane(10, id="%99", activity=str(NOW))
        self.assertEqual([w["liveness"] for w in self.scan(NOW)], ["missing"])

    def test_stray_json_is_not_a_run(self):
        self.beat(NOW)
        for name, text in [("checks", "[]"), ("scratch", '{"note": "scratch"}'), ("broken", "{")]:
            self.put("runs/%s.json" % name, text)
        self.assertEqual([name for name, _ in self.mod.runs(self.state)], ["ben-7"])
        self.assertEqual(self.scan(NOW), [])

    def test_record_reaped_between_listing_and_stat_is_skipped(self):  # #591
        for starting in (False, True):
            with self.subTest(starting=starting):
                rec = self.record("ben-7") if not starting else dict(self.record("ben-7"), start=None)
                os.remove(os.path.join(self.state, "runs", "ben-7.json"))
                with mock.patch.dict(self.mod.scan.__globals__, runs=lambda state: iter([("ben-7", rec)])):
                    self.assertEqual(self.scan(NOW), [])
                self.assertEqual(self.mod.heartbeat(self.state, "ben-7"), ("", None))
                self.put("runs/ben-7.json", json.dumps(rec))

    def test_same_size_status_delivered_after_window_reuse_and_rearm(self):
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % HEAD)
        os.utime(os.path.join(self.state, "status", "ben-7.status"), (NOW, NOW))
        first = self.scan(NOW)
        self.assertEqual([w["reason"] for w in first], ["status"])
        seen = json.loads(json.dumps(self.seen))
        rec = self.record("ben-7")
        rec["start"] = "2033-05-18T00:00:00Z"
        self.put("runs/ben-7.json", json.dumps(rec))
        self.put("status/ben-7.status", "done: #7 #13 %s\n" % HEAD)
        os.utime(os.path.join(self.state, "status", "ben-7.status"), (NOW, NOW))
        second = self.scan(NOW, seen)
        self.assertEqual([w["line"] for w in second], ["done: #7 #13 " + HEAD])
        # each status wake names the run that wrote it, so route spares a respawn under the same name (#1092)
        self.assertEqual(second[0]["run"], self.mod.run_identity(rec))
        self.assertNotEqual(first[0]["run"], second[0]["run"])
        self.assertEqual(self.scan(NOW, self.seen), [])
        self.assertEqual(self.record("ben-7")["pr"], 13)

    def test_retained_status_never_replays_across_identity_changes(self):  # #819
        old = "blocked: #5 hold\ndelivered: m1\n"
        self.put("status/ben-7.status", old)
        self.assertEqual([w["line"] for w in self.scan(NOW) if w["reason"] == "status"], old.splitlines())
        rec = self.record("ben-7")
        for change in ({"start": "2033-05-18T00:00:00Z", "pane_id": None, "pane_pid": None, "pane_start": None},
                       {"pane_id": "%99", "pane_pid": "4242", "pane_start": "Thu May 18 00:00:01 2033"}):
            rec.update(change)  # a restart saves its record without, then with, the new pane identity
            self.put("runs/ben-7.json", json.dumps(rec))
            self.assertEqual([w for w in self.scan(NOW, self.seen) if w["reason"] == "status"], [])
        self.put("status/ben-7.status", old + "ack: m2\n")
        self.assertEqual([w["line"] for w in self.scan(NOW, self.seen) if w["reason"] == "status"], ["ack: m2"])

    def test_rewritten_status_reads_from_the_start(self):  # #819: same prefix length, other content
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % HEAD)
        self.scan(NOW)
        self.put("status/ben-7.status", "done: #7 #13 %s\nack: m2\n" % HEAD)
        self.assertEqual([w["line"] for w in self.scan(NOW, self.seen) if w["reason"] == "status"],
                         ["done: #7 #13 " + HEAD, "ack: m2"])

    def missing_window(self, starting=False):
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash"}}, f)
        if starting:
            rec = self.record("ben-7")
            del rec["start"]
            self.put("runs/ben-7.json", json.dumps(rec))
        self.beat(NOW)

    def test_scan_fresh_starting_run_without_window_does_not_wake(self):
        self.missing_window(starting=True)
        self.assertEqual(self.probe(), "missing")
        self.assertEqual(self.scan(NOW), [])
        self.assertEqual(self.scan(NOW + 59, self.seen), [])

    def test_scan_expired_starting_run_without_window_wakes_once(self):
        self.missing_window(starting=True)
        self.assertEqual(self.scan(NOW), [])
        wakes = self.scan(NOW + 60, self.seen)
        self.assertEqual([(w["reason"], w["liveness"], w["action"]) for w in wakes],
                         [("stale", "missing", "restart")])
        self.assertEqual(self.scan(NOW + 61, self.seen), [])

    def test_scan_started_run_without_window_wakes_immediately(self):
        self.missing_window()
        wakes = self.scan(NOW)
        self.assertEqual([(w["reason"], w["liveness"], w["action"]) for w in wakes],
                         [("stale", "missing", "restart")])
        self.assertEqual(wakes[0]["run"], self.mod.run_identity(self.record("ben-7")))  # #1552

    def test_scan_fresh_silent_dead_and_twice(self):
        self.beat(NOW - 60)
        self.assertEqual(self.scan(NOW), [])  # fresh
        silent = self.scan(NOW + 900)
        self.assertEqual([(w["liveness"], w["action"]) for w in silent], [("alive", "escalate")])  # never restart
        self.assertEqual(self.scan(NOW + 1000, self.seen), [])  # once per silence
        self.set_pane(10, dead="1")
        self.assertEqual([(w["liveness"], w["action"]) for w in self.scan(NOW)], [("dead", "restart")])
        self.set_pane(10, id="%99", pid="9000099")
        self.assertEqual([(w["liveness"], w["action"]) for w in self.scan(NOW + 900)], [("missing", "restart")])
        rec = self.record("ben-7")
        rec["restarts"] = 1  # silent twice: the restarted run went silent and died again
        with open(os.path.join(self.state, "runs", "ben-7.json"), "w") as f:
            json.dump(rec, f)
        self.assertEqual([w["action"] for w in self.scan(NOW + 900)], ["escalate"])
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % HEAD)
        self.assertEqual([(w["reason"], w.get("line"), w.get("liveness")) for w in self.scan(NOW + 900)],
                         [("status", "done: #7 #12 " + HEAD, None), ("stale", None, "missing")])  # #139 F4

    def test_scan_builder_after_done_idle_ok_dead_flagged_reviewer_terminal(self):  # #139 F4
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % HEAD)
        self.beat(NOW - 3600)
        os.utime(os.path.join(self.state, "status", "ben-7.status"), (NOW - 3600, NOW - 3600))
        self.assertEqual([w["reason"] for w in self.scan(NOW, {"offsets": {"ben-7": 54}, "keys": {}})],
                         ["idle-builder"])  # alive and expired; a dead builder still follows recovery below
        self.set_pane(10, dead="1")
        self.assertEqual([(w["liveness"], w["action"]) for w in self.scan(NOW, {"offsets": {"ben-7": 54}, "keys": {}})],
                         [("dead", "restart")])
        rec = self.record("ben-7")
        rec["role"] = "reviewer"
        with open(os.path.join(self.state, "runs", "ben-7.json"), "w") as f:
            json.dump(rec, f)
        self.assertEqual(self.scan(NOW, {"offsets": {"ben-7": 54}, "keys": {}}), [])  # a reviewer done: is terminal

    def test_scan_dialog_wakes_at_once_not_after_stale(self):  # #234 N3
        self.beat(NOW - 30)
        self.set_pane(10, screen="Hooks need review\n> 1. Review hooks\n  2. Continue without hooks\n"
                               "enter confirm · esc skip")
        wakes = self.scan(NOW)  # 30 s after the last progress, far inside --stale 900
        self.assertEqual([(w["reason"], w["liveness"], w["action"]) for w in wakes], [("dialog", "ambiguous", "escalate")])
        self.assertEqual(self.mod.reason(wakes[0]), "dialog: ben-7 ambiguous, silent 30s, escalate")
        self.assertEqual(self.scan(NOW + 900, self.seen), [])  # once per dialog, and no stale wake behind it

    def test_scan_bypass_permission_prompt_names_class_and_line(self):  # #1968
        self.beat(NOW - 30)
        cases = [("claude-proceed", "bypass", "Do you want to proceed?"),
                 ("codex-approval", "bypass", "Would you like to run the following command?"),
                 ("claude-trust", "bypass", None), ("codex-trust", "bypass", None),
                 ("claude-proceed", "auto", None), ("claude-proceed", None, None)]
        for name, mode, want in cases:
            with self.subTest(name=name, mode=mode):
                self.set_pane(10, screen=screen(name))
                with mock.patch.dict(os.environ, self.env):
                    wakes = self.mod.scan(self.state, "crew-acme-widgets", NOW, 900, {"offsets": {}, "keys": {}},
                                          permission_mode=mode)
                self.assertEqual([(w["reason"], w["action"]) for w in wakes], [("dialog", "escalate")])
                self.assertEqual((wakes[0].get("class"), wakes[0].get("prompt")),
                                 ("permission-dialog", want) if want else (None, None))
        self.set_pane(10, screen=screen("claude-proceed"))
        with mock.patch.dict(os.environ, self.env):
            wake, = self.mod.scan(self.state, "crew-acme-widgets", NOW, 900, {"offsets": {}, "keys": {}},
                                  permission_mode="bypass")
        self.assertEqual(self.mod.reason(wake), "dialog: ben-7 ambiguous, silent 30s, escalate, "
                                                "permission-dialog: Do you want to proceed?")

    def test_scan_stuck_screen_wakes_at_once_working_screen_does_not(self):  # #289
        self.beat(NOW - 30)
        for name, want in [(n, [("dialog", "ambiguous")]) for n in STUCK] + [(n, []) for n in WORKING]:
            with self.subTest(name):
                self.set_pane(10, screen=screen(name))
                self.assertEqual([(w["reason"], w["liveness"]) for w in self.scan(NOW)], want)

    def test_scan_quota_screen_wakes_once_for_restart(self):  # #631: never alive, trust or a stale escalation
        self.beat(NOW - 30)
        quoted = "⏺ Read(issue 631)\n  ⎿  printed `Error: Weekly usage limit reached`\n  ■ You've hit your usage limit (quoted)"
        self.set_pane(10, screen=quoted)  # another harness's text, or its own quoted out of place: not quota
        self.assertEqual((self.probe(), self.scan(NOW)), ("alive", []))
        self.set_pane(10, screen="• Working\n■ You've hit your usage limit. Upgrade to Pro or try again in 2 days.")
        self.assertEqual(self.probe(), "quota")
        wakes = self.scan(NOW)
        self.assertEqual([(w["reason"], w["liveness"], w["engine"], w["action"]) for w in wakes],
                         [("quota", "quota", "codex", "restart")])
        self.assertEqual(self.scan(NOW + 1800, self.seen), [])  # once per run, and no stale wake behind it
        rec = dict(self.record("ben-7"), restarts=1)
        self.put("runs/ben-7.json", json.dumps(rec))
        self.assertEqual([w["action"] for w in self.scan(NOW)], ["escalate"])  # after its one restart

    def test_scan_records_adapter_transient_text_once(self):  # #621
        claude = "  ⎿  API Error (529 {\"type\":\"error\"}) · Retrying in 2 seconds… (attempt 1/10)"
        codex = "■ exceeded retry limit, last status: 429 Too Many Requests"
        fatal = '  ⎿  API Error: 529 {"type":"error","error":{"type":"overloaded_error"}}'
        # Pane text that is not the harness's own error line (#1366): file names, tool output, diffs, quoted issue
        # bodies and a docs table row naming the error line.
        noise = "\n".join([
            "  ⎿  Wrote 9 lines to changes/unreleased/1300-rate-limit-backoff.md",
            "⏺ Bash(gh issue view 1395)", "  ⎿  title: back off on a rate limit", "     API Error (429) seen twice",
            "     ⎿  API Error (529 …) · Retrying in 2 seconds… (attempt 1/10)",
            "      12 +| Transient | A `⎿  API Error` line naming 429 or a 5xx status |",
            "| C5 | `⎿  API Error (529 …) · Retrying` and `■ last status: 429 Too Many Requests` |",
            "  └ grep -n rate-limit docs/scheduling.md: HTTP 429 Too Many Requests, retry",
            '    {"type":"error","status":503} quoted from #621', "• 429 Too Many Requests is the rate limit retry"])
        errors = os.path.join(self.state, "schedule", "errors.jsonl")
        for harness, text, want in [("claude", claude, [claude.strip()]), ("claude", fatal, [fatal.strip()]),
                                    ("codex", codex, [codex]),
                                    ("codex", '■ {"type":"error","status":503,…}', ['■ {"type":"error","status":503,…}']),
                                    ("pi", claude, []), ("claude", noise, []), ("codex", noise, []),
                                    ("claude", noise + "\n" + claude, [claude.strip()]),
                                    ("codex", noise + "\n" + codex, [codex])] + \
                [(h, screen(n), []) for n in WORKING for h in ("claude", "codex")]:
            with self.subTest(harness=harness, text=text[:30]):
                if os.path.exists(errors):
                    os.remove(errors)
                rec = self.record("ben-7")
                rec["harness"] = harness
                self.put("runs/ben-7.json", json.dumps(rec))
                self.beat(NOW - 30)
                self.set_pane(10, command=harness, screen=text)
                self.scan(NOW)
                self.scan(NOW + 60, self.seen)  # still on screen at the next scan: one error, not two
                lines = []
                if os.path.exists(errors):
                    with open(errors) as f:
                        lines = [json.loads(line) for line in f]
                self.assertEqual([(e["source"], e["text"]) for e in lines], [("ben-7", t) for t in want])

    def test_scan_stale_key_ignores_liveness_class(self):  # #234 N4
        self.beat(NOW - 60)
        self.set_pane(10, command="node")
        self.assertEqual([(w["reason"], w["liveness"]) for w in self.scan(NOW + 900)], [("stale", "ambiguous")])
        self.set_pane(10)
        self.assertEqual(self.probe(), "alive")
        self.assertEqual(self.scan(NOW + 1000, self.seen), [])  # same silence, no second wake

    def ask(self, n, deadline):
        self.put("asks/%s.json" % n, json.dumps({"deadline": deadline}))

    def asks(self, now, seen=None):
        return [w["event"] for w in self.scan(now, seen) if w["reason"] == "ask"]

    def tick(self, now, values=None, rc=0, stdout="crew: started riley-sweep\n"):
        """One triage timer tick with a fake spawn: (outcome, spawn argv or None, queue.jsonl unchanged). A `queued:`
        spawn appends its sweep request to spawn-queue.jsonl, as `mdstack spawn` does at the cap."""
        values = {"triage.enabled": True, "triage.interval_hours": 6} if values is None else values
        queue = os.path.join(self.state, "wake", "queue.jsonl")
        before = os.path.exists(queue) and os.path.getsize(queue)
        done = subprocess.CompletedProcess([], rc, stdout, "")

        def spawn(*_, **__):
            if not rc and stdout.startswith("queued:"):
                with open(os.path.join(self.state, "spawn-queue.jsonl"), "a") as f:
                    f.write(json.dumps({"role": "researcher", "pass": "research", "sweep": True}) + "\n")
            return done
        with mock.patch.object(self.mod.subprocess, "run", side_effect=spawn) as run:
            outcome = self.mod.triage_tick(values, self.state, now, self.project)
        after = os.path.exists(queue) and os.path.getsize(queue)
        return outcome, run.call_args[0][0] if run.called else None, before == after

    def test_triage_timer_due_and_overdue_on_wake(self):  # #748
        outcome, argv, quiet = self.tick(NOW)  # never swept: due on the first scan
        self.assertEqual((outcome, quiet), ("started", True))
        self.assertEqual((os.path.realpath(argv[1]), argv[2:]),
                         (os.path.realpath(CREW), ["spawn", "researcher", "--sweep", "--project", self.project]))
        self.assertEqual(self.tick(NOW + 6 * 3600 - 1)[:2], (None, None))  # inside the interval
        self.assertEqual(self.tick(NOW + 6 * 3600)[0], "started")  # due
        self.assertEqual(self.tick(NOW + 30 * 86400)[0], "started")  # woke a month overdue: at once, one sweep
        self.assertEqual(self.tick(NOW + 30 * 86400 + 5)[:2], (None, None))
        with open(os.path.join(self.state, "triage", "sweep.json")) as f:
            self.assertEqual(json.load(f), {"at": NOW + 30 * 86400, "outcome": "started"})

    def test_triage_timer_skips_an_empty_queue_and_sweeps_an_unreadable_one(self):  # #748
        self.put("triage/queue.json", json.dumps({"items": []}))
        self.assertEqual(self.tick(NOW)[:2], ("skipped: empty queue", None))
        self.assertEqual(self.tick(NOW + 3600)[:2], (None, None))  # a skipped slot still counts
        self.put("triage/queue.json", json.dumps({"items": [{"issue": 9, "kind": "owner-reply"}]}))
        self.assertEqual(self.tick(NOW + 6 * 3600)[0], "started")
        self.put("triage/queue.json", "{not json")
        self.assertEqual(self.tick(NOW + 12 * 3600)[0], "started")

    def test_triage_timer_disabled_never_spawns(self):  # #748
        for values in ({}, {"triage.enabled": False, "triage.interval_hours": 6}):
            self.assertEqual(self.tick(NOW, values)[:2], (None, None))
        self.assertFalse(os.path.exists(os.path.join(self.state, "triage", "sweep.json")))

    def test_triage_timer_keeps_closed_milestones_until_a_started_sweep_takes_them(self):  # #374
        poll = self.mod.commands()["poll"]
        values = {"triage.enabled": True, "triage.interval_hours": 6, "repo.owner": "acme", "repo.name": "widgets"}
        closed = [{"number": 1, "title": "M1"}]

        def scan():  # mdstack poll's milestone part
            pending = poll.triage_milestones(values, self.state, read=lambda *a, **k: closed)
            self.put("triage/queue.json", json.dumps({"items": [], "milestones": pending}))
            return [m["number"] for m in pending]
        queued = "queued: researcher research sweep (researcher cap reached)\n"
        self.assertEqual(scan(), [])  # baseline
        self.assertEqual(self.tick(NOW, values)[0], "skipped: empty queue")
        closed.append({"number": 2, "title": "M2"})
        self.assertEqual(scan(), [2])
        self.assertEqual(self.tick(NOW + 60, values, stdout=queued)[0], "queued")  # at once, inside the interval
        self.assertEqual(scan(), [2])  # capped: still pending
        closed.append({"number": 3, "title": "M3"})
        self.assertEqual(scan(), [2, 3])  # M3 closes before the queued sweep starts
        self.assertEqual(self.tick(NOW + 120, values)[:2], (None, None))  # the queued sweep will take both
        self.assertEqual(self.tick(NOW + 60 + 6 * 3600, values, stdout=queued)[0], "queued")  # interval before dequeue
        self.assertEqual(scan(), [2, 3])
        self.assertEqual(poll.triage_untaken(self.state), [{"repo": "acme/widgets", "number": n, "title": "M%d" % n}
                                                           for n in (2, 3)])  # what the dequeued spawn names and takes
        self.dequeue_sweep()
        poll.triage_take(self.state, poll.triage_untaken(self.state))
        self.assertEqual(scan(), [])
        self.assertEqual(self.tick(NOW + 61 + 12 * 3600, values)[0], "skipped: empty queue")
        closed.append({"number": 4, "title": "M4"})
        self.assertEqual(scan(), [4])
        self.assertEqual(self.tick(NOW + 62 + 12 * 3600, values, rc=1, stdout="crew: riley-sweep already running\n")[0],
                         "failed: crew: riley-sweep already running")
        self.assertEqual(self.tick(NOW + 62 + 12 * 3600 + 599, values)[:2], (None, None))
        self.assertEqual(self.tick(NOW + 62 + 12 * 3600 + 600, values)[0], "started")  # retried after SWEEP_RETRY

    def dequeue_sweep(self):  # mdstack dequeue drops the request before it spawns the sweep
        os.remove(os.path.join(self.state, "spawn-queue.jsonl"))

    def test_triage_timer_dequeued_sweep_frees_the_slot_for_a_later_milestone(self):  # #1175
        poll = self.mod.commands()["poll"]
        values = {"triage.enabled": True, "triage.interval_hours": 6, "repo.owner": "acme", "repo.name": "widgets"}
        closed = [{"number": 1, "title": "M1"}]

        def scan():
            pending = poll.triage_milestones(values, self.state, read=lambda *a, **k: closed)
            self.put("triage/queue.json", json.dumps({"items": [], "milestones": pending}))
        scan()  # baseline
        closed.append({"number": 4, "title": "M4"})
        scan()
        self.assertEqual(self.tick(NOW, values, stdout="queued: researcher research sweep (...)\n")[0], "queued")
        self.assertEqual(self.tick(NOW + 60, values)[:2], (None, None))  # still queued: it will take M4
        self.dequeue_sweep()
        poll.triage_take(self.state, poll.triage_untaken(self.state))  # the dequeued sweep starts and takes M4
        scan()
        self.assertEqual(self.tick(NOW + 120, values)[:2], (None, None))  # nothing untaken: the interval holds
        closed.append({"number": 5, "title": "M5"})
        scan()
        self.assertEqual(self.tick(NOW + 180, values)[0], "started")  # M5 sweeps at once, not after the interval
        self.put("spawn-queue.jsonl", "{not json\n")
        self.put("triage/sweep.json", json.dumps({"at": NOW + 240, "outcome": "queued"}))
        closed.append({"number": 6, "title": "M6"})
        scan()
        self.assertEqual(self.tick(NOW + 300, values)[:2], (None, None))  # an unreadable queue may still hold it

    def test_triage_timer_queued_and_failed_spawns(self):  # #748
        self.assertEqual(self.tick(NOW, stdout="queued: researcher research sweep (...)\n")[0], "queued")
        self.assertEqual(self.tick(NOW + 6 * 3600, rc=1, stdout="crew: session x not reachable\n")[0],
                         "failed: crew: session x not reachable")
        self.assertEqual(self.tick(NOW + 6 * 3600 + 599)[:2], (None, None))
        self.assertEqual(self.tick(NOW + 6 * 3600 + 600)[0], "started")  # retried after SWEEP_RETRY

    DOCS = {"docs.enabled": True, "docs.interval_days": 7, "docs.repos": ["acme/widgets"], "repo.owner": "acme",
            "repo.name": "widgets", "repo.default_branch": "main"}

    def docs_tick(self, now, values=None, findings=0, head="a" * 40, scan_rc=0, spawn_rc=0,
                  stdout="crew: started riley-docs\n"):
        """One docs-pass timer tick with a fake git, docs scan and spawn: (outcome, the argv run, queue.jsonl unchanged).
        The fake scan writes acme/widgets' scan.json with `findings` broken links at `head`, scanned today."""
        values = self.DOCS if values is None else values
        queue = os.path.join(self.state, "wake", "queue.jsonl")
        before = os.path.exists(queue) and os.path.getsize(queue)
        out = os.path.join(os.path.dirname(self.state), "acme__widgets", "docs", "scan.json")

        def run(argv, **_):
            if argv[1:2] == [os.path.join(self.mod.HERE, "docs-scan.py")] and not scan_rc:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "w") as f:
                    json.dump({"repo": "acme/widgets", "head": head, "scanned": str(now), "inventory": [],
                               "stale": [{"path": "docs/d.md", "age_days": int(now)}],
                               "broken_links": [{"path": "README.md", "line": n} for n in range(findings)]}, f)
            rc = scan_rc if "docs-scan.py" in argv[1] else spawn_rc if "spawn" in argv else 0
            return subprocess.CompletedProcess(argv, rc, stdout if "spawn" in argv else "",
                                               "docs-scan: no --checkout for acme/pack\n" if rc else "")
        with mock.patch.object(self.mod.subprocess, "run", side_effect=run) as fake:
            outcome = self.mod.docs_tick(values, self.state, now, self.project)
        after = os.path.exists(queue) and os.path.getsize(queue)
        return outcome, [c[0][0] for c in fake.call_args_list], before == after

    def test_docs_timer_due_at_once_and_catches_up_overdue_on_wake(self):  # #1026
        outcome, argv, quiet = self.docs_tick(NOW)  # never run: due on the first scan
        self.assertEqual((outcome, quiet), ("started", True))
        self.assertEqual([a[3:5] for a in argv[:2]], [["rev-parse", "--show-toplevel"], ["fetch", "-q"]])
        self.assertEqual(argv[2][2:5], ["--project", self.project, "--checkout"])
        self.assertTrue(argv[2][5].startswith("acme/widgets="))
        self.assertEqual((os.path.realpath(argv[3][1]), argv[3][2:]),
                         (os.path.realpath(CREW), ["spawn", "researcher", "--docs-pass", "--project", self.project]))
        week = 7 * 86400
        self.assertEqual(self.docs_tick(NOW + week - 1, findings=1), (None, [], True))  # inside the interval
        self.assertEqual(self.docs_tick(NOW + week, findings=1)[0], "started")  # due
        self.assertEqual(self.docs_tick(NOW + 60 * 86400, findings=2)[0], "started")  # woke two months overdue: one pass
        self.assertEqual(self.docs_tick(NOW + 60 * 86400 + 5, findings=3)[:2], (None, []))
        with open(os.path.join(self.state, "docs", "pass.json")) as f:
            rec = json.load(f)
        self.assertEqual((rec["at"], rec["outcome"]), (NOW + 60 * 86400, "started"))

    def test_docs_timer_skips_a_scan_unchanged_since_the_last_report(self):  # #1026
        week = 7 * 86400
        self.assertEqual(self.docs_tick(NOW, findings=1)[0], "started")
        outcome, argv, _ = self.docs_tick(NOW + week, findings=1, head="b" * 40)  # new head and date, same findings
        self.assertEqual((outcome, len(argv)), ("skipped: scan unchanged", 3))  # scanned, no session
        self.assertEqual(self.docs_tick(NOW + week + 60, findings=2)[:2], (None, []))  # a skipped slot still counts
        self.assertEqual(self.docs_tick(NOW + 2 * week, findings=1)[0], "skipped: scan unchanged")  # vs the last report
        self.assertEqual(self.docs_tick(NOW + 3 * week, findings=2)[0], "started")  # changed: a pass
        self.assertEqual(self.docs_tick(NOW + 4 * week, findings=2, stdout="queued: researcher research docs pass\n")[0],
                         "skipped: scan unchanged")
        self.assertEqual(self.docs_tick(NOW + 5 * week, findings=0, stdout="queued: researcher research docs pass\n")[0],
                         "queued")  # a queued pass is the report too
        self.assertEqual(self.docs_tick(NOW + 6 * week, findings=0)[0], "skipped: scan unchanged")

    def test_docs_timer_retries_a_failed_scan_or_spawn(self):  # #1026
        self.assertEqual(self.docs_tick(NOW, scan_rc=2)[:2][0], "failed: scan: docs-scan: no --checkout for acme/pack")
        self.assertEqual(self.docs_tick(NOW + 599)[:2], (None, []))
        self.assertEqual(self.docs_tick(NOW + 600, spawn_rc=1, stdout="crew: riley-docs already running\n")[0],
                         "failed: crew: riley-docs already running")
        self.assertEqual(self.docs_tick(NOW + 1200)[0], "started")  # the failed spawn reported nothing: not skipped

    def test_docs_timer_disabled_never_scans(self):  # #1026
        for values in ({}, dict(self.DOCS, **{"docs.enabled": False})):
            self.assertEqual(self.docs_tick(NOW, values), (None, [], True))
        self.assertFalse(os.path.exists(os.path.join(self.state, "docs", "pass.json")))

    REFLECT = {"reflection.enabled": True, "repo.owner": "acme", "repo.name": "widgets",
               "runtime.options.poll_interval": 60, "runtime.timezone": "UTC"}
    W19, W20 = "week-2033-W19", "week-2033-W20"  # the full ISO weeks before NOW and before Monday NOW + 5 days

    def reflect(self, now, closed=(1,), rc=0, stdout="crew: started riley-reflection\n", posted=None, values=None):
        """One reflection timer tick with fake milestone reads, spawn and report lookup: (outcome, spawn argv or None).
        A `queued:` spawn appends its request to spawn-queue.jsonl, as `mdstack spawn` does at the cap."""
        mod, restart = self.mod.commands()["reflection"], self.mod.commands()["restart"]

        def spawn(argv, **_):
            if not rc and stdout.startswith("queued:"):
                with open(os.path.join(self.state, "spawn-queue.jsonl"), "a") as f:
                    f.write(json.dumps({"role": "researcher", "reflection": {
                        "window": argv[argv.index("--reflection") + 1], "run": argv[argv.index("--run-id") + 1]}}) + "\n")
            return subprocess.CompletedProcess(argv, rc, stdout, "")
        lookup = posted if callable(posted) else lambda *_: posted
        with mock.patch.object(mod.subprocess, "run", side_effect=spawn) as run, \
                mock.patch.object(restart, "reflection_posted", side_effect=lookup) as look:
            outcome = mod.tick(self.REFLECT if values is None else values, self.state, now, self.project,
                               read=lambda *a, **k: [{"number": n} for n in closed])
        self.looked = [c[0][1] for c in look.call_args_list]
        return outcome, run.call_args[0][0] if run.called else None

    def ledger(self):
        with open(os.path.join(self.state, "reflection", "ledger.json")) as f:
            return json.load(f)

    def hold(self, window, run="r1"):  # a live reflection run record carrying the window
        with open(os.path.join(self.state, "runs", "ben-7.json")) as f:
            rec = json.load(f)
        rec["args"] = dict(rec.get("args") or {}, reflection={"window": window, "run": run, "log": None, "sha": None})
        self.put("runs/riley-reflection.json", json.dumps(rec))

    def test_reflection_timer_disabled_never_reads_or_spawns(self):  # #1521
        for values in ({}, dict(self.REFLECT, **{"reflection.enabled": False})):
            self.assertEqual(self.reflect(NOW, values=values), (None, None))
        self.assertFalse(os.path.exists(os.path.join(self.state, "reflection")))

    def test_reflection_timer_weekly_run_completes_only_on_its_posted_report(self):  # #1521
        queued = "queued: researcher research reflection %s (researcher cap reached)\n" % self.W19
        outcome, argv = self.reflect(NOW, stdout=queued)  # never ran: the last full week at once, at the cap
        self.assertEqual(outcome, "queued")
        self.assertEqual(argv[2:6], ["spawn", "researcher", "--reflection", self.W19])
        self.assertEqual(argv[6:8], ["--run-id", self.W19 + "-20330518T033320Z"])
        self.assertEqual(self.ledger()["closed"], [1])  # the first milestone read is a baseline only
        self.assertEqual(self.reflect(NOW + 3600, posted="https://x/1#c"), (None, None))  # queued is not complete
        self.assertEqual(self.looked, [])
        os.remove(os.path.join(self.state, "spawn-queue.jsonl"))  # dequeued: the run starts and holds the window
        self.hold(self.W19)
        self.assertEqual(self.reflect(NOW + 7200, posted="https://x/1#c"), (None, None))  # started is not complete
        self.assertEqual(self.looked, [])
        os.remove(os.path.join(self.state, "runs", "riley-reflection.json"))  # done: reflection, reaped by route
        self.assertEqual(self.reflect(NOW + 7260, posted="https://x/1#c"), ("completed: https://x/1#c", None))
        self.assertEqual(self.looked, [{"window": self.W19, "log": None}])
        led = self.ledger()
        self.assertEqual((led["pending"], list(led["completed"]), "request" in led), ([], [self.W19], False))
        self.assertEqual(self.reflect(NOW + 7320, posted="https://x/1#c"), (None, None))  # nothing re-runs
        self.assertEqual(self.reflect(NOW + 5 * 86400)[1][5], self.W20)  # Monday 00:00: the next week
        self.hold(self.W20)
        self.assertEqual(self.reflect(NOW + 6 * 86400), (None, None))  # in flight: no second run

    def test_reflection_timer_catches_up_once_and_coalesces_a_close(self):  # #1521
        self.hold("close-0")  # another run in flight holds the pool's reflection slot
        self.put("reflection/ledger.json", json.dumps({"slot": NOW - 60 * 86400, "closed": [1], "pending": [],
                                                       "completed": {}, "request": {
                                                           "window": "close-0", "run": "r0", "at": NOW, "outcome": "started"}}))
        self.assertEqual(self.reflect(NOW + 5 * 86400, closed=(1, 2)), (None, None))  # woke two months late
        self.assertEqual(self.ledger()["pending"], [self.W20, "close-2"])  # one week caught up, the close at once
        os.remove(os.path.join(self.state, "runs", "riley-reflection.json"))
        outcome, argv = self.reflect(NOW + 5 * 86400 + 60, closed=(1, 2), posted="https://x/0#c")
        self.assertEqual((outcome, argv[5]), ("started", "close-2+" + self.W20))  # overlapping windows: one run
        self.assertEqual(sorted(self.ledger()["completed"]), ["close-0"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "triage")))  # independent of triage's ledger

    def test_reflection_timer_retries_a_failed_start_once_per_retry(self):  # #1521
        self.assertEqual(self.reflect(NOW, rc=1, stdout="crew: session x not reachable\n")[0],
                         "failed: crew: session x not reachable")
        run = self.ledger()["request"]["run"]
        self.assertEqual(self.reflect(NOW + 599), (None, None))
        queued = "queued: researcher research reflection (researcher cap reached)\n"
        outcome, argv = self.reflect(NOW + 600, stdout=queued)
        self.assertEqual((outcome, argv[argv.index("--run-id") + 1]), ("queued", run))  # the same run ID
        self.assertEqual(self.reflect(NOW + 1300, stdout=queued), (None, None))  # still queued: no second entry
        with open(os.path.join(self.state, "spawn-queue.jsonl")) as f:
            self.assertEqual(len(f.readlines()), 1)

    def test_reflection_timer_reruns_a_run_that_ended_without_a_report(self):  # #1521
        self.reflect(NOW)
        self.assertEqual(self.reflect(NOW + 60), ("failed: run ended without a posted report", None))
        self.assertEqual(self.reflect(NOW + 659)[1], None)

        def unreadable(*_):
            raise RuntimeError("crew: gh issue list: HTTP 502")
        self.assertEqual(self.reflect(NOW + 660, posted=unreadable), (None, None))  # unverified: no second run
        self.assertTrue(self.ledger()["request"]["outcome"].startswith("failed: cannot read the reflection log"))
        self.assertEqual(self.reflect(NOW + 1260)[0], "started")
        quiet = "https://x/2#quiet"  # a quiet window's proposals=0 report still completes it
        self.assertEqual(self.reflect(NOW + 1320, posted=quiet)[0], "completed: " + quiet)

    def test_scan_ask_wakes_at_its_deadline_once(self):  # #287
        self.ask("12", "2033-05-17T20:33:20-07:00")  # == NOW
        self.assertEqual(self.asks(NOW - 1), [])
        wakes = [w for w in self.scan(NOW, self.seen) if w["reason"] == "ask"]
        self.assertEqual([self.mod.reason(w) for w in wakes], ["ask: 12 deadline 2033-05-17T20:33:20-07:00"])
        self.assertEqual(self.asks(NOW + 3600, self.seen), [])  # once per deadline
        self.ask("12", "2033-05-17T20:43:20-07:00")  # moved to NOW + 600: fires again at the new deadline
        self.assertEqual(self.asks(NOW + 599, self.seen), [])
        self.assertEqual(self.asks(NOW + 600, self.seen), ["12 deadline 2033-05-17T20:43:20-07:00"])
        self.put("asks/13.json", "{")  # a bad record wakes at once, once
        self.assertEqual(self.asks(NOW + 600, self.seen), ["13 deadline unreadable"])
        self.assertEqual(self.asks(NOW + 601, self.seen), [])

    def test_pause_lands_the_next_scan_on_an_ask_deadline(self):  # #287
        self.assertEqual(self.mod.pause(self.state, NOW - 2, 5), 5)  # no open ask
        self.ask("12", "2033-05-17T20:33:20-07:00")  # == NOW
        self.assertEqual(self.mod.pause(self.state, NOW - 2, 5), 2)
        self.assertEqual(self.mod.pause(self.state, NOW - 60, 5), 5)
        self.assertEqual(self.mod.pause(self.state, NOW, 5), 5)  # due: this scan wakes, no shorter sleep

    def test_watch_ask_deadline_wakes_while_backstop_backed_off(self):  # #287
        self.assertEqual(self.crew("kill", "ben-7", "--project", self.project).returncode, 0)  # nothing in flight
        self.put("wake/watch-state.json", json.dumps({"idle": 4}))  # backstop at its cap, 16 x 3600 s
        self.ask("12", "2020-01-01T09:00:00-08:00")  # past due
        out, err = self.watch("--backstop", "3600").communicate(timeout=10)
        self.assertEqual(out, "ask: 12 deadline 2020-01-01T09:00:00-08:00\n", err)
        self.assertEqual(self.queue_lines()[0]["reason"], "ask")
        with open(os.path.join(self.state, "wake", "watch-state.json")) as f:
            self.assertEqual(json.load(f)["idle"], 4)  # an ask wake, not a backstop

    def decision(self):
        snap = dict(ts="2033-05-18T03:33:20Z", workers=[], reservations=[], memory={"os": "darwin", "level": "normal"},
                    load=0.5, errors=0, orphans=[], demand={"builder": [{"kind": "merge-up", "refs": ["#601"]}], "reviewer": []})
        self.put("schedule/decisions-20330518.jsonl", json.dumps(
            dict(action="snapshot", snapshot=snap, target=2, caps={"builder": 5, "reviewer": 2})) + "\n")
        return snap

    def test_scan_schedule_stuck_wakes_once_per_deferral(self):  # #628
        snap = self.decision()
        deferred = lambda since: self.put("schedule/deferred.json", json.dumps({"builder": {
            "#601": {"kind": "merge-up", "class": 3, "reasons": ["target"], "since": since},
            "#9": {"kind": "build", "class": 7, "reasons": ["target"], "since": "2020-01-01T00:00:00Z"}}}))
        stuck = lambda now, seen=None: [w for w in self.scan(now, seen) if w["reason"] == "schedule-stuck"]
        deferred("2033-05-18T03:03:20Z")  # NOW - 1800
        self.assertEqual(stuck(NOW - 1), [])
        wakes = stuck(NOW, self.seen)
        self.assertEqual([self.mod.reason(w) for w in wakes],
                         ["schedule-stuck: builder #601 merge-up class 3 deferred since 2033-05-18T03:03:20Z: target"])
        self.assertEqual(wakes[0]["snapshot"], snap)
        self.assertEqual(stuck(NOW + 60, self.seen), [])  # deduplicated
        deferred("2033-05-18T02:00:00Z")  # a new deferral of the same ref
        self.assertEqual(len(stuck(NOW + 60, self.seen)), 1)
        self.put("schedule/deferred.json", "{")
        self.assertEqual(stuck(NOW + 60), [])  # unreadable: no wake, no crash

    def test_watch_exit_line_carries_the_schedule_summary(self):  # #628
        self.decision()
        p = self.watch()
        self.put("status/ben-7.status", "done: PR #12\n")
        out, err = p.communicate(timeout=10)
        self.assertEqual(out.splitlines(), ["status: ben-7 done: PR #12", "schedule: builders 0/5 reviewers 0/2 "
                         "target 2 (load 0.5/cpu mem normal errors 0) queued merge-up 1; deferred 0; held 0; orphans 0; terminal 0"], err)

    def watch(self, *args):
        return subprocess.Popen([sys.executable, CREW, "watch", "--project", self.project, "--interval", "0.05",
                                 "--source-interval", "0", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)

    def test_watch_names_a_bypass_permission_dialog(self):  # #1968, through the shipped entry point
        with open(self.project) as f:
            profile = f.read()
        dialog = r"dialog: ben-7 ambiguous, silent \d+s, escalate"
        cases = [("claude-proceed", "bypass", dialog + ", permission-dialog: Do you want to proceed\\?"),
                 ("codex-approval", "bypass", dialog + ", permission-dialog: Would you like to run the following command\\?"),
                 ("claude-trust", "bypass", dialog), ("codex-trust", "bypass", dialog), ("claude-proceed", "auto", dialog)]
        for name, mode, want in cases:
            with self.subTest(name=name, mode=mode):
                with open(self.project, "w") as f:
                    f.write(profile + '[runtime.options]\npermission_mode = "%s"\n' % mode)
                for left in ("watch-state.json", "queue.jsonl"):  # each case wakes afresh, its queue drained
                    if os.path.exists(os.path.join(self.state, "wake", left)):
                        os.remove(os.path.join(self.state, "wake", left))
                self.set_pane(10, screen=screen(name))
                p = self.watch()
                out, err = p.communicate(timeout=30)
                self.assertEqual((p.returncode, err), (0, "mdstack: config %s\n" % self.project))
                self.assertRegex(out, "^%s\n$" % want)
                w = self.queue_lines()[-1]
                self.assertEqual((w["reason"], w.get("class"), "prompt" in w),
                                 ("dialog", "permission-dialog", True) if "permission-dialog" in want else ("dialog", None, False))

    def test_watch_blocks_then_exits_with_reason_and_queue(self):
        p = self.watch()
        pidfile = os.path.join(self.state, "wake", "watcher.pid")
        for _ in range(100):
            if os.path.exists(pidfile):
                break
            time.sleep(0.05)
        with open(pidfile) as f:
            self.assertEqual(int(f.read()), p.pid)
        self.assertIsNone(p.poll())  # blocks: fresh run, nothing new
        self.put("status/ben-7.status", "done: PR #12\n")
        out, err = p.communicate(timeout=10)
        self.assertEqual((p.returncode, out), (0, "status: ben-7 done: PR #12\n"), err)
        with open(os.path.join(self.state, "wake", "queue.jsonl")) as f:
            self.assertEqual(json.loads(f.readline())["line"], "done: PR #12")
        self.assertFalse(os.path.exists(pidfile))
        self.assertNotIn("send-keys", [c[0] for c in self.calls()])

    def test_muse_versioned_coordinator_wakes_but_dialog_does_not(self):
        source = ["--source", "printf 'pr-merged #9\\n'"]
        nudge = ["send-keys", "-t", "=crew-acme-widgets:0", "-l", "wake: watcher"]
        self.set_pane(0, command="muse-bin-0.1.0-R708.1", screen=
                      "Do you trust this workspace?\nUse Up/Down or 1/2, then Enter. Esc quits.")
        self.watch(*source).communicate(timeout=10)
        self.assertNotIn(nudge, self.calls())
        self.assertEqual(self.queue_lines()[-1]["reason"], "dialog")
        self.set_pane(0, command="muse-bin-0.1.0-R708.1")
        self.watch(*source).communicate(timeout=10)
        self.assertIn(nudge, self.calls())

    def test_watch_source_event_and_nudge_idle_coordinator(self):
        source = ["--source", "printf 'pr-merged #9\\n'"]
        nudge = ["send-keys", "-t", "=crew-acme-widgets:0", "-l", "wake: watcher"]
        self.set_pane(0, command="claude", activity=str(int(time.time())))  # busy: output just now
        out, _ = self.watch(*source).communicate(timeout=10)
        self.assertEqual(out, "poll: pr-merged #9\n")
        self.set_pane(0, command="claude")  # idle: no output since 1970
        self.watch(*source, "--no-nudge").communicate(timeout=10)
        self.assertNotIn(nudge, self.calls())
        self.watch(*source).communicate(timeout=10)
        self.assertIn(nudge, self.calls())

    def test_watch_never_types_into_a_coordinator_prompt(self):  # #315
        source = ["--source", "printf 'pr-merged #9\\n'"]
        prompts = [n for n in STUCK if not n.endswith("-api-error")]  # an API error over a composer is no prompt (#1346)
        for name in prompts:  # idle coordinator showing a prompt: queue a dialog wake instead of the wake line
            with self.subTest(name):
                self.set_pane(0, command="claude", screen=screen(name))
                out, err = self.watch(*source).communicate(timeout=10)
                self.assertEqual(out, "poll: pr-merged #9 (+1 more in wake/queue.jsonl)\n", err)  # own record once
                w = self.queue_lines()[-1]
                self.assertEqual({k: w[k] for k in ("reason", "window", "liveness", "action")},
                                 {"reason": "dialog", "window": "ash", "liveness": "ambiguous", "action": "escalate"})
        self.assertNotIn("send-keys", [c[0] for c in self.calls()])
        for name in WORKING:
            with self.subTest(name):
                self.set_pane(0, command="claude", screen=screen(name))
                out, _ = self.watch(*source).communicate(timeout=10)
                self.assertEqual(out, "poll: pr-merged #9\n")
        self.assertEqual(self.calls().count(["send-keys", "-t", "=crew-acme-widgets:0", "-l", "wake: watcher"]),
                         len(WORKING))  # a normal screen still gets the wake line

    def test_persistent_watcher_wakes_a_coordinator_stopped_by_a_gateway_error(self):  # #1346 review R1
        nudge = ["send-keys", "-t", "=crew-acme-widgets:0", "-l", "wake: watcher"]
        for name in ("claude-api-error", "codex-api-error"):
            with self.subTest(name):
                os.makedirs(os.path.join(self.tmp, name))
                flag = shlex.quote(os.path.join(self.tmp, name, "polled"))
                once = "test -e %s || { touch %s; printf 'pr-merged #9\\n'; }" % (flag, flag)
                self.set_pane(0, command=name.split("-")[0], screen=screen(name))
                before = self.calls().count(nudge)
                p = self.watch("--persistent", "--renudge", "0.5", "--source", "sh -c %s" % shlex.quote(once))
                self.addCleanup(lambda p=p: p.poll() is None and p.kill())
                self.wait_for(lambda: self.calls().count(nudge) >= before + 2)  # the wake, then a re-nudge
                self.assertIsNone(p.poll())
                p.send_signal(signal.SIGTERM)
                p.communicate(timeout=10)
                self.assertNotIn("dialog", [w["reason"] for w in self.queue_lines()])

    def test_watch_backstop_backs_off_while_idle(self):
        self.assertEqual(self.crew("kill", "ben-7", "--project", self.project).returncode, 0)
        idle = []
        for _ in range(2):
            out, _ = self.watch("--backstop", "0.1").communicate(timeout=10)
            self.assertEqual(out, "backstop: due (nothing in flight)\n")
            with open(os.path.join(self.state, "wake", "watch-state.json")) as f:
                idle.append(json.load(f)["idle"])
        self.assertEqual(idle, [1, 2])

    def test_in_flight_counts_only_work_that_can_move_without_the_owner(self):  # #394
        self.assertEqual(self.mod.in_flight(self.state), "work")  # ben-7 on issue #7, nothing held
        self.ask("7", "2033-05-18T10:00:00-07:00")
        self.assertEqual(self.mod.in_flight(self.state), "held")  # its only run waits on an owner ask
        os.remove(os.path.join(self.state, "asks", "7.json"))
        self.put("poll-state.json", json.dumps({"prs": {}, "issues": [], "held": ["#7"]}))
        self.assertEqual(self.mod.in_flight(self.state), "held")  # a hold label in the poll snapshot
        rec = dict.fromkeys(("index", "repo", "worktree", "claim", "engine", "model", "effort", "harness"), "x")
        self.put("runs/vera-9.json", json.dumps(dict(rec, role="reviewer", item="PR #9", **{"pass": "review"})))
        self.assertEqual(self.mod.in_flight(self.state), "work")  # mixed held and live runs do not back off
        self.put("runs/vera-9.json", json.dumps(dict(rec, role="reviewer", item="a sweep", **{"pass": "review"})))
        self.assertEqual(self.mod.in_flight(self.state), "work")  # an unclassified item counts as live
        os.remove(os.path.join(self.state, "runs", "vera-9.json"))
        self.put("poll-state.json", json.dumps({"prs": {}, "issues": [], "held": ["#8"]}))
        self.assertEqual(self.mod.in_flight(self.state), "work")  # an unrelated hold does not back off
        self.put("poll-state.json", "{not json")
        self.assertEqual(self.mod.in_flight(self.state), "work")  # unreadable snapshot: nothing positively held
        self.assertEqual(self.crew("kill", "ben-7", "--project", self.project).returncode, 0)
        self.assertEqual(self.mod.in_flight(self.state), "nothing")

    def test_watch_backstop_waits_hours_while_only_held_work_is_open(self):  # #394
        self.ask("7", "2033-05-18T10:00:00-07:00")  # ben-7's issue is parked on the owner
        p = self.watch("--backstop", "0.1")
        self.armed(p)
        time.sleep(1)  # ten short backstops
        self.assertIsNone(p.poll())  # backed off to max(16 x 0.1 s, 4 h)
        os.remove(os.path.join(self.state, "asks", "7.json"))  # the owner answered: live work again
        out, err = p.communicate(timeout=10)
        self.assertEqual(out, "backstop: due (work in flight)\n", err)
        with open(os.path.join(self.state, "wake", "watch-state.json")) as f:
            self.assertEqual(json.load(f)["idle"], 0)

    def test_watch_backstop_extends_when_active_work_becomes_held(self):  # #394
        p = self.watch("--backstop", "3")
        self.armed(p)  # ben-7 on issue #7 is live: the short backstop
        self.put("poll-state.json", json.dumps({"prs": {}, "issues": [], "held": ["#7"]}))  # the owner holds it
        time.sleep(5)  # past the short backstop
        if p.poll() is not None:  # recomputed to max(16 x 3 s, 4 h) from arming
            self.fail("watcher exited: %r %r" % p.communicate())
        os.remove(os.path.join(self.state, "poll-state.json"))
        out, err = p.communicate(timeout=10)
        self.assertEqual(out, "backstop: due (work in flight)\n", err)

    def test_watch_ask_deadline_wakes_while_only_held_work_is_open(self):  # #394, #287
        self.ask("7", "2020-01-01T09:00:00-08:00")  # past due: held, and its deadline still wakes
        out, err = self.watch("--backstop", "3600").communicate(timeout=10)
        self.assertEqual(out, "ask: 7 deadline 2020-01-01T09:00:00-08:00\n", err)

    def armed(self, p):
        for _ in range(100):
            if os.path.exists(os.path.join(self.state, "wake", "watch-state.json")):
                break
            time.sleep(0.05)
        self.assertIsNone(p.poll())  # blocking, state saved after a scan

    def queue_lines(self):
        with open(os.path.join(self.state, "wake", "queue.jsonl")) as f:
            return [json.loads(line) for line in f]

    def test_watch_source_timeout_never_wedges(self):
        start = time.monotonic()
        out, _ = self.watch("--source", "sleep 30", "--source-timeout", "1", "--source-failures", "1").communicate(
            timeout=20)
        self.assertLess(time.monotonic() - start, 15)  # cut off at --source-timeout, long before the 30 s
        self.assertEqual(out, "source-failing: sleep 30: 1 failures in a row, last: timed out after 1s\n")
        self.assertEqual(self.queue_lines()[0]["reason"], "source-failing")

    def incidents(self):
        with open(os.path.join(self.state, "wake", "incidents.jsonl")) as f:
            return [json.loads(line) for line in f]

    def test_watch_transient_source_failures_wake_once_after_n_in_a_row(self):  # #702
        counter = os.path.join(self.tmp, "calls")
        code = ("import sys; n = len(open(%r).read()) if __import__('os').path.exists(%r) else 0\n"
                "open(%r, 'a').write('x')\n"
                "if n != 2: print('crew: gh pr list failed: HTTP 504: 504 Gateway Timeout'); sys.exit(75)\n"
                ) % (counter, counter, counter)  # calls 1-2 fail, 3 succeeds quietly, 4-6 fail
        out, err = self.watch("--source", shlex.join([sys.executable, "-c", code])).communicate(timeout=30)
        self.assertEqual(out, "source-failing: %s: 3 failures in a row, last: crew: gh pr list failed: HTTP 504: "
                         "504 Gateway Timeout\n" % shlex.join([sys.executable, "-c", code]), err)
        with open(counter) as f:
            self.assertEqual(len(f.read()), 6)  # no wake at failures 1, 2, 4 or 5
        self.assertEqual([i["consecutive"] for i in self.incidents()], [1, 2, 1, 2, 3])
        self.assertEqual([q["reason"] for q in self.queue_lines()], ["source-failing"])

    def counted(self, line="", code=0):
        """A source command that appends one byte to a counter per run, prints line and exits code; (cmd, count)."""
        counter = os.path.join(self.tmp, "calls")
        cmd = shlex.join([sys.executable, "-c", "import sys; open(%r, 'a').write('x'); print(%r); sys.exit(%d)"
                          % (counter, line, code)])
        return cmd, lambda: os.path.getsize(counter) if os.path.exists(counter) else 0

    def run_for(self, seconds, *args):
        p = self.watch(*args, "--no-nudge")
        self.armed(p)
        time.sleep(seconds)
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=10)
        with open(os.path.join(self.state, "wake", "watch-state.json")) as f:
            return json.load(f)

    def test_watch_runs_sources_once_per_source_interval_across_a_rearm(self):  # #1300
        cmd, count = self.counted()
        self.run_for(1, "--source", cmd, "--source-interval", "60")  # ~20 scans at --interval 0.05
        self.assertEqual(count(), 1)
        self.run_for(0.5, "--source", cmd, "--source-interval", "60")  # a re-armed watcher keeps the due time
        self.assertEqual(count(), 1)

    def test_watch_holds_sources_until_a_rate_limit_reset_capped_at_an_hour(self):  # #1300
        for ahead, hold in [(1800, 1800), (36000, 3600)]:
            with self.subTest(ahead=ahead):
                until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + ahead))
                cmd, count = self.counted("crew: gh pr list rate-limited until %s: API rate limit exceeded" % until, 75)
                start, before = time.time(), count()
                seen = self.run_for(0.5, "--source", cmd)  # --source-interval 0: due every scan but for the hold
                self.assertEqual(count() - before, 1)
                self.assertAlmostEqual(seen["sources_next"], start + hold, delta=5)
                self.assertEqual(self.incidents()[-1]["consecutive"], 1)
                os.remove(os.path.join(self.state, "wake", "watch-state.json"))

    def crew_home(self, *args):
        """A watcher run from a copied crew home of its own, so the test can update its code on disk."""
        root = os.path.join(self.tmp, "home")
        shutil.copytree(os.path.dirname(os.path.dirname(CREW)), root,
                        ignore=shutil.ignore_patterns(".git", ".crew", "test-*", "fixtures"))
        scripts = os.path.join(root, "scripts")
        p = subprocess.Popen([sys.executable, os.path.join(root, "cli", "mdstack"), "watch", "--project", self.project,
                              *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        self.armed(p)
        return scripts, p

    def test_watch_reexecs_before_routing_with_a_new_profile_key(self):  # #702 R1: code and profile updated together
        scripts, p = self.crew_home("--interval", "2", "--no-nudge")
        time.sleep(0.3)  # asleep between scans
        config = os.path.join(os.path.dirname(scripts), "core", "crew-config.py")
        with open(config) as f:
            text = f.read()
        with open(config, "w") as f:
            f.write(text.replace('"poll_interval": (int, 60)', '"poll_interval": (int, 60), "reload_probe": (int, 1)'))
        with open(self.project, "a") as f:
            f.write("\n[runtime.options]\nreload_probe = 1\n")
        self.put("status/ben-7.status", "done: PR #12\n")
        out, err = p.communicate(timeout=20)
        self.assertEqual((p.returncode, out), (0, "status: ben-7 done: PR #12\n"), err)
        config = "mdstack: config %s\n" % self.project  # at start and again after the re-exec (#1324)
        self.assertEqual(err, config + "crew: watch: crew code changed on disk; re-exec\n" + config)

    def test_watch_reexecs_when_crew_code_changes(self):  # #702
        scripts, p = self.crew_home("--interval", "0.05")
        with open(os.path.join(os.path.dirname(scripts), "environments", "terminal", "crew.d", "watch.py"), "a") as f:
            f.write("\nsys.stderr.write('reloaded\\n')\n")  # runs at import, so only in a new process image
        time.sleep(1)  # a few scans: the re-exec'd watcher is armed again under the same PID
        self.assertIsNone(p.poll())
        with open(os.path.join(self.state, "wake", "watcher.pid")) as f:
            self.assertEqual(int(f.read()), p.pid)
        self.put("status/ben-7.status", "done: PR #12\n")
        out, err = p.communicate(timeout=10)
        self.assertEqual((p.returncode, out), (0, "status: ben-7 done: PR #12\n"), err)
        config = "mdstack: config %s\n" % self.project  # at start and again after the re-exec (#1324)
        self.assertEqual(err, config + "crew: watch: crew code changed on disk; re-exec\nreloaded\n" + config)
        self.assertFalse(os.path.exists(os.path.join(self.state, "wake", "watcher.pid")))

    def test_watch_source_timeout_floor_outlasts_a_short_interval(self):  # #272
        slow = shlex.join([sys.executable, "-c", "import time; time.sleep(0.5); print('pr-merged #9')"])
        out, _ = self.watch("--source", slow).communicate(timeout=20)  # 10 x --interval 0.05
        self.assertEqual(out, "poll: pr-merged #9\n")

    def test_watch_wakes_on_queue_growth_without_requeueing(self):
        p = self.watch()
        self.armed(p)
        rec = {"id": "poll-1", "source": "poll", "reason": "poll", "event": "ci-passed", "refs": ["#12"]}
        self.put("wake/queue.jsonl", json.dumps(rec) + "\n")  # an mdstack poll loop in its own window
        out, err = p.communicate(timeout=10)
        self.assertEqual(out, "poll: ci-passed\n", err)
        self.assertEqual(self.queue_lines(), [rec])
        out, _ = self.watch("--backstop", "0.1").communicate(timeout=10)  # offset saved: no second wake
        self.assertEqual(out, "backstop: due (work in flight)\n")

    def test_watch_does_not_double_queue_a_poll_source(self):
        script = os.path.join(self.tmp, "poll-once.py")  # appends its own record and prints a line, like mdstack poll
        with open(script, "w") as f:
            f.write("import json, sys\nwith open(sys.argv[1], 'a') as f:\n"
                    "    f.write(json.dumps({'reason': 'poll', 'event': 'ci-failed'}) + '\\n')\n"
                    "print('crew: poll: ci-failed -> builder #12')\n")
        os.makedirs(os.path.join(self.state, "wake"), exist_ok=True)
        queue = os.path.join(self.state, "wake", "queue.jsonl")
        source = ["--source", shlex.join([sys.executable, script, queue]), "--interval", "5"]  # timeout > startup
        out, _ = self.watch(*source).communicate(timeout=20)
        self.assertEqual(out, "poll: ci-failed\n")
        self.assertEqual(self.queue_lines(), [{"reason": "poll", "event": "ci-failed"}])

    def test_watch_triage_timer_reads_the_queue_this_scans_poll_wrote(self):  # #1098: resume, overdue slot
        with open(self.project, "a") as f:
            f.write("\n[triage]\nenabled = true\n")
        self.put("triage/queue.json", json.dumps({"items": []}))  # the pre-pause poll's queue
        self.put("triage/sweep.json", json.dumps({"at": time.time() - 20 * 3600, "outcome": "skipped: empty queue"}))
        script = os.path.join(self.tmp, "poll-once.py")  # queues the issue opened during the pause, like mdstack poll
        with open(script, "w") as f:
            f.write("import json, sys\nwith open(sys.argv[1], 'w') as f:\n"
                    "    json.dump({'items': [{'repo': 'acme/widgets', 'issue': 9, 'reason': 'new'}]}, f)\n"
                    "print('crew: poll: triage queued #9')\n")
        queue = os.path.join(self.state, "triage", "queue.json")
        out, err = self.watch("--source", shlex.join([sys.executable, script, queue])).communicate(timeout=60)
        self.assertEqual(out, "poll: crew: poll: triage queued #9\n", err)
        with open(os.path.join(self.state, "triage", "sweep.json")) as f:
            self.assertNotEqual(json.load(f)["outcome"], "skipped: empty queue")  # the overdue slot sweeps #9

    def test_second_watcher_leaves_the_armed_ones_pid_file(self):  # #591
        p = self.watch()
        self.armed(p)
        pidfile = os.path.join(self.state, "wake", "watcher.pid")
        with open(self.ps, "w") as f:
            json.dump({"command": {str(p.pid): "python3 cli/mdstack watch --project crew.toml"}}, f)
        second = self.watch()
        out, _ = second.communicate(timeout=10)
        self.assertEqual((second.returncode, out), (0, "crew: a watcher is already armed (pid %d)\n" % p.pid))
        with open(pidfile) as f:
            self.assertEqual(int(f.read()), p.pid)
        self.assertIsNone(p.poll())
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=10)
        self.assertFalse(os.path.exists(pidfile))

    @staticmethod
    def read(path):
        with open(path) as f:
            return f.read()

    def wait_for(self, check, timeout=20):
        deadline = time.monotonic() + timeout
        while not check():
            self.assertLess(time.monotonic(), deadline, "timed out")
            time.sleep(0.05)

    def test_persistent_watcher_nudges_keeps_scanning_and_renudges_until_drained(self):  # #1346
        once = "test -e %s || { touch %s; printf 'pr-merged #9\\n'; }" % ((os.path.join(self.tmp, "polled"),) * 2)
        nudge = ["send-keys", "-t", "=crew-acme-widgets:0", "-l", "wake: watcher"]
        self.set_pane(0, command="claude")  # idle: a coordinator whose turn ended on a gateway error
        log = os.path.join(self.tmp, "watch.out")
        with open(log, "w") as out:
            p = subprocess.Popen([sys.executable, CREW, "watch", "--project", self.project, "--interval", "0.05",
                                  "--source-interval", "0", "--persistent", "--renudge", "1", "--source",
                                  "sh -c %s" % shlex.quote(once)], stdout=out, stderr=subprocess.DEVNULL, env=self.env)
        self.wait_for(lambda: self.calls().count(nudge) >= 1)
        self.assertIsNone(p.poll())  # the wake did not end the watcher
        self.wait_for(lambda: self.calls().count(nudge) >= 2)  # nobody drained the queue: nudged again
        self.put("status/ben-7.status", "done: PR #12\n")  # a later event is still routed and nudged
        self.wait_for(lambda: "status: ben-7 done: PR #12" in self.read(log))
        with open(os.path.join(self.state, "wake", "queue.jsonl"), "w"):
            pass  # the coordinator drained it
        time.sleep(0.3)
        drained = self.calls().count(nudge)
        time.sleep(1.5)
        self.assertEqual(self.calls().count(nudge), drained)  # nothing left: no more nudges
        self.assertIsNone(p.poll())
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=10)
        lines = self.read(log).splitlines()
        self.assertEqual(lines[0], "poll: pr-merged #9")
        self.assertIn("renudge: wake/queue.jsonl not drained", lines)
        self.assertFalse(os.path.exists(os.path.join(self.state, "wake", "watcher.pid")))

    def test_detach_starts_one_persistent_watcher_that_outlives_its_caller(self):  # #1346
        r = self.crew("watch", "--project", self.project, "--interval", "0.05", "--detach")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = int(re.fullmatch(r"crew: persistent watcher started \(pid (\d+), log (\S+)\)\n", r.stdout)[1])
        pidfile = os.path.join(self.state, "wake", "watcher.pid")
        self.wait_for(lambda: os.path.exists(pidfile) and self.read(pidfile).strip() == str(pid))
        self.addCleanup(lambda: subprocess.run(["kill", str(pid)], capture_output=True))
        self.assertNotEqual(os.getpgid(pid), os.getpgid(0))  # its own session: the caller's signals miss it
        with open(self.ps, "w") as f:
            json.dump({"command": {str(pid): "python3 cli/mdstack watch --persistent"}}, f)
        again = self.crew("watch", "--project", self.project, "--detach")
        self.assertEqual((again.returncode, again.stdout), (0, "crew: a watcher is already armed (pid %d)\n" % pid))
        os.kill(pid, signal.SIGTERM)
        self.wait_for(lambda: not os.path.exists(pidfile))

    def test_down_stops_a_watcher_whose_pid_file_was_lost(self):  # #1346 review R2: the lock names it
        p = self.watch("--persistent")
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.armed(p)
        os.remove(os.path.join(self.state, "wake", "watcher.pid"))
        with open(self.ps, "w") as f:
            json.dump({"command": {str(p.pid): "python3 cli/mdstack watch --persistent"}}, f)
        with open(self.state_file, "w") as f:
            json.dump({}, f)  # no session left
        r = self.crew("down", "--project", self.project)
        self.assertEqual((r.returncode, r.stdout), (0, "crew: crew-acme-widgets not running; watcher stopped\n"),
                         r.stderr)
        p.communicate(timeout=10)
        self.assertEqual(p.returncode, 128 + signal.SIGTERM)
        self.assertEqual(self.crew("down", "--project", self.project).stdout, "crew: crew-acme-widgets not running\n")

    def test_stop_watcher_never_signals_an_unidentified_lock_holder(self):  # #1346 review R2: refuse, never guess
        p = self.watch("--persistent")
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.armed(p)
        os.remove(os.path.join(self.state, "wake", "watcher.pid"))  # and the fake ps names no watch command
        with open(self.state_file, "w") as f:
            json.dump({}, f)
        r = self.crew("down", "--project", self.project)
        self.assertEqual((r.returncode, r.stdout), (1, "crew: refusing down: the watcher (pid unknown) is still armed\n"))
        self.assertIsNone(p.poll())  # never signalled
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=10)

    def test_simultaneous_starts_leave_exactly_one_watcher(self):  # #399: the lock, not a check-then-write
        first, second = self.watch(), self.watch()
        for _ in range(200):
            if first.poll() is not None or second.poll() is not None:
                break
            time.sleep(0.05)
        live, done = (first, second) if second.poll() is not None else (second, first)
        out, _ = done.communicate(timeout=10)
        self.assertEqual((done.returncode, out), (0, "crew: a watcher is already armed (pid %d)\n" % live.pid))
        self.armed(live)
        with open(os.path.join(self.state, "wake", "watcher.pid")) as f:
            self.assertEqual(int(f.read()), live.pid)
        live.send_signal(signal.SIGTERM)
        live.communicate(timeout=10)
        third = self.watch()  # the lock went with the watcher
        self.armed(third)
        third.send_signal(signal.SIGTERM)
        third.communicate(timeout=10)

    def test_watcher_removes_only_its_own_pid_file(self):  # #591: a stale or reused PID does not block arming
        pidfile = os.path.join(self.state, "wake", "watcher.pid")
        self.put("wake/watcher.pid", "%d\n" % os.getpid())  # live, but not mdstack watch
        p = self.watch()
        self.armed(p)
        self.put("wake/watcher.pid", "%d\n" % os.getpid())  # another watcher took over the file
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=10)
        with open(pidfile) as f:
            self.assertEqual(int(f.read()), os.getpid())

    def test_watch_sigterm_removes_pid_file_and_saves_state(self):
        p = self.watch()
        self.armed(p)
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=10)
        self.assertEqual(p.returncode, 128 + signal.SIGTERM)
        self.assertFalse(os.path.exists(os.path.join(self.state, "wake", "watcher.pid")))
        with open(os.path.join(self.state, "wake", "watch-state.json")) as f:
            self.assertIn("queue", json.load(f))

    def test_watch_signal_waits_for_a_running_child(self):  # #272: a signal never leaves a child running
        done = os.path.join(self.tmp, "child-done")
        code = "import os, signal, time; os.kill(os.getppid(), signal.SIGTERM); time.sleep(0.3); open(%r, 'w')" % done
        p = self.watch("--source", shlex.join([sys.executable, "-c", code]))
        p.communicate(timeout=20)
        self.assertEqual(p.returncode, 128 + signal.SIGTERM)
        self.assertTrue(os.path.exists(done))  # the child finished before the watcher exited
        self.assertFalse(os.path.exists(os.path.join(self.state, "wake", "watcher.pid")))

    def test_watch_second_signal_exits_at_once(self):  # #272: a held signal never makes a hung child unkillable
        started = os.path.join(self.tmp, "child-started")
        code = "import time; open(%r, 'w'); time.sleep(60)" % started
        p = self.watch("--source", shlex.join([sys.executable, "-c", code]), "--source-timeout", "60")
        for _ in range(200):
            if os.path.exists(started):
                break
            time.sleep(0.05)
        start = time.monotonic()
        while p.poll() is None and time.monotonic() - start < 20:  # signals sent apart, so two are delivered
            p.send_signal(signal.SIGTERM)
            time.sleep(0.1)
        p.communicate(timeout=10)
        self.assertEqual(p.returncode, 128 + signal.SIGTERM)
        self.assertLess(time.monotonic() - start, 20)

    def test_watch_sighup_like_sigterm(self):  # #234 N8
        p = self.watch()
        self.armed(p)
        p.send_signal(signal.SIGHUP)
        p.communicate(timeout=10)
        self.assertEqual(p.returncode, 128 + signal.SIGHUP)
        self.assertFalse(os.path.exists(os.path.join(self.state, "wake", "watcher.pid")))


class DeliveryProgress(DeliveryBase):  # #1850 D2.4
    def deliveries(self, now, seen):
        with mock.patch.dict(os.environ, self.env):
            send = self.mod.commands()["send"]
            values, _, _ = self.mod.profile(argparse.Namespace(project=self.project, org_profile=None))
            wakes = self.mod.scan(self.state, "crew-acme-widgets", now, 900, seen, mine=send.ours(self.project, None, values))
        return [(w["window"], w["id"], w["delivery"], w["worker"], w["action"]) for w in wakes if w["reason"] == "delivery"]

    def test_pending_delivery_wakes_once_per_changed_actionable_state(self):
        self.show(self.BUSY)
        self.assertEqual(self.send("fix", "#12", "a" * 40).returncode, 0)
        msg = self.inbox()[0]
        foreign = dict(msg, id="20331118T031000Z-f0e1d2", context=dict(msg["context"], repo="other/repo"))
        with open(os.path.join(self.state, "inbox", "ben-7.jsonl"), "a") as f:
            f.write(json.dumps(foreign) + "\n")
        with open(os.path.join(self.state, "runs", "ben-7.delivery.jsonl"), "a") as f:
            f.write(json.dumps(dict(id=foreign["id"], event="recorded", run=None, status=0)) + "\n")
        seen = {"offsets": {}, "keys": {}}
        typed = self.typed()
        self.assertEqual(self.deliveries(NOW, seen), [])  # first sight: busy, nothing to do
        self.assertEqual(list(seen["deliveries"]), ["ben-7 " + msg["id"]])  # the foreign record is never tracked
        self.assertEqual(self.deliveries(NOW + 600, seen), [])  # still busy past any wait: no wake, no fault
        self.show(self.IDLE)
        self.assertEqual(self.deliveries(NOW + 660, seen), [("ben-7", msg["id"], "submitted", "idle", "nudge")])
        self.assertEqual(self.deliveries(NOW + 720, seen), [])  # a duplicate wake: none
        self.show(self.IDLE, dead="1")
        self.assertEqual(self.deliveries(NOW + 780, seen), [("ben-7", msg["id"], "submitted", "dead", "restart")])
        self.assertEqual(self.typed(), typed)  # the watcher types nothing
        self.show(self.IDLE)
        self.put("status/ben-7.status", "ack: %s\n" % msg["id"])
        self.assertEqual(self.deliveries(NOW + 840, seen), [])
        self.assertEqual(seen["deliveries"], {})  # acked: the book keeps no settled id

    def test_delivery_wake_is_handed_to_the_pool_lead(self):
        self.put("render/runtime/builder-lead.md", "Manage the builder pool; never build.\n")
        wake = dict(reason="delivery", window="ben-7", id="20331118T031000Z-abc123", delivery="submitted",
                    worker="dead", disposition="pending", action="restart", event="ben-7 x: worker dead, restart")
        args = argparse.Namespace(project=self.project, org_profile=None, timeout=1)
        with mock.patch.dict(os.environ, self.env):
            route, lead = self.mod.commands()["route"], self.mod.commands()["lead"]
            values, _, state = self.mod.profile(args)
            with mock.patch.object(lead, "event", return_value=0) as event:
                self.assertTrue(route.route_record(args, values, state, dict(wake)))
        event.assert_called_once_with(args, "builder", wake)


if __name__ == "__main__":
    unittest.main()
