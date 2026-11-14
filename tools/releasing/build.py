"""One release, from one commit, into one folder (S6.4): what `python3 -I tools/release.py build` runs.

The steps: export the commit (source.py) into a scratch folder; check its lists are fresh (bundled_lists.py) and its
cake.js current; build the local pages into the package (webapp.py), copy the sites' middleware into it
(middleware.py) and minify cake.js (cakejs.py); write the wheel, the .pyz and the release folder, then SHA256SUMS;
look for what must never ship (scan.py). Only when all of that passed are the files moved into the output folder,
which must be empty or missing: a release never mixes with older files and nothing in the folder is overwritten or
deleted. The summary names the commit, each file's size and sha256, and the tools used; a tool version other than
release.json "toolchain" is pointed out, since it can change bytes.
"""
import os
import platform
import shutil
import subprocess
import tempfile
import zlib

from tools.releasing import (archive, bundled_lists, cakejs, checksums, middleware, project as project_module, pyz,
                             scan, source, webapp, wheel)
from tools.releasing.settings import ROOT, SETTINGS_FILE, ReleaseError, load


def check_out_dir(out_dir):
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        raise ReleaseError(f"{out_dir} is not empty: move its files away (or pass --out <empty folder>); a release is "
                           "only ever written into an empty folder")
    if os.path.exists(out_dir) and not os.path.isdir(out_dir):
        raise ReleaseError(f"{out_dir} is a file, not a folder")


def node_version():
    try:
        return subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    except FileNotFoundError:
        return None


def toolchain_notes(settings, esbuild_version):
    """The tools this build used, and a note for each that differs from release.json "toolchain". zlib is named too:
    it compresses every file, and another zlib (another platform's) may compress the same bytes differently."""
    used = {"python": platform.python_version(), "zlib": zlib.ZLIB_RUNTIME_VERSION, "node": node_version(),
            "esbuild": esbuild_version}
    notes = [f"{tool} {used[tool]} here, release.json \"toolchain\" says {wanted}: the bytes may differ from a build "
             "with that one" for tool, wanted in settings["toolchain"].items()
             if not tool.startswith("$") and used.get(tool) != wanted]
    return used, notes


def prepare(repository, commit, tree, tag, log):
    """Export the commit into tree and make its package what the release ships; returns (settings, project, epoch,
    facts about the build)."""
    log(f"release: exporting commit {commit}")
    source.export(repository, commit, tree)
    settings_file = os.path.join(tree, os.path.relpath(SETTINGS_FILE, ROOT))
    if not os.path.isfile(settings_file):
        raise ReleaseError(f"commit {commit} has no {os.path.relpath(SETTINGS_FILE, ROOT)}: a release is built from a "
                           "commit, so commit the release tools first")
    settings = load(settings_file)
    project = project_module.Project(tree, settings)
    if tag is not None and tag != settings["tag_prefix"] + project.version:
        raise ReleaseError(f"tag {tag} does not match the version, {project.version} (agentcake/__init__.py)")
    epoch = source.commit_time(repository, commit)
    lists_age = bundled_lists.check_fresh(tree, settings, epoch)
    webapp.build(tree, settings)
    middleware.build(tree, settings)
    before, after, esbuild_version = cakejs.build(tree, settings)
    log(f"release: cake.js minified, {before} -> {after} bytes")
    return settings, project, epoch, {"lists_age_days": lists_age, "cakejs_bytes": [before, after],
                                      "esbuild": esbuild_version}


def write_files(project, settings, epoch, folder):
    """The wheel, the .pyz and the release folder (which holds the wheel), written into folder."""
    os.makedirs(folder)
    wheel_path = wheel.build(project, folder, epoch, settings)
    return [wheel_path, pyz.build(project, folder, epoch, settings),
            archive.build(project, folder, epoch, settings, wheel_path)]


def build(repository, out_dir, tag=None, log=print):
    """Build the release of the commit checked out in repository into out_dir; returns a summary (a dict)."""
    commit = source.head(repository)
    leftovers = source.uncommitted(repository)
    check_out_dir(out_dir)
    with tempfile.TemporaryDirectory(prefix="agentcake-release-") as scratch:
        settings, project, epoch, facts = prepare(repository, commit, os.path.join(scratch, "tree"), tag, log)
        built = os.path.join(scratch, "out")
        files = write_files(project, settings, epoch, built)
        personal = scan.personal_texts(repository, scratch, settings["scan"]["min_chars"])
        problems = scan.problems(files, personal, settings)
        if problems:
            raise ReleaseError("the release holds what it must not:\n  " + "\n  ".join(problems))
        files.append(checksums.write(files, built, settings, project))
        os.makedirs(out_dir, exist_ok=True)
        kept = [shutil.move(path, os.path.join(out_dir, os.path.basename(path))) for path in files]
    used, notes = toolchain_notes(settings, facts["esbuild"])
    return {"commit": commit, "version": project.version, "epoch": epoch, "uncommitted": leftovers,
            "toolchain": used, "notes": notes, "out_dir": out_dir, "files": kept,
            "lists_age_days": facts["lists_age_days"], "cakejs_bytes": facts["cakejs_bytes"]}
