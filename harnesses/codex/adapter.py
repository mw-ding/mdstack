"""Codex harness adapter (docs/runtimes/harness-adapters.md#codex-codex)."""
import datetime
import glob
import json
import os
import re
import shlex
import subprocess
import tomllib

EXECUTABLE = "codex"
TITLE = "Codex"
ENGINE_RANK, LAUNCH_RANK = 1, 1
LOGIN_STATUS = ["login", "status"]
PERMISSION = {"bypass": ["--dangerously-bypass-approvals-and-sandbox"],
              "auto": ["-s", "workspace-write", "-a", "on-request", "-c", "sandbox_workspace_write.network_access=true"],
              "safe": ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]}
# Modes whose OS write sandbox confines a builder run (#1252); a confined launch also drops /tmp and $TMPDIR from the
# writable roots, so they are exactly the worktree, its own git dir and the state dir.
CONFINES = ("auto", "safe")
CONFINED = ["-c", "sandbox_workspace_write.exclude_slash_tmp=true", "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true"]
SANDBOX_PROBE = ["sandbox", "--", "true"]  # a no-op under its OS sandbox: fails where it cannot apply one (#1252)
RESUME = ["resume"]
# Blocking prompts (#289): approval (command, edits), folder trust (1. Trust and continue) and host hooks review.
PERMISSION_PROMPTS = [(r"Would you like to .+\?", r"Press enter to confirm or esc to cancel")]
PROMPTS = PERMISSION_PROMPTS + [
           (r"Trust this folder\?", r"enter continue · esc "),
           (r"(?i:Hooks need review)$", r"enter confirm · esc skip$")]
FATAL = r'■\s(?=.*"type": ?"error")(?=.*"status": ?[45]\d\d\b)'  # ■ {"type":"error","status":400,...}
# Its own error banner only, a line opening with ■: never tool output, file names or quoted text (#1366).
TRANSIENT = re.compile(r'^■\s.*(?:"status": ?(?:429|5\d\d)\b|\b(?:429|5\d\d)\b.*(?:Too Many Requests|Internal Server '
                       r"Error|Bad Gateway|Unavailable|Gateway Timeout|retry)|rate.?limit)", re.I)  # ■ … last status: 429 …
QUOTA = re.compile(r"^■\s+You[’']ve hit your usage limit\b")  # ■ You've hit your usage limit. … try again in 2 days (#631)
COMPOSER = "›"
BUSY = re.compile(r"esc to interrupt")  # a lowercased screen mid-turn


def common_dir(path):
    """The absolute git common dir of path, or None outside a git repository."""
    r = subprocess.run(["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    return None if r.returncode else r.stdout.strip()


def trust(path):
    """Codex `-c` pre-trust for path and, in a git repo, its repo root: a whole projects table for this process, since
    the projects."<dir>".trust_level key form did not stop the trust dialog (#262); a linked worktree's trust is its
    repo root's (#288). An mdstack up project dir need not be a git repo."""
    dirs = [os.path.realpath(path)]
    if (common := common_dir(path)) is not None:
        dirs.append(os.path.dirname(common))
    return "projects={%s}" % ",".join('"%s"={trust_level="trusted"}' % d for d in dict.fromkeys(dirs))


def role_argv(model, effort, wt, state, flags):
    """--add-dir state lets every pass write $CREW_STATUS and verdicts/ (#234 F15); a linked worktree's refs and objects
    live in the common dir (#384)."""
    add_dirs = [state]
    if (common := common_dir(wt)) is not None:
        add_dirs.append(os.path.realpath(common))
    return ["codex", "-m", model, "-c", "model_reasoning_effort=" + effort,
            "-c", trust(wt), *flags, *[a for d in add_dirs for a in ("--add-dir", d)]]


def coordinator_argv(project_dir, state, flags):
    """No model or effort flags; the folder-trust dialog is avoided by the projects table."""
    return ["codex", "-c", trust(project_dir)]


def host_checks():
    """Check stored trust for host hooks.json and inline config.toml hooks without hashing or writing config.
    Edited hooks with stale hashes, plugin hooks and project hooks remain the live dialog check's responsibility."""
    def read(path, reader):
        try:
            with open(path, "rb") as f:
                return reader(f)
        except FileNotFoundError:
            return {}

    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    path = os.path.join(home, "hooks.json")
    config_path = os.path.join(home, "config.toml")
    inline = read(config_path, tomllib.load).get("hooks", {})
    trusted = inline.get("state", {})
    sources = [(path, read(path, json.load).get("hooks", {})), (config_path, inline)]
    keys = ["%s:%s:%d:%d" % (path, re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower(), i, j)
            for path, hooks in sources for event, groups in hooks.items() if event != "state"
            for i, group in enumerate(groups) for j, _ in enumerate(group.get("hooks", []))]
    bad = [k for k in keys if not trusted.get(k, {}).get("trusted_hash")]
    if bad:
        paths = ", ".join(dict.fromkeys(k.rsplit(":", 3)[0] for k in bad))
        return [("human", "codex hooks", "%d untrusted in %s" % (len(bad), paths), "before mdstack up, run codex once on "
                 "the host and trust every hook under Review hooks (answering a crew window does not persist)")]
    return [("ok", "codex hooks", "%d trusted" % len(keys), "")]


def install_launch(project, pointer, notes=()):
    """The printed Codex launch line: the coordinator brief pointer, then each pack launch note in order."""
    prompt = pointer + "".join(" Then read %s and follow it." % note for note in notes)
    return shlex.join(["codex", "-c", trust(str(project.parent)), prompt])


def usage(directory, start):
    """Token totals since start (epoch seconds) from the Codex session logs whose cwd is directory: {input, cached,
    output, model}, or None with no token count. Each log's cumulative total_token_usage at its end, less its last total
    before start; Codex input already includes cached input (#1557)."""
    base = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    want = os.path.realpath(directory)
    total = None
    for path in sorted(glob.glob(os.path.join(glob.escape(base), "sessions", "**", "*.jsonl"), recursive=True)):
        if os.path.getmtime(path) < start:
            continue
        cwd = model = None
        before, last = {}, None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    kind, p = rec["type"], rec["payload"]
                    if kind == "session_meta":
                        cwd = p["cwd"]
                    elif kind == "turn_context":
                        model = p.get("model") or model
                    elif kind == "event_msg" and p["type"] == "token_count" and p["info"]:
                        counts = p["info"]["total_token_usage"]
                        when = datetime.datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp()
                        before, last = (counts, last) if when < start else (before, counts)
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
        if cwd is None or os.path.realpath(cwd) != want or last is None:
            continue
        total = total or {"input": 0, "cached": 0, "output": 0, "model": None}
        for key, field in (("input", "input_tokens"), ("cached", "cached_input_tokens"), ("output", "output_tokens")):
            total[key] += (last.get(field) or 0) - (before.get(field) or 0)
        total["model"] = model or total["model"]
    return total
