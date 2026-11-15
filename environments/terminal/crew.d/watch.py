"""`mdstack watch` is the zero-token watcher that queues wakes in `wake/queue.jsonl` (one-shot `--source` commands cut off
at `--source-timeout`, default 60 s, queue growth from another poller, and an `ask:`
wake at each open owner ask's deadline in `asks/<n>.json`; a signal during a scan is held until its children exit)
and retries pending lead demand after 60, 120, 240, 480, then every 900 s while it is unchanged (a changed pending set
restarts at 60 s; a lead's acknowledged `waiting:` owner, hold or CI id is never retried until its PR's poll-state,
hold, owner answers or ask change, which wakes it on that scan; an acknowledged admission deferral also gets a 60 s
`admission recheck` that types only once its ref is admissible, #1715), then exits with one reason line; runs without `start` skip liveness
wakes while their record mtime is less than 60 s
old. Verified panes with a live tool session or recent output get a supervisor heartbeat instead of a stale wake; a
working run whose tmux pane printed nothing for `--idle-stall` (default 1800 s) is idle at its prompt and wakes stale with
liveness `idle` even while its claim or status file keeps being refreshed (#1283). An alive builder holding acked
unfinished work whose claim heartbeat is older than 900 s wakes stale with liveness `claim` for its lead, however fresh
the supervisor heartbeat on its status file, unless its item is held or its harness is mid-turn (#1633). Each new stale wake opens a stall
in `metrics/observations.jsonl` keyed by run, and that run's next status line closes it (self-improve.md, #1524).
Each live run's screen is matched against its harness adapter's transient-error text; each new match is a line in
`schedule/errors.jsonl` (docs/scheduling.md#inputs). A run whose harness shows its adapter's usage-limit line probes
`quota` and wakes once per run as `quota` (action restart: `mdstack restart` moves it to the next eligible engine, #631;
escalate after its one restart). Finishing work deferred by the scheduler past `stuck_after` is one
`schedule-stuck` wake per (pool, ref, first deferral), and the exit line is followed by `mdstack schedule summary`'s line
(docs/scheduling.md#observability).
While the project is paused (`pause.json`, mdstack pause, #1714) the watcher only observes: each scan runs the sources
and queues their events, but runs no status or liveness scan, role-host pull, timer, routine, scale-down, route,
backstop or nudge, and a one-shot watcher does not exit; status lines wait at their offsets until mdstack resume.
Its `wake: watcher` line is never typed into a window 0 showing a dialog, which gets
a `dialog` wake instead (#315). Before a coordinator wake, `mdstack route` consumes mechanical records;
the watcher continues scanning when none of the new records need judgement (#434); a record route keeps with
added notes (`consumer`, `dependents`, `route_error`) still counts as one that does (#814).
A source cut off at its timeout or exiting 75 (EX_TEMPFAIL, a transient `mdstack poll` failure) is a line in
`wake/incidents.jsonl`, not a wake; `--source-failures` consecutive ones send one `source-failing` wake with the count.
The `--source` commands run at most once per `--source-interval` (default `runtime.options.poll_interval`, 60 s), not on
every `--interval` scan, and the next due time survives a re-arm; an exit-75 line `rate-limited until <UTC>` holds them
until that reset, at most an hour, so watchers sharing one GitHub login stop spending its quota (#1300).
When `cli/mdstack`, `crew.d/*.py` or a `crew-*.py` module change on disk, the watcher re-execs itself before it queues or
routes that scan's wakes, so new code resolves any new profile keys (#702).
A run on a role host gets no liveness wake from this primary's tmux; every `runtime.options.host_scan_interval`
(default 15 s) one `pull` per role host with runs copies their new status lines into the primary's status mirrors,
which wake as local lines do; the host's answer is kept under `pulls` in watch-state.json (#346). Pulls failing 3 scans
in a row make the host's runs `unreachable`: one `unreachable` escalate wake per outage past --stale, then a `reconcile`
wake when it answers again, with a restart wake for each run found dead or missing; a tombstoned run (an owner's
abandon) is stopped on its host then (#347).
Once another runtime owns the repo (ownership `lost`, after a handoff's ack) the watcher refuses to arm (prompt stop).
With `[triage] enabled`, each scan runs the triage sweep timer, which costs no model turn and queues no wake
(docs/triage.md#triggers-and-cadence, #748); a newly closed milestone makes a sweep due at once (#374).
With `[docs] enabled`, each scan runs the docs-pass timer: the zero-model docs scan, then a docs-pass researcher session
only when the scan changed since the last report (docs/project-docs.md#docs-pass, #1026).
With `[reflection] enabled`, each scan runs the reflection timer (`mdstack reflection`'s tick): weekly and
milestone-close windows into a persistent ledger, one researcher reflection run at a time (docs/self-improve.md#reflection,
#1521).
Each scan also scales idle lifecycle role instances down to their min (`mdstack up`'s scale_down, #1231) and runs due
role routines (`mdstack up`'s routine_tick, #1247); the triage, docs and backstop timers take their cadence from the
researcher's and coordinator's routine files (docs/routines.md#terminal).
While every recorded run's item is held or owner-blocked (an open ask, or `held` in poll-state.json) and no lead has
pending work, the backstop waits its idle cap, at least 4 h from arming; each scan recomputes this both ways, so work
becoming held extends the wait and a run or lead message that can move restores the short backstop; ask deadlines and
poll wakes are unchanged, and `mdstack poll`'s `hold-released` wakes the coordinator when the owner lifts a hold (#394).

Usage: mdstack watch --project FILE [--org-profile FILE]
"""
import argparse
import contextlib
import datetime
import fcntl
import glob
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from crew_shared import BUSY, checkout, commands, CREW_BIN, dialog, ownership_module, ENGINE_CMD, foreground_matches, finished, GLYPHS, PROMPTS, gateway_error, HERE, heartbeat, idle_builder, paused, probe, proc, profile, queue_lock, receipts, remember_pr, remote_run, ROOT, runs, TRANSIENT, tmux, transient_lines

# Fields route adds to a record it leaves queued; a kept record still matches its candidate and wakes window 0 (#814).
ROUTE_NOTES = ("at", "route_error", "consumer", "dependents")
RATE_LIMITED = re.compile(r"rate-limited until (\S+Z)")  # mdstack poll's exit-75 line for a GitHub quota refusal
LEAD_RETRY = (60, 120, 240, 480, 900)  # seconds between lead-backstop retries of unchanged pending demand (#1715)
HELD_BACKSTOP = 4 * 3600  # seconds; the shortest backstop while every run is held or owner-blocked (#394)
LOCK_ENV = "MDSTACK_WATCH_LOCK"  # "<pid>:<fd>" of the held wake/watcher.lock, kept across a re-exec (#399)
RATE_HOLD_MAX = 3600  # seconds; GitHub's primary quota window, so a bad reset time never parks the sources for longer
CLAIM_STALE = 900  # seconds; a builder refreshes its claim heartbeat at least every 5 min (#1633)

def asks(state):
    """Open owner asks, asks/<n>.json {"deadline": ISO 8601 with UTC offset}: (n, deadline, epoch); an unreadable
    deadline is due now, so a bad record wakes the coordinator instead of dropping the timer (#287)."""
    d, found = os.path.join(state, "asks"), []
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if n.endswith(".json"):
            try:
                with open(os.path.join(d, n)) as f:
                    text = json.load(f)["deadline"]
                due = datetime.datetime.fromisoformat(text).timestamp()
            except FileNotFoundError:
                continue  # closed between listdir and open
            except (OSError, ValueError, KeyError, TypeError):
                text, due = "unreadable", 0.0
            found.append((n[:-5], text, due))
    return found


def pause(state, now, interval):
    """Seconds to the next scan: --interval, cut short so that a scan lands on the next open ask's deadline."""
    return min([interval] + [due - now for _, _, due in asks(state) if due > now])


def held(state):
    """Refs parked on the owner (#394): each open ask in asks/<n>.json and `held` in mdstack poll's last snapshot."""
    refs = {"#" + n for n, _, _ in asks(state)}
    with contextlib.suppress(OSError, ValueError, AttributeError, TypeError):
        with open(os.path.join(state, "poll-state.json")) as f:
            refs |= set(json.load(f).get("held", []))
    return refs


def in_flight(state):
    """"work" while anything can move without the owner: a lead's pending message, or a run whose item is not
    positively held (an unparsable item counts); "held" while every run is parked on the owner; else "nothing"."""
    if any(commands()["lead"].pending(state, n) for n, _ in commands()["lead"].records(state)):
        return "work"
    parked, items = held(state), [rec["item"] for _, rec in runs(state)]
    refs = [m.group(1) if (m := re.fullmatch(r"(?:issue|pr) (#\d+)", str(i), re.I)) else None for i in items]
    return "nothing" if not refs else "held" if all(r in parked for r in refs) else "work"


def work(state, name, rec):
    """Queued or in-flight work: a lead's undone inbox messages, a synthesizer's unacked messages, uncompleted lands,
    open trains or held land lock; other roles always count as working."""
    if rec["role"].endswith("-lead"):
        return bool(commands()["lead"].pending(state, name))
    if rec["role"] == "synthesizer":
        with queue_lock(state):
            return commands()["route"].synthesizer_busy(state, name)
    return True


def run_identity(rec):
    """The run behind a window name: a respawn under the same name differs (#1092), and so does a team run's new
    execution generation (its run ID, #1858)."""
    return [rec.get(k) for k in ("start", "pane_id", "pane_pid", "pane_start", "worktree")] + (
        [rec["run_id"]] if rec.get("run_id") else [])


def pull_hosts(values, state, seen, now, stale):
    """One `pull` per role host with runs; each host's last result, time and run probes under seen["pulls"]. Pulls
    failing in a row are an outage (#347): its runs are unreachable, keep their claims and are never restarted or
    re-placed; past stale, one escalate wake per outage. The first ok pull after it reconciles (a refused or failed
    reply keeps it pending): the pull brings the missed lines and each run's probe, a dead or missing run wakes for tmux's restart rules on that host, and the
    coordinator re-reads GitHub. A tombstoned run is stopped on its host once the host answers. Returns the wakes."""
    hosts, recs = {}, dict(runs(state))
    for name, rec in recs.items():
        if remote_run.host_of(rec):
            hosts.setdefault(rec["host"], []).append(name)
    pulls, wakes = seen.setdefault("pulls", {}), []
    for host in [h for h in pulls if h not in hosts]:
        del pulls[host]  # no run left there: a later run starts with no outage
    for host, names in sorted(hosts.items()):
        before, reply = pulls.get(host, {}), remote_run.pull(values, state, host, names)
        liveness = {n: w.get("liveness") for n, w in (reply.get("windows") or {}).items()}
        fails = before.get("fails", 0) + 1 if reply["result"] == "unreachable" else 0
        pulls[host] = entry = dict(at=now, result=reply["result"], liveness=liveness, fails=fails, **({} if reply[
            "result"] == "ok" else {"error": reply.get("reason") or reply.get("error")}))
        pending = before.get("reconcile") or (before.get("since") if before.get("fails", 0) >= remote_run.OUTAGE else
                                               None)  # an outage's start, kept until an ok pull brings the run probes
        if fails:
            entry.update({k: before[k] for k in ("since", "escalated", "reconcile") if k in before})
            since = entry.setdefault("since", now)
            if fails >= remote_run.OUTAGE:
                entry.setdefault("reconcile", since)
            if fails >= remote_run.OUTAGE and now - since >= stale and "escalated" not in entry:
                entry["escalated"] = now
                wakes.append({"reason": "unreachable", "host": host, "action": "escalate", "event": (
                    "%s unreachable since %s: %s; claims kept, never restarted or re-placed" % (
                        host, utc(since), ", ".join(names)))})
        elif pending and reply["result"] != "ok":
            entry["reconcile"] = pending  # refused or failed: the host answers, but without the probes
        elif pending:
            wakes.append({"reason": "reconcile", "host": host, "event": "%s answers after an outage since %s: %s; "
                          "re-read GitHub (protocol 6 step 1)" % (host, utc(pending), ", ".join(
                              "%s %s" % (n, liveness.get(n)) for n in names))})
            wakes += [{"reason": "stale", "window": n, "liveness": liveness[n], "silent": int(now - pending),
                       "action": "restart" if not recs[n].get("restarts") else "escalate"}
                      for n in names if liveness.get(n) in ("dead", "missing")]
    for name, t in remote_run.tombstones(state):
        if pulls.get(t["host"], {}).get("fails"):
            continue  # still away; the scan it answers stops the run
        reply = remote_run.reconcile_tombstone(values, state, name, t)
        if reply["result"] == "ok":
            wakes.append({"reason": "reconcile", "host": t["host"], "event": "%s: tombstoned %s stopped; %s" % (
                t["host"], name, "worktree kept, unlanded: " + "; ".join(reply["unlanded"]) if reply["unlanded"]
                else "clean worktree removed")})
    return wakes


def acked_work(state, name):
    """Whether a run's status acknowledges an inbox message with no done:, blocked: or failed: after it (#1633)."""
    try:
        with open(os.path.join(state, "status", name + ".status"), "rb") as f:
            lines = [raw.decode("utf-8", "replace") for raw in f]
    except FileNotFoundError:
        return False
    receipt = set(receipts(state, name).values())  # the one receipt rule: an ack before its message's record is none
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith(("done:", "blocked:", "failed:")):
            return False
        if i in receipt:
            return True
    return False


def silent_claim(state, session, name, rec, cls, now):
    """An alive builder's claim heartbeat time when it is older than CLAIM_STALE while the builder holds acknowledged
    unfinished work, its item is not held and its harness is not mid-turn; else None. A supervisor heartbeat on the
    status file never refreshes the claim, so this catches a worker idle after an API error (#1633)."""
    if rec["role"] != "builder" or cls != "alive" or not rec.get("claim") or not acked_work(state, name):
        return None
    try:
        beat = os.path.getmtime(rec["claim"])
    except OSError:
        return None
    ref = re.fullmatch(r"(?:issue|pr) (#\d+)", str(rec.get("item", "")).split(",")[0], re.I)
    if now - beat <= CLAIM_STALE or ref and ref.group(1) in held(state):
        return None
    screen = tmux.capture(session, rec["index"]).lower()
    return None if any(b.search(screen) for b in BUSY) else beat


def deliveries(state, session, windows, seen, mine):
    """Token-free re-probe of workers' pending deliveries (#1850, D2.4): one `delivery` wake when a message's delivery,
    worker or action changed since the last scan to one needing the lead (nudge, restart, escalate); a first sight,
    busy or held waits, and an unchanged state never wake. The book in seen keeps only still-pending ids."""
    book, live = seen.get("deliveries", {}), {}
    wakes = []
    for name, rec in runs(state):
        for d in [] if remote_run.host_of(rec) else commands()["send"].pending(state, session, name, rec, windows, mine):
            key, now = "%s %s" % (name, d["id"]), [d["delivery"], d["worker"], d["action"]]
            live[key] = now
            if book.get(key, now) != now and d["action"] in ("nudge", "restart", "escalate"):
                wakes.append({"reason": "delivery", "window": name, "id": d["id"], "delivery": d["delivery"],
                              "worker": d["worker"], "disposition": d["disposition"], "action": d["action"],
                              "event": "%s %s: %s, %s" % (name, d["id"], d["reason"], d["action"])})
    seen["deliveries"] = live
    return wakes


def utc(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def stall(state, seen, name, now, since=None, liveness=None):
    """A stale wake opens one sanitized stall sample (since = last progress); without since, the run's next status
    line closes the open one. A replayed scan repeats (key, kind, since), which reflection-measures dedupes (#1524)."""
    stalled = seen.setdefault("stalled", {})
    if since is None and name not in stalled:
        return
    record = {"kind": "stall", "since": since, "liveness": liveness} if since else {"kind": "resume",
                                                                                      "since": stalled.pop(name)}
    if since:
        stalled[name] = since
    commands()["poll"].observe(state, dict(record, ts=utc(now), source="watch", key="run:" + name))


def scan(state, session, now, stale, seen, idle_ttl=1800, stuck_after=1800, idle_stall=1800, schedule_home=None,
         repo=None, mine=None):
    """Wake records: new status lines, runs dead, missing or silent past stale, owner asks past their deadline and
    finishing work deferred past stuck_after (in a team, this repo's from the team schedule at schedule_home); each
    fires once per key. A working run whose pane printed nothing for
    idle_stall seconds is idle at its prompt and wakes stale (liveness `idle`), however fresh its status file (#1283)."""
    windows = dict((n, i) for i, n in tmux.list_windows(session))
    wakes = []
    for name, rec in list(runs(state)) + list(commands()["lead"].records(state)):
        identity = run_identity(rec)
        identities = seen.setdefault("runs", {})
        changed = name in identities and identities[name] != identity
        if changed:
            seen["keys"].pop(name, None)
        identities[name] = identity
        previous_pr = rec.get("pr")
        status = os.path.join(state, "status", name + ".status")
        if remote_run.host_of(rec) and not os.path.exists(status):
            continue  # a role host's mirror not pulled yet, or removed until the next pull rebuilds it: offsets kept
        size, off = os.path.getsize(status) if os.path.exists(status) else 0, seen["offsets"].get(name, 0)
        digests = seen.setdefault("digests", {})
        if size and (size != off or changed):
            with open(status, "rb") as f:
                data = f.read()
            # the read prefix, not the run identity, decides: a restart keeping its file never replays it (#819);
            # an offset saved before digests existed is trusted
            prefix = hashlib.sha256(data[:off]).hexdigest()
            if off > len(data) or digests.get(name, prefix) != prefix:
                off = 0  # shorter than seen or rewritten: a new run's file
            for line in data[off:].decode("utf-8", "replace").splitlines():
                remember_pr(rec, line)
                if line.strip():
                    wakes.append({"reason": "status", "window": name, "line": line, "run": identity})
                    stall(state, seen, name, now)
            size = len(data)
            digests[name] = hashlib.sha256(data).hexdigest()
        elif not size:
            digests.pop(name, None)
        seen["offsets"][name] = size
        if rec.get("pr") != previous_pr:
            path = os.path.join(state, "runs", name + ".json")
            with open(path + ".tmp", "w") as f:
                json.dump(rec, f, indent=2)
            os.replace(path + ".tmp", path)
        try:
            if not rec.get("start") and now - os.path.getmtime(os.path.join(state, "runs", name + ".json")) < 60:
                continue  # spawn saves its record before the window and pane identity; an older record is a failed spawn
        except FileNotFoundError:
            continue  # reaped between listing and stat (#591)
        last, beat = heartbeat(state, name)
        if beat is None or remote_run.host_of(rec):  # a role host's run wakes by its pulled status lines (#346)
            continue
        cls = probe(session, name, rec, windows)
        if cls in ("alive", "ambiguous") and rec.get("harness") in TRANSIENT:
            for line in transient_lines(tmux.capture(session, rec["index"]), rec["harness"]):
                gateway_error(state, name, line, now, once=True)
        if cls == "quota" and not finished(rec, last):
            if seen["keys"].get(name) != "quota":  # once per run: a new identity clears the key
                seen["keys"][name] = "quota"
                wakes.append({"reason": "quota", "window": name, "liveness": cls, "engine": rec.get("engine"),
                              "run": identity, "action": "escalate" if rec.get("restarts") else "restart"})
            continue
        idle = idle_builder(state, name) if rec["role"] == "builder" and cls == "alive" else None
        if idle_ttl and idle is not None and now - idle >= idle_ttl:
            key = "idle %s" % idle
            if seen["keys"].get(name) != key:
                seen["keys"][name] = key
                wakes.append({"reason": "idle-builder", "window": name, "event": "idle expiry"})
            continue
        if cls == "ambiguous" and not finished(rec, last) and dialog(session, rec["index"]):
            if seen["keys"].get(name) != "dialog %s" % beat:  # wakes on the next scan, never after --stale (#234 N3)
                seen["keys"][name] = "dialog %s" % beat
                wakes.append({"reason": "dialog", "window": name, "liveness": cls, "silent": int(now - beat),
                              "action": "escalate"})
            continue
        p = tmux.pane(session, rec["index"]) if cls == "alive" and idle_stall else None
        quiet = now - float(p["activity"]) if p and float(p["activity"]) else None  # herdr reports no activity ("0")
        if quiet is not None and quiet >= idle_stall and not finished(rec, last) and not last.startswith("done:") and \
                work(state, name, rec):
            key = "idle %s" % p["activity"]  # a self-refreshed claim or status file never hides it (#1283)
            if seen["keys"].get(name) != key:
                seen["keys"][name] = key
                wakes.append({"reason": "stale", "window": name, "liveness": "idle", "silent": int(quiet),
                              "action": "escalate"})
                stall(state, seen, name, now, utc(float(p["activity"])), "idle")
            continue
        claim = silent_claim(state, session, name, rec, cls, now)
        if claim is not None:
            key = "claim %s" % claim  # once per claim silence, whatever the status file's supervisor heartbeat
            if seen["keys"].get(name) != key:
                seen["keys"][name] = key
                wakes.append({"reason": "stale", "window": name, "liveness": "claim", "silent": int(now - claim),
                              "run": identity, "action": "escalate"})
                stall(state, seen, name, now, utc(claim), "claim")
            continue
        if finished(rec, last) or (cls in ("alive", "ambiguous") and (last.startswith("done:") or now - beat <= stale)):
            continue  # a live builder after done: waits for its inbox; a dead one is restartable (#139 F4)
        p = tmux.pane(session, rec["index"]) if cls in ("alive", "ambiguous") else None
        if p and p["dead"] == "0" and (p["id"], p["pid"]) == (rec.get("pane_id"), rec.get("pane_pid")) and \
                proc.proc_start(p["pid"]) == rec.get("pane_start") and \
                (now - float(p["activity"]) <= stale or proc.live_child(p["pid"], rec["harness"])):
            with open(status, "a") as f:
                f.write("heartbeat: %s\n" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)))
            os.utime(status, (now, now))
            continue
        if cls in ("alive", "ambiguous") and not work(state, name, rec):
            continue  # an idle lead or synthesizer has nothing to progress; dead or missing still wakes (#578)
        key = "stale %s" % beat  # not the class: an ambiguous -> alive flip is the same silence (#234 N4)
        if seen["keys"].get(name) != key:
            seen["keys"][name] = key
            wakes.append({"reason": "stale", "window": name, "liveness": cls, "silent": int(now - beat), "run": identity,
                          "action": "restart" if cls in ("dead", "missing") and not rec.get("restarts") else "escalate"})
            stall(state, seen, name, now, utc(beat), cls)
    wakes += deliveries(state, session, windows, seen, mine or (lambda env: isinstance(env, dict)))
    for n, text, due in asks(state):  # whatever the backstop: the ask's §6 auto-apply time (tmux.md C8)
        if now >= due and seen["keys"].get("ask " + n) != text:  # once per (ask, deadline)
            seen["keys"]["ask " + n] = text
            wakes.append({"reason": "ask", "event": "%s deadline %s" % (n, text)})
    schedule = commands()["schedule"]
    found = schedule.read(schedule.stuck, schedule_home or state, now, stuck_after, repo)
    for d in [] if found == schedule.UNKNOWN else found:
        if seen["keys"].get("stuck %s %s" % (d["pool"], d["ref"])) != d["since"]:
            seen["keys"]["stuck %s %s" % (d["pool"], d["ref"])] = d["since"]
            line = schedule.read(schedule.latest, schedule_home or state)
            wakes.append({"reason": "schedule-stuck", "snapshot": line["snapshot"] if isinstance(line, dict) else None,
                          "event": "%s %s %s class %s deferred since %s: %s" % (
                              d["pool"], d["ref"], d["kind"], d["class"], d["since"], ", ".join(d["reasons"]))})
    for name, _ in commands()["lead"].records(state):
        retries, lead = seen.setdefault("lead_retries", {}), commands()["lead"]
        demand = sorted(m["id"] for m in lead.actionable(state, name))  # unchanged acknowledged waits never retry
        checks = seen.setdefault("lead_admission", {})
        if set(demand) & lead.deferred_ids(state, name):  # token-free: route nudges only once the ref is admissible
            if now >= checks.setdefault(name, now + LEAD_RETRY[0]):
                wakes.append({"reason": "lead-backstop", "window": name, "event": "admission recheck"})
                checks[name] = now + LEAD_RETRY[0]
        else:
            checks.pop(name, None)
        if not demand:
            retries.pop(name, None)
            continue
        woke = {i for i, w in lead.waits(state, name).items() if w["woke"]}
        prior = retries.get(name)
        if not isinstance(prior, dict) or prior["demand"] != demand:  # changed demand restarts at the first step
            fresh = set(demand) - set(prior["demand"] if isinstance(prior, dict) else [])
            prior = retries[name] = {"demand": demand, "step": 0, "due": now if fresh & woke else now + LEAD_RETRY[0]}
        if now >= prior["due"]:
            wakes.append({"reason": "lead-backstop", "window": name, "event": "admission retry"})
            prior["step"] += 1
            prior["due"] = now + LEAD_RETRY[min(prior["step"], len(LEAD_RETRY) - 1)]
    return wakes


def routine(role, name):
    """A migrated role routine the watcher runs natively on its timers (#1247, docs/routines.md): its cadence, retry
    and enable switch come from roles/<team>/<role>/routines/<name>.toml."""
    return commands()["up"].ROUTINES[(role, name)]


def sweep_queued(state):
    """Whether spawn-queue.jsonl still holds a triage sweep request; an unreadable queue counts as holding one."""
    try:
        with open(os.path.join(state, "spawn-queue.jsonl")) as f:
            return any(json.loads(line).get("sweep") for line in f if line.strip())
    except FileNotFoundError:
        return False
    except (OSError, ValueError, AttributeError):
        return True


def triage_tick(values, state, now, project, org_profile=None):
    """Triage sweep timer: once `[triage] interval_hours` passed since the last slot in triage/sweep.json (at once when
    none is recorded, so a crew waking overdue sweeps on its first scan), start `mdstack spawn researcher --sweep`. The slot
    is skipped when triage/queue.json lists no items (`mdstack poll` queues unplaced issues and owner replies there); an
    unreadable queue sweeps (docs/triage.md#inputs). A failed spawn retries after the routine's retry. Returns the new slot's
    outcome, or None when disabled or not due. A queued closed milestone that no sweep started with yet makes the slot due
    at once, retried as above, unless the last slot queued a sweep still in spawn-queue.jsonl, which takes it when it starts
    (T6, #374); once that sweep was dequeued, a later closed milestone is due at once again (#1175)."""
    sweep = routine("researcher", "triage-sweep")  # milestone-close-sweep shares its slot
    routines = commands()["up"].crew_routines
    if not routines.enabled(sweep, values):
        return None
    path = os.path.join(state, "triage", "sweep.json")
    try:
        with open(os.path.join(state, "triage", "queue.json")) as f:
            empty = json.load(f)["items"] == []
    except (OSError, ValueError, KeyError, TypeError):
        empty = False
    milestones = commands()["poll"].triage_untaken(state)
    try:
        with open(path) as f:
            last = json.load(f)
        retry = last["outcome"].startswith("failed")
        wait = routines.seconds(sweep["retry"]) if retry else routines.interval(sweep, values)
        if now - last["at"] < wait and (retry or not milestones or last["outcome"] == "queued" and sweep_queued(state)):
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass  # never swept, or an unreadable record: due now
    if empty and not milestones:
        outcome = "skipped: empty queue"
    else:
        cmd = [sys.executable, CREW_BIN, "spawn", "researcher", "--sweep", "--project", project]
        try:
            r = subprocess.run(cmd + (["--org-profile", org_profile] if org_profile else []),
                               capture_output=True, text=True, timeout=120)
            out = (r.stdout.strip().splitlines() or ["exit %d" % r.returncode])[-1]
            outcome = ("queued" if out.startswith("queued:") else "started") if r.returncode == 0 else "failed: " + out
        except subprocess.TimeoutExpired:
            outcome = "failed: spawn timed out"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump({"at": now, "outcome": outcome}, f)
    os.replace(path + ".tmp", path)
    return outcome


def scan_digest(values, state):
    """Digest of every `[docs] repos` scan.json with the head, scan date and banner ages left out, so a scan whose
    findings and inventory did not change matches; None when one is unreadable, which never counts as unchanged."""
    out = hashlib.sha256()
    for repo in values["docs.repos"]:
        try:
            with open(os.path.join(os.path.dirname(state), repo.replace("/", "__"), "docs", "scan.json")) as f:
                data = json.load(f)
            for key in ("head", "scanned"):
                data.pop(key, None)
            for item in data.get("stale", []):
                item.pop("age_days", None)
            out.update(json.dumps([repo, data], sort_keys=True).encode())
        except (OSError, ValueError, AttributeError, TypeError):
            return None
    return out.hexdigest()


def docs_tick(values, state, now, project, org_profile=None):
    """Docs-pass timer: once `[docs] interval_days` passed since the last slot in docs/pass.json (at once when none is
    recorded, so a crew waking with a pass overdue runs it on its first scan), fetch the default branch into the
    project's checkout, run `docs-scan.py` on it (no model), then start `mdstack spawn researcher --docs-pass`. The slot is
    skipped when the scans digest as the slot that last started or queued a pass (the last report) recorded. A failed
    scan or spawn retries after the routine's retry. Returns the new slot's outcome, or None when disabled or not due. The timer
    passes only the project's own checkout, so another `[docs] repos` entry fails the scan (docs/project-docs.md#triggers)."""
    docs, routines = routine("researcher", "docs-pass"), commands()["up"].crew_routines
    if not routines.enabled(docs, values):
        return None
    path, reported = os.path.join(state, "docs", "pass.json"), None
    try:
        with open(path) as f:
            last = json.load(f)
        reported = last.get("reported")
        wait = routines.seconds(docs["retry"]) if last["outcome"].startswith("failed") else routines.interval(docs, values)
        if now - last["at"] < wait:
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass  # never run, or an unreadable record: due now
    org = ["--org-profile", org_profile] if org_profile else []
    repo = checkout(values, project)
    try:
        repo = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              timeout=60).stdout.strip() or repo
        subprocess.run(["git", "-C", repo, "fetch", "-q", "origin", values["repo.default_branch"]], capture_output=True,
                       timeout=120)  # a failed fetch scans the last fetched head
        r = subprocess.run([sys.executable, os.path.join(HERE, "docs-scan.py"), "--project", project, "--checkout",
                            "%s/%s=%s" % (values["repo.owner"], values["repo.name"], repo)] + org,
                           capture_output=True, text=True, timeout=300)
        digest = None if r.returncode else scan_digest(values, state)
        if r.returncode:
            outcome = "failed: scan: " + ((r.stderr.strip() or r.stdout.strip()).splitlines() or ["exit %d" % r.returncode])[-1]
        elif digest is not None and digest == reported:
            outcome = "skipped: scan unchanged"
        else:
            r = subprocess.run([sys.executable, CREW_BIN, "spawn", "researcher", "--docs-pass",
                                "--project", project] + org, capture_output=True, text=True, timeout=120)
            out = (r.stdout.strip().splitlines() or ["exit %d" % r.returncode])[-1]
            outcome = ("queued" if out.startswith("queued:") else "started") if r.returncode == 0 else "failed: " + out
            reported = digest if r.returncode == 0 else reported
    except subprocess.TimeoutExpired as e:
        outcome = "failed: timed out: " + " ".join(os.path.basename(str(a)) for a in e.cmd[:3])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump({"at": now, "outcome": outcome, "reported": reported}, f)
    os.replace(path + ".tmp", path)
    return outcome


def armed(pidfile):
    """PID of another live `mdstack watch` named in wake/watcher.pid, else None; a stale or reused PID is not armed."""
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return None
    command = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return pid if "watch" in command.split() else None


def hold_lock(wake):
    """Take wake/watcher.lock exclusively for this process's life (#399); the fd, or None while another watcher holds
    it. A re-exec'd watcher (same PID) reuses the fd it inherited, so the lock is never released in between. A short
    retry outlasts `mdstack guard`'s instant probe."""
    pid, _, fd = os.environ.get(LOCK_ENV, "").partition(":")
    if pid == str(os.getpid()) and fd.isdigit():
        return int(fd)
    fd = os.open(os.path.join(wake, "watcher.lock"), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + 1
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)  # the holder's PID, which survives a lost wake/watcher.pid (holder)
            os.write(fd, b"%d\n" % os.getpid())
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(0.05)


def holder(wake):
    """The live watcher holding wake/watcher.lock: its PID from the lock file, -1 when held under an unreadable or
    foreign PID, None when free. Works with wake/watcher.pid lost (#399); the probe holds the lock for an instant."""
    try:
        fd = os.open(os.path.join(wake, "watcher.lock"), os.O_RDONLY)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return None
    except BlockingIOError:
        return armed(os.path.join(wake, "watcher.lock")) or -1
    finally:
        os.close(fd)


def prompt_open(session, index):
    """A blocking harness prompt on the pane, whose Enter could approve a command (#315). Unlike dialog(), a fatal API
    error over an idle composer is not one: a coordinator stopped by a gateway error still gets its wake (#1346)."""
    lines = [line.strip().lstrip(GLYPHS + "> ") for line in tmux.capture(session, index).splitlines() if line.strip()]
    return bool(lines) and any(foot.match(lines[-1]) and any(head.match(line) for line in lines)
                               for head, foot in PROMPTS)


def reason(w):
    if "event" in w:
        return "%s: %s" % (w["reason"], w["event"])
    if "line" in w:
        return "status: %s %s" % (w["window"], w["line"])
    return "%s: %s %s, silent %ds, %s" % (w["reason"], w["window"], w["liveness"], w["silent"], w["action"])


def queue_sig(wake):
    """(inode, byte size, mtime) of wake/queue.jsonl, or None; a change means records were appended or drained."""
    try:
        st = os.stat(os.path.join(wake, "queue.jsonl"))
    except FileNotFoundError:
        return None
    return [st.st_ino, st.st_size, st.st_mtime_ns]


def queued(state, wake, seen):
    """Records appended to queue.jsonl since the offset in seen (another poller's); never queued again."""
    with queue_lock(state):
        sig, old = queue_sig(wake), seen.get("queue")
        if sig == old or sig is None:
            seen["queue"] = sig
            return []
        with open(os.path.join(wake, "queue.jsonl"), encoding="utf-8") as f:
            f.seek(old[1] if old and old[0] == sig[0] and sig[1] > old[1] else 0)  # else drained: a new file
            lines = f.read().splitlines()
        seen["queue"] = sig
    records = []
    for line in lines:
        with contextlib.suppress(ValueError):  # a source killed mid-append leaves a partial line
            records.append(json.loads(line))
    return records


def code_sig():
    """mtimes of the crew CLI and the modules it loads; a change means a tooling update landed under this watcher."""
    paths = [os.path.join(ROOT, "cli", "mdstack")] + glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "*.py"))
    for module in ("scripts", "core", "environments/terminal", "environments/terminal/remote", "harnesses", "connectors/github"):
        paths += glob.glob(os.path.join(ROOT, module, "crew-*.py"))
    return sorted((p, os.stat(p).st_mtime_ns) for p in paths if os.path.exists(p))


def reexec(lock):
    """Replace this process with a fresh `mdstack watch` on the same argv; the PID, so wake/watcher.pid, and the held
    wake/watcher.lock are kept."""
    os.set_inheritable(lock, True)
    os.environ[LOCK_ENV] = "%d:%d" % (os.getpid(), lock)
    sys.stdout.flush()
    print("crew: watch: crew code changed on disk; re-exec", file=sys.stderr, flush=True)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def rate_hold(error, now):
    """Epoch until which a rate-limited source's reset holds every --source, capped at RATE_HOLD_MAX; 0 for none."""
    if m := RATE_LIMITED.search(error):
        with contextlib.suppress(ValueError):
            return min(datetime.datetime.fromisoformat(m[1]).timestamp(), now + RATE_HOLD_MAX)
    return 0


def source_failure(wake, seen, cmd, error, limit):
    """Record one transient source failure in wake/incidents.jsonl; return a wake only at the limit-th in a row."""
    failures = seen.setdefault("source_failures", {})
    n = failures[cmd] = failures.get(cmd, 0) + 1
    with open(os.path.join(wake, "incidents.jsonl"), "a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": cmd, "error": error,
                            "consecutive": n}) + "\n")
    if n < limit:
        return []
    failures[cmd] = 0
    return [{"reason": "source-failing", "event": "%s: %d failures in a row, last: %s" % (cmd, n, error)}]


def nudge(args, session, state, wake, seen):
    """Type `wake: watcher` into an idle window-0 coordinator; one showing a dialog gets a queued `dialog` wake
    instead, which is returned (#315); an API error over an idle composer gets the wake (#1346)."""
    p = None if args.no_nudge else tmux.pane(session, 0)
    if not (p and foreground_matches(ENGINE_CMD.values(), {p["command"], *tmux.foreground(p["tty"])}) and
            time.time() - float(p["activity"]) > args.idle):
        return None
    if prompt_open(session, 0):  # never type into a prompt: its Enter could approve a command (#315)
        w = {"reason": "dialog", "window": dict(tmux.list_windows(session)).get(0, "0"),
             "liveness": "ambiguous", "silent": int(time.time() - float(p["activity"])), "action": "escalate"}
        with queue_lock(state), open(os.path.join(wake, "queue.jsonl"), "a") as f:
            f.write(json.dumps(dict(w, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))) + "\n")
            f.flush()
            seen["queue"] = queue_sig(wake)
        return w
    if "doorbell" in tmux.CAPABILITIES:
        if error := commands()["send"].nudge(session, 0, "wake: watcher"):
            print("crew: coordinator nudge not submitted: " + error)
    else:
        tmux.send_keys(session, 0, "wake: watcher")  # the Codex-recipe path, for when exit alone wakes nobody
    return None


def announce(args, session, state, wake, seen, wakes, schedule_home=None):
    """Wake the coordinator for retained wakes: the nudge, then one reason line and the schedule summary (a team's
    from its team root, schedule_home)."""
    wakes = wakes + [w for w in [nudge(args, session, state, wake, seen)] if w]
    print(reason(wakes[0]) + (" (+%d more in wake/queue.jsonl)" % (len(wakes) - 1) if len(wakes) > 1 else ""))
    if (line := commands()["schedule"].read(commands()["schedule"].summary, schedule_home or state)) not in (None, "unknown"):
        print(line)
    sys.stdout.flush()


def start_persistent(state, argv):
    """Start `mdstack watch --persistent ARGV` in its own session, so it outlives the shell or coordinator turn that
    started it, its output appended to wake/watcher.log (#1346); prints and returns 0, also when one is armed."""
    wake = os.path.join(state, "wake")
    os.makedirs(wake, exist_ok=True)
    if pid := armed(os.path.join(wake, "watcher.pid")):
        print("crew: a watcher is already armed (pid %d)" % pid)
        return 0
    with open(os.path.join(wake, "watcher.log"), "a") as log:
        p = subprocess.Popen([sys.executable, CREW_BIN, "watch", "--persistent", *argv], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    print("crew: persistent watcher started (pid %d, log %s)" % (p.pid, os.path.join(wake, "watcher.log")))
    return 0


def backstop_wait(flight, idle, backstop, backoff):
    """Seconds to the backstop: x2 per idle wake up to backoff times; held-only work waits that cap, at least 4 h."""
    return max(backstop * backoff, HELD_BACKSTOP) if flight == "held" else min(backstop * 2 ** idle, backstop * backoff)


def backstop_deadline(state, seen, backstop, backoff):
    """(in_flight, monotonic arm time, monotonic time of the next backstop wake); work resets the idle count."""
    flight, now = in_flight(state), time.monotonic()
    seen["idle"] = 0 if flight == "work" else seen["idle"]
    return flight, now, now + backstop_wait(flight, seen["idle"], backstop, backoff)


def register(sub):
    p = sub.add_parser("watch")
    p.add_argument("--stale", type=float, default=900, help="seconds without status progress before a stale wake")
    p.add_argument("--backstop", type=float, help="seconds to a backstop wake, x2 per idle wake up to idle_backoff "
                   "times (default: the coordinator's stale-sweep routine, 30m and x16)")
    p.add_argument("--idle-stall", type=float, default=1800,
                   help="seconds with no pane output before a working run counts as idle at its prompt (0: off)")
    p.add_argument("--interval", type=float, default=5, help="seconds between scans")
    p.add_argument("--source-timeout", type=float, default=60, help="seconds before a --source run is cut off")
    p.add_argument("--source-interval", type=float,
                   help="seconds between --source runs (default: runtime.options.poll_interval)")
    p.add_argument("--source-failures", type=int, default=3,
                   help="consecutive source timeouts or exit-75 failures before one source-failing wake")
    p.add_argument("--source", action="append", default=[],
                   help="one-shot event command (mdstack poll --once); each stdout line is a poll wake")
    p.add_argument("--no-nudge", action="store_true", help="do not type the wake line into an idle coordinator")
    p.add_argument("--idle", type=float, default=30, help="seconds with no coordinator output that count as idle")
    p.add_argument("--persistent", action="store_true",
                   help="nudge the coordinator and keep scanning instead of exiting on a coordinator wake (#1346)")
    p.add_argument("--renudge", type=float, default=300,
                   help="with --persistent, seconds before an undrained wake/queue.jsonl is nudged again")
    p.add_argument("--detach", action="store_true",
                   help="start a --persistent watcher in its own session (log: wake/watcher.log) and return")
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    """Zero-token watcher: block on status files, liveness, owner-ask deadlines, one-shot --source commands and
    queue growth; queue wakes, then exit."""
    values, session, state = profile(args)
    schedule = commands()["schedule"]  # a team repo's stuck work and summary come from the team schedule (#1857)
    home, repo = schedule.home(values, state), schedule.canonical(values) if values.get("team.name") else None
    if args.detach:
        argv = sys.argv[sys.argv.index("watch") + 1:]
        return start_persistent(state, [a for a in argv if a not in ("--detach", "--persistent")])
    wake = os.path.join(state, "wake")
    os.makedirs(wake, exist_ok=True)
    path, pidfile = os.path.join(wake, "watch-state.json"), os.path.join(wake, "watcher.pid")
    lock = hold_lock(wake)
    if lock is None:  # one watcher per state dir: leave its PID file and state alone (#591, #399)
        other = "unknown"
        with contextlib.suppress(OSError):
            with open(pidfile) as f:
                other = f.read().strip() or other
        print("crew: a watcher is already armed (pid %s)" % other)
        return 0
    with open(pidfile, "w") as f:  # published under the lock, so a refused start can name this watcher
        f.write("%d\n" % os.getpid())
    if ownership_module.status(values) == "lost":  # prompt stop: never re-armed once ownership moved away
        os.remove(pidfile)
        print("crew: ownership: lost; watcher not armed (run mdstack down, then mdstack handoff stopped)")
        return 1
    seen = {"offsets": {}, "keys": {}, "idle": 0, "queue": None}
    if os.path.exists(path):
        with open(path) as f:
            seen.update(json.load(f))

    def save(data):
        with open(path + ".tmp", "w") as f:
            json.dump(data, f)
        os.replace(path + ".tmp", path)

    held, sleeping = [], False  # a signal is held while a child may be starting, so none is orphaned (#272)

    def stop(signum, _frame):
        held.append(signum)
        if sleeping or len(held) > 1:  # between scans, or a second signal: exit at once
            raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):  # a killed watcher removes its PID file, saves offsets
        signal.signal(sig, stop)
    sweep = routine("coordinator", "stale-sweep")  # the team head's backstop (#1247)
    backstop = args.backstop or commands()["up"].crew_routines.interval(sweep, values)
    backoff = sweep.get("idle_backoff", 1)
    flight, armed_at, deadline = backstop_deadline(state, seen, backstop, backoff)  # backs off when idle
    code = code_sig()
    source_interval = values["runtime.options.poll_interval"] if args.source_interval is None else args.source_interval
    try:
        while True:
            hold = paused(state) is not None  # observation mode: no timer, scan, route or nudge (#1714)
            if not hold:
                docs_tick(values, state, time.time(), args.project, args.org_profile)
                commands()["up"].scale_down(values, session, state, time.time())  # idle lifecycle instances (#1231)
            missed = [] if hold else commands()["up"].routine_tick(args, values, state, time.time())  # (#1247)
            found = commands()["notify"].tick(values, state, time.time())
            found = [w for w in found if seen["keys"].get("notify-digest") != [w["entry"], w["slot"]]]
            for w in found:
                seen["keys"]["notify-digest"] = [w["entry"], w["slot"]]
            found += missed
            due = args.source and time.time() >= seen.get("sources_next", 0)
            if due:  # GitHub reads at most once per source interval, however short the scan --interval (#1300)
                seen["sources_next"] = time.time() + source_interval
                if args.persistent and ownership_module.status(values) == "lost":  # prompt stop (#212)
                    print("crew: ownership: lost; persistent watcher stopped", flush=True)
                    return 1
            for cmd in args.source if due else []:  # one-shot commands, each cut off at the source timeout
                before = queue_sig(wake)
                try:
                    r = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=args.source_timeout)
                except subprocess.TimeoutExpired:
                    found += source_failure(wake, seen, cmd, "timed out after %gs" % args.source_timeout,
                                            args.source_failures)
                    continue
                out = r.stdout
                if r.returncode == os.EX_TEMPFAIL:
                    error = (out.strip().splitlines() or ["exit %d" % r.returncode])[-1]
                    seen["sources_next"] = max(seen["sources_next"], rate_hold(error, time.time()))
                    found += source_failure(wake, seen, cmd, error, args.source_failures)
                    continue
                seen.get("source_failures", {}).pop(cmd, None)
                if queue_sig(wake) == before:  # a source that queues its own records (mdstack poll) is not re-queued
                    found += [{"reason": "poll", "event": line} for line in out.splitlines() if line.strip()]
            if hold:  # the events stay queued for after mdstack resume; status lines and host pulls wait
                if found:
                    with queue_lock(state), open(os.path.join(wake, "queue.jsonl"), "a") as f:
                        for w in found:
                            f.write(json.dumps(dict(w, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))) + "\n")
                    seen["queue"] = queue_sig(wake)
                save(seen)
                sleeping = True
                if held:
                    raise SystemExit(128 + held[0])
                time.sleep(pause(state, time.time(), args.interval))
                sleeping = False
                continue
            # after the sources: the timer reads the queue this scan's mdstack poll wrote, not a pre-pause one (#1098)
            triage_tick(values, state, time.time(), args.project, args.org_profile)
            commands()["reflection"].tick(values, state, time.time(), args.project, args.org_profile)  # #1521
            if time.time() >= seen.get("pulls_next", 0):  # role hosts' status lines into their mirrors (#346)
                seen["pulls_next"] = time.time() + values["runtime.options.host_scan_interval"]
                found += pull_hosts(values, state, seen, time.time(), args.stale)
            trial = json.loads(json.dumps(seen))  # committed only once its wakes are queued
            wakes = scan(state, session, time.time(), args.stale, trial, values["runtime.options.idle_builder_ttl"],
                         values["runtime.options.stuck_after"], args.idle_stall, home, repo,
                         commands()["send"].ours(args.project, args.org_profile, values)) + found
            others = queued(state, wake, trial)
            if code_sig() != code and not held:  # before route resolves the live profile with old code (#702)
                reexec(lock)  # trial is not committed, so the new image finds this scan's status lines and records again
            if (now_flight := in_flight(state)) != flight:  # recomputed each scan, both ways (#394)
                if now_flight == "work":  # live work again: the short backstop from now
                    trial["idle"] = 0
                    deadline = min(deadline, time.monotonic() + backstop)
                else:
                    deadline = armed_at + backstop_wait(now_flight, trial["idle"], backstop, backoff)
                flight = now_flight
            if not wakes and not others and time.monotonic() > deadline:
                trial["idle"] += 0 if flight == "work" else 1
                wakes = [{"reason": "backstop", "event": "due (%s in flight)" % flight}]
                if args.persistent:  # the next backstop, as a re-armed one-shot watcher would start it
                    flight, armed_at, deadline = backstop_deadline(state, trial, backstop, backoff)
            if wakes:
                with queue_lock(state), open(os.path.join(wake, "queue.jsonl"), "a") as f:
                    for w in wakes:
                        f.write(json.dumps(dict(w, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))) + "\n")
                    f.flush()
                    trial["queue"] = queue_sig(wake)
            save(trial)
            seen = trial
            if wakes or others:
                candidates = [{k: v for k, v in w.items() if k not in ROUTE_NOTES}
                              for w in wakes + others]
                commands()["route"].route_queue(argparse.Namespace(
                    project=args.project, org_profile=args.org_profile, timeout=15))
                trial["queue"] = queue_sig(wake)
                save(trial)
                with queue_lock(state):
                    queue = os.path.join(wake, "queue.jsonl")
                    remaining = []
                    if os.path.exists(queue):
                        with open(queue) as f:
                            remaining = [json.loads(line) for line in f if line.strip()]
                wakes = []
                for w in reversed(remaining):
                    key = {k: v for k, v in w.items() if k not in ROUTE_NOTES}
                    if key in candidates:
                        wakes.insert(0, w)
                        candidates.remove(key)
                others = []
                if wakes and not args.persistent:
                    break
                if wakes:  # persistent: wake the coordinator by its nudge and keep scanning (#1346)
                    announce(args, session, state, wake, seen, wakes, home)
                    seen["nudged"] = time.time()
                    flight, armed_at, deadline = backstop_deadline(state, seen, backstop, backoff)
                    save(seen)
            if args.persistent and not wakes and time.time() - seen.get("nudged", 0) >= args.renudge and \
                    os.path.exists(queue := os.path.join(wake, "queue.jsonl")) and os.path.getsize(queue):
                # a coordinator turn that ended without draining (a gateway error, #1346) is nudged again
                announce(args, session, state, wake, seen, [{"reason": "renudge", "event": "wake/queue.jsonl not drained"}],
                         home)
                seen["nudged"] = time.time()
                save(seen)
            sleeping = True
            if held:
                raise SystemExit(128 + held[0])
            time.sleep(pause(state, time.time(), args.interval))
            sleeping = False
        if held:  # held during the last scan, whose wakes are queued
            raise SystemExit(128 + held[0])
        announce(args, session, state, wake, seen, wakes + others, home)
        return 0
    finally:
        save(seen)
        with contextlib.suppress(OSError, ValueError):
            with open(pidfile) as f:
                mine = int(f.read().strip()) == os.getpid()
            if mine:  # never another watcher's (#591)
                os.remove(pidfile)
