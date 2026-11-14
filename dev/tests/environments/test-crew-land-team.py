"""Repo-bound land, locks and trains for one team serving two repos (#1859, docs/specs/team.md §9.5), through the
shipped `mdstack train` and `land-lock` entry points. Two disposable repos, example/alpha and example/beta, share
change numbers, heads and train numbers under one team file; a fake gh logs every backend call with its repo and a
logging git records clones and pushes. Each refusal pairs with a valid same-repo control and leaves both repo states
and the mutation log unchanged. No model or network calls. Run in CI.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, CREW

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GH = """#!/usr/bin/env python3
import json, os, sys
args, d = sys.argv[1:], os.environ["FAKE_GH_DIR"]
open(os.path.join(d, "gh.log"), "a").write(json.dumps(args) + "\\n")
repo = args[args.index("-R") + 1] if "-R" in args else ""
if args[:2] in (["pr", "view"], ["issue", "view"]):
    path = os.path.join(d, repo.replace("/", "__"), "%s-%s.json" % (args[0], args[2]))
    view = json.load(open(path)) if os.path.exists(path) else {}
    print(json.dumps(dict({"url": "https://github.com/%s/%s/%s" % (repo, "pull" if args[0] == "pr" else "issues", args[2]),
                           "number": int(args[2]), "labels": [], "reviews": [], "comments": [], "state": "OPEN",
                           "closingIssuesReferences": []}, **view)))
elif args[:2] == ["pr", "create"]:
    print("https://github.com/%s/pull/900" % repo)
elif args[:2] == ["pr", "checks"]:
    print(json.dumps([{"name": "ci", "bucket": "pass", "link": "https://ci.invalid/1"}]))
elif args[:1] == ["api"]:
    print("[]")
else:
    print("{}")
"""
WRITES = (["pr", "create"], ["pr", "merge"], ["pr", "close"], ["pr", "review"], ["pr", "edit"], ["issue", "edit"])


class TeamLand(Base):
    def setUp(self):
        super().setUp()
        bindir, real = os.path.join(self.tmp, "bin"), shutil.which("git")
        self.gh_dir, self.git_log = os.path.join(self.tmp, "gh"), os.path.join(self.tmp, "git.log")
        os.makedirs(self.gh_dir)
        for name, text in [("gh", GH), ("git", '#!/bin/sh\necho "$*" >> %s\nexec %s "$@"\n' % (self.git_log, real))]:
            with open(os.path.join(bindir, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(bindir, name), 0o755)
        self.env.update(FAKE_GH_DIR=self.gh_dir, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        self.checkouts = {}
        for repo in ("alpha", "beta"):
            origin, work = os.path.join(self.tmp, repo + ".git"), os.path.join(self.tmp, repo)
            os.makedirs(work)
            self.git("init", "-q", "--bare", "-b", "main", origin, cwd=self.tmp)
            self.git("init", "-q", "-b", "main", cwd=work)
            self.git("remote", "add", "origin", origin, cwd=work)
            self.git("commit", "-q", "--allow-empty", "-m", "base", cwd=work)
            self.git("push", "-q", "origin", "main", cwd=work)
            self.checkouts[repo] = work
        self.team = os.path.join(self.project_dir, "teams", "eng.toml")
        os.makedirs(os.path.dirname(self.team))
        with open(self.team, "w") as f:
            f.write('[team]\npersonas = { builder = "Ben", reviewer = "Vera", synthesizer = "Sam" }\n'
                    'accounts = { all = "acme-bot", reviewer = "acme-reviewer" }\n'
                    '[team.runtime]\nname = "tmux"\ninstance = "local"\n'
                    '[team.identities]\nowners = ["acme-owner"]\n'
                    '[team.paths]\nstate_dir = "%s"\nworktree_root = "%s"\ntoolchain_bin = "/opt/node/bin"\n'
                    '[repos.a]\nrepo = "example/alpha"\ncheckout = "%s"\n'
                    '[repos.b]\nrepo = "example/beta"\ncheckout = "%s"\n'
                    % (os.path.join(self.tmp, "state"), os.path.join(self.tmp, "wt"), self.checkouts["alpha"],
                       self.checkouts["beta"]))
        self.refs = {"alpha": self.team + "#a", "beta": self.team + "#b"}
        self.states = {r: os.path.join(self.tmp, "state", "eng", "example__" + r) for r in ("alpha", "beta")}
        loader = importlib.machinery.SourceFileLoader("crew_config_t", os.path.join(ROOT, "core", "crew-config.py"))
        config = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_config_t", loader))
        loader.exec_module(config)
        self.ctx = {}
        for repo, ref in self.refs.items():
            team, _ = config.project_identity(ref)
            self.ctx[repo] = config.context(ref, team, "example", repo)

    def git(self, *args, cwd):
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def change(self, repo, n):
        """Change n in repo: a head at refs/pull/<n>/head with a passing verdict at it, served by the fake gh."""
        work = self.checkouts[repo]
        self.git("checkout", "-q", "-B", "c%d" % n, "origin/main", cwd=work)
        with open(os.path.join(work, "f%d.txt" % n), "w") as f:
            f.write("%s %d\n" % (repo, n))
        self.git("add", "-A", cwd=work)
        self.git("commit", "-q", "-m", "change %d" % n, cwd=work)
        self.git("push", "-q", "origin", "HEAD:refs/pull/%d/head" % n, cwd=work)
        head = self.git("rev-parse", "HEAD", cwd=work)
        self.git("checkout", "-q", "main", cwd=work)
        verdict = "<!-- crew:v1 role=reviewer-validator pass=verdict pr=%d sha=%s round=1 verdict=pass -->" % (n, head)
        self.serve(repo, n, headRefOid=head, reviews=[{"body": "[Vera/verdict]\n" + verdict}])
        return head

    def serve(self, repo, n, **view):
        d = os.path.join(self.gh_dir, "example__" + repo)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "pr-%d.json" % n), "w") as f:
            json.dump(view, f)

    def run_crew(self, repo, *args, **env):
        return self.crew(*args, "--project", self.refs[repo], **env)

    def snapshot(self):
        """Both repo states as files and bytes, plus every backend write and git clone or push so far."""
        files = {}
        for top, _, names in os.walk(os.path.join(self.tmp, "state")):
            for n in names:
                with open(os.path.join(top, n), "rb") as f:
                    files[os.path.join(top, n)] = f.read()
        gh, git, calls = os.path.join(self.gh_dir, "gh.log"), [], []
        if os.path.exists(gh):
            with open(gh) as f:
                calls = [json.loads(line) for line in f]
        if os.path.exists(self.git_log):
            with open(self.git_log) as f:
                git = [line for line in f.read().splitlines() if line.split()[:1] in (["clone"], ["push"])]
        return files, [c for c in calls if c[:2] in WRITES or c[:1] == ["api"] and "--method" in c], git

    def put(self, repo, rel, data):
        path = os.path.join(self.states[repo], rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)


class Trains(TeamLand):
    def test_mixed_or_foreign_train_refused_with_zero_mutation_and_all_local_train_builds(self):
        heads = {r: [self.change(r, 7), self.change(r, 9)] for r in ("alpha", "beta")}
        self.assertNotEqual(heads["alpha"], heads["beta"])
        beta_train = {"n": 1, "branch": "crew/train-1", "base": "0" * 40, "sha": "1" * 40, "pr": 900, "ci": "pass",
                      "local": "skipped", "ci_links": [], "after": None, "deferred": [], "dropped": [], "closed": False,
                      "members": [{"pr": 7, "head": heads["alpha"][0], "step": "2" * 40}], "context": self.ctx["beta"]}

        def redirect():  # alpha's change 9 reads back as beta's: a transferred or redirected change
            self.serve("alpha", 9, **dict(self.view("alpha", 9), url="https://github.com/example/beta/pull/9"))
        cases = [  # (setup, train arguments, the refused source); every case runs against repo alpha
            (None, ("build", "7", "example/beta#7"), "example/beta#7 is example/beta, not example/alpha"),
            (None, ("delegate", "7", "example/beta#9"), "example/beta#9 is example/beta, not example/alpha"),
            (redirect, ("build", "7", "9"), "member #9 is example/beta, not example/alpha"),
            (lambda: self.put("alpha", "trains/train-1.json", beta_train), ("land", "1", "7"),
             "train 1 record is example/beta in team eng, not example/alpha in team eng"),
            (lambda: self.put("alpha", "trains/train-1.json", beta_train), ("close", "1"), "train 1 record is example/beta"),
            (lambda: self.put("alpha", "trains/delegated-1.json", dict(beta_train, members=[{"pr": 7, "head": heads[
                "alpha"][0]}])), ("build", "--train", "1"), "train 1 delegation is example/beta"),
        ]
        for setup, argv, why in cases:
            with self.subTest(argv=argv):
                if setup:
                    setup()
                before = self.snapshot()
                r = self.run_crew("alpha", "train", *argv)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("crew: refusing train %s: %s" % (argv[0], why), r.stdout)
                self.assertEqual(self.snapshot(), before)  # no record, clone, push, PR, merge or cleanup
                shutil.rmtree(os.path.join(self.states["alpha"], "trains"), ignore_errors=True)
                self.serve("alpha", 9, **dict(self.view("alpha", 9), url="https://github.com/example/alpha/pull/9"))
        beta = self.snapshot()[0]
        r = self.run_crew("alpha", "train", "build", "7", "9", "--no-wait", "--grace", "0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.states["alpha"], "trains", "train-1.json")) as f:
            rec = json.load(f)
        self.assertEqual([(m["pr"], m["head"]) for m in rec["members"]], list(zip((7, 9), heads["alpha"])))
        self.assertEqual(rec["context"], self.ctx["alpha"])  # the result routes back to alpha
        creates = [c for c in self.snapshot()[1] if c[:2] == ["pr", "create"]]
        self.assertEqual([c[c.index("-R") + 1] for c in creates], ["example/alpha"])
        self.assertEqual({p: b for p, b in self.snapshot()[0].items() if self.states["beta"] in p},
                         {p: b for p, b in beta.items() if self.states["beta"] in p})  # beta untouched
        self.assertIsNone(self.git_ref("beta", "refs/heads/crew/train-1"))
        self.assertIsNotNone(self.git_ref("alpha", "refs/heads/crew/train-1"))

    def view(self, repo, n):
        with open(os.path.join(self.gh_dir, "example__" + repo, "pr-%d.json" % n)) as f:
            return json.load(f)

    def git_ref(self, repo, ref):
        out = self.git("ls-remote", os.path.join(self.tmp, repo + ".git"), ref, cwd=self.tmp)
        return out.split("\t")[0] or None


class Locks(TeamLand):
    def lock(self, repo, action):
        return self.run_crew(repo, "land-lock", action)

    def pidfile(self, repo):
        return os.path.join(self.states[repo], "locks", "merge.pid")

    def test_each_repo_has_its_own_lock_and_record(self):
        self.addCleanup(self.lock, "alpha", "release")
        self.addCleanup(self.lock, "beta", "release")
        self.assertEqual(self.lock("alpha", "acquire").returncode, 0)
        again = self.lock("alpha", "acquire")
        self.assertEqual(again.returncode, 1, again.stdout)  # one land at a time inside alpha
        self.assertIn("is held; another land is in progress", again.stdout)
        other = self.lock("beta", "acquire")
        self.assertEqual(other.returncode, 0, other.stdout)  # beta is not blocked by alpha's lock
        for repo in ("alpha", "beta"):
            with open(self.pidfile(repo)) as f:
                self.assertEqual(json.load(f)["context"], self.ctx[repo])
        self.assertEqual(self.lock("alpha", "release").returncode, 0)
        self.assertTrue(os.path.exists(self.pidfile("beta")))

    def test_foreign_lock_record_refused_before_cleanup_and_own_record_cleaned(self):
        self.addCleanup(self.lock, "alpha", "release")  # no holder outlives the test, even when a refusal regresses
        for action in ("acquire", "release"):
            for repo in ("beta", "alpha"):
                with self.subTest(action=action, record=repo):
                    self.lock("alpha", "release")  # a holder a regressed case left never outlives its record
                    stale = {"pid": 999999, "start": "never", "owner": None, "window": "sam-lead",
                             "context": self.ctx[repo]}  # a dead holder's record
                    self.put("alpha", "locks/merge.pid", stale)
                    before = self.snapshot()
                    r = self.lock("alpha", action)
                    if repo == "beta":
                        self.assertEqual(r.returncode, 1, r.stdout)
                        self.assertIn("crew: refusing %s: land lock record %s is example/beta in team eng, not "
                                      "example/alpha in team eng; nothing cleaned, signalled or removed"
                                      % (action, self.pidfile("alpha")), r.stdout)
                        self.assertEqual(self.snapshot(), before)
                    else:
                        self.assertEqual(r.returncode, 0, r.stdout)
                        if action == "acquire":
                            with open(self.pidfile("alpha")) as f:
                                self.assertEqual(json.load(f)["context"], self.ctx["alpha"])
                            self.assertEqual(self.lock("alpha", "release").returncode, 0)


if __name__ == "__main__":
    unittest.main()
