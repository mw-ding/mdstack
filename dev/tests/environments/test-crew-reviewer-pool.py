"""Reviewer lead fixtures: handoff replay, fresh passes, schedule decide admission, cleanup and identity recovery.
Fake tmux/GitHub; --transcript prints the handoff-to-completion lifecycle; --held-wait-transcript runs and prints
#1836's parked held-request waits. Run in CI.
"""
import argparse
import datetime
import importlib.machinery
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW, FAKE_TMUX_PANES, FAKE_PS

loader = importlib.machinery.SourceFileLoader("route_tests", os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-crew-route.py"))
route_tests = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(route_tests)


class ReviewerPool(route_tests.Route):
    def setUp(self):
        super().setUp()
        bindir = os.path.join(self.tmp, "bin")
        os.rename(os.path.join(bindir, "tmux"), os.path.join(bindir, "tmux-base"))
        for name, text in (("tmux", FAKE_TMUX_PANES), ("ps", FAKE_PS)):
            with open(os.path.join(bindir, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(bindir, name), 0o755)
        self.env.update(FAKE_PANES=os.path.join(self.tmp, "panes.json"), FAKE_PS=os.path.join(self.tmp, "ps.json"))
        self.put("render/runtime/reviewer-lead.md", "Manage the reviewer pool; never review.\n")
        loader = importlib.machinery.SourceFileLoader("reviewer_cli", CREW)
        self.mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(self.mod)
        self.lead = self.mod.commands()["lead"]
        self.args = argparse.Namespace(project=self.project, org_profile=None, timeout=1)

    def pool(self, load=0):
        with mock.patch.dict(os.environ, dict(self.env, CREW_POOL="reviewer")), \
                mock.patch("os.getloadavg", return_value=(load, 0, 0)), mock.patch("os.cpu_count", return_value=4):
            self.assertEqual(self.mod.commands()["reviewer-pool"].run(self.args), 0)

    def gate(self, options="max_suites = 1\nmax_load = 4"):
        with open(self.project, "a") as out:
            out.write("\n[runtime.options]\n" + options + "\n")

    def target(self, n):
        """schedule/target.json with room for n busy workers, changed now so it holds for the test."""
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.put("schedule/target.json", json.dumps(dict(target=n, changed=now, starts=[])))

    def messages(self):
        return self.lead.pending(self.state, "vera-lead")

    def handoff(self, kind, refs):
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.handoff(self.args, "reviewer", kind, refs), 0)

    def test_handoff_dispatch_complete_reclaim(self):
        self.queue(self.event(), self.event())
        self.route()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(len(self.messages()), 1)
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])
        self.put("verdicts/pr12-%s-r1-review.md" % self.sha[:7], "review output")
        self.put("status/vera-12-r1-review.status", "done: #12 %s review pass\n" % self.sha)
        self.queue(self.status("vera-12-r1-review", "review pass"))
        self.route()
        self.pool()
        self.assertNotIn("vera-12-r1-review", self.names())
        self.assertIn("vera-12-r1-validate", self.names())
        self.queue(self.status("vera-12-r1-validate", "validate pass"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(self.messages(), [])
        if "--transcript" in sys.argv:
            print("$ mdstack route --project <fixture>/crew.toml --timeout 1; exit 0")
            print("$ mdstack reviewer-pool --project <fixture>/crew.toml; exit 0")
            print("handoff received: one lead, one durable request, zero workers")
            print("dispatch: one fresh review; duplicate event suppressed")
            print("completion: review reclaimed, retained output, fresh validation")
            print("validation completed: both workers reclaimed; lead stays; pending=0")

    def test_resumed_fix_head_dispatches_the_round_poll_emits(self):  # #1005: vera-991-r4-review was round 1
        def marker(text, login="acme-reviewer", name="Vera"):
            return dict(author={"login": login}, body="<!-- crew:v1 %s -->\n— 🔍 %s (Role) · codex · m" % (text, name))
        self.live["reviews"] = [marker("role=reviewer-validator pass=verdict pr=12 sha=%s round=%d verdict=changes"
                                       % (str(k) * 40, k)) for k in (1, 2, 3)]
        self.live["reviews"] += [
            marker("role=coordinator pass=steer pr=12 sha=%s round=n/a verdict=n/a cmd=resume cmd-id=chat" % ("3" * 40),
                   "acme-bot", "Ash"),
            marker("role=builder pass=fix pr=12 sha=%s round=1 verdict=n/a" % self.sha, "acme-bot", "Ben")]
        self.live["reviews"][-1]["body"] = "~~~text\n$ make test\nok\n~~~\n" + self.live["reviews"][-1]["body"]
        self.save()
        values = self.mod.profile(self.args)[0]
        events, _ = self.mod.commands()["poll"].decide({}, [dict(self.live, labels=[{"name": "crew:in-review"}])], [],
                                                         values=values)
        self.assertEqual([(e["event"], e["round"]) for e in events], [("new-head", 1)])
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha))
        self.route()
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertNotIn("vera-12-r4-review", self.names())

    def test_malformed_work_ref_is_recorded_and_the_queue_drains(self):  # #1020
        self.put("hold-note.md", "# hold #1001\n")
        self.put("leads/reviewer-events/list.json", "[1]")
        for bad in ("hold-note.md", "leads/reviewer-events/list.json", "leads/reviewer-events/gone.json"):
            self.handoff("work", [os.path.join(self.state, bad)])
        bad_ids = [m["id"] for m in self.messages()]
        self.queue(self.event())
        self.route()
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])
        with open(os.path.join(self.state, "status", "vera-lead.status")) as f:
            blocked = [l.split()[1:3] for l in f if l.startswith("blocked: ")]
        self.assertEqual(blocked, [[i, "invalid-work-ref"] for i in bad_ids])

    def test_deferred_valid_work_stays_replayable_beside_a_malformed_ref(self):  # #1020
        self.gate("max_load = 4")
        result = self.spawn("reviewer", "--pr", "12", "--round", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.put("hold-note.md", "# hold #1001\n")
        self.handoff("work", [os.path.join(self.state, "hold-note.md")])
        self.queue(self.event())
        self.route()
        self.pool()  # first decision: T starts at the busy count, 1
        self.assertNotIn("vera-12-r1-review", self.names())
        self.target(4)
        self.pool(load=4)
        self.assertNotIn("vera-12-r1-review", self.names())
        self.assertEqual([m["kind"] for m in self.messages()], ["work"])
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])

    def test_done_line_with_trailing_note_still_routes(self):  # #1343
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        note = "review pass Independent validation required; CI markdownlint red: stale link"
        self.put("verdicts/pr12-%s-r1-review.md" % self.sha[:7], "review output")
        self.put("status/vera-12-r1-review.status", "done: #12 %s %s\n" % (self.sha, note))
        self.queue(self.status("vera-12-r1-review", note))
        self.route()
        self.pool()
        self.assertNotIn("vera-12-r1-review", self.names())
        self.assertIn("vera-12-r1-validate", self.names())
        self.queue(self.status("vera-12-r1-validate", "validate pass all ACs proven"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(self.messages(), [])

    def test_no_ceiling_admits_under_high_load(self):
        self.target(4)
        result = self.spawn("reviewer", "--pr", "12", "--round", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool(load=170)
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])

    def test_target_and_max_load_defer_then_resume(self):
        self.gate("max_load = 4")
        result = self.spawn("reviewer", "--pr", "12", "--round", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()  # first decision: T starts at the busy count, 1
        self.target(4)
        self.pool(load=4)
        self.assertNotIn("vera-12-r1-review", self.names())
        self.assertEqual(len(self.messages()), 1)
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])
        day = datetime.datetime.now(datetime.timezone.utc).strftime("decisions-%Y%m%d.jsonl")
        with open(os.path.join(self.state, "schedule", day)) as f:
            self.assertEqual([(a["action"], a["reasons"]) for a in map(json.loads, f) if a["action"] != "snapshot"],
                             [("defer", ["target"]), ("defer", ["max_load"]), ("admit", [])])

    def test_reviewer_floor_under_builder_load(self):
        self.gate()
        self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        self.target(1)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool(load=170)
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])
        if "--admission-transcript" in sys.argv:
            print("busy builder, T=1, max_suites=1 max_load=4, load=170: the empty reviewer pool's floor admits one review")

    def test_review_held_by_builder_call_is_granted_on_next_reviewer_call(self):
        self.put("inbox/ben-lead.jsonl", json.dumps(dict(id="b1", kind="build", refs=["#20"])) + "\n")
        self.handoff("review", ["#12", self.sha, "1"])
        r = self.crew("schedule", "decide", "--pool", "builder", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(([a["ref"] for a in out["holds"]], [a["ref"] for a in out["admit"]]), (["#12"], ["#20"]))
        self.assertNotIn("vera-12-r1-review", self.names())
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])
        if "--admission-transcript" in sys.argv:
            print("builder decide: holds #12, admits #20; next reviewer-pool call grants and starts the #12 review")

    def test_failed_spawn_releases_the_grant(self):
        self.handoff("review", ["#12", self.sha, "1"])
        with mock.patch.object(self.mod.commands()["route"], "invoke", side_effect=RuntimeError("crew: spawn failed")):
            self.pool()
        with open(os.path.join(self.state, "schedule", "reservations.json")) as f:
            self.assertEqual(json.load(f), [])
        self.assertEqual(len(self.messages()), 1)

    def test_completed_review_reclaimed_by_kill_starts_validation(self):
        """Review rounds 1-2: a lifecycle wake from `mdstack kill` is saved as the completion it carries, so decide ranks
        the validation and a target deferral keeps it pending until the retry starts it."""
        self.target(4)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertEqual(self.spawn("reviewer", "--pr", "12", "--round", "3").returncode, 0)
        self.target(1)
        self.put("verdicts/pr12-%s-r1-review.md" % self.sha[:7], "Review passed")
        self.put("status/vera-12-r1-review.status", "done: #12 %s review pass\n" % self.sha)
        result = self.crew("kill", "vera-12-r1-review", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([m["kind"] for m in self.messages()], ["work"])
        self.pool()
        self.assertNotIn("vera-12-r1-validate", self.names())
        self.assertEqual(len(self.messages()), 1)
        self.target(4)
        self.pool()
        self.assertIn("vera-12-r1-validate", self.names())
        self.assertEqual(self.messages(), [])

    def test_profile_suite_cap_allows_reviewer_expansion(self):
        with open(self.project, "a") as out:
            out.write("\n[runtime.options]\nmax_suites = 2\n")
        self.target(4)
        result = self.spawn("reviewer", "--pr", "12", "--round", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())
        self.assertEqual(self.messages(), [])

    def test_builder_completion_wakes_deferred_review(self):
        result = self.spawn("reviewer", "--pr", "12", "--round", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()  # T starts at the busy count, 1
        self.assertEqual(len(self.messages()), 1)
        self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        before = len(self.calls())
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha))
        self.route()
        self.assertTrue(any(c[0] == "send-keys" and c[c.index("-t") + 1] == "=crew-acme-widgets:3"
                            and c[-1].startswith("inbox:") for c in self.calls()[before:]))
        self.target(3)
        self.pool()
        self.assertEqual(sorted(n for n in self.names() if n.endswith("review")),
                         ["vera-12-r1-review", "vera-12-r3-review"])
        self.assertEqual(self.messages(), [])
        if "--admission-transcript" in sys.argv:
            print("target 1 reached: review deferred; pending=1; existing review=1")
            print("builder done: reviewer lead nudged without coordinator handoff")
            print("target raised: pending=0; fresh review=1; duplicate completion suppressed")

    def delta_merge_up(self, note):
        previous = self.approved_push()
        self.live["reviews"][-1]["body"] = (
            "[Ben/fix] round 2 @ " + self.sha[:7] + "\n\n" + note + "\n" +
            self.live["reviews"][-1]["body"] + "\n— 🛠️ Ben (Builder) · codex · gpt-6.1-sol")
        self.save()
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha),
                   dict(self.event("merge-up"), previous_head=previous, round=2))
        self.route()
        self.pool()
        self.assertEqual([n for n in self.names() if n.endswith("review")], ["vera-12-r2-review"])
        self.assertEqual(self.record("vera-12-r2-review")["head"], self.sha)
        self.assertEqual(self.messages(), [])
        if "--merge-up-transcript" in sys.argv:
            print(note + " -> one review at updated head, round 2; no coordinator handoff")
        self.queue(self.status("vera-12-r2-review", "review pass"))
        self.route()
        self.pool()
        self.assertIn("vera-12-r2-validate", self.names())
        if "--merge-up-transcript" in sys.argv:
            print("delta review passed -> fresh independent validation at updated head")

    def test_resolved_conflict_merge_up_starts_delta_review(self):
        self.delta_merge_up("Resolved conflict in docs.")

    def test_semantic_conflict_fix_starts_delta_review(self):
        self.delta_merge_up("Fixed train's semantic conflict.")

    def test_differing_patch_merge_up_starts_delta_review(self):
        self.delta_merge_up("Differing patch after merge-up.")

    def published_note(self, previous):
        """The verbatim #1656 merge-up note (review 5857839197), re-pinned to this fixture's PR and head (#1682)."""
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "merge-up",
                               "pr1656-review-5857839197.txt")) as f:
            body = f.read()
        old = "72db15d699e1bf78cae41064f9e7a51143cb42f9"
        return body.replace(old, self.sha).replace(old[:7], self.sha[:7]).replace("pr=1656", "pr=12")

    def test_published_merge_up_note_replays_to_one_delta_review(self):  # #1682
        previous = self.approved_push()
        self.live["reviews"][-1] = dict(body=self.published_note(previous), author={"login": "acme-bot"})
        self.live["labels"] = [{"name": "crew:approved"}]
        self.save()
        poll, values = self.mod.commands()["poll"], self.mod.profile(self.args)[0]
        with mock.patch.dict(os.environ, self.env):
            approved = poll.merge_up(self.live, {"head": previous}, "acme/widgets", "main")
        events, _ = poll.decide({"prs": {"12": {"head": previous}}}, [self.live], [], {"12": approved}, values=values)
        event = next(e for e in events if e["event"] == "merge-up")
        self.assertEqual((event["refs"], event["previous_head"], event["round"]), (["#12", self.sha], previous, 2))
        built = dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha)
        for replay in (False, True):
            self.queue(built, dict(event, reason="poll", id="poll-%d" % replay))
            self.route()
            self.pool()
            self.assertEqual([n for n in self.names() if n.endswith(("review", "validate"))], ["vera-12-r2-review"])
            self.assertEqual(self.record("vera-12-r2-review")["head"], self.sha)
            self.assertEqual(self.messages(), [])
            self.assertEqual(self.pending(), [])
        if "--merge-up-transcript" in sys.argv:
            print("published #1656 merge-up note -> one review at updated head, round 2; replay starts none")

    def test_published_merge_up_note_without_delta_keeps_current_handling(self):  # #1682
        route = self.mod.commands()["route"]
        previous = self.approved_push()
        note, verdicts = self.published_note(previous), self.live["reviews"][:-1]
        self.live["reviews"] = verdicts + [dict(body=note)]
        self.assertTrue(route.merge_up_delta(self.live, self.sha, "Ben"))
        clean = note.replace("The merge hit two text conflicts and one semantic conflict, and all three are resolved.",
                             "The merge was clean; no conflicts.")
        for body in (clean, note.replace(self.sha, "f" * 40), note.replace("Ben (Builder)", "Bo (Builder)"),
                     note.split("\n— ")[0], note.replace("[Ben/merge-up]", "[Ben/status]")):
            self.live["reviews"] = verdicts + [dict(body=body)]
            self.assertFalse(route.merge_up_delta(self.live, self.sha, "Ben"))
        self.live["reviews"] = verdicts + [dict(body=clean)]
        self.live["labels"] = [{"name": "crew:approved"}]
        self.save()
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha),
                   dict(self.event("merge-up"), previous_head=previous, round=2, consumer="synthesizer"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual([w["event"] for w in self.pending()], ["merge-up"])

    def test_identical_merge_up_keeps_synthesizer_portability(self):
        previous = self.approved_push()
        self.queue(dict(reason="status", window="ben-7", line="done: #7 #12 " + self.sha),
                   dict(self.event("merge-up"), previous_head=previous, round=2, consumer="synthesizer"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(self.messages(), [])
        self.assertEqual([w["event"] for w in self.pending()], ["merge-up"])
        if "--merge-up-transcript" in sys.argv:
            print("identical merge-up -> synthesizer portability; zero review workers")

    def test_delta_note_must_be_signed_and_pin_current_head(self):
        route = self.mod.commands()["route"]
        note = ("[Ben/fix] round 1 @ " + self.sha[:7] + "\nResolved conflict.\n"
                "<!-- crew:v1 role=builder pass=fix pr=12 sha=%s round=1 verdict=n/a -->\n"
                "— 🛠️ Ben (Builder) · codex · gpt-6.1-sol")
        self.live["reviews"] = [dict(body=note % self.sha)]
        self.assertTrue(route.merge_up_delta(self.live, self.sha, "Ben"))
        for signed in ("— Ben (Builder) · codex · gpt-6.1-sol", "— 🧰 Ben (Builder) · md · codex · gpt-6.1-sol"):  # #431
            self.live["reviews"] = [dict(body=(note % self.sha).replace("— 🛠️ Ben (Builder) · codex · gpt-6.1-sol", signed))]
            self.assertTrue(route.merge_up_delta(self.live, self.sha, "Ben"), signed)
        self.assertFalse(route.merge_up_delta(self.live, self.sha, "Bo"))
        for body in (note % ("f" * 40), (note % self.sha).split("—")[0],
                     (note % self.sha).replace("Resolved conflict.", "Identical merge-up; no conflicts."),
                     (note % self.sha).replace("Resolved conflict.", "No differing patch.")):
            self.live["reviews"] = [dict(body=body)]
            self.assertFalse(route.merge_up_delta(self.live, self.sha, "Ben"))

    def test_full_cap_then_completed_slot_admits_validation(self):
        self.env["CREW_POOL"] = "reviewer"
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('name = "tmux"\n', 'name = "tmux"\noptions = { reviewers = 1 }\n'))
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.handoff("review", ["#12", self.sha, "2"])
        self.pool()
        self.assertNotIn("vera-12-r2-review", self.names())
        self.assertEqual(len(self.messages()), 1)
        self.put("status/vera-12-r1-review.status", "done: #12 %s review pass\n" % self.sha)
        with mock.patch.dict(os.environ, self.env):
            self.lead.event(self.args, "reviewer", self.status("vera-12-r1-review", "review pass"))
        self.pool()
        self.assertNotIn("vera-12-r1-review", self.names())
        self.assertIn("vera-12-r1-validate", self.names())

    def test_replay_review_after_cleanup_starts_missing_validation(self):
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertEqual(self.crew("kill", "vera-12-r1-review", "--project", self.project, CREW_POOL="reviewer").returncode, 0)
        wake = dict(self.status("vera-12-r1-review", "review pass"), round=1)
        with mock.patch.dict(os.environ, self.env):
            self.lead.event(self.args, "reviewer", wake)
        self.pool()
        self.assertIn("vera-12-r1-validate", self.names())
        self.pool()
        self.assertEqual(len([n for n in self.names() if "validate" in n]), 1)

    def test_recheck_escalation_starts_review_then_validation(self):
        self.live["reviews"] = [self.changes("0" * 40), self.builder_note("merge-up", "n/a")]  # live round 2 (#1878)
        self.save()
        self.handoff("recheck", ["#12", self.sha, "2"])
        self.pool()
        self.queue(self.status("vera-12-r2-recheck", "recheck escalate"))
        self.route()
        self.pool(load=4)
        self.assertIn("vera-12-r2-review", self.names())
        self.assertEqual(self.messages(), [])
        self.pool()
        self.assertNotIn("vera-12-r2-recheck", self.names())
        self.assertIn("vera-12-r2-review", self.names())
        self.queue(self.status("vera-12-r2-review", "review pass"))
        self.route()
        self.pool()
        self.assertIn("vera-12-r2-validate", self.names())

    def test_recheck_completion_never_starts_validation(self):
        self.handoff("recheck", ["#12", self.sha, "1"])
        self.pool()
        self.queue(self.status("vera-12-r1-recheck", "recheck pass"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])

    def test_held_request_stays_stale_head_retires(self):
        self.live["labels"] = [{"name": "crew:escalated"}]
        self.save()
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertEqual(len(self.messages()), 1)
        self.live["headRefOid"] = "f" * 40
        self.save()
        self.pool()
        self.assertEqual(self.messages(), [])
        self.assertEqual(self.names(), ["ash", "vera-lead"])

    def test_hold_label_stays_held_when_hold_label_blocks_is_false(self):  # #1124
        self.gate("hold_label_blocks = false")
        self.live["labels"] = [{"name": "crew:hold"}]
        self.save()
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertEqual(len(self.messages()), 1)
        self.assertEqual(self.names(), ["ash", "vera-lead"])

    def park(self, label="crew:escalated"):
        """#1836's production path: a held #12's durable review-changes status event and direct review, validate
        and recheck handoffs, all dispatched by reviewer-pool while the label is live; their inbox ids."""
        self.live["labels"] = [{"name": label}]
        self.save()
        wake = dict(self.status("vera-12-r1-review", "review changes escalated"), round=1)
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.event(self.args, "reviewer", wake), 0)
        for kind in ("review", "validate", "recheck"):
            self.handoff(kind, ["#12", self.sha, "1"])
        ids = [m["id"] for m in self.messages()]
        self.assertEqual([m["kind"] for m in self.messages()], ["work", "review", "validate", "recheck"])
        self.pool()
        return ids

    def waits(self):
        with open(os.path.join(self.state, "status", "vera-lead.status")) as f:
            return [line.strip() for line in f if line.startswith("waiting:")]

    def renudges(self, start, offsets, changes=(), seen=None):
        """Watcher scans and lead retries (backstop, slot release, coordinator) at each offset after `start`, applying
        `changes` (offset -> callable) first; the offsets whose scan or retry typed an inbox id into vera-lead."""
        self.seen, typed = seen or {"offsets": {}, "keys": {}}, []
        changes = dict(changes)
        for t in offsets:
            if t in changes:
                changes[t]()
            before = len(self.calls())
            with mock.patch.dict(os.environ, self.env):
                woke = any(w["reason"] == "lead-backstop" and w.get("window") == "vera-lead"
                           for w in self.mod.scan(self.state, "crew-acme-widgets", start + t, 900, self.seen))
                for recheck in (True, False):
                    self.lead.retry_pending(self.args, "vera-lead", recheck=recheck)
                self.lead.retry_pending(self.args)  # the coordinator backstop walks every lead
            if woke or any(c[0] == "send-keys" and any(a.startswith("inbox: ") for a in c) for c in self.calls()[before:]):
                typed.append(t)
        return typed

    def test_held_ref_parks_with_a_dispatcher_wait_through_unchanged_hold(self):  # #1836
        ids = self.park()
        self.assertEqual(self.waits(), ["waiting: #12 owner id=%s" % i for i in ids])  # after each id's ack
        self.assertEqual(len(self.messages()), 4)  # parked, not done
        sample = dict(state="OPEN", head=self.sha, ci="pending", verdict=None, mergeable="MERGEABLE", hold=False,
                      ready=False)
        poll = {"observed": {"12": sample}, "held": [], "answers": {}}  # poll has not seen the escalation yet

        def update(**fields):
            def apply():
                sample.update(fields.pop("sample", {}))
                poll.update(fields)
                self.put("poll-state.json", json.dumps(poll))
            return apply

        update()()
        start, quarter = 2_000_000_000, range(0, 961, 30)
        changes = {60: update(sample=dict(hold=True, verdict="changes"), held=["#12"], answers={"#12": 3}),
                   300: self.pool, 330: self.pool,  # dispatcher re-runs: a fresh ack after the wait, re-parked
                   870: update(sample=dict(mergeable="UNKNOWN")), 930: update(sample=dict(mergeable="MERGEABLE"))}
        self.assertEqual(self.renudges(start, quarter, changes), [])  # the reported 15 minutes: zero re-nudges
        restarted = json.loads(json.dumps(self.seen))
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 3)
            self.assertEqual(self.lead.ensure(self.args, "reviewer"), 0)  # lead restart keeps inbox and waits
        self.assertEqual(self.renudges(start + 990, range(0, 1801, 60), seen=restarted), [])  # and the watcher's
        self.assertEqual(len(self.messages()), 4)
        with open(os.path.join(self.state, "inbox", "vera-lead.jsonl"), "a") as f:  # a genuinely new handoff
            f.write(json.dumps(dict(id="fresh", kind="review", refs=["#12", self.sha, "2"])) + "\n")
        before = len(self.calls())
        self.assertEqual(self.renudges(start + 2850, [0], seen=self.seen), [0])
        self.assertEqual({a for c in self.calls()[before:] if c[0] == "send-keys" for a in c if a.startswith("inbox: ")},
                         {"inbox: fresh"})
        if "--held-wait-transcript" in sys.argv:
            print("held #12: work, review, validate and recheck ids parked by reviewer-pool; 15 min of hold/verdict/mergeable churn, 2 dispatcher "
                  "re-runs, lead and watcher restart: 0 re-nudges")

    def test_parked_ref_wakes_on_listed_changes_and_reparks(self):  # #1836
        ids = self.park()
        sample = dict(state="OPEN", head=self.sha, ci="pending", verdict="changes", mergeable="MERGEABLE", hold=True,
                      ready=False)
        poll = {"observed": {"12": sample}, "held": ["#12"], "answers": {"#12": 3}}
        self.put("poll-state.json", json.dumps(poll))
        start = 2_000_000_000
        self.assertEqual(self.renudges(start, [0]), [])
        for t, change in enumerate((lambda: sample.update(ci="passed"),  # CI change
                                    lambda: poll["answers"].update({"#12": 4}),  # owner answer
                                    lambda: self.put("asks/12.json", "{}"),  # an owner ask opened
                                    lambda: poll.update(held=[], answers={})), 1):  # hold released
            with self.subTest(change=t):
                change()
                self.put("poll-state.json", json.dumps(poll))
                self.assertEqual(self.renudges(start + 60 * t, [0], seen=self.seen), [0])
                self.pool()  # re-reads live eligibility: still escalated on GitHub, parked again
                self.assertEqual(self.waits()[-4:], ["waiting: #12 owner id=%s" % i for i in ids])
                self.assertEqual(self.renudges(start + 60 * t + 30, [0], seen=self.seen), [])
        self.live["labels"] = [{"name": "crew:hold"}]
        self.save()
        self.pool()
        self.assertEqual(self.waits()[-4:], ["waiting: #12 hold id=%s" % i for i in ids])
        self.live["headRefOid"] = "f" * 40  # moved work retires; nothing starts and no hold is cleared
        self.save()
        self.pool()
        self.assertEqual((self.messages(), self.names()), ([], ["ash", "vera-lead"]))
        if "--held-wait-transcript" in sys.argv:
            print("parked #12 wakes once each on CI, owner answer, ask and hold release, then re-parks; a moved head "
                  "retires all four ids")

    def test_same_head_rereview_ignores_old_section(self):
        self.put("verdicts/pr12-%s-r1-review.md" % self.sha[:7],
                 "<!-- crew:v1 role=reviewer-validator pass=review pr=12 sha=%s round=1 verdict=pass -->" % self.sha)
        self.live["reviews"] = [dict(body="<!-- crew:v1 role=coordinator pass=steer cmd=rereview cmd-id=42 sha=%s -->" % self.sha)]
        self.save()
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.assertIn("vera-12-r1-review", self.names())

    def test_lead_restart_preserves_queue_and_live_worker(self):
        self.target(4)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.handoff("validate", ["#12", self.sha, "1"])
        with mock.patch.dict(os.environ, self.env):
            rec = dict(self.lead.records(self.state))["vera-lead"]
            windows = dict((n, i) for i, n in self.mod.tmux.list_windows("crew-acme-widgets"))
            self.assertEqual(self.mod.probe("crew-acme-widgets", "vera-lead", rec, windows), "alive")
        if "--transcript" in sys.argv:
            print("before recovery: readiness=alive; live review=1; pending validation=1")
        worker = self.record("vera-12-r1-review")
        self.pool()
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 3)
            self.assertEqual(self.lead.ensure(self.args, "reviewer"), 0)
            rec = dict(self.lead.records(self.state))["vera-lead"]
            windows = dict((n, i) for i, n in self.mod.tmux.list_windows("crew-acme-widgets"))
            self.assertEqual(self.mod.probe("crew-acme-widgets", "vera-lead", rec, windows), "alive")
        if "--transcript" in sys.argv:
            print("after recovery: readiness=alive; restarts=1; live review=1; pending validation=1")
        self.assertEqual(self.record("vera-12-r1-review"), worker)
        self.assertEqual(len(self.messages()), 1)
        self.put("verdicts/pr12-%s-r1-review.md" % self.sha[:7],
                 "<!-- crew:v1 role=reviewer-validator pass=review pr=12 sha=%s round=1 verdict=pass -->" % self.sha)
        self.pool()
        self.assertIn("vera-12-r1-validate", self.names())
        with mock.patch.dict(os.environ, self.env):
            self.mod.tmux.kill_window("crew-acme-widgets", 3)
            self.assertEqual(self.lead.ensure(self.args, "reviewer"), 1)
        if "--transcript" in sys.argv:
            print("$ mdstack lead ensure reviewer --project <fixture>/crew.toml; first recovery exit 0, second exit 1")
            print("lead restart: identity replaced; live review untouched; pending validation preserved and dispatched")
            print("second lead failure: blocked; no replacement; workers retained")

    def test_worker_probe_restarts_once_and_never_ambiguous(self):
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        wake = dict(reason="stale", window="vera-12-r1-review")
        args = argparse.Namespace(**vars(self.args), reviewer_lead=True) if not hasattr(self.args, "reviewer_lead") else self.args
        pool = self.mod.commands()["reviewer-pool"]
        with mock.patch.dict(os.environ, dict(self.env, CREW_POOL="reviewer")), \
                mock.patch.object(pool, "probe", return_value="ambiguous"):
            with self.assertRaisesRegex(RuntimeError, "escalation"):
                pool.dispatch(args, self.mod.profile(args)[0], self.state, wake)
        with mock.patch.dict(os.environ, dict(self.env, CREW_POOL="reviewer")):
            self.mod.tmux.kill_window("crew-acme-widgets", 20)
            self.assertTrue(pool.dispatch(args, self.mod.profile(args)[0], self.state, wake))
        self.assertEqual(self.record("vera-12-r1-review")["restarts"], 1)

    def test_idle_stall_wake_escalates_while_plain_silence_does_not(self):  # #1283
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        args = argparse.Namespace(**vars(self.args), reviewer_lead=True) if not hasattr(self.args, "reviewer_lead") else self.args
        pool = self.mod.commands()["reviewer-pool"]
        with mock.patch.dict(os.environ, dict(self.env, CREW_POOL="reviewer")), \
                mock.patch.object(pool, "probe", return_value="alive"):
            values = self.mod.profile(args)[0]
            self.assertTrue(pool.dispatch(args, values, self.state, dict(reason="stale", window="vera-12-r1-review",
                                                                         liveness="alive")))
            with self.assertRaisesRegex(RuntimeError, "idle at its prompt; coordinator escalation required"):
                pool.dispatch(args, values, self.state, dict(reason="stale", window="vera-12-r1-review",
                                                             liveness="idle", action="escalate"))
        self.assertFalse(self.record("vera-12-r1-review").get("restarts"))  # never a restart of a live worker

    def test_infra_ci_allows_validation_real_failure_keeps_it_pending(self):
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        check = dict(status="COMPLETED", conclusion="FAILURE")
        self.live["statusCheckRollup"] = [check]
        self.save()
        self.queue(self.status("vera-12-r1-review", "review pass"))
        self.route()
        self.pool()
        self.assertNotIn("vera-12-r1-validate", self.names())
        self.assertEqual(len(self.messages()), 1)
        check["_ci_infra"] = True
        self.save()
        self.pool()
        self.assertIn("vera-12-r1-validate", self.names())
        self.assertEqual(self.messages(), [])

    def test_ambiguous_lead_never_starts_replacement(self):
        self.handoff("review", ["#12", self.sha, "1"])
        with open(self.env["FAKE_PANES"], "w") as f:
            json.dump({"crew-acme-widgets:3": {"command": "sleep"}}, f)
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.ensure(self.args, "reviewer"), 1)
        self.assertEqual(len(self.messages()), 1)
        self.assertEqual(self.names(), ["ash", "vera-lead"])

    def test_closed_pr_reclaims_active_worker_through_lead(self):
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.live["state"] = "CLOSED"
        self.save()
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.event(self.args, "reviewer", self.event("pr-closed")), 0)
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(self.messages(), [])

    def finished_validate(self):
        result = self.spawn("reviewer", "--pr", "12", "--pass", "validate", "--round", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.put("status/vera-12-r1-validate.status", "done: #12 %s validate pass\n" % self.sha)
        own = self.record("vera-12-r1-validate")["verdict"]
        self.sections = {own.replace("validate.md", kind + ".md"): kind + " output"
                         for kind in ("review", "validate", "verdict")}
        os.makedirs(os.path.dirname(own), exist_ok=True)
        for path, text in self.sections.items():
            with open(path, "w") as f:
                f.write(text)

    def assert_sections_kept(self):
        for path, text in self.sections.items():
            with open(path) as f:
                self.assertEqual(f.read(), text, path)

    def reviewer_workers(self):
        r = self.crew("schedule", "snapshot", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return [w["name"] for w in json.loads(r.stdout)["workers"] if w["role"] == "reviewer"]

    def test_validate_done_after_merge_reclaimed_by_kill_is_reaped(self):
        """#719: `mdstack kill` from the router delegates a lifecycle reclaim; the lead saves it as the validate
        completion, whose PR has merged, and must still reap the worker and free its reviewer slot."""
        self.finished_validate()
        self.live["state"] = "MERGED"
        self.save()
        result = self.crew("kill", "vera-12-r1-validate", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "vera-12-r1-validate.json")))
        self.assertEqual(self.messages(), [])
        self.assertEqual(self.reviewer_workers(), [])
        self.assert_sections_kept()

    def test_validate_done_after_head_moved_is_reaped_once(self):
        self.finished_validate()
        self.live["headRefOid"] = "f" * 40
        self.save()
        self.queue(self.status("vera-12-r1-validate", "validate pass"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(self.messages(), [])
        with mock.patch.dict(os.environ, self.env):
            self.lead.event(self.args, "reviewer", dict(self.status("vera-12-r1-validate", "validate pass"), round=1))
        self.pool()
        self.assertEqual(self.messages(), [])
        self.assertEqual(self.reviewer_workers(), [])
        self.assert_sections_kept()

    def stale_after_external_merge(self):
        """#811: another runtime merged the PR mid-pass; the worker stopped with `done: #12 stale`."""
        self.finished_validate()
        self.put("status/vera-12-r1-validate.status", "done: #12 stale\n")
        self.live["state"] = "MERGED"
        self.save()
        return dict(reason="status", window="vera-12-r1-validate", line="done: #12 stale")

    def assert_stale_reaped(self):
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "vera-12-r1-validate.json")))
        self.assertEqual(self.messages(), [])
        self.assertEqual(self.reviewer_workers(), [])
        self.assert_sections_kept()

    def test_stale_done_after_external_merge_is_reaped_once(self):
        wake = self.stale_after_external_merge()
        self.queue(wake)
        self.route()
        self.pool()
        self.assert_stale_reaped()
        with mock.patch.dict(os.environ, self.env):
            self.lead.event(self.args, "reviewer", wake)
        self.pool()
        self.assert_stale_reaped()

    def test_stale_done_after_external_merge_reclaimed_by_kill_is_reaped(self):
        self.stale_after_external_merge()
        result = self.crew("kill", "vera-12-r1-validate", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.pool()
        self.assert_stale_reaped()

    def test_validate_pass_at_open_head_keeps_its_verdict_files(self):
        self.finished_validate()
        self.queue(self.status("vera-12-r1-validate", "validate pass"))
        self.route()
        self.pool()
        self.assertEqual(self.names(), ["ash", "vera-lead"])
        self.assertEqual(self.reviewer_workers(), [])
        self.assert_sections_kept()

    def test_rereview_waits_for_old_pass_then_starts_fresh(self):
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.live["reviews"] = [dict(body="<!-- crew:v1 role=coordinator pass=steer cmd=rereview cmd-id=42 sha=%s -->" % self.sha)]
        self.save()
        self.handoff("review", ["#12", self.sha, "1", "42"])
        self.pool()
        self.assertEqual(len(self.messages()), 1)
        self.assertEqual(len([n for n in self.names() if n.endswith("review")]), 1)
        self.queue(self.status("vera-12-r1-review", "review pass"))
        self.route()
        self.pool()
        self.assertEqual(self.record("vera-12-r1-review")["rereview_id"], "42")
        self.assertNotIn("vera-12-r1-validate", self.names())

    def test_restarted_rereview_pass_completes_without_a_duplicate(self):  # #1477
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        self.live["reviews"] = [dict(body="<!-- crew:v1 role=coordinator pass=steer cmd=rereview cmd-id=42 sha=%s -->" % self.sha)]
        self.save()
        self.handoff("review", ["#12", self.sha, "1", "42"])
        self.pool()
        self.queue(self.status("vera-12-r1-review", "review pass"))
        self.route()
        self.pool()
        self.assertEqual(self.record("vera-12-r1-review")["rereview_id"], "42")
        args = argparse.Namespace(**dict(vars(self.args), reviewer_lead=True))
        pool = self.mod.commands()["reviewer-pool"]
        with mock.patch.dict(os.environ, dict(self.env, CREW_POOL="reviewer")):  # the session is lost: clean restart
            self.mod.tmux.kill_window("crew-acme-widgets", self.record("vera-12-r1-review")["index"])
            self.assertTrue(pool.dispatch(args, self.mod.profile(args)[0], self.state,
                                          dict(reason="stale", window="vera-12-r1-review")))
        rec = self.record("vera-12-r1-review")
        self.assertEqual((rec["restarts"], rec["rereview_id"], rec["head"]), (1, "42", self.sha))
        self.queue(self.status("vera-12-r1-review", "review pass"))
        self.route()
        self.pool()
        self.assertIn("vera-12-r1-validate", self.names())  # the restarted pass's completion moves on to validation
        self.assertNotIn("vera-12-r1-review", self.names())  # and opens no duplicate same-head review

    def test_reclaim_does_not_bypass_load_admission_by_dequeuing(self):
        self.gate()
        self.target(4)
        result = self.spawn("reviewer", "--pr", "12", "--round", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.handoff("review", ["#12", self.sha, "1"])
        self.pool()
        request = dict(role="reviewer", issue=None, pr=12, head=self.sha, **{
            "pass": "review", "round": 2, "tier": "default"})
        self.put("spawn-queue.jsonl", json.dumps(request) + "\n")
        self.queue(self.status("vera-12-r1-review", "review pass"))
        self.route()
        self.pool(load=4)
        self.assertNotIn("vera-12-r1-validate", self.names())
        self.assertIn("vera-12-r3-review", self.names())
        with open(os.path.join(self.state, "spawn-queue.jsonl")) as f:
            self.assertEqual(json.loads(f.read()), request)
        self.assertEqual(len(self.messages()), 1)

    def relayed(self):
        """#1871's production path: a reviewer's review-changes status, relayed by reviewer-pool to the builder lead
        (ben-lead, beside a spawned ben-7); the builder lead acknowledges it. The relay's inbox id."""
        self.put("render/runtime/builder-lead.md", "Manage the builder pool; never build.\n")
        if not os.path.exists(os.path.join(self.state, "runs", "ben-7.json")):
            self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.event(self.args, "reviewer", dict(
                self.status("vera-12-r1-review", "review changes"), round=1)), 0)
        self.pool()
        relay = [m for m in self.lead.pending(self.state, "ben-lead") if m["kind"] == "work"]
        self.assertEqual(len(relay), 1)
        self.ben_status("ack: %s\n" % relay[0]["id"])
        return relay[0]["id"]

    def ben_status(self, line, name="ben-lead"):
        with open(os.path.join(self.state, "status", name + ".status"), "a") as f:
            f.write(line)

    def disposition(self, msg_id):
        """`mdstack lead relay builder ID` as the builder lead runs it: (exit, stdout, lines it added to its status)."""
        path = os.path.join(self.state, "status", "ben-lead.status")
        before = open(path).read() if os.path.exists(path) else ""
        r = self.crew("lead", "relay", "builder", msg_id, "--project", self.project)
        return r.returncode, r.stdout.strip(), (open(path).read() if os.path.exists(path) else "")[len(before):]

    def test_relayed_changes_wait_for_the_coordinator_fix_and_settle_on_its_receipt(self):  # #1871
        relay = self.relayed()
        code, first, added = self.disposition(relay)
        self.assertEqual((code, added), (0, "waiting: #12 fix id=%s\n" % relay))
        self.assertIn("crew: relay %s #12 %s r1 review changes: awaiting coordinator fix" % (relay, self.sha), first)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ben-7.jsonl")))  # no fix launched
        backstop = lambda: [a[len("inbox: "):] for c in self.calls()[before:] if c[0] == "send-keys"
                            for a in c if a.startswith("inbox: ")]
        before = len(self.calls())
        with mock.patch.dict(os.environ, self.env):
            for _ in range(10):  # omitted handoff: an unchanged fix wait is never re-typed
                self.lead.retry_pending(self.args, "ben-lead", recheck=True)
            self.assertNotIn(relay, [m["id"] for m in self.lead.actionable(self.state, "ben-lead")])
        self.assertEqual(backstop(), [])
        self.assertEqual(self.disposition(relay)[0::2], (0, "waiting: #12 fix id=%s\n" % relay))  # still pending
        with mock.patch.dict(os.environ, self.env):  # the watcher's next scan records the re-written wait's baseline
            self.assertNotIn(relay, [m["id"] for m in self.lead.actionable(self.state, "ben-lead")])
        findings = os.path.join(self.state, "verdicts", "pr12-%s-r1-review.md" % self.sha[:7])
        self.put(os.path.relpath(findings, self.state), "findings")
        with mock.patch.dict(os.environ, self.env):  # the coordinator's explicit fix: the only trigger
            self.assertEqual(self.lead.handoff(self.args, "builder", "fix", ["#12", self.sha, findings]), 0)
            self.assertIn(relay, [m["id"] for m in self.lead.actionable(self.state, "ben-lead")])  # same head wakes it
        fix = [m for m in self.lead.pending(self.state, "ben-lead") if m["kind"] == "fix"][0]
        self.ben_status("ack: %s\n" % fix["id"])
        self.assertEqual(self.disposition(relay)[0::2], (0, "waiting: #12 fix id=%s\n" % relay))  # not yet delivered
        r = self.crew("send", "ben-7", "fix", *fix["refs"], "--project", self.project)  # the lead delivers it
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.state, "inbox", "ben-7.jsonl")) as f:
            sent = [json.loads(line) for line in f]
        self.assertEqual([m["kind"] for m in sent], ["fix"])
        with mock.patch.dict(os.environ, self.env):
            self.assertNotIn(relay, [m["id"] for m in self.lead.actionable(self.state, "ben-lead")])  # re-parked
        self.ben_status("ack: %s\n" % sent[0]["id"], "ben-7")  # the worker's receipt
        with mock.patch.dict(os.environ, self.env):
            self.assertIn(relay, [m["id"] for m in self.lead.actionable(self.state, "ben-lead")])
        code, out, added = self.disposition(relay)
        self.assertEqual((code, added), (0, "done: %s\n" % relay))
        self.assertIn("fix delivered", out)
        with open(os.path.join(self.state, "inbox", "ben-7.jsonl")) as f:
            self.assertEqual(len(f.readlines()), 1)  # no second handoff
        self.assertEqual([m["id"] for m in self.lead.pending(self.state, "ben-lead")], [fix["id"]])
        if "--relay-transcript" in sys.argv:
            print(first + "\nomitted handoff: 10 backstops typed 0; relay still waiting\ncoordinator fix " + fix["id"] +
                  " woke the relay (same head); worker ack settled it:\n" + out + "\nworker fix messages: 1")

    def test_parked_relay_wakes_and_settles_when_its_fix_pass_is_spawned(self):  # #1871 r1: no worker inbox receipt
        relay = self.relayed()
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(self.lead.handoff(self.args, "builder", "fix", ["#12", self.sha, "findings"]), 0)
        fix = [m for m in self.lead.pending(self.state, "ben-lead") if m["kind"] == "fix"][0]
        self.ben_status("ack: %s\n" % fix["id"])
        self.assertEqual(self.disposition(relay)[0::2], (0, "waiting: #12 fix id=%s\n" % relay))
        actionable = lambda: [m["id"] for m in self.lead.actionable(self.state, "ben-lead")]
        with mock.patch.dict(os.environ, self.env):
            self.assertNotIn(relay, actionable())  # parked while the adopted fix pass awaits spawn
            rec = self.record("ben-7")  # the lead spawns the adopted PR's fix pass at the verdict head
            rec.update(head=self.sha, start="2099-01-01T00:00:00Z", args=dict(rec["args"], **{"pass": "fix", "pr": 12}))
            self.put("runs/ben-7.json", json.dumps(rec))
            self.assertIn(relay, actionable())
        code, out, added = self.disposition(relay)
        self.assertEqual((code, added), (0, "done: %s\n" % relay))
        self.assertIn("fix delivered", out)
        if "--relay-transcript" in sys.argv:
            print("parked relay: spawned fix pass woke it; " + out)

    def test_relay_disposition_table(self):  # #1871: one rule; every refusal beside its valid control
        relay = self.relayed()
        base = {p: open(os.path.join(self.state, p)).read() for p in
                ("status/ben-lead.status", "inbox/ben-lead.jsonl", "runs/ben-7.json")}
        event = [m for m in self.lead.pending(self.state, "ben-lead") if m["id"] == relay][0]["refs"][0]
        wake = open(event).read()
        later = "2099-01-01T00:00:00Z"

        def fix(window, head, acked, ts="2026-01-01T00:00:00Z"):
            def apply():
                with open(os.path.join(self.state, "inbox", window + ".jsonl"), "a") as f:
                    f.write(json.dumps(dict(id="f-" + window, kind="fix", refs=["#12", head], ts=ts)) + "\n")
                if acked:
                    self.ben_status("ack: f-%s\n" % window, window)
            return apply

        def live(**kv):
            return lambda: (self.live.update(kv), self.save())

        def spawned(head, start):
            def apply():
                rec = self.record("ben-7")
                rec.update(head=head, start=start, args=dict(rec["args"], **{"pass": "fix", "pr": 12}))
                self.put("runs/ben-7.json", json.dumps(rec))
            return apply

        def put(path, text):
            return lambda: self.put(path, text)

        waiting, done = "waiting: #12 fix id=%s\n" % relay, "done: %s\n" % relay
        other = "f" * 40
        rows = [  # (name, setup, msg id, exit, status lines added)
            ("valid relay, no fix: awaiting coordinator fix", [], relay, 0, waiting),
            ("held after relay: still awaiting", [live(labels=[{"name": "crew:hold"}])], relay, 0, waiting),
            ("coordinator fix at the lead only", [fix("ben-lead", self.sha, True)], relay, 0, waiting),
            ("worker copy unacknowledged", [fix("ben-7", self.sha, False)], relay, 0, waiting),
            ("worker fix at another head", [fix("ben-7", other, True)], relay, 0, waiting),
            ("worker received the fix (either order)", [fix("ben-7", self.sha, True)], relay, 0, done),
            ("fix pass spawned after the lead copy", [fix("ben-lead", self.sha, True), spawned(self.sha, later)],
             relay, 0, done),
            ("fix pass older than the lead copy", [fix("ben-lead", self.sha, True, later),
                                                   spawned(self.sha, "2026-01-01T00:00:00Z")], relay, 0, waiting),
            ("PR closed: superseded", [live(state="CLOSED")], relay, 0, done),
            ("head moved: superseded", [live(headRefOid=other)], relay, 0, done),
            ("refuse: unknown id", [], "nope", 2, ""),
            ("refuse: already done (replay)", [lambda: self.ben_status(done)], relay, 2, ""),
            ("refuse: unacknowledged", [put("status/ben-lead.status", "")], relay, 2, ""),
            ("refuse: event file missing", [lambda: os.remove(event)], relay, 2, ""),
            ("refuse: not a changes event", [put(os.path.relpath(event, self.state), wake.replace(
                "review changes", "review pass"))], relay, 2, ""),
            ("refuse: not a work event", [put("inbox/ben-lead.jsonl", base["inbox/ben-lead.jsonl"].replace(
                '"kind": "work"', '"kind": "build"'))], relay, 2, ""),
        ]
        for name, setup, msg_id, code, added in rows:
            with self.subTest(name):
                for path, text in base.items():
                    self.put(path, text)
                self.put(os.path.relpath(event, self.state), wake)
                for path in ("inbox/ben-7.jsonl", "status/ben-7.status"):
                    if os.path.exists(os.path.join(self.state, path)):
                        os.remove(os.path.join(self.state, path))
                self.live.update(state="OPEN", headRefOid=self.sha, labels=[])
                self.save()
                for step in setup:
                    step()
                got = self.disposition(msg_id)
                self.assertEqual((got[0], got[2]), (code, added), got[1])
                if "--relay-transcript" in sys.argv:
                    print("%-42s exit %d  %s" % (name, got[0], got[2].strip().split(" id=")[0].split(":")[0] or "-"))
                if code:
                    self.assertIn("refusing relay", got[1])
                    self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ben-7.jsonl")) and
                                     "f-ben-7" not in open(os.path.join(self.state, "inbox", "ben-7.jsonl")).read())

    def test_team_root_relay_and_fix_rows_stay_in_their_repo(self):  # #1871: foreign context, valid control beside it
        relay = self.relayed()
        team = os.path.join(self.tmp, "team")
        for rel in ("inbox/ben-lead.jsonl", "status/ben-lead.status"):
            os.makedirs(os.path.dirname(os.path.join(team, rel)), exist_ok=True)
            with open(os.path.join(self.state, rel)) as f:
                lines = [json.dumps(dict(json.loads(l), context={"repo": "acme/widgets"})) + "\n" if
                         rel.startswith("inbox") else l for l in f]
            with open(os.path.join(team, rel), "w") as f:
                f.writelines(lines + ([json.dumps(dict(id="f-other", kind="fix", refs=["#12", self.sha], ts="t",
                                                      context={"repo": "acme/other"})) + "\n"]
                                      if rel.startswith("inbox") else ["ack: f-other\n"]))
        args = argparse.Namespace(project=self.project, org_profile=None, refs=[relay])
        status = os.path.join(team, "status", "ben-lead.status")
        for repo, code, added, rows in (("acme/other", 2, "", ["f-other"]),
                                        ("acme/widgets", 0, "waiting: #12 fix id=%s\n" % relay, [])):
            with self.subTest(repo), mock.patch.dict(os.environ, self.env), \
                    mock.patch.object(self.lead, "lead_state", return_value=team), \
                    mock.patch.object(self.lead.team_module, "repo_of", return_value=repo):
                before = open(status).read()
                self.assertEqual(self.lead.relay(args), code)
                self.assertEqual(open(status).read()[len(before):], added)
                self.assertEqual([r[1] for r in self.lead.fixes(self.state, "12") if r[0] == "ben-lead"], rows)
                self.assertFalse(self.lead.delivered(self.state, "12", self.sha))  # a lead copy is never delivery

    def test_ci_jobs_without_steps_are_infra_never_green(self):
        poll = self.mod.commands()["poll"]
        self.live["statusCheckRollup"] = [dict(status="COMPLETED", conclusion="FAILURE", detailsUrl="https://github.com/acme/widgets/actions/runs/123/job/456")]
        with mock.patch.object(poll, "gh_json", return_value={"jobs": [{"steps": []}]}):
            poll.observe_ci(self.live, "acme/widgets")
        self.assertEqual(poll.pr_snapshot(self.live)["ci"], "infra")
        self.live["labels"] = [{"name": "crew:in-review"}]
        events, _ = poll.decide({"prs": {"12": {"head": self.sha, "ci": "pending"}}}, [self.live], [])
        self.assertEqual([(e["event"], e["consumer"]) for e in events], [("ci-infra", "coordinator")])
        self.live["statusCheckRollup"][0].pop("_ci_infra")
        with mock.patch.object(poll, "gh_json", return_value={"jobs": [{"steps": [{"name": "test"}]}]}):
            poll.observe_ci(self.live, "acme/widgets")
        self.assertEqual(poll.pr_snapshot(self.live)["ci"], "failed")


if __name__ == "__main__":
    names = [n for n in ReviewerPool.__dict__ if n.startswith("test_")]
    if "--transcript" in sys.argv:
        names = ["test_handoff_dispatch_complete_reclaim", "test_lead_restart_preserves_queue_and_live_worker"]
    if "--admission-transcript" in sys.argv:
        names = ["test_reviewer_floor_under_builder_load",
                 "test_review_held_by_builder_call_is_granted_on_next_reviewer_call",
                 "test_builder_completion_wakes_deferred_review"]
    if "--relay-transcript" in sys.argv:  # #1871
        names = ["test_relayed_changes_wait_for_the_coordinator_fix_and_settle_on_its_receipt",
                 "test_parked_relay_wakes_and_settles_when_its_fix_pass_is_spawned",
                 "test_relay_disposition_table", "test_team_root_relay_and_fix_rows_stay_in_their_repo"]
    if "--held-wait-transcript" in sys.argv:  # #1836
        names = ["test_held_ref_parks_with_a_dispatcher_wait_through_unchanged_hold",
                 "test_parked_ref_wakes_on_listed_changes_and_reparks"]
    if "--merge-up-transcript" in sys.argv:
        names = ["test_resolved_conflict_merge_up_starts_delta_review",
                 "test_semantic_conflict_fix_starts_delta_review",
                 "test_differing_patch_merge_up_starts_delta_review",
                 "test_identical_merge_up_keeps_synthesizer_portability"]
    result = unittest.TextTestRunner().run(unittest.TestSuite(ReviewerPool(n) for n in names))
    sys.exit(not result.wasSuccessful())
