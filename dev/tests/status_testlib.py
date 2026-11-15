"""Shared fixtures for the shared-status tests (docs/specs/shared-status.md §9, #1313): a fake status API behind a
fake `gh` on PATH, a temp install with a [status] profile, a state-dir snapshot and the shipped CLI entry point
(stdlib only). No tests here.

The fake API keeps issues, comments, collector data and faults in $FAKE_GH_STATE (JSON) and appends every POST,
PATCH and DELETE to $FAKE_GH_AUDIT. Comment pages hold at most `page_size` (2) comments, so page 2+ is exercised.
Faults per write method, consumed in order: rejected (HTTP 422, not applied), lost (applied, response lost),
5xx (HTTP 502, not applied), never (timeout, never applied), delay:K (timeout, applied after K later comment-page-1
reads), mangle (applied with other content, success reported). `fail` lists read families that fail: user, issue,
page:N, issues, prs, milestones, merged; `user_calls_ok` = N fails every account read after the first N. A control
item's comments read with --slurp (the ownership guard's handoff markers) come from the same issues table.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(TESTS))
CREW = os.path.join(ROOT_DIR, "cli", "mdstack")
DEST = "https://github.com/acme/status/issues/5"
CLOCK = 2_000_000_000  # 2033-05-18T03:33:20Z

FAKE_GH = textwrap.dedent(r'''
    #!/usr/bin/env python3
    import fcntl, json, os, re, sys
    args = sys.argv[1:]
    path = os.environ["FAKE_GH_STATE"]
    lock = open(path + ".lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX)  # one request at a time, as one API server serializes them
    st = json.load(open(path))
    def save():
        json.dump(st, open(path, "w"), indent=1)
    def fail(msg, code=1):
        save()
        sys.stderr.write("gh: " + msg + "\n")
        sys.exit(code)
    def audit(method, target, body):
        with open(os.environ["FAKE_GH_AUDIT"], "a") as f:
            f.write(json.dumps({"method": method, "path": target, "body": body}) + "\n")
    def flag(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    def issue(key):
        return st["issues"].setdefault(key, {"state": "open", "comments": []})
    def apply(w):
        comments = issue(w["issue"])["comments"]
        if w["method"] == "POST":
            comments.append({"id": w["id"], "user": w["user"], "body": w["body"]})
        else:
            for c in comments:
                if c["id"] == w["id"]:
                    c["body"] = w["body"]
    fails = st.get("fail", [])
    if args[0] == "api":
        method = flag("-X", "GET")
        target = next(a for a in args[1:] if not a.startswith("-") and a not in (method, ".login") and
                      args[args.index(a) - 1] not in ("-X", "--jq", "--input"))
        if target == "user":
            if isinstance(st.get("user_calls_ok"), int):
                st["user_calls_ok"] -= 1
                if st["user_calls_ok"] < 0:
                    fails = fails + ["user"]
            if "user" in fails or not st.get("login"):
                fail("authentication required (HTTP 401)")
            save()
            print(st["login"])
            sys.exit(0)
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/milestones\?state=open&per_page=100", target)
        if m:
            if "milestones" in fails:
                fail("HTTP 500 (HTTP 500)")
            print(json.dumps([st["repos"].get(m.group(1), {}).get("milestones", [])]))
            sys.exit(0)
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)", target)
        if m and method == "GET":
            key = "%s/%s" % m.groups()
            if "issue" in fails:
                fail("Server Error (HTTP 500)")
            if key not in st["issues"]:
                fail("Not Found (HTTP 404)")
            print(json.dumps({"number": int(m.group(2)), "state": st["issues"][key]["state"]}))
            sys.exit(0)
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)/comments", target)
        if m and method == "GET" and "--slurp" in args:  # a control item's handoff markers (ownership)
            print(json.dumps([[{"id": c["id"], "user": {"login": c["user"]}, "body": c["body"],
                                "created_at": "2033-01-01T00:00:00Z"} for c in issue("%s/%s" % m.groups())["comments"]]]))
            save()
            sys.exit(0)
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)/comments\?per_page=(\d+)&page=(\d+)", target)
        if m and method == "GET":
            key, page = "%s/%s" % m.groups()[:2], int(m.group(4))
            if page == 1:
                for w in st.get("delayed", []):
                    w["after"] -= 1
                    if w["after"] <= 0:
                        apply(w)
                st["delayed"] = [w for w in st.get("delayed", []) if w["after"] > 0]
            if "page:%d" % page in fails:
                fail("Server Error (HTTP 502)")
            size = min(int(m.group(3)), st.get("page_size", 2))
            comments = issue(key)["comments"][(page - 1) * size:page * size]
            save()
            print(json.dumps([{"id": c["id"], "user": {"login": c["user"]}, "body": c["body"],
                               "html_url": "https://github.com/%s/issues/%s#issuecomment-%d" % (
                                   m.group(1), m.group(2), c["id"])}
                              for c in comments]))
            sys.exit(0)
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)/comments", target)
        n = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/comments/(\d+)", target)
        if method in ("POST", "PATCH", "DELETE") and (m or n):
            body = json.loads(sys.stdin.read() or "{}").get("body")
            audit(method, target, body)
            if method == "DELETE":
                fail("Forbidden (HTTP 403)")
            faults = st.setdefault("faults", {}).setdefault(method, [])
            fault = faults.pop(0) if faults else None
            if method == "POST":
                st["next_id"] = st.get("next_id", 1000) + 1
                w = {"method": "POST", "issue": "%s/%s" % m.groups(), "id": st["next_id"], "user": st["login"],
                     "body": body}
            else:
                owner_repo, cid = n.groups()
                key = next((k for k, v in st["issues"].items() if any(c["id"] == int(cid) for c in v["comments"])), None)
                if key is None:
                    fail("Not Found (HTTP 404)")
                w = {"method": "PATCH", "issue": key, "id": int(cid), "body": body}
            if fault == "rejected":
                fail("Validation Failed (HTTP 422)")
            if fault == "5xx":
                fail("Bad Gateway (HTTP 502)")
            if fault == "never":
                fail("net/http: request canceled (Client.Timeout exceeded)")
            if fault and fault.startswith("delay:"):
                st.setdefault("delayed", []).append(dict(w, after=int(fault.split(":")[1])))
                fail("net/http: request canceled (Client.Timeout exceeded)")
            if fault == "mangle":  # applied with other content, success reported
                w["body"] = body + " (edited)"
            apply(w)
            if fault == "lost":
                fail("read: connection reset by peer")
            save()
            print(json.dumps({"id": w["id"], "body": body}))
            sys.exit(0)
        fail("fake gh: unhandled api %s" % target, 3)
    if args[0] in ("issue", "pr") and args[1] == "list":
        repo, state, limit = flag("-R"), flag("--state"), int(flag("--limit", "30"))
        data = st["repos"].get(repo, {})
        family = "merged" if state == "merged" else "issues" if args[0] == "issue" else "prs"
        if family in fails:
            fail("HTTP 500 (HTTP 500)")
        print(json.dumps(data.get(family, [])[:limit]))
        sys.exit(0)
    fail("fake gh: unhandled %s" % " ".join(args), 3)
''').lstrip()

PROFILE = textwrap.dedent("""\
    [repo]
    owner = "acme"
    name = "{repo}"
    [runtime]
    name = "{runtime}"
    [identities]
    owners = ["acme-owner"]
    coordinator = {{ gh_user = "{login}", name = "Ash" }}
    builder = {{ gh_user = "acme-bot", name = "Ben" }}
    reviewer = {{ gh_user = "acme-reviewer", name = "Vera" }}
    synthesizer = {{ gh_user = "acme-bot", name = "Sam" }}
    [engines]
    coordinator = "claude-code"
    [paths]
    state_dir = "{state}"
    worktree_root = "{state}/wt"
    toolchain_bin = "/opt/node/bin"
    """)

STATUS = textwrap.dedent("""\
    [status]
    enabled = true
    destination = "{dest}"
    instance_id = "{instance}"
    decision_log = "https://github.com/acme/{repo}/issues/985"
    """)


class StatusBase(unittest.TestCase):
    """A temp install `alpha` (acme/widgets) with a fake status API, its destination issue open and empty."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.tmux_log = os.path.join(self.tmp, "tmux.log")  # status --all needs no session: any tmux call is logged
        with open(os.path.join(self.bin, "tmux"), "w") as f:
            f.write('#!/bin/sh\necho "$@" >> "%s"\nexit 1\n' % self.tmux_log)
        os.chmod(os.path.join(self.bin, "tmux"), 0o755)
        self.gh_state, self.audit_path = os.path.join(self.tmp, "gh.json"), os.path.join(self.tmp, "audit.jsonl")
        self.api = {"login": "acme-bot", "page_size": 2, "issues": {"acme/status/5": {"state": "open", "comments": [
            {"id": 11, "user": "acme-owner", "body": "Shared status board."}]}}, "repos": {}, "faults": {}, "fail": []}
        self.save_api()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("CREW_") and k not in ("MDSTACK_CONFIG", "GH_TOKEN")}
        self.env.update(PATH=self.bin + os.pathsep + os.environ["PATH"], FAKE_GH_STATE=self.gh_state,
                        FAKE_GH_AUDIT=self.audit_path, MDSTACK_STATUS_CLOCK=str(CLOCK),
                        MDSTACK_COPY_CLAIMS=os.path.join(self.tmp, "copy-claims"))
        self.project = self.install("alpha")

    def install(self, instance, repo="widgets", login="acme-bot", runtime="tmux", status=True, extra=""):
        """A profile at <tmp>/<instance>/crew.toml with its own state dir; returns its path."""
        directory = os.path.join(self.tmp, instance)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "crew.toml")
        with open(path, "w") as f:
            f.write(PROFILE.format(repo=repo, runtime=runtime, login=login, state=os.path.join(directory, "state")))
            if status:
                f.write(STATUS.format(dest=DEST, instance=instance, repo=repo))
            f.write(extra)
        return path

    def state_root(self, project=None):
        return os.path.join(os.path.dirname(project or self.project), "state")

    def save_api(self):
        with open(self.gh_state, "w") as f:
            json.dump(self.api, f, indent=1)

    def load_api(self):
        with open(self.gh_state) as f:
            self.api = json.load(f)
        return self.api

    def crew(self, *args, project=None, clock=None, **env):
        e = dict(self.env, **env)
        if clock is not None:
            e["MDSTACK_STATUS_CLOCK"] = str(clock)
        return subprocess.run([sys.executable, CREW, *args, "--project", project or self.project],
                              capture_output=True, text=True, env=e)

    def audit(self):
        if not os.path.exists(self.audit_path):
            return []
        with open(self.audit_path) as f:
            return [json.loads(line) for line in f]

    def snapshot(self, project=None):
        """Recursive file list of the state dir with each file's SHA-256."""
        root, out = self.state_root(project), {}
        for d, _, files in os.walk(root):
            for name in files:
                full = os.path.join(d, name)
                with open(full, "rb") as f:
                    out[os.path.relpath(full, root)] = hashlib.sha256(f.read()).hexdigest()
        return out

    def comments(self, key="acme/status/5"):
        return self.load_api()["issues"][key]["comments"]

    def receipt(self, project=None, name="receipt.json"):
        with open(os.path.join(self.state_root(project), "acme__widgets", "status", name)) as f:
            return json.load(f)

    def receipt_file(self, project=None):
        return os.path.join(self.state_root(project), "acme__widgets", "status", "receipt.json")
