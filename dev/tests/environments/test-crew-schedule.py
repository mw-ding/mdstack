"""Tests for mdstack schedule snapshot (docs/scheduling.md#inputs): every input read from a fixture state dir into one
JSON object, `unknown` per failed read, memory pressure on macOS and Linux; the summary line, defer `since` times and
stuck finishing work (docs/scheduling.md#observability). Fake tmux and gh; run in CI.
"""
import argparse
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW, Base, LivenessBase

FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit(1)
args = sys.argv[1:]
if args[0] == "api":
    print(json.dumps([{"number": 34, "title": "M18.2"}, {"number": 30, "title": "M21"}]))
elif args[:2] == ["issue", "list"] and "--label" in args:
    if os.environ.get("FAKE_GH_HOLDS_FAIL"):
        sys.exit(1)
    print(json.dumps([{"number": int(n)} for n in os.environ.get("FAKE_GH_HELD", "").split()]))
elif args[:2] == ["pr", "list"]:
    print(os.environ.get("FAKE_GH_PRS", "[]"))
elif args[:2] == ["issue", "list"]:
    print(json.dumps([
        {"number": 620, "milestone": {"title": "M18.2"}, "body": "## Depends on\\n\\n#598. Start after.\\n\\n## AC\\n#1"},
        {"number": 622, "milestone": None, "body": "Depends on #620, #621\\n"},
        {"number": 7, "milestone": None, "body": None},
        {"number": 15, "milestone": None, "body": "", "title": "main-red: default-branch CI red after land of #14"},
        {"number": 16, "milestone": None, "body": "", "title": "Fix the main-red notify text"}]))
"""


class Fixture(Base):
    """A state dir with demand in both pools, a reservation, errors, lands, a train and two runs."""
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.tmp, "bin", "gh"), "w") as f:
            f.write(FAKE_GH)
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash"}}, f)
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = lambda minutes: (now - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.event = os.path.join(self.state, "leads", "builder-events", "e1.json")
        self.put("leads/builder-events/e1.json", json.dumps({"event": "pr-merged", "refs": ["#5"]}))
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(m) + "\n" for m in [
            {"id": "b1", "kind": "build", "refs": ["#620"], "ts": stamp(5)},
            {"id": "b2", "kind": "merge-up", "refs": ["#601"], "ts": stamp(4)}]))
        self.put("status/ben-lead.status", "ack: b1\ndone: b1\n")
        self.put("inbox/vera-lead.jsonl", "".join(json.dumps(m) + "\n" for m in [
            {"id": "r1", "kind": "review", "refs": ["#601", "a" * 40, "1"]},
            {"id": "r2", "kind": "work", "refs": [self.event]}]))
        self.put("spawn-queue.jsonl", "".join(json.dumps(e) + "\n" for e in [
            {"role": "builder", "issue": 9, "pr": None, "pass": "build", "queued": stamp(3)},
            {"role": "reviewer", "issue": None, "pr": 8, "pass": "review", "queued": stamp(3)}]))
        self.put("schedule/reservations.json", json.dumps([{"ref": "#9", "pool": "builder", "time": stamp(1)}]))
        self.put("schedule/errors.jsonl", json.dumps({"ts": stamp(2)}) + "\n" + json.dumps({"ts": stamp(30)}) + "\n")
        self.put("inbox/sam.jsonl", "".join(json.dumps(m) + "\n" for m in [
            {"id": "l1", "kind": "land", "refs": ["#11", "c" * 40]},
            {"id": "l2", "kind": "land", "refs": ["#12", "d" * 40]},
            {"id": "l4", "kind": "land", "refs": ["#14"]}]))
        self.put("inbox/synthesizer-pending.jsonl", json.dumps({"id": "l3", "kind": "land", "refs": ["#13"]}) + "\n")
        self.put("status/sam.status", "ack: l1\ndone: #11 " + "c" * 40 + "\nack: l2\nack: l4\ndone: #14 " + "e" * 40 + "\n")
        self.put("trains/train-3.json", json.dumps({"members": [1, 2], "landed": [1]}))
        run = dict(index=10, item="issue #7", repo="acme/widgets", worktree="/wt", claim="/c", engine="codex",
                   model="m", effort="e", harness="codex")
        self.put("runs/ben-7.json", json.dumps(dict(run, role="builder", **{"pass": "build"})))
        self.put("status/ben-7.status", "done: #7 #12 " + "b" * 40 + "\n")
        self.put("runs/vera-8.json", json.dumps(dict(run, index=20, role="reviewer", **{"pass": "review"})))

    def snapshot(self, **env):
        r = self.crew("schedule", "snapshot", "--project", self.project, **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class Snapshot(Fixture):
    def test_every_input_from_fixture_state(self):
        snap = self.snapshot()
        builder = snap["demand"]["builder"]
        self.assertEqual([(d["kind"], d.get("queued", False)) for d in builder], [("merge-up", False), ("build", True)])
        reviewer = snap["demand"]["reviewer"]
        self.assertEqual([d["kind"] for d in reviewer], ["review", "work"])
        self.assertEqual(reviewer[1]["event"]["event"], "pr-merged")
        self.assertEqual({w["name"]: w["state"] for w in snap["workers"]}, {"ben-7": "idle", "vera-8": "exited"})
        self.assertEqual([w["name"] for w in snap["workers"] if w["finished"]], [])
        self.assertEqual(snap["reservations"][0]["ref"], "#9")
        self.assertEqual(snap["trains"], ["train-3.json"])
        self.assertEqual(sorted(land["refs"][0] for land in snap["lands"]), ["#12", "#13"])
        self.assertEqual(snap["errors"], 1)
        self.assertEqual(snap["caps"], {"builder": 5, "reviewer": 2})
        self.assertEqual(snap["memory_high"], "critical")
        self.assertIsInstance(snap["load"], float)
        self.assertIn(snap["memory"] if snap["memory"] == "unknown" else snap["memory"]["os"],
                      ("darwin", "linux", "unknown"))
        tracker = snap["tracker"]
        self.assertEqual([m["title"] for m in tracker["milestones"]], ["M18.2", "M21"])
        self.assertEqual(tracker["max_active"], 1)
        self.assertEqual({i["number"]: (i["milestone"], i["depends"]) for i in tracker["issues"]},
                         {620: ("M18.2", [598]), 622: (None, [620, 621]), 7: (None, []), 15: (None, []), 16: (None, [])})
        self.assertEqual(tracker["red_fixes"], [15])

    def test_holds_read_labels_and_prs_closing_held_issues(self):  # #712
        prs = json.dumps([{"number": 40, "labels": [{"name": "crew:hold"}], "closingIssuesReferences": []},
                          {"number": 41, "labels": [], "closingIssuesReferences": [{"number": 639}]},
                          {"number": 42, "labels": [], "closingIssuesReferences": [{"number": 7}]}])
        self.assertEqual(self.snapshot()["holds"], [])
        self.assertEqual(self.snapshot(FAKE_GH_HELD="639", FAKE_GH_PRS=prs)["holds"], [40, 41, 639])
        self.assertEqual(self.snapshot(FAKE_GH_HOLDS_FAIL="1")["holds"], "unknown")
        with open(self.project, "a") as f:
            f.write('\n[runtime.options]\nhold_label_blocks = false\n')
        self.assertEqual(self.snapshot(FAKE_GH_HELD="639", FAKE_GH_PRS=prs)["holds"], [40, 41, 639])  # #1124

    def test_reviewer_done_line_marks_its_worker_finished(self):  # #719; a builder's done: is not terminal
        self.put("status/vera-8.status", "done: #8 %s validate pass\n" % ("a" * 40))
        self.assertEqual([w["name"] for w in self.snapshot()["workers"] if w["finished"]], ["vera-8"])

    def test_reviewer_work_events_rank_as_the_pass_they_start(self):
        sha = "a" * 40
        events = [{"event": "new-head", "refs": ["#31", sha]}, {"reason": "status", "line": "done: #7 #32 " + sha},
                  {"reason": "status", "line": "done: #33 %s review pass" % sha},
                  {"reason": "status", "line": "done: #34 %s recheck escalate" % sha},
                  {"reason": "status", "line": "done: #35 %s review changes" % sha},
                  {"reason": "status", "line": "done: #36 %s review pass validation required; CI red" % sha}]  # #1343
        for i, e in enumerate(events):
            self.put("leads/reviewer-events/w%d.json" % i, json.dumps(e))
        self.put("inbox/vera-lead.jsonl", "".join(json.dumps(dict(id="w%d" % i, kind="work", refs=[
            os.path.join(self.state, "leads", "reviewer-events", "w%d.json" % i)])) + "\n" for i in range(len(events))))
        self.assertEqual([(d["kind"], d["refs"][0][-8:]) for d in self.snapshot()["demand"]["reviewer"]],
                         [("review", "#31"), ("review", "#32"), ("validate", "#33"), ("review", "#34"),
                          ("work", "/w4.json"), ("validate", "#36")])

    def test_malformed_work_ref_is_classified_without_hiding_other_demand(self):  # #1020
        self.put("hold-note.md", "# hold #1001\n")
        self.put("leads/reviewer-events/list.json", "[1]")
        os.remove(self.event)
        self.put("inbox/vera-lead.jsonl", "".join(json.dumps(m) + "\n" for m in [
            {"id": "r1", "kind": "review", "refs": ["#601", "a" * 40, "1"]},
            {"id": "r2", "kind": "work", "refs": [self.event]},
            {"id": "r3", "kind": "work", "refs": [os.path.join(self.state, "hold-note.md")]},
            {"id": "r4", "kind": "work", "refs": [os.path.join(self.state, "leads", "reviewer-events", "list.json")]}]))
        reviewer = self.snapshot()["demand"]["reviewer"]
        self.assertEqual([(d["id"], d["kind"]) for d in reviewer],
                         [("r1", "review"), ("r2", "invalid-work"), ("r3", "invalid-work"), ("r4", "invalid-work")])
        self.assertTrue(reviewer[1]["error"].startswith("FileNotFoundError"))
        self.assertTrue(reviewer[2]["error"].startswith("JSONDecodeError"))
        self.assertEqual(reviewer[3]["error"], "not a JSON object")

    def test_failed_reads_are_unknown_per_input(self):
        self.put("inbox/vera-lead.jsonl", "{not json\n")
        snap = self.snapshot(FAKE_GH_FAIL="1")
        self.assertEqual(snap["demand"]["reviewer"], "unknown")
        self.assertEqual(len(snap["demand"]["builder"]), 2)
        self.assertEqual(snap["tracker"], "unknown")
        self.put("away-control.json", json.dumps({"issue": 110}))
        self.put("schedule/errors.jsonl", "{not json\n")
        self.put("inbox/sam.jsonl", "{not json\n")
        snap = self.snapshot(FAKE_GH_FAIL="1")
        self.assertEqual(snap["caps"], {"builder": "unknown", "reviewer": "unknown"})
        self.assertEqual(snap["errors"], "unknown")
        self.assertEqual(snap["lands"], "unknown")
        self.assertEqual(snap["reservations"][0]["ref"], "#9")


class Memory(unittest.TestCase):
    @staticmethod
    def load():
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        return mod.commands()["schedule"]

    def setUp(self):
        self.schedule = self.load()

    def test_macos_pressure_levels(self):
        for raw, level in (("1\n", "normal"), ("2\n", "warn"), ("4\n", "critical")):
            done = subprocess.CompletedProcess([], 0, stdout=raw)
            with mock.patch.object(self.schedule.platform, "system", return_value="Darwin"), \
                    mock.patch.object(self.schedule.subprocess, "run", return_value=done):
                self.assertEqual(self.schedule.memory(), {"os": "darwin", "level": level})

    def test_linux_psi_some_avg10(self):
        psi = "some avg10=12.50 avg60=3.00 avg300=1.00 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        with mock.patch.object(self.schedule.platform, "system", return_value="Linux"), \
                mock.patch("builtins.open", mock.mock_open(read_data=psi)):
            self.assertEqual(self.schedule.memory(), {"os": "linux", "some_avg10": 12.5})

    def test_unreadable_pressure_is_unknown(self):
        with mock.patch.object(self.schedule.platform, "system", return_value="Linux"), \
                mock.patch("builtins.open", side_effect=FileNotFoundError):
            self.assertEqual(self.schedule.read(self.schedule.memory), "unknown")


def item(kind, n, ts="2026-11-02T10:00:00Z", **kw):
    return dict(id="%s%d" % (kind, n), kind=kind, refs=["#%d" % n], ts=ts, **kw)


class Rank(unittest.TestCase):
    def setUp(self):
        self.schedule = Memory.load()
        self.snap = dict(
            demand={"builder": [], "reviewer": []},
            workers=[{"name": "ben-30", "item": "issue #30", "pr": 31}, {"name": "ben-40", "item": "issue #40", "pr": None}],
            tracker=dict(milestones=[{"number": 1, "title": "M18"}, {"number": 2, "title": "M21"}], max_active=2,
                         issues=[dict(number=10, milestone="M18", depends=[]), dict(number=20, milestone="M21", depends=[]),
                                 dict(number=30, milestone="M21", depends=[]), dict(number=11, milestone="M18", depends=[])]))

    def ranked(self, builder=(), reviewer=(), **kw):
        self.snap["demand"] = {"builder": list(builder), "reviewer": list(reviewer)}
        return [(r["class"], r["ref"]) for r in self.schedule.rank(self.snap, **kw)]

    def test_eight_classes_finish_before_start(self):
        got = self.ranked(
            builder=[item("build", 20), item("build", 10), item("fix", 31), item("merge-up", 32), item("build", 9)],
            reviewer=[item("review", 33), item("validate", 34), item("recheck", 35)], red_fixes={9})
        self.assertEqual(got, [(1, "#9"), (2, "#35"), (3, "#32"), (4, "#34"), (5, "#33"), (6, "#31"), (7, "#10"), (8, "#20")])

    def test_ci_red_ranks_with_fix_and_red_fix_beats_everything(self):
        got = self.ranked(builder=[item("ci-red", 31, ts="2026-11-02T09:00:00Z"), item("fix", 32, ts="2026-11-02T08:00:00Z")],
                          reviewer=[item("recheck", 35)], red_fixes={31})
        self.assertEqual(got, [(1, "#31"), (2, "#35"), (6, "#32")])

    def test_open_main_red_issue_and_its_pr_rank_class_1_by_default(self):  # #1072
        self.snap["tracker"]["red_fixes"] = [15, 30]
        demand = dict(builder=[item("build", 15), item("fix", 31), item("build", 10)], reviewer=[item("review", 43)])
        self.assertEqual(self.ranked(**demand), [(1, "#15"), (1, "#31"), (5, "#43"), (7, "#10")])
        self.snap["tracker"]["red_fixes"] = []
        self.assertEqual(self.ranked(**demand), [(5, "#43"), (6, "#31"), (7, "#10"), (8, "#15")])

    def test_unknown_milestone_with_one_active_is_class_7(self):
        self.snap["tracker"]["max_active"] = 1
        self.assertEqual(self.ranked(builder=[item("build", 99), item("build", 20), item("build", 10)]),
                         [(7, "#99"), (7, "#10"), (8, "#20")])

    def test_unknown_milestone_is_latest_active(self):
        self.assertEqual(self.ranked(builder=[item("build", 99), item("build", 10)]), [(7, "#10"), (8, "#99")])

    def test_milestone_tie_break_maps_pr_to_issue(self):
        got = self.ranked(builder=[item("fix", 31, ts="2026-11-02T08:00:00Z"), item("fix", 50, ts="2026-11-02T09:00:00Z"),
                                   item("fix", 12, ts="2026-11-02T10:00:00Z")])
        self.assertEqual(got, [(6, "#31"), (6, "#50"), (6, "#12")])
        self.snap["workers"].append({"name": "ben-10", "item": "issue #10", "pr": 12})
        self.assertEqual(self.ranked(builder=[item("fix", 31), item("fix", 12)]), [(6, "#12"), (6, "#31")])

    def test_critical_path_counts_transitive_waiters(self):
        self.snap["tracker"]["issues"] += [dict(number=60, milestone="M18", depends=[11]),
                                           dict(number=61, milestone="M18", depends=[60]),
                                           dict(number=62, milestone=None, depends=[10, 61])]
        self.assertEqual(self.schedule.critical_path(self.snap["tracker"]["issues"]), {11: 3, 60: 2, 61: 1, 10: 1})
        got = self.ranked(builder=[item("build", 10, ts="2026-11-02T08:00:00Z"), item("build", 11, ts="2026-11-02T09:00:00Z")])
        self.assertEqual(got, [(7, "#11"), (7, "#10")])

    def test_critical_path_survives_a_cycle(self):
        issues = [dict(number=1, milestone=None, depends=[2]), dict(number=2, milestone=None, depends=[1])]
        self.assertEqual(self.schedule.critical_path(issues), {1: 1, 2: 1})

    def test_age_breaks_remaining_ties_oldest_first(self):
        got = self.ranked(reviewer=[item("review", 2, ts="2026-11-02T10:00:00Z"), item("review", 1, ts="2026-11-02T09:00:00Z"),
                                    item("review", 3, ts=None)])
        self.assertEqual(got, [(5, "#1"), (5, "#2"), (5, "#3")])

    def test_queued_spawns_rank_by_issue_and_pr(self):
        got = self.ranked(builder=[dict(kind="build", issue=20, pr=None, ts="2026-11-02T08:00:00Z", queued=True),
                                   dict(kind="fix", issue=30, pr=31, ts="2026-11-02T08:00:00Z", queued=True)])
        self.assertEqual(got, [(6, "#31"), (8, "#20")])

    def test_work_wake_beside_eligible_demand_is_skipped(self):
        wake = dict(id="w1", kind="work", refs=["/state/leads/reviewer-events/e1.json"],
                    event={"event": "pr-merged", "refs": ["#5"]})
        self.assertEqual(self.ranked(builder=[item("build", 10)], reviewer=[wake, item("review", 33)]),
                         [(5, "#33"), (7, "#10")])

    def test_spawned_fix_record_maps_pr_to_issue(self):
        self.snap["workers"] = [{"name": "ben-30", "role": "builder", "item": "issue #10, PR #31", "pr": 31}]
        got = self.schedule.rank(dict(self.snap, demand={"builder": [item("fix", 31)], "reviewer": [item("validate", 31)]}))
        self.assertEqual([(r["class"], r["ref"], r["issue"], r["milestone_order"]) for r in got],
                         [(4, "#31", 10, 0), (6, "#31", 10, 0)])

    def test_held_issue_or_pr_is_left_out_and_listed_as_held(self):  # #712
        self.snap["holds"] = [20, 31]
        demand = dict(builder=[item("build", 20, ts="2026-11-02T08:00:00Z"), item("build", 10), item("fix", 31)],
                      reviewer=[item("validate", 31), item("review", 33)])
        self.assertEqual(self.ranked(**demand), [(5, "#33"), (7, "#10")])
        self.assertEqual([(r["kind"], r["ref"]) for r in self.schedule.held(self.snap)],
                         [("build", "#20"), ("fix", "#31"), ("validate", "#31")])
        self.snap["holds"] = [30]  # the PR's issue, mapped through its worker record
        self.assertEqual(self.ranked(**demand), [(5, "#33"), (7, "#10"), (8, "#20")])
        self.snap["holds"] = "unknown"
        self.assertEqual(len(self.ranked(**demand)), 5)

    def test_unknown_inputs_and_unranked_kinds(self):
        self.snap["tracker"] = "unknown"
        self.snap["workers"] = "unknown"
        self.snap["demand"] = {"builder": [item("build", 20), item("work", 5)], "reviewer": "unknown"}
        self.assertEqual([(r["class"], r["ref"]) for r in self.schedule.rank(self.snap)], [(7, "#20")])

    def test_invalid_work_is_unranked_beside_valid_review(self):  # #1020
        bad = dict(id="w1", kind="invalid-work", refs=["/state/hold-note.md"], error="JSONDecodeError: x")
        self.assertEqual(self.ranked(reviewer=[bad, item("review", 43)]), [(5, "#43")])


T0 = datetime.datetime(2026, 11, 3, 8, 0, tzinfo=datetime.timezone.utc)


class Target(unittest.TestCase):
    def setUp(self):
        self.schedule = Memory.load()
        self.opts = dict(self.schedule.TARGET_OPTIONS)
        self.snap = dict(workers=[{"state": "busy"}] * 3 + [{"state": "idle"}], caps={"builder": 4, "reviewer": 2},
                         load=5.0, memory={"os": "darwin", "level": "normal"}, memory_high="warn", errors=0, tracker="unknown",
                         demand={"builder": [item("build", 10)], "reviewer": []})
        self.doc = dict(target=3, changed=self.schedule.stamp(T0), starts=[])

    def step(self, minutes, doc=None, **snap):
        return self.schedule.target(dict(self.snap, **snap), self.opts, self.doc if doc is None else doc,
                                    T0 + datetime.timedelta(minutes=minutes))

    def test_first_run_starts_at_busy_count_within_caps(self):
        first = lambda **snap: self.schedule.target(dict(self.snap, **snap), self.opts, None, T0)["target"]
        self.assertEqual(first(), 3)
        self.assertEqual(first(workers=[]), 1)
        self.assertEqual(first(caps={"builder": 1, "reviewer": 1}), 2)

    def test_hold_between_watermarks(self):
        self.assertEqual(self.step(3), self.doc)
        self.assertEqual(self.step(3, load=2.0, errors=1)["target"], 3)
        self.assertEqual(self.step(3, load=2.0, memory={"os": "linux", "some_avg10": 5.0})["target"], 3)

    def test_grow_when_every_signal_low_and_demand_waits(self):
        grown = self.step(3, load=3.9)
        self.assertEqual((grown["target"], grown["changed"]), (4, "2026-11-03T08:03:00Z"))
        self.assertEqual(self.step(3, load=3.9, demand={"builder": [], "reviewer": []})["target"], 3)
        self.assertEqual(self.step(3, dict(self.doc, target=6), load=1.0)["target"], 6)

    def test_shrink_from_busy_on_any_high_signal(self):
        for snap in (dict(load=6.0), dict(memory={"os": "darwin", "level": "warn"}), dict(errors=3),
                     dict(memory={"os": "linux", "some_avg10": 10.0})):
            self.assertEqual(self.step(3, dict(self.doc, target=6), **snap)["target"], 2, snap)
        self.assertEqual(self.step(3, dict(self.doc, target=1), load=9.0)["target"], 1)

    def test_memory_threshold_by_speed_and_override(self):  # #1282
        values = {"runtime.options.builders": 4, "runtime.options.reviewers": 2}
        high = lambda caps, **opts: self.schedule.memory_high(dict(values, **opts), caps)
        full, light = {"builder": 4, "reviewer": 2}, {"builder": 3, "reviewer": 2}
        self.assertEqual((high(full), high(light), high({"builder": "unknown", "reviewer": 2})),
                         ("critical", "warn", "unknown"))
        self.assertEqual(high({"builder": 10, "reviewer": 2}, **{"runtime.options.builders": 12}), "critical")  # band
        self.assertEqual(high(full, **{"runtime.options.memory_high": "warn"}), "warn")
        self.assertEqual(high(light, **{"runtime.options.memory_high": "critical"}), "critical")

    def test_full_speed_throttles_on_memory_only_at_critical(self):  # #1282
        warn, critical = {"os": "darwin", "level": "warn"}, {"os": "darwin", "level": "critical"}
        big = dict(self.doc, target=6)
        self.assertEqual(self.step(3, load=3.9, memory=warn, memory_high="critical")["target"], 4)
        self.assertEqual(self.step(3, big, memory=critical, memory_high="critical")["target"], 2)
        self.assertEqual(self.step(3, big, memory=warn, memory_high="warn")["target"], 2)
        linux = lambda avg: {"os": "linux", "some_avg10": avg}
        self.assertEqual(self.step(3, big, memory=linux(10.0), memory_high="critical")["target"], 6)
        self.assertEqual(self.step(3, big, memory=linux(40.0), memory_high="critical")["target"], 2)
        self.assertEqual(self.step(3, memory=warn, memory_high="unknown")["target"], 3)

    def test_at_most_one_change_per_interval(self):
        doc = self.step(3, load=1.0)
        for minutes in (3.5, 4, 4.9):
            self.assertEqual(self.step(minutes, doc, load=9.0)["target"], 4)
        self.assertEqual(self.step(5, doc, load=9.0)["target"], 2)

    def test_no_flapping_when_load_hovers(self):
        doc = self.doc
        for i, load in enumerate([4.0, 5.9, 4.5, 5.99, 4.0, 5.0] * 3):
            doc = self.step(3 * (i + 1), doc, load=load)
        self.assertEqual(doc, self.doc)

    def test_unknown_inputs_hold_and_lower_caps_clamp_at_once(self):
        for snap in (dict(load="unknown"), dict(memory="unknown"), dict(errors="unknown"), dict(workers="unknown"),
                     dict(load=9.0, caps={"builder": "unknown", "reviewer": 2})):
            self.assertEqual(self.step(3, **snap)["target"], 3, snap)
        self.assertEqual(self.step(1, caps={"builder": 1, "reviewer": 1})["target"], 2)
        self.assertEqual(self.step(1, caps={"builder": 0, "reviewer": 0})["target"], 1)
        zero = dict(caps={"builder": 0, "reviewer": 0}, load=1.0)
        self.assertEqual(self.step(3, dict(self.doc, target=1), **zero)["target"], 1)
        self.assertEqual(self.step(3, **zero)["target"], 1)

    def test_ramp_limit_counts_starts_in_the_interval(self):
        doc = self.step(3, dict(self.doc, starts=["2026-11-03T08:00:30Z", "2026-11-03T08:02:00Z"]))
        self.assertEqual((doc["starts"], self.schedule.ramp_left(doc, self.opts)), (["2026-11-03T08:02:00Z"], 1))
        self.assertEqual(self.schedule.ramp_left(dict(doc, starts=doc["starts"] * 3), self.opts), 0)

    def test_update_target_writes_target_json(self):
        with tempfile.TemporaryDirectory() as state:
            values = {"runtime.options.schedule_interval": 60}
            first = self.schedule.update_target(state, self.snap, values, T0)
            path = os.path.join(state, "schedule", "target.json")

            def saved():
                with open(path) as f:
                    return json.load(f)
            self.assertEqual(saved(), first)
            later = self.schedule.update_target(state, dict(self.snap, load=1.0), values, T0 + datetime.timedelta(minutes=1))
            self.assertEqual((first["target"], later["target"], saved()), (3, 4, later))


def walked(actions):
    return [(a["action"], a["ref"], a["reasons"]) for a in actions]


class Decide(unittest.TestCase):
    """The walk of docs/scheduling.md#model: caller-only reservations, cross-pool holds, floors, lead down."""
    def setUp(self):
        self.schedule = Memory.load()
        self.opts = dict(self.schedule.TARGET_OPTIONS)
        self.snap = dict(workers=[], caps={"builder": 1, "reviewer": 1})
        self.ranked = [dict(pool="reviewer", ref="#5", kind="review", **{"class": 5}),
                       dict(pool="builder", ref="#7", kind="build", **{"class": 7})]
        self.alive = {"builder": "alive", "reviewer": "alive"}

    def walk(self, pool, reserved=(), target=2, starts=(), leads=None, ceiling=None, ranked=None, **snap):
        return walked(self.schedule.walk(pool, self.ranked if ranked is None else ranked, dict(self.snap, **snap),
                                         [dict(ref=r, pool=p, time="t") for p, r in reserved],
                                         dict(target=target, starts=list(starts)), self.opts,
                                         self.alive if leads is None else leads, ceiling))

    def test_builder_calls_first(self):
        self.assertEqual(self.walk("builder"), [("hold", "#5", []), ("admit", "#7", [])])
        self.assertEqual(self.walk("reviewer", reserved=[("builder", "#7")]), [("admit", "#5", [])])

    def test_reviewer_calls_first(self):
        self.assertEqual(self.walk("reviewer"), [("admit", "#5", []), ("hold", "#7", [])])
        self.assertEqual(self.walk("builder", reserved=[("reviewer", "#5")]), [("admit", "#7", [])])

    def test_repeated_calls_by_one_lead_never_reserve_the_other_pool(self):
        first = self.walk("builder")
        again = self.walk("builder", reserved=[("builder", "#7")])
        self.assertEqual((first, again), ([("hold", "#5", []), ("admit", "#7", [])],
                                          [("hold", "#5", []), ("admit", "#7", ["reserved"])]))

    def test_red_fix_takes_the_budget_before_a_review(self):  # #1072: decide's default rank sees main-red issues
        snap = dict(demand={"builder": [item("build", 15)], "reviewer": [item("review", 43)]}, workers=[],
                    tracker=dict(milestones=[], max_active=1, issues=[], red_fixes=[15]))
        ranked = self.schedule.rank(snap)
        self.assertEqual([(r["class"], r["ref"]) for r in ranked], [(1, "#15"), (5, "#43")])
        self.assertEqual(self.walk("builder", target=1, ranked=ranked), [("admit", "#15", []), ("hold", "#43", ["floor"])])

    def test_floors_with_target_one(self):
        self.assertEqual(self.walk("builder", target=1), [("hold", "#5", []), ("admit", "#7", ["floor"])])
        self.assertEqual(self.walk("reviewer", reserved=[("builder", "#7")], target=1), [("admit", "#5", ["floor"])])

    def test_floor_waives_target_ramp_and_ceiling_for_the_top_item_only(self):
        builds = [dict(pool="builder", ref="#%d" % n, kind="build", **{"class": 7}) for n in (7, 8)]
        caps = {"builder": 3, "reviewer": 1}
        reviewing = [{"role": "reviewer", "state": "busy"}]
        for kw, why in ((dict(target=1), "target"), (dict(target=5, starts=["a", "b"]), "ramp"),
                        (dict(target=5, ceiling="max_suites"), "max_suites")):
            self.assertEqual(self.walk("builder", ranked=builds, caps=caps, workers=reviewing, **kw),
                             [("admit", "#7", ["floor"]), ("defer", "#8", [why])], kw)
        busy = [{"role": "builder", "state": "busy"}, {"role": "builder", "state": "idle"}]
        self.assertEqual(self.walk("builder", ranked=builds, caps=caps, target=1, workers=busy),
                         [("defer", "#7", ["target"]), ("defer", "#8", ["target"])])
        self.assertEqual(self.walk("builder", ranked=builds, caps={"builder": 0, "reviewer": 1}),
                         [("defer", "#7", ["cap"]), ("defer", "#8", ["cap"])])

    def test_reviewer_floor_under_builder_load(self):
        busy = [{"role": "builder", "state": "busy"}] * 3
        self.assertEqual(self.walk("reviewer", target=3, caps={"builder": 3, "reviewer": 1}, workers=busy),
                         [("admit", "#5", ["floor"])])

    def test_other_lead_down_drops_its_hold(self):
        builds = self.ranked[:1] + [dict(pool="builder", ref="#%d" % n, kind="build", **{"class": 7}) for n in (7, 8)]
        caps = {"builder": 2, "reviewer": 1}
        self.assertEqual(self.walk("builder", ranked=builds, caps=caps),
                         [("hold", "#5", []), ("admit", "#7", []), ("defer", "#8", ["target"])])
        for down in ("dead", "missing", "ambiguous", "unknown"):
            self.assertEqual(self.walk("builder", ranked=builds, caps=caps, leads=dict(self.alive, reviewer=down)),
                             [("drop", "#5", ["lead-down"]), ("admit", "#7", []), ("admit", "#8", [])], down)

    def test_demand_a_busy_worker_runs_takes_no_budget(self):  # #988: a running merge-up starved the builder ramp
        ranked = [dict(pool="builder", ref="#972", kind="merge-up", **{"class": 3}),
                  dict(pool="builder", ref="#928", kind="build", **{"class": 7})]
        worker = dict(role="builder", item="issue #936, PR #972", pr=None, state="busy")
        run = lambda w: self.walk("builder", ranked=ranked, caps={"builder": 6, "reviewer": 1}, target=6, starts=["a"],
                                  workers=[w])
        self.assertEqual(self.opts["schedule_ramp"], 2)
        self.assertEqual(run(worker), [("admit", "#928", [])])
        self.assertEqual(run(dict(worker, item="issue #936", pr=972)), [("admit", "#928", [])])
        for other in (dict(worker, state="idle"), dict(worker, role="reviewer")):
            self.assertEqual(run(other)[:1], [("admit", "#972", [])], other)
        review = [dict(pool="reviewer", ref="#972", kind="validate", **{"class": 4})]
        self.assertEqual(self.walk("reviewer", ranked=review, caps={"builder": 1, "reviewer": 2}, target=6,
                                   workers=[dict(worker, role="reviewer", item="PR #972 r3 review", pr=972)]),
                         [("admit", "#972", [])])

    def test_reservation_expiry_and_run_record(self):
        live = lambda workers, minutes=1: [r["ref"] for r in self.schedule.live_reservations(
            [dict(ref="#9", pool="builder", time="2026-11-03T08:00:00Z")], workers, T0 + datetime.timedelta(minutes=minutes))]
        old = dict(role="builder", item="issue #9", pr=None, state="idle", start="2026-11-03T07:00:00Z")
        self.assertEqual(live([]), ["#9"])
        self.assertEqual(live([], minutes=10), [])
        self.assertEqual(live([old]), ["#9"])
        self.assertEqual(live([dict(old, role="reviewer", state="busy")]), ["#9"])
        self.assertEqual(live([dict(old, state="busy")]), [])
        self.assertEqual(live([dict(old, start="2026-11-03T08:00:30Z")]), [])
        self.assertEqual(live([dict(old, item="issue #3, PR #9", state="busy")]), [])

    def test_ceilings(self):
        snap = dict(suites=4, load=0.5, cpus=8)
        hit = lambda values, **kw: self.schedule.ceiling_hit(dict(snap, **kw), values)
        self.assertIsNone(hit({}))
        self.assertEqual(hit({"runtime.options.max_suites": 4}), "max_suites")
        self.assertIsNone(hit({"runtime.options.max_suites": 5}))
        self.assertEqual(hit({"runtime.options.max_load": 4}), "max_load")
        self.assertEqual(hit({"runtime.options.max_load": 9}, load="unknown"), "max_load")
        self.assertIsNone(hit({"runtime.options.max_load": 9}))


class Summary(unittest.TestCase):
    def setUp(self):
        self.schedule = Memory.load()
        self.state = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state)
        os.makedirs(os.path.join(self.state, "schedule"))

    def write(self, name, *lines):
        with open(os.path.join(self.state, "schedule", name), "w") as f:
            f.writelines(json.dumps(line) + "\n" for line in lines)

    def test_unknown_inputs_orphans_and_newest_decision(self):
        snap = dict(ts="2026-11-03T10:00:00Z", workers="unknown", reservations=[], memory={"os": "linux", "some_avg10": 2.5},
                    load="unknown", errors=0, orphans=[{"window": "ben-7", "pid": 42}],
                    demand={"builder": "unknown", "reviewer": [{"kind": "validate", "refs": ["#8"]}, {"kind": "work"}]})
        self.write("decisions-20261102.jsonl", dict(action="snapshot", snapshot={}, target=9, caps={}))
        self.write("decisions-20261103.jsonl", dict(action="snapshot", snapshot=snap, target=3,
                                                    caps={"builder": 2, "reviewer": "unknown"}), dict(action="admit"))
        with open(os.path.join(self.state, "schedule", "deferred.json"), "w") as f:
            json.dump({"builder": {"#5": {"kind": "build", "class": 7, "reasons": ["overlap #4 a.py"], "since": "x"},
                                   "#6": ["target"]},
                       "reviewer": {"#8": {"kind": "review", "class": 5, "reasons": ["cap"], "since": "x"}}}, f)
        self.assertEqual(self.schedule.summary(self.state),
                         "schedule: builders unknown/2 reviewers unknown/unknown target 3 (load unknown mem psi 2.5 "
                         "errors 0) queued validate 1 builder unknown; deferred 2 (overlap 1, cap 1); held 0; orphans 1 ben-7 pid 42; "
                         "terminal unknown")

    def test_finished_reviewer_holding_a_slot_is_terminal(self):  # #719
        workers = [dict(name="vera-711-r3-validate", role="reviewer", state="busy", finished=True),
                   dict(name="ben-7", role="builder", state="busy", finished=False)]
        snap = dict(ts="2026-11-03T10:00:00Z", workers=workers, reservations=[], memory={"os": "darwin", "level": "normal"},
                    load=0.5, errors=0, orphans=[], demand={"builder": [], "reviewer": []})
        self.write("decisions-20261103.jsonl", dict(action="snapshot", snapshot=snap, target=3,
                                                    caps={"builder": 3, "reviewer": 3}))
        self.assertEqual(self.schedule.summary(self.state),
                         "schedule: builders 1/3 reviewers 1/3 target 3 (load 0.5/cpu mem normal errors 0) queued none; "
                         "deferred 0; held 0; orphans 0; terminal 1 vera-711-r3-validate")

    def test_memory_threshold_in_the_summary(self):  # #1282
        snap = dict(ts="2026-11-03T10:00:00Z", workers=[], reservations=[], load=0.5, errors=0, orphans=[],
                    demand={"builder": [], "reviewer": []})
        for memory, high, shown in (({"os": "darwin", "level": "warn"}, "critical", "warn (high at critical)"),
                                    ({"os": "linux", "some_avg10": 2.5}, "critical", "psi 2.5 (high at psi 40.0)"),
                                    ("unknown", "warn", "unknown (high at warn)")):
            self.write("decisions-20261103.jsonl", dict(action="snapshot", target=3, caps={"builder": 3, "reviewer": 3},
                                                        snapshot=dict(snap, memory=memory, memory_high=high)))
            self.assertIn("(load 0.5/cpu mem %s errors 0)" % shown, self.schedule.summary(self.state))

    def test_stuck_is_finishing_work_past_the_threshold(self):
        since = lambda s: "2026-11-03T10:%02d:00Z" % s
        with open(os.path.join(self.state, "schedule", "deferred.json"), "w") as f:
            json.dump({"builder": {"#1": {"kind": "fix", "class": 6, "reasons": ["target"], "since": since(0)},
                                   "#2": {"kind": "build", "class": 7, "reasons": ["target"], "since": since(0)}},
                       "reviewer": {"#3": {"kind": "review", "class": 5, "reasons": ["cap"], "since": since(20)}}}, f)
        now = datetime.datetime(2026, 11, 3, 10, 30, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual([d["ref"] for d in self.schedule.stuck(self.state, now, 1800)], ["#1"])
        self.assertEqual([d["ref"] for d in self.schedule.stuck(self.state, now, 600)], ["#1", "#3"])


class Orphans(LivenessBase):
    def snapshot(self):
        r = self.crew("schedule", "snapshot", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_live_tool_session_without_a_run_record_is_an_orphan(self):  # #706 r1
        self.set_pane(10, command="node")
        with open(self.ps, "w") as f:
            json.dump({"children": [[42, 9000010, "S", "codex.real"], [43, 42, "Ss", "python3"]]}, f)
        os.remove(os.path.join(self.state, "runs", "ben-7.json"))
        self.assertEqual(self.snapshot()["orphans"], [{"window": "ben-7", "pid": "9000010"}])
        with open(self.ps, "w") as f:
            json.dump({"children": [[42, 9000010, "S", "codex.real"]]}, f)  # the harness alone is no tool session
        self.assertEqual(self.snapshot()["orphans"], [])


class DecideCommand(Fixture):
    def call(self, *argv):
        r = self.crew("schedule", *argv, "--project", self.project)
        self.assertEqual((r.returncode, r.stderr), (0, "mdstack: config %s\n" % self.project))  # #1324
        return json.loads(r.stdout)

    def saved(self, name):
        with open(os.path.join(self.state, "schedule", name)) as f:
            return json.load(f) if name.endswith(".json") else [json.loads(line) for line in f]

    def test_decide_reserves_logs_and_release_frees(self):
        brief = lambda out: [(a["ref"], a["reasons"]) for a in out["admit"] + out["deferred"]]
        self.assertEqual(brief(self.call("decide", "--pool", "builder")), [("#9", ["reserved"]), ("#601", ["target"])])
        self.assertEqual(self.call("release", "--pool", "builder", "#9")["released"], ["#9"])
        self.assertEqual(self.saved("reservations.json"), [])
        out = self.call("decide", "--pool", "builder")
        self.assertEqual((out["target"], brief(out)), (1, [("#601", []), ("#9", ["target"])]))
        self.assertEqual([(r["ref"], r["pool"]) for r in self.saved("reservations.json")], [("#601", "builder")])
        self.assertEqual(len(self.saved("target.json")["starts"]), 1)
        self.call("decide", "--pool", "builder")
        day = [n for n in os.listdir(os.path.join(self.state, "schedule")) if n.startswith("decisions-")]
        lines = [(x["action"], x.get("ref"), x.get("reasons")) for x in self.saved(day[0]) if x["action"] != "drop"]
        self.assertEqual(lines, [("snapshot", None, None), ("defer", "#601", ["target"]), ("admit", "#9", ["reserved"]),
                                 ("snapshot", None, None), ("admit", "#601", []), ("defer", "#9", ["target"]),
                                 ("snapshot", None, None), ("admit", "#601", ["reserved"])])
        self.assertIn("demand", self.saved(day[0])[0]["snapshot"])

    def test_unreadable_demand_defers_only_that_pool(self):
        self.put("inbox/vera-lead.jsonl", "{not json\n")
        self.assertEqual(self.call("decide", "--pool", "reviewer")["deferred"][0]["reasons"], ["demand-unreadable"])
        self.assertEqual(self.call("decide", "--pool", "builder")["admit"][0]["ref"], "#9")

    def test_reservations_count_as_busy_for_the_first_target(self):
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.put("schedule/reservations.json", json.dumps([dict(ref=r, pool="builder", time=now) for r in ("#9", "#77")]))
        self.assertEqual(self.call("decide", "--pool", "builder")["target"], 2)

    def test_summary_line_and_defer_since(self):  # #628
        self.assertEqual(self.crew("schedule", "summary", "--project", self.project).stdout, "schedule: no decision yet\n")
        self.call("decide", "--pool", "builder")
        since = self.saved("deferred.json")["builder"]["#601"]
        self.assertEqual((since["kind"], since["class"], since["reasons"]), ("merge-up", 3, ["target"]))
        self.call("decide", "--pool", "builder")
        self.assertEqual(self.saved("deferred.json")["builder"]["#601"]["since"], since["since"])
        r = self.crew("schedule", "summary", "--project", self.project)
        self.assertRegex(r.stdout, r"^schedule: builders 1/5 reviewers 0/2 target 1 \(load [\d.]+/cpu mem .+ errors 1\) "
                                   r"queued merge-up 1 review 1 build 1; deferred 1 \(target 1\); held 0; orphans 0; "
                                   r"terminal 0\n$")

    def test_target_one_skips_an_older_held_handoff(self):  # #712: the #639 / #710 stall
        stamp = lambda minutes: (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
                                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.put("inbox/ben-lead.jsonl", "".join(json.dumps(m) + "\n" for m in [
            {"id": "h1", "kind": "build", "refs": ["#639"], "ts": stamp(600)},
            {"id": "c1", "kind": "build", "refs": ["#710"], "ts": stamp(5)}]))
        self.put("status/ben-lead.status", "")
        os.remove(os.path.join(self.state, "spawn-queue.jsonl"))
        self.put("schedule/reservations.json", "[]")
        self.put("schedule/target.json", json.dumps(dict(target=1, changed=stamp(0), starts=[])))
        decide = lambda **env: json.loads(self.crew("schedule", "decide", "--pool", "builder", "--project", self.project,
                                                    **env).stdout)
        out = decide(FAKE_GH_HELD="639")
        self.assertEqual((out["target"], [a["ref"] for a in out["admit"]], out["deferred"]), (1, ["#710"], []))
        self.assertEqual(out["held"], [dict(pool="builder", ref="#639", kind="build")])
        self.assertRegex(self.crew("schedule", "summary", "--project", self.project).stdout,
                         r"queued review 1 build 1; deferred 0; held 1 #639; ")
        self.call("release", "--pool", "builder", "#710")
        out = decide()  # hold lifted: the same pending handoff ranks again, no new handoff
        self.assertEqual(([a["ref"] for a in out["admit"]], out["held"]), (["#639"], []))
        self.call("release", "--pool", "builder", "#639")
        out = decide(FAKE_GH_HELD="639", FAKE_GH_HOLDS_FAIL="1")  # an unreadable hold read grants nothing (r1)
        self.assertEqual((out["admit"], [d["reasons"] for d in out["deferred"]], out["held"]),
                         ([], [["holds-unreadable"]], []))
        self.assertRegex(self.crew("schedule", "summary", "--project", self.project).stdout, r"; held unknown; ")

    def mod_schedule(self):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        return mod.commands()["schedule"]

    def test_admissible_writes_only_target_progression(self):  # #1502
        schedule = self.mod_schedule()
        sched = os.path.join(self.state, "schedule")
        def files():
            found = {}
            for n in os.listdir(sched):
                with open(os.path.join(sched, n)) as f:
                    found[n] = f.read()
            return found
        before = files()
        args = argparse.Namespace(project=self.project, org_profile=None)
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(schedule.admissible(args, "builder"), {"#9"})
            self.assertEqual(schedule.admissible(args, "builder"), {"#9"})
        after = files()
        self.assertEqual(json.loads(after.pop("target.json"))["target"], 1)
        after.pop("lock", None)
        self.assertEqual(after, before)  # no reservation, decision log or deferral
        self.assertEqual([(a["ref"], a["reasons"]) for a in self.call("decide", "--pool", "builder")["deferred"]],
                         [("#601", ["target"])])  # the same walk decide takes

    def test_backstop_recovers_a_throttled_target_without_decide(self):  # #1502 review R1
        s = self.mod_schedule()
        start = datetime.datetime(2026, 11, 11, tzinfo=datetime.timezone.utc)
        snap = dict(workers=[dict(role="builder", state="busy", item="#1")] * 3, caps=dict(builder=4, reviewer=2),
                    reservations=[], holds=[], tracker="unknown", load=1.0, memory=dict(os="darwin", level="normal"),
                    memory_high="warn", errors=0,
                    demand=dict(builder=[dict(id="d1", kind="build", refs=["#8"])], reviewer=[]))
        state = os.path.join(self.tmp, "throttled")
        os.makedirs(os.path.join(state, "schedule"))
        with open(os.path.join(state, "schedule", "target.json"), "w") as f:
            json.dump(dict(target=2, changed=s.stamp(start), starts=[]), f)  # T shrunk to busy - 1 under high load
        args = argparse.Namespace(project="fake", org_profile=None)
        real, seen = datetime.datetime, []
        with mock.patch.object(s, "profile", return_value=({}, "fake", state)), \
                mock.patch.object(s, "snapshot", return_value=snap), \
                mock.patch.object(s, "lead_states", return_value=dict(builder="alive", reviewer="alive")):
            for minutes in (3, 6):  # load low, busy unchanged: T 2 -> 3 -> 4, one step per schedule_interval
                class Clock(real):
                    @classmethod
                    def now(cls, tz=None):
                        return start + datetime.timedelta(minutes=minutes)
                with mock.patch.object(s.datetime, "datetime", Clock):
                    seen.append(sorted(s.admissible(args, "builder")))
        with open(os.path.join(state, "schedule", "target.json")) as f:
            self.assertEqual((seen, json.load(f)["target"]), ([[], ["#8"]], 4))
        self.assertEqual(sorted(os.listdir(os.path.join(state, "schedule"))), ["lock", "target.json"])

    def test_decide_and_release_require_a_pool(self):
        r = self.crew("schedule", "decide", "--project", self.project)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "crew: schedule decide requires --pool\n",
                                                                "mdstack: config %s\n" % self.project))



TEAM_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
with open(os.environ["FAKE_GH_CONF"]) as f:
    conf = json.load(f)
path = next((a for a in args[1:] if a.startswith("repos/")), "")
repo = args[args.index("-R") + 1] if "-R" in args else "/".join(path.split("?")[0].split("/")[1:3])
r = conf.get(repo, {})
if args[0] == "api" and "/comments" in path:  # the control item's ownership record
    if r.get("posts") is None:
        sys.exit(1)
    print(json.dumps([[dict(user=dict(login="acme-bot"), body=b, created_at="2026-11-14T00:00:00Z", id=i)
                       for i, b in enumerate(r["posts"])]]))
elif args[0] == "api":
    print(json.dumps(r.get("milestones", [{"number": 1, "title": "M1"}, {"number": 2, "title": "M2"}])))
elif args[:2] == ["issue", "list"] and "--label" in args:
    if r.get("holds_fail"):
        sys.exit(1)
    print(json.dumps([{"number": n} for n in r.get("labels", {}).get(args[args.index("--label") + 1], [])]))
elif args[:2] == ["pr", "list"] and "number,headRefOid" in args:  # open PR heads
    if r.get("heads_fail"):
        sys.exit(1)
    print(json.dumps(r.get("prs", [{"number": 7, "headRefOid": "1" * 40}])))
elif args[:2] == ["pr", "list"]:
    print("[]")
elif args[:2] == ["issue", "list"]:
    print(json.dumps(r.get("issues", [])))
else:
    sys.exit(1)
"""
READS = (["api"], ["issue", "list"], ["pr", "list"])  # every backend call admission may make; anything else mutates
SHA = "1" * 40


class Team(Base):
    """Two disposable repos in one team file, acme/widgets (A) and acme/gadgets (B), sharing issue 42, change 7, head,
    pass and round (team §9.3, §9.7); a fake gh logs every backend call, so a decision proves it mutated nothing."""
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.tmp, "bin", "gh"), "w") as f:
            f.write(TEAM_GH)
        self.gh_log, self.gh_conf = os.path.join(self.tmp, "gh.log"), os.path.join(self.tmp, "gh.json")
        self.env.update(FAKE_GH_LOG=self.gh_log, FAKE_GH_CONF=self.gh_conf)
        self.gh({})
        with open(self.state_file, "w") as f:
            json.dump({"crew-team-eng": {"0": "ash-eng"}}, f)
        self.team = os.path.join(self.tmp, "teams", "eng.toml")
        self.write_team()
        self.root = os.path.join(self.tmp, "team", "eng")
        self.a, self.b = (os.path.join(self.root, s) for s in ("acme__widgets", "acme__gadgets"))
        for state in (self.a, self.b):  # the same issue 42 build in each repo's builder lead inbox
            self.inbox(state, "ben-lead", [dict(id="b42", kind="build", refs=["#42"], ts="2026-11-13T10:00:00Z")])
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write(os.path.join(self.root, "schedule", "target.json"), json.dumps(dict(target=4, changed=now, starts=[])))

    def write_team(self, builders=2, extra="", runtime=""):
        os.makedirs(os.path.dirname(self.team), exist_ok=True)
        checkouts = [os.path.join(self.tmp, c) for c in ("wa", "wb")]
        for c in checkouts:
            os.makedirs(c, exist_ok=True)
        with open(self.team, "w") as f:
            f.write('[team]\nname = "eng"\nruntime = { name = "tmux"%s, options = { builders = %d, reviewers = 2 } }\n'
                    'engines = { coordinator = "claude-code" }\n'
                    'identities = { owners = ["acme-owner"], coordinator = { gh_user = "acme-bot", name = "Ash" }, '
                    'builder = { gh_user = "acme-bot", name = "Ben" }, reviewer = { gh_user = "acme-reviewer", name = '
                    '"Vera" }, synthesizer = { gh_user = "acme-bot", name = "Sam" } }\n'
                    'paths = { state_dir = "%s", worktree_root = "%s" }\n'
                    '[repos.widgets]\nrepo = "acme/widgets"\ncheckout = "%s"\n'
                    '[repos.gadgets]\nrepo = "acme/gadgets"\ncheckout = "%s"\n%s'
                    % (runtime, builders, os.path.join(self.tmp, "team"), os.path.join(self.tmp, "team-wt"), *checkouts, extra))

    def gh(self, conf):
        with open(self.gh_conf, "w") as f:
            json.dump(conf, f)

    def inbox(self, state, name, messages):
        os.makedirs(os.path.join(state, "inbox"), exist_ok=True)
        with open(os.path.join(state, "inbox", name + ".jsonl"), "w") as f:
            f.writelines(json.dumps(m) + "\n" for m in messages)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def call(self, repo, *argv, code=0):
        r = self.crew("schedule", *argv, "--project", "%s#%s" % (self.team, repo))
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout) if r.stdout.startswith("{") else r.stdout

    def ledger(self):
        with open(os.path.join(self.root, "schedule", "reservations.json")) as f:
            return [(r["repo"], r["pool"], r["ref"]) for r in json.load(f)]

    def mutations(self):
        with open(self.gh_log) as f:
            return [a for a in map(json.loads, f) if not any(a[:len(p)] == p for p in READS)]

    def mod(self):
        return Memory.load()

    def test_one_team_lock_target_and_ledger_with_every_action_naming_its_repo(self):
        out = self.call("widgets", "decide", "--pool", "builder")
        self.assertEqual((out["team"], out["repo"], out["blocked"]), ("eng", "acme/widgets", []))
        self.assertEqual([(a["repo"], a["ref"], a["project"]) for a in out["admit"]],
                         [("acme/widgets", "#42", self.team + "#widgets")])
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "schedule")))[-3:],
                         ["lock", "reservations.json", "target.json"])
        self.assertFalse(any(os.path.exists(os.path.join(s, "schedule", "reservations.json")) for s in (self.a, self.b)))
        out = self.call("gadgets", "decide", "--pool", "builder")  # same issue 42, other repo: its own grant
        self.assertEqual([(a["repo"], a["ref"], a["reasons"]) for a in out["admit"]], [("acme/gadgets", "#42", [])])
        self.assertEqual(self.ledger(), [("acme/widgets", "builder", "#42"), ("acme/gadgets", "builder", "#42")])
        again = self.call("widgets", "decide", "--pool", "builder")
        self.assertEqual([(a["repo"], a["reasons"]) for a in again["admit"]], [("acme/widgets", ["reserved"])])
        self.assertEqual(len(self.ledger()), 2)  # repeated grants never add a reservation
        snap = self.call("widgets", "snapshot")
        self.assertEqual((sorted(snap["repos"]), snap["caps"]), (["acme/gadgets", "acme/widgets"],
                                                                 {"builder": 2, "reviewer": 2}))
        self.assertEqual(self.mutations(), [])

    def test_a_held_leaves_b_eligible_and_takes_no_reservation(self):
        self.write_team(builders=1)
        self.gh({"acme/widgets": {"labels": {"crew:hold": [42]}}})
        a = self.call("widgets", "decide", "--pool", "builder")
        self.assertEqual((a["admit"], a["held"]), ([], [dict(pool="builder", ref="#42", kind="build", repo="acme/widgets")]))
        b = self.call("gadgets", "decide", "--pool", "builder")
        self.assertEqual([(x["repo"], x["ref"]) for x in b["admit"]], [("acme/gadgets", "#42")])
        self.assertEqual(self.ledger(), [("acme/gadgets", "builder", "#42")])
        self.call("gadgets", "release", "--pool", "builder", "#42")
        self.gh({"acme/widgets": {"labels": {"crew:escalated": [42]}}})  # escalation filters a team repo the same way
        self.assertEqual(self.call("widgets", "decide", "--pool", "builder")["admit"], [])
        self.call("gadgets", "release", "--pool", "builder", "#42")
        self.gh({})  # control: A unheld is admitted through the same entry point
        self.assertEqual([x["repo"] for x in self.call("widgets", "decide", "--pool", "builder")["admit"]],
                         ["acme/widgets"])
        self.assertEqual(self.mutations(), [])

    def test_a_and_b_racing_for_the_last_slot_never_over_admit(self):
        self.write_team(builders=1)
        argv = lambda repo: [sys.executable, CREW, "schedule", "decide", "--pool", "builder", "--project",
                             "%s#%s" % (self.team, repo)]
        procs = [subprocess.Popen(argv(r), env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for r in ("widgets", "gadgets", "widgets", "gadgets")]
        outs = [json.loads(p.communicate()[0]) for p in procs]
        self.assertEqual(len(self.ledger()), 1)  # one team cap of 1: exactly one grant, whoever won
        winner = self.ledger()[0][0]
        loser = [o for o in outs if o["repo"] != winner]
        self.assertTrue(loser and all(o["admit"] == [] and [d["reasons"] for d in o["deferred"]] == [["cap"]]
                                      for o in loser), outs)

    def test_team_caps_count_every_repo_once(self):
        self.write_team(builders=1)
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write(os.path.join(self.root, "schedule", "reservations.json"), json.dumps(
            [dict(ref="#9", pool="builder", time=now, repo="acme/widgets", project="x", kind="build", round=None)]))
        b = self.call("gadgets", "decide", "--pool", "builder")  # A's grant fills the one team builder slot
        self.assertEqual((b["admit"], [d["reasons"] for d in b["deferred"]]), ([], [["cap"]]))
        self.call("gadgets", "release", "--pool", "builder", "#9")  # B's release of #9 cannot free A's grant
        self.assertEqual(self.ledger(), [("acme/widgets", "builder", "#9")])
        self.call("widgets", "release", "--pool", "builder", "#9")  # control: A's own release frees it
        self.assertEqual([x["repo"] for x in self.call("gadgets", "decide", "--pool", "builder")["admit"]],
                         ["acme/gadgets"])

    def test_unreadable_a_state_blocks_only_a(self):
        cases = [("paused", lambda: self.write(os.path.join(self.a, "pause.json"), json.dumps({"at": "t"})),
                  lambda: os.remove(os.path.join(self.a, "pause.json"))),
                 ("holds-unreadable", lambda: self.gh({"acme/widgets": {"holds_fail": True}}), lambda: self.gh({})),
                 ("demand-unreadable", lambda: self.write(os.path.join(self.a, "inbox", "ben-lead.jsonl"), "{bad\n"),
                  lambda: self.inbox(self.a, "ben-lead", [dict(id="b42", kind="build", refs=["#42"])]))]
        for why, break_a, mend_a in cases:
            break_a()
            a = self.call("widgets", "decide", "--pool", "builder")
            self.assertEqual((a["admit"], a["deferred"]), ([], [dict(pool="builder", ref=None, action="defer",
                                                                     reasons=[why], repo="acme/widgets")]), why)
            self.assertIn(dict(repo="acme/widgets", pool="builder", reasons=[why]), a["blocked"])
            b = self.call("gadgets", "decide", "--pool", "builder")
            self.assertEqual([x["repo"] for x in b["admit"]], ["acme/gadgets"], why)
            self.call("gadgets", "release", "--pool", "builder", "#42")
            mend_a()
            self.assertEqual([x["repo"] for x in self.call("widgets", "decide", "--pool", "builder")["admit"]],
                             ["acme/widgets"], why)  # the same-repo control
            self.call("widgets", "release", "--pool", "builder", "#42")
        self.assertRegex(self.crew("schedule", "summary", "--project", self.team + "#gadgets").stdout,
                         r"^schedule: builders \d/2 .*; terminal 0\n$")

    def test_ownership_read_only_blocks_that_repo_only(self):
        self.write_team(extra="control_item = 5\n", runtime=', instance = "eng"')  # B's control record is unreadable
        b = self.call("gadgets", "decide", "--pool", "builder")
        self.assertEqual([d["reasons"] for d in b["deferred"]], [["ownership-read-only"]])
        self.assertEqual([x["repo"] for x in self.call("widgets", "decide", "--pool", "builder")["admit"]],
                         ["acme/widgets"])

    def test_unknown_aggregate_state_refuses_the_team_and_keeps_the_ledger(self):
        path = os.path.join(self.root, "schedule", "reservations.json")
        self.write(path, "{not a ledger")
        for repo in ("widgets", "gadgets"):
            out = self.call(repo, "decide", "--pool", "builder")
            self.assertEqual((out["admit"], [d["reasons"] for d in out["deferred"]]), ([], [["reservations-unreadable"]]))
        with open(path) as f:
            self.assertEqual(f.read(), "{not a ledger")  # never rewritten as an empty ledger
        os.remove(path)
        self.write_team(extra="spec = 3\n")  # B's section no longer resolves: its runs cannot be counted
        out = self.call("widgets", "decide", "--pool", "builder")
        self.assertEqual((out["admit"], [d["reasons"] for d in out["deferred"]]), ([], [["caps-unreadable"]]))
        self.assertEqual([b["reasons"] for b in out["blocked"]], [["profile-unreadable"]])
        with open(path) as f:
            self.assertEqual(json.load(f), [])  # nothing granted
        self.write_team()  # control: both resolve again
        self.assertEqual([x["repo"] for x in self.call("widgets", "decide", "--pool", "builder")["admit"]],
                         ["acme/widgets"])

    def test_red_default_repair_in_a_ranks_first_and_b_still_starts(self):
        self.gh({"acme/widgets": {"issues": [{"number": 15, "milestone": None, "body": "", "title": "main-red: CI"}]}})
        self.inbox(self.a, "ben-lead", [dict(id="b15", kind="build", refs=["#15"], ts="2026-11-13T11:00:00Z")])
        self.inbox(self.b, "vera-lead", [dict(id="r7", kind="review", refs=["#7", SHA, "1"], ts="2026-11-13T09:00:00Z")])
        snap = self.call("gadgets", "snapshot")
        ranked = self.mod().rank(snap)
        self.assertEqual([(r["class"], r["repo"], r["ref"]) for r in ranked],
                         [(1, "acme/widgets", "#15"), (5, "acme/gadgets", "#7"), (7, "acme/gadgets", "#42")])
        self.assertEqual([x["ref"] for x in self.call("gadgets", "decide", "--pool", "builder")["admit"]], ["#42"])

    def test_parked_wait_is_not_team_demand(self):
        self.inbox(self.a, "ben-lead", [dict(id="f7", kind="fix", refs=["#7"]), dict(id="b42", kind="build", refs=["#42"])])
        self.write(os.path.join(self.a, "status", "ben-lead.status"), "ack: f7\nwaiting: #7 ci id=f7\n")
        self.write(os.path.join(self.a, "leads", "waits.json"), json.dumps(
            {"ben-lead": {"f7": {"line": 1, "seen": [None, False, None, False], "woke": False}}}))
        snap = self.call("gadgets", "snapshot")
        self.assertEqual([d["id"] for d in snap["repos"]["acme/widgets"]["demand"]["builder"]], ["b42"])
        self.write(os.path.join(self.a, "leads", "waits.json"), json.dumps(
            {"ben-lead": {"f7": {"line": 1, "seen": [None, False, None, False], "woke": True}}}))
        snap = self.call("gadgets", "snapshot")  # control: once its state changed, the wait is demand again
        self.assertEqual([d["id"] for d in snap["repos"]["acme/widgets"]["demand"]["builder"]], ["f7", "b42"])

    def milestones(self, first=True):
        """A's issue 42 in M1 (class 7) and 43 in M2 (class 8); B has no demand."""
        self.inbox(self.b, "ben-lead", [])
        builds = [dict(id="b42", kind="build", refs=["#42"])] if first else []
        self.inbox(self.a, "ben-lead", builds + [dict(id="b43", kind="build", refs=["#43"])])
        self.gh({"acme/widgets": {"issues": [dict(number=42, milestone={"title": "M1"}, body="", title="First"),
                                              dict(number=43, milestone={"title": "M2"}, body="", title="Later")]}})

    def test_class_8_waits_while_team_class_7_is_eligible(self):
        self.milestones()
        out = self.call("widgets", "decide", "--pool", "builder")  # two free slots, but #42 has not started
        self.assertEqual([(a["ref"], a["class"]) for a in out["admit"]], [("#42", 7)])
        self.assertEqual([(d["ref"], d["class"], d["reasons"]) for d in out["deferred"]], [("#43", 8, ["class-7"])])
        self.milestones(False)  # control: with no class 7 left, M2 fills the slot
        out = self.call("widgets", "decide", "--pool", "builder")
        self.assertEqual([(a["ref"], a["class"], a["reasons"]) for a in out["admit"]], [("#43", 8, [])])

    def test_every_ac2_predicate_refuses_only_its_item_unknown_or_mismatched(self):
        """One table over AC2's predicates (team §9.4) through `mdstack schedule decide`: B's item under an unknown or
        mismatched predicate is refused and takes no reservation, A then wins the one team slot (the cross-repo
        last-slot control), and B's item under the passing predicate is admitted."""
        live, other = SHA, "2" * 40
        claim = lambda to: ("<!-- crew:v1 role=coordinator pass=handoff handoff=20261114-abcdef state=claimed from=none "
                            "to=%s cmd-id=c1 sha=%s round=n/a verdict=n/a -->" % (to, SHA))
        issue = lambda n, body="": dict(number=n, milestone={"title": "M1"}, body=body, title=str(n))
        dep = lambda *ns: {"acme/gadgets": {"issues": [issue(n) for n in ns] + [issue(42, "Depends on #41")]}}
        owned = 'control_item = 5\n'
        pause = lambda text: lambda: self.write(os.path.join(self.b, "pause.json"), text)
        gh = lambda conf: lambda: self.gh(conf)
        cfg = lambda extra: lambda: self.write_team(builders=1, extra=extra, runtime=', instance = "eng"')
        both = lambda *fs: lambda: [f() for f in fs]
        request = lambda head: lambda: self.inbox(self.b, "vera-lead", [dict(id="v7", kind="validate", refs=[
            "#7", *([head] if head else []), "1"][:3 if head else 1])])
        fix = lambda refs: lambda: self.inbox(self.b, "ben-lead", [dict(id="f7", kind="fix", refs=refs)])
        fix7 = ("#7", "fix")
        rows = [  # predicate, case, pool, setup, B's refusal (None: admitted), where it is reported
            ("ownership", "unknown", "builder", cfg(owned), "ownership-read-only", "blocked"),
            ("ownership", "mismatch", "builder", both(cfg(owned), gh({"acme/gadgets": {"posts": [claim("tmux@other")]}})),
             "ownership-read-only", "blocked"),
            ("ownership", "pass", "builder", both(cfg(owned), gh({"acme/gadgets": {"posts": [claim("tmux@eng")]}})),
             None, None),
            ("pause", "unknown", "builder", pause("{bad"), "paused", "blocked"),
            ("pause", "mismatch", "builder", pause(json.dumps({"at": "t"})), "paused", "blocked"),
            ("pause", "pass", "builder", lambda: None, None, None),
            ("hold", "unknown", "builder", gh({"acme/gadgets": {"holds_fail": True}}), "holds-unreadable", "blocked"),
            ("hold", "mismatch", "builder", gh({"acme/gadgets": {"labels": {"crew:hold": [42]}}}), "held", "held"),
            ("hold", "pass", "builder", gh({"acme/gadgets": {"labels": {"crew:hold": [99]}}}), None, None),
            ("escalation", "unknown", "builder", gh({"acme/gadgets": {"holds_fail": True}}), "holds-unreadable", "blocked"),
            ("escalation", "mismatch", "builder", gh({"acme/gadgets": {"labels": {"crew:escalated": [42]}}}), "held", "held"),
            ("escalation", "pass", "builder", gh({"acme/gadgets": {"labels": {"crew:escalated": [99]}}}), None, None),
            ("tracker", "unknown", "builder", gh({"acme/gadgets": {"issues": None}}), "tracker-unreadable", "blocked"),
            ("tracker", "pass", "builder", gh({"acme/gadgets": {"issues": [issue(42)]}}), None, None),
            ("dependency", "unknown", "builder", gh({"acme/gadgets": {"issues": None}}), "tracker-unreadable",
             "blocked"),
            ("dependency", "mismatch", "builder", gh(dep(41)), "depends-open", "waiting"),
            ("dependency", "pass", "builder", gh(dep()), None, None),
            ("head", "unknown", "reviewer", gh({"acme/gadgets": {"heads_fail": True}}), "heads-unreadable", "waiting"),
            ("head", "unknown", "reviewer", request("unknown"), "head-unreadable", "waiting"),  # requested head
            ("head", "unknown", "reviewer", request(None), "head-unreadable", "waiting"),  # no head named
            ("head", "unknown", "builder", fix(["#7"]), "head-unreadable", "waiting", fix7),  # fix without its head
            ("head", "mismatch", "builder", fix(["#7", other]), "stale-head", "waiting", fix7),
            ("head", "pass", "builder", fix(["#7", live]), None, None, fix7),
            ("head", "mismatch", "reviewer", gh({"acme/gadgets": {"prs": [{"number": 7, "headRefOid": other}]}}),
             "stale-head", "waiting"),
            ("head", "mismatch", "reviewer", gh({"acme/gadgets": {"prs": []}}), "stale-head", "waiting"),  # PR not open
            ("head", "pass", "reviewer", gh({"acme/gadgets": {"prs": [{"number": 7, "headRefOid": live}]}}),
             None, None)]
        ref, ledger = {"builder": "#42", "reviewer": "#7"}, os.path.join(self.root, "schedule", "reservations.json")

        def cap1():  # one team slot per pool, so A taking it after B's refusal is the last-slot control
            with open(self.team) as f:
                text = f.read()
            with open(self.team, "w") as f:
                f.write(text.replace("reviewers = 2", "reviewers = 1"))
        kinds = {"builder": "build", "reviewer": "validate"}
        for pred, case, pool, setup, why, where, *mine in rows:
            b_ref, b_kind = mine[0] if mine else (ref[pool], kinds[pool])
            with self.subTest("%s/%s" % (pred, case)):
                self.write_team(builders=1)
                self.gh({})
                for path in (os.path.join(self.b, "pause.json"), ledger):
                    if os.path.exists(path):
                        os.remove(path)
                for state in (self.a, self.b):
                    builds = [dict(id="b42", kind="build", refs=["#42"])] if pool == "builder" else []
                    passes = [dict(id="v7", kind="validate", refs=["#7", live, "1"])] if pool == "reviewer" else []
                    self.inbox(state, "ben-lead", builds)
                    self.inbox(state, "vera-lead", passes)
                setup()
                cap1()
                b = self.call("gadgets", "decide", "--pool", pool)
                if why is None:
                    self.assertEqual([(x["repo"], x["ref"], x["kind"]) for x in b["admit"]],
                                     [("acme/gadgets", b_ref, b_kind)])
                    continue
                self.assertEqual(b["admit"], [])
                self.assertFalse(os.path.exists(ledger) and self.ledger())
                item = dict(pool=pool, ref=b_ref, kind=b_kind, repo="acme/gadgets")
                if where == "blocked":
                    self.assertEqual([d["reasons"] for d in b["deferred"]], [[why]])
                    self.assertIn(dict(repo="acme/gadgets", pool=pool, reasons=[why]), b["blocked"])
                elif where == "held":
                    self.assertEqual(b["held"], [item])
                else:
                    self.assertEqual([{k: w.get(k) for k in [*item, "reasons"]} for w in b["waiting"]],
                                     [dict(item, reasons=[why])])
                a = self.call("widgets", "decide", "--pool", pool)  # A's same-ID item takes the one team slot
                self.assertEqual([(x["repo"], x["ref"]) for x in a["admit"]], [("acme/widgets", ref[pool])])
        self.assertEqual(self.mutations(), [])

    def test_shared_team_leads_admit_through_one_ledger_and_a_never_takes_bs_last_slot(self):
        """Integration with the shared `(team, pool)` leads (#1858): team.json binds both repos, so each lead's inbox is
        the team root's and its messages name their repo in `context`. A's held build and A's stale-head validation
        take no reservation; B's same-ID current work wins the one team slot in the one team ledger."""
        repos = {"acme/widgets": self.a, "acme/gadgets": self.b}
        self.write(os.path.join(self.root, "team.json"), json.dumps({"team": "eng", "repos": {
            r: {"project": "%s#%s" % (self.team, r.split("/")[1]), "state": st} for r, st in repos.items()}}))
        msg = lambda repo, i, kind, refs: dict(id=i, kind=kind, refs=refs, context=dict(
            repo=repo, project="%s#%s" % (self.team, repo.split("/")[1])))
        for state in repos.values():
            for lead in ("ben-lead", "vera-lead"):
                self.inbox(state, lead, [])
        self.write_team(builders=1)
        with open(self.team) as f:
            text = f.read()
        with open(self.team, "w") as f:
            f.write(text.replace("reviewers = 2", "reviewers = 1"))
        live, stale = "2" * 40, SHA
        self.inbox(self.root, "ben-lead", [msg("acme/widgets", "a42", "build", ["#42"]),
                                           msg("acme/gadgets", "b42", "build", ["#42"])])
        self.inbox(self.root, "vera-lead", [msg("acme/widgets", "a7", "validate", ["#7", stale, "1"]),
                                            msg("acme/gadgets", "b7", "validate", ["#7", live, "1"])])
        pr = [{"number": 7, "headRefOid": live}]
        self.gh({"acme/widgets": {"labels": {"crew:hold": [42]}, "prs": pr}, "acme/gadgets": {"prs": pr}})
        a = self.call("widgets", "decide", "--pool", "builder")  # A's held build: no grant
        self.assertEqual((a["admit"], [(h["repo"], h["ref"]) for h in a["held"]]), ([], [("acme/widgets", "#42")]))
        a = self.call("widgets", "decide", "--pool", "reviewer")  # A's stale validation: no grant
        self.assertEqual((a["admit"], [(w["repo"], w["reasons"]) for w in a["waiting"]]),
                         ([], [("acme/widgets", ["stale-head"])]))
        self.assertFalse(os.path.exists(os.path.join(self.root, "schedule", "reservations.json")) and self.ledger())
        for pool, ref in (("builder", "#42"), ("reviewer", "#7")):  # B takes each pool's last team slot
            b = self.call("gadgets", "decide", "--pool", pool)
            self.assertEqual([(x["repo"], x["ref"], x["reasons"]) for x in b["admit"]], [("acme/gadgets", ref, [])],
                             pool)
        self.assertEqual(self.ledger(), [("acme/gadgets", "builder", "#42"), ("acme/gadgets", "reviewer", "#7")])
        self.assertFalse(any(os.path.exists(os.path.join(st, "schedule", "reservations.json"))
                             for st in repos.values()))
        a = self.call("widgets", "decide", "--pool", "reviewer")  # B holds the one reviewer slot
        self.assertEqual(a["admit"], [])
        self.call("gadgets", "release", "--pool", "reviewer", "#7")
        self.inbox(self.root, "vera-lead", [msg("acme/widgets", "a7", "validate", ["#7", live, "1"])])
        a = self.call("widgets", "decide", "--pool", "reviewer")  # control: A's current head, slot free
        self.assertEqual([(x["repo"], x["ref"]) for x in a["admit"]], [("acme/widgets", "#7")])
        self.assertEqual(self.mutations(), [])

    def route(self, kind, round_, cap=1):
        """The reviewer lead requests `kind` round `round_` of A's #7 while only A's validate round 1 is granted."""
        self.inbox(self.a, "ben-lead", [])
        self.inbox(self.b, "ben-lead", [])
        self.inbox(self.a, "vera-lead", [dict(id="v7", kind="validate", refs=["#7", SHA, "1"])])
        with open(self.team) as f:
            config = f.read()
        with open(self.team, "w") as f:
            f.write(config.replace("reviewers = 2", "reviewers = %d" % cap))
        out = self.call("widgets", "decide", "--pool", "reviewer")
        self.assertEqual([(a["kind"], a["round"]) for a in out["admit"]], [("validate", 1)])
        s = self.mod()
        route = s.commands()["route"]
        args = argparse.Namespace(project=self.team + "#widgets", org_profile=None, reviewer_lead=True)
        values = {"identities.reviewer.name": "Vera", "identities.reviewer.gh_user": "acme-reviewer"}
        with mock.patch.object(route, "profile", return_value=(values, "fake", self.a)), \
                mock.patch.object(s.commands()["poll"], "express_lane", return_value=False), \
                mock.patch.object(s, "schedule_decide", return_value=out), \
                mock.patch.object(route, "ready_check"), \
                mock.patch.object(route, "invoke") as spawn:  # admission grants only; readiness has its own tests (#1878)
            try:
                route.review(args, self.a, dict(number=7, reviews=[]), SHA, kind, round_)
            except RuntimeError as e:
                return spawn, str(e)
        return spawn, None

    def test_reviewer_grant_is_consumed_only_by_its_pass_and_round(self):
        for kind, round_ in (("review", 1), ("validate", 2)):  # another pass, another round: not granted
            spawn, err = self.route(kind, round_)
            self.assertFalse(spawn.called, (kind, round_))
            self.assertEqual(err, "crew: reviewer admission deferred: #7 not-granted")
        spawn, err = self.route("validate", 1)  # control: the granted pass and round spawn
        self.assertEqual((err, spawn.call_args.kwargs["pass_"], spawn.call_args.kwargs["round"]), (None, "validate", 1))


class TeamWalk(unittest.TestCase):
    """The team walk, transfer and release as pure functions over two repos sharing #7 (team §9.4)."""
    def setUp(self):
        self.s = Memory.load()
        self.opts = dict(self.s.TARGET_OPTIONS)
        a, b = "acme/widgets", "acme/gadgets"
        self.a, self.b = a, b
        self.ranked = [dict(pool="reviewer", ref="#7", kind="review", round=1, repo=b, project="t#b", **{"class": 5}),
                       dict(pool="reviewer", ref="#7", kind="review", round=1, repo=a, project="t#a", **{"class": 5}),
                       dict(pool="builder", ref="#42", kind="build", repo=a, project="t#a", **{"class": 7})]
        self.alive = {(r, p): "alive" for r in (a, b) for p in ("builder", "reviewer")}

    def walk(self, pool, repo, reserved=(), workers=(), target=3, caps=None, leads=None):
        return [(x["action"], x["repo"], x["ref"], x["reasons"]) for x in self.s.walk(
            pool, self.ranked, dict(workers=list(workers), caps=caps or {"builder": 2, "reviewer": 2}), list(reserved),
            dict(target=target, starts=[]), self.opts, self.alive if leads is None else leads, None, repo)]

    def test_only_the_callers_lane_is_granted(self):
        self.assertEqual(self.walk("reviewer", self.a), [("hold", self.b, "#7", []), ("admit", self.a, "#7", []),
                                                         ("hold", self.a, "#42", ["floor"])])  # ramp spent: floor
        down = {**self.alive, (self.b, "reviewer"): "missing"}
        self.assertEqual(self.walk("reviewer", self.a, leads=down)[0], ("drop", self.b, "#7", ["lead-down"]))

    def test_team_pool_floor_and_caps_are_team_totals(self):
        busy = [dict(role="reviewer", state="busy", item="PR #3", repo=self.b)]
        self.assertEqual(self.walk("reviewer", self.a, workers=busy, caps={"builder": 2, "reviewer": 1}),
                         [("defer", self.a, "#7", ["cap"]), ("hold", self.a, "#42", [])])  # B's busy reviewer fills it

    def test_same_id_passes_and_rounds_stay_distinct(self):
        res = lambda repo, kind="review", rnd=1: dict(ref="#7", pool="reviewer", time="t", repo=repo, kind=kind, round=rnd)
        mine = lambda reserved: [x for x in self.walk("reviewer", self.a, reserved=[reserved], target=4,
                                                      caps={"builder": 2, "reviewer": 3}) if x[1:3] == (self.a, "#7")]
        for other in (res(self.b), res(self.a, "validate"), res(self.a, rnd=2)):  # another repo, pass or round
            self.assertEqual(mine(other), [("admit", self.a, "#7", [])], other)
        self.assertEqual(mine(res(self.a)), [("admit", self.a, "#7", ["reserved"])])

    def test_reservation_transfers_only_to_its_own_run(self):
        r = dict(ref="#7", pool="reviewer", time="2026-11-03T08:00:00Z", repo=self.a, kind="review", round=1)
        w = dict(role="reviewer", item="PR #7", pr=7, state="busy", repo=self.a, round=1, **{"pass": "review"})
        live = lambda *workers: len(self.s.live_reservations([r], list(workers), T0 + datetime.timedelta(minutes=1)))
        self.assertEqual([live(dict(w, repo=self.b)), live(dict(w, **{"pass": "validate"})), live(dict(w, round=2)),
                          live(w), live(dict(w, round=None))], [1, 1, 1, 0, 0])

    def test_release_frees_only_the_callers_repo_and_pass(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, "schedule"))
        rows = [dict(ref="#7", pool="reviewer", time="t", repo=repo, kind=kind, round=1)
                for repo, kind in ((self.a, "review"), (self.a, "validate"), (self.b, "review"))]
        with open(os.path.join(tmp, "schedule", "reservations.json"), "w") as f:
            json.dump(rows, f)
        values = {"team.name": "eng", "paths.state_dir": tmp, "repo.owner": "acme", "repo.name": "widgets"}
        self.s.release(os.path.join(tmp, "acme__widgets"), "reviewer", ["#7"], values, "review", 1)
        with open(os.path.join(tmp, "schedule", "reservations.json")) as f:
            self.assertEqual([(x["repo"], x["kind"]) for x in json.load(f)], [(self.a, "validate"), (self.b, "review")])

    def test_ties_break_by_class_milestone_then_repo_and_identity(self):
        tracker = lambda issues: dict(milestones=[dict(number=1, title="M1"), dict(number=2, title="M2")], max_active=2,
                                      issues=issues, red_fixes=[])
        repo = lambda project, issues, builds: dict(project=project, ownership="active", paused=None, holds=[],
                                                    tracker=tracker(issues), demand=dict(builder=builds, reviewer=[]))
        snap = dict(workers=[], repos={
            self.a: repo("t#a", [dict(number=42, milestone="M2", depends=[])], [item("build", 42)]),
            self.b: repo("t#b", [dict(number=42, milestone="M1", depends=[]), dict(number=43, milestone="M1", depends=[])],
                         [item("build", 43), item("build", 42)])})
        self.assertEqual([(r["class"], r["repo"], r["ref"]) for r in self.s.rank(snap)],
                         [(7, self.b, "#42"), (7, self.b, "#43"), (8, self.a, "#42")])

    def test_stuck_alarm_is_per_repo(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, "schedule"))
        entry = lambda repo: dict(kind="fix", reasons=["target"], since="2026-11-03T07:00:00Z", repo=repo, ref="#7",
                                  **{"class": 6})
        with open(os.path.join(tmp, "schedule", "deferred.json"), "w") as f:
            json.dump({"builder": {self.a + " #7": entry(self.a), self.b + " #7": entry(self.b)}}, f)
        now = T0.timestamp()
        self.assertEqual([d["repo"] for d in self.s.stuck(tmp, now, 1800, self.b)], [self.b])
        self.assertEqual(len(self.s.stuck(tmp, now, 1800)), 2)


class OneRepoLedger(Fixture):
    def test_unreadable_ledger_refuses_and_is_kept(self):  # a one-repo config is its own singleton team (#1857)
        self.put("schedule/reservations.json", "{oops")
        r = self.crew("schedule", "decide", "--pool", "builder", "--project", self.project)
        out = json.loads(r.stdout)
        self.assertEqual((out["admit"], [d["reasons"] for d in out["deferred"]]), ([], [["reservations-unreadable"]]))
        self.assertNotIn("repo", out["deferred"][0])
        with open(os.path.join(self.state, "schedule", "reservations.json")) as f:
            self.assertEqual(f.read(), "{oops")

if __name__ == "__main__":
    unittest.main()
