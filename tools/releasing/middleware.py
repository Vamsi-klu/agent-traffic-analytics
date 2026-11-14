"""The sites' middleware in the release (S6.4): edge/ copied into the package, so every way of installing has it.

edge/ holds the server half for a website (Node, Python, PHP, WordPress; S4.1-S4.3). It is not published anywhere
else: `agentcake setup --print --site` points at the copy inside the installed package, in the folder the data file
named by release.json "edge" says (agentcake.site_setup.edge_dir() looks there first, S6.1). Its tests and
development scripts stay in the repository (release.json "edge" -> "skip"), and so do node_modules and the other
names never shipped.
"""
import os
import shutil

from tools.releasing.settings import ReleaseError, package_folder


def build(tree, settings):
    """Copy the commit's edge/ into the package; returns the folder it was copied to."""
    rule = settings["edge"]
    source = os.path.join(tree, rule["folder"])
    target = package_folder(tree, settings, rule)
    if os.path.exists(target):
        raise ReleaseError(f"{os.path.relpath(target, tree)} is already in the commit: the middleware goes there")
    left_out = {os.path.normpath(os.path.join(source, path)) for path in rule["skip"]}
    missing = sorted(path for path in left_out if not os.path.exists(path))
    if missing:
        raise ReleaseError(f"release.json edge skip names what the commit does not have: {missing}")
    never = settings["package_files"]

    def ignore(folder, names):
        return [name for name in names
                if os.path.normpath(os.path.join(folder, name)) in left_out or name in never["skip_dirs"]
                or name in never["skip_names"] or name.endswith(tuple(never["skip_suffixes"]))]

    shutil.copytree(source, target, ignore=ignore)
    return target
