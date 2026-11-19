# Security policy

## Reporting a vulnerability

Report security issues through GitHub private vulnerability reporting:
open the repository's **Security** tab and choose **Report a vulnerability**,
or go to <https://github.com/mw-ding/mdstack/security/advisories/new>.

Use that route only. Do not open a public issue, pull request or discussion
for a suspected vulnerability, and do not post exploit details anywhere
public before a fix is released.

Include what you can:

- the affected file, script or command, and the mdstack version
  (`mdstack --version`) or commit;
- steps to reproduce and the impact you expect;
- whether the issue is already public anywhere.

Never paste live tokens, keys or private data into a report; describe the
credential by type instead.

## What happens next

The maintainers acknowledge the report in the advisory thread, agree on a
fix and a disclosure date with you there, and credit you in the advisory
unless you ask otherwise.

## Supported versions

Fixes go into the next release from `main`. Only the newest release on the
[releases page](https://github.com/mw-ding/mdstack/releases) receives
security fixes.
