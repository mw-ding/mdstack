#!/usr/bin/env python3
"""M25 disposable sandbox (#785): set up and tear down a level-a local sandbox, and plan a level-b forge sandbox.

`setup` refuses before any write when ROOT exists non-empty or overlaps a production root, then creates under ROOT a
bare origin (`origin.git`), a clone (`repo`) seeded with a local CI fixture, the sandbox profile (`repo/crew.toml`,
git-excluded, as `mdstack spawn` takes the repo from the profile's checkout; its own repo slug, tmux session,
state/worktree/live roots and `toolchain_bin`), engine and forge stubs in `state/bin` (`claude` and `codex` run bash
under the engine's name so the liveness probe sees that harness, and ack each `inbox:` line; `gh` answers offline
from scenario-written JSON, `gh api` from a path map that keeps posted comments), a control-item and fixtures record
(`state/sandbox.json`: labels, identities, CI), the guarded run manifest (`state/manifest.json`, via
campaign-guard.py) and, when tmux is installed, the `state/bin/tmux` shim that pins every scenario tmux call to the
sandbox socket. `teardown` runs the guard check, kills only the sandbox's own tmux session on the sandbox socket,
records every repo or worktree with uncommitted or unpushed work and the sentinel check in `state/cleanup.json`;
`--remove` deletes ROOT only when nothing is retained and the sentinel is unchanged. `plan-forge` prints the level-b
forge operations and never runs them: level b is blocked on owner account access. Python 3.11+ stdlib only. Contract
and runbook: docs/campaign-harness.md.

Usage: campaign-sandbox.py setup --root DIR --run-id ID --production FILE --source DIR --release ID --sentinel FILE
                                 [--scenario AXX ...]
       campaign-sandbox.py teardown MANIFEST [--remove]
       campaign-sandbox.py plan-forge --repo OWNER/NAME --production FILE
"""
import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard, crew_repo = load("campaign_guard", "campaign-guard.py"), load("crew_repo", "../connectors/github/crew-repo.py")
EXTRA_LABELS = ["integration:finding", "integration:run"]
IDENTITIES = {"builder": "sandbox-builder", "reviewer": "sandbox-reviewer"}
PROFILE = """[repo]\nowner = "campaign"\nname = "sandbox-{run}"\ndefault_branch = "main"\n
[runtime]\nname = "tmux"\n\n[runtime.options]\nsession = "{session}"\n
[paths]\nstate_dir = "{base}/state"\nworktree_root = "{base}/wt"\nlive_dir = "{base}/live"\n
toolchain_bin = "{root}/state/bin"\n"""
# Each team's --org-profile (#801, #1440): its runtime instance and the one control item; --engine adds the engine.
TEAM = """[repo]\ncontrol_item = 1\n\n[runtime]\ninstance = "{name}"\n\n[identities.coordinator]
gh_user = "sandbox-coordinator"\n"""
ENGINES = """\n[engines]\ncoordinator = "{engine}"\nfallback_engine = "{engine}"\ntrivial = {{ order = ["{pick}"] }}
default = {{ order = ["{pick}"] }}\ndeep = {{ order = ["{pick}"] }}\n"""
# An inherited $TMUX beats TMUX_TMPDIR, so a bare `tmux kill-server` from a crew pane kills the owner's server (#817).
SHIM = """#!/bin/sh
# Campaign sandbox tmux shim (#817): pin every call to the sandbox socket and never follow an inherited $TMUX.
# A crew's own -L NAME (#818) passes through: tmux ignores -L when -S is given.
sock={sock}
refuse() {{ echo "tmux shim: refused $1 (outside the sandbox)" >&2; exit 2; }}
want=
for arg; do
  if [ -n "$want" ]; then
    [ "$want" = S ] && [ "$arg" != "$sock" ] && refuse "-S $arg"
    want=; continue
  fi
  case "$arg" in
    --) break ;;
    -?*) ;;
    *) break ;;
  esac
  # Walk grouped flags as tmux's getopt does (-uS PATH, -2L NAME, -uf FILE -S PATH).
  rest=${{arg#-}}
  while [ -n "$rest" ]; do
    c=${{rest%"${{rest#?}}"}}; rest=${{rest#?}}
    case "$c" in
      S) if [ -z "$rest" ]; then want=S; elif [ "$rest" != "$sock" ]; then refuse "$arg"; fi; rest= ;;
      c|f|L|T) [ -z "$rest" ] && want=v; rest= ;;
    esac
  done
done
unset TMUX TMUX_PANE
exec {real} -S "$sock" "$@"
"""
STUB_ENGINE = """#!/bin/sh\nexec "{bin}/exe/{name}" "{bin}/stub-body.sh" "$@"\n"""
STUB_BODY = """# Campaign engine stub: no model. Logs its start and every line typed, acks each `inbox: <id>` nudge in
# $CREW_STATUS, and runs a `campaign-exec: <sh>` line as a scenario's tool session.
log="${CAMPAIGN_STUB_LOG:-/dev/null}"
echo "start $(date -u +%FT%TZ) pid=$$ role=${CREW_ROLE:-} id=${CREW_ID:-} argv=$*" >> "$log"
echo "stub harness ready"
while IFS= read -r line; do
  echo "got ${CREW_ID:-ash}: $line" >> "$log"
  case "$line" in "campaign-exec: "*) eval "${line#campaign-exec: }"; continue;; esac
  echo "got: $line"
  id=$(printf '%s\\n' "$line" | sed -n 's/.*inbox: \\([^ ]*\\).*/\\1/p')
  [ -n "$id" ] && [ -n "$CREW_STATUS" ] && echo "ack: $id" >> "$CREW_STATUS"
done
exit 0
"""
STUB_GH = """#!/bin/sh\n# Campaign forge stub (level a has no forge): logs every call; a scenario scripts the forge's answers in
# $CAMPAIGN_GH_DIR/<cmd>-<sub>[-<arg>].json (pr-list.json, pr-view-5.json), a `--label L` query first in
# <cmd>-<sub>-label-L.json (issue-list-label-crew:hold.json), a `--state S` call next from <cmd>-<sub>-S.json
# (issue-list-closed.json); otherwise token and empty views. A `--body-file -` body is kept in bodies.log after its call.
echo "$*" >> "${CAMPAIGN_GH_LOG:-/dev/null}"
d=${CAMPAIGN_GH_DIR:-/nonexistent}
case " $* " in *" --body-file - "*) [ -d "$d" ] && { echo "--- gh $*"; cat; } >> "$d/bodies.log";; esac
[ "$1" = api ] && [ -f "$d/api.json" ] && exec python3 "$(dirname "$0")/gh-api" "$@"
label=; prev=; for a; do [ "$prev" = --label ] && label=$a; prev=$a; done
[ -n "$label" ] && [ -f "$d/$1-$2-label-$label.json" ] && exec cat "$d/$1-$2-label-$label.json"
s=$(printf '%s\\n' "$@" | sed -n '/^--state$/{n;p;q;}')
for f in ${s:+"$d/$1-$2-$s.json"} "$d/$1-$2-$3.json" "$d/$1-$2.json"; do [ -f "$f" ] && exec cat "$f"; done
case "$1 $2" in
  "auth token") echo gho_campaignstub;;
  "issue view"|"pr view") echo '{"labels":[],"comments":[],"closingIssuesReferences":[],"state":"OPEN","title":"stub","body":""}';;
  *) echo '[]';;
esac
"""

STUB_GH_API = """#!/usr/bin/env python3
# Campaign forge stub for `gh api` once a scenario writes $CAMPAIGN_GH_DIR/api.json, a map of paths below
# repos/<owner>/<name>/ (query dropped) to answers. GET prints the answer (as one page with --slurp; [] when absent);
# `-F body=@-` appends a comment by $CAMPAIGN_GH_USER (default sandbox-coordinator) and prints it; DELETE of
# issues/<n>/labels/<name> drops that label from data["issues"]. "fail": N fails the next N posts, and with
# "fail_mode": "lost" each lands first, as a timed-out post that did post. A `post-probe` script beside api.json runs
# at each post and its stdout is kept on the comment as "probe".
import datetime, fcntl, json, os, subprocess, sys
d, args = os.environ["CAMPAIGN_GH_DIR"], sys.argv[2:]
rel = next(a for a in args if a.startswith("repos/")).split("/", 3)[3].split("?")[0]
with open(os.path.join(d, "api.json"), "r+") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    data, code = json.load(f), 0
    if "-F" not in args and "DELETE" not in args:
        print(json.dumps([data.get(rel, [])] if "--slurp" in args else data.get(rel, [])))
        sys.exit(0)
    if "DELETE" in args:
        n, label = rel.split("/")[1], rel.split("/", 3)[3]
        for i in data.get("issues", []):
            if str(i["number"]) == n:
                i["labels"] = [lb for lb in i["labels"] if lb["name"] != label]
    else:
        code = 1 if data.get("fail", 0) else 0
        data["fail"] = max(data.get("fail", 0) - 1, 0)
        if not code or data.get("fail_mode") == "lost":
            probe = os.path.join(d, "post-probe")
            post = {"id": len(data.get(rel, [])) + 1, "user": {"login": os.environ.get("CAMPAIGN_GH_USER",
                    "sandbox-coordinator")}, "body": sys.stdin.read(), "created_at": datetime.datetime.now(
                    datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "probe": subprocess.run(
                    ["sh", probe], capture_output=True, text=True).stdout.strip() if os.path.exists(probe) else None}
            data.setdefault(rel, []).append(post)
            print(json.dumps(post) if not code else "")
    f.seek(0)
    f.truncate()
    json.dump(data, f, indent=1)
sys.exit(code)
"""


def stubs(bindir, real=None):
    """The engine and forge stubs; the real engine (--engine) gets no stub, so its own CLI runs."""
    os.makedirs(os.path.join(bindir, "exe"), exist_ok=True)
    Path(bindir, "stub-body.sh").write_text(STUB_BODY)
    for name in ("claude", "codex"):
        if name == real:
            continue
        os.symlink("/bin/bash", os.path.join(bindir, "exe", name))
        Path(bindir, name).write_text(STUB_ENGINE.format(bin=bindir, name=name))
    Path(bindir, "gh").write_text(STUB_GH)
    Path(bindir, "gh-api").write_text(STUB_GH_API)
    for name in ("claude", "codex", "gh", "gh-api"):
        if name != real:
            os.chmod(os.path.join(bindir, name), 0o755)
    return bindir


def sandbox_root(m):
    return os.path.dirname(os.path.dirname(m["profile"]["path"]))


def tmux_socket(state_dir):
    return os.path.join(state_dir, "tmux", "tmux-%d" % os.getuid(), "default")


def install_shim(state_dir):
    real = shutil.which("tmux")
    if not real:
        return None
    sock = tmux_socket(state_dir)
    os.makedirs(os.path.dirname(sock), mode=0o700)
    shim = Path(state_dir, "bin", "tmux")
    shim.parent.mkdir(exist_ok=True)
    shim.write_text(SHIM.format(sock=shlex.quote(sock), real=shlex.quote(real)))
    shim.chmod(0o755)
    return {"socket": sock, "shim": str(shim)}


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=campaign", "-c", "user.email=campaign@sandbox.invalid", *args],
                          cwd=cwd, capture_output=True, text=True, check=True).stdout


def setup(a):
    root = os.path.realpath(a.root)
    prod = guard.target(a.production)["roots"].values()
    if os.path.exists(root) and os.listdir(root):
        return ["root: %s exists and is not empty" % root]
    if any(guard.nested(root, p) for p in prod):
        return ["root: %s overlaps a production root" % root]
    for sub in ("state", "wt", "live"):
        os.makedirs(os.path.join(root, sub))
    git("init", "-q", "--bare", "-b", "main", os.path.join(root, "origin.git"))
    repo = os.path.join(root, "repo")
    git("clone", "-q", os.path.join(root, "origin.git"), repo)
    Path(repo, "ci.sh").write_text("#!/bin/sh\n# Level-a CI fixture: the scenario sets CI_RESULT to replay red.\n"
                                   "exit \"${CI_RESULT:-0}\"\n")
    git("add", "ci.sh", cwd=repo)
    git("commit", "-q", "-m", "campaign sandbox seed", cwd=repo)
    git("push", "-q", "origin", "HEAD:main", cwd=repo)
    Path(repo, ".git", "info", "exclude").write_text("crew.toml\n")
    session = "crew-campaign-%s" % a.run_id
    Path(repo, "crew.toml").write_text(PROFILE.format(run=a.run_id, root=root, base=root, session=session))
    teams = [{"name": "a", "repo": repo, "session": session, "worktree_root": os.path.join(root, "wt")}]
    if a.teams == 2:  # A28's second team (#1440): its own checkout, session and roots, on the same origin
        base, repo_b = os.path.join(root, "team-b"), os.path.join(root, "repo-b")
        for sub in ("state", "wt", "live"):
            os.makedirs(os.path.join(base, sub))
        git("clone", "-q", os.path.join(root, "origin.git"), repo_b)
        Path(repo_b, ".git", "info", "exclude").write_text("crew.toml\n")
        Path(repo_b, "crew.toml").write_text(PROFILE.format(run=a.run_id, root=root, base=base, session=session + "-b"))
        teams.append({"name": "b", "repo": repo_b, "session": session + "-b",
                      "worktree_root": os.path.join(base, "wt")})
    engine = a.engine.split("/", 1)[0] if a.engine else None
    for t in teams if a.teams == 2 else []:
        t["org_profile"] = os.path.join(root, "state", "team-%s.toml" % t["name"])
        Path(t["org_profile"]).write_text(TEAM.format(name=t["name"]) + (
            ENGINES.format(engine=engine, pick=a.engine) if engine else ""))
    for t in teams:
        t.update(project=os.path.join(t["repo"], "crew.toml"), source=os.path.realpath(a.source), release=a.release)
        t["sha256"] = {p: guard.sha256(p) for p in (t["project"], t.get("org_profile")) if p}
    labels = [n for n, _, _ in crew_repo.LABELS] + EXTRA_LABELS
    Path(root, "state", "sandbox.json").write_text(json.dumps({
        "level": "a", "run_id": a.run_id, "labels": labels, "identities": IDENTITIES, "ci": "ci.sh",
        "tmux": install_shim(os.path.join(root, "state")),
        "stubs": stubs(os.path.join(root, "state", "bin"), guard.config.harnesses.ENGINE_CMD.get(engine)),
        "teams": teams,
        "control_item": {"number": 1, "title": "M25 campaign control (%s)" % a.run_id, "labels": ["integration:run"]},
    }, indent=2) + "\n")
    argv = ["manifest", "--sandbox", os.path.join(repo, "crew.toml"), "--production", a.production, "--source",
            a.source, "--release", a.release, "--run-id", a.run_id, "--sentinel", a.sentinel,
            "--out", os.path.join(root, "state", "manifest.json")]
    return guard.main(argv + [x for s in a.scenario for x in ("--scenario", s)])


def teams_of(m):
    """The sandbox's teams from state/sandbox.json; a record from before #1440 is the pinned team alone."""
    root = sandbox_root(m)
    rec = json.loads(Path(root, "state", "sandbox.json").read_text())
    return rec.get("teams") or [{"name": "a", "repo": os.path.join(root, "repo"), "session": m["session"],
                                 "worktree_root": m["roots"]["worktree_root"], "project": m["profile"]["path"]}]


def team_refusals(m):
    """Every reason teardown must not act on a team: a profile changed since setup, or a resolved root outside the
    sandbox or on a production root (#1440 R1). The manifest pins only the first team's profile."""
    root, out = os.path.realpath(sandbox_root(m)), []
    prod = [v for v in guard.target(m["production"]["path"])["roots"].values() if "<" not in v]
    for t in teams_of(m):
        out += ["team %s: %s changed since setup" % (t["name"], p) for p, h in t.get("sha256", {}).items()
                if not os.path.isfile(p) or guard.sha256(p) != h]
        merged, _, problems, _ = guard.config.resolve_profile(t["project"], t.get("org_profile"))
        out += ["team %s: %s" % (t["name"], e) for e in problems]
        for key, path in ({} if problems else merged["paths"]).items():
            path = os.path.realpath(path)
            if key in guard.ROOTS and (not path.startswith(root + os.sep) or any(guard.nested(path, q) for q in prod)):
                out.append("team %s: paths.%s %s is outside the sandbox or on a production root" % (
                    t["name"], key, path))
    return out


def retained(m):
    """Every team's repo or worktree with uncommitted changes or commits not on a remote, on any local branch."""
    out, paths = [], []
    for t in teams_of(m):
        wt = t["worktree_root"]
        paths += [t["repo"]] + sorted(os.path.join(wt, d) for d in os.listdir(wt))
    for path in paths:
        if not os.path.exists(os.path.join(path, ".git")):
            continue
        dirty = git("status", "--porcelain", cwd=path).splitlines()
        unpushed = git("log", "--format=%H %s", "HEAD", "--branches", "--not", "--remotes",
                       cwd=path).splitlines()
        if dirty or unpushed:
            out.append({"path": path, "dirty": dirty, "unpushed": unpushed})
    return out


def teardown(a):
    m = json.loads(Path(a.manifest).read_text())
    problems = guard.refusals(m) or team_refusals(m)
    if problems:
        return problems
    session, state = m["session"], m["roots"]["state_dir"]
    sock = tmux_socket(state)
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE") and not k.startswith("CREW_")}
    env.update(TMUX_TMPDIR=os.path.join(state, "tmux"), PATH=os.path.join(state, "bin") + os.pathsep + env["PATH"],
               MDSTACK_INTERNAL="1")  # mdstack down --project, as a crew window passes it (#1965)
    stopped = []
    for t in teams_of(m) if shutil.which("tmux") else []:
        # mdstack down --preserve stops the team's watcher and pane processes and keeps every run's work (#1440)
        argv = [sys.executable, os.path.join(m["source"]["path"], "cli", "mdstack"), "down", "--preserve",
                "--project", t["project"]] + (["--org-profile", t["org_profile"]] if t.get("org_profile") else [])
        down = subprocess.run(argv, capture_output=True, text=True, env=dict(env, CREW_PROJECT=t["project"]))
        subprocess.run(["tmux", "-S", sock, "kill-session", "-t", "=" + t["session"]], capture_output=True, env=env)
        gone = subprocess.run(["tmux", "-S", sock, "has-session", "-t", "=" + t["session"]], capture_output=True,
                              env=env).returncode != 0
        stopped.append({"team": t["name"], "session": t["session"], "stopped": gone,
                        "down": (down.stdout.strip().splitlines() or ["exit %d" % down.returncode])[-1]})
    killed = bool(stopped) and all(s["stopped"] for s in stopped)
    keep = retained(m)
    sentinel = guard.main(["sentinel", a.manifest]) == 0
    record = {"run_id": m["run_id"], "session": session, "session_killed": killed, "teams": stopped,
              "retained": keep, "sentinel_unchanged": sentinel}
    Path(m["roots"]["state_dir"], "cleanup.json").write_text(json.dumps(record, indent=2) + "\n")
    print("retained: %d worktree(s)%s" % (len(keep), "".join("\n  " + r["path"] for r in keep)))
    root = sandbox_root(m)
    if a.remove and not keep and sentinel and os.path.isfile(os.path.join(root, "state", "sandbox.json")):
        shutil.rmtree(root)
        print("removed: %s" % root)
    elif a.remove:
        print("kept: %s (retained work, changed sentinel or no sandbox record)" % root)
    return 0 if sentinel else 1


def plan_forge(a):
    owner, name = a.repo.split("/", 1)
    if a.repo == guard.target(a.production)["repo"]:
        return ["repo: %s is the production repo" % a.repo]
    ops = [["gh", "repo", "create", a.repo, "--private"]]
    ops += [["gh", "label", "create", n, "-R", a.repo, "--color", c, "--description", d]
            for n, c, d in crew_repo.LABELS]
    ops += [["gh", "label", "create", n, "-R", a.repo] for n in EXTRA_LABELS]
    ops += [["gh", "api", "-X", "PUT", "repos/%s/collaborators/<%s-identity>" % (a.repo, r)] for r in IDENTITIES]
    ops += [["git", "push", "<sandbox-clone>", "HEAD:main"],  # with .github/workflows/ci.yml copied from the source
            ["gh", "issue", "create", "-R", a.repo, "--title", "M25 campaign control", "--label", "integration:run"]]
    for op in ops:
        print("plan: " + shlex.join(op))
    print("level b: blocked, owner account access (nothing was run; profile repo = %s/%s)" % (owner, name))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    for flag in ("root", "run-id", "production", "source", "release", "sentinel"):
        s.add_argument("--" + flag, required=True)
    s.add_argument("--scenario", action="append", default=[])
    s.add_argument("--teams", type=int, choices=(1, 2), default=1, help="2: A28's second team (#1440)")
    s.add_argument("--engine", help="ENGINE/MODEL for both teams' roles, unstubbed (needs --teams 2)")
    t = sub.add_parser("teardown")
    t.add_argument("manifest")
    t.add_argument("--remove", action="store_true")
    p = sub.add_parser("plan-forge")
    p.add_argument("--repo", required=True)
    p.add_argument("--production", required=True)
    args = ap.parse_args(argv)
    result = {"setup": setup, "teardown": teardown, "plan-forge": plan_forge}[args.cmd](args)
    if isinstance(result, list):
        for problem in result:
            print("refused: " + problem)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
