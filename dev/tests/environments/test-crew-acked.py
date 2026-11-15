"""Tests for mdstack acked (and send --wait-ack), moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: the ack is read from the status file only, and `send --wait-ack` sees a late ack. `acked --delivery` (#1850,
D2.1): only the target's own ack written after the message was recorded is acked; inbox, submitted composer, transcript
echo, busy worker, another id, an earlier run's ack, another project's message or an unknown id never are, and a refused
read writes nothing. Run in CI.
"""
import json
import os
import subprocess
import sys
import textwrap
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import DeliveryBase, SendBase


class Acked(SendBase):
    def test_ack_only_from_status_file(self):
        r = self.crew("send", "ben-7", "fix", "#1", "--wait-ack", "0.3", "--project", self.project)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        msg_id = self.inbox()[0]["id"]
        self.assertIn("no ack: " + msg_id, r.stdout)
        acked = ["acked", "ben-7", msg_id, "--project", self.project]
        self.assertEqual(self.crew(*acked).returncode, 3)
        self.put("status/ben-7.status", "ack: other-id #1\ndone: #1 inbox: %s\n" % msg_id)
        self.assertEqual(self.crew(*acked).returncode, 3)
        self.put("status/ben-7.status", "done: #1\nack: %s #1\n" % msg_id)
        r = self.crew(*acked)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("acked " + msg_id, r.stdout)

    def test_wait_ack_sees_late_ack(self):
        status = os.path.join(self.state, "status", "ben-7.status")
        os.makedirs(os.path.dirname(status), exist_ok=True)
        # A stand-in role: acks whatever id lands in the inbox, a moment after the send.
        role = subprocess.Popen([sys.executable, "-c", textwrap.dedent("""\
            import json, os, sys, time
            inbox, status = sys.argv[1:]
            while not os.path.exists(inbox):
                time.sleep(0.05)
            time.sleep(0.3)
            open(status, "a").write("ack: %s\\n" % json.loads(open(inbox).readline())["id"])
            """), os.path.join(self.state, "inbox", "ben-7.jsonl"), status])
        self.addCleanup(role.wait)
        r = self.crew("send", "ben-7", "review", "#9", "--wait-ack", "10", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("acked " + self.inbox()[0]["id"], r.stdout)


class TruthfulReceipt(DeliveryBase):  # #1850 D2.1
    def test_only_the_actual_matching_ack_discharges(self):
        self.show(self.BUSY)
        self.assertEqual(self.send("fix", "#12", "a" * 40).returncode, 0)
        msg_id = self.inbox()[0]["id"]
        status = os.path.join(self.state, "status", "ben-7.status")
        for name, screen, lines in [
                ("inbox and busy", self.BUSY, ""),
                ("submitted composer", "› inbox: %s\n" % msg_id, ""),
                ("transcript echo", "› inbox: %s\n\n• Reading the inbox.\n\n› Ask Codex to do anything\n" % msg_id,
                 "heartbeat: x\n"),
                ("another id", self.IDLE, "ack: 20331118T031000Z-abc123\n"),
                ("done names it", self.IDLE, "done: #7 inbox: %s\n" % msg_id)]:
            with self.subTest(name):
                self.show(screen)
                with open(status, "w") as f:
                    f.write(lines)
                r, d = self.delivery(msg_id)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertEqual([d["ack"], d["delivery"]], [False, "submitted"])
                self.assertNotEqual(d["disposition"], "dispatched")
        with open(status, "a") as f:
            f.write("ack: %s\n" % msg_id)
        r, d = self.delivery(msg_id)  # the valid counterpart
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([d["ack"], d["delivery"], d["disposition"], d["action"]], [True, "acked", "dispatched", "none"])
        self.assertEqual([d["id"], d["window"], d["kind"], d["refs"], d["context"]["change"]],
                         [msg_id, "ben-7", "fix", ["#12", "a" * 40], 12])

    def test_an_earlier_runs_ack_never_settles_a_later_record(self):
        self.assertEqual(self.send("fix", "#12", "a" * 40).returncode, 0)
        msg = self.inbox()[0]
        ledger = os.path.join(self.state, "runs", "ben-7.delivery.jsonl")
        with open(ledger) as f:
            events = [json.loads(line) for line in f]
        old = "ack: %s\n" % msg["id"]  # written before this message was recorded (an earlier run's file)
        self.put("status/ben-7.status", old)
        events[0]["status"] = len(old)
        self.put("runs/ben-7.delivery.jsonl", "".join(json.dumps(e) + "\n" for e in events))
        self.assertEqual(self.crew("acked", "ben-7", msg["id"], "--project", self.project).returncode, 0)  # legacy
        r, d = self.delivery(msg["id"])
        self.assertEqual([r.returncode, d["ack"]], [3, False], r.stdout)
        with open(os.path.join(self.state, "status", "ben-7.status"), "a") as f:
            f.write(old)
        self.assertEqual(self.delivery(msg["id"])[0].returncode, 0)

    def test_foreign_or_unknown_message_refused_with_nothing_written(self):
        self.assertEqual(self.send("fix", "#12", "a" * 40).returncode, 0)
        msg = self.inbox()[0]
        foreign = dict(msg, id="20331118T031000Z-f0e1d2", context=dict(msg["context"], repo="other/repo"))
        bare = dict(msg, id="20331118T031000Z-a0b1c2")
        bare.pop("context")
        with open(os.path.join(self.state, "inbox", "ben-7.jsonl"), "a") as f:
            f.write(json.dumps(foreign) + "\n" + json.dumps(bare) + "\n")
        for msg_id in (foreign["id"], bare["id"], "20331118T031000Z-ffffff"):
            with self.subTest(msg_id):
                before = self.tree()
                r, _ = self.delivery(msg_id)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("refusing delivery read: no message %s for this project" % msg_id, r.stdout)
                self.assertEqual(self.tree(), before)
        before = self.tree()
        self.assertEqual(self.delivery(msg["id"])[0].returncode, 3)  # the valid counterpart, also read only
        self.assertEqual(self.tree(), before)


if __name__ == "__main__":
    unittest.main()
