#!/usr/bin/env python3
"""The one apply entry point for triage sweep writes (#753; docs/triage.md#write-allowlist).

Usage: triage-apply.py --project FILE --requests FILE

The requests file is {"sweep": "<YYYYMMDDTHHMMZ>", "signature": "<one line>", "requests": [{"kind": ...}, ...]}.
Every request is checked before anything is written: against the write allowlist (the kinds below), the profile's
triage.mode and triage.repos, and the issue's own pass=triage record from this sweep (posted in the same batch, or
already on the issue by the researcher's login). One refused request refuses the batch: each reason goes to stderr,
exit 1, zero writes. Otherwise each write runs once through `gh`, one already in effect is skipped, and stdout lists
both; exit 0. Exit 2: unreadable profile or requests, or a non-GitHub tracker (no apply binding; nothing written).
Exit 3: a forge command failed mid-batch; a rerun skips the writes already made.

Kinds: record, refusal, label, unlabel, milestone, flavor, duplicate, card, log, cluster-record, intake-card,
intake-evidence. Anything else (a close, a gate or `crew:` label, a milestone create, a body edit, a repository or
owner-config write) is refused. Issue text never widens this set.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("crew_config", os.path.join(ROOT, "core", "crew-config.py"))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

TYPE_LABELS = ("bug", "enhancement", "documentation", "question")
SCOPE_LABELS = ("scope:repo", "scope:crew")
BANDS = ("P0", "P1", "P2", "P3")
REVERTS = ("owner-rejected", "owner-adjusted")  # owner answers that revert or correct applied changes
APPLY_ONLY = ("milestone", "flavor", "duplicate")
MARKER = re.compile(r"<!-- crew:v1 (.*?) -->")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


class Refused(Exception):
    pass


class ForgeError(Exception):
    pass


def markers(body):
    return [dict(re.findall(r"(\S+)=(\S+)", m)) for m in MARKER.findall(body)] if isinstance(body, str) else []


def one_marker(body, **want):
    """The body's single crew:v1 marker; refused unless it is exactly one and matches every wanted field (`pass` is
    a keyword, so callers spell it pass_)."""
    want = {("pass" if k == "pass_" else k): v for k, v in want.items()}
    found = markers(body)
    if len(found) != 1:
        raise Refused("needs exactly one crew:v1 marker, found %d" % len(found))
    bad = sorted(k for k, v in want.items() if found[0].get(k) != v)
    if bad:
        raise Refused("marker field %s must be %s" % (bad[0], want[bad[0]]))
    return found[0]


def plain(body, what="body"):
    if not isinstance(body, str) or not body.strip():
        raise Refused("%s must be non-empty text" % what)
    if markers(body):
        raise Refused("%s carries a crew:v1 marker" % what)
    return body


class Gh:
    """The GitHub tracker writes and reads (docs/backends/github.md Interface mapping)."""

    def run(self, *args):
        r = subprocess.run(["gh", *args], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if r.returncode:
            raise ForgeError("gh %s: %s" % (" ".join(args[:2]), r.stderr.strip()))
        return r.stdout

    def issue(self, repo, n):
        try:
            i = json.loads(self.run("issue", "view", str(n), "-R", repo, "--json",
                                    "number,url,state,title,labels,milestone,comments"))
        except ForgeError:
            return None
        return dict(i, labels=[lb["name"] for lb in i.get("labels") or []],
                    milestone=(i.get("milestone") or {}).get("title"))

    def issues(self, repo):
        out = json.loads(self.run("issue", "list", "-R", repo, "--state", "all", "--limit", "500", "--json",
                                  "number,title,labels,state"))
        return [dict(i, labels=[lb["name"] for lb in i.get("labels") or []]) for i in out]

    def milestones(self, repo):
        pages = json.loads(self.run("api", "--paginate", "--slurp", "repos/%s/milestones?state=open&per_page=100" % repo))
        return [m for page in pages for m in page]

    def label(self, repo, n, label, add):
        if add and label.startswith("cluster:"):  # a new cluster's label may not exist yet
            self.run("label", "create", label, "-R", repo, "--force")
        self.run("issue", "edit", str(n), "-R", repo, "--add-label" if add else "--remove-label", label)

    def milestone(self, repo, n, title):
        self.run("issue", "edit", str(n), "-R", repo, *(["--milestone", title] if title else ["--remove-milestone"]))

    def comment(self, repo, n, body):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(body)
        try:
            self.run("issue", "comment", str(n), "-R", repo, "--body-file", f.name)
        finally:
            os.unlink(f.name)

    def create(self, repo, title, body, label=None):
        out = self.run("issue", "create", "-R", repo, "--title", title, "--body", body,
                       *(["--label", label] if label else []))
        return int(out.strip().rstrip("/").rsplit("/", 1)[-1])

    def close(self, repo, n, body):
        self.run("issue", "close", str(n), "-R", repo, "--comment", body)


class Batch:
    def __init__(self, values, merged, forge, doc):
        if not isinstance(doc, dict) or not isinstance(doc.get("requests"), list):
            raise ValueError("expected an object with a requests list")
        self.values, self.forge, self.sweep = values, forge, doc.get("sweep")
        self.sig = doc.get("signature")
        if not isinstance(self.sweep, str) or not re.fullmatch(r"\d{8}T\d{4}Z", self.sweep):
            raise ValueError("sweep must be YYYYMMDDTHHMMZ")
        if not isinstance(self.sig, str) or not self.sig.strip() or "\n" in self.sig or markers(self.sig):
            raise ValueError("signature must be one plain line")
        self.requests, self.mode = doc["requests"], values.get("triage.mode", "shadow")
        self.project = "%s/%s" % (values["repo.owner"], values["repo.name"])
        self.repos = values.get("triage.repos") or [self.project]
        self.bot = values.get("identities.researcher.gh_user")
        self.owners = set(values.get("identities.owners") or [])
        self.flavors = dict(config.FLAVOR_PRESETS)
        for name, knobs in ((merged.get("flavor") or {}).get("custom") or {}).items():
            self.flavors[name] = dict(self.flavors[knobs["base"]], **{k: v for k, v in knobs.items() if k != "base"})
        self.flavors.pop("express", None)
        self.project_flavor = values.get("flavor.name", config.UNSET_FLAVOR)
        self.cache, self.records, self.clusters, self.refusing = {}, {}, {}, []

    def item(self, repo, n):
        if (repo, n) not in self.cache:
            self.cache[repo, n] = self.forge.issue(repo, n)
        i = self.cache[repo, n]
        if not i or "/pull/" in (i.get("url") or ""):
            raise Refused("unknown issue %s#%s" % (repo, n))
        return i

    def researcher(self, item):
        """(fields, index) of each researcher-authored pass=triage marker on the item, oldest first."""
        return [(f, k) for k, c in enumerate(item.get("comments") or [])
                if self.bot and (c.get("author") or {}).get("login") == self.bot
                for f in markers(c.get("body")) if f.get("pass") == "triage" and f.get("role") == "researcher"
                and f.get("issue") == str(item["number"])]

    def parked(self, item):
        recs = self.researcher(item)
        if recs and recs[-1][0].get("decision") == "refused":
            later = (item.get("comments") or [])[recs[-1][1] + 1:]
            return not any((c.get("author") or {}).get("login") in self.owners for c in later)
        return False

    def record(self, repo, n, item):
        rec = self.records.get((repo, n)) or next((f for f, _ in reversed(self.researcher(item))), None)
        if not rec or rec.get("sweep") != self.sweep:
            raise Refused("no pass=triage record from sweep %s on %s#%d" % (self.sweep, repo, n))
        return rec

    def has_comment(self, item, body):
        return any(c.get("body", "").strip() == body.strip() for c in item.get("comments") or [])

    def plan(self):
        """(writes, refusals): writes are (op, args, already) tuples; refusals are (index, kind, reason)."""
        refusals, writes, log = [], [], []
        for i, r in enumerate(self.requests):  # pre-scan: this batch's records and cluster records
            try:
                if isinstance(r, dict) and r.get("kind") == "record":
                    repo, n = self.target(r)
                    self.records[repo, n] = one_marker(r.get("body"), role="researcher", pass_="triage")
                elif isinstance(r, dict) and r.get("kind") == "refusal":
                    self.refusing.append(self.target(r))
                elif isinstance(r, dict) and r.get("kind") == "cluster-record":
                    f = one_marker(r.get("body"), role="researcher", pass_="triage-cluster")
                    self.clusters[f.get("cluster")] = r.get("body")
            except Refused:
                pass  # reported by the main pass
        for i, r in enumerate(self.requests):
            kind = r.get("kind") if isinstance(r, dict) else None
            try:
                check = getattr(self, "k_" + kind.replace("-", "_"), None) if isinstance(kind, str) else None
                if not check:
                    raise Refused("unknown or unlisted request kind %s" % json.dumps(kind))
                if kind in APPLY_ONLY and self.mode != "apply":
                    raise Refused("mode %s: %s is apply mode only (propose it)" % (self.mode, kind))
                out = check(r)
                if kind not in ("refusal", "log", "cluster-record"):  # log bodies land on the log issue
                    self.guard(out)
                (log if kind in ("log", "cluster-record") else writes).extend(out)
            except Refused as e:
                refusals.append((i, kind, str(e)))
        if (log or any(op == "cluster-link" for op, _, _ in writes)) and not refusals:
            writes = self.log_writes(log) + writes  # today's log first: member links name it
        return writes, refusals

    def repo_of(self, r):
        repo = r.get("repo", self.project)
        if repo not in self.repos:
            raise Refused("repo %s is not in triage.repos" % json.dumps(repo))
        return repo

    def target(self, r):
        repo, n = self.repo_of(r), r.get("issue")
        if type(n) is not int or n < 1:
            raise Refused("issue must be a positive integer")
        return repo, n

    def issue_of(self, r):
        repo, n = self.target(r)
        self.unparked(repo, n)
        return repo, n, self.item(repo, n)

    def unparked(self, repo, n):
        """Refuse a write on an issue parked by a refusal record without a later owner comment, or refused in this
        same batch."""
        if (repo, n) in self.refusing or self.parked(self.item(repo, n)):
            raise Refused("%s#%d is parked after a provider refusal until the owner acts" % (repo, n))

    def guard(self, writes):
        """Every issue a write lands on, an indirect one such as a duplicate's evidence destination included."""
        for op, args, _ in writes:
            if op in ("label", "unlabel", "milestone", "comment", "cluster-link"):
                self.unparked(args[0], args[1])

    def comment(self, repo, n, item, body):
        return [("comment", (repo, n, body), self.has_comment(item, body))]

    def k_record(self, r):
        repo, n, item = self.issue_of(r)
        f = one_marker(r.get("body"), role="researcher", pass_="triage", issue=str(n), mode=self.mode,
                       sweep=self.sweep)
        if f.get("decision") in (None, "refused") or f.get("priority") not in BANDS:
            raise Refused("record needs a decision (not refused; use the refusal kind) and a P0-P3 priority")
        return self.comment(repo, n, item, r["body"])

    def k_refusal(self, r):
        repo, n = self.target(r)
        item = self.item(repo, n)
        body = ("[%s/triage] #%d: refused P3\nRefused by the provider; parked for the owner, never retried or "
                "reframed.\n<!-- crew:v1 role=researcher pass=triage issue=%d decision=refused priority=P3 mode=%s "
                "sweep=%s -->\n%s" % (self.values.get("identities.researcher.name", "Researcher"), n, n, self.mode,
                                      self.sweep, self.sig))
        if self.refusing.count((repo, n)) > 1:
            raise Refused("one refusal per item: %s#%d is refused twice in this batch" % (repo, n))
        if not self.has_comment(item, body) and self.parked(item):
            raise Refused("%s#%d is parked after a provider refusal until the owner acts" % (repo, n))
        return self.comment(repo, n, item, body)

    def label_rule(self, r, add):
        repo, n, item = self.issue_of(r)
        label = r.get("label")
        rec = lambda: self.record(repo, n, item)
        if label == "triage:proposed":
            if not add and not rec().get("decision", "").startswith("owner-"):
                raise Refused("triage:proposed comes off only with an owner answer recorded")
            rec()
        elif label in BANDS + TYPE_LABELS + SCOPE_LABELS or (not add and label == "triage:duplicate"):
            if self.mode != "apply":
                raise Refused("mode %s: label %s is apply mode only (propose it)" % (self.mode, label))
            if add and label in BANDS and rec().get("priority") != label:
                raise Refused("band %s differs from the record's priority %s" % (label, rec().get("priority")))
            if not add and rec().get("decision") not in REVERTS:
                raise Refused("removing %s needs an owner-rejected or owner-adjusted record" % label)
            rec()
        elif isinstance(label, str) and label.startswith("cluster:") and SLUG.fullmatch(label[8:]):
            if self.mode != "apply":
                raise Refused("mode %s: cluster labels are apply mode only" % self.mode)
            body = self.clusters.get(label[8:])
            if body is None:
                raise Refused("no cluster record for %s in this batch" % label[8:])
            if add != bool(re.search(r"(?<![\w/])%s#%d\b|(?<![\w/#])#%d\b" % (re.escape(repo), n, n), body)):
                raise Refused("%s#%d is %s the cluster record" % (repo, n, "not in" if add else "still in"))
            if add:
                linked = any(c.get("body", "").startswith("Cluster `%s`:" % label[8:]) for c in item["comments"])
                return [("label", (repo, n, label), label in item["labels"]),
                        ("cluster-link", (repo, n, label[8:]), linked)]
        else:
            raise Refused("label %s is not on the allowlist" % json.dumps(label))
        return [("label" if add else "unlabel", (repo, n, label), (label in item["labels"]) == add)]

    def k_label(self, r):
        return self.label_rule(r, True)

    def k_unlabel(self, r):
        return self.label_rule(r, False)

    def k_milestone(self, r):
        repo, n, item = self.issue_of(r)
        rec, title = self.record(repo, n, item), r.get("milestone", "")
        if title is None:
            if rec.get("decision") not in REVERTS:
                raise Refused("clearing a milestone needs an owner-rejected or owner-adjusted record")
        else:
            found = self.forge.milestones(repo)
            if self.values.get("repo.milestones"):
                found = [m for k in self.values["repo.milestones"] for m in found if m["number"] == k]
            order, active = [m["title"] for m in found], self.values.get("runtime.options.max_active_milestones", 1)
            if title not in order:
                raise Refused("milestone %s is not open (triage never creates one)" % json.dumps(title))
            k = order.index(title)
            if k > active or (k < active and rec.get("priority") != "P0"):
                raise Refused("%s is %s milestone; only a P0 joins the active one, others the next" % (
                    title, "an active" if k < active else "a later"))
        return [("milestone", (repo, n, title), item.get("milestone") == title)]

    def k_flavor(self, r):
        repo, n, item = self.issue_of(r)
        self.record(repo, n, item)
        f = one_marker(r.get("body"), role="coordinator", pass_="flavor", issue=str(n))
        if f.get("flavor") not in self.flavors or f.get("flavor") != f.get("default") or "tier" in f:
            raise Refused("only the default flavor record (flavor equals default, no tier) applies")
        if self.lowers(f["flavor"]):
            raise Refused("flavor %s lowers the project flavor %s (propose it)" % (f["flavor"], self.project_flavor))
        recorded = any(g.get("pass") == "flavor" for c in item.get("comments") or [] for g in markers(c.get("body")))
        if recorded and not self.has_comment(item, r["body"]):
            raise Refused("%s#%d already has a flavor record" % (repo, n))
        return self.comment(repo, n, item, r["body"])

    def lowers(self, name):
        c, b = self.flavors[name], self.flavors.get(self.project_flavor, self.flavors[config.UNSET_FLAVOR])
        return any(config.FLAVOR_ORDER[k].index(c[k]) > config.FLAVOR_ORDER[k].index(b[k])
                   for k in config.FLAVOR_ORDER if k != "builder") or any(x < y for x, y in zip(c["caps"], b["caps"]))

    def k_duplicate(self, r):
        repo, n, item = self.issue_of(r)
        if self.record(repo, n, item).get("decision") != "duplicate":
            raise Refused("the record's decision is not duplicate")
        of = r.get("of")
        if type(of) is not int or of == n:
            raise Refused("of must be another issue number")
        orig = self.item(repo, of)
        link = "Duplicate of #%d\n\n%s" % (of, self.sig)
        out = [("label", (repo, n, "triage:duplicate"), "triage:duplicate" in item["labels"])]
        out += self.comment(repo, n, item, link)
        if r.get("evidence"):
            moved = "Evidence moved from #%d:\n\n%s\n\n%s" % (n, plain(r["evidence"], "evidence"), self.sig)
            out += self.comment(repo, of, orig, moved)
        return out

    def k_card(self, r):
        repo, n, item = self.issue_of(r)
        body = plain(r.get("body"))
        if "**Source:**" not in body or "**Failure class:**" not in body:
            raise Refused("card needs the intake-candidate Source and Failure class fields")
        if "triage:card-extracted" in item["labels"] and not self.has_comment(item, body):
            raise Refused("%s#%d already has an extracted card" % (repo, n))
        return self.comment(repo, n, item, body) + [
            ("label", (repo, n, "triage:card-extracted"), "triage:card-extracted" in item["labels"])]

    def k_log(self, r):
        one_marker(r.get("body"), role="researcher", pass_="triage-log", sweep=self.sweep)
        return [r["body"]]

    def k_cluster_record(self, r):
        f = one_marker(r.get("body"), role="researcher", pass_="triage-cluster", sweep=self.sweep)
        if not SLUG.fullmatch(f.get("cluster", "")):
            raise Refused("cluster record needs a cluster=<slug>")
        return [r["body"]]

    def k_intake_card(self, r):
        repo, title = self.repo_of(r), r.get("title")
        body = plain(r.get("body"))
        if not isinstance(title, str) or not title.startswith("intake: ") or "\n" in title:
            raise Refused("title must be one line starting with 'intake: '")
        if "**Trigger:** milestone-close" not in body or "**Decision:** pending" not in body:
            raise Refused("card needs Trigger milestone-close and Decision pending")
        done = any(i["title"] == title for i in self.forge.issues(repo))
        return [("create", (repo, title, body, None), done)]

    def k_intake_evidence(self, r):
        repo, n, item = self.issue_of(r)
        if not item.get("title", "").startswith("intake: "):
            raise Refused("%s#%d is not an intake card" % (repo, n))
        return self.comment(repo, n, item, plain(r.get("body")))

    def log_writes(self, bodies):
        date = "%s-%s-%s" % (self.sweep[:4], self.sweep[4:6], self.sweep[6:8])
        logs = [i for i in self.forge.issues(self.project) if "triage:log" in i["labels"]
                and str(i.get("state")).upper() == "OPEN"]
        today = next((i["number"] for i in logs if i["title"] == "Triage log " + date), None)
        item = self.forge.issue(self.project, today) if today else {"comments": []}
        out = [] if today else [("create-log", (self.project, "Triage log " + date), False)]
        out += [("close", (self.project, i["number"], "Closed by the %s log.\n\n%s" % (date, self.sig)), False)
                for i in logs if re.fullmatch(r"Triage log \d{4}-\d\d-\d\d", i["title"]) and i["title"][11:] < date]
        return out + [("log-comment", (self.project, b), self.has_comment(item, b)) for b in bodies]

    def apply(self, writes):
        log, date = None, "%s-%s-%s" % (self.sweep[:4], self.sweep[4:6], self.sweep[6:8])
        for op, args, already in writes:
            desc = "%s %s" % (op, " ".join(str(a).splitlines()[0] if isinstance(a, str) else str(a) for a in args[:3]))
            if already:
                print("skipped: %s (already in effect)" % desc)
                continue
            if op == "label" or op == "unlabel":
                self.forge.label(*args, add=op == "label")
            elif op == "milestone":
                self.forge.milestone(*args)
            elif op == "comment":
                self.forge.comment(*args)
            elif op == "create":
                self.forge.create(*args)
            elif op == "create-log":
                log = self.forge.create(*args, "Daily triage log ([docs/triage.md](https://github.com/%s/blob/main/"
                                        "docs/triage.md#owner-loop)).\n\n%s" % (self.project, self.sig), "triage:log")
            elif op == "close":
                self.forge.close(*args)
            else:  # log-comment or cluster-link: today's log issue, found or created above
                log = log or next(i["number"] for i in self.forge.issues(self.project) if "triage:log" in i["labels"]
                                  and i["title"] == "Triage log " + date and str(i.get("state")).upper() == "OPEN")
                if op == "log-comment":
                    self.forge.comment(self.project, log, args[1])
                else:
                    repo, n, slug = args
                    self.forge.comment(repo, n, "Cluster `%s`: this issue is a member; the cluster record is on "
                                                "%s#%d.\n\n%s" % (slug, self.project, log, self.sig))
            print("applied: %s" % desc)


def main(argv=None, forge=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True)
    p.add_argument("--requests", required=True)
    a = p.parse_args(argv)
    merged, _, problems, _ = config.resolve_profile(a.project)
    if problems:
        print("triage-apply: unreadable profile: %s; nothing written" % "; ".join(problems), file=sys.stderr)
        return 2
    values = dict(config.leaves(merged))
    if values.get("backends.tracker.name", "github") != "github":
        print("triage-apply: no apply binding for tracker backend %s; nothing written"
              % values["backends.tracker.name"], file=sys.stderr)
        return 2
    try:
        with open(a.requests) as f:
            batch = Batch(values, merged, forge or Gh(), json.load(f))
    except (OSError, ValueError) as e:
        print("triage-apply: unreadable requests %s: %s; nothing written" % (a.requests, e), file=sys.stderr)
        return 2
    try:
        writes, refusals = batch.plan()
    except ForgeError as e:
        print("triage-apply: forge read failed: %s; nothing written" % e, file=sys.stderr)
        return 3
    for i, kind, reason in refusals:
        print("refused: request %d (%s): %s" % (i, kind, reason), file=sys.stderr)
    if refusals:
        print("triage-apply: refused %d request(s); nothing written" % len(refusals), file=sys.stderr)
        return 1
    try:
        batch.apply(writes)
    except ForgeError as e:
        print("triage-apply: %s; stopped, rerun skips the writes already made" % e, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
