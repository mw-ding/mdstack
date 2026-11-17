"""Team-root state for one team serving several repos (docs/specs/team.md §9.3-§9.4, #1858): the team record, the
home of the `(team, pool)` leads and the atomic run-ID and window-slot allocation. A one-repo state has no team root,
so every helper falls back to that state and one-repo behaviour is unchanged."""
import contextlib
import fcntl
import json
import os
import re
import time

RECORD = "team.json"  # <team-root>/team.json: {"team", "coordinator", "repos": {canonical repo: {"project", "state"}}}


def root(state):
    """The team root above a team repo's state (it holds team.json), else None."""
    parent = os.path.dirname(os.path.abspath(state))
    return parent if os.path.isfile(os.path.join(parent, RECORD)) else None


def lead_state(state):
    """Where the pool leads' records, inbox and status live: the team root, else the repo state."""
    return root(state) or state


def read(top):
    try:
        with open(os.path.join(top, RECORD)) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"repos": {}}
    return data if isinstance(data, dict) and isinstance(data.get("repos"), dict) else {"repos": {}}


def save(path, data):
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=2)
    os.replace(path + ".tmp", path)


@contextlib.contextmanager
def lock(top):
    """allocations/.lock: one lock for the team record and every run-ID and slot allocation."""
    os.makedirs(os.path.join(top, "allocations"), exist_ok=True)
    with open(os.path.join(top, "allocations", ".lock"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def bind(state, team, repo, project, coordinator=False):
    """Record a team repo in team.json: its canonical repo, project reference and state, and with coordinator as the
    repo the coordinator's $CREW_PROJECT names. An unchanged record is not rewritten. Returns the team root."""
    top = os.path.dirname(os.path.abspath(state))
    with lock(top):
        data = read(top)
        old = json.dumps(data, sort_keys=True)
        data["team"] = team
        data["repos"][repo] = {"project": project, "state": os.path.abspath(state)}
        if coordinator:
            data["coordinator"] = repo
        if json.dumps(data, sort_keys=True) != old:
            save(os.path.join(top, RECORD), data)
    return top


def unbind(top, repo):
    """Drop a repo's team.json row (#1964); its state directory is kept."""
    with lock(top):
        data = read(top)
        if data["repos"].pop(repo, None) is not None:
            save(os.path.join(top, RECORD), data)


def coordinator(top):
    """The repo the running coordinator's $CREW_PROJECT names: recorded at start, else the first bound repo (a team
    started before the record existed binds in file order)."""
    data = read(top)
    return data.get("coordinator") or next(iter(data["repos"]), None)


def repo_of(state):
    """The canonical repo team.json records for this repo state, else None."""
    top = root(state)
    found = [r for r, v in read(top)["repos"].items() if v.get("state") == os.path.abspath(state)] if top else []
    return found[0] if len(found) == 1 else None


def tag(repo):
    """A window-name and path segment for a canonical repo: owner__name, tmux- and path-safe and one-to-one, so two
    valid repos never share a tag: `/` is `__`, every byte other than [a-z0-9-] (`_` and `.` included) is `_<hex>`."""
    return "".join(c if re.fullmatch(r"[a-z0-9-]", c) else "__" if c == "/" else "".join(
        "_%02x" % b for b in c.encode()) for c in repo.lower())


def allocations(top):
    d = os.path.join(top, "allocations")
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if n.endswith(".json"):
            try:
                with open(os.path.join(d, n)) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and "run_id" in rec:
                yield rec


def allocate(top, band, used, entry, prefer=None):
    """Under the caller's lock(top): mint the next team-global run ID and take the first band slot that no window
    (used) and no other allocation holds, prefer first; write allocations/<run-id>.json. None when the band is full."""
    held = {a.get("index") for a in allocations(top)}
    free = [i for i in range(band[0], band[1] + 1) if i not in used and i not in held]
    if not free:
        return None
    path = os.path.join(top, "allocations", "seq")
    try:
        with open(path) as f:
            seq = int(f.read().strip() or 0) + 1
    except (OSError, ValueError):
        seq = max([0] + [int(a["run_id"][1:]) for a in allocations(top) if re.fullmatch(r"r\d+", a["run_id"])]) + 1
    with open(path + ".tmp", "w") as f:
        f.write("%d\n" % seq)
    os.replace(path + ".tmp", path)
    rec = dict(entry, run_id="r%d" % seq, index=prefer if prefer in free else free[0],
               allocated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    save(os.path.join(top, "allocations", rec["run_id"] + ".json"), rec)
    return rec


def release(top, run_id, repo):
    """Drop run_id's allocation only when it is repo's: another repo's cleanup or replay never frees it."""
    path = os.path.join(top, "allocations", "%s.json" % run_id)
    with lock(top):
        found = next((a for a in allocations(top) if a["run_id"] == run_id), None)
        if found and found.get("repo") == repo:
            os.remove(path)
            return True
    return False
