"""Review readiness (#1878, M57 D1): a fresh review starts only from the head's published, builder-signed record for its
operation, on both reviewer admission paths (route's durable work event and an explicit review handoff, each dispatched
by `mdstack reviewer-pool`). Table-driven D1.1 binding and D1.5 operation matrices, D1.2 publication orders, D1.3
persistence and D1.4 token-free recovery, with fake tmux/GitHub. --transcript prints the lifecycle; test names run
only those. Run in CI.
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("pool_tests", os.path.join(HERE, "test-crew-reviewer-pool.py"))
pool_tests = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(pool_tests)
OLD = "0" * 40
PROOF = "~~~text\n$ make test\nok\n~~~"


def say(line):
    if "--transcript" in sys.argv:
        print(line)


class ReviewReadiness(pool_tests.ReviewerPool):
    def setUp(self):
        super().setUp()
        self.n = 0

    def note(self, kind="fix", round_="1", sha=None, pr="12", login="acme-bot", name="Ben", proof=PROOF):
        self.n += 1
        sha = self.sha if sha is None else sha
        return dict(id="N%d" % self.n, author={"login": login}, body=(
            "[%s/%s] round %s @ %s\n\n%s\n\n<!-- crew:v1 role=builder pass=%s pr=%s sha=%s round=%s verdict=n/a "
            "engine=codex model=gpt-6.1-sol effort=medium -->\n— 🛠️ %s (Builder) · codex · gpt-6.1-sol") % (
                name, kind, round_, sha[:7], proof, kind, pr, sha, round_, name))

    def verdict(self, sha, round_, result):
        return dict(self.signed("<!-- crew:v1 role=reviewer-validator pass=verdict pr=12 sha=%s round=%s verdict=%s -->"
                                % (sha, round_, result)), id="V%s" % round_)

    def reset(self):
        return dict(self.signed("<!-- crew:v1 role=coordinator pass=steer pr=12 sha=%s round=n/a verdict=n/a cmd=resume "
                                "cmd-id=chat -->" % OLD, "acme-bot", "Ash"), id="R1")

    def scene(self, reviews, opened=False, **live):
        """The live PR: these reviews, its head commit dated before (opened) or after the PR was created."""
        self.live.update(dict(reviews=reviews, commits=[{"oid": self.sha, "committedDate": "2026-01-01T00:%s:00Z" % (
            "00" if opened else "20")}]), **live)
        self.save()

    def offer(self, round_=2, paths=("work", "review")):
        """The admission paths for a fresh review of the live head (route's work event, an explicit review handoff),
        dispatched by reviewer-pool."""
        if "work" in paths:
            with mock.patch.dict(os.environ, self.env):
                self.assertEqual(self.lead.event(self.args, "reviewer", dict(event="new-head", refs=["#12", self.sha],
                                                                              round=round_)), 0)
        if "review" in paths:
            self.handoff("review", ["#12", self.sha, str(round_)])
        self.pool()

    def reviewers(self):
        return [n for n in self.names() if n.startswith("vera-12-")]

    def assert_parked(self, why=""):
        """No claim, reservation or spawn; every pending id waits on evidence after its latest ack."""
        self.assertEqual(self.reviewers(), [], why)
        self.assertFalse(os.path.exists(os.path.join(self.state, "schedule", "reservations.json")), why)
        ids = [m["id"] for m in self.messages()]
        self.assertTrue(ids, why)
        self.assertEqual(self.waits()[-len(ids):], ["waiting: #12 evidence id=%s" % i for i in ids], why)

    def fresh(self):
        """A new fixture (state, fake tmux and GitHub) for the next table row."""
        self.doCleanups()
        self.setUp()

    def push(self):
        """The next head on the PR branch."""
        self.git("reset", "-q", "--hard", self.sha)
        self.sha = self.pr(12, "codex gpt-6.1-sol medium")

    def poll_saw(self):
        """mdstack poll's token-free record of the live PR, as the watcher's lead backstop reads it."""
        poll, values = self.mod.commands()["poll"], self.mod.profile(self.args)[0]
        _, state = poll.decide({"prs": {"12": {"head": self.sha}}}, [dict(self.live, labels=[{"name": "crew:in-review"}])],
                               [], values=values)
        state["observed"] = {"12": poll.ready_sample(self.live)}
        self.put("poll-state.json", json.dumps(state))

    def test_binding_varies_each_field_once_then_the_valid_record_dispatches_once(self):  # D1.1
        changes = self.verdict(OLD, 1, "changes")
        cases = [("no record", [changes]), ("foreign PR", [changes, self.note(pr="13")]),
                 ("short SHA", [changes, self.note(sha=self.sha[:7])]), ("other head", [changes, self.note(sha="c" * 40)]),
                 ("copied signature, other login", [changes, self.note(login="acme-other")]),
                 ("builder login, other signature", [changes, self.note(name="Sam")]),
                 ("previous epoch", [self.note(), changes]), ("wrong round", [changes, self.note(round_="2")]),
                 ("truncated round", [changes, self.note(round_="")]), ("wrong kind", [changes, self.note(kind="selfgate")]),
                 ("no inline proof", [changes, self.note(proof="Fixed it.")])]
        for why, reviews in cases:
            with self.subTest(why):
                self.scene(reviews)
                self.offer()
                self.assert_parked(why)
                say("D1.1 %-31s -> parked: evidence wait, no claim/reservation/spawn" % why)
        self.scene([changes, self.note()])
        self.offer()
        self.offer()  # replay
        self.assertEqual((self.reviewers(), self.messages()), (["vera-12-r2-review"], []))
        say("D1.1 %-31s -> one review r2; replay starts none" % "valid fix note")

    def test_unreadable_or_foreign_live_read_admits_nothing(self):  # D1.1
        route = self.mod.commands()["route"]
        self.scene([self.verdict(OLD, 1, "changes"), self.note()])
        real = route.gh

        def unreadable(*args):
            if args[-1] == route.READY_FIELDS:
                raise RuntimeError("crew: gh pr view: HTTP 502")
            return real(*args)
        with mock.patch.object(route, "gh", unreadable):
            self.offer()
        self.assertEqual(self.reviewers(), [])
        self.assertEqual(len(self.messages()), 2)  # retried with backoff, never a typed wait or an admission
        self.assertNotIn("evidence", " ".join(self.waits() if os.path.exists(
            os.path.join(self.state, "status", "vera-lead.status")) else []))
        self.live["url"] = "https://github.com/acme/gadgets/pull/12"  # same ids and SHA, repo B
        self.save()
        self.pool()
        self.assertEqual(self.reviewers(), [])
        self.live["url"] = "https://github.com/acme/widgets/pull/12"
        self.save()
        self.pool()
        self.assertEqual((self.reviewers(), self.messages()), (["vera-12-r2-review"], []))
        say("D1.1 unreadable read, repo-B URL         -> no admission; readable repo-A read -> one review")

    def test_publication_orders_and_proof(self):  # D1.2
        changes = self.verdict(OLD, 1, "changes")
        self.scene([changes])
        self.poll_saw()
        self.offer()
        self.assert_parked()
        start = 2_000_000_000
        self.assertEqual(self.renudges(start, range(0, 961, 60)), [])  # 16 unchanged minutes: never re-typed
        self.live["reviews"].append(self.note(proof="Pushed the fix."))  # published without proof
        self.save()
        self.poll_saw()
        self.assertEqual(self.renudges(start + 1000, [0], seen=self.seen), [0])  # the new note wakes it once
        self.pool()
        self.assert_parked("note without proof")
        self.live["reviews"].append(self.note(proof="Evidence: N/A — docs-only wording, no behaviour change."))
        self.save()
        self.poll_saw()
        self.assertEqual(self.renudges(start + 1060, [0], seen=self.seen), [0])
        self.pool()
        self.assertEqual((self.reviewers(), self.messages()), (["vera-12-r2-review"], []))
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha))  # the late done: wake
        self.route()
        self.pool()
        self.assertEqual((self.reviewers(), self.messages()), (["vera-12-r2-review"], []))
        say("D1.2 head->note: parked 16 min with 0 re-nudges; proofless note re-parks; reasoned N/A -> one review; "
            "late done: starts none")

    def test_note_before_head_event_and_failed_post(self):  # D1.2
        self.scene([self.verdict(OLD, 1, "changes"), self.note()])
        self.offer()
        self.assertEqual(self.reviewers(), ["vera-12-r2-review"])
        self.fresh()
        self.push()  # its post failed; `done:` was still written
        self.scene([self.verdict(OLD, 1, "changes"), self.note(sha=OLD)], headRefOid=self.sha)
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha))
        self.route()
        self.pool()
        self.assert_parked("done: without its published note")
        self.live["reviews"].append(self.note())  # the readback after the uncertain post finds it published
        self.save()
        self.pool()
        self.assertEqual(self.reviewers(), ["vera-12-r2-review"])
        self.assertEqual(self.record("vera-12-r2-review")["head"], self.sha)
        say("D1.2 note->event: one review at once; done: without a published note parks until readback finds it")

    def test_pending_survives_restart_duplicates_hold_and_supersession(self):  # D1.3
        self.scene([self.verdict(OLD, 1, "changes")])
        self.offer()
        self.assert_parked()
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 3)
            self.assertEqual(self.lead.ensure(self.args, "reviewer"), 0)
        self.offer()  # duplicate event and handoff after the restart: the same two ids
        self.assert_parked("after restart")
        self.assertEqual(len(self.messages()), 2)
        self.live["labels"] = [{"name": "crew:hold"}]
        self.save()
        self.pool()
        self.assertEqual(self.waits()[-2:], ["waiting: #12 hold id=%s" % m["id"] for m in self.messages()])
        self.live["labels"] = []
        self.save()
        self.pool()
        self.assert_parked("hold released, still no note")
        h1 = self.sha
        self.push()  # H2 supersedes H1
        self.scene([self.verdict(OLD, 1, "changes"), self.note(sha=h1)], headRefOid=self.sha)
        self.pool()
        self.assertEqual((self.reviewers(), self.messages()), ([], []))  # H1's demand retires itself
        self.live["reviews"].append(self.note())
        self.save()
        self.offer()
        self.assertEqual(self.reviewers(), ["vera-12-r2-review"])
        self.assertEqual(self.record("vera-12-r2-review")["head"], self.sha)
        say("D1.3 restart+duplicates keep 2 parked ids; hold parks then evidence again; H2 retires H1; one review at H2")

    def test_backstop_releases_a_published_note_without_done(self):  # D1.4
        self.scene([self.verdict(OLD, 1, "changes")])
        self.poll_saw()
        self.offer()
        self.assert_parked()
        start = 2_000_000_000
        self.assertEqual(self.renudges(start, range(0, 301, 60)), [])
        self.live["reviews"].append(self.note())  # no done:, no builder run: only the published note
        self.save()
        self.poll_saw()
        self.assertEqual(self.renudges(start + 400, [0]), [0])  # a restarted watcher (fresh seen) reconciles it
        self.pool()
        self.assertEqual(self.reviewers(), ["vera-12-r2-review"])
        say("D1.4 published note, done: lost, watcher restarted -> backstop wakes the lead; one review")

    def test_removed_note_keeps_a_visible_wait(self):  # D1.4 control
        self.scene([self.verdict(OLD, 1, "changes"), self.note()])
        self.poll_saw()
        self.scene([self.verdict(OLD, 1, "changes")])  # removed before the lead re-reads it
        self.offer()
        self.assert_parked("note removed")
        start = 2_000_000_000
        self.poll_saw()
        self.assertEqual(self.renudges(start, [0]), [0])  # poll's changed record wakes once
        self.pool()
        self.assert_parked("re-read: still no note")
        self.assertEqual(self.renudges(start + 60, range(0, 901, 60), seen=self.seen), [])
        say("D1.4 removed note -> no admission; visible evidence wait; no time-based waiver over 15 min")

    def test_operation_matrix(self):  # D1.5
        body = self.live["body"]
        rows = lambda: [  # noqa: E731 (notes are numbered per fixture)
            ("initial: signed body", [], True, {}, 1, True),
            ("initial: body by another login", [], True, dict(author={"login": "acme-other"}), 1, False),
            ("initial: no builder marker", [], True, dict(body=body.split("<!--")[0] + "— 🛠️ Ben (Builder) · c · m"), 1, False),
            ("initial: marker names no linked item", [], True, dict(body=body.replace("issue=7", "issue=8")), 1, False),
            ("initial: no inline proof", [], True, dict(body=body.replace("~~~", "")), 1, False),
            ("unknown operation", [], True, dict(commits=[]), 1, False),
            ("ci-fix before verdict: none", [], False, {}, 1, False),
            ("ci-fix before verdict: round 0", [self.note("ci-fix", "0")], False, {}, 1, True),
            ("ci-fix before verdict: round 1", [self.note("ci-fix", "1")], False, {}, 1, False),
            ("ci-fix before verdict: fix kind", [self.note("fix", "0")], False, {}, 1, False),
            ("merge-up before verdict", [self.note("merge-up", "n/a", proof="")], False, {}, 1, True),
            ("fix same head: none", [self.verdict(self.sha, 1, "changes")], False, {}, 2, False),
            ("fix same head: before verdict", [self.note(), self.verdict(self.sha, 1, "changes")], False, {}, 2, False),
            ("fix same head: ci-fix kind", [self.verdict(self.sha, 1, "changes"), self.note("ci-fix", "1")], False, {}, 2, False),
            ("fix same head: new note", [self.verdict(self.sha, 1, "changes"), self.note()], False, {}, 2, True),
            ("ci-fix after verdict: round 2", [self.verdict(OLD, 2, "pass"), self.note("ci-fix", "2")], False, {}, 1, True),
            ("ci-fix after verdict: round 0", [self.verdict(OLD, 2, "pass"), self.note("ci-fix", "0")], False, {}, 1, False),
            ("merge-up different: note", [self.verdict(OLD, 2, "pass"), self.note("merge-up", "n/a", proof="")], False, {}, 1, True),
            ("merge-up different: round 2", [self.verdict(OLD, 2, "pass"), self.note("merge-up", "2")], False, {}, 1, False),
            ("after reset: note", [self.verdict(OLD, 2, "pass"), self.reset(), self.note("fix", "1")], False, {}, 1, True),
            ("after reset: note before it", [self.verdict(OLD, 2, "pass"), self.note("fix", "2"), self.reset()], False, {}, 1, False),
        ]
        for row in range(len(rows())):
            if row:
                self.fresh()
            why, reviews, opened, live, round_, admitted = rows()[row]
            with self.subTest(why):
                self.scene(reviews, opened, **live)
                # a replayed new-head for a head whose newest verdict is its own is consumed (#1124): explicit handoff
                self.offer(round_, paths=("review",) if "same head" in why else ("work",))
                if admitted:
                    self.assertEqual((self.reviewers(), self.messages()), (["vera-12-r%d-review" % round_], []))
                else:
                    self.assert_parked(why)
                say("D1.5 %-36s -> %s" % (why, "one review" if admitted else "parked"))
        self.fresh()
        self.scene([self.verdict(self.sha, 2, "pass")])  # no-op merge-up: same head, nothing to note
        self.offer(2)
        self.assertEqual((self.reviewers(), self.messages()), ([], []))  # consumed, never a wait
        say("D1.5 %-36s -> consumed; no wait for a note never posted" % "merge-up no-op (passed head)")


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if a.startswith("test_")] or \
        [n for n in ReviewReadiness.__dict__ if n.startswith("test_")]  # named tests, else all
    result = unittest.TextTestRunner().run(unittest.TestSuite(ReviewReadiness(n) for n in names))
    sys.exit(not result.wasSuccessful())
