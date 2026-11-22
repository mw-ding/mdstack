#!/usr/bin/env python3
"""Run dev/tests/*/test-*.py files in parallel and report per-file results (#613).

Usage:
  run-tests.py [-j N] [--slowest K] [--log-dir DIR] [FILE ...]

With no FILE, runs every `dev/tests/*/test-*.py`; a FILE given as a bare
`test-*.py` name runs that test from its module directory. Each file runs once, as
`python3 <file>` from the repo root, in its own process with its output
captured. Each file runs with `TMUX` and `TMUX_PANE` removed and `TMUX_TMPDIR`
set to a fresh private directory, removed when the file finishes, so a test's
bare `tmux` call can never reach the caller's server (#1156), and with
`MDSTACK_INTERNAL=1`, so `mdstack --project` is accepted as in a crew window (#1965). -j sets the
worker count (default: 1.5 times the CPU count, at most 8: files wait on
subprocesses, and CI's 4 CPUs sat about 13% idle at -j 4, #2082). Files named
in SLOW_FIRST start first, slowest first, so the longest files never start
last (#2082); the rest follow in path order. Files in SERIAL run one at a time after the parallel batch.
With no FILE, before any file starts, the runner writes bytecode for the repo's
Python files: `mdstack` turns off bytecode writing (`crew-remote.py`), so
otherwise every CLI call a test makes recompiles each module it loads (#2082).
The runner prints one line per file as it finishes (status and duration), then
the K slowest files, then the full output of every failing file, then a summary
line with the file and failure counts, the wall time, the worker count and the
CPU seconds the files used. A failing file's output is also written, as soon as it
finishes, to `<log-dir>/<file name>.log` (default: a fresh temp directory, kept),
named on its FAIL line. Exit code: 1 if any file fails, else 0.
CI runs the full suite this way in the `repo-guard` job of
`.github/workflows/ci.yml`. Python 3 standard library only.
"""
import argparse
import compileall
import concurrent.futures
import glob
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TESTS = os.path.join(ROOT, "dev", "tests")
MAX_DEFAULT_JOBS = 8
# Files that cannot share a machine with other tests (ports, cwd or global
# state). None found so far: every test uses temp dirs and ephemeral ports.
SERIAL = set()
# Longest files, slowest first, by their CI duration (#2082). A stale or
# missing name only changes start order.
SLOW_FIRST = (
    "test-crew-reviewer-pool.py", "test-crew-train.py", "test-crew-spawn.py", "test-crew-route.py",
    "test-crew-watch.py", "test-crew-lead.py", "test-crew-review-ready.py", "test-crew-bootstrap.py",
    "test-crew-schedule.py", "test-crew-restart.py", "test-crew-land.py", "test-crew-up.py",
    "test-crew-team.py", "test-crew-start.py", "test-crew-send.py", "test-crew-dequeue.py",
    "test-status-shared.py", "test-crew-upgrade.py", "test-check-repo.py", "test-crew-kill.py",
    "test-crew-remote.py",
)


def short_tmp_root():
    # tmux socket paths are length-limited and macOS TMPDIR is long.
    return "/tmp" if os.path.isdir("/tmp") else None


def precompile():
    for name in sorted(os.listdir(ROOT)):
        if not name.startswith(".") and os.path.isdir(os.path.join(ROOT, name)):
            compileall.compile_dir(os.path.join(ROOT, name), quiet=2)


def find(name):
    """A bare test name -> its dev/tests/<module>/ path; anything else as given."""
    if os.sep in name or os.path.exists(name):
        return name
    return next(iter(glob.glob(os.path.join(TESTS, "*", name))), name)


def run_one(path):
    start = time.monotonic()
    tmux_tmpdir = tempfile.mkdtemp(prefix="rt.", dir=short_tmp_root())
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
    env["TMUX_TMPDIR"] = tmux_tmpdir
    env["MDSTACK_INTERNAL"] = "1"  # tests pass --project as crew windows do; owner-shell tests unset it (#1965)
    try:
        proc = subprocess.run([sys.executable, path], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    finally:
        shutil.rmtree(tmux_tmpdir, ignore_errors=True)
    return path, proc.returncode, time.monotonic() - start, proc.stdout.decode(errors="replace")


def default_jobs():
    return min((os.cpu_count() or 1) * 3 // 2 or 1, MAX_DEFAULT_JOBS)


def start_order(files):
    """SLOW_FIRST files in its order, then the rest as given."""
    rank = {name: i for i, name in enumerate(SLOW_FIRST)}
    return sorted(files, key=lambda f: rank.get(os.path.basename(f), len(rank)))


def rel(path):
    return os.path.relpath(path, ROOT)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-j", "--jobs", type=int, default=default_jobs())
    ap.add_argument("--slowest", type=int, default=10, metavar="K")
    ap.add_argument("--log-dir", metavar="DIR")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args(argv)
    if args.jobs < 1:
        ap.error("-j must be at least 1")
    files = [os.path.abspath(f) for f in map(find, args.files)] or sorted(glob.glob(os.path.join(TESTS, "*", "test-*.py")))
    files = list(dict.fromkeys(files))
    for f in files:
        if not os.path.isfile(f):
            ap.error("no such test file: %s" % f)
    parallel = start_order([f for f in files if os.path.basename(f) not in SERIAL])
    serial = [f for f in files if os.path.basename(f) in SERIAL]

    if not args.files:
        precompile()
    results = []
    log_dir = args.log_dir

    def report(result):
        nonlocal log_dir
        path, code, secs, output = result
        results.append(result)
        line = "%-4s %7.1fs  %s" % ("ok" if code == 0 else "FAIL", secs, rel(path))
        if code != 0:
            if log_dir is None:
                log_dir = tempfile.mkdtemp(prefix="run-tests-logs.")
            os.makedirs(log_dir, exist_ok=True)
            log = os.path.join(log_dir, os.path.basename(path) + ".log")
            with open(log, "w") as fh:
                fh.write(output)
            line += "  log: %s" % log
        print(line, flush=True)

    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run_one, f) for f in parallel]):
            report(future.result())
    for f in serial:
        report(run_one(f))
    wall = time.monotonic() - start
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)

    print("\nslowest:")
    for path, _, secs, _ in sorted(results, key=lambda r: -r[2])[:args.slowest]:
        print("  %7.1fs  %s" % (secs, rel(path)))
    failed = sorted((r for r in results if r[1] != 0), key=lambda r: r[0])
    for path, code, _, output in failed:
        print("\n===== FAIL %s (exit %d) =====\n%s" % (rel(path), code, output.rstrip()))
    print("\n%d files, %d failed, %.1fs wall, -j %d, %.1fs cpu"
          % (len(results), len(failed), wall, args.jobs, usage.ru_utime + usage.ru_stime))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
