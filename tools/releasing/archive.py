"""The release folder, agentcake-<version>.tar.gz: Agent Cake ready to run, and what a server install needs.

One folder, agentcake-<version>/, holding what pyproject.toml's [tool.flit.sdist] names (bin/agentcake, the 0.3.x
entry points, INSTALL.md, SERVER.md, deploy/cake.service, Dockerfile, .dockerignore, ...), the package as the release
built it (compiled local pages, minified cake.js), pyproject.toml, the readme, the license files and PKG-INFO, so it
is also a source distribution (https://packaging.python.org/specifications/source-distribution-format/) that pip
can build. The wheel goes in too, alone in dist/ next to Dockerfile, which is where `docker build` takes it from
(SERVER.md, "Install with Docker"). Files are chosen the way flit_core chooses them for a source distribution: each
include pattern is a file or a folder (all of it), relative to the project; exclude patterns take files out again.
"""
import glob
import os
import posixpath

from tools.releasing import reproducible
from tools.releasing.project import is_executable
from tools.releasing.settings import ReleaseError, modes

PKG_INFO = "PKG-INFO"  # protocol: the source distribution's metadata file


def expand(root, pattern, skip):
    """The files (paths relative to root, with /) a pattern names: a file, or every file in a folder."""
    found = set()
    for match in glob.glob(pattern, root_dir=root, recursive=True):
        path = os.path.join(root, match)
        if os.path.isfile(path):
            found.add(match.replace(os.sep, "/"))
        for folder, dirs, names in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip["skip_dirs"]]
            for name in names:
                if name not in skip["skip_names"] and not name.endswith(tuple(skip["skip_suffixes"])):
                    found.add(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/"))
    return found


def chosen_files(project, settings):
    """Paths, relative to the project, of the files of the release folder besides the package and PKG-INFO."""
    rules = project.sdist_rules()
    skip = settings["package_files"]
    files = {"pyproject.toml", *project.license_files()}
    if project.readme():
        files.add(project.readme())
    for pattern in rules.get("include", []):
        matched = expand(project.root, pattern, skip)
        if not matched:
            raise ReleaseError(f"pyproject.toml [tool.flit.sdist] include: {pattern!r} matches nothing in the commit")
        files |= matched
    for pattern in rules.get("exclude", []):
        files -= expand(project.root, pattern, skip)
    return sorted(files)


def folders_of(names):
    """Every folder above the given paths, parents first."""
    found = set()
    for name in names:
        parent = posixpath.dirname(name)
        while parent:
            found.add(parent)
            parent = posixpath.dirname(parent)
    return sorted(found)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def entries(project, settings, wheel_path):
    """(name, bytes or None for a folder, executable) of the release folder, in the order they are written."""
    top = project.sdist_base()
    files = {name: (read(path), executable) for name, path, executable in project.package_files()}
    for name in chosen_files(project, settings):
        path = os.path.join(project.root, name)
        files[name] = (read(path), is_executable(path))
    files[PKG_INFO] = (project.metadata().encode("utf-8"), False)
    files[f"{settings['archive']['wheel_folder']}/{os.path.basename(wheel_path)}"] = (read(wheel_path), False)
    out = [(top, None, True)] + [(f"{top}/{folder}", None, True) for folder in folders_of(files)]
    out += [(f"{top}/{name}", data, executable) for name, (data, executable) in sorted(files.items())]
    return out


def build(project, out_dir, epoch, settings, wheel_path):
    """Write the release folder into out_dir as <name>-<version>.tar.gz; returns its path."""
    path = os.path.join(out_dir, project.sdist_base() + ".tar.gz")
    reproducible.write_tar_gz(path, entries(project, settings, wheel_path), epoch, modes(settings),
                              settings["zip_compresslevel"])
    return path
