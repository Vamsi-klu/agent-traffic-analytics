#!/usr/bin/env python3
"""Build a release of AgentCake (we build it, people download what we built).

    python3 -I tools/release.py refresh
        Refresh the lists that ship with AgentCake (needs the internet), in this working tree. Read the summary
        and `git diff`, run the tests, update the dates in THIRD_PARTY.md, and commit before building.

    python3 -I tools/release.py build [--out <folder>] [--tag v<version>]
        Build the release of the commit checked out (HEAD) into <folder> (default dist/, which must be empty):
        agentcake-<version>-py3-none-any.whl, agentcake.pyz, agentcake-<version>.tar.gz and SHA256SUMS. Uncommitted
        changes are left out (the summary lists them). --tag refuses a tag that is not v<version>.

The build needs git, Python 3.11 or newer and Node.js with npm (the local pages and esbuild come from `npm ci`); it
works offline when npm's cache has the packages. The same commit, built again with the same tools, gives the same
bytes. Nothing is published: .github/workflows/release.yml runs this command when a v<version> tag is pushed and
puts the files on a draft release, which the maintainer publishes. tools/releasing/__init__.py describes the steps.
"""
import argparse
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.releasing import build, bundled_lists, checksums  # noqa: E402  (the repository is put on sys.path first)
from tools.releasing.settings import ReleaseError, load  # noqa: E402


def print_summary(summary):
    when = datetime.datetime.fromtimestamp(summary["epoch"], datetime.timezone.utc).isoformat()
    print(f"release: agentcake {summary['version']} from commit {summary['commit']} ({when})")
    print(f"release: lists built {summary['lists_age_days']} day(s) before the commit; cake.js "
          f"{summary['cakejs_bytes'][0]} -> {summary['cakejs_bytes'][1]} bytes")
    pinned = ", ".join(f"{name} {count}" for name, count in summary["readme_pinned"].items())
    print(f"release: README's addresses on {summary['readme_branch']} named at {summary['tag']}: {pinned}")
    for path in summary["files"]:
        print(f"  {os.path.basename(path)}  {os.path.getsize(path)} bytes  sha256 {checksums.sha256_of(path)}")
    tools = ", ".join(f"{tool} {version}" for tool, version in summary["toolchain"].items())
    print(f"release: built with {tools}")
    for note in summary["notes"]:
        print(f"release: note: {note}")
    if summary["uncommitted"]:
        print("release: left out, not committed: " + ", ".join(summary["uncommitted"]))
    print(f"release: written to {summary['out_dir']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a release of AgentCake.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("refresh", help="refresh the shipped lists (online), to review and commit")
    build_command = commands.add_parser("build", help="build the release of HEAD into an empty folder")
    build_command.add_argument("--out", help="the folder to write into (default: dist/ in the repository)")
    build_command.add_argument("--tag", help="refuse unless this tag is v<version>")
    args = parser.parse_args(argv)
    settings = load()
    try:
        if args.command == "refresh":
            changed = bundled_lists.refresh(ROOT, settings)
            print("release: changed:\n" + changed if changed else "release: the lists did not change")
            return 0
        out_dir = os.path.abspath(args.out or os.path.join(ROOT, settings["out_dir"]))
        print_summary(build.build(ROOT, out_dir, tag=args.tag))
        return 0
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
