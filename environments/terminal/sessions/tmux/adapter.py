"""tmux adapter for cli/mdstack: every tmux call goes through here, so tests can put a fake `tmux` on PATH."""
import subprocess
import os
import time
import shlex

EXECUTABLE = "tmux"
RANK = 0
CAPABILITIES = {"reload", "dead-keeps-pid", "icon"}  # its doorbell is the core's cursor-checked composer nudge (mdstack send)
SOCKET = None  # the session name, set by crew_shared.profile; names the dedicated server `-L SOCKET` (#818)
DEDICATED = False  # runtime.options.tmux_server = "dedicated": the crew's own `-L SOCKET` server (#818, opt-in #1327)
WORKER_TMUX = "/dev/null/mdstack-worker,0,0"  # a role window's $TMUX: no server can listen under a non-directory (#1475)
_server = {}


def default_socket():
    """The default server's socket by path, so an inherited $TMUX (a caller's or a test's) is never followed (#818)."""
    return os.path.join(os.environ.get("TMUX_TMPDIR") or "/tmp", "tmux-%d" % os.getuid(), "default")


def server():
    """The chosen server: the owner's default server, named by path, or with DEDICATED `-L SOCKET`, so an agent's tmux
    mistake stays off the owner's server. A crew session still running on the other server is used there until its next
    mdstack up (#1327; pre-#818 sessions likewise). None of SOCKET keeps the default server. Never the inherited $TMUX:
    under a private TMUX_TMPDIR a test cannot reach the caller's server."""
    key = (SOCKET, DEDICATED)
    if key not in _server:
        # tmux makes its socket directory only when it resolves the default itself; a fresh host (no tmux run yet,
        # as a role host's runner) would otherwise fail every -S call (#346)
        os.makedirs(os.path.dirname(default_socket()), mode=0o700, exist_ok=True)
        default = ["-S", default_socket()]
        dedicated = ["-L", SOCKET] if SOCKET else default
        own, other = (dedicated, default) if DEDICATED else (default, dedicated)
        probe = ["has-session", "-t", "=%s" % SOCKET]
        moved = own != other and subprocess.run(["tmux", *own, *probe], capture_output=True).returncode and \
            not subprocess.run(["tmux", *other, *probe], capture_output=True).returncode
        _server[key] = other if moved else own
    return _server[key]


def bind(session, tmux_server="default"):
    """The session and its tmux server, runtime.options.tmux_server: "default" or "dedicated" (#818, #1327)."""
    global SOCKET, DEDICATED
    SOCKET, DEDICATED = session, tmux_server == "dedicated"


def tmux(*args):
    return subprocess.run(["tmux", *server(), *args], capture_output=True, text=True)


def has_session(name):
    return tmux("has-session", "-t", "=" + name).returncode == 0


def new_session(name, window, cwd, env, command, private_env=None):
    """Detached session; private environment crosses stdin, never argv or a file."""
    flags = [x for k, v in env.items() for x in ("-e", "%s=%s" % (k, v))]
    args = ["new-session", "-d", "-s", name, "-n", window, "-c", cwd, *flags]
    r = tmux(*args, "sleep 60" if private_env else command)
    if r.returncode:
        raise RuntimeError("tmux new-session failed: " + r.stderr.strip())
    if not has_session(name):  # tmux can print `error creating …` and still exit 0, so a caller never runs sessionless (#1480)
        raise RuntimeError("tmux new-session failed: no session %s after exit 0: %s" % (name, r.stderr.strip()))
    pin_layout(name)
    tmux("move-window", "-s", "=" + name, "-t", "=%s:0" % name)  # window 0 even with a user base-index
    if private_env:
        lines = [shlex.join(["set-environment", "-t", "=" + name, k, v]) for k, v in private_env.items()]
        lines.append(shlex.join(["respawn-pane", "-k", "-t", "=%s:0" % name, command]))
        r = subprocess.run(["tmux", *server(), "source-file", "-"], input="\n".join(lines) + "\n",
                           capture_output=True, text=True)
        if r.returncode:
            kill_session(name)
            raise RuntimeError("tmux new-session failed: private environment launch refused")


def pin_layout(name):
    """Keep the index bands stable against a user renumber-windows / base-index: this session only, never -g."""
    for option, value in [("renumber-windows", "off"), ("base-index", "0")]:
        tmux("set-option", "-t", "=%s:" % name, option, value)  # set-option -t is a pane target


ICON = "#{?@crew_icon,#{@crew_icon} ,}"  # display-only: window names stay the targeting identity (#1157)


def icon(name, index, emoji):
    """Show emoji before the tab through the window's @crew_icon option, prefixed to the owner's own status formats on
    this window only: never -g, never another session."""
    target = "=%s:%d" % (name, index)
    tmux("set-option", "-w", "-t", target, "@crew_icon", emoji)
    for option in ("window-status-format", "window-status-current-format"):
        current = tmux("show-options", "-wgv", option).stdout.rstrip("\n") or "#I:#W#{?window_flags,#{window_flags}, }"
        tmux("set-option", "-w", "-t", target, option, current if current.startswith(ICON) else ICON + current)


def list_windows(name):
    out = tmux("list-windows", "-t", "=" + name, "-F", "#{window_index} #{window_name}").stdout
    return [(int(i), n) for i, _, n in (line.partition(" ") for line in out.splitlines())]


def has_window(name, index):
    """Whether the session has a window at index; None when tmux cannot answer."""
    windows = tmux("list-windows", "-t", "=" + name, "-F", "#{window_index}")
    if windows.returncode:
        return None
    return str(index) in [line.split()[0] for line in windows.stdout.splitlines() if line.strip()]


def kill_window(name, index):
    tmux("kill-window", "-t", "=%s:%d" % (name, index))


def kill_session(name):
    tmux("kill-session", "-t", "=" + name)


def new_window(name, index, window, cwd, env, command):
    """Background window (focus stays on the coordinator); env holds names, paths and logins only, never tokens. Its
    $TMUX is WORKER_TMUX, so a bare `tmux kill-server` from the agent's shell misses the crew's server (#1475, #817);
    crew commands never follow $TMUX (server())."""
    flags = [x for k, v in dict(env, TMUX=WORKER_TMUX).items() for x in ("-e", "%s=%s" % (k, v))]
    r = tmux("new-window", "-d", "-t", "=%s:%d" % (name, index), "-n", window, "-c", cwd, *flags, command)
    if r.returncode:
        raise RuntimeError("tmux new-window failed: " + r.stderr.strip())


def pane_command(name, index):
    """The pane's foreground command, or `dead` for a dead pane, whose command would read as the launch's first word."""
    return tmux("display-message", "-p", "-t", "=%s:%d" % (name, index),
                "#{?pane_dead,dead,#{pane_current_command}}").stdout.strip()


def capture(name, index):
    """The pane's visible screen, for the trust-dialog check (tmux.md Q7)."""
    return tmux("capture-pane", "-p", "-t", "=%s:%d" % (name, index)).stdout


def cursor(name, index):
    """The pane's cursor as (column, row) on its visible screen, for the nudge's composer check (#308); None when
    tmux cannot answer."""
    out = tmux("display-message", "-p", "-t", "=%s:%d" % (name, index), "#{cursor_x} #{cursor_y}").stdout.split()
    return (int(out[0]), int(out[1])) if len(out) == 2 and all(p.isdigit() for p in out) else None


def press(name, index, *keys):
    """Named keys (Enter, C-u), which tmux interprets; text goes through send_keys."""
    tmux("send-keys", "-t", "=%s:%d" % (name, index), *keys)


def send_keys(name, index, text, settle=0.3):
    """Type a fixed nudge line literally (-l, so no key names are interpreted), then Enter after settle seconds: an
    Enter right behind the typed text lands in Codex's paste burst and adds a newline instead of submitting (#308)."""
    tmux("send-keys", "-t", "=%s:%d" % (name, index), "-l", text)
    time.sleep(settle)
    press(name, index, "Enter")


def attach(target, read_only=True):
    """Attach the caller's terminal (no capture); -r makes the client read-only, it can still detach."""
    return subprocess.run(["tmux", *server(), "attach-session", *(["-r"] if read_only else []), "-t", target]).returncode


def socket_path():
    """The crew server's socket path, for comparing it with a calling client's $TMUX (#1845)."""
    own = server()
    return own[1] if own[0] == "-S" else os.path.join(os.path.dirname(default_socket()), own[1])


def client_socket():
    """The socket of the tmux server the caller is a client of, from its $TMUX; None outside tmux."""
    value = os.environ.get("TMUX", "")
    return value.rsplit(",", 2)[0] if value else None


def switch(target):
    """Switch the calling tmux client to target on the crew's server instead of nesting an attach (#1845)."""
    return subprocess.run(["tmux", *server(), "switch-client", "-t", target]).returncode


def attach_hint(session):
    """The owner's attach line on the crew's server: plain `tmux attach` on the default server (#818, #1327)."""
    own = server()
    return shlex.join(["tmux", *(own if own[0] == "-L" else []), "attach", "-t", session])


def hold(name, index):
    """Keep the window when its only process exits, so a reload's stop does not destroy it (#1087)."""
    result = tmux("set-option", "-w", "-t", "=%s:%d" % (name, index), "remain-on-exit", "on")
    if result.returncode:
        raise RuntimeError("reload failed: " + result.stderr.strip())


def respawn(name, index, cwd, env, command):
    """Restart a held window in place with a new command and environment, then drop the hold. A role window keeps its
    WORKER_TMUX guard (#1475); window 0, the coordinator, keeps the crew's $TMUX."""
    target = "=%s:%d" % (name, index)
    flags = [x for k, v in (dict(env, TMUX=WORKER_TMUX) if index else env).items() for x in ("-e", "%s=%s" % (k, v))]
    result = tmux("respawn-window", "-k", "-t", target, "-c", cwd, *flags, command)
    if result.returncode:
        raise RuntimeError("reload failed: " + result.stderr.strip())
    tmux("set-option", "-w", "-u", "-t", target, "remain-on-exit")


def view(name, commands):
    """Temporary detached session, one tiled pane per command; a session of its own, so no crew window moves."""
    r = tmux("new-session", "-d", "-s", name, "-n", "view", commands[0])
    if r.returncode:
        raise RuntimeError("tmux new-session failed: " + r.stderr.strip())
    for command in commands[1:]:
        tmux("split-window", "-t", "=%s:" % name, command)
        tmux("select-layout", "-t", "=%s:" % name, "tiled")


def pane(name, index):
    """Pane identity and state for the liveness probe (tmux.md Q7); None when tmux cannot answer."""
    r = tmux("display-message", "-p", "-t", "=%s:%d" % (name, index),
             "#{pane_id} #{pane_pid} #{pane_dead} #{window_activity} #{pane_tty} #{pane_current_command}")
    parts = r.stdout.strip().split(None, 5)
    if r.returncode or len(parts) < 5:
        return None
    return dict(zip(["id", "pid", "dead", "activity", "tty", "command"], parts + [""]))


def foreground(tty):
    """Names of the processes in the tty's foreground process group (ps stat has '+')."""
    out = subprocess.run(["ps", "-o", "stat=", "-o", "comm=", "-t", tty], capture_output=True, text=True).stdout
    return [c.strip().rsplit("/", 1)[-1] for s, _, c in (line.strip().partition(" ") for line in out.splitlines())
            if "+" in s]
