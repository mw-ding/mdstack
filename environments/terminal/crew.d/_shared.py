"""Shared helpers for the crew commands in this directory (docs/runtimes/tmux.md). Python 3.11+ stdlib only.

cli/mdstack is the entry point; it loads this module as `crew_shared`, which the commands import from.
Helpers: profile resolve (refusing a `<placeholder>` in a path key the command uses) and state paths, the harness
launch line and window variables (every window gets `CREW_BIN`, `CREW_PROJECT` and the pack's `CREW_SANDBOX_ENV`
variable), run removal with the unlanded-work check, the pane stop (SIGTERM then SIGKILL the process group),
liveness probe and dialog check, queue lock and the command loader. A writing command names its resolved config
on stderr (#1324)."""
import argparse
import contextlib
import fcntl
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HERE = os.path.join(ROOT, "scripts")  # the repo's own scripts (release, checks, evidence)


def load(name, file):
    """A module by its path from the repo root."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


crew_render = load("crew_render", "core/crew-render.py")
harnesses = crew_render.crew_config.harnesses  # harnesses/<engine>/adapter.py (harness-adapters.md); one instance, so
# the adapters a pack.toml pack adds at resolve (docs/packs.md#pack-plug-ins) are the ones crew spawns
sessions = load("crew_session", "environments/terminal/crew-session.py")  # sessions/<backend>/adapter.py
copy_claim = load("crew_copy_claim", "environments/terminal/copy-claim.py")  # host-wide working-copy claims (#391)


class SessionBackend:
    """The profile's session backend adapter; profile() sets name from runtime.options.session_backend."""
    def __init__(self):
        self.backends = sessions.ADAPTERS
        self.name = "tmux"

    def __getattr__(self, key):
        return getattr(self.backends[self.name], key)


tmux = SessionBackend()
proc = load("crew_proc", "environments/terminal/crew-proc.py")  # OS process helpers every session backend shares


remote_run = load("crew_remote_run", "environments/terminal/crew.d/_remote.py")  # runs on a role host (#345)
ownership_module = load("crew_ownership", "environments/terminal/crew.d/_ownership.py")
ownership, require_ownership = ownership_module.ownership, ownership_module.require_ownership
team_module = load("crew_team", "environments/terminal/crew.d/_team.py")  # team root, leads, allocation (#1858)
lead_state = team_module.lead_state


POINTER = "Read your brief at $CREW_BRIEF and follow it."
# The token is derived inside the window's shell: never in argv, -e or a file (tmux.md Q5).
LAUNCH = 'export GH_TOKEN="$(gh auth token --user "$CREW_IDENTITY")"; exec %s "%s"'
ENGINE_CMD = harnesses.ENGINE_CMD
CREW_BIN = os.path.join(ROOT, "cli", "mdstack")  # this checkout's CLI, for briefs to call as $CREW_BIN (#139 F1)
ROLES = crew_render.crew_config.ROLE_REGISTRY
SPAWN_ROLES = {r: v for r, v in ROLES.items() if v["engine_source"] == "tier"}
BANDS = {r: tuple(v["window_band"]) for r, v in SPAWN_ROLES.items()}
PASSES = {r: v["passes"] for r, v in SPAWN_ROLES.items()}
NAMES = {r: v["display_name"].lower() for r, v in SPAWN_ROLES.items()}
CAPS = {r: v["cap_key"] for r, v in SPAWN_ROLES.items() if "cap_key" in v}


def coordinator_window(values):
    """Window 0's name: the coordinator's name, then `-<identities.team>` when the team is set (#1329)."""
    name = values.get("identities.coordinator.name", "ash").lower()
    return name + "-" + values["identities.team"] if values.get("identities.team") else name


def coordinator_launch(values, cmd, resume):
    """Window 0's launch line: it derives GH_TOKEN only when a backend is bound to GitHub (#1957); ask takes no pointer
    (the harness picker would read it as a search term)."""
    github = any(v == "github" for k, v in values.items() if re.fullmatch(r"backends\.[\w-]+\.name", k))
    line = LAUNCH if github else LAUNCH.partition("; ")[2]
    return line.removesuffix(' "%s"') % cmd if resume == "ask" else line % (cmd, POINTER)


def coordinator_dir(values, project):
    """Window 0's working directory: runtime.options.launch.cwd, relative to the profile's directory, else that
    directory (#1957)."""
    base = os.path.dirname(os.path.abspath(project))
    return os.path.abspath(os.path.join(base, os.path.expanduser(values.get("runtime.options.launch.cwd") or ".")))


def window_alias(values, window):
    """A window name with the coordinator's bare name (`ash`) resolved to window 0's name."""
    return coordinator_window(values) if window == values.get("identities.coordinator.name", "ash").lower() else window


def brief_src(state, role):
    """Rendered role brief: briefs/<role>.md from core/, else the runtime binding's runtime/<role>.md (#137)."""
    core = os.path.join(state, "render", "briefs", role + ".md")
    return core if os.path.exists(core) else os.path.join(state, "render", "runtime", role + ".md")


def role_notes(values, state, role):
    """Read standing notes at launch, in profile order; relative paths use the project's state directory."""
    sections = []
    for path in values.get("runtime.options.notes." + role, []):
        try:
            with open(os.path.join(state, path), encoding="utf-8") as f:
                sections.append("\n## Runtime note: %s\n\n%s" % (path, f.read()))
        except (OSError, UnicodeError) as e:
            raise RuntimeError("crew: cannot read runtime.options.notes.%s file %s: %s" % (role, path, e)) from e
    return "".join(sections)


def placeholder_paths(args, values, keys):
    """Path keys this command uses whose resolved value still holds a <placeholder>, whichever layer set it (#265):
    an omitted key falls back to the shipped default. A key the command does not use is not checked."""
    return ["%s:paths.%s: still the placeholder %s; set it in the project or org profile, or use the project file "
            "given to mdstack up ($CREW_PROJECT)" % (args.project, k, values.get("paths." + k)) for k in keys
            if re.search(r"<[^<>]+>", str(values.get("paths." + k, "")))]


def profile(args, *keys, runtimes=("tmux",)):
    """Resolved profile, session name and state dir; exit 1 on a resolve problem, a runtime outside runtimes, or a
    placeholder in paths.state_dir or another path key the command uses (keys). A non-tmux runtime binds no session
    backend and its session name is None (#1122)."""
    values, problems = crew_render.resolve(args.project, args.org_profile)
    if values and values["runtime.name"] not in runtimes:
        problems = ["%s:runtime.name: runtime.name is %s, not %s" % (args.project, values["runtime.name"],
                                                                  " or ".join(runtimes))]
    elif values:  # an unrendered copy (a worktree's config.toml) would put locks and state in the wrong place (#139 F5)
        problems = placeholder_paths(args, values, ("state_dir",) + keys)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    owner, repo = values["repo.owner"], values["repo.name"]
    state = os.path.join(os.path.abspath(values["paths.state_dir"]), "%s__%s" % (owner, repo))
    if values["runtime.name"] != "tmux":
        return values, None, state
    tmux.name = values.get("runtime.options.session_backend", "tmux")
    session = values.get("runtime.options.session") or "crew-%s-%s" % (owner, repo)
    tmux.bind(session, values.get("runtime.options.tmux_server") or "default")
    return values, session, state


def work_context(project, values):
    """The routing context {team, project, repo} of project's resolved values, for a work envelope (team §9.3);
    computed on demand so the resolved values stay exactly the profile."""
    return crew_render.crew_config.context(project, values.get("team.name"), values["repo.owner"], values["repo.name"])


def repo_id(values):
    """The canonical repo (owner/name, lower case) of resolved values, as a work envelope names it."""
    return ("%s/%s" % (values["repo.owner"], values["repo.name"])).lower()


def team_name(values, name):
    """A run's window name: in a team, with its repo tag, so same-number work in two repos never shares a name in the
    team's one session (#1858); unchanged for a one-repo profile."""
    return "%s-%s" % (name, team_module.tag(repo_id(values))) if values.get("team.name") else name


def post_title(values, role, pass_, *details):
    """A role post's title line (docs/protocol.md §4, #1946): profile emoji (none with report.emoji = false), name,
    pass label and details. Display only; readers parse the crew:v1 marker."""
    identity = crew_render.ROLES[role]
    key = identity["identity_key"]
    emoji = values.get(key + ".emoji", identity["identity_defaults"]["emoji"])
    return crew_render.post_title.title(values.get(key + ".name", identity["identity_defaults"]["name"]), pass_,
                                        *details, emoji="" if values.get("report.emoji") is False else emoji)


def tracker_labels(values):
    """Canonical state tag -> this project's tracker label (repo.labels), the tag itself when unmapped."""
    return {tag: values.get("repo.labels." + tag, tag) for tag in crew_render.crew_config.STATE_TAGS}


def canonical_labels(values, record):
    """record's tracker labels renamed back to canonical state tags, in place. A label spelled like a tag this project
    renames is not that tag and is dropped."""
    labels = tracker_labels(values)
    back = dict({tag: None for tag, label in labels.items() if label != tag}, **{v: k for k, v in labels.items()})
    if isinstance(record, dict) and isinstance(record.get("labels"), list):
        record["labels"] = [dict(label, name=back.get(label["name"], label["name"])) for label in record["labels"]
                            if back.get(label["name"], label["name"]) is not None]
    return record


def checkout(values, project):
    """The git checkout role worktrees and trains come from: paths.checkout (relative to the profile's directory),
    else the profile's directory, so a non-git runtime home can name a separate checkout (#1178)."""
    base = os.path.dirname(os.path.abspath(project))
    path = values.get("paths.checkout")
    return os.path.abspath(os.path.join(base, os.path.expanduser(path))) if path else base


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("crew: git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout.strip()


def fetch(repo, ref):
    """Fresh base: always the just-fetched remote ref, never a possibly stale local one. Each call fetches into its
    own private ref, writing neither the shared FETCH_HEAD nor a configured remote-tracking ref, so concurrent fetches
    in one checkout never read or race on each other's result (#1367, #1584)."""
    private = "refs/crew/fetch/%d-%s" % (os.getpid(), os.urandom(8).hex())
    try:
        git(repo, "fetch", "-q", "--no-tags", "--no-write-fetch-head", "--refmap=", "origin", "+%s:%s" % (ref, private))
        return git(repo, "rev-parse", "--verify", private + "^{commit}")
    finally:
        subprocess.run(["git", "-C", repo, "update-ref", "-d", private], capture_output=True)


def public_repo(values):
    """Contributor-tier policy (roles.md Hard rules): the repository is verified public through the GitHub API."""
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    result = subprocess.run(["gh", "api", "repos/" + repo], capture_output=True, text=True)
    try:
        return result.returncode == 0 and json.loads(result.stdout).get("private") is False
    except (ValueError, AttributeError):
        return False


def launch_policy(engine, mode, values):
    """The adapter and its runtime.options.permission_mode flags (tmux.md mdstack spawn), once the adapter supports the
    mode and, for a contributor-tier harness, the repository is verified public; RuntimeError otherwise."""
    adapter = harnesses.ADAPTERS[engine]
    if mode not in adapter.PERMISSION:
        raise RuntimeError(getattr(adapter, "PERMISSION_REFUSAL", "crew: %s does not support permission_mode=%s" % (
            adapter.TITLE, mode)))
    if getattr(adapter, "CONTRIBUTOR_TIER", False) and not public_repo(values):
        raise RuntimeError("crew: %s requires a verified public repository (contributor-tier rule)" % adapter.TITLE)
    return adapter, adapter.PERMISSION[mode]


def harness(engine, model, effort, wt, state, mode, values, local=True, confined=False):
    """Role window argv from the engine's adapter, after the core's launch policy. A local launch also asks the
    adapter's launch_refusal for this host's effective uid; a remote one leaves that to the execution host (#738).
    A confined builder run adds the adapter's CONFINED flags (#1252)."""
    adapter, flags = launch_policy(engine, mode, values)
    refusal = local and getattr(adapter, "launch_refusal", lambda *_: None)(mode, os.geteuid())
    if refusal:
        raise RuntimeError(refusal)
    return adapter.role_argv(model, effort, wt, state, flags + (adapter.CONFINED if confined else []))


def coordinator_harness(engine, project_dir, state, mode, values, resume="fresh"):
    """Coordinator argv from the engine's adapter, after the core's launch policy; resume (launch.resume) appends the
    adapter's resume verb and, unless ask, the conversation id."""
    adapter, flags = launch_policy(engine, mode, values)
    argv = adapter.coordinator_argv(project_dir, state, flags)
    return argv if resume == "fresh" else argv + adapter.RESUME + ([] if resume == "ask" else [resume])


def unlanded(values, rec, wt):
    """Uncommitted or untracked paths, and commits not on the fetched default branch, run branch or PR head."""
    items = ["uncommitted: " + line for line in git(wt, "status", "--porcelain", "--untracked-files=all").split("\n")
             if line]
    landed = [fetch(wt, values["repo.default_branch"])]
    branch = subprocess.run(["git", "-C", wt, "symbolic-ref", "-q", "--short", "HEAD"], capture_output=True, text=True)
    refs = [branch.stdout.strip()] if branch.returncode == 0 else []
    refs += ["pull/%s/head" % n for n in re.findall(r"PR #(\d+)", rec.get("item", ""))]
    pr = rec.get("pr") or rec.get("args", {}).get("pr")
    if pr:
        refs.append("pull/%s/head" % pr)
    for ref in refs:
        try:
            landed.append(fetch(wt, ref))
        except RuntimeError:  # not on the remote: its commits count as unlanded
            pass
    log = git(wt, "log", "--format=%H %s", "HEAD", "--not", *landed)
    return items + ["commit: " + line for line in log.split("\n") if line]


def record_discard(values, rec, name, reason, items):
    """Post the owner's discard reason on the run's PR (narrative post) or issue; False if it was not posted."""
    pr, issue = re.search(r"PR #(\d+)", rec.get("item", "")), re.search(r"issue #(\d+)", rec.get("item", ""))
    body = "%s\n\nReason: %s\n\n%s" % (
        post_title(values, "coordinator", "kill", "discarded unlanded work in " + name), reason,
        "\n".join("- `%s`" % i for i in items))
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    cmd = (["gh", "pr", "review", pr.group(1), "--comment", "-R", repo] if pr else
           ["gh", "issue", "comment", issue.group(1), "-R", repo] if issue else None)
    return cmd is not None and subprocess.run(cmd + ["--body", body], capture_output=True).returncode == 0


def stop_pane(session, index, grace=2.0):
    """SIGTERM the pane's process group, SIGKILL what is left after grace seconds; return the pgid if it survives.

    kill-window alone sends SIGHUP, which Codex ignores (#139 F2). The caller's own group (mdstack down run from
    window 0) is left to kill-session."""
    try:
        pid = int((tmux.pane(session, index) or {})["pid"])
    except (KeyError, ValueError):
        return None
    return stop_pid(pid, grace)


def stop_pid(pid, grace=2.0):
    """stop_pane for a known pid: SIGTERM its process group and its descendants' groups, SIGKILL after grace seconds;
    return the pgid if it survives."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return None
    if pgid <= 1 or pgid == os.getpgrp():
        return None
    groups = {pgid}
    for child in proc.descendants(pid):
        with contextlib.suppress(ProcessLookupError):
            groups.add(os.getpgid(int(child)))
    groups -= {1, os.getpgrp()}
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for group in groups:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(group, sig)
        deadline = time.monotonic() + grace
        while groups and time.monotonic() < deadline:
            for group in list(groups):
                try:
                    os.killpg(group, 0)
                except ProcessLookupError:
                    groups.remove(group)
                except PermissionError:
                    pass
            if groups:
                time.sleep(0.05)
        if not groups:
            return None
    return min(groups)


def synthesizer_work(state, name, extra=""):
    inbox = os.path.join(state, "inbox", name + ".jsonl")
    lines = status_lines(state, name)
    if extra:
        lines.append(extra)
    acks = receipts(state, name)
    messages = []
    if os.path.exists(inbox):
        with open(inbox) as f:
            messages = [json.loads(line) for line in f if line.strip()]
    pending = []
    for msg in messages:
        ack = acks.get(msg["id"], -1)
        completed = any((line.startswith("done: ") and line.split()[1:] in
                         (msg["refs"][:2], msg["refs"][:1], msg["refs"][:2] + ["stale"])) or
                        (line.startswith("blocked: ") and line.split()[1:2] == msg["refs"][:1])
                        for line in (lines[ack + 1:] if ack >= 0 else [extra]))
        if (msg["kind"] == "land" and not completed) or (msg["kind"] != "land" and ack < 0):
            pending.append(msg)
    path = os.path.join(state, "runs", name + ".json")
    if os.path.exists(path):
        with open(path) as f:
            rec = json.load(f)
        rec["pending_lands"] = [m for m in pending if m["kind"] == "land"]
        temporary = path + ".tmp"
        with open(temporary, "w") as f:
            json.dump(rec, f, indent=2)
        os.replace(temporary, path)
    return pending


def open_trains(state):
    paths = []
    for path in sorted(glob.glob(os.path.join(state, "trains", "train-*.json"))):
        with open(path) as f:
            rec = json.load(f)
        if not rec.get("closed") and (len(rec.get("landed", [])) < len(rec["members"]) or
                                      rec.get("pending_record")):
            paths.append(path)
    for path in sorted(glob.glob(os.path.join(state, "trains", "delegated-*.json"))):  # a builder builds it (#1391)
        built = os.path.join(state, "trains", "train-" + path.rsplit("-", 1)[1])
        with open(path) as f:
            if not json.load(f).get("closed") and not os.path.exists(built):
                paths.append(path)
    return paths


def retain_synthesizer(state, name):
    pending = synthesizer_work(state, name)
    path = os.path.join(state, "inbox", "synthesizer-pending.jsonl")
    saved = []
    if os.path.exists(path):
        with open(path) as f:
            saved = [json.loads(line) for line in f if line.strip()]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for msg in {m["id"]: m for m in saved + pending}.values():
            f.write(json.dumps(msg) + "\n")


def kill_run(values, session, state, name, reason=None):
    """Stop the window, then remove only this run's worktree (build output inside it) and state files; a run on a
    role host is stopped and checked there, and an unreachable host keeps everything unless a discard reason is
    recorded: the owner's abandon then leaves a tombstone for the host's return and drops the records here (#347).

    Removal needs the window's processes gone and the work landed, or a discard reason recorded on the item;
    otherwise keep the worktree and state files and return the blocking items."""
    path = os.path.join(state, "runs", name + ".json")
    rec, top = {}, team_module.root(state)
    if os.path.exists(path):
        with open(path) as f:
            rec = json.load(f)
    for index, n in tmux.list_windows(session):
        if n == name and top and name not in dict(commands()["lead"].records(state)) and not own_pane(session, index, rec):
            print("crew: refusing to stop window %s: its pane is not this repo's run %s" % (name, rec.get("run_id")))
            return ["foreign: window %s" % name]
        if n == name:
            pgid = stop_pane(session, index)
            if pgid:
                print("crew: refusing to remove %s: process group %d survived SIGKILL" % (name, pgid))
                return ["alive: process group %d" % pgid]
            tmux.kill_window(session, index)
    if name in dict(commands()["lead"].records(state)):
        return []  # A lead's durable inbox survives stop and supervisor restart.
    if rec:
        status = os.path.join(state, "status", name + ".status")
        if os.path.exists(status):
            with open(status) as f:
                for line in f.read().splitlines():
                    remember_pr(rec, line)
    if rec.get("role") == "synthesizer":
        retain_synthesizer(state, name)
        commands()["land-lock"].cleanup(state)
    wt = rec.get("worktree")
    if remote_run.host_of(rec):  # the host stops the run and keeps or removes the worktree there
        reply = remote_run.kill(values, name, rec)
        if reply["result"] == "ok" and reply["unlanded"] and reason is not None and \
                record_discard(values, rec, name, reason, reply["unlanded"]):
            reply = remote_run.kill(values, name, rec, discard=True)
        items = reply["unlanded"] if reply["result"] == "ok" else ["%s: %s" % (reply["result"], reply.get(
            "reason") or reply.get("error"))]
        abandon = ["unreachable: %s; tombstoned, stopped when it returns, unlanded work kept" % rec["host"]]
        if reply["result"] == "unreachable" and reason is not None and record_discard(values, rec, name, reason, abandon):
            remote_run.tombstone(state, name, rec, reason)  # the owner's abandon (#347): the host stops it on return
            print("crew: %s on %s is unreachable: tombstone written; its records and claim are dropped here" % (
                name, rec["host"]))
            items = []
        if items:
            print("crew: refusing to remove %s on %s: %s:\n  %s" % (
                wt, rec["host"], "the host call failed" if reply["result"] != "ok" else "unlanded work in %s%s" % (
                    name, "" if reason is None else " (discard reason not recorded on the item)"), "\n  ".join(items)))
            return items
    elif wt and own_worktree(values, wt, top):
        try:
            items = unlanded(values, rec, wt) if os.path.isdir(wt) else []
        except RuntimeError as e:
            items = ["unchecked: %s" % e]
        if items and (reason is None or not record_discard(values, rec, name, reason, items)):
            print("crew: refusing to remove %s: unlanded work in %s%s:\n  %s" % (
                wt, name, "" if reason is None else " (discard reason not recorded on the item)", "\n  ".join(items)))
            return items
        subprocess.run(["git", "-C", rec["repo"], "worktree", "remove", "--force", wt], capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "-C", rec["repo"], "worktree", "prune"], capture_output=True)
    if top and rec.get("run_id"):  # its team slot and run ID, only when the allocation is this repo's (#1858)
        team_module.release(top, rec["run_id"], repo_id(values))
    if rec.get("copy_claim"):  # the run is gone: its holder releases the working-copy claim (#391)
        copy_claim.release(rec["copy_claim"], state, name)
    scratch = [p for p in glob.glob(os.path.join(state, "runs", "**", glob.escape(name) + "[.-]*"), recursive=True)
               if os.path.isfile(p)]  # record, brief, PR body, also under subdirectories (#139 F7, N6)
    for p in scratch + [os.path.join(state, "inbox", name + ".jsonl"),
                        os.path.join(state, "status", name + ".status"), rec.get("claim")] + verdict_files(state, name, rec):
        if p and os.path.exists(p):
            os.remove(p)
    return []


def own_pane(session, index, rec):
    """In a team session a window name alone is not a run (#1858): the window must be at the run's recorded slot and,
    once the run recorded one, show its pane with its live process (pid and start time, as probe reads it), so a
    successor in the same pane survives. A dead pane matches by handle where the backend drops its pid, else by pid."""
    if not rec or rec.get("index") != index:
        return False
    if rec.get("pane_id") is None:
        return True
    p = tmux.pane(session, index) or {}
    if p.get("id") != rec["pane_id"]:
        return False
    if p.get("dead") == "1":
        return "dead-keeps-pid" not in tmux.CAPABILITIES or p.get("pid") == rec.get("pane_pid")
    return p.get("pid") == rec.get("pane_pid") and proc.proc_start(p["pid"]) == rec.get("pane_start")


def own_worktree(values, wt, top):
    """Whether kill may remove wt: a direct child of paths.worktree_root, or in a team (top) this repo's
    <worktree-root>/<repo-tag>/<run-id>/ (team §9.3); another repo's tree never qualifies."""
    real, base = os.path.realpath(wt), os.path.realpath(values["paths.worktree_root"])
    return os.path.dirname(real) == base or bool(top) and os.path.dirname(real) == os.path.join(
        base, team_module.tag(repo_id(values)))


def verdict_files(state, name, rec):
    """A reviewer run's disposable sections; keep the review file until head moves or the PR closes so a
    re-validation can reuse it. The coordinator removes the retained review files on those events."""
    own = rec.get("verdict")
    if not own:
        return []
    keep = rec["pass"] == "review"
    base = own[:-len("validate.md")]  # validate also writes the round's -verdict file (#139 N6)
    return ([] if keep else [own]) + ([base + "verdict.md"] if rec["pass"] == "validate" else [])


def sandbox_env(values):
    """NAME=VALUE from CREW_SANDBOX_ENV or the profile, propagated to every window and future launches."""
    setting = os.environ.get("CREW_SANDBOX_ENV", values.get("runtime.options.sandbox_env", ""))
    key, sep, value = setting.partition("=")
    return {"CREW_SANDBOX_ENV": setting, key: value} if key and sep else {}


def window_env(values, state, role, name, brief, project):
    """The role window's -e variables: names, paths and the login only, never a token (tmux.md Q5)."""
    return {"CREW_ROLE": role, "CREW_ID": name, "CREW_STATE": state, "CREW_BRIEF": brief, "CREW_BIN": CREW_BIN,
            "CREW_PROJECT": os.path.abspath(project),
            "CREW_STATUS": os.path.join(state, "status", name + ".status"),
            "CREW_INBOX": os.path.join(state, "inbox", name + ".jsonl"),
            "CREW_IDENTITY": values["identities.%s.gh_user" % role], **sandbox_env(values)}


def show_icon(values, session, index, role):
    """The role's configured emoji beside its tab, display-only (#1157): a variation selector (U+FE0F) is dropped and
    any other multi-codepoint emoji (a ZWJ sequence) shows the name only, as tmux would misalign the status bar."""
    emoji = values.get("identities.%s.emoji" % role, "").replace("\ufe0f", "")
    if len(emoji) == 1 and "icon" in tmux.CAPABILITIES:
        tmux.icon(session, index, emoji)


def foreground_matches(executables, names):
    """A harness executable among the foreground names, or a name its adapter's PROCESS pattern matches."""
    names = set(names)
    return bool(set(executables) & names) or any(
        getattr(harnesses.BY_EXECUTABLE.get(e), "PROCESS", None) and any(
            harnesses.BY_EXECUTABLE[e].PROCESS.fullmatch(n) for n in names) for e in executables)


def tty_foreground(executables, tty):
    """An adapter's own foreground signature on the tty (Cursor's bundled Node launcher)."""
    return any(hasattr(harnesses.BY_EXECUTABLE.get(e), "foreground_tty") and
               harnesses.BY_EXECUTABLE[e].foreground_tty(tty) for e in executables)


def wait_harness(session, index, name, expected, timeout):
    """Verify start: the expected harness must reach the foreground within timeout seconds, on harness_up's evidence:
    the pane command or a foreground process name of the pane's tty. Through a symlinked install the pane command is
    the resolved file's name (`claude` -> `2.1.314`, #286), so that name counts as the pane command too."""
    path = shutil.which(expected)
    names = {expected} | ({os.path.basename(os.path.realpath(path))} if path else set())
    deadline = time.monotonic() + timeout
    while not foreground_matches(names, [seen := tmux.pane_command(session, index)]):
        p = None if seen == "dead" else tmux.pane(session, index)
        if p and (foreground_matches([expected], tmux.foreground(p["tty"])) or tty_foreground([expected], p["tty"])):
            return
        if seen == "dead" or time.monotonic() > deadline:  # a dead pane never starts (#139 F20)
            raise RuntimeError("failed: %s: foreground is %r, not %s, after %ss; cleaned up" % (
                name, seen, expected, timeout))
        time.sleep(0.2)


def receipts(state, window):
    """The one receipt rule (#1850, D2.1); every ack consumer reads receipts here, never `ack:` lines itself.
    {message id: status line index} of the first `ack: <id>` line written after that message's latest `recorded` send
    in runs/<window>.delivery.jsonl: an ack before it (an earlier run's, or one already there) never counts, and a
    status file shorter than the record was rewritten and counts whole. A message with no record keeps the plain rule:
    its first matching line."""
    sent = {}
    with contextlib.suppress(OSError):
        with open(os.path.join(state, "runs", window + ".delivery.jsonl"), encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError, AttributeError, TypeError, KeyError):
                    e = json.loads(line)
                    if e.get("event") == "recorded":
                        sent[e["id"]] = int(e.get("status", 0))
    try:
        with open(os.path.join(state, "status", window + ".status"), "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return {}
    found, pos = {}, 0
    for i, raw in enumerate(io.BytesIO(data)):  # lines as status_lines splits them, so the indices agree
        words = raw.decode("utf-8", "replace").split()
        if words[:1] == ["ack:"] and len(words) > 1 and words[1] not in found:
            floor = sent.get(words[1], 0)
            if pos >= (floor if floor <= len(data) else 0):
                found[words[1]] = i
        pos += len(raw)
    return found


def status_lines(state, window):
    """The window's status lines, split on newlines only, as receipts indexes them."""
    try:
        with open(os.path.join(state, "status", window + ".status"), "rb") as f:
            return [raw.decode("utf-8", "replace").rstrip("\r\n") for raw in f]
    except FileNotFoundError:
        return []


def acked(state, window, msg_id):
    """Delivery proof: the window's own receipt of msg_id (receipts), nothing else."""
    return msg_id in receipts(state, window)


def wait_ack(state, window, msg_id, secs, refresh=None):
    """Wait up to secs for the ack; `refresh` (a remote run's pull into its mirror) runs before each check."""
    deadline = time.monotonic() + secs
    while True:
        if refresh:
            refresh()
        if acked(state, window, msg_id):
            break
        if time.monotonic() >= deadline:
            print("crew: no ack: %s from %s after %ss" % (msg_id, window, secs))
            return 3
        time.sleep(1 if refresh else 0.2)
    print("crew: acked %s by %s" % (msg_id, window))
    return 0


@contextlib.contextmanager
def queue_lock(state):
    """wake/queue.lock: held around every queue.jsonl append and mdstack drain's rename, so no append is lost."""
    os.makedirs(os.path.join(state, "wake"), exist_ok=True)
    with open(os.path.join(state, "wake", "queue.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def paused(state):
    """The project pause barrier `pause.json` (#1714): None when absent, else its record; an unreadable one is
    {"unreadable": why}, which counts as paused, so a damaged barrier never lets work start."""
    try:
        with open(os.path.join(state, "pause.json")) as f:
            rec = json.load(f)
        if not isinstance(rec, dict):
            raise ValueError("not a JSON object")
        return rec
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        return {"unreadable": str(e)}


def refuse_paused(state, what):
    """True, after one refusal line, while the project is paused or its pause state is unreadable."""
    rec = paused(state)
    if rec is None:
        return False
    since = "pause state unreadable: %s" % rec["unreadable"] if "unreadable" in rec else "since %s" % rec.get("at")
    print("crew: project paused (%s); refusing %s; mdstack resume ends it" % (since, what))
    return True


def pause_guarded(args):
    """Typed commands a project pause refuses: they dispatch, message, land or clean up work (#1714); `down
    --preserve` keeps every run's work and stays allowed."""
    cmd, action = args.cmd, getattr(args, "action", None)
    return cmd in ("spawn", "send", "dequeue", "kill", "reviewer-pool") or cmd == "train" and action != "check" or \
        cmd == "land-lock" and action == "acquire" or cmd == "gc" and getattr(args, "apply", False) or \
        cmd == "down" and not getattr(args, "preserve", False)


def unacked(state, name, lines, ignored_kinds=()):
    """Whether the inbox holds an unacked message outside the caller's ignored kinds."""
    inbox = os.path.join(state, "inbox", name + ".jsonl")
    acknowledgments = set(receipts(state, name))
    # A build nudge typed into a trust dialog is never acked; a done: naming its issue settles it (#1302).
    built = {line.split()[1] for line in lines if line.startswith("done: ") and len(line.split()) > 1}
    if os.path.exists(inbox):
        with open(inbox) as f:
            return any(m["kind"] not in ignored_kinds and m["id"] not in acknowledgments and
                       not (m["kind"] == "build" and m["refs"][:1] and m["refs"][0] in built)
                       for m in map(json.loads, filter(str.strip, f)))
    return False


def idle_builder(state, name):
    status = os.path.join(state, "status", name + ".status")
    if not os.path.exists(status):
        return None
    raw = status_lines(state, name)
    lines = [line for line in raw if not line.startswith("heartbeat:")]
    inbox = os.path.join(state, "inbox", name + ".jsonl")
    policy_ids = set()
    if os.path.exists(inbox):
        with open(inbox) as f:
            messages = [json.loads(line) for line in f if line.strip()]
        policy_ids = {m["id"] for m in messages if m["kind"] == "owner-policy"}
        policy_ids -= {m["id"] for m in messages if m["kind"] != "owner-policy"}
    acks = receipts(state, name)
    policy = {acks[i] for i in policy_ids if i in acks}  # owner-policy receipts are not work progress
    work_lines = [line for j, line in enumerate(raw) if j not in policy and not line.startswith("heartbeat:")]
    if not work_lines or not work_lines[-1].startswith("done:") or unacked(state, name, lines, ("owner-policy",)):
        return None
    rec = dict(runs(state)).get(name, {})
    if rec.get("pane_pid") and proc.live_child(rec["pane_pid"], rec["harness"]):
        return None
    return os.path.getmtime(status)


def pool_cap(values, role, state):
    full = values[CAPS[role]]
    present = min(full, values.get("runtime.options.present_" + role + "s", full))
    path = os.path.join(state, "away-control.json") if state else None
    if not path or not os.path.exists(path):
        return present
    with open(path) as f:
        issue = json.load(f)["issue"]
    result = subprocess.run(["gh", "api", "--paginate", "--slurp",
                             "repos/%s/%s/issues/%s/comments" %
                             (values["repo.owner"], values["repo.name"], issue)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("crew: cannot read away record; admission requires reconciliation")
    current, seen = None, set()
    # Away records signed before #781 carry the old default title, so they still count.
    sign = r"— .*\((?:%s|Coordinator)\) ·" % re.escape(values["identities.coordinator.title"])
    for comment in (c for page in json.loads(result.stdout) for c in page):
        if comment["user"]["login"] != values["identities.coordinator.gh_user"] or (
                comment.get("updated_at") != comment.get("created_at")):
            continue
        body = comment["body"] or ""
        markers = re.findall(r"<!-- crew:v1 ([^>]*?) -->", body)
        records = re.findall(r"```json\s*\n(.*?)\n```|`(\{[^`]+\})`", body, re.S)
        records = [a or b for a, b in records]
        if not records or not re.search(sign, body):
            continue
        for marker in markers:
            fields = dict(kv.split("=", 1) for kv in marker.split() if "=" in kv)
            source = fields.get("cmd-id")
            if fields.get("role") != "coordinator" or fields.get("pass") != "steer" or not source or source in seen:
                continue
            if fields.get("round") != "n/a" or fields.get("verdict") != "n/a" or not re.fullmatch(r"[0-9a-f]{40}", fields.get("sha", "")):
                continue
            if fields.get("cmd") not in ("away", "away-return"):
                continue
            record = json.loads(records[0])
            seen.add(source)
            if fields["cmd"] == "away" and record.get("state") == "away" and record.get("entry") == source:
                current = record
            elif fields["cmd"] == "away-return" and current and record.get("state") == "returned" and record.get("entry") == current["entry"]:
                current = None
    if not current:
        return present
    limit = present if current.get("quiet", False) else full
    bound = current.get("cap")
    if bound is None:
        return limit
    if type(bound) is not int or bound < 1:
        raise RuntimeError("crew: invalid away cap; admission requires reconciliation")
    others = sum(r["role"] != role for _, r in runs(state))
    return max(0, min(limit, bound - others))


def over_cap(values, role, windows, state=None):
    """Busy builders count toward their cap; every window still occupies a physical band slot. A run on a role host
    has no window here but counts toward the cap (#345)."""
    used = [name for name, i in windows.items() if BANDS[role][0] <= i <= BANDS[role][1]]
    busy = [name for name in used if role != "builder" or not state or idle_builder(state, name) is None]
    busy += [name for name, rec in runs(state) if rec["role"] == role and remote_run.host_of(rec)] if state else []
    return len(used) >= BANDS[role][1] - BANDS[role][0] + 1 or role in CAPS and len(busy) >= pool_cap(values, role, state)


def identity(session, index):
    """Run identity for the probe: pane handle, pane pid and that process's start time (tmux.md Q7)."""
    p = tmux.pane(session, index) or {}
    return {"pane_id": p.get("id"), "pane_pid": p.get("pid"), "pane_start": proc.proc_start(p["pid"]) if p else None}


def runs(state):
    """Run records only; scratch JSON and partial writes in runs/ are not runs."""
    d = os.path.join(state, "runs")
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if n.endswith(".json"):
            try:
                with open(os.path.join(d, n)) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and {"index", "role", "item", "pass", "repo", "worktree", "claim",
                                         "engine", "model", "effort", "harness"} <= rec.keys():
                yield n[:-5], rec


def remember_pr(rec, last):
    """Keep a builder's opened PR from its done line so squash landing survives branch deletion."""
    done = re.match(r"done: #([0-9]+) #([0-9]+) [0-9a-f]{40}(?:\s|$)", last)  # a trailing note is allowed (#695)
    if rec.get("role") == "builder" and done and rec.get("item", "").split(",")[0] == "issue #" + done[1]:
        rec["pr"] = int(done[2])


def heartbeat(state, name):
    """Last status line and the time of the run's last progress (status file, else run record); the time is None
    when the run record is reaped between listing and stat (#591)."""
    lead = dict(commands()["lead"].records(state)).get(name)
    status = os.path.join(lead_state(state) if lead else state, "status", name + ".status")
    if not os.path.exists(status) or not os.path.getsize(status):
        path = commands()["lead"].record_path(state, lead["role"].removesuffix("-lead")) if lead else \
            os.path.join(state, "runs", name + ".json")
        try:
            return "", os.path.getmtime(path)
        except FileNotFoundError:
            return "", None
    with open(status) as f:
        return f.read().splitlines()[-1], os.path.getmtime(status)


def probe(session, name, rec, windows):
    """C5 liveness from tmux, never from the agent: alive | dead | missing | ambiguous | quota (tmux.md Q7). quota: the
    run's own harness shows its adapter's usage-limit line, so it idles until the account resets (#631). A run on a
    role host has no pane here: ambiguous, which never restarts; its host answers remote_run.probe (#345)."""
    if remote_run.host_of(rec):
        return "ambiguous"
    if windows.get(name) != rec.get("index"):
        return "missing"
    p = tmux.pane(session, rec["index"])
    if p is None:
        return "ambiguous"
    if "dead-keeps-pid" not in tmux.CAPABILITIES and p["id"] == rec.get("pane_id") and p["dead"] == "1":
        return "dead"  # a backend that drops the pid after exit: the handle still identifies the object.
    if (p["id"], p["pid"]) != (rec.get("pane_id"), rec.get("pane_pid")):
        return "missing"  # same name, another run
    if p["dead"] == "1":
        return "dead"
    if proc.proc_start(p["pid"]) != rec.get("pane_start"):
        return "missing"
    if rec.get("harness") in QUOTA and quota_line(tmux.capture(session, rec["index"]), rec["harness"]):
        return "quota"
    return harness_up(session, rec["index"], p, [rec["harness"]])


# Blocking prompts (#289), from every adapter's PROMPTS: the heading on a line of its own and the prompt's footer as
# the last line on screen, so a prompt echo, diff or file quoting the same text, with the composer below it, never
# counts. FATAL: a harness's own fatal API error line, after which it idles at its prompt (#289).
PROMPTS = [(re.compile(head), re.compile(foot)) for a in harnesses.BY_EXECUTABLE.values()
           for head, foot in getattr(a, "PROMPTS", [])]
FATAL = [re.compile(a.FATAL) for a in harnesses.BY_EXECUTABLE.values() if getattr(a, "FATAL", None)]
# A composer's first row opens with an adapter's prompt glyph and a no-break space (mdstack send, #308).
GLYPHS = "".join(getattr(a, "COMPOSER", "") for a in harnesses.BY_EXECUTABLE.values())
COMPOSER = re.compile(r"[%s]\s?" % re.escape(GLYPHS))
# A lowercased screen of a harness mid-turn (mdstack upgrade waits for it).
BUSY = [a.BUSY for a in harnesses.BY_EXECUTABLE.values() if getattr(a, "BUSY", None)]


def dialog(session, index):
    """A blocking prompt or a fatal API error on the pane's screen (#139 F6, F7; #289)."""
    screen = tmux.capture(session, index)
    lines = [line.strip().lstrip(GLYPHS + "> ") for line in screen.splitlines() if line.strip()]
    return any(f.match(line) for f in FATAL for line in lines) or bool(lines) and any(
        foot.match(lines[-1]) and any(head.match(line) for line in lines) for head, foot in PROMPTS)


# Gateway errors (docs/scheduling.md#inputs): HTTP 429 or 5xx and rate-limit text from crew scripts, and each harness
# adapter's declared transient-error text on its pane (harness-adapters.md); a harness with none declared adds nothing.
GATEWAY = re.compile(r"\bHTTP\s+(?:429|5\d\d)\b|rate.?limit", re.I)
TRANSIENT = {e: a.TRANSIENT for e, a in harnesses.BY_EXECUTABLE.items() if getattr(a, "TRANSIENT", None)}


QUOTA = {e: a.QUOTA for e, a in harnesses.BY_EXECUTABLE.items() if getattr(a, "QUOTA", None)}


def quota_line(screen, harness):
    """The harness's own usage-limit line on its screen (harness-adapters.md QUOTA), else None (#631)."""
    pattern = QUOTA.get(harness)
    return next((line.strip() for line in screen.splitlines() if pattern and pattern.search(line)), None)


def transient_lines(screen, harness):
    pattern = TRANSIENT.get(harness)
    return [line.strip() for line in screen.splitlines() if pattern and pattern.search(line)]


def gateway_error(state, source, text, now=None, once=False):
    """Append one error to schedule/errors.jsonl. With once (a pane scan), the same source and text within the last 10
    minutes (the snapshot's window) is the same error still on screen, not counted again. Returns whether it wrote."""
    now = now or time.time()
    path = os.path.join(state, "schedule", "errors.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 600))
        for line in f if once else ():
            e = json.loads(line) if line.strip() else {}
            if e.get("source") == source and e.get("text") == text and e.get("ts", "") >= since:
                return False
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "source": source,
                            "text": text}) + "\n")
    return True


def harness_up(session, index, p, executables):
    """alive with a harness in the foreground and no dialog on screen, else ambiguous."""
    if dialog(session, index):
        return "ambiguous"
    alive = foreground_matches(executables, {p["command"], *tmux.foreground(p["tty"])})
    return "alive" if alive or tty_foreground(executables, p["tty"]) else "ambiguous"


def finished(rec, last):
    """Terminal: failed: for any run; done: only for a role whose completion is done (a builder stays for fixes)."""
    return last.startswith("failed:") or last.startswith("done:") and ROLES.get(rec["role"], {}).get("completion") == "done"


DESCRIPTION = "tmux crew CLI (docs/runtimes/tmux.md). Python 3.11+ stdlib only."
_COMMANDS = {}


def commands():
    """The crew.d/<cmd>.py modules by command name, loaded once in sorted file order; _-prefixed files are not
    commands. Each module's register(subparsers) adds the subparser named after its file; run(args) runs it."""
    if not _COMMANDS:
        for path in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "[!_]*.py"))):
            name = os.path.basename(path)[:-3]
            spec = importlib.util.spec_from_file_location("crew_cmd_" + name.replace("-", "_"), path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _COMMANDS[name] = mod
    return _COMMANDS


# Commands that can write state, the install or the forge: each names the config it acts under on stderr (#1324).
WRITES = {"action", "bootstrap", "dequeue", "doctor", "down", "drain", "feedback", "grant", "handoff", "host", "kill", "land",
          "land-lock", "layout", "lead", "migrate", "notify", "poll", "restart", "reviewer-pool", "route", "runner",
          "schedule", "send", "spawn", "start", "train", "up", "upgrade", "watch"}


# The owner CLI without --project (#1965): an owner shell (no CREW_ROLE, not a child of an mdstack command) gets no
# --project; it uses the installed team, and --repo KEY picks one of its repos. True re-enables --project there.
OWNER_PROJECT = False
INTERNAL = "MDSTACK_INTERNAL"  # set by main() for its child processes (watcher, poll, bootstrap) and by the test runner
UNSET = object()  # an owner shell's --project default, so a given one is seen whatever its spelling
TEAM_SCOPED = ("up", "start")  # with no --repo, a team file runs `up --team`; attach (bare, coordinator) takes it too
USAGE_PROJECT = re.compile(r"\(--project \S+ \| (--team FILE)\)|\s?\[--project \S+\]\]?|\s?--project [A-Z]\S*")


def owner_shell():
    return not OWNER_PROJECT and not os.environ.get("CREW_ROLE") and not os.environ.get(INTERNAL)


def bootstrap_reexec(args):
    """A 7.x bootstrap's verified re-exec of `upgrade --project FILE`: it sets the bundle sha but not INTERNAL (#2024)."""
    return args.cmd == "upgrade" and bool(os.environ.get("CREW_BOOTSTRAP_BUNDLE_SHA256"))


def owner_options(parser, seen=None):
    """Hide every --project from help, default it to UNSET, and add the repo selector --repo KEY (--team-repo KEY where
    the command's own --repo means something else, as for content and feedback)."""
    seen = set() if seen is None else seen
    if id(parser) in seen:
        return
    seen.add(id(parser))
    if parser.description:
        parser.description = USAGE_PROJECT.sub(lambda m: "[%s]" % m.group(1) if m.group(1) else "", parser.description)
    for action in list(parser._actions):
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                owner_options(child, seen)
        elif "--project" in action.option_strings:
            action.help, action.default = argparse.SUPPRESS, UNSET
            names = ["--team-repo"] if "--repo" in parser._option_string_actions else ["--repo", "--team-repo"]
            parser.add_argument(*names, dest="owner_repo", metavar="KEY",
                                help="the installed team file's repo (its [repos.KEY] section)")
            parser.set_defaults(owner_repo_flag=names[0])


def owner_project(args):
    """The installed team for an owner shell: up and start (no ROLE) and a bare or coordinator attach take a team file
    whole, unless --repo names a repo; any other command takes FILE#<--repo>, the reference's own repo or the team's
    only repo; an explicit --team stays. Returns an exit code; 2 when the repo is unknown or ambiguous."""
    if getattr(args, "team", None):
        args.project = None
        return 0
    found = crew_render.crew_config.installed_config()
    file, ref_repo = crew_render.crew_config.split_ref(found)
    key = getattr(args, "owner_repo", None)
    try:
        keys = crew_render.crew_config.team_repos(file)
    except (OSError, ValueError):
        keys = None  # not readable here: the profile read reports it
    if key and key not in (keys or ()):
        print("mdstack: %s %s: %s has no such repo (repos: %s)" % (args.owner_repo_flag, key, file,
                                                                  ", ".join(keys or ()) or "none"),
              file=sys.stderr)
        return 2
    args.project = "%s#%s" % (file, key) if key else found
    if key or ref_repo or not keys:
        return 0
    if args.cmd in TEAM_SCOPED and not args.role:
        args.team, args.project, args.team_ref = file, None, "%s#%s" % (file, keys[0])
    elif args.cmd == "attach" and args.target in (None, "coordinator"):
        pass
    elif len(keys) == 1:
        args.project = "%s#%s" % (file, keys[0])
    else:
        print("mdstack: %s lists repos %s; name one with %s KEY" % (file, ", ".join(keys), args.owner_repo_flag),
              file=sys.stderr)
        return 2
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    version = os.path.join(ROOT, "VERSION")  # the release bundle's tag; a clone has none (#1317)
    ap.add_argument("--version", action="version",
                    version="mdstack " + (open(version).read().strip() if os.path.isfile(version) else "dev"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, mod in commands().items():
        mod.register(sub)
        # `crew <cmd> --help` prints the command module's docstring, its usage doc (#325)
        sub.choices[name].description = mod.__doc__
        sub.choices[name].formatter_class = argparse.RawDescriptionHelpFormatter
    owner = owner_shell()
    if owner:
        owner_options(ap)
    args = ap.parse_args(argv)
    if owner and getattr(args, "project", UNSET) is not UNSET and not bootstrap_reexec(args):
        print("mdstack: --project is disabled; mdstack uses the installed team (%s). Set MDSTACK_CONFIG to override."
              % os.path.abspath(crew_render.crew_config.installed_config()), file=sys.stderr)
        return 2
    os.environ[INTERNAL] = "1"  # the commands' own mdstack calls pass --project
    if owner and getattr(args, "project", None) is UNSET and (code := owner_project(args)):
        return code
    if getattr(args, "project", "") is None and not getattr(args, "team", None):
        args.project = crew_render.crew_config.default_config()  # the user-level config by default (#1316)
    if args.cmd in WRITES and (getattr(args, "project", None) or owner and getattr(args, "team", None)):
        print("mdstack: config " + os.path.abspath(args.project or args.team), file=sys.stderr)  # its file (#1324)
    guarded = args.cmd in ("spawn", "restart", "send", "train") or (
        args.cmd == "land-lock" and args.action == "acquire" or args.cmd == "kill" and args.discard)
    if guarded:
        values, _, _ = profile(args)
        action = "land" if args.cmd in ("train", "land-lock") else "start"
        if not require_ownership(values, action):
            return 1
    if pause_guarded(args) and getattr(args, "project", None) and refuse_paused(profile(args)[2], args.cmd):
        return 1
    return commands()[args.cmd].run(args)
