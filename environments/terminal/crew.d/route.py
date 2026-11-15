"""`mdstack route` consumes mechanical wakes without a coordinator model turn. The watcher calls it before waking
window 0. Worker completion retries admission in all pending pools. A backstop wake also runs `mdstack gc --apply`,
at most 5 removals of merged, landed run copies a missed close-out left (#316); its report goes to gc/backstop.txt.
New heads and escalated rechecks start review;
approved merge-ups stay queued for synthesizer dispatch. A change that resolves express never starts a reviewer pass.
Solo build wakes are consumed; solo builder findings stay queued for coordinator pickup.
Passed reviews start validation, including after zero-step CI startup failures (ci-infra goes to the coordinator). Terminal
reviewers/synthesizers are killed and dequeued; a finished relay = coordinator run (the researcher) is killed and its done: wakes
the coordinator, and that queued done: never kills a later run reusing the window name (#1092); a reflection run's
`done: reflection <window> <url>` puts the report URL on the relayed wake and reaps only the run for that window (#1520); merged PRs are closed out,
and a merge that an open issue's `Depends on` names stays queued so the coordinator dispatches the dependent (#814), as does
one that closes an active milestone's last open item or is a release cut, noted `milestone-complete` (#1559). Progress lines are ignored. Judgement records remain in the queue,
including red CI, changes, stale heads, holds, failed commands, dialogs, blocked runs and owner asks. Red CI for a
superseded head and synthesizer gate-status blocks that only wait (`wait=ci,review,validation,selfgate,train`) are consumed.
A lead's `waiting: #<n> owner|hold|ci id=<id>` line is consumed; the watcher keeps that id off its retries (#1715).
A lead's or gone run's `blocked:` line whose typed items are all closed or merged, or whose pinned head or round is
superseded, is consumed (#1476); an open issue, a current head or an unreadable item keeps it. A dead or missing stale
wake whose run identity an idle reclaim recorded is consumed; a replacement under the same name still wakes (#1552).
Routing is serialized; interrupted batches survive in wake/queue.jsonl.route-* and are retried. Reviewer spawns
are deduplicated by PR/head/pass/round against live and queued runs, section files and pass markers posted by this
runtime's reviewer (its login and signature; #1290); the head-verdict check that gates a reviewer spawn counts only
that reviewer's verdicts too.
Synthesizers remain alive while land requests lack completion or other inbox messages lack acknowledgment, and through
a merged PR's close-out while their own spawn PR lacks completion (its direct-land main CI check, #1339);
the inbox check and reap share the queue lock with send's inbox append.
With the synthesizer lead installed (#1569), `review-approved`, `selfgate-passed`, `ci-passed` with a passing verdict
or self-gate at head, and approved merge-ups become durable `work` events in its land queue, never coordinator
wakes (a merge-up head's `ci-passed` counts its approved previous head, and a head-pinned coordinator `merge-ok`
steer counts as the §7 approval override); a poll `merge-ok-recorded` whose authenticated merge-ok is still at
the live head is forwarded the same way, whatever CI shows, as a reason to re-read gates (#1835); a closed PR or a
merge-ok no longer at head consumes it. A superseded one is dropped, and an
unapproved `ci-passed` is consumed unless held CI refs for that PR
(`ci/<n>-*.json`) still wait on it. Before forwarding, a passing verdict at head from this runtime's reviewer sets
`crew:approved` and drops a superseded `crew:changes`/`crew:in-review`, read back (#1464).
Its waiting gate-status blocks are consumed like a synthesizer's; its other
`blocked:` lines (owner merge-ok, sensitive, holds, `main red`) stay queued for the coordinator; a clean
`train-report` (all landed, `dropped=none stop=none`) is consumed. After its land's close-out, route queues the
away-only Slack `land` message itself and hands `crew:ready` dependents to the builder lead; only dependents that are
not ready still wake the coordinator.
Before any action a record must qualify (#1856): its `context` envelope is closed and names this team and repo
(another project reference resolving to them) and agrees with its refs; without one, a team file's record must come
from a run or lead in this repo's state, and a `done:` completion line must match the run it came from. The item or
change it reads, before any lead handoff, must carry this repo's URL. A refused record
stays queued with its `route_error`. `repo.labels` maps state tags on every label read and write.
A poll `pr-conflicting` at the live head becomes one builder-lead `merge-up` handoff before any CI (#1398); a moved
head or resolved conflict is consumed, and held, escalated, solo or lead-less conflicts stay queued.

Usage: mdstack route --project FILE [--org-profile FILE] [--timeout SECS]
"""
import argparse
import contextlib
import fcntl
import glob
import io
import json
import os
import re
import subprocess
from urllib.parse import quote
from crew_shared import (canonical_labels, commands, crew_render, heartbeat, profile, queue_lock, refuse_paused,
                         require_ownership, ROLES, runs, synthesizer_work, open_trains, tracker_labels, work_context)


# A gate-status block whose only unmet items are pending CI, an in-flight review, validation or express self-gate, or a
# running train.
WAITING = re.compile(r"blocked: #\d+ [0-9a-f]{40} gate-status \S+ wait=(?:ci|review|validation|selfgate|train)"
                     r"(?:,(?:ci|review|validation|selfgate|train))*")
# A reviewer's finished pass; a trailing note after the verdict is allowed (#1343), as on a builder's done line (#695).
# A reflection run's completion with its posted report (templates/policy/researcher/skills/protocol-reflection).
REFLECTION_DONE = re.compile(r"done: reflection (\S+) (https?://\S+)")
# A finished train with every member landed and nothing dropped: a train-report the coordinator need not read.
TRAIN_CLEAN = re.compile(r"train-report n=\d+ members=\S+ landed=\S+ dropped=none stop=none path=\S+")
# A block's typed items: optional handoff IDs or window names, its #refs, then an optional head and round (#1476).
BLOCKED = re.compile(r"blocked: (?:(?:\d{8}T\d{6}Z-[0-9a-f]+|[a-z]+-\d+\S*) )*((?:#\d+ ?)+)"
                     r"(?:([0-9a-f]{40})(?: |$))?(?:r(\d+)\b)?")
LAND_EVENTS = ("review-approved", "selfgate-passed", "ci-passed", "merge-ok-recorded")
# A release cut's CHANGELOG.md patch adds a version section heading (scripts/changelog-cut.py).
RELEASE_HEADING = re.compile(r"^\+## \[\d+\.\d+\.\d+\]", re.M)
REVIEW_DONE = re.compile(r"done: #(\d+) ([0-9a-f]{40}) (review|validate|recheck) (pass|changes|escalate)(?:\s.*)?")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
BUILT = re.compile(r"done: #(\d+) #(\d+) ([0-9a-f]{40})")
ITEM_EVENTS = ("issue-assigned", "builder-queued")  # records whose first ref is an item, not a change
GC_MAX = 5  # removals per backstop wake: mdstack gc's merged-only sweep stays bounded (#316)


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("crew: gh %s: %s" % (" ".join(args[:2]), r.stderr.strip()))
    return json.loads(r.stdout) if "--json" in args else None


def repo_of(url):
    """Canonical owner/name of an https item or change URL; None when unreadable."""
    m = re.fullmatch(r"https://[^/\s]+/([^/\s]+)/([^/\s]+)/(?:pull|issues)/\d+", url) if isinstance(url, str) else None
    return ("%s/%s" % m.groups()).lower() if m else None


def same_repo(values, record, what):
    """An independently read item or change must be in this project's repo (team §9.3): a transferred or redirected
    record, or one without a readable URL, refuses before any claim, spawn or post."""
    found, mine = repo_of(record.get("url")), ("%s/%s" % (values["repo.owner"], values["repo.name"])).lower()
    if found != mine:
        raise RuntimeError("crew: route: refusing: %s reads as repo %s, not %s" % (
            what, found or "unknown (no readable url)", mine))
    return canonical_labels(values, record)


def line_identity(line):
    """The ids a completion status line claims: a builder's `done: #<issue> #<pr> <head>` or a reviewer's
    `done: #<pr> <head> <pass> <verdict>`; {} for any other line."""
    m = BUILT.fullmatch(line)
    if m:
        return {"item": int(m[1]), "change": int(m[2]), "head": m[3]}
    m = REVIEW_DONE.fullmatch(line)
    return {"change": int(m[1]), "head": m[2], "pass": m[3]} if m else {}


def named_ids(w, rec):
    """(ids, source of each, conflict): every work id the record, its completion status line and its run name. The
    record's first ref `#n` is an issue event's item or any other record's change, a full-SHA second ref its head,
    `round` its round; the line names item/change/head (builder) or change/head/pass (reviewer); for a status record
    from it, the run names its item, change and pass, plus head and round for a reviewer (a builder pushes new heads).
    Sources that disagree conflict."""
    ids, source, refs = {}, {}, w.get("refs") or []
    named = []
    if refs and re.fullmatch(r"#\d+", refs[0]):
        change = w.get("event") not in ITEM_EVENTS
        named.append(("change" if change else "item", int(refs[0][1:]), "the record"))
        if change and len(refs) > 1 and FULL_SHA.fullmatch(refs[1]):
            named.append(("head", refs[1], "the record"))
    named.append(("round", w.get("round"), "the record"))
    if w.get("reason") == "status":
        named += [(k, v, "the completion line") for k, v in line_identity(w.get("line", "")).items()]
    if rec is not None and w.get("reason") == "status":  # a result from the run; a handoff to it names only itself
        args = rec.get("args", {})
        run = [("item", args.get("issue")), ("change", rec.get("pr") or args.get("pr")), ("pass", rec.get("pass"))]
        run += [("head", rec.get("head")), ("round", args.get("round"))] if rec["role"] == "reviewer" else []
        named += [(k, v, "run " + w["window"]) for k, v in run]
    for key, value, where in named:
        if value is None:
            continue
        if key in ids and str(ids[key]) != str(value):
            return ids, source, "%s names %s %s, not %s's %s" % (where, key, value, source[key], ids[key])
        ids.setdefault(key, value)
        source.setdefault(key, where)
    return ids, source, None


def qualify(args, values, state, w):
    """Why wake w may not act in this project, or None (team §9.3, #1856). One comparison: a supplied envelope must be
    closed, name this team and repo (another project reference must resolve to them), and carry and equal every work
    id the record, its completion line or its run names (named_ids); a missing or differing id refuses. An id nothing
    names may be absent (a new build has no change or head). A record without an envelope is bound to a run or lead
    record in this repo's state, or the profile is a one-repo config, whose selected state is its only project; in a
    team file every other envelope-less record refuses, and a completion line needs its run or lead even with an
    envelope. A one-repo replay with neither keeps today's recovery after the repo-checked change read."""
    config = crew_render.crew_config
    rec = dict(runs(state)).get(w.get("window"))
    bound = rec or dict(commands()["lead"].records(state)).get(w.get("window"))
    ids, source, conflict = named_ids(w, rec)
    if conflict:
        return conflict
    if "context" in w:
        env = w["context"]
        problem = config.envelope_problem(env, work_context(args.project, values), lambda ref: config.project_identity(ref, args.org_profile))
        if problem:
            return problem
        for key, value in ids.items():
            if env[key] is None:
                return "work envelope lacks the %s %s names" % (key, source[key])
            if str(env[key]) != str(value):
                return "work envelope %s %s is not %s's %s" % (key, env[key], source[key], value)
    elif bound is None and "team.name" in values and w.get("reason") != "backstop":
        return "no work envelope, and no run or lead record in this repo's state (team %s)" % values["team.name"]
    if bound is not None and "context" in bound:
        problem = config.envelope_problem(bound["context"], work_context(args.project, values))
        if problem:
            return problem
    if w.get("reason") == "status" and line_identity(w.get("line", "")) and bound is None and "team.name" in values:
        return "completion line from %s has no run or lead record in this repo's state (team %s)" % (
            w.get("window"), values["team.name"])
    return None


def read_change(values, n):
    """The independent read of change #n, checked against this repo before a lead receives work for it (#1856)."""
    return same_repo(values, gh("pr", "view", str(n), "-R", "%s/%s" % (values["repo.owner"], values["repo.name"]),
                                "--json", "url"), "change #%d" % n)


def invoke(args, cmd, **kw):
    values, _, _ = profile(args)
    if not require_ownership(values):
        raise RuntimeError("crew: ownership changed before " + cmd)
    rc = commands()[cmd].run(argparse.Namespace(project=args.project, org_profile=args.org_profile,
                            timeout=args.timeout, **kw))
    if rc and not (cmd == "send" and rc == 4):
        raise RuntimeError("crew: %s failed (exit %s)" % (cmd, rc))


def markers(text):
    return [dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            for line in re.findall(r"<!-- crew:v1 ([^>]*?) -->", text)]


def open_rereview(pr, head):
    pending = False
    for m in markers("\n".join(r["body"] for r in pr["reviews"])):
        if m.get("sha") == head:
            if m.get("pass") == "steer" and m.get("cmd") == "rereview":
                pending = True
            elif m.get("role") == "reviewer-validator" and m.get("pass") == "verdict":
                pending = False
    return pending


def rereview_id(pr, head):
    if open_rereview(pr, head):
        return next(m.get("cmd-id", "rereview") for m in reversed(markers("\n".join(r["body"] for r in pr["reviews"])))
                    if m.get("sha") == head and m.get("pass") == "steer" and m.get("cmd") == "rereview")
    return None


def own_reviews(values, pr):
    """Reviews this runtime's reviewer posted: its login and its signature (#1290). Another runtime's records on the
    same PR, even under a shared login, never stand in for this runtime's pass."""
    sign = re.compile(r"^— .*\b%s \(" % re.escape(values["identities.reviewer.name"]), re.M)
    return [r for r in pr["reviews"] if (r.get("author") or {}).get("login") == values["identities.reviewer.gh_user"]
            and sign.search(r["body"])]


def own_view(values, pr):
    """The PR with another runtime's reviewer-validator records dropped (#1290), so a foreign verdict never gates
    dispatch or approves a merge-up; builder and coordinator records stay."""
    own = own_reviews(values, pr)
    return dict(pr, reviews=[r for r in pr["reviews"] if any(r is o for o in own) or
                             not any(m.get("role") == "reviewer-validator" for m in markers(r["body"]))])


def merge_up_delta(pr, head, builder):
    """A signed, head-pinned builder fix or merge-up note recording a resolved conflict or differing patch needs
    delta review.

    builder: the builder's display name; the signature may carry any emoji, none, or a team (#431, #1291).
    The published merge-up form (`[Ben/merge-up]`, `pass=merge-up`, "conflicts ... are resolved") counts (#1682)."""
    sign = re.compile(r"^— (?:.* )?%s \(" % re.escape(builder), re.M)
    for review in pr["reviews"]:
        body = review["body"]
        if not re.search(r"^\[[^]\n]+/(?:fix|ci-fix|merge-up)\]", body) or not sign.search(body):
            continue
        if not any(m.get("role") == "builder" and m.get("pass") in ("fix", "ci-fix", "merge-up") and
                   m.get("pr") == str(pr["number"]) and m.get("sha") == head for m in markers(body)):
            continue
        if re.search(r"(?<!no )\b(?:resolved|fixed|resolving)\b[^\n]*\bconflicts?\b|"
                     r"(?<!no )\bconflicts?\b[^\n.]*\b(?:resolved|fixed)\b|"
                     r"(?<!no )(?<!without a )\bdiffering patch\b", body, re.I):
            return True
    return False


def reconcile_approval(values, repo, pr, own):
    """This runtime's reviewer's passing verdict at head supersedes an earlier changes round (#1464): set
    crew:approved, drop crew:changes and crew:in-review, and read the tags back before land work is forwarded. An open
    rereview at head or a later formal changes request leaves the tags for the gate."""
    head = pr["headRefOid"]
    if commands()["poll"].pr_snapshot(own)["verdict"] != "pass" or open_rereview(own, head):  # a foreign verdict
        return  # never settles a rereview (#1290)
    last = max(i for i, r in enumerate(own["reviews"]) for m in markers(r["body"])
               if m.get("role") == "reviewer-validator" and m.get("pass") == "verdict" and m.get("sha") == head)
    if any(r.get("state") == "CHANGES_REQUESTED" and (r.get("author") or {}).get("login") ==
           values["identities.reviewer.gh_user"] for r in own["reviews"][last + 1:]):
        return
    stale = {"crew:changes", "crew:in-review"}
    labels = {label["name"] for label in pr["labels"]}
    if "crew:approved" in labels and not labels & stale:
        return
    tag = tracker_labels(values)
    gh("pr", "edit", str(pr["number"]), "-R", repo, "--add-label", tag["crew:approved"],
       *[a for label in sorted(labels & stale) for a in ("--remove-label", tag[label])])
    back = {label["name"] for label in canonical_labels(values, gh("pr", "view", str(pr["number"]), "-R", repo,
                                                                     "--json", "labels"))["labels"]}
    if "crew:approved" not in back or back & stale:
        raise RuntimeError("crew: #%d tag readback after approval: %s" % (pr["number"], ",".join(sorted(back))))


def approved_merge_up(pr, repo, default_branch):
    # Use live verdict history: poll may already have stored the new head as its baseline.
    for m in reversed(markers("\n".join(r["body"] for r in pr["reviews"]))):
        if m.get("role") == "reviewer-validator" and m.get("pass") == "verdict":
            return commands()["poll"].merge_up(pr, {"head": m.get("sha")}, repo, default_branch)
    return None


def scheduler(args, **kw):
    return argparse.Namespace(project=args.project, org_profile=args.org_profile, pool="reviewer", **kw)


def granted(a, ref, kind, round_):
    """Whether admit action `a` grants this pass: its ref, and for a team grant its pass and round too (team §9.3)."""
    return a["ref"] == ref and (a.get("repo") is None or (a.get("kind") == kind and a.get("round") in (None, round_)))


def admit(args, ref, kind, round_):
    """The reviewer lead starts a pass only when `mdstack schedule decide --pool reviewer` grants it."""
    out = commands()["schedule"].schedule_decide(scheduler(args))
    if not any(granted(a, ref, kind, round_) for a in out["admit"]):
        why = next((a["reasons"][0] for a in out["deferred"] if a["ref"] in (ref, None)), "not-granted")
        raise RuntimeError("crew: reviewer admission deferred: %s %s" % (ref, why))


def review(args, state, pr, head, pass_, round_):
    if commands()["poll"].express_lane(args, profile(args)[0], pr):  # the self-gate replaces review (express-lane.md)
        print("crew: route: #%d resolves express; the reviewer pool skips it" % pr["number"])
        return
    steer = rereview_id(pr, head)
    for name, rec in list(runs(state)):
        if rec["role"] == "reviewer" and rec.get("args", {}).get("pr") == pr["number"] and \
                rec.get("head", head if head[:7] in rec.get("claim", "") else None) != head:
            reap(args, name)
            continue
        if rec["role"] == "reviewer" and rec.get("args", {}).get("pr") == pr["number"] and \
                rec.get("head", head if head[:7] in rec.get("claim", "") else None) == head and \
                rec["pass"] == pass_ and rec.get("args", {}).get("round") == round_:
            if getattr(args, "reviewer_lead", False) and steer and rec.get("rereview_id") != steer:
                raise RuntimeError("crew: reviewer still finishing before rereview " + steer)
            return
    path = os.path.join(state, "spawn-queue.jsonl")
    if os.path.exists(path):
        with open(path) as f:
            if any(e.get("pr") == pr["number"] and e.get("head") == head and e["pass"] == pass_ and
                   e["round"] == round_ for e in (json.loads(line) for line in f if line.strip())):
                return
    own = own_reviews(profile(args)[0], pr)
    posted = [(r in own, m) for r in pr["reviews"] for m in markers(r["body"])]
    pending = open_rereview(pr, head)
    if pending:
        for i in range(len(posted) - 1, -1, -1):
            m = posted[i][1]
            if m.get("sha") == head and m.get("pass") == "steer" and m.get("cmd") == "rereview":
                posted = posted[i + 1:]
                break
    posted = [m for mine, m in posted if mine]
    section = os.path.join(state, "verdicts", "pr%d-%s-r%d-%s.md" % (pr["number"], head[:7], round_, pass_))
    if os.path.exists(section) and not pending:
        with open(section) as f:
            posted += markers(f.read())
    if any(m.get("role") == "reviewer-validator" and m.get("pr") == str(pr["number"]) and
           m.get("sha") == head and
           m.get("round") == str(round_) and m.get("pass") in (pass_, "verdict") for m in posted):
        return
    lead = getattr(args, "reviewer_lead", False)
    if lead:
        admit(args, "#%d" % pr["number"], pass_, round_)
    try:
        invoke(args, "spawn", role="reviewer", issue=None, pr=pr["number"], pass_=pass_, round=round_,
               tier=None, head=head, rereview_id=steer if lead else None)
    except RuntimeError:
        if lead:
            commands()["schedule"].schedule_release(scheduler(args, refs=["#%d" % pr["number"]], kind=pass_, round=round_))
        raise


def reap(args, name, state=None, dequeue=True):
    _, _, pool_state = profile(args)
    role = dict(runs(pool_state))[name]["role"]
    retained = {}
    if state:
        rec = dict(runs(state))[name]
        own = rec.get("verdict")
        for path in [own, own.replace("validate.md", "review.md") if own else None,
                     own.replace("validate.md", "verdict.md") if own else None]:
            if path and os.path.exists(path):
                with open(path) as f:
                    retained[path] = f.read()
    invoke(args, "kill", window=name, discard=False, reason=None)
    for path, text in retained.items():
        with open(path, "w") as f:
            f.write(text)
    if dequeue and not commands()["lead"].enabled(pool_state, role):
        invoke(args, "dequeue")


def pending_inbox(state, name, done):
    return bool(synthesizer_work(state, name, done))


def synthesizer_busy(state, name, done=""):
    return pending_inbox(state, name, done) or bool(open_trains(state)) or commands()["land-lock"].held(state)


def land_open(state, name, n):
    """The synthesizer's spawn PR #n has no `done:`/`blocked:` line yet: a direct land waits for main CI (#1339)."""
    status = os.path.join(state, "status", name + ".status")
    lines = []
    if os.path.exists(status):
        with open(status) as f:
            lines = [line.split() for line in f]
    ref = "#%d" % n
    return not any(w[:2] in (["done:", ref], ["blocked:", ref]) or w[:5] == ["blocked:", "main", "red", "after", ref]
                   for w in lines)


def branch_retained(values, pr, default):
    """Why a PR's head branch must not be deleted (fork, default or base branch), or None when it may be."""
    if pr.get("isCrossRepository") is not False or \
            (pr.get("headRepositoryOwner") or {}).get("login") != values["repo.owner"] or \
            (pr.get("headRepository") or {}).get("name") != values["repo.name"]:
        return "fork"  # an unreadable head repository counts as a fork: never deleted
    if not pr.get("headRefName") or pr["headRefName"] in (default, pr.get("baseRefName")):
        return "default or base branch"
    return None


def close_out(args, values, state, pr):
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    labels, tag = {label["name"] for label in pr["labels"]}, tracker_labels(values)
    for label in ("crew:approved", "crew:hold", "crew:in-review", "crew:changes"):
        if label in labels:
            gh("pr", "edit", str(pr["number"]), "-R", repo, "--remove-label", tag[label])
    issues = {i["number"] for i in pr["closingIssuesReferences"]}
    for n in sorted(issues):
        issue = canonical_labels(values, gh("issue", "view", str(n), "-R", repo, "--json", "labels,state,stateReason"))
        if any(label["name"] == "crew:ready" for label in issue["labels"]):
            gh("issue", "edit", str(n), "-R", repo, "--remove-label", tag["crew:ready"])
        # GitHub's auto-close can miss (train lands, #846); a reopened issue stays open on purpose (#917)
        if issue["state"] == "OPEN" and issue.get("stateReason") != "REOPENED":
            gh("issue", "close", str(n), "-R", repo, "--comment",
               "[%s/close-out] #%d merged and closes this issue, but GitHub left it open; closed by close-out." % (
                   values.get("identities.coordinator.name", "Ash"), pr["number"]))
    default = gh("repo", "view", repo, "--json", "defaultBranchRef")["defaultBranchRef"]["name"]
    branch = pr["headRefName"]
    if not branch_retained(values, pr, default):
        ref = "repos/%s/git/refs/heads/%s" % (repo, quote(branch, safe="/"))
        r = subprocess.run(["gh", "api", ref], capture_output=True, text=True)
        if r.returncode and "404" not in r.stderr:
            raise RuntimeError("crew: branch lookup: " + r.stderr.strip())
        if not r.returncode:  # fallback (#395): the land deletes an eligible branch; this one was left
            gh("api", "-X", "DELETE", ref)
    else:
        print("crew: close-out #%d: branch retained (%s)" % (pr["number"], branch_retained(values, pr, default)))
    for name, rec in list(runs(state)):
        item = rec.get("args", {})
        done = heartbeat(state, name)[0].split()
        if item.get("pr") == pr["number"] or item.get("issue") in issues or \
                (rec["role"] == "builder" and done[:1] == ["done:"] and
                 len(done) > 2 and done[2] == "#%d" % pr["number"]):
            if rec["role"] == "synthesizer":
                with queue_lock(state):
                    if not synthesizer_busy(state, name) and \
                            not (item.get("pr") == pr["number"] and land_open(state, name, pr["number"])):
                        reap(args, name, dequeue=False)
                invoke(args, "dequeue")
            else:
                reap(args, name)


def dependents(repo, pr):
    """Open issues whose `Depends on` block names the merged PR or an issue it closes (#814)."""
    refs = {pr["number"]} | {i["number"] for i in pr["closingIssuesReferences"]}
    issues = gh("issue", "list", "-R", repo, "--state", "open", "--limit", "1000", "--json", "number,body")
    return sorted(i["number"] for i in issues
                  if refs & {int(n) for block in commands()["schedule"].DEPENDS.findall(i["body"] or "")
                             for n in re.findall(r"#(\d+)", block)})


def ready(values, repo, n):
    return any(label["name"] == "crew:ready" for label in
               canonical_labels(values, gh("issue", "view", str(n), "-R", repo, "--json", "labels"))["labels"])


def notify_land(args, state, repo, pr):
    """The away-only Slack `land` message the coordinator used to queue after close-out (#1569); the merge post is
    its GitHub record, and notify dedupes by away entry, kind and id."""
    trains = []
    for path in sorted(glob.glob(os.path.join(state, "trains", "train-*.json"))):
        with open(path) as f:
            rec = json.load(f)
        if any(m["pr"] == pr["number"] for m in rec.get("landed", [])):
            trains.append(rec["n"])
    event = dict(id="land-%d" % pr["number"], kind="land", url="https://github.com/%s/pull/%d" % (repo, pr["number"]),
                 title=pr.get("title") or "#%d" % pr["number"], train=str(trains[-1]) if trains else "direct",
                 milestone=(pr.get("milestone") or {}).get("title") or "None")
    path = os.path.join(state, "wake", "land-%d.json" % pr["number"])
    with open(path, "w") as f:
        json.dump(event, f)
    invoke(args, "notify", event_file=path, flush=False, status=False)


def milestone_complete(repo, pr):
    """The merge closes the last open item of an active milestone, or is a release cut whose diff adds a CHANGELOG.md
    version heading (#1559): the coordinator closes the milestone and admits the next one."""
    def api(path):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("crew: gh api %s: %s" % (path, r.stderr.strip()))
        return json.loads(r.stdout)
    for f in api("repos/%s/pulls/%d/files?per_page=100" % (repo, pr["number"])):
        if f["filename"] == "CHANGELOG.md" and RELEASE_HEADING.search(f.get("patch", "")):
            return True
    for n in sorted({i["number"] for i in pr["closingIssuesReferences"]}):
        milestone = gh("issue", "view", str(n), "-R", repo, "--json", "milestone").get("milestone")
        if milestone:
            m = api("repos/%s/milestones/%d" % (repo, milestone["number"]))
            if m.get("state") == "open" and m.get("open_issues") == 0:
                return True
    return False


def conflict(args, values, state, w):
    """A poll `pr-conflicting` wake (#1398): GitHub runs no PR CI on a conflicting head, so the builder lead gets one
    merge-up handoff now. A closed PR, moved head or resolved conflict is consumed (a new conflict polls again); held,
    escalated, draft, still-UNKNOWN, solo or lead-less work stays queued for the coordinator."""
    lead, n, head = commands()["lead"], int(w["refs"][0].lstrip("#")), w["refs"][1]
    pr = same_repo(values, gh("pr", "view", str(n), "-R", "%s/%s" % (values["repo.owner"], values["repo.name"]),
                              "--json", "state,headRefOid,isDraft,labels,mergeable,url"), "change #%d" % n)
    if pr["state"] != "OPEN" or pr["headRefOid"] != head or pr["mergeable"] == "MERGEABLE":
        return True
    if pr["mergeable"] != "CONFLICTING" or pr["isDraft"] or \
            {label["name"] for label in pr["labels"]} & {"crew:escalated", "crew:hold"}:
        return False
    if not lead.enabled(state, "builder") or lead.solo(values, pr=n):
        w["consumer"] = "coordinator"  # solo: the owner's session takes the merge-up through the coordinator
        return False
    return lead.handoff(args, "builder", "merge-up", ["#%d" % n, head]) in (0, 4)


def reclaimed(state, w):
    """A dead or missing stale wake for the very run an idle reclaim removed (#1552); a replacement run under the same
    window name has another identity and still wakes."""
    if w.get("reason") != "stale" or w.get("liveness") not in ("dead", "missing") or not w.get("run"):
        return False
    for path in glob.glob(os.path.join(state, "retained", "builders", w["window"] + "-*", "run.json")):
        with open(path) as f:
            rec = json.load(f)
        if rec.get("window") == w["window"] and rec.get("run") == w["run"]:
            return True
    return False


def obsolete_block(values, line):
    """A `blocked:` line whose every typed item is terminal or a PR whose pinned head or round is superseded (#1476):
    `blocked: [<handoff-id>|<window>...] #n... [<sha>] [r<k>] ...`. An open issue, an untyped line or an unreadable
    item keeps it."""
    m = BLOCKED.match(line)
    if not m:
        return False
    refs, head, round_ = [int(n) for n in re.findall(r"\d+", m[1])], m[2], m[3]
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    items = {}
    for n in refs:
        r = subprocess.run(["gh", "api", "repos/%s/issues/%d" % (repo, n)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("crew: gh api issue #%d: %s" % (n, r.stderr.strip()))
        items[n] = json.loads(r.stdout)
    for n, item in items.items():
        if item.get("state") == "closed":
            continue
        if not head or "pull_request" not in item:
            return False
        pr = gh("pr", "view", str(n), "-R", repo, "--json", "state,headRefOid,reviews")
        if pr["state"] != "OPEN" or pr["headRefOid"] != head:
            continue
        verdicts = [int(v["round"]) for v in markers("\n".join(r["body"] for r in own_reviews(values, pr)))
                    if v.get("role") == "reviewer-validator" and v.get("pass") == "verdict" and v.get("sha") == head
                    and v.get("round", "").isdigit()]
        if not (round_ and verdicts and max(verdicts) > int(round_)):
            return False
    return bool(items)


def backstop_gc(args, state):
    """Merged run copies a missed close-out left behind (#316). The sweep's report goes to <state>/gc/backstop.txt,
    not the watcher's output; only a failure prints one line naming it, and nothing here is fatal to routing."""
    path = os.path.join(state, "gc", "backstop.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out, error = io.StringIO(), None
    try:
        with contextlib.redirect_stdout(out):
            invoke(args, "gc", apply=True, max=GC_MAX)
    except RuntimeError as e:
        error = str(e)
    with open(path, "w") as f:
        f.write(out.getvalue() + ("%s\n" % error if error else ""))
    if error:
        print("crew: route: backstop gc: %s; report in %s" % (error, path))


def route_record(args, values, state, w):
    line = w.get("line", "")
    problem = qualify(args, values, state, w)
    if problem:  # refused before any claim, spawn, post or reap; the record stays queued for the coordinator
        raise RuntimeError("crew: route: refusing %s: %s" % (w.get("event") or w.get("reason") or "record", problem))
    if reclaimed(state, w):
        print("crew: route: %s was reclaimed idle; its stale wake is consumed" % w["window"])
        return True
    if w.get("reason") == "status" and line.startswith(("ack:", "heartbeat:")):
        if line.startswith("ack:"):
            rec = dict(runs(state)).get(w.get("window"))
            if rec and rec["role"] == "synthesizer":
                with queue_lock(state):
                    synthesizer_work(state, w["window"])
        return True
    event = w.get("event")
    if event == "ci-failed" and len(w.get("refs", [])) < 2:
        return False  # a source's narrative wake has no PR/head to classify
    rec = dict(runs(state)).get(w.get("window"))
    lead = commands()["lead"]
    leader = dict(lead.records(state)).get(w.get("window"))
    if leader and w.get("reason") == "status" and line.startswith(("done:", "deferred:", "waiting:")):
        return True
    if w.get("reason") == "status" and rec is None and obsolete_block(values, line):
        print("crew: route: %s: terminal or superseded item; consumed" % line[:60])
        return True  # a lead's or a gone run's block; a live worker's block still reaches the coordinator
    if (rec and rec["role"] == "synthesizer" or leader and leader["role"] == "synthesizer-lead") and \
            WAITING.fullmatch(line):
        return True  # recorded in the status file and gate-status review; CI or a pass will wake it again (#578)
    if leader and leader["role"] == "synthesizer-lead" and TRAIN_CLEAN.fullmatch(line):
        return True  # every member landed and none dropped: nothing for the coordinator (#1569)
    if w.get("reason") == "lead-backstop":
        lead.retry_pending(args, w["window"], recheck=w.get("event") != "admission recheck",
                           admission=w.get("event") == "admission recheck")
        return True
    if w.get("reason") == "idle-builder":
        if lead.enabled(state, "builder"):
            return lead.event(args, "builder", w) == 0
        invoke(args, "dequeue", idle_only=True)
        return True
    if w.get("reason") == "backstop":
        lead.retry_pending(args)
        backstop_gc(args, state)
    if rec and ROLES.get(rec["role"], {}).get("relay") == "coordinator" and line.startswith(("done:", "failed:")):
        run = commands()["watch"].run_identity(rec)
        report, mode = REFLECTION_DONE.fullmatch(line), rec.get("args", {}).get("reflection")
        if report:
            w["report"] = report.group(2)  # the coordinator relays the posted report
        if w.get("run", run) == run and not (mode and report and report.group(1) != mode["window"]):
            reap(args, w["window"])  # one fresh session per request; the result is on the item (#584)
        # else a queued wake of an earlier run: a respawn under the same name stays alive (#1092)
        return False  # the coordinator relays the result
    if rec and line.startswith("done:") and not getattr(args, "reviewer_lead", False):
        lead.retry_pending(args)
    if leader and w.get("reason") == "stale":
        return w.get("liveness") in ("dead", "missing") and lead.ensure(args, leader["role"].removesuffix("-lead")) == 0
    if event == "pr-conflicting":
        return conflict(args, values, state, w)
    pool = "builder" if event in ("issue-assigned", "builder-message", "builder-queued") else rec.get("role") if rec else None
    if event in ("issue-assigned", "builder-message"):
        n = int(w["refs"][0].lstrip("#"))
        kind = "issue" if event == "issue-assigned" else "pr"
        same_repo(values, gh(kind, "view", str(n), "-R", "%s/%s" % (values["repo.owner"], values["repo.name"]),
                             "--json", "url"), "%s #%d" % (kind, n))
        if lead.solo(values, **{"issue" if event == "issue-assigned" else "pr": n}):
            if event == "issue-assigned":
                return True
            w["consumer"] = "coordinator"
            return False
    if lead.enabled(state, pool) and (event in ("issue-assigned", "builder-message", "builder-queued") or w.get("reason") in ("stale", "dialog", "quota", "delivery")):
        return lead.event(args, pool, w) == 0
    if event == "pr-closed" and lead.enabled(state, "reviewer"):
        read_change(values, int(w["refs"][0].lstrip("#")))
        lead.event(args, "reviewer", w)
    reviewer_event = event in ("new-head", "fix-at-head") or \
        REVIEW_DONE.fullmatch(line)
    if not getattr(args, "reviewer_lead", False) and lead.enabled(state, "reviewer") and reviewer_event:
        read_change(values, int(REVIEW_DONE.fullmatch(line)[1]) if REVIEW_DONE.fullmatch(line) else
                    int(w["refs"][0].lstrip("#")))
        if rec and rec["role"] == "reviewer":
            w = dict(w, round=rec["args"]["round"])
        return lead.event(args, "reviewer", w) == 0
    if event == "builder-queued":
        return True
    built = BUILT.fullmatch(line)
    done = REVIEW_DONE.fullmatch(line)
    if done and done[4] in ("pass", "escalate") and rec is None and not getattr(args, "reviewer_lead", False):
        return True
    terminal = line.startswith("done:") and rec and rec["role"] in ("reviewer", "synthesizer")
    landing = event in LAND_EVENTS and lead.enabled(state, "synthesizer")
    if event not in ("new-head", "merge-up", "pr-merged", "pr-closed", "builder-message", "fix-at-head", "ci-failed") and not terminal and not built and not done and not landing:
        return False
    if built:
        n, head = int(built[2]), built[3]
    elif terminal or done:
        stale = not done and " stale" in line  # a verdict's note may say "stale"
        if stale and rec and rec["role"] == "reviewer":
            pr = gh("pr", "view", str(rec["args"]["pr"]), "-R", "%s/%s" % (values["repo.owner"], values["repo.name"]),
                    "--json", "state")
            if pr["state"] != "OPEN":  # merged or closed by anyone, another runtime included: free the slot (#811)
                reap(args, w["window"], state)
                return True
        if rec and rec["role"] == "synthesizer":  # its `done: <refs> stale` closes a land request too (#1187)
            with queue_lock(state):
                if not synthesizer_busy(state, w["window"], line):
                    reap(args, w["window"], dequeue=False)
            invoke(args, "dequeue")
            return True
        if stale or (rec and rec["role"] == "reviewer" and not done):
            return False
        n, head = int(done[1]), done[2]
    else:
        n, head = int(w["refs"][0].lstrip("#")), w["refs"][1]
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    fields = "number,state,headRefOid,isDraft,labels,reviews,statusCheckRollup,headRefName,baseRefName," \
             "headRepositoryOwner,headRepository,isCrossRepository,closingIssuesReferences,title,milestone,url"
    pr = same_repo(values, gh("pr", "view", str(n), "-R", repo, "--json", fields), "change #%d" % n)
    if event in ("pr-merged", "pr-closed"):
        if pr["state"] != ("MERGED" if event == "pr-merged" else "CLOSED"):
            return False
        if event == "pr-merged":
            close_out(args, values, state, pr)
            landed = lead.enabled(state, "synthesizer")  # its lead's lands need no coordinator turn (#1569)
            if values["backends.owner-channel.name"] == "slack":
                if not landed:
                    return False  # The coordinator records the away land notification after cleanup.
                notify_land(args, state, repo, pr)
            waiting, complete = dependents(repo, pr), milestone_complete(repo, pr)
            if waiting and landed and lead.enabled(state, "builder"):
                for d in [d for d in waiting if ready(values, repo, d)]:
                    if lead.handoff(args, "builder", "build", ["#%d" % d]) not in (0, 4):
                        raise RuntimeError("crew: builder lead handoff failed for dependent #%d" % d)
                    waiting.remove(d)
            if waiting:
                w["dependents"] = ["#%d" % n for n in waiting]  # dispatched now, not at the backstop (#814)
            if complete:
                w["note"] = "milestone-complete"  # close the milestone and admit the next one (#1559)
            if waiting or complete:
                w["consumer"] = "coordinator"
                return False
        else:
            issues = {i["number"] for i in pr["closingIssuesReferences"]}
            for name, run in list(runs(state)):
                if run["role"] == "builder" and (run.get("pr") == n or run["args"].get("pr") == n or
                                                run["args"].get("issue") in issues):
                    reap(args, name)
        return True
    if (event == "ci-failed" or landing) and pr["state"] == "OPEN" and pr["headRefOid"] != head:
        return True  # superseded head: its new head gets its own CI (#578) and its own land event (#1569)
    if landing and event == "merge-ok-recorded" and pr["state"] != "OPEN":
        return True  # a merged or closed PR needs no land: its close-out has its own event (#1835)
    labels = {label["name"] for label in pr["labels"]}
    if pr["state"] != "OPEN" or pr["headRefOid"] != head or pr["isDraft"] or labels & {"crew:escalated", "crew:hold"}:
        if terminal:  # a finished reviewer frees its slot, keeping its verdict files, even when its PR moved on (#719)
            reap(args, w["window"], state)
        return False
    if landing:
        own = own_view(values, pr)
        snapshot = commands()["poll"].pr_snapshot(own)
        merge_ok = any(m.get("role") == "coordinator" and m.get("pass") == "steer" and m.get("cmd") == "merge-ok" and
                       m.get("sha") == head for m in markers("\n".join(r["body"] for r in pr["reviews"])))
        if event == "ci-passed" and "pass" not in (snapshot["verdict"], snapshot["selfgate"]) and not merge_ok and \
                not approved_merge_up(own, repo, values["repo.default_branch"]) and \
                not commands()["poll"].express_lane(args, values, pr):  # poll gates an express ci-passed already
            return not glob.glob(os.path.join(state, "ci", "%d-*.json" % n))  # held CI refs: the coordinator drops them
        if event == "merge-ok-recorded" and not commands()["poll"].merge_ok_identity(pr, values):
            return True  # no authenticated merge-ok at the live head any more: nothing to re-check (#1835)
        reconcile_approval(values, repo, pr, own)
        return lead.event(args, "synthesizer", w) == 0
    delta = merge_up_delta(pr, head, values["identities.builder.name"])
    if event == "merge-up" and (open_rereview(pr, head) or delta) and lead.enabled(state, "reviewer") and not getattr(args, "reviewer_lead", False):
        return lead.event(args, "reviewer", w) == 0
    if built and lead.enabled(state, "reviewer") and not getattr(args, "reviewer_lead", False):
        return lead.event(args, "reviewer", w) == 0
    if event == "ci-failed":
        if commands()["poll"].ci_state(pr, repo) == "infra":
            w.update(event="ci-infra", consumer="coordinator")
        return False
    if event == "builder-message":
        issue = int(w["window"].rsplit("-", 1)[1])
        if issue not in {i["number"] for i in pr["closingIssuesReferences"]}:
            return False
        if w["window"] not in dict(runs(state)):
            queued = os.path.join(state, "spawn-queue.jsonl")
            if os.path.exists(queued):
                with open(queued) as f:
                    entries = [json.loads(line) for line in f if line.strip()]
                for entry in entries:
                    if entry.get("role") == "builder" and entry.get("issue") == issue:
                        messages = entry.setdefault("messages", [])
                        if not any(m["id"] == w["id"] for m in messages):
                            messages.append(w)
                        with open(queued, "w") as f:
                            f.writelines(json.dumps(e) + "\n" for e in entries)
                        return True
            invoke(args, "spawn", role="builder", issue=issue, pr=n, pass_="fix", round=w.get("round", 1),
                   tier=None, head=head, messages=[w], wake=False)
        if w["window"] not in dict(runs(state)):
            return True  # capped spawn carries the message until dequeue
        invoke(args, "send", window=w["window"], kind=w["kind"], refs=w["refs"], wait_ack=None,
               context=w.get("context"))  # the original envelope travels on, re-checked by send
        return True
    if built:
        if rec and rec["role"] == "builder":
            rec["pr"] = n
            with open(os.path.join(state, "runs", w["window"] + ".json"), "w") as f:
                json.dump(rec, f, indent=2)
        own = own_view(values, pr)
        snapshot = commands()["poll"].pr_snapshot(own, values=values)
        pending = open_rereview(pr, head)
        if not pending and not delta and approved_merge_up(own, repo, values["repo.default_branch"]):
            return True
        if pending or delta or snapshot["verdict"] is None or snapshot["fixed"]:
            review(args, state, pr, head, "review", snapshot["round"])
        return True
    if done and done[4] == "changes":
        if rec:
            reap(args, w["window"], state)
        return False  # findings stay queued, with their section files retained for the builder
    round_ = rec["args"]["round"] if rec else w.get("round", commands()["poll"].pr_snapshot(own_view(values, pr), values=values)["round"])
    if terminal and done and getattr(args, "reviewer_lead", False):
        steer = rereview_id(pr, head)
        if steer and rec.get("rereview_id") != steer:
            reap(args, w["window"], state)
            review(args, state, pr, head, "review", round_)
            return True
        reap(args, w["window"], state)
        terminal = False
    if done and done[3] == "recheck" and done[4] == "escalate":
        review(args, state, pr, head, "review", round_)
    elif done and done[3] == "review":
        if commands()["poll"].ci_state(pr, repo) == "failed":
            return False
        review(args, state, pr, head, "validate", round_)
    elif event in ("new-head", "merge-up", "fix-at-head"):
        if event == "merge-up" and not open_rereview(pr, head) and not delta:
            return lead.enabled(state, "synthesizer") and lead.event(args, "synthesizer", w) == 0
        snapshot = commands()["poll"].pr_snapshot(own_view(values, pr))
        if event != "merge-up" and snapshot["verdict"] and not snapshot["fixed"] and not open_rereview(pr, head):
            return True  # this head already has the newest round's verdict: a replayed event opens no round (#1124)
        review(args, state, pr, head, "review", w["round"])
    if terminal:
        reap(args, w["window"], state)
    return True


def route_queue(args):
    values, _, state = profile(args)
    wake = os.path.join(state, "wake")
    os.makedirs(wake, exist_ok=True)
    with open(os.path.join(wake, "route.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not require_ownership(values) or refuse_paused(state, "route"):  # a paused project keeps its queue (#1714)
            return 1
        queue = os.path.join(wake, "queue.jsonl")
        with queue_lock(state):
            if os.path.exists(queue):
                os.rename(queue, queue + ".route-" + os.urandom(6).hex())
        for path in sorted(glob.glob(queue + ".route-*"), key=os.path.getmtime):
            with open(path) as f:
                records = [json.loads(line) for line in f if line.strip()]
            for w in records:
                try:
                    consumed = route_record(args, values, state, w)
                except (RuntimeError, OSError) as e:
                    consumed = False
                    w = dict(w, route_error=str(e))
                if not consumed:
                    with queue_lock(state), open(queue, "a") as f:
                        f.write(json.dumps(w) + "\n")
            os.remove(path)
        spawn_queue = os.path.join(state, "spawn-queue.jsonl")
        if os.path.exists(spawn_queue) and os.path.getsize(spawn_queue):
            invoke(args, "dequeue", role="builder")
        with queue_lock(state):
            return int(os.path.exists(queue) and os.path.getsize(queue) > 0)


def register(sub):
    p = sub.add_parser("route")
    p.add_argument("--project")
    p.add_argument("--org-profile")
    p.add_argument("--timeout", type=float, default=15, help="spawn timeout in seconds")


def run(args):
    pending = route_queue(args)
    print("crew: route: %s" % ("judgement records remain" if pending else "mechanical wakes consumed"))
    return 0
