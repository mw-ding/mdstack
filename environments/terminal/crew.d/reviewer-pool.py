"""Reviewer lead's serialized inbox dispatch: fresh passes, replay and slot reclaim; admission is
`mdstack schedule decide --pool reviewer` (docs/scheduling.md#model). A team lead runs it per message repo; its acks and
dispositions go to its status at the team root (#1858). A fresh review whose head lacks its builder record is a
`waiting: #<n> evidence id=<id>` wait, not a claim (#1878).

Usage: mdstack reviewer-pool --project FILE [--org-profile FILE]
"""
import argparse
import fcntl
import json
import os
import re
from crew_shared import commands, heartbeat, lead_state, probe, profile, require_ownership, runs, tmux


def held(labels):
    """The typed wait a live hold label parks a request on (tmux.md lead backstop, #1836), else None."""
    return "hold" if "crew:hold" in labels else "owner" if "crew:escalated" in labels else None


def dispatch(args, values, state, wake):
    route = commands()["route"]
    name = wake.get("window")
    rec = dict(runs(state)).get(name)
    if wake.get("event") in ("pr-merged", "pr-closed"):
        pr = route.gh("pr", "view", wake["refs"][0].lstrip("#"), "-R",
                      "%s/%s" % (values["repo.owner"], values["repo.name"]), "--json", "number,state")
        if pr["state"] == "OPEN":
            return False
        for worker, record in list(runs(state)):
            if record["role"] == "reviewer" and record["args"]["pr"] == pr["number"]:
                route.reap(args, worker)
        return True
    if wake.get("reason") in ("stale", "dialog", "lifecycle", "quota"):
        if rec is None:
            return True
        _, session, _ = profile(args)
        windows = dict((n, i) for i, n in tmux.list_windows(session))
        liveness = probe(session, name, rec, windows)
        last = heartbeat(state, name)[0]
        if wake.get("reason") == "lifecycle" and (wake.get("start"), wake.get("head")) != (rec.get("start"), rec.get("head")):
            return True
        if wake.get("reason") == "lifecycle":
            pr = route.gh("pr", "view", str(rec["args"]["pr"]), "-R",
                          "%s/%s" % (values["repo.owner"], values["repo.name"]), "--json", "state,headRefOid")
            if pr["state"] != "OPEN" or pr["headRefOid"] != rec["head"]:
                route.reap(args, name)
                return True
        if last.startswith("done:"):
            return route.route_record(args, values, state, dict(wake, reason="status", line=last, round=rec["args"]["round"]))
        if liveness in ("dead", "missing", "quota") and not rec.get("restarts"):  # quota: next engine (#631)
            pr = route.gh("pr", "view", str(rec["args"]["pr"]), "-R", "%s/%s" % (values["repo.owner"], values["repo.name"]),
                          "--json", "headRefOid,state,labels")
            if pr["headRefOid"] != rec["head"] or pr["state"] != "OPEN":
                route.reap(args, name)
                return True
            labels = {l["name"] for l in pr["labels"]}
            if labels & {"crew:escalated", "crew:hold"}:
                return False
            route.invoke(args, "restart", window=name)
            return True
        if liveness == "alive" and wake.get("reason") == "stale" and wake.get("liveness") == "idle":
            liveness = "idle at its prompt"  # the watcher's idle stall; a re-probe still says alive (#1283)
        elif liveness == "alive" and wake.get("reason") == "stale":
            return True  # the lead has just re-probed; silence alone permits no restart
        raise RuntimeError("crew: reviewer %s is %s; coordinator escalation required" % (name, liveness))
    result = route.route_record(args, values, state, wake)
    if result:
        return True
    if rec is None and re.fullmatch(r"done: #\d+ stale", wake.get("line", "")):
        return True  # a replay after the stale reviewer was reaped (#811)
    # Closed and superseded requests retire; holds and missing CI/evidence stay pending.
    refs = wake.get("refs", [])
    match = re.match(r"done: #(?:\d+ #)?(\d+) ([0-9a-f]{40})", wake.get("line", ""))
    if match:
        refs = ["#" + match[1], match[2]]
    if len(refs) >= 2:
        pr = route.gh("pr", "view", refs[0].lstrip("#"), "-R", "%s/%s" % (values["repo.owner"], values["repo.name"]),
                      "--json", "state,headRefOid,labels")
        if pr["state"] != "OPEN" or pr["headRefOid"] != refs[1]:
            return True
        labels = {l["name"] for l in pr["labels"]}
        if held(labels):
            return "%s %s" % (refs[0], held(labels))  # parked: run() writes the typed wait
        if re.fullmatch(r"done: #\d+ [0-9a-f]{40} (review|validate|recheck) changes(?:\s.*)?", wake.get("line", "")):
            return commands()["lead"].event(args, "builder", wake) == 0
    return False


def register(sub):
    p = sub.add_parser("reviewer-pool")
    p.add_argument("--timeout", type=float, default=15)
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    values, _, state = profile(args)
    if not require_ownership(values) or os.environ.get("CREW_POOL") != "reviewer":
        return 1
    args.reviewer_lead = True
    root = os.path.join(state, "leads", "reviewer")
    os.makedirs(root, exist_ok=True)
    name = values["identities.reviewer.name"].lower() + "-lead"
    status = os.path.join(lead_state(state), "status", name + ".status")  # a team lead's is at the team root (#1858)
    os.makedirs(os.path.dirname(status), exist_ok=True)
    with open(os.path.join(root, "dispatch.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        evidence = False
        for message in commands()["lead"].pending(state, name):
            if not require_ownership(values):
                return 1
            with open(status, "a") as out:
                out.write("ack: " + message["id"] + "\n")
            refs = message["refs"]
            if message["kind"] == "work":
                wake, error = commands()["schedule"].work_event(refs[0])
                if error:
                    # A durable disposition for the coordinator; the rest of the queue still drains (#1020).
                    print("crew: reviewer work %s: invalid ref %s: %s" % (message["id"], refs[0], error))
                    with open(status, "a") as out:
                        out.write("blocked: %s invalid-work-ref %s %s\ndone: %s\n" % (
                            message["id"], refs[0], error.replace("\n", " "), message["id"]))
                    continue
                rec = dict(runs(state)).get(wake.get("window"))
                current = rec and (wake.get("reason") in ("stale", "dialog") or wake.get("reason") == "lifecycle" and
                                   (wake.get("start"), wake.get("head")) == (rec.get("start"), rec.get("head")))
                last = heartbeat(state, wake["window"])[0] if current else ""
                if last.startswith("done:"):
                    # Saved as the status wake dispatch() routes, so decide ranks its successor and a deferral replays it.
                    wake = dict(wake, reason="status", line=last, round=rec["args"]["round"])
                    with open(refs[0] + ".tmp", "w") as f:
                        json.dump(wake, f)
                    os.replace(refs[0] + ".tmp", refs[0])
            elif message["kind"] in ("review", "validate", "recheck"):
                pr, head, round_ = refs[:3]
                live = commands()["route"].gh("pr", "view", pr.lstrip("#"), "-R",
                         "%s/%s" % (values["repo.owner"], values["repo.name"]), "--json",
                         "number,state,headRefOid,isDraft,labels,reviews,statusCheckRollup")
                if live["state"] != "OPEN" or live["headRefOid"] != head:
                    with open(status, "a") as out:
                        out.write("done: " + message["id"] + "\n")
                    continue
                labels = {l["name"] for l in live["labels"]}
                if held(labels):
                    with open(status, "a") as out:
                        out.write("waiting: %s %s id=%s\n" % (pr, held(labels), message["id"]))
                    continue
                if live["isDraft"]:
                    continue
                if message["kind"] == "validate":
                    commands()["poll"].observe_ci(live, "%s/%s" % (values["repo.owner"], values["repo.name"]))
                    if commands()["poll"].pr_snapshot(live)["ci"] == "failed":
                        continue
                    section = os.path.join(state, "verdicts", "pr%s-%s-r%s-review.md" % (pr.lstrip("#"), head[:7], round_))
                    text = "\n".join(r["body"] for r in live["reviews"])
                    if os.path.exists(section):
                        with open(section) as f:
                            text += "\n" + f.read()
                    if not any(m.get("pass") == "review" and m.get("verdict") == "pass" and
                               m.get("sha") == head and m.get("round") == round_ for m in commands()["route"].markers(text)):
                        continue
                try:
                    commands()["route"].review(args, state, live, head, message["kind"], int(round_))
                except commands()["route"].NotReady as e:
                    print(e)
                    with open(status, "a") as out:
                        out.write("waiting: %s evidence id=%s\n" % (e.ref, message["id"]))
                    evidence = True
                    continue
                except RuntimeError as e:
                    print(e)
                    continue
                wake = None
            else:
                print("crew: unknown reviewer handoff " + message["kind"])
                continue
            try:
                completed = wake is None or dispatch(args, values, state, wake)
            except commands()["route"].NotReady as e:  # retained behind its typed wait until a builder note (#1878)
                print(e)
                completed = evidence = "%s evidence" % e.ref
            except (RuntimeError, OSError) as e:
                print(e)
                continue
            if isinstance(completed, str):  # a live hold: keep the id pending behind its typed wait (#1836)
                with open(status, "a") as out:
                    out.write("waiting: %s id=%s\n" % (completed, message["id"]))
            elif completed:
                with open(status, "a") as out:
                    out.write("done: " + message["id"] + "\n")
        if evidence:  # baseline evidence waits as they park: a note before the watcher's next scan still wakes (#1878)
            commands()["lead"].actionable(state, name)
    return 0
