"""Tests for mdstack train (#321): a fake `gh` and a logging `git` on PATH, a temp bare origin; fixtures in
crew_testlib.py (stdlib only).

Covers, with the fake `gh` (its `pr merge` squashes onto the temp bare origin): build merges in order
and drops a conflict even when the repo's `info/attributes` sets `merge=union`, never force-pushes and
takes the next train number, CI read only after the grace period with no checks yet counted as pending,
a red train or failing local check lands nothing, land one member per call in order (out of order
refused) with merge records citing the train then close and delete, land stops on a head change, a moved
default branch, a missing verdict, no merge permission, `crew:escalated`, `crew:changes`, `crew:hold`,
an open rereview, an open hold-until, a later rework steer or reviewer `CHANGES_REQUESTED` review at head
(#1118), or a PR GitHub reports `CONFLICTING`; UNKNOWN/API errors pause
and resume the green train; overlapping members kept unless their merge conflicts, and deferred merge-up routing; `close` ends a
train early, recursive bisection and green-on-retry recovery; build and bisect refuse on a rebase backend before any side
effect, and refuse, with nothing built, when the change backend declares land.tests_against_tip (#873 B4); a delegated
train (#1391): `delegate` reserves the number and hands refs to the builder lead (a refused handoff closes it), `build
--train` builds the recorded heads on the recorded base, a concurrent land makes it stale (at build or at land), a
moved head drops as head-moved, a dead builder's train closes before any record, and a red one bisects; the release
cut freeze (#1433): an open cut holds fragment PRs at check and land, and a cut behind main is blocked until
update-branch. Run in CI.
"""
import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import textwrap
import unittest
from unittest import mock
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW, write_pack

LINK = "https://github.com/acme/widgets/actions/runs/1"  # the CI run; gh pr checks links its jobs
PASS, PENDING, FAIL = ([{"name": name, "bucket": b, "link": LINK + "/job/%d" % i} for i, name in enumerate(["ci", "lint"])]
                       for b in ("pass", "pending", "fail"))
# Fake gh: pr view / issue view serve $FAKE_GH_DIR/pr-<n>.json / issue-<n>.json; pr checks plays checks.json in order
# (null: no checks reported yet, exit 1), keeping the last; pr merge squashes refs/pull/<n>/head onto the origin's main
# like GitHub does, refusing a head that is not --match-head-commit; pr list serves open.json (default none open);
# a pr or issue view reports its acme/widgets url unless the served JSON names one (#1859); every call is logged with
# its time.
FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, re, subprocess, sys, tempfile, time
    args, d = sys.argv[1:], os.environ["FAKE_GH_DIR"]
    with open(os.path.join(d, "gh.log"), "a") as f:
        f.write(json.dumps({"t": time.time(), "args": args}) + "\\n")
    pr = lambda n: json.load(open(os.path.join(d, "pr-%s.json" % n)))
    url = lambda kind, view: dict({"url": "https://github.com/acme/widgets/%s/%s" % (kind, args[2])}, **view) \
        if isinstance(view, dict) else view
    if args[:2] == ["pr", "create"]:
        body = args[args.index("--body") + 1]
        members = re.search(r"Members, in landing order: (.*)", body).group(1)
        json.dump([int(n) for n in re.findall(r"#(\\d+) @", members)], open(os.path.join(d, "members.json"), "w"))
        print("https://github.com/acme/widgets/pull/900")
    elif args[:2] == ["pr", "checks"]:
        culprit = os.path.join(d, "culprit.json")
        if os.path.exists(culprit):
            red = json.load(open(culprit)) in json.load(open(os.path.join(d, "members.json")))
            print(json.dumps([{"name": "ci", "bucket": "fail" if red else "pass", "link": "https://github.com/acme/widgets/actions/runs/1"}]))
            sys.exit(0)
        seq = json.load(open(os.path.join(d, "checks.json")))
        json.dump(seq[1:] or seq, open(os.path.join(d, "checks.json"), "w"))
        if seq[0] is None:
            sys.exit("no checks reported on the 'crew/train-1' branch")
        print(json.dumps(seq[0]))
        sys.exit(8 if any(c["bucket"] == "pending" for c in seq[0]) else 0)
    elif args[:1] == ["api"] and "/files" in args[1]:
        path = os.path.join(d, "files-%s.json" % args[1].split("/")[-2])
        print(open(path).read() if os.path.exists(path) else "[]")
    elif args[:1] == ["api"] and "--method" not in args:
        print(open(os.path.join(d, "tree.json")).read())
    elif args[:2] == ["pr", "list"]:
        path = os.path.join(d, "open.json")
        print(open(path).read() if os.path.exists(path) else "[]")
    elif args[:2] == ["pr", "view"]:
        path = os.path.join(d, "views-%s.json" % args[2])
        if os.path.exists(path):
            seq = json.load(open(path))
            json.dump(seq[1:] or seq, open(path, "w"))
            if isinstance(seq[0], str):
                sys.exit(seq[0])
            print(json.dumps(url("pull", seq[0])))
            sys.exit(0)
        print(json.dumps(url("pull", pr(args[2]))))
    elif args[:2] == ["issue", "view"]:
        path = os.path.join(d, "issue-%s.json" % args[2])
        if not os.path.exists(path):
            sys.exit("GraphQL: Could not resolve to an Issue or PullRequest")
        print(json.dumps(url("issues", json.load(open(path)))))
    elif args[0] == "api":
        failure = os.path.join(d, "update-error.txt")
        if os.path.exists(failure):
            sys.exit(open(failure).read())
        print('{}')
    elif args[:2] == ["pr", "review"]:
        failure = os.path.join(d, "review-error.txt")
        if os.path.exists(failure):
            sys.exit(open(failure).read())
    elif args[:2] == ["pr", "merge"]:
        if pr(args[2])["headRefOid"] != args[args.index("--match-head-commit") + 1]:
            sys.exit("GraphQL: Head branch was modified")
        tmp = tempfile.mkdtemp(dir=d)
        for cmd in (["clone", "-q", os.environ["FAKE_ORIGIN"], "."], ["fetch", "-q", "origin", "pull/%s/head" % args[2]],
                    ["merge", "-q", "--squash", "FETCH_HEAD"], ["commit", "-q", "-m", "squash #" + args[2]],
                    ["push", "-q", "origin", "HEAD:main"]):
            subprocess.run([os.environ["FAKE_REAL_GIT"], *cmd], cwd=tmp, check=True, capture_output=True)
        failure = os.path.join(d, "delete-error.txt")
        if "--delete-branch" in args and os.path.exists(failure):  # gh exits non-zero after a landed merge
            view = pr(args[2])
            view["state"] = "MERGED"
            json.dump(view, open(os.path.join(d, "pr-%s.json" % args[2]), "w"))
            sys.exit(open(failure).read())
    """)
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid"}


class TrainBase(Base):
    def setUp(self):
        super().setUp()
        bindir, real = os.path.join(self.tmp, "bin"), shutil.which("git")
        self.gh_dir, self.origin = os.path.join(self.tmp, "gh"), os.path.join(self.tmp, "origin.git")
        os.makedirs(self.gh_dir)
        self.git_log = os.path.join(self.tmp, "git.log")
        for name, text in [("gh", FAKE_GH), ("git", '#!/bin/sh\necho "$*" >> %s\nexec %s "$@"\n' % (self.git_log, real))]:
            with open(os.path.join(bindir, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(bindir, name), 0o755)
        self.env.update(IDENTITY, FAKE_GH_DIR=self.gh_dir, FAKE_ORIGIN=self.origin, FAKE_REAL_GIT=real)
        with open(self.project) as f:
            text = f.read().replace('name = "tmux"\n', 'name = "tmux"\noptions = { merge_grant = "test grant" }\n')
        with open(self.project, "w") as f:
            f.write(text)
        self.git("init", "-q", "--bare", "-b", "main", self.origin, cwd=self.tmp)
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", self.origin)
        self.commit({"a.txt": "base\n", "dev/tests/x/test-ok.py": "print('ok')\n"}, "base")
        self.git("push", "-q", "origin", "main")
        self.checks(PASS)

    def git(self, *args, cwd=None):
        r = subprocess.run(["git", *args], cwd=cwd or self.project_dir, capture_output=True, text=True,
                           env=dict(os.environ, **IDENTITY))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, files, msg):
        for name, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(self.project_dir, name)), exist_ok=True)
            with open(os.path.join(self.project_dir, name), "w") as f:
                f.write(text)
        self.git("add", *files)
        self.git("commit", "-q", "-m", msg)

    def pr(self, n, files, approved=True):
        """A PR head off origin/main at refs/pull/<n>/head, served by the fake gh, approved at head by default."""
        self.git("checkout", "-q", "-B", "pr%d" % n, "origin/main")
        self.commit(files, "pr %d" % n)
        self.git("push", "-q", "origin", "HEAD:refs/pull/%d/head" % n)
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        marker = "<!-- crew:v1 role=reviewer-validator pass=verdict pr=%d sha=%s base=%s round=1 verdict=pass -->" % (
            n, head, self.git("rev-parse", "origin/main"))
        self.serve(n, head, [{"body": "[Vera/verdict] round 1\n" + marker}] if approved else [])
        return head

    def serve(self, n, head, reviews, labels=(), comments=(), mergeable="MERGEABLE"):
        with open(os.path.join(self.gh_dir, "pr-%d.json" % n), "w") as f:
            json.dump({"number": n, "state": "OPEN", "headRefOid": head, "labels": [{"name": x} for x in labels],
                       "statusCheckRollup": [], "reviews": list(reviews), "comments": [{"body": b} for b in comments],
                       "mergeable": mergeable, "closingIssuesReferences": []}, f)

    def complete_view(self, n):
        path = os.path.join(self.gh_dir, "pr-%d.json" % n)
        with open(path) as f:
            view = json.load(f)
        head = view["headRefOid"]
        body = "\n".join("<!-- crew:v1 role=reviewer-validator pass=%s sha=%s verdict=pass -->" % (p, head)
                         for p in ("review", "validate", "verdict"))
        view.update(body="## Acceptance Evidence\nN/A: no observable behaviour changes\n", files=[],
                    isDraft=False, baseRefName="main", closingIssuesReferences=[{"number": 1}],
                    statusCheckRollup=[{"__typename": "StatusContext", "state": "SUCCESS"}],
                    reviews=[{"body": body, "state": "APPROVED", "author": {"login": "acme-reviewer"}}])
        with open(path, "w") as f:
            json.dump(view, f)
        return path, view

    def view(self, n):
        with open(os.path.join(self.gh_dir, "pr-%d.json" % n)) as f:
            pr = json.load(f)
        return pr["headRefOid"], pr["reviews"]

    def issue(self, n, state):
        with open(os.path.join(self.gh_dir, "issue-%d.json" % n), "w") as f:
            json.dump({"state": state}, f)

    def require(self, *names):
        with open(self.project, "a") as f:
            f.write("\n[ci]\nrequired_checks = %s\n" % json.dumps(list(names)))

    def checks(self, *seq):
        with open(os.path.join(self.gh_dir, "checks.json"), "w") as f:
            json.dump(list(seq), f)

    def train(self, *args):
        return self.crew("train", *args, "--project", self.project, "--grace", "0", "--interval", "0.01")

    def gh_calls(self, *prefix):
        """Logged calls under prefix; `api` leaves out the changed-files reads train_spec makes at every gate check."""
        with open(os.path.join(self.gh_dir, "gh.log")) as f:
            calls = [json.loads(line) for line in f]
        return [c for c in calls if c["args"][:len(prefix)] == list(prefix) and not (
            prefix[:1] == ("api",) and "/files" in c["args"][1])]

    def remote(self, ref):
        return self.git("ls-remote", self.origin, ref).split("\t")[0]

    def record(self, n=1):
        with open(os.path.join(self.state, "trains", "train-%d.json" % n)) as f:
            return json.load(f)

    def legacy_overlap(self):
        """Rewrite the record's conflict drop as a pre-#627 `reason=overlap` drop, still routed by update-branch."""
        rec = self.record()
        rec["dropped"][0]["reason"] = "overlap"
        with open(os.path.join(self.state, "trains", "train-1.json"), "w") as f:
            json.dump(rec, f)

    def land_all(self, n, prs):
        return [self.train("land", str(n), str(pr)) for pr in prs]

    def built(self, *prs):
        heads = [self.pr(n, {"f%d.txt" % n: "x\n"}) for n in prs]
        r = self.train("build", *map(str, prs))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return heads


class Bisect(TrainBase):
    def red(self, prs, culprit):
        heads = [self.pr(n, {"f%d.txt" % n: "x\n"}) for n in prs]
        self.checks(FAIL)
        self.assertEqual(self.train("build", *map(str, prs)).returncode, 1)
        with open(os.path.join(self.gh_dir, "culprit.json"), "w") as f:
            json.dump(culprit, f)
        return heads

    def check_culprit(self, culprit):
        prs = [5, 1, 3, 2, 4]
        heads = self.red(prs, culprit)
        r = self.train("bisect", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("culprit pr=%d" % culprit, r.stdout)
        source = self.record()
        self.assertEqual(source["bisect"]["culprits"], [culprit])
        self.assertEqual([[m["pr"] for m in self.record(n)["members"]]
                          for n in source["bisect"]["trains"][:2]], [prs[:2], prs[2:]])
        self.assertIn("%d:ci-culprit" % culprit, source["report"])
        survivor = self.record(source["bisect"]["remaining"])
        expected = [n for n in prs if n != culprit]
        self.assertEqual([m["pr"] for m in survivor["members"]], expected)
        self.assertEqual([m["head"] for m in survivor["members"]], [h for n, h in zip(prs, heads) if n != culprit])
        for n in source["bisect"]["trains"]:
            child = self.record(n)
            self.assertIsNone(child["after"])
            self.assertEqual(child["base"], source["base"])
            if n != survivor["n"]:
                self.assertTrue(child["closed"])
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        for land in self.land_all(survivor["n"], expected):
            self.assertEqual(land.returncode, 0, land.stdout + land.stderr)
        self.assertEqual([int(c["args"][2]) for c in self.gh_calls("pr", "merge")], expected)

    def test_culprit_first(self):
        self.check_culprit(5)

    def test_culprit_middle(self):
        self.check_culprit(3)

    def test_culprit_last(self):
        self.check_culprit(4)

    def check_flaky(self, prs):
        self.red(prs, None)
        r = self.train("bisect", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("culprit=none green-on-retry", r.stdout)
        rec = self.record()
        self.assertEqual(rec["bisect"]["culprits"], [])
        remaining = self.record(rec["bisect"]["remaining"])
        self.assertEqual([m["pr"] for m in remaining["members"]], prs)
        for land in self.land_all(remaining["n"], prs):
            self.assertEqual(land.returncode, 0, land.stdout + land.stderr)

    def test_flaky_train_rebuilds_all_members(self):
        self.check_flaky([1, 2, 3, 4])

    def test_singleton_flaky_train(self):
        self.check_flaky([1])

    def test_failed_predecessor_is_refused_even_if_not_closed(self):
        self.red([1], 1)
        rec = self.record()
        rec["closed"] = False
        with open(os.path.join(self.state, "trains", "train-1.json"), "w") as f:
            json.dump(rec, f)
        self.pr(2, {"f2.txt": "x\n"})
        r = self.train("build", "2", "--after", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("predecessor unavailable", r.stdout)
        self.assertEqual(len(self.gh_calls("pr", "create")), 1)

    def test_changed_member_head_does_not_infer_culprit(self):
        self.red([1, 2], 1)
        self.git("checkout", "-q", "pr1")
        self.commit({"f1.txt": "changed\n"}, "advance member head")
        self.git("push", "-q", "origin", "HEAD:refs/pull/1/head")
        self.git("checkout", "-q", "main")
        r = self.train("bisect", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("head changed", r.stdout)
        self.assertEqual(self.record()["bisect"]["culprits"], [])


class Build(TrainBase):
    def test_backend_tested_land_refuses_local_train(self):
        org = write_pack(os.path.join(self.tmp, "pack"))
        manifest = os.path.join(self.tmp, "pack", "manifest.toml")
        with open(manifest) as f:
            text = f.read().replace('land = "supported"', 'land = "supported"\nland-status = "supported"')
        self.pr(1, {"b.txt": "one\n"})
        for land, refused in (('mode = "async"\n', False),
                              ('mode = "async"\nserializes = true\ntests_against_tip = true\n', True)):
            with open(manifest, "w") as f:
                f.write(text + "\n[land]\n" + land)
            for action in ("build", "bisect"):
                r = self.crew("train", action, "1", "--project", self.project, "--org-profile", org,
                              "--grace", "0", "--interval", "0.01")
                if refused:
                    self.assertEqual(r.returncode, 1)
                    self.assertIn("crew: refusing train %s: the change backend declares land.tests_against_tip"
                                  % action, r.stdout)
                    self.assertFalse(os.path.exists(os.path.join(self.state, "trains", "train-2.json")))
                elif action == "build":  # a bare async declaration grants no exemption: trains still build
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertEqual(self.record()["members"][0]["pr"], 1)

    def test_build_merges_in_order_and_drops_conflict(self):
        h1, h2 = self.pr(1, {"b.txt": "one\n"}), self.pr(2, {"a.txt": "two\n"})
        self.pr(3, {"a.txt": "three\n"})  # conflicts with #2 once #2 is in the train
        with open(os.path.join(self.project_dir, ".git", "info", "attributes"), "w") as f:
            f.write("a.txt merge=union\n")  # the shared repo's own attributes would hide that conflict (train 4)
        base = self.remote("refs/heads/main")
        r = self.train("build", "1", "2", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.record()
        self.assertEqual([(m["pr"], m["head"]) for m in rec["members"]], [(1, h1), (2, h2)])
        self.assertIn("member pr=1 head=%s step=" % h1, r.stdout)
        self.assertIn("dropped pr=3 reason=conflict", r.stdout)
        self.assertEqual(r.stdout.count("ci-link "), 1)  # one run for both jobs
        self.assertIn("ci-link %s\n" % LINK, r.stdout)
        self.assertIn("train n=1 branch=crew/train-1 base=%s sha=%s pr=900 local=skipped ci=pass" % (base, rec["sha"]),
                      r.stdout)
        self.assertEqual(self.remote("refs/heads/crew/train-1"), rec["sha"])
        self.git("fetch", "-q", "origin", "crew/train-1")  # built in a temporary clone, so only the remote has it
        self.assertEqual(self.git("log", "--first-parent", "--format=%s", "%s..%s" % (base, rec["sha"])).splitlines(),
                         ["mdstack train 1: merge #2 @ %s" % h2[:7], "mdstack train 1: merge #1 @ %s" % h1[:7]])
        self.assertEqual(self.git("show", rec["sha"] + ":a.txt"), "two")
        create = self.gh_calls("pr", "create")[0]["args"]
        self.assertIn("--draft", create)
        self.assertEqual(create[create.index("--title") + 1], "mdstack train 1 (CI only, do not merge)")
        with open(self.git_log) as f:
            pushes = [line for line in f if " push " in line]
        self.assertTrue(pushes and not any(" -f" in p or "--force" in p for p in pushes), pushes)
        self.assertEqual(os.listdir(os.path.join(self.tmp, "state", "wt")), [])  # train worktree removed
        os.remove(os.path.join(self.state, "trains", "train-1.json"))  # the remote branch alone still counts
        self.assertEqual(self.train("build", "1").returncode, 0)  # the next train takes the next number
        self.assertEqual(self.remote("refs/heads/crew/train-1"), rec["sha"])
        self.assertNotEqual(self.remote("refs/heads/crew/train-2"), "")

    def test_ci_wait_grace_then_no_checks_yet_is_pending(self):
        self.pr(1, {"b.txt": "one\n"})
        self.checks(None, PENDING, PASS)
        r = self.crew("train", "build", "1", "--project", self.project, "--grace", "0.5", "--interval", "0.01")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ci=pass", r.stdout)
        create, checks = self.gh_calls("pr", "create")[0], self.gh_calls("pr", "checks")
        self.assertEqual(len(checks), 3)
        self.assertGreaterEqual(checks[0]["t"] - create["t"], 0.5)

    def test_ci_wait_holds_until_every_expected_check_registers(self):  # #1536
        self.require("ci", "lint", "repo-guard")
        self.pr(1, {"b.txt": "one\n"})
        guard = {"name": "repo-guard", "bucket": "pass", "link": LINK + "/job/9"}
        self.checks(PASS, PASS + [guard])
        r = self.train("build", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ci=pass", r.stdout)
        self.assertEqual(len(self.gh_calls("pr", "checks")), 2)

    def test_ci_wait_missing_expected_check_times_out_never_green(self):  # #1536
        self.require("ci", "lint", "repo-guard")
        self.pr(1, {"b.txt": "one\n"})
        self.checks(PASS)
        r = self.train("build", "1", "--timeout", "0.2")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ci=timeout", r.stdout)
        self.assertNotIn("ci=pass", r.stdout)
        self.checks(FAIL)  # a red check decides at once, missing names or not
        self.pr(2, {"c.txt": "two\n"})
        r = self.train("build", "2", "--timeout", "30")
        self.assertIn("ci=fail", r.stdout)

    def test_land_rereads_the_expected_checks_and_merges_nothing_while_one_is_absent(self):  # #1536
        self.pr(1, {"b.txt": "one\n"})
        self.pr(2, {"c.txt": "two\n"})
        self.assertEqual(self.train("build", "1", "2").returncode, 0)  # built green with no baseline yet
        self.require("ci", "lint", "repo-guard")  # the baseline set after the build still governs the land
        before = self.remote("refs/heads/main")
        r = self.train("land", "1", "1")
        self.assertIn("paused pr=1 reason=train CI UNKNOWN or pending; missing repo-guard", r.stdout)
        self.assertEqual((self.gh_calls("pr", "merge"), self.remote("refs/heads/main")), ([], before))
        self.checks(PASS + [{"name": "repo-guard", "bucket": "pass", "link": LINK + "/job/9"}])
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("landed pr=1", r.stdout)

    def test_red_ci_or_local_failure_lands_nothing(self):
        self.pr(1, {"b.txt": "one\n"})
        self.checks(FAIL)
        r = self.train("build", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ci-link %s\ntrain n=1" % LINK, r.stdout)  # the failing check, to read after the close
        self.assertIn("ci=fail", r.stdout)
        self.assertEqual([c["args"] for c in self.gh_calls("pr", "close")], [["pr", "close", "900", "-R", "acme/widgets"]])
        self.assertEqual(self.remote("refs/heads/crew/train-1"), "")
        land = self.train("land", "1", "1")
        self.assertEqual(land.returncode, 1)
        self.assertIn("train 1 is CI fail; nothing landed", land.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        self.pr(2, {"dev/tests/x/test-bad.py": "raise SystemExit('boom')\n"})
        r = self.train("build", "2", "--local")
        self.assertEqual(r.returncode, 1)
        self.assertIn("local=fail:dev/tests/x/test-bad.py ci=none", r.stdout)
        self.assertIn("boom", r.stdout)
        self.assertEqual(self.remote("refs/heads/crew/train-2"), "")  # nothing pushed, no train PR
        self.assertEqual(len(self.gh_calls("pr", "create")), 1)

    def test_default_skips_failing_local_suite(self):
        self.pr(1, {"dev/tests/x/test-bad.py": "raise SystemExit('must not run')\n"})
        r = self.train("build", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.record()["local"], "skipped")
        self.assertIn("local=skipped ci=pass", r.stdout)
        self.assertNotIn("must not run", r.stdout)

    def test_profile_opt_in_runs_local_suite(self):
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"',
                                    'merge_grant = "test grant", train_local_checks = true')
        with open(self.project, "w") as f:
            f.write(text)
        self.pr(1, {"dev/tests/x/test-bad.py": "raise SystemExit('boom')\n"})
        r = self.train("build", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("local=fail:dev/tests/x/test-bad.py ci=none", r.stdout)
        self.assertEqual(self.record()["pr"], None)

    def test_overlapping_members_keep_input_order_and_drop_only_on_conflict(self):
        self.pr(1, {"x.txt": "hub", "y.txt": "hub"})
        self.pr(2, {"x.txt": "leaf"})  # conflicts with #1 on x.txt
        self.pr(3, {"z.txt": "leaf"})
        r = self.train("build", "1", "2", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m["pr"] for m in self.record()["members"]], [1, 3])
        self.assertEqual(self.record()["dropped"], [{"pr": 2, "head": self.view(2)[0], "reason": "conflict",
                                                     "merge_up": "queued"}])
        self.assertIn("train-report n=1 members=1,3 landed=none dropped=2:conflict stop=none", r.stdout)
        self.assertEqual(self.gh_calls("api"), [])  # no merge-up while the train is still active
        first = self.train("land", "1", "1")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(self.gh_calls("api"), [])
        last = self.train("land", "1", "3")
        self.assertEqual(last.returncode, 0, last.stdout + last.stderr)
        self.assertIn("merge-up pr=2 status=queued", last.stdout)  # a conflict waits for its builder, never update-branch
        self.assertEqual(self.gh_calls("api"), [])

    def test_legacy_overlap_drop_routes_by_update_branch_once(self):
        self.pr(1, {"x.txt": "first"})
        self.pr(2, {"x.txt": "second"})
        self.assertEqual(self.train("build", "1", "2").returncode, 0)
        self.legacy_overlap()
        last = self.train("land", "1", "1")
        self.assertEqual(last.returncode, 0, last.stdout + last.stderr)
        self.assertIn("merge-up pr=2 status=updated", last.stdout)
        calls = self.gh_calls("api")
        self.assertEqual(len(calls), 1)
        self.assertIn("expected_head_sha=" + self.view(2)[0], calls[0]["args"])
        self.assertEqual(self.train("route", "1").returncode, 0)
        self.assertEqual(len(self.gh_calls("api")), 1)

    def test_merge_up_failure_remains_queued_for_retry(self):
        self.pr(1, {"x.txt": "first"})
        self.pr(2, {"x.txt": "second"})
        self.assertEqual(self.train("build", "1", "2").returncode, 0)
        self.legacy_overlap()
        path = os.path.join(self.gh_dir, "update-error.txt")
        with open(path, "w") as f:
            f.write("HTTP 503 Service Unavailable")
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("merge-up pr=2 status=queued", r.stdout)
        os.remove(path)
        self.assertEqual(self.train("route", "1").returncode, 0)
        self.assertEqual(self.record()["dropped"][0]["merge_up"], "updated")

    def test_conflict_routes_to_attached_builder_once_after_last_land(self):
        self.pr(1, {"x.txt": "first"})
        self.pr(2, {"x.txt": "second"})
        self.assertEqual(self.train("build", "1", "2").returncode, 0)
        head, reviews = self.view(2)
        self.serve(2, head, reviews, mergeable="CONFLICTING")
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash", "10": "ben-2"}}, f)
        self.put("runs/ben-2.json", json.dumps(dict(index=10, role="builder", item="issue #2",
                 **{"pass": "build"}, repo=self.project_dir, worktree=self.project_dir, claim="unused", engine="codex",
                 model="test", effort="medium", harness="codex", pr=2)))
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("merge-up pr=2 status=builder", r.stdout)
        path = os.path.join(self.state, "inbox", "ben-2.jsonl")
        with open(path) as f:
            message = json.loads(f.read())
        self.assertEqual(message["kind"], "fix")
        self.assertEqual(message["refs"][:2], ["#2", head])
        self.assertEqual(self.train("route", "1").returncode, 0)
        with open(path) as f:
            self.assertEqual(len(f.readlines()), 1)

    def test_held_deferred_member_stays_queued(self):
        self.pr(1, {"x.txt": "first"})
        self.pr(2, {"x.txt": "second"})
        self.assertEqual(self.train("build", "1", "2").returncode, 0)
        self.legacy_overlap()
        head, reviews = self.view(2)
        self.serve(2, head, reviews, labels=["crew:hold"])
        self.assertEqual(self.train("land", "1", "1").returncode, 0)
        self.assertEqual(self.gh_calls("api"), [])
        self.serve(2, head, reviews)
        self.assertEqual(self.train("route", "1").returncode, 0)
        self.assertEqual(self.record()["dropped"][0]["merge_up"], "updated")


class LonePrLand(TrainBase):
    """#1425: membership is decided before the push; drops leaving one member land it directly under direct."""

    def direct(self):
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"', 'merge_grant = "test grant", lone_pr_land = "direct"')
        with open(self.project, "w") as f:
            f.write(text)

    def test_one_drop_collapses_to_direct_without_a_train_branch_pr_or_ci(self):
        self.direct()
        h1 = self.pr(1, {"a.txt": "one\n"})
        self.pr(2, {"a.txt": "two\n"})  # conflicts with #1 on the train branch
        r = self.train("build", "1", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("dropped pr=2 reason=conflict", r.stdout)
        self.assertIn("direct pr=1 head=%s reason=collapsed-to-direct: train 1 dropped #2 (conflict)" % h1, r.stdout)
        self.assertNotIn("merge-up", r.stdout)  # its drop routes after the direct land (train route 1)
        self.assertIn("train-report n=1 members=1 landed=none dropped=2:conflict stop=none "
                      "path=direct:collapsed-to-direct", r.stdout)
        rec = self.record()
        self.assertEqual((rec["path"], rec["closed"], rec["pr"], rec["ci"], rec["local"]), ("direct", True, None, "none", "none"))
        self.assertEqual(rec["path_reason"], "collapsed-to-direct: train 1 dropped #2 (conflict)")
        self.assertEqual(self.gh_calls("pr", "create"), [])
        self.assertEqual(self.gh_calls("pr", "checks"), [])
        self.assertEqual(self.remote("refs/heads/crew/train-1"), "")  # no train branch pushed
        land = self.train("land", "1", "1")  # nothing lands through the collapsed train: the synthesizer lands directly
        self.assertEqual(land.returncode, 1)
        self.assertIn("train 1 is CI none; nothing landed", land.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_resurvey_after_collapse_sees_the_survivor_alone_until_it_lands(self):
        self.direct()
        h1 = self.pr(1, {"a.txt": "one\n"})
        h2 = self.pr(2, {"a.txt": "two\n"})  # merges into main alone, conflicts only with #1
        for n in (1, 2):
            self.complete_view(n)
        self.assertIn("direct pr=1 ", self.train("build", "1", "2").stdout)
        r = self.train("check", "1", "2")  # the lone-ready re-survey: #2 is not ready at its dropped head
        self.assertIn("gate pr=1 sha=%s name=train-merge status=pass" % h1, r.stdout)
        self.assertIn('gate pr=2 sha=%s name=train-merge status=blocked reason="dropped at this head by collapsed '
                      'train 1 while #1 is open: not ready until it lands or closes"' % h2, r.stdout)
        h3 = self.pr(3, {"c.txt": "three\n"})
        self.complete_view(3)
        r = self.train("check", "1", "2", "3")  # a new ready PR: #1 and #3 are ready, so they train
        self.assertIn("gate pr=3 sha=%s name=train-merge status=pass" % h3, r.stdout)
        self.assertIn("pr=2 sha=%s name=train-merge status=blocked" % h2, r.stdout)
        self.git("fetch", "-q", "origin", "pull/1/head")  # the survivor lands directly
        self.git("merge", "-q", "--squash", "FETCH_HEAD")
        self.git("commit", "-q", "-m", "squash #1")
        self.git("push", "-q", "origin", "main")
        path = os.path.join(self.gh_dir, "pr-1.json")
        with open(path) as f:
            view = json.load(f)
        view["state"] = "MERGED"
        with open(path, "w") as f:
            json.dump(view, f)
        r = self.train("check", "2")  # now the conflict is real on main
        self.assertIn('name=train-merge status=blocked reason="conflict on %s' % self.remote("refs/heads/main")[:7], r.stdout)
        route = self.train("route", "1")
        self.assertIn("merge-up pr=2 status=queued", route.stdout)  # a conflict waits for its builder

    def test_train_policy_or_no_drop_keeps_the_one_member_train(self):
        self.pr(1, {"a.txt": "one\n"})
        self.pr(2, {"a.txt": "two\n"})
        r = self.train("build", "1", "2")  # lone_pr_land = "train" (default): today's one-member train
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("direct pr=", r.stdout)
        self.assertIn("dropped=2:conflict stop=none path=train", r.stdout)
        self.assertEqual((self.record()["path"], self.record()["ci"], self.record()["pr"]), ("train", "pass", 900))
        self.assertNotEqual(self.remote("refs/heads/crew/train-1"), "")
        self.direct()
        r = self.train("build", "1")  # one member without a drop (a bisect half) still trains
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("direct pr=", r.stdout)
        self.assertEqual(self.record(2)["path"], "train")

    def test_new_ready_pr_during_the_collapse_forms_a_train(self):
        self.direct()
        h1 = self.pr(1, {"a.txt": "one\n"})
        self.pr(2, {"a.txt": "two\n"})
        self.assertIn("direct pr=1 ", self.train("build", "1", "2").stdout)
        h3 = self.pr(3, {"c.txt": "three\n"})  # ready before the direct land's re-survey: the two ready PRs train
        r = self.train("build", "1", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("direct pr=", r.stdout)
        rec = self.record(2)
        self.assertEqual([(m["pr"], m["head"]) for m in rec["members"]], [(1, h1), (3, h3)])
        self.assertEqual((rec["path"], rec["ci"]), ("train", "pass"))
        self.pr(4, {"a.txt": "four\n"})
        r = self.train("build", "1", "3", "4")  # a drop leaving two members trains as today
        self.assertIn("members=1,3 landed=none dropped=4:conflict stop=none path=train", r.stdout)


class RebaseStrategy(TrainBase):
    def test_build_and_bisect_refuse_before_side_effects(self):  # #952 (#874 B3)
        org = write_pack(os.path.join(self.tmp, "pack"))
        with open(os.path.join(self.tmp, "pack", "manifest.toml"), "a") as f:
            f.write('\n[strategy]\nupdate_from_base = "rebase"\nretains_prior_heads = true\n')
        self.pr(1, {"f1.txt": "x\n"})
        open(self.git_log, "w").close()
        for action in ("build", "bisect"):
            r = self.crew("train", action, "1", "--project", self.project, "--org-profile", org)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(r.stdout, 'crew: refusing train %s: the change backend declares strategy.update_from_base '
                             '= "rebase", and a merge train stacks merge commits; land ready PRs one at a time after '
                             "the declared update\n" % action)
        with open(self.git_log) as f:
            self.assertEqual(f.read(), "")
        self.assertFalse(os.path.exists(os.path.join(self.gh_dir, "gh.log")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "state", "wt")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "trains")))
        self.assertEqual(self.remote("refs/heads/crew/train-1"), "")

    def test_merge_strategy_still_builds(self):
        org = write_pack(os.path.join(self.tmp, "pack"))
        with open(os.path.join(self.tmp, "pack", "manifest.toml"), "a") as f:
            f.write('\n[strategy]\nupdate_from_base = "merge"\n')
        self.pr(1, {"f1.txt": "x\n"})
        r = self.crew("train", "build", "1", "--project", self.project, "--org-profile", org, "--grace", "0",
                      "--interval", "0.01")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.record()["members"][0]["pr"], 1)


class Pipeline(TrainBase):
    def test_successor_prepared_while_ci_pending_then_lands_serially(self):
        self.pr(1, {"one.txt": "one"})
        self.pr(2, {"two.txt": "two"})
        self.assertEqual(self.train("build", "1", "--no-wait").returncode, 0)
        self.assertEqual(self.record()["ci"], "pending")
        self.assertEqual(self.gh_calls("pr", "checks"), [])
        result = self.train("build", "1", "2", "--after", "1", "--no-wait")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("deferred pr=1 reason=predecessor-member", result.stdout)
        self.assertEqual(self.record(2)["base"], self.record()["sha"])
        self.assertEqual(self.train("wait", "2").returncode, 0)
        result = self.train("land", "2", "2")
        self.assertIn("predecessor has not finished", result.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        self.assertEqual(self.train("wait", "1").returncode, 0)
        self.assertEqual(self.train("land", "1", "1").returncode, 0)
        result = self.train("land", "2", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([c["args"][2] for c in self.gh_calls("pr", "merge")], ["1", "2"])

    def test_paused_predecessor_preserves_successor_ci_and_allows_preparation(self):
        self.built(1)
        self.pr(2, {"two.txt": "two"})
        self.pr(3, {"three.txt": "three"})
        self.assertEqual(self.train("build", "2", "--after", "1", "--no-wait").returncode, 0)
        head, reviews = self.view(1)
        self.serve(1, head, reviews, mergeable="UNKNOWN")
        self.assertEqual(self.train("land", "1", "1").returncode, 1)
        self.assertTrue(self.record()["stopped"]["paused"])
        self.assertEqual(self.train("wait", "2").returncode, 0)
        successor = self.record(2)
        result = self.train("land", "2", "2")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("predecessor has not finished", result.stdout)
        self.assertEqual(self.record(2), successor)
        self.assertEqual(self.train("build", "3", "--after", "1", "--no-wait").returncode, 0)
        self.serve(1, head, reviews)
        self.assertEqual(self.train("land", "1", "1").returncode, 0)
        self.assertEqual(self.train("land", "2", "2").returncode, 0)
        self.assertEqual([c["args"][2] for c in self.gh_calls("pr", "merge")], ["1", "2"])

    def test_stopped_predecessor_rebuilds_successor_on_new_main(self):
        self.built(1, 2)
        self.pr(3, {"three.txt": "three"})
        self.assertEqual(self.train("build", "3", "--after", "1", "--no-wait").returncode, 0)
        self.assertEqual(self.train("land", "1", "1").returncode, 0)
        head, reviews = self.view(2)
        self.serve(2, head, reviews, labels=["crew:hold"])
        self.assertEqual(self.train("land", "1", "2").returncode, 1)
        result = self.train("wait", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rebuild train=2 reason=predecessor-stopped", result.stdout)
        self.assertTrue(self.record(2)["closed"])
        self.assertEqual(self.record(3)["base"], self.remote("refs/heads/main"))
        self.assertIsNone(self.record(3)["after"])
        self.assertEqual(self.train("land", "3", "3").returncode, 0)

    def test_shared_file_without_conflict_stays_in_train(self):
        self.commit({"a.txt": "first\n" + "middle\n" * 12 + "last\n"}, "multiline base")
        self.git("push", "-q", "origin", "main")
        self.pr(1, {"a.txt": "FIRST\n" + "middle\n" * 12 + "last\n"})
        self.pr(2, {"a.txt": "first\n" + "middle\n" * 12 + "LAST\n"})
        result = self.train("build", "1", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rec = self.record()
        self.assertEqual([m["pr"] for m in rec["members"]], [1, 2])
        self.assertEqual([m["paths"] for m in rec["members"]], [["a.txt"], ["a.txt"]])
        self.assertEqual(rec["dropped"], [])
        self.git("fetch", "-q", "origin", "crew/train-1")
        self.assertEqual(self.git("show", rec["sha"] + ":a.txt"), "FIRST\n" + "middle\n" * 12 + "LAST")


class Precheck(TrainBase):
    def test_reports_all_prs_without_git_build_or_github_writes(self):
        self.pr(1, {"one.txt": "one"})
        self.pr(2, {"two.txt": "two"})
        self.complete_view(1)
        path, view = self.complete_view(2)
        view["labels"] = [{"name": "crew:sensitive"}, {"name": "crew:needs-mirror"}]
        view["body"] = "no evidence"
        view["statusCheckRollup"] = []
        with open(path, "w") as f:
            json.dump(view, f)
        result = self.train("check", "1", "2")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for text in ("name=verdict status=pass", "name=evidence status=manual", "name=sensitive status=blocked",
                     "name=mirror status=blocked", "name=ci status=blocked", "name=evidence status=blocked"):
            self.assertIn(text, result.stdout)
        self.assertEqual(self.gh_calls("pr", "create"), [])
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        with open(self.git_log) as f:
            self.assertNotIn(" merge -q", f.read())  # the train-merge pre-filter uses merge-tree, never a merge
        self.assertFalse(os.path.exists(os.path.join(self.state, "trains")))

    def test_check_prefilters_a_conflict_with_the_current_base(self):
        self.pr(1, {"a.txt": "one\n"})
        self.pr(2, {"c.txt": "two\n"})
        self.commit({"a.txt": "main moved\n"}, "main")
        self.git("push", "-q", "origin", "main")
        self.complete_view(1)
        self.complete_view(2)
        base = self.remote("refs/heads/main")
        r = self.train("check", "1", "2")
        self.assertIn('gate pr=1 sha=%s name=train-merge status=blocked reason="conflict on %s: route to merge-up '
                      'before training"' % (self.view(1)[0], base[:7]), r.stdout)
        self.assertIn('gate pr=2 sha=%s name=train-merge status=pass' % self.view(2)[0], r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "trains")))
        self.assertEqual(self.gh_calls("pr", "create"), [])

    def test_check_blocks_ci_missing_an_expected_check(self):  # #1536
        self.require("markdownlint", "repo-guard")
        self.pr(1, {"one.txt": "one"})
        path, view = self.complete_view(1)
        head = view["headRefOid"]
        view["statusCheckRollup"] = [{"__typename": "CheckRun", "name": "repo-guard", "status": "COMPLETED",
                                      "conclusion": "SUCCESS"}]
        with open(path, "w") as f:
            json.dump(view, f)
        r = self.train("check", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn('gate pr=1 sha=%s name=ci status=blocked reason="checks pending; missing markdownlint"' % head,
                      r.stdout)
        view["statusCheckRollup"].append(dict(view["statusCheckRollup"][0], name="markdownlint"))
        with open(path, "w") as f:
            json.dump(view, f)
        self.assertIn("gate pr=1 sha=%s name=ci status=pass" % head, self.train("check", "1").stdout)

    def test_failed_validate_marker_cannot_pass_precheck(self):
        self.pr(1, {"one.txt": "one"})
        path, view = self.complete_view(1)
        head = view["headRefOid"]
        view["reviews"][0]["body"] = view["reviews"][0]["body"].replace(
            "pass=validate sha=%s verdict=pass" % head, "pass=validate sha=%s verdict=changes" % head)
        with open(path, "w") as f:
            json.dump(view, f)
        result = self.train("check", "1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("name=verdict status=blocked", result.stdout)


    def test_evidence_artifacts_checked_at_head(self):
        self.pr(1, {"one.txt": "one"})
        path, view = self.complete_view(1)
        view["body"] = "## Acceptance Evidence\nCLI: evidence/1/output.txt\n"
        with open(path, "w") as f:
            json.dump(view, f)
        for present in (True, False):
            with open(os.path.join(self.gh_dir, "tree.json"), "w") as f:
                json.dump({"tree": [{"path": "evidence/1/output.txt"}] if present else []}, f)
            result = self.train("check", "1")
            self.assertEqual(result.returncode, 0 if present else 1, result.stdout + result.stderr)
            self.assertIn("name=evidence status=" + ("manual" if present else "blocked"), result.stdout)
        self.assertIn(view["headRefOid"], self.gh_calls("api")[-1]["args"][1])

    def evidence_check(self, body, reviews=(), tree=()):
        if not os.path.exists(os.path.join(self.gh_dir, "pr-1.json")):
            self.pr(1, {"one.txt": "one"})
        path, view = self.complete_view(1)
        head = view["headRefOid"]
        view["body"] = body
        view["reviews"] += [{"body": r.replace("HEAD", head)} for r in reviews]
        with open(path, "w") as f:
            json.dump(view, f)
        with open(os.path.join(self.gh_dir, "tree.json"), "w") as f:
            json.dump({"tree": [{"path": p} for p in tree]}, f)
        return self.train("check", "1")

    def test_prefixed_evidence_paths_are_not_required_artifacts(self):
        result = self.evidence_check("## Acceptance Evidence\nAdapter: templates/evidence/cli-exit-stdout.md; "
                                     "setup `.crew/evidence/demo.py`, a/evidence/x.txt\n```sh\nrun\n```\n"
                                     "```text\nok\n```\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('name=evidence status=manual reason="inline reproduction', result.stdout)
        self.assertEqual(self.gh_calls("api"), [])

    def test_real_evidence_path_still_required_next_to_prefixed_ones(self):
        body = "## Acceptance Evidence\nSee templates/evidence/cli-exit-stdout.md and `evidence/1/out.txt`.\n"
        result = self.evidence_check(body, tree=["evidence/1/out.txt"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("name=evidence status=manual reason=\"artifacts present", result.stdout)
        result = self.evidence_check(body)
        self.assertEqual(result.returncode, 1)
        self.assertIn('name=evidence status=blocked reason="missing artifacts: evidence/1/out.txt"', result.stdout)

    def test_prose_evidence_slash_is_not_an_artifact(self):
        result = self.evidence_check("## Acceptance Evidence\n| 2 | scope, evidence/citation, direction rule |\n"
                                     "Bare evidence/run dir, evidence/citation. Next.\n```sh\nrun\n```\n```text\nok\n```\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('name=evidence status=manual reason="inline reproduction', result.stdout)
        self.assertEqual(self.gh_calls("api"), [])

    def test_artifact_shaped_evidence_paths_are_checked(self):
        refs = {"`evidence/1/dir`": "evidence/1/dir", "[run](evidence/1/run)": "evidence/1/run",
                "![shot](evidence/1/shot.png)": "evidence/1/shot.png", "see evidence/1/out.txt.": "evidence/1/out.txt"}
        for ref, path in refs.items():
            body = "## Acceptance Evidence\nscope, evidence/citation; " + ref + "\n"
            result = self.evidence_check(body, tree=[path])
            self.assertEqual(result.returncode, 0, ref + result.stdout + result.stderr)
            self.assertIn('name=evidence status=manual reason="artifacts present', result.stdout)
            result = self.evidence_check(body)
            self.assertEqual(result.returncode, 1, ref)
            self.assertIn('name=evidence status=blocked reason="missing artifacts: %s"' % path, result.stdout)

    def test_only_body_evidence_section_and_head_builder_fix_reviews_count(self):
        stale = "<!-- crew:v1 role=builder pass=fix pr=1 sha=0000000 round=1 -->"
        other = "<!-- crew:v1 role=reviewer-validator pass=review sha=HEAD verdict=changes -->"
        result = self.evidence_check("## Context\nevidence/9/ctx.txt\n\n## Acceptance Evidence\nN/A: docs only change\n",
                                     ["evidence/9/review.txt\n" + other, "evidence/9/stale.txt\n" + stale])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("name=evidence status=manual reason=\"verify the stated N/A", result.stdout)
        for kind in ("fix", "ci-fix"):
            result = self.evidence_check("## Acceptance Evidence\nsee fix review\n",
                                         ["evidence/9/fix.txt\n<!-- crew:v1 role=builder pass=%s sha=HEAD -->" % kind])
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing artifacts: evidence/9/fix.txt", result.stdout)

    def test_inline_reproduction_in_head_fix_review_with_tilde_fences(self):
        fix = "~~~sh\nrun\n~~~\n~~~text\nok\n~~~\n<!-- crew:v1 role=builder pass=fix sha=HEAD round=1 -->"
        for body, reviews, code in (("## Acceptance Evidence\nsee fix review\n", [fix], 0),
                                    ("## Acceptance Evidence\n~~~sh\nrun\n~~~\n```text\nok\n```\n", [], 0),
                                    ("## Acceptance Evidence\nsee fix review\n", [fix.replace("HEAD", "0000000")], 1)):
            result = self.evidence_check(body, reviews)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            self.assertIn("name=evidence status=" + ("manual" if code == 0 else "blocked"), result.stdout)


    def test_head_fix_proof_supersedes_missing_body_artifacts(self):
        body = "## Acceptance Evidence\n![R1](evidence/r1.png) and `evidence/run.log`\n"
        marker = "<!-- crew:v1 role=builder pass=fix sha=HEAD round=1 -->"
        fix = "~~~sh\nrun\n~~~\n~~~text\nok\n~~~\n" + marker
        for reviews, code in (((), 1), ([fix.replace("HEAD", "0000000")], 1), (["see body\n" + marker], 1), ([fix], 0)):
            result = self.evidence_check(body, reviews)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            if code:
                self.assertIn('name=evidence status=blocked reason="missing artifacts: evidence/r1.png, evidence/run.log"',
                              result.stdout)
            else:
                self.assertIn('name=evidence status=manual reason="missing artifacts superseded by inline fix proof '
                              'at head: evidence/r1.png, evidence/run.log', result.stdout)

    def test_evidence_paths_quoted_in_code_are_not_cited(self):
        rows = ("| AC: missing real artifact | `missing-artifact-blocks-prose-ignored`: a body citing "
                "`![R1](evidence/r1.png)` and `` `evidence/run.log` `` gives `status=blocked reason=\"missing artifacts: "
                "evidence/r1.png, evidence/run.log\"` | A12 |\n"
                "| AC: prose-scan | Same step: a body mentioning `evidence/citation` rules, "
                "`../templates/evidence/cli-exit-stdout.md` and `.crew/evidence/s.log`, with an inline R1 pair | A12 |\n")
        fences = "```sh\ncat evidence/r1.log\n```\n```text\nevidence/r1.log\n```\n"
        result = self.evidence_check("## Acceptance Evidence\n" + rows + fences)  # the #1080 body
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('name=evidence status=manual reason="inline reproduction', result.stdout)
        self.assertEqual(self.gh_calls("api"), [])
        result = self.evidence_check("## Acceptance Evidence\n" + rows + "Real: `evidence/1/out.txt`\n" + fences)
        self.assertEqual(result.returncode, 1)
        self.assertIn('name=evidence status=blocked reason="missing artifacts: evidence/1/out.txt"', result.stdout)

    def test_inline_reproduction_under_test_output_counts(self):
        body = ("## Test Output\n```sh\nrun\n```\n```text\nok\n```\n\n"
                "## Acceptance Evidence\n| AC | Proof |\n| 1 | R1 in Test Output |\n")
        result = self.evidence_check(body)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('name=evidence status=manual reason="inline reproduction', result.stdout)

    def test_no_fences_in_builder_posts_still_blocks(self):
        fences = "```sh\nrun\n```\n```text\nok\n```\n"
        other = "<!-- crew:v1 role=reviewer-validator pass=review sha=HEAD verdict=pass -->"
        coordinator = "<!-- crew:v1 role=coordinator pass=route sha=HEAD -->"
        for reviews in ((), (fences + other, fences + coordinator)):
            result = self.evidence_check("## Test Output\nsee R1\n\n## Acceptance Evidence\nR1\n", reviews)
            self.assertEqual(result.returncode, 1)
            self.assertIn('name=evidence status=blocked reason="no evidence artifacts', result.stdout)
        result = self.evidence_check("## Context\nevidence/9/ctx.txt\n" + fences + "\n## Acceptance Evidence\nR1\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.gh_calls("api"), [])

    def test_user_attachments_media_is_manual_other_hosts_block(self):
        shot = "![items view](https://github.com/user-attachments/assets/0a12-items) route `/`, 1280x800, sha HEAD\n"
        video = "https://github.com/user-attachments/assets/0a12-run.mp4 device Pixel 8, build 42, sha HEAD\n"
        fix = "<!-- crew:v1 role=builder pass=fix sha=HEAD round=1 -->"
        for body, reviews in (("## Acceptance Evidence\nShape: Web, W1. " + shot, ()),
                              ("## Acceptance Evidence\nShape: Mobile. " + video, ()),
                              ("## Acceptance Evidence\nsee fix review\n", (shot + fix,))):
            result = self.evidence_check(body, reviews)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('name=evidence status=manual reason="user-attachments media', result.stdout)
        for body, reviews in (("## Acceptance Evidence\n![a12](https://media.example.com/a12.png)\n", ()),
                              ("## Acceptance Evidence\nhttps://github.com/user-attachments.example.com/a/b.png\n", ()),
                              ("## Acceptance Evidence\nhttps://evil.example/https://github.com/user-attachments/a/b\n", ()),
                              ("## Context\n" + shot + "\n## Acceptance Evidence\nsee above\n", ()),
                              ("## Acceptance Evidence\nsee fix review\n", (shot + fix.replace("HEAD", "0000000"),))):
            result = self.evidence_check(body, reviews)
            self.assertEqual(result.returncode, 1, body)
            self.assertIn('name=evidence status=blocked reason="no evidence artifacts', result.stdout)

    def mirror_check(self, path):
        view_path, view = self.complete_view(1)
        view["files"] = [{"path": path}]
        with open(view_path, "w") as f:
            json.dump(view, f)
        return self.train("check", "1")

    def framework_checkout(self):
        """The checkout carries cli/mdstack, as mdstack's own does under any repo name (#1234)."""
        os.makedirs(os.path.join(self.project_dir, "cli"), exist_ok=True)
        with open(os.path.join(self.project_dir, "cli", "mdstack"), "w") as f:
            f.write("")

    def test_missing_mirror_record_blocks_without_label(self):
        self.framework_checkout()
        self.pr(1, {"one.txt": "one"})
        result = self.mirror_check("templates/runtimes/tmux/synthesizer.md")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('name=mirror status=blocked reason="no coordinator mirror/drift record"', result.stdout)

    def test_product_repo_templates_need_no_mirror(self):
        self.pr(1, {"one.txt": "one"})
        for path in ("templates/foo.html", "docs/protocol.md"):
            result = self.mirror_check(path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('name=mirror status=pass reason="no mirrored paths"', result.stdout)

    def test_profile_mirror_none_passes_with_label_and_mirrored_paths(self):
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"', 'merge_grant = "test grant", mirror = "none"')
        self.framework_checkout()
        with open(self.project, "w") as f:
            f.write(text)
        self.pr(1, {"one.txt": "one"})
        for labels in ([], [{"name": "crew:needs-mirror"}]):
            view_path, view = self.complete_view(1)
            view.update(files=[{"path": "templates/runtimes/tmux/synthesizer.md"}, {"path": "docs/protocol.md"}],
                        labels=labels)
            with open(view_path, "w") as f:
                json.dump(view, f)
            result = self.train("check", "1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('name=mirror status=pass reason="n/a: profile mirror = none"', result.stdout)

    def test_profile_mirror_none_leaves_other_holds_blocking(self):
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"', 'merge_grant = "test grant", mirror = "none"')
        with open(self.project, "w") as f:
            f.write(text)
        self.pr(1, {"one.txt": "one"})
        view_path, view = self.complete_view(1)
        view["labels"] = [{"name": "crew:needs-mirror"}, {"name": "crew:sensitive"}]
        with open(view_path, "w") as f:
            json.dump(view, f)
        result = self.train("check", "1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('name=mirror status=pass reason="n/a: profile mirror = none"', result.stdout)
        self.assertIn("name=sensitive status=blocked", result.stdout)

    def test_live_copy_label_still_blocks(self):
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"', 'merge_grant = "test grant", mirror = "live-copy"')
        with open(self.project, "w") as f:
            f.write(text)
        self.pr(1, {"one.txt": "one"})
        view_path, view = self.complete_view(1)
        view["labels"] = [{"name": "crew:needs-mirror"}]
        with open(view_path, "w") as f:
            json.dump(view, f)
        result = self.train("check", "1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('name=mirror status=blocked reason="crew:needs-mirror"', result.stdout)


VERDICT = "<!-- crew:v1 role=reviewer-validator pass=verdict pr=%d sha=%s round=1 verdict=pass -->"
REREVIEW = "<!-- crew:v1 role=coordinator pass=steer pr=%d sha=%s round=n/a verdict=n/a cmd=rereview cmd-id=9 -->"


class Land(TrainBase):
    def test_project_stop_blocks_other_pr_and_matching_resume_allows_new_train(self):
        self.built(1)
        stop = {"body": "<!-- crew:v1 role=coordinator pass=steer cmd=stop-landing cmd-id=incident sha=%s -->" % ("0" * 40)}
        head, reviews = self.view(1)
        self.serve(1, head, reviews + [stop])
        control_path = os.path.join(self.gh_dir, "issue-99.json")
        control = {"state": "CLOSED", "comments": [stop]}
        with open(control_path, "w") as f:
            json.dump(control, f)
        self.put("landing-control.json", '{"issue": 99}')
        result = self.train("land", "1", "1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("open stop-landing: incident", result.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        control["comments"].append({"body": "<!-- crew:v1 role=coordinator pass=steer cmd=resume-landing stop-id=incident cmd-id=recovered -->"})
        with open(control_path, "w") as f:
            json.dump(control, f)
        self.assertEqual(self.train("build", "1").returncode, 0)
        result = self.train("land", "2", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.gh_calls("pr", "merge")), 1)

    def head(self, n, **fields):
        path = os.path.join(self.gh_dir, "pr-%d.json" % n)
        with open(path) as f:
            view = json.load(f)
        view.update(dict(headRefName="builder/%d-x" % n, baseRefName="main", isCrossRepository=False,
                         headRepositoryOwner={"login": "acme"}, headRepository={"name": "widgets"}), **fields)
        with open(path, "w") as f:
            json.dump(view, f)

    def merge_record(self):
        post = self.gh_calls("pr", "review")[-1]["args"]
        return post[post.index("--body") + 1]

    def test_same_repo_head_is_deleted_by_the_merge_itself(self):  # #395
        head = self.built(1)[0]
        self.head(1)
        result = self.train("land", "1", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([c["args"] for c in self.gh_calls("pr", "merge")],
                         [["pr", "merge", "1", "-R", "acme/widgets", "--squash", "--match-head-commit", head,
                           "--delete-branch"]])
        self.assertIn("branch pr=1 deleted at merge", result.stdout)
        self.assertIn("- Head branch: deleted at merge.", self.merge_record())
        self.assertFalse([c for c in self.gh_calls() if c["args"][:1] == ["api"] and "-X" in c["args"]])

    def test_fork_default_base_and_unknown_heads_are_never_deleted(self):  # #395
        cases = [(dict(isCrossRepository=True, headRepositoryOwner={"login": "fork"}), "fork"),
                 (dict(headRepository={"name": "other"}), "fork"),
                 (dict(headRefName="main"), "default or base branch"),
                 (dict(headRefName=None, isCrossRepository=None), "fork")]
        for n, (fields, reason) in enumerate(cases, 1):
            with self.subTest(fields=fields):
                head = self.built(n)[0]
                self.head(n, **fields)
                result = self.train("land", str(n), str(n))
                self.assertIn("branch pr=%d retained (%s)" % (n, reason), result.stdout)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.gh_calls("pr", "merge")[-1]["args"],
                                 ["pr", "merge", str(n), "-R", "acme/widgets", "--squash", "--match-head-commit", head])
                self.assertIn("- Head branch: retained (%s)." % reason, self.merge_record())

    def test_failed_delete_after_landed_merge_records_the_land(self):  # #395
        head = self.built(1)[0]
        self.head(1)
        self.put_gh("delete-error.txt", "failed to delete remote branch builder/1-x: HTTP 403")
        result = self.train("land", "1", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("landed pr=1 head=%s" % head, result.stdout)
        self.assertIn("branch pr=1 delete failed (failed to delete remote branch builder/1-x: HTTP 403)", result.stdout)
        self.assertIn("- Head branch: delete failed (failed to delete remote branch builder/1-x: HTTP 403).",
                      self.merge_record())

    def put_gh(self, name, text):
        with open(os.path.join(self.gh_dir, name), "w") as f:
            f.write(text)

    def test_unreadable_landing_control_refuses_land(self):
        self.built(1)
        Precheck.complete_view(self, 1)
        for text in ('not json', '{"issue": 0}', '{"issue": 999}'):
            with self.subTest(control=text):
                self.put("landing-control.json", text)
                result = self.train("check", "1")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("landing control unreadable", result.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_new_hold_after_release_blocks_again(self):
        self.built(1)
        self.issue(77, "OPEN")
        path = os.path.join(self.gh_dir, "pr-1.json")
        with open(path) as f:
            view = json.load(f)
        view["reviews"].append({"body": "<!-- crew:v1 role=coordinator pass=steer cmd=hold-release --> hold-until-#77",
                                "submittedAt": "2026-11-01T01:00:00Z"})
        view["comments"].append({"body": "[Ash/hold] hold-until-#77", "createdAt": "2026-11-01T02:00:00Z"})
        with open(path, "w") as f:
            json.dump(view, f)
        result = self.train("land", "1", "1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("open coordinator hold-until-#77", result.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_recorded_hold_release_clears_named_dependency(self):
        self.built(1)
        head, reviews = self.view(1)
        reviews += [{"body": "<!-- crew:v1 role=coordinator pass=steer cmd=hold --> hold-until-#77"},
                    {"body": "<!-- crew:v1 role=coordinator pass=steer cmd=hold-release --> hold-until-#77 released by owner"}]
        self.serve(1, head, reviews)
        result = self.train("land", "1", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.gh_calls("issue", "view"), [])

    def test_other_roles_quoting_holds_never_lookup_dependencies(self):
        for n, (name, role, kind) in enumerate([
                ("Vera", "reviewer-validator", "verdict"),
                ("Ben", "builder", "fix"), ("Sam", "synthesizer", "merge")], 1):
            with self.subTest(role=role):
                head = self.built(n)[0]
                _, reviews = self.view(n)
                quote = ("[%s/%s] quotes `hold-until-#77` and `hold-until-#503`\n"
                         "<!-- crew:v1 role=%s pass=%s -->" % (name, kind, role, kind))
                reviews.append({"body": quote})
                self.serve(n, head, reviews, comments=[quote, "Example: [Ash/hold] hold-until-#503"])
                self.issue(77, "OPEN")
                result = self.train("land", str(n), str(n))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.gh_calls("issue", "view"), [])
        self.assertEqual(len(self.gh_calls("pr", "merge")), 3)

    def test_coordinator_holds_block_only_open_or_unresolved_dependencies(self):
        marker = "<!-- crew:v1 role=coordinator pass=steer --> hold-until-#77"
        cases = [("[Ash/hold] hold-until-#77", "OPEN", "open coordinator hold-until-#77"),
                 (marker, "OPEN", "open coordinator hold-until-#77"),
                 ("[Ash/hold] hold-until-#77", "CLOSED", None),
                 (marker, "MERGED", None),
                 (marker, None, "unresolved coordinator hold-until-#77: dependency missing or lookup failed")]
        for n, (body, state, reason) in enumerate(cases, 1):
            with self.subTest(state=state, body=body):
                head = self.built(n)[0]
                _, reviews = self.view(n)
                reviews.append({"body": body})
                self.serve(n, head, reviews)
                if state:
                    self.issue(77, state)
                else:
                    os.remove(os.path.join(self.gh_dir, "issue-77.json"))
                result = self.train("land", str(n), str(n))
                self.assertEqual(result.returncode, 1 if reason else 0, result.stdout + result.stderr)
                if reason:
                    self.assertIn("stopped pr=%d reason=%s" % (n, reason), result.stdout)
                    self.assertIn("pr-closed=yes branch-deleted=yes", result.stdout)
                self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual([c["args"][2] for c in self.gh_calls("pr", "merge")], ["3", "4"])

    def test_land_in_order_with_records_then_close_and_delete(self):
        heads = self.built(1, 2, 3)
        rec = self.record()
        # #1: a rereview at head answered by a fresh verdict, and a hold-until on an item that has landed: not blocking
        self.serve(1, heads[0], [{"body": VERDICT % (1, heads[0])}, {"body": REREVIEW % (1, heads[0])},
                                 {"body": VERDICT % (1, heads[0])}], comments=["[Ash/hold] hold-until-#77"])
        self.issue(77, "CLOSED")
        wrong = self.train("land", "1", "2")
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("train 1 lands #1 next, not #2; nothing landed", wrong.stdout)
        runs = self.land_all(1, (1, 2, 3))
        self.assertEqual([r.returncode for r in runs], [0, 0, 0], [r.stdout + r.stderr for r in runs])
        self.assertIn("train n=1 landed=1/3 next=2", runs[0].stdout)
        self.assertIn("train n=1 landed=2/3 next=3", runs[1].stdout)
        self.assertIn("landed pr=3 head=%s" % heads[2], runs[2].stdout)
        self.assertIn("train n=1 landed=3/3 pr-closed=yes branch-deleted=yes", runs[2].stdout)
        merges = [c["args"] for c in self.gh_calls("pr", "merge")]
        self.assertEqual(merges, [["pr", "merge", str(n), "-R", "acme/widgets", "--squash", "--match-head-commit", h]
                                  for n, h in zip((1, 2, 3), heads)])
        self.assertTrue(self.gh_calls("pr", "view")[-1]["args"][-1].endswith(",comments,mergeable,closingIssuesReferences,url"))
        main = self.remote("refs/heads/main")
        self.assertEqual(self.git("rev-parse", main + "^{tree}"), self.git("rev-parse", rec["sha"] + "^{tree}"))
        posts = [c["args"] for c in self.gh_calls("pr", "review")]
        self.assertEqual([p[2] for p in posts], ["1", "2", "3"])
        for (n, head), post in zip(zip((1, 2, 3), heads), posts):
            body = post[post.index("--body") + 1]
            self.assertTrue(body.startswith("[Sam/merge] squashed @ %s" % head[:7]), body)
            for text in ["Land rule: train of 3 (ready together).", "`crew/train-1` @ " + rec["sha"], LINK, "train PR #900", 'Permission: merge_grant = "test grant"',
                         "Mirror deferral used: none",
                         "<!-- crew:v1 role=synthesizer pass=merge pr=%d sha=%s round=n/a verdict=n/a content=identical carried-from=%s -->" % (n, head, head)]:
                self.assertIn(text, body)
        self.assertEqual([c["args"] for c in self.gh_calls("pr", "close")], [["pr", "close", "900", "-R", "acme/widgets"]])
        self.assertEqual(self.remote("refs/heads/crew/train-1"), "")
        self.assertIn("train 1 is closed; nothing landed", self.train("land", "1", "3").stdout)
        with open(self.git_log) as f:  # #1367, #1584: fetches between lands isolate their results
            fetches = [line.split() for line in f if line.split()[2:3] == ["fetch"]]
        self.assertTrue(fetches)
        for args in fetches:
            self.assertIn("--no-write-fetch-head", args)
            self.assertIn("--refmap=", args)
            self.assertTrue(args[-1].split(":")[-1].startswith("refs/crew/fetch/"), args)
        self.assertEqual(self.git("for-each-ref", "refs/crew/fetch/"), "")

    def test_merge_record_names_only_used_profile_deferral(self):
        self.built(1)
        refused = self.train("land", "1", "1", "--mirror-deferred")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"',
                                    'merge_grant = "test grant", mirror_deferral = "#110 roadmap PRs per #140"')
        with open(self.project, "w") as f:
            f.write(text)
        r = self.train("land", "1", "1", "--mirror-deferred")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        post = self.gh_calls("pr", "review")[0]["args"]
        self.assertIn("Mirror deferral used: #110 roadmap PRs per #140", post[post.index("--body") + 1])

    def test_merge_record_says_mirror_na_under_profile_none(self):
        self.built(1)
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"', 'merge_grant = "test grant", mirror = "none"')
        with open(self.project, "w") as f:
            f.write(text)
        refused = self.train("land", "1", "1", "--mirror-deferred")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = self.gh_calls("pr", "review")[0]["args"]
        body = body[body.index("--body") + 1]
        self.assertIn("- Mirror: n/a (profile).\n", body)
        self.assertNotIn("Mirror deferral used", body)

    def test_land_stops_on_head_change(self):
        heads = self.built(1, 2, 3)
        self.serve(2, "f" * 40, [])  # #2 got a new commit after the train was built
        runs = self.land_all(1, (1, 2, 3))
        self.assertEqual([r.returncode for r in runs], [0, 1, 1])
        self.assertEqual([c["args"][2] for c in self.gh_calls("pr", "merge")], ["1"])
        self.assertIn("landed pr=1 head=%s" % heads[0], runs[0].stdout)
        self.assertIn("stopped pr=2 reason=head changed: %s, tested %s" % ("f" * 40, heads[1]), runs[1].stdout)
        self.assertIn("train n=1 landed=1/3 pr-closed=yes branch-deleted=yes", runs[1].stdout)
        self.assertIn("train 1 is closed; nothing landed", runs[2].stdout)
        self.assertEqual(self.record()["stopped"]["pr"], 2)

    def test_changed_head_containing_http_code_closes_and_routes_deferred_member(self):
        self.pr(1, {"x.txt": "first"})
        self.pr(2, {"x.txt": "second"})
        self.assertEqual(self.train("build", "1", "2").returncode, 0)
        self.legacy_overlap()
        self.serve(1, "502" + "f" * 37, [])
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("stopped pr=1 reason=head changed", r.stdout)
        self.assertNotIn("paused pr=1", r.stdout)
        self.assertTrue(self.record()["closed"])
        self.assertFalse(self.record()["stopped"]["paused"])
        self.assertEqual(self.remote("refs/heads/crew/train-1"), "")
        self.assertEqual(self.record()["dropped"][0]["merge_up"], "updated")
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_http_status_substrings_do_not_make_real_stops_transient(self):
        import runpy
        from crew_testlib import CREW
        transient = runpy.run_path(CREW)["train_transient"]
        for code in ("429", "500", "502", "503", "504"):
            with self.subTest(code=code):
                self.assertFalse(transient("head changed: " + code + "f" * 37))
                self.assertFalse(transient("main moved: " + code + "f" * 37))
                self.assertFalse(transient("open coordinator hold-until-#" + code))
                self.assertFalse(transient("merge refused: head " + code + "f" * 37 + " was modified"))
                self.assertTrue(transient("HTTP " + code + " server error"))

    def test_land_stops_when_main_moved_or_no_approval(self):
        self.built(1)
        self.commit({"z.txt": "z\n"}, "someone else landed")
        self.git("push", "-q", "origin", "main")
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped pr=1 reason=main moved", r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        head = self.pr(2, {"b.txt": "two\n"})
        self.assertEqual(self.train("build", "2").returncode, 0)
        self.serve(2, head, [])
        r = self.train("land", "2", "2")
        self.assertIn("stopped pr=2 reason=no approval verdict at head", r.stdout)
        self.write_profile()  # merge_grant = "none" and no merge-ok at head
        self.pr(3, {"c.txt": "three\n"})
        self.assertEqual(self.train("build", "3").returncode, 0)
        r = self.train("land", "3", "3")
        self.assertIn("stopped pr=3 reason=no merge permission", r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_land_stops_on_a_gate_added_while_ci_ran(self):
        self.issue(429, "OPEN")
        cases = [("escalated", {"labels": ["crew:escalated"]}, "state tag crew:escalated"),
                 ("changes", {"labels": ["crew:changes"]}, "state tag crew:changes"),
                 ("hold label", {"labels": ["crew:hold"]}, "state tag crew:hold"),  # hold_label_blocks defaults true
                 ("sensitive", {"labels": ["crew:sensitive"]}, "crew:sensitive needs owner merge-ok at head"),
                 ("rereview", {"rereview": True}, "open rereview at head"),
                 ("hold-until", {"comments": ["[Ash/hold] hold-until-#429"]}, "open coordinator hold-until-#429"),
                 ("stop-landing", {"reviews_extra": [{"body": "<!-- crew:v1 role=coordinator pass=steer cmd=stop-landing cmd-id=stop -->"},
                                                        {"body": "<!-- crew:v1 role=coordinator pass=steer cmd=urgent -->"}]}, "open stop-landing: stop"),
                 ("conflicting", {"mergeable": "CONFLICTING"}, "not mergeable: GitHub reports CONFLICTING")]
        for n, (name, change, reason) in enumerate(cases, 1):
            with self.subTest(gate=name):
                pr = 10 + n
                self.built(pr)
                head, reviews = self.view(pr)
                if change.pop("rereview", False):
                    reviews.append({"body": REREVIEW % (pr, head)})
                reviews.extend(change.pop("reviews_extra", []))
                if name == "stop-landing":
                    reviews.append({"body": "<!-- crew:v1 role=coordinator pass=steer cmd=merge-ok sha=%s -->" % head})
                self.serve(pr, head, reviews, **change)
                r = self.train("land", str(n), str(pr))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("stopped pr=%d reason=%s" % (pr, reason), r.stdout)
                self.assertIn("train n=%d landed=0/1 pr-closed=yes branch-deleted=yes" % n, r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_changes_then_pass_lands_once_route_reconciled_the_tags(self):  # #1464
        changes = "<!-- crew:v1 role=reviewer-validator pass=verdict pr=%d sha=%s round=%d verdict=changes -->"
        cases = [("stale tag", ["crew:approved", "crew:changes"], False, "stopped pr=1 reason=state tag crew:changes"),
                 ("later changes", ["crew:approved"], True, "stopped pr=2 reason=no approval verdict at head"),
                 ("reconciled", ["crew:approved"], False, "train n=3 landed=1/1")]
        for n, (name, labels, later, expect) in enumerate(cases, 1):
            with self.subTest(case=name):
                self.built(n)
                head, reviews = self.view(n)
                reviews.insert(0, {"body": changes % (n, "0" * 40, 1)})
                if later:
                    reviews.append({"body": changes % (n, head, 2)})
                self.serve(n, head, reviews, labels=labels)
                r = self.train("land", str(n), str(n))
                self.assertEqual(r.returncode, int(name != "reconciled"), r.stdout + r.stderr)
                self.assertIn(expect, r.stdout)
        self.assertEqual(len(self.gh_calls("pr", "merge")), 1)

    def test_transient_pause_resumes_same_green_train(self):
        self.built(1, 2)
        self.assertEqual(self.train("land", "1", "1").returncode, 0)
        head, reviews = self.view(2)
        self.serve(2, head, reviews, mergeable="UNKNOWN")
        r = self.train("land", "1", "2")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("paused pr=2 reason=GitHub mergeability UNKNOWN", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "schedule", "errors.jsonl")))  # not a gateway error
        self.assertTrue(self.record()["stopped"]["paused"])
        self.assertFalse(self.record().get("closed", False))
        self.assertEqual(sum(c["args"][-1].endswith(",comments,mergeable,closingIssuesReferences,url")
                             for c in self.gh_calls("pr", "view", "2")), 10)
        self.assertEqual(self.gh_calls("pr", "close"), [])
        self.serve(2, head, reviews)
        self.assertEqual(self.train("land", "1", "2").returncode, 0)
        self.assertEqual(len(self.gh_calls("pr", "create")), 1)
        self.assertEqual(len(self.record()["landed"]), 2)
        self.assertNotIn("stopped", self.record())

    def test_transient_api_errors_and_unknown_settle_before_land(self):
        self.built(1)
        with open(os.path.join(self.gh_dir, "pr-1.json")) as f:
            ready = json.load(f)
        with open(os.path.join(self.gh_dir, "views-1.json"), "w") as f:
            json.dump(["HTTP 502 Bad Gateway", dict(ready, mergeable="UNKNOWN"), ready], f)
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sum(c["args"][-1].endswith(",comments,mergeable,closingIssuesReferences,url")
                             for c in self.gh_calls("pr", "view", "1")), 3)
        with open(os.path.join(self.state, "schedule", "errors.jsonl")) as f:  # #621: recovered read still recorded
            self.assertEqual([(e["source"], e["text"]) for e in map(json.loads, f)],
                             [("train-1", "crew: gh pr view failed: HTTP 502 Bad Gateway")])

    def test_api_timeout_pause_still_checks_main_on_resume(self):
        self.built(1)
        with open(os.path.join(self.gh_dir, "views-1.json"), "w") as f:
            json.dump(["HTTP 503 Service Unavailable"], f)
        self.assertEqual(self.train("land", "1", "1").returncode, 1)
        self.assertFalse(self.record().get("closed", False))
        self.assertEqual(self.train("land", "1", "1").returncode, 1)  # #621: each failed read is one error
        with open(os.path.join(self.state, "schedule", "errors.jsonl")) as f:
            self.assertEqual([(e["source"], e["text"]) for e in map(json.loads, f)],
                             [("train-1", "crew: gh pr view failed: HTTP 503 Service Unavailable")] * 20)
        self.commit({"moved.txt": "x"}, "main moved")
        self.git("push", "-q", "origin", "main")
        r = self.train("land", "1", "1")
        self.assertIn("stopped pr=1 reason=main moved", r.stdout)
        self.assertTrue(self.record()["closed"])
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_train_ci_rerun_pending_pauses_and_red_closes(self):
        self.built(1)
        self.checks(PENDING)
        r = self.train("land", "1", "1")
        self.assertIn("paused pr=1 reason=train CI UNKNOWN or pending", r.stdout)
        self.assertFalse(self.record().get("closed", False))
        self.checks(FAIL)
        r = self.train("land", "1", "1")
        self.assertIn("stopped pr=1 reason=train CI red", r.stdout)
        self.assertTrue(self.record()["closed"])
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_transient_merge_record_failure_retries_without_another_squash(self):
        self.built(1)
        path = os.path.join(self.gh_dir, "review-error.txt")
        with open(path, "w") as f:
            f.write("HTTP 503 Service Unavailable")
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("paused pr=1 reason=merge record pending", r.stdout)
        self.assertFalse(self.record().get("closed", False))
        self.assertEqual(len(self.record()["landed"]), 1)
        os.remove(path)
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.record()["closed"])
        self.assertEqual(len(self.gh_calls("pr", "merge")), 1)
        self.assertNotIn("pending_record", self.record())

    def test_sensitive_land_requires_merge_ok_at_current_head(self):
        for n, sha in [(1, "0" * 40), (2, None)]:
            self.built(n)
            head, reviews = self.view(n)
            reviews.append({"body": "<!-- crew:v1 role=coordinator pass=steer cmd=merge-ok sha=%s -->" % (sha or head)})
            self.serve(n, head, reviews, labels=["crew:sensitive"])
            result = self.train("land", str(n), str(n))
            self.assertEqual(result.returncode, 1 if sha else 0, result.stdout + result.stderr)
            if sha:
                self.assertIn("crew:sensitive needs owner merge-ok at head", result.stdout)
                self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_close_ends_a_train_early(self):
        self.built(1, 2)
        r = self.train("close", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("train n=1 landed=0/2 pr-closed=yes branch-deleted=yes", r.stdout)
        self.assertEqual(self.remote("refs/heads/crew/train-1"), "")
        self.assertIn("train 1 is closed; nothing landed", self.train("land", "1", "1").stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])


REWORK = "<!-- crew:v1 role=coordinator pass=steer cmd=rework pr=%d sha=%s -->"


class LaterChangesRequest(TrainBase):
    """#1118 (protocol §7): a rework steer or a reviewer-identity CHANGES_REQUESTED review after the passing verdict
    at head blocks `train check` and `train land`; a fresh verdict at head after it answers it."""

    def later(self, pr, head, kind):
        return {"rework": {"body": REWORK % (pr, head), "state": "COMMENTED", "author": {"login": "acme-coord"}},
                "formal": {"body": "Please fix the parser before this lands.", "state": "CHANGES_REQUESTED",
                           "author": {"login": "acme-reviewer"}}}[kind]

    def test_check_blocks_a_later_changes_request_until_a_verdict_answers_it(self):
        cases = [("rework", "later changes request at head: rework steer"),
                 ("formal", "later changes request at head: reviewer CHANGES_REQUESTED review")]
        for n, (kind, reason) in enumerate(cases, 1):
            with self.subTest(kind=kind):
                self.pr(n, {"f%d.txt" % n: "x"})
                path, view = Precheck.complete_view(self, n)
                head, verdict = view["headRefOid"], view["reviews"][0]
                self.assertEqual(self.train("check", str(n)).returncode, 0)
                view["reviews"].append(self.later(n, head, kind))
                with open(path, "w") as f:
                    json.dump(view, f)
                result = self.train("check", str(n))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("name=state-permission status=blocked reason=%s" % json.dumps(reason), result.stdout)
                view["reviews"].append(verdict)  # a fresh passing verdict at head answers the request
                with open(path, "w") as f:
                    json.dump(view, f)
                result = self.train("check", str(n))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_other_authors_and_older_requests_do_not_block(self):
        self.pr(1, {"one.txt": "one"})
        path, view = Precheck.complete_view(self, 1)
        head = view["headRefOid"]
        older = dict(self.later(1, head, "formal"), body="round 1 findings")
        other = dict(self.later(1, head, "formal"), author={"login": "someone-else"})
        stale = self.later(1, "0" * 40, "rework")
        view["reviews"] = [older] + view["reviews"] + [other, stale]
        with open(path, "w") as f:
            json.dump(view, f)
        result = self.train("check", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_land_squashes_nothing_on_a_later_changes_request(self):
        """The #1118 repro: both later requests after the verdict; land stops and main does not move."""
        self.built(1)
        main = self.remote("refs/heads/main")
        head, reviews = self.view(1)
        self.serve(1, head, reviews + [self.later(1, head, "rework"), self.later(1, head, "formal")])
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("stopped pr=1 reason=later changes request at head: rework steer", r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        self.assertEqual(self.remote("refs/heads/main"), main)
        self.serve(1, head, reviews + [self.later(1, head, "formal")])
        self.assertEqual(self.train("build", "1").returncode, 0)
        r = self.train("land", "2", "1")
        self.assertIn("stopped pr=1 reason=later changes request at head: reviewer CHANGES_REQUESTED review", r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        self.assertEqual(self.remote("refs/heads/main"), main)


class Spec(TrainBase):
    """#928: a spec change (crew:spec, or a spec.paths match on either rename path) lands on the standing grant only
    when merge_grant_scope lists spec; otherwise, sensitive, rereview or unreadable, it needs merge-ok at head."""

    def scope(self, extra=""):
        with open(self.project) as f:
            text = f.read().replace('merge_grant = "test grant"',
                                    'merge_grant = "test grant", merge_grant_scope = ["approved", "spec"]') + extra
        with open(self.project, "w") as f:
            f.write(text)

    def land(self, n, files=None, labels=(), reviews_extra=(), raw=None):
        self.built(n)
        head, reviews = self.view(n)
        self.serve(n, head, reviews + [{"body": b % (n, head)} for b in reviews_extra], labels=labels)
        with open(os.path.join(self.gh_dir, "files-%d.json" % n), "w") as f:
            f.write(raw if raw is not None else json.dumps(files or [{"filename": "f%d.txt" % n}]))
        train = len(os.listdir(os.path.join(self.state, "trains")))  # trains are numbered in build order
        return self.train("land", str(train), str(n))

    def record_body(self):
        post = self.gh_calls("pr", "review")[-1]["args"]
        return post[post.index("--body") + 1]

    def test_spec_without_scope_needs_merge_ok(self):
        cases = [("label only", {"labels": ["crew:spec"]}),
                 ("path only", {"files": [{"filename": "docs/specs/a.md"}]}),
                 ("rename away", {"files": [{"filename": "docs/a.md", "previous_filename": "docs/specs/a.md"}]})]
        for n, (name, change) in enumerate(cases, 1):
            with self.subTest(case=name):
                r = self.land(n, **change)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("stopped pr=%d reason=spec change needs owner merge-ok at head: merge_grant_scope does "
                              "not cover spec" % n, r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        r = self.land(9, labels=["crew:spec"],
                      reviews_extra=["<!-- crew:v1 role=coordinator pass=steer pr=%d cmd=merge-ok sha=%s -->"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Permission: owner merge-ok at head.", self.record_body())

    def test_scope_covers_ordinary_spec_and_names_grant_in_record(self):
        self.scope()
        r = self.land(1, files=[{"filename": "docs/specs/a.md"}])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Permission: merge_grant = "test grant" with merge_grant_scope = ["approved", "spec"]: '
                      'covered a spec change.', self.record_body())
        r = self.land(2)  # a non-spec change keeps today's record
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Permission: merge_grant = "test grant".', self.record_body())

    def test_scope_never_covers_sensitive_rereview_or_unreadable(self):
        self.scope()
        cases = [("sensitive spec", {"labels": ["crew:sensitive", "crew:spec"]}, "crew:sensitive needs owner merge-ok"),
                 ("open rereview", {"labels": ["crew:spec"], "reviews_extra": [REREVIEW]}, "open rereview at head"),
                 ("unreadable paths", {"raw": "not json"}, "spec classification unreadable")]
        for n, (name, change, reason) in enumerate(cases, 1):
            with self.subTest(case=name):
                r = self.land(n, **change)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("stopped pr=%d reason=%s" % (n, reason), r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_configured_spec_paths_replace_default(self):
        self.scope('\n[spec]\npaths = ["rfcs/**"]\n')
        with open(self.project) as f:
            text = f.read().replace(', merge_grant_scope = ["approved", "spec"]', "")
        with open(self.project, "w") as f:
            f.write(text)
        self.assertEqual(self.land(1, files=[{"filename": "docs/specs/a.md"}]).returncode, 0)
        r = self.land(2, files=[{"filename": "rfcs/a.md"}])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("spec change needs owner merge-ok at head", r.stdout)

    def test_check_reports_spec_permission(self):
        self.scope()
        self.pr(1, {"one.txt": "one"})
        path = os.path.join(self.gh_dir, "pr-1.json")
        Precheck.complete_view(self, 1)
        with open(path) as f:
            view = json.load(f)
        view["labels"] = [{"name": "crew:spec"}]
        with open(path, "w") as f:
            json.dump(view, f)
        r = self.train("check", "1")
        self.assertIn('name=state-permission status=pass', r.stdout)
        self.assertIn('name=grant-scope status=manual reason="verify the recorded owner decision merge_grant names '
                      'authorizes spec coverage"', r.stdout)


SELFGATE = ("[Ben/selfgate] pass\n<!-- crew:v1 role=builder pass=selfgate pr=%d sha=%s base=%s round=n/a verdict=pass "
            "mode=different builder-engine=claude-code/opus reviewer-engine=codex/gpt-5 reviews=1 findings=0 open=0 "
            "checks=pass -->\n— 🛠️ Ben (Builder) · Claude Code · opus")
ITEM = "[Ash/flavor] #%d: %s\nReason: small and well specified\n<!-- crew:v1 role=coordinator pass=flavor issue=%d flavor=%s default=standard -->"


class SelfgateKeys(unittest.TestCase):
    """#876: train's selfgate consumer passes the live view's number and one linked issue as the independent keys."""

    def test_item_and_change_keys_from_the_view(self):
        from importlib.machinery import SourceFileLoader
        import importlib.util
        loader = SourceFileLoader("crew_cli_train", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "cli", "mdstack"))
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli_train", loader))
        loader.exec_module(mod)
        train, head = mod.commands()["train"], "a" * 40
        values = {"identities.builder.gh_user": "acme-bot", "identities.builder.name": "Ben"}
        item_mode = dict(values, **{"ids.item": "[A-Z]+-[0-9]+", "ids.change": "D[0-9]+", "ids.marker_key": "item"})
        view = {"number": 7, "reviews": [{"body": SELFGATE % (7, head, "b" * 40), "author": {"login": "acme-bot"}}],
                "closingIssuesReferences": [{"number": 71}]}
        item_view = dict(view, reviews=[dict(view["reviews"][0], body=view["reviews"][0]["body"].replace(
            "pr=7 ", "issue=OPS-1042 "))])
        cases = [(values, view, "pass"), (values, dict(view, number=8), "marker for 7, expected 8"),
                 (item_mode, dict(item_view, closingIssuesReferences=[{"number": "OPS-1042"}]), "pass"),
                 (item_mode, dict(item_view, closingIssuesReferences=[{"number": "OPS-7"}]),
                  "marker for OPS-1042, expected OPS-7"),
                 (item_mode, dict(item_view, closingIssuesReferences=[]), "missing item key")]
        for vals, v, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(train.train_selfgate(vals, v, head), expected)

    def test_train_view_reads_the_linked_item(self):
        """Build and land read the selfgate's view through train_view: it must request the linked issue field."""
        from importlib.machinery import SourceFileLoader
        import importlib.util
        from types import SimpleNamespace
        loader = SourceFileLoader("crew_cli_train", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "cli", "mdstack"))
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli_train", loader))
        loader.exec_module(mod)
        train, poll, head = mod.commands()["train"], mod.commands()["poll"], "a" * 40
        body = (SELFGATE % (7, head, "b" * 40)).replace("pr=7 ", "issue=OPS-1042 ")
        record = dict(number=7, state="OPEN", headRefOid=head, labels=[], statusCheckRollup=[], commits=[], comments=[],
                      reviews=[{"body": body, "author": {"login": "acme-bot"}}], mergeable="MERGEABLE",
                      closingIssuesReferences=[{"number": "OPS-1042"}])
        values = {"identities.builder.gh_user": "acme-bot", "identities.builder.name": "Ben",
                  "ids.item": "[A-Z]+-[0-9]+", "ids.change": "D[0-9]+", "ids.marker_key": "item"}
        saved = poll.gh_json
        poll.gh_json = lambda *a: {k: record[k] for k in a[a.index("--json") + 1].split(",") if k in record}
        try:
            view = train.train_view(poll, "acme/repo", 7, SimpleNamespace(interval=0), ".crew", 1)
        finally:
            poll.gh_json = saved
        self.assertEqual(train.train_selfgate(values, view, head), "pass")


class Express(TrainBase):
    """#673: a member resolved express (item record + paths) passes on its selfgate record, never a verdict; a
    crew:express label on a crew-lane or unreadable change never does."""

    def express_pr(self, n, files, sha=None, labels=(), item="express", verdict=False):
        head = self.pr(n, files, approved=verdict)
        reviews = self.view(n)[1] + [{"body": SELFGATE % (n, sha or head, self.git("rev-parse", "origin/main")),
                                      "author": {"login": "acme-bot"}}]
        self.serve(n, head, reviews, labels=("crew:express",) + labels)
        self.item(n, item)
        with open(os.path.join(self.gh_dir, "files-%d.json" % n), "w") as f:
            json.dump([{"filename": name} for name in files], f)
        path = os.path.join(self.gh_dir, "pr-%d.json" % n)
        with open(path) as f:
            view = json.load(f)
        view.update(body="", files=[{"path": name} for name in files], isDraft=False, baseRefName="main",
                    commits=[], closingIssuesReferences=[{"number": 70 + n}])
        with open(path, "w") as f:
            json.dump(view, f)
        return head

    def item(self, n, *flavors):
        with open(os.path.join(self.gh_dir, "issue-%d.json" % (70 + n)), "w") as f:
            json.dump({"state": "OPEN", "labels": [], "comments": [
                {"body": ITEM % (70 + n, x, 70 + n, x), "author": {"login": "acme-bot"}} for x in flavors if x]}, f)

    def test_mixed_train_lands_verdict_and_selfgate_members(self):
        crew = self.pr(1, {"one.txt": "one\n"})
        fast = self.express_pr(2, {"two.txt": "two\n"})
        r = self.train("build", "1", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m["approval"] for m in self.record()["members"]], ["verdict", "selfgate"])
        runs = self.land_all(1, (1, 2))
        self.assertEqual([r.returncode for r in runs], [0, 0], [r.stdout for r in runs])
        self.assertEqual([c["args"][-1] for c in self.gh_calls("pr", "merge")], [crew, fast])
        bodies = [c["args"][c["args"].index("--body") + 1] for c in self.gh_calls("pr", "review")]
        self.assertIn("`pass=verdict verdict=pass` at " + crew, bodies[0])
        self.assertIn("`pass=selfgate verdict=pass` at " + fast, bodies[1])

    def test_stale_selfgate_or_lane_change_stops_land(self):
        head = self.express_pr(1, {"one.txt": "one\n"})
        self.assertEqual(self.train("build", "1").returncode, 0)
        reviews = [{"body": SELFGATE % (1, "e" * 40, "e" * 40), "author": {"login": "acme-bot"}},
                   {"body": "[Vera/verdict]\n" + VERDICT % (1, head)}]
        self.serve(1, head, reviews, labels=("crew:express",))
        with open(os.path.join(self.gh_dir, "pr-1.json")) as f:
            view = json.load(f)
        view["closingIssuesReferences"] = [{"number": 71}]  # serve() reset the linked issue
        with open(os.path.join(self.gh_dir, "pr-1.json"), "w") as f:
            json.dump(view, f)
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped pr=1 reason=no express selfgate pass at head: stale marker", r.stdout)
        head = self.express_pr(2, {"two.txt": "two\n"})
        self.assertEqual(self.train("build", "2").returncode, 0)
        self.item(2, "express", "standard")  # a newer item record takes the change out of express
        r = self.train("land", "2", "2")
        self.assertIn("stopped pr=2 reason=no approval verdict at head", r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_crew_lane_or_unreadable_express_never_builds_on_selfgate(self):
        with open(self.project, "a") as f:
            f.write('\n[flavor]\nname = "standard"\n[[flavor.classes]]\npaths = ["src/private/**"]\nflavor = "thorough"\n')
        self.express_pr(1, {"src/private/a.txt": "x\n"})  # tightening class
        self.express_pr(2, {"two.txt": "x\n"}, item=None)  # no item record
        self.express_pr(3, {"three.txt": "x\n"}, item="standard")
        self.express_pr(4, {"four.txt": "x\n"})
        os.remove(os.path.join(self.gh_dir, "issue-74.json"))  # unreadable
        r = self.train("check", "1", "2", "3", "4")
        self.assertEqual(r.returncode, 1)
        for n, why in ((1, "crew lane (tightening class rule)"), (2, "crew lane (item flavor thorough (flavor-missing))"),
                       (3, "crew lane (item flavor standard (recorded))"), (4, "express resolution unreadable")):
            self.assertRegex(r.stdout, r"pr=%d sha=\w+ name=verdict status=blocked" % n)
            self.assertIn("name=express status=blocked reason=\"%s" % why, r.stdout)
        r = self.train("build", "1", "2", "3", "4")
        for n in (1, 2, 3):
            self.assertIn("dropped pr=%d reason=no-verified-base" % n, r.stdout)
        self.assertIn("dropped pr=4 reason=express-unreadable", r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_spec_path_without_label_needs_owner_override(self):
        """#928: a spec.paths match on either rename path is a spec change for express eligibility, like crew:spec."""
        self.express_pr(1, {"docs/specs/a.md": "x\n"})  # path only
        self.express_pr(2, {"docs/a.md": "x\n"})
        with open(os.path.join(self.gh_dir, "files-2.json"), "w") as f:  # rename away from the spec tree
            json.dump([{"filename": "docs/a.md", "previous_filename": "docs/specs/a.md"}], f)
        self.express_pr(3, {"three.txt": "x\n"}, labels=("crew:spec",))  # labelled control
        self.express_pr(4, {"docs/specs/b.md": "x\n"})
        with open(os.path.join(self.gh_dir, "issue-74.json"), "w") as f:
            json.dump({"state": "OPEN", "labels": [], "comments": [{"body": ITEM % (74, "express", 74, "express") +
                       "\nOwner override: \"express it\"", "author": {"login": "acme-bot"}}]}, f)
        r = self.train("check", "1", "2", "3", "4")
        for n in (1, 2, 3):
            self.assertRegex(r.stdout, r'pr=%d sha=\w+ name=express status=blocked reason="crew lane \(item flavor '
                             r'standard \(express-ineligible\)\)' % n)
        self.assertRegex(r.stdout, r'pr=4 sha=\w+ name=verdict status=pass reason="express selfgate pass at')
        self.assertRegex(r.stdout, r'pr=4 sha=\w+ name=express status=blocked reason="spec change needs owner '
                         r'merge-ok at head"')
        r = self.train("build", "1", "2", "3")
        for n in (1, 2, 3):
            self.assertIn("dropped pr=%d reason=no-verified-base" % n, r.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_check_reports_express_gate(self):
        head = self.express_pr(1, {"f1.txt": "x\n"})
        self.express_pr(2, {"f2.txt": "x\n"}, labels=("crew:spec",))
        self.item(2, "")  # crew:spec without an owner override is express-ineligible
        with open(os.path.join(self.gh_dir, "issue-72.json"), "w") as f:
            json.dump({"state": "OPEN", "labels": [], "comments": [{"body": ITEM % (72, "express", 72, "express") +
                       "\nOwner override: \"express it\"", "author": {"login": "acme-bot"}}]}, f)
        r = self.train("check", "1", "2")
        self.assertIn('pr=1 sha=%s name=verdict status=pass reason="express selfgate pass at' % head, r.stdout)
        self.assertIn('pr=1 sha=%s name=express status=pass reason="resolved express"' % head, r.stdout)
        self.assertIn('name=express status=blocked reason="spec change needs owner merge-ok at head"', r.stdout)


class ReleaseCut(TrainBase):
    """#1433, the 7.2.0 sequence (#1424, main-red #1432): a cut approved on an old base, a fragment PR landing after
    it, then the cut landing on a stale merge ref."""
    CUT_PATCH = "@@ -1,4 +1,6 @@\n ## [Unreleased]\n \n+## [7.2.0] - 2026-11-08\n+\n ### Added\n"

    def files(self, n, files):
        with open(os.path.join(self.gh_dir, "files-%d.json" % n), "w") as f:
            json.dump(files, f)

    def open_prs(self, *prs):
        with open(os.path.join(self.gh_dir, "open.json"), "w") as f:
            json.dump([{"number": n, "files": [{"path": p} for p in paths]} for n, paths in prs], f)

    def setUp(self):
        super().setUp()
        self.commit({"CHANGELOG.md": "## [Unreleased]\n\n### Added\n", "changes/unreleased/1-a.md": "a\n"}, "fragment")
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", "-B", "pr1", "origin/main")  # the cut consumes 1-a.md into [7.2.0]
        self.git("rm", "-q", "changes/unreleased/1-a.md")
        self.commit({"CHANGELOG.md": "## [Unreleased]\n\n## [7.2.0] - 2026-11-08\n\n### Added\n\n- a\n"}, "cut 7.2.0")
        self.git("push", "-q", "origin", "HEAD:refs/pull/1/head")
        self.cut = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.serve(1, self.cut, [])
        self.complete_view(1)
        self.files(1, [{"filename": "CHANGELOG.md", "status": "modified", "patch": self.CUT_PATCH},
                       {"filename": "changes/unreleased/1-a.md", "status": "removed"}])
        self.pr(2, {"changes/unreleased/2-b.md": "b\n", "b.txt": "b\n"})
        self.complete_view(2)
        self.files(2, [{"filename": "changes/unreleased/2-b.md", "status": "added"}, {"filename": "b.txt", "status": "added"}])
        self.open_prs((1, ["CHANGELOG.md", "changes/unreleased/1-a.md"]), (2, ["changes/unreleased/2-b.md", "b.txt"]))

    def gate(self, r, pr, name):
        return next(line for line in r.stdout.splitlines() if line.startswith("gate pr=%d " % pr) and " name=%s " % name in line)

    def test_open_cut_holds_the_fragment_pr_and_lands_nothing(self):
        r = self.train("check", "1", "2")
        self.assertIn("status=pass", self.gate(r, 1, "release-cut"))
        self.assertIn("status=pass", self.gate(r, 1, "state-permission"))  # the cut itself is not held
        self.assertIn('status=blocked reason="release cut #1 (7.2.0) open: fragment changes hold until it lands"',
                      self.gate(r, 2, "state-permission"))
        self.open_prs()
        self.assertEqual(self.train("build", "2").returncode, 0)
        self.open_prs((1, ["CHANGELOG.md"]), (2, ["changes/unreleased/2-b.md"]))  # the cut opened while the train ran
        land = self.train("land", "1", "2")
        self.assertEqual(land.returncode, 1, land.stdout + land.stderr)
        self.assertIn("release cut #1 (7.2.0) open", land.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])

    def test_cut_behind_main_after_a_fragment_lands_is_refused_until_update_branch(self):
        self.open_prs()  # 7.2.0: nothing held the fragment PR, so it landed after the cut's approval
        self.commit({"changes/unreleased/2-b.md": "b\n"}, "squash #2")
        self.git("push", "-q", "origin", "main")
        base = self.remote("refs/heads/main")
        r = self.train("check", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('status=blocked reason="release cut 7.2.0 behind %s: update-branch so release.yml validate '
                      're-runs on current main; never land it direct"' % base[:7], self.gate(r, 1, "release-cut"))
        self.git("checkout", "-q", "pr1")  # update-branch: the head now contains main, so validate saw 2-b.md
        self.git("merge", "-q", "--no-edit", "origin/main")
        self.git("push", "-q", "origin", "HEAD:refs/pull/1/head")
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        path, view = self.complete_view(1)
        view["headRefOid"] = head
        with open(path, "w") as f:
            json.dump(view, f)
        self.complete_view(1)
        self.assertIn("status=pass reason=\"release cut 7.2.0 contains %s\"" % base[:7],
                      self.gate(self.train("check", "1"), 1, "release-cut"))

    def test_cut_without_changelog_patch_is_unreadable_and_blocks_both_gates(self):
        self.files(1, [{"filename": "CHANGELOG.md", "status": "modified"},
                       {"filename": "changes/unreleased/1-a.md", "status": "removed"}])
        r = self.train("check", "1", "2")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('status=blocked reason="unreadable: CHANGELOG.md patch unavailable"', self.gate(r, 1, "release-cut"))
        self.assertIn('status=blocked reason="release-cut hold unreadable: CHANGELOG.md patch unavailable"',
                      self.gate(r, 2, "state-permission"))
        self.open_prs()
        self.commit({"changes/unreleased/2-b.md": "b\n"}, "squash #2")
        self.git("push", "-q", "origin", "main")
        r = self.train("check", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("status=blocked", self.gate(r, 1, "release-cut"))

    def test_unreadable_open_list_holds_fragment_prs_only(self):
        with open(os.path.join(self.gh_dir, "open.json"), "w") as f:
            f.write("not json")
        r = self.train("check", "1", "2")
        self.assertIn("status=pass", self.gate(r, 1, "state-permission"))
        self.assertIn('status=blocked reason="release-cut hold unreadable:', self.gate(r, 2, "state-permission"))


class Delegated(TrainBase):
    """#1391: the synthesizer delegates the build to a builder worker and keeps landing; only it lands."""

    def delegate(self, *prs, handoff=0):
        """Run `train delegate` in process with the builder lead's handoff mocked; (exit, stdout, handoff calls)."""
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(mod)
        parser = argparse.ArgumentParser()
        mod.commands()["train"].register(parser.add_subparsers())
        args = parser.parse_args(["train", "delegate", *map(str, prs), "--project", self.project])
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out), \
                mock.patch.object(mod.commands()["lead"], "handoff", return_value=handoff) as sent:
            code = mod.commands()["train"].run(args)
            self.open = mod.open_trains(self.state)
        return code, out.getvalue(), sent.call_args_list

    def no_train_pr(self):
        log = os.path.join(self.gh_dir, "gh.log")
        self.assertFalse(os.path.exists(log) and self.gh_calls("pr", "create"))

    def delegation(self, n=1):
        with open(os.path.join(self.state, "trains", "delegated-%d.json" % n)) as f:
            return json.load(f)

    def test_delegate_hands_refs_to_builder_lead_then_builder_builds_that_train(self):
        heads = [self.pr(n, {"f%d.txt" % n: "x\n"}) for n in (1, 2)]
        base = self.remote("refs/heads/main")
        code, out, sent = self.delegate(1, 2)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].args[1:], ("builder", "train", ["train-1", base, "#1", heads[0], "#2", heads[1]]))
        self.assertIn("delegated train n=1 base=%s members=1@%s,2@%s" % (base, heads[0], heads[1]), out)
        self.assertEqual(self.delegation()["synthesizer"], "sam")
        self.assertEqual([os.path.basename(p) for p in self.open], ["delegated-1.json"])  # route keeps sam alive
        self.no_train_pr()  # the synthesizer built nothing
        refused = self.train("build", "--train", "1", "1")
        self.assertEqual(refused.returncode, 2)
        r = self.train("build", "--train", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([(m["pr"], m["head"]) for m in self.record(1)["members"]], [(1, heads[0]), (2, heads[1])])
        self.assertEqual((self.record(1)["base"], self.record(1)["ci"]), (base, "pass"))
        again = self.train("build", "--train", "1")  # a restarted builder waits instead of rebuilding
        self.assertEqual(again.returncode, 1)
        self.assertIn("delegated train 1 is already built; run mdstack train wait 1", again.stdout)
        self.assertEqual(self.gh_calls("pr", "merge"), [])  # the builder never lands
        self.assertEqual([r.returncode for r in self.land_all(1, (1, 2))], [0, 0])

    def test_delegation_names_the_synthesizer_lead_when_installed(self):  # #1569: train-done reaches the lander
        self.pr(1, {"f1.txt": "x\n"})
        self.put("render/runtime/synthesizer-lead.md", "Land.\n")
        code, out, _ = self.delegate(1)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.delegation()["synthesizer"], "sam-lead")

    def test_refused_handoff_closes_the_delegation(self):
        self.pr(1, {"f1.txt": "x\n"})
        self.pr(2, {"f2.txt": "x\n"})
        code, out, _ = self.delegate(1, 2, handoff=1)
        self.assertEqual(code, 1)
        self.assertIn("builder lead handoff failed; delegation 1 closed; build the train yourself", out)
        self.assertTrue(self.delegation()["closed"])
        self.assertEqual(self.open, [])
        self.assertEqual(self.train("build", "--train", "1").returncode, 1)
        r = self.train("build", "1", "2")  # the synthesizer's own build takes the next number
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("train n=2 ", r.stdout)

    def test_concurrent_land_during_the_build_stales_the_train(self):
        self.pr(1, {"f1.txt": "x\n"})
        self.pr(2, {"f2.txt": "x\n"})
        self.assertEqual(self.delegate(1, 2)[0], 0)
        self.commit({"z.txt": "z\n"}, "sam landed #3 directly meanwhile")
        self.git("push", "-q", "origin", "main")
        r = self.train("build", "--train", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped train=1 reason=base-moved", r.stdout)
        rec = self.record(1)
        self.assertTrue(rec["closed"])
        self.assertEqual(rec["members"], [])
        self.no_train_pr()

    def test_concurrent_land_after_a_green_build_stops_the_member_land(self):
        heads = [self.pr(n, {"f%d.txt" % n: "x\n"}) for n in (1, 2)]
        self.assertEqual(self.delegate(1, 2)[0], 0)
        self.assertEqual(self.train("build", "--train", "1").returncode, 0)
        self.serve(3, self.pr(3, {"f3.txt": "x\n"}), [{"body": VERDICT % (3, self.view(3)[0])}])
        subprocess.run(["gh", "pr", "merge", "3", "-R", "acme/widgets", "--squash", "--match-head-commit",
                        self.view(3)[0]], env=self.env, check=True)  # sam's direct land of a non-member
        r = self.train("land", "1", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stopped pr=1 reason=main moved", r.stdout)
        self.assertEqual([c["args"][2] for c in self.gh_calls("pr", "merge")], ["3"])
        self.assertNotIn(heads[0], self.git("log", "--format=%H", "origin/main"))

    def test_moved_member_head_drops_without_merge_up(self):
        self.pr(1, {"f1.txt": "x\n"})
        self.pr(2, {"f2.txt": "x\n"})
        self.assertEqual(self.delegate(1, 2)[0], 0)
        self.git("checkout", "-q", "pr2")  # a fix round pushed a new head after the handoff
        self.commit({"f2.txt": "y\n"}, "fix")
        self.git("push", "-q", "origin", "HEAD:refs/pull/2/head")
        self.git("checkout", "-q", "main")
        r = self.train("build", "--train", "1")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("dropped pr=2 reason=head-moved", r.stdout)
        self.assertEqual([m["pr"] for m in self.record(1)["members"]], [1])
        self.assertEqual(self.record(1)["dropped"][0]["merge_up"], "none")

    def test_dead_builder_train_closes_before_any_record(self):
        self.pr(1, {"f1.txt": "x\n"})
        self.pr(2, {"f2.txt": "x\n"})
        self.assertEqual(self.delegate(1, 2)[0], 0)
        r = self.train("close", "1")  # the lead's second restart failed: train-failed train-1
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("train n=1 delegation closed before build", r.stdout)
        self.assertTrue(self.delegation()["closed"])
        late = self.train("build", "--train", "1")  # a zombie worker builds nothing
        self.assertEqual(late.returncode, 1)
        self.assertIn("delegated train 1 is closed", late.stdout)
        self.no_train_pr()

    def test_red_delegated_train_bisects_and_survivors_land(self):
        heads = [self.pr(n, {"f%d.txt" % n: "x\n"}) for n in (1, 2, 3)]
        self.assertEqual(self.delegate(1, 2, 3)[0], 0)
        self.checks(FAIL)
        self.assertEqual(self.train("build", "--train", "1").returncode, 1)
        with open(os.path.join(self.gh_dir, "culprit.json"), "w") as f:
            json.dump(2, f)
        r = self.train("bisect", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("culprit pr=2", r.stdout)
        survivor = self.record(self.record(1)["bisect"]["remaining"])
        self.assertEqual([(m["pr"], m["head"]) for m in survivor["members"]], [(1, heads[0]), (3, heads[2])])
        self.assertEqual(self.gh_calls("pr", "merge"), [])
        self.assertEqual([x.returncode for x in self.land_all(survivor["n"], (1, 3))], [0, 0])


class RepoBound(TrainBase):
    """#1859 (team §9.5): a train action reads its records, members and gate records only from the selected repo. Each
    foreign source refuses before any write, merge or cleanup; the same source from acme/widgets is the control."""

    def tree(self):
        """Every file under the state dir and its bytes: a refusal leaves it unchanged."""
        found = {}
        for top, _, names in os.walk(self.state):
            for n in names:
                with open(os.path.join(top, n), "rb") as f:
                    found[os.path.relpath(os.path.join(top, n), self.state)] = f.read()
        return found

    def writes(self):
        with open(self.git_log) as f:
            git = [line for line in f.read().splitlines() if line.split()[:1] in (["clone"], ["push"])]
        return [c["args"][:2] for c in self.gh_calls() if c["args"][:2] in (
            ["pr", "create"], ["pr", "merge"], ["pr", "close"], ["pr", "review"], ["pr", "edit"])] + git

    def edit(self, name, **fields):
        path = os.path.join(self.gh_dir, name)
        with open(path) as f:
            data = json.load(f)
        with open(path, "w") as f:
            json.dump(dict(data, **fields), f)

    def test_gate_reads_from_another_repo_land_nothing(self):
        hold = "<!-- crew:v1 role=coordinator pass=steer --> hold-until-#77"

        def verdict(n, repo):
            self.edit("pr-%d.json" % n, url="https://github.com/%s/pull/%d" % (repo, n))

        def dependency(n, repo):
            head, reviews = self.view(n)
            self.serve(n, head, reviews + [{"body": hold}])
            self.issue(77, "CLOSED")
            self.edit("issue-77.json", url="https://github.com/%s/issues/77" % repo)

        def control(n, repo):
            self.put("landing-control.json", '{"issue": 99}')
            with open(os.path.join(self.gh_dir, "issue-99.json"), "w") as f:
                json.dump({"state": "OPEN", "comments": [], "url": "https://github.com/%s/issues/99" % repo}, f)

        cases = [(verdict, "change #%d's verdict and permission read"), (dependency, "hold-until-#77 dependency"),
                 (control, "landing control #99")]
        n = 0
        for setup, what in cases:
            for repo in ("example/beta", "acme/widgets"):
                n += 1
                with self.subTest(source=what, repo=repo):
                    self.built(n)
                    setup(n, repo)
                    result = self.train("land", str(n), str(n))
                    merged = [c["args"][2] for c in self.gh_calls("pr", "merge")]
                    if repo == "acme/widgets":
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn(str(n), merged)
                    else:
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn("is example/beta, not acme/widgets", result.stdout)
                        self.assertIn(what % n if "%d" in what else what, result.stdout)
                        self.assertNotIn(str(n), merged)
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(os.path.join(self.state, "landing-control.json"))

    def test_foreign_record_or_member_refuses_whole_action_with_nothing_written(self):
        self.built(1)
        for n in (2, 3):
            self.pr(n, {"f%d.txt" % n: "x\n"})
        own = self.record()
        self.assertEqual((own["context"]["team"], own["context"]["repo"]), ("repo:acme/widgets", "acme/widgets"))
        path = os.path.join(self.state, "trains", "train-1.json")
        beta = dict(own, context=dict(own["context"], team="repo:example/beta", repo="example/beta"))
        delegated = dict(beta, members=[{"pr": 2, "head": own["members"][0]["head"]}])

        def record(rec):
            with open(path, "w") as f:
                f.write(rec if isinstance(rec, str) else json.dumps(rec))

        def delegation(rec):
            with open(os.path.join(self.state, "trains", "delegated-4.json"), "w") as f:
                json.dump(rec, f)

        def member_url(n):
            return lambda: self.edit("pr-%d.json" % n, url="https://github.com/example/beta/pull/%d" % n)

        cases = [  # (setup, train arguments, the refused source)
            (lambda: record(beta), ("land", "1", "1"), "train 1 record is example/beta"),
            (lambda: record(beta), ("close", "1"), "train 1 record is example/beta"),
            (lambda: record(beta), ("wait", "1"), "train 1 record is example/beta"),
            (lambda: record(beta), ("route", "1"), "train 1 record is example/beta"),
            (lambda: record(beta), ("build", "2", "--after", "1"), "train 1 record is example/beta"),
            (lambda: record("not json"), ("close", "1"), "train 1 record names no readable repo context"),
            (lambda: delegation(delegated), ("build", "--train", "4"), "train 4 delegation is example/beta"),
            (lambda: None, ("build", "2", "example/beta#3"), "example/beta#3 is example/beta, not acme/widgets"),
            (lambda: None, ("delegate", "example/beta#2", "3"), "example/beta#2 is example/beta, not acme/widgets"),
            (member_url(3), ("build", "2", "3"), "member #3 is example/beta, not acme/widgets"),
            (member_url(3), ("delegate", "2", "3"), "member #3 is example/beta, not acme/widgets"),
        ]
        for setup, argv, why in cases:
            with self.subTest(argv=argv):
                record(own)
                for n in (2, 3):
                    self.edit("pr-%d.json" % n, url="https://github.com/acme/widgets/pull/%d" % n)
                setup()
                before, writes = self.tree(), self.writes()
                result = self.train(*argv)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("crew: refusing train %s: " % argv[0], result.stdout)
                self.assertIn(why, result.stdout)
                self.assertEqual(self.tree(), before)
                self.assertEqual(self.writes(), writes)
                with contextlib.suppress(FileNotFoundError):
                    os.remove(os.path.join(self.state, "trains", "delegated-4.json"))
        record(own)  # controls: this repo's record and a member qualified with this repo act
        self.edit("pr-3.json", url="https://github.com/acme/widgets/pull/3")
        result = self.train("build", "2", "acme/widgets#3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([m["pr"] for m in self.record(2)["members"]], [2, 3])
        self.assertEqual(self.record(2)["context"], own["context"])
        legacy = dict(own)
        legacy.pop("context")
        record(legacy)  # a one-repo record from before #1859: the selected state is its only project
        result = self.train("close", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([c["args"][2] for c in self.gh_calls("pr", "close")][-1:], ["900"])


if __name__ == "__main__":
    unittest.main()
