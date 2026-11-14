#!/usr/bin/env python3
"""Refresh the lists that ship with Agent Cake (S3.1, D23), as PostHog's refresh_bot_ip_ranges.py does for its own.

    python3 -I tools/build_lists.py        (from the cake folder; needs the internet)

Fetches every source in agentcake/data/lists/sources.json (botscent, PostHog and ai.robots.txt at their current
commits, the operators' published address lists, the Web Bot Auth key directories) and rewrites names.json,
ip_ranges.json, signers.json and keys.json in that folder. Then: read the summary below (disagreements between
sources and skipped names deserve a decision in sources.json), review the diff, run the tests, update the dates and
commits in THIRD_PARTY.md, and commit. Nothing is written when any source fails.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentcake.detect import lists, lists_build  # noqa: E402


def summary(files):
    names = files["names.json"]
    lines = [f"built {names['built']}"]
    for source, about in names["sources"].items():
        detail = ", ".join(f"{k} {v if not isinstance(v, (list, dict)) else len(v)}" for k, v in about.items()
                           if k not in ("repo", "url", "license"))
        lines.append(f"  {source}: {detail}")
    lines.append(f"names {len(names['names'])}, hints {len(names['hints'])}")
    for item in names["disagreements"]:
        state = f"settled: {item['settled']}" if item["settled"] else "NOT SETTLED: add an override in sources.json"
        lines.append(f"  disagreement {item['id']}: {item['kinds']} -> {item['chosen']} ({state})")
    for raw, reason in names["sources"]["ai-robots-txt"]["skipped"].items():
        lines.append(f"  ai.robots.txt skipped {raw!r}: {reason}")
    for entry in files["ip_ranges.json"]["ranges"]:
        lines.append(f"range {entry['id']} ({entry['kind']}): {len(entry['v4'])} v4, {len(entry['v6'])} v6 blocks")
    for host, keys in files["keys.json"]["directories"].items():
        lines.append(f"signer {host}: {len(keys)} keys")
    return "\n".join(lines)


def main():
    sources, kinds = lists_build.read_recipe()
    try:
        previous = lists.Lists.load(lists.BUNDLED_DIR)
    except lists.ListsError:
        previous = None
    try:
        files = lists_build.build(sources, kinds, lists_build.http_fetch(sources["fetch"]), previous,
                                  datetime.datetime.now(datetime.timezone.utc))
    except lists_build.BuildError as error:
        print(f"nothing written: {error}", file=sys.stderr)
        return 1
    lists_build.write_files(files, lists.BUNDLED_DIR)
    print(summary(files))
    for name in files:
        path = os.path.join(lists.BUNDLED_DIR, name)
        print(f"wrote {os.path.relpath(path)} ({os.path.getsize(path)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
