"""Repo binding for land, land-lock, train and stack (docs/specs/team.md §9.5, #1859).

One comparison closes every refusal class: each source a land acts on names a repo, and every source must name the
selected project's canonical repo before any mutation. Sources are a persisted record's `context` (train,
delegation, land or stack intent, land lock: its team must match too), an independent backend read's URL (a member,
its verdict, permission, control and hold records) and a member's `owner/name#` qualifier. A missing or unreadable
source refuses, except an unqualified member and, in a one-repo config, a legacy record written before #1859: there
the selected state is the only project. Gate satisfaction, actors and fail-open paths are unchanged."""
import re
from crew_shared import work_context

URL = re.compile(r"https://[^/\s]+/([^/\s]+)/([^/\s]+)/(?:pull|issues)/\d+")
MEMBER = re.compile(r"(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#)?(\d+)")


def context(project, values):
    """The {team, project, repo} stamp a land-side record carries."""
    return work_context(project, values)


def member(text):
    """`N` or `owner/name#N` -> (lowercase qualifier or None, N); ValueError otherwise."""
    m = MEMBER.fullmatch(text)
    if not m:
        raise ValueError("member %r is not <n> or <owner>/<name>#<n>" % text)
    return (m[1].lower() if m[1] else None), int(m[2])


def foreign(ctx, team, records=(), urls=(), repos=()):
    """Why acting on these sources would leave ctx's repo, or None. records: (what, persisted record or None for none
    on file); urls: (what, an independent read's URL); repos: (what, a member's qualifier or None). team: the profile
    is a team file, where a record without context refuses."""
    named = []
    for what, rec in records:
        if rec is None:
            continue
        env = rec.get("context") if isinstance(rec, dict) else None
        if env is None and not team and isinstance(rec, dict):
            continue  # a one-repo legacy record: the selected state is its only project
        found = (env.get("team"), env.get("repo")) if isinstance(env, dict) else None
        named.append((what, found, True))
    for what, url in urls:
        m = URL.fullmatch(url) if isinstance(url, str) else None
        named.append((what, (None, ("%s/%s" % m.groups()).lower()) if m else None, False))
    named += [(what, (None, repo), False) for what, repo in repos if repo is not None]
    for what, found, with_team in named:
        if not found or not isinstance(found[1], str):
            return "%s names no readable repo context" % what
        if found[1].lower() != ctx["repo"] or (with_team and found[0] != ctx["team"]):
            return "%s is %s%s, not %s%s" % (what, found[1], " in team %s" % found[0] if with_team else "",
                                            ctx["repo"], " in team %s" % ctx["team"] if with_team else "")
    return None


def off_repo(slug, urls):
    """Why an independent read is not the selected repo `owner/name`'s, or None; urls: (what, URL)."""
    return foreign({"repo": slug.lower(), "team": None}, False, urls=urls)
