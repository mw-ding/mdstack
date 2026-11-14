"""Tests for mdstack land (#930, #873 B2): an external pack declaring land.mode = "async", whose backend map points
change.land, change.land-status and change.read-head at a fake `exland` CLI on PATH; fixtures in crew_testlib.py
(stdlib only).

Covers: none → request → queued → landing → landed with the landed revision; failed with its reason; timeout;
a stale head refused with no request; a lost acknowledgement resolved by read-back with exactly one request,
and a lost one that reads `none` blocked with no resend; an unknown or malformed status never taken as `none`;
an already in-flight land polled, not requested again; `status` reads once; a sync backend and a short --head
refused; no land lock or train state written in the backend-managed mode. B3 (#931): the intent recorded before
the first read, marked landed with the merge record's landed revision and marker, cleared only by `done` after
`landed`; dropped on failed, stale head and a lost request reading none; kept on timeout. `resume` after a restart
before terminal success polls without requesting, after terminal success prints the pending record, and drops a
never-requested intent. #1042: a backend with its own change placeholder, native status words (read-landed for
the revision) and no head-match flag runs request, resume and done; a word no declared pattern matches stays
unknown and never requests; change.land without <head-sha> is refused unless head_guard = false. #1605: the
session stack land (land stack, stack-done, resume) with per-member gates, readback and refusals. #1722: a sync
backend with no shell in its map lands a three-member stack by its top change and recorded revision ids, read back
per change through land.status; mixed or unknown member states record nothing; resume reuses the recorded ids.
Run in CI.
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import textwrap
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, write_pack

HEAD, OTHER, LANDED = "a" * 40, "b" * 40, "c" * 40
# Fake exland: land-status plays $FAKE_LAND_DIR/status.json in order (keeping the last; an int entry exits with
# it); read-head prints head.txt; land exits with land-exit.txt (default 0). Every call is logged.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    d, args = os.environ["FAKE_LAND_DIR"], sys.argv[1:]
    open(os.path.join(d, "calls.log"), "a").write(json.dumps(args) + "\\n")
    if args[0] == "land-status":
        path = os.path.join(d, "status.json")
        seq = json.load(open(path))
        json.dump(seq[1:] or seq, open(path, "w"))
        if isinstance(seq[0], int):
            sys.exit(seq[0])
        print(seq[0])
    elif args[0] == "head" and os.path.exists(os.path.join(d, "heads.json")):
        print(json.load(open(os.path.join(d, "heads.json")))[args[1]])
    elif args[0] == "head":
        print(open(os.path.join(d, "head.txt")).read())
    elif args[0] == "stack-status":
        path = os.path.join(d, "stack.json")
        seq = json.load(open(path))
        json.dump(seq[1:] or seq, open(path, "w"))
        if isinstance(seq[0], int):
            sys.exit(seq[0])
        print(seq[0])
    elif args[0] == "land-stack":
        path = os.path.join(d, "land-exit.txt")
        sys.exit(int(open(path).read()) if os.path.exists(path) else 0)
    elif args[0] == "landed":
        print(open(os.path.join(d, "landed.txt")).read())
    elif args[0] == "rev":  # refuses a head other than the member's live one, as the contract requires
        live, revs = json.load(open(os.path.join(d, "heads.json"))), json.load(open(os.path.join(d, "revs.json")))
        if live[args[1]] != args[2]:
            sys.exit(3)
        print(revs[args[1]])
    elif args[0] == "member-status":  # rounds of {change: status}; a round advances once every member read it
        path = os.path.join(d, "members.json")
        rounds = json.load(open(path))
        status = rounds["seq"][0][args[1]]
        rounds["seen"].append(args[1])
        if set(rounds["seen"]) >= set(rounds["seq"][0]):
            rounds = {"seq": rounds["seq"][1:] or rounds["seq"], "seen": []}
        json.dump(rounds, open(path, "w"))
        print(status)
    elif args[0] == "submit-stack":  # refuses a member revision id that is not the current one; an accepted
        revs = json.load(open(os.path.join(d, "revs.json")))  # request exits land-exit.txt (a lost acknowledgement)
        if args[2:] != [revs[c] for c in sorted(revs, key=int)]:
            sys.exit(4)
        path = os.path.join(d, "land-exit.txt")
        sys.exit(int(open(path).read()) if os.path.exists(path) else 0)
    elif args[0] == "land":
        path = os.path.join(d, "land-exit.txt")
        sys.exit(int(open(path).read()) if os.path.exists(path) else 0)
    """)


class LandFixture(Base):
    def setUp(self):
        super().setUp()
        self.fake = os.path.join(self.tmp, "land")
        os.makedirs(self.fake)
        exland = os.path.join(self.tmp, "bin", "exland")
        with open(exland, "w") as f:
            f.write(FAKE)
        os.chmod(exland, 0o755)
        self.env["FAKE_LAND_DIR"] = self.fake
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        with open(os.path.join(repo, "templates", "backends", "github.toml")) as f:
            mapping = f.read()
        mapping = re.sub(r'(?m)^land = .*$', 'land = "exland land <n> --expect-head <head-sha>"\n'
                         'land-status = "exland land-status <n> <head-sha> -R <owner>/<repo>"', mapping)
        mapping = re.sub(r'(?m)^read-head = .*$', 'read-head = "exland head <n>"', mapping)
        self.org = write_pack(os.path.join(self.tmp, "pack"), mapping=mapping)
        self.manifest = os.path.join(self.tmp, "pack", "manifest.toml")
        with open(self.manifest) as f:
            text = f.read().replace('land = "supported"', 'land = "supported"\nland-status = "supported"')
        with open(self.manifest, "w") as f:
            f.write(text + '\n[land]\nmode = "async"\nserializes = true\ntests_against_tip = true\n')
        with open(self.project, "a") as f:
            f.write("[runtime.options]\nland_poll_interval = 1\nland_timeout = 3\n")
        self.head(HEAD)

    def head(self, sha):
        with open(os.path.join(self.fake, "head.txt"), "w") as f:
            f.write(sha)

    def statuses(self, *seq):
        with open(os.path.join(self.fake, "status.json"), "w") as f:
            json.dump(list(seq), f)

    def land(self, action="request", head=HEAD):
        target = [] if action == "resume" else ["--pr", "7", "--head", head]
        r = self.crew("land", action, "--project", self.project, "--org-profile", self.org, *target)
        if "--owner-transcript" in sys.argv:
            print("$ mdstack land %s --project <fixture>/crew.toml --org-profile <fixture>/pack/profile.toml%s"
                  % (action, "".join(" " + t for t in target)))
            print("exit: %d\n--- stdout\n%s--- stderr\n%s" % (r.returncode, r.stdout.replace(self.tmp, "<fixture>"),
                                                             r.stderr), end="")
        return r

    def intent(self, head=HEAD):
        path = os.path.join(self.state, "land", "7-%s.json" % head)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def calls(self, verb=None):
        path = os.path.join(self.fake, "calls.log")
        found = []
        if os.path.exists(path):
            with open(path) as f:
                found = [json.loads(line) for line in f]
        return [c for c in found if verb is None or c[0] == verb]


class Land(LandFixture):
    def test_queued_landing_landed(self):
        self.statuses("none", "queued", "landing", "landed " + LANDED)
        r = self.land()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew: land #7 @ aaaaaaa: queued", r.stdout)
        self.assertIn("crew: land #7 @ aaaaaaa: landing", r.stdout)
        self.assertIn("crew: landed #7 @ aaaaaaa as " + LANDED, r.stdout)
        self.assertEqual(self.calls("land"), [["land", "7", "--expect-head", HEAD]])
        self.assertEqual(self.calls("land-status")[0], ["land-status", "7", HEAD, "-R", "acme/widgets"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "locks")))  # backend-managed: no land lock
        self.assertFalse(os.path.exists(os.path.join(self.state, "trains")))  # and no train

    def test_failed(self):
        self.statuses("none", "queued", "failed checks red on tip")
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("blocked: land #7 @ aaaaaaa: failed: checks red on tip", r.stdout)
        self.assertNotIn("landed", r.stdout)

    def test_timeout(self):
        self.statuses("none", "queued")
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("blocked: land #7 @ aaaaaaa: timeout after 3s, still queued", r.stdout)
        self.assertEqual(len(self.calls("land")), 1)

    def test_stale_head(self):
        self.statuses("none")
        self.head(OTHER)
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale head, change head is '%s'; no request sent" % OTHER, r.stdout)
        self.assertEqual(self.calls("land"), [])

    def test_lost_acknowledgement(self):
        with open(os.path.join(self.fake, "land-exit.txt"), "w") as f:
            f.write("1")
        self.statuses("none", "queued", "landed " + LANDED)
        r = self.land()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(len(self.calls("land")), 1)  # read back, never resent
        self.statuses("none")
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("request failed and land-status is none; rerun the §7 gate check", r.stdout)
        self.assertEqual(len(self.calls("land")), 2)  # one per run

    def test_unknown_status_never_requests(self):
        for bad in (["garbage"], [2], ["landed abc"], ["failed"], ["none\nfailed already requested"], ["none\n"]):
            self.statuses(*bad)
            r = self.land()
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("blocked: land #7 @ aaaaaaa: unknown", r.stdout)
        self.assertEqual(self.calls("land"), [])

    def test_extra_lines_after_landed_not_success(self):
        self.statuses("landing", "landed %s\nfailed oops" % LANDED)
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("blocked: land #7 @ aaaaaaa: unknown", r.stdout)
        self.assertNotIn("crew: landed", r.stdout)
        self.assertEqual(self.calls("land"), [])

    def test_in_flight_polled_not_requested(self):
        self.statuses("landing", "landed " + LANDED)
        self.assertEqual(self.land().returncode, 0)
        self.statuses("landed " + LANDED)
        self.assertEqual(self.land().returncode, 0)
        self.assertEqual(self.calls("land"), [])

    def test_status_reads_once(self):
        self.statuses("failed head moved", "none")
        r = self.land("status")
        self.assertEqual((r.returncode, r.stdout), (0, "failed head moved\n"))
        self.statuses(3)
        self.assertEqual(self.land("status").returncode, 1)
        self.assertEqual([c[0] for c in self.calls()], ["land-status", "land-status"])

    def test_sync_backend_and_short_head_refused(self):
        self.assertIn("--head must be a full", self.land(head="abc1234").stdout)
        with open(self.manifest) as f:
            text = f.read().split("\n[land]")[0]
        with open(self.manifest, "w") as f:
            f.write(text)
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("land.mode is sync", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_intent_marked_landed_then_done(self):
        self.statuses("none", "queued", "landed " + LANDED)
        r = self.land()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("record: Landed revision: `%s` (checked head `%s`); tested with `main` by the backend's "
                      "land check (`land.tests_against_tip`) on the landed revision." % (LANDED, HEAD), r.stdout)
        self.assertIn("marker: <!-- crew:v1 role=synthesizer pass=merge pr=7 sha=%s round=n/a verdict=n/a "
                      "landed=%s -->" % (HEAD, LANDED), r.stdout)
        self.assertEqual(self.intent()["landed"], LANDED)
        r = self.land("done")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIsNone(self.intent())
        r = self.land("done")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing done #7 @ aaaaaaa: no intent marked landed", r.stdout)

    def test_done_refused_before_landed(self):
        self.statuses("none", "queued")
        self.assertEqual(self.land().returncode, 1)  # timeout keeps the intent
        self.assertEqual(self.intent()["head"], HEAD)
        self.assertIsNone(self.intent().get("landed"))
        r = self.land("done")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no intent marked landed", r.stdout)
        self.assertIsNotNone(self.intent())

    def test_terminal_failures_drop_intent(self):
        self.statuses("none", "failed checks red")
        self.assertEqual(self.land().returncode, 1)
        self.assertIsNone(self.intent())
        self.statuses("none")
        self.head(OTHER)
        self.assertEqual(self.land().returncode, 1)
        self.assertIsNone(self.intent())
        self.head(HEAD)
        self.statuses("none")
        r = self.land()
        self.assertIn("request sent and land-status is none", r.stdout)
        self.assertIsNone(self.intent())

    def test_restart_before_terminal_success(self):
        self.statuses("none", "queued")
        r = self.land()
        self.assertIn("timeout after 3s, still queued; intent kept", r.stdout)
        self.statuses("landing", "landed " + LANDED)
        r = self.land("resume")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("crew: land #7 @ aaaaaaa: landing", r.stdout)
        self.assertIn("landed=%s -->" % LANDED, r.stdout)
        self.assertEqual(len(self.calls("land")), 1)  # resumed by a status read, not requested again
        self.assertEqual(self.intent()["landed"], LANDED)

    def test_restart_after_terminal_success(self):
        self.statuses("none", "landed " + LANDED)
        self.assertEqual(self.land().returncode, 0)  # landed, but the merge record never posted
        self.statuses("landed " + LANDED)
        r = self.land("resume")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("crew: landed #7 @ aaaaaaa as " + LANDED, r.stdout)
        self.assertIn("marker: <!-- crew:v1 role=synthesizer pass=merge pr=7 sha=%s" % HEAD, r.stdout)
        self.assertEqual(len(self.calls("land")), 1)
        self.assertEqual(self.land("done").returncode, 0)
        r = self.land("resume")
        self.assertEqual((r.returncode, r.stdout), (0, ""))  # no intents, nothing read

    def test_resume_never_requested(self):
        os.makedirs(os.path.join(self.state, "land"))
        with open(os.path.join(self.state, "land", "7-%s.json" % HEAD), "w") as f:
            json.dump({"pr": 7, "head": HEAD}, f)  # intent written, then a crash before the request
        self.statuses("none")
        r = self.land("resume")
        self.assertEqual(r.returncode, 1)
        self.assertIn("blocked: land #7 @ aaaaaaa: never requested at this head; intent dropped", r.stdout)
        self.assertEqual(self.calls("land"), [])
        self.assertIsNone(self.intent())

    def test_resume_unknown_keeps_intent(self):
        self.statuses("none", "queued")
        self.land()
        self.statuses("garbage")
        r = self.land("resume")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown", r.stdout)
        self.assertIsNotNone(self.intent())
        self.assertEqual(len(self.calls("land")), 1)


# A non-GitHub backend (#1042): <n> names the tracker item, so the change id is <change>; the CLI prints its own
# status words and no revision, and its land call has no head-match flag.
NATIVE_STATUS = textwrap.dedent("""\
    [land.status]
    NOT_STARTED = "none"
    "QUEUED|WAITING" = "queued"
    RUNNING = "landing"
    SUCCESS = "landed"
    "FAILED: (?P<reason>.+)" = "failed"
    """)


class NativeLand(LandFixture):
    def setUp(self):
        super().setUp()
        mapping_path = os.path.join(self.tmp, "pack", "render", "backends", "example.toml")
        with open(mapping_path) as f:
            mapping = f.read()
        mapping = re.sub(r'(?m)^land = .*$', 'land = "exland land <change>"', mapping)
        mapping = re.sub(r'(?m)^land-status = .*$', 'land-status = "exland land-status <change>"\n'
                         'read-landed = "exland landed <change>"', mapping)
        mapping = re.sub(r'(?m)^read-head = .*$', 'read-head = "exland head <change>"', mapping)
        with open(mapping_path, "w") as f:
            f.write(mapping + '\n[placeholders]\nkept = ["change"]\n')
        with open(self.manifest) as f:
            text = f.read().replace('land-status = "supported"', 'land-status = "supported"\nread-landed = "supported"')
        self.async_manifest = text.replace("tests_against_tip = true\n", "tests_against_tip = true\n"
                                           'change_placeholder = "change"\nhead_guard = false\n') + NATIVE_STATUS
        with open(self.manifest, "w") as f:
            f.write(self.async_manifest)
        with open(os.path.join(self.fake, "landed.txt"), "w") as f:
            f.write(LANDED)

    def test_request_resume_done_end_to_end(self):
        self.statuses("NOT_STARTED", "QUEUED")
        r = self.land()
        self.assertIn("crew: land #7 @ aaaaaaa: queued", r.stdout)
        self.assertIn("timeout after 3s, still queued; intent kept", r.stdout)
        self.assertEqual(self.calls("land"), [["land", "7"]])  # change id under <change>, no head flag
        self.assertEqual(self.calls("head"), [["head", "7"]])  # head re-read right before the request
        self.statuses("RUNNING", "SUCCESS")
        r = self.land("resume")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("crew: land #7 @ aaaaaaa: landing", r.stdout)
        self.assertIn("crew: landed #7 @ aaaaaaa as " + LANDED, r.stdout)
        self.assertIn("landed=%s -->" % LANDED, r.stdout)
        self.assertEqual(self.calls("landed"), [["landed", "7"]])
        self.assertEqual(len(self.calls("land")), 1)
        self.assertEqual(self.land("done").returncode, 0)
        self.assertIsNone(self.intent())

    def test_native_failed_and_stale_head(self):
        self.statuses("NOT_STARTED", "FAILED: tip tests red")
        r = self.land()
        self.assertIn("blocked: land #7 @ aaaaaaa: failed: tip tests red", r.stdout)
        self.assertIsNone(self.intent())
        self.statuses("NOT_STARTED")
        self.head(OTHER)
        r = self.land()
        self.assertIn("stale head, change head is '%s'; no request sent" % OTHER, r.stdout)
        self.assertEqual(len(self.calls("land")), 1)

    def test_undeclared_word_unknown_never_requests(self):
        for bad in (["CANCELLED"], ["none"], ["landed " + LANDED], ["QUEUED\nSUCCESS"]):
            self.statuses(*bad)
            r = self.land()
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("blocked: land #7 @ aaaaaaa: unknown output", r.stdout)
        self.statuses("SUCCESS")
        with open(os.path.join(self.fake, "landed.txt"), "w") as f:
            f.write("abc")
        r = self.land()
        self.assertIn("unknown landed, but revision 'abc' is not a full commit SHA", r.stdout)
        self.assertEqual(self.calls("land"), [])

    def test_optional_revision_group_not_captured_is_unknown(self):
        with open(self.manifest, "w") as f:
            f.write(self.async_manifest.replace('SUCCESS = "landed"', '"SUCCESS( (?P<revision>[0-9a-f]{40}))?" = "landed"'))
        self.statuses("SUCCESS")
        r = self.land()
        self.assertIn("unknown landed, but output 'SUCCESS' captured no revision", r.stdout)
        self.statuses("SUCCESS " + LANDED)
        self.assertIn("crew: landed #7 @ aaaaaaa as " + LANDED, self.land().stdout)
        self.assertEqual(self.calls("landed"), [])

    def test_land_without_head_guard_needs_declaration(self):
        with open(self.manifest, "w") as f:
            f.write(self.async_manifest.replace("head_guard = false\n", ""))
        self.statuses("NOT_STARTED")
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("change.land carries no <head-sha> guard; declare land.head_guard = false", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_undeclared_placeholder_keeps_v510_refusal(self):
        with open(self.manifest, "w") as f:
            f.write(self.async_manifest.replace('change_placeholder = "change"\n', ""))
        r = self.land()
        self.assertEqual(r.returncode, 1)
        self.assertIn("keeps an unfilled placeholder <change>", r.stdout)
        self.assertEqual(self.calls(), [])



class SessionNativeLand(NativeLand):
    """#1351: the session runtime's async land binding runs every NativeLand case unchanged, plus its refusals."""
    def setUp(self):
        super().setUp()
        self.write_profile(runtime="session")
        with open(self.project, "a") as f:
            f.write('[runtime.options]\nsession_backend = "native"\nland_poll_interval = 1\nland_timeout = 3\n')

    def test_session_failed_and_unknown_refuse(self):
        self.statuses("NOT_STARTED", "QUEUED", "FAILED: checks red")
        r = self.land()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("blocked: land #7 @ aaaaaaa: failed", r.stdout)
        self.assertIsNone(self.intent())
        self.statuses("WHATEVER")
        r = self.land()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("blocked: land #7 @ aaaaaaa: unknown", r.stdout)
        self.assertEqual(len(self.calls("land")), 1)  # an unknown status never requests

STACK_HEAD, STACK_LANDED = "d" * 40, "e" * 40


class SessionStackLand(LandFixture):
    """#1605: a session profile whose sync change backend declares land.stack with a combined-stack test lands #7 and
    #8 in one atomic request; per-member readback, refusals, a lost acknowledgement and resume."""
    def setUp(self):
        super().setUp()
        mapping_path = os.path.join(self.tmp, "pack", "render", "backends", "example.toml")
        with open(mapping_path) as f:
            mapping = f.read()
        with open(mapping_path, "w") as f:
            f.write(re.sub(r'(?m)^land = (.*)$', 'land = \\1\nland-stack = "exland land-stack <stack>"\n'
                           'stack-status = "exland stack-status <stack>"', mapping, count=1))
        with open(self.manifest) as f:
            text = f.read().split("\n[land]")[0]
        with open(self.manifest, "w") as f:
            f.write(text.replace('land-status = "supported"', 'land-stack = "supported"\nstack-status = "supported"')
                    + '\n[land]\nstack = true\nstack_tests_against_tip = true\n')
        self.write_profile(runtime="session")
        with open(self.project, "a") as f:
            f.write('[runtime.options]\nsession_backend = "native"\nland_poll_interval = 1\nland_timeout = 3\n')
        self.heads(HEAD, STACK_HEAD)

    def heads(self, seven, eight):
        with open(os.path.join(self.fake, "heads.json"), "w") as f:
            json.dump({"7": seven, "8": eight}, f)

    def stack_statuses(self, *seq):
        with open(os.path.join(self.fake, "stack.json"), "w") as f:
            json.dump(list(seq), f)

    def stack(self, action="stack", members="7:%s,8:%s" % (HEAD, STACK_HEAD), *extra):
        target = [] if action == "resume" else ["--stack", members]
        r = self.crew("land", action, "--project", self.project, "--org-profile", self.org, *target, *extra)
        if "--owner-transcript" in sys.argv:
            print("$ mdstack land %s --project <fixture>/crew.toml --org-profile <fixture>/pack/profile.toml%s"
                  % (action, "".join(" " + t for t in target + list(extra))))
            print("exit: %d\n--- stdout\n%s--- stderr\n%s" % (r.returncode, r.stdout.replace(self.tmp, "<fixture>"),
                                                             r.stderr), end="")
        return r

    def stack_intent(self):
        path = os.path.join(self.state, "land", "stack", "7-%s.json" % HEAD)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    LANDED_BOTH = "7 landed %s\n8 landed %s\ncheck ci/run-42" % (LANDED, STACK_LANDED)

    def test_stack_lands_once_with_per_member_records(self):
        self.stack_statuses("7 none\n8 none", "7 queued\n8 landing", self.LANDED_BOTH)
        r = self.stack()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls("land-stack"), [["land-stack", "7:" + HEAD, "8:" + STACK_HEAD]])
        self.assertEqual([c[1] for c in self.calls("head")], ["7", "8"])  # every member head read before the request
        tested = "; tested as a combined stack on `main` by the backend's stack land check `ci/run-42`"
        for change, head, landed in ((7, HEAD, LANDED), (8, STACK_HEAD, STACK_LANDED)):
            self.assertIn("record: #%d: Landed revision: `%s` (checked head `%s`); stack land of 2 (#7, #8)%s"
                          % (change, landed, head, tested), r.stdout)
            self.assertIn("marker: #%d: <!-- crew:v1 role=synthesizer pass=merge pr=%d sha=%s round=n/a verdict=n/a "
                          "landed=%s -->" % (change, change, head, landed), r.stdout)
        self.assertEqual(self.stack_intent()["landed"], [LANDED, STACK_LANDED])
        self.assertEqual(self.calls("land"), [])  # no individual land
        self.assertFalse(os.path.exists(os.path.join(self.state, "locks")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "trains")))
        self.assertEqual(self.stack("stack-done").returncode, 0)
        self.assertIsNone(self.stack_intent())

    def test_one_stale_member_refuses_the_whole_stack(self):
        self.stack_statuses("7 none\n8 none")
        self.heads(HEAD, OTHER)
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale head, #8 head is '%s'; no request sent for any member" % OTHER, r.stdout)
        self.assertEqual(self.calls("land-stack"), [])
        self.assertIsNone(self.stack_intent())

    def test_lost_acknowledgement_read_back_never_resent(self):
        with open(os.path.join(self.fake, "land-exit.txt"), "w") as f:
            f.write("1")
        self.stack_statuses("7 none\n8 none", "7 queued\n8 queued", self.LANDED_BOTH)
        self.assertEqual(self.stack().returncode, 0)
        self.assertEqual(len(self.calls("land-stack")), 1)
        self.assertEqual(self.stack("stack-done").returncode, 0)
        self.stack_statuses("7 none\n8 none")
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("request failed and stack-status is none; rerun the §7 gate check for every member", r.stdout)
        self.assertEqual(len(self.calls("land-stack")), 2)  # one per run
        self.assertIsNone(self.stack_intent())

    def test_malformed_or_mismatched_readback_records_nothing(self):
        for bad in ("7 landed %s\ncheck ci/1" % LANDED,  # a member missing
                    "8 landed %s\n7 landed %s\ncheck ci/1" % (STACK_LANDED, LANDED),  # reordered
                    "7 landed %s\n8 none" % LANDED,  # split state
                    "7 landed %s\n8 landed %s" % (LANDED, STACK_LANDED),  # declared combined test, no check line
                    "7 landed abc\n8 landed %s\ncheck ci/1" % STACK_LANDED, "garbage", 2):
            self.stack_statuses(bad)
            r = self.stack()
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("blocked: land stack #7 @ aaaaaaa, #8 @ ddddddd: unknown", r.stdout)
            self.assertIn("intent kept", r.stdout)
            self.assertNotIn("record:", r.stdout)
            self.assertNotIn("landed", self.stack_intent())
        self.assertEqual(self.calls("land-stack"), [])  # an unknown state never requests
        self.assertEqual(self.stack("stack-done").returncode, 1)  # nor completes

    def test_failed_drops_intent(self):
        self.stack_statuses("7 none\n8 none", "7 failed combined CI red\n8 failed combined CI red")
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("blocked: land stack #7 @ aaaaaaa, #8 @ ddddddd: failed: combined CI red", r.stdout)
        self.assertIsNone(self.stack_intent())

    def test_resume_after_timeout_never_requests(self):
        self.stack_statuses("7 none\n8 none", "7 queued\n8 queued")
        r = self.stack()
        self.assertIn("timeout after 3s, still landing; intent kept", r.stdout)
        self.stack_statuses(self.LANDED_BOTH)
        r = self.stack("resume")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("record: #8: Landed revision: `%s`" % STACK_LANDED, r.stdout)
        self.assertEqual(len(self.calls("land-stack")), 1)
        self.assertEqual(self.stack("stack-done").returncode, 0)
        self.assertEqual(self.stack("resume").returncode, 0)  # nothing recorded: nothing read
        self.stack_statuses("7 none\n8 none", "7 queued\n8 queued")
        self.stack()
        self.stack_statuses("7 none\n8 none")
        r = self.stack("resume")
        self.assertEqual(r.returncode, 1)
        self.assertIn("never requested at these heads; intent dropped", r.stdout)
        self.assertEqual(len(self.calls("land-stack")), 2)

    def test_refusals(self):
        for members, expected in (("7:%s" % HEAD, "two or more distinct changes"),
                                  ("7:%s,7:%s" % (HEAD, STACK_HEAD), "two or more distinct changes"),
                                  ("7:abc,8:%s" % STACK_HEAD, "is not <n>:<full lowercase head sha>")):
            r = self.stack(members=members)
            self.assertEqual(r.returncode, 1)
            self.assertIn(expected, r.stdout)
        self.assertIn("takes --stack, not --pr or --head", self.stack("stack", "7:%s,8:%s" % (HEAD, STACK_HEAD),
                                                                      "--pr", "7").stdout)
        self.assertIn("refusing done", self.crew("land", "done", "--project", self.project, "--org-profile",
                                                 self.org, "--pr", "7", "--head", HEAD).stdout)
        with open(self.manifest) as f:
            text = f.read()
        with open(self.manifest, "w") as f:
            f.write(text.split("\n[land]")[0])
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("declares no land.stack; land each change alone", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_foreign_member_refuses_whole_stack_with_nothing_written(self):  # #1859: before any intent or read
        r = self.stack(members="7:%s,example/beta#8:%s" % (HEAD, STACK_HEAD))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("stack member #8 is example/beta, not acme/widgets; nothing written, read or requested", r.stdout)
        self.assertEqual(self.calls(), [])
        self.assertFalse(os.path.exists(os.path.join(self.state, "land")))
        self.stack_statuses("7 none\n8 none", self.LANDED_BOTH)
        r = self.stack(members="7:%s,acme/widgets#8:%s" % (HEAD, STACK_HEAD))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.stack_intent()["context"], contexts(self.project)[0])

    def test_foreign_stack_intent_refused_and_own_proceeds(self):  # #1859: before any read, request or drop
        own, beta = contexts(self.project)
        path = os.path.join(self.state, "land", "stack", "7-%s.json" % HEAD)
        refusal = "stack land intent 7-%s.json: recorded land intent %s" % (HEAD, FOREIGN)
        for action, extra, refused in (("stack", {}, "blocked: land stack #7 @ aaaaaaa, #8 @ ddddddd: "),
                                       ("resume", {}, "blocked: " + refusal),
                                       ("stack-done", {"landed": [LANDED, STACK_LANDED]}, "crew: refusing stack-done")):
            for ctx in (beta, own):
                with self.subTest(action=action, repo=ctx["repo"]):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as f:
                        json.dump(dict({"members": [[7, HEAD], [8, STACK_HEAD]], "context": ctx}, **extra), f)
                    with open(path, "rb") as f:
                        before = f.read()
                    self.stack_statuses(self.LANDED_BOTH)
                    calls = len(self.calls())
                    r = self.stack(action)
                    if ctx is beta:
                        self.assertEqual(r.returncode, 1, r.stdout)
                        self.assertIn(refused, r.stdout)
                        self.assertIn(FOREIGN, r.stdout)
                        self.assertEqual(len(self.calls()), calls)
                        with open(path, "rb") as f:
                            self.assertEqual(f.read(), before)
                    else:
                        self.assertEqual(r.returncode, 0, r.stdout)
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(path)

    def test_tmux_profile_refused(self):
        """tmux trains are unchanged: the stack land is session-only."""
        self.write_profile(runtime="tmux")
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("runtime.name is tmux, not session", r.stdout)
        self.assertEqual(self.calls(), [])



TOP_HEAD, TOP_LANDED = "f" * 40, "9" * 40
PER_CHANGE_STATUS = textwrap.dedent("""\
    [land.status]
    NEW = "none"
    QUEUED = "queued"
    MERGING = "landing"
    "MERGED (?P<revision>[0-9a-f]{40})" = "landed"
    "ABANDONED: (?P<reason>.+)" = "failed"
    """)


class SessionRevisionStackLand(LandFixture):
    """#1722: a sync backend whose stack request names the top change plus every member's revision id, and whose
    status is per change, lands #7, #8 and #9 through `mdstack land stack` with no shell in its map."""
    STACK = "7:%s,8:%s,9:%s" % (HEAD, STACK_HEAD, TOP_HEAD)
    REVS = {"7": "D107", "8": "D108", "9": "D109"}

    def setUp(self):
        super().setUp()
        mapping_path = os.path.join(self.tmp, "pack", "render", "backends", "example.toml")
        with open(mapping_path) as f:
            mapping = f.read()
        mapping = re.sub(r'(?m)^land = .*$', 'land = "exland land <rev>"\n'
                         'land-stack = "exland submit-stack <stack-top> <stack-revisions>"\n'
                         'read-revision-id = "exland rev <rev> <head-sha>"', mapping)
        mapping = re.sub(r'(?m)^land-status = .*$', 'land-status = "exland member-status <rev>"', mapping)
        mapping = re.sub(r'(?m)^read-head = .*$', 'read-head = "exland head <rev>"', mapping)
        with open(mapping_path, "w") as f:
            f.write(mapping + '\n[placeholders]\nkept = ["rev"]\n')
        with open(self.manifest) as f:
            text = f.read().split("\n[land]")[0]
        with open(self.manifest, "w") as f:
            f.write(text.replace('land-status = "supported"', 'land-status = "supported"\nland-stack = "supported"\n'
                                 'read-revision-id = "supported"')
                    + '\n[land]\nstack = true\nstack_status = "per-change"\nchange_placeholder = "rev"\n'
                    + PER_CHANGE_STATUS)
        self.write_profile(runtime="session")
        with open(self.project, "a") as f:
            f.write('[runtime.options]\nsession_backend = "native"\nland_poll_interval = 1\nland_timeout = 3\n')
        self.heads(HEAD, STACK_HEAD, TOP_HEAD)
        self.revs(self.REVS)

    def heads(self, *shas):
        with open(os.path.join(self.fake, "heads.json"), "w") as f:
            json.dump(dict(zip(("7", "8", "9"), shas)), f)

    def revs(self, revs):
        with open(os.path.join(self.fake, "revs.json"), "w") as f:
            json.dump(revs, f)

    def rounds(self, *seq):
        """Each round: one status for every member, or a dict per member."""
        with open(os.path.join(self.fake, "members.json"), "w") as f:
            json.dump({"seq": [r if isinstance(r, dict) else {"7": r, "8": r, "9": r} for r in seq], "seen": []}, f)

    LANDED_ALL = {"7": "MERGED " + LANDED, "8": "MERGED " + STACK_LANDED, "9": "MERGED " + TOP_LANDED}

    def stack(self, action="stack", members=STACK):
        target = [] if action == "resume" else ["--stack", members]
        r = self.crew("land", action, "--project", self.project, "--org-profile", self.org, *target)
        if "--owner-transcript" in sys.argv:
            print("$ mdstack land %s --project <fixture>/crew.toml --org-profile <fixture>/pack/profile.toml%s"
                  % (action, "".join(" " + t for t in target)))
            print("exit: %d\n--- stdout\n%s--- stderr\n%s" % (r.returncode, r.stdout.replace(self.tmp, "<fixture>"),
                                                             r.stderr), end="")
        return r

    def stack_intent(self):
        path = os.path.join(self.state, "land", "stack", "7-%s.json" % HEAD)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def test_three_member_stack_lands_by_top_change_and_revision_ids(self):
        with open(os.path.join(self.tmp, "pack", "render", "backends", "example.toml")) as f:
            bound = re.findall(r'(?m)^(?:land|land-stack|read-revision-id|land-status|read-head) = "(.*)"$', f.read())
        self.assertEqual(len(bound), 5)
        for cmd in bound:  # no shell in the stack binding: one exland call each
            self.assertRegex(cmd, r"^exland [\w<> -]+$")
        self.rounds("NEW", "QUEUED", "MERGING", self.LANDED_ALL)
        r = self.stack()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls("submit-stack"), [["submit-stack", "9", "D107", "D108", "D109"]])
        self.assertEqual([c[1:] for c in self.calls("rev")], [["7", HEAD], ["8", STACK_HEAD], ["9", TOP_HEAD]])
        self.assertEqual([c[1] for c in self.calls("head")], ["7", "8", "9"])  # every head re-read before it
        for change, head, landed in ((7, HEAD, LANDED), (8, STACK_HEAD, STACK_LANDED), (9, TOP_HEAD, TOP_LANDED)):
            self.assertIn("record: #%d: Landed revision: `%s` (checked head `%s`); stack land of 3 (#7, #8, #9)."
                          % (change, landed, head), r.stdout)
            self.assertIn("marker: #%d: <!-- crew:v1 role=synthesizer pass=merge pr=%d sha=%s round=n/a verdict=n/a "
                          "landed=%s -->" % (change, change, head, landed), r.stdout)
        self.assertEqual(self.stack_intent()["revisions"], ["D107", "D108", "D109"])
        self.assertEqual(self.stack_intent()["landed"], [LANDED, STACK_LANDED, TOP_LANDED])
        self.assertEqual(self.calls("land"), [])
        if "--owner-transcript" in sys.argv:
            print("backend calls, in order:\n" + "".join("  exland %s\n" % " ".join(c) for c in self.calls()), end="")
        self.assertEqual(self.stack("stack-done").returncode, 0)
        self.assertIsNone(self.stack_intent())

    def test_mixed_or_unknown_member_states_record_nothing(self):
        for bad in ({"7": "QUEUED", "8": "MERGING", "9": "QUEUED"},  # queued against landing is unknown here
                    {"7": "MERGED " + LANDED, "8": "MERGED " + STACK_LANDED, "9": "MERGING"},
                    {"7": "NEW", "8": "NEW", "9": "WHATEVER"},
                    {"7": "MERGED abc", "8": "MERGED " + STACK_LANDED, "9": "MERGED " + TOP_LANDED}):
            self.rounds(bad)
            r = self.stack()
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("blocked: land stack #7 @ aaaaaaa, #8 @ ddddddd, #9 @ fffffff: unknown", r.stdout)
            self.assertIn("intent kept", r.stdout)
            self.assertNotIn("record:", r.stdout)
            self.assertNotIn("landed", self.stack_intent())
        self.assertEqual(self.calls("submit-stack"), [])  # an unknown state never requests
        self.assertEqual(len(self.calls("rev")), 3)  # ids resolved once; every rerun used the recorded set
        self.assertEqual(self.stack("stack-done").returncode, 1)

    def test_resume_uses_recorded_ids_and_never_requests(self):
        self.rounds("NEW", "QUEUED")
        r = self.stack()
        self.assertIn("timeout after 3s, still landing; intent kept", r.stdout)
        self.revs({"7": "D107", "8": "D208", "9": "D109"})  # a later upload: resume never re-resolves
        self.rounds(self.LANDED_ALL)
        r = self.stack("resume")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("record: #9: Landed revision: `%s`" % TOP_LANDED, r.stdout)
        self.assertEqual(len(self.calls("submit-stack")), 1)
        self.assertEqual(len(self.calls("rev")), 3)
        self.assertEqual(self.stack_intent()["revisions"], ["D107", "D108", "D109"])

    def record(self, revisions):
        os.makedirs(os.path.join(self.state, "land", "stack"), exist_ok=True)
        with open(os.path.join(self.state, "land", "stack", "7-%s.json" % HEAD), "w") as f:
            json.dump({"members": [[7, HEAD], [8, STACK_HEAD], [9, TOP_HEAD]], "revisions": revisions}, f)

    def test_changed_revision_id_refused_and_read_back_never_resent(self):
        self.record(["D107", "D1", "D109"])  # recorded before #8's id changed; a rerun never re-resolves
        self.rounds("NEW")
        r = self.stack()  # the backend refuses the changed id (a lost acknowledgement) and reads none
        self.assertEqual(r.returncode, 1)
        self.assertIn("request failed and every member's land-status is none", r.stdout)
        self.assertEqual(self.calls("submit-stack"), [["submit-stack", "9", "D107", "D1", "D109"]])
        self.assertEqual(self.calls("rev"), [])
        self.assertIsNone(self.stack_intent())

    def test_lost_acknowledgement_lands_with_exactly_one_request(self):
        with open(os.path.join(self.fake, "land-exit.txt"), "w") as f:
            f.write("1")  # the backend accepts the request but its acknowledgement is lost
        self.rounds("NEW", "QUEUED", self.LANDED_ALL)
        r = self.stack()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls("submit-stack"), [["submit-stack", "9", "D107", "D108", "D109"]])
        self.assertIn("record: #9: Landed revision: `%s`" % TOP_LANDED, r.stdout)
        if "--owner-transcript" in sys.argv:
            print("backend calls, in order:\n" + "".join("  exland %s\n" % " ".join(c) for c in self.calls()), end="")
        probe = subprocess.run([os.path.join(self.tmp, "bin", "exland"), "submit-stack", "9", "D107", "D108", "D109"],
                               env=self.env)
        self.assertEqual(probe.returncode, 1)  # the same accepted request acknowledges nonzero
        if "--owner-transcript" in sys.argv:
            print("acknowledgement probe (after the run): exland submit-stack 9 D107 D108 D109 -> exit %d"
                  % probe.returncode)

    def test_moved_head_or_bad_id_sends_no_request(self):
        self.rounds("NEW")
        self.heads(HEAD, OTHER, TOP_HEAD)
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("#8 revision id read exit 3", r.stdout)  # read-revision-id refuses the moved head
        self.assertIn("no request sent for any member", r.stdout)
        self.assertIsNone(self.stack_intent())
        self.record(["D107", "D108", "D109"])  # ids already recorded, then #9's head moves
        self.heads(HEAD, STACK_HEAD, OTHER)
        r = self.stack()
        self.assertIn("stale head, #9 head is '%s'; no request sent for any member" % OTHER, r.stdout)
        self.assertIsNone(self.stack_intent())
        self.heads(HEAD, STACK_HEAD, TOP_HEAD)
        for bad in ("D1;touch x", "", "two words"):
            self.revs(dict(self.REVS, **{"8": bad}))
            r = self.stack()
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("is not one safe token; no request sent for any member", r.stdout)
            self.assertIsNone(self.stack_intent())
        self.record(["D107", "D1;touch x", "D109"])  # a tampered intent is never substituted
        r = self.stack()
        self.assertIn("are not one safe token per member; nothing requested", r.stdout)
        self.assertEqual(self.calls("submit-stack"), [])

    def test_config_refusals(self):
        mapping_path = os.path.join(self.tmp, "pack", "render", "backends", "example.toml")
        with open(mapping_path) as f:
            mapping = f.read()
        with open(mapping_path, "w") as f:
            f.write(mapping.replace('read-revision-id = "exland rev <rev> <head-sha>"',
                                    'read-revision-id = "exland rev <rev>"'))
        r = self.stack()
        self.assertEqual(r.returncode, 1)
        self.assertIn("change.read-revision-id carries no <head-sha>", r.stdout)
        with open(mapping_path, "w") as f:
            f.write(mapping.replace("<stack-revisions>", "<stack-changes>"))
        r = self.stack()
        self.assertIn("change.land-stack carries no <stack> or <stack-revisions> placeholder", r.stdout)
        self.assertEqual(self.calls(), [])


def contexts(project):
    """(this one-repo profile's context, another repo's) as an intent records them (#1859)."""
    own = {"team": "repo:acme/widgets", "project": os.path.realpath(project), "repo": "acme/widgets"}
    return own, dict(own, team="repo:example/beta", repo="example/beta")


FOREIGN = "is example/beta in team repo:example/beta, not acme/widgets in team repo:acme/widgets"


class RepoBoundIntents(LandFixture):
    """#1859 (team §9.5): request, resume and done act only on an intent recorded for the selected repo. Another
    repo's intent at the same change and head refuses before any status read, request or drop; this repo's is the
    control."""

    def test_foreign_intent_refused_before_any_read_and_own_intent_proceeds(self):
        own, beta = contexts(self.project)
        path = os.path.join(self.state, "land", "7-%s.json" % HEAD)
        cases = [("request", {}, "crew: refusing land #7 @ aaaaaaa: recorded land intent " + FOREIGN),
                 ("resume", {}, "blocked: land intent 7-%s.json: recorded land intent %s" % (HEAD, FOREIGN)),
                 ("done", {"landed": LANDED}, "crew: refusing done #7 @ aaaaaaa: recorded land intent " + FOREIGN)]
        for action, extra, refusal in cases:
            for ctx in (beta, own):
                with self.subTest(action=action, repo=ctx["repo"]):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as f:
                        json.dump(dict({"pr": 7, "head": HEAD, "context": ctx, "recorded": "t"}, **extra), f)
                    with open(path, "rb") as f:
                        before = f.read()
                    self.statuses("landed " + LANDED)
                    calls = len(self.calls())
                    r = self.land(action)
                    if ctx is beta:
                        self.assertEqual(r.returncode, 1, r.stdout)
                        self.assertIn(refusal, r.stdout)
                        self.assertEqual(len(self.calls()), calls)  # no status read, head read or request
                        with open(path, "rb") as f:
                            self.assertEqual(f.read(), before)
                    else:
                        self.assertEqual(r.returncode, 0, r.stdout)
                        self.assertNotIn("refusing", r.stdout)
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(path)
        self.statuses("none", "landed " + LANDED)
        self.assertEqual(self.land().returncode, 0)
        self.assertEqual(self.intent()["context"], own)  # a new intent records this repo


if __name__ == "__main__":
    unittest.main(argv=[a for a in sys.argv if a != "--owner-transcript"])
