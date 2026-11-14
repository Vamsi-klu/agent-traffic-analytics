"""The third-party notices of the local pages in a release (since 0.4.0).

`npm run build` writes them into web/dist (web/scripts/notices.mjs; the file is web/notices.json "file") and
webapp.py copies web/dist into the package, so the wheel, the .pyz and the release folder all carry them. The build
itself lists every package it bundled and stops when one has no licence text; check() is the release's own look at
what was copied: it stops the release when the pages have no notices, when an entry the notices list has no licence
text, or when a package they list is not the version web/package-lock.json locks (they were not written from this
commit's packages).

The file starts with an index, one entry per line indented by two spaces ("name version (licence)", or a file's
name and its licence), before the first rule of "=" characters; each entry then has a heading line (the same
"name version"), a "License:" line and its licence and notice files, each under a "----- <file> -----" line.
"""
import os
import re

from tools.releasing.settings import ReleaseError, read_json, setting

INDEX_INDENT = "  "
RULE = re.compile(r"=+")
LOCKED_PACKAGE = "node_modules/"  # protocol: package-lock.json keys are node_modules/<name>, nested ones repeat it
TEXT_HEADING = "\n----- "


def index_titles(text):
    """The titles the index lists ("name version", or a file's name), in order."""
    titles = []
    for line in text.split("\n"):
        if RULE.fullmatch(line):
            break
        if line.startswith(INDEX_INDENT) and line.strip():
            titles.append(line.strip().split(" (", 1)[0])
    return titles


def locked_versions(lockfile):
    """{name: {versions}} of every package package-lock.json locks, nested ones included."""
    versions = {}
    for key, entry in read_json(lockfile).get("packages", {}).items():
        if LOCKED_PACKAGE in key:
            versions.setdefault(key.rsplit(LOCKED_PACKAGE, 1)[1], set()).add(entry.get("version"))
    return versions


def problems(text, locked):
    """What is wrong with notices text, one line each (empty when nothing is); locked: locked_versions()."""
    titles = index_titles(text)
    if not titles:
        return ["they list nothing"]
    found = []
    starts = {title: text.find(f"\n{title}\nLicense: ") for title in titles}
    ends = sorted(start for start in starts.values() if start >= 0) + [len(text)]
    for title, start in starts.items():
        if start < 0:
            found.append(f"{title} is in the index but has no entry")
            continue
        if TEXT_HEADING not in text[start:next(end for end in ends if end > start)]:
            found.append(f"{title} has no licence text")
        name, _, version = title.rpartition(" ")
        if name and version not in locked.get(name, ()):
            found.append(f"{title} is not a package web/package-lock.json locks at that version")
    return found


def check(tree, settings, pages):
    """Stop the release unless the compiled pages (pages: their folder in the package) hold sound notices."""
    rule = settings["web"]["notices"]
    name = setting(tree, rule, "which file holds the pages' third-party notices")
    path = os.path.join(pages, name)
    if not os.path.isfile(path):
        raise ReleaseError(f"the compiled pages have no {name}: `npm run build` writes it (web/scripts/notices.mjs, "
                           "added in web/vite.config.ts), and every release carries it")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    found = problems(text, locked_versions(os.path.join(tree, rule["lockfile"])))
    if found:
        raise ReleaseError(f"the compiled pages' {name}: " + "; ".join(found))
