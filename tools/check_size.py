#!/usr/bin/env python3
"""Find source files longer than the line limit (one module does one job, like PostHog 1.0).

    python3 tools/check_size.py [repository folder]      (default: the folder above tools/)

Counts the lines of every source file (suffixes and limit in tools/limits.json, "check_size") in the repository,
leaving out the folder names in "skip_dir_names" and the paths in "exempt" (bundled third-party code, generated files,
the development repository's notes), each listed there with its reason. Prints one line per file over the limit and a count; the exit code is
0 when the count is 0.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)  # run as a script under python3 -I, the repository root is not on sys.path

from tools.code_checks import folder_argument, limits  # noqa: E402


def settings():
    return limits("check_size")


def source_files(root, rules):
    """Paths relative to root of the files the limit applies to."""
    for folder, dirs, files in os.walk(root):
        rel_folder = os.path.relpath(folder, root)
        dirs[:] = sorted(d for d in dirs if d not in rules["skip_dir_names"]
                         and os.path.normpath(os.path.join(rel_folder, d)) not in rules["exempt"])
        for name in sorted(files):
            rel = os.path.normpath(os.path.join(rel_folder, name))
            if name.endswith(tuple(rules["suffixes"])) and rel not in rules["exempt"]:
                yield rel


def oversized(root, rules=None):
    """(path, lines) of each source file longer than max_lines."""
    rules = rules or settings()
    found = []
    for rel in source_files(root, rules):
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            lines = sum(1 for _ in f)
        if lines > rules["max_lines"]:
            found.append((rel, lines))
    return found


def main(argv):
    root = folder_argument(argv, __doc__)
    rules = settings()
    found = oversized(root, rules)
    for rel, lines in found:
        print(f"{rel}: {lines} lines (limit {rules['max_lines']}): split it into modules that each do one job")
    print(f"check_size: {len(found)} file(s) over {rules['max_lines']} lines")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
