"""Tests for mdstack poll, moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: the decision function on recorded `gh` JSON in `fixtures/poll/` (new-head ->
reviewer, ci-passed -> synthesizer, ci-failed -> builder, changes -> builder, approved -> synthesizer, merged ->
coordinator, no change -> nothing; `new-head` carries round `k`, reset by a cutover; an
evidence-only fix at the verdict head emits `fix-at-head` once; an intake `pass=ack` marker wakes nobody
and counts no round, #303) and `poll --once` against a fake `gh` (baseline, one wake record per change,
read-only calls); express routing (no reviewer event, `ci-passed` only with a selfgate pass at head,
`selfgate-passed` to the synthesizer, `new-head` on lane fallback, an unreadable resolution runs the crew lane, #672);
`gh` retries (a rate limit never retried but a `RateLimited` error until the quota's reset, #1300; a transient 5xx retried with bounded backoff, a persistent one a `Transient` error and
`--once` exit 75, a non-transient error never retried, other callers kept to one attempt, #702); the triage scan on
`fixtures/poll/triage-*.json` (each skip rule, owner replies, exact-key duplicate hints, card fields from the intake
template, P0 signals from defaults or a rules file, unreadable items and repos recorded, one wake per new P0, issue
reads only, off unless `triage.enabled`, #747); closed milestones queued after a baseline until a sweep takes them
(#374); a non-GitHub tracker scanned through its `tracker.list-items` binding per `triage.trackers` id, never `gh`,
and `poll --triage-only` on a session profile (#1404). Run in CI.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW, SCRIPTS, write_pack


POLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "poll")
HEAD = "1" * 40
# Fake gh: serves $FAKE_GH_DIR/{prs,issues,pr-<n>}.json for pr list / issue list / pr view; logs every call. A held
# ref's comments view without pr-<n>.json serves answers-<n>.json, else {} (#394).
FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    args, d = sys.argv[1:], os.environ["FAKE_GH_DIR"]
    with open(os.path.join(d, "gh.log"), "a") as f:
        f.write(json.dumps(args) + "\\n")
    name = ("job" if "/actions/jobs/" in args[1] else "commit" if "/commits/" in args[1] else "files" if "/files" in args[1]
            else "compare") if args[0] == "api" else (
        {("pr", "list"): "prs", ("issue", "list"): "issues"}.get(tuple(args[:2])) or args[0] + "-" + args[2])
    path = os.path.join(d, name + ".json")
    if not os.path.exists(path) and args[-1] in ("comments", "comments,reviews"):  # a held ref's owner answers (#394)
        path = os.path.join(d, "answers-" + args[2] + ".json") if os.path.exists(os.path.join(d, "answers-" + args[2] + ".json")) else os.devnull
    sys.stdout.write(open(path).read() or "{}")
    """)


def fixture(name):
    with open(os.path.join(POLL, name)) as f:
        return json.load(f)


def load_crew():
    from importlib.machinery import SourceFileLoader
    import importlib.util
    loader = SourceFileLoader("crew_cli", CREW)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
    loader.exec_module(mod)
    return mod


class PollDecide(unittest.TestCase):
    """The pure decision function on recorded gh JSON fixtures: each change is one event for one consumer."""

    @classmethod
    def setUpClass(cls):
        cls.crew = load_crew()

    def decide(self, before, after, issues_before="issues-none.json", issues_after="issues-none.json"):
        _, state = self.crew.decide({}, fixture(before), fixture(issues_before))
        return self.crew.decide(state, fixture(after), fixture(issues_after))

    def only(self, before, after, **kw):
        events, _ = self.decide(before, after, **kw)
        return [(e["event"], e["consumer"], e["refs"]) for e in events]

    def test_landing_markers_preserve_stops_until_matching_resume(self):
        def post(cmd, extra="", role="coordinator"):
            return {"body": "<!-- crew:v1 role=%s pass=steer cmd=%s %s -->" % (role, cmd, extra)}
        urgent = post("urgent", "cmd-id=u pr=171 sha=" + HEAD)
        reviews = [urgent, post("stop-landing", "cmd-id=a sha=" + HEAD),
                   post("stop-landing", "cmd-id=b"), post("resume-landing", "stop-id=unknown"),
                   post("resume-landing", "stop-id=a"), post("resume-landing", "stop-id=b", role="builder")]
        result = self.crew.landing_steers(reviews)
        self.assertEqual(result["stops"], ["b"])
        self.assertEqual(result["urgent"][0]["sha"], HEAD)
        self.assertEqual(self.crew.landing_steers(reviews + [post("resume-landing", "stop-id=b")])["stops"], [])
        self.assertEqual(self.crew.pr_snapshot({"headRefOid": HEAD, "reviews": [urgent],
                                              "statusCheckRollup": []})["verdict"], None)

    def test_ci_passed_to_synthesizer_only(self):
        self.assertEqual(self.only("prs-pending.json", "prs-ci-passed.json"),
                         [("ci-passed", "synthesizer", ["#171", HEAD])])

    def test_ci_failed_to_builder(self):
        self.assertEqual(self.only("prs-pending.json", "prs-ci-failed.json"),
                         [("ci-failed", "builder", ["#171", HEAD])])

    def test_missing_expected_check_never_reads_green(self):  # #1536
        required = ("markdownlint", "links", "repo-guard")
        green = fixture("prs-ci-passed.json")
        partial = json.loads(json.dumps(green))
        partial[0]["statusCheckRollup"] = [c for c in green[0]["statusCheckRollup"] if c["name"] == "links"]
        _, before = self.crew.decide({}, fixture("prs-pending.json"), [], required=required)
        events, state = self.crew.decide(before, partial, [], required=required)
        self.assertEqual((events, state["prs"]["171"]["ci"]), ([], "pending"))
        self.assertEqual(self.crew.missing_checks(partial[0]["statusCheckRollup"], required), ["markdownlint", "repo-guard"])
        self.assertEqual(self.crew.decide(before, partial, [])[1]["prs"]["171"]["ci"], "passed")  # no baseline: legacy
        events, _ = self.crew.decide(state, green, [], required=required)  # late registration completes the set
        self.assertEqual([(e["event"], e["refs"]) for e in events], [("ci-passed", ["#171", HEAD])])
        optional = json.loads(json.dumps(green))  # a check outside the baseline (lab) stays optional
        optional[0]["statusCheckRollup"].append({"__typename": "CheckRun", "name": "lab", "status": "COMPLETED",
                                                  "conclusion": "SKIPPED"})
        self.assertEqual(self.crew.pr_snapshot(optional[0], required)["ci"], "passed")
        self.assertEqual(self.crew.pr_snapshot(green[0], required + ("lab",))["ci"], "pending")
        partial[0]["statusCheckRollup"][0]["conclusion"] = "FAILURE"
        self.assertEqual(self.crew.pr_snapshot(partial[0], required)["ci"], "failed")
        context = {"headRefOid": HEAD, "reviews": [], "statusCheckRollup": [
            {"__typename": "StatusContext", "context": "repo-guard", "state": "SUCCESS"}]}
        self.assertEqual(self.crew.pr_snapshot(context, ("repo-guard",))["ci"], "passed")
        self.assertEqual(self.crew.required_checks({"ci.required_checks": list(required)}), required)
        self.assertEqual(self.crew.required_checks({}), ())

    def test_zero_step_failure_emits_infra_once_and_never_green(self):
        prs = fixture("prs-ci-failed.json")
        for check in prs[0]["statusCheckRollup"]:
            if check.get("conclusion") == "FAILURE":
                check["steps"] = []
        _, before = self.crew.decide({}, fixture("prs-pending.json"), [])
        events, state = self.crew.decide(before, prs, [])
        self.assertEqual([(e["event"], e["consumer"]) for e in events], [("ci-infra", "coordinator")])
        self.assertEqual(state["prs"]["171"]["ci"], "infra")
        self.assertEqual(self.crew.decide(state, prs, [])[0], [])
        prs[0]["statusCheckRollup"].append({"status": "COMPLETED", "conclusion": "FAILURE", "steps": [{}]})
        self.assertEqual(self.crew.pr_snapshot(prs[0])["ci"], "failed")

    def test_held_lists_owner_blocked_prs_their_issues_and_held_issues(self):  # #394
        prs = fixture("prs-pending.json")
        prs[0]["labels"] = [{"name": "crew:in-review"}]
        self.assertEqual(self.crew.decide({}, prs, [])[1]["held"], [])
        prs[0]["labels"] = [{"name": "crew:in-review"}, {"name": "crew:hold"}]
        prs[0]["closingIssuesReferences"] = [{"number": 41}]
        ready = {"assignees": [{"login": "a"}], "labels": [{"name": "crew:ready"}, {"name": "crew:needs-md"}]}
        issues = [dict(ready, number=9), dict(ready, number=10, labels=[{"name": "crew:ready"}])]
        events, state = self.crew.decide({}, prs, issues)
        self.assertEqual(state["held"], ["#9", "#41", "#171"])
        self.assertNotIn("held", [e["event"] for e in events])  # a hold label alone emits no wake
        closed = dict(prs[0], state="CLOSED")
        self.assertEqual(self.crew.decide(state, [closed], [])[1]["held"], [])

    def test_owner_unhold_is_one_prompt_coordinator_wake(self):  # #394
        prs = fixture("prs-pending.json")
        prs[0]["labels"] = [{"name": "crew:in-review"}, {"name": "crew:hold"}]
        ready = {"assignees": [{"login": "a"}], "number": 9, "labels": [{"name": "crew:ready"}, {"name": "crew:needs-md"}]}
        _, state = self.crew.decide({}, prs, [ready])
        self.assertEqual(state["held"], ["#9", "#171"])
        self.assertEqual(self.crew.decide(state, prs, [ready])[0], [])  # still held: no wake
        prs[0]["labels"] = [{"name": "crew:in-review"}]  # only the label changes; head, CI and verdict do not
        ready["labels"] = [{"name": "crew:ready"}]
        events, after = self.crew.decide(state, prs, [ready])
        self.assertEqual([(e["event"], e["consumer"], e["refs"]) for e in events],
                         [("hold-released", "coordinator", ["#9", "#171"])])
        self.assertEqual(after["held"], [])
        closed = dict(prs[0], state="CLOSED", labels=[{"name": "crew:hold"}])
        self.assertEqual([e["event"] for e in self.crew.decide(state, [closed], [])[0]], ["pr-closed"])  # gone, not unheld

    def test_owner_comment_on_a_held_pr_is_one_prompt_wake_and_keeps_the_hold(self):  # #394
        prs = fixture("prs-pending.json")
        prs[0]["labels"] = [{"name": "crew:in-review"}, {"name": "crew:hold"}]
        _, state = self.crew.decide({}, prs, [], answers={"#171": 0})
        self.assertEqual(self.crew.decide(state, prs, [], answers={"#171": 0})[0], [])  # no answer yet: no wake
        events, after = self.crew.decide(state, prs, [], answers={"#171": 1})  # only an owner comment changed
        self.assertEqual([(e["event"], e["consumer"], e["refs"]) for e in events], [("owner-answer", "coordinator", ["#171"])])
        self.assertEqual((after["held"], after["answers"]), (["#171"], {"#171": 1}))  # the hold stays for reconciliation
        self.assertEqual(self.crew.decide(after, prs, [], answers={"#171": 1})[0], [])  # once per answer

    def test_owner_comment_on_an_asked_item_without_a_hold_label_wakes(self):  # #394
        prs = fixture("prs-pending.json")
        prs[0]["labels"] = [{"name": "crew:in-review"}]  # parked by an open ask only
        _, state = self.crew.decide({}, prs, [], answers={"#171": 0})
        self.assertEqual((state["held"], state["answers"]), ([], {"#171": 0}))
        events, after = self.crew.decide(state, prs, [], answers={"#171": 1})
        self.assertEqual([(e["event"], e["refs"]) for e in events], [("owner-answer", ["#171"])])
        self.assertEqual(self.crew.owner_answers(prs, [], {"mw"}, lambda kind, n, fields: {"comments": []}, [171]),
                         {"#171": 0})  # an asked ref is read with no hold label

    def test_owner_answers_reads_only_held_items_and_counts_owner_posts(self):  # #394
        prs = fixture("prs-pending.json")
        prs[0]["labels"], prs[0]["closingIssuesReferences"] = [{"name": "crew:hold"}], [{"number": 41}]
        reads, owner, bot = [], {"author": {"login": "mw"}}, {"author": {"login": "crew-bot"}}
        posts = {171: {"comments": [owner, bot], "reviews": [owner]}, 41: {"comments": [bot]}}

        def read(kind, n, fields):
            reads.append((kind, n, fields))
            return posts[n]
        self.assertEqual(self.crew.owner_answers(prs, [], {"mw"}, read), {"#41": 0, "#171": 2})
        self.assertEqual(reads, [("issue", 41, ["comments"]), ("pr", 171, ["comments", "reviews"])])  # PR #300 is not held: unread

    def test_changes_verdict_to_builder(self):
        self.assertEqual(self.only("prs-ci-passed.json", "prs-changes.json"),
                         [("review-changes-requested", "builder", ["#171", HEAD])])

    def test_pass_verdict_to_synthesizer(self):
        self.assertEqual(self.only("prs-ci-passed.json", "prs-approved.json"),
                         [("review-approved", "synthesizer", ["#171", HEAD])])

    def test_merged_to_coordinator_and_dropped(self):
        _, state = self.crew.decide({}, fixture("prs-approved.json"), [])
        events, state = self.crew.decide(state, fixture("prs-none.json") + [fixture("pr-171-merged.json")], [])
        self.assertEqual([(e["event"], e["consumer"]) for e in events], [("pr-merged", "coordinator")])
        self.assertNotIn("171", state["prs"])
        closed = dict(fixture("pr-171-merged.json"), state="CLOSED")
        self.assertEqual([e["event"] for e in self.crew.decide({"prs": {"171": {}}}, [closed], [])[0]], ["pr-closed"])

    def test_no_change_nothing(self):
        for name in ["prs-pending.json", "prs-ci-passed.json", "prs-ci-failed.json", "prs-changes.json",
                     "prs-approved.json"]:
            self.assertEqual(self.only(name, name, issues_before="issues-ready.json",
                                       issues_after="issues-ready.json"), [], name)

    def test_assigned_ready_issue_to_builder(self):
        self.assertEqual(self.only("prs-pending.json", "prs-pending.json", issues_after="issues-ready.json"),
                         [("issue-assigned", "builder", ["#134"])])

    def test_hidden_marker_at_head_only_and_non_crew_pr_ignored(self):
        _, state = self.crew.decide({}, fixture("prs-ci-passed.json"), [])
        self.assertEqual(state["prs"], {"171": {"head": HEAD, "ci": "passed", "verdict": None, "round": 1,
                                                "fixed": False, "selfgate": None,
                                                "verdict_identity": None, "verdict_review_id": None, "notes": [],
                                                "merge_ok_identity": None}})

    def test_every_event_has_exactly_one_consumer(self):
        self.assertEqual(sorted(self.crew.CONSUMER), sorted(["new-head", "ci-passed", "ci-failed", "ci-infra", "review-changes-requested",
                                                             "review-approved", "pr-merged", "pr-closed",
                                                             "issue-assigned", "fix-at-head", "merge-up",
                                                             "selfgate-passed", "pr-conflicting", "hold-released", "owner-answer",
                                                             "merge-ok-recorded"]))
        self.assertTrue(all(isinstance(v, str) for v in self.crew.CONSUMER.values()))


    def test_conflict_at_unchanged_head_wakes_builder_once_per_head_and_conflict(self):  # #1398
        def poll(state, mergeable, head=HEAD, verdict=True):
            prs = fixture("prs-approved.json" if verdict else "prs-pending.json")
            prs[0].update(mergeable=mergeable, headRefOid=head)
            events, state = self.crew.decide(state, prs, [])
            return [(e["event"], e["consumer"], e["refs"]) for e in events if e["event"] == "pr-conflicting"], state
        _, state = poll({}, "MERGEABLE")
        hit = [("pr-conflicting", "builder", ["#171", HEAD])]
        events, state = poll(state, "CONFLICTING")  # another land made the approved head conflict, no checks yet
        self.assertEqual(events, hit)
        for mergeable in ("CONFLICTING", "UNKNOWN", "CONFLICTING", None):  # repeats and UNKNOWN never multiply
            events, state = poll(state, mergeable)
            self.assertEqual(events, [], mergeable)
        self.assertEqual(state["prs"]["171"]["mergeable"], "CONFLICTING")
        events, state = poll(state, "MERGEABLE")
        self.assertEqual((events, state["prs"]["171"]["mergeable"]), ([], "MERGEABLE"))
        self.assertEqual(poll(state, "CONFLICTING")[0], hit)  # resolved, then conflicting again: a new handoff
        self.assertEqual(poll(state, "UNKNOWN")[0], [])  # UNKNOWN is not a conflict
        new = "b" * 40
        events, state = poll(state, "CONFLICTING", head=new, verdict=False)
        self.assertEqual(events, [("pr-conflicting", "builder", ["#171", new])])
        self.assertNotIn("mergeable", poll({}, "UNKNOWN", head=new)[1]["prs"]["171"])

    def marked(self, name, *markers, at=None):
        """A fixture with one more review (or one inserted at index at) holding the given crew:v1 lines."""
        prs = fixture(name)
        review = {"body": "".join("<!-- crew:v1 %s -->\n" % m for m in markers)}
        prs[0]["reviews"].insert(len(prs[0]["reviews"]) if at is None else at, review)
        return prs

    def test_opened_and_pushed_heads_start_review_without_ci(self):
        for ci in ("prs-pending.json", "prs-ci-failed.json", "prs-ci-passed.json"):
            prs = fixture(ci)
            events, state = self.crew.decide({}, prs, [])
            self.assertEqual(events[0], {"event": "new-head", "consumer": "reviewer",
                                         "refs": ["#171", HEAD], "round": 1})
            self.assertEqual(self.crew.decide(state, prs, [])[0], [])
            prs[0]["headRefOid"] = "2" * 40
            events, _ = self.crew.decide(state, prs, [])
            self.assertEqual(events[0]["event"], "new-head")
            self.assertEqual(events[0]["refs"], ["#171", "2" * 40])
            self.assertEqual(sum(e["consumer"] == "reviewer" for e in events), 1)

    def express(self, prev, prs):
        events, state = self.crew.decide(prev, prs, [], express={"171"})
        return [(e["event"], e["consumer"]) for e in events], state

    def test_express_skips_reviewers_and_routes_selfgate_and_ci_to_synthesizer(self):  # #672
        selfgate = "role=builder pass=selfgate pr=171 sha=%s verdict=pass" % HEAD
        self.assertEqual(self.express({}, fixture("prs-pending.json"))[0], [])
        _, state = self.express({}, fixture("prs-ci-passed.json"))  # CI green alone wakes nobody
        self.assertEqual(state["prs"]["171"]["express"], True)
        events, state = self.express(state, self.marked("prs-ci-passed.json", selfgate))
        self.assertEqual(events, [("selfgate-passed", "synthesizer")])
        self.assertEqual(self.express(state, self.marked("prs-ci-passed.json", selfgate))[0], [])
        _, state = self.express({}, self.marked("prs-pending.json", selfgate))
        self.assertEqual(self.express(state, self.marked("prs-ci-passed.json", selfgate))[0], [("ci-passed", "synthesizer")])
        self.assertEqual(self.express({}, fixture("prs-ci-failed.json"))[0], [("ci-failed", "builder")])
        stale = "role=builder pass=selfgate pr=171 sha=%s verdict=pass" % ("0" * 40)
        self.assertEqual(self.express({}, self.marked("prs-ci-passed.json", stale))[0], [])
        changes = selfgate.replace("verdict=pass", "verdict=changes")
        self.assertEqual(self.express({}, self.marked("prs-ci-passed.json", changes))[0], [])

    def test_express_evidence_only_fix_wakes_no_reviewer(self):  # #672 r1: a changes verdict from before the lane
        changes = "role=reviewer-validator pass=verdict pr=171 sha=%s round=1 verdict=changes" % HEAD
        _, state = self.express({}, self.marked("prs-ci-passed.json", changes))
        fix = "role=builder pass=fix pr=171 sha=%s" % HEAD
        self.assertEqual(self.express(state, self.marked("prs-ci-passed.json", changes, fix))[0], [])

    def test_express_merge_up_carries_the_selfgate_to_ci_passed(self):  # #672 r2
        selfgate = "role=builder pass=selfgate pr=171 sha=%s verdict=pass" % HEAD
        _, state = self.express({}, self.marked("prs-ci-passed.json", selfgate))
        merged = self.marked("prs-pending.json", selfgate)
        merged[0]["headRefOid"] = "3" * 40
        events, state = self.crew.decide(state, merged, [], {"171": {"head": HEAD, "round": 1}}, express={"171"})
        self.assertEqual([(e["event"], e["consumer"], e.get("previous_head")) for e in events],
                         [("merge-up", "synthesizer", HEAD)])
        green = self.marked("prs-ci-passed.json", selfgate)
        green[0]["headRefOid"] = "3" * 40
        self.assertEqual(self.express(state, green)[0], [("ci-passed", "synthesizer")])
        _, state = self.express(state, green)
        self.assertEqual(self.express(state, green)[0], [])  # an idle poll at the carried head wakes nobody

    def test_express_fallback_emits_new_head_once(self):  # #672: the coordinator then hands normal review
        _, state = self.express({}, fixture("prs-pending.json"))
        events, state = self.crew.decide(state, fixture("prs-pending.json"), [])
        self.assertEqual(events, [{"event": "new-head", "consumer": "reviewer", "refs": ["#171", HEAD], "round": 1}])
        self.assertEqual(self.crew.decide(state, fixture("prs-pending.json"), [])[0], [])

    def test_new_head_carries_round_k(self):  # #139 F21
        old = "role=reviewer-validator pass=verdict pr=171 sha=%s round=1 verdict=changes" % ("2" * 40)
        prs = self.marked("prs-pending.json", old)
        events, _ = self.crew.decide({}, prs, [])
        self.assertEqual((events[0]["event"], events[0]["round"]), ("new-head", 2))
        cut = self.marked("prs-pending.json", old, "role=coordinator pass=cutover pr=171 sha=%s round=n/a "
                          "verdict=n/a" % HEAD)
        self.assertEqual(self.crew.decide({}, cut, [])[0][0]["round"], 1)  # §5: counted after a cutover

    VALUES = {"identities.coordinator.gh_user": "acme-bot", "identities.coordinator.name": "Ash",
              "identities.reviewer.gh_user": "acme-reviewer", "identities.reviewer.name": "Vera"}

    @staticmethod
    def post(marker, login, name):
        return {"author": {"login": login}, "body": "<!-- crew:v1 %s -->\n— %s (Role) · codex · m" % (marker, name)}

    MERGE_OK = "role=coordinator pass=steer pr=171 sha=%s round=n/a verdict=n/a cmd=merge-ok cmd-id=chat"

    def permission(self, state, *reviews, head=HEAD, ci="prs-ci-passed.json"):
        """One poll of PR #171 at head with the given extra reviews and repo values: (events, state) (#1835)."""
        prs = fixture(ci)
        prs[0].update(headRefOid=head, reviews=prs[0]["reviews"] + list(reviews))
        values = dict(self.VALUES, **{"repo.owner": "acme", "repo.name": "widgets"})
        events, state = self.crew.decide(state, prs, [], values=values)
        return [(e["event"], e["consumer"], e["refs"]) for e in events], state

    def test_merge_ok_after_green_ci_wakes_the_synthesizer_once(self):  # #1835
        _, state = self.permission({})
        events, state = self.permission(state)  # the green head's ci-passed is already consumed
        self.assertEqual((events, state["prs"]["171"]["ci"]), ([], "passed"))
        ok = self.post(self.MERGE_OK % HEAD, "acme-bot", "Ash")
        events, state = self.permission(state, ok)
        self.assertEqual(events, [("merge-ok-recorded", "synthesizer", ["#171", HEAD])])
        self.assertEqual(state["prs"]["171"]["merge_ok_identity"], ["acme/widgets", "#171", HEAD, "merge-ok"])
        self.assertEqual(self.permission(state, ok)[0], [])  # unchanged poll
        copy = self.post(self.MERGE_OK.replace("chat", "again") % HEAD, "acme-bot", "Ash")
        self.assertEqual(self.permission(state, ok, copy)[0], [])  # a duplicate copy of the same identity
        new = "2" * 40
        events, moved = self.permission(state, ok, head=new)  # never carried across heads
        self.assertEqual((events, moved["prs"]["171"]["merge_ok_identity"]), (
            [("new-head", "reviewer", ["#171", new]), ("ci-passed", "synthesizer", ["#171", new])], None))
        events, _ = self.permission(moved, ok, self.post(self.MERGE_OK % new, "acme-bot", "Ash"), head=new)
        self.assertEqual(events, [("merge-ok-recorded", "synthesizer", ["#171", new])])

    def test_merge_ok_before_ci_wakes_and_ci_still_follows(self):  # #1835
        _, state = self.permission({}, ci="prs-pending.json")
        ok = self.post(self.MERGE_OK % HEAD, "acme-bot", "Ash")
        events, state = self.permission(state, ok, ci="prs-pending.json")
        self.assertEqual(events, [("merge-ok-recorded", "synthesizer", ["#171", HEAD])])
        events, _ = self.permission(state, ok)
        self.assertEqual(events, [("ci-passed", "synthesizer", ["#171", HEAD])])

    def test_unauthenticated_or_misplaced_merge_ok_wakes_nobody(self):  # #1835
        _, state = self.permission({})
        for case, review in (
                ("prose", {"author": {"login": "acme-bot"}, "body": "merge-ok\n— 🔥 Ash (CTO) · codex · m"}),
                ("other author", self.post(self.MERGE_OK % HEAD, "someone", "Ash")),
                ("unsigned", {"author": {"login": "acme-bot"}, "body": "<!-- crew:v1 %s -->" % (self.MERGE_OK % HEAD)}),
                ("other runtime", self.post(self.MERGE_OK % HEAD, "acme-bot", "Rex")),
                ("other role", self.post((self.MERGE_OK % HEAD).replace("coordinator", "builder"), "acme-bot", "Ash")),
                ("other head", self.post(self.MERGE_OK % ("f" * 40), "acme-bot", "Ash")),
                ("short head", self.post(self.MERGE_OK % HEAD[:7], "acme-bot", "Ash")),
                ("other PR", self.post((self.MERGE_OK % HEAD).replace("pr=171", "pr=172"), "acme-bot", "Ash")),
                ("malformed", self.post("role=coordinator pass=steer cmd=merge-ok sha", "acme-bot", "Ash"))):
            with self.subTest(case=case):
                events, after = self.permission(state, review)
                self.assertEqual((events, after["prs"]["171"]["merge_ok_identity"]), ([], None))
        prs = fixture("prs-ci-passed.json")  # utility mode (no profile values) authenticates nothing
        prs[0]["reviews"].append(self.post(self.MERGE_OK % HEAD, "acme-bot", "Ash"))
        self.assertEqual(self.crew.decide(state, prs, [])[0], [])

    def test_legacy_state_seeds_merge_ok_quietly(self):  # #1835: restart keeps it, a new PR entry wakes
        ok = self.post(self.MERGE_OK % HEAD, "acme-bot", "Ash")
        _, state = self.permission({}, ok)
        legacy = json.loads(json.dumps(state))
        del legacy["prs"]["171"]["merge_ok_identity"]
        events, seeded = self.permission(legacy, ok)
        self.assertEqual((events, seeded), ([], state))
        self.assertEqual(self.permission(seeded, ok)[0], [])
        events, _ = self.permission({"prs": {}}, ok)
        self.assertIn(("merge-ok-recorded", "synthesizer", ["#171", HEAD]), events)

    def resumed_round(self, *tail):
        """Round k of a new head after three own changes verdicts, an escalation and tail, with the profile values."""
        prs = fixture("prs-pending.json")
        prs[0]["reviews"] = [self.post("role=reviewer-validator pass=verdict pr=171 sha=%s round=%d verdict=changes"
                                       % (str(k) * 40, k), "acme-reviewer", "Vera") for k in (2, 3, 4)]
        prs[0]["reviews"] += [self.post("role=reviewer-validator pass=escalation pr=171 sha=%s round=3 verdict=n/a"
                                        % ("4" * 40), "acme-reviewer", "Vera"), *tail]
        return self.crew.decide({}, prs, [], values=self.VALUES)[0][0]["round"]

    def test_round_counts_after_canonical_steer_resume(self):  # #1005: protocol §5 and §9
        def steer(cmd, login="acme-bot", name="Ash", role="coordinator"):
            return self.post("role=%s pass=steer pr=171 sha=%s round=n/a verdict=n/a cmd=%s cmd-id=chat"
                             % (role, "4" * 40, cmd), login, name)
        changes = self.post("role=reviewer-validator pass=verdict pr=171 sha=%s round=1 verdict=changes" % ("5" * 40),
                            "acme-reviewer", "Vera")
        self.assertEqual(self.resumed_round(), 4)
        for cmd in ("resume", "cutover"):
            self.assertEqual(self.resumed_round(steer(cmd)), 1, cmd)
            self.assertEqual(self.resumed_round(steer(cmd), changes), 2, cmd)  # the next changes verdict is round 2
        for legacy in ("resume", "cutover"):  # supported legacy reset records still reset
            self.assertEqual(self.resumed_round(self.post("role=coordinator pass=%s pr=171 sha=%s round=n/a verdict=n/a"
                                                          % (legacy, "4" * 40), "acme-bot", "Ash")), 1, legacy)
        no_reset = {
            "builder note": self.post("role=builder pass=fix pr=171 sha=%s round=3 verdict=n/a" % HEAD, "acme-bot", "Ben"),
            "merge-ok steer": steer("merge-ok"),
            "rereview steer": steer("rereview"),
            "builder pass=resume": self.post("role=builder pass=resume pr=171 sha=%s" % HEAD, "acme-bot", "Ben"),
            "reviewer steer resume": steer("resume", "acme-reviewer", "Vera", role="reviewer-validator"),
            "foreign login": steer("resume", login="someone"),
            "foreign coordinator": steer("resume", name="Zed"),
            "ownership handoff": self.post("role=coordinator pass=handoff handoff=h1 state=acked from=a to=b cmd-id=c "
                                           "sha=%s round=n/a verdict=n/a" % ("9" * 40), "acme-bot", "Ash"),
            "foreign changes": self.post("role=reviewer-validator pass=verdict pr=171 sha=%s round=1 verdict=changes"
                                         % ("5" * 40), "acme-bot", "Ash"),
        }
        for why, post in no_reset.items():
            self.assertEqual(self.resumed_round(post), 4, why)

    def verdict_post(self, round, verdict="changes", review_id="R1", **extra):
        post = self.post("role=reviewer-validator pass=verdict pr=171 sha=%s round=%s verdict=%s"
                         % (HEAD, round, verdict), "acme-reviewer", "Vera")
        return dict(post, id=review_id, **extra)

    def verdict_poll(self, state, *posts):
        prs = fixture("prs-ci-passed.json")
        prs[0]["reviews"] = list(posts)
        return self.crew.decide(state, prs, [], values=self.VALUES)

    def test_same_head_new_posted_round_wakes_once_without_reviewer_dispatch(self):
        first, later = self.verdict_post(2), self.verdict_post(4, review_id="R2")
        _, state = self.verdict_poll({}, first)
        events, state = self.verdict_poll(state, first, later)
        self.assertEqual(events, [{"event": "review-changes-requested", "consumer": "builder",
                                   "refs": ["#171", HEAD]}])
        self.assertEqual(state["prs"]["171"]["verdict_identity"], [HEAD, "legacy", "4", "changes"])
        self.assertEqual(state["prs"]["171"]["round"], 3)  # next dispatch, not posted round 4
        self.assertEqual(self.verdict_poll(state, first, later)[0], [])
        passed = self.verdict_post(5, "pass", "R3")
        events, state = self.verdict_poll(state, first, later, passed)
        self.assertEqual(events, [{"event": "review-approved", "consumer": "synthesizer",
                                   "refs": ["#171", HEAD]}])
        self.assertEqual(self.verdict_poll(state, first, later, passed)[0], [])
        next_pass = self.verdict_post(6, "pass", "R4")
        self.assertEqual(self.verdict_poll(state, first, later, passed, next_pass)[0], events)

    def test_duplicate_posts_keep_canonical_provenance_and_formal_round_count(self):
        first = self.verdict_post(2)
        _, state = self.verdict_poll({}, first)
        duplicate = self.verdict_post(2, review_id="duplicate")
        for posts in ((first, first), (first, duplicate), (first, duplicate, duplicate)):
            events, current = self.verdict_poll(state, *posts)
            self.assertEqual(events, [])
            self.assertEqual(current["prs"]["171"]["verdict_review_id"], "R1")
            self.assertEqual(current["prs"]["171"]["round"], 1 + len(posts))
        later = self.verdict_post(4, review_id="R2")
        _, state = self.verdict_poll(state, first, later)
        self.assertEqual(self.verdict_poll(state, first, later, duplicate)[0], [])
        fix = self.post("role=builder pass=fix pr=171 sha=%s round=4 verdict=n/a" % HEAD,
                        "acme-bot", "Ben")
        events, state = self.verdict_poll(state, first, later, fix)
        self.assertEqual([e["event"] for e in events], ["fix-at-head"])
        self.assertEqual(self.verdict_poll(state, first, later, fix, dict(later, id="R3"))[0], [])
        self.assertEqual(state["prs"]["171"]["verdict_review_id"], "R2")

    def test_only_valid_signed_current_head_verdicts_change_identity(self):
        first = self.verdict_post(2)
        _, state = self.verdict_poll({}, first)
        good = self.verdict_post(4, review_id="R2")
        wrong = [dict(good, author={"login": "someone"}),
                 dict(good, body=good["body"].split("\n—")[0]),
                 dict(good, body=good["body"].replace("Vera (", "Zed (")),
                 dict(good, body=good["body"].replace(HEAD, "0" * 40))]
        wrong += [dict(good, body=good["body"].replace("pass=verdict", "pass=" + kind))
                  for kind in ("ack", "review", "validate", "fix")]
        wrong += [dict(good, body=good["body"].replace("round=4", "round=" + value))
                  for value in ("n/a", "0", "-1", "4x")]
        wrong.append(dict(good, body=good["body"].replace("verdict=changes", "verdict=n/a")))
        for post in wrong:
            with self.subTest(post=post):
                events, current = self.verdict_poll(state, first, post)
                self.assertEqual(events, [])
                self.assertEqual(current["prs"]["171"]["verdict_identity"], state["prs"]["171"]["verdict_identity"])
        self.assertIsNone(self.verdict_poll({}, *wrong)[1]["prs"]["171"]["verdict"])

    def test_utility_mode_preserves_roundless_and_latest_verdict_selection(self):
        prs = fixture("prs-ci-passed.json")
        first = self.verdict_post(2)
        first["body"] = first["body"].replace(" round=2", "")
        later = dict(first, id="R2", body=first["body"].replace("verdict=changes", "verdict=pass"))
        for posts, expected in (([first], "changes"), ([first, later], "pass"),
                                ([first, later, first], "changes")):
            prs[0]["reviews"] = posts
            self.assertEqual(self.crew.pr_snapshot(prs[0])["verdict"], expected)
            self.assertIsNone(self.crew.pr_snapshot(prs[0], values=self.VALUES)["verdict"])
        rounded = self.verdict_post(3, "pass", "R3")
        prs[0]["reviews"] = [rounded, self.verdict_post(4), rounded]
        self.assertEqual(self.crew.pr_snapshot(prs[0])["verdict"], "pass")

    def test_signed_reset_source_makes_reused_round_a_new_epoch(self):
        first = self.verdict_post(2)
        for mode in ("steer cmd=resume", "steer cmd=cutover", "resume", "cutover"):
            reset = dict(self.post("role=coordinator pass=%s pr=171 sha=%s" % (mode, HEAD),
                                   "acme-bot", "Ash"), id="reset-1")
            _, state = self.verdict_poll({}, first)
            events, state = self.verdict_poll(state, first, reset)
            self.assertEqual(events, [])  # reset alone is not a new verdict
            later = self.verdict_post(2, review_id="R2")
            events, state = self.verdict_poll(state, first, reset, later)
            self.assertEqual([e["event"] for e in events], ["review-changes-requested"])
            self.assertEqual(state["prs"]["171"]["verdict_identity"], [HEAD, "reset-1", "2", "changes"])
            self.assertEqual(state["prs"]["171"]["round"], 2)
            self.assertEqual(self.verdict_poll(state, first, reset, later)[0], [])
            reset2 = dict(reset, id="reset-2")
            self.assertEqual([e["event"] for e in self.verdict_poll(state, first, reset, later, reset2, later)[0]],
                             ["review-changes-requested"])
        for reset in (dict(reset, author={"login": "someone"}),
                      dict(reset, body=reset["body"].replace("Ash (", "Zed ("))):
            _, state = self.verdict_poll({}, first)
            self.assertEqual(self.verdict_poll(state, first, reset, first)[0], [])

    def test_legacy_state_seeds_without_replay_and_detects_first_new_round(self):
        first, later = self.verdict_post(2), self.verdict_post(4, review_id="R2")
        _, state = self.verdict_poll({}, first)
        legacy = json.loads(json.dumps(state))
        for key in ("verdict_identity", "verdict_review_id"):
            del legacy["prs"]["171"][key]
        events, seeded = self.verdict_poll(legacy, first)
        self.assertEqual(events, [])
        self.assertEqual(seeded["prs"]["171"]["verdict_review_id"], "R1")
        self.assertEqual(self.verdict_poll(seeded, first)[0], [])
        self.assertEqual([e["event"] for e in self.verdict_poll(legacy, first, later)[0]],
                         ["review-changes-requested"])
        for verdict, head in (("pass", HEAD), ("changes", "2" * 40)):
            post = dict(later, body=later["body"].replace("verdict=changes", "verdict=" + verdict))
            prs = fixture("prs-ci-passed.json")
            prs[0].update(headRefOid=head, reviews=[post])
            if head != HEAD:
                prs[0]["reviews"][0]["body"] = post["body"].replace(HEAD, head)
            events, _ = self.crew.decide(legacy, prs, [], values=self.VALUES)
            self.assertIn("review-approved" if verdict == "pass" else "review-changes-requested",
                          [e["event"] for e in events])

    def test_evidence_only_fix_at_same_head_wakes_reviewer_once(self):  # #139 B2
        fix = "role=builder pass=fix pr=171 sha=%s round=1 verdict=n/a engine=codex model=m effort=e" % HEAD
        _, state = self.crew.decide({}, fixture("prs-changes.json"), [])
        events, state = self.crew.decide(state, self.marked("prs-changes.json", fix), [])
        self.assertEqual([(e["event"], e["consumer"], e["refs"], e["round"]) for e in events],
                         [("fix-at-head", "reviewer", ["#171", HEAD], 2)])
        self.assertEqual(self.crew.decide(state, self.marked("prs-changes.json", fix), [])[0], [])
        _, state = self.crew.decide({}, fixture("prs-changes.json"), [])
        early = self.marked("prs-changes.json", fix, at=2)  # a fix note older than the verdict at head
        self.assertEqual(self.crew.decide(state, early, [])[0], [])

    def test_intake_ack_wakes_nobody_and_counts_no_round(self):  # #303: pass=ack is narrative only
        ack = "role=reviewer-validator pass=ack pr=171 sha=%s round=n/a verdict=n/a" % HEAD
        _, state = self.crew.decide({}, fixture("prs-ci-passed.json"), [])
        for acks in ([ack], [ack, ack]):  # one ack, and a repeated one: neither is an event
            self.assertEqual(self.crew.decide(state, self.marked("prs-ci-passed.json", *acks), [])[0], [])
        old = "role=reviewer-validator pass=verdict pr=171 sha=%s round=1 verdict=changes" % ("2" * 40)
        events, _ = self.crew.decide({}, self.marked("prs-pending.json", old, ack), [])
        self.assertEqual([(e["event"], e["round"]) for e in events], [("new-head", 2)])
        self.assertEqual(self.crew.decide({}, self.marked("prs-ci-passed.json", ack), [])[1]["prs"]["171"]["verdict"],
                         None)


class GhRetry(unittest.TestCase):
    """gh_json retries transient GitHub failures with bounded backoff before reporting (#702)."""

    @classmethod
    def setUpClass(cls):
        cls.poll = load_crew().commands()["poll"]

    def gh(self, *stderrs, retry=True):
        """Run gh_json against gh failing with each stderr in turn, then succeeding; return (result or error, sleeps,
        gh calls)."""
        results = [subprocess.CompletedProcess([], 1, "", e) for e in stderrs] + \
            [subprocess.CompletedProcess([], 0, "[1]", "")]
        with mock.patch("subprocess.run", side_effect=results) as run, mock.patch("time.sleep") as sleep:
            try:
                out = self.poll.gh_json("pr", "list", **({"retry": self.poll.RETRY_DELAYS} if retry else {}))
            except RuntimeError as e:
                out = e
        return out, [c.args[0] for c in sleep.call_args_list], run.call_count

    def test_transient_failure_retried_then_succeeds(self):
        bad = "HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)"
        self.assertEqual(self.gh(bad, "read: connection reset by peer"), ([1], [1, 2], 3))

    def test_persistent_transient_failure_is_bounded_and_marked(self):
        out, sleeps, calls = self.gh(*["HTTP 502: Bad Gateway"] * 4)
        self.assertIsInstance(out, self.poll.Transient)
        self.assertEqual((str(out), sleeps, calls), ("crew: gh pr list failed: HTTP 502: Bad Gateway", [1, 2, 4], 4))

    def test_non_transient_failure_is_not_retried(self):
        out, sleeps, calls = self.gh("HTTP 404: Not Found")
        self.assertIs(type(out), RuntimeError)
        self.assertEqual((sleeps, calls), ([], 1))

    def test_other_callers_keep_one_attempt(self):  # train_view records each failed read itself (#621)
        out, sleeps, calls = self.gh("HTTP 504: 504 Gateway Timeout", retry=False)
        self.assertIsInstance(out, self.poll.Transient)
        self.assertEqual((sleeps, calls), ([], 1))

    def rate_limited(self, stderr, limits):
        """gh_json against gh refusing for quota, then `gh api rate_limit` answering limits; (error, gh argv)."""
        results = [subprocess.CompletedProcess([], 1, "", stderr),
                   subprocess.CompletedProcess([], 0, json.dumps({"resources": limits}), "")]
        with mock.patch("subprocess.run", side_effect=results) as run, mock.patch("time.sleep") as sleep, \
                mock.patch("time.time", return_value=1_800_000_000):
            with self.assertRaises(self.poll.RateLimited) as e:
                self.poll.gh_json("pr", "list", retry=self.poll.RETRY_DELAYS)
        self.assertEqual(sleep.call_count, 0)  # a retry only spends more of the quota
        return e.exception, [c.args[0] for c in run.call_args_list]

    def test_rate_limit_is_not_retried_and_waits_for_the_exhausted_reset(self):  # #1300
        limits = {"core": {"remaining": 4000, "reset": 1_800_000_900},
                  "graphql": {"remaining": 0, "reset": 1_800_001_800}}
        e, argv = self.rate_limited("GraphQL: API rate limit exceeded for user ID 1.", limits)
        self.assertEqual(argv[1], ["gh", "api", "rate_limit"])
        self.assertEqual(e.until, 1_800_001_800)
        self.assertEqual(str(e), "crew: gh pr list rate-limited until 2027-01-15T08:30:00Z: "
                         "GraphQL: API rate limit exceeded for user ID 1.")

    def test_secondary_rate_limit_waits_a_minute(self):  # #1300
        e, _ = self.rate_limited("HTTP 403: You have exceeded a secondary rate limit.",
                                 {"graphql": {"remaining": 10, "reset": 1_800_003_600}})
        self.assertEqual(e.until, 1_800_000_000 + self.poll.SECONDARY_WAIT)

    def test_loop_sleeps_until_the_rate_limit_reset(self):  # #1300: poll without --once
        values = {"runtime.options.poll_interval": 60}
        error = self.poll.RateLimited("crew: gh pr list rate-limited until ...", 1_800_000_600)
        with mock.patch.object(self.poll, "profile", return_value=(values, None, None)), \
                mock.patch.object(self.poll, "poll_once", side_effect=error), mock.patch("builtins.print"), \
                mock.patch("time.time", return_value=1_800_000_000), \
                mock.patch("time.sleep", side_effect=KeyboardInterrupt) as sleep:
            with self.assertRaises(KeyboardInterrupt):
                self.poll.run(mock.Mock(once=False, triage_only=False))
        sleep.assert_called_once_with(600)

    def refused(self, *argv, **kwargs):
        raise self.poll.RateLimited("crew: gh %s rate-limited until 2027-01-15T08:30:00Z: API rate limit exceeded"
                                    % " ".join(argv[:2]), 1_800_001_800)

    def test_late_rate_limit_in_triage_exits_tempfail_without_more_reads(self):  # #1300 r1
        values = {"repo.owner": "acme", "repo.name": "widgets", "repo.default_branch": "main", "triage.enabled": True}
        reads, triage = [], self.poll.triage_poll

        def read(*argv, **kwargs):
            reads.append(argv[:2])
            return self.refused(*argv) if argv[:2] == ("issue", "list") else []

        with tempfile.TemporaryDirectory() as state, mock.patch("builtins.print") as out:
            os.makedirs(os.path.join(state, "wake"))
            with mock.patch.object(self.poll, "profile", return_value=(values, None, state)), \
                    mock.patch.object(self.poll.ownership_module, "status", return_value="active"), \
                    mock.patch.object(self.poll, "gh_json", return_value=[]), \
                    mock.patch.object(self.poll, "triage_poll", lambda v, s, p, **kw: triage(v, s, p, read=read, **kw)):
                code = self.poll.run(mock.Mock(once=True, triage_only=False, project="crew.toml"))
        self.assertEqual(code, 75)
        self.assertEqual(reads, [("issue", "list")])  # no milestones read after the refusal
        self.assertIn("rate-limited until 2027-01-15T08:30:00Z", str(out.call_args_list[-1].args[0]))

    def test_late_rate_limit_in_express_spec_read_exits_tempfail(self):  # #1300 r2: train_spec's files read
        pr = dict(fixture("prs-pending.json")[0], labels=[{"name": "crew:express"}])
        values = {"repo.owner": "acme", "repo.name": "widgets", "repo.default_branch": "main"}
        replies = {("pr", "list"): [pr], ("pr", "view"): {"closingIssuesReferences": [{"number": 1300}]},
                   ("issue", "view"): {"comments": [], "labels": []}}
        reads = []

        def read(*argv, **kwargs):
            reads.append(argv[:2])
            return self.refused(*argv) if "/files?" in argv[1] else replies.get(argv[:2], [])

        train = self.poll.commands()["train"]
        with tempfile.TemporaryDirectory() as state, mock.patch("builtins.print") as out:
            os.makedirs(os.path.join(state, "wake"))
            with mock.patch.object(self.poll, "profile", return_value=(values, None, state)), \
                    mock.patch.object(self.poll.ownership_module, "status", return_value="active"), \
                    mock.patch.object(self.poll, "gh_json", side_effect=read), \
                    mock.patch.object(train.precheck.config, "resolve_profile", return_value=({},)):
                code = self.poll.run(mock.Mock(once=True, triage_only=False, project="crew.toml", org_profile=None))
            self.assertFalse(os.path.exists(os.path.join(state, "poll-state.json")))  # no baseline recorded
        self.assertEqual(code, 75)
        self.assertEqual(reads[-1], ("api", "repos/acme/widgets/pulls/171/files?per_page=100"))
        self.assertEqual(str(out.call_args_list[-1].args[0]),
                         "crew: gh api repos/acme/widgets/pulls/171/files?per_page=100 rate-limited until "
                         "2027-01-15T08:30:00Z: API rate limit exceeded")

    def test_every_read_fallback_reraises_a_rate_limit(self):  # #1300 r1: each would otherwise poll on as success
        failed = {"status": "COMPLETED", "conclusion": "FAILURE",
                  "detailsUrl": "https://github.com/acme/widgets/actions/runs/1/job/2"}
        train = self.poll.commands()["train"]
        with tempfile.TemporaryDirectory() as state:
            for name, call in [
                    ("observe_ci", lambda: self.poll.observe_ci({"statusCheckRollup": [failed]}, "acme/widgets")),
                    ("ci_state", lambda: self.poll.ci_state({"statusCheckRollup": [failed]}, "acme/widgets")),
                    ("triage_milestones", lambda: self.poll.triage_milestones(
                        {"repo.owner": "acme", "repo.name": "widgets"}, state, read=self.refused)),
                    ("express_lane", lambda: self.poll.express_lane(
                        mock.Mock(project="crew.toml", org_profile=None), {"repo.owner": "acme", "repo.name": "widgets"},
                        {"number": 9, "labels": [{"name": "crew:express"}]}))]:
                with self.subTest(name), mock.patch.object(self.poll, "gh_json", side_effect=self.refused), \
                        mock.patch.object(train.precheck.config, "resolve_profile", return_value=({},)):
                    self.assertRaises(self.poll.RateLimited, call)

    def test_once_exits_tempfail_on_transient_and_one_otherwise(self):
        args = mock.Mock(once=True, triage_only=False)
        for error, code in [(self.poll.Transient("crew: gh pr list failed: HTTP 504"), 75),
                            (self.poll.RateLimited("crew: gh pr list rate-limited until ...", 0), 75),
                            (RuntimeError("crew: gh pr list failed: HTTP 404"), 1)]:
            with self.subTest(code=code), mock.patch.object(self.poll, "profile", return_value=({}, None, None)), \
                    mock.patch.object(self.poll, "poll_once", side_effect=error), mock.patch("builtins.print"):
                self.assertEqual(self.poll.run(args), code)


class Poll(Base):
    """mdstack poll --once against a fake gh: baseline, one wake record per change, read-only gh calls."""

    def setUp(self):
        super().setUp()
        self.gh_dir = os.path.join(self.tmp, "gh")
        os.makedirs(self.gh_dir)
        fake = os.path.join(self.tmp, "bin", "gh")
        with open(fake, "w") as f:
            f.write(FAKE_GH)
        os.chmod(fake, 0o755)
        self.env["FAKE_GH_DIR"] = self.gh_dir

    def serve(self, prs, issues="issues-none.json", **views):
        for dst, src in [("prs", prs), ("issues", issues)] + [("pr-" + n, s) for n, s in views.items()]:
            shutil.copy(os.path.join(POLL, src), os.path.join(self.gh_dir, dst + ".json"))
        r = self.crew("poll", "--once", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def queue(self):
        path = os.path.join(self.state, "wake", "queue.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f]

    def test_once_baseline_then_one_record_per_change(self):
        self.assertIn("baseline", self.serve("prs-none.json"))
        self.assertEqual(self.queue(), [])
        out = self.serve("prs-pending.json")
        self.assertIn("new-head -> reviewer #171 " + HEAD, out)
        (rec,) = self.queue()
        self.assertEqual(sorted(rec), ["consumer", "context", "event", "id", "reason", "refs", "round", "source", "ts"])
        self.assertEqual((rec["source"], rec["reason"], rec["event"], rec["consumer"], rec["refs"]),
                         ("poll", "poll", "new-head", "reviewer", ["#171", HEAD]))
        self.assertEqual(rec["context"], {  # the durable envelope: one-repo singleton team, change and head (#1856)
            "team": "repo:acme/widgets", "project": os.path.realpath(self.project), "repo": "acme/widgets",
            "item": None, "change": 171, "head": HEAD, "pass": None, "round": rec["round"]})
        self.serve("prs-pending.json")
        self.assertEqual(len(self.queue()), 1)
        self.serve("prs-none.json", **{"171": "pr-171-merged.json"})
        self.assertEqual([(r["event"], r["consumer"]) for r in self.queue()[1:]], [("pr-merged", "coordinator")])
        with open(os.path.join(self.state, "poll-state.json")) as f:
            self.assertEqual(json.load(f)["prs"], {})
        with open(os.path.join(self.gh_dir, "gh.log")) as f:
            calls = [json.loads(line) for line in f]
        self.assertTrue(all(c[:2] in (["pr", "list"], ["issue", "list"], ["pr", "view"]) for c in calls), calls)
        self.assertIn(["pr", "view", "171", "-R", "acme/widgets", "--json",
                       "number,state,headRefOid,labels,statusCheckRollup,reviews,closingIssuesReferences,mergeable"], calls)

    def test_once_same_head_round_transition_legacy_seed_and_duplicate_suppression(self):
        shutil.copy(os.path.join(POLL, "issues-none.json"), os.path.join(self.gh_dir, "issues.json"))
        prs = fixture("prs-ci-passed.json")
        first = dict(PollDecide.post("role=reviewer-validator pass=verdict pr=171 sha=%s round=2 verdict=changes"
                                    % HEAD, "acme-reviewer", "Vera"), id="R1")
        prs[0]["reviews"] = [first]
        path = os.path.join(self.state, "poll-state.json")

        def poll():
            with open(os.path.join(self.gh_dir, "prs.json"), "w") as f:
                json.dump(prs, f)
            r = self.crew("poll", "--once", "--project", self.project)
            self.assertEqual((r.returncode, r.stderr), (0, "mdstack: config %s\n" % self.project), r.stdout)
            return r.stdout

        self.assertIn("baseline", poll())  # a known verdict on the first read is not replayed
        self.assertEqual(self.queue(), [])
        with open(path) as f:
            stored = json.load(f)
        for key in ("verdict_identity", "verdict_review_id"):
            del stored["prs"]["171"][key]
        with open(path, "w") as f:
            json.dump(stored, f)
        self.assertEqual(poll(), "")  # legacy state seeds quietly
        self.assertEqual(self.queue(), [])
        with open(path) as f:
            self.assertEqual(json.load(f)["prs"]["171"]["verdict_review_id"], "R1")
        later = dict(first, id="R2", body=first["body"].replace("round=2", "round=4"))
        prs[0]["reviews"].append(later)
        self.assertEqual(poll(), "crew: poll: review-changes-requested -> builder #171 %s\n" % HEAD)
        self.assertEqual([(r["event"], r["consumer"], r["refs"]) for r in self.queue()],
                         [("review-changes-requested", "builder", ["#171", HEAD])])
        self.assertEqual(poll(), "")
        prs[0]["reviews"].append(dict(later, id="duplicate"))
        self.assertEqual(poll(), "")
        self.assertEqual(len(self.queue()), 1)
        with open(path) as f:
            self.assertEqual(json.load(f)["prs"]["171"]["verdict_review_id"], "R2")
        passed = dict(later, id="R3", body=later["body"].replace("round=4", "round=5").replace(
                      "verdict=changes", "verdict=pass"))
        prs[0]["reviews"].append(passed)
        self.assertEqual(poll(), "crew: poll: review-approved -> synthesizer #171 %s\n" % HEAD)
        self.assertEqual(poll(), "")
        self.assertEqual([r["consumer"] for r in self.queue()], ["builder", "synthesizer"])
        with open(os.path.join(self.gh_dir, "gh.log")) as f:
            calls = list(map(json.loads, f))
        self.assertTrue(all(c[:2] in (["pr", "list"], ["issue", "list"], ["pr", "view"]) for c in calls))

    def test_owner_comment_on_a_held_pr_queues_one_owner_answer(self):  # #394
        self.serve("prs-none.json")
        self.serve("prs-pending.json")  # PR #171 carries crew:hold
        before = len(self.queue())
        self.serve("prs-pending.json")
        self.assertEqual(len(self.queue()), before)  # no owner answer yet
        with open(os.path.join(self.gh_dir, "answers-171.json"), "w") as f:
            json.dump({"comments": [{"author": {"login": "acme-owner"}, "body": "Please proceed with option A."}],
                       "reviews": []}, f)
        self.assertIn("owner-answer -> coordinator #171", self.serve("prs-pending.json"))
        self.assertEqual([r["event"] for r in self.queue()[before:]], ["owner-answer"])
        with open(os.path.join(self.state, "poll-state.json")) as f:
            self.assertEqual(json.load(f)["held"], ["#171"])  # the hold stays for the coordinator to reconcile
        with open(os.path.join(self.gh_dir, "gh.log")) as f:
            self.assertIn(["pr", "view", "171", "-R", "acme/widgets", "--json", "comments,reviews"], map(json.loads, f))

    def test_once_conflict_wakes_builder_once_per_head_and_conflict(self):  # #1398: through the shipped CLI
        self.transcript = []
        shutil.copy(os.path.join(POLL, "issues-none.json"), os.path.join(self.gh_dir, "issues.json"))

        def poll(mergeable, head=HEAD):
            prs = fixture("prs-pending.json")
            prs[0].update(mergeable=mergeable, headRefOid=head)
            with open(os.path.join(self.gh_dir, "prs.json"), "w") as f:
                json.dump(prs, f)
            r = self.crew("poll", "--once", "--project", self.project)
            self.transcript.append(("mergeable=%s head=%s" % (mergeable, head[:7]), r))
            self.assertEqual((r.returncode, r.stderr), (0, "mdstack: config %s\n" % self.project), r.stdout)
            with open(os.path.join(self.state, "poll-state.json")) as f:
                stored = json.load(f)["prs"]["171"].get("mergeable")
            return [line for line in r.stdout.splitlines() if "pr-conflicting" in line], stored
        self.assertEqual(poll("MERGEABLE"), ([], "MERGEABLE"))
        hit = ["crew: poll: pr-conflicting -> builder #171 " + HEAD]
        self.assertEqual(poll("CONFLICTING"), (hit, "CONFLICTING"))  # a land made the unchanged head conflict
        for mergeable in ("CONFLICTING", "UNKNOWN"):  # repeats and UNKNOWN never multiply
            self.assertEqual(poll(mergeable), ([], "CONFLICTING"), mergeable)
        self.assertEqual(poll("MERGEABLE"), ([], "MERGEABLE"))
        self.assertEqual(poll("CONFLICTING"), (hit, "CONFLICTING"))  # resolved, then conflicting again
        new = "b" * 40
        self.assertEqual(poll("CONFLICTING", new), (["crew: poll: pr-conflicting -> builder #171 " + new],
                                                    "CONFLICTING"))
        self.assertEqual([(w["event"], w["consumer"], w["refs"]) for w in self.queue()
                          if w["event"] == "pr-conflicting"],
                         [("pr-conflicting", "builder", ["#171", h]) for h in (HEAD, HEAD, new)])

    def test_owner_comment_on_an_asked_pr_without_a_hold_queues_one_owner_answer(self):  # #394
        pr = dict(fixture("prs-pending.json")[0], labels=[{"name": "crew:in-review"}])
        with open(os.path.join(self.gh_dir, "prs.json"), "w") as f:
            json.dump([pr], f)
        shutil.copy(os.path.join(POLL, "issues-none.json"), os.path.join(self.gh_dir, "issues.json"))
        self.put("asks/171.json", json.dumps({"deadline": "2033-05-18T10:00:00-07:00"}))  # the coordinator's open ask
        for _ in range(2):  # baseline, then the ask's answer count
            self.assertEqual(self.crew("poll", "--once", "--project", self.project).returncode, 0)
        with open(os.path.join(self.gh_dir, "answers-171.json"), "w") as f:
            json.dump({"comments": [{"author": {"login": "acme-owner"}, "body": "Option A."}], "reviews": []}, f)
        r = self.crew("poll", "--once", "--project", self.project)
        self.assertIn("owner-answer -> coordinator #171", r.stdout, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.state, "asks", "171.json")))  # the ask stays for the coordinator

    def test_ready_samples_written_on_change_with_the_polling_bound(self):  # #1524
        def poll(labels, mergeable, state="OPEN"):
            pr = dict(fixture("pr-171-merged.json"), state=state, mergeable=mergeable,
                      labels=[{"name": x} for x in labels])
            for name, value in (("prs", [pr] if state == "OPEN" else []), ("pr-171", pr), ("issues", [])):
                with open(os.path.join(self.gh_dir, name + ".json"), "w") as f:
                    json.dump(value, f)
            r = self.crew("poll", "--once", "--project", self.project)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        poll(["crew:in-review", "crew:hold"], "MERGEABLE")
        poll(["crew:in-review", "crew:hold"], "MERGEABLE")  # unchanged: no second sample
        poll(["crew:in-review"], "CONFLICTING")
        poll(["crew:in-review"], "MERGEABLE")
        poll(["crew:approved"], "MERGEABLE", state="MERGED")
        with open(os.path.join(self.state, "metrics", "observations.jsonl")) as f:
            obs = [json.loads(line) for line in f]
        self.assertEqual([(o["state"], o["hold"], o["mergeable"], o["ready"]) for o in obs],
                         [("OPEN", True, "MERGEABLE", False), ("OPEN", False, "CONFLICTING", False),
                          ("OPEN", False, "MERGEABLE", True), ("MERGED", False, "MERGEABLE", False)])
        self.assertEqual({(o["source"], o["key"], o["ci"], o["verdict"]) for o in obs},
                         {("poll", "pr#171@" + HEAD, "passed", "pass")})
        self.assertIsNone(obs[0]["prev_ts"])
        self.assertTrue(all(o["prev_ts"] and o["prev_ts"] <= o["ts"] for o in obs[1:]))

    def test_triage_scan_off_unless_enabled(self):  # #747: T2 adds the [triage] profile
        self.serve("prs-none.json")
        self.assertFalse(os.path.exists(os.path.join(self.state, "triage")))

    def test_ci_finishes_without_a_second_review(self):
        self.serve("prs-none.json")
        self.serve("prs-pending.json")
        self.serve("prs-ci-failed.json")
        self.serve("prs-ci-passed.json")
        self.assertEqual([(r["event"], r["consumer"]) for r in self.queue()],
                         [("new-head", "reviewer"), ("ci-failed", "builder"), ("ci-passed", "synthesizer")])

    def express_pr(self, labels=("crew:in-review", "crew:express"), item="express", selfgate=False):
        prs = fixture("prs-ci-passed.json")
        prs[0]["labels"] = [{"name": x} for x in labels]
        if selfgate:
            prs[0]["reviews"].append({"author": {"login": "acme-bot"}, "body": "<!-- crew:v1 role=builder "
                                      "pass=selfgate pr=171 sha=%s verdict=pass -->" % HEAD})
        for name, value in (("prs", prs), ("pr-171", {"closingIssuesReferences": [{"number": 72}]}),
                            ("issue-72", {"labels": [], "comments": [{"author": {"login": "acme-bot"}, "body": (
                                "[Ash/flavor] #72: %s\nReason: small\n<!-- crew:v1 role=coordinator pass=flavor "
                                "issue=72 flavor=%s default=standard -->" % (item, item))}]} if item else {}),
                            ("files", [{"filename": "docs/two.md"}])):
            with open(os.path.join(self.gh_dir, name + ".json"), "w") as f:
                json.dump(value, f)
        r = self.crew("poll", "--once", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_once_resolves_express_and_falls_back(self):  # #672
        self.serve("prs-none.json")
        self.express_pr()
        self.assertEqual(self.queue(), [])  # no new-head, and CI green without a selfgate pass wakes nobody
        self.assertIn("selfgate-passed -> synthesizer #171 " + HEAD, self.express_pr(selfgate=True))
        self.assertIn("new-head -> reviewer #171 " + HEAD, self.express_pr(labels=("crew:in-review",), selfgate=True))
        self.assertEqual([r["event"] for r in self.queue()], ["selfgate-passed", "new-head"])

    def test_once_express_merge_up_reads_the_selfgate(self):  # #672 r2: no reviewer verdict exists
        self.serve("prs-none.json")
        self.express_pr(selfgate=True)
        with open(os.path.join(self.gh_dir, "prs.json")) as f:
            prs = json.load(f)
        prs[0]["headRefOid"] = "3" * 40
        for name, value in (("prs", prs), ("commit", {"parents": [{"sha": HEAD}, {"sha": "4" * 40}]}),
                            ("compare", {"status": "identical"})):
            with open(os.path.join(self.gh_dir, name + ".json"), "w") as f:
                json.dump(value, f)
        r = self.crew("poll", "--once", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("merge-up -> synthesizer #171 " + "3" * 40, r.stdout)
        self.assertEqual([(e["event"], e.get("previous_head")) for e in self.queue()[1:]],
                         [("merge-up", HEAD), ("ci-passed", None)])  # CI already green at the merged head

    def test_once_crew_lane_item_or_unreadable_resolution_gets_review(self):  # #672
        self.serve("prs-none.json")
        self.assertIn("new-head -> reviewer", self.express_pr(item="standard"))
        self.serve("prs-none.json", **{"171": "pr-171-merged.json"})
        out = self.express_pr(item=None)  # the issue read has no comments
        self.assertIn("crew: poll: #171 crew lane: express resolution unreadable", out)
        self.assertIn("new-head -> reviewer", out)

    def test_queued_ci_failed_for_superseded_head_dropped(self):  # #578
        self.serve("prs-pending.json")
        old, other = (dict(event="ci-failed", consumer="builder", refs=refs) for refs in
                      (["#171", "a" * 40], ["#999", "b" * 40]))
        current = dict(event="ci-failed", consumer="builder", refs=["#171", HEAD])
        with open(os.path.join(self.state, "wake", "queue.jsonl"), "w") as f:
            f.writelines(json.dumps(w) + "\n" for w in (old, other, current))
        self.serve("prs-pending.json")
        self.assertEqual(self.queue(), [other, current])

    def test_poll_reads_job_steps_and_routes_startup_failure_to_coordinator(self):
        self.serve("prs-pending.json")
        prs = fixture("prs-ci-failed.json")
        for check in prs[0]["statusCheckRollup"]:
            if check.get("conclusion") == "FAILURE":
                check["detailsUrl"] = "https://github.com/acme/widgets/actions/runs/1/job/2"
        for name, data in [("prs", prs), ("job", dict(status="completed", conclusion="failure", steps=[]))]:
            with open(os.path.join(self.gh_dir, name + ".json"), "w") as f:
                json.dump(data, f)
        for _ in range(2):
            r = self.crew("poll", "--once", "--project", self.project)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([(e["event"], e["consumer"]) for e in self.queue()], [("ci-infra", "coordinator")])

    def merge_push(self, parents, status="identical", verdict="pass", intermediate=False):
        prs = fixture("prs-approved.json")
        prs[0]["reviews"][-1]["body"] = (
            "<!-- crew:v1 role=reviewer-validator pass=verdict pr=171 sha=%s round=1 verdict=changes -->\n"
            "<!-- crew:v1 role=reviewer-validator pass=verdict pr=171 sha=%s round=2 verdict=%s -->"
            % ("0" * 40, HEAD, verdict))
        for name, value in (("prs", prs), ("issues", [])):
            with open(os.path.join(self.gh_dir, name + ".json"), "w") as f:
                json.dump(value, f)
        self.assertEqual(self.crew("poll", "--once", "--project", self.project).returncode, 0)
        if intermediate:  # a later changes verdict must override the cached approval
            prs[0]["reviews"].append({"body": "<!-- crew:v1 role=reviewer-validator pass=verdict pr=171 "
                                     "sha=%s round=2 verdict=changes -->" % HEAD})
        prs[0]["headRefOid"] = "3" * 40
        for name, value in (("prs", prs), ("commit", {"parents": [{"sha": p} for p in parents]}),
                            ("compare", {"status": status})):
            with open(os.path.join(self.gh_dir, name + ".json"), "w") as f:
                json.dump(value, f)
        r = self.crew("poll", "--once", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_approved_merge_emits_recheck_once_with_previous_head_and_round(self):
        r = self.merge_push([HEAD, "4" * 40], status="ahead")
        self.assertIn("merge-up -> synthesizer", r.stdout)
        event = self.queue()[0]
        self.assertEqual((event["event"], event["consumer"], event["refs"], event["previous_head"], event["round"]),
                         ("merge-up", "synthesizer", ["#171", "3" * 40], HEAD, 2))
        self.assertEqual(self.crew("poll", "--once", "--project", self.project).returncode, 0)
        self.assertEqual(len([e for e in self.queue() if e["event"] == "merge-up"]), 1)
        with open(os.path.join(self.gh_dir, "gh.log")) as f:
            api = [json.loads(line) for line in f if json.loads(line)[0] == "api"]
        self.assertEqual(api, [["api", "repos/acme/widgets/commits/" + "3" * 40],
                               ["api", "repos/acme/widgets/compare/" + "4" * 40 + "...main"]])

    def test_non_merge_code_push_uses_normal_review(self):
        self.merge_push([HEAD])
        self.assertEqual(self.queue()[0]["event"], "new-head")

    def test_merge_of_current_default_tip_uses_recheck(self):
        self.merge_push([HEAD, "4" * 40])
        self.assertEqual(self.queue()[0]["event"], "merge-up")

    def test_merge_after_another_builder_commit_uses_normal_review(self):
        self.merge_push(["5" * 40, "4" * 40])
        self.assertEqual(self.queue()[0]["event"], "new-head")

    def test_merge_of_other_branch_uses_normal_review(self):
        self.merge_push([HEAD, "4" * 40], status="diverged")
        self.assertEqual(self.queue()[0]["event"], "new-head")

    def test_changes_verdict_does_not_inherit_approval(self):
        self.merge_push([HEAD, "4" * 40], verdict="changes")
        self.assertEqual(self.queue()[0]["event"], "new-head")

    def test_live_changes_verdict_overrides_cached_pass(self):
        self.merge_push([HEAD, "4" * 40], intermediate=True)
        self.assertEqual(self.queue()[0]["event"], "new-head")


class TriageScan(unittest.TestCase):
    """The zero-model triage scan (triage.md T1, #747) on fixture issues."""

    @classmethod
    def setUpClass(cls):
        cls.crew = load_crew()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.values = {"repo.owner": "acme", "repo.name": "widgets", "identities.owners": ["owner"]}
        self.closed = [{"number": 1, "title": "M1"}]

    def scan(self, rules=None):
        rules = rules or self.crew.TRIAGE_RULES
        entries = self.crew.triage_scan("acme/widgets", fixture("triage-open.json"), fixture("triage-closed.json"),
                                        rules, {"owner"}, self.crew.triage_card_fields())
        return {e["ref"].split("#")[1]: e for e in entries}

    def poll(self, read=None, project=None):
        calls = []

        def fake(*args, retry=()):
            calls.append(args)
            if args[0] == "api":
                return self.closed
            if read:
                return read(*args)
            return fixture("triage-open.json" if args[5] == "open" else "triage-closed.json")
        self.crew.triage_poll(self.values, self.tmp, project or os.path.join(self.tmp, "crew.toml"), read=fake)
        with open(os.path.join(self.tmp, "triage", "queue.json")) as f:
            queue = json.load(f)
        path = os.path.join(self.tmp, "wake", "queue.jsonl")
        wakes = []
        if os.path.exists(path):
            with open(path) as f:
                wakes = [json.loads(line) for line in f]
        return queue, wakes, calls

    def test_skip_rules_queue_only_unplaced_issues_and_owner_replies(self):
        entries = self.scan()
        self.assertEqual(sorted(entries, key=int), ["10", "11", "12", "16", "20", "21"])
        self.assertEqual({n: entries[n].get("reason") for n in ("10", "16")}, {"10": "new", "16": "owner-reply"})
        # 13 triage:log, 14 milestone, 15 flavor record, 17 non-owner reply, 18 no reply after the record, 19 a PR

    def test_owner_feedback_queues_applied_records_and_relayed_decisions(self):  # #835
        def item(n, comments, milestone=None):
            return {"number": n, "title": "item %d" % n, "body": "", "labels": [], "milestone": milestone,
                    "url": "https://github.com/acme/widgets/issues/%d" % n, "comments": comments}

        def c(login, body, at="2026-11-05T05:00:00Z"):
            return {"author": {"login": login}, "body": body, "createdAt": at}
        record = c("md-mt", "[Riley/triage] #%d\n<!-- crew:v1 role=researcher pass=triage issue=0 decision=place "
                   "priority=P2 mode=apply sweep=20261105T0400Z -->", "2026-11-05T04:00:00Z")
        items = [item(30, [record, c("owner", "triage: adjust priority=P1 type=bug")], {"title": "M2"}),
                 item(31, [record, c("owner", "looks fine")], {"title": "M2"}),  # placed: a plain reply is not feedback
                 item(32, [record, c("md-mt", "[Ash/decision] Owner 04:45Z: \"reject, P2\"\n<!-- crew:v1 role=coordinator pass=steer cmd=decision -->")]),
                 item(33, [record], {"title": "M2"}),
                 item(34, [record]),
                 item(985, [c("md-mt", "🔥 Ash · Decision · Owner ~04:52Z: \"accept\" on #33; #34 too.\n<!-- crew:v1 role=coordinator pass=steer cmd=decision -->"),
                            c("md-mt", "[Ash/note] #30 unrelated"), c("bot", "[Ash/decision] spoof on #31\n<!-- crew:v1 role=coordinator pass=steer cmd=decision -->"),
                            c("md-mt", "[Ash/decision] markerless on #31")],
                      {"title": "log"})]
        entries = self.crew.triage_scan("acme/widgets", items, [], self.crew.TRIAGE_RULES, {"owner"},
                                        self.crew.triage_card_fields(), ("md-mt", "Ash"))
        self.assertEqual({e["ref"]: e["reason"] for e in entries},
                         {"acme/widgets#%d" % n: "owner-feedback" for n in (30, 32, 33, 34)})
        items[3]["comments"].append(dict(record, createdAt="2026-11-05T06:00:00Z"))  # the sweep recorded it
        entries = self.crew.triage_scan("acme/widgets", items, [], self.crew.TRIAGE_RULES, {"owner"},
                                        self.crew.triage_card_fields(), ("md-mt", "Ash"))
        self.assertNotIn("acme/widgets#33", {e["ref"] for e in entries})

    def test_unreadable_item_is_recorded(self):
        self.assertEqual(self.scan()["20"], {"ref": "acme/widgets#20", "unreadable": "KeyError: 'comments'"})

    def test_duplicate_hints_from_exact_keys_across_open_and_closed(self):
        entries = self.scan()
        self.assertEqual(entries["10"]["duplicates"], [{"ref": "acme/widgets#3", "state": "closed",
                                                        "keys": ["class:merge-gate-race", "path:scripts/crew.d/train.py"]}])
        self.assertEqual(entries["21"]["duplicates"], [{"ref": "acme/widgets#4", "state": "closed",
                                                        "keys": ["title:watcher exits early"]}])
        self.assertEqual(entries["11"]["duplicates"], [])

    def test_card_fields_parsed_from_the_intake_template(self):
        fields = self.crew.triage_card_fields()
        self.assertEqual(fields[:3], ["Source", "Trigger", "Failure class"])
        self.assertIn("Escaped from", fields)
        card = self.scan()["10"]["card"]
        self.assertEqual((card["Source"], card["Failure class"], card["Decision"]),
                         ("acme/widgets#171 (https://github.com/acme/widgets/pull/171)", "merge-gate-race", "pending"))
        self.assertEqual(self.scan()["11"]["card"], {})

    def test_intake_issue_template_matches_the_card_and_parses(self):
        root = os.path.dirname(SCRIPTS)
        with open(os.path.join(root, ".github", "ISSUE_TEMPLATE", "intake-card.md"), encoding="utf-8") as f:
            body = f.read().split("\n---\n", 1)[1]
        fields = self.crew.triage_card_fields()
        self.assertEqual(re.findall(r"^(?:\*\*)?([A-Z][\w ]*?):", body, re.M), fields)
        card, _ = self.crew.triage_keys({"title": "intake: flake on acme/widgets#1", "body": body}, fields)
        self.assertEqual(sorted(card), sorted(fields))
        with open(os.path.join(root, ".github", "ISSUE_TEMPLATE", "config.yml"), encoding="utf-8") as f:
            self.assertIn("blank_issues_enabled: true", f.read().splitlines())

    def test_p0_signals_from_defaults_and_rules_file(self):
        entries = self.scan()
        self.assertEqual({n: e.get("p0") for n, e in entries.items() if e.get("p0")},
                         {"11": ["keyword:pipeline blocked"], "12": ["label:security"]})
        rules_file = os.path.join(self.tmp, "triage-rules.toml")
        with open(rules_file, "w") as f:
            f.write('[p0]\nkeywords = ["exits early"]\n')
        rules, note = self.crew.triage_rules(rules_file)
        self.assertEqual(note, rules_file)
        self.assertEqual({n for n, e in self.scan(rules).items() if e.get("p0")}, {"21"})
        with open(rules_file, "w") as f:
            f.write("not toml [")
        rules, note = self.crew.triage_rules(rules_file)
        self.assertIs(rules, self.crew.TRIAGE_RULES)
        self.assertTrue(note.startswith("default (unreadable " + rules_file), note)
        self.assertEqual(self.crew.triage_rules(None), (self.crew.TRIAGE_RULES, "default"))

    def test_poll_writes_queue_and_wakes_each_new_p0_once(self):
        queue, wakes, calls = self.poll()
        self.assertEqual((queue["rules"], queue["repos"]), ("default", {"acme/widgets": "ok"}))
        self.assertEqual(len(queue["items"]), 6)
        self.assertEqual([(w["event"], w["consumer"], w["refs"]) for w in wakes],
                         [("triage-p0", "coordinator", ["acme/widgets#11"]),
                          ("triage-p0", "coordinator", ["acme/widgets#12"])])
        self.assertTrue(all(c[:2] == ("issue", "list") or c == ("api", "repos/acme/widgets/milestones?state=closed&per_page=100")
                            for c in calls), calls)  # read-only gh, no model call
        _, wakes, _ = self.poll()
        self.assertEqual(len(wakes), 2)

    def test_owner_feedback_on_a_recorded_p0_queues_without_a_second_wake(self):  # #1093
        def c(login, body, at):
            return {"author": {"login": login}, "body": body, "createdAt": at}
        item = {"number": 9, "title": "Crew stalls on every run", "body": "", "labels": [{"name": "P0"}],
                "milestone": None, "url": "https://github.com/acme/widgets/issues/9", "comments": []}
        read = lambda *args: [item] if args[5] == "open" else []
        queue, wakes, _ = self.poll(read)
        self.assertEqual(([e["reason"] for e in queue["items"]], [w["refs"] for w in wakes]),
                         (["new"], [["acme/widgets#9"]]))
        item["comments"].append(c("md-mt", "<!-- crew:v1 role=researcher pass=triage issue=9 decision=classify "
                                  "priority=P0 mode=shadow sweep=20261105T0400Z -->", "2026-11-05T04:00:00Z"))
        queue, wakes, _ = self.poll(read)  # recorded: it leaves the queue
        self.assertEqual((queue["items"], len(wakes)), ([], 1))
        item["comments"].append(c("owner", "triage: accept", "2026-11-05T05:00:00Z"))
        queue, wakes, _ = self.poll(read)
        self.assertEqual(([e["reason"] for e in queue["items"]], queue["items"][0]["p0"], len(wakes)),
                         (["owner-feedback"], ["label:P0"], 1))

    def test_triage_repos_and_unreadable_repo_recorded(self):
        def read(*args):
            if args[3] == "acme/down":
                raise RuntimeError("crew: gh issue list failed: HTTP 404")
            return []
        self.values.update({"triage.repos": ["acme/down", "acme/tracker"], "triage.rules": "missing.toml"})
        queue, wakes, _ = self.poll(read)
        self.assertTrue(queue["rules"].startswith("default (unreadable %s" % os.path.join(self.tmp, "missing.toml")))
        self.assertEqual(queue["repos"], {"acme/down": "unreadable: crew: gh issue list failed: HTTP 404",
                                          "acme/tracker": "ok"})
        self.assertEqual((queue["items"], wakes), ([], []))

    def test_closed_milestones_queue_after_the_baseline_until_a_sweep_takes_them(self):  # #374
        def milestones():
            return self.poll(lambda *args: [])[0]["milestones"]
        self.assertEqual(milestones(), [])  # first scan: baseline only, the already-closed M1 never sweeps
        self.closed += [{"number": 2, "title": "M2"}, {"number": 3, "title": "M3"}]
        m2, m3 = ({"repo": "acme/widgets", "number": n, "title": "M%d" % n} for n in (2, 3))
        self.assertEqual(milestones(), [m2, m3])
        self.assertEqual(milestones(), [m2, m3])  # kept on later scans
        self.crew.triage_take(self.tmp, [m2])  # a started sweep took M2
        self.assertEqual(milestones(), [m3])

        def down(*args, retry=()):  # an unreadable milestone list keeps the pending ones
            if args[0] == "api":
                raise RuntimeError("crew: gh api failed: HTTP 502")
            return []
        self.crew.triage_poll(self.values, self.tmp, os.path.join(self.tmp, "crew.toml"), read=down)
        with open(os.path.join(self.tmp, "triage", "queue.json")) as f:
            self.assertEqual(json.load(f)["milestones"], [m3])


class NativeTriage(Base):
    """#1404: a non-GitHub tracker's triage scan reads `tracker.list-items`, never gh; `--triage-only` runs on session."""
    EX = textwrap.dedent("""\
        #!/usr/bin/env python3
        import json, os, sys
        if sys.argv[1:3] == ["items", "DOWN"]:
            sys.exit("ex: no tracker DOWN")
        with open(os.environ["EX_ITEMS"] + ".log", "a") as f:
            f.write(json.dumps(sys.argv[1:]) + "\\n")
        if sys.argv[1] == "comments":  # #1960: one item's comments, or a failed read for an item without any
            comments = json.load(open(os.environ["EX_ITEMS"] + ".comments")).get(sys.argv[2])
            sys.exit("ex: no comments") if comments is None else print(json.dumps(comments))
            sys.exit(0)
        print(open(os.environ["EX_ITEMS"]).read())
        """)

    def setUp(self):
        super().setUp()
        self.write_profile(runtime="session")
        with open(os.path.join(SCRIPTS, "..", "templates", "backends", "github.toml")) as f:
            github = f.read()
        mapping = re.sub(r"(?m)^list-items = .*$", 'list-items = "ex items <tracker> --json --root <state-dir>"', github)
        write_pack(os.path.join(self.project_dir, "pack"), mapping=mapping)
        with open(self.project, "a") as f:
            f.write('pack = "pack"\n[runtime.options]\nresearchers = 1\n'  # #1724: the session sweep is opt-in
                    '[triage]\nenabled = true\ntrackers = ["OPS", "DOWN"]\n')
        for name, text in (("ex", self.EX), ("gh", '#!/bin/sh\necho "$*" >> "%s"\nexit 1\n'
                                                 % os.path.join(self.tmp, "gh.log"))):
            path = os.path.join(self.tmp, "bin", name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.env["EX_ITEMS"] = os.path.join(self.tmp, "items.json")
        owner = "acme-owner"
        record = "<!-- crew:v1 role=researcher pass=triage issue=OPS-3 decision=classify priority=P2 mode=shadow -->"
        with open(self.env["EX_ITEMS"], "w") as f:
            json.dump([{"id": "OPS-1", "title": "Pipeline blocked on deploy", "body": "", "labels": ["bug"]},
                       {"id": "OPS-2", "title": "Placed", "body": "", "labels": [], "milestone": "M3"},
                       {"id": "OPS-3", "title": "Recorded", "body": "", "labels": [{"name": "P2"}],
                        "comments": [{"author": "acme-bot", "body": record, "created": "2026-11-01T00:00:00Z"},
                                     {"author": owner, "body": "triage: accept", "created": "2026-11-02T00:00:00Z"}]},
                       {"id": "OPS-4", "title": "Pipeline blocked on deploy", "body": "", "state": "closed"}], f)

    def test_triage_only_scans_the_tracker_binding_on_a_session_profile(self):
        r = self.crew("poll", "--triage-only", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew: poll: triage queue 2 items (OPS ok, DOWN unreadable: tracker.list-items failed: "
                      "ex: no tracker DOWN)", r.stdout)
        with open(os.path.join(self.state, "triage", "queue.json")) as f:
            queue = json.load(f)
        items = {e["ref"]: e for e in queue["items"]}
        self.assertEqual(sorted(items), ["OPS#OPS-1", "OPS#OPS-3"])
        self.assertEqual((items["OPS#OPS-1"]["reason"], items["OPS#OPS-1"]["p0"]), ("new", ["keyword:pipeline blocked"]))
        self.assertEqual([d["ref"] for d in items["OPS#OPS-1"]["duplicates"]], ["OPS#OPS-4"])
        self.assertEqual(items["OPS#OPS-3"]["reason"], "owner-feedback")
        self.assertEqual(queue["milestones"], [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gh.log")))  # gh never ran
        with open(self.env["EX_ITEMS"] + ".log") as f:  # install-time <state-dir> filled, <tracker> per read
            self.assertEqual(json.loads(f.readline()), ["items", "OPS", "--json", "--root",
                                                        os.path.join(self.tmp, "state")])
        with open(os.path.join(self.state, "wake", "queue.jsonl")) as f:
            self.assertEqual([json.loads(line)["refs"] for line in f], [["OPS#OPS-1"]])

    def test_read_comments_per_open_item_yields_the_github_fixture_queue(self):  # #1960 AC1
        opened, closed = fixture("triage-open.json"), fixture("triage-closed.json")
        with open(self.env["EX_ITEMS"], "w") as f:  # listed without comments, as a tracker CLI that omits them
            json.dump([{k: v for k, v in i.items() if k != "comments"} for i in opened] +
                      [dict(i, state="closed") for i in closed], f)
        with open(self.env["EX_ITEMS"] + ".comments", "w") as f:  # #20 has none: its read fails, as gh's lacks them
            json.dump({str(i["number"]): i["comments"] for i in opened if "comments" in i}, f)
        pack = os.path.join(self.project_dir, "pack")
        for rel, old, new in (("manifest.toml", 'read-comments = "unsupported"', 'read-comments = "supported"'),
                              ("render/backends/example.toml", "\nlist-items = ",
                               '\nread-comments = "ex comments <n>"\nlist-items = ')):
            with open(os.path.join(pack, rel)) as f:
                text = f.read()
            self.assertIn(old, text)
            with open(os.path.join(pack, rel), "w") as f:
                f.write(text.replace(old, new, 1))
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:  # the fixture's owner; the default tracker id, so refs match gh's
            f.write(text.replace('owners = ["acme-owner"]', 'owners = ["owner"]')
                    .replace('trackers = ["OPS", "DOWN"]\n', ""))
        r = self.crew("poll", "--triage-only", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.state, "triage", "queue.json")) as f:
            native = json.load(f)
        with open(self.env["EX_ITEMS"] + ".log") as f:  # once per open item, never a closed one
            reads = [json.loads(line) for line in f][1:]
        self.assertEqual(reads, [["comments", str(i["number"])] for i in opened])

        gh_state = os.path.join(self.tmp, "gh-state")
        values = {"repo.owner": "acme", "repo.name": "widgets", "identities.owners": ["owner"],
                  "identities.coordinator.gh_user": "acme-bot", "identities.coordinator.name": "Ash"}
        load_crew().triage_poll(values, gh_state, self.project, read=lambda *a, retry=(): [] if a[0] == "api" else
                                fixture("triage-open.json" if a[5] == "open" else "triage-closed.json"))
        with open(os.path.join(gh_state, "triage", "queue.json")) as f:
            github = json.load(f)
        self.assertEqual(native["repos"], {"acme/widgets": "ok"})
        self.assertEqual(native["items"], github["items"])
        self.assertEqual(len(native["items"]), 6)

    def test_triage_only_needs_triage_enabled_and_plain_poll_stays_tmux_only(self):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace("enabled = true", "enabled = false"))
        r = self.crew("poll", "--triage-only", "--project", self.project)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "crew: poll: triage.enabled is false; nothing to scan"))
        r = self.crew("poll", "--once", "--project", self.project)
        self.assertEqual(r.returncode, 1)
        self.assertIn("runtime.name is session, not tmux", r.stdout)

    def test_list_items_shapes_normalize(self):
        crew = load_crew()
        opened, closed = crew.triage_items([[{"number": 7, "title": "a", "labels": [{"name": "P1"}],
                                              "comments": [{"author": {"login": "o"}, "body": None}]}],
                                            [{"id": "12", "title": "b", "state": "CLOSED"}]])
        self.assertEqual((opened[0]["number"], opened[0]["labels"], opened[0]["comments"][0]["body"]),
                         (7, [{"name": "P1"}], ""))
        self.assertEqual((closed[0]["number"], closed[0]["url"]), (12, ""))
        with self.assertRaises(ValueError):
            crew.triage_items({"items": []})

    def test_relayed_decision_names_a_native_item(self):  # #1404 self-gate: `#OPS-3`, not only `#123`
        crew = load_crew()
        record = {"author": {"login": "acme-bot"}, "createdAt": "2026-11-01T00:00:00Z",
                  "body": "<!-- crew:v1 role=researcher pass=triage issue=OPS-3 decision=classify mode=shadow -->"}
        decision = {"author": {"login": "acme-bot"}, "createdAt": "2026-11-02T00:00:00Z",
                    "body": "[Ash/decision] owner: accept #OPS-3 as P2\n<!-- crew:v1 role=coordinator pass=steer cmd=decision -->"}
        items = [{"number": "OPS-3", "title": "Recorded", "body": "", "labels": [], "comments": [record], "url": ""},
                 {"number": "OPS-9", "title": "Decision log", "body": "", "labels": [], "comments": [decision],
                  "url": "", "milestone": "M1"}]
        entries = crew.triage_scan("OPS", items, [], crew.TRIAGE_RULES, {"acme-owner"}, crew.triage_card_fields(),
                                   ("acme-bot", "Ash"))
        self.assertEqual([(e["ref"], e["reason"]) for e in entries], [("OPS#OPS-3", "owner-feedback")])


if __name__ == "__main__":
    if "--conflict-transcript" in sys.argv:  # #1398: each `mdstack poll --once` of the CLI conflict test, verbatim
        test = Poll("test_once_conflict_wakes_builder_once_per_head_and_conflict")
        test.setUp()
        try:
            test.test_once_conflict_wakes_builder_once_per_head_and_conflict()
            for label, r in test.transcript:
                print("$ mdstack poll --once --project <fixture>/project/crew.toml  # %s\nexit: %d\n--- stdout\n%s"
                      "--- stderr\n%s" % (label, r.returncode, r.stdout, r.stderr.replace(test.tmp, "<fixture>")),
                      end="")
        finally:
            test.doCleanups()
    else:
        unittest.main()
