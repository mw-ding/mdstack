"""Shared status for independent crews (docs/specs/shared-status.md, #1313): the [status] settings, the read phase,
the section collectors, the receipt and publish lock, `mdstack status register`, `mdstack status publish [--check]`,
the read-only `mdstack status --all` view and the watcher's publish timer.

The status connector is reached only through the bound backend map's [status] commands (resolve's meta), each run
through `sh -c` with one JSON request on stdin and MDSTACK_ROOT and MDSTACK_PYTHON set. Every read-phase step is a
read: a refusal writes nothing (no destination request, no file under the state dir) and exits 1 with the reason
on stderr. The receipt and lock live under the install's state root: the repo state dir, a team file's team root.
MDSTACK_STATUS_CLOCK (epoch seconds) is the test-only clock seam every UTC check and observation time reads.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from crew_shared import CREW_BIN, commands, crew_render, load, ownership_module, paused, tracker_labels

record = load("crew_status_record", "core/status-record.py")
config = crew_render.crew_config
RUNTIMES = list(config.RUNTIME_OPTIONS)  # source.runtime: a runtime.name the profile schema accepts
ROOT = os.path.dirname(os.path.dirname(CREW_BIN))
TIMEOUT = 120  # one connector or collector call
LIST_LIMIT = 1000  # one collector list read; a full page of it is a partial read
OUTCOMES = ("applied", "rejected", "not-sent", "uncertain")
RECEIPT_KEYS = ["schema_version", "destination", "instance_id", "registration_id", "publisher", "comment_id",
                "binding", "sequence", "content_sha256", "pending"]
PENDING_KEYS = ["op", "state", "sequence", "content_sha256", "body"]
SHA = re.compile(r"[0-9a-f]{64}")


class Refused(Exception):
    """A refusal: its reason goes to stderr, exit 1."""


class Unknown(Exception):
    """A collector that did not complete a fresh read: args[0] is the reason (read-failed, unsupported, over-limit)."""


def now():
    return float(os.environ.get("MDSTACK_STATUS_CLOCK") or time.time())


# --- configuration and connector ---

def resolve(args):
    """(values, status commands {op: cmd}, problems) of the resolved profile; values are its dotted leaves."""
    meta = {}
    merged, _, problems, _ = config.resolve_profile(args.project, args.org_profile, meta=meta)
    if problems:
        return None, None, problems
    values = dict(config.leaves(merged))
    if "team.name" in meta:
        values["team.name"] = meta["team.name"][0]
    if re.search(r"<[^<>]+>", str(values.get("paths.state_dir", ""))):
        return None, None, ["%s:paths.state_dir: still the placeholder %s" % (args.project, values["paths.state_dir"])]
    return values, {k[len("status."):]: v for k, (v, _) in meta.items() if k.startswith("status.")}, []


def settings(values):
    return {k: values.get("status." + k, default) for k, (_, default) in config.STATUS_FIELDS.items()}


def homes(values):
    """(repo state dir, install state root): a team file's root is paths.state_dir, else the repo state dir."""
    root = os.path.abspath(values["paths.state_dir"])
    state = os.path.join(root, "%s__%s" % (values["repo.owner"], values["repo.name"]))
    return state, root if values.get("team.name") else state


def connector(cmds, op, req):
    """(JSON object, None) from one run of the bound map's [status] op command, else (None, why)."""
    if not cmds.get(op):
        return None, "no status.%s command bound" % op
    env = dict(os.environ, MDSTACK_ROOT=ROOT, MDSTACK_PYTHON=sys.executable)
    try:
        r = subprocess.run(["sh", "-c", cmds[op]], input=json.dumps(req), capture_output=True, text=True,
                           timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return None, "timed out after %ds" % TIMEOUT
    except OSError as e:
        return None, "cannot run (%s)" % e.strerror
    if r.returncode:
        return None, "exit %d" % r.returncode
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = None
    return (out, None) if isinstance(out, dict) else (None, "stdout is not one JSON object")


def listing(cmds, destination):
    """(read-records result, None) or (None, why): {login, issue, complete, comments [{id, author, body, url}]}."""
    out, why = connector(cmds, "read-records", {"destination": destination})
    if out is None:
        return None, "read-records failed (%s)" % why
    comments = out.get("comments")
    if out.get("issue") not in ("open", "closed", "missing", "unknown") or type(out.get("complete")) is not bool or \
            not isinstance(out.get("login"), (str, type(None))) or not isinstance(comments, list) or not all(
                isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"] and isinstance(c.get("body"), str)
                and isinstance(c.get("author"), (str, type(None))) for c in comments):
        return None, "read-records output malformed"
    for c in comments:
        c["url"] = c.get("url") if isinstance(c.get("url"), str) else "%s#comment-%s" % (destination, c["id"])
    return out, None


def status_comments(comments):
    """[(comment, object or None, problem or None)] for each comment whose first line is the status marker."""
    found = []
    for c in comments:
        rec, problem = record.parse_slot(c["body"])
        if rec is not None or problem is not None:
            found.append((c, rec, problem))
    return found


def holds(rec, key, value):
    return isinstance(rec, dict) and rec.get(key) == value


def same_login(a, b):
    return isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower()


# --- receipt and lock ---

def binding(home, project):
    """SHA-256 of the host name and the real paths of the state root and the config file; never published."""
    text = "\0".join([socket.gethostname(), os.path.realpath(home), os.path.realpath(config.split_ref(project)[0])])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def receipt_path(home):
    return os.path.join(home, "status", "receipt.json")


def receipt_problem(r):
    """Why r is not a valid receipt (§4), else None; a pending body must be the exact next record for it."""
    if not isinstance(r, dict) or set(r) != set(RECEIPT_KEYS):
        return "not the closed receipt object"
    if r["schema_version"] != 1 or type(r["schema_version"]) is not int:
        return "schema_version is not 1"
    if not all(isinstance(r[k], str) and r[k] for k in ("destination", "publisher")) or \
            not isinstance(r["instance_id"], str) or not record.INSTANCE_ID.fullmatch(r["instance_id"]) or \
            not isinstance(r["registration_id"], str) or not record.REGISTRATION_ID.fullmatch(r["registration_id"]):
        return "destination, publisher, instance_id or registration_id malformed"
    if not (r["comment_id"] is None or isinstance(r["comment_id"], str) and r["comment_id"]):
        return "comment_id is not null or a nonempty string"
    if not isinstance(r["binding"], str) or not SHA.fullmatch(r["binding"]):
        return "binding is not a SHA-256"
    if type(r["sequence"]) is not int or not 0 <= r["sequence"] <= record.MAX_SEQUENCE or \
            (r["sequence"] == 0) != (r["content_sha256"] is None) or \
            not (r["content_sha256"] is None or isinstance(r["content_sha256"], str) and SHA.fullmatch(r["content_sha256"])):
        return "sequence and content_sha256 disagree or are malformed"
    p = r["pending"]
    if p is None:
        return None
    if not isinstance(p, dict) or set(p) != set(PENDING_KEYS) or p["op"] not in ("create", "update") or \
            p["state"] not in ("prepared", "uncertain") or not isinstance(p["body"], str):
        return "pending is not null or the closed pending object"
    if (p["op"] == "create") != (r["comment_id"] is None):
        return "pending %s with comment_id %s" % (p["op"], json.dumps(r["comment_id"]))
    rec, problems = record.check_body(p["body"], RUNTIMES)
    if problems:
        return "pending body invalid (%s)" % problems[0]
    expected = 1 if p["op"] == "create" else r["sequence"] + 1
    if rec["instance_id"] != r["instance_id"] or rec["registration_id"] != r["registration_id"] or \
            rec["sequence"] != p["sequence"] or p["sequence"] != expected or \
            record.content_sha256(rec) != p["content_sha256"]:
        return "pending body is not the receipt's next record"
    return None


def load_receipt(home):
    """(receipt or None when absent, raw bytes or None); Refused receipt-invalid when unreadable or invalid."""
    try:
        with open(receipt_path(home), "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None, None
    except OSError as e:
        raise Refused("receipt-invalid: %s unreadable (%s)" % (receipt_path(home), e.strerror))
    try:
        r = json.loads(raw)
    except ValueError:
        r = None
    problem = receipt_problem(r)
    if problem:
        raise Refused("receipt-invalid: %s: %s" % (receipt_path(home), problem))
    return r, raw


def write_receipt(home, r):
    """Atomic: a temporary file in status/, flushed and synced, renamed over the receipt, the directory synced."""
    directory = os.path.join(home, "status")
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".receipt-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(r, f, sort_keys=True, indent=1)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, receipt_path(home))
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


@contextlib.contextmanager
def publish_lock(home):
    directory = os.path.join(home, "status")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "publish.lock"), "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused("busy: another publisher holds status/publish.lock") from None
        yield


# --- collectors (§3.3) ---

def gh_json(*args):
    """One GitHub read through the shared poll helper (a failure raises RuntimeError or its Transient subclass)."""
    return commands()["poll"].gh_json(*args)


def full_list(*args):
    """One collector list read; a result that fills LIST_LIMIT may be partial, so it is a failed read."""
    found = gh_json(*args, "--limit", str(LIST_LIMIT))
    if not isinstance(found, list) or len(found) >= LIST_LIMIT:
        raise Unknown("read-failed")
    return found


def sources(args, values):
    """[(owner/name, values)] of the install's source repos, sorted: the repo, or every [repos.<name>] of a team."""
    if not values.get("team.name"):
        return [("%s/%s" % (values["repo.owner"], values["repo.name"]), values)]
    file, found = config.split_ref(args.project)[0], []
    for name in config.team_repos(file):
        v, problems = crew_render.resolve("%s#%s" % (file, name), args.org_profile)
        if problems or not v:
            raise Refused("config: %s#%s does not resolve (%s)" % (file, name, (problems or ["unresolved"])[0]))
        found.append(("%s/%s" % (v["repo.owner"], v["repo.name"]), v))
    return sorted(found)


class Reads:
    """Each source repo's open issues, open PRs and open milestones, read once per collection."""
    def __init__(self):
        self.cache = {}

    def get(self, key, repo, fn):
        if (key, repo) not in self.cache:
            try:
                self.cache[key, repo] = (fn(), None)
            except Unknown as e:
                self.cache[key, repo] = (None, e.args[0])
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
                self.cache[key, repo] = (None, "read-failed")
        found, why = self.cache[key, repo]
        if why:
            raise Unknown(why)
        return found

    def issues(self, repo):
        return self.get("issues", repo, lambda: full_list(
            "issue", "list", "-R", repo, "--state", "open", "--json", "number,title,labels"))

    def prs(self, repo):
        return self.get("prs", repo, lambda: full_list("pr", "list", "-R", repo, "--state", "open", "--json", "number,labels"))


def labelled(item, label):
    return any(isinstance(lb, dict) and lb.get("name") == label for lb in item.get("labels") or [])


def limited(items, name):
    if len(items) > record.SECTIONS[name][2]:
        raise Unknown("over-limit")
    return {"items": items}


def milestones(srcs, t):
    items = []
    for repo, v in srcs:
        pages = gh_json("api", "--paginate", "--slurp", "repos/%s/milestones?state=open&per_page=100" % repo)
        found = [m for page in pages for m in page]
        if v.get("repo.milestones"):
            found = [m for n in v["repo.milestones"] for m in found if m["number"] == n]
        for m in found[:v.get("runtime.options.max_active_milestones", 1)]:
            items.append({"url": "https://github.com/%s/milestone/%d" % (repo, m["number"]),
                          "completed": m["closed_issues"], "total": m["open_issues"] + m["closed_issues"]})
    return limited(items, "milestones")


def prs(srcs, reads, t):
    items = []
    for repo, v in srcs:
        labels = tracker_labels(v)
        order = [("escalated", "crew:escalated"), ("held", "crew:hold"), ("changes", "crew:changes"),
                 ("approved", "crew:approved"), ("in-review", "crew:in-review")]
        for p in sorted(reads.prs(repo), key=lambda p: p["number"]):
            stage = next((s for s, tag in order if labelled(p, labels[tag])), "other")
            items.append({"url": "https://github.com/%s/pull/%d" % (repo, p["number"]), "stage": stage})
    return limited(items, "prs")


def owner_asks(srcs, reads, t):
    items = []
    for repo, v in srcs:
        label = tracker_labels(v)["crew:needs-md"]
        for kind, found in (("issues", reads.issues(repo)), ("pull", reads.prs(repo))):
            items += [{"url": "https://github.com/%s/%s/%d" % (repo, kind, i["number"]), "deadline": None}
                      for i in sorted(found, key=lambda i: i["number"]) if labelled(i, label)]
    return limited(items, "owner_asks")


def blockers(srcs, reads, t):
    items = []
    for repo, v in srcs:
        labels = tracker_labels(v)
        for kind, found in (("issues", reads.issues(repo)), ("pull", reads.prs(repo))):
            for i in sorted(found, key=lambda i: i["number"]):
                red = kind == "issues" and (i.get("title") or "").startswith("main-red")
                what = "escalated" if labelled(i, labels["crew:escalated"]) else "main-red" if red else \
                    "held" if labelled(i, labels["crew:hold"]) else None
                if what:
                    items.append({"url": "https://github.com/%s/%s/%d" % (repo, kind, i["number"]), "kind": what})
    return limited(items, "blockers")


def throughput(srcs, t):
    since, merged = t - 86400, 0
    for repo, _ in srcs:
        found = full_list("pr", "list", "-R", repo, "--state", "merged", "--search",
                          "merged:>=%s" % record.stamp(since), "--json", "number,mergedAt")
        for p in found:
            at = record.utc(p.get("mergedAt"))
            if at is None:
                raise Unknown("read-failed")
            merged += since < at <= t
    return {"merged_24h": merged}


def queue(values, home, stale_after, t):
    """depth and target from the scheduler's newest snapshot line, and its ts as the observation time."""
    if values["runtime.name"] != "tmux":
        raise Unknown("unsupported")
    line = commands()["schedule"].latest(home)
    if not isinstance(line, dict) or not isinstance(line.get("snapshot"), dict):
        raise Unknown("read-failed")
    snap = line["snapshot"]
    if "repos" in snap and (snap.get("unresolved") or not isinstance(snap["repos"], dict)):
        raise Unknown("read-failed")
    demands = [r.get("demand") for r in snap["repos"].values()] if "repos" in snap else [snap.get("demand")]
    depth = 0
    for d in demands:
        for pool in ("builder", "reviewer"):
            if not isinstance(d, dict) or not isinstance(d.get(pool), list):
                raise Unknown("read-failed")
            depth += len(d[pool])
    ts = record.utc(line.get("ts"))
    if type(line.get("target")) is not int or ts is None or ts > t or t - ts >= stale_after:
        raise Unknown("read-failed")
    return {"depth": depth, "target": line["target"], "_observed": ts}


def collect(args, values, st, home, srcs):
    """The six sections, each `known` from a fresh read or `unknown` with its reason, never empty in its place."""
    github = values["backends.tracker.name"] == "github" and values["backends.change.name"] == "github"
    reads = Reads()
    fns = {"milestones": lambda t: milestones(srcs, t), "prs": lambda t: prs(srcs, reads, t),
           "owner_asks": lambda t: owner_asks(srcs, reads, t), "blockers": lambda t: blockers(srcs, reads, t),
           "throughput": lambda t: throughput(srcs, t),
           "queue": lambda t: queue(values, home, st["stale_after"], t)}
    sections = {}
    for name, fn in fns.items():
        t = now()
        try:
            if not github and name != "queue":
                raise Unknown("unsupported")
            payload = fn(t)
        except Unknown as e:
            sections[name] = {"state": "unknown", "observed_at": record.stamp(t), "reason": e.args[0]}
            continue
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
            sections[name] = {"state": "unknown", "observed_at": record.stamp(t), "reason": "read-failed"}
            continue
        observed = payload.pop("_observed", t)
        sections[name] = dict({"state": "known", "observed_at": record.stamp(observed)}, **payload)
    return sections


def build(values, st, srcs, sections, registration_id, sequence):
    return {"schema_version": 1, "instance_id": st["instance_id"], "registration_id": registration_id,
            "sequence": sequence,
            "observed_at": record.stamp(min(record.utc(s["observed_at"]) for s in sections.values())),
            "published_at": record.stamp(now()),
            "source": {"repos": sorted(r for r, _ in srcs), "runtime": values["runtime.name"],
                       "decision_log": st["decision_log"]},
            "sections": sections}


def checked(rec):
    problems = record.check_record(rec, RUNTIMES, now())
    if problems:
        raise Refused("record invalid: %s" % "; ".join(problems))
    return rec


# --- read phase (§5) ---

def read_phase(args, action):
    """Every step a read; Refused at any step means zero writes. action: register or publish."""
    values, cmds, problems = resolve(args)
    if problems:
        raise Refused("config: " + "\n".join(problems))
    st = settings(values)
    need = ["destination", "instance_id", "decision_log"]
    missing = [k for k in need if st[k] is None]
    if missing:
        raise Refused("unconfigured: [status] %s unset" % ", ".join(missing))
    if action == "publish" and st["enabled"] is not True:
        raise Refused("off: [status] enabled is false")
    role = os.environ.get("CREW_ROLE")
    if role and role != "coordinator":
        raise Refused("caller: CREW_ROLE=%s; only the watcher or an owner shell publishes" % role)
    mode = ownership_module.ownership(values)
    if not ownership_module.permits(mode, "write"):
        raise Refused("ownership: %s; refusing write" % mode)
    state, home = homes(values)
    barrier = paused(state)
    if barrier is not None:
        raise Refused("paused: %s" % ("pause state unreadable: %s" % barrier["unreadable"] if "unreadable" in barrier
                                      else "pause barrier since %s" % barrier.get("at")))
    publisher = values["identities.coordinator.gh_user"]
    found, why = listing(cmds, st["destination"])
    if found is None:
        raise Refused("destination unreadable: " + why)
    if not same_login(found["login"], publisher):
        raise Refused("publisher: authenticated account %s is not identities.coordinator.gh_user %s"
                      % (found["login"] or "unreadable", publisher))
    receipt, raw = load_receipt(home)
    bind = binding(home, args.project)
    ctx = dict(args=args, values=values, cmds=cmds, st=st, state=state, home=home, publisher=publisher,
               receipt=receipt, raw=raw, binding=bind, listing=found)
    mine = receipt is not None and receipt["destination"] == st["destination"] and \
        receipt["instance_id"] == st["instance_id"]
    if mine and receipt["binding"] != bind:
        raise Refused("copied receipt: %s binds another host, state dir or config; choose a new instance_id and "
                      "run register" % receipt_path(home))
    if action == "publish":
        if receipt is None or not mine:
            raise Refused("unregistered: no receipt for %s on %s; run mdstack status register"
                          % (st["instance_id"], st["destination"]))
        if receipt["comment_id"] is None:
            raise Refused("unregistered: registration not confirmed (create pending); rerun mdstack status register")
    if found["issue"] != "open" or not found["complete"]:
        raise Refused("destination %s: %s" % (st["destination"], "issue " + found["issue"] if found["issue"] != "open"
                                              else "a comment page did not read"))
    ctx["comments"] = status_comments(found["comments"])
    if action == "publish":
        slot = next((c for c in found["comments"] if c["id"] == receipt["comment_id"]), None)
        if slot is None:
            raise Refused("conflict: bound slot comment %s is not on %s" % (receipt["comment_id"], st["destination"]))
        rec, _ = record.parse_slot(slot["body"])
        if not same_login(slot["author"], publisher) or not holds(rec, "instance_id", st["instance_id"]) or \
                not holds(rec, "registration_id", receipt["registration_id"]):
            raise Refused("conflict: %s is not this publisher's slot for %s/%s"
                          % (slot["url"], st["instance_id"], receipt["registration_id"]))
        other = next((c for c, r, _ in ctx["comments"] if c["id"] != slot["id"] and (
            holds(r, "instance_id", st["instance_id"]) or holds(r, "registration_id", receipt["registration_id"]))), None)
        if other:
            raise Refused("conflict: %s also holds %s or its registration" % (other["url"], st["instance_id"]))
        ctx["slot"], ctx["slot_rec"] = slot, rec
    srcs = sources(args, values)
    sections = collect(args, values, st, home, srcs)
    sequence = receipt["sequence"] + 1 if action == "publish" else 1
    rid = receipt["registration_id"] if mine else "r-" + "0" * 32  # register draws its ID under the lock
    ctx.update(srcs=srcs, sections=sections, record=checked(build(values, st, srcs, sections, rid, sequence)))
    return ctx


# --- write phase and outcomes ---

def unchanged(ctx):
    """Refused unless the receipt and the bound slot are as the read phase saw them (under the lock)."""
    _, raw = load_receipt(ctx["home"])
    if raw != ctx["raw"]:
        raise Refused("conflict: the receipt changed since the read phase")
    if "slot" in ctx:
        found, why = listing(ctx["cmds"], ctx["st"]["destination"])
        if found is None:
            raise Refused("destination unreadable: " + why)
        slot = next((c for c in found["comments"] if c["id"] == ctx["slot"]["id"]), None)
        if slot is None or slot["body"] != ctx["slot"]["body"] or slot["author"] != ctx["slot"]["author"]:
            raise Refused("conflict: the bound slot changed since the read phase")


def send(ctx, receipt, op):
    """Send pending once through publish-record and apply the outcome rules; returns 0 or raises Refused."""
    home, pending = ctx["home"], receipt["pending"]
    out, why = connector(ctx["cmds"], "publish-record", {
        "destination": ctx["st"]["destination"], "publisher": ctx["publisher"], "op": op,
        "comment_id": receipt["comment_id"], "body": pending["body"]})
    outcome = out.get("outcome") if out and out.get("outcome") in OUTCOMES else "uncertain"
    detail = (out or {}).get("error") or why or ""
    cid = (out or {}).get("comment_id")
    if outcome == "applied" and not (isinstance(cid, str) and cid and (op == "create" or cid == receipt["comment_id"])):
        outcome, detail = "uncertain", "applied with no matching comment id"
    if outcome in ("rejected", "not-sent"):
        receipt["pending"] = None
        write_receipt(home, receipt)
        raise Refused("%s: sequence %d was not applied (%s); no retry in this run" % (outcome, pending["sequence"], detail))
    if outcome == "uncertain":
        pending["state"] = "uncertain"
        write_receipt(home, receipt)
        raise Refused("uncertain: pending sequence %d (%s); never resent: later runs only read back"
                      % (pending["sequence"], detail))
    found, why = listing(ctx["cmds"], ctx["st"]["destination"])
    slot = next((c for c in found["comments"] if c["id"] == cid), None) if found else None
    if found is None:
        pending["state"] = "uncertain"
        write_receipt(home, receipt)
        raise Refused("uncertain: applied, readback failed (%s); pending sequence %d" % (why, pending["sequence"]))
    if slot is None or slot["body"] != pending["body"] or not same_login(slot["author"], ctx["publisher"]):
        raise Refused("conflict: applied, but comment %s does not hold the pending body" % cid)
    confirm(home, receipt, cid)
    return pending["sequence"], cid


def confirm(home, receipt, cid=None):
    pending = receipt["pending"]
    receipt.update(sequence=pending["sequence"], content_sha256=pending["content_sha256"], pending=None)
    if cid is not None:
        receipt["comment_id"] = cid
    write_receipt(home, receipt)


def prepared(op, rec):
    return {"op": op, "state": "prepared", "sequence": rec["sequence"], "content_sha256": record.content_sha256(rec),
            "body": record.slot_body(rec)}


def publish(args):
    ctx = read_phase(args, "publish")
    receipt, slot, rec = ctx["receipt"], ctx["slot"], ctx["slot_rec"]
    pending = receipt["pending"]
    confirmed = isinstance(rec, dict) and rec.get("sequence") == receipt["sequence"] and \
        record.content_sha256(rec) == receipt["content_sha256"]
    if pending is not None and slot["body"] == pending["body"]:
        action = "confirm"
    elif pending is None and confirmed:
        action = "send"
    elif pending is not None and confirmed:
        raise Refused("uncertain: pending sequence %d may still apply; never resent, no newer record; wait for "
                      "readback or register a new instance_id" % pending["sequence"])
    else:
        raise Refused("conflict: %s shows sequence %s, not the confirmed %d or the pending one; publication stops "
                      "until the owner resolves it" % (slot["url"], json.dumps(rec.get("sequence")), receipt["sequence"]))
    if args.check:
        print("confirm sequence %d" % pending["sequence"] if action == "confirm"
              else json.dumps(ctx["record"], indent=2, sort_keys=True))
        return 0
    with publish_lock(ctx["home"]):
        unchanged(ctx)
        if action == "confirm":
            confirm(ctx["home"], receipt)
            print("confirmed sequence %d" % receipt["sequence"])
            return 0
        receipt["pending"] = prepared("update", ctx["record"])
        write_receipt(ctx["home"], receipt)
        sequence, _ = send(ctx, receipt, "update")
    print("published sequence %d" % sequence)
    return 0


def register(args):
    ctx = read_phase(args, "register")
    st, receipt, publisher, home = ctx["st"], ctx["receipt"], ctx["publisher"], ctx["home"]
    mine = receipt is not None and receipt["destination"] == st["destination"] and \
        receipt["instance_id"] == st["instance_id"]
    if mine and receipt["comment_id"] is not None:
        print("registered %s" % st["instance_id"])
        return 0
    if mine and receipt["pending"] is not None:  # a create still pending: adopt its exact comment, never create again
        pending = receipt["pending"]
        found = [c for c, r, _ in ctx["comments"] if same_login(c["author"], publisher)
                 and holds(r, "registration_id", receipt["registration_id"])]
        exact = [c for c in found if c["body"] == pending["body"]]
        if len(exact) == 1 and len(found) == 1:
            with publish_lock(home):
                unchanged(ctx)
                confirm(home, receipt, exact[0]["id"])
            print("registered %s" % st["instance_id"])
            return 0
        if found:
            raise Refused("conflict: %s holds registration %s with other content" % (found[0]["url"],
                                                                                    receipt["registration_id"]))
        raise Refused("uncertain: create of %s (sequence 1) has no readback; never created again for this instance; "
                      "wait or choose a new instance_id" % receipt["registration_id"])
    taken = next((c for c, r, _ in ctx["comments"] if holds(r, "instance_id", st["instance_id"])), None)
    if taken:
        raise Refused("conflict: %s already holds instance_id %s" % (taken["url"], st["instance_id"]))
    for key in ("instance_id", "registration_id"):
        seen = {}
        for c, r, _ in ctx["comments"]:
            value = r.get(key) if isinstance(r, dict) else None
            if isinstance(value, str) and value in seen:
                raise Refused("conflict: %s and %s hold the same %s %s" % (seen[value]["url"], c["url"], key, value))
            seen[value] = c
    with publish_lock(home):
        unchanged(ctx)
        if receipt is not None and not mine:  # another destination or instance: archived, never deleted
            os.replace(receipt_path(home), os.path.join(home, "status", "receipt-%s.json" % receipt["registration_id"]))
        rid = receipt["registration_id"] if mine else "r-" + secrets.token_hex(16)
        rec = checked(build(ctx["values"], st, ctx["srcs"], ctx["sections"], rid, 1))
        new = {"schema_version": 1, "destination": st["destination"], "instance_id": st["instance_id"],
               "registration_id": rid, "publisher": publisher, "comment_id": None, "binding": ctx["binding"],
               "sequence": 0, "content_sha256": None, "pending": prepared("create", rec)}
        write_receipt(home, new)
        send(ctx, new, "create")
    print("registered %s" % st["instance_id"])
    return 0


# --- aggregate view (§6) ---

COLUMNS = ("INSTANCE", "REPOS", "RUNTIME", "AGE", "STATE", "BLOCKED", "UNKNOWN", "PRS", "ASKS", "QUEUE")


def age_text(seconds):
    return "%ds" % seconds if seconds < 120 else "%dm" % (seconds // 60) if seconds < 7200 else "%dh" % (seconds // 3600)


def items_text(sec):
    return str(len(sec["items"])) if sec["state"] == "known" else "unknown"


def row(rec, state, t, stale_after):
    if state in ("invalid", "conflict"):
        return [rec["instance_id"], "-", "-", "-", state] + ["-"] * 5
    age = int(t - record.utc(rec["observed_at"]))
    secs = rec["sections"]
    blocked = "unknown" if secs["blockers"]["state"] == "unknown" else "yes" if secs["blockers"]["items"] else "no"
    unknown = ",".join(n for n in record.SECTIONS if secs[n]["state"] == "unknown") or "-"
    q = secs["queue"]
    return [rec["instance_id"], ",".join(rec["source"]["repos"]), rec["source"]["runtime"], age_text(age),
            "fresh" if age < stale_after else "stale", blocked, unknown, items_text(secs["prs"]),
            items_text(secs["owner_asks"]), "%d/%d" % (q["depth"], q["target"]) if q["state"] == "known" else "unknown"]


def view(args):
    values, cmds, problems = resolve(args)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    st = settings(values)
    if st["destination"] is None:
        print("status --all: unconfigured", file=sys.stderr)
        return 3
    t = now()
    found, why = listing(cmds, st["destination"])
    rows, diagnostics, partial = [], [], None
    if found is None:
        partial = why
        found = {"issue": "unknown", "complete": False, "comments": []}
    entries, regs = {}, {}
    for c, rec, problem in status_comments(found["comments"]):
        if problem is None:
            problems = record.check_record(rec, RUNTIMES, t)
            problem = problems[0] if problems else None
        inst = rec.get("instance_id") if isinstance(rec, dict) else None
        if not (isinstance(inst, str) and record.INSTANCE_ID.fullmatch(inst)):
            inst = None
        if problem:
            diagnostics.append("diagnostic: %s invalid: %s" % (c["url"], problem))
        if inst is not None:
            entries.setdefault(inst, []).append((c, rec, problem))
        reg = rec.get("registration_id") if isinstance(rec, dict) else None
        if isinstance(reg, str):
            regs.setdefault(reg, []).append(inst)
    clashing = {i for insts in regs.values() if len(insts) > 1 for i in insts if i}
    for inst in sorted(entries):
        group = entries[inst]
        if len(group) > 1 or inst in clashing:
            rows.append(row({"instance_id": inst}, "conflict", t, st["stale_after"]))
            diagnostics += ["diagnostic: %s conflict: duplicate instance_id or registration_id" % c["url"]
                            for c, _, _ in group]
        elif group[0][2]:
            rows.append(row({"instance_id": inst}, "invalid", t, st["stale_after"]))
        else:
            rows.append(row(group[0][1], "fresh", t, st["stale_after"]))
    if partial is None and found["issue"] != "open":
        partial = "destination issue %s" % found["issue"]
    elif partial is None and not found["complete"]:
        partial = "a comment page did not read"
    table = [list(COLUMNS)] + rows
    widths = [max(len(r[i]) for r in table) for i in range(len(COLUMNS))]
    print("\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in table))
    for line in diagnostics:
        print(line)
    if partial:
        print("partial: %s (%d status comment%s read)" % (partial, len(rows), "" if len(rows) == 1 else "s"))
        return 1
    return 0


# --- the watcher's timer (§5 Timer) ---

def tick(values, project, org_profile, seen, t):
    """Run `mdstack status publish` as a subprocess once publish_interval passed since the last attempt; no model
    or coordinator wake, stderr discarded. Off, or ownership lost: no run. True when it ran."""
    if values.get("status.enabled") is not True or t - seen.get("status_attempt", 0) < values["status.publish_interval"]:
        return False
    if ownership_module.status(values) == "lost":
        return False
    seen["status_attempt"] = t
    argv = [sys.executable, CREW_BIN, "status", "publish", "--project", project]
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        subprocess.run(argv + (["--org-profile", org_profile] if org_profile else []), stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10 * TIMEOUT)
    return True


def main(args):
    """`mdstack status register|publish [--check]` and `mdstack status --all`."""
    if args.all and (args.action or args.check) or args.check and args.action != "publish":
        print("mdstack status: --all takes no action; --check needs publish", file=sys.stderr)
        return 2
    if args.all:
        return view(args)
    try:
        return register(args) if args.action == "register" else publish(args)
    except Refused as e:
        print("status %s: %s" % (args.action, e), file=sys.stderr)
        return 1
