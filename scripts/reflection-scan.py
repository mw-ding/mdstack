#!/usr/bin/env python3
"""Reflection evidence scan: a deterministic JSON evidence index for one window (M39 R2, #1518; #1403).

Reads, offline: forge snapshots (`--forge`, repeatable: the JSON of `gh issue list` or `gh pr list --state all
--json number,url,state,title,body,labels,createdAt,closedAt,comments`), lessons (`docs/lessons/*.md`) and the
findings buffer (`docs/findings/buffer.md`) at a named `--sha` of the `--root` git repo, owner decisions
(`--decisions`, the same JSON shape for the decision-log issue) and sanitized runtime observations
(`--observations`, JSON lines `{"at", "ref", "kind", "note"}`). Python 3 standard library only; no network, no gh;
git only reads objects. It writes nothing but stdout and --out, and prints evidence, never a conclusion.

Selection: every issue or pull request opened, closed or corrected (a signed comment whose title details start
`correction`, in either title form) in [--since, --until), whatever its state, milestone or labels; `triage:log`
issues are skipped. Lessons and findings entries dated in the window are selected; older ones that name a selected
incident or item stay as `context`. A missing `docs/lessons/` at the SHA is missing, not an empty store.

Incidents: a card (an item with a Failure class) and its fix chain (a triage title `... accepted -> #n`, a
`Closes #n` in a body, a `(#n)` in a title) are one incident. A card's sites are its Source and the refs its Summary
names: cards of one class on one site are one incident however many report it, and a card naming two or more sites
reports one incident per site. A site is listed, never merged, so distinct failures on one PR stay distinct. Keys
are triage-clusters.py's (class, source, depends, component), computed by that script's own `keys()`; triage's
open-only selection is not changed. Selected items with no card stay under `items`.

Evidence states: `reported` (a body, a signed note or triage line), `confirmed` (a signed research finding, a triage
acceptance, a correction, an applied/encoded/fixed lesson or finding) and `superseded` (a reported card body after a
later research finding on that item, the same bot's latest earlier line after its correction, a superseded lesson).

An input not given, not found or unreadable at the SHA is listed under `missing` and its section is null, never an
empty list or a zero. A cited site or fix ref absent from every snapshot is listed under its incident's `unresolved`.

Usage: reflection-scan.py --since DATE --until DATE [--forge FILE]... [--root DIR --sha SHA] [--decisions FILE]
           [--observations FILE] [--out FILE]
Exit codes: 0 index written, 2 usage or malformed input.
"""
import argparse
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys

spec = importlib.util.spec_from_file_location(
    "triage_clusters", os.path.join(os.path.dirname(os.path.abspath(__file__)), "triage-clusters.py"))
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)


def signed(body):
    """A signed post's title as (None, name, pass, details), indexable like a match, in either title form (#1946)."""
    title = tc.post_title.parse(body)
    return (None,) + title if title else None


REF = re.compile(r"(?:([\w.-]+/[\w.-]+)(?:/issues/|/pull/|#)|(?<![\w/&])#)(\d+)\b")
ARROW = re.compile(r"(?:→|->)\s*((?:[\w.-]+/[\w.-]+)?#\d+)")
CLOSES = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+((?:[\w.-]+/[\w.-]+)?#\d+)")
SUMMARY = re.compile(r"(?im)^[-*\s]*(?:\*\*)?Summary:(?:\*\*)?\s*(.+)$")
FIELD = re.compile(r"^- \*\*([^*:]+):\*\*\s*(.*)$")


def when(text):
    text = str(text).strip().replace("Z", "+00:00")
    t = datetime.datetime.fromisoformat(text if "T" in text else text[:10] + "T00:00:00+00:00")
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def refs(text, repo):
    return sorted({"%s#%s" % ((r or repo).lower(), n) for r, n in REF.findall(text or "")})


def correction(m):
    return bool(m) and m[3].lower().startswith("correction")


def fixes(item, repo):
    """Refs in this item's fix chain: a triage acceptance, a closing ref in the body, a `(#n)` in the title."""
    out = set()
    for c in item.get("comments") or []:
        m = signed(c.get("body"))
        if m and m[2] == "triage" and "accepted" in m[3]:
            out |= {x for a in ARROW.findall(m[3]) for x in refs(a, repo)}
    for x in CLOSES.findall(item.get("body") or "") + re.findall(r"\((#\d+)\)", item.get("title") or ""):
        out |= set(refs(x, repo))
    return out - {tc.ref(item).lower()}


def sites(item, repo):
    """Where a card's failure happened: its Source and the occurrences its Summary names, never the card."""
    m = SUMMARY.search(item.get("body") or "")
    found = set(refs(tc.card(item, "Source"), repo) + (refs(m[1], repo) if m else []))
    return sorted(found - {tc.ref(item).lower()})


def order(node):
    head, tail = node.split("#", 1)
    return head, int(tail.split("~")[0]), node


def evidence(item):
    """Evidence rows of one item, oldest first, with superseded marks applied."""
    rows = [{"ref": tc.ref(item).lower(), "kind": "card" if tc.card(item, "Failure class") else "body",
             "state": "reported", "at": item.get("createdAt"), "url": item.get("url")}]
    for c in sorted(item.get("comments") or [], key=lambda c: c.get("createdAt") or ""):
        m = signed(c.get("body"))
        corr = correction(m)
        if not m or m[2] not in ("research", "triage", "note") and not corr:
            continue
        state = "confirmed" if m[2] == "research" or corr or m[2] == "triage" and "accepted" in m[3] else "reported"
        row = {"ref": rows[0]["ref"], "kind": "correction" if corr else m[2], "by": m[1], "state": state,
               "at": c.get("createdAt"), "url": c.get("url"), "line": m[3][:160]}
        if m[2] == "research":
            for r in rows:
                if r["kind"] == "card" and r["state"] == "reported":
                    r.update(state="superseded", superseded_by=row["url"])
        if corr:
            prior = [r for r in rows if r.get("by") == m[1]]
            if prior:
                prior[-1].update(state="superseded", superseded_by=row["url"])
        rows.append(row)
    return rows


def git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, check=True).stdout


def entries(text, path, repo):
    """Lesson or findings entries: a heading followed by `- **Field:** value` bullets with a Date."""
    out, cur = [], None
    for line in text.splitlines() + ["# end"]:
        if line.startswith("#"):
            if cur and "date" in cur["fields"]:
                out.append(cur)
            cur = {"path": path, "title": line.lstrip("# ").strip(), "fields": {}}
            last = None
        elif cur is not None and FIELD.match(line):
            last = FIELD.match(line)[1].strip().lower()
            cur["fields"][last] = FIELD.match(line)[2]
        elif cur is not None and last and line.startswith("  "):
            cur["fields"][last] += " " + line.strip()
    for e in out:
        f = e.pop("fields")
        word = ((f.get("status") or "").split() or [""])[0].strip("`*:,.").lower()
        e.update(date=f["date"][:10], status=word, refs=refs(" ".join(f.values()), repo),
                 state="superseded" if word == "superseded" else
                 "confirmed" if word in ("applied", "encoded", "fixed") else "reported")
    return out


def scan(a):
    since, until = when(a.since), when(a.until)
    inside = lambda t: bool(t) and since <= when(t) < until  # noqa: E731
    missing, inputs, items, loaded = [], {}, [], False
    for path in a.forge or []:
        if os.path.exists(path):
            items, loaded = items + load(path), True
        else:
            missing.append("forge %s: not found" % path)
    if not a.forge:
        missing.append("forge: not provided")
    inputs["forge"] = len(items) if loaded else None
    repos = {tc.repo_of(i).lower() for i in items}
    repo = repos.pop() if len(repos) == 1 else ""
    by_ref = {tc.ref(i).lower(): i for i in items
              if "triage:log" not in {lab["name"] for lab in i.get("labels") or []}}

    why = {}
    for r, i in by_ref.items():
        corrected = any(correction(signed(c.get("body"))) and inside(c.get("createdAt"))
                        for c in i.get("comments") or [])
        tags = [t for t, ok in (("opened", inside(i.get("createdAt"))), ("closed", inside(i.get("closedAt"))),
                                ("corrected", corrected)) if ok]
        if tags:
            why[r] = tags

    parent = {}
    find = lambda x: x if parent.setdefault(x, x) == x else find(parent[x])  # noqa: E731
    cards = {r for r, i in by_ref.items() if tc.card(i, "Failure class")}
    multi = {}
    for r, i in by_ref.items():
        find(r)
        for o in fixes(i, repo):
            parent[find(o)] = find(r)
        if r in cards:
            cls = tc.card(i, "Failure class").split()[0].lower()
            at = ["%s~%s" % (x, cls) for x in sites(i, repo)]
            if len(at) == 1:
                parent[find(at[0])] = find(r)
            elif at:
                multi[r] = at
                for v in at:
                    find(v)
    groups = {}
    for x in list(parent):
        groups.setdefault(find(x), set()).add(x)
    shared = {}
    for g, members in groups.items():
        for m in members & set(multi):
            for v in multi[m]:
                shared.setdefault(find(v), set()).add(g)
    incidents, placed = [], set()
    for g, members in groups.items():
        virt = {x for x in members if "~" in x}
        if not (virt or members & cards) or members & set(multi) and not virt:
            continue
        own = members - virt
        reporters = {x for s in shared.get(g, ()) for x in groups[s] if "~" not in x} - own
        site = {v.split("~")[0] for v in virt}
        known = sorted(r for r in own | reporters if r in by_ref)
        selected = {r: why[r] for r in sorted(own | reporters | site) if r in why}
        if not selected:
            continue
        placed |= own | reporters | site
        incidents.append({
            "id": "incident:" + min(virt or own, key=order), "refs": sorted(own, key=order),
            "reported_by": sorted(reporters, key=order), "sites": sorted(site, key=order), "selected": selected,
            "keys": sorted(set().union(*(tc.keys(by_ref[r]) for r in known))),
            "unresolved": sorted((r for r in own | site if r not in by_ref), key=order),
            "evidence": sorted((e for r in known for e in evidence(by_ref[r])),
                               key=lambda e: (e["at"] or "", e["ref"]))})
    incidents.sort(key=lambda i: order(i["id"].split(":", 1)[1]))
    owner = {}
    for i in incidents:
        for r in i["refs"] + i["reported_by"] + i["sites"]:
            owner.setdefault(r, set()).add(i["id"])
    keyed = {}
    for i in incidents:
        for k in i["keys"]:
            keyed.setdefault(k, []).append(i["id"])

    free = {r: why[r] for r in sorted(why, key=order) if r not in placed}

    def linked(refs_):
        return sorted(set().union(*(owner.get(r, set()) for r in refs_)))

    def touched(refs_):
        return sorted((r for r in set(refs_) if r in free), key=order)

    stores = {}
    for name, paths in (("lessons", None), ("findings", ["docs/findings/buffer.md"])):
        if not a.sha:
            missing.append("%s: no --sha" % name)
            stores[name] = None
            continue
        try:
            if paths is None:
                git(a.root, "cat-file", "-e", "%s:docs/lessons" % a.sha)
                paths = [p for p in git(a.root, "ls-tree", "--name-only", a.sha, "docs/lessons/").split()
                         if p.endswith(".md") and not p.endswith("README.md")]
            rows = [e for p in paths for e in entries(git(a.root, "show", "%s:%s" % (a.sha, p)), p, repo)]
        except (OSError, subprocess.CalledProcessError):
            missing.append("%s: unreadable at %s" % (name, a.sha))
            stores[name] = None
            continue
        for e in rows:
            e.update(incidents=linked(e["refs"]), items=touched(e["refs"]), context=not inside(e["date"]))
        stores[name] = [e for e in rows if not e["context"] or e["incidents"] or e["items"]]

    decisions = None
    if not a.decisions:
        missing.append("decisions: not provided")
    elif not os.path.exists(a.decisions):
        missing.append("decisions %s: not found" % a.decisions)
    else:
        decisions = []
        for i in load(a.decisions):
            for c in i.get("comments") or []:
                rs = refs(c.get("body"), repo)
                if inside(c.get("createdAt")) or linked(rs) or touched(rs):
                    decisions.append({"url": c.get("url"), "at": c.get("createdAt"), "incidents": linked(rs),
                                      "items": touched(rs),
                                      "line": (c.get("body") or "").split("\n")[0][:160]})
    observations = None
    if not a.observations:
        missing.append("observations: not provided")
    elif not os.path.exists(a.observations):
        missing.append("observations %s: not found" % a.observations)
    else:
        with open(a.observations, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        observations = [{**o, "incidents": linked(refs(o.get("ref"), repo)), "items": touched(refs(o.get("ref"), repo))}
                        for o in rows if inside(o.get("at"))]

    for name in ("lessons", "findings"):
        inputs[name] = None if stores[name] is None else len(stores[name])
    inputs["decisions"] = None if decisions is None else len(decisions)
    inputs["observations"] = None if observations is None else len(observations)
    return {"window": {"since": a.since, "until": a.until}, "sha": a.sha, "inputs": inputs, "missing": missing,
            "incidents": incidents, "items": free,
            "keys": keyed, "lessons": stores["lessons"], "findings": stores["findings"],
            "decisions": decisions, "observations": observations}


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("%s: expected a JSON list" % path)
    return data


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", required=True)
    p.add_argument("--until", required=True)
    p.add_argument("--forge", action="append")
    p.add_argument("--root", default=".")
    p.add_argument("--sha")
    p.add_argument("--decisions")
    p.add_argument("--observations")
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        index = scan(a)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print("reflection-scan: unreadable input: %s" % e, file=sys.stderr)
        return 2
    text = json.dumps(index, sort_keys=True, separators=(",", ":"))
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
