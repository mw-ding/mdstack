#!/usr/bin/env python3
"""A19 installed-adapter smoke (docs/campaign-scenarios/A19.md#a19): `smoke.py SOURCE ROOT [--only ENGINE/BACKEND]...
[--skip ENGINE=REASON]... [--model ENGINE=MODEL]... [--repo OWNER/NAME]` runs, for every installed harness with an
interactive launch and every installed session backend, launch, doorbell, ack, probe and stop on one disposable run
through SOURCE's own runtime code: the adapter's role argv under the bypass launch policy (--repo names the repository
a contributor-tier harness needs verified public), the backend's new_session, the foreground check, `mdstack send`'s
nudge, the inbox `ack:` wait, the C5 probe and the pane stop. tmux runs on a dedicated `-L` server named for the run;
herdr uses its local server and closes only the run's own workspace. Each run's worktree is a detached linked worktree
of SOURCE at its HEAD, as `mdstack spawn` makes, removed after the run stops; ROOT holds it and the run's state. One
JSON line per binding pins the source SHA, both adapter files' sha256 and the harness and backend versions; a binding
not installed, without an interactive launch, skipped by policy or whose adapter's role trust check is unmet for
SOURCE's repository root (never accepted here) is `blocked` with the reason. Exit 0 only when every run binding
passed."""
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

src, root = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
only = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--only"]
skip = dict(sys.argv[i + 1].split("=", 1) for i, a in enumerate(sys.argv) if a == "--skip")
models = dict(sys.argv[i + 1].split("=", 1) for i, a in enumerate(sys.argv) if a == "--model")
repo = dict(zip(("repo.owner", "repo.name"), next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--repo"),
                                                  "/").split("/", 1)))
for k in ("TMUX", "TMUX_PANE", "GH_TOKEN", "GITHUB_TOKEN"):
    os.environ.pop(k, None)  # never the caller's server or forge (campaign-harness.md#refusal-before-mutation)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(src, path))
    mod = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shared = load("crew_shared", "environments/terminal/crew.d/_shared.py")
send = load("crew_send", "environments/terminal/crew.d/send.py")
BRIEF = ("This is a disposable mdstack smoke run; do not touch anything else. Now append the line `ready` to the file "
         "named by $CREW_STATUS and end your turn. Later a line `inbox: <id>` arrives: append `ack: <id>` (that id) "
         "to $CREW_STATUS and end your turn.\n")


def version(argv):
    r = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    lines = [line.strip() for line in (r.stdout or r.stderr).splitlines() if line.strip()]
    return lines[-1] if lines and not r.returncode else "exit %d: %s" % (r.returncode, lines[-1] if lines else "")


def digest(path):
    return hashlib.sha256(open(os.path.join(src, path), "rb").read()).hexdigest()


def wait(check, secs):
    deadline = time.monotonic() + secs
    while not check():
        if time.monotonic() > deadline:
            return False
        time.sleep(1)
    return True


def smoke(engine, adapter, backend, mod, rec):
    """Launch, ready, doorbell, ack, probe and stop on one run; each step's outcome lands in rec, the first failure stops the rest."""
    name, session = "smoke-" + engine, "a19-smoke-%d-%s" % (os.getpid(), engine)
    state, wt = os.path.join(root, backend, engine, "state"), os.path.join(root, backend, engine, "wt")
    for d in ("status", "inbox"):
        os.makedirs(os.path.join(state, d), exist_ok=True)
    subprocess.run(["git", "-C", src, "worktree", "add", "-q", "--detach", wt, source], check=True)
    status = os.path.join(state, "status", name + ".status")
    open(os.path.join(state, "brief.md"), "w").write(BRIEF)
    shared.tmux.name = backend
    mod.bind(session, "dedicated")
    argv = shared.harness(engine, models.get(engine, ""), "medium", wt, state, "bypass", repo)
    env = {"CREW_ID": name, "CREW_STATE": state, "CREW_STATUS": status, "CREW_BRIEF": os.path.join(state, "brief.md"),
           "CREW_INBOX": os.path.join(state, "inbox", name + ".jsonl")}
    rec["argv"], steps, run = argv, rec.setdefault("steps", {}), None
    try:
        mod.new_session(session, name, wt, env, 'exec %s "%s"' % (shlex.join(argv), shared.POINTER))
        shared.wait_harness(session, 0, name, adapter.EXECUTABLE, 60)
        run = dict(shared.identity(session, 0), index=0, harness=adapter.EXECUTABLE)
        if not run["pane_id"]:
            raise RuntimeError("launch: the run exited before its identity was read")
        steps["launch"] = "ok: %s pid %s" % (run["pane_id"], run["pane_pid"])
        said = lambda word: os.path.exists(status) and word in open(status).read().split()  # noqa: E731
        ready = wait(lambda: said("ready") or not mod.has_session(session), 300) and said("ready")
        steps["ready"] = "ok" if ready else "failed: no ready line (run %s)" % shared.probe(session, name, run, {
            n: i for i, n in mod.list_windows(session)})
        msg = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + os.urandom(3).hex()
        open(env["CREW_INBOX"], "a").write(json.dumps({"id": msg, "kind": "smoke", "refs": ["#1439"]}) + "\n")
        failed = ready and send.nudge(session, 0, "inbox: " + msg)
        steps["doorbell"] = "failed: " + failed if failed else "ok: inbox: " + msg if ready else "not run"
        acked = ready and not failed and shared.wait_ack(state, name, msg, 300) == 0
        steps["ack"] = "ok" if acked else "failed: no ack: %s after 300s" % msg if ready and not failed else "not run"
        steps["probe"] = shared.probe(session, name, run, {n: i for i, n in mod.list_windows(session)})
    finally:
        if mod.has_session(session):
            rec["screen_tail"] = [line for line in mod.capture(session, 0).splitlines() if line.strip()][-8:]
        survived = shared.stop_pane(session, 0) if mod.has_session(session) else None
        mod.kill_session(session)
        after = run and shared.probe(session, name, run, {n: i for i, n in mod.list_windows(session)})
        steps["stop"] = "ok: probe %s after" % after if not survived and after in ("missing", None) else \
            "failed: group %s survived, probe %s" % (survived, after)
        subprocess.run(["git", "-C", src, "worktree", "remove", "--force", wt], check=True)
    rec["result"] = "pass" if all(str(v).startswith(("ok", "alive")) for v in steps.values()) and \
        set(steps) == {"launch", "ready", "doorbell", "ack", "probe", "stop"} else "fail"


source = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
common = subprocess.run(["git", "-C", src, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                        capture_output=True, text=True).stdout.strip()
checkout = os.path.dirname(common) if os.path.basename(common) == ".git" else src  # the root linked worktrees key on


def untrusted(adapter):
    """The adapter's unmet role trust check for checkout with its fix, or None (docs/runtimes/harness-adapters.md)."""
    rows = [r for r in getattr(adapter, "role_checks", lambda v, c: [])({}, checkout) if r[0] != "ok"]
    return "; ".join("%s %s: %s" % (r[1], r[2], r[3]) for r in rows) or None


results = []
for backend, mod in sorted(shared.sessions.ADAPTERS.items()):
    for engine, adapter in sorted(shared.harnesses.ADAPTERS.items()):
        if only and "%s/%s" % (engine, backend) not in only:
            continue
        rec = {"binding": "%s/%s" % (engine, backend), "source": source,
               "adapter": {p: digest(p)[:12] for p in ("harnesses/%s/adapter.py" % engine,
                                                       "environments/terminal/sessions/%s/adapter.py" % backend)}}
        missing = [e for e in (adapter.EXECUTABLE, mod.EXECUTABLE) if not shutil.which(e)]
        trust = not missing and hasattr(adapter, "role_argv") and engine not in skip and untrusted(adapter)
        if missing or not hasattr(adapter, "role_argv") or engine in skip or trust:
            rec["result"] = "blocked"
            rec["block"] = "installation: %s not on PATH" % ", ".join(missing) if missing else \
                "unsupported: no interactive launch (docs/runtimes/harness-adapters.md#adapter-modules)" if \
                not hasattr(adapter, "role_argv") else "policy: " + skip[engine] if engine in skip else \
                "precondition: " + trust
        else:
            bypass = adapter.PERMISSION["bypass"]  # muse --version alone applies its own sandbox
            rec["versions"] = {adapter.EXECUTABLE: version([adapter.EXECUTABLE, *bypass, "--version"]),
                               mod.EXECUTABLE: version([mod.EXECUTABLE, "-V" if backend == "tmux" else "--version"])}
            try:
                smoke(engine, adapter, backend, mod, rec)
            except Exception as e:  # a launch refusal or backend error is this binding's failure, not the run's
                rec.setdefault("result", "fail")
                rec["error"] = "%s: %s" % (type(e).__name__, str(e)[-300:])
        results.append(rec)
        print(json.dumps(rec), flush=True)
print("A19 smoke: " + ", ".join("%s %s" % (r["binding"], r["result"]) for r in results))
sys.exit(0 if all(r["result"] in ("pass", "blocked") for r in results) else 1)
