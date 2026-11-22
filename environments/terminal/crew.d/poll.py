"""`mdstack poll` turns GitHub state changes into one-consumer wake records in `wake/queue.jsonl` (`new-head` and the
evidence-only `fix-at-head` carry the round `k`; approved default-branch merges emit `merge-up` with the previous
head and approval round). Queued ci-failed records for a superseded head are dropped. Failed Actions jobs with zero
steps emit ci-infra to the coordinator, never ci-passed; so does a head missing an expected check named in
`[ci] required_checks`, which stays pending (#1536). Non-active ownership emits one coordinator ownership wake per
mode change and no work events; `lost` (another runtime owns, after the ack) is the prompt-stop wake. A transient `gh` failure (5xx, timeout, connection reset) is retried with bounded
backoff; if it persists, `--once` exits 75 (EX_TEMPFAIL) so `mdstack watch` records an incident instead of waking (#702).
A rate-limited `gh` read is never retried: `--once` exits 75 with `rate-limited until <UTC>`, the reset from `gh api
rate_limit` (60 s for a secondary limit), and `mdstack watch` holds its sources until then (#1300).
A change that resolves express (express-lane.md, routing) emits no reviewer event; `ci-passed` needs a selfgate pass at
head (or carried by an express merge-up atop a selfgate-passed head) and a new selfgate pass with CI green emits
`selfgate-passed`, all to the synthesizer. When the lane falls back, the head emits `new-head` for normal review.
With `triage.enabled`, each poll also runs the zero-model triage scan (triage.md, #747): unplaced issues, owner
replies to triage records and owner feedback on them (placed or not, relayed decisions included, #835) in each
`triage.repos` tracker go to `triage/queue.json` with exact-key duplicate hints,
intake-card fields and P0 signals; a newly seen P0 candidate without a triage record queues one `triage-p0` wake for
the coordinator; owner feedback on a recorded P0 item queues the item but no wake (#1093). The
scan also lists the project repo's milestones closed since its baseline under `milestones` until a sweep takes them
(milestone-close sweep, triage.md T6, #374). A non-GitHub tracker backend is read through its `tracker.list-items`
binding, once per `triage.trackers` id (`<tracker>`), and has no milestone list. `--triage-only` runs one triage scan
and nothing else, on a tmux or session profile, so a hosted routine can refresh the queue before a sweep (#1404).
An open crew PR whose head turns `CONFLICTING` (UNKNOWN is no conflict) emits one `pr-conflicting` per head and
conflict, so route hands the builder a merge-up without waiting for CI GitHub never runs on it (#1398).
Each crew PR whose ready sample (head, CI, verdict, mergeable, hold) changed is one line in
`metrics/observations.jsonl` with the poll's time and the previous poll's, its sampling bound (self-improve.md, #1524).
`poll-state.json`'s `held` lists the refs parked on the owner: open crew PRs and crew:ready issues labelled
crew:hold, crew:escalated or crew:needs-md, and the issues such a PR closes; `mdstack watch` backs off for them, and
open refs that leave it are one `hold-released` record for the coordinator; for held refs and refs with an open
`asks/<n>.json` only, a changed count of owner comments (and PR reviews) is one `owner-answer` record for the
coordinator while the hold and the ask stay (#394).
A new authenticated coordinator `pass=steer cmd=merge-ok` record at an open crew PR's current head is one
`merge-ok-recorded` record for the synthesizer, even after CI went green; a duplicate, another head or author, or an
unsigned marker is none, and a legacy poll-state entry seeds it quietly (#1835).

Every wake record carries the closed `context` work envelope (team, project, repo, item, change, head, pass, round;
`null` when absent), and `repo.labels` maps this project's tracker labels to state tags on read (#1856).

Usage: mdstack poll [--once | --triage-only] --project FILE
"""
import functools
import json
import os
import re
import subprocess
import time
import tomllib
import shlex
from crew_shared import (canonical_labels, commands, crew_render, ownership_module, profile, queue_lock, ROLES, ROOT,
                         tracker_labels, work_context)


# mdstack poll (tmux.md Q1, C2): one wake source. Read-only gh JSON for open crew PRs and crew:ready items is diffed
# against poll-state.json; each change becomes one wake record in wake/queue.jsonl naming one consuming role
# (protocol §8). The coordinator drains the queue and routes each record by mdstack send or mdstack spawn.
CONSUMER = {event: role for role, data in ROLES.items() for event in data["events"]["tmux"]}
PR_FIELDS = "number,state,headRefOid,labels,statusCheckRollup,reviews,closingIssuesReferences"
HOLDS = {"crew:hold", "crew:escalated"}  # a known hold: an approved, green, mergeable PR is still not ready (#1524)
OWNER_BLOCKED = HOLDS | {"crew:needs-md"}  # nothing moves until the owner answers (#394)
CREW_LINE = re.compile(r"<!-- crew:v1 ([^>]*?) -->")
CI_OK, CI_BAD = {"SUCCESS", "NEUTRAL", "SKIPPED"}, {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
                                                    "STARTUP_FAILURE"}
TRANSIENT_GH = re.compile(r"HTTP 5\d\d|time(d ?)?out|connection reset|unexpected EOF|TLS handshake", re.IGNORECASE)
RETRY_DELAYS = (1, 2, 4)  # seconds between poll's attempts; well inside mdstack watch's default --source-timeout
RATE_LIMIT_GH = re.compile(r"rate limit|HTTP 429", re.IGNORECASE)
SECONDARY_WAIT = 60  # seconds; GitHub asks a secondary-rate-limited client to wait at least a minute


class Transient(RuntimeError):
    """A gh failure that persisted through every retry but looks like a GitHub hiccup, not a crew bug."""


class RateLimited(Transient):
    """GitHub refused a read for quota; any call before `until` (epoch) spends more of the shared budget (#1300)."""

    def __init__(self, message, until):
        super().__init__(message)
        self.until = until


def rate_reset(now):
    """Epoch at which the exhausted GitHub quota resets, read from `gh api rate_limit` (which counts against none);
    a secondary limit or an unreadable reply waits SECONDARY_WAIT."""
    r = subprocess.run(["gh", "api", "rate_limit"], capture_output=True, text=True)
    try:
        resets = [v["reset"] for v in json.loads(r.stdout)["resources"].values() if v["remaining"] == 0]
    except (ValueError, KeyError, TypeError, AttributeError):
        resets = []
    return max([now + SECONDARY_WAIT, *resets])


def landing_steers(reviews):
    """Read recorded coordinator urgency and outstanding project stops in review order."""
    urgent, stops = [], set()
    for review in reviews:
        for line in CREW_LINE.findall(review["body"]):
            marker = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            if (marker.get("role"), marker.get("pass")) != ("coordinator", "steer"):
                continue
            cmd, cmd_id = marker.get("cmd"), marker.get("cmd-id")
            if cmd == "urgent":
                urgent.append(marker)
            elif cmd == "stop-landing" and cmd_id:
                stops.add(cmd_id)
            elif cmd == "resume-landing":
                stops.discard(marker.get("stop-id"))
    return {"urgent": urgent, "stops": sorted(stops)}


def signed_by(values, role, review):
    """The review's author login and visible signature are this runtime's `role` identity (#1290, #1005)."""
    login, name = values.get("identities.%s.gh_user" % role), values.get("identities.%s.name" % role)
    return (review.get("author") or {}).get("login") == login and \
        (not name or bool(re.search(r"^— .*\b%s \(" % re.escape(name), review["body"], re.M)))


def merge_ok_identity(pr, values):
    """The permission identity of this runtime's coordinator `pass=steer cmd=merge-ok` record at the PR's current full
    head SHA (protocol §7, Merge permission), scoped by repository, PR, head and command, or None. Without profile
    values nothing authenticates it. Only a marker naming this PR (or no PR) counts; copies share one identity (#1835)."""
    head = pr["headRefOid"]
    for review in pr["reviews"] if values is not None else ():
        for line in CREW_LINE.findall(review["body"]):
            m = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            if (m.get("role"), m.get("pass"), m.get("cmd"), m.get("sha")) == ("coordinator", "steer", "merge-ok", head) \
                    and m.get("pr", str(pr.get("number"))) == str(pr.get("number")) and \
                    signed_by(values, "coordinator", review):
                return ["%s/%s" % (values.get("repo.owner"), values.get("repo.name")), "#%s" % pr.get("number"), head,
                        "merge-ok"]
    return None


def round_reset(values, review, m):
    """A coordinator `steer cmd=resume|cutover` record (protocol §9), or a legacy `pass=resume|cutover` one, restarts
    the round count (§5). With values, only this runtime's coordinator identity resets it (#1005)."""
    canonical = m.get("pass") == "steer" and m.get("cmd") in ("resume", "cutover")
    return m.get("role") == "coordinator" and (canonical or m.get("pass") in ("resume", "cutover")) and \
        (values is None or signed_by(values, "coordinator", review))


def required_checks(values):
    """The expected-check baseline: `[ci] required_checks` from the project profile, or () when unset (#1536)."""
    return tuple(values.get("ci.required_checks") or ())


def missing_checks(checks, required):
    """Sorted names of the expected checks absent at head: a check run's or status context's name, or `gh pr checks`'
    name (#1536)."""
    seen = {c.get("context") if c.get("__typename") == "StatusContext" else c.get("name") for c in checks}
    return sorted(set(required) - seen)


def pr_snapshot(pr, required=(), values=None):
    """Head, CI rollup, the latest verdict at head, round k (protocol §5) and whether a builder fix note sits at head
    after a changes verdict there (an evidence-only fix), the latest builder selfgate verdict at head and the builder
records at head (`notes`, an evidence wait's fingerprint, #1878), from the
    hidden crew:v1 lines only (protocol §4). An expected check absent at head keeps green CI pending (#1536). With the
    profile values, round k counts only this runtime's reviewer and coordinator records, so poll emission and reviewer
    dispatch derive the same round (#1005). Verdict identity keeps the posted round and reset source separate from
    dispatch round k; duplicate posts retain the first review ID as provenance (#1777). Utility mode preserves
    legacy roundless and latest-post verdict selection for gate consumers."""
    head = pr["headRefOid"]
    results = [c.get("state") if c.get("__typename") == "StatusContext" else
               "INFRA" if c.get("status") == "COMPLETED" and c.get("conclusion") in CI_BAD and
               (c.get("steps") == [] or c.get("_ci_infra")) else c.get("conclusion") if c.get("status") == "COMPLETED" else "PENDING"
               for c in pr["statusCheckRollup"]]
    ci = "failed" if CI_BAD & set(results) else "infra" if "INFRA" in results else \
         "passed" if results and set(results) <= CI_OK and not missing_checks(pr["statusCheckRollup"], required) \
         else "pending"
    verdict, fixed, changes, selfgate, notes = None, False, 0, None, []
    epoch, identity, review_id, seen = "legacy", None, None, set()
    for review in pr["reviews"]:
        for line in CREW_LINE.findall(review["body"]):
            m = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            if m.get("role") == "builder" and m.get("sha") == head:
                notes.append(review.get("id") or len(notes))
            if round_reset(values, review, m):
                changes = 0
                epoch = review.get("id") or review.get("submittedAt") or line
            elif m.get("role") == "reviewer-validator" and m.get("pass") == "verdict":
                signed = values is None or signed_by(values, "reviewer", review)
                changes += m.get("verdict") == "changes" and signed
                if signed and m.get("sha") == head and m.get("verdict") in ("pass", "changes") and \
                        (values is None or re.fullmatch(r"[1-9][0-9]*", m.get("round", ""))):
                    key = (head, epoch, m.get("round"), m["verdict"])
                    if values is None or key not in seen:
                        seen.add(key)
                        verdict, fixed = m["verdict"], False
                        identity, review_id = list(key), review.get("id")
            elif m.get("role") == "builder" and m.get("pass") == "fix" and m.get("sha") == head:
                fixed = True
            elif m.get("role") == "builder" and m.get("pass") == "selfgate" and m.get("sha") == head:
                selfgate = m.get("verdict")
    return {"head": head, "ci": ci, "verdict": verdict, "round": 1 + changes, "fixed": fixed and verdict == "changes",
            "selfgate": selfgate, "verdict_identity": identity, "verdict_review_id": review_id, "notes": notes,
            "merge_ok_identity": merge_ok_identity(pr, values)}


def held_numbers(prs, issues):
    """Open crew PRs and crew:ready issues labelled OWNER_BLOCKED, and the issues such a PR closes (#394)."""
    held = set()
    for item in prs + issues:
        if item.get("state", "OPEN") == "OPEN" and {label["name"] for label in item["labels"]} & OWNER_BLOCKED:
            held |= {item["number"]} | {i["number"] for i in item.get("closingIssuesReferences", [])}
    return sorted(held)


def owner_answers(prs, issues, owners, read, asked=()):
    """{"#n": owner comments (and PR reviews) on n} for each held n and each n with an open ask (asked) only, so the
    extra reads stay bounded (#394)."""
    pr_numbers, answers = {pr["number"] for pr in prs}, {}
    for n in sorted(set(held_numbers(prs, issues)) | set(asked)):
        item = read("pr" if n in pr_numbers else "issue", n, ["comments", "reviews"] if n in pr_numbers else ["comments"])
        answers["#%d" % n] = sum((c.get("author") or {}).get("login") in owners
                                 for c in item.get("comments", []) + item.get("reviews", []))
    return answers


def decide(prev, prs, issues, merge_ups=None, express=(), answers=None, required=(), values=None):
    """Pure: previous poll state plus gh JSON (open PRs, tracked PRs now merged or closed, open issues), the PR
    numbers that resolve express, held refs' owner-answer counts, the expected checks and the profile values for
    round identities -> (events, new state). A change emits one event; no change emits nothing."""
    events, state = [], {"prs": {}, "issues": []}

    def emit(event, *refs, **extra):
        events.append({"event": event, "consumer": CONSUMER[event], "refs": list(refs), **extra})

    for pr in prs:
        n, cur = str(pr["number"]), pr_snapshot(pr, required, values)
        if pr["state"] != "OPEN":
            emit("pr-merged" if pr["state"] == "MERGED" else "pr-closed", "#" + n, cur["head"])
            continue
        if not any(label["name"].startswith("crew:") for label in pr["labels"]):
            continue
        old, lane, approved = prev.get("prs", {}).get(n, {}), n in express, (merge_ups or {}).get(n)
        carried = lane and bool(approved or old.get("head") == cur["head"] and old.get("carried"))  # merge-up portability
        gate = cur["selfgate"] == "pass" or carried
        state["prs"][n] = dict(cur, express=True, gate=gate, carried=carried) if lane else cur
        if cur["head"] != old.get("head"):
            if approved:
                emit("merge-up", "#" + n, cur["head"], previous_head=approved["head"], round=approved["round"])
            elif not lane:
                emit("new-head", "#" + n, cur["head"], round=cur["round"])
        elif old.get("express") and not lane:  # lane fallback: the suppressed head now needs normal review
            emit("new-head", "#" + n, cur["head"], round=cur["round"])
        live = pr.get("mergeable")  # UNKNOWN is no conflict and keeps the head's last known value (#1398)
        known = live if live in ("MERGEABLE", "CONFLICTING") else \
            old.get("mergeable") if old.get("head") == cur["head"] else None
        if known:
            state["prs"][n]["mergeable"] = known
        if live == "CONFLICTING" and (cur["head"], live) != (old.get("head"), old.get("mergeable")):
            emit("pr-conflicting", "#" + n, cur["head"])  # GitHub runs no PR CI on a conflicting head
        if cur["ci"] in ("passed", "failed", "infra") and (cur["head"], cur["ci"]) != (old.get("head"), old.get("ci")) \
                and not (lane and cur["ci"] == "passed" and not gate):
            emit("ci-" + cur["ci"], "#" + n, cur["head"])
        elif lane and gate and cur["ci"] == "passed" and (cur["head"], True) != (old.get("head"), old.get("gate")):
            emit("selfgate-passed", "#" + n, cur["head"])
        verdict_changed = cur["verdict_identity"] != old.get("verdict_identity") if "verdict_identity" in old else \
            (cur["head"], cur["verdict"], cur["round"]) != (old.get("head"), old.get("verdict"), old.get("round"))
        if cur["verdict"] and verdict_changed:
            emit("review-approved" if cur["verdict"] == "pass" else "review-changes-requested", "#" + n, cur["head"])
        if cur["fixed"] and not lane and (cur["head"], True) != (old.get("head"), old.get("fixed")):  # no new-head (B2)
            emit("fix-at-head", "#" + n, cur["head"], round=cur["round"])
        if cur["merge_ok_identity"] and cur["merge_ok_identity"] != old.get("merge_ok_identity") and \
                ("merge_ok_identity" in old or not old):  # a legacy entry seeds quietly (#1835)
            emit("merge-ok-recorded", "#" + n, cur["head"])  # permission after green CI still wakes the lander
    state["issues"] = sorted(i["number"] for i in issues if i["assignees"] and
                             any(label["name"] == "crew:ready" for label in i["labels"]))
    state["held"] = ["#%d" % n for n in held_numbers(prs, issues)]
    open_refs = {"#%s" % i["number"] for i in prs + issues if i.get("state", "OPEN") == "OPEN"}
    if released := sorted(set(prev.get("held", [])) - set(state["held"]) & open_refs, key=lambda r: int(r[1:])):
        emit("hold-released", *released)  # the owner lifted a hold: wake at once, not at the backstop (#394)
    answers, before = answers or {}, prev.get("answers", {})
    state["answers"] = dict(answers)  # held or asked refs; the hold and the ask stay for the coordinator
    if answered := sorted((r for r in answers if r in before and answers[r] != before[r]), key=lambda r: int(r[1:])):
        emit("owner-answer", *answered)  # the owner answered on a parked item: wake at once (#394)
    for n in state["issues"]:
        if n not in prev.get("issues", []):
            emit("issue-assigned", "#%d" % n)
    return events, state


def ready_sample(pr, required=()):
    """Operational ready (self-improve.md#effect-measures): approval at head, green CI, mergeable and no known hold.
    A sampled observation, never merge authorization."""
    cur, hold = pr_snapshot(pr, required), any(label["name"] in HOLDS for label in pr["labels"])
    ready = pr["state"] == "OPEN" and cur["verdict"] == "pass" and cur["ci"] == "passed" and \
        pr.get("mergeable") == "MERGEABLE" and not hold
    return {"state": pr["state"], "head": cur["head"], "ci": cur["ci"], "verdict": cur["verdict"],
            "mergeable": pr.get("mergeable"), "hold": hold, "ready": ready}


def observe(state, record):
    """Append one sanitized observation (structured fields only, never pane text or paths) for
    scripts/reflection-measures.py (#1524)."""
    path = os.path.join(state, "metrics", "observations.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def gh_json(*args, retry=()):
    """gh JSON output; with retry (poll_once's reads, #702), a transient failure is retried after each delay in turn.
    Other callers keep one attempt: train_view records each failed read itself, and route runs inside the watcher."""
    for delay in (*retry, None):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if not r.returncode:
            return json.loads(r.stdout)
        if RATE_LIMIT_GH.search(r.stderr):
            until = rate_reset(time.time())
            raise RateLimited("crew: gh %s rate-limited until %s: %s" % (
                " ".join(args[:2]), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(until)), r.stderr.strip()), until)
        transient = bool(TRANSIENT_GH.search(r.stderr))
        if delay is None or not transient:
            break
        time.sleep(delay)
    raise (Transient if transient else RuntimeError)("crew: gh %s failed: %s" % (" ".join(args[:2]), r.stderr.strip()))


def observe_ci(pr, repo):
    """A failed Actions run with no started job steps is infrastructure, never green CI.
    Unavailable job observations keep the original failure classification."""
    ci_state(pr, repo)
    for check in pr["statusCheckRollup"]:
        if check.get("status") != "COMPLETED" or check.get("conclusion") not in CI_BAD:
            continue
        match = re.search(r"/actions/runs/(\d+)", check.get("detailsUrl", ""))
        if not match:
            continue
        try:
            jobs = gh_json("api", "repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, match[1]))["jobs"]
        except RateLimited:  # a quota refusal ends the poll; each fallback below re-raises it too (#1300)
            raise
        except (RuntimeError, KeyError):
            continue
        check["_ci_infra"] = bool(jobs) and all(j.get("steps") == [] for j in jobs) and len(jobs) < 100


def ci_state(pr, repo):
    """Read failed Actions jobs' steps; unknown jobs remain code failures, never a green CI signal."""
    checks = []
    for check in pr["statusCheckRollup"]:
        job = re.search(r"/actions/runs/\d+/job/(\d+)", check.get("detailsUrl") or "")
        if job and check.get("status") == "COMPLETED" and check.get("conclusion") in CI_BAD:
            try:
                data = gh_json("api", "repos/%s/actions/jobs/%s" % (repo, job[1]))
            except RateLimited:
                raise
            except RuntimeError:
                data = {}
            if data.get("status") == "completed" and data.get("conclusion", "").upper() in CI_BAD and \
                    isinstance(data.get("steps"), list):
                check = dict(check, steps=data["steps"])
        checks.append(check)
    pr["statusCheckRollup"] = checks
    return pr_snapshot(pr)["ci"]


def merge_up(pr, old, repo, default_branch, express=False):
    """Recognize one merge atop the previously observed, still-approved head (for express, its selfgate pass); its
    second parent must belong to the default branch. Read the verdict live, so a later changes verdict cannot inherit
    a cached approval."""
    if not old.get("head") or old["head"] == pr["headRefOid"]:
        return None
    approved = pr_snapshot({**pr, "headRefOid": old["head"]})
    if approved["selfgate" if express else "verdict"] != "pass":
        return None
    for review in pr["reviews"]:
        for line in CREW_LINE.findall(review["body"]):
            marker = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            if (marker.get("role"), marker.get("pass"), marker.get("sha")) == (
                    "reviewer-validator", "verdict", old["head"]):
                approved["round"] = int(marker["round"])
    commit = gh_json("api", "repos/%s/commits/%s" % (repo, pr["headRefOid"]))
    parents = [p["sha"] for p in commit["parents"]]
    if len(parents) != 2 or parents[0] != old["head"]:
        return None
    comparison = gh_json("api", "repos/%s/compare/%s...%s" % (repo, parents[1], default_branch))
    return approved if comparison["status"] in ("ahead", "identical") else None


def express_lane(args, values, view):
    """Express resolution for a crew:express change (mdstack train's train_express); unreadable runs the crew lane."""
    try:
        return commands()["train"].train_express(args, values, "%s/%s" % (values["repo.owner"], values["repo.name"]),
                                                 view)[0]
    except RateLimited:
        raise
    except RuntimeError as e:
        print("crew: poll: #%d crew lane: %s" % (view["number"], e))
        return False


def event_context(project, values, e):
    """A wake record's work envelope (team §9.3): issue-assigned names its item; a `#n <sha>` record its change and
    head, with the round it carries; anything else names this project only."""
    refs, envelope = e.get("refs", []), crew_render.crew_config.envelope
    if e.get("event") == "issue-assigned":
        return envelope(work_context(project, values), item=int(refs[0][1:]))
    if len(refs) == 2 and re.fullmatch(r"#\d+", refs[0]) and re.fullmatch(r"[0-9a-f]{40}", refs[1]):
        return envelope(work_context(project, values), change=int(refs[0][1:]), head=refs[1], round_=e.get("round"))
    return envelope(work_context(project, values))


def drop_superseded(queue, heads):
    """Drop queued ci-failed records for a PR whose live head has moved past theirs (#578); caller holds the lock."""
    if not os.path.exists(queue):
        return
    with open(queue, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    kept = []
    for line in lines:
        try:
            w = json.loads(line)
        except ValueError:
            kept.append(line)
            continue
        refs = w.get("refs") or []
        if not (w.get("event") == "ci-failed" and len(refs) > 1 and heads.get(refs[0], refs[1]) != refs[1]):
            kept.append(line)
    if len(kept) < len(lines):
        with open(queue, "w", encoding="utf-8") as f:
            f.writelines(kept)


def poll_once(values, state, args):
    mode = ownership_module.status(values)
    ownership_path = os.path.join(state, "ownership.json")
    previous = json.load(open(ownership_path)) if os.path.exists(ownership_path) else "active"
    if mode != "active":
        if previous != mode:
            with queue_lock(state), open(os.path.join(state, "wake", "queue.jsonl"), "a") as f:
                f.write(json.dumps({"id": "ownership-" + os.urandom(6).hex(), "source": "poll",
                                   "reason": "ownership:", "event": "ownership", "consumer": "coordinator",
                                   "refs": [mode], "context": event_context(args.project, values, {})}) + "\n")
        with open(ownership_path, "w") as f:
            json.dump(mode, f)
        print("crew: ownership: %s; poll emits no work" % mode)
        return
    if previous != "active":
        with open(ownership_path, "w") as f:
            json.dump(mode, f)
    repo, path = "%s/%s" % (values["repo.owner"], values["repo.name"]), os.path.join(state, "poll-state.json")
    prev = None
    if os.path.exists(path):
        with open(path) as f:
            prev = json.load(f)
    prs = gh_json("pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", PR_FIELDS + ",mergeable",
                  retry=RETRY_DELAYS)
    gone = set((prev or {}).get("prs", {})) - {str(pr["number"]) for pr in prs}
    prs += [gh_json("pr", "view", n, "-R", repo, "--json", PR_FIELDS + ",mergeable", retry=RETRY_DELAYS)
            for n in sorted(gone)]
    issues = gh_json("issue", "list", "-R", repo, "--state", "open", "--label", tracker_labels(values)["crew:ready"],
                     "--limit", "200", "--json", "number,labels,assignees", retry=RETRY_DELAYS)
    for record in prs + issues:  # this project's tracker labels read as canonical state tags (repo.labels)
        canonical_labels(values, record)
    express = {str(pr["number"]) for pr in prs if pr["state"] == "OPEN" and express_lane(args, values, pr)}
    merge_ups = {}
    for pr in prs:
        if pr["state"] == "OPEN" and any(l["name"].startswith("crew:") for l in pr["labels"]):
            approved = merge_up(pr, (prev or {}).get("prs", {}).get(str(pr["number"]), {}),
                                repo, values["repo.default_branch"], str(pr["number"]) in express)
            if approved:
                merge_ups[str(pr["number"])] = approved
    for pr in prs:
        observe_ci(pr, repo)
    owners = set(values.get("identities.owners") or []) or {values["repo.owner"]}
    asked = [int(n) for n, _, _ in commands()["watch"].asks(state) if n.isdigit()]  # asks/<n>.json park n too
    answers = owner_answers(prs, issues, owners, lambda kind, n, fields: gh_json(
        kind, "view", str(n), "-R", repo, "--json", ",".join(fields), retry=RETRY_DELAYS), asked)
    events, new = decide(prev or {}, prs, issues, merge_ups, express, answers, required_checks(values), values)
    if prev is None:  # first run: record a baseline only; the §6 step 3 sweep covers what happened before it
        events = []
        print("crew: poll: baseline of %d PRs, %d issues" % (len(new["prs"]), len(new["issues"])))
    heads = {"#%d" % pr["number"]: pr["headRefOid"] for pr in prs}
    with queue_lock(state):
        drop_superseded(os.path.join(state, "wake", "queue.jsonl"), heads)
    with queue_lock(state), open(os.path.join(state, "wake", "queue.jsonl"), "a", encoding="utf-8") as f:  # at-least-once
        for e in events:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(json.dumps({"id": "poll-%s-%s" % (ts, os.urandom(3).hex()), "source": "poll", "reason": "poll", **e,
                                "context": event_context(args.project, values, e), "ts": ts}) + "\n")
            print("crew: poll: %s -> %s %s" % (e["event"], e["consumer"], " ".join(e["refs"])))
    now, seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), (prev or {}).get("observed", {})
    new["observed"], new["ts"] = {}, now
    for pr in prs:
        n = str(pr["number"])
        if n in seen or pr["state"] == "OPEN" and any(label["name"].startswith("crew:") for label in pr["labels"]):
            sample = ready_sample(pr, required_checks(values))
            if pr["state"] == "OPEN":
                new["observed"][n] = sample
            if sample != seen.get(n):
                observe(state, dict(sample, ts=now, prev_ts=(prev or {}).get("ts"), source="poll", pr=int(n),
                                    key="pr#%s@%s" % (n, sample["head"])))
    with open(path + ".tmp", "w") as f:
        json.dump(new, f, indent=2)
    os.replace(path + ".tmp", path)
    if values.get("triage.enabled"):
        triage_poll(values, state, args.project, org=args.org_profile)


# Always-on triage scan (triage.md T1, #747): deterministic, no model call. Skip rules per triage.md "Skip rules".
TRIAGE_FIELDS = "number,title,body,labels,milestone,url,comments"
TRIAGE_RULES = {"p0": {"labels": ["P0", "security"],  # built-in defaults when triage.rules is unset or unreadable
                       "keywords": ["pipeline blocked", "gate bypass", "secret leak", "token leak", "data loss"]}}
TRIAGE_CARD = os.path.join(ROOT, "templates", "intake-candidate.md")
TRIAGE_PATH = re.compile(r"(?<![\w/.])(?:[\w.-]+/)+[\w-]+\.\w+\b")
TRIAGE_SOURCE = re.compile(r"[\w.-]+/[\w.-]+#\d+")
TRIAGE_FEEDBACK = re.compile(r"^triage: (?:accept|reject|adjust)\b", re.M)


def triage_card_fields(template=TRIAGE_CARD):
    """Card field names from the intake-candidate template's markdown block, e.g. Source, Failure class."""
    with open(template, encoding="utf-8") as f:
        block = f.read().split("```markdown", 1)[1].split("```", 1)[0]
    return re.findall(r"^(?:\*\*)?([A-Z][\w ]*?):", block, re.M)


def triage_keys(item, fields):
    """Card fields and the exact duplicate keys of one issue: failure class, Source, named paths, normalized title."""
    body = item.get("body") or ""
    card = {}
    for name in fields:
        m = re.search(r"^(?:\*\*)?%s:(?:\*\*)?[ \t]*(.+?)[ \t]*$" % re.escape(name), body, re.M)
        if m:
            card[name] = m[1]
    source = TRIAGE_SOURCE.search(card.get("Source", ""))
    title = re.sub(r"^(\[[^]]*\]\s*)+", "", item["title"].lower())
    keys = {"title:" + " ".join(re.findall(r"[a-z0-9]+", title))}
    keys |= {"path:" + p for p in TRIAGE_PATH.findall(body)}
    if card.get("Failure class"):
        keys.add("class:" + card["Failure class"].split()[0].lower())
    if source:
        keys.add("source:" + source[0].lower())
    return card, keys


def triage_rules(path):
    """(rules, note): the rules file's P0 signals, or the built-in defaults when unset or unreadable."""
    if not path:
        return TRIAGE_RULES, "default"
    try:
        with open(path, "rb") as f:
            p0 = tomllib.load(f)["p0"]
        return {"p0": {k: [str(v) for v in p0.get(k, [])] for k in ("labels", "keywords")}}, path
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return TRIAGE_RULES, "default (unreadable %s: %s)" % (path, e)


def triage_feedback(comment, owners, coordinator):
    """An owner's `triage: accept|reject|adjust` reply, or a coordinator decision relaying the owner: its
    `pass=steer cmd=decision` marker decides, whatever the title, old or new (#1946)."""
    login, body = (comment.get("author") or {}).get("login"), (comment.get("body") or "").lstrip()
    if login in owners and TRIAGE_FEEDBACK.search(body):
        return True
    decision = any("role=coordinator" in line.split() and "pass=steer" in line.split() and "cmd=decision" in line.split()
                   for line in CREW_LINE.findall(body))
    return bool(coordinator and coordinator[1]) and login in owners | {coordinator[0]} and decision


def triage_scan(repo, open_items, closed_items, rules, owners, fields, coordinator=None):
    """Pure: queue entries for one repo. Skips pull requests, triage:log issues, placed issues and issues with a
    flavor record; an issue with a pass=triage record queues on later owner feedback (a `triage:` reply, or a relayed
    coordinator decision on it or naming it from another open issue such as the decision log), placed or not, or on
    a later owner comment without a record while unplaced. coordinator is (gh_user, name)."""
    entries, keyed, open_numbers = [], [], {i.get("number") for i in open_items}
    relayed = {}  # issue number -> createdAt of each relayed decision naming it from another issue
    for item in open_items:
        for c in item.get("comments") or []:
            if isinstance(c, dict) and triage_feedback(c, owners, coordinator):
                for n in set(re.findall(r"(?<![\w/])#(\w[\w-]*\w|\w)\b", c.get("body") or "")) - {str(item.get("number"))}:
                    relayed.setdefault(int(n) if n.isdigit() else n, []).append(c.get("createdAt") or "")
    for item in open_items + closed_items:
        try:
            keyed.append((item, *triage_keys(item, fields)))
        except (KeyError, TypeError, AttributeError) as e:  # a closed item only loses its duplicate hints
            if item in open_items:
                entries.append({"ref": "%s#%s" % (repo, item.get("number")),
                                "unreadable": "%s: %s" % (type(e).__name__, e)})
    for item, card, keys in keyed:
        ref = "%s#%s" % (repo, item["number"])
        if item["number"] not in open_numbers:
            continue
        try:
            labels = {label["name"] for label in item["labels"]}
            markers = [(c, dict(kv.split("=", 1) for kv in line.split() if "=" in kv))
                       for c in item["comments"] for line in CREW_LINE.findall(c["body"])]
            if "/pull/" in item.get("url", "") or "triage:log" in labels:
                continue
            triaged = [i for i, (_, m) in enumerate(markers) if m.get("pass") == "triage"]
            if triaged:
                last = markers[triaged[-1]][0]
                later = item["comments"][item["comments"].index(last) + 1:]
                if any(triage_feedback(c, owners, coordinator) for c in later) or any(
                        t > (last.get("createdAt") or "") for t in relayed.get(item["number"], [])):
                    reason = "owner-feedback"
                elif not item.get("milestone") and any(
                        (c.get("author") or {}).get("login") in owners and "pass=triage" not in c["body"]
                        for c in later):
                    reason = "owner-reply"
                else:
                    continue
            elif item.get("milestone") or any(m.get("pass") == "flavor" for _, m in markers):
                continue
            else:
                reason = "new"
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            entries.append({"ref": ref, "unreadable": "%s: %s" % (type(e).__name__, e)})
            continue
        text = " ".join((item["title"], card.get("Failure class", ""))).lower()
        p0 = sorted({"label:" + n for n in labels if n in rules["p0"]["labels"]} |
                    {"keyword:" + k for k in rules["p0"]["keywords"]
                     if re.search(r"\b%s\b" % re.escape(k.lower()), text)})
        dupes = [{"ref": "%s#%s" % (repo, other["number"]), "state": "open" if other["number"] in open_numbers
                  else "closed", "keys": sorted(keys & other_keys)}
                 for other, _, other_keys in keyed if other is not item and keys & other_keys]
        entries.append({"ref": ref, "reason": reason, "title": item["title"], "card": card, "duplicates": dupes,
                        "p0": p0})
    return entries


def triage_array(data):
    """A tracker operation's JSON output (an array or pages) as one array of objects; ValueError otherwise."""
    flat = [x for page in data for x in page] if isinstance(data, list) and data and all(
        isinstance(p, list) for p in data) else data
    if not isinstance(flat, list) or not all(isinstance(x, dict) for x in flat):
        raise ValueError("printed no array of objects")
    return flat


def triage_comment(c):
    """One tracker comment: author as a string or `{login}`, `created` or `createdAt`, a missing body empty."""
    return dict(c, author=c["author"] if isinstance(c.get("author"), dict) else {"login": c.get("author")},
                createdAt=c.get("createdAt") or c.get("created"), body=c.get("body") or "")


def triage_items(data):
    """(open, closed) from a `tracker.list-items` output (an array or pages): ids (`number` or `id`, digits as int),
    label names or `{name}`, comment authors as a string or `{login}`, `created` or `createdAt`; only an absent or
    `open` state is open."""
    items = ([], [])
    for i in triage_array(data):
        n = i.get("number", i.get("id"))
        n = int(n) if isinstance(n, str) and n.isdigit() else n
        comments = [triage_comment(c) for c in i.get("comments") or [] if isinstance(c, dict)]
        labels = [lb if isinstance(lb, dict) else {"name": lb} for lb in i.get("labels") or []]
        items[str(i.get("state") or "open").lower() != "open"].append(
            dict(i, number=n, labels=labels, comments=comments, url=i.get("url") or ""))
    return items


def triage_native(values, project, org, tracker):
    """The non-GitHub tracker's `tracker.list-items` binding run for one tracker id: (open, closed). RuntimeError when
    unbound, failed or unreadable, so the scan records the tracker unreadable. A bound `tracker.read-comments` then
    replaces each open item's comments (#1960); an item whose read fails or prints no array loses its comments, so
    the scan records it unreadable."""
    renderer = crew_render.Renderer(values, os.path.join(ROOT, "templates"), overlay=crew_render.pack_overlay(
        project, org, values))
    try:
        cmd, kept = renderer.op("tracker", "list-items")
        renderer.kept = kept | {"tracker"}  # install-time placeholders filled as in a brief; <tracker> per read
        cmd = renderer.line(cmd)
    except ValueError as e:
        raise RuntimeError("tracker.list-items unbound (%s)" % e) from e
    argv = [a.replace("<tracker>", tracker) for a in shlex.split(cmd)]
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except OSError as e:
        raise RuntimeError("tracker.list-items failed (%s)" % e) from e
    if r.returncode:
        raise RuntimeError("tracker.list-items failed: %s" % r.stderr.strip())
    try:
        items = triage_items(json.loads(r.stdout))
    except ValueError as e:
        raise RuntimeError("tracker.list-items %s" % e) from e
    try:
        cmd, kept = renderer.op("tracker", "read-comments")
        renderer.kept = kept | {"n"}
        cmd = renderer.line(cmd)
    except crew_render.Unsupported:
        return items
    except ValueError as e:
        raise RuntimeError("tracker.read-comments unbound (%s)" % e) from e
    for item in items[0]:
        argv = [a.replace("<n>", str(item["number"])) for a in shlex.split(cmd)]
        try:
            r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            if r.returncode:
                raise ValueError(r.stderr.strip())
            item["comments"] = [triage_comment(c) for c in triage_array(json.loads(r.stdout))]
        except (OSError, ValueError):
            del item["comments"]
    return items


def triage_poll(values, state, project, read=gh_json, org=None, native=triage_native):
    """Scan every triage.repos tracker into triage/queue.json; queue one triage-p0 wake per newly seen P0 candidate.
    Only a `new` entry (no pass=triage record yet) wakes: a recorded P0 item re-queued by owner feedback was already
    triaged (#1093). An unreadable repo or item is recorded in the queue, never dropped. A non-GitHub tracker backend
    scans each triage.trackers id (default the project, `<owner>/<repo>`) through native (#1404)."""
    rules_path = values.get("triage.rules")
    rules, note = triage_rules(rules_path and os.path.join(os.path.dirname(os.path.abspath(project)), rules_path))
    owners, fields = set(values.get("identities.owners") or []), triage_card_fields()
    coordinator = (values.get("identities.coordinator.gh_user"), values.get("identities.coordinator.name"))
    path = os.path.join(state, "triage", "queue.json")
    try:
        with open(path) as f:
            seen = {e["ref"] for e in json.load(f)["items"] if e.get("p0")}
    except (OSError, ValueError, KeyError, TypeError):
        seen = set()
    queue = {"scanned": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rules": note, "repos": {}, "items": []}
    github = values.get("backends.tracker.name", "github") == "github"
    project_repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    for repo in values.get("triage.repos" if github else "triage.trackers") or [project_repo]:
        try:
            items = native(values, project, org, repo) if not github else [read("issue", "list", "-R", repo, "--state", s, "--limit", "500", "--json",
                          TRIAGE_FIELDS if s == "open" else "number,title,body", retry=RETRY_DELAYS)
                     for s in ("open", "closed")]
        except RateLimited:
            raise
        except RuntimeError as e:
            queue["repos"][repo] = "unreadable: %s" % e
            continue
        queue["repos"][repo] = "ok"
        queue["items"] += triage_scan(repo, *items, rules, owners, fields, coordinator)
    queue["milestones"] = triage_milestones(values, state, read) if github else \
        triage_load(state, "queue.json", "milestones", [])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(queue, f, indent=2)
    os.replace(path + ".tmp", path)
    for e in queue["items"]:
        if e.get("p0") and e.get("reason") == "new" and e["ref"] not in seen:
            ts = queue["scanned"]
            with queue_lock(state), open(os.path.join(state, "wake", "queue.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": "triage-p0-%s-%s" % (ts, os.urandom(3).hex()), "source": "poll",
                                    "reason": "triage-p0", "event": "triage-p0", "consumer": "coordinator",
                                    "refs": [e["ref"]], "p0": e["p0"], "context": event_context(project, values, {}),
                                    "ts": ts}) + "\n")
            print("crew: poll: triage-p0 -> coordinator %s" % e["ref"])


def triage_load(state, name, key, default):
    try:
        with open(os.path.join(state, "triage", name)) as f:
            return json.load(f)[key]
    except (OSError, ValueError, KeyError, TypeError):
        return default


def triage_untaken(state):
    """Queued closed milestones no sweep started with yet: `mdstack spawn researcher --sweep` names them in its Item and
    records them in triage/milestones-taken.json only once its window started (#374)."""
    taken = triage_load(state, "milestones-taken.json", "taken", [])
    return [m for m in triage_load(state, "queue.json", "milestones", []) or [] if m not in taken]


def triage_take(state, milestones):
    taken = triage_load(state, "milestones-taken.json", "taken", [])
    with open(os.path.join(state, "triage", "milestones-taken.json"), "w") as f:
        json.dump({"taken": taken + [m for m in milestones if m not in taken]}, f)


def triage_milestones(values, state, read=gh_json):
    """Milestones awaiting a milestone-close sweep (triage.md T6, #374): the queue's earlier list plus the project repo's
    milestones closed since the last scan (triage/milestones.json; the first scan records a baseline only), less those a
    started sweep took (triage_take). An unreadable list keeps the earlier one."""
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    load = functools.partial(triage_load, state)
    pending, seen = load("queue.json", "milestones", []), load("milestones.json", "closed", None)
    try:
        closed = read("api", "repos/%s/milestones?state=closed&per_page=100" % repo, retry=RETRY_DELAYS)
        closed = {m["number"]: m["title"] for m in closed}
    except RateLimited:
        raise
    except (RuntimeError, ValueError, KeyError, TypeError):
        return pending
    if seen is not None:
        pending += [{"repo": repo, "number": n, "title": t} for n, t in sorted(closed.items()) if n not in seen]
    os.makedirs(os.path.join(state, "triage"), exist_ok=True)
    with open(os.path.join(state, "triage", "milestones.json"), "w") as f:
        json.dump({"closed": sorted(closed)}, f)
    taken = load("milestones-taken.json", "taken", [])
    return [m for m in pending if m not in taken]


def register(sub):
    p = sub.add_parser("poll")
    p.add_argument("--once", action="store_true", help="one poll, then exit (default: every poll_interval seconds)")
    p.add_argument("--triage-only", action="store_true",
                   help="one triage scan into triage/queue.json, then exit; tmux or session profile (#1404)")
    p.add_argument("--project")
    p.add_argument("--org-profile")


def triage_only(args):
    values, _, state = profile(args, runtimes=("tmux", "session"))
    if not values.get("triage.enabled"):
        print("crew: poll: triage.enabled is false; nothing to scan")
        return 1
    mode = ownership_module.status(values)
    if mode != "active":
        print("crew: ownership: %s; poll emits no work" % mode)
        return 0
    try:
        triage_poll(values, state, args.project, org=args.org_profile)
    except RuntimeError as e:
        print(e)
        return os.EX_TEMPFAIL if isinstance(e, Transient) else 1
    with open(os.path.join(state, "triage", "queue.json")) as f:
        queue = json.load(f)
    print("crew: poll: triage queue %d items (%s)" % (len(queue["items"]), ", ".join(
        "%s %s" % kv for kv in queue["repos"].items())))
    return 0


def run(args):
    if args.triage_only:
        return triage_only(args)
    values, _, state = profile(args)
    while True:
        until = 0
        try:
            poll_once(values, state, args)
        except RuntimeError as e:
            print(e)
            if args.once:
                return os.EX_TEMPFAIL if isinstance(e, Transient) else 1
            until = getattr(e, "until", 0)
        if args.once:
            return 0
        time.sleep(max(values["runtime.options.poll_interval"], until - time.time()))
