#!/usr/bin/env python3
"""A31 campaign-history report from actual campaign PR and event records (#804).

`capture` records one campaign's crew PRs (closing issue in the milestone,
closed in the window) as metrics-refresh.py rows, plus the decision log's
`[Ash/decision]` comments in the window, into a JSON file. `report` renders
that file: counts and denominators per lane, timing and owner decisions.
Missing data is named as missing; nothing is estimated. Python 3 standard
library only. `capture` is read-only and relies on gh's own auth; `report`
makes no network call. Not run in CI.

Usage: campaign-report.py capture --repo OWNER/REPO --milestone N --since YYYY-MM-DD
                                  --until YYYY-MM-DD --decision-log N --out FILE
       campaign-report.py report --records FILE [--out FILE]
"""
import argparse
import importlib.util
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LANES = [("crew", "standard (`crew`)"), ("express", "express"), ("solo", "solo")]


def capture(repo, milestone, since, until, log):
    mr, mb = _load("metrics_refresh", "metrics-refresh.py"), _load("metrics_baseline", "metrics-baseline.py")
    prs = []
    query = "q=repo:%s is:pr is:closed closed:%s..%s" % (repo, since, until)
    for hit in mr.gh_json("search/issues", query, "per_page=100"):
        number = mb.closing_issue(hit.get("body"))
        if not number or not mr.is_crew_pr(hit.get("body"), [l["name"] for l in hit.get("labels", [])]):
            continue
        issue = mr.gh_json("repos/%s/issues/%d" % (repo, number))
        if (issue.get("milestone") or {}).get("number") != milestone:
            continue
        n = hit["number"]
        details = mr.gh_json("repos/%s/pulls/%d" % (repo, n))
        row = mr.build_row(repo, dict(details, head_sha=details["head"]["sha"]),
                           mr.gh_json("repos/%s/pulls/%d/reviews" % (repo, n), "per_page=100"),
                           mr.gh_json("repos/%s/issues/%d/events" % (repo, n), "per_page=100"),
                           mr.gh_json("repos/%s/pulls/%d/commits" % (repo, n), "per_page=100"),
                           rollups=mr.ci_rollups(repo, n))
        prs.append(dict(row, issue=number))
    decisions = [{"at": c["created_at"], "url": c["html_url"]}
                 for c in mr.gh_json("repos/%s/issues/%d/comments" % (repo, log), "since=%sT00:00:00Z" % since,
                                     "per_page=100")
                 if decision(c["body"]) and since <= c["created_at"][:10] <= until]
    return {"repo": repo, "milestone": milestone, "since": since, "until": until, "decision_log": log,
            "captured": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prs": sorted(prs, key=lambda r: r["pr"]), "decisions": decisions}


def decision(body):
    """A coordinator decision record: its `pass=steer cmd=decision` marker, or the old `[Ash/decision]` title (#1946)."""
    return body.startswith("[Ash/decision]") or any(
        {"role=coordinator", "pass=steer", "cmd=decision"} <= set(m.split())
        for m in re.findall(r"<!-- crew:v1 ([^>]*?) -->", body))


def median(values):
    return "n/a" if not values else "%g" % statistics.median(values)


def ratio(num, den, fmt="%.2f"):
    return fmt % (num / den) if den else "n/a"


def render(rec):
    prs, missing = rec["prs"], []
    lines = ["# A31 campaign-history report", "",
             "Crew PRs in `%s` whose closing issue is in milestone %d, closed %s to %s (UTC), and the "
             "`[Ash/decision]` records on #%d in that window. Captured %s; rendered by "
             "`scripts/campaign-report.py`." % (rec["repo"], rec["milestone"], rec["since"], rec["until"],
                                               rec["decision_log"], rec["captured"]), "",
             "## Counts per lane", "",
             "| Lane | PRs | Merged | Verdicts | Changes verdicts | Rounds / PR | Request-changes rate "
             "| Fix rounds | CI-fix rounds | Red-CI commits | Merge-ups | Selfgate reviews |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, label in LANES:
        g = [r for r in prs if r["lane"] == key]
        if not g:
            missing.append("No %s-lane PR in the records: its row is n/a, not zero." % key)
        s = {f: sum(r[f] for r in g) for f in ("verdicts", "changes_verdicts", "builder_fix_rounds",
                                               "ci_fix_rounds", "ci_red_rounds", "merge_ups", "selfgate_reviews")}
        cells = [sum(r["state"] == "merged" for r in g), s["verdicts"], s["changes_verdicts"],
                 ratio(s["verdicts"], len(g)), ratio(100 * s["changes_verdicts"], s["verdicts"], "%.1f%%"),
                 s["builder_fix_rounds"], s["ci_fix_rounds"], s["ci_red_rounds"], s["merge_ups"], s["selfgate_reviews"]]
        lines.append("| %s | %d | %s |" % (label, len(g), " | ".join(str(c) if g else "n/a" for c in cells)))
    lines += ["", "Total: %d PRs (%d merged). Rounds / PR divides verdicts by PRs; the request-changes rate "
              "divides changes verdicts by verdicts." % (len(prs), sum(r["state"] == "merged" for r in prs)), ""]
    opened = [r["opened_at"] for r in prs]
    merged = [r["merged_at"] for r in prs if r["merged_at"]]
    lines += ["## Timing", "", "| Measure | Value | PRs |", "|---|---|---|"]
    for field, label in (("open_to_merge_min", "Median open to merge (min)"),
                         ("dispatch_to_merge_min", "Median dispatch to merge (min)")):
        vals = [r[field] for r in prs if r[field] != ""]
        lines.append("| %s | %s | %d |" % (label, median(vals), len(vals)))
        if len(vals) < len(merged):
            missing.append("%d merged PRs have no `%s` (see docs/metrics/README.md, Fields)." % (
                len(merged) - len(vals), field))
    lines += ["| First PR opened | %s | |" % min(opened, default="n/a"),
              "| Last PR merged | %s | |" % max(merged, default="n/a"), "",
              "## Owner decisions", "",
              "%d `[Ash/decision]` records on #%d in the window, for any milestone: each records an owner call "
              "that unblocked or steered the crew, and the linked record says which. Only the time and "
              "link are stored, so no owner quote is copied." % (
                  len(rec["decisions"]), rec["decision_log"]), ""]
    lines += ["- %s [%s](%s)" % (d["at"], d["url"].rsplit("#", 1)[-1], d["url"]) for d in rec["decisions"]]
    if not rec["decisions"]:
        missing.append("No decision record in the window: owner unblocks are unknown, not zero.")
    unrun = sum(r["engine_runs"] == "" for r in prs)
    if unrun:
        missing.append("%d PRs have no recorded engine run." % unrun)
    missing.append("Token counts: no PR or event record carries them, so none are reported.")
    lines += ["", "## Missing data", ""] + ["- " + m for m in missing]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    for flag in ("--repo", "--since", "--until", "--out"):
        cap.add_argument(flag, required=True)
    cap.add_argument("--milestone", type=int, required=True)
    cap.add_argument("--decision-log", type=int, required=True)
    rep = sub.add_parser("report")
    rep.add_argument("--records", required=True)
    rep.add_argument("--out")
    args = ap.parse_args(argv)
    if args.cmd == "capture":
        rec = capture(args.repo, args.milestone, args.since, args.until, args.decision_log)
        with open(args.out, "w") as fh:
            json.dump(rec, fh, indent=1)
            fh.write("\n")
        print("%s: %d PRs, %d decisions -> %s" % (args.repo, len(rec["prs"]), len(rec["decisions"]), args.out),
              file=sys.stderr)
        return
    with open(args.records) as fh:
        text = render(json.load(fh))
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
