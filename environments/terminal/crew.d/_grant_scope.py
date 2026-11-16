"""Conservative whole-clause recognition and exact GitHub scope reads for grant pruning (#1774).

Only top-level semicolons split clauses. Unknown prose, restrictions and history stay intact.
The decision log is the single local issue named by recognized source locators; other bindings are unsupported.
"""
import hashlib
import json
import re
from crew_shared import ownership_module

MILESTONE = r"M[0-9]+(?:\.[0-9]+)?"
VERSION = r"v?[0-9]+\.[0-9]+\.[0-9]+"
REF = re.compile(r"#([0-9]+) comment ([0-9]+)")
URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/issues/([0-9]+)#issuecomment-([0-9]+)")
WORDS = set("mdstack every PR PRs changes incl including the cut cuts minor and one after both finish as per release go "
            "template protocol authority gate contract F6 spec text recorded at head".lower().split())


def clauses(value):
    depth, start, result = 0, 0, []
    for i, char in enumerate(value):
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return [value]
        if char == ";" and depth == 0:
            result.append(value[start:i])
            start = i + 1
    return [value] if depth else result + [value[start:]]


def recognize(clause, repo):
    text = clause.strip()
    if re.search(r"§7|crew:sensitive|\b(all|standing|archiv\w*|unknown)\b", text, re.I):
        return None
    refs = [(repo, n, c) for n, c in REF.findall(text)] + URL.findall(text)
    if not refs or any(r != repo for r, _, _ in refs):
        return None
    locator = "(?:" + REF.pattern + "|" + URL.pattern + ")"
    text = re.sub(r"\(owner [0-9]{4}-[0-9]{2}-[0-9]{2}, " + locator + r"(?:, " + locator + r")*\)", "", text)
    text = URL.sub("", REF.sub("", text))
    milestones = re.findall(r"\b" + MILESTONE + r"\b", text)
    versions = re.findall(r"\b" + VERSION + r"\b", text)
    if not re.match(r"^(?:mdstack |every )?M[0-9]|^(?:the |one )?v?[0-9]+\.", text):
        return None
    if milestones and not versions and not re.search(r"\bPRs?\b|\bchanges\b", text):
        return None
    if versions and not re.search(r"\bcuts?\b", text):
        return None
    remainder = re.sub(r"\b(?:" + MILESTONE + "|" + VERSION + r")\b", "", text)
    if not milestones and not versions or re.search(r"[^a-zA-Z0-9\s,.()-]", remainder):
        return None
    if any(w.lower() not in WORDS for w in re.findall(r"[\w]+", remainder)):
        return None
    # A range, disjunction or an empty scope list has no proved finite boundary.
    if re.search(r"(?<![a-zA-Z])-(?![a-zA-Z])|\bor\b", remainder):
        return None
    return sorted(set(milestones)), sorted(set(versions)), sorted(set(refs))


def api(path, *flags, body=None):
    return ownership_module.github_api(path, *flags, body=body)


def classify(value, values):
    repo = values["repo.owner"] + "/" + values["repo.name"]
    rows = [{"clause": c, "remove": False, "reason": "standing, protected or unclassifiable", "links": [], "sources": []}
            for c in clauses(value)]
    try:
        if any(values["backends." + b + ".name"] != "github" for b in ("tracker", "release", "markers")):
            raise ValueError("unsupported decision-log/finished-scope bindings")
        for row in rows:
            scope = recognize(row["clause"], repo)
            if scope is None:
                continue
            milestones, versions, refs = scope
            if len({n for _, n, _ in refs}) != 1:
                row["reason"] = "ambiguous decision log"
                continue
            finished, facts = True, []
            for _, n, c in refs:
                source = api("repos/" + repo + "/issues/comments/" + c)
                link = "https://github.com/" + repo + "/issues/" + n + "#issuecomment-" + c
                if source["html_url"] != link or source["user"]["login"] not in values["identities.owners"] + [
                        values["identities.coordinator.gh_user"]] or not source["body"] or not re.search(
                            r"(?m)^— .+", source["body"]):
                    raise ValueError("source attribution/locator unreadable: " + link)
                row["links"].append(link)
                row["sources"].append(hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest())
                if re.search(r"\[[^]]+/(?:grant-prune|note)\].*archive|· (?:grant prune|note) · .*archive",
                             source["body"], re.I):  # either title form (#1946)
                    finished = False
                    facts.append("historical source")
            for name in milestones:
                pages = api("repos/" + repo + "/milestones?state=all&per_page=100", "--paginate", "--slurp")
                matches = [m for page in pages for m in page if m["title"] == name or m["title"].startswith(name + " ")]
                if len(matches) != 1 or matches[0]["state"] not in ("open", "closed"):
                    raise ValueError("milestone unreadable or ambiguous: " + name)
                finished &= matches[0]["state"] == "closed"
                facts.append(name + " " + matches[0]["state"])
                row["links"].append(matches[0]["html_url"])
            for version in versions:
                tag = version if version.startswith("v") else "v" + version
                release = api("repos/" + repo + "/releases/tags/" + tag)
                if release["tag_name"] != tag or not isinstance(release["draft"], bool) or not isinstance(
                        release["published_at"], (str, type(None))):
                    raise ValueError("release unreadable: " + version)
                published = not release["draft"] and bool(release["published_at"])
                finished &= published
                facts.append(version + (" published" if published else " unpublished"))
                row["links"].append(release["html_url"])
            row.update(remove=finished, reason=", ".join(facts), log=refs[0][1])
    except (OSError, ValueError, KeyError, TypeError) as e:
        for row in rows:
            row.update(remove=False, reason="keeping everything: " + str(e))
    return rows
