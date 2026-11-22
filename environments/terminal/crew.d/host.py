"""Check or prepare a named inventory host; default project is CREW_PROJECT, else the user-level config. Primary uses doctor locally.

Usage: mdstack host check HOST [--project FILE] [--org-profile FILE] [--fix]
       mdstack host prepare HOST [--project FILE] [--org-profile FILE] [--prune]

prepare creates the host's project mirror with its own gh login, or fetches it, plus its worktree and state
directories (the hardened `prepare` call, crew-remote.py), then runs check. On the primary it fetches the project
checkout. On a forge-less host it fetches the primary's checkout and seeds the host's mirror with a full bundle of
the default branch (the `seed` call); the host never reaches the forge. A failed step prints `fail prepare <step>`
and the host stays not ready. A host with checkout = "command" sends `prepare` with checkout=command instead,
forge-less or not: the host runs the checkout command declared in its own root (never sent over SSH) in place of the
mirror steps, and check then requires a `project checkout` row in place of `project mirror` (#1035). A primary with
checkout = "command" runs its own declaration under its root (unset: the resolved paths.root, #1961) locally with the same functions instead of the fetch;
check reads the receipt, never runs the command, and also needs the declared path to be the project checkout (#1723).
With an
[install] table, prepare on a non-primary host also sends the primary's install.json (tag, bundle digest, transport)
as the toolkit pin, and the host installs that release from the same source with the shared verifier
(docs/bootstrap.md Host toolkit); no primary release install fails `toolkit`.
--prune then removes the host's toolkit versions and staging leftovers that no project there pins, and lists them.
With [install], check on a non-primary host adds a required `toolkit` row (the `version` call with the pin): it
fails when the project pins no toolkit or another tag there, or the version's record or a file hash differs.

Remote checks use the hardened `check` call (crew-remote.py `call`: version, ssh argv) to the crew-host entrypoint:
root, project=owner__repo, default_branch, capabilities, roles, identities, toolchain_bin, forge, fix and ssh_port.
Reply: checks=[{status: ok|warn|fail|human|unverified, check, detail, hint?}], projects=[owner__repo], load=int.
The entrypoint probes tools, logins, the project mirror, the runner service and capacity; it repairs nothing yet,
so fix only passes through and each failing row's hint names the step.
Check and prepare/seed send capabilities.os; the entrypoint picks its host OS adapter from it against its uname, and
a mismatch fails the `capabilities` row (check 5), or fails prepare step `capabilities` before any change.
No credentials, profile contents or shell snippets cross SSH. A missing runner never reports ready.
A forge-less host (forge = false) sends no roles or identities; its logins row prints n/a, or warn when the
runner's logins check is not ok, meaning a forge login is present there.
Exit 1 for fail, human or unverified (doctor's human rows also block placement), otherwise 0.
A session-runtime profile (runtime.name = "session") gets the same rows: doctor runs its runtime-independent rows on
the primary, whose load is 0 since session workers hold no tmux windows; remote hosts are checked as for tmux (#1122).
"""
from argparse import Namespace
import base64
import contextlib
import io
import json
import os
import subprocess
import tempfile
from crew_shared import checkout, commands, crew_render, harnesses, load, profile, tmux

REMOTE = "environments/terminal/remote/crew-remote.py"


def options(p):
    p.add_argument("--project", default=os.environ.get("CREW_PROJECT"))
    p.add_argument("--org-profile")


def inventory(values):
    return sorted({k.split(".")[1] for k in values if k.startswith("hosts.")})


def setting(values, host, key, default=None):
    return values.get("hosts.%s.%s" % (host, key), default)


def address(values, host):
    """The SSH destination of an inventory host: its `address` (a DNS name), else its label (#1034)."""
    return setting(values, host, "address", host)


def ssh_port(host):
    """The SSH port the client resolves for host (`ssh -G`), sent so the host's adapter checks that listener."""
    try:
        r = subprocess.run(["ssh", "-G", host], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None  # the check call then reports the host unreachable
    ports = [line.split()[1] for line in r.stdout.splitlines() if line.startswith("port ")]
    return int(ports[0]) if not r.returncode and ports and ports[0].isdigit() else None


def toolkit_check(host, project, root, pin):
    """The host's `toolkit` row: its pinned toolkit, record and file hashes against the primary's pin."""
    if not pin["tag"]:
        return dict(status="fail", check="toolkit", detail="no release install on the primary to pin",
                    hint="run mdstack bootstrap --version, then mdstack host prepare")
    reply = load("crew_remote", REMOTE).call(host, "version", project=project, root=root, toolkit=pin)
    facts = reply.get("toolkit") if reply.get("result") == "ok" else None
    if not isinstance(facts, dict) or facts.get("status") not in ("ok", "fail"):
        return dict(status="fail", check="toolkit", detail="no toolkit facts: %s" % (
            reply.get("reason") or reply.get("error") or "host entrypoint predates the toolkit pin"))
    return dict(facts, check="toolkit", **({} if facts["status"] == "ok" else {"hint": "run mdstack host prepare"}))


def inspect_host(args, values, session, state, host):
    project = values["repo.owner"] + "__" + values["repo.name"]
    if setting(values, host, "primary", False):
        with contextlib.redirect_stdout(io.StringIO()) as report:
            code = commands()["doctor"].run(Namespace(project=args.project, org_profile=args.org_profile,
                                                       fix=getattr(args, "fix", False), dry_run=False, milestone=None))
        text = report.getvalue()
        login_ok = True
        for engine in setting(values, host, "capabilities.engines", []):
            ok = commands()["doctor"].sh(*harnesses.login_status(engine))[0] == 0
            login_ok = login_ok and ok
            text += ("ok" if ok else "human") + " engine login " + engine + (": logged in\n" if ok else
                    ": log in on the host\n")
        if command_checkout(values, host):
            row = primary_checkout_row(values, args.project, host, project)
            mirror = row["status"] == "ok"
            text += "%s %s: %s%s\n" % (row["status"], row["check"], row["detail"],
                                       "; " + row["hint"] if row.get("hint") else "")
        else:
            mirror = commands()["doctor"].sh("git", "-C", checkout(values, args.project), "rev-parse", "--verify",
                                             "refs/remotes/origin/" + values["repo.default_branch"])[0] == 0
            text += ("ok" if mirror else "fail") + " project mirror: default branch " + values["repo.default_branch"] + "\n"
        runs = sum(i >= 10 for i, _ in tmux.list_windows(session)) if session and tmux.has_session(session) else 0
        ready = mirror and login_ok and not code and not any(line.startswith("human") for line in text.splitlines())
        return dict(reachable=True, ready=ready, report=text, projects=[project] if ready else [], load=runs)
    forge = setting(values, host, "forge", True)
    roles = setting(values, host, "roles", ["builder", "reviewer"]) if forge else []
    request = dict(root=setting(values, host, "root", "~/.mdstack"), project=project,
                   default_branch=values["repo.default_branch"], roles=roles,
                   capabilities={k: setting(values, host, "capabilities." + k, []) for k in
                                 ("os", "arch", "devices", "engines")},
                   identities={r: values["identities.%s.gh_user" % r] for r in roles},
                   toolchain_bin=setting(values, host, "toolchain_bin"), forge=forge, fix=getattr(args, "fix", False),
                   ssh_port=ssh_port(address(values, host)), **command_checkout(values, host))
    reply = load("crew_remote", REMOTE).call(address(values, host), "check", **request)
    if reply["result"] == "unreachable":
        return dict(reachable=False, ready=False, report="fail reachable: SSH unavailable or timed out: %s\n"
                    % reply["error"], projects=[], load="?")
    if reply["result"] != "ok":
        return dict(reachable=True, ready=False, report="fail remote check: %s %s; check overlay, host key and "
                    "runner\n" % (reply["result"], reply.get("reason") or reply.get("error")), projects=[], load="?")
    try:
        checks, projects, runs = reply["checks"], reply["projects"], reply["load"]
        if not checks or not isinstance(projects, list) or any(not isinstance(p, str) for p in projects) \
                or type(runs) is not int or runs < 0:
            raise ValueError("invalid host facts")
        for c in checks:
            if c["status"] not in ("ok", "warn", "fail", "human", "unverified"):
                raise ValueError("unknown check status")
        required = {"tools", "project checkout" if request.get("checkout") else "project mirror"} \
            | ({"logins"} if forge else set())
        pin = toolkit_pin(values, state)
        if pin is not None:
            checks = checks + [toolkit_check(address(values, host), project, request["root"], pin)]
            required.add("toolkit")
        if not forge:
            logins = [c for c in checks if c["check"] == "logins"]
            checks = [c for c in checks if c["check"] != "logins"] + [
                dict(status="warn", check="logins", detail="forge login present on a forge-less host",
                     hint="remove it; the host never reaches the forge")
                if logins and logins[0]["status"] != "ok" else
                dict(status="n/a", check="logins", detail="forge-less host; runner jobs only")]
        ready = required <= {c["check"] for c in checks} and project in projects \
            and all(c["status"] in ("ok", "warn", "n/a") for c in checks) \
            and all(c["status"] == "ok" for c in checks if c["check"] in required)
        report = "".join("%s %s: %s%s\n" % (c["status"], c["check"], c["detail"],
                         "; " + c["hint"] if c.get("hint") else "") for c in checks)
        return dict(reachable=True, ready=ready, report=report, projects=projects, load=runs)
    except (ValueError, KeyError, TypeError):
        return dict(reachable=True, ready=False, report="fail remote check: invalid runner response\n",
                    projects=[], load="?")


def toolkit_pin(values, state):
    """The primary's install record as the host toolkit pin; None without an [install] table (no toolkit)."""
    if not any(k.startswith("install.") for k in values):
        return None
    try:
        with open(os.path.join(state, "install.json")) as f:
            record = json.load(f)
    except (OSError, ValueError):
        record = {}
    return dict(tag=record.get("tag"), bundle_sha256=record.get("bundle_sha256"), transport=record.get("transport"))


def command_checkout(values, host):
    """{checkout: command} for a host whose checkout comes from its declared command, else {} (requests unchanged)."""
    return dict(checkout="command") if setting(values, host, "checkout") == "command" else {}


def primary_root(values, host):
    """The primary's root: its declared `root`, else the resolved paths.root (CREW_ROOT already applied), else
    user_root(); never a fixed ~/.mdstack under another install root (#1961)."""
    default = values.get("paths.root") or crew_render.crew_config.user_root()
    return os.path.abspath(os.path.expanduser(setting(values, host, "root", default)))


def primary_checkout_row(values, project_file, host, project):
    """The primary's `project checkout` row from the receipt its last prepare wrote (the command never runs here);
    the declared path must also be the profile's project checkout (#1723)."""
    remote = load("crew_remote", REMOTE)
    root, want = primary_root(values, host), checkout(values, project_file)
    row = remote.checkout_row(root, project)
    if row["status"] != "ok":
        return row
    path = remote.declared_checkout(root, project)[1]
    if os.path.realpath(path) != os.path.realpath(want):
        return remote.row("fail", "project checkout", "declared path %s is not the project checkout %s" % (path, want),
                          "fix checkout/%s.json or paths.checkout" % project)
    return row


def prepare(args, values, host, state):
    """Primary: fetch its checkout, or run its declared checkout command (#1723). Forge-less: fetch, then seed the default branch as a git bundle. Else `prepare`.
    A non-primary host also gets the toolkit pin when the profile has [install]."""
    checkout_dir, branch = checkout(values, args.project), values["repo.default_branch"]
    project, root = values["repo.owner"] + "__" + values["repo.name"], setting(values, host, "root", "~/.mdstack")
    primary, forge = setting(values, host, "primary", False), setting(values, host, "forge", True)
    pin = None if primary else toolkit_pin(values, state)
    if pin is not None and not pin["tag"]:
        return dict(result="failed", step="toolkit", error="no release install on the primary to pin; run crew "
                    "bootstrap --version first")
    extra = dict(os=setting(values, host, "capabilities.os"), **(dict(toolkit=pin) if pin else {}))
    if getattr(args, "prune", False):
        extra["prune"] = True
    extra.update(command_checkout(values, host))
    if primary and "checkout" in extra:  # #1723: the declared command runs here, no git fetch
        remote, receipt = load("crew_remote", REMOTE), os.path.join(primary_root(values, host), "state", project,
                                                                     "checkout.json")
        with contextlib.suppress(FileNotFoundError):
            os.remove(receipt)  # a failed prepare must not leave an earlier success receipt behind
        try:
            return dict(result="ok", **remote.run_checkout(primary_root(values, host), project))
        except remote.Failed as e:
            return e.reply
    if not primary and (forge or "checkout" in extra):
        return load("crew_remote", REMOTE).call(address(values, host), "prepare", timeout=660, project=project,
                                                root=root, **extra)
    r = subprocess.run(["git", "-C", checkout_dir, "fetch", "-q", "origin"], capture_output=True, text=True)
    if r.returncode or primary:
        return dict(result="failed", step="fetch", error=r.stderr.strip()[-200:]) if r.returncode else \
            dict(result="ok", step="fetch")
    with tempfile.TemporaryDirectory() as tmp:
        bundle = os.path.join(tmp, "seed.bundle")
        r = subprocess.run(["git", "-C", checkout_dir, "bundle", "create", "-q", bundle, "refs/remotes/origin/" + branch],
                           capture_output=True, text=True)
        if r.returncode:
            return dict(result="failed", step="bundle", error=r.stderr.strip()[-200:])
        with open(bundle, "rb") as f:
            data = base64.b64encode(f.read()).decode()
    return load("crew_remote", REMOTE).call(address(values, host), "seed", timeout=660, project=project, root=root,
                                            branch=branch, bundle=data, **extra)


def register(sub):
    p = sub.add_parser("host", help="check or prepare an inventory host's project readiness")
    actions = p.add_subparsers(dest="action", required=True)
    p = actions.add_parser("check")
    p.add_argument("host")
    options(p)
    p.add_argument("--fix", action="store_true")
    p = actions.add_parser("prepare")
    p.add_argument("host")
    options(p)
    p.add_argument("--prune", action="store_true", help="remove toolkit versions no project on the host pins")


def run(args):
    values, session, state = profile(args, runtimes=("tmux", "session"))
    if args.host not in inventory(values):
        print("crew host: unknown inventory host " + args.host)
        return 1
    if args.action == "prepare":
        reply = prepare(args, values, args.host, state)
        if reply["result"] != "ok":
            print("fail prepare %s: %s" % (reply.get("step", reply["result"]),
                                          reply.get("error") or reply.get("reason", "")))
            print("%s: not ready" % args.host)
            return 1
        print("ok prepare %s: project %s" % (reply["step"], "checkout" if reply["step"] == "checkout" else "mirror"))
        if reply.get("toolkit"):
            print("ok prepare toolkit: mdstack %s %s" % (reply["toolkit"]["tag"], reply["toolkit"]["state"]))
        if "pruned" in reply:
            print("ok prepare prune: %s" % (", ".join(reply["pruned"]) or "nothing to remove"))
    facts = inspect_host(args, values, session, state, args.host)
    print(facts["report"], end="")
    print("%s: %s" % (args.host, "ready" if facts["ready"] else "not ready"))
    return 0 if facts["ready"] else 1
