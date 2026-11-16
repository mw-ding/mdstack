#!/usr/bin/env python3
"""Triage clusters: group related but distinct open issues (docs/triage.md Clusters; #1298).

Reads the JSON that `gh issue list --state all --json number,url,state,title,body,labels,milestone,comments` prints
(repos concatenated). Pure computation: no network, no gh, no writes except --out. Python 3 standard library only.

Deterministic keys first, per open issue (pull requests and `triage:log` issues skipped):
  class:<slug>       the intake card's Failure class, first word (body, else a card-extracted comment, either title form)
  source:<o/r#n>     the card's Source issue, when it is not the issue itself
  depends:<o/r#n>    a `Depends on #n` target; the open target itself carries the key too
  component:<a/b>    the first two segments of each named path
A key that two or more open issues share is a candidate. Candidates run in that order, then those the prior sweep
already recorded, then by size and key; each issue joins at most one cluster, and a candidate with fewer than two
unplaced issues left forms none. The slug comes from the placing key alone, so it is stable across sweeps. The model
(--model) may add members, each with a one-line reason, and set a cluster's summary, band, milestone and tracking
proposal; earlier model members and settings carry over from --prior while the cluster stands.

A cluster proposal (a tracking issue, or `milestone:<title>` to move the whole cluster into that milestone) counts once
toward the noise cap whatever its size, and a changed milestone target is a new proposal. New proposals run by band,
size and slug while --cap-left lasts; the rest are skipped by cap.

Usage: triage-clusters.py --items FILE --sweep ID [--prior FILE] [--model FILE] [--cap-left 10] [--out FILE]
Exit codes: 0 OK, 2 usage or input error.
"""
import argparse
import importlib.util
import json
import os
import re
import sys

_spec = importlib.util.spec_from_file_location(
    "post_title", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core", "post-title.py"))
post_title = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post_title)

PATH = re.compile(r"(?<![\w/.])(?:[\w.-]+/)+[\w-]+\.\w+\b")
SOURCE = re.compile(r"([\w.-]+/[\w.-]+)(?:#|/issues/)(\d+)")
ORDER = ("class", "source", "depends", "component")
BANDS = ("P0", "P1", "P2", "P3")


def repo_of(item):
    m = re.search(r"([\w.-]+/[\w.-]+)/(?:issues|pull)/\d+", item.get("url", ""))
    return m[1] if m else ""


def ref(item):
    return "%s#%s" % (repo_of(item), item["number"])


def card(item, name):
    pattern = r"^(?:\*\*)?%s:(?:\*\*)?[ \t]*(.+?)[ \t]*$" % re.escape(name)
    texts = [item.get("body") or ""] + [c.get("body") or "" for c in item.get("comments") or []
                                        if (post_title.parse(c.get("body")) or ("", ""))[1] == "card-extracted"]
    for text in texts:
        m = re.search(pattern, text, re.M)
        if m and m[1].strip("*` ").lower() not in ("", "unknown", "none", "n/a"):
            return m[1].strip("*` ")
    return ""


def keys(item):
    """The deterministic cluster keys of one issue."""
    out, me, body = set(), ref(item), item.get("body") or ""
    if card(item, "Failure class"):
        out.add("class:" + card(item, "Failure class").split()[0].lower())
    m = SOURCE.search(card(item, "Source"))
    if m and "%s#%s" % (m[1], m[2]) != me:
        out.add("source:%s#%s" % (m[1].lower(), m[2]))
    for line in re.findall(r"(?im)^.*\bdepends on\b(.*)$", body):
        out |= {"depends:%s#%s" % (r or repo_of(item), n) for r, n in re.findall(r"([\w.-]+/[\w.-]+)?#(\d+)", line)}
    out |= {"component:" + "/".join(p.split("/")[:2]) for p in PATH.findall(body)}
    return out


def slug(key):
    return re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:40].rstrip("-")


def band(labels):
    return next((b for b in BANDS if b in labels), "P2")


def build(items, prior, model, cap_left):
    issues = {ref(i): i for i in items if (i.get("state") or "OPEN").upper() == "OPEN" and "/pull/" not in
              i.get("url", "") and "triage:log" not in {lab["name"] for lab in i.get("labels") or []}}
    have = {r: keys(i) for r, i in issues.items()}
    for r, ks in list(have.items()):
        for k in [k for k in ks if k.startswith("depends:")]:
            if k[len("depends:"):] in have:
                have[k[len("depends:"):]].add(k)
    by_key = {}
    for r, ks in have.items():
        for k in ks:
            by_key.setdefault(k, set()).add(r)
    before = {c["slug"]: c for c in prior.get("clusters", [])}
    order = sorted((k for k, rs in by_key.items() if len(rs) > 1),
                   key=lambda k: (ORDER.index(k.split(":")[0]), slug(k) not in before, -len(by_key[k]), k))
    placed, clusters = set(), {}
    for k in order:
        rs = by_key[k] - placed
        if len(rs) < 2:
            continue
        placed |= rs
        clusters[slug(k)] = {"slug": slug(k), "key": k, "members": [
            {"ref": r, "keys": sorted(x for x in have[r] if any(x in have[o] for o in rs - {r}))} for r in sorted(rs)]}
    notes = []
    named = {m.get("ref") for m in model.get("members") or []}
    added = [{**m, "cluster": c["slug"]} for c in before.values() for m in c.get("members", [])
             if m.get("by") == "model" and c["slug"] in clusters and m["ref"] in issues and m["ref"] not in named]
    for m in added + (model.get("members") or []):
        c, r, why = clusters.get(m.get("cluster", "")), m.get("ref"), " ".join(str(m.get("reason", "")).split())
        if not why or c is None or r not in issues:
            raise ValueError("model member %s needs a one-line reason, a current cluster and an open issue" % r)
        if r in placed:
            notes.append("model member %s skipped: already in a cluster" % r)
            continue
        placed.add(r)
        c["members"].append({"ref": r, "by": "model", "reason": why})
    picks = []
    for s, c in clusters.items():
        old, refs = before.get(s, {}), [m["ref"] for m in c["members"]]
        labels = [{lab["name"] for lab in issues[r].get("labels") or []} for r in refs]
        miles = {(issues[r].get("milestone") or {}).get("title") or "backlog" for r in refs}
        given = {**old.get("model", {}), **(model.get("clusters") or {}).get(s, {})}
        c.update(size=len(refs), summary=given.get("summary") or "%d open issues sharing %s" % (len(refs), c["key"]),
                 band=given.get("band") or band(set().union(*labels)),
                 milestone=given.get("milestone") or (miles.pop() if len(miles) == 1 else "backlog"),
                 tracking=bool(given.get("tracking")),
                 new=[r for r in refs if r not in {m["ref"] for m in old.get("members", [])}])
        if given:
            c["model"] = given
        wanted = ["tracking"] * c["tracking"] + ["milestone:" + c["milestone"]] * (
            c["milestone"] != "backlog" and any((issues[r].get("milestone") or {}).get("title") != c["milestone"]
                                                for r in refs))
        c["proposals"] = [p for p in wanted if p in old.get("proposals", [])]
        if [p for p in wanted if p not in c["proposals"]]:
            picks.append(c)
            c["wanted"] = wanted
    proposed, capped = [], []
    for c in sorted(picks, key=lambda c: (BANDS.index(c["band"]) if c["band"] in BANDS else 9, -c["size"], c["slug"])):
        (proposed if len(proposed) < cap_left else capped).append(c["slug"])
        if c["slug"] in proposed:
            c["proposals"] = c["wanted"]
        del c["wanted"]
    return {"clusters": sorted(clusters.values(), key=lambda c: c["slug"]), "proposed": proposed,
            "skipped_cap": capped, "notes": notes}


def render(result):
    out = ["clusters: %d (proposed %d, skipped: cap %d)" % (
        len(result["clusters"]), len(result["proposed"]), len(result["skipped_cap"]))]
    for c in result["clusters"]:
        state = "new" if c["slug"] in result["proposed"] else "skipped: cap" if c["slug"] in result[
            "skipped_cap"] else "open" if c["proposals"] else "none"
        out.append("- cluster:%s size=%d band=%s milestone=%s new=%d%s proposal=%s (%s) key=%s" % (
            c["slug"], c["size"], c["band"], c["milestone"], len(c["new"]),
            " (%s)" % ", ".join(c["new"]) if c["new"] else "", ",".join(c["proposals"]) or "-", state, c["key"]))
        out += ["  - %s: %s" % (m["ref"], "model: " + m["reason"] if m.get("by") else ", ".join(m["keys"]))
                for m in c["members"]]
    return out + result["notes"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--items", required=True)
    p.add_argument("--sweep", required=True)
    p.add_argument("--prior")
    p.add_argument("--model")
    p.add_argument("--cap-left", type=int, default=10)
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        result = build(load(a.items), load(a.prior) if a.prior else {}, load(a.model) if a.model else {},
                       max(a.cap_left, 0))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print("triage-clusters: unreadable input: %s" % e, file=sys.stderr)
        return 2
    result["sweep"] = a.sweep
    print("\n".join(render(result)))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
