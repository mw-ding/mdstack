#!/usr/bin/env python3
"""Role post titles (docs/protocol.md §4 Marker conventions, #1946): one readable, bracket-free form.

    <emoji> <name> · <Pass> · <details>

for example `🔎 Vera · Verdict · round 1 @ abc1234 · 🔁 changes`. The title is display only: routing, polling,
dedupe and gates read the hidden crew:v1 marker. parse() reads a post's first line in this form or the old
`[<name>/<pass>] <details>` form, for report tooling over existing posts. Python 3 stdlib only.
"""
import re

SEP = " · "
OLD = re.compile(r"\[([^]/\s]+)/([\w-]+)\][ \t]*(.*)")
NEW = re.compile(r"(?:[^\w\s]\S* )?([^\s·]+) · ([A-Z][A-Za-z]*(?: [a-z]+)*)(?: · (.*))?$")


def label(pass_):
    """A pass slug as its title word: `merge-up` -> `Merge up`, `ci-fix` -> `CI fix`."""
    text = pass_.replace("-", " ")
    return "CI" + text[2:] if text.startswith("ci ") else text[:1].upper() + text[1:]


def title(name, pass_, *details, emoji=""):
    """The title line: emoji (omitted when empty), name, pass label, then each non-empty detail."""
    return SEP.join([emoji + " " + name if emoji else name, label(pass_)] + [d for d in details if d])


def parse(body):
    """(name, pass slug, details) from a post body's first line in the new or old form, else None."""
    line = (body or "").lstrip().split("\n", 1)[0]
    old = OLD.match(line)
    if old:
        return old.group(1), old.group(2), old.group(3)
    new = NEW.match(line)
    if new:
        return new.group(1), new.group(2).lower().replace(" ", "-"), new.group(3) or ""
    return None
