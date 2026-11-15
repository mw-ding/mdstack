#!/usr/bin/env python3
"""Tests for core/status-record.py, shared-status record S v1 (docs/specs/shared-status.md §3, #1313; AC S.1).

One table of refusal rows over every §3.2/§3.3 field (missing, extra and wrong-typed keys, versions 0 and 2,
string, boolean, float, negative and too-large counts, completed > total, bad, foreign-repo and credentialed URLs,
malformed and future times, unsorted or duplicate repos, a known section with a reason, an over-limit list, a
secret-pattern match, an oversize body), each paired with the valid minimal (every section unknown) and full
records as controls. The same rows then go through the shipped CLI: `mdstack status --all` reads each as a
destination comment and names it in a `diagnostic:` line with no row marked fresh, and a publisher whose
collectors produce an invalid record refuses with zero writes. Run in CI.
"""
import copy
import importlib.util
import json
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TESTS)
from status_testlib import CLOCK, StatusBase  # noqa: E402

spec = importlib.util.spec_from_file_location("status_record", os.path.join(os.path.dirname(TESTS), "..", "core",
                                                                            "status-record.py"))
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)
spec = importlib.util.spec_from_file_location("crew_config", os.path.join(os.path.dirname(TESTS), "..", "core",
                                                                          "crew-config.py"))
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)
RUNTIMES = ["tmux", "session", "grok-bot"]  # the spec's source.runtime enum: the profile's runtime.name values

T = sr.stamp(CLOCK - 60)
NOW = sr.stamp(CLOCK)


def unknown(reason="read-failed"):
    return {"state": "unknown", "observed_at": T, "reason": reason}


def minimal():
    return {"schema_version": 1, "instance_id": "alpha", "registration_id": "r-" + "a" * 32, "sequence": 1,
            "observed_at": T, "published_at": NOW,
            "source": {"repos": ["acme/widgets"], "runtime": "tmux",
                       "decision_log": "https://github.com/acme/widgets/issues/985"},
            "sections": {name: unknown() for name in sr.SECTIONS}}


def full():
    rec = minimal()
    rec["source"]["repos"] = ["acme/gadgets", "acme/widgets"]
    k = {"state": "known", "observed_at": T}
    rec["sections"] = {
        "milestones": dict(k, items=[{"url": "https://github.com/acme/widgets/milestone/3", "completed": 4, "total": 9}]),
        "prs": dict(k, items=[{"url": "https://github.com/acme/gadgets/pull/7", "stage": s} for s in ["in-review"]]),
        "owner_asks": dict(k, items=[{"url": "https://github.com/acme/widgets/issues/12", "deadline": None},
                                     {"url": "https://github.com/acme/widgets/pull/13", "deadline": NOW}]),
        "blockers": dict(k, items=[{"url": "https://github.com/acme/widgets/issues/14", "kind": "main-red"}]),
        "throughput": dict(k, merged_24h=5),
        "queue": dict(k, depth=3, target=4)}
    return rec


def at(rec, path, value=None, delete=False):
    """rec with the dotted path (list indexes as numbers) set to value, or deleted."""
    rec = copy.deepcopy(rec)
    node, keys = rec, path.split(".")
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    last = int(keys[-1]) if isinstance(node, list) else keys[-1]
    if delete:
        del node[last]
    else:
        node[last] = value
    return rec


M = "sections.milestones.items.0."
ROWS = [  # (name, record, expected problem substring); controls: minimal() and full()
    ("missing top field", at(full(), "sequence", delete=True), "record.sequence: missing"),
    ("extra top field", at(full(), "summary", "all good"), "record.summary: unknown field"),
    ("missing source field", at(full(), "source.runtime", delete=True), "source.runtime: missing"),
    ("extra source field", at(full(), "source.host", "box"), "source.host: unknown field"),
    ("missing section", at(full(), "sections.queue", delete=True), "sections.queue: missing"),
    ("extra section", at(full(), "sections.notes", unknown()), "sections.notes: unknown field"),
    ("missing item field", at(full(), M + "total", delete=True), "sections.milestones.items[0].total: missing"),
    ("extra item field", at(full(), M + "title", "M57"), "sections.milestones.items[0].title: unknown field"),
    ("known section with reason", at(full(), "sections.throughput.reason", "read-failed"),
     "sections.throughput.reason: unknown field"),
    ("unknown section with payload", at(minimal(), "sections.queue.depth", 1), "sections.queue.depth: unknown field"),
    ("bad section state", at(full(), "sections.queue.state", "healthy"), "sections.queue.state: expected known or unknown"),
    ("bad reason", at(minimal(), "sections.queue.reason", "offline"), "sections.queue.reason: expected one of"),
    ("version 0", at(full(), "schema_version", 0), "schema_version: unknown version 0"),
    ("version 2", at(full(), "schema_version", 2), "schema_version: unknown version 2"),
    ("version string", at(full(), "schema_version", "1"), 'schema_version: unknown version "1"'),
    ("version boolean", at(full(), "schema_version", True), "schema_version: unknown version true"),
    ("bad instance id", at(full(), "instance_id", "Alpha"), "instance_id: expected"),
    ("bad registration id", at(full(), "registration_id", "r-XYZ"), "registration_id: expected"),
    ("sequence 0", at(full(), "sequence", 0), "sequence: expected an integer"),
    ("sequence float", at(full(), "sequence", 2.0), "sequence: expected an integer"),
    ("sequence too large", at(full(), "sequence", 2 ** 53), "sequence: expected an integer"),
    ("count string", at(full(), "sections.throughput.merged_24h", "5"), "merged_24h: expected an integer count"),
    ("count boolean", at(full(), "sections.queue.depth", True), "queue.depth: expected an integer count"),
    ("count float", at(full(), "sections.queue.target", 4.0), "queue.target: expected an integer count"),
    ("count negative", at(full(), M + "completed", -1), "items[0].completed: expected an integer count"),
    ("count too large", at(full(), M + "total", 1_000_001), "items[0].total: expected an integer count"),
    ("completed > total", at(full(), M + "completed", 10), "sections.milestones.items[0]: completed > total"),
    ("pull URL as milestone", at(full(), M + "url", "https://github.com/acme/widgets/pull/3"), "expected a milestone URL"),
    ("foreign-repo URL", at(full(), "sections.prs.items.0.url", "https://github.com/evil/repo/pull/7"),
     "URL is not in a source repo"),
    ("credentialed URL", at(full(), "sections.prs.items.0.url", "https://<user>:<password>@github.com/acme/gadgets/pull/7"),
     "expected a pull URL"),
    ("URL with query", at(full(), "sections.blockers.items.0.url", "https://github.com/acme/widgets/issues/14?x=1"),
     "expected a issues or pull URL"),
    ("URL with port", at(full(), "sections.owner_asks.items.0.url", "https://github.com:443/acme/widgets/issues/12"),
     "expected a issues or pull URL"),
    ("bad decision log", at(full(), "source.decision_log", "https://github.com/acme/widgets/milestone/1"),
     "source.decision_log: expected a issues URL"),
    ("bad stage", at(full(), "sections.prs.items.0.stage", "merged"), "stage: expected one of"),
    ("bad blocker kind", at(full(), "sections.blockers.items.0.kind", "sev"), "kind: expected one of"),
    ("duplicate blocker", at(full(), "sections.blockers.items", [
        {"url": "https://github.com/acme/widgets/issues/14", "kind": "held"}] * 2), "duplicate blocker URL"),
    ("malformed time", at(full(), "published_at", "2033-05-18 03:33:20"), "published_at: expected a UTC time"),
    ("not a calendar time", at(full(), "sections.queue.observed_at", "2033-02-30T00:00:00Z"),
     "sections.queue.observed_at: expected a UTC time"),
    ("malformed deadline", at(full(), "sections.owner_asks.items.0.deadline", "tomorrow"), "deadline: expected a UTC time"),
    ("future time", at(at(full(), "published_at", sr.stamp(CLOCK + 121)), "observed_at", T), "published_at: future time"),
    ("future section", at(full(), "sections.prs.observed_at", sr.stamp(CLOCK + 3600)),
     "sections.prs.observed_at: future time"),
    ("observed_at not earliest", at(full(), "observed_at", NOW), "observed_at: expected the earliest section observed_at"),
    ("published before observed", at(full(), "published_at", sr.stamp(CLOCK - 120)), "published_at: before an observed_at"),
    ("unsorted repos", at(full(), "source.repos", ["acme/widgets", "acme/gadgets"]), "expected sorted, distinct repos"),
    ("duplicate repos", at(full(), "source.repos", ["acme/widgets", "acme/widgets"]), "expected sorted, distinct repos"),
    ("no repos", at(full(), "source.repos", []), "source.repos: expected 1-32"),
    ("bad runtime", at(full(), "source.runtime", "docker"), "source.runtime: expected one of"),
    ("over-limit list", at(full(), "sections.milestones.items", [
        {"url": "https://github.com/acme/widgets/milestone/%d" % n, "completed": 0, "total": 0} for n in range(1, 22)]),
     "21 items over the limit 20"),
    ("secret-pattern match", at(full(), "instance_id", "sk-" + "a" * 24), "record: secret-pattern match"),
]


def leaf_paths(value, path=""):
    """Every dotted path in a record (list indexes as numbers), containers included."""
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
    for key, child in items:
        sub = "%s.%s" % (path, key) if path else str(key)
        yield sub
        yield from leaf_paths(child, sub)


WRONG = [[], {}, None, True, 1.5, -1, "x"]  # every JSON type, plus a negative number and a short string
ITEM_KEYS = [(name, key) for name, (_, keys, _) in sr.SECTIONS.items() if keys for key in keys]


class RecordRows(unittest.TestCase):
    def test_controls_valid(self):
        self.assertEqual(sorted(cc.RUNTIME_OPTIONS), sorted(RUNTIMES))
        for rec in (minimal(), full()):
            self.assertEqual(sr.check_record(rec, RUNTIMES, CLOCK), [])
            body = sr.slot_body(rec)
            self.assertEqual(sr.check_body(body, RUNTIMES, CLOCK), (rec, []))
            self.assertEqual(sr.parse_slot(body + "\n"), (rec, None))  # an optional final newline
        self.assertEqual(sr.check_record(at(full(), "published_at", sr.stamp(CLOCK + 120)), RUNTIMES, CLOCK), [])  # skew edge
        self.assertEqual(sr.check_record(at(full(), "sections.owner_asks.items.1.deadline", sr.stamp(CLOCK + 10 ** 6)),
                                         RUNTIMES, CLOCK), [])  # deadline is exempt from the future check

    def test_refusal_rows(self):
        for name, rec, want in ROWS:
            with self.subTest(name):
                problems = sr.check_record(rec, RUNTIMES, CLOCK)
                self.assertTrue(any(want in p for p in problems), (want, problems))

    def test_every_field_with_every_wrong_type(self):
        """The whole wrong-type class (round-1 finding 1): every path of the full record, containers included,
        replaced by each JSON type, returns problems and never raises; the valid value at the path is the control."""
        rows = 0
        for path in leaf_paths(full()):
            control = full()
            for value in WRONG:
                rec = at(control, path, value)
                if rec == control or path.endswith(".deadline") and value is None:
                    continue  # the same value, or a valid one (a null deadline)
                if path in ("instance_id",) and value == "x" or path.endswith(".items") and value == []:
                    continue  # valid: a one-letter instance ID, an empty list
                with self.subTest(path=path, value=value):
                    problems = sr.check_record(rec, RUNTIMES, CLOCK)
                    self.assertTrue(problems, (path, value))
                rows += 1
        self.assertGreater(rows, 300)
        self.assertEqual(sr.check_record(full(), RUNTIMES, CLOCK), [])
        nested = sr.MARKER + "\n```json\n" + '{"a":' * 5000 + "1" + "}" * 5000 + "\n```"
        self.assertEqual(sr.parse_slot(nested)[0], None)
        self.assertRegex(sr.parse_slot(nested)[1], r"record is not JSON|nested deeper than 8")
        self.assertIn("nested deeper than 8", sr.parse_slot(sr.slot_body(at(full(), "sections.queue.depth",
                                                                              [[[[[[[1]]]]]]])))[1])

    def test_slot_envelope(self):
        body = sr.slot_body(full())
        self.assertTrue(body.startswith(sr.MARKER + "\n```json\n") and body.endswith("\n```"))
        self.assertNotIn("crew:v1", body)
        self.assertEqual(sr.parse_slot("Shared status board."), (None, None))  # not a status comment: ignored
        self.assertEqual(sr.parse_slot("<!-- crew:v1 role=coordinator -->\n"), (None, None))
        for name, bad, want in (
                ("trailing text", body + "\nthanks", "not exactly the marker line and one json fence"),
                ("two fences", body + "\n```json\n{}\n```", "not exactly the marker line and one json fence"),
                ("not json", sr.MARKER + "\n```json\n{oops}\n```", "record is not JSON"),
                ("duplicate key", sr.MARKER + '\n```json\n{"a":1,"a":2}\n```', "duplicate key"),
                ("NaN", sr.MARKER + '\n```json\n{"a":NaN}\n```', "non-finite number"),
                ("array", sr.MARKER + "\n```json\n[]\n```", "record is not a JSON object"),
                ("oversize body", sr.MARKER + "\n```json\n" + json.dumps({"x": "a" * 60_000}) + "\n```",
                 "slot body over 60000 bytes")):
            with self.subTest(name):
                self.assertIn(want, sr.parse_slot(bad)[1] or "")

    def test_content_identity(self):
        a, b = full(), json.loads(json.dumps(full(), sort_keys=False))
        self.assertEqual(sr.content_sha256(a), sr.content_sha256(b))
        self.assertEqual(sr.canonical({"b": 1, "a": "é"}), '{"a":"é","b":1}'.encode("utf-8"))
        self.assertNotEqual(sr.content_sha256(a), sr.content_sha256(at(a, "sequence", 2)))


class RecordRowsThroughCli(StatusBase):
    """The S.1 rows read back by the shipped `mdstack status --all` and refused by `mdstack status publish`."""

    def test_status_all_names_every_invalid_comment(self):
        def distinct(name, rec, i):  # its own instance and registration, unless the row is about that field
            rec = rec if "instance id" in name or "secret" in name else at(rec, "instance_id", "row-%02d" % i)
            return rec if "registration" in name or "registration_id" not in rec else \
                at(rec, "registration_id", "r-%032x" % (i + 1))
        bodies = [sr.slot_body(distinct(name, rec, i)) for i, (name, rec, _) in enumerate(ROWS)]
        bodies.append(sr.MARKER + "\n```json\n" + json.dumps({"instance_id": "big", "x": "a" * 60_000}) + "\n```")
        controls = [sr.slot_body(at(at(minimal(), "instance_id", "ctl-min"), "registration_id", "r-" + "b" * 32)),
                    sr.slot_body(at(at(full(), "instance_id", "ctl-full"), "registration_id", "r-" + "c" * 32))]
        comments = self.api["issues"]["acme/status/5"]["comments"]
        for n, body in enumerate(bodies + controls):
            comments.append({"id": 100 + n, "user": "someone", "body": body})
        self.save_api()
        before = self.snapshot()
        r = self.crew("status", "--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        for n, (name, _, want) in enumerate(ROWS):
            line = next((ln for ln in lines if "#issuecomment-%d " % (100 + n) in ln), "")
            self.assertTrue(line.startswith("diagnostic: ") and "invalid:" in line, (name, line))
        self.assertTrue(any("#issuecomment-%d invalid: slot body over 60000 bytes" % (100 + len(ROWS)) in ln
                            for ln in lines), lines)
        rows = {ln.split()[0]: ln.split() for ln in lines[1:] if not ln.startswith("diagnostic:")}
        self.assertEqual(rows["ctl-min"][4], "fresh")  # controls: valid minimal and full records
        self.assertEqual(rows["ctl-full"][4:7], ["fresh", "yes", "-"])
        self.assertEqual(rows["ctl-min"][5:7], ["unknown", ",".join(sr.SECTIONS)])
        self.assertFalse([name for name, row in rows.items() if name.startswith("row-") and row[4] != "invalid"], rows)
        self.assertEqual((self.audit(), self.snapshot()), ([], before))

    def test_wrong_typed_item_values_in_every_section(self):
        """Round-1 finding 1 through the shipped CLI: a wrong-typed value for each item key of each list section, and a
        too-deeply nested body, each becomes a `diagnostic:` while the valid control stays a fresh row; exit 0, no writes."""
        comments, n = self.api["issues"]["acme/status/5"]["comments"], 0
        wanted = {}
        for name, key in ITEM_KEYS:
            for value in ([], {}, None if key != "deadline" else 7, True):
                rec = full()
                rec["sections"][name]["items"][0][key] = value
                rec.update(instance_id="w-%02d" % n, registration_id="r-%032x" % (n + 1))
                comments.append({"id": 300 + n, "user": "someone", "body": sr.slot_body(rec)})
                wanted[300 + n] = (name, key, value)
                n += 1
        comments.append({"id": 299, "user": "someone",
                         "body": sr.MARKER + "\n```json\n" + '{"a":' * 5000 + "1" + "}" * 5000 + "\n```"})
        comments.append({"id": 298, "user": "someone", "body": sr.slot_body(at(at(full(), "instance_id", "ctl"),
                                                                              "registration_id", "r-" + "e" * 32))})
        self.save_api()
        before = self.snapshot()
        r = self.crew("status", "--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        for cid, row in wanted.items():
            self.assertTrue(any(ln.startswith("diagnostic: ") and "#issuecomment-%d invalid:" % cid in ln for ln in lines),
                            (row, lines))
        self.assertTrue(any(re.search(r"#issuecomment-299 invalid: (record is not JSON|record nested deeper than 8)", ln)
                            for ln in lines), lines)
        rows = {ln.split()[0]: ln.split() for ln in lines[1:] if not ln.startswith("diagnostic:")}
        self.assertEqual(rows["ctl"][4], "fresh")  # the valid control stays visible
        self.assertEqual(sorted(k for k, v in rows.items() if v[4] == "invalid"), sorted("w-%02d" % i for i in range(n)))
        self.assertEqual((self.audit(), self.snapshot()), ([], before))

    def test_publisher_refuses_an_invalid_record_with_zero_writes(self):
        assert self.crew("status", "register").returncode == 0
        before, audit = self.snapshot(), self.audit()
        self.api = self.load_api()
        self.api["repos"]["acme/widgets"] = {"milestones": [{"number": 2, "open_issues": -3, "closed_issues": 4}]}
        self.save_api()
        r = self.crew("status", "publish")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("status publish: record invalid: sections.milestones.items[0]: completed > total", r.stderr)
        self.assertEqual((self.audit(), self.snapshot()), (audit, before))
        self.api["repos"]["acme/widgets"]["milestones"][0]["open_issues"] = 3  # control: valid counts publish
        self.save_api()
        r = self.crew("status", "publish")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "published sequence 2"), r.stderr)


if __name__ == "__main__":
    unittest.main()
