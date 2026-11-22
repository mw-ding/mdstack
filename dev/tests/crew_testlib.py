"""Shared fixtures for the dev/tests/environments/test-crew-<cmd>.py tests: a fake `tmux` binary on PATH, a temp profile,
a temp git repo with a bare origin and PR refs, a fake `gh`, fake panes and a fake `ps` for liveness (stdlib
only). No tests here."""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")
ROOT_DIR = os.path.dirname(SCRIPTS)
CREW = os.path.join(ROOT_DIR, "cli", "mdstack")
INPUTS = os.path.join(TESTS, "fixtures", "render", "inputs")

# Fake tmux: sessions live in $FAKE_TMUX_STATE (JSON), every call is appended to $FAKE_TMUX_LOG.
FAKE_TMUX = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    if args[:1] in (["-L"], ["-S"]):  # the server (#818): logged apart, so call logs stay command-first
        with open(os.environ["FAKE_TMUX_LOG"] + ".sockets", "a") as f:
            f.write(args[1] + "\\n")
        args = args[2:]
    with open(os.environ["FAKE_TMUX_LOG"], "a") as f:
        f.write(json.dumps(args) + "\\n")
    path = os.environ["FAKE_TMUX_STATE"]
    state = json.load(open(path)) if os.path.exists(path) else {}
    cmd, target = args[0], args[args.index("-t") + 1].lstrip("=") if "-t" in args else None
    if cmd == "has-session":
        sys.exit(0 if target in state else 1)
    if cmd == "new-session":
        state[args[args.index("-s") + 1]] = {"0": args[args.index("-n") + 1]}
    elif cmd == "new-window":
        session, _, index = target.partition(":")
        state[session][index] = args[args.index("-n") + 1]
        launch = args[-1].split("exec ", 1)[1].split()[0]
        state.setdefault("_panes", {})[target] = os.environ.get("FAKE_TMUX_PANE", launch)
    elif cmd == "display-message":
        print(state.get("_panes", {}).get(target, ""))
    elif cmd == "capture-pane":
        sys.stdout.write(os.environ.get("FAKE_TMUX_SCREEN", ""))
    elif cmd == "list-windows":
        if target not in state:  # as tmux: no such session, nothing on stdout
            sys.exit(1)
        print("\\n".join("%s %s" % kv for kv in state.get(target, {}).items()))
    elif cmd == "set-option":
        state.setdefault("_opts", {}).setdefault(target.rstrip(":"), {})[args[-2]] = args[-1]
    elif cmd == "kill-window":
        session, _, index = target.partition(":")
        state[session].pop(index)
        # FAKE_TMUX_USER_CONF: a user config with renumber-windows on and base-index 1, unless the session overrides it.
        opts = dict({"renumber-windows": "on", "base-index": "1"} if os.environ.get("FAKE_TMUX_USER_CONF") else {},
                    **state.get("_opts", {}).get(session, {}))
        if opts.get("renumber-windows") == "on":
            names = [state[session][k] for k in sorted(state[session], key=int)]
            state[session] = {str(int(opts["base-index"]) + i): n for i, n in enumerate(names)}
    elif cmd == "kill-session":
        state.pop(target)
    # A read never writes back, and a write replaces the file whole: a detached poller (the land-lock holder) can
    # neither undo a test's edit with the state it read before it nor show a reader a truncated file (#2011).
    if cmd in ("new-session", "new-window", "set-option", "kill-window", "kill-session"):
        with open(path + ".%d" % os.getpid(), "w") as f:
            json.dump(state, f)
        os.replace(f.name, path)
    """)

# A tmux wrapper with a composer model in $FAKE_COMPOSER: `-l` text joins the draft's last line, C-u clears a line
# and then joins it to the one above (as in Codex and Claude Code), Enter takes the next of `enters` (the last one
# repeats): `submit` moves the draft into the transcript, `newline` adds a line. Every other call goes to the base fake.
FAKE_COMPOSER = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    full = sys.argv[1:]
    args = full[2:] if full[:1] in (["-L"], ["-S"]) else full  # the crew's server (#818) goes on to the base fake
    c = json.load(open(os.environ["FAKE_COMPOSER"]))
    def rows(draft):
        return ["› " + draft[0]] + ["  " + line for line in draft[1:]]
    if args[0] in ("capture-pane", "display-message") and (args[0] == "capture-pane" or "#{cursor_x}" in args[-1]):
        with open(os.environ["FAKE_TMUX_LOG"], "a") as f:
            f.write(json.dumps(args) + "\\n")
        screen = c["history"] + [""] + (rows(c["draft"]) if c["draft"] else ["› Ask Codex to do anything"])
        x = 2 + len(c["draft"][-1]) if c["draft"] else 2
        print("\\n".join([r.rstrip() for r in screen] + c.get("below", ["", "  ? for shortcuts"]))
              if args[0] == "capture-pane" else "%d %d" % (x, len(screen) - 1))
        sys.exit(0)
    if args[0] == "send-keys":
        draft = c["draft"]
        if "-l" in args:
            c["draft"] = draft[:-1] + [(draft[-1] if draft else "") + args[-1]]
        for key in args[args.index("-t") + 2:] if "-l" not in args else []:
            if key == "C-u" and c.get("clears", True) and draft:
                draft[-1:] = [""] if draft[-1] else []
            elif key == "Enter":
                if "below_on_enter" in c:  # a prompt the Enter brings up under the composer
                    c["below"] = c.pop("below_on_enter")
                mode = c["enters"].pop(0) if len(c["enters"]) > 1 else c["enters"][0]
                if mode == "submit" and draft:
                    c["history"], c["draft"] = c["history"] + rows(draft), []
                elif mode == "newline":
                    c["draft"] = (draft or [""]) + [""]
            draft = c["draft"]
        json.dump(c, open(os.environ["FAKE_COMPOSER"], "w"))
    os.execv(os.path.join(os.path.dirname(sys.argv[0]), "tmux-base"), ["tmux"] + full)
    """)

CONCERNS = ["change", "review", "tracker", "state-tags", "markers", "ci", "events", "owner-channel"]


def write_pack(root, pin="v2.1.0", mapping=None):
    """An external `example` pack with a render/ overlay (#580): manifest, an org profile picking it for every
    concern, its backend map (default: the GitHub map with `ex` as the CLI name) and a changed tmux solo.md.
    Returns the org profile path."""
    repo = os.path.dirname(SCRIPTS)
    os.makedirs(os.path.join(root, "render", "backends"), exist_ok=True)
    os.makedirs(os.path.join(root, "render", "runtimes", "tmux"), exist_ok=True)
    with open(os.path.join(repo, "connectors", "github", "manifest.toml")) as f:
        manifest = f.read().replace('name = "github"', 'name = "example"\nmdstack_version = "%s"' % pin)
    with open(os.path.join(repo, "templates", "backends", "github.toml")) as f:
        github = f.read()
    with open(os.path.join(repo, "templates", "runtimes", "tmux", "solo.md")) as f:
        solo = f.read()
    files = {"manifest.toml": manifest,
             "profile.toml": "".join('[backends.%s]\nname = "example"\n' % c for c in CONCERNS),
             "render/backends/example.toml": mapping or github.replace('cli-name = "gh"', 'cli-name = "ex"'),
             "render/runtimes/tmux/solo.md": solo + "\nPack rule.\n"}
    for rel, text in files.items():
        with open(os.path.join(root, rel), "w") as f:
            f.write(text)
    return os.path.join(root, "profile.toml")


def example_profile(directory, name="tmux.toml"):
    """A copy of profiles/<name> without its [paths] table, so renders and golden files stay machine-independent of
    the shipped ~/.mdstack default layout (#1316); returns its path."""
    with open(os.path.join(ROOT_DIR, "profiles", name), encoding="utf-8") as f:
        text = re.sub(r"(?ms)^\[paths\]\n.*?(?=^\[|\Z)", "", f.read())
    os.makedirs(os.path.join(directory, "profile"), exist_ok=True)  # beside, never inside, a render --out
    path = os.path.join(directory, "profile", name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def render_template(project, dst, inputs=os.path.join(ROOT_DIR, "templates")):
    """(text, problems) for one rendered file, dst as `briefs/builder.md` or `runtime/builder-b1.md`, through the
    production path (#1413): crew-render's render() expands includes and filters control, backend and strategy lines
    before it fills placeholders. Template tests use this, never Renderer.line on raw template text; token-level
    Renderer.line tests stay as unit coverage."""
    spec = importlib.util.spec_from_file_location("crew_render", os.path.join(ROOT_DIR, "core", "crew-render.py"))
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    args = argparse.Namespace(project=project, org_profile=None, inputs=inputs)
    _, rendered, problems = cr.render(args, None, normalize_paths=False)
    return rendered.get(dst), problems


PROFILE = textwrap.dedent("""\
    [repo]
    owner = "acme"
    name = "widgets"
    [runtime]
    name = "{runtime}"
    [identities]
    owners = ["acme-owner"]
    coordinator = {{ gh_user = "acme-bot", name = "Ash" }}
    builder = {{ gh_user = "acme-bot", name = "Ben" }}
    reviewer = {{ gh_user = "acme-reviewer", name = "Vera" }}
    synthesizer = {{ gh_user = "acme-bot", name = "Sam" }}
    [engines]
    coordinator = "{engine}"
    [paths]
    state_dir = "{state}"
    worktree_root = "{state}/wt"
    toolchain_bin = "/opt/node/bin"
    """)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "tmux")
        with open(fake, "w") as f:
            f.write(FAKE_TMUX)
        os.chmod(fake, 0o755)
        self.log = os.path.join(self.tmp, "tmux.log")
        self.state_file = os.path.join(self.tmp, "tmux.json")
        self.env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
                        FAKE_TMUX_LOG=self.log, FAKE_TMUX_STATE=self.state_file)
        for name in ("CREW_PROJECT", "MDSTACK_CONFIG", "CREW_ROOT"):  # a crew window's own config never leaks in (#1324)
            self.env.pop(name, None)
        self.env["MDSTACK_COPY_CLAIMS"] = os.path.join(self.tmp, "copy-claims")  # never the real host store (#391)
        self.env["CREW_WATCHER"] = "off"  # mdstack up/upgrade start no detached watcher unless a test asks (#1346)
        # Stub engine CLIs, last on PATH: spawn and lead start pick only an engine whose executable is installed
        # (#631), so the suite needs none installed; an installed real CLI, or a test's own in bin/, comes first.
        self.engines = os.path.join(self.tmp, "engines")
        os.makedirs(self.engines)
        for cli in ENGINE_STUBS:
            with open(os.path.join(self.engines, cli), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(os.path.join(self.engines, cli), 0o755)
        self.env["PATH"] += os.pathsep + self.engines
        self.project_dir = os.path.join(self.tmp, "project")
        os.makedirs(self.project_dir)
        self.state = os.path.join(self.tmp, "state", "acme__widgets")
        self.write_profile()
        with open(os.path.join(bindir, "gh"), "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, os, sys\n"
                    "args = sys.argv[1:]\n"
                    "solo = args[2] in os.environ.get('FAKE_SOLO_' + args[0].upper(), '').split(',')\n"
                    "print(json.dumps({'labels': [{'name': 'crew:solo'}] if solo else [], "
                    "'comments': json.loads(os.environ.get('FAKE_COMMENTS_' + args[2], '[]')), "
                    "'closingIssuesReferences': [{'number': 7}], 'body': os.environ.get('FAKE_PR_BODY', '')}))\n")
        os.chmod(os.path.join(bindir, "gh"), 0o755)

    def sandboxing_codex(self):
        """A codex first on PATH that applies its sandbox here: an installed one may not (a nesting launcher, #1252)."""
        path = os.path.join(self.tmp, "bin", "codex")
        with open(path, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)

    def write_profile(self, runtime="tmux", engine="claude-code"):
        self.project = os.path.join(self.project_dir, "crew.toml")
        with open(self.project, "w") as f:
            f.write(PROFILE.format(runtime=runtime, engine=engine, state=os.path.join(self.tmp, "state")))

    def crew(self, *args, stdin="", **env):
        return subprocess.run([sys.executable, CREW, *args], input=stdin, capture_output=True, text=True,
                              env=dict(self.env, **env))

    def up(self):
        return self.crew("up", "--project", self.project, "--inputs", INPUTS)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def new_session(self):
        found = [c for c in self.calls() if c[0] == "new-session"]
        self.assertEqual(len(found), 1, self.calls())
        return found[0]

    def session_env(self, call):
        """A new-session call's environment: exported by window 0's command, never -e on the session (#1957)."""
        self.assertNotIn("-e", call)
        head = call[-1].partition("; ")[0]
        self.assertTrue(head.startswith("export "), call[-1])
        return dict(a.split("=", 1) for a in shlex.split(head)[1:])

    def settings(self):
        with open(os.path.join(self.project_dir, ".claude", "settings.local.json")) as f:
            return json.load(f)

    def put(self, rel, text):
        path = os.path.join(self.state, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)


SECRET = "ghp_" + "S3cr3tT0kenValue0000000000000000000000"  # built at run time; never in a file
ENGINE_STUBS = ("claude", "codex", "pi", "muse", "opencode", "cursor-agent")


class SpawnBase(Base):
    """mdstack spawn / kill against a temp git repo: a bare origin, the project as primary checkout, PR refs."""

    def git(self, *args, cwd=None):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t", *args], cwd=cwd or self.project_dir,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def setUp(self):
        super().setUp()
        self.origin = os.path.join(self.tmp, "origin.git")
        self.git("init", "-q", "--bare", "-b", "main", self.origin, cwd=self.tmp)
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", self.origin)
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        self.git("push", "-q", "origin", "main")
        bindir = os.path.join(self.tmp, "bin")
        with open(os.path.join(bindir, "gh"), "w") as f:  # spawn must never derive the token itself
            f.write("#!/usr/bin/env python3\nimport json, os, sys\nargs = sys.argv[1:]\n"
                    "if args[:2] in (['issue', 'view'], ['pr', 'view']):\n"
                    " solo = args[2] in os.environ.get('FAKE_SOLO_' + args[0].upper(), '').split(',')\n"
                    " print(json.dumps({'labels': [{'name': 'crew:solo'}] if solo else [], "
                    "'comments': json.loads(os.environ.get('FAKE_COMMENTS_' + args[2], '[]')), "
                    "'closingIssuesReferences': [{'number': int(i)} for i in os.environ.get('FAKE_PR_ISSUES', '7').split(',')], "
                    "'body': os.environ.get('FAKE_PR_BODY', '')}))\n"
                    "else:\n open(%r, 'a').write('called\\n')\n print(%r)\n" % (os.path.join(self.tmp, "gh.log"), SECRET))
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        self.env["GH_TOKEN"] = SECRET
        self.assertEqual(self.up().returncode, 0)

    def pr(self, n, engine):
        """Push a PR head with one commit carrying an Engine trailer to refs/pull/<n>/head."""
        self.git("commit", "-q", "--allow-empty", "-m", "feat: x\n\nEngine: %s" % engine)
        self.git("push", "-q", "origin", "HEAD:refs/pull/%d/head" % n)
        sha = self.git("rev-parse", "HEAD")
        self.git("reset", "-q", "--hard", "origin/main")
        return sha

    def spawn(self, *args):
        return self.crew("spawn", *args, "--project", self.project, "--timeout", "1")

    def windows(self):
        found = [c for c in self.calls() if c[0] == "new-window"]
        return found

    def record(self, name):
        with open(os.path.join(self.state, "runs", name + ".json")) as f:
            return json.load(f)


class KillLandedBase(SpawnBase):
    """mdstack kill removes a worktree only when its work has landed, or with --discard --reason (#172)."""

    def setUp(self):
        super().setUp()
        self.gh_log = os.path.join(self.tmp, "gh-calls.log")
        self.gh_exit = 0
        self.write_gh()

    def write_gh(self):
        with open(os.path.join(self.tmp, "bin", "gh"), "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, sys\n"
                    "if sys.argv[1:3] in (['issue', 'view'], ['pr', 'view']):\n"
                    " print(json.dumps({'labels': [], 'comments': [], 'closingIssuesReferences': []}))\n sys.exit(0)\n"
                    "open(%r, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                    "sys.exit(%d)\n" % (self.gh_log, self.gh_exit))

    def gh_calls(self):
        if not os.path.exists(self.gh_log):
            return []
        with open(self.gh_log) as f:
            return [json.loads(line) for line in f]

    def builder(self):
        self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        return self.record("ben-7")["worktree"]

    def commit(self, wt, name="a.txt"):
        with open(os.path.join(wt, name), "w") as f:
            f.write("x\n")
        self.git("add", name, cwd=wt)
        self.git("commit", "-q", "-m", "feat: " + name, cwd=wt)
        return self.git("rev-parse", "HEAD", cwd=wt)

    def kill(self, *args):
        return self.crew("kill", "ben-7", "--project", self.project, *args)

    def assert_refused(self, r, wt, *shown):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("refusing to remove", r.stdout)
        for text in shown:
            self.assertIn(text, r.stdout)
        self.assertTrue(os.path.isdir(wt))
        self.assertTrue(os.path.exists(os.path.join(self.state, "runs", "ben-7.json")))
        self.assertIn(["kill-window", "-t", "=crew-acme-widgets:10"], self.calls())  # the window still stops


class SendBase(Base):
    """mdstack send / acked: one JSON line in the inbox, a fixed nudge, refs only, delivery proven by ack: <id>."""

    def setUp(self):
        super().setUp()
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash", "10": "ben-7"}}, f)
        self.env["CREW_ROLE"] = "coordinator"
        self.env.pop("CREW_ID", None)

    def send(self, *args):
        return self.crew("send", *args, "--project", self.project)

    def inbox(self, window="ben-7"):
        with open(os.path.join(self.state, "inbox", window + ".jsonl")) as f:
            return [json.loads(line) for line in f]


class ObserveBase(Base):
    """mdstack attach / logs (#138) against the fake tmux: attach is read-only by default and never changes the layout."""

    def setUp(self):
        super().setUp()
        self.session = {"0": "ash", "1": "sam", "10": "ben-7", "11": "ben-8", "20": "vera-9-r1-review"}
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": self.session}, f)

    def remote_run(self, name, role="builder", **replies):
        """A run record placed on host-b (#348) and a fake `ssh` that logs each call and answers a verb from replies;
        an attach (`-t`) exits FAKE_SSH_EXIT, as the host's tmux client would."""
        self.put("runs/%s.json" % name, json.dumps(dict(
            index=None, role=role, item="issue #12", repo="acme/widgets", claim=None, engine="claude-code",
            model="opus", effort="high", harness="claude", remote=True, host="host-b", **{"pass": "build"},
            worktree="/home/crew/.mdstack/wt/12-abcdef0-%s-build" % role)))
        self.ssh_log = os.path.join(self.tmp, "ssh.log")
        with open(os.path.join(self.tmp, "bin", "ssh"), "w") as f:
            f.write("#!/usr/bin/env python3\nimport base64, json, os, sys\n"
                    "if '-G' in sys.argv:\n    print('hostname host-b')\n    sys.exit(0)\n"
                    "tty = '-t' in sys.argv\n"
                    "request = json.loads(base64.urlsafe_b64decode(sys.argv[-1].split(' ', 1)[1]) if tty else sys.stdin.read())\n"
                    "open(%r, 'a').write(json.dumps(dict(argv=sys.argv[1:], request=request)) + '\\n')\n"
                    "code = int(os.environ.get('FAKE_SSH_EXIT', '0'))\n"
                    "if not tty and code != 255:\n    print(json.dumps(%r.get(request['verb'])))\n"
                    "sys.exit(code)\n" % (self.ssh_log, replies))
        os.chmod(os.path.join(self.tmp, "bin", "ssh"), 0o755)

    def ssh_calls(self):
        if not os.path.exists(self.ssh_log):
            return []
        with open(self.ssh_log) as f:
            return [json.loads(line) for line in f]


HEAD = "1" * 40


# Liveness (#135): a tmux wrapper answers the probe's pane query from $FAKE_PANES and passes every other call to
# the fake above; a fake `ps` answers start times, commands and foreground names from $FAKE_PS.
FAKE_TMUX_PANES = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    full = sys.argv[1:]
    args = full[2:] if full[:1] in (["-L"], ["-S"]) else full
    def load(var):
        return json.load(open(os.environ[var])) if os.path.exists(os.environ[var]) else {}
    if args[0] == "capture-pane":
        print(load("FAKE_PANES").get(args[args.index("-t") + 1].lstrip("="), {}).get("screen", ""))
        sys.exit(0)
    if args[0] == "display-message" and "#{pane_id}" in args[-1]:
        target = args[args.index("-t") + 1].lstrip("=")
        session, _, index = target.partition(":")
        state = load("FAKE_TMUX_STATE")
        if index not in state.get(session, {}):
            sys.exit(1)
        p = dict({"id": "%" + index, "pid": str(9000000 + int(index)), "dead": "0", "activity": "0",
                  "command": state.get("_panes", {}).get(target, "")}, **load("FAKE_PANES").get(target, {}))
        print(p["id"], p["pid"], p["dead"], p["activity"], "/dev/ttyp" + index, p["command"])
        sys.exit(0)
    os.execv(os.path.join(os.path.dirname(sys.argv[0]), "tmux-base"), ["tmux"] + full)
    """)
FAKE_PS = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    ps = json.load(open(os.environ["FAKE_PS"])) if os.path.exists(os.environ["FAKE_PS"]) else {}
    if "command=" in args:
        print(ps.get("command", {}).get(args[args.index("-p") + 1], ""))
    elif "-p" in args:
        print(ps.get("start", {}).get(args[args.index("-p") + 1], "Fri Oct 30 10:00:00 2026"))
    elif "args=" in args:
        for stat, argv in ps.get("argv", {}).get(args[args.index("-t") + 1], []):
            print(stat, argv)
    elif "-axo" in args:
        for child, parent, stat, command in ps.get("children", []):
            print(child, parent, stat, command)
    else:
        for stat, comm in ps.get("fg", {}).get(args[args.index("-t") + 1], []):
            print(stat, comm)
    """)
NOW = 2_000_000_000.0  # fake clock for scan()
# Pane screens for dialog() (#289), from throwaway tmux sessions (Claude Code 2.1.310, codex-cli 0.164.0) with paths
# and host lines neutralised. Reconstructed, since the live CLI would not show them: codex-approval (heading and footer
# from the issue, options from the 0.164.0 binary), codex-api-error (the issue's error line) and claude-api-error.
STUCK = ["claude-proceed", "claude-edit", "claude-trust", "claude-api-error", "codex-approval", "codex-trust",
         "codex-api-error", "codex-hooks"]
WORKING = ["claude-quote-idle", "claude-quote-working", "codex-idle", "codex-hooks-quote"]  # quote-*: prompt text


def screen(name):
    with open(os.path.join(TESTS, "environments", "fixtures", "dialog", name + ".txt"), encoding="utf-8") as f:
        return f.read()


class LivenessBase(SpawnBase):
    """mdstack status / watch / restart and the C5 probe, with a fake clock, fake tmux panes and a fake ps."""

    def setUp(self):
        super().setUp()
        bindir = os.path.join(self.tmp, "bin")
        os.rename(os.path.join(bindir, "tmux"), os.path.join(bindir, "tmux-base"))
        for name, text in [("tmux", FAKE_TMUX_PANES), ("ps", FAKE_PS)]:
            with open(os.path.join(bindir, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(bindir, name), 0o755)
        self.panes, self.ps = os.path.join(self.tmp, "panes.json"), os.path.join(self.tmp, "ps.json")
        self.env.update(FAKE_PANES=self.panes, FAKE_PS=self.ps)
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        self.mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(self.mod)
        self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        self.set_pane(10)

    def set_pane(self, index, **kv):
        with open(self.panes, "w") as f:
            json.dump({"crew-acme-widgets:%d" % index: kv}, f)

    def probe(self, name="ben-7"):
        with mock.patch.dict(os.environ, self.env):
            windows = dict((n, i) for i, n in self.mod.tmux.list_windows("crew-acme-widgets"))
            return self.mod.probe("crew-acme-widgets", name, self.record(name), windows)

    def scan(self, now, seen=None):
        self.seen = seen or {"offsets": {}, "keys": {}}
        with mock.patch.dict(os.environ, self.env):
            return self.mod.scan(self.state, "crew-acme-widgets", now, 900, self.seen)

    def beat(self, when):
        os.utime(os.path.join(self.state, "runs", "ben-7.json"), (when, when))

    def stubborn(self, *ignored):
        """A real pane process in its own group that ignores the given signals (Codex ignores SIGHUP), reparented
        away from the test so nothing leaves a zombie; it logs each signal it got."""
        log = os.path.join(self.tmp, "signals.log")
        code = ("import os, signal, sys, time\n"
                "if os.fork(): sys.exit(0)\n"
                "os.setsid()\n"
                "for s in %r: signal.signal(s, lambda n, f: open(%r, 'a').write('%%d\\n' %% n))\n"
                "print(os.getpid(), flush=True)\n"
                "null = os.open(os.devnull, os.O_RDWR)\n"
                "os.dup2(null, 1), os.dup2(null, 2)\n"
                "time.sleep(60)\n" % ([int(s) for s in ignored], log))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10).stdout
        pid = int(out.split()[0])
        self.addCleanup(lambda: subprocess.run(["kill", "-9", str(pid)], capture_output=True))
        return pid, log

    def alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False


class DeliveryBase(LivenessBase):
    """Busy delivery (#1850): ben-7 is a spawned builder on fake panes in its recorded harness (codex); screens come
    from that adapter's own BUSY and composer patterns, and each crew call is a fresh process (a restarted lead or
    watcher)."""
    BUSY = "• Running tests (2m 03s • esc to interrupt)\n\n› Ask Codex to do anything\n"
    IDLE = "• Done.\n\n› Ask Codex to do anything\n"

    def setUp(self):
        super().setUp()
        self.show(self.IDLE)

    def show(self, text, **kv):
        self.set_pane(10, **dict(dict(command=self.record("ben-7")["harness"], screen=text), **kv))

    def send(self, *args):
        return self.crew("send", "ben-7", *args, "--project", self.project)

    def inbox(self):
        path = os.path.join(self.state, "inbox", "ben-7.jsonl")
        with open(path) if os.path.exists(path) else open(os.devnull) as f:
            return [json.loads(line) for line in f]

    def typed(self):
        return [c for c in self.calls() if c[0] == "send-keys"]

    def delivery(self, msg_id):
        r = self.crew("acked", "ben-7", msg_id, "--delivery", "--project", self.project)
        return r, json.loads(r.stdout) if r.returncode in (0, 3) else None

    def tree(self):
        """Every file under the state dir with its bytes: a read must leave it unchanged."""
        found = {}
        for root, _, files in os.walk(self.state):
            for name in files:
                with open(os.path.join(root, name), "rb") as f:
                    found[os.path.join(root, name)] = f.read()
        return found
