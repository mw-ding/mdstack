"""Claude Code harness adapter (docs/runtimes/harness-adapters.md#claude-code-claude-code)."""
import datetime
import glob
import json
import os
import re
import shlex

CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cli", "mdstack")
EXECUTABLE = "claude"
TITLE = "Claude Code"
ENGINE_RANK, LAUNCH_RANK = 0, 0
LOGIN_STATUS = ["auth", "status"]
# runtime.options.permission_mode (tmux.md mdstack spawn): bypass runs any command in the worktree without asking (#293).
PERMISSION = {"bypass": ["--permission-mode", "bypassPermissions",  # no warning screen, set per process only
                         "--settings", '{"skipDangerousModePermissionPrompt":true}'],
              "auto": ["--permission-mode", "auto"], "safe": ["--permission-mode", "acceptEdits"]}
ROOT_BYPASS = ("crew: Claude Code refuses permission_mode=bypass when running as root (uid 0) and exits before "
               "starting a session (#738); run the crew as a non-root user, or set "
               "runtime.options.permission_mode to auto or safe for Claude Code roles")
RESUME = ["--resume"]
# Blocking prompts (#289): permission (proceed, make this edit, create) and folder trust, old and current.
# Bypass does not suppress the built-in safety dialog, which uses the permission prompt (#1968).
PERMISSION_PROMPTS = [(r"Do you want to .+\?", r"Esc to cancel")]
PROMPTS = PERMISSION_PROMPTS + [
           (r"Do you trust the files in this folder\?$", r"Enter to confirm · Esc to cancel"),
           (r"Accessing workspace:$", r"Enter to confirm · Esc to cancel")]
FATAL = r'⎿\s+API Error: [45]\d\d\b.*"type": ?"error"'  # ⎿  API Error: 400 {"type":"error",...}
# Its own error line only, at the result gutter's indent: never tool output, file names or quoted text (#1366).
# ⎿  API Error (529 …) · Retrying, ⎿  API Error: Connection lost mid-response, and the gateway's capacity line (#1633).
TRANSIENT = re.compile(r"^ {0,2}(?:⎿\s+API Error\W{1,3}(?:(?:429|5\d\d)\b|Connection lost\b)"
                       r"|(?:⎿\s+)?429 .*\bcapacity\b.*\bexhausted\b)")
# Its own usage-limit line at the same gutter (#631): the account is out of quota, so a retry on this engine is futile.
QUOTA = re.compile(r"^ {0,2}⎿\s+(?:Claude (?:AI )?usage limit reached|You[’']ve hit your (?:\w+ )?limit|\d+-hour limit reached|"
                   r"Weekly limit reached)\b")
COMPOSER = "❯"
BUSY = re.compile(r"esc to interrupt|^[✽✻✶✢·*] .+… \([^\n]+\)", re.M)  # a lowercased screen mid-turn
INSTALL_ROLES = ("coordinator", "builder", "reviewer", "synthesizer")
INSTALL_TARGETS = [".claude/agents/crew-%s.md" % r for r in ("builder", "reviewer", "synthesizer")] + [
    ".claude/skills/crew-coordinator/SKILL.md", ".claude/settings.local.json"]


def role_argv(model, effort, wt, state, flags):
    """--add-dir state: every pass reads its brief and writes $CREW_STATUS, verdicts/ (#234 F15). Claude's --add-dir
    takes several values, so a flag must end it before the prompt."""
    directories, extra = [state], []
    if role_cwd(wt) != wt:
        directories.append(wt)
        extra = ["--append-system-prompt", "Your assigned working copy is %s. Run every shell command with an "
                 "explicit cd to that directory and use absolute paths for file tools. The startup directory is "
                 "only the stable folder-trust boundary; work only in your assigned copy." % wt]
    return ["claude", "--model", model, "--effort", effort, "--add-dir", *directories, *flags, *extra]


def role_cwd(wt):
    """Run copies launch from their stable parent; linked worktrees still launch in the worktree (#1792)."""
    return os.path.dirname(wt) if os.path.isdir(os.path.join(wt, ".git")) else wt


def builder_checks(values):
    """Read the stable run-copy root's trust without writing any user-level harness config."""
    root = os.path.realpath(values["paths.worktree_root"])
    d = trusted(root)
    if d is None:
        return [("human", "claude copy trust", "not accepted for " + root,
                 "before dispatch, run mkdir -p %s && cd %s && claude; pick Yes, I trust this folder, then /exit "
                 "(once per host; never a blind Enter)" % (shlex.quote(root), shlex.quote(root)))]
    return [("ok", "claude copy trust", d, "")]


def launch_refusal(mode, uid):
    """Why a role window cannot launch on a host whose effective uid is uid, or None: Claude Code exits at once on
    bypass as root, which would surface only as missing probes (#738)."""
    return ROOT_BYPASS if mode == "bypass" and uid == 0 else None


def coordinator_argv(project_dir, state, flags):
    """No model or effort flags; the folder-trust dialog is accepted once by the owner (tmux.md)."""
    return ["claude"]


def is_guard(hook, state):
    """Whether a Stop hook is a crew turn-end guard for this state, from any bundle, link or checkout path."""
    try:
        argv = shlex.split(hook.get("command") or "")
    except ValueError:
        return False
    return len(argv) == 5 and argv[0] == "python3" and os.path.basename(argv[1]) == "mdstack" and \
        argv[2:] == ["guard", "--state", state]


def stop_hook_settings(settings, state):
    """Add the turn-end guard to a settings object, preserving every other key. The command names the resolved
    bundle, so a run through the mdstack link matches; a guard for this state from another path is re-pointed
    (#1088)."""
    command = shlex.join(["python3", os.path.realpath(CLI), "guard", "--state", state])
    stop = settings.setdefault("hooks", {}).setdefault("Stop", [])
    placed = False
    for entry in list(stop):
        hooks = []
        for h in entry.get("hooks", []):
            if is_guard(h, state):
                if placed:
                    continue
                h, placed = dict(h, command=command), True
            hooks.append(h)
        if entry.get("hooks") and not hooks:
            stop.remove(entry)
        elif "hooks" in entry:
            entry["hooks"] = hooks
    if not placed:
        stop.append({"hooks": [{"type": "command", "command": command}]})
    return settings


def coordinator_setup(project_dir, state):
    """Add the turn-end guard to the project's local Claude settings, once, keeping every other key."""
    path = os.path.join(project_dir, ".claude", "settings.local.json")
    settings = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    settings = stop_hook_settings(settings, state)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")


def trusted(path):
    """The directory, path or a parent, whose folder-trust dialog was accepted, read from the Claude Code config; None
    when none was."""
    config = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~"), ".claude.json")
    try:
        with open(config, "rb") as f:
            projects = json.load(f).get("projects", {})
    except FileNotFoundError:
        projects = {}
    d = os.path.realpath(path)
    while not projects.get(d, {}).get("hasTrustDialogAccepted"):
        if d == os.path.dirname(d):
            return None
        d = os.path.dirname(d)
    return d


def coordinator_checks(values, project_dir):
    """A Claude Code coordinator opens at the folder-trust dialog until it is accepted once for the project directory
    or a parent (docs/runtimes/harness-adapters.md)."""
    d = trusted(project_dir)
    if d is None:
        window = values.get("identities.coordinator.name", "ash").lower()
        return [("human", "claude trust", "not accepted for " + project_dir, "after mdstack up, accept the folder-"
                 "trust dialog once with mdstack attach %s --rw (never a blind Enter: it picks No, exit)" % window)]
    return [("ok", "claude trust", d, "")]


def role_checks(values, checkout):
    """A Claude Code role window opens at the folder-trust dialog until it is accepted for the repository root its
    linked worktree comes from: the checkout, which a paths.checkout outside the project directory leaves uncovered by
    the coordinator's answer (#408)."""
    d = trusted(checkout)
    if d is None:
        return [("human", "claude role trust", "not accepted for " + checkout, "before dispatch, run claude once in %s "
                 "and pick Yes, I trust this folder, then /exit (never a blind Enter: it picks No, exit)" % checkout)]
    return [("ok", "claude role trust", d, "")]


def install_targets(project, state, pointer, check):
    """Agent and skill files with a one-line brief pointer, and the Stop hook in the local settings (bootstrap Q4)."""
    targets = {}
    for role in INSTALL_ROLES:
        if role == "coordinator":
            path = project.parent / ".claude/skills/crew-coordinator/SKILL.md"
        else:
            path = project.parent / (".claude/agents/crew-" + role + ".md")
        targets[path] = ('---\nname: crew-%s\ndescription: mdstack %s role\n---\n\n%s\n' %
                         (role, role, pointer(role)))
    path = project.parent / ".claude/settings.local.json"
    check(path)
    settings = json.loads(path.read_text()) if path.exists() else {}
    targets[path] = json.dumps(stop_hook_settings(settings, str(state)), indent=2) + "\n"
    return targets


def usage(directory, start):
    """Token totals since start (epoch seconds) from the Claude Code transcripts for directory, subagent logs included:
    {input, cached, output, model}, or None with no transcript entry. Input counts fresh, cache-write and cache-read
    tokens; cached is the cache reads. A streamed message logged on several lines counts once (#1557)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    folder = os.path.join(base, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(directory)))
    seen, total = set(), None
    for path in sorted(glob.glob(os.path.join(glob.escape(folder), "**", "*.jsonl"), recursive=True)):
        if os.path.getmtime(path) < start:
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    msg = rec["message"]
                    u = msg["usage"]
                    when = datetime.datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
                key = (msg.get("id"), rec.get("requestId")) if msg.get("id") else rec.get("uuid")
                if when < start or key in seen:
                    continue
                seen.add(key)
                total = total or {"input": 0, "cached": 0, "output": 0, "model": None}
                cached = u.get("cache_read_input_tokens") or 0
                total["input"] += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + cached
                total["cached"] += cached
                total["output"] += u.get("output_tokens") or 0
                if msg.get("model") and not msg["model"].startswith("<"):
                    total["model"] = msg["model"]
    return total
