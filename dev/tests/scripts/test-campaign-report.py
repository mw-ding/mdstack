#!/usr/bin/env python3
"""Offline self-test for scripts/campaign-report.py (no network). Run in CI."""
import copy
import importlib.util
import json
import os
import re
import unittest
from unittest.mock import patch

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
ROOT = os.path.dirname(os.path.dirname(TESTS))
spec = importlib.util.spec_from_file_location("campaign_report", os.path.join(ROOT, "scripts", "campaign-report.py"))
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

RECORDS = os.path.join(TESTS, "scripts", "fixtures", "campaign", "a31", "records-m25.json")
REPORT = os.path.join(ROOT, "docs", "metrics", "a31-campaign-report.md")
BASELINE = os.path.join(ROOT, "docs", "metrics", "baseline-m25.md")


def load():
    with open(RECORDS) as fh:
        return json.load(fh)


class RecordedCampaign(unittest.TestCase):
    def test_committed_report_is_the_render_of_the_recorded_capture(self):
        with open(REPORT) as fh:
            self.assertEqual(cr.render(load()), fh.read())

    def test_lane_counts_and_denominators_check_against_the_records(self):
        rec = load()
        out = cr.render(rec)
        self.assertIn("| standard (`crew`) | 44 | 44 | 69 | 15 | 1.57 | 21.7% | 18 | 2 | 23 | 9 | 0 |", out)
        self.assertEqual({r["lane"] for r in rec["prs"]}, {"crew"})
        self.assertIn("| express | 0 | n/a |", out)
        self.assertIn("| solo | 0 | n/a |", out)
        self.assertIn("Total: 44 PRs (44 merged).", out)
        self.assertEqual(sum(r["verdicts"] for r in rec["prs"]), 69)

    def test_per_pr_rounds_match_the_separately_captured_baseline(self):
        with open(BASELINE) as fh:
            rows = re.findall(r"^\| (\d+) \| \d+ \| merged \|.*\| (\d+) \| (\d+) \| [\d]* \|$", fh.read(), re.M)
        baseline = {int(pr): (int(rounds), int(defects)) for pr, rounds, defects in rows}
        records = {r["pr"]: (r["verdicts"], r["changes_verdicts"]) for r in load()["prs"]}
        self.assertEqual(len(baseline), 44)
        self.assertEqual(records, baseline)

    def test_timing_and_owner_decisions_are_reported(self):
        out = cr.render(load())
        self.assertIn("| Median open to merge (min) | 40 | 44 |", out)
        self.assertIn("| Median dispatch to merge (min) | 48.5 | 44 |", out)
        self.assertIn("40 `[Ash/decision]` records on #985", out)
        self.assertEqual(out.count("](https://github.com/mw-ding/mdstack/issues/985#issuecomment-"), 40)

    def test_missing_data_is_named_never_estimated(self):
        rec = copy.deepcopy(load())
        rec["decisions"] = []
        rec["prs"][0].update(lane="express", dispatch_to_merge_min="", engine_runs="")
        out = cr.render(rec)
        missing = out.split("## Missing data")[1]
        self.assertIn("No solo-lane PR in the records", missing)
        self.assertNotIn("No express-lane PR", missing)
        self.assertIn("1 merged PRs have no `dispatch_to_merge_min`", missing)
        self.assertIn("1 PRs have no recorded engine run.", missing)
        self.assertIn("owner unblocks are unknown, not zero", missing)
        self.assertIn("Token counts: no PR or event record carries them", missing)
        self.assertEqual([l for l in out.splitlines() if "token" in l.lower()],
                         ["- Token counts: no PR or event record carries them, so none are reported."])


class Capture(unittest.TestCase):
    def test_keeps_milestone_crew_prs_and_window_decisions(self):
        mr = cr._load("metrics_refresh", "metrics-refresh.py")
        hits = [{"number": 1, "body": "Closes #10\n<!-- crew:v1 role=builder issue=10 -->", "labels": []},
                {"number": 2, "body": "Closes #11\n<!-- crew:v1 role=builder issue=11 -->", "labels": []},
                {"number": 3, "body": "Closes #10", "labels": []},
                {"number": 4, "body": "<!-- crew:v1 role=builder -->", "labels": []}]
        pr = {"number": 1, "created_at": "2026-11-04T10:00:00Z", "merged_at": "2026-11-04T11:00:00Z",
              "head": {"sha": "a" * 40}, "labels": [{"name": "crew:express"}], "body": hits[0]["body"]}
        comments = [{"created_at": "2026-11-05T00:00:00Z", "html_url": "u1", "body": "🔥 Ash · Decision · go\nmore\n<!-- crew:v1 role=coordinator pass=steer cmd=decision -->"},
                    {"created_at": "2026-11-05T00:01:00Z", "html_url": "u2", "body": "[Ash/decision] busy, no marker"},
                    {"created_at": "2026-11-09T00:00:00Z", "html_url": "u3", "body": "[Ash/decision] late\n<!-- crew:v1 role=coordinator pass=steer cmd=decision -->"}]
        answers = {"search/issues": hits, "repos/o/r/issues/10": {"milestone": {"number": 38}},
                   "repos/o/r/issues/11": {"milestone": {"number": 39}}, "repos/o/r/pulls/1": pr,
                   "repos/o/r/issues/985/comments": comments}
        mr.gh_json = lambda path, *params: answers.get(path, [])
        mr.ci_rollups = lambda repo, n: []
        real = cr._load
        with patch.object(cr, "_load", lambda name, f: mr if name == "metrics_refresh" else real(name, f)):
            rec = cr.capture("o/r", 38, "2026-11-03", "2026-11-07", 985)
        self.assertEqual([(r["pr"], r["issue"], r["lane"]) for r in rec["prs"]], [(1, 10, "express")])
        self.assertEqual(rec["decisions"], [{"at": "2026-11-05T00:00:00Z", "url": "u1"}])


if __name__ == "__main__":
    unittest.main()
