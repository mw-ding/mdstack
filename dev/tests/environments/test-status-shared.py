#!/usr/bin/env python3
"""Tests for shared status through the shipped CLI (`mdstack status register|publish|--all`, the watcher's timer;
environments/terminal/crew.d/_status_shared.py, docs/specs/shared-status.md §4-§6 and §9, #1313; ACs S.2-S.6).

Every row runs `cli/mdstack` against a fake status API (dev/tests/status_testlib.py) and asserts exit, stderr
substrings, the API audit of POST/PATCH/DELETE and a state-dir snapshot (path and SHA-256 of every file); every
refusal row writes nothing and names its valid control. S.2: off, unset keys, invalid config, worker and pool-lead
callers, refused ownership, a present or unreadable pause barrier, the wrong account, a foreign registration.
S.3: N = 0/1/2/3 instances with equal repo and runtime labels, a reused instance ID, a copied receipt, wrong issue,
comment or author, duplicates on a later page, concurrent distinct publishers. S.4: same content, not-sent,
rejected, lost response, delayed and never-applied timeouts, re-registration with a late landing, interrupted runs,
corrupt pending, higher or conflicting slot sequences, an applied write with another readback. S.5: the stale
threshold -1/0/+1, an old observation republished, future, unknown, malformed and duplicate records, closed or
missing destination, API and page failures, unconfigured. S.6: the timer (off, due, duplicate tick, ownership
lost), a collector failure, plain `status` unchanged, register -> publish -> publish -> --all -> disable. Run in CI.
"""
import copy
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TESTS)
from status_testlib import CLOCK, CREW, DEST, StatusBase  # noqa: E402

spec = importlib.util.spec_from_file_location("status_record", os.path.join(os.path.dirname(os.path.dirname(TESTS)),
                                                                            "core", "status-record.py"))
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

MARKER_CLAIM = ("<!-- crew:v1 role=coordinator pass=handoff handoff=20330101-abcdef state=claimed from=none to=%s "
                "cmd-id=c1 sha=" + "a" * 40 + " round=n/a verdict=n/a -->")


class Shared(StatusBase):
    def refused(self, r, want):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(want, r.stderr)

    def ok(self, r, out=None):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        if out is not None:
            self.assertEqual(r.stdout.strip(), out)
        return r

    def frozen(self, project=None):
        return self.audit(), self.snapshot(project)

    def assert_zero(self, before, project=None):
        self.assertEqual(self.frozen(project), before)

    def slot(self, instance="alpha"):
        return next(c for c in self.comments() if sr.parse_slot(c["body"])[0] and
                    sr.parse_slot(c["body"])[0].get("instance_id") == instance)

    def set_api(self, **changes):
        self.load_api()
        self.api.update(changes)
        self.save_api()

    def edit_slot(self, fn, instance="alpha"):
        self.load_api()
        for c in self.api["issues"]["acme/status/5"]["comments"]:
            rec = sr.parse_slot(c["body"])[0]
            if rec and rec.get("instance_id") == instance:
                fn(c, rec)
        self.save_api()

    def rewrite(self, project, old, new):
        with open(project) as f:
            text = f.read()
        self.assertIn(old, text)
        with open(project, "w") as f:
            f.write(text.replace(old, new))

    def write_receipt(self, receipt, project=None):
        with open(self.receipt_file(project), "w") as f:
            json.dump(receipt, f)

    def next_body(self, receipt, edit=None):
        """The exact body of the record after the receipt's confirmed one, as a publisher would prepare it."""
        rec = copy.deepcopy(sr.parse_slot(self.slot()["body"])[0])
        rec.update(sequence=receipt["sequence"] + 1, published_at=sr.stamp(CLOCK))
        if edit:
            edit(rec)
        return {"op": "update", "state": "prepared", "sequence": rec["sequence"],
                "content_sha256": sr.content_sha256(rec), "body": sr.slot_body(rec)}


class Authority(Shared):
    """S.2: off or unauthorized means zero writes; each row against the authorized publish control."""

    def test_refusal_rows_against_the_authorized_publish(self):
        self.ok(self.crew("status", "register"), "registered alpha")
        status = "decision_log = \"https://github.com/acme/widgets/issues/985\"\n"
        rows = [  # (profile edit (old, new) or None, env, api changes, files, expected stderr)
            (("enabled = true", "enabled = false"), {}, {}, {}, "status publish: off: [status] enabled is false"),
            (('destination = "%s"\n' % DEST, ""), {}, {}, {}, "status.destination: missing; enabled = true needs"),
            (('instance_id = "alpha"\n', ""), {}, {}, {}, "status.instance_id: missing; enabled = true needs"),
            ((status, ""), {}, {}, {}, "status.decision_log: missing; enabled = true needs"),
            (("enabled = true", "enabled = true\npublish_interval = 10"), {}, {}, {},
             "status.publish_interval: must be 60-3600 seconds, got 10"),
            (None, {"CREW_ROLE": "builder"}, {}, {}, "caller: CREW_ROLE=builder; only the watcher or an owner shell"),
            (None, {"CREW_ROLE": "builder-lead"}, {}, {}, "caller: CREW_ROLE=builder-lead"),
            (None, {}, {}, {"pause.json": '{"at": "2033-05-18T00:00:00Z"}'}, "paused: pause barrier since 2033-05-18"),
            (None, {}, {}, {"pause.json": "{not json"}, "paused: pause state unreadable"),
            (None, {}, {"login": "someone-else"}, {}, "publisher: authenticated account someone-else is not "
                                                      "identities.coordinator.gh_user acme-bot"),
            (None, {}, {"login": None}, {}, "publisher: authenticated account unreadable"),
        ]
        with open(self.project) as f:
            original = f.read()
        for edit, env, api, files, want in rows:
            with self.subTest(want=want):
                if edit:
                    self.rewrite(self.project, *edit)
                saved = copy.deepcopy(self.load_api())
                self.set_api(**api)
                for rel, text in files.items():
                    with open(os.path.join(self.state_root(), "acme__widgets", rel), "w") as f:
                        f.write(text)
                before = self.frozen()
                self.refused(self.crew("status", "publish", **env), want)
                self.assert_zero(before)
                for rel in files:
                    os.remove(os.path.join(self.state_root(), "acme__widgets", rel))
                self.api = saved
                self.save_api()
                with open(self.project, "w") as f:
                    f.write(original)
        before = len(self.audit())  # control: the authorized publish, also as the coordinator's own role
        self.ok(self.crew("status", "publish", CREW_ROLE="coordinator"), "published sequence 2")
        self.assertEqual([a["method"] for a in self.audit()[before:]], ["PATCH"])
        self.assertEqual(self.receipt()["sequence"], 2)

    def test_register_needs_every_key_but_enabled(self):
        self.rewrite(self.project, "enabled = true", "enabled = false")
        for key in ('instance_id = "alpha"\n', 'destination = "%s"\n' % DEST):
            self.rewrite(self.project, key, "")
            before = self.frozen()
            self.refused(self.crew("status", "register"), "unconfigured: [status] %s unset" % key.split(" ")[0])
            self.assert_zero(before)
            self.rewrite(self.project, "enabled = false", "enabled = false\n" + key.strip())
        self.ok(self.crew("status", "register"), "registered alpha")  # control: off still registers
        self.assertEqual([a["method"] for a in self.audit()], ["POST"])

    def test_ownership_refused_and_foreign_registration(self):
        self.rewrite(self.project, 'name = "widgets"', 'name = "widgets"\ncontrol_item = 9')
        self.rewrite(self.project, 'name = "tmux"', 'name = "tmux"\ninstance = "box"')
        self.api["issues"]["acme/widgets/9"] = {"state": "open", "comments": [
            {"id": 1, "user": "acme-owner", "body": MARKER_CLAIM % "tmux@box"}]}
        self.save_api()
        self.ok(self.crew("status", "register"), "registered alpha")  # control: this runtime owns
        for owner in ("session@other",):
            self.load_api()["issues"]["acme/widgets/9"]["comments"][0]["body"] = MARKER_CLAIM % owner
            self.save_api()
            before = self.frozen()
            self.refused(self.crew("status", "publish"), "ownership: read-only; refusing write")
            self.assert_zero(before)
        self.load_api()["issues"]["acme/widgets/9"]["comments"][0]["body"] = MARKER_CLAIM % "tmux@box"
        self.save_api()
        self.edit_slot(lambda c, rec: c.update(body=sr.slot_body(dict(rec, registration_id="r-" + "f" * 32))))
        before = self.frozen()
        self.refused(self.crew("status", "publish"), "is not this publisher's slot for alpha/")
        self.assert_zero(before)


class Isolation(Shared):
    """S.3: the configured issue, publisher and binding; one publisher per instance; other comments untouched."""

    def test_n_instances_equal_labels_and_concurrent_publishers(self):
        r = self.ok(self.crew("status", "--all"))  # N = 0
        self.assertEqual(r.stdout.splitlines(), ["INSTANCE  REPOS  RUNTIME  AGE  STATE  BLOCKED  UNKNOWN  PRS  ASKS  QUEUE"])
        projects = {"alpha": self.project, "beta": self.install("beta"), "gamma": self.install("gamma")}
        for n, name in enumerate(["alpha", "beta", "gamma"], 1):
            self.ok(self.crew("status", "register", project=projects[name]), "registered %s" % name)
            rows = self.ok(self.crew("status", "--all")).stdout.splitlines()[1:]
            self.assertEqual([row.split()[:5] for row in rows],
                             [[i, "acme/widgets", "tmux", "0s", "fresh"] for i in ["alpha", "beta", "gamma"][:n]])
        slots = {name: self.slot(name)["id"] for name in projects}
        self.assertEqual(len(set(slots.values())), 3)
        before = len(self.audit())
        procs = [subprocess.Popen([sys.executable, CREW, "status", "publish", "--project", projects[n]], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in ("alpha", "beta")]
        for p in procs:
            out, err = p.communicate()
            self.assertEqual((p.returncode, out.strip()), (0, "published sequence 2"), err)
        writes = self.audit()[before:]
        self.assertEqual(sorted(a["path"] for a in writes), sorted(
            "repos/acme/status/issues/comments/%d" % slots[n] for n in ("alpha", "beta")))
        for name, seq in (("alpha", 2), ("beta", 2), ("gamma", 1)):
            self.assertEqual(sr.parse_slot(self.slot(name)["body"])[0]["sequence"], seq)
        self.assertEqual(self.comments()[0], {"id": 11, "user": "acme-owner", "body": "Shared status board."})
        self.assertFalse([a for a in self.audit() if a["method"] == "DELETE" or a["path"].endswith("issues/5")])

    def test_identity_and_binding_refusals(self):
        self.ok(self.crew("status", "register"), "registered alpha")
        reused = self.install("alpha-copy", extra="")
        self.rewrite(reused, 'instance_id = "alpha-copy"', 'instance_id = "alpha"')
        before = self.frozen(reused)
        self.refused(self.crew("status", "register", project=reused), "already holds instance_id alpha")
        self.assert_zero(before, reused)
        os.makedirs(os.path.dirname(self.receipt_file(reused)))  # a copied receipt: another state dir and config
        shutil.copy(self.receipt_file(), self.receipt_file(reused))
        for action in ("publish", "register"):
            before = self.frozen(reused)
            self.refused(self.crew("status", action, project=reused), "copied receipt:")
            self.assert_zero(before, reused)
        self.api = self.load_api()
        self.api["issues"]["acme/status/6"] = {"state": "open", "comments": []}
        self.save_api()
        self.rewrite(self.project, "status/issues/5", "status/issues/6")  # wrong issue for the receipt
        before = self.frozen()
        self.refused(self.crew("status", "publish"), "unregistered: no receipt for alpha on "
                                                     "https://github.com/acme/status/issues/6")
        self.assert_zero(before)
        self.rewrite(self.project, "status/issues/6", "status/issues/5")
        receipt = self.receipt()
        self.write_receipt(dict(receipt, comment_id="11"))  # the owner's comment
        before = self.frozen()
        self.refused(self.crew("status", "publish"), "is not this publisher's slot")
        self.assert_zero(before)
        self.write_receipt(receipt)
        self.edit_slot(lambda c, rec: c.update(user="mallory"))  # wrong author
        before = self.frozen()
        self.refused(self.crew("status", "publish"), "is not this publisher's slot")
        self.assert_zero(before)
        self.edit_slot(lambda c, rec: c.update(user="acme-bot"))
        self.ok(self.crew("status", "publish"), "published sequence 2")  # control

    def test_duplicates_on_a_later_page(self):
        self.ok(self.crew("status", "register"), "registered alpha")
        copy_body = sr.slot_body(dict(sr.parse_slot(self.slot()["body"])[0], sequence=9))
        self.load_api()
        comments = self.api["issues"]["acme/status/5"]["comments"]
        comments += [{"id": 20 + i, "user": "acme-owner", "body": "note %d" % i} for i in range(3)]
        comments.append({"id": 30, "user": "acme-bot", "body": copy_body})  # page 3 of 2-comment pages
        self.save_api()
        before = self.frozen()
        self.refused(self.crew("status", "publish"), "#issuecomment-30 also holds alpha or its registration")
        self.assert_zero(before)
        delta = self.install("delta")
        self.load_api()
        dup = sr.slot_body(dict(sr.parse_slot(copy_body)[0], instance_id="omega", registration_id="r-" + "d" * 32))
        comments = self.api["issues"]["acme/status/5"]["comments"]
        comments[-1]["body"] = dup
        comments.append({"id": 31, "user": "acme-bot", "body": dup})
        self.save_api()
        before = self.frozen(delta)
        self.refused(self.crew("status", "register", project=delta), "hold the same instance_id omega")
        self.assert_zero(before, delta)
        self.load_api()["issues"]["acme/status/5"]["comments"].pop()
        self.save_api()
        self.ok(self.crew("status", "register", project=delta), "registered delta")  # control


class Recovery(Shared):
    """S.4: no blind resend; uncertain writes reconcile only by readback; restarts keep the receipt byte for byte."""

    def setUp(self):
        super().setUp()
        self.ok(self.crew("status", "register"), "registered alpha")

    def fault(self, method, *faults):
        self.load_api()
        self.api["faults"] = {method: list(faults)}
        self.save_api()

    def test_same_content_not_sent_and_rejected(self):
        self.set_api(user_calls_ok=1)  # the read phase reads the account, then the send's own check fails
        r = self.crew("status", "publish")
        self.refused(r, "not-sent: sequence 2 was not applied")
        self.assertEqual((self.receipt()["pending"], self.receipt()["sequence"]), (None, 1))
        self.set_api(user_calls_ok=None)
        self.fault("PATCH", "rejected")
        before = len(self.audit())
        self.refused(self.crew("status", "publish"), "rejected: sequence 2 was not applied (HTTP 422); no retry")
        self.assertEqual(len(self.audit()), before + 1)  # one request, no retry in that run
        self.assertEqual(self.receipt()["pending"], None)
        self.ok(self.crew("status", "publish"), "published sequence 2")  # control: the next run publishes
        self.fault("PATCH", "lost")
        self.refused(self.crew("status", "publish"), "uncertain: pending sequence 3")
        self.assertEqual(self.receipt()["pending"]["state"], "uncertain")
        before = self.frozen()[0]
        self.ok(self.crew("status", "publish"), "confirmed sequence 3")  # same content shown: confirm, no write
        self.assertEqual(self.audit(), before)
        self.assertEqual((self.receipt()["sequence"], self.receipt()["pending"]), (3, None))

    def test_delayed_and_never_applied_timeouts(self):
        self.fault("PATCH", "delay:3")
        self.refused(self.crew("status", "publish"), "uncertain: pending sequence 2")
        pending = self.receipt()["pending"]
        before = self.frozen()
        self.refused(self.crew("status", "publish", "--check"), "uncertain: pending sequence 2 may still apply")
        self.assertEqual(self.frozen()[0], before[0])
        self.refused(self.crew("status", "publish"), "uncertain: pending sequence 2 may still apply")
        self.assertEqual(self.audit(), before[0])  # no resend, no newer record
        self.assertEqual(self.receipt()["pending"], pending)
        self.ok(self.crew("status", "publish"), "confirmed sequence 2")  # the delayed write landed: readback confirms
        self.assertEqual(self.audit(), before[0])
        self.fault("PATCH", "never")
        self.refused(self.crew("status", "publish"), "uncertain: pending sequence 3")
        audit = self.audit()
        for _ in range(2):
            self.refused(self.crew("status", "publish"), "uncertain: pending sequence 3 may still apply")
        self.ok(self.crew("status", "register"), "registered alpha")  # never creates again for this instance
        self.assertEqual(self.audit(), audit)

    def test_uncertain_create_is_never_created_again(self):
        beta = self.install("beta")
        self.fault("POST", "never")
        self.refused(self.crew("status", "register", project=beta), "uncertain: pending sequence 1")
        for action, want in (("register", "uncertain: create of r-"), ("publish", "unregistered: registration not "
                                                                                    "confirmed")):
            before = self.frozen(beta)
            self.refused(self.crew("status", action, project=beta), want)
            self.assert_zero(before, beta)
        self.assertEqual([a["method"] for a in self.audit()].count("POST"), 2)  # alpha's and beta's one create
        gamma = self.install("gamma")
        self.fault("POST", "lost")
        self.refused(self.crew("status", "register", project=gamma), "uncertain: pending sequence 1")
        before = self.audit()
        self.ok(self.crew("status", "register", project=gamma), "registered gamma")  # adopted by readback
        self.assertEqual(self.audit(), before)

    def test_reregistration_then_the_old_send_lands_late(self):
        old_slot = self.slot()["id"]
        self.fault("PATCH", "delay:3")
        self.refused(self.crew("status", "publish"), "uncertain: pending sequence 2")
        rid = self.receipt()["registration_id"]
        self.rewrite(self.project, 'instance_id = "alpha"', 'instance_id = "alpha-2"')
        self.ok(self.crew("status", "register"), "registered alpha-2")
        archived = self.receipt(name="receipt-%s.json" % rid)
        self.assertEqual((archived["instance_id"], archived["pending"]["sequence"]), ("alpha", 2))
        new_slot = self.slot("alpha-2")
        self.ok(self.crew("status", "publish"), "published sequence 2")
        self.ok(self.crew("status", "--all"))
        landed = sr.parse_slot(next(c for c in self.comments() if c["id"] == old_slot)["body"])[0]
        self.assertEqual((landed["instance_id"], landed["sequence"]), ("alpha", 2))  # the late write: old slot only
        now = sr.parse_slot(self.slot("alpha-2")["body"])[0]
        self.assertEqual((now["sequence"], self.slot("alpha-2")["id"]), (2, new_slot["id"]))

    def test_interrupted_runs_keep_the_original_pending_bytes(self):
        receipt = self.receipt()
        pending = self.next_body(receipt)
        self.write_receipt(dict(receipt, pending=pending))  # stopped after `prepared`, before the send
        self.set_api(repos={"acme/widgets": {"prs": [{"number": 8, "labels": []}]}})  # fresh collector data differs
        before = self.frozen()
        self.refused(self.crew("status", "publish"), "uncertain: pending sequence 2 may still apply")
        self.assert_zero(before)
        self.edit_slot(lambda c, rec: c.update(body=pending["body"]))  # stopped after the send, before the outcome
        before = self.audit()
        self.ok(self.crew("status", "publish"), "confirmed sequence 2")
        self.assertEqual((self.audit(), self.receipt()["content_sha256"]), (before, pending["content_sha256"]))
        self.assertEqual(sr.parse_slot(self.slot()["body"])[0]["sections"]["prs"]["items"], [])  # old observation

    def test_corrupt_pending_and_conflicting_slots(self):
        receipt = self.receipt()
        for name, bad in (("sha", dict(self.next_body(receipt), content_sha256="0" * 64)),
                          ("sequence", self.next_body(receipt, lambda rec: rec.update(sequence=5))),
                          ("instance", self.next_body(receipt, lambda rec: rec.update(instance_id="beta"))),
                          ("body", dict(self.next_body(receipt), body="not a slot"))):
            with self.subTest(name):
                self.write_receipt(dict(receipt, pending=bad))
                for action in ("publish", "register"):
                    before = self.frozen()
                    self.refused(self.crew("status", action), "receipt-invalid:")
                    self.assert_zero(before)
        self.write_receipt(receipt)
        for name, edit in (("higher", lambda rec: rec.update(sequence=6)),
                           ("same, other content", lambda rec: rec.update(published_at=sr.stamp(CLOCK - 1)))):
            with self.subTest(name):
                saved = self.slot()["body"]
                self.edit_slot(lambda c, rec: (edit(rec), c.update(body=sr.slot_body(rec))))
                before = self.frozen()
                self.refused(self.crew("status", "publish"), "conflict:")
                self.assert_zero(before)
                self.edit_slot(lambda c, rec: c.update(body=saved))
        self.fault("PATCH", "mangle")
        self.refused(self.crew("status", "publish"), "conflict: applied, but comment")
        self.refused(self.crew("status", "publish"), "conflict:")  # publication stays stopped
        self.assertEqual([a["method"] for a in self.audit()], ["POST", "PATCH"])


class View(Shared):
    """S.5: `status --all` is read-only, needs no session, and never shows invalid or conflicting rows fresh."""

    def setUp(self):
        super().setUp()
        self.ok(self.crew("status", "register"), "registered alpha")

    def rows(self, r):
        return {ln.split()[0]: ln.split() for ln in r.stdout.splitlines()[1:] if not ln.startswith(("diagnostic:", "partial:"))}

    def test_threshold_and_freshness_rows(self):
        before = self.frozen()
        for offset, state in ((899, "fresh"), (900, "stale"), (901, "stale")):
            r = self.ok(self.crew("status", "--all", clock=CLOCK + offset))
            self.assertEqual(self.rows(r)["alpha"][3:5], ["14m" if offset < 900 else "15m", state], offset)
        rec = sr.parse_slot(self.slot()["body"])[0]
        old = dict(rec, instance_id="old", registration_id="r-" + "1" * 32, published_at=sr.stamp(CLOCK + 2000))
        future = dict(rec, instance_id="future", registration_id="r-" + "2" * 32,
                      observed_at=sr.stamp(CLOCK + 3000), published_at=sr.stamp(CLOCK + 3000),
                      sections={k: dict(v, observed_at=sr.stamp(CLOCK + 3000)) for k, v in rec["sections"].items()})
        unknown = dict(rec, instance_id="unknown", registration_id="r-" + "3" * 32,
                       sections={k: {"state": "unknown", "observed_at": rec["observed_at"], "reason": "unsupported"}
                                 for k in rec["sections"]})
        dup = dict(rec, instance_id="twin", registration_id="r-" + "4" * 32)
        self.load_api()
        comments = self.api["issues"]["acme/status/5"]["comments"]
        for n, body in enumerate([sr.slot_body(old), sr.slot_body(future), sr.slot_body(unknown), sr.slot_body(dup),
                                  sr.slot_body(dict(dup, registration_id="r-" + "5" * 32)),
                                  sr.MARKER + "\n```json\n{broken\n```",
                                  sr.slot_body(dict(rec, instance_id="v2", registration_id="r-" + "6" * 32,
                                                    schema_version=2))]):
            comments.append({"id": 50 + n, "user": "acme-bot", "body": body})
        self.save_api()
        r = self.ok(self.crew("status", "--all", clock=CLOCK + 2000))
        rows = self.rows(r)
        self.assertEqual(rows["old"][4], "stale")  # republished at +2000, observed at 0: age from the observation
        self.assertEqual(rows["future"][4:], ["invalid"] + ["-"] * 5)
        self.assertEqual(rows["unknown"][4:7], ["stale", "unknown", ",".join(sr.SECTIONS)])
        self.assertEqual(rows["twin"][4:], ["conflict"] + ["-"] * 5)
        self.assertEqual(rows["v2"][4], "invalid")
        lines = r.stdout.splitlines()
        for cid, want in ((51, "future time"), (55, "record is not JSON"), (56, "unknown version 2"),
                          (53, "conflict: duplicate"), (54, "conflict: duplicate")):
            self.assertTrue(any("#issuecomment-%d " % cid in ln and want in ln for ln in lines), (cid, lines))
        self.assertEqual(self.frozen(), before)  # no writes
        self.assertFalse(os.path.exists(self.tmux_log))  # no session needed

    def test_incomplete_reads_and_unconfigured(self):
        for fail, want in ((["page:2"], "partial: a comment page did not read"),
                           (["issue"], "partial: destination issue unknown")):
            self.set_api(fail=fail)
            r = self.crew("status", "--all")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(want, r.stdout)
        self.set_api(fail=[])
        self.load_api()["issues"]["acme/status/5"]["state"] = "closed"
        self.save_api()
        r = self.crew("status", "--all")
        self.assertEqual((r.returncode, r.stdout.splitlines()[-1]), (1, "partial: destination issue closed (1 status comment read)"))
        self.assertIn("alpha", r.stdout)  # the rows read so far
        del self.load_api()["issues"]["acme/status/5"]
        self.save_api()
        self.assertIn("partial: destination issue missing", self.crew("status", "--all").stdout)
        off = self.install("off", status=False)
        r = self.crew("status", "--all", project=off)
        self.assertEqual((r.returncode, r.stderr.strip()), (3, "status --all: unconfigured"))
        self.api["issues"]["acme/status/5"] = {"state": "open", "comments": []}
        self.save_api()
        self.rewrite(self.project, "enabled = true", "enabled = false")
        self.assertEqual(self.crew("status", "--all").returncode, 0)  # off with a destination still reads
        self.rewrite(self.project, "enabled = false", "enabled = false\nverbose = 1")
        self.assertEqual(self.crew("status", "--all").returncode, 2)
        self.assertEqual(self.crew("status", "register", "--all").returncode, 2)
        self.assertEqual(self.crew("status", "--check").returncode, 2)


class Seam(Shared):
    """S.6: the watcher's timer, collector failure, plain `status`, and the end-to-end lifecycle."""

    def cli(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli_status", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli_status", loader))
        loader.exec_module(mod)
        return mod.commands()["status"].status_shared

    def test_timer_rows(self):
        shared = self.cli()
        values = {"status.enabled": True, "status.publish_interval": 300}
        runs = []
        with mock.patch.object(shared.subprocess, "run", side_effect=lambda argv, **kw: runs.append(argv)), \
                mock.patch.object(shared.ownership_module, "status", return_value="active"):
            seen = {}
            self.assertTrue(shared.tick(values, self.project, None, seen, 1000.0))  # control: due
            self.assertEqual(runs[-1][1:], [CREW, "status", "publish", "--project", self.project])
            self.assertFalse(shared.tick(values, self.project, None, seen, 1299.0))  # duplicate tick in the interval
            self.assertTrue(shared.tick(values, self.project, "org.toml", seen, 1300.0))
            self.assertEqual(runs[-1][-2:], ["--org-profile", "org.toml"])
            self.assertFalse(shared.tick(dict(values, **{"status.enabled": False}), self.project, None, seen, 9000.0))
            self.assertFalse(shared.tick({}, self.project, None, {}, 9000.0))  # no [status] table at all
        with mock.patch.object(shared.subprocess, "run", side_effect=lambda argv, **kw: runs.append(argv)), \
                mock.patch.object(shared.ownership_module, "status", return_value="lost"):
            self.assertFalse(shared.tick(values, self.project, None, {}, 9000.0))
        self.assertEqual(len(runs), 2)

    def test_lifecycle_collector_failure_and_plain_status(self):
        shared = self.cli()
        self.ok(self.crew("status", "register"), "registered alpha")
        values = {"status.enabled": True, "status.publish_interval": 300}
        env = {k: v for k, v in self.env.items()}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(shared.tick(values, self.project, None, {}, 5000.0))  # the real subprocess publishes
        self.assertEqual(self.receipt()["sequence"], 2)
        self.set_api(repos={"acme/widgets": {"prs": [{"number": 8, "labels": [{"name": "crew:approved"}]}]}},
                     fail=["issues"])
        self.ok(self.crew("status", "publish"), "published sequence 3")
        secs = sr.parse_slot(self.slot()["body"])[0]["sections"]
        self.assertEqual({k: v.get("reason") for k, v in secs.items() if v["state"] == "unknown"},
                         {"owner_asks": "read-failed", "blockers": "read-failed", "queue": "read-failed"})
        self.assertEqual(secs["prs"]["items"], [{"url": "https://github.com/acme/widgets/pull/8", "stage": "approved"}])
        rows = self.ok(self.crew("status", "--all")).stdout.splitlines()
        self.assertEqual(rows[1].split()[4:], ["fresh", "unknown", "owner_asks,blockers,queue", "1", "unknown",
                                               "unknown"])
        self.rewrite(self.project, "enabled = true", "enabled = false")
        audit = self.audit()
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(shared.tick({"status.enabled": False}, self.project, None, {}, 9000.0))
        self.refused(self.crew("status", "publish"), "off:")
        self.assertEqual(self.audit(), audit)  # disabled: no later write
        r = subprocess.run([sys.executable, CREW, "status", "--project", self.project], capture_output=True,
                           text=True, env=self.env)
        self.assertEqual((r.returncode, r.stdout.split()), (0, ["WINDOW", "ROLE", "HOST", "ITEM", "HEAD", "BEAT",
                                                                "LIVENESS", "LAST"]))


if __name__ == "__main__":
    unittest.main()
