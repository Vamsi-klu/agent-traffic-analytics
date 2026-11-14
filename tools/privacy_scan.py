#!/usr/bin/env python3
"""Privacy scan of an Agent Cake data folder (GOAL S1, plan step S6.5): at every milestone, before every release, and
on the server during T13 and T14.

    python3 -I tools/privacy_scan.py <CAKE_HOME> [more files or folders, such as exported JSON]
            [--canary <text> ...] [--json]

Reads every file (tools/privacy/sources.py: each table cell of each database, each line of every replay chunk once
decompressed, each line of every log, JSON or other file) and looks for what Agent Cake must never keep
(tools/privacy/rules.py, tools/privacy/rules.json): IPv4 and IPv6 addresses other than its own listen addresses,
the canary strings given (what a test typed into the page), card numbers and the test card 4242 4242 4242 4242,
fields naming a pressed key, cookies, authorization headers and Bearer tokens, private key material, the value of the
folder's srv_secret, and e-mail addresses. Prints how many of each kind and where (at most max_locations of each),
what it skipped and why, and what it could not read: never what matched, nor the canaries. The folder's own path is
not printed either; locations are relative to it.

Exit code 0: everything was read and nothing found; 1: something found, or something could not be read; 2: wrong
arguments. Nothing is written anywhere.
"""
import argparse
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)  # run as a script under python3 -I, the repository root is not on sys.path

from agentcake import paths  # noqa: E402
from tools.privacy import rules as rules_module, sources  # noqa: E402

JSON_INDENT = 2
CONFIG_NAME = os.path.basename(paths.config_file())
SECRET_NAME = os.path.basename(paths.secret_file())


def parse(argv):
    parser = argparse.ArgumentParser(prog="privacy_scan.py", description="Privacy scan of an Agent Cake data folder.")
    parser.add_argument("home", help="the data folder (CAKE_HOME) to scan")
    parser.add_argument("more", nargs="*", help="more files or folders to scan, such as exported JSON")
    parser.add_argument("--canary", action="append", default=[], help="a string the test typed; may be repeated")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    return parser.parse_args(argv)


def scan(home, more=(), canaries=()):
    """{found, by_kind, where, read, skipped, unreadable} of the folder and the extra paths."""
    data = rules_module.load_rules()
    rules = rules_module.Rules(canaries, _secret(home), [_public_host(home)], data)
    by_kind, where, read = Counter(), {}, Counter()
    skipped, unreadable = [], []
    folders = [sources.Folder(home, data)] + [sources.Folder(path, data, name=_name(path)) for path in more]
    for folder in folders:
        for location, text in folder.texts():
            for kind in rules.find(text):
                by_kind[kind] += 1
                spots = where.setdefault(kind, [])
                if location not in spots and len(spots) < data["max_locations"]:
                    spots.append(location)
        read.update(folder.counts)
        skipped += folder.skipped
        unreadable += folder.unreadable
    return {"found": sum(by_kind.values()), "by_kind": {kind: by_kind[kind] for kind in rules_module.CATEGORIES},
            "where": where, "read": dict(read), "skipped": skipped, "unreadable": unreadable}


def report(result):
    """The result as the lines a person reads."""
    read = result["read"]
    lines = [f"privacy scan: {result['found']} found, {len(result['unreadable'])} unreadable",
             "read: " + ", ".join(f"{n:,} {what}" for what, n in sorted(read.items())) if read else "read: nothing",
             "found by kind:"]
    width = max(map(len, result["by_kind"]))
    lines += [f"  {kind.ljust(width)}  {n}" for kind, n in result["by_kind"].items()]
    if result["where"]:
        lines.append("where (the first locations of each kind; never what matched):")
        lines += [f"  {kind.ljust(width)}  {spot}" for kind, spots in result["where"].items() for spot in spots]
    if result["skipped"]:
        lines.append("skipped:")
        lines += [f"  {path}: {why}" for path, why in result["skipped"]]
    if result["unreadable"]:
        lines.append("unreadable (not checked, so not clean):")
        lines += [f"  {spot}: {why}" for spot, why in result["unreadable"]]
    return "\n".join(lines)


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    if not os.path.isdir(args.home):
        print(f"not a folder: {args.home}", file=sys.stderr)
        return 2
    missing = [path for path in args.more if not os.path.exists(path)]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    result = scan(args.home, args.more, args.canary)
    print(json.dumps(result, indent=JSON_INDENT) if args.json else report(result))
    return 0 if not result["found"] and not result["unreadable"] else 1


def _secret(home):
    """The folder's srv_secret value, to look for everywhere else; None without one. Read, never printed."""
    try:
        with open(os.path.join(home, SECRET_NAME), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _public_host(home):
    """The host of the folder's public_listen setting ("0.0.0.0:8080" -> "0.0.0.0"): also cake's own address."""
    try:
        with open(os.path.join(home, CONFIG_NAME), encoding="utf-8") as f:
            listen = json.load(f).get("public_listen") or ""
    except (OSError, ValueError):
        return None
    return listen.rpartition(":")[0].strip("[]") or None


def _name(path):
    return os.path.basename(os.path.normpath(path))


if __name__ == "__main__":
    sys.exit(main())
