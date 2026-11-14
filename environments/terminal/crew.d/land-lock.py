"""`mdstack land-lock acquire` / `release` holds the serial land lock.

Usage: mdstack land-lock acquire|release --project FILE [--org-profile FILE]
"""
import contextlib
import fcntl
import json
import os
import signal
import subprocess
import time
from crew_shared import commands, load, profile, refuse_paused, runs, tmux

repo_bind = load("crew_repo_bind", "environments/terminal/crew.d/_repo_bind.py")


def proc_identity(pid):
    """(start time, command line) of a live process from ps, or None; the start time tells a reused PID apart."""
    out = [subprocess.run(["ps", "-o", col + "=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
           for col in ("lstart", "command")]
    return tuple(out) if all(out) else None


def owner_alive(owner):
    live = proc_identity(owner["pid"])
    if live is None or live[0] != owner["start"]:
        return False
    if owner.get("pane_id"):
        pane = tmux.pane(owner["session"], owner["index"])
        if pane is None:  # an unavailable backend (None) never proves the lock owner's death
            return tmux.has_window(owner["session"], owner["index"]) is not False
        return pane["id"] == owner["pane_id"] and pane["pid"] == str(owner["pid"])
    return True


def cleanup(state):
    path = os.path.join(state, "locks", "merge.pid")
    try:
        with open(path) as f:
            rec = json.load(f)
    except FileNotFoundError:
        return
    live = proc_identity(rec["pid"])
    matching = live and live[0] == rec["start"] and "land-lock acquire" in live[1]
    orphan = matching and rec.get("owner") and not owner_alive(rec["owner"])
    if matching and "owner" not in rec:
        parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(rec["pid"])],
                                capture_output=True, text=True).stdout.strip()
        orphan = parent == "1"
    if orphan:
        try:
            os.kill(rec["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    # Only clear the record while holding the lock; another live holder is never stolen.
    with open(os.path.join(state, "locks", "merge.lock"), "a") as f:
        for attempt in range(50 if orphan else 1):
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                os.remove(path)
                return
            except BlockingIOError:
                if orphan:
                    time.sleep(0.1)


def held(state):
    cleanup(state)
    path = os.path.join(state, "locks", "merge.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def register(sub):
    p = sub.add_parser("land-lock")
    p.add_argument("action", choices=["acquire", "release"])
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    """Serial land (tmux.md C7): acquire takes an flock on locks/merge.lock, held by a detached child until
    release; a second acquire fails fast. The lock is the selected repo's (team §9.5, #1859): its record names that
    repo and its owner, and a record naming another repo is refused before any cleanup, signal or removal."""
    values, session, state = profile(args)
    lock, pidfile = os.path.join(state, "locks", "merge.lock"), os.path.join(state, "locks", "merge.pid")
    ctx = repo_bind.context(args.project, values)
    try:
        with open(pidfile) as f:
            recorded = json.load(f)
    except FileNotFoundError:
        recorded = None
    except (OSError, ValueError):
        recorded = "unreadable"
    problem = repo_bind.foreign(ctx, "team.name" in values, records=[("land lock record %s" % pidfile, recorded)])
    if problem:
        print("crew: refusing %s: %s; nothing cleaned, signalled or removed" % (args.action, problem))
        return 1
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    if args.action == "acquire":
        cleanup(state)
        me = os.environ.get("CREW_ID")  # a run, or the synthesizer lead (#1569): its pane owns the lock
        run = dict(runs(state)).get(me) or dict(commands()["lead"].records(state)).get(me) or {}
        owner = None
        if run.get("pane_pid") and run.get("pane_start"):
            owner = {"pid": int(run["pane_pid"]), "start": run["pane_start"]}
            if run.get("pane_id"):
                owner.update(pane_id=run["pane_id"], session=session, index=run["index"])
            if not owner_alive(owner):
                print("crew: refusing acquire: owning pane is gone")
                return 1
        fd = os.open(lock, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("crew: land lock %s is held; another land is in progress" % lock)
            return 1
        if refuse_paused(state, "land-lock acquire"):  # rechecked under the lock: mdstack pause waits on it (#1714)
            os.close(fd)
            return 1
        pid = os.fork()
        if pid == 0:  # holder: keeps the lock's open file until release signals it
            os.setsid()
            null = os.open(os.devnull, os.O_RDWR)
            for n in (0, 1, 2):
                os.dup2(null, n)
            while owner is None or owner_alive(owner):
                time.sleep(0.5)
            os._exit(0)
        with open(pidfile, "w") as f:
            json.dump({"pid": pid, "start": proc_identity(pid)[0], "owner": owner, "window": me, "context": ctx}, f)
        print("crew: land lock acquired (holder pid %d)" % pid)
        return 0
    with open(lock, "a") as f:
        for attempt in range(50):  # signal the holder, then await the unlock
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if attempt == 0:  # signal only our holder: same PID, same start time, a land-lock acquire
                    try:
                        with open(pidfile) as p:
                            rec = json.load(p)
                        live = proc_identity(int(rec["pid"]))
                    except (OSError, ValueError, TypeError, KeyError):
                        live = rec = None
                    if not live or live[0] != rec["start"] or "land-lock acquire" not in live[1]:
                        print("crew: refusing release: land lock %s is held, but not by the holder recorded in "
                              "merge.pid (stale or reused PID); nothing signalled" % lock)
                        return 1
                    with contextlib.suppress(ProcessLookupError):  # it exited after the check (#1757)
                        os.kill(int(rec["pid"]), signal.SIGTERM)
                time.sleep(0.1)
        else:
            print("crew: land lock %s still held after release" % lock)
            return 1
    if os.path.exists(pidfile):
        os.remove(pidfile)
    print("crew: land lock released" if attempt else "crew: land lock not held")
    return 0
