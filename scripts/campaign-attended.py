#!/usr/bin/env python3
"""Attended owner-channel and sleep run (#1463, part of #804): A26 around an actual machine sleep, plus a real
sandbox Slack delivery the owner confirms. Runbook: docs/campaign-harness.md, Attended owner-channel and sleep run.

Runs A26's steps before its first `resume-*` step (a handled head, then the forge moves while paused), sends one
owner-channel `ask` carrying a receipt code through `mdstack notify` under a sandbox away record, snapshots the
sandbox claims, worktrees and tmux windows, then waits for the owner to sleep and wake the machine: a wall-clock jump
over --gap seconds across one poll. After resume it checks the snapshot is unchanged, asks for the code the owner
read on the channel, and runs A26's resume steps (missed head, red CI and one overdue sweep caught up exactly once).
--dry-run uses a loopback webhook, reads the code from its post and does not wait for sleep; its record says
`mode: rehearsal, evidence: false`. The webhook comes only from CAMPAIGN_WEBHOOK in the owner's environment, is
never printed or written, and is refused when it equals the production profile's own webhook. Results: --out,
inside a sandbox root. Exit 0 only on PASS; 2 on a refusal.

Usage: campaign-attended.py MANIFEST --scenarios DIR --out FILE [--dry-run] [--gap SECS] [--max-wait SECS]
"""
import argparse
import http.server
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location("campaign_run", Path(__file__).with_name("campaign-run.py"))
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)
SLACK = '\n[backends.owner-channel]\nname = "slack"\n\n[runtime.options]\nslack_webhook_env = "CAMPAIGN_WEBHOOK"\n' \
        'slack_digest_interval = 86400\n'


def utc(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def loopback(posts):
    class Hook(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            posts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"])))["text"])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d/hook" % server.server_address[1]


def away(gh, state, cmd, record):
    """Append one signed coordinator away or away-return record to the fake forge's control-item comments."""
    path = Path(gh, "api---paginate---slurp.json")
    pages = json.loads(path.read_text()) if path.exists() else [[]]
    body = "🔥 Ash · Steer · %s\n\n```json\n%s\n```\n\n<!-- crew:v1 role=coordinator pass=steer cmd=%s cmd-id=%s sha=%s " \
           "round=n/a verdict=n/a -->\n\n— Ash (CTO) · stub · stub" % (cmd, json.dumps(record), cmd, cmd + "-1463", "a" * 40)
    pages[0].append({"id": len(pages[0]) + 1, "user": {"login": "sandbox-coordinator"}, "created_at": utc(),
                     "updated_at": utc(), "body": body})
    path.write_text(json.dumps(pages))
    Path(state, "away-control.json").write_text('{"issue": 1}')


def snapshot(m, state, env):
    claims = {p.name: p.read_text() for p in sorted(Path(state, "claims").glob("*"))} if Path(state, "claims").is_dir() else {}
    def run(*a):  # a failed read would make an empty snapshot that always compares equal
        r = subprocess.run(a, capture_output=True, text=True, env=env)
        if r.returncode:
            raise RuntimeError("snapshot: %s exited %d: %s" % (a[0], r.returncode, r.stderr.strip()))
        return r.stdout
    return {"claims": claims, "worktrees": run("git", "-C", str(Path(m["roots"]["state_dir"]).parent / "repo"),
                                               "worktree", "list", "--porcelain"),
            "windows": run("tmux", "list-windows", "-t", "=" + m["session"], "-F", "#{window_name}")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gap", type=float, default=60)
    ap.add_argument("--max-wait", type=float, default=4 * 3600)
    args = ap.parse_args(argv)
    m, out, posts = json.loads(Path(args.manifest).read_text()), os.path.realpath(args.out), []
    hook = loopback(posts) if args.dry_run else os.environ.get("CAMPAIGN_WEBHOOK", "")
    merged = cr.guard.config.resolve_profile(m["production"]["path"])[0]
    live = merged.get("runtime", {}).get("options", {}).get("slack_webhook_env")
    problems = cr.guard.refusals(m) + ([] if "A26" in m["scenarios"] else ["scenario: A26 is not in the manifest"])
    problems += [] if any(out.startswith(r.rstrip(os.sep) + os.sep) for r in m["roots"].values()) else [
        "out: %s is outside the sandbox roots" % out]
    problems += [] if args.dry_run or hook.startswith("https://") else ["channel: CAMPAIGN_WEBHOOK is not an https URL"]
    problems += ["channel: CAMPAIGN_WEBHOOK is the live crew's webhook"] if live and os.environ.get(live) == hook else []
    sc = json.loads(Path(args.scenarios, "A26.json").read_text())
    problems += ["tool: %s is missing" % t for t in sc.get("requires", []) if not shutil.which(t)]
    for p in problems:
        print("refused: " + p)
    if problems:
        return 2
    st = m["roots"]["state_dir"]
    state, gh = os.path.join(st, m["repo"].replace("/", "__")), os.path.join(st, "gh")
    env = dict(cr.scenario_env(m, 0, dict(os.environ, CAMPAIGN_WEBHOOK=hook)), TMUX_TMPDIR=os.path.join(st, "tmux"))
    steps = sc["steps"]
    cut = next(i for i, s in enumerate(steps) if s["name"].startswith("resume"))
    doc = {"run_id": m["run_id"], "source_sha": m["source"]["sha"], "mode": "rehearsal" if args.dry_run else "attended",
           "evidence": not args.dry_run, "status": "FAIL", "steps": [], "unblocks": []}

    def save(reason=None, status="FAIL"):
        doc.update(status=status, reason=reason)
        Path(out + ".tmp").write_text(json.dumps(doc, indent=2) + "\n")
        os.replace(out + ".tmp", out)
        print("%s%s %s%s" % ("REHEARSAL (not evidence) " if args.dry_run else "", doc["mode"], status,
                             ": " + reason if reason else ""))
        return 0 if status == "PASS" else 1

    def run(batch):
        for step in batch:
            problems = cr.guard.refusals(m)
            if problems:
                return "refused: " + "; ".join(problems)
            unsafe = cr.lint.step_problems(step)
            if unsafe:
                return "step %s refused: %s" % (step["name"], "; ".join(unsafe))
            ok, event, rec = cr.run_step(step, m, 0, env)
            doc["steps"].append(rec)
            print(event)
            if not ok:
                return event
    bad = run(steps[:cut])
    if bad:
        return save(bad)
    with open(os.path.join(st, "org-a26.toml"), "a") as f:
        f.write(SLACK)
    code = secrets.token_hex(3)
    away(gh, state, "away", {"state": "away", "entry": "away-1463", "started": utc(), "until": None, "cap": None,
                             "quiet": False, "words": ""})
    Path(st, "ev.json").write_text(json.dumps({
        "id": "attended-" + code, "kind": "ask", "url": "https://example.invalid/%s/issues/1" % m["repo"],
        "title": "Attended run %s: receipt code %s" % (m["run_id"], code), "deadline": utc(time.time() + 86400),
        "default": "no action; type the code into the driver after resume"}))
    crew = [sys.executable, os.path.join(m["source"]["path"], "cli/mdstack")]
    project = ["--project", m["profile"]["path"], "--org-profile", os.path.join(st, "org-a26.toml")]
    subprocess.run(crew + ["notify", *project, "--event-file", os.path.join(st, "ev.json")], env=env, capture_output=True)
    sent = [json.loads(p.read_text()) for p in Path(state, "notifications").glob("*.json")]
    away(gh, state, "away-return", {"state": "returned", "entry": "away-1463", "returned": utc()})
    doc["channel"] = {"sent_at": utc(), "status": [r["status"] for r in sent], "loopback": args.dry_run}
    if [r["status"] for r in sent] != ["sent"]:
        return save("channel: delivery status %s" % doc["channel"]["status"])
    if subprocess.run(crew + ["spawn", "builder", "--issue", "3", *project, "--timeout", "10"], env=env,
                      capture_output=True).returncode:
        return save("work: builder #3 did not start before the sleep")
    Path(state, "status", "builder-3.status").write_text("ack: attended\n")  # existing work the sleep must keep
    try:
        before, t, mono = snapshot(m, state, env), time.time(), time.monotonic()
    except (OSError, RuntimeError) as e:
        return save(str(e))
    doc["before"] = {"utc": utc(t), "claims": sorted(before["claims"]),
                    "worktrees": before["worktrees"].count("worktree "), "windows": before["windows"].split()}
    save(status="WAITING")
    if args.dry_run:
        doc["sleep"] = {"slept": False, "label": "rehearsal: the machine was not slept"}
    else:
        print("owner: sleep this machine now (Apple menu > Sleep) for at least %ds, then wake it" % args.gap)
        while time.monotonic() - mono < args.max_wait and "sleep" not in doc:
            last = time.time()
            time.sleep(5)
            if time.time() - last > args.gap:
                doc["sleep"] = {"slept": True, "asleep_from": utc(last), "awake_at": utc(), "seconds": int(time.time() - last)}
                doc["unblocks"].append({"at": utc(), "what": "owner slept and woke the machine"})
        if "sleep" not in doc:
            return save("sleep: no wall-clock jump over %ds within %ds" % (args.gap, args.max_wait))
    doc["after"] = {"utc": utc()}
    try:
        changed = snapshot(m, state, env) != before
    except (OSError, RuntimeError) as e:
        return save(str(e))
    if changed:
        return save("preserved: claims, worktrees or tmux windows changed across the sleep")
    doc["preserved"] = True
    got = posts[0].split("receipt code ")[1][:6] if args.dry_run else input("owner: the receipt code on the channel: ")
    doc["channel"]["receipt"] = {"at": utc(), "match": got.strip() == code}
    if got.strip() != code:
        return save("channel: receipt code does not match the sent message")
    doc["unblocks"].append({"at": utc(), "what": "owner confirmed receipt of the sandbox channel message"})
    bad = run(steps[cut:])
    return save(bad) if bad else save(status="PASS")


if __name__ == "__main__":
    sys.exit(main())
