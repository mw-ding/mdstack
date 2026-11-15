#!/usr/bin/env python3
"""Tests for connectors/github/status.py, the bundled status connector (docs/specs/shared-status.md §5 Outcomes and
§7, #1313), run as the map runs it: one JSON request on stdin, against a fake status API behind a fake `gh`.

read-records: every page (page size 2), a failed later page reports complete false with the pages read, a missing,
closed or unreadable issue, an unreadable account; it never writes. publish-record: the create and update controls
report applied with the comment id; each fault reports exactly one outcome: rejected (HTTP 4xx, not applied),
not-sent (no account or another account: no request), uncertain (5xx, lost response, timeout, delayed application,
an unreadable success); a malformed request exits 2 with no request. No DELETE and no write to the issue body or
another comment ever appears in the API audit. Run in CI.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TESTS)
from status_testlib import DEST, ROOT_DIR, StatusBase  # noqa: E402

CONNECTOR = os.path.join(ROOT_DIR, "connectors", "github", "status.py")
spec = importlib.util.spec_from_file_location("github_status", CONNECTOR)
connector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connector)


class Connector(StatusBase):
    def op(self, name, req):
        r = subprocess.run([sys.executable, CONNECTOR, name], input=json.dumps(req), capture_output=True, text=True,
                           env=self.env)
        return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else r.stderr)

    def seed(self, n):
        self.api["issues"]["acme/status/5"]["comments"] = [
            {"id": 100 + i, "user": "acme-bot" if i % 2 else "other", "body": "c%d" % i} for i in range(n)]
        self.save_api()

    def publish(self, op="update", body="new", comment_id="101", publisher="acme-bot"):
        return self.op("publish-record", {"destination": DEST, "publisher": publisher, "op": op,
                                          "comment_id": comment_id, "body": body})

    def test_read_records_rows(self):
        self.seed(5)
        code, out = self.op("read-records", {"destination": DEST})  # control: every page, page size 2
        self.assertEqual((code, out["login"], out["issue"], out["complete"]), (0, "acme-bot", "open", True))
        self.assertEqual([c["id"] for c in out["comments"]], [str(100 + i) for i in range(5)])
        self.assertEqual(out["comments"][1], {"id": "101", "author": "acme-bot", "body": "c1",
                                              "url": "https://github.com/acme/status/issues/5#issuecomment-101"})
        for fail, issue, complete, ids in ((["page:2"], "open", False, ["100", "101"]),
                                           (["page:3"], "open", False, ["100", "101", "102", "103"]),
                                           (["issue"], "unknown", False, [])):
            self.api["fail"] = fail
            self.save_api()
            code, out = self.op("read-records", {"destination": DEST})
            self.assertEqual((code, out["issue"], out["complete"], [c["id"] for c in out["comments"]]),
                             (0, issue, complete, ids), fail)
        self.api["fail"] = ["user"]
        self.save_api()
        code, out = self.op("read-records", {"destination": DEST})
        self.assertEqual((out["login"], out["complete"], len(out["comments"])), (None, True, 5))
        self.api["fail"], self.api["issues"]["acme/status/5"]["state"] = [], "closed"
        self.save_api()
        self.assertEqual(self.op("read-records", {"destination": DEST})[1]["issue"], "closed")
        code, out = self.op("read-records", {"destination": "https://github.com/acme/status/issues/6"})
        self.assertEqual((out["issue"], out["complete"]), ("missing", False))
        self.assertEqual(self.op("read-records", {"destination": "https://github.com/acme/status/pull/5"})[0], 2)
        self.assertEqual(self.audit(), [])

    def test_publish_record_outcomes(self):
        self.seed(2)
        code, out = self.publish("create", "first", None)  # control: create
        self.assertEqual((code, out), (0, {"outcome": "applied", "comment_id": "1001", "error": None}))
        code, out = self.publish("update", "second", "1001")  # control: update of the instance's own slot
        self.assertEqual(out["outcome"], "applied")
        self.assertEqual(self.comments()[-1]["body"], "second")
        rows = [  # (fault or login change, op, expected outcome, applied afterwards)
            ("rejected", "update", "rejected", False), ("5xx", "update", "uncertain", False),
            ("lost", "update", "uncertain", True), ("never", "update", "uncertain", False),
            ("delay:1", "update", "uncertain", False), ("rejected", "create", "rejected", False),
            ("5xx", "create", "uncertain", False), ("lost", "create", "uncertain", True)]
        for n, (fault, op, outcome, applied) in enumerate(rows):
            with self.subTest(fault=fault, op=op):
                api = self.load_api()
                api["faults"] = {"PATCH" if op == "update" else "POST": [fault]}
                self.api = api
                self.save_api()
                before = len(self.comments())
                body = "row-%d" % n
                code, out = self.publish(op, body, "1001" if op == "update" else None)
                self.assertEqual((code, out["outcome"]), (0, outcome), out)
                bodies = [c["body"] for c in self.comments()]
                self.assertEqual(body in bodies, applied, bodies)
                self.assertEqual(len(bodies), before + (op == "create" and applied))
        api = self.load_api()
        api["login"] = None
        self.api = api
        self.save_api()
        audit = len(self.audit())
        self.assertEqual(self.publish(body="x")[1]["outcome"], "not-sent")
        self.api["login"] = "someone-else"
        self.save_api()
        code, out = self.publish(body="x")
        self.assertEqual((out["outcome"], out["error"]), ("not-sent", "authenticated as someone-else, not the publisher acme-bot"))
        self.assertEqual(len(self.audit()), audit)  # not-sent: no request left
        self.api["login"] = "acme-bot"
        self.save_api()
        self.assertEqual(self.publish(body="x", comment_id="999")[1]["outcome"], "rejected")  # a comment it cannot edit
        for bad in ({"op": "update", "comment_id": None}, {"op": "delete"}, {"publisher": ""}, {"body": 7}):
            req = dict({"destination": DEST, "publisher": "acme-bot", "op": "update", "comment_id": "101", "body": "x"}, **bad)
            self.assertEqual(self.op("publish-record", req)[0], 2, bad)
        self.assertEqual(len(self.audit()), audit + 1)
        methods = {(a["method"], a["path"]) for a in self.audit()}
        self.assertEqual({m for m, _ in methods}, {"POST", "PATCH"})
        self.assertTrue(all(p == "repos/acme/status/issues/5/comments" or p.startswith("repos/acme/status/issues/comments/")
                            for _, p in methods), methods)
        self.assertEqual(self.comments()[0], {"id": 100, "user": "other", "body": "c0"})  # another comment untouched

    def test_publish_record_timeout_and_unstartable_gh(self):
        req = {"destination": DEST, "publisher": "acme-bot", "op": "update", "comment_id": "101", "body": "x"}
        with mock.patch.object(connector, "login", return_value="acme-bot"):
            with mock.patch.object(connector, "gh", side_effect=subprocess.TimeoutExpired("gh", 60)):
                self.assertEqual(connector.publish_record(req)["outcome"], "uncertain")
            with mock.patch.object(connector, "gh", side_effect=FileNotFoundError(2, "No such file")):
                self.assertEqual(connector.publish_record(req)["outcome"], "not-sent")
            with mock.patch.object(connector, "gh", return_value=(0, "not json", "")):
                self.assertEqual(connector.publish_record(req)["outcome"], "uncertain")
            with mock.patch.object(connector, "gh", return_value=(0, '{"id": 102}', "")):
                self.assertEqual(connector.publish_record(req)["outcome"], "uncertain")  # names another comment
            with mock.patch.object(connector, "gh", return_value=(0, '{"id": 101}', "")):
                self.assertEqual(connector.publish_record(req)["outcome"], "applied")  # control


if __name__ == "__main__":
    unittest.main()
