#!/usr/bin/env python3
"""Local lab Docker setup and teardown on the primary (M20.1 lab C, #1357).

Usage: crew-lab-docker.py setup MANIFEST --image REF --stage DIR --tag TAG [--source-sha SHA] [--host ALIAS ...]
                                [--context NAME] [--n3]
       crew-lab-docker.py n3 MANIFEST
       crew-lab-docker.py teardown MANIFEST

MANIFEST is a campaign run manifest (scripts/campaign-guard.py); every command runs its guard check first. `setup`
refuses before any Docker mutation when the manifest already has a `lab` section, an alias is not lowercase, or a
container or network with a planned name or the run's label exists. It pins the Docker context's endpoint and the
image ID, then writes the `lab` section (context, endpoint, run, owner label, image, stage hashes) and adds each
network and container ID the moment Docker returns it. Per host: its own network (`--internal` with --n3), a
container with no mount, SSH published on 127.0.0.1 only (none with --n3), the staged bundle activated and the
run's key authorized by crew-lab-host.py, and its host key in a per-run known_hosts. --n3 adds a driver container
on every host network. Loopback runs get a per-run SSH config mapping each alias to 127.0.0.1:<port>. `n3` probes
from each host to the other hosts, the Mac (pinned to the host gateway with --n3) and the internet, with the driver
as positive control; it writes lab/n3.json and exits 1 with `n3: unproved` unless every probe is denied (an
unresolved name is not denied). `teardown` first inspects every recorded ID and refuses, removing nothing, when
the context now points elsewhere or a live ID lost the run's owner or run label. Otherwise it saves each
resource's inspect JSON and logs under lab/evidence/, removes only those IDs, then checks the state sentinel and a
tmux decoy, and adds that cleanup to each evidence record under lab/runs/: no prune, wildcard or kill-server.
Every child gets only PATH and locale plus the run's own HOME and auth dirs: no CREW_*, token, SSH agent or TMUX.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))), "scripts")
ALIAS, RUN = re.compile(r"[a-z][a-z0-9-]{0,30}"), re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,40}")
HOST_PY = "/usr/local/lib/mdstack-lab/environments/terminal/remote/lab/crew-lab-host.py"
HOST_KEY = "/etc/ssh/crew-lab/ssh_host_ed25519_key.pub"
KEEP = ("PATH", "LANG", "LC_ALL", "TMPDIR", "USER", "LOGNAME")
OUTSIDE = ["host.docker.internal:22", "1.1.1.1:443"]  # the Mac and the internet
PROBE = """import json, socket, sys
out = {}
for t in sys.argv[1:]:
    h, p = t.rsplit(":", 1)
    try:
        socket.create_connection((h, int(p)), 3).close()
        out[t] = "open"
    except ConnectionRefusedError:
        out[t] = "refused"
    except socket.gaierror as e:
        out[t] = "unresolved: %s" % e
    except OSError as e:
        out[t] = "denied: %s" % e
print(json.dumps(out))"""


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = load("campaign_guard", "campaign-guard.py")


def call(argv, env):
    return subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)


def lab_dir(m):
    return os.path.join(m["roots"]["state_dir"], "lab")


def child_env(m):
    d = lab_dir(m)
    env = {k: os.environ[k] for k in KEEP if k in os.environ}
    env.update(HOME=os.path.join(d, "home"), XDG_CONFIG_HOME=os.path.join(d, "home", ".config"),
               GH_CONFIG_DIR=os.path.join(d, "gh-config"), MDSTACK_INTERNAL="1")  # scenarios pass --project (#1965)
    if m.get("lab"):
        env["DOCKER_HOST"] = m["lab"]["endpoint"]
    return env


def decoy_start(m):
    """A tmux server on its own throwaway socket, started in the lab env; None without tmux."""
    if not shutil.which("tmux"):
        return None
    sock = os.path.join(tempfile.mkdtemp(prefix="crew-lab-decoy-"), "s")
    call(["tmux", "-f", os.devnull, "-S", sock, "new-session", "-d", "-s", "decoy", "sleep 86400"], child_env(m))
    if not decoy_alive(m, sock):  # new-session -d can exit 0 without a server
        raise RuntimeError("the tmux decoy did not start on %s" % sock)
    return sock


def decoy_alive(m, sock):
    return sock is None or call(["tmux", "-S", sock, "has-session", "-t", "=decoy"], child_env(m)).returncode == 0


def owner_docker(*argv):
    """Read-only, with the owner's Docker config so the context store resolves; still no token, agent or TMUX."""
    env = {k: os.environ[k] for k in KEEP + ("HOME", "DOCKER_CONFIG") if k in os.environ}
    r = call(["docker", *argv], env)
    if r.returncode:
        raise RuntimeError("docker %s: %s" % (argv[0], r.stderr.strip()[-300:]))
    return r.stdout.strip()


def endpoint(context):
    return owner_docker("context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}")


def docker(m, *argv, check=True):
    r = call(["docker", *argv], child_env(m))
    if check and r.returncode:
        raise RuntimeError("docker %s: %s" % (" ".join(argv[:2]), r.stderr.strip()[-300:]))
    return r.stdout.strip()


def save(path, m):
    Path(path).write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setup(a):
    m = json.loads(Path(a.manifest).read_text())
    run, hosts = m["run_id"], a.host or ["lab-a", "lab-b"]
    problems = guard.refusals(m) + ["host: %s is not a lowercase alias" % h for h in hosts if not ALIAS.fullmatch(h)]
    problems += [] if RUN.fullmatch(run) else ["run: %s is not a Docker-safe run id" % run]
    problems += ["lab: run %s already has lab resources; write a new manifest" % run] if "lab" in m else []
    if problems:
        return problems
    context = a.context or owner_docker("context", "show")
    owner = hashlib.sha256(("%s %s" % (os.path.realpath(a.manifest), run)).encode()).hexdigest()[:16]
    m["lab"] = lab = dict(context=context, endpoint=endpoint(context), run=run, owner=owner, n3=a.n3, tag=a.tag,
                          source_sha=a.source_sha, hosts={}, networks=[], driver=None)
    d = lab_dir(m)
    os.makedirs(os.path.join(d, "home", ".ssh"), mode=0o700, exist_ok=True)
    names = ["crew-lab-%s-%s" % (run, h) for h in hosts] + (["crew-lab-%s-driver" % run] if a.n3 else [])
    taken = set()
    for kind, fmt in (("ps", "{{.Names}}"), ("network", "{{.Name}}")):
        ls = ["ps", "-a"] if kind == "ps" else ["network", "ls"]
        taken |= set(docker(m, *ls, "--format", fmt).split()) & set(names)
        taken |= set(docker(m, *ls, "--filter", "label=mdstack.lab.run=" + run, "--format", fmt).split())
    if taken:
        return ["collision: %s already exists" % n for n in sorted(taken)]
    lab["image"] = docker(m, "image", "inspect", "--format", "{{.Id}}", a.image)
    lab["stage"] = {f.name: sha256(f) for f in sorted(Path(a.stage).iterdir()) if f.is_file()}
    key = os.path.join(d, "id_ed25519")
    if call(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "crew-lab-" + run, "-f", key],
            child_env(m)).returncode:
        return ["key: ssh-keygen could not write %s" % key]
    save(a.manifest, m)
    labels = [x for k, v in (("run", run), ("owner", owner)) for x in ("--label", "mdstack.lab.%s=%s" % (k, v))]
    try:
        for h, name in zip(hosts, names):
            add_host(a, m, h, name, labels, key + ".pub")
        if a.n3:
            add_driver(a, m, names[-1], labels)
    except RuntimeError as e:
        return ["setup: %s (recorded IDs stay in the manifest for teardown)" % e]
    write_ssh(m, key)
    print("ok: lab %s up with %s (%s)" % (run, ", ".join(hosts), "n3 driver" if a.n3 else "loopback SSH"))
    return 0


def add_host(a, m, h, name, labels, pub):
    lab = m["lab"]
    lab["networks"].append(docker(m, "network", "create", *(["--internal"] if a.n3 else []), *labels, name))
    save(a.manifest, m)
    publish = ["--add-host", "host.docker.internal:host-gateway"] if a.n3 else ["-p", "127.0.0.1::22"]
    cid = docker(m, "create", "--name", name, "--hostname", h, *labels, "--network", lab["networks"][-1],
                 "--network-alias", h, *publish, lab["image"])
    host = lab["hosts"][h] = {"container": cid, "network": lab["networks"][-1]}
    save(a.manifest, m)
    mounts = json.loads(docker(m, "inspect", "--format", "{{json .Mounts}}", cid) or "[]")
    if any(x.get("Type") != "volume" for x in mounts):
        raise RuntimeError("%s has a non-volume mount" % name)
    host["volumes"] = [x["Name"] for x in mounts]
    docker(m, "cp", pub, cid + ":/tmp/crew-lab.pub")
    docker(m, "cp", a.stage, cid + ":/tmp/crew-stage")
    docker(m, "start", cid)
    src = ["--source-sha", a.source_sha] if a.source_sha else []
    docker(m, "exec", cid, "python3", HOST_PY, "activate", "--stage", "/tmp/crew-stage", "--tag", a.tag, *src)
    act = host["activated"] = json.loads(docker(m, "exec", cid, "cat", "/opt/mdstack-lab.json"))
    if act.get("bundle_sha256") not in lab["stage"].values() or act.get("source_sha") != a.source_sha:
        raise RuntimeError("%s activated bundle %s at source %s, not the staged one" % (
            name, act.get("bundle_sha256"), act.get("source_sha")))
    docker(m, "exec", cid, "python3", HOST_PY, "authorize", "--user", "crew", "--key-file", "/tmp/crew-lab.pub")
    for _ in range(30):
        host["host_key"] = " ".join(docker(m, "exec", cid, "cat", HOST_KEY, check=False).split()[:2])
        if host["host_key"]:
            break
        time.sleep(1)
    else:
        raise RuntimeError("%s made no SSH host key" % name)
    if not a.n3:
        ports = docker(m, "port", cid, "22/tcp").splitlines()
        if not ports or any(not p.startswith("127.0.0.1:") for p in ports):
            raise RuntimeError("%s publishes SSH beyond 127.0.0.1: %s" % (name, ports))
        host["port"] = int(ports[0].rsplit(":", 1)[1])
    save(a.manifest, m)


def add_driver(a, m, name, labels):
    lab, nets = m["lab"], m["lab"]["networks"]
    lab["driver"] = docker(m, "create", "--name", name, *labels, "--network", nets[0], "--entrypoint", "python3",
                           lab["image"], "-c", "import time; time.sleep(1e9)")
    save(a.manifest, m)
    for net in nets[1:]:
        docker(m, "network", "connect", net, lab["driver"])
    docker(m, "start", lab["driver"])


def write_ssh(m, key):
    home, conf, known = os.path.join(lab_dir(m), "home", ".ssh"), [], []
    for h, host in m["lab"]["hosts"].items():
        known.append("%s %s\n" % (h, host["host_key"]))
        if "port" in host:
            conf.append("Host %s\n  HostName 127.0.0.1\n  Port %d\n  User crew\n  HostKeyAlias %s\n  IdentityFile %s\n"
                        "  IdentitiesOnly yes\n  IdentityAgent none\n  UserKnownHostsFile %s\n"
                        "  StrictHostKeyChecking yes\n" % (h, host["port"], h, key, os.path.join(home, "known_hosts")))
    Path(home, "known_hosts").write_text("".join(known))
    Path(home, "config").write_text("".join(conf))


def n3(a):
    m = json.loads(Path(a.manifest).read_text())
    problems = guard.refusals(m) + ([] if m.get("lab") else ["lab: no lab resources recorded"])
    if problems:
        return problems
    lab, reasons = m["lab"], []
    if not lab["n3"]:
        reasons.append("loopback setup: hosts sit on non-internal networks, so the Mac and the internet are routable")
    else:
        ips = {h: docker(m, "inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                         x["container"]).split() for h, x in lab["hosts"].items()}
        probes = [(h, x["container"], ["%s:22" % ip for o in ips if o != h for ip in ips[o]] + OUTSIDE)
                  for h, x in lab["hosts"].items()]
        for h, cid, targets in probes:
            seen = json.loads(docker(m, "exec", cid, "python3", "-c", PROBE, *targets))
            reasons += ["%s -> %s: %s" % (h, t, r) for t, r in seen.items() if not r.startswith("denied")]
        control = ["%s:22" % ip for v in ips.values() for ip in v]
        seen = json.loads(docker(m, "exec", lab["driver"], "python3", "-c", PROBE, *control))
        reasons += ["driver -> %s: %s, so the probe has no positive control" % (t, r)
                    for t, r in seen.items() if r != "open"]
    Path(lab_dir(m), "n3.json").write_text(json.dumps({"proved": not reasons, "reasons": reasons}, indent=2) + "\n")
    print("n3: proved" if not reasons else "n3: unproved\n" + "\n".join("  " + r for r in reasons))
    return 1 if reasons else 0


def teardown(a):
    m = json.loads(Path(a.manifest).read_text())
    problems = guard.refusals(m) + ([] if m.get("lab") else ["lab: no lab resources recorded"])
    if not problems and endpoint(m["lab"]["context"]) != m["lab"]["endpoint"]:
        problems.append("context: %s no longer points at %s" % (m["lab"]["context"], m["lab"]["endpoint"]))
    if problems:
        return problems
    lab, ev = m["lab"], os.path.join(lab_dir(m), "evidence")
    items = [("container", h, x["container"]) for h, x in lab["hosts"].items()]
    items += [("container", "driver", lab["driver"])] if lab["driver"] else []
    items += [("network", "net-%d" % i, n) for i, n in enumerate(lab["networks"])]
    live, record = [], {"removed": [], "gone": []}
    for kind, name, rid in items:
        found = json.loads(docker(m, "inspect", "--type", kind, rid, check=False) or "[]")
        if not found:
            record["gone"].append(rid)
            continue
        labels = (found[0].get("Config") or found[0]).get("Labels") or {}
        if labels.get("mdstack.lab.owner") != lab["owner"] or labels.get("mdstack.lab.run") != lab["run"]:
            problems.append("owner: %s %s no longer carries run %s's labels" % (kind, rid, lab["run"]))
        live.append((kind, name, rid, found))
    if problems:
        return problems + ["teardown: nothing removed"]
    os.makedirs(ev, exist_ok=True)
    decoy = decoy_start(m)
    for kind, name, rid, found in live:
        Path(ev, name + ".inspect.json").write_text(json.dumps(found, indent=2) + "\n")
        if kind == "container":
            r = call(["docker", "logs", rid], child_env(m))
            Path(ev, name + ".log").write_text(r.stdout + r.stderr)
        docker(m, *(["rm", "-f", "-v"] if kind == "container" else ["network", "rm"]), rid)
        record["removed"].append(rid)
    record["sentinel_unchanged"] = guard.main(["sentinel", a.manifest]) == 0
    record["tmux_decoy_alive"] = decoy_alive(m, decoy)
    if decoy:
        call(["tmux", "-S", decoy, "kill-session", "-t", "=decoy"], child_env(m))
    Path(lab_dir(m), "cleanup.json").write_text(json.dumps(record, indent=2) + "\n")
    evidence = importlib.util.spec_from_file_location("crew_lab_evidence", os.path.join(HERE, "crew-lab-evidence.py"))
    labe = importlib.util.module_from_spec(evidence)
    evidence.loader.exec_module(labe)
    labe.close(lab_dir(m), record)  # each scenario run's evidence record gets its teardown (#1442)
    print("removed: %d, gone: %d" % (len(record["removed"]), len(record["gone"])))
    ok = record["sentinel_unchanged"] and record["tmux_decoy_alive"]
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("manifest")
    for flag in ("image", "stage", "tag"):
        s.add_argument("--" + flag, required=True)
    s.add_argument("--source-sha")
    s.add_argument("--context")
    s.add_argument("--host", action="append", default=[])
    s.add_argument("--n3", action="store_true")
    for name in ("n3", "teardown"):
        sub.add_parser(name).add_argument("manifest")
    args = ap.parse_args(argv)
    try:
        result = {"setup": setup, "n3": n3, "teardown": teardown}[args.cmd](args)
    except RuntimeError as e:
        result = ["%s: %s" % (args.cmd, e)]
    if isinstance(result, list):
        for problem in result:
            print("refused: " + problem)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
