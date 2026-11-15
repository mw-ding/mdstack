"""Crew scheduler inputs (docs/scheduling.md#inputs): one JSON read of every input, `unknown` where a read fails,
the ranking over it (docs/scheduling.md#priority) and the crew-wide target T (docs/scheduling.md#target), kept in
schedule/target.json, and the decision a lead asks for (docs/scheduling.md#model): admit, defer or hold, with
caller-only reservations in schedule/reservations.json and the log in schedule/decisions-<yyyymmdd>.jsonl, and the
one-line summary of the latest decision (docs/scheduling.md#observability).

A team file's repos share one schedule/ at the team root: one lock, target and reservation ledger of qualified work
(repo, pool, ref, and a reviewer pass's kind and round), every repo's workers counted once, each repo's demand
filtered by its own ownership, pause, holds and escalation; the caller's lane is its (repo, pool)
(docs/scheduling.md#team-admission, team §9.4). A one-repo config is its own singleton team, unchanged.

Usage: mdstack schedule snapshot|decide|release|summary [--pool builder|reviewer] [REF...] --project FILE [--org-profile FILE]
"""
import argparse
import datetime
import fcntl
import json
import os
import platform
import re
import subprocess
from crew_shared import (BANDS, CAPS, ENGINE_CMD, commands, crew_render, heartbeat, idle_builder, open_trains,
                         ownership_module, paused, pool_cap, probe, proc, profile, receipts, runs, status_lines, tmux, tracker_labels)

UNKNOWN = "unknown"
MAC_PRESSURE = {1: "normal", 2: "warn", 4: "critical"}
CLASSES = {("reviewer", "recheck"): 2, ("builder", "merge-up"): 3, ("reviewer", "validate"): 4, ("reviewer", "review"): 5,
           ("builder", "fix"): 6, ("builder", "ci-red"): 6, ("builder", "build"): 7}
TARGET_OPTIONS = {"load_high": 6.0, "load_low": 4.0, "error_high": 3, "schedule_interval": 120, "schedule_ramp": 2}
PSI_HIGH = {"warn": 10.0, "critical": 40.0}  # Linux memory `some avg10` high at, per memory threshold
PSI_LOW = 1.0  # and low below
RESERVATION_TTL = 600  # seconds a grant counts as busy before its run record appears
LEAD_DOWN = ("dead", "missing", "ambiguous", UNKNOWN)
DEPENDS = re.compile(r"^#*\s*Depends on\b(.*?)(?=^#+\s|\Z)", re.I | re.M | re.S)
RED_FIX = re.compile(r"main-red\b", re.I)
SHA40 = re.compile(r"\b[0-9a-f]{40}\b")
REVIEW_LINES = ((re.compile(r"done: #(\d+) [0-9a-f]{40} review pass(?:\s|$)"), "validate"),
                (re.compile(r"done: #(\d+) [0-9a-f]{40} recheck escalate(?:\s|$)"), "review"),
                (re.compile(r"done: #\d+ #(\d+) [0-9a-f]{40}$"), "review"))


def read(fn, *args):
    try:
        return fn(*args)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        return UNKNOWN


def jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def work_event(path):
    """A reviewer `work` ref's event and None, else None and why it is unreadable or not a JSON object (#1020)."""
    try:
        with open(path) as f:
            event = json.load(f)
    except (OSError, ValueError) as e:
        return None, "%s: %s" % (type(e).__name__, e)
    if not isinstance(event, dict):
        return None, "not a JSON object"
    return event, None


def work_pass(event):
    """The reviewer pass a `work` event starts and its PR ref, else (None, None)."""
    if event.get("event") in ("new-head", "fix-at-head", "merge-up"):
        return "review", event["refs"][0]
    for pattern, kind in REVIEW_LINES:
        m = pattern.match(event.get("line", ""))
        if m:
            return kind, "#" + m[1]
    return None, None


def demand(state, values, role, team=False):
    """Pending lead inbox ids by kind; reviewer `work` ids carry the event they name, ranked as the pass it starts
    (docs/scheduling.md#inputs); builders add spawn-queue.jsonl. In a team, an acknowledged wait the wait book holds
    unchanged is parked, not demand, so one repo's parked waits never take another's budget (#1836)."""
    items, name = [], values["identities.%s.name" % role].lower() + "-lead"
    parked = commands()["lead"].parked(state, name) if team else set()
    for m in commands()["lead"].pending(state, name):
        if m["id"] in parked:
            continue
        item = dict(id=m["id"], kind=m["kind"], refs=m["refs"], ts=m.get("ts"))
        if role == "reviewer" and m["kind"] == "work":
            event, error = work_event(m["refs"][0])
            if error:
                item.update(kind="invalid-work", error=error)  # unranked; the pool records its disposition (#1020)
            else:
                item["event"] = event
                kind, ref = work_pass(event)
                if kind:
                    item.update(kind=kind, refs=[ref])
        items.append(item)
    if role == "builder":
        items += [dict(kind=e["pass"], issue=e["issue"], pr=e["pr"], ts=e["queued"], queued=True, head=e.get("head"))
                  for e in jsonl(os.path.join(state, "spawn-queue.jsonl")) if e["role"] == "builder"]
    return items


def workers(session, state, repo=None):
    """Run records with their state; a team repo's (`repo`) also carry that repo and the run's round."""
    windows = dict((n, i) for i, n in tmux.list_windows(session))
    found = []
    for name, rec in runs(state):
        live = read(probe, session, name, rec, windows)
        idle = rec["role"] == "builder" and read(idle_builder, state, name) not in (None, UNKNOWN)
        found.append({"name": name, "role": rec["role"], "item": rec["item"], "pass": rec["pass"], "pr": rec.get("pr"),
                      "start": rec.get("start"),
                      "finished": rec["role"] == "reviewer" and heartbeat(state, name)[0].startswith("done:"),
                      "state": "idle" if idle else "exited" if live in ("dead", "missing") else "busy",
                      **({"repo": repo, "round": rec.get("args", {}).get("round")} if repo else {})})
    return found


def lands(state, values):
    """Outstanding land messages in the synthesizer inbox and its saved queue, read without synthesizer_work's write."""
    name = values["identities.synthesizer.name"].lower()
    lines = status_lines(state, name)
    saved = jsonl(os.path.join(state, "inbox", "synthesizer-pending.jsonl"))
    found = []
    for m in {m["id"]: m for m in saved + jsonl(os.path.join(state, "inbox", name + ".jsonl"))}.values():
        ack = receipts(state, name).get(m["id"], len(lines))
        if m["kind"] == "land" and not any(
                line.split()[1:len(m["refs"][:2]) + 1] == m["refs"][:2] if line.startswith("done: ") else
                line.startswith("blocked: ") and line.split()[1:2] == m["refs"][:1] for line in lines[ack + 1:]):
            found.append(dict(id=m["id"], refs=m["refs"], ts=m.get("ts")))
    return found


def tracker(values):
    """Open milestones and open issues with their milestone and `Depends on #n` refs (critical-path input), and the
    open issues titled `main-red` that fix a red default branch (class 1). A set `repo.milestones` is the project's
    own milestone order (team §9.1): only those open milestones, in that order."""
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    gh = commands()["route"].gh
    milestones = json.loads(subprocess.run(["gh", "api", "repos/%s/milestones?state=open&per_page=100" % repo],
                                           capture_output=True, text=True, check=True).stdout)
    if values.get("repo.milestones"):
        milestones = [m for n in values["repo.milestones"] for m in milestones if m["number"] == n]
    issues = gh("issue", "list", "-R", repo, "--state", "open", "--limit", "1000", "--json", "number,milestone,body,title")
    return dict(milestones=[dict(number=m["number"], title=m["title"]) for m in milestones],
                max_active=values.get("runtime.options.max_active_milestones", 1),
                issues=[dict(number=i["number"], milestone=(i["milestone"] or {}).get("title"),
                             depends=sorted({int(n) for block in DEPENDS.findall(i["body"] or "")
                                             for n in re.findall(r"#(\d+)", block)}))
                        for i in issues],
                red_fixes=sorted(i["number"] for i in issues if RED_FIX.match(i.get("title") or "")))


def holds(values, escalated=False):
    """Open issue and PR numbers under `crew:hold` (this project's tracker label for it, repo.labels), with the PRs
    that close a held issue; a team repo's `crew:escalated` items too. The label always blocks; the deprecated
    `hold_label_blocks` is ignored (#1124)."""
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    gh, labels = commands()["route"].gh, tracker_labels(values)
    names = [labels["crew:hold"]] + [labels["crew:escalated"]] * escalated
    issues = {i["number"] for name in names for i in gh("issue", "list", "-R", repo, "--state", "open", "--label",
                                                         name, "--limit", "1000", "--json", "number")}
    prs = gh("pr", "list", "-R", repo, "--state", "open", "--limit", "1000", "--json", "number,labels,closingIssuesReferences")
    return sorted(issues | {p["number"] for p in prs if any(label["name"] in names for label in p["labels"])
                            or issues & {i["number"] for i in p["closingIssuesReferences"]}})


def heads(values):
    """Each open PR's head commit by number (a team repo's head check, team §9.4)."""
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    prs = commands()["route"].gh("pr", "list", "-R", repo, "--state", "open", "--limit", "1000", "--json", "number,headRefOid")
    return {str(p["number"]): p["headRefOid"] for p in prs}


def memory():
    if platform.system() == "Darwin":
        out = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                             capture_output=True, text=True, check=True).stdout
        return dict(os="darwin", level=MAC_PRESSURE[int(out)])
    with open("/proc/pressure/memory") as f:
        some = next(line for line in f if line.startswith("some "))
    return dict(os="linux", some_avg10=float(re.search(r"avg10=([\d.]+)", some)[1]))


def errors(state, now):
    """Gateway errors (HTTP 429/5xx, rate limits) recorded in the last 10 minutes."""
    since = now - datetime.timedelta(minutes=10)
    return sum(datetime.datetime.fromisoformat(e["ts"].replace("Z", "+00:00")) >= since
               for e in jsonl(os.path.join(state, "schedule", "errors.jsonl")))


def unrecorded(session, *states):
    """Crew windows other than window 0 with no run or lead record (in any of a team's repo states) whose pane holds a
    live tool session."""
    recorded = {n for state in states for n, _ in runs(state)} | \
        {n for state in states for n, _ in commands()["lead"].records(state)}
    found = []
    for index, name in tmux.list_windows(session):
        p = None if int(index) == 0 or name in recorded else tmux.pane(session, int(index))
        if p and p["dead"] == "0" and p["pid"] and all(proc.live_child(p["pid"], h) for h in ENGINE_CMD.values()):
            found.append(dict(window=name, pid=p["pid"]))
    return found


def cap(values, state, role):
    lo, hi = BANDS[role]
    return min(pool_cap(values, role, state), hi - lo + 1)


def memory_high(values, caps):
    """The memory threshold of docs/scheduling.md#target: runtime.options.memory_high, else `critical` at full speed
    (every pool's effective cap is its full cap) and `warn` below it."""
    if values.get("runtime.options.memory_high"):
        return values["runtime.options.memory_high"]
    if UNKNOWN in caps.values():
        return UNKNOWN
    full = all(caps[r] == min(values[CAPS[r]], BANDS[r][1] - BANDS[r][0] + 1) for r in caps)
    return "critical" if full else "warn"


def canonical(values):
    """The canonical repo identity of resolved values, spelled as crew-config's context() spells it (team §9.3)."""
    return ("%s/%s" % (values["repo.owner"], values["repo.name"])).lower()


def home(values, state):
    """The directory holding schedule/: a team file's team root (one lock, target and ledger, D2), else the repo state,
    a one-repo config's singleton team."""
    return os.path.abspath(values["paths.state_dir"]) if values.get("team.name") else state


def members(args, values):
    """A team file's repos as {project, repo, values, state}, or {project, problem} for one that does not resolve; None
    for a one-repo config."""
    if not values.get("team.name"):
        return None
    config = crew_render.crew_config
    file, found = config.split_ref(args.project)[0], []
    for name in config.team_repos(file):
        ref = "%s#%s" % (file, name)
        v, problems = crew_render.resolve(ref, args.org_profile)
        found.append(dict(project=ref, problem=(problems or ["unresolved"])[0]) if problems or not v else dict(
            project=ref, repo=canonical(v), values=v,
            state=os.path.join(os.path.abspath(v["paths.state_dir"]), "%s__%s" % (v["repo.owner"], v["repo.name"]))))
    return found


def repo_inputs(values, state, team=False):
    """One repo's demand, lands, trains, tracker and holds (docs/scheduling.md#inputs)."""
    return dict(demand={role: read(demand, state, values, role, team) for role in ("builder", "reviewer")},
                lands=read(lands, state, values), trains=read(lambda: [os.path.basename(p) for p in open_trains(state)]),
                tracker=read(tracker, values), holds=read(holds, values, team),
                **({"heads": read(heads, values)} if team else {}))


def ledger(path):
    return json.load(open(path)) if os.path.exists(path) else []


def machine(values, caps, now):
    cpus = os.cpu_count()
    return dict(ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"), cpus=cpus or UNKNOWN,
                load=read(lambda: round(os.getloadavg()[0] / cpus, 3)), memory=read(memory),
                memory_high=memory_high(values, caps), caps=caps)


def snapshot(args):
    values, session, state = profile(args)
    team = members(args, values)
    if team is not None:
        return team_snapshot(values, session, state, team)
    now = datetime.datetime.now(datetime.timezone.utc)
    closed = []
    suites = read(commands()["lead"].suites, values, state, closed)
    loose = read(unrecorded, session, state)
    caps = {role: read(cap, values, state, role) for role in ("builder", "reviewer")}
    return dict(
        machine(values, caps, now), **repo_inputs(values, state),
        workers=read(workers, session, state),
        reservations=read(ledger, os.path.join(state, "schedule", "reservations.json")),
        suites=suites,
        orphans=UNKNOWN if UNKNOWN in (suites, loose) else closed + loose,
        errors=read(errors, state, now))


def summed(counts):
    return UNKNOWN if UNKNOWN in counts else sum(counts)


def team_snapshot(values, session, state, team):
    """The team's inputs (team §9.4): every repo's workers (tagged with their repo), suites and errors counted once,
    each repo's demand, tracker, holds, ownership and pause under `repos`, the team ledger, and caps applied once to
    team totals. A repo that does not resolve leaves workers, suites and caps unknown: its runs cannot be counted."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ok, closed = [m for m in team if "problem" not in m], []
    whole = len(ok) == len(team)
    found = [read(workers, session, m["state"], m["repo"]) for m in ok]
    suites = summed([read(commands()["lead"].suites, m["values"], m["state"], closed) for m in ok] + [UNKNOWN] * (not whole))
    loose = read(unrecorded, session, *[m["state"] for m in ok])
    caps = {role: [read(cap, m["values"], m["state"], role) for m in ok] + [UNKNOWN] * (not whole)
            for role in ("builder", "reviewer")}
    caps = {role: UNKNOWN if UNKNOWN in c else min(c) for role, c in caps.items()}
    return dict(
        machine(values, caps, now), team=values["team.name"],
        repos={m["repo"]: dict(project=m["project"], ownership=read(ownership_module.ownership, m["values"]),
                               paused=paused(m["state"]), **repo_inputs(m["values"], m["state"], True)) for m in ok},
        unresolved=[dict(project=m["project"], problem=m["problem"]) for m in team if "problem" in m],
        workers=UNKNOWN if UNKNOWN in found or not whole else [w for ws in found for w in ws],
        reservations=read(ledger, os.path.join(home(values, state), "schedule", "reservations.json")),
        suites=suites,
        orphans=UNKNOWN if UNKNOWN in (suites, loose) else closed + loose,
        errors=summed([read(errors, m["state"], now) for m in ok]))


def critical_path(issues):
    """Open issues waiting on each issue, directly or transitively, from their `Depends on` refs."""
    waiters = {}
    for i in issues:
        for n in i["depends"]:
            waiters.setdefault(n, set()).add(i["number"])
    counts = {}
    for n in waiters:
        seen, todo = set(), list(waiters[n])
        while todo:
            w = todo.pop()
            if w not in seen:
                seen.add(w)
                todo += waiters.get(w, ())
        counts[n] = len(seen - {n})
    return counts


def classify(snap, red_fixes=None):
    """Both pools' demand with class, milestone order, critical path and `held` (its issue or PR is in snap["holds"])
    per item, unsorted; decide never walks unknown holds. Kinds outside the eight classes and pools with unknown demand
    are left out. `red_fixes` defaults to the tracker's open `main-red` issues. A team snapshot classifies each repo
    against its own tracker, holds and workers (milestones and dependencies stay local) and tags every item with its
    repo and project reference; a blocked repo's demand in a pool is left out. A team build whose `Depends on` names
    an issue still open in its own repo carries those numbers as `depends_open`, and each team item carries the first
    AC2 predicate it fails as `ineligible` (see ineligible()); rank() leaves those out."""
    if "repos" in snap:
        found = []
        for repo, r in sorted(snap["repos"].items()):
            sub = dict({k: v for k, v in snap.items() if k != "repos"}, tracker=r["tracker"], holds=r["holds"],
                       demand={p: [] if blocked(r, p) else r["demand"][p] for p in ("builder", "reviewer")},
                       workers=snap["workers"] if snap["workers"] == UNKNOWN else
                       [w for w in snap["workers"] if w.get("repo") == repo])
            issues = [] if r["tracker"] == UNKNOWN else r["tracker"]["issues"]
            open_ = {i["number"] for i in issues}
            depends = {i["number"]: sorted(set(i["depends"]) & open_) for i in issues}
            for i in classify(sub, red_fixes):
                i = dict(i, repo=repo, project=r["project"], **({"round": round_of(i)} if i["pool"] == "reviewer" else {}),
                         **({"depends_open": depends[i["issue"]]} if i["kind"] == "build" and depends.get(i["issue"])
                            else {}))
                found.append(dict(i, ineligible=ineligible(r, i)))
        return found
    tracker = snap["tracker"] if snap.get("tracker", UNKNOWN) != UNKNOWN else dict(milestones=[], max_active=1, issues=[])
    red_fixes = set(tracker.get("red_fixes", []) if red_fixes is None else red_fixes)
    titles = [m["title"] for m in tracker["milestones"]]
    latest = max(min(tracker["max_active"], len(titles)) - 1, 0)
    milestone = {i["number"]: i["milestone"] for i in tracker["issues"]}
    waiting = critical_path(tracker["issues"])
    issue_of = {w["pr"]: int(re.search(r"issue #(\d+)", w["item"])[1]) for w in snap["workers"] if w.get("pr")} \
        if snap["workers"] != UNKNOWN else {}
    held = snap.get("holds", [])
    held = set() if held == UNKNOWN else set(held)
    ranked = []
    for pool in ("builder", "reviewer"):
        if snap["demand"][pool] == UNKNOWN:
            continue
        for d in snap["demand"][pool]:
            cls = CLASSES.get((pool, d["kind"]))
            if not cls:
                continue
            build = d["kind"] == "build"
            if d.get("queued"):
                n = d["issue"] if build else d["pr"]
                issue = d["issue"] or issue_of.get(n)
            else:
                n = int(d["refs"][0].lstrip("#"))
                issue = n if build else issue_of.get(n)
            order = titles.index(milestone.get(issue)) if milestone.get(issue) in titles else latest
            if pool == "builder" and {n, issue} & red_fixes and d["kind"] in ("build", "fix", "ci-red"):
                cls = 1
            elif build:
                cls = 7 if order == 0 else 8
            ranked.append(dict(d, pool=pool, ref="#%d" % n, issue=issue, milestone_order=order,
                               waiting=waiting.get(issue, 0), held=bool({n, issue} & held), **{"class": cls}))
    return ranked


def rank(snap, red_fixes=None):
    """Both pools' unheld demand in one list (docs/scheduling.md#priority): class, then milestone order, critical
    path (more waiters first) and age (oldest first). `red_fixes` are the issue or PR numbers whose builds or fixes
    repair a red default branch (class 1); by default the tracker's open `main-red` issues and their PRs. Team items
    then tie-break by canonical repo and work identity, so the order is deterministic across repos."""
    return sorted((r for r in classify(snap, red_fixes) if not r["held"] and not r.get("ineligible")),
                  key=lambda r: (r["class"], r["milestone_order"], -r["waiting"], r.get("ts") or "~") +
                  ((r["repo"], r["ref"], r["kind"]) if "repo" in r else ()))


def blocked(r, pool):
    """Why a team repo's demand in `pool` is not eligible, else None: its ownership does not permit starting work, it
    is paused, or its holds, tracker or that pool's demand cannot be read (team §9.4). Its runs still count as busy."""
    if r["ownership"] == UNKNOWN or not ownership_module.permits(r["ownership"], "start"):
        return "ownership-" + r["ownership"]
    if r["paused"] is not None:
        return "paused"
    if r["holds"] == UNKNOWN:
        return "holds-unreadable"
    if r["tracker"] == UNKNOWN:
        return "tracker-unreadable"
    return "demand-unreadable" if r["demand"][pool] == UNKNOWN else None


def head_of(item):
    """The head commit a demand item is bound to, else None: a queued spawn's head, or the sha after its PR ref in its
    refs (a `#n <sha> ...` handoff, fix or ci-red) or in the work event it names (refs or `done:` line)."""
    if item.get("queued"):
        return item.get("head")
    event = item.get("event") or {}
    for refs in (event.get("refs"), item.get("refs")):
        if refs and len(refs) > 1 and SHA40.fullmatch(str(refs[1])):
            return refs[1]
    found = SHA40.search(event.get("line", ""))
    return found[0] if found else None


def ineligible(r, item):
    """The first AC2 predicate (team §9.4) a team demand item fails in its own repo `r`, else None. Each predicate must
    read positively, so an unknown input defers the item exactly as a mismatch does: the repo's ownership, pause and
    readable holds, tracker and demand (blocked()), its hold or escalation, every PR pass (each kind but `build`)
    naming a readable head equal to its open PR's live head, and a build's local dependencies closed. Only that item
    is refused; other repos are untouched."""
    why = blocked(r, item["pool"])
    if why:
        return why
    if item["held"]:
        return "held"
    if item["kind"] != "build":
        head = head_of(item)
        if head is None:
            return "head-unreadable"
        if r.get("heads", UNKNOWN) == UNKNOWN:
            return "heads-unreadable"
        if r["heads"].get(item["ref"][1:]) != head:
            return "stale-head"
    return "depends-open" if item.get("depends_open") else None


def lane(x):
    """An item's, action's or reservation's admission lane: its pool, and its repo too in a team. Only the caller's
    lane is granted and reserved; another lane's would-be grants hold budget for the walk."""
    return x["pool"] if x.get("repo") is None else (x["repo"], x["pool"])


def round_of(item):
    """A reviewer item's round when its handoff names one: a `#n <sha> <round>` message, else its event's envelope."""
    refs = item.get("refs") or []
    if len(refs) > 2 and str(refs[2]).isdigit():
        return int(refs[2])
    found = ((item.get("event") or {}).get("context") or {}).get("round")
    return found if type(found) is int else None


def ident(x):
    """The qualified work identity a reservation matches (team §9.3): lane and ref, plus a team reviewer pass's kind
    and round, so the same PR's passes and rounds stay distinct. One-repo identity stays (pool, ref)."""
    return (lane(x), x["ref"]) + ((x.get("kind"), x.get("round")) if x.get("repo") and x["pool"] == "reviewer" else ())


def held(snap):
    """Demand left out of the ranking because its issue or PR is on hold, oldest first."""
    return sorted((r for r in classify(snap) if r["held"]), key=lambda r: r.get("ts") or "~")


def stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def target_options(values):
    return {k: values.get("runtime.options." + k, v) for k, v in TARGET_OPTIONS.items()}


def level(value, high, low):
    return UNKNOWN if value == UNKNOWN else "high" if value >= high else "low" if value < low else "between"


def signals(snap, opts):
    """Each machine signal of docs/scheduling.md#target as high, low, between or unknown."""
    mem, high = snap["memory"], snap["memory_high"]
    if UNKNOWN in (mem, high):
        memory = UNKNOWN
    elif "level" in mem:
        levels = list(MAC_PRESSURE.values())
        memory = "high" if levels.index(mem["level"]) >= levels.index(high) else "low"
    else:
        memory = level(mem["some_avg10"], PSI_HIGH[high], PSI_LOW)
    return dict(load=level(snap["load"], opts["load_high"], opts["load_low"]), memory=memory,
                errors=level(snap["errors"], opts["error_high"], 1))


def target(snap, opts, doc, now):
    """The next schedule/target.json document from the previous one (None on the first run). T starts at the busy
    count, stays within [1, sum of pool caps] and moves by one at most once per schedule_interval: down when any
    signal is high, up when every signal is low and demand waits. Unknown signals, caps or workers hold T."""
    busy = None if snap["workers"] == UNKNOWN else sum(w["state"] == "busy" for w in snap["workers"])
    ceiling = None if UNKNOWN in snap["caps"].values() else sum(snap["caps"].values())
    clamp = lambda t: max(1, t if ceiling is None else min(t, ceiling))
    if doc is None:
        return dict(target=clamp(busy or 1), changed=stamp(now), starts=[])
    t, changed = clamp(doc["target"]), doc["changed"]
    sig = signals(snap, opts)
    due = (now - parse(changed)).total_seconds() >= opts["schedule_interval"]
    if due and UNKNOWN not in sig.values() and None not in (busy, ceiling):
        if "high" in sig.values():
            nxt = max(1, min(t, busy) - 1)
        elif set(sig.values()) == {"low"} and rank(snap):
            nxt = clamp(t + 1)
        else:
            nxt = t
        if nxt != t:
            t, changed = nxt, stamp(now)
    since = now - datetime.timedelta(seconds=opts["schedule_interval"])
    return dict(target=t, changed=changed, starts=[s for s in doc.get("starts", []) if parse(s) > since])


def ramp_left(doc, opts):
    """Starts the ramp limit still allows in the current schedule_interval (`starts` is pruned by target())."""
    return max(0, opts["schedule_ramp"] - len(doc["starts"]))


def update_target(state, snap, values, now):
    """Read, advance and write schedule/target.json; return the new document."""
    path = os.path.join(state, "schedule", "target.json")
    doc = None
    if os.path.exists(path):
        with open(path) as f:
            doc = json.load(f)
    doc = target(snap, target_options(values), doc, now)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    os.replace(path + ".tmp", path)
    return doc


def on_ref(w, pool, ref):
    """Whether worker `w` belongs to `pool` and works `ref` (its `pr` or any #n in its item)."""
    return w["role"] == pool and int(ref[1:]) in {w.get("pr"), *map(int, re.findall(r"#(\d+)", w.get("item", "")))}


def live_reservations(reservations, workers, now):
    """Reservations younger than RESERVATION_TTL whose ref has no run record yet: a busy worker of the pool on the
    ref, or one started since the grant, ends a reservation. A team reservation transfers only to its allocated run:
    a worker of the same repo and, for a reviewer pass, the same pass and round (when both name one)."""
    def mine(w, r):
        if w.get("repo") != r.get("repo"):
            return False
        if r.get("repo") is None or r["pool"] != "reviewer":
            return True
        return w.get("pass") == r.get("kind") and (None in (w.get("round"), r.get("round")) or w["round"] == r["round"])

    def started(r):
        return any(on_ref(w, r["pool"], r["ref"]) and mine(w, r) and
                   (w["state"] == "busy" or (w.get("start") or "") >= r["time"]) for w in workers)
    return [r for r in reservations if (now - parse(r["time"])).total_seconds() < RESERVATION_TTL and not started(r)]


def ceiling_hit(snap, values):
    """The optional hard ceiling a start would exceed (an unobserved input counts as exceeded), else None."""
    max_suites, max_load = values.get("runtime.options.max_suites"), values.get("runtime.options.max_load")
    if max_suites is not None and (snap["suites"] == UNKNOWN or snap["suites"] >= max_suites):
        return "max_suites"
    if max_load is not None and (UNKNOWN in (snap["load"], snap["cpus"]) or snap["load"] * snap["cpus"] >= max_load):
        return "max_load"
    return None


def walk(pool, ranked, snap, reserved, target_doc, opts, leads, ceiling=None, repo=None):
    """Walk the crew's ranked demand (docs/scheduling.md#model). The caller's items are admitted (already reserved
    ones again, as `reserved`) or deferred with the first failed condition; the other pool's would-be grants are
    holds for this walk only, dropped as `lead-down` when that pool's lead is down. A pool with no busy worker or
    reservation may admit its top-ranked item past the target, ramp and ceiling (its floor). Builder demand a busy
    builder already runs is skipped: it is neither admitted, held nor counted (#988). Reviewer demand is not: it leaves
    the inbox when its pass starts, and a busy reviewer on the same PR runs another pass or round. In a team the
    caller is the lane (repo, pool): another repo's would-be grants are holds too, `leads` is keyed by lane, and caps,
    floors, target and ramp count team totals (team §9.4). A team class 8 build waits (`class-7`) while any eligible
    team class 7 build has not started; a one-repo walk keeps class 8 as fill-in by rank order."""
    caller = pool if repo is None else (repo, pool)

    def running(item):
        return item["pool"] == "builder" and any(w["state"] == "busy" and on_ref(w, "builder", item["ref"]) and
                                                 w.get("repo") == item.get("repo") for w in snap["workers"])
    class_7 = repo is not None and any(i["class"] == 7 and not running(i) and
                                       (lane(i) == caller or leads.get(lane(i), UNKNOWN) not in LEAD_DOWN) for i in ranked)
    used = {p: sum(w["role"] == p and w["state"] == "busy" for w in snap["workers"]) +
            sum(r["pool"] == p for r in reserved) for p in ("builder", "reviewer")}
    floor = {p: used[p] == 0 for p in used}
    held = {ident(r) for r in reserved}
    total, starts, actions = sum(used.values()), len(target_doc["starts"]), []
    for item in ranked:
        if running(item):
            continue
        p, act = item["pool"], dict(pool=item["pool"], ref=item["ref"], kind=item["kind"], **{"class": item["class"]})
        if "repo" in item:
            act.update(repo=item["repo"], project=item["project"], **({"round": item["round"]} if "round" in item else {}))
        mine = lane(item) == caller
        if ident(item) in held:
            if mine:
                actions.append(dict(act, action="admit", reasons=["reserved"]))
            continue
        if not mine and leads.get(lane(item), UNKNOWN) in LEAD_DOWN:
            actions.append(dict(act, action="drop", reasons=["lead-down"]))
            continue
        if item["class"] == 8 and class_7:
            if mine:
                actions.append(dict(act, action="defer", reasons=["class-7"]))
            continue
        fails = [why for why, ok in (("cap", used[p] < snap["caps"][p]), ("target", total < target_doc["target"]),
                                     ("ramp", starts < opts["schedule_ramp"]), (ceiling, ceiling is None)) if not ok]
        if fails and not (floor[p] and fails[0] != "cap"):
            if mine:
                actions.append(dict(act, action="defer", reasons=fails[:1]))
            floor[p] = False
            continue
        actions.append(dict(act, action="admit" if mine else "hold", reasons=["floor"] if fails else []))
        used[p], total, starts, floor[p] = used[p] + 1, total + 1, starts + 1, False
    return actions


def save_json(path, doc):
    with open(path + ".tmp", "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    os.replace(path + ".tmp", path)


def defer_key(a):
    """deferred.json's key for a defer: its ref, qualified by repo in a team (the same #n in two repos is two items)."""
    return a["ref"] if a.get("repo") is None else "%s %s" % (a["repo"], a["ref"])


def log(state, pool, snap, target_doc, actions, now, repo=None):
    """Append the snapshot line and each action to the UTC day's decisions file (7 days kept); a defer repeated with
    the same reasons as the caller's previous decision is not written again. schedule/deferred.json keeps each pool's
    current defers with their kind, class, reasons and the time each ref was first deferred (`since`); a team caller
    (`repo`) replaces only its own repo's defers, each entry carrying its repo and ref."""
    sched = os.path.join(state, "schedule")
    keep = (now - datetime.timedelta(days=7)).strftime("decisions-%Y%m%d.jsonl")
    for name in os.listdir(sched):
        if name.startswith("decisions-") and name < keep:
            os.remove(os.path.join(sched, name))
    last_path = os.path.join(sched, "deferred.json")
    last = json.load(open(last_path)) if os.path.exists(last_path) else {}
    caps = snap["caps"]
    lines = [dict(action="snapshot", pool=pool, ts=stamp(now), snapshot=snap, target=target_doc["target"], caps=caps,
                  ceiling=UNKNOWN if UNKNOWN in caps.values() else sum(caps.values()), **({"repo": repo} if repo else {}))]
    prev = {ref: d for ref, d in last.get(pool, {}).items() if isinstance(d, dict)}
    lines += [a for a in actions if a["action"] != "defer" or prev.get(defer_key(a), {}).get("reasons") != a["reasons"]]
    last[pool] = {k: d for k, d in prev.items() if d.get("repo") != repo}  # a team caller replaces only its repo's
    last[pool].update({defer_key(a): dict(kind=a.get("kind"), reasons=a["reasons"], since=prev.get(defer_key(a), {}).get(
        "since", stamp(now)), **{"class": a.get("class")}, **({"repo": repo, "ref": a["ref"]} if repo else {}))
        for a in actions if a["action"] == "defer"})
    save_json(last_path, last)
    with open(os.path.join(sched, now.strftime("decisions-%Y%m%d.jsonl")), "a") as f:
        f.writelines(json.dumps(line, sort_keys=True) + "\n" for line in lines)


def lead_states(session, state, values, team=None):
    """Each pool lead's liveness; for a team, keyed by lane (repo, pool) from each repo's lead records, a repo whose
    probe fails being down."""
    if team is not None:
        found = {}
        for m in team:
            got = {} if "problem" in m else read(lead_states, session, m["state"], m["values"])
            found.update({(m["repo"], p): s for p, s in ({} if got == UNKNOWN else got).items()})
        return found
    lead = commands()["lead"]
    recs, windows = dict(lead.records(state)), dict((n, i) for i, n in tmux.list_windows(session))
    names = {p: values["identities.%s.name" % p].lower() + "-lead" for p in ("builder", "reviewer")}
    return {p: read(probe, session, n, recs[n], windows) if n in recs else "missing" for p, n in names.items()}


def evaluate(args, values, session, state, now):
    """One write-free walk for args.pool: (snapshot, live reservations, advanced target document, actions, the
    refusal or None). An unreadable reservation ledger refuses rather than counting as no busy work. A team refuses
    on unreadable caps, workers or ledger, and when the caller's own repo is blocked; another blocked repo only loses
    its demand."""
    snap = snapshot(args)
    workers = [] if snap["workers"] == UNKNOWN else snap["workers"]
    ledger_ok = isinstance(snap["reservations"], list)
    reserved = live_reservations(snap["reservations"] if ledger_ok else [], workers, now)
    busy = workers + [dict(role=r["pool"], state="busy") for r in reserved]  # a reservation counts as busy for T
    path = os.path.join(home(values, state), "schedule", "target.json")
    doc = json.load(open(path)) if os.path.exists(path) else None
    doc = target(snap if snap["workers"] == UNKNOWN else dict(snap, workers=busy), target_options(values), doc, now)
    team, repo = "repos" in snap, canonical(values) if "repos" in snap else None
    unreadable = "caps" if UNKNOWN in snap["caps"].values() else "workers" if snap["workers"] == UNKNOWN \
        else "reservations" if not ledger_ok else None
    if not team and snap["demand"][args.pool] == UNKNOWN:
        unreadable = "demand"
    elif not team and not unreadable and snap["holds"] == UNKNOWN:
        unreadable = "holds"
    refusal = unreadable + "-unreadable" if unreadable else None
    if team and not refusal:
        refusal = blocked(snap["repos"][repo], args.pool) if repo in snap["repos"] else "profile-unreadable"
    if refusal:
        actions = [dict(pool=args.pool, ref=None, action="defer", reasons=[refusal], **({"repo": repo} if team else {}))]
    else:
        leads = read(lead_states, session, state, values, members(args, values) if team else None)
        actions = walk(args.pool, rank(snap), snap, reserved, doc, target_options(values),
                       {} if leads == UNKNOWN else leads, ceiling_hit(snap, values), repo)
    return snap, reserved, doc, actions, refusal


def admissible(args, pool):
    """Refs of `pool` one decision would admit now, reserved ones included: the lead backstop's token-free re-check of
    acknowledged deferred handoffs (#1502). It persists only the target's progression in schedule/target.json, so a
    throttled T recovers on this cadence; it writes no reservation, decision log or deferral. Unreadable inputs admit
    nothing. In a team only the caller's repo is admitted, so the refs are that repo's."""
    values, session, state = profile(args)
    sched = os.path.join(home(values, state), "schedule")
    os.makedirs(sched, exist_ok=True)
    with open(os.path.join(sched, "lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _, _, doc, actions, _ = evaluate(argparse.Namespace(**dict(vars(args), pool=pool)), values, session, state,
                                         datetime.datetime.now(datetime.timezone.utc))
        save_json(os.path.join(sched, "target.json"), doc)
    return {a["ref"] for a in actions if a["action"] == "admit"}


def team_blocks(snap):
    """A team snapshot's refusals per repo: [{repo, pool, reasons}] for blocked demand, [{project, reasons}] for a repo
    that does not resolve."""
    return [dict(repo=repo, pool=p, reasons=[why]) for repo, r in sorted(snap["repos"].items())
            for p in ("builder", "reviewer") for why in [blocked(r, p)] if why] + \
        [dict(project=u["project"], reasons=["profile-unreadable"]) for u in snap["unresolved"]]


def schedule_decide(args):
    """One decision for args.pool under schedule/lock; returns the JSON printed to the lead. A team adds its name, the
    caller's repo, each repo's refusals (`blocked`) and its unheld items an item-level AC2 predicate refuses
    (`waiting`, each with its reason), and every action names its repo."""
    values, session, state = profile(args)
    sched = os.path.join(home(values, state), "schedule")
    os.makedirs(sched, exist_ok=True)
    with open(os.path.join(sched, "lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        now = datetime.datetime.now(datetime.timezone.utc)
        snap, reserved, doc, actions, unreadable = evaluate(args, values, session, state, now)
        team = "repos" in snap
        save_json(os.path.join(sched, "target.json"), doc)
        grants = [a for a in actions if a["action"] == "admit" and a["reasons"] != ["reserved"]]
        if isinstance(snap["reservations"], list):  # an unreadable ledger is left as it is, never overwritten
            save_json(os.path.join(sched, "reservations.json"), reserved + [dict(
                ref=a["ref"], pool=args.pool, time=stamp(now), **({k: a.get(k) for k in ("repo", "project", "kind", "round")}
                                                                  if team else {})) for a in grants])
        if grants:
            save_json(os.path.join(sched, "target.json"), dict(doc, starts=doc["starts"] + [stamp(now)] * len(grants)))
        log(home(values, state), args.pool, snap, doc, actions + [dict(b, action="block") for b in
                                                                   (team_blocks(snap) if team else [])],
            now, canonical(values) if team else None)
    other = "reviewer" if args.pool == "builder" else "builder"
    for owner in sorted({lane(a) for a in actions if a["action"] == "hold"}, key=str):
        project, pool = (args.project, other) if isinstance(owner, str) else \
            (next(a["project"] for a in actions if a["action"] == "hold" and lane(a) == owner), owner[1])
        try:  # the owning lead's backstop wake, so the held item is claimed before the next tick
            commands()["lead"].retry_pending(argparse.Namespace(project=project, org_profile=args.org_profile),
                                             values["identities.%s.name" % pool].lower() + "-lead")
        except (RuntimeError, OSError):
            pass
    out = dict(pool=args.pool, target=doc["target"], admit=[a for a in actions if a["action"] == "admit"],
               deferred=[a for a in actions if a["action"] == "defer"], holds=[a for a in actions if a["action"] == "hold"],
               held=[] if unreadable else [dict(pool=r["pool"], ref=r["ref"], kind=r["kind"],
                                                **({"repo": r["repo"]} if team else {})) for r in held(snap)])
    if team:
        out.update(team=snap["team"], repo=canonical(values), blocked=team_blocks(snap), waiting=[] if unreadable else [
            dict(pool=r["pool"], ref=r["ref"], kind=r["kind"], repo=r["repo"], reasons=[r["ineligible"]],
                 **({"depends": r["depends_open"]} if r["ineligible"] == "depends-open" else {}))
            for r in classify(snap) if r["ineligible"] not in (None, "held")])
    return out


def release(state, pool, refs, values=None, kind=None, round_=None):
    """Drop `pool`'s reservations for `refs` under schedule/lock. Given a team repo's values, only that repo's in the
    team ledger, and with a reviewer `kind` (and `round_`) only that pass's: A's completion or failure never frees B's
    grant, nor another pass's (team §9.3)."""
    team = bool(values and values.get("team.name"))
    sched = os.path.join(home(values, state) if team else state, "schedule")
    repo = canonical(values) if team else None
    os.makedirs(sched, exist_ok=True)
    path = os.path.join(sched, "reservations.json")
    with open(os.path.join(sched, "lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        kept = [r for r in (json.load(open(path)) if os.path.exists(path) else [])
                if not (r["pool"] == pool and r["ref"] in refs and r.get("repo") == repo and
                        (pool != "reviewer" or kind is None or r.get("kind") in (None, kind)) and
                        (round_ is None or r.get("round") in (None, round_)))]
        save_json(path, kept)


def schedule_release(args):
    """Drop the caller's reservations for REFs (after a spawn failure); a team names the caller's repo."""
    values, _, state = profile(args)
    release(state, args.pool, args.refs, values, getattr(args, "kind", None), getattr(args, "round", None))
    return dict(pool=args.pool, released=args.refs, **({"repo": canonical(values)} if values.get("team.name") else {}))


def latest(state):
    """The newest decision's snapshot line, or None before the first decision."""
    sched = os.path.join(state, "schedule")
    for name in sorted((n for n in os.listdir(sched) if n.startswith("decisions-")), reverse=True) \
            if os.path.isdir(sched) else []:
        found = [line for line in jsonl(os.path.join(sched, name)) if line["action"] == "snapshot"]
        if found:
            return found[-1]
    return None


def deferred(state):
    """Each pool's current defers from schedule/deferred.json: dicts with pool and ref added (a team entry keeps its
    own repo and ref)."""
    path, last = os.path.join(state, "schedule", "deferred.json"), {}
    if os.path.exists(path):
        with open(path) as f:
            last = json.load(f)
    return [dict(dict(pool=pool, ref=ref), **d) for pool, refs in sorted(last.items()) for ref, d in refs.items()
            if isinstance(d, dict)]


def stuck(state, now, after, repo=None):
    """Finishing work (classes 1-6) deferred for at least `after` seconds at epoch `now`; with `repo`, a team
    watcher's own repo's only."""
    return [d for d in deferred(state) if (d.get("class") or 9) <= 6 and now - parse(d["since"]).timestamp() >= after
            and (repo is None or d.get("repo") == repo)]


def counts(words):
    tally = {}
    for w in words:
        tally[w] = tally.get(w, 0) + 1
    return tally


def summary(state):
    """One line from the latest decision (docs/scheduling.md#observability), or None before the first decision."""
    line = latest(state)
    if line is None:
        return None
    snap, caps = line["snapshot"], line["caps"]
    workers = snap["workers"]
    if workers == UNKNOWN:
        busy = dict(builder=UNKNOWN, reviewer=UNKNOWN)
    else:
        reserved = live_reservations(snap["reservations"] if isinstance(snap["reservations"], list) else [], workers,
                                     parse(snap["ts"]))
        busy = {p: sum(w["role"] == p and w["state"] == "busy" for w in workers) + sum(r["pool"] == p for r in reserved)
                for p in ("builder", "reviewer")}
    mem = snap["memory"]
    mem = mem if mem == UNKNOWN else mem["level"] if "level" in mem else "psi %s" % mem["some_avg10"]
    high = snap.get("memory_high")
    if high:
        mem += " (high at %s)" % (high if high == UNKNOWN or snap["memory"] == UNKNOWN or "level" in snap["memory"]
                                   else "psi %s" % PSI_HIGH[high])
    load = snap["load"] if snap["load"] == UNKNOWN else "%.1f/cpu" % snap["load"]
    kinds = [r["kind"] for r in rank(snap)]
    order = {k: c for (_, k), c in CLASSES.items()}
    queued = " ".join("%s %d" % kv for kv in sorted(counts(kinds).items(), key=lambda kv: order[kv[0]]))
    if "repos" in snap:  # a team: each repo's unread demand, and its refusals at the end of the line
        unread = " ".join("%s %s unknown" % (repo, p) for repo, r in sorted(snap["repos"].items())
                          for p in ("builder", "reviewer") if r["demand"][p] == UNKNOWN)
        blocks = "; blocked " + ", ".join(" ".join([b.get("repo") or b["project"]] + ([b["pool"]] if "pool" in b else [])
                                                   + b["reasons"]) for b in team_blocks(snap)) if team_blocks(snap) else ""
    else:
        unread, blocks = " ".join("%s unknown" % p for p in ("builder", "reviewer") if snap["demand"][p] == UNKNOWN), ""
    defers = deferred(state)
    why = ", ".join("%s %d" % kv for kv in counts(d["reasons"][0].split()[0] for d in defers if d["reasons"]).items())
    orphans = snap.get("orphans", UNKNOWN)
    orphans = orphans if orphans == UNKNOWN else "%d" % len(orphans) + "".join(
        " %s pid %s" % (o["window"], o["pid"]) for o in orphans)
    finished = UNKNOWN if workers == UNKNOWN else [w["name"] for w in workers if w.get("finished")]
    finished = finished if finished == UNKNOWN else " ".join(["%d" % len(finished)] + finished)
    paused = [r["ref"] for r in held(snap)]
    paused = UNKNOWN if snap.get("holds") == UNKNOWN else " ".join(["%d" % len(paused)] + paused)
    return "schedule: builders %s/%s reviewers %s/%s target %s (load %s mem %s errors %s) queued %s; deferred %d%s; " \
        "held %s; orphans %s; terminal %s%s" % (
            busy["builder"], caps["builder"], busy["reviewer"], caps["reviewer"], line["target"], load, mem,
            snap["errors"], " ".join(filter(None, (queued, unread))) or "none", len(defers),
            " (%s)" % why if why else "", paused, orphans, finished, blocks)


def register(sub):
    p = sub.add_parser("schedule")
    p.add_argument("action", choices=["snapshot", "decide", "release", "summary"])
    p.add_argument("refs", nargs="*")
    p.add_argument("--pool", choices=["builder", "reviewer"])
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    if args.action == "summary":
        values, _, state = profile(args)
        print(summary(home(values, state)) or "schedule: no decision yet")
        return 0
    if args.action != "snapshot" and not args.pool:
        print("crew: schedule %s requires --pool" % args.action)
        return 2
    out = {"snapshot": snapshot, "decide": schedule_decide, "release": schedule_release}[args.action](args)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0
