#!/usr/bin/env python3
"""GitHub status connector (docs/specs/shared-status.md §7, #1313): the bundled binding of the optional status
concern's read-records and publish-record operations, run through templates/backends/github.toml [status].

Usage: status.py read-records < request.json
       status.py publish-record < request.json
       status.py --help

Each operation reads one JSON request on stdin and prints one JSON object on stdout, exit 0; exit 2 on a malformed
request. The destination is an issue URL https://github.com/<owner>/<repo>/issues/<n>.

read-records {destination}: never writes. Prints {login, issue, complete, comments}: login is the authenticated
account (null when unreadable); issue is open, closed, missing or unknown; comments lists {id, author, body, url}
for every page read, page by page until an empty page; complete is false when the issue or a page did not read.

publish-record {destination, publisher, op, comment_id, body}: verifies the authenticated account equals publisher,
then sends one request: op create POSTs a comment on the issue (only register asks for it), op update PATCHes
comment comment_id. It never retries, never edits the issue body, another comment or a label, and never deletes.
Prints {outcome, comment_id, error}, outcome exactly one of: applied (a success response naming the comment),
rejected (an HTTP 4xx response: the request was not applied), not-sent (it failed before any request byte left:
no account, another account, no gh) or uncertain (anything else: a timeout, a lost connection, a 5xx, an
unreadable success). Python 3 stdlib only.
"""
import json
import re
import subprocess
import sys

DESTINATION = re.compile(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)/issues/([1-9][0-9]*)")
HTTP = re.compile(r"\(HTTP ([0-9]{3})\)")
TIMEOUT = 60
PER_PAGE = 100


def gh(args, body=None):
    """(exit code, stdout, stderr) of one gh call; OSError when gh cannot start, TimeoutExpired on a timeout."""
    r = subprocess.run(["gh", *args], input=body, capture_output=True, text=True, timeout=TIMEOUT)
    return r.returncode, r.stdout, r.stderr


def login():
    try:
        code, out, _ = gh(["api", "user", "--jq", ".login"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (out.strip() or None) if code == 0 else None


def read_records(req):
    owner, repo, number = DESTINATION.fullmatch(req["destination"]).groups()
    out = {"login": login(), "issue": "unknown", "complete": False, "comments": []}
    try:
        code, text, err = gh(["api", "repos/%s/%s/issues/%s" % (owner, repo, number)])
        if code:
            out["issue"] = "missing" if "(HTTP 404)" in err or "(HTTP 410)" in err else "unknown"
            return out
        issue = json.loads(text)
        out["issue"] = "missing" if "pull_request" in issue else "closed" if issue.get("state") == "closed" else "open"
        page = 1
        while True:
            code, text, _ = gh(["api", "repos/%s/%s/issues/%s/comments?per_page=%d&page=%d"
                                % (owner, repo, number, PER_PAGE, page)])
            if code:
                return out
            found = json.loads(text)
            if not isinstance(found, list):
                return out
            if not found:
                break
            for c in found:
                out["comments"].append({"id": str(c["id"]), "author": (c.get("user") or {}).get("login"),
                                        "body": c.get("body") or "",
                                        "url": c.get("html_url") or "%s#issuecomment-%s" % (req["destination"], c["id"])})
            page += 1
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return out
    out["complete"] = True
    return out


def publish_record(req):
    owner, repo, number = DESTINATION.fullmatch(req["destination"]).groups()
    account = login()
    if account is None:
        return {"outcome": "not-sent", "comment_id": None, "error": "authenticated account unreadable"}
    if account.lower() != req["publisher"].lower():
        return {"outcome": "not-sent", "comment_id": None,
                "error": "authenticated as %s, not the publisher %s" % (account, req["publisher"])}
    if req["op"] == "create":
        args = ["api", "-X", "POST", "repos/%s/%s/issues/%s/comments" % (owner, repo, number), "--input", "-"]
    else:
        args = ["api", "-X", "PATCH", "repos/%s/%s/issues/comments/%s" % (owner, repo, req["comment_id"]),
                "--input", "-"]
    try:
        code, text, err = gh(args, json.dumps({"body": req["body"]}))
    except OSError as e:
        return {"outcome": "not-sent", "comment_id": None, "error": "gh cannot start (%s)" % e.strerror}
    except subprocess.TimeoutExpired:
        return {"outcome": "uncertain", "comment_id": None, "error": "timed out after %ds" % TIMEOUT}
    if code:
        status = HTTP.search(err)
        if status and status.group(1).startswith("4"):
            return {"outcome": "rejected", "comment_id": None, "error": "HTTP %s" % status.group(1)}
        return {"outcome": "uncertain", "comment_id": None,
                "error": "HTTP %s" % status.group(1) if status else "no response status (%s)" % err.strip()[:200]}
    try:
        cid = str(json.loads(text)["id"])
    except (ValueError, KeyError, TypeError):
        return {"outcome": "uncertain", "comment_id": None, "error": "success response names no comment"}
    if req["op"] == "update" and cid != str(req["comment_id"]):
        return {"outcome": "uncertain", "comment_id": None, "error": "success response names another comment"}
    return {"outcome": "applied", "comment_id": cid, "error": None}


def request(op):
    """The stdin request for op, else None when malformed."""
    try:
        req = json.loads(sys.stdin.read())
    except ValueError:
        return None
    if not isinstance(req, dict) or not isinstance(req.get("destination"), str) or \
            not DESTINATION.fullmatch(req["destination"]):
        return None
    if op == "publish-record" and not (
            isinstance(req.get("publisher"), str) and req["publisher"] and isinstance(req.get("body"), str)
            and (req.get("op") == "create" or req.get("op") == "update" and isinstance(req.get("comment_id"), str)
                 and req["comment_id"].isdigit())):
        return None
    return req


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--help"], ["-h"]):
        print(__doc__)
        return 0
    if len(argv) != 1 or argv[0] not in ("read-records", "publish-record"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    req = request(argv[0])
    if req is None:
        print("status connector: malformed %s request" % argv[0], file=sys.stderr)
        return 2
    print(json.dumps(read_records(req) if argv[0] == "read-records" else publish_record(req)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
