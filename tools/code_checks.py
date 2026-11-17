"""What the three code checks share (tools/check_hardcode.py, check_size.py and check_imports.py): where the
repository is, their settings in tools/limits.json and how they read their command line.

    limits(check)                                   the check's section of tools/limits.json
    folder_argument(argv, doc[, default, what])     the folder the command line names, or default (the repository)

The checks run as scripts (python3 -I tools/check_size.py), so each puts the repository's root on sys.path before it
imports this module.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMITS = os.path.join(ROOT, "tools", "limits.json")
REPOSITORY = "the repository folder (default: the folder above tools/)"


def limits(check):
    """The check's section of tools/limits.json: "check_size", "check_hardcode" or "check_imports"."""
    with open(LIMITS, encoding="utf-8") as f:
        return json.load(f)[check]


def folder_argument(argv, doc, default=ROOT, what=REPOSITORY):
    """The folder named on the command line (default when none is), read as any command reads its line: --help
    prints the usage (doc's first paragraph, the check's docstring), and a folder that is not there is a usage error
    (exit 2), not a check of nothing."""
    parser = argparse.ArgumentParser(description=doc.split("\n\n")[0])
    parser.add_argument("folder", nargs="?", default=default, help=what)
    folder = os.path.abspath(parser.parse_args(argv).folder)
    if not os.path.isdir(folder):
        parser.error(f"{folder} is not a folder")
    return folder
